"""Isolated unlimited-query accounting; no gateway, network or real data."""
from datetime import timedelta
import uuid

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanJob
from portal.baichuan_jobs import claim_job, consume_budget, enqueue_job, heartbeat, retry_job, save_job
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


@override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=True)
class QueryModelBudgetTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("unlimited-query-owner", "product")
        self.other = self.create_user("unlimited-query-other", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            BAICHUAN_ASSISTANT_SCOPE="isolated-query-model-budget")
        config.enable()
        self.addCleanup(config.disable)

    def enqueue(self, **values):
        return enqueue_job(values.pop("user", self.owner), kind=values.pop("kind", "query"),
            payload=values.pop("payload", {"text": "合成条件"}),
            idempotency_key=values.pop("idempotency_key", uuid.uuid4().hex), **values)[0]

    def claim(self, **values):
        return claim_job("budget-worker", job_id=self.enqueue(**values).pk)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(BaichuanError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_default_query_has_no_total_model_limit_and_records_all_reservations(self):
        job = self.claim()
        self.assertIsNone(job.budget["max_model_calls"])
        for increment in [8, 1, 10000]:
            consume_budget(job.pk, "budget-worker", job.fence, model_calls=increment)
        job.refresh_from_db()
        self.assertEqual(job.counts["_budget_model_calls"], 10009)
        self.assertEqual(job.status, "running")
        self.assertEqual(job.budget["max_attempts"], 3)
        self.assertEqual(job.budget["timeout_seconds"], 120)

    def test_old_numeric_request_budget_is_preserved_but_not_enforced_when_enabled(self):
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            job = self.enqueue(budget={"max_model_calls": 1})
        original_hash, original_budget = job.request_hash, dict(job.budget)
        job = claim_job("budget-worker", job_id=job.pk)
        consume_budget(job.pk, "budget-worker", job.fence, model_calls=9)
        job.refresh_from_db()
        self.assertEqual(job.counts["_budget_model_calls"], 9)
        self.assertEqual(job.request_hash, original_hash)
        self.assertEqual(job.budget, original_budget)

    def test_disabled_setting_keeps_existing_finite_query_behavior(self):
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            job = self.claim(budget={"max_model_calls": 1})
            consume_budget(job.pk, "budget-worker", job.fence, model_calls=1)
            self.assert_code("budget_exhausted", consume_budget, job.pk, "budget-worker", job.fence, model_calls=1)
        job.refresh_from_db()
        self.assertEqual(job.counts["_budget_model_calls"], 1)
        self.assertEqual(job.error_code, "budget_exhausted")

    def test_other_kinds_remain_model_limited_and_reject_null(self):
        for kind in ["parse", "research", "export"]:
            with self.subTest(kind=kind):
                self.assert_code("invalid_budget", self.enqueue, kind=kind, budget={"max_model_calls": None})
                job = self.claim(kind=kind, budget={"max_model_calls": 1})
                consume_budget(job.pk, "budget-worker", job.fence, model_calls=1)
                self.assert_code("budget_exhausted", consume_budget, job.pk, "budget-worker", job.fence, model_calls=1)

    def test_other_kinds_keep_finite_default_when_query_switch_enabled(self):
        for kind in ["parse", "research", "export"]:
            with self.subTest(kind=kind):
                self.assertEqual(self.enqueue(kind=kind).budget["max_model_calls"], 8)

    def test_source_limit_still_preserves_partial_and_cannot_be_reset_by_progress(self):
        job = self.claim(budget={"max_sources": 1})
        consume_budget(job.pk, "budget-worker", job.fence, model_calls=19, sources=1)
        save_job(job.pk, "budget-worker", job.fence, result_ref={"snapshot": "synthetic-partial"})
        self.assert_code("invalid_request", save_job, job.pk, "budget-worker", job.fence,
            counts={"_budget_model_calls": 0})
        self.assert_code("budget_exhausted", consume_budget, job.pk, "budget-worker", job.fence, sources=1)
        job.refresh_from_db()
        self.assertEqual(job.status, "partial")
        self.assertEqual(job.counts["_budget_model_calls"], 19)
        self.assertEqual(job.result_ref, {"snapshot": "synthetic-partial"})

    def test_elapsed_timeout_still_stops_an_unlimited_query(self):
        job = self.claim(budget={"timeout_seconds": 1})
        BaichuanJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(seconds=2))
        self.assert_code("budget_exhausted", consume_budget, job.pk, "budget-worker", job.fence, model_calls=1)
        job.refresh_from_db()
        self.assertEqual(job.error_code, "budget_exhausted")
        self.assertEqual(job.counts, {})

    def test_attempt_limit_still_stops_a_crashed_unlimited_query(self):
        job = self.claim(budget={"max_attempts": 1})
        BaichuanJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(claim_job("another-worker", job_id=job.pk))
        job.refresh_from_db()
        self.assertEqual(job.error_code, "budget_exhausted")

    def test_revoked_permission_stops_without_recording_another_reservation(self):
        job = self.claim()
        consume_budget(job.pk, "budget-worker", job.fence, model_calls=1)
        with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[]):
            self.assert_code("permission_revoked", consume_budget, job.pk, "budget-worker", job.fence, model_calls=1)
        job.refresh_from_db()
        self.assertEqual(job.error_code, "permission_revoked")
        self.assertEqual(job.counts["_budget_model_calls"], 1)

    def test_retry_preserves_budget_hash_progress_and_resets_attempt_usage(self):
        job = self.claim()
        consume_budget(job.pk, "budget-worker", job.fence, model_calls=20)
        save_job(job.pk, "budget-worker", job.fence, counts={"processed": 3},
            checkpoint={"safe": "checkpoint"}, status="failed")
        original_hash = job.request_hash
        retry, created = retry_job(self.owner, job.pk, idempotency_key="unlimited-retry")
        self.assertTrue(created)
        self.assertIsNone(retry.budget["max_model_calls"])
        self.assertEqual(retry.counts, {"processed": 3})
        self.assertEqual(retry.checkpoint["safe"], "checkpoint")
        self.assertEqual(retry.attempts, 0)
        duplicate, created = retry_job(self.owner, job.pk, idempotency_key="unlimited-retry")
        self.assertFalse(created)
        self.assertEqual(duplicate.pk, retry.pk)
        job.refresh_from_db()
        self.assertEqual(job.request_hash, original_hash)
        self.assertEqual(job.counts["_budget_model_calls"], 20)

    def test_retry_of_stored_null_survives_switch_off_with_finite_execution_fallback(self):
        job = self.claim()
        save_job(job.pk, "budget-worker", job.fence, status="failed")
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            retry, created = retry_job(self.owner, job.pk, idempotency_key="finite-after-switch")
            self.assertTrue(created)
            self.assertIsNone(retry.budget["max_model_calls"])
            retry = claim_job("budget-worker", job_id=retry.pk)
            consume_budget(retry.pk, "budget-worker", retry.fence, model_calls=8)
            self.assert_code("budget_exhausted", consume_budget, retry.pk, "budget-worker", retry.fence, model_calls=1)

    def test_retry_cannot_clone_other_owners_null_budget(self):
        job = self.claim()
        save_job(job.pk, "budget-worker", job.fence, status="failed")
        self.assert_code("not_found", retry_job, self.other, job.pk, idempotency_key="foreign-retry")
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            self.assert_code("not_found", self.enqueue, user=self.other, parent_job=job, budget=job.budget)

    def test_default_idempotency_survives_switch_change_but_rejects_payload_change(self):
        for first, second in [(False, True), (True, False)]:
            with self.subTest(first=first):
                key = uuid.uuid4().hex
                with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=first):
                    job = self.enqueue(idempotency_key=key)
                with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=second):
                    duplicate = self.enqueue(idempotency_key=key)
                    self.assertEqual(duplicate.pk, job.pk)
                    self.assert_code("idempotency_conflict", self.enqueue, idempotency_key=key,
                        payload={"text": "changed"})
                    self.assert_code("idempotency_conflict", self.enqueue, idempotency_key=key,
                        budget={"max_model_calls": 2})

    def test_invalid_budgets_and_usage_are_rejected_even_when_unlimited(self):
        for budget in [{"timeout_seconds": None}, {"max_sources": None}, {"max_attempts": None},
                {"max_model_calls": True}, {"max_model_calls": -1}, {"max_model_calls": 10001},
                {"max_model_calls": "unlimited"}, {"unbounded": 1}, {"timeout_seconds": 86401}]:
            with self.subTest(budget=budget):
                self.assert_code("invalid_budget", self.enqueue, budget=budget)
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            self.assert_code("invalid_budget", self.enqueue, budget={"max_model_calls": None})
        job = self.claim()
        for values in [{"model_calls": True}, {"model_calls": -1}, {"sources": None}]:
            with self.subTest(values=values):
                self.assert_code("invalid_request", consume_budget, job.pk, "budget-worker", job.fence, **values)

    def test_partial_budget_idempotency_preserves_original_defaults_after_switch_change(self):
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            job = self.enqueue(idempotency_key="partial-budget", budget={"timeout_seconds": 60})
        duplicate = self.enqueue(idempotency_key="partial-budget", budget={"timeout_seconds": 60})
        self.assertEqual(duplicate.pk, job.pk)
        self.assertEqual(duplicate.budget["max_model_calls"], 8)
        self.assert_code("idempotency_conflict", self.enqueue, idempotency_key="partial-budget",
            budget={"timeout_seconds": 61})

    def test_explicit_null_idempotency_replay_survives_switch_off_without_allowing_new_null(self):
        job = self.enqueue(idempotency_key="null-budget", budget={"max_model_calls": None})
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            duplicate = self.enqueue(idempotency_key="null-budget", budget={"max_model_calls": None})
            self.assertEqual(duplicate.pk, job.pk)
            self.assert_code("invalid_budget", self.enqueue, budget={"max_model_calls": None})

    def test_tampered_request_cannot_be_retried_when_unlimited(self):
        job = self.claim()
        save_job(job.pk, "budget-worker", job.fence, status="failed")
        BaichuanJob.objects.filter(pk=job.pk).update(budget={**job.budget, "max_model_calls": 1})
        self.assert_code("request_changed", retry_job, self.owner, job.pk, idempotency_key="tampered")

    def test_disabled_stored_null_query_heartbeat_keeps_timeout_and_original_budget(self):
        job = self.claim(budget={"timeout_seconds": 1})
        BaichuanJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(seconds=2))
        with override_settings(BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS=False):
            self.assert_code("budget_exhausted", heartbeat, job.pk, "budget-worker", job.fence)
        job.refresh_from_db()
        self.assertIsNone(job.budget["max_model_calls"])
        self.assertEqual(job.error_code, "budget_exhausted")
