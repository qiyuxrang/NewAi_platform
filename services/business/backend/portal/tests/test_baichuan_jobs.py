"""Synthetic durable-job tests: no model/network calls and no target data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
import threading
import uuid
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanJob, BaichuanJobItem
from portal.baichuan_jobs import (cancel_job, claim_job, consume_budget, enqueue_job, heartbeat,
    job_for, leased_job, retry_job, save_item, save_job)
from portal.baichuan_service import BaichuanError
from portal.models import Role, User
from .base import PortalTestCase


class JobBehaviorTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("job-owner", "product")
        self.reader = self.create_user("job-reader", "product")
        self.other = self.create_user("job-other", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.reader.pk, self.other.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            BAICHUAN_ASSISTANT_SCOPE="isolated")
        config.enable()
        self.addCleanup(config.disable)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="isolated")

    def enqueue(self, **values):
        return enqueue_job(values.pop("user", self.owner), kind=values.pop("kind", "query"),
            payload=values.pop("payload", {"text": "虚构需求"}),
            idempotency_key=values.pop("idempotency_key", uuid.uuid4().hex), **values)[0]

    def claim(self, **values):
        row = self.enqueue(**values)
        return claim_job("worker-a", job_id=row.pk)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(BaichuanError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_idempotency_hash_preserves_request_and_rejects_changed_payload(self):
        first = self.enqueue(idempotency_key="same-key", conversation=self.conversation)
        second, created = enqueue_job(self.owner, kind="query", payload={"text": "虚构需求"},
            idempotency_key="same-key", conversation=self.conversation)
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        error = self.assert_code("idempotency_conflict", self.enqueue, idempotency_key="same-key",
            payload={"text": "另一个条件"}, conversation=self.conversation)
        self.assertEqual(error.status, 409)
        self.assertEqual(BaichuanJob.objects.count(), 1)
        self.assertNotEqual(self.enqueue(user=self.other, idempotency_key="same-key").pk, first.pk)

    def test_owner_scope_and_foreign_conversation_are_isolated(self):
        job = self.enqueue()
        for identity, scope in [(self.other, None), (self.owner, "another-deployment")]:
            error = self.assert_code("not_found", job_for, identity, job.pk, scope=scope)
            self.assertEqual(error.status, 404)
        self.assert_code("not_found", job_for, self.other, uuid.uuid4())
        self.assert_code("not_found", self.enqueue, user=self.other, conversation=self.conversation)
        self.assert_code("forbidden_execution_identity", self.enqueue, execution_actor=self.other)
        self.assertIsNone(claim_job("w", job_id=uuid.uuid4()))

    def test_readonly_query_and_export_allowed_research_requires_maintenance(self):
        self.assertEqual(self.enqueue(user=self.reader).status, "queued")
        self.assertEqual(self.enqueue(user=self.reader, kind="export").kind, "export")
        error = self.assert_code("baichuan_forbidden", self.enqueue, user=self.reader, kind="research")
        self.assertEqual(error.status, 403)
        self.assertEqual(self.enqueue(kind="research").kind, "research")

    def test_invalid_json_kind_limits_and_budgets_rejected(self):
        for values in [{"kind": "sql"}, {"payload": {"bad": float("nan")}},
                       {"payload": {"bad": "x" * 512001}}, {"budget": {"timeout_seconds": 0}},
                       {"budget": {"max_model_calls": True}}, {"budget": {"max_attempts": 6}},
                       {"budget": {"unbounded": 1}}, {"idempotency_key": ""}]:
            with self.subTest(values=list(values)):
                with self.assertRaises(BaichuanError):
                    self.enqueue(**values)
        self.assertFalse(BaichuanJob.objects.exists())

    def test_crash_reclaims_checkpoint_fence_and_rejects_all_old_writes(self):
        first = self.claim()
        save_job(first.pk, "worker-a", first.fence, checkpoint={"next_company": "fictional-4"},
                 counts={"processed": 3}, result_ref={"snapshot": "fictional-v1"})
        BaichuanJob.objects.filter(pk=first.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        second = claim_job("worker-b", job_id=first.pk)
        self.assertEqual(second.fence, first.fence + 1)
        self.assertEqual(second.attempts, 2)
        self.assertEqual(second.checkpoint, {"next_company": "fictional-4"})
        self.assertEqual(second.result_ref, {"snapshot": "fictional-v1"})
        self.assert_code("stale_lease", heartbeat, first.pk, "worker-a", first.fence)
        self.assert_code("stale_lease", save_job, first.pk, "worker-a", first.fence, status="completed")
        self.assert_code("stale_lease", save_item, first.pk, "worker-a", first.fence, item_key="x", status="completed")
        self.assertFalse(BaichuanJobItem.objects.exists())
        done = save_job(second.pk, "worker-b", second.fence, status="completed", counts={"processed": 4})
        self.assertEqual(done.status, "completed")
        self.assertIsNone(done.lease_expires_at)
        self.assertEqual(done.lease_owner, "")
        self.assertIsNotNone(done.finished_at)

    def test_expired_lease_cannot_heartbeat_or_write_before_reclaim(self):
        job = self.claim()
        BaichuanJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_code("stale_lease", heartbeat, job.pk, "worker-a", job.fence)
        self.assert_code("stale_lease", save_job, job.pk, "worker-a", job.fence, checkpoint={"bad": True})
        job.refresh_from_db()
        self.assertEqual(job.checkpoint, {})

    def test_awaiting_input_releases_lease_and_new_attempt_keeps_prior_result(self):
        job = self.claim()
        waiting = save_job(job.pk, "worker-a", job.fence, status="awaiting_input",
            checkpoint={"question": "证书主体？"}, result_ref={"snapshot": "fictional-v1"})
        self.assertIsNone(waiting.lease_expires_at)
        self.assertEqual(waiting.lease_owner, "")
        self.assertIsNone(claim_job("worker-b", job_id=job.pk))
        retry, created = retry_job(self.owner, job.pk, idempotency_key="new-attempt")
        self.assertTrue(created)
        self.assertEqual(retry.parent_job_id, job.pk)
        self.assertEqual(retry.result_ref, waiting.result_ref)
        self.assertEqual(retry.checkpoint["question"], "证书主体？")
        self.assertEqual(retry.checkpoint["retry_of"], str(job.pk))
        self.assertEqual(retry.attempts, 0)
        duplicate, created = retry_job(self.owner, job.pk, idempotency_key="new-attempt")
        self.assertFalse(created)
        self.assertEqual(duplicate.pk, retry.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "awaiting_input")

    def test_cancel_queued_running_and_awaiting_input_is_terminal_and_idempotent(self):
        for initial in ["queued", "running", "awaiting_input"]:
            with self.subTest(initial=initial):
                job = self.enqueue()
                if initial != "queued":
                    job = claim_job("worker-a", job_id=job.pk)
                    save_item(job.pk, "worker-a", job.fence, item_key="unfinished", status="running")
                if initial == "awaiting_input":
                    save_job(job.pk, "worker-a", job.fence, status=initial)
                cancelled = cancel_job(self.owner, job.pk)
                self.assertEqual(cancelled.status, "cancelled")
                self.assertIsNone(cancelled.lease_expires_at)
                self.assertIsNone(claim_job("worker-b", job_id=job.pk))
                self.assert_code("stale_lease", save_job, job.pk, "worker-a", job.fence, status="completed")
                self.assertEqual(cancel_job(self.owner, job.pk).fence, cancelled.fence)
                self.assertFalse(cancelled.items.exclude(status="cancelled").exists())

    def test_revoked_permission_persists_failed_without_publishing_checkpoint(self):
        job = self.claim(kind="research")
        with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[]):
            self.assert_code("permission_revoked", save_job, job.pk, "worker-a", job.fence,
                checkpoint={"must_not_publish": True}, status="completed")
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("failed", "permission_revoked"))
        self.assertEqual(job.checkpoint, {})
        self.assertIsNone(job.lease_expires_at)
        queued = self.enqueue()
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertIsNone(claim_job("worker-b", job_id=queued.pk))
        queued.refresh_from_db()
        self.assertEqual(queued.error_code, "permission_revoked")
        self.assert_code("not_found", job_for, self.owner, queued.pk)

    def test_budget_reservation_is_finite_preserves_partial_and_cannot_be_reset_by_counts(self):
        job = self.claim(budget={"max_model_calls": 1, "max_sources": 2})
        consume_budget(job.pk, "worker-a", job.fence, model_calls=1, sources=2)
        save_job(job.pk, "worker-a", job.fence, result_ref={"snapshot": "partial"})
        self.assert_code("invalid_request", save_job, job.pk, "worker-a", job.fence,
                         counts={"_budget_sources": 0})
        self.assert_code("budget_exhausted", consume_budget, job.pk, "worker-a", job.fence, sources=1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("partial", "budget_exhausted"))
        self.assertEqual(job.counts["_budget_sources"], 2)
        self.assertEqual(job.result_ref, {"snapshot": "partial"})
        self.assert_code("stale_lease", save_job, job.pk, "worker-a", job.fence, status="completed")

    def test_elapsed_budget_and_reclaim_attempt_limit_stop_without_renewing(self):
        job = self.claim(budget={"timeout_seconds": 1})
        BaichuanJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(seconds=2))
        self.assert_code("budget_exhausted", heartbeat, job.pk, "worker-a", job.fence)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        other = self.claim(budget={"max_attempts": 1})
        BaichuanJob.objects.filter(pk=other.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(claim_job("worker-b", job_id=other.pk))
        other.refresh_from_db()
        self.assertEqual(other.error_code, "budget_exhausted")

    def test_items_completed_idempotently_and_coupled_checkpoint_rolls_back(self):
        job = self.claim()
        item = save_item(job.pk, "worker-a", job.fence, item_key="company-field", status="running")
        self.assertEqual(item.attempts, 1)
        done = save_item(job.pk, "worker-a", job.fence, item_key="company-field", status="completed", result={"state": "not_found"})
        duplicate = save_item(job.pk, "worker-a", job.fence, item_key="company-field", status="completed", result={"state": "not_found"})
        self.assertEqual(done.pk, duplicate.pk)
        self.assertEqual(job.items.count(), 1)
        self.assert_code("item_conflict", save_item, job.pk, "worker-a", job.fence,
            item_key="company-field", status="completed", result={"state": "verified"})
        with self.assertRaises(RuntimeError):
            with leased_job(job.pk, "worker-a", job.fence) as locked:
                BaichuanJobItem.objects.create(job=locked, item_key="atomic", result={"fact_revision": "fictional"})
                locked.checkpoint = {"committed": True}
                locked.save()
                raise RuntimeError("simulated crash before commit")
        self.assertFalse(job.items.filter(item_key="atomic").exists())
        job.refresh_from_db()
        self.assertEqual(job.checkpoint, {})

    def test_retry_refuses_payload_changed_since_original_request_hash(self):
        job = self.enqueue()
        job.status = "failed"
        job.payload = {"synthetic": "changed after submission"}
        job.save()
        before = BaichuanJob.objects.count()
        self.assert_code("request_changed", retry_job, self.owner, job.pk, idempotency_key="hash-changed")
        self.assertEqual(BaichuanJob.objects.count(), before)


class JobConcurrencyTests(TransactionTestCase):
    def setUp(self):
        call_command("seed_portal", stdout=StringIO())
        self.owner = User.objects.create_user("job-thread-owner", password="test-only", must_change_password=False)
        self.owner.roles.add(Role.objects.get(code="product"))
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            BAICHUAN_ASSISTANT_SCOPE="isolated")
        config.enable()
        self.addCleanup(config.disable)

    def test_concurrent_duplicate_submissions_and_claims_publish_once(self):
        barrier = threading.Barrier(2)
        owner_id = self.owner.pk
        def submit(_):
            close_old_connections()
            try:
                user = User.objects.get(pk=owner_id)
                barrier.wait(timeout=10)
                row, created = enqueue_job(user, kind="query", payload={"synthetic": True}, idempotency_key="concurrent")
                return str(row.pk), created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            submitted = list(pool.map(submit, range(2)))
        self.assertEqual(len({result[0] for result in submitted}), 1)
        self.assertEqual(sum(result[1] for result in submitted), 1)
        barrier = threading.Barrier(2)
        def claim(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                row = claim_job(f"worker-{index}")
                return row.fence if row else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, range(2)))
        self.assertEqual(sum(result is not None for result in claims), 1)
        job = BaichuanJob.objects.get()
        self.assertEqual((job.attempts, job.fence), (1, 1))

    def test_independent_processes_deduplicate_and_claim_only_once(self):
        if connection.vendor != "sqlite" or str(connection.settings_dict["NAME"]) == ":memory:":
            self.skipTest("This OS-process probe requires isolated file SQLite.")
        database = str(connection.settings_dict["NAME"])
        if database.startswith("file:"):
            self.skipTest("Shared-memory SQLite cannot cross independent processes.")
        environment = {key: value for key, value in os.environ.items() if key.upper() in {
            "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LOCALAPPDATA", "USERPROFILE"}}
        environment.update(PORTAL_SECRET_KEY="synthetic-baichuan-jobs-process-check-only-20261017",
            PORTAL_DEBUG="1", PORTAL_HTTPS="0", PORTAL_SQLITE_PATH=database,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED="1", PORTAL_BAICHUAN_ASSISTANT_SCOPE="isolated",
            PORTAL_BAICHUAN_READ_USER_IDS=str(self.owner.pk), PORTAL_BAICHUAN_WRITE_USER_IDS=str(self.owner.pk),
            PORTAL_BAICHUAN_READ_ROLE_CODES="", PORTAL_BAICHUAN_WRITE_ROLE_CODES="",
            DJANGO_SETTINGS_MODULE="config.settings", PYTHONIOENCODING="utf-8")
        script = '''import json,sys,time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import django
django.setup()
from portal.models import User
from portal.baichuan_jobs import enqueue_job,claim_job
action,identity,gate,ready,owner = sys.argv[2:]
Path(ready).touch()
deadline=time.monotonic()+10
while not Path(gate).exists():
    if time.monotonic()>deadline: raise RuntimeError('synthetic gate timeout')
    time.sleep(.01)
if action=='submit':
    row,created=enqueue_job(User.objects.get(pk=owner),kind='query',payload={'synthetic':True},idempotency_key='process-duplicate')
    print(json.dumps({'id':str(row.pk),'created':created}))
else:
    row=claim_job(identity)
    print(json.dumps({'fence':row.fence if row else None}))
'''
        backend = str(Path(__file__).resolve().parents[2])
        connection.close()
        with tempfile.TemporaryDirectory(prefix="baichuan-job-process-") as directory:
            for action in ["submit", "claim"]:
                gate = Path(directory) / (action + "-go")
                processes, readies = [], []
                try:
                    for index in range(2):
                        ready = Path(directory) / f"{action}-{index}-ready"
                        readies.append(ready)
                        processes.append(subprocess.Popen([sys.executable, "-c", script, backend, action,
                            f"process-worker-{index}", str(gate), str(ready), str(self.owner.pk)],
                            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
                    deadline = time.monotonic() + 10
                    while not all(path.exists() for path in readies):
                        if time.monotonic() >= deadline:
                            self.fail("Synthetic workers did not become ready.")
                        time.sleep(.01)
                    gate.touch()
                    outputs = []
                    for process in processes:
                        stdout, stderr = process.communicate(timeout=20)
                        self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
                        import json
                        outputs.append(json.loads(stdout))
                    if action == "submit":
                        self.assertEqual(len({row["id"] for row in outputs}), 1)
                        self.assertEqual(sum(row["created"] for row in outputs), 1)
                    else:
                        self.assertEqual(sum(row["fence"] is not None for row in outputs), 1)
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                        process.communicate(timeout=5)
        job = BaichuanJob.objects.get()
        self.assertEqual((job.fence, job.attempts), (1, 1))
