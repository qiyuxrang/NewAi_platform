from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from portal.product_chapter_materials import chapter_material
from portal.product_worker import _project_facts, model_input


def material_text():
    blocks = [
        ("段落 1", "合成项目资料"),
        ("段落 2", "1 数据备份"),
        ("段落 3", "数据备份保留30天，暂未实测。"),
        ("段落 4", "仅在独立网络中执行。"),
        ("第 1 行 · 表格 1", "设备名称 | 数量 | 单位"),
        ("第 2 行 · 表格 1", "数据备份设备 | 2 | 台"),
        ("第 3 行 · 表格 1", "配套交换设备 | 1 | 台"),
        ("段落 8", "备注：以上数量为规划值，不是实测结果。"),
        ("段落 9", "2 展示设计"),
        ("段落 10", "展板沿墙布置。" * 80),
        ("段落 11", "展示屏以中性色呈现内容。" * 80),
    ]
    return "\n\n".join(f"[{label} · b{index}]\n{text}" for index, (label, text) in enumerate(blocks, 1))


class ProductChapterMaterialsTests(SimpleTestCase):
    chapter = {"id": "backup", "title": "数据备份", "scope": "保留规划值和验证条件", "source_ids": ["approved"]}

    def test_complete_section_table_qualifiers_and_exact_omission_ranges(self):
        text = material_text()
        excerpt, selection = chapter_material(text, self.chapter)
        self.assertLess(len(excerpt), len(text))
        for retained in ("[段落 3 · b3]", "暂未实测", "仅在独立网络中执行", "设备名称 | 数量 | 单位",
                         "配套交换设备 | 1 | 台", "不是实测结果"):
            self.assertIn(retained, excerpt)
        self.assertNotIn("展板沿墙布置", excerpt)
        self.assertEqual(selection["mode"], "excerpt")
        spans = sorted([*selection["included_ranges"], *selection["omitted_ranges"]])
        self.assertEqual("".join(text[start:end] for start, end in spans), text)
        self.assertEqual("".join(text[start:end] for start, end in selection["included_ranges"]), excerpt)

    def test_unstructured_paragraphs_are_not_cut_and_adjacent_denials_survive(self):
        paragraphs = ["合成资料", "大厅显示布局。", "家具采用木材。",
                      "数据备份容量30TB；该容量为规划值，整句必须保留。",
                      "前提是机房条件通过核对。", "不得把规划容量视为实测结果。",
                      "展示屏为灰色。", "展板为白色。" * 60]
        text = "\n\n".join(paragraphs)
        excerpt, selection = chapter_material(text, self.chapter)
        self.assertEqual(selection["mode"], "excerpt")
        self.assertIn(paragraphs[3], excerpt)
        self.assertIn(paragraphs[4], excerpt)
        self.assertIn(paragraphs[5], excerpt)
        self.assertNotIn(paragraphs[7], excerpt)

    def test_no_complete_phrase_match_falls_back_to_full_authorized_material(self):
        text = "原文介绍备份。\n\n另段介绍恢复。\n\n保留所有数据和限定条件。"
        excerpt, selection = chapter_material(text, {"title": "数据备份与恢复", "scope": "核对建设依据"})
        self.assertEqual(excerpt, text)
        self.assertEqual(selection["reason"], "no_reliable_match")
        self.assertEqual(selection["omitted_ranges"], [])
        ascii_text = "planet description\n\nother details"
        self.assertEqual(chapter_material(ascii_text, {"title": "plan"})[0], ascii_text)

    def test_neighbor_expansion_never_cuts_an_adjacent_table_or_english_qualifier(self):
        blocks = [("段落 1", "Original source"), ("段落 2", "Other details"),
                  ("第 1 行 · 表格 1", "first table header"), ("第 2 行 · 表格 1", "first table last row"),
                  ("第 1 行 · 表格 2", "second table header"), ("第 2 行 · 表格 2", "Backup policy row"),
                  ("段落 7", "Only a planned value; not a measured result."),
                  ("段落 8", "Other details"), ("段落 9", "Unrelated description" * 100)]
        text = "\n\n".join(f"[{label} · b{index}]\n{body}" for index, (label, body) in enumerate(blocks, 1))
        excerpt, selection = chapter_material(text, {"title": "Backup policy"})
        for body in (blocks[2][1], blocks[3][1], blocks[4][1], blocks[5][1], blocks[6][1]):
            self.assertIn(body, excerpt)
        self.assertEqual(selection["mode"], "excerpt")

    def input_fixture(self, *, sources_exist=True):
        text = material_text()
        payload = {"project": "合成项目", "requirements": "按资料编写", "conditions": ["不得新增设备"],
                   "background": text, "items": [{"name": "备份设备", "source_id": "approved", "row_id": "1"},
                                                    {"name": "越权设备", "source_id": "foreign", "row_id": "2"}],
                   "sources": [{"id": "approved", "purpose": "background"}, {"id": "foreign", "purpose": "background"}],
                   "source_materials": [{"source_id": "approved", "status": "completed", "extraction_hash": "original-hash", "text": text},
                                        {"source_id": "foreign", "status": "completed", "extraction_hash": "foreign-hash", "text": "FOREIGN_PRIVATE_TEXT"}],
                   "knowledge_sources": [{"id": "approved", "sha256": "original-knowledge-hash", "text": text, "fact_scope": "PUBLIC_REFERENCE"},
                                         {"id": "foreign", "text": "FOREIGN_PRIVATE_KNOWLEDGE"}],
                   "statements": [{"text": "批准的核对意见", "source_ids": ["approved"]},
                                  {"text": "越权的核对意见", "source_ids": ["foreign"]}], "issues": [{"text": "待核对"}]}
        sources = Mock()
        sources.exists.return_value = sources_exist
        sources.filter.return_value = [SimpleNamespace(pk=source_id, parsed={"background": value})
                                       for source_id, value in (("approved", text), ("foreign", "FOREIGN_PRIVATE_BACKGROUND"))]
        return SimpleNamespace(sources=sources), payload

    def test_scope_precedes_selection_and_inputs_and_fact_audit_stay_full(self):
        task, payload = self.input_fixture()
        original = deepcopy(payload)
        with patch("portal.product_worker._source_items", return_value=payload["items"]):
            context = model_input(task, payload, ["approved", "foreign"], chapter=self.chapter)
        self.assertNotIn("FOREIGN_PRIVATE", str(context))
        self.assertNotIn("foreign", str(context))
        self.assertEqual(context["items"], [payload["items"][0]])
        self.assertEqual(context["sources"], [payload["sources"][0]])
        self.assertEqual(context["statements"], [payload["statements"][0]])
        self.assertEqual(context["knowledge_sources"][0]["fact_scope"], "PUBLIC_REFERENCE")
        self.assertEqual(context["knowledge_sources"][0]["sha256"], "original-knowledge-hash")
        self.assertNotIn("展板沿墙布置", context["background"])
        self.assertNotIn("展板沿墙布置", context["knowledge_sources"][0]["text"])
        self.assertIn("原全文", context["material_selection"]["instruction"])
        self.assertTrue(all(row["source_id"] == "approved" for row in context["material_selection"]["sources"]))
        self.assertEqual(payload, original)
        self.assertEqual(_project_facts(payload)["source_materials"], original["source_materials"])
        self.assertEqual(task.sources.filter.return_value[0].parsed["background"], original["background"])

    def test_default_blueprint_and_scoped_review_keep_original_full_behavior(self):
        task, payload = self.input_fixture()
        with patch("portal.product_worker._source_items", return_value=payload["items"]):
            blueprint = model_input(task, payload)
            review = model_input(task, payload, ["approved"])
        self.assertEqual(blueprint["background"], payload["background"] + "\n\n" + "\n\n".join(
            f"[资料 {item['source_id']} · {item['status']} · {item['extraction_hash']}]\n{item['text']}" for item in payload["source_materials"]))
        self.assertEqual(blueprint["knowledge_sources"], payload["knowledge_sources"])
        self.assertIn("展板沿墙布置", review["background"])
        self.assertEqual(review["knowledge_sources"], [payload["knowledge_sources"][0]])
        self.assertNotIn("material_selection", blueprint)
        self.assertNotIn("material_selection", review)

    def test_unseparable_legacy_aggregate_cannot_leak_an_unapproved_source(self):
        task, payload = self.input_fixture(sources_exist=False)
        payload["source_materials"] = []
        payload["background"] = "AUTHORIZED_AND_FOREIGN_AGGREGATED_PRIVATE_TEXT"
        for sources in (payload["sources"], [], None):
            with self.subTest(sources=sources):
                if sources is None:
                    payload.pop("sources", None)
                else:
                    payload["sources"] = sources
                with patch("portal.product_worker._source_items", return_value=payload["items"]):
                    context = model_input(task, payload, chapter=self.chapter)
                self.assertEqual(context["background"], "")
                self.assertNotIn(payload["background"], str(context))
                self.assertIn({"source_id": None, "representation": "input_background", "mode": "unavailable",
                               "reason": "legacy_aggregate_cannot_separate_authorized_sources"},
                              context["material_selection"]["sources"])
