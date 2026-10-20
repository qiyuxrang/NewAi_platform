import json
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanConversation, BaichuanEvidence, BaichuanFactRevision, BaichuanMatchSnapshot
from portal.baichuan_jobs import claim_job, enqueue_job, retry_job, save_job
from portal.baichuan_models import Company
from portal.baichuan_research import create_manifest, research_report
from portal.baichuan_research_runtime import (SEARCH_RELEVANCE_POLICY, _hash, _independent_subject,
    _search, process_research, run_query_research)
from portal.baichuan_service import BaichuanError
from portal.model_gateway import GatewayError
from portal.product_service import ProductError
from .base import PortalTestCase


@override_settings(BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
    BAICHUAN_DATASET_KIND="isolation", BAICHUAN_ENVIRONMENT_LABEL="虚构研究runtime样本", BAICHUAN_ASSISTANT_SCOPE="default")
class ResearchRuntimeTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("research-runtime", "product")
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, BAICHUAN_STORAGE_ROOT=self.temporary.name,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name="公开虚构企业名称", website="https://example.test/", phone="000-manual",
            contact_name="内部人工联系人不能发搜索", created_by=self.actor, updated_by=self.actor)

    def query(self, key):
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        queued, _ = enqueue_job(self.actor, kind="query", payload={"text": "内部招标内容与秘密报价不能发搜索"},
            idempotency_key=key, conversation=conversation)
        job = claim_job("runtime-worker", job_id=queued.pk, lease_seconds=300)
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
            result_revision=1, fact_cutoff_at=timezone.now(), condition_tree={"must": {"category": "itss"}},
            results=[{"company_id": str(self.company.pk), "status": "candidate"}])
        return job, snapshot

    @staticmethod
    def extracted(actor, route, messages, **kwargs):
        sources = json.loads(messages[-1]["content"])["sources"]
        source = sources[0]
        return {"content": json.dumps({"facts": [{"field": "phone", "value": "020-12345678",
            "quote": "公开业务电话020-12345678", "source_id": source["source_id"]}], "certificates": []})}

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_public_only_query_body_suggestions_and_persistent_source_cache(self, model, fetch, search):
        job, snapshot = self.query("first")
        result = run_query_research(job, "runtime-worker", snapshot)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["counts"]["research_suggestions"], 1)
        search_query = search.call_args.args[0]
        self.assertIn(self.company.name, search_query)
        self.assertNotIn("内部", search_query)
        self.assertNotIn("000-manual", search_query)
        revision = BaichuanFactRevision.objects.get(field="phone")
        self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "000-manual")
        source = BaichuanEvidence.objects.get(source_type="web")
        self.assertEqual(source.subject["identity_verified"], False)
        self.assertEqual(source.access_status, "fetched")
        self.assertTrue(source.storage_ref.endswith(".txt"))
        repeated = run_query_research(job, "runtime-worker", snapshot)
        self.assertEqual(repeated["status"], "partial")
        self.assertEqual(repeated["counts"], result["counts"])
        job.refresh_from_db()
        self.assertEqual(job.counts["researched_companies"], 1)
        next_job, next_snapshot = self.query("second")
        next_result = run_query_research(next_job, "runtime-worker", next_snapshot)
        self.assertGreaterEqual(next_result["counts"]["research_cache_hits"], 2)
        self.assertEqual((search.call_count, fetch.call_count), (1, 1))
        self.assertEqual(BaichuanFactRevision.objects.count(), 1)

    @patch("portal.baichuan_research_runtime.search_public_query")
    def test_search_accepts_complete_legal_name_in_title_or_text_with_only_parentheses_whitespace_case_normalization(self, search):
        self.company.name = "虚构 Example（集团）有限公司"
        self.company.save(update_fields=["name"])
        search.return_value = [
            {"title": "虚构example(集团) 有限公司官网", "url": "https://related-one.test/"},
            {"title": "公开登记", "text": "记录：虚构 Example（集团）有限公司", "url": "https://related-two.test/"},
            {"title": "虚构Example集团有限公司", "url": "https://missing-parentheses.test/"},
            {"title": "完全不同的企业", "url": "https://unrelated.test/虚构Example（集团）有限公司"},
        ]
        job, _ = self.query("relevant-search")
        urls, error, cache_hits = _search(job, "runtime-worker", self.company, [])
        self.assertEqual((urls, error, cache_hits), (["https://related-one.test/", "https://related-two.test/"], "", 0))
        evidence = BaichuanEvidence.objects.get(source_type="search_index")
        self.assertEqual(evidence.access_status, "discovered")
        self.assertEqual(evidence.locator["relevance_policy"], SEARCH_RELEVANCE_POLICY)
        self.assertEqual((evidence.locator["received_count"], evidence.locator["accepted_count"], evidence.locator["discarded_count"]), (4, 2, 2))
        self.assertFalse(evidence.subject["identity_verified"])

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[
        {"title": "Google Search", "text": "Generic search service", "url": "https://google.test/"},
        {"title": "另一家公开虚构企业", "text": "名称不同", "url": "https://other-company.test/"},
        {"title": "Wikipedia", "url": "https://wiki.test/公开虚构企业名称"}])
    @patch("portal.baichuan_research_runtime.fetch_public_page")
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_all_irrelevant_search_results_are_recorded_and_never_fetch_or_call_model(self, model, fetch, search):
        self.company.website = None
        self.company.save(update_fields=["website"])
        job, snapshot = self.query("irrelevant-search")
        result = run_query_research(job, "runtime-worker", snapshot)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("线索未包含本企业完整名称" in gap for gap in result["gaps"]))
        self.assertFalse(fetch.called or model.called)
        evidence = BaichuanEvidence.objects.get(source_type="search_index")
        self.assertEqual(evidence.locator["error_code"], "web_search_irrelevant_results")
        self.assertEqual(evidence.locator["urls"], [])
        self.assertEqual((evidence.locator["received_count"], evidence.locator["discarded_count"]), (3, 3))
        self.assertFalse(BaichuanEvidence.objects.filter(source_type="web").exists())
        self.assertFalse(BaichuanFactRevision.objects.exists())

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page")
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_actual_empty_search_has_distinct_no_hits_evidence_without_inventing_absence(self, model, fetch, search):
        self.company.website = None
        self.company.save(update_fields=["website"])
        job, snapshot = self.query("no-hits-search")
        result = run_query_research(job, "runtime-worker", snapshot)
        self.assertTrue(any("未命中不能说明企业或资料不存在" in gap for gap in result["gaps"]))
        evidence = BaichuanEvidence.objects.get(source_type="search_index")
        self.assertEqual(evidence.locator["error_code"], "web_search_no_hits")
        self.assertEqual((evidence.locator["received_count"], evidence.locator["discarded_count"]), (0, 0))
        self.assertFalse(fetch.called or model.called)

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[
        {"title": "完全无关的搜索服务", "url": "https://unrelated.test/"}])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 原官网公开正文")
    @patch("portal.baichuan_research_runtime.generate_for_use", return_value={"content": '{"facts":[],"certificates":[]}'})
    def test_irrelevant_discovery_does_not_block_existing_website_or_upgrade_its_identity(self, model, fetch, search):
        job, snapshot = self.query("irrelevant-existing-site")
        result = run_query_research(job, "runtime-worker", snapshot)
        fetch.assert_called_once_with(self.company.website)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(BaichuanEvidence.objects.get(source_type="web").subject["identity_verified"])
        self.assertEqual(BaichuanEvidence.objects.get(source_type="search_index").locator["urls"], [])

    @patch("portal.baichuan_research_runtime.search_public_query")
    def test_pre_policy_search_cache_is_retained_but_not_reused_and_current_policy_cache_is_reused(self, search):
        job, _ = self.query("old-cache-search")
        query_hash = _hash(self.company.name + " 官网 联系方式 公开资质")
        historical = BaichuanEvidence.objects.create(scope=job.scope, source_type="search_index",
            retrieved_at=timezone.now(), access_status="discovered", content_hash="a" * 64,
            subject={"company_id": str(self.company.pk), "identity_verified": False},
            locator={"query_hash": query_hash, "urls": ["https://old-unrelated.test/"], "job_id": str(job.pk)})
        search.return_value = [{"title": self.company.name, "url": "https://current-related.test/"}]
        first = _search(job, "runtime-worker", self.company, [])
        second = _search(job, "runtime-worker", self.company, [])
        self.assertEqual(first, (["https://current-related.test/"], "", 0))
        self.assertEqual(second, (["https://current-related.test/"], "", 1))
        self.assertEqual(search.call_count, 1)
        self.assertTrue(BaichuanEvidence.objects.filter(pk=historical.pk).exists())
        self.assertEqual(BaichuanEvidence.objects.filter(source_type="search_index").count(), 2)

    @patch("portal.baichuan_research_runtime.search_public_query", side_effect=ProductError("web_search_unconfigured", "未配置", 409))
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=GatewayError("unconfigured"))
    def test_missing_search_still_reads_existing_website_and_falls_back_to_quoted_suggestions(self, model, fetch, search):
        job, snapshot = self.query("no-search")
        result = run_query_research(job, "runtime-worker", snapshot)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(any("搜索" in gap for gap in result["gaps"]))
        self.assertEqual(BaichuanFactRevision.objects.get().new_value, "020-12345678")

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_linked_retry_retains_completed_progress_without_inheriting_attempt_budget_or_repeating_calls(self, model, fetch, search):
        job, snapshot = self.query("linked-retry-source")
        first = run_query_research(job, "runtime-worker", snapshot)
        job.refresh_from_db()
        self.assertEqual(first["counts"]["researched_companies"], 1)
        self.assertGreater(job.counts["_budget_model_calls"], 0)
        save_job(job.pk, "runtime-worker", job.fence, status="partial",
            result_ref={"snapshot_id": str(snapshot.pk)})
        retried, created = retry_job(self.actor, job.pk, idempotency_key="linked-retry-attempt")
        self.assertTrue(created)
        self.assertEqual(retried.parent_job_id, job.pk)
        self.assertEqual(retried.result_ref, {"snapshot_id": str(snapshot.pk)})
        self.assertEqual({key: retried.counts.get(key, 0) for key in first["counts"]}, first["counts"])
        self.assertFalse(any(key.startswith("_budget_") for key in retried.counts))
        fresh = claim_job("linked-retry-worker", job_id=retried.pk, lease_seconds=300)
        model.reset_mock()
        fetch.reset_mock()
        search.reset_mock()
        again = run_query_research(fresh, "linked-retry-worker", snapshot)
        self.assertEqual(again["counts"], first["counts"])
        self.assertFalse(model.called or fetch.called or search.called)
        self.assertEqual(BaichuanFactRevision.objects.count(), 1)
        self.assertEqual(BaichuanEvidence.objects.filter(source_type="web").count(), 1)

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", side_effect=OSError("transient"))
    @patch("portal.baichuan_research_runtime.generate_for_use")
    def test_source_network_retry_is_bounded_and_failure_is_cached(self, model, fetch, search):
        job, snapshot = self.query("network")
        result = run_query_research(job, "runtime-worker", snapshot)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(fetch.call_count, 3)
        self.assertFalse(model.called)
        source = BaichuanEvidence.objects.get(source_type="web")
        self.assertEqual((source.access_status, source.locator["attempts"]), ("inaccessible", 3))
        fresh, snapshot = self.query("network-reuse")
        run_query_research(fresh, "runtime-worker", snapshot)
        self.assertEqual(fetch.call_count, 3)
        self.assertFalse(BaichuanFactRevision.objects.exists())

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", side_effect=ssl.SSLCertVerificationError("untrusted"))
    def test_tls_failure_is_recorded_once_without_disabling_certificate_checks(self, fetch, search):
        job, snapshot = self.query("tls-failure")
        self.assertEqual(run_query_research(job, "runtime-worker", snapshot)["status"], "partial")
        self.assertEqual(fetch.call_count, 1)
        evidence = BaichuanEvidence.objects.get(source_type="web")
        self.assertEqual(evidence.locator["error_code"], "source_tls_untrusted")

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", return_value={"content": json.dumps({"facts": [
        {"field": "email", "value": "fabricated@example.test", "quote": "网页并无此原文", "source_id": "invented"}], "certificates": []})})
    def test_invented_model_quote_is_rejected_and_cannot_create_verified_facts(self, model, fetch, search):
        job, snapshot = self.query("bad-quote")
        run_query_research(job, "runtime-worker", snapshot)
        self.assertFalse(BaichuanFactRevision.objects.filter(field="email").exists())
        self.assertFalse(BaichuanFactRevision.objects.filter(verification_status="verified").exists())
        self.assertFalse(BaichuanCertificate.objects.exists())

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_full_queue_publishes_suggestions_and_field_progress_together(self, model, fetch, search):
        manifest, _ = create_manifest(self.actor, "full-fixture", fields=["phone", "website"])
        job = claim_job("runtime-worker", job_id=manifest.job_id, lease_seconds=300)
        process_research(job, "runtime-worker")
        report = research_report(self.actor, manifest.pk)
        self.assertEqual((report["state"], report["researched_companies"], report["verified_fields"]), ("completed", 1, 0))
        self.assertEqual(report["field_statuses"]["pending_review"], 1)
        self.assertEqual(report["field_statuses"]["not_found"], 1)
        self.assertEqual(manifest.items.get(field="phone").checkpoint["outcome"]["status"], "pending_review")
        self.assertEqual(BaichuanFactRevision.objects.get().review_status, "proposed")

    @override_settings(BAICHUAN_RESEARCH_ENABLED=False)
    @patch("portal.baichuan_research_runtime.search_public_query")
    @patch("portal.baichuan_research_runtime.fetch_public_page")
    def test_disabled_research_has_no_external_calls(self, fetch, search):
        job, snapshot = self.query("disabled")
        self.assertEqual(run_query_research(job, "runtime-worker", snapshot)["status"], "partial")
        self.assertFalse(fetch.called or search.called)

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称 ITSS二级证书00123")
    def test_certificate_normalization_uses_quoted_raw_values_and_discards_fabricated_fields(self, fetch, search):
        def response(actor, route, messages, **kwargs):
            source = json.loads(messages[-1]["content"])["sources"][0]
            return {"content": json.dumps({"facts": [], "certificates": [{"source_id": source["source_id"],
                "quote": "ITSS二级证书00123", "declaration": {"raw_category": "ITSS", "category": "cmmi",
                    "raw_grade": "二级", "grade": "5", "certificate_no": "00123", "issuer": "模型虚构机构",
                    "holder_name": "模型虚构持有人", "holder_type": "bidder", "valid_until": "2099-01-01"}}]})}
        job, snapshot = self.query("certificate-normalization")
        with patch("portal.baichuan_research_runtime.generate_for_use", side_effect=response):
            run_query_research(job, "runtime-worker", snapshot)
        revision = BaichuanFactRevision.objects.get(field="certificate")
        self.assertEqual((revision.new_value["category"], revision.new_value["grade"]), ("itss", "2"))
        self.assertNotIn("issuer", revision.new_value)
        self.assertNotIn("holder_name", revision.new_value)
        self.assertNotIn("valid_until", revision.new_value)
        self.assertEqual(revision.new_value["holder_type"], "unknown")
        self.assertFalse(BaichuanCertificate.objects.exists())

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.fetch_public_page", return_value="公开虚构企业名称\n公开业务电话020-12345678")
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_multiline_storage_hash_is_verified_and_changed_cache_is_rejected(self, model, fetch, search):
        job, snapshot = self.query("storage")
        run_query_research(job, "runtime-worker", snapshot)
        evidence = BaichuanEvidence.objects.get(source_type="web")
        target = Path(self.temporary.name) / evidence.storage_ref
        self.assertEqual(target.read_bytes(), evidence.excerpt.encode("utf-8"))
        self.assertTrue(evidence.locator["full_text_not_confirmed"])
        target.write_bytes(b"changed")
        next_job, next_snapshot = self.query("storage-changed")
        with self.assertRaises(BaichuanError) as error:
            run_query_research(next_job, "runtime-worker", next_snapshot)
        self.assertEqual(error.exception.code, "source_storage_changed")
        self.assertEqual(fetch.call_count, 1)

    def test_empty_manifest_retry_ends_partial_instead_of_running_forever(self):
        self.company.delete()
        manifest, _ = create_manifest(self.actor, "empty")
        retry, _ = retry_job(self.actor, manifest.job_id, idempotency_key="empty-retry")
        running = claim_job("runtime-worker", job_id=retry.pk, lease_seconds=300)
        process_research(running, "runtime-worker")
        retry.refresh_from_db()
        self.assertEqual((retry.status, retry.error_code), ("partial", "empty_manifest"))

    def verified_body(self, **changes):
        Company.objects.filter(pk=self.company.pk).update(credit_code="91310000MA1234567X", phone=None, **changes)
        self.company.refresh_from_db()
        return f"{self.company.name} 统一社会信用代码91310000MA1234567X 公开业务电话020-12345678"

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_independent_corporate_host_name_credit_code_and_business_context_allow_blank_phone_fill(self, model, search):
        body = self.verified_body()
        manifest, _ = create_manifest(self.actor, "independent-phone", fields=["phone"])
        job = claim_job("runtime-worker", job_id=manifest.job_id, lease_seconds=300)
        with patch("portal.baichuan_research_runtime.fetch_public_page", return_value=body):
            process_research(job, "runtime-worker")
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "020-12345678")
        evidence = BaichuanEvidence.objects.get(source_type="web")
        self.assertEqual(evidence.subject["identity_method"], "official_host_name_credit_code")
        self.assertEqual(evidence.subject["authority"], "corporate")
        self.assertNotIn("revocation_checked", evidence.subject)
        self.assertEqual(BaichuanFactRevision.objects.get(field="phone").review_status, "applied")
        report = research_report(self.actor, manifest.pk)
        self.assertEqual((report["verified_fields"], report["fully_verified_companies"]), (1, 1))

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_independently_identified_page_still_cannot_write_for_reader(self, model, search):
        body = self.verified_body()
        job, snapshot = self.query("independent-reader")
        with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[]), patch("portal.baichuan_research_runtime.fetch_public_page", return_value=body):
            run_query_research(job, "runtime-worker", snapshot)
        self.company.refresh_from_db()
        self.assertIsNone(self.company.phone)
        self.assertEqual(BaichuanFactRevision.objects.get(field="phone").review_status, "proposed")

    @patch("portal.baichuan_research_runtime.search_public_query", return_value=[])
    @patch("portal.baichuan_research_runtime.generate_for_use", side_effect=extracted)
    def test_identity_or_business_context_missing_keeps_only_proposals(self, model, search):
        body = self.verified_body()
        variants = (body.replace("91310000MA1234567X", "another-code"),
            body.replace("公开业务电话", "招聘公开业务电话"))
        for index, text in enumerate(variants):
            with self.subTest(text=text):
                job, snapshot = self.query("identity-negative-" + str(index))
                # Distinct URL avoids intentionally reusing the preceding fixture.
                Company.objects.filter(pk=self.company.pk).update(website=f"https://example.test/{index}")
                with patch("portal.baichuan_research_runtime.fetch_public_page", return_value=text):
                    run_query_research(job, "runtime-worker", snapshot)
                self.company.refresh_from_db()
                self.assertIsNone(self.company.phone)
        self.assertFalse(BaichuanFactRevision.objects.filter(review_status="applied").exists())

    def test_different_host_or_group_profile_never_receives_independent_identity(self):
        body = self.verified_body()
        self.assertFalse(_independent_subject(self.company, "https://other.test/", body)["identity_verified"])
        self.company.website_kind = "group_profile"
        self.assertFalse(_independent_subject(self.company, self.company.website, body)["identity_verified"])
