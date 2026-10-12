"""Opt-in real render smoke; only the model response is a deterministic substitute."""
import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.conf import settings
from django.test import override_settings

from portal.product_documents import DocumentError
from portal.product_models import DocumentArtifact, DocumentApproval, DocumentTask
from portal.product_worker import run_once
from .base import PortalTestCase
from . import test_product_api as product_api_tests
from .short_triad_fixture import TECHNICAL, FEASIBILITY


class ShortTriadRealChainTests(PortalTestCase):
    setUp = product_api_tests.ProductApiTests.setUp
    create_task = product_api_tests.ProductApiTests.create_task
    save_blueprint = product_api_tests.ProductApiTests.save_blueprint
    approve_blueprint = product_api_tests.ProductApiTests.approve_blueprint

    def input_payload(self):
        paragraphs = [self.paragraph(row) for row in [*TECHNICAL, *FEASIBILITY]]
        return {"project": "合成短链验证", "requirements": "仅验证合成文件结构与失败恢复。",
                "items": [{"row_id": "1", "name": "合成防火墙", "quantity": 2, "unit": "台"}],
                "background": "全部内容均为合成测试资料。\n" + "\n".join(paragraphs),
                "conditions": ["不得新增清单外设备"]}

    def blueprint_payload(self):
        return {"purpose": "合成短链验证", "audience": "工程验证人员",
                "chapters": [{"id": "overview", "title": "合成机制与验证边界", "scope": "人工合成机制",
                              "source_ids": ["1"]}],
                "conditions": [{"text": "不得新增清单外设备", "type": "program"}],
                "missing": ["真实项目资料及模型与知识库尚未验证"], "conflicts": [],
                "template_version": "frozen-original-v1"}

    @staticmethod
    def paragraph(row):
        _, start, process, end, detail = row
        return start + "、" + process + "、" + end + "构成本段的合成关系。" + detail

    def model_reply(self, *args, **kwargs):
        request = json.loads(args[2][1]["content"])
        action = request["action"]
        self.model_actions.append(action)
        if action == "chapter":
            rows = TECHNICAL if request["family"] == "technical-solution" else FEASIBILITY
            value = {"chapter_id": "overview", "title": "合成机制与验证边界",
                     "paragraphs": [self.paragraph(row) for row in rows], "source_ids": ["1"]}
        elif action == "independent_review":
            value = {"passed": True, "issues": []}
        elif action == "diagram":
            rows = TECHNICAL if request["family"] == "technical-solution" else FEASIBILITY
            diagrams = []
            for figure in request["figures"]:
                index = int(figure["figure_id"].split("_")[1]) - 1
                title, start, process, end, detail = rows[index]
                block = next(item for item in request["report_blocks"] if start + "、" in item["text"])
                diagrams.append({"figure_id": figure["figure_id"], "title": "合成示意：" + title,
                    "description": detail, "source": f'flowchart LR\nA["{start}"] --> B["{process}"]\nB --> C["{end}"]',
                    "evidence_block_ids": [block["id"]], "anchor_text": start})
            value = {"diagrams": diagrams}
        else:
            raise AssertionError("unexpected substitute action: " + action)
        return {"content": json.dumps(value, ensure_ascii=False), "prompt_tokens": 10, "completion_tokens": 20}

    def audit_package(self, artifact):
        target = Path(self.storage.name) / artifact.path
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), artifact.sha256)
        with ZipFile(target) as package:
            self.assertIsNone(package.testzip())
            names = package.namelist()
            for name in names:
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(package.read(name))
            if artifact.family != "presentation":
                expected = 15 if artifact.family == "technical-solution" else 20
                self.assertGreaterEqual(len([name for name in names if name.startswith("word/media/")]), expected)
                diagrams = artifact.render_evidence["diagram_generation"]
                self.assertEqual(diagrams["figure_count"], expected)
                self.assertEqual(diagrams["security_level"], "strict")
                self.assertEqual(diagrams["blocked_network_requests"], 0)
                self.assertFalse(diagrams["source_persisted"])
                embedded = {hashlib.sha256(package.read(name)).hexdigest() for name in names if name.startswith("word/media/")}
                self.assertTrue({item["image_sha256"] for item in diagrams["figures"]} <= embedded)
                text = b"".join(package.read(name) for name in names if name.startswith("word/") and name.endswith(".xml"))
                self.assertNotIn(b"flowchart LR", text)
                self.assertIn(b"PAGE", text)
                self.assertIn(b"TOC", text)
                report = artifact.task.revisions.get(pk=artifact.render_evidence["report_id"])
                figures = [block for block in report.payload["blocks"] if block["type"] == "figure"]
                self.assertEqual(len(figures), expected)
                visible = "".join(ET.fromstring(package.read("word/document.xml")).itertext())
                for figure in figures:
                    self.assertTrue(figure["caption"].startswith("合成示意："), "saved report lost its rendered diagram caption")
                    self.assertIn(figure["caption"], visible)
            else:
                self.assertTrue(any(name.startswith("ppt/media/") for name in names))
                self.assertTrue(any(name.startswith("ppt/embeddings/") for name in names))

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=500,
                       PRODUCT_FEASIBILITY_TARGET_CHARACTERS=600, PRODUCT_MAX_MODEL_CALLS=100,
                       PRODUCT_STEP_RETRY_BASE_SECONDS=0,
                       PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS=180, PRODUCT_OFFICE_RENDER_TIMEOUT_SECONDS=120)
    def test_short_writing_review_two_reports_ppt_download_and_resume(self):
        if os.environ.get("RUN_PRODUCT_REAL_SHORT_SMOKE") != "1":
            self.skipTest("opt-in real Node, Chromium and Office smoke; use scripts/test-product-short-chain.py")
        self.assertTrue(settings.PRODUCT_ENFORCE_OUTPUT_LENGTH)
        retained = os.environ.get("PRODUCT_SHORT_SMOKE_OUTPUT")
        if retained:
            self.addCleanup(lambda: shutil.copytree(self.storage.name, Path(retained) / "retained", dirs_exist_ok=True))
        self.model_actions = []
        real_presentation = __import__("portal.product_presentation", fromlist=["render_presentation_draft"]).render_presentation_draft
        failed_once = False
        def presentation_with_one_fault(*args, **kwargs):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise DocumentError("presentation_unavailable", diagnostic={"stage": "presentation_render", "reason": "timeout"})
            return real_presentation(*args, **kwargs)
        with patch("portal.product_worker.generate_for_use", side_effect=self.model_reply), \
             patch("portal.product_presentation.render_presentation_draft", side_effect=presentation_with_one_fault):
            created = self.approve_blueprint(self.save_blueprint(self.create_task()))["task"]
            task = DocumentTask.objects.get(pk=created["id"])
            self.assertTrue(run_once())
            task.refresh_from_db()
            if task.error_code not in {"step_retry_pending", ""} and retained:
                (Path(retained) / "failure-state.json").write_text(json.dumps({"error_code": task.error_code,
                    "checkpoint": task.checkpoint, "artifacts": list(task.artifacts.values()),
                    "revisions": list(task.revisions.values()), "steps": list(task.steps.values())}, default=str,
                    ensure_ascii=False, indent=2), encoding="utf-8")
            self.assertEqual(task.state, "QUEUED", task.error_code)
            self.assertEqual(task.error_code, "step_retry_pending")
            before = {artifact.family: (str(artifact.pk), artifact.sha256) for artifact in task.artifacts.all()}
            self.assertEqual(set(before), {"technical-solution", "feasibility"})
            calls_before = len(self.model_actions)
            manual_attempts = task.attempt_count
            self.assertTrue(run_once())
            task.refresh_from_db()
            self.assertEqual(task.error_code, "", task.checkpoint.get("last_failure"))
            self.assertEqual(task.state, "WAITING_REVIEW")
            self.assertEqual(task.attempt_count, manual_attempts, "automatic retry consumed a manual attempt")
            self.assertEqual(task.attempts.count(), 2)
            self.assertEqual(task.steps.get(key="render:presentation").retry_count, 1)
            self.assertEqual(len(self.model_actions), calls_before, "retry called the model for saved work")
            self.assertEqual({artifact.family: (str(artifact.pk), artifact.sha256) for artifact in task.artifacts.exclude(family="presentation")}, before)
        self.assertEqual(self.model_actions.count("chapter"), 2)
        self.assertEqual(self.model_actions.count("independent_review"), 2)
        self.assertEqual(self.model_actions.count("diagram"), 35)
        self.assertFalse(DocumentApproval.objects.filter(task=task, revision__kind="report").exists())
        records = []
        from portal.product_output_preview import draft_preview_evidence
        for artifact in task.artifacts.order_by("version"):
            self.audit_package(artifact)
            download = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/download/")
            self.assertEqual(download.status_code, 200)
            downloaded = b"".join(download.streaming_content)
            self.assertEqual(hashlib.sha256(downloaded).hexdigest(), artifact.sha256)
            self.assertEqual(self.other_client.get(f"/api/product/outputs/{artifact.pk}/download/").status_code, 404)
            preview = draft_preview_evidence(artifact)
            self.assertIsNotNone(preview, artifact.family)
            for page in preview["pages"]:
                response = self.owner_client.get(f"/api/product/outputs/{artifact.pk}/preview/?page={page['page']}")
                self.assertEqual(response.status_code, 200, artifact.family)
                content = b"".join(response.streaming_content) if response.streaming else response.content
                self.assertEqual(hashlib.sha256(content).hexdigest(), page["sha256"])
            records.append({"family": artifact.family, "path": artifact.path, "sha256": artifact.sha256,
                            "page_count": preview["page_count"], "preview": preview,
                            "characters": sum(len(p) for chapter in task.revisions.filter(kind="chapter", family=artifact.family)
                                              for p in chapter.payload["paragraphs"])})
        if retained:
            destination = Path(retained) / "retained"
            shutil.copytree(self.storage.name, destination, dirs_exist_ok=True)
            (Path(retained) / "evidence.json").write_text(json.dumps({"scope": "synthetic_short_worker_chain",
                "model": "deterministic_substitute", "rag": "source_only_preview",
                "office": "real_office16", "mermaid": "real_mermaid12_edge", "figure_count": 35,
                "test_only_character_targets": {"technical-solution": 500, "feasibility": 600},
                "production_targets_unchanged": {"technical-solution": 50000, "feasibility": 70000},
                "fault": "injected_presentation_timeout_once", "report_ids_and_hashes_reused": True,
                "retry_model_calls": 0, "model_actions": self.model_actions, "artifacts": records,
                "manual_attempt_count": task.attempt_count, "execution_attempt_count": task.attempts.count(),
                "final_state": task.state, "error_code": task.error_code,
                "visual_review": "not_run", "formal_delivery": False}, ensure_ascii=False, indent=2), encoding="utf-8")
