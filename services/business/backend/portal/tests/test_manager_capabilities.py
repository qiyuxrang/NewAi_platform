from portal.models import Module, Role
from portal.security import authorized_modules, can_use_department, is_business_manager

from .base import PortalTestCase


class ManagerCapabilityTests(PortalTestCase):
    def test_manager_has_local_capabilities_without_legacy_or_admin_grants(self):
        manager = self.create_user("manager-capabilities", "general_manager")
        self.assertTrue(is_business_manager(manager))
        for code in ("product", "hr", "cost", "business", "finance"):
            with self.subTest(code=code):
                self.assertTrue(can_use_department(manager, code))
        self.assertEqual(list(authorized_modules(manager).values_list("code", flat=True)), ["business"])
        self.assertFalse(can_use_department(manager, "ops"))
        self.assertFalse(can_use_department(self.create_admin(), "product"))
        product_user = self.create_user("product-capabilities", "product")
        self.assertTrue(can_use_department(product_user, "product"))
        self.assertFalse(can_use_department(product_user, "hr"))

    def test_disabled_modules_and_revocation_stop_capabilities(self):
        manager = self.create_user("manager-revocation", "general_manager")
        Module.objects.filter(code="product").update(enabled=False)
        self.assertFalse(can_use_department(manager, "product"))
        self.assertTrue(can_use_department(manager, "hr"))
        Module.objects.filter(code="business").update(enabled=False)
        self.assertFalse(can_use_department(manager, "hr"))
        Module.objects.filter(code="business").update(enabled=True)
        manager.roles.remove(Role.objects.get(code="general_manager"))
        self.assertFalse(can_use_department(manager, "hr"))

    def test_inactive_and_first_login_accounts_cannot_use_capabilities(self):
        manager = self.create_user("manager-first-login", "general_manager", must_change_password=True)
        self.assertFalse(can_use_department(manager, "product"))
        manager.must_change_password = False
        manager.is_active = False
        self.assertFalse(can_use_department(manager, "product"))

    def test_manager_model_route_keeps_model_scopes_and_module_revocation(self):
        from portal.model_gateway import GatewayError, selectable_models
        from portal.models import GatewayModel, ModelRoute, ModelRouteOption, Provider

        manager = self.create_user("manager-model-route", "general_manager")
        provider = Provider.objects.create(code="manager-test", name="隔离服务", protocol="openai_chat",
            base_url="https://provider.example/v1", api_key_env="PORTAL_MODEL_KEY_TEST", enabled=True)
        model = GatewayModel.objects.create(name="默认模型", provider=provider, model_name="test", enabled=True)
        restricted = GatewayModel.objects.create(name="受限模型", provider=provider, model_name="restricted", enabled=True)
        route = ModelRoute.objects.create(code="manager-product-test", name="本人方案", model=model,
            module=Module.objects.get(code="product"), enabled=True)
        option = ModelRouteOption.objects.create(route=route, model=restricted, enabled=True)
        option.allowed_roles.add(Role.objects.get(code="hr"))
        self.assertEqual([item["id"] for item in selectable_models(manager, route.code)["models"]],
                         [str(model.public_id)])
        Module.objects.filter(code="product").update(enabled=False)
        with self.assertRaises(GatewayError) as denied:
            selectable_models(manager, route.code)
        self.assertEqual(denied.exception.code, "forbidden")
