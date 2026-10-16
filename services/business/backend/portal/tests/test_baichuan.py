import copy
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.http import QueryDict
from django.test import Client, TransactionTestCase, override_settings

from portal.baichuan_models import Company, CompanyPerson, CompanyQualification, QUALIFICATION_GRADES
from portal.baichuan_service import (BaichuanError, COMPANY_FIELDS, can_access, company_detail, list_companies,
                                     save_company, validate_payload)
from portal.models import AuditEvent, Module, Role, User
from .base import PortalTestCase, csrf_client


ROOT = "/api/product/baichuan/companies/"


def payload(name="样例新增", **company):
    return {"company": {field: (name if field == "name" else company.get(field)) for field in COMPANY_FIELDS},
            "qualifications": [], "people": []}


def qualification(category="electronic", grade="1", status="PRESENT", **values):
    return {"category": category, "grade": grade, "status": status, **values}


class BaichuanTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("baichuan-product", "product")
        self.manager = self.create_user("baichuan-manager", "general_manager")
        self.reader = self.create_user("baichuan-reader", "product")
        self.outsider = self.create_user("baichuan-outsider", "hr")
        self.settings_override = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
            PORTAL_BAICHUAN_READ_USER_IDS=[self.user.pk, self.manager.pk, self.reader.pk, self.outsider.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.user.pk, self.manager.pk, self.outsider.pk])
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.login(self.client, self.user)

    def post(self, body):
        return self.client.post(ROOT, json.dumps(body), content_type="application/json")

    def put(self, row, body):
        return self.client.put(f"{ROOT}{row.pk}/", json.dumps(body), content_type="application/json")

    def snapshot(self, row):
        detail = company_detail(row, self.user)
        return {"company": {key: detail["company"][key] for key in COMPANY_FIELDS},
                "qualifications": detail["qualifications"], "people": detail["people"], "expected_version": row.version}

    def seed_companies(self):
        definitions = {
            "A": [qualification(), qualification("cmmi", "3"), qualification("itss", "2")],
            "B": [qualification(grade="2"), qualification("cmmi", "5"), qualification("itss", "3"), qualification("labor", None)],
            "C": [qualification(), qualification("cmmi", None), qualification("labor", None, "ABSENT")],
            "D": [qualification(grade=None, status="ABSENT")],
            "E": [qualification(), qualification(grade="2"), qualification("cmmi", "3")],
            "F": [qualification(), qualification("ccrc", "2")], "G": [],
        }
        rows = {}
        for label, records in definitions.items():
            data = payload(f"样例{label}")
            data["qualifications"] = records
            if label == "D":
                data["people"] = [{"name": "样例员工", "credentials": "电子与智能化一级"}]
            rows[label] = save_company(self.user, data)
        return rows

    def labels(self, query):
        data = list_companies(self.user, QueryDict(query))
        return {item["name"][-1] for item in data["items"]}

    def test_exact_or_and_any_seven_categories_and_no_cross_record_matching(self):
        rows = self.seed_companies()
        for query, expected in (("electronic=2", "BE"), ("electronic=1", "ACEF"), ("cmmi=3", "AE"),
                ("electronic=1,2", "ABCEF"), ("electronic=1,2&cmmi=3", "AE"),
                ("electronic=1,2&cmmi=3&itss=2", "A"), ("electronic=2&cmmi=5", "B"),
                ("cmmi=any", "ABCE"), ("labor=any", "B"), ("electronic=any", "ABCEF"), ("", "ABCDEFG")):
            with self.subTest(query=query):
                self.assertEqual(self.labels(query), set(expected))
        CompanyQualification.objects.create(company=rows["G"], category="electronic", status="UNKNOWN")
        self.assertEqual(self.labels("electronic=any"), set("ABCEF"))
        data = payload("样例H")
        data["qualifications"] = [qualification(key, None if key == "labor" else grades[0]) for key, grades in QUALIFICATION_GRADES.items()]
        save_company(self.user, data)
        query = "&".join(f"{key}={'any' if key == 'labor' else grades[0]}" for key, grades in QUALIFICATION_GRADES.items())
        self.assertEqual(self.labels(query), {"H"})

    def test_query_validation_pagination_deduplication_and_matching_ids(self):
        self.seed_companies()
        collected = []
        for page, count in ((1, 2), (2, 2), (3, 1)):
            response = self.client.get(ROOT, {"electronic": "any", "page_size": 2, "page": page})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual((data["total"], len(data["items"])), (5, count))
            collected.extend(item["id"] for item in data["items"])
        self.assertEqual(len(set(collected)), 5)
        self.assertEqual(self.labels("electronic=any&q=样例F"), {"F"})
        Company.objects.filter(name="样例E").update(website="https://example.com/")
        data = self.client.get(ROOT, {"electronic": "1", "q": "样例E"}).json()
        self.assertEqual(data["items"][0]["website"], "https://example.com/")
        self.assertEqual(len(data["items"][0]["qualifications"]), 3)
        self.assertEqual(len(data["items"][0]["matched_qualification_ids"]), 1)
        self.assertEqual(data["query"], {"q": "样例E", "filters": {"electronic": ["1"]}})
        self.assertEqual(self.client.get(ROOT + "?electronic=1,1").json()["total"], 4)
        self.assertEqual(self.client.get(ROOT + "?page=999").json()["total"], 7)
        for query in ("cs=0", "cmmi=2", "labor=1", "wrong=1", "electronic=", "page=0", "page=-1", "page=x", "page_size=101", "page_size=1.0", "cmmi=any,3", "q=a&q=b", "page=1&page=2", "electronic=1&electronic=2"):
            with self.subTest(query=query):
                response = self.client.get(ROOT + "?" + query)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["code"], "invalid_request")
                self.assertTrue(response.json()["errors"])

    def test_default_deny_and_same_permission_boundary_for_every_endpoint(self):
        row = save_company(self.user, payload())
        for scope in (False, True):
            with override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=scope, PORTAL_BAICHUAN_READ_USER_IDS=[]):
                self.assertEqual(self.client.get(ROOT).status_code, 403)
                self.assertEqual(self.client.get(f"{ROOT}{row.pk}/").status_code, 404)
                self.assertEqual(self.post(payload()).status_code, 403)
                self.assertEqual(self.put(row, self.snapshot(row)).status_code, 403)
        for user in (self.manager, self.reader):
            self.login(self.client, user)
            self.assertEqual(self.client.get(ROOT).json()["total"], 1)
            self.assertEqual(self.client.get(f"{ROOT}{row.pk}/").json()["company"]["id"], str(row.pk))
        self.assertFalse(self.client.get(ROOT).json()["permissions"]["can_create"])
        self.assertEqual(self.post(payload()).status_code, 403)
        self.assertEqual(self.put(row, self.snapshot(row)).status_code, 403)
        self.login(self.client, self.outsider)
        self.assertEqual(self.client.get(ROOT).status_code, 403)
        self.login(self.client, self.user)
        Module.objects.filter(code="product").update(enabled=False)
        self.assertEqual(self.client.get(ROOT).status_code, 403)
        self.assertEqual(Company.objects.count(), 1)

    def test_homepage_types_roundtrip_legacy_snapshot_and_invalid_type_is_atomic(self):
        for kind in ("corporate", "group_profile", "official_wechat"):
            response = self.post(payload("主页类型" + kind, website="https://example.com/company", website_kind=kind))
            self.assertEqual(response.status_code, 201, response.content)
            row = Company.objects.get(pk=response.json()["company"]["id"])
            self.assertEqual(response.json()["company"]["website_kind"], kind)
            listed = self.client.get(ROOT, {"q": row.name}).json()["items"]
            self.assertEqual(listed[0]["website_kind"], kind)
            legacy = self.snapshot(row)
            del legacy["company"]["website_kind"]
            self.assertEqual(self.put(row, legacy).status_code, 200)
            row.refresh_from_db()
            self.assertEqual(row.website_kind, kind)
            invalid = self.snapshot(row)
            invalid["company"]["website_kind"] = "third_party_directory"
            invalid["company"]["name"] = "不得保存"
            rejected = self.put(row, invalid)
            self.assertEqual(rejected.status_code, 400, rejected.content)
            self.assertIn("company.website_kind", rejected.json()["errors"])
            row.refresh_from_db()
            self.assertEqual((row.website_kind, row.name, row.version), (kind, "主页类型" + kind, 2))

    def test_authentication_csrf_and_no_delete_endpoint(self):
        self.assertEqual(Client().get(ROOT).status_code, 401)
        client = csrf_client()
        token = self.csrf_token(client)
        response = client.post("/api/login/", json.dumps({"username": self.user.username, "password": "Current!Pass9274-Qx"}), content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post(ROOT, json.dumps(payload()), content_type="application/json").status_code, 403)
        row = save_company(self.user, payload())
        self.assertEqual(self.client.delete(f"{ROOT}{row.pk}/").status_code, 405)
        self.assertEqual(self.client.get(f"{ROOT}{uuid.uuid4()}/").status_code, 404)
        malformed = self.client.get(f"{ROOT}not-a-uuid/")
        self.assertEqual(malformed.status_code, 404)
        self.assertEqual(malformed.json()["code"], "not_found")

    def test_create_minimal_preserves_text_and_rename_identity_and_audit(self):
        response = self.post({"company": {"name": "  名称  ", "phone": "010001", "contact_phone": "+86138000"}})
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        row = Company.objects.get(pk=data["company"]["id"])
        self.assertEqual((row.name, row.version, row.verified_on), ("名称", 1, None))
        self.assertEqual((row.phone, row.contact_phone), ("010001", "+86138000"))
        self.assertIsNone(data["company"]["website"])
        edited = self.snapshot(row)
        edited["company"]["name"] = "新名称"
        edited["people"] = [{"name": "同事", "reports_to_text": "有来源的主管"}]
        edited["qualifications"] = [qualification()]
        response = self.put(row, edited)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["company"]["id"], str(row.pk))
        self.assertEqual(response.json()["company"]["version"], 2)
        self.assertEqual(CompanyPerson.objects.get().company_id, row.pk)
        event = AuditEvent.objects.filter(action="baichuan_update").get()
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertNotIn("010001", json.dumps(event.changes))
        self.assertNotIn("有来源的主管", json.dumps(event.changes, ensure_ascii=False))

    def test_company_duplicates_and_name_warning(self):
        code = "91110000123456789X"
        first = save_company(self.user, payload("同名", credit_code=code))
        response = self.post(payload("另名", credit_code=code))
        self.assertEqual((response.status_code, response.json()["code"]), (409, "duplicate_company"))
        response = self.post(payload("同名"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["warnings"][0]["code"], "duplicate_name")
        self.assertEqual(self.post(payload("同名", credit_code="91110000123456788X")).status_code, 201)
        self.assertEqual(Company.objects.count(), 3)
        self.assertEqual(first.credit_code, code)

    def test_strict_inputs_urls_dates_children_and_states_are_atomic(self):
        valid = payload()
        valid["qualifications"] = [qualification(), qualification(grade="2")]
        self.assertEqual(self.post(valid).status_code, 201)
        invalid_inputs = [[], {"company": {"name": "  "}}, {"company": {"name": 5}}, {"company": {"name": "x", "unexpected": "x"}},
                          {**payload(), "people": {}}, {**payload(), "people": [{"name": ""}]}, {**payload(), "expected_version": True}]
        for website in ("javascript:alert(1)", "data:text/html,hi", "https://user:pass@example.com", "https://user@example.com", "http://", "https://example.com\\evil", "https://exa mple.com"):
            invalid_inputs.append(payload(website=website))
        for field, value in (("verified_on", "2026-02-30"), ("verified_on", "20261016"), ("verified_on", False), ("credit_code", "123"), ("email", "bad")):
            invalid_inputs.append(payload(**{field: value}))
        for records in ([qualification(), qualification(status="ABSENT", grade=None)],
                        [qualification(), qualification(status="UNKNOWN", grade=None)],
                        [qualification("labor", "1")], [qualification("cs", "0")],
                        [qualification(grade=1)], [qualification(), qualification()],
                        [qualification(certificate_no="cert"), qualification(grade="2", certificate_no="cert")]):
            invalid_inputs.append({**payload(), "qualifications": records})
        before = Company.objects.count()
        for data in invalid_inputs:
            with self.subTest(data=data):
                response = self.post(data)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Company.objects.count(), before)
        self.assertEqual(self.post(payload(website="https://example.com/path?x=1#section", verified_on="2026-10-16")).status_code, 201)
        response = self.client.post(ROOT, "{broken", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_snapshot_required_fields_owned_children_and_explicit_clear(self):
        data = payload()
        data["qualifications"], data["people"] = [qualification()], [{"name": "姓名"}]
        row = save_company(self.user, data)
        other = save_company(self.user, {**payload("另一家"), "people": [{"name": "他人"}]})
        original = self.snapshot(row)
        for key in ("company", "qualifications", "people", "expected_version"):
            edited = copy.deepcopy(original)
            del edited[key]
            self.assertEqual(self.put(row, edited).status_code, 400)
        edited = copy.deepcopy(original)
        del edited["company"]["phone"]
        self.assertEqual(self.put(row, edited).status_code, 400)
        edited = copy.deepcopy(original)
        edited["people"][0]["id"] = str(other.people.get().pk)
        self.assertEqual(self.put(row, edited).status_code, 400)
        self.assertEqual(self.snapshot(row), original)
        edited = copy.deepcopy(original)
        edited["qualifications"] = []
        edited["people"] = []
        self.assertEqual(self.put(row, edited).status_code, 200)
        self.assertFalse(row.qualifications.exists())
        self.assertFalse(row.people.exists())
        self.assertTrue(other.people.exists())

    def test_version_cas_conflict_preserves_first_snapshot_and_child_ids(self):
        row = save_company(self.user, {**payload(), "qualifications": [qualification()]})
        first, stale = self.snapshot(row), self.snapshot(row)
        first["company"]["name"] = "首份已保存"
        child_id = first["qualifications"][0]["id"]
        first["qualifications"][0]["grade"] = "2"
        self.assertEqual(self.put(row, first).status_code, 200)
        stale["company"]["name"] = "过期不得覆盖"
        stale["qualifications"] = []
        response = self.put(row, stale)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "version_conflict"))
        row.refresh_from_db()
        self.assertEqual((row.name, row.version), ("首份已保存", 2))
        self.assertEqual(str(row.qualifications.get().pk), child_id)
        self.assertEqual(row.qualifications.get().grade, "2")
        for version in (True, 0, -1, "2", None):
            edited = self.snapshot(row)
            edited["expected_version"] = version
            self.assertEqual(self.put(row, edited).status_code, 400)
        stale = self.snapshot(row)
        cleared = self.snapshot(row)
        cleared["qualifications"] = []
        self.assertEqual(self.put(row, cleared).status_code, 200)
        self.assertEqual(self.put(row, stale).json()["code"], "version_conflict")

    def test_validation_has_no_writes_and_mid_save_failure_rolls_back_everything(self):
        data = {**payload(), "people": [{"name": "姓名"}], "qualifications": [qualification()]}
        self.assertEqual(validate_payload(data)["company"]["name"], "样例新增")
        self.assertFalse(Company.objects.exists())
        with patch.object(CompanyPerson.objects, "create", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                save_company(self.user, data)
        self.assertEqual((Company.objects.count(), CompanyQualification.objects.count()), (0, 0))
        self.assertFalse(AuditEvent.objects.filter(action="baichuan_create").exists())
        row = save_company(self.user, payload())
        edited = self.snapshot(row)
        edited["company"]["name"] = "应回滚"
        edited["people"] = [{"name": "新增"}]
        with patch.object(CompanyPerson.objects, "create", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                save_company(self.user, edited, row.pk)
        row.refresh_from_db()
        self.assertEqual((row.name, row.version), ("样例新增", 1))

    def test_database_grade_state_and_credit_constraints(self):
        row = save_company(self.user, payload(credit_code="91110000123456789X"))
        for values in ({"category": "labor", "status": "PRESENT", "grade": "1"},
                       {"category": "cs", "status": "PRESENT", "grade": "6"},
                       {"category": "electronic", "status": "ABSENT", "grade": "1"},
                       {"category": "unknown", "status": "PRESENT", "grade": None}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CompanyQualification.objects.create(company=row, **values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(name="duplicate", credit_code=row.credit_code, created_by=self.user, updated_by=self.user)

    def test_cs_level_one_persists_and_filters_exactly_with_other_categories(self):
        for name, grade, cmmi in (("CS初始级", "1", "3"), ("CS二级", "2", "5")):
            response = self.post({**payload(name), "qualifications": [qualification("cs", grade), qualification("cmmi", cmmi)]})
            self.assertEqual(response.status_code, 201, response.content)
        data = self.client.get(ROOT, {"cs": "1"}).json()
        self.assertEqual([item["name"] for item in data["items"]], ["CS初始级"])
        row = Company.objects.get(name="CS初始级")
        self.assertEqual(row.qualifications.get(category="cs").grade, "1")
        detail = self.client.get(f"{ROOT}{row.pk}/").json()
        self.assertEqual(next(q["grade"] for q in detail["qualifications"] if q["category"] == "cs"), "1")
        self.assertEqual(self.client.get(ROOT, {"cs": "1,2"}).json()["total"], 2)
        self.assertEqual(self.client.get(ROOT, {"cs": "1,2", "cmmi": "3"}).json()["total"], 1)
        self.assertEqual(self.client.get(ROOT, {"cs": "1", "cmmi": "5"}).json()["total"], 0)

    def test_role_read_grants_never_implicitly_enable_writes(self):
        row = save_company(self.user, payload())
        with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[], PORTAL_BAICHUAN_WRITE_USER_IDS=[]):
            self.assertFalse(can_access(self.user))
            with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=["product", "general_manager"]):
                for user in (self.user, self.manager):
                    self.login(self.client, user)
                    self.assertFalse(self.client.get(ROOT).json()["permissions"]["can_create"])
                    detail = self.client.get(f"{ROOT}{row.pk}/").json()
                    self.assertFalse(detail["permissions"]["can_edit"])
                    self.assertEqual(self.post(payload()).status_code, 403)
                    self.assertEqual(self.put(row, self.snapshot(row)).status_code, 403)
                with override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=False):
                    self.assertFalse(can_access(self.manager))
                with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[self.user.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.user.pk]):
                    self.assertTrue(can_access(self.user, write=True))
                    self.login(self.client, self.user)
                    self.assertEqual(self.post(payload("显式名单写入")).status_code, 201)
                with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_READ_USER_IDS=[self.user.pk]):
                    self.assertFalse(can_access(self.user, write=True))
                with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=["product"]):
                    self.assertFalse(can_access(self.manager))
                with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=["general_manager"]):
                    self.assertFalse(can_access(self.user))
                with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=["hr"]), patch("portal.baichuan_service.product_user_allowed", return_value=True):
                    self.assertFalse(can_access(self.outsider))
                self.user.is_active = False
                self.assertFalse(can_access(self.user))
                self.user.is_active = True
                self.user.must_change_password = True
                self.assertFalse(can_access(self.user))
                Module.objects.filter(code="product").update(enabled=False)
                self.assertFalse(can_access(self.manager))

    def test_explicit_write_roles_require_read_grant_and_existing_product_access(self):
        with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[], PORTAL_BAICHUAN_WRITE_USER_IDS=[],
                               PORTAL_BAICHUAN_READ_ROLE_CODES=["product", "general_manager"],
                               PORTAL_BAICHUAN_WRITE_ROLE_CODES=["product", "general_manager"]):
            for user in (self.user, self.manager):
                self.login(self.client, user)
                self.assertTrue(self.client.get(ROOT).json()["permissions"]["can_create"])
                response = self.post(payload(user.username))
                self.assertEqual(response.status_code, 201, response.content)
                self.assertTrue(response.json()["permissions"]["can_edit"])
                row = Company.objects.get(pk=response.json()["company"]["id"])
                edited = self.snapshot(row)
                edited["company"]["name"] += "修改"
                self.assertEqual(self.put(row, edited).status_code, 200)
            with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=[]):
                self.assertFalse(can_access(self.user, write=True))
                self.assertFalse(can_access(self.manager, write=True))
                with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[self.user.pk]):
                    self.assertTrue(can_access(self.user, write=True))
            with override_settings(PORTAL_BAICHUAN_WRITE_ROLE_CODES=["product"]):
                self.assertFalse(can_access(self.manager, write=True))
            with override_settings(PORTAL_BAICHUAN_WRITE_ROLE_CODES=["general_manager"]):
                self.assertFalse(can_access(self.user, write=True))
                with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[self.user.pk]):
                    self.assertTrue(can_access(self.user, write=True))
            with override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=False):
                self.assertFalse(can_access(self.user, write=True))
            with override_settings(PORTAL_BAICHUAN_READ_ROLE_CODES=["hr"], PORTAL_BAICHUAN_WRITE_ROLE_CODES=["hr"]), patch("portal.baichuan_service.product_user_allowed", return_value=True):
                self.assertFalse(can_access(self.outsider, write=True))
            Module.objects.filter(code="product").update(enabled=False)
            self.assertFalse(can_access(self.user, write=True))
            self.assertFalse(can_access(self.manager, write=True))


class BaichuanConcurrencyTests(TransactionTestCase):
    def test_parallel_updates_commit_exactly_one_snapshot(self):
        if connection.vendor == "sqlite" and "mode=memory" in str(connection.settings_dict["NAME"]):
            self.skipTest("Run with a file SQLite test database; shared-memory SQLite cannot wait for writer locks.")
        call_command("seed_portal", stdout=StringIO())
        user = User.objects.create_user(username="concurrent-product", must_change_password=False)
        user.roles.add(Role.objects.get(code="product"))
        with override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[user.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[user.pk]):
            row = save_company(user, payload("并发原始"))
            barrier = threading.Barrier(2, timeout=10)

            def update(name):
                close_old_connections()
                try:
                    actor = User.objects.get(pk=user.pk)
                    data = {**payload(name), "expected_version": 1, "people": [{"name": name}]}
                    barrier.wait()
                    try:
                        save_company(actor, data, row.pk)
                        return ("saved", name)
                    except BaichuanError as error:
                        return (error.code, name)
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(update, ("会话一", "会话二")))
            self.assertEqual(sorted(result[0] for result in results), ["saved", "version_conflict"])
            row.refresh_from_db()
            saved_name = next(result[1] for result in results if result[0] == "saved")
            self.assertEqual((row.name, row.version, row.people.get().name), (saved_name, 2, saved_name))
            self.assertEqual(AuditEvent.objects.filter(action="baichuan_update").count(), 1)
