from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from portal import engineering_api as api
from portal import engineering_knowledge as knowledge
from portal.knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant
from .base import PortalTestCase
from .test_engineering_knowledge import CONFIG, DATASET


class EngineeringKnowledgeAccessTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_active=True, is_authenticated=True)
        self.user.roles = MagicMock()
        self.user.roles.filter.return_value.exists.return_value = True
        self.enterContext(patch.object(api, "can_use_department", return_value=True))
        self.enterContext(patch.object(api, "is_business_manager", return_value=False))
        self.enterContext(patch.object(api.EngineeringJob.objects, "filter"))
        self.enterContext(patch.object(api, "audit"))
        self.enterContext(patch.object(knowledge, "configuration", return_value=CONFIG))
        self.snapshot = {"datasets": {DATASET: ["allowed-doc"], "other-dataset": ["other-doc"]},
                         "revision": "revision-1"}
        self.authorize = self.enterContext(patch.object(api.knowledge_access, "authorize",
                                                       return_value=self.snapshot))
        self.recheck = self.enterContext(patch.object(api.knowledge_access, "recheck"))
        self.outbound = self.enterContext(patch.object(knowledge, "_request"))
        self.outbound.return_value = {"chunks": [{"id": "chunk-1", "dataset_id": DATASET,
            "document_id": "allowed-doc", "document_keyword": "授权资料", "content": "授权证据"}]}

    def call(self, *, status=False, payload=None):
        request = (self.factory.get("/api/engineering/knowledge/") if status else
                   self.factory.post("/api/engineering/knowledge/retrieve/",
                                     payload or {"question": "定额来源？"}, format="json"))
        force_authenticate(request, user=self.user)
        return (api.knowledge_status if status else api.knowledge_retrieve)(request)

    def test_status_counts_only_authorized_fixed_dataset_documents_without_network(self):
        response = self.call(status=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["dataset_document_count"], 1)
        self.assertEqual(response.data["authorization_revision"], "revision-1")
        self.assertIs(response.data["assistant_export_allowed"], False)
        self.snapshot["allow_assistant_export"] = True
        self.assertIs(self.call(status=True).data["assistant_export_allowed"], True)
        self.outbound.assert_not_called()
        self.recheck.assert_called_with(self.user, "engineering", self.snapshot, action="ai_use")

    def test_retrieval_sends_both_server_owned_scopes(self):
        response = self.call()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sources"][0]["document_id"], "allowed-doc")
        self.assertEqual(response.data["authorization_revision"], "revision-1")
        self.assertIs(response.data["assistant_export_allowed"], False)
        self.outbound.assert_called_once_with(CONFIG[0], CONFIG[2], body={
            "question": "定额来源？", "dataset_ids": [DATASET], "document_ids": ["allowed-doc"],
            "page": 1, "page_size": 6})
        self.authorize.assert_called_with(self.user, "engineering", action="ai_use")
        self.assertEqual(self.recheck.call_count, 4)
        self.snapshot["allow_assistant_export"] = True
        self.assertIs(self.call().data["assistant_export_allowed"], True)

    def test_missing_scope_or_denied_policy_blocks_all_network(self):
        for scope in ({}, {DATASET: []}, {"other-dataset": ["allowed-doc"]}):
            self.snapshot["datasets"] = scope
            for status in (True, False):
                with self.subTest(scope=scope, status=status):
                    response = self.call(status=status)
                    self.assertEqual((response.status_code, response.data["code"]),
                                     (403, "knowledge_forbidden"))
        self.authorize.side_effect = api.knowledge_access.KnowledgeAccessDenied()
        self.assertEqual(self.call().status_code, 403)
        self.outbound.assert_not_called()

    def test_provider_cannot_return_another_document_or_dataset(self):
        for field, value in (("document_id", "private-doc"), ("dataset_id", "other-dataset")):
            self.outbound.return_value = {"chunks": [{"id": "chunk-1", "dataset_id": DATASET,
                "document_id": "allowed-doc", "document_keyword": "private-title",
                "content": "private-evidence", field: value}]}
            with self.subTest(field=field):
                response = self.call()
                self.assertEqual((response.status_code, response.data["code"]),
                                 (503, "knowledge_unavailable"))
                self.assertNotIn("private", str(response.data))

    def test_revocation_during_retrieval_suppresses_sources(self):
        def revoke(*args, **kwargs):
            self.recheck.side_effect = api.knowledge_access.KnowledgeAccessDenied()
            return {"chunks": [{"id": "chunk-1", "dataset_id": DATASET,
                "document_id": "allowed-doc", "content": "revoked-evidence"}]}

        self.outbound.side_effect = revoke
        response = self.call()
        self.assertEqual((response.status_code, response.data["code"]), (403, "knowledge_forbidden"))
        self.assertNotIn("revoked-evidence", str(response.data))

    def test_recheck_denial_before_retrieval_blocks_network(self):
        self.recheck.side_effect = api.knowledge_access.KnowledgeAccessDenied()
        self.assertEqual(self.call().status_code, 403)
        self.outbound.assert_not_called()

    def test_caller_cannot_select_documents_or_datasets(self):
        for name, value in (("document_ids", ["private-doc"]), ("dataset_ids", ["other-dataset"])):
            response = self.call(payload={"question": "来源", name: value})
            self.assertEqual(response.status_code, 400)
        self.authorize.assert_not_called()
        self.outbound.assert_not_called()

    def test_empty_managed_scope_cannot_call_retrieval_directly(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.retrieve("来源", CONFIG, [])
        self.outbound.assert_not_called()


class EngineeringKnowledgeDatabaseAccessTests(PortalTestCase):
    def test_database_grant_and_revocation_are_enforced_at_the_response_boundary(self):
        user = self.create_user("engineering-knowledge-owner", "engineering")
        user.refresh_from_db()
        api.EngineeringJob.objects.create(owner=user, inspection={"ok": True})
        policy = KnowledgeAccessPolicy.objects.create(department_code="engineering", enabled=True)
        grant = KnowledgeDocumentGrant.objects.create(policy=policy, user=user, enabled=True,
            can_read=True, can_ai_use=True, dataset_id=DATASET, document_id="allowed-doc")
        factory = APIRequestFactory()

        def call():
            request = factory.post("/api/engineering/knowledge/retrieve/",
                                   {"question": "来源"}, format="json")
            force_authenticate(request, user=user)
            return api.knowledge_retrieve(request)

        chunks = {"chunks": [{"id": "chunk-1", "dataset_id": DATASET,
                              "document_id": "allowed-doc", "content": "授权证据"}]}
        with patch.object(knowledge, "configuration", return_value=CONFIG), \
                patch.object(knowledge, "_request", return_value=chunks) as outbound:
            response = call()
            self.assertEqual(response.status_code, 200)
            self.assertIs(response.data["assistant_export_allowed"], False)
            self.assertEqual(response.data["authorization_revision"],
                             api.knowledge_access.authorize(user, "engineering", action="ai_use")["revision"])
            self.assertEqual(outbound.call_args.kwargs["body"]["document_ids"], ["allowed-doc"])

            def revoke(*args, **kwargs):
                KnowledgeDocumentGrant.objects.filter(pk=grant.pk).update(enabled=False)
                return chunks

            outbound.side_effect = revoke
            response = call()
            self.assertEqual((response.status_code, response.data["code"]), (403, "knowledge_forbidden"))
            self.assertNotIn("sources", response.data)
            outbound.reset_mock()
            self.assertEqual(call().status_code, 403)
            outbound.assert_not_called()
