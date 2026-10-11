from unittest.mock import patch
import json
from pathlib import Path
import sqlite3
import tempfile

from django.db import OperationalError

from portal.product_models import DocumentTask
from .base import PortalTestCase
from . import test_product_api as fixture


class ProductFailureDiagnosticTests(PortalTestCase):
    setUp = fixture.ProductApiTests.setUp
    input_payload = fixture.ProductApiTests.input_payload
    create_task = fixture.ProductApiTests.create_task

    def test_sqlite_lock_diagnostic_uses_real_error_code_without_sql_or_exception_text(self):
        from portal.product_worker import _failure_diagnostic
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'isolated.sqlite3'
            first, second = sqlite3.connect(path, timeout=0), sqlite3.connect(path, timeout=0)
            try:
                first.execute('CREATE TABLE synthetic_counter (value INTEGER)')
                first.execute('INSERT INTO synthetic_counter VALUES (0)')
                first.commit()
                first.execute('BEGIN IMMEDIATE')
                try:
                    second.execute('UPDATE synthetic_counter SET value=1')
                except sqlite3.OperationalError as original:
                    try:
                        raise OperationalError('PRIVATE-DATABASE-MESSAGE') from original
                    except OperationalError as wrapped:
                        diagnostic = _failure_diagnostic(wrapped)
                else:
                    self.fail('A separate connection must encounter the actual write lock.')
            finally:
                first.rollback()
                first.close()
                second.close()
        self.assertEqual(diagnostic['database_error'], {'engine':'sqlite', 'name':'SQLITE_BUSY', 'code':5})
        safe = json.dumps(diagnostic)
        self.assertNotIn('PRIVATE-DATABASE-MESSAGE', safe)
        self.assertNotIn('synthetic_counter', safe)
        self.assertNotIn(directory, safe)
        self.assertLessEqual(len(diagnostic['frames']), 12)

    def failed_task(self):
        created = self.create_task()
        task = DocumentTask.objects.get(pk=created["id"])
        task.state, task.error_code = "FAILED", "invalid_model_output"
        task.checkpoint = {**task.checkpoint, "last_failure": {
            "code": task.error_code, "frames": [{"file": "private-debug-path"}],
            "provider_key": "PRIVATE-CONTRACT-SENTINEL",
            "quality_issue_count": 14,
            "quality_issues": [{"code": "unsupported_parameter", "chapter_id": "chapter-1",
                "paragraph_index": index, "claim": "保留期限" * 100, "context": "句级限定待调查确认" * 100,
                "context_truncated": False,
                "correction": "明确待确认" * 100,
                "raw_response": "PRIVATE-CONTRACT-SENTINEL"} for index in range(14)]}}
        task.save()
        return task

    def detail(self, task, client=None):
        return (client or self.owner_client).get(f"/api/product/tasks/{task.pk}/")

    def test_current_failure_reports_location_and_bounded_correction_without_internal_debug_data(self):
        task = self.failed_task()
        response = self.detail(task)
        self.assertEqual(response.status_code, 200)
        failure = response.json()["content_failure"]
        self.assertEqual(failure["quality_issue_count"], 14)
        self.assertEqual(len(failure["quality_issues"]), 10)
        first = failure["quality_issues"][0]
        self.assertEqual(first["chapter_id"], "chapter-1")
        self.assertEqual(first["paragraph_index"], 0)
        self.assertEqual(len(first["claim"]), 250)
        self.assertEqual(len(first["context"]), 250)
        self.assertTrue(first["context_truncated"])
        self.assertEqual(len(first["correction"]), 350)
        self.assertNotIn("private-debug-path", response.content.decode())
        self.assertNotIn("PRIVATE-CONTRACT-SENTINEL", response.content.decode())

    def test_recovered_or_different_failure_does_not_present_stale_content_findings(self):
        task = self.failed_task()
        for state, code in (("RUNNING", ""), ("DRAFT", ""), ("FAILED", "gateway_unavailable")):
            with self.subTest(state=state, code=code):
                task.state, task.error_code = state, code
                task.save()
                self.assertIsNone(self.detail(task).json()["content_failure"])

    def test_foreign_reader_and_revoked_sources_cannot_read_failure_claims(self):
        task = self.failed_task()
        self.assertEqual(self.detail(task, self.other_client).status_code, 404)
        with patch("portal.product_api.input_authorized", return_value=False):
            response = self.detail(task)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("quality_issues", response.json())

    def test_generic_transport_failure_exposes_code_only(self):
        task = self.failed_task()
        task.error_code = "gateway_unavailable"
        task.checkpoint["last_failure"] = {"code": task.error_code, "frames": [{"file": "private-debug-path"}]}
        task.save()
        self.assertEqual(self.detail(task).json()["content_failure"], {
            "code": "gateway_unavailable", "quality_issues": [], "quality_issue_count": 0})

    def test_diagram_failure_preserves_bounded_figure_and_field_location(self):
        task = self.failed_task()
        task.error_code = "diagram_generation_invalid"
        task.checkpoint["last_failure"] = {"code": task.error_code, "quality_issues": [
            {"code": "unsupported_parameter", "figure_id": "F" * 130,
             "field": "title" * 20, "claim": "无依据的投资预算", "visible_text": "private raw field"}]}
        task.save()
        failure = self.detail(task).json()["content_failure"]
        self.assertEqual(len(failure["quality_issues"][0]["figure_id"]), 100)
        self.assertEqual(len(failure["quality_issues"][0]["field"]), 40)
        self.assertNotIn("visible_text", failure["quality_issues"][0])
