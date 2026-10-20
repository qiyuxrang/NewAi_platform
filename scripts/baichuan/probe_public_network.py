"""Bounded public-only network diagnostics; no models, company queries or DB.

No flag performs no outbound requests. --public-fetch makes one request through
the real pinned public-page reader. --tls-compare makes two example.org requests.
--public-search makes at most two identical generic queries (direct/system proxy),
never follows redirects, retries, solves challenges or rotates public instances.
Exception bodies, proxy addresses and credentials are deliberately omitted.
"""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import re
import ssl
import tempfile
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener, getproxies

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PAGE = "https://example.org/"
PUBLIC_SEARCH = "https://html.duckduckgo.com/html/?q=Python+official+documentation"
OTHER_PUBLIC_SEARCHES = (
    ("bing_public_rss", "https://www.bing.com/search?q=Python+official+documentation&format=rss"),
    ("baidu_public_html", "https://www.baidu.com/s?wd=Python+official+documentation"),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_probe(label, url, context, proxies):
    start = monotonic()
    row = {"label": label, "tls_verification": True, "attempts": 1}
    try:
        with build_opener(ProxyHandler(proxies), NoRedirect(), HTTPSHandler(context=context)).open(
                Request(url, headers={"User-Agent": "Baichuan-public-capability-probe/1.0"}), timeout=8) as response:
            content = response.read(262145)
            row.update(status=response.status, bytes=len(content), limit_exceeded=len(content) > 262144,
                       sha256=hashlib.sha256(content).hexdigest(),
                       result_links=content.count(b"result__a"),
                       challenge=bool(re.search(br"anomaly\.js|challenge-form|captcha", content, re.I)))
            if label == "bing_public_rss" and response.status == 200 and len(content) <= 262144:
                from xml.etree import ElementTree
                try:
                    root = ElementTree.fromstring(content)
                    items = root.findall("./channel/item") if root.tag == "rss" else []
                    row["rss_items"] = len(items)
                    row["rss_public_links"] = sum(urlsplit(item.findtext("link", "")).scheme in {"https", "http"}
                                                  for item in items)
                except (ElementTree.ParseError, ValueError):
                    row["rss_invalid"] = True
            if label == "baidu_public_html":
                text = content.decode("utf-8", "replace")
                row["challenge"] = row["challenge"] or any(value in text for value in ("百度安全验证", "请输入验证码", "访问过于频繁"))
                row["html_result_headings"] = len(re.findall(r"<h3\b", text, re.I))
            row["usable_search"] = bool(response.status == 200 and row["result_links"] and not row["challenge"])
            if label == "bing_public_rss":
                row["usable_search"] = bool(response.status == 200 and row.get("rss_public_links") and not row["challenge"])
    except Exception as error:
        reason = getattr(error, "reason", error)
        row.update(error_type=type(error).__name__, reason_type=type(reason).__name__,
                   http_status=getattr(error, "code", None), verify_code=getattr(reason, "verify_code", None))
        if isinstance(error, HTTPError):
            error.close()
    row["elapsed_ms"] = round((monotonic() - start) * 1000)
    return row


def configure_application(directory):
    spec = importlib.util.spec_from_file_location("isolated_public_probe", ROOT /
        "doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    return probe.configure(Path(directory))


def public_fetch():
    with tempfile.TemporaryDirectory(prefix="public-network-", dir=ROOT / ".runtime") as directory:
        configure_application(directory)
        from django.db import connection
        from portal.product_assistant_tools import fetch_public_page
        def deny_database(*args):
            raise AssertionError("Database access forbidden during public capability probe")
        start = monotonic()
        row = {"label": "real_pinned_public_fetch", "attempts": 1, "tls_verification": True,
               "ssrf_pinning": True, "database_accessed": False}
        try:
            with connection.execute_wrapper(deny_database):
                text = fetch_public_page(PUBLIC_PAGE)
            row.update(success="Example Domain" in text, characters=len(text),
                       sha256=hashlib.sha256(text.encode()).hexdigest())
        except Exception as error:
            row.update(success=False, error_type=type(error).__name__,
                       error_code=getattr(error, "code", None), verify_code=getattr(error, "verify_code", None))
        assert not (Path(directory) / "unused-isolated.sqlite3").exists()
        row["elapsed_ms"] = round((monotonic() - start) * 1000)
        return row


def bing_adapter():
    with tempfile.TemporaryDirectory(prefix="public-rss-", dir=ROOT / ".runtime") as directory:
        configure_application(directory)
        from django.db import connection
        from django.test import override_settings
        from portal.product_web_search import search_public_query
        def deny_database(*args):
            raise AssertionError("Database access forbidden during public capability probe")
        start = monotonic()
        row = {"label": "real_bing_rss_adapter", "provider_requests": 1,
               "tls_verification": True, "public_dns_validation": True, "database_accessed": False}
        try:
            with override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="bing_rss",
                    PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True, PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True), \
                    connection.execute_wrapper(deny_database):
                sources = search_public_query("Python official documentation")
            assert sources and len(sources) <= 6
            assert all(source["untrusted"] and source["discovery_only"] and source["reference_only"]
                       and source["source_trust"] == "UNKNOWN" and source["provider"] == "bing_rss" for source in sources)
            row.update(success=True, result_count=len(sources), source_trust="UNKNOWN", discovery_only=True,
                       source_set_sha256=hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest())
        except Exception as error:
            row.update(success=False, error_type=type(error).__name__, error_code=getattr(error, "code", None))
        assert not (Path(directory) / "unused-isolated.sqlite3").exists()
        row["elapsed_ms"] = round((monotonic() - start) * 1000)
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls-compare", action="store_true")
    parser.add_argument("--public-search", action="store_true")
    app_mode = parser.add_mutually_exclusive_group()
    app_mode.add_argument("--public-fetch", action="store_true")
    app_mode.add_argument("--bing-adapter", action="store_true")
    parser.add_argument("--other-public-search", action="store_true")
    args = parser.parse_args()
    report = {"database_accessed": False, "model_calls": 0, "company_queries": 0,
              "ssl": ssl.OPENSSL_VERSION, "results": []}
    if args.tls_compare:
        report["results"].append(request_probe("openssl_default", PUBLIC_PAGE, ssl.create_default_context(), {}))
        try:
            import truststore
            report["truststore_version"] = importlib.metadata.version("truststore")
            context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            report["results"].append(request_probe("windows_cryptoapi", PUBLIC_PAGE, context, {}))
        except ImportError:
            report["results"].append({"label": "windows_cryptoapi", "not_run": "truststore_unavailable"})
    if args.public_search:
        for label, proxies in (("ddg_direct", {}), ("ddg_system_proxy", getproxies())):
            report["results"].append(request_probe(label, PUBLIC_SEARCH, ssl.create_default_context(), proxies))
    if args.public_fetch:
        report["results"].append(public_fetch())
    if args.bing_adapter:
        report["results"].append(bing_adapter())
    if args.other_public_search:
        for label, url in OTHER_PUBLIC_SEARCHES:
            report["results"].append(request_probe(label, url, ssl.create_default_context(), getproxies()))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
