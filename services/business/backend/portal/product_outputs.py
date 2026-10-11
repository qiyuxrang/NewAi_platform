"""Task-authorized endpoints for independent review-only outputs."""

import re
import hashlib

from django.db import transaction
from django.http import FileResponse
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .product_api import product_endpoint, _artifact_download_response, _body, _expected, _task_detail
from .product_models import DocumentArtifact, DocumentRevision
from .product_pair import FAMILIES, latest_report_content, output_current
from .product_service import (ProductError, approved_blueprint, current_revision, effective_artifact_approval, input_authorized,
                              require_owner, require_version, task_for, source_ids_belong, validate_chapter, append_revision)
from .product_storage import StorageError, verified_artifact
from .product_release import evidence_file
from .product_output_preview import draft_preview_evidence, public_draft_preview
from .security import audit


@api_view(["GET"])
@product_endpoint
def outputs(request, task_id):
    task = task_for(request.user, task_id)
    result = []
    for artifact in task.artifacts.order_by("version"):
        if artifact.family not in (*FAMILIES, "presentation"):
            continue
        revision = task.revisions.filter(kind="input", sha256=artifact.input_hash).first()
        if not input_authorized(task, revision):
            continue
        report = task.revisions.filter(pk=artifact.render_evidence.get("report_id"), kind=DocumentRevision.Kind.REPORT).first()
        current = output_current(task, artifact)
        approved = effective_artifact_approval(artifact) is not None
        delivered = bool(current and task.agent_root_id and task.state == "COMPLETED")
        result.append({"id": str(artifact.pk), "family": artifact.family, "version": artifact.version,
                       "sha256": artifact.sha256, "current": current, "stale": not current,
                       "draft": not (approved or delivered), "approved": approved, "delivered": delivered,
                       "review_status": "stale" if not current else "approved" if approved else "delivered" if delivered else "pending_review",
                       "engine": artifact.render_evidence.get("engine", "frozen-word"),
                       "content_version": report.version if report else None,
                       "content_sha256": report.sha256 if report else None,
                       "content_approved": False if report else None,
                       **public_draft_preview(artifact, current=current),
                       "source_versions": artifact.render_evidence.get("source_versions", [])})
    return Response({"task_version": task.version, "outputs": result})


@api_view(["GET"])
@product_endpoint
def draft_download(request, artifact_id):
    try:
        artifact = DocumentArtifact.objects.select_related("task").get(pk=artifact_id)
    except (DocumentArtifact.DoesNotExist, ValueError, TypeError) as error:
        raise ProductError("not_found", "对象不存在。", 404) from error
    if artifact.family == "technical-solution":
        return _artifact_download_response(request, artifact)
    task = task_for(request.user, artifact.task_id)
    if artifact.family not in ("feasibility", "presentation"):
        raise ProductError("not_found", "对象不存在。", 404)
    if not input_authorized(task, task.revisions.filter(kind="input", sha256=artifact.input_hash).first()):
        raise ProductError("source_permission_changed", "来源授权已变化。", 404)
    current = output_current(task, artifact)
    history = request.query_params.get("history") == "1"
    if not current and not history:
        raise ProductError("stale_output", "此成果已过期，仅保留历史记录。", 409)
    try:
        target = verified_artifact(artifact)
    except StorageError as error:
        raise ProductError(error.code, error.detail, 409) from error
    task = task_for(request.user, artifact.task_id)
    if not input_authorized(task, task.revisions.filter(kind="input", sha256=artifact.input_hash).first()):
        raise ProductError("source_permission_changed", "来源授权已变化。", 404)
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", task.title).strip(" .") or "报告"
    prefix = "成果" if current and task.agent_root_id and task.state == "COMPLETED" else "草稿" if current else "历史草稿-已过期"
    response = FileResponse(target.open("rb"), as_attachment=True,
                            filename=f"{prefix}-{title}-{artifact.family}-v{artifact.version}{target.suffix}")
    response["X-Product-Artifact-Current"] = "true" if current else "false"
    response["Cache-Control"] = "no-store"
    audit(request.user, "product_artifact_download", f"{artifact.pk}:v{task.version}:{artifact.family}:{'current' if current else 'history'}:{artifact.sha256}")
    return response


def _preview_authorized(request, artifact):
    task = task_for(request.user, artifact.task_id)
    if artifact.family not in (*FAMILIES, "presentation"):
        raise ProductError("not_found", "对象不存在。", 404)
    if not input_authorized(task, task.revisions.filter(kind="input", sha256=artifact.input_hash).first()):
        raise ProductError("source_permission_changed", "来源授权已变化。", 404)
    if not output_current(task, artifact):
        raise ProductError("stale_output", "此成果已过期，请重新生成后预览。", 409)
    return task


@api_view(["GET"])
@product_endpoint
def draft_preview(request, artifact_id):
    try:
        artifact = DocumentArtifact.objects.select_related("task").get(pk=artifact_id)
    except (DocumentArtifact.DoesNotExist, ValueError, TypeError):
        raise ProductError("not_found", "对象不存在。", 404) from None
    task = _preview_authorized(request, artifact)
    preview = draft_preview_evidence(artifact)
    if preview is None:
        raise ProductError("preview_unavailable", "当前版本缺少可验证预览证据，需生成新的内容版本后预览。", 409)
    page = request.query_params.get("page", "1")
    if (not page.isascii() or not page.isdigit() or len(page) > 6
            or not 1 <= int(page) <= preview["page_count"]):
        raise ProductError("invalid_page", "页面编号无效。")
    record = preview["pages"][int(page) - 1]
    stream = None
    try:
        verified_artifact(artifact)
        evidence_file(preview["pdf"])
        target = evidence_file(record)
        # Keep the checked file descriptor, so replacing a path after hashing
        # cannot substitute different bytes into this response.
        stream = target.open("rb")
        checksum = hashlib.sha256()
        signature = stream.read(8)
        checksum.update(signature)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
        if signature != b"\x89PNG\r\n\x1a\n" or checksum.hexdigest() != record["sha256"]:
            raise StorageError("artifact_hash_mismatch", "预览页面完整性校验失败。")
        stream.seek(0)
        # Disk I/O must not preserve permissions, versions or evidence that were
        # revoked/changed while the files were checked.
        artifact = DocumentArtifact.objects.select_related("task").get(pk=artifact_id)
        task = _preview_authorized(request, artifact)
        if draft_preview_evidence(artifact) != preview:
            raise ProductError("stale_evidence", "预览证据已变化，请刷新后重试。", 409)
        audit(request.user, "product_draft_page_preview",
              f"{artifact.pk}:v{task.version}:{artifact.family}:{artifact.sha256}:p{page}:{record['sha256']}")
        response = FileResponse(stream, content_type="image/png")
        stream = None
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Product-Artifact-Sha256"] = artifact.sha256
        response["X-Product-Page-Sha256"] = record["sha256"]
        return response
    except (StorageError, OSError) as error:
        if isinstance(error, StorageError):
            raise ProductError(error.code, error.detail, 409) from None
        raise ProductError("preview_unavailable", "当前草稿预览文件不可读取，请重新生成。", 409) from None
    except DocumentArtifact.DoesNotExist:
        raise ProductError("not_found", "对象不存在。", 404) from None
    finally:
        if stream is not None:
            stream.close()


@api_view(["POST"])
@product_endpoint
def report_chapter(request, task_id):
    body = _body(request, {"expected_version", "family", "chapter_id", "title", "paragraphs", "source_ids"})
    if body["family"] != "feasibility":
        raise ProductError("invalid_family", "请使用独立的可研报告章节。")
    with transaction.atomic():
        task = task_for(request.user, task_id, write=True)
        require_owner(task, request.user)
        require_version(task, _expected(body["expected_version"]))
        if task.state in {"QUEUED", "RUNNING", "CANCELLED", "COMPLETED"}:
            raise ProductError("invalid_state", "任务当前不可修改。", 409)
        blueprint = approved_blueprint(task)
        if blueprint is None:
            raise ProductError("blueprint_approval_required", "蓝图尚未批准。", 409)
        payload = validate_chapter({key: body[key] for key in ("chapter_id", "title", "paragraphs", "source_ids")})
        spec = next((chapter for chapter in blueprint.payload["chapters"] if chapter["id"] == payload["chapter_id"]), None)
        if not spec or spec["title"] != payload["title"] or not source_ids_belong(task, payload["source_ids"]) or not set(payload["source_ids"]) <= set(spec["source_ids"]):
            raise ProductError("invalid_chapter", "章节或来源超出已批准蓝图。", 409)
        current = current_revision(task, "input")
        record = append_revision(task, "chapter", payload, input_hash=current.sha256, blueprint_hash=blueprint.sha256,
                                 actor=request.user, family="feasibility", reason="manual_chapter_edit")
        task.version += 1
        task.save(update_fields=["version", "updated_at"])
    audit(request.user, "product_chapter_create", f"{record.pk}:v{task.version}")
    return Response({"task": _task_detail(task, request.user)}, status=201)


urlpatterns = [path("tasks/<uuid:task_id>/outputs/", outputs),
               path("tasks/<uuid:task_id>/report-chapters/", report_chapter),
               path("outputs/<uuid:artifact_id>/download/", draft_download),
               path("outputs/<uuid:artifact_id>/preview/", draft_preview)]
