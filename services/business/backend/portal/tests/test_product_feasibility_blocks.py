"""Authored guide tables/headings survive the existing renderer without filler."""

import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.test import SimpleTestCase

from portal import product_feasibility_blocks as blocks
from portal import product_feasibility as guide


PACK = Path(__file__).resolve().parents[1] / "product_assets" / "bj_docs"
RUNTIME = Path(__file__).resolve().parents[3] / ".runtime" / "product-documents-python" / "Scripts" / "python.exe"


class ProductFeasibilityBlocksTests(SimpleTestCase):
    def authored(self, paragraphs):
        return blocks.authored_blocks(paragraphs, "CONE", ["S1"], ["R1"])

    def test_headings_preserve_text_and_never_make_empty_or_skipped_sections(self):
        result = self.authored(["### 仅有三级时降为二级\n正文。", "## 4.1 业务需求", "### 4.1.1 C#", "具体论证。",
                                "### 空小节", "## 结尾空小节", "#### 深层标题按原文保留"])
        headings = [(value["level"], value["text"]) for value in result if value["type"] == "heading"]
        self.assertEqual(headings[:3], [(2, "仅有三级时降为二级"), (2, "业务需求"), (3, "C#")])
        self.assertIn("### 空小节", [value.get("text") for value in result if value["type"] == "paragraph"])
        self.assertEqual(result[-1]["text"], "#### 深层标题按原文保留")
        self.assertEqual(self.authored(["## 没有正文"])[0],
                         {"id": "CONEB1", "type": "paragraph", "text": "## 没有正文",
                          "source_ids": ["S1"], "requirement_ids": ["R1"]})
        self.assertTrue(all(not any(key.startswith("_") for key in value) for value in result))

    def test_caption_columns_cells_missing_values_and_literal_prose_survive(self):
        result = self.authored(["原样保留 a | b。", "表4-6 本项目数据需求清单",
                                "| 数据名称 | 单位 | 数据量（条） |\n| :--- | ---: | --- |\n| 人口数据 | 待确认 | |\n| a\\|b | 已有单位 | 0 |",
                                "公式 x|y 与未确认限定均保留。"])
        table = next(value for value in result if value["type"] == "table")
        self.assertEqual(table["caption"], "表4-6 本项目数据需求清单")
        self.assertEqual(table["columns"], ["数据名称", "单位", "数据量（条）"])
        self.assertEqual(table["rows"], [["人口数据", "待确认", "待确认"], ["a|b", "已有单位", "0"]])
        self.assertEqual(table["units"], ["—", "—", "—"])
        self.assertEqual(result[0]["text"], "原样保留 a | b。")
        self.assertEqual(result[-1]["text"], "公式 x|y 与未确认限定均保留。")
        self.assertEqual(len({value["id"] for value in result}), len(result))
        self.assertTrue(all(value["source_ids"] == ["S1"] and value["requirement_ids"] == ["R1"] for value in result))

    def test_malformed_and_uncaptioned_tables_remain_literal_without_invented_rows(self):
        cases = [
            ["表1-1 标题", "| 列A | 列B |", "| -- | -- |", "| 值A | 值B |"],
            ["表1-1 标题", "| 列A | 列B |", "| --- | --- |", "| 只有一个值 |"],
            ["表1-1 标题", "| 列A | 列B |", "| --- | --- |"],
            ["| 列A | 列B |", "| --- | --- |", "| 值A | 值B |"],
            ["表1-1 单列", "| 列A |", "| --- |", "| 值A |"],
        ]
        for source in cases:
            with self.subTest(source=source):
                result = self.authored(source)
                self.assertTrue(all(value["type"] == "paragraph" for value in result))
                self.assertEqual([value["text"] for value in result], source)

    def test_wide_tables_keep_every_column_cell_and_row_in_existing_prototypes(self):
        profile = json.loads((PACK / "assets" / "feasibility" / "profile.json").read_text(encoding="utf-8"))
        for width in (2, 3, 4, 5, 6, 7, 8, 9, 15, 17):
            with self.subTest(width=width):
                columns = [f"列{number}" for number in range(width)]
                first = [f"首行{number}" for number in range(width)]
                last = [f"末行{number}" for number in range(width)]
                source = ["表3-1 宽表现状", "|" + "|".join(columns) + "|",
                          "|" + "|".join(["---"] * width) + "|",
                          "|" + "|".join(first) + "|", "|" + "|".join(last) + "|"]
                result = self.authored(source)
                self.assertEqual([cell for value in result for cell in value["columns"]], columns)
                self.assertEqual([cell for value in result for cell in value["rows"][0]], first)
                self.assertEqual([cell for value in result for cell in value["rows"][1]], last)
                for value in result:
                    prototype = profile["tables"][value["prototype"]]
                    self.assertTrue(prototype["variable_rows"])
                    self.assertEqual(prototype["columns"], len(value["columns"]))
                    self.assertEqual(len(value["rows"]), 2)

    def test_figures_come_from_approved_specs_without_generic_twenty_or_inherited_duplicates(self):
        self.assertEqual(blocks.figure_plan({"chapters": []}, "road-only"), [])
        self.assertFalse(any(value["type"] == "figure" for value in self.authored(["本期只修道路，不建设信息系统。"])))
        figure = {"id": "图5-1", "kind": "figure", "title": "总体架构图"}
        selected = [{"table_figure_specs": [figure, {"id": "表5-1", "kind": "table", "title": "功能对比"}],
                     "inherited_sections": [{"table_figure_specs": [figure]}]},
                    {"table_figure_specs": [{"id": "图5-2", "kind": "figure", "title": "数据架构图"}]}]
        with patch.object(blocks, "chapter_requirements", return_value=selected):
            self.assertEqual(blocks.figure_plan({}, "actual"), ["总体架构图", "数据架构图"])

    def test_real_asset_inheritance_selects_figures_and_tail_headings_have_no_empty_sections(self):
        catalog = guide.catalog()
        sections = [section for chapter in catalog["chapters"] for section in chapter["sections"]] + catalog["appendices"]
        blueprint = {"chapters": [{"id": "actual", "family": "feasibility", "title": "实际应用设计"}],
                     "feasibility_guide": {"asset_sha256": guide.asset_hash(), "sections": [
                         {"section_id": section["id"], "status": "include" if section["id"] == "5.2.2" else "not_applicable",
                          "chapter_ids": ["actual"] if section["id"] == "5.2.2" else [],
                          "reason": "合成裁剪，仅验证实际资产中应用系统N的要求继承。"} for section in sections]}}
        selected = guide.chapter_requirements(blueprint, "actual")
        self.assertTrue(selected[0]["inherited_sections"])
        self.assertEqual(blocks.figure_plan(blueprint, "actual"), ["应用系统架构图", "系统功能关系图"])
        dangling = self.authored(["## 有正文", "正文。", "### 空子节", "## 空尾节"])
        self.assertEqual([value["text"] for value in dangling if value["type"] == "heading"], ["有正文"])
        for entry in blueprint["feasibility_guide"]["sections"]:
            entry.update(status="include" if entry["section_id"] == "1.1" else "not_applicable",
                         chapter_ids=["actual"] if entry["section_id"] == "1.1" else [],
                         reason="合成范围仅需项目名称，本期无信息系统设计。")
        self.assertEqual(blocks.figure_plan(blueprint, "actual"), [])

    def test_native_docx_contains_authored_table_cells_caption_and_pending_values(self):
        authored = self.authored(["## 现状分析", "实际范围与尚待确认的信息均在原文保留。",
                                  "表3-1 项目资源现状",
                                  "| 名称 | 数量 | 状态 |\n| --- | --- | --- |\n| 本期资源 | | 待核实 |",
                                  "表3-2 宽表验证",
                                  "|" + "|".join(f"宽列{index}" for index in range(9)) + "|",
                                  "|" + "|".join(["---"] * 9) + "|",
                                  "|" + "|".join(f"宽值{index}" for index in range(9)) + "|",
                                  "### 详细说明", "说明内容。", "### 无正文子节", "## 无正文尾节"])
        content = {"version": 1, "family": "feasibility",
                   "metadata": {"id": "TONE", "title": "合成内容保留验证", "subtitle": "合成验证",
                                "date": "2026-10-15", "organization": "合成单位", "status": "synthetic"},
                   "sources": [{"id": "S1", "text": "合成验证资料"}],
                   "requirements": [{"id": "R1", "text": "保留完整表格内容"}], "pending": [],
                   "blocks": [{"id": "H1", "type": "heading", "level": 1, "text": "项目概况",
                               "source_ids": ["S1"], "requirement_ids": ["R1"]}, *authored]}
        with tempfile.TemporaryDirectory(prefix="authored-feasibility-") as directory:
            root = Path(directory)
            source, target = root / "content.json", root / "report.docx"
            source.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([str(RUNTIME), "-B", str(PACK / "scripts" / "artifacts.py"),
                                     "docx", str(source), str(target)], cwd=root, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace")[-3000:])
            with ZipFile(target) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "".join(node.text or "" for node in document.findall(".//w:t", ns))
            for expected in ("项目资源现状", "名称", "数量", "状态", "本期资源", "待确认", "待核实"):
                self.assertIn(expected, text)
            for index in range(9):
                self.assertIn(f"宽列{index}", text)
                self.assertIn(f"宽值{index}", text)
            self.assertEqual(len(document.findall(".//w:tbl", ns)), 3)
