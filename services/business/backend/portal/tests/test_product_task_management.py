"""Task list actions preserve source authorization, history and worker fencing."""
import hashlib
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.models import AuditEvent
from portal.product_models import DocumentArtifact, DocumentAttempt, DocumentSource, DocumentTask
from portal.product_worker import ExecutionError, _claim_candidate, _finish, _model, _renew, _store, claim_task

from .base import PortalTestCase, json_body
from .test_product_workspace import _ProductWorkspaceFixture


class ProductTaskManagementTests(_ProductWorkspaceFixture, PortalTestCase):
    def pin(self, task, pinned=True, version=None):
        return self.client.post(f"/api/product/tasks/{task.pk}/pin/",
            json_body(expected_version=task.version if version is None else version, pinned=pinned),
            content_type="application/json")

    def delete(self, task, version=None):
        return self.client.delete(f"/api/product/tasks/{task.pk}/",
            json_body(expected_version=task.version if version is None else version),
            content_type="application/json")

    def test_pin_persists_sorts_before_recent_tasks_and_preserves_worker_version(self):
        pinned = self.task("置顶项目", state="RUNNING")
        self.owner.refresh_from_db()
        pinned.fence, pinned.pending_action = 7, "retrieve"
        pinned.lease_until = timezone.now() + timedelta(minutes=5)
        pinned.checkpoint = {"grant_version": self.owner.grant_version}
        pinned.save()
        recent = self.task("较新项目")
        response = self.pin(pinned)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["is_pinned"])
        pinned.refresh_from_db()
        self.assertEqual((pinned.version, pinned.fence, pinned.state), (1, 7, "RUNNING"))
        _renew(pinned.pk, 7)
        # A later worker update controls order inside each pinned/unpinned group.
        DocumentTask.objects.filter(pk=recent.pk).update(updated_at=timezone.now() + timedelta(minutes=1))
        for url in ("/api/product/workspace/", "/api/product/tasks/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, response.content)
            projects = response.json()["projects"] if "workspace" in url else response.json()
            self.assertEqual([item["id"] for item in projects], [str(pinned.pk), str(recent.pk)])
            self.assertTrue(projects[0]["is_pinned"])
        self.assertTrue(self.client.get("/api/product/workspace/").json()["projects"][0]["can_manage"])
        response = self.pin(pinned, False)
        self.assertEqual(response.status_code, 200, response.content)
        projects = self.client.get("/api/product/workspace/").json()["projects"]
        self.assertEqual(projects[0]["id"], str(recent.pk))
        self.assertFalse(projects[1]["is_pinned"])
        self.assertTrue(AuditEvent.objects.filter(actor=self.owner, action="product_task_pin").exists())
        self.assertTrue(AuditEvent.objects.filter(actor=self.owner, action="product_task_unpin").exists())

    def test_deleted_queued_and_running_tasks_are_hidden_and_cannot_publish_late_results(self):
        for state in ("QUEUED", "RUNNING"):
            with self.subTest(state=state):
                task = self.task(state, state=state, reviewer=self.reviewer)
                task.fence, task.pending_action = 3, "retrieve"
                task.lease_until = timezone.now() + timedelta(minutes=5)
                task.retry_after = timezone.now() - timedelta(minutes=1)
                task.checkpoint = {"grant_version": self.owner.grant_version}
                task.save()
                attempt = DocumentAttempt.objects.create(task=task, fence=3, action="retrieve")
                content = b"preserved private history"
                private_file = Path(self.storage.name) / f"{task.pk}.txt"
                private_file.write_bytes(content)
                source = DocumentSource.objects.create(task=task, original_name="source.txt",
                    path=private_file.name, sha256=hashlib.sha256(content).hexdigest(),
                    media_type="text/plain", size=len(content))
                artifact = DocumentArtifact.objects.create(task=task, version=1, path=private_file.name,
                    sha256=source.sha256, blueprint_hash="b" * 64, input_hash="a" * 64, template_hash="c" * 64)
                revisions_before = task.revisions.count()
                response = self.delete(task)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(response.json()["deleted"])
                task.refresh_from_db()
                attempt.refresh_from_db()
                self.assertEqual((task.state, task.fence, task.version), ("CANCELLED", 4, 2))
                self.assertIsNotNone(task.deleted_at)
                self.assertIsNone(task.lease_until)
                self.assertIsNone(task.retry_after)
                self.assertEqual(task.pending_action, "")
                self.assertEqual(attempt.status, "cancelled")
                self.assertIsNotNone(attempt.finished_at)
                self.assertIsNone(claim_task())
                self.assertIsNone(_claim_candidate(task.pk, ""))
                with self.assertRaises(ExecutionError):
                    _store(task.pk, 3, "chapter", {"paragraphs": ["late response"]}, "a" * 64)
                self.assertFalse(_finish(task.pk, 3, attempt.pk, "COMPLETED", "FINAL_REVIEW"))
                self.assertEqual(task.revisions.count(), revisions_before)
                self.assertTrue(DocumentArtifact.objects.filter(pk=artifact.pk).exists())
                self.assertTrue(DocumentSource.objects.filter(pk=source.pk).exists())
                self.assertEqual(private_file.read_bytes(), content)
                for url in (f"/api/product/tasks/{task.pk}/",
                            f"/api/product/sources/{source.pk}/download/",
                            f"/api/product/artifacts/{artifact.pk}/download/"):
                    self.assertEqual(self.client.get(url).status_code, 404, url)
                conversation = self.client.post(f"/api/product/tasks/{task.pk}/conversation/",
                    json_body(expected_version=task.version, message="追加材料"), content_type="application/json")
                self.assertEqual(conversation.status_code, 404)
                self.assertEqual(self.pin(task).status_code, 404)
                self.assertEqual(self.delete(task).status_code, 404)
                self.assertEqual(self.client.get("/api/product/tasks/").json(), [])
                workspace = self.client.get("/api/product/workspace/").json()
                self.assertEqual(workspace["metrics"]["all"], 0)
                self.assertEqual(workspace["projects"], [])
                self.assertEqual(workspace["recent_projects"], [])
                self.assertEqual(workspace["recent_outputs"], [])
                self.assertEqual(self.client.get("/api/product/workspace/outputs/").json()["outputs"], [])
        self.assertEqual(AuditEvent.objects.filter(actor=self.owner, action="product_task_delete").count(), 2)

    def test_only_owner_can_manage_and_source_permissions_still_apply(self):
        task = self.task(reviewer=self.reviewer)
        for user in (self.reviewer, self.other):
            with self.subTest(user=user.username):
                self.login(self.client, user)
                self.assertEqual(self.pin(task).status_code, 404)
                self.assertEqual(self.delete(task).status_code, 404)
        self.login(self.client, self.reviewer)
        project = self.client.get("/api/product/workspace/").json()["projects"][0]
        self.assertFalse(project["can_manage"])
        self.login(self.client, self.owner)
        with patch("portal.product_service.input_authorized", return_value=False):
            self.assertEqual(self.pin(task).status_code, 404)
            self.assertEqual(self.delete(task).status_code, 404)
        task.refresh_from_db()
        self.assertIsNone(task.deleted_at)
        self.assertIsNone(task.pinned_at)

    @override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True)
    @patch("portal.product_worker.generate_for_use")
    def test_delete_during_model_call_discards_the_returned_response(self, model):
        task = self.task("模型等待期间删除", state="QUEUED")
        task.pending_action = "retrieve"
        task.save()
        task_id, fence, attempt_id = claim_task()

        def delete_while_waiting(*args, **kwargs):
            task.refresh_from_db()
            response = self.delete(task)
            self.assertEqual(response.status_code, 200, response.content)
            return {"content": "{}"}

        model.side_effect = delete_while_waiting
        with self.assertRaises(ExecutionError) as lost:
            _model(task_id, fence, attempt_id, "product_writing", {"action": "blueprint", "schema": {}})
        self.assertEqual(lost.exception.code, "lease_lost")
        model.assert_called_once()
        task.refresh_from_db()
        self.assertEqual(task.state, "CANCELLED")
        self.assertEqual(task.checkpoint["calls"][-1]["status"], "started")
        self.assertEqual(DocumentAttempt.objects.get(pk=attempt_id).status, "cancelled")
        self.assertEqual(task.revisions.count(), 1)
        self.assertFalse(task.artifacts.exists())

    def test_versions_and_request_types_are_checked_before_mutation(self):
        task = self.task()
        self.assertEqual(self.pin(task, version=task.version + 1).status_code, 409)
        self.assertEqual(self.delete(task, version=task.version + 1).status_code, 409)
        for pinned in ("true", 1, None):
            self.assertEqual(self.pin(task, pinned).status_code, 400)
        for body in ({}, {"expected_version": True}, {"expected_version": 1, "extra": True}):
            result = self.client.delete(f"/api/product/tasks/{task.pk}/", json_body(**body),
                                        content_type="application/json")
            self.assertEqual(result.status_code, 400, result.content)
        task.refresh_from_db()
        self.assertIsNone(task.deleted_at)
        self.assertIsNone(task.pinned_at)

    def test_completed_task_can_be_hidden_without_removing_history_or_reporting_completion(self):
        task = self.task(state="COMPLETED", stage="FINAL_REVIEW")
        self.assertEqual(self.pin(task).status_code, 200)
        response = self.delete(task)
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual(task.state, "CANCELLED")
        self.assertTrue(task.revisions.exists())
        self.assertEqual(self.client.get("/api/product/workspace/").json()["metrics"]["completed"], 0)

    def test_deleted_task_cannot_be_revealed_by_idempotent_create_replay(self):
        bodies = (("tasks", {"title": "重放项目", "input": {"project": "重放项目", "requirements": "",
                    "items": [], "background": "", "conditions": []}}),
                  ("conversations", {"message": "重放会话"}))
        for route, body in bodies:
            with self.subTest(route=route):
                url = f"/api/product/{route}/"
                response = self.client.post(url, json_body(**body), content_type="application/json",
                                            HTTP_IDEMPOTENCY_KEY=f"replay-{route}")
                self.assertEqual(response.status_code, 201, response.content)
                detail = response.json()["task"] if route == "conversations" else response.json()
                task = DocumentTask.objects.get(pk=detail["id"])
                self.assertEqual(self.delete(task).status_code, 200)
                replay = self.client.post(url, json_body(**body), content_type="application/json",
                                         HTTP_IDEMPOTENCY_KEY=f"replay-{route}")
                self.assertEqual(replay.status_code, 404, replay.content)
                self.assertEqual(DocumentTask.objects.filter(idempotency_key=f"replay-{route}").count(), 1)
