"""Deterministic writing briefs; approved blueprint content is never rewritten."""

from copy import deepcopy
from graphlib import CycleError, TopologicalSorter


_FAMILIES = {"technical-solution", "feasibility"}
_BASIS = ("现状", "需求", "背景", "目标", "必要性", "建设条件", "概述", "总论", "编制依据", "设计依据", "设计原则")
_DESIGN = ("架构", "总体设计", "技术路线", "建设方案", "技术方案", "系统设计", "详细设计",
           "总体方案", "部署方案", "建设内容", "工程方案", "技术选型", "设备选型", "设计方案")
_FINANCE = ("投资", "估算", "概算", "预算", "资金", "效益", "经济论证", "经济评价", "经济分析",
            "财务", "成本", "费用", "收益")
_CONSTRAINTS = [
    "只编写chapter中已批准的title和scope；chapters是完整批准目录，不得新增、删除或改写蓝图。",
    "服从共同purpose、audience和conditions；不得替其他章节作出结论或扩大本章职责。",
    "source_ids仅可使用本章批准来源；不得改写已批准事实、对象、数值、单位或确认状态。",
    "前置章节结论只用于保持口径一致，不是新增项目事实或扩大来源授权的依据；冲突保留待确认。",
    "适用但缺资料的内容须保留缺项、取证方法和论证限制，不得将资料不足判为不适用。",
    "不得编造测算、收益、设备、政策或确定性结论；未知和冲突继续保留待确认。",
]


def _role(chapter):
    # ponytail: title keywords cover common headings; unusual approved titles stay independent.
    title = "".join(chapter["title"].split())
    if any(word in title for word in _FINANCE):
        return "finance"
    if any(word in title for word in _DESIGN):
        return "design"
    if any(word in title for word in _BASIS):
        return "basis"
    return "design" if "设计" in title else "other"


def _validate_plan(jobs):
    """Validate executable identities, including legacy shared-family chapter IDs."""
    by_key = {(job["family"], job["chapter_id"]): job for job in jobs}
    if len(by_key) != len(jobs):
        raise ValueError("Duplicate writing job")
    graph = {}
    for key, job in by_key.items():
        dependencies = []
        for chapter_id in job["depends_on"]:
            if chapter_id == job["chapter_id"]:
                raise ValueError("Chapter cannot depend on itself")
            candidate = (job["family"], chapter_id)
            if candidate not in by_key:
                matches = [other for other in by_key if other[1] == chapter_id]
                if len(matches) != 1:
                    raise ValueError("Missing or ambiguous chapter dependency")
                candidate = matches[0]
            dependencies.append(candidate)
        graph[key] = dependencies
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ValueError("Cyclic chapter dependencies") from exc


def build_writing_plan(blueprint_payload, families):
    """Return jobs in approved directory order, with dependencies only on selected jobs.

    Common chapter titles establish a conservative basis -> design -> finance graph.
    Titles without these roles remain independent; this is not a semantic re-planner.
    Legacy chapters without family remain shared, as in blueprint_chapters().
    """
    if (not isinstance(blueprint_payload, dict) or not isinstance(families, (list, tuple))
            or not families or any(not isinstance(family, str) or family not in _FAMILIES for family in families)):
        raise ValueError("Invalid writing plan input")
    chapters = blueprint_payload.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("Approved chapters are required")
    ids = set()
    for chapter in chapters:
        if (not isinstance(chapter, dict) or not isinstance(chapter.get("id"), str)
                or not chapter["id"].strip() or chapter["id"] in ids
                or not isinstance(chapter.get("title"), str) or not chapter["title"].strip()
                or not isinstance(chapter.get("scope"), str)
                or not isinstance(chapter.get("source_ids"), list)
                or ("family" in chapter and (not isinstance(chapter["family"], str)
                                            or chapter["family"] not in _FAMILIES))):
            raise ValueError("Invalid or duplicate approved chapter")
        ids.add(chapter["id"])

    jobs = []
    common = {field: blueprint_payload.get(field, [] if field in {"conditions", "missing", "conflicts"} else "")
              for field in ("purpose", "audience", "conditions", "missing", "conflicts")}
    common.update(chapters=chapters, constraints=_CONSTRAINTS)
    for family in dict.fromkeys(families):
        for chapter in chapters:
            if chapter.get("family", family) == family:
                jobs.append({"family": family, "chapter_id": chapter["id"], "depends_on": [],
                             "brief": deepcopy({**common, "chapter": chapter})})

    roles = {(job["family"], job["chapter_id"]): _role(job["brief"]["chapter"]) for job in jobs}
    basis = [job for job in jobs if roles[(job["family"], job["chapter_id"])] == "basis"]
    designs = [job for job in jobs if roles[(job["family"], job["chapter_id"])] == "design"]
    # ponytail: O(n²) family filtering is bounded by 200 approved chapters; index if that cap grows.
    for job in jobs:
        role = roles[(job["family"], job["chapter_id"])]
        own_basis = [other for other in basis if other["family"] == job["family"]]
        if role == "design":
            predecessors = own_basis or basis
        elif role == "finance":
            predecessors = designs or own_basis or basis
        else:
            predecessors = []
        job["depends_on"] = list(dict.fromkeys(other["chapter_id"] for other in predecessors))
    _validate_plan(jobs)
    return jobs
