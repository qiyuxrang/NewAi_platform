"""Fixed-denominator research queue; coverage is separate from verification.

This module performs no external requests. Workers acquire public sources
outside transactions, then publish bounded batches under a current fence.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils import timezone

from .baichuan_assistant_models import (BaichuanEvidence, BaichuanJob, BaichuanJobItem, BaichuanResearchItem,
    BaichuanResearchManifest)
from .baichuan_facts import evidence_is_valid
from .baichuan_jobs import _fresh, _object, _scope, enqueue_job, leased_job
from .baichuan_models import Company
from .baichuan_service import BaichuanError, can_access, require_access
from .product_parallel import atomic


RESEARCH_FIELDS = ("identity", "province", "city", "website", "website_kind", "phone", "email", "address",
    "contact_name", "contact_phone", "people", "qualifications")
RESULT_STATUSES = {"verified", "not_disclosed", "not_found", "inaccessible", "conflict", "pending_review", "failed", "merged", "removed"}


def manifest_for(user, manifest_id):
    current = _fresh(user)
    if not can_access(current, write=True):
        raise BaichuanError("not_found", "研究清单不存在或不可访问。", 404)
    try:
        return BaichuanResearchManifest.objects.select_related("job").get(pk=manifest_id, owner=current, scope=_scope())
    except (BaichuanResearchManifest.DoesNotExist, ValueError, TypeError, ValidationError):
        raise BaichuanError("not_found", "研究清单不存在或不可访问。", 404) from None


def create_manifest(user, idempotency_key, *, fields=None, parent_manifest_id=None, budget=None):
    current = _fresh(user)
    require_access(current, write=True)
    if not getattr(settings, "BAICHUAN_RESEARCH_ENABLED", False):
        raise BaichuanError("research_disabled", "资料研究尚未启用。", 503)
    dataset_kind = getattr(settings, "BAICHUAN_DATASET_KIND", "unconfirmed")
    environment_label = getattr(settings, "BAICHUAN_ENVIRONMENT_LABEL", "")
    if dataset_kind not in {"isolation", "actual"} or not environment_label:
        raise BaichuanError("dataset_unconfirmed", "尚未确认研究数据源，不能创建全库清单。", 503)
    backup_ref = getattr(settings, "BAICHUAN_TARGET_BACKUP_REF", "")
    if dataset_kind == "actual" and (not getattr(settings, "BAICHUAN_TARGET_DATASET_CONFIRMED", False) or not backup_ref):
        raise BaichuanError("dataset_unconfirmed", "真实全库研究须先确认数据源并记录备份。", 503)
    fields = list(RESEARCH_FIELDS) if fields is None else fields
    if (not isinstance(fields, list) or not fields or any(not isinstance(field, str) or field not in RESEARCH_FIELDS for field in fields)
            or len(fields) != len(set(fields))):
        raise BaichuanError("invalid_request", "研究字段无效或重复。")
    parent = manifest_for(current, parent_manifest_id) if parent_manifest_id else None
    if parent and fields != parent.fields:
        raise BaichuanError("invalid_request", "增量清单须沿用原清单字段。")
    if parent and (parent.job.payload.get("dataset_kind") != dataset_kind
            or parent.job.payload.get("environment_label") != environment_label):
        raise BaichuanError("invalid_request", "增量清单不能跨数据源创建。")
    manifest_id = uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan-research:{_scope()}:{current.pk}:{idempotency_key}")
    payload = {"manifest_id": str(manifest_id), "fields": fields, "parent_manifest_id": str(parent.pk) if parent else None,
        "dataset_kind": dataset_kind, "environment_label": environment_label, "backup_ref": backup_ref}
    with atomic():
        job, created = enqueue_job(current, kind="research", payload=payload, idempotency_key=idempotency_key,
            budget={"timeout_seconds": 86400, "max_model_calls": 10000, "max_sources": 100000} if budget is None else budget)
        if not created:
            return BaichuanResearchManifest.objects.get(job=job), False
        excluded = set()
        ancestor = parent
        while ancestor:
            excluded.update(item["id"] for item in ancestor.company_versions)
            ancestor = ancestor.parent_manifest
        versions = [{"id": str(pk), "version": version} for pk, version in Company.objects.order_by("id")
            .exclude(pk__in=excluded).values_list("id", "version")]
        manifest = BaichuanResearchManifest.objects.create(id=manifest_id, owner=current, scope=job.scope, job=job,
            parent_manifest=parent, company_versions=versions, total_count=len(versions), fields=fields)
        BaichuanResearchItem.objects.bulk_create([BaichuanResearchItem(manifest=manifest, company_id=item["id"],
            company_version=item["version"], field=field) for item in versions for field in fields], batch_size=500)
        BaichuanJobItem.objects.bulk_create([BaichuanJobItem(job=job, company_id=item["id"],
            item_key=f'{item["id"]}:{field}', stage="researching") for item in versions for field in fields], batch_size=500)
        job.counts = {"total_companies": len(versions), "total_fields": len(versions) * len(fields),
            "researched_companies": 0, "attempted_companies": 0, "completed_company_attempts": 0,
            "verified_fields": 0, "attempted_fields": 0}
        job.checkpoint = {"manifest_id": str(manifest.pk), "last_items": []}
        if not versions:
            job.status, job.error_code, job.finished_at = "partial", "empty_manifest", timezone.now()
        job.save()
        return manifest, True


def coverage_report(manifest):
    items = manifest.items.all()
    grouped = list(items.values("field", "status").annotate(count=Count("id")))
    by_field = {field: {"total": manifest.total_count, "pending": 0, **{status: 0 for status in RESULT_STATUSES}} for field in manifest.fields}
    totals = {"pending": 0, **{status: 0 for status in RESULT_STATUSES}}
    for item in grouped:
        by_field[item["field"]][item["status"]] = item["count"]
        totals[item["status"]] += item["count"]
    companies = items.values("company_id").annotate(
        attempted=Count("id", filter=Q(attempts__gt=0)),
        unfinished=Count("id", filter=Q(status__in=["pending", "failed"])),
        unverified=Count("id", filter=~Q(status="verified")))
    researched = companies.filter(unfinished=0).count()
    fully_verified = companies.filter(unverified=0).count()
    current_ids = set(str(pk) for pk in Company.objects.filter(pk__in=[entry["id"] for entry in manifest.company_versions]).values_list("pk", flat=True))
    latest_job = BaichuanJob.objects.filter(owner=manifest.owner, scope=manifest.scope, kind="research",
        payload__manifest_id=str(manifest.pk)).order_by("-created_at", "-id").first() or manifest.job
    return {"manifest_id": str(manifest.pk), "job_id": str(latest_job.pk), "parent_manifest_id": str(manifest.parent_manifest_id) if manifest.parent_manifest_id else None,
        "dataset_kind": manifest.job.payload.get("dataset_kind", "unconfirmed"),
        "environment_label": manifest.job.payload.get("environment_label", ""),
        "state": "empty" if manifest.total_count == 0 else latest_job.status, "fixed_denominator": True,
        "total_companies": manifest.total_count, "total_fields": manifest.total_count * len(manifest.fields),
        "research_fields": manifest.fields, "full_field_scope": set(manifest.fields) == set(RESEARCH_FIELDS),
        "researched_companies": researched, "fully_verified_companies": fully_verified,
        # Kept for API compatibility: terminal inaccessible outcomes count here.
        # This is attempt completion, never readable-source or fact coverage.
        "attempted_companies": companies.filter(attempted__gt=0).count(),
        "completed_company_attempts": researched,
        "research_coverage_basis": "all_fields_terminal_including_inaccessible; pending_or_failed_unfinished",
        "research_coverage": researched / manifest.total_count if manifest.total_count else None,
        "verified_fields": totals["verified"], "attempted_fields": sum(totals.values()) - totals["pending"],
        "field_statuses": totals, "fields": by_field,
        "missing_company_ids": [entry["id"] for entry in manifest.company_versions if entry["id"] not in current_ids]}


def research_report(user, manifest_id):
    return coverage_report(manifest_for(user, manifest_id))


def record_batch(job_id, worker_id, fence, results):
    """Publish at most 200 field outcomes atomically with task checkpoints.

    A worker applying facts must call both the fact service and this function
    inside the same outer ``leased_job`` context. A duplicate completed item is
    accepted only when the complete outcome is identical.
    """
    if not isinstance(results, list) or not 1 <= len(results) <= 200:
        raise BaichuanError("invalid_request", "研究批次须为 1 至 200 项。")
    with leased_job(job_id, worker_id, fence) as job:
        if job.kind != "research":
            raise BaichuanError("invalid_request", "此任务不是全库研究任务。")
        try:
            manifest = BaichuanResearchManifest.objects.select_related("job").get(pk=job.payload.get("manifest_id"),
                owner=job.owner, scope=job.scope)
        except (BaichuanResearchManifest.DoesNotExist, ValueError, TypeError, ValidationError):
            raise BaichuanError("invalid_request", "任务没有有效固定清单。") from None
        ancestor = job
        while ancestor.pk != manifest.job_id and ancestor.parent_job_id:
            ancestor = ancestor.parent_job
        if ancestor.pk != manifest.job_id:
            raise BaichuanError("invalid_request", "任务不属于此研究清单的执行链。")
        keys = []
        for raw in results:
            result = _object(raw, 16000)
            if (set(result) - {"company_id", "field", "status", "reason", "evidence_id", "checkpoint"}
                    or result.get("status") not in RESULT_STATUSES or result.get("field") not in manifest.fields
                    or not isinstance(result.get("reason", ""), str)):
                raise BaichuanError("invalid_request", "研究工作项内容无效。")
            try:
                item = manifest.items.select_related("company").get(company_id=result.get("company_id"), field=result["field"])
            except (BaichuanResearchItem.DoesNotExist, ValueError, TypeError, ValidationError):
                raise BaichuanError("invalid_request", "研究工作项不在固定清单内。") from None
            if item.status != "pending":
                retry_failed = item.status == "failed" and job.parent_job_id and item.checkpoint.get("job_id") != str(job.pk)
                if not retry_failed and item.checkpoint.get("outcome") != result:
                    raise BaichuanError("research_item_conflict", "已完成研究工作项不能改写。", 409)
                if not retry_failed:
                    continue
            evidence = None
            if result.get("evidence_id"):
                try:
                    evidence = BaichuanEvidence.objects.get(pk=result["evidence_id"], scope=job.scope)
                except (BaichuanEvidence.DoesNotExist, ValueError, TypeError, ValidationError):
                    raise BaichuanError("invalid_request", "研究依据不存在或不属于本部署。") from None
            if result["status"] == "verified":
                if not evidence_is_valid(evidence, item.company, certificate=item.field == "qualifications", scope=job.scope):
                    raise BaichuanError("invalid_evidence", "缺少有效正文、主体与定位，不能标记已核实。")
            if result["status"] != "verified" and not result.get("reason", "").strip():
                raise BaichuanError("invalid_request", "未核实字段必须记录具体原因。")
            item.status = result["status"]
            item.verification_status = "verified" if item.status == "verified" else "conflict" if item.status == "conflict" else "inaccessible" if item.status == "inaccessible" else "unverified"
            item.evidence = evidence
            item.reason = result.get("reason", "")
            item.attempts += 1
            previous_attempts = item.checkpoint.get("previous_attempts", [])
            if item.checkpoint.get("outcome"):
                previous_attempts = [*previous_attempts, {"job_id": item.checkpoint.get("job_id"), "outcome": item.checkpoint["outcome"]}]
            item.checkpoint = {"outcome": result, "job_id": str(job.pk), "previous_attempts": previous_attempts,
                "baseline_version": item.company_version,
                "observed_version": item.company.version, "company_changed": item.company.version != item.company_version}
            item.save()
            key = f"{item.company_id}:{item.field}"
            keys.append(key)
            job_item, _ = BaichuanJobItem.objects.get_or_create(job=job, item_key=key, defaults={"company": item.company})
            job_item.status, job_item.stage = "completed", "researching"
            job_item.attempts += 1
            job_item.result, job_item.checkpoint = result, item.checkpoint
            job_item.save()
        report = coverage_report(manifest)
        job.counts = {**job.counts, **{key: report[key] for key in
            ("total_companies", "total_fields", "researched_companies", "attempted_companies",
             "completed_company_attempts", "verified_fields", "attempted_fields")}}
        job.stage = "researching"
        job.checkpoint = {"manifest_id": str(manifest.pk), "last_items": keys}
        job.result_ref = {"manifest_id": str(manifest.pk)}
        if report["field_statuses"]["pending"] == 0:
            job.status = "partial" if report["field_statuses"]["failed"] else "completed"
            job.finished_at, job.lease_owner, job.lease_expires_at = timezone.now(), "", None
        job.save()
        report["state"] = job.status
        return report
