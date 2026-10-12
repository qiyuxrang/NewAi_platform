import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
import unittest

from django.core.management import call_command
from django.db import connection, connections, transaction
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from portal.models import Module, Role, User
from portal.product_models import DocumentApproval, DocumentTask
from portal.product_service import ProductError, append_revision, approval_authorization, digest, task_for
from portal.product_worker import ExecutionError, _analysis_progress, _model, claim_task, execute_claim

from .base import PortalTestCase


class SQLiteTaskWriteReservationTests(unittest.TestCase):
    """Use a temporary migrated SQLite file to exercise independent connections."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temporary = TemporaryDirectory(prefix="product-task-lock-")
        cls.template = Path(cls.temporary.name) / "template.sqlite3"
        cls.database = deepcopy(connections["default"].settings_dict)
        cls.database.update(ENGINE="django.db.backends.sqlite3", NAME=str(cls.template))
        cls.database["OPTIONS"] = {"timeout": 0.8, "transaction_mode": "DEFERRED"}
        original = connections["default"]
        isolated = DatabaseWrapper(deepcopy(cls.database), "default")
        connections["default"] = isolated
        try:
            call_command("migrate", verbosity=0, interactive=False)
        except BaseException:
            cls.temporary.cleanup()
            raise
        finally:
            isolated.close()
            connections["default"] = original

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.path = Path(self.temporary.name) / (self._testMethodName + ".sqlite3")
        shutil.copyfile(self.template, self.path)
        self.config = deepcopy(self.database)
        self.config["NAME"] = str(self.path)
        self.original = connections["default"]
        self.connection = DatabaseWrapper(deepcopy(self.config), "default")
        connections["default"] = self.connection
        self.addCleanup(self.restore_connection)

        module = Module.objects.create(code="product", name="产品", enabled=True)
        role = Role.objects.create(code="product-test", name="产品测试")
        role.modules.add(module)
        self.owner = User.objects.create_user("sqlite-task-owner", password="test", must_change_password=False)
        self.owner.roles.add(role)
        self.task = DocumentTask.objects.create(
            owner=self.owner, title="SQLite锁测试", idempotency_key="sqlite-task-lock",
            payload_hash=digest({}), state="DRAFT",
        )

    def restore_connection(self):
        self.connection.close()
        connections["default"] = self.original

    def test_write_task_reserves_sqlite_before_authorization_reads(self):
        writer = sqlite3.connect(self.path, timeout=0.8, isolation_level=None)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute('UPDATE "portal_documenttask" SET "version" = "version" WHERE "id" = ?', (str(self.task.pk),))
        self.addCleanup(writer.close)
        entered = Event()
        statements = []

        def authorize_on_second_connection():
            worker_connection = DatabaseWrapper(deepcopy(self.config), "default")
            connections["default"] = worker_connection

            def observe(execute, sql, params, many, context):
                if sql.lstrip().upper().startswith(("SELECT", "UPDATE")):
                    statements.append(sql)
                    if len(statements) == 1:
                        entered.set()
                return execute(sql, params, many, context)

            try:
                with worker_connection.execute_wrapper(observe), transaction.atomic():
                    return task_for(self.owner, self.task.pk, write=True)
            finally:
                worker_connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(authorize_on_second_connection)
            try:
                if not entered.wait(2):
                    future.result(timeout=0)
                    self.fail("task_for did not issue a database read or write")
                with self.assertRaises(FutureTimeout):
                    future.result(timeout=0.12)
            finally:
                writer.rollback()
            task = future.result(timeout=2)

        self.assertTrue(statements[0].lstrip().upper().startswith('UPDATE "PORTAL_DOCUMENTTASK"'), statements)
        self.assertEqual(task.pk, self.task.pk)
        self.task.refresh_from_db()
        self.assertEqual(self.task.version, 1)


@override_settings(
    PRODUCT_P1_ENABLED=True,
    PRODUCT_MODEL_CALLS_ALLOWED=True,
    PRODUCT_COST_POLICY={
        "approval_ref": "isolated-test-only",
        "currency": "TEST",
        "max_task_cost": "100",
        "route_cost_caps": {"product_writing": "1"},
    },
)
class ProductWorkerTransactionTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("transaction-writer", "product")
        input_payload = {
            "project": "隔离事务测试",
            "requirements": "不调用外部模型",
            "items": [{"row_id": "r1", "name": "测试设备", "quantity": "1", "unit": "台"}],
            "conditions": [],
        }
        blueprint_payload = {
            "purpose": "隔离事务测试",
            "audience": "测试人员",
            "chapters": [{"id": "chapter-1", "title": "测试章节", "scope": "测试", "source_ids": ["r1"]}],
            "conditions": [],
            "missing": [],
            "conflicts": [],
            "template_version": "frozen-original-v1",
        }
        self.task = DocumentTask.objects.create(
            owner=self.owner,
            title="隔离事务测试",
            idempotency_key="product-worker-transaction-test",
            payload_hash=digest(input_payload),
            state="QUEUED",
            stage="WRITING",
            pending_action="write",
        )
        input_revision = append_revision(self.task, "input", input_payload, actor=self.owner)
        blueprint = append_revision(
            self.task, "blueprint", blueprint_payload, input_hash=input_revision.sha256, actor=self.owner
        )
        self.task.input_version = input_revision.version
        self.task.blueprint_version = blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        DocumentApproval.objects.create(
            task=self.task,
            revision=blueprint,
            actor=self.owner,
            decision="approve",
            sha256=blueprint.sha256,
            authorization=approval_authorization(self.task, self.owner),
        )

    def test_sqlite_checkpoint_write_reserves_lock_before_guard_reads(self):
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-specific lock-upgrade regression")
        task_id, fence, _ = claim_task()

        with CaptureQueriesContext(connection) as queries:
            _analysis_progress(task_id, fence, "writing_technical", "completed")

        statements = [query["sql"].upper() for query in queries.captured_queries]
        first_task_update = next(index for index, sql in enumerate(statements)
                                 if sql.startswith('UPDATE "PORTAL_DOCUMENTTASK"'))
        first_task_read = next(index for index, sql in enumerate(statements)
                               if sql.startswith('SELECT') and '"PORTAL_DOCUMENTTASK"' in sql)
        self.assertLess(first_task_update, first_task_read)

    @patch("portal.product_worker.generate_for_use")
    def test_model_request_runs_outside_database_transaction(self, model):
        task_id, fence, attempt_id = claim_task()
        transaction_depth = len(connection.atomic_blocks)

        def reply(*_args):
            self.assertEqual(len(connection.atomic_blocks), transaction_depth)
            return {"content": json.dumps({}), "prompt_tokens": 1, "completion_tokens": 1}

        model.side_effect = reply
        self.assertEqual(_model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"}), {})

    @override_settings(PRODUCT_LEASE_SECONDS=900)
    @patch("portal.product_worker.generate_for_use")
    def test_long_model_call_retains_lease_and_cannot_be_reclaimed(self, model):
        started = timezone.now()
        clock = [started]
        with patch("portal.product_worker.timezone.now", side_effect=lambda: clock[0]):
            task_id, fence, attempt_id = claim_task()

            def reply(*_args):
                clock[0] = started + timedelta(seconds=300)
                self.assertIsNone(claim_task())
                return {"content": json.dumps({}), "prompt_tokens": 1, "completion_tokens": 1}

            model.side_effect = reply
            self.assertEqual(_model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"}), {})
        self.task.refresh_from_db()
        self.assertEqual(self.task.fence, fence)
        self.assertEqual(self.task.checkpoint["calls"][-1]["status"], "response_received")

    @patch("portal.product_worker.generate_for_use")
    def test_invalid_json_retries_once_and_counts_each_physical_call(self, model):
        reply = {"prompt_tokens": 1, "completion_tokens": 1}
        model.side_effect = [{**reply, "content": '{"paragraphs": ['}, {**reply, "content": '{}'}]
        task_id, fence, attempt_id = claim_task()
        self.assertEqual(_model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"}), {})
        self.assertEqual(model.call_count, 2)
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 2)
        self.assertEqual(self.task.checkpoint["calls"][0]["parse_error"], "invalid_model_output")
        self.assertIn("json_format_correction", json.loads(model.call_args.args[2][1]["content"]))

    @patch("portal.product_worker.generate_for_use")
    def test_invalid_json_retry_remains_bounded_and_preserves_call_budget(self, model):
        model.return_value = {"content": 'not json', "prompt_tokens": 1, "completion_tokens": 1}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as caught:
            _model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"})
        self.assertEqual(caught.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        model.reset_mock()
        with override_settings(PRODUCT_MAX_MODEL_CALLS=2), self.assertRaises(ExecutionError) as caught:
            _model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"})
        self.assertEqual(caught.exception.code, "model_call_limit")
        model.assert_not_called()

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch("portal.product_worker.generate_for_use")
    def test_invalid_json_correction_cannot_exceed_remaining_budget(self, model):
        model.return_value = {"content": 'not json', "prompt_tokens": 1, "completion_tokens": 1}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as caught:
            _model(task_id, fence, attempt_id, "product_writing", {"action": "chapter"})
        self.assertEqual(caught.exception.code, "model_call_limit")
        self.assertEqual(model.call_count, 1)

    @patch("portal.product_worker.generate_for_use")
    def test_missing_source_ids_and_invalid_field_types_retry_without_fabrication(self, model):
        valid = {"chapter_id": "chapter-1", "title": "测试章节", "paragraphs": ["有来源的正文"], "source_ids": ["r1"]}
        request = {"action": "chapter", "schema": {"chapter_id": "chapter-1", "title": "测试章节", "paragraphs": ["string"], "source_ids": []}}
        task_id, fence, attempt_id = claim_task()
        for bad in ({key:value for key,value in valid.items() if key != "source_ids"}, {**valid, "source_ids": "r1"}, {**valid, "extra": True}):
            with self.subTest(bad=bad):
                model.reset_mock()
                model.side_effect = [{"content":json.dumps(value), "prompt_tokens":1, "completion_tokens":1} for value in (bad, valid)]
                self.assertEqual(_model(task_id, fence, attempt_id, "product_writing", request), valid)
                self.assertEqual(model.call_count, 2)
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempts.get(pk=attempt_id).model_calls, 6)

    @patch("portal.product_worker.generate_for_use")
    def test_persistent_missing_source_ids_is_output_error_and_saves_no_chapter(self, model):
        from portal.product_models import DocumentRevision
        model.return_value = {"content":json.dumps({"chapter_id":"chapter-1", "title":"测试章节", "paragraphs":["正文"]}), "prompt_tokens":1, "completion_tokens":1}
        task_id, fence, attempt_id = claim_task()
        with self.assertRaises(ExecutionError) as caught:
            _model(task_id, fence, attempt_id, "product_writing", {"action":"chapter", "schema":{"chapter_id":"chapter-1", "title":"测试章节", "paragraphs":["string"], "source_ids":[]}})
        self.assertEqual(caught.exception.code, "invalid_model_output")
        self.assertEqual(model.call_count, 2)
        self.assertFalse(DocumentRevision.objects.filter(task=self.task, kind="chapter").exists())

    @patch("portal.product_workflow.run_product_workflow")
    def test_web_search_unconfigured_waits_for_input_and_fails_running_knowledge(self, workflow):
        self.task.checkpoint = {"analysis_progress": {"knowledge": {"status": "running"}}}
        self.task.save(update_fields=["checkpoint"])
        task_id, fence, attempt_id = claim_task()
        workflow.side_effect = ProductError("web_search_unconfigured", "未配置联网检索。", 503)

        execute_claim(task_id, fence, attempt_id)

        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "WAITING_INPUT")
        self.assertEqual(self.task.error_code, "web_search_unconfigured")
        self.assertEqual(self.task.checkpoint["analysis_progress"]["knowledge"]["status"], "failed")
