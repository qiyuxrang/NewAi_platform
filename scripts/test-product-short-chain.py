"""Run a short synthetic worker smoke with real rendering in wholly isolated state."""
import os
import secrets
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".runtime" / "short-chain-smoke" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
OUTPUT.mkdir(parents=True, exist_ok=False)
NODE = Path("C:/Users/YLJJT/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
env = {key: value for key, value in os.environ.items() if not key.startswith(("PORTAL_", "PLATFORM_", "MODEL_GATEWAY_"))}
env.update(PORTAL_SECRET_KEY=secrets.token_urlsafe(48), PORTAL_DEBUG="1", PORTAL_HTTPS="0",
           PORTAL_SQLITE_PATH=str(OUTPUT / "isolated.sqlite3"), PORTAL_ALLOWED_HOSTS="testserver,localhost,127.0.0.1",
           PORTAL_PRODUCT_DOCUMENT_PYTHON=sys.executable, PORTAL_PRODUCT_PARSER_PYTHON=sys.executable,
           PORTAL_PRODUCT_OFFICE_RENDER_ENABLED="1", PORTAL_PRODUCT_OFFICE_RENDERER="word",
           PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED="0", PORTAL_ENGINEERING_ALLOW_ONLINE="0", DISABLE_WEB_LOOKUP="1",
           PORTAL_PRODUCT_MODEL_CALLS_ALLOWED="0", PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview",
           PORTAL_MERMAID_NODE=str(NODE), PORTAL_MERMAID_CHROMIUM=str(EDGE),
           PYTHONIOENCODING="utf-8", RUN_PRODUCT_REAL_SHORT_SMOKE="1", PRODUCT_SHORT_SMOKE_OUTPUT=str(OUTPUT))
for family in ("product", "hr", "engineering", "tender"):
    env["PORTAL_" + family.upper() + "_STORAGE_ROOT"] = str(OUTPUT / (family + "-private"))
print("Isolated short smoke output: " + str(OUTPUT), flush=True)
with (OUTPUT / "regression.log").open("w", encoding="utf-8") as log:
    result = subprocess.run([sys.executable, str(ROOT / "services/business/backend/manage.py"), "test",
        "portal.tests.test_product_short_chain", "--verbosity", "2"], cwd=ROOT, env=env,
        stdout=log, stderr=subprocess.STDOUT)
print("Short smoke exit: " + str(result.returncode), flush=True)
print((OUTPUT / "regression.log").read_text(encoding="utf-8")[-10000:])
raise SystemExit(result.returncode)
