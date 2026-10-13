"""Draft diagnostics stay visible without exposing render inputs or granting approval."""

import hashlib
import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_pair import _report_generation_hash
from portal.product_release import public_evidence
from portal.product_service import append_revision
from .base import PortalTestCase, json_body
from . import test_product_pair as fixtures


class PublicQualityWarningsTests(SimpleTestCase):
    def test_bounded_warning_metadata_preserves_real_counts_and_omits_private_content(self):
        evidence = {
            "kind": "draft", "private_path": "PRIVATE_RENDER_PATH",
            "draft_quality": {"quality_issue_count": 24, "quality_issue_codes": ["quantity_mismatch"],
                              "actual_characters": 40000, "minimum_characters": 50000},
            "diagram_generation": {"planned_count": 120, "rendered": 0, "pending_count": 120,
                "pending_figures": [{"figure_id": f"FIGURE_{index}", "error_code": "diagram_render_failed",
                                     "path": "PRIVATE_SOURCE", "reason": "PRIVATE_MODEL_TEXT"}
                                    for index in range(120)]},
        }
        warning = public_evidence(evidence)["quality_warnings"]
        self.assertEqual(warning["issue_count"], 24)
        self.assertEqual(warning["actual_characters"], 40000)
        self.assertEqual(warning["minimum_characters"], 50000)
        self.assertEqual(warning["figures"]["pending_count"], 120)
        self.assertEqual(warning["figures"]["rendered"], 0)
        self.assertEqual(len(warning["figures"]["pending"]), 100)
        self.assertNotIn("PRIVATE_", json.dumps(public_evidence(evidence)))


class DraftWarningApiTests(PortalTestCase):
    setUp = fixtures.PairDraftTests.setUp
    input_payload = fixtures.PairDraftTests.input_payload
    create_task = fixtures.PairDraftTests.create_task
    blueprint_payload = fixtures.PairDraftTests.blueprint_payload
    save_blueprint = fixtures.PairDraftTests.save_blueprint
    approve_blueprint = fixtures.PairDraftTests.approve_blueprint
    _task = fixtures.PairDraftTests._task
    _reviewed_pair = fixtures.PairDraftTests._reviewed_pair

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_worker.generate_for_use")
    def test_pending_diagram_retry_preserves_budget_permissions_and_saved_progress(self, model):
        task, _, _, _, _, _, _ = self._reviewed_pair(model, self.storage.name)
        artifact = task.artifacts.get(family="technical-solution")
        artifact.render_evidence.update(kind="draft", content_review="human_review_required",
            diagram_generation={"planned_count": 1,
            "rendered": 0, "pending_count": 1,
            "pending_figures": [{"figure_id": "FIGURE_1", "error_code": "diagram_render_failed"}]})
        artifact.save()
        task.state, task.stage, task.pending_action = "WAITING_REVIEW", "FINAL_REVIEW", ""
        task.attempt_count = 8
        task.save()
        endpoint = f"/api/product/tasks/{task.pk}/"
        before = (task.version, task.attempt_count, list(task.artifacts.values_list("sha256", flat=True)),
                  list(task.revisions.filter(kind="chapter").values_list("sha256", flat=True)))
        self.assertNotIn("retry", self.owner_client.get(endpoint).json()["actions"])
        response = self.owner_client.post(endpoint + "retry/", json_body(expected_version=task.version),
                                          content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "attempt_limit")
        task.refresh_from_db()
        self.assertFalse(task.checkpoint.get("repair_pending_diagrams", False))
        task.attempt_count = 7
        task.save()
        self.assertIn("retry", self.owner_client.get(endpoint).json()["actions"])
        self.assertEqual(self.other_client.post(endpoint + "retry/", json_body(expected_version=task.version),
                         content_type="application/json").status_code, 404)
        response = self.owner_client.post(endpoint + "retry/", json_body(expected_version=task.version),
                                          content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual((task.state, task.pending_action), ("QUEUED", "generate_outputs"))
        self.assertIs(task.checkpoint["repair_pending_diagrams"], True)
        self.assertEqual(task.attempt_count, 7)
        self.assertEqual(task.version, before[0] + 1)
        self.assertEqual(list(task.artifacts.values_list("sha256", flat=True)), before[2])
        self.assertEqual(list(task.revisions.filter(kind="chapter").values_list("sha256", flat=True)), before[3])
        response = self.owner_client.post(endpoint + "retry/", json_body(expected_version=task.version),
                                          content_type="application/json")
        self.assertEqual(response.status_code, 409)

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_worker.generate_for_use")
    def test_running_task_exposes_bound_warnings_and_download_without_approval(self, model):
        task, _, _, current, blueprint, _, _ = self._reviewed_pair(model, self.storage.name)
        artifact = task.artifacts.get(family="technical-solution")
        review = append_revision(task, "review", {**artifact.review.payload,
            "passed": False, "full_document_human_review_required": True,
            "issues": [{"code": "quantity_mismatch", "paragraph": "PRIVATE_BODY"}]},
            input_hash=current.sha256, blueprint_hash=blueprint.sha256, actor=self.owner,
            family=artifact.family, reason="worker_review")
        artifact.review = review
        artifact.generation_hash = _report_generation_hash(task, artifact.family, current, blueprint)
        artifact.render_evidence.update(kind="draft", content_review="human_review_required",
            draft_quality={"quality_issue_count": 1, "quality_issue_codes": ["quantity_mismatch"]},
            diagram_generation={"planned_count": 1, "rendered": 0, "pending_count": 1,
                "pending_figures": [{"figure_id": "FIGURE_1", "error_code": "diagram_render_failed",
                                     "path": "PRIVATE_RENDER_PATH"}]})
        artifact.save()
        task.refresh_from_db()
        self.assertEqual(task.state, "RUNNING")
        detail = self.owner_client.get(f"/api/product/tasks/{task.pk}/")
        self.assertEqual(detail.status_code, 200)
        warnings = detail.json()["quality_warnings"]
        technical = next(item for item in warnings if item["family"] == artifact.family)
        self.assertEqual(technical["issues"], [{"code": "quantity_mismatch"}])
        self.assertEqual(technical["figures"]["pending_count"], 1)
        outputs = self.owner_client.get(f"/api/product/tasks/{task.pk}/outputs/").json()["outputs"]
        visible = next(item for item in outputs if item["id"] == str(artifact.pk))
        self.assertTrue(visible["current"])
        self.assertTrue(visible["draft"])
        self.assertFalse(visible["approved"])
        self.assertNotIn("PRIVATE_", json.dumps(visible["quality_warnings"]))
        response = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        response.close()
        self.assertEqual(hashlib.sha256(content).hexdigest(), artifact.sha256)
        self.assertEqual(self.other_client.get(f"/api/product/outputs/{artifact.pk}/download/").status_code, 404)
        artifact.review.refresh_from_db()
        self.assertIs(artifact.review.payload["passed"], False)
        self.assertFalse(task.approvals.filter(artifact=artifact).exists())
