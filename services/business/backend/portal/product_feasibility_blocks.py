"""Adapt authored feasibility prose to the existing frozen document contract."""

import re

from .product_diagrams import heading_display_text
from .product_feasibility import chapter_requirements


# Existing variable-row prototypes, verified against the frozen feasibility profile.
_TABLES = {2: "table0", 3: "table28", 4: "table3", 5: "table10",
           6: "table1", 7: "table43", 8: "table65"}
_CAPTION = re.compile(r"^(?:附表|表)\s*\d+(?:[-.]\d+)*\s*\S.*$")
_HEADING = re.compile(r"^(#{2,3})[ \t]+(\S.*?)\s*$")
_SEPARATOR = re.compile(r":?-{3,}:?")


def _cells(line):
    parts, cell, escaped = [], [], False
    for char in line.strip():
        if char == "|" and not escaped:
            parts.append("".join(cell).strip())
            cell = []
        elif char == "|" and escaped:
            cell[-1] = "|"
        else:
            cell.append(char)
        escaped = char == "\\" and not escaped
    parts.append("".join(cell).strip())
    if line.strip().startswith("|"):
        parts.pop(0)
    if line.strip().endswith("|") and not escaped and parts[-1] == "":
        parts.pop()
    return parts


def _table(lines, start):
    caption = lines[start].strip()
    if not _CAPTION.fullmatch(caption) or len(caption) > 230:
        return None
    header = start + 1
    while header < len(lines) and not lines[header].strip():
        header += 1
    if header + 2 >= len(lines) or "|" not in lines[header]:
        return None
    columns, separator = _cells(lines[header]), _cells(lines[header + 1])
    if (len(columns) < 2 or len(columns) != len(separator)
            or any(not _SEPARATOR.fullmatch(value) for value in separator)
            or any(len(value) > 100 for value in columns)):
        return None
    rows, end = [], header + 2
    while end < len(lines) and lines[end].strip() and "|" in lines[end]:
        row = _cells(lines[end])
        if len(row) != len(columns) and not lines[end].strip().startswith("|"):
            break  # Ordinary prose containing a pipe is not an authored table row.
        if len(row) != len(columns) or any(len(value) > 10000 for value in row):
            return None  # Preserve malformed tables as text rather than dropping cells.
        rows.append([value or "待确认" for value in row])
        end += 1
    if not rows:
        return None
    columns = [value or "待确认" for value in columns]
    tables, offset = [], 0
    while offset < len(columns):
        width = min(8, len(columns) - offset)
        if len(columns) - offset - width == 1:
            width -= 1
        tables.append({"type": "table", "prototype": _TABLES[width],
                       "columns": columns[offset:offset + width], "units": ["—"] * width,
                       "rows": [row[offset:offset + width] for row in rows],
                       "caption": caption if not tables else f"{caption}（续{len(tables) + 1}）"})
        offset += width
    return tables, end


def authored_blocks(paragraphs, stable, sources, requirements):
    """Recognize only explicit headings and captioned, rectangular pipe tables.

    Wider tables use consecutive column groups supported by existing prototypes;
    all authored rows and cells survive, with no inferred values or synthetic rows.
    Empty source cells are explicitly pending because the contract forbids blanks.
    """
    if not isinstance(paragraphs, list) or any(not isinstance(value, str) for value in paragraphs):
        raise ValueError("authored paragraphs must be strings")
    lines = [line for paragraph in paragraphs for line in paragraph.splitlines()]
    blocks, index, has_h2 = [], 0, False
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        parsed = _table(lines, index)
        if parsed:
            tables, index = parsed
            blocks.extend(tables)
            continue
        match = _HEADING.fullmatch(line.strip())
        if match:
            text = heading_display_text(re.sub(r"\s+#+$", "", match[2]))
            if not text or len(text) > 160:
                blocks.append({"type": "paragraph", "text": line})
                index += 1
                continue
            level = len(match[1])
            if level == 2:
                has_h2 = True
            elif not has_h2:
                level = 2  # Keep orphan H3 content without skipping the existing H1.
            blocks.append({"type": "heading", "level": level, "text": text, "_literal": line})
        else:
            blocks.append({"type": "paragraph", "text": line})
        index += 1
    content = {2: False, 3: False}
    for block in reversed(blocks):
        if block["type"] == "heading":
            level = block["level"]
            literal = block.pop("_literal")
            if not content[level]:
                block.pop("level")
                block.update(type="paragraph", text=literal)
            for current in range(level, 4):
                content[current] = False
        else:
            content = {2: True, 3: True}
    for number, block in enumerate(blocks, 1):
        block.update(id=f"{stable}B{number}", source_ids=list(sources), requirement_ids=list(requirements))
    return blocks


def figure_plan(blueprint, chapter_id):
    """Use only figure requirements selected by the approved guide dispositions."""
    figures = {}
    for section in chapter_requirements(blueprint, chapter_id):
        for item in [section, *section.get("inherited_sections", [])]:
            # The guide offers package/class/SC as alternatives for one figure.
            if item.get("id") == "5.2.1.3":
                figures.setdefault("system-function-relationship", "系统功能关系图")
                continue
            for spec in item.get("table_figure_specs", []):
                if spec.get("kind") == "figure":
                    title = "应用系统架构图" if spec["id"] == "图5-7" else spec["title"]
                    figures.setdefault(spec["id"], title)
    return list(figures.values())
