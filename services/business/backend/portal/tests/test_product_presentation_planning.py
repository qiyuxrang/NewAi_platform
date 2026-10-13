"""Real editable exports, deterministic style selection and readable source views."""
import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from PIL import Image
from portal.product_presentation import _valid_manifest, render_presentation_draft


def planning_pair(image):
    families = ("technical-solution", "feasibility")
    blocks = []
    titles = ("背景与需求", "架构与配置", "方案比较", "实施安排", "风险与对策", "结论与建议")
    for family in families:
        for index, title in enumerate(titles):
            blocks.append({"ref": f"{family}:H{index}", "type": "heading", "level": 1, "text": title})
            for number in range(3):
                blocks.append({"ref": f"{family}:P{index}_{number}", "type": "paragraph",
                    "text": f"合成验收条目{index + 1}。设备数量依据输入清单，实施窗口待确认；预算未落实时不得补造金额或收益。"})
        blocks.append({"ref": family + ":F1", "type": "figure", "caption": "合成验收原图", "asset_path": str(image),
            "presentation_image_evidence": {"width_mm": 145, "min_font_pt": 15}})
    return {"approval_inherited": False, "sha256": "c" * 64, "input_hash": "d" * 64, "blueprint_hash": "e" * 64,
        "sources": [{"family": family, "id": family, "version": 2, "sha256": "a" * 64} for family in families],
        "blocks": blocks, "pending": [], "diagram_pending": [], "draft_quality": {"reports": []}}


class PresentationPlanningTests(SimpleTestCase):
    def test_explicit_purpose_mapping_and_safe_default(self):
        runtime = Path(settings.PRODUCT_DOCUMENT_PYTHON)
        if not runtime.is_absolute():
            runtime = settings.BASE_DIR / runtime
        def select_style(data):
            code = "import json; from portal.product_assets.simple_presentation import select_style; print(json.dumps(select_style(" + repr(data) + "),ensure_ascii=True))"
            result = subprocess.run([str(runtime), "-B", "-c", code], cwd=settings.BASE_DIR / "backend", capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(select_style({"planning_context": {"purpose": "政府立项汇报"}})[0], "government")
        self.assertEqual(select_style({"planning_context": {"purpose": "管理层投资决策"}})[0], "consulting")
        self.assertEqual(select_style({"planning_context": {"purpose": "技术评审"}})[0], "engineering")
        self.assertEqual(select_style({"planning_context": {"purpose": "深色成果演示"}})[0], "dark-tech")
        self.assertEqual(select_style({"planning_context": {"purpose": "品牌简明演示"}})[0], "minimal")
        for purpose in ("科技设备有200台", "暂无用途"):
            self.assertEqual(select_style({"planning_context": {"purpose": purpose}})[0], "business")
        self.assertEqual(select_style({"planning_context": {"style": "unknown"}})[0], "business")

    def test_six_real_styles_export_native_objects_notes_and_locked_source_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "source.png"
            Image.new("RGB", (1280, 720), "#DDEAF0").save(image)
            pair = planning_pair(image)
            layouts = []
            refs = []
            with override_settings(PRODUCT_STORAGE_ROOT=root, PRODUCT_OFFICE_RENDER_ENABLED=False):
                for style in ("business", "consulting", "government", "engineering", "dark-tech", "minimal"):
                    result = render_presentation_draft(SimpleNamespace(pk=uuid.uuid4(), title="合成验收 · 项目方案"), pair,
                        presentation_style=style, communication_goal="decision", purpose="管理层投资决策")
                    output = root / result["path"]
                    evidence = result["render_evidence"]
                    plan = evidence["presentation_plan"]
                    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
                    plan_bytes = (output.parent / "pair.plan.json").read_bytes()
                    self.assertEqual(evidence["quality_gate"]["status"], "pass")
                    self.assertEqual(plan["style"], style)
                    self.assertEqual(plan["sources"], pair["sources"])
                    self.assertEqual(plan["pair_hash"], pair["sha256"])
                    self.assertTrue(all(page["reading_window_count"] == 1 for page in plan["pages"] if page["type"] == "source-figure"))
                    self.assertEqual(hashlib.sha256(plan_bytes).hexdigest(), evidence["presentation_plan_sha256"])
                    self.assertTrue(_valid_manifest(manifest, pair))
                    self.assertFalse(_valid_manifest({**manifest, "presentation_plan": {**plan, "sources": []}}, pair))
                    layouts.append(sorted(evidence["layout_inventory"]))
                    refs.append(sorted({ref for page in plan["pages"] for ref in page["source_refs"]}))
                    with ZipFile(output) as archive:
                        self.assertIsNone(archive.testzip())
                        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                        slides = [ET.fromstring(archive.read(name)) for name in archive.namelist()
                                  if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
                        self.assertEqual(len(slides), len(plan["pages"]))
                        self.assertGreater(sum(len(slide.findall(".//p:sp", ns)) for slide in slides), len(slides))
                        if style == "consulting":
                            self.assertTrue(any(slide.find(".//a:tbl", ns) is not None for slide in slides))
                        for slide in slides:
                            for shape in slide.findall(".//p:sp", ns):
                                name = shape.find("p:nvSpPr/p:cNvPr", ns).get("name", "")
                                minimum = 1200 if name == "ppt:source" else 1800 if name == "ppt:node" else 2000
                                for font in shape.findall(".//a:rPr", ns):
                                    self.assertGreaterEqual(int(font.get("sz", "0")), minimum)
                        notes = "".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                            if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml"))
                        self.assertIn("technical-solution:P0_0", notes)
                        self.assertIn("feasibility:P0_0", notes)
                    self.assertEqual(evidence["program_checks"]["status"], "pass")
            self.assertEqual(len({tuple(value) for value in layouts}), 6)
            self.assertTrue(all(value == refs[0] for value in refs))

    def test_long_source_diagram_splits_without_shrinking_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "tall-source.png"
            Image.new("RGB", (600, 2200), "white").save(image)
            pair = planning_pair(image)
            with override_settings(PRODUCT_STORAGE_ROOT=root, PRODUCT_OFFICE_RENDER_ENABLED=False):
                result = render_presentation_draft(SimpleNamespace(pk=uuid.uuid4(), title="合成验收 · 长图"), pair)
            plan = result["render_evidence"]["presentation_plan"]
            pages = [page for page in plan["pages"] if page["type"] == "source-figure"]
            self.assertGreater(len(pages), 2)
            self.assertTrue(all(page["image_view"]["minimum_label_pt"] >= 18 for page in pages))
            with ZipFile(root / result["path"]) as archive:
                images = [archive.read(name) for name in archive.namelist() if name.startswith("ppt/media/")]
                self.assertTrue(images)
                self.assertTrue(all(blob == image.read_bytes() for blob in images))
