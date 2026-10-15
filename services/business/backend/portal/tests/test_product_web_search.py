import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from portal.product_blueprint_knowledge import prepare_blueprint_knowledge, require_generation_knowledge
from portal.product_models import DocumentTask
from portal.product_service import ProductError, append_revision, current_revision, digest
from portal.product_web_search import evidence_coverage, public_queries, search_public_query, search_public_references
from portal.product_workflow import run_product_workflow

from .base import PortalTestCase
from .test_product_feasibility_search import PUBLIC_GUIDE


@override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="tavily",
                   PRODUCT_WEB_SEARCH_TOKEN_ENV="TEST_PUBLIC_SEARCH_TOKEN")
class PublicSearchBoundaryTests(SimpleTestCase):
    def response(self, payload):
        stream = BytesIO(json.dumps(payload).encode())
        response = Mock(status=200, read1=stream.read1)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def result(self):
        return {"title": "网络设计指南", "url": "https://example.org/design", "content": "网络技术设计规范"}

    def test_queries_only_contain_fixed_categories_not_private_content(self):
        private = "绝密客户123 手机13912345678 完整清单及地址"
        payload = {"project": private, "requirements": private + "网络与视频监控", "background": private,
                   "items": [{"name": private + "光纤", "quantity": 99999}]}
        coverage = evidence_coverage(payload, [])
        queries = public_queries(coverage)
        self.assertEqual(queries, ["网络与安全 视频监控 综合布线 技术设计规范 验收要求"])
        self.assertNotIn(private, queries[0])

    def test_half_of_broad_domains_is_sufficient_without_per_equipment_hits(self):
        payload = {"requirements": "防火墙和摄像机", "items": []}
        self.assertTrue(evidence_coverage(payload, [{"title": "网络指南", "text": "网络设计"}])["sufficient"])
        self.assertEqual(evidence_coverage({"requirements": "user groups"}, [])['domains'], [])
        self.assertEqual(evidence_coverage({"requirements": "UPS供电"}, [])['domains'], ["供配电"])

    @patch.dict("os.environ", {"TEST_PUBLIC_SEARCH_TOKEN": "synthetic-key-no-real-provider"})
    def test_tavily_contract_and_public_source_provenance(self):
        with patch("portal.product_web_search._open", return_value=self.response({"results": [self.result(), self.result()]})) as opened:
            sources = search_public_references(["网络与安全 技术设计规范 验收要求"])
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.tavily.com/search")
        self.assertEqual(json.loads(request.data)["include_raw_content"], False)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["fact_scope"], "PUBLIC_REFERENCE")
        self.assertTrue(sources[0]["untrusted"])
        self.assertTrue(sources[0]["reference_only"])
        self.assertEqual(sources[0]["source_trust"], "UNKNOWN")
        self.assertIn("retrieved_at", sources[0])

    @override_settings(PRODUCT_WEB_SEARCH_PROVIDER="brave")
    @patch.dict("os.environ", {"TEST_PUBLIC_SEARCH_TOKEN": "synthetic-key-no-real-provider"})
    def test_brave_contract(self):
        row = self.result()
        row["description"] = row.pop("content")
        with patch("portal.product_web_search._open", return_value=self.response({"web": {"results": [row]}})) as opened:
            sources = search_public_references(["网络与安全 技术设计规范 验收要求"])
        self.assertTrue(opened.call_args.args[0].full_url.startswith("https://api.search.brave.com/res/v1/web/search?"))
        self.assertEqual(sources[0]["provider"], "brave")

    @override_settings(PRODUCT_WEB_SEARCH_ENABLED=False)
    def test_unconfigured_service_never_opens_network(self):
        with patch("portal.product_web_search._open") as opened, self.assertRaises(ProductError) as caught:
            search_public_references(["信息化系统集成 技术设计规范 验收要求"])
        self.assertEqual(caught.exception.code, "web_search_unconfigured")
        opened.assert_not_called()

    @patch.dict("os.environ", {"TEST_PUBLIC_SEARCH_TOKEN": "synthetic-key-no-real-provider"})
    def test_network_error_is_bounded_without_retry_or_leaking_provider_error(self):
        with patch("portal.product_web_search._open", side_effect=URLError("sensitive provider details")) as opened, self.assertRaises(ProductError) as caught:
            search_public_references(["网络与安全 技术设计规范 验收要求"])
        self.assertEqual(caught.exception.code, "web_search_unavailable")
        self.assertNotIn("sensitive", caught.exception.detail)
        opened.assert_called_once()

    @patch.dict("os.environ", {"TEST_PUBLIC_SEARCH_TOKEN": "synthetic-key-no-real-provider"})
    def test_malformed_json_and_unsafe_source_url_fail_closed(self):
        malformed = Mock(status=200, read1=Mock(side_effect=[b'{"results":[],"results":[]}', b""]))
        malformed.__enter__ = Mock(return_value=malformed)
        malformed.__exit__ = Mock(return_value=False)
        row = {**self.result(), "url": "javascript:alert(1)"}
        for response in (malformed, self.response({"results": [row]})):
            with self.subTest(response=response), patch("portal.product_web_search._open", return_value=response), self.assertRaises(ProductError) as caught:
                search_public_references(["网络与安全 技术设计规范 验收要求"])
            self.assertEqual(caught.exception.code, "web_search_invalid_response")

    @patch.dict("os.environ", {"TEST_PUBLIC_SEARCH_TOKEN": "synthetic-key-no-real-provider"})
    def test_tavily_still_rejects_any_malformed_result_row(self):
        rows = [self.result() for _ in range(6)] + [{**self.result(), "url": "javascript:alert(1)"}]
        with patch("portal.product_web_search._open", return_value=self.response({"results": rows})), \
                self.assertRaises(ProductError) as caught:
            search_public_references(["网络与安全 技术设计规范 验收要求"])
        self.assertEqual(caught.exception.code, "web_search_invalid_response")

    def test_helper_rejects_arbitrary_private_query_before_configuration_or_network(self):
        with patch("portal.product_web_search._open") as opened, self.assertRaises(ProductError):
            search_public_references(["内部项目完整清单 技术设计规范 验收要求"])
        opened.assert_not_called()


@override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="searxng",
                   PRODUCT_WEB_SEARCH_SEARXNG_URL="http://searxng:8080/base/")
class SearxngSearchTests(SimpleTestCase):
    def response(self, payload):
        stream = BytesIO(json.dumps(payload).encode())
        response = Mock(status=200, read1=stream.read1)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def row(self, suffix="one", **values):
        return {"title": "公开技术指南 " + suffix, "url": "https://example.org/" + suffix,
                "content": "网络技术设计规范", **values}

    @patch.dict("os.environ", {}, clear=True)
    def test_contract_needs_no_token_and_keeps_public_reference_provenance(self):
        with patch("portal.product_web_search._open", return_value=self.response({"results": [self.row()]})) as opened:
            sources = search_public_references(["网络与安全 技术设计规范 验收要求"])
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "http://searxng:8080/base/search?q=%E7%BD%91%E7%BB%9C%E4%B8%8E%E5%AE%89%E5%85%A8+%E6%8A%80%E6%9C%AF%E8%AE%BE%E8%AE%A1%E8%A7%84%E8%8C%83+%E9%AA%8C%E6%94%B6%E8%A6%81%E6%B1%82&format=json")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(sources[0]["provider"], "searxng")
        self.assertEqual(sources[0]["fact_scope"], "PUBLIC_REFERENCE")
        self.assertEqual(sources[0]["source_trust"], "UNKNOWN")
        self.assertTrue(sources[0]["untrusted"])

    @patch.dict("os.environ", {}, clear=True)
    def test_opted_in_question_is_forwarded_and_bad_or_empty_content_does_not_poison_results(self):
        rows = [{"title": "bad", "url": "javascript:alert(1)"},
                self.row("fallback", content=""), *[self.row(str(i)) for i in range(25)]]
        with patch("portal.product_web_search._open", return_value=self.response({"results": rows})) as opened:
            sources = search_public_query("网络设备验收标准")
        self.assertIn("q=%E7%BD%91%E7%BB%9C%E8%AE%BE%E5%A4%87%E9%AA%8C%E6%94%B6%E6%A0%87%E5%87%86", opened.call_args.args[0].full_url)
        self.assertEqual(len(sources), 6)
        self.assertEqual(sources[0]["text"], "公开技术指南 fallback")

    def test_invalid_service_urls_fail_before_network(self):
        invalid = ("http://example.com", "http://8.8.8.8", "http://user@localhost", "https://localhost/path?x=1",
                   "https://localhost/path#fragment", "https://localhost:bad", "https://localhost:65536", "https://localhost:",
                   "https://localhost/with space", "https://local\nhost")
        for url in invalid:
            with self.subTest(url=url), override_settings(PRODUCT_WEB_SEARCH_SEARXNG_URL=url), \
                    patch("portal.product_web_search._open") as opened, self.assertRaises(ProductError) as caught:
                search_public_references(["网络与安全 技术设计规范 验收要求"])
            self.assertEqual(caught.exception.code, "web_search_unconfigured")
            opened.assert_not_called()

    def test_numeric_ipv4_hostname_forms_are_not_treated_as_private_service_names(self):
        for url in ("http://2130706433", "http://0x7f000001", "http://127"):
            with self.subTest(url=url), override_settings(PRODUCT_WEB_SEARCH_SEARXNG_URL=url), \
                    patch("portal.product_web_search._open") as opened, self.assertRaises(ProductError) as caught:
                search_public_references(["网络与安全 技术设计规范 验收要求"])
            self.assertEqual(caught.exception.code, "web_search_unconfigured")
            opened.assert_not_called()

    def test_public_https_service_url_is_allowed(self):
        with override_settings(PRODUCT_WEB_SEARCH_SEARXNG_URL="https://search.example/base"), \
                patch("portal.product_web_search._open", return_value=self.response({"results": []})) as opened:
            search_public_references(["网络与安全 技术设计规范 验收要求"])
        self.assertTrue(opened.call_args.args[0].full_url.startswith("https://search.example/base/search?"))

    def test_oversized_response_is_rejected(self):
        response = Mock(status=200, read1=BytesIO(b"x" * 262145).read1)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("portal.product_web_search._open", return_value=response), self.assertRaises(ProductError) as caught:
            search_public_references(["网络与安全 技术设计规范 验收要求"])
        self.assertEqual(caught.exception.code, "web_search_invalid_response")


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="ragflow_required")
class KnowledgeWebFallbackTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("public-search-owner", "product")
        self.owner.refresh_from_db()
        self.payload = {"project": "合成测试客户名称", "requirements": "网络、视频监控和综合布线",
                        "background": "合成私有资料不得外发", "items": [], "conditions": []}
        self.task = DocumentTask.objects.create(owner=self.owner, title="合成联网检索测试",
            idempotency_key="public-search-test", payload_hash=digest(self.payload),
            state=DocumentTask.State.RUNNING, stage=DocumentTask.Stage.BLUEPRINT, pending_action="knowledge",
            fence=2, lease_until=timezone.now() + timedelta(seconds=180),
            checkpoint={"grant_version": self.owner.grant_version})
        revision = append_revision(self.task, "input", self.payload, actor=self.owner)
        self.task.input_version = revision.version
        self.task.save(update_fields=["input_version"])
        self.scope = {"datasets": {"dataset": ["document"]}, "session_version": self.owner.session_version,
                      "grant_version": self.owner.grant_version, "authority": "https://ragflow.test/api/v1/retrieval"}
        for target, value in (("authorize", self.scope), ("configuration", ("https://ragflow.test/api/v1/retrieval", "synthetic", "route"))):
            patcher = patch("portal.product_knowledge_service." + target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("portal.product_worker._analysis_progress")
        self.progress = patcher.start()
        self.addCleanup(patcher.stop)

    def rag_source(self, content="网络设计指南"):
        if content != "网络设计指南":
            content += PUBLIC_GUIDE
        return {"id": "S1", "chunk_id": "chunk", "dataset_id": "dataset", "document_id": "document",
                "title": "授权知识", "content": content}

    def web_source(self, text="视频监控设计规范与综合布线验收"):
        if text != "天气资料":
            text += PUBLIC_GUIDE
        return {"id": "web:" + "a" * 32, "provider": "tavily", "title": "公开技术指南", "text": text,
                "url": "https://example.org/design", "retrieved_at": timezone.now().isoformat(),
                "query_hash": "b" * 64, "fact_scope": "PUBLIC_REFERENCE", "reference_only": True,
                "untrusted": True, "source_trust": "UNKNOWN", "timeliness": "UNKNOWN"}

    def test_insufficient_rag_automatically_searches_public_and_persists_both_sources(self):
        with patch("portal.product_knowledge_service.retrieve", return_value=[self.rag_source()]), \
                patch("portal.product_blueprint_knowledge.search_public_references", return_value=[self.web_source()]) as web:
            result = prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertTrue(result["evidence_ready"])
        self.assertEqual(result["ragflow_source_count"], 1)
        self.assertEqual(result["web_source_count"], 1)
        query = web.call_args.args[0][0]
        self.assertIn("可行性研究报告", query)
        self.assertNotIn(self.payload["project"], query)
        web.assert_called_once()
        self.task.refresh_from_db()
        snapshot = current_revision(self.task, "input").payload
        self.assertEqual(snapshot["blueprint_knowledge"]["authorization"], self.scope)
        self.assertEqual(snapshot["knowledge_sources"][1]["fact_scope"], "PUBLIC_REFERENCE")
        self.assertEqual(snapshot["background"], self.payload["background"])
        self.assertEqual(snapshot["items"], self.payload["items"])

    def test_rag_zero_hits_public_success_preserves_no_hits_truth(self):
        with patch("portal.product_knowledge_service.retrieve", return_value=[]), \
                patch("portal.product_blueprint_knowledge.search_public_references", return_value=[self.web_source("网络与视频监控设计规范")]):
            result = prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertTrue(result["evidence_ready"])
        self.assertEqual(result["retrieval_outcome"], "no_hits")
        self.assertEqual(result["ragflow_source_count"], 0)

    def test_sufficient_rag_skips_public_search(self):
        with patch("portal.product_knowledge_service.retrieve", return_value=[self.rag_source("网络及视频监控设计")]), \
                patch("portal.product_blueprint_knowledge.search_public_references") as web:
            result = prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertTrue(result["evidence_ready"])
        self.assertEqual(result["web_search"]["status"], "skipped")
        web.assert_not_called()

    def test_network_failure_saves_rag_then_explicit_retry_reuses_authorized_rag(self):
        with patch("portal.product_knowledge_service.retrieve", return_value=[self.rag_source()]) as rag, \
                patch("portal.product_blueprint_knowledge.search_public_references", side_effect=ProductError("web_search_unavailable", "network", 409)) as web:
            result = prepare_blueprint_knowledge(self.task.pk, 2)
            self.assertFalse(result["evidence_ready"])
            self.assertEqual(result["web_search"]["status"], "blocked")
            self.task.refresh_from_db()
            payload = current_revision(self.task, "input").payload
            self.assertEqual(payload["knowledge_sources"][0]["id"], "ragflow:S1")
            with self.assertRaises(ProductError) as caught:
                require_generation_knowledge(payload)
            self.assertEqual(caught.exception.code, "web_search_unavailable")
            web.side_effect = None
            web.return_value = [self.web_source()]
            result = prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertTrue(result["evidence_ready"])
        self.assertEqual(rag.call_count, 1)
        self.assertEqual(web.call_count, 2)

    def test_valid_but_irrelevant_public_results_are_saved_and_do_not_unlock_generation(self):
        with patch("portal.product_knowledge_service.retrieve", return_value=[]), \
                patch("portal.product_blueprint_knowledge.search_public_references", return_value=[self.web_source("天气资料")]):
            result = prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertFalse(result["evidence_ready"])
        self.assertEqual(result["web_search"]["code"], "web_search_no_hits")
        self.task.refresh_from_db()
        payload = current_revision(self.task, "input").payload
        self.assertEqual(len(payload["knowledge_sources"]), 1)
        with self.assertRaises(ProductError):
            require_generation_knowledge(payload)

    def test_workflow_reports_completed_web_search_and_only_then_executes_action(self):
        execute = Mock()
        with patch("portal.product_knowledge_service.retrieve", return_value=[]), \
                patch("portal.product_blueprint_knowledge.search_public_references", return_value=[self.web_source("网络及视频监控设计")]):
            run_product_workflow(self.task.pk, 2, "00000000-0000-0000-0000-000000000009",
                                 prepare_blueprint_knowledge=prepare_blueprint_knowledge, execute_action=execute)
        execute.assert_called_once()
        self.assertEqual(self.progress.call_args.args[2:4], ("web_search", "completed"))

    def test_scope_revocation_stops_before_public_search(self):
        with patch("portal.product_knowledge_service.authorize", side_effect=ProductError("scope_revoked", "revoked", 403)), \
                patch("portal.product_blueprint_knowledge.search_public_references") as web, self.assertRaises(ProductError):
            prepare_blueprint_knowledge(self.task.pk, 2)
        web.assert_not_called()
