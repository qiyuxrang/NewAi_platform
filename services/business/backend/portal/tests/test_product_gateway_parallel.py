"""Real isolated SQLite gateway concurrency; only outbound model I/O is mocked."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import StringIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest import TestCase
from unittest.mock import patch

from django.core.management import call_command
from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.test import override_settings

from portal import model_gateway
from portal.models import AuditEvent, GatewayModel, ModelCallLog, ModelRoute, Module, Provider, Role, User


class GatewayParallelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temporary = TemporaryDirectory(prefix="product-gateway-parallel-")
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
        path = Path(self.temporary.name) / (self._testMethodName + ".sqlite3")
        shutil.copyfile(self.template, path)
        self.config = deepcopy(self.database)
        self.config["NAME"] = str(path)
        original = connections["default"]
        connection = DatabaseWrapper(deepcopy(self.config), "default")
        connections["default"] = connection

        def restore():
            connection.close()
            connections["default"] = original
        self.addCleanup(restore)

        self.user = User.objects.create(username="parallel-writer", must_change_password=False)
        module = Module.objects.create(code="parallel-product", name="并行写作")
        role = Role.objects.create(code="parallel-product", name="并行写作")
        role.modules.add(module)
        self.user.roles.add(role)
        provider = Provider.objects.create(code="parallel", name="隔离服务", protocol="openai_chat",
                                           base_url="https://provider.example/v1",
                                           api_key_env="PORTAL_MODEL_KEY_PARALLEL", enabled=True)
        model = GatewayModel.objects.create(provider=provider, name="隔离模型", model_name="isolated",
                                            enabled=True, timeout_seconds=20)
        self.route = ModelRoute.objects.create(code="parallel", name="隔离路由", module=module,
                                              model=model, enabled=True, max_calls_per_minute=20)
        self.closed = []

    def generate(self, marker, finished=None):
        connection = DatabaseWrapper(deepcopy(self.config), "default")
        connections["default"] = connection
        try:
            return model_gateway.generate_for_use(self.user, self.route.code,
                                                   [{"role": "user", "content": marker}])
        finally:
            connection.close()
            self.closed.append(connection.connection is None)
            if finished:
                finished.set()

    @staticmethod
    def reply(marker):
        return {"content": marker + "-result", "prompt_tokens": 3, "completion_tokens": 4}

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=2)
    def test_real_parallel_reservations_reverse_completion_logs_and_close_connections(self):
        first_entered, second_finished = Event(), Event()
        in_flight = Barrier(2, timeout=5)

        def request(payload):
            marker = payload["messages"][0]["content"]
            self.assertFalse(connections["default"].in_atomic_block)
            if marker == "first":
                first_entered.set()
            in_flight.wait()
            if marker == "first":
                self.assertTrue(second_finished.wait(5))
            return self.reply(marker)

        with patch("portal.model_gateway._request_gateway", side_effect=request) as outbound:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.generate, "first")
                self.assertTrue(first_entered.wait(5))
                second = pool.submit(self.generate, "second", second_finished)
                self.assertEqual(second.result(timeout=8)["content"], "second-result")
                self.assertEqual(first.result(timeout=8)["content"], "first-result")
        self.assertEqual(outbound.call_count, 2)
        records = list(ModelCallLog.objects.order_by("pk"))
        self.assertEqual([record.status for record in records], ["success", "success"])
        self.assertEqual([(record.prompt_tokens, record.completion_tokens) for record in records],
                         [(3, 4), (3, 4)])
        audits = list(AuditEvent.objects.filter(action="model_call").order_by("pk"))
        self.assertEqual([(item.target, item.result) for item in audits],
                         [(str(records[1].pk), "success"), (str(records[0].pk), "success")])
        self.assertEqual(self.closed, [True, True])
        self.assertFalse(ModelCallLog.objects.filter(status="pending").exists())

    def assert_inflight_limit(self, expected):
        entered, release = Event(), Event()

        def request(payload):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.reply("first")

        with patch("portal.model_gateway._request_gateway", side_effect=request) as outbound:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.generate, "first")
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(model_gateway.GatewayError) as caught:
                        pool.submit(self.generate, "second").result(timeout=5)
                    self.assertEqual(caught.exception.code, expected)
                    self.assertEqual(caught.exception.status, 429)
                    self.assertEqual(ModelCallLog.objects.filter(status="pending").count(), 1)
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=5)["content"], "first-result")
        self.assertEqual(outbound.call_count, 1)
        self.assertEqual(list(ModelCallLog.objects.values_list("status", flat=True)), ["success"])
        self.assertEqual(AuditEvent.objects.filter(action="model_call", result="success").count(), 1)
        self.assertEqual(self.closed, [True, True])

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=1)
    def test_pending_limit_is_respected_while_request_is_in_flight(self):
        self.assert_inflight_limit("busy")

    @override_settings(MODEL_MAX_PENDING_PER_MODEL=2)
    def test_route_rpm_limit_is_respected_while_request_is_in_flight(self):
        self.route.max_calls_per_minute = 1
        self.route.save(update_fields=["max_calls_per_minute"])
        self.assert_inflight_limit("rate_limited")

    def test_inflight_revocation_discards_reply_and_closes_connection(self):
        entered, release = Event(), Event()

        def request(payload):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.reply("revoked")

        with patch("portal.model_gateway._request_gateway", side_effect=request):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.generate, "first")
                try:
                    self.assertTrue(entered.wait(5))
                    self.user.roles.clear()
                finally:
                    release.set()
                with self.assertRaises(model_gateway.GatewayError) as caught:
                    future.result(timeout=5)
        self.assertEqual(caught.exception.code, "forbidden")
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")
        self.assertEqual(AuditEvent.objects.get(action="model_call").result, "forbidden")
        self.assertEqual(self.closed, [True])
