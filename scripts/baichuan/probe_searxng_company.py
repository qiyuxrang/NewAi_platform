"""Exactly one authorized public-company query via the existing app provider.

Uses only the already installed ignored sandbox. No installation, models,
application SQL or page fetching. Keeps its owned loopback process for takeover.
"""
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from time import monotonic, sleep
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / ".runtime/baichuan-search-sandbox"
SOURCE = SANDBOX / "searxng-2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6"
RECEIPT = SANDBOX / "company-app-search-receipt.json"
SERVICE = SANDBOX / "owned-service.json"
PUBLIC_NAME = "陕西艺霖信息科技有限公司"
IDENTITY = "baichuan-owned-searxng-sandbox-v1"


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def process_identity(pid, *, terminate=False, expected=None):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x1000 | (0x0001 if terminate else 0), False, pid)
    if not handle:
        raise OSError("Owned process is unavailable")
    try:
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)):
            raise OSError("Process identity unavailable")
        size, image = wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise OSError("Process image unavailable")
        identity = {"pid": pid, "created_filetime": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                    "executable": image.value}
        if expected is not None and identity != expected:
            raise ValueError("Owned process identity changed; refusing termination")
        if terminate:
            kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            if not kernel.TerminateProcess(handle, 0):
                raise OSError("Owned process termination failed")
        return identity
    finally:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)


def stop():
    value = json.loads(SERVICE.read_text())
    if value.get("identity") != IDENTITY or value.get("sandbox") != str(SANDBOX):
        raise ValueError("Foreign service marker")
    process_identity(value["process"]["pid"], terminate=True, expected=value["process"])
    print(json.dumps({"stopped_owned_pid": value["process"]["pid"]}))


def bare_name():
    """One separately authorized contrast; reuse the exact owned process."""
    path = SANDBOX / "company-app-bare-name-receipt.json"
    if path.exists():
        raise ValueError("Bare-name query already reserved; no retry")
    previous = json.loads(RECEIPT.read_text())
    service = json.loads(SERVICE.read_text())
    if previous.get("query_requests") != 1 or service.get("identity") != IDENTITY:
        raise ValueError("Prior bounded query/owned identity missing")
    process_identity(service["process"]["pid"], expected=service["process"])
    local = module("bare_search_local", "scripts/baichuan/local_dev.py")
    record = {"kind": "baichuan_searxng_company_bare_v1", "provider": "searxng", "query_requests": 1,
              "total_company_requests_this_unit": 2, "model_calls": 0, "database_accessed": False,
              "facts_written": 0, "owned_pid": service["process"]["pid"], "status": "reserved"}
    local.private_json(path, record)
    caller = {key: os.environ[key] for key in ("USERNAME", "USERDOMAIN") if key in os.environ}
    start = monotonic()
    try:
        probe = module("bare_search_probe", "scripts/baichuan/probe_public_network.py")
        with tempfile.TemporaryDirectory(prefix="searxng-bare-", dir=ROOT / ".runtime") as directory:
            probe.configure_application(directory)
            from django.db import connection
            from django.test import override_settings
            from portal.product_web_search import search_public_query
            def deny_sql(*args): raise AssertionError("Application SQL forbidden")
            with override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="searxng",
                    PRODUCT_WEB_SEARCH_SEARXNG_URL="http://127.0.0.1:18888"), connection.execute_wrapper(deny_sql):
                sources = search_public_query(PUBLIC_NAME)
            assert len(sources) <= 6
            record.update(status="completed", result_count=len(sources),
                query_sha256=hashlib.sha256(PUBLIC_NAME.encode()).hexdigest(),
                source_set_sha256=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),
                full_company_name_matches=sum(PUBLIC_NAME in row["title"] + row["text"] for row in sources),
                domains=[urlsplit(row["url"]).hostname for row in sources],
                https_sources=sum(urlsplit(row["url"]).scheme == "https" for row in sources),
                pdf_sources=sum(urlsplit(row["url"]).path.lower().endswith(".pdf") for row in sources),
                all_unverified=all(row["source_trust"] == "UNKNOWN" and row["reference_only"] for row in sources))
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__, error_code=getattr(error,"code",None))
    finally:
        os.environ.update(caller)
        record["elapsed_ms"] = round((monotonic()-start)*1000)
        path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(record,ensure_ascii=False))


def main():
    if RECEIPT.exists() or SERVICE.exists():
        raise ValueError("Existing one-query/service receipt; no implicit restart or external retry")
    local = module("company_search_local", "scripts/baichuan/local_dev.py")
    clean = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "USERNAME", "USERDOMAIN") if key in os.environ}
    caller = {key: os.environ[key] for key in ("USERNAME", "USERDOMAIN") if key in os.environ}
    clean.update(PYTHONPATH=str(SOURCE), PYTHONUTF8="1", SEARXNG_SETTINGS_PATH=str(SANDBOX / "settings.yml"),
                 TEMP=str(SANDBOX / "tmp"), TMP=str(SANDBOX / "tmp"))
    command = [str(SANDBOX / "venv/Scripts/python.exe"), "-m", "searx.webapp"]
    with (SANDBOX / "owned-server.log").open("wb") as output:
        process = subprocess.Popen(command, cwd=SOURCE, env=clean, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    service = {"identity": IDENTITY, "sandbox": str(SANDBOX), "process": process_identity(process.pid),
               "command": command, "cwd": str(SOURCE), "bind": "127.0.0.1", "port": 18888,
               "stop_command": ".runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_searxng_company.py --stop"}
    local.private_json(SERVICE, service)
    deadline = monotonic() + 20
    while monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError("Owned server startup failed; no search issued")
        try:
            with socket.create_connection(("127.0.0.1", 18888), timeout=.2): break
        except OSError: sleep(.2)
    else:
        raise ValueError("Owned startup deadline; no search issued")
    report = {"kind": "baichuan_searxng_company_app_v1", "provider": "searxng", "query_requests": 1,
              "model_calls": 0, "database_accessed": False, "facts_written": 0, "tls_verification": True,
              "browser_tls_impersonation": False, "automatic_retries": 0, "max_redirects": 0,
              "owned_service_receipt": str(SERVICE), "owned_pid": process.pid}
    # Reserve the one explicit query before any application/network execution.
    local.private_json(RECEIPT, {**report, "status": "reserved"})
    start = monotonic()
    try:
        probe = module("company_search_probe", "scripts/baichuan/probe_public_network.py")
        with tempfile.TemporaryDirectory(prefix="searxng-app-", dir=ROOT / ".runtime") as directory:
            probe.configure_application(directory)
            from django.db import connection
            from django.test import override_settings
            from portal.product_web_search import search_public_query
            def deny_sql(*args):
                raise AssertionError("Application SQL forbidden during public company search")
            query = PUBLIC_NAME + " 官网 联系方式 公开资质"
            with override_settings(PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="searxng",
                    PRODUCT_WEB_SEARCH_SEARXNG_URL="http://127.0.0.1:18888"), connection.execute_wrapper(deny_sql):
                sources = search_public_query(query)
            assert len(sources) <= 6
            report.update(status="completed", result_count=len(sources),
                query_sha256=hashlib.sha256(query.encode()).hexdigest(),
                source_set_sha256=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),
                full_company_name_matches=sum(PUBLIC_NAME in row["title"] + row["text"] for row in sources),
                domains=[urlsplit(row["url"]).hostname for row in sources],
                https_sources=sum(urlsplit(row["url"]).scheme == "https" for row in sources),
                pdf_sources=sum(urlsplit(row["url"]).path.lower().endswith(".pdf") for row in sources),
                all_unverified=all(row["source_trust"] == "UNKNOWN" and row["reference_only"] for row in sources))
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error_code=getattr(error,"code",None))
    finally:
        os.environ.update(caller)
        report.update(elapsed_ms=round((monotonic()-start)*1000), owned_process_kept=process.poll() is None)
        RECEIPT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true")
    mode.add_argument("--bare-name", action="store_true")
    args = parser.parse_args()
    stop() if args.stop else bare_name() if args.bare_name else main()
