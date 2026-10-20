"""Prepare owned backend search credentials, with search disabled until validation.

No network, database, Django or model imports. No activation command exists.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "baichuan_ai_isolated_local_v1"
LINK_KIND = "baichuan_owned_search_link_v1"
CREDENTIAL_KIND = "baichuan_owned_search_credentials_v1"
TOKEN_NAMES = {"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}


def _plain_path(path):
    path = Path(os.path.abspath(path))
    for ancestor in [path, *path.parents]:
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)):
            raise ValueError("Symbolic links and Windows reparse paths are refused")
    return path


def _runtime():
    base = _plain_path(ROOT)
    runtime = _plain_path(base / ".runtime" / "baichuan-ai-local")
    if runtime.resolve() != base.resolve() / ".runtime" / "baichuan-ai-local":
        raise ValueError("Runtime is outside this workspace")
    if not runtime.is_dir():
        raise ValueError("Initialize the owned local environment first")
    marker = _plain_path(runtime / "environment.json")
    if not marker.is_file() or marker.stat().st_size > 16384:
        raise ValueError("Owned environment marker is missing")
    owner = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(owner, dict) or owner.get("kind") != IDENTITY:
        raise ValueError("Runtime does not belong to this local environment")
    return runtime


def _paths(runtime):
    return (_plain_path(runtime / "search-link.json"),
            _plain_path(runtime / "search-credentials.json"))


def _link(runtime):
    link, credentials = _paths(runtime)
    if not link.exists() and not credentials.exists():
        return None
    if not link.is_file() or not credentials.is_file() or link.stat().st_size > 16384:
        raise ValueError("Incomplete or unknown search configuration; existing files preserved")
    value = json.loads(link.read_text(encoding="utf-8"))
    if (not isinstance(value, dict)
            or set(value) != {"kind", "provider", "enabled", "quality_status", "credential_file"}
            or value["kind"] != LINK_KIND or value["provider"] not in TOKEN_NAMES
            or value["enabled"] is not False or value["quality_status"] != "quality_not_validated"
            or value["credential_file"] != credentials.name):
        raise ValueError("Unknown or activated search configuration; existing files preserved")
    return value


def status():
    value = _link(_runtime())
    return {"configured": bool(value), "provider": value["provider"] if value else None,
            "credential": "masked" if value else "not_configured", "enabled": False,
            "quality_status": "quality_not_validated"}


def _key(path):
    source = _plain_path(path)
    if not source.is_file() or source.stat().st_size > 514:
        raise ValueError("Key file must contain one bounded ASCII token")
    with source.open("rb") as stream:
        raw = stream.read(515)
    if len(raw) > 514:
        raise ValueError("Key file must contain one bounded ASCII token")
    if raw.endswith(b"\r\n"):
        raw = raw[:-2]
    elif raw.endswith(b"\n"):
        raw = raw[:-1]
    if not 10 <= len(raw) <= 512 or any(byte < 33 or byte > 126 for byte in raw):
        raise ValueError("Key file must contain a single ASCII token of 10 to 512 characters")
    return raw.decode("ascii")


def _private_create(path, value):
    """Set current-user-only access BEFORE any credential bytes are written."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if os.name == "nt":
            result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                    capture_output=True, text=True, check=True)
            rows = list(csv.reader(io.StringIO(result.stdout.strip())))
            sid = rows[0][-1] if len(rows) == 1 and rows[0] else ""
            if not re.fullmatch(r"S-1-[0-9-]+", sid):
                raise ValueError("Unable to establish the current Windows identity")
            subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "*" + sid + ":(F)"],
                           capture_output=True, check=True)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = None
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def configure(provider, key_file):
    if provider not in TOKEN_NAMES:
        raise ValueError("Unsupported search provider")
    runtime = _runtime()
    link, credentials = _paths(runtime)
    if link.exists() or credentials.exists():
        raise ValueError("Search configuration already exists; existing files preserved")
    token = _key(key_file)
    # O_EXCL prevents concurrent configuration from replacing existing files.
    _private_create(credentials, {"kind": CREDENTIAL_KIND, "provider": provider, "token": token})
    try:
        _private_create(link, {"kind": LINK_KIND, "provider": provider, "enabled": False,
                              "quality_status": "quality_not_validated", "credential_file": credentials.name})
    except Exception:
        credentials.unlink(missing_ok=True)
        raise
    return status()


def backend_search_environment(service):
    """Future local portal/worker hook. Fail closed; never release a token yet.

    A separate tested quality-receipt/activation implementation is required
    before any service can receive credentials or enable search. This helper
    does not inspect credentials, inherit environment values or mutate os.environ.
    """
    if service not in {"portal", "baichuan-worker"}:
        raise ValueError("Search settings are restricted to owned backend services")
    current = status()
    result = {"PRODUCT_WEB_SEARCH_ENABLED": "false"}
    if current["configured"]:
        result.update(PRODUCT_WEB_SEARCH_PROVIDER=current["provider"],
                      PRODUCT_WEB_SEARCH_TOKEN_ENV=TOKEN_NAMES[current["provider"]])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("status")
    config = commands.add_parser("configure")
    config.add_argument("--provider", choices=TOKEN_NAMES, required=True)
    config.add_argument("--key-file", required=True)
    args = parser.parse_args()
    try:
        result = configure(args.provider, args.key_file) if args.command == "configure" else status()
    except (ValueError, OSError, json.JSONDecodeError, subprocess.SubprocessError):
        # Never render exception details: paths/process errors can contain input.
        parser.exit(2, "Owned search configuration rejected; existing user files preserved.\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
