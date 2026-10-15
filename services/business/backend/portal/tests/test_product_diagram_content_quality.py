import copy
import unittest
from unittest.mock import patch

from portal.product_diagrams import diagram_contract_hash, validate_diagram_batch


class DiagramContentQualityTests(unittest.TestCase):
    def setUp(self):
        self.figures = [{"id": "DIAGRAM_01_FIGURE"}]
        self.paragraphs = [{"id": "P1", "text": "合成网关采集日志，备份周期待确认。",
                            "source_ids": ["S1"]}]
        self.item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "合成网关日志流向",
                     "description": "合成网关采集日志。", "anchor_text": "合成网关",
                     "source": 'flowchart LR\nN100["合成网关"] --> N200["日志复核"]',
                     "evidence_block_ids": ["P1"]}

    def validate(self, **changes):
        item = copy.deepcopy(self.item)
        item.update(changes)
        return validate_diagram_batch({"diagrams": [item]}, self.figures, self.paragraphs)

    def test_true_anchor_does_not_support_added_caption_description_or_label(self):
        for changes in (
            {"title": "投资预算10万元"},
            {"description": "每周固定备份。"},
            {"source": 'flowchart LR\nN100["合成网关"] --> N200["预算10万元"]'},
            {"source": 'flowchart LR\nN100["合成网关"] -->|每周固定备份| N200["日志"]'},
            {"source": 'flowchart LR\nN100["合成网关"] -- 预算10万元 --> N200["日志"]'},
            {"source": 'sequenceDiagram\nparticipant A100 as 合成网关\nparticipant B200 as 日志服务\nA100->>B200: 每周固定备份'},
            {"source": 'sequenceDiagram\nparticipant A100 as 合成网关\nloop 每周固定备份\nA100->>A100: 日志\nend'},
            {"source": 'flowchart LR\nsubgraph S100["预算10万元"]\nN100["合成网关"]\nend'},
            {"source": 'flowchart LR\nN100["合成网关"] --> 工资3000'},
            {"description": "指标80"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError) as failure:
                self.validate(**changes)
            self.assertTrue(failure.exception.quality_issues)
            self.assertEqual(failure.exception.quality_issues[0]["figure_id"], "DIAGRAM_01_FIGURE")

    def test_pending_label_does_not_qualify_another_fixed_label(self):
        with self.assertRaises(ValueError):
            self.validate(source='flowchart LR\nN100["合成网关：待确认"] --> N200["预算10万元"]')

    def test_confirmed_quantities_and_explicit_pending_labels_pass(self):
        self.validate(source='flowchart LR\nN100["合成网关"] --> N200["预算10万元待确认"]',
                      description="每周备份候选值待确认。")
        self.validate(source='flowchart LR\nN100["合成网关"]--预算10万元待确认-->N200["日志"]')
        self.paragraphs[0]["text"] += "项目投资预算10万元，备份每周固定执行。"
        self.validate(title="项目投资预算10万元", description="备份每周固定执行。",
                      source='flowchart LR\nN100["合成网关"] --> N200["项目投资预算10万元"]')

    def test_pending_and_conditional_evidence_cannot_be_promoted_to_fact(self):
        for text, changes in (
            ("合成网关预算10万元待确认。", {"title": "预算10万元"}),
            ("合成网关若实施每周备份则需验证。", {"description": "每周固定备份。"}),
            ("合成网关工资3000待确认。", {"description": "工资3000"}),
        ):
            self.paragraphs[0]["text"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.validate(**changes)

    def test_other_graph_or_unreferenced_paragraph_cannot_supply_evidence(self):
        self.paragraphs.append({"id": "P2", "text": "项目投资预算10万元。", "source_ids": ["S2"]})
        with self.assertRaises(ValueError):
            self.validate(title="项目投资预算10万元")
        self.validate(title="项目投资预算10万元", evidence_block_ids=["P1", "P2"])

    def test_ids_and_title_outline_numbers_are_not_project_parameters(self):
        self.validate(title="合成网关设计1", source='flowchart LR\nA10000["合成网关"] --> loop3000["日志复核"]')
        self.validate(source='sequenceDiagram\nparticipant A100 as 日志源\nparticipant B200 as 合成网关\nA100->>B200: 日志复核')

    def test_cache_contract_binds_content_quality_policy(self):
        original = diagram_contract_hash()
        with patch("portal.product_diagrams.content_quality_policy_hash", return_value="changed-policy"):
            self.assertNotEqual(original, diagram_contract_hash())

    def test_visible_internal_figure_ids_are_rejected(self):
        for changes in ({"title": "图DIAGRAM_01_FIGURE"},
                        {"source": 'flowchart LR\nA["合成网关"] --> B["DIAGRAM_01_FIGURE"]'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError) as failure:
                self.validate(**changes)
            self.assertTrue(any(issue["code"] == "body_source_identifier"
                                for issue in failure.exception.quality_issues))
        self.validate(source='flowchart LR\nDIAGRAM_01_FIGURE["合成网关"] --> B["日志复核"]')

    def test_public_version_only_supported_by_this_graph_references(self):
        self.paragraphs[0]["text"] += "参考PostgreSQL官方文档15。"
        self.validate(description="参考PostgreSQL官方文档15。")
        with self.assertRaises(ValueError):
            self.validate(description="端口15")

    def test_project_status_and_capability_assertions_in_short_labels(self):
        for label in ("数据孤岛", "已保证高可用"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.validate(source=f'flowchart LR\nA["合成网关"] --> B["{label}"]')
            self.validate(source=f'flowchart LR\nA["合成网关"] --> B["{label}待确认"]')
        self.paragraphs[0]["text"] += "当前存在数据孤岛。"
        self.validate(source='flowchart LR\nA["合成网关"] --> B["当前存在数据孤岛"]')

    def candidate_component(self):
        self.paragraphs[0]["text"] = "Kafka Connect作为候选组件待确认。"
        self.item.update(title="Kafka Connect候选采集方案", description="拟采用Kafka Connect，选型待确认。",
                         anchor_text="Kafka Connect",
                         source='flowchart LR\nA["Kafka Connect"] --> B["采集方案待确认"]')

    def test_candidate_anchor_cannot_establish_existing_state_anywhere_visible(self):
        self.candidate_component()
        for changes, field in (
            ({"title": "已部署Kafka Connect"}, "title"),
            ({"description": "本项目已部署Kafka Connect进行数据采集。"}, "description"),
            ({"source": 'flowchart LR\nA["Kafka Connect"] --> B["已部署采集组件"]'}, "source_label"),
            ({"source": 'flowchart LR\nA["Kafka Connect"] -->|已选型Kafka Connect| B["采集"]'}, "source_label"),
            ({"source": 'flowchart LR\nA["Kafka Connect"] -- 已实现身份认证 --> B["采集"]'}, "source_label"),
            ({"source": 'flowchart LR\nsubgraph S["已部署Kafka Connect"]\nA["Kafka Connect"]\nend'}, "source_label"),
            ({"source": 'sequenceDiagram\nparticipant A as Kafka Connect\nparticipant B as 已部署采集组件\nA->>B: 采集'}, "source_label"),
            ({"source": 'sequenceDiagram\nparticipant A as Kafka Connect\nA->>A: 已实现日志审计'}, "source_label"),
            ({"source": 'sequenceDiagram\nparticipant A as Kafka Connect\nloop 已满足容量要求\nA->>A: 采集\nend'}, "source_label"),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError) as failure:
                self.validate(**changes)
            issues = [issue for issue in failure.exception.quality_issues
                      if issue["code"] == "unsupported_diagram_state"]
            self.assertTrue(issues)
            self.assertEqual(issues[0]["field"], field)
            self.assertEqual(issues[0]["figure_id"], "DIAGRAM_01_FIGURE")
            self.assertTrue(issues[0]["visible_text"])

    def test_state_anchor_requires_confirmed_assertion_not_candidate_occurrence(self):
        self.candidate_component()
        self.paragraphs[0]["text"] = "是否已部署Kafka Connect待确认。"
        with self.assertRaises(ValueError) as failure:
            self.validate(anchor_text="已部署Kafka Connect",
                          source='flowchart LR\nA["已部署Kafka Connect"] --> B["采集方案待确认"]')
        self.assertTrue(any(issue["field"] == "anchor_text"
                            and issue["code"] == "unsupported_diagram_state"
                            for issue in failure.exception.quality_issues))

    def test_unconfirmed_or_conditional_capacity_does_not_establish_satisfied_state(self):
        self.candidate_component()
        for fact in ("Kafka Connect容量要求待确认。", "Kafka Connect作为容量候选组件。",
                     "若Kafka Connect已满足容量要求则实施采集。"):
            self.paragraphs[0]["text"] = fact
            with self.subTest(fact=fact), self.assertRaises(ValueError):
                self.validate(description="Kafka Connect已满足容量要求。")

    def test_confirmed_state_and_qualified_design_steps_pass(self):
        self.candidate_component()
        self.validate()
        self.validate(description="实施身份认证并记录审计。",
                      source='flowchart LR\nA["Kafka Connect"] --> B["实施身份认证"] --> C["记录审计"]')
        for label in ("拟采用Kafka Connect", "已部署Kafka Connect待确认",
                      "若Kafka Connect已满足容量要求则实施采集",
                      "Kafka Connect部署完成后实施采集", "不能确认已部署Kafka Connect"):
            with self.subTest(label=label):
                self.validate(source=f'flowchart LR\nA["Kafka Connect"] --> B["{label}"]')
        self.paragraphs[0]["text"] = "本项目已部署Kafka Connect进行数据采集。Kafka Connect已满足容量要求。"
        self.validate(title="已部署Kafka Connect", description="本项目已部署Kafka Connect进行数据采集。",
                      anchor_text="已部署Kafka Connect",
                      source='flowchart LR\nA["已部署Kafka Connect"] --> B["Kafka Connect已满足容量要求"]')

    def test_unrelated_reference_and_other_diagram_cannot_confirm_state(self):
        self.candidate_component()
        self.paragraphs.append({"id": "P2", "text": "本项目已部署Kafka Connect进行数据采集。",
                                "source_ids": ["S2"]})
        confirmed_item = {**self.item, "figure_id": "DIAGRAM_02_FIGURE",
                          "evidence_block_ids": ["P2"], "title": "已部署Kafka Connect",
                          "description": "本项目已部署Kafka Connect进行数据采集。",
                          "source": 'flowchart LR\nC["Kafka Connect"] --> D["数据采集"]'}
        promoted_item = {**self.item, "title": "已部署Kafka Connect"}
        figures = self.figures + [{"id": "DIAGRAM_02_FIGURE"}]
        with self.assertRaises(ValueError) as failure:
            validate_diagram_batch({"diagrams": [confirmed_item, promoted_item]}, figures, self.paragraphs)
        self.assertEqual(failure.exception.quality_issues[0]["figure_id"], "DIAGRAM_01_FIGURE")
        self.validate(title="已部署Kafka Connect", evidence_block_ids=["P1", "P2"])

    def test_local_pending_label_does_not_qualify_separate_status_assertion(self):
        self.candidate_component()
        for label in ("Kafka Connect待确认，已实现审计", "Kafka Connect待确认且已实现审计"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.validate(source=f'flowchart LR\nA["Kafka Connect"] --> B["{label}"]')

    def test_status_after_contrast_or_simultaneous_join_keeps_own_evidence_scope(self):
        self.candidate_component()
        for join in ("但", "而", "同时", "但是", "然而"):
            text = f"Kafka Connect作为候选待确认{join}本项目已部署Kafka Connect"
            for changes, field in (({"description": text}, "description"),
                                   ({"source": f'flowchart LR\nA["Kafka Connect"] --> B["{text}"]'}, "source_label")):
                with self.subTest(join=join, field=field), self.assertRaises(ValueError) as failure:
                    self.validate(**changes)
                self.assertTrue(any(issue["code"] == "unsupported_diagram_state"
                                    and issue["field"] == field
                                    and issue["claim"] == "本项目已部署Kafka Connect"
                                    for issue in failure.exception.quality_issues))
            # The same join must not convert an explicitly uncertain status or
            # a future deployment step into an assertion of existing capability.
            self.validate(description=f"Kafka Connect作为候选待确认{join}不能确认已部署Kafka Connect")
            self.validate(description=f"Kafka Connect作为候选待确认{join}部署完成后实施采集")
        self.paragraphs[0]["text"] += "本项目已部署Kafka Connect。"
        self.validate(description="Kafka Connect作为候选待确认但本项目已部署Kafka Connect")

    def test_state_issue_retains_bounded_diagram_api_diagnostics(self):
        from portal.product_worker import _bounded_quality_issues
        self.candidate_component()
        with self.assertRaises(ValueError) as failure:
            self.validate(title="已部署Kafka Connect")
        issues = _bounded_quality_issues(failure.exception.quality_issues)
        self.assertEqual(issues[0]["code"], "unsupported_diagram_state")
        self.assertEqual(issues[0]["field"], "title")
        self.assertEqual(issues[0]["figure_id"], "DIAGRAM_01_FIGURE")


if __name__ == "__main__":
    unittest.main()
