"""Linux service entrypoint. Migrations run only in the explicit init job."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("/app/services/business")


def main():
    service, *arguments = sys.argv[1:]
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.chdir(ROOT / "backend")
    if service in {"image-checks", "render-smoke"}:
        script = "image_checks.py" if service == "image-checks" else "render_smoke.py"
        os.execv(sys.executable, [sys.executable, "/app/cloud/" + script, *arguments])
    if service == "init":
        for command in (("migrate", "--noinput"), ("seed_portal",), ("collectstatic", "--noinput")):
            subprocess.run([sys.executable, "manage.py", *command], check=True)
        return
    if service == "portal":
        from waitress import serve
        from config.wsgi import application
        # Only reachable through private Docker networking; preserve Caddy TLS
        # metadata so Django's HTTPS redirect and Secure cookies work.
        serve(application, host="0.0.0.0", port=8100, threads=8,
              trusted_proxy="*", trusted_proxy_count=1,
              trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for"},
              max_request_body_size=200 * 1024 * 1024)
        return
    commands = {
        "product-worker": [sys.executable, "manage.py", "run_product_worker"],
        "hr-worker": [sys.executable, "manage.py", "run_hr_worker"],
        "engineering-worker": [sys.executable, "manage.py", "run_engineering_worker"],
        "model-gateway": [sys.executable, "-m", "uvicorn", "model_gateway.app:app", "--host", "0.0.0.0",
                          "--port", "18410", "--no-access-log"],
        "manage": [sys.executable, "manage.py", *arguments],
    }
    if service not in commands:
        raise SystemExit("Unknown service")
    os.execv(sys.executable, commands[service])


if __name__ == "__main__":
    main()
