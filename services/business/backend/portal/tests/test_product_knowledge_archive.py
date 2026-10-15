"""Archive/restore contracts. External knowledge and model calls use existing mocks."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import Client
from django.utils import timezone
from rest_framework.test import force_authenticate

from portal import product_knowledge_api as api
from portal.models import AuditEvent
from portal.product_knowledge_models import ProductKnowledgeConversation as Conversation

from .base import ADMIN_PASSWORD, PortalTestCase
from .test_product_knowledge_api import _ProductKnowledgeApiFixture


class ProductKnowledgeArchiveTests(_ProductKnowledgeApiFixture, PortalTestCase):
    def lifecycle(self, view, item, version, user=None):
        return self.request(view, "post", {"version": version}, user=user, conversation=item)

    def test_archive_frees_limit_without_disclosing_or_deleting_old_scope(self):
        item = self.create()
        turns = [{"question": "SECRET", "answer": "SECRET", "sources": [{"text": "SECRET"}]}]
        Conversation.objects.filter(pk=item.pk).update(title="SECRET", turns=turns)
        Conversation.objects.bulk_create([Conversation(owner=self.owner, scope=item.scope) for _ in range(99)])
        self.grants[str(self.owner.pk)] = {"dataset-1": ["replacement-document"]}
        self.assertEqual(self.request(api.conversations).data["conversations"], [])
        self.assertEqual(self.request(api.conversations, "post", {}).status_code, 409)
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 0, self.other).status_code, 404)
        archived = self.lifecycle(api.archive_conversation, item, 0)
        self.assertEqual(archived.data, {"id": str(item.pk), "version": 1, "archived": True})
        self.assertNotIn(b"SECRET", archived.content)
        self.assertEqual(self.request(api.archived_conversations).data["conversations"], [])
        self.assertEqual(self.request(api.conversation, conversation=item).status_code, 404)
        self.assertEqual(self.send(item).status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.turns, turns)
        self.assertEqual(item.title, "SECRET")
        self.assertIsNotNone(item.archived_at)
        self.assertEqual(self.request(api.conversations, "post", {}).status_code, 201)
        self.assertEqual(Conversation.objects.count(), 101)
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_restore_requires_owner_scope_version_and_capacity(self):
        item = self.create()
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 0).status_code, 200)
        self.assertEqual(self.lifecycle(api.restore_conversation, item, 1, self.other).status_code, 404)
        self.grants[str(self.owner.pk)] = {"dataset-1": ["replacement-document"]}
        revoked = self.lifecycle(api.restore_conversation, item, 1)
        self.assertEqual(revoked.status_code, 403)
        self.assertEqual(revoked.data["code"], "scope_revoked")
        self.grants[str(self.owner.pk)] = {"dataset-1": ["document-1"]}
        self.assertEqual(self.request(api.archived_conversations).data["conversations"][0]["id"], str(item.pk))
        self.assertEqual(self.lifecycle(api.restore_conversation, item, 0).status_code, 409)
        Conversation.objects.bulk_create([Conversation(owner=self.owner, scope=item.scope) for _ in range(100)])
        self.assertEqual(self.lifecycle(api.restore_conversation, item, 1).data["code"], "conversation_limit")
        replacement = Conversation.objects.filter(owner=self.owner, archived_at__isnull=True).first()
        self.assertEqual(self.lifecycle(api.archive_conversation, replacement, 0).status_code, 200)
        restored = self.lifecycle(api.restore_conversation, item, 1)
        self.assertEqual(restored.data, {"id": str(item.pk), "version": 2, "archived": False})
        self.assertEqual(self.request(api.conversation, conversation=item).data["version"], 2)
        event = AuditEvent.objects.get(action="productknowledgeconversation_restore", target=str(item.pk))
        self.assertEqual(event.changes, ["archived_at"])
        self.assertEqual(Conversation.objects.filter(owner=self.owner, archived_at__isnull=True).count(), 100)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.grant_version, item.scope["grant_version"])

    def test_archive_validates_version_and_rejects_live_lease(self):
        item = self.create()
        for payload in ({}, {"version": True}, {"version": -1}, {"version": 0, "extra": True}):
            self.assertEqual(self.request(api.archive_conversation, "post", payload, conversation=item).status_code, 400)
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 1).status_code, 409)
        lease = uuid.uuid4()
        Conversation.objects.filter(pk=item.pk).update(pending_id=lease, pending_until=timezone.now() + timedelta(seconds=60))
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 0).status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.pending_id, lease)
        self.assertIsNone(item.archived_at)
        Conversation.objects.filter(pk=item.pk).update(pending_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 0).status_code, 200)
        self.assertEqual(self.lifecycle(api.archive_conversation, item, 0).status_code, 409)

    def test_archive_stops_expired_stream_before_more_chunks_or_commit(self):
        item = self.create()
        archived = []

        def events():
            yield {"delta": '{"answer":"允许的开头'}
            self.assertEqual(self.lifecycle(api.archive_conversation, item, 0).status_code, 409)
            Conversation.objects.filter(pk=item.pk).update(pending_until=timezone.now() - timedelta(seconds=1))
            archived.append(self.lifecycle(api.archive_conversation, item, 0).status_code)
            yield {"delta": 'SECRET_AFTER_ARCHIVE","source_ids":["S1"]}'}
            yield {"done": True}

        with patch("portal.model_gateway.stream_for_use", return_value=events()):
            request = self.factory.post("/api/product/knowledge/", {
                "question": "问题", "version": 0, "request_id": str(uuid.uuid4()), "stream": True}, format="json")
            force_authenticate(request, user=self.owner)
            response = api.conversation(request, conversation_id=item.pk)
            output = b"".join(response.streaming_content).decode()
        self.assertEqual(archived, [200])
        self.assertIn('"code": "not_found"', output)
        self.assertNotIn("SECRET_AFTER_ARCHIVE", output)
        self.assertNotIn('"done"', output)
        item.refresh_from_db()
        self.assertEqual(item.version, 1)
        self.assertEqual(item.turns, [])
        self.assertIsNotNone(item.archived_at)
        self.assertIsNone(item.pending_id)

    def test_admin_can_archive_hidden_scope_without_content_access(self):
        item = self.create()
        Conversation.objects.filter(pk=item.pk).update(title="SECRET_ADMIN", scope={"datasets": {"old": ["secret"]}},
                                                       turns=[{"answer": "SECRET_ADMIN"}])
        admin = self.create_admin()
        client = Client()
        self.login(client, admin, ADMIN_PASSWORD)
        url = "/admin/portal/productknowledgeconversation/"
        self.assertEqual(client.get(url).status_code, 200)
        self.assertNotIn(b"SECRET_ADMIN", client.get(url).content)
        self.assertNotIn(b"SECRET_ADMIN", client.get(url + str(item.pk) + "/change/").content)
        response = client.post(url, {"action": "archive_conversations", "_selected_action": [str(item.pk)], "index": "0"})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertIsNotNone(item.archived_at)
        self.assertEqual(item.turns, [{"answer": "SECRET_ADMIN"}])
        self.assertTrue(AuditEvent.objects.filter(action="productknowledgeconversation_archive", target=str(item.pk)).exists())
        protected = self.create()
        denied = Client()
        self.login(denied, self.owner)
        response = denied.post(url, {"action": "archive_conversations", "_selected_action": [str(protected.pk)]}, follow=True)
        self.assertEqual(response.status_code, 403)
        protected.refresh_from_db()
        self.assertIsNone(protected.archived_at)
        self.assertEqual(protected.version, 0)
