import io
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import call, patch

from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, override_settings

from portal.management.commands import run_product_worker as command


@override_settings(PRODUCT_P1_ENABLED=True)
class ProductWorkerCommandTests(SimpleTestCase):
    def wrap(self, cause):
        error = OperationalError("PRIVATE-DATABASE-MESSAGE")
        error.__cause__ = cause
        return error

    def lock(self, code):
        cause = sqlite3.OperationalError("PRIVATE-SQLITE-MESSAGE")
        cause.sqlite_errorcode = code
        return self.wrap(cause)

    def test_real_busy_lock_recovers_and_processes_the_next_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "isolated.sqlite3"
            first, second = sqlite3.connect(database, timeout=0), sqlite3.connect(database, timeout=0)
            try:
                first.execute("CREATE TABLE synthetic_counter (value INTEGER)")
                first.execute("INSERT INTO synthetic_counter VALUES (0)")
                first.commit()
                first.execute("BEGIN IMMEDIATE")
                try:
                    second.execute("UPDATE synthetic_counter SET value=1")
                except sqlite3.OperationalError as cause:
                    error = self.wrap(cause)
                else:
                    self.fail("The isolated second connection must encounter the write lock.")
            finally:
                first.rollback()
                first.close()
                second.close()
        self.assertEqual(error.__cause__.sqlite_errorcode, sqlite3.SQLITE_BUSY)
        with patch.object(command, "run_once", side_effect=[error, True, KeyboardInterrupt]) as run, \
                patch.object(command, "close_old_connections") as close, \
                patch.object(command.time, "sleep") as sleep, \
                self.assertLogs(command.__name__, level="WARNING") as logs:
            with self.assertRaises(KeyboardInterrupt):
                command.Command().handle(once=False)
        self.assertEqual(run.call_count, 3)
        close.assert_called_once_with()
        sleep.assert_called_once_with(1)
        self.assertNotIn("PRIVATE", " ".join(logs.output))
        self.assertNotIn(directory, " ".join(logs.output))

    def test_locked_and_extended_sqlite_lock_codes_also_recover(self):
        for code in (sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY_SNAPSHOT, sqlite3.SQLITE_LOCKED_SHAREDCACHE):
            with self.subTest(code=code), \
                    patch.object(command, "run_once", side_effect=[self.lock(code), True, KeyboardInterrupt]) as run, \
                    patch.object(command, "close_old_connections") as close, \
                    patch.object(command.time, "sleep") as sleep, \
                    patch.object(command.logging, "getLogger"):
                with self.assertRaises(KeyboardInterrupt):
                    command.Command().handle(once=False)
                self.assertEqual(run.call_count, 3)
                close.assert_called_once_with()
                sleep.assert_called_once_with(1)

    def test_lock_backoff_is_capped_and_resets_after_a_successful_iteration(self):
        busy = self.lock(sqlite3.SQLITE_BUSY)
        with patch.object(command, "run_once", side_effect=[busy, busy, busy, busy, True, busy, KeyboardInterrupt]), \
                patch.object(command, "close_old_connections") as close, \
                patch.object(command.time, "sleep") as sleep, \
                patch.object(command.logging, "getLogger"):
            with self.assertRaises(KeyboardInterrupt):
                command.Command().handle(once=False)
        self.assertEqual(close.call_count, 5)
        self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4), call(5), call(1)])

    def test_once_preserves_sqlite_lock_failure(self):
        error = self.lock(sqlite3.SQLITE_BUSY)
        with patch.object(command, "run_once", side_effect=error) as run, \
                patch.object(command, "close_old_connections") as close, \
                patch.object(command.time, "sleep") as sleep:
            with self.assertRaises(OperationalError) as caught:
                command.Command().handle(once=True)
        self.assertIs(caught.exception, error)
        run.assert_called_once_with()
        close.assert_not_called()
        sleep.assert_not_called()

    def test_non_lock_database_errors_permissions_and_cancellation_propagate(self):
        unconfirmed = sqlite3.OperationalError("database is locked")
        unconfirmed.sqlite_errorname = "SQLITE_BUSY"
        errors = [self.lock(sqlite3.SQLITE_IOERR), self.lock(sqlite3.SQLITE_READONLY),
                  self.lock(sqlite3.SQLITE_CORRUPT), self.wrap(unconfirmed),
                  OperationalError("database is locked"), PermissionError("forbidden"),
                  KeyboardInterrupt(), SystemExit(1)]
        for error in errors:
            with self.subTest(error=type(error).__name__, code=getattr(error.__cause__, "sqlite_errorcode", None)), \
                    patch.object(command, "run_once", side_effect=error) as run, \
                    patch.object(command, "close_old_connections") as close, \
                    patch.object(command.time, "sleep") as sleep:
                with self.assertRaises(type(error)) as caught:
                    command.Command().handle(once=False)
                self.assertIs(caught.exception, error)
                run.assert_called_once_with()
                close.assert_not_called()
                sleep.assert_not_called()

    def test_successful_once_and_idle_polling_keep_the_existing_behavior(self):
        for worked in (True, False):
            with self.subTest(worked=worked), patch.object(command, "run_once", return_value=worked) as run:
                output = io.StringIO()
                command.Command(stdout=output).handle(once=True)
                run.assert_called_once_with()
                self.assertTrue(output.getvalue().strip())
        with patch.object(command, "run_once", side_effect=[False, KeyboardInterrupt]), \
                patch.object(command.time, "sleep") as sleep:
            with self.assertRaises(KeyboardInterrupt):
                command.Command().handle(once=False)
        sleep.assert_called_once_with(2)

    @override_settings(PRODUCT_P1_ENABLED=False)
    def test_disabled_worker_never_attempts_a_claim(self):
        with patch.object(command, "run_once") as run:
            with self.assertRaises(CommandError):
                command.Command().handle(once=False)
        run.assert_not_called()
