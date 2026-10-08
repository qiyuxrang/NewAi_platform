from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from portal import agent_api
from portal.agent_harness import BoundaryMiddleware
from portal.agent_models import AgentConversation, AgentMessage, AgentRequirement, AgentRun, AgentWorkTask
from portal.agent_read_sources import check_read_sources
from portal.agent_runtime import AgentDenied, RuntimeGuard, initialize_root
from portal.agent_tools import AgentTools, tools_for_run
from portal.business_models import BusinessLedgerGrant, BusinessLedgerWorkbook
from portal.hr_recruitment_models import JDVersion, RecruitmentRequest
from portal.model_config import ModelCallLog
from portal.models import Module
from portal.product_agent import check_task_scope
from portal.product_models import DocumentTask
from portal.product_service import ProductError, append_revision, digest

from .base import PortalTestCase


@override_settings(AGENT_PLATFORM_ENABLED=True, PRODUCT_P1_ENABLED=True)
class AgentManagerExecutionTests(TransactionTestCase):
    create_user = PortalTestCase.create_user

    def setUp(self):
        call_command("seed_portal", stdout=StringIO())
        self.manager = self.create_user("gm-agent-owner", "general_manager")
        self.other = self.create_user("gm-agent-other", "product")
        self.other.department_code = "product"
        self.other.save(update_fields=["department_code"])
        self.factory = APIRequestFactory()

    def guard(self, owner=None):
        owner = owner or self.manager
        conversation = AgentConversation.objects.create(owner=owner, department_code=agent_api.department(owner))
        message = AgentMessage.objects.create(conversation=conversation, role="user", content="办理本人业务")
        root = AgentRun.objects.create(id=conversation.root_run_id, root_run_id=conversation.root_run_id,
            conversation=conversation, state="running", deadline_at=timezone.now() + timedelta(minutes=10),
            policy={"max_actions": 30, "max_model_calls": 20, "max_tool_calls": 20,
                    "max_launches": 5, "max_concurrent": 5, "max_active_ms": 600000})
        return RuntimeGuard(initialize_root(root.pk, owner.pk)), message

    def call(self, view, data=None, method="post", **kwargs):
        request = getattr(self.factory, method)("/api/agent/", data=data, format="json")
        force_authenticate(request, user=self.manager)
        return view(request, **kwargs)

    def product_task(self, owner, key):
        task = DocumentTask.objects.create(owner=owner, title=key, idempotency_key=key, payload_hash=digest({}))
        revision = append_revision(task, "input", {"project": key, "requirements": "本人资料", "background": "",
            "items": [], "conditions": [], "sources": []}, actor=owner)
        task.input_version = revision.version
        task.save(update_fields=["input_version"])
        return task

    def test_cross_department_work_keeps_owner_root_and_cumulative_limits(self):
        guard, message = self.guard()
        action = guard.admit("tool", "before-work")
        guard.finish(action)
        before = guard.check()
        registered = tools_for_run(guard, message_id=message.pk)
        boundary = BoundaryMiddleware(guard, business_tools=[tool.name for tool in registered])
        request = SimpleNamespace(tools=registered, override=lambda **values: values)
        tools = AgentTools(guard, message_id=message.pk)
        result = tools.execute("begin_work", {"department_code": "product"}, "begin-product")
        created = tools.create_product_task("本人产品方案", "create-product")
        task = DocumentTask.objects.get(pk=created["task_id"])
        root = guard.check()
        check_task_scope(task, (root, root.work))
        self.assertEqual(root.conversation.department_code, "")
        self.assertEqual((root.work.owner_id, root.work.department_code), (self.manager.pk, "product"))
        self.assertEqual(result, tools.begin_work("begin-product", "product"))
        visible = {tool.name for tool in boundary._model_request(request)["tools"]}
        self.assertIn("product_create_task", visible)
        self.assertNotIn("hr_queue_batch", visible)
        with self.assertRaises(ProductError):
            tools.hr_queue_batch("untrusted-batch", 1, "wrong-domain")
        self.assertEqual(AgentWorkTask.objects.count(), 1)
        product_work = root.work
        root.work.state = "completed"
        root.work.save(update_fields=["state"])
        visible = {tool.name for tool in boundary._model_request(request)["tools"]}
        self.assertIn("begin_work", visible)
        self.assertFalse({"product_create_task", "hr_queue_batch"} & visible)
        second = AgentMessage.objects.create(conversation=root.conversation, role="user", content="查看本人招聘需求")
        snapshot = guard.check()
        AgentTools(guard, message_id=second.pk).begin_work("begin-hr", "hr")
        current = guard.check()
        visible = {tool.name for tool in boundary._model_request(request)["tools"]}
        self.assertIn("hr_queue_batch", visible)
        self.assertNotIn("product_create_task", visible)
        self.assertEqual(current.work.department_code, "hr")
        self.assertEqual((current.pk, current.deadline_at, current.policy["fence"], current.policy["identity"]),
                         (before.pk, before.deadline_at, before.policy["fence"], before.policy["identity"]))
        self.assertEqual((current.action_count, current.tool_count, current.launch_count),
                         (snapshot.action_count, snapshot.tool_count, snapshot.launch_count))
        for work in (product_work, current.work):
            ModelCallLog.objects.create(actor=self.manager, root=current, run=current,
                conversation=current.conversation, work=work, physical_call_id=str(work.pk),
                purpose="business", status="success", duration_ms=1, prompt_tokens=1, completion_tokens=2)
            usage = self.call(agent_api.management_usage, {"department_code": work.department_code}, method="get")
            self.assertEqual(usage.data["calls"], 1)
        Module.objects.filter(code="hr").update(enabled=False)
        with self.assertRaisesRegex(AgentDenied, "authorization_changed"):
            guard.check()

    def test_tool_registration_and_department_claims_do_not_add_grants(self):
        guard, message = self.guard()
        names = {tool.name for tool in tools_for_run(guard, message_id=message.pk)}
        self.assertTrue({"begin_work", "product_create_task", "hr_queue_batch", "gm_read_business"} <= names)
        self.assertFalse(any(name.startswith(("finance_", "engineering_", "cost_")) for name in names))
        grant = BusinessLedgerGrant.objects.create(user=self.manager, department="finance", can_submit=True)
        guard, _ = self.guard()
        names = {tool.name for tool in tools_for_run(guard)}
        self.assertIn("finance_read_drafts", names)
        self.assertNotIn("finance_save_draft", names)
        grant.can_edit = True
        grant.save(update_fields=["can_edit"])
        guard, message = self.guard()
        self.assertIn("finance_save_draft", {tool.name for tool in tools_for_run(guard)})
        with self.assertRaises(ProductError):
            AgentTools(guard, message_id=message.pk).begin_work("unsupported", "engineering")
        employee_guard, employee_message = self.guard(self.other)
        with self.assertRaises(ProductError):
            AgentTools(employee_guard, message_id=employee_message.pk).begin_work("spoof", "hr")
        self.assertFalse(AgentWorkTask.objects.exists())
        Module.objects.filter(code="product").update(enabled=False)
        self.assertNotIn("product_create_task", {tool.name for tool in tools_for_run(guard)})
        with self.assertRaises(ProductError):
            AgentTools(guard, message_id=message.pk).begin_work("disabled", "product")

    def test_gm_read_sources_keep_native_owner_checks_and_revoke_by_module(self):
        guard, _ = self.guard()
        tools = AgentTools(guard)
        task = self.product_task(self.manager, "gm-read-own")
        tools.read_product_task(str(task.pk), "read-product")
        request = RecruitmentRequest.objects.create(created_by=self.manager, updated_by=self.manager,
            position_name="本人岗位", original_text="招聘需求")
        JDVersion.objects.create(request=request, version=1, input_version=1, body="本人JD",
                                 requirements={}, created_by=self.manager)
        tools.hr_read_jd(str(request.pk), "read-hr")
        root = guard.check()
        check_read_sources(root)
        with self.assertRaises(ProductError):
            tools.read_product_task(str(self.product_task(self.other, "other-product").pk), "read-other")
        other_request = RecruitmentRequest.objects.create(created_by=self.other, updated_by=self.other,
            position_name="他人岗位", original_text="他人需求")
        from portal.hr_api import HrError
        with self.assertRaises(HrError):
            tools.hr_read_jd(str(other_request.pk), "read-other-hr")
        Module.objects.filter(code="product").update(enabled=False)
        with self.assertRaisesRegex(AgentDenied, "source_authorization_changed"):
            check_read_sources(root)

    def test_finance_save_requires_real_grant_and_authored_record(self):
        BusinessLedgerGrant.objects.create(user=self.manager, department="finance", can_edit=True)
        guard, message = self.guard()
        tools = AgentTools(guard, message_id=message.pk)
        tools.begin_work("begin-finance", "finance")
        record = {"project_id": "GM-OWN", "project_name": "本人项目", "contract_amount": "100.00",
                  "received_amount": "10.00", "due_date": ""}
        tools.finance_save_draft(record, 0, "save-own")
        self.other.department_code = "finance"
        self.other.save(update_fields=["department_code"])
        BusinessLedgerGrant.objects.create(user=self.other, department="finance", can_edit=True)
        other_guard, other_message = self.guard(self.other)
        other_tools = AgentTools(other_guard, message_id=other_message.pk)
        other_tools.begin_work("begin-other")
        other_record = {**record, "project_id": "OTHER", "project_name": "他人项目"}
        other_tools.finance_save_draft(other_record, 1, "save-other")
        self.assertEqual(tools.finance_read_drafts("read-own")["records"][0]["record"]["project_id"], "GM-OWN")
        self.assertEqual(len(tools.finance_read_drafts("read-own-again")["records"]), 1)
        workbook = BusinessLedgerWorkbook.objects.get(department="finance")
        with self.assertRaises(ProductError):
            tools.finance_save_draft({**other_record, "contract_amount": "200.00"}, workbook.revision, "rewrite-other")
        workbook.refresh_from_db()
        self.assertTrue(all(row["contract_amount"] == "100.00" for row in workbook.records))

    def test_gm_api_work_has_trusted_domain_and_preserves_blank_conversation(self):
        project = self.call(agent_api.projects, {"name": "本人产品", "department_code": "product"})
        self.assertEqual(project.status_code, 201)
        conversation = self.call(agent_api.conversations, {"project_id": project.data["id"]})
        self.assertEqual(conversation.status_code, 201)
        row = AgentConversation.objects.get(pk=conversation.data["id"])
        self.assertEqual(row.department_code, "")
        message = AgentMessage.objects.create(conversation=row, role="user", content="本人工作")
        result = self.call(agent_api.work_list, {"conversation_id": str(row.pk), "message_id": str(message.pk),
                                               "goal": message.content})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.data["department_code"], "product")
        self.assertEqual(self.call(agent_api.work_list, method="get").data["total"], 1)
        self.assertEqual(self.call(agent_api.work_detail, method="get", work_id=result.data["id"]).status_code, 200)
        mismatch = AgentMessage.objects.create(conversation=row, role="user", content="域声明不一致")
        response = self.call(agent_api.work_list, {"conversation_id": str(row.pk), "message_id": str(mismatch.pk),
            "goal": mismatch.content, "department_code": "hr"})
        self.assertEqual(response.status_code, 403)

    def test_legacy_gm_blank_work_remains_readable_correctable_and_cancellable(self):
        guard, message = self.guard()
        root = guard.check()
        work = AgentWorkTask.objects.create(owner=self.manager, conversation=root.conversation,
            department_code="", goal=message.content, state="running", current_requirement_version=1)
        message.work = work
        message.save(update_fields=["work"])
        requirement = AgentRequirement.objects.create(work=work, version=1, user_message=message,
                                                       content=message.content)
        root.work, root.requirement = work, requirement
        root.save(update_fields=["work", "requirement"])
        self.assertEqual(self.call(agent_api.work_detail, method="get", work_id=str(work.pk)).status_code, 200)
        correction = AgentMessage.objects.create(conversation=root.conversation, role="user", content="更正旧工作摘要")
        with patch("portal.agent_api.dispatch_saved_message", return_value={"state": "unavailable"}):
            response = self.call(agent_api.requirements, {"expected_version": 1, "message_id": str(correction.pk),
                "content": correction.content}, work_id=str(work.pk))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["version"], 2)
        response = self.call(agent_api.cancel_work, {"expected_version": 2, "request_id": "cancel-legacy"},
                             work_id=str(work.pk))
        self.assertEqual(response.status_code, 200)
