"""Real local SQLite contention; no application database or network access."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from django.conf import settings
from django.db import OperationalError, connections, transaction
from django.db.backends.sqlite3.base import DatabaseWrapper


@unittest.skipUnless(settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3',
                     'Local SQLite configuration only')
class SQLiteTransactionTests(unittest.TestCase):
    def test_atomic_read_then_write_waits_before_reading_instead_of_failing_lock_upgrade(self):
        options = settings.DATABASES['default']['OPTIONS']
        self.assertEqual(options, {'timeout': 30, 'transaction_mode': 'IMMEDIATE'})
        for mode in ('DEFERRED', options['transaction_mode']):
            with self.subTest(mode=mode), TemporaryDirectory(prefix='sqlite-transaction-') as directory:
                path = Path(directory) / 'isolated.sqlite3'
                writer = sqlite3.connect(path, isolation_level=None)
                writer.execute('CREATE TABLE counter (value INTEGER NOT NULL)')
                writer.execute('INSERT INTO counter VALUES (0)')
                writer.execute('BEGIN IMMEDIATE')
                writer.execute('UPDATE counter SET value = 10')
                entered = Event()
                config = deepcopy(connections['default'].settings_dict)
                config.update(NAME=str(path), OPTIONS={**options, 'transaction_mode': mode})

                def read_then_write():
                    alias = 'sqlite_transaction_probe'
                    connection = DatabaseWrapper(config, alias)
                    connections[alias] = connection

                    def observe(execute, sql, params, many, context):
                        if sql.startswith('BEGIN'):
                            entered.set()
                        return execute(sql, params, many, context)

                    try:
                        with connection.execute_wrapper(observe), transaction.atomic(using=alias):
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT value FROM counter')
                                value = cursor.fetchone()[0]
                                cursor.execute('UPDATE counter SET value = %s', [value + 1])
                    finally:
                        connection.close()

                try:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(read_then_write)
                        try:
                            self.assertTrue(entered.wait(2))
                            if mode == 'DEFERRED':
                                with self.assertRaises(OperationalError) as caught:
                                    future.result(timeout=1)
                                self.assertEqual(caught.exception.__cause__.sqlite_errorname, 'SQLITE_BUSY')
                            else:
                                with self.assertRaises(FutureTimeout):
                                    future.result(timeout=0.1)
                        finally:
                            writer.rollback()
                        if mode == 'IMMEDIATE':
                            future.result(timeout=2)
                    self.assertEqual(writer.execute('SELECT value FROM counter').fetchone()[0],
                                     1 if mode == 'IMMEDIATE' else 0)
                finally:
                    writer.close()
