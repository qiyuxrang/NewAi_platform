"""Official SDK client -> ASGI MCP server -> fake authorized portal.

Run: python -m unittest discover -s platform/tests -p test_ragflow_mcp.py.
Uses in-memory SQLite; does not contact RAGFlow, a model, Docker or business DB.
"""

import json
import logging
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI, HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import ragflow_mcp as bridge
from app.business_client import CSRF_COOKIE, SESSION_COOKIE, seal_session
from app.config import settings
from app.db.models import Base, Container, User


class AsyncSQLite:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def refresh(self, user):
        self.session.refresh(user)


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.getLogger("mcp.server").setLevel(logging.WARNING)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.requests = []
        self.retrieved = False
        self.revoke_during_answer = False
        self.export_before = True
        self.export_after = True
        self.export_result = True
        self.admin_revoke = False
        self.expired = False
        self.engineering_locked = False
        self.engineering_revision = "a" * 64
        self.engineering_result_revision = "a" * 64
        self.creation_status = 201
        self.foreign_owner = False
        self.business_written = False
        self.patches = [patch.object(settings, "jwt_secret", "mcp-test-only-secret-for-32-characters"),
                        patch.object(settings, "portal_base_url", "http://portal.test"),
                        patch.object(settings, "portal_timeout_seconds", 10),
                        patch.object(bridge, "portal_client", self.portal_client),
                        patch.object(bridge, "async_session", self.db_factory)]
        for item in self.patches:
            item.start()
        with Session(self.engine) as db:
            for name, portal_id, department in (("alice", 42, "product"), ("bob", 43, "engineering"), ("carol", 44, "hr")):
                cookies = {SESSION_COOKIE: name, CSRF_COOKIE: "csrf-" + name}
                db.add(User(id=name, username=name, email=name + "@test.invalid", password_hash="unused",
                            role="admin" if name == "alice" else "user", business_role="employee",
                            department_code=department, portal_user_id=portal_id,
                            portal_session_enc=seal_session(name, portal_id, cookies, "csrf-" + name)))
                db.add(Container(id="runtime-" + name, user_id=name, container_token="container-" + name, status="running"))
            db.commit()
        self.app, self.manager = bridge.create_mcp_app()

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()

    @asynccontextmanager
    async def db_factory(self):
        with Session(self.engine, expire_on_commit=False) as db:
            yield AsyncSQLite(db)

    def portal_client(self, cookies=None):
        return httpx.AsyncClient(base_url="http://portal.test", cookies=cookies,
                                transport=httpx.MockTransport(self.portal), follow_redirects=False)

    def portal(self, request):
        self.requests.append(request)
        name = next(name for name in ("alice", "bob", "carol") if SESSION_COOKIE + "=" + name in request.headers.get("cookie", ""))
        portal_id, department, module = {"alice": (42, "product", "product"), "bob": (43, "engineering", "cost"), "carol": (44, "hr", "hr")}[name]
        self.assertNotIn("authorization", request.headers)
        if self.expired:
            return httpx.Response(401, json={"detail": "expired"})
        path = request.url.path
        export_allowed = self.export_after if self.retrieved else self.export_before
        export_policy = {} if export_allowed is None else {"assistant_export_allowed": export_allowed}
        export_result = {} if self.export_result is None else {"assistant_export_allowed": self.export_result}
        if path == "/api/me/":
            return httpx.Response(200, json={"id": portal_id, "roles": [{"code": department}],
                "department_code": department, "must_change_password": False})
        if path == "/api/modules/":
            return httpx.Response(200, json=[{"code": module, "enabled": True}])
        if request.method == "POST":
            self.assertEqual(request.headers["x-csrftoken"], "csrf-" + name)
            self.assertEqual(request.headers["origin"], "http://portal.test")
        if path == "/api/product/knowledge/status/":
            revision = "b" * 64 if self.revoke_during_answer and self.retrieved else "a" * 64
            return httpx.Response(200, json={"available": True, "code": "ready", "authorization_revision": revision,
                                           **export_policy})
        if path == "/api/product/knowledge/retrieve/":
            self.assertEqual(name, "alice")
            self.assertEqual(set(json.loads(request.content)), {"question"})
            self.retrieved = True
            if self.admin_revoke:
                with Session(self.engine) as db:
                    user = db.get(User, "alice")
                    user.portal_session_enc = None
                    user.business_role = "unassigned"
                    db.commit()
            return httpx.Response(200, json={"status": "completed", "authorization_revision": "a" * 64,
                **export_result,
                "sources": [{"id": "S1", "chunk_id": "chunk-1", "dataset_id": "authorized-dataset",
                             "document_id": "authorized-doc", "content": "private-source-body"}]})
        if path == "/api/engineering/knowledge/retrieve/":
            self.assertEqual(name, "bob")
            self.assertEqual(set(json.loads(request.content)), {"question"})
            self.retrieved = True
            return httpx.Response(200, json={"status": "completed", **export_result,
                "authorization_revision": self.engineering_result_revision,
                "sources": [{"document_id": "engineering-doc", "content": "engineering-source"}]})
        if path == "/api/engineering/knowledge/":
            revision = "b" * 64 if self.revoke_during_answer and self.retrieved else self.engineering_revision
            return httpx.Response(200, json={"status": "locked" if self.engineering_locked else "ready",
                "authorization_revision": revision, **export_policy})
        task_id, request_id, draft_id = ["00000000-0000-0000-0000-00000000000" + str(n) for n in (1, 2, 3)]
        task = {"id": task_id, "owner_id": 99 if self.foreign_owner else 42,
                "version": 1, "state": "DRAFT", "stage": "INTAKE", "title": "project", "configuration": "private-config"}
        row = {"id": request_id, "created_by_id": 99 if self.foreign_owner else 44,
               "input_version": 1, "position_name": "engineer", "salary": "private-salary", "original_text": "private-hr-body"}
        draft = {"id": draft_id, "request_id": request_id, "version": 1, "state": "draft", "body": "private-jd-body"}
        if path in {"/api/product/conversations/", "/api/hr/recruitment/requests/intake/"}:
            if path == "/api/product/conversations/":
                self.assertEqual(name, "alice")
                self.assertEqual(set(json.loads(request.content)), {"message", "paths", "requested_outputs"})
                self.assertEqual(json.loads(request.content)["paths"], [])
                self.assertEqual(json.loads(request.content)["requested_outputs"], [])
                self.assertRegex(request.headers["idempotency-key"], r"^mcp-draft-[0-9a-f-]{36}$")
                result = {"task": task, "intent": {"model_called": False}}
            else:
                self.assertEqual(name, "carol")
                self.assertEqual(set(json.loads(request.content)), {"text"})
                result = {"request": row, "jd": draft}
            self.business_written = True
            if self.admin_revoke:
                with Session(self.engine) as db:
                    db.get(User, name).portal_session_enc = None
                    db.commit()
            return httpx.Response(self.creation_status, json=result)
        if path == f"/api/product/tasks/{task_id}/":
            return httpx.Response(200, json=task)
        if path == f"/api/hr/recruitment/requests/{request_id}/":
            return httpx.Response(200, json=row)
        if path == f"/api/hr/recruitment/requests/{request_id}/jd-versions/":
            return httpx.Response(200, json=[draft])
        if path == "/api/product/tasks/":
            return httpx.Response(200, json=[{**task, "id": f"00000000-0000-0000-0000-{n:012d}"} for n in range(1, 25)] + [{**task, "owner_id": 99}])
        if path == "/api/hr/recruitment/requests/":
            return httpx.Response(200, json=[row, {**row, "created_by_id": 99}])
        if path == "/api/engineering/jobs/":
            return httpx.Response(200, json={"jobs": [{"id": task_id, "status": "completed", "region": "cn", "inspection": "private-inspection", "result": "private-engineering-body"}], "capabilities": "private-config"})
        return httpx.Response(404, json={"detail": "unknown"})

    @asynccontextmanager
    async def client(self, token="container-alice"):
        app, manager = bridge.create_mcp_app()
        platform = FastAPI()
        platform.mount("/api/enterprise", app)
        async with manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=platform),
                headers={"Authorization": "Bearer " + token}) as http:
                async with streamable_http_client("http://127.0.0.1/api/enterprise/mcp", http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session

    async def test_real_sdk_initialization_catalog_and_authorized_calls(self):
        async with self.client() as session:
            catalog = await session.list_tools()
            self.assertEqual({t.name for t in catalog.tools}, {"product_knowledge_retrieve", "engineering_knowledge_retrieve",
                "product_create_draft", "hr_create_intake_draft", "department_work_list"})
            for tool in catalog.tools:
                self.assertEqual(len(tool.inputSchema["properties"]), 1)
                self.assertFalse(tool.inputSchema["additionalProperties"])
                self.assertNotIn("authorized-dataset", tool.description)
            answered = await session.call_tool("product_knowledge_retrieve", {"question": "test-question"})
            self.assertFalse(answered.isError)
            result = json.loads(answered.content[0].text)
            self.assertEqual(result["sources"][0]["id"], "S1")
            self.assertNotIn("authorization_revision", result)
            self.assertFalse(any("conversations" in r.url.path for r in self.requests))
            denied = await session.call_tool("engineering_knowledge_retrieve", {"question": "test"})
            self.assertTrue(denied.isError)
        async with self.client("container-bob") as session:
            answered = await session.call_tool("engineering_knowledge_retrieve", {"question": "test-engineering"})
            self.assertFalse(answered.isError)
            self.assertEqual(json.loads(answered.content[0].text)["sources"][0]["document_id"], "engineering-doc")
            denied = await session.call_tool("product_knowledge_retrieve", {"question": "test"})
            self.assertTrue(denied.isError)

    async def test_foreign_tokens_and_unbound_disabled_users_cannot_initialize(self):
        for token in ("shared-global-token", "browser-jwt", "forged-token"):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app)) as http:
                result = await http.post("http://127.0.0.1/mcp", headers={"Authorization": "Bearer " + token}, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                self.assertEqual(result.status_code, 401)
                self.assertEqual(result.headers["cache-control"], "no-store")
                self.assertNotIn(token, result.text)
        for change in ("is_active", "portal_session_enc"):
            with Session(self.engine) as db:
                user = db.get(User, "alice")
                original = getattr(user, change)
                setattr(user, change, False if change == "is_active" else None)
                db.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app)) as http:
                result = await http.post("http://127.0.0.1/mcp", headers={"Authorization": "Bearer container-alice"}, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                self.assertEqual(result.status_code, 401)
            with Session(self.engine) as db:
                setattr(db.get(User, "alice"), change, original)
                db.commit()

    async def test_clients_cannot_select_dataset_document_key_or_user(self):
        async with self.client() as session:
            for extra in ({"dataset_ids": ["other-dataset"]}, {"document_ids": ["other-doc"]},
                          {"api_key": "forbidden-secret"}, {"user_id": "bob"}, {"url": "http://evil.test"}):
                before = len(self.requests)
                result = await session.call_tool("product_knowledge_retrieve", {"question": "test", **extra})
                self.assertTrue(result.isError)
                self.assertNotIn("forbidden-secret", result.content[0].text)
                self.assertEqual(len(self.requests), before)
            self.assertTrue((await session.call_tool("product_knowledge_retrieve", {"question": " "})).isError)

    async def test_portal_partial_revocation_and_expiry_withhold_evidence(self):
        async with self.client() as session:
            self.revoke_during_answer = True
            revoked = await session.call_tool("product_knowledge_retrieve", {"question": "test"})
            self.assertTrue(revoked.isError)
            self.assertNotIn("private-source-body", revoked.content[0].text)
            self.revoke_during_answer = False
            self.expired = True
            expired = await session.call_tool("product_knowledge_retrieve", {"question": "test"})
            self.assertTrue(expired.isError)
            self.assertNotIn("private-source-body", expired.content[0].text)

    async def test_platform_revocation_during_answer_withholds_evidence(self):
        async with self.client() as session:
            self.admin_revoke = True
            result = await session.call_tool("product_knowledge_retrieve", {"question": "test"})
            self.assertTrue(result.isError)
            self.assertNotIn("private-source-body", result.content[0].text)

    async def test_assistant_export_requires_explicit_true_before_retrieval(self):
        for token, department in (("container-alice", "product"), ("container-bob", "engineering")):
            for value in (False, None, 1, "true"):
                with self.subTest(department=department, value=value):
                    self.requests.clear()
                    self.retrieved = False
                    self.export_before = value
                    with self.assertRaises(HTTPException) as caught:
                        await bridge.knowledge_question(token, department, "test")
                    self.assertEqual(caught.exception.status_code, 403)
                    self.assertFalse(self.retrieved)
                    self.assertFalse(any(r.url.path.endswith("/retrieve/") for r in self.requests))

    async def test_assistant_export_rechecked_on_status_and_retrieval_result(self):
        for token, department in (("container-alice", "product"), ("container-bob", "engineering")):
            for field in ("export_after", "export_result"):
                for value in (False, None, 1, "true"):
                    with self.subTest(department=department, field=field, value=value):
                        self.retrieved = False
                        self.export_after = self.export_result = True
                        setattr(self, field, value)
                        with self.assertRaises(HTTPException) as caught:
                            await bridge.knowledge_question(token, department, "test")
                        self.assertEqual(caught.exception.status_code, 403)
                        self.assertTrue(self.retrieved)
                        self.assertNotIn("private-source-body", caught.exception.detail)
                        self.assertNotIn("engineering-source", caught.exception.detail)

    async def test_sdk_export_revocation_during_retrieval_withholds_evidence(self):
        for token, department in (("container-alice", "product"), ("container-bob", "engineering")):
            async with self.client(token) as session:
                for field in ("export_after", "export_result"):
                    for value in (False, None):
                        with self.subTest(department=department, field=field, value=value):
                            self.retrieved = False
                            self.export_after = self.export_result = True
                            setattr(self, field, value)
                            result = await session.call_tool(department + "_knowledge_retrieve", {"question": "test"})
                            self.assertTrue(result.isError)
                            self.assertEqual(json.loads(result.content[0].text)["code"], "knowledge_denied")
                            self.assertNotIn("private-source-body", result.content[0].text)
                            self.assertNotIn("engineering-source", result.content[0].text)

    async def test_engineering_checks_status_before_and_after_retrieval(self):
        result = await bridge.knowledge_question("container-bob", "engineering", "test")
        paths = [r.url.path for r in self.requests if "/knowledge/" in r.url.path]
        self.assertEqual(paths, ["/api/engineering/knowledge/", "/api/engineering/knowledge/retrieve/",
                                 "/api/engineering/knowledge/"])
        self.assertEqual(set(result), {"status", "sources"})

    async def test_engineering_partial_revocation_withholds_evidence(self):
        self.revoke_during_answer = True
        async with self.client("container-bob") as session:
            result = await session.call_tool("engineering_knowledge_retrieve", {"question": "test"})
            self.assertTrue(result.isError)
            self.assertEqual(json.loads(result.content[0].text)["code"], "knowledge_denied")
            self.assertNotIn("engineering-source", result.content[0].text)

    async def test_engineering_requires_revision_and_accepts_explicit_legacy_revision(self):
        for revision in (None, ""):
            with self.subTest(revision=revision):
                self.engineering_revision = revision
                with self.assertRaises(HTTPException) as caught:
                    await bridge.knowledge_question("container-bob", "engineering", "test")
                self.assertEqual(caught.exception.status_code, 403)
                self.assertFalse(self.retrieved)
        self.engineering_revision = "legacy"
        self.engineering_result_revision = "legacy"
        result = await bridge.knowledge_question("container-bob", "engineering", "test")
        self.assertEqual(result["sources"][0]["document_id"], "engineering-doc")

    async def test_engineering_rejects_missing_or_mismatched_retrieval_revision(self):
        for revision in (None, "", "b" * 64):
            with self.subTest(revision=revision):
                self.retrieved = False
                self.engineering_result_revision = revision
                with self.assertRaises(HTTPException) as caught:
                    await bridge.knowledge_question("container-bob", "engineering", "test")
                self.assertEqual(caught.exception.status_code, 403)
                self.assertTrue(self.retrieved)

    async def test_engineering_check_revoked_and_catalog_refresh_authenticates_each_request(self):
        async with self.client("container-bob") as session:
            self.engineering_locked = True
            result = await session.call_tool("engineering_knowledge_retrieve", {"question": "test"})
            self.assertTrue(result.isError)
            self.assertNotIn("engineering-source", result.content[0].text)
            with Session(self.engine) as db:
                db.get(User, "bob").is_active = False
                db.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app)) as http:
                response = await http.post("http://127.0.0.1/mcp", headers={"Authorization": "Bearer container-bob"},
                    json={"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
                self.assertEqual(response.status_code, 401)

    async def test_sdk_creates_only_owned_input_drafts_with_201_and_review_links(self):
        async with self.client() as session:
            result = await session.call_tool("product_create_draft", {"message": 'Project C:\\private\\secret.xlsx'})
            self.assertFalse(result.isError)
            value = json.loads(result.content[0].text)
            self.assertEqual(value["state"], "DRAFT")
            self.assertFalse(value["artifact_available"])
            self.assertEqual(value["version"], 1)
            self.assertEqual(value["review_url"], "/departments/product/documents?task=" + value["task_id"])
        async with self.client("container-carol") as session:
            result = await session.call_tool("hr_create_intake_draft", {"text": "need engineer"})
            self.assertFalse(result.isError)
            value = json.loads(result.content[0].text)
            self.assertEqual(value["state"], "draft")
            self.assertEqual(value["input_version"], 1)
            self.assertEqual(value["review_url"], "/departments/hr/jobs")
            self.assertNotIn("private-jd-body", result.content[0].text)
        self.assertFalse(any(any(part in r.url.path for part in ("queue", "generate", "confirm", "decisions", "agent/run")) for r in self.requests))

    async def test_sdk_business_schema_inputs_and_departments_are_enforced(self):
        async with self.client() as session:
            for tool, args in (("product_create_draft", {"message": "test", "paths": ["/private"]}),
                ("product_create_draft", {"message": "test", "requested_outputs": ["presentation"]}),
                ("product_create_draft", {"message": "test", "owner_id": 44}),
                ("product_create_draft", {"message": "x" * 8001}),
                ("product_create_draft", {"message": " "}),
                ("hr_create_intake_draft", {"text": "test", "confirm": True}),
                ("department_work_list", {"department": "admin"}),
                ("department_work_list", {"department": "product", "limit": 500})):
                before = len(self.requests)
                self.assertTrue((await session.call_tool(tool, args)).isError)
                self.assertEqual(before, len(self.requests))
            self.assertTrue((await session.call_tool("hr_create_intake_draft", {"text": "test"})).isError)
            self.assertTrue((await session.call_tool("department_work_list", {"department": "engineering"})).isError)
        self.assertFalse(self.business_written)

    async def test_sdk_business_drafts_reject_wrong_status_owner_and_expired_session(self):
        for token, tool, args in (("container-alice", "product_create_draft", {"message": "test"}),
                                  ("container-carol", "hr_create_intake_draft", {"text": "test"})):
            async with self.client(token) as session:
                for field, bad in (("creation_status", 200), ("creation_status", 202), ("foreign_owner", True), ("expired", True)):
                    original = getattr(self, field)
                    setattr(self, field, bad)
                    result = await session.call_tool(tool, args)
                    self.assertTrue(result.isError)
                    self.assertNotIn("draft_created", result.content[0].text)
                    setattr(self, field, original)

    async def test_sdk_post_write_revocation_withholds_draft_receipt(self):
        for token, tool, args in (("container-alice", "product_create_draft", {"message": "test"}),
                                  ("container-carol", "hr_create_intake_draft", {"text": "test"})):
            async with self.client(token) as session:
                self.admin_revoke = True
                result = await session.call_tool(tool, args)
                self.assertTrue(self.business_written)
                self.assertTrue(result.isError)
                self.assertNotIn("draft_created", result.content[0].text)
                self.assertNotIn("task_id", result.content[0].text)
                self.admin_revoke = False

    async def test_sdk_lists_bounded_owned_summaries_without_private_bodies(self):
        for token, department in (("container-alice", "product"), ("container-carol", "hr"), ("container-bob", "engineering")):
            async with self.client(token) as session:
                result = await session.call_tool("department_work_list", {"department": department})
                self.assertFalse(result.isError)
                value = json.loads(result.content[0].text)
                self.assertEqual(len(value["items"]), 20 if department == "product" else 1)
                self.assertEqual(value["truncated"], department == "product")
                self.assertNotIn("private-", result.content[0].text)
                self.assertFalse(any(key in row for row in value["items"] for key in ("owner_id", "created_by_id", "salary", "configuration", "inspection", "result", "original_text")))


if __name__ == "__main__":
    unittest.main()
