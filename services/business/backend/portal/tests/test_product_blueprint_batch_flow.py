"""Synthetic worker regressions: bounded blueprint retries never approve a partial plan."""

import json
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.model_gateway import GatewayError
from portal.product_models import DocumentApproval, DocumentAttempt, DocumentStep
from portal.product_worker import run_once

from .base import PortalTestCase
from . import test_product_worker as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview",
                   PRODUCT_MAX_MODEL_CALLS=256, PRODUCT_STEP_MAX_ATTEMPTS=3,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=3)
class BlueprintBatchFlowTests(PortalTestCase):
    model_blueprint = fixture.ProductWorkerTests.model_blueprint

    def setUp(self):
        fixture.ProductWorkerTests.setUp(self)
        self.task.pending_action, self.task.stage = "blueprint", "BLUEPRINT"
        self.task.save(update_fields=["pending_action", "stage"])
        self.candidate = self.model_blueprint()

    def retry_due(self):
        past = timezone.now() - timedelta(seconds=1)
        self.task.retry_after = past
        self.task.save(update_fields=["retry_after"])
        DocumentStep.objects.filter(task=self.task).update(retry_after=past)

    def assert_no_new_blueprint_or_approval(self):
        self.assertEqual(self.task.blueprint_version, self.blueprint.version)
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 1)
        self.assertEqual(DocumentApproval.objects.filter(task=self.task).count(), 1)

    @patch("portal.product_worker.generate_for_use")
    def test_second_scope_batch_transport_retry_reuses_completed_steps_and_budget(self, model):
        normal_reply = fixture.blueprint_model_responses(self.candidate, prompt_tokens=2, completion_tokens=3)
        requests = []
        failed_ids = None

        def reply(*args, **kwargs):
            nonlocal failed_ids
            request = json.loads(args[2][1]["content"])
            requests.append(request)
            if request["action"] == "blueprint_scope" and len(requests) == 3:
                failed_ids = [section["id"] for section in request["guide_batch"]["sections"]]
                raise GatewayError("output_truncated")
            return normal_reply(*args, **kwargs)

        model.side_effect = reply
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("QUEUED", "step_retry_pending"))
        self.assertEqual(self.task.checkpoint["last_failure"]["cause_code"], "output_truncated")
        self.assert_no_new_blueprint_or_approval()
        base = self.task.steps.get(key="blueprint:base")
        first = self.task.steps.get(key="blueprint:scope:1")
        second = self.task.steps.get(key="blueprint:scope:2")
        self.assertEqual((base.status, first.status, second.status), ("completed", "completed", "retry_wait"))
        self.assertEqual((base.attempts, first.attempts, second.attempts), (1, 1, 1))
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).model_calls, 3)
        started_at = self.task.checkpoint["analysis_progress"]["blueprint"]["started_at"]
        completed_hashes = (base.output_hash, first.output_hash)
        self.retry_due()

        run_once()

        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code), ("WAITING_REVIEW", "BLUEPRINT", ""))
        saved = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        self.assertEqual(saved.payload, self.candidate)
        self.assertEqual(saved.input_hash, self.input_revision.sha256)
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 2)
        self.assertFalse(saved.approvals.exists())
        self.assertEqual(DocumentApproval.objects.filter(task=self.task).count(), 1)
        base.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((base.attempts, first.attempts, second.attempts), (1, 1, 2))
        self.assertEqual((base.output_hash, first.output_hash), completed_hashes)
        self.assertEqual([request["action"] for request in requests].count("blueprint"), 1)
        scope_ids = [[section["id"] for section in request["guide_batch"]["sections"]]
                     for request in requests if request["action"] == "blueprint_scope"]
        self.assertEqual(scope_ids.count(scope_ids[0]), 1)
        self.assertEqual(scope_ids.count(failed_ids), 2)
        self.assertEqual(model.call_count, 5)
        self.assertEqual(list(self.task.attempts.order_by("fence").values_list("model_calls", flat=True)), [3, 2])
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), model.call_count)
        self.assertEqual(len(self.task.checkpoint["calls"]), model.call_count)
        progress = self.task.checkpoint["analysis_progress"]["blueprint"]
        self.assertEqual((progress["completed_count"], progress["total_count"]), (3, 3))
        self.assertEqual((progress["completed_sections"], progress["total_sections"]), (124, 124))
        self.assertTrue(progress["started_at"])
        self.assertEqual(progress["started_at"], started_at)

    @patch("portal.product_worker.generate_for_use")
    def test_technical_chapter_mapping_gets_one_correction_then_fails_without_final_plan(self, model):
        normal_reply = fixture.blueprint_model_responses(self.candidate)
        requests = []
        technical_id = next(chapter["id"] for chapter in self.candidate["chapters"]
                            if chapter["family"] == "technical-solution")

        def malicious_reply(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            requests.append(request)
            reply = normal_reply(*args, **kwargs)
            if request["action"] == "blueprint_scope":
                response = json.loads(reply["content"])
                response["decisions"][0][2] = [technical_id]
                reply["content"] = json.dumps(response, ensure_ascii=False)
            return reply

        model.side_effect = malicious_reply
        run_once()

        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("FAILED", "invalid_model_output"))
        self.assert_no_new_blueprint_or_approval()
        self.assertEqual([request["action"] for request in requests], ["blueprint", "blueprint_scope", "blueprint_scope"])
        self.assertEqual(requests[1]["guide_batch"], requests[2]["guide_batch"])
        self.assertNotIn("json_format_correction", requests[1])
        self.assertIn("json_format_correction", requests[2])
        self.assertEqual((self.task.steps.get(key="blueprint:base").status,
                          self.task.steps.get(key="blueprint:scope:1").status), ("completed", "failed"))
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).model_calls, 3)

    @patch("portal.product_worker.generate_for_use")
    def test_final_merge_failure_invalidates_scope_steps_and_manual_retry_reuses_base(self, model):
        normal_reply = fixture.blueprint_model_responses(self.candidate)
        requests = []
        exclude_all = True

        def reply(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            requests.append(request)
            response = normal_reply(*args, **kwargs)
            if exclude_all and request["action"] == "blueprint_scope":
                payload = json.loads(response["content"])
                payload["reasons"] = [{"id": "R1", "text": "合成回执明确排除此项，供全局校验拒绝。"}]
                for entry in payload["decisions"]:
                    entry[1:] = ["N", [], "R1"]
                response["content"] = json.dumps(payload, ensure_ascii=False)
            return response

        model.side_effect = reply
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("FAILED", "invalid_blueprint"))
        self.assert_no_new_blueprint_or_approval()
        base = self.task.steps.get(key="blueprint:base")
        self.assertEqual((base.status, base.attempts), ("completed", 1))
        base_hash = base.output_hash
        scopes = self.task.steps.filter(key__startswith="blueprint:scope:")
        self.assertEqual(scopes.count(), 3)
        self.assertEqual(scopes.filter(status="pending", error_code="invalid_blueprint").count(), 3)
        self.assertTrue(all(step.output["sections"] and step.output_hash for step in scopes))
        self.assertEqual(model.call_count, 4)

        exclude_all = False
        self.task.state = "QUEUED"
        self.task.checkpoint = {**self.task.checkpoint, "automatic_recovery": False, "recovery_mode": False}
        self.task.save(update_fields=["state", "checkpoint"])
        run_once()

        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code), ("WAITING_REVIEW", "BLUEPRINT", ""))
        saved = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        self.assertEqual(saved.payload, self.candidate)
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 2)
        self.assertFalse(saved.approvals.exists())
        self.assertEqual(DocumentApproval.objects.filter(task=self.task).count(), 1)
        base.refresh_from_db()
        self.assertEqual((base.status, base.attempts, base.output_hash), ("completed", 1, base_hash))
        self.assertEqual([request["action"] for request in requests].count("blueprint"), 1)
        self.assertEqual(model.call_count, 7)
        self.assertEqual(list(self.task.attempts.order_by("fence").values_list("model_calls", flat=True)), [4, 3])

    @override_settings(PRODUCT_MAX_MODEL_CALLS=2)
    @patch("portal.product_worker.generate_for_use")
    def test_low_call_budget_survives_transport_retry_and_stops_before_next_dispatch(self, model):
        normal_reply = fixture.blueprint_model_responses(self.candidate)

        def reply(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            if request["action"] == "blueprint_scope":
                raise GatewayError("output_truncated")
            return normal_reply(*args, **kwargs)

        model.side_effect = reply
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("QUEUED", "step_retry_pending"))
        self.assertEqual(model.call_count, 2)
        self.assert_no_new_blueprint_or_approval()
        self.retry_due()

        run_once()

        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "model_call_limit"))
        self.assert_no_new_blueprint_or_approval()
        self.assertEqual(model.call_count, 2)
        self.assertEqual(list(self.task.attempts.order_by("fence").values_list("model_calls", flat=True)), [2, 0])
        self.assertEqual(len(self.task.checkpoint["calls"]), 2)
        self.assertEqual(self.task.steps.get(key="blueprint:base").attempts, 1)
        self.assertEqual(self.task.steps.get(key="blueprint:scope:1").status, "failed")
