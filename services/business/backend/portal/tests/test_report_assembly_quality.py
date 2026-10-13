import json
import hashlib
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from portal.product_documents import (
    DocumentError, _diagram_evidence, _publish_render_snapshot, _render_draft_diagrams,
    _render_formal_diagrams, assembly_quality_issues, clean_report_paragraph, content_document, frozen_pack,
)


class ReportAssemblyQualityTests(SimpleTestCase):
    def setUp(self):
        self.task = SimpleNamespace(pk="synthetic", title="合成工程")
        self.input = SimpleNamespace(pk="input", sha256="1" * 64, payload={
            "items": [{"row_id": f"r{i}", "name": f"设备{i}", "quantity": "2", "unit": "台"}
                      for i in range(100)], "requirements": "保持项目事实", "conditions": [], "issues": [],
        })
        self.blueprint = SimpleNamespace(payload={"template_version": "frozen-original-v1", "missing": [], "conflicts": []})
        self.chapter = SimpleNamespace(payload={"chapter_id": "c1", "title": "第1章 供配电设计", "source_ids": ["r0"],
            "paragraphs": ["开关柜用于已确认供电范围的分配，实施前核对接线和保护资料；现场检查与验收依据由负责人确认。"]})

    def assemble(self, family="technical-solution", chapters=None, **options):
        return content_document(self.task, self.input, self.blueprint, chapters or [self.chapter], family, **options)

    def test_equipment_stays_in_sources_without_automatic_table_or_item_prose(self):
        original = deepcopy(self.input.payload)
        for family in ("technical-solution", "feasibility"):
            document = self.assemble(family)
            self.assertFalse(any(block["id"].startswith("INPUT_") for block in document["blocks"]))
            self.assertEqual(len(document["sources"]), 101)
            paragraph = next(block for block in document["blocks"] if block["id"].endswith("P1"))
            self.assertEqual(paragraph["source_ids"], ["S1"])
            self.assertEqual(json.loads(document["sources"][1]["text"]), original["items"][0])
        self.assertEqual(self.input.payload, original)

    def test_review_diagnostics_are_not_customer_pending_notes(self):
        issues = [{"code": "quantity_source_ambiguous", "chapter_id": "c1", "paragraph_index": i,
                   "claim": f"内部诊断{i}"} for i in range(200)]
        original = deepcopy(issues)
        document = self.assemble(draft=True, review_issues=issues)
        self.assertEqual(document["pending"], [])
        self.assertNotIn("内部诊断", "\n".join(block.get("text", "") for block in document["blocks"]))
        self.assertEqual(issues, original)

    def test_business_missing_conditions_are_summarized_once(self):
        self.blueprint.payload.update(missing=["负荷参数待确认。", "负荷参数待确认。"],
                                      conflicts=[" 负荷参数待确认 ", "建设单位需提供接线资料。"])
        document = self.assemble(draft=True)
        self.assertEqual(len(document["pending"]), 2)
        summaries = [block for block in document["blocks"] if block["id"].startswith("PENDING_TEXT")]
        self.assertEqual([block["text"] for block in summaries], [item["text"] for item in document["pending"]])
        self.assertEqual(sum(block["id"] == "PENDING_HEADING" for block in document["blocks"]), 1)

    def test_no_rotating_subheading_for_each_authored_paragraph(self):
        self.chapter.payload["paragraphs"] *= 12
        document = self.assemble()
        headings = [block for block in document["blocks"] if block["type"] == "heading"]
        self.assertFalse(any(block["level"] == 2 and not block["id"].startswith("DIAGRAM_") for block in headings))
        self.assertEqual(len([block for block in document["blocks"] if block["id"].startswith("C") and block["type"] == "paragraph"]), 12)

    def test_contract_fragments_filtered_but_valid_prose_and_metadata_preserved(self):
        valid = self.chapter.payload["paragraphs"][0]
        raw = [valid, 'source_ids', '{"source_ids": ["r0"]}', '```json\n"chapter_id": "c1",\n}\n```',
               '正文待生成', valid + '\n"source_ids": ["r0"]',
               '"source_ids": [\n"01234567-0123-0123-0123-0123456789ab",\n"r0"\n]']
        self.chapter.payload["paragraphs"] = raw
        original = deepcopy(self.chapter.payload)
        document = self.assemble()
        paragraphs = [block["text"] for block in document["blocks"] if block["type"] == "paragraph" and block["id"].startswith("C")]
        self.assertEqual(paragraphs, [valid, valid])
        issues = assembly_quality_issues([self.chapter])
        self.assertEqual([issue["paragraph_index"] for issue in issues], [1, 2, 3, 4, 5, 6])
        self.assertEqual(issues[1]["claim"], raw[2])
        self.assertEqual(self.chapter.payload, original)
        self.assertEqual(clean_report_paragraph('接口返回JSON，字段name用于设备名称。'), '接口返回JSON，字段name用于设备名称。')
        self.assertEqual(clean_report_paragraph('`source_ids`'), '')

    def test_empty_chapter_blocks_formal_but_preserves_other_draft_chapters(self):
        empty = SimpleNamespace(payload={"chapter_id": "c2", "title": "验收设计", "source_ids": ["r0"],
                                         "paragraphs": ['"source_ids": ["r0"]', "TODO"]})
        chapters = [self.chapter, empty]
        with self.assertRaises(DocumentError) as caught:
            self.assemble(chapters=chapters)
        self.assertEqual(caught.exception.code, "chapter_body_missing")
        self.assertEqual(caught.exception.diagnostic["chapter_ids"], ["c2"])
        document = self.assemble(chapters=chapters, draft=True)
        self.assertTrue(any("验收设计”缺少有效设计正文" in block.get("text", "") for block in document["blocks"]))
        self.assertTrue(any(block.get("text") == self.chapter.payload["paragraphs"][0] for block in document["blocks"]))
        self.assertEqual(len([block for block in document["blocks"] if block["type"] == "figure"]), 15)
        self.assertIn("chapter_body_missing", {issue["code"] for issue in assembly_quality_issues(chapters)})

    def test_template_version_and_frozen_hash_guards_unchanged(self):
        self.assertTrue(frozen_pack()["files"])
        self.blueprint.payload["template_version"] = "different-version"
        with self.assertRaises(DocumentError) as caught:
            self.assemble()
        self.assertEqual(caught.exception.code, "template_unavailable")


class DiagramReadingUnitIntegrationTests(SimpleTestCase):
    def setUp(self):
        self.figure = {"id": "DIAGRAM_01_FIGURE", "type": "figure", "path": "assets/diagram-01.png",
                       "caption": "设备连接", "alt": "依正文核对连接", "width_mm": 145,
                       "source_ids": ["S1"], "requirement_ids": []}
        self.document = {"family": "technical-solution", "blocks": [deepcopy(self.figure)], "pending": []}
        self.source = {"figure_id": self.figure["id"], "source": 'flowchart TD\nA["设备"] --> B["验收"]',
                       "evidence_block_ids": ["C1P1"]}

    def render(self, directory):
        panels = []
        for index, name in enumerate((self.figure["path"], "assets/diagram-01-unit-2.png"), 1):
            path = directory / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(f"synthetic reading unit {index}".encode())
            panels.append({"index": index, "total": 2, "path": name,
                           "imageSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "width_mm": 145, "min_font_pt": 12})
        return {"figures": [{"figure_id": self.figure["id"], "imageSha256": panels[0]["imageSha256"],
                             "sourceSha256": hashlib.sha256(self.source["source"].encode()).hexdigest(),
                             "layout": {"version": "word-readable-v1", "panels": panels}}]}

    def test_draft_recovery_verifies_every_reading_unit_and_source_hash(self):
        cached = {}
        def step(key, binding, execute, valid):
            if key not in cached or not valid(cached[key]):
                cached[key] = execute()
            return cached[key]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch("portal.product_documents._diagram_sources", return_value=[self.source]), \
                    patch("portal.product_documents.preflight_document_rendering", return_value={}), \
                    patch("portal.product_documents._render_one_diagram", side_effect=lambda *args: self.render(directory)) as renderer:
                first_document = deepcopy(self.document)
                first = _render_draft_diagrams(first_document, None, directory, step)
                self.assertEqual((first["rendered"], first["figure_count"], first["pending_count"]), (1, 2, 0))
                self.assertEqual([block["id"] for block in first_document["blocks"]],
                                 ["DIAGRAM_01_FIGURE", "DIAGRAM_01_FIGURE_PANEL_02"])
                self.assertEqual(first["figures"][1]["evidence_block_ids"], ["C1P1"])
                _render_draft_diagrams(deepcopy(self.document), None, directory, step)
                self.assertEqual(renderer.call_count, 1)
                (directory / "assets/diagram-01-unit-2.png").write_bytes(b"tampered panel")
                _render_draft_diagrams(deepcopy(self.document), None, directory, step)
                self.assertEqual(renderer.call_count, 2)
                cached[next(iter(cached))]["figures"][0]["sourceSha256"] = "0" * 64
                _render_draft_diagrams(deepcopy(self.document), None, directory, step)
                self.assertEqual(renderer.call_count, 3)

    def test_formal_layout_preserves_source_binding_and_publishes_all_verified_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "workspace"
            directory.mkdir()
            raw = {"rendered": 1, "engine": "mermaid-js-12.0.0", "sourcePersisted": False,
                   "securityLevel": "strict", "blockedNetworkRequests": 0,
                   "bundleSha256": "a" * 64, "manifestSha256": "b" * 64,
                   "runtimeVersions": {"mermaid": "12.0.0", "katex": "0.18.2", "lodash-es": "4.18.1"},
                   **self.render(directory)}
            self.assertEqual(_diagram_evidence(json.dumps(raw), 1)["figures"][0]["layout"]["panels"][1]["min_font_pt"], 12)
            document = deepcopy(self.document)
            with patch("portal.product_documents._diagram_sources", return_value=[self.source]), \
                    patch("portal.product_documents._mermaid_runtime", return_value=Path("synthetic-node")), \
                    patch("portal.product_documents._mermaid_chromium", return_value=Path("synthetic-chromium")), \
                    patch("portal.product_documents.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(raw), stderr="")):
                evidence = _render_formal_diagrams(document, None, directory, directory / "content.json", {"figure_count": 1}, None)
            self.assertEqual(evidence["figure_count"], 2)
            self.assertEqual(evidence["figures"][1]["source_sha256"], raw["figures"][0]["sourceSha256"])
            (directory / "draft.docx").write_bytes(b"synthetic document")
            (directory / "draft.quality.json").write_text("{}")
            promoted = _publish_render_snapshot(root, directory, SimpleNamespace(pk="synthetic"), "draft.docx", document,
                                                {"diagram_generation": evidence, "word_field_cache": {}})
            self.assertTrue((promoted.parent / "assets/diagram-01-unit-2.png").is_file())
            self.assertEqual(json.loads((promoted.parent / "content.json").read_bytes()), document)
