"""Run: python -m unittest discover -s platform/tests -p test_enterprise_identity.py

Uses a separate FastAPI app and in-memory SQLite only; no platform lifespan,
real database, Docker daemon, or original portal is started or contacted.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.service import create_access_token, hash_password
from app.db.engine import get_db
from app.db.models import AuditLog, Base, User
from app.enterprise import enterprise_identity
from app.routes import admin, auth


class AsyncSQLite:
    """Adapt the synchronous SQLite test session to the route's async DB API."""

    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, obj):
        self.session.refresh(obj)

    async def flush(self):
        self.session.flush()

    def add(self, obj):
        self.session.add(obj)


class EnterpriseIdentityTests(unittest.TestCase):
    def test_admin_creates_assigned_account_without_exposing_password(self):
        payload = {"username": "assigned-hr", "email": "assigned-hr@example.com", "password": "test-only-password", "business_role": "employee", "department_code": "hr", "portal_user_id": 84}
        url = "/api/admin/users"
        self.assertEqual(self.client.post(url, json=payload, headers=self.employee_headers).status_code, 403)
        self.assertEqual(self.client.post(url, json={**payload, "department_code": None}, headers=self.admin_headers).status_code, 422)
        created = self.client.post(url, json=payload, headers=self.admin_headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capabilities"], ["hr"])
        self.assertNotIn("password", created.text)
        self.assertNotIn("access_token", created.text)
        self.assertEqual(self.client.post(url, json=payload, headers=self.admin_headers).status_code, 409)
        with Session(self.engine) as db:
            assigned = db.get(User, created.json()["id"])
            self.assertIsNone(assigned.portal_session_enc)
            self.assertEqual(assigned.runtime_mode, "dedicated")
            audits = db.scalars(select(AuditLog).where(AuditLog.action == "user_create")).all()
            self.assertEqual(len(audits), 1)
            self.assertNotIn(payload["password"], str(audits[0].detail))
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([
                User(id="admin", username="admin-test", email="admin@test.invalid",
                     password_hash=hash_password("test-only-password"), role="admin"),
                User(id="employee", username="employee-test", email="employee@test.invalid",
                     password_hash="unused", role="user"),
                User(id="manager", username="manager-test", email="manager@test.invalid",
                     password_hash="unused", role="user", business_role="general_manager"),
            ])
            db.commit()

        async def test_db():
            with Session(self.engine, expire_on_commit=False) as session:
                yield AsyncSQLite(session)

        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(admin.router)
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)
        # Deliberately stale JWT roles; the DB role must decide administration.
        self.admin_headers = self.headers("admin", "user")
        self.employee_headers = self.headers("employee", "admin")

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    @staticmethod
    def headers(user_id, claim_role="user"):
        return {"Authorization": f"Bearer {create_access_token(user_id, claim_role)}"}

    def update(self, payload, user_id="employee", headers=None):
        return self.client.put(
            f"/api/admin/users/{user_id}", json=payload,
            headers=self.admin_headers if headers is None else headers,
        )

    def test_registration_cannot_assign_identity(self):
        fields = {"username": "new-test", "email": "new@test.invalid", "password": "test-only-password"}
        for extra in (
            {"business_role": "general_manager"}, {"department_code": "hr"},
            {"portal_user_id": 42}, {"role": "admin"}, {"portal_session_enc": "unsafe"},
        ):
            with self.subTest(extra=extra):
                self.assertEqual(self.client.post("/api/auth/register", json={**fields, **extra}).status_code, 422)
        registered = self.client.post("/api/auth/register", json=fields)
        self.assertEqual(registered.status_code, 201)
        profile = self.client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {registered.json()['access_token']}"}).json()
        self.assertEqual((profile["role"], profile["business_role"], profile["capabilities"]),
                         ("user", "unassigned", []))

    def test_current_database_identity_and_system_role_are_independent(self):
        unassigned = self.client.get("/api/auth/me", headers=self.admin_headers).json()
        self.assertEqual(unassigned["capabilities"], [])
        self.assertEqual(self.update({"business_role": "employee", "department_code": "hr"},
                                     headers=self.employee_headers).status_code, 403)
        self.assertEqual(self.update({"business_role": "employee", "department_code": "hr",
                                     "portal_user_id": 42}).status_code, 200)
        profile = self.client.get("/api/auth/me", headers=self.employee_headers).json()
        self.assertEqual(profile["role"], "user")
        self.assertEqual((profile["business_role"], profile["department_code"],
                          profile["portal_user_id"], profile["capabilities"]),
                         ("employee", "hr", 42, ["hr"]))
        manager = self.client.get("/api/auth/me", headers=self.headers("manager")).json()
        self.assertEqual(manager["role"], "user")
        self.assertEqual(manager["capabilities"], ["general_manager", "product", "hr", "engineering"])
        self.assertEqual(self.update({}, user_id="employee", headers=self.headers("manager")).status_code, 403)
        self.assertEqual(self.update({"business_role": "unassigned", "department_code": None}).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.employee_headers).json()["capabilities"], [])

    def test_invalid_identity_fields(self):
        for payload in (
            {"business_role": "admin"}, {"business_role": None},
            {"business_role": "employee"}, {"department_code": "finance"},
            {"department_code": "hr"}, {"role": "general_manager"},
            {"portal_user_id": 0}, {"portal_user_id": -1}, {"portal_user_id": True},
            {"portal_user_id": "42"}, {"portal_user_id": 1.5},
            {"portal_session_enc": "unsafe"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.update(payload).status_code, 422)

    def test_unique_mapping_unlink_and_private_session(self):
        self.assertEqual(self.update({"portal_user_id": 42}).status_code, 200)
        self.assertEqual(self.update({"portal_user_id": 42}, user_id="manager").status_code, 409)
        with Session(self.engine) as db:
            db.get(User, "employee").portal_session_enc = "test-encrypted-session"
            db.commit()
        profile = self.client.get("/api/auth/me", headers=self.employee_headers).json()
        self.assertNotIn("portal_session_enc", profile)
        items = self.client.get("/api/admin/users", headers=self.admin_headers).json()["items"]
        self.assertEqual(next(row for row in items if row["id"] == "employee")["portal_user_id"], 42)
        self.assertTrue(all("portal_session_enc" not in row for row in items))
        self.assertEqual(self.update({"portal_user_id": None}).status_code, 200)
        with Session(self.engine) as db:
            user = db.get(User, "employee")
            self.assertIsNone(user.portal_user_id)
            self.assertIsNone(user.portal_session_enc)
            self.assertGreater(len(db.scalars(select(AuditLog)).all()), 0)
        self.assertEqual(self.update({"portal_user_id": 42}, user_id="manager").status_code, 200)

    def test_unique_constraint_handles_write_race(self):
        user_result = SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(
            business_role="unassigned", department_code=None, portal_user_id=None))
        free_result = SimpleNamespace(scalar_one_or_none=lambda: None)
        db = SimpleNamespace(
            execute=AsyncMock(side_effect=[user_result, free_result, IntegrityError("update", {}, Exception())]),
            rollback=AsyncMock(),
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(admin.update_user("employee", admin.UpdateUserRequest(portal_user_id=42),
                                          db, SimpleNamespace(id="admin")))
        self.assertEqual(raised.exception.status_code, 409)
        db.rollback.assert_awaited_once()
        with Session(self.engine) as session:
            session.get(User, "employee").portal_user_id = 42
            session.get(User, "manager").portal_user_id = 42
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_missing_or_invalid_legacy_identity_is_unassigned(self):
        for legacy in (SimpleNamespace(role="admin"), SimpleNamespace(
            role="user", business_role="employee", department_code="finance")):
            self.assertEqual(enterprise_identity(legacy)["business_role"], "unassigned")
            self.assertEqual(enterprise_identity(legacy)["capabilities"], [])


if __name__ == "__main__":
    unittest.main()
