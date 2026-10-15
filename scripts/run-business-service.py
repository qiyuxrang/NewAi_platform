"""Run the bundled Windows business services with repository-local runtimes."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import uuid
from urllib.parse import urlsplit

from dotenv import load_dotenv

WORKERS = {"product-worker": "run_product_worker", "hr-worker": "run_hr_worker",
           "engineering-worker": "run_engineering_worker", "tender-worker": "run_tender_consumer"}


def bundle_path_environment(repo):
    """Map only trusted deployment paths; never print the loaded environment."""
    bundle = Path(__file__).resolve().parents[1]
    runtime = repo / ".runtime"
    fixed = {
        "PORTAL_SQLITE_PATH": runtime / "portal.sqlite3",
        "PORTAL_MERMAID_NODE": bundle / ".runtime/node/node.exe",
        "PORTAL_MERMAID_CHROMIUM": bundle / ".runtime/browser/chrome-win64/chrome.exe",
        "PORTAL_ENGINEERING_PYTHON": runtime / "engineering-web-venv/Scripts/python.exe",
        "PORTAL_ENGINEERING_COST_CLI": bundle / "services/engineering/tools/cost_skill.py",
        "PORTAL_PRODUCT_PARSER_PYTHON": runtime / "product-parser-python/Scripts/python.exe",
        "PORTAL_PRODUCT_DOCUMENT_PYTHON": runtime / "product-documents-python/Scripts/python.exe",
    }
    for key, value in fixed.items():
        os.environ[key] = str(value.resolve())
    # These aliases are also used by deployments that expose settings directly.
    os.environ["ENGINEERING_PYTHON"] = os.environ["PORTAL_ENGINEERING_PYTHON"]
    os.environ["ENGINEERING_COST_CLI"] = os.environ["PORTAL_ENGINEERING_COST_CLI"]

    def local_path(value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = repo / path
        elif not path.is_relative_to(repo):
            # Copied legacy environments may retain an absolute .runtime path.
            parts = path.parts
            if ".runtime" not in parts:
                raise ValueError("Business storage/import path must be inside services/business")
            path = runtime.joinpath(*parts[parts.index(".runtime") + 1:])
        path = path.resolve()
        if not path.is_relative_to(repo):
            raise ValueError("Business storage/import path escapes services/business")
        return str(path)

    for key, default in {
        "PORTAL_PRODUCT_STORAGE_ROOT": ".runtime/product-private",
        "PORTAL_TENDER_STORAGE_ROOT": ".runtime/tender-private",
        "PORTAL_HR_STORAGE_ROOT": ".runtime/hr-private",
        "PORTAL_ENGINEERING_STORAGE_ROOT": ".runtime/engineering-private",
    }.items():
        os.environ[key] = local_path(os.environ.get(key) or default)
    imports = os.environ.get("PORTAL_PRODUCT_IMPORT_ROOTS", "")
    os.environ["PORTAL_PRODUCT_IMPORT_ROOTS"] = os.pathsep.join(
        local_path(value) for value in imports.split(os.pathsep) if value
    )
    paths = {key: os.environ[key] for key in (*fixed, "PORTAL_PRODUCT_STORAGE_ROOT",
             "PORTAL_TENDER_STORAGE_ROOT", "PORTAL_HR_STORAGE_ROOT",
             "PORTAL_ENGINEERING_STORAGE_ROOT", "PORTAL_PRODUCT_IMPORT_ROOTS")}
    paths["engineering_data_library"] = str((bundle / "services/engineering/data/library").resolve())
    return paths


def model_gateway_matches():
    from django.conf import settings
    url = urlsplit(settings.MODEL_GATEWAY_URL)
    return (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
            and url.port == 18411 and not url.username and not url.password)


def worker_preflight():
    """SELECT-only snapshot. Never call cleanup/claim/run/inspect CLI methods."""
    from django.conf import settings
    from django.db import connection
    from django.db.models import Count
    from django.utils import timezone
    from portal.engineering_models import EngineeringJob
    from portal.engineering_storage import verified_input
    from portal.engineering_worker import _engineering_allowed, max_attempts, online_webprice_key, runtime_state
    from portal.hr_retention import cutoff
    from portal.hr_resume_storage import _root
    from portal.hr_recruitment_models import RecruitmentRequest
    from portal.hr_screening_models import ResumeArtifact, ResumeScreeningBatch
    from portal.product_models import DocumentTask
    from portal.tender_models import TenderFetchRun, TenderManualRefresh, TenderSource
    from portal.product_storage import StorageError

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA query_only = ON" if connection.vendor == "sqlite" else "SET default_transaction_read_only = on")
    def counts(model, field):
        return {row[field]: row["count"] for row in model.objects.values(field).annotate(count=Count("pk"))}

    root, edge = _root(), cutoff()
    sweep = {"root": str(root), "directory_exists": root.is_dir(), "eligible_entries": 0,
             "eligible_file_ids": 0, "deferred_markers": 0, "expired_unreferenced": 0,
             "protected_referenced": 0, "fresh_unreferenced": 0, "stat_failures": 0,
             "record_archive_or_delete_operations": 0, "dry_run": True}
    eligible_ids = set()
    if root.is_dir():
        with os.scandir(root) as entries:
            for entry in entries:
                deferred = entry.name.endswith(".delete")
                identifier = entry.name[:-7] if deferred else entry.name[:-4] if entry.name.endswith(".tmp") else entry.name
                try:
                    if str(uuid.UUID(identifier)) != identifier or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    if not deferred and entry.stat(follow_symlinks=False).st_mtime > edge.timestamp():
                        sweep["fresh_unreferenced"] += int(not ResumeArtifact.objects.filter(file_id=identifier).exclude(archive_state__in=["deleted", "file_deleted"]).exists())
                        continue
                    if ResumeArtifact.objects.filter(file_id=identifier).exclude(archive_state__in=["deleted", "file_deleted"]).exists():
                        sweep["protected_referenced"] += 1
                        continue
                except ValueError:
                    continue
                except OSError:
                    sweep["stat_failures"] += 1
                    continue
                sweep["eligible_entries"] += 1
                sweep["deferred_markers" if deferred else "expired_unreferenced"] += 1
                eligible_ids.add(identifier)
    sweep["eligible_file_ids"] = len(eligible_ids)
    state = runtime_state()
    jobs = []
    for job in EngineeringJob.objects.exclude(status="completed").select_related("owner").order_by("created_at"):
        errors = []
        for item in job.inputs if isinstance(job.inputs, list) else [None]:
            try:
                verified_input(item)
            except StorageError as error:
                errors.append(error.code)
        jobs.append({"id": str(job.pk), "status": job.status, "input_count": len(job.inputs) if isinstance(job.inputs, list) else 0,
                     "input_ready": bool(job.inputs) and not errors, "input_error_codes": errors,
                     "owner_department_allowed": _engineering_allowed(job.owner), "attempt_count": job.attempt_count,
                     "attempts_remaining": job.attempt_count < max_attempts(),
                     "inspection_recorded": bool(job.inspection), "inspection_ok": job.inspection.get("ok") is True if isinstance(job.inspection, dict) else False})
    return {"checked_at": timezone.now().isoformat(), "read_only": True,
            "product": {"enabled": settings.PRODUCT_P1_ENABLED, "states": counts(DocumentTask, "state")},
            "hr": {"request_archive_states": counts(RecruitmentRequest, "archive_state"),
                   "batch_states": counts(ResumeScreeningBatch, "status"), "artifact_states": counts(ResumeArtifact, "processing_status"),
                   "cleanup": sweep},
            "engineering": {"runtime_status": state["status"], "python": str(state["python"]) if state["python"] else None,
                            "cli": str(state["cli"]) if state["cli"] else None, "states": counts(EngineeringJob, "status"), "pending_jobs": jobs,
                            "online_flag": os.environ.get("PORTAL_ENGINEERING_ALLOW_ONLINE") == "1",
                            "online_effective": bool(online_webprice_key()), "result_type": "internal_draft",
                            "cli_invoked": False},
            "tender": {"enabled": settings.PORTAL_TENDER_INGESTION_ENABLED,
                       "manual_refresh_enabled": settings.PORTAL_TENDER_MANUAL_REFRESH_ENABLED,
                       "schedule_enabled": settings.PORTAL_TENDER_SCHEDULE_ENABLED,
                       "enabled_sources": TenderSource.objects.filter(enabled=True).count(),
                       "running_sources": TenderFetchRun.objects.filter(state="RUNNING").count(),
                       "running_batches": TenderManualRefresh.objects.filter(state="RUNNING").count()},
            "model_gateway_loopback_18411": model_gateway_matches(), "workers_started": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("portal", "gateway", "workers-check", "paths-check", *WORKERS))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1] / "services/business")
    parser.add_argument("--output", type=Path, help="workers-check only; legacy-worker evidence under this repo's .runtime/enterprise")
    args = parser.parse_args()
    if args.output and args.service != "workers-check":
        parser.error("--output is valid only for workers-check")
    repo = args.repository.resolve(strict=True)
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    load_dotenv(repo / ".runtime" / "local.env", override=True)
    paths = bundle_path_environment(repo)
    if args.service == "paths-check":
        print(json.dumps(paths, ensure_ascii=False, indent=2))
        return
    if args.service == "gateway":
        load_dotenv(repo / ".runtime" / "model-gateway.env", override=True)
        import uvicorn
        uvicorn.run("model_gateway.app:app", host="127.0.0.1", port=18411, workers=1, access_log=False)
        return
    sys.path.insert(0, str(repo / "backend"))
    if args.service == "workers-check" or args.service in WORKERS:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()
        if args.service == "workers-check":
            data = worker_preflight()
            encoded = json.dumps(data, ensure_ascii=False, indent=2)
            if args.output:
                target = args.output.resolve()
                evidence_root = Path(__file__).resolve().parents[1] / ".runtime" / "enterprise"
                if target.parent != evidence_root.resolve() or not target.name.startswith("legacy-worker") or target.suffix != ".json":
                    parser.error("output must be a legacy-worker*.json under this repo's .runtime/enterprise")
                target.write_text(encoded + "\n", encoding="utf-8")
            print(encoded)
            return
        if not model_gateway_matches():
            parser.error("existing portal model gateway must point to loopback:18411; configuration was not changed")
        from django.core.management import call_command
        call_command(WORKERS[args.service], **({"concurrency": 1} if args.service == "hr-worker" else {}))
        return
    sys.argv = [str(repo / "backend" / "manage.py"), "runserver", "127.0.0.1:8100", "--noreload"]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
