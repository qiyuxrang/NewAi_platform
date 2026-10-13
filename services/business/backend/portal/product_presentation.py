"""Editable, source-bound business/technology PowerPoint draft."""

import hashlib
import json
import math
import os
import subprocess
import time
import uuid
from pathlib import Path

from django.conf import settings

from .product_documents import DocumentError, _document_runtime, _safe_environment
from .product_storage import private_root

SCRIPT = Path(__file__).resolve().parent / "product_assets" / "simple_presentation.py"


def presentation_renderer_hash():
    return hashlib.sha256(SCRIPT.read_bytes() + Path(__file__).read_bytes()).hexdigest()


def _valid_plan(plan, pair, slides):
    if (not isinstance(plan, dict) or plan.get("schema_version") != 1 or plan.get("locked") is not True
            or plan.get("style") not in {"business", "consulting", "government", "engineering", "dark-tech", "minimal"}
            or plan.get("goal") not in {"customer", "department", "decision"}
            or plan.get("sources") != pair["sources"] or plan.get("pair_hash") != pair.get("sha256", "")
            or plan.get("input_hash") != pair.get("input_hash", "") or plan.get("blueprint_hash") != pair.get("blueprint_hash", "")
            or not isinstance(plan.get("pages"), list) or len(plan["pages"]) != slides):
        return False
    known = {block["ref"] for block in pair["blocks"]}
    for index, page in enumerate(plan["pages"], 1):
        if (not isinstance(page, dict) or page.get("page") != index
                or not isinstance(page.get("title"), str) or not 1 <= len(page["title"]) <= 100
                or not isinstance(page.get("source_refs"), list)
                or any(not isinstance(ref, str) or ref not in known for ref in page["source_refs"])
                or not isinstance(page.get("items"), list) or not all(isinstance(item, str) for item in page["items"])
                or not isinstance(page.get("speaker_notes"), str)):
            return False
    design = plan.get("design", {})
    checks = plan.get("program_checks", {})
    return (isinstance(design, dict) and design.get("canvas") == "16:9"
            and design.get("minimum_body_pt") == 20 and design.get("minimum_node_pt") == 18
            and design.get("minimum_source_pt") == 12
            and isinstance(checks, dict) and checks.get("status") == "pass" and checks.get("issues") == [])


def _valid_manifest(quality, pair):
    if not isinstance(quality, dict):
        return False
    text_fields = ("engine", "engine_version", "design_profile", "fact_boundary")
    counts = ("slides", "diagram_slides", "native_charts", "editable_data_visuals", "visual_asset_count",
              "source_blocks", "source_blocks_mapped")
    references = ("mapped_source_refs", "omitted_source_refs", "missing_source_refs")
    if (any(not isinstance(quality.get(key), str) or not 1 <= len(quality[key]) <= 500 for key in text_fields)
            or any(type(quality.get(key)) is not int or not 0 <= quality[key] <= 10000 for key in counts)
            or any(not isinstance(quality.get(key), list) or len(quality[key]) > 10000
                   or any(not isinstance(ref, str) or not 1 <= len(ref) <= 200 for ref in quality[key])
                   or len(set(quality[key])) != len(quality[key]) for key in references)):
        return False
    gate = quality.get("quality_gate")
    layouts = quality.get("layout_inventory")
    ratio = quality.get("dominant_layout_ratio")
    if (not isinstance(gate, dict) or gate.get("status") not in ("pass", "fail")
            or not isinstance(layouts, dict) or not layouts
            or any(not isinstance(key, str) or type(value) is not int or value < 0 for key, value in layouts.items())
            or not quality["slides"] or sum(layouts.values()) != quality["slides"]
            or type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1
            or quality.get("source_mapping_scope") != "selected_summary_blocks"
            or quality.get("content_review") != "not_run"):
        return False
    if quality.get("engine_version") == "v5":
        checks = quality.get("program_checks", {})
        if (not _valid_plan(quality.get("presentation_plan"), pair, quality["slides"])
                or not isinstance(quality.get("presentation_plan_sha256"), str)
                or len(quality["presentation_plan_sha256"]) != 64
                or checks != quality["presentation_plan"].get("program_checks")):
            return False
    all_refs = {block["ref"] for block in pair["blocks"]}
    eligible = {block["ref"] for block in pair["blocks"]
                if block.get("type") in {"heading", "paragraph", "table", "figure"}
                and not block["ref"].split(":", 1)[-1].startswith(("DRAFT_NOTICE", "PENDING_"))}
    mapped = set(quality["mapped_source_refs"])
    for family in ("technical-solution", "feasibility"):
        body = {block["ref"] for block in pair["blocks"]
                if block["ref"] in eligible and block["ref"].startswith(family + ":")
                and block.get("type") in {"paragraph", "table"}}
        if body and not body & mapped:
            return False
    pending = pair.get("diagram_pending", [])
    reports = pair.get("draft_quality", {}).get("reports", [])
    reasons = quality.get("presentation_quality_reasons", [])
    if (not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons)
            or len(set(reasons)) != len(reasons)
            or set(reasons) - {"visual_assets_missing", "copy_review_required", "layout_review_required", "source_image_font_unverified"}
            or ("visual_assets_missing" in reasons and quality["visual_asset_count"] != 0)):
        return False
    if (gate["status"] == "pass" and quality["visual_asset_count"] == 0
            or ("draft_quality" in quality and quality["visual_asset_count"] == 0 and "visual_assets_missing" not in reasons)):
        return False
    if pending or reasons or any(report.get("quality_issue_count", 0) for report in reports):
        draft_quality = quality.get("draft_quality", {})
        diagrams = quality.get("diagram_generation", {})
        if not isinstance(draft_quality, dict) or not isinstance(diagrams, dict):
            return False
        issue_count = sum(report.get("quality_issue_count", 0) for report in reports) + len(pending) + bool(reasons)
        codes = sorted({code for report in reports for code in report.get("quality_issue_codes", [])}
                       | ({"diagram_pending"} if pending else set())
                       | ({"presentation_quality_warning"} if reasons else set()))
        source_figures = sum(block.get("type") == "figure" for block in pair["blocks"])
        if (gate["status"] != "fail" or draft_quality.get("reports") != reports
                or (quality.get("engine_version") != "v5" and (quality["slides"] != 6 or layouts.get("pending") != 1))
                or (quality.get("engine_version") == "v5" and not any(page["type"] == "pending" for page in quality["presentation_plan"]["pages"]))
                or type(draft_quality.get("quality_issue_count")) is not int or draft_quality.get("quality_issue_count") != issue_count
                or draft_quality.get("quality_issue_codes") != codes or draft_quality.get("human_review_required") is not True
                or draft_quality.get("presentation_quality_reasons") != reasons
                or diagrams.get("status") != ("pending" if pending else "completed")
                or diagrams.get("pending_count") != len(pending) or diagrams.get("pending_figures") != pending
                or any(type(diagrams.get(key)) is not int for key in ("pending_count", "planned_count", "rendered", "source_image_count"))
                or diagrams.get("source_versions") != pair["sources"]
                or diagrams.get("planned_count") != source_figures + len(pending)
                or diagrams.get("rendered") != source_figures or diagrams.get("source_scope") != "report_figures"
                or type(diagrams.get("source_image_count")) is not int or diagrams["source_image_count"] < 0
                or diagrams["source_image_count"] != quality["visual_asset_count"]):
            return False
    elif "draft_quality" in quality or "diagram_generation" in quality:
        return False
    return (quality["source_blocks"] == len(eligible)
            and quality["source_blocks_mapped"] == len(eligible & mapped)
            and set(quality["omitted_source_refs"]) == eligible - mapped
            and set(quality["missing_source_refs"]) == mapped - all_refs)


def _render_with_progress(command, directory, content, pair, progress, timeout):
    """Keep the existing subprocess timeout and stop it if the worker loses its lease."""
    last = None
    def report_progress():
        nonlocal last
        path = content.with_suffix(".progress.json")
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                return
            raw = path.read_bytes()
            if raw == last:
                return
            event = json.loads(raw)
            plan = event.get("plan", {})
            total, completed = event.get("total_count"), event.get("completed_count")
            if (type(total) is not int or type(completed) is not int or not 0 <= completed <= total <= 10000
                    or event.get("stage") not in {"planning", "rendering", "repairing", "validating"}
                    or not _valid_plan({**plan, "program_checks": {"status": "pass", "issues": []}}, pair, total)):
                return
        except (OSError, ValueError, TypeError, AttributeError):
            return
        last = raw
        progress(event)

    started = time.monotonic()
    with subprocess.Popen(command, cwd=directory, env=_safe_environment(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.25, remaining))
                    report_progress()
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    report_progress()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def render_presentation_draft(task, pair, *, presentation_style="auto", communication_goal="", audience="", purpose="", requirements="", progress=None):
    if pair.get("approval_inherited") is not False or not pair.get("blocks") or not pair.get("sources"):
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_source", "reason": "invalid_source"})
    try:
        runtime = _document_runtime()
    except DocumentError:
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_runtime", "reason": "runtime_missing"}) from None
    root = private_root().resolve()
    directory = root / str(task.pk) / "artifacts" / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    content = directory / "pair.json"
    context = dict(pair.get("planning_context", {}))
    context.setdefault("style", "auto")
    for key, value in (("style", presentation_style), ("goal", communication_goal), ("audience", audience),
                       ("purpose", purpose), ("requirements", requirements)):
        if value and (key != "style" or value != "auto" or "style" not in pair.get("planning_context", {})):
            context[key] = value
    content.write_text(json.dumps({"title": task.title, **pair, "planning_context": context, "draft_mode": True}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    output = directory / "draft.pptx"
    manifest = output.with_suffix(".manifest.json")
    try:
        command = [str(runtime), "-B", str(SCRIPT), str(content), str(output)]
        timeout = int(getattr(settings, "PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS", 300))
        if progress is not None:
            result = _render_with_progress(command, directory, content, pair, progress, timeout)
        else:
            result = subprocess.run(command, cwd=directory, env=_safe_environment(), capture_output=True,
                                    timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_render", "reason": "timeout"}) from None
    except OSError:
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_render", "reason": "launch_failed"}) from None
    if result.returncode:
        reason = "process_failed"
        stderr = result.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        known_errors = {"presentation source limit exceeded": "source_limit", "invalid slide source": "invalid_source",
                        "presentation quality gate failed": "quality_failed"}
        last_line = stderr.rstrip().splitlines()[-1] if stderr.strip() else ""
        for message, code in known_errors.items():
            if last_line == "ValueError: " + message:
                reason = code
                break
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_render", "reason": reason, "returncode": result.returncode})
    if not output.is_file() or not manifest.is_file():
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_manifest", "reason": "missing_output"})
    try:
        quality = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_manifest", "reason": "invalid_manifest"}) from None
    if not _valid_manifest(quality, pair):
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_manifest", "reason": "invalid_manifest"})
    if quality.get("engine_version") == "v5":
        plan_path = content.with_suffix(".plan.json")
        try:
            plan_bytes = plan_path.read_bytes()
            plan = json.loads(plan_bytes)
        except (OSError, UnicodeError, ValueError):
            raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_manifest", "reason": "invalid_manifest"}) from None
        if (plan != quality["presentation_plan"] or hashlib.sha256(plan_bytes).hexdigest() != quality["presentation_plan_sha256"]):
            raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_manifest", "reason": "invalid_manifest"})
    if (quality["missing_source_refs"] or (quality["quality_gate"].get("status") != "pass"
            and not quality.get("draft_quality", {}).get("human_review_required"))):
        raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_quality", "reason": "quality_failed"})
    office = None
    if getattr(settings, "PRODUCT_OFFICE_RENDER_ENABLED", False):
        from .product_rendering import render_office
        try:
            office = render_office(output.relative_to(root).as_posix(), hashlib.sha256(output.read_bytes()).hexdigest())
        except DocumentError as error:
            raise DocumentError("presentation_unavailable", diagnostic={
                "stage": "presentation_office_render", "reason": error.code}) from None
    return {"path": output.relative_to(root).as_posix(), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "template_hash": presentation_renderer_hash(),
            "render_evidence": {"kind": "draft", "status": "draft_unverified", "engine": quality["engine"],
                                "engine_version": quality["engine_version"], "design_profile": quality["design_profile"],
                                "quality_gate": quality["quality_gate"], "slides": quality["slides"],
                                **({"presentation_plan": quality["presentation_plan"],
                                    "presentation_plan_sha256": quality["presentation_plan_sha256"],
                                    "program_checks": quality["program_checks"]} if quality.get("engine_version") == "v5" else {}),
                                **({key: quality[key] for key in ("draft_quality", "diagram_generation") if key in quality}),
                                "diagram_slides": quality["diagram_slides"], "native_charts": quality["native_charts"],
                                "editable_data_visuals": quality["editable_data_visuals"],
                                "visual_asset_count": quality.get("visual_asset_count", 0),
                                "layout_inventory": quality["layout_inventory"],
                                "dominant_layout_ratio": quality["dominant_layout_ratio"],
                                "source_block_coverage": {"total": quality["source_blocks"],
                                                          "mapped": quality["source_blocks_mapped"]},
                                "source_mapping_scope": quality["source_mapping_scope"],
                                "omitted_source_blocks": len(quality["omitted_source_refs"]),
                                "content_review": quality["content_review"],
                                "fact_boundary": quality["fact_boundary"],
                                "pair_hash": pair["sha256"], "source_versions": pair["sources"],
                                "block_refs": [{"ref": block["ref"], "source_ids": block.get("source_ids", [])}
                                               for block in pair["blocks"] if block["ref"] in set(quality["mapped_source_refs"])],
                                "office_render": "completed" if office else "not_run",
                                **({"office_render_evidence": office} if office else {}),
                                "visual_review": "not_run", "business_approval": "blocked"}}
