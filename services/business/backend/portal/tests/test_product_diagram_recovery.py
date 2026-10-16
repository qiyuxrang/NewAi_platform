import base64
import copy
import hashlib
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.product_documents import DocumentError, _render_draft_diagrams
from portal.product_models import DocumentAttempt, DocumentStep, DocumentTask
from portal.product_steps import StepRetryPending, run_step
from portal.product_worker import ExecutionError, _finish, claim_task
from .base import PortalTestCase


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8WQAAAAASUVORK5CYII="
)
CORRECTED_TITLE = "设备布置复核流程（已纠正）"


@override_settings(
    PRODUCT_P1_ENABLED=True,
    PRODUCT_MODEL_CALLS_ALLOWED=True,
    PRODUCT_MAX_MODEL_CALLS=10,
    PRODUCT_COST_POLICY={
        "approval_ref": "isolated-test-only",
        "currency": "TEST",
        "max_task_cost": "100",
        "route_cost_caps": {"product_review": "1"},
    },
    PRODUCT_STEP_MAX_ATTEMPTS=3,
    PRODUCT_STEP_RETRY_BASE_SECONDS=1,
    PRODUCT_STEP_RETRY_MAX_SECONDS=10,
)
class ProductDiagramRecoveryTests(PortalTestCase):
    def setUp(self):
        super().setUp()
        from .test_product_review_output_retry import ProductReviewOutputRetryTests
        from .test_product_draft_first import DraftFirstDocumentTests

        self.review_fixture = ProductReviewOutputRetryTests()
        self.review_fixture.setUp()
        self.task = self.review_fixture.task
        self.task_id, self.fence, self.attempt_id = self.review_fixture.claimed()

        self.document_fixture = DraftFirstDocumentTests()
        self.document_fixture.setUp()
        self.document = self.document_fixture.document()
        self.target = next(block for block in self.document["blocks"]
                           if block.get("type") == "figure")
        self.target_id = self.target["id"]
        self.base_key = f'diagram_render:{self.document["family"]}:{self.target_id}'

        self.repair_calls = []
        self.rendered = []
        self.target_render_attempts = 0

        def generator(value):
            feedback = value.get("diagram_render_feedback")
            if feedback:
                self.repair_calls.append(copy.deepcopy(value))
                figure = next(block for block in value["blocks"] if block.get("type") == "figure")
                paragraph = next(block for block in value["blocks"] if block.get("type") == "paragraph")
                return [{
                    "figure_id": figure["id"],
                    "title": CORRECTED_TITLE,
                    "description": "设备布置和安全检查由负责人逐项复核。",
                    "source": 'flowchart LR\nA["设备布置"] --> B["安全检查"]',
                    "evidence_block_ids": [paragraph["id"]],
                    "anchor_text": "设备布置",
                }]
            return self.document_fixture.generator(value)

        def renderer(directory, document, figure, source):
            if figure["id"] == self.target_id:
                self.target_render_attempts += 1
                if self.target_render_attempts == 1:
                    raise DocumentError("diagram_render_failed", diagnostic={
                        "stage": "diagram_render", "reason": "diagram_layout_unreadable"})
            image_path = Path(directory) / figure["path"]
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(PNG)
            evidence = {"figures": [{
                "figure_id": figure["id"],
                "imageSha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "sourceSha256": hashlib.sha256(source["source"].encode()).hexdigest(),
                "layout": {"version": "word-readable-v2", "panels": [{
                    "index": 1, "total": 1, "path": figure["path"], "width_mm": 145, "min_font_pt": 13.5,
                    "imageSha256": hashlib.sha256(image_path.read_bytes()).hexdigest()}]},
            }]}
            self.rendered.append((figure["id"], copy.deepcopy(source), evidence))
            return evidence

        self.generator = generator
        self.renderer = renderer

    def diagram_step(self, task_id, fence):
        return lambda key, binding, operation, validate: run_step(
            task_id, fence, key, binding, operation, validate=validate)

    def render(self, document, directory, task_id, fence):
        return _render_draft_diagrams(
            document, self.generator, directory, self.diagram_step(task_id, fence))

    def prepare_office_retry(self, directory):
        with patch("portal.product_documents.preflight_document_rendering",
                   return_value={"mermaid": {"status": "available"}}), \
                patch("portal.product_documents._render_one_diagram", side_effect=self.renderer):
            first = self.render(copy.deepcopy(self.document), directory, self.task_id, self.fence)

        self.assertEqual((first["rendered"], first["pending_count"]), (15, 0))
        self.assertEqual(self.target_render_attempts, 2)
        self.assertEqual(len(self.repair_calls), 1)

        selected = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key + ":selected")
        base = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key)
        correction = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key + ":correction")
        self.assertEqual((selected.status, selected.attempts), ("completed", 1))
        self.assertEqual((base.status, base.attempts), ("failed", 1))
        self.assertEqual((correction.status, correction.attempts), ("completed", 1))
        self.assertTrue(selected.output["corrected"])

        office_error = DocumentError("document_render_failed", diagnostic={
            "stage": "office_render", "reason": "renderer_failed"})
        with self.assertRaises(StepRetryPending) as caught:
            run_step(self.task_id, self.fence, "office_render:technical-solution",
                     {"stage": "office-render-test"}, lambda: (_ for _ in ()).throw(office_error))
        office_step = DocumentStep.objects.get(task_id=self.task_id, key="office_render:technical-solution")
        self.assertEqual((office_step.status, office_step.retry_count), ("retry_wait", 1))
        DocumentAttempt.objects.filter(pk=self.attempt_id).update(model_calls=4)
        finished = _finish(self.task_id, self.fence, self.attempt_id, "QUEUED", "RENDER",
                           caught.exception.code, recovery=caught.exception)
        self.assertTrue(finished)

        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "QUEUED")
        self.assertIs(self.task.checkpoint["automatic_recovery"], True)
        initial_attempt_count = self.task.attempt_count
        DocumentTask.objects.filter(pk=self.task_id).update(
            retry_after=timezone.now() - timedelta(seconds=1))
        recovered = claim_task()
        self.assertIsNotNone(recovered)
        recovered_task_id, recovered_fence, recovered_attempt_id = recovered
        self.assertEqual(recovered_task_id, self.task_id)
        self.assertEqual(recovered_fence, self.fence + 1)
        self.assertNotEqual(recovered_attempt_id, self.attempt_id)
        self.task.refresh_from_db()
        self.assertIs(self.task.checkpoint["recovery_mode"], True)
        self.assertEqual(self.task.attempt_count, initial_attempt_count)
        self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 4)
        return recovered_task_id, recovered_fence, initial_attempt_count

    def test_selected_diagram_survives_office_retry_without_replaying_failed_base(self):
        with tempfile.TemporaryDirectory() as storage, \
                patch("portal.product_documents.preflight_document_rendering",
                      return_value={"mermaid": {"status": "available"}}), \
                patch("portal.product_documents._render_one_diagram", side_effect=self.renderer):
            recovered_task_id, recovered_fence, attempt_count = self.prepare_office_retry(Path(storage))

            selected = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key + ":selected")
            selected_hash = selected.output_hash
            image_path = Path(storage) / self.target["path"]
            expected_image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
            self.assertEqual(selected.output["evidence"]["figures"][0]["imageSha256"], expected_image_sha)

            recovered_document = copy.deepcopy(self.document)
            result = self.render(recovered_document, Path(storage), recovered_task_id, recovered_fence)

            self.assertEqual((result["rendered"], result["pending_count"]), (15, 0))
            self.assertEqual(self.target_render_attempts, 2)
            self.assertEqual(len(self.repair_calls), 1)
            self.assertEqual(len(self.rendered), 15)
            self.assertEqual(hashlib.sha256(image_path.read_bytes()).hexdigest(), expected_image_sha)
            target_output = next(item for item in result["figures"] if item["id"] == self.target_id)
            self.assertEqual(target_output["image_sha256"], expected_image_sha)
            corrected = next(block for block in recovered_document["blocks"]
                             if block.get("id") == self.target_id)
            self.assertEqual(corrected["caption"], CORRECTED_TITLE)
            self.assertEqual(target_output["evidence_block_ids"],
                             selected.output["source"]["evidence_block_ids"])
            evidence_blocks = {block["id"]: block for block in recovered_document["blocks"]}
            expected_sources = list(dict.fromkeys(
                source_id for block_id in target_output["evidence_block_ids"]
                for source_id in evidence_blocks[block_id]["source_ids"]))
            self.assertEqual(corrected["source_ids"], expected_sources)

            selected.refresh_from_db()
            base = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key)
            correction = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key + ":correction")
            self.assertEqual((selected.status, selected.attempts, selected.output_hash),
                             ("completed", 1, selected_hash))
            self.assertEqual((base.status, base.attempts), ("failed", 1))
            self.assertEqual((correction.status, correction.attempts), ("completed", 1))
            self.task.refresh_from_db()
            self.assertEqual(self.task.attempt_count, attempt_count)
            self.assertEqual(sum(self.task.attempts.values_list("model_calls", flat=True)), 4)

    def test_corrupt_cached_png_is_rejected_during_recovery(self):
        with tempfile.TemporaryDirectory() as storage, \
                patch("portal.product_documents.preflight_document_rendering",
                      return_value={"mermaid": {"status": "available"}}), \
                patch("portal.product_documents._render_one_diagram", side_effect=self.renderer):
            recovered_task_id, recovered_fence, _ = self.prepare_office_retry(Path(storage))
            image_path = Path(storage) / self.target["path"]
            image_path.write_bytes(b"corrupted cached image")

            with self.assertRaises(ExecutionError):
                self.render(copy.deepcopy(self.document), Path(storage), recovered_task_id, recovered_fence)

            self.assertEqual(self.target_render_attempts, 2)
            self.assertEqual(len(self.repair_calls), 1)
            selected = DocumentStep.objects.get(task_id=self.task_id, key=self.base_key + ":selected")
            self.assertEqual(selected.status, "failed")
