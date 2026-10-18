"""One public Chinese-name positive control; never a company-existence verdict.

Reuses the exact owned SearXNG service and existing application provider. Capture
the already received JSON for offline error/result analysis; do not fetch pages,
invoke models, issue application SQL, reinstall, retry or change engines.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from time import monotonic
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / ".runtime/baichuan-search-sandbox"
NAME = "中国移动通信集团陕西有限公司"
RECEIPT = SANDBOX / "positive-control-receipt.json"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if RECEIPT.exists():
        raise ValueError("Positive-control receipt exists; no implicit repeated search")
    owned = load("positive_owned", "scripts/baichuan/probe_searxng_company.py")
    service = json.loads(owned.SERVICE.read_text())
    if service.get("identity") != owned.IDENTITY or service.get("sandbox") != str(SANDBOX):
        raise ValueError("Owned service identity missing")
    owned.process_identity(service["process"]["pid"], expected=service["process"])
    local = load("positive_local", "scripts/baichuan/local_dev.py")
    caller = {key: os.environ[key] for key in ("USERNAME", "USERDOMAIN") if key in os.environ}
    record = {"kind": "baichuan_searxng_chinese_positive_control_v1", "status": "reserved",
        "provider": "searxng", "engine": "bing", "query_requests": 0, "model_calls": 0,
        "database_accessed": False, "facts_written": 0, "owned_pid": service["process"]["pid"],
        "query_sha256": hashlib.sha256(NAME.encode()).hexdigest(), "engine_changed": False,
        "tls_verification": True, "automatic_retries": 0, "max_redirects": 0}
    local.private_json(RECEIPT, record)
    received, sources = bytearray(), []
    start = monotonic()
    try:
        probe = load("positive_public_probe", "scripts/baichuan/probe_public_network.py")
        with tempfile.TemporaryDirectory(prefix="searxng-positive-", dir=ROOT / ".runtime") as directory:
            probe.configure_application(directory)
            from django.db import connection
            from django.test import override_settings
            from portal import product_web_search as web
            original_open = web._open
            class CapturedResponse:
                def __init__(self, response): self.response = response
                def __enter__(self):
                    self.response.__enter__()
                    record["http_status"] = self.response.status
                    return self
                def __exit__(self, *args): return self.response.__exit__(*args)
                def __getattr__(self, field): return getattr(self.response, field)
                def read1(self, length):
                    data = self.response.read1(length)
                    received.extend(data)
                    if len(received) > 262144: raise ValueError("Captured response exceeds limit")
                    return data
            def capture(request, timeout):
                parsed = urlsplit(request.full_url)
                if parsed.hostname != "127.0.0.1" or parsed.port != 18888 or parsed.path != "/search":
                    raise AssertionError("Only existing fixed loopback provider permitted")
                if record["query_requests"]:
                    raise AssertionError("One positive-control request only")
                record["query_requests"] = 1
                return CapturedResponse(original_open(request, timeout))
            def deny_sql(*args): raise AssertionError("SQL forbidden during positive control")
            with override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="searxng",
                    PRODUCT_WEB_SEARCH_SEARXNG_URL="http://127.0.0.1:18888"), connection.execute_wrapper(deny_sql), \
                    patch.object(web, "_open", side_effect=capture):
                sources = web.search_public_query(NAME)
            assert len(sources) <= 6
            record.update(status="completed", result_count=len(sources),
                full_company_name_matches=sum(NAME in row["title"] + row["text"] for row in sources),
                domains=[urlsplit(row["url"]).hostname for row in sources],
                https_sources=sum(urlsplit(row["url"]).scheme == "https" for row in sources),
                pdf_sources=sum(urlsplit(row["url"]).path.lower().endswith(".pdf") for row in sources),
                all_unverified=all(row["source_trust"] == "UNKNOWN" and row["reference_only"] for row in sources))
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__, error_code=getattr(error,"code",None))
    finally:
        os.environ.update(caller)
        record.update(elapsed_ms=round((monotonic()-start)*1000),
            received_bytes=len(received), response_sha256=hashlib.sha256(received).hexdigest())
        if received:
            try:
                data = json.loads(received)
                rows = data.get("results", [])
                record.update(raw_result_count=len(rows), engine_errors=data.get("unresponsive_engines", []),
                    raw_full_company_name_matches=sum(NAME in str(row.get("title", "")) + str(row.get("content", ""))
                                                      for row in rows),
                    json_echoes_exact_query=data.get("query") == NAME,
                    parser_dropped_all_results=bool(rows and not sources),
                    html_available_for_offline_analysis=False)
                local.private_json(SANDBOX / "positive-control-response.json", data)
            except (ValueError, TypeError):
                record["offline_json_parse_failed"] = True
        if sources:
            local.private_json(SANDBOX / "positive-control-sources.json", {"validation_label": "公开中文正向对照，非事实核实", "sources": sources})
        RECEIPT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
