"""Apply a bounded reviewed-public-source batch to owned local empty fields.

Default invocation is inert. Execution never calls models or the network.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 8 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are refused")
        result[key] = value
    return result


def read_batch(path, expected_hash):
    from local_search import _plain_path
    path = _plain_path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Batch must be an existing bounded file")
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("Batch file hash differs from explicit authorization")
    return path, content, json.loads(content.decode("utf-8"), object_pairs_hook=_pairs)


def _guard_network():
    import socket
    def refused(*args, **kwargs):
        raise RuntimeError("Maintenance batch cannot access the network")
    socket.create_connection = refused
    socket.socket.connect = refused
    socket.socket.connect_ex = refused
    socket.getaddrinfo = refused


def execute(batch_file, expected_hash):
    import re
    if not re.fullmatch("[a-f0-9]{64}", expected_hash or ""):
        raise ValueError("Explicit complete lowercase batch SHA256 required")
    original, content, batch = read_batch(batch_file, expected_hash)
    _guard_network()
    import local_model
    import local_search
    import research_source_pilot as pilot
    local_model.application()
    from django.conf import settings
    from django.test import override_settings
    from portal.baichuan_assistant_models import BaichuanFactRevision
    from portal.baichuan_models import Company, CompanyQualification, CompanyPerson
    from portal.baichuan_reviewed_enrichment import apply_reviewed_company, item_digest, stamp_id, validate_batch
    from portal.baichuan_service import require_access
    from portal.models import ModelCallLog, User
    validate_batch(batch)
    runtime = local_search._runtime()
    source = json.loads((ROOT / "doc/baichuan-sdd/ai-assistant/checkpoint.json").read_text(encoding="utf-8"))["source_workbook"]
    source_hash = batch["source_workbook_sha256"]
    restore = local_search._plain_path(runtime / ("source-restore-" + source_hash[:8]))
    state = local_model.local.source_state()
    db = local_search._plain_path(settings.DATABASES["default"]["NAME"])
    if (runtime != local_model.local.RUNTIME or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3"
            or db != runtime / "portal.sqlite3" or source.get("sha256") != source_hash
            or state.get("source_connected") is not True or state.get("source_sha256") != source_hash
            or state.get("imported_company_count") != 1283 or Company.objects.count() != 1283
            or pilot.sha256(local_search._plain_path(source["path"])) != source_hash
            or pilot.sha256(local_search._plain_path(restore / "original.xlsx")) != source_hash
            or settings.BAICHUAN_RESEARCH_ENABLED or settings.BAICHUAN_FACT_WRITE_ENABLED):
        raise ValueError("Owned original-source DB, workbook hash and default-off gates required")
    manifest = json.loads(local_search._plain_path(restore / "reviewed-manifest.json").read_text(encoding="utf-8"))
    records = {item["id"]: item for item in manifest["records"]}
    if len(records) != 1283 or set(records) != set(str(pk) for pk in Company.objects.values_list("pk", flat=True)):
        raise ValueError("Catalog no longer matches restored source ID set")
    accounts = json.loads(local_search._plain_path(runtime / "accounts.json").read_text(encoding="utf-8"))["accounts"]
    actor = User.objects.get(username=next(item["username"] for item in accounts if item["role"] == "general_manager"))
    require_access(actor, write=True)
    # Preflight the WHOLE batch before backup or any company commit.
    for item in batch["items"]:
        company = Company.objects.get(pk=item["company_id"])
        if company.name != item["name"] or records[str(company.pk)]["company"]["name"] != company.name:
            raise ValueError("Company ID/legal name must match current and restored catalog exactly")
        stamp = BaichuanFactRevision.objects.filter(pk=stamp_id(company.pk, expected_hash)).first()
        if stamp:
            if stamp.company_id != company.pk or stamp.new_value.get("item_sha256") != item_digest(item):
                raise ValueError("Existing batch stamp differs")
        elif company.version != item["expected_version"]:
            raise ValueError("Company changed since batch review; no writes started")
    # One shared lock serializes all reviewed batches, including different files.
    import msvcrt
    lock_path = local_search._plain_path(runtime / "reviewed-enrichment.lock")
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        lock.write(b"1")
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            out = local_search._plain_path(runtime / ("reviewed-enrichment-" + expected_hash))
            # Restrict the directory BEFORE writing the original body or backup.
            if not out.exists():
                out.mkdir(mode=0o700)
            elif any(out.iterdir()) and not (out / "state.json").is_file():
                raise ValueError("Unknown/incomplete operation directory retained; refusing overwrite")
            # Reapply also after a crash between mkdir and ACL establishment.
            import csv, io, subprocess
            identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
            sid = list(csv.reader(io.StringIO(identity.stdout.strip())))[0][-1]
            if not re.fullmatch(r"S-1-[0-9-]+", sid):
                raise ValueError("Current Windows identity unavailable")
            subprocess.run(["icacls", str(out), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F"], capture_output=True, check=True)
            state_path = local_search._plain_path(out / "state.json")
            archived = local_search._plain_path(out / "batch.json")
            if state_path.exists():
                checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
                backup = local_search._plain_path(checkpoint["backup"]["file"])
                if (checkpoint.get("batch_sha256") != expected_hash or pilot.sha256(backup) != checkpoint["backup"]["sha256"]
                        or pilot.sha256(archived) != expected_hash):
                    raise ValueError("Resume requires unchanged batch archive and original backup")
            else:
                if any(out.iterdir()):
                    raise ValueError("Unknown/incomplete operation directory retained; refusing overwrite")
                backup = pilot.online_backup(db, out / "before.sqlite3")
                with archived.open("xb") as stream:
                    stream.write(content)
                checkpoint = {"kind": "reviewed_public_source_batch_v1", "batch_sha256": expected_hash,
                              "source_workbook_sha256": source_hash, "backup": backup, "status": "running"}
                local_search._private_create(state_path, checkpoint)
            calls_before = ModelCallLog.objects.count()
            def protected_digest():
                fixed = ("id", "name", "credit_code", "source", "verified_on", "contact_name", "contact_phone", "website_kind", "created_by_id", "created_at")
                data = {"companies": list(Company.objects.order_by("pk").values(*fixed)),
                        "qualifications": list(CompanyQualification.objects.order_by("pk").values()),
                        "people": list(CompanyPerson.objects.order_by("pk").values())}
                return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
            protected_before = protected_digest()
            totals = Counter()
            applied_this_run = replayed_companies = 0
            # This override exists only in this explicit maintenance subprocess.
            with override_settings(BAICHUAN_FACT_WRITE_ENABLED=True):
                for item in batch["items"]:
                    result = apply_reviewed_company(actor, batch, item, expected_hash)
                    totals.update({key: result[key] for key in ("applied", "conflict", "unchanged")})
                    if result["replayed"]:
                        replayed_companies += 1
                    else:
                        applied_this_run += result["applied"]
            if (protected_digest() != protected_before or ModelCallLog.objects.count() != calls_before
                    or local_search._plain_path(original).read_bytes() != content or settings.BAICHUAN_FACT_WRITE_ENABLED):
                raise ValueError("Post-commit preservation check failed; checkpoint and backup retained")
            checkpoint.update(status="completed", counts=dict(totals), companies=len(batch["items"]),
                              model_call_delta=0, network_calls=0, protected_records_unchanged=True)
            import uuid
            temporary = local_search._plain_path(out / ("state-" + uuid.uuid4().hex + ".new"))
            local_search._private_create(temporary, checkpoint)
            temporary.replace(state_path)
            return {"status": "completed", "companies": len(batch["items"]), "counts": dict(totals),
                    "applied_this_run": applied_this_run, "replayed_companies": replayed_companies,
                    "model_calls": 0, "network_calls": 0, "publication_only": True}
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch")
    parser.add_argument("--batch-sha256")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "inert", "database_writes": 0, "network_calls": 0, "model_calls": 0,
                          "requires": "--execute --batch PATH --batch-sha256 HASH"}))
        return
    if not args.batch or not args.batch_sha256:
        parser.error("Explicit batch file and SHA256 are required")
    try:
        result = execute(args.batch, args.batch_sha256)
    except Exception:
        parser.exit(2, "Reviewed enrichment stopped; preserve original batch, checkpoint and backup for recovery.\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
