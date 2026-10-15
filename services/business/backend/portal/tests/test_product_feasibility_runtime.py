"""Executable contracts for approved guide identity and exhaustive body evidence."""

import json
from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from portal import product_feasibility as guide
from portal.product_service import ProductError


def section(section_id, **extra):
    return {"id": section_id, "title": "指南小节", "source_text": "完整来源原文",
            "applicability": "按已确认范围适用", "content_elements": ["说明真实建设范围。"],
            "writing_requirements": [], "tables_figures": [], "public_research": ["可检索公开技术资料。"],
            "project_inputs": ["项目参数须由项目单位确认。"], **extra}


class ProductFeasibilityRuntimeTests(SimpleTestCase):
    def setUp(self):
        self.asset = {"chapters": [{"id": "1", "title": "项目概述", "sections": [section("1.1"), section("1.2")]}],
                      "appendices": [section("附件1")]}
        self.loader = patch.object(guide, "_load_guide", return_value=self.asset)
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.blueprint = {
            "missing": ["审批资料待项目单位提供。"],
            "chapters": [{"id": "edited-id", "family": "feasibility", "title": "第七章 重新命名的专业建设方案",
                          "scope": "本项目只建设道路，不含信息系统。"},
                         {"id": "technical", "family": "technical-solution", "title": "技术方案"}],
            "feasibility_guide": {"asset_sha256": guide._ASSET_SHA256, "sections": [
                {"section_id": "1.1", "status": "include", "chapter_ids": ["edited-id"], "reason": "建设范围已确认。"},
                {"section_id": "1.2", "status": "not_applicable", "chapter_ids": [], "reason": "本期无信息化建设。"},
                {"section_id": "附件1", "status": "pending", "chapter_ids": ["edited-id"], "reason": "审批资料待项目单位提供。"},
            ]},
        }
        self.chapters = [{"chapter_id": "edited-id", "title": "第七章 重新命名的专业建设方案",
                          "paragraphs": ["本项目只建设道路，不含信息系统。", "审批资料待项目单位提供，由项目负责人核对后补充。"]}]

    def requests(self, chapters=None):
        return guide.review_requests({}, self.blueprint, chapters or self.chapters)

    @staticmethod
    def response(request, status="not_seen", quote=None):
        evidence = [] if status == "not_seen" else [{"chapter_id": request["chapters"][0]["chapter_id"],
                                                     "quote": quote or request["chapters"][0]["paragraphs"][0][:1000]}]
        return {"passed": True, "issues": [], "guide_checks": [
            {"id": atom["id"], "status": status, "evidence": deepcopy(evidence), "reason": "按实际正文逐项判断。"}
            for atom in request["guide_requirements"]]}

    def test_stable_ids_survive_edited_titles_and_clipping_is_not_twelve_chapters(self):
        plan = guide.validate_plan(self.blueprint)
        self.assertEqual(plan["sections"][0]["chapter_ids"], ["edited-id"])
        chosen = guide.chapter_requirements(self.blueprint, "edited-id")
        self.assertEqual([row["id"] for row in chosen], ["1.1", "附件1"])
        self.assertNotIn("source_text", chosen[0])
        self.assertEqual(guide.validate_plan({"chapters": []}), None)
        for mutate in (lambda plan: plan["sections"].pop(),
                       lambda plan: plan["sections"].append(deepcopy(plan["sections"][0])),
                       lambda plan: plan["sections"][0].update(chapter_ids=["technical"]),
                       lambda plan: plan["sections"][1].update(reason=""),
                       lambda plan: plan.update(asset_sha256="0" * 64)):
            broken = deepcopy(self.blueprint)
            mutate(broken["feasibility_guide"])
            with self.assertRaises(ProductError):
                guide.validate_plan(broken)

    def test_direct_chapter_obligations_and_inheritance_are_not_lost(self):
        self.asset["chapters"].append({**section("6"), "sections": []})
        self.asset["chapters"][0]["sections"][1]["inherits_requirements_from"] = ["1.1"]
        headings = guide.catalog()["chapters"]
        self.assertEqual(headings[1]["sections"][0]["id"], "6")
        atoms = guide._requirements(self.asset["chapters"][0]["sections"][1],
                                    {row["id"]: row for row in guide._sections(self.asset)})
        self.assertIn("1.2:from:1.1:E1", [atom["id"] for atom in atoms])

    def test_plan_cannot_hide_all_content_unmapped_chapters_or_pending_items(self):
        broken = deepcopy(self.blueprint)
        for entry in broken["feasibility_guide"]["sections"]:
            entry.update(status="not_applicable", chapter_ids=[], reason="不适用。")
        with self.assertRaises(ProductError):
            guide.validate_plan(broken)
        broken = deepcopy(self.blueprint)
        broken["chapters"].append({"id": "unmapped", "family": "feasibility", "title": "没有指南映射的章节"})
        with self.assertRaises(ProductError):
            guide.validate_plan(broken)
        broken = deepcopy(self.blueprint)
        broken["missing"] = []
        with self.assertRaises(ProductError):
            guide.validate_plan(broken)

    def test_numbered_requirements_are_atomic_and_acquisition_guidance_is_context(self):
        self.asset["chapters"][0]["sections"][0]["content_elements"] = ["应包括：\n1．说明现状。\n2．论证必要性。"]
        self.asset["chapters"][0]["sections"][0]["other_requirements"] = ["说明前置条件。"]
        requests = self.requests()
        ids = {atom["id"] for request in requests for atom in request["guide_requirements"]}
        self.assertTrue({"1.1:E1", "1.1:E2", "1.1:O1"} <= ids)
        self.assertFalse(any(":R" in value or ":I" in value for value in ids))
        self.assertIn("project_inputs", requests[0]["guide_support_context"]["1.1"])

    def test_long_chapter_is_contiguous_bounded_and_identifies_only_global_absence(self):
        chapters = [{**self.chapters[0], "paragraphs": ["甲" * 10000, '引号"和反斜杠\\' * 300]}]
        requests = self.requests(chapters)
        self.assertGreater(len(requests), 2)
        self.assertTrue(all(guide._size(request) <= 14500 for request in requests))
        self.assertTrue(all(sum(len(text) for chapter in request["chapters"] for text in chapter["paragraphs"]) <= 7000
                            for request in requests))
        self.assertTrue(guide._complete_scan_plan(requests))
        responses = [self.response(request) for request in requests]
        partial = guide.reduce_guide_reviews(requests, responses[:-1])
        self.assertFalse(partial["complete"])
        self.assertFalse(partial["passed"])
        self.assertEqual(partial["issues"], [])
        complete = guide.reduce_guide_reviews(requests, responses)
        self.assertTrue(complete["complete"])
        self.assertFalse(complete["passed"])
        self.assertTrue(all(check["status"] == "missing" for check in complete["checks"]))
        self.assertEqual(len(complete["issues"]), 2)
        # Even apparently successful replies cannot excuse an omitted planned fragment.
        incomplete_plan = guide.reduce_guide_reviews(requests[:-1], responses[:-1])
        self.assertFalse(incomplete_plan["complete"])
        self.assertEqual(incomplete_plan["issues"], [])

    def test_exact_receipts_cover_tail_content_and_reject_fabricated_or_missing_ids(self):
        chapters = [{**self.chapters[0], "paragraphs": ["甲" * 9000, "完整的论证内容在保存正文的最后一段。"]}]
        requests = self.requests(chapters)
        responses = [self.response(request) for request in requests]
        responses[-1] = self.response(requests[-1], "covered", "完整的论证内容在保存正文的最后一段。")
        self.assertTrue(guide.reduce_guide_reviews(requests, responses)["passed"])
        broken = deepcopy(responses[-1])
        broken["guide_checks"][0]["evidence"][0]["quote"] = "模型编造的引文"
        with self.assertRaises(ProductError):
            guide.validate_guide_review(broken, requests[-1])
        broken = deepcopy(responses[-1])
        broken["guide_checks"].pop()
        with self.assertRaises(ProductError):
            guide.validate_guide_review(broken, requests[-1])
        with self.assertRaises(ProductError):
            guide.validate_guide_review({**responses[-1], "extra": True}, requests[-1])

    def test_pending_needs_real_quote_and_never_becomes_full_pass(self):
        requests = self.requests()
        responses = [self.response(request, "pending") for request in requests]
        result = guide.reduce_guide_reviews(requests, responses)
        self.assertTrue(result["complete"])
        self.assertFalse(result["passed"])
        self.assertTrue(result["pending"])
        self.assertEqual(result["issues"], [])
        responses[0]["guide_checks"][0]["evidence"] = []
        with self.assertRaises(ProductError):
            guide.validate_guide_review(responses[0], requests[0])

    def test_cross_fragment_partial_evidence_is_not_misreported_as_absence_or_completion(self):
        requests = self.requests([{**self.chapters[0], "paragraphs": ["甲" * 9000]}])
        responses = [self.response(request, "partial") for request in requests]
        result = guide.reduce_guide_reviews(requests, responses)
        self.assertTrue(result["complete"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["issues"], [])
        self.assertTrue(all(check["status"] == "partial" for check in result["checks"]))

    def test_conditional_not_applicable_requires_approved_reason_and_body_scope(self):
        self.asset["chapters"][0]["sections"][0]["content_elements"] = []
        self.asset["chapters"][0]["sections"][0]["calculations"] = [{"requirement": "迁移容量测算", "conditions": "涉及数据迁移时"}]
        requests = self.requests()
        response = self.response(requests[0])
        conditional = next(check for check in response["guide_checks"] if check["id"] == "1.1:C1")
        conditional.update(status="not_applicable", reason="批准范围无信息系统和数据迁移。",
                           evidence=[{"chapter_id": "edited-id", "quote": "不含信息系统"}])
        guide.validate_guide_review(response, requests[0])
        request = deepcopy(requests[0])
        request["guide_dispositions"]["1.1"]["reason"] = ""
        with self.assertRaises(ProductError):
            guide.validate_guide_review(response, request)
        nonconditional = next(check for check in response["guide_checks"] if check["id"] != "1.1:C1")
        nonconditional.update(status="not_applicable", evidence=deepcopy(conditional["evidence"]))
        with self.assertRaises(ProductError):
            guide.validate_guide_review(response, requests[0])


class ProductFeasibilityBundledAssetTests(SimpleTestCase):
    def test_bundled_asset_is_valid_and_grouped_planning_stays_within_call_budget(self):
        catalog = guide.catalog()
        chapters = [{"id": f"feas-{chapter['id']}", "family": "feasibility", "title": chapter["title"],
                     "scope": "按已确认建设范围编写；示例不作项目事实。"} for chapter in catalog["chapters"]]
        dispositions = [{"section_id": section["id"], "status": "include", "chapter_ids": [f"feas-{chapter['id']}"],
                         "reason": "本期相关建设内容按指南适用；示例名称和数字须以项目资料替换。"}
                        for chapter in catalog["chapters"] for section in chapter["sections"]]
        dispositions.extend({"section_id": section["id"], "status": "include", "chapter_ids": ["feas-11"],
                             "reason": "附录按本期项目资料适用。"} for section in catalog["appendices"])
        blueprint = {"chapters": chapters, "feasibility_guide": {"asset_sha256": guide.asset_hash(), "sections": dispositions}}
        body = [{"chapter_id": chapter["id"], "title": chapter["title"], "paragraphs": ["实际保存正文。" * 1000]}
                for chapter in chapters]
        requests = guide.review_requests({}, blueprint, body)
        self.assertTrue(guide._complete_scan_plan(requests))
        self.assertLessEqual(len(requests), 110)
        self.assertTrue(all(guide._size(request) <= 14500 for request in requests))
        obligation_ids = {atom["id"] for request in requests for atom in request["guide_requirements"]}
        self.assertTrue(any(value.startswith("6:") for value in obligation_ids))
        self.assertTrue(any(value.startswith("8:") for value in obligation_ids))
        self.assertTrue(any(value.startswith("12:") for value in obligation_ids))
        self.assertTrue(any(value.startswith("4.1.2:from:4.1.1:") for value in obligation_ids))
