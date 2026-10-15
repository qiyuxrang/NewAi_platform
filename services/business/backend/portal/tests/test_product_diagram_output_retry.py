import json
from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings

from portal.product_worker import ExecutionError, _failure_diagnostic, _generate_diagrams_uncached as _generate_diagrams
from portal.product_diagrams import validate_diagram_batch
from portal.product_service import digest
from .base import PortalTestCase
from . import test_product_review_output_retry as fixture


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_MAX_MODEL_CALLS=10,
    PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100",
                         "route_cost_caps": {"product_writing": "1", "product_review": "1"}})
class ProductDiagramOutputRetryTests(PortalTestCase):
    setUp = fixture.ProductReviewOutputRetryTests.setUp
    claimed = fixture.ProductReviewOutputRetryTests.claimed

    def document(self):
        return {"family": "technical-solution", "metadata": {"title": "测试图表正文依据"}, "blocks": [
            {"id": "H1", "type": "heading", "level": 1, "text": "采集设计"},
            {"id": "P1", "type": "paragraph", "text": "数据采集方案支持权限控制和审计，具体参数需另行确认。", "source_ids": ["r1"]},
            {"id": "DIAGRAM_01_FIGURE", "type": "figure", "caption": "采集与审计"},
        ]}

    def reply(self, *, valid=True):
        item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "采集与审计", "description": "先验证权限并记录审计结果。",
                "source": "flowchart LR\nA1[权限控制] --> B2[审计流程]", "evidence_block_ids": ["P1"], "anchor_text": "权限控制"}
        if not valid:
            item["anchor_text"] = "未提供的虚构节点"
        return {"content": json.dumps({"diagrams": [item]}, ensure_ascii=False)}

    @patch("portal.product_worker.generate_for_use")
    def test_real_render_feedback_keeps_budget_and_cannot_fall_back_to_excerpt(self, model):
        task_id, fence, attempt_id = self.claimed()
        document = self.document()
        feedback = {"figure_id": "DIAGRAM_01_FIGURE", "reason": "diagram_layout_unreadable",
                    "previous_source": json.loads(self.reply()["content"])["diagrams"][0]["source"]}
        document["diagram_render_feedback"] = feedback
        invalid = json.loads(self.reply()["content"])
        invalid["diagrams"][0]["source"] += '\nclick A1 "https://external.invalid"'
        model.return_value = {"content": json.dumps(invalid, ensure_ascii=False)}
        with self.assertRaises(ExecutionError) as rejected:
            _generate_diagrams(task_id, fence, attempt_id, document, draft=True)
        self.assertEqual(rejected.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)
        request = json.loads(model.call_args_list[0].args[2][1]["content"])
        self.assertEqual(request["render_feedback"], feedback)
        self.assertIn("优先在单页完整呈现", request["instruction"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)
        self.assertFalse(any("diagram_excerpt_fallback" in call for call in self.task.checkpoint["calls"]))

    @patch("portal.product_worker.generate_for_use")
    def test_draft_excerpt_after_two_rejections_keeps_real_refs_and_pending_evidence(self, model):
        task_id, fence, attempt_id = self.claimed()
        document = self.document()
        invalid = json.loads(self.reply()["content"])
        invalid["diagrams"][0]["source"] += '\nclick A1 "https://external.invalid"'
        model.return_value = {"content": json.dumps(invalid, ensure_ascii=False)}
        excerpts = _generate_diagrams(task_id, fence, attempt_id, document, draft=True)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(len(excerpts), 1)
        item = excerpts[0]
        self.assertEqual(item["evidence_block_ids"], ["P1"])
        self.assertIn(item["anchor_text"], document["blocks"][1]["text"])
        self.assertIn(item["anchor_text"], item["source"])
        self.assertNotIn("-->", item["source"])
        self.assertNotIn("click", item["source"])
        self.assertIn("详细关系待人工确认", item["title"])
        warnings = []
        self.assertEqual(validate_diagram_batch({"diagrams": excerpts}, [document["blocks"][-1]],
            [document["blocks"][1]], draft=True, quality_issues=warnings), excerpts)
        self.assertEqual(warnings[0]["code"], "diagram_excerpt_fallback")
        with self.assertRaises(ValueError):
            validate_diagram_batch({"diagrams": excerpts}, [document["blocks"][-1]], [document["blocks"][1]])
        from portal.product_documents import _diagram_sources
        document["pending"] = []
        with patch("portal.product_documents.validate_document_requirements"), \
                patch("portal.product_documents.apply_diagram_descriptions"):
            retained = []
            _diagram_sources(document, lambda _: excerpts, draft=True, quality_issues=retained)
        self.assertEqual(retained, warnings)
        self.assertEqual(document["pending"], [])
        self.task.refresh_from_db()
        calls = self.task.checkpoint["calls"]
        self.assertTrue(all(call.get("parse_error") == "invalid_model_output" for call in calls[-2:]))
        self.assertTrue(all("response_validated" not in call for call in calls[-2:]))
        self.assertEqual(calls[-1]["diagram_excerpt_fallback"]["sha256"], digest(excerpts))
        with self.assertRaises(ExecutionError) as formal:
            _generate_diagrams(task_id, fence, attempt_id, document)
        self.assertEqual(formal.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 4)
        unknown = json.loads(self.reply()["content"])
        unknown["diagrams"][0]["evidence_block_ids"] = ["OTHER_PROJECT_BLOCK"]
        model.return_value = {"content": json.dumps(unknown, ensure_ascii=False)}
        with self.assertRaises(ExecutionError):
            _generate_diagrams(task_id, fence, attempt_id, document, draft=True)
        self.assertEqual(model.call_count, 6)
        def revoke(*args):
            self.owner.roles.clear()
            return {"content": json.dumps(invalid, ensure_ascii=False)}
        model.side_effect = revoke
        with self.assertRaises(ExecutionError) as permission:
            _generate_diagrams(task_id, fence, attempt_id, document, draft=True)
        self.assertEqual(permission.exception.code, "permission_changed")
        self.assertEqual(model.call_count, 7)

    @patch("portal.product_worker.generate_for_use")
    def test_draft_semantic_findings_are_retained_and_only_benign_style_is_removed(self, model):
        from portal.product_documents import _diagram_sources
        document = self.document()
        figures, paragraphs = [document["blocks"][-1]], [document["blocks"][1]]
        payload = json.loads(self.reply()["content"])
        payload["diagrams"][0]["title"] = "项目投资预算10万元"
        original_source = payload["diagrams"][0]["source"]
        payload["diagrams"][0]["source"] += "\nstyle B2 stroke-dasharray: 5 5"
        with self.assertRaises(ValueError):
            validate_diagram_batch(payload, figures, paragraphs)
        findings = []
        normalized = validate_diagram_batch(payload, figures, paragraphs, draft=True, quality_issues=findings)
        self.assertTrue(findings)
        self.assertEqual(normalized[0]["source"], original_source + "\n")
        self.assertEqual(normalized[0]["title"], payload["diagrams"][0]["title"])
        document["pending"] = []
        downstream = []
        with patch("portal.product_documents.validate_document_requirements"), \
                patch("portal.product_documents.apply_diagram_descriptions"):
            self.assertEqual(_diagram_sources(document, lambda _: normalized, draft=True, quality_issues=downstream), normalized)
        self.assertEqual(downstream, findings)
        self.assertEqual(document["pending"], [])
        self.assertNotIn("diagram_quality_issues", document)
        for source in (original_source + "\nclick B2 \"https://external.invalid\"",
                       original_source + "\nstyle B2 fill:url(javascript:evil)",
                       original_source + "\nclassDef pending opacity:0.5", original_source + "\n%%{init: {}}%%"):
            candidate = deepcopy(payload)
            candidate["diagrams"][0]["source"] = source
            rejected = []
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_diagram_batch(candidate, figures, paragraphs, draft=True, quality_issues=rejected)
            self.assertEqual(rejected, [])
        candidate = deepcopy(payload)
        candidate["diagrams"].append({**candidate["diagrams"][0], "figure_id": "FOREIGN_FIGURE"})
        rejected = []
        with self.assertRaises(ValueError):
            validate_diagram_batch(candidate, figures, paragraphs, draft=True, quality_issues=rejected)
        self.assertEqual(rejected, [])
        candidate = deepcopy(payload)
        candidate["diagrams"][0]["title"] = "DIAGRAM_01_FIGURE"
        with self.assertRaises(ValueError):
            validate_diagram_batch(candidate, figures, paragraphs, draft=True)
        task_id, fence, attempt_id = self.claimed()
        model.return_value = {"content": json.dumps(payload, ensure_ascii=False)}
        self.assertEqual(_generate_diagrams(task_id, fence, attempt_id, document, draft=True), normalized)
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][-1]["response_sha256"], digest(normalized))

    @patch("portal.product_worker.generate_for_use")
    def test_draft_plain_linebreak_and_benign_class_keep_visible_text_and_relations(self, model):
        import re
        from portal.product_diagrams import _diagram_visible_labels
        document = self.document()
        figures, paragraphs = [document["blocks"][-1]], [document["blocks"][1]]
        payload = json.loads(self.reply()["content"])
        payload["diagrams"][0]["source"] = (
            'flowchart LR\nA1["权限控制<BR/>待确认"]:::pending --> B2["审计流程"]\n'
            'classDef pending fill:#fff,stroke:#333,stroke-width:2px\n')
        original = deepcopy(payload)
        with self.assertRaises(ValueError):
            validate_diagram_batch(payload, figures, paragraphs)
        diagrams = validate_diagram_batch(payload, figures, paragraphs, draft=True)
        source = diagrams[0]["source"]
        self.assertEqual(source, 'flowchart LR\nA1["权限控制 待确认"] --> B2["审计流程"]\n')
        self.assertEqual(payload, original)
        self.assertEqual(diagrams[0], {**payload["diagrams"][0], "source": source})
        self.assertEqual(_diagram_visible_labels(source),
            _diagram_visible_labels(re.sub(r"<br\s*/?>", " ", payload["diagrams"][0]["source"], flags=re.I)))
        for unsafe in ('<br onclick="evil">', '<img src="https://external.invalid">', '<script>evil</script>',
                       '<br style="color:red">', 'classDef pending fill:url(javascript:evil)',
                       'classDef pending opacity:0.5', 'linkStyle 0 stroke:#fff', 'click A1 "https://external.invalid"'):
            candidate = deepcopy(original)
            candidate["diagrams"][0]["source"] += "\n" + unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                validate_diagram_batch(candidate, figures, paragraphs, draft=True)
        task_id, fence, attempt_id = self.claimed()
        model.return_value = {"content": json.dumps(original, ensure_ascii=False)}
        self.assertEqual(_generate_diagrams(task_id, fence, attempt_id, document, draft=True), diagrams)
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][-1]["response_sha256"], digest(diagrams))

    @patch("portal.product_worker.generate_for_use")
    def test_literal_report_anchor_normalizes_only_to_complete_visible_evidence(self, model):
        document = self.document()
        figures, paragraphs = [document["blocks"][-1]], [document["blocks"][1]]
        payload = json.loads(self.reply()["content"])
        payload["diagrams"][0]["anchor_text"] = "数据采集方案支持权限控制和审计"
        original = deepcopy(payload)
        normalized = validate_diagram_batch(payload, figures, paragraphs)
        self.assertEqual(normalized[0]["anchor_text"], "权限控制")
        self.assertEqual(payload, original)
        self.assertEqual(normalized[0], {**original["diagrams"][0], "anchor_text": "权限控制"})
        self.assertEqual(validate_diagram_batch({"diagrams": normalized}, figures, paragraphs), normalized)
        inaccurate = deepcopy(original)
        inaccurate["diagrams"][0]["anchor_text"] = "未准确引用的锚点元数据"
        with self.assertRaises(ValueError):
            validate_diagram_batch(inaccurate, figures, paragraphs)
        self.assertEqual(validate_diagram_batch(inaccurate, figures, paragraphs, draft=True), normalized)
        for changes in (
            {"anchor_text": "虚构正文锚点"},
            {"evidence_block_ids": ["OTHER_PROJECT_BLOCK"]},
            {"source": 'flowchart LR\nA["权限控制扩展"] --> B["正文未提供的标签"]'},
            {"source": 'flowchart LR\nAUTH_GATEWAY --> B["正文未提供的标签"]'},
            {"source": 'flowchart LR\nA["权限控制"]\nclick A "https://external.invalid"'},
            {"title": "项目投资预算10万元"},
        ):
            candidate = deepcopy(original)
            candidate["diagrams"][0].update(changes)
            # A hidden identifier is literal report text, never a visible label.
            evidence = [{**paragraphs[0], "text": paragraphs[0]["text"] + "内部引用AUTH_GATEWAY。"}]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_diagram_batch(candidate, figures, evidence)
            if not {"anchor_text", "title"} & changes.keys():
                with self.subTest(draft_changes=changes), self.assertRaises(ValueError):
                    validate_diagram_batch(candidate, figures, evidence, draft=True, quality_issues=[])
        task_id, fence, attempt_id = self.claimed()
        model.return_value = {"content": json.dumps(original, ensure_ascii=False)}
        self.assertEqual(_generate_diagrams(task_id, fence, attempt_id, document), normalized)
        self.assertEqual(model.call_count, 1)
        self.task.refresh_from_db()
        call = self.task.checkpoint["calls"][-1]
        self.assertTrue(call["response_validated"])
        self.assertEqual(call["response_sha256"], digest(normalized))
        self.assertNotEqual(call["response_sha256"], digest(original["diagrams"]))

    @patch("portal.product_worker.generate_for_use")
    def test_invalid_diagram_has_one_correction_and_returns_only_validated_items(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.side_effect = [self.reply(valid=False), self.reply()]
        diagrams = _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["anchor_text"], "权限控制")
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("diagram_validation_correction", correction)
        expected_ids = ["DIAGRAM_01_FIGURE"]
        for call in model.call_args_list:
            request = json.loads(call.args[2][1]["content"])
            self.assertEqual([item["figure_id"] for item in request["schema"]["diagrams"]], expected_ids)
        self.assertIn(json.dumps(expected_ids), correction["diagram_validation_correction"])
        reason = "diagram is missing its report evidence anchor"
        self.assertIn(reason, correction["diagram_validation_correction"])
        self.assertIn("可见节点标签或消息", correction["diagram_validation_correction"])
        primary = model.call_args_list[0].args[2][0]["content"]
        self.assertIn("六个字段", primary)
        self.assertIn("anchor_text为2至100字符", primary)
        self.assertIn("所引用原文及source", primary)
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["calls"][-2]["diagram_validation_reason"], reason)
        self.assertNotIn("diagram_validation_reason", self.task.checkpoint["calls"][-1])
        self.assertTrue(self.task.checkpoint["calls"][-1]["response_validated"])
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_single_node_uses_existing_bounded_quality_correction(self, model):
        task_id, fence, attempt_id = self.claimed()
        invalid = json.loads(self.reply()["content"])
        invalid["diagrams"][0]["source"] = 'flowchart TB\nA1["权限控制"]'
        model.side_effect = [{"content": json.dumps(invalid, ensure_ascii=False)}, self.reply()]
        diagrams = _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(len(diagrams), 1)
        self.assertEqual(model.call_count, 2)
        correction = json.loads(model.call_args_list[1].args[2][1]["content"])
        self.assertIn("diagram_structure_quality", json.dumps(correction))
        self.task.refresh_from_db()
        calls = self.task.checkpoint["calls"]
        self.assertEqual(calls[-2]["quality_issues"][0]["figure_id"], "DIAGRAM_01_FIGURE")
        self.assertEqual(calls[-2]["quality_issues"][0]["field"], "source")
        self.assertTrue(calls[-1]["response_validated"])

    @patch("portal.product_worker.generate_for_use")
    def test_anchor_correction_cannot_replace_figure_id_or_use_foreign_evidence(self, model):
        task_id, fence, attempt_id = self.claimed()
        invalid = json.loads(self.reply(valid=False)["content"])
        invalid["diagrams"][0]["source"] = 'flowchart LR\nA["无正文依据的节点"] --> B["另一个无依据节点"]'
        for change, reason in (
            ({"figure_id": "本批figure_id"}, "diagram identifiers differ from planned figures"),
            ({"evidence_block_ids": ["OTHER_PROJECT_BLOCK"]}, "diagram evidence outside authored chapter"),
        ):
            corrected = json.loads(self.reply()["content"])
            corrected["diagrams"][0].update(change)
            model.side_effect = [{"content": json.dumps(invalid, ensure_ascii=False)},
                                 {"content": json.dumps(corrected, ensure_ascii=False)}]
            with self.subTest(reason=reason), self.assertRaises(ExecutionError) as error:
                _generate_diagrams(task_id, fence, attempt_id, self.document(), draft=True)
            self.assertEqual(error.exception.code, "diagram_generation_invalid")
            self.assertEqual(error.exception.diagram_validation_reason, reason)
            self.task.refresh_from_db()
            self.assertNotIn("diagram_excerpt_fallback", self.task.checkpoint["calls"][-1])
        self.assertEqual(model.call_count, 4)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_twice_invalid_diagram_fails_closed_without_artifact(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.return_value = self.reply(valid=False)
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(_failure_diagnostic(error.exception)["diagram_validation_reason"],
                         "diagram is missing its report evidence anchor")
        unknown = ExecutionError("diagram_generation_invalid", diagram_validation_reason="private provider text")
        self.assertNotIn("diagram_validation_reason", _failure_diagnostic(unknown))
        self.assertEqual(model.call_count, 2)
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_json_and_diagram_semantics_share_one_retry(self, model):
        task_id, fence, attempt_id = self.claimed()
        model.side_effect = [{"content": "not JSON"}, self.reply(valid=False), self.reply()]
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)

    @patch("portal.product_worker.generate_for_use")
    def test_fabricated_diagram_budget_fails_with_locatable_diagnostics(self, model):
        task_id, fence, attempt_id = self.claimed()
        reply = self.reply()
        payload = json.loads(reply["content"])
        payload["diagrams"][0]["title"] = "项目投资预算10万元"
        model.return_value = {"content": json.dumps(payload, ensure_ascii=False)}
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "diagram_generation_invalid")
        self.assertEqual(model.call_count, 2)
        from portal.product_worker import _bounded_quality_issues
        issues = _bounded_quality_issues(error.exception.quality_issues)
        self.assertTrue(issues)
        self.assertEqual(issues[0]["figure_id"], "DIAGRAM_01_FIGURE")
        self.assertEqual(issues[0]["field"], "title")
        self.assertFalse(self.task.artifacts.exists())

    @patch("portal.product_worker.generate_for_use")
    def test_revoked_permission_prevents_diagram_correction_call(self, model):
        task_id, fence, attempt_id = self.claimed()
        def revoke(*args):
            self.owner.roles.clear()
            return self.reply(valid=False)
        model.side_effect = revoke
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(task_id, fence, attempt_id, self.document())
        self.assertEqual(error.exception.code, "permission_changed")
        self.assertEqual(model.call_count, 1)
        self.assertFalse(self.task.artifacts.exists())
