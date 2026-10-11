import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.model_config import GatewayModel, ModelRoute, Provider
from portal.models import Module
from portal.product_models import DocumentApproval
from portal.product_service import append_revision, approval_authorization, digest
from portal.product_worker import (ExecutionError, _content_review_current, _ensure_content_review,
                                  _finish, _render, _review_family, claim_task)
from .base import PortalTestCase
from . import test_product_review_output_retry as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_MAX_MODEL_CALLS=100,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_COST_POLICY={
                       "approval_ref": "isolated-resume-test", "currency": "TEST", "max_task_cost": "1000",
                       "route_cost_caps": {"product_review": "1"}})
class ProductReviewBatchResumeTests(PortalTestCase):
    def setUp(self):
        fixture.ProductReviewOutputRetryTests.setUp(self)
        symbols = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳"
        paragraphs = []
        for index in range(8):
            values = "".join(hashlib.sha256(f"resume:{index}:{part}".encode()).hexdigest() for part in range(79))
            paragraphs.append("".join(symbols[int(value, 16)] for value in values)[:5000])
        self.chapter = append_revision(self.task, "chapter", {**self.chapter.payload, "paragraphs": paragraphs},
                                       input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        self.claim = claim_task()
        self.assertIsNotNone(self.claim)

    def review(self):
        return _review_family(*self.claim, self.task, self.input_revision, self.blueprint, [self.chapter], "technical-solution")

    def cache(self):
        self.task.refresh_from_db()
        return self.task.checkpoint["content_review_batches"]["technical-solution"]

    def passed_reply(self, *args):
        return {"content": '{"passed":true,"issues":[]}'}

    def interrupted(self, model):
        def reply(*args):
            request = json.loads(args[2][1]["content"])
            index = request["review_contract"]["batch_index"]
            if index == 4:
                return {"content": '{"passed":"false","issues":[]}'}
            return {"content": json.dumps({"passed": index != 1,
                "issues": ["首批发现真实来源归属问题"] if index == 1 else []})}
        model.side_effect = reply
        with self.assertRaises(ExecutionError) as error:
            self.review()
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 5)

    def restart(self):
        _finish(*self.claim, "FAILED", "WRITING", "invalid_model_output")
        self.task.refresh_from_db()
        self.task.state = "QUEUED"
        self.task.save(update_fields=["state"])
        self.claim = claim_task()
        self.assertIsNotNone(self.claim)

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_fourth_batch_failure_preserves_real_issues_and_restart_calls_only_remaining_batches(self, model, render):
        self.interrupted(model)
        partial = self.cache()
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["completed_count"], 3)
        self.assertEqual(partial["issues_preview"], ["首批发现真实来源归属问题"])
        self.assertLessEqual(len(json.dumps(partial, ensure_ascii=False)), 1100000)
        self.assertNotIn("paragraphs", partial["binding"])
        self.assertFalse(self.task.revisions.filter(kind="review").exists())
        self.assertFalse(self.task.artifacts.exists())
        # A partial cache cannot authorize a Word render when further calls are closed.
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=False):
            with self.assertRaises(ExecutionError) as error:
                _render(self.task, self.claim[1], self.claim[2], self.input_revision, self.blueprint, [self.chapter])
        self.assertEqual(error.exception.code, "model_authorization_required")
        render.assert_not_called()
        self.assertFalse(self.task.revisions.filter(kind="review").exists())
        self.restart()
        model.reset_mock()
        model.side_effect = self.passed_reply
        result = self.review()
        requested = [json.loads(call.args[2][1]["content"])["review_contract"]["batch_index"] for call in model.call_args_list]
        self.assertEqual(requested, list(range(4, partial["total_count"] + 1)))
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["issues"], ["首批发现真实来源归属问题"])
        self.assertTrue(result["coverage"]["complete"])
        self.assertFalse(result["coverage"]["all_batches_passed"])
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 5 + len(requested))
        # Complete resumed findings still block files, with no extra model calls.
        with self.assertRaises(ExecutionError) as error:
            _render(self.task, self.claim[1], self.claim[2], self.input_revision, self.blueprint, [self.chapter])
        self.assertEqual(error.exception.code, "content_review_required")
        self.assertEqual(model.call_count, len(requested))
        render.assert_not_called()
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_complete_exact_bound_cache_resumes_with_zero_new_calls_and_preserves_coverage(self, model):
        model.side_effect = self.passed_reply
        first = self.review()
        calls = model.call_count
        self.restart()
        model.reset_mock()
        second = self.review()
        model.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), calls)
        self.assertTrue(self.cache()["complete"])

    @patch("portal.product_worker.generate_for_use")
    def test_corrected_valid_response_binds_original_batch_and_resumes_without_new_calls(self, model):
        first = True
        def reply(*args):
            nonlocal first
            if first:
                first = False
                return {"content": '{"passed":"true","issues":[]}'}
            return self.passed_reply(*args)
        model.side_effect = reply
        result = self.review()
        self.assertEqual(model.call_count, result["coverage"]["batch_count"] + 1)
        batch = self.cache()["batches"][0]
        self.assertNotEqual(batch["request_sha256"], batch["model_call_input_sha256"])
        self.restart()
        model.reset_mock()
        recovered = self.review()
        model.assert_not_called()
        self.assertEqual(recovered, result)

    @patch("portal.product_worker.generate_for_use")
    def test_actual_correction_request_reserves_exact_json_space_and_preserves_both_hard_limits(self, model):
        from portal.product_worker import _model, _review_batch_payloads, _review_payload, _review_request_size
        payload, scope = _review_payload(self.task, self.input_revision, self.blueprint, [self.chapter], "technical-solution")
        self.assertEqual(scope, "sampled")
        plan = _review_batch_payloads(payload, [self.chapter])
        for batch in plan:
            self.assertLessEqual(_review_request_size(batch), 14500)
            self.assertLessEqual(sum(len(text) for chapter in batch["chapters"] for text in chapter["paragraphs"]), 7000)
        request = deepcopy(plan[0])
        request["boundary_fixture_context"] = ""
        allowance = 14500 - _review_request_size(request)
        self.assertGreaterEqual(allowance, 0)
        request["boundary_fixture_context"] = '"\\\n' * (allowance // 6) + "甲" * (allowance % 6)
        self.assertEqual(_review_request_size(request), 14500)
        model.side_effect = [{"content": '{"passed":"true","issues":[]}'}, self.passed_reply()]
        result = _model(*self.claim, "product_review", request)
        self.assertEqual(result, {"passed": True, "issues": []})
        self.assertEqual(model.call_count, 2)
        actual = [json.loads(call.args[2][1]["content"]) for call in model.call_args_list]
        self.assertIn("independent_review_correction", actual[1])
        self.assertEqual(len(json.dumps(actual[1], ensure_ascii=False)), 14500)
        self.assertTrue(all(len(json.dumps(value, ensure_ascii=False)) <= 14500 for value in actual))
        oversized = deepcopy(request)
        oversized["boundary_fixture_context"] += "甲" * 1000
        too_much_body = {"action": "independent_review", "chapters": [{"paragraphs": ["甲" * 7001]}],
                         "schema": {"passed": "boolean", "issues": ["string"]}}
        for invalid in (oversized, too_much_body):
            with self.assertRaises(ExecutionError) as error:
                _model(*self.claim, "product_review", invalid)
            self.assertEqual(error.exception.code, "request_too_large")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 2)

    @patch("portal.product_worker.generate_for_use")
    def test_saved_review_requires_complete_current_plan_configuration_and_actual_response_evidence(self, model):
        from portal.product_worker import _review_batch_payloads
        model.side_effect = self.passed_reply
        review = _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                       self.blueprint, [self.chapter])
        self.assertTrue(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        def changed_plan(*args):
            plan = _review_batch_payloads(*args)
            plan[0]["review_contract"]["context_scope"] = "updated full review plan"
            return plan
        with patch("portal.product_worker._review_batch_payloads", side_effect=changed_plan):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        with patch("portal.product_worker._review_route_hash", return_value="d" * 64):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        self.task.refresh_from_db()
        self.task.checkpoint["calls"][0]["response_sha256"] = "e" * 64
        self.task.save(update_fields=["checkpoint"])
        self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        model.reset_mock()
        repaired = _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                          self.blueprint, [self.chapter])
        self.assertEqual(model.call_count, 1)
        self.assertNotEqual(repaired.pk, review.pk)
        self.assertTrue(_content_review_current(self.task, repaired, self.input_revision, self.blueprint, [self.chapter]))

    @patch("portal.product_worker.generate_for_use")
    def test_legacy_review_without_current_binding_cannot_authorize_files(self, model):
        model.side_effect = self.passed_reply
        review = _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                       self.blueprint, [self.chapter])
        payload = deepcopy(review.payload)
        del payload["model_review"]["coverage"]["review_binding"]
        legacy = append_revision(self.task, "review", payload, input_hash=self.input_revision.sha256,
                                 blueprint_hash=self.blueprint.sha256, reason="worker_review")
        self.task.refresh_from_db()
        self.task.checkpoint.pop("content_review_batches")
        self.task.save(update_fields=["checkpoint"])
        self.assertFalse(_content_review_current(self.task, legacy, self.input_revision, self.blueprint, [self.chapter]))
        model.reset_mock()
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=False):
            with self.assertRaises(ExecutionError) as error:
                _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                       self.blueprint, [self.chapter])
        self.assertEqual(error.exception.code, "model_authorization_required")
        model.assert_not_called()
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_program_block_preserves_true_diagnostic_review_without_claiming_a_model_review(self, model):
        self.input_revision = append_revision(self.task, "input", {**self.input_revision.payload,
            "issues": ["原始资料存在尚未解决的行级问题"]})
        self.blueprint = append_revision(self.task, "blueprint", {**self.blueprint.payload,
            "missing": ["预算待确认"]}, input_hash=self.input_revision.sha256)
        self.task.input_version, self.task.blueprint_version = self.input_revision.version, self.blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner, decision="approve",
            sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))
        self.chapter = append_revision(self.task, "chapter", self.chapter.payload,
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        with self.assertRaises(ExecutionError) as error:
            _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                   self.blueprint, [self.chapter])
        self.assertEqual(error.exception.code, "content_review_required")
        self.assertIn("unresolved_input_items", {issue["code"] for issue in error.exception.quality_issues})
        model.assert_not_called()
        review = self.task.revisions.get(kind="review")
        self.assertFalse(review.payload["passed"])
        self.assertEqual(review.payload["model_review"], {"status": "not_run"})
        self.assertEqual(review.payload["draft_pending"], ["预算待确认"])
        self.assertEqual(review.payload["human_review"], "required")
        self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        self.assertFalse(self.task.artifacts.exists())
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 0)

    @patch("portal.product_worker.generate_for_use")
    def test_body_revision_change_invalidates_all_batches(self, model):
        model.side_effect = self.passed_reply
        self.review()
        self.chapter = append_revision(self.task, "chapter", {**self.chapter.payload,
            "paragraphs": [*self.chapter.payload["paragraphs"], "实施条件尚待确认。"]},
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        model.reset_mock()
        result = self.review()
        self.assertEqual(model.call_count, result["coverage"]["batch_count"])
        self.assertEqual(self.cache()["binding"]["chapter_revision_ids"], {"chapter-1": str(self.chapter.pk)})

    @patch("portal.product_worker.generate_for_use")
    def test_mutated_saved_revision_with_stale_hash_cannot_reuse_or_promote_a_review(self, model):
        model.side_effect = self.passed_reply
        review = _ensure_content_review(self.task, self.claim[1], self.claim[2], self.input_revision,
                                       self.blueprint, [self.chapter])
        state = deepcopy(self.cache())
        changed = {**self.chapter.payload, "paragraphs": [*self.chapter.payload["paragraphs"], "后补正文待确认。"]}
        type(self.chapter).objects.filter(pk=self.chapter.pk).update(payload=changed)
        self.chapter.refresh_from_db()
        self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, [self.chapter]))
        model.reset_mock()
        with self.assertRaises(ExecutionError) as error:
            self.review()
        self.assertEqual(error.exception.code, "source_snapshot_changed")
        model.assert_not_called()
        self.assertEqual(self.cache(), state)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_input_and_blueprint_revisions_invalidate_all_batches(self, model):
        model.side_effect = self.passed_reply
        self.review()
        self.input_revision = append_revision(self.task, "input", {**self.input_revision.payload, "background": "项目资料已更新"})
        self.blueprint = append_revision(self.task, "blueprint", {**self.blueprint.payload, "purpose": "更新资料后复核"},
                                         input_hash=self.input_revision.sha256)
        self.task.input_version, self.task.blueprint_version = self.input_revision.version, self.blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner, decision="approve",
            sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))
        self.chapter = append_revision(self.task, "chapter", self.chapter.payload,
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        model.reset_mock()
        result = self.review()
        self.assertEqual(model.call_count, result["coverage"]["batch_count"])
        self.assertEqual(self.cache()["binding"]["input_sha256"], self.input_revision.sha256)

    @patch("portal.product_worker.generate_for_use")
    def test_policy_rules_and_plan_changes_invalidate_all_batches(self, model):
        from portal.product_worker import _review_batch_payloads
        model.side_effect = self.passed_reply
        self.review()
        def changed_plan(*args):
            plan = _review_batch_payloads(*args)
            for batch in plan:
                batch["review_contract"]["context_scope"] = "changed bounded review contract"
            return plan
        cases = [patch("portal.product_content_quality.content_quality_policy_hash", return_value="b" * 64),
                 patch("portal.product_worker.rules_hash", return_value="c" * 64),
                 patch("portal.product_worker._review_batch_payloads", side_effect=changed_plan)]
        for change in cases:
            with change:
                model.reset_mock()
                result = self.review()
                self.assertEqual(model.call_count, result["coverage"]["batch_count"])

    @patch("portal.product_worker.generate_for_use")
    def test_dynamic_route_configuration_changes_invalidate_cached_calls_without_reading_credentials(self, model):
        model.side_effect = self.passed_reply
        self.review()
        provider = Provider.objects.create(code="resume-provider", name="隔离提供方", base_url="https://example.test/v1",
                                           api_key_env="PORTAL_MODEL_KEY_ISOLATED_REVIEW_FIXTURE", enabled=True)
        gateway = GatewayModel.objects.create(name="隔离模型", provider=provider, model_name="mock-review", enabled=True)
        route = ModelRoute.objects.create(code="product_review", name="隔离复核", model=gateway,
                                          module=Module.objects.get(code="product"), enabled=True)
        model.reset_mock()
        result = self.review()
        self.assertEqual(model.call_count, result["coverage"]["batch_count"])
        old_signature = self.cache()["binding"]["route_sha256"]
        GatewayModel.objects.filter(pk=gateway.pk).update(max_output_tokens=2048)
        model.reset_mock()
        result = self.review()
        self.assertEqual(model.call_count, result["coverage"]["batch_count"])
        self.assertNotEqual(old_signature, self.cache()["binding"]["route_sha256"])
        self.assertEqual(route.code, "product_review")

    @patch("portal.product_worker.generate_for_use")
    def test_tampered_results_call_binding_and_fragment_are_ignored_and_rerun(self, model):
        self.interrupted(model)
        original = deepcopy(self.cache())
        def result_tamper(batch):
            batch.update(passed=True, reviewer_passed=True, issues=[], response_sha256=digest({"passed": True, "issues": []}))
        def call_tamper(batch):
            batch["model_call_input_sha256"] = "f" * 64
        def fragment_tamper(batch):
            batch["fragments"][0]["end"] += 1
        def other_batch_call_tamper(batch):
            other = original["batches"][1]
            for field in ("passed", "reviewer_passed", "issues", "model_call_input_sha256",
                          "model_call_attempt_id", "model_call", "response_sha256"):
                batch[field] = deepcopy(other[field])
        for tamper in (result_tamper, call_tamper, fragment_tamper, other_batch_call_tamper):
            with self.subTest(tamper=tamper.__name__):
                state = deepcopy(original)
                tamper(state["batches"][0])
                self.task.refresh_from_db()
                self.task.checkpoint["content_review_batches"]["technical-solution"] = state
                self.task.save(update_fields=["checkpoint"])
                model.reset_mock()
                model.side_effect = self.passed_reply
                result = self.review()
                requested = [json.loads(call.args[2][1]["content"])["review_contract"]["batch_index"] for call in model.call_args_list]
                self.assertEqual(requested, [1, *range(4, original["total_count"] + 1)])
                self.assertEqual(model.call_count, original["total_count"] - 2)
                self.assertTrue(result["coverage"]["complete"])

    @patch("portal.product_worker.generate_for_use")
    def test_resuming_partial_cache_preserves_total_call_budget(self, model):
        self.interrupted(model)
        self.restart()
        model.reset_mock()
        model.side_effect = self.passed_reply
        with override_settings(PRODUCT_MAX_MODEL_CALLS=6):
            with self.assertRaises(ExecutionError) as error:
                self.review()
        self.assertEqual(error.exception.code, "model_call_limit")
        self.assertEqual(model.call_count, 1)
        self.assertFalse(self.cache()["complete"])
        self.assertEqual(self.cache()["completed_count"], 4)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_revoked_permission_cannot_resume_cached_results(self, model):
        model.side_effect = self.passed_reply
        self.review()
        original = deepcopy(self.cache())
        self.owner.roles.clear()
        model.reset_mock()
        with self.assertRaises(ExecutionError) as error:
            self.review()
        self.assertEqual(error.exception.code, "permission_changed")
        model.assert_not_called()
        self.assertEqual(self.cache(), original)

    @patch("portal.product_worker.generate_for_use")
    def test_cancellation_between_response_and_batch_commit_cannot_promote_cache(self, model):
        from portal.product_worker import _review_checkpoint
        original = _review_checkpoint
        def cancel_before_commit(task_id, fence, *args, **kwargs):
            record = kwargs.get("record") or (args[3] if len(args) > 3 else None)
            if record:
                self.task.refresh_from_db()
                self.task.fence += 1
                self.task.state = "CANCELLED"
                self.task.lease_until = None
                self.task.save(update_fields=["fence", "state", "lease_until"])
            return original(task_id, fence, *args, **kwargs)
        model.side_effect = self.passed_reply
        with patch("portal.product_worker._review_checkpoint", side_effect=cancel_before_commit):
            with self.assertRaises(ExecutionError) as error:
                self.review()
        self.assertEqual(error.exception.code, "lease_lost")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(self.cache()["completed_count"], 0)
        self.assertFalse(self.task.revisions.filter(kind="review").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_expired_lease_prevents_zero_call_cache_reuse(self, model):
        model.side_effect = self.passed_reply
        self.review()
        state = deepcopy(self.cache())
        self.task.lease_until = timezone.now() - timedelta(seconds=1)
        self.task.save(update_fields=["lease_until"])
        model.reset_mock()
        with self.assertRaises(ExecutionError) as error:
            self.review()
        self.assertEqual(error.exception.code, "lease_lost")
        model.assert_not_called()
        self.assertEqual(self.cache(), state)
