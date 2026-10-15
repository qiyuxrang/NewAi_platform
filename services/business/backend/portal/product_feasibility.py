"""Versioned feasibility-guide planning and evidence-backed completeness scans."""

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path


_ASSET_PATH = Path(__file__).resolve().parent / "product_assets" / "feasibility_guide_requirements.json"
_ASSET_SHA256 = "1079308d4cc639f1f210046a2d516739cbf4a67aae3828a9985eec41d4d875aa"
_SOURCE_SHA256 = "1ffe2ace313aa4dc76e90ef9f2b91df6e1a2f0d3ef7896dfa9bb0ce2ab89be84"
_STATUSES = {"include", "pending", "not_applicable"}
_CHECK_STATUSES = {"covered", "partial", "not_seen", "not_applicable", "pending"}


def _error(detail, code="invalid_feasibility_guide"):
    from .product_service import ProductError
    raise ProductError(code, detail)


def _load_guide():
    try:
        raw = _ASSET_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != _ASSET_SHA256:
            _error("可研指南资产校验失败。", "feasibility_guide_unavailable")
        result = json.loads(raw)
        if (result.get("schema") != "yulin-feasibility-requirements-v1"
                or result.get("source_sha256") != _SOURCE_SHA256):
            _error("可研指南来源版本无效。", "feasibility_guide_unavailable")
        sections = _sections(result)
        ids = [section["id"] for section in sections]
        if (not sections or len(ids) != len(set(ids))
                or any(not isinstance(value, str) or not value.strip() for value in ids)
                or any(not isinstance(section.get("title"), str) or not section["title"].strip()
                       for section in sections)):
            _error("可研指南资产结构无效。", "feasibility_guide_unavailable")
        return result
    except (OSError, ValueError, TypeError, KeyError):
        _error("可研指南资产不可用。", "feasibility_guide_unavailable")


def _sections(asset):
    return [section for chapter in asset["chapters"]
            for section in ([chapter] if any(chapter.get(field) for field in (
                "content_elements", "writing_requirements", "other_requirements", "tables_figures", "table_figure_specs", "calculations")) else [])
            + chapter["sections"]] + asset.get("appendices", [])


def asset_hash():
    _load_guide()
    return _ASSET_SHA256


def catalog():
    """Compact stable identities for tailoring; full requirements are injected when writing."""
    asset = _load_guide()
    def heading(section):
        return {key: deepcopy(section.get(key, ""))
                for key in ("id", "title", "applicability")}
    return {
        "asset_sha256": _ASSET_SHA256,
        "title": asset.get("source_title", "可行性研究报告编制指南"),
        "chapters": [{"id": chapter["id"], "title": chapter["title"],
                      "sections": [heading(section) for section in _sections({"chapters": [chapter]})]}
                     for chapter in asset["chapters"]],
        "appendices": [heading(section) for section in asset.get("appendices", [])],
    }


def validate_plan(blueprint):
    """Normalize one approved disposition per section; old blueprints remain readable."""
    if "feasibility_guide" not in blueprint:
        return None
    plan = blueprint["feasibility_guide"]
    if (not isinstance(plan, dict) or set(plan) != {"asset_sha256", "sections"}
            or plan["asset_sha256"] != _ASSET_SHA256 or not isinstance(plan["sections"], list)):
        _error("可研指南版本或裁剪映射无效。")
    asset_sections = _sections(_load_guide())
    allowed = {section["id"] for section in asset_sections}
    chapter_ids = {chapter["id"] for chapter in blueprint.get("chapters", [])
                   if chapter.get("family") == "feasibility"}
    checked = {}
    for entry in plan["sections"]:
        if (not isinstance(entry, dict)
                or set(entry) != {"section_id", "status", "chapter_ids", "reason"}
                or not isinstance(entry["section_id"], str) or entry["section_id"] not in allowed
                or entry["section_id"] in checked or not isinstance(entry["status"], str)
                or entry["status"] not in _STATUSES
                or not isinstance(entry["chapter_ids"], list)
                or any(not isinstance(value, str) or value not in chapter_ids for value in entry["chapter_ids"])
                or len(entry["chapter_ids"]) != len(set(entry["chapter_ids"]))
                or not isinstance(entry["reason"], str) or len(entry["reason"]) > 2000):
            _error("可研指南裁剪条目无效、重复或指向非可研章节。")
        status, reason = entry["status"], entry["reason"].strip()
        if ((status == "not_applicable" and (entry["chapter_ids"] or not reason))
                or (status != "not_applicable" and not entry["chapter_ids"])
                or (status == "pending" and not reason)):
            _error("适用或待确认内容须映射章节；不适用和待确认内容须说明具体理由。")
        checked[entry["section_id"]] = {**entry, "reason": reason, "chapter_ids": list(entry["chapter_ids"])}
    if set(checked) != allowed:
        _error("可研蓝图必须逐项说明全部指南小节及附录的适用性。")
    by_id = {section["id"]: section for section in asset_sections}
    active = {key: entry for key, entry in checked.items() if entry["status"] != "not_applicable"}
    substantive = {key: entry for key, entry in active.items() if _requirements(by_id[key], by_id)}
    if not substantive or {value for entry in substantive.values() for value in entry["chapter_ids"]} != chapter_ids:
        _error("每个可研章节须对应至少一项实际适用的指南内容，不能全部裁剪或仅映射空目录。")
    for key, entry in active.items():
        if key not in substantive and not any(
                (child.startswith(key + ".") or by_id[child].get("parent_id") == key)
                and set(entry["chapter_ids"]) & set(child_entry["chapter_ids"])
                for child, child_entry in substantive.items()):
            _error("适用的结构目录须保留对应实际子节。")
    if any(entry["status"] == "pending" for entry in active.values()) and not blueprint.get("missing"):
        _error("待确认指南内容须同时保留蓝图缺项，供批准和人工核对。")
    return {"asset_sha256": _ASSET_SHA256,
            "sections": [checked[section["id"]] for section in asset_sections]}


def chapter_requirements(blueprint, chapter_id):
    plan = validate_plan(blueprint)
    if plan is None:
        return []
    selected = {entry["section_id"]: entry for entry in plan["sections"] if chapter_id in entry["chapter_ids"]}
    sections = _sections(_load_guide())
    by_id = {section["id"]: section for section in sections}
    return [{**{key: deepcopy(value) for key, value in section.items() if key != "source_text"},
             "inherited_sections": [{key: value for key, value in inherited.items() if key != "source_text"}
                                    for inherited in _inherited(section, by_id)],
             "approved_status": selected[section["id"]]["status"],
             "approved_reason": selected[section["id"]]["reason"]}
            for section in sections if section["id"] in selected]


def _inherited(section, sections, seen=()):
    if section["id"] in seen:
        _error("可研指南要求引用循环。", "feasibility_guide_unavailable")
    result = []
    for section_id in section.get("inherits_requirements_from", []):
        if section_id not in sections:
            _error("可研指南要求引用不存在。", "feasibility_guide_unavailable")
        inherited = sections[section_id]
        result.append(deepcopy(inherited))
        result.extend(_inherited(inherited, sections, (*seen, section["id"])))
    return result


def _numbered_parts(text):
    parts = [part.strip() for part in re.split(r"(?m)(?=^\s*\d+[．、]\s*)", text) if part.strip()]
    if len(parts) > 1 and not re.match(r"\d+[．、]", parts[0]):
        parts[1] = parts[0] + "\n" + parts[1]
        parts = parts[1:]
    return parts


def _requirements(section, sections=None):
    result = []
    source_blocks = "\n".join(section.get("content_elements", []) + section.get("writing_requirements", []))
    for field, prefix in (("content_elements", "E"), ("writing_requirements", "W"), ("other_requirements", "O"), ("tables_figures", "F"),
                          ("table_figure_specs", "T"), ("calculations", "C")):
        values = [part for value in section.get(field, [])
                  if not (field == "other_requirements" and isinstance(value, str)
                          and re.sub(r"\s+", "", value) in re.sub(r"\s+", "", source_blocks))
                  for part in (_numbered_parts(value) if isinstance(value, str) else [value])]
        for index, value in enumerate(values, 1):
            conditions = value.get("conditions", []) if isinstance(value, dict) else []
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
            if not isinstance(text, str) or not text.strip():
                _error("可研指南要求为空。", "feasibility_guide_unavailable")
            result.append({"id": f"{section['id']}:{prefix}{index}", "section_id": section["id"],
                           "kind": field, "requirement": text, "conditions": deepcopy(conditions)})
    if sections:
        for inherited in _inherited(section, sections):
            for atom in _requirements(inherited):
                result.append({**atom, "id": f"{section['id']}:from:{atom['id']}",
                               "section_id": section["id"], "inherited_from": inherited["id"]})
    return result


def _size(payload):
    # The worker supplies its exact correction-aware measure in production.
    return len(json.dumps(payload, ensure_ascii=False)) + 1800


def review_requests(payload, blueprint, chapters, measure=None):
    """Scan each applicable obligation against every assigned saved text fragment.

    A fragment may report not_seen, never whole-chapter absence. Only the reducer
    can identify missing content after the complete scan has finished.
    """
    plan = validate_plan(blueprint)
    if plan is None:
        return []
    measure = measure or _size
    contents = [getattr(chapter, "payload", chapter) for chapter in chapters]
    saved = {chapter["chapter_id"]: chapter for chapter in contents}
    sections = {section["id"]: section for section in _sections(_load_guide())}
    requests = []
    instruction = (
        "本批只审查guide_requirements的实质内容覆盖，事实与来源另有全文复核。逐项返回全部要求ID。"
        "covered必须由本批正文原文完整支持该条全部适用要点，不得凭标题、关键词或提到表号认定完成。"
        "公开检索和项目资料清单只辅助判断依据与缺项，不要求把内部检索操作写进正文。"
        "表图按适用内容和结构判断，不要求机械沿用指南表号或排版。"
        "本次在图形生成前审查；图形要求只核对正文已交代的节点、关系、流程和边界等绘图依据，"
        "不得因正文尚无图片报缺项，也不得声称图形渲染通过；实际图形由后续适用图形计划与渲染校验负责。"
        "指南示例行、模板业务1或系统1、示例数值是结构样例，不属于项目事实，也不要求照抄或补造。"
        "partial表示已有部分内容；pending须引用明确缺项、影响和确认方式的正文，不能空口声称待确认。"
        "not_applicable只用于带明确conditions的条件要求，须与已批准适用性理由一致，并引用明确范围边界原文；"
        "没有批准依据或不能确认条件时用pending或partial，不得擅自裁剪。"
        "not_seen只表示本批未见支持原文，evidence为空，不得将它写成整章遗漏issue。"
        "跨片段关联尚不完整时用partial；不得根据当前片段缺少内容就断言全文缺失。"
        "evidence逐字引用本批实际发送的正文，chapter_id与原文对应，reason解释实际覆盖或未覆盖的要点。"
    )
    by_scope = {}
    for disposition in plan["sections"]:
        if disposition["status"] == "not_applicable":
            continue
        section = sections[disposition["section_id"]]
        atoms = _requirements(section, sections)
        if not atoms:
            continue  # Structural headings have no additional content obligations.
        if any(chapter_id not in saved for chapter_id in disposition["chapter_ids"]):
            _error("可研指南对应章节正文尚未完整保存。", "chapters_incomplete")
        scope = tuple(sorted(disposition["chapter_ids"]))
        by_scope.setdefault(scope, []).extend(atoms)
    for scope, atoms in by_scope.items():
        groups, current = [], []
        for atom in atoms:
            if current and len(json.dumps([*current, atom], ensure_ascii=False)) > 4500:
                groups.append(current)
                current = []
            current.append(atom)
        if current:
            groups.append(current)
        assigned = [saved[chapter_id] for chapter_id in scope]
        if not any(paragraph for chapter in assigned for paragraph in chapter.get("paragraphs", [])):
            _error("可研指南对应章节正文为空。", "chapters_incomplete")
        for group_index, group in enumerate(groups, 1):
            base = {
                "action": "independent_review", "family": "feasibility", "chapters": [],
                "guide_requirements": group,
                "guide_dispositions": {section_id: {
                    "status": next(entry["status"] for entry in plan["sections"] if entry["section_id"] == section_id),
                    "reason": next(entry["reason"] for entry in plan["sections"] if entry["section_id"] == section_id),
                    "applicability": sections[section_id].get("applicability", "")}
                    for section_id in dict.fromkeys(atom["section_id"] for atom in group)},
                "guide_support_context": {section_id: {
                    "public_research": sections[section_id].get("public_research", []),
                    "project_inputs": sections[section_id].get("project_inputs", [])}
                    for section_id in dict.fromkeys(atom["section_id"] for atom in group)},
                "schema": {"passed": "boolean", "issues": ["string"], "guide_checks": [{
                    "id": "exact-guide-requirement-id", "status": "covered/partial/not_seen/not_applicable/pending",
                    "evidence": [{"chapter_id": "saved-chapter-id", "quote": "exact-sent-body-quote"}], "reason": "string"}]},
                "review_contract": {
                    "scope": "guide_full_batched", "guide_audit_only": True,
                    "asset_sha256": _ASSET_SHA256, "assigned_chapter_ids": list(scope),
                    "body_manifest": {chapter["chapter_id"]: [len(text) for text in chapter.get("paragraphs", [])]
                                      for chapter in assigned},
                    "approved_scopes": [{"chapter_id": chapter["id"], "scope": chapter.get("scope", "")}
                                        for chapter in blueprint["chapters"] if chapter["id"] in scope],
                    "group_index": group_index, "group_count": len(groups), "batch_index": 0, "batch_count": 0,
                    "instruction": instruction,
                },
            }
            batches, current, body_characters = [], deepcopy(base), 0
            for chapter in assigned:
                for paragraph_index, paragraph in enumerate(chapter.get("paragraphs", []), 1):
                    start = 0
                    while start < len(paragraph):
                        if body_characters >= 4500:
                            batches.append(current)
                            current, body_characters = deepcopy(base), 0
                        end = min(len(paragraph), start + 4500 - body_characters)
                        while True:
                            fragment = {"chapter_id": chapter["chapter_id"], "title": chapter["title"],
                                        "paragraphs": [paragraph[start:end]],
                                        "fragment": {"paragraph_index": paragraph_index, "start": start, "end": end,
                                                     "paragraph_characters": len(paragraph),
                                                     "is_full_paragraph": start == 0 and end == len(paragraph)}}
                            candidate = {**current, "chapters": [*current["chapters"], fragment]}
                            if measure(candidate) <= 14400:
                                current, start = candidate, end
                                body_characters += end - fragment["fragment"]["start"]
                                break
                            if current["chapters"]:
                                batches.append(current)
                                current, body_characters = deepcopy(base), 0
                                end = min(len(paragraph), start + 4500)
                            elif end - start > 1:
                                end = start + max(1, (end - start) // 2)
                            else:
                                _error("可研指南审查请求超过模型载荷上限。", "request_too_large")
            if current["chapters"]:
                batches.append(current)
            for index, batch in enumerate(batches, 1):
                batch["review_contract"].update(batch_index=index, batch_count=len(batches))
                if measure(batch) > 14500:
                    _error("可研指南审查请求超过模型载荷上限。", "request_too_large")
                requests.append(batch)
    return requests


def validate_guide_review(response, request):
    """Validate receipts against the actual dispatched fragment, never model-supplied text."""
    if (not isinstance(response, dict) or set(response) != {"passed", "issues", "guide_checks"}
            or type(response["passed"]) is not bool or not isinstance(response["issues"], list)
            or len(response["issues"]) > 100
            or any(not isinstance(issue, str) or len(issue) > 2000 for issue in response["issues"])
            or not isinstance(response["guide_checks"], list)):
        _error("可研指南复核响应格式无效。", "invalid_model_output")
    required = {item["id"]: item for item in request["guide_requirements"]}
    sent = {}
    for chapter in request["chapters"]:
        sent.setdefault(chapter["chapter_id"], []).extend(chapter["paragraphs"])
    checked = {}
    for check in response["guide_checks"]:
        if (not isinstance(check, dict) or set(check) != {"id", "status", "evidence", "reason"}
                or not isinstance(check["id"], str) or check["id"] not in required or check["id"] in checked
                or not isinstance(check["status"], str) or check["status"] not in _CHECK_STATUSES
                or not isinstance(check["reason"], str) or not check["reason"].strip() or len(check["reason"]) > 2000
                or not isinstance(check["evidence"], list) or len(check["evidence"]) > 5):
            _error("可研指南要求复核遗漏、重复或类型无效。", "invalid_model_output")
        if ((check["status"] == "not_seen" and check["evidence"])
                or (check["status"] != "not_seen" and not check["evidence"])
                or (check["status"] == "not_applicable"
                    and (not required[check["id"]].get("conditions")
                         or not request["guide_dispositions"][required[check["id"]]["section_id"]]["reason"].strip()))):
            _error("已覆盖、待确认或不适用判断缺少有效正文和批准依据。", "invalid_model_output")
        for receipt in check["evidence"]:
            if (not isinstance(receipt, dict) or set(receipt) != {"chapter_id", "quote"}
                    or not isinstance(receipt["chapter_id"], str) or receipt["chapter_id"] not in sent
                    or not isinstance(receipt["quote"], str) or not receipt["quote"].strip()
                    or len(receipt["quote"]) > 2000
                    or not any(receipt["quote"] in text for text in sent[receipt["chapter_id"]])):
                _error("可研指南覆盖证据不是本批保存正文的连续原文。", "invalid_model_output")
        checked[check["id"]] = deepcopy(check)
    if set(checked) != set(required):
        _error("可研指南复核不得遗漏要求。", "invalid_model_output")
    return {"passed": response["passed"], "issues": list(response["issues"]),
            "guide_checks": [checked[item["id"]] for item in request["guide_requirements"]]}


def _complete_scan_plan(requests):
    """Check contiguous paragraph coverage for every scope/checklist group."""
    groups, scopes = {}, {}
    for request in requests:
        contract = request["review_contract"]
        scope = tuple(contract["assigned_chapter_ids"])
        key = scope, contract["group_index"]
        scopes.setdefault(scope, set()).add(contract["group_index"])
        group = groups.setdefault(key, {"contract": contract, "batches": set(), "fragments": {}})
        if (contract["group_count"] != group["contract"]["group_count"]
                or contract["batch_count"] != group["contract"]["batch_count"]
                or contract["body_manifest"] != group["contract"]["body_manifest"]
                or contract["batch_index"] in group["batches"]):
            return False
        group["batches"].add(contract["batch_index"])
        for chapter in request["chapters"]:
            fragment = chapter["fragment"]
            if (len(chapter["paragraphs"]) != 1
                    or fragment["end"] - fragment["start"] != len(chapter["paragraphs"][0])):
                return False
            position = chapter["chapter_id"], fragment["paragraph_index"]
            group["fragments"].setdefault(position, []).append((fragment["start"], fragment["end"]))
    for (scope, _), group in groups.items():
        contract = group["contract"]
        if (scopes[scope] != set(range(1, contract["group_count"] + 1))
                or group["batches"] != set(range(1, contract["batch_count"] + 1))):
            return False
        expected = {}
        for chapter_id, lengths in contract["body_manifest"].items():
            for index, length in enumerate(lengths, 1):
                if length:
                    expected[chapter_id, index] = length
        if set(group["fragments"]) != set(expected):
            return False
        for position, length in expected.items():
            cursor = 0
            for start, end in sorted(group["fragments"][position]):
                if start != cursor or not start < end <= length:
                    return False
                cursor = end
            if cursor != length:
                return False
    return True


def reduce_guide_reviews(requests, responses):
    """Absence is a whole-scan result; incomplete and partial scans never imply PASS."""
    if len(responses) > len(requests):
        _error("可研指南复核响应数量无效。", "invalid_model_output")
    atoms, expected, receipts, issues = {}, {}, {}, []
    for request in requests:
        for atom in request["guide_requirements"]:
            atoms[atom["id"]] = atom
            expected[atom["id"]] = expected.get(atom["id"], 0) + 1
    scan_passed = True
    for request, response in zip(requests, responses):
        checked = validate_guide_review(response, request)
        scan_passed = scan_passed and checked["passed"] and not checked["issues"]
        issues.extend(issue for issue in checked["issues"] if issue not in issues)
        for check in checked["guide_checks"]:
            receipts.setdefault(check["id"], []).append(check)
    complete = len(responses) == len(requests) and _complete_scan_plan(requests)
    checks = []
    for requirement_id, atom in atoms.items():
        found = receipts.get(requirement_id, [])
        states = {check["status"] for check in found}
        if not complete or len(found) != expected[requirement_id]:
            status = "incomplete"
        elif "pending" in states:
            status = "pending"
        elif "covered" in states and "not_applicable" in states:
            status = "partial"
        elif "covered" in states:
            status = "covered"
        elif "not_applicable" in states:
            status = "not_applicable"
        elif "partial" in states:
            status = "partial"
        else:
            status = "missing"
            issues.append(f"指南要求 {requirement_id}（{atom['requirement']}）在已批准映射章节的完整保存正文中未找到覆盖证据；补充适用内容，资料不足时说明具体缺项、影响和确认方式。")
        evidence = []
        for check in found:
            if check["status"] == status or (status == "partial" and check["status"] != "not_seen"):
                for receipt in check["evidence"]:
                    if receipt not in evidence and len(evidence) < 5:
                        evidence.append(receipt)
        checks.append({"id": requirement_id, "section_id": atom["section_id"], "status": status,
                       "evidence": evidence, "reason": next((check["reason"] for check in found if check["status"] == status), ""),
                       "completed_fragments": len(found), "expected_fragments": expected[requirement_id]})
    pending = [check["id"] for check in checks if check["status"] in {"pending", "partial", "incomplete"}]
    return {"complete": complete, "passed": complete and scan_passed and not issues and not pending,
            "issues": issues, "checks": checks, "pending": pending, "asset_sha256": _ASSET_SHA256}
