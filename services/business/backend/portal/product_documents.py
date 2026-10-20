import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .product_storage import private_root
from .product_office_runtime import run_office
from .product_docx_layout import normalize_docx_layout
from .product_formal import has_repeated_filler, unsupported_financial_conclusion
from .product_render_cache import StageCache, atomic_write, canonical_hash, confined, file_hash
from .product_diagrams import (
    add_structural_blocks,
    apply_diagram_descriptions,
    apply_diagram_layout,
    diagram_contract_hash,
    diagram_evidence_blocks,
    heading_display_text,
    validate_diagram_batch,
    inspect_docx_requirements,
    validate_document_requirements,
)


PACK = Path(__file__).resolve().parent / "product_assets" / "bj_docs"


class DocumentError(Exception):
    def __init__(self, code, *, diagnostic=None):
        self.code = code
        self.diagnostic = diagnostic or {}
        super().__init__(code)


def _company_name():
    try:
        policy = json.loads((PACK / "assets" / "document-format-policy.json").read_text(encoding="utf-8"))
        value = policy["company_identity"]["name"].strip()
        if not value or len(value) > 200:
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
        raise DocumentError("template_unavailable") from None


def _family_document_title(title, family):
    title = title.strip()
    # Workflow state belongs in the platform, not in the delivered document title.
    title = re.sub(r"[（(](?:代表性)?(?:草稿|待审稿)[）)]\s*$", "", title).strip()
    suffix = "技术方案" if family == "technical-solution" else "可行性研究报告"
    if suffix in title:
        return title
    if "三件套" in title:
        return title.replace("三件套", suffix, 1)
    return f"{title}（{suffix}）"


def frozen_pack(family="technical-solution"):
    if family not in {"technical-solution", "feasibility"}:
        raise DocumentError("template_unavailable")
    try:
        manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            target = (PACK / entry["path"]).resolve()
            if not target.is_relative_to(PACK.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
                raise DocumentError("template_unavailable")
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise DocumentError("template_unavailable") from None


_BODY_FIELD = re.compile(r'^\s*[\[{,]*\s*["\']?(?:source_ids|requirement_ids|chapter_id|paragraphs|title)["\']?\s*(?::.*)?\s*$', re.I)
_BODY_PLACEHOLDER = re.compile(r"^(?:待生成正文|正文待生成|待补充正文|章节正文占位|TODO|TBD|PLACEHOLDER|<[^<>]*placeholder[^<>]*>)$", re.I)


def clean_report_paragraph(paragraph):
    """Remove standalone model-contract residue without rewriting authored prose."""
    lines = []
    for line in paragraph.splitlines():
        value = line.strip()
        if (_BODY_FIELD.fullmatch(value.strip("`")) or _BODY_PLACEHOLDER.fullmatch(value.strip("`"))
                or re.fullmatch(r'[\[\]{}",\s]+|```(?:json)?', value, re.I)
                or re.fullmatch(r'["\']?[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}["\']?,?', value, re.I)
                or re.fullmatch(r'["\'][A-Za-z0-9_-]+["\'],?', value)):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def assembly_quality_issues(chapters):
    """Keep original fragments and chapter locations in platform diagnostics."""
    issues = []
    for chapter in chapters:
        payload = chapter.payload
        paragraphs = payload.get("paragraphs", [])
        cleaned = [clean_report_paragraph(paragraph) for paragraph in paragraphs]
        for index, (original, body) in enumerate(zip(paragraphs, cleaned)):
            if original.strip() != body:
                issues.append({"code": "internal_body_fragment", "chapter_id": payload["chapter_id"],
                               "paragraph_index": index, "claim": original,
                               "correction": "内部字段或占位片段不作为客户正文；保留原始证据并修正本段。"})
        if not any(cleaned):
            issues.append({"code": "chapter_body_missing", "chapter_id": payload["chapter_id"],
                           "title": payload["title"], "claim": "\n".join(paragraphs),
                           "correction": "本章缺少有效正文；仅补充该章设计内容，保留其他已有效章节。"})
    return issues


def content_document(task, input_revision, blueprint, chapters, family="technical-solution", *, draft=False, review_issues=()):
    if family not in {"technical-solution", "feasibility"}:
        raise DocumentError("template_unavailable")
    if blueprint.payload.get("template_version") != "frozen-original-v1":
        raise DocumentError("template_unavailable")
    facts = input_revision.payload
    source_map = {}
    sources = [{"id": "SINPUT", "text": f"输入版本{input_revision.pk}；SHA256={input_revision.sha256}；人工资料，真实性待审核。"}]
    for index, item in enumerate([*facts.get("items", []), *facts.get("sources", []), *facts.get("knowledge_sources", [])], start=1):
        source_id = f"S{index}"
        original_id = str(item.get("id", item.get("row_id", "")))
        source_map.setdefault(original_id, []).append(source_id)
        sources.append({"id": source_id, "text": json.dumps(item, ensure_ascii=False, allow_nan=False)})
    conditions = facts.get("conditions", [])
    requirements = [{"id": f"R{index}", "text": value} for index, value in enumerate(conditions, start=1)]
    if facts.get("requirements", "").strip():
        requirements.append({"id": "RINPUT", "text": facts["requirements"]})
    requirement_ids = [item["id"] for item in requirements]
    from .product_generation_policy import POLICY, generation_only
    if generation_only(task):
        requirements.append({"id": "RGENERATIONPOLICY", "text": POLICY})
    blocks = []
    guide_aware = family == "feasibility" and bool(blueprint.payload.get("feasibility_guide"))
    planned_titles = set()
    bodies = [[clean_report_paragraph(paragraph) for paragraph in chapter.payload["paragraphs"]] for chapter in chapters]
    chapter_count = sum(any(body) for body in bodies)
    chapter_index = 0
    missing_chapters = []
    financial_claims_found = False
    for chapter, body in zip(chapters, bodies):
        payload = chapter.payload
        stable = "C" + hashlib.sha256(payload["chapter_id"].encode()).hexdigest()[:24]
        cited = [mapped for original in payload["source_ids"] for mapped in source_map.get(original, [])] or ["SINPUT"]
        heading_title = heading_display_text(payload["title"])
        blocks.append({"id": stable, "type": "heading", "level": 1, "text": heading_title, "source_ids": cited, "requirement_ids": requirement_ids})
        if not any(body):
            missing_chapters.append(payload["chapter_id"])
            if not draft:
                continue
            blocks.append({"id": stable + "MISSING", "type": "paragraph",
                           "text": f"本章“{heading_title}”缺少有效设计正文，需由编制负责人补充本章内容后复核。",
                           "source_ids": cited, "requirement_ids": requirement_ids})
            continue
        accepted_body = []
        for index, paragraph in enumerate(body, start=1):
            if not paragraph:
                continue
            if family == "feasibility" and unsupported_financial_conclusion(paragraph):
                financial_claims_found = True
                if not draft:
                    continue
            if guide_aware:
                accepted_body.append(paragraph)
                continue
            for part_index, text in enumerate((part.strip() for part in paragraph.splitlines() if part.strip()), start=1):
                identifier = f"{stable}P{index}" + (f"_{part_index}" if part_index > 1 else "")
                blocks.append({"id": identifier, "type": "paragraph", "text": text,
                               "source_ids": cited, "requirement_ids": requirement_ids})
        if guide_aware:
            from .product_feasibility_blocks import authored_blocks, figure_plan
            blocks.extend(authored_blocks(accepted_body, stable, cited, requirement_ids))
            titles = [title for title in figure_plan(blueprint.payload, payload["chapter_id"]) if title not in planned_titles]
            planned_titles.update(titles)
        add_structural_blocks(
            blocks,
            family,
            cited,
            requirement_ids,
            chapter_index=chapter_index,
            chapter_count=chapter_count,
            chapter_title=payload["title"],
            **({"diagram_titles": titles} if guide_aware else {}),
        )
        chapter_index += 1
    if guide_aware:
        from .product_feasibility import asset_hash
        requirements.append({"id": "RGUIDEFIGURES", "text": json.dumps({"asset_sha256": asset_hash(),
            "figure_ids": [block["id"] for block in blocks if block["type"] == "figure"]}, ensure_ascii=False)})
    if missing_chapters and not draft:
        raise DocumentError("chapter_body_missing", diagnostic={"stage": "content_assembly", "chapter_ids": missing_chapters})
    pending = []
    if family == "feasibility":
        pending.append("未提供经核实的成本与收益依据，不形成经济成本、收益或回报结论。")
        if financial_claims_found:
            pending.append("可研正文中的投资或回报数值仍需核对依据，尚未人工批准。" if draft else
                           "可研正文包含未经核实的投资或回报数值结论，已拒绝纳入交付；请补充并确认对应依据。")
    pending.extend(blueprint.payload.get("missing", []))
    pending.extend(blueprint.payload.get("conflicts", []))
    if facts.get("issues"):
        pending.append("输入资料存在缺项或冲突，请在平台逐项复核，不得按无问题发布。")
    # Review findings retain their original evidence in platform records.
    unique_pending = {}
    for value in pending:
        value = value.strip()
        key = re.sub(r"\s+", "", value).rstrip("。；;.")
        if key:
            unique_pending.setdefault(key, value)
    pending = list(unique_pending.values())
    # Keep unresolved source records for human review without appending a report chapter.
    return {"version": 1, "family": family,
            "metadata": {"id": "T" + str(task.pk).replace("-", ""),
                         "title": _family_document_title(task.title, family),
                         "subtitle": "技术方案" if family == "technical-solution" else "可行性研究报告",
                         "date": timezone.localdate().isoformat(), "organization": _company_name(), "status": "draft"},
            "sources": sources, "requirements": requirements,
             "pending": [{"id": f"PEND{index}", "text": value} for index, value in enumerate(pending, start=1)], "blocks": blocks}


def _document_runtime():
    runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
    if not runtime.is_absolute():
        runtime = settings.BASE_DIR / runtime
    if not runtime.is_file():
        raise DocumentError("template_unavailable")
    return runtime.resolve()


def _mermaid_runtime():
    configured = str(getattr(settings, "PRODUCT_MERMAID_NODE", "node")).strip()
    runtime = configured if Path(configured).is_absolute() else shutil.which(configured)
    if not runtime or not Path(runtime).is_file():
        raise DocumentError("template_unavailable")
    return Path(runtime).resolve()


def _mermaid_chromium():
    configured = str(getattr(settings, "PRODUCT_MERMAID_CHROMIUM", "")).strip()
    candidates = [configured] if configured else []
    for command in ("chromium", "chromium-browser", "google-chrome", "msedge"):
        found = shutil.which(command)
        if found:
            candidates.append(found)
    if os.name == "nt":
        for root in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            if root:
                candidates.extend([str(Path(root) / "Microsoft/Edge/Application/msedge.exe"),
                                   str(Path(root) / "Google/Chrome/Application/chrome.exe")])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise DocumentError("template_unavailable")


def _safe_environment():
    environment = {key: value for key, value in os.environ.items() if key.upper() in
                   {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "PATH", "HOME", "LANG", "LC_ALL", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"}}
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONNOUSERSITE="1")
    return environment


def preflight_document_rendering(*, draft=False):
    """Check executable dependencies before generating paid content or files.

    Child stderr is never propagated: it may contain paths, authored source or
    credentials. Diagnostics use only these fixed stage/reason identifiers.
    """
    stage = "document_preflight"
    reason = "document_python_unavailable"
    try:
        runtime = _document_runtime()
        reason = "document_python_dependencies_unavailable"
        imports = "import lxml.etree, docx, pptx, fitz, PIL"
        if (getattr(settings, "PRODUCT_OFFICE_RENDER_ENABLED", False)
                and getattr(settings, "PRODUCT_OFFICE_RENDERER", "word") == "word"):
            imports += "; import win32com.client"
        result = subprocess.run([str(runtime), "-B", "-c", imports], env=_safe_environment(),
                                capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError
        try:
            reason = "node_unavailable"
            node = _mermaid_runtime()
            reason = "chromium_unavailable"
            chromium = _mermaid_chromium()
            reason = "mermaid_runtime_invalid"
            environment = _safe_environment()
            environment["PORTAL_CHROMIUM_PATH"] = str(chromium)
            result = subprocess.run([str(node), str(PACK.parent / "mermaid-runtime" / "render.mjs"), "--preflight"],
                                    env=environment, capture_output=True, timeout=30,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise ValueError
            mermaid = json.loads(result.stdout)
            if any(not isinstance(mermaid.get(name), str) or not re.fullmatch(r"[a-f0-9]{64}", mermaid[name])
                   for name in ("bundleSha256", "manifestSha256", "rendererSha256", "nodeSha256", "chromiumSha256")):
                raise ValueError
        except (DocumentError, OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            if not draft:
                raise
            mermaid = {"status": "unavailable", "reason": reason}
        reason = "office_renderer_unavailable"
        office_script = None
        if getattr(settings, "PRODUCT_OFFICE_RENDER_ENABLED", False):
            command = _office_command(runtime, Path("input.docx"), Path("render"), 300)
            office_script = file_hash(Path(command[2]))
        renderer_files = [Path(__file__), Path(__file__).with_name("product_render_cache.py"),
                          Path(__file__).with_name("product_feasibility_blocks.py"),
                          Path(__file__).with_name("product_docx_layout.py"),
                          Path(__file__).with_name("product_office_runtime.py")]
        renderer_files.extend(sorted((PACK / "scripts").glob("*.py")))
        return {"document_python_sha256": file_hash(runtime), "mermaid": mermaid,
                "renderer_sha256": canonical_hash({path.name: file_hash(path) for path in renderer_files}),
                "office_enabled": bool(getattr(settings, "PRODUCT_OFFICE_RENDER_ENABLED", False)),
                "office_renderer": getattr(settings, "PRODUCT_OFFICE_RENDERER", "word"),
                "office_script_sha256": office_script}
    except (DocumentError, OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        raise DocumentError("template_unavailable", diagnostic={"stage": stage, "reason": reason}) from None


def _diagram_failure_diagnostic(result):
    allowed = {"diagram_layout_unreadable", "runtime_manifest_invalid", "chromium_unavailable", "chromium_launch_failed", "diagram_input_invalid",
               "diagram_path_invalid", "diagram_cache_invalid", "diagram_parse_or_anchor_failed",
               "diagram_bitmap_failed", "diagram_network_blocked"}
    reason = "diagram_renderer_failed"
    try:
        value = json.loads(result.stderr)
        if value.get("reason") in allowed:
            reason = value["reason"]
    except (ValueError, TypeError, AttributeError):
        pass
    return {"stage": "diagram_render", "reason": reason, "returncode": result.returncode}


def _office_command(runtime, source, output, timeout, *, kind="word"):
    """Select an explicit renderer; never fall back after a failed render."""
    renderer = getattr(settings, "PRODUCT_OFFICE_RENDERER", "word")
    if renderer == "word":
        return [str(runtime), "-B", str(PACK / "scripts" / "office_render.py"),
                kind, str(source), str(output), "--timeout", str(timeout)]
    if renderer != "libreoffice":
        raise DocumentError("office_render_unavailable")
    executable = Path(getattr(settings, "PRODUCT_LIBREOFFICE_EXECUTABLE", "/usr/bin/libreoffice"))
    uno_python = Path(getattr(settings, "PRODUCT_UNO_PYTHON", "/usr/bin/python3"))
    if not all(path.is_absolute() and path.is_file() for path in (executable, uno_python)):
        raise DocumentError("office_render_unavailable")
    script = Path(__file__).parent / "product_assets" / "libreoffice_render.py"
    return [str(runtime), "-B", str(script), kind, str(source), str(output),
            "--timeout", str(timeout), "--executable", str(executable), "--uno-python", str(uno_python)]


def _diagram_evidence(output, figure_count):
    try:
        result = json.loads(output)
        versions = {"mermaid": "12.0.0", "katex": "0.18.2", "lodash-es": "4.18.1"}
        bundle_hash = result["bundleSha256"]
        manifest_hash = result["manifestSha256"]
        if (result["rendered"] != figure_count or result["engine"] != "mermaid-js-12.0.0"
                or result["sourcePersisted"] is not False or result["securityLevel"] != "strict"
                or result["blockedNetworkRequests"] != 0
                or not isinstance(bundle_hash, str) or re.fullmatch(r"[0-9a-f]{64}", bundle_hash) is None
                or not isinstance(manifest_hash, str) or re.fullmatch(r"[0-9a-f]{64}", manifest_hash) is None
                or any(result["runtimeVersions"].get(name) != version for name, version in versions.items())):
            raise ValueError
        figures = result["figures"]
        if (not isinstance(figures, list) or len(figures) != figure_count
                or any(not isinstance(item, dict) or not {"figure_id", "sourceSha256", "imageSha256"} <= set(item)
                       or set(item) - {"figure_id", "sourceSha256", "imageSha256", "layout"}
                       or ("layout" in item and not isinstance(item["layout"], dict))
                       or not isinstance(item["figure_id"], str)
                       or any(not isinstance(item[key], str) or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None
                              for key in ("sourceSha256", "imageSha256")) for item in figures)
                or len({item["figure_id"] for item in figures}) != figure_count):
            raise ValueError
        return {"engine": result["engine"], "color": True, "source_persisted": False,
                "figure_count": figure_count, "bundle_sha256": bundle_hash,
                "manifest_sha256": manifest_hash,
                "runtime_versions": result["runtimeVersions"], "security_level": "strict",
                "blocked_network_requests": 0, "figures": figures}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise DocumentError("document_validation_failed") from None


def _refresh_word_field_cache(target, runtime, directory, *, retained_name="word-field-refresh"):
    """Refresh Word fields in an owned short path before promoting the DOCX."""
    if not getattr(settings, "PRODUCT_OFFICE_RENDER_ENABLED", False):
        return {"status": "not_run", "reason": "office_render_disabled"}
    timeout = int(getattr(settings, "PRODUCT_OFFICE_RENDER_TIMEOUT_SECONDS", 300))
    retained = confined(directory, retained_name)
    diagnostic = {"status": "failed", "reason": "staging_failed"}
    try:
        # Never replace evidence from an earlier attempt in this artifact.
        retained.mkdir(exist_ok=False)
    except OSError:
        raise DocumentError("document_render_failed", diagnostic={"stage": "office_render", "reason": "staging_failed"}) from None
    try:
        original = target.read_bytes()
        quality_path = target.with_suffix(".quality.json")
        original_quality = quality_path.read_bytes()
        quality = json.loads(original_quality)
        if not isinstance(quality, dict):
            raise ValueError("Invalid quality report")
        # mkdtemp's private directory is transient; all Office paths, including
        # the renderer's own reviewed copy and PDF, stay below MAX_PATH.
        with tempfile.TemporaryDirectory(prefix="portal-word-") as temporary:
            stage = Path(temporary).resolve()
            source = stage / "input.docx"
            output = stage / "render"
            if os.name == "nt" and any(len(str(path)) >= 260 for path in
                   (source, output / "reviewed.docx", output / "document.pdf")):
                diagnostic["reason"] = "office_path_too_long"
                raise ValueError("Office staging path exceeds MAX_PATH")
            shutil.copy2(target, source)
            command = _office_command(runtime, source, output, timeout)
            script_hash = hashlib.sha256(Path(command[2]).read_bytes()).hexdigest()

            def retained_paths(value):
                if isinstance(value, dict):
                    return {key: retained_paths(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [retained_paths(item) for item in value]
                if isinstance(value, str):
                    return value.replace(str(output), str(retained)).replace(
                        str(source), str(target)).replace(str(stage), str(retained))
                return value

            try:
                diagnostic["reason"] = "renderer_failed"
                result = run_office(
                    command, cwd=stage, env=_safe_environment(), capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=timeout + 30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    linux=getattr(settings, "PRODUCT_OFFICE_RENDERER", "word") == "libreoffice",
                )
                diagnostic["returncode"] = result.returncode
            finally:
                # Preserve partial output even when the child times out or fails.
                # This destination was exclusively created by this attempt.
                if output.is_dir():
                    shutil.copytree(output, retained, dirs_exist_ok=True)
                    report_path = retained / "render.json"
                    if report_path.is_file():
                        try:
                            report = json.loads(report_path.read_text(encoding="utf-8"))
                        except (UnicodeError, ValueError):
                            pass  # Preserve malformed output for review; it cannot pass.
                        else:
                            report_path.write_text(json.dumps(retained_paths(report), ensure_ascii=False),
                                                   encoding="utf-8")
            report_path = retained / "render.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("Invalid Office report")

            reviewed = retained / "reviewed.docx"
            if (result.returncode != 0 or report.get("rendered") is not True
                    or type(report.get("toc_count")) is not int or report["toc_count"] < 1
                    or type(report.get("page_count")) is not int or report["page_count"] < 1
                    or not reviewed.is_file()
                    or hashlib.sha256(Path(command[2]).read_bytes()).hexdigest() != script_hash):
                raise ValueError("Word field refresh did not pass")
            if getattr(settings, "PRODUCT_OFFICE_RENDERER", "word") == "libreoffice":
                from .product_rendering import _validated_outputs
                _validated_outputs(retained, report, hashlib.sha256(original).hexdigest(), "word")
                if (source.read_bytes() != original or target.read_bytes() != original
                        or report.get("toc_cached") is not True):
                    raise ValueError("LibreOffice input or TOC cache verification failed")
            cache = {"status": "completed", "renderer": report.get("renderer", "Microsoft Word"),
                     "toc_count": int(report["toc_count"]),
                     "page_count": report["page_count"], "office_render_script_sha256": script_hash,
                     "input_sha256": hashlib.sha256(original).hexdigest(),
                     "output_sha256": hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                     "visual_review": "not_run"}
            # Canonical preview records bind pages to the promoted DOCX, whose
            # hash differs from the pre-refresh input. Paths stay private and
            # are never rebuilt later from an untrusted render.json file.
            if "structural_pass" in report:
                from .product_rendering import _validated_outputs, _relative_evidence
                pdf, pdf_hash, pages, page_hashes, _, output_hash = _validated_outputs(
                    retained, report, cache["input_sha256"], "word")
                root = private_root().resolve()
                cache["preview"] = {
                    "status": "rendered", "verified": False, "visual_review": "not_run",
                    "docx_sha256": output_hash, "page_count": report["page_count"],
                    "pdf": _relative_evidence(root, pdf, pdf_hash),
                    "pages": [{"page": number, **_relative_evidence(root, page, checksum)}
                              for number, (page, checksum) in enumerate(zip(pages, page_hashes), 1)],
                }
            quality["output_sha256"] = hashlib.sha256(reviewed.read_bytes()).hexdigest()
            quality["word_field_cache"] = cache
            refreshed_quality = json.dumps(quality, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            diagnostic["reason"] = "staging_cleanup_failed"
        # Cleanup must succeed before either delivered file is changed.
        if stage.exists():
            raise OSError("Office staging cleanup left its owned directory")
        completed = {"status": "completed", "returncode": result.returncode,
                     "temporary_directory_removed": True}
        # No diagnostic I/O may fail after the delivered files are promoted.
        (retained / "refresh.json").write_text(json.dumps(completed), encoding="utf-8")
        diagnostic["reason"] = "promotion_failed"
        try:
            shutil.copy2(reviewed, target)
            quality_path.write_bytes(refreshed_quality)
        except OSError:
            target.write_bytes(original)
            quality_path.write_bytes(original_quality)
            raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError, subprocess.TimeoutExpired, DocumentError):
        try:
            (retained / "refresh.json").write_text(json.dumps(diagnostic), encoding="utf-8")
        except OSError:
            pass  # Existing renderer output still remains available for review.
        raise DocumentError("document_render_failed", diagnostic={"stage": "office_render", **diagnostic}) from None
    return {**cache, "cached_result": True}


def _normalize_word_layout(target, document):
    """Bind authored headings and empty TOC boundaries before Office refresh."""
    quality_path = target.with_suffix(".quality.json")
    original = target.read_bytes()
    original_quality = quality_path.read_bytes()
    try:
        quality = json.loads(original_quality)
        if quality["output_sha256"] != hashlib.sha256(original).hexdigest():
            raise ValueError("Generated output hash mismatch")
        bookmarks = quality["bookmark_map"]
        heading_names = [bookmarks[block["id"]] for block in document["blocks"] if block["type"] == "heading"]
        normalized, evidence = normalize_docx_layout(original, heading_names)
        quality["output_sha256"] = evidence["normalized_sha256"]
        quality["layout_normalization"] = evidence
        refreshed = json.dumps(quality, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        try:
            target.write_bytes(normalized)
            quality_path.write_bytes(refreshed)
        except OSError:
            target.write_bytes(original)
            quality_path.write_bytes(original_quality)
            raise
        return evidence
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        raise DocumentError("document_validation_failed") from None


def _diagram_sources(document, generator, *, draft=False, quality_issues=None):
    from .product_generation_policy import document_generation_only
    if generator is None:
        raise DocumentError("diagram_generation_required")
    try:
        diagrams = generator(document)
        if draft:
            _mark_pending_figures(document)
        findings = []
        diagrams = validate_diagram_batch({"diagrams": diagrams},
                               [block for block in document["blocks"] if block["type"] == "figure"],
                               diagram_evidence_blocks(document["blocks"]), draft=draft, quality_issues=findings,
                               verify_content=not document_generation_only(document))
        apply_diagram_descriptions(document, diagrams)
        validate_document_requirements(document, allow_pending=draft)
        if findings:
            if quality_issues is not None:
                quality_issues.extend(findings)
        return diagrams
    except (ValueError, KeyError, TypeError):
        raise DocumentError("diagram_generation_invalid") from None


def _mark_pending_figures(document):
    pending = {item["figure_id"]: item for item in document.get("diagram_pending", [])}
    for index, block in enumerate(document["blocks"]):
        if block.get("type") == "figure" and block["id"] in pending:
            notice = f"图表待补：{block['caption']}。生成或渲染未完成，当前草稿未包含此图，须补图并人工复核。"
            document["blocks"][index] = {"id": block["id"] + "_PENDING", "type": "paragraph", "text": notice,
                "source_ids": block.get("source_ids", ["SINPUT"]), "requirement_ids": block.get("requirement_ids", [])}
            document["pending"].append({"id": "PEND_" + block["id"], "text": notice})


def _render_one_diagram(directory, document, figure, source):
    # The existing renderer owns bitmap reuse and network/syntax checks.
    with tempfile.TemporaryDirectory(prefix="mermaid-", dir=directory) as temporary:
        source_path = Path(temporary) / "input.json"
        content_path = confined(directory, "single-diagram.json")
        content_path.write_text(json.dumps({**document, "blocks": [figure]}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        source_path.write_text(json.dumps({"diagrams": [source]}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        environment = _safe_environment()
        environment["PORTAL_CHROMIUM_PATH"] = str(_mermaid_chromium())
        try:
            result = subprocess.run([str(_mermaid_runtime()), str(PACK.parent / "mermaid-runtime" / "render.mjs"),
                str(content_path), str(source_path)], cwd=directory, env=environment, capture_output=True,
                timeout=int(getattr(settings, "PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS", 300)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode != 0:
                raise DocumentError("diagram_render_failed", diagnostic=_diagram_failure_diagnostic(result))
            evidence = _diagram_evidence(result.stdout, 1)
            actual = evidence["figures"][0]
            image = confined(directory, figure["path"])
            if (actual["figure_id"] != figure["id"] or not image.is_file()
                    or file_hash(image) != actual["imageSha256"]
                    or hashlib.sha256(source["source"].encode()).hexdigest() != actual["sourceSha256"]):
                raise DocumentError("diagram_render_failed")
            return evidence
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render",
                "reason": "process_timeout" if isinstance(error, subprocess.TimeoutExpired) else "runtime_io_failed"}) from None
        finally:
            content_path.unlink(missing_ok=True)


def _render_draft_diagrams(document, generator, directory, step_runner=None):
    from .product_steps import StepRetryPending
    planned = len([block for block in document["blocks"] if block["type"] == "figure"])
    findings = []
    sources = _diagram_sources(document, generator, draft=True, quality_issues=findings)
    figures = {block["id"]: block for block in document["blocks"] if block["type"] == "figure"}
    output = []
    rendered_count = 0
    runtime = preflight_document_rendering(draft=True)
    for original_source in sources:
        figure = figures[original_source["figure_id"]]
        evidence_ids = set(original_source["evidence_block_ids"])
        paragraphs = [block for block in diagram_evidence_blocks(document["blocks"])
                      if block["id"] in evidence_ids]
        binding = {"figure": deepcopy(figure), "source": original_source,
                   "runtime": runtime, "contract": diagram_contract_hash()}
        def valid(evidence, selected_source):
            try:
                if len(evidence["figures"]) != 1:
                    return False
                record = evidence["figures"][0]
                if (record["figure_id"] != figure["id"]
                        or record["sourceSha256"] != hashlib.sha256(selected_source["source"].encode()).hexdigest()
                        or file_hash(confined(directory, figure["path"])) != record["imageSha256"]):
                    return False
                apply_diagram_layout(deepcopy(document), evidence, directory)
                return True
            except (OSError, KeyError, TypeError, ValueError):
                return False
        def selected_valid(selected):
            try:
                if (set(selected) != {"source", "evidence", "corrected"}
                        or type(selected["corrected"]) is not bool
                        or (not selected["corrected"] and selected["source"] != original_source)):
                    return False
                if selected["corrected"]:
                    from .product_generation_policy import document_generation_only
                    validate_diagram_batch({"diagrams": [selected["source"]]}, [figure], paragraphs, draft=False,
                                           verify_content=not document_generation_only(document))
                return valid(selected["evidence"], selected["source"])
            except (ValueError, KeyError, TypeError):
                return False
        base_key = f'diagram_render:{document["family"]}:{figure["id"]}'
        def render_selected():
            source = original_source
            key = base_key
            render_binding = {"figure": deepcopy(figure),
                "source_sha256": hashlib.sha256(source["source"].encode()).hexdigest(),
                "runtime": runtime, "contract": binding["contract"]}
            def operation():
                if runtime.get("mermaid", {}).get("status") == "unavailable":
                    raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render", "reason": runtime["mermaid"]["reason"]})
                return _render_one_diagram(directory, document, figure, source)
            try:
                evidence = step_runner(key, render_binding, operation,
                    lambda value: valid(value, source)) if step_runner else operation()
                corrected = False
            except (DocumentError, StepRetryPending) as rejected:
                failure = getattr(rejected, "diagnostic", {}) or getattr(rejected.__cause__, "diagnostic", {})
                reason = failure.get("reason", "render_failed")
                if reason not in {"diagram_layout_unreadable", "diagram_parse_or_anchor_failed"}:
                    raise
                # One real-render correction uses the existing guarded model
                # callback and budget; never shrink fonts or invent a substitute.
                repair = {"family": document["family"], "metadata": document["metadata"],
                    "requirements": document.get("requirements", []),
                    "blocks": [*deepcopy(paragraphs), deepcopy(figure)],
                    "diagram_render_feedback": {"figure_id": figure["id"], "reason": reason,
                        "previous_source": source["source"]}}
                try:
                    from .product_generation_policy import document_generation_only
                    revised = validate_diagram_batch({"diagrams": generator(repair)}, [figure], paragraphs,
                        draft=False, verify_content=not document_generation_only(document))
                except (ValueError, KeyError, TypeError):
                    raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render",
                        "reason": "render_correction_invalid"}) from None
                source = revised[0]
                apply_diagram_descriptions(document, revised)
                render_binding = {"figure": deepcopy(figure), "source_sha256": hashlib.sha256(source["source"].encode()).hexdigest(),
                           "runtime": runtime, "contract": binding["contract"], "render_correction": reason}
                key += ":correction"
                evidence = step_runner(key, render_binding, operation,
                    lambda value: valid(value, source)) if step_runner else operation()
                corrected = True
            return {"source": source, "evidence": evidence, "corrected": corrected}
        key = base_key + ":selected"
        try:
            # Persist the accepted selection as one resumable step. A successful
            # redraw must not revisit its failed predecessor after Office retries.
            selected = step_runner(key, binding, render_selected, selected_valid) if step_runner else render_selected()
            if not selected_valid(selected):
                raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render", "reason": "reading_unit_verification_failed"})
            source, evidence = selected["source"], selected["evidence"]
            apply_diagram_descriptions(document, [source])
            if selected["corrected"]:
                findings[:] = [issue for issue in findings if issue.get("figure_id") != figure["id"]]
            units = apply_diagram_layout(document, evidence, directory) or [{"id": figure["id"],
                "image_sha256": evidence["figures"][0]["imageSha256"]}]
            output.extend({**unit, "source_sha256": evidence["figures"][0]["sourceSha256"],
                           "evidence_block_ids": source["evidence_block_ids"]} for unit in units)
            rendered_count += 1
        except (DocumentError, StepRetryPending) as error:
            code = error.cause_code if isinstance(error, StepRetryPending) else error.code
            if code not in {"diagram_render_failed", "document_validation_failed"}:
                raise
            document.setdefault("diagram_pending", []).append({"figure_id": figure["id"], "error_code": code,
                "stage": "diagram_render", "reason": getattr(error, "diagnostic", {}).get("reason", "render_failed"), "step_key": key})
    _mark_pending_figures(document)
    pending = document.get("diagram_pending", [])
    from .product_worker import _bounded_quality_issues
    return {"status": "pending" if pending else "completed", "planned_count": planned, "rendered": rendered_count,
        "figure_count": len(output), "pending_count": len(pending), "pending_figures": pending,
        "figures": output, "source_persisted": False, "contract_sha256": diagram_contract_hash(),
        "source_scope": "authored_chapter_blocks", "semantic_review": "human_review_required",
        "quality_issue_count": len(findings) + len(pending), "quality_issues": _bounded_quality_issues(findings),
        "full_document_human_review_required": True}


def _render_formal_diagrams(document, diagram_generator, directory, content_path, structural, diagram_progress):
    diagram_issues = []
    sources = _diagram_sources(document, diagram_generator, draft=False, quality_issues=diagram_issues)
    content_path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    # Source is confined to owned private temporary input, even on renderer failure.
    with tempfile.TemporaryDirectory(prefix="mermaid-", dir=directory) as temporary:
        source_path = Path(temporary) / "input.json"
        source_path.write_text(json.dumps({"diagrams": sources}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        diagram_environment = _safe_environment()
        diagram_environment["PORTAL_CHROMIUM_PATH"] = str(_mermaid_chromium())
        diagrams = subprocess.run([str(_mermaid_runtime()), str(PACK.parent / "mermaid-runtime" / "render.mjs"),
                                  str(content_path), str(source_path)],
                                 cwd=directory, env=diagram_environment, capture_output=True,
                                 timeout=int(getattr(settings, "PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS", 300)),
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if diagrams.returncode != 0:
        raise DocumentError("diagram_render_failed", diagnostic=_diagram_failure_diagnostic(diagrams))
    diagram_evidence = _diagram_evidence(diagrams.stdout, structural["figure_count"])
    rendered = {item["figure_id"]: item for item in diagram_evidence["figures"]}
    planned = {block["id"]: block for block in document["blocks"] if block["type"] == "figure"}
    if set(rendered) != set(planned):
        raise DocumentError("diagram_render_failed")
    for item in sources:
        actual = rendered[item["figure_id"]]
        image_path = (directory / planned[item["figure_id"]]["path"]).resolve()
        if (not image_path.is_relative_to(directory) or not image_path.is_file()
                or hashlib.sha256(image_path.read_bytes()).hexdigest() != actual["imageSha256"]
                or hashlib.sha256(item["source"].encode()).hexdigest() != actual["sourceSha256"]):
            raise DocumentError("diagram_render_failed")
    try:
        units = apply_diagram_layout(document, diagram_evidence, directory)
    except (OSError, ValueError, KeyError, TypeError):
        raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render", "reason": "reading_unit_verification_failed"}) from None
    source_records = {item["figure_id"]: item for item in sources}
    unit_records = {item["id"]: item for item in units}
    records = []
    for figure in (block for block in document["blocks"] if block["type"] == "figure"):
        original_id = re.sub(r"_PANEL_\d+$", "", figure["id"])
        source = source_records[original_id]
        records.append({**unit_records.get(figure["id"], {"id": figure["id"], "image_sha256": rendered[original_id]["imageSha256"]}),
                        "source_sha256": rendered[original_id]["sourceSha256"],
                        "evidence_block_ids": source["evidence_block_ids"]})
    content_path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    diagram_evidence = {**diagram_evidence,
                        "contract_sha256": diagram_contract_hash(), "source_scope": "authored_chapter_blocks",
                        "semantic_review": "human_review_required",
                        "figure_count": len(records), "figures": records}
    if diagram_issues:
        from .product_worker import _bounded_quality_issues
        diagram_evidence.update(quality_issues=_bounded_quality_issues(diagram_issues),
                                quality_issue_count=len(diagram_issues), full_document_human_review_required=True)
    if diagram_progress:
        diagram_progress("completed", figure_count=structural["figure_count"])
    return diagram_evidence


def _publish_render_snapshot(root, directory, task, filename, document, evidence):
    """Publish all referenced assets together; cache paths remain private."""
    try:
        published = confined(root, f"{task.pk}/artifacts/{uuid.uuid4().hex}")
        published.mkdir(parents=True, exist_ok=False)
        promoted = confined(published, filename)
        source = confined(directory, filename)
        atomic_write(promoted, source.read_bytes())
        content_bytes = confined(directory, "content.json").read_bytes()
        if json.loads(content_bytes) != document:
            raise ValueError
        atomic_write(confined(published, "content.json"), content_bytes)
        expected = {item["id"]: item["image_sha256"] for item in evidence["diagram_generation"]["figures"]}
        for figure in (block for block in document["blocks"] if block["type"] == "figure"):
            image = confined(directory, figure["path"]).read_bytes()
            if hashlib.sha256(image).hexdigest() != expected[figure["id"]]:
                raise ValueError
            destination = confined(published, figure["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(destination, image)
        field_refresh = deepcopy(evidence["word_field_cache"])
        preview = field_refresh.get("preview")
        if preview:
            for number, item in enumerate([preview["pdf"], *preview["pages"]]):
                original = confined(root, item["path"]).read_bytes()
                if hashlib.sha256(original).hexdigest() != item["sha256"]:
                    raise ValueError
                name = "document.pdf" if number == 0 else f"page-{number:03d}.png"
                destination = confined(published, f"office-preview/{name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(destination, original)
                item["path"] = destination.relative_to(root).as_posix()
        quality = json.loads(source.with_suffix(".quality.json").read_bytes())
        if "word_field_cache" in quality:
            quality["word_field_cache"] = field_refresh
        atomic_write(promoted.with_suffix(".quality.json"), json.dumps(
            quality, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())
        evidence["word_field_cache"] = field_refresh
        return promoted
    except (OSError, ValueError, KeyError, TypeError):
        raise DocumentError("document_render_failed", diagnostic={"stage": "artifact_publish", "reason": "snapshot_verification_failed"}) from None


def _render_document(task, chapters, manifest, runtime, document, filename, status, business_approval, extra_evidence=None,
                     *, draft=False, diagram_generator=None, diagram_progress=None, workspace_key=None, diagram_step=None):
    preflight = preflight_document_rendering(draft=draft)
    document = deepcopy(document)
    root = private_root().resolve()
    # A caller key identifies the job, while a second hash binds all inputs and
    # implementations. Different revisions never share mutable render output.
    binding = canonical_hash({"document": document, "draft": draft, "runtime": preflight,
                              "manifest": manifest, "filename": filename, "contract": diagram_contract_hash()})
    if workspace_key is not None:
        if not isinstance(workspace_key, str) or not workspace_key or len(workspace_key) > 500:
            raise DocumentError("document_render_failed", diagnostic={"stage": "document_render", "reason": "workspace_key_invalid"})
        workspace_id = canonical_hash({"key": workspace_key, "binding": binding})
        directory = confined(root, f"{task.pk}/render-workspaces/{workspace_id}")
    else:
        directory = confined(root, f"{task.pk}/artifacts/{uuid.uuid4().hex}")
    if not directory.is_relative_to(root):
        raise DocumentError("template_unavailable")
    directory.mkdir(parents=True, exist_ok=workspace_key is not None)
    content_path = confined(directory, "content.json")
    target = confined(directory, filename)
    confined(directory, target.with_suffix(".quality.json").name)
    structural = validate_document_requirements(document)
    render_stage = "diagram_render"
    try:
        if diagram_progress:
            diagram_progress("running", figure_count=structural["figure_count"])
        try:
            if draft or structural["figure_count"] == 0:
                diagram_evidence = _render_draft_diagrams(document,
                    diagram_generator if structural["figure_count"] else lambda _: [], directory, diagram_step)
                structural = validate_document_requirements(document, allow_pending=True)
                document.pop("diagram_pending", None)
                content_path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                if diagram_progress:
                    diagram_progress("pending" if diagram_evidence["pending_count"] else "completed",
                        figure_count=diagram_evidence["rendered"], pending_count=diagram_evidence["pending_count"])
            else:
                diagram_evidence = _render_formal_diagrams(document, diagram_generator, directory, content_path, structural, diagram_progress)
                structural = validate_document_requirements(document)
        except Exception:
            if diagram_progress:
                diagram_progress("failed", figure_count=structural["figure_count"])
            raise
        stage_binding = canonical_hash({"workspace": binding, "content": document, "diagrams": diagram_evidence})
        render_stage = "docx_assembly"
        cache = StageCache(directory, stage_binding)
        stage_files = [filename, target.with_suffix(".quality.json").name]
        office = cache.load("office", stage_files)
        if office:
            layout = office["layout"]
            field_refresh = office["field_refresh"]
            # Preview files are evidence, too. Missing or changed evidence
            # reruns Office using the still cached normalized input.
            preview = field_refresh.get("preview")
            if preview:
                try:
                    for item in [preview["pdf"], *preview["pages"]]:
                        if file_hash(confined(root, item["path"])) != item["sha256"]:
                            raise ValueError
                except (OSError, ValueError, KeyError, TypeError):
                    office = None
        if not office:
            normalized = cache.load("normalized", stage_files)
            if normalized:
                layout = normalized["layout"]
            else:
                assembled = cache.load("assembled", stage_files)
                if assembled is None:
                    # A stale or corrupted checkpoint is a miss. The frozen
                    # assembler requires new output files, so remove only the
                    # owned staging outputs before rebuilding them.
                    for name in stage_files:
                        confined(directory, name).unlink(missing_ok=True)
                    result = subprocess.run([str(runtime), "-B", str(PACK / "scripts" / "artifacts.py"), "docx", str(content_path), str(target)],
                                            cwd=directory, env=_safe_environment(), capture_output=True,
                                            timeout=int(getattr(settings, "PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS", 300)),
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if result.returncode != 0 or not target.is_file():
                        raise DocumentError("document_validation_failed", diagnostic={"stage": "docx_assembly", "reason": "assembly_failed", "returncode": result.returncode})
                    cache.save("assembled", stage_files, {})
                layout = _normalize_word_layout(target, document)
                cache.save("normalized", stage_files, {"layout": layout})
            retained_name = "word-field-refresh" if workspace_key is None else "word-field-refresh-" + uuid.uuid4().hex
            render_stage = "office_render"
            field_refresh = _refresh_word_field_cache(target, runtime, directory, retained_name=retained_name)
            cache.save("office", stage_files, {"layout": layout, "field_refresh": field_refresh})
        structural = inspect_docx_requirements(target, structural)
    except (OSError, subprocess.TimeoutExpired) as error:
        reason = "process_timeout" if isinstance(error, subprocess.TimeoutExpired) else "runtime_io_failed"
        raise DocumentError("document_render_failed", diagnostic={"stage": render_stage, "reason": reason}) from None
    template = next(entry for entry in manifest["files"] if entry["path"] == f"assets/{document['family']}/template.docx")
    evidence = {"status": status, "verified": False,
                "structural_generation": "completed", "office_render": field_refresh["status"],
                "word_field_cache": field_refresh, "visual_review": "not_run", "business_approval": business_approval,
                "layout_normalization": layout,
                "manifest_sha256": hashlib.sha256((PACK / "manifest.json").read_bytes()).hexdigest(),
                "chapter_hashes": {chapter.payload["chapter_id"]: chapter.sha256 for chapter in chapters},
                "document_structure": structural,
                "diagram_generation": diagram_evidence}
    evidence.update(extra_evidence or {})
    evidence["render_checkpoint"] = {"binding_sha256": binding, "stage_binding_sha256": stage_binding,
                                     "office_reused": bool(office)}
    if workspace_key is not None:
        # Published files are immutable snapshots of the resumable workspace.
        target = _publish_render_snapshot(root, directory, task, filename, document, evidence)
    final_content = confined(target.parent, "content.json")
    return {"path": target.relative_to(root).as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "content_path": final_content.relative_to(root).as_posix(), "content_sha256": file_hash(final_content),
            "template_hash": template["sha256"], "render_evidence": evidence}


def render_report_draft(task, input_revision, blueprint, chapters, family, *, draft=False, document=None, diagram_generator=None, diagram_progress=None, workspace_key=None, diagram_step=None):
    from .product_blueprint_knowledge import blueprint_knowledge_status
    paragraphs = [paragraph for chapter in chapters for paragraph in chapter.payload.get("paragraphs", [])]
    if not draft and has_repeated_filler(paragraphs):
        raise DocumentError("repeated_body_filler")
    if not draft and family == "feasibility" and any(unsupported_financial_conclusion(paragraph) for paragraph in paragraphs):
        raise DocumentError("investment_evidence_required")
    manifest = frozen_pack(family)
    runtime = _document_runtime()
    document = document if document is not None else content_document(task, input_revision, blueprint, chapters, family, draft=draft)
    return _render_document(task, chapters, manifest, runtime, document, "draft.docx", "draft_unverified", "blocked",
                            {"knowledge": blueprint_knowledge_status(input_revision.payload)},
                            draft=draft, diagram_generator=diagram_generator, diagram_progress=diagram_progress, workspace_key=workspace_key, diagram_step=diagram_step)


def render_draft(task, input_revision, blueprint, chapters, **diagram_options):
    return render_report_draft(task, input_revision, blueprint, chapters, "technical-solution", **diagram_options)


def _template_approval(manifest):
    approval = getattr(settings, "PRODUCT_TEMPLATE_APPROVAL", None)
    template = next((entry for entry in manifest["files"] if entry["path"] == "assets/technical-solution/template.docx"), None)
    if not isinstance(approval, dict) or template is None:
        raise DocumentError("template_approval_required")
    template_hash = approval.get("template_hash")
    approval_ref = approval.get("approval_ref")
    organization = approval.get("organization")
    if (not isinstance(template_hash, str) or len(template_hash) != 64
            or any(character not in "0123456789abcdef" for character in template_hash.lower())
            or template_hash.lower() != template["sha256"]):
        raise DocumentError("template_approval_required")
    for value in (approval_ref, organization):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200 or any(ord(character) < 32 for character in value):
            raise DocumentError("template_approval_required")
    return {"template_hash": template["sha256"], "approval_ref": approval_ref.strip(), "organization": organization.strip()}


def _candidate_document(task, input_revision, blueprint, chapters, approval):
    if blueprint.payload.get("missing") or blueprint.payload.get("conflicts") or input_revision.payload.get("issues"):
        raise DocumentError("candidate_content_unresolved")
    document = content_document(task, input_revision, blueprint, chapters)
    document["metadata"].update(subtitle="技术方案", organization=approval["organization"], status="reviewed")
    document["sources"].append({"id": "STEMPLATE", "text": f"模板批准引用={approval['approval_ref']}；组织={approval['organization']}"})
    document["pending"] = []
    document["blocks"] = [block for block in document["blocks"]
                          if block["id"] != "DRAFT_NOTICE" and block["id"] != "PENDING_HEADING" and not block["id"].startswith("PENDING_TEXT")]
    first_heading = next((index for index, block in enumerate(document["blocks"]) if block["type"] == "heading"), -1)
    document["blocks"].insert(first_heading + 1, {
        "id": "ORGANIZATION", "type": "paragraph", "text": f"编制单位：{approval['organization']}",
        "source_ids": ["STEMPLATE"], "requirement_ids": [],
    })
    for block in document["blocks"]:
        if block["id"] == "INPUT_TABLE":
            block["caption"] = "表1 输入设备清单"
    return document


def render_candidate(task, input_revision, blueprint, chapters, **diagram_options):
    from .product_blueprint_knowledge import blueprint_knowledge_status
    manifest = frozen_pack()
    approval = _template_approval(manifest)
    runtime = _document_runtime()
    document = _candidate_document(task, input_revision, blueprint, chapters, approval)
    approval_hash = hashlib.sha256(json.dumps(
        approval, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return _render_document(
        task, chapters, manifest, runtime, document, "candidate.docx", "candidate_unverified", "pending",
        {"knowledge": blueprint_knowledge_status(input_revision.payload), "template_approval": approval, "template_approval_hash": approval_hash,
         "template_approval_hash_method": "sha256-canonical-json-v1"},
        **diagram_options,
    )
