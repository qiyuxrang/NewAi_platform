"""Real file-backed SQLite reservation contention; no gateway/network calls."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
import unittest

from django.core.management import call_command
from django.db import OperationalError, connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.test import override_settings
from django.utils import timezone

from portal import model_gateway
from portal.models import GatewayModel, ModelCallLog, ModelRoute, Module, Provider, User


class SQLiteReservationTests(unittest.TestCase):
    """Swap only the current thread's default connection to a synthetic database."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temporary = TemporaryDirectory(prefix="gateway-reservation-")
        cls.template = Path(cls.temporary.name) / "template.sqlite3"
        cls.database = deepcopy(connections["default"].settings_dict)
        cls.database.update(ENGINE="django.db.backends.sqlite3", NAME=str(cls.template))
        cls.database["OPTIONS"] = {"timeout": 0.8, "transaction_mode": "DEFERRED"}
        original = connections["default"]
        isolated = DatabaseWrapper(deepcopy(cls.database), "default")
        connections["default"] = isolated
        try:
            call_command("migrate", verbosity=0, interactive=False, stdout=StringIO())
        except BaseException:
            cls.temporary.cleanup()
            raise
        finally:
            isolated.close()
            connections["default"] = original

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.path = Path(self.temporary.name) / (self._testMethodName + ".sqlite3")
        shutil.copyfile(self.template, self.path)
        self.config = deepcopy(self.database)
        self.config["NAME"] = str(self.path)
        self.original = connections["default"]
        self.connection = DatabaseWrapper(deepcopy(self.config), "default")
        connections["default"] = self.connection
        self.addCleanup(self.restore_connection)
        self.user = User.objects.create(username="isolated-reserver", must_change_password=False)
        self.other_user = User.objects.create(username="isolated-other", must_change_password=False)
        provider = Provider.objects.create(code="isolated", name="isolated", enabled=True,
                                           base_url="https://provider.example/v1",
                                           api_key_env="PORTAL_MODEL_KEY_ISOLATED")
        self.model = GatewayModel.objects.create(provider=provider, name="isolated", enabled=True,
                                                model_name="isolated", timeout_seconds=20)
        module, _ = Module.objects.get_or_create(code="isolated", defaults={"name": "isolated"})
        self.route = ModelRoute.objects.create(code="isolated", name="isolated", module=module,
                                              model=self.model, enabled=True)

    def restore_connection(self):
        self.connection.close()
        connections["default"] = self.original

    def writer(self):
        writer = sqlite3.connect(self.path, timeout=0.8, isolation_level=None)
        self.addCleanup(writer.close)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE portal_user SET grant_version = grant_version WHERE id = ?", (self.user.pk,))
        return writer

    def reserve(self, user=None, purpose="business", route=True, started=None, inserted=None, release=None,
                statements=None):
        connection = DatabaseWrapper(deepcopy(self.config), "default")
        connections["default"] = connection

        def observe(execute, sql, params, many, context):
            if statements is not None:
                statements.append(sql)
            if started and sql.lstrip().upper().startswith(("SELECT", "UPDATE")):
                started.set()
            result = execute(sql, params, many, context)
            if inserted and sql.lstrip().upper().startswith("INSERT INTO \"PORTAL_MODELCALLLOG\""):
                inserted.set()
                if not release.wait(3):
                    raise AssertionError("reservation release was not signalled")
            return result

        try:
            with connection.execute_wrapper(observe):
                return model_gateway._reserve(user or self.user, self.model, purpose,
                                               self.route if route else None, "isolated-version")
        finally:
            connection.close()

    def test_deferred_read_then_write_reproduces_sqlite_busy(self):
        # This is the old transaction order, independently of the fixed code.
        reader = sqlite3.connect(self.path, timeout=0.8, isolation_level=None)
        writer = sqlite3.connect(self.path, timeout=0.8, isolation_level=None)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT grant_version FROM portal_user WHERE id = ?", (self.user.pk,)).fetchone()
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE portal_user SET grant_version = grant_version WHERE id = ?", (self.user.pk,))
            started = monotonic()
            with self.assertRaises(sqlite3.OperationalError) as caught:
                reader.execute("UPDATE portal_user SET grant_version = grant_version WHERE id = ?", (self.user.pk,))
            self.assertEqual(caught.exception.sqlite_errorname, "SQLITE_BUSY")
            self.assertLess(monotonic() - started, 0.4)  # Busy timeout cannot resolve the upgrade deadlock.
        finally:
            reader.close()
            writer.close()

    def test_reservation_waits_for_writer_and_preserves_grant_version(self):
        writer = self.writer()
        entered = Event()
        statements = []
        started = monotonic()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.reserve, started=entered, statements=statements)
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(FutureTimeout):
                    future.result(timeout=0.12)
            finally:
                writer.rollback()
            record = future.result(timeout=2)
        self.assertGreaterEqual(monotonic() - started, 0.12)
        first_access = next(sql for sql in statements if sql.lstrip().upper().startswith(("SELECT", "UPDATE")))
        self.assertTrue(first_access.startswith('UPDATE "portal_user"'), first_access)
        self.assertEqual(record.status, "pending")
        self.assertEqual(record.config_version, "isolated-version")
        self.assertEqual(ModelCallLog.objects.count(), 1)
        self.assertEqual(User.objects.get(pk=self.user.pk).grant_version, self.user.grant_version)
        self.assertEqual(User.objects.get(pk=self.user.pk).session_version, self.user.session_version)

    def test_writer_timeout_is_bounded_and_creates_no_reservation(self):
        writer = self.writer()
        started = monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(OperationalError) as caught:
                    pool.submit(self.reserve).result(timeout=3)
            self.assertEqual(caught.exception.__cause__.sqlite_errorname, "SQLITE_BUSY")
            elapsed = monotonic() - started
            self.assertGreaterEqual(elapsed, 0.6)
            self.assertLess(elapsed, 2)
        finally:
            writer.rollback()
        self.assertFalse(ModelCallLog.objects.exists())

    def competing_reservations(self, other_user=None, purpose="business", route=True):
        inserted, release, entered = Event(), Event(), Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.reserve, purpose=purpose, route=route, inserted=inserted, release=release)
            try:
                self.assertTrue(inserted.wait(2))
                second = pool.submit(self.reserve, user=other_user, purpose=purpose, route=route, started=entered)
                self.assertTrue(entered.wait(2))
                with self.assertRaises(FutureTimeout):
                    second.result(timeout=0.12)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=2).status, "pending")
            with self.assertRaises(model_gateway.GatewayError) as caught:
                second.result(timeout=2)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(ModelCallLog.objects.count(), 1)
        return caught.exception.code

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=1)
    def test_pending_limit_serializes_different_users(self):
        self.assertEqual(self.competing_reservations(other_user=self.other_user), "busy")

    def test_route_rate_limit_serializes_same_user(self):
        self.route.max_calls_per_minute = 1
        self.route.save(update_fields=["max_calls_per_minute"])
        self.assertEqual(self.competing_reservations(), "rate_limited")

    def test_probe_limit_serializes_same_user(self):
        self.assertEqual(self.competing_reservations(purpose="test", route=False), "rate_limited")

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=1)
    def test_stale_pending_and_grant_checks_keep_existing_semantics(self):
        stale = ModelCallLog.objects.create(actor=self.other_user, model=self.model, purpose="business",
                                             status="pending", duration_ms=0)
        ModelCallLog.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(seconds=self.model.timeout_seconds + 31))
        record = model_gateway._reserve(self.user, self.model, "business", self.route)
        self.assertEqual(record.status, "pending")
        self.assertEqual(User.objects.get(pk=self.user.pk).grant_version, self.user.grant_version)
        User.objects.filter(pk=self.user.pk).update(session_version=self.user.session_version + 1)
        with self.assertRaises(model_gateway.GatewayError) as caught:
            model_gateway._fresh_user(self.user)
        self.assertEqual(caught.exception.code, "forbidden")

    def test_non_sqlite_branch_keeps_original_selects_without_noop_update(self):
        # Exercise the vendor branch on the same real connection; only its vendor
        # label changes. This verifies the guard, not a PostgreSQL integration.
        original_vendor = self.connection.vendor
        statements = []
        self.connection.vendor = "postgresql"
        try:
            with self.connection.execute_wrapper(
                lambda execute, sql, params, many, context:
                    (statements.append(sql), execute(sql, params, many, context))[1]
            ):
                model_gateway._reserve(self.user, self.model, "business", self.route)
        finally:
            self.connection.vendor = original_vendor
        self.assertFalse(any(sql.lstrip().upper().startswith("UPDATE") for sql in statements))
        self.assertTrue(any(sql.startswith('SELECT "portal_user"') for sql in statements))
