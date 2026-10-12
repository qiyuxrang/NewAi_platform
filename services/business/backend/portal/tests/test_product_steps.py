from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import override_settings
from django.utils import timezone

from portal.product_models import DocumentAttempt, DocumentStep, DocumentTask
from portal.product_steps import StepRetryPending, run_step
from portal.product_worker import ExecutionError, _finish, claim_task
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
