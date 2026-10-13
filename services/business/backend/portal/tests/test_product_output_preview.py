import hashlib
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings
import fitz

from portal.product_models import DocumentArtifact, DocumentTask
from portal.product_pair import _report_generation_hash, pair_snapshot, save_report_content
from portal.product_service import append_revision, digest
from portal.product_storage import verified_artifact
from .base import PortalTestCase
from . import test_product_api as api_fixture


class ProductDraftPreviewTests(PortalTestCase):
    input_payload = api_fixture.ProductApiTests.input_payload
    create_task = api_fixture.ProductApiTests.create_task
    blueprint_payload = api_fixture.ProductApiTests.blueprint_payload
    save_blueprint = api_fixture.ProductApiTests.save_blueprint
    approve_blueprint = api_fixture.ProductApiTests.approve_blueprint

    def setUp(self):
        from portal.product_worker import _ensure_content_review, _finish, claim_task
        api_fixture.ProductApiTests.setUp(self)
        created = self.create_task()
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True):
            self.approve_blueprint(self.save_blueprint(created))
        self.task = DocumentTask.objects.get(pk=created["id"])
        self.input = self.task.revisions.get(kind="input", version=self.task.input_version)
        self.blueprint = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        task_id, fence, attempt_id = claim_task()
        self.artifacts = {}
        for index, family in enumerate(("technical-solution", "feasibility"), 1):
            text = ("技术方案合成正文，仅用于预览权限与文件校验。" if family == "technical-solution"
                    else "可研合成正文，仅用于来源过期与预览边界校验。")
            chapter = append_revision(self.task, "chapter", {"chapter_id": "overview", "title": "项目概述",
                            "paragraphs": [text], "source_ids": ["1"]},
                            input_hash=self.input.sha256, blueprint_hash=self.blueprint.sha256,
                            actor=self.owner, family=family)
            with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True), patch("portal.product_worker.generate_for_use",
                    return_value={"content": '{"passed":true,"issues":[]}'}) as model:
                review = _ensure_content_review(self.task, fence, attempt_id, self.input, self.blueprint, [chapter], family)
                model.assert_not_called()
            self.assertTrue(review.payload["program_checks_complete"])
            self.assertFalse(review.payload["passed"])
            self.assertEqual(review.payload["model_review"]["status"], "not_run")
            self.assertEqual(review.payload["model_review"]["scope"], "program_only")
            report = save_report_content(self.task, family, {
                "blocks": [{"id": "p1", "type": "paragraph", "text": family, "source_ids": ["SINPUT"]}],
                "pending": []}, input_hash=self.input.sha256, blueprint_hash=self.blueprint.sha256, actor=self.owner)
            source = self.file(f"{self.task.pk}/artifacts/{family}/draft.docx", b"PK-final-reviewed-" + family.encode())
            preview = self.preview_files(family)
            preview["docx_sha256"] = source["sha256"]
            artifact = DocumentArtifact.objects.create(task=self.task, family=family, version=index,
                **source, review=review, input_hash=self.input.sha256, blueprint_hash=self.blueprint.sha256, template_hash="a" * 64,
                generation_hash=_report_generation_hash(self.task, family, self.input, self.blueprint),
                render_evidence={"kind": "draft", "status": "draft_unverified", "verified": False,
                    "visual_review": "not_run", "report_id": str(report.pk), "word_field_cache": {
                        "status": "completed", "input_sha256": "e" * 64,
                        "output_sha256": source["sha256"], "preview": preview}})
            self.artifacts[family] = artifact
        _finish(self.task.pk, fence, attempt_id, "WAITING_REVIEW", "FINAL_REVIEW")
        self.task.refresh_from_db()
        pair = pair_snapshot(self.task)
        source = self.file(f"{self.task.pk}/artifacts/presentation/draft.pptx", b"PK-editable-presentation")
        preview = self.preview_files("presentation")
        preview.update(pptx_sha256=source["sha256"], generation_sha256=source["sha256"], generation=source)
        self.artifacts["presentation"] = DocumentArtifact.objects.create(task=self.task, family="presentation", version=3,
            **source, input_hash=self.input.sha256, blueprint_hash=self.blueprint.sha256, template_hash="b" * 64,
            generation_hash=digest({"kind": "presentation", "pair": pair["sha256"]}),
            render_evidence={"kind": "draft", "status": "draft_unverified", "verified": False,
                             "visual_review": "not_run", "pair_hash": pair["sha256"], "office_render_evidence": preview})

    def file(self, relative, content):
        target = Path(self.storage.name) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}

    def preview_files(self, family):
        prefix = f"{self.task.pk}/artifacts/{family}/word-field-refresh"
        pdf = fitz.open()
        pdf.new_page(width=120, height=100).insert_text((10, 40), family)
        png = pdf[0].get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).tobytes("png")
        pdf_bytes = pdf.tobytes()
        pdf.close()
        return {"status": "rendered", "verified": False, "visual_review": "not_run", "page_count": 1,
                "pdf": self.file(prefix + "/document.pdf", pdf_bytes),
                "pages": [{"page": 1, **self.file(prefix + "/page-001.png", png)}]}

    def url(self, artifact, query="?page=1"):
        return f"/api/product/outputs/{artifact.pk}/preview/{query}"

    def rows(self):
        response = self.owner_client.get(f"/api/product/tasks/{self.task.pk}/outputs/")
        self.assertEqual(response.status_code, 200, response.content)
        return {item["family"]: item for item in response.json()["outputs"]}

    def test_three_families_serve_hashed_png_for_owner_and_assigned_reviewer(self):
        rows = self.rows()
        for family, artifact in self.artifacts.items():
            with self.subTest(family=family):
                self.assertTrue(rows[family]["has_preview"])
                self.assertEqual(rows[family]["page_count"], 1)
                self.assertEqual(rows[family]["preview_url"], self.url(artifact, ""))
                preview = (artifact.render_evidence["office_render_evidence"] if family == "presentation"
                           else artifact.render_evidence["word_field_cache"]["preview"])
                page = preview["pages"][0]
                expected = (Path(self.storage.name) / page["path"]).read_bytes()
                before, approvals = artifact.render_evidence, self.task.approvals.count()
                for client in (self.owner_client, self.reviewer_client):
                    response = client.get(self.url(artifact))
                    self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
                    actual = b"".join(response.streaming_content)
                    self.assertEqual(actual, expected)
                    self.assertEqual(hashlib.sha256(actual).hexdigest(), page["sha256"])
                    self.assertEqual(response["X-Product-Page-Sha256"], page["sha256"])
                    self.assertEqual(response["X-Product-Artifact-Sha256"], artifact.sha256)
                    self.assertEqual(response["Content-Type"], "image/png")
                    self.assertIn("no-store", response["Cache-Control"])
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                artifact.refresh_from_db()
                self.assertEqual(artifact.render_evidence, before)
                self.assertNotIn("page_views", artifact.render_evidence)
                self.assertFalse(artifact.render_evidence["verified"])
                self.assertEqual(self.task.approvals.count(), approvals)
        serialized = str(rows)
        self.assertNotIn(self.storage.name, serialized)
        self.assertNotIn("word-field-refresh", serialized)
        self.assertNotIn("page-001.png", serialized)

    def test_foreign_user_or_revoked_reviewer_and_source_permissions_cannot_preview(self):
        artifact = self.artifacts["technical-solution"]
        self.assertEqual(self.other_client.get(self.url(artifact)).status_code, 404)
        with override_settings(PRODUCT_REVIEWER_IDS=()):
            self.assertEqual(self.reviewer_client.get(self.url(artifact)).status_code, 404)
        with patch("portal.product_outputs.input_authorized", return_value=False):
            response = self.owner_client.get(self.url(artifact))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "source_permission_changed")

    def test_changed_input_or_blueprint_blocks_all_preview_and_history_bypass(self):
        for kind in ("input", "blueprint"):
            with self.subTest(kind=kind):
                old = self.input if kind == "input" else self.blueprint
                newer = append_revision(self.task, kind, {**old.payload, "preview_test_revision": kind}, actor=self.owner)
                setattr(self.task, kind + "_version", newer.version)
                self.task.save(update_fields=[kind + "_version"])
                for artifact in self.artifacts.values():
                    response = self.owner_client.get(self.url(artifact, "?page=1&history=1"))
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()["code"], "stale_output")
                self.assertTrue(all(not row["has_preview"] and row["page_count"] == 0 for row in self.rows().values()))
                setattr(self.task, kind + "_version", old.version)
                self.task.save(update_fields=[kind + "_version"])

    def test_changed_report_invalidates_its_word_and_dependent_presentation(self):
        save_report_content(self.task, "technical-solution", {"blocks": [], "pending": []},
                            input_hash=self.input.sha256, blueprint_hash=self.blueprint.sha256, actor=self.owner)
        for family in ("technical-solution", "presentation"):
            response = self.owner_client.get(self.url(self.artifacts[family]))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], "stale_output")
        response = self.owner_client.get(self.url(self.artifacts["feasibility"]))
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)

    def test_missing_canonical_evidence_and_candidates_are_not_draft_previews(self):
        for family, artifact in self.artifacts.items():
            with self.subTest(family=family):
                evidence = dict(artifact.render_evidence)
                evidence.pop("word_field_cache", None)
                evidence.pop("office_render_evidence", None)
                artifact.render_evidence = evidence
                artifact.save(update_fields=["render_evidence"])
                response = self.owner_client.get(self.url(artifact))
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "preview_unavailable")
                row = self.rows()[family]
                self.assertFalse(row["has_preview"])
                self.assertEqual(row["page_count"], 0)
                self.assertIsNone(row["preview_url"])
        artifact = self.artifacts["feasibility"]
        artifact.render_evidence = {**artifact.render_evidence, "kind": "candidate"}
        artifact.save(update_fields=["render_evidence"])
        self.assertEqual(self.owner_client.get(self.url(artifact)).json()["code"], "preview_unavailable")

    def test_source_and_page_tampering_never_serves_preview_bytes(self):
        for number, family in enumerate(("technical-solution", "presentation")):
            artifact = self.artifacts[family]
            preview = (artifact.render_evidence["office_render_evidence"] if family == "presentation"
                       else artifact.render_evidence["word_field_cache"]["preview"])
            path = Path(self.storage.name) / (artifact.path if number == 0 else preview["pages"][0]["path"])
            original = path.read_bytes()
            try:
                path.write_bytes(b"tampered")
                response = self.owner_client.get(self.url(artifact))
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "artifact_hash_mismatch")
                self.assertFalse(response.streaming)
            finally:
                path.write_bytes(original)

    def test_snapshot_hash_mismatch_and_unsafe_page_records_are_unavailable(self):
        artifact = self.artifacts["technical-solution"]
        original = artifact.render_evidence
        import copy
        for failure in ("pre_refresh_sha", "path", "sequence", "count"):
            with self.subTest(failure=failure):
                evidence = copy.deepcopy(original)
                preview = evidence["word_field_cache"]["preview"]
                if failure == "pre_refresh_sha":
                    preview["docx_sha256"] = evidence["word_field_cache"]["input_sha256"]
                elif failure == "path":
                    preview["pages"][0]["path"] = "../outside.png"
                elif failure == "sequence":
                    preview["pages"][0]["page"] = True
                else:
                    preview["page_count"] = 2
                artifact.render_evidence = evidence
                artifact.save(update_fields=["render_evidence"])
                self.assertEqual(self.owner_client.get(self.url(artifact)).json()["code"], "preview_unavailable")

    def test_invalid_page_numbers_are_rejected(self):
        artifact = self.artifacts["presentation"]
        for page in ("0", "2", "-1", "invalid", "１", "1" * 20):
            with self.subTest(page=page):
                response = self.owner_client.get(self.url(artifact, "?page=" + page))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_page")

    def test_permissions_and_current_generation_are_rechecked_after_file_validation(self):
        artifact = self.artifacts["feasibility"]
        def transfer(item):
            target = verified_artifact(item)
            DocumentTask.objects.filter(pk=self.task.pk).update(owner=self.other)
            return target
        with patch("portal.product_outputs.verified_artifact", side_effect=transfer):
            response = self.owner_client.get(self.url(artifact))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.streaming)

    def test_source_authorization_revoked_during_validation_blocks_response(self):
        artifact = self.artifacts["presentation"]
        with patch("portal.product_outputs.input_authorized", side_effect=[True, False]):
            response = self.owner_client.get(self.url(artifact))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "source_permission_changed")
        self.assertFalse(response.streaming)

    def test_input_changed_during_validation_blocks_response(self):
        artifact = self.artifacts["technical-solution"]
        def change_input(item):
            target = verified_artifact(item)
            newer = append_revision(self.task, "input", {**self.input.payload, "requirements": "Changed during verification"}, actor=self.owner)
            self.task.input_version = newer.version
            self.task.save(update_fields=["input_version"])
            return target
        with patch("portal.product_outputs.verified_artifact", side_effect=change_input):
            response = self.owner_client.get(self.url(artifact))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_output")
        self.assertFalse(response.streaming)
