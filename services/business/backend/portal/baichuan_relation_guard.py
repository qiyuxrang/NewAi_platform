"""Validate a model's broad grade relation against bounded source clauses.

This gate never extracts a replacement predicate or orders certificate grades.
An unproven relation requires clarification instead of silently becoming exact.
"""
import hashlib
import json
import re

from .baichuan_rules_aliases import ALIASES


def leaves(node):
    for op in ("all", "any"):
        if op in node:
            return [leaf for child in node[op] for leaf in leaves(child)]
    return leaves(node["not"]) if "not" in node else [node]


def relation_key(node):
    data = {key: value for key, value in node.items() if key != "source_refs"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _aliases(category):
    values = {category, *(name for name, code in ALIASES.items() if code == category)}
    return [re.compile((r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])")
                       if name.isascii() else re.escape(name), re.I) for name in values]


def _category_present(text, category):
    return any(alias.search(text) for alias in _aliases(category))


def _grade(value):
    # Literal grade spellings only; this map does not imply any ordering.
    chinese = {str(i): ch for i, ch in enumerate("一二三四五六七八九", 1)}
    boundary = r"(?<![0-9一二三四五六七八九十百零])"
    spellings = [boundary + re.escape(value) + r"(?!\d)"]
    if value in chinese:
        spellings.append(boundary + chinese[value] + r"(?:级|等)?")
    return "(?:" + "|".join(spellings) + ")"


def _supported(clause, node):
    if len(clause) > 300 or re.search(r"不是|并非|不按|不得|不能|不要|不要求|不接受|不含|无需|无须|不必|不需要|不需|可不|免于|取消|精确|仅限|仅为", clause):
        return False
    holder_words = {"bidder": r"投标人|投标单位|投标企业|供应商",
                    "manufacturer": r"制造商|生产厂商|生产厂家",
                    "person": r"人员|个人|项目负责人", "product": r"产品证书|产品认证",
                    "consortium_member": r"联合体成员"}
    holders = {holder for holder, words in holder_words.items() if re.search(words, clause)}
    if holders and holders != {node["holder"]}:
        return False
    if not holders and node["holder"] != "bidder":
        return False
    aliases = _aliases(node["category"])
    starts = {match.start() for alias in aliases for match in alias.finditer(clause)}
    if len(starts) != 1:
        return False  # Multiple same-category subjects/levels require a scope.
    grade = _grade(node["value"])
    gap = r"[^，。；;\n]{0,12}?"
    before = r"(?:不低于|至少|大于等于|≥|>=)"
    after = r"(?:级|等)?\s*(?:及以上|或以上)"
    for alias in aliases:
        patterns = (alias.pattern + gap + grade + after,
                    alias.pattern + gap + before + gap + grade,
                    before + gap + alias.pattern + gap + grade)
        for pattern in patterns:
            for match in re.finditer(pattern, clause, re.I):
                # A comparator next to another category never licenses this one.
                if any(code != node["category"] and _category_present(match.group(), code)
                       for code in set(ALIASES.values())):
                    continue
                return True
    return False


def check_relations(compiled, *, text, source_blocks, previous=None, validated_previous=()):
    """Return unresolved claims and validated keys; inputs are already schema checked.

    File claims need the predicate's own block refs. A prior gate-approved claim
    can survive an unrelated follow-up without requiring the source to repeat.
    """
    accepted, problems = [], []
    prior = {relation_key(node) for root in ([previous["must"], *previous["should"]] if previous else [])
             for node in leaves(root)} & set(validated_previous)
    for root in [compiled["must"], *compiled["should"]]:
        for node in leaves(root):
            if node.get("field") != "qualification" or node.get("op") != "grade_at_least":
                continue
            key = relation_key(node)
            changed_text = (_category_present(text, node["category"]) and re.search(_grade(node["value"]), text)) or re.fullmatch(
                r"(?:请)?(?:所有|全部)?(?:资质等级|等级|级别)?(?:改成|改为|要求)?精确(?:匹配)?[。！!]?", text.strip())
            new_source = any(_category_present(value, node["category"]) for value in source_blocks.values())
            if key in prior and not changed_text and not new_source:
                accepted.append(key)
                continue
            sources = [text] if text else []
            sources.extend(source_blocks[ref] for ref in node.get("source_refs", []) if ref in source_blocks)
            clauses = [clause.strip() for source in sources for clause in re.split(r"[，。；;\n!?！？]", source)]
            if any(_supported(clause, node) for clause in clauses if clause):
                accepted.append(key)
            else:
                problems.append({"category": node["category"], "value": node["value"],
                                 "holder": node["holder"], "relation_key": key})
    return problems, sorted(set(accepted))
