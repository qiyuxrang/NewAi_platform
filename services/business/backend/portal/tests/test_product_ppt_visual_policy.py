"""Evidence-selected visual requirements, without chart or connector quotas."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.test import SimpleTestCase, override_settings

from portal.product_ppt_master import (DESIGN, native_chart_export_issues, page_roster,
    render, valid_manifest, validate_planned_visuals)
from portal.product_service import ProductError
from .test_product_ppt_master_flow import source_pair


def qualitative_pair():
    pair = source_pair()
    for block in pair["blocks"]:
        if block["type"] == "paragraph":
            block["text"] = "技术路线须依据现场条件确认。实施范围以审批结果为准。实施窗口待确认，确认后才能组织切换。"
    return pair


def selected_plan(roster):
    pages = [{**roster[0], "items": [], "source_refs": [], "chart": None}]
    for page in roster[1:]:
        evidence = page["evidence"][:2]
        pages.append({**{key: value for key, value in page.items() if key != "evidence"},
            "items": [item["quote"] for item in evidence],
            "source_refs": list(dict.fromkeys(item["ref"] for item in evidence)), "chart": None})
    return pages


class PPTVisualPolicyTests(SimpleTestCase):
    def test_complete_qualitative_plan_records_honest_chart_selection_note(self):
        roster = page_roster(qualitative_pair(), "定性报告")
        requirements = validate_planned_visuals(selected_plan(roster), roster)
        self.assertEqual(requirements["planned_native_charts"], 0)
        self.assertEqual(requirements["chart_selection_note"], "本次规划未选用数值图；不代表资料绝对无数据。")

    def test_complete_plan_rejects_chart_values_inconsistent_with_bound_evidence(self):
        roster = page_roster(source_pair(), "数量报告")
        pages = selected_plan(roster)
        points = [{"label": label, "value": value, **item} for item, label, value in
            zip(roster[1]["evidence"][:2], ("甲组", "乙组"), (2, 3))]
        chart = {"title": "设备数量", "unit": "台", "categories": ["甲组", "乙组"],
            "values": [2, 3], "evidence": points, "box": [650, 190, 550, 400]}
        pages[1]["chart"] = chart
        self.assertEqual(validate_planned_visuals(pages, roster)["planned_native_charts"], 1)
        broken = copy.deepcopy(pages)
        broken[1]["chart"]["values"][0] = 99
        with self.assertRaises(ProductError):
            validate_planned_visuals(broken, roster)
        broken = copy.deepcopy(pages)
        broken[1]["chart"]["values"][0] = 99
        broken[1]["chart"]["evidence"][0]["value"] = 99
        with self.assertRaises(ProductError):
            validate_planned_visuals(broken, roster)

    def test_bypassed_callback_validation_cannot_reach_svg_calls(self):
        calls = []
        def designer(key, request, validator):
            calls.append(request["action"])
            self.assertEqual(request["action"], "presentation_plan")
            pages = [{"page": page["page"], "items": page["evidence"][:2], "chart": None}
                for page in request["pages"]]
            pages[0]["chart"] = {"title": "设备数量", "unit": "台", "points": [
                {"label": label, "value": value, **item} for item, label, value in
                zip(request["pages"][0]["evidence"][:2], ("甲组", "乙组"), (99, 3))]}
            return {"pages": pages}  # Deliberately bypass the supplied validator.
        with tempfile.TemporaryDirectory() as temporary, override_settings(PRODUCT_STORAGE_ROOT=Path(temporary)):
            with patch("portal.product_ppt_master._document_runtime") as native_export_runtime:
                with self.assertRaises(ProductError):
                    render(SimpleNamespace(pk="invalid-plan", title="数量报告"), source_pair(), designer)
                native_export_runtime.assert_not_called()
        self.assertEqual(calls, ["presentation_plan"])

    def test_complete_plan_check_runs_after_all_batches_and_before_any_svg(self):
        calls = []
        def designer(key, request, validator):
            calls.append(request["action"])
            return validator({"pages": [{"page": page["page"], "items": page["evidence"][:2], "chart": None}
                for page in request["pages"]]})
        with tempfile.TemporaryDirectory() as temporary, override_settings(PRODUCT_STORAGE_ROOT=Path(temporary)):
            with patch("portal.product_ppt_master.validate_planned_visuals", side_effect=ProductError("invalid_presentation", "invalid plan", 422)) as check:
                with self.assertRaises(ProductError):
                    render(SimpleNamespace(pk="complete-plan", title="定性报告"), qualitative_pair(), designer)
                check.assert_called_once()
        self.assertEqual(calls, ["presentation_plan"] * 6)

    def test_native_chart_export_must_match_each_page_and_total(self):
        pages = [{"chart": None}, {"chart": {"title": "有证据的比较"}}, {"chart": None}]
        correct = {"charts": 1, "per_slide": [{"charts": 0}, {"charts": 1}, {"charts": 0}]}
        self.assertEqual(native_chart_export_issues(correct, pages), [])
        for broken in ({"charts": 1, "per_slide": [{"charts": 1}, {"charts": 0}, {"charts": 0}]},
                {"charts": 0, "per_slide": [{"charts": 0}, {"charts": 0}, {"charts": 0}]},
                {"charts": 2, "per_slide": correct["per_slide"]},
                {"charts": 1, "per_slide": correct["per_slide"][:2]}):
            with self.subTest(export=broken):
                self.assertEqual(native_chart_export_issues(broken, pages), ["native_charts_plan_mismatch"])
        self.assertEqual(native_chart_export_issues({"charts": 0, "per_slide": [{"charts": 0}]}, [{"chart": None}]), [])
        self.assertEqual(native_chart_export_issues({"charts": 1, "per_slide": [{"charts": 1}]}, [{"chart": None}]), ["native_charts_plan_mismatch"])

    def test_real_qualitative_native_export_has_no_chart_or_fake_connector_quota(self):
        pair = qualitative_pair()
        calls = []
        def designer(key, request, validator):
            calls.append(request["action"])
            if request["action"] == "presentation_plan":
                return validator({"pages": [{"page": page["page"], "items": page["evidence"][:2], "chart": None}
                    for page in request["pages"]]})
            page = request["page"]
            nodes = [f'<rect x="0" y="0" width="1280" height="720" fill="{DESIGN["background"]}"/>',
                f'<text x="48" y="80" font-size="40" font-family="Microsoft YaHei">{escape(page["title"])}</text>']
            for index, item in enumerate(page["items"]):
                nodes.append(f'<text x="48" y="{160+index*60}" font-size="28" font-family="Microsoft YaHei">{escape(item)}</text>')
            if page["page"] in {1, 2, 18}:
                nodes.append('<image href="asset:logo" x="48" y="600" width="160" height="40"/>')
            return validator({"svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'+''.join(nodes)+'</svg>'})
        with tempfile.TemporaryDirectory() as temporary, override_settings(PRODUCT_STORAGE_ROOT=Path(temporary), PRODUCT_OFFICE_RENDER_ENABLED=False):
            result = render(SimpleNamespace(pk="qualitative-native", title="定性报告"), pair, designer)
            evidence = result["render_evidence"]
            self.assertEqual(evidence["slides"], 18)
            self.assertEqual(evidence["native_charts"], 0)
            self.assertTrue(all(slide["charts"] == 0 for slide in evidence["native_export"]["per_slide"]))
            self.assertEqual(evidence["planned_native_charts"], 0)
            self.assertEqual(evidence["native_connectors"], 0)
            self.assertEqual(evidence["visual_asset_count"], 3)
            self.assertEqual(evidence["quality_gate"], {"status": "pass", "issues": []})
            self.assertTrue(valid_manifest(evidence, pair))
            tampered = copy.deepcopy(evidence)
            tampered["native_export"]["per_slide"][1]["charts"] = 1
            self.assertFalse(valid_manifest(tampered, pair))
            self.assertEqual(calls[:6], ["presentation_plan"] * 6)
            self.assertEqual(calls[6:], ["presentation_slide"] * 18)
            self.assertEqual(evidence["business_approval"], "blocked")
            self.assertEqual(evidence["visual_review"], "not_run")
