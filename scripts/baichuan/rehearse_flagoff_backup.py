"""AI-AC16: offline flag-off rehearsal on an online backup, never the live DB.

Run with the existing company-test Python and --output NEW ignored directory.
No migration/unapply, worker, HTTP server, external model or frontend is started.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OWNED = ROOT / ".runtime/baichuan-ai-local"
SOURCE_SHA = "220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=lambda x: x.hex() if isinstance(x, bytes) else str(x)).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def private_directory(path):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / ".runtime").resolve()) or path == OWNED.resolve():
        raise ValueError("Output must be a new private .runtime child")
    if path.exists() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Refusing existing output or symlink")
    path.mkdir(parents=True, exist_ok=False)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
        import re
        sid = re.search(r"S-1-[0-9-]+", identity).group(0)
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F"],
                       check=True, capture_output=True)
    else:
        path.chmod(0o700)
    return path


def backup(source, target):
    started = time.monotonic()
    captured_at = datetime.now(timezone.utc).isoformat()
    with target.open("xb"):
        pass
    def progress(*unused):
        if time.monotonic() - started > 20:
            raise TimeoutError("Online backup exceeded 20 seconds")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=2)) as original:
        original.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(target)) as copied:
            original.backup(copied, pages=256, progress=progress, sleep=0.05)
            assert copied.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    return {"sha256": file_hash(target), "quick_check": "ok", "started_at": captured_at,
            "completed_at": datetime.now(timezone.utc).isoformat(), "seconds": round(time.monotonic() - started, 4)}


def snapshot(connection):
    result = {}
    for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        columns = connection.execute('PRAGMA table_info("' + table + '")').fetchall()
        names = [c[1] for c in columns]
        pk = [names.index(c[1]) for c in sorted(columns, key=lambda c: c[5]) if c[5]]
        rows = connection.execute('SELECT * FROM "' + table + '"').fetchall()
        values = {canonical([row[i] for i in pk] if pk else row).decode(): digest(row) for row in rows}
        assert len(values) == len(rows)
        result[table] = {"columns": names, "rows": values, "count": len(rows), "sha256": digest(values)}
    return result


def clean_environment(database, output):
    env = {key: value for key, value in os.environ.items() if not key.startswith(
        ("PORTAL_", "PLATFORM_", "MODEL_GATEWAY_", "COMPANY_TRIAL_", "PG", "DATABASE_URL"))}
    env.update(PORTAL_DEBUG="1", PORTAL_HTTPS="0", PORTAL_SECRET_KEY="isolated-flagoff-rehearsal-" + "x" * 48,
        PORTAL_SQLITE_PATH=str(database), PORTAL_ALLOWED_HOSTS="testserver,localhost,127.0.0.1",
        DJANGO_SETTINGS_MODULE="config.settings", PYTHONPATH=str(ROOT / "services/business"),
        PORTAL_BAICHUAN_SCOPE_CONFIRMED="1", PORTAL_BAICHUAN_READ_ROLE_CODES="product,general_manager",
        PORTAL_BAICHUAN_WRITE_ROLE_CODES="product,general_manager", PORTAL_BAICHUAN_ASSISTANT_ENABLED="0",
        PORTAL_BAICHUAN_RESEARCH_ENABLED="0", PORTAL_BAICHUAN_FACT_WRITE_ENABLED="0",
        PORTAL_PRODUCT_MODEL_CALLS_ALLOWED="0", PORTAL_AGENT_ENABLED="0",
        PORTAL_BAICHUAN_ASSISTANT_SCOPE="baichuan-ai-local", PORTAL_PRODUCT_OCR_ENABLED="0",
        PORTAL_BAICHUAN_STORAGE_ROOT=str(output / "private-storage"),
        PORTAL_PRODUCT_STORAGE_ROOT=str(output / "product-storage"), PORTAL_TENDER_STORAGE_ROOT=str(output / "tender-storage"))
    return env


def child(output):
    database = (output / "working.sqlite3").resolve(strict=True)
    assert Path(os.environ["PORTAL_SQLITE_PATH"]).resolve() == database
    assert database != (OWNED / "portal.sqlite3").resolve()
    attempts, local_probes = [], []
    def deny(*args, **kwargs):
        import traceback
        attempts.append({"stack": traceback.format_stack(limit=7)})
        raise AssertionError("Network and model execution forbidden in backup rehearsal")
    def deny_local_probe(*args, **kwargs):
        import traceback
        local_probes.append({"stack": traceback.format_stack(limit=7)})
        raise AssertionError("Even local socket binding is blocked")
    # Keep socket class identity intact for ssl imports; block DNS and all outbound transports.
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
        setattr(socket, name, deny)
    for name in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, name, deny)
    for name in ("bind", "listen"):
        setattr(socket.socket, name, deny_local_probe)
    sys.path[:0] = [str(ROOT / "services/business/backend"), str(ROOT / "services/business")]
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection, connections
    from django.db.backends.signals import connection_created
    from django.db.migrations.executor import MigrationExecutor
    from django.test import override_settings
    from rest_framework.test import APIRequestFactory, force_authenticate
    from portal import baichuan_api as api, baichuan_assistant_api as assistant_api, model_gateway
    from portal.baichuan_service import COMPANY_FIELDS, company_detail, can_access
    from portal.baichuan_models import Company, CompanyQualification
    from portal.models import User
    model_gateway.generate_for_use = deny
    def assert_copy(sender, connection, **kwargs):
        assert Path(connection.settings_dict["NAME"]).resolve() == database
    connection_created.connect(assert_copy, weak=False)
    assert_copy(None, connection)
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    assert not pending, "Pending migration: cannot claim current-schema rollback safety"
    raw = connection.connection
    baseline = snapshot(raw)
    assert Company.objects.count() == 1283
    assert CompanyQualification.objects.count() == 1460
    actors = {}
    for role in ("product", "general_manager"):
        actors[role] = next(user for user in User.objects.filter(is_active=True, must_change_password=False, roles__code=role).order_by("pk") if can_access(user, True))
    factory = APIRequestFactory()
    def call(view, method, path, actor, data=None, **kwargs):
        request = getattr(factory, method)(path, data=data or {}, format="json")
        force_authenticate(request, user=actor)
        response = view(request, **kwargs)
        response.render()
        return response
    checks = []
    for role, actor in actors.items():
        listed = call(api.companies, "get", "/api/baichuan/companies/", actor, {"page_size": 100})
        assert listed.status_code == 200 and listed.data["total"] == 1283
        expected = set(str(pk) for pk in CompanyQualification.objects.filter(category="electronic", status="PRESENT", grade="2").values_list("company_id", flat=True))
        actual, page = set(), 1
        while True:
            filtered = call(api.companies, "get", "/api/baichuan/companies/", actor,
                            {"electronic": "2", "page_size": 100, "page": page})
            assert filtered.status_code == 200 and filtered.data["total"] == len(expected)
            actual.update(item["id"] for item in filtered.data["items"])
            if not filtered.data["has_more"]:
                break
            page += 1
        assert actual == expected
        checks.append({"role": role, "list_total": 1283, "exact_electronic_grade_2": len(actual), "pages": page})
    actor = actors["product"]
    target = Company.objects.filter(qualifications__isnull=False).order_by("id").first()
    assert target
    detail = call(api.company, "get", "/api/baichuan/company/", actor, company_id=target.pk)
    assert detail.status_code == 200
    before_detail = detail.data
    payload = {"company": {key: before_detail["company"][key] for key in COMPANY_FIELDS},
               "qualifications": before_detail["qualifications"], "people": before_detail["people"],
               "expected_version": target.version}
    old_company = dict(Company.objects.filter(pk=target.pk).values().get())
    marker = "[ISOLATED COPY ONLY: AC16 manual save survives flag rollback]"
    payload["company"]["description"] = (payload["company"]["description"] or "") + "\n" + marker
    saved = call(api.company, "put", "/api/baichuan/company/", actor, payload, company_id=target.pk)
    assert saved.status_code == 200, {"save_status": saved.status_code, "code": saved.data.get("code"), "errors": saved.data.get("errors")}
    assert saved.data["company"]["version"] == old_company["version"] + 1
    assert saved.data["company"]["description"].endswith(marker)
    assert saved.data["qualifications"] == before_detail["qualifications"]
    assert saved.data["people"] == before_detail["people"]
    # Replaying the old full snapshot must fail, retaining the subsequent manual value.
    stale = call(api.company, "put", "/api/baichuan/company/", actor, payload, company_id=target.pk)
    assert stale.status_code == 409 and stale.data["code"] == "version_conflict"
    disabled = call(assistant_api.conversations, "post", "/api/baichuan/assistant/conversations/", actor)
    assert disabled.status_code == 503 and disabled.data["code"] == "assistant_unavailable"
    after_company = Company.objects.filter(pk=target.pk).values().get()
    allowed = {"description", "version", "updated_at", "updated_by_id"}
    assert {k: v for k, v in old_company.items() if k not in allowed} == {k: v for k, v in after_company.items() if k not in allowed}
    # Re-enable only inside this isolated process; do not run work. No snapshot restore.
    with override_settings(BAICHUAN_ASSISTANT_ENABLED=True):
        recovered = call(api.company, "get", "/api/baichuan/company/", actors["general_manager"], company_id=target.pk)
        assert recovered.status_code == 200 and recovered.data["company"]["description"].endswith(marker)
        assert recovered.data["company"]["version"] == old_company["version"] + 1
    assert not settings.BAICHUAN_ASSISTANT_ENABLED and not settings.BAICHUAN_RESEARCH_ENABLED and not settings.BAICHUAN_FACT_WRITE_ENABLED
    final = snapshot(raw)
    assert baseline.keys() == final.keys()
    target_key = canonical([target.pk.hex]).decode()
    permitted_additions = {"portal_baichuanfactrevision", "portal_auditevent"}
    changes = {}
    for table, before in baseline.items():
        after = final[table]
        assert before["columns"] == after["columns"]
        removed = before["rows"].keys() - after["rows"].keys()
        modified = {key for key in before["rows"].keys() & after["rows"].keys() if before["rows"][key] != after["rows"][key]}
        added = after["rows"].keys() - before["rows"].keys()
        assert not removed, (table, "deleted rows")
        assert not modified or (table == "portal_company" and modified == {target_key}), (table, "unexpected modified rows", len(modified))
        assert not added or table in permitted_additions, (table, "unexpected additions")
        changes[table] = {"before": before["count"], "after": after["count"], "preserved": before["count"] - len(modified), "added": len(added), "modified": len(modified), "removed": len(removed), "before_sha256": before["sha256"], "after_sha256": after["sha256"]}
    assert changes["portal_baichuanfactrevision"]["added"] == 1
    assert raw.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    assert not raw.execute("PRAGMA foreign_key_check").fetchall()
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
    if attempts:
        write_json(output / "blocked-attempts.json", attempts)
    write_json(output / "blocked-local-socket-probes.json", local_probes)
    assert not attempts
    receipt = {"kind": "baichuan_flagoff_backup_rehearsal_v1", "status": "passed", "executed_at": datetime.now(timezone.utc).isoformat(),
        "django_version": django.get_version(), "sqlite_version": sqlite3.sqlite_version, "python_version": sys.version,
        "pending_migrations": 0, "applied_migrations": len(executor.loader.applied_migrations),
        "flags": {key: getattr(settings, key) for key in ("BAICHUAN_ASSISTANT_ENABLED", "BAICHUAN_RESEARCH_ENABLED", "BAICHUAN_FACT_WRITE_ENABLED", "PRODUCT_MODEL_CALLS_ALLOWED", "AGENT_PLATFORM_ENABLED")},
        "api_checks": checks, "detail_status": 200, "copy_only_manual_save_status": saved.status_code,
        "stale_snapshot_status": stale.status_code, "assistant_disabled_status": disabled.status_code,
        "manual_update_retained_after_flag_restore": True, "target_company_id": str(target.pk),
        "target_version_before": old_company["version"], "target_version_after": after_company["version"],
        "non_target_company_fields_preserved": True, "tables": changes, "before_snapshot_sha256": digest(baseline),
        "after_snapshot_sha256": digest(final), "quick_check": "ok", "foreign_key_violations": 0,
        "network_model_attempts": len(attempts), "blocked_local_socket_probes": len(local_probes), "workers_started": 0,
        "rollback_requirement": "Stop new worker explicitly; flag-off alone does not stop claim_job/run_one. Preserve incremental tables; never restore stale full DB over subsequent manual edits.",
        "limitations": ["No live rollback or deployment", "No browser/page interaction", "No PostgreSQL concurrency rehearsal", "No down-migration; intentionally preserves new schema", "History-enriched original DB is not recovered"]}
    write_json(output / "copy-receipt.json", receipt)
    connections.close_all()
    print(json.dumps({"status": "passed", "checks": len(checks), "pending_migrations": 0, "network_model_attempts": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        return child(args.output.resolve(strict=True))
    state = json.loads((OWNED / "source-status.json").read_text(encoding="utf-8"))
    identity = json.loads((OWNED / "environment.json").read_text(encoding="utf-8"))
    assert identity["kind"] == "baichuan_ai_isolated_local_v1"
    assert state["source_kind"] == "local_original_excel" and state["import_completed"] is True
    assert state["source_sha256"] == SOURCE_SHA and state["imported_company_count"] == 1283
    assert state["historical_enrichment_restored"] is False
    output = private_directory(args.output)
    started = time.monotonic()
    original = (OWNED / "portal.sqlite3").resolve(strict=True)
    def protected_source():
        with closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
            conn.execute("PRAGMA query_only=ON")
            current = snapshot(conn)
            protected = {name: {"count": table["count"], "sha256": table["sha256"]}
                for name, table in current.items() if name in {"portal_company", "portal_companyqualification", "portal_companyperson",
                    "portal_baichuanevidence", "portal_baichuancertificate", "portal_baichuanfactrevision",
                    "portal_baichuanresearchmanifest", "portal_baichuanresearchitem"}}
            assert len(protected) == 8
            return protected
    original_before = protected_source()
    baseline = backup(original, output / "before.sqlite3")
    working = backup((output / "before.sqlite3").resolve(), output / "working.sqlite3")
    env = clean_environment(output / "working.sqlite3", output)
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", "--output", str(output)],
        env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
    (output / "child-stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output / "child-stderr.txt").write_text(completed.stderr, encoding="utf-8")
    assert file_hash(output / "before.sqlite3") == baseline["sha256"], "Original backup was modified"
    original_after = protected_source()
    assert original_before == original_after, "Protected source changed concurrently; do not mix snapshot points"
    receipt = {"kind": "baichuan_flagoff_backup_parent_v1", "status": "passed" if completed.returncode == 0 else "failed",
        "source_open_mode": "ro", "source_query_only": True, "owned_source_sha256": SOURCE_SHA,
        "source_receipt_sha256": file_hash(OWNED / "source-status.json"), "source_backup": baseline,
        "working_initial_backup": working, "before_backup_unchanged": True, "child_exit_code": completed.returncode,
        "protected_source_before": original_before, "protected_source_after": original_after, "protected_source_unchanged": True,
        "working_final_sha256": file_hash(output / "working.sqlite3"), "elapsed_seconds": round(time.monotonic() - started, 4),
        "note": "Original connection was read-only. Live service may concurrently create legitimate tasks; no whole-live-file equality assertion.",
        "script_sha256": file_hash(Path(__file__))}
    write_json(output / "parent-receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "child_exit_code": completed.returncode, "elapsed_seconds": receipt["elapsed_seconds"]}))
    if completed.returncode:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
