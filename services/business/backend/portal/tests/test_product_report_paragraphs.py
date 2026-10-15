import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from django.conf import settings
from django.test import SimpleTestCase

from portal.product_documents import content_document, frozen_pack


EXTERNAL_FIXTURE = os.environ.get("PRODUCT_REPORT_PARAGRAPH_FIXTURE", "")


class ProductReportParagraphTests(SimpleTestCase):
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    def test_newlines_become_styled_docx_paragraphs_and_table_breaks_remain_soft(self):
        task = SimpleNamespace(pk="paragraph-test", title="正文分段合成测试")
        revision = SimpleNamespace(pk="input", sha256="1" * 64, payload={
            "requirements": "保持来源映射", "conditions": ["保留需求映射"],
            "items": [{"row_id": "r1", "name": "合成设备"}], "sources": [], "issues": [],
        })
        blueprint = SimpleNamespace(payload={
            "template_version": "frozen-original-v1", "missing": [], "conflicts": [],
        })
        chapter = SimpleNamespace(payload={
            "chapter_id": "paragraph-test-chapter", "title": "正文测试", "source_ids": ["r1"],
            "paragraphs": ["第一自然段第一行。\r\n第二行。\r\n \r\n第三自然段。", "后续原段。"],
        })
        document = content_document(task, revision, blueprint, [chapter])
        stable = "C" + hashlib.sha256(chapter.payload["chapter_id"].encode()).hexdigest()[:24]
        body = [block for block in document["blocks"] if block["id"].startswith(stable + "P")]
        self.assertEqual([block["id"] for block in body], [
            stable + "P1", stable + "P1_2", stable + "P1_3", stable + "P2",
        ])
        self.assertEqual([block["text"] for block in body], [
            "第一自然段第一行。", "第二行。", "第三自然段。", "后续原段。",
        ])
        self.assertTrue(all(block["source_ids"] == ["S1"] for block in body))
        self.assertTrue(all(block["requirement_ids"] == ["R1", "RINPUT"] for block in body))

        # Table-cell newlines are deliberate soft breaks and bypass body-block splitting.
        document["blocks"] = [block for block in document["blocks"] if block["type"] != "figure"]
        document["blocks"].append({
            "id": "TESTTABLE", "type": "table", "prototype": "table0",
            "columns": ["字段", "说明"], "units": ["不适用", "不适用"],
            "rows": [["单元格第一行\n单元格第二行\n单元格第三行", "保留"]],
            "caption": "合法软换行测试", "source_ids": ["S1"], "requirement_ids": ["R1"],
        })
        pack = Path(__file__).parents[1] / "product_assets" / "bj_docs"
        assembler = pack / "scripts" / "artifacts.py"
        runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "content.json"
            target = root / "report.docx"
            source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([str(runtime), "-B", str(assembler), "docx", str(source), str(target)],
                                    cwd=root, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace")[-2000:])

            with ZipFile(target) as archive:
                tree = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = list(tree.iter(self.W + "p"))
            by_bookmark = {
                start.get(self.W + "name"): paragraph
                for paragraph in paragraphs
                for start in paragraph.findall(self.W + "bookmarkStart")
            }
            for block in body:
                paragraph = by_bookmark[block["id"]]
                self.assertEqual("".join(node.text or "" for node in paragraph.iter(self.W + "t")), block["text"])
                self.assertIsNone(paragraph.find(f".//{self.W}br"))
                spacing = paragraph.find(f"{self.W}pPr/{self.W}spacing")
                indent = paragraph.find(f"{self.W}pPr/{self.W}ind")
                run = paragraph.find(self.W + "r")
                self.assertEqual((spacing.get(self.W + "line"), spacing.get(self.W + "lineRule")), ("360", "exact"))
                self.assertEqual(indent.get(self.W + "firstLine"), "480")
                self.assertEqual(run.find(f"{self.W}rPr/{self.W}rFonts").get(self.W + "eastAsia"), "宋体")
                self.assertEqual(run.find(f"{self.W}rPr/{self.W}sz").get(self.W + "val"), "24")

            first_cell = tree.find(f".//{self.W}tbl/{self.W}tr[2]/{self.W}tc")
            self.assertEqual(len(first_cell.findall(f".//{self.W}br")), 2)

    @unittest.skipUnless(EXTERNAL_FIXTURE and Path(EXTERNAL_FIXTURE).is_file(),
                         "set PRODUCT_REPORT_PARAGRAPH_FIXTURE to run the private historical DOCX check")
    def test_henggou_historical_paragraph_reassembles_from_private_fixture(self):
        source_path = Path(EXTERNAL_FIXTURE)
        source_bytes = source_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        with ZipFile(source_path) as archive:
            tree = ET.fromstring(archive.read("word/document.xml"))
        original_paragraphs = tree.find(f".//{self.W}body").findall(self.W + "p")
        source_paragraph = original_paragraphs[87]
        original_breaks = len(list(source_paragraph.iter(self.W + "br")))
        source_chars = sum(len(node.text or "") for node in source_paragraph.iter(self.W + "t"))
        original_text = "".join(
            "\n" if node.tag in (self.W + "br", self.W + "cr") else
            "\t" if node.tag == self.W + "tab" else
            (node.text or "") if node.tag == self.W + "t" else ""
            for node in source_paragraph.iter()
        )
        line_slots = len(original_text.splitlines())
        parts = [part.strip() for part in original_text.splitlines() if part.strip()]
        self.assertEqual((source_chars, original_breaks, line_slots, len(parts)), (1684, 6, 7, 4))

        task = SimpleNamespace(pk="henggou-paragraph-regression", title="横沟供配电设备方案")
        revision = SimpleNamespace(pk="historical-input", sha256="1" * 64, payload={
            "requirements": "", "conditions": [], "items": [], "sources": [], "issues": [],
        })
        blueprint = SimpleNamespace(payload={
            "template_version": "frozen-original-v1", "missing": [], "conflicts": [],
        })
        chapter = SimpleNamespace(payload={
            "chapter_id": "historical-paragraph-87", "title": "供配电设计", "source_ids": [],
            "paragraphs": [original_text],
        })
        stable = "C" + hashlib.sha256(chapter.payload["chapter_id"].encode()).hexdigest()[:24]
        pack = Path(__file__).parents[1] / "product_assets" / "bj_docs"
        frozen_manifest_sha256 = hashlib.sha256((pack / "manifest.json").read_bytes()).hexdigest()
        runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for family in ("technical-solution", "feasibility"):
                frozen_pack(family)
                document = content_document(task, revision, blueprint, [chapter], family)
                body = [block for block in document["blocks"] if block["id"].startswith(stable + "P")]
                self.assertEqual(len(body), len(parts))
                self.assertEqual([block["text"] for block in body], parts)
                document["blocks"] = [block for block in document["blocks"] if block["type"] != "figure"]
                source = root / f"{family}.json"
                target = root / f"{family}.docx"
                source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
                result = subprocess.run([str(runtime), "-B", str(pack / "scripts" / "artifacts.py"),
                                         "docx", str(source), str(target)], cwd=root, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0,
                                 result.stderr.decode("utf-8", errors="replace")[-2000:])
                manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
                template_sha256 = next(item["sha256"] for item in manifest["files"]
                                       if item["path"] == f"assets/{family}/template.docx")
                with ZipFile(target) as archive:
                    output = ET.fromstring(archive.read("word/document.xml"))
                    styles = ET.fromstring(archive.read("word/styles.xml"))
                output_paragraphs = list(output.iter(self.W + "p"))
                bookmarks = {
                    start.get(self.W + "name"): paragraph
                    for paragraph in output_paragraphs
                    for start in paragraph.findall(self.W + "bookmarkStart")
                }
                generated = [bookmarks[block["id"]] for block in body]
                self.assertEqual(len(generated), len(parts))
                for paragraph, expected in zip(generated, parts):
                    self.assertEqual("".join(node.text or "" for node in paragraph.iter(self.W + "t")), expected)
                    self.assertIsNone(paragraph.find(f".//{self.W}br"))
                    spacing = paragraph.find(f"{self.W}pPr/{self.W}spacing")
                    indent = paragraph.find(f"{self.W}pPr/{self.W}ind")
                    run = paragraph.find(self.W + "r")
                    if family == "technical-solution":
                        self.assertEqual((spacing.get(self.W + "line"), spacing.get(self.W + "lineRule")),
                                         ("360", "exact"))
                        self.assertEqual(indent.get(self.W + "firstLine"), "480")
                    else:
                        self.assertEqual((spacing.get(self.W + "line"), spacing.get(self.W + "lineRule")),
                                         ("360", "auto"))
                        self.assertEqual(indent.get(self.W + "firstLine"), "480")
                        self.assertEqual(indent.get(self.W + "firstLineChars"), "200")
                    self.assertEqual(run.find(f"{self.W}rPr/{self.W}rFonts").get(self.W + "eastAsia"), "宋体")
                    self.assertEqual(run.find(f"{self.W}rPr/{self.W}sz").get(self.W + "val"), "24")
                print(json.dumps({"source_sha256": source_sha256, "source_paragraph_index": 87,
                    "source_chars": source_chars, "source_breaks": original_breaks,
                    "line_slots": line_slots, "nonempty_segments": len(parts),
                    "generated_paragraphs": len(generated), "family": family,
                    "direct_first_line_twips": "480",
                    "first_line_chars": "200" if family == "feasibility" else None,
                    "template_sha256": template_sha256,
                    "manifest_sha256": frozen_manifest_sha256},
                    ensure_ascii=False, sort_keys=True))
