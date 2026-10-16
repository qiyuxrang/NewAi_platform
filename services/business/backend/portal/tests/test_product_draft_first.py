import hashlib
import json
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings

from portal.product_documents import DocumentError, content_document, render_report_draft, _render_draft_diagrams
from portal.product_models import DocumentStep
from portal.product_worker import ExecutionError, _generate_family, _ensure_content_review, claim_task
from .base import PortalTestCase
from . import test_product_worker as worker_tests


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=300, PRODUCT_ENFORCE_OUTPUT_LENGTH=True,
                   PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100",
                     "route_cost_caps": {"product_blueprint": "1", "product_writing": "1", "product_review": "1"}})
class DraftFirstWorkerTests(PortalTestCase):
    setUp = worker_tests.ProductWorkerTests.setUp
    queue_outputs = worker_tests.ProductWorkerTests.queue_outputs
    reply = worker_tests.ProductWorkerTests.reply
    saved_chapters_for_continuation = worker_tests.ProductWorkerTests.saved_chapters_for_continuation
    saved_chapters_with_long_duplicate = worker_tests.ProductWorkerTests.saved_chapters_with_long_duplicate

    @override_settings(PRODUCT_ENFORCE_OUTPUT_LENGTH=False)
    @patch("portal.product_worker.generate_for_use")
    def test_quality_warning_keeps_existing_body_and_new_invalid_quantity(self, model):
        self.queue_outputs(missing=["预算待确认"], conflicts=["资料待核对"])
        saved = self.saved_chapters_for_continuation()
        self.task.revisions.filter(pk__in=[chapter.pk for chapter in saved[1:]]).delete()
        saved = saved[:1]
        originals = {chapter.pk: deepcopy(chapter.payload) for chapter in saved}
        def respond(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            if request["action"] == "independent_review":
                return {"content": json.dumps({"passed": False, "issues": ["数量尚未核实"]})}
            chapter = request["chapter"]
            return {"content": json.dumps({"chapter_id": chapter["id"], "title": chapter["title"],
                "paragraphs": [f"本章核对{chapter['title']}的实施材料：测试设备99台。"], "source_ids": ["r1"]})}
        model.side_effect = respond
        task_id, fence, attempt_id = claim_task()
        chapters = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        review = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertFalse(review.payload["passed"])
        self.assertTrue(review.payload["full_document_human_review_required"])
        self.assertIn("quantity_mismatch", {issue["code"] for issue in review.payload["issues"]})
        self.assertEqual(sum(json.loads(call.args[2][1]["content"])["action"] == "chapter" for call in model.call_args_list), 2)
        for chapter in saved:
            chapter.refresh_from_db()
            self.assertEqual(chapter.payload, originals[chapter.pk])
        document = content_document(self.task, self.input_revision, self.blueprint, chapters, draft=True, review_issues=review.payload["issues"])
        self.assertTrue(document["pending"])
        self.assertTrue(any("99台" in block.get("text", "") for block in document["blocks"]))

    @patch("portal.product_worker.generate_for_use")
    def test_short_saved_body_is_truthfully_reviewed_as_below_target(self, model):
        self.queue_outputs()
        chapters = self.saved_chapters_for_continuation()
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": json.dumps({"passed": True, "issues": []})}
        review = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertIn("output_length_below_target", {issue["code"] for issue in review.payload["issues"]})
        self.assertFalse(review.payload["passed"])
        self.assertLess(review.payload["draft_quality"]["actual_characters"], review.payload["draft_quality"]["minimum_characters"])

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_partial_draft_chapter_appends_and_complete_saved_chapters_are_reused(self, model):
        self.queue_outputs()
        saved = self.saved_chapters_for_continuation()
        original = deepcopy(saved[0].payload)
        def respond(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            self.assertEqual(request["chapter"]["id"], "chapter-1")
            self.assertTrue(request["continuation"]["append_only"])
            self.assertEqual(request["continuation"]["saved_text"], original["paragraphs"][0])
            return {"content": json.dumps({**original, "paragraphs": ["实施前核对现场签字、设备照片和验证记录。"]})}
        model.side_effect = respond
        task_id, fence, attempt_id = claim_task()
        chapters = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        model.assert_called_once()
        self.assertEqual(chapters[0].payload["paragraphs"][0], original["paragraphs"][0])
        self.assertEqual(len(chapters[0].payload["paragraphs"]), 2)
        saved[0].refresh_from_db()
        self.assertEqual(saved[0].payload, original)

    @patch("portal.product_worker.generate_for_use")
    def test_formal_generation_still_rejects_real_quantity_mismatch(self, model):
        candidate = json.loads(self.reply("chapter-1")["content"])
        candidate["paragraphs"] = ["测试设备99台。"]
        model.return_value = {"content": json.dumps(candidate)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as caught:
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        self.assertIn("quantity_mismatch", {issue["code"] for issue in caught.exception.quality_issues})
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_draft_still_rejects_unapproved_source_ids_and_structure(self, model):
        self.queue_outputs()
        candidate = json.loads(self.reply("chapter-1")["content"])
        candidate["source_ids"] = ["other-project"]
        model.return_value = {"content": json.dumps(candidate)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError):
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_entirely_repeated_draft_stops_after_one_correction_and_preserves_saved_body(self, model):
        self.queue_outputs()
        saved = self.saved_chapters_with_long_duplicate("technical-solution")
        original = deepcopy(saved[0].payload)
        repeated = saved[1].payload["paragraphs"][0]
        model.return_value = {"content": json.dumps({**original, "paragraphs": [repeated]})}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        saved[0].refresh_from_db()
        self.assertEqual(saved[0].payload, original)
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), len(saved))

    @patch("portal.product_worker.generate_for_use")
    def test_program_only_review_binds_body_policy_and_true_blueprint_approval(self, model):
        from portal.product_worker import _content_review_current
        from portal.product_service import digest
        self.queue_outputs()
        chapters = self.saved_chapters_for_continuation()
        task_id, fence, attempt_id = claim_task()
        review = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        model.assert_not_called()
        self.assertTrue(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
        self.assertEqual(review.payload["model_review"], {"status": "not_run", "scope": "program_only", "full_document_human_review_required": True})
        changed = deepcopy(review.payload)
        changed["quality_policy_sha256"] = "0" * 64
        altered = SimpleNamespace(payload=changed, sha256=digest(changed), change_reason=review.change_reason,
            input_hash=review.input_hash, blueprint_hash=review.blueprint_hash)
        self.assertFalse(_content_review_current(self.task, altered, self.input_revision, self.blueprint, chapters))
        with patch("portal.product_worker.approved_blueprint", return_value=None):
            self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))

    def test_single_render_step_repair_keeps_saved_body_and_completed_image_cache(self):
        import base64
        from portal.product_steps import run_step
        self.queue_outputs()
        chapters = self.saved_chapters_for_continuation()
        original_hashes = {chapter.pk: chapter.sha256 for chapter in chapters}
        task_id, fence, attempt_id = claim_task()
        fixture = DraftFirstDocumentTests()
        fixture.setUp()
        original = fixture.document()
        failed = {"DIAGRAM_02_FIGURE"}
        calls = []
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8WQAAAAASUVORK5CYII=")
        def render(directory, document, figure, source):
            calls.append(figure["id"])
            if figure["id"] in failed:
                raise DocumentError("diagram_render_failed")
            path = Path(directory) / figure["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png)
            return {"figures": [{"figure_id": figure["id"], "imageSha256": hashlib.sha256(png).hexdigest(),
                "sourceSha256": hashlib.sha256(source["source"].encode()).hexdigest()}]}
        step = lambda key, binding, execute, validate: run_step(task_id, fence, key, binding, execute, validate=validate)
        with tempfile.TemporaryDirectory() as storage, patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                patch("portal.product_documents._render_one_diagram", side_effect=render):
            first = _render_draft_diagrams(deepcopy(original), fixture.generator, Path(storage), step)
            failed_step = self.task.steps.get(status="failed")
            self.assertEqual((failed_step.key, failed_step.error_code),
                             ("diagram_render:technical-solution:DIAGRAM_02_FIGURE", "diagram_render_failed"))
            self.assertEqual((first["rendered"], first["pending_count"]), (14, 1))
            failed.clear()
            second = _render_draft_diagrams(deepcopy(original), fixture.generator, Path(storage), step)
            self.assertEqual((second["rendered"], second["pending_count"]), (15, 0))
            self.assertEqual(len(calls), 16)
            failed_step.refresh_from_db()
            self.assertEqual((failed_step.status, failed_step.attempts), ("completed", 2))
            self.assertEqual(self.task.steps.filter(status="completed", attempts=1).count(), 14)
        for chapter in chapters:
            chapter.refresh_from_db()
            self.assertEqual(chapter.sha256, original_hashes[chapter.pk])

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=3,
                       PRODUCT_OFFICE_RENDER_ENABLED=False, PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_documents.preflight_document_rendering", return_value={})
    @patch("portal.product_worker._generate_diagrams_uncached", side_effect=ExecutionError("diagram_generation_invalid"))
    @patch("portal.product_worker.generate_for_use")
    def test_platform_delivers_real_two_docx_and_ppt_with_failed_steps_and_no_fake_review(self, model, diagrams, preflight):
        from portal.product_worker import run_once
        from portal.product_pair import output_current
        self.queue_outputs()
        self.task.checkpoint["output_families"] = ["technical-solution", "feasibility", "presentation"]
        self.task.save(update_fields=["checkpoint"])
        def respond(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            if request["action"] == "independent_review":
                self.assertEqual(request["family"], "cross-report")
                return {"content": json.dumps({"passed": True, "issues": []})}
            self.assertEqual(request["action"], "chapter")
            chapter = request["chapter"]
            return {"content": json.dumps({"chapter_id": chapter["id"], "title": chapter["title"],
                "paragraphs": ["沿用清单中2台测试设备，实施条件须由负责人核对。"], "source_ids": ["r1"]})}
        model.side_effect = respond
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code), ("WAITING_REVIEW", "FINAL_REVIEW", ""))
        self.assertEqual(sum(json.loads(call.args[2][1]["content"])["action"] == "chapter"
                             for call in model.call_args_list), 6)
        model_calls_before_repair = model.call_count
        artifacts = list(self.task.artifacts.order_by("version"))
        self.assertEqual({artifact.family for artifact in artifacts}, {"technical-solution", "feasibility", "presentation"})
        failed_steps = list(self.task.steps.filter(key__startswith="diagram:", status="failed"))
        self.assertEqual(len(failed_steps), 35)
        self.assertTrue(all(step.error_code == "diagram_generation_invalid" for step in failed_steps))
        self.login(self.client, self.owner)
        for artifact in artifacts:
            self.assertTrue(output_current(self.task, artifact))
            response = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
            self.assertEqual(response.status_code, 200)
            raw = b"".join(response.streaming_content)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), artifact.sha256)
            from io import BytesIO
            with ZipFile(BytesIO(raw)) as archive:
                if artifact.family == "presentation":
                    self.assertIn("ppt/presentation.xml", archive.namelist())
                    self.assertEqual(artifact.render_evidence["visual_asset_count"], 0)
                    self.assertEqual(artifact.render_evidence["quality_gate"]["status"], "fail")
                else:
                    text = archive.read("word/document.xml").decode()
                    self.assertIn("图表待补", text)
                    self.assertEqual(artifact.render_evidence["diagram_generation"]["rendered"], 0)
                    self.assertFalse(artifact.review.payload["passed"])
                    self.assertEqual(artifact.review.payload["model_review"]["status"], "not_run")
                    self.assertNotIn("coverage", artifact.review.payload["model_review"])
        self.assertFalse(self.task.approvals.filter(artifact__isnull=False).exists())
        # The normal repair action must preserve downloads until a replacement
        # report/artifact transaction succeeds, including a later render failure.
        response = self.client.post(f"/api/product/tasks/{self.task.pk}/retry/",
            json.dumps({"expected_version": self.task.version}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertTrue(self.task.checkpoint["repair_pending_diagrams"])
        previous_hashes = {artifact.pk: artifact.sha256 for artifact in artifacts}
        def repair_failure(*args, **kwargs):
            for artifact in artifacts:
                artifact.refresh_from_db()
                self.assertTrue(output_current(self.task, artifact))
                download = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
                self.assertEqual(download.status_code, 200)
                download.close()
            raise DocumentError("document_render_failed")
        with patch("portal.product_three_drafts.render_report_draft", side_effect=repair_failure):
            run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "FAILED")
        self.assertTrue(self.task.checkpoint["repair_pending_diagrams"])
        for artifact in artifacts:
            artifact.refresh_from_db()
            self.assertTrue(output_current(self.task, artifact))
            self.assertEqual(artifact.sha256, previous_hashes[artifact.pk])
        self.assertEqual(model.call_count, model_calls_before_repair)


@override_settings(PRODUCT_OFFICE_RENDER_ENABLED=False)
class DraftFirstDocumentTests(SimpleTestCase):
    def setUp(self):
        self.task = SimpleNamespace(pk=uuid.uuid4(), title="隔离草稿验证")
        self.input = SimpleNamespace(pk=uuid.uuid4(), sha256="1" * 64, payload={
            "requirements": "校验原文", "conditions": [], "items": [], "sources": [], "issues": []})
        self.blueprint = SimpleNamespace(payload={"template_version": "frozen-original-v1", "missing": [], "conflicts": []})
        self.chapter = SimpleNamespace(sha256="2" * 64, payload={"chapter_id": "c1", "title": "项目概述",
            "source_ids": ["r1"], "paragraphs": ["设备布置和安全检查须由负责人核对。"]})

    def document(self):
        return content_document(self.task, self.input, self.blueprint, [self.chapter], draft=True)

    def generator(self, document):
        anchor = next(block for block in document["blocks"] if block["type"] == "paragraph")
        return [{"figure_id": figure["id"], "title": figure["caption"], "description": "依据正文，设备布置待核对。",
            "source": f'flowchart LR\nA["设备布置"] --> B["待核对{index}"]',
            "evidence_block_ids": [anchor["id"]], "anchor_text": "设备布置"}
            for index, figure in enumerate(block for block in document["blocks"] if block["type"] == "figure")]

    def test_mermaid_runtime_failure_is_draft_warning_and_formal_dependency_failure(self):
        from portal.product_documents import preflight_document_rendering
        with patch("portal.product_documents._mermaid_runtime", side_effect=DocumentError("template_unavailable")):
            runtime = preflight_document_rendering(draft=True)
            self.assertEqual(runtime["mermaid"], {"status": "unavailable", "reason": "node_unavailable"})
            with self.assertRaises(DocumentError):
                preflight_document_rendering()

    def test_all_diagrams_failed_still_creates_real_docx_with_pending_not_fake_images(self):
        from portal.product_documents import _document_runtime
        with tempfile.TemporaryDirectory() as storage, override_settings(PRODUCT_STORAGE_ROOT=storage), \
                patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                patch("portal.product_documents._render_one_diagram", side_effect=DocumentError("diagram_render_failed",
                    diagnostic={"stage": "diagram_render", "reason": "diagram_parse_or_anchor_failed"})):
            result = render_report_draft(self.task, self.input, self.blueprint, [self.chapter], "technical-solution",
                draft=True, diagram_generator=self.generator, workspace_key="isolated")
            target = Path(storage) / result["path"]
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), result["sha256"])
            with ZipFile(target) as archive:
                text = archive.read("word/document.xml").decode()
                self.assertIn("图表待补", text)
                self.assertIn(self.chapter.payload["paragraphs"][0], text)
            diagrams = result["render_evidence"]["diagram_generation"]
            self.assertEqual((diagrams["planned_count"], diagrams["rendered"], diagrams["pending_count"]), (15, 0, 15))
            self.assertEqual(diagrams["figures"], [])
            self.assertEqual(diagrams["status"], "pending")
            content = json.loads((Path(storage) / result["content_path"]).read_bytes())
            self.assertFalse(any(block["type"] == "figure" for block in content["blocks"]))
            self.assertEqual(result["render_evidence"]["business_approval"], "blocked")

    def test_one_failed_figure_recovery_reuses_success_and_keeps_source_body(self):
        original = self.document()
        cached = {}
        calls = []
        failed = {"DIAGRAM_02_FIGURE"}
        def operation(directory, document, figure, source):
            calls.append(figure["id"])
            if figure["id"] in failed:
                raise DocumentError("diagram_render_failed")
            path = Path(directory) / figure["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"isolated-image" + figure["id"].encode())
            return {"figures": [{"figure_id": figure["id"], "imageSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sourceSha256": hashlib.sha256(source["source"].encode()).hexdigest()}]}
        def step(key, binding, execute, validate):
            if key in cached and validate(cached[key]):
                return cached[key]
            result = execute()
            cached[key] = result
            return result
        with tempfile.TemporaryDirectory() as storage, patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                patch("portal.product_documents._render_one_diagram", side_effect=operation):
            first = _render_draft_diagrams(deepcopy(original), self.generator, Path(storage), step)
            self.assertEqual((first["rendered"], first["pending_count"]), (14, 1))
            failed.clear()
            second_document = deepcopy(original)
            second = _render_draft_diagrams(second_document, self.generator, Path(storage), step)
            self.assertEqual((second["rendered"], second["pending_count"]), (15, 0))
            self.assertEqual(len(calls), 16)
            original_body = {block["id"]: block["text"] for block in original["blocks"]
                             if block["type"] == "paragraph" and block["id"].startswith("C")}
            recovered_body = {block["id"]: block["text"] for block in second_document["blocks"]
                              if block["type"] == "paragraph" and block["id"].startswith("C")}
            self.assertEqual(recovered_body, original_body)

    def test_formal_diagram_failure_does_not_degrade(self):
        with tempfile.TemporaryDirectory() as storage, override_settings(PRODUCT_STORAGE_ROOT=storage), \
                patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                patch("portal.product_documents._render_formal_diagrams", side_effect=DocumentError("diagram_render_failed")):
            with self.assertRaises(DocumentError):
                render_report_draft(self.task, self.input, self.blueprint, [self.chapter], "technical-solution", diagram_generator=self.generator)
