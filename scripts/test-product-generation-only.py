"""Run generation-only regression in a fresh database and private file root."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".runtime" / "product-generation-only" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
OUTPUT.mkdir(parents=True, exist_ok=False)
NODE = Path("C:/Users/YLJJT/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
env = {key: value for key, value in os.environ.items() if not key.startswith(("PORTAL_", "PLATFORM_", "MODEL_GATEWAY_"))}
env.update(PORTAL_SECRET_KEY=secrets.token_urlsafe(48), PORTAL_DEBUG="1", PORTAL_HTTPS="0",
           PORTAL_SQLITE_PATH=str(OUTPUT / "isolated.sqlite3"), PORTAL_ALLOWED_HOSTS="testserver,localhost,127.0.0.1",
           PORTAL_PRODUCT_DOCUMENT_PYTHON=sys.executable, PORTAL_PRODUCT_PARSER_PYTHON=sys.executable,
           PORTAL_PRODUCT_OFFICE_RENDER_ENABLED="1", PORTAL_PRODUCT_OFFICE_RENDERER="word",
           PORTAL_PRODUCT_CONTENT_VERIFICATION_ENABLED="0",
           PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED="0", PORTAL_ENGINEERING_ALLOW_ONLINE="0", DISABLE_WEB_LOOKUP="1",
           PORTAL_PRODUCT_MODEL_CALLS_ALLOWED="0", PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview",
           PORTAL_MERMAID_NODE=str(NODE), PORTAL_MERMAID_CHROMIUM=str(EDGE), PYTHONIOENCODING="utf-8",
           RUN_PRODUCT_GENERATION_ONLY_SMOKE="1", PRODUCT_GENERATION_ONLY_OUTPUT=str(OUTPUT))
for family in ("product", "hr", "engineering", "tender"):
    env["PORTAL_" + family.upper() + "_STORAGE_ROOT"] = str(OUTPUT / (family + "-private"))
labels = sys.argv[1:]
legacy = "--legacy-verification" in labels
if legacy:
    labels.remove("--legacy-verification")
    env["PORTAL_PRODUCT_CONTENT_VERIFICATION_ENABLED"] = "1"
labels = labels or ["portal.tests.test_product_generation_only"]
# Read-only boundary evidence; this command never builds or reloads the UI.
def frontend_pins():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "frontend" / "src").rglob("*") if path.is_file()}
before = frontend_pins()
print("Isolated output: " + str(OUTPUT), flush=True)
with (OUTPUT / "regression.log").open("w", encoding="utf-8") as log:
    result = subprocess.run([sys.executable, str(ROOT / "services/business/backend/manage.py"), "test",
        *labels, "--verbosity", "2"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
after = frontend_pins()
(OUTPUT / "boundary.json").write_text(json.dumps({"frontend_files": len(before), "frontend_unchanged": before == after,
    "database": str(OUTPUT / "isolated.sqlite3"), "model": "deterministic_substitute", "exit_code": result.returncode,
    "labels": labels, "legacy_verification_compatibility": legacy}, ensure_ascii=False, indent=2), encoding="utf-8")
print((OUTPUT / "regression.log").read_text(encoding="utf-8")[-14000:])
raise SystemExit(result.returncode if before == after else 1)
