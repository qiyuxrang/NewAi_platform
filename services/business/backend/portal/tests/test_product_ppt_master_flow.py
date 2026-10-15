"""Exercise the real native exporter through the platform's model callback boundary."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import escape
from zipfile import ZipFile
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_ppt_master import (DESIGN, POLICY, page_roster, validate_exported_text,
    validate_selection, validate_svg)
from portal.product_presentation import _valid_manifest, render_presentation_draft
from portal.product_service import ProductError
from portal.product_three_drafts import _rendered_result_current
from portal.product_steps import run_step
from portal.product_worker import _model
from .base import PortalTestCase
from . import test_product_review_output_retry as model_fixture


def source_pair():
    blocks = []
    for family in ("technical-solution", "feasibility"):
        for chapter in range(8):
            blocks.append({"ref": f"{family}:H{chapter}", "type": "heading", "level": 1, "text": f"专题{chapter+1}设计依据"})
            blocks.append({"ref": f"{family}:P{chapter}", "type": "paragraph", "text":
                f"专题{chapter+1}甲组设备数量为2台。专题{chapter+1}乙组设备数量为3台。实施窗口待确认，确认后才能组织切换。"})
    return {"approval_inherited": False, "sha256": "a"*64, "input_hash": "b"*64, "blueprint_hash": "c"*64,
        "sources": [{"family": family, "id": family, "version": 1, "sha256": "d"*64} for family in ("technical-solution", "feasibility")],
        "blocks": blocks, "pending": [], "diagram_pending": [], "draft_quality": {"reports": []}}


class PPTMasterFlowTests(SimpleTestCase):
    def test_source_selection_and_svg_reject_fabrication_and_hidden_body(self):
        pages = page_roster(source_pair(), "合成验收项目")
        self.assertGreaterEqual(len(pages), 17)
        page = pages[1]
        selected = {"pages": [{"page": page["page"], "items": page["evidence"][:2], "chart": None}]}
        self.assertEqual(validate_selection(selected, [page]), selected)
        fabricated = copy.deepcopy(selected)
        fabricated["pages"][0]["items"][0]["quote"] = "投资收益已经实现。"
        with self.assertRaises(ProductError):
            validate_selection(fabricated, [page])
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text x="48" y="80" font-size="40" font-family="Microsoft YaHei">合成验收项目</text></svg>'
        cover = {"page": 1, "title": "合成验收项目", "items": []}
        self.assertEqual(validate_svg({"svg": svg}, cover, DESIGN), {"svg": svg})
        for bad in (svg.replace('font-size="40"', 'font-size="12"'),
                    svg.replace('font-size="40"', 'font-size="16" data-role="source"'),
                    svg.replace('</svg>', '<script>alert(1)</script></svg>'),
                    svg.replace('</svg>', '<image href="https://example.com/a.png"/></svg>'),
                    svg.replace('>合成验收项目</text>', '><tspan font-size="0">合成验收项目</tspan></text>')):
            with self.assertRaises(ProductError):
                validate_svg({"svg": bad}, cover, DESIGN)

    def test_svg_rejects_hidden_text_containers_fill_and_nested_canvas(self):
        cover = {"page": 1, "title": "合成验收项目", "items": []}
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text x="48" y="80" font-size="40" font-family="Microsoft YaHei">合成验收项目</text></svg>'
        hidden = [
            svg.replace('</svg>', '<defs><text x="48" y="120" font-size="28" font-family="Microsoft YaHei">合成验收项目</text></defs></svg>'),
            svg.replace('</svg>', '<marker id="m"><text x="48" y="120" font-size="28" font-family="Microsoft YaHei">合成验收项目</text></marker></svg>'),
            svg.replace('<text ', '<text fill="none" ', 1),
            svg.replace('<text ', '<text fill="transparent" ', 1),
            svg.replace('<text ', f'<text fill="{DESIGN["background"]}" ', 1),
            svg.replace('<text ', f'<g fill="{DESIGN["background"]}"><text ', 1).replace('</text>', '</text></g>', 1),
            svg.replace('</svg>', '<svg viewBox="0 0 1280 720"/></svg>'),
        ]
        for bad in hidden:
            with self.subTest(svg=bad[-100:]), self.assertRaises(ProductError):
                validate_svg({"svg": bad}, cover, DESIGN)

    def test_svg_rejects_tspan_y_and_dy_outside_safe_area(self):
        cover = {"page": 1, "title": "合成验收项目", "items": []}
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text x="48" y="80" font-size="40" font-family="Microsoft YaHei">合成验收项目</text></svg>'
        for attr in ('y="700"', 'dy="700"'):
            bad = svg.replace('>合成验收项目</text>', f'><tspan {attr}>合成验收项目</tspan></text>')
            with self.subTest(attr=attr), self.assertRaises(ProductError):
                validate_svg({"svg": bad}, cover, DESIGN)

    def test_svg_rejects_long_body_outside_tspan_width_measurement(self):
        body = "项目正文内容" * 17 + "项目正文"  # 106 CJK characters
        cover = {"page": 1, "title": "合成验收项目", "items": [body]}
        prefix = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text x="48" y="80" font-size="40" font-family="Microsoft YaHei">合成验收项目</text>'
        for fragment in (f'{body}<tspan x="48">。</tspan>', f'<tspan x="48">。</tspan>{body}'):
            svg = prefix + f'<text x="48" y="180" font-size="28" font-family="Microsoft YaHei">{fragment}</text></svg>'
            with self.subTest(fragment_start=fragment[:20]), self.assertRaises(ProductError):
                validate_svg({"svg": svg}, cover, DESIGN)

    def test_chart_requires_correct_object_quantity_and_rejects_signed_values_as_positive(self):
        quotes = ("甲组设备2台。", "乙组设备3台。")
        page = {"page": 2, "title": "设备数量", "type": "content",
            "evidence": [{"ref": f"equipment:P{i}", "quote": quote} for i, quote in enumerate(quotes, 1)]}
        points = [{"label": "甲组设备", "value": 2, "ref": "equipment:P1", "quote": quotes[0]},
            {"label": "乙组设备", "value": 3, "ref": "equipment:P2", "quote": quotes[1]}]
        selection = {"pages": [{"page": 2, "items": page["evidence"],
            "chart": {"title": "设备数量", "unit": "台", "points": points}}]}
        self.assertEqual(validate_selection(selection, [page]), selection)
        swapped = copy.deepcopy(selection)
        swapped["pages"][0]["chart"]["points"][0]["value"] = 3
        swapped["pages"][0]["chart"]["points"][1]["value"] = 2
        with self.assertRaises(ProductError):
            validate_selection(swapped, [page])

        for sign in ("-", "−"):
            signed_quotes = (f"甲组收益为{sign}2万元。", f"乙组收益为{sign}3万元。")
            signed_page = {"page": 2, "title": "收益", "type": "content",
                "evidence": [{"ref": f"finance:P{i}", "quote": quote} for i, quote in enumerate(signed_quotes, 1)]}
            positive_chart = {"pages": [{"page": 2, "items": signed_page["evidence"], "chart": {
                "title": "收益对比", "unit": "万元", "points": [
                    {"label": "甲组收益", "value": 2, "ref": "finance:P1", "quote": signed_quotes[0]},
                    {"label": "乙组收益", "value": 3, "ref": "finance:P2", "quote": signed_quotes[1]}]}}]}
            with self.subTest(sign=sign), self.assertRaises(ProductError):
                validate_selection(positive_chart, [signed_page])

    def test_exported_text_requires_title_and_body_in_slide_xml(self):
        page = {"page": 1, "title": "封面标题", "items": ["正文完整句子"]}
        ns = {
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        }
        def write_minimal_pptx(path, texts):
            runs = "".join(f"<a:p><a:r><a:t>{escape(text)}</a:t></a:r></a:p>" for text in texts)
            slide = (f'<p:sld xmlns:p="{ns["p"]}" xmlns:a="{ns["a"]}"><p:cSld>'
                f'<p:spTree>{runs}</p:spTree></p:cSld></p:sld>')
            with ZipFile(path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", slide)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "minimal.pptx"
            write_minimal_pptx(output, [page["title"]])
            with self.assertRaisesRegex(ValueError, "native_export_missing_text"):
                validate_exported_text(output, [page])
            write_minimal_pptx(output, [page["title"], *page["items"]])
            self.assertIsNone(validate_exported_text(output, [page]))

    def test_real_18_page_native_export_is_bound_and_download_cache_valid(self):
        pair = source_pair()
        calls = []
        def designer(key, request, validator):
            calls.append((key, request["action"]))
            if request["action"] == "presentation_plan":
                pages = []
                for page in request["pages"]:
                    chart = None
                    if page["page"] == 2:
                        points = [{"label": label, "value": value, **item} for item, label, value in
                            zip(page["evidence"][:2], ("甲组", "乙组"), (2, 3))]
                        chart = {"title": "合成设备数量", "unit": "台", "points": points}
                    pages.append({"page": page["page"], "items": page["evidence"][:2], "chart": chart})
                result = {"pages": pages}
            else:
                page = request["page"]
                # Synthetic boundary fixture only; production pages are authored
                # serially by the model, never by this test layout.
                nodes = [f'<rect x="0" y="0" width="1280" height="720" fill="{DESIGN["background"]}"/>',
                         f'<text x="48" y="80" font-size="40" font-family="Microsoft YaHei">{escape(page["title"])}</text>']
                for index, item in enumerate(page["items"]):
                    nodes.append(f'<text x="48" y="{160+index*60}" font-size="28" font-family="Microsoft YaHei">{escape(item)}</text>')
                nodes += [f'<line x1="48" y1="{400+i*12}" x2="500" y2="{400+i*12}" stroke="{DESIGN["accent"]}"/>' for i in range(2)]
                if page["page"] in {1, 2, 18}:
                    nodes.append('<image href="asset:logo" x="48" y="600" width="160" height="40"/>')
                result = {"svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'+''.join(nodes)+'</svg>'}
            return validator(result)
        with tempfile.TemporaryDirectory() as temporary, override_settings(PRODUCT_STORAGE_ROOT=Path(temporary), PRODUCT_OFFICE_RENDER_ENABLED=False):
            result = render_presentation_draft(SimpleNamespace(pk="ppt-fixture", title="合成验收项目"), pair, designer=designer)
            target = Path(temporary) / result["path"]
            evidence = result["render_evidence"]
            self.assertEqual(evidence["slides"], 18)
            self.assertEqual(evidence["native_charts"], 1)
            self.assertGreaterEqual(evidence["native_connectors"], 8)
            self.assertEqual(evidence["visual_asset_count"], 3)
            self.assertEqual(evidence["quality_gate"]["status"], "pass")
            self.assertTrue(_rendered_result_current(result))
            self.assertTrue(_valid_manifest(evidence, pair))
            self.assertFalse(_valid_manifest(evidence, {**pair, "sha256": "f"*64}))
            self.assertEqual(evidence["presentation_plan"]["policy"], POLICY)
            self.assertEqual(evidence["visual_review"], "not_run")
            self.assertEqual(evidence["business_approval"], "blocked")
            first_svg = next(i for i, (_, action) in enumerate(calls) if action == "presentation_slide")
            self.assertTrue(all(action == "presentation_plan" for _, action in calls[:first_svg]))
            self.assertEqual([key for key, action in calls if action == "presentation_slide"], [f"slide:{i}" for i in range(1, 19)])
            plan_raw = (target.parent / "pair.plan.json").read_bytes()
            self.assertEqual(hashlib.sha256(plan_raw).hexdigest(), evidence["presentation_plan_sha256"])
            with ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                self.assertTrue(any(name.startswith("ppt/charts/") for name in archive.namelist()))
                self.assertIn("technical-solution:P0", archive.read("ppt/notesSlides/notesSlide2.xml").decode())
                self.assertTrue(any("feasibility:P" in archive.read(name).decode() for name in archive.namelist() if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")))


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True, PRODUCT_MAX_MODEL_CALLS=10,
    PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST", "max_task_cost": "100", "route_cost_caps": {"product_writing": "1"}})
class PPTMasterModelBoundaryTests(PortalTestCase):
    setUp = model_fixture.ProductReviewOutputRetryTests.setUp
    claimed = model_fixture.ProductReviewOutputRetryTests.claimed

    def test_one_bounded_correction_records_real_calls_and_resume_reuses_page(self):
        task_id, fence, attempt_id = self.claimed()
        page = {"title": "合成验收项目", "items": [], "page": 1}
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><text x="48" y="80" font-size="40" font-family="Microsoft YaHei">合成验收项目</text></svg>'
        payload = {"action": "presentation_slide", "schema": {"svg": "SVG"}, "page": page}
        validator = lambda result: validate_svg(result, page, DESIGN)
        with patch("portal.product_worker.generate_for_use") as model:
            model.side_effect = [{"content": json.dumps({"svg": svg.replace('font-size="40"', 'font-size="12"')})}, {"content": json.dumps({"svg": svg})}]
            operation = lambda: _model(task_id, fence, attempt_id, "product_writing", payload, output_validator=validator)
            first = run_step(task_id, fence, "presentation:slide:1", payload, operation)
            resumed = run_step(task_id, fence, "presentation:slide:1", payload, operation)
            self.assertEqual(first, resumed)
            self.assertEqual(model.call_count, 2)
            correction = json.loads(model.call_args_list[1].args[2][1]["content"])
            self.assertIn("文字字号或安全区不合格", correction["presentation_correction"])
        self.task.refresh_from_db()
        attempt = self.task.attempts.get(pk=attempt_id)
        self.assertEqual(attempt.model_calls, 2)
        self.assertEqual(self.task.checkpoint["calls"][0]["validation_stage"], "output_contract")
        self.assertEqual(self.task.steps.get(key="presentation:slide:1").status, "completed")
