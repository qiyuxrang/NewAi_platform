import json
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from portal import model_gateway as gateway, product_assistant_model as assistant
from portal.models import AuditEvent, GatewayModel, ModelCallLog, ModelRoute, Module, Provider
from .base import PortalTestCase


TOOLS = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
RESULT = {"content": "Checking", "tool_calls": [{"id": "call_1", "type": "function", "function": {
    "name": "lookup", "arguments": '{"q":"test"}'}}], "prompt_tokens": 12, "completion_tokens": 5}


def sse(event):
    return ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode()


class AssistantWireTests(SimpleTestCase):
    @override_settings(MODEL_GATEWAY_TOKEN="x" * 48)
    def test_cancellation_interrupts_real_socket_without_waiting_for_a_token(self):
        ready, release, cancelled, finished = Event(), Event(), Event(), Event()
        failures = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.flush()
                ready.set()
                release.wait(3)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        serving = Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
        serving.start()
        url = "http://127.0.0.1:" + str(server.server_port)

        def read():
            try:
                list(assistant._request_agent_stream({"messages": [{"role": "user", "content": "test"}],
                    "tools": TOOLS, "model": {"timeout_seconds": 3}}, cancelled=cancelled))
            except Exception as error:
                failures.append(error)
            finally:
                finished.set()

        try:
            with override_settings(MODEL_GATEWAY_URL=url, MODEL_GATEWAY_ALLOWED_URLS=(url,)):
                worker = Thread(target=read, daemon=True)
                worker.start()
                self.assertTrue(ready.wait(1))
                cancelled.set()
                self.assertTrue(finished.wait(1), "Cancellation must interrupt a no-token socket read")
                self.assertEqual(len(failures), 1)
                self.assertIsInstance(failures[0], assistant.ModelStreamCancelled)
        finally:
            cancelled.set()
            release.set()
            server.shutdown()
            server.server_close()
            serving.join(1)

    def test_native_wire_terminal_consistency_and_strict_boundaries(self):
        done = {"done": True, **RESULT}
        wire = sse({"delta": "Checking"}) + sse(done)
        self.assertEqual(list(assistant._agent_events(BytesIO(wire), monotonic() + 3, {"lookup"})),
                         [{"delta": "Checking"}, done])
        for bad in (sse(done), wire + sse(done), wire[:-1], sse({"delta": "partial"}),
                    sse({"delta": "Checking", "reasoning_content": "secret"}),
                    sse({"done": True, **RESULT, "prompt_tokens": True}),
                    b'data: {"delta":"ok","delta":"overwrite"}\n\n'):
            with self.subTest(wire=bad[:40]), self.assertRaises(gateway.GatewayError) as caught:
                list(assistant._agent_events(BytesIO(bad), monotonic() + 3, {"lookup"}))
            self.assertEqual(caught.exception.code, "invalid_response")

    @override_settings(MODEL_GATEWAY_URL="http://127.0.0.1:18410", MODEL_GATEWAY_TOKEN="x" * 48)
    @patch("portal.product_assistant_model.build_opener")
    def test_http_stream_uses_native_endpoint_and_closes_on_cancel(self, opener):
        response = BytesIO(sse({"delta": "Checking"}) + sse({"done": True, **RESULT}))
        response.headers = {"Content-Type": "text/event-stream"}
        opener.return_value.open.return_value = response
        source = assistant._request_agent_stream({"messages": [{"role": "user", "content": "test"}], "tools": TOOLS})
        self.assertEqual(next(source), {"delta": "Checking"})
        source.close()
        self.assertTrue(response.closed)
        self.assertTrue(opener.return_value.open.call_args.args[0].full_url.endswith("/v1/generate-agent-stream"))


@override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
class AssistantAuthorizationTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("assistant-model", "product")
        provider = Provider.objects.create(code="assistant", name="测试", protocol="openai_chat", base_url="https://provider.example/v1",
                                           api_key_env="PORTAL_MODEL_KEY_TEST", enabled=True)
        self.model = GatewayModel.objects.create(name="测试", provider=provider, model_name="test", enabled=True)
        self.route = ModelRoute.objects.create(code="product_knowledge", name="知识", module=Module.objects.get(code="product"), model=self.model, enabled=True)
        self.messages = [{"role": "user", "content": "private prompt"}]
        self.guard = Mock()

    def stream(self, purpose="product_knowledge"):
        return assistant.stream_agent_for_use(self.user, purpose, self.messages, TOOLS, recheck=self.guard)

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_shared_assistant_route_does_not_grant_product_generation(self, request):
        from portal.business_models import BusinessLedgerGrant
        extra = ModelRoute.objects.create(code="product_solution", name="方案", module=self.route.module,
                                          model=self.model, enabled=True)
        for role in ("hr", "engineering", "finance", "general_manager"):
            with self.subTest(role=role):
                self.user = self.create_user("shared-model-" + role, *(() if role == "finance" else (role,)))
                if role == "finance":
                    self.user.department_code = "finance"
                    self.user.save(update_fields=["department_code"])
                    BusinessLedgerGrant.objects.create(user=self.user, department="finance", can_edit=True)
                self.user.refresh_from_db()
                request.return_value = (event for event in [{"delta": "Checking"}, {"done": True, **RESULT}])
                self.assertEqual(list(self.stream())[-1], {"done": True, **RESULT})
                if role != "general_manager":
                    for code in (self.route.code, extra.code):
                        with self.assertRaises(gateway.GatewayError):
                            gateway._route_for(self.user, code)
                    with self.assertRaises(gateway.GatewayError):
                        gateway._route_for(self.user, extra.code, assistant=True)
        self.route.module.enabled = False
        self.route.module.save(update_fields=["enabled"])
        self.user = self.create_user("disabled-product-route", "hr")
        with self.assertRaises(gateway.GatewayError):
            list(self.stream())

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_success_native_tools_and_usage_are_audited_without_content(self, request):
        request.return_value = iter([{"delta": "Checking"}, {"done": True, **RESULT}])
        request.return_value = (event for event in request.return_value)
        self.assertEqual(list(self.stream()), [{"delta": "Checking"}, {"done": True, **RESULT}])
        record = ModelCallLog.objects.get()
        self.assertEqual((record.status, record.prompt_tokens, record.completion_tokens), ("success", 12, 5))
        self.assertGreaterEqual(self.guard.call_count, 5)
        self.assertNotIn("Checking", str(list(ModelCallLog.objects.values())))
        self.assertEqual(AuditEvent.objects.filter(action="model_call").count(), 1)

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_wrong_route_and_module_stop_before_transport(self, request):
        with self.assertRaises(gateway.GatewayError):
            list(self.stream("solution"))
        self.route.module = Module.objects.get(code="hr")
        self.route.save()
        with self.assertRaises(gateway.GatewayError):
            list(self.stream())
        request.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_revocation_and_configuration_change_block_next_delta(self, request):
        for change, code in ((lambda: self.user.roles.clear(), "forbidden"),
                             (lambda: GatewayModel.objects.filter(pk=self.model.pk).update(model_name="changed"), "model_configuration_changed")):
            def source(payload, **kwargs):
                yield {"delta": "first"}
                change()
                yield {"delta": "must-not-leak"}
            request.side_effect = source
            if code == "model_configuration_changed":
                from portal.models import Role
                self.user.roles.set(Role.objects.filter(code="product"))
            stream = self.stream()
            self.assertEqual(next(stream), {"delta": "first"})
            with self.assertRaises(gateway.GatewayError) as caught:
                next(stream)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(ModelCallLog.objects.latest("pk").status, code)

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_cancel_closes_transport_and_callback_error_propagates(self, request):
        closed = []
        def source(payload, **kwargs):
            try:
                yield {"delta": "first"}
                yield {"done": True, **RESULT}
            finally:
                closed.append(True)
        request.side_effect = source
        stream = self.stream()
        next(stream)
        stream.close()
        self.assertTrue(closed)
        self.assertEqual(ModelCallLog.objects.latest("pk").status, "cancelled")
        stream = self.stream()
        next(stream)
        self.guard.side_effect = ValueError("revoked")
        with self.assertRaisesRegex(ValueError, "revoked"):
            next(stream)
        self.assertEqual(ModelCallLog.objects.latest("pk").status, "forbidden")

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_cancel_event_is_audited_as_cancelled(self, request):
        cancelled = Event()
        request.return_value = (event for event in [{"delta": "Checking"}, {"done": True, **RESULT}])
        stream = assistant.stream_agent_for_use(self.user, self.route.code, self.messages, TOOLS,
                                                recheck=self.guard, cancelled=cancelled)
        next(stream)
        cancelled.set()
        with self.assertRaises(assistant.ModelStreamCancelled):
            next(stream)
        self.assertEqual(ModelCallLog.objects.get().status, "cancelled")
