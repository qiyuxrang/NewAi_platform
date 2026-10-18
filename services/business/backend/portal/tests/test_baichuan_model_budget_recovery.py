"""Synthetic recovery boundaries; the gateway is always replaced, never called."""
from datetime import timedelta
import json
import tempfile
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanJob, BaichuanMessage
from portal.baichuan_assistant_worker import _conditions, process_query, run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_jobs import cancel_job, claim_job, consume_budget, enqueue_job, retry_job, save_job
from portal.baichuan_matching import save_match_snapshot
from portal.baichuan_service import BaichuanError
from portal.model_gateway import GatewayError
from .base import PortalTestCase


def tree(city="西安市"):
    return compile_conditions({"schema_version": 1, "revision": 1,
        "must": {"field": "company.city", "op": "eq", "value": city}}, today=timezone.localdate())


class ModelBudgetRecoveryTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("budget-recovery-owner", "product")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="budget-recovery",
            BAICHUAN_STORAGE_ROOT=self.temp.name, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            BAICHUAN_RESEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_ENABLED=True)
        config.enable()
        self.addCleanup(config.disable)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="budget-recovery", condition_revision=1)

    def enqueue(self):
        message = BaichuanMessage.objects.create(conversation=self.conversation, role="user",
            content="合成地区条件", condition_revision=1)
        job, _ = enqueue_job(self.owner, kind="query", conversation=self.conversation, message=message,
            payload={"text": message.content, "attachment_ids": [], "condition_revision": 1,
                "parent_revision": 0, "export": None}, idempotency_key=str(message.pk),
            budget={"max_model_calls": 1, "max_attempts": 3})
        return job

    def claimed(self):
        return claim_job("worker-a", job_id=self.enqueue().pk, lease_seconds=45)

    def expire(self, job):
        BaichuanJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))

    def assert_code(self, code, function, *args):
        with self.assertRaises(BaichuanError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_durable_conditions_override_stale_empty_checkpoint_without_model(self):
        job = self.claimed()
        original_hash = job.request_hash
        save_job(job.pk, "worker-a", job.fence, checkpoint={"conditions": tree(), "preserve": "durable"})
        self.assertEqual(job.checkpoint, {})  # The exact real-verifier failure shape.
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            process_query(job, "worker-a")
        model.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.counts.get("_budget_model_calls", 0), 0)
        self.assertEqual(job.checkpoint["preserve"], "durable")
        self.assertEqual(job.request_hash, original_hash)
        self.assertEqual(job.snapshots.get().condition_tree, tree())

    def test_memory_only_checkpoint_and_payload_cannot_replace_persisted_request(self):
        job = self.claimed()
        save_job(job.pk, "worker-a", job.fence, checkpoint={"conditions": tree()})
        job.checkpoint = {"conditions": tree("广州市")}
        job.payload = {**job.payload, "export": {"limit": 1}, "text": "cached replacement"}
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            process_query(job, "worker-a")
        model.assert_not_called()
        self.assertEqual(job.snapshots.get().condition_tree, tree())
        self.assertFalse(BaichuanJob.objects.filter(kind="export").exists())

    def test_direct_condition_entry_also_reads_durable_checkpoint(self):
        job = self.claimed()
        save_job(job.pk, "worker-a", job.fence, checkpoint={"conditions": tree()})
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            result = _conditions(job, "worker-a", [], set(), [])
        model.assert_not_called()
        self.assertEqual(result, tree())

    def test_crash_after_condition_commit_reclaims_without_second_call(self):
        job = self.claimed()
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(tree())}) as model:
            committed = _conditions(job, "worker-a", [], set(), [])
            self.assertEqual(committed["must"], tree()["must"])
            self.assertEqual(committed["source_refs"], [f"message:{job.message_id}"])
            self.assertEqual(_conditions(job, "worker-a", [], set(), []), committed)
            self.expire(job)
            self.assertTrue(run_one("worker-b", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts, job.counts["_budget_model_calls"]), ("completed", 2, 1))
        self.assertEqual(job.snapshots.count(), 1)
        self.assertEqual(self.conversation.messages.filter(role="assistant").count(), 1)

    def test_crash_after_budget_reservation_never_reissues_uncertain_call(self):
        job = self.claimed()
        consume_budget(job.pk, "worker-a", job.fence, model_calls=1)
        self.expire(job)
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            self.assertTrue(run_one("worker-b", job.pk))
        model.assert_not_called()
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("failed", "budget_exhausted"))
        self.assertEqual(job.counts["_budget_model_calls"], 1)
        self.assertEqual(job.snapshots.count(), 0)
        self.assertIsNone(job.lease_expires_at)

    def test_crash_after_snapshot_commit_keeps_same_snapshot_and_one_call(self):
        job = self.claimed()
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(tree())}) as model:
            conditions = _conditions(job, "worker-a", [], set(), [])
            snapshot = save_match_snapshot(self.owner, job.pk, "worker-a", job.fence, conditions)
            save_job(job.pk, "worker-a", job.fence, result_ref={"snapshot_id": str(snapshot.pk)})
            self.expire(job)
            self.assertTrue(run_one("worker-b", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual(job.result_ref["snapshot_id"], str(snapshot.pk))
        self.assertEqual(job.snapshots.count(), 1)
        self.assertEqual(job.status, "completed")

    def test_cancelled_stale_or_revoked_entry_cannot_parse_or_call_model(self):
        for mode in ("cancel", "stale", "revoke"):
            with self.subTest(mode=mode):
                job = self.claimed()
                if mode == "cancel":cancel_job(self.owner, job.pk)
                elif mode == "stale":
                    self.expire(job)
                    self.assertIsNotNone(claim_job("worker-b", job_id=job.pk))
                config = override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[] if mode == "revoke" else [self.owner.pk])
                with config, patch("portal.baichuan_assistant_worker._parse") as parser, patch("portal.baichuan_assistant_worker.generate_for_use") as model:
                    self.assert_code("permission_revoked" if mode == "revoke" else "stale_lease", process_query, job, "worker-a")
                parser.assert_not_called()
                model.assert_not_called()

    def test_cancel_between_parse_and_conditions_prevents_gateway(self):
        job = self.claimed()
        def parsed(*args):
            cancel_job(self.owner, job.pk)
            return [], set(), []
        with patch("portal.baichuan_assistant_worker._parse", side_effect=parsed), patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            self.assert_code("stale_lease", process_query, job, "worker-a")
        model.assert_not_called()

    def test_owner_or_deployment_mismatch_prevents_parsing_and_model_access(self):
        for field, value in (("scope", "another-deployment"), ("owner_id", None)):
            with self.subTest(field=field):
                job = self.claimed()
                if field == "owner_id":
                    value = self.create_user("foreign-conversation-owner", "product").pk
                BaichuanConversation.objects.filter(pk=self.conversation.pk).update(**{field: value})
                with patch("portal.baichuan_assistant_worker._parse") as parser, patch("portal.baichuan_assistant_worker.generate_for_use") as model:
                    self.assert_code("not_found", process_query, job, "worker-a")
                parser.assert_not_called();model.assert_not_called()
                BaichuanConversation.objects.filter(pk=self.conversation.pk).update(scope="budget-recovery", owner_id=self.owner.pk)

    def test_gateway_timeout_consumes_one_reservation_without_automatic_retry(self):
        job = self.enqueue()
        with patch("portal.baichuan_assistant_worker.generate_for_use", side_effect=GatewayError("timeout")) as model:
            self.assertTrue(run_one("worker-a", job.pk))
            self.assertFalse(run_one("worker-b", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code, job.counts["_budget_model_calls"]), ("failed", "timeout", 1))
        self.assertIsNone(job.lease_expires_at)
        self.assertIn("超时", self.conversation.messages.get(role="assistant").content)

    def test_cancel_during_inflight_model_preserves_charge_without_publication(self):
        job = self.enqueue()
        def model_response(*args, **kwargs):
            cancel_job(self.owner, job.pk)
            return {"content": json.dumps(tree())}
        with patch("portal.baichuan_assistant_worker.generate_for_use", side_effect=model_response) as model:
            self.assertTrue(run_one("worker-a", job.pk))
            self.assertFalse(run_one("worker-b", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.counts["_budget_model_calls"]), ("cancelled", 1))
        self.assertEqual(job.checkpoint, {})
        self.assertFalse(job.snapshots.exists())
        self.assertFalse(self.conversation.messages.filter(role="assistant").exists())

    def test_revocation_during_inflight_model_stops_condition_publication(self):
        job = self.enqueue()
        def model_response(*args, **kwargs):
            self.owner.is_active = False
            self.owner.save(update_fields=["is_active"])
            return {"content": json.dumps(tree())}
        with patch("portal.baichuan_assistant_worker.generate_for_use", side_effect=model_response) as model:
            self.assertTrue(run_one("worker-a", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("failed", "permission_revoked"))
        self.assertEqual(job.counts["_budget_model_calls"], 1)
        self.assertEqual(job.checkpoint, {})
        self.assertFalse(job.snapshots.exists())
        self.assertFalse(self.conversation.messages.filter(role="assistant").exists())

    def test_invalid_model_shape_is_charged_once_and_not_automatically_retried(self):
        job = self.enqueue()
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": '{"must": []}'}) as model:
            self.assertTrue(run_one("worker-a", job.pk))
            self.assertFalse(run_one("worker-b", job.pk))
        self.assertEqual(model.call_count, 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("failed", "invalid_model_conditions"))
        self.assertEqual(job.counts["_budget_model_calls"], 1)
        self.assertFalse(job.snapshots.exists())

    def test_explicit_retry_preserves_conditions_and_resets_only_new_attempt_budget(self):
        old = self.claimed()
        consume_budget(old.pk, "worker-a", old.fence, model_calls=1)
        save_job(old.pk, "worker-a", old.fence, status="failed", checkpoint={"conditions": tree()}, error_code="processing_failed")
        new, created = retry_job(self.owner, old.pk, idempotency_key="explicit-retry")
        self.assertTrue(created)
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            self.assertTrue(run_one("worker-b", new.pk))
        model.assert_not_called()
        old.refresh_from_db();new.refresh_from_db()
        self.assertEqual((old.status, old.counts["_budget_model_calls"]), ("failed", 1))
        self.assertEqual((new.status, new.counts.get("_budget_model_calls", 0)), ("completed", 0))
