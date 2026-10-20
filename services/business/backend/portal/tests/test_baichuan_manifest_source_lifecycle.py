"""AC11 lifecycle gaps, synthetic files and the runner's isolated SQLite only."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation,
    BaichuanEvidence, BaichuanFactRevision, BaichuanJob, BaichuanMatchSnapshot,
    BaichuanResearchManifest, map_legacy_qualifications)
from portal.baichuan_import import apply_import, preview_import
from portal.baichuan_jobs import claim_job
from portal.baichuan_legacy_evidence import backfill_legacy_source_evidence
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_research import create_manifest, record_batch, research_report
from portal.baichuan_source import convert_source
from portal.baichuan_source_workbook import normalize_workbook
from .base import PortalTestCase
from .test_baichuan_import import workbook as import_workbook
from .test_baichuan_source_workbook import workbook as source_workbook


@override_settings(BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_DATASET_KIND="isolation",
    BAICHUAN_ENVIRONMENT_LABEL="AC11合成来源生命周期隔离样本", BAICHUAN_ASSISTANT_SCOPE="default",
    BAICHUAN_FACT_WRITE_ENABLED=False)
class ManifestSourceLifecycleTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("lifecycle-maintainer", "product")
        access = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        access.enable()
        self.addCleanup(access.disable)
        # Fail immediately if these deterministic services accidentally acquire I/O.
        self.denied = []
        for target in ("socket.getaddrinfo", "socket.socket.connect",
                "portal.baichuan_assistant_worker.generate_for_use",
                "portal.baichuan_research_runtime.generate_for_use"):
            guard = patch(target, side_effect=AssertionError("Lifecycle test forbids network/model"))
            self.denied.append(guard.start())
            self.addCleanup(guard.stop)
        self.addCleanup(self.assert_no_external_calls)

    def assert_no_external_calls(self):
        for guard in self.denied:
            guard.assert_not_called()

    def company(self, name):
        return Company.objects.create(name=name, phone="00123", source="合成人工原值", version=2,
            created_by=self.actor, updated_by=self.actor)

    def snapshot(self, company):
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        job = BaichuanJob.objects.create(owner=self.actor, conversation=conversation, kind="query",
            idempotency_key="historical-query")
        return BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job,
            condition_revision=1, result_revision=1, fact_cutoff_at=timezone.now(),
            condition_tree={"fixture": "historical condition; must not rewrite"},
            candidate_ids=[str(company.pk)], results=[{"company_id": str(company.pk), "status": "candidate"}],
            counts={"confirmed": 0, "candidate": 1})

    def test_explicit_merged_outcome_retains_target_baseline_and_fixed_denominator(self):
        old, target = self.company("合成原主体"), self.company("合成承接主体")
        snapshot = self.snapshot(old)
        old_snapshot = BaichuanMatchSnapshot.objects.get(pk=snapshot.pk).__dict__.copy()
        old_snapshot.pop("_state")
        manifest, _ = create_manifest(self.actor, "explicit-merge", fields=["phone"])
        frozen = list(manifest.company_versions)
        # Simulates a subsequent version, not a fabricated company-merge endpoint.
        Company.objects.filter(pk=old.pk).update(version=3)
        job = claim_job("lifecycle-worker", job_id=manifest.job_id)
        outcome = {"company_id": str(old.pk), "field": "phone", "status": "merged",
            "reason": "隔离维护者显式记录主体承接；不是字段核实或自动合并",
            "checkpoint": {"merge_target_company_id": str(target.pk), "decision_origin": "explicit_fixture"}}
        record_batch(job.pk, "lifecycle-worker", job.fence, [outcome])
        record_batch(job.pk, "lifecycle-worker", job.fence, [outcome])
        item = manifest.items.get(company=old)
        self.assertEqual(item.attempts, 1)
        self.assertEqual(item.verification_status, "unverified")
        self.assertEqual(item.checkpoint["outcome"]["checkpoint"], outcome["checkpoint"])
        self.assertEqual((item.company_version, item.checkpoint["baseline_version"],
            item.checkpoint["observed_version"], item.checkpoint["company_changed"]), (2, 2, 3, True))
        report = record_batch(job.pk, "lifecycle-worker", job.fence, [{"company_id": str(target.pk),
            "field": "phone", "status": "not_found", "reason": "未查证；不推断没有电话"}])
        self.assertEqual((report["total_companies"], report["total_fields"], report["researched_companies"],
            report["fully_verified_companies"], report["verified_fields"]), (2, 2, 2, 0, 0))
        self.assertEqual(report["field_statuses"]["merged"], 1)
        self.assertTrue(report["fixed_denominator"])
        self.assertEqual(BaichuanResearchManifest.objects.get(pk=manifest.pk).company_versions, frozen)
        self.assertEqual(Company.objects.count(), 2)
        self.assertEqual(Company.objects.get(pk=old.pk).phone, "00123")
        after = BaichuanMatchSnapshot.objects.get(pk=snapshot.pk).__dict__.copy()
        after.pop("_state")
        self.assertEqual(after, old_snapshot)

    def test_explicit_removed_is_terminal_unverified_history_not_physical_deletion(self):
        company = self.company("合成待移出主体")
        manifest, _ = create_manifest(self.actor, "explicit-removed", fields=["phone", "website"])
        frozen = list(manifest.company_versions)
        before = list(Company.objects.values())
        job = claim_job("removed-worker", job_id=manifest.job_id)
        report = record_batch(job.pk, "removed-worker", job.fence, [{"company_id": str(company.pk),
            "field": field, "status": "removed", "reason": "显式移出研究说明，保留历史、不物理删除",
            "checkpoint": {"decision_origin": "explicit_fixture", "retained_company_id": str(company.pk)}}
            for field in manifest.fields])
        self.assertEqual((report["total_companies"], report["total_fields"], report["researched_companies"],
            report["verified_fields"], report["field_statuses"]["removed"]), (1, 2, 1, 0, 2))
        self.assertEqual(set(manifest.items.values_list("verification_status", flat=True)), {"unverified"})
        self.assertEqual(BaichuanResearchManifest.objects.get(pk=manifest.pk).company_versions, frozen)
        self.assertEqual(list(Company.objects.values()), before)
        with self.assertRaises(ProtectedError):
            company.delete()
        self.assertEqual(research_report(self.actor, manifest.pk)["missing_company_ids"], [])

    def test_moved_original_excel_preserves_import_evidence_manifest_and_snapshot(self):
        with TemporaryDirectory(prefix="ac11-source-lifecycle-") as directory:
            root = Path(directory)
            original, converted = root / "original.xlsx", root / "converted.xlsx"
            source_workbook(original, [("electronic", "合成来源保留企业", "二级", "陕西省", "西安市", "029-12345678")])
            normalized = normalize_workbook(original)
            original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            self.assertEqual(normalized[-1]["source_sha256"], original_hash)
            artifact = root / "normalized-history.json"
            artifact.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
            sheets, mapping, conversion = convert_source(*normalized)
            rows = [dict(zip(mapping["company_columns"].values(), row)) for row in sheets["sheets"][0]["rows"]]
            import_workbook(converted, rows, mapping=mapping)
            preview = preview_import(converted, mapping)
            self.assertEqual(preview["issues"], [])
            preview["confirmed"] = True
            apply_import(converted, preview, self.actor, mapping)
            company = Company.objects.get(name="合成来源保留企业")
            map_legacy_qualifications(company, self.actor)
            legacy = CompanyQualification.objects.get(company=company)
            locator = normalized[1][0]["source_rows"]
            context = {str(legacy.pk): {"source": legacy.source,
                "source_sha256": hashlib.sha256(legacy.source.encode()).hexdigest(),
                "import_ref": "sha256:" + original_hash,
                "locator": {"sheet": locator["summary"]["sheet"], "row": locator["summary"]["row"],
                    "section": {"sheet": locator["detail"]["sheet"], "row": locator["detail"]["row"]}}}}
            self.assertEqual(backfill_legacy_source_evidence(company, self.actor,
                source_context_by_legacy_id=context)["created"], 1)
            manifest, _ = create_manifest(self.actor, "source-history", fields=["qualifications"])
            self.snapshot(company)
            models = (Company, CompanyQualification, BaichuanCertificate, BaichuanEvidence,
                BaichuanFactRevision, BaichuanResearchManifest, BaichuanMatchSnapshot, BaichuanJob)
            history = {model.__name__: list(model.objects.order_by("pk").values()) for model in models}
            original.rename(root / "moved-original.xlsx")
            converted.rename(root / "moved-converted.xlsx")
            with self.assertRaises(FileNotFoundError):
                normalize_workbook(original)
            with self.assertRaises(FileNotFoundError):
                preview_import(converted, mapping)
            replay = backfill_legacy_source_evidence(company, self.actor, source_context_by_legacy_id=context)
            self.assertEqual(replay, {"created": 0, "already_linked": 1, "empty_source": 0})
            same, created = create_manifest(self.actor, "source-history", fields=["qualifications"])
            self.assertFalse(created)
            self.assertEqual(same.pk, manifest.pk)
            self.assertEqual({model.__name__: list(model.objects.order_by("pk").values()) for model in models}, history)
            restored = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(restored[-1]["source_sha256"], original_hash)
            self.assertEqual(restored[1][0]["source_rows"], locator)
            evidence = BaichuanEvidence.objects.get()
            self.assertEqual((evidence.import_ref, evidence.locator), ("sha256:" + original_hash, context[str(legacy.pk)]["locator"]))
            self.assertEqual(evidence.excerpt, legacy.source)
            self.assertEqual(evidence.access_status, "unverified")
            self.assertFalse(evidence.subject["identity_verified"])
            self.assertEqual(research_report(self.actor, manifest.pk)["verified_fields"], 0)
