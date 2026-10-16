from contextlib import ExitStack, nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from portal import product_worker as worker
from portal.product_service import digest
from portal import product_writing_revision as revision


class WritingRevisionTests(SimpleTestCase):
    def setUp(self):
        self.chapter = {"id": "tech-scope", "family": "technical-solution", "title": "建设范围",
                        "scope": "据授权资料说明范围与确认事项", "source_ids": ["source-1"]}
        self.blueprint = SimpleNamespace(sha256="blueprint", payload={"purpose": "范围核对", "audience": "编制人员",
            "conditions": [], "chapters": [self.chapter]})
        self.input = SimpleNamespace(sha256="input", payload={"items": [], "background": "",
            "sources": [{"id": "source-1", "purpose": "background", "media_type": "text/plain"}]})
        self.original = {"chapter_id": self.chapter["id"], "title": self.chapter["title"],
            "source_ids": ["source-1"], "paragraphs": ["原始资料应由建设单位提供并记录版本及出处。",
                "具体边界尚待确认，应进一步核查交接资料。", "验收记录应保留确认责任人与核对依据。"]}
        self.existing = SimpleNamespace(payload=deepcopy(self.original), sha256=digest(self.original))
        self.task = SimpleNamespace(pending_action="write")
        self.finding = {"family": "technical-solution", "chapter_id": self.chapter["id"],
                        "paragraph_indices": [1], "issues": ["[W000001] 明确范围的待确认边界"]}

    def repair(self, reply):
        def generate(*args, output_validator, **kwargs):
            return output_validator(reply)

        def store(*args, **kwargs):
            payload = args[3]
            return SimpleNamespace(payload=payload, sha256=digest(payload))

        with patch.object(worker, "_writing_model", side_effect=generate), \
             patch.object(worker, "model_input", return_value={}), \
             patch.object(worker, "_source_items", return_value=[]), \
             patch.object(worker, "_family_target", return_value=1), \
             patch.object(worker, "_guard"), \
             patch.object(worker, "current_chapters", return_value={self.chapter["id"]: self.existing}), \
             patch.object(worker, "_store", side_effect=store), \
             patch.object(revision, "atomic", side_effect=nullcontext):
            return revision._repair_chapter("task", 1, "attempt", self.task, self.input, self.blueprint,
                "technical-solution", self.existing, self.finding, {"technical-solution": [self.existing]})

    def test_located_replacement_preserves_other_paragraphs_and_old_revision(self):
        paragraph = "建设范围以已授权资料为依据，缺项由建设单位确认。"
        repaired = self.repair({**self.original, "paragraphs": [paragraph]})
        self.assertEqual(repaired.payload["paragraphs"], [self.original["paragraphs"][0], paragraph,
                                                         self.original["paragraphs"][2]])
        self.assertEqual(self.existing.payload, self.original)
        self.assertNotEqual(repaired.sha256, self.existing.sha256)

    def test_unapproved_sources_or_wrong_replacement_count_are_rejected(self):
        for reply in ({**self.original, "paragraphs": ["保持边界待确认。"], "source_ids": ["foreign-source"]},
                      {**self.original, "paragraphs": ["保留范围。", "额外改写。"]}):
            with self.subTest(reply=reply), self.assertRaises(worker.ExecutionError):
                self.repair(reply)
        self.assertEqual(self.existing.payload, self.original)

    def test_invalid_location_never_guesses_a_paragraph(self):
        self.finding["paragraph_indices"] = [99]
        with patch.object(worker, "_writing_model") as generate:
            result = revision._repair_chapter("task", 1, "attempt", self.task, self.input, self.blueprint,
                "technical-solution", self.existing, self.finding, {"technical-solution": [self.existing]})
        self.assertIs(result, self.existing)
        generate.assert_not_called()

    def test_drafts_skip_editor_without_clearing_findings_or_claiming_pass(self):
        from portal import product_writing_editor
        prior = {"status": "issues_found", "passed": False, "issues": ["原有冲突"],
                 "blocked_families": ["technical-solution"]}
        for action in ("generate_outputs", "three_drafts"):
            with self.subTest(action=action):
                self.task.pending_action = action
                fresh = SimpleNamespace(checkpoint={"writing_editor": deepcopy(prior)}, save=lambda **kwargs: None)
                with patch.object(product_writing_editor, "review_writing") as review, \
                     patch.object(revision, "_repair_chapter") as repair, \
                     patch.object(worker, "_analysis_progress") as progress, \
                     patch.object(worker, "_guard", return_value=fresh), \
                     patch.object(revision, "atomic", side_effect=nullcontext):
                    result = revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                        self.blueprint, {"technical-solution": [self.existing]})
                review.assert_not_called()
                repair.assert_not_called()
                self.assertFalse(result["review"]["passed"])
                self.assertEqual(result["review"]["status"], "not_run")
                self.assertEqual(result["blocked_families"], [])
                self.assertEqual(result["failures"], [])
                self.assertIs(result["chapters"]["technical-solution"][0], self.existing)
                self.assertEqual(fresh.checkpoint["writing_editor"], prior)
                self.assertEqual(fresh.checkpoint["draft_consistency"]["chapter_hashes"],
                                 {"technical-solution": {self.chapter["id"]: self.existing.sha256}})
                self.assertEqual(progress.call_args.args[3], "skipped")

    def test_draft_deferral_still_enforces_worker_permissions(self):
        self.task.pending_action = "generate_outputs"
        with patch.object(worker, "_guard", side_effect=worker.ExecutionError("permission_changed")), \
             patch.object(revision, "atomic", side_effect=nullcontext), self.assertRaises(worker.ExecutionError) as raised:
            revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                self.blueprint, {"technical-solution": [self.existing]})
        self.assertEqual(raised.exception.code, "permission_changed")

    def test_reviewer_is_run_again_and_unresolved_issues_are_not_cleared(self):
        from portal import product_writing_editor
        corrected = SimpleNamespace(payload=deepcopy(self.original), sha256="corrected-hash")
        first = {"issues": ["原问题"], "affected_chapters": [self.finding], "blocked_families": ["technical-solution"]}
        second = {"issues": ["仍有实质问题"], "affected_chapters": [self.finding], "blocked_families": ["technical-solution"]}
        fresh = SimpleNamespace(checkpoint={}, save=lambda **kwargs: None)
        with patch.object(product_writing_editor, "review_writing", side_effect=[first, second]) as review, \
             patch.object(revision, "_repair_chapter", return_value=corrected) as repair, \
             patch.object(worker, "_analysis_progress"), patch.object(worker, "_guard", return_value=fresh), \
             patch.object(revision, "atomic", side_effect=nullcontext):
            result = revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                self.blueprint, {"technical-solution": [self.existing]})
        self.assertEqual(review.call_count, 2)
        self.assertEqual(repair.call_count, 1)
        self.assertEqual(result["review"]["issues"], ["仍有实质问题"])
        self.assertEqual(result["blocked_families"], ["technical-solution"])
        self.assertEqual(fresh.checkpoint["writing_editor"]["repair_round_limit"], 1)

    def test_rejected_correction_keeps_original_findings_visible(self):
        from portal import product_writing_editor
        self.finding["issues"] = ["原始冲突依据"]
        finding = {"issues": ["原始冲突依据"], "affected_chapters": [self.finding],
                   "blocked_families": ["technical-solution"]}
        fresh = SimpleNamespace(checkpoint={}, save=lambda **kwargs: None)
        error = worker.ExecutionError("invalid_model_output")
        with patch.object(product_writing_editor, "review_writing", return_value=finding), \
             patch.object(revision, "_repair_chapter", side_effect=error), \
             patch.object(worker, "_analysis_progress"), patch.object(worker, "_guard", return_value=fresh), \
             patch.object(revision, "atomic", side_effect=nullcontext):
            result = revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                self.blueprint, {"technical-solution": [self.existing]})
        self.assertEqual(result["failures"], [error])
        self.assertEqual(fresh.checkpoint["writing_editor"]["issues"], ["原始冲突依据"])
        self.assertEqual(fresh.checkpoint["writing_editor"]["blocked_families"], ["technical-solution"])

    def test_failed_family_keeps_findings_while_other_family_is_repaired(self):
        from portal import product_writing_editor
        from portal.product_steps import StepRetryPending
        other = SimpleNamespace(payload={**self.original, "chapter_id": "feas-scope"}, sha256="feas-old")
        corrected = SimpleNamespace(payload=other.payload, sha256="feas-new")
        self.finding["issues"] = ["真实冲突"]
        other_finding = {**self.finding, "family": "feasibility", "chapter_id": "feas-scope", "issues": ["已修复冲突"]}
        first = {"issues": ["真实冲突", "已修复冲突"], "affected_chapters": [self.finding, other_finding],
                 "blocked_families": ["technical-solution", "feasibility"]}
        second = {"issues": [], "affected_chapters": [], "blocked_families": [], "passed": True}
        error = StepRetryPending(None, "timeout")
        fresh = SimpleNamespace(checkpoint={}, save=lambda **kwargs: None)
        with patch.object(product_writing_editor, "review_writing", side_effect=[first, second]), \
             patch.object(revision, "_repair_chapter", side_effect=[error, corrected]) as repair, \
             patch.object(worker, "_analysis_progress"), patch.object(worker, "_guard", return_value=fresh), \
             patch.object(revision, "atomic", side_effect=nullcontext):
            result = revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                self.blueprint, {"technical-solution": [self.existing], "feasibility": [other]})
        self.assertEqual(repair.call_count, 2)
        self.assertEqual(result["blocked_families"], ["technical-solution"])
        self.assertEqual(result["failures"], [error])
        self.assertEqual(result["review"]["issues"], ["真实冲突"])
        self.assertEqual(result["review"]["affected_chapters"], [self.finding])
        self.assertFalse(result["review"]["passed"])
        self.assertIs(result["chapters"]["feasibility"][0], corrected)

    def test_hard_stop_still_raises_with_original_findings_saved(self):
        from portal import product_writing_editor
        first = {"issues": ["真实冲突"], "affected_chapters": [self.finding],
                 "blocked_families": ["technical-solution"]}
        fresh = SimpleNamespace(checkpoint={}, save=lambda **kwargs: None)
        with patch.object(product_writing_editor, "review_writing", return_value=first), \
             patch.object(revision, "_repair_chapter", side_effect=worker.ExecutionError("permission_changed")), \
             patch.object(worker, "_analysis_progress"), patch.object(worker, "_guard", return_value=fresh), \
             patch.object(revision, "atomic", side_effect=nullcontext), self.assertRaises(worker.ExecutionError) as raised:
            revision.ensure_writing_consistency("task", 1, "attempt", self.task, self.input,
                self.blueprint, {"technical-solution": [self.existing]})
        self.assertEqual(raised.exception.code, "permission_changed")
        self.assertEqual(fresh.checkpoint["writing_editor"]["issues"], ["真实冲突"])

    def action_context(self, action, consistency):
        stack = ExitStack()
        self.task.pending_action = action
        self.task.stage, self.task.pk = "WRITING", "task"
        self.task.checkpoint = {"output_families": ["technical-solution", "feasibility"]}
        self.blueprint.input_hash = self.input.sha256
        other = SimpleNamespace(payload={**self.original, "chapter_id": "feas-scope"}, sha256="feas-old")
        self.blueprint.payload["chapters"].append({**self.chapter, "id": "feas-scope", "family": "feasibility"})
        families = {"technical-solution": [self.existing], "feasibility": [other]}
        for target, kwargs in [("atomic", {"side_effect": nullcontext}),
                ("_guard", {"return_value": self.task}),
                ("current_revision", {"side_effect": lambda task, kind: self.input if kind == "input" else self.blueprint}),
                ("current_chapters", {"side_effect": lambda task, ih, bh, family: {
                    record.payload["chapter_id"]: record for record in families[family]}}),
                ("_generate_families", {"return_value": (families, [])}),
                ("_content_quality_guard", {}), ("_analysis_progress", {})]:
            stack.enter_context(patch.object(worker, target, **kwargs))
        stack.enter_context(patch.object(worker.DocumentTask.objects, "get", return_value=self.task))
        approved = stack.enter_context(patch.object(worker.DocumentApproval.objects, "filter"))
        approved.return_value.exists.return_value = True
        stack.enter_context(patch.object(revision, "ensure_writing_consistency", return_value={
            "chapters": families, **consistency}))
        return stack

    def test_three_drafts_runs_editor_for_both_families_and_cannot_bypass_issues(self):
        from portal import product_three_drafts
        with self.action_context("three_drafts", {"blocked_families": ["technical-solution"], "failures": []}), \
             patch.object(product_three_drafts, "generate_three_drafts") as generate, \
             patch.object(worker, "_finish") as finish, \
             patch.object(revision, "ensure_writing_consistency", return_value={
                 "blocked_families": ["technical-solution"], "failures": []}) as review:
            worker._execute_claim_action("task", 1, "attempt")
        self.assertEqual(set(review.call_args.args[-1]), {"technical-solution", "feasibility"})
        generate.assert_not_called()
        self.assertEqual(finish.call_args.args[5], "content_review_required")

    def test_outputs_delivers_unblocked_family_and_preserves_step_retry(self):
        from portal import product_documents, product_three_drafts
        from portal.product_steps import StepRetryPending
        error = StepRetryPending(None, "timeout")
        with self.action_context("generate_outputs", {"blocked_families": ["technical-solution"], "failures": [error]}), \
             patch.object(product_documents, "preflight_document_rendering"), \
             patch.object(product_three_drafts, "generate_report_drafts", return_value=[]) as generate, \
             patch.object(worker, "_finish") as finish:
            worker._execute_claim_action("task", 1, "attempt")
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(generate.call_args.kwargs["families"], ["feasibility"])
        self.assertEqual(finish.call_args.args[3], "QUEUED")
        self.assertIs(finish.call_args.kwargs["recovery"], error)
