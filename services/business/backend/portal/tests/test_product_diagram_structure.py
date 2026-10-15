import copy
import unittest
from unittest.mock import patch

from portal.product_diagrams import (
    DIAGRAM_INSTRUCTION, _diagram_structure_issues, add_structural_blocks,
    apply_diagram_descriptions, diagram_contract_hash, heading_display_text,
    excerpt_diagrams, validate_diagram_batch,
    diagram_batches,
)


class DiagramStructureTests(unittest.TestCase):
    def test_native_tables_keep_original_evidence_ids_in_diagram_requests(self):
        table = {'id': 'T1', 'type': 'table', 'caption': '表1-1 资料交付关系待确认',
                 'columns': ['来源', '目标'], 'rows': [['资料接收', '资料复核']], 'source_ids': ['S1']}
        document = {'blocks': [{'type': 'heading', 'level': 1}, table,
                              {'type': 'figure', 'id': 'DIAGRAM_01_FIGURE'}]}
        figures, evidence = next(diagram_batches(document))
        self.assertEqual(evidence[0]['id'], 'T1')
        self.assertIn('资料接收 | 资料复核', evidence[0]['text'])
        item = {**self.item, 'evidence_block_ids': ['T1']}
        self.assertEqual(validate_diagram_batch({'diagrams': [item]}, figures, evidence), [item])

    def setUp(self):
        self.figures = [{"id": "DIAGRAM_01_FIGURE"}]
        self.paragraphs = [{"id": "P1", "text": "资料接收后进行资料复核，条件和交付结果待确认。", "source_ids": ["S1"]}]
        self.item = {"figure_id": self.figures[0]["id"], "title": "资料交付关系待确认",
                     "description": "资料接收与复核关系，条件待确认。", "anchor_text": "资料接收",
                     "source": 'flowchart TB\nA["资料接收"] --> B["资料复核"]', "evidence_block_ids": ["P1"]}

    def test_degenerate_diagrams_fail_with_locatable_findings_and_drafts_keep_warning(self):
        for source in ('flowchart TB\nA["资料接收"]',
                       'flowchart TB\nA["资料接收"]\nB["资料复核"]',
                       'flowchart TB\nA["资料接收"] --> B["节点二"]',
                       'flowchart TB\nA["资料接收"] --> B',
                       'flowchart TB\nA["资料接收"] --> D{"条件待确认"}',
                       'flowchart TB\nA["资料接收"] --> D{"条件待确认"}\nD --> B["资料复核"]'):
            payload = {"diagrams": [{**self.item, "source": source}]}
            before = copy.deepcopy(payload)
            with self.subTest(source=source), self.assertRaises(ValueError) as failed:
                validate_diagram_batch(payload, self.figures, self.paragraphs)
            issue = failed.exception.quality_issues[0]
            self.assertEqual(issue["code"], "diagram_structure_quality")
            self.assertEqual((issue["figure_id"], issue["field"]), (self.item["figure_id"], "source"))
            warnings = []
            accepted = validate_diagram_batch(payload, self.figures, self.paragraphs, draft=True, quality_issues=warnings)
            self.assertEqual(accepted, payload["diagrams"])
            self.assertTrue(warnings)
            self.assertEqual(payload, before)

    def test_branches_chains_subgraphs_and_sequence_conditions_are_not_flattened(self):
        sources = [self.item["source"],
            'flowchart TB\nA["资料接收"] --> D{"条件待确认"}\nD -->|条件成立| B["资料复核"]\nD -->|条件未成立| C["补齐资料"]\nC --> A',
            'flowchart TB\nA["资料接收"] --> D{"条件待确认"}\nD -. 条件成立 .-> B["资料复核"]\nD == 条件未成立 ==> C["补齐资料"]',
            'flowchart TB\nA["资料接收"]-->B["资料复核"]-->C["结果待确认"]',
            'flowchart TB\nA(("资料接收")) --> D{{"资料复核"}} --> E[("结果待确认")]',
            'flowchart TB\nsubgraph S["接收层"]\nA["资料接收"]\nend\nsubgraph T["处理层"]\nB["资料复核"]\nend\nA --> B',
            'flowchart TB\nA["资料接收"] --> D{"条件待确认"}\nD -->|条件成立| B["资料复核"] & C["结果待确认"]\nD -->|条件未成立| E["补齐资料"]',
            'sequenceDiagram\nparticipant A as 接收端\nparticipant B as 复核端\nA->>+B:资料接收\nalt 条件待确认\nB-->>-A:复核结果\nelse 资料不完整\nB-->>A:补齐资料\nend']
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(_diagram_structure_issues({**self.item, "source": source}), [])

    def test_excerpt_remains_draft_only_and_semantic_guidance_is_hash_bound(self):
        excerpts = excerpt_diagrams(self.figures, self.paragraphs)
        warnings = []
        validate_diagram_batch({"diagrams": excerpts}, self.figures, self.paragraphs, draft=True, quality_issues=warnings)
        self.assertEqual([issue["code"] for issue in warnings], ["diagram_excerpt_fallback"])
        with self.assertRaises(ValueError):
            validate_diagram_batch({"diagrams": excerpts}, self.figures, self.paragraphs)
        self.assertIn("先按正文关系选择表达方式", DIAGRAM_INSTRUCTION)
        original = diagram_contract_hash()
        from pathlib import Path
        read_bytes = Path.read_bytes
        with patch.object(Path, "read_bytes", lambda path: b"changed layout rules" if path.name == "diagram-layout-guidance.md" else read_bytes(path)):
            self.assertNotEqual(diagram_contract_hash(), original)

    def test_heading_numbering_is_removed_at_both_diagram_heading_entries_only(self):
        titles = {
            "第四章建设条件与环境影响：高可用架构待确认边界": "建设条件与环境影响：高可用架构待确认边界",
            "第五章投资估算中跨行规格解析与费用归集流程": "投资估算中跨行规格解析与费用归集流程",
            "第八章结论与建议：可行性评价框架": "结论与建议：可行性评价框架",
            "第 12 章： 部署条件": "部署条件", "第十二节 安全边界": "安全边界",
            "12. 部署条件": "部署条件", "12、部署条件": "部署条件",
            "1.2.3 部署条件": "部署条件", "1.2.3.4. 部署条件": "部署条件",
            "（三）部署条件": "部署条件", "三、部署条件": "部署条件",
            "10kV供配电设计": "10kV供配电设计", "2026年建设计划": "2026年建设计划",
            "1.2万元费用依据待确认": "1.2万元费用依据待确认",
        }
        for title, expected in titles.items():
            with self.subTest(title=title):
                self.assertEqual(heading_display_text(title), expected)
        for title in list(titles)[:3]:
            blocks = [{"id": "P1", "type": "paragraph", "text": "正文依据原文", "source_ids": ["S1"]}]
            add_structural_blocks(blocks, "feasibility", ["S1"], [], chapter_title=title)
            headings = [block for block in blocks if block["type"] == "heading"]
            self.assertTrue(all(block["text"].startswith(titles[title]) for block in headings))
            item = {"figure_id": "DIAGRAM_01_FIGURE", "title": title, "description": "正文限定原文待确认",
                    "evidence_block_ids": ["P1"], "anchor_text": "正文依据原文"}
            apply_diagram_descriptions({"blocks": blocks}, [item])
            by_id = {block["id"]: block for block in blocks}
            self.assertEqual(by_id["DIAGRAM_01_HEADING"]["text"], titles[title])
            self.assertEqual(by_id["DIAGRAM_01_FIGURE"]["caption"], title)
            self.assertEqual(by_id["DIAGRAM_01_NOTE"]["text"], item["description"])
            self.assertEqual(blocks[0]["text"], "正文依据原文")
            self.assertEqual(item["title"], title)
