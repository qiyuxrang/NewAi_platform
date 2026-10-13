"""Source-bound business/technology presentation runtime.

The process is intentionally deterministic: it turns the two persisted report
families into an editable PPTX without adding external facts. The visual
grammar is richer than the original text-only draft, while every content slide
keeps the report block references that support it.
"""

import json
import hashlib
import math
import re
import sys
from collections import Counter
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


CANVAS_W = 13.333
CANVAS_H = 7.5
COLORS = {
    "ink": "EAF2FF", "muted": "9FB1CC", "navy": "071426",
    "navy_2": "0B1F38", "panel": "102A46", "panel_2": "153553",
    "blue": "2563EB", "cyan": "22D3EE", "azure": "60A5FA",
    "green": "34D399", "amber": "FBBF24", "red": "FB7185", "white": "FFFFFF",
}
FONT = "Microsoft YaHei"
FAMILY_LABELS = {"technical-solution": "技术方案", "feasibility": "可行性研究"}
LOGO = Path(__file__).resolve().parent / "bj_docs" / "assets" / "company" / "company-logo.png"
SOURCE_MAX_BYTES = 16 * 1024 * 1024
BLOCK_MAX_COUNT = 10000
BLOCK_TYPES = {"heading", "paragraph", "table", "figure"}
EXCLUDED_REF_PREFIXES = ("DRAFT_NOTICE", "PENDING_")
PROHIBITED_COPY = (
    "待核草稿：未经正式内容、格式及产品负责人批准，不得作为正式方案使用。",
    "待核草稿 · 未获正式发布批准",
    "正式模板与样例、内容及格式批准尚未完成；本件始终为待核草稿。",
    "技术方案与可行性研究 · 待人工审核草稿",
    "内容来自平台当前报告版本，不继承正式业务批准",
    "平台自动生成的商务科技风待审草稿",
    "只使用当前报告来源；正式发布需要人工审核。",
)

# One content planner, six visual grammars. Style selection never changes facts.
STYLES = {
    "business": {"label": "商务汇报", "background": "F5F8FC", "ink": "152C48", "muted": "495C73", "accent": "174EA6", "panel": "E6EDF6", "cover": "split", "body": "columns"},
    "consulting": {"label": "决策咨询", "background": "FFFFFF", "ink": "172536", "muted": "4C5868", "accent": "A63E26", "panel": "F4EDE9", "cover": "statement", "body": "evidence-table"},
    "government": {"label": "政务立项", "background": "FFFCF7", "ink": "302C28", "muted": "5B514A", "accent": "913A30", "panel": "F1E9DE", "cover": "formal", "body": "numbered"},
    "engineering": {"label": "工程技术", "background": "F1F6FA", "ink": "102A43", "muted": "455C70", "accent": "126178", "panel": "DDEAF0", "cover": "technical", "body": "layers"},
    "dark-tech": {"label": "深色科技", "background": "071426", "ink": "EAF2FF", "muted": "B3C3DA", "accent": "22D3EE", "panel": "102A46", "cover": "dark", "body": "spotlight"},
    "minimal": {"label": "极简品牌", "background": "FAFAF8", "ink": "252923", "muted": "535A50", "accent": "416040", "panel": "ECEFE8", "cover": "minimal", "body": "single-point"},
}
GOALS = {"customer": "客户沟通", "department": "部门汇报", "decision": "立项决策"}


def select_style(data):
    context = data.get("planning_context", {})
    requested = context.get("style", "auto")
    if requested in STYLES:
        style, reason = requested, "沿用本次生成明确指定的视觉风格；报告事实与版本保持绑定。"
    else:
        # Purpose comes from project context, not generic equipment/report words.
        purpose = clean(" ".join(context.get(key, "") for key in ("purpose", "audience", "requirements")))
        rules = (
            ("government", ("政府立项", "政务立项", "正式评审", "政府评审")),
            ("consulting", ("投资决策", "管理层决策", "立项决策", "董事会", "备选决策")),
            ("engineering", ("技术评审", "方案评审", "技术交流", "工程评审")),
            ("dark-tech", ("深色成果演示", "深色科技演示", "深色产品展示")),
            ("minimal", ("品牌简明演示", "极简品牌", "品牌汇报")),
        )
        match = next(((name, token) for name, tokens in rules for token in tokens if token in purpose), None)
        style, reason = (match[0], f"项目汇报用途明确包含“{match[1]}”，匹配{STYLES[match[0]]['label']}。") if match else (
            "business", "用途未明确匹配专用风格，采用默认商务汇报。" if requested == "auto" else "风格设置不可识别，回退默认商务汇报。")
    goal = context.get("goal")
    if goal not in GOALS:
        purpose = context.get("purpose", "") + context.get("audience", "")
        goal = "decision" if any(word in purpose for word in ("决策", "立项", "评审", "董事会")) else "customer" if "客户" in purpose else "department"
    return style, goal, reason


def planning_warnings(data, selected_figures=None):
    warnings = []
    for family in FAMILY_LABELS:
        refs = [item["ref"] for item in source_blocks(data["blocks"], family, {"paragraph", "table"})[:1]]
        missing = [item for item in data.get("diagram_pending", []) if item["family"] == family]
        if missing:
            warnings.append({"text": f"{FAMILY_LABELS[family]}有 {len(missing)} 张图表待补；当前PPT未包含这些图。", "refs": refs})
        report = next((item for item in data.get("draft_quality", {}).get("reports", []) if item["family"] == family), {})
        if report.get("quality_issue_count"):
            text = f"{FAMILY_LABELS[family]}存在 {report['quality_issue_count']} 项质量提示，数量、来源与正文需复核。"
            if "output_length_below_target" in report.get("quality_issue_codes", []):
                text += "正文篇幅尚未达到要求。"
            warnings.append({"text": text, "refs": refs})
    if not any(item["type"] == "figure" for item in data["blocks"]):
        warnings.append({"text": "汇报PPT存在图文或布局质量提示：当前PPT未包含报告图表，图表待补。", "refs": []})
    elif any(figure_views(item)[0]["font_check"] == "not_verified" for item in data["blocks"] if item["type"] == "figure"
             and (selected_figures is None or item["ref"] in selected_figures)):
        warnings.append({"text": "报告原图标签字号缺少测量依据，图内18pt尚未核验；请对照原报告查看。", "refs": []})
    if any(copy in block_text(item) for item in data["blocks"] for copy in PROHIBITED_COPY):
        warnings.append({"text": "汇报PPT存在图文或布局质量提示：报告中的状态文案需核对。", "refs": []})
    return warnings


def figure_views(figure):
    with Image.open(figure["asset_path"]) as image:
        width, height = image.size
    evidence = figure.get("presentation_image_evidence", figure)
    word_width = evidence.get("width_mm")
    source_pt = evidence.get("min_font_pt")
    measured = (type(word_width) in (int, float) and 0 < word_width <= 1000
                and type(source_pt) in (int, float) and 0 < source_pt <= 100)
    display_width = min(11.65, 4.78 * width / height)
    if measured:
        required_width = 18 * word_width / source_pt / 25.4
        display_width = max(display_width, required_width)
    display_height = display_width * height / width
    # Overlapping windows retain every source pixel and connectors. The window
    # is a view of the same image bytes, never a fabricated re-drawn graph.
    columns = max(1, math.ceil(max(0, display_width - .35 - 1e-8) / (11.65 - .35)))
    rows = max(1, math.ceil(max(0, display_height - .35 - 1e-8) / (4.78 - .35)))
    if columns * rows > 60:
        raise ValueError("presentation source limit exceeded")
    views = []
    for row in range(rows):
        for column in range(columns):
            x = min(column * (11.65 - .35), max(0, display_width - 11.65))
            y = min(row * (4.78 - .35), max(0, display_height - 4.78))
            views.append({"x": x, "y": y, "width": min(display_width, 11.65), "height": min(display_height, 4.78),
                "display_width": display_width, "display_height": display_height,
                "minimum_label_pt": source_pt * display_width * 25.4 / word_width if measured else None,
                "font_check": "measured" if measured else "not_verified"})
    return views


def build_plan(data):
    style, goal, reason = select_style(data)
    theme = STYLES[style]
    chapters = build_chapters(data["blocks"])
    if not all(any(item["family"] == family for item in chapters) for family in FAMILY_LABELS):
        raise ValueError("both report families must contribute chapters")
    pages = []

    def page(title, kind, blocks=(), items=None, **extra):
        pages.append({"page": len(pages) + 1, "title": excerpt(title, 33), "type": kind,
            "core_message": excerpt(title, 100), "source_refs": list(dict.fromkeys(item["ref"] for item in blocks)),
            "items": items if items is not None else [excerpt(block_text(item), 106) for item in blocks],
            "speaker_notes": "\n\n".join(block_text(item) for item in blocks), **extra})

    def figure_page(figure):
        views = figure_views(figure)
        for index, view in enumerate(views, 1):
            suffix = f"（阅读窗 {index}/{len(views)}）" if len(views) > 1 else ""
            page(block_text(figure) + suffix, "source-figure", [figure], asset_ref=figure["ref"], image_view=view,
                 reading_window=index, reading_window_count=len(views),
                 edit_boundary="报告原图为图片，图内标签不能逐项编辑；页标题、来源与备注可编辑。")

    page(display_title(data.get("title", "项目方案汇报")), "cover")
    summary = [item for family in FAMILY_LABELS for item in select_summary_blocks(
        data["blocks"], family, 1, types={"paragraph", "table"})]
    if summary:
        capacity = 1 if style == "minimal" else 2
        for start in range(0, len(summary), capacity):
            page("核心判断与报告依据" if goal == "decision" else "项目方案的核心要点", "summary", summary[start:start + capacity])
    # Preserve the same core content when only style changes. Minimal style may
    # split it into more pages; audience/goal alone controls narrative ordering.
    if goal == "decision":
        chapters.sort(key=lambda item: (item["family"] != "feasibility", not any(
            token in item["title"] for token in ("结论", "建议", "风险", "可行性"))))
    figures = [item for item in data["blocks"] if eligible_block(item) and item["type"] == "figure"]
    chosen_figures = []
    for family in FAMILY_LABELS:
        chosen_figures.extend([item for item in figures if item["ref"].startswith(family + ":")][:2])
    for chapter in chapters:
        body = [item for item in chapter["blocks"] if item["type"] in {"paragraph", "table"} and block_text(item)]
        selected = body[:4]
        risk = next((item for item in body[4:] if any(token in block_text(item) for token in ("风险", "待确认", "缺少", "未落实"))), None)
        if risk:
            selected.append(risk)
        if not selected:
            continue
        title = chapter["title"]
        kind = "analysis"
        if any(token in title for token in ("风险", "安全", "不确定")):
            kind = "risk"
        elif any(token in title for token in ("对比", "比较", "备选", "选择")):
            kind = "comparison"
        elif any(token in title for token in ("实施", "阶段", "流程", "验收")):
            kind = "process"
        elif any(token in title for token in ("架构", "接口", "部署", "配置", "技术路线")):
            kind = "architecture"
        capacity = 1 if style == "minimal" else 2 if style in {"business", "dark-tech"} else 3
        for start in range(0, len(selected), capacity):
            chunk = selected[start:start + capacity]
            suffix = f"（{start // capacity + 1}）" if len(selected) > capacity else ""
            page(title + suffix, kind, [chunk[0], *chunk[1:]], section=FAMILY_LABELS[chapter["family"]], chapter_ref=chapter["ref"])
        # Figure copies remain exact source images, on their own broad canvas.
        family_figures = [item for item in chosen_figures if item["ref"].startswith(chapter["family"] + ":")]
        if family_figures:
            figure = family_figures[0]
            chosen_figures.remove(figure)
            figure_page(figure)
    for figure in chosen_figures:
        figure_page(figure)
    warnings = planning_warnings(data, {item["asset_ref"] for item in pages if item["type"] == "source-figure"})
    known = {item["ref"] for item in data["blocks"]}
    pending = [*warnings, *data.get("pending", [])]
    pending_capacity = 1 if style == "minimal" else 2 if style in {"business", "dark-tech"} else 3
    for start in range(0, len(pending), pending_capacity):
        values = pending[start:start + pending_capacity]
        refs = {ref for item in values for ref in item.get("refs", []) if ref in known}
        blocks = [item for item in data["blocks"] if item["ref"] in refs]
        page("风险与未落实事项", "pending", blocks, items=[excerpt(item.get("text", ""), 106) for item in values])
    conclusion = [item for item in data["blocks"] if eligible_block(item) and item["type"] == "paragraph"
                  and any(token in block_text(item) for token in ("建议", "结论", "下一步"))][:2]
    if conclusion:
        capacity = 1 if style == "minimal" else 2
        for start in range(0, len(conclusion), capacity):
            page("报告结论与下一步", "conclusion", conclusion[start:start + capacity])
    context = data.get("planning_context", {})
    return {"schema_version": 1, "style": style, "style_label": theme["label"], "selection_reason": reason,
        "goal": goal, "goal_label": GOALS[goal], "audience": context.get("audience", "") or "未明确指定",
        "purpose": context.get("purpose", "") or GOALS[goal], "sources": data["sources"],
        "pair_hash": data.get("sha256", ""), "input_hash": data.get("input_hash", ""), "blueprint_hash": data.get("blueprint_hash", ""),
        "pipeline": ["报告依据", "汇报叙事", "逐页大纲", "视觉规范", "逐页生成", "程序检查", "可编辑导出"],
        "design": {"canvas": "16:9", "colors": {key: theme[key] for key in ("background", "ink", "muted", "accent", "panel")},
            "font": FONT, "title_pt": 34, "body_pt": 24, "minimum_body_pt": 20, "minimum_node_pt": 18,
            "minimum_source_pt": 12, "margin_inches": 0.7, "icon_style": "native-geometric", "brand": "平台通用视觉",
            "images": [{"ref": item["ref"], "sha256": hashlib.sha256(Path(item["asset_path"]).read_bytes()).hexdigest()} for item in figures]},
        "constraints": {"max_points_per_page": 3, "overflow": "split_page", "editable": "正文、图形、来源和备注；报告原图为图片",
            "model_review": "not_run", "correction_budget": 1, "optional_images_block_generation": False},
        "suggested_pages": "20—30；依据论证范围与可读性确定，不为凑页增加内容", "pages": pages,
        "warnings": warnings, "locked": True}


def rgb(value):
    return RGBColor.from_string(value)


def clean(value):
    return " ".join(str(value or "").replace("\u0000", " ").split())


def eligible_block(block):
    return (block.get("type") in BLOCK_TYPES
            and not block["ref"].split(":", 1)[1].startswith(EXCLUDED_REF_PREFIXES))


def block_text(block):
    if block.get("type") == "figure":
        return clean(block.get("caption") or block.get("alt") or block.get("text"))
    if block.get("type") == "table":
        return clean(block.get("caption") or block.get("text") or "报告表格")
    return clean(block.get("text"))


def source_blocks(blocks, family=None, types=None):
    prefix = family + ":" if family else None
    return [block for block in blocks
            if eligible_block(block)
            and (prefix is None or block["ref"].startswith(prefix))
            and (types is None or block.get("type") in types)
            and block_text(block)]


def select_summary_blocks(blocks, family, limit, *, types=None, excluded=()):
    candidates = source_blocks(blocks, family, types)
    excluded = set(excluded)
    selected = []
    # Round-robin chapter content before filling remaining slots with headings.
    # A long table of contents must not displace every substantive conclusion.
    chapters = {}
    current = {}
    for block in candidates:
        block_family = block["ref"].split(":", 1)[0]
        if block.get("type") == "heading" and block.get("level", 1) == 1:
            current[block_family] = block["ref"]
        key = (block_family, current.get(block_family, "intro"))
        if block.get("type") in {"paragraph", "table"} and block["ref"] not in excluded:
            chapters.setdefault(key, []).append(block)
    depth = 0
    while any(depth < len(values) for values in chapters.values()):
        for values in chapters.values():
            if depth < len(values):
                selected.append(values[depth])
                if len(selected) == limit:
                    return selected
        depth += 1
    selected_refs = {block["ref"] for block in selected}
    priorities = (lambda block: block.get("type") == "heading" and block.get("level") == 1,
                  lambda block: True)
    for priority in priorities:
        for block in candidates:
            if block["ref"] not in excluded and block["ref"] not in selected_refs and priority(block):
                selected.append(block)
                selected_refs.add(block["ref"])
                if len(selected) == limit:
                    return selected
    return selected


def set_source_notes(slide, refs):
    values = list(dict.fromkeys(ref for ref in refs if isinstance(ref, str) and ref))
    slide.notes_slide.notes_text_frame.text = "source_refs" + ("\n" + "\n".join(values) if values else "")


def display_title(value):
    value = re.sub(r"[（(](?:代表性)?(?:草稿|待审稿)[）)]\s*$", "", clean(value)).strip()
    return value.replace("三件套", "综合方案汇报")


def excerpt(value, limit=120):
    text = clean(value)
    if len(text) <= limit:
        return text
    start = max(40, limit - 45)
    boundary = max(text.rfind(mark, start, limit + 1) for mark in "。！？；，、")
    if boundary >= start:
        return text[: boundary + 1]
    return text[:limit].rstrip("，。、；：,. ") + "…"


def set_text(shape, text, size, color, *, bold=False, align=PP_ALIGN.LEFT,
             valign=MSO_ANCHOR.TOP, margin=0.06, font=FONT):
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(margin)
    frame.margin_top = frame.margin_bottom = Inches(margin)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.space_after = Pt(0)
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    return shape


def text_box(slide, x, y, w, h, text, size=18, color=COLORS["ink"], **kwargs):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    return set_text(box, text, size, color, **kwargs)


def contained_picture(slide, image_path, x, y, width, height):
    """Keep every source pixel inside its reserved box without distortion."""
    left, top, box_width, box_height = map(Inches, (x, y, width, height))
    if box_width <= 0 or box_height <= 0:
        raise ValueError("image container must have positive dimensions")
    with Image.open(image_path) as image:
        pixel_width, pixel_height = image.size
    scale = min(box_width / pixel_width, box_height / pixel_height)
    picture_width = max(1, round(pixel_width * scale))
    picture_height = max(1, round(pixel_height * scale))
    return slide.shapes.add_picture(str(image_path),
        left + (box_width - picture_width) // 2, top + (box_height - picture_height) // 2,
        width=picture_width, height=picture_height)


def rect(slide, x, y, w, h, fill, *, line=None, radius=False):
    geometry = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(geometry, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line or fill)
    shape.line.width = Pt(0.8 if line else 0)
    return shape


def add_line(slide, x1, y1, x2, y2, color=COLORS["blue"], width=2.2):
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    line.line.color.rgb = rgb(color)
    line.line.width = Pt(width)
    return line


def add_slide(prs, title, section, page, layout_name, refs=()):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(COLORS["navy"])
    rect(slide, 0, 0, 0.1, CANVAS_H, COLORS["cyan"])
    text_box(slide, 0.58, 0.38, 10.8, 0.52, title, 27, COLORS["white"], bold=True)
    text_box(slide, 11.72, 0.41, 0.92, 0.32, f"{page:02d}", 12, COLORS["cyan"], bold=True, align=PP_ALIGN.RIGHT)
    text_box(slide, 0.62, 7.04, 2.9, 0.2, section, 8.5, COLORS["muted"], bold=True)
    ref_text = "内容来源：技术方案与可行性研究报告"
    text_box(slide, 6.5, 6.98, 5.55, 0.28, ref_text, 8, COLORS["muted"], align=PP_ALIGN.RIGHT)
    set_source_notes(slide, refs)
    return slide


def cover(prs, data, hero=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(COLORS["navy"])
    rect(slide, 0, 0, 13.333, 0.13, COLORS["cyan"])
    rect(slide, 8.15, 0, 5.18, 7.5, COLORS["navy_2"])
    if LOGO.is_file():
        slide.shapes.add_picture(str(LOGO), Inches(0.72), Inches(0.62), width=Inches(1.05))
    text_box(slide, 0.72, 1.62, 6.9, 1.55, excerpt(display_title(data.get("title", "项目方案汇报")), 58), 34, COLORS["white"], bold=True)
    text_box(slide, 0.75, 3.52, 5.8, 0.65, "技术方案与可行性研究报告", 18, COLORS["cyan"], bold=True)
    text_box(slide, 0.75, 5.92, 6.4, 0.5, "项目方案成果汇报", 13, COLORS["muted"])
    if hero and Path(hero["asset_path"]).is_file():
        panel=rect(slide,8.55,1.25,4.25,4.85,"FFFFFF",line=COLORS["cyan"],radius=True)
        panel.fill.transparency=4
        contained_picture(slide, hero["asset_path"], 8.75, 1.72, 3.85, 3.95)
        text_box(slide,8.77,5.74,3.75,0.32,excerpt(block_text(hero), 24),11,COLORS["navy"],bold=True,align=PP_ALIGN.CENTER)
    else:
        for index,(size,color) in enumerate(((3.8,COLORS["panel_2"]),(2.75,COLORS["blue"]),(1.65,COLORS["cyan"]))):
            shape=slide.shapes.add_shape(MSO_SHAPE.OVAL,Inches(9.0+index*.53),Inches(1.25+index*.53),Inches(size),Inches(size))
            shape.fill.background(); shape.line.color.rgb=rgb(color); shape.line.width=Pt(2.2)
    set_source_notes(slide, [hero["ref"]] if hero else [])
    return slide


def add_visual_panel(slide, block, x, y, w, h, title=None):
    panel = rect(slide, x, y, w, h, "FFFFFF", line=COLORS["panel_2"], radius=True)
    panel.fill.transparency = 2
    contained_picture(slide, block["asset_path"], x + 0.18, y + 0.42, w - 0.36, h - 0.72)
    text_box(slide, x + 0.22, y + 0.08, w - 0.44, 0.28,
             title or block.get("caption") or "方案图示", 10.5, COLORS["navy"],
             bold=True, align=PP_ALIGN.CENTER)


def build_chapters(blocks):
    chapters = []
    active = {}
    for family in ("technical-solution", "feasibility"):
        active[family] = None
        selected = [item for item in blocks if item["ref"].startswith(family + ":")]
        for block in selected:
            local_ref = block["ref"].split(":", 1)[1]
            if local_ref.startswith(("DRAFT_NOTICE", "PENDING_")):
                continue
            if block.get("type") == "heading" and block.get("level", 1) == 1:
                chapter = {"family": family, "title": clean(block.get("text")) or "章节内容",
                           "ref": block["ref"], "blocks": []}
                chapters.append(chapter)
                active[family] = chapter
            elif block.get("type") in {"heading", "paragraph", "table"}:
                if active[family] is None:
                    chapter = {"family": family, "title": FAMILY_LABELS[family],
                               "ref": block["ref"], "blocks": []}
                    chapters.append(chapter)
                    active[family] = chapter
                active[family]["blocks"].append(block)
    return chapters


def load_source(source):
    if source.stat().st_size > SOURCE_MAX_BYTES:
        raise ValueError("presentation source limit exceeded")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ValueError("invalid slide source") from None
    if (not isinstance(data, dict)
            or not isinstance(data.get("title", ""), str)
            or len(data.get("title", "")) > 500):
        raise ValueError("invalid slide source")
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != len(FAMILY_LABELS):
        raise ValueError("invalid slide source")
    families = []
    for item in sources:
        if (not isinstance(item, dict)
                or item.get("family") not in FAMILY_LABELS
                or not isinstance(item.get("id"), str) or not 1 <= len(item["id"]) <= 100
                or type(item.get("version")) is not int or item["version"] < 1
                or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in item["sha256"].lower())):
            raise ValueError("invalid slide source")
        families.append(item["family"])
    if set(families) != set(FAMILY_LABELS) or len(set(families)) != len(families):
        raise ValueError("invalid slide source")
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("invalid slide source")
    if len(blocks) > BLOCK_MAX_COUNT:
        raise ValueError("presentation source limit exceeded")
    if not blocks:
        raise ValueError("invalid slide source")
    refs = []
    for item in blocks:
        if not isinstance(item, dict):
            raise ValueError("invalid slide source")
        ref = item.get("ref")
        block_type = item.get("type")
        if (not isinstance(ref, str) or not 3 <= len(ref) <= 200 or ":" not in ref
                or any(ord(character) < 32 for character in ref)
                or block_type not in BLOCK_TYPES):
            raise ValueError("invalid slide source")
        family, local_ref = ref.split(":", 1)
        if family not in FAMILY_LABELS or not local_ref:
            raise ValueError("invalid slide source")
        for field in ("text", "caption", "alt"):
            value = item.get(field, "")
            if not isinstance(value, str) or len(value) > 100_000:
                raise ValueError("invalid slide source")
        if block_type == "heading" and (type(item.get("level", 1)) is not int
                                         or not 1 <= item.get("level", 1) <= 9):
            raise ValueError("invalid slide source")
        if "asset_path" in item and (not isinstance(item["asset_path"], str)
                                     or not item["asset_path"] or len(item["asset_path"]) > 4096
                                     or "\x00" in item["asset_path"]):
            raise ValueError("invalid slide source")
        if "presentation_image_evidence" in item:
            evidence = item["presentation_image_evidence"]
            if (not isinstance(evidence, dict) or any(type(evidence.get(key)) not in (int, float)
                    or not math.isfinite(evidence[key]) or not 0 < evidence[key] <= 1000 for key in ("width_mm", "min_font_pt"))):
                raise ValueError("invalid slide source")
        refs.append(ref)
    if len(refs) != len(set(refs)):
        raise ValueError("invalid slide source")
    if type(data.get("draft_mode", False)) is not bool:
        raise ValueError("invalid slide source")
    context = data.get("planning_context", {})
    if (not isinstance(context, dict) or any(not isinstance(context.get(key, ""), str)
            or len(context.get(key, "")) > 20000 for key in ("style", "goal", "audience", "purpose", "requirements"))):
        raise ValueError("invalid slide source")
    for block in blocks:
        if block["type"] == "figure" and not (block.get("asset_path") and Path(block["asset_path"]).is_file()):
            raise ValueError("invalid slide source")
    pending = data.get("diagram_pending", [])
    reports = data.get("draft_quality", {}).get("reports", []) if isinstance(data.get("draft_quality", {}), dict) else None
    if not isinstance(pending, list) or len(pending) > BLOCK_MAX_COUNT or not isinstance(reports, list) or len(reports) > 2:
        raise ValueError("invalid slide source")
    for item in pending:
        if (not isinstance(item, dict) or item.get("family") not in FAMILY_LABELS
                or not isinstance(item.get("figure_id"), str) or not 1 <= len(item["figure_id"]) <= 100):
            raise ValueError("invalid slide source")
    if len({(item["family"], item["figure_id"]) for item in pending}) != len(pending):
        raise ValueError("invalid slide source")
    for item in reports:
        if (not isinstance(item, dict) or item.get("family") not in FAMILY_LABELS
                or type(item.get("quality_issue_count", 0)) is not int or not 0 <= item.get("quality_issue_count", 0) <= BLOCK_MAX_COUNT
                or not isinstance(item.get("quality_issue_codes", []), list)
                or len(item.get("quality_issue_codes", [])) > 100
                or any(not isinstance(code, str) or not 1 <= len(code) <= 100 for code in item.get("quality_issue_codes", []))):
            raise ValueError("invalid slide source")
    if len({item["family"] for item in reports}) != len(reports):
        raise ValueError("invalid slide source")
    return data


def source_mapping(prs, eligible_refs, all_refs):
    declared = set()
    for slide in prs.slides:
        if not slide.has_notes_slide:
            continue
        lines = slide.notes_slide.notes_text_frame.text.splitlines()
        if lines and lines[0] == "source_refs":
            for line in lines[1:]:
                if not line:
                    break
                declared.add(line)
    eligible_refs = set(eligible_refs)
    all_refs = set(all_refs)
    return {
        "mapped_source_refs": sorted(declared),
        "omitted_source_refs": sorted(eligible_refs - declared),
        "missing_source_refs": sorted(declared - all_refs),
    }


def planned_text(slide, x, y, w, h, value, theme, *, role="body", size=24, bold=False, color=None):
    # Fonts are actual exported pt; no Office/autofit shrinking is enabled.
    shape = text_box(slide, x, y, w, h, value, size, color or theme["ink"], bold=bold, margin=0.025)
    shape.name = "ppt:" + role
    return shape


def render_planned_page(prs, page, plan, blocks):
    theme = STYLES[plan["style"]]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(theme["background"])
    style = plan["style"]
    kind = page["type"]
    refs = page["source_refs"]
    set_source_notes(slide, refs)
    if page["speaker_notes"]:
        slide.notes_slide.notes_text_frame.text += "\n\n讲解备注\n" + page["speaker_notes"]
    # The raw block identifiers stay in notes/manifest, never in audience copy.
    source_labels = [FAMILY_LABELS[source["family"]] + f" v{source['version']}" for source in plan["sources"]
                     if not refs or any(ref.startswith(source["family"] + ":") for ref in refs)]
    planned_text(slide, .7, 7.0, 11.25, .3, "来源：" + "、".join(source_labels), theme, role="source", size=12, color=theme["muted"])
    planned_text(slide, 12.05, 7.0, .55, .3, str(page["page"]), theme, role="source", size=12)
    if kind == "cover":
        cover_mode = theme["cover"]
        if cover_mode in {"split", "dark"}:
            rect(slide, 9.1, .6, 3.55, 5.9, theme["panel"])
            for index in range(3):
                rect(slide, 9.7, 1.55 + index * 1.25, 2.4 - index * .4, .15, theme["accent"])
            title_box = (.8, 1.7, 7.7, 2.45)
        elif cover_mode == "formal":
            rect(slide, .7, 1.3, 11.9, .08, theme["accent"])
            rect(slide, .7, 5.9, 11.9, .08, theme["accent"])
            title_box = (1.1, 2.0, 11.05, 2.1)
        elif cover_mode == "technical":
            for index in range(3):
                rect(slide, 9.2, 1.45 + index * 1.45, 3.3, 1.0, theme["panel"], line=theme["accent"])
            title_box = (.8, 1.7, 7.85, 2.4)
        elif cover_mode == "statement":
            rect(slide, .8, 1.0, 1.3, .13, theme["accent"])
            title_box = (.8, 1.7, 11.6, 2.4)
        else:
            title_box = (1.0, 2.0, 11.3, 2.3)
        planned_text(slide, *title_box, page["title"], theme, role="title", size=40, bold=True)
        planned_text(slide, .95, 4.65, 10.8, .6, plan["goal_label"] + " · " + plan["style_label"], theme, size=24, color=theme["accent"])
        return slide, "cover:" + cover_mode
    if style == "government":
        planned_text(slide, .75, .28, 11.5, .28, "项目建设汇报", theme, role="source", size=12, color=theme["muted"])
        rect(slide, .7, 1.32, 11.9, .04, theme["accent"])
    else:
        rect(slide, .7, .53, .12, .7, theme["accent"])
    planned_text(slide, .98, .5, 11.45, 1.1, page["title"], theme, role="title", size=34, bold=True)
    if kind == "source-figure":
        block = blocks[page["asset_ref"]]
        view = page["image_view"]
        picture = slide.shapes.add_picture(block["asset_path"], Inches(.85 + (11.65 - view["width"]) / 2),
            Inches(1.65 + (4.78 - view["height"]) / 2), width=Inches(view["width"]), height=Inches(view["height"]))
        picture.crop_left, picture.crop_top = view["x"] / view["display_width"], view["y"] / view["display_height"]
        picture.crop_right = max(0, 1 - (view["x"] + view["width"]) / view["display_width"])
        picture.crop_bottom = max(0, 1 - (view["y"] + view["height"]) / view["display_height"])
        copy = "报告原图；图内文字为图片。"
        if view["font_check"] == "not_verified":
            copy += "原图标签字号缺少测量依据，阅读时请对照报告。"
        elif page["reading_window_count"] > 1:
            copy += f"连续阅读窗 {page['reading_window']}/{page['reading_window_count']}，相邻窗保留重叠关系。"
        planned_text(slide, .85, 6.53, 11.6, .32, copy, theme, role="source", size=12, color=theme["muted"])
        return slide, "source-figure:wide"
    values = page["items"]
    if kind == "architecture":
        # Report excerpts form evidence layers. No speculative dependency edges.
        for index, value in enumerate(values):
            y = 1.72 + index * 1.48
            rect(slide, .85, y, 11.65, 1.27, theme["panel"], line=theme["accent"])
            planned_text(slide, 1.12, y + .13, 11.05, 1.0, value, theme, role="node", size=20, bold=True)
        return slide, "architecture:evidence-layers"
    if kind in {"comparison", "risk"} or theme["body"] == "evidence-table":
        # Keep quoted alternatives/risks, without fabricating scores or axes.
        table_shape = slide.shapes.add_table(len(values) + 1, 2, Inches(.85), Inches(1.72), Inches(11.65), Inches(4.82))
        table_shape.name = "ppt:table"
        table = table_shape.table
        table.columns[0].width, table.columns[1].width = Inches(1.8), Inches(9.85)
        table.rows[0].height = Inches(.58)
        rows = [("条目", "报告依据"), *[(str(index + 1), value) for index, value in enumerate(values)]]
        for row_index, row in enumerate(rows):
            if row_index:
                table.rows[row_index].height = Inches(4.24 / max(1, len(values)))
            for col_index, value in enumerate(row):
                cell = table.cell(row_index, col_index)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(theme["panel"] if row_index % 2 == 0 else theme["background"])
                cell.margin_left = cell.margin_right = Inches(.12)
                cell.margin_top = cell.margin_bottom = Inches(.08)
                cell.text = value
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.name, run.font.size = FONT, Pt(20 if row_index else 18)
                        run.font.color.rgb = rgb(theme["ink"])
                        run.font.bold = row_index == 0
        return slide, kind + ":evidence-table"
    if kind == "process" or theme["body"] == "numbered":
        for index, value in enumerate(values):
            y = 1.75 + index * 1.57
            planned_text(slide, .92, y, .7, .65, f"{index + 1:02d}", theme, role="node", size=24, color=theme["accent"], bold=True)
            planned_text(slide, 1.85, y, 10.5, 1.35, value, theme, size=24)
            add_line(slide, 1.85, y + 1.43, 12.35, y + 1.43, theme["panel"], 1)
        return slide, kind + ":numbered-route"
    if theme["body"] == "layers":
        for index, value in enumerate(values):
            y = 1.75 + index * 1.48
            rect(slide, .85, y, .12, 1.2, theme["accent"])
            rect(slide, 1.15, y, 11.2, 1.23, theme["panel"])
            planned_text(slide, 1.42, y + .12, 10.65, 1.0, value, theme, size=20)
        return slide, kind + ":technical-layers"
    if theme["body"] == "single-point":
        planned_text(slide, 1.15, 2.1, 10.9, 3.95, values[0] if values else "", theme, size=30)
        return slide, kind + ":single-point"
    if theme["body"] == "spotlight":
        if values:
            planned_text(slide, .95, 1.8, 11.4, 1.8, values[0], theme, size=28, bold=True)
        rect(slide, .95, 3.92, 11.35, .06, theme["accent"])
        if len(values) > 1:
            planned_text(slide, .95, 4.42, 11.4, 1.78, values[1], theme, size=24, color=theme["muted"])
        return slide, kind + ":spotlight"
    for index, value in enumerate(values):
        x = .85 + index * 6.0
        rect(slide, x, 1.72, 5.6, .12, theme["accent"])
        planned_text(slide, x + .07, 2.02, 5.43, 4.32, value, theme, size=24)
    return slide, kind + ":columns"


def exported_checks(prs, plan):
    issues = []
    native_shapes = 0
    for page_number, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.left < 0 or shape.top < 0 or shape.left + shape.width > prs.slide_width + 20 or shape.top + shape.height > prs.slide_height + 20:
                issues.append({"page": page_number, "reason": "object_out_of_canvas", "shape": shape.name})
            if getattr(shape, "has_table", False):
                native_shapes += 1
                cells = [cell for row in shape.table.rows for cell in row.cells]
                frames = [(cell.text_frame, 18, shape.table.columns[index % 2].width, shape.table.rows[index // 2].height)
                          for index, cell in enumerate(cells)]
            elif getattr(shape, "has_text_frame", False):
                native_shapes += 1
                role = shape.name.split(":", 1)[-1]
                minimum = 12 if role == "source" else 18 if role == "node" else 20
                frames = [(shape.text_frame, minimum, shape.width, shape.height)]
            else:
                continue
            for frame, minimum, width, height in frames:
                runs = [run for paragraph in frame.paragraphs for run in paragraph.runs if run.text]
                if not runs:
                    continue
                if any(run.font.size is None or run.font.size.pt < minimum for run in runs):
                    issues.append({"page": page_number, "reason": "font_below_minimum", "shape": shape.name})
                # Conservative CJK width/line estimate, not a claim of Office pixel QA.
                size = max(run.font.size.pt for run in runs if run.font.size)
                usable_w = max(1, width / 12700 - (frame.margin_left + frame.margin_right) / 12700)
                usable_h = max(1, height / 12700 - (frame.margin_top + frame.margin_bottom) / 12700)
                lines = 0
                for paragraph in frame.paragraphs:
                    weight = sum(1 if ord(char) > 255 else .52 for char in paragraph.text)
                    lines += max(1, math.ceil(weight * size / usable_w))
                if lines * size * 1.2 > usable_h + size * .3:
                    issues.append({"page": page_number, "reason": "estimated_text_overflow", "shape": shape.name})
    image_checks = [{"page": page["page"], "source_ref": page["asset_ref"], **page["image_view"]}
                    for page in plan["pages"] if page["type"] == "source-figure"]
    for item in image_checks:
        if item["minimum_label_pt"] is not None and item["minimum_label_pt"] < 18 - 0.01:
            issues.append({"page": item["page"], "reason": "source_image_font_below_minimum"})
    return {"status": "pass" if not issues else "fail", "issues": issues, "editable_text_or_table_objects": native_shapes,
            "minimum_body_pt": 20, "minimum_node_pt": 18, "minimum_source_pt": 12,
            "source_image_checks": image_checks, "source_image_fonts": "not_verified" if any(item["font_check"] == "not_verified" for item in image_checks) else "measured",
            "text_fit_method": "conservative_cjk_estimate", "office_visual_check": "not_run"}


def write_progress(source, plan, stage, completed):
    # One atomic sidecar; the parent reads actual rendered pages, never a timer.
    plan = {**plan, "pages": [{**page, "page": index} for index, page in enumerate(plan["pages"], 1)]}
    target = source.with_suffix(".progress.json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"stage": stage, "completed_count": completed,
        "total_count": len(plan["pages"]), "plan": plan}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    try:
        temporary.replace(target)
    except PermissionError:
        # Windows can briefly lock the sidecar while the parent reads it.
        # Skip this notification; the next real page and final artifact report progress.
        temporary.unlink(missing_ok=True)


def main():
    source, target = map(Path, sys.argv[1:])
    data = load_source(source)
    plan = build_plan(data)
    # Persist the locked outline before any page generation, beside pair.json.
    plan_path = source.with_suffix(".plan.json")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    write_progress(source, plan, "planning", 0)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(CANVAS_W), Inches(CANVAS_H)
    prs.core_properties.title = display_title(data.get("title"))
    prs.core_properties.subject = plan["style_label"] + " · " + plan["goal_label"]
    prs.core_properties.comments = "依据当前两份报告生成，文字、表格与普通图形可编辑。"
    blocks = {item["ref"]: item for item in data["blocks"]}
    inventory = Counter()
    for page in plan["pages"]:
        _, layout = render_planned_page(prs, page, plan, blocks)
        page["layout"] = layout
        inventory[layout] += 1
        write_progress(source, plan, "rendering", page["page"])
    checks = exported_checks(prs, plan)
    # A bounded correction splits only overflowing content pages. Valid pages
    # and source objects remain untouched, never shrink key text to fit.
    overflowing = {item["page"] for item in checks["issues"] if item["reason"] == "estimated_text_overflow"}
    repaired = []
    for page in plan["pages"]:
        if page["page"] not in overflowing or page["type"] in {"cover", "source-figure"}:
            repaired.append(page)
            continue
        for item in page["items"]:
            # A long point is split at a real sentence boundary or preserved
            # exact character boundary; full paragraphs remain in notes.
            segments = [item[start:start + 72] for start in range(0, len(item), 72)] or [""]
            for segment in segments:
                repaired.append({**page, "items": [segment], "continuation_of": page["page"]})
    if overflowing:
        write_progress(source, {**plan, "pages": repaired}, "repairing", 0)
        # Reuse already-rendered page XML for unchanged pages. Only corrected
        # slides are authored again, then reordered in the existing package.
        original_ids = list(prs.slides._sldIdLst)
        original_pages = {page["page"]: index for index, page in enumerate(plan["pages"])}
        ordered_ids = []
        inventory.clear()
        for index, page in enumerate(repaired, 1):
            original_number = page["page"]
            page["page"] = index
            if "continuation_of" in page:
                _, layout = render_planned_page(prs, page, plan, blocks)
                ordered_ids.append(prs.slides._sldIdLst[-1])
            else:
                slide_id = original_ids[original_pages[original_number]]
                slide = prs.part.related_slide(slide_id.rId)
                for shape in slide.shapes:
                    if shape.name == "ppt:source" and shape.left > Inches(12):
                        shape.text_frame.paragraphs[0].runs[0].text = str(index)
                ordered_ids.append(slide_id)
                layout = page.get("layout", page["type"] + ":" + STYLES[plan["style"]]["body"])
            page["layout"] = layout
            inventory[layout] += 1
            write_progress(source, {**plan, "pages": repaired}, "repairing", index)
        for slide_id in list(prs.slides._sldIdLst):
            prs.slides._sldIdLst.remove(slide_id)
            if slide_id not in ordered_ids:
                prs.part.drop_rel(slide_id.rId)
        for slide_id in ordered_ids:
            prs.slides._sldIdLst.append(slide_id)
        plan["pages"] = repaired
    write_progress(source, plan, "validating", len(plan["pages"]))
    prs.save(target)
    rendered = Presentation(str(target))
    checks = exported_checks(rendered, plan)
    checks["correction_attempts"] = int(bool(overflowing))
    plan["program_checks"] = checks
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    write_progress(source, plan, "validating", len(plan["pages"]))
    eligible = {item["ref"] for item in data["blocks"] if eligible_block(item)}
    mapping = source_mapping(rendered, eligible, blocks)
    mapped = set(mapping["mapped_source_refs"])
    body_coverage = {}
    for family in FAMILY_LABELS:
        available = {item["ref"] for item in source_blocks(data["blocks"], family, {"paragraph", "table"})}
        body_coverage[family] = {"available": len(available), "mapped": len(available & mapped)}
    image_count = sum(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for slide in rendered.slides for shape in slide.shapes)
    editable_visuals = (sum(bool(getattr(shape, "has_table", False)) for slide in rendered.slides for shape in slide.shapes)
                        + sum(page["type"] in {"architecture", "process"} for page in plan["pages"]))
    text = "\n".join(shape.text for slide in rendered.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False))
    reasons = []
    if not image_count:
        reasons.append("visual_assets_missing")
    elif checks["source_image_fonts"] == "not_verified":
        reasons.append("source_image_font_unverified")
    prohibited = [copy for copy in PROHIBITED_COPY if copy in text]
    if prohibited:
        reasons.append("copy_review_required")
    reports = data.get("draft_quality", {}).get("reports", [])
    pending = data.get("diagram_pending", [])
    source_valid = bool(mapped and not mapping["missing_source_refs"] and all(not item["available"] or item["mapped"] for item in body_coverage.values()))
    warning = bool(reasons or pending or any(item.get("quality_issue_count", 0) for item in reports))
    passed = source_valid and checks["status"] == "pass" and not warning
    quality = {"engine": "business-tech-pptx", "engine_version": "v5", "design_profile": plan["style"],
        "slides": len(rendered.slides), "diagram_slides": sum(page["type"] in {"source-figure", "architecture", "process", "comparison", "risk"} for page in plan["pages"]),
        "native_charts": 0, "editable_data_visuals": editable_visuals, "visual_asset_count": image_count,
        "layout_inventory": dict(inventory), "source_blocks": len(eligible), "source_blocks_mapped": len(eligible & mapped),
        "dominant_layout_ratio": round(max(inventory.values()) / len(rendered.slides), 3), **mapping,
        "source_mapping_scope": "selected_summary_blocks", "content_review": "not_run", "body_coverage": body_coverage,
        "prohibited_copy_hits": prohibited, "fact_boundary": "source-bound; no external facts or invented business metrics",
        "presentation_quality_reasons": reasons, "presentation_plan": plan,
        "presentation_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(), "program_checks": checks,
        "quality_gate": {"status": "pass" if passed else "fail", "reasons": [*reasons,
            *(["diagram_pending"] if pending else []), *(["source_quality_findings"] if any(item.get("quality_issue_count") for item in reports) else []),
            *(["layout_checks_failed"] if checks["status"] != "pass" else [])]}}
    if warning:
        quality["draft_quality"] = {"reports": reports, "quality_issue_count": sum(item.get("quality_issue_count", 0) for item in reports) + len(pending) + bool(reasons),
            "quality_issue_codes": sorted({code for item in reports for code in item.get("quality_issue_codes", [])} | ({"diagram_pending"} if pending else set()) | ({"presentation_quality_warning"} if reasons else set())),
            "presentation_quality_reasons": reasons, "human_review_required": True}
        source_figures = sum(item["type"] == "figure" for item in data["blocks"])
        quality["diagram_generation"] = {"status": "pending" if pending else "completed", "pending_count": len(pending), "pending_figures": pending,
            "source_image_count": image_count, "source_versions": data["sources"], "planned_count": source_figures + len(pending),
            "rendered": source_figures, "source_scope": "report_figures"}
    target.with_suffix(".manifest.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if not source_valid or checks["status"] != "pass" or (warning and data.get("draft_mode") is not True):
        raise ValueError("presentation quality gate failed")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--validate-source":
        load_source(Path(sys.argv[2]))
    else:
        main()
