"""Run only named backend tests with fresh isolated configuration and storage."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    root = Path(__file__).resolve().parents[2]
    runtime = root / ".runtime" / "baichuan-checks"
    runtime.mkdir(parents=True, exist_ok=True)
    for key in list(os.environ):
        if key.startswith("PORTAL_"):
            os.environ.pop(key)
    with TemporaryDirectory(prefix="tests-", dir=runtime) as directory:
        storage = Path(directory)
        os.environ.update(PORTAL_DEBUG="1", PORTAL_HTTPS="0",
            PORTAL_SECRET_KEY="isolated-baichuan-test-only-secret-not-a-deployment-key",
            PORTAL_SQLITE_PATH=str(storage / "unused.sqlite3"), DJANGO_SETTINGS_MODULE="config.settings",
            PORTAL_BAICHUAN_STORAGE_ROOT=str(storage / "private"),
            PORTAL_PRODUCT_STORAGE_ROOT=str(storage / "product-private"))
        backend = root / "services" / "business" / "backend"
        os.chdir(backend)
        # Match portal/worker startup: model_gateway is a sibling package of
        # backend, while config/portal live inside backend.
        sys.path[:0] = [str(backend), str(backend.parent)]
        from django.conf import settings
        from django.core.management import execute_from_command_line
        from django.db import connections
        # File SQLite exercises actual writer waiting and independent processes;
        # Django's default shared-memory DB silently skips those regressions.
        settings.DATABASES["default"]["TEST"] = {"NAME": str(storage / "test.sqlite3")}
        labels = sys.argv[1:] or ["portal.tests.test_baichuan_assistant"]
        if any(not label.startswith("portal.tests.test_baichuan") for label in labels):
            raise ValueError("Only explicit Baichuan test modules are allowed")
        try:
            execute_from_command_line(["manage.py", "test", *labels, "--noinput", "-v", "1"])
        finally:
            connections.close_all()


if __name__ == "__main__":
    main()
