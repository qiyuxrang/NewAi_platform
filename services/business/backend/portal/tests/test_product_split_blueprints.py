import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_service import ProductError, blueprint_chapters, validate_blueprint, append_revision
from portal.product_worker import _chapter_character_count, _generate_family, claim_task
from .base import PortalTestCase
from . import test_product_api as api_fixture
from . import test_product_worker as worker_fixture


def split_plan(payload):
    plan = deepcopy(payload)
    plan["chapters"] = [
        {"id": "T1", "family": "technical-solution", "title": "技术路线与接口设计", "scope": "选型依据与技术约束", "source_ids": payload["chapters"][0]["source_ids"]},
        {"id": "F1", "family": "feasibility", "title": "背景调研与建设必要性", "scope": "现状证据与需求论证", "source_ids": payload["chapters"][0]["source_ids"]},
        {"id": "F2", "family": "feasibility", "title": "投资估算依据与实施风险", "scope": "数据需求与分析方法，不虚构收益", "source_ids": payload["chapters"][0]["source_ids"]},
    ]
    return plan


class SplitBlueprintContractTests(SimpleTestCase):
    def test_two_plans_share_one_validated_package_and_legacy_is_unchanged(self):
        old = {"purpose": "建设论证", "audience": "项目负责人", "chapters": [{"id": "shared", "title": "概述", "scope": "", "source_ids": ["1"]}],
               "conditions": [], "missing": [], "conflicts": [], "template_version": "frozen-original-v1"}
        new = split_plan(old)
        self.assertEqual(validate_blueprint(new, {}), new)
        self.assertEqual([item["id"] for item in blueprint_chapters(new)], ["T1"])
        self.assertEqual([item["id"] for item in blueprint_chapters(new, "feasibility")], ["F1", "F2"])
        self.assertEqual(validate_blueprint(old, {}), old)
        self.assertEqual(blueprint_chapters(old), blueprint_chapters(old, "feasibility"))
        for bad in ([42], [{**new["chapters"][0], "family": []}], new["chapters"][:1], [new["chapters"][0], old["chapters"][0]],
                    [new["chapters"][0], {**new["chapters"][0], "id": "F1", "family": "feasibility"}]):
            with self.subTest(bad=bad), self.assertRaises(ProductError):
                validate_blueprint({**new, "chapters": bad}, {})

    def test_only_distinct_customer_body_counts_toward_minimum(self):
        body = "核对设备接口约束，记录现场条件并比较备选技术路线。"
        revisions = [SimpleNamespace(payload={"paragraphs": [body, body + " \n", 'source_ids: ["r1"]', "TODO", "待审核", "重复句。" * 300]}),
                     SimpleNamespace(payload={"paragraphs": [body, "保留接口核对记录。"]})]
        self.assertEqual(_chapter_character_count(revisions), len(body + "保留接口核对记录。"))


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=20,
                   PRODUCT_FEASIBILITY_TARGET_CHARACTERS=40)
class SplitBlueprintGenerationTests(PortalTestCase):
    setUp = worker_fixture.ProductWorkerTests.setUp

    @override_settings(PRODUCT_OFFICE_RENDER_ENABLED=False, PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    def test_generation_selects_only_family_chapters_and_resume_uses_same_ids(self):
        from portal.product_models import DocumentApproval
        from portal.product_service import approval_authorization
        from portal.product_three_drafts import generate_report_drafts, generate_presentation_artifact
        from portal.product_worker import ExecutionError
        plan = split_plan(self.blueprint_payload)
        self.blueprint = append_revision(self.task, "blueprint", plan, input_hash=self.input_revision.sha256, actor=self.owner)
        self.task.blueprint_version = self.blueprint.version
        self.task.pending_action = "generate_outputs"
        self.task.save()
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner, decision="approve",
                                        sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))
        task_id, fence, attempt = claim_task()
        calls = []
        def respond(*args, **kwargs):
            request = json.loads(args[2][1]["content"])
            family = request["family"]
            spec = request["chapter"]
            calls.append((family, spec["id"]))
            expected = ["T1"] if family == "technical-solution" else ["F1", "F2"]
            self.assertEqual([item["id"] for item in request["approved_blueprint"]["chapters"]], expected)
            self.assertEqual(request["length_target"]["chapter_characters"], 20)
            bodies = {"T1": "对接前应核对接口输入输出边界，记录异常处理和联调验收证据。",
                      "F1": "调研阶段应记录实际使用场景与资料缺口，再据此论证建设需求和约束。",
                      "F2": "估算阶段先收集报价与维护范围，分析不确定因素对实施决策的影响。"}
            return {"content": json.dumps({"chapter_id": spec["id"], "title": spec["title"],
                                           "paragraphs": [bodies[spec["id"]]], "source_ids": ["r1"]})}
        self.login(self.client, self.owner)
        with patch("portal.product_worker.generate_for_use", side_effect=respond) as model, patch(
                "portal.product_worker._generate_diagrams_uncached", side_effect=ExecutionError("diagram_generation_invalid")):
            for family in ("technical-solution", "feasibility"):
                result = _generate_family(task_id, fence, attempt, self.task, self.input_revision, self.blueprint, family)
                self.assertTrue(all(chapter.family == family for chapter in result))
                _generate_family(task_id, fence, attempt, self.task, self.input_revision, self.blueprint, family)
                artifacts = generate_report_drafts(self.task, fence, attempt, self.input_revision, self.blueprint, families=[family])
                artifact = artifacts[0]
                # The first report is a real downloadable DOCX while the other is still absent.
                response = self.client.get(f"/api/product/outputs/{artifact.pk}/download/")
                self.assertEqual(response.status_code, 200)
                raw = b"".join(response.streaming_content)
                self.assertTrue(raw.startswith(b"PK"))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), artifact.sha256)
                self.task.refresh_from_db()
                self.assertEqual(self.task.state, "RUNNING")
                if family == "technical-solution":
                    self.assertFalse(self.task.artifacts.filter(family="feasibility").exists())
            presentation = generate_presentation_artifact(self.task, fence, attempt, self.input_revision, self.blueprint)
            response = self.client.get(f"/api/product/outputs/{presentation.pk}/download/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(hashlib.sha256(b"".join(response.streaming_content)).hexdigest(), presentation.sha256)
            self.assertEqual(presentation.render_evidence["engine_version"], "v5")
            self.assertEqual(model.call_count, 3)
        self.assertEqual(calls, [("technical-solution", "T1"), ("feasibility", "F1"), ("feasibility", "F2")])


class SplitBlueprintApiTests(PortalTestCase):
    setUp = api_fixture.ProductApiTests.setUp
    create_task = api_fixture.ProductApiTests.create_task
    input_payload = api_fixture.ProductApiTests.input_payload
    save_blueprint = api_fixture.ProductApiTests.save_blueprint
    approve_blueprint = api_fixture.ProductApiTests.approve_blueprint

    def blueprint_payload(self):
        return split_plan(api_fixture.ProductApiTests.blueprint_payload(self))

    def test_manual_family_scope_and_saved_download_are_bound_to_same_approval(self):
        from portal.product_models import DocumentTask
        task = self.save_blueprint(self.create_task())
        self.approve_blueprint(task)
        record = DocumentTask.objects.get(pk=task["id"])
        record.state = "DRAFT"
        record.save(update_fields=["state"])
        url = f"/api/product/tasks/{record.pk}/chapters/"
        def submit(chapter, family):
            record.refresh_from_db()
            return self.owner_client.post(url, json.dumps({"expected_version": record.version,
                "family": family, "chapter_id": chapter["id"], "title": chapter["title"],
                "paragraphs": [chapter["title"] + "的已保存分析正文。"], "source_ids": ["1"]}), content_type="application/json")
        plan = self.blueprint_payload()
        denied = submit(plan["chapters"][0], "feasibility")
        self.assertEqual(denied.status_code, 409, denied.content)
        self.assertFalse(record.revisions.filter(kind="chapter").exists())
        for spec in plan["chapters"]:
            response = submit(spec, spec["family"])
            self.assertEqual(response.status_code, 201, response.content)
        for family, included, excluded in (("technical-solution", "技术路线与接口设计", "背景调研与建设必要性"),
                                           ("feasibility", "背景调研与建设必要性", "技术路线与接口设计")):
            response = self.owner_client.get(f"/api/product/tasks/{record.pk}/saved-draft/download/?family={family}")
            self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
            body = b"".join(response.streaming_content).decode("utf-8-sig")
            self.assertIn(included, body)
            self.assertNotIn(excluded, body)
