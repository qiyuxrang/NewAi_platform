"""One explicit Chinese-locale probe with a bounded sandbox HTML sidecar.

No install, models, application SQL, retries, engine changes or page fetching.
Only the existing owned SearXNG process may be restarted. Receipt reserves the
single authorized request before any process/source change.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from time import monotonic, sleep
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / ".runtime/baichuan-search-sandbox"
SOURCE = SANDBOX / "searxng-2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6"
RECEIPT = SANDBOX / "locale-capture-receipt.json"
NAME = "中国移动通信集团陕西有限公司"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def main():
    if RECEIPT.exists(): raise ValueError("Locale probe already reserved; no repeated query")
    local = load("locale_local", "scripts/baichuan/local_dev.py")
    caller = {key: os.environ[key] for key in ("USERNAME", "USERDOMAIN") if key in os.environ}
    record = {"kind": "baichuan_searxng_locale_capture_v1", "status": "reserved", "query_requests": 0,
              "language": "zh-CN", "model_calls": 0, "database_accessed": False, "facts_written": 0,
              "maximum_seconds": 300, "maximum_saved_html_bytes": 524288, "engine_changed": False,
              "tls_verification": True, "automatic_retries": 0, "max_redirects": 0}
    local.private_json(RECEIPT, record)
    start = monotonic()
    process = None
    received = bytearray()
    try:
        owned = load("locale_owned", "scripts/baichuan/probe_searxng_company.py")
        service = json.loads(owned.SERVICE.read_text())
        if service.get("identity") != owned.IDENTITY or service.get("sandbox") != str(SANDBOX):
            raise ValueError("Foreign service marker")
        owned.process_identity(service["process"]["pid"], expected=service["process"])
        local.private_json(SANDBOX / "before-locale-owned-service.json", service)
        target = SOURCE / "searx/search/processors/online.py"
        before = target.read_text(encoding="utf-8")
        anchor = '        response = self._send_http_request(params)\n'
        if before.count(anchor) != 1: raise ValueError("Capture patch anchor changed")
        hook = '''
        # Local one-query observation only; no transport or parser behavior change.
        if self.engine.name == "bing" and query == TARGET_NAME:
            import hashlib as _capture_hash
            import json as _capture_json
            from pathlib import Path as _CapturePath
            from urllib.parse import urlsplit as _capture_split, parse_qs as _capture_qs
            _capture_root = _CapturePath(CAPTURE_ROOT)
            _capture_body = response.content
            with (_capture_root / "locale-upstream.html").open("xb") as _capture_file:
                _capture_file.write(_capture_body[:524288])
            _capture_request = _capture_split(params["url"])
            _capture_final = _capture_split(str(response.url))
            _capture_actual_query = _capture_qs(_capture_request.query).get("q", [""])[0]
            _capture_meta = {"response_status": response.status_code,
                "original_bytes": len(_capture_body), "saved_bytes": min(len(_capture_body), 524288),
                "truncated": len(_capture_body) > 524288,
                "response_sha256": _capture_hash.sha256(_capture_body).hexdigest(),
                "request_url_sha256": _capture_hash.sha256(params["url"].encode()).hexdigest(),
                "request_host": _capture_request.hostname, "final_host": _capture_final.hostname,
                "final_url_sha256": _capture_hash.sha256(str(response.url).encode()).hexdigest(),
                "actual_q_sha256": _capture_hash.sha256(_capture_actual_query.encode()).hexdigest(),
                "actual_q_matches": _capture_actual_query == TARGET_NAME,
                "request_parameter_names": sorted(_capture_qs(_capture_request.query)),
                "setlang": _capture_qs(_capture_request.query).get("setlang"),
                "adlt": _capture_qs(_capture_request.query).get("adlt")}
            with (_capture_root / "locale-upstream-metadata.json").open("x") as _capture_file:
                _capture_json.dump(_capture_meta, _capture_file, indent=2)
'''.replace("TARGET_NAME", repr(NAME)).replace("CAPTURE_ROOT", repr(str(SANDBOX)))
        after = before.replace(anchor, anchor + hook, 1)
        compile(after, str(target), "exec")
        owned.process_identity(service["process"]["pid"], terminate=True, expected=service["process"])
        target.write_text(after, encoding="utf-8")
        record["capture_patch_sha256"] = hashlib.sha256(after.encode()).hexdigest()
        clean = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "USERNAME", "USERDOMAIN") if key in os.environ}
        clean.update(PYTHONPATH=str(SOURCE), PYTHONUTF8="1", SEARXNG_SETTINGS_PATH=str(SANDBOX / "settings.yml"),
                     TEMP=str(SANDBOX / "tmp"), TMP=str(SANDBOX / "tmp"))
        command = [str(SANDBOX / "venv/Scripts/python.exe"), "-m", "searx.webapp"]
        with (SANDBOX / "locale-server.log").open("wb") as output:
            process = subprocess.Popen(command, cwd=SOURCE, env=clean, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        service.update(process=owned.process_identity(process.pid), command=command,
                       capture_budget_receipt=str(RECEIPT))
        owned.SERVICE.write_text(json.dumps(service, indent=2))
        record["owned_pid"] = process.pid
        deadline = monotonic() + 20
        while monotonic() < deadline:
            if process.poll() is not None: raise ValueError("Owned server startup failed")
            try:
                with socket.create_connection(("127.0.0.1",18888),timeout=.2): break
            except OSError: sleep(.2)
        else: raise ValueError("Owned startup deadline")
        probe = load("locale_public_probe", "scripts/baichuan/probe_public_network.py")
        with tempfile.TemporaryDirectory(prefix="searxng-locale-",dir=ROOT / ".runtime") as directory:
            probe.configure_application(directory)
            from django.db import connection
            from django.test import override_settings
            from portal import product_web_search as web
            original_open = web._open
            class CaptureJSON:
                def __init__(self, response): self.response = response
                def __enter__(self): self.response.__enter__(); return self
                def __exit__(self,*args): return self.response.__exit__(*args)
                def __getattr__(self,key): return getattr(self.response,key)
                def read1(self,length):
                    data=self.response.read1(length);received.extend(data)
                    if len(received)>262144: raise ValueError("JSON size limit")
                    return data
            def fixed_language(request, timeout):
                parsed=urlsplit(request.full_url);values=parse_qs(parsed.query)
                if parsed.hostname!="127.0.0.1" or parsed.port!=18888 or parsed.path!="/search" or values!={"q":[NAME],"format":["json"]}:
                    raise AssertionError("Only the authorized existing provider request")
                if record["query_requests"]: raise AssertionError("One request only")
                record["query_requests"]=1
                new_url=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,parsed.query+"&"+urlencode({"language":"zh-CN"}),""))
                return CaptureJSON(original_open(Request(new_url,headers=dict(request.header_items()),method="GET"),timeout))
            def deny_sql(*args): raise AssertionError("Application SQL forbidden")
            with override_settings(PRODUCT_WEB_SEARCH_ENABLED=True,PRODUCT_WEB_SEARCH_PROVIDER="searxng",
                    PRODUCT_WEB_SEARCH_SEARXNG_URL="http://127.0.0.1:18888"), connection.execute_wrapper(deny_sql), \
                    patch.object(web,"_open",side_effect=fixed_language):
                sources=web.search_public_query(NAME)
            record.update(status="completed",result_count=len(sources),
                full_company_name_matches=sum(NAME in row["title"]+row["text"] for row in sources),
                domains=[urlsplit(row["url"]).hostname for row in sources],
                https_sources=sum(urlsplit(row["url"]).scheme=="https" for row in sources),
                pdf_sources=sum(urlsplit(row["url"]).path.lower().endswith(".pdf") for row in sources))
            os.environ.update(caller)
            if sources: local.private_json(SANDBOX / "locale-app-sources.json",{"sources":sources})
    except Exception as error:
        record.update(status="failed",error_type=type(error).__name__,error_code=getattr(error,"code",None))
    finally:
        os.environ.update(caller)
        if received:
            data=json.loads(received)
            record.update(raw_result_count=len(data.get("results",[])),engine_errors=data.get("unresponsive_engines",[]))
            local.private_json(SANDBOX / "locale-app-response.json",data)
        html=SANDBOX / "locale-upstream.html"
        if html.exists():
            body=html.read_bytes();text=body.decode("utf-8","replace")
            record.update(captured_html_bytes=len(body),html_full_name_matches=text.count(NAME),
                html_b_results_markers=len(re.findall(r'id=[\"\']b_results[\"\']',text)),
                html_b_algo_markers=len(re.findall(r'class=[\"\'][^\"\']*\bb_algo\b',text)),
                challenge_word_present=bool(re.search(r'captcha|recaptcha|verify.{0,15}human|challenge-form',text,re.I)),
                no_results_phrase_present=any(term in text for term in ("There are no results for", "没有与此相关的结果", "找不到相关结果", "没有找到")))
            record["upstream_metadata"]=json.loads((SANDBOX / "locale-upstream-metadata.json").read_text())
        record.update(elapsed_ms=round((monotonic()-start)*1000),owned_process_kept=process is not None and process.poll() is None)
        RECEIPT.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(record,ensure_ascii=False))


if __name__=="__main__": main()
