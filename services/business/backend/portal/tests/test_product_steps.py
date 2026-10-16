from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone

from portal.model_gateway import GatewayError
from portal.product_models import DocumentAttempt, DocumentStep, DocumentTask
from portal.product_steps import StepRetryPending, run_step
from portal.product_worker import ExecutionError, _analysis_progress, _execute_claim_action, _finish, claim_task
from .base import PortalTestCase
from . import test_product_review_output_retry as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_STEP_MAX_ATTEMPTS=3, PRODUCT_STEP_RETRY_BASE_SECONDS=1,
                   PRODUCT_STEP_RETRY_MAX_SECONDS=10)
class ProductStepRecoveryTests(PortalTestCase):
    setUp = fixture.ProductReviewOutputRetryTests.setUp
    claimed = fixture.ProductReviewOutputRetryTests.claimed

    def test_committed_batch_reused_after_process_recovery_and_input_change_invalidates(self):
        task_id, fence, attempt_id = self.claimed()
        operation = Mock(return_value={"paragraphs": ["已核验的短正文"]})
        first = run_step(task_id, fence, "writing:technical", {"revision": "v1"}, operation)
        first["paragraphs"].append("caller mutation")
        DocumentTask.objects.filter(pk=task_id).update(lease_until=timezone.now() - timedelta(seconds=1))
        recovered_id, recovered_fence, _ = claim_task()
        cached = run_step(recovered_id, recovered_fence, "writing:technical", {"revision": "v1"}, operation)
        self.assertEqual(cached, {"paragraphs": ["已核验的短正文"]})
        self.assertEqual(operation.call_count, 1)
        run_step(recovered_id, recovered_fence, "writing:technical", {"revision": "v2"}, operation)
        self.assertEqual(operation.call_count, 2)

    def test_transient_recovery_is_scheduled_without_resetting_manual_or_model_budgets(self):
        task_id, fence, attempt_id = self.claimed()
        DocumentAttempt.objects.filter(pk=attempt_id).update(model_calls=4)
        operation = Mock(side_effect=ExecutionError("timeout"))
        with self.assertRaises(StepRetryPending) as caught:
            run_step(task_id, fence, "diagram:one", {"input": "same"}, operation)
        _finish(task_id, fence, attempt_id, "QUEUED", "RENDER", caught.exception.code, recovery=caught.exception)
        self.assertIsNone(claim_task())
        self.task.refresh_from_db()
        count = self.task.attempt_count
        DocumentTask.objects.filter(pk=task_id).update(retry_after=timezone.now() - timedelta(seconds=1))
        DocumentStep.objects.filter(task_id=task_id).update(retry_after=timezone.now() - timedelta(seconds=1))
        recovered_id, recovered_fence, recovered_attempt = claim_task()
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempt_count, count)
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 4)
        self.assertEqual(self.task.attempts.count(), 2)
        succeeded = Mock(return_value={"image": "verified"})
        self.assertEqual(run_step(recovered_id, recovered_fence, "diagram:one", {"input": "same"}, succeeded),
                         {"image": "verified"})
        self.assertEqual(DocumentStep.objects.get(task_id=task_id).attempts, 2)

    def test_retry_budget_is_bounded_and_semantic_failures_do_not_autoretry(self):
        task_id, fence, _ = self.claimed()
        operation = Mock(side_effect=ExecutionError("timeout"))
        for index in range(3):
            DocumentStep.objects.filter(task_id=task_id).update(retry_after=timezone.now() - timedelta(seconds=1))
            expected = StepRetryPending if index < 2 else ExecutionError
            with self.assertRaises(expected):
                run_step(task_id, fence, "model:one", {"input": "same"}, operation)
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(DocumentStep.objects.get(task_id=task_id).status, "failed")
        with self.assertRaises(ExecutionError):
            run_step(task_id, fence, "model:two", {"input": "same"},
                     Mock(side_effect=ExecutionError("invalid_model_output")))
        self.assertEqual(DocumentStep.objects.get(task_id=task_id, key="model:two").status, "failed")

    def test_invalid_json_recovers_automatically_with_finite_shared_call_budget(self):
        from portal.product_worker import _model
        with patch("portal.product_worker.generate_for_use", return_value={"content": '{"passed":'}) as model:
            for index in range(3):
                task_id, fence, attempt_id = self.claimed()
                expected = StepRetryPending if index < 2 else ExecutionError
                with self.assertRaises(expected) as caught:
                    run_step(task_id, fence, "writing-editor:1", {"input": "same"},
                        lambda: _model(task_id, fence, attempt_id, "product_review",
                            {"action": "independent_review", "schema": {"passed": "boolean", "issues": ["string"]}}))
                if index < 2:
                    _finish(task_id, fence, attempt_id, "QUEUED", "WRITING", caught.exception.code,
                            recovery=caught.exception)
                    self.task.refresh_from_db()
                    self.assertTrue(self.task.checkpoint["automatic_recovery"])
                    self.assertIsNone(claim_task())
                    past = timezone.now() - timedelta(seconds=1)
                    DocumentTask.objects.filter(pk=task_id).update(retry_after=past)
                    DocumentStep.objects.filter(task_id=task_id).update(retry_after=past)
            self.assertEqual(caught.exception.code, "invalid_model_output")
            self.assertEqual(model.call_count, 6)
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempt_count, 1)
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 6)
        step = DocumentStep.objects.get(task=self.task)
        self.assertEqual((step.status, step.retry_count), ("failed", 3))
        with self.assertRaises(ExecutionError) as caught:
            run_step(task_id, fence, "writing-editor:1", {"input": "same"}, Mock())
        self.assertEqual(caught.exception.code, "invalid_model_output")

    def test_only_parser_classified_failures_get_format_recovery(self):
        from portal.product_worker import _parse_model_output
        task_id, fence, _ = self.claimed()
        for index, text in enumerate(('{"a":', '{"a":1,"a":2}', '{"a":NaN}', '[]')):
            with self.assertRaises(StepRetryPending):
                run_step(task_id, fence, f"syntax:{index}", {}, lambda: _parse_model_output(text))
        for code in ("invalid_model_output", "content_review_required", "permission_changed", "model_call_limit"):
            with self.assertRaises(ExecutionError):
                run_step(task_id, fence, f"semantic:{code}", {}, Mock(side_effect=ExecutionError(code)))
            self.assertEqual(DocumentStep.objects.get(task_id=task_id, key=f"semantic:{code}").status, "failed")

    def test_upstream_error_retries_with_backoff_then_preserves_error_and_saved_body(self):
        self.task.pending_action = "generate_outputs"
        self.task.checkpoint = {"output_families": ["technical-solution"]}
        self.task.save()
        error = GatewayError("upstream_error")
        error.diagnostic = {"upstream_status": 503, "upstream_code": "service_unavailable"}
        operation = Mock(side_effect=error)
        def generate(task_id, fence, attempt_id, *args):
            _analysis_progress(task_id, fence, "writing_technical", "running", detail="正在编写第1章")
            return run_step(task_id, fence, "writing:technical", {}, operation)
        with patch("portal.product_worker._generate_family", side_effect=generate), patch(
                "portal.product_documents.preflight_document_rendering"):
            for index in range(3):
                task_id, fence, attempt_id = self.claimed()
                started = timezone.now()
                _execute_claim_action(task_id, fence, attempt_id)
                self.task.refresh_from_db()
                if index < 2:
                    self.assertEqual((self.task.state, self.task.error_code), ("QUEUED", "step_retry_pending"))
                    self.assertGreaterEqual(self.task.retry_after, started + timedelta(seconds=2 ** index))
                    DocumentTask.objects.filter(pk=task_id).update(retry_after=started)
                    DocumentStep.objects.filter(task_id=task_id).update(retry_after=started)
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "upstream_error"))
        self.assertEqual((operation.call_count, self.task.attempt_count), (3, 1))
        step = DocumentStep.objects.get(task=self.task)
        self.assertEqual((step.status, step.retry_count), ("failed", 3))
        self.assertEqual(self.task.checkpoint["last_failure"]["upstream_status"], 503)
        progress = self.task.checkpoint["analysis_progress"]["writing_technical"]
        self.assertEqual(progress["status"], "failed")
        self.assertNotIn("正在编写", progress["detail"])
        self.assertEqual(self.task.revisions.filter(kind="chapter").get().sha256, self.chapter.sha256)

    def test_permanent_upstream_errors_stop_without_retry_and_keep_original_code(self):
        for code in ("upstream_invalid_request", "upstream_auth", "invalid_request", "forbidden"):
            with self.subTest(code=code):
                self.task.state, self.task.pending_action = "QUEUED", "write"
                self.task.save()
                task_id, fence, attempt_id = self.claimed()
                operation = Mock(side_effect=GatewayError(code))
                with patch("portal.product_worker._generate_family", side_effect=lambda *args: run_step(
                        task_id, fence, code, {}, operation)):
                    _execute_claim_action(task_id, fence, attempt_id)
                self.task.refresh_from_db()
                self.assertEqual((self.task.state, self.task.error_code), ("FAILED", code))
                self.assertIsNone(self.task.retry_after)
                self.assertEqual(DocumentStep.objects.get(task=self.task, key=code).retry_count, 0)
                operation.assert_called_once()

    def test_gateway_call_keeps_only_bounded_upstream_diagnostic(self):
        from portal.product_worker import _failure_diagnostic, _model
        task_id, fence, attempt_id = self.claimed()
        error = GatewayError("upstream_error")
        error.diagnostic = {"upstream_status": 503, "upstream_code": "service_unavailable", "message": "private body",
                            "upstream_stage": "response_headers", "upstream_exception": "RemoteDisconnected"}
        with patch("portal.product_worker.generate_for_use", side_effect=error), self.assertRaises(GatewayError):
            _model(task_id, fence, attempt_id, "product_review", {"action": "independent_review"})
        self.task.refresh_from_db()
        call = self.task.checkpoint["calls"][-1]
        self.assertEqual((call["upstream_status"], call["upstream_code"]), (503, "service_unavailable"))
        self.assertEqual((call["upstream_stage"], call["upstream_exception"]), ("response_headers", "RemoteDisconnected"))
        self.assertNotIn("private body", str(call))
        error.diagnostic = {"upstream_status": True, "upstream_code": "sk-secret",
                            "upstream_stage": "private stage", "upstream_exception": "private exception"}
        self.assertFalse({"upstream_status", "upstream_code", "upstream_stage", "upstream_exception"}
                         & _failure_diagnostic(error).keys())

    def test_revocation_and_stale_worker_cannot_read_or_commit_cached_results(self):
        task_id, fence, _ = self.claimed()
        operation = Mock(return_value={"text": "private"})
        run_step(task_id, fence, "writing:one", {}, operation)
        DocumentTask.objects.filter(pk=task_id).update(fence=fence + 1)
        with self.assertRaises(ExecutionError):
            run_step(task_id, fence, "writing:one", {}, operation)
        self.assertEqual(operation.call_count, 1)
        DocumentTask.objects.filter(pk=task_id).update(fence=fence)
        self.owner.roles.clear()
        with self.assertRaises(ExecutionError):
            run_step(task_id, fence, "writing:one", {}, operation)

    def test_corrupt_cache_is_regenerated_instead_of_reused(self):
        task_id, fence, _ = self.claimed()
        operation = Mock(return_value={"text": "verified"})
        run_step(task_id, fence, "writing:one", {}, operation)
        DocumentStep.objects.filter(task_id=task_id).update(output={"text": "corrupted"})
        self.assertEqual(run_step(task_id, fence, "writing:one", {}, operation), {"text": "verified"})
        self.assertEqual(operation.call_count, 2)

    def test_waiting_child_does_not_spend_parent_retry_budget(self):
        task_id, fence, _ = self.claimed()
        failing = Mock(side_effect=ExecutionError("timeout"))
        def parent():
            return run_step(task_id, fence, "diagram:child", {}, failing)
        for index in range(3):
            DocumentStep.objects.filter(task_id=task_id).update(retry_after=timezone.now() - timedelta(seconds=1))
            with self.assertRaises(StepRetryPending if index < 2 else ExecutionError):
                run_step(task_id, fence, "render:parent", {}, parent)
        self.assertEqual(DocumentStep.objects.get(task_id=task_id, key="diagram:child").retry_count, 3)
        self.assertEqual(DocumentStep.objects.get(task_id=task_id, key="render:parent").retry_count, 0)

    def test_lease_revoked_during_operation_cannot_commit_result(self):
        task_id, fence, _ = self.claimed()
        def stale_operation():
            DocumentTask.objects.filter(pk=task_id).update(fence=fence + 1)
            return {"text": "stale output"}
        with self.assertRaises(ExecutionError):
            run_step(task_id, fence, "writing:one", {}, stale_operation)
        self.assertEqual(DocumentStep.objects.get(task_id=task_id).output, {})

    def test_truncated_batch_shrinks_request_without_changing_report_requirement(self):
        from portal.product_worker import _writing_model
        task_id, fence, attempt_id = self.claimed()
        payload = {"family": "technical-solution", "chapter": {"id": "one"},
                   "length_target": {"this_response_characters": 2400, "minimum_characters": 50000}}
        requests = []
        def model(*args, **kwargs):
            requests.append(args[4])
            if len(requests) == 1:
                raise ExecutionError("output_truncated")
            return {"paragraphs": ["已保存"]}
        with patch("portal.product_worker._model", side_effect=model):
            with self.assertRaises(StepRetryPending):
                _writing_model(task_id, fence, attempt_id, "writing", payload, output_validator=lambda result: True)
            DocumentStep.objects.filter(task_id=task_id).update(retry_after=timezone.now() - timedelta(seconds=1))
            _writing_model(task_id, fence, attempt_id, "writing", payload, output_validator=lambda result: True)
        self.assertEqual(requests[0]["length_target"]["this_response_characters"], 2400)
        self.assertEqual(requests[1]["length_target"]["this_response_characters"], 1200)
        self.assertEqual(requests[1]["length_target"]["minimum_characters"], 50000)

    def test_document_office_failure_is_scheduled_for_automatic_recovery(self):
        from portal.product_documents import DocumentError
        task_id, fence, _ = self.claimed()
        error = DocumentError("document_render_failed", diagnostic={
            "stage": "office_render", "reason": "renderer_failed", "returncode": 2})
        with self.assertRaises(StepRetryPending):
            run_step(task_id, fence, "render:technical", {}, Mock(side_effect=error))
        self.assertEqual(DocumentStep.objects.get(task_id=task_id).status, "retry_wait")
