"""Small, isolated deployment checks. No database/network/process mutations."""
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

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
print("Local paths, engineering overrides, storage containment, secret exclusion and Python syntax: PASS")
