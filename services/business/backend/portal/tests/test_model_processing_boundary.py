from unittest.mock import patch

from django.db import transaction
from django.db.models import F
from django.test import override_settings

from portal import model_gateway as gateway
from portal.models import GatewayModel, ModelCallLog, ModelRoute, ModelRouteOption, Module, Provider, Role, User

from .base import PortalTestCase


class ModelProcessingBoundaryTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("boundary-user", "product")
        self.external = Provider.objects.create(code="external", name="外部",
            base_url="https://external.example/v1", api_key_env="PORTAL_MODEL_KEY_EXTERNAL", enabled=True)
        self.internal = Provider.objects.create(code="internal", name="内部",
            base_url="https://internal.example/v1", api_key_env="PORTAL_MODEL_KEY_INTERNAL", enabled=True,
            processing_boundary=Provider.ProcessingBoundary.INTERNAL)
        self.external_model = GatewayModel.objects.create(name="外部模型", provider=self.external,
            model_name="external", enabled=True)
        self.internal_model = GatewayModel.objects.create(name="内部模型", provider=self.internal,
            model_name="internal", enabled=True)
        self.route = ModelRoute.objects.create(code="product_assistant", name="产品助手",
            module=Module.objects.get(code="product"), model=self.internal_model, enabled=True,
            allow_external_processing=False)
        ModelRouteOption.objects.create(route=self.route, model=self.external_model)
        self.messages = [{"role": "user", "content": "仅限内部处理的业务资料"}]
        self.reply = {"content": "result", "duration_ms": 1, "prompt_tokens": 2, "completion_tokens": 3}

    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(gateway.GatewayError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def allow_external(self):
        ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=True)

    def test_defaults_are_conservative_provider_and_compatible_route(self):
        self.assertEqual(self.external.processing_boundary, Provider.ProcessingBoundary.EXTERNAL)
        self.assertIs(ModelRoute._meta.get_field("allow_external_processing").default, True)

    @patch("portal.model_gateway._request_gateway")
    def test_internal_only_picker_and_implicit_default_call_use_internal(self, request):
        request.return_value = self.reply
        choices = gateway.selectable_models(self.user, self.route.code)
        self.assertEqual([item["id"] for item in choices["models"]], [str(self.internal_model.public_id)])
        self.assertEqual(gateway.generate_for_use(self.user, self.route.code, self.messages), self.reply)
        self.assertEqual(request.call_args.args[0]["provider"]["base_url"], self.internal.base_url)
        self.assertEqual(ModelCallLog.objects.get().status, "success")

    @patch("portal.model_gateway._request_gateway")
    def test_external_implicit_default_is_never_reintroduced(self, request):
        self.route.model = self.external_model
        self.route.save()
        ModelRouteOption.objects.all().delete()
        self.assert_error("disabled", gateway.selectable_models, self.user, self.route.code)
        self.assert_error("disabled", gateway.generate_for_use, self.user, self.route.code, self.messages)
        request.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    @patch("portal.model_gateway._request_gateway")
    def test_stale_explicit_external_choice_is_blocked_before_network(self, request):
        self.allow_external()
        selection = gateway.validate_model_selection(self.user, self.route.code, {
            "model_id": str(self.external_model.public_id),
            "config_version": next(item["config_version"] for item in gateway.selectable_models(
                self.user, self.route.code)["models"] if item["id"] == str(self.external_model.public_id)),
        })
        ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
        self.assert_error("forbidden", gateway.generate_for_use, self.user, self.route.code,
                          self.messages, selection)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_policy_changed_after_selection_blocks_before_network(self, request):
        self.allow_external()
        ModelRoute.objects.filter(pk=self.route.pk).update(model=self.external_model)
        original_reserve = gateway._reserve

        def change_before_reservation(*args, **kwargs):
            ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
            return original_reserve(*args, **kwargs)

        with patch.object(gateway, "_reserve", side_effect=change_before_reservation):
            self.assert_error("processing_boundary_denied", gateway.generate_for_use,
                              self.user, self.route.code, self.messages)
        request.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    @patch("portal.model_gateway._request_gateway")
    def test_provider_boundary_changed_after_selection_blocks_before_network(self, request):
        original_reserve = gateway._reserve

        def change_before_reservation(*args, **kwargs):
            Provider.objects.filter(pk=self.internal.pk).update(processing_boundary="external")
            return original_reserve(*args, **kwargs)

        with patch.object(gateway, "_reserve", side_effect=change_before_reservation):
            self.assert_error("processing_boundary_denied", gateway.generate_for_use,
                              self.user, self.route.code, self.messages)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_new_internal_assignment_cannot_authorize_prepared_external_payload(self, request):
        self.allow_external()
        ModelRoute.objects.filter(pk=self.route.pk).update(model=self.external_model)
        original_reserve = gateway._reserve

        def change_before_reservation(*args, **kwargs):
            ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
            GatewayModel.objects.filter(pk=self.external_model.pk).update(provider=self.internal)
            return original_reserve(*args, **kwargs)

        with patch.object(gateway, "_reserve", side_effect=change_before_reservation):
            self.assert_error("processing_boundary_denied", gateway.generate_for_use,
                              self.user, self.route.code, self.messages)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_policy_fields_invalidate_versions_even_without_updated_timestamp(self, request):
        selection = gateway.validate_model_selection(self.user, self.route.code)
        self.allow_external()
        self.assert_error("model_configuration_changed", gateway.generate_for_use,
                          self.user, self.route.code, self.messages, selection)
        selection = gateway.validate_model_selection(self.user, self.route.code)
        Provider.objects.filter(pk=self.internal.pk).update(processing_boundary="external")
        self.assert_error("model_configuration_changed", gateway.generate_for_use,
                          self.user, self.route.code, self.messages, selection)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_provider_policy_change_discards_inflight_result_and_audits_failure(self, request):
        def change_policy(payload):
            Provider.objects.filter(pk=self.internal.pk).update(processing_boundary="external")
            return self.reply

        request.side_effect = change_policy
        self.assert_error("forbidden", gateway.generate_for_use, self.user, self.route.code, self.messages)
        request.assert_called_once()
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")

    @patch("portal.model_gateway._request_gateway")
    def test_route_policy_change_discards_inflight_external_result_without_retry(self, request):
        self.allow_external()
        ModelRoute.objects.filter(pk=self.route.pk).update(model=self.external_model)

        def change_policy(payload):
            ModelRoute.objects.filter(pk=self.route.pk).update(allow_external_processing=False)
            return self.reply

        request.side_effect = change_policy
        self.assert_error("forbidden", gateway.generate_for_use, self.user, self.route.code, self.messages)
        request.assert_called_once()
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_assistant")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_rechecks_policy_before_emitting_each_delta(self, request):
        def events(payload):
            yield {"delta": "允许的片段"}
            Provider.objects.filter(pk=self.internal.pk).update(processing_boundary="external")
            yield {"delta": "拒绝的片段"}
            yield {"done": True, "prompt_tokens": 1, "completion_tokens": 2}

        request.side_effect = events
        stream = gateway.stream_for_use(self.user, self.route.code, self.messages)
        self.assertEqual(next(stream), {"delta": "允许的片段"})
        self.assert_error("forbidden", next, stream)
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")

    @patch("portal.model_gateway._request_gateway")
    def test_client_cannot_override_server_processing_policy(self, request):
        selection = gateway.validate_model_selection(self.user, self.route.code)
        self.login(self.client, self.user)
        response = self.client.post("/api/models/departments/product/ask/", {
            "prompt": "资料", "model_selection": selection,
            "allow_external_processing": True, "sensitivity": "public",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_internal_failure_does_not_retry_external_model(self, request):
        request.side_effect = gateway.GatewayError("timeout", status=504)
        self.assert_error("timeout", gateway.generate_for_use, self.user, self.route.code, self.messages)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0]["provider"]["base_url"], self.internal.base_url)

    @patch("portal.model_gateway._request_gateway")
    def test_identity_changes_after_selection_block_before_network(self, request):
        original_reserve = gateway._reserve
        for changes in ({"is_active": False}, {"must_change_password": True},
                        {"session_version": F("session_version") + 1},
                        {"grant_version": F("grant_version") + 1}):
            with self.subTest(changes=changes), transaction.atomic():
                def revoke(*args, **kwargs):
                    User.objects.filter(pk=self.user.pk).update(**changes)
                    return original_reserve(*args, **kwargs)

                with patch.object(gateway, "_reserve", side_effect=revoke):
                    self.assert_error("forbidden", gateway.generate_for_use,
                                      self.user, self.route.code, self.messages)
                request.assert_not_called()
                self.assertFalse(ModelCallLog.objects.exists())
                transaction.set_rollback(True)

    @patch("portal.model_gateway._request_gateway")
    def test_disabled_route_model_provider_or_module_block_before_network(self, request):
        original_reserve = gateway._reserve
        for target, code in ((self.route, "disabled"), (self.internal_model, "disabled"),
                             (self.internal, "disabled"), (self.route.module, "forbidden")):
            with self.subTest(target=type(target).__name__), transaction.atomic():
                def revoke(*args, **kwargs):
                    type(target).objects.filter(pk=target.pk).update(enabled=False)
                    return original_reserve(*args, **kwargs)

                with patch.object(gateway, "_reserve", side_effect=revoke):
                    self.assert_error(code, gateway.generate_for_use,
                                      self.user, self.route.code, self.messages)
                request.assert_not_called()
                self.assertFalse(ModelCallLog.objects.exists())
                transaction.set_rollback(True)

    @patch("portal.model_gateway._request_gateway")
    def test_option_scope_or_configuration_changes_block_before_network(self, request):
        option = ModelRouteOption.objects.create(route=self.route, model=self.internal_model)
        original_reserve = gateway._reserve
        for change, code in (("option", "forbidden"), ("scope", "forbidden"),
                             ("option_version", "model_configuration_changed"),
                             ("provider", "model_configuration_changed"), ("model", "model_configuration_changed")):
            with self.subTest(change=change), transaction.atomic():
                def revoke(*args, **kwargs):
                    if change == "option":
                        ModelRouteOption.objects.filter(pk=option.pk).update(enabled=False)
                    elif change == "scope":
                        option.allowed_roles.add(Role.objects.get(code="hr"))
                    elif change == "option_version":
                        ModelRouteOption.objects.filter(pk=option.pk).update(display_order=1)
                    elif change == "provider":
                        Provider.objects.filter(pk=self.internal.pk).update(base_url="https://changed.example/v1")
                    else:
                        GatewayModel.objects.filter(pk=self.internal_model.pk).update(model_name="changed")
                    return original_reserve(*args, **kwargs)

                with patch.object(gateway, "_reserve", side_effect=revoke):
                    self.assert_error(code, gateway.generate_for_use,
                                      self.user, self.route.code, self.messages)
                request.assert_not_called()
                self.assertFalse(ModelCallLog.objects.exists())
                transaction.set_rollback(True)

    @patch("portal.model_gateway._request_gateway")
    def test_role_revocation_after_selection_blocks_before_network(self, request):
        original_reserve = gateway._reserve

        def revoke(*args, **kwargs):
            self.user.roles.clear()
            return original_reserve(*args, **kwargs)

        with patch.object(gateway, "_reserve", side_effect=revoke):
            self.assert_error("forbidden", gateway.generate_for_use,
                              self.user, self.route.code, self.messages)
        request.assert_not_called()

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_assistant")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_revocation_after_selection_blocks_before_network(self, request):
        original_reserve = gateway._reserve

        def revoke(*args, **kwargs):
            User.objects.filter(pk=self.user.pk).update(is_active=False)
            return original_reserve(*args, **kwargs)

        with patch.object(gateway, "_reserve", side_effect=revoke):
            self.assert_error("forbidden", list, gateway.stream_for_use(self.user, self.route.code, self.messages))
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_admin_connection_checks_identity_role_and_prepared_configuration_before_network(self, request):
        admin = self.create_admin("boundary-admin")
        original_reserve = gateway._reserve
        for change, code in (("identity", "forbidden"), ("role", "forbidden"), ("model", "disabled")):
            with self.subTest(change=change), transaction.atomic():
                def revoke(*args, **kwargs):
                    if change == "identity":
                        User.objects.filter(pk=admin.pk).update(is_active=False)
                    elif change == "role":
                        # Raw through deletion also tests the live admin capability,
                        # independently of the normal grant-version signal.
                        User.roles.through.objects.filter(user_id=admin.pk).delete()
                    else:
                        GatewayModel.objects.filter(pk=self.internal_model.pk).update(model_name="changed")
                    return original_reserve(*args, **kwargs)

                with patch.object(gateway, "_reserve", side_effect=revoke):
                    self.assert_error(code, gateway.test_connection, admin, self.internal_model.pk)
                request.assert_not_called()
                self.assertFalse(ModelCallLog.objects.exists())
                transaction.set_rollback(True)
