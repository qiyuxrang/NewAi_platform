import json
from copy import deepcopy
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.db import transaction
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from portal.model_gateway import GatewayError
from portal.product_models import DocumentApproval, DocumentArtifact, DocumentAttempt, DocumentTask
from portal.product_service import append_revision, digest, approval_authorization
from portal.product_worker import ExecutionError, _store, claim_task, content_checks, current_chapters, run_once

from .base import PortalTestCase


class ProductQualityIssueContextTests(SimpleTestCase):
    def test_context_keeps_following_qualifier_and_omits_other_sentences(self):
        from portal.product_worker import _bounded_quality_issues
        claim = "任何关于现有系统存在数据孤岛的结论"
        sentence = claim + "，均须待调查确认。"
        issue = {"code": "unsupported_project_status", "paragraph_index": 0,
                 "claim": claim, "paragraph": "前一无关句。" + sentence + "后一无关句。", "correction": "核实"}
        result = _bounded_quality_issues([issue])[0]
        self.assertEqual(result["claim"], claim)
        self.assertEqual(result["context"], sentence)
        self.assertFalse(result["context_truncated"])
        self.assertNotIn("paragraph", result)

    def test_context_stays_bounded_and_does_not_guess_repeated_claim_location(self):
        from portal.product_worker import _bounded_quality_issues
        claim = "性能指标需确认"
        base = {"code": "unsupported_capability_claim", "paragraph_index": 0,
                "claim": claim, "correction": "核实"}
        long_issue = {**base, "paragraph": "前" * 300 + claim + "后" * 1000}
        result = _bounded_quality_issues([long_issue])[0]
        context = result["context"]
        self.assertTrue(result["context_truncated"])
        self.assertEqual(len(context), 250)
        self.assertIn(claim, context)
        repeated = {**base, "paragraph": claim + "。" + claim + "。"}
        self.assertNotIn("context", _bounded_quality_issues([repeated])[0])
        self.assertNotIn("context", _bounded_quality_issues([base])[0])


class ProductDiagramEvidenceAliasTests(SimpleTestCase):
    def test_short_model_ids_restore_exact_body_references_and_reject_unknown_ids(self):
        from portal.product_worker import _generate_diagrams_uncached as _generate_diagrams
        paragraph = {"id": "C123456789012345678901234P1", "type": "paragraph", "text": "权限控制和审计流程需验证。", "source_ids": ["SINPUT"]}
        document = {"family": "technical-solution", "metadata": {"title": "测试"}, "blocks": [
            {"id": "H1", "type": "heading", "level": 1, "text": "测试"}, paragraph,
            {"id": "DIAGRAM_01_FIGURE", "type": "figure", "caption": "权限与审计"}]}
        item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "权限与审计", "description": "验证权限和审计流程。",
                "source": "flowchart LR\nA[权限控制] --> B[审计流程]", "evidence_block_ids": ["B1"], "anchor_text": "权限控制"}
        def model(*args, **kwargs):
            self.assertEqual(args[4]["report_blocks"], [{"id": "B1", "text": paragraph["text"], "source_ids": ["SINPUT"]}])
            return kwargs["output_validator"]({"diagrams": [item]})
        with patch("portal.product_worker._model", side_effect=model):
            result = _generate_diagrams("test", 1, "attempt", document)
            self.assertEqual(result[0]["evidence_block_ids"], [paragraph["id"]])
            self.assertEqual(item["evidence_block_ids"], ["B1"])
            for invalid in ("B2", "OTHER_PROJECT_BLOCK"):
                item["evidence_block_ids"] = [invalid]
                with self.assertRaises(ExecutionError):
                    _generate_diagrams("test", 1, "attempt", document)


class ProductQuantitySourceTests(SimpleTestCase):
    def check(self, text, approved=("1",), cited=None, items=None, background="", sources=None):
        items = items or [
            {"row_id": "1", "source_id": "file-a", "source_item_id": "file-a:1", "name": "开关柜", "quantity": "2", "unit": "台"},
            {"row_id": "2", "source_id": "file-b", "source_item_id": "file-b:2", "name": "开关柜", "quantity": "3", "unit": "台"},
        ]
        chapter = SimpleNamespace(payload={"chapter_id": "c", "title": "设备清单",
            "source_ids": list(approved if cited is None else cited), "paragraphs": [text]})
        result = content_checks({"items": items, "background": background,
            "sources": sources or [{"id": "file-a"}, {"id": "file-b"}]},
            {"chapters": [{"id": "c", "title": "设备清单", "source_ids": list(approved)}]}, [chapter])
        return [issue for issue in result["issues"] if issue["code"] in {
            "quantity_mismatch", "quantity_source_ambiguous", "source_outside_blueprint", "source_review_required"}]

    def test_selected_row_does_not_compare_other_same_name_quantity(self):
        for text in ("开关柜2台。", "2台开关柜。"):
            with self.subTest(text=text):
                self.assertEqual(self.check(text), [])
        issues = self.check("开关柜3台。")
        self.assertTrue(any(issue["code"] == "quantity_mismatch" and issue["row_id"] == "1" for issue in issues))

    def test_original_area_disambiguates_and_specification_mm_is_not_quantity_m(self):
        items = [{"row_id": "1", "name": "黄绿线", "quantity": "110", "unit": "m", "source_section": "原煤仓配电室"},
                 {"row_id": "2", "name": "黄绿线", "quantity": "120", "unit": "m", "source_section": "产品仓下配电室"}]
        self.assertEqual(self.check("原煤仓配电室的黄绿线110m。", approved=("1", "2"), items=items), [])
        self.assertEqual(self.check("黄绿线截面积规格16mm²待核对。", approved=("1", "2"), items=items), [])
        self.assertTrue(any(issue["code"] == "quantity_mismatch" for issue in
            self.check("原煤仓配电室的黄绿线120m。", approved=("1", "2"), items=items)))

    def test_cited_project_background_can_support_its_bound_equipment_quantity(self):
        source = {"id": "background", "purpose": "background", "media_type": "text/plain"}
        options = {"approved": ("background",), "background": "新增开关柜2台。", "sources": [source]}
        self.assertEqual(self.check("开关柜2台。", **options), [])
        self.assertTrue(any(issue["code"] == "quantity_mismatch" for issue in self.check("开关柜3台。", **options)))
        for sources in ([source, {**source, "id": "uncited-background"}], [{**source, "purpose": "reference"}]):
            self.assertTrue(any(issue["code"] == "source_outside_blueprint"
                for issue in self.check("开关柜2台。", **{**options, "sources": sources})))
        self.assertTrue(any(issue["code"] == "quantity_source_ambiguous"
            for issue in self.check("开关柜2台。", **{**options, "background": "开关柜2台；开关柜3台。"})))

    def test_equipment_lists_bind_prefix_and_suffix_quantities_to_each_object(self):
        items = [{"row_id": row, "name": name, "quantity": quantity, "unit": "台"}
            for row, name, quantity in (("TEST-SRV", "应用服务器", "2"), ("TEST-STO", "备份存储", "1"),
                ("TEST-SW", "网络交换机", "2"), ("TEST-FW", "防火墙", "1"))]
        for text in ("将2台应用服务器（TEST-SRV）、1台备份存储（TEST-STO）、2台网络交换机（TEST-SW）和1台防火墙（TEST-FW）用于部署。",
            "应用服务器2台、备份存储1台、网络交换机2台和防火墙1台。",
            "2台TEST-SRV应用服务器、1台TEST-STO备份存储、2台TEST-SW网络交换机和1台TEST-FW防火墙。",
            "仅新增2台应用服务器和1台备份存储。", "应用服务器共计2台，备份存储1台。"):
            with self.subTest(text=text):
                self.assertEqual(self.check(text, approved=tuple(item["row_id"] for item in items), items=items), [])
                wrong = text.replace("2台应用服务器", "3台应用服务器").replace("应用服务器2台", "应用服务器3台")
                wrong = wrong.replace("2台TEST-SRV应用服务器", "3台TEST-SRV应用服务器").replace("应用服务器共计2台", "应用服务器共计3台")
                self.assertTrue(any(issue["code"] == "quantity_mismatch"
                    for issue in self.check(wrong, approved=tuple(item["row_id"] for item in items), items=items)))

    def test_file_sources_and_duplicate_row_ids_keep_their_scope(self):
        self.assertEqual(self.check("开关柜2台。", approved=("file-a",)), [])
        self.assertTrue(any(issue["code"] == "quantity_mismatch"
            for issue in self.check("开关柜3台。", approved=("file-a",))))
        items = [{"row_id": str(index), "source_id": "file-a", "source_item_id": f"file-a:{index}",
            "name": "开关柜", "quantity": str(index + 1), "unit": "台"} for index in (1, 2)]
        self.assertTrue(any(issue["code"] == "quantity_source_ambiguous"
            for issue in self.check("开关柜2台。", approved=("file-a",), items=items)))
        items = [{"row_id": "1", "source_id": source, "source_item_id": f"{source}:1",
            "name": "开关柜", "quantity": quantity, "unit": "台"}
            for source, quantity in (("file-a", "2"), ("file-b", "3"))]
        self.assertEqual(self.check("开关柜2台。", approved=("file-a",), items=items), [])
        self.assertTrue(any(issue["code"] == "quantity_source_ambiguous"
            for issue in self.check("开关柜2台。", items=items)))

    def test_outside_sources_and_specific_objects_still_fail(self):
        issues = self.check("开关柜3台。", cited=("2",))
        self.assertTrue(any(issue["code"] == "source_outside_blueprint" for issue in issues))
        items = [{"row_id": "1", "name": "开关柜", "quantity": "2", "unit": "台"},
            {"row_id": "2", "name": "变压器", "quantity": "3", "unit": "台"}]
        for text in ("变压器3台。", "变压器4台。", "变压器安装位置需核对。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "source_outside_blueprint"
                    for issue in self.check(text, items=items)))

        items = [{"row_id": "1", "name": "开关柜", "quantity": "2", "unit": "台"},
            {"row_id": "2", "name": "35kV开关柜", "quantity": "3", "unit": "台"}]
        self.assertEqual(self.check("35kV开关柜3台。", approved=("2",), items=items), [])
        self.assertTrue(any(issue["code"] == "source_outside_blueprint"
            for issue in self.check("35kV开关柜3台。", items=items)))
        self.assertTrue(any(issue["code"] == "quantity_mismatch"
            for issue in self.check("35kV开关柜2台。", approved=("1", "2"), items=items)))

    def test_ambiguous_same_names_never_guess_or_sum_distinct_objects(self):
        for text in ("开关柜2台。", "开关柜3台。", "开关柜5台。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "quantity_source_ambiguous"
                    for issue in self.check(text, approved=("1", "2"))))
        items = [{"row_id": "1", "name": "10kV开关柜", "quantity": "2", "unit": "台"},
            {"row_id": "2", "name": "35kV开关柜", "quantity": "3", "unit": "台"}]
        self.assertEqual(self.check("10kV开关柜2台；35kV开关柜3台。", approved=("1", "2"), items=items), [])
        self.assertTrue(any(issue["code"] == "quantity_mismatch"
            for issue in self.check("10kV开关柜3台；35kV开关柜2台。", approved=("1", "2"), items=items)))


class ProductChapterCorrectionContextTests(SimpleTestCase):
    def candidate_and_request(self):
        candidate = {"chapter_id": "chapter-1", "title": "章节1", "paragraphs": ["待修复的分析正文。"], "source_ids": ["r1"]}
        payload = {"action": "chapter", "chapter": {"id": "chapter-1", "title": "章节1", "source_ids": ["r1"]},
                   "schema": {"chapter_id": "chapter-1", "title": "章节1", "paragraphs": ["string"], "source_ids": []}}
        return candidate, payload

    def test_candidate_requires_complete_original_chapter_and_approved_sources(self):
        from portal.product_worker import _chapter_correction_context
        candidate, payload = self.candidate_and_request()
        original = deepcopy(payload)
        for field, value in (("chapter_id", "other"), ("title", "改写标题"), ("source_ids", []),
                             ("source_ids", ["unapproved"]), ("paragraphs", [])):
            with self.subTest(field=field, value=value):
                self.assertIsNone(_chapter_correction_context(payload, {**candidate, field: value}))
        self.assertIsNone(_chapter_correction_context(payload, {**candidate, "extra": "private"}))
        self.assertIsNone(_chapter_correction_context(payload, {key: value for key, value in candidate.items() if key != "title"}))
        context = _chapter_correction_context(payload, candidate)
        self.assertEqual(json.loads(context[0]["content"])["unaccepted_chapter_candidate"], candidate)
        self.assertEqual(context[1]["sha256"], digest(candidate))
        self.assertEqual(payload, original)

    def test_complete_candidate_and_combined_request_limits_never_truncate(self):
        from portal.product_worker import _chapter_correction_context
        candidate, payload = self.candidate_and_request()
        candidate["paragraphs"] = ["甲"]
        overhead = len(json.dumps(candidate, ensure_ascii=False)) - 1
        candidate["paragraphs"] = ["甲" * (12000 - overhead)]
        context = _chapter_correction_context(payload, candidate)
        self.assertEqual(context[1]["characters"], 12000)
        self.assertEqual(json.loads(context[0]["content"])["unaccepted_chapter_candidate"], candidate)
        candidate["paragraphs"][0] += "甲"
        self.assertIsNone(_chapter_correction_context(payload, candidate))

        candidate, payload = self.candidate_and_request()
        payload["input"] = {"background": ""}
        base = _chapter_correction_context(payload, candidate)[1]["request_characters"]
        payload["input"]["background"] = "资" * (14500 - base)
        context = _chapter_correction_context(payload, candidate)
        self.assertEqual(context[1]["request_characters"], 14500)
        self.assertEqual(json.loads(context[0]["content"])["unaccepted_chapter_candidate"], candidate)
        payload["input"]["background"] += "资"
        self.assertIsNone(_chapter_correction_context(payload, candidate))


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_COST_POLICY={
    "approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100",
    "route_cost_caps": {"product_blueprint": "1", "product_writing": "1", "product_review": "1"},
})
class ProductWorkerTests(PortalTestCase):
    @patch("portal.product_worker.generate_for_use")
    def test_unexpected_error_keeps_safe_failure_diagnostics(self, model):
        model.side_effect = RuntimeError("private source text and secret must not be retained")
        run_once()
        self.task.refresh_from_db()
        failure = self.task.checkpoint["last_failure"]
        self.assertEqual(self.task.error_code, "execution_failed")
        self.assertEqual(failure["exception_type"], "RuntimeError")
        self.assertTrue(failure["frames"])
        self.assertNotIn("private source text", json.dumps(failure))

    @patch("portal.product_worker.generate_for_use")
    def test_gateway_busy_is_not_replaced_with_generic_failure(self, model):
        model.side_effect = GatewayError("busy")
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("QUEUED", "step_retry_pending"))
        self.assertEqual(self.task.checkpoint["last_failure"]["cause_code"], "busy")
        self.assertIsNotNone(self.task.retry_after)

    @patch("portal.product_worker.generate_for_use")
    def test_blueprint_prompt_lists_only_current_authorized_source_ids(self, model):
        self.task.pending_action = "blueprint"
        self.task.stage = "BLUEPRINT"
        self.task.save(update_fields=["pending_action", "stage"])
        model.return_value = {"content": json.dumps(self.blueprint_payload), "prompt_tokens": 1, "completion_tokens": 1}

        run_once()

        payload = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(payload["allowed_source_ids"], ["r1"])
        self.assertEqual(payload["schema"]["chapters"][0]["source_ids"], ["source-id-from-allowed_source_ids"])
        self.assertIn("不得将allowed_source_ids整体复制到每章", payload["response_instruction"])
        self.assertIn(json.dumps(payload["schema"], ensure_ascii=False), model.call_args.args[2][0]["content"])
        self.assertIn("建设目标和待分析议题不能代替项目事实", model.call_args.args[2][0]["content"])

    def queue_blueprint_with_original_conditions(self):
        conditions = ["在现有机房部署", "支持权限控制和审计", "预算和工期待确认"]
        self.input_payload["conditions"] = conditions
        self.input_revision = append_revision(self.task, "input", self.input_payload, actor=self.owner)
        self.task.input_version = self.input_revision.version
        self.task.pending_action, self.task.stage = "blueprint", "BLUEPRINT"
        self.task.save(update_fields=["input_version", "pending_action", "stage"])
        legal = deepcopy(self.blueprint_payload)
        legal["conditions"] = [{"text": text, "type": "human"} for text in conditions]
        return legal

    def assert_blueprint_rejected(self, model, code):
        self.task.refresh_from_db()
        self.assertEqual(model.call_count, 2)
        self.assertEqual(self.task.state, "FAILED")
        self.assertEqual(self.task.error_code, code)
        self.assertEqual(self.task.blueprint_version, self.blueprint.version)
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 1)
        self.assertIsNone(self.task.lease_until)
        self.assertEqual(self.task.checkpoint["last_failure"]["code"], code)
        self.assertEqual(self.task.checkpoint["analysis_progress"]["blueprint"]["status"], "failed")
        attempt = DocumentAttempt.objects.get(task=self.task)
        self.assertEqual((attempt.status, attempt.error_code, attempt.model_calls), ("failed", code, 2))

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=70000)
    @patch("portal.product_worker.generate_for_use")
    def test_valid_blueprint_preserves_conditions_and_saves_review_state(self, model):
        legal = self.queue_blueprint_with_original_conditions()
        model.return_value = {"content": json.dumps(legal)}
        run_once()
        self.task.refresh_from_db()
        model.assert_called_once()
        request = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(request["input"]["conditions"], self.input_payload["conditions"])
        self.assertIn("每个原始条件必须逐字", request["response_instruction"])
        self.assertIn("预算和工期等未确认事项仍须保持未确认", request["response_instruction"])
        self.assertEqual(request["output_requirements"]["technical_minimum_characters"], 50000)
        self.assertEqual(request["output_requirements"]["feasibility_minimum_characters"], 70000)
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code), ("WAITING_REVIEW", "BLUEPRINT", ""))
        self.assertEqual(self.task.pending_action, "")
        saved = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        self.assertEqual(saved.payload, legal)
        self.assertEqual(saved.input_hash, self.input_revision.sha256)
        self.assertEqual(saved.sha256, digest(legal))
        self.assertFalse(saved.approvals.exists())
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).status, "done")

    @patch("portal.product_worker.generate_for_use")
    def test_rewritten_conditions_remain_rejected_after_one_correction(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid["conditions"][-1]["text"] = "预算和工期需要进一步确认"
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.assert_blueprint_rejected(model, "condition_missing")
        calls = self.task.checkpoint["calls"]
        self.assertEqual([call["validation_error"] for call in calls], ["condition_missing", "condition_missing"])
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertEqual(correction["output_validation_correction"]["code"], "condition_missing")
        self.assertEqual(correction["input"]["conditions"], self.input_payload["conditions"])

    @patch("portal.product_worker.generate_for_use")
    def test_condition_correction_persists_only_valid_second_response(self, model):
        legal = self.queue_blueprint_with_original_conditions()
        invalid = deepcopy(legal)
        invalid["conditions"] = invalid["conditions"][:1]
        model.side_effect = [{"content": json.dumps(invalid)}, {"content": json.dumps(legal)}]
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(model.call_count, 2)
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_REVIEW", ""))
        saved = self.task.revisions.get(kind="blueprint", version=self.task.blueprint_version)
        self.assertEqual(saved.payload, legal)
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 2)
        self.assertEqual(self.task.checkpoint["calls"][0]["validation_error"], "condition_missing")
        self.assertNotIn("validation_error", self.task.checkpoint["calls"][1])
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).model_calls, 2)

    @patch("portal.product_worker.generate_for_use")
    def test_schema_failure_records_counts_without_response_keys_or_values(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid.pop('audience')
        invalid['unexpected-private-field'] = 'private rejected response content'
        model.return_value = {'content': json.dumps(invalid)}
        run_once()
        self.assert_blueprint_rejected(model, 'invalid_model_output')
        calls = self.task.checkpoint['calls']
        self.assertTrue(all(call['structure_failure'] == {
            'reason': 'schema_fields_mismatch', 'missing_field_count': 1,
            'extra_field_count': 1} for call in calls))
        serialized = json.dumps(calls)
        self.assertNotIn('unexpected-private-field', serialized)
        self.assertNotIn('private rejected response content', serialized)

    @patch("portal.product_worker.generate_for_use")
    def test_json_and_blueprint_validation_share_one_correction(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid["conditions"] = []
        model.side_effect = [{"content": "invalid JSON"}, {"content": json.dumps(invalid)}]
        run_once()
        self.assert_blueprint_rejected(model, "condition_missing")
        self.assertEqual(self.task.checkpoint["calls"][0]["parse_error"], "invalid_model_output")
        self.assertEqual(self.task.checkpoint["calls"][1]["validation_error"], "condition_missing")

    @patch("portal.product_worker.generate_for_use")
    def test_blueprint_correction_still_rejects_unauthorized_sources(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid["chapters"][0]["source_ids"] = ["unapproved-source"]
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.assert_blueprint_rejected(model, "invalid_blueprint")

    @patch("portal.product_worker.generate_for_use")
    def test_blueprint_correction_still_rejects_unapproved_template(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid["template_version"] = "unapproved-template"
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.assert_blueprint_rejected(model, "invalid_template_version")

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_blueprint_correction_obeys_task_model_call_limit(self, model):
        invalid = self.queue_blueprint_with_original_conditions()
        invalid["conditions"] = []
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.task.refresh_from_db()
        model.assert_called_once()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "model_call_limit"))
        self.assertEqual(self.task.revisions.filter(kind="blueprint").count(), 1)
        self.assertEqual(self.task.checkpoint["calls"][0]["validation_error"], "condition_missing")

    @patch("portal.product_worker.generate_for_use")
    def test_stage_rules_are_sent_and_bound_to_call_evidence(self, model):
        from portal.product_rules import rules_hash
        from portal.product_worker import _model

        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": "{}", "prompt_tokens": 1, "completion_tokens": 1}
        self.assertEqual(_model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"}), {})
        system_message = model.call_args.args[2][0]["content"]
        self.assertIn("必须使用简体中文", system_message)
        self.assertIn("JSON键名、枚举值、来源标识和资料中的型号保持原样", system_message)
        self.assertIn("适用阶段：write", system_message)
        self.assertIn(rules_hash(), system_message)
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][0]["rules_hash"], rules_hash())

    def test_chapter_context_excludes_unselected_sources_and_history(self):
        from portal.product_worker import model_input

        payload = {**self.input_payload, "knowledge_sources": [{"id": "selected", "text": "allowed"}, {"id": "other", "text": "unselected"}],
                   "retrieval": {"raw": "private"}, "issue_history": [{"text": "private"}],
                   "statements": [{"text": "included", "source_ids": ["selected"]}, {"text": "excluded", "source_ids": ["other"]}]}
        context = model_input(self.task, payload, ["selected"])
        self.assertEqual(context["items"], [])
        self.assertEqual(context["knowledge_sources"], [{"id": "selected", "text": "allowed"}])
        self.assertEqual(context["statements"], [{"text": "included", "source_ids": ["selected"]}])
        self.assertNotIn("retrieval", context)
        self.assertNotIn("issue_history", context)

    @patch("portal.product_worker._finish", return_value=False)
    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_artifact_and_finish_commit_atomically(self, model, render, finish):
        from portal.product_worker import _render

        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256) for chapter in self.blueprint_payload["chapters"]]
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        render.return_value = self.rendered()
        with self.assertRaises(ExecutionError):
            _render(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertFalse(DocumentArtifact.objects.filter(task=self.task).exists())

    @override_settings(PRODUCT_COST_POLICY={})
    @patch("portal.product_worker.generate_for_use")
    def test_missing_cost_policy_does_not_block_model_call(self, model):
        self.task.pending_action = "blueprint"
        self.task.stage = "BLUEPRINT"
        self.task.save(update_fields=["pending_action", "stage"])
        model.return_value = {"content": json.dumps(self.blueprint_payload), "prompt_tokens": 10, "completion_tokens": 20}

        run_once()

        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "")
        model.assert_called_once()
        self.assertNotIn("budget", self.task.checkpoint)

    def setUp(self):
        # Worker unit tests replace document renderers; real preflight is covered by the short-chain smoke.
        self.enterContext(patch("portal.product_documents.preflight_document_rendering", return_value={}))
        self.owner = self.create_user("writer", "product")
        self.reviewer = self.create_user("reviewer", "product")
        self.input_payload = {"project": "隔离合成方案", "requirements": "不新增清单外设备", "background": "仅用于测试",
                              "items": [{"row_id": "r1", "name": "测试设备", "quantity": "2", "unit": "台"}], "conditions": ["不新增清单外设备"]}
        self.blueprint_payload = {"purpose": "隔离验证", "audience": "测试审核人", "chapters": [
            {"id": f"chapter-{index}", "title": f"章节{index}", "scope": "只描述清单", "source_ids": ["r1"]} for index in range(1, 4)],
            "conditions": [{"text": "不新增清单外设备", "type": "program"}], "missing": [], "conflicts": [], "template_version": "frozen-original-v1"}
        self.task = DocumentTask.objects.create(owner=self.owner, reviewer=self.reviewer, title="合成方案", idempotency_key="worker-test", payload_hash=digest(self.input_payload), state="QUEUED", stage="WRITING", pending_action="write")
        self.input_revision = append_revision(self.task, "input", self.input_payload, actor=self.owner)
        self.blueprint = append_revision(self.task, "blueprint", self.blueprint_payload, input_hash=self.input_revision.sha256, actor=self.owner)
        self.task.input_version = self.input_revision.version
        self.task.blueprint_version = self.blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings_override = override_settings(PRODUCT_STORAGE_ROOT=self.temporary.name, PRODUCT_REVIEWER_IDS=[self.reviewer.pk])
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner, decision="approve", sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))

    def reply(self, chapter_id):
        chapter = next(chapter for chapter in self.blueprint_payload["chapters"] if chapter["id"] == chapter_id)
        return {"content": json.dumps({"chapter_id": chapter_id, "title": chapter["title"], "paragraphs": ["沿用清单中2台测试设备。"], "source_ids": ["r1"]}), "prompt_tokens": 1, "completion_tokens": 2}

    def configure_structured_chapter_route(self):
        from portal.models import GatewayModel, ModelRoute, Module, Provider
        provider = Provider.objects.create(code="structured-chapter-test", name="合成结构化服务",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_env="PORTAL_MODEL_KEY_TEST", enabled=True)
        model = GatewayModel.objects.create(provider=provider, name="合成结构化模型", model_name="qwen3.8-flash",
            timeout_seconds=120, max_output_tokens=4096, enabled=True)
        ModelRoute.objects.update_or_create(code="product_writing", defaults={"name": "合成写作路由",
            "module": Module.objects.get(code="product"), "model": model, "enabled": True})

    @patch("portal.product_worker.generate_for_use")
    def test_chapter_schema_reaches_dispatch_and_binds_approved_fields(self, model):
        from portal.product_worker import _model
        from portal.model_response_format import chapter_response_format, generation_profile_metadata
        self.configure_structured_chapter_route()
        chapter = self.blueprint_payload["chapters"][0]
        payload = {"action": "chapter", "chapter": chapter, "schema": json.loads(self.reply(chapter["id"])["content"])}
        model.return_value = self.reply(chapter["id"])
        task_id, fence, attempt_id = claim_task()
        result = _model(task_id, fence, attempt_id, "product_writing", payload)
        model.assert_called_once()
        response_format = chapter_response_format(chapter)
        self.assertEqual(model.call_args.kwargs, {"response_format": response_format,
                                               "generation_profile": "bounded_chapter_v1"})
        self.assertEqual(result["source_ids"], ["r1"])
        self.task.refresh_from_db()
        evidence = self.task.checkpoint["calls"][0]
        metadata = generation_profile_metadata("bounded_chapter_v1")
        self.assertEqual(evidence["input_hash"], digest({"payload": payload,
            "response_format_sha256": digest(response_format), "generation_profile": metadata}))
        self.assertEqual(evidence["generation_profile"], metadata)
        self.assertEqual(evidence["response_format"], {"type": "json_schema", "schema_sha256": digest(response_format)})
        self.assertNotIn("properties", json.dumps(evidence))

    @patch("portal.product_worker.generate_for_use")
    def test_bounded_reasoning_records_only_numeric_usage_not_private_reasoning(self, model):
        from portal.product_worker import _model
        self.configure_structured_chapter_route()
        chapter = self.blueprint_payload["chapters"][0]
        model.return_value = {**self.reply(chapter["id"]), "completion_tokens": 602,
                              "reasoning_tokens": 512, "reasoning_content": "私有推理不得存储"}
        task_id, fence, attempt_id = claim_task()
        _model(task_id, fence, attempt_id, "product_writing", {
            "action": "chapter", "chapter": chapter, "schema": json.loads(self.reply(chapter["id"])["content"])})
        self.task.refresh_from_db()
        evidence = self.task.checkpoint["calls"][0]
        self.assertEqual(evidence["reasoning_tokens"], 512)
        self.assertNotIn("私有推理", json.dumps(self.task.checkpoint, ensure_ascii=False))
        self.assertNotIn("reasoning_content", evidence)

    @patch("portal.product_worker.generate_for_use")
    def test_small_configured_output_keeps_structured_nonreasoning_path(self, model):
        from portal.models import ModelRoute
        from portal.product_worker import _model
        self.configure_structured_chapter_route()
        configured = ModelRoute.objects.get(code="product_writing").model
        configured.max_output_tokens = 512
        configured.save(update_fields=["max_output_tokens"])
        chapter = self.blueprint_payload["chapters"][0]
        model.return_value = self.reply(chapter["id"])
        task_id, fence, attempt_id = claim_task()
        _model(task_id, fence, attempt_id, "product_writing", {
            "action": "chapter", "chapter": chapter, "schema": json.loads(self.reply(chapter["id"])["content"])})
        self.assertNotIn("generation_profile", model.call_args.kwargs)
        self.task.refresh_from_db()
        self.assertNotIn("generation_profile", self.task.checkpoint["calls"][0])

    @patch("portal.product_worker.generate_for_use")
    def test_schema_does_not_bypass_types_or_add_correction_calls(self, model):
        from portal.product_worker import _model
        self.configure_structured_chapter_route()
        chapter = self.blueprint_payload["chapters"][0]
        legal = json.loads(self.reply(chapter["id"])["content"])
        model.return_value = {"content": json.dumps({**legal, "paragraphs": True})}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError):
            _model(task_id, fence, attempt_id, "product_writing", {"action": "chapter", "chapter": chapter, "schema": legal})
        self.assertEqual(model.call_count, 2)
        self.task.refresh_from_db()
        self.assertEqual([item["validation_stage"] for item in self.task.checkpoint["calls"]], ["chapter_types", "chapter_types"])
        self.assertTrue(all("response_format" in call.kwargs for call in model.call_args_list))
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_schema_does_not_authorize_unapproved_sources(self, model):
        from portal.product_worker import _generate_family
        self.configure_structured_chapter_route()
        legal = json.loads(self.reply("chapter-1")["content"])
        model.return_value = {"content": json.dumps({**legal, "source_ids": ["not-approved"]})}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError):
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][-1]["validation_stage"], "output_contract")

    def rendered(self):
        return {"path": f"{self.task.pk}/draft-test.docx", "sha256": "a" * 64, "template_hash": "b" * 64, "render_evidence": {"status": "not_run"}}

    def queue_outputs(self, *, missing=(), conflicts=(), input_issues=()):
        self.input_payload["issues"] = list(input_issues)
        self.input_revision = append_revision(self.task, "input", self.input_payload, actor=self.owner)
        self.blueprint_payload["missing"] = list(missing)
        self.blueprint_payload["conflicts"] = list(conflicts)
        self.blueprint = append_revision(self.task, "blueprint", self.blueprint_payload,
                                        input_hash=self.input_revision.sha256, actor=self.owner)
        self.task.input_version = self.input_revision.version
        self.task.blueprint_version = self.blueprint.version
        self.task.pending_action = "generate_outputs"
        self.task.checkpoint = {"output_families": ["technical-solution"]}
        self.task.save(update_fields=["input_version", "blueprint_version", "pending_action", "checkpoint"])
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner, decision="approve",
                                        sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))

    def generation_replies(self, *, passed=True, issues=()):
        return [*[self.reply(chapter["id"]) for chapter in self.blueprint_payload["chapters"]],
                {"content": json.dumps({"passed": passed, "issues": list(issues)})}]

    def saved_chapters_for_continuation(self):
        paragraphs = ["沿用清单中2台测试设备。", "本章先核对原始设备清单与来源，保留未确认的实施条件并记录审查意见。",
                      "本章依据授权材料规划校验步骤，具体实施窗口仍须由业务负责人确认。"]
        return [append_revision(self.task, "chapter", {"chapter_id": chapter["id"], "title": chapter["title"],
                    "paragraphs": [paragraph], "source_ids": ["r1"]},
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                for chapter, paragraph in zip(self.blueprint_payload["chapters"], paragraphs)]

    def saved_chapters_with_long_duplicate(self, family):
        paragraphs = ["沿用清单中2台测试设备。",
                      "对照原始材料检查设备布置与施工条件，核对签字记录和现场照片，保留待确认事项。" * 6,
                      "本章依据授权材料规划校验步骤，具体实施窗口仍须由业务负责人确认。"]
        return [append_revision(self.task, "chapter", {"chapter_id": chapter["id"], "title": chapter["title"],
                    "paragraphs": [paragraph], "source_ids": ["r1"]},
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256, family=family)
                for chapter, paragraph in zip(self.blueprint_payload["chapters"], paragraphs)]

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_mixed_duplicate_chapter_keeps_only_new_body_and_binds_normalized_audit(self, model):
        from portal.product_worker import _generate_family, _chapter_character_count
        task_id, fence, attempt_id = claim_task()
        for family in ("technical-solution", "feasibility"):
            with self.subTest(family=family):
                saved = self.saved_chapters_with_long_duplicate(family)
                originals = [deepcopy(row.payload) for row in saved]
                duplicate = originals[1]["paragraphs"][0]
                addition = "实施前向业务负责人核对采集权限，记录字段映射与验收依据。"
                candidate = {**originals[0], "paragraphs": [duplicate, duplicate + "补充检查交接签字。", addition]}
                accepted = {**candidate, "paragraphs": [addition]}
                model.return_value = {"content": json.dumps(candidate)}
                result = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, family)
                self.assertEqual(result[0].payload["paragraphs"], [*originals[0]["paragraphs"], addition])
                self.assertEqual([row.pk for row in result[1:]], [row.pk for row in saved[1:]])
                for row, original in zip(saved, originals):
                    row.refresh_from_db()
                    self.assertEqual(row.payload, original)
                self.task.refresh_from_db()
                evidence = self.task.checkpoint["calls"][-1]
                self.assertEqual(evidence["chapter_output_normalization"], {
                    "original_response_sha256": digest(candidate), "removed_paragraph_count": 2,
                    "accepted_response_sha256": digest(accepted)})
                self.assertEqual(evidence["response_sha256"], digest(accepted))
                self.assertTrue(evidence["response_validated"])
                self.assertNotIn("parse_error", evidence)
                self.assertNotIn(duplicate, json.dumps(evidence, ensure_ascii=False))
                self.assertEqual(self.task.checkpoint["output_generation"][family]["actual_characters"],
                                 _chapter_character_count(result))
        self.assertEqual(model.call_count, 2)

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_all_long_duplicates_still_fail_after_one_correction_without_changing_saved_body(self, model):
        from portal.product_worker import _generate_family
        saved = self.saved_chapters_with_long_duplicate("technical-solution")
        candidate = {**saved[0].payload, "paragraphs": [saved[1].payload["paragraphs"][0] + "补充检查交接签字。"]}
        model.return_value = {"content": json.dumps(candidate)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(error.exception.quality_issues[0]["code"], "partial_duplicate_content")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 3)
        self.task.refresh_from_db()
        self.assertTrue(all(not call.get("response_validated") for call in self.task.checkpoint["calls"]))

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_removing_duplicate_body_cannot_bypass_numeric_facts_or_source_scope(self, model):
        from portal.product_worker import _generate_family
        saved = self.saved_chapters_with_long_duplicate("technical-solution")
        task_id, fence, attempt_id = claim_task()
        for invalid in ({"paragraphs": ["数据备份保留三十天。"]}, {"source_ids": ["not-approved"]}):
            with self.subTest(invalid=invalid):
                candidate = {**saved[0].payload, "paragraphs": ["实施前核对授权资料与验收依据。"], **invalid}
                candidate["paragraphs"] = [saved[1].payload["paragraphs"][0], *candidate["paragraphs"]]
                model.return_value = {"content": json.dumps(candidate)}
                with self.assertRaises(ExecutionError) as error:
                    _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint, "technical-solution")
                if "paragraphs" in invalid:
                    self.assertTrue(error.exception.quality_issues)
                    self.assertTrue(all(issue["paragraph_index"] == 1 for issue in error.exception.quality_issues))
                self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 3)
        self.assertEqual(model.call_count, 4)

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_duplicate_continuation_is_corrected_and_appends_without_overwriting_saved_text(self, model):
        from portal.product_worker import _generate_family
        saved = self.saved_chapters_for_continuation()
        original = deepcopy(saved[0].payload)
        duplicate = {**original, "paragraphs": [" \n" + original["paragraphs"][0].replace("2", " 2 ") + "\t"]}
        addition = "实施前核对设备清单与审批依据，实施后记录验收结果和待确认事项。"
        corrected = {**original, "paragraphs": [original["paragraphs"][0], addition, " " + addition + " "]}
        model.side_effect = [{"content": json.dumps(duplicate)}, {"content": json.dumps(corrected)}]
        task_id, fence, attempt_id = claim_task()
        result = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                                  self.blueprint, "technical-solution")
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertTrue(correction["continuation"]["append_only"])
        self.assertNotIn("last_text", correction["continuation"])
        self.assertNotIn("covered_paragraphs", correction["continuation"])
        self.assertEqual(correction["continuation"]["saved_text"], original["paragraphs"][0])
        self.assertFalse(correction["continuation"]["saved_text_truncated"])
        self.assertIn("真正新增", correction["chapter_validation_correction"])
        self.assertEqual(result[0].payload["paragraphs"], [original["paragraphs"][0], addition])
        saved[0].refresh_from_db()
        self.assertEqual(saved[0].payload, original)
        self.assertEqual([row.pk for row in result[1:]], [row.pk for row in saved[1:]])
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 4)

    @patch("portal.product_worker.generate_for_use")
    def test_bounded_batch_goal_is_system_instruction_without_rewriting_saved_chapter(self, model):
        from portal.product_worker import _model
        chapter = self.blueprint_payload["chapters"][0]
        legal = json.loads(self.reply(chapter["id"])["content"])
        payload = {"action": "chapter", "chapter": chapter, "schema": legal,
            "continuation": {"saved_text": "已保存的章节论证。", "append_only": True},
            "length_target": {"this_response_characters": 1182}}
        model.return_value = self.reply(chapter["id"])
        task_id, fence, attempt_id = claim_task()
        _model(task_id, fence, attempt_id, "product_writing", payload)
        model.assert_called_once()
        self.assertIn("本次仅追加约1182个非空白正文字符", model.call_args.args[2][0]["content"])
        self.assertIn("不是整章重写", model.call_args.args[2][0]["content"])
        self.assertEqual(json.loads(model.call_args.args[2][1]["content"]), payload)

    def test_writing_context_includes_earlier_middle_passages_and_bounds_large_manual_chapters(self):
        from portal.product_worker import _saved_writing_context
        middle = "此前已阐述的验收证据与责任边界不应重复续写。"
        paragraphs = ["原有背景" * 30 + middle + "前文内容" * 300, "后续已存论述" * 500]
        context = _saved_writing_context(paragraphs)
        self.assertNotIn(middle, paragraphs[0][:100])
        self.assertNotIn(middle, "\n".join(paragraphs)[-2400:])
        self.assertIn(middle, context["saved_text"])
        self.assertFalse(context["saved_text_truncated"])
        oversized = _saved_writing_context(["开头" + "中间" * 8000 + "末尾"])
        self.assertTrue(oversized["saved_text_truncated"])
        self.assertLessEqual(len(oversized["saved_text"]), 12000)
        self.assertGreater(oversized["saved_text_characters"], len(oversized["saved_text"]))
        self.assertTrue(oversized["saved_text"].startswith("开头"))
        self.assertTrue(oversized["saved_text"].endswith("末尾"))

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_two_duplicate_continuations_fail_without_persisting_fake_increment(self, model):
        saved = self.saved_chapters_for_continuation()
        original = deepcopy(saved[0].payload)
        model.return_value = {"content": json.dumps(original)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("FAILED", "invalid_model_output"))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).model_calls, 2)
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 3)
        current = current_chapters(self.task, self.input_revision.sha256, self.blueprint.sha256)
        self.assertEqual(current["chapter-1"].pk, saved[0].pk)
        self.assertEqual(current["chapter-1"].payload, original)
        self.assertFalse(self.task.artifacts.exists())

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60, PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_duplicate_continuation_retry_obeys_remaining_call_limit(self, model):
        saved = self.saved_chapters_for_continuation()
        original = deepcopy(saved[0].payload)
        model.return_value = {"content": json.dumps(original)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "model_call_limit"))
        model.assert_called_once()
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 3)
        self.assertEqual(current_chapters(self.task, self.input_revision.sha256, self.blueprint.sha256)
                         ["chapter-1"].payload, original)

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=60)
    @patch("portal.product_worker.generate_for_use")
    def test_json_failure_and_duplicate_continuation_share_one_correction(self, model):
        saved = self.saved_chapters_for_continuation()
        model.side_effect = [{"content": "invalid JSON"}, {"content": json.dumps(saved[0].payload)}]
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(self.task.revisions.filter(kind="chapter").count(), 3)

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_chapter_semantics_share_one_correction_and_save_only_valid_response(self, model, render):
        for field, invalid_value in (("chapter_id", "other"), ("title", "模型改写标题"),
                                     ("source_ids", ["unapproved-source"]), ("source_ids", [])):
            with self.subTest(field=field, value=invalid_value):
                # Exercise the actual model boundary without starting other chapters.
                from portal.product_worker import _generate_family
                # Each subcase intentionally exercises a new model contract, not a cached batch.
                self.task.steps.all().delete()
                task_id, fence, attempt_id = claim_task()
                invalid = json.loads(self.reply("chapter-1")["content"])
                invalid[field] = invalid_value
                model.reset_mock()
                model.side_effect = [{"content": json.dumps(invalid)}, self.reply("chapter-1"),
                                     self.reply("chapter-2"), self.reply("chapter-3")]
                _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                                 self.blueprint, "technical-solution")
                self.assertEqual(model.call_count, 4)
                correction = json.loads(model.call_args_list[1].args[2][1]["content"])
                self.assertIn("chapter_validation_correction", correction)
                self.assertEqual(correction["chapter"]["title"], "章节1")
                self.assertEqual(correction["chapter"]["source_ids"], ["r1"])
                self.assertEqual(len(model.call_args_list[1].args[2]), 2)
                revisions = self.task.revisions.filter(kind="chapter")
                self.assertEqual(revisions.count(), 3)
                self.assertTrue(all(row.payload["source_ids"] == ["r1"] for row in revisions))
                self.assertEqual(revisions.get(payload__chapter_id="chapter-1").payload["title"], "章节1")
                self.task.refresh_from_db()
                self.assertEqual(self.task.checkpoint["calls"][-4]["parse_error"], "invalid_model_output")
                revisions.delete()
                DocumentAttempt.objects.filter(pk=attempt_id).update(status="done")
                self.task.state = "QUEUED"
                self.task.lease_until = None
                self.task.save(update_fields=["state", "lease_until"])
        render.assert_not_called()

    @patch("portal.product_worker.generate_for_use")
    def test_chapter_json_and_semantic_errors_share_one_retry(self, model):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["title"] = "错误标题"
        model.side_effect = [{"content": "invalid JSON"}, {"content": json.dumps(invalid)}]
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("FAILED", "invalid_model_output"))
        self.assertEqual(model.call_count, 2)
        self.assertTrue(all(len(call.args[2]) == 2 for call in model.call_args_list))
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_chapter_semantic_correction_obeys_call_limit(self, model):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["title"] = "错误标题"
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "model_call_limit"))
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_permission_revoked_after_invalid_chapter_prevents_retry(self, model):
        def revoke(*args):
            self.owner.roles.clear()
            invalid = json.loads(self.reply("chapter-1")["content"])
            invalid["title"] = "错误标题"
            return {"content": json.dumps(invalid)}
        model.side_effect = revoke
        run_once()
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_chapter_validator_product_error_keeps_chapter_error_code(self, model):
        from portal.product_service import ProductError
        from portal.product_worker import _model
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": "{}"}
        def reject(result):
            raise ProductError("invalid_chapter", "invalid chapter")
        with self.assertRaises(ExecutionError) as error:
            _model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"}, output_validator=reject)
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_approved_preview_gaps_generate_draft_with_true_review_and_pending(self, model, render):
        self.queue_outputs(missing=["预算和工期待确认"])
        model.side_effect = self.generation_replies()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.stage, self.task.error_code), ("WAITING_REVIEW", "FINAL_REVIEW", ""))
        render.assert_called_once()
        request = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(request["action"], "independent_review")
        self.assertEqual(request["draft_review_boundary"]["approved_pending_items"], ["预算和工期待确认"])
        self.assertIn("仍须如实列入issues", request["draft_review_boundary"]["instruction"])
        review = self.task.revisions.get(kind="review").payload
        self.assertEqual(review["issues"], [{"code": "unresolved_blueprint_items"}])
        self.assertEqual(review["draft_pending"], ["预算和工期待确认"])
        self.assertEqual({key: review["model_review"][key] for key in
                          ("status", "issues", "scope", "full_document_human_review_required")},
                         {"status": "passed", "issues": [], "scope": "full", "full_document_human_review_required": False})
        self.assertTrue(review["model_review"]["coverage"]["complete"])
        self.assertFalse(review["passed"])
        self.assertEqual(review["human_review"], "required")
        self.assertTrue(review["full_document_human_review_required"])
        self.assertTrue(self.task.checkpoint["analysis_progress"]["outputs"]["full_document_human_review_required"])
        self.assertFalse(self.task.approvals.filter(revision__kind="report").exists())

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_preview_gaps_never_bypass_input_issues_conflicts_or_reviewer_findings(self, model, render):
        self.queue_outputs(missing=["预算和工期待确认"], input_issues=[{"code": "source_conflict"}],
                           conflicts=["输入资料存在冲突"])
        model.side_effect = self.generation_replies()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "content_review_required")
        render.assert_not_called()
        review = self.task.revisions.get(kind="review").payload
        self.assertEqual({issue["code"] for issue in review["issues"]},
                         {"unresolved_blueprint_items", "unresolved_input_items"})
        self.assertNotIn("draft_pending", review)

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_preview_gaps_do_not_hide_model_review_findings(self, model, render):
        self.queue_outputs(missing=["预算和工期待确认"])
        model.side_effect = self.generation_replies(passed=False, issues=["方案依据仍需核实"])
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_REVIEW", ""))
        render.assert_called_once()
        review = self.task.revisions.get(kind="review").payload
        self.assertEqual(review["model_review"]["status"], "issues_found")
        self.assertEqual(review["model_review"]["issues"], ["方案依据仍需核实"])
        self.assertFalse(review["passed"])
        self.assertTrue(review["full_document_human_review_required"])

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_preview_pending_exception_still_blocks_input_issues_without_conflicts(self, model, render):
        self.queue_outputs(missing=["预算待确认"], input_issues=[{"code": "missing_equipment_quantity"}])
        model.side_effect = self.generation_replies()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "content_review_required")
        render.assert_not_called()
        review = self.task.revisions.get(kind="review").payload
        self.assertIn({"code": "unresolved_input_items"}, review["issues"])
        self.assertEqual(review["draft_pending"], ["预算待确认"])

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="ragflow_required")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_formal_review_does_not_receive_preview_pending_exception(self, model, render):
        # Enter the already-authorized action boundary to isolate the content
        # gate; the graph's separate RAGFlow permission gate remains unchanged.
        from portal.product_worker import _execute_claim_action
        self.queue_outputs(missing=["预算待确认"])
        model.side_effect = self.generation_replies()
        task_id, fence, attempt_id = claim_task()
        _execute_claim_action(task_id, fence, attempt_id)
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "content_review_required")
        render.assert_not_called()
        request = json.loads(model.call_args.args[2][1]["content"])
        self.assertNotIn("draft_review_boundary", request)
        self.assertNotIn("draft_pending", self.task.revisions.get(kind="review").payload)

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_preview_gaps_do_not_hide_quantity_mismatch(self, model, render):
        self.queue_outputs(missing=["预算和工期待确认"])
        replies = self.generation_replies()
        chapter = json.loads(replies[0]["content"])
        chapter["paragraphs"] = ["测试设备数量999台。"]
        replies = [{"content": json.dumps(chapter)}] * 2
        model.side_effect = replies
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "invalid_model_output")
        render.assert_not_called()
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.assertIn("quantity_mismatch", {issue["code"] for issue in
            self.task.checkpoint["last_failure"]["quality_issues"]})

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_exact_owner_approved_pending_condition_keeps_conflicts_in_draft_review(self, model, render):
        from portal.product_worker import _DRAFT_PENDING_CONDITION, _approved_pending_draft
        self.blueprint_payload["conditions"].append(deepcopy(_DRAFT_PENDING_CONDITION))
        self.queue_outputs(missing=["预算待确认"], conflicts=["重复行归属待确认"],
                           input_issues=[{"code": "duplicate_row_id"}])
        model.side_effect = self.generation_replies()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.stage), ("WAITING_REVIEW", "FINAL_REVIEW"))
        render.assert_called_once()
        review = self.task.revisions.get(kind="review").payload
        self.assertFalse(review["passed"])
        self.assertEqual(review["approved_pending"]["conflicts"], ["重复行归属待确认"])
        self.assertEqual({issue["code"] for issue in review["issues"]},
                         {"unresolved_blueprint_items", "unresolved_input_items"})
        self.assertTrue(review["full_document_human_review_required"])
        self.task.pending_action = "write"
        self.assertFalse(_approved_pending_draft(self.task, self.blueprint))
        self.task.pending_action = "generate_outputs"
        self.blueprint.approvals.all().delete()
        self.assertFalse(_approved_pending_draft(self.task, self.blueprint))

    @patch("portal.product_worker.generate_for_use")
    def test_explicit_quantity_pending_approval_retains_body_findings_and_blocks_real_mismatch(self, model):
        from portal.product_worker import _DRAFT_QUANTITY_PENDING_CONDITION, _ensure_content_review
        from portal.product_documents import content_document
        self.input_payload["items"].extend([
            {"row_id": "r2", "name": "测试设备", "quantity": "3", "unit": "台"},
            {"row_id": "r3", "name": "变压器", "quantity": "5", "unit": "台"},
        ])
        for chapter in self.blueprint_payload["chapters"]:
            chapter["source_ids"] = ["r1", "r2", "r3"]
        self.blueprint_payload["conditions"].append(deepcopy(_DRAFT_QUANTITY_PENDING_CONDITION))
        self.queue_outputs()
        chapters = self.saved_chapters_for_continuation()
        original = deepcopy(chapters[0].payload)
        original["source_ids"] = ["r1", "r2", "r3"]
        chapters[0] = append_revision(self.task, "chapter", original, input_hash=self.input_revision.sha256,
                                      blueprint_hash=self.blueprint.sha256)
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": json.dumps({"passed": True, "issues": []})}
        review = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertFalse(review.payload["passed"])
        self.assertTrue(review.payload["full_document_human_review_required"])
        self.assertEqual(review.payload["approved_pending"]["quantity_issues"][0]["code"], "quantity_source_ambiguous")
        document = content_document(self.task, self.input_revision, self.blueprint, chapters, draft=True,
                                    review_issues=review.payload["issues"])
        self.assertIn("第1章第1段", document["pending"][0]["text"])
        self.assertIn("未经确认", document["pending"][0]["text"])
        chapters[0].refresh_from_db()
        self.assertEqual(chapters[0].payload, original)
        self.task.pending_action = "write"
        with self.assertRaises(ExecutionError):
            _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.task.pending_action = "generate_outputs"
        wrong = {**original, "paragraphs": ["变压器999台。"], "source_ids": ["r3"]}
        chapters[0] = append_revision(self.task, "chapter", wrong, input_hash=self.input_revision.sha256,
                                      blueprint_hash=self.blueprint.sha256)
        with self.assertRaises(ExecutionError) as error:
            _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertIn("quantity_mismatch", {issue["code"] for issue in error.exception.quality_issues})

    @patch("portal.product_worker.generate_for_use")
    def test_approved_source_expansion_preserves_saved_body_and_keeps_quantity_review(self, model):
        from portal.product_worker import _generate_family, _DRAFT_PENDING_CONDITION, _reuse_source_expansion_chapters
        self.input_payload["sources"] = [{"id": "reference"}]
        self.queue_outputs()
        saved = self.saved_chapters_for_continuation()
        original = deepcopy(saved[0].payload)
        original["paragraphs"] = ["清单中测试设备999台。"]
        saved[0] = append_revision(self.task, "chapter", original,
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        condition_only = deepcopy(self.blueprint.payload)
        condition_only["conditions"].append(deepcopy(_DRAFT_PENDING_CONDITION))
        condition_revision = append_revision(self.task, "blueprint", condition_only,
            input_hash=self.input_revision.sha256)
        self.task.blueprint_version = condition_revision.version
        self.task.save(update_fields=["blueprint_version"])
        DocumentApproval.objects.create(task=self.task, revision=condition_revision, actor=self.owner,
            decision="approve", sha256=condition_revision.sha256, authorization=approval_authorization(self.task, self.owner))
        self.assertEqual(_reuse_source_expansion_chapters(self.task, 1, self.input_revision,
                                                         condition_revision, "technical-solution", {}), {})
        payload = deepcopy(self.blueprint.payload)
        payload["chapters"][0]["source_ids"].append("reference")
        payload["conditions"].append(deepcopy(_DRAFT_PENDING_CONDITION))
        new = append_revision(self.task, "blueprint", payload, input_hash=self.input_revision.sha256)
        self.task.blueprint_version = new.version
        self.task.save(update_fields=["blueprint_version"])
        DocumentApproval.objects.create(task=self.task, revision=new, actor=self.owner, decision="approve",
            sha256=new.sha256, authorization=approval_authorization(self.task, self.owner))
        model.return_value = self.reply("chapter-1")
        task_id, fence, attempt_id = claim_task()
        result = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision, new, "technical-solution")
        model.assert_not_called()
        self.assertEqual(result[0].payload["paragraphs"], original["paragraphs"])
        self.assertEqual(result[0].blueprint_hash, new.sha256)
        saved[0].refresh_from_db()
        self.assertEqual(saved[0].payload, original)
        self.assertTrue(all(chapter.blueprint_hash == new.sha256 for chapter in result))
        self.assertIn("approved_source_scope_reuse", result[0].change_reason)
        self.assertIn("quantity_mismatch", {issue["code"] for issue in
            content_checks(self.input_revision.payload, new.payload, result)["issues"]})

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_batched_model_review_cannot_complete_without_full_human_review(self, model, render):
        self.input_payload["requirements"] = "完整约束待确认。" * 3000
        self.queue_outputs()
        model.side_effect = self.generation_replies()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "WAITING_REVIEW")
        render.assert_called_once()
        review = self.task.revisions.get(kind="review").payload
        self.assertEqual(review["model_review"]["status"], "passed")
        self.assertEqual(review["model_review"]["scope"], "full_batched")
        self.assertTrue(review["model_review"]["coverage"]["complete"])
        self.assertFalse(review["passed"])
        self.assertEqual(review["human_review"], "required")

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=70000)
    def test_review_contract_uses_all_body_counts_and_marks_samples_not_chapter_endings(self):
        from portal.product_worker import _review_payload
        for family, chapter_minimum, minimum in (("technical-solution", 6250, 50000), ("feasibility", 8750, 70000)):
            with self.subTest(family=family):
                counts = [chapter_minimum + index for index in range(8)]
                citation = "860a3e2c-7328-448f-a935-e1bb9bddc102"
                chapters = [SimpleNamespace(payload={"chapter_id": f"chapter-{index + 1}", "title": "项目设计",
                    "paragraphs": ["正文" * (count // 2) + ("文" if count % 2 else "") + " \n"],
                    "source_ids": [citation]}) for index, count in enumerate(counts)]
                request, scope = _review_payload(self.task, self.input_revision, self.blueprint, chapters, family)
                contract = request["review_contract"]
                self.assertEqual(scope, "sampled")
                self.assertEqual(contract["scope"], scope)
                self.assertEqual(contract["actual_body_characters"], sum(counts))
                self.assertEqual(contract["family_minimum_characters"], minimum)
                self.assertEqual(contract["body_characters_by_chapter"], counts)
                self.assertEqual(contract["chapter_count"], 8)
                self.assertEqual(contract["length_check_status"], "target_met")
                self.assertTrue(contract["full_document_human_review_required"])
                self.assertIn("片段末尾不是实际章节结尾", contract["sample_boundary"])
                self.assertIn("source_ids是合法引用元数据，不属于正文", contract["citation_boundary"])
                self.assertIn("不是已发现内容错误", contract["issues_boundary"])
                self.assertLessEqual(sum(len(item["sample"]) for item in request["chapters"]), 7000)
                self.assertLessEqual(len(json.dumps(request, ensure_ascii=False)), 14500)
                for position, item in enumerate(request["chapters"], 1):
                    self.assertTrue(item["sample_truncated"])
                    self.assertEqual(item["chapter_position"], position)
                    self.assertEqual(item["actual_characters"], counts[position - 1])
                    self.assertEqual(item["source_ids"], [citation])
                    self.assertNotIn(citation, item["sample"])

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000)
    def test_full_review_contract_reports_short_body_truthfully(self):
        from portal.product_worker import _review_payload
        chapters = [SimpleNamespace(payload={"chapter_id": "chapter-1", "title": "项目设计",
                                            "paragraphs": ["有 据 正 文\n"], "source_ids": ["r1"]})]
        request, scope = _review_payload(self.task, self.input_revision, self.blueprint, chapters, "technical-solution")
        contract = request["review_contract"]
        self.assertEqual(scope, "full")
        self.assertEqual(contract["actual_body_characters"], 4)
        self.assertEqual(contract["body_characters_by_chapter"], [4])
        self.assertEqual(contract["length_check_status"], "below_target")
        self.assertFalse(contract["full_document_human_review_required"])
        self.assertEqual(request["chapters"][0]["paragraphs"], ["有 据 正 文\n"])

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000)
    def test_fallback_review_keeps_authoritative_counts_and_explicit_truncation_within_budget(self):
        from portal.product_worker import _review_payload
        blueprint = SimpleNamespace(payload={**self.blueprint.payload,
            "conditions": [{"text": "长输入条件" * 200, "type": "human"}] * 30})
        chapters = [SimpleNamespace(payload={"chapter_id": f"chapter-{index}", "title": "项目设计",
                                            "paragraphs": ["正文" * 4000], "source_ids": ["r1"]}) for index in range(8)]
        request, scope = _review_payload(self.task, self.input_revision, blueprint, chapters, "technical-solution")
        self.assertEqual(scope, "sampled")
        self.assertEqual(request["conditions"], [])
        self.assertEqual(request["review_contract"]["actual_body_characters"], 64000)
        self.assertEqual(request["review_contract"]["body_characters_by_chapter"], [8000] * 8)
        self.assertEqual(request["review_contract"]["length_check_status"], "target_met")
        self.assertTrue(all(item["sample_truncated"] and len(item["sample"]) <= 500 for item in request["chapters"]))
        self.assertLessEqual(len(json.dumps(request, ensure_ascii=False)), 14500)

    def test_oversized_review_contract_fails_before_model_dispatch(self):
        from portal.product_worker import _review_payload
        blueprint = SimpleNamespace(payload={**self.blueprint.payload, "missing": ["未决事项" * 500] * 20})
        chapters = [SimpleNamespace(payload=json.loads(self.reply("chapter-1")["content"]))]
        with self.assertRaises(ExecutionError) as error:
            _review_payload(self.task, self.input_revision, blueprint, chapters, "technical-solution")
        self.assertEqual(error.exception.code, "request_too_large")

    @override_settings(PRODUCT_TECHNICAL_TARGET_CHARACTERS=50000)
    @patch("portal.product_content_quality.content_review_prompt", return_value="审查" * 3500)
    def test_oversized_unused_samples_do_not_block_complete_review_batches(self, prompt):
        from portal.product_worker import _review_batch_payloads, _review_payload, _review_request_size
        chapters = [SimpleNamespace(payload={"chapter_id": f"chapter-{index}", "title": "项目设计",
                    "source_ids": ["r1"], "paragraphs": [f"章节{index}正文。" + "文" * 5400]}) for index in range(10)]
        payload, scope = _review_payload(self.task, self.input_revision, self.blueprint, chapters, "technical-solution")
        self.assertEqual(scope, "sampled")
        self.assertEqual(payload["chapters"], [])
        plan = _review_batch_payloads(payload, chapters)
        body = [{"chapter_id": chapter.payload["chapter_id"], "paragraphs": chapter.payload["paragraphs"]} for chapter in chapters]
        recovered = {chapter.payload["chapter_id"]: "" for chapter in chapters}
        for batch in plan:
            self.assertLessEqual(_review_request_size(batch), 14500)
            self.assertEqual(batch["review_contract"]["body_sha256"], digest(body))
            for chapter in batch["chapters"]:
                fragment = chapter["fragment"]
                saved = recovered[chapter["chapter_id"]]
                self.assertEqual(fragment["start"], len(saved))
                recovered[chapter["chapter_id"]] += chapter["paragraphs"][0]
                self.assertEqual(fragment["end"], len(recovered[chapter["chapter_id"]]))
        self.assertEqual(recovered, {chapter.payload["chapter_id"]: chapter.payload["paragraphs"][0] for chapter in chapters})

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview")
    @patch("portal.product_three_drafts.generate_report_drafts")
    @patch("portal.product_worker.generate_for_use")
    def test_batched_review_contract_preserves_real_commitment_findings(self, model, render):
        self.input_payload["requirements"] = "完整约束待确认。" * 3000
        self.queue_outputs(missing=["预算待确认"])
        model.side_effect = self.generation_replies(passed=False, issues=["正文存在未经确认的安全实现承诺"])
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_REVIEW", ""))
        render.assert_called_once()
        request = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(request["review_contract"]["scope"], "full_batched")
        review = self.task.revisions.get(kind="review").payload
        self.assertEqual(review["model_review"]["status"], "issues_found")
        self.assertEqual(review["model_review"]["issues"], ["正文存在未经确认的安全实现承诺"])
        self.assertFalse(review["passed"])
        self.assertTrue(review["model_review"]["full_document_human_review_required"])

    def long_review_chapters(self):
        return [SimpleNamespace(payload={"chapter_id": chapter["id"], "title": chapter["title"], "source_ids": ["r1"],
            "paragraphs": ["章首设计与约束。" * 1800 + "正文尾部真实风险证据。", "后续设计建议须结合完整项目资料核对。"]})
            for chapter in self.blueprint_payload["chapters"]]

    @patch("portal.product_worker.generate_for_use")
    def test_full_batched_review_covers_every_paragraph_tail_with_bounded_requests_and_hashes(self, model):
        from portal.product_worker import _review_family
        chapters = self.long_review_chapters()
        model.return_value = {"content": json.dumps({"passed": True, "issues": []})}
        task_id, fence, attempt_id = claim_task()
        reviewed = _review_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint,
                                  chapters, "technical-solution")
        requests = [json.loads(call.args[2][1]["content"]) for call in model.call_args_list]
        self.assertGreater(len(requests), 1)
        self.assertEqual(reviewed["scope"], "full_batched")
        self.assertEqual(reviewed["status"], "passed")
        self.assertTrue(reviewed["full_document_human_review_required"])
        self.assertTrue(reviewed["coverage"]["complete"])
        self.assertTrue(reviewed["coverage"]["all_batches_passed"])
        self.assertEqual(reviewed["coverage"]["batch_count"], model.call_count)
        self.assertEqual(DocumentAttempt.objects.get(pk=attempt_id).model_calls, model.call_count)
        assembled = {}
        for batch_index, request in enumerate(requests, 1):
            self.assertLessEqual(len(json.dumps(request, ensure_ascii=False)), 14500)
            self.assertLessEqual(sum(len(text) for chapter in request["chapters"] for text in chapter["paragraphs"]), 7000)
            self.assertEqual(request["review_contract"]["batch_index"], batch_index)
            self.assertEqual(request["review_contract"]["batch_count"], len(requests))
            self.assertIn("截取边界不是原段尾", request["review_contract"]["batch_boundary"])
            for chapter in request["chapters"]:
                fragment = chapter["fragment"]
                key = (chapter["chapter_id"], fragment["paragraph_index"])
                text = chapter["paragraphs"][0]
                self.assertEqual(fragment["start"], len(assembled.get(key, "")))
                self.assertEqual(fragment["end"] - fragment["start"], len(text))
                assembled[key] = assembled.get(key, "") + text
        for chapter in chapters:
            for index, paragraph in enumerate(chapter.payload["paragraphs"], 1):
                self.assertEqual(assembled[(chapter.payload["chapter_id"], index)], paragraph)
        coverage = reviewed["coverage"]
        self.assertEqual(coverage["raw_characters"], sum(map(len, assembled.values())))
        self.assertEqual(coverage["input_sha256"], self.input_revision.sha256)
        self.assertEqual(coverage["blueprint_sha256"], self.blueprint.sha256)
        for batch, request in zip(coverage["batches"], requests):
            self.assertEqual(batch["request_sha256"], digest(request))
            for fragment, sent in zip(batch["fragments"], request["chapters"]):
                self.assertEqual(fragment["text_sha256"], digest(sent["paragraphs"]))

    @patch("portal.product_worker.generate_for_use")
    def test_full_batched_review_preserves_issues_found_only_at_late_paragraph_ends(self, model):
        from portal.product_worker import _review_family
        def review(*args):
            request = json.loads(args[2][1]["content"])
            found = any("正文尾部真实风险证据" in text for chapter in request["chapters"] for text in chapter["paragraphs"])
            return {"content": json.dumps({"passed": not found, "issues": ["正文尾部存在实质风险"] if found else []})}
        model.side_effect = review
        task_id, fence, attempt_id = claim_task()
        reviewed = _review_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint,
                                  self.long_review_chapters(), "technical-solution")
        self.assertEqual(reviewed["status"], "issues_found")
        self.assertEqual(reviewed["issues"], ["正文尾部存在实质风险"])
        self.assertTrue(reviewed["coverage"]["complete"])
        self.assertFalse(reviewed["coverage"]["all_batches_passed"])
        self.assertTrue(any(batch["issues"] for batch in reviewed["coverage"]["batches"]))

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_full_batched_review_preserves_call_limit_and_never_claims_partial_coverage_complete(self, model):
        from portal.product_worker import _review_family
        model.return_value = {"content": json.dumps({"passed": True, "issues": []})}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _review_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint,
                           self.long_review_chapters(), "technical-solution")
        self.assertEqual(error.exception.code, "model_call_limit")
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="review").exists())
        self.task.refresh_from_db()
        progress = self.task.checkpoint["analysis_progress"]["review_technical"]
        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["completed_count"], 1)
        self.assertGreater(progress["total_count"], 1)

    @patch("portal.product_worker.generate_for_use")
    def test_full_batched_review_revocation_discards_response_and_stops_other_batches(self, model):
        from portal.product_worker import _review_family
        def revoke(*args):
            self.owner.roles.clear()
            return {"content": json.dumps({"passed": True, "issues": []})}
        model.side_effect = revoke
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _review_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint,
                           self.long_review_chapters(), "technical-solution")
        self.assertEqual(error.exception.code, "permission_changed")
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="review").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_full_batched_review_fence_change_discards_response_and_stops_other_batches(self, model):
        from portal.product_worker import _review_family
        def cancel(*args):
            self.task.refresh_from_db()
            self.task.fence += 1
            self.task.state = "CANCELLED"
            self.task.lease_until = None
            self.task.save(update_fields=["fence", "state", "lease_until"])
            return {"content": json.dumps({"passed": True, "issues": []})}
        model.side_effect = cancel
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _review_family(task_id, fence, attempt_id, self.task, self.input_revision, self.blueprint,
                           self.long_review_chapters(), "technical-solution")
        self.assertEqual(error.exception.code, "lease_lost")
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="review").exists())

    def test_empty_batched_review_cannot_vacuously_pass(self):
        from portal.product_worker import _review_batch_payloads, _review_payload
        payload, scope = _review_payload(self.task, self.input_revision, self.blueprint, [], "technical-solution")
        with self.assertRaises(ExecutionError) as error:
            _review_batch_payloads(payload, [])
        self.assertEqual(error.exception.code, "chapters_incomplete")

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_generated_unsupported_chinese_period_is_corrected_in_shared_retry_before_storage(self, model, render):
        invalid = json.loads(self.reply("chapter-1")["content"])
        retained_analysis = "独立候选分析应保留：实施前向业务负责人核对采集权限，并记录字段映射与验收依据。"
        invalid["paragraphs"] = ["数据备份保留三十天。", retained_analysis]
        corrected = {**invalid, "paragraphs": ["数据备份保留期尚未提供，须由业务负责人确认后制定候选方案。", retained_analysis]}
        model.side_effect = [{"content": json.dumps(invalid)}, {"content": json.dumps(corrected)},
                             self.reply("chapter-2"), self.reply("chapter-3"), {"content": '{"passed":true,"issues":[]}'}]
        render.return_value = self.rendered()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "")
        request = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("content_quality_correction", request)
        self.assertIn("三十天", str(request["content_quality_correction"]))
        self.assertNotIn("未通过JSON解析", request["json_format_correction"])
        self.assertIn("length_target.this_response_characters", request["chapter_validation_correction"])
        self.assertIn("新增正文仅指paragraphs字段", request["chapter_validation_correction"])
        self.assertIn("输入输出与验证方法", request["chapter_validation_correction"])
        self.assertEqual(request["length_target"], json.loads(model.call_args_list[0].args[2][1]["content"])["length_target"])
        self.assertNotIn("content_quality_rules", request)
        messages = model.call_args_list[1].args[2]
        self.assertEqual(len(messages), 3)
        candidate_message = json.loads(messages[2]["content"])
        self.assertEqual(candidate_message["unaccepted_chapter_candidate"], invalid)
        self.assertIn("尚未通过质量校验", candidate_message["candidate_boundary"])
        self.assertIn("定点纠错", messages[0]["content"])
        self.assertIn("未列出问题的文字也不代表已通过", messages[0]["content"])
        self.assertNotIn("unaccepted_chapter_candidate", request)
        self.assertEqual(len(model.call_args_list[0].args[2]), 2)
        candidate_evidence = self.task.checkpoint["calls"][1]["chapter_correction_candidate"]
        self.assertEqual(candidate_evidence["sha256"], digest(invalid))
        self.assertEqual(self.task.checkpoint["calls"][1]["input_hash"],
                         digest({"payload": request, "chapter_correction_candidate_sha256": digest(invalid)}))
        self.assertNotEqual(self.task.checkpoint["calls"][1]["input_hash"], digest(request))
        self.assertTrue(self.task.checkpoint["calls"][1]["response_validated"])
        self.assertNotIn(retained_analysis, json.dumps(self.task.checkpoint, ensure_ascii=False))
        self.assertTrue(all(len(call.args[2]) == 2 for call in model.call_args_list[2:]))
        from portal.product_content_quality import generation_quality_rules
        self.assertEqual(model.call_args_list[1].args[2][0]["content"].count(generation_quality_rules()), 1)
        for call in model.call_args_list:
            self.assertIn("其确认授权目录、分析范围与原条件", call.args[2][0]["content"])
            self.assertIn("审核不能仅因正文未承认蓝图预设就判范围不符", call.args[2][0]["content"])
        saved = current_chapters(self.task, self.input_revision.sha256, self.blueprint.sha256)["chapter-1"]
        self.assertEqual(saved.payload["paragraphs"], corrected["paragraphs"])
        self.assertEqual(self.task.revisions.filter(kind="chapter", payload__chapter_id="chapter-1").count(), 1)

    @patch("portal.product_worker.generate_for_use")
    def test_semantic_candidate_is_copied_before_validator_mutation(self, model):
        from portal.product_worker import _model
        candidate = json.loads(self.reply("chapter-1")["content"])
        candidate["paragraphs"] = ["数据备份保留三十天。", "原始完整分析必须保留。"]
        corrected = {**candidate, "paragraphs": ["保留期须确认。", candidate["paragraphs"][1]]}
        model.side_effect = [{"content": json.dumps(candidate)}, {"content": json.dumps(corrected)}]
        checked = []
        def validate(result):
            checked.append(deepcopy(result))
            if len(checked) == 1:
                result["paragraphs"][1] = "validator mutation must not enter candidate"
                raise ExecutionError("invalid_model_output", quality_issues=[{
                    "code": "unsupported_parameter", "claim": "数据备份保留三十天", "correction": "核对保留期"}])
            return result
        task_id, fence, attempt_id = claim_task()
        result = _model(task_id, fence, attempt_id, "product_writing", {
            "action": "chapter", "chapter": self.blueprint_payload["chapters"][0], "schema": candidate,
            "length_target": {"this_response_characters": 600}}, output_validator=validate)
        self.assertEqual(result, corrected)
        self.assertEqual(model.call_count, 2)
        attached = json.loads(model.call_args_list[1].args[2][2]["content"])["unaccepted_chapter_candidate"]
        self.assertEqual(attached, candidate)
        self.assertNotIn("validator mutation", json.dumps(attached))

    @patch("portal.product_worker.generate_for_use")
    def test_semantic_candidate_correction_still_rejects_new_unsupported_status(self, model):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["数据备份保留三十天。", "完整候选有效分析标记。"]
        new_invalid = {**invalid, "paragraphs": ["现有系统存在严重的数据孤岛。", invalid["paragraphs"][1]]}
        model.side_effect = [{"content": json.dumps(invalid)}, {"content": json.dumps(new_invalid)}]
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("FAILED", "invalid_model_output"))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(len(model.call_args_list[1].args[2]), 3)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.assertFalse(self.task.artifacts.exists())
        self.assertIn("unsupported_project_status", {issue["code"] for issue in self.task.checkpoint["calls"][1]["quality_issues"]})
        self.assertNotIn(invalid["paragraphs"][1], json.dumps(self.task.checkpoint, ensure_ascii=False))

    @patch("portal.product_worker.generate_for_use")
    def test_semantic_candidate_oversize_falls_back_to_original_generation_without_truncation(self, model):
        from portal.product_worker import _model
        candidate = json.loads(self.reply("chapter-1")["content"])
        task_id, fence, attempt_id = claim_task()
        for candidate_size, input_size in ((13000, 0), (20, 15000)):
            with self.subTest(candidate_size=candidate_size, input_size=input_size):
                invalid = {**candidate, "paragraphs": ["文" * candidate_size]}
                model.reset_mock()
                model.side_effect = [{"content": json.dumps(invalid)}, self.reply("chapter-1")]
                validation_calls = []
                def validate(result):
                    validation_calls.append(result)
                    if len(validation_calls) == 1:
                        raise ExecutionError("invalid_model_output", quality_issues=[{
                            "code": "unsupported_parameter", "claim": "fixture", "correction": "fix"}])
                    return result
                result = _model(task_id, fence, attempt_id, "product_writing", {
                    "action": "chapter", "chapter": self.blueprint_payload["chapters"][0], "schema": candidate,
                    "input": {"background": "资" * input_size}}, output_validator=validate)
                self.assertEqual(result, candidate)
                self.assertEqual(model.call_count, 2)
                self.assertEqual(len(model.call_args_list[1].args[2]), 2)
                self.assertNotIn("定点纠错", model.call_args_list[1].args[2][0]["content"])
                self.task.refresh_from_db()
                self.assertNotIn("chapter_correction_candidate", self.task.checkpoint["calls"][-1])

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_semantic_candidate_correction_cannot_bypass_model_call_budget(self, model):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["数据备份保留三十天。"]
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual((self.task.state, self.task.error_code), ("WAITING_INPUT", "model_call_limit"))
        model.assert_called_once()
        self.assertEqual(DocumentAttempt.objects.get(task=self.task).model_calls, 1)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_semantic_candidate_correction_cannot_bypass_permission_gate(self, model):
        from portal.product_worker import _model
        invalid = json.loads(self.reply("chapter-1")["content"])
        model.return_value = {"content": json.dumps(invalid)}
        task_id, fence, attempt_id = claim_task()
        def revoke_then_reject(result):
            self.owner.roles.clear()
            raise ExecutionError("invalid_model_output", quality_issues=[{
                "code": "unsupported_parameter", "claim": "fixture", "correction": "fix"}])
        with self.assertRaises(ExecutionError):
            _model(task_id, fence, attempt_id, "product_writing", {
                "action": "chapter", "chapter": self.blueprint_payload["chapters"][0], "schema": invalid},
                output_validator=revoke_then_reject)
        model.assert_called_once()
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("langsmith.tracing_context")
    @patch("portal.product_worker.generate_for_use")
    def test_chapter_gateway_and_parser_disable_local_tracing_without_changing_other_actions(self, model, tracing):
        from portal.product_worker import _model
        task_id, fence, attempt_id = claim_task()
        for action, result in (("chapter", json.loads(self.reply("chapter-1")["content"])),
                               ("blueprint", {"purpose": "fixture"}), ("diagram", {"figures": []}),
                               ("independent_review", {"passed": True, "issues": []})):
            with self.subTest(action=action):
                tracing.reset_mock()
                model.return_value = {"content": json.dumps(result)}
                _model(task_id, fence, attempt_id, "product_writing", {"action": action, "schema": result})
                if action == "chapter":
                    self.assertEqual(tracing.call_count, 2)
                    self.assertTrue(all(call.kwargs == {"enabled": False} for call in tracing.call_args_list))
                else:
                    tracing.assert_not_called()

    @patch("portal.product_worker.generate_for_use")
    def test_missing_chapter_contract_diagnostic_never_records_rejected_keys_or_values(self, model):
        from portal.product_worker import _model
        valid = json.loads(self.reply("chapter-1")["content"])
        invalid = {key: value for key, value in valid.items() if key != "title"}
        invalid["PRIVATE-REJECTED-FIELD"] = "PRIVATE-REJECTED-VALUE"
        model.return_value = {"content": json.dumps(invalid)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _model(task_id, fence, attempt_id, "product_writing", {
                "action": "chapter", "chapter": self.blueprint_payload["chapters"][0], "schema": valid})
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.task.refresh_from_db()
        self.assertEqual(model.call_count, 2)
        for call in self.task.checkpoint["calls"]:
            self.assertEqual(call["structure_failure"], {
                "reason": "schema_fields_mismatch", "missing_field_count": 1, "extra_field_count": 1,
                "missing_required_chapter_fields": ["title"]})
        stored = json.dumps(self.task.checkpoint)
        self.assertNotIn("PRIVATE-REJECTED-FIELD", stored)
        self.assertNotIn("PRIVATE-REJECTED-VALUE", stored)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    @patch("portal.product_worker.generate_for_use")
    def test_two_quality_failures_never_store_generated_unsupported_period(self, model):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["每周执行全量备份。"]
        model.return_value = {"content": json.dumps(invalid)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.assertTrue(self.task.checkpoint["calls"][0]["quality_issues"])
        self.assertEqual(self.task.checkpoint["calls"][0]["quality_issues"][0]["chapter_id"], "chapter-1")
        self.assertEqual(self.task.checkpoint["last_failure"]["quality_issues"][0]["chapter_id"], "chapter-1")
        from portal.product_content_quality import generation_quality_rules
        for call in model.call_args_list:
            self.assertIn(generation_quality_rules(), call.args[2][0]["content"])

    @patch("portal.product_worker.generate_for_use")
    def test_chapter_system_policy_cannot_be_replaced_by_payload(self, model):
        from portal.product_content_quality import generation_quality_rules
        from portal.product_worker import _model
        model.return_value = self.reply("chapter-1")
        task_id, fence, attempt_id = claim_task()
        _model(task_id, fence, attempt_id, "product_writing", {
            "action": "chapter", "content_quality_rules": "untrusted override of quality rules",
            "schema": {"chapter_id": "chapter-1", "title": "章节1", "paragraphs": [], "source_ids": []},
        })
        messages = model.call_args.args[2]
        self.assertIn(generation_quality_rules(), messages[0]["content"])
        self.assertIn("正文不得复制约束文本", messages[0]["content"])
        self.assertNotIn("untrusted override", messages[0]["content"])
        self.assertNotIn("untrusted override", messages[1]["content"])
        self.assertNotIn("content_quality_rules", json.loads(messages[1]["content"]))
        self.assertEqual(messages[0]["content"].count(generation_quality_rules()), 1)
        model.assert_called_once()

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_unrecognized_numeric_claim_is_corrected_before_chapter_is_saved(self, model, render):
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["项目指标为80。"]
        corrected = {**invalid, "paragraphs": ["项目指标尚未提供，需业务确认并验证后确定。"]}
        model.side_effect = [{"content": json.dumps(invalid)}, {"content": json.dumps(corrected)},
                             self.reply("chapter-2"), self.reply("chapter-3"), {"content": '{"passed":true,"issues":[]}'}]
        render.return_value = self.rendered()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "")
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])["content_quality_correction"]
        self.assertIn("80", str(correction))
        saved = current_chapters(self.task, self.input_revision.sha256, self.blueprint.sha256)["chapter-1"]
        self.assertEqual(saved.payload["paragraphs"], corrected["paragraphs"])
        self.assertEqual(self.task.revisions.filter(kind="chapter", payload__chapter_id="chapter-1").count(), 1)

    def test_project_number_whitelist_excludes_metadata_requirements_and_public_reference(self):
        chapter = SimpleNamespace(payload={"chapter_id": "chapter-1", "title": "项目设计",
                                           "paragraphs": ["候选端口设置为9080，须另行确认。"], "source_ids": ["r1"]})
        facts = {**self.input_payload, "requirements": "生成设计使用9080作为示例", "version": 9080,
                 "sources": [{"id": "source-9080", "text": "公开文档示例端口9080"}]}
        result = content_checks(facts, self.blueprint_payload, [chapter])
        self.assertTrue(any(issue["code"] == "unsupported_number" and issue["chapter_id"] == "chapter-1"
                            for issue in result["issues"]))

    @patch("portal.product_three_drafts.verified_artifact")
    @patch("portal.product_three_drafts.render_report_draft")
    def test_cached_three_drafts_cannot_bypass_current_quality_guard(self, render, verified):
        from portal.product_pair import _report_generation_hash
        from portal.product_three_drafts import generate_report_drafts
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                                   input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        bad = {**chapters[0].payload, "paragraphs": ["每日执行数据备份。"]}
        append_revision(self.task, "chapter", bad, input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        report_hash = _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint)
        DocumentArtifact.objects.create(task=self.task, family="technical-solution", version=1,
            path=f"{self.task.pk}/old.docx", sha256="a" * 64, input_hash=self.input_revision.sha256,
            blueprint_hash=self.blueprint.sha256, generation_hash=report_hash)
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            generate_report_drafts(self.task, fence, attempt_id, self.input_revision, self.blueprint)
        self.assertEqual(error.exception.code, "content_review_required")
        render.assert_not_called()
        verified.assert_not_called()
        self.assertEqual(self.task.artifacts.count(), 1)

    @patch("portal.product_documents.render_draft")
    def test_legacy_render_rechecks_old_passed_review_before_any_artifact_reuse(self, render):
        from portal.product_worker import _render
        bad = {**json.loads(self.reply("chapter-1")["content"]), "paragraphs": ["每日执行数据备份。"]}
        chapter = append_revision(self.task, "chapter", bad, input_hash=self.input_revision.sha256,
                                  blueprint_hash=self.blueprint.sha256)
        append_revision(self.task, "review", {"passed": True, "issues": [], "chapter_hashes": {"chapter-1": chapter.sha256},
                        "model_review": {"status": "passed", "scope": "full"}},
                        input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _render(self.task, fence, attempt_id, self.input_revision, self.blueprint, [chapter])
        self.assertEqual(error.exception.code, "content_review_required")
        render.assert_not_called()
        self.assertFalse(self.task.artifacts.exists())

    def test_report_generation_hash_changes_with_quality_policy(self):
        from portal.product_pair import _report_generation_hash
        for chapter in self.blueprint_payload["chapters"]:
            append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        with patch("portal.product_content_quality.content_quality_policy_hash", return_value="a" * 64):
            first = _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint)
        with patch("portal.product_content_quality.content_quality_policy_hash", return_value="b" * 64):
            second = _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint)
        self.assertNotEqual(first, second)

    @patch("portal.product_worker.generate_for_use")
    def test_report_cache_changes_after_call_evidence_invalidates_same_body_review(self, model):
        from portal.product_pair import _report_generation_hash
        from portal.product_worker import _ensure_content_review
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        first = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        old_hash = _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint)
        old = DocumentArtifact.objects.create(task=self.task, family="technical-solution", version=1,
            path=f"{self.task.pk}/historical.docx", sha256="a" * 64, review=first,
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256, generation_hash=old_hash)
        self.task.refresh_from_db()
        self.task.checkpoint["calls"][0]["response_sha256"] = "0" * 64
        self.task.save(update_fields=["checkpoint"])
        self.assertNotEqual(old_hash, _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint))
        second = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        new_hash = _report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(old_hash, new_hash)
        self.assertEqual(model.call_count, 2)
        old.refresh_from_db()
        self.assertEqual((old.review_id, old.generation_hash, old.sha256), (first.pk, old_hash, "a" * 64))

    @patch("portal.product_worker.generate_for_use")
    def test_current_complete_real_review_is_reused_without_another_model_call(self, model):
        from portal.product_worker import _ensure_content_review
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        first = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        second = _ensure_content_review(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertEqual(first.pk, second.pk)
        model.assert_called_once()
        self.assertEqual(self.task.revisions.filter(kind="review").count(), 1)

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_same_chapter_hash_old_policy_review_requires_real_current_review(self, model, render):
        from portal.product_worker import _render
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                                   input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        append_revision(self.task, "review", {"passed": True, "issues": [],
            "chapter_hashes": {chapter.payload["chapter_id"]: chapter.sha256 for chapter in chapters},
            "quality_policy_sha256": "legacy-policy", "model_review": {"status": "passed", "scope": "full"}},
            input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        render.return_value = self.rendered()
        _render(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        from portal.product_content_quality import content_quality_policy_hash
        review = self.task.artifacts.get().review.payload
        self.assertEqual(review["quality_policy_sha256"], content_quality_policy_hash())
        model.assert_called_once()
        self.assertTrue(review["passed"])
        self.assertEqual(review["model_review"]["status"], "passed")
        self.assertTrue(review["model_review"]["coverage"]["complete"])

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=False)
    @patch("portal.product_worker.generate_for_use")
    def test_external_permission_closed_without_outbound(self, model):
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "WAITING_INPUT")
        self.assertEqual(self.task.error_code, "model_authorization_required")
        model.assert_not_called()

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_truncated_chapter_is_failure_and_completed_chapters_resume(self, model, render):
        model.side_effect = [self.reply("chapter-1"), self.reply("chapter-2"), GatewayError("output_truncated")]
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "QUEUED")
        self.assertEqual(self.task.error_code, "step_retry_pending")
        self.assertEqual(self.task.checkpoint["last_failure"]["cause_code"], "output_truncated")
        self.assertEqual(len(current_chapters(self.task, self.input_revision.sha256, self.blueprint.sha256)), 2)
        self.assertEqual(DocumentArtifact.objects.count(), 0)
        self.task.state = "QUEUED"
        self.task.retry_after = timezone.now() - timedelta(seconds=1)
        self.task.save()
        from portal.product_models import DocumentStep
        DocumentStep.objects.filter(task=self.task).update(retry_after=timezone.now() - timedelta(seconds=1))
        model.reset_mock()
        model.side_effect = [self.reply("chapter-3"), {"content": '{"passed":true,"issues":[]}'}]
        render.return_value = self.rendered()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "WAITING_REVIEW")
        self.assertEqual(self.task.stage, "FINAL_REVIEW")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(DocumentArtifact.objects.count(), 1)
        self.assertEqual(DocumentApproval.objects.filter(artifact__isnull=False).count(), 0)

    @patch("portal.product_worker.generate_for_use")
    def test_cancellation_fences_inflight_output(self, model):
        def cancel(*args):
            self.task.refresh_from_db()
            self.task.fence += 1
            self.task.state = "CANCELLED"
            self.task.lease_until = None
            self.task.save()
            return self.reply("chapter-1")
        model.side_effect = cancel
        run_once()
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.assertEqual(DocumentAttempt.objects.get().status, "cancelled")

    @patch("portal.product_worker.generate_for_use")
    def test_revocation_before_model_call_refuses(self, model):
        self.owner.roles.clear()
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "FAILED")
        model.assert_not_called()

    def test_expired_lease_reclaims_with_new_fence_and_late_write_rejected(self):
        first = claim_task()
        self.task.refresh_from_db()
        self.task.lease_until = timezone.now() - timedelta(seconds=1)
        self.task.save()
        second = claim_task()
        self.assertGreater(second[1], first[1])
        with self.assertRaises(ExecutionError):
            with transaction.atomic():
                _store(first[0], first[1], "chapter", {}, self.input_revision.sha256, self.blueprint.sha256)
        self.assertEqual(DocumentAttempt.objects.get(pk=first[2]).error_code, "lease_expired")

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_task_model_budget_is_bounded(self, model):
        model.return_value = self.reply("chapter-1")
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "WAITING_INPUT")
        self.assertEqual(self.task.error_code, "model_call_limit")
        self.assertEqual(model.call_count, 1)

    def test_attempt_limit_closes_expired_running_attempt(self):
        task_id, fence, attempt_id = claim_task()
        self.task.refresh_from_db()
        self.task.attempt_count = 8
        self.task.lease_until = timezone.now() - timedelta(seconds=1)
        self.task.save()
        self.assertIsNone(claim_task())
        self.task.refresh_from_db()
        self.assertIsNone(self.task.lease_until)
        self.assertGreater(self.task.fence, fence)
        self.assertEqual(DocumentAttempt.objects.get(pk=attempt_id).status, "failed")

    @patch("portal.product_worker.generate_for_use")
    def test_model_cannot_expand_blueprint_source_scope(self, model):
        payload = json.loads(self.reply("chapter-1")["content"])
        payload["source_ids"] = ["unapproved-source"]
        model.return_value = {"content": json.dumps(payload)}
        run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.error_code, "invalid_model_output")
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())

    def test_unknown_number_and_missing_citations_require_review(self):
        chapter = append_revision(self.task, "chapter", {"chapter_id": "chapter-1", "title": "章节", "paragraphs": ["新增999台设备"], "source_ids": []}, input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        result = content_checks(self.input_payload, self.blueprint_payload, [chapter])
        self.assertFalse(result["passed"])
        self.assertEqual({issue["code"] for issue in result["issues"]},
                         {"source_review_required", "unsupported_number", "unsupported_parameter"})

    @patch("portal.product_worker.generate_for_use")
    def test_owner_revocation_prevents_approved_work(self, model):
        self.owner.roles.clear()
        run_once()
        self.task.refresh_from_db()
        self.assertIn(self.task.error_code, {"blueprint_approval_required", "permission_changed"})
        model.assert_not_called()

    @patch("portal.product_worker.generate_for_use")
    def test_owner_revocation_during_call_discards_output(self, model):
        def revoke(*args):
            self.owner.roles.clear()
            return self.reply("chapter-1")
        model.side_effect = revoke
        run_once()
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_manual_change_does_not_reuse_prior_model_review(self, model, render):
        from portal.product_worker import _render

        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256) for chapter in self.blueprint_payload["chapters"]]
        append_revision(self.task, "review", {"passed": True, "issues": [], "chapter_hashes": {"chapter-1": "old-hash"}},
                        input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":true,"issues":[]}'}
        render.return_value = self.rendered()
        _render(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        review = DocumentArtifact.objects.get().review
        model.assert_called_once()
        self.assertTrue(review.payload["passed"])
        self.assertEqual(review.payload["model_review"]["status"], "passed")
        self.assertTrue(review.payload["model_review"]["coverage"]["complete"])

    @patch("portal.product_documents.render_draft")
    @patch("portal.product_worker.generate_for_use")
    def test_legacy_render_actual_model_findings_block_current_policy_body(self, model, render):
        from portal.product_worker import _render
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        task_id, fence, attempt_id = claim_task()
        model.return_value = {"content": '{"passed":false,"issues":["正文中的来源归属需要纠正"]}'}
        with self.assertRaises(ExecutionError) as error:
            _render(self.task, fence, attempt_id, self.input_revision, self.blueprint, chapters)
        self.assertEqual(error.exception.code, "content_review_required")
        model.assert_called_once()
        render.assert_not_called()
        actual = self.task.revisions.filter(kind="review").latest("version").payload["model_review"]
        self.assertEqual(actual["status"], "issues_found")
        self.assertEqual(actual["issues"], ["正文中的来源归属需要纠正"])

    def queue_numbered_outline(self):
        for chapter, title in zip(self.blueprint_payload["chapters"],
                                  ["第一章 项目背景", "第二章 现状调查", "第三章 总体架构"]):
            chapter["title"] = title
        self.queue_outputs()

    @patch("portal.product_worker.generate_for_use")
    def test_wrong_cross_chapter_mapping_gets_one_correction_and_is_not_saved(self, model):
        from portal.product_worker import _generate_family
        self.queue_numbered_outline()
        self.task.pending_action = "write"
        self.task.save(update_fields=["pending_action"])
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["接口设计在第二章 数据存储方案展开。"]
        model.return_value = {"content": json.dumps(invalid)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                             self.blueprint, "technical-solution")
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        expected = [{"id": chapter["id"], "title": chapter["title"]}
                    for chapter in self.blueprint_payload["chapters"]]
        for call in model.call_args_list:
            self.assertEqual(json.loads(call.args[2][1]["content"])["approved_blueprint"]["chapters"], expected)
            self.assertIn("不按经验推测章号与主题", call.args[2][0]["content"])
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("approved_chapter_reference_mismatch", str(correction["content_quality_correction"]))

    @patch("portal.product_worker.generate_for_use")
    def test_exact_approved_reference_is_saved_with_sources_unchanged(self, model):
        from portal.product_worker import _generate_family
        self.queue_numbered_outline()
        legal = json.loads(self.reply("chapter-1")["content"])
        legal["paragraphs"] = ["现状资料在第二章 现状调查核实，候选职责在第三章 总体架构展开。"]
        model.side_effect = [{"content": json.dumps(legal)}, self.reply("chapter-2"), self.reply("chapter-3")]
        task_id, fence, attempt_id = claim_task()
        chapters = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                                    self.blueprint, "technical-solution")
        self.assertEqual(model.call_count, 3)
        self.assertEqual(chapters[0].payload, legal)
        self.assertEqual(chapters[0].blueprint_hash, self.blueprint.sha256)
        self.assertEqual(chapters[0].input_hash, self.input_revision.sha256)

    @patch("portal.product_worker.generate_for_use")
    def test_split_quote_is_corrected_as_complete_batch_before_save(self, model):
        from portal.product_worker import _generate_family
        self.queue_numbered_outline()
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["建设目标不能由", "统一", "这一目标预设现状能力。"]
        legal = {**invalid, "paragraphs": ["建设目标不能由“统一”这一目标预设现状能力。",
                                            "调查应记录已有接口及其依据，由项目方确认实施范围。"]}
        model.side_effect = [{"content": json.dumps(invalid)}, {"content": json.dumps(legal)},
                             self.reply("chapter-2"), self.reply("chapter-3")]
        task_id, fence, attempt_id = claim_task()
        chapters = _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                                    self.blueprint, "technical-solution")
        self.assertEqual(model.call_count, 4)
        self.assertEqual(chapters[0].payload, legal)
        self.assertEqual(self.task.revisions.filter(kind="chapter", payload__chapter_id="chapter-1").count(), 1)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("fragmented_quoted_paragraph", str(correction["content_quality_correction"]))
        self.assertIn("本批全部完整正文", str(correction["content_quality_correction"]))

    @patch("portal.product_three_drafts.verified_artifact")
    @patch("portal.product_three_drafts.render_report_draft")
    def test_manual_wrong_reference_is_reported_and_blocks_cached_report(self, render, verified):
        from portal.product_pair import _report_generation_hash
        from portal.product_three_drafts import generate_report_drafts
        self.queue_numbered_outline()
        self.task.pending_action = "write"
        self.task.save(update_fields=["pending_action"])
        chapters = [append_revision(self.task, "chapter", json.loads(self.reply(chapter["id"])["content"]),
                    input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
                    for chapter in self.blueprint_payload["chapters"]]
        bad = {**chapters[0].payload, "paragraphs": ["第二章 接口设计给出数据采集细节。"]}
        chapters[0] = append_revision(self.task, "chapter", bad, input_hash=self.input_revision.sha256,
                                     blueprint_hash=self.blueprint.sha256)
        checked = content_checks(self.input_payload, self.blueprint_payload, chapters)
        self.assertTrue(any(issue["code"] == "approved_chapter_reference_mismatch"
                            and issue["chapter_id"] == "chapter-1" for issue in checked["issues"]))
        DocumentArtifact.objects.create(task=self.task, family="technical-solution", version=1,
            path=f"{self.task.pk}/old.docx", sha256="a" * 64, input_hash=self.input_revision.sha256,
            blueprint_hash=self.blueprint.sha256,
            generation_hash=_report_generation_hash(self.task, "technical-solution", self.input_revision, self.blueprint))
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            generate_report_drafts(self.task, fence, attempt_id, self.input_revision, self.blueprint)
        self.assertEqual(error.exception.code, "content_review_required")
        render.assert_not_called()
        verified.assert_not_called()

    @patch("portal.product_worker.generate_for_use")
    def test_isolated_preposition_cannot_consume_writing_parts_as_saved_body(self, model):
        from portal.product_worker import _generate_family
        self.queue_numbered_outline()
        invalid = json.loads(self.reply("chapter-1")["content"])
        invalid["paragraphs"] = ["关于"]
        model.return_value = {"content": json.dumps(invalid)}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as error:
            _generate_family(task_id, fence, attempt_id, self.task, self.input_revision,
                             self.blueprint, "technical-solution")
        self.assertEqual(error.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.revisions.filter(kind="chapter").exists())
        self.task.refresh_from_db()
        self.assertEqual([call["validation_stage"] for call in self.task.checkpoint["calls"]],
                         ["content_quality", "content_quality"])
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("dangling_paragraph", str(correction["content_quality_correction"]))
