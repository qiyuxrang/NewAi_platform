"""Real ORM grants and bounded RAG HTTP parsing; no model calls or conversations."""
import json
from unittest.mock import patch

from django.test import Client, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from portal import product_knowledge_api as api
from portal import product_knowledge_service as service
from portal.models import User
from portal.product_knowledge_models import ProductKnowledgeConversation as Conversation
from portal.product_service import ProductError

from .base import PASSWORD, PortalTestCase
from .test_product_knowledge_service import CONFIG, Response, chunk, wire


class ProductKnowledgeRetrieveTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("retrieval-owner", "product")
        self.other = self.create_user("retrieval-ungranted", "product")
        self.admin = self.create_admin("retrieval-admin")
        self.owner.refresh_from_db()
        self.other.refresh_from_db()
        self.admin.refresh_from_db()
        self.grants = {str(self.owner.pk): {"dataset-1": ["document-1", "document-2"]}}
        override = override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS=self.grants)
        override.enable()
        self.addCleanup(override.disable)
        self.factory = APIRequestFactory()
        self.ready = self.start_patch("portal.product_knowledge_service.ready", return_value=CONFIG)
        self.start_patch("portal.product_knowledge_service.configuration", return_value=CONFIG)
        self.outbound = self.start_patch("portal.product_knowledge_service._open", side_effect=lambda *args: Response(wire()))
        self.model = self.start_patch("portal.model_gateway.generate_for_use", side_effect=AssertionError("No model calls"))

    def start_patch(self, name, **kwargs):
        item = patch(name, **kwargs)
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def request(self, payload=None, user=None, method="post", query=""):
        path = "/api/product/knowledge/retrieve/" + query
        request = (self.factory.get(path) if method == "get" else self.factory.post(path,
            data=json.dumps({"question": "  设备端口？  "} if payload is None else payload), content_type="application/json"))
        force_authenticate(request, user=user or self.owner)
        response = api.retrieve(request)
        response.render()
        return response

    def test_only_real_owner_grants_are_retrieved_without_model_or_conversation(self):
        count = Conversation.objects.count()
        response = self.request()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], "completed")
        source = response.data["sources"][0]
        self.assertEqual((source["id"], source["chunk_id"], source["dataset_id"], source["document_id"]),
                         ("S1", "chunk-1", "dataset-1", "document-1"))
        request = self.outbound.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["question"], "设备端口？")
        self.assertEqual(payload["dataset_ids"], ["dataset-1"])
        self.assertEqual(payload["document_ids"], ["document-1", "document-2"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertRegex(response.data["authorization_revision"], r"^[0-9a-f]{64}$")
        status_request = self.factory.get("/api/product/knowledge/status/")
        force_authenticate(status_request, user=self.owner)
        status = api.status(status_request)
        self.assertEqual(status.data["authorization_revision"], response.data["authorization_revision"])
        self.grants[str(self.owner.pk)]["dataset-1"] = ["document-1"]
        status_request = self.factory.get("/api/product/knowledge/status/")
        force_authenticate(status_request, user=self.owner)
        self.assertNotEqual(api.status(status_request).data["authorization_revision"], response.data["authorization_revision"])
        self.assertEqual(Conversation.objects.count(), count)
        self.model.assert_not_called()

    def test_other_user_admin_and_stale_or_inactive_owner_are_denied_before_rag(self):
        for user in (self.other, self.admin):
            self.assertEqual(self.request(user=user).status_code, 403)
        for field in ("is_active", "session_version", "grant_version"):
            original = getattr(self.owner, field)
            User.objects.filter(pk=self.owner.pk).update(**{field: False if field == "is_active" else original + 1})
            self.assertEqual(self.request().status_code, 403)
            User.objects.filter(pk=self.owner.pk).update(**{field: original})
        self.outbound.assert_not_called()

    def test_client_scope_key_url_and_invalid_questions_are_rejected(self):
        for extra in ({"dataset_ids": ["other"]}, {"document_ids": ["other"]}, {"api_key": "secret"},
                      {"user_id": self.other.pk}, {"url": "https://other.invalid"}, {"history": []}):
            self.assertEqual(self.request({"question": "test", **extra}).status_code, 400)
        for question in ("", " ", "x" * 2001, None, 123, "x\x00", "x\ud800"):
            self.assertEqual(self.request({"question": question}).status_code, 400)
        self.assertEqual(self.request({"question": "test"}, query="?dataset_ids=other").status_code, 400)
        self.assertEqual(self.request(method="get").status_code, 405)
        self.outbound.assert_not_called()

    def test_partial_revocation_or_configuration_change_during_rag_withholds_sources(self):
        for change in ("document", "user", "config"):
            with self.subTest(change=change):
                def retrieve_then_revoke(*args):
                    if change == "document":
                        # The returned document remains allowed, but another grant is revoked.
                        self.grants[str(self.owner.pk)]["dataset-1"] = ["document-1"]
                    elif change == "user":
                        User.objects.filter(pk=self.owner.pk).update(is_active=False)
                    else:
                        self.ready.return_value = (CONFIG[0], CONFIG[1], "replacement-route")
                    return Response(wire())
                self.outbound.side_effect = retrieve_then_revoke
                response = self.request()
                self.assertIn(response.status_code, (403, 503))
                self.assertNotIn("sources", response.data)
                self.assertNotIn("chunk-1", response.content.decode())
                self.grants[str(self.owner.pk)]["dataset-1"] = ["document-1", "document-2"]
                User.objects.filter(pk=self.owner.pk).update(is_active=True)
                self.ready.return_value = CONFIG
        self.model.assert_not_called()

    def test_wrong_document_oversized_rag_and_unready_service_fail_closed(self):
        for raw in (wire([chunk(document_id="other-private-doc")]), b" " * 262145):
            self.outbound.side_effect = lambda *args: Response(raw)
            self.assertEqual(self.request().status_code, 502)
        self.outbound.reset_mock()
        self.ready.side_effect = ProductError("disabled", "disabled", 503)
        self.assertEqual(self.request().status_code, 503)
        self.outbound.assert_not_called()
        self.model.assert_not_called()

    def test_real_route_requires_portal_session_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        token = self.csrf_token(client)
        signed = client.post("/api/login/", data=json.dumps({"username": self.owner.username, "password": PASSWORD}),
                             content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(signed.status_code, 200, signed.content)
        token = self.csrf_token(client)
        path = "/api/product/knowledge/retrieve/"
        response = client.post(path, data=json.dumps({"question": "端口？"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        response = client.post(path, data=json.dumps({"question": "端口？"}),
                               content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sources"][0]["id"], "S1")
        self.model.assert_not_called()
