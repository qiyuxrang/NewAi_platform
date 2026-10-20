from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import override_settings
from django.utils import timezone

from portal import knowledge_access as access, product_knowledge_service as knowledge, product_retrieval
from portal.agent_models import AgentProject
from portal.knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant, ProjectMembership
from portal.models import Role
from portal.product_service import ProductError
from .base import ADMIN_PASSWORD, PortalTestCase


class KnowledgeAccessTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("access-owner", "product")
        self.other = self.create_user("access-other", "product")
        self.admin = self.create_admin()
        for user in (self.user, self.other, self.admin):
            user.refresh_from_db()
        self.policy = KnowledgeAccessPolicy.objects.create(department_code="product", enabled=True)

    def grant(self, **values):
        return KnowledgeDocumentGrant.objects.create(policy=self.policy, dataset_id="dataset-1",
            document_id=values.pop("document_id", "document-1"), enabled=True, can_ai_use=True, **values)

    def test_personal_grant_is_live_and_does_not_give_other_accounts_or_admin_access(self):
        row = self.grant(user=self.user)
        snapshot = access.authorize(self.user, "product")
        self.assertEqual(snapshot["datasets"], {"dataset-1": ["document-1"]})
        for user in (self.other, self.admin):
            with self.subTest(user=user.pk), self.assertRaises(access.KnowledgeAccessDenied):
                access.authorize(user, "product")
        row.enabled = False
        row.save()
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.recheck(self.user, "product", snapshot)

    def test_role_and_department_grants_do_not_implicitly_grant_capabilities(self):
        role = Role.objects.get(code="product")
        self.grant(role=role)
        self.grant(recipient_department="hr", document_id="hr-shared")
        self.other.department_code = "hr"
        self.other.save()
        self.other.refresh_from_db()
        self.assertEqual(access.authorize(self.other, "product")["datasets"],
                         {"dataset-1": ["document-1", "hr-shared"]})
        self.other.roles.clear()
        self.other.refresh_from_db()
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.authorize(self.other, "product")

    def test_project_membership_revocation_removes_shared_document_access(self):
        project = AgentProject.objects.create(owner=self.user, department_code="product", name="Test project")
        self.grant(project=project)
        member = ProjectMembership.objects.create(project=project, user=self.other)
        self.assertEqual(access.authorize(self.other, "product")["datasets"], {"dataset-1": ["document-1"]})
        member.enabled = False
        member.save()
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.authorize(self.other, "product")
        self.assertIsNotNone(access.authorize(self.user, "product"))

    def test_read_ai_and_download_are_distinct_and_no_network_for_read_only(self):
        self.grant(user=self.user)
        KnowledgeDocumentGrant.objects.filter(policy=self.policy).update(can_ai_use=False)
        scope = knowledge.authorize(self.user)
        self.assertEqual(scope["datasets"], {"dataset-1": ["document-1"]})
        self.assertEqual(scope["ai_datasets"], {})
        with patch.object(knowledge, "_open") as outbound, self.assertRaises(ProductError):
            knowledge.retrieve("question", [], scope, ("https://example.test", "token", "route"))
        outbound.assert_not_called()
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.authorize(self.user, "product", action="download")

    def test_ai_scope_is_subset_of_read_scope_and_changes_invalidate_old_conversations(self):
        self.grant(user=self.user)
        read_only = self.grant(user=self.user, document_id="read-only")
        read_only.can_ai_use = False
        read_only.save()
        scope = knowledge.authorize(self.user)
        self.assertEqual(scope["ai_datasets"], {"dataset-1": ["document-1"]})
        KnowledgeDocumentGrant.objects.filter(document_id="document-1").update(can_ai_use=False)
        with self.assertRaises(ProductError):
            knowledge.recheck(self.user, scope)

    def test_general_assistant_export_is_separate_and_internal_route_always_blocks_it(self):
        from types import SimpleNamespace
        self.grant(user=self.user)
        scope = knowledge.authorize(self.user)
        self.assertFalse(knowledge.assistant_export_allowed(self.user, scope))
        self.policy.allow_assistant_export = True
        self.policy.save()
        scope = knowledge.authorize(self.user)
        with patch.object(knowledge, "configuration", return_value=("url", "token", "route")), patch(
                "portal.model_gateway._route_for", return_value=(self.user, SimpleNamespace(allow_external_processing=False))):
            self.assertFalse(knowledge.assistant_export_allowed(self.user, scope))
        with patch.object(knowledge, "configuration", return_value=("url", "token", "route")), patch(
                "portal.model_gateway._route_for", return_value=(self.user, SimpleNamespace(allow_external_processing=True))):
            self.assertTrue(knowledge.assistant_export_allowed(self.user, scope))

    def test_expired_grant_and_disabled_policy_never_fall_back_to_legacy(self):
        row = self.grant(user=self.user, expires_at=timezone.now() - timedelta(seconds=1))
        with override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS={str(self.user.pk): {"legacy": ["secret"]}}):
            with self.assertRaises(ProductError):
                knowledge.authorize(self.user)
            row.expires_at = None
            row.save()
            self.policy.enabled = False
            self.policy.save()
            with self.assertRaises(ProductError):
                knowledge.authorize(self.user)

    def test_legacy_mode_is_used_only_without_a_department_policy(self):
        self.assertIsNone(access.authorize(self.user, "engineering"))
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.authorize(self.user, "product")

    @override_settings(KNOWLEDGE_AUTHORIZATION_REQUIRED=True)
    def test_production_without_a_managed_policy_is_denied(self):
        with self.assertRaises(access.KnowledgeAccessDenied):
            access.authorize(self.user, "engineering")

    def test_validation_requires_one_recipient_and_rejects_wildcards(self):
        row = KnowledgeDocumentGrant(policy=self.policy, dataset_id="*", document_id="doc", user=self.user)
        with self.assertRaises(ValidationError):
            row.full_clean()
        row.dataset_id = "dataset-1"
        row.role = Role.objects.get(code="product")
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_generation_scope_can_only_narrow_the_existing_source_approval(self):
        self.grant(user=self.user)
        self.grant(user=self.user, document_id="chat-only")
        with override_settings(PRODUCT_RETRIEVAL_AUTHORIZATIONS={str(self.user.pk): {
                "dataset-1": ["document-1", "legacy-only"]}}):
            self.assertEqual(product_retrieval._scope_for_owner(self.user.pk),
                             [{"dataset_id": "dataset-1", "document_ids": ["document-1"]}])

    def test_admin_configuration_is_accessible_but_does_not_expose_document_contents(self):
        self.login(self.client, self.admin, password=ADMIN_PASSWORD)
        for path in ("knowledgeaccesspolicy", "knowledgedocumentgrant", "projectmembership"):
            response = self.client.get(f"/admin/portal/{path}/")
            self.assertEqual(response.status_code, 200)


class KnowledgeGrantImportTests(PortalTestCase):
    def test_dry_run_and_atomic_cutover_preserve_exact_user_document_scope(self):
        user = self.create_user("legacy-import", "product")
        user.refresh_from_db()
        grants = {str(user.pk): {"dataset-1": ["document-1"]}}
        with override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS=grants):
            call_command("import_knowledge_grants", stdout=StringIO())
            self.assertFalse(KnowledgeAccessPolicy.objects.exists())
            call_command("import_knowledge_grants", apply=True, stdout=StringIO())
            self.assertEqual(access.authorize(user, "product")["datasets"], grants[str(user.pk)])
            with self.assertRaises(CommandError):
                call_command("import_knowledge_grants", apply=True, stdout=StringIO())

    def test_invalid_import_writes_nothing(self):
        with override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS={"999999": {"dataset": ["*"]}}):
            with self.assertRaises(CommandError):
                call_command("import_knowledge_grants", apply=True, stdout=StringIO())
        self.assertFalse(KnowledgeAccessPolicy.objects.exists())

    def test_import_rejects_account_aliases_that_legacy_authorization_never_matched(self):
        user = self.create_user("import-alias", "product")
        for alias in (user.pk, "00" + str(user.pk), "１２"):
            with self.subTest(alias=alias), override_settings(PRODUCT_KNOWLEDGE_AUTHORIZATIONS={
                    alias: {"dataset": ["document"]}}):
                with self.assertRaises(CommandError):
                    call_command("import_knowledge_grants", apply=True, stdout=StringIO())
                self.assertFalse(KnowledgeAccessPolicy.objects.exists())
