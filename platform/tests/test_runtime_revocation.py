"""Run: python -m unittest discover -s platform/tests -p test_runtime_revocation.py.

Live SSE iterators and temporary SQLite identity/binding records; no Docker,
production database, network, or mocked identity decisions.
"""

import asyncio
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from app.auth.service import create_access_token
from app.config import settings
from app.db.models import Base, Container, User
from app.routes import proxy


class QueueStream(httpx.AsyncByteStream):
    def __init__(self):
        self.queue = asyncio.Queue()
        self.closed = False
        self.cancelled = False

    async def __aiter__(self):
        try:
            while True:
                chunk = await self.queue.get()
                if chunk is None:
                    return
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        self.closed = True


class RuntimeRevocationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + str(Path(self.directory.name) / 'identity.sqlite3'))
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            for name in ('alice', 'bob'):
                db.add(User(id=name, username=name, email=name + '@example.test', role='user',
                            business_role='employee', department_code='product', portal_user_id=1 if name == 'alice' else 2,
                            portal_session_enc='synthetic-session', password_hash='credential'))
                db.add(Container(id=name + '-runtime', user_id=name, docker_id=name + '-docker',
                                 container_token='server-only-' + name, internal_host=name + '.test',
                                 internal_port=18080, status='running'))
            db.commit()
        self.active_sessions = 0
        self.session_opens = 0
        self.identity_unavailable = False
        self.identity_blocked = False
        self.stream = QueueStream()
        self.clients = []
        self.requests = []
        self.handshake_mutation = None
        self.real_client = httpx.AsyncClient
        self.ensure_running = AsyncMock(side_effect=proxy.get_container)
        self.patches = [
            patch.object(settings, 'dev_openclaw_url', ''),
            patch.object(settings, 'dev_bridge_token', ''),
            patch.object(proxy, 'async_session', self.session),
            patch.object(proxy, 'ensure_running', self.ensure_running),
            patch.object(proxy, 'SSE_IDENTITY_INTERVAL_SECONDS', .02),
            patch.object(proxy, 'SSE_IDENTITY_TIMEOUT_SECONDS', .04),
            patch.object(proxy.httpx, 'AsyncClient', self.http_client),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    @asynccontextmanager
    async def session(self):
        if self.identity_unavailable:
            raise OSError('synthetic identity outage')
        if self.identity_blocked:
            await asyncio.Future()

        class Adapter:
            def __init__(self, db):
                self.db = db

            async def execute(self, statement):
                return self.db.execute(statement)

        with Session(self.engine) as db:
            self.active_sessions += 1
            self.session_opens += 1
            try:
                yield Adapter(db)
            finally:
                self.active_sessions -= 1

    def change(self, model, **values):
        with Session(self.engine) as db:
            db.execute(update(model).where(model.id == ('alice' if model is User else 'alice-runtime')).values(**values))
            db.commit()

    def http_client(self, **kwargs):
        client = self.real_client(transport=httpx.MockTransport(self.upstream), **kwargs)
        self.clients.append(client)
        return client

    def upstream(self, request):
        self.requests.append(request)
        self.assertEqual(request.url.host, 'alice.test')
        self.assertEqual(request.headers['authorization'], 'Bearer server-only-alice')
        self.assertNotIn('token', request.url.params)
        if self.handshake_mutation:
            self.handshake_mutation()
        return httpx.Response(200, stream=self.stream, headers={'content-type': 'text/event-stream'})

    async def open_stream(self):
        return await proxy.proxy_events_stream(Request({'type': 'http'}), create_access_token('alice', 'user', 'credential'))

    def assert_closed(self):
        self.assertTrue(self.stream.closed)
        self.assertTrue(self.clients[-1].is_closed)
        self.assertEqual(self.active_sessions, 0)
        self.assertEqual(self.ensure_running.await_count, 1)

    async def revoke(self, mutation):
        response = await self.open_stream()
        await self.stream.queue.put(b'data: authorized\n\n')
        self.assertEqual(await anext(response.body_iterator), b'data: authorized\n\n')
        self.assertEqual(self.active_sessions, 0)
        mutation()
        # An idle upstream must close too, with its pending read cancelled.
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(anext(response.body_iterator), 1)
        self.assertTrue(self.stream.cancelled)
        self.assert_closed()

    async def test_disabled_user_closes_idle_stream(self):
        await self.revoke(lambda: self.change(User, is_active=False))

    async def test_password_reset_closes_stream(self):
        await self.revoke(lambda: self.change(User, password_hash='reset'))

    async def test_token_signing_key_rotation_closes_stream(self):
        with patch.object(settings, 'jwt_secret', 'synthetic-initial-key'):
            await self.revoke(lambda: setattr(settings, 'jwt_secret', 'synthetic-replacement-key'))

    async def test_business_identity_and_session_changes_close_stream(self):
        for values in ({'portal_user_id': 3}, {'portal_session_enc': 'replacement'},
                       {'business_role': 'unassigned'}, {'department_code': 'hr'},
                       {'runtime_mode': 'shared'}):
            with self.subTest(values=values):
                identity = None
                async with self.session() as db:
                    from app.auth.service import get_user_by_id
                    identity = proxy._sse_identity(await get_user_by_id(db, 'alice'))
                self.change(User, **values)
                self.assertFalse(await proxy._sse_authorized(
                    create_access_token('alice', 'user', 'credential'), identity,
                    ('http://alice.test:18080', {'Authorization': 'Bearer server-only-alice'})))
                self.change(User, portal_user_id=1, portal_session_enc='synthetic-session',
                            business_role='employee', department_code='product', runtime_mode='dedicated')

    async def test_live_session_unlink_closes_stream(self):
        await self.revoke(lambda: self.change(User, portal_session_enc=None))

    async def test_runtime_credential_revocation_closes_stream(self):
        await self.revoke(lambda: self.change(Container, container_token=''))

    async def test_runtime_credential_rotation_closes_stream(self):
        await self.revoke(lambda: self.change(Container, container_token='replacement-server-token'))

    async def test_runtime_reassignment_closes_stream(self):
        # A formerly owned runtime is no longer returned by the user's binding lookup.
        await self.revoke(lambda: self.change(Container, user_id='unbound-owner'))

    async def test_runtime_removal_closes_stream(self):
        def remove():
            with Session(self.engine) as db:
                db.execute(delete(Container).where(Container.id == 'alice-runtime'))
                db.commit()
        await self.revoke(remove)

    async def test_runtime_stopped_closes_stream(self):
        await self.revoke(lambda: self.change(Container, status='paused'))

    async def test_runtime_endpoint_rebinding_closes_stream(self):
        await self.revoke(lambda: self.change(Container, internal_host='bob.test'))

    async def test_identity_outage_closes_stream(self):
        await self.revoke(lambda: setattr(self, 'identity_unavailable', True))

    async def test_identity_lookup_timeout_closes_stream(self):
        await self.revoke(lambda: setattr(self, 'identity_blocked', True))

    async def test_revocation_during_handshake_blocks_first_event(self):
        self.handshake_mutation = lambda: self.change(User, is_active=False)
        response = await self.open_stream()
        await self.stream.queue.put(b'data: private\n\n')
        with self.assertRaises(StopAsyncIteration):
            await anext(response.body_iterator)
        self.assert_closed()

    async def test_busy_stream_rechecks_before_forwarding_buffered_event(self):
        response = await self.open_stream()
        await self.stream.queue.put(b'data: authorized\n\n')
        self.assertEqual(await anext(response.body_iterator), b'data: authorized\n\n')
        self.change(User, is_active=False)
        await self.stream.queue.put(b'data: private\n\n')
        await asyncio.sleep(.03)
        with self.assertRaises(StopAsyncIteration):
            await anext(response.body_iterator)
        self.assert_closed()

    async def test_wrong_user_container_is_rejected_before_connecting(self):
        async def wrong_container(db, user_id):
            return await proxy.get_container(db, 'bob')
        self.ensure_running.side_effect = wrong_container
        with self.assertRaises(HTTPException) as error:
            await self.open_stream()
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.requests, [])

    async def test_normal_transfer_rechecks_without_retaining_database_or_leaking_tokens(self):
        response = await self.open_stream()
        for chunk in (b'data: first\n\n', b': heartbeat\n\n', b'data: last\n\n'):
            await self.stream.queue.put(chunk)
            self.assertEqual(await anext(response.body_iterator), chunk)
            self.assertEqual(self.active_sessions, 0)
            await asyncio.sleep(.025)
        self.assertGreaterEqual(self.session_opens, 4)
        self.assertNotIn('server-only-alice', str(dict(response.headers)))
        await self.stream.queue.put(None)
        with self.assertRaises(StopAsyncIteration):
            await anext(response.body_iterator)
        self.assert_closed()

    async def test_client_cancellation_cleans_up_pending_upstream_read(self):
        response = await self.open_stream()
        task = asyncio.create_task(anext(response.body_iterator))
        await asyncio.sleep(.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(self.stream.cancelled)
        self.assert_closed()

    async def test_upstream_disconnect_after_revocation_emits_no_error_event(self):
        response = await self.open_stream()
        await self.stream.queue.put(b'data: authorized\n\n')
        self.assertEqual(await anext(response.body_iterator), b'data: authorized\n\n')
        self.change(User, is_active=False)
        await self.stream.queue.put(httpx.RemoteProtocolError('private-server-only-alice'))
        with self.assertRaises(StopAsyncIteration):
            await anext(response.body_iterator)
        self.assert_closed()


if __name__ == '__main__':
    unittest.main()
