"""Pure temporary-directory configuration checks; no application startup."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "local_search.py"
spec = importlib.util.spec_from_file_location("baichuan_local_search_tested", SCRIPT)
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


class LocalSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / ".runtime" / "baichuan-ai-local"
        self.runtime.mkdir(parents=True)
        (self.runtime / "environment.json").write_text(json.dumps({"kind": search.IDENTITY}), encoding="utf-8")
        self.patcher = patch.object(search, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.key = self.root / "input-key.txt"
        self.token = "synthetic_test_token_123456789"
        self.key.write_text(self.token + "\n", encoding="ascii")

    def test_default_status_zero_imports_or_calls_and_no_new_files(self):
        before = set(sys.modules)
        files = list(self.runtime.iterdir())
        with patch.object(search.subprocess, "run", side_effect=AssertionError("No OS subprocess in status")):
            result = search.status()
        self.assertEqual(result, {"configured": False, "provider": None, "credential": "not_configured",
                                  "enabled": False, "quality_status": "quality_not_validated"})
        self.assertEqual(files, list(self.runtime.iterdir()))
        self.assertFalse(any(name.startswith(("django", "portal", "sqlite3", "socket", "urllib"))
                             for name in set(sys.modules) - before))

    def test_configure_both_existing_auth_contracts_no_key_in_state_or_environment(self):
        for provider, token_name in search.TOKEN_NAMES.items():
            with self.subTest(provider=provider):
                result = search.configure(provider, self.key)
                self.assertTrue(result["configured"])
                self.assertNotIn(self.token, json.dumps(result))
                link = (self.runtime / "search-link.json").read_text()
                self.assertNotIn(self.token, link)
                stored = json.loads((self.runtime / "search-credentials.json").read_text())
                self.assertEqual(stored["token"], self.token)
                for service in ("portal", "baichuan-worker"):
                    values = search.backend_search_environment(service)
                    self.assertEqual(values, {"PRODUCT_WEB_SEARCH_ENABLED": "false",
                        "PRODUCT_WEB_SEARCH_PROVIDER": provider, "PRODUCT_WEB_SEARCH_TOKEN_ENV": token_name})
                    self.assertNotIn(token_name, values)
                self.assertEqual(self.key.read_text(), self.token + "\n")
                if os.name == "nt":
                    acl = subprocess.run(["icacls", str(self.runtime / "search-credentials.json")],
                                         capture_output=True, text=True, check=True).stdout
                    self.assertNotIn("(I)", acl)
                else:
                    self.assertEqual((self.runtime / "search-credentials.json").stat().st_mode & 0o777, 0o600)
                (self.runtime / "search-link.json").unlink()
                (self.runtime / "search-credentials.json").unlink()

    def test_no_gateway_frontend_or_unknown_service_can_get_environment(self):
        for service in ("gateway", "model-gateway", "frontend", "worker", ""):
            with self.assertRaises(ValueError):
                search.backend_search_environment(service)

    def test_no_key_format_leaks_or_partial_files(self):
        for raw in (b"short", b"two_lines_123\nsecond_123", b" " + b"x" * 20,
                    b"x" * 513, b"x" * 20 + b"\x7f", b"x" * 20 + b"\r", b"x" * 20 + b"\n\n",
                    "not_ascii_凭据".encode()):
            self.key.write_bytes(raw)
            with self.assertRaises(ValueError):
                search.configure("tavily", self.key)
            self.assertFalse((self.runtime / "search-link.json").exists())
            self.assertFalse((self.runtime / "search-credentials.json").exists())

    def test_crlf_is_one_line(self):
        self.key.write_bytes(self.token.encode() + b"\r\n")
        self.assertEqual(search._key(self.key), self.token)

    def test_unknown_provider_and_unknown_owner_are_rejected(self):
        with self.assertRaises(ValueError):
            search.configure("other", self.key)
        (self.runtime / "environment.json").write_text('{"kind":"other"}')
        with self.assertRaises(ValueError):
            search.status()
        with self.assertRaises(ValueError):
            search.configure("brave", self.key)
        (self.runtime / "environment.json").write_text('[]')
        with self.assertRaises(ValueError):
            search.status()

    def test_existing_files_never_overwritten(self):
        for filename in ("search-link.json", "search-credentials.json"):
            path = self.runtime / filename
            path.write_text("unknown user content")
            with self.assertRaises(ValueError):
                search.configure("tavily", self.key)
            self.assertEqual(path.read_text(), "unknown user content")
            with self.assertRaises(ValueError):
                search.status()
            path.unlink()
        search.configure("tavily", self.key)
        before = {path.name: path.read_bytes() for path in self.runtime.iterdir()}
        with self.assertRaises(ValueError):
            search.configure("brave", self.key)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.runtime.iterdir()})

    def test_status_does_not_read_credentials(self):
        search.configure("brave", self.key)
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if path.name == "search-credentials.json":
                raise AssertionError("Status must never read the token")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            self.assertTrue(search.status()["configured"])
            self.assertEqual(search.backend_search_environment("portal")["PRODUCT_WEB_SEARCH_ENABLED"], "false")

    def test_failure_writing_state_removes_only_own_new_credentials(self):
        original = search._private_create
        def create(path, value):
            if path.name == "search-link.json":
                raise OSError("synthetic failure")
            return original(path, value)
        with patch.object(search, "_private_create", create), self.assertRaises(OSError):
            search.configure("tavily", self.key)
        self.assertFalse((self.runtime / "search-credentials.json").exists())
        self.assertEqual(self.key.read_text(), self.token + "\n")

    def test_reparse_path_is_rejected_without_reading_target(self):
        info = type("ReparseInfo", (), {"st_mode": 0o100600, "st_file_attributes": 1024})()
        with patch.object(Path, "lstat", return_value=info), self.assertRaises(ValueError):
            search.configure("tavily", self.key)

    def test_default_cli_and_errors_never_render_token(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["local_search.py"]), contextlib.redirect_stdout(output):
            search.main()
        self.assertFalse(json.loads(output.getvalue())["configured"])
        output = io.StringIO()
        with patch.object(sys, "argv", ["local_search.py", "activate"]), contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit):
                search.main()
        self.assertNotIn(self.token, output.getvalue())


if __name__ == "__main__":
    unittest.main()
