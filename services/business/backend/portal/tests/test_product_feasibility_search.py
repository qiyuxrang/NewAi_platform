"""Feasibility public-reference gaps, privacy, bounded calls and durable retry."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from portal import product_blueprint_knowledge as blueprint
from portal import product_knowledge_service as knowledge
from portal import product_web_search as search
from portal.product_models import DocumentTask
from portal.product_service import ProductError


PUBLIC_GUIDE = (
    "编制依据包括政策法规与适用标准规范；需求分析应论证建设规模和方案比选；"
    "实施进度应衔接招标采购和运营管理；投资估算应明确费用构成与资金来源；"
    "绩效效益评价应分析主要风险和敏感性。"
)


class FeasibilitySearchTests(SimpleTestCase):
    def test_gaps_require_retrieved_text_and_queries_never_include_private_inputs_or_invent_it(self):
        payload = {"project": "保密客户13912345678", "requirements": "社区活动场地改造"}
        coverage = search.evidence_coverage(payload, [{"title": PUBLIC_GUIDE, "text": "天气晴朗"}], feasibility=True)
        self.assertFalse(coverage["sufficient"])
        self.assertEqual(len(coverage["missing_writing_topics"]), 5)
        queries = search.public_queries(coverage)
        self.assertLessEqual(len(queries), 3)
        self.assertNotIn("保密", " ".join(queries))
        self.assertNotIn("13912345678", " ".join(queries))
        self.assertNotIn("信息化", " ".join(queries))
        covered = search.evidence_coverage(payload, [{"text": PUBLIC_GUIDE}], feasibility=True)
        self.assertTrue(covered["sufficient"])
        self.assertEqual(search.public_queries(covered), [])
        title_only_domain = search.evidence_coverage({"requirements": "防火墙"},
            [{"title": "网络安全指南", "text": PUBLIC_GUIDE}], feasibility=True)
        self.assertFalse(title_only_domain["sufficient"])
        self.assertEqual(title_only_domain["missing_domains"], ["网络与安全"])
        partial = search.evidence_coverage(payload, [{"text": PUBLIC_GUIDE.split("；投资估算")[0]}], feasibility=True)
        self.assertEqual(len(partial["missing_writing_topics"]), 2)

    def test_public_queries_validate_entire_batch_before_network_and_deduplicate_sources(self):
        queries = search.public_queries(search.evidence_coverage({}, [], feasibility=True))
        source = {"id": "web:one", "text": PUBLIC_GUIDE}
        with patch.object(search, "_provider_search", return_value=[source]) as provider:
            self.assertEqual(search.search_public_references(queries), [source])
        self.assertEqual(provider.call_count, 3)
        for invalid in ([*queries, queries[0]], [queries[0], "客户地址 可行性研究报告 编制指南 方法 适用条件"]):
            with self.subTest(queries=invalid), patch.object(search, "_provider_search") as provider, self.assertRaises(ProductError):
                search.search_public_references(invalid)
            provider.assert_not_called()

    def test_source_records_snippet_and_pending_applicability_instead_of_fulltext_or_current_policy(self):
        source = search._source({"title": "编制方法", "url": "https://example.org/guide",
                                 "content": PUBLIC_GUIDE + "长" * 5000}, "tavily", "generic", "now")
        self.assertEqual(source["fact_scope"], "PUBLIC_REFERENCE")
        self.assertEqual(source["content_kind"], "search_snippet")
        self.assertEqual(source["timeliness"], "UNKNOWN")
        self.assertEqual(source["applicability"], "PENDING_HUMAN")
        self.assertTrue(source["content_truncated"])
        self.assertEqual(len(source["text"]), 4000)
        title_only = search._source({"title": PUBLIC_GUIDE, "url": "https://example.org/title"},
                                    "searxng", "generic", "now")
        self.assertEqual(title_only["content_kind"], "search_title")
        self.assertFalse(search.evidence_coverage({}, [title_only], feasibility=True)["sufficient"])

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE=blueprint.RAGFLOW_REQUIRED)
    def test_partial_failure_persists_sources_and_retry_searches_only_remaining_gaps_then_reuses_snapshot(self):
        payload = {"project": "保密社区项目", "requirements": "场地改造", "items": []}
        revision = SimpleNamespace(pk=1, payload=payload)
        task = SimpleNamespace(pk=1, owner=Mock(), state=DocumentTask.State.RUNNING,
                               fence=2, checkpoint={}, save=Mock())
        scope = {"datasets": {"dataset": ["document"]}, "grant_version": 1}
        first = search._source({"title": "公开编制依据", "url": "https://example.org/one",
                                "content": "政策法规与标准规范"}, "tavily", "generic", "now")
        rest = search._source({"title": "公开方法", "url": "https://example.org/two",
                               "content": PUBLIC_GUIDE}, "tavily", "generic", "later")
        with patch.object(DocumentTask, "objects") as objects, \
                patch("portal.product_worker._analysis_progress"), \
                patch("portal.product_service.current_revision", side_effect=lambda *args: revision), \
                patch("portal.product_service.append_revision", return_value=SimpleNamespace(version=2)) as append, \
                patch.object(blueprint.transaction, "atomic", side_effect=lambda: nullcontext()), \
                patch.object(knowledge, "authorize", return_value=scope), \
                patch.object(knowledge, "configuration", return_value=("url", "token", "route")), \
                patch.object(knowledge, "retrieve", return_value=[]) as retrieve, \
                patch.object(blueprint, "search_public_references", side_effect=[
                    [first], ProductError("web_search_unavailable", "offline", 409)]) as public:
            objects.select_related.return_value.get.return_value = task
            objects.select_for_update.return_value.get.return_value = task
            status = blueprint.prepare_blueprint_knowledge(1, 2)
            self.assertFalse(status["evidence_ready"])
            self.assertEqual(status["web_search"]["code"], "web_search_unavailable")
            revision.payload = append.call_args.args[2]
            self.assertEqual(revision.payload["knowledge_sources"], [first])
            with self.assertRaises(ProductError):
                blueprint.require_generation_knowledge(revision.payload)
            public.side_effect = None
            public.return_value = [rest]
            status = blueprint.prepare_blueprint_knowledge(1, 2)
            self.assertTrue(status["evidence_ready"])
            self.assertNotIn("政策规范与编制依据", public.call_args.args[0][0])
            self.assertEqual(status["web_source_count"], 2)
            self.assertEqual(status["retrieval_outcome"], "no_hits")
            revision.payload = append.call_args.args[2]
            self.assertEqual(revision.payload["project"], payload["project"])
            self.assertEqual(revision.payload["blueprint_knowledge"]["authorization"], scope)
            self.assertEqual(revision.payload["blueprint_knowledge"]["sources"][0]["content_kind"], "search_snippet")
            blueprint.prepare_blueprint_knowledge(1, 2)
            self.assertEqual(public.call_count, 3)
            retrieve.assert_called_once()
            revision.payload["requirements"] += " 新输入"
            blueprint.prepare_blueprint_knowledge(1, 2)
            self.assertEqual(retrieve.call_count, 2)

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE=blueprint.PREVIEW)
    def test_preview_skips_network_and_authorization(self):
        task = SimpleNamespace(pk=1, state=DocumentTask.State.RUNNING, fence=2)
        with patch.object(DocumentTask, "objects") as objects, \
                patch("portal.product_service.current_revision", return_value=SimpleNamespace(payload={})), \
                patch.object(blueprint, "_preview_checkpoint"), \
                patch.object(knowledge, "authorize") as authorize, \
                patch.object(blueprint, "search_public_references") as public:
            objects.select_related.return_value.get.return_value = task
            status = blueprint.prepare_blueprint_knowledge(1, 2)
        self.assertEqual(status["mode"], blueprint.PREVIEW)
        authorize.assert_not_called()
        public.assert_not_called()
