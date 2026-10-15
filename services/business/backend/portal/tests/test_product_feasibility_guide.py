"""Contract tests for feasibility-guide prompts and blueprint persistence.

The model is stubbed: these tests do not claim that a real model classifies
project scope correctly.
"""

import json
from unittest.mock import patch

from django.test import override_settings

from portal.product_service import append_revision
from portal.product_worker import ExecutionError, _guard, claim_task, run_once

from . import test_product_worker as fixture
from .base import PortalTestCase


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_COST_POLICY={
    "approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100",
    "route_cost_caps": {"product_blueprint": "1", "product_writing": "1", "product_review": "1"},
})
class ProductFeasibilityGuideTests(PortalTestCase):
    setUp = fixture.ProductWorkerTests.setUp
    model_blueprint = fixture.ProductWorkerTests.model_blueprint
    assert_blueprint_scope_calls = fixture.ProductWorkerTests.assert_blueprint_scope_calls

    GUIDE_CHAPTERS = [
        "项目概述", "项目建设单位概况", "现状分析", "需求分析", "建设方案", "数据资源共享方案",
        "网络安全建设方案", "建设内容清单", "项目招标方案", "项目管理", "投资概算和资金来源", "项目可行性分析",
    ]

    def _queue_blueprint(self, conditions, feasibility_titles, missing=()):
        self.input_payload["conditions"] = list(conditions)
        self.input_revision = append_revision(self.task, "input", self.input_payload, actor=self.owner)
        self.task.input_version = self.input_revision.version
        self.task.pending_action, self.task.stage = "blueprint", "BLUEPRINT"
        self.task.save(update_fields=["input_version", "pending_action", "stage"])

        candidate = self.model_blueprint()
        technical = [chapter for chapter in candidate["chapters"] if chapter["family"] == "technical-solution"]
        feasibility_source = [chapter for chapter in candidate["chapters"] if chapter["family"] == "feasibility"]
        feasibility = [
            {**feasibility_source[index % len(feasibility_source)], "id": f"guide-feasibility-{index + 1}",
             "title": title}
            for index, title in enumerate(feasibility_titles)
        ]
        candidate["chapters"] = [*technical, *feasibility]
        for entry in candidate["feasibility_guide"]["sections"]:
            original_chapter = entry["section_id"].split(".")[0]
            title = self.GUIDE_CHAPTERS[int(original_chapter) - 1] if original_chapter.isdigit() else ""
            matched = [chapter["id"] for chapter in feasibility if chapter["title"] == title]
            entry.update(status="include" if matched else "not_applicable", chapter_ids=matched,
                         reason="合成模型回执按本用例目录保留或裁剪，实际范围判断由真实模型和人工确认。")
        candidate["conditions"] = [{"text": text, "type": "human"} for text in conditions]
        candidate["missing"] = list(missing)
        return candidate

    def _run_blueprint(self, model, candidate):
        model.side_effect = fixture.blueprint_model_responses(candidate, prompt_tokens=1, completion_tokens=1)
        run_once()
        self.task.refresh_from_db()
        self.assert_blueprint_scope_calls(model, candidate)
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code),
                         ("WAITING_REVIEW", "BLUEPRINT", ""))
        saved = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        self.assertEqual(saved.payload, candidate)
        self.assertFalse(saved.approvals.exists())
        self.assertEqual(saved.input_hash, self.input_revision.sha256)
        first_call = model.call_args_list[0]
        request = json.loads(first_call.args[2][1]["content"])
        return request, first_call.args[2][0]["content"], saved

    @patch("portal.product_worker.generate_for_use")
    def test_guide_prompt_and_pure_infrastructure_clipping_are_preserved(self, model):
        conditions = ["本项目仅建设道路排水设施，不建设信息系统，也不涉及数据共享和等级保护。"]
        selected = ["项目概述", "现状分析", "建设方案", "建设内容清单", "项目可行性分析"]
        candidate = self._queue_blueprint(conditions, selected)

        request, system_prompt, saved = self._run_blueprint(model, candidate)

        self.assertEqual(request["blueprint_structure"]["feasibility"], self.GUIDE_CHAPTERS)
        self.assertIn("榆林市市级政务信息化项目实施方案编制指南（建设类）", system_prompt)
        self.assertIn("纯基建项目在明确无信息化建设范围时", system_prompt)
        self.assertIn("sha256=1ffe2ace313aa4dc76e90ef9f2b91df6e1a2f0d3ef7896dfa9bb0ce2ab89be84", system_prompt)
        saved_titles = [chapter["title"] for chapter in saved.payload["chapters"]
                        if chapter["family"] == "feasibility"]
        self.assertEqual(saved_titles, selected)
        self.assertNotIn("数据资源共享方案", saved_titles)
        self.assertNotIn("网络安全建设方案", saved_titles)

    @patch("portal.product_worker.generate_for_use")
    def test_applicable_but_missing_it_chapter_and_missing_item_are_kept(self, model):
        conditions = ["项目建设范围包含政务数据共享。", "共享接口清单和数据目录待项目单位提供。"]
        missing = ["共享接口清单、数据目录及字段映射待提供。"]
        candidate = self._queue_blueprint(
            conditions, ["项目概述", "建设方案", "数据资源共享方案", "项目可行性分析"], missing,
        )

        request, system_prompt, saved = self._run_blueprint(model, candidate)

        self.assertIn("适用但资料不足的内容必须保留并记入missing或conditions待确认", system_prompt)
        self.assertEqual(request["input"]["conditions"], conditions)
        self.assertEqual(saved.payload["missing"], missing)
        self.assertIn("数据资源共享方案", [chapter["title"] for chapter in saved.payload["chapters"]
                                       if chapter["family"] == "feasibility"])

    @patch("portal.product_worker.generate_for_use")
    def test_mixed_infrastructure_keeps_relevant_it_chapters(self, model):
        conditions = ["道路改造同时包含交通信号控制系统。", "信号数据需要与交管平台共享，接口范围待确认。"]
        selected = ["项目概述", "建设方案", "数据资源共享方案", "网络安全建设方案",
                    "建设内容清单", "项目可行性分析"]
        candidate = self._queue_blueprint(conditions, selected)

        _, system_prompt, saved = self._run_blueprint(model, candidate)

        self.assertIn("混合项目逐个子项判断", system_prompt)
        saved_titles = [chapter["title"] for chapter in saved.payload["chapters"]
                        if chapter["family"] == "feasibility"]
        self.assertIn("数据资源共享方案", saved_titles)
        self.assertIn("网络安全建设方案", saved_titles)
        self.assertEqual(saved_titles, selected)

    def test_guard_rejects_approval_bound_to_old_rules_hash(self):
        from portal.product_rules import rules_hash

        task_id, fence, _ = claim_task()
        previous_rules_hash = rules_hash()
        self.assertEqual(self.blueprint.approvals.get().authorization["rules_hash"], previous_rules_hash)

        with patch("portal.product_rules.rules_hash", return_value="f" * 64):
            with self.assertRaises(ExecutionError) as error:
                _guard(task_id, fence)

        self.assertEqual(error.exception.code, "blueprint_approval_required")
