import hashlib
import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from portal.product_three_drafts import _rendered_result_current


class PublishedResumeAssetTests(SimpleTestCase):
    def test_corrupt_diagram_or_preview_invalidates_completed_render_step(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(PRODUCT_STORAGE_ROOT=Path(directory)):
            root = Path(directory)
            def asset(name, value):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)
                return {"path": name, "sha256": hashlib.sha256(value).hexdigest()}
            output = asset("published/draft.docx", b"docx")
            image = asset("published/diagrams/one.png", b"diagram")
            preview = asset("published/preview/page-001.png", b"page")
            content = asset("published/content.json", json.dumps({"blocks": [
                {"id": "FIG1", "type": "figure", "path": "diagrams/one.png"}]}).encode())
            result = {**output, "content_path": content["path"], "content_sha256": content["sha256"],
                      "render_evidence": {"diagram_generation": {"figures": [
                          {"id": "FIG1", "image_sha256": image["sha256"]}]},
                          "word_field_cache": {"preview": {"pages": [preview]}}}}
            self.assertTrue(_rendered_result_current(result))
            (root / image["path"]).unlink()
            self.assertFalse(_rendered_result_current(result))
            asset(image["path"], b"diagram")
            (root / preview["path"]).write_bytes(b"tampered")
            self.assertFalse(_rendered_result_current(result))
