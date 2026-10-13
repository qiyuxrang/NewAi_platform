import copy
import hashlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from portal.product_diagrams import apply_diagram_layout


class DiagramLayoutTests(SimpleTestCase):
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
            evidence = {"figures": [{"figure_id": "D1", "imageSha256": panels[0]["imageSha256"],
                "layout": {"version": "word-readable-v1", "panels": panels}}]}
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
                                 ("imageSha256", "0" * 64)):
                invalid = copy.deepcopy(evidence)
                invalid["figures"][0]["layout"]["panels"][1][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    apply_diagram_layout(document, invalid, root)
                self.assertEqual(document, before)
