from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.agent_api import AgentApiError
from portal.agent_management import _product_task_for_child
from portal.agent_models import AgentConversation, AgentMessage, AgentRequirement, AgentRun, AgentWorkTask
from portal.agent_runtime import AgentDenied
from portal.agent_source_permissions import check_sources
from portal.product_blueprint_knowledge import prepare_blueprint_knowledge
from portal.product_models import DocumentTask
from portal.product_service import append_revision, digest
from portal.product_worker import ExecutionError
from portal.work_summary import _product_items

from .base import PortalTestCase


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_BLUEPRINT_KNOWLEDGE_MODE="ragflow_required")
class ProductDeletedBoundaryTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("deleted-boundary-owner", "product")
        self.owner.department_code = "product"
        self.owner.save(update_fields=["department_code"])
        self.owner.refresh_from_db()
        payload = {"project": "删除边界", "requirements": "网络设计", "background": "",
                   "conditions": [], "items": [], "sources": []}
        self.task = DocumentTask.objects.create(
            owner=self.owner, title="删除边界", idempotency_key="deleted-boundary", payload_hash=digest(payload),
            state="RUNNING", pending_action="knowledge", fence=2,
            lease_until=timezone.now() + timedelta(minutes=5),
            checkpoint={"grant_version": self.owner.grant_version})
        revision = append_revision(self.task, "input", payload, actor=self.owner)
        self.task.input_version = revision.version
        self.task.save(update_fields=["input_version"])

    def delete_task(self, *_args):
        DocumentTask.objects.filter(pk=self.task.pk).update(
            deleted_at=timezone.now(), state="CANCELLED", fence=3,
            pending_action="", lease_until=None, retry_after=None)
        return []

    def test_deleted_task_is_absent_from_work_summary(self):
        self.delete_task()
        self.assertEqual(_product_items(self.owner), ([], [], []))

    def test_deletion_during_search_blocks_the_next_query_and_writeback(self):
        coverage = {"sufficient": False, "missing_domains": [], "missing_writing_topics": []}
        with patch("portal.product_knowledge_service.authorize", return_value={}), \
                patch("portal.product_knowledge_service.configuration", return_value=()), \
                patch("portal.product_knowledge_service.retrieve", return_value=[]), \
                patch("portal.product_blueprint_knowledge.evidence_coverage", return_value=coverage), \
                patch("portal.product_blueprint_knowledge.public_queries", return_value=["first", "second"]), \
                patch("portal.product_blueprint_knowledge.search_public_references", side_effect=self.delete_task) as search:
            with self.assertRaises(ExecutionError) as caught:
                prepare_blueprint_knowledge(self.task.pk, 2)
        self.assertEqual(caught.exception.code, "lease_lost")
        search.assert_called_once_with(["first"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.state, "CANCELLED")
        self.assertEqual(self.task.revisions.count(), 1)

    def test_deleted_agent_source_stops_runtime_source_authorization(self):
        conversation = AgentConversation.objects.create(owner=self.owner, department_code="product")
        work = AgentWorkTask.objects.create(owner=self.owner, department_code="product", conversation=conversation,
                                           goal="删除边界", state="running", current_requirement_version=1)
        message = AgentMessage.objects.create(conversation=conversation, work=work, role="user", content="生成方案")
        requirement = AgentRequirement.objects.create(work=work, version=1, user_message=message, content=message.content)
        root = AgentRun.objects.create(id=conversation.root_run_id, root_run_id=conversation.root_run_id,
                                       conversation=conversation, work=work, requirement=requirement, state="running")
        self.task.agent_root_id, self.task.agent_work_id = str(root.pk), str(work.pk)
        self.task.save(update_fields=["agent_root_id", "agent_work_id"])
        check_sources(root)
        self.delete_task()
        with self.assertRaisesRegex(AgentDenied, "source_authorization_changed"):
            check_sources(root)

    def test_deleted_source_and_artifact_are_unavailable_to_manager(self):
        self.delete_task()
        self.task.refresh_from_db()
        with self.assertRaises(AgentApiError) as caught:
            _product_task_for_child(SimpleNamespace(), self.task)
        self.assertEqual(caught.exception.code, "reference_unavailable")
        self.assertEqual(caught.exception.status, 404)
