"""Runtime diagram planning and DOCX structural acceptance for product reports."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile


TECHNICAL_DIAGRAM_TOPICS = [
    "业务闭环流程", "总体架构", "应用架构", "技术架构", "部署架构", "网络拓扑", "数据流转", "集成架构",
    "安全架构", "身份与权限", "日志审计", "高可用架构", "备份与恢复", "监控告警", "发布与变更",
]
# Topics guide layout only; the model must replace irrelevant topics with authored project designs.
FAMILY_DIAGRAMS = {
    "technical-solution": TECHNICAL_DIAGRAM_TOPICS,
    "feasibility": [*TECHNICAL_DIAGRAM_TOPICS, "可行性评价框架", "建设范围边界", "干系人协同", "决策门禁", "效益实现路径"],
}

SUBSECTION_TITLES = {
    "technical-solution": ("设计目标与约束", "方案组成与关键机制", "实施方法与控制要求", "运行保障与验收要点"),
    "feasibility": ("评价目标与分析边界", "现状依据与关键假设", "可行性论证与风险控制", "实施条件与决策建议"),
}

DIAGRAM_PROMPT_VERSION = "report-evidence-mermaid-v1"
DIAGRAM_INSTRUCTION = "为本批每张图生成对应本项目正文的Mermaid代码、具体标题和图说明。仅据report_blocks中的节点与关系绘图；建议主题若与本章无关，改用本章已有设计、流程或实施示例，不得套用通用平台架构或补造设备、网络、参数、审批及收益。未确认的关系须明确标为待确认。每图引用正文块evidence_block_ids，anchor_text取自所引正文的连续原文且必须出现在图中。不同图表达不同正文机制，禁止重复图。仅用flowchart或sequenceDiagram，建议每图3至8节点，代码约1000字符以内；禁止Markdown围栏、配置指令、注释、HTML、URL、click、style、classDef和linkStyle。所有可见文字黑色由渲染器控制。仅返回schema规定的JSON。"
MERMAID_SOURCE = re.compile(r"(?:flowchart\s+(?:TB|TD|BT|RL|LR)|graph\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|journey|pie\b|mindmap\b|timeline\b)", re.I)


def diagram_contract_hash() -> str:
    runtime = Path(__file__).resolve().parent / "product_assets" / "mermaid-runtime"
    return hashlib.sha256(DIAGRAM_PROMPT_VERSION.encode() + Path(__file__).read_bytes() + (runtime / "render.mjs").read_bytes()
                          + (runtime / "dist" / "runtime-manifest.json").read_bytes()).hexdigest()


def minimum_diagrams(family: str) -> int:
    return 15 if family == "technical-solution" else 20


def add_structural_blocks(
    blocks: list[dict],
    family: str,
    sources: list[str],
    requirements: list[str],
    *,
    chapter_index: int = 0,
    chapter_count: int = 1,
    chapter_title: str = "",
) -> None:
    """Embed this chapter's mandatory diagrams without persisting Mermaid source.

    Diagram specifications are distributed round-robin across the report's real
    business chapters.  Consequently every figure remains below a business H1
    and the renderer never creates a detached, catch-all diagram chapter.
    """
    if chapter_count < 1 or not 0 <= chapter_index < chapter_count:
        raise ValueError("invalid diagram chapter allocation")
    for index, title in enumerate(FAMILY_DIAGRAMS[family], start=1):
        if (index - 1) % chapter_count != chapter_index:
            continue
        prefix = f"DIAGRAM_{index:02d}"
        title = f"{chapter_title}：{title}" if chapter_title else title
        description = "依据本章正文及所列资料绘制，未确认的关系须保留待确认标识。"
        blocks.extend([
            {"id": prefix + "_HEADING", "type": "heading", "level": 2, "text": title,
             "source_ids": sources, "requirement_ids": requirements},
            {"id": prefix + "_FIGURE", "type": "figure", "path": f"assets/diagram-{index:02d}.png",
             "caption": title, "width_mm": 145, "alt": description,
             "source_ids": sources, "requirement_ids": requirements},
            {"id": prefix + "_NOTE", "type": "paragraph", "text": description,
             "source_ids": sources, "requirement_ids": requirements},
        ])


def diagram_batches(document: dict):
    """Send complete authored chapter paragraphs, never unrelated runtime labels."""
    paragraphs, figures = [], []
    for block in document["blocks"]:
        if block.get("type") == "heading" and block.get("level") == 1:
            if figures:
                for start in range(0, len(figures), 4):
                    yield figures[start:start + 4], paragraphs
            paragraphs, figures = [], []
        elif block.get("type") == "paragraph" and not block["id"].startswith("DIAGRAM_"):
            paragraphs.append({"id": block["id"], "text": block["text"], "source_ids": block["source_ids"]})
        elif block.get("type") == "figure":
            figures.append(block)
    if figures:
        for start in range(0, len(figures), 4):
            yield figures[start:start + 4], paragraphs


def validate_diagram_batch(payload: dict, figures: list[dict], paragraphs: list[dict]) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {"diagrams"} or not isinstance(payload["diagrams"], list):
        raise ValueError("invalid diagram model output")
    expected = {figure["id"] for figure in figures}
    evidence = {block["id"]: block for block in paragraphs}
    diagrams = payload["diagrams"]
    seen, sources = set(), set()
    for item in diagrams:
        if not isinstance(item, dict) or set(item) != {"figure_id", "title", "description", "source", "evidence_block_ids", "anchor_text"}:
            raise ValueError("invalid diagram schema")
        identifier, source, refs = item["figure_id"], item["source"], item["evidence_block_ids"]
        if not isinstance(identifier, str) or identifier not in expected or identifier in seen:
            raise ValueError("diagram identifiers differ from planned figures")
        for field, limit in (("title", 120), ("description", 400), ("anchor_text", 100), ("source", 6000)):
            value = item[field]
            if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
                raise ValueError("invalid diagram text")
        if (not isinstance(refs, list) or not refs or len(refs) > 30
                or any(not isinstance(ref, str) or ref not in evidence for ref in refs)):
            raise ValueError("diagram evidence outside authored chapter")
        anchor = item["anchor_text"]
        if len(anchor.strip()) < 2 or anchor not in source or not any(anchor in evidence[ref]["text"] for ref in refs):
            raise ValueError("diagram is missing its report evidence anchor")
        if (not re.match(r"\s*(?:flowchart\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram)\b", source)
                or re.search(r"%%|https?://|javascript:|<|\b(?:click|style|classDef|linkStyle)\b", source, re.I)):
            raise ValueError("unsupported or unsafe Mermaid source")
        normalized = re.sub(r"\s+", "", source)
        if normalized in sources:
            raise ValueError("duplicate diagram source")
        seen.add(identifier)
        sources.add(normalized)
    if seen != expected:
        raise ValueError("diagram model output is incomplete")
    return diagrams


def apply_diagram_descriptions(document: dict, diagrams: list[dict]) -> None:
    blocks = {block["id"]: block for block in document["blocks"]}
    for item in diagrams:
        figure = blocks[item["figure_id"]]
        prefix = item["figure_id"].removesuffix("_FIGURE")
        sources = list(dict.fromkeys(source for ref in item["evidence_block_ids"] for source in blocks[ref]["source_ids"]))
        figure.update(caption=item["title"], alt=item["description"], source_ids=sources)
        blocks[prefix + "_HEADING"].update(text=item["title"], source_ids=sources)
        blocks[prefix + "_NOTE"].update(text=item["description"], source_ids=sources)


def validate_document_requirements(document: dict) -> dict:
    family = document.get("family")
    if family not in FAMILY_DIAGRAMS:
        raise ValueError("unsupported report family")
    blocks = document.get("blocks", [])
    figures = [block for block in blocks if block.get("type") == "figure"]
    h1 = [block for block in blocks if block.get("type") == "heading" and block.get("level") == 1]
    h2 = [block for block in blocks if block.get("type") == "heading" and block.get("level") == 2]
    required = minimum_diagrams(family)
    if len(figures) < required:
        raise ValueError(f"diagram count below requirement: {len(figures)} < {required}")
    if not h1 or not h2:
        raise ValueError("reports require both level-one and level-two headings")
    if max((block.get("level", 0) for block in blocks if block.get("type") == "heading"), default=0) < 2:
        raise ValueError("table of contents must include level-two headings")
    paths = [block["path"] for block in figures]
    if len(paths) != len(set(paths)):
        raise ValueError("diagram paths must be unique")
    serialized = json.dumps(document, ensure_ascii=False)
    if MERMAID_SOURCE.search(serialized.replace("\\n", "\n")):
        raise ValueError("Mermaid source must not be persisted in report content")
    return {"figure_count": len(figures), "heading1_count": len(h1), "heading2_count": len(h2), "toc_depth": 2}


def inspect_docx_requirements(path: Path, expected: dict) -> dict:
    with ZipFile(path) as archive:
        names = archive.namelist()
        xml = b"".join(archive.read(name) for name in names if name.endswith(".xml"))
        media = [name for name in names if name.startswith("word/media/") and name.lower().endswith((".png", ".jpg", ".jpeg"))]
    # The company logo is also media, so the number must be at least the planned figure count.
    if len(media) < expected["figure_count"]:
        raise ValueError("rendered DOCX is missing diagram images")
    if MERMAID_SOURCE.search(xml.decode("utf-8", errors="ignore")):
        raise ValueError("rendered DOCX contains Mermaid source")
    return {**expected, "embedded_raster_count": len(media), "mermaid_source_embedded": False}
