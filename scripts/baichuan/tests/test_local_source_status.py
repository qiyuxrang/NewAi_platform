"""Source receipt validation uses disposable directories, never a business DB."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('local_dev', Path(__file__).resolve().parents[1] / 'local_dev.py')
local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local)


class SourceStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.value = {'source_kind': 'local_original_excel', 'import_completed': True,
                      'source_sha256': 'a' * 64, 'imported_company_count': 1462,
                      'historical_enrichment_restored': False}

    def save(self, value):
        (self.root / 'source-status.json').write_text(json.dumps(value), encoding='utf-8')

    def test_absent_or_malformed_receipts_stay_unconnected(self):
        self.assertFalse(local.source_state(self.root)['source_connected'])
        (self.root / 'source-status.json').write_text('{', encoding='utf-8')
        self.assertEqual(local.source_state(self.root)['environment_label'], local.EMPTY_LABEL)
        self.save([])
        self.assertFalse(local.source_state(self.root)['source_connected'])

    def test_incomplete_or_false_claims_do_not_connect(self):
        for key, value in [('import_completed', False), ('source_sha256', 'not-a-hash'),
                           ('imported_company_count', 0), ('imported_company_count', True),
                           ('source_kind', 'production'), ('historical_enrichment_restored', True)]:
            with self.subTest(key=key, value=value):
                self.save({**self.value, key: value})
                self.assertFalse(local.source_state(self.root)['source_connected'])

    def test_successful_local_receipt_keeps_isolation_and_historical_gap(self):
        self.save(self.value)
        result = local.source_state(self.root)
        self.assertTrue(result['source_connected'])
        self.assertTrue(result['local_source_only'])
        self.assertEqual(result['dataset_kind'], 'isolation')
        self.assertFalse(result['historical_enrichment_restored'])
        self.assertEqual(result['environment_label'], local.SOURCE_LABEL)

    def test_environment_uses_same_label_without_changing_database_or_accounts(self):
        self.save(self.value)
        (self.root / 'environment.json').write_text(json.dumps({'kind': local.IDENTITY}), encoding='utf-8')
        (self.root / 'secrets.json').write_text(json.dumps({'portal': 'test-only', 'platform': 'test-only'}), encoding='utf-8')
        with patch.object(local, 'RUNTIME', self.root), patch.object(local, 'local_model_enabled', return_value=False):
            env = local.environment()
        self.assertEqual(env['PORTAL_BAICHUAN_ENVIRONMENT_LABEL'], local.SOURCE_LABEL)
        self.assertEqual(env['PORTAL_BAICHUAN_DATASET_KIND'], 'isolation')
        self.assertEqual(env['PORTAL_SQLITE_PATH'], str(self.root / 'portal.sqlite3'))
        self.assertFalse((self.root / 'accounts.json').exists())
        self.assertFalse((self.root / 'portal.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
