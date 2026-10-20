"""Missing file attribution is a clarification, never an inferred citation."""
from .baichuan_file_conditions import identity, predicates


def missing_hard_sources(compiled, *, current_refs, text_ref="", previous=None, previous_text_keys=(), required_keys=()):
    """Return new hard leaves lacking a per-leaf authorized file citation.

    This checks attribution completeness, not truth of a cited clause. Existing
    text-only predicates may survive a later upload without fabricated citations.
    Older file trees with missing attribution cannot certify themselves.
    """
    if not current_refs and not required_keys:
        return []
    previous = previous or {}
    previous_has_files = any(ref.startswith("attachment:") for ref in previous.get("source_refs", []))
    inherited = {identity(node) for node in predicates(previous["must"])
        if not previous_has_files or node.get("source_refs") or identity(node) in previous_text_keys} if previous.get("must") else set()
    allowed = set(current_refs) | set(previous.get("source_refs", []))
    if text_ref:
        allowed.add(text_ref)
    gaps = []
    for node in predicates(compiled["must"]):
        if not current_refs and identity(node) not in required_keys:
            continue
        if identity(node) in inherited:
            continue
        refs = node.get("source_refs", [])
        if not refs or not all(ref in allowed for ref in refs):
            gaps.append({"field": node["field"], "category": node.get("category", ""),
                         "holder": node.get("holder", ""), "value": node["value"]})
    return gaps
