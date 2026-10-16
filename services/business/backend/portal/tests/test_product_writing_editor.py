"""Offline editor checks: mocked permissions, steps and models; no database access."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal import product_worker as worker
from portal import product_writing_editor as editor
from portal.product_service import digest


def revision(identifier, payload):
    return SimpleNamespace(pk=identifier, payload=payload, sha256=digest(payload))


@override_settings(PRODUCT_REVIEW_ROUTE="product_review")
class WritingEditorTests(SimpleTestCase):
    def setUp(self):
        self.items = [{"row_id": "r1", "name": "测试服务器", "quantity": "2", "unit": "台"}]
        self.input = revision("input", {"items": self.items})
        self.blueprint = revision("blueprint", {"conditions": [{"text": "项目预算待确认", "type": "human"}],
            "chapters": [{"id": "T", "family": "technical-solution", "title": "设备设计", "source_ids": ["r1"]},
                         {"id": "F", "family": "feasibility", "title": "设备论证", "source_ids": ["r1"]}]})
        self.chapters = {family: [revision(identifier, {"chapter_id": identifier, "title": title,
            "paragraphs": ["测试服务器共2台，具体部署位置待确认。"], "source_ids": ["r1"]})]
            for family, identifier, title in (("technical-solution", "T", "设备设计"), ("feasibility", "F", "设备论证"))}
        self.task = SimpleNamespace(pk="task")
        self.cache = {}

        def run_step(task_id, fence, key, binding, operation, *, validate):
            identity = (key, digest(binding))
            if identity in self.cache and validate(deepcopy(self.cache[identity])):
                return deepcopy(self.cache[identity])
            self.cache[identity] = deepcopy(operation())
            return deepcopy(self.cache[identity])

        self.patches = [patch.object(editor, "atomic", side_effect=lambda: nullcontext()),
                        patch.object(editor, "current_revision", side_effect=lambda task, kind: self.input if kind == "input" else self.blueprint),
                        patch.object(editor, "source_ids_belong", return_value=True),
                        patch.object(editor, "rules_hash", return_value="rules-1"),
                        patch.object(editor, "content_quality_policy_hash", return_value="quality-1"),
                        patch.object(editor, "run_step", side_effect=run_step),
                        patch.object(worker, "_guard", return_value=self.task),
                        patch.object(worker, "current_chapters", side_effect=lambda task, inp, bp, family:
                                     {chapter.payload["chapter_id"]: chapter for chapter in self.chapters[family]}),
                        patch.object(worker, "_source_items", return_value=self.items),
                        patch.object(worker, "_review_route_hash", return_value="route-1"),
                        patch.object(worker, "_model", side_effect=self.model_reply)]
        self.mocks = [patcher.start() for patcher in self.patches]
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(self.patches)])
        self.source_allowed, self.rules, self.route, self.model = self.mocks[2], self.mocks[3], self.mocks[9], self.mocks[10]

    def model_reply(self, task_id, fence, attempt_id, route, request, *, output_validator):
        return output_validator({"passed": True, "issues": []})

    def review(self):
        return editor.review_writing("task", 1, "attempt", self.task, self.input, self.blueprint, self.chapters)

    def plan(self):
        return editor._plan(self.chapters, self.input.payload, self.blueprint.payload, self.items, worker._review_request_size)

    def test_full_scan_keeps_exact_original_locations_and_declares_selected_scope(self):
        for chapters in self.chapters.values():
            chapters[0].payload["paragraphs"].append("系统方案应便于使用。")
        requests, locations, coverage = self.plan()
        self.assertEqual(len(requests), 1)
        self.assertEqual(coverage["scanned_sentences"], 4)
        self.assertEqual(coverage["not_selected_sentences"], 2)
        self.assertFalse(coverage["full_document_semantic_review"])
        for chunk in requests[0]["chapters"]:
            location = locations[chunk["chunk_id"]]
            original = self.chapters[location["family"]][0].payload["paragraphs"][location["paragraph_index"]]
            self.assertEqual(chunk["paragraphs"], [original[location["start"]:location["end"]]])
            self.assertEqual(chunk["source_ids"], ["r1"])
        result = self.review_after_hash_update()
        self.assertTrue(result["passed"])
        self.assertEqual(result["scope"], editor.SCOPE)
        self.assertTrue(result["full_document_human_review_required"])

    def review_after_hash_update(self):
        for chapters in self.chapters.values():
            for chapter in chapters:
                chapter.sha256 = digest(chapter.payload)
        return self.review()

    def test_issue_is_preserved_and_true_flag_cannot_override_findings(self):
        issue = []

        def reply(*args, output_validator):
            identifiers = [chunk["chunk_id"] for chunk in args[4]["chapters"]]
            issue.append("[" + ",".join(identifiers) + "] 同一设备数量分别为2台与3台，须按来源核对。")
            return output_validator({"passed": True, "issues": [issue[-1]]})

        self.model.side_effect = reply
        result = self.review()
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["issues"], issue)
        self.assertEqual(set(result["blocked_families"]), set(self.chapters))
        self.assertEqual({item["chapter_id"] for item in result["affected_chapters"]}, {"T", "F"})
        for item in result["affected_chapters"]:
            self.assertEqual(item["issues"], issue)
            self.assertEqual(item["paragraph_indices"], [0])

    def test_unknown_or_missing_chunk_location_is_rejected_without_guessing(self):
        for issue in ("数量存在冲突。", "[W999999] 数量存在冲突。"):
            with self.subTest(issue=issue):
                self.model.side_effect = lambda *args, output_validator: output_validator({"passed": False, "issues": [issue]})
                with self.assertRaises(worker.ExecutionError) as caught:
                    self.review()
                self.assertEqual(caught.exception.code, "invalid_model_output")

    def test_shared_baseline_preserves_source_kind_and_excludes_uncited_statements(self):
        public = {"text": "测试服务器的通用数量仅作参考。", "source_ids": ["r1"], "kind": "public_reference"}
        self.input.payload["statements"] = [public,
            {"text": "测试服务器已部署99台。", "source_ids": ["outside-source"]},
            {"text": "测试服务器已部署88台。", "source_ids": []}]
        requests, _, _ = self.plan()
        baseline = requests[0]["comparison_groups"][0]["baseline"]
        self.assertEqual(baseline["source_statements"], [public])
        self.assertEqual(baseline["source_statements"][0]["kind"], "public_reference")

    def test_cached_batches_bind_all_body_input_blueprint_rules_and_route_hashes(self):
        self.review()
        self.review()
        self.assertEqual(self.model.call_count, 1)
        self.chapters["technical-solution"][0].payload["paragraphs"].append("这是一句未被主题抽取的文字。")
        self.review_after_hash_update()
        self.input.payload["project"] = "新项目版本"
        self.input.sha256 = digest(self.input.payload)
        self.review()
        self.blueprint.payload["conditions"].append({"text": "另一条件", "type": "human"})
        self.blueprint.sha256 = digest(self.blueprint.payload)
        self.review()
        self.rules.return_value = "rules-2"
        self.review()
        self.route.return_value = "route-2"
        self.review()
        self.assertEqual(self.model.call_count, 6)

    def test_outside_blueprint_or_current_source_permission_stops_before_model(self):
        self.chapters["technical-solution"][0].payload["source_ids"] = ["outside-source"]
        with self.assertRaises(worker.ExecutionError):
            self.review_after_hash_update()
        self.model.assert_not_called()
        self.chapters["technical-solution"][0].payload["source_ids"] = ["r1"]
        self.chapters["technical-solution"][0].sha256 = digest(self.chapters["technical-solution"][0].payload)
        self.source_allowed.return_value = False
        with self.assertRaises(worker.ExecutionError) as caught:
            self.review()
        self.assertEqual(caught.exception.code, "retrieval_authorization_required")
        self.model.assert_not_called()

    def test_revoked_permission_rejects_cached_review(self):
        self.review()
        self.source_allowed.return_value = False
        with self.assertRaises(worker.ExecutionError):
            self.review()
        self.assertEqual(self.model.call_count, 1)

    def test_long_groups_are_linear_bounded_and_pending_not_false_pass(self):
        text = "测试服务器共2台，" + "具体部署边界仍应保留原始资料中的条件，" * 12 + "待确认。"
        for chapters in self.chapters.values():
            chapters[0].payload["paragraphs"] = [text] * 18
        requests, locations, coverage = self.plan()
        self.assertGreater(len(requests), 1)
        self.assertLessEqual(len(requests), 5)
        reviewed = {chunk["chunk_id"] for request in requests for chunk in request["chapters"]}
        self.assertEqual(reviewed, set(locations))
        for request in requests:
            self.assertLessEqual(worker._review_request_size(request), 14500)
            self.assertLessEqual(sum(len(text) for chunk in request["chapters"] for text in chunk["paragraphs"]), 7000)
            self.assertTrue(request["comparison_groups"][0]["baseline"]["equipment_items"])
        result = self.review_after_hash_update()
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "pending_human_review")
        self.assertEqual(result["blocked_families"], [])
        self.assertEqual(result["affected_chapters"], [])
        self.assertTrue(coverage["pending_groups"])

    def test_long_sentence_and_json_escaping_are_never_silently_truncated(self):
        text = "建设范围为" + ('路径\\"以及换行\t' * 850) + "，边界待确认。"
        for chapters in self.chapters.values():
            chapters[0].payload["paragraphs"] = [text]
        requests, locations, coverage = self.plan()
        self.assertTrue(coverage["pending_groups"])
        for request in requests:
            self.assertLessEqual(worker._review_request_size(request), 14500)
        for family in self.chapters:
            chunks = {chunk["chunk_id"]: chunk for request in requests for chunk in request["chapters"] if chunk["family"] == family}
            ordered = sorted(chunks.values(), key=lambda chunk: chunk["fragment"]["start"])
            self.assertEqual("".join(chunk["paragraphs"][0] for chunk in ordered), text)
            self.assertTrue(all(identifier in locations for identifier in chunks))

    def test_oversized_context_is_reported_pending_without_a_model_call(self):
        for chapters in self.chapters.values():
            chapters[0].payload["source_ids"] = ["source-" + "x" * 60 + str(index) for index in range(500)]
        requests, locations, coverage = self.plan()
        self.assertEqual(requests, [])
        self.assertEqual(coverage["unreviewed_chunks"], len(locations))
        self.assertEqual(coverage["pending_groups"]["equipment:测试服务器"]["reason"], "request_context_too_large")

    def test_unpaired_or_unselected_body_is_not_claimed_as_a_pass(self):
        self.chapters["feasibility"][0].payload["paragraphs"] = ["仅保留本章原文。"]
        result = self.review_after_hash_update()
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "not_applicable")
        self.assertEqual(result["blocked_families"], [])
        self.assertEqual(result["coverage"]["unpaired_chunks"], 1)
        self.model.assert_not_called()

    def test_false_reviewer_without_findings_stays_pending_without_inventing_a_defect(self):
        self.model.side_effect = lambda *args, output_validator: output_validator({"passed": False, "issues": []})
        result = self.review()
        self.assertEqual(result["status"], "pending_human_review")
        self.assertFalse(result["passed"])
        self.assertEqual(result["blocked_families"], [])
        self.assertEqual(result["affected_chapters"], [])
