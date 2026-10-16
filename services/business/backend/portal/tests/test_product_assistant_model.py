import asyncio
import json
import socket

import httpx
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore, Event, Lock, Thread, enumerate as threads
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
    def test_cancel_headers_body_and_slow_success_without_worker_leaks(self):
        for phase in ("headers", "body", "slow_success"):
            with self.subTest(phase=phase):
                baseline_threads = set(threads())
                ready, release, cancelled, finished = Event(), Event(), Event(), Event()
                failures, events, clients, pending = [], [], [], []
                original_client = httpx.AsyncClient
                def create_client(**kwargs):
                    client = original_client(**kwargs)
                    clients.append(client)
                    close = client.aclose
                    async def checked_close():
                        await close()
                        pending.extend(task for task in asyncio.all_tasks()
                                       if task is not asyncio.current_task() and not task.done())
                    client.aclose = checked_close
                    return client

                class Handler(BaseHTTPRequestHandler):
                    def do_POST(self):
                        self.rfile.read(int(self.headers["Content-Length"]))
                        if phase == "headers":
                            ready.set()
                            release.wait(5)
                            return
                        if phase == "slow_success":
                            release.wait(1.1)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        self.wfile.flush()
                        ready.set()
                        if phase == "body":
                            release.wait(5)
                        else:
                            self.wfile.write(sse({"delta": "Checking"}) + sse({"done": True, **RESULT}))

                    def log_message(self, *args):
                        pass

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                serving = Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
                serving.start()
                url = "http://127.0.0.1:" + str(server.server_port)
                def read():
                    try:
                        events.extend(assistant._request_agent_stream({"messages": [{"role": "user", "content": "test"}],
                            "tools": TOOLS, "model": {"timeout_seconds": 120}}, cancelled=cancelled))
                    except Exception as error:
                        failures.append(error)
                    finally:
                        finished.set()
                worker = Thread(target=read, daemon=True)
                try:
                    with override_settings(MODEL_GATEWAY_URL=url, MODEL_GATEWAY_ALLOWED_URLS=(url,)), patch.object(
                            assistant.httpx, "AsyncClient", side_effect=create_client):
                        worker.start()
                        self.assertTrue(ready.wait(2))
                        started = monotonic()
                        if phase != "slow_success":
                            cancelled.set()
                        self.assertTrue(finished.wait(1.5))
                        worker.join(.2)
                        self.assertFalse(worker.is_alive())
                        self.assertFalse(pending)
                        self.assertTrue(all(client.is_closed for client in clients))
                        if phase != "slow_success":
                            self.assertLess(monotonic() - started, 1.5)
                            self.assertEqual(len(failures), 1)
                            self.assertIsInstance(failures[0], assistant.ModelStreamCancelled)
                        else:
                            self.assertFalse(failures)
                            self.assertEqual(events[-1], {"done": True, **RESULT})
                finally:
                    cancelled.set()
                    release.set()
                    worker.join(1)
                    server.shutdown()
                    server.server_close()
                    serving.join(1)
                self.assertFalse([thread for thread in threads() if thread not in baseline_threads])

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
    def test_http_stream_fragmentation_endpoint_and_generator_close(self):
        responses, requests, clients = [], [], []
        class Fragmented(httpx.AsyncByteStream):
            async def __aiter__(self):
                first = sse({"delta": "Checking"})
                for index in range(0, len(first), 3):
                    yield first[index:index + 3]
                await asyncio.sleep(2)
                yield sse({"done": True, **RESULT})
        def respond(request):
            requests.append(request)
            response = httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=Fragmented())
            responses.append(response)
            return response
        original_client = httpx.AsyncClient
        def create_client(**kwargs):
            self.assertFalse(kwargs["trust_env"])
            self.assertFalse(kwargs["follow_redirects"])
            client = original_client(**kwargs, transport=httpx.MockTransport(respond))
            clients.append(client)
            return client
        with patch.object(assistant.httpx, "AsyncClient", side_effect=create_client):
            source = assistant._request_agent_stream({"messages": [{"role": "user", "content": "test"}], "tools": TOOLS})
            started = monotonic()
            self.assertEqual(next(source), {"delta": "Checking"})
            self.assertLess(monotonic() - started, .5)
            source.close()
        self.assertTrue(responses[0].is_closed)
        self.assertTrue(clients[0].is_closed)
        self.assertTrue(str(requests[0].url).endswith("/v1/generate-agent-stream"))

    @override_settings(MODEL_GATEWAY_URL="https://dns.example.test", MODEL_GATEWAY_TOKEN="x" * 48,
                       MODEL_GATEWAY_ALLOWED_URLS=("https://dns.example.test",))
    def test_blocked_dns_cancel_releases_worker_and_caps_late_resolvers(self):
        release, entered, lock = Event(), [Event(), Event()], Lock()
        slots, lookups, workers = BoundedSemaphore(2), [], []
        baseline = set(threads())
        payload = {"messages": [{"role": "user", "content": "test"}], "tools": TOOLS}
        def blocked_dns(*args):
            with lock:
                index = len(lookups)
                lookups.append(args)
            entered[index].set()
            release.wait(5)
            raise socket.gaierror("isolated DNS fixture")
        with patch.object(assistant, "_DNS_SLOTS", slots), patch.object(
                assistant.socket, "getaddrinfo", side_effect=blocked_dns):
            try:
                for index in range(2):
                    cancelled, finished, failures = Event(), Event(), []
                    def read():
                        try:
                            list(assistant._request_agent_stream(payload, cancelled=cancelled))
                        except Exception as error:
                            failures.append(error)
                        finally:
                            finished.set()
                    worker = Thread(target=read, daemon=True)
                    workers.append(worker)
                    worker.start()
                    self.assertTrue(entered[index].wait(2))
                    started = monotonic()
                    cancelled.set()
                    self.assertTrue(finished.wait(1.5))
                    worker.join(.2)
                    self.assertFalse(worker.is_alive())
                    self.assertLess(monotonic() - started, 1.5)
                    self.assertEqual(len(failures), 1)
                    self.assertIsInstance(failures[0], assistant.ModelStreamCancelled)
                self.assertFalse(slots.acquire(blocking=False), "cancel must not release a still-running DNS slot")
                resolvers = [thread for thread in threads() if thread not in baseline]
                self.assertEqual(len(resolvers), 2)
                self.assertTrue(all(thread.daemon and thread.name == "assistant-gateway-dns" for thread in resolvers))
                with self.assertRaises(gateway.GatewayError) as caught:
                    list(assistant._request_agent_stream(payload))
                self.assertEqual(caught.exception.code, "busy")
                self.assertEqual(len(lookups), 2)
            finally:
                release.set()
                for thread in [*workers, *(thread for thread in threads() if thread not in baseline)]:
                    thread.join(1)
            self.assertTrue(slots.acquire(blocking=False))
            self.assertTrue(slots.acquire(blocking=False))
            self.assertFalse(slots.acquire(blocking=False))
            slots.release()
            slots.release()
        self.assertFalse([thread for thread in threads() if thread not in baseline])

    @override_settings(MODEL_GATEWAY_TOKEN="x" * 48)
    def test_dns_preserves_resolution_arguments_and_gateway_http_guard(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "gateway", ("127.0.0.1", 18410))]
        with patch.object(assistant.socket, "getaddrinfo", return_value=addresses) as lookup:
            with asyncio.Runner() as runner:
                result = runner.run(assistant._resolve_gateway("model-gateway", 18410,
                    family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, proto=6, flags=socket.AI_CANONNAME))
            self.assertIs(result, addresses)
            lookup.assert_called_once_with("model-gateway", 18410, socket.AF_UNSPEC,
                                           socket.SOCK_STREAM, 6, socket.AI_CANONNAME)
        payload = {"messages": [{"role": "user", "content": "test"}], "tools": TOOLS}
        with override_settings(MODEL_GATEWAY_URL="http://unapproved.example:18410",
                               MODEL_GATEWAY_ALLOWED_URLS=("http://unapproved.example:18410",)), patch.object(
                assistant.httpx, "AsyncClient") as client, self.assertRaises(gateway.GatewayError) as caught:
            list(assistant._request_agent_stream(payload))
        self.assertEqual(caught.exception.code, "unconfigured")
        client.assert_not_called()
        with override_settings(MODEL_GATEWAY_URL="https://gateway.example",
                               MODEL_GATEWAY_ALLOWED_URLS=("https://gateway.example",)):
            request, _ = gateway._gateway_request(payload, "/v1/generate-agent-stream")
        self.assertEqual(request.full_url, "https://gateway.example/v1/generate-agent-stream")

    @override_settings(MODEL_GATEWAY_URL="http://127.0.0.1:18410", MODEL_GATEWAY_TOKEN="x" * 48)
    def test_transport_error_boundaries_size_and_total_deadline(self):
        original_client = httpx.AsyncClient
        payload = {"messages": [{"role": "user", "content": "test"}], "tools": TOOLS}
        for status, headers, wire, expected in (
            (503, {}, b'{"code":"rate_limited"}' + b' ' * 8192 + b'invalid', "rate_limited"),
            (302, {"Location": "https://forbidden.example/"}, b'', "upstream_error"),
            (200, {"Content-Type": "application/json"}, b'{}', "invalid_response"),
            (200, {"Content-Type": "text/event-stream", "Content-Encoding": "gzip"}, b'', "invalid_response"),
            (200, {"Content-Type": "text/event-stream"}, b'data: ' + b'x' * (assistant.RESPONSE_LIMIT + 65537), "response_too_large"),
        ):
            with self.subTest(expected=expected):
                def respond(request):
                    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(wire))
                def create_client(**kwargs):
                    return original_client(**kwargs, transport=httpx.MockTransport(respond))
                with patch.object(assistant.httpx, "AsyncClient", side_effect=create_client), self.assertRaises(
                        gateway.GatewayError) as caught:
                    list(assistant._request_agent_stream(payload))
                self.assertEqual(caught.exception.code, expected)
        async def slow_response(request):
            await asyncio.sleep(2)
        def slow_client(**kwargs):
            return original_client(**kwargs, transport=httpx.MockTransport(slow_response))
        request, _ = gateway._gateway_request(payload, "/v1/generate-agent-stream")
        with patch.object(gateway, "_gateway_request", return_value=(request, .05)), patch.object(
                assistant.httpx, "AsyncClient", side_effect=slow_client), self.assertRaises(gateway.GatewayError) as caught:
            list(assistant._request_agent_stream(payload))
        self.assertEqual(caught.exception.code, "timeout")


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
