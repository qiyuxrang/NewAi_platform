"""Merged safety boundaries on the existing Harness and document-download paths."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from portal import model_gateway as gateway, product_assistant_model as assistant
from portal import product_assistant_tools as tools, product_knowledge_api as api
from portal import product_knowledge_service as knowledge
from portal.knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant
from portal.models import GatewayModel, ModelCallLog, ModelRoute, Module, Provider
from portal.product_service import ProductError
from .base import PortalTestCase


@override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
class MergedAssistantBoundaryTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("merged-assistant", "product")
        self.user.refresh_from_db()
        provider = Provider.objects.create(code="merged", name="Test", base_url="https://provider.example/v1",
            api_key_env="PORTAL_MODEL_KEY_TEST", enabled=True)
        self.model = GatewayModel.objects.create(name="Test", provider=provider, model_name="test", enabled=True)
        self.route = ModelRoute.objects.create(code="product_knowledge", name="Test",
            module=Module.objects.get(code="product"), model=self.model, enabled=True)

    def stream(self):
        return assistant.stream_agent_for_use(self.user, self.route.code,
            [{"role": "user", "content": "synthetic"}], [], recheck=Mock())

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_harness_internal_only_route_blocks_external_before_network(self, outbound):
        ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
        with self.assertRaises(gateway.GatewayError):
            list(self.stream())
        outbound.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_harness_boundary_revocation_blocks_next_delta(self, outbound):
        def events(*args, **kwargs):
            yield {"delta": "first"}
            ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
            yield {"delta": "MUST-NOT-LEAK"}
        outbound.side_effect = events
        stream = self.stream()
        self.assertEqual(next(stream), {"delta": "first"})
        with self.assertRaises(gateway.GatewayError):
            next(stream)
        self.assertNotEqual(ModelCallLog.objects.get().status, "success")

    @patch("portal.product_assistant_model._request_agent_stream")
    def test_harness_reservation_rechecks_boundary_before_network(self, outbound):
        reserve = gateway._reserve
        def revoke(*args, **kwargs):
            ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
            return reserve(*args, **kwargs)
        with patch.object(gateway, "_reserve", side_effect=revoke), self.assertRaises(gateway.GatewayError) as caught:
            list(self.stream())
        self.assertEqual(caught.exception.code, "processing_boundary_denied")
        outbound.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    def test_denied_sources_do_not_disable_empty_chat_or_fall_back_to_legacy(self):
        KnowledgeAccessPolicy.objects.create(department_code="product", enabled=True)
        with override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS={str(self.user.pk): {"legacy": ["secret"]}}):
            scope = knowledge.authorize(self.user, allow_empty=True)
            self.assertEqual(scope["datasets"], {})
            self.assertEqual(scope["ai_datasets"], {})
            self.assertFalse(scope["allow_assistant_export"])
            with self.assertRaises(ProductError):
                knowledge.authorize(self.user)

    @patch("portal.product_knowledge_api.original_input")
    def test_read_grant_does_not_allow_original_download(self, original):
        policy = KnowledgeAccessPolicy.objects.create(department_code="product", enabled=True)
        KnowledgeDocumentGrant.objects.create(policy=policy, dataset_id="dataset", document_id="document",
            user=self.user, can_read=True, can_ai_use=False, can_download=False, enabled=True)
        request = SimpleNamespace(user=self.user, knowledge_scope=knowledge.authorize(self.user), query_params={})
        with self.assertRaises(ProductError) as caught:
            api.original_response(request, "dataset", "document", download=True)
        self.assertEqual(caught.exception.code, "forbidden")
        original.assert_not_called()


class MergedToolBoundaryTests(SimpleTestCase):
    def test_harness_cannot_list_or_read_documents_without_ai_permission(self):
        scope = {"datasets": {"dataset": ["read-only"]}, "ai_datasets": {}}
        toolbox = tools.AssistantTools("question", scope, ("url", "token", "route"),
            web_search=False, recheck=Mock())
        self.assertFalse(any(item["function"]["name"].startswith("knowledge_") for item in toolbox.schemas))
        for name, args in (("knowledge_list", {}),
                           ("knowledge_read", {"dataset_id": "dataset", "document_id": "read-only"})):
            with self.subTest(name=name), patch.object(knowledge, "_open") as outbound:
                with self.assertRaises(ProductError):
                    toolbox._execute(name, args)
                outbound.assert_not_called()
