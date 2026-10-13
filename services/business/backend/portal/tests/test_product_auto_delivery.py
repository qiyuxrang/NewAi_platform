import hashlib
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

from django.test import Client, override_settings

from portal.product_delivery import artifact_delivery, finish_output_delivery, record_artifact_delivery
from portal.product_diagrams import minimum_diagrams
from portal.product_models import DocumentApproval, DocumentArtifact, DocumentSource
from portal.product_pair import _report_generation_hash, output_current, pair_snapshot, save_report_content
from portal.product_service import append_revision
from portal.product_worker import _ensure_content_review, claim_task
from .base import PortalTestCase
from .test_product_pair import report_diagram_evidence
from . import test_product_worker as worker_tests


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
    PRODUCT_TECHNICAL_TARGET_CHARACTERS=60, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=60,
    PRODUCT_ENFORCE_OUTPUT_LENGTH=True,
    PRODUCT_COST_POLICY={"approval_ref": "isolated-delivery-test", "currency": "TEST", "max_task_cost": "100",
                        "route_cost_caps": {"product_blueprint": "1", "product_writing": "1", "product_review": "1"}})
class AutomaticDeliveryTests(PortalTestCase):
    queue_outputs = worker_tests.ProductWorkerTests.queue_outputs

    def setUp(self):
        worker_tests.ProductWorkerTests.setUp(self)
        self.blueprint_payload["chapters"] = [
            {"id": family, "family": family, "title": "项目概述", "scope": "核对授权资料", "source_ids": ["r1"]}
            for family in ("technical-solution", "feasibility")]
        self.queue_outputs(missing=["预算待确认"])
        self.task.reviewer = None
        self.task.save(update_fields=["reviewer"])
        _, self.fence, self.attempt = claim_task()
        self.task.refresh_from_db()
        self.client = Client()
        self.login(self.client, self.owner)

    @staticmethod
    def synthetic_body(family, size):
        # Synthetic distinct text checks character boundaries, not report quality.
        alphabet = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳"
        raw = "".join(hashlib.sha256(f"{family}:{index}".encode()).hexdigest()
                      for index in range(size // 64 + 1))
        return "".join(alphabet[int(value, 16)] for value in raw)[:size - 1] + "。"

    def report(self, family="technical-solution", *, size=100, tail="", diagrams_pending=False, source_ids=None):
        text = self.synthetic_body(family, size) + tail
        chapter = append_revision(self.task, "chapter", {"chapter_id": family, "title": "项目概述",
            "paragraphs": [text], "source_ids": source_ids or ["r1"]}, family=family,
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        with patch("portal.product_worker.generate_for_use", side_effect=AssertionError("no model review")):
            review = _ensure_content_review(self.task, self.fence, self.attempt,
                                           self.input_revision, self.blueprint, [chapter], family)
        version = self.task.artifacts.count() + 1
        target = Path(self.temporary.name) / str(self.task.pk) / f"report-{version}" / "report.docx"
        target.parent.mkdir(parents=True)
        target.write_bytes(f"isolated-mocked-assembled-report-{version}".encode())
        count = minimum_diagrams(family)
        blocks = [{"id": "h1", "type": "heading", "level": 1, "text": "项目概述"},
                  {"id": "h2", "type": "heading", "level": 2, "text": "分析依据"},
                  {"id": "body", "type": "paragraph", "text": text, "source_ids": ["SINPUT"]}]
        blocks.extend({"id": f"figure-{index}", "type": "figure", "path": f"assets/diagram-{index}.png"}
                      for index in range(count))
        content = {"family": family, "blocks": blocks, "pending": [{"id": "pending", "text": "预算待确认"}]}
        diagrams = report_diagram_evidence(content, target)
        diagrams.update(pending_count=int(diagrams_pending), quality_issue_count=int(diagrams_pending))
        report = save_report_content(self.task, family, content, input_hash=self.input_revision.sha256,
                                    blueprint_hash=self.blueprint.sha256, actor=self.owner)
        artifact = DocumentArtifact.objects.create(task=self.task, family=family, version=version,
            path=target.relative_to(self.temporary.name).as_posix(), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            review=review, input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256,
            template_hash="a" * 64, generation_hash=_report_generation_hash(
                self.task, family, self.input_revision, self.blueprint),
            render_evidence={"kind": "draft", "content_review": "human_review_required",
                "report_id": str(report.pk), "draft_quality": review.payload["draft_quality"],
                "structural_generation": "completed", "document_structure": {"figure_count": count,
                    "heading1_count": 1, "heading2_count": 1, "toc_depth": 2,
                    "embedded_raster_count": count, "mermaid_source_embedded": False},
                "diagram_generation": diagrams})
        return artifact

    def test_one_complete_report_delivers_while_running_without_second_approval_or_agent(self):
        artifact = self.report()
        original_review = deepcopy(artifact.review.payload)
        original_state = (self.task.state, self.task.pending_action, self.task.fence)
        approvals = DocumentApproval.objects.count()
        decision = record_artifact_delivery(artifact)
        self.assertTrue(decision["delivered"], decision)
        self.assertEqual(decision["quality_scope"], "program_only")
        self.assertEqual(decision["warnings"], [{"code": "unresolved_blueprint_items"}])
        self.assertFalse(artifact.review.payload["passed"])
        self.assertEqual(artifact.review.payload, original_review)
        self.assertEqual(DocumentApproval.objects.count(), approvals)
        self.assertIsNone(self.task.agent_root_id)
        listed = self.client.get(f"/api/product/tasks/{self.task.pk}/outputs/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertTrue(listed.json()["outputs"][0]["delivered"])
        response = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
        self.assertEqual(response.status_code, 200)
        downloaded = b"".join(response.streaming_content)
        response.close()
        self.assertEqual(hashlib.sha256(downloaded).hexdigest(), artifact.sha256)
        self.assertNotIn("草稿", unquote(response["Content-Disposition"]))
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.pending_action, self.task.fence), original_state)

    def test_real_quantity_problem_and_missing_diagrams_keep_downloadable_draft(self):
        for options, expected in (({"tail": "测试设备99台。"}, "quantity_mismatch"),
                                  ({"diagrams_pending": True}, "diagram_pending")):
            with self.subTest(expected=expected):
                artifact = self.report(**options)
                self.assertTrue(output_current(self.task, artifact))
                decision = artifact_delivery(artifact)
                self.assertFalse(decision["delivered"])
                self.assertIn(expected, {issue["code"] for issue in decision["blocking_issues"]})
                response = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
                self.assertEqual(response.status_code, 200)
                b"".join(response.streaming_content)
                response.close()
                self.assertIn("草稿", unquote(response["Content-Disposition"]))

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=70000)
    def test_exact_50k_and_70k_effective_length_boundaries(self):
        for family, target in (("technical-solution", 50000), ("feasibility", 70000)):
            with self.subTest(family=family):
                short = self.report(family, size=target - 1)
                self.assertFalse(artifact_delivery(short)["delivered"])
                full = self.report(family, size=target)
                decision = artifact_delivery(full)
                self.assertTrue(decision["delivered"], decision)
                self.assertEqual((decision["actual_characters"], decision["minimum_characters"]), (target, target))

    def test_old_versions_owner_rejection_body_and_file_changes_never_deliver(self):
        old = self.report()
        latest = self.report(size=110)
        self.assertFalse(artifact_delivery(old)["delivered"])
        self.assertTrue(artifact_delivery(latest)["delivered"])
        target = Path(self.temporary.name) / latest.path
        raw = target.read_bytes()
        target.write_bytes(b"changed")
        self.assertFalse(artifact_delivery(latest)["delivered"])
        target.write_bytes(raw)
        approval = self.blueprint.approvals.filter(actor=self.owner).latest("created_at")
        approval.decision = "reject"
        approval.save(update_fields=["decision"])
        self.assertFalse(artifact_delivery(latest)["delivered"])
        approval.decision = "approve"
        approval.save(update_fields=["decision"])
        chapter = self.task.revisions.filter(kind="chapter", family=latest.family).latest("version")
        chapter.payload["paragraphs"] = ["未经复核的新正文。"]
        chapter.save(update_fields=["payload"])
        self.assertFalse(artifact_delivery(latest)["delivered"])

    def test_complete_finishes_and_incomplete_waits_for_recovery(self):
        self.report()
        finish_output_delivery(self.task, self.fence, self.attempt, families=["technical-solution", "feasibility"])
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code, self.task.pending_action),
                         ("WAITING_INPUT", "delivery_incomplete", "generate_outputs"))

    def test_complete_selected_families_finish_without_a_reviewer(self):
        self.report()
        finish_output_delivery(self.task, self.fence, self.attempt, families=["technical-solution"])
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code, self.task.pending_action), ("COMPLETED", "", ""))

    def test_ppt_requires_both_delivered_reports_and_a_real_passing_quality_gate(self):
        self.report()
        feasibility = self.report("feasibility")
        pair = pair_snapshot(self.task)
        target = Path(self.temporary.name) / str(self.task.pk) / "presentation.pptx"
        target.write_bytes(b"isolated-mocked-presentation")
        artifact = DocumentArtifact.objects.create(task=self.task, family="presentation", version=3,
            path=target.relative_to(self.temporary.name).as_posix(), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256,
            generation_hash="b" * 64, template_hash="a" * 64,
            render_evidence={"pair_hash": pair["sha256"], "quality_gate": {"status": "pass"},
                "program_checks": {"status": "pass", "issues": []}, "visual_review": "not_run"})
        self.assertTrue(artifact_delivery(artifact)["delivered"])
        artifact.render_evidence["quality_gate"]["status"] = "fail"
        artifact.save(update_fields=["render_evidence"])
        self.assertFalse(artifact_delivery(artifact)["delivered"])
        artifact.render_evidence["quality_gate"]["status"] = "pass"
        artifact.save(update_fields=["render_evidence"])
        feasibility.render_evidence["diagram_generation"]["pending_count"] = 1
        feasibility.save(update_fields=["render_evidence"])
        self.assertFalse(artifact_delivery(artifact)["delivered"])

    def test_pair_retains_warning_evidence_without_turning_it_into_a_ppt_blocker(self):
        self.report()
        feasibility = self.report("feasibility")
        before = pair_snapshot(self.task)
        for quality in before["draft_quality"]["reports"]:
            self.assertEqual(quality["review_issue_count"], 1)
            self.assertEqual(quality["quality_issue_count"], 0)
            self.assertEqual(quality["blocking_issues"], [])
            self.assertEqual(quality["warnings"], [{"code": "unresolved_blueprint_items"}])
            self.assertEqual(quality["delivery_status"], "delivered")
        feasibility.render_evidence["diagram_generation"]["pending_count"] = 1
        feasibility.save(update_fields=["render_evidence"])
        after = pair_snapshot(self.task)
        self.assertNotEqual(before["sha256"], after["sha256"])
        quality = next(item for item in after["draft_quality"]["reports"] if item["family"] == "feasibility")
        self.assertIn("diagram_pending", quality["quality_issue_codes"])

    def test_changed_source_snapshot_blocks_delivery(self):
        artifact = self.report()
        self.assertTrue(artifact_delivery(artifact)["delivered"])
        target = Path(self.temporary.name) / "new-source.txt"
        target.write_bytes(b"new source not in confirmed input")
        DocumentSource.objects.create(task=self.task, original_name="new-source.txt", media_type="text/plain",
            path=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(), size=target.stat().st_size,
            parsed={}, uploaded_by=self.owner)
        self.assertFalse(artifact_delivery(artifact)["delivered"])

    def test_exact_approved_quantity_warning_survives_ppt_action_and_completion(self):
        from portal.product_worker import _DRAFT_QUANTITY_PENDING_CONDITION
        self.input_payload["items"].append(
            {"row_id": "r2", "name": "测试设备", "quantity": "3", "unit": "台"})
        for chapter in self.blueprint_payload["chapters"]:
            chapter["source_ids"] = ["r1", "r2"]
        self.blueprint_payload["conditions"].append(deepcopy(_DRAFT_QUANTITY_PENDING_CONDITION))
        grant_version = self.task.checkpoint["grant_version"]
        self.queue_outputs(missing=["预算待确认"])
        # This test replaces queued inputs after setUp's claim; retain the
        # real owner grant fence so the worker guard still checks authorization.
        self.task.checkpoint["grant_version"] = grant_version
        self.task.save(update_fields=["checkpoint"])
        for family in ("technical-solution", "feasibility"):
            artifact = self.report(family, tail="测试设备2台。", source_ids=["r1", "r2"])
            decision = artifact_delivery(artifact)
            self.assertTrue(decision["delivered"], decision)
            self.assertIn("quantity_source_ambiguous", {issue["code"] for issue in decision["warnings"]})
            self.assertIn("quantity_source_ambiguous", {issue["code"] for issue in artifact.review.payload["issues"]})
        before = pair_snapshot(self.task)
        self.task.pending_action = "presentation"
        self.task.save(update_fields=["pending_action"])
        self.assertEqual(pair_snapshot(self.task), before)
        finish_output_delivery(self.task, self.fence, self.attempt,
                               families=["technical-solution", "feasibility"])
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.pending_action), ("COMPLETED", ""))
        self.assertEqual(pair_snapshot(self.task), before)

    def test_incomplete_failure_logs_codes_without_body_or_claim_evidence(self):
        secret = "私有正文不得进入错误日志"
        self.report(tail=f"测试设备99台。{secret}。")
        with self.assertLogs("portal.product_worker", level="ERROR") as captured:
            finish_output_delivery(self.task, self.fence, self.attempt, families=["technical-solution"])
        self.task.refresh_from_db()
        self.assertNotIn(secret, str(captured.output))
        self.assertNotIn(secret, str(self.task.checkpoint["last_failure"]))
        summary = self.task.checkpoint["last_failure"]["outputs"]["technical-solution"]
        self.assertEqual(set(summary), {"status", "blocking_codes"})
        self.assertIn("quantity_mismatch", summary["blocking_codes"])
