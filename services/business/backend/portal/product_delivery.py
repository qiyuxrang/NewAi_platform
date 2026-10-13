"""Automatic delivery after the owner's exact blueprint confirmation.

Delivery is a separate decision; it never upgrades program checks to model or
human review, and never modifies the legacy formal-release approvals.
"""

from .product_service import ProductError, approved_blueprint, blueprint_chapters, current_revision

POLICY = "owner-blueprint-auto-delivery-v1"


def artifact_delivery(artifact, *, current=None):
    from .product_pair import FAMILIES, output_current
    from .product_three_drafts import _rendered_result_current

    task = artifact.task
    current = output_current(task, artifact) if current is None else current
    decision = {"policy": POLICY, "status": "stale" if not current else "draft",
                "delivered": False, "blocking_issues": [], "warnings": [],
                "artifact_sha256": artifact.sha256, "input_sha256": artifact.input_hash,
                "blueprint_sha256": artifact.blueprint_hash, "quality_scope": "not_run"}
    if not current:
        decision["blocking_issues"].append({"code": "stale_output"})
        return decision
    blocked, warnings = decision["blocking_issues"], decision["warnings"]
    blueprint = approved_blueprint(task)
    current_input = current_revision(task, "input")
    if not blueprint or not current_input:
        blocked.append({"code": "blueprint_approval_required"})
        return decision
    approval = blueprint.approvals.filter(actor_id=task.owner_id).order_by("-created_at").first()
    decision.update(input_version=current_input.version, blueprint_version=blueprint.version,
                    owner_blueprint_confirmation={"id": str(approval.pk), "actor_id": approval.actor_id,
                                                  "sha256": approval.sha256})
    evidence = artifact.render_evidence
    report = None
    if artifact.family in FAMILIES:
        from .product_worker import (_chapter_character_count, _content_review_current,
            _family_target, _formal_content_guard, _minimum_characters, current_chapters,
            ExecutionError, _DRAFT_QUANTITY_PENDING_CONDITION)

        report = task.revisions.filter(pk=evidence.get("report_id"), kind="report").first()
        found = current_chapters(task, current_input.sha256, blueprint.sha256, artifact.family)
        chapters = [found.get(chapter["id"]) for chapter in blueprint_chapters(blueprint.payload, artifact.family)]
        if not report or not chapters or any(chapter is None for chapter in chapters):
            blocked.append({"code": "chapters_incomplete"})
            return decision
        if not _content_review_current(task, artifact.review, current_input, blueprint, chapters):
            blocked.append({"code": "stale_report_review"})
            return decision
        checked = artifact.review.payload
        model = checked.get("model_review", {})
        decision.update(quality_scope=model.get("scope", "not_run"), review_sha256=artifact.review.sha256,
                        chapter_hashes={chapter.payload["chapter_id"]: chapter.sha256 for chapter in chapters})
        # The exact owner-approved condition remains valid after output actions
        # change or finish; delivery must not depend on a mutable queue action.
        quantity_pending = _DRAFT_QUANTITY_PENDING_CONDITION in blueprint.payload.get("conditions", [])
        for issue in checked.get("issues", []):
            nonblocking = (issue.get("code") in {"unresolved_blueprint_items", "unresolved_input_items"}
                           or quantity_pending and issue.get("code") == "quantity_source_ambiguous")
            (warnings if nonblocking else blocked).append(issue)
        if checked.get("program_checks_complete") is not True:
            blocked.append({"code": "program_checks_incomplete"})
        if model.get("status") == "issues_found" or model.get("issues"):
            blocked.append({"code": "model_content_issues", "issues": model.get("issues", [])})
        actual = _chapter_character_count(chapters)
        minimum = _minimum_characters(_family_target(artifact.family))
        decision.update(actual_characters=actual, minimum_characters=minimum)
        if actual < minimum:
            blocked.append({"code": "output_length_below_target", "actual_characters": actual,
                            "minimum_characters": minimum})
        try:
            _formal_content_guard(chapters, artifact.family)
        except ExecutionError as error:
            blocked.append({"code": error.code})
        structure = evidence.get("document_structure", {})
        from .product_diagrams import minimum_diagrams
        if (not isinstance(structure, dict)
                or any(type(structure.get(key)) is not int for key in
                       ("figure_count", "heading1_count", "heading2_count", "toc_depth", "embedded_raster_count"))
                or evidence.get("structural_generation") != "completed"
                or structure.get("figure_count", 0) < minimum_diagrams(artifact.family)
                or structure.get("heading1_count", 0) < 1 or structure.get("heading2_count", 0) < 1
                or structure.get("toc_depth") != 2
                or structure.get("embedded_raster_count", 0) < structure.get("figure_count", 0)
                or structure.get("mermaid_source_embedded") is not False):
            blocked.append({"code": "document_structure_incomplete"})
    elif artifact.family == "presentation":
        decision["quality_scope"] = "presentation_program_checks"
        for family in FAMILIES:
            source = task.artifacts.filter(family=family).order_by("-version").first()
            if not source or not artifact_delivery(source)["delivered"]:
                blocked.append({"code": "source_report_not_delivered", "family": family})
        if evidence.get("quality_gate", {}).get("status") != "pass":
            blocked.append({"code": "presentation_quality_failed"})
        checks = evidence.get("program_checks")
        if checks is not None and (checks.get("status") != "pass" or checks.get("issues")):
            blocked.append({"code": "presentation_program_checks_failed"})
    else:
        blocked.append({"code": "unsupported_delivery_family"})
    diagrams = evidence.get("diagram_generation", {})
    if diagrams.get("pending_count") or diagrams.get("pending_figures") or diagrams.get("quality_issue_count"):
        blocked.append({"code": "diagram_pending"})
    if not _rendered_result_current({"path": artifact.path, "sha256": artifact.sha256,
            "render_evidence": evidence}, report.payload if report else None):
        blocked.append({"code": "artifact_hash_mismatch"})
    decision["delivered"] = not blocked
    decision["status"] = "delivered" if not blocked else "draft"
    return decision


def record_artifact_delivery(artifact):
    decision = artifact_delivery(artifact)
    artifact.render_evidence = {**artifact.render_evidence, "delivery_decision": decision}
    artifact.save(update_fields=["render_evidence"])
    return decision


def finish_output_delivery(task, fence, attempt_id, *, families=None):
    from .product_models import DocumentTask
    from .product_worker import _analysis_progress, _finish

    task = DocumentTask.objects.get(pk=task.pk)
    families = families if families is not None else task.checkpoint.get(
        "output_families", ["technical-solution", "feasibility", "presentation"])
    decisions = {}
    for family in families:
        artifact = task.artifacts.filter(family=family).order_by("-version").first()
        decisions[family] = artifact_delivery(artifact) if artifact else {
            "delivered": False, "blocking_issues": [{"code": "output_missing"}]}
    complete = bool(decisions) and all(decision["delivered"] for decision in decisions.values())
    _analysis_progress(task.pk, fence, "outputs", "completed" if complete else "waiting",
        detail="全部请求成果已交付，可下载或查看历史版本" if complete else "有效成果已交付；其余草稿已保存，待修复后继续生成",
        output_families=families, delivery_decisions=decisions, second_approval_required=False)
    return _finish(task.pk, fence, attempt_id, "COMPLETED" if complete else "WAITING_INPUT", "FINAL_REVIEW",
        error_code="" if complete else "delivery_incomplete",
        failure=None if complete else {"stage": "delivery", "outputs": {
            family: {"status": decision.get("status", "draft"),
                     "blocking_codes": sorted({issue.get("code", "unknown")
                                               for issue in decision["blocking_issues"]})}
            for family, decision in decisions.items()}})
