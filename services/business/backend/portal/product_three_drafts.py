"""Persist independent report drafts and derive an editable presentation."""

from pathlib import Path

from django.db import transaction
from django.db.models import Max

from .product_documents import content_document, render_report_draft
from .product_models import DocumentArtifact
from .product_pair import pair_snapshot, save_report_content
from .product_service import ProductError, blueprint_chapters, digest
from .product_storage import verified_artifact
from .product_steps import run_step
from .product_delivery import record_artifact_delivery, finish_output_delivery


def _rendered_result_current(result, document=None):
    from .product_storage import resolve_relative, StorageError
    import hashlib
    import json
    try:
        def verified(path, expected):
            candidate = resolve_relative(path)
            return candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == expected
        target = resolve_relative(result["path"])
        valid = verified(result["path"], result["sha256"])
        if "content_path" in result:
            content = resolve_relative(result["content_path"])
            valid = valid and verified(result["content_path"], result["content_sha256"])
            if not valid:
                return False
            document = json.loads(content.read_bytes())
        if document:
            expected = {item["id"]: item["image_sha256"] for item in
                        result.get("render_evidence", {}).get("diagram_generation", {}).get("figures", [])}
            for block in document.get("blocks", []):
                if block.get("type") == "figure":
                    image = target.parent / block["path"]
                    if not image.resolve().is_relative_to(target.parent.resolve()):
                        return False
                    relative = str(Path(result["path"]).parent / block["path"])
                    valid = valid and verified(relative, expected[block["id"]])
        def evidence_current(value):
            if isinstance(value, dict):
                if "path" in value and "sha256" in value and not verified(value["path"], value["sha256"]):
                    return False
                return all(evidence_current(item) for item in value.values())
            if isinstance(value, list):
                return all(evidence_current(item) for item in value)
            return True
        valid = valid and evidence_current(result.get("render_evidence", {}))
        return valid
    except (StorageError, OSError, KeyError, TypeError, ValueError):
        return False


def _rendered_content(result, original):
    import hashlib
    import json
    from .product_storage import resolve_relative
    if "content_path" not in result:
        return original
    raw = resolve_relative(result["content_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != result.get("content_sha256"):
        raise ProductError("artifact_hash_mismatch", "报告正文缓存已变化，请重新生成。", 409)
    content = json.loads(raw)
    if not isinstance(content, dict):
        raise ProductError("artifact_hash_mismatch", "报告正文缓存无效，请重新生成。", 409)
    return content


def generate_report_drafts(task, fence, attempt_id, input_revision, blueprint, *, families=None):
    from django.conf import settings
    from .product_documents import preflight_document_rendering
    from .product_worker import (_analysis_progress, _chapter_character_count, _content_quality_guard, _family_target, _formal_content_guard,
                                 _generate_diagrams, _diagram_progress, _guard, _minimum_characters,
                                 _record_output_generation, _renew, _ensure_content_review, _content_review_current, _store, current_chapters)
    from .product_pair import _report_generation_hash

    artifacts = []
    draft = task.pending_action in {"generate_outputs", "three_drafts"}
    repair_diagrams = task.checkpoint.get("repair_pending_diagrams") is True
    for family in (families if families is not None else ("technical-solution", "feasibility")):
        if family not in task.checkpoint.get("output_families", ["technical-solution", "feasibility", "presentation"]):
            continue
        phase = 'render_technical' if family == 'technical-solution' else 'render_feasibility'
        label = '技术方案' if family == 'technical-solution' else '可行性研究报告'
        chapters = current_chapters(task, input_revision.sha256, blueprint.sha256, family)
        ordered = [chapters.get(chapter["id"]) for chapter in blueprint_chapters(blueprint.payload, family)]
        if any(chapter is None for chapter in ordered):
            raise ProductError("chapters_incomplete", f"{family} 报告内容不完整。", 409)
        target = _family_target(family)
        actual = _chapter_character_count(ordered)
        _content_quality_guard(ordered, input_revision.payload, blueprint.payload, draft=draft)
        _formal_content_guard(ordered, family, draft=draft)
        _record_output_generation(task.pk, fence, family, target, actual)
        if not draft and settings.PRODUCT_ENFORCE_OUTPUT_LENGTH and actual < _minimum_characters(target):
            raise ProductError("output_length_below_target", f"{label}正文尚未达到{target}字下限，请续写后再生成文件。", 409)
        _renew(task.pk, fence)
        review = _ensure_content_review(task, fence, attempt_id, input_revision, blueprint, ordered, family)
        content = content_document(task, input_revision, blueprint, ordered, family, draft=draft,
                                   review_issues=review.payload.get("issues", []))
        report_hash = _report_generation_hash(task, family, input_revision, blueprint)
        runtime_hash = digest(preflight_document_rendering(draft=draft))
        existing = DocumentArtifact.objects.filter(task=task, generation_hash=report_hash).first()
        if existing:
            if (existing.review_id != review.pk
                    or not _content_review_current(task, existing.review, input_revision, blueprint, ordered)):
                raise ProductError("stale_report_review", "报告文件的复核依据已变化，请重新生成。", 409)
            report = task.revisions.filter(pk=existing.render_evidence.get("report_id")).first()
            if (not (repair_diagrams and existing.render_evidence.get("diagram_generation", {}).get("pending_count"))
                    and existing.render_evidence.get("render_runtime_hash", runtime_hash) == runtime_hash
                    and _rendered_result_current({"path": existing.path, "sha256": existing.sha256,
                                        "render_evidence": existing.render_evidence}, report.payload if report else None)):
                verified_artifact(existing)
                record_artifact_delivery(existing)
                artifacts.append(existing)
                _analysis_progress(task.pk, fence, phase, 'completed', detail=f'{label}已保存，复用已核验的文件版本')
                continue
            if not repair_diagrams:
                with transaction.atomic():
                    _guard(task.pk, fence)
                    DocumentArtifact.objects.filter(pk=existing.pk).update(generation_hash="")
        def render_current(result):
            return (not (repair_diagrams and result.get("render_evidence", {}).get("diagram_generation", {}).get("pending_count"))
                    and _rendered_result_current(result))
        try:
            generated = run_step(task.pk, fence, f"render:{family}", {"report_hash": report_hash, "runtime_hash": runtime_hash},
                lambda: render_report_draft(task, input_revision, blueprint, ordered, family, draft=draft, document=content,
                    workspace_key=digest({"family": family, "input": input_revision.sha256,
                        "blueprint": blueprint.sha256, "chapters": [chapter.sha256 for chapter in ordered]}),
                    diagram_generator=lambda document: _generate_diagrams(task.pk, fence, attempt_id, document, draft=draft),
                    diagram_progress=lambda status, **details: _diagram_progress(task.pk, fence, family, status, **details),
                    diagram_step=lambda key, binding, operation, validate: run_step(task.pk, fence, key,
                        binding, operation, validate=validate)),
                validate=render_current)
        except Exception as error:
            from .product_steps import StepRetryPending
            waiting = isinstance(error, StepRetryPending)
            _analysis_progress(task.pk, fence, phase, 'waiting' if waiting else 'failed',
                               detail=f'{label}等待自动恢复' if waiting else f'{label}文件生成失败')
            raise
        content = _rendered_content(generated, content)
        diagram_review = generated["render_evidence"].get("diagram_generation", {})
        with transaction.atomic():
            fresh = _guard(task.pk, fence)
            # Keep the previous downloadable draft current until its replacement
            # review, report and artifact can all be committed together.
            if diagram_review.get("quality_issue_count") or (review.payload.get("diagram_review")
                                                           and review.payload["diagram_review"] != diagram_review):
                review = _store(task.pk, fence, "review", {**review.payload, "passed": False,
                    "full_document_human_review_required": True, "diagram_review": diagram_review},
                    input_revision.sha256, blueprint.sha256, family=family)
                report_hash = _report_generation_hash(task, family, input_revision, blueprint)
            if repair_diagrams and existing:
                DocumentArtifact.objects.filter(pk=existing.pk).update(generation_hash="")
            report = save_report_content(fresh, family, content, input_hash=input_revision.sha256,
                                         blueprint_hash=blueprint.sha256, actor=fresh.owner)
            version = (fresh.artifacts.aggregate(value=Max("version"))["value"] or 0) + 1
            artifact = DocumentArtifact.objects.create(
                task=fresh, family=family, version=version, path=generated["path"], sha256=generated["sha256"],
                review=review,
                input_hash=input_revision.sha256, blueprint_hash=blueprint.sha256,
                template_hash=generated["template_hash"], generation_hash=report_hash,
                render_evidence={**generated["render_evidence"], "report_id": str(report.pk), "kind": "draft", "render_runtime_hash": runtime_hash,
                                 "draft_quality": review.payload.get("draft_quality", {}),
                                 "content_review": "human_review_required" if review.payload.get("full_document_human_review_required") else "reviewed",
                                 "attempt_id": str(attempt_id)},
            )
            artifacts.append(artifact)
            record_artifact_delivery(artifact)
        _analysis_progress(task.pk, fence, phase, 'completed', detail=f'{label}文件已保存，可下载')
    return artifacts


def generate_presentation_artifact(task, fence, attempt_id, input_revision, blueprint):
    from .product_presentation import presentation_renderer_hash, render_presentation_draft
    from .product_worker import _analysis_progress, _guard, _renew

    _renew(task.pk, fence)
    _analysis_progress(task.pk, fence, 'presentation', 'running', detail='正在根据两份报告制作汇报PPT')
    pair = pair_snapshot(task)
    planning = {"presentation_style": task.checkpoint.get("presentation_style", "auto"), "audience": blueprint.payload.get("audience", ""),
                "purpose": blueprint.payload.get("purpose", ""),
                "requirements": input_revision.payload.get("requirements", "")}
    generation_hash = digest({"kind": "presentation", "pair": pair["sha256"], "title": task.title,
                              "renderer": presentation_renderer_hash(), "planning": planning})
    existing = DocumentArtifact.objects.filter(task=task, generation_hash=generation_hash).first()
    latest = task.artifacts.filter(family="presentation").order_by("-version").first()
    if existing and latest and existing.pk == latest.pk and _rendered_result_current({"path": existing.path, "sha256": existing.sha256,
                                             "render_evidence": existing.render_evidence}):
        verified_artifact(existing)
        record_artifact_delivery(existing)
        _presentation_progress(task.pk, fence, existing.render_evidence.get("presentation_plan"), "completed")
        _analysis_progress(task.pk, fence, 'presentation', 'completed', detail='汇报PPT已保存，复用已核验的文件版本')
        return existing
    if existing:
        with transaction.atomic():
            _guard(task.pk, fence)
            DocumentArtifact.objects.filter(pk=existing.pk).update(generation_hash="")
    generated = run_step(task.pk, fence, "render:presentation", {"generation_hash": generation_hash},
                         lambda: render_presentation_draft(task, pair, **planning,
                             progress=lambda event: _presentation_progress(task.pk, fence, event["plan"], "running", event)),
                         validate=_rendered_result_current)
    with transaction.atomic():
        fresh = _guard(task.pk, fence)
        if pair_snapshot(fresh)["sha256"] != pair["sha256"]:
            raise ProductError("stale_pair", "报告来源已变化。", 409)
        version = (fresh.artifacts.aggregate(value=Max("version"))["value"] or 0) + 1
        artifact = DocumentArtifact.objects.create(
            task=fresh, family="presentation", version=version, path=generated["path"],
            sha256=generated["sha256"], input_hash=input_revision.sha256,
            blueprint_hash=blueprint.sha256, template_hash=generated["template_hash"],
            generation_hash=generation_hash,
            render_evidence={**generated["render_evidence"], "attempt_id": str(attempt_id)},
        )
        record_artifact_delivery(artifact)
    _presentation_progress(task.pk, fence, generated["render_evidence"].get("presentation_plan"), "completed")
    _analysis_progress(task.pk, fence, 'presentation', 'completed', detail='汇报PPT已保存，可下载')
    return artifact


def _presentation_progress(task_id, fence, plan, status, event=None):
    from .product_worker import _analysis_progress, _guard
    from .product_release import public_presentation_plan

    if not plan:
        return
    with transaction.atomic():
        fresh = _guard(task_id, fence)
        fresh.checkpoint = {**fresh.checkpoint, "presentation_plan": public_presentation_plan(plan)}
        fresh.save(update_fields=["checkpoint", "updated_at"])
    labels = {"planning": "已自动确定风格和汇报大纲", "rendering": "正在制作幻灯片",
              "repairing": "正在调整页面排版", "validating": "正在检查并保存 PPT"}
    stage = event["stage"] if event else "completed"
    total = len(plan["pages"])
    _analysis_progress(task_id, fence, "presentation", status, stage=stage,
        completed_count=event["completed_count"] if event else total, total_count=total,
        detail=labels.get(stage, "汇报 PPT 已保存，可下载"))


def generate_three_drafts(task, fence, attempt_id, input_revision, blueprint):
    generate_report_drafts(task, fence, attempt_id, input_revision, blueprint)
    return finish_output_delivery(task, fence, attempt_id, families=[family for family in
        task.checkpoint.get("output_families", ["technical-solution", "feasibility"])
        if family in {"technical-solution", "feasibility"}])


def generate_presentation(task, fence, attempt_id, input_revision, blueprint):
    generate_presentation_artifact(task, fence, attempt_id, input_revision, blueprint)
    return finish_output_delivery(task, fence, attempt_id, families=["presentation"])
