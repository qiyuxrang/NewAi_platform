"""Persist independent report drafts and derive an editable presentation."""

from django.db import transaction
from django.db.models import Max

from .product_documents import content_document, render_report_draft
from .product_models import DocumentArtifact
from .product_pair import pair_snapshot, save_report_content
from .product_service import ProductError, digest
from .product_storage import verified_artifact


def generate_report_drafts(task, fence, attempt_id, input_revision, blueprint):
    from django.conf import settings
    from .product_worker import (_analysis_progress, _chapter_character_count, _family_target, _formal_content_guard,
                                 _generate_diagrams, _diagram_progress, _guard, _minimum_characters,
                                 _record_output_generation, _renew, current_chapters)
    from .product_pair import _report_generation_hash

    artifacts = []
    for family in ("technical-solution", "feasibility"):
        if family not in task.checkpoint.get("output_families", ["technical-solution", "feasibility", "presentation"]):
            continue
        phase = 'render_technical' if family == 'technical-solution' else 'render_feasibility'
        label = '技术方案' if family == 'technical-solution' else '可行性研究报告'
        chapters = current_chapters(task, input_revision.sha256, blueprint.sha256, family)
        ordered = [chapters.get(chapter["id"]) for chapter in blueprint.payload["chapters"]]
        if any(chapter is None for chapter in ordered):
            raise ProductError("chapters_incomplete", f"{family} 报告内容不完整。", 409)
        target = _family_target(family)
        actual = _chapter_character_count(ordered)
        _formal_content_guard(ordered, family)
        _record_output_generation(task.pk, fence, family, target, actual)
        if settings.PRODUCT_ENFORCE_OUTPUT_LENGTH and actual < _minimum_characters(target):
            raise ProductError("output_length_below_target", f"{label}正文尚未达到{target}字下限，请续写后再生成文件。", 409)
        _renew(task.pk, fence)
        content = content_document(task, input_revision, blueprint, ordered, family)
        report_hash = _report_generation_hash(task, family, input_revision, blueprint)
        existing = DocumentArtifact.objects.filter(task=task, generation_hash=report_hash).first()
        if existing:
            verified_artifact(existing)
            artifacts.append(existing)
            _analysis_progress(task.pk, fence, phase, 'completed', detail=f'{label}已保存，复用已核验的文件版本')
            continue
        try:
            generated = render_report_draft(task, input_revision, blueprint, ordered, family, document=content,
                                            diagram_generator=lambda document: _generate_diagrams(task.pk, fence, attempt_id, document),
                                            diagram_progress=lambda status, **details: _diagram_progress(task.pk, fence, family, status, **details))
        except Exception:
            _analysis_progress(task.pk, fence, phase, 'failed', detail=f'{label}文件生成失败')
            raise
        with transaction.atomic():
            fresh = _guard(task.pk, fence)
            report = save_report_content(fresh, family, content, input_hash=input_revision.sha256,
                                         blueprint_hash=blueprint.sha256, actor=fresh.owner)
            version = (fresh.artifacts.aggregate(value=Max("version"))["value"] or 0) + 1
            artifact = DocumentArtifact.objects.create(
                task=fresh, family=family, version=version, path=generated["path"], sha256=generated["sha256"],
                input_hash=input_revision.sha256, blueprint_hash=blueprint.sha256,
                template_hash=generated["template_hash"], generation_hash=report_hash,
                render_evidence={**generated["render_evidence"], "report_id": str(report.pk), "kind": "draft",
                                 "attempt_id": str(attempt_id)},
            )
            artifacts.append(artifact)
        _analysis_progress(task.pk, fence, phase, 'completed', detail=f'{label}文件已保存，可下载')
    return artifacts


def generate_presentation_artifact(task, fence, attempt_id, input_revision, blueprint):
    from .product_presentation import presentation_renderer_hash, render_presentation_draft
    from .product_worker import _analysis_progress, _guard, _renew

    _renew(task.pk, fence)
    _analysis_progress(task.pk, fence, 'presentation', 'running', detail='正在根据两份报告制作汇报PPT')
    pair = pair_snapshot(task)
    generation_hash = digest({"kind": "presentation", "pair": pair["sha256"], "title": task.title,
                              "renderer": presentation_renderer_hash()})
    existing = DocumentArtifact.objects.filter(task=task, generation_hash=generation_hash).first()
    if existing:
        verified_artifact(existing)
        _analysis_progress(task.pk, fence, 'presentation', 'completed', detail='汇报PPT已保存，复用已核验的文件版本')
        return existing
    generated = render_presentation_draft(task, pair)
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
    _analysis_progress(task.pk, fence, 'presentation', 'completed', detail='汇报PPT已保存，可下载')
    return artifact


def generate_three_drafts(task, fence, attempt_id, input_revision, blueprint):
    from .product_worker import _finish

    generate_report_drafts(task, fence, attempt_id, input_revision, blueprint)
    return _finish(task.pk, fence, attempt_id, "WAITING_REVIEW", "FINAL_REVIEW")


def generate_presentation(task, fence, attempt_id, input_revision, blueprint):
    from .product_worker import _finish

    generate_presentation_artifact(task, fence, attempt_id, input_revision, blueprint)
    return _finish(task.pk, fence, attempt_id, "WAITING_REVIEW", "FINAL_REVIEW")
