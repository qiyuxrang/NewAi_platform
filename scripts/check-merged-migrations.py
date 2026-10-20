"""Exercise fresh and legacy database upgrades without touching a running database."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "services/business/backend"


def run(database, *command):
    env = {key: value for key, value in os.environ.items() if not key.startswith("PORTAL_")}
    env.update(PORTAL_DEBUG="1", PORTAL_HTTPS="0", PORTAL_SECRET_KEY="isolated-migration-verification-" * 3,
               PORTAL_SQLITE_PATH=str(database), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "manage.py", *command], cwd=BACKEND,
                            env=env, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def snapshot(database):
    with closing(sqlite3.connect(database)) as connection:
        tables = [name for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: (connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
                       {row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')})
                for name in tables}


def upgrade(database):
    before = snapshot(database)
    run(database, "migrate", "--noinput")
    after = snapshot(database)
    for name, (count, columns) in before.items():
        assert name in after and columns <= after[name][1], name
        if name not in {"django_migrations", "django_content_type", "auth_permission"}:
            assert count == after[name][0], name
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    run(database, "makemigrations", "portal", "--check", "--dry-run")
    return {"tables_before": len(before), "tables_after": len(after), "passed": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, help="Read-only backup to copy and verify")
    args = parser.parse_args()
    results = {}
    with tempfile.TemporaryDirectory(prefix="newai-migration-") as directory:
        root = Path(directory)
        results["fresh"] = upgrade(root / "fresh.sqlite3")
        legacy = root / "legacy.sqlite3"
        run(legacy, "migrate", "portal", "0046_baichuan_assistant_foundation", "--noinput")
        results["legacy_branch"] = upgrade(legacy)
        if args.snapshot:
            database = root / "current.sqlite3"
            source = args.snapshot.resolve(strict=True)
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as source_db, closing(sqlite3.connect(database)) as target:
                source_db.backup(target)
            results["current_snapshot"] = upgrade(database)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
