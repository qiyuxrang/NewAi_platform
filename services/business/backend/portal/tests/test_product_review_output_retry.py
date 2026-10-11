import json
from unittest.mock import patch

from django.test import override_settings

from portal.product_models import DocumentApproval, DocumentRevision, DocumentTask
from portal.product_service import append_revision, approval_authorization, digest
from portal.product_worker import ExecutionError, _model, _review_family, _validated_reviewer, claim_task

from .base import PortalTestCase


@override_settings(
    PRODUCT_P1_ENABLED=True,
    PRODUCT_MODEL_CALLS_ALLOWED=True,
    PRODUCT_MAX_MODEL_CALLS=10,
    PRODUCT_COST_POLICY={
        "approval_ref": "isolated-test-only",
        "currency": "TEST",
        "max_task_cost": "100",
        "route_cost_caps": {"product_review": "1"},
    },
)
class ProductReviewOutputRetryTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("review-output-writer", "product")
        input_payload = {
            "project": "独立复核输出契约",
            "requirements": "仅使用已提供的测试资料",
            "background": "测试背景",
            "items": [{"row_id": "r1", "name": "测试设备", "quantity": "1", "unit": "台"}],
            "conditions": [],
        }
        blueprint_payload = {
            "purpose": "核对测试资料",
            "audience": "测试审核人",
            "chapters": [{"id": "chapter-1", "title": "测试章节", "scope": "核对资料", "source_ids": ["r1"]}],
            "conditions": [],
            "missing": [],
            "conflicts": [],
            "template_version": "frozen-original-v1",
        }
        self.task = DocumentTask.objects.create(
            owner=self.owner,
            title="独立复核输出契约",
            idempotency_key="review-output-retry-test",
            payload_hash=digest(input_payload),
            state="QUEUED",
            stage="WRITING",
            pending_action="write",
        )
        self.input_revision = append_revision(self.task, "input", input_payload, actor=self.owner)
        self.blueprint = append_revision(
            self.task,
            "blueprint",
            blueprint_payload,
            input_hash=self.input_revision.sha256,
            actor=self.owner,
        )
        self.task.input_version = self.input_revision.version
        self.task.blueprint_version = self.blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        DocumentApproval.objects.create(
            task=self.task,
            revision=self.blueprint,
            actor=self.owner,
            decision="approve",
            sha256=self.blueprint.sha256,
            authorization=approval_authorization(self.task, self.owner),
        )
        self.chapter = append_revision(
            self.task,
            "chapter",
            {
                "chapter_id": "chapter-1",
                "title": "测试章节",
                "paragraphs": ["正文只用于验证独立复核的输出契约。"],
                "source_ids": ["r1"],
            },
            input_hash=self.input_revision.sha256,
            blueprint_hash=self.blueprint.sha256,
        )

    def claimed(self):
        claimed = claim_task()
        self.assertIsNotNone(claimed)
        return claimed

    def test_invalid_reviewer_type_gets_one_correction_and_returns_actual_review(self):
        task_id, fence, attempt_id = self.claimed()
        actual_issue = "实施时间尚未确认，不能声称已经确定实施窗口。"
        corrected = {"passed": False, "issues": [actual_issue]}
        with patch("portal.product_worker.generate_for_use") as model:
            model.side_effect = [
                {"content": json.dumps({"passed": "false", "issues": []})},
                {"content": json.dumps(corrected, ensure_ascii=False)},
            ]

            result = _model(
                task_id,
                fence,
                attempt_id,
                "product_review",
                {"action": "independent_review", "schema": {"passed": "boolean", "issues": ["string"]}},
            )

        self.assertEqual(result, corrected)
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("independent_review_correction", correction)
        self.assertIn("passed必须是JSON布尔值true或false", correction["independent_review_correction"])
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)

    def test_twice_invalid_reviewer_is_rejected_without_saving_review(self):
        task_id, fence, attempt_id = self.claimed()
        invalid = {"passed": 1, "issues": ["类型错误"]}
        with patch("portal.product_worker.generate_for_use") as model:
            model.return_value = {"content": json.dumps(invalid, ensure_ascii=False)}

            with self.assertRaises(ExecutionError) as caught:
                _review_family(
                    task_id,
                    fence,
                    attempt_id,
                    self.task,
                    self.input_revision,
                    self.blueprint,
                    [self.chapter],
                    "technical-solution",
                )

        self.assertEqual(caught.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="review").exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][0]["parse_error"], "invalid_model_output")
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)

    def test_valid_reviewer_preserves_false_passed_and_real_issues(self):
        task_id, fence, attempt_id = self.claimed()
        actual_issues = ["设备数量与正文中的承诺不一致。", "来源没有证明该设备已完成部署。"]
        with patch("portal.product_worker.generate_for_use") as model:
            model.return_value = {
                "content": json.dumps({"passed": False, "issues": actual_issues}, ensure_ascii=False)
            }

            review = _review_family(
                task_id,
                fence,
                attempt_id,
                self.task,
                self.input_revision,
                self.blueprint,
                [self.chapter],
                "technical-solution",
            )

        self.assertEqual(review["status"], "issues_found")
        self.assertEqual(review["issues"], actual_issues)
        self.assertFalse(review["coverage"]["all_batches_passed"])
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="review").exists())

    def test_compliance_observation_gets_one_correction_and_keeps_real_issue(self):
        task_id, fence, attempt_id = self.claimed()
        actual_issue = "前段合规，但后段数字无依据。"
        mixed = {
            "passed": False,
            "issues": [actual_issue, "准确引用了官方文档观点，合规。"],
        }
        corrected = {"passed": False, "issues": [actual_issue]}
        with patch("portal.product_worker.generate_for_use") as model:
            model.side_effect = [
                {"content": json.dumps(mixed, ensure_ascii=False)},
                {"content": json.dumps(corrected, ensure_ascii=False)},
            ]

            result = _model(
                task_id,
                fence,
                attempt_id,
                "product_review",
                {"action": "independent_review", "schema": {"passed": "boolean", "issues": ["string"]}},
            )

        self.assertEqual(result, corrected)
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        instruction = correction["independent_review_correction"]
        self.assertIn("不得把明确合规的观察", instruction)
        self.assertIn("不得列假设的未来问题", instruction)
        self.assertIn("逐项原样保留全部真实问题", instruction)

    def test_explicit_compliance_conclusions_are_invalid_but_noncompliance_is_an_issue(self):
        compliance_observations = [
            "这部分当前表述合规。",
            "本段目前合规。",
            "本段基本合规。",
            "准确引用了官方文档观点，合规。",
            "此片段本身无实质错误可判。需人工审核完整段落。",
            "chapter-4-data-collection-scheme/paragraph_index=3: 片段不完整（'为确保进入存储层的数据具备可用性'）。根据review_contract，sample_truncated不代表正文截断，但此片段本身无实质错误可判。需人工审核完整段落。",
        ]
        for issue in compliance_observations:
            with self.subTest(issue=issue):
                with self.assertRaises(ExecutionError) as caught:
                    _validated_reviewer({"passed": False, "issues": [issue]})
                self.assertEqual(caught.exception.code, "invalid_model_output")

        self.assertFalse(_validated_reviewer({"passed": False, "issues": ["该段并不合规，数字无依据。"]}))
        self.assertFalse(_validated_reviewer({"passed": False, "issues": ["前段合规，但后段数字无依据。"]}))
        self.assertFalse(_validated_reviewer({"passed": False, "issues": ["前段未发现错误，但后段数字无依据。"]}))

    def test_repeated_no_defect_observation_fails_closed_without_review(self):
        task_id, fence, attempt_id = self.claimed()
        contradictory = {
            "passed": False,
            "issues": ["此片段本身无实质错误可判。需人工审核完整段落。"],
        }
        with patch("portal.product_worker.generate_for_use") as model:
            model.return_value = {"content": json.dumps(contradictory, ensure_ascii=False)}

            with self.assertRaises(ExecutionError) as caught:
                _review_family(
                    task_id,
                    fence,
                    attempt_id,
                    self.task,
                    self.input_revision,
                    self.blueprint,
                    [self.chapter],
                    "technical-solution",
                )

        self.assertEqual(caught.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="review").exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][0]["parse_error"], "invalid_model_output")
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)

    def test_leading_compliance_with_later_real_defect_remains_an_issue(self):
        task_id, fence, attempt_id = self.claimed()
        actual_issue = "前段合规，但后段数字无依据。"
        with patch("portal.product_worker.generate_for_use") as model:
            model.return_value = {
                "content": json.dumps({"passed": False, "issues": [actual_issue]}, ensure_ascii=False)
            }

            review = _review_family(
                task_id,
                fence,
                attempt_id,
                self.task,
                self.input_revision,
                self.blueprint,
                [self.chapter],
                "technical-solution",
            )

        self.assertEqual(review["status"], "issues_found")
        self.assertEqual(review["issues"], [actual_issue])
        self.assertEqual(model.call_count, 1)
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="review").exists())

    def test_passed_true_with_real_issues_still_blocks_review(self):
        task_id, fence, attempt_id = self.claimed()
        actual_issue = "来源没有证明正文中已经部署该设备。"
        with patch("portal.product_worker.generate_for_use") as model:
            model.return_value = {
                "content": json.dumps({"passed": True, "issues": [actual_issue]}, ensure_ascii=False)
            }

            review = _review_family(
                task_id,
                fence,
                attempt_id,
                self.task,
                self.input_revision,
                self.blueprint,
                [self.chapter],
                "technical-solution",
            )

        self.assertEqual(review["status"], "issues_found")
        self.assertEqual(review["issues"], [actual_issue])
        self.assertFalse(review["coverage"]["all_batches_passed"])
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="review").exists())

    def test_semantic_correction_shares_the_json_retry_budget(self):
        task_id, fence, attempt_id = self.claimed()
        with patch("portal.product_worker.generate_for_use") as model:
            model.side_effect = [
                {"content": "not JSON"},
                {"content": json.dumps({"passed": False, "issues": [None]})},
            ]

            with self.assertRaises(ExecutionError) as caught:
                _model(
                    task_id,
                    fence,
                    attempt_id,
                    "product_review",
                    {"action": "independent_review", "schema": {"passed": "boolean", "issues": ["string"]}},
                )

        self.assertEqual(caught.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)

    def test_issue_list_and_item_limits_are_enforced_and_inclusive_bounds_are_valid(self):
        task_id, fence, attempt_id = self.claimed()
        schema = {"passed": "boolean", "issues": ["string"]}
        cases = [
            {"passed": False, "issues": ["问题"] * 101},
            {"passed": False, "issues": ["问" * 2001]},
        ]
        bounded = {"passed": False, "issues": ["真" * 2000] * 100}
        with patch("portal.product_worker.generate_for_use") as model:
            for invalid in cases:
                with self.subTest(issue_count=len(invalid["issues"]), max_length=max(map(len, invalid["issues"]))):
                    model.reset_mock()
                    model.side_effect = [
                        {"content": json.dumps(invalid, ensure_ascii=False)},
                        {"content": json.dumps(bounded, ensure_ascii=False)},
                    ]
                    result = _model(
                        task_id, fence, attempt_id, "product_review",
                        {"action": "independent_review", "schema": schema},
                    )
                    self.assertEqual(result, bounded)
                    self.assertEqual(model.call_count, 2)

        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 4)
