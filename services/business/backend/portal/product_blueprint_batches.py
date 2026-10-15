"""Bounded guide-scope responses; final approval still uses the complete blueprint."""

from copy import deepcopy

from .product_service import ProductError, validate_blueprint


def _error():
    raise ProductError("invalid_blueprint", "指南适用性批次字段、范围或取舍无效。")


def _headings(sections):
    if not isinstance(sections, list):
        _error()
    seen = set()
    for section in sections:
        if (not isinstance(section, dict) or set(section) != {"id", "title", "applicability"}
                or any(not isinstance(section[key], str) for key in section)
                or not section["id"].strip() or not section["title"].strip()
                or section["id"] in seen):
            _error()
        seen.add(section["id"])
    return sections


def scope_batches(catalog, max_sections=8):
    """Keep chapter ownership and catalog order; appendices never share a chapter batch."""
    if (type(max_sections) is not int or not 1 <= max_sections <= 8
            or not isinstance(catalog, dict)
            or set(catalog) != {"asset_sha256", "title", "chapters", "appendices"}
            or not isinstance(catalog["chapters"], list)):
        _error()
    groups = []
    for chapter in catalog["chapters"]:
        if (not isinstance(chapter, dict) or set(chapter) != {"id", "title", "sections"}
                or any(not isinstance(chapter[key], str) or not chapter[key].strip() for key in ("id", "title"))):
            _error()
        groups.append(("chapter", chapter["id"], chapter["title"], _headings(chapter["sections"])))
    groups.append(("appendices", "", "附录", _headings(catalog["appendices"])))
    ids = [section["id"] for _, _, _, sections in groups for section in sections]
    if not ids or len(ids) != len(set(ids)):
        _error()
    return [{"kind": kind, "chapter_id": chapter_id, "chapter_title": title,
             "sections": deepcopy(sections[index:index + max_sections])}
            for kind, chapter_id, title, sections in groups
            for index in range(0, len(sections), max_sections)]


def _batch_sections(batch):
    if isinstance(batch, dict) and batch.get("kind") == "compact":
        from . import product_feasibility

        if (type(batch.get("start_index")) is not int
                or batch not in compact_batches(product_feasibility.catalog())):
            _error()
        return batch["sections"]
    if (not isinstance(batch, dict)
            or set(batch) != {"kind", "chapter_id", "chapter_title", "sections"}
            or batch["kind"] not in ("chapter", "appendices")
            or not isinstance(batch["chapter_id"], str)
            or not isinstance(batch["chapter_title"], str)
            or not batch["chapter_title"].strip()
            or (batch["kind"] == "chapter" and not batch["chapter_id"].strip())
            or (batch["kind"] == "appendices" and batch["chapter_id"] != "")):
        _error()
    sections = _headings(batch["sections"])
    if not 1 <= len(sections) <= 8:
        _error()
    return sections


def compact_batches(catalog):
    """Pack consecutive real guide nodes, retaining chapter ownership across boundaries."""
    nodes = scope_batches(catalog, 1)
    batches = []
    for start in range(0, len(nodes), 48):
        selected = nodes[start:start + 48]
        groups = []
        for node in selected:
            owner = {key: node[key] for key in ("kind", "chapter_id", "chapter_title")}
            if not groups or any(groups[-1][key] != value for key, value in owner.items()):
                groups.append({**owner, "section_ids": []})
            groups[-1]["section_ids"].append(node["sections"][0]["id"])
        batches.append({"kind": "compact", "chapter_id": "", "chapter_title": "指南适用性",
                        "asset_sha256": catalog["asset_sha256"], "start_index": start,
                        "sections": [node["sections"][0] for node in selected], "groups": groups})
    return batches


def compact_scope_request(batch, base):
    """Only alias-bearing inputs; the server retains canonical guide/chapter identities."""
    sections = _batch_sections(batch)
    if batch["kind"] != "compact":
        _error()
    groups = [{"id": f"G{index + 1}", **{key: group[key] for key in ("kind", "chapter_id", "chapter_title")}}
              for index, group in enumerate(batch["groups"])]
    owners = {section_id: group["id"] for group, source in zip(groups, batch["groups"])
              for section_id in source["section_ids"]}
    return {"asset_sha256": batch["asset_sha256"], "groups": groups,
            "sections": [{"id": f"S{batch['start_index'] + index + 1}", "group": owners[section["id"]],
                          "title": section["title"], "applicability": section["applicability"]}
                         for index, section in enumerate(sections)],
            "chapters": [{"id": f"F{index + 1}", "title": chapter["title"], "scope": chapter["scope"]}
                         for index, chapter in enumerate(chapter for chapter in base["chapters"]
                                                         if chapter.get("family") == "feasibility")]}


def validate_compact_scope(result, batch, base):
    """Expand bounded aliases and shared reasons before the canonical scope validation."""
    sections = _batch_sections(batch)
    if (batch["kind"] != "compact" or not isinstance(result, dict)
            or set(result) != {"reasons", "decisions", "missing", "conflicts"}
            or not isinstance(result["reasons"], list) or not 1 <= len(result["reasons"]) <= len(sections)
            or not isinstance(result["decisions"], list)):
        _error()
    reasons = {}
    allowed_reasons = {f"R{index + 1}" for index in range(len(sections))}
    for reason in result["reasons"]:
        if (not isinstance(reason, dict) or set(reason) != {"id", "text"}
                or not isinstance(reason["id"], str) or reason["id"] not in allowed_reasons
                or reason["id"] in reasons or not isinstance(reason["text"], str)
                or not reason["text"].strip() or len(reason["text"]) > 120):
            _error()
        reasons[reason["id"]] = reason["text"].strip()
    missing, conflicts = _notes(result["missing"]), _notes(result["conflicts"])
    if (sum(len(reason["text"]) for reason in result["reasons"]) > 1200
            or sum(len(value) for value in result["missing"] + result["conflicts"]) > 800):
        _error()
    aliases = {f"S{batch['start_index'] + index + 1}": section["id"] for index, section in enumerate(sections)}
    chapters = {f"F{index + 1}": chapter["id"] for index, chapter in enumerate(
        chapter for chapter in base["chapters"] if chapter.get("family") == "feasibility")}
    statuses = {"I": "include", "P": "pending", "N": "not_applicable"}
    entries = []
    for row in result["decisions"]:
        if (not isinstance(row, list) or len(row) != 4
                or not isinstance(row[0], str) or row[0] not in aliases
                or not isinstance(row[1], str) or row[1] not in statuses
                or not isinstance(row[2], list)
                or any(not isinstance(value, str) or value not in chapters for value in row[2])
                or not isinstance(row[3], str) or row[3] not in reasons):
            _error()
        entries.append({"section_id": aliases[row[0]], "status": statuses[row[1]],
                        "chapter_ids": [chapters[value] for value in row[2]], "reason": reasons[row[3]]})
    return validate_scope_batch({"sections": entries, "missing": missing, "conflicts": conflicts}, batch, base)


def _notes(values, max_items=8):
    if (not isinstance(values, list) or len(values) > max_items
            or any(not isinstance(value, str) or not value.strip() or len(value) > 200 for value in values)):
        _error()
    return list(dict.fromkeys(value.strip() for value in values))


def validate_scope_batch(result, batch, blueprint):
    """Reject incomplete decisions; only normalize text and explicit pending reasons."""
    sections = _batch_sections(batch)
    if (not isinstance(result, dict) or set(result) != {"sections", "missing", "conflicts"}
            or not isinstance(result["sections"], list)):
        _error()
    # Raw replies allow eight notes; normalized replies also retain every pending item.
    compact = batch["kind"] == "compact"
    max_missing = 8 + len(sections) if compact else 16
    missing, conflicts = _notes(result["missing"], max_missing), _notes(result["conflicts"])
    allowed = {section["id"] for section in sections}
    chapter_ids = {chapter["id"] for chapter in blueprint.get("chapters", [])
                   if chapter.get("family") == "feasibility"}
    checked = {}
    for entry in result["sections"]:
        if (not isinstance(entry, dict) or set(entry) != {"section_id", "status", "chapter_ids", "reason"}
                or not isinstance(entry["section_id"], str) or entry["section_id"] not in allowed
                or entry["section_id"] in checked
                or not isinstance(entry["status"], str) or entry["status"] not in ("include", "pending", "not_applicable")
                or not isinstance(entry["reason"], str) or len(entry["reason"]) > (120 if compact else 160)
                or not isinstance(entry["chapter_ids"], list)
                or any(not isinstance(value, str) or value not in chapter_ids for value in entry["chapter_ids"])
                or len(entry["chapter_ids"]) != len(set(entry["chapter_ids"]))):
            _error()
        status, reason, mapped = entry["status"], entry["reason"].strip(), entry["chapter_ids"]
        if ((compact and not reason) or (status == "not_applicable" and (mapped or not reason))
                or (status != "not_applicable" and not mapped)
                or (status == "pending" and not reason)):
            _error()
        pending_note = f"{entry['section_id']}：{reason}"
        if status == "pending" and pending_note not in missing:
            missing.append(pending_note)
        checked[entry["section_id"]] = {**entry, "reason": reason, "chapter_ids": list(mapped)}
    if set(checked) != allowed:
        _error()
    return {"sections": [checked[section["id"]] for section in sections],
            "missing": _notes(missing, max_missing), "conflicts": conflicts}


def merge_scope_batches(base, catalog, batches, results):
    """Bind the real guide and re-run whole-plan rules across all batch boundaries."""
    from . import product_feasibility

    if (catalog != product_feasibility.catalog() or not isinstance(batches, list)
            or not isinstance(results, list) or len(batches) != len(results)):
        _error()
    if any(isinstance(batch, dict) and batch.get("kind") == "compact" for batch in batches):
        if batches != compact_batches(catalog):
            _error()
    else:
        expected = scope_batches(catalog, 1)
        expanded = [{**batch, "sections": [section]}
                    for batch in batches for section in _batch_sections(batch)]
        if expanded != expected:
            _error()
    payload = deepcopy(base)
    sections = []
    for batch, result in zip(batches, results):
        checked = validate_scope_batch(result, batch, base)
        sections.extend(checked["sections"])
        for field in ("missing", "conflicts"):
            payload[field] = list(dict.fromkeys([*payload[field], *checked[field]]))
    payload["feasibility_guide"] = {"asset_sha256": catalog["asset_sha256"], "sections": sections}
    return validate_blueprint(payload, {})
