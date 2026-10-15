"""Contract checks for the user-requested feasibility report format."""
import base64
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings

from portal.product_docx_layout import normalize_docx_layout


BACKEND = Path(__file__).parents[1]
PACK = BACKEND / "product_assets" / "bj_docs"
ASSEMBLER = PACK / "scripts" / "artifacts.py"
RUNTIME = Path(__file__).resolve().parents[3] / ".runtime" / "product-documents-python" / "Scripts" / "python.exe"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6WQAAAAASUVORK5CYII="
)


def _text(node):
    return "".join(item.text or "" for item in node.iter(W + "t"))


def _field_instructions(root):
    return [node.text or "" for node in root.iter(W + "instrText")]


def _effective_run_value(paragraph, styles, property_name, attribute):
    run = paragraph.find(W + "r")
    if run is not None:
        direct = run.find(f"{W}rPr/{W}{property_name}")
        if direct is not None and direct.get(W + attribute) is not None:
            return direct.get(W + attribute)
    paragraph_properties = paragraph.find(W + "pPr")
    if paragraph_properties is not None:
        direct = paragraph_properties.find(f"{W}rPr/{W}{property_name}")
        if direct is not None and direct.get(W + attribute) is not None:
            return direct.get(W + attribute)
    reference = paragraph.find(f"{W}pPr/{W}pStyle")
    style_id = reference.get(W + "val") if reference is not None else None
    visited = set()
    while style_id and style_id not in visited:
        visited.add(style_id)
        style = styles.get(style_id)
        if style is None:
            break
        run_properties = style.find(f"{W}rPr")
        if run_properties is not None:
            value = run_properties.find(f"{W}{property_name}")
            if value is not None and value.get(W + attribute) is not None:
                return value.get(W + attribute)
        based_on = style.find(f"{W}basedOn")
        style_id = based_on.get(W + "val") if based_on is not None else None
    return None


@override_settings(PRODUCT_DOCUMENT_PYTHON=str(RUNTIME))
class ProductFeasibilityFormatTests(SimpleTestCase):
    def test_cli_feasibility_docx_matches_guide_and_preserves_authored_semantics(self):
        content = {
            "version": 1,
            "family": "feasibility",
            "metadata": {
                "id": "synthetic-feasibility", "title": "合成园区建设可行性研究报告",
                "subtitle": "格式契约合成样例", "date": "2026年10月",
                "organization": "合成建设单位", "status": "synthetic",
            },
            "sources": [{"id": "S1", "text": "仅用于格式接口验证的合成来源。"}],
            "requirements": [{"id": "R1", "text": "保留合成正文、表格和插图。"}],
            "pending": [{"id": "PENDING1", "text": "联系信息待提供。"}],
            "blocks": [
                {"id": "H1", "type": "heading", "level": 1, "text": "项目概述",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "P1", "type": "paragraph", "text": "合成正文保留字句与来源，不代表真实项目结论。",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "H2", "type": "heading", "level": 2, "text": "建设背景",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "P2", "type": "paragraph", "text": "第二层级下的合成论证段落。",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "H3", "type": "heading", "level": 3, "text": "现状说明",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "P3", "type": "paragraph", "text": "第三层级下的合成论证段落。",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "T1", "type": "table", "prototype": "table0",
                 "columns": ["项目", "说明"], "units": ["不适用", "不适用"],
                 "rows": [["合成条目", "仅验证表格格式"]], "caption": "合成表格",
                 "source_ids": ["S1"], "requirement_ids": ["R1"]},
                {"id": "F1", "type": "figure", "path": "figure.png", "caption": "合成示意图",
                 "width_mm": 20, "alt": "单像素合成插图", "source_ids": ["S1"],
                 "requirement_ids": ["R1"]},
            ],
        }
        with tempfile.TemporaryDirectory(prefix="feasibility-format-") as directory:
            root = Path(directory)
            source, target = root / "content.json", root / "report.docx"
            source.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            (root / "figure.png").write_bytes(ONE_PIXEL_PNG)
            result = subprocess.run(
                [str(RUNTIME), "-B", str(ASSEMBLER), "docx", str(source), str(target)],
                cwd=root, capture_output=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace")[-3000:])

            quality = json.loads(target.with_suffix(".quality.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["guide_format_status"], "user_requested_yulin_202403")
            self.assertFalse(quality["company_identity"]["logo_used"])
            heading_bookmarks = [quality["bookmark_map"][block["id"]]
                                 for block in content["blocks"] if block["type"] == "heading"]
            normalized, evidence = normalize_docx_layout(target.read_bytes(), heading_bookmarks)
            self.assertTrue(normalized)
            self.assertEqual(evidence["heading_count"], 3)
            self.assertEqual(evidence["toc_end_count"], 1)
            self.assertEqual(evidence["visual_review"], "not_run")

            with ZipFile(target) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                styles = ET.fromstring(archive.read("word/styles.xml"))
                media = [name for name in archive.namelist()
                         if name.startswith("word/media/") and not name.endswith("/")]
                headers = [ET.fromstring(archive.read(name)) for name in archive.namelist()
                           if name.startswith("word/header") and name.endswith(".xml")]
                footers = [ET.fromstring(archive.read(name)) for name in archive.namelist()
                           if name.startswith("word/footer") and name.endswith(".xml")]

            paragraphs = list(document.iter(W + "p"))
            texts = [_text(paragraph) for paragraph in paragraphs]
            self.assertLess(texts.index("合成园区建设"), texts.index("可行性研究报告"))
            for field_text in (
                "项目建设单位：待提供", "编制单位：合成建设单位", "编制日期：2026年10月",
                "项目建设单位联系人：待提供", "联系方式：待提供",
            ):
                self.assertIn(field_text, texts)
            self.assertEqual(len(media), 1, "only the authored synthetic figure may be embedded; no logo")

            instructions = _field_instructions(document)
            toc_instructions = [value for value in instructions if value.strip().startswith("TOC")]
            self.assertEqual(len(toc_instructions), 1)
            self.assertIn('\\o "1-3"', toc_instructions[0])
            toc_styles = {}
            for level in range(1, 4):
                expected_name = f"toc {level}"
                matches = [style for style in styles.iter(W + "style")
                           if (style.find(W + "name") is not None
                               and style.find(W + "name").get(W + "val", "").casefold() == expected_name)]
                self.assertEqual(len(matches), 1, f"exactly one built-in TOC style named {expected_name}")
                toc_styles[level] = matches[0]
            for style in toc_styles.values():
                spacing = style.find(f"{W}pPr/{W}spacing")
                fonts = style.find(f"{W}rPr/{W}rFonts")
                size = style.find(f"{W}rPr/{W}sz")
                bold = style.find(f"{W}rPr/{W}b")
                self.assertEqual((spacing.get(W + "line"), spacing.get(W + "lineRule")), ("360", "auto"))
                self.assertEqual(fonts.get(W + "eastAsia"), "宋体")
                self.assertEqual(size.get(W + "val"), "24")
                self.assertEqual(bold.get(W + "val"), "0")

            sections = list(document.iter(W + "sectPr"))
            self.assertEqual(len(sections), 3, "cover/signature, TOC, and body sections")
            self.assertIsNone(sections[0].find(W + "pgNumType"))
            self.assertEqual((sections[1].find(W + "pgNumType").get(W + "fmt"),
                              sections[1].find(W + "pgNumType").get(W + "start")), ("upperRoman", "1"))
            self.assertEqual((sections[2].find(W + "pgNumType").get(W + "fmt"),
                              sections[2].find(W + "pgNumType").get(W + "start")), ("decimal", "1"))
            for section in sections:
                margins = section.find(W + "pgMar")
                self.assertEqual(tuple(margins.get(W + key) for key in ("top", "bottom", "left", "right")),
                                 ("1440", "1440", "1803", "1803"))

            page_fields = " ".join(value for footer in footers for value in _field_instructions(footer)).upper()
            self.assertIn("PAGE", page_fields)
            self.assertIn("PAGEREF", page_fields)
            self.assertNotIn("NUMPAGES", page_fields)
            self.assertNotIn("SECTIONPAGES", page_fields)
            self.assertTrue(any("YulinFeasibilityBodyEnd" in value for value in _field_instructions(
                next(footer for footer in footers if any(
                    "PAGEREF" in value.upper() for value in _field_instructions(footer))))))

            header_paragraphs = [paragraph for header in headers for paragraph in header.iter(W + "p")
                                 if "合成园区建设" in _text(paragraph)]
            self.assertTrue(header_paragraphs)
            for paragraph in header_paragraphs:
                self.assertEqual(paragraph.find(f"{W}pPr/{W}jc").get(W + "val"), "right")
                run = paragraph.find(W + "r")
                self.assertEqual(run.find(f"{W}rPr/{W}rFonts").get(W + "eastAsia"), "宋体")
                self.assertEqual(run.find(f"{W}rPr/{W}sz").get(W + "val"), "21")

            authored_heading = {
                level: next(paragraph for paragraph in paragraphs
                            if quality["bookmark_map"][f"H{level}"] in [
                                node.get(W + "name") for node in paragraph.findall(W + "bookmarkStart")])
                for level in (1, 2, 3)
            }
            style_map = {style.get(W + "styleId"): style for style in styles.iter(W + "style")}
            self.assertEqual([_text(authored_heading[level]) for level in (1, 2, 3)],
                             ["第1章 项目概述", "1.1 建设背景", "1.1.1 现状说明"])
            for level, (size, spacing_points) in {1: ("44", "360"), 2: ("36", "240"), 3: ("32", "120")}.items():
                paragraph = authored_heading[level]
                spacing = paragraph.find(f"{W}pPr/{W}spacing")
                self.assertEqual(_effective_run_value(paragraph, style_map, "rFonts", "eastAsia"), "黑体")
                self.assertEqual(_effective_run_value(paragraph, style_map, "sz", "val"), size)
                self.assertEqual(_effective_run_value(paragraph, style_map, "b", "val"),
                                 "1" if level == 1 else "0")
                self.assertEqual(spacing.get(W + "after"), spacing_points)
                if level == 1:
                    self.assertEqual(paragraph.find(f"{W}pPr/{W}jc").get(W + "val"), "center")
                    self.assertEqual(spacing.get(W + "line"), "240")
                    self.assertEqual(spacing.get(W + "before"), "360")
                elif level == 2:
                    self.assertEqual((spacing.get(W + "before"), spacing.get(W + "line")), ("240", "240"))
                else:
                    self.assertEqual((spacing.get(W + "before"), spacing.get(W + "line")), ("120", "240"))

            body_paragraph = next(paragraph for paragraph in paragraphs
                                  if _text(paragraph) == "合成正文保留字句与来源，不代表真实项目结论。")
            spacing = body_paragraph.find(f"{W}pPr/{W}spacing")
            indent = body_paragraph.find(f"{W}pPr/{W}ind")
            body_run = body_paragraph.find(W + "r")
            self.assertEqual((spacing.get(W + "line"), spacing.get(W + "lineRule")), ("360", "auto"))
            self.assertEqual((indent.get(W + "firstLine"), indent.get(W + "firstLineChars")), ("480", "200"))
            self.assertEqual(body_run.find(f"{W}rPr/{W}rFonts").get(W + "eastAsia"), "宋体")
            self.assertEqual(body_run.find(f"{W}rPr/{W}rFonts").get(W + "ascii"), "Times New Roman")
            self.assertEqual(body_run.find(f"{W}rPr/{W}sz").get(W + "val"), "24")

            table_caption = next(paragraph for paragraph in paragraphs if _text(paragraph).startswith("表1-1 "))
            figure_caption = next(paragraph for paragraph in paragraphs if _text(paragraph).startswith("图1-1 "))
            body = document.find(f"{W}body")
            direct_nodes = list(body)
            table_caption_node = next(node for node in direct_nodes
                                      if node.tag == W + "p" and _text(node) == _text(table_caption))
            table_index = direct_nodes.index(table_caption_node)
            self.assertEqual(direct_nodes[table_index + 1].tag, W + "tbl")
            figure_node = next(node for node in direct_nodes
                               if node.tag == W + "p" and node.find(f".//{W}drawing") is not None)
            figure_index = direct_nodes.index(figure_node)
            self.assertEqual(direct_nodes[figure_index + 1].tag, W + "p")
            self.assertTrue(_text(direct_nodes[figure_index + 1]).startswith("图1-1 "))
            for caption in (table_caption, figure_caption):
                run = caption.find(W + "r")
                self.assertEqual(run.find(f"{W}rPr/{W}rFonts").get(W + "eastAsia"), "黑体")
                self.assertEqual(run.find(f"{W}rPr/{W}sz").get(W + "val"), "24")

            table = document.find(f".//{W}tbl")
            table_width = table.find(f"{W}tblPr/{W}tblW")
            self.assertEqual((table_width.get(W + "w"), table_width.get(W + "type")), ("9071", "dxa"))
            rows = table.findall(W + "tr")
            self.assertEqual(rows[0].find(f"{W}trPr/{W}tblHeader").get(W + "val"), "1")
            for row in rows:
                height = row.find(f"{W}trPr/{W}trHeight")
                self.assertEqual(height.get(W + "val"), "397")
                for paragraph in row.iter(W + "p"):
                    spacing = paragraph.find(f"{W}pPr/{W}spacing")
                    run = paragraph.find(W + "r")
                    self.assertEqual((spacing.get(W + "line"), spacing.get(W + "lineRule")), ("240", "auto"))
                    self.assertEqual(run.find(f"{W}rPr/{W}rFonts").get(W + "eastAsia"), "宋体")
                    self.assertEqual(run.find(f"{W}rPr/{W}rFonts").get(W + "ascii"), "Times New Roman")
                    self.assertEqual(run.find(f"{W}rPr/{W}sz").get(W + "val"), "21")

            block_text = " ".join(_text(paragraph) for paragraph in paragraphs)
            self.assertIn("合成正文保留字句与来源，不代表真实项目结论。", block_text)
            self.assertIn("合成条目", block_text)
            self.assertIn("合成示意图", block_text)
