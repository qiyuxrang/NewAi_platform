"""Task-authorized endpoints for independent review-only outputs."""

import re
import hashlib
from io import BytesIO

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .product_api import product_endpoint, _artifact_download_response, _body, _expected, _task_detail
from .product_models import DocumentArtifact, DocumentRevision
from .product_pair import FAMILIES, latest_report_content, output_current
from .product_delivery import artifact_delivery
from .product_service import (ProductError, approved_blueprint, blueprint_chapters, current_revision, effective_artifact_approval, input_authorized,
                              require_owner, require_version, task_for, source_ids_belong, validate_chapter, append_revision)
from .product_storage import StorageError, verified_artifact
from .product_release import evidence_file, public_quality_warnings, public_presentation_plan
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
        delivery = artifact_delivery(artifact, current=current)
        delivered = delivery["delivered"]
        result.append({"id": str(artifact.pk), "family": artifact.family, "version": artifact.version,
                       "sha256": artifact.sha256, "current": current, "stale": not current,
                       "draft": not approved and not delivered, "approved": approved, "delivered": delivered,
                       "delivery_decision": delivery,
                       "presentation_plan": public_presentation_plan(artifact.render_evidence.get("presentation_plan")),
                       "review_status": "stale" if not current else "approved" if approved else "delivered" if delivered else "pending_review",
                       "engine": artifact.render_evidence.get("engine", "frozen-word"),
                       "content_version": report.version if report else None,
                       "content_sha256": report.sha256 if report else None,
                       "content_approved": False if report else None,
                       "quality_warnings": public_quality_warnings(artifact.render_evidence,
                           artifact.review.payload.get("issues", []) if artifact.review else []),
                       **public_draft_preview(artifact, current=current),
                       "source_versions": artifact.render_evidence.get("source_versions", [])})
    return Response({"task_version": task.version, "outputs": result})


@api_view(["GET"])
@product_endpoint
def saved_draft_download(request, task_id):
    """Export only saved text bound to the currently authorized approved plan."""
    task = task_for(request.user, task_id)
    family = request.query_params.get("family")
    if family not in FAMILIES:
        raise ProductError("invalid_family", "请选择技术方案或可研报告正文。")
    current = task.revisions.filter(kind=DocumentRevision.Kind.INPUT, version=task.input_version).first()
    if not input_authorized(task, current):
        raise ProductError("source_permission_changed", "来源授权已变化。", 404)
    blueprint = approved_blueprint(task)
    if blueprint is None:
        raise ProductError("blueprint_approval_required", "当前蓝图尚未批准，不能导出正文。", 409)
    for key, actual in (("input_version", task.input_version), ("blueprint_version", task.blueprint_version)):
        expected = request.query_params.get(key)
        if expected is not None:
            if not expected.isascii() or not expected.isdigit() or len(expected) > 10:
                raise ProductError("invalid_version", "正文版本参数无效。")
            if int(expected) != actual:
                raise ProductError("stale_draft", "输入或蓝图版本已变化，请刷新后重新下载。", 409)
    latest = {}
    for chapter in task.revisions.filter(kind=DocumentRevision.Kind.CHAPTER, family=family,
                                         input_hash=current.sha256, blueprint_hash=blueprint.sha256).order_by("version"):
        latest[chapter.payload.get("chapter_id")] = chapter
    saved, missing = [], []
    for spec in blueprint_chapters(blueprint.payload, family):
        chapter = latest.get(spec["id"])
        if chapter is not None:
            try:
                payload = validate_chapter(chapter.payload)
            except ProductError:
                payload = None
            if (payload and payload["title"] == spec["title"]
                    and source_ids_belong(task, payload["source_ids"])
                    and set(payload["source_ids"]) <= set(spec["source_ids"])):
                saved.append(chapter)
                continue
        missing.append(spec["title"])
    if not saved:
        raise ProductError("saved_draft_unavailable", "当前输入与已批准蓝图尚无可下载的已保存章节。", 409)
    name = "技术方案" if family == "technical-solution" else "可行性研究报告"
    characters = sum(len(re.sub(r"\s", "", paragraph)) for chapter in saved for paragraph in chapter.payload["paragraphs"])
    lines = [f"{task.title} · {name} · 已保存正文草稿", "【草稿：正文快照 / 未包含完整图文排版】",
             "本文件仅为已保存正文快照；正式交付状态请在成果工作区查看。",
             f"输入版本：{task.input_version}；已批准蓝图版本：{task.blueprint_version}",
             f"导出时间：{timezone.localtime().isoformat()}",
             f"已保存章节：{len(saved)} / {len(blueprint_chapters(blueprint.payload, family))}；非空白字数：{characters}",
             "未完成章节：" + ("；".join(missing) if missing else "无缺章；整体生成与篇幅要求仍以后台记录为准"),
             "本 TXT 草稿未包含配图和文档排版；完整有效的 Word 成果生成后直接交付，无需再次审批。", ""]
    for chapter in saved:
        lines.extend([chapter.payload["title"], "", *chapter.payload["paragraphs"], ""])
    # Check again before releasing bytes: a permission or plan change cannot
    # turn a historical chapter into an export of the current plan.
    checked = task_for(request.user, task_id)
    checked_input = checked.revisions.filter(kind=DocumentRevision.Kind.INPUT, version=checked.input_version).first()
    checked_blueprint = approved_blueprint(checked)
    if not input_authorized(checked, checked_input):
        raise ProductError("source_permission_changed", "来源授权已变化。", 404)
    if (not checked_blueprint or checked_input.sha256 != current.sha256
            or checked_blueprint.sha256 != blueprint.sha256
            or checked.input_version != task.input_version or checked.blueprint_version != task.blueprint_version):
        raise ProductError("stale_draft", "输入或蓝图版本已变化，请刷新后重新下载。", 409)
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", task.title).strip(" .") or "报告"
    response = FileResponse(BytesIO("\n".join(lines).encode("utf-8-sig")), as_attachment=True,
                            filename=f"已保存正文草稿-{title}-{name}.txt", content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    audit(request.user, "product_saved_draft_download", f"{task.pk}:v{task.version}:{family}:{len(saved)}")
    return response


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
    prefix = "成果" if artifact_delivery(artifact, current=current)["delivered"] else "草稿" if current else "历史草稿-已过期"
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
        spec = next((chapter for chapter in blueprint_chapters(blueprint.payload, "feasibility") if chapter["id"] == payload["chapter_id"]), None)
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
               path("tasks/<uuid:task_id>/saved-draft/download/", saved_draft_download),
               path("tasks/<uuid:task_id>/report-chapters/", report_chapter),
               path("outputs/<uuid:artifact_id>/download/", draft_download),
               path("outputs/<uuid:artifact_id>/preview/", draft_preview)]
