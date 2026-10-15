"""Finance identity checks using the existing mock portal and in-memory SQLite.

Run: python -m unittest discover -s platform/tests -p test_finance_identity.py
"""

import unittest

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import test_business_bridge as bridge
import test_enterprise_identity as identity_tests
from app.business_client import SESSION_COOKIE
from app.db.models import User
from app.enterprise import enterprise_identity
from app.routes.admin import CreateUserRequest, UpdateUserRequest


class FinanceBridgeTests(unittest.TestCase):
    tearDown = bridge.BridgeTests.tearDown
    mock_client = bridge.BridgeTests.mock_client
    headers = staticmethod(bridge.BridgeTests.headers)
    link = bridge.BridgeTests.link

    def setUp(self):
        bridge.BridgeTests.setUp(self)
        self.profile.update(department_code="finance", roles=[{"code": "finance"}])
        self.modules = [{"code": "business", "enabled": True}]
        self.grants = [{"department": "finance", "can_edit": True, "can_submit": False, "can_publish": False}]
        self.permissions_response = None

    def portal(self, req):
        if req.url.path == "/api/business/ledgers/permissions/":
            self.requests.append(req)
            self.assertIn(SESSION_COOKIE + "=s-42", req.headers.get("cookie", ""))
            return self.permissions_response or httpx.Response(200, json={"departments": self.grants})
        return bridge.BridgeTests.portal(self, req)

    def test_finance_binding_status_and_proxy_share_verified_identity(self):
        bound = self.link()
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual((bound.json()["business_role"], bound.json()["department_code"], bound.json()["capabilities"]),
                         ("employee", "finance", ["finance"]))
        status = self.client.get("/api/enterprise/status", headers=self.headers())
        self.assertTrue(status.json()["available"])
        self.assertEqual(status.json()["capabilities"], ["finance"])
        path = "/api/enterprise/business/business/ledgers/finance/"
        response = self.client.get(path, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.requests[-1].url.path, "/api/business/ledgers/finance/")
        checks = [req for req in self.requests if req.url.path == "/api/business/ledgers/permissions/"]
        self.assertEqual(len(checks), 3)
        with Session(self.engine) as db:
            self.assertEqual(enterprise_identity(db.get(User, "alice"))["capabilities"], ["finance"])
        assistant = self.client.get("/api/enterprise/business/product/knowledge/status/", headers=self.headers())
        self.assertEqual(assistant.status_code, 200, assistant.text)
        self.assertEqual(self.requests[-1].url.path, "/api/product/knowledge/status/")
        self.business_response = lambda req: httpx.Response(403, json={"detail": "finance grant denied"})
        self.assertEqual(self.client.get(path, headers=self.headers()).status_code, 403)

    def test_absent_or_disabled_business_never_grants_finance(self):
        for modules in ([], [{"code": "business", "enabled": False}], [{"code": "finance", "enabled": True}]):
            with self.subTest(modules=modules):
                self.modules = modules
                result = self.link().json()
                self.assertEqual((result["business_role"], result["capabilities"]), ("unassigned", []))
        self.assertFalse(any(req.url.path == "/api/business/ledgers/permissions/" for req in self.requests))

    def test_finance_requires_original_department_and_matching_grant(self):
        for department, grants in ((None, self.grants), ("product", self.grants),
                                   ("finance", []), ("finance", [{"department": "presales", "can_edit": True}])):
            with self.subTest(department=department, grants=grants):
                self.profile["department_code"] = department
                self.grants = grants
                self.assertEqual(self.link().json()["capabilities"], [])

    def test_finance_is_primary_in_mixed_modules_and_old_fallback_is_preserved(self):
        self.modules += [{"code": "product", "enabled": True}, {"code": "hr", "enabled": True}, {"code": "cost", "enabled": True}]
        self.assertEqual(self.link().json()["capabilities"], ["finance"])
        self.grants = []
        self.assertEqual(self.link().json()["capabilities"], ["product"])
        for department, expected in (("product", "product"), ("hr", "hr"), ("cost", "engineering"),
                                     ("engineering", "engineering"), (None, "product")):
            with self.subTest(department=department):
                self.profile["department_code"] = department
                self.assertEqual(self.link().json()["capabilities"], [expected])

    def test_general_manager_capabilities_and_profile_requests_are_unchanged(self):
        self.profile["roles"] = [{"code": "general_manager"}]
        self.assertEqual(self.link().json()["capabilities"], ["general_manager", "product", "hr", "engineering"])
        self.modules = [{"code": "cost", "enabled": True}]
        self.assertEqual(self.link().json()["capabilities"], ["engineering"])
        self.assertFalse(any(req.url.path == "/api/business/ledgers/permissions/" for req in self.requests))

    def test_revoked_finance_grant_updates_status_and_blocks_proxy(self):
        self.assertEqual(self.link().status_code, 200)
        self.grants = []
        status = self.client.get("/api/enterprise/status", headers=self.headers()).json()
        self.assertEqual(status["capabilities"], [])
        self.assertEqual(self.client.get("/api/enterprise/business/business/ledgers/finance/", headers=self.headers()).status_code, 403)

    def test_invalid_finance_permission_response_fails_closed(self):
        for response, status in ((httpx.Response(200, json={}), 502),
                                 (httpx.Response(200, json={"departments": "finance"}), 502),
                                 (httpx.Response(403, json={"detail": "denied"}), 403)):
            with self.subTest(status=status):
                self.permissions_response = response
                self.assertEqual(self.link().status_code, status)


class FinanceAdminTests(unittest.TestCase):
    setUp = identity_tests.EnterpriseIdentityTests.setUp
    tearDown = identity_tests.EnterpriseIdentityTests.tearDown
    headers = identity_tests.EnterpriseIdentityTests.headers
    update = identity_tests.EnterpriseIdentityTests.update

    def test_admin_finance_assignment_schema_and_database_constraint(self):
        assignment = {"business_role": "employee", "department_code": "finance"}
        self.assertEqual(UpdateUserRequest(**assignment).department_code, "finance")
        payload = {**assignment, "username": "finance-test", "email": "finance@example.com", "password": "test-only-password"}
        self.assertEqual(CreateUserRequest(**payload).department_code, "finance")
        self.assertEqual(self.update(assignment, headers=self.employee_headers).status_code, 403)
        assigned = self.update(assignment)
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.employee_headers).json()["capabilities"], ["finance"])
        created = self.client.post("/api/admin/users", json=payload, headers=self.admin_headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capabilities"], ["finance"])
        self.assertEqual(self.update({"business_role": "unassigned", "department_code": "finance"}).status_code, 422)
        with Session(self.engine) as db:
            user = db.get(User, "employee")
            user.department_code = "unrecognized"
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            self.assertEqual(db.get(User, "employee").department_code, "finance")


if __name__ == "__main__":
    unittest.main()
