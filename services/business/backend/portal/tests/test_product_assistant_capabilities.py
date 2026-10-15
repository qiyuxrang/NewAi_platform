"""Assistant capability isolation; no live provider or knowledge requests."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import force_authenticate

from portal import product_knowledge_agent as agent
from portal import product_knowledge_api as api
from portal import product_knowledge_service as service
from portal.model_gateway import GatewayError
from portal.business_models import BusinessLedgerGrant
from portal.models import User
from portal.product_service import ProductError

from .base import PortalTestCase
from .test_product_knowledge_api import _ProductKnowledgeApiFixture
from .test_product_knowledge_service import CONFIG, Response


def answer(*args, **kwargs):
    kwargs["recheck"]()
    yield {"delta": "你好"}
    yield {"result": {"answer": "你好", "sources": [], "activities": [],
                      "assistant": True, "web_search": False, "outcome": "answered",
                      "runtime": "deepseek_harness"}}


class AssistantCapabilityTests(_ProductKnowledgeApiFixture, PortalTestCase):
    def test_all_department_assistants_keep_document_and_product_grants_separate(self):
        from portal.product_service import product_user_allowed
        for role in ("hr", "engineering", "finance", "general_manager", "product"):
            with self.subTest(role=role):
                self.owner = self.create_user("assistant-" + role, *(() if role == "finance" else (role,)))
                if role == "finance":
                    self.owner.department_code = "finance"
                    self.owner.save(update_fields=["department_code"])
                    BusinessLedgerGrant.objects.create(user=self.owner, department="finance", can_edit=True)
                self.owner.refresh_from_db()
                status = self.request(api.status)
                self.assertEqual(status.status_code, 200)
                self.assertFalse(status.data["knowledge"]["available"])
                item = self.create()
                with patch.object(agent, "run", side_effect=answer):
                    response, result = self.assistant_request(item)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(result["turns"][0]["answer"], "你好")
                self.assertEqual(self.request(api.datasets).status_code, 403)
                self.assertEqual(self.request(api.conversation, conversation=item, user=self.other).status_code, 404)
                self.assertEqual(product_user_allowed(self.owner), role in {"product", "general_manager"})
                self.grants[str(self.owner.pk)] = {"dataset-1": ["document-1"]}
                self.assertEqual(service.authorize(self.owner)["datasets"], self.grants[str(self.owner.pk)])
                self.outbound.side_effect = lambda *args: Response(
                    json.dumps({"code": 0, "data": [{"id": "dataset-1", "name": "授权资料"}]}).encode())
                self.assertEqual(self.request(api.datasets).status_code, 200)
                self.assertEqual(self.request(api.conversation, conversation=item).status_code, 403)

    def test_department_access_rechecks_current_roles_modules_and_finance_grant(self):
        from portal.models import Module
        for revoked in ("role", "module", "inactive", "password", "finance"):
            with self.subTest(revoked=revoked):
                user = self.create_user("recheck-" + revoked, *(("hr",) if revoked != "finance" else ()))
                if revoked == "finance":
                    user.department_code = "finance"
                    user.save(update_fields=["department_code"])
                    BusinessLedgerGrant.objects.create(user=user, department="finance", can_edit=True)
                user.refresh_from_db()
                scope = service.authorize(user, allow_empty=True)
                # Deliberately keep the request object stale after the DB change.
                if revoked == "role":
                    user.roles.clear()
                elif revoked == "module":
                    Module.objects.filter(code="hr").update(enabled=False)
                elif revoked == "finance":
                    BusinessLedgerGrant.objects.filter(user=user).delete()
                else:
                    User.objects.filter(pk=user.pk).update(**{"is_active": False} if revoked == "inactive"
                                                          else {"must_change_password": True})
                with self.assertRaises(ProductError) as caught:
                    service.recheck(user, scope)
                self.assertEqual(caught.exception.code, "forbidden")
                Module.objects.filter(code="hr").update(enabled=True)

    def assistant_request(self, item, *, stream=False, **changes):
        payload = {"question": "你好", "version": 0, "request_id": str(uuid.uuid4()),
                   "assistant": True, **changes}
        if stream:
            payload["stream"] = True
        request = self.factory.post("/api/product/knowledge/", payload, format="json")
        force_authenticate(request, user=self.owner)
        response = api.conversation(request, conversation_id=item.pk)
        if response.streaming:
            events = [json.loads(line[6:]) for chunk in response.streaming_content
                      for line in chunk.decode().splitlines() if line.startswith("data: ")]
            return response, events
        response.render()
        return response, response.data

    def test_allow_empty_is_opt_in_and_never_skips_identity_or_session_checks(self):
        for raw in (None, {}):
            with self.subTest(raw=raw):
                if raw is None:
                    self.grants.pop(str(self.owner.pk), None)
                else:
                    self.grants[str(self.owner.pk)] = raw
                with self.assertRaises(ProductError) as caught:
                    service.authorize(self.owner)
                self.assertEqual(caught.exception.code, "scope_revoked")
                scope = service.authorize(self.owner, allow_empty=True)
                self.assertEqual(scope["datasets"], {})
                service.recheck(self.owner, scope)
        for user in (self.denied, self.owner):
            with self.subTest(user=user.pk):
                if user == self.owner:
                    User.objects.filter(pk=user.pk).update(session_version=user.session_version + 1)
                with self.assertRaises(ProductError) as caught:
                    service.authorize(user, allow_empty=True)
                self.assertEqual(caught.exception.code, "forbidden")

    def test_empty_snapshot_is_revoked_if_knowledge_scope_is_added(self):
        self.grants.pop(str(self.owner.pk))
        scope = service.authorize(self.owner, allow_empty=True)
        self.grants[str(self.owner.pk)] = {"dataset-1": ["document-1"]}
        with self.assertRaises(ProductError) as caught:
            service.recheck(self.owner, scope)
        self.assertEqual(caught.exception.code, "scope_revoked")

    def test_status_separates_missing_grant_or_config_from_assistant_and_web(self):
        web = {"available": False, "code": "web_disabled", "help": "未启用联网"}
        runtime = {"available": True, "code": "ready", "runtime": "deepseek_harness"}
        with patch.object(agent, "web_status", return_value=web), \
                patch.object(agent, "runtime_status", return_value=runtime):
            for failure in ("no_grant", "disabled", "unconfigured"):
                with self.subTest(failure=failure):
                    self.grants[str(self.owner.pk)] = {} if failure == "no_grant" else {"dataset-1": ["document-1"]}
                    self.configuration.side_effect = (None if failure == "no_grant" else
                                                     ProductError(failure, "知识不可用", 503))
                    response = self.request(api.status)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.data["available"])
                    self.assertTrue(response.data["assistant"]["available"])
                    self.assertFalse(response.data["knowledge"]["available"])
                    self.assertEqual(response.data["knowledge"]["code"],
                                     "knowledge_not_authorized" if failure == "no_grant" else failure)
                    self.assertTrue(response.data["knowledge"]["help"])
                    self.assertEqual(response.data["web_search"], web)
                    self.assertTrue(response.data["authorization_revision"])
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_model_unavailable_keeps_status_and_conversation_history_accessible(self):
        item = self.create()
        self.assistant_ready.side_effect = ProductError("unconfigured", "模型未配置", 503)
        with patch.object(agent, "runtime_status", return_value={"available": True, "runtime": "deepseek_harness"}):
            status = self.request(api.status)
        self.assertTrue(status.data["available"])
        self.assertFalse(status.data["assistant"]["available"])
        self.assertEqual(status.data["assistant"]["code"], "unconfigured")
        self.assertTrue(status.data["knowledge"]["available"])
        self.assertEqual(self.request(api.conversation, conversation=item).status_code, 200)
        response, _ = self.assistant_request(item)
        self.assertEqual(response.status_code, 503)
        self.assert_unchanged(item)
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_runtime_unavailable_is_reported_separately_from_knowledge(self):
        runtime = {"available": False, "code": "runtime_unavailable", "help": "运行时未配置",
                   "runtime": "deepseek_harness"}
        with patch.object(agent, "runtime_status", return_value=runtime):
            response = self.request(api.status)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["assistant"], runtime)
        self.assertTrue(response.data["knowledge"]["available"])
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_no_knowledge_grant_supports_conversation_lifecycle_and_send(self):
        self.grants.pop(str(self.owner.pk))
        self.ready.side_effect = ProductError("disabled", "知识未启用", 503)
        self.configuration.side_effect = ProductError("disabled", "知识未启用", 503)
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                item = self.create()
                self.assertEqual(item.scope["datasets"], {})
                with patch.object(agent, "run", side_effect=answer) as run:
                    response, result = self.assistant_request(item, stream=streaming)
                self.assertEqual(response.status_code, 200)
                done = result[-1]["done"] if streaming else result
                self.assertEqual(done["version"], 1)
                self.assertEqual(done["turns"][0]["answer"], "你好")
                self.assertIsNone(run.call_args.args[4])
                self.assertEqual(run.call_args.kwargs["purpose_code"], CONFIG[2])
                self.assertEqual(run.call_args.args[3]["datasets"], {})
                self.assertEqual(self.request(api.conversation, conversation=item).status_code, 200)
                archived = self.request(api.archive_conversation, "post", {"version": 1}, conversation=item)
                self.assertEqual(archived.status_code, 200)
                listing = self.request(api.archived_conversations)
                self.assertIn(str(item.pk), [row["id"] for row in listing.data["conversations"]])
                restored = self.request(api.restore_conversation, "post", {"version": 2}, conversation=item)
                self.assertEqual(restored.status_code, 200)
        self.assertNotIn(str(self.owner.pk), self.grants)
        self.ready.assert_not_called()
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_existing_grants_with_unavailable_knowledge_send_without_knowledge_config(self):
        self.configuration.side_effect = ProductError("unconfigured", "知识未配置", 503)
        item = self.create()
        with patch.object(agent, "run", side_effect=answer) as run:
            response, _ = self.assistant_request(item)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(run.call_args.args[4])
        self.assertEqual(run.call_args.kwargs["purpose_code"], CONFIG[2])
        self.assertEqual(self.grants[str(self.owner.pk)], {"dataset-1": ["document-1"]})
        self.outbound.assert_not_called()

    def test_old_scope_history_hidden_and_unreadable_after_grant_removal(self):
        old = self.create()
        old.title = "SECRET_OLD_TITLE"
        old.turns = [{"question": "SECRET_OLD_QUESTION", "request_id": str(uuid.uuid4()),
                      "answer": "SECRET_OLD_ANSWER", "sources": [{"document_id": "document-1"}]}]
        old.save(update_fields=["title", "turns"])
        self.grants.pop(str(self.owner.pk))
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                listing = self.request(api.conversations)
                self.assertEqual(listing.data["conversations"], [])
                self.assertNotIn("SECRET_OLD", listing.content.decode())
                response = self.request(api.conversation, conversation=old)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["code"], "scope_revoked")
                self.assertNotIn("SECRET_OLD", response.content.decode())
        fresh = self.create()
        self.assertEqual(fresh.scope["datasets"], {})
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_legacy_send_and_all_knowledge_document_endpoints_remain_strict(self):
        self.grants.pop(str(self.owner.pk))
        item = self.create()
        legacy = self.send(item)
        self.assertEqual(legacy.status_code, 403)
        self.assertEqual(legacy.data["code"], "scope_revoked")
        self.assert_unchanged(item)
        endpoints = ((api.datasets, {}), (api.retrieve, {}),
                     (api.documents, {"dataset_id": "dataset-1"}),
                     *((view, {"dataset_id": "dataset-1", "document_id": "document-1"})
                       for view in (api.chunks, api.document_preview, api.document_pages, api.document_download)))
        for view, kwargs in endpoints:
            with self.subTest(view=view.__name__):
                request = (self.factory.post("/api/product/knowledge/", {"question": "设备"}, format="json")
                           if view == api.retrieve else self.factory.get("/api/product/knowledge/"))
                force_authenticate(request, user=self.owner)
                response = view(request, **kwargs)
                self.assertEqual(response.status_code, 403)
        self.outbound.assert_not_called()
        self.gateway.assert_not_called()

    def test_midstream_grant_session_and_scope_changes_stop_release_and_save(self):
        for change in ("remove_grant", "add_grant", "grant_version", "session_version"):
            with self.subTest(change=change):
                self.owner.refresh_from_db()
                self.grants[str(self.owner.pk)] = {} if change == "add_grant" else {"dataset-1": ["document-1"]}
                item = self.create()

                def revoke(*args, **kwargs):
                    yield {"delta": "允许的开头"}
                    if change == "remove_grant":
                        self.grants.pop(str(self.owner.pk))
                    elif change == "add_grant":
                        self.grants[str(self.owner.pk)] = {"dataset-1": ["document-1"]}
                    else:
                        User.objects.filter(pk=self.owner.pk).update(**{change: getattr(self.owner, change) + 1})
                    yield {"delta": "SECRET_AFTER_REVOCATION"}

                with patch.object(agent, "run", side_effect=revoke):
                    response, events = self.assistant_request(item, stream=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(events[0], {"delta": "允许的开头"})
                self.assertEqual(events[-1]["error"]["code"],
                                 "forbidden" if change.endswith("version") else "scope_revoked")
                self.assertNotIn("SECRET_AFTER_REVOCATION", json.dumps(events))
                self.assert_unchanged(item)
        self.outbound.assert_not_called()

    def test_model_failure_does_not_create_grants_or_commit_partial_answer(self):
        self.grants.pop(str(self.owner.pk))
        item = self.create()

        def broken(*args, **kwargs):
            yield {"delta": "部分回答"}
            raise GatewayError("upstream_error")

        with patch.object(agent, "run", side_effect=broken):
            _, events = self.assistant_request(item, stream=True)
        self.assertEqual(events[-1]["error"]["code"], "upstream_error")
        self.assertNotIn(str(self.owner.pk), self.grants)
        self.assertEqual(service.authorize(self.owner, allow_empty=True)["datasets"], {})
        self.assert_unchanged(item)
        self.outbound.assert_not_called()


class AssistantRouteIsolationTests(SimpleTestCase):
    def test_assistant_route_needs_model_and_ai_switch_but_no_knowledge_configuration(self):
        route = SimpleNamespace(module=SimpleNamespace(code="product"), model=object())
        with override_settings(PRODUCT_KNOWLEDGE_ENABLED=False, PRODUCT_KNOWLEDGE_URL="",
                               PRODUCT_KNOWLEDGE_TOKEN_ENV="", PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED=True,
                               PRODUCT_KNOWLEDGE_MODEL_ROUTE=CONFIG[2],
                               MODEL_GATEWAY_URL="https://gateway.example.test",
                               MODEL_GATEWAY_ALLOWED_URLS=("https://gateway.example.test",),
                               MODEL_GATEWAY_TOKEN="x" * 40), \
                patch.object(service, "configuration", side_effect=AssertionError("knowledge config consulted")), \
                patch("portal.model_gateway._route_for", return_value=(None, route)), \
                patch("portal.model_gateway._model_config", return_value={"model": {"timeout_seconds": 120}}), \
                patch("portal.model_gateway._request_gateway") as outbound:
            self.assertEqual(service.assistant_ready(object()), CONFIG[2])
            for changes in ({"PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED": False},
                            {"PRODUCT_KNOWLEDGE_MODEL_ROUTE": ""}, {"MODEL_GATEWAY_TOKEN": ""}):
                with self.subTest(changes=changes), override_settings(**changes), self.assertRaises(ProductError):
                    service.assistant_ready(object())
            route.module.code = "hr"
            with self.assertRaises(ProductError):
                service.assistant_ready(object())
            outbound.assert_not_called()
