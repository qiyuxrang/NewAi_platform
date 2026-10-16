import copy
import hashlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from portal.product_diagrams import add_structural_blocks, apply_diagram_layout


class DiagramLayoutTests(SimpleTestCase):
    def test_explanation_precedes_atomic_figure_and_retains_evidence(self):
        blocks = []
        add_structural_blocks(blocks, "technical-solution", ["S1"], ["R1"], diagram_titles=["流程待确认"])
        self.assertEqual([block["type"] for block in blocks], ["heading", "paragraph", "figure"])
        self.assertTrue(blocks[1]["id"].endswith("_NOTE"))
        self.assertEqual(blocks[1]["source_ids"], blocks[2]["source_ids"])
        self.assertEqual(blocks[1]["text"], blocks[2]["alt"])

    def test_verified_units_preserve_body_sources_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = {"blocks": [{"id": "BODY", "type": "paragraph", "text": "有效正文待确认"},
                {"id": "D1", "type": "figure", "path": "figure.png", "caption": "流程待确认",
                 "alt": "分支条件待确认", "source_ids": ["S1"], "requirement_ids": [], "width_mm": 145}]}
            panels = []
            for number in (1, 2):
                name = "figure.png" if number == 1 else "figure-unit-2.png"
                data = f"synthetic panel {number}".encode()
                (root / name).write_bytes(data)
                panels.append({"index": number, "total": 2, "path": name,
                    "imageSha256": hashlib.sha256(data).hexdigest(), "width_mm": 95, "min_font_pt": 13.5})
            for version in ("word-readable-v1", "word-readable-v2", "word-readable-v3"):
                evidence = {"figures": [{"figure_id": "D1", "imageSha256": panels[0]["imageSha256"],
                    "layout": {"version": version, "panels": panels}}]}
                with self.subTest(version=version):
                    records = apply_diagram_layout(document, evidence, root)
                    self.assertEqual(len(records), 2)
                    self.assertEqual(document["blocks"][0]["text"], "有效正文待确认")
                    self.assertEqual(document["blocks"][2]["id"], "D1_PANEL_02")
                    self.assertEqual(document["blocks"][2]["source_ids"], ["S1"])
                    self.assertIn("待确认", document["blocks"][2]["caption"])
                    before = copy.deepcopy(document)
                    apply_diagram_layout(document, evidence, root)
                    self.assertEqual(document, before)
                    for field, value in (("min_font_pt", 10), ("width_mm", 146), ("path", "../foreign.png"),
                                         ("imageSha256", "0" * 64), ("index", 1), ("total", 3)):
                        invalid = copy.deepcopy(evidence)
                        invalid["figures"][0]["layout"]["panels"][1][field] = value
                        with self.subTest(field=field), self.assertRaises(ValueError):
                            apply_diagram_layout(document, invalid, root)
                        self.assertEqual(document, before)
            invalid = copy.deepcopy(evidence)
            invalid["figures"][0]["layout"]["version"] = "word-readable-v4"
            with self.assertRaises(ValueError):
                apply_diagram_layout(document, invalid, root)
            data = b"synthetic panel 3"
            (root / "figure-unit-3.png").write_bytes(data)
            invalid = copy.deepcopy(evidence)
            invalid["figures"][0]["layout"]["panels"].append({**panels[1], "index": 3,
                "path": "figure-unit-3.png", "imageSha256": hashlib.sha256(data).hexdigest()})
            for panel in invalid["figures"][0]["layout"]["panels"]:
                panel["total"] = 3
            with self.assertRaises(ValueError):
                apply_diagram_layout(document, invalid, root)
            self.assertEqual(document, before)
