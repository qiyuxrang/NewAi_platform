"""Read one owned pilot's source metadata; optionally two fixed public-name requests.

Never calls models, changes databases/facts or fetches discovered pages. The
private receipt is exclusive: this script refuses implicit network repetition.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import Request
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime/baichuan-ai-local"
PUBLIC_NAME = "陕西艺霖信息科技有限公司"
MANIFEST_ID = "3a73d8fe9b2e58d185077d73b835fd61"
RECEIPT = RUNTIME / "bing-rss-company-relevance.json"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_pilot():
    local = load("relevance_local", "scripts/baichuan/local_dev.py")
    local.environment()  # Validate the owned marker/config without Django or DB writes.
    original_query = PUBLIC_NAME + " 官网 联系方式 公开资质"
    connection = sqlite3.connect((RUNTIME / "portal.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        manifests = connection.execute("SELECT id,job_id,total_count,fields FROM portal_baichuanresearchmanifest WHERE id=?",
                                       (MANIFEST_ID,)).fetchall()
        evidence = connection.execute("SELECT id,source_type,url,access_status,locator,subject,content_hash "
            "FROM portal_baichuanevidence WHERE source_type IN ('search_index','web') ORDER BY created_at DESC LIMIT 60").fetchall()
        rows = []
        for item in evidence:
            subject, locator = json.loads(item["subject"]), json.loads(item["locator"])
            if subject.get("public_name") != PUBLIC_NAME:
                continue
            urls = locator.get("urls", []) if item["source_type"] == "search_index" else [item["url"]]
            rows.append({"evidence_id": item["id"], "source_type": item["source_type"],
                "access_status": item["access_status"], "query_hash": locator.get("query_hash"),
                "matches_reconstructed_query_hash": locator.get("query_hash") == digest(original_query),
                "error_code": locator.get("error_code", ""), "result_count": len(urls),
                "domains": [urlsplit(url).hostname for url in urls],
                "url_set_sha256": digest(json.dumps(urls)), "content_hash": item["content_hash"]})
        return {"database_mode": "read_only_query_only", "manifest_count": len(manifests),
                "manifest_id": MANIFEST_ID, "manifest_total": manifests[0]["total_count"] if manifests else None,
                "original_query_sha256": digest(original_query), "evidence": rows}
    finally:
        connection.close()


def request_variant(rss, label, parameters):
    start = monotonic()
    record = {"label": label, "query_sha256": digest(parameters["q"]), "requests": 1,
              "tls_verification": True, "fixed_host": "www.bing.com", "loopback_proxy_only": True}
    try:
        request = Request(rss.ENDPOINT + "?" + urlencode(parameters), headers={
            "User-Agent": "Baichuan-public-reference/1.0", "Accept": "application/rss+xml, application/xml",
            "Accept-Encoding": "identity"})
        with rss._open(request, 8) as response:
            record["status"] = response.status
            raw = response.read(262145)
            record.update(bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest(),
                          redirect_followed=False)
            if (response.status != 200 or len(raw) > 262144 or b"\x00" in raw
                    or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I)):
                raise ValueError("invalid_bounded_response")
            root = ElementTree.fromstring(raw.decode("utf-8-sig"))
            if root.tag != "rss" or root.get("version") != "2.0":
                raise ValueError("not_rss")
            items = root.findall("./channel/item")
            if len(items) > 50:
                raise ValueError("too_many_items")
            metrics, domains, urls = [], [], []
            for item in items:
                title = " ".join(item.find("title").itertext()) if item.find("title") is not None else ""
                description = " ".join(item.find("description").itertext()) if item.find("description") is not None else ""
                url = item.findtext("link", "")
                domains.append(urlsplit(url).hostname)
                urls.append(url)
                metrics.append({"exact_name": PUBLIC_NAME in title + description,
                    "distinctive_name": "艺霖" in title + description,
                    "title_sha256": digest(title), "snippet_sha256": digest(description)})
            channel = root.find("channel")
            channel_title = channel.findtext("title", "") if channel is not None else ""
            channel_link = channel.findtext("link", "") if channel is not None else ""
            record.update(result_count=len(items), domains=domains, url_set_sha256=digest(json.dumps(urls)),
                exact_name_matches=sum(row["exact_name"] for row in metrics),
                distinctive_name_matches=sum(row["distinctive_name"] for row in metrics),
                channel_echoes_company_name=PUBLIC_NAME in channel_title + channel_link,
                channel_title_sha256=digest(channel_title), channel_link_sha256=digest(channel_link),
                items=metrics)
    except Exception as error:
        record.update(error_type=type(error).__name__, error_code=getattr(error, "code", None))
        if hasattr(error, "close"):
            error.close()
    record["elapsed_ms"] = round((monotonic() - start) * 1000)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--two-public-comparisons", action="store_true")
    args = parser.parse_args()
    if RECEIPT.exists():
        raise ValueError("Existing relevance receipt; no implicit repetition")
    windows_identity = {key: os.environ[key] for key in ("USERNAME", "USERDOMAIN") if key in os.environ}
    report = {"kind": "baichuan_bing_company_relevance_v1", "pilot": read_pilot(),
              "database_written": False, "model_calls": 0, "fact_writes": 0, "results": []}
    if args.two_public_comparisons:
        probe = load("relevance_public_probe", "scripts/baichuan/probe_public_network.py")
        with tempfile.TemporaryDirectory(prefix="rss-relevance-", dir=ROOT / ".runtime") as directory:
            probe.configure_application(directory)
            from django.test import override_settings
            from django.db import connection
            from portal import product_bing_rss as rss
            def deny_sql(*args):
                raise AssertionError("No application SQL during comparison")
            with override_settings(PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True), connection.execute_wrapper(deny_sql):
                report["results"].append(request_variant(rss, "quoted_public_name", {"q": '"' + PUBLIC_NAME + '"', "format": "rss"}))
                report["results"].append(request_variant(rss, "quoted_name_cn_market", {"q": '"' + PUBLIC_NAME + '"',
                    "format": "rss", "cc": "CN", "mkt": "zh-CN"}))
    # Isolated Django configuration intentionally clears unrelated environment.
    # Restore only the caller identity needed for the private-file ACL, never
    # service secrets or network/proxy configuration.
    os.environ.update(windows_identity)
    local = load("relevance_local_writer", "scripts/baichuan/local_dev.py")
    local.private_json(RECEIPT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
