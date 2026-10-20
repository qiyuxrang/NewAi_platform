"""Synthetic six-sheet inputs; test DB only, no network or actual catalog writes."""
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

from portal.baichuan_national_import import HEADERS, SHEETS, _region, apply_catalog, preview_catalog, read_catalog
from portal.baichuan_models import Company, CompanyPerson, CompanyQualification
from portal.baichuan_service import BaichuanError, COMPANY_FIELDS, company_detail, save_company
from portal.models import AuditEvent
from .base import PortalTestCase


def workbook(path, rows=None, formula=False, bad_header=False):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    root = ET.Element(f"{{{ns}}}workbook")
    sheets = ET.SubElement(root, f"{{{ns}}}sheets")
    relations = ET.Element("Relationships")
    defaults = [
        [["1", "旧公司", "陕西-西安", "一级", "工程", "91110000123456789A", "历史", "来源平台", "https://example.org/e", "2026-10-19"]],
        [["1", "新 公司（集团）", "北京", "CS1级（初始级）", "系统", "CS1-1100-01", "有效", "来源平台", "https://example.org/cs", "2026-10-19"]],
        [["1", "新公司(集团)", "深圳", "ML3", "软件", "R&D Department (研发部)", "有效", "来源平台", "https://example.org/cmmi", "2026-10-19"]],
        [["1", "集成公司", "广东-广州市", "三级", "安全集成", "CCRC-2026-ISV-SI-01", "有效", "来源平台", "https://example.org/ccrc", "2026-10-19"]],
        [["1", "运维公司", "深圳", "四级", "运行维护", "ITSS-YW-4-01", "有效", "评估机构甲", "来源平台", "https://example.org/itss", "2026-10-19"]],
        [["1", "新公司(集团)", "北京", "一级", "安防", "", "历史", "评估机构乙", "来源平台", "https://example.org/s1", "2026-10-19"],
         ["2", "新公司(集团)", "北京", "三级", "安防", "", "有效", "评估机构乙", "来源平台", "https://example.org/s3", "2026-10-19"]]]
    rows = rows if rows is not None else defaults
    with ZipFile(path, "w") as archive:
        for index, ((name, category), data_rows) in enumerate(zip(SHEETS.items(), rows), 1):
            ET.SubElement(sheets, f"{{{ns}}}sheet", name=name, sheetId=str(index), attrib={f"{{{rel}}}id": f"r{index}"})
            ET.SubElement(relations, "Relationship", Id=f"r{index}", Target=f"worksheets/sheet{index}.xml")
            sheet = ET.Element(f"{{{ns}}}worksheet")
            data = ET.SubElement(sheet, f"{{{ns}}}sheetData")
            headers = list(HEADERS[:7] + ("评估机构",) + HEADERS[7:] if category in {"itss", "security"} else HEADERS)
            if bad_header and index == 1:
                headers[1] = "未知标题"
            for number, values in [(4, headers)] + [(i, value) for i, value in enumerate(data_rows, 5)]:
                row = ET.SubElement(data, f"{{{ns}}}row", r=str(number))
                for column, value in enumerate(values):
                    cell = ET.SubElement(row, f"{{{ns}}}c", r=f"{chr(65 + column)}{number}", t="str")
                    if formula and index == 1 and number == 5 and column == 1:
                        ET.SubElement(cell, f"{{{ns}}}f").text = 'HYPERLINK("https://example.org")'
                    ET.SubElement(cell, f"{{{ns}}}v").text = value
            archive.writestr(f"xl/worksheets/sheet{index}.xml", ET.tostring(sheet))
        archive.writestr("xl/workbook.xml", ET.tostring(root))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(relations))
    return defaults


class NationalCatalogTests(PortalTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "catalog.xlsx"
        self.rows = workbook(self.path)
        self.actor = self.create_user("national-maintainer", "product")
        self.access = self.settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
                                    PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk],
                                    PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
                                    PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        self.access.enable()
        self.addCleanup(self.access.disable)
        self.old = Company.objects.create(name="旧公司", phone="010-12345678", source="人工成果", province="原省",
                                          created_by=self.actor, updated_by=self.actor)
        self.person = CompanyPerson.objects.create(company=self.old, name="既有人员", source="原人员来源")
        self.old_qual = CompanyQualification.objects.create(company=self.old, category="labor", status="PRESENT", source="旧劳务")

    def manifest(self):
        manifest = preview_catalog(self.path)
        manifest["confirmed"] = True
        return manifest

    def test_parse_merge_two_header_forms_credit_grades_raw_and_multi_grade(self):
        catalog = read_catalog(self.path)
        self.assertEqual(catalog["counts"]["source_rows"], 7)
        self.assertEqual(catalog["counts"]["source_companies"], 4)
        self.assertEqual(catalog["companies"]["旧公司"]["company"]["credit_code"], "91110000123456789A")
        electronic = catalog["rows"][0]
        self.assertIsNone(electronic["qualification"]["certificate_no"])
        self.assertEqual(catalog["rows"][1]["qualification"]["grade"], "1")
        self.assertEqual(catalog["rows"][2]["qualification"]["grade"], "3")
        self.assertIsNone(catalog["rows"][2]["qualification"]["certificate_no"])
        self.assertEqual(catalog["rows"][4]["source"]["raw"]["评估机构"], "评估机构甲")
        self.assertEqual(catalog["rows"][4]["source"]["raw"]["来源链接"], "https://example.org/itss")
        self.assertEqual([row["qualification"]["grade"] for row in catalog["rows"][-2:]], ["1", "3"])
        new = catalog["companies"]["新公司(集团)"]["company"]
        self.assertEqual(new["province"], "北京市")
        self.assertIsNone(catalog["companies"]["运维公司"]["company"]["province"])
        self.assertEqual(catalog["companies"]["运维公司"]["company"]["city"], "深圳")
        self.assertEqual(_region("陕西省榆林市"), ("陕西省", "榆林市"))
        self.assertEqual(_region("北京-市辖区"), ("北京市", None))
        self.assertEqual(_region("北京"), ("北京市", None))
        self.assertEqual(_region("宁波"), (None, "宁波"))
        for row in catalog["rows"]:
            self.assertIn(catalog["file_sha256"], row["qualification"]["source"])
            self.assertIn(str(row["row"]), row["qualification"]["source"])

    def test_preview_has_no_writes(self):
        with CaptureQueriesContext(connection) as queries:
            report = self.manifest()
        self.assertEqual(report["counts"]["new_companies"], 3)
        self.assertEqual(report["counts"]["linked_companies"], 1)
        self.assertEqual(report["counts"]["add_qualifications"], 7)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.assertEqual(Company.objects.count(), 1)

    def test_append_preserves_old_rows_and_cas_blocks_stale_form(self):
        old_values = Company.objects.values().get(pk=self.old.pk)
        person = CompanyPerson.objects.values().get(pk=self.person.pk)
        qualification = CompanyQualification.objects.values().get(pk=self.old_qual.pk)
        detail = company_detail(self.old, self.actor)
        payload = {"company": {field: detail["company"][field] for field in COMPANY_FIELDS}, "qualifications": detail["qualifications"], "people": detail["people"], "expected_version": 1}
        result = apply_catalog(self.path, self.manifest(), self.actor)
        self.assertEqual(result["database_status"], "committed")
        self.old.refresh_from_db()
        self.assertEqual(self.old.version, 2)
        current = Company.objects.values().get(pk=self.old.pk)
        for field in old_values:
            if field not in {"version", "updated_at", "updated_by_id"}:
                self.assertEqual(current[field], old_values[field], field)
        self.assertEqual(CompanyPerson.objects.values().get(pk=self.person.pk), person)
        self.assertEqual(CompanyQualification.objects.values().get(pk=self.old_qual.pk), qualification)
        with self.assertRaises(BaichuanError) as raised:
            save_company(self.actor, payload, self.old.pk)
        self.assertEqual(raised.exception.code, "version_conflict")
        self.assertEqual(Company.objects.count(), 4)
        self.assertEqual(CompanyQualification.objects.count(), 8)
        self.assertEqual(AuditEvent.objects.filter(action="baichuan_national_import").count(), 1)
        self.assertFalse(Company.objects.exclude(pk=self.old.pk).exclude(phone=None).exists())

    def test_exact_replay_and_fresh_preview_make_zero_writes(self):
        manifest = self.manifest()
        apply_catalog(self.path, manifest, self.actor)
        for reviewed in (manifest, self.manifest()):
            with CaptureQueriesContext(connection) as queries:
                result = apply_catalog(self.path, reviewed, self.actor)
            self.assertTrue(result["replayed"])
            self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.old.refresh_from_db()
        self.assertEqual(self.old.version, 2)

    def test_changed_input_is_rejected(self):
        manifest = self.manifest()
        rows = copy.deepcopy(self.rows)
        rows[0][0][6] = "变更"
        workbook(self.path, rows)
        with self.assertRaisesMessage(BaichuanError, "原文件"):
            apply_catalog(self.path, manifest, self.actor)
        self.assertEqual(Company.objects.count(), 1)

    def test_target_company_qualification_and_person_changes_reject(self):
        for model, item, values in ((Company, self.old, {"phone": "changed"}),
                                    (CompanyQualification, self.old_qual, {"source": "changed"}),
                                    (CompanyPerson, self.person, {"name": "changed"})):
            manifest = self.manifest()
            model.objects.filter(pk=item.pk).update(**values)
            with self.assertRaisesMessage(BaichuanError, "目标资料"):
                apply_catalog(self.path, manifest, self.actor)
        self.assertEqual(Company.objects.count(), 1)

    def test_failed_audit_rolls_back_all_new_rows_and_version(self):
        rows = copy.deepcopy(self.rows)
        rows[3].append(["2", "旧公司", "陕西", "安全运维服务（等级未公示）", "", "", "补录", "名录", "https://example.org/outside", "2026-10-19"])
        workbook(self.path, rows)
        manifest = self.manifest()
        self.assertEqual(manifest["counts"]["source_updates"], 1)
        with patch("portal.baichuan_national_import.AuditEvent.objects.create", side_effect=IntegrityError("injected")):
            with self.assertRaises(IntegrityError):
                apply_catalog(self.path, manifest, self.actor)
        self.old.refresh_from_db()
        self.assertEqual(self.old.version, 1)
        self.assertEqual(self.old.source, "人工成果")
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(CompanyQualification.objects.count(), 1)

    def test_conflicting_states_and_ambiguous_names_reject_whole_batch(self):
        for status in ("UNKNOWN", "ABSENT"):
            conflict = CompanyQualification.objects.create(company=self.old, category="electronic", status=status)
            with self.assertRaisesMessage(BaichuanError, "UNKNOWN或ABSENT"):
                preview_catalog(self.path)
            conflict.delete()
        Company.objects.create(name="旧 公 司", created_by=self.actor, updated_by=self.actor)
        with self.assertRaisesMessage(BaichuanError, "多个现有企业"):
            preview_catalog(self.path)

    def test_unconfirmed_tampered_and_unauthorized_requests_reject(self):
        manifest = preview_catalog(self.path)
        with self.assertRaisesMessage(BaichuanError, "确认"):
            apply_catalog(self.path, manifest, self.actor)
        manifest["confirmed"] = True
        altered = copy.deepcopy(manifest)
        altered["counts"]["new_companies"] += 1
        with self.assertRaisesMessage(BaichuanError, "摘要"):
            apply_catalog(self.path, altered, self.actor)
        with self.settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[]):
            with self.assertRaises(BaichuanError):
                apply_catalog(self.path, manifest, self.actor)
        for field in ("must_change_password", "is_active"):
            original = getattr(self.actor, field)
            setattr(self.actor, field, not original)
            self.actor.save()
            with self.assertRaises(BaichuanError):
                apply_catalog(self.path, manifest, self.actor)
            setattr(self.actor, field, original)
            self.actor.save()
        self.assertEqual(Company.objects.count(), 1)

    def test_formula_and_unexpected_header_reject(self):
        workbook(self.path, formula=True)
        with self.assertRaisesMessage(ValueError, "公式"):
            read_catalog(self.path)
        workbook(self.path, bad_header=True)
        with self.assertRaisesMessage(ValueError, "表头"):
            read_catalog(self.path)

    def test_cmmi_assessment_id_and_scope_are_conservative(self):
        rows = copy.deepcopy(self.rows)
        rows[2][0][5] = "ID:78641"
        workbook(self.path, rows)
        row = read_catalog(self.path)["rows"][2]
        self.assertIsNone(row["qualification"]["certificate_no"])
        self.assertEqual(row["source"]["raw"]["证书编号/统一社会信用代码"], "ID:78641")
        rows[2][0][5] = "78641"
        workbook(self.path, rows)
        self.assertEqual(read_catalog(self.path)["rows"][2]["qualification"]["certificate_no"], "78641")
        rows[3][0][4] = "安全运维"
        rows[3][0][5] = "CCRC-2026-ISV-SO-01"
        workbook(self.path, rows)
        with self.assertRaisesMessage(ValueError, "范围不明确"):
            read_catalog(self.path)

    def test_revoked_during_parsing_is_rechecked_inside_transaction(self):
        manifest = self.manifest()
        original = read_catalog

        def revoke(path):
            parsed = original(path)
            type(self.actor).objects.filter(pk=self.actor.pk).update(is_active=False)
            return parsed

        with patch("portal.baichuan_national_import.read_catalog", side_effect=revoke):
            with self.assertRaises(BaichuanError):
                apply_catalog(self.path, manifest, self.actor)
        self.assertEqual(Company.objects.count(), 1)

    def test_outside_scope_rows_append_source_keep_original_prefix_and_replay_without_writes(self):
        rows = copy.deepcopy(self.rows)
        rows[3].append(["2", "旧公司", "陕西", "安全运维服务（等级未公示）", "", "", "本地核验补录", "名录", "https://example.org/outside", "2026-10-19"])
        rows[4].append(["2", "通用公司", "深圳", "通用要求", "", "", "补录", "", "名录", "https://example.org/general", "2026-10-19"])
        workbook(self.path, rows)
        manifest = self.manifest()
        self.assertEqual(manifest["counts"]["source_only_rows"], 2)
        self.assertEqual(manifest["counts"]["source_updates"], 1)
        result = apply_catalog(self.path, manifest, self.actor)
        self.assertEqual(len(result["source_only_links"]), 2)
        self.assertTrue(all(row["stored_in"] == "company.source" for row in result["source_only_links"]))
        self.old.refresh_from_db()
        self.assertTrue(self.old.source.startswith("人工成果\n\n"))
        self.assertIn("安全运维服务（等级未公示）", self.old.source)
        self.assertIn('"row":6', self.old.source)
        self.assertEqual(self.old.version, 2)
        self.assertFalse(self.old.qualifications.filter(category="ccrc").exists())
        general = Company.objects.get(name="通用公司")
        self.assertIn("通用要求", general.source)
        self.assertFalse(general.qualifications.exists())
        source = self.old.source
        for reviewed in (manifest, self.manifest()):
            with CaptureQueriesContext(connection) as queries:
                replay = apply_catalog(self.path, reviewed, self.actor)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["counts"]["source_updates"], 0)
            self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.old.refresh_from_db()
        self.assertEqual(self.old.source, source)
        self.assertEqual(self.old.version, 2)

    def test_only_source_append_to_existing_company_also_updates_version(self):
        general = Company.objects.create(name="通用公司", source="原通用公司来源", phone="010-87654321", created_by=self.actor, updated_by=self.actor)
        rows = copy.deepcopy(self.rows)
        rows[4].append(["2", "通用公司", "深圳", "通用要求", "", "", "补录", "", "名录", "https://example.org/general", "2026-10-19"])
        workbook(self.path, rows)
        manifest = self.manifest()
        self.assertEqual(manifest["counts"]["version_updates"], 2)
        apply_catalog(self.path, manifest, self.actor)
        general.refresh_from_db()
        self.assertTrue(general.source.startswith("原通用公司来源\n\n"))
        self.assertIn("通用要求", general.source)
        self.assertEqual(general.phone, "010-87654321")
        self.assertEqual(general.version, 2)
        self.assertFalse(general.qualifications.exists())

    def test_manual_modification_after_import_never_gets_overwritten(self):
        manifest = self.manifest()
        apply_catalog(self.path, manifest, self.actor)
        new = Company.objects.get(name="新 公司（集团）")
        CompanyQualification.objects.filter(company=new, category="cs").update(grade="2")
        with self.assertRaises(BaichuanError):
            apply_catalog(self.path, manifest, self.actor)
        self.assertEqual(new.qualifications.get(category="cs").grade, "2")

    def test_cli_default_preview_private_report_and_path_protection(self):
        output = StringIO()
        report = self.root / "preview.json"
        call_command("import_baichuan_national", input=str(self.path), report=str(report), stdout=output)
        self.assertNotIn("旧公司", output.getvalue())
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["counts"]["source_rows"], 7)
        self.assertEqual(Company.objects.count(), 1)
        before = self.path.read_bytes()
        with self.assertRaises(CommandError):
            call_command("import_baichuan_national", input=str(self.path), report=str(self.path), stdout=StringIO())
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(CommandError):
            call_command("import_baichuan_national", input=str(self.path), report=str(report), apply=True, stdout=StringIO())
