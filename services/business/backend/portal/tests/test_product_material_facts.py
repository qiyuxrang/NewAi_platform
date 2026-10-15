from django.test import SimpleTestCase

from portal.product_content_quality import (
    inspect_content_quality, project_fact_text, unsupported_numeric_claims,
)
from portal.product_worker import _project_facts
from portal.product_service import preserve_input_provenance, validate_input


class ProductMaterialFactsTests(SimpleTestCase):
    def test_uploaded_project_text_supports_parameters_and_status(self):
        payload = {"source_materials": [{
            "source_id": "company-file", "extraction_hash": "metadata-180",
            "text": "数据保留期为180天。调研确认：现有系统缺乏统一认证。",
        }]}
        facts = _project_facts(payload)
        paragraphs = ["数据保留期为180天。", "现有系统缺乏统一认证。"]
        self.assertEqual(unsupported_numeric_claims(paragraphs, project_facts=facts), [])
        self.assertEqual(inspect_content_quality(paragraphs, project_facts=facts), [])
        self.assertNotIn("metadata-180", project_fact_text(facts))
        self.assertTrue(unsupported_numeric_claims(["数据保留期为365天。"], project_facts=facts))

    def test_equipment_specification_reaches_fact_text(self):
        payload = {"items": [{"name": "数据服务器", "quantity": 2, "unit": "台",
                               "specification": "内存容量为128GB。"}]}
        self.assertIn("数据服务器规格：内存容量为128GB。", project_fact_text(_project_facts(payload)))

    def test_input_edits_keep_specifications_only_for_unchanged_source_rows(self):
        previous = {"project": "设备项目", "requirements": "生成方案", "background": "", "conditions": [],
                    "items": [{"row_id": "1", "name": "数据服务器", "quantity": 2, "unit": "台",
                               "source_id": "company-file", "source_row": 1,
                               "source_item_id": "company-file:1", "specification": "内存容量为128GB。"}]}
        editable = {**previous, "items": [{key: previous["items"][0][key]
                    for key in ("row_id", "name", "quantity", "unit", "source_item_id")}]}
        unchanged = preserve_input_provenance(previous, validate_input(editable))
        self.assertEqual(unchanged["items"][0]["specification"], "内存容量为128GB。")
        editable["items"][0]["name"] = "交换机"
        changed = preserve_input_provenance(previous, validate_input(editable))
        self.assertTrue(changed["items"][0]["source_edited"])
        self.assertNotIn("specification", changed["items"][0])

    def test_public_uploads_do_not_authorize_project_claims(self):
        reference = "数据保留期为180天。现有系统缺乏统一认证。"
        public_document = ("标题：公开指南\n来源机构：example.org\n精确URL：https://example.org\n"
                           + reference + "\n用途声明：只做通用参考非本项目事实。")
        for material in ({"kind": "public", "text": reference},
                         {"fact_scope": "PUBLIC_REFERENCE", "text": reference},
                         {"reference_only": True, "text": reference},
                         {"text": public_document}):
            with self.subTest(material=material):
                facts = _project_facts({"source_materials": [material]})
                self.assertEqual(project_fact_text(facts).strip(), "")
                self.assertTrue(unsupported_numeric_claims(["数据保留期为180天。"], project_facts=facts))
                self.assertTrue(inspect_content_quality(["现有系统缺乏统一认证。"], project_facts=facts))
