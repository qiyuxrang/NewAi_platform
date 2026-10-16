"""Runtime diagram planning and DOCX structural acceptance for product reports."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile

from .product_content_quality import (
    _evidence, _pending, content_quality_policy_hash, inspect_content_quality, unsupported_numeric_claims,
)


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

DIAGRAM_PROMPT_VERSION = "report-evidence-mermaid-v3"
DIAGRAM_INSTRUCTION = "为本批每张图生成对应本项目正文的Mermaid代码、具体标题和图说明。仅据report_blocks中的节点与关系绘图；建议主题若与本章无关，改用本章已有设计、流程或实施示例，不得套用通用平台架构或补造设备、网络、参数、审批及收益。未确认的关系须明确标为待确认。标题、图说明及所有节点、连线、分组和时序文字须保留本图所引正文中的候选、条件和待确认限定；锚点组件名称不能证明已选型、已部署或已实现等既有状态。每图引用正文块evidence_block_ids，anchor_text取自所引正文的连续原文且必须出现在图中。不同图表达不同正文机制，禁止重复图。仅用flowchart或sequenceDiagram，建议每图3至8节点，代码约1000字符以内；禁止Markdown围栏、配置指令、注释、HTML、URL、click、style、classDef和linkStyle。所有可见文字黑色由渲染器控制。仅返回schema规定的JSON。"
MERMAID_SOURCE = re.compile(r"(?:flowchart\s+(?:TB|TD|BT|RL|LR)|graph\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|journey|pie\b|mindmap\b|timeline\b)", re.I)
DIAGRAM_LAYOUT_RESOURCE = Path(__file__).resolve().parent / "product_assets" / "diagram-layout-guidance.md"
DIAGRAM_INSTRUCTION += "\n" + DIAGRAM_LAYOUT_RESOURCE.read_text(encoding="utf-8").split("## 来源与使用边界", 1)[0]


def diagram_contract_hash() -> str:
    runtime = Path(__file__).resolve().parent / "product_assets" / "mermaid-runtime"
    return hashlib.sha256(DIAGRAM_PROMPT_VERSION.encode() + content_quality_policy_hash().encode()
                          + Path(__file__).read_bytes() + DIAGRAM_LAYOUT_RESOURCE.read_bytes() + (runtime / "render.mjs").read_bytes()
                          + (runtime / "dist" / "runtime-manifest.json").read_bytes()).hexdigest()


def minimum_diagrams(family: str) -> int:
    return 15 if family == "technical-solution" else 20


def heading_display_text(title: str) -> str:
    """Remove authored outline numbering where Word supplies automatic numbering."""
    ordinal = r"零〇一二两三四五六七八九十百千万"
    return re.sub(
        rf"^(?:第\s*[0-9{ordinal}]+\s*[章节篇]\s*[：:、.．]?\s*|"
        rf"[（(]\s*[0-9{ordinal}]+\s*[）)]\s*|[{ordinal}]+[、.．：:]\s*|"
        r"\d+(?:[.．]\d+)*(?:[.．、：:)）]\s*|\s+)(?![\d.．]))",
        "", title.strip(), count=1)


def add_structural_blocks(
    blocks: list[dict],
    family: str,
    sources: list[str],
    requirements: list[str],
    *,
    chapter_index: int = 0,
    chapter_count: int = 1,
    chapter_title: str = "",
    diagram_titles: list[str] | None = None,
) -> None:
    """Embed this chapter's mandatory diagrams without persisting Mermaid source.

    Diagram specifications are distributed round-robin across the report's real
    business chapters.  Consequently every figure remains below a business H1
    and the renderer never creates a detached, catch-all diagram chapter.
    """
    if chapter_count < 1 or not 0 <= chapter_index < chapter_count:
        raise ValueError("invalid diagram chapter allocation")
    offset = sum(block.get("type") == "figure" for block in blocks) if diagram_titles is not None else 0
    for index, title in enumerate(FAMILY_DIAGRAMS[family] if diagram_titles is None else diagram_titles, start=1):
        if diagram_titles is None and (index - 1) % chapter_count != chapter_index:
            continue
        index += offset
        prefix = f"DIAGRAM_{index:02d}"
        title = f"{chapter_title}：{title}" if chapter_title else title
        description = "依据本章正文及所列资料绘制，未确认的关系须保留待确认标识。"
        blocks.extend([
            {"id": prefix + "_HEADING", "type": "heading", "level": 2, "text": heading_display_text(title),
             "source_ids": sources, "requirement_ids": requirements},
            {"id": prefix + "_NOTE", "type": "paragraph", "text": description,
             "source_ids": sources, "requirement_ids": requirements},
            {"id": prefix + "_FIGURE", "type": "figure", "path": f"assets/diagram-{index:02d}.png",
             "caption": title, "width_mm": 145, "alt": description,
             "source_ids": sources, "requirement_ids": requirements},
        ])


def diagram_evidence_blocks(blocks):
    """Expose authored prose and native tables using their original block IDs."""
    result = []
    for block in blocks:
        if block.get("type") == "paragraph" and not block["id"].startswith("DIAGRAM_"):
            value = block["text"]
        elif block.get("type") == "table":
            value = "\n".join([block["caption"], " | ".join(block["columns"]),
                               *(" | ".join(row) for row in block["rows"])])
        else:
            continue
        result.append({"id": block["id"], "type": "paragraph", "text": value, "source_ids": block["source_ids"]})
    return result


def diagram_batches(document: dict):
    """Send complete authored chapter paragraphs, never unrelated runtime labels."""
    paragraphs, figures = [], []
    for block in document["blocks"]:
        if block.get("type") == "heading" and block.get("level") == 1:
            if figures:
                for start in range(0, len(figures), 4):
                    yield figures[start:start + 4], paragraphs
            paragraphs, figures = [], []
        elif block.get("type") in {"paragraph", "table"}:
            paragraphs.extend(diagram_evidence_blocks([block]))
        elif block.get("type") == "figure":
            figures.append(block)
    if figures:
        for start in range(0, len(figures), 4):
            yield figures[start:start + 4], paragraphs


def _diagram_visible_labels(source: str) -> list[str]:
    """Extract displayed Mermaid text, without treating graph IDs as prose.

    The renderer remains responsible for syntax. This extraction covers both
    permitted dialects and deliberately keeps labels separate: a pending label
    must not qualify an unrelated fixed value in another node or message.
    """
    labels = []
    if source.lstrip().startswith("sequenceDiagram"):
        for line in source.splitlines()[1:]:
            line = line.strip()
            participant = re.match(r"(?:participant|actor)\s+(\S+)(?:\s+as\s+(.+))?$", line)
            if participant:
                display = participant.group(2) or participant.group(1)
                if not re.fullmatch(r"[A-Za-z_]\w*", display):
                    labels.append(display)
            elif ":" in line:
                # Message/note labels occur after the first colon, never in
                # sender/receiver IDs or their activation markers.
                labels.append(line.split(":", 1)[1].strip())
            else:
                display = re.match(r"(?:loop|alt|else|opt|par|and|critical|option|break|box)\s+(.+)$", line)
                if display:
                    labels.append(display.group(1))
        return labels

    masked = list(source)
    pairs = {"[": "]", "(": ")", "{": "}"}
    position = 0
    while position < len(source):
        if source[position] not in pairs:
            position += 1
            continue
        start = position
        stack, quoted = [pairs[source[position]]], False
        position += 1
        while position < len(source) and stack:
            char = source[position]
            if char == '"':
                quoted = not quoted
            elif not quoted:
                if char in pairs:
                    stack.append(pairs[char])
                elif char == stack[-1]:
                    stack.pop()
            position += 1
        if stack:
            # An invalid/unclosed shape must not hide its text from the guard.
            labels.append(source[start + 1:])
            break
        label = source[start + 1:position - 1].strip(' [](){}"')
        if label:
            labels.append(label)
        masked[start:position] = " " * (position - start)
    remaining = "".join(masked)
    for pattern in (r"\|([^|\n]+)\|", r"(?:--|==|\-\.)(?!>)\s*(.+?)\s*(?:-->|==>|\.->)"):
        for match in re.finditer(pattern, remaining):
            labels.append(match.group(1).strip(' "'))
            masked[match.start():match.end()] = " " * (match.end() - match.start())
    for line in "".join(masked).splitlines()[1:]:
        subgraph = re.match(r"\s*subgraph\s+(.*)", line)
        if subgraph:
            display = subgraph.group(1).strip()
            display = re.sub(r"^[A-Za-z_]\w*\s+", "", display)
            if display and not re.fullmatch(r"[A-Za-z_]\w*", display):
                labels.append(display)
            continue
        # Bare Chinese node names are displayed; ASCII node IDs and numeric
        # suffixes on internal IDs are not project quantities.
        for token in re.split(r"\s+|[-=~.]+>|[;&|]", line):
            if re.search(r"[\u3400-\u9fff]", token):
                labels.append(token.strip(' "'))
    return labels


_DIAGRAM_STATE = re.compile(
    r"已(?:经)?(?:选型|部署|实现|满足|采用|选用|接入|上线|建成|配置|建立|具备|完成|启用|落实)|"
    r"(?:选型|部署|配置|建设|实施)(?:已)?(?:确定|确认|完成)|既定选型|最终选型|"
    r"(?:现有|既有)(?=.{0,20}(?:能力|组件|系统|平台|服务|机制|认证|审计))")
_DIAGRAM_UNCONFIRMED = re.compile(
    r"候选|可选|备选|拟(?:采用|部署|选用|建立|实施)|计划|建议|设计目标|建设目标|"
    r"(?:选型|部署|配置|建设|实施)(?:确定|确认|完成)(?:后|时)|"
    r"并非|并未|不是|不代表|不证明|不等于|无法确认|不能确认")


def _diagram_state_clauses(text: str) -> list[str]:
    # Keep qualifiers local to their own assertion, including a second status
    # assertion joined without punctuation. A pending node cannot qualify any
    # other displayed node, edge, caption or message.
    return [part.strip() for part in re.split(
        r"[。！？!?；;\n，,]|(?:但是|然而|同时|并且|以及|但|而|且|并|及)"
        r"(?=(?:本项目|该项目)?(?:已|既定|最终|现有|既有))",
        text) if part.strip()]


def _diagram_state_text(text: str) -> str:
    text = re.sub(r"\s+|[：:、()（）\"]", "", text).replace("已经", "已")
    # Caption framing is not part of a state assertion; retain the component,
    # action and scope instead of comparing only the anchored component name.
    text = re.sub(r"^(?:本项目图示|本项目|该项目|图示)", "", text)
    return re.sub(r"(?:示意图|流程图|架构图)$", "", text)


def _unsupported_diagram_state_claims(visible: list[str], texts: list[str]) -> list[dict]:
    """A cited candidate component is not evidence that it is already deployed.

    Literal confirmed assertions are deliberately required here. Entity/anchor
    overlap alone cannot establish selection, deployment or achieved capability.
    This guard only checks stated existing facts; imperative design steps such
    as implementing authentication or recording audits remain design steps.
    """
    confirmed = [_diagram_state_text(clause)
                 for text in texts for clause in _diagram_state_clauses(text)
                 if _DIAGRAM_STATE.search(clause) and not _pending(clause)
                 and not _DIAGRAM_UNCONFIRMED.search(clause)
                 and any(clause == accepted for accepted, _ in _evidence(clause))]
    issues = []
    for index, text in enumerate(visible):
        for clause in _diagram_state_clauses(text):
            if (not _DIAGRAM_STATE.search(clause) or _pending(clause)
                    or _DIAGRAM_UNCONFIRMED.search(clause)):
                continue
            assertion = _diagram_state_text(clause)
            if any(assertion in fact for fact in confirmed):
                continue
            issues.append({"code": "unsupported_diagram_state", "paragraph_index": index,
                "claim": clause,
                "correction": "该图可见的已选型、已部署或已实现等既有事实缺少本图引用正文中的已确认依据；"
                              "保留候选、拟采用、待确认或条件限定，不能仅凭锚点组件名称证明既有状态。"})
    return issues


def _validate_diagram_content(item: dict, evidence: dict) -> None:
    texts = [evidence[ref]["text"] for ref in item["evidence_block_ids"]]
    # Conditional/pending statements may be drawn as such, but their numbers
    # must not become a whitelist for an unqualified caption or node label.
    confirmed = [clause for clause, _ in _evidence("\n".join(texts))]
    visible = [item["title"], item["description"], item["anchor_text"],
               *_diagram_visible_labels(item["source"])]
    # Internal identifiers belong in metadata, never in rendered captions or labels.
    leaked = [{"code": "body_source_identifier", "paragraph_index": index,
               "claim": text, "correction": "删除可见文字中的内部图表标识，使用自然语言名称。"}
              for index, text in enumerate(visible)
              if re.search(r"DIAGRAM_\d+_(?:FIGURE|HEADING|NOTE)(?![A-Za-z0-9_])", text)]
    # Human figure/outline numbering is not a project parameter.
    visible = [re.sub(r"(?<=图)\d{1,3}(?=$|待(?:核对|确认)|[：:.\s])", "", text) for text in visible]
    visible[0] = re.sub(r"((?:分图|示意图|流程图|架构图|设计|流程|架构|图))\d{1,3}$", r"\1", visible[0])
    issues = leaked + inspect_content_quality(visible, project_facts=texts, source_context=texts)
    issues.extend(_unsupported_diagram_state_claims(visible, texts))
    issues.extend(unsupported_numeric_claims(visible, project_facts=confirmed, source_context=texts))
    # Short labels such as “数据孤岛” still make a project assertion even when
    # the subject is implicit. Preserve literal support from reviewed clauses.
    contextual = inspect_content_quality(["本项目图示：" + text for text in visible],
        project_facts=["本项目图示：" + text for text in confirmed])
    issues.extend(issue for issue in contextual
                  if issue["code"] in {"unsupported_project_status", "unsupported_capability_claim"})
    if issues:
        fields = ["title", "description", "anchor_text"]
        for issue in issues:
            index = issue["paragraph_index"]
            issue.update(figure_id=item["figure_id"], field=fields[index] if index < 3 else "source_label",
                         visible_text=visible[index])
        error = ValueError(f"diagram content quality: {issues[0]['code']}: {issues[0]['claim']}")
        error.quality_issues = issues
        raise error


def _diagram_structure_issues(item: dict) -> list[dict]:
    """Catch degenerate supported diagrams before rendering; Mermaid owns syntax.

    This intentionally inspects common node/edge notation rather than attempting
    another Mermaid parser. Unknown syntax is left to the controlled renderer.
    """
    source = item["source"]
    # ponytail: inspect common Mermaid notation; use its AST if more notation needs structural checks.
    if re.match(r"\s*flowchart TB\s+EXCERPT_[0-9a-f]{16}\[", source):
        return []  # The existing draft-only excerpt finding owns this fallback.
    problems, nodes, edges = [], {}, []
    if source.lstrip().startswith("sequenceDiagram"):
        for line in source.splitlines()[1:]:
            participant = re.match(r"\s*(?:participant|actor)\s+(\w+)(?:\s+as\s+(.+))?$", line)
            if participant:
                nodes[participant[1]] = participant[2] or participant[1]
            message = re.match(r"\s*(\w+)\s*(?:--?>>?|--?[)x])\s*[+-]?(\w+)\s*:\s*(\S.*)$", line)
            if message:
                edges.append((message[1], message[2], message[3]))
    else:
        masked = list(source)
        shapes = r'(?:\[(?:"[^"\n]*"|[^\]"\n])*\]|\((?:"[^"\n]*"|[^)"\n])*\)|\{(?:"[^"\n]*"|[^}"\n])*\})[\])}]*'
        decisions = set()
        for match in re.finditer(rf"(?P<id>[^\W\d]\w*)\s*(?P<shape>{shapes})", source):
            before = source[source.rfind("\n", 0, match.start()) + 1:match.start()]
            if re.match(r"\s*subgraph\s*$", before):
                continue
            shape = match["shape"]
            nodes[match["id"]] = shape.strip(' [](){}"')
            if shape.startswith("{") and not shape.startswith("{{"):
                decisions.add(match["id"])
            masked[match.start("shape"):match.end("shape")] = " " * len(shape)
        plain = "".join(masked)
        # Edge labels cannot masquerade as endpoints or arrow syntax.
        edge_labels = {}
        def hide_label(match):
            token = f"EDGE_LABEL_{len(edge_labels)}"
            edge_labels[token] = match[1]
            return " " + token + " "
        plain = re.sub(r"\|([^|\n]*)\|", hide_label, plain)
        plain = re.sub(r"(?:--|==|-\.)\s+([^\n]+?)\s+(?:-->|==>|\.->)",
                       lambda match: "-->" + hide_label(match), plain)
        for match in re.finditer(r"(?=\b([^\W\d]\w*)\s*(?:-->|---|==>|-\.->|--[ox]|~~~)\s*(EDGE_LABEL_\d+)?\s*([^\W\d]\w*))", plain):
            edges.append((match[1], match[3], edge_labels.get(match[2], "")))
        for node in decisions:
            if re.search(rf"\b{re.escape(node)}\s*&|\b{re.escape(node)}\s*(?:-->|==>|-\.->)[^\n]*&", plain):
                continue  # Compound Mermaid edges are checked by the renderer.
            outgoing = [edge for edge in edges if edge[0] == node]
            if len({edge[1] for edge in outgoing}) < 2 or any(not edge[2].strip() for edge in outgoing):
                problems.append("决策节点缺少两个有条件标签的去向")
    entities = set(nodes) | {endpoint for edge in edges for endpoint in edge[:2]}
    if len(entities) < 2 or not edges:
        problems.append("关系图至少需要两个实体和一条关系，单节点摘录或无关系节点不能作为完整图")
    if any(re.fullmatch(r"(?:节点|步骤|模块|组件|参与者|Node|Step|TBD|TODO)\s*[A-Z0-9一二三四五六七八九十]*", label, re.I)
           for label in nodes.values()):
        problems.append("图中存在没有业务含义的占位名称")
    # Only obvious generated IDs are rejected; real English business names and
    # implicit sequence participants remain valid.
    if any(re.fullmatch(r"[A-Z]\d*", nodes.get(node, node)) for node in entities):
        problems.append("实体显示为内部字母编号，须使用业务名称")
    return [{"code": "diagram_structure_quality", "figure_id": item["figure_id"], "field": "source",
             "paragraph_index": 0, "claim": problem,
             "correction": "依据所引正文修正实体、关系和分支条件；无法确认时保留待确认，不补造关系或以摘录卡充数。"}
            for problem in dict.fromkeys(problems)]


def excerpt_diagrams(figures: list[dict], paragraphs: list[dict]) -> list[dict]:
    snippets = [(paragraph, match.group()) for paragraph in paragraphs
                for match in re.finditer(r"[\u3400-\u9fff]{2,40}", paragraph["text"])]
    if not snippets:
        raise ValueError("diagram is missing its report evidence anchor")
    diagrams = []
    for index, figure in enumerate(figures):
        paragraph, excerpt = snippets[index % len(snippets)]
        identifier = hashlib.sha256(figure["id"].encode()).hexdigest()[:16]
        diagrams.append({"figure_id": figure["id"], "title": "草稿摘录图，详细关系待人工确认",
            "description": "仅呈现本章真实正文摘录，不表示完整关系设计；详细关系待人工确认。",
            "source": f'flowchart TB\nEXCERPT_{identifier}["{excerpt}"]',
            "evidence_block_ids": [paragraph["id"]], "anchor_text": excerpt})
    return validate_diagram_batch({"diagrams": diagrams}, figures, paragraphs, draft=True)


def _draft_diagram_source(source: str) -> str:
    source = re.sub(r"(?m)^([ \t]*)Direction([ \t]+(?:TB|TD|BT|RL|LR)[ \t]*)(?=\r?$)", r"\1direction\2", source)
    # These decorations cannot add nodes, relations or interactive behavior.
    css = (r"(?:(?:fill|stroke|color):\s*#[0-9a-fA-F]{3,8}|"
           r"stroke-dasharray:\s*\d+(?:\s+\d+)*|stroke-width:\s*\d+(?:\.\d+)?px)")
    kept, classes = [], set()
    for line in source.splitlines(keepends=True):
        decoration = re.fullmatch(
            rf"\s*(style|classDef)\s+([A-Za-z_]\w*)\s+{css}(?:\s*,\s*{css})*\s*;?\s*", line)
        if decoration:
            if decoration[1] == "classDef":
                classes.add(decoration[2])
        else:
            kept.append(line)
    source = "".join(kept)
    if classes:
        names = "|".join(re.escape(name) for name in sorted(classes))
        # Quoted visible text is never a class attachment.
        pieces = re.split(r'("(?:[^"\\]|\\.)*")', source)
        for index in range(0, len(pieces), 2):
            pieces[index] = re.sub(rf"(?<=[\]\)}}]):::(?:{names})(?!\w)", "", pieces[index])
        source = "".join(pieces)
    # Empty, attribute-free line breaks become plain text before the HTML guard.
    return re.sub(r"<br\s*/?>", " ", source, flags=re.I)


def validate_diagram_batch(payload: dict, figures: list[dict], paragraphs: list[dict], *, draft=False, quality_issues=None) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {"diagrams"} or not isinstance(payload["diagrams"], list):
        raise ValueError("invalid diagram model output")
    expected = {figure["id"] for figure in figures}
    evidence = {block["id"]: block for block in paragraphs}
    diagrams = [dict(item) if isinstance(item, dict) else item for item in payload["diagrams"]]
    seen, sources, findings = set(), set(), []
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
        if draft:
            source = _draft_diagram_source(source)
            item["source"] = source
        anchor = item["anchor_text"]
        supported_anchor = any(anchor in evidence[ref]["text"] for ref in refs)
        if len(anchor.strip()) < 2 or (not draft and not supported_anchor):
            raise ValueError("diagram is missing its report evidence anchor")
        if anchor not in source or not supported_anchor:
            # Repair only metadata using an existing complete visible label.
            # Drafts may also repair an inaccurate anchor, using the same literal evidence.
            labels = [label for label in _diagram_visible_labels(source)
                      if 2 <= len(label) <= 100 and label in source
                      and any(label in evidence[ref]["text"] for ref in refs)]
            if not labels:
                raise ValueError("diagram is missing its report evidence anchor")
            item["anchor_text"] = max(labels, key=len)
        if (not re.match(r"\s*(?:flowchart\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram)\b", source)
                or re.search(r"%%|https?://|javascript:|<|\b(?:click|style|classDef|linkStyle)\b", source, re.I)):
            raise ValueError("unsupported or unsafe Mermaid source")
        normalized = re.sub(r"\s+", "", source)
        if normalized in sources:
            raise ValueError("duplicate diagram source")
        if re.match(r"\s*flowchart TB\s+EXCERPT_[0-9a-f]{16}\[", source):
            if not draft:
                raise ValueError("diagram excerpt fallback requires draft review")
            findings.append({"code": "diagram_excerpt_fallback", "figure_id": identifier, "field": "source",
                "claim": "草稿摘录图，详细关系待人工确认",
                "correction": "按引用正文人工确认详细关系；摘录卡不代表完整关系图或人工批准。"})
        try:
            _validate_diagram_content(item, evidence)
        except ValueError as error:
            issues = getattr(error, "quality_issues", [])
            if not draft or not issues or any(issue["code"] == "body_source_identifier" for issue in issues):
                raise
            findings.extend(issues)
        structural_issues = _diagram_structure_issues(item)
        if structural_issues:
            if not draft:
                error = ValueError("diagram structure quality: " + structural_issues[0]["claim"])
                error.quality_issues = structural_issues
                raise error
            findings.extend(structural_issues)
        seen.add(identifier)
        sources.add(normalized)
    if seen != expected:
        raise ValueError("diagram model output is incomplete")
    if quality_issues is not None:
        quality_issues.extend(findings)
    return diagrams


def apply_diagram_descriptions(document: dict, diagrams: list[dict]) -> None:
    blocks = {block["id"]: block for block in document["blocks"]}
    for item in diagrams:
        figure = blocks[item["figure_id"]]
        prefix = item["figure_id"].removesuffix("_FIGURE")
        sources = list(dict.fromkeys(source for ref in item["evidence_block_ids"] for source in blocks[ref]["source_ids"]))
        figure.update(caption=item["title"], alt=item["description"], source_ids=sources)
        blocks[prefix + "_HEADING"].update(text=heading_display_text(item["title"]), source_ids=sources)
        blocks[prefix + "_NOTE"].update(text=item["description"], source_ids=sources)


def apply_diagram_layout(document: dict, evidence: dict, directory: Path) -> list[dict]:
    """Insert measured reading units only after validating every image binding.

    The caller verifies original figure/source identities first. This replaces
    layout, never authored chapter text or Mermaid semantics, and is idempotent
    when a recovered document already contains the reading units.
    """
    from .product_render_cache import confined, file_hash

    figures = {block["id"]: block for block in document["blocks"] if block.get("type") == "figure"}
    replacements, records = {}, []
    for item in evidence.get("figures", []):
        layout = item.get("layout")
        if layout is None:  # Older/synthetic renderer evidence has no layout contract.
            continue
        if not isinstance(layout, dict):
            raise ValueError("invalid diagram reading units")
        figure = figures.get(item["figure_id"])
        panels = layout.get("panels")
        if (figure is None or layout.get("version") not in ("word-readable-v1", "word-readable-v2", "word-readable-v3")
                or not isinstance(panels, list) or not panels
                or len(panels) > (100 if layout["version"] == "word-readable-v1" else 2)
                or any(not isinstance(panel, dict) for panel in panels)):
            raise ValueError("invalid diagram reading units")
        units = []
        for number, panel in enumerate(panels, 1):
            expected_path = (figure["path"] if number == 1 else
                             re.sub(r"\.png$", f"-unit-{number}.png", figure["path"], flags=re.I))
            width, font = panel.get("width_mm"), panel.get("min_font_pt")
            if (panel.get("index") != number or panel.get("total") != len(panels)
                    or panel.get("path") != expected_path
                    or type(width) not in (int, float) or not 10 <= width <= 145
                    or type(font) not in (int, float) or not 10.5 <= font <= 100
                    or not re.fullmatch(r"[0-9a-f]{64}", str(panel.get("imageSha256", "")))
                    or file_hash(confined(directory, expected_path)) != panel["imageSha256"]
                    or (number == 1 and panel["imageSha256"] != item["imageSha256"])):
                raise ValueError("unverified diagram reading unit")
            identifier = figure["id"] if number == 1 else f'{figure["id"]}_PANEL_{number:02d}'
            caption = re.sub(r"（阅读单元\d+/\d+）$", "", figure["caption"])
            alt = re.sub(r"；阅读单元\d+/\d+.*$", "", figure["alt"])
            if len(panels) > 1:
                caption += f"（阅读单元{number}/{len(panels)}）"
                alt += f"；阅读单元{number}/{len(panels)}，相邻单元保留重叠衔接。"
            units.append({**figure, "id": identifier, "path": expected_path, "caption": caption,
                          "alt": alt, "width_mm": width})
            records.append({"id": identifier, "image_sha256": panel["imageSha256"],
                            "width_mm": width, "min_font_pt": font,
                            "reading_unit": number, "reading_unit_count": len(panels)})
        replacements[figure["id"]] = units
    unit_ids = {unit["id"] for units in replacements.values() for unit in units[1:]}
    document["blocks"] = [unit for block in document["blocks"] if block["id"] not in unit_ids
                          for unit in replacements.get(block["id"], [block])]
    return records


def validate_document_requirements(document: dict, *, allow_pending=False) -> dict:
    family = document.get("family")
    if family not in FAMILY_DIAGRAMS:
        raise ValueError("unsupported report family")
    blocks = document.get("blocks", [])
    figures = [block for block in blocks if block.get("type") == "figure"]
    h1 = [block for block in blocks if block.get("type") == "heading" and block.get("level") == 1]
    h2 = [block for block in blocks if block.get("type") == "heading" and block.get("level") == 2]
    required = minimum_diagrams(family)
    pending = document.get("diagram_pending", []) if allow_pending else []
    plans = [item for item in document.get("requirements", []) if item.get("id") == "RGUIDEFIGURES"]
    if plans:
        from .product_feasibility import asset_hash
        if family != "feasibility" or len(plans) != 1:
            raise ValueError("invalid guide figure plan")
        plan = json.loads(plans[0]["text"])
        if (set(plan) != {"asset_sha256", "figure_ids"} or plan["asset_sha256"] != asset_hash()
                or not isinstance(plan["figure_ids"], list)
                or plan["figure_ids"] != [f"DIAGRAM_{index:02d}_FIGURE" for index in range(1, len(plan["figure_ids"]) + 1)]):
            raise ValueError("invalid guide figure plan")
        actual = {re.sub(r"_PANEL_\d+$", "", block["id"]) for block in figures}
        actual.update(item["figure_id"] for item in pending)
        if actual != set(plan["figure_ids"]):
            raise ValueError("guide figures differ from approved plan")
        required = len(plan["figure_ids"])
    if len(figures) + len(pending) < required:
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
