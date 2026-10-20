"""Synthetic source-normalization tests; no Django or database setup."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from portal.baichuan_source import COMPANY_COLUMNS, convert_source
from portal.baichuan_source_workbook import (CATEGORY_NAMES, CATEGORIES, DETAIL_HEADERS,
    SUMMARY_HEADERS, explicit_grade, main, normalize_workbook, normalized_name)


def workbook(path, records, *, extra_detail=None, formula=False, hidden=False):
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    root = ET.Element("workbook", xmlns=namespace)
    sheets = ET.SubElement(root, "sheets")
    relations = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    with ZipFile(path, "w") as archive:
        for index in range(8):
            name = f"{index}-合成来源"
            ET.SubElement(sheets, "sheet", name=name, sheetId=str(index + 1), state="hidden" if hidden and index == 7 else "visible",
                          attrib={f"{{{relationship}}}id": f"r{index}"})
            ET.SubElement(relations, "Relationship", Id=f"r{index}", Target=f"worksheets/sheet{index}.xml")
            sheet = ET.Element("worksheet", xmlns=namespace)
            data = ET.SubElement(sheet, "sheetData")
            headers = SUMMARY_HEADERS if index == 0 else DETAIL_HEADERS
            selected = records if index == 0 else [row for row in records if row[0] == CATEGORIES[index - 1]]
            if extra_detail and index == 1:
                selected = [*selected, extra_detail]
            values = [["合成容量标题"], list(headers)]
            for number, (category, name, grade, region, city, phone) in enumerate(selected, 1):
                values.append([str(number), region, CATEGORY_NAMES[CATEGORIES.index(category)], name, grade, city, phone]
                              if index == 0 else [str(number), region, name, grade, city, phone])
            for number, row_values in enumerate(values, 1):
                row = ET.SubElement(data, "row", r=str(number))
                for column, value in zip("ABCDEFG", row_values):
                    cell = ET.SubElement(row, "c", r=f"{column}{number}", t="inlineStr")
                    ET.SubElement(ET.SubElement(cell, "is"), "t").text = value
                    if formula and number == 3 and column == "A":
                        ET.SubElement(cell, "f").text = "1+1"
            archive.writestr(f"xl/worksheets/sheet{index}.xml", ET.tostring(sheet))
        archive.writestr("xl/workbook.xml", ET.tostring(root))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(relations))


class SourceWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "original.xlsx"
        self.records = [
            ("electronic", "合成 企业（集团）", "一级", "陕西省", "西安", "029-12345678"),
            ("itss", "合成企业(集团)", "三级（拓展级）", "陕西省", "西安", "未找到公开专线（总机10010转）"),
            ("labor", "合成近似企业", "AAA", "榆林市", "榆阳区小纪汉乡", "未标注"),
            ("ccrc", "合成安全企业", "安全运维服务（等级未公示）", "陕西省", "未标注", ""),
            ("security", "合成安全企业", "二级（全国一级）", "陕西省", "陕西省", ""),
            ("ccrc", "合成集成企业", "信息系统安全集成二级/安全运维一级", "榆林市", "未标注", ""),
            ("cs", "合成其他企业", "CS1级（初始级）", "陕西省", "高新区", ""),
            ("cmmi", "合成其他企业", "ML5（优化级）", "陕西省", "(未细化)", ""),
        ]
        workbook(self.path, self.records)

    def test_views_count_once_and_full_raw_values_and_both_locators_survive(self):
        before = self.path.read_bytes()
        companies, claims, facts, audit = normalize_workbook(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(audit["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertTrue(audit["multiset_verified"])
        self.assertEqual((len(claims), len(companies), len(facts)), (8, 5, 0))
        self.assertEqual(len(audit["normalization_groups"]), 1)
        first = companies[0]
        self.assertEqual(first["original_names"], ["合成 企业（集团）", "合成企业(集团)"])
        self.assertIn("未找到公开专线（总机10010转）", first["phones"])
        self.assertEqual(first["phone_candidates"], ["029-12345678"])
        self.assertFalse(first["phone_missing"])
        self.assertFalse(first["identity_verified"])
        self.assertEqual(first["source_rows"][0]["summary"]["cells"]["D3"], self.records[0][1])
        self.assertEqual(claims[0]["source_rows"]["detail"]["cells"]["C3"], self.records[0][1])
        self.assertEqual(claims[4]["raw_grade"], "二级（全国一级）")
        self.assertIsNone(claims[4]["proposed_grade"])
        self.assertEqual(normalize_workbook(self.path), (companies, claims, facts, audit))

    def test_names_do_not_use_fuzzy_suffix_case_or_punctuation_merging(self):
        self.assertEqual(normalized_name(" 合 成（公司）\n"), "合成(公司)")
        for a, b in (("ABC公司", "abc公司"), ("合成公司", "合成集团公司"), ("合成-公司", "合成公司")):
            self.assertNotEqual(normalized_name(a), normalized_name(b))

    def test_multiset_duplicate_multiplicity_mismatch_fails_without_outputs(self):
        workbook(self.path, self.records, extra_detail=self.records[0])
        with self.assertRaisesRegex(ValueError, "extra rows or multiplicities"):
            normalize_workbook(self.path)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_identical_repeated_claims_are_retained_not_collapsed(self):
        workbook(self.path, [*self.records, self.records[0]])
        _, claims, _, audit = normalize_workbook(self.path)
        self.assertEqual(audit["source_record_count"], 9)
        self.assertEqual(sum(claim["category"] == "electronic" for claim in claims), 2)
        self.assertNotEqual(claims[0]["source_row"], claims[-1]["source_row"])

    def test_explicit_grades_conflicts_and_scope(self):
        for category, raw, grade in (("labor", "AAA", None), ("itss", "通用要求", None),
            ("security", "贰级", "2"), ("security", "二级（全国一级）", None),
            ("electronic", "一级或二级", None), ("cmmi", "ML3（定义级）", "3"),
            ("cmmi", "ML3/ML5", None), ("cs", "CS1级（初始级）", "1"),
            ("ccrc", "安全运维二级", None), ("ccrc", "安全集成一级/安全集成二级", None)):
            with self.subTest(category=category, raw=raw):
                self.assertEqual(explicit_grade(category, raw)[0], grade)

    def test_explicit_geography_phone_and_unverified_conversion_compatible(self):
        normalized = normalize_workbook(self.path)
        rows, mapping, report = convert_source(*normalized)
        by_name = {row[0]: dict(zip(COMPANY_COLUMNS.values(), row)) for row in rows["sheets"][0]["rows"]}
        first = by_name["合成企业(集团)"]
        self.assertEqual((first["province"], first["city"], first["phone"]), ("陕西省", "西安", "029-12345678"))
        self.assertNotIn("10010", first["phone"])
        self.assertIn("总机10010转", first["source"])
        second = by_name["合成近似企业"]
        self.assertEqual((second["province"], second["city"]), (None, "榆林市"))
        self.assertIn("榆阳区小纪汉乡", second["source"])
        self.assertIsNone(by_name["合成其他企业"]["city"])
        self.assertTrue(all(row["verified_on"] is None for quals in mapping["qualification_overrides"].values() for row in quals))
        self.assertEqual(report["credit_codes_assigned"], 0)
        self.assertEqual(report["counts"]["source_facts"], 0)

    def test_legacy_converter_without_explicit_keys_keeps_prior_behavior(self):
        companies = [{"id": "old", "name": "合成旧契约", "regions": ["原地区"], "phones": ["029-12345678"]}]
        rows, _, _ = convert_source(companies, [], [], {})
        row = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][0]))
        self.assertEqual(row["city"], "原地区")
        self.assertEqual(row["phone"], "029-12345678")

    def test_converter_does_not_reinfer_first_cs_or_ccrc_grade_from_conflicting_source(self):
        records = list(self.records)
        records[5] = ("ccrc", "合成集成企业", "安全集成一级/安全集成二级", "榆林市", "未标注", "")
        records[6] = ("cs", "合成其他企业", "CS1级/CS2级", "陕西省", "高新区", "")
        workbook(self.path, records)
        normalized = normalize_workbook(self.path)
        self.assertIsNone(normalized[1][5]["proposed_grade"])
        self.assertIsNone(normalized[1][6]["proposed_grade"])
        _, mapping, _ = convert_source(*normalized)
        grades = [qualification["grade"] for items in mapping["qualification_overrides"].values()
                  for qualification in items if qualification["category"] in {"ccrc", "cs"}]
        self.assertEqual(grades, [None, None])

    def test_formula_and_hidden_source_fail_closed(self):
        for settings in ({"formula": True}, {"hidden": True}):
            with self.subTest(settings=settings):
                workbook(self.path, self.records, **settings)
                with self.assertRaises(ValueError):
                    normalize_workbook(self.path)

    def test_cli_creates_only_fresh_json_outputs_and_preserves_input(self):
        before = self.path.read_bytes()
        output = self.root / "normalized"
        arguments = ["normalize", "--input", str(self.path), "--output-dir", str(output)]
        with patch("sys.argv", arguments), patch("builtins.print"):
            main()
        self.assertEqual(set(path.name for path in output.iterdir()), {"companies.json", "claims.json", "facts.json", "audit.json"})
        self.assertEqual(json.loads((output / "facts.json").read_text(encoding="utf-8")), [])
        self.assertEqual(self.path.read_bytes(), before)
        with patch("sys.argv", arguments), self.assertRaises(ValueError):
            main()
        with patch("sys.argv", ["normalize", "--input", str(self.path), "--output-dir", str(self.root)]), self.assertRaises(ValueError):
            main()
