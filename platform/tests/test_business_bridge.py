"""Run: python -m unittest discover -s platform/tests -p test_business_bridge.py.

Mock HTTP portal plus in-memory SQLite. No real database/services are used.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.service import create_access_token
from app.business_client import CSRF_COOKIE, SESSION_COOKIE, open_session, safe_business_path
from app.config import settings
from app.db.engine import get_db
from app.db.models import Base, User
from app.routes import auth, enterprise


class AsyncSQLite:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, user):
        self.session.refresh(user)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=name, username=name, email=name + "@invalid.test", password_hash="unused") for name in ("alice", "bob")])
            db.commit()
        self.requests = []
        self.expired = False
        self.unavailable = False
        self.login_page = False
        self.revoke_during_profile = False
        self.profile = {"id": 42, "username": "portal-alice", "roles": [{"code": "product"}], "department_code": "product", "must_change_password": False}
        self.modules = [{"code": "product", "enabled": True}]
        self.business_response = lambda req: httpx.Response(200, content=b"business-result", headers={"Content-Type": "application/octet-stream", "Content-Disposition": 'attachment; filename="result.bin"', "Set-Cookie": "secret=never-expose", "Authorization": "upstream-secret", "X-CSRFToken": "upstream-secret"})
        self.patches = [patch.object(settings, "jwt_secret", "bridge-test-only-secret-of-32-characters"),
                        patch.object(settings, "portal_base_url", "http://portal.test", create=True),
                        patch.object(settings, "portal_timeout_seconds", 10, create=True),
                        patch.object(enterprise, "portal_client", self.mock_client)]
        for item in self.patches:
            item.start()

        async def test_db():
            with Session(self.engine, expire_on_commit=False) as db:
                yield AsyncSQLite(db)

        app = FastAPI()
        app.include_router(enterprise.router)
        app.include_router(auth.router)
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()

    def mock_client(self, cookies=None):
        return httpx.AsyncClient(base_url="http://portal.test", cookies=cookies, transport=httpx.MockTransport(self.portal), follow_redirects=False)

    def portal(self, req):
        self.requests.append(req)
        if self.unavailable:
            raise httpx.ConnectError("upstream-private-error", request=req)
        path = req.url.path
        if path == "/api/csrf/":
            signed_in = "s-42" in req.headers.get("cookie", "")
            token = "rotated-csrf" if signed_in else "initial-csrf"
            return httpx.Response(200, json={"csrfToken": token}, headers={"Set-Cookie": f"{CSRF_COOKIE}={token}; Path=/; HttpOnly"})
        if path == "/api/login/":
            body = json.loads(req.content)
            if body["password"] != "correct":
                return httpx.Response(401, json={"detail": "upstream-detail-is-not-leaked"})
            self.assertEqual(req.headers["x-csrftoken"], "initial-csrf")
            self.assertIn(CSRF_COOKIE, req.headers["cookie"])
            return httpx.Response(200, json=self.profile, headers={"Set-Cookie": f"{SESSION_COOKIE}=s-42; Path=/; HttpOnly"})
        if self.expired or "s-42" not in req.headers.get("cookie", ""):
            return httpx.Response(401, json={"detail": "expired"})
        if path == "/api/me/":
            if self.login_page:
                return httpx.Response(200, text="login", headers={"Content-Type": "text/html"})
            return httpx.Response(200, json=self.profile)
        if path == "/api/modules/":
            if self.revoke_during_profile:
                with Session(self.engine) as db:
                    user = db.get(User, "alice")
                    user.portal_session_enc = None
                    user.business_role = "unassigned"
                    user.department_code = None
                    db.commit()
            return httpx.Response(200, json=self.modules)
        self.assertEqual(req.headers["x-csrftoken"], "rotated-csrf")
        self.assertNotIn("authorization", req.headers)
        return self.business_response(req)

    @staticmethod
    def headers(name="alice"):
        # A forged admin role in JWT must never grant original portal authority.
        return {"Authorization": "Bearer " + create_access_token(name, "admin", "unused")}

    def link(self, name="alice", password="correct"):
        return self.client.post("/api/enterprise/link", headers=self.headers(name), json={"username": "portal-alice", "password": password})

    def test_success_csrf_identity_encryption_and_no_secret_headers(self):
        linked = self.link()
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json()["capabilities"], ["product"])
        with Session(self.engine) as db:
            user = db.get(User, "alice")
            self.assertNotIn("s-42", user.portal_session_enc)
            self.assertNotIn("correct", user.portal_session_enc)
            self.assertEqual(open_session(user)["csrf"], "rotated-csrf")
        response = self.client.get("/api/enterprise/business/product/tasks/?q=a%2Fb&q=c", headers={**self.headers(), "Cookie": "evil=stolen", "X-CSRFToken": "evil", "X-Forwarded-Host": "evil.test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"business-result")
        self.assertEqual(response.headers["cache-control"], "no-store")
        for header in ("set-cookie", "authorization", "x-csrftoken"):
            self.assertNotIn(header, response.headers)
        sent = self.requests[-1]
        self.assertEqual(sent.url.query, b"q=a%2Fb&q=c")
        self.assertNotIn("evil", sent.headers.get("cookie", ""))
        self.assertNotIn("x-forwarded-host", sent.headers)
        self.assertNotIn("transfer-encoding", sent.headers)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers()).json()["capabilities"], linked.json()["capabilities"])

    def test_duplicate_and_cross_account_session_are_blocked(self):
        self.assertEqual(self.link().status_code, 200)
        self.assertEqual(self.link("bob").status_code, 409)
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers("bob")).status_code, 401)

    def test_link_preserves_admin_mapping_and_concurrent_revocation(self):
        with Session(self.engine) as db:
            alice = db.get(User, "alice")
            alice.portal_user_id = 84
            db.commit()
        self.assertEqual(self.link().status_code, 409)
        with Session(self.engine) as db:
            alice = db.get(User, "alice")
            self.assertEqual(alice.portal_user_id, 84)
            self.assertIsNone(alice.portal_session_enc)
            alice.portal_user_id = None
            db.commit()
        self.assertEqual(self.link().status_code, 200)
        self.revoke_during_profile = True
        # The fixture revokes identity while the remote profile is being read.
        self.assertEqual(self.link().status_code, 409)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(User, "alice").portal_session_enc)
        with Session(self.engine) as db:
            alice, bob = db.get(User, "alice"), db.get(User, "bob")
            bob.portal_session_enc = alice.portal_session_enc
            db.commit()
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers("bob")).status_code, 401)

    def test_expired_and_mismatched_upstream_sessions_fail_closed(self):
        self.link()
        self.expired = True
        result = self.client.get("/api/enterprise/status", headers=self.headers()).json()
        self.assertFalse(result["linked"])
        self.assertFalse(result["available"])
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 401)
        self.expired = False
        self.link()
        self.profile["id"] = 99
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 401)

    def test_admin_revocation_during_upstream_check_cannot_restore_identity(self):
        self.link()
        self.revoke_during_profile = True
        result = self.client.get("/api/enterprise/status", headers=self.headers()).json()
        self.assertFalse(result["linked"])
        self.assertFalse(result["available"])
        self.assertEqual(result["capabilities"], [])
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 401)

    def test_outage_and_200_login_page_cannot_report_available(self):
        self.link()
        self.unavailable = True
        response = self.client.get("/api/enterprise/status", headers=self.headers())
        self.assertFalse(response.json()["available"])
        self.assertTrue(response.json()["linked"])
        self.assertNotIn("upstream-private-error", response.text)
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 503)
        self.unavailable = False
        self.login_page = True
        self.assertFalse(self.client.get("/api/enterprise/status", headers=self.headers()).json()["available"])
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 502)

    def test_proxy_preserves_multipart_and_rejects_login_html_and_redirects(self):
        self.link()
        payload = b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n\r\nbytes\r\n--boundary--\r\n"
        result = self.client.post("/api/enterprise/business/product/sources/", headers={**self.headers(), "Content-Type": "multipart/form-data; boundary=boundary", "Idempotency-Key": "original-product-key"}, content=payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.requests[-1].content, payload)
        self.assertEqual(self.requests[-1].headers["content-length"], str(len(payload)))
        self.assertEqual(self.requests[-1].headers["idempotency-key"], "original-product-key")
        self.assertNotIn("transfer-encoding", self.requests[-1].headers)
        streamed = self.client.post("/api/enterprise/business/product/sources/", headers=self.headers(), content=iter([b"first", b"second"]))
        self.assertEqual(streamed.status_code, 200)
        self.assertEqual(self.requests[-1].content, b"firstsecond")
        self.assertEqual(self.requests[-1].headers["content-length"], "11")
        self.assertNotIn("transfer-encoding", self.requests[-1].headers)
        self.business_response = lambda req: httpx.Response(200, text="login", headers={"Content-Type": "text/html"})
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 502)
        self.business_response = lambda req: httpx.Response(302, headers={"Location": "https://evil.test/"})
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 502)

    def test_sse_and_permission_denials_are_preserved(self):
        self.link()
        events = b"data: " + b"x" * 100000 + b"\n\ndata: done\n\n"
        self.business_response = lambda req: httpx.Response(200, content=events, headers={"Content-Type": "text/event-stream"})
        response = self.client.get("/api/enterprise/business/product/events/", headers={**self.headers(), "Accept": "text/event-stream"})
        self.assertEqual(response.content, events)
        self.assertEqual(response.headers["content-type"], "text/event-stream")
        self.assertIsNone(self.requests[-1].extensions["timeout"]["read"])
        self.business_response = lambda req: httpx.Response(403, json={"code": "source_permission_changed"})
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 403)
        self.assertTrue(self.client.get("/api/enterprise/status", headers=self.headers()).json()["linked"])

    def test_bad_login_password_change_and_derivation(self):
        self.assertEqual(self.link(password="wrong").status_code, 401)
        self.profile["must_change_password"] = True
        self.assertEqual(self.link().status_code, 403)
        self.profile["must_change_password"] = False
        self.profile["department_code"] = "engineering"
        self.modules = [{"code": "cost", "enabled": True}, {"code": "hr", "enabled": True}]
        self.assertEqual(self.link().json()["capabilities"], ["engineering"])
        self.profile["roles"] = [{"code": "general_manager"}]
        self.assertEqual(self.link().json()["business_role"], "employee")
        self.modules.append({"code": "business", "enabled": True})
        self.assertEqual(self.link().json()["business_role"], "general_manager")

    def test_unlink_keeps_identity_but_blocks_proxy_and_sensitive_paths(self):
        self.link()
        result = self.client.delete("/api/enterprise/link", headers=self.headers()).json()
        self.assertFalse(result["linked"])
        self.assertEqual(result["portal_user_id"], 42)
        self.assertEqual(result["capabilities"], ["product"])
        self.assertEqual(self.client.get("/api/enterprise/business/product/tasks/", headers=self.headers()).status_code, 401)
        for path in ("login/", "ops/users/", "admin/", "product/../ops/", "product/%2e%2e/ops/", "product//tasks/", "product/tasks//", "//evil.test/", "product/https://evil.test", "product\\..\\ops", "agent/conversations/", "agent/installations/"):
            with self.subTest(path=path), self.assertRaises(HTTPException):
                safe_business_path(path, "POST")
        self.assertEqual(safe_business_path("agent/work/history/events/", "GET"), "/api/agent/work/history/events/")
        with self.assertRaises(HTTPException):
            safe_business_path("agent/work/history/retry/", "POST")
        self.assertIn(self.client.get("/api/enterprise/status").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
