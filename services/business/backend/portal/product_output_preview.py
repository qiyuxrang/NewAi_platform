"""Canonical draft preview metadata, independent of candidate verification."""

from pathlib import PurePosixPath
import re


def _record(value, suffix):
    if not isinstance(value, dict):
        return False
    path, checksum = value.get("path"), value.get("sha256")
    if (not isinstance(path, str) or not path or len(path) > 4000
            or any(character in path for character in ("\\", "\x00", ":"))
            or not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None):
        return False
    relative = PurePosixPath(path)
    return not relative.is_absolute() and ".." not in relative.parts and relative.suffix.lower() == suffix


def draft_preview_evidence(artifact):
    """Return trusted stored records only; old drafts require regeneration."""
    evidence = artifact.render_evidence
    if not isinstance(evidence, dict) or evidence.get("kind") != "draft":
        return None
    if artifact.family == "presentation":
        preview = evidence.get("office_render_evidence")
        if (not isinstance(preview, dict) or preview.get("pptx_sha256") != artifact.sha256
                or preview.get("generation_sha256") != artifact.sha256
                or preview.get("generation") != {"path": artifact.path, "sha256": artifact.sha256}):
            return None
    elif artifact.family in {"technical-solution", "feasibility"}:
        cache = evidence.get("word_field_cache")
        if not isinstance(cache, dict) or cache.get("status") != "completed" or cache.get("output_sha256") != artifact.sha256:
            return None
        preview = cache.get("preview")
        if not isinstance(preview, dict) or preview.get("docx_sha256") != artifact.sha256:
            return None
    else:
        return None
    pages, count = preview.get("pages"), preview.get("page_count")
    if (preview.get("status") != "rendered" or preview.get("verified") is not False
            or preview.get("visual_review") != "not_run" or type(count) is not int
            or not 1 <= count <= 10000 or not isinstance(pages, list) or len(pages) != count
            or not _record(preview.get("pdf"), ".pdf")
            or any(not _record(page, ".png") or type(page.get("page")) is not int or page["page"] != number
                   for number, page in enumerate(pages, 1))):
        return None
    return {"page_count": count, "pdf": preview["pdf"], "pages": pages}


def public_draft_preview(artifact, *, current):
    evidence = draft_preview_evidence(artifact) if current else None
    available = evidence is not None
    return {"has_preview": available, "page_count": evidence["page_count"] if available else 0,
            "preview_url": f"/api/product/outputs/{artifact.pk}/preview/" if available else None}
