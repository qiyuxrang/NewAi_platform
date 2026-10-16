"""Offline writing-plan checks: no models, services, or database required."""

from copy import deepcopy
from unittest import TestCase

from portal.product_writing_plan import _validate_plan, build_writing_plan


def chapter(chapter_id, title, family="technical-solution"):
    return {"id": chapter_id, "family": family, "title": title, "scope": "只写批准范围",
            "source_ids": ["approved-source"]}


class WritingPlanTests(TestCase):
    def setUp(self):
        self.blueprint = {"purpose": "批准用途", "audience": "批准读者",
                          "conditions": [{"text": "预算待确认", "type": "human"}],
                          "missing": ["现状证据缺项"], "conflicts": ["口径待确认"],
                          "chapters": [chapter("needs", "第二章 现状与需求分析"),
                                       chapter("design", "第五章 总体架构及技术路线"),
                                       chapter("ops", "第九章 运维保障"),
                                       chapter("background", "一、建设背景及必要性", "feasibility"),
                                       chapter("construction", "四、项目建设方案", "feasibility"),
                                       chapter("cost", "八、投资概算与资金筹措", "feasibility"),
                                       chapter("benefit", "九、经济效益评价", "feasibility")]}

    def test_both_families_keep_approved_directory_and_independent_chapters(self):
        jobs = build_writing_plan(self.blueprint, ["technical-solution", "feasibility"])
        self.assertEqual({job["family"] for job in jobs}, {"technical-solution", "feasibility"})
        by_id = {job["chapter_id"]: job for job in jobs}
        self.assertEqual({job["chapter_id"] for job in jobs if not job["depends_on"]},
                         {"needs", "ops", "background"})
        self.assertEqual(by_id["design"]["depends_on"], ["needs"])
        self.assertEqual(by_id["construction"]["depends_on"], ["background"])
        for job in jobs:
            brief = job["brief"]
            self.assertEqual(brief["chapters"], self.blueprint["chapters"])
            self.assertEqual(brief["chapter"], next(c for c in self.blueprint["chapters"]
                                                    if c["id"] == job["chapter_id"]))
            for field in ("purpose", "audience", "conditions", "missing", "conflicts"):
                self.assertEqual(brief[field], self.blueprint[field])
            self.assertTrue(brief["constraints"])

    def test_estimates_and_benefits_wait_for_selected_design_conclusions(self):
        jobs = build_writing_plan(self.blueprint, ["technical-solution", "feasibility"])
        for job in jobs:
            if job["chapter_id"] in {"cost", "benefit"}:
                self.assertEqual(job["depends_on"], ["design", "construction"])

    def test_single_family_and_missing_predecessors_are_executable(self):
        jobs = build_writing_plan(self.blueprint, ["feasibility"])
        self.assertEqual(next(job for job in jobs if job["chapter_id"] == "cost")["depends_on"],
                         ["construction"])
        only_cost = deepcopy(self.blueprint)
        only_cost["chapters"] = [chapter("unknown-id", "费用估算", "feasibility")]
        self.assertEqual(build_writing_plan(only_cost, ["feasibility"])[0]["depends_on"], [])

    def test_legacy_blueprint_remains_shared_between_families(self):
        legacy = deepcopy(self.blueprint)
        legacy["chapters"] = [chapter("basis", "项目需求"), chapter("plan", "建设方案")]
        for item in legacy["chapters"]:
            del item["family"]
        jobs = build_writing_plan(legacy, ["technical-solution", "feasibility"])
        self.assertEqual(len(jobs), 4)
        self.assertEqual([job["depends_on"] for job in jobs], [[], ["basis"], [], ["basis"]])

    def test_blueprint_is_unchanged_and_briefs_do_not_share_mutable_content(self):
        before = deepcopy(self.blueprint)
        jobs = build_writing_plan(self.blueprint, ["technical-solution", "feasibility"])
        self.assertEqual(self.blueprint, before)
        jobs[0]["brief"]["chapter"]["source_ids"].append("unapproved")
        jobs[0]["brief"]["chapters"].clear()
        jobs[0]["brief"]["conditions"].clear()
        self.assertEqual(self.blueprint, before)
        self.assertEqual(jobs[1]["brief"]["chapters"], before["chapters"])

    def test_duplicate_approved_id_is_rejected_even_across_families(self):
        self.blueprint["chapters"][-1]["id"] = "needs"
        with self.assertRaises(ValueError):
            build_writing_plan(self.blueprint, ["technical-solution", "feasibility"])

    def test_invalid_graphs_are_rejected(self):
        for pairs in ([('a', ['a'])], [('a', ['b']), ('b', ['a'])], [('a', ['missing'])],
                      [('a', []), ('a', [])]):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                _validate_plan([{"family": "feasibility", "chapter_id": chapter_id,
                                 "depends_on": dependencies} for chapter_id, dependencies in pairs])

    def test_design_words_in_unrelated_scopes_do_not_serialize_every_chapter(self):
        self.blueprint["chapters"][2]["scope"] = "说明运维职责，引用总体架构和投资数据，不重写设计"
        jobs = build_writing_plan(self.blueprint, ["technical-solution"])
        self.assertEqual(next(job for job in jobs if job["chapter_id"] == "ops")["depends_on"], [])

    def test_design_title_variants_and_basis_wording(self):
        for title in ("整体技术路线", "专业建设方案", "网络与安全设计", "工程方案与设备选型"):
            with self.subTest(title=title):
                self.blueprint["chapters"][1]["title"] = title
                jobs = build_writing_plan(self.blueprint, ["technical-solution", "feasibility"])
                self.assertEqual(next(job for job in jobs if job["chapter_id"] == "design")["depends_on"],
                                 ["needs"])
                self.assertIn("design", next(job for job in jobs if job["chapter_id"] == "cost")["depends_on"])
        self.blueprint["chapters"][1]["title"] = "设计依据与设计原则"
        jobs = build_writing_plan(self.blueprint, ["technical-solution"])
        self.assertEqual(next(job for job in jobs if job["chapter_id"] == "design")["depends_on"], [])
