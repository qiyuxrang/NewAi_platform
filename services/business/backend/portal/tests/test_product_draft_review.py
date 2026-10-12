"""Draft generation keeps findings and downloadable files without approving content."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.test import override_settings

from portal.model_gateway import GatewayError
from portal.product_models import DocumentApproval, DocumentArtifact, DocumentTask
from portal.product_service import append_revision
from portal.product_worker import ExecutionError, _content_review_current, _formal_paragraph_guard, run_once
from .base import PortalTestCase
from . import test_product_three_drafts as fixtures
from .test_product_pair import report_diagram_evidence


class DraftReviewTests(PortalTestCase):
    setUp = fixtures.ThreeDraftFlowTests.setUp
    input_payload = fixtures.ThreeDraftFlowTests.input_payload
    create_task = fixtures.ThreeDraftFlowTests.create_task
    blueprint_payload = fixtures.ThreeDraftFlowTests.blueprint_payload
    save_blueprint = fixtures.ThreeDraftFlowTests.save_blueprint
    approve_blueprint = fixtures.ThreeDraftFlowTests.approve_blueprint

    @patch("portal.product_three_drafts.render_report_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_technical_draft_is_downloadable_before_feasibility_generation_fails(self, model, renderer):
        paragraphs = [
            "编制人员检查目录、来源、正文和附件，保留待确认事项。",
            "实施流程安排资料收集、范围确认、责任落实和异常处置。",
            "验收人员按批准目录逐项核查内容，并登记需补充的项目依据。",
            "文档版本记录每次修改的来源、原因与审核意见，供项目方确认。",
            "资料收集由编制人员执行，审核由项目方确认，并记录异常处理。",
        ]
        artifact_bytes = b"technical-report-before-feasibility"
        observed = {}

        def reply(*args):
            request = json.loads(args[2][1]["content"])
            if request["family"] == "feasibility" and request["action"] == "chapter":
                artifact = DocumentArtifact.objects.get(task=observed["task"], family="technical-solution")
                outputs = self.owner_client.get(f"/api/product/tasks/{artifact.task_id}/outputs/")
                self.assertEqual(outputs.status_code, 200)
                current = [item for item in outputs.json()["outputs"] if item["family"] == "technical-solution"]
                self.assertEqual(len(current), 1)
                self.assertTrue(current[0]["current"])
                self.assertEqual(current[0]["sha256"], artifact.sha256)
                report_revision = artifact.task.revisions.get(pk=artifact.render_evidence["report_id"])
                self.assertEqual(current[0]["content_sha256"], report_revision.sha256)
                download = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/")
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download["X-Product-Artifact-Current"], "true")
                content = b"".join(download.streaming_content)
                download.close()
                self.assertEqual(hashlib.sha256(content).hexdigest(), artifact.sha256)
                self.assertEqual(content, artifact_bytes)
                observed["technical_was_downloadable"] = True
                raise GatewayError("timeout")
            if request["action"] == "chapter":
                value = {"chapter_id": "overview", "title": "项目概述", "paragraphs": paragraphs, "source_ids": ["1"]}
            else:
                self.assertEqual(request["action"], "independent_review")
                value = {"passed": True, "issues": []}
            return {"content": json.dumps(value)}

        def report(task, input_revision, blueprint, chapters, family, **options):
            self.assertEqual(family, "technical-solution")
            path = Path(self.storage.name) / str(task.pk) / "technical-solution.docx"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact_bytes)
            return {"path": path.relative_to(self.storage.name).as_posix(),
                    "sha256": hashlib.sha256(artifact_bytes).hexdigest(), "template_hash": "b" * 64,
                    "render_evidence": {"status": "draft_unverified",
                        "diagram_generation": report_diagram_evidence(options["document"], path)}}

        model.side_effect = reply
        renderer.side_effect = report
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=100,
                               PRODUCT_FEASIBILITY_TARGET_CHARACTERS=100, PRODUCT_ENFORCE_OUTPUT_LENGTH=True):
            task = self.create_task(reviewer=False)
            approved = self.approve_blueprint(self.save_blueprint(task))["task"]
            record = DocumentTask.objects.get(pk=approved["id"])
            observed["task"] = record
            record.checkpoint["output_families"] = ["technical-solution", "feasibility"]
            record.save(update_fields=["checkpoint"])

            self.assertTrue(run_once())
            record.refresh_from_db()
            self.assertEqual((record.state, record.error_code), ("QUEUED", "step_retry_pending"))
            self.assertEqual(record.checkpoint["last_failure"]["cause_code"], "timeout")
            self.assertEqual(model.call_count, 3)
            self.assertTrue(observed["technical_was_downloadable"])
            renderer.assert_called_once()
            self.assertEqual(set(record.artifacts.values_list("family", flat=True)), {"technical-solution"})
            self.assertFalse(record.artifacts.filter(family="presentation").exists())
            artifact = record.artifacts.get(family="technical-solution")
            self.assertEqual(artifact.review.payload["model_review"]["status"], "passed")
            outputs = self.owner_client.get(f"/api/product/tasks/{record.pk}/outputs/").json()["outputs"]
            self.assertEqual(len(outputs), 1)
            self.assertTrue(outputs[0]["current"])
            report_revision = record.revisions.get(pk=artifact.render_evidence["report_id"])
            self.assertEqual(outputs[0]["content_sha256"], report_revision.sha256)
            download = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/")
            self.assertEqual(download.status_code, 200)
            content = b"".join(download.streaming_content)
            download.close()
            self.assertEqual(hashlib.sha256(content).hexdigest(), artifact.sha256)

    @patch("portal.product_three_drafts.render_report_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_diagram_only_warning_keeps_real_review_and_current_artifact_on_resume(self, model, renderer):
        from portal.product_three_drafts import generate_report_drafts
        from portal.product_worker import _ensure_content_review, claim_task, current_chapters
        from portal.product_pair import report_current
        paragraphs = ["编制人员检查目录、来源、正文和附件，保留待确认事项。",
                      "实施流程安排资料收集、范围确认、责任落实和异常处置。",
                      "验收人员按批准目录逐项核查内容，并登记需补充的项目依据。",
                      "文档版本记录每次修改的来源、原因与审核意见，供项目方确认。",
                      "资料收集由编制人员执行，审核由项目方确认，并记录异常处理。"]
        def reply(*args):
            request = json.loads(args[2][1]["content"])
            result = ({"chapter_id": "overview", "title": "项目概述", "paragraphs": paragraphs, "source_ids": ["1"]}
                      if request["action"] == "chapter" else {"passed": True, "issues": []})
            return {"content": json.dumps(result)}
        def report(task, input_revision, blueprint, chapters, family, **options):
            path = Path(self.storage.name) / str(task.pk) / (family + ".docx")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"pending-diagram-report")
            diagrams = report_diagram_evidence(options["document"], path)
            diagrams.update(quality_issue_count=1, quality_issues=[{"code": "unsupported_project_status",
                "figure_id": "DIAGRAM_01_FIGURE", "field": "title", "claim": "现有系统"}])
            return {"path": path.relative_to(self.storage.name).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "template_hash": "b" * 64, "render_evidence": {"diagram_generation": diagrams}}
        model.side_effect, renderer.side_effect = reply, report
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=100,
                               PRODUCT_FEASIBILITY_TARGET_CHARACTERS=100, PRODUCT_ENFORCE_OUTPUT_LENGTH=True):
            approved = self.approve_blueprint(self.save_blueprint(self.create_task(reviewer=False)))["task"]
            task = DocumentTask.objects.get(pk=approved["id"])
            task.checkpoint["output_families"] = ["technical-solution", "feasibility"]
            task.save(update_fields=["checkpoint"])
            self.assertTrue(run_once())
            task.refresh_from_db()
            self.assertEqual(task.state, "WAITING_REVIEW")
            self.assertEqual(model.call_count, 4)
            current_input = task.revisions.get(kind="input", version=task.input_version)
            blueprint = task.revisions.get(kind="blueprint", version=task.blueprint_version)
            artifact = task.artifacts.get(family="technical-solution")
            self.assertFalse(artifact.review.payload["passed"])
            self.assertTrue(artifact.review.payload["full_document_human_review_required"])
            self.assertEqual(artifact.review.payload["model_review"]["status"], "passed")
            task.state, task.pending_action = "QUEUED", "generate_outputs"
            task.save(update_fields=["state", "pending_action"])
            _, fence, attempt_id = claim_task()
            task.refresh_from_db()
            chapters = list(current_chapters(task, current_input.sha256, blueprint.sha256).values())
            review = _ensure_content_review(task, fence, attempt_id, current_input, blueprint, chapters)
            self.assertEqual(review.pk, artifact.review_id)
            generate_report_drafts(task, fence, attempt_id, current_input, blueprint)
            self.assertEqual(model.call_count, 4)
            self.assertEqual(renderer.call_count, 2)
            report_revision = task.revisions.get(pk=artifact.render_evidence["report_id"])
            self.assertTrue(report_current(task, report_revision))

    @patch("portal.product_presentation.render_presentation_draft")
    @patch("portal.product_three_drafts.render_report_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_findings_leave_current_downloadable_drafts_and_real_review_evidence(self, model, report_renderer, ppt_renderer):
        paragraphs = [
            "项目交付100份文档，扫描1000页。项目总投资140000元仍须核对依据。",
            "编制人员分别检查目录、来源、正文和附件，保留待确认事项。",
            "实施流程安排资料收集、范围确认、责任落实和异常处置。",
            "验收人员按批准目录逐项核查内容，并登记需补充的项目依据。",
            "文档版本记录每次修改的来源、原因与审核意见，供项目方确认。",
        ]
        finding = "正文的数量用途仍需人工核对"

        def reply(*args):
            request = json.loads(args[2][1]["content"])
            if request["action"] == "chapter":
                value = {"chapter_id": "overview", "title": "项目概述", "paragraphs": paragraphs, "source_ids": ["1"]}
            else:
                self.assertEqual(request["action"], "independent_review")
                value = {"passed": False, "issues": [finding]}
            return {"content": json.dumps(value)}

        def report(task, input_revision, blueprint, chapters, family, **options):
            self.assertTrue(options["draft"])
            body = [block["text"] for block in options["document"]["blocks"] if block.get("type") == "paragraph"]
            self.assertTrue(all(paragraph in body for paragraph in paragraphs))
            if family == "feasibility":
                self.assertTrue(any("尚未人工批准" in item["text"] for item in options["document"]["pending"]))
            path = Path(self.storage.name) / str(task.pk) / (family + ".docx")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"draft-report-" + family.encode())
            return {"path": path.relative_to(self.storage.name).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "template_hash": "b" * 64,
                    "render_evidence": {"status": "draft_unverified",
                        "diagram_generation": report_diagram_evidence(options["document"], path)}}

        def presentation(task, pair):
            self.assertFalse(pair["approval_inherited"])
            path = Path(self.storage.name) / str(task.pk) / "presentation.pptx"
            with ZipFile(path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", "pending draft")
            return {"path": path.relative_to(self.storage.name).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "template_hash": "c" * 64,
                    "render_evidence": {"status": "draft_unverified", "pair_hash": pair["sha256"], "source_versions": pair["sources"]}}

        model.side_effect = reply
        report_renderer.side_effect = report
        ppt_renderer.side_effect = presentation
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=100,
                               PRODUCT_FEASIBILITY_TARGET_CHARACTERS=100, PRODUCT_ENFORCE_OUTPUT_LENGTH=True):
            approved = self.approve_blueprint(self.save_blueprint(self.create_task(reviewer=False)))["task"]
            record = DocumentTask.objects.get(pk=approved["id"])
            self.assertTrue(run_once())
            record.refresh_from_db()
            self.assertEqual((record.state, record.error_code), ("WAITING_REVIEW", ""))
            self.assertTrue(record.checkpoint["analysis_progress"]["outputs"]["full_document_human_review_required"])
            self.assertEqual(model.call_count, 4)  # Two authored families, each really reviewed once.
            current_input = record.revisions.get(kind="input", version=record.input_version)
            blueprint = record.revisions.get(kind="blueprint", version=record.blueprint_version)
            for review in record.revisions.filter(kind="review"):
                chapters = list(record.revisions.filter(kind="chapter", family=review.family))
                self.assertEqual(chapters[0].payload["paragraphs"], paragraphs)
                self.assertFalse(review.payload["passed"])
                self.assertTrue(review.payload["full_document_human_review_required"])
                self.assertTrue(any(issue["code"] == "unsupported_number" for issue in review.payload["issues"]))
                financial = [issue for issue in review.payload["issues"] if issue["code"] == "financial_conclusion_requires_review"]
                self.assertEqual(financial, [{"code": "financial_conclusion_requires_review", "chapter_id": "overview", "paragraph_index": 0}]
                                 if review.family == "feasibility" else [])
                self.assertEqual(review.payload["model_review"]["issues"], [finding])
                self.assertEqual(review.payload["model_review"]["status"], "issues_found")
                self.assertTrue(_content_review_current(record, review, current_input, blueprint, chapters))
            outputs = self.owner_client.get(f"/api/product/tasks/{record.pk}/outputs/").json()["outputs"]
            self.assertEqual({item["family"] for item in outputs}, {"technical-solution", "feasibility", "presentation"})
            self.assertTrue(all(item["current"] and item["draft"] for item in outputs))
            for artifact in record.artifacts.all():
                download = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/")
                self.assertEqual(download.status_code, 200)
                content = b"".join(download.streaming_content)
                self.assertEqual(hashlib.sha256(content).hexdigest(), artifact.sha256)
            self.assertFalse(DocumentApproval.objects.filter(task=record, revision__kind="report").exists())
            from portal.product_documents import DocumentError, render_report_draft
            feasibility = list(record.revisions.filter(kind="chapter", family="feasibility"))
            with patch("portal.product_documents._render_document", return_value={"contract_render_reached": True}) as runtime_render:
                rendered = render_report_draft(record, current_input, blueprint, feasibility, "feasibility", draft=True)
                self.assertTrue(rendered["contract_render_reached"])
                rendered_body = [block["text"] for block in runtime_render.call_args.args[4]["blocks"] if block.get("type") == "paragraph"]
                self.assertTrue(all(paragraph in rendered_body for paragraph in paragraphs))
                with self.assertRaises(DocumentError) as strict_render:
                    render_report_draft(record, current_input, blueprint, feasibility, "feasibility")
                self.assertEqual(strict_render.exception.code, "investment_evidence_required")
                self.assertEqual(runtime_render.call_count, 1)
            chapter = record.revisions.filter(kind="chapter", family="technical-solution").first()
            append_revision(record, "chapter", {**chapter.payload, "paragraphs": ["已修改正文。"]},
                            input_hash=current_input.sha256, blueprint_hash=blueprint.sha256, family=chapter.family)
            stale = {item["family"]: item for item in self.owner_client.get(f"/api/product/tasks/{record.pk}/outputs/").json()["outputs"]}
            self.assertFalse(stale["technical-solution"]["current"])
            self.assertFalse(stale["presentation"]["current"])
            self.assertTrue(stale["feasibility"]["current"])
        with self.assertRaises(ExecutionError) as formal:
            _formal_paragraph_guard(paragraphs, "feasibility")
        self.assertEqual(formal.exception.code, "investment_evidence_required")
        with self.assertRaises(ExecutionError) as repeated:
            _formal_paragraph_guard(["重复内容" * 300], "feasibility", draft=True)
        self.assertEqual(repeated.exception.code, "repeated_body_filler")
