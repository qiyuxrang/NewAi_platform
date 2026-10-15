"""Synthetic pure-function checks: lossless facts, provenance and compact rows."""

from copy import deepcopy
import json
import unittest

from portal.product_blueprint_context import scope_context


def restore_items(table):
    missing = {row: set(columns) for row, columns in table["missing"]}
    return [{key: value for column, (key, value) in enumerate(zip(table["columns"], values))
             if column not in missing.get(index, set())}
            for index, values in enumerate(table["rows"])]


class BlueprintScopeContextTests(unittest.TestCase):
    def fixture(self):
        return {
            "project": " 设备改造\n", "requirements": "不得新增设备；仅在停机后实施。",
            "conditions": ["若审核未通过则不建设", "数量待确认"],
            "background": "[资料 S1 · needs_review · hash]\n[第2行 · b2]\n未建设新机房。\n条件：仅复用现有房间。",
            "statements": [{"text": "范围待确认，不代表不适用", "source_ids": ["S1"], "status": "UNKNOWN"}],
            "sources": [{"id": "S1", "sha256": "hash", "purpose": "equipment", "status": "UNKNOWN"}],
            "issues": [{"code": "invalid_quantity", "item_index": 1}],
            "items": [
                {"row_id": "1", "source_item_id": "S1:b2", "source_id": "S1", "source_row": 2,
                 "source_location": {"sheet": "设备", "row": 2}, "source_section": "原煤仓",
                 "name": "开关柜", "specification": "暂不更换；如检测不合格再换", "unit": "台", "quantity": -1,
                 "备注": "并非已确认数量", "未知业务字段": {"限定": "仅复用", "歧义": "待确认"}, "nullable": None},
                {"row_id": "1", "source_item_id": "S1:b3", "source_id": "S1", "source_row": 3,
                 "source_location": {"sheet": "设备", "row": 3}, "source_section": "产品仓",
                 "name": "开关柜", "unit": "台", "quantity": "待确认", "source_edited": True},
            ],
            "knowledge_sources": [{"id": "K1", "text": "外部资料要求新建机房，不得成为项目事实。",
                                   "provider": "ragflow", "status": "UNKNOWN", "timeliness": "UNKNOWN"}],
            "future_business_context": {"保留": "不得丢弃未知字段"},
        }

    def test_verbatim_facts_all_values_and_original_source_indices(self):
        context = self.fixture()
        result = scope_context(context, {"chapters": []})
        for key in ("project", "requirements", "conditions", "background", "statements", "sources", "issues",
                    "future_business_context"):
            self.assertEqual(result[key], context[key])
        self.assertEqual(restore_items(result["items"]), context["items"])
        self.assertEqual(result["items"]["source_path"], "/items")
        self.assertIn("pending", result["scope_policy"])
        self.assertIn("不得因未出现关键词", result["scope_policy"])
        # Repeated row IDs are not merged; missing differs from explicit null.
        self.assertEqual(len(result["items"]["rows"]), 2)
        self.assertIsNone(restore_items(result["items"])[0]["nullable"])
        self.assertNotIn("nullable", restore_items(result["items"])[1])

    def test_references_exclude_body_and_base_remains_inference(self):
        context = self.fixture()
        chapters = [{"id": "c1", "title": "新建机房", "scope": "唯一目录线索内容", "source_ids": ["S1"]}]
        result = scope_context(context, {"chapters": chapters})
        self.assertEqual(result["knowledge_sources"]["rows"], [
            {"id": "K1", "provider": "ragflow", "status": "UNKNOWN", "timeliness": "UNKNOWN"}])
        self.assertNotIn(context["knowledge_sources"][0]["text"], json.dumps(result, ensure_ascii=False))
        self.assertNotIn("blueprint_hints", result)
        self.assertNotIn(chapters[0]["scope"], json.dumps(result, ensure_ascii=False))
        self.assertIn("基础目录base章节仅属于模型推断线索", result["scope_policy"])

    def test_deterministic_and_deeply_detached(self):
        context, base = self.fixture(), {"chapters": [{"id": "c", "source_ids": ["S1"]}]}
        before = deepcopy((context, base))
        result = scope_context(context, base)
        self.assertEqual(result, scope_context(context, base))
        self.assertEqual((context, base), before)
        result["statements"][0]["text"] = "changed"
        result["items"]["rows"][0][result["items"]["columns"].index("source_location")]["row"] = 99
        self.assertEqual((context, base), before)

    def test_all_rows_survive_with_substantially_less_repeated_keys(self):
        context = self.fixture()
        template = context["items"][0]
        context["items"] = [{**deepcopy(template), "row_id": str(index), "source_item_id": f"S1:b{index}",
                             "source_row": index, "source_location": {"sheet": "设备", "row": index}}
                            for index in range(600)]
        result = scope_context(context, {"chapters": []})
        packed = lambda value: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        self.assertLess(packed(result), packed(context) * .65)
        self.assertEqual(restore_items(result["items"]), context["items"])
        self.assertEqual(len(result["items"]["rows"]), 600)


if __name__ == "__main__":
    unittest.main()
