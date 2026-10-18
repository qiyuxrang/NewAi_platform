from datetime import date, timedelta

from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanEvidence, BaichuanJob, BaichuanJobItem
from portal.baichuan_jobs import claim_job, retry_job
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_research import create_manifest, record_batch, research_report
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


@override_settings(BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_DATASET_KIND="isolation",
    BAICHUAN_ENVIRONMENT_LABEL="明确虚构隔离样本", BAICHUAN_ASSISTANT_SCOPE="default")
class ResearchQueueTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("research-maintainer", "product")
        self.other = self.create_user("research-other", "product")
        self.reader = self.create_user("research-reader", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.other.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk, self.other.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = self.company_row("研究队列虚构甲")

    def company_row(self, name):
        return Company.objects.create(name=name, phone="00123", source="既有人工研究", version=2,
            created_by=self.actor, updated_by=self.actor)

    def result(self, field="phone", **overrides):
        value = {"company_id": str(self.company.pk), "field": field, "status": "not_found", "reason": "本轮公开原始来源未找到"}
        value.update(overrides)
        return value

    def test_manifest_fixed_ids_versions_and_idempotency_ignore_later_new_company(self):
        manifest, created = create_manifest(self.actor, "manifest-1", fields=["phone", "website"])
        self.assertTrue(created)
        self.assertEqual(manifest.company_versions, [{"id": str(self.company.pk), "version": 2}])
        self.assertEqual((manifest.items.count(), manifest.job.items.count()), (2, 2))
        self.company_row("研究队列虚构乙")
        same, created = create_manifest(self.actor, "manifest-1", fields=["phone", "website"])
        self.assertFalse(created)
        self.assertEqual(same.pk, manifest.pk)
        report = research_report(self.actor, manifest.pk)
        self.assertEqual((report["total_companies"], report["total_fields"], report["researched_companies"]), (1, 2, 0))
        with self.assertRaises(BaichuanError):
            create_manifest(self.actor, "manifest-1", fields=["phone"])

    def test_increment_is_independent_and_does_not_repeat_ancestor_ids(self):
        base, _ = create_manifest(self.actor, "base", fields=["phone"])
        second = self.company_row("研究队列虚构乙")
        increment, _ = create_manifest(self.actor, "increment", fields=["phone"], parent_manifest_id=base.pk)
        self.assertEqual(increment.company_versions, [{"id": str(second.pk), "version": 2}])
        empty, _ = create_manifest(self.actor, "next-increment", fields=["phone"], parent_manifest_id=increment.pk)
        self.assertEqual(empty.total_count, 0)
        report = research_report(self.actor, empty.pk)
        self.assertEqual(report["state"], "empty")
        self.assertIsNone(report["research_coverage"])
        self.assertEqual(empty.job.status, "partial")

    def test_explicit_bounded_budget_uses_standard_validation_and_idempotency_hash(self):
        budget = {"timeout_seconds": 210, "max_model_calls": 1, "max_sources": 10}
        manifest, _ = create_manifest(self.actor, "bounded", budget=budget)
        self.assertEqual(manifest.job.budget, {**budget, "max_attempts": 3})
        same, created = create_manifest(self.actor, "bounded", budget=budget)
        self.assertFalse(created)
        self.assertEqual(same.pk, manifest.pk)
        with self.assertRaises(BaichuanError) as error:
            create_manifest(self.actor, "bounded", budget={**budget, "max_model_calls": 2})
        self.assertEqual(error.exception.code, "idempotency_conflict")
        for invalid in ({"max_model_calls": 0}, {"unknown_budget": 1}, {"timeout_seconds": True}):
            with self.subTest(budget=invalid), self.assertRaises(BaichuanError) as rejected:
                create_manifest(self.actor, "invalid-budget", budget=invalid)
            self.assertEqual(rejected.exception.code, "invalid_budget")

    def test_maintenance_ownership_scope_and_dataset_safety(self):
        with self.assertRaises(BaichuanError):
            create_manifest(self.reader, "forbidden")
        manifest, _ = create_manifest(self.actor, "private", fields=["phone"])
        for user in (self.other, self.reader):
            with self.assertRaises(BaichuanError) as denied:
                research_report(user, manifest.pk)
            self.assertEqual(denied.exception.status, 404)
        for overrides in ({"BAICHUAN_RESEARCH_ENABLED": False}, {"BAICHUAN_DATASET_KIND": "unconfirmed"},
                {"BAICHUAN_DATASET_KIND": "actual", "BAICHUAN_TARGET_DATASET_CONFIRMED": True, "BAICHUAN_TARGET_BACKUP_REF": ""}):
            with self.subTest(settings=overrides), override_settings(**overrides), self.assertRaises(BaichuanError):
                create_manifest(self.actor, "unsafe")
        with override_settings(BAICHUAN_ASSISTANT_SCOPE="another-deployment"), self.assertRaises(BaichuanError):
            research_report(self.actor, manifest.pk)

    def test_batched_results_are_atomic_idempotent_and_never_create_absence(self):
        manifest, _ = create_manifest(self.actor, "batch", fields=["phone", "website"])
        job = claim_job("worker-a", job_id=manifest.job_id)
        report = record_batch(job.pk, "worker-a", job.fence, [self.result()])
        self.assertEqual((report["attempted_fields"], report["researched_companies"], report["verified_fields"]), (1, 0, 0))
        record_batch(job.pk, "worker-a", job.fence, [self.result()])
        self.assertEqual(manifest.items.get(field="phone").attempts, 1)
        with self.assertRaises(BaichuanError):
            record_batch(job.pk, "worker-a", job.fence, [self.result(reason="different")])
        report = record_batch(job.pk, "worker-a", job.fence, [self.result("website", status="inaccessible", reason="来源访问受限")])
        self.assertEqual((report["researched_companies"], report["fully_verified_companies"], report["verified_fields"]), (1, 0, 0))
        self.company.refresh_from_db()
        self.assertEqual((self.company.phone, self.company.version), ("00123", 2))
        self.assertFalse(CompanyQualification.objects.exists())
        self.assertTrue(all(item.status == "completed" for item in BaichuanJobItem.objects.filter(job=job)))

    def test_inaccessible_completion_is_explicitly_an_attempt_not_verification(self):
        manifest, _ = create_manifest(self.actor, "inaccessible-coverage", fields=["phone", "website"])
        report = research_report(self.actor, manifest.pk)
        self.assertEqual((report["attempted_companies"], report["completed_company_attempts"]), (0, 0))
        job = claim_job("coverage-worker", job_id=manifest.job_id)
        first = self.result(status="inaccessible", reason="正文无法读取，不推断不存在")
        report = record_batch(job.pk, "coverage-worker", job.fence, [first])
        self.assertEqual((report["attempted_companies"], report["completed_company_attempts"]), (1, 0))
        report = record_batch(job.pk, "coverage-worker", job.fence, [
            self.result("website", status="inaccessible", reason="正文无法读取，不推断不存在")])
        self.assertEqual((report["attempted_companies"], report["completed_company_attempts"],
                          report["researched_companies"], report["verified_fields"],
                          report["fully_verified_companies"]), (1, 1, 1, 0, 0))
        self.assertEqual(report["research_coverage"], 1)
        self.assertIn("including_inaccessible", report["research_coverage_basis"])
        self.assertEqual(report["field_statuses"]["inaccessible"], 2)
        job.refresh_from_db()
        self.assertEqual((job.counts["attempted_companies"], job.counts["completed_company_attempts"],
                          job.counts["verified_fields"]), (1, 1, 0))

    def test_invalid_second_item_rolls_back_first_and_stale_fence_is_rejected(self):
        manifest, _ = create_manifest(self.actor, "atomic", fields=["phone", "website"])
        job = claim_job("worker-a", job_id=manifest.job_id)
        with self.assertRaises(BaichuanError):
            record_batch(job.pk, "worker-a", job.fence, [self.result(), self.result("website", status="verified", reason="")])
        self.assertEqual(manifest.items.filter(status="pending").count(), 2)
        BaichuanJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        replacement = claim_job("worker-b", job_id=job.pk)
        with self.assertRaises(BaichuanError) as denied:
            record_batch(job.pk, "worker-a", job.fence, [self.result()])
        self.assertEqual(denied.exception.code, "stale_lease")
        record_batch(job.pk, "worker-b", replacement.fence, [self.result()])
        self.assertEqual(manifest.items.get(field="phone").status, "not_found")

    def test_verified_fields_require_body_identity_and_remain_distinct_from_research(self):
        manifest, _ = create_manifest(self.actor, "verified", fields=["phone", "website"])
        job = claim_job("worker", job_id=manifest.job_id)
        evidence = BaichuanEvidence.objects.create(retrieved_at=timezone.now(), verified_on=date(2026, 10, 17),
            access_status="verified", source_type="web", url="https://example.test/phone", excerpt="业务电话00123",
            locator={"section": "联系"}, content_hash="b" * 64,
            subject={"company_id": str(self.company.pk), "identity_verified": True})
        report = record_batch(job.pk, "worker", job.fence, [self.result(status="verified", evidence_id=str(evidence.pk)),
            self.result("website", status="not_disclosed", reason="已查官方来源未公开")])
        self.assertEqual((report["researched_companies"], report["verified_fields"], report["fully_verified_companies"]), (1, 1, 0))
        self.assertEqual(report["field_statuses"]["not_disclosed"], 1)
        with self.assertRaises(ProtectedError):
            self.company.delete()

    def test_retry_keeps_original_denominator_completed_fields_and_failure_history(self):
        manifest, _ = create_manifest(self.actor, "retry-source", fields=["phone", "website"])
        old = claim_job("worker-old", job_id=manifest.job_id)
        record_batch(old.pk, "worker-old", old.fence, [self.result(),
            self.result("website", status="failed", reason="有限网络重试耗尽")])
        retried, _ = retry_job(self.actor, old.pk, idempotency_key="retry-attempt")
        fresh = claim_job("worker-new", job_id=retried.pk)
        record_batch(fresh.pk, "worker-new", fresh.fence,
            [self.result("website", status="inaccessible", reason="已确认来源需要登录，不绕过")])
        report = research_report(self.actor, manifest.pk)
        self.assertEqual((report["total_companies"], report["researched_companies"], report["job_id"]), (1, 1, str(fresh.pk)))
        website = manifest.items.get(field="website")
        self.assertEqual(website.attempts, 2)
        self.assertEqual(website.checkpoint["previous_attempts"][0]["outcome"]["status"], "failed")
        self.assertEqual(manifest.items.get(field="phone").attempts, 1)
        self.assertEqual(BaichuanJobItem.objects.get(job=old, item_key=f"{self.company.pk}:website").result["status"], "failed")
