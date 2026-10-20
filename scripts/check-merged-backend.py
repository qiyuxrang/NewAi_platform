"""Run merge regressions on disposable SQLite, without loading local.env."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services/business/backend"), str(ROOT / "services/business")]
for key in list(os.environ):
    if key.startswith("PORTAL_"):
        del os.environ[key]
os.environ.update(PORTAL_DEBUG="1", PORTAL_HTTPS="0",
    PORTAL_SECRET_KEY="synthetic-merge-regression-key-" + "x" * 40,
    DJANGO_SETTINGS_MODULE="config.settings")

with TemporaryDirectory(prefix="backend-merge-", dir=ROOT / ".runtime") as temporary:
    os.environ["PORTAL_SQLITE_PATH"] = str(Path(temporary) / "empty.sqlite3")
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    settings.DATABASES["default"]["TEST"]["NAME"] = str(Path(temporary) / "tests.sqlite3")
    labels = sys.argv[1:] or [
        "test_knowledge_access", "test_model_processing_boundary", "test_engineering_knowledge_acl",
        "test_admin_review", "test_legacy_product_visibility", "test_architecture_merge",
        "test_admin", "test_model_admin", "test_model_gateway_sqlite", "test_product_model_pacing",
        "test_production_readiness", "test_product_knowledge_archive", "test_product_assistant_model",
        "test_product_assistant_tools_efficiency", "test_baichuan_api_permissions", "test_baichuan_jobs",
        "test_baichuan_model_admission", "test_baichuan_model_budget_recovery", "test_baichuan_query_model_budget",
        "test_baichuan_assistant_models", "test_baichuan_assistant", "test_product_deleted_boundaries",
        "test_product_task_management", "test_product_short_chain", "test_product_generation_only",
        "test_product_steps", "test_department_workflow_migrations",
    ]
    try:
        call_command("test", *("portal.tests." + label for label in labels), interactive=False, verbosity=1)
    finally:
        connections.close_all()
