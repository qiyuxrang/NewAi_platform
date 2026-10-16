"""Pure conversion checks with synthetic input; no Django/database setup."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from portal.baichuan_source import (COMPANY_COLUMNS, PERSON_COLUMNS, convert_source,
                                    prepare_source)


class BaichuanSourceTests(unittest.TestCase):
    def setUp(self):
        self.companies = [{"id": "TEST1", "name": "测试企业一", "regions": ["榆林市"], "phones": ["029-12345678"], "phone_missing": False},
                          {"id": "TEST2", "name": "测试企业二", "regions": [], "phones": ["未找到公开专线（总机10010转）"], "phone_missing": True}]
        self.claims = [self.claim("cs", "CS1级"), self.claim("itss", "通用要求"),
                       self.claim("labor", "AAA"), self.claim("ccrc", "信息安全服务资质（等级未公示）"),
                       self.claim("ccrc", "信息系统安全集成二级/安全运维二级", "2"),
                       self.claim("electronic", "一级", "1"), self.claim("electronic", "二级", "2")]
        self.facts = [{"company_id": "TEST1", "kind": "person", "value": "陈工", "role": "项目联系人",
                       "source_url": "https://example.com/project", "source_date": "2020-01-02", "verification": "search_snippet", "evidence_id": "E1"},
                      {"company_id": "TEST2", "kind": "phone", "value": "13900000001", "source_kind": "official", "role": "2018年招聘联系电话"},
                      {"company_id": "TEST2", "kind": "phone", "value": "029-87654321", "source_kind": "official", "role": "官网公开联系电话"},
                      {"company_id": "TEST2", "kind": "website", "value": "https://example.com/", "source_kind": "official"}]

    def claim(self, category, raw, proposed=None):
        return {"company_id": "TEST1", "category": category, "raw_category": category,
                "raw_grade": raw, "proposed_grade": proposed, "source_sheet": "源表", "source_row": len(raw)}

    def convert(self, companies=None, claims=None, facts=None, audit=None):
        return convert_source(companies if companies is not None else self.companies,
                              claims if claims is not None else self.claims,
                              facts if facts is not None else self.facts, audit or {})

    def test_all_claims_visible_and_unknown_scope_excluded(self):
        rows, mapping, report = self.convert()
        first = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][0]))
        self.assertEqual(report["counts"]["source_claims"], 7)
        self.assertEqual(report["counts"]["qualifications"], 6)
        for claim in self.claims:
            self.assertIn(claim["raw_grade"], first["description"])
        quals = mapping["qualification_overrides"]["企业资料:2"]
        self.assertEqual([(q["grade"], q["status"]) for q in quals if q["category"] == "cs"], [("1", "PRESENT")])
        self.assertEqual([q["grade"] for q in quals if q["category"] == "ccrc"], ["2"])
        self.assertEqual([q["grade"] for q in quals if q["category"] in {"itss", "labor"}], [None, None])
        self.assertEqual([q["grade"] for q in quals if q["category"] == "electronic"], ["1", "2"])
        self.assertTrue(all(q["verified_on"] is None for q in quals))
        self.assertEqual(mapping["notes_reviewed"], {})
        self.assertFalse(report["confirmed"])

    def test_fact_provenance_and_explicit_people_link_no_phone_inference(self):
        rows, mapping, report = self.convert()
        first = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][0]))
        second = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][1]))
        person = dict(zip(PERSON_COLUMNS.values(), rows["sheets"][1]["rows"][0]))
        self.assertIn("https://example.com/project", first["source"])
        self.assertIn("2020-01-02", first["source"])
        self.assertIn("search_snippet", first["source"])
        self.assertIn("搜索摘要", first["source"])
        self.assertIn("来源网址：", first["source"])
        self.assertIn("原表全部电话及说明", first["source"])
        self.assertNotIn('"verification":', first["source"])
        self.assertIn("非完整具名核心人员", person["position"])
        self.assertIsNone(person["verified_on"])
        self.assertIsNone(first["credit_code"])
        self.assertIsNone(first["contact_phone"])
        self.assertEqual(second["phone"], "029-87654321")
        self.assertNotIn("13900000001", second["phone"])
        self.assertNotIn("10010", second["phone"])
        self.assertIn("13900000001", second["source"])
        self.assertEqual(mapping["people_links"], {"核心人员:2": "企业资料:2"})
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["source_facts"], self.facts)
        self.assertEqual(report["source_claims"], self.claims)

    def test_phone_truncation_preserves_whole_numbers_and_full_source(self):
        companies = copy.deepcopy(self.companies)
        phones = ["139" + str(number).zfill(8) for number in range(12)]
        companies[0]["phones"] = [" / ".join(phones)]
        rows, _, report = self.convert(companies=companies)
        company = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][0]))
        self.assertLessEqual(len(company["phone"]), 100)
        self.assertTrue(all(phone in phones for phone in company["phone"].split("；")))
        self.assertTrue(report["phone_overflow"])
        for phone in phones:
            self.assertIn(phone, company["source"])

    def test_only_explicit_official_homepage_and_no_candidate_means_empty(self):
        for kind, value in (("third_party", "https://example.com/"), ("official", "https://example.com/parent/profile")):
            rows, _, _ = self.convert(facts=[{"company_id": "TEST2", "kind": "website", "value": value, "source_kind": kind}])
            company = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][1]))
            self.assertIsNone(company["website"])
            self.assertIsNone(company["phone"])

    def test_reject_orphans_duplicates_oversize_and_count_drift(self):
        variants = [(self.companies + [self.companies[0]], self.claims, self.facts, {}),
                    (self.companies, self.claims, [{"company_id": "MISSING"}], {}),
                    (self.companies, self.claims, self.facts, {"source_record_count": 999}),
                    (self.companies, self.claims, [{"company_id": "TEST1", "kind": "note", "value": "长" * 20000}], {})]
        for inputs in variants:
            with self.subTest(inputs=inputs[-1]), self.assertRaises(ValueError):
                convert_source(*inputs)

    def test_scope_grade_official_subject_and_malformed_homepage_boundaries(self):
        claims = [self.claim("ccrc", "信息系统安全集成等级未公示；安全运维一级", "1")]
        for url in ("https://example.com:invalid/", "https://example.com:70000/", "https://[invalid/"):
            with self.subTest(url=url):
                facts = [{"company_id": "TEST1", "kind": "website", "value": url, "source_kind": "official"}]
                rows, mapping, _ = self.convert(claims=claims, facts=facts)
                company = dict(zip(COMPANY_COLUMNS.values(), rows["sheets"][0]["rows"][0]))
                self.assertIsNone(company["website"])
                self.assertIn(url, company["source"])
                self.assertIn("官方公开资料（主体见来源网址）", company["source"])
                self.assertNotIn("企业官方", company["source"])
                qualification = mapping["qualification_overrides"]["企业资料:2"][0]
                self.assertEqual(qualification["status"], "PRESENT")
                self.assertIsNone(qualification["grade"])
                self.assertIn("安全运维一级", qualification["source"])

    def test_prepare_requires_fresh_outputs_and_preserves_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = [root / name for name in ("companies.json", "claims.json", "facts.json", "audit.json")]
            for path, value in zip(files, (self.companies, self.claims, self.facts, {})):
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            before = [path.read_bytes() for path in files]
            report = prepare_source(*files, root / "converted")
            self.assertEqual(report["counts"]["companies"], 2)
            self.assertEqual(len(report["input_sha256"]), 4)
            with self.assertRaises(ValueError):
                prepare_source(*files, root / "converted")
            self.assertEqual(before, [path.read_bytes() for path in files])
