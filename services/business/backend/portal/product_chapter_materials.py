"""Conservative, local excerpts of already authorized material; never edit facts."""
import re


_BLOCK = re.compile(r"(?m)^\[[^\]\n]+ · b\d+\]\n")
_QUALIFIER = re.compile(
    r"不|未|无|仅|只|需|须|待|限制|前提|否则|条件|注意|说明|备注|约束|例外|尚|来源|出处|用途|参考|适用|机构|URL"
    r"|\b(?:not|only|unless|except|if|must|should|pending|unverified|reference|source)\b", re.IGNORECASE)


def _heading_level(text):
    match = re.match(r"^(#{1,6})\s+", text)
    if match:
        return len(match[1])
    match = re.match(r"^(\d+(?:\.\d+)*)[、.．\s]+", text)
    if match:
        return match[1].count(".") + 1
    if re.match(r"^(?:第[一二三四五六七八九十百0-9]+章|[一二三四五六七八九十百]+[、.．])", text):
        return 1
    if re.match(r"^[（(][一二三四五六七八九十百0-9]+[）)]", text):
        return 2
    return None


def chapter_material(text, chapter):
    """Return intact spans and their offsets; weak/no matches keep the full text.

    ponytail: exact title/scope phrases only; semantic retrieval needs separate
    evidence and acceptance before replacing this conservative fallback.
    """
    phrases = [phrase.strip() for value in (chapter.get("title", ""), chapter.get("scope", ""))
               for phrase in re.split(r"[，,。；;！？!?\n]+", value) if len(phrase.strip()) >= 4]
    markers = list(_BLOCK.finditer(text))
    starts = ([0] if not markers or markers[0].start() else []) + [match.start() for match in markers]
    if not markers:
        starts += [match.end() for match in re.finditer(r"\n[ \t]*\n", text) if match.end() < len(text)]
    ends = [*starts[1:], len(text)]
    spans = list(zip(starts, ends))
    bodies = [_BLOCK.sub("", text[start:end], count=1).strip() for start, end in spans]
    matches = set()
    for index, body in enumerate(bodies):
        for phrase in phrases:
            # ASCII words must not match fragments such as 'plan' in 'planet'.
            pattern = re.escape(phrase)
            if re.search(r"[A-Za-z]", phrase):
                pattern = r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])"
            if re.search(pattern, body, re.IGNORECASE):
                matches.add(index)
                break
    selected = set(range(len(spans))) if not matches else {0}
    levels = [_heading_level(body) if "\n" not in body and len(body) <= 160 else None for body in bodies]
    for index in matches:
        heading = next((before for before in range(index, -1, -1) if levels[before] is not None), None)
        if heading is not None:
            end = next((after for after in range(heading + 1, len(spans))
                        if levels[after] is not None and levels[after] <= levels[heading]), len(spans))
            selected.update(range(heading, end))
        selected.update(range(max(0, index - 1), min(len(spans), index + 2)))
    # Retain qualifications and provenance even when they occur outside a match.
    if matches:
        selected.update(index for index, body in enumerate(bodies) if _QUALIFIER.search(body))
    tables = {}
    for index, (start, end) in enumerate(spans):
        marker = _BLOCK.match(text[start:end])
        if marker:
            label = marker[0]
            table = re.search(r"表格 \d+", label)
            sheet = re.search(r"工作表 (.+?)(?: ·|\])", label)
            if table or sheet:
                key = (sheet[1] if sheet else "", table[0] if table else "worksheet")
                tables.setdefault(key, set()).add(index)
    previous = None
    while previous != selected:
        previous = selected.copy()
        for rows in tables.values():
            if rows & selected:
                selected.update(rows)
                selected.update(neighbor for row in rows for neighbor in (row - 1, row + 1)
                                if 0 <= neighbor < len(spans))
    included = [span for index, span in enumerate(spans) if index in selected]
    omitted = [span for index, span in enumerate(spans) if index not in selected]
    return "".join(text[start:end] for start, end in included), {
        "mode": "excerpt" if omitted else "full",
        "reason": "literal_chapter_match" if matches else "no_reliable_match",
        "original_characters": len(text), "included_ranges": included, "omitted_ranges": omitted,
    }
