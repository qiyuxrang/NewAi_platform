import copy
import json
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_diagrams import diagram_batches, diagram_contract_hash, validate_diagram_batch, validate_document_requirements
from portal.product_documents import DocumentError, _diagram_sources, content_document, render_report_draft
from portal.product_worker import ExecutionError, _generate_diagrams_uncached as _generate_diagrams


@override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="source_only_preview", PRODUCT_OFFICE_RENDER_ENABLED=False)
class DiagramSourceTests(SimpleTestCase):
    def setUp(self):
        self.task = SimpleNamespace(pk=uuid.uuid4(), title="合成工厂日志采集项目")
        self.input = SimpleNamespace(pk=uuid.uuid4(), sha256="1" * 64, payload={
            "items": [{"row_id": "r1", "name": "合成网关", "quantity": "2", "unit": "台"}],
            "requirements": "只使用本项目资料", "conditions": [], "sources": [], "issues": []})
        self.blueprint = SimpleNamespace(payload={"template_version": "frozen-original-v1", "missing": [], "conflicts": []})
        self.chapter = SimpleNamespace(sha256="2" * 64, payload={"chapter_id": "logs", "title": "工厂日志采集设计",
            "source_ids": ["r1"], "paragraphs": ["合成网关采集设备日志，经合成审计服务复核。验收关系仍待确认。"]})
        self.document = content_document(self.task, self.input, self.blueprint, [self.chapter])

    def reply(self, figures, paragraphs):
        return {"diagrams": [{"figure_id": figure["id"], "title": f"合成网关日志分图{self.figure_label(figure['id'])}",
            "description": "合成网关到合成审计服务的日志流向，验收待确认。",
            "source": f'flowchart LR\nA["合成网关"] --> B["合成审计服务（图{self.figure_label(figure["id"])}）"]',
            "evidence_block_ids": [paragraphs[0]["id"]], "anchor_text": "合成网关"} for figure in figures]}

    @staticmethod
    def figure_label(identifier):
        return "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉"[int(identifier.split("_")[1]) - 1]

    @patch("portal.product_worker._model")
    def test_model_batches_use_full_current_chapter_and_exact_source_lineage(self, model):
        def response(*args, output_validator=None):
            request = args[-1]
            self.assertEqual(request["action"], "diagram")
            self.assertEqual(request["project_title"], self.task.title + "（技术方案）")
            self.assertEqual(request["report_blocks"][0]["text"], self.chapter.payload["paragraphs"][0])
            self.assertEqual(request["report_blocks"][0]["source_ids"], ["S1"])
            self.assertLessEqual(len(request["figures"]), 4)
            self.assertIsNotNone(output_validator)
            return output_validator(self.reply([{"id": figure["figure_id"]} for figure in request["figures"]], request["report_blocks"]))
        model.side_effect = response
        diagrams = _generate_diagrams(self.task.pk, 1, "mocked-attempt", self.document)
        self.assertEqual(model.call_count, 4)
        self.assertEqual(len(diagrams), 15)
        sources = _diagram_sources(self.document, lambda document: diagrams)
        self.assertEqual(sources, diagrams)
        self.assertTrue(all("合成网关日志分图" in block["caption"] for block in self.document["blocks"] if block["type"] == "figure"))
        serialized = json.dumps(self.document, ensure_ascii=False)
        self.assertNotIn("flowchart LR", serialized)

    def test_missing_sources_foreign_evidence_or_directives_fail_without_fallback(self):
        figures, paragraphs = next(diagram_batches(self.document))
        good = self.reply(figures, paragraphs)
        malformed = []
        for changes in ({"evidence_block_ids": ["OTHER_PROJECT_BLOCK"]}, {"anchor_text": "虚构设备"},
                        {"source": '%%{init: {"securityLevel":"loose"}}}%%\nflowchart LR\nA --> B'},
                        {"source": 'flowchart LR\nA["合成网关"]\nclick A "https://external.invalid"'},
                        {"figure_id": "OTHER_PROJECT_FIGURE"}):
            value = copy.deepcopy(good)
            value["diagrams"][0].update(changes)
            malformed.append(value)
        malformed.append({"diagrams": good["diagrams"][:-1]})
        malformed.append({"diagrams": [good["diagrams"][0]] * len(figures)})
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_diagram_batch(value, figures, paragraphs)
        with self.assertRaises(DocumentError) as error:
            _diagram_sources(self.document, None)
        self.assertEqual(error.exception.code, "diagram_generation_required")

    def test_other_mermaid_dialects_cannot_leak_into_persisted_content(self):
        for text in ("sequenceDiagram\nA->>B:hello", "classDiagram\nclass A", "flowchart LR\nA --> B"):
            document = copy.deepcopy(self.document)
            document["blocks"][1]["text"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_document_requirements(document)

    @patch("portal.product_worker._model")
    def test_model_missing_figures_are_not_replaced_with_generic_charts(self, model):
        model.side_effect = lambda *args, output_validator=None: output_validator({"diagrams": []})
        with self.assertRaises(ExecutionError) as error:
            _generate_diagrams(self.task.pk, 1, "mocked-attempt", self.document)
        self.assertEqual(error.exception.code, "diagram_generation_invalid")

    def test_renderer_failure_cleans_all_private_sources_and_reports_actual_failed_phase(self):
        phases, source_paths = [], []
        def generator(document):
            return [item for figures, paragraphs in diagram_batches(document) for item in self.reply(figures, paragraphs)["diagrams"]]
        def reject(command, **kwargs):
            source = Path(command[-1])
            source_paths.append(source)
            self.assertIn("flowchart LR", source.read_text(encoding="utf-8"))
            self.assertNotIn("flowchart LR", Path(command[-2]).read_text(encoding="utf-8"))
            return SimpleNamespace(returncode=2, stdout=b"", stderr=b"parser source details must not be persisted")
        with tempfile.TemporaryDirectory() as storage, override_settings(PRODUCT_STORAGE_ROOT=storage), \
                patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                patch("portal.product_documents._document_runtime", return_value=Path("unused-python")), \
                patch("portal.product_documents._mermaid_runtime", return_value=Path("unused-node")), \
                patch("portal.product_documents._mermaid_chromium", return_value=Path("unused-browser")), \
                patch("portal.product_documents.subprocess.run", side_effect=reject) as process:
            with self.assertRaises(DocumentError) as error:
                render_report_draft(self.task, self.input, self.blueprint, [self.chapter], "technical-solution",
                    diagram_generator=generator, diagram_progress=lambda status, **details: phases.append(status))
            self.assertEqual(error.exception.code, "diagram_render_failed")
            self.assertEqual(error.exception.diagnostic, {"stage": "diagram_render", "reason": "diagram_renderer_failed", "returncode": 2})
            self.assertEqual(process.call_count, 1)
            self.assertTrue(all(not source.exists() for source in source_paths))
            self.assertFalse(list(Path(storage).rglob("mermaid-*")))
            for path in Path(storage).rglob("*.json"):
                self.assertNotIn("flowchart LR", path.read_text(encoding="utf-8"))
        self.assertEqual(phases, ["running", "failed"])

    def test_cache_contract_binds_renderer_and_prompt_without_source(self):
        self.assertRegex(diagram_contract_hash(), r"^[0-9a-f]{64}$")
        with patch("portal.product_diagrams.DIAGRAM_PROMPT_VERSION", "different-prompt"):
            changed = diagram_contract_hash()
        self.assertNotEqual(diagram_contract_hash(), changed)

    @patch("portal.product_documents._render_document", return_value={"path": "synthetic"})
    @patch("portal.product_documents._document_runtime", return_value=Path("unused-python"))
    def test_source_only_preview_is_retained_in_delivery_evidence(self, runtime, render):
        render_report_draft(self.task, self.input, self.blueprint, [self.chapter], "technical-solution")
        evidence = render.call_args.args[8]
        self.assertEqual(evidence["knowledge"]["mode"], "source_only_preview")
        self.assertFalse(evidence["knowledge"]["ragflow_used"])

    @patch("portal.product_worker._model")
    def test_equipment_project_topics_replace_generic_platform_slots(self, model):
        self.task.title = "合成供配电项目"
        self.chapter.payload["paragraphs"] = ["配电柜接入母线，电能经馈线输送至合成车间，接地校验待确认。"]
        document = content_document(self.task, self.input, self.blueprint, [self.chapter])
        def response(*args, output_validator=None):
            request = args[-1]
            self.assertIn("不得套用通用平台架构", request["instruction"])
            self.assertIn("建议主题若与本章无关", request["instruction"])
            payload = {"diagrams": [{"figure_id": figure["figure_id"], "title": f"配电柜供配电设计图{self.figure_label(figure['figure_id'])}",
                "description": "配电柜与馈线供电关系，接地校验待确认。", "source": f'flowchart LR\nA["配电柜"] --> B["合成车间馈线（图{self.figure_label(figure["figure_id"])}）"]',
                "evidence_block_ids": [request["report_blocks"][0]["id"]], "anchor_text": "配电柜"}
                for figure in request["figures"]]}
            self.assertIsNotNone(output_validator)
            return output_validator(payload)
        model.side_effect = response
        diagrams = _generate_diagrams(self.task.pk, 1, "mocked-attempt", document)
        _diagram_sources(document, lambda document: diagrams)
        self.assertTrue(all("配电柜" in diagram["source"] for diagram in diagrams))
        self.assertEqual(len({diagram["source"] for diagram in diagrams}), 15)
        self.assertFalse(any("平台" in block.get("caption", "") for block in document["blocks"]))
