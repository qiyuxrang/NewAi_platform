import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree
from zipfile import ZipFile

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from portal.product_presentation import SCRIPT, _valid_manifest, render_presentation_draft


def warning_pair():
    families = ("technical-solution", "feasibility")
    return {"approval_inherited": False, "sha256": "c" * 64,
        "sources": [{"family": family, "id": str(index), "version": 1, "sha256": "a" * 64}
                    for index, family in enumerate(families)],
        "blocks": [block for family in families for block in (
            {"ref": family + ":H1", "type": "heading", "level": 1, "text": "项目方案"},
            {"ref": family + ":P1", "type": "paragraph", "text": "设备需求来自原始清单，实施窗口与数量需人工核实。"},
            {"ref": family + ":DIAGRAM_01_FIGURE_PENDING", "type": "paragraph", "text": "图表待补：总体架构。"})],
        "pending": [{"text": "图表待补：总体架构。", "refs": ["technical-solution:PEND_DIAGRAM_01_FIGURE"]}],
        "diagram_pending": [{"family": family, "figure_id": "DIAGRAM_01_FIGURE", "error_code": "diagram_render_failed",
                             "stage": "diagram_render"} for family in families],
        "draft_quality": {"reports": [{"family": family, "quality_issue_count": 2,
            "quality_issue_codes": ["quantity_source_mismatch", "output_length_below_target"],
            "actual_characters": 100, "minimum_characters": 50000, "human_review_required": True} for family in families]}}


class PresentationDraftWarningTests(SimpleTestCase):
    def setUp(self):
        self.runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
        if not self.runtime.is_absolute():
            self.runtime = settings.BASE_DIR / self.runtime
        if not self.runtime.is_file():
            self.fail("isolated document runtime is required for real PPTX checks")
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.override = override_settings(PRODUCT_STORAGE_ROOT=Path(self.storage.name),
            PRODUCT_DOCUMENT_PYTHON=self.runtime, PRODUCT_OFFICE_RENDER_ENABLED=False,
            PRODUCT_DOCUMENT_RENDER_TIMEOUT_SECONDS=60)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_real_pptx_all_report_images_pending_keeps_warnings_and_failed_gate(self):
        pair = warning_pair()
        result = render_presentation_draft(SimpleNamespace(pk=uuid.uuid4(), title="草稿警告验证"), pair)
        evidence = result["render_evidence"]
        self.assertEqual(evidence["quality_gate"]["status"], "fail")
        self.assertEqual(evidence["visual_asset_count"], 0)
        self.assertEqual(evidence["diagram_generation"]["source_image_count"], 0)
        self.assertEqual(evidence["diagram_generation"]["rendered"], 0)
        self.assertEqual(evidence["diagram_generation"]["planned_count"], 2)
        self.assertEqual(evidence["diagram_generation"]["pending_figures"], pair["diagram_pending"])
        self.assertEqual(evidence["diagram_generation"]["source_versions"], pair["sources"])
        self.assertEqual(evidence["draft_quality"]["quality_issue_count"], 7)
        self.assertIn("presentation_quality_warning", evidence["draft_quality"]["quality_issue_codes"])
        self.assertEqual(evidence["business_approval"], "blocked")
        self.assertEqual(evidence["slides"], len(evidence["presentation_plan"]["pages"]))
        self.assertTrue(any(page["type"] == "pending" for page in evidence["presentation_plan"]["pages"]))
        with ZipFile(Path(self.storage.name) / result["path"]) as archive:
            self.assertIsNone(archive.testzip())
            slides = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
            self.assertEqual(len(slides), evidence["slides"])
            for name in (name for name in archive.namelist() if name.endswith(".xml")):
                ElementTree.fromstring(archive.read(name))
            visible = "".join(archive.read(name).decode("utf-8") for name in slides)
            self.assertIn("图表待补", visible)
            self.assertIn("质量提示", visible)
            self.assertIn("篇幅尚未达到要求", visible)
            self.assertTrue(all(b"<p:pic>" not in archive.read(name) for name in slides if name != "ppt/slides/slide1.xml"))
            notes = "".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                            if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml"))
            self.assertIn("technical-solution:P1", notes)
            self.assertIn("feasibility:P1", notes)
            self.assertNotIn("technical-solution:PEND_DIAGRAM_01_FIGURE", notes)
        self.quality = json.loads((Path(self.storage.name) / result["path"]).with_suffix(".manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(_valid_manifest(self.quality, pair))
        for changed in ({"missing_source_refs": ["technical-solution:UNKNOWN"]},
                        {"diagram_generation": {**self.quality["diagram_generation"], "source_versions": []}},
                        {"quality_gate": {"status": "pass"}},
                        {"slides": 5, "layout_inventory": {"cover": 1, "panorama": 1, "architecture": 1, "workflow": 1, "feasibility": 1}},
                        {"draft_quality": {**self.quality["draft_quality"], "quality_issue_count": 0}}):
            self.assertFalse(_valid_manifest({**self.quality, **changed}, pair))

    def test_ppt_own_quality_finding_adds_visible_warning_without_source_report_findings(self):
        pair = warning_pair()
        pair["diagram_pending"] = []
        pair["draft_quality"] = {"reports": []}
        result = render_presentation_draft(SimpleNamespace(pk=uuid.uuid4(), title="PPT自身质量提示"), pair)
        evidence = result["render_evidence"]
        self.assertEqual(evidence["quality_gate"]["status"], "fail")
        self.assertEqual(evidence["draft_quality"]["quality_issue_codes"], ["presentation_quality_warning"])
        self.assertEqual(evidence["draft_quality"]["presentation_quality_reasons"], ["visual_assets_missing"])
        with ZipFile(Path(self.storage.name) / result["path"]) as archive:
            visible = "".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                              if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            self.assertIn("汇报PPT存在图文或布局质量提示", visible)
            self.assertIn("图表待补", visible)

    def test_ppt_copy_quality_is_warning_in_draft_and_keeps_original_source_text(self):
        pair = warning_pair()
        pair["diagram_pending"] = []
        pair["draft_quality"] = {"reports": []}
        text = "内容来自平台当前报告版本，不继承正式业务批准"
        pair["blocks"][1]["text"] = text
        result = render_presentation_draft(SimpleNamespace(pk=uuid.uuid4(), title="文案待核对"), pair)
        evidence = result["render_evidence"]
        self.assertEqual(evidence["quality_gate"]["status"], "fail")
        self.assertIn("copy_review_required", evidence["draft_quality"]["presentation_quality_reasons"])
        with ZipFile(Path(self.storage.name) / result["path"]) as archive:
            visible = "".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                              if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            self.assertIn(text, visible)
            self.assertIn("汇报PPT存在图文或布局质量提示", visible)

    def test_runtime_without_explicit_draft_mode_rejects_quality_downgrade(self):
        source = Path(self.storage.name) / "pair.json"
        source.write_text(json.dumps({"title": "严格路径", **warning_pair()}), encoding="utf-8")
        result = subprocess.run([str(self.runtime), "-B", str(SCRIPT), str(source), str(source.with_suffix(".pptx"))],
                                capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"presentation quality gate failed", result.stderr)

    def test_draft_mode_still_rejects_duplicate_refs_and_missing_figure_bytes(self):
        for change in ("duplicate", "missing_figure"):
            with self.subTest(change=change):
                pair = warning_pair()
                if change == "duplicate":
                    pair["blocks"].append(dict(pair["blocks"][0]))
                else:
                    pair["blocks"].append({"ref": "technical-solution:FIG", "type": "figure", "caption": "架构",
                                           "asset_path": str(Path(self.storage.name) / "missing.png")})
                source = Path(self.storage.name) / "invalid.json"
                source.write_text(json.dumps({"title": "来源校验", **pair, "draft_mode": True}), encoding="utf-8")
                result = subprocess.run([str(self.runtime), "-B", str(SCRIPT), str(source), str(source.with_suffix(".pptx"))],
                                        capture_output=True, timeout=60)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"invalid slide source", result.stderr)
