import json
from unittest.mock import patch

from django.test import override_settings

from portal.product_worker import ExecutionError, _generate_diagrams
from .base import PortalTestCase
from . import test_product_review_output_retry as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_MAX_MODEL_CALLS=10,
    PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100",
                         "route_cost_caps": {"product_writing": "1", "product_review": "1"}})
class ProductDiagramOutputRetryTests(PortalTestCase):
    setUp = fixture.ProductReviewOutputRetryTests.setUp
    claimed = fixture.ProductReviewOutputRetryTests.claimed

    def document(self):
        return {"family": "technical-solution", "metadata": {"title": "测试图表正文依据"}, "blocks": [
            {"id": "H1", "type": "heading", "level": 1, "text": "采集设计"},
            {"id": "P1", "type": "paragraph", "text": "数据采集方案支持权限控制和审计，具体参数需另行确认。", "source_ids": ["r1"]},
            {"id": "DIAGRAM_01_FIGURE", "type": "figure", "caption": "采集与审计"},
        ]}

    def reply(self, *, valid=True):
        item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "采集与审计", "description": "先验证权限并记录审计结果。",
                "source": "flowchart LR\nA1[权限控制] --> B2[审计流程]", "evidence_block_ids": ["P1"], "anchor_text": "权限控制"}
        if not valid:
            item["anchor_text"] = "未提供的虚构节点"
        return {"content": json.dumps({"diagrams": [item]}, ensure_ascii=False)}

    @patch("portal.product_worker.generate_for_use")
    def test_invalid_diagram_has_one_correction_and_returns_only_validated_items(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.side_effect = [self.reply(valid=False), self.reply()]
        diagrams = _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["anchor_text"], "权限控制")
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("diagram_validation_correction", correction)
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_twice_invalid_diagram_fails_closed_without_artifact(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.return_value = self.reply(valid=False)
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_json_and_diagram_semantics_share_one_retry(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.side_effect = [{"content": "not JSON"}, self.reply(valid=False), self.reply()]
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)

    @patch("portal.product_worker.generate_for_use")
    def test_fabricated_diagram_budget_fails_with_locatable_diagnostics(self, model):
        task_id, fence, attempt_id = self.claimed()
        reply = self.reply()
        payload = json.loads(reply["content"])
        payload["diagrams"][0]["title"] = "项目投资预算10万元"
        model.return_value = {"content": json.dumps(payload, ensure_ascii=False)}
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)
        from portal.product_worker import _bounded_quality_issues
        issues = _bounded_quality_issues(error.exception.quality_issues)
        self.assertTrue(issues)
        self.assertEqual(issues[0]["figure_id"], "DIAGRAM_01_FIGURE")
        self.assertEqual(issues[0]["field"], "title")
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_revoked_permission_prevents_diagram_correction_call(self, model):
        task_id, fence, attempt_id = self.claimed()
        def revoke(*args):
            self.owner.roles.clear()
            return self.reply(valid=False)
        model.side_effect = revoke
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "permission_changed")
        self.assertEqual(model.call_count, 1)
        self.assertFalse(self.task.artifacts.exists())
