from types import SimpleNamespace

from .product_storage import StorageError, verified_artifact


CONTENT_CHECKS = {"facts", "quantities", "terms", "sources", "completeness", "conditions"}


def evidence_file(record):
    if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("sha256"), str):
        raise StorageError("invalid_evidence", "成果证据无效。")
    return verified_artifact(SimpleNamespace(path=record["path"], sha256=record["sha256"]))


def public_quality_warnings(evidence, review_issues=()):
    """Expose bounded draft findings, never renderer paths or authored paragraphs."""
    quality = evidence.get("draft_quality") or {}
    diagrams = evidence.get("diagram_generation") or {}
    codes = list(quality.get("quality_issue_codes") or [])
    codes.extend(issue.get("code") for issue in review_issues if isinstance(issue, dict))
    content_count = len(set(code for code in codes if isinstance(code, str)))
    codes.extend(issue.get("code") for issue in diagrams.get("quality_issues", []) if isinstance(issue, dict))
    issues = [{"code": code} for code in dict.fromkeys(code for code in codes
              if isinstance(code, str) and code and len(code) <= 64)][:10]
    count = quality.get("quality_issue_count", 0)
    diagram_count = diagrams.get("quality_issue_count", 0)
    result = {"issue_count": max(count if type(count) is int and count >= 0 else 0,
                                 len(review_issues), content_count)
                            + (diagram_count if type(diagram_count) is int and diagram_count >= 0 else 0),
              "issues": issues}
    for field in ("actual_characters", "minimum_characters"):
        value = quality.get(field)
        if type(value) is int and value >= 0:
            result[field] = value
    if "planned_count" in diagrams:
        pending = [{"figure_id": str(item.get("figure_id", ""))[:100],
                    "error_code": str(item.get("error_code", "diagram_pending"))[:64]}
                   for item in diagrams.get("pending_figures", [])[:100] if isinstance(item, dict)]
        result["figures"] = {"planned": diagrams.get("planned_count", 0),
                             "rendered": diagrams.get("rendered", 0), "pending": pending,
                             "pending_count": diagrams.get("pending_count", len(pending))}
    return result


def public_presentation_plan(plan):
    """Only presentation copy and bindings; renderer paths never leave storage."""
    if not isinstance(plan, dict) or not isinstance(plan.get("pages"), list):
        return None
    result = {key: plan[key] for key in ("schema_version", "locked", "style", "style_label", "goal", "goal_label",
        "selection_reason", "selection_reasons", "pair_hash", "input_hash", "blueprint_hash") if key in plan}
    result["sources"] = [{key: source[key] for key in ("family", "id", "version", "sha256") if key in source}
                         for source in plan.get("sources", []) if isinstance(source, dict)]
    result["pages"] = [{key: page[key] for key in ("page", "title", "type", "items", "speaker_notes", "source_refs", "layout")
                        if key in page} for page in plan["pages"] if isinstance(page, dict)]
    return result


def public_evidence(evidence):
    return {key: value for key, value in evidence.items() if key in
            {"kind", "status", "verified", "docx_sha256", "page_count", "visual_review", "template_approval_hash"}} | {
        "pages": [{"page": page.get("page"), "sha256": page.get("sha256")} for page in evidence.get("pages", [])],
        "quality_warnings": public_quality_warnings(evidence),
        "presentation_plan": public_presentation_plan(evidence.get("presentation_plan")),
    }


def candidate_current(artifact, *, visual=False):
    from .product_documents import DocumentError, _template_approval, frozen_pack
    from .product_service import approved_blueprint, blueprint_chapters, digest, input_authorized, approval_authorization

    task = artifact.task
    evidence = artifact.render_evidence
    if evidence.get("kind") != "candidate" or evidence.get("docx_sha256") != artifact.sha256:
        return False
    try:
        approval = _template_approval(frozen_pack())
    except DocumentError:
        return False
    if approval["template_hash"] != artifact.template_hash or digest(approval) != evidence.get("template_approval_hash"):
        return False
    blueprint = approved_blueprint(task)
    current_input = task.revisions.filter(kind="input", version=task.input_version).first()
    review = artifact.review
    if not input_authorized(task, current_input):
        return False
    if (not blueprint or not current_input or current_input.payload.get("issues")
            or not review or review.kind != "review" or review.payload.get("passed") is not True
            or review.input_hash != artifact.input_hash or current_input.sha256 != artifact.input_hash
            or review.blueprint_hash != artifact.blueprint_hash or blueprint.sha256 != artifact.blueprint_hash
            or task.artifacts.filter(family=artifact.family).order_by("-version").values_list("pk", flat=True).first() != artifact.pk):
        return False
    chapter_hashes = {}
    for chapter in task.revisions.filter(kind="chapter", family=artifact.family, input_hash=current_input.sha256, blueprint_hash=blueprint.sha256).order_by("version"):
        chapter_hashes[chapter.payload["chapter_id"]] = chapter.sha256
    if (set(chapter_hashes) != {chapter["id"] for chapter in blueprint_chapters(blueprint.payload, artifact.family)}
            or review.payload.get("chapter_hashes") != chapter_hashes):
        return False
    try:
        verified_artifact(artifact)
        evidence_file(evidence.get("pdf"))
        pages = evidence.get("pages", [])
        if not pages or evidence.get("page_count") != len(pages):
            return False
        for index, page in enumerate(pages, 1):
            if page.get("page") != index:
                return False
            evidence_file(page)
    except (StorageError, OSError):
        return False
    if visual:
        check = evidence.get("visual_review")
        if (not isinstance(check, dict) or check.get("passed") is not True
                or check.get("authorization") != approval_authorization(task, task.reviewer)
                or check.get("actor_id") != task.reviewer_id or check.get("sha256") != artifact.sha256
                or check.get("review_hash") != review.sha256
                or check.get("pages_hash") != digest([{key: page[key] for key in ("page", "sha256")} for page in pages])
                or set(check.get("content_checks", {})) != CONTENT_CHECKS
                or any(value is not True for value in check["content_checks"].values())):
            return False
    return True
