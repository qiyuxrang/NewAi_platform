"""Actual migrated SQLite restoration, overwrite refusal and rollback checks."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.db import connections
from django.test import TransactionTestCase

from portal.models import User
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_assistant_models import BaichuanJob

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'scripts/baichuan'))
import restore_repository_data as restore_tool


class RepositoryRestoreTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username='restore-operator',password='Synthetic-only-local-password')
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.database = Path(settings.DATABASES['default']['NAME'])
        connections.close_all()

    def restore(self):
        return restore_tool.restore(self.database,ROOT/'data/baichuan',self.actor.pk,self.output/'backup')

    def test_all_nine_tables_real_rows_and_cancelled_archive_only(self):
        result = self.restore()
        self.assertEqual(result['snapshot_validation']['rows'],25843)
        self.assertEqual(Company.objects.count(),1283)
        self.assertEqual(CompanyQualification.objects.count(),1460)
        self.assertEqual(BaichuanJob.objects.filter(status='cancelled').count(),1)
        self.assertFalse(BaichuanJob.objects.exclude(status='cancelled').exists())
        self.assertEqual(Company.objects.exclude(created_by=self.actor).count(),0)
        source = [json.loads(s) for s in (ROOT/'data/baichuan/tables/portal_company.jsonl').read_text(encoding='utf8').splitlines()]
        actual = Company.objects.get(pk=source[0]['id'])
        self.assertEqual(actual.phone,source[0]['phone'])
        self.assertEqual(actual.website,source[0]['website'])
        self.assertEqual(actual.version,source[0]['version'])
        with closing(sqlite3.connect(self.output/'backup/before.sqlite3')) as backup:
            self.assertEqual(backup.execute('select count(*) from portal_company').fetchone()[0],0)
            self.assertEqual(backup.execute('pragma quick_check').fetchone()[0],'ok')

    def test_existing_manual_company_is_never_overwritten(self):
        Company.objects.create(name='人工资料必须保留',phone='manual-value',created_by=self.actor,updated_by=self.actor)
        connections.close_all()
        with self.assertRaisesRegex(ValueError,'not empty'):
            self.restore()
        self.assertEqual(Company.objects.get().phone,'manual-value')
        self.assertFalse((self.output/'backup').exists())

    def test_repeated_restore_refuses_without_writes(self):
        self.restore()
        connections.close_all()
        with self.assertRaisesRegex(ValueError,'not empty'):
            restore_tool.restore(self.database,ROOT/'data/baichuan',self.actor.pk,self.output/'second')
        self.assertEqual(Company.objects.count(),1283)
        self.assertFalse((self.output/'second').exists())

    def test_missing_actor_refuses_before_backup(self):
        with self.assertRaisesRegex(ValueError,'active user'):
            restore_tool.restore(self.database,ROOT/'data/baichuan',987654321,self.output/'backup')
        self.assertFalse((self.output/'backup').exists())

    def test_foreign_key_failure_rolls_back_complete_catalog_and_job(self):
        original = restore_tool.checked_snapshot
        def broken(directory):
            manifest,rows,validation = original(directory)
            rows['portal_baichuancertificate'][0]['evidence_id'] = 'f'*32
            return manifest,rows,validation
        with patch.object(restore_tool,'checked_snapshot',side_effect=broken):
            with self.assertRaisesRegex(ValueError,'Foreign key'):
                self.restore()
        self.assertEqual(Company.objects.count(),0)
        self.assertEqual(BaichuanJob.objects.count(),0)
        self.assertTrue((self.output/'backup/before.sqlite3').is_file())

    def test_path_escape_rejected_before_database_open(self):
        directory = self.output/'bad-snapshot'
        directory.mkdir()
        manifest = json.loads((ROOT/'data/baichuan/manifest.json').read_text(encoding='utf8'))
        manifest['files'][0]['file'] = '../outside'
        (self.output/'outside').write_text('unrelated')
        (directory/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        shutil.copyfile(ROOT/'data/baichuan/source-index.json',directory/'source-index.json')
        # Put the escape first; rejection does not depend on other files existing.
        manifest['tables'][next(iter(manifest['tables']))]['file'] = '../outside'
        (directory/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'escapes'):
            restore_tool.restore(self.database,directory,self.actor.pk,self.output/'backup')
        self.assertFalse((self.output/'backup').exists())

    def test_corrupt_snapshot_rejected_without_database_writes(self):
        directory = self.output/'bad-snapshot'
        shutil.copytree(ROOT/'data/baichuan',directory)
        with (directory/'tables/portal_company.jsonl').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(AssertionError):
            restore_tool.restore(self.database,directory,self.actor.pk,self.output/'backup')
        self.assertEqual(Company.objects.count(),0)
        self.assertFalse((self.output/'backup').exists())
