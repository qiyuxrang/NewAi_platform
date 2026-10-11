from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection
from django.db.models import F
from django.test import override_settings
from django.utils import timezone

from portal import product_worker
from portal.model_gateway import GatewayError, _reserve
from portal.models import GatewayModel, ModelCallLog, ModelRoute, Module, Provider
from portal.product_models import DocumentAttempt, DocumentTask
from portal.product_service import append_revision, digest

from .base import PortalTestCase


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_MAX_MODEL_CALLS=10, PRODUCT_LEASE_SECONDS=10)
class ProductModelPacingTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("pacing-writer", "product")
        self.now = timezone.now()
        self.elapsed = 0
        self.sleeps = []
        self.after_sleep = None
        self.transaction_depth = len(connection.atomic_blocks)
        self.clock_patch = patch("portal.product_worker.timezone.now", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.monotonic_patch = patch("portal.product_worker.monotonic", side_effect=lambda: self.elapsed)
        self.monotonic_patch.start()
        self.addCleanup(self.monotonic_patch.stop)
        self.sleep_patch = patch("portal.product_worker.sleep", side_effect=self.advance)
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)
        payload = {"project": "隔离限流测试", "items": [], "conditions": []}
        self.task = DocumentTask.objects.create(owner=self.owner, title="限流测试", state="QUEUED",
            stage="BLUEPRINT", pending_action="blueprint", idempotency_key="pacing-test", payload_hash=digest(payload))
        revision = append_revision(self.task, "input", payload, actor=self.owner)
        self.task.input_version = revision.version
        self.task.save(update_fields=["input_version"])
        self.claim = product_worker.claim_task()
        self.attempt = DocumentAttempt.objects.get(pk=self.claim[2])
        provider = Provider.objects.create(code="pacing", name="隔离", base_url="https://example.invalid",
                                           api_key_env="PORTAL_MODEL_KEY_PACING")
        self.model = GatewayModel.objects.create(name="隔离", model_name="isolated", provider=provider)
        self.route = ModelRoute.objects.create(code="pacing-review", name="隔离", model=self.model,
            module=Module.objects.get(code="product"), max_calls_per_minute=1)

    def advance(self, seconds):
        # TestCase's own outer transaction is expected; the worker must release
        # all of its nested atomic blocks before sleeping.
        self.assertEqual(len(connection.atomic_blocks), self.transaction_depth)
        self.assertLessEqual(seconds, 1)
        self.sleeps.append(seconds)
        self.elapsed += seconds
        self.now += timedelta(seconds=seconds)
        if self.after_sleep:
            self.after_sleep()

    def log(self, *, actor=None, route=None, status="success", seconds_ago=0):
        record = ModelCallLog.objects.create(actor=actor or self.owner, route=route or self.route,
            model=self.model, purpose="business", status=status, duration_ms=0)
        ModelCallLog.objects.filter(pk=record.pk).update(created_at=self.now - timedelta(seconds=seconds_ago))
        return record

    def call(self, gateway):
        with patch("portal.product_worker.generate_for_use", gateway):
            return product_worker._model(*self.claim, self.route.code, {"action": "independent_review"})

    def reply(self):
        return {"content": '{"passed":true,"issues":[]}'}

    def assert_stopped(self, code):
        gateway = Mock(return_value=self.reply())
        with self.assertRaises(product_worker.ExecutionError) as error:
            self.call(gateway)
        self.assertEqual(error.exception.code, code)
        gateway.assert_not_called()

    def test_full_rolling_minute_waits_then_gateway_reservation_succeeds(self):
        self.route.max_calls_per_minute = 3
        self.route.save(update_fields=["max_calls_per_minute"])
        for status in ("success", "pending", "timeout"):
            self.log(status=status)

        def dispatch(actor, route_code, messages):
            self.assertEqual(route_code, self.route.code)
            _reserve(actor, self.model, "business", self.route)
            return self.reply()

        self.assertEqual(self.call(Mock(side_effect=dispatch)), {"passed": True, "issues": []})
        self.assertEqual(self.elapsed, 61)  # Gateway includes the exact 60s boundary.
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.model_calls, 1)
        self.task.refresh_from_db()
        self.assertGreater(self.task.lease_until, self.now)
        self.assertEqual(self.task.checkpoint["calls"][0]["pacing_wait_seconds"], 61)

    def test_no_recent_logs_dispatches_without_sleep(self):
        gateway = Mock(return_value=self.reply())
        self.call(gateway)
        gateway.assert_called_once()
        self.assertEqual(self.sleeps, [])

    def test_other_actors_and_routes_and_old_logs_do_not_consume_slot(self):
        self.log(actor=self.create_user("other-pacing", "product"))
        other_route = ModelRoute.objects.create(code="other-pacing", name="隔离", model=self.model,
                                                module=self.route.module)
        self.log(route=other_route)
        self.log(seconds_ago=61)
        self.call(Mock(return_value=self.reply()))
        self.assertEqual(self.sleeps, [])

    def test_initial_budget_limit_stops_before_wait(self):
        self.log()
        DocumentAttempt.objects.filter(pk=self.attempt.pk).update(model_calls=10)
        self.assert_stopped("model_call_limit")
        self.assertEqual(self.sleeps, [])

    def test_budget_consumed_during_wait_is_rechecked_before_dispatch(self):
        self.log()
        self.after_sleep = lambda: DocumentAttempt.objects.filter(pk=self.attempt.pk).update(model_calls=10)
        self.assert_stopped("model_call_limit")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.model_calls, 10)
        self.assertEqual(self.elapsed, 1)

    def test_cancelled_task_stops_during_wait(self):
        self.log()
        self.after_sleep = lambda: DocumentTask.objects.filter(pk=self.task.pk).update(state="CANCELLED")
        self.assert_stopped("lease_lost")
        self.assertEqual(self.elapsed, 1)

    def test_changed_fence_stops_during_wait(self):
        self.log()
        self.after_sleep = lambda: DocumentTask.objects.filter(pk=self.task.pk).update(fence=self.claim[1] + 1)
        self.assert_stopped("lease_lost")

    def test_expired_lease_stops_without_resurrecting_it(self):
        self.log()
        self.after_sleep = lambda: DocumentTask.objects.filter(pk=self.task.pk).update(lease_until=self.now)
        self.assert_stopped("lease_lost")

    def test_changed_permissions_stop_during_wait(self):
        self.log()
        self.after_sleep = lambda: type(self.owner).objects.filter(pk=self.owner.pk).update(
            grant_version=F("grant_version") + 1)
        self.assert_stopped("permission_changed")

    def test_model_authorization_revoked_during_wait_stops(self):
        self.log()
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True):
            self.after_sleep = lambda: setattr(product_worker.settings, "PRODUCT_MODEL_CALLS_ALLOWED", False)
            self.assert_stopped("model_authorization_required")

    def test_rules_change_during_wait_stops_before_dispatch(self):
        self.log()
        original_hash = product_worker.rules_hash()
        with patch("portal.product_worker.rules_hash", side_effect=lambda: original_hash if not self.sleeps else "changed"):
            self.assert_stopped("product_rules_unavailable")

    def test_route_limit_is_reloaded_after_wait(self):
        self.log()
        self.after_sleep = lambda: ModelRoute.objects.filter(pk=self.route.pk).update(max_calls_per_minute=2)
        self.call(Mock(return_value=self.reply()))
        self.assertEqual(self.elapsed, 1)

    def test_continuous_contention_has_bounded_wait_and_no_charged_dispatch(self):
        record = self.log()
        self.after_sleep = lambda: ModelCallLog.objects.filter(pk=record.pk).update(created_at=self.now)
        self.assert_stopped("rate_limited")
        self.assertEqual(self.elapsed, 120)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.model_calls, 0)

    def test_output_correction_is_paced_and_remains_one_retry(self):
        def dispatch(*args):
            self.log()
            return {"content": "invalid JSON"}

        gateway = Mock(side_effect=dispatch)
        with self.assertRaises(product_worker.ExecutionError) as error:
            self.call(gateway)
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(gateway.call_count, 2)
        self.assertEqual(self.elapsed, 61)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.model_calls, 2)

    def test_gateway_race_rejection_is_recorded_and_charged_without_retry(self):
        def raced_dispatch(actor, route_code, messages):
            self.log()  # Another caller reserves after pacing observed a slot.
            _reserve(actor, self.model, "business", self.route)
            return self.reply()

        gateway = Mock(side_effect=raced_dispatch)
        with self.assertRaises(GatewayError):
            self.call(gateway)
        gateway.assert_called_once()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.model_calls, 1)
        self.task.refresh_from_db()
        evidence = self.task.checkpoint["calls"][0]
        self.assertEqual((evidence["status"], evidence["error_code"]), ("gateway_rejected", "rate_limited"))

    def test_timeout_is_not_retried(self):
        gateway = Mock(side_effect=GatewayError("timeout"))
        with self.assertRaises(GatewayError):
            self.call(gateway)
        gateway.assert_called_once()

    def test_agent_admission_occurs_after_pacing_and_finishes_on_error(self):
        self.log(seconds_ago=59)
        runtime = Mock()
        runtime.admit.return_value = "model-action"
        original_guard = product_worker._guard

        def guard(*args):
            task = original_guard(*args)
            task.agent_root_id = "isolated-root"
            return task

        self.after_sleep = lambda: runtime.admit.assert_not_called()
        gateway = Mock(side_effect=GatewayError("rate_limited"))
        with patch("portal.product_worker._guard", side_effect=guard), patch(
                "portal.product_agent.runtime_guard_for_task", return_value=runtime):
            with self.assertRaises(GatewayError):
                self.call(gateway)
        runtime.admit.assert_called_once()
        runtime.finish.assert_called_once_with("model-action", "error")
        self.assertEqual(self.elapsed, 2)

    def test_agent_binding_revalidated_during_wait(self):
        self.log()
        original_guard = product_worker._guard

        def guard(*args):
            if self.sleeps:
                raise product_worker.ExecutionError("agent_binding_stale")
            return original_guard(*args)

        with patch("portal.product_worker._guard", side_effect=guard):
            self.assert_stopped("agent_binding_stale")
        self.assertEqual(self.elapsed, 1)
