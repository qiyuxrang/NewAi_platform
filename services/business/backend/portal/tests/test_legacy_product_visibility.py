"""Visibility and migration checks use only synthetic rows in the Django test DB."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from portal.product_knowledge_api import visible
from portal.product_knowledge_models import ProductKnowledgeConversation as Conversation
from portal.product_models import DocumentRevision, DocumentSource, DocumentTask
from portal.product_service import ProductError, input_authorized
from portal.product_worker import claim_task

from .base import PortalTestCase, json_body


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=False)
class LegacyProductVisibilityTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("visibility-owner", "product")
        self.client = Client()
        self.login(self.client, self.owner)

    def create_task(self, key):
        payload = {"title": key, "input": {
            "project": key, "requirements": "Use approved sources only", "items": [],
            "background": "Synthetic visibility check", "conditions": [],
        }}
        response = self.client.post("/api/product/tasks/", json.dumps(payload),
            content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, 201, response.content)
        return DocumentTask.objects.get(pk=response.json()["id"]), payload

    def test_deleted_tasks_are_hidden_from_lists_direct_sources_workers_and_replays(self):
        active, _ = self.create_task("active-task")
        deleted, payload = self.create_task("deleted-task")
        sources = [DocumentSource.objects.create(task=task, original_name="synthetic.txt",
            media_type="text/plain", path="unused/synthetic.txt", sha256="a" * 64,
            size=1, parsed={"background": "Synthetic source"}) for task in (active, deleted)]
        revision = DocumentRevision.objects.get(task=deleted, kind="input", version=1)
        DocumentTask.objects.filter(pk=deleted.pk).update(deleted_at=timezone.now(), state="QUEUED")

        self.assertEqual(self.client.get(f"/api/product/tasks/{active.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/product/sources/{sources[0].pk}/").status_code, 200)
        listing = self.client.get("/api/product/tasks/").json()
        self.assertEqual([item["id"] for item in listing], [str(active.pk)])
        self.assertNotContains(self.client.get("/api/product/workspace/"), str(deleted.pk))
        for url in (f"/api/product/tasks/{deleted.pk}/", f"/api/product/tasks/{deleted.pk}/history/",
                    f"/api/product/tasks/{deleted.pk}/outputs/", f"/api/product/sources/{sources[1].pk}/",
                    f"/api/product/sources/{sources[1].pk}/download/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        replay = self.client.post("/api/product/tasks/", json.dumps(payload),
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="deleted-task")
        self.assertEqual(replay.status_code, 404)
        self.assertIsNone(claim_task())
        self.assertFalse(self.owner.owned_document_tasks.filter(pk=deleted.pk, deleted_at__isnull=True).exists())
        self.assertFalse(input_authorized(deleted, revision))  # stale instance
        child = DocumentSource.objects.select_related("task").get(pk=sources[1].pk)
        self.assertFalse(input_authorized(child.task, revision))  # FK bypasses manager
        self.assertTrue(DocumentTask.objects.filter(pk=deleted.pk).exists())

    def test_archived_conversations_are_hidden_and_cached_streams_stop(self):
        scope = {"datasets": {"synthetic-dataset": ["synthetic-document"]}}
        active = Conversation.objects.create(owner=self.owner, scope=scope, title="active")
        archived = Conversation.objects.create(owner=self.owner, scope=scope, title="archived",
            archived_at=timezone.now())
        with patch("portal.product_knowledge_service.authorize", return_value=scope), \
                patch("portal.product_knowledge_service.recheck"), \
                patch("portal.product_knowledge_service.ready", return_value=("url", "token", "route")):
            base = "/api/product/knowledge/conversations/"
            self.assertEqual(self.client.get(base + f"{active.pk}/").status_code, 200)
            listing = self.client.get(base).json()["conversations"]
            self.assertEqual([item["id"] for item in listing], [str(active.pk)])
            for method in (self.client.get, self.client.post):
                self.assertEqual(method(base + f"{archived.pk}/").status_code, 404)

            def archive_during_retrieval(*args):
                Conversation.objects.filter(pk=active.pk).update(archived_at=timezone.now())
                return []

            with patch("portal.product_knowledge_service.retrieve", side_effect=archive_during_retrieval):
                response = self.client.post(base + f"{active.pk}/", json_body(
                    question="synthetic question", version=0, request_id=str(uuid.uuid4()), stream=True),
                    content_type="application/json")
                self.assertEqual(response.status_code, 200)
                events = [json.loads(line[6:]) for chunk in response.streaming_content
                          for line in chunk.decode().splitlines() if line.startswith("data: ")]
                self.assertEqual(events, [{"error": {"code": "not_found", "detail": "对象不存在。"}}])
            with self.assertRaises(ProductError):
                visible(SimpleNamespace(user=self.owner, knowledge_scope=scope), active)
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertFalse(Conversation.objects.filter(archived_at__isnull=True).exists())


class LegacyProductVisibilityMigrationTests(TransactionTestCase):
    def test_existing_columns_and_values_survive_conditional_migration(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("portal", "0037_knowledge_access")]
        try:
            # Reverse intentionally retains the five columns, reproducing a legacy DB.
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            user = apps.get_model("portal", "User").objects.create(username="migration-owner")
            task = apps.get_model("portal", "DocumentTask").objects.create(
                owner=user, title="synthetic", idempotency_key="synthetic")
            chat = apps.get_model("portal", "ProductKnowledgeConversation").objects.create(owner=user)
            now = timezone.now()
            pending = uuid.uuid4()
            with connection.cursor() as cursor:
                cursor.execute("UPDATE portal_documenttask SET retry_after=%s, pinned_at=%s, deleted_at=%s WHERE id=%s",
                               [now, now, now, task.pk.hex])
                cursor.execute("UPDATE portal_productknowledgeconversation SET archived_at=%s, pending_request_id=%s WHERE id=%s",
                               [now, pending.hex, chat.pk.hex])
                cursor.execute("SELECT retry_after, pinned_at, deleted_at FROM portal_documenttask WHERE id=%s", [task.pk.hex])
                task_before = cursor.fetchone()
                cursor.execute("SELECT archived_at, pending_request_id FROM portal_productknowledgeconversation WHERE id=%s", [chat.pk.hex])
                chat_before = cursor.fetchone()
            with patch.object(connection.SchemaEditorClass, "add_field",
                              side_effect=AssertionError("Existing legacy columns must not be added again")):
                MigrationExecutor(connection).migrate(latest)
            with connection.cursor() as cursor:
                cursor.execute("SELECT retry_after, pinned_at, deleted_at FROM portal_documenttask WHERE id=%s", [task.pk.hex])
                self.assertEqual(cursor.fetchone(), task_before)
                cursor.execute("SELECT archived_at, pending_request_id FROM portal_productknowledgeconversation WHERE id=%s", [chat.pk.hex])
                self.assertEqual(cursor.fetchone(), chat_before)
            self.assertTrue(DocumentTask.objects.filter(pk=task.pk, deleted_at__isnull=False).exists())
            self.assertTrue(Conversation.objects.filter(pk=chat.pk, archived_at__isnull=False).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
