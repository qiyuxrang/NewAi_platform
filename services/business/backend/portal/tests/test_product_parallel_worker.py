"""Committed SQLite fixtures exercise the real chapter scheduler and persistence."""
import json
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event, Lock
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.db.models import F
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from portal.model_gateway import GatewayError
from portal.models import Role, User
from portal.product_models import DocumentApproval, DocumentAttempt, DocumentRevision, DocumentStep, DocumentTask
from portal.product_parallel import atomic, db_lock
from portal.product_service import append_revision, approval_authorization, digest
from portal.product_worker import ExecutionError, _generate_families, _store, claim_task


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_WRITING_CONCURRENCY=2, PRODUCT_ENFORCE_OUTPUT_LENGTH=False,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=30, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=30,
                   PRODUCT_STEP_MAX_ATTEMPTS=3, PRODUCT_STEP_RETRY_BASE_SECONDS=1,
                   PRODUCT_STEP_RETRY_MAX_SECONDS=10)
class ProductParallelWorkerTests(TransactionTestCase):
    def setUp(self):
        call_command("seed_portal", stdout=StringIO())
        self.owner = User.objects.create_user("parallel-writer", must_change_password=False)
        self.owner.roles.set(Role.objects.filter(code="product"))
        self.owner.refresh_from_db()
        self.input_payload = {"project": "隔离并行验证", "requirements": "仅使用批准材料", "conditions": [],
                              "items": [{"row_id": "r1", "name": "测试设备", "quantity": "2", "unit": "台"}]}
        self.task = DocumentTask.objects.create(owner=self.owner, title="隔离并行验证", idempotency_key="parallel",
            payload_hash=digest(self.input_payload), state="QUEUED", stage="WRITING", pending_action="generate_outputs")
        self.input_revision = append_revision(self.task, "input", self.input_payload, actor=self.owner)
        self.blueprint_payload = {"purpose": "隔离验证", "audience": "审核人员", "conditions": [],
            "missing": [], "conflicts": [], "template_version": "frozen-original-v1", "chapters": [
                {"id": "t1", "family": "technical-solution", "title": "接口校核", "scope": "接口分析", "source_ids": ["r1"]},
                {"id": "f1", "family": "feasibility", "title": "风险分析", "scope": "风险分析", "source_ids": ["r1"]}]}
        self.save_blueprint()

    def save_blueprint(self):
        self.blueprint = append_revision(self.task, "blueprint", self.blueprint_payload,
            input_hash=self.input_revision.sha256, actor=self.owner)
        self.task.input_version, self.task.blueprint_version = self.input_revision.version, self.blueprint.version
        self.task.save(update_fields=["input_version", "blueprint_version"])
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner,
            decision="approve", sha256=self.blueprint.sha256, authorization=approval_authorization(self.task, self.owner))

    def generate(self):
        self.claim = claim_task()
        self.assertIsNotNone(self.claim)
        return _generate_families(*self.claim, self.task, self.input_revision, self.blueprint,
                                  ["technical-solution", "feasibility"])

    def reply(self, request):
        chapter = request["chapter"]
        text = ("接口校核应核对字段映射、调用边界与异常回执，形成可追溯的联调记录。"
                if chapter["id"] == "t1" else
                "风险分析应分别记录责任归属、条件变化与处置证据，未确认事项保留后续核实方法。")
        return {"content": json.dumps({"chapter_id": chapter["id"], "title": chapter["title"],
                "paragraphs": [text], "source_ids": ["r1"]}), "prompt_tokens": 1, "completion_tokens": 2}

    def test_two_families_overlap_and_each_call_keeps_its_own_response(self):
        barrier = Barrier(2)
        requests, responses = {}, {}
        active, maximum = [0], [0]
        lock = Lock()
        original_blueprint = deepcopy(self.blueprint.payload)

        def network(_owner, _route, messages, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            request = json.loads(messages[1]["content"])
            self.assertEqual(request["writing_brief"]["chapter"], request["chapter"])
            with lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
                requests[digest(request)] = request
            barrier.wait(timeout=5)
            reply = self.reply(request)
            with lock:
                responses[digest(request)] = json.loads(reply["content"])
                active[0] -= 1
            return reply

        with patch("portal.product_worker.generate_for_use", side_effect=network):
            chapters, failures = self.generate()
        self.assertEqual(failures, [])
        self.assertEqual(maximum[0], 2)
        self.assertEqual(set(chapters), {"technical-solution", "feasibility"})
        self.task.refresh_from_db()
        calls = self.task.checkpoint["calls"]
        self.assertEqual({call["call"] for call in calls}, {1, 2})
        self.assertEqual(DocumentAttempt.objects.get(pk=self.claim[2]).model_calls, 2)
        for call in calls:
            self.assertEqual(call["attempt_id"], str(self.claim[2]))
            self.assertTrue(call["response_validated"])
            self.assertEqual(call["response_sha256"], digest(responses[call["input_hash"]]))
        progress = self.task.checkpoint["parallel_writing"]
        self.assertEqual((progress["active_count"], progress["completed_count"], progress["active_model_calls"]), (0, 2, 0))
        self.assertEqual(progress["max_active_model_calls"], 2)
        self.blueprint.refresh_from_db()
        self.assertEqual(self.blueprint.payload, original_blueprint)
        with patch("portal.product_worker.generate_for_use") as network:
            reused, failures = _generate_families(*self.claim, self.task, self.input_revision, self.blueprint,
                                                ["technical-solution", "feasibility"])
        network.assert_not_called()
        self.assertEqual(failures, [])
        self.assertEqual(reused["technical-solution"][0].sha256, chapters["technical-solution"][0].sha256)

    @override_settings(PRODUCT_STEP_RETRY_BASE_SECONDS=0)
    def test_exhausted_transient_failure_preserves_success_and_only_blocks_dependents(self):
        self.blueprint_payload["chapters"].append({"id": "f2", "family": "feasibility", "title": "投资概算",
                                                  "scope": "基于建设方案核算", "source_ids": ["r1"]})
        self.blueprint_payload["chapters"][1]["title"] = "系统设计"
        self.save_blueprint()
        saved = Event()
        calls = []

        def store(*args, **kwargs):
            record = _store(*args, **kwargs)
            if record.family == "technical-solution":
                saved.set()
            return record

        def network(_owner, _route, messages, **kwargs):
            request = json.loads(messages[1]["content"])
            calls.append(request["chapter"]["id"])
            if request["family"] == "feasibility":
                self.assertTrue(saved.wait(5))
                raise GatewayError("timeout")
            return self.reply(request)

        with patch("portal.product_worker.generate_for_use", side_effect=network), patch(
                "portal.product_worker._store", side_effect=store):
            chapters, failures = self.generate()
        self.assertEqual(list(chapters), ["technical-solution"])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].code, "timeout")
        self.assertEqual(set(calls), {"t1", "f1"})
        self.assertEqual(DocumentRevision.objects.filter(task=self.task, kind="chapter").count(), 1)
        self.task.refresh_from_db()
        states = {job["chapter_id"]: job["status"] for job in self.task.checkpoint["parallel_writing"]["jobs"]}
        self.assertEqual(states, {"t1": "completed", "f1": "failed", "f2": "blocked"})
        self.assertEqual(next(call for call in self.task.checkpoint["calls"] if call.get("error_code"))["error_code"], "timeout")
        self.assertEqual(DocumentAttempt.objects.get(pk=self.claim[2]).model_calls, 4)
        self.assertEqual(DocumentStep.objects.get(task=self.task, status="failed").retry_count, 3)

    def test_temporary_busy_retries_locally_after_other_family_saves_without_resetting_budget(self):
        feasibility_saved = Event()
        attempts = 0

        def store(*args, **kwargs):
            record = _store(*args, **kwargs)
            if record.family == "feasibility":
                feasibility_saved.set()
            return record

        def network(_owner, _route, messages, **kwargs):
            nonlocal attempts
            request = json.loads(messages[1]["content"])
            if request["family"] == "technical-solution":
                attempts += 1
                if attempts == 1:
                    raise GatewayError("busy")
                self.assertTrue(feasibility_saved.is_set())
            return self.reply(request)

        with patch("portal.product_worker.generate_for_use", side_effect=network), patch(
                "portal.product_worker._store", side_effect=store):
            chapters, failures = self.generate()
        self.assertEqual(failures, [])
        self.assertEqual(len(chapters), 2)
        self.assertEqual(attempts, 2)
        self.assertEqual(DocumentAttempt.objects.get(pk=self.claim[2]).model_calls, 3)
        step = DocumentStep.objects.get(task=self.task, key__startswith="writing:technical-solution:")
        self.assertEqual((step.status, step.retry_count, step.attempts), ("completed", 1, 2))
        self.task.refresh_from_db()
        self.assertEqual(self.task.attempt_count, 1)
        self.assertEqual(self.task.checkpoint["parallel_writing"]["completed_count"], 2)

    def test_cancellation_waits_for_running_call_and_keeps_saved_chapter(self):
        self.blueprint_payload["chapters"][0]["title"] = "需求分析"
        self.blueprint_payload["chapters"].append({"id": "t2", "family": "technical-solution", "title": "总体架构",
                                                  "scope": "依赖需求", "source_ids": ["r1"]})
        self.save_blueprint()
        entered = Barrier(2)
        cancelled, exited = Event(), Event()
        calls = []

        def store(*args, **kwargs):
            record = _store(*args, **kwargs)
            with atomic():
                DocumentTask.objects.filter(pk=self.task.pk).update(state="CANCELLED", fence=F("fence") + 1)
            cancelled.set()
            return record

        def network(_owner, _route, messages, **kwargs):
            request = json.loads(messages[1]["content"])
            calls.append(request["chapter"]["id"])
            entered.wait(timeout=5)
            if request["family"] == "feasibility":
                self.assertTrue(cancelled.wait(5))
                exited.set()
            return self.reply(request)

        with patch("portal.product_worker.generate_for_use", side_effect=network), patch(
                "portal.product_worker._store", side_effect=store), self.assertRaises(ExecutionError) as caught:
            self.generate()
        self.assertEqual(caught.exception.code, "lease_lost")
        self.assertTrue(exited.is_set())
        self.assertEqual(set(calls), {"t1", "f1"})
        saved = DocumentRevision.objects.get(task=self.task, kind="chapter")
        self.assertEqual(saved.payload["chapter_id"], "t1")

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    def test_parallel_reservation_cannot_exceed_task_call_budget(self):
        with patch("portal.product_worker.generate_for_use", side_effect=lambda _owner, _route, messages, **kw:
                   self.reply(json.loads(messages[1]["content"]))) as network, self.assertRaises(ExecutionError) as caught:
            self.generate()
        self.assertEqual(caught.exception.code, "model_call_limit")
        self.assertEqual(network.call_count, 1)
        self.assertEqual(DocumentAttempt.objects.get(pk=self.claim[2]).model_calls, 1)

    def test_unapproved_source_retries_stay_on_their_call_and_never_replace_success(self):
        requests = {}
        lock = Lock()

        def network(_owner, _route, messages, **kwargs):
            request = json.loads(messages[1]["content"])
            with lock:
                requests[digest(request)] = request
            reply = self.reply(request)
            if request["family"] == "feasibility":
                payload = json.loads(reply["content"])
                payload["source_ids"] = ["not-approved"]
                reply["content"] = json.dumps(payload)
            return reply

        with patch("portal.product_worker.generate_for_use", side_effect=network):
            chapters, failures = self.generate()
        self.assertEqual(list(chapters), ["technical-solution"])
        self.assertEqual([error.code for error in failures], ["invalid_model_output"])
        self.assertEqual(DocumentRevision.objects.filter(task=self.task, kind="chapter").count(), 1)
        self.task.refresh_from_db()
        self.assertEqual(DocumentAttempt.objects.get(pk=self.claim[2]).model_calls, 3)
        for call in self.task.checkpoint["calls"]:
            if requests[call["input_hash"]]["family"] == "feasibility":
                self.assertEqual(call["parse_error"], "invalid_model_output")
                self.assertFalse(call.get("response_validated", False))
            else:
                self.assertTrue(call["response_validated"])
                self.assertNotIn("parse_error", call)

    def test_dependency_receives_saved_prose_and_assembly_keeps_blueprint_order(self):
        self.blueprint_payload["chapters"] = [
            {"id": "t2", "family": "technical-solution", "title": "总体架构", "scope": "设计", "source_ids": ["r1"]},
            {"id": "t1", "family": "technical-solution", "title": "需求分析", "scope": "需求", "source_ids": ["r1"]},
            self.blueprint_payload["chapters"][1]]
        self.save_blueprint()
        requests = []

        def network(_owner, _route, messages, **kwargs):
            request = json.loads(messages[1]["content"])
            requests.append(request)
            if request["chapter"]["id"] == "t2":
                dependency = request["dependency_chapters"][0]
                with db_lock:
                    saved = DocumentRevision.objects.get(task=self.task, kind="chapter", family="technical-solution")
                self.assertEqual(dependency["sha256"], saved.sha256)
                self.assertEqual(dependency["chapter"], saved.payload)
                self.assertIn("不是新增项目事实", request["dependency_boundary"])
            return self.reply(request)

        with patch("portal.product_worker.generate_for_use", side_effect=network):
            chapters, failures = self.generate()
        self.assertEqual(failures, [])
        self.assertEqual([chapter.payload["chapter_id"] for chapter in chapters["technical-solution"]], ["t2", "t1"])
        order = [request["chapter"]["id"] for request in requests]
        self.assertLess(order.index("t1"), order.index("t2"))

    @override_settings(PRODUCT_WRITING_CONCURRENCY=12)
    def test_agent_root_remaining_slot_narrows_pool_without_changing_policy(self):
        from portal.agent_models import AgentConversation, AgentMessage, AgentRequirement, AgentRun, AgentWorkTask
        from portal.agent_runtime import RuntimeGuard, initialize_root
        from portal.product_agent import bind_task

        self.owner.department_code = "product"
        self.owner.save(update_fields=["department_code"])
        self.owner.refresh_from_db()
        conversation = AgentConversation.objects.create(owner=self.owner, department_code="product")
        work = AgentWorkTask.objects.create(owner=self.owner, department_code="product", conversation=conversation,
            goal="并行任务根配额验证", state="running", current_requirement_version=1)
        message = AgentMessage.objects.create(conversation=conversation, work=work, role="user", content=work.goal)
        requirement = AgentRequirement.objects.create(work=work, version=1, user_message=message, content=work.goal)
        root = AgentRun.objects.create(id=conversation.root_run_id, root_run_id=conversation.root_run_id,
            conversation=conversation, work=work, requirement=requirement, state="running",
            deadline_at=timezone.now() + timedelta(hours=1), policy={"max_actions": 30, "max_model_calls": 20,
                "max_tool_calls": 20, "max_launches": 5, "max_concurrent": 2, "max_active_ms": 3600000})
        guard = RuntimeGuard(initialize_root(root.pk, self.owner.pk))
        self.task.state = "DRAFT"
        self.task.save(update_fields=["state"])
        self.task = bind_task(guard, self.task.pk, self.task.version)
        self.task.state = "QUEUED"
        self.task.save(update_fields=["state"])
        DocumentApproval.objects.filter(task=self.task).update(authorization=approval_authorization(self.task, self.owner))
        in_flight = []

        def network(_owner, _route, messages, **kwargs):
            with db_lock:
                current = AgentRun.objects.get(pk=root.pk)
                in_flight.append(len(current.policy["active"]))
            return self.reply(json.loads(messages[1]["content"]))

        with patch("portal.product_worker.generate_for_use", side_effect=network):
            chapters, failures = self.generate()
        self.assertEqual(failures, [])
        self.assertEqual(len(chapters), 2)
        self.task.refresh_from_db()
        self.assertEqual(self.task.checkpoint["parallel_writing"]["concurrency"], 1)
        self.assertEqual(in_flight, [2, 2])
        root.refresh_from_db()
        self.assertEqual(root.policy["max_concurrent"], 2)
        self.assertEqual(root.model_count, 2)
