"""Bounded pilot contracts using temporary DB/files and mocked external adapters."""
import copy
from contextlib import closing
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanEvidence, BaichuanFactRevision, BaichuanResearchManifest
from portal.baichuan_jobs import consume_budget
from portal.baichuan_models import Company, CompanyQualification
from .base import PortalTestCase

SCRIPT = Path(__file__).resolve().parents[5] / "scripts/baichuan/research_source_pilot.py"
spec = importlib.util.spec_from_file_location("research_source_pilot_test", SCRIPT)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
HASH = "a" * 64


class PilotBoundaryTests(SimpleTestCase):
    @staticmethod
    def gate():
        return {"kind": "baichuan_public_research_capability_v1", "search": {"provider": "bing_rss",
            "success": True, "tls_verification": True, "result_count": 2}, "public_get": {"success": True,
            "tls_verification": True, "ssrf_pinning": True}, "company_queries": 0, "model_calls": 0}

    def test_generic_gate_requires_each_exact_security_and_success_claim(self):
        value = self.gate()
        pilot.validate_gate(value)
        cases = [None, {**value, "model_calls": True}, {**value, "company_queries": 1}, {**value, "extra": "unsupported"}]
        for parent, key, bad in (("search", "tls_verification", False), ("search", "success", False),
            ("search", "result_count", 0), ("public_get", "ssrf_pinning", False), ("public_get", "success", False)):
            changed = copy.deepcopy(value)
            changed[parent][key] = bad
            cases.append(changed)
        for bad in cases:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                pilot.validate_gate(bad)

    def test_default_cli_is_noop_without_loading_django_or_local_secrets(self):
        with patch("sys.argv", [str(SCRIPT)]), patch.object(pilot, "load_local_model") as setup, patch("builtins.print") as output:
            pilot.main()
        self.assertFalse(setup.called)
        result = json.loads(output.call_args.args[0])
        self.assertEqual((result["mode"], result["database_writes"], result["network_calls"]), ("explanation_only", 0, 0))

    def test_online_backup_checks_integrity_refuses_overwrite_and_does_not_modify_source(self):
        with TemporaryDirectory() as directory:
            source, target = Path(directory) / "source.sqlite3", Path(directory) / "before.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE sample (value TEXT)")
                db.execute("INSERT INTO sample VALUES ('fictional')")
                db.commit()
            before = source.read_bytes()
            receipt = pilot.online_backup(source, target)
            self.assertEqual(receipt["quick_check"], "ok")
            self.assertEqual(source.read_bytes(), before)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute("SELECT value FROM sample").fetchall(), [("fictional",)])
            with self.assertRaises(ValueError):
                pilot.online_backup(source, target)
            with self.assertRaises(TimeoutError):
                pilot.online_backup(source, Path(directory) / "expired.sqlite3", seconds=0)
            self.assertFalse((Path(directory) / "expired.sqlite3").exists())

    def test_missing_execute_hash_or_gate_cannot_start_child(self):
        for args in (["--execute"], ["--execute", "--source-sha256", HASH]):
            with patch("sys.argv", [str(SCRIPT), *args]), patch("sys.stderr", io.StringIO()), patch.object(pilot.subprocess, "run") as spawn, self.assertRaises(SystemExit):
                pilot.main()
            self.assertFalse(spawn.called)


@override_settings(BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=False,
    BAICHUAN_DATASET_KIND="actual", BAICHUAN_TARGET_DATASET_CONFIRMED=True,
    BAICHUAN_TARGET_BACKUP_REF="owned-fixture-backup", BAICHUAN_ENVIRONMENT_LABEL=pilot.LABEL,
    BAICHUAN_ASSISTANT_SCOPE="pilot-test")
class PilotQueueTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("pilot-actor", "product")
        access = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        access.enable()
        self.addCleanup(access.disable)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        storage = override_settings(BAICHUAN_STORAGE_ROOT=self.directory.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.companies = [Company.objects.create(name=f"虚构pilot企业{number}", phone="000123", source="人工原文",
            created_by=self.actor, updated_by=self.actor) for number in range(3)]
        CompanyQualification.objects.create(company=self.companies[0], category="itss", status="PRESENT", grade="2", source="人工原文")
        self.baseline = pilot.catalog_digest()

    def run_pilot(self, **overrides):
        return pilot.run_pilot(self.actor, HASH, limit=overrides.get("limit", 1), backup_ref="owned-fixture-backup",
            baseline=self.baseline, expected_count=3, keep_lease=False)

    @patch("portal.baichuan_research_runtime.search_public_query")
    @patch("portal.baichuan_research_runtime.fetch_public_page")
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_one_company_real_runtime_publishes_12_fields_fixed_full_manifest_and_replay_does_not_call(self, model, fetch, search):
        def discovered(query):
            public_name = query.split(" 官网")[0]
            fetch.return_value = public_name + " 虚构官网 联系电话020-12345678"
            return [{"url": "https://public.example.test/", "title": public_name}]
        search.side_effect = discovered
        def extract(actor, route, messages):
            source = json.loads(messages[-1]["content"])["sources"][0]
            return {"content": json.dumps({"facts": [{"field": "phone", "value": "020-12345678",
                "quote": "联系电话020-12345678", "source_id": source["source_id"]}], "certificates": []})}
        model.side_effect = extract
        result = self.run_pilot()
        manifest = BaichuanResearchManifest.objects.get()
        self.assertEqual((manifest.total_count, len(manifest.fields), manifest.items.count()), (3, 12, 36))
        self.assertEqual((result["status"], result["error_code"]), ("partial", "pilot_batch_limit"))
        self.assertEqual(result["coverage"]["attempted_fields"], 12)
        self.assertEqual(result["coverage"]["researched_companies"], 1)
        self.assertEqual(result["coverage"]["field_statuses"]["pending"], 24)
        self.assertEqual(result["coverage"]["verified_fields"], 0)
        self.assertTrue(result["main_catalog_digest_unchanged"])
        self.assertEqual((result["budget_model_calls_reserved"], result["budget_source_calls_reserved"]), (1, 2))
        self.assertEqual(BaichuanFactRevision.objects.get(field="phone").review_status, "proposed")
        self.assertEqual((model.call_count, fetch.call_count, search.call_count), (1, 1, 1))
        repeated = self.run_pilot()
        self.assertTrue(repeated["replayed_without_network"])
        self.assertEqual(repeated["coverage"]["attempted_fields"], 12)
        self.assertEqual((model.call_count, fetch.call_count, search.call_count), (1, 1, 1))

    @patch("portal.baichuan_research_runtime.search_public_query")
    @patch("portal.baichuan_research_runtime.fetch_public_page", side_effect=TimeoutError("fixture slow GET"))
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_unreadable_source_is_persisted_as_inaccessible_not_verified_or_absent(self, model, fetch, search):
        search.side_effect = lambda query: [{"url": "https://public.example.test/", "text": query.split(" 官网")[0]}]
        result = self.run_pilot()
        self.assertEqual(fetch.call_count, 3)
        self.assertFalse(model.called)
        self.assertEqual(result["coverage"]["field_statuses"]["inaccessible"], 12)
        self.assertTrue(result["main_catalog_digest_unchanged"])
        self.assertEqual(BaichuanEvidence.objects.get(source_type="web").locator["attempts"], 3)

    def test_standard_budget_exhaustion_preserves_partial_without_extra_source_or_model_calls(self):
        def exhausted(job, worker, company, fields):
            consume_budget(job.pk, worker, job.fence, sources=11)
        with patch("portal.baichuan_research_runtime._research_company", side_effect=exhausted):
            result = self.run_pilot()
        self.assertEqual((result["status"], result["error_code"]), ("partial", "budget_exhausted"))
        self.assertEqual(result["coverage"]["attempted_fields"], 0)
        self.assertEqual(result["coverage"]["field_statuses"]["pending"], 36)

    @patch("portal.baichuan_research_runtime.search_public_query")
    @patch("portal.baichuan_research_runtime.fetch_public_page")
    @patch("portal.baichuan_research_runtime.generate_for_use", return_value={"content": '{"facts":[],"certificates":[]}'})
    def test_explicit_two_company_cap_keeps_full_denominator_and_bounded_calls(self, model, fetch, search):
        def discovered(query):
            public_name = query.split(" 官网")[0]
            fetch.return_value = public_name + " 合成公共正文，没有可提取字段"
            return [{"url": "https://public.example.test/", "title": public_name}]
        search.side_effect = discovered
        result = self.run_pilot(limit=2)
        self.assertEqual((result["coverage"]["total_companies"], result["coverage"]["attempted_fields"]), (3, 24))
        self.assertEqual((result["budget_model_calls_reserved"], result["budget_source_calls_reserved"]), (2, 4))
        self.assertEqual((model.call_count, fetch.call_count, search.call_count), (2, 2, 2))
        self.assertTrue(result["main_catalog_digest_unchanged"])

    @patch("portal.baichuan_research_runtime.search_public_query")
    @patch("portal.baichuan_research_runtime.fetch_public_page",
        return_value="完全虚构其他主体有限公司 公开业务电话021-87654321")
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_relevant_search_title_but_wrong_actual_subject_keeps_unknown_without_model_or_suggestions(self, model, fetch, search):
        requested_names = []
        def discovered(query):
            requested_names.append(query.split(" 官网")[0])
            return [{"url": "https://public.example.test/", "title": requested_names[-1]}]
        search.side_effect = discovered
        result = self.run_pilot()
        model.assert_not_called()
        self.assertEqual((search.call_count, fetch.call_count), (1, 1))
        self.assertEqual(result["budget_model_calls_reserved"], 0)
        self.assertTrue(result["main_catalog_digest_unchanged"])
        self.assertEqual(pilot.catalog_digest(), self.baseline)
        self.assertFalse(BaichuanFactRevision.objects.exists())
        manifest = BaichuanResearchManifest.objects.get()
        self.assertEqual((manifest.total_count, manifest.items.count()), (3, 36))
        # process_research classifies readable-but-ineligible extraction as
        # failed/unknown, retaining the other companies' unattempted fields.
        self.assertEqual(result["coverage"]["field_statuses"]["failed"], 12)
        self.assertEqual(result["coverage"]["field_statuses"]["pending"], 24)
        self.assertEqual(result["coverage"]["verified_fields"], 0)
        source = BaichuanEvidence.objects.get(source_type="web")
        self.assertEqual(source.excerpt, "完全虚构其他主体有限公司 公开业务电话021-87654321")
        self.assertEqual(source.subject["public_name"], requested_names[0])
        self.assertEqual((Path(self.directory.name) / source.storage_ref).read_text(encoding="utf-8"), source.excerpt)
        index = BaichuanEvidence.objects.get(source_type="search_index")
        self.assertEqual(index.locator["accepted_count"], 1)
        self.assertEqual(index.locator["urls"], ["https://public.example.test/"])
        for item in manifest.items.filter(status="failed"):
            checkpoint = item.checkpoint["outcome"]["checkpoint"]
            self.assertIn(str(source.pk), checkpoint["evidence_ids"])
            self.assertTrue(any("完整法定名称" in gap for gap in checkpoint["gaps"]))
            self.assertIsNone(item.evidence_id)
            self.assertEqual(item.verification_status, "unverified")

    def test_changed_catalog_or_fact_write_flag_refuses_before_manifest_or_network(self):
        self.companies[0].phone = "人工新修改"
        self.companies[0].save(update_fields=["phone"])
        with self.assertRaises(ValueError):
            self.run_pilot()
        self.assertFalse(BaichuanResearchManifest.objects.exists())
        with override_settings(BAICHUAN_FACT_WRITE_ENABLED=True), self.assertRaises(ValueError):
            self.run_pilot()
