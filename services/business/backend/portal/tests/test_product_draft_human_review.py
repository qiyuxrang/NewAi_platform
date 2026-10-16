"""Draft files require human review; formal model review and integrity checks remain."""
import json
from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings

from portal.product_service import append_revision
from portal.product_worker import ExecutionError, _content_review_current, _ensure_content_review
from .base import PortalTestCase
from . import test_product_feasibility_flow as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=3,
                   PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST",
                       "max_task_cost": "100", "route_cost_caps": {
                           "product_blueprint": "1", "product_writing": "1", "product_review": "1"}})
class DraftHumanReviewTests(PortalTestCase):
    setUp = fixture.FeasibilityFlowTests.setUp
    saved_chapter = fixture.FeasibilityFlowTests.saved_chapter

    @patch("portal.product_worker.generate_for_use", side_effect=AssertionError("Draft AI review must not run"))
    def test_both_draft_actions_skip_all_review_for_both_report_families(self, model):
        feasibility = self.saved_chapter()
        technical = append_revision(self.task, "chapter", {
            "chapter_id": "chapter-1", "title": "章节1", "source_ids": ["r1"],
            "paragraphs": ["沿用清单中2台测试设备，实施前由负责人核对。"]},
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256,
            family="technical-solution")
        for action in ("generate_outputs", "three_drafts"):
            self.task.pending_action = action
            self.task.save(update_fields=["pending_action"])
            for family, chapters in (("feasibility", [feasibility]), ("technical-solution", [technical])):
                with self.subTest(action=action, family=family):
                    review = _ensure_content_review(self.task, self.fence, self.attempt_id,
                        self.input_revision, self.blueprint, chapters, family)
                    self.assertEqual(review.payload["model_review"]["status"], "not_run")
                    self.assertNotIn("guide_review", review.payload)
                    self.assertFalse(review.payload["passed"])
                    self.assertTrue(review.payload["program_checks_complete"])
                    self.assertTrue(review.payload["full_document_human_review_required"])
                    self.assertTrue(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
                    self.task.refresh_from_db()
                    phase = self.task.checkpoint["analysis_progress"][
                        "review_feasibility" if family == "feasibility" else "review_technical"]
                    self.assertEqual(phase["status"], "skipped")
                    self.assertTrue(phase["human_review_required"])
        model.assert_not_called()

    def test_feasibility_program_checks_still_bind_body_sources_policy_and_approval(self):
        chapters = [self.saved_chapter()]
        review = _ensure_content_review(self.task, self.fence, self.attempt_id,
            self.input_revision, self.blueprint, chapters, "feasibility")
        for index, target in enumerate((review, self.input_revision, self.blueprint, chapters[0]), 1):
            with self.subTest(kind=target.kind):
                changed = deepcopy(target)
                changed.payload["tampered"] = True
                args = [self.task, review, self.input_revision, self.blueprint, chapters]
                args[index] = [changed] if index == 4 else changed
                self.assertFalse(_content_review_current(*args))
        with patch("portal.product_content_quality.content_quality_policy_hash", return_value="0" * 64):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
        with patch("portal.product_worker.approved_blueprint", return_value=None):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
        with patch("portal.product_worker._source_items", side_effect=ExecutionError("source_snapshot_changed")):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
            with self.assertRaises(ExecutionError):
                _ensure_content_review(self.task, self.fence, self.attempt_id,
                    self.input_revision, self.blueprint, chapters, "feasibility")

    @patch("portal.product_worker.generate_for_use")
    def test_formal_feasibility_still_reviews_body_and_guide_and_rejects_issues(self, model):
        self.task.pending_action = "render"
        self.task.save(update_fields=["pending_action"])
        chapters = [self.saved_chapter()]
        def respond(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            if request.get("review_contract", {}).get("guide_audit_only"):
                return fixture.FeasibilityFlowTests.covered_reply(*args, **kwargs)
            return {"content": json.dumps({"passed": False, "issues": ["实际内容仍需修正"]})}
        model.side_effect = respond
        with self.assertRaises(ExecutionError) as caught:
            _ensure_content_review(self.task, self.fence, self.attempt_id,
                self.input_revision, self.blueprint, chapters, "feasibility")
        self.assertEqual(caught.exception.code, "content_review_required")
        requests = [json.loads(call.args[2][1]["content"]) for call in model.call_args_list]
        self.assertTrue(any(request.get("review_contract", {}).get("guide_audit_only") for request in requests))
        self.assertTrue(any(not request.get("review_contract", {}).get("guide_audit_only") for request in requests))
        review = self.task.revisions.filter(kind="review", family="feasibility").latest("version")
        self.assertEqual(review.payload["model_review"]["status"], "issues_found")
        self.assertNotIn("generation_policy", review.payload)
