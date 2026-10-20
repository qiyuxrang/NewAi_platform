"""Short, fenced transactions for private, durable Baichuan work.

Never perform model/network/file work inside these functions. A claimed job's
lease_owner and fence must accompany every checkpoint and item publication.
"""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .baichuan_assistant_models import BaichuanConversation, BaichuanExport, BaichuanJob, BaichuanJobItem, BaichuanMatchSnapshot, BaichuanMessage
from .baichuan_service import BaichuanError, can_access, require_access
from .models import User
from .product_parallel import atomic

KINDS = frozenset({"query", "parse", "research", "export"})
STAGES = frozenset({"", "parsing", "planning", "querying", "researching", "matching", "exporting"})
TERMINAL = frozenset({"partial", "completed", "failed", "cancelled"})
DEFAULT_BUDGET = {"timeout_seconds": 120, "max_model_calls": 8, "max_sources": 12, "max_attempts": 3}
MAX_BUDGET = {"timeout_seconds": 86400, "max_model_calls": 10000, "max_sources": 100000, "max_attempts": 5}


def _error(code, detail, status=409):
    return BaichuanError(code, detail, status)


def _scope(scope=None):
    actual = getattr(settings, "BAICHUAN_ASSISTANT_SCOPE", "default")
    if not isinstance(actual, str) or not 1 <= len(actual) <= 100:
        raise _error("scope_unconfigured", "百川任务范围尚未配置。", 503)
    if scope is not None and scope != actual:
        raise _error("not_found", "任务不存在或不可访问。", 404)
    return actual


def _fresh(user):
    current = User.objects.filter(pk=getattr(user, "pk", None), is_active=True, must_change_password=False).first()
    if not current or current.session_version != getattr(user, "session_version", None):
        raise _error("not_found", "任务不存在或不可访问。", 404)
    return current


def _object(value, limit=512000):
    if not isinstance(value, dict):
        raise _error("invalid_request", "任务参数须为 JSON 对象。", 400)
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise _error("invalid_request", "任务参数不是合法 JSON。", 400) from None
    if len(encoded.encode()) > limit:
        raise _error("payload_too_large", "任务参数超过限制。", 413)
    return json.loads(encoded)


def _key(value, label="任务标识", maximum=100):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise _error("invalid_request", f"{label}无效。", 400)
    return value


def _unlimited_query_models(kind):
    return kind == "query" and getattr(settings, "BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS", False) is True


def _budget(value, *, kind, allow_stored_query_budget=False):
    value = {} if value is None else _object(value, 2000)
    if set(value) - set(DEFAULT_BUDGET):
        raise _error("invalid_budget", "预算包含不支持的字段。", 400)
    result = {**DEFAULT_BUDGET, **value}
    if _unlimited_query_models(kind) and "max_model_calls" not in value:
        result["max_model_calls"] = None
    nullable_model_limit = kind == "query" and (_unlimited_query_models(kind) or allow_stored_query_budget)
    if any(not (k == "max_model_calls" and v is None and nullable_model_limit)
           and (type(v) is not int or not 1 <= v <= MAX_BUDGET[k]) for k, v in result.items()):
        raise _error("invalid_budget", "预算必须为限制范围内的正整数。", 400)
    return result


def _request_digest(kind, payload, budget, conversation_id=None, message_id=None, parent_job_id=None):
    request = {"kind": kind, "payload": payload, "budget": budget,
               "conversation": str(conversation_id) if conversation_id else None,
               "message": str(message_id) if message_id else None,
               "parent_job": str(parent_job_id) if parent_job_id else None}
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def job_for(user, job_id, *, scope=None, lock=False):
    current = _fresh(user)
    if not can_access(current):
        raise _error("not_found", "任务不存在或不可访问。", 404)
    try:
        rows = BaichuanJob.objects.select_for_update() if lock else BaichuanJob.objects.all()
        return rows.get(pk=job_id, owner=current, scope=_scope(scope))
    except (BaichuanJob.DoesNotExist, ValueError, TypeError, ValidationError):
        raise _error("not_found", "任务不存在或不可访问。", 404) from None


def enqueue_job(user, *, kind, payload, idempotency_key, scope=None, conversation=None,
                message=None, budget=None, execution_actor=None, parent_job=None):
    scope, payload = _scope(scope), _object(payload)
    requested_budget = budget
    _key(idempotency_key)
    if kind not in KINDS:
        raise _error("invalid_request", "不支持的任务类型。", 400)
    with atomic():
        current = _fresh(user)
        # Serializes duplicate submissions for the same owner in PostgreSQL.
        User.objects.select_for_update().get(pk=current.pk)
        require_access(current, write=kind == "research")
        if execution_actor is not None and execution_actor.pk != current.pk:
            raise _error("forbidden_execution_identity", "不能指定其他用户作为任务执行身份。", 403)
        if conversation is not None:
            conversation = BaichuanConversation.objects.filter(pk=conversation.pk, owner=current, scope=scope).first()
            if conversation is None:
                raise _error("not_found", "会话不存在或不可访问。", 404)
        if message is not None:
            if conversation is None or not BaichuanMessage.objects.filter(pk=message.pk, conversation=conversation).exists():
                raise _error("not_found", "消息不存在或不可访问。", 404)
        if parent_job is not None:
            parent_job = BaichuanJob.objects.filter(pk=parent_job.pk, owner=current, scope=scope).first()
            if parent_job is None:
                raise _error("not_found", "任务不存在或不可访问。", 404)
        existing = BaichuanJob.objects.filter(owner=current, scope=scope, idempotency_key=idempotency_key).first()
        # A retry preserves its original JSON budget and request hash even if
        # configuration has changed. Only a trusted stored query can inherit a
        # null limit while the local unlimited-query switch is disabled.
        budget = _budget(budget, kind=kind, allow_stored_query_budget=bool(
            (parent_job and parent_job.kind == kind == "query" and budget == parent_job.budget)
            or (existing and existing.kind == kind == "query" and existing.budget.get("max_model_calls") is None)))
        digest = _request_digest(kind, payload, budget, conversation.pk if conversation else None,
                                 message.pk if message else None, parent_job.pk if parent_job else None)
        if existing:
            # Defaults are resolved once, when a request is first accepted.
            # Changing a server default must not break an identical replay,
            # including callers that explicitly supplied only some fields.
            replay_budget = {**existing.budget, **(requested_budget or {})}
            digest = _request_digest(kind, payload, replay_budget, conversation.pk if conversation else None,
                message.pk if message else None, parent_job.pk if parent_job else None)
            if existing.request_hash != digest:
                raise _error("idempotency_conflict", "同一请求标识已用于不同内容。")
            return existing, False
        return BaichuanJob.objects.create(owner=current, execution_actor=current, scope=scope,
            kind=kind, conversation=conversation, message=message, payload=payload, budget=budget,
            idempotency_key=idempotency_key, request_hash=digest, parent_job=parent_job), True


def _authorized(job):
    owner = User.objects.filter(pk=job.owner_id, is_active=True, must_change_password=False).first()
    actor = User.objects.filter(pk=job.execution_actor_id, is_active=True, must_change_password=False).first()
    return bool(owner and actor and can_access(owner) and can_access(actor, write=job.kind == "research"))


def _finish(job, status, error_code=""):
    job.status, job.error_code = status, error_code
    job.lease_owner, job.lease_expires_at = "", None
    if status in TERMINAL:
        job.finished_at = timezone.now()
    job.save()


def _expired_budget(job, now):
    return bool(job.started_at and (now - job.started_at).total_seconds() >= job.budget["timeout_seconds"])


def claim_job(worker_id, *, job_id=None, scope=None, lease_seconds=30):
    _key(worker_id, "执行器标识")
    _lease_seconds(lease_seconds)
    scope = _scope(scope)
    with atomic():
        now = timezone.now()
        rows = BaichuanJob.objects.select_for_update().filter(scope=scope).filter(
            Q(status="queued") | Q(status="running", lease_expires_at__lte=now))
        if job_id is not None:
            try:
                rows = rows.filter(pk=job_id)
            except (ValidationError, ValueError, TypeError):
                return None
        for job in rows.order_by("created_at", "id")[:100]:
            if not _authorized(job):
                _finish(job, "failed", "permission_revoked")
                continue
            if _expired_budget(job, now) or job.attempts >= job.budget["max_attempts"]:
                _finish(job, "partial" if job.result_ref else "failed", "budget_exhausted")
                continue
            model_wait = job.checkpoint.get("model_wait")
            if model_wait is not None:
                try:
                    not_before = parse_datetime(model_wait.get("not_before", "")) if isinstance(model_wait, dict) else None
                except (TypeError, ValueError):
                    not_before = None
                if not_before is None or timezone.is_naive(not_before):
                    _finish(job, "failed", "invalid_checkpoint")
                    continue
                if not_before > now:
                    continue
            dependency = job.checkpoint.get("dependency_job_id")
            if dependency and not BaichuanMatchSnapshot.objects.filter(conversation_id=job.conversation_id,
                    condition_revision=job.payload.get("parent_revision"), job__owner_id=job.owner_id,
                    job__scope=scope).exists():
                if BaichuanJob.objects.filter(pk=dependency, owner_id=job.owner_id, scope=scope,
                        conversation_id=job.conversation_id, status__in=["queued", "running"]).exists():
                    continue  # Do not starve later independent jobs while a parent runs.
            job.status, job.lease_owner = "running", worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.fence += 1
            job.attempts += 1
            job.started_at = job.started_at or now
            job.finished_at, job.error_code = None, ""
            job.save()
            return job
    return None


def _lease_seconds(value):
    if type(value) is not int or not 1 <= value <= 300:
        raise _error("invalid_request", "任务租约须为 1 至 300 秒。", 400)


@contextmanager
def leased_job(job_id, worker_id, fence):
    """Guard for atomic business writes coupled to a job checkpoint.

    Callers may write fact revisions and checkpoint in this same short
    transaction; never yield to a model or network client while inside it.
    """
    error = None
    with atomic():
        try:
            job = BaichuanJob.objects.select_for_update().get(pk=job_id, scope=_scope())
        except (BaichuanJob.DoesNotExist, ValidationError, ValueError, TypeError):
            raise _error("not_found", "任务不存在或不可访问。", 404) from None
        now = timezone.now()
        if (type(fence) is not int or job.status != "running" or job.lease_owner != worker_id
                or job.fence != fence or not job.lease_expires_at or job.lease_expires_at <= now):
            raise _error("stale_lease", "执行租约已失效，请恢复任务。")
        if not _authorized(job):
            _finish(job, "failed", "permission_revoked")
            error = _error("permission_revoked", "任务权限已变更，执行已停止。", 403)
        elif _expired_budget(job, now):
            _finish(job, "partial" if job.result_ref else "failed", "budget_exhausted")
            error = _error("budget_exhausted", "任务预算已耗尽，已保存恢复点。", 429)
        else:
            yield job
    # Persist stopped state before returning an error to the caller.
    if error:
        raise error


def heartbeat(job_id, worker_id, fence, *, lease_seconds=30):
    _lease_seconds(lease_seconds)
    with leased_job(job_id, worker_id, fence) as job:
        job.lease_expires_at = timezone.now() + timedelta(seconds=lease_seconds)
        job.save(update_fields=["lease_expires_at", "updated_at"])
        return job


def defer_job(job_id, worker_id, fence, *, reason, dependency_job):
    """Release a query waiting on its own conversation without spending attempts."""
    _key(reason, "等待原因")
    with leased_job(job_id, worker_id, fence) as job:
        dependency = BaichuanJob.objects.filter(pk=dependency_job.pk, kind="query", owner_id=job.owner_id,
            scope=job.scope, conversation_id=job.conversation_id).first()
        if (job.kind != "query" or dependency is None or dependency.pk == job.pk
                or dependency.payload.get("condition_revision") != job.payload.get("parent_revision")):
            raise _error("invalid_dependency", "任务依赖不属于前轮条件。", 400)
        job.checkpoint = _object({**job.checkpoint, "dependency_job_id": str(dependency.pk), "dependency_reason": reason}, 64000)
        job.status, job.stage, job.error_code = "queued", "", ""
        job.lease_owner, job.lease_expires_at = "", None
        job.attempts, job.fence = max(0, job.attempts - 1), job.fence + 1
        job.save()
        return job


def save_job(job_id, worker_id, fence, *, stage=None, checkpoint=None, counts=None,
             result_ref=None, status=None, error_code=""):
    if stage is not None and stage not in STAGES:
        raise _error("invalid_request", "任务阶段无效。", 400)
    if status is not None and status not in TERMINAL | {"running", "awaiting_input"}:
        raise _error("invalid_request", "任务状态转换无效。", 400)
    with leased_job(job_id, worker_id, fence) as job:
        if stage is not None:
            job.stage = stage
        if checkpoint is not None:
            job.checkpoint = _object(checkpoint, 64000)
        if counts is not None:
            counts = _object(counts, 8000)
            if any(not isinstance(k, str) or k.startswith("_budget_") or type(v) is not int or v < 0 for k, v in counts.items()):
                raise _error("invalid_request", "进度计数须为非负整数。", 400)
            job.counts = {**job.counts, **counts}
        if result_ref is not None:
            job.result_ref = _object(result_ref)
        if status in TERMINAL | {"awaiting_input"}:
            _finish(job, status, error_code)
        else:
            job.save()
        return job


def consume_budget(job_id, worker_id, fence, *, model_calls=0, sources=0):
    if any(type(v) is not int or v < 0 for v in (model_calls, sources)):
        raise _error("invalid_request", "预算用量须为非负整数。", 400)
    error = None
    with leased_job(job_id, worker_id, fence) as job:
        counts = dict(job.counts)
        counts["_budget_model_calls"] = counts.get("_budget_model_calls", 0) + model_calls
        counts["_budget_sources"] = counts.get("_budget_sources", 0) + sources
        model_limit = job.budget["max_model_calls"]
        if not _unlimited_query_models(job.kind) and model_limit is None:
            # Safe downgrade for a query accepted with an unlimited default;
            # never rewrite its immutable request budget during configuration changes.
            model_limit = DEFAULT_BUDGET["max_model_calls"]
        model_exhausted = not _unlimited_query_models(job.kind) and counts["_budget_model_calls"] > model_limit
        if model_exhausted or counts["_budget_sources"] > job.budget["max_sources"]:
            _finish(job, "partial" if job.result_ref else "failed", "budget_exhausted")
            error = _error("budget_exhausted", "任务预算已耗尽，已保存恢复点。", 429)
        else:
            job.counts = counts
            job.save(update_fields=["counts", "updated_at"])
    if error:
        raise error
    return job


def save_item(job_id, worker_id, fence, *, item_key, status, stage="", checkpoint=None,
              result=None, company=None, error_code=""):
    _key(item_key, "工作项标识", 200)
    if status not in {"pending", "running", "completed", "partial", "failed", "cancelled"} or stage not in STAGES:
        raise _error("invalid_request", "工作项状态或阶段无效。", 400)
    with leased_job(job_id, worker_id, fence) as job:
        item, created = BaichuanJobItem.objects.get_or_create(job=job, item_key=item_key)
        if not created and item.status == "completed":
            # Idempotent retries retain completed results; never rewrite them.
            if result is not None and item.result != _object(result):
                raise _error("item_conflict", "工作项已经完成，不能改写结果。")
            return item
        if item.company_id and company is not None and item.company_id != company.pk:
            raise _error("item_conflict", "工作项所属企业不能变更。")
        if status == "running" and item.status != "running":
            item.attempts += 1
        item.status, item.stage, item.error_code = status, stage, error_code
        if company is not None:
            item.company = company
        if checkpoint is not None:
            item.checkpoint = _object(checkpoint, 64000)
        if result is not None:
            item.result = _object(result)
        item.save()
        return item


def cancel_job(user, job_id, *, scope=None):
    with atomic():
        job = job_for(user, job_id, scope=scope, lock=True)
        if job.status not in TERMINAL:
            job.fence += 1
            _finish(job, "cancelled")
            job.items.exclude(status__in=["completed", "partial", "failed", "cancelled"]).update(status="cancelled", updated_at=timezone.now())
        return job


def retry_job(user, job_id, *, idempotency_key, scope=None):
    with atomic():
        old = job_for(user, job_id, scope=scope, lock=True)
        if old.status not in {"partial", "failed", "cancelled", "awaiting_input"}:
            raise _error("invalid_transition", "当前任务无需重试。")
        if old.request_hash != _request_digest(old.kind, old.payload, old.budget,
                old.conversation_id, old.message_id, old.parent_job_id):
            raise _error("invalid_export_retry" if old.kind == "export" else "request_changed",
                         "原任务请求校验失败，不能重试。")
        job, created = enqueue_job(user, kind=old.kind, payload=old.payload, budget=old.budget,
            idempotency_key=idempotency_key, scope=old.scope, conversation=old.conversation,
            message=old.message, parent_job=old)
        if created:
            if old.kind == "export":
                previous = BaichuanExport.objects.select_related("snapshot__conversation", "snapshot__job").filter(job=old, owner_id=user.pk).first()
                if (previous is None or previous.authorization.get("scope") != old.scope
                        or previous.snapshot.conversation.owner_id != user.pk
                        or previous.snapshot.conversation.scope != old.scope
                        or previous.snapshot.job.scope != old.scope
                        or old.payload.get("snapshot_id") != str(previous.snapshot_id)
                        or old.payload.get("selection") != previous.selection
                        or old.payload.get("fields") != previous.fields):
                    raise _error("invalid_export_retry", "导出快照或授权信息不一致，不能重试。")
                BaichuanExport.objects.create(owner_id=user.pk, job=job, snapshot=previous.snapshot,
                    selection=previous.selection, fields=previous.fields, authorization=previous.authorization)
            job.checkpoint = {**old.checkpoint, "retry_of": str(old.pk)}
            job.result_ref = old.result_ref
            # Completed checkpoints survive the retry, so their visible progress
            # must survive too. Invocation budgets belong to the fresh attempt.
            job.counts = {key: value for key, value in old.counts.items() if not key.startswith("_budget_")}
            job.save(update_fields=["checkpoint", "result_ref", "counts", "updated_at"])
        return job, created
