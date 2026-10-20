"""Prepare/run one explicitly enabled, bounded local original-source pilot.

Default: no Django setup, private configuration, database writes or networking.
Execute only with --execute --source-sha256 HASH --capability-receipt PATH.
One fixed ALL-company/12-field manifest is retained; only its first one (maximum
two) companies are attempted. Repetition reads coverage and never retries a
terminal attempt. Main company/legacy/person rows remain unchanged.

The child gets 230 seconds, including setup; its job budget is 210 seconds.
The parent kills a stalled child, then only finalizes already persisted state.
Existing TLS, SSRF pinning, quotas, evidence and proposal boundaries are reused.
"""
import argparse
from contextlib import closing, nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COMPANIES = 1283
JOB_SECONDS = 210
CHILD_SECONDS = 230
LABEL = "本地原始Excel来源企业，历史研究未恢复；有界研究试查"


def load_local_model():
    spec = importlib.util.spec_from_file_location("baichuan_owned_pilot_model", ROOT / "scripts/baichuan/local_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_gate(value):
    if (not isinstance(value, dict) or set(value) != {"kind", "search", "public_get", "company_queries", "model_calls"}
            or value["kind"] != "baichuan_public_research_capability_v1"
            or type(value["company_queries"]) is not int or value["company_queries"] != 0
            or type(value["model_calls"]) is not int or value["model_calls"] != 0):
        raise ValueError("Independent generic capability receipt is missing or invalid")
    search, get = value["search"], value["public_get"]
    if (not isinstance(search, dict) or set(search) != {"provider", "success", "tls_verification", "result_count"}
            or search["provider"] != "bing_rss" or search["success"] is not True or search["tls_verification"] is not True
            or type(search["result_count"]) is not int or search["result_count"] <= 0
            or not isinstance(get, dict) or set(get) != {"success", "tls_verification", "ssrf_pinning"}
            or any(get[key] is not True for key in get)):
        raise ValueError("Search and pinned verified-TLS GET must both have actual generic probe evidence")


def catalog_digest():
    from portal.baichuan_models import Company, CompanyPerson, CompanyQualification
    content = {model._meta.label_lower: list(model.objects.order_by("pk").values())
               for model in (Company, CompanyQualification, CompanyPerson)}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def online_backup(source, target, *, seconds=10):
    """Bounded SQLite online backup, refusing overwrite, with integrity check."""
    source, target = Path(source).resolve(strict=True), Path(target).resolve()
    if target.exists() or target == source:
        raise ValueError("Backup target already exists or aliases source")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb"):
        pass
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started >= seconds:
            raise TimeoutError("Online backup exceeded bounded time")
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=2)) as original:
            with closing(sqlite3.connect(target, timeout=2)) as destination:
                original.backup(destination, pages=256, progress=progress, sleep=0.05)
                if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup integrity check failed")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"file": str(target), "sha256": sha256(target), "quick_check": "ok"}


def field_results(items, outcome):
    """Use the normal full-research status meanings for the selected 12 fields."""
    results = []
    for item in items:
        if item.field in outcome["verified_sources"]:
            status, reason = "verified", "独立来源、主体及字段原文已经核对。"
        elif item.field in outcome["found_fields"]:
            status, reason = "pending_review", "已保留正文引用建议，主体和有效性仍待独立核验。"
        elif not outcome["readable"]:
            status = "failed" if not outcome["sources"] else "inaccessible"
            reason = "本轮未取得可读来源；访问或搜索缺口已记录，不推断资料不存在。"
        elif outcome["extraction_failed"]:
            status, reason = "failed", "正文已保存，但提取或引用校验未完成，需另行明确重试。"
        else:
            status, reason = "not_found", "本轮有限公开正文未提取到该字段；未找到不等于没有。"
        results.append({"company_id": str(item.company_id), "field": item.field, "status": status, "reason": reason,
            "evidence_id": outcome["verified_sources"].get(item.field),
            "checkpoint": {"evidence_ids": [str(source.pk) for source in outcome["sources"]], "gaps": outcome["gaps"]}})
    return results


def pilot_key(source_hash):
    return "source-pilot:" + source_hash


def pilot_receipt(manifest, baseline, *, replayed=False):
    from portal.baichuan_assistant_models import BaichuanEvidence
    from portal.baichuan_research import coverage_report
    job = manifest.job
    job.refresh_from_db()
    unchanged = catalog_digest() == baseline
    return {"kind": "baichuan_original_source_pilot_v1", "source_sha256": job.idempotency_key.removeprefix("source-pilot:"),
            "scope": "owned_local_original_workbook_only", "historical_enrichment_restored": False,
            "manifest_id": str(manifest.pk), "job_id": str(job.pk), "status": job.status, "error_code": job.error_code,
            "coverage": coverage_report(manifest), "replayed_without_network": replayed,
            "budget": job.budget, "budget_model_calls_reserved": job.counts.get("_budget_model_calls", 0),
            "budget_source_calls_reserved": job.counts.get("_budget_sources", 0),
            "main_catalog_digest_unchanged": unchanged, "catalog_digest_before": baseline,
            "catalog_digest_after": catalog_digest(), "fact_write_enabled": False,
            "persisted_source_count": BaichuanEvidence.objects.filter(locator__job_id=str(job.pk)).count(),
            "raw_sources_and_suggestions": "private_database_and_controlled_storage",
            "not_a_full_catalog_completion": True}


def run_pilot(actor, source_hash, *, limit, backup_ref, baseline, expected_count=EXPECTED_COMPANIES, keep_lease=True):
    """Real queue/runtime boundary, separately fixture-testable without real web."""
    from django.conf import settings
    from django.db import transaction
    from portal.baichuan_assistant_models import BaichuanResearchManifest
    from portal.baichuan_assistant_worker import KeepLease
    from portal.baichuan_jobs import claim_job, leased_job, save_job
    from portal.baichuan_models import Company
    from portal.baichuan_research import RESEARCH_FIELDS, create_manifest
    from portal.baichuan_research_runtime import _persist_proposals, _research_company
    from portal.baichuan_research import record_batch
    from portal.baichuan_service import BaichuanError
    if (settings.BAICHUAN_FACT_WRITE_ENABLED or limit not in (1, 2) or Company.objects.count() != expected_count
            or settings.BAICHUAN_TARGET_BACKUP_REF != backup_ref):
        raise ValueError("Pilot requires disabled fact writes, bounded selection and the confirmed company count")
    budget = {"timeout_seconds": JOB_SECONDS, "max_model_calls": limit, "max_sources": 10 * limit, "max_attempts": 3}
    identity = uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan-research:{settings.BAICHUAN_ASSISTANT_SCOPE}:{actor.pk}:{pilot_key(source_hash)}")
    existing = BaichuanResearchManifest.objects.select_related("job").filter(pk=identity).first()
    if existing and existing.job.status in {"partial", "completed", "failed", "cancelled"}:
        return pilot_receipt(existing, baseline, replayed=True)
    if catalog_digest() != baseline:
        raise ValueError("Main catalog changed since the protected pilot baseline")
    with transaction.atomic():
        manifest, created = create_manifest(actor, pilot_key(source_hash), fields=list(RESEARCH_FIELDS), budget=budget)
        if manifest.total_count != expected_count or set(manifest.fields) != set(RESEARCH_FIELDS):
            raise ValueError("Pilot must retain the complete fixed denominator and all 12 fields")
        job = claim_job("source-pilot-" + source_hash[:16], job_id=manifest.job_id, lease_seconds=45)
        if job is None:
            raise ValueError("Pilot already has an active executor or has exhausted its persisted budget")
        selected = [entry["id"] for entry in manifest.company_versions[:limit]]
        save_job(job.pk, job.lease_owner, job.fence, result_ref={"manifest_id": str(manifest.pk)},
                 checkpoint={**job.checkpoint, "pilot": {"selected_company_ids": selected,
                    "source_sha256": source_hash, "catalog_digest_before": baseline, "company_limit": limit}})
    worker = job.lease_owner
    try:
        with KeepLease(job, worker) if keep_lease else nullcontext() as lease:
            for identifier in selected:
                items = list(manifest.items.filter(company_id=identifier).select_related("company").order_by("field"))
                if all(item.status != "pending" for item in items):
                    continue
                if any(item.status != "pending" for item in items) or len(items) != len(RESEARCH_FIELDS):
                    raise ValueError("A pilot company must publish all 12 fields in one fenced transaction")
                job.refresh_from_db()
                before_model = job.counts.get("_budget_model_calls", 0)
                before_sources = job.counts.get("_budget_sources", 0)
                outcome = _research_company(job, worker, items[0].company, list(RESEARCH_FIELDS))
                if lease is not None and lease.error:
                    raise lease.error
                job.refresh_from_db()
                if job.counts.get("_budget_model_calls", 0) - before_model > 1 or job.counts.get("_budget_sources", 0) - before_sources > 10:
                    raise ValueError("Per-company pilot budget exceeded")
                with leased_job(job.pk, worker, job.fence):
                    _persist_proposals(job, worker, items[0].company, outcome)
                    record_batch(job.pk, worker, job.fence, field_results(items, outcome))
            job.refresh_from_db()
            if job.status == "running":
                save_job(job.pk, worker, job.fence, status="partial", error_code="pilot_batch_limit")
    except Exception as error:
        job.refresh_from_db()
        if job.status == "running":
            try:
                save_job(job.pk, worker, job.fence, status="partial", error_code=getattr(error, "code", "pilot_interrupted"))
            except BaichuanError:
                pass  # Fence/authorization/deadline failures already preserve durable state.
        if not isinstance(error, BaichuanError):
            raise
    manifest.refresh_from_db()
    result = pilot_receipt(manifest, baseline)
    if not result["main_catalog_digest_unchanged"]:
        raise ValueError("Pilot detected a main-catalog change; preserve backup and investigate")
    return result


def validate_owned_source(local, source_hash, gate_path):
    """Read-only prerequisite check; never creates markers or grants."""
    from django.conf import settings
    from portal.baichuan_models import Company
    runtime = local.RUNTIME.resolve()
    if (runtime != ROOT / ".runtime/baichuan-ai-local" or local.RUNTIME.is_symlink()
            or local.read_json(runtime / "environment.json").get("kind") != local.IDENTITY
            or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3"
            or Path(settings.DATABASES["default"]["NAME"]).resolve() != runtime / "portal.sqlite3"):
        raise ValueError("Refusing work outside the marked owned local source database")
    source = read_json(ROOT / "doc/baichuan-sdd/ai-assistant/checkpoint.json")["source_workbook"]
    state = local.source_state()
    restore = runtime / ("source-restore-" + source_hash[:8])
    verification = read_json(restore / "verification-receipt.json")
    if (source.get("sha256") != source_hash or state.get("source_sha256") != source_hash
            or state.get("source_connected") is not True or state.get("imported_company_count") != EXPECTED_COMPANIES
            or verification.get("source_sha256") != source_hash or verification.get("original_unchanged") is not True
            or verification.get("counts", {}).get("companies") != EXPECTED_COMPANIES
            or verification.get("history_restored") is not False or Company.objects.count() != EXPECTED_COMPANIES
            or sha256(source["path"]) != source_hash or sha256(restore / "original.xlsx") != source_hash):
        raise ValueError("Original workbook, restoration receipt or current catalog failed confirmation")
    expected_ids = {record["id"] for record in read_json(restore / "reviewed-manifest.json")["records"]}
    if expected_ids != set(str(pk) for pk in Company.objects.values_list("pk", flat=True)):
        raise ValueError("Current company IDs do not match the reviewed source restoration")
    gate_path = Path(gate_path).resolve(strict=True)
    if not gate_path.is_relative_to(runtime):
        raise ValueError("Capability receipt must be in owned private runtime storage")
    validate_gate(read_json(gate_path))
    return runtime


def execute(options, *, timeout_cleanup=False):
    model = load_local_model()
    model.application()
    local = model.local
    runtime = validate_owned_source(local, options.source_sha256, options.capability_receipt)
    from django.test import override_settings
    from portal.models import User
    from portal.baichuan_assistant_models import BaichuanResearchManifest
    from portal.baichuan_jobs import claim_job, save_job
    from portal.baichuan_service import BaichuanError
    actor = User.objects.get(username="baichuan-dev-product", is_active=True, must_change_password=False)
    directory = runtime / ("research-source-" + options.source_sha256[:12])
    directory.mkdir(exist_ok=True)
    state_path = directory / "pilot-state.json"
    if state_path.exists():
        state = read_json(state_path)
        if (state.get("source_sha256") != options.source_sha256 or state.get("company_limit") != options.companies
                or state.get("capability_gate_sha256") != sha256(options.capability_receipt)):
            raise ValueError("Persisted pilot arguments differ; no implicit new attempt is allowed")
        backup = state["backup"]
        if (Path(backup["file"]).resolve() != directory / "before-pilot.sqlite3"
                or backup.get("quick_check") != "ok" or sha256(backup["file"]) != backup.get("sha256")):
            raise ValueError("Persisted protected backup failed verification")
    elif timeout_cleanup:
        return {"status": "not_started", "error_code": "pilot_startup_timeout", "network_retry": False}
    else:
        baseline = catalog_digest()
        backup = online_backup(runtime / "portal.sqlite3", directory / "before-pilot.sqlite3")
        state = {"source_sha256": options.source_sha256, "company_limit": options.companies,
                 "capability_gate_sha256": sha256(options.capability_receipt), "backup": backup,
                 "catalog_digest_before": baseline}
        local.private_json(state_path, state)
    with override_settings(BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=False,
            BAICHUAN_DATASET_KIND="actual", BAICHUAN_TARGET_DATASET_CONFIRMED=True,
            BAICHUAN_TARGET_BACKUP_REF=backup["file"], BAICHUAN_ENVIRONMENT_LABEL=LABEL,
            PRODUCT_WEB_SEARCH_ENABLED=True, PRODUCT_WEB_SEARCH_PROVIDER="bing_rss",
            PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True, PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True):
        if timeout_cleanup:
            manifest = BaichuanResearchManifest.objects.select_related("job").filter(job__owner=actor,
                job__idempotency_key=pilot_key(options.source_sha256)).first()
            if manifest is None:
                return {"status": "not_started", "error_code": "pilot_startup_timeout", "network_retry": False}
            job = manifest.job
            if job.status == "running":
                try:
                    save_job(job.pk, job.lease_owner, job.fence, status="partial", error_code="pilot_timeout")
                except BaichuanError:
                    recovered = claim_job("source-pilot-timeout-cleanup", job_id=job.pk)
                    if recovered:
                        save_job(recovered.pk, recovered.lease_owner, recovered.fence, status="partial", error_code="pilot_timeout")
            receipt = pilot_receipt(manifest, state["catalog_digest_before"])
        else:
            receipt = run_pilot(actor, options.source_sha256, limit=options.companies,
                                backup_ref=backup["file"], baseline=state["catalog_digest_before"])
    receipt.update(backup=backup, capability_gate_sha256=state["capability_gate_sha256"])
    receipt_path = directory / "pilot-receipt.json"
    temporary = directory / (".receipt-" + uuid.uuid4().hex + ".json")
    local.private_json(temporary, receipt)
    temporary.replace(receipt_path)
    return receipt


def summary(receipt):
    coverage = receipt.get("coverage", {})
    return {"status": receipt["status"], "error_code": receipt.get("error_code", ""),
            "fixed_total_companies": coverage.get("total_companies"), "attempted_fields": coverage.get("attempted_fields"),
            "researched_companies": coverage.get("researched_companies"), "verified_fields": coverage.get("verified_fields"),
            "model_calls_reserved": receipt.get("budget_model_calls_reserved", 0),
            "source_calls_reserved": receipt.get("budget_source_calls_reserved", 0),
            "main_catalog_digest_unchanged": receipt.get("main_catalog_digest_unchanged"),
            "replayed_without_network": receipt.get("replayed_without_network", False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-sha256")
    parser.add_argument("--capability-receipt")
    parser.add_argument("--companies", type=int, choices=(1, 2), default=1)
    parser.add_argument("--_child-run", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if not options.execute:
        print(json.dumps({"mode": "explanation_only", "database_writes": 0, "network_calls": 0,
                          "requires": ["--execute", "--source-sha256 HASH", "--capability-receipt PATH"],
                          "default_company_limit": 1, "maximum_company_limit": 2, "fixed_catalog_fields": 12}))
        return
    if not isinstance(options.source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", options.source_sha256) or not options.capability_receipt:
        parser.error("Execute requires exact source hash and independent capability receipt")
    if options._child_run:
        try:
            print(json.dumps(summary(execute(options))))
        except Exception:
            # Vendor errors, full URLs and local source rows must not reach stdout.
            print(json.dumps({"status": "failed", "error_code": "pilot_execution_failed", "details": "private_runtime_state"}))
            raise SystemExit(1)
        return
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--_child-run"]
    try:
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=CHILD_SECONDS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(process.stdout.decode("utf-8", errors="replace").strip())
        if process.returncode:
            raise SystemExit(process.returncode)
    except subprocess.TimeoutExpired:
        print(json.dumps(summary(execute(options, timeout_cleanup=True))))


if __name__ == "__main__":
    main()
