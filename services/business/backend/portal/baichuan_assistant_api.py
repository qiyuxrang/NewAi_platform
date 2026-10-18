from pathlib import Path
from urllib.parse import urlsplit
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .baichuan_api import endpoint
from .baichuan_assistant_models import BaichuanConversation, BaichuanMatchSnapshot, BaichuanEvidence
from .baichuan_assistant_service import (attachment_data, conversation_for, job_data, message_data,
    require_assistant, scope, store_attachment, submit_message)
from .baichuan_jobs import cancel_job, job_for, retry_job
from .baichuan_service import BaichuanError, require_access


@api_view(["GET"])
@endpoint
def config(request):
    require_access(request.user)
    from .product_web_search import configuration
    from .product_service import ProductError
    from .model_config import ModelRoute
    from .baichuan_exports import export_available
    try:
        configuration()
        search = True
    except ProductError:
        search = False
    # Configuration is only a readiness hint, not a claimed successful model call.
    route = ModelRoute.objects.filter(code=settings.BAICHUAN_ASSISTANT_MODEL_ROUTE, enabled=True).exists()
    return Response({"enabled": settings.BAICHUAN_ASSISTANT_ENABLED, "owner_id": request.user.pk,
        "scope": scope(), "environment_label": settings.BAICHUAN_ENVIRONMENT_LABEL,
        "capabilities": {"answer_stream": True, "model": bool(settings.MODEL_GATEWAY_URL and route), "search": search,
            "parser": Path(settings.PRODUCT_PARSER_PYTHON).is_file(), "export": export_available()},
        "limits": {"file_bytes": 20 * 1024 * 1024, "files": 3, "pdf_pages": 100, "ocr_pages": 12}})


@api_view(["POST"])
@endpoint
def conversations(request):
    require_assistant(request.user)
    row = BaichuanConversation.objects.create(owner=request.user, scope=scope())
    return Response({"id": str(row.pk), "condition_revision": 0}, status=201)


@api_view(["GET"])
@endpoint
def conversation(request, conversation_id):
    row = conversation_for(request.user, conversation_id)
    recent_messages = list(row.messages.order_by("-created_at", "-id")[:201])
    recent_attachments = list(row.attachments.order_by("-created_at", "-id")[:101])
    return Response({"id": str(row.pk), "condition_revision": row.condition_revision,
        "messages": [message_data(m) for m in reversed(recent_messages[:200])],
        "attachments": [attachment_data(a) for a in reversed(recent_attachments[:100])],
        "has_older_messages": len(recent_messages) > 200,
        "has_older_attachments": len(recent_attachments) > 100,
        "jobs": [job_data(j) for j in row.jobs.order_by("-created_at")[:100]],
        "snapshots": [{"id": str(s.pk), "condition_revision": s.condition_revision,
            "result_revision": s.result_revision, "counts": s.counts} for s in row.snapshots.only(
                "id", "condition_revision", "result_revision", "counts").order_by("-created_at")[:100]]})


@api_view(["POST"])
@endpoint
def messages(request, conversation_id):
    message, job, created = submit_message(request.user, conversation_id, request.data)
    return Response({"message": message_data(message), "job": job_data(job)}, status=202 if created else 200)


@api_view(["POST"])
@endpoint
def attachments(request, conversation_id):
    if len(request.FILES) != 1 or "file" not in request.FILES:
        raise BaichuanError("invalid_request", "每次上传一个 PDF 或 DOCX 附件。")
    row = store_attachment(request.user, conversation_id, request.FILES["file"])
    return Response(attachment_data(row), status=201)


@api_view(["GET"])
@endpoint
def job(request, job_id):
    require_assistant(request.user)
    return Response(job_data(job_for(request.user, job_id)))


@api_view(["POST"])
@endpoint
def job_stream(request, job_id):
    from .baichuan_stream import events, observed_job
    require_assistant(request.user)
    if not isinstance(request.data, dict) or request.data:
        raise BaichuanError("invalid_request", "流式观察不接受任务或模型参数。")
    session_key = getattr(getattr(request, 'session', None), 'session_key', None)
    observed_job(request.user, job_id, session_key)
    return StreamingHttpResponse(events(request.user, job_id, session_key),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"})


@api_view(["POST"])
@endpoint
def cancel(request, job_id):
    require_assistant(request.user)
    return Response(job_data(cancel_job(request.user, job_id)))


@api_view(["POST"])
@endpoint
def retry(request, job_id):
    require_assistant(request.user)
    if not isinstance(request.data, dict):
        raise BaichuanError("invalid_request", "重试参数无效。")
    job, _ = retry_job(request.user, job_id, idempotency_key=request.data.get("client_request_id"))
    return Response({"job": job_data(job)}, status=202)


def snapshot_for(user, snapshot_id):
    require_assistant(user)
    try:
        return BaichuanMatchSnapshot.objects.get(pk=snapshot_id, conversation__owner=user,
            conversation__scope=scope(), job__scope=scope(), job__owner=user)
    except (BaichuanMatchSnapshot.DoesNotExist, ValidationError, ValueError, TypeError):
        raise BaichuanError("not_found", "结果不存在或不可访问。", 404) from None


@api_view(["GET"])
@endpoint
def results(request, snapshot_id):
    from .baichuan_exports import public_locator
    snapshot = snapshot_for(request.user, snapshot_id)
    try:
        page, size = int(request.query_params.get("page", 1)), int(request.query_params.get("page_size", 50))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError
    except (ValueError, TypeError):
        raise BaichuanError("invalid_request", "结果页码或每页数量无效。") from None
    # Keep the full immutable match/audit set. The requested output window is
    # applied before paging, so page2 cannot bypass "前10家" with page_size=50.
    limit = snapshot.condition_tree.get("output", {}).get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 5000:
        raise BaichuanError("invalid_result", "结果数量无效，请重新检索。", 409)
    visible = snapshot.results[:limit]
    selected = visible[(page - 1) * size:page * size]
    evidence_ids = set()
    company_ids = {r["company_id"] for r in selected}
    for row in selected:
        for condition in row.get("conditions", []):
            for identifier in condition.get("evidence_ids", []):
                try:
                    evidence_ids.add(uuid.UUID(identifier))
                except (TypeError, ValueError, AttributeError):
                    continue
    sources = {}
    for evidence in BaichuanEvidence.objects.filter(pk__in=evidence_ids, scope=scope()):
        if evidence.subject.get("company_id") not in company_ids:
            continue
        try:
            parsed = urlsplit(evidence.url)
            safe_url = evidence.url if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password else ""
        except ValueError:
            safe_url = ""
        sources[str(evidence.pk)] = {"title": evidence.title or "资料来源", "url": safe_url,
            "excerpt": evidence.excerpt[:1500], "locator": public_locator(evidence.locator),
            "verified_on": evidence.verified_on.isoformat() if evidence.verified_on else None,
            "retrieved_at": evidence.retrieved_at.isoformat()}
    return Response({"id": str(snapshot.pk), "condition_revision": snapshot.condition_revision,
        "result_revision": snapshot.result_revision, "counts": snapshot.counts,
        "conditions": snapshot.condition_tree,
        # Frozen certificate metadata belongs to evidence exports. The existing
        # page does not consume it; retain it in storage without enlarging its
        # response or changing the other result keys.
        "results": [{key: value for key, value in row.items() if key != "certificate_records"} for row in selected],
        "evidence": sources, "page": page, "page_size": size,
        "total": len(visible), "total_available": len(snapshot.results), "output_limit": limit,
        "research_status": snapshot.research_status,
        "fact_cutoff_at": snapshot.fact_cutoff_at.isoformat()})


@api_view(["POST"])
@endpoint
def research_manifests(request):
    from .baichuan_research import create_manifest, research_report
    if not isinstance(request.data, dict) or set(request.data) - {"client_request_id", "fields", "parent_manifest_id"}:
        raise BaichuanError("invalid_request", "研究清单参数无效。")
    manifest, created = create_manifest(request.user, request.data.get("client_request_id"),
        fields=request.data.get("fields"), parent_manifest_id=request.data.get("parent_manifest_id"))
    return Response(research_report(request.user, manifest.pk), status=201 if created else 200)


@api_view(["GET"])
@endpoint
def research_manifest(request, manifest_id):
    from .baichuan_research import research_report
    return Response(research_report(request.user, manifest_id))
