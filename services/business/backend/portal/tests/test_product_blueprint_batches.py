"""Offline bounded-output contracts; no worker, network, model, or database calls."""

from copy import deepcopy
import json

from django.test import SimpleTestCase

from portal import product_feasibility as guide
from portal.product_blueprint_batches import (
    compact_batches, compact_scope_request, merge_scope_batches, scope_batches,
    validate_compact_scope, validate_scope_batch,
)
from portal.product_service import ProductError


class BlueprintScopeBatchTests(SimpleTestCase):
    def setUp(self):
        self.catalog = guide.catalog()
        self.batches = scope_batches(self.catalog)
        self.base = {"purpose": "建设论证", "audience": "项目负责人", "conditions": [],
                     "missing": ["现场资料待提供。"], "conflicts": [], "template_version": "frozen-original-v1",
                     "chapters": [
                         {"id": "T1", "family": "technical-solution", "title": "技术路线", "scope": "技术范围", "source_ids": []},
                         {"id": "F1", "family": "feasibility", "title": "建设必要性论证", "scope": "项目范围", "source_ids": []},
                     ]}
        self.results = [{"sections": [
            {"section_id": section["id"], "status": "include", "chapter_ids": ["F1"], "reason": "本用例明确保留。"}
            for section in batch["sections"]], "missing": [], "conflicts": []} for batch in self.batches]

    def test_real_catalog_has_124_items_in_22_bounded_owned_batches(self):
        expected = [section for chapter in self.catalog["chapters"] for section in chapter["sections"]]
        expected.extend(self.catalog["appendices"])
        flattened = [section for batch in self.batches for section in batch["sections"]]
        self.assertEqual((len(self.batches), len(flattened)), (22, 124))
        self.assertEqual(flattened, expected)
        self.assertEqual(len({section["id"] for section in flattened}), 124)
        self.assertTrue(all(1 <= len(batch["sections"]) <= 8 for batch in self.batches))
        self.assertEqual(self.batches[-1]["kind"], "appendices")
        self.assertEqual(self.batches[-1]["sections"], self.catalog["appendices"])
        for batch in self.batches[:-1]:
            chapter = next(chapter for chapter in self.catalog["chapters"] if chapter["id"] == batch["chapter_id"])
            self.assertEqual(batch["chapter_title"], chapter["title"])
            self.assertTrue(all(section in chapter["sections"] for section in batch["sections"]))
        for bound in (0, 9, True, "8"):
            with self.subTest(bound=bound), self.assertRaises(ProductError):
                scope_batches(self.catalog, bound)

    def test_rejects_unknown_fields_out_of_batch_ids_and_invalid_decisions(self):
        mutations = [
            lambda value: value.update(chapters=[]),
            lambda value: value["sections"].pop(),
            lambda value: value["sections"].append(deepcopy(value["sections"][0])),
            lambda value: value["sections"][0].update(section_id="12"),
            lambda value: value["sections"][0].update(title="伪造字段"),
            lambda value: value["sections"][0].update(status="covered"),
            lambda value: value["sections"][0].update(status=[]),
            lambda value: value["sections"][0].update(chapter_ids=["T1"]),
            lambda value: value["sections"][0].update(chapter_ids=["F1", "F1"]),
            lambda value: value["sections"][0].update(chapter_ids=[]),
            lambda value: value["sections"][0].update(status="not_applicable", reason=""),
            lambda value: value["sections"][0].update(status="not_applicable", reason="有理由但仍映射章节"),
            lambda value: value["sections"][0].update(status="pending", reason=" "),
            lambda value: value["sections"][0].update(reason="长" * 161),
            lambda value: value.update(missing=["长" * 201]),
            lambda value: value.update(conflicts=["冲突"] * 9),
            lambda value: value.update(missing=[None]),
        ]
        for index, mutate in enumerate(mutations):
            broken = deepcopy(self.results[0])
            mutate(broken)
            with self.subTest(case=index), self.assertRaises(ProductError):
                validate_scope_batch(broken, self.batches[0], self.base)
        valid = deepcopy(self.results[0])
        valid["sections"][0].update(status="not_applicable", chapter_ids=[], reason="本期明确不建设此项。")
        self.assertEqual(validate_scope_batch(valid, self.batches[0], self.base), valid)

    def test_pending_reason_is_preserved_as_specific_missing_and_bounded(self):
        result = deepcopy(self.results[0])
        result["sections"][0].update(status="pending", reason="  建设规模待项目单位确认。  ")
        checked = validate_scope_batch(result, self.batches[0], self.base)
        entry = checked["sections"][0]
        self.assertEqual(entry["status"], "pending")
        self.assertEqual(entry["chapter_ids"], ["F1"])
        self.assertEqual(checked["missing"], [f"{entry['section_id']}：建设规模待项目单位确认。"])
        self.results[0] = checked
        merged = merge_scope_batches(self.base, self.catalog, self.batches, self.results)
        self.assertEqual(merged["feasibility_guide"]["sections"][0], entry)
        self.assertIn(checked["missing"][0], merged["missing"])
        result["missing"] = [f"其他明确缺项{index}" for index in range(16)]
        with self.assertRaises(ProductError):
            validate_scope_batch(result, self.batches[0], self.base)

    def test_pending_normalization_is_idempotent_at_sixteen_missing_items(self):
        result = deepcopy(self.results[0])
        result["missing"] = [f"其他明确缺项{index}" for index in range(8)]
        for entry in result["sections"]:
            entry.update(status="pending", reason=f"{entry['section_id']}的建设规模待项目单位确认。")
        checked = validate_scope_batch(result, self.batches[0], self.base)
        self.assertEqual(len(checked["missing"]), 16)
        self.assertEqual(validate_scope_batch(checked, self.batches[0], self.base), checked)

    def test_merge_binds_asset_preserves_base_deduplicates_and_accepts_smaller_batches(self):
        self.results[0]["missing"] = [self.base["missing"][0]]
        self.results[0]["conflicts"] = ["两份来源的数量不一致。"]
        self.results[1]["conflicts"] = list(self.results[0]["conflicts"])
        original = deepcopy((self.base, self.catalog, self.batches, self.results))
        merged = merge_scope_batches(self.base, self.catalog, self.batches, self.results)
        self.assertEqual((self.base, self.catalog, self.batches, self.results), original)
        self.assertEqual(merged["feasibility_guide"]["asset_sha256"], guide.asset_hash())
        self.assertEqual(len(merged["feasibility_guide"]["sections"]), 124)
        self.assertEqual(merged["conflicts"], ["两份来源的数量不一致。"])
        for field in self.base:
            if field != "conflicts":
                self.assertEqual(merged[field], self.base[field])
        smaller = scope_batches(self.catalog, 4)
        by_id = {entry["section_id"]: entry for result in self.results for entry in result["sections"]}
        results = [{"sections": [by_id[section["id"]] for section in batch["sections"]], "missing": [], "conflicts": []}
                   for batch in smaller]
        self.assertEqual(len(merge_scope_batches(self.base, self.catalog, smaller, results)["feasibility_guide"]["sections"]), 124)

    def test_merge_rejects_missing_duplicate_forged_or_reordered_batches_and_assets(self):
        invalid = [
            (self.catalog, self.batches[:-1], self.results[:-1]),
            (self.catalog, self.batches + [self.batches[0]], self.results + [self.results[0]]),
            (self.catalog, self.batches[::-1], self.results[::-1]),
            (self.catalog, self.batches, self.results[:-1]),
        ]
        forged = deepcopy(self.batches)
        forged[0]["chapter_title"] = "伪造归属"
        invalid.append((self.catalog, forged, self.results))
        for field, value in (("asset_sha256", "0" * 64), ("title", "伪造目录")):
            invalid.append(({**self.catalog, field: value}, self.batches, self.results))
        for index, (catalog, batches, results) in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ProductError):
                merge_scope_batches(self.base, catalog, batches, results)

    def test_final_rules_reject_cross_batch_orphan_parent_and_unmapped_feasibility_chapter(self):
        results = deepcopy(self.results)
        touched_batches = set()
        for index, result in enumerate(results):
            for entry in result["sections"]:
                if entry["section_id"].startswith("5.2."):
                    entry.update(status="not_applicable", chapter_ids=[], reason="本用例明确排除该项。")
                    touched_batches.add(index)
            validate_scope_batch(result, self.batches[index], self.base)
        self.assertGreater(len(touched_batches), 1)
        with self.assertRaisesMessage(ProductError, "适用的结构目录须保留对应实际子节"):
            merge_scope_batches(self.base, self.catalog, self.batches, results)
        base = deepcopy(self.base)
        base["chapters"].append({**base["chapters"][-1], "id": "F2", "title": "无人映射的可研章节"})
        with self.assertRaisesMessage(ProductError, "每个可研章节须对应至少一项实际适用的指南内容"):
            merge_scope_batches(base, self.catalog, self.batches, self.results)


class CompactBlueprintScopeTests(SimpleTestCase):
    setUp = BlueprintScopeBatchTests.setUp

    def compact_results(self, status="I"):
        return [{"reasons": [{"id": "R1", "text": "本项目明确保留该项论证。"}],
                 "decisions": [[f"S{batch['start_index'] + index + 1}", status, ["F1"], "R1"]
                               for index in range(len(batch["sections"]))], "missing": [], "conflicts": []}
                for batch in compact_batches(self.catalog)]

    def test_compact_catalog_three_batches_aliases_and_response_size(self):
        batches = compact_batches(self.catalog)
        self.assertEqual([len(batch["sections"]) for batch in batches], [48, 48, 28])
        self.assertEqual([section for batch in batches for section in batch["sections"]],
                         [section for batch in self.batches for section in batch["sections"]])
        base = deepcopy(self.base)
        base["chapters"][-1]["id"] = "real-feasibility-chapter"
        results = self.compact_results()
        normalized = []
        for batch, result in zip(batches, results):
            request = compact_scope_request(batch, base)
            self.assertEqual(request["chapters"], [{"id": "F1", "title": "建设必要性论证", "scope": "项目范围"}])
            self.assertEqual([section["id"] for section in request["sections"]],
                             [row[0] for row in result["decisions"]])
            self.assertEqual([value for group in batch["groups"] for value in group["section_ids"]],
                             [section["id"] for section in batch["sections"]])
            self.assertEqual({section["group"] for section in request["sections"]},
                             {group["id"] for group in request["groups"]})
            checked = validate_compact_scope(result, batch, base)
            self.assertTrue(all(entry["chapter_ids"] == ["real-feasibility-chapter"] for entry in checked["sections"]))
            self.assertEqual(validate_scope_batch(checked, batch, base), checked)
            normalized.append(checked)
        merged = merge_scope_batches(base, self.catalog, batches, normalized)
        self.assertEqual(len(merged["feasibility_guide"]["sections"]), 124)
        self.assertEqual(merged["feasibility_guide"]["asset_sha256"], guide.asset_hash())
        size = lambda value: len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        self.assertLess(size(results), size(normalized) // 2)
        self.assertLess(max(map(size, results)), 2500)

    def test_compact_pending_normalization_retains_all_56_notes_on_cached_revalidation(self):
        batch = compact_batches(self.catalog)[0]
        result = self.compact_results("P")[0]
        result["missing"] = [f"其他明确缺项{index}" for index in range(8)]
        checked = validate_compact_scope(result, batch, self.base)
        self.assertEqual(len(checked["missing"]), 56)
        self.assertEqual(validate_scope_batch(checked, batch, self.base), checked)
        result["missing"].append("第九条原始模型缺项")
        with self.assertRaises(ProductError):
            validate_compact_scope(result, batch, self.base)

    def test_compact_raw_reason_and_note_budgets_are_independent_of_generated_pending_notes(self):
        batch = compact_batches(self.catalog)[0]
        result = self.compact_results("P")[0]
        result["reasons"] = [{"id": f"R{index + 1}", "text": "理由" * 60} for index in range(10)]
        result["missing"] = [str(index) * 200 for index in range(4)]
        checked = validate_compact_scope(result, batch, self.base)
        self.assertEqual(len(checked["missing"]), 52)
        self.assertEqual(validate_scope_batch(checked, batch, self.base), checked)
        for field in ("reasons", "conflicts"):
            broken = deepcopy(result)
            if field == "reasons":
                broken[field].append({"id": "R11", "text": "超出合计理由预算"})
            else:
                broken[field].append("超出缺项与冲突合计预算")
            with self.subTest(field=field), self.assertRaises(ProductError):
                validate_compact_scope(broken, batch, self.base)

    def test_compact_rejects_missing_duplicate_unknown_boolean_aliases_and_invalid_reasons(self):
        batch = compact_batches(self.catalog)[0]
        mutations = [
            lambda value: value.update(extra=[]),
            lambda value: value["decisions"].pop(),
            lambda value: value["decisions"].append(deepcopy(value["decisions"][0])),
            lambda value: value["decisions"][0].__setitem__(0, "S49"),
            lambda value: value["decisions"][0].__setitem__(0, True),
            lambda value: value["decisions"][0].__setitem__(1, True),
            lambda value: value["decisions"][0].__setitem__(2, [True]),
            lambda value: value["decisions"][0].__setitem__(3, True),
            lambda value: value["decisions"][0].__setitem__(2, ["T1"]),
            lambda value: value["decisions"][0].__setitem__(2, ["F2"]),
            lambda value: value["decisions"][0].__setitem__(2, ["F1", "F1"]),
            lambda value: value["decisions"][0].__setitem__(2, []),
            lambda value: value["decisions"][0].__setitem__(1, "N"),
            lambda value: value["decisions"][0].__setitem__(3, "R2"),
            lambda value: value["reasons"].append(deepcopy(value["reasons"][0])),
            lambda value: value["reasons"][0].update(id=True),
            lambda value: value["reasons"][0].update(text=" "),
            lambda value: value["reasons"][0].update(text="长" * 121),
            lambda value: value.update(reasons=[]),
            lambda value: value.update(conflicts=["冲突"] * 9),
        ]
        for index, mutate in enumerate(mutations):
            result = self.compact_results()[0]
            mutate(result)
            with self.subTest(case=index), self.assertRaises(ProductError):
                validate_compact_scope(result, batch, self.base)
        result = self.compact_results()[0]
        result["decisions"][0][1:3] = ["N", []]
        checked = validate_compact_scope(result, batch, self.base)
        self.assertEqual(checked["sections"][0]["status"], "not_applicable")
        checked["sections"][0]["reason"] = ""
        with self.assertRaises(ProductError):
            validate_scope_batch(checked, batch, self.base)

    def test_compact_merge_rejects_forged_order_identity_asset_and_preserves_final_rules(self):
        batches = compact_batches(self.catalog)
        normalized = [validate_compact_scope(result, batch, self.base)
                      for result, batch in zip(self.compact_results(), batches)]
        mutations = [
            lambda value: value.reverse(),
            lambda value: value.pop(),
            lambda value: value[0].update(start_index=True),
            lambda value: value[0].update(asset_sha256="0" * 64),
            lambda value: value[0]["sections"][0].update(id="forged"),
            lambda value: value[0]["sections"][0].update(title="伪造标题"),
            lambda value: value[0]["groups"][0].update(chapter_id="forged"),
        ]
        for index, mutate in enumerate(mutations):
            broken = deepcopy(batches)
            mutate(broken)
            with self.subTest(case=index), self.assertRaises(ProductError):
                merge_scope_batches(self.base, self.catalog, broken, normalized)
        touched_batches = set()
        for index, result in enumerate(normalized):
            for entry in result["sections"]:
                if entry["section_id"].startswith("5.1."):
                    entry.update(status="not_applicable", chapter_ids=[], reason="本期不建设此项。")
                    touched_batches.add(index)
        self.assertGreater(len(touched_batches), 1)
        with self.assertRaisesMessage(ProductError, "适用的结构目录须保留对应实际子节"):
            merge_scope_batches(self.base, self.catalog, batches, normalized)
        base = deepcopy(self.base)
        base["chapters"].append({**base["chapters"][-1], "id": "F2", "title": "无人映射的可研章节"})
        normalized = [validate_compact_scope(result, batch, base)
                      for result, batch in zip(self.compact_results(), batches)]
        with self.assertRaisesMessage(ProductError, "每个可研章节须对应至少一项实际适用的指南内容"):
            merge_scope_batches(base, self.catalog, batches, normalized)
