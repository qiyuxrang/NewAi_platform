"""PPT-only version changes with real renderer progress and immutable reports."""
import hashlib
import json
from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings

from portal.product_delivery import artifact_delivery, finish_output_delivery
from portal.product_models import DocumentArtifact, DocumentRevision
from portal.product_pair import output_current
from portal.product_release import public_presentation_plan
from portal.product_three_drafts import generate_presentation_artifact
from portal.product_worker import claim_task
from .base import PortalTestCase
from . import test_product_auto_delivery as delivery_tests


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
    PRODUCT_TECHNICAL_TARGET_CHARACTERS=60, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=60,
    PRODUCT_ENFORCE_OUTPUT_LENGTH=True, PRODUCT_OFFICE_RENDER_ENABLED=False,
    PRODUCT_COST_POLICY={"approval_ref": "isolated-ppt-workspace", "currency": "TEST", "max_task_cost": "100",
        "route_cost_caps": {"product_blueprint": "1", "product_writing": "1", "product_review": "1"}})
class PresentationWorkspaceTests(PortalTestCase):
    setUp = delivery_tests.AutomaticDeliveryTests.setUp
    queue_outputs = delivery_tests.AutomaticDeliveryTests.queue_outputs
    report = delivery_tests.AutomaticDeliveryTests.report
    synthetic_body = staticmethod(delivery_tests.AutomaticDeliveryTests.synthetic_body)

    def pair(self):
        # Reports are isolated fixture bytes. PPT export and source image handling
        # are real; this does not claim acceptance of long-form authored content.
        artifacts = [self.report(family) for family in ("technical-solution", "feasibility")]
        for artifact in artifacts:
            for figure in artifact.render_evidence["diagram_generation"]["figures"]:
                figure.update(width_mm=145, min_font_pt=15)
            artifact.save(update_fields=["render_evidence"])
            self.assertTrue(artifact_delivery(artifact)["delivered"])
        return artifacts

    def queue(self, style, version=None):
        self.task.refresh_from_db()
        return self.client.post(f"/api/product/tasks/{self.task.pk}/queue/", json.dumps({
            "expected_version": self.task.version if version is None else version,
            "action": "presentation", "presentation_style": style}), content_type="application/json")

    def test_completed_project_style_versions_preserve_report_bytes_and_stream_real_progress(self):
        reports = self.pair()
        before = list(DocumentRevision.objects.filter(task=self.task).values_list("pk", "sha256"))
        from portal.product_three_drafts import _presentation_progress
        observed = []
        def progress(*args, **kwargs):
            _presentation_progress(*args, **kwargs)
            observed.append(deepcopy(args[4] if len(args) > 4 else None))

        with patch("portal.product_worker.generate_for_use", side_effect=AssertionError("PPT does not call a model")), \
                patch("portal.product_three_drafts._presentation_progress", side_effect=progress):
            original = generate_presentation_artifact(self.task, self.fence, self.attempt,
                self.input_revision, self.blueprint)
        self.assertTrue(artifact_delivery(original)["delivered"], original.render_evidence)
        finish_output_delivery(self.task, self.fence, self.attempt)
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "COMPLETED")
        events = [event for event in observed if event]
        self.assertTrue(events)
        self.assertTrue(all(0 <= event["completed_count"] <= event["total_count"] for event in events))
        self.assertEqual(events[-1]["total_count"], len(original.render_evidence["presentation_plan"]["pages"]))
        self.assertTrue(self.task.checkpoint["presentation_plan"]["locked"])
        self.assertNotIn("asset_path", json.dumps(self.task.checkpoint["presentation_plan"]))
        version = self.task.version
        queued = self.queue("government", version)
        self.assertEqual(queued.status_code, 200, queued.content)
        self.assertEqual(queued.json()["state"], "QUEUED")
        self.assertIsNone(queued.json()["presentation_plan"])
        self.assertEqual(self.queue("minimal", version).status_code, 409)
        self.assertTrue(output_current(self.task, original))
        for artifact in [*reports, original]:
            response = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
            self.assertEqual(response.status_code, 200, response.content if not response.streaming else "")
            self.assertEqual(hashlib.sha256(b"".join(response.streaming_content)).hexdigest(), artifact.sha256)
        _, fence, attempt = claim_task()
        self.task.refresh_from_db()
        replacement = generate_presentation_artifact(self.task, fence, attempt, self.input_revision, self.blueprint)
        self.assertEqual(replacement.render_evidence["presentation_plan"]["style"], "government")
        self.assertGreater(replacement.version, original.version)
        self.assertFalse(output_current(self.task, original))
        self.assertTrue(artifact_delivery(replacement)["delivered"])
        finish_output_delivery(self.task, fence, attempt, families=["presentation"])
        self.assertEqual(before, list(DocumentRevision.objects.filter(task=self.task).values_list("pk", "sha256")))
        self.assertEqual(self.task.artifacts.filter(family__in=["technical-solution", "feasibility"]).count(), 2)
        # Returning to a previous style must produce the new current version,
        # not return an old, stale artifact from the generation cache.
        self.assertEqual(self.queue("business").status_code, 200)
        _, fence, attempt = claim_task()
        self.task.refresh_from_db()
        restored = generate_presentation_artifact(self.task, fence, attempt, self.input_revision, self.blueprint)
        self.assertEqual(restored.render_evidence["presentation_plan"]["style"], "business")
        self.assertGreater(restored.version, replacement.version)
        self.assertTrue(output_current(self.task, restored))
        listed = self.client.get(f"/api/product/tasks/{self.task.pk}/outputs/").json()["outputs"]
        versions = {row["version"]: row for row in listed if row["family"] == "presentation"}
        self.assertEqual(versions[replacement.version]["presentation_plan"]["style"], "government")
        self.assertEqual(versions[restored.version]["presentation_plan"]["style"], "business")
        self.assertTrue(versions[restored.version]["delivered"])

    def test_invalid_style_and_ppt_attempt_without_pair_do_not_change_task(self):
        self.task.state, self.task.lease_until = "COMPLETED", None
        self.task.save()
        before = (self.task.version, self.task.checkpoint, self.task.attempt_count)
        for style, status in (([], 400), ("unexpected", 400), ("government", 409)):
            response = self.queue(style)
            self.assertEqual(response.status_code, status, response.content)
            self.task.refresh_from_db()
            self.assertEqual((self.task.version, self.task.checkpoint, self.task.attempt_count), before)

    def test_public_plan_drops_renderer_paths(self):
        plan = public_presentation_plan({"style": "business", "path": "private/secret", "sources": [
            {"family": "feasibility", "version": 1, "asset_path": "secret"}], "pages": [
            {"page": 1, "title": "结论", "asset_path": "secret", "source_refs": ["feasibility:P1"]}]})
        self.assertNotIn("secret", json.dumps(plan))
        self.assertEqual(plan["pages"][0]["title"], "结论")

    def test_incomplete_reports_cannot_replace_the_report_recovery_action_with_ppt(self):
        for family in ("technical-solution", "feasibility"):
            self.report(family, size=30)
        finish_output_delivery(self.task, self.fence, self.attempt)
        self.task.refresh_from_db()
        before = (self.task.version, self.task.pending_action, self.task.checkpoint)
        response = self.queue("government")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "source_reports_incomplete")
        self.task.refresh_from_db()
        self.assertEqual((self.task.version, self.task.pending_action, self.task.checkpoint), before)
        detail = self.client.get(f"/api/product/tasks/{self.task.pk}/").json()
        self.assertNotIn("queue_presentation", detail["actions"])
        self.assertIn("retry", detail["actions"])

    def test_incomplete_diagrams_retry_repairs_saved_files_without_second_approval(self):
        self.report(diagrams_pending=True)
        finish_output_delivery(self.task, self.fence, self.attempt, families=["technical-solution"])
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "delivery_incomplete"))
        response = self.client.post(f"/api/product/tasks/{self.task.pk}/retry/",
            json.dumps({"expected_version": self.task.version}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertTrue(self.task.checkpoint["repair_pending_diagrams"])
        self.assertEqual(self.task.pending_action, "generate_outputs")
