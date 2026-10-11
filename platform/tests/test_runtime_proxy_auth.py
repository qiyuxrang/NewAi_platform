"""Run: python -m unittest discover -s platform/tests -p test_runtime_proxy_auth.py.

Fake dedicated containers and HTTP/WS upstreams only; no Docker or real DB.
"""

import asyncio
import json
import sys
import unittest
import tempfile
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
    def test_password_reset_blocks_sse_file_and_both_websocket_entrypoints(self):
        from starlette.websockets import WebSocketDisconnect
        token = self.token('alice')
        self.users['alice'].password_hash = 'changed-credential'
        for endpoint in ('events/stream', 'filemanager/serve', 'filemanager/download'):
            response = self.client.get('/api/openclaw/'+endpoint+'?token='+token)
            self.assertIn(response.status_code, (401, 403))
        for endpoint in ('ws', 'terminal/ws'):
            with self.assertRaises(WebSocketDisconnect) as error:
                with self.client.websocket_connect('/api/openclaw/'+endpoint+'?token='+token):
                    pass
            self.assertEqual(error.exception.code, 4001)
        self.assertEqual(self.requests, [])

    def setUp(self):
        self.users = {name: SimpleNamespace(id=name, role="admin", business_role="employee", is_active=True, runtime_mode="dedicated", password_hash="unused") for name in ("alice", "bob")}
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
        return create_access_token(name, "admin", "unused")

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


class EstablishedWebSocketRevocationTests(unittest.IsolatedAsyncioTestCase):
    """Real file SQLite plus live ASGI relay queues, without mocked identity reads."""

    async def asyncSetUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db.models import Base, User
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///'+str(Path(self.directory.name)/'identity.sqlite3'))
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add(User(id='live-admin',username='live-admin',email='live@example.com',
                        role='admin',password_hash='initial-credential'))
            db.commit()
        self.active_sessions=0
        self.session_opens=0
        self.identity_unavailable=False
        self.patches=[patch.object(proxy,'async_session',self.real_session),
                      patch.object(proxy,'WEBSOCKET_IDENTITY_INTERVAL_SECONDS',.02),
                      patch.object(proxy,'WEBSOCKET_IDENTITY_TIMEOUT_SECONDS',.2),
                      patch.object(proxy,'_container_target',AsyncMock(return_value=(
                          'http://isolated-bridge:18080',{'Authorization':'Bearer synthetic-bridge'})))]
        for item in self.patches:item.start()

    async def asyncTearDown(self):
        for item in reversed(self.patches):item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    @asynccontextmanager
    async def real_session(self):
        from sqlalchemy.orm import Session
        if self.identity_unavailable:raise OSError('synthetic identity store outage')
        class Adapter:
            def __init__(self,session):self.session=session
            async def execute(self,statement):return self.session.execute(statement)
        with Session(self.engine) as session:
            self.active_sessions+=1
            self.session_opens+=1
            try:yield Adapter(session)
            finally:self.active_sessions-=1

    def change_user(self,**values):
        from sqlalchemy import update
        from sqlalchemy.orm import Session
        from app.db.models import User
        with Session(self.engine) as db:
            db.execute(update(User).where(User.id=='live-admin').values(**values))
            db.commit()

    async def scenario(self,endpoint,mutation,expected_code,send_after=False):
        from starlette.websockets import WebSocket
        self.identity_unavailable=False
        self.change_user(password_hash='initial-credential',role='admin',is_active=True)
        browser_in,browser_out=asyncio.Queue(),asyncio.Queue()
        upstream_in=asyncio.Queue()
        forwarded=[]
        closed=asyncio.Event()
        class EchoUpstream:
            async def send(self,message):
                forwarded.append(message)
                await upstream_in.put(message)
            async def close(self):closed.set()
            async def messages(self):
                while True:yield await upstream_in.get()
            def __aiter__(self):return self.messages()
        socket=WebSocket({'type':'websocket','path':'/api/openclaw/'+endpoint},
                         browser_in.get,browser_out.put)
        token=create_access_token('live-admin','admin','initial-credential')
        route=proxy.proxy_websocket if endpoint=='ws' else proxy.proxy_terminal_websocket
        await browser_in.put({'type':'websocket.connect'})
        with patch('websockets.legacy.client.connect',AsyncMock(return_value=EchoUpstream())):
            task=asyncio.create_task(route(socket,token))
            try:
                accepted=await asyncio.wait_for(browser_out.get(),1)
                self.assertEqual(accepted['type'],'websocket.accept')
                await browser_in.put({'type':'websocket.receive','text':'authorized-command'})
                echoed=await asyncio.wait_for(browser_out.get(),1)
                self.assertEqual(echoed,{'type':'websocket.send','text':'authorized-command'})
                # A live idle connection releases every identity checkout.
                await asyncio.sleep(.03)
                self.assertEqual(self.active_sessions,0)
                self.assertGreaterEqual(self.session_opens,3)
                mutation()
                if send_after:
                    await browser_in.put({'type':'websocket.receive','text':'revoked-command'})
                message=await asyncio.wait_for(browser_out.get(),1)
                self.assertEqual(message['type'],'websocket.close')
                self.assertEqual(message['code'],expected_code)
                await asyncio.wait_for(task,1)
                self.assertTrue(closed.is_set())
                self.assertEqual(forwarded,['authorized-command'])
                self.assertEqual(self.active_sessions,0)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)

    async def test_established_both_relays_close_after_password_reset(self):
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:self.change_user(password_hash='reset-credential'),4001)

    async def test_established_both_relays_close_after_disable(self):
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:self.change_user(is_active=False),4001)

    async def test_established_both_relays_close_after_admin_demotion(self):
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:self.change_user(role='user'),4003)

    async def test_next_terminal_command_is_blocked_immediately_after_reset(self):
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:self.change_user(password_hash='reset-credential'),4001,send_after=True)

    async def test_identity_store_outage_closes_established_both_relays(self):
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:setattr(self,'identity_unavailable',True),1013)

    async def test_new_credential_connects_and_relays_after_previous_connection_revocation(self):
        from starlette.websockets import WebSocket
        for endpoint in ('ws','terminal/ws'):
            await self.scenario(endpoint,lambda:self.change_user(password_hash='reset-credential'),4001)
            incoming,outgoing=asyncio.Queue(),asyncio.Queue()
            upstream_in=asyncio.Queue()
            class FreshUpstream:
                async def send(self,message):await upstream_in.put(message)
                async def close(self):pass
                async def messages(self):
                    while True:yield await upstream_in.get()
                def __aiter__(self):return self.messages()
            socket=WebSocket({'type':'websocket','path':'/api/openclaw/'+endpoint},incoming.get,outgoing.put)
            route=proxy.proxy_websocket if endpoint=='ws' else proxy.proxy_terminal_websocket
            await incoming.put({'type':'websocket.connect'})
            with patch('websockets.legacy.client.connect',AsyncMock(return_value=FreshUpstream())):
                task=asyncio.create_task(route(socket,create_access_token('live-admin','admin','reset-credential')))
                try:
                    self.assertEqual((await asyncio.wait_for(outgoing.get(),1))['type'],'websocket.accept')
                    await incoming.put({'type':'websocket.receive','text':'fresh-command'})
                    self.assertEqual((await asyncio.wait_for(outgoing.get(),1))['text'],'fresh-command')
                    await incoming.put({'type':'websocket.disconnect','code':1000})
                    await asyncio.wait_for(task,1)
                    self.assertEqual(self.active_sessions,0)
                finally:
                    if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
