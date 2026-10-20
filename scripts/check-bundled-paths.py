"""Small, isolated deployment checks. No database/network/process mutations."""
import importlib.util
import io
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("business_runner", root / "scripts/run-business-service.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
repo = root / "services/business"
with patch.dict(os.environ, {
    "PORTAL_ENGINEERING_PYTHON": "C:/old/runtime/python.exe",
    "PORTAL_ENGINEERING_COST_CLI": "C:/old/tools/cost_skill.py",
    "PORTAL_ENGINEERING_STORAGE_ROOT": "C:/old/.runtime/engineering-private",
    "PORTAL_SQLITE_PATH": "C:/old/portal.sqlite3",
    "PORTAL_MERMAID_NODE": "C:/old/node.exe",
    "PORTAL_MERMAID_CHROMIUM": "C:/old/chrome.exe",
    "PORTAL_PRODUCT_IMPORT_ROOTS": ".runtime/product-imports",
    "SECRET_KEY": "must-never-appear-in-output",
}, clear=True):
    paths = runner.bundle_path_environment(repo)
    assert paths["PORTAL_SQLITE_PATH"] == str((repo / ".runtime/portal.sqlite3").resolve())
    assert paths["PORTAL_MERMAID_NODE"] == str((root / ".runtime/node/node.exe").resolve())
    assert paths["PORTAL_MERMAID_CHROMIUM"] == str((root / ".runtime/browser/chrome-win64/chrome.exe").resolve())
    assert Path(paths["PORTAL_SQLITE_PATH"]).is_relative_to(repo)
    for key in ("PORTAL_MERMAID_NODE", "PORTAL_MERMAID_CHROMIUM"):
        assert Path(paths[key]).is_relative_to(root)
        assert not Path(paths[key]).is_relative_to(repo)
    assert paths["PORTAL_ENGINEERING_PYTHON"] == str((repo / ".runtime/engineering-web-venv/Scripts/python.exe").resolve())
    assert paths["PORTAL_ENGINEERING_COST_CLI"] == str((root / "services/engineering/tools/cost_skill.py").resolve())
    assert paths["engineering_data_library"] == str((root / "services/engineering/data/library").resolve())
    assert paths["PORTAL_ENGINEERING_STORAGE_ROOT"] == str((repo / ".runtime/engineering-private").resolve())
    assert paths["PORTAL_PRODUCT_IMPORT_ROOTS"] == str((repo / ".runtime/product-imports").resolve())
    assert "SECRET_KEY" not in paths and "must-never-appear-in-output" not in str(paths)
with patch.dict(os.environ, {"PORTAL_PRODUCT_STORAGE_ROOT": "../../escape"}, clear=True):
    try:
        runner.bundle_path_environment(repo)
    except ValueError:
        pass
    else:
        raise AssertionError("Escaping storage path was accepted")
compile((root / "scripts/run-business-service.py").read_text(encoding="utf-8-sig"), "run-business-service.py", "exec")
# Exercise actual CLI dispatch with synthetic Django; no settings/database or worker is loaded.
django = ModuleType("django")
django.setup = lambda: None
conf = ModuleType("django.conf")
conf.settings = SimpleNamespace(BAICHUAN_ASSISTANT_ENABLED=True, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
                                BAICHUAN_ASSISTANT_SCOPE="isolated-check")
management = ModuleType("django.core.management")
calls = []
management.call_command = lambda name, **options: calls.append((name, options))
with patch.dict(sys.modules, {"django": django, "django.conf": conf, "django.core.management": management}), \
        patch.object(runner, "load_dotenv"), patch.object(runner, "bundle_path_environment"), \
        patch.object(runner, "model_gateway_matches", return_value=True), patch.object(os, "chdir"), \
        patch.object(sys, "path", sys.path.copy()), \
        patch.object(sys, "argv", ["run-business-service.py", "baichuan-worker", "--repository", str(repo)]):
    runner.main()
    assert calls == [("run_baichuan_worker", {})]
    conf.settings.BAICHUAN_ASSISTANT_ENABLED = False
    try:
        with patch.object(sys, "stderr", io.StringIO()):
            runner.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Disabled Baichuan worker was dispatched")
    assert len(calls) == 1
# Preflight imports are synthetic too: prove flag-off skips the Baichuan table,
# and flag-on counts only the configured scope under the read-only connection.
modules = {"django.conf": conf}
for module_name, names in {
    "django.db": "connection", "django.db.models": "Count", "django.utils": "timezone",
    "portal.engineering_models": "EngineeringJob", "portal.engineering_storage": "verified_input",
    "portal.engineering_worker": "_engineering_allowed max_attempts online_webprice_key runtime_state",
    "portal.hr_retention": "cutoff", "portal.hr_resume_storage": "_root",
    "portal.hr_recruitment_models": "RecruitmentRequest",
    "portal.hr_screening_models": "ResumeArtifact ResumeScreeningBatch",
    "portal.product_models": "DocumentTask", "portal.product_storage": "StorageError",
    "portal.tender_models": "TenderFetchRun TenderManualRefresh TenderSource",
    "portal.baichuan_assistant_models": "BaichuanJob",
}.items():
    module = modules[module_name] = ModuleType(module_name)
    for name in names.split():
        setattr(module, name, MagicMock())
conf.settings.PRODUCT_P1_ENABLED = True
conf.settings.PORTAL_TENDER_INGESTION_ENABLED = False
conf.settings.PORTAL_TENDER_MANUAL_REFRESH_ENABLED = False
conf.settings.PORTAL_TENDER_SCHEDULE_ENABLED = False
modules["django.db"].connection.vendor = "sqlite"
modules["portal.hr_resume_storage"]._root.return_value.is_dir.return_value = False
modules["portal.engineering_worker"].runtime_state.return_value = {"status": "ready", "python": None, "cli": None}
modules["portal.engineering_worker"].online_webprice_key.return_value = None
baichuan_jobs = modules["portal.baichuan_assistant_models"].BaichuanJob.objects
baichuan_jobs.filter.return_value.values.return_value.annotate.return_value = [{"status": "queued", "count": 2}]
with patch.dict(sys.modules, modules), patch.object(runner, "model_gateway_matches", return_value=True):
    assert runner.worker_preflight()["baichuan"]["states"] == {}
    baichuan_jobs.filter.assert_not_called()
    conf.settings.BAICHUAN_ASSISTANT_ENABLED = True
    snapshot = runner.worker_preflight()
    assert snapshot["read_only"] and not snapshot["workers_started"]
    assert snapshot["baichuan"]["states"] == {"queued": 2}
    baichuan_jobs.filter.assert_called_once_with(scope="isolated-check")
    statements = modules["django.db"].connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert len(statements) == 2 and all(call.args == ("PRAGMA query_only = ON",) for call in statements)
print("Local paths, engineering overrides, storage containment, secret exclusion and Python syntax: PASS")
print("Baichuan enabled dispatch and disabled rejection without loading settings/database/worker: PASS")
print("Read-only preflight, flag-off table exclusion and scope-restricted aggregate counts: PASS")
