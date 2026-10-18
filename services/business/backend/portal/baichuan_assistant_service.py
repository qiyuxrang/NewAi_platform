"""Private conversations and bounded attachment storage; no enterprise fact writes."""
import hashlib
import json
from pathlib import Path
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .baichuan_assistant_models import BaichuanAttachment, BaichuanConversation, BaichuanMessage
from .baichuan_service import BaichuanError, require_access


def scope():
    return settings.BAICHUAN_ASSISTANT_SCOPE


def require_assistant(user):
    require_access(get_user_model().objects.get(pk=user.pk))
    if not settings.BAICHUAN_ASSISTANT_ENABLED:
        raise BaichuanError("assistant_unavailable", "百川助手尚未启用，现有企业列表仍可使用。", 503)


def conversation_for(user, conversation_id, *, lock=False):
    require_assistant(user)
    try:
        rows = BaichuanConversation.objects.select_for_update() if lock else BaichuanConversation.objects
        return rows.get(pk=conversation_id, owner=user, scope=scope())
    except (BaichuanConversation.DoesNotExist, ValueError, TypeError, ValidationError):
        raise BaichuanError("not_found", "对话不存在或不可访问。", 404) from None


def root():
    path = Path(settings.BAICHUAN_STORAGE_ROOT).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def storage_path(key):
    # Only server-generated scalar UUID filenames can ever address private files.
    try:
        valid = isinstance(key, str) and str(uuid.UUID(key)) == key
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise BaichuanError("not_found", "附件不存在或不可访问。", 404)
    path = root() / key
    if path.is_symlink() or path.resolve().parent != root():
        raise BaichuanError("not_found", "附件不存在或不可访问。", 404)
    return path


def job_data(job):
    return {"id": str(job.pk), "kind": job.kind, "status": job.status, "stage": job.stage,
            "counts": {k: v for k, v in job.counts.items() if not k.startswith("_budget_")}, "result_ref": job.result_ref, "error_code": job.error_code,
            "updated_at": job.updated_at.isoformat(), "checkpoint": {k: v for k, v in job.checkpoint.items()
                if k in {"summary", "warnings", "capability_gaps", "condition_revision"}}}


def message_data(message):
    return {"id": str(message.pk), "role": message.role, "content": message.content,
            "condition_revision": message.condition_revision, "metadata": message.metadata}


def attachment_data(attachment):
    return {"id": str(attachment.pk), "original_name": attachment.original_name,
            "parse_status": attachment.parse_status, "error_code": attachment.error_code}


def export_intent(text):
    """Recognize explicit combined query/export requests without selecting a mode."""
    if "导出" not in text or re.search(r"(?:不(?:要|用|必)?|无需|别)\s*导出", text):
        return None
    selection = {"include_candidates": "包含候选" in text and "不包含候选" not in text}
    limit = re.search(r"导出(?:这些公司|当前结果|结果)?\s*前\s*(\d+)\s*(?:条|家)", text)
    if limit:
        value = int(limit.group(1))
        if not 1 <= value <= 5000:
            raise BaichuanError("invalid_request", "导出条数须为 1 至 5000。")
        selection["limit"] = value
    return selection


def store_attachment(user, conversation_id, upload):
    conversation = conversation_for(user, conversation_id)
    name = upload.name or ""
    if (not name or len(name) > 255 or Path(name).name != name or "/" in name or "\\" in name
            or any(ord(c) < 32 for c in name)):
        raise BaichuanError("invalid_filename", "附件名称无效。")
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise BaichuanError("unsupported_file", "请上传 PDF 或 DOCX，旧 DOC 请先另存为 DOCX。")
    content = upload.read(20 * 1024 * 1024 + 1)
    if not content or len(content) > 20 * 1024 * 1024:
        raise BaichuanError("upload_too_large", "附件为空或超过 20 MiB。", 413)
    if (suffix == ".pdf" and not content.startswith(b"%PDF-")) or (suffix == ".docx" and not content.startswith(b"PK\x03\x04")):
        raise BaichuanError("invalid_document", "附件内容与格式不符。")
    if suffix == ".docx":
        from .source_parsers.core import ParseError, safe_zip
        try:
            archive = safe_zip(content, "word/document.xml")
            archive.close()
        except ParseError as error:
            raise BaichuanError(error.code, error.detail) from None
    key = str(uuid.uuid4())
    path = storage_path(key)
    try:
        with path.open("xb") as stream:
            stream.write(content)
        with transaction.atomic():
            conversation_for(user, conversation.pk, lock=True)
            return BaichuanAttachment.objects.create(conversation=conversation, owner=user, original_name=name,
                media_type="application/pdf" if suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), storage_ref=key)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@transaction.atomic
def submit_message(user, conversation_id, payload):
    from .baichuan_jobs import enqueue_job
    conversation = conversation_for(user, conversation_id, lock=True)
    if not isinstance(payload, dict) or set(payload) - {"text", "attachment_ids", "parent_revision", "client_request_id"}:
        raise BaichuanError("invalid_request", "消息字段无效。")
    text, ids, key = payload.get("text", ""), payload.get("attachment_ids", []), payload.get("client_request_id")
    parent = payload.get("parent_revision")
    if (not isinstance(text, str) or len(text) > 20000 or "\x00" in text
            or not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(i, str) for i in ids)
            or len(set(ids)) != len(ids) or not (text.strip() or ids)
            or not isinstance(key, str) or not key or len(key) > 100 or type(parent) is not int):
        raise BaichuanError("invalid_request", "请填写需求或上传最多三份文件，并提供有效消息编号。")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = conversation.messages.filter(client_request_id=key).first()
    if existing:
        if existing.request_hash != digest:
            raise BaichuanError("idempotency_conflict", "相同消息编号包含不同内容。", 409)
        return existing, existing.jobs.filter(parent_job__isnull=True).order_by("created_at").first(), False
    if parent != conversation.condition_revision:
        raise BaichuanError("revision_conflict", "对话条件已更新，请恢复最新对话后重试。", 409)
    pending = conversation.jobs.filter(owner=user, scope=scope(), kind="query", status__in=["awaiting_input", "failed", "partial"],
        payload__condition_revision=parent).order_by("-created_at").first()
    replacement = None
    replacement_text = text
    replacement_prefixes = {
        "放弃本轮未读附件，改用本轮文字：": "text",
        "放弃本轮未读附件，改用本轮文件：": "file",
    }
    # Only this owner-authored message can authorize abandoning the one failed
    # unreadable attachment. Quotes, negations and attachment text never enter
    # this anchored branch; ordinary follow-ups still carry pending files.
    mode = next((mode for prefix, mode in replacement_prefixes.items() if text.startswith(prefix)), None)
    if mode:
        prefix = next(prefix for prefix, value in replacement_prefixes.items() if value == mode)
        replacement_text = text[len(prefix):].strip()
        if (not pending or pending.error_code != "attachment_unreadable"
                or not replacement_text or (mode == "text" and ids)
                or (mode == "file" and not ids)):
            raise BaichuanError("invalid_attachment_replacement",
                "仅能明确替换本轮未读附件；改用文字时请提供完整需求且不附新文件，改用文件时请上传新文件并填写说明。")
    if pending and pending.checkpoint.get("pending_attachment_ids"):
        carry = pending.checkpoint["pending_attachment_ids"]
        if not isinstance(carry, list) or any(not isinstance(identifier, str) for identifier in carry):
            raise BaichuanError("not_found", "附件不存在或不可访问。", 404)
        if mode:
            if mode == "file" and not any(identifier not in carry for identifier in ids):
                raise BaichuanError("invalid_attachment_replacement", "请实际上传本轮新文件，不能以原待确认附件代替新文件。")
            issue = pending.checkpoint.get("attachment_issue")
            abandoned = issue.get("attachment_id") if isinstance(issue, dict) else None
            try:
                if (not isinstance(abandoned, str) or str(uuid.UUID(abandoned)) != abandoned
                        or abandoned not in carry or abandoned in ids):
                    raise ValueError
                # Validate all originals before dropping any reference, so a
                # forged foreign diagnostic cannot bypass the existing 404.
                authorized_ids = list(dict.fromkeys([*carry, *ids]))
                if BaichuanAttachment.objects.filter(pk__in=authorized_ids,
                        conversation=conversation, owner=user).count() != len(authorized_ids):
                    raise ValueError
            except (ValueError, TypeError, ValidationError):
                raise BaichuanError("not_found", "附件不存在或不可访问。", 404) from None
            carry = [identifier for identifier in carry if identifier != abandoned]
            replacement = {"failed_job_id": str(pending.pk), "attachment_id": abandoned, "mode": mode}
        ids = list(dict.fromkeys([*carry, *ids]))
        if len(ids) > 3:
            raise BaichuanError("invalid_request", "待确认附件与新附件合计最多三份，请先完成待确认文件的解析。")
    if mode and replacement is None:
        raise BaichuanError("invalid_attachment_replacement", "当前没有可明确替换的未读附件，请重试原任务或提供完整需求。")
    export_only = not ids and re.fullmatch(r"(?:请|帮我)?导出(?:这些公司|当前结果|结果)?(?:前\s*\d+\s*(?:条|家))?(?:为)?(?:\s*(?:Excel|excel|EXCEL|xlsx))?(?:，?包含候选)?[。！!]?", text.strip())
    if export_only:
        from .baichuan_exports import enqueue_export
        snapshot = conversation.snapshots.filter(condition_revision=conversation.condition_revision).order_by("-result_revision", "-created_at").first()
        if not snapshot:
            raise BaichuanError("result_required", "请先检索企业，再导出当前结果。")
        message = BaichuanMessage.objects.create(conversation=conversation, role="user", content=text.strip(),
            condition_revision=conversation.condition_revision, client_request_id=key, request_hash=digest)
        selection = {"client_request_id": "message:" + str(message.pk), "include_candidates": "包含候选" in text}
        limit = re.search(r"前\s*(\d+)\s*(?:条|家)", text)
        if limit:
            selection["limit"] = int(limit.group(1))
        job = enqueue_export(user, snapshot.pk, selection, message=message)
        return message, job, True
    try:
        found = BaichuanAttachment.objects.filter(pk__in=ids, conversation=conversation, owner=user)
        if found.count() != len(ids):
            raise ValueError
    except (ValueError, ValidationError):
        raise BaichuanError("not_found", "附件不存在或不可访问。", 404) from None
    conversation.condition_revision += 1
    conversation.save(update_fields=["condition_revision", "updated_at"])
    message = BaichuanMessage.objects.create(conversation=conversation, role="user", content=text.strip(),
        condition_revision=conversation.condition_revision, client_request_id=key, request_hash=digest,
        metadata={"attachment_ids": ids})
    job, _ = enqueue_job(user, kind="query", payload={"text": replacement_text.strip(), "attachment_ids": ids,
        "condition_revision": conversation.condition_revision, "parent_revision": parent,
        "export": export_intent(text)},
        idempotency_key="message:" + str(message.pk), conversation=conversation, message=message)
    if ids or replacement:
        # Payload/hash already include these authorized IDs. Checkpoint metadata
        # survives a parser/model failure until validated conditions consume it.
        base = (pending.checkpoint.get("conditions") or pending.checkpoint.get("pending_base_conditions")) if pending else None
        base_checkpoint = pending.checkpoint if pending else {}
        previous_snapshot = None
        if base is None:
            # A newly uploaded unreadable file can fail in _parse before the
            # worker inherits the immediately preceding completed conditions.
            # Capture that exact revision here; never jump over an unresolved
            # round by selecting an arbitrary older snapshot.
            previous_snapshot = conversation.snapshots.filter(condition_revision=parent, job__owner=user, job__scope=scope()).order_by(
                "-result_revision", "-created_at").first()
            if previous_snapshot:
                base = previous_snapshot.condition_tree
                base_checkpoint = previous_snapshot.job.checkpoint
        job.checkpoint = {"pending_attachment_ids": ids, "pending_base_conditions": base}
        if pending and "file_requirements" in pending.checkpoint:
            job.checkpoint["file_requirements"] = pending.checkpoint["file_requirements"]
        elif previous_snapshot and "file_requirements" in previous_snapshot.job.checkpoint:
            job.checkpoint["file_requirements"] = previous_snapshot.job.checkpoint["file_requirements"]
        # Carry only the gate state already bound to this exact base. A parser
        # failure occurs before the worker can inherit it. Never manufacture
        # validated relation keys or turn an unanswered question into proof.
        for guard_key in ("grade_relation_guard", "grade_relation_question", "grade_relation_gaps"):
            if guard_key in base_checkpoint:
                job.checkpoint[guard_key] = base_checkpoint[guard_key]
        if pending and pending.checkpoint.get("grade_relation_question"):
            job.checkpoint["grade_relation_question"] = pending.checkpoint["grade_relation_question"]
            if "grade_relation_gaps" in pending.checkpoint:
                job.checkpoint["grade_relation_gaps"] = pending.checkpoint["grade_relation_gaps"]
        if replacement:
            job.checkpoint["attachment_replacement"] = {**replacement, "message_id": str(message.pk)}
        job.save(update_fields=["checkpoint", "updated_at"])
    return message, job, True
