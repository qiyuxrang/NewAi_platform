"""Isolation-only initialization checks; no source workbook or live database edits."""
import copy
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext

from portal.baichuan_import import (COMPANY_HEADERS, PERSON_HEADERS, DEFAULT_MAPPING,
                                    apply_import, preview_import)
from portal.baichuan_models import Company, CompanyPerson, CompanyQualification
from portal.baichuan_service import BaichuanError, save_company, company_detail
from portal.models import AuditEvent
from .base import PortalTestCase


def workbook(path, companies=(), people=(), mapping=None):
    """Minimal OOXML test input, not an authored user deliverable."""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    book = ET.Element(f"{{{namespace}}}workbook")
    sheets = ET.SubElement(book, f"{{{namespace}}}sheets")
    relations = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    mapping = mapping or DEFAULT_MAPPING
    with ZipFile(path, "w") as archive:
        for index, (name, columns, rows) in enumerate(((mapping["company_sheet"], mapping["company_columns"], companies),
                                                      (mapping["people_sheet"], mapping["people_columns"], people)), 1):
            ET.SubElement(sheets, f"{{{namespace}}}sheet", name=name, sheetId=str(index), attrib={f"{{{rel}}}id": f"r{index}"})
            ET.SubElement(relations, "Relationship", Id=f"r{index}", Target=f"worksheets/sheet{index}.xml", Type=f"{rel}/worksheet")
            sheet = ET.Element(f"{{{namespace}}}worksheet")
            data = ET.SubElement(sheet, f"{{{namespace}}}sheetData")
            all_rows = [dict(zip(columns.values(), columns))] + list(rows)
            for number, values in enumerate(all_rows, 1):
                row = ET.SubElement(data, f"{{{namespace}}}row", r=str(number))
                for position, field in enumerate(columns.values()):
                    value = values.get(field)
                    if value is None:
                        continue
                    letter, number_col = "", position + 1
                    while number_col:
                        number_col, digit = divmod(number_col - 1, 26)
                        letter = chr(65 + digit) + letter
                    cell = ET.SubElement(row, f"{{{namespace}}}c", r=f"{letter}{number}", t="str")
                    if isinstance(value, tuple):
                        kind, value = value
                        if kind == "formula":
                            ET.SubElement(cell, f"{{{namespace}}}f").text = value
                            value = ""
                        else:
                            cell.set("t", kind)
                    ET.SubElement(cell, f"{{{namespace}}}v").text = str(value)
            archive.writestr(f"xl/worksheets/sheet{index}.xml", ET.tostring(sheet))
        archive.writestr("xl/workbook.xml", ET.tostring(book))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(relations))
    return path


class BaichuanImportTests(PortalTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "isolated.xlsx"
        self.user = self.create_user("isolated-importer", "product")
        self.access = self.settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
                                    PORTAL_BAICHUAN_READ_USER_IDS=[self.user.pk],
                                    PORTAL_BAICHUAN_WRITE_USER_IDS=[self.user.pk])
        self.access.enable()
        self.addCleanup(self.access.disable)

    def valid_manifest(self, companies=None, people=None):
        workbook(self.source, companies or [{"name": "隔离样例", "electronic": "一级", "cmmi": "三级", "phone": "+86 01000123", "verified_on": "2026-10-01"}],
                 people if people is not None else [{"company_name": "隔离样例", "name": "虚构人员", "credentials": "电子与智能化一级"}])
        report = preview_import(self.source)
        self.assertEqual(report["issues"], [])
        report["confirmed"] = True
        return report

    def test_delivered_blank_template_and_preview_have_no_writes(self):
        template = Path(__file__).resolve().parents[5] / "doc/baichuan-sdd/assets/initial-template.xlsx"
        before = template.read_bytes()
        with CaptureQueriesContext(connection) as queries:
            report = preview_import(template)
        self.assertEqual(report["counts"]["companies"], 0)
        self.assertEqual(report["counts"]["people"], 0)
        self.assertEqual(report["issues"], [])
        self.assertEqual(template.read_bytes(), before)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.assertFalse(Company.objects.exists())

    def test_preflight_collects_all_errors_and_preserves_unknowns_and_notes(self):
        workbook(self.source, [
            {"name": "重复一", "credit_code": "91110000123456789A"},
            {"name": "重复二", "credit_code": "91110000123456789A"},
            {"name": "重名"}, {"name": "重名"},
            {"name": "非法", "cmmi": "二级", "website": "javascript:alert(1)", "verified_on": "2026-02-30", "email": "bad"},
            {"name": "待核对", "electronic": "一级", "notes": "电子与智能化二级另有一份"},
            {"name": "未知", "itss": "未知", "cmmi": "具备（等级待补充）", "phone": "001234"},
            {"name": "公式", "phone": ("formula", "1+1"), "credit_code": ("n", "12345")},
        ], [{"company_name": "不存在", "name": "孤立"}, {"company_name": "重名", "name": "歧义"},
            {"company_name": "待核对", "name": "非法人员", "verified_on": "2026-02-30"}])
        with CaptureQueriesContext(connection) as queries:
            report = preview_import(self.source)
        codes = {item["code"] for item in report["issues"]}
        self.assertTrue({"duplicate_credit_code", "ambiguous_company", "invalid_qualification", "notes_need_review", "orphan_person", "ambiguous_person", "invalid_cell", "identifier_not_text"}.issubset(codes))
        errors = str(report["issues"])
        for field in ("company.website", "company.verified_on", "company.email"):
            self.assertIn(field, errors)
        self.assertTrue(any(item["source"] == "核心人员:4" and "people.0.verified_on" in item.get("errors", {}) for item in report["issues"]))
        unknown = next(item for item in report["records"] if item["company"]["name"] == "未知")
        qualifications = {item["category"]: item for item in unknown["qualifications"]}
        self.assertEqual(qualifications["itss"]["status"], "UNKNOWN")
        self.assertEqual((qualifications["cmmi"]["status"], qualifications["cmmi"]["grade"]), ("PRESENT", None))
        self.assertEqual(unknown["company"]["phone"], "001234")
        self.assertIn("电子与智能化二级另有一份", json.dumps(report, ensure_ascii=False))
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.assertFalse(Company.objects.exists())

    def test_alias_mapping_and_manual_multi_certificate_normalization(self):
        mapping = copy.deepcopy(DEFAULT_MAPPING)
        mapping["company_columns"] = {"企业名称": "name", "电子资质": "electronic", "其他说明": "notes"}
        notes = "电子与智能化一级及二级"
        mapping["notes_reviewed"] = {"企业资料:2": notes}
        mapping["qualification_overrides"] = {"企业资料:2": [
            {"category": "electronic", "status": "PRESENT", "grade": "1"},
            {"category": "electronic", "status": "PRESENT", "grade": "2"}]}
        workbook(self.source, [{"name": "改列表头", "electronic": "一级、二级", "notes": notes}], mapping=mapping)
        report = preview_import(self.source, mapping)
        self.assertEqual(report["issues"], [])
        self.assertEqual({item["grade"] for item in report["records"][0]["qualifications"]}, {"1", "2"})
        self.assertEqual(report["source_rows"][0]["row"], 2)
        report["confirmed"] = True
        apply_import(self.source, report, self.user)
        self.assertEqual(CompanyQualification.objects.count(), 2)

    def test_stable_ids_atomic_creation_and_idempotency_without_receipt(self):
        manifest = self.valid_manifest()
        repeated = preview_import(self.source)
        self.assertEqual(manifest["records"], repeated["records"])
        created = apply_import(self.source, manifest, self.user)
        self.assertEqual(created["counts"]["create"], 1)
        self.assertEqual((Company.objects.count(), CompanyQualification.objects.count(), CompanyPerson.objects.count()), (1, 2, 1))
        self.assertEqual(str(Company.objects.get().id), manifest["records"][0]["id"])
        self.assertIn("企业资料:2", Company.objects.get().source)
        replay = apply_import(self.source, manifest, self.user)
        self.assertEqual(replay["counts"]["skip"], 1)
        self.assertEqual(replay["counts"]["create"], 0)
        self.assertEqual(AuditEvent.objects.filter(action="baichuan.import").count(), 1)

    def test_midway_database_error_rolls_back_company_children_and_audit(self):
        manifest = self.valid_manifest()
        with patch("portal.baichuan_import.CompanyPerson.objects.create", side_effect=IntegrityError("isolated failure")):
            with self.assertRaises(IntegrityError):
                apply_import(self.source, manifest, self.user)
        self.assertEqual((Company.objects.count(), CompanyQualification.objects.count(), CompanyPerson.objects.count()), (0, 0, 0))
        self.assertFalse(AuditEvent.objects.filter(action="baichuan.import").exists())

    def test_page_edit_and_child_change_are_conflicts_not_overwrites(self):
        manifest = self.valid_manifest()
        apply_import(self.source, manifest, self.user)
        company = Company.objects.get()
        detail = company_detail(company, self.user)
        payload = {"company": {key: value for key, value in detail["company"].items() if key in manifest["records"][0]["company"]},
                   "qualifications": detail["qualifications"], "people": detail["people"], "expected_version": 1}
        payload["company"]["name"] = "页面改名"
        save_company(self.user, payload, company.id)
        with self.assertRaises(BaichuanError) as raised:
            apply_import(self.source, manifest, self.user)
        self.assertEqual(raised.exception.code, "import_conflicts")
        self.assertEqual(Company.objects.get().name, "页面改名")

    def test_file_mapping_or_manifest_changes_are_rejected(self):
        manifest = self.valid_manifest()
        changed = copy.deepcopy(manifest)
        changed["records"][0]["company"]["name"] = "篡改"
        with self.assertRaises(BaichuanError):
            apply_import(self.source, changed, self.user)
        changed_mapping = copy.deepcopy(manifest["mapping"])
        changed_mapping["notes_reviewed"] = {"unknown:2": "changed"}
        with self.assertRaises(BaichuanError):
            apply_import(self.source, manifest, self.user, changed_mapping)
        workbook(self.source, [{"name": "文件变更"}])
        with self.assertRaises(BaichuanError):
            apply_import(self.source, manifest, self.user)
        self.assertFalse(Company.objects.exists())

    def test_permission_and_review_gates_default_deny(self):
        manifest = self.valid_manifest()
        with self.settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=False):
            with self.assertRaises(BaichuanError) as raised:
                apply_import(self.source, manifest, self.user)
        self.assertEqual(raised.exception.status, 403)
        manifest["confirmed"] = False
        with self.assertRaises(BaichuanError):
            apply_import(self.source, manifest, self.user)
        self.assertFalse(Company.objects.exists())

    def test_same_name_distinct_codes_and_person_links_do_not_merge(self):
        workbook(self.source, [{"name": "同名", "credit_code": "91110000123456789A"},
                               {"name": "同名", "credit_code": "91110000123456789B"}],
                 [{"company_name": "同名", "credit_code": "91110000123456789B", "name": "明确人员"}])
        report = preview_import(self.source)
        self.assertEqual(report["issues"], [])
        report["confirmed"] = True
        apply_import(self.source, report, self.user)
        self.assertEqual(Company.objects.count(), 2)
        self.assertEqual(CompanyPerson.objects.get().company.credit_code, "91110000123456789B")

    def test_report_failure_after_commit_then_manifest_recovery(self):
        manifest = self.valid_manifest()
        manifest_path = self.root / "confirmed.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        arguments = {"input": str(self.source), "apply": True, "actor": self.user.username,
                     "manifest": str(manifest_path), "report": str(self.root / "result.json"), "stdout": StringIO()}
        with patch("portal.management.commands.import_baichuan.NamedTemporaryFile", side_effect=OSError("simulated receipt failure")):
            with self.assertRaisesMessage(CommandError, "数据库已提交"):
                call_command("import_baichuan", **arguments)
        self.assertEqual(Company.objects.count(), 1)
        call_command("import_baichuan", **arguments)
        result = json.loads((self.root / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["database_status"], "committed")
        self.assertEqual(result["counts"]["skip"], 1)
        self.assertEqual(CompanyPerson.objects.count(), 1)

    def test_existing_company_requires_explicit_link_and_frozen_snapshot(self):
        existing = save_company(self.user, {"company": {"name": "已有对象", "source": "现有来源"}})
        workbook(self.source, [{"name": "已有对象", "source": "原表新来源"}])
        self.assertIn("existing_company_conflict", {item["code"] for item in preview_import(self.source)["issues"]})
        mapping = copy.deepcopy(DEFAULT_MAPPING)
        mapping["company_links"] = {"企业资料:2": str(existing.id)}
        manifest = preview_import(self.source, mapping)
        self.assertEqual(manifest["issues"], [])
        manifest["confirmed"] = True
        result = apply_import(self.source, manifest, self.user)
        self.assertEqual(result["counts"]["skip"], 1)
        self.assertTrue(result["records"][0]["linked"])
        existing.refresh_from_db()
        self.assertEqual(existing.source, "现有来源")
        self.assertIn("原表新来源", json.dumps(result["source_rows"], ensure_ascii=False))
        existing.version += 1
        existing.save(update_fields=["version"])
        with self.assertRaises(BaichuanError) as raised:
            apply_import(self.source, manifest, self.user)
        self.assertEqual(raised.exception.code, "manifest_mismatch")

    def test_complete_override_cannot_drop_any_nonempty_original_category(self):
        workbook(self.source, [{"name": "完整覆盖", "electronic": "一级、二级", "cmmi": "三级", "itss": "未知", "labor": "不具备"}])
        mapping = copy.deepcopy(DEFAULT_MAPPING)
        for replacement in ([], [{"category": "electronic", "status": "PRESENT", "grade": "1"},
                                 {"category": "electronic", "status": "PRESENT", "grade": "2"}]):
            with self.subTest(replacement=replacement):
                mapping["qualification_overrides"] = {"企业资料:2": replacement}
                report = preview_import(self.source, mapping)
                issue = next(item for item in report["issues"] if item["code"] == "incomplete_qualification_override")
                self.assertTrue({"cmmi", "itss", "labor"}.issubset(issue["missing_categories"]))
                report["confirmed"] = True
                with self.assertRaises(BaichuanError):
                    apply_import(self.source, report, self.user)
        self.assertFalse(Company.objects.exists())
