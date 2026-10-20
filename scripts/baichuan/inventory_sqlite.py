"""Read-only, aggregate Baichuan inventory. Never opens/creates a writable DB.

Run with explicit --sqlite paths. A table missing from an old trial is reported
as missing, not as an empty or confirmed production catalog. No company names,
contact values, account identities or credential contents are emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


TABLES = ("portal_company", "portal_companyqualification", "portal_companyperson")
FIELDS = ("credit_code", "province", "city", "address", "website", "phone",
          "contact_name", "contact_phone", "email", "description", "source", "verified_on")


def inventory(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Explicit database path must be a regular existing file")
    # mode=ro rejects missing files and prevents accidental schema/data writes.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                  if table in existing else None for table in TABLES}
        coverage = {}
        if "portal_company" in existing:
            columns = {row[1] for row in connection.execute('PRAGMA table_info("portal_company")')}
            for field in FIELDS:
                if field in columns:
                    coverage[field] = connection.execute(
                        f'SELECT COUNT(*) FROM portal_company WHERE "{field}" IS NOT NULL '
                        f'AND TRIM(CAST("{field}" AS TEXT)) != \'\'').fetchone()[0]
        migrations = []
        if "django_migrations" in existing:
            migrations = [row[0] for row in connection.execute(
                "SELECT name FROM django_migrations WHERE app='portal' ORDER BY id DESC LIMIT 5")]
        connection.rollback()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"database": str(path), "bytes": path.stat().st_size, "sha256": digest,
            "access": "sqlite_uri_mode_ro_and_query_only", "target_confirmed": False,
            "table_counts": counts, "nonempty_field_counts": coverage,
            "field_verification": "not_assessed_nonempty_does_not_mean_verified",
            "latest_portal_migrations": migrations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", action="append", required=True,
                        help="Explicit existing SQLite file; may be repeated")
    args = parser.parse_args()
    results = []
    for path in args.sqlite:
        try:
            results.append(inventory(path))
        except (OSError, ValueError, sqlite3.Error) as error:
            results.append({"database": str(Path(path).absolute()), "error_type": type(error).__name__,
                            "target_confirmed": False})
    print(json.dumps({"schema_version": 1, "kind": "read_only_aggregate_inventory", "databases": results},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
