import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("reviewed_enrichment_cli_tested", DIRECTORY / "apply_reviewed_enrichment.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class ReviewedEnrichmentCLITests(unittest.TestCase):
    def test_default_cli_is_inert_without_application_imports(self):
        before = set(sys.modules)
        output = io.StringIO()
        with patch.object(sys, "argv", ["apply_reviewed_enrichment.py"]), contextlib.redirect_stdout(output):
            cli.main()
        self.assertEqual(json.loads(output.getvalue()), {"mode": "inert", "database_writes": 0, "network_calls": 0,
            "model_calls": 0, "requires": "--execute --batch PATH --batch-sha256 HASH"})
        self.assertFalse(any(name.startswith(("django", "portal", "local_model", "socket", "sqlite3")) for name in set(sys.modules) - before))

    def test_hash_and_duplicate_keys_and_size_fail_before_application(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "batch.json"
            raw = b'{"a":1}'
            path.write_bytes(raw)
            self.assertEqual(cli.read_batch(path, hashlib.sha256(raw).hexdigest())[2], {"a": 1})
            self.assertEqual(path.read_bytes(), raw)
            with self.assertRaises(ValueError): cli.read_batch(path, "0" * 64)
            raw = b'{"a":1,"a":2}'
            path.write_bytes(raw)
            with self.assertRaises(ValueError): cli.read_batch(path, hashlib.sha256(raw).hexdigest())
            with patch.object(cli, "MAX_BYTES", 2), self.assertRaises(ValueError):
                cli.read_batch(path, hashlib.sha256(raw).hexdigest())

    def test_execute_requires_explicit_hash_before_loading_application(self):
        for digest in (None, "", "a" * 63, "A" * 64):
            with self.assertRaises(ValueError): cli.execute("not-opened", digest)

    def test_no_execute_does_not_read_supplied_private_batch(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["apply_reviewed_enrichment.py", "--batch", "does-not-exist"]), contextlib.redirect_stdout(output):
            cli.main()
        self.assertEqual(json.loads(output.getvalue())["database_writes"], 0)


if __name__ == "__main__":
    unittest.main()
