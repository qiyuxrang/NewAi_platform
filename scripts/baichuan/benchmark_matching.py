"""Synthetic, disposable structured matching benchmark; no target DB access."""
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter


def main():
    root = Path(__file__).resolve().parents[2]
    parent = root / ".runtime/baichuan-checks"
    parent.mkdir(parents=True, exist_ok=True)
    for key in list(os.environ):
        if key.startswith("PORTAL_"):
            os.environ.pop(key)
    with TemporaryDirectory(prefix="benchmark-", dir=parent) as directory:
        os.environ.update(PORTAL_DEBUG="1", PORTAL_HTTPS="0", DJANGO_SETTINGS_MODULE="config.settings",
            PORTAL_SECRET_KEY="isolated-benchmark-secret-never-used-for-a-deployment",
            PORTAL_SQLITE_PATH=str(Path(directory) / "benchmark.sqlite3"),
            PORTAL_BAICHUAN_SCOPE_CONFIRMED="1", PORTAL_BAICHUAN_READ_ROLE_CODES="product")
        sys.path.insert(0, str(root / "services/business/backend"))
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connection
        from django.utils import timezone
        from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanQualificationRule
        from portal.baichuan_matching import match_companies
        from portal.baichuan_models import Company
        from portal.models import Role, User
        call_command("migrate", verbosity=0, stdout=StringIO())
        call_command("seed_portal", stdout=StringIO())
        user = User.objects.create_user(username="fictional-benchmark", must_change_password=False)
        user.roles.add(Role.objects.get(code="product"))
        now, day = timezone.now(), timezone.localdate()
        basis = BaichuanEvidence.objects.create(source_type="fixture", import_ref="fixture:rule",
            retrieved_at=now, verified_on=day, access_status="verified", excerpt="Synthetic exact grade rule",
            locator={"fixture": True}, content_hash=hashlib.sha256(b"fixture").hexdigest())
        BaichuanQualificationRule.objects.create(category="itss", evidence=basis, legal_grades=["1", "2", "3", "4"])
        conditions = {"schema_version": 1, "revision": 1, "must": {"field": "qualification", "op": "grade_exact",
            "category": "itss", "value": "2", "holder": "bidder"}}
        report = {"synthetic": True, "target_database_accessed": False, "backend": "SQLite",
                  "python": sys.version.split()[0], "scope": "structured matching only", "datasets": []}
        for count in (1000, 5000):
            previous = Company.objects.count()
            companies = [Company(name=f"虚构性能企业{i:05}", created_by=user, updated_by=user) for i in range(previous, count)]
            Company.objects.bulk_create(companies, batch_size=200)
            sources, certificates = [], []
            for i, company in enumerate(companies, previous):
                source = BaichuanEvidence(source_type="fixture", import_ref="fixture:certificate",
                    retrieved_at=now, verified_on=day, access_status="verified", excerpt="Synthetic certificate evidence",
                    locator={"fixture": True}, content_hash=hashlib.sha256(str(company.pk).encode()).hexdigest(),
                    subject={"company_id": str(company.pk), "identity_verified": True, "holder_type": "bidder",
                        "authority": "issuer", "scope_verified": True, "revocation_checked": True,
                        "revocation_checked_on": day.isoformat()})
                sources.append(source)
                certificates.append(BaichuanCertificate(company=company, category="itss", grade="2",
                    holder_type="bidder", holder_company_id=company.pk, assertion_status="PRESENT",
                    verification_status="verified" if i % 2 == 0 else "unverified", evidence=source,
                    valid_from=day, valid_until=day, revocation_status="clear"))
            BaichuanEvidence.objects.bulk_create(sources, batch_size=200)
            BaichuanCertificate.objects.bulk_create(certificates, batch_size=200)
            durations = []
            for attempt in range(13):
                if attempt == 0:
                    connection.close()
                started = perf_counter()
                result = match_companies(user, conditions)
                durations.append((perf_counter() - started) * 1000)
                assert result[3] == {"confirmed": count // 2, "candidate": count // 2, "excluded": 0}
            warm = sorted(durations[1:])
            report["datasets"].append({"companies": count, "certificates": count, "cold_ms": round(durations[0], 3),
                "warm_samples": len(warm), "warm_median_ms": round(median(warm), 3),
                "warm_p95_ms": round(warm[math.ceil(len(warm) * .95) - 1], 3),
                "samples_ms": [round(value, 3) for value in durations], "verified_result_counts": result[3],
                "meets_2s_structured_target": max(warm) <= 2000})
        path = root / "doc/baichuan-sdd/ai-assistant/evidence/AI-T16/2026-10-17-structured-benchmark.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        from django.db import connections
        connections.close_all()


if __name__ == "__main__":
    main()
