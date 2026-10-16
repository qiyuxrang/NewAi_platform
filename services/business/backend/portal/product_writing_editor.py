"""Bounded, explicitly selected cross-report checks; never a replacement for full review."""
import re
from copy import deepcopy

from django.conf import settings

from .product_content_quality import content_quality_policy_hash
from .product_parallel import atomic
from .product_rules import rules_hash
from .product_service import (blueprint_chapters, current_revision, digest,
                              source_ids_belong, validate_chapter)
from .product_steps import run_step


VERSION = 1
SCOPE = "selected_cross_report_consistency"
_SENTENCE = re.compile(r"[^。！？!?\n]+(?:[。！？!?]+[”’」』]*|\n+|$)")
_QUANTITY = re.compile(r"[\d一二三四五六七八九十百千万两]+(?:\.\d+)?\s*(?:台|套|个|只|块|面|路|条|座|根|米|组)")
_TOPICS = {
    "construction_scope": re.compile(r"建设范围|建设内容|建设边界|不纳入|不包含|不包括|纳入建设|范围包括|范围为|覆盖范围"),
    "schedule": re.compile(r"工期|建设周期|实施周期|建设期限|建设期[为是暂预计：:]|实施窗口"),
    "investment": re.compile(r"总投资|投资总额|项目预算|建设预算|预算总额|投资概算|投资估算|建设投资|项目投资|费用总额"),
}
_ISSUE = re.compile(r"^\[(W\d+(?:,W\d+)*)\]\s*\S")
_BOUNDARY = (
    "仅对照本批同comparison_group的原句，核对同一对象的建设范围、数量、工期投资及待确认口径。"
    "不得把不同对象、阶段、单位、现状与候选方案混为冲突。条件和批准目录不是项目事实，"
    "PUBLIC_REFERENCE不能证明本项目事实；缺少原始来源时只判断所给原句是否冲突，不确认事实真实性。"
    "这是关键词选中的口径对照，未选语句和跨批关系未审；原逐报告全文复核和人工核对仍必需。"
    "fragment给出原段落0基索引及字符范围；片段截断不是原文缺失。不得仅因本检查边界列内容问题。"
    "issues每项必须以一个或多个实际片段ID组成的前缀开头，例如[W000001,W000002]，"
    "随后完整说明具体口径冲突及依据。只定位本批实际提供的ID，不能猜测其他位置；保留所有实质问题。"
)


def _request(groups):
    return {"action": "independent_review", "family": "cross-report",
            "chapters": [chunk for group in groups for chunk in group["chunks"]],
            "comparison_groups": [{key: value for key, value in group.items() if key != "chunks"}
                                  for group in groups],
            "schema": {"passed": "boolean", "issues": ["string"]},
            "review_contract": {"scope": SCOPE, "full_document_human_review_required": True,
                                "instruction": _BOUNDARY}}


def _plan(chapters_by_family, input_payload, blueprint_payload, items, request_size):
    """Scan every sentence; selected groups are packed linearly without dropping text."""
    # ponytail: exact keyword selection misses implicit claims; keep the existing full report review.
    groups, locations = {}, {}
    stats = {"scanned_sentences": 0, "scanned_characters": 0, "selected_sentences": 0,
             "not_selected_sentences": 0, "unpaired_chunks": 0, "unreviewed_chunks": 0}
    names = sorted({str(item.get("name", "")) for item in items if len(str(item.get("name", ""))) >= 2
                    and item.get("name") not in {"系统", "方案", "设备", "平台", "项目"}})
    for family, chapters in chapters_by_family.items():
        for chapter in chapters:
            payload = chapter.payload
            for paragraph_index, paragraph in enumerate(payload["paragraphs"]):
                stats["scanned_characters"] += len(paragraph)
                for match in _SENTENCE.finditer(paragraph):
                    text = match.group()
                    stats["scanned_sentences"] += 1
                    keys = [key for key, pattern in _TOPICS.items() if pattern.search(text)]
                    if _QUANTITY.search(text):
                        keys.extend("equipment:" + name for name in names if name in text)
                    if not keys:
                        stats["not_selected_sentences"] += 1
                        continue
                    stats["selected_sentences"] += 1
                    for start in range(0, len(text), 2000):
                        end = min(start + 2000, len(text))
                        identifier = f"W{len(locations) + 1:06d}"
                        location = {"family": family, "chapter_id": payload["chapter_id"],
                                    "paragraph_index": paragraph_index, "start": match.start() + start,
                                    "end": match.start() + end, "sentence_start": match.start(),
                                    "sentence_end": match.end(), "is_full_sentence": start == 0 and end == len(text),
                                    "text_sha256": digest(text[start:end])}
                        locations[identifier] = location
                        chunk = {"chunk_id": identifier, "family": family, "chapter_id": payload["chapter_id"],
                                 "title": payload["title"], "source_ids": payload["source_ids"],
                                 "paragraphs": [text[start:end]], "fragment": location}
                        for key in keys:
                            groups.setdefault(key, []).append(chunk)

    requests, pending, current = [], {}, []

    def fits(candidate):
        return (sum(len(text) for group in candidate for chunk in group["chunks"] for text in chunk["paragraphs"]) <= 6500
                and request_size(_request(candidate)) <= 14500)

    for key, chunks in groups.items():
        families = sorted({chunk["family"] for chunk in chunks})
        if len({(chunk["family"], chunk["chapter_id"]) for chunk in chunks}) < 2:
            stats["unpaired_chunks"] += len(chunks)
            continue
        allowed = {source for chunk in chunks for source in chunk["source_ids"]}
        name = key.removeprefix("equipment:") if key.startswith("equipment:") else None
        condition_matches = lambda text: name in text if name else bool(_TOPICS[key].search(text))
        baseline = {"equipment_items": [{field: item.get(field) for field in
                                         ("row_id", "source_id", "name", "quantity", "unit", "specification", "source_section", "source_location")
                                         if item.get(field) is not None} for item in items
                                        if name and item.get("name") == name
                                        and any(str(item.get(field)) in allowed for field in ("row_id", "source_id"))],
                    "approved_conditions": [condition for condition in blueprint_payload.get("conditions", [])
                                            if condition_matches(str(condition.get("text", "")))],
                    "source_statements": [deepcopy(statement) for statement in input_payload.get("statements", [])
                                          if statement.get("source_ids") and set(statement["source_ids"]) <= allowed
                                          and condition_matches(str(statement.get("text", "")))],
                    "scope": "仅匹配的清单、已定位来源陈述及批准条件；保留陈述原有来源性质，不代替完整来源，也不验证来源真实性"}
        group = {"key": key, "families": families, "baseline": baseline, "chunk_ids": [], "chunks": []}
        pieces = []
        for chunk in chunks:
            candidate = {**group, "chunks": [*group["chunks"], chunk],
                         "chunk_ids": [*group["chunk_ids"], chunk["chunk_id"]]}
            if fits([candidate]):
                group = candidate
                continue
            if group["chunks"]:
                pieces.append(group)
            group = {**group, "chunks": [chunk], "chunk_ids": [chunk["chunk_id"]]}
            if not fits([group]):
                stats["unreviewed_chunks"] += 1
                pending[key] = {"families": families, "reason": "request_context_too_large"}
                group = {**group, "chunks": [], "chunk_ids": []}
        if group["chunks"]:
            pieces.append(group)
        if len(pieces) > 1 or any(not chunk["fragment"]["is_full_sentence"] for chunk in chunks):
            pending.setdefault(key, {"families": families, "reason": "cross_batch_or_split_sentence_requires_human_review"})
        for piece in pieces:
            if current and not fits([*current, piece]):
                requests.append(_request(current))
                current = []
            current.append(piece)
    if current:
        requests.append(_request(current))
    stats.update(selected_chunks=len(locations), batch_count=len(requests), pending_groups=pending,
                 scanned_complete=True, full_document_semantic_review=False,
                 selection="精确清单对象及数量；明确建设范围、工期和投资句；未选句保留原逐报告全文复核")
    return requests, locations, stats


def review_writing(task_id, fence, attempt_id, task, input_revision, blueprint, chapters_by_family):
    """Return located findings; coverage limits stay visible without inventing content defects."""
    from . import product_worker as worker

    chapters_by_family = {family: list(chapters.values() if isinstance(chapters, dict) else chapters)
                          for family, chapters in chapters_by_family.items()}
    chapter_hashes = {}
    for family, chapters in chapters_by_family.items():
        approved = {chapter["id"]: chapter for chapter in blueprint_chapters(blueprint.payload, family)}
        if not chapters or {chapter.payload["chapter_id"] for chapter in chapters} != set(approved):
            raise worker.ExecutionError("chapters_incomplete")
        for chapter in chapters:
            payload = validate_chapter(chapter.payload)
            allowed = approved[payload["chapter_id"]]["source_ids"]
            if (payload["title"] != approved[payload["chapter_id"]]["title"] or not payload["source_ids"]
                    or not set(payload["source_ids"]) <= set(allowed)
                    or digest(chapter.payload) != chapter.sha256):
                raise worker.ExecutionError("source_snapshot_changed")
            chapter_hashes[family + ":" + payload["chapter_id"]] = chapter.sha256
    route = settings.PRODUCT_REVIEW_ROUTE
    binding = {"editor_version": VERSION, "input_sha256": input_revision.sha256,
               "blueprint_sha256": blueprint.sha256, "chapter_hashes": chapter_hashes,
               "rules_sha256": rules_hash(), "quality_policy_sha256": content_quality_policy_hash(),
               "route": route, "route_sha256": worker._review_route_hash(route)}

    def guard():
        with atomic():
            fresh = worker._guard(task_id, fence)
            current_input, current_blueprint = current_revision(fresh, "input"), current_revision(fresh, "blueprint")
            if (not current_input or not current_blueprint
                    or current_input.pk != input_revision.pk or current_blueprint.pk != blueprint.pk
                    or current_input.sha256 != input_revision.sha256 or digest(current_input.payload) != input_revision.sha256
                    or current_blueprint.sha256 != blueprint.sha256 or digest(current_blueprint.payload) != blueprint.sha256):
                raise worker.ExecutionError("source_snapshot_changed")
            for family, chapters in chapters_by_family.items():
                current = worker.current_chapters(fresh, input_revision.sha256, blueprint.sha256, family)
                for chapter in chapters:
                    found = current.get(chapter.payload["chapter_id"])
                    if (not found or found.pk != chapter.pk or found.sha256 != chapter.sha256
                            or digest(found.payload) != chapter.sha256):
                        raise worker.ExecutionError("source_snapshot_changed")
            cited = [source for chapters in chapters_by_family.values() for chapter in chapters for source in chapter.payload["source_ids"]]
            if not source_ids_belong(fresh, cited):
                raise worker.ExecutionError("retrieval_authorization_required")
            if rules_hash() != binding["rules_sha256"] or content_quality_policy_hash() != binding["quality_policy_sha256"]:
                raise worker.ExecutionError("product_rules_unavailable")
            if settings.PRODUCT_REVIEW_ROUTE != route or worker._review_route_hash(route) != binding["route_sha256"]:
                raise worker.ExecutionError("model_configuration_changed")

    guard()
    requests, locations, coverage = _plan(chapters_by_family, input_revision.payload, blueprint.payload,
                                         worker._source_items(task, input_revision.payload), worker._review_request_size)
    binding["plan_sha256"] = digest(requests)
    issues, batches, affected, blocked = [], [], {}, set()
    all_passed = bool(requests)
    for index, request in enumerate(requests, 1):
        guard()
        identifiers = {chunk["chunk_id"] for chunk in request["chapters"]}

        def validate(response):
            worker._validated_reviewer(response, request)
            for issue in response["issues"]:
                match = _ISSUE.match(issue)
                if not match or not set(match[1].split(",")) <= identifiers:
                    raise worker.ExecutionError("invalid_model_output")
            return response

        def cached_valid(response):
            try:
                return bool(validate(response))
            except (worker.ExecutionError, KeyError, TypeError):
                return False

        response = run_step(task_id, fence, f"writing-editor:{index}", {**binding, "request_sha256": digest(request)},
                            lambda: worker._model(task_id, fence, attempt_id, route, deepcopy(request), output_validator=validate),
                            validate=cached_valid)
        validate(response)
        guard()
        passed = response["passed"] and not response["issues"]
        all_passed = all_passed and passed
        for issue in response["issues"]:
            if issue not in issues:
                issues.append(issue)
            for identifier in _ISSUE.match(issue)[1].split(","):
                location = locations[identifier]
                blocked.add(location["family"])
                key = (location["family"], location["chapter_id"])
                item = affected.setdefault(key, {"family": key[0], "chapter_id": key[1], "issues": [], "paragraph_indices": []})
                if issue not in item["issues"]:
                    item["issues"].append(issue)
                if location["paragraph_index"] not in item["paragraph_indices"]:
                    item["paragraph_indices"].append(location["paragraph_index"])
        batches.append({"batch": index, "request_sha256": digest(request), "passed": passed,
                        "issues": list(response["issues"]), "chunk_ids": sorted(identifiers)})
    guard()
    complete = not coverage["pending_groups"] and all_passed
    status = ("issues_found" if issues else "passed" if complete else
              "pending_human_review" if requests or coverage["pending_groups"] else "not_applicable")
    return {"status": status, "passed": complete, "issues": issues, "blocked_families": sorted(blocked),
            "affected_chapters": list(affected.values()), "scope": SCOPE,
            "full_document_human_review_required": True, "binding": binding, "batches": batches,
            "coverage": {**coverage, "selected_comparisons_complete": complete,
                         "locations": locations, "completed_batches": len(batches)}}
