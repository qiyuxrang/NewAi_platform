"""Conservative text-authorized edits of file requirements, never model actions."""
from copy import deepcopy
import json
import re

from .baichuan_rules_aliases import canonical_category

KNOWN_CATEGORIES = {"electronic", "labor", "cs", "cmmi", "ccrc", "itss", "security"}


def identity(node):
    """Sources describe an assertion; they do not change its logical identity."""
    if "all" in node or "any" in node:
        op = "all" if "all" in node else "any"
        return json.dumps([op, sorted(identity(child) for child in node[op])], ensure_ascii=False)
    if "not" in node:
        return json.dumps(["not", identity(node["not"])], ensure_ascii=False)
    return json.dumps({k: v for k, v in node.items() if k != "source_refs"}, sort_keys=True, ensure_ascii=False)


def normalize(node):
    node = deepcopy(node)
    if "not" in node:
        return {"not": normalize(node["not"])}
    for op in ("all", "any"):
        if op not in node:
            continue
        children, positions = [], {}
        for child in node[op]:
            child = normalize(child)
            for item in child.get(op, [child]):
                key = identity(item)
                if key not in positions:
                    positions[key] = len(children)
                    children.append(item)
                elif "source_refs" in item:
                    old = children[positions[key]]
                    old["source_refs"] = sorted(set(old.get("source_refs", [])) | set(item["source_refs"]))
        return children[0] if len(children) == 1 else {op: children}
    return node


def merge(*nodes):
    nodes = [node for node in nodes if node is not None]
    return normalize({"all": nodes}) if nodes else None


def conjuncts(node):
    if "all" in node:
        return [child for item in node["all"] for child in conjuncts(item)]
    return [node]


def predicates(node):
    for op in ("all", "any"):
        if op in node:
            return [leaf for item in node[op] for leaf in predicates(item)]
    if "not" in node:
        return predicates(node["not"])
    return [node]


def cancellation(text):
    # Full-message matching prevents quoted/instructional document content or
    # unrelated negations from becoming a tool authorization.
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"(?:请|帮我)?(?:取消|去掉|移除|删除)(?:前轮|之前|上一轮)?(?:招标文件|文件|附件)(?:中|里)?(?:的)?\s*(.*?)\s*(?:硬性要求|硬性条件|资格要求|资质要求)[。！!]?", text.strip(), re.I)
    if not match:
        return None
    target = match.group(1).strip()
    if target in {"全部", "所有", "全部的", "所有的"}:
        return {"all": True}
    category = canonical_category(target)
    if category not in KNOWN_CATEGORIES:
        category = canonical_category(target.upper())
    return {"category": category} if category in KNOWN_CATEGORIES else {"unknown": target}


def guards_from(tree, *, payload, checkpoint):
    if "file_requirements" in checkpoint:
        return deepcopy(checkpoint["file_requirements"])
    if not tree or not any(ref.startswith("attachment:") for ref in tree.get("source_refs", [])):
        return []
    pure_file = bool(payload.get("attachment_ids")) and not payload.get("text", "").strip() and not payload.get("parent_revision", 0)
    result = []
    for node in conjuncts(tree["must"]):
        leaves = predicates(node)
        origins = [any(ref.startswith("attachment:") for ref in leaf.get("source_refs", [])) for leaf in leaves]
        if all(origins) or pure_file:
            result.append({"node": deepcopy(node), "known": True})
        elif not all(leaf.get("source_refs") for leaf in leaves):
            # Older mixed-input snapshots may not attribute each predicate.
            result.append({"node": deepcopy(node), "known": False})
    return result


def relax(guards, action):
    """Return retained guards, exact removed predicates, and a clarification."""
    guards = [{"node": node, "known": guard["known"]} for guard in guards for node in conjuncts(guard["node"])]
    if action is None:
        return deepcopy(guards), set(), ""
    if "unknown" in action:
        return deepcopy(guards), set(), "请指出要取消的已识别资质类别；目前无法精确定位该文件要求。"
    target = lambda leaf: action.get("all") or (leaf.get("field") == "qualification" and leaf.get("category") == action.get("category"))
    matches = [guard for guard in guards if any(target(leaf) for leaf in predicates(guard["node"]))]
    if not matches:
        return deepcopy(guards), set(), "没有定位到该类别的文件硬性要求，请指出文件条款或具体范围。"
    if any(not guard["known"] for guard in matches):
        return deepcopy(guards), set(), "相关条件未能区分文件和文字来源，请指出要取消的具体文件条款，原条件暂时保留。"
    # A whole-file request drops whole known groups. A category-only edit
    # inside OR/NOT changes the other branches and needs explicit wider scope.
    if not action.get("all") and any("any" in guard["node"] or "not" in guard["node"] for guard in matches):
        return deepcopy(guards), set(), "该要求位于或/非组合中，不能只删除其中一项。若确实要取消全部文件硬性要求，请回复“取消前轮文件全部硬性要求”；否则该组合继续保留。"
    removed = {identity(guard["node"]) for guard in matches}
    retained = [deepcopy(guard) for guard in guards if identity(guard["node"]) not in removed]
    return retained, removed, ""


def remove_exact(node, removed):
    if identity(node) in removed:
        return None
    if "all" in node:
        return merge(*(remove_exact(child, removed) for child in node["all"]))
    # Never alter part of OR/NOT. Caller asks for scope if the model reintroduces
    # a removed assertion under such a group.
    if any(identity(leaf) in removed for leaf in predicates(node)):
        raise ValueError("ambiguous_boolean_edit")
    return deepcopy(node)
