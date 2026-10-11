import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings

from portal.product_models import DocumentArtifact
from portal.product_pair import _report_generation_hash, output_current, pair_snapshot, report_current, save_report_content
from portal.product_service import ProductError, append_revision, digest
from portal.product_storage import verified_artifact
from .test_product_api import ProductApiTests
from .base import PortalTestCase


def report_diagram_evidence(document, artifact_path):
    """Provide real PNG files for mocked report-render lifecycle tests."""
    from PIL import Image
    from portal.product_diagrams import diagram_contract_hash
    figures = []
    for block in document["blocks"]:
        if block.get("type") != "figure":
            continue
        path = artifact_path.parent / block["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 24), (25, 80, 140)).save(path, format="PNG")
        figures.append({"id": block["id"], "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_sha256": hashlib.sha256(b'flowchart LR; A[fixture] --> B[pending]').hexdigest(),
                        "evidence_block_ids": [item["id"] for item in document["blocks"]
                                               if item.get("type") == "paragraph"][:1]})
    return {"contract_sha256": diagram_contract_hash(), "source_scope": "authored_chapter_blocks",
            "semantic_review": "human_review_required", "figures": figures}


class PairDraftTests(PortalTestCase):
    setUp = ProductApiTests.setUp
    input_payload = ProductApiTests.input_payload
    create_task = ProductApiTests.create_task
    blueprint_payload = ProductApiTests.blueprint_payload
    save_blueprint = ProductApiTests.save_blueprint
    approve_blueprint = ProductApiTests.approve_blueprint

    def _reviewed_pair(self, model, directory, *, figures=False):
        from portal.product_worker import _ensure_content_review, claim_task
        task = self._task(self.save_blueprint(self.create_task()))
        self.approve_blueprint(self.owner_client.get(f"/api/product/tasks/{task.pk}/").json())
        task.refresh_from_db()
        _, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        current = task.revisions.get(kind="input", version=task.input_version)
        blueprint = task.revisions.get(kind="blueprint", version=task.blueprint_version)
        reports, images = [], []
        for version, family in enumerate(("technical-solution", "feasibility"), 1):
            text = "设计条件仍待确认。"
            chapter = append_revision(task, "chapter", {"chapter_id": "overview", "title": "项目概述",
                "paragraphs": [text], "source_ids": ["1"]}, input_hash=current.sha256,
                blueprint_hash=blueprint.sha256, actor=self.owner, family=family)
            blocks = [{"id": "body", "type": "paragraph", "text": text, "source_ids": ["SINPUT"]}]
            evidence = {}
            path = Path(directory) / str(task.pk) / "artifacts" / family / "draft.docx"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"reviewed draft")
            if figures:
                image = path.parent / "assets" / "diagram.png"
                images.append(image)
                blocks.append({"id": "figure", "type": "figure", "path": "assets/diagram.png",
                               "caption": "待确认流程", "source_ids": ["SINPUT"]})
                evidence["diagram_generation"] = report_diagram_evidence({"blocks": blocks}, path)
            report = save_report_content(task, family, {"blocks": blocks, "pending": []},
                input_hash=current.sha256, blueprint_hash=blueprint.sha256, actor=self.owner)
            review = _ensure_content_review(task, fence, attempt_id, current, blueprint, [chapter], family)
            DocumentArtifact.objects.create(task=task, family=family, version=version,
                path=path.relative_to(directory).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                input_hash=current.sha256, blueprint_hash=blueprint.sha256, template_hash="a" * 64,
                generation_hash=_report_generation_hash(task, family, current, blueprint), review=review,
                render_evidence={**evidence, "report_id": str(report.pk)})
            reports.append(report)
        return task, fence, attempt_id, current, blueprint, reports, images

    def _cached_presentation(self, task, pair, directory):
        from portal.product_presentation import presentation_renderer_hash
        path = Path(directory) / str(task.pk) / "artifacts" / "cached.pptx"
        path.write_bytes(b"cached presentation")
        return DocumentArtifact.objects.create(task=task, family="presentation", version=3,
            path=path.relative_to(directory).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            input_hash=pair["input_hash"], blueprint_hash=pair["blueprint_hash"], template_hash="a" * 64,
            generation_hash=digest({"kind": "presentation", "pair": pair["sha256"], "title": task.title,
                                    "renderer": presentation_renderer_hash()}),
            render_evidence={"pair_hash": pair["sha256"]})

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_presentation.render_presentation_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_report_payload_change_rejects_current_pair_and_cached_presentation(self, model, render):
        from portal.product_three_drafts import generate_presentation_artifact
        with tempfile.TemporaryDirectory() as directory, override_settings(PRODUCT_STORAGE_ROOT=directory):
            task, fence, attempt, current, blueprint, reports, _ = self._reviewed_pair(model, directory)
            pair = pair_snapshot(task)
            cached = self._cached_presentation(task, pair, directory)
            self.assertTrue(report_current(task, reports[0]))
            self.assertTrue(output_current(task, cached))
            self.assertEqual(generate_presentation_artifact(task, fence, attempt, current, blueprint).pk, cached.pk)
            original_hash = reports[0].sha256
            changed = {**reports[0].payload, "blocks": [{**reports[0].payload["blocks"][0], "text": "未经复核的来源内容。"}]}
            type(reports[0]).objects.filter(pk=reports[0].pk).update(payload=changed)
            reports[0].refresh_from_db()
            self.assertEqual(reports[0].sha256, original_hash)
            self.assertFalse(report_current(task, reports[0]))
            self.assertFalse(output_current(task, cached))
            with self.assertRaises(ProductError) as error:
                generate_presentation_artifact(task, fence, attempt, current, blueprint)
            self.assertEqual(error.exception.code, "stale_pair")
            render.assert_not_called()

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_presentation.render_presentation_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_report_image_change_rejects_current_pair_and_cached_presentation(self, model, render):
        from portal.product_three_drafts import generate_presentation_artifact
        with tempfile.TemporaryDirectory() as directory, override_settings(PRODUCT_STORAGE_ROOT=directory):
            task, fence, attempt, current, blueprint, reports, images = self._reviewed_pair(model, directory, figures=True)
            pair = pair_snapshot(task)
            cached = self._cached_presentation(task, pair, directory)
            self.assertTrue(report_current(task, reports[0]))
            self.assertTrue(output_current(task, cached))
            self.assertEqual(generate_presentation_artifact(task, fence, attempt, current, blueprint).pk, cached.pk)
            images[0].write_bytes(b"changed image bytes")
            self.assertFalse(report_current(task, reports[0]))
            self.assertFalse(output_current(task, cached))
            with self.assertRaises(ProductError) as error:
                generate_presentation_artifact(task, fence, attempt, current, blueprint)
            self.assertEqual(error.exception.code, "stale_pair")
            render.assert_not_called()

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_worker.generate_for_use")
    def test_report_versions_are_separate_and_pair_detects_changed_input(self, model):
        from portal.product_worker import _ensure_content_review, claim_task
        created = self.create_task()
        task = self._task(self.save_blueprint(created))
        self.approve_blueprint(self.owner_client.get(f"/api/product/tasks/{task.pk}/").json())
        task.refresh_from_db()
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        input_revision = task.revisions.get(kind="input", version=task.input_version)
        blueprint = task.revisions.get(kind="blueprint", version=task.blueprint_version)
        reports = []
        for version, (family, text, pending_id) in enumerate((("technical-solution", "技术路线", "P1"), ("feasibility", "条件评估", "P2")), 1):
            chapter = append_revision(task, "chapter", {"chapter_id": "overview", "title": "项目概述", "paragraphs": [text], "source_ids": ["1"]},
                                      input_hash=input_revision.sha256, blueprint_hash=blueprint.sha256,
                                      actor=self.owner, family=family, reason="test_lineage")
            report = save_report_content(task, family, {"blocks": [{"id": "same", "text": text, "source_ids": ["SINPUT"]}], "pending": [{"id": pending_id, "text": "同一待确认事项"}]}, input_hash=input_revision.sha256, blueprint_hash=blueprint.sha256, actor=self.owner)
            review = _ensure_content_review(task, fence, attempt_id, input_revision, blueprint, [chapter], family)
            generation_hash = _report_generation_hash(task, family, input_revision, blueprint)
            DocumentArtifact.objects.create(task=task, family=family, version=version, path=f"legacy/{family}.docx",
                sha256=str(version) * 64, input_hash=input_revision.sha256, blueprint_hash=blueprint.sha256,
                template_hash="a" * 64, generation_hash=generation_hash, review=review, render_evidence={"report_id": str(report.pk)})
            reports.append(report)
        first, second = reports
        snapshot = pair_snapshot(task)
        self.assertEqual({block["ref"] for block in snapshot["blocks"]}, {"technical-solution:same", "feasibility:same"})
        self.assertTrue(all(source["id"] and source["sha256"] and source["created_at"] for source in snapshot["sources"]))
        self.assertTrue(all("approval_id" not in source for source in snapshot["sources"]))
        self.assertEqual(snapshot["pending"], [{"text": "同一待确认事项",
                                                "refs": ["technical-solution:P1", "feasibility:P2"],
                                                "families": ["technical-solution", "feasibility"]}])
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(model.call_count, 2)
        later = append_revision(task, "input", {**input_revision.payload, "requirements": "已更改"}, actor=self.owner)
        task.input_version = later.version
        task.save(update_fields=["input_version"])
        with self.assertRaises(ProductError):
            pair_snapshot(task)

    def test_old_pair_without_complete_real_review_is_rejected(self):
        created = self.create_task()
        task = self._task(self.save_blueprint(created))
        current = task.revisions.get(kind="input", version=task.input_version)
        blueprint = task.revisions.get(kind="blueprint", version=task.blueprint_version)
        for version, family in enumerate(("technical-solution", "feasibility"), 1):
            append_revision(task, "chapter", {"chapter_id": "overview", "title": "项目概述",
                "paragraphs": ["设计条件仍待确认。"], "source_ids": ["1"]},
                input_hash=current.sha256, blueprint_hash=blueprint.sha256, family=family)
            report = save_report_content(task, family, {"blocks": [], "pending": []},
                input_hash=current.sha256, blueprint_hash=blueprint.sha256, actor=self.owner)
            DocumentArtifact.objects.create(task=task, family=family, version=version,
                path=f"legacy/{family}.docx", sha256="a" * 64, input_hash=current.sha256,
                blueprint_hash=blueprint.sha256, generation_hash=_report_generation_hash(task, family, current, blueprint),
                render_evidence={"report_id": str(report.pk)})
        with self.assertRaises(ProductError) as error:
            pair_snapshot(task)
        self.assertEqual(error.exception.code, "stale_pair")

    def test_current_download_rejects_stale_and_foreign_access(self):
        created = self.create_task()
        saved = self.save_blueprint(created)
        self.approve_blueprint(saved)
        task = self._task(created)
        current = task.revisions.get(kind="input", version=task.input_version)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRODUCT_STORAGE_ROOT=directory):
            path = Path(directory) / str(task.pk) / "artifacts" / "test.docx"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"draft")
            report = save_report_content(task, "feasibility", {"blocks": [], "pending": []}, input_hash=current.sha256, blueprint_hash=task.revisions.get(kind="blueprint", version=task.blueprint_version).sha256, actor=self.owner)
            artifact = DocumentArtifact.objects.create(task=task, version=1, family="feasibility", path=path.relative_to(directory).as_posix(), sha256=hashlib.sha256(b"draft").hexdigest(), input_hash=current.sha256, blueprint_hash=report.blueprint_hash, template_hash="a" * 64, render_evidence={"report_id": str(report.pk)})
            url = f"/api/product/outputs/{artifact.pk}/download/"
            self.assertEqual(self.other_client.get(url).status_code, 404)
            self.assertEqual(self.owner_client.get(url).status_code, 409)
            response = self.owner_client.get(url + "?history=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["X-Product-Artifact-Current"], "false")
            for closer in response._resource_closers:
                closer()
            response._resource_closers.clear()
            later = append_revision(task, "input", {**current.payload, "requirements": "已更改"}, actor=self.owner)
            task.input_version = later.version
            task.save(update_fields=["input_version"])
            self.assertEqual(self.owner_client.get(url).status_code, 409)
            self.assertTrue(verified_artifact(artifact).is_file())

    def test_technical_output_download_uses_candidate_fallback_until_approved(self):
        created = self.create_task()
        task = self._task(created)
        current = task.revisions.get(kind="input", version=task.input_version)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRODUCT_STORAGE_ROOT=directory):
            final_path = Path(directory) / str(task.pk) / "artifacts" / "candidate.docx"
            draft_path = Path(directory) / str(task.pk) / "artifacts" / "draft.docx"
            final_path.parent.mkdir(parents=True)
            final_content = b"UNAPPROVED_CANDIDATE"
            draft_content = b"SAFE_DRAFT"
            final_path.write_bytes(final_content)
            draft_path.write_bytes(draft_content)
            artifact = DocumentArtifact.objects.create(
                task=task,
                family="technical-solution",
                version=1,
                path=final_path.relative_to(directory).as_posix(),
                sha256=hashlib.sha256(final_content).hexdigest(),
                input_hash=current.sha256,
                blueprint_hash="b" * 64,
                template_hash="t" * 64,
                render_evidence={
                    "kind": "candidate",
                    "draft_fallback": {
                        "path": draft_path.relative_to(directory).as_posix(),
                        "sha256": hashlib.sha256(draft_content).hexdigest(),
                    },
                },
            )

            response = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/?history=1")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), draft_content)

    def _task(self, created):
        from portal.product_models import DocumentTask
        return DocumentTask.objects.get(pk=created["id"])
