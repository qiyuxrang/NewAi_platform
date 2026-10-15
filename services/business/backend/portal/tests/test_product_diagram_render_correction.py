import base64
import copy
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_diagrams import _draft_diagram_source, validate_diagram_batch
from portal.product_documents import DocumentError, _render_draft_diagrams
from portal.product_service import digest
from portal.product_worker import ExecutionError, _generate_diagrams, _generate_diagrams_uncached


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j8WQAAAAASUVORK5CYII="
)
TARGET_FIGURE = "DIAGRAM_02_FIGURE"
PARAGRAPH_TEXT = "设备布置和安全检查须由负责人核对，具体参数待确认。"


@override_settings(PRODUCT_OFFICE_RENDER_ENABLED=False)
class ProductDiagramRenderCorrectionTests(SimpleTestCase):
    def setUp(self):
        from .test_product_draft_first import DraftFirstDocumentTests

        self.fixture = DraftFirstDocumentTests()
        self.fixture.setUp()
        self.document = self.fixture.document()
        self.target_figure = next(block for block in self.document["blocks"]
                                  if block.get("id") == TARGET_FIGURE)

    def with_second_paragraph(self, document=None):
        value = copy.deepcopy(document or self.document)
        first = next(index for index, block in enumerate(value["blocks"])
                     if block.get("type") == "paragraph" and not block["id"].startswith("DIAGRAM_"))
        value["blocks"].insert(first + 1, {"id": "P2", "type": "paragraph",
            "text": "设备保护动作需要另行确认。", "source_ids": ["S1"], "requirement_ids": []})
        return value

    def valid_repair(self, document):
        figure = next(block for block in document["blocks"] if block.get("type") == "figure")
        paragraph = next(block for block in document["blocks"] if block.get("type") == "paragraph"
                         and not block["id"].startswith("DIAGRAM_"))
        return {"figure_id": figure["id"], "title": "设备布置核对关系",
            "description": "设备布置和安全检查需由负责人核对。",
            "source": 'flowchart LR\nA["设备布置"] --> B["安全检查"]',
            "evidence_block_ids": [paragraph["id"]], "anchor_text": "设备布置"}

    def step_runner(self):
        records = []
        def run(key, binding, operation, validate):
            records.append({"key": key, "binding": copy.deepcopy(binding), "input_hash": digest(binding)})
            output = operation()
            if not validate(output):
                raise DocumentError("diagram_render_failed")
            return output
        return records, run

    def render_success(self, directory, figure, source):
        path = Path(directory) / figure["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        return {"figures": [{"figure_id": figure["id"],
            "imageSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sourceSha256": hashlib.sha256(source["source"].encode()).hexdigest()}]}

    def run_render(self, document, generator, renderer, runtime=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        steps, step = self.step_runner()
        with patch("portal.product_documents.preflight_document_rendering",
                   return_value=runtime or {"mermaid": {"status": "available"}}), \
                patch("portal.product_documents._render_one_diagram", side_effect=renderer):
            result = _render_draft_diagrams(copy.deepcopy(document), generator, Path(temporary.name), step)
        return result, Path(temporary.name), steps

    def test_real_render_failure_redraws_once_with_new_binding_and_verified_image(self):
        generator_calls, repair_documents, repair_items = [], [], []
        original_generator = self.fixture.generator

        def generator(document):
            generator_calls.append(copy.deepcopy(document))
            if document.get("diagram_render_feedback"):
                repair_documents.append(copy.deepcopy(document))
                item = self.valid_repair(document)
                repair_items.append(copy.deepcopy(item))
                return [item]
            return original_generator(document)

        attempts, rendered_sources = {}, []
        def renderer(directory, document, figure, source):
            rendered_sources.append((figure["id"], copy.deepcopy(source)))
            attempts[figure["id"]] = attempts.get(figure["id"], 0) + 1
            if figure["id"] == TARGET_FIGURE and attempts[figure["id"]] == 1:
                raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render",
                    "reason": "diagram_layout_unreadable"})
            return self.render_success(directory, figure, source)

        result, directory, steps = self.run_render(self.document, generator, renderer)
        self.assertEqual((result["rendered"], result["pending_count"]), (15, 0))
        self.assertEqual(attempts[TARGET_FIGURE], 2)
        self.assertEqual(len(generator_calls), 2)
        feedback = repair_documents[0]["diagram_render_feedback"]
        initial_source = next(source["source"] for figure_id, source in rendered_sources
                              if figure_id == TARGET_FIGURE)
        self.assertEqual(feedback, {"figure_id": TARGET_FIGURE, "reason": "diagram_layout_unreadable",
            "previous_source": initial_source})

        repair_doc = repair_documents[0]
        repair_figure = next(block for block in repair_doc["blocks"] if block.get("type") == "figure")
        repair_paragraphs = [block for block in repair_doc["blocks"] if block.get("type") == "paragraph"]
        self.assertEqual([block["id"] for block in repair_paragraphs],
                         repair_items[0]["evidence_block_ids"])
        self.assertEqual(validate_diagram_batch({"diagrams": repair_items}, [repair_figure],
            repair_paragraphs, draft=False), repair_items)

        base_key = f"diagram_render:technical-solution:{TARGET_FIGURE}"
        base_step = next(item for item in steps if item["key"] == base_key)
        correction_step = next(item for item in steps if item["key"] == base_key + ":correction")
        self.assertNotEqual(base_step["input_hash"], correction_step["input_hash"])
        self.assertNotEqual(base_step["binding"]["source_sha256"], correction_step["binding"]["source_sha256"])
        self.assertEqual(correction_step["binding"]["render_correction"], "diagram_layout_unreadable")

        output = next(item for item in result["figures"] if item["id"] == TARGET_FIGURE)
        image_path = directory / self.target_figure["path"]
        actual_image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        self.assertEqual(output["image_sha256"], actual_image_hash)
        self.assertEqual(output["source_sha256"],
            hashlib.sha256(repair_items[0]["source"].encode()).hexdigest())
        self.assertEqual(output["evidence_block_ids"], repair_items[0]["evidence_block_ids"])

    def test_second_render_failure_is_bounded_and_remains_pending(self):
        generator_calls = []
        def generator(document):
            generator_calls.append(copy.deepcopy(document))
            return [self.valid_repair(document)] if document.get("diagram_render_feedback") else self.fixture.generator(document)

        attempts = {}
        def renderer(directory, document, figure, source):
            attempts[figure["id"]] = attempts.get(figure["id"], 0) + 1
            if figure["id"] == TARGET_FIGURE:
                reason = "diagram_layout_unreadable" if attempts[figure["id"]] == 1 else "diagram_parse_or_anchor_failed"
                raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render", "reason": reason})
            return self.render_success(directory, figure, source)

        result, _, steps = self.run_render(self.document, generator, renderer)
        self.assertEqual((result["rendered"], result["pending_count"]), (14, 1))
        self.assertEqual(attempts[TARGET_FIGURE], 2)
        self.assertEqual(len(generator_calls), 2)
        target_steps = [item["key"] for item in steps if TARGET_FIGURE in item["key"]]
        self.assertEqual(target_steps, [f"diagram_render:technical-solution:{TARGET_FIGURE}:selected",
            f"diagram_render:technical-solution:{TARGET_FIGURE}",
            f"diagram_render:technical-solution:{TARGET_FIGURE}:correction"])
        self.assertEqual(result["pending_figures"][0]["figure_id"], TARGET_FIGURE)

    def test_runtime_unavailable_does_not_start_correction(self):
        generator_calls, renderer_calls = [], []
        def generator(document):
            generator_calls.append(copy.deepcopy(document))
            return self.fixture.generator(document)
        def renderer(*args):
            renderer_calls.append(args)
            return self.render_success(args[0], args[2], args[3])

        result, _, steps = self.run_render(self.document, generator, renderer,
            runtime={"mermaid": {"status": "unavailable", "reason": "node_unavailable"}})
        self.assertEqual((result["rendered"], result["pending_count"]), (0, 15))
        self.assertEqual(len(generator_calls), 1)
        self.assertEqual(renderer_calls, [])
        self.assertFalse(any(item["key"].endswith(":correction") for item in steps))

    def test_excerpt_parameter_and_foreign_reference_repairs_remain_pending(self):
        cases = {
            "excerpt": lambda item: item.update(source='flowchart TB\nEXCERPT_0123456789abcdef["设备布置"]'),
            "unsupported_parameter": lambda item: item.update(
                source='flowchart LR\nA["设备布置"] --> B["额定电压100kV"]'),
            "foreign_reference": lambda item: item.update(evidence_block_ids=["P2"]),
        }
        for name, corrupt in cases.items():
            with self.subTest(repair=name):
                document = self.with_second_paragraph()
                generator_calls, repair_documents = [], []
                def generator(value):
                    generator_calls.append(copy.deepcopy(value))
                    if value.get("diagram_render_feedback"):
                        repair_documents.append(copy.deepcopy(value))
                        item = self.valid_repair(value)
                        corrupt(item)
                        return [item]
                    return self.fixture.generator(value)

                attempts = {}
                def renderer(directory, current, figure, source):
                    attempts[figure["id"]] = attempts.get(figure["id"], 0) + 1
                    if figure["id"] == TARGET_FIGURE and attempts[figure["id"]] == 1:
                        raise DocumentError("diagram_render_failed", diagnostic={"stage": "diagram_render",
                            "reason": "diagram_parse_or_anchor_failed"})
                    return self.render_success(directory, figure, source)

                result, _, steps = self.run_render(document, generator, renderer)
                self.assertEqual((result["rendered"], result["pending_count"]), (14, 1))
                self.assertEqual(attempts[TARGET_FIGURE], 1)
                self.assertEqual(len(generator_calls), 2)
                self.assertNotIn("P2", {block["id"] for block in repair_documents[0]["blocks"]})
                self.assertFalse(any(item["key"].endswith(":correction") for item in steps
                                     if TARGET_FIGURE in item["key"]))
                self.assertEqual(result["pending_figures"][0]["figure_id"], TARGET_FIGURE)

    def test_worker_binds_render_feedback_into_cache_and_model_request(self):
        from portal.product_models import DocumentTask

        feedback = {"figure_id": "DIAGRAM_01_FIGURE", "reason": "diagram_layout_unreadable",
                    "previous_source": 'flowchart LR\nA["设备布置"] --> B["待核对"]'}
        document = {"family": "technical-solution", "metadata": {"title": "合成校验"},
            "diagram_render_feedback": feedback, "blocks": [
                {"id": "H1", "type": "heading", "level": 1, "text": "设备布置"},
                {"id": "P1", "type": "paragraph", "text": PARAGRAPH_TEXT, "source_ids": ["S1"]},
                {"id": "DIAGRAM_01_FIGURE", "type": "figure", "caption": "设备布置核对关系"},
            ]}
        task = SimpleNamespace(pk="test-task")
        input_revision = SimpleNamespace(sha256="1" * 64)
        blueprint = SimpleNamespace(sha256="2" * 64)
        binding_records, request_records = [], []

        def run_step(task_id, fence, key, binding, operation, *, validate=None):
            binding_records.append(copy.deepcopy(binding))
            value = operation()
            self.assertTrue(validate(value))
            return value

        def model(task_id, fence, attempt_id, route, request, *, output_validator):
            request_records.append(copy.deepcopy(request))
            item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "设备布置核对关系",
                "description": "设备布置和安全检查需由负责人核对。",
                "source": 'flowchart LR\nA["设备布置"] --> B["安全检查"]',
                "evidence_block_ids": ["B1"], "anchor_text": "设备布置"}
            return output_validator({"diagrams": [item]})

        with patch.object(DocumentTask.objects, "get", return_value=task), \
                patch("portal.product_worker.current_revision",
                      side_effect=lambda _task, kind: input_revision if kind == "input" else blueprint), \
                patch("portal.product_worker._review_route_hash", return_value="route-hash"), \
                patch("portal.product_worker.rules_hash", return_value="rules-hash"), \
                patch("portal.product_steps.run_step", side_effect=run_step), \
                patch("portal.product_worker._model", side_effect=model):
            result = _generate_diagrams("test-task", 1, "test-attempt", document, draft=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["evidence_block_ids"], ["P1"])
        self.assertEqual(binding_records[0]["document"]["diagram_render_feedback"], feedback)
        self.assertEqual(request_records[0]["render_feedback"], feedback)
        self.assertIn("按render_feedback重画同一机制", request_records[0]["instruction"])

    def test_feedback_repair_does_not_fallback_to_excerpt_card(self):
        feedback = {"figure_id": "DIAGRAM_01_FIGURE", "reason": "diagram_parse_or_anchor_failed",
                    "previous_source": "flowchart LR\nA --> B"}
        document = {"family": "technical-solution", "metadata": {"title": "合成校验"},
            "diagram_render_feedback": feedback, "blocks": [
                {"id": "P1", "type": "paragraph", "text": PARAGRAPH_TEXT, "source_ids": ["S1"]},
                {"id": "DIAGRAM_01_FIGURE", "type": "figure", "caption": "设备布置核对关系"},
            ]}
        def invalid_model(_task, _fence, _attempt, _route, _request, *, output_validator):
            item = {"figure_id": "DIAGRAM_01_FIGURE", "title": "设备布置核对关系",
                "description": "设备布置和安全检查需由负责人核对。",
                "source": 'flowchart LR\nA["设备布置"] --> B["安全检查"]\nclick A "https://example.invalid"',
                "evidence_block_ids": ["B1"], "anchor_text": "设备布置"}
            return output_validator({"diagrams": [item]})

        from portal.product_models import DocumentTask
        with patch.object(DocumentTask.objects, "get", side_effect=AssertionError("excerpt fallback attempted")), \
                patch("portal.product_worker._model", side_effect=invalid_model):
            with self.assertRaises(ExecutionError) as caught:
                _generate_diagrams_uncached("test-task", 1, "test-attempt", document, draft=True)
        self.assertEqual(caught.exception.code, "diagram_generation_invalid")
        self.assertEqual(caught.exception.diagram_validation_reason, "unsupported or unsafe Mermaid source")

    def test_direction_normalization_changes_only_syntax_keyword(self):
        source = ('flowchart LR\nDirection LR\n'
                  'A["Direction LR"] --> B["设备布置"]\n')
        normalized = _draft_diagram_source(source)
        self.assertEqual(normalized, ('flowchart LR\ndirection LR\n'
            'A["Direction LR"] --> B["设备布置"]\n'))
