"""Real, bounded OCR edge/concurrency and disposable SQLite lock measurements.

No deployed settings, model, network, or enterprise database are used. Existing
PDF/OCR libraries are reused; PyMuPDF is fixture/render tooling only.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def scanned_pdf(path, *, rotation=0, blur=0, pages=1):
    import fitz
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 40)
    document = fitz.open()
    for number in range(1, pages + 1):
        image = Image.new("RGB", (1200, 360), "white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 45), "虚构验收企业：投标人须具备 ITSS 二级", fill="black", font=font)
        draw.text((40, 130), "制造商 ISO9001 仅为优先项", fill="black", font=font)
        draw.text((40, 215), f"SYNTHETIC EDGE PAGE {number:02d}", fill="black", font=font)
        if blur:
            old = image
            image = image.filter(ImageFilter.GaussianBlur(blur))
            old.close()
        if rotation:
            old = image
            image = image.rotate(rotation, expand=True, fillcolor="white")
            old.close()
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        width, height = image.size
        document.new_page(width=width / 2, height=height / 2).insert_image(
            fitz.Rect(0, 0, width / 2, height / 2), stream=buffer.getvalue())
        image.close()
    document.save(str(path))
    # Visual inspection artifact independent of native text extraction.
    document[0].get_pixmap(matrix=fitz.Matrix(1, 1)).save(str(path.with_suffix(".png")))
    document.close()
    return path.read_bytes()


def encrypted_pdf(path):
    import fitz
    document = fitz.open()
    document.new_page().insert_text((40, 60), "SYNTHETIC PASSWORD PROTECTED DOCUMENT")
    document.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
                  owner_pw="fictional-owner-only", user_pw="fictional-password-only")
    document.close()
    # Inspect the fixture with its known password; the parser receives no password.
    document = fitz.open(str(path))
    assert document.needs_pass and document.authenticate("fictional-password-only")
    document[0].get_pixmap().save(str(path.with_suffix(".png")))
    document.close()
    return path.read_bytes()


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def win_resources(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    if not get_memory(wintypes.HANDLE(int(handle)), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    times = [wintypes.FILETIME() for _ in range(4)]
    get_times = kernel.GetProcessTimes
    get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    get_times.restype = wintypes.BOOL
    if not get_times(wintypes.HANDLE(int(handle)), *(ctypes.byref(item) for item in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = lambda item: (item.dwHighDateTime << 32) | item.dwLowDateTime
    return {"peak_working_set_bytes": counters.PeakWorkingSetSize,
            "working_set_bytes": counters.WorkingSetSize,
            "peak_pagefile_bytes": counters.PeakPagefileUsage,
            "cpu_seconds": round((ticks(times[2]) + ticks(times[3])) / 10_000_000, 6)}


def sqlite_contender(database, release, report):
    held = threading.Event()
    released = threading.Event()
    def holder():
        connection = sqlite3.connect(database, timeout=1)
        start = time.monotonic()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE counter SET value=value+1")
            held.set()
            assert release.wait(110), "OCR group must release the disposable write lock"
            connection.execute("INSERT INTO events VALUES ('holder')")
            connection.commit()
            report["holder"] = {"status": "committed", "elapsed_seconds": round(time.monotonic() - start, 4)}
        finally:
            connection.close()
            released.set()
    def writer():
        assert held.wait(5)
        connection = sqlite3.connect(database, timeout=.2)
        start = time.monotonic()
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                assert "locked" in str(error)
                report["contended_attempt"] = {"status": "database_locked", "elapsed_seconds": round(time.monotonic() - start, 4)}
            else:
                raise AssertionError("The second writer must not enter the held transaction")
            assert released.wait(110)
            start = time.monotonic()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE counter SET value=value+1")
            connection.execute("INSERT INTO events VALUES ('retry')")
            connection.commit()
            report["single_retry"] = {"status": "committed", "elapsed_seconds": round(time.monotonic() - start, 4)}
        finally:
            connection.close()
    holder_thread = threading.Thread(target=holder)
    writer_thread = threading.Thread(target=writer)
    holder_thread.start()
    writer_thread.start()
    assert held.wait(5)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as reader:
        start = time.monotonic()
        assert reader.execute("SELECT value FROM counter").fetchone()[0] == 0
        report["reader_during_reserved_lock"] = {"value": 0, "elapsed_seconds": round(time.monotonic() - start, 4)}
    return holder_thread, writer_thread


def process_tree_resources(roots):
    """Include the real interpreter behind Windows venv redirector processes."""
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    selected = set(roots)
    while True:
        expanded = selected | {pid for pid, parent in parents.items() if parent in selected}
        if expanded == selected:
            break
        selected = expanded
    rows = []
    for pid in selected:
        handle = kernel.OpenProcess(0x410, False, pid)
        if not handle:
            continue  # Process may have exited between snapshot and OpenProcess.
        try:
            rows.append({"pid": pid, "parent_pid": parents.get(pid),
                "is_redirector_root": pid in roots, **win_resources(handle)})
        except OSError:
            pass
        finally:
            kernel.CloseHandle(handle)
    return rows


def execute(output):
    spec = importlib.util.spec_from_file_location("existing_capacity_probe", HERE / "probe_file_limits.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    output.mkdir()
    report = {"task": "AI-T16", "complete": False, "python": sys.version.split()[0],
        "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
        "target_database_accessed": False, "model_calls": 0, "network_calls": 0,
        "cases": [], "processes": [], "limits": {"parser_wall_seconds": 90,
        "outer_wall_seconds": 180, "concurrent_parser_slots_per_process": 2,
        "omp_threads_per_child": 2, "ocr_intra_op_threads": 2, "ocr_inter_op_threads": 1,
        "hard_rss_limit_bytes": None, "input_bytes": 20 * 1024 * 1024,
        "output_bytes": 8 * 1024 * 1024, "pages": 100, "ocr_pages": 12,
        "image_pixels": 24_000_000}, "sqlite_lock": {"scope": "raw SQLite transactions, not business worker scheduling"}}
    active, peak_active, process_lock = set(), [0], threading.Lock()
    two_started = threading.Event()
    original_popen = subprocess.Popen
    monitor_stop = threading.Event()
    sampled, aggregate_peak = {}, [0]
    def monitor():
        while not monitor_stop.wait(.1):
            with process_lock:
                roots = set(active)
            if roots:
                rows = process_tree_resources(roots)
                aggregate_peak[0] = max(aggregate_peak[0], sum(row["working_set_bytes"] for row in rows))
                for row in rows:
                    previous = sampled.get(row["pid"], {})
                    row["peak_working_set_bytes"] = max(row["peak_working_set_bytes"], previous.get("peak_working_set_bytes", 0))
                    sampled[row["pid"]] = row
    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.start()
    class ObservedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.probe_start = time.monotonic()
            with process_lock:
                active.add(self.pid)
                peak_active[0] = max(peak_active[0], len(active))
                if len(active) == 2:
                    two_started.set()
        def __exit__(self, *args):
            try:
                self.wait(timeout=5)
                row = {"pid": self.pid, "returncode": self.returncode,
                       "elapsed_seconds": round(time.monotonic() - self.probe_start, 4),
                       **win_resources(self._handle)}
                with process_lock:
                    report["processes"].append(row)
            finally:
                with process_lock:
                    active.discard(self.pid)
                super().__exit__(*args)
    subprocess.Popen = ObservedPopen
    release = threading.Event()
    database_threads = []
    try:
        with tempfile.TemporaryDirectory(prefix="baichuan-AI-T16-ocr-", dir=REPO / ".runtime") as temporary:
            directory = Path(temporary)
            helper.configure(directory)
            from django.conf import settings
            from django.db import connections
            from django.test import override_settings
            from portal.product_intake import run_parser
            from portal.product_storage import StorageError
            import importlib.metadata as metadata
            report["versions"] = {name: metadata.version(name) for name in ("Django", "pypdf", "Pillow", "PyMuPDF")}
            report["ocr_python"] = str(helper.OCR_PYTHON.relative_to(REPO))
            def measure(case, content, *, filename=None):
                start = time.monotonic()
                row = {"case": case, "input_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                try:
                    parsed = run_parser(filename or (case + ".pdf"), content)
                except StorageError as error:
                    row.update(error_code=error.code, error_detail=error.detail)
                else:
                    row.update(status=parsed["status"], method=parsed["method"], warnings=parsed["warnings"],
                        blocks=parsed["blocks"], character_count=parsed["character_count"], truncated=parsed["truncated"])
                    assert parsed["status"] != "completed", "Image OCR cannot claim verified/native completion"
                    assert all(block.get("location", {}).get("page") is not None for block in parsed["blocks"])
                    if parsed["blocks"]:
                        assert any(w["code"] == "ocr_review_required" for w in parsed["warnings"])
                row["elapsed_seconds"] = round(time.monotonic() - start, 4)
                with process_lock:
                    report["cases"].append(row)
                print(json.dumps({key: row[key] for key in ("case", "elapsed_seconds", "status", "error_code") if key in row}), flush=True)
                return row
            with override_settings(PRODUCT_STORAGE_ROOT=directory / "private", PRODUCT_PARSER_PYTHON=str(helper.OCR_PYTHON),
                    PRODUCT_OCR_ENABLED=True, PRODUCT_PARSE_TIMEOUT_SECONDS=90):
                rotated = scanned_pdf(output / "rotated-90.pdf", rotation=90)
                blurred = scanned_pdf(output / "blurred-radius-8.pdf", blur=8)
                encrypted = encrypted_pdf(output / "encrypted.pdf")
                corrupt = b"%PDF-1.7\nTHIS IS A DELIBERATELY BROKEN SYNTHETIC FILE\n%%EOF"
                with (output / "corrupt.pdf").open("xb") as stream:
                    stream.write(corrupt)
                row = measure("rotated_90", rotated)
                assert "error_code" not in row
                normalized = "".join("".join(block["text"].split()) for block in row["blocks"])
                assert "ITSS二级" in normalized and "制造商ISO9001仅为优先项" in normalized
                row = measure("blurred_radius_8", blurred)
                assert "error_code" not in row and row["status"] == "failed" and not row["blocks"]
                assert {warning["code"] for warning in row["warnings"]} == {"image_no_text", "no_text"}
                row = measure("encrypted_no_password", encrypted)
                assert row.get("error_code") == "encrypted_document"
                row = measure("corrupt_pdf", corrupt)
                assert row.get("error_code") == "invalid_document"
                first = scanned_pdf(output / "concurrent-a.pdf", pages=3)
                second = scanned_pdf(output / "concurrent-b.pdf", pages=3)
                database = directory / "synthetic-lock.sqlite3"
                with closing(sqlite3.connect(database)) as connection:
                    connection.executescript("CREATE TABLE counter(value INTEGER);INSERT INTO counter VALUES(0);CREATE TABLE events(value TEXT UNIQUE);")
                database_threads = list(sqlite_contender(database, release, report["sqlite_lock"]))
                two_started.clear()
                try:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [executor.submit(measure, "concurrent_a", first), executor.submit(measure, "concurrent_b", second)]
                        assert two_started.wait(10), "Both real parser subprocesses must overlap"
                        busy = measure("third_request_refused", first)
                        assert busy.get("error_code") == "parser_busy"
                        for future in futures:
                            row = future.result(timeout=100)
                            assert row.get("status") == "needs_review" and row.get("method") == "ocr"
                            assert sorted({block["location"]["page"] for block in row["blocks"]}) == [1, 2, 3]
                finally:
                    release.set()
                    for thread in database_threads:
                        thread.join(5)
                        assert not thread.is_alive()
                with closing(sqlite3.connect(database)) as connection:
                    assert connection.execute("SELECT value FROM counter").fetchone()[0] == 2
                    assert connection.execute("SELECT value FROM events ORDER BY value").fetchall() == [("holder",), ("retry",)]
                    report["sqlite_lock"]["quick_check"] = connection.execute("PRAGMA quick_check").fetchone()[0]
                assert report["sqlite_lock"]["quick_check"] == "ok"
                assert "contended_attempt" in report["sqlite_lock"] and "single_retry" in report["sqlite_lock"]
                assert connections["default"].connection is None
                assert not (directory / "unused-isolated.sqlite3").exists()
                assert not list((directory / "private" / ".parsing").iterdir())
                report["parser_staging_empty"] = True
                report["django_database_opened"] = False
            report["peak_active_parser_children"] = peak_active[0]
            assert peak_active[0] == 2 and len(report["processes"]) == 6
            report["sampled_process_tree"] = list(sampled.values())
            report["sampled_aggregate_peak_working_set_bytes"] = aggregate_peak[0]
            report["memory_sampling_interval_seconds"] = .1
            report["peak_child_working_set_bytes"] = max(row["peak_working_set_bytes"] for row in sampled.values())
            assert any(not row["is_redirector_root"] and row["peak_working_set_bytes"] > 10_000_000 for row in sampled.values())
        report["temporary_database_removed"] = not directory.exists()
        report["complete"] = True
    finally:
        release.set()
        monitor_stop.set()
        monitor_thread.join(3)
        subprocess.Popen = original_popen
        write_new(output / "receipt.json", report)
    print(json.dumps({"complete": report["complete"], "cases": len(report["cases"]),
        "peak_active_parser_children": report["peak_active_parser_children"],
        "peak_child_working_set_bytes": report["peak_child_working_set_bytes"],
        "temporary_database_removed": report["temporary_database_removed"]}), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    assert output.is_relative_to((REPO / ".runtime").resolve()) and not output.exists()
    assert output.parent.is_dir()
    if args.child:
        execute(output)
    else:
        with subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--output", str(output), "--child"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            try:
                stdout, _ = process.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                # Only this newly spawned probe and its descendants; never a
                # deployed process. Windows venv redirectors require tree kill.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                raise RuntimeError("Probe wall limit reached; incomplete private fixtures retained") from None
            print(stdout, end="", flush=True)
            raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
