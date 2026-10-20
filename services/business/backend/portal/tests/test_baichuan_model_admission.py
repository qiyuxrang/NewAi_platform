"""Actual private queue/admission state; synthetic DB and no provider I/O."""
from datetime import timedelta
import json
import uuid
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanJob, BaichuanMessage
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_jobs import cancel_job, claim_job, enqueue_job, save_job
from portal.baichuan_service import BaichuanError
from portal.model_gateway import GatewayError, _reserve
from portal.models import GatewayModel, ModelCallLog, ModelRoute, Module, Provider
from .base import PortalTestCase


class ModelAdmissionTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("model-wait-owner", "product")
        self.owner.refresh_from_db()
        config = override_settings(BAICHUAN_ASSISTANT_SCOPE="wait-test", BAICHUAN_ASSISTANT_LOCAL_GRAMMAR=False,
            BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=True, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)

    def enqueue(self):
        c = BaichuanConversation.objects.create(owner=self.owner, scope="wait-test", condition_revision=1)
        message = BaichuanMessage.objects.create(conversation=c, role="user", content="合成城市条件", condition_revision=1)
        return enqueue_job(self.owner, kind="query", conversation=c, message=message,
            payload={"text":message.content,"attachment_ids":[],"condition_revision":1,"parent_revision":0},
            idempotency_key=uuid.uuid4().hex)[0]

    def reply(self, user, route, messages):
        context = json.loads(messages[-1]["content"]); ref=context["text_source_ref"]
        return {"content":json.dumps({"schema_version":1,"revision":1,"source_refs":[ref],
            "must":{"field":"company.city","op":"eq","value":"西安市","source_refs":[ref]}})}

    def wait(self, job, code="rate_limited"):
        error = GatewayError(code,status=429,reservation_rejected=True,retry_after=2)
        with patch("portal.baichuan_assistant_worker.generate_for_use",side_effect=error) as model:
            self.assertTrue(run_one("worker-a",job.pk))
        self.assertEqual(model.call_count,1); job.refresh_from_db()
        self.assertEqual(job.status,"queued")
        return job

    def ready(self, job):
        cp=dict(job.checkpoint); cp["model_wait"]["not_before"]=(timezone.now()-timedelta(seconds=1)).isoformat()
        BaichuanJob.objects.filter(pk=job.pk).update(checkpoint=cp)

    def test_local_rejection_waits_durably_then_completes_once_without_charge_or_failure_attempt(self):
        job=self.wait(self.enqueue()); old_fence=job.fence-1
        self.assertEqual(job.counts["_budget_model_calls"],0)
        self.assertEqual(job.attempts,0); self.assertIsNone(job.lease_expires_at)
        self.assertFalse(job.conversation.messages.filter(role="assistant").exists())
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            self.assertFalse(run_one("worker-b",job.pk))
        model.assert_not_called()
        with self.assertRaises(BaichuanError):
            save_job(job.pk,"worker-a",old_fence,status="completed")
        self.ready(job)
        with patch("portal.baichuan_assistant_worker.generate_for_use",side_effect=self.reply) as model:
            self.assertTrue(run_one("worker-b",job.pk))
            self.assertFalse(run_one("worker-c",job.pk))
        self.assertEqual(model.call_count,1); job.refresh_from_db()
        self.assertEqual((job.status,job.counts["_budget_model_calls"]),("completed",1))
        self.assertEqual(job.snapshots.count(),1)
        self.assertEqual(job.checkpoint["model_wait"]["count"],1)
        self.assertEqual(job.conversation.messages.filter(role="assistant").count(),1)

    def test_busy_wait_does_not_starve_next_independent_query(self):
        waiting=self.wait(self.enqueue(),"busy"); ready=self.enqueue()
        claimed=claim_job("other-worker")
        self.assertEqual(claimed.pk,ready.pk)
        self.assertNotEqual(claimed.pk,waiting.pk)

    def test_cancellation_while_waiting_prevents_further_model_call(self):
        job=self.wait(self.enqueue()); cancel_job(self.owner,job.pk)
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            self.assertFalse(run_one("worker-b",job.pk))
        model.assert_not_called(); job.refresh_from_db(); self.assertEqual(job.status,"cancelled")

    def test_permission_revocation_while_waiting_stops_before_model(self):
        job=self.wait(self.enqueue()); self.owner.is_active=False; self.owner.save(update_fields=["is_active"])
        self.assertIsNone(claim_job("worker-b",job_id=job.pk)); job.refresh_from_db()
        self.assertEqual((job.status,job.error_code),("failed","permission_revoked"))

    def test_wait_does_not_extend_total_deadline(self):
        job=self.wait(self.enqueue())
        BaichuanJob.objects.filter(pk=job.pk).update(started_at=timezone.now()-timedelta(seconds=121))
        self.assertIsNone(claim_job("worker-b",job_id=job.pk)); job.refresh_from_db()
        self.assertEqual((job.status,job.error_code),("failed","budget_exhausted"))

    def test_invalid_wait_timestamp_is_terminal_not_a_permanent_queue_block(self):
        for stamp in ("bad","2026-10-18T12:00:00"):
            job=self.enqueue(); BaichuanJob.objects.filter(pk=job.pk).update(checkpoint={"model_wait":{"not_before":stamp}})
            self.assertIsNone(claim_job("worker-b",job_id=job.pk));job.refresh_from_db()
            self.assertEqual((job.status,job.error_code),("failed","invalid_checkpoint"))

    def test_upstream_429_timeout_or_ambiguous_busy_is_not_replayed(self):
        for code in ("rate_limited","busy","timeout"):
            job=self.enqueue()
            with patch("portal.baichuan_assistant_worker.generate_for_use",side_effect=GatewayError(code)) as model:
                run_one("worker-a",job.pk); run_one("worker-b",job.pk)
            self.assertEqual(model.call_count,1);job.refresh_from_db()
            self.assertEqual((job.status,job.error_code,job.counts["_budget_model_calls"]),("failed",code,1))

    def test_wait_count_is_finite_even_with_unlimited_model_allowance(self):
        job=self.enqueue()
        BaichuanJob.objects.filter(pk=job.pk).update(checkpoint={"model_wait":{"count":12,
            "not_before":(timezone.now()-timedelta(seconds=1)).isoformat()}})
        with patch("portal.baichuan_assistant_worker.generate_for_use",side_effect=GatewayError(
                "busy",reservation_rejected=True,retry_after=2)) as model:
            self.assertTrue(run_one("worker-a",job.pk));self.assertFalse(run_one("worker-b",job.pk))
        self.assertEqual(model.call_count,1);job.refresh_from_db()
        self.assertEqual((job.status,job.error_code),("failed","model_queue_exhausted"))
        self.assertEqual(job.counts["_budget_model_calls"],0)

    def configured_gateway(self):
        provider=Provider.objects.create(code="wait-provider",name="synthetic",enabled=True,base_url="https://provider.example/v1",
            api_key_env="PORTAL_MODEL_KEY_WAIT")
        model=GatewayModel.objects.create(provider=provider,name="synthetic",model_name="synthetic",enabled=True)
        route=ModelRoute.objects.create(code="wait-route",name="synthetic",module=Module.objects.get(code="product"),
            model=model,enabled=True,max_calls_per_minute=1)
        return model,route

    def test_actual_gateway_rate_rejection_is_marked_before_any_new_log(self):
        model,route=self.configured_gateway()
        _reserve(self.owner,model,"business",route)
        with self.assertRaises(GatewayError) as caught:
            _reserve(self.owner,model,"business",route)
        error=caught.exception
        self.assertEqual(error.code,"rate_limited");self.assertTrue(error.reservation_rejected)
        self.assertTrue(1<=error.retry_after<=61)
        self.assertEqual(ModelCallLog.objects.count(),1)

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=1)
    def test_actual_pending_rejection_is_marked_before_any_new_log(self):
        model,route=self.configured_gateway();_reserve(self.owner,model,"business",route)
        with self.assertRaises(GatewayError) as caught:
            _reserve(self.owner,model,"business",route)
        self.assertEqual(caught.exception.code,"busy");self.assertTrue(caught.exception.reservation_rejected)
        self.assertEqual(ModelCallLog.objects.count(),1)
