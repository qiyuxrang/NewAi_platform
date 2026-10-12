import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.product_documents import DocumentError, _diagram_failure_diagnostic, preflight_document_rendering, render_draft, content_document
from portal.tests import test_product_documents as document_fixtures
from portal.product_render_cache import StageCache, canonical_hash, confined, file_hash


class DocumentStageCacheTests(SimpleTestCase):
    def test_stage_recovery_is_hash_bound_and_does_not_require_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = ["draft.docx", "draft.quality.json"]
            for name in files:
                (root / name).write_bytes(name.encode())
            cache = StageCache(root, "input-runtime-binding")
            cache.save("normalized", files, {"layout": {"normalized": True}})
            (root / "draft.docx").write_bytes(b"interrupted Office output")
            self.assertEqual(cache.load("normalized", files), {"layout": {"normalized": True}})
            self.assertEqual((root / "draft.docx").read_bytes(), b"draft.docx")
            self.assertIsNone(StageCache(root, "changed-input").load("normalized", files))
            snapshot = root / ".stage-cache/normalized/draft.docx"
            snapshot.write_bytes(b"tampered snapshot")
            self.assertIsNone(cache.load("normalized", files))

    def test_cache_metadata_cannot_redirect_reads_or_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for value in ["../outside", "/outside", "a/../../outside"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    confined(root, value)
            (root / "draft.docx").write_bytes(b"original")
            cache = StageCache(root, "binding")
            cache.save("assembled", ["draft.docx"], {})
            checkpoint = root / ".stage-cache/assembled/checkpoint.json"
            metadata = json.loads(checkpoint.read_bytes())
            metadata["files"] = {"../outside": "a" * 64}
            checkpoint.write_text(json.dumps(metadata))
            self.assertIsNone(cache.load("assembled", ["draft.docx"]))
            self.assertEqual((root / "draft.docx").read_bytes(), b"original")

    def test_binding_changes_with_document_or_renderer(self):
        base = {"document": {"title": "synthetic"}, "renderer": "old"}
        self.assertNotEqual(canonical_hash(base), canonical_hash({**base, "renderer": "new"}))
        self.assertNotEqual(canonical_hash(base), canonical_hash({**base, "document": {"title": "changed"}}))


class DocumentSafeDiagnosticsTests(SimpleTestCase):
    def test_preflight_rejects_missing_python_before_child_process_or_generation(self):
        with override_settings(PRODUCT_DOCUMENT_PYTHON="missing-synthetic-runtime"), patch("portal.product_documents.subprocess.run") as run:
            with self.assertRaises(DocumentError) as error:
                preflight_document_rendering()
        run.assert_not_called()
        self.assertEqual(error.exception.diagnostic, {"stage": "document_preflight", "reason": "document_python_unavailable"})

    def test_renderer_stderr_only_accepts_fixed_safe_reason(self):
        result = SimpleNamespace(returncode=2, stderr=b'{"reason":"diagram_parse_or_anchor_failed","secret":"sk-private","source":"authored text"}')
        diagnostic = _diagram_failure_diagnostic(result)
        self.assertEqual(diagnostic, {"stage": "diagram_render", "reason": "diagram_parse_or_anchor_failed", "returncode": 2})
        result.stderr = b'{"reason":"sk-private authored text"}'
        self.assertEqual(_diagram_failure_diagnostic(result)["reason"], "diagram_renderer_failed")


class ReportRenderRecoveryTests(SimpleTestCase):
    def setUp(self):
        document_fixtures.ProductDocumentTests.setUp(self)

    def test_office_failure_resumes_assembled_docx_and_keeps_published_files_immutable(self):
        from portal import product_documents
        document = content_document(self.task, self.input_revision, self.blueprint, [self.chapter])
        original = json.dumps(document, sort_keys=True)
        real_run = product_documents.subprocess.run
        assembly_calls = []

        def run(command, **kwargs):
            if len(command) > 2 and str(command[2]).endswith("artifacts.py"):
                assembly_calls.append(command)
            result = real_run(command, **kwargs)
            if len(command) > 2 and str(command[2]).endswith("artifacts.py") and result.returncode:
                self.fail(result.stderr.decode("utf-8", errors="replace")[-2000:])
            return result

        with tempfile.TemporaryDirectory() as temporary, override_settings(PRODUCT_STORAGE_ROOT=temporary), \
                patch("portal.product_documents.subprocess.run", side_effect=run), \
                patch("portal.product_documents._normalize_word_layout", wraps=product_documents._normalize_word_layout) as normalize, \
                patch("portal.product_documents._refresh_word_field_cache", side_effect=[
                    DocumentError("document_render_failed", diagnostic={"stage": "office_render", "reason": "renderer_failed"}),
                    {"status": "completed", "renderer": "synthetic", "toc_count": 1, "page_count": 1},
                ]) as refresh:
            options = {"document": document, "workspace_key": "synthetic-retry-job"}
            with self.assertRaises(DocumentError) as failure:
                render_draft(self.task, self.input_revision, self.blueprint, [self.chapter], **options)
            self.assertEqual(failure.exception.diagnostic["reason"], "renderer_failed")
            bitmap = next(Path(temporary).rglob(".bitmap-cache/*.png"))
            bitmap_time = bitmap.stat().st_mtime_ns
            resumed = render_draft(self.task, self.input_revision, self.blueprint, [self.chapter], **options)
            delivered = Path(temporary) / resumed["path"]
            original_docx = delivered.read_bytes()
            final_content = Path(temporary) / resumed["content_path"]
            self.assertEqual(file_hash(final_content), resumed["content_sha256"])
            rendered_document = json.loads(final_content.read_bytes())
            self.assertTrue(any(block["id"].startswith("DIAGRAM_") for block in rendered_document["blocks"]))
            self.assertNotIn("flowchart LR", final_content.read_text(encoding="utf-8"))
            reused = render_draft(self.task, self.input_revision, self.blueprint, [self.chapter], **options)
            self.assertEqual(len(assembly_calls), 1)
            self.assertEqual(normalize.call_count, 1)
            self.assertEqual(refresh.call_count, 2)
            self.assertTrue(reused["render_evidence"]["render_checkpoint"]["office_reused"])
            self.assertNotEqual(reused["path"], resumed["path"])
            self.assertEqual(delivered.read_bytes(), original_docx)
            self.assertEqual(bitmap.stat().st_mtime_ns, bitmap_time)
            for block in (block for block in document["blocks"] if block["type"] == "figure"):
                self.assertTrue((delivered.parent / block["path"]).is_file())
        self.assertEqual(json.dumps(document, sort_keys=True), original)

    def test_publication_snapshots_preview_assets_and_refuses_tampered_evidence(self):
        from portal.product_documents import _publish_render_snapshot
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            target = workspace / "draft.docx"
            target.write_bytes(b"synthetic docx")
            target.with_suffix(".quality.json").write_text(json.dumps({"word_field_cache": {}}))
            records = []
            for name, value in [("diagram.png", b"synthetic diagram"), ("preview.pdf", b"synthetic PDF"), ("page.png", b"synthetic page")]:
                asset = workspace / name
                asset.write_bytes(value)
                records.append({"path": asset.relative_to(root).as_posix(), "sha256": file_hash(asset)})
            evidence = {"diagram_generation": {"figures": [{"id": "D1", "image_sha256": records[0]["sha256"]}]},
                        "word_field_cache": {"status": "completed", "preview": {"pdf": records[1], "pages": [{"page": 1, **records[2]}]}}}
            document = {"blocks": [{"type": "figure", "id": "D1", "path": "diagram.png"}]}
            (workspace / "content.json").write_text(json.dumps(document))
            promoted = _publish_render_snapshot(root, workspace, self.task, "draft.docx", document, evidence)
            self.assertEqual((promoted.parent / "diagram.png").read_bytes(), b"synthetic diagram")
            preview = evidence["word_field_cache"]["preview"]
            for record in [preview["pdf"], *preview["pages"]]:
                asset = root / record["path"]
                self.assertTrue(asset.is_relative_to(promoted.parent))
                self.assertEqual(file_hash(asset), record["sha256"])
            self.assertNotIn("workspace", json.dumps(json.loads(promoted.with_suffix(".quality.json").read_bytes())))
            (workspace / "diagram.png").write_bytes(b"tampered image")
            with self.assertRaises(DocumentError) as failure:
                _publish_render_snapshot(root, workspace, self.task, "draft.docx", document, evidence)
            self.assertEqual(failure.exception.diagnostic["reason"], "snapshot_verification_failed")
