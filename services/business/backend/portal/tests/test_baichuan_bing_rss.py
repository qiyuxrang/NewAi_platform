"""Synthetic fixed-host RSS transport and untrusted discovery boundaries."""
from io import BytesIO
import socket
import ssl
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request
from xml.sax.saxutils import escape

from django.test import SimpleTestCase, override_settings

from portal import product_bing_rss as rss
from portal.product_service import ProductError
from portal.product_web_search import configuration, search_public_query, search_public_references


def xml(items=None):
    items = items if items is not None else [("Public source", "https://example.org/source", "Public snippet")]
    return ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>" + "".join(
        f"<item><title>{escape(title)}</title><link>{escape(url)}</link><description>{escape(text)}</description></item>"
        for title, url, text in items) + "</channel></rss>").encode()


@override_settings(DEBUG=True, PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="bing_rss",
    PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True, PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=False)
class BingRssTests(SimpleTestCase):
    def setUp(self):
        self.rate = patch.object(rss, "_last_request_at", None)
        self.rate.start()
        self.addCleanup(self.rate.stop)

    def response(self, content=None, status=200, encoding="identity"):
        stream = BytesIO(xml() if content is None else content)
        response = Mock(status=status, read1=stream.read1, getheader=Mock(return_value=encoding))
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def run_search(self, content=None):
        with patch.object(rss, "_open", return_value=self.response(content)), patch("model_gateway.transport._resolve"):
            return search_public_query("Python official documentation")

    def error(self, code, call):
        with self.assertRaises(ProductError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_fixed_endpoint_no_token_and_untrusted_source_schema(self):
        with patch.object(rss, "_open", return_value=self.response()) as opened, patch("model_gateway.transport._resolve") as resolve:
            results = search_public_query("公开通用标准")
        request = opened.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://www.bing.com/search?q="))
        self.assertTrue(request.full_url.endswith("&format=rss"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("Proxy-authorization"))
        self.assertEqual(opened.call_args.args[1], 8)
        self.assertEqual(resolve.call_args.args[0], "example.org")
        self.assertEqual(len(results), 1)
        source = results[0]
        self.assertEqual(source["provider"], "bing_rss")
        self.assertEqual(source["content_kind"], "search_snippet")
        self.assertEqual(source["source_trust"], "UNKNOWN")
        self.assertEqual(source["fact_scope"], "PUBLIC_REFERENCE")
        self.assertTrue(source["untrusted"] and source["reference_only"] and source["discovery_only"])
        self.assertEqual(source["provider_stability"], "experimental_rss")

    def test_professional_multiple_queries_use_one_explicit_bounded_discovery(self):
        queries = ["信息化系统集成 技术设计规范 验收要求", "信息化系统集成 技术设计规范 验收要求"]
        with patch.object(rss, "_open", return_value=self.response()) as opened, patch("model_gateway.transport._resolve"):
            sources = search_public_references(queries)
        opened.assert_called_once()
        self.assertEqual(len(sources), 1)
        self.assertTrue(sources[0]["query_limited"])
        self.assertEqual(sources[0]["query_count_requested"], 2)
        self.assertEqual(sources[0]["query_count_executed"], 1)

    def test_professional_unused_query_still_requires_allowlist_before_network(self):
        with patch.object(rss, "_open") as opened:
            self.error("web_search_invalid_response", lambda: search_public_references([
                "信息化系统集成 技术设计规范 验收要求", "private material 技术设计规范 验收要求"]))
        opened.assert_not_called()

    def test_defaults_and_nonlocal_environment_never_open_network(self):
        for fields in ({"PRODUCT_WEB_SEARCH_ENABLED": False}, {"PRODUCT_WEB_SEARCH_BING_RSS_ENABLED": False}, {"DEBUG": False}):
            with self.subTest(fields=fields), override_settings(**fields), patch.object(rss, "_open") as opened:
                self.error("web_search_unconfigured", lambda: search_public_query("Python"))
                opened.assert_not_called()

    def test_dtd_entities_utf16_and_html_challenge_fail_before_dns(self):
        bodies = [b'<!DOCTYPE rss [<!ENTITY x "secret">]><rss version="2.0"><channel/></rss>',
                  b'<!DOCTYPE rss SYSTEM "file:///private"><rss version="2.0"><channel/></rss>',
                  b'<!ENTITY x SYSTEM "https://private/"><rss/>', xml().decode().encode("utf-16"),
                  b'<html><form id="challenge-form"/></html>', b'<rss version="2.0"><channel/>&unknown;</rss>']
        for body in bodies:
            with self.subTest(body=body[:20]), patch.object(rss, "_last_request_at", None), \
                    patch.object(rss, "_open", return_value=self.response(body)), patch("model_gateway.transport._resolve") as resolve:
                self.error("web_search_invalid_response", lambda: search_public_query("Python"))
                resolve.assert_not_called()

    def test_oversized_deep_many_items_and_duplicate_xml_fields_rejected(self):
        bodies = [b"x" * 262145, xml([(str(i), "https://example.org/" + str(i), "snippet") for i in range(51)]),
                  b'<rss version="2.0"><channel><item><title>x</title><title>y</title><link>https://example.org</link></item></channel></rss>',
                  b'<rss version="2.0"><channel>' + b'<x>' * 14 + b'</x>' * 14 + b'</channel></rss>',
                  b'<rss version="2.0"><channel/><channel/></rss>']
        for body in bodies:
            with self.subTest(length=len(body)), patch.object(rss, "_last_request_at", None):
                self.error("web_search_invalid_response", lambda: self.run_search(body))

    def test_six_unique_results_public_dns_checked_once_per_host(self):
        body = xml([("one", "https://example.org/0", "first"), ("one", "https://example.org/0", "second")]
                   + [(str(i), "https://example.org/" + str(i), "text") for i in range(1, 10)])
        with patch.object(rss, "_open", return_value=self.response(body)), patch("model_gateway.transport._resolve") as resolve:
            result = search_public_query("Python")
        self.assertEqual(len(result), 6)
        resolve.assert_called_once()
        self.assertEqual(result[0]["text"], "first")

    def test_empty_feed_is_not_invented_results_and_title_fallback_is_labeled(self):
        self.assertEqual(self.run_search(xml([])), [])
        with patch.object(rss, "_last_request_at", None):
            result = self.run_search(xml([("Just title", "https://example.org", "")]))
        self.assertEqual(result[0]["content_kind"], "search_title")
        self.assertEqual(result[0]["text"], "Just title")

    def test_script_html_is_not_added_as_snippet_text(self):
        source = self.run_search(xml([("Heading", "https://example.org", "<p>visible</p><script>dangerous</script>")]))[0]
        self.assertEqual(source["text"], "visible")

    def test_private_literals_mapped_addresses_and_local_dns_are_rejected(self):
        private = ["https://127.0.0.1/", "https://10.0.0.1/", "https://169.254.169.254/", "https://[::1]/",
                   "https://[::ffff:8.8.8.8]/", "https://192.168.0.2/"]
        for url in private:
            with self.subTest(url=url), patch.object(rss, "_last_request_at", None), \
                    patch.object(rss, "_open", return_value=self.response(xml([("x", url, "x")]))):
                self.error("web_search_invalid_response", lambda: search_public_query("Python"))
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.215.14", 443)),
                     (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))]
        with patch.object(rss, "_last_request_at", None), patch.object(rss, "_open", return_value=self.response()), \
                patch("model_gateway.transport.socket.getaddrinfo", return_value=addresses):
            self.error("web_search_invalid_response", lambda: search_public_query("Python"))

    def test_credential_port_scheme_and_control_character_links_rejected(self):
        for url in ("https://u:p@example.org/", "https://example.org:444/", "javascript:alert(1)",
                    "file:///private", "http://example.org:443", "https://example.org/\\x", "https://example.org/a\tb"):
            with self.subTest(url=url), patch.object(rss, "_last_request_at", None):
                self.error("web_search_invalid_response", lambda: self.run_search(xml([("x", url, "x")])))

    def test_timeout_tls_errors_and_redirect_fail_once_without_provider_details(self):
        for error in (TimeoutError("private detail"), URLError("private detail"), ssl.SSLCertVerificationError("private detail"),
                      HTTPError(rss.ENDPOINT, 302, "private detail", {}, None), HTTPError(rss.ENDPOINT, 429, "private detail", {}, None)):
            with self.subTest(error=type(error).__name__), patch.object(rss, "_last_request_at", None), \
                    patch.object(rss, "_open", side_effect=error) as opened:
                failure = self.error("web_search_unavailable", lambda: search_public_query("Python"))
                self.assertNotIn("private detail", failure.detail)
                opened.assert_called_once()

    def test_status_encoding_deadline_and_rate_budgets(self):
        for status, encoding in ((202, "identity"), (200, "gzip")):
            with patch.object(rss, "_last_request_at", None), patch.object(rss, "_open", return_value=self.response(status=status, encoding=encoding)):
                self.error("web_search_unavailable", lambda: search_public_query("Python"))
        with patch.object(rss, "_last_request_at", None), patch.object(rss, "monotonic", side_effect=[0, 0, 21]), \
                patch.object(rss, "_open", return_value=self.response()) as opened:
            self.error("web_search_unavailable", lambda: search_public_query("Python"))
            opened.assert_called_once()
        with patch.object(rss, "_last_request_at", 10), patch.object(rss, "monotonic", return_value=10.5), patch.object(rss, "_open") as opened:
            self.error("web_search_rate_limited", lambda: search_public_query("Python"))
            opened.assert_not_called()

    def test_explicit_proxy_only_loopback_no_credentials_and_no_global_open(self):
        with patch.object(rss, "getproxies") as proxies:
            self.assertEqual(rss._proxy_configuration(), {})
            proxies.assert_not_called()
        with override_settings(PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True):
            for value in ("http://user:secret@127.0.0.1:8080", "http://10.0.0.1:8080", "socks5://127.0.0.1:8080",
                          "http://127.0.0.1:8080/path", "http://127.0.0.1:8080?secret", "http://127.0.0.1", "https://127.0.0.1:8080"):
                with self.subTest(value=value), patch.object(rss, "getproxies", return_value={"https": value}):
                    self.error("web_search_unconfigured", rss._proxy_configuration)
            with patch.object(rss, "getproxies", return_value={"https": "http://localhost:8080", "http": "http://private:9"}):
                self.assertEqual(rss._proxy_configuration(), {"https": "http://127.0.0.1:8080"})
        with patch.object(rss, "build_opener") as builder:
            rss._open(Request(rss.ENDPOINT + "?q=Python&format=rss"), 8)
        handlers = builder.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsNone(handlers[1].redirect_request(None, None, None, None, None, None))
        self.assertTrue(handlers[2]._context.check_hostname)
        self.assertEqual(handlers[2]._context.verify_mode, ssl.CERT_REQUIRED)

    def test_fixed_opener_cannot_be_reused_for_other_targets(self):
        for url in ("https://evil.example/search", "http://www.bing.com/search", "https://www.bing.com:444/search",
                    "https://www.bing.com/other", "https://u@www.bing.com/search", "https://www.bing.com/search#x"):
            with self.subTest(url=url), patch.object(rss, "build_opener") as builder:
                self.error("web_search_unconfigured", lambda: rss._open(Request(url), 8))
                builder.assert_not_called()


from .base import PortalTestCase


@override_settings(DEBUG=True, PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="bing_rss",
    PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="rss-budget")
class BingResearchBudgetTests(PortalTestCase):
    def test_existing_job_budget_stops_before_provider_or_evidence_write(self):
        from portal.baichuan_assistant_models import BaichuanEvidence
        from portal.baichuan_jobs import claim_job, consume_budget, enqueue_job
        from portal.baichuan_models import Company
        from portal.baichuan_research_runtime import _search
        from portal.baichuan_service import BaichuanError
        actor = self.create_user("fictional-rss-budget", "product")
        with override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[actor.pk],
                PORTAL_BAICHUAN_WRITE_USER_IDS=[actor.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[]):
            company = Company.objects.create(name="虚构RSS预算测试企业", created_by=actor, updated_by=actor)
            queued, _ = enqueue_job(actor, kind="query", payload={}, idempotency_key="rss-budget", budget={"max_sources": 1})
            job = claim_job("rss-budget-worker", job_id=queued.pk)
            consume_budget(job.pk, "rss-budget-worker", job.fence, sources=1)
            with patch.object(rss, "_open") as opened, self.assertRaises(BaichuanError) as failure:
                _search(job, "rss-budget-worker", company, ["itss"])
            self.assertEqual(failure.exception.code, "budget_exhausted")
            opened.assert_not_called()
            self.assertEqual(BaichuanEvidence.objects.count(), 0)
            job.refresh_from_db()
            self.assertEqual(job.status, "failed")
