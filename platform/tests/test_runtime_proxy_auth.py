"""Run: python -m unittest discover -s platform/tests -p test_runtime_proxy_auth.py.

Fake dedicated containers and HTTP/WS upstreams only; no Docker or real DB.
"""

import asyncio
import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from app.auth.dependencies import get_current_user
from app.auth.service import create_access_token, decode_token
from app.config import settings
from app.db.engine import get_db
from app.routes import proxy


class ProxyAuthTests(unittest.TestCase):
    def setUp(self):
        self.users = {name: SimpleNamespace(id=name, role="admin", business_role="employee", is_active=True, runtime_mode="dedicated") for name in ("alice", "bob")}
        self.containers = {name: SimpleNamespace(user_id=name, internal_host=name + ".test", internal_port=18080, container_token="test-only-container-" + name) for name in self.users}
        self.requests = []
        self.http_clients = []
        self.db = SimpleNamespace(close=AsyncMock())
        self.real_client = httpx.AsyncClient
        self.patches = [
            patch.object(settings, "dev_openclaw_url", ""),
            patch.object(settings, "dev_gateway_url", ""),
            patch.object(settings, "dev_bridge_token", ""),
            patch.object(proxy, "ensure_running", AsyncMock(side_effect=lambda db, user_id: self.containers[user_id])),
            patch.object(proxy, "async_session", self.db_context),
            patch("app.auth.service.get_user_by_id", AsyncMock(side_effect=lambda db, user_id: self.users.get(user_id))),
            patch.object(proxy.httpx, "AsyncClient", self.http_client),
        ]
        for item in self.patches:
            item.start()

        async def user(request: Request):
            payload = decode_token(request.headers.get("authorization", "")[7:])
            if not payload or payload.get("type") != "access":
                raise HTTPException(401, "Invalid token")
            return self.users[payload["sub"]]

        async def db():
            yield self.db

        app = FastAPI()
        app.include_router(proxy.router)
        app.dependency_overrides[get_current_user] = user
        app.dependency_overrides[get_db] = db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()

    @asynccontextmanager
    async def db_context(self):
        yield self.db

    def http_client(self, **kwargs):
        client = self.real_client(transport=httpx.MockTransport(self.upstream), **kwargs)
        self.http_clients.append(client)
        return client

    def upstream(self, request):
        self.requests.append(request)
        name = request.url.host.split(".")[0]
        self.assertEqual(request.headers["authorization"], "Bearer " + self.containers[name].container_token)
        self.assertNotIn("token", request.url.params)
        if request.url.path == "/api/events/stream":
            return httpx.Response(200, content=b'data: {"owned":true}\n\n', headers={"Content-Type": "text/event-stream"})
        if request.url.path.startswith("/api/filemanager/"):
            return httpx.Response(200, content=b"owned-file", headers={"Content-Type": "application/octet-stream"})
        return httpx.Response(200, json={"account": name})

    @staticmethod
    def token(name):
        return create_access_token(name, "admin")

    def test_http_and_abort_route_use_own_container_tokens(self):
        for name in self.users:
            headers = {"Authorization": "Bearer " + self.token(name)}
            response = self.client.post("/api/openclaw/chat?tag=a&tag=b&token=" + self.token(name), headers=headers, json={"message": "test"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"account": name})
            self.assertEqual(self.requests[-1].url.params.get_list("tag"), ["a", "b"])
            self.assertNotIn(self.containers[name].container_token, response.text)
            response = self.client.post("/api/openclaw/runs/test-run/abort", headers=headers, json={"sessionKey": "owned"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(self.requests[-1].content), {"sessionKey": "owned"})

    def test_sse_and_files_replace_browser_credentials(self):
        for name in self.users:
            token = self.token(name)
            response = self.client.get("/api/openclaw/events/stream?token=" + token)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"owned", response.content)
            for endpoint in ("download", "serve"):
                response = self.client.get(f"/api/openclaw/filemanager/{endpoint}?token={token}&path=owned.txt&path=second.txt")
                self.assertEqual(response.content, b"owned-file")
                self.assertEqual(self.requests[-1].url.params.get_list("path"), ["owned.txt", "second.txt"])
            response = self.client.get("/api/openclaw/filemanager/download?path=owned.txt", headers={"Authorization": "Bearer " + token})
            self.assertEqual(response.content, b"owned-file")
        before = len(self.requests)
        self.assertEqual(self.client.get("/api/openclaw/filemanager/serve?token=invalid").status_code, 401)
        self.assertEqual(len(self.requests), before)

    def test_both_websocket_relays_pass_own_token_only(self):
        class Upstream:
            async def send(self, data):
                pass

            async def close(self):
                pass

            async def messages(self):
                yield "owned-message"

            def __aiter__(self):
                return self.messages()

        for name in self.users:
            for endpoint, bridge_path in (("ws", "/ws"), ("terminal/ws", "/api/terminal/ws")):
                with patch("websockets.legacy.client.connect", AsyncMock(return_value=Upstream())) as connect:
                    with self.client.websocket_connect(f"/api/openclaw/{endpoint}?token={self.token(name)}") as ws:
                        self.assertEqual(ws.receive_text(), "owned-message")
                    connect.assert_awaited_once_with("ws://" + name + ".test:18080" + bridge_path,
                        origin="http://127.0.0.1:8080", extra_headers={"Authorization": "Bearer " + self.containers[name].container_token})

    def test_sse_preserves_upstream_errors_and_closes_connections(self):
        class ErrorBody(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b'{"detail":"private-upstream-error"}'

            async def aclose(self):
                self.closed = True

        url = "/api/openclaw/events/stream?token=" + self.token("alice")
        for status_code in (401, 503):
            body = ErrorBody()
            upstream = httpx.Response(status_code, stream=body, headers={"Content-Type": "application/json"})
            self.assertFalse(upstream.is_closed)
            with patch.object(self, "upstream", return_value=upstream):
                response = self.client.get(url)
            self.assertEqual(response.status_code, status_code)
            self.assertNotIn("text/event-stream", response.headers["content-type"])
            self.assertNotIn("private-upstream-error", response.text)
            self.assertTrue(upstream.is_closed)
            self.assertTrue(body.closed)
            self.assertTrue(self.http_clients[-1].is_closed)
        with patch.object(self, "upstream", side_effect=httpx.ConnectError("private-connection-error")):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(self.http_clients[-1].is_closed)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"owned", response.content)
        self.assertTrue(self.http_clients[-1].is_closed)

    def test_wrong_owner_and_unconfigured_dev_token_fail_closed(self):
        self.containers["alice"].user_id = "bob"
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(proxy._container_target(self.db, self.users["alice"]))
        self.assertEqual(caught.exception.status_code, 403)
        for token in ("", "dev-token"):
            with patch.object(settings, "dev_openclaw_url", "http://dev.test:18080"), patch.object(settings, "dev_bridge_token", token):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(proxy._container_target(self.db, self.users["alice"]))
                self.assertEqual(caught.exception.status_code, 503)
        with patch.object(settings, "dev_openclaw_url", "http://dev.test:18080"), patch.object(settings, "dev_bridge_token", "explicit-test-dev-token"):
            self.assertEqual(asyncio.run(proxy._container_target(self.db, self.users["alice"])),
                ("http://dev.test:18080", {"Authorization": "Bearer explicit-test-dev-token"}))


if __name__ == "__main__":
    unittest.main()
