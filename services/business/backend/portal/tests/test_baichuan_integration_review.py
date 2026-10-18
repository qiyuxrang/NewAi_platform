"""Regression evidence for orchestration boundaries found in AI-T15 review."""
from datetime import timedelta
import json
import hashlib
import io
import uuid
import tempfile
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanAttachment, BaichuanCertificate, BaichuanConversation,
    BaichuanEvidence, BaichuanExport, BaichuanJob, BaichuanMatchSnapshot, BaichuanMessage, BaichuanQualificationRule)
from portal.baichuan_assistant_service import storage_path, submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_exports import enqueue_export
from portal.baichuan_jobs import cancel_job, claim_job, enqueue_job, save_job
from portal.baichuan_matching import match_companies, save_match_snapshot
from portal.baichuan_models import Company
from portal.baichuan_service import BaichuanError
from portal.model_gateway import GatewayError
from .base import PortalTestCase


ROOT = "/api/product/baichuan/assistant/"


def conditions(revision=1):
    return compile_conditions({"schema_version": 1, "revision": revision,
        "must": {"field": "company.city", "op": "eq", "value": "广州市"}})


class IntegrationReviewTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("review-owner", "product")
        self.other = self.create_user("review-other", "product")
        self.temp = tempfile.TemporaryDirectory(prefix="baichuan-review-")
        self.addCleanup(self.temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="review",
            BAICHUAN_STORAGE_ROOT=self.temp.name, BAICHUAN_RESEARCH_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="review", condition_revision=1)
        self.login(self.client, self.owner)

    def queued(self):
        job, _ = enqueue_job(self.owner, kind="query", payload={"condition_revision": 1, "parent_revision": 0},
            idempotency_key="review-query", conversation=self.conversation)
        return job

    def claimed(self):
        return claim_job("review-worker", job_id=self.queued().pk)

    def post(self, url, body):
        return self.client.post(ROOT + url, json.dumps(body), content_type="application/json")

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(BaichuanError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_chat_export_failed_then_http_retry_produces_new_file(self):
        job = self.claimed()
        snapshot = save_match_snapshot(self.owner, job.pk, "review-worker", job.fence, conditions())
        save_job(job.pk, "review-worker", job.fence, status="completed")
        message, export_job, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "导出前10条Excel", "parent_revision": 1, "attachment_ids": [], "client_request_id": "chat-export"})
        self.assertEqual(export_job.message_id, message.pk)
        with patch("portal.baichuan_exports.build_workbook", side_effect=BaichuanError("synthetic_io", "虚构写入失败。")):
            self.assertTrue(run_one("export-failure", export_job.pk))
        export_job.refresh_from_db()
        self.assertEqual(export_job.status, "failed")
        retried = self.post(f"jobs/{export_job.pk}/retry/", {"client_request_id": "chat-export-retry"})
        self.assertEqual(retried.status_code, 202, retried.content)
        retry_id = retried.json()["job"]["id"]
        self.assertTrue(run_one("export-retry", retry_id))
        exported = BaichuanExport.objects.get(job_id=retry_id)
        self.assertEqual(exported.snapshot_id, snapshot.pk)
        self.assertEqual(exported.job.message_id, message.pk)
        self.assertEqual(exported.job.status, "completed")
        self.assertTrue(storage_path(exported.storage_ref).read_bytes().startswith(b"PK"))
        self.assertFalse(BaichuanExport.objects.get(job=export_job).storage_ref)

    def test_expected_failure_keeps_committed_checkpoint_and_partial_result(self):
        job = self.queued()
        def processor(claimed, worker):
            save_job(claimed.pk, worker, claimed.fence,
                checkpoint={"conditions": conditions(), "query_research_done": True, "research_cursor": 9},
                result_ref={"snapshot_id": "synthetic-snapshot"}, counts={"researched": 9})
            raise BaichuanError("synthetic_provider", "虚构提供方失败。", 503)
        with patch("portal.baichuan_assistant_worker.process_query", side_effect=processor):
            run_one("review-worker", job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "partial")
        self.assertEqual(job.checkpoint["research_cursor"], 9)
        self.assertTrue(job.checkpoint["query_research_done"])
        self.assertEqual(job.result_ref["snapshot_id"], "synthetic-snapshot")
        self.assertEqual(job.counts["researched"], 9)

    def test_unexpected_failure_keeps_partial_result_and_raises_for_diagnostics(self):
        job = self.queued()
        def processor(claimed, worker):
            save_job(claimed.pk, worker, claimed.fence,
                checkpoint={"research_cursor": 11}, result_ref={"snapshot_id": "synthetic-snapshot"})
            raise RuntimeError("synthetic crash")
        with patch("portal.baichuan_assistant_worker.process_query", side_effect=processor), self.assertRaises(RuntimeError):
            run_one("review-worker", job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "partial")
        self.assertEqual(job.checkpoint, {"research_cursor": 11})
        self.assertEqual(job.error_code, "processing_failed")

    def test_snapshot_owner_scope_and_revision_boundaries(self):
        job = self.claimed()
        self.assert_code("not_found", save_match_snapshot, self.other, job.pk, "review-worker", job.fence, conditions())
        with override_settings(BAICHUAN_ASSISTANT_SCOPE="other-deployment"):
            self.assert_code("not_found", save_match_snapshot, self.owner, job.pk, "review-worker", job.fence, conditions())
        self.assert_code("revision_conflict", save_match_snapshot, self.owner, job.pk, "review-worker", job.fence, conditions(2))
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())

    def test_cancellation_during_matching_prevents_snapshot_publication(self):
        job = self.claimed()
        def compute(user, compiled):
            cancel_job(user, job.pk)
            return compiled, {}, [], {"confirmed": 0, "candidate": 0, "excluded": 0}
        with patch("portal.baichuan_matching.match_companies", side_effect=compute):
            self.assert_code("stale_lease", save_match_snapshot, self.owner, job.pk, "review-worker", job.fence, conditions())
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())

    def test_budget_expiry_during_matching_prevents_snapshot_publication(self):
        job = self.claimed()
        def compute(user, compiled):
            BaichuanJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(days=2))
            return compiled, {}, [], {"confirmed": 0, "candidate": 0, "excluded": 0}
        with patch("portal.baichuan_matching.match_companies", side_effect=compute):
            self.assert_code("budget_exhausted", save_match_snapshot, self.owner, job.pk, "review-worker", job.fence, conditions())
        job.refresh_from_db()
        self.assertEqual(job.error_code, "budget_exhausted")
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())

    def test_snapshot_same_revision_resumption_is_immutable(self):
        job = self.claimed()
        first = save_match_snapshot(self.owner, job.pk, "review-worker", job.fence, conditions())
        second = save_match_snapshot(self.owner, job.pk, "review-worker", job.fence, conditions())
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BaichuanMatchSnapshot.objects.count(), 1)
        changed = conditions()
        changed["must"]["value"] = "深圳市"
        self.assert_code("revision_conflict", save_match_snapshot, self.owner, job.pk, "review-worker", job.fence, changed)

    def test_parent_pending_does_not_call_model_or_publish_broadened_results(self):
        _, job, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州", "parent_revision": 1, "attachment_ids": [], "client_request_id": "pending-parent"})
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            run_one("review-worker", job.pk)
        model.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.error_code, "parent_conditions_pending")
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())

    def test_running_parent_defers_child_without_spending_attempts_or_starving_others(self):
        parent = self.queued()
        _, child, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州", "parent_revision": 1, "attachment_ids": [], "client_request_id": "queued-parent"})
        self.assertFalse(run_one("child-first", child.pk))
        for unused in range(4):
            self.assertFalse(run_one("child-wait", child.pk))
        child.refresh_from_db()
        self.assertEqual(child.status, "queued")
        self.assertEqual(child.attempts, 0)
        self.assertIsNone(child.lease_expires_at)
        self.assertEqual(child.checkpoint["dependency_job_id"], str(parent.pk))
        claimed_parent = claim_job("parent-running", job_id=parent.pk)
        another = BaichuanConversation.objects.create(owner=self.owner, scope="review")
        independent, _ = enqueue_job(self.owner, kind="query", payload={"condition_revision": 1},
            idempotency_key="independent", conversation=another)
        self.assertEqual(claim_job("other-worker").pk, independent.pk)
        BaichuanJob.objects.filter(pk=claimed_parent.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}) as model:
            self.assertTrue(run_one("parent-reclaimed", parent.pk))
            self.assertTrue(run_one("child-resumed", child.pk))
        child.refresh_from_db()
        self.assertIn(child.status, {"completed", "partial"})
        self.assertEqual(child.attempts, 1)
        self.assertEqual(child.snapshots.get().condition_revision, 2)
        context = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(context["previous_conditions"]["revision"], 1)
        self.assertEqual(context["previous_conditions"]["must"]["value"], "广州市")
        self.assertNotIn("response_format", model.call_args.kwargs)

    def test_revocation_evidence_must_address_the_requested_date(self):
        company = Company.objects.create(name="虚构证书企业", created_by=self.owner, updated_by=self.owner)
        evidence = BaichuanEvidence.objects.create(scope="review", url="https://example.test/cert",
            excerpt="FICTIONAL", content_hash=hashlib.sha256(b"FICTIONAL").hexdigest(), locator={"page": 1},
            verified_on=timezone.localdate(), retrieved_at=timezone.now(), access_status="verified",
            subject={"company_id": str(company.pk), "identity_verified": True, "holder_type": "bidder",
                "authority": "issuer", "scope_verified": True, "revocation_checked": True,
                "revocation_checked_on": timezone.localdate().isoformat()})
        BaichuanQualificationRule.objects.create(category="itss", version=1, evidence=evidence, legal_grades=["2"])
        certificate = BaichuanCertificate.objects.create(company=company, category="itss", grade="2", holder_type="bidder",
            holder_company_id=company.pk, verification_status="verified", assertion_status="PRESENT", evidence=evidence,
            valid_from=timezone.localdate() - timedelta(days=100), valid_until=timezone.localdate() + timedelta(days=100),
            revocation_status="clear")
        tree = {"schema_version": 1, "revision": 1,
            "must": {"field": "qualification", "category": "itss", "op": "grade_exact", "value": "2", "holder": "bidder"}}
        self.assertEqual(match_companies(self.owner, tree)[3]["confirmed"], 1)
        for offset in [-10, 10]:
            tree["as_of"] = {"date": (timezone.localdate() + timedelta(days=offset)).isoformat(), "basis": "user_date"}
            self.assertEqual(match_companies(self.owner, tree)[3]["candidate"], 1)
        historical = (timezone.localdate() - timedelta(days=10)).isoformat()
        historical_evidence = BaichuanEvidence.objects.create(scope=evidence.scope, url=evidence.url,
            excerpt=evidence.excerpt, content_hash=evidence.content_hash, locator=evidence.locator,
            verified_on=evidence.verified_on, retrieved_at=evidence.retrieved_at, access_status=evidence.access_status,
            subject={**evidence.subject, "revocation_as_of": historical})
        certificate.evidence = historical_evidence
        certificate.save()
        tree["as_of"]["date"] = historical
        self.assertEqual(match_companies(self.owner, tree)[3]["confirmed"], 1)

    def test_combined_new_conditions_export_uses_its_new_immutable_snapshot(self):
        self.conversation.condition_revision = 0
        self.conversation.save()
        message, job, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州的，导出前10条Excel，不包含候选", "parent_revision": 0,
             "attachment_ids": [], "client_request_id": "combined-export"})
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}):
            self.assertTrue(run_one("combined-query", job.pk))
        job.refresh_from_db()
        exported = BaichuanExport.objects.get(job_id=job.checkpoint["export_job_id"])
        self.assertEqual(exported.snapshot_id, job.snapshots.get().pk)
        self.assertEqual(exported.job.message_id, message.pk)
        self.assertEqual(exported.selection, {"include_candidates": False, "limit": 10})
        self.assertEqual(exported.snapshot.condition_tree["must"]["value"], "广州市")
        self.assertTrue(run_one("combined-export", exported.job_id))
        exported.refresh_from_db()
        self.assertTrue(storage_path(exported.storage_ref).is_file())
        repeated, repeated_job, created = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州的，导出前10条Excel，不包含候选", "parent_revision": 0,
             "attachment_ids": [], "client_request_id": "combined-export"})
        self.assertFalse(created)
        self.assertEqual(repeated_job.pk, job.pk)
        self.assertEqual(BaichuanExport.objects.count(), 1)

    def test_combined_negative_export_request_does_not_enqueue_export(self):
        self.conversation.condition_revision = 0
        self.conversation.save()
        _, job, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州的，不要导出Excel", "parent_revision": 0,
             "attachment_ids": [], "client_request_id": "no-export"})
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}):
            self.assertTrue(run_one("negative-export", job.pk))
        self.assertFalse(BaichuanExport.objects.exists())

    def test_ambiguous_placeholder_awaits_input_without_research_or_export_then_resumes(self):
        self.conversation.condition_revision = 0
        self.conversation.save()
        _, first, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "找合适的企业并导出Excel", "parent_revision": 0,
             "attachment_ids": [], "client_request_id": "clarify"})
        unclear = {"schema_version": 1, "revision": 1, "unresolved": ["请说明地区或投标人需要的资质。"],
            "must": {"field": "qualification", "category": "未明确条件", "op": "present", "value": "present", "holder": "bidder"}}
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(unclear)}), patch(
                "portal.baichuan_research_runtime.run_query_research") as research:
            self.assertTrue(run_one("clarification", first.pk))
        first.refresh_from_db()
        self.assertEqual(first.status, "awaiting_input")
        self.assertEqual(first.lease_owner, "")
        self.assertIsNone(first.lease_expires_at)
        self.assertIn("conditions", first.checkpoint)
        research.assert_not_called()
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())
        self.assertFalse(BaichuanExport.objects.exists())
        _, second, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州市企业", "parent_revision": 1, "attachment_ids": [], "client_request_id": "clarified"})
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}) as model:
            self.assertTrue(run_one("clarified", second.pk))
        context = json.loads(model.call_args.args[2][1]["content"])
        self.assertEqual(context["previous_conditions"]["must"]["category"], "未明确条件")
        self.assertEqual(second.snapshots.get().condition_tree["unresolved"], [])

    def test_file_requirement_preservation_notice_does_not_make_evidence_unknown(self):
        parent = self.claimed()
        tree = conditions()
        tree["source_refs"] = ["attachment:synthetic:b1"]
        tree["must"]["source_refs"] = list(tree["source_refs"])
        save_match_snapshot(self.owner, parent.pk, "review-worker", parent.fence, tree)
        save_job(parent.pk, "review-worker", parent.fence, status="completed")
        _, child, _ = submit_message(self.owner, self.conversation.pk,
            {"text": "只要广州", "parent_revision": 1, "attachment_ids": [], "client_request_id": "file-refine"})
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}):
            self.assertTrue(run_one("file-refine", child.pk))
        child.refresh_from_db()
        snapshot = child.snapshots.get()
        self.assertEqual(snapshot.condition_tree["must"], tree["must"])
        self.assertEqual(snapshot.condition_tree["unresolved"], [])
        self.assertIn("已保留前轮文件硬性要求。", child.checkpoint["warnings"])

    def test_result_and_xlsx_show_positions_but_hide_private_acquisition_metadata(self):
        job = self.queued()
        company_id = str(uuid.uuid4())
        evidence = BaichuanEvidence.objects.create(scope="review", title="公开证据标题", retrieved_at=timezone.now(),
            import_ref=r"C:\private\imports\customers.xlsx", subject={"company_id": company_id},
            locator={"page": 2, "text_start": 1, "job_id": "private-job-id", "storage_ref": "private-key",
                     "file": r"C:\private\original.pdf"})
        snapshot = BaichuanMatchSnapshot.objects.create(job=job, conversation=self.conversation, condition_revision=1, result_revision=1,
            condition_tree=conditions(), fact_cutoff_at=timezone.now(), results=[{"company_id": company_id,
                "company": {"name": "虚构导出企业"}, "status": "confirmed", "conditions": [{"condition_id": "must",
                    "verdict": "satisfied", "evidence_ids": [str(evidence.pk)]}]}])
        response = self.client.get(ROOT + f"results/{snapshot.pk}/")
        self.assertEqual(response.status_code, 200)
        expected = {"page": 2, "text_start": 1}
        self.assertEqual(response.json()["evidence"][str(evidence.pk)]["locator"], expected)
        exported = enqueue_export(self.owner, snapshot.pk, {"client_request_id": "private-source-export"})
        self.assertTrue(run_one("source-export", exported.pk))
        file = BaichuanExport.objects.get(job=exported)
        import openpyxl
        workbook = openpyxl.load_workbook(io.BytesIO(storage_path(file.storage_ref).read_bytes()))
        self.assertEqual(workbook["逐项依据"]["H8"].value, "公开证据标题")
        self.assertEqual(json.loads(workbook["逐项依据"]["J8"].value), expected)

    def test_result_api_omits_export_only_certificate_metadata_without_mutating_snapshot_or_xlsx(self):
        job = self.queued()
        company_id = str(uuid.uuid4())
        evidence = BaichuanEvidence.objects.create(scope="review", title="合成原证书来源",
            retrieved_at=timezone.now(), url="https://example.test/declared-certificate",
            subject={"company_id": company_id}, locator={"page": 2}, excerpt="合成证号001239，未核实")
        row = {"company_id": company_id, "company": {"name": "合成证号候选企业", "phone": "00123"},
            "company_version": 3, "status": "candidate", "verdict": "unknown", "preferences": [],
            "unresolved": ["尚未核实"], "conditions": [{"condition_id": "must", "verdict": "unknown",
                "reason": "原证书尚未核实", "evidence_ids": [str(evidence.pk)]}],
            "certificate_records": [{"company_id": company_id, "evidence_id": str(evidence.pk),
                "evidence_scope": "review", "condition_ids": ["must"], "certificate_no": "001239",
                "verification_status": "unverified", "holder_type": "manufacturer",
                "holder_name": "合成制造商", "scope_text": "仅供固定证据导出的范围正文" * 100}]}
        snapshot = BaichuanMatchSnapshot.objects.create(job=job, conversation=self.conversation,
            condition_revision=1, result_revision=1, condition_tree=conditions(), fact_cutoff_at=timezone.now(),
            counts={"confirmed": 0, "candidate": 1, "excluded": 0}, results=[row])
        response = self.client.get(ROOT + f"results/{snapshot.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [{key: value for key, value in row.items()
            if key != "certificate_records"}])
        self.assertNotIn(b"certificate_records", response.content)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.results, [row])
        exported = enqueue_export(self.owner, snapshot.pk,
            {"client_request_id": "export-only-certificate", "include_candidates": True})
        self.assertTrue(run_one("export-only-certificate", exported.pk))
        artifact = BaichuanExport.objects.get(job=exported)
        import openpyxl
        workbook = openpyxl.load_workbook(io.BytesIO(storage_path(artifact.storage_ref).read_bytes()), data_only=False)
        self.assertEqual(workbook["逐项依据"]["K8"].value, "001239")
        self.assertEqual(workbook["逐项依据"]["K8"].data_type, "s")
        self.assertEqual(workbook["逐项依据"]["L8"].value, "manufacturer")
        self.assertEqual(workbook["逐项依据"]["T8"].value, "未核实")
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.results, [row])

    def test_refresh_returns_recent_history_and_explicit_truncation(self):
        BaichuanMessage.objects.bulk_create([BaichuanMessage(conversation=self.conversation, role="user",
            content=f"message-{index}", condition_revision=1) for index in range(201)])
        BaichuanAttachment.objects.bulk_create([BaichuanAttachment(conversation=self.conversation, owner=self.owner,
            original_name=f"attachment-{index}.pdf", size_bytes=1, sha256="a" * 64, storage_ref="private") for index in range(101)])
        result = self.client.get(ROOT + f"conversations/{self.conversation.pk}/")
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertTrue(data["has_older_messages"])
        self.assertTrue(data["has_older_attachments"])
        self.assertEqual(data["messages"][-1]["content"], "message-200")
        self.assertEqual(data["messages"][0]["content"], "message-1")
        self.assertEqual(data["attachments"][-1]["original_name"], "attachment-100.pdf")
        self.assertNotIn("storage_ref", data["attachments"][-1])

    def test_malformed_private_storage_key_is_consistent_not_found(self):
        for value in ("../escape", "C:\\private\\source.xlsx", "not-uuid", None, 42):
            self.assert_code("not_found", storage_path, value)

    def test_export_error_without_payload_revision_reaches_failed_and_safe_message(self):
        query = self.queued()
        snapshot = BaichuanMatchSnapshot.objects.create(job=query, conversation=self.conversation,
            condition_revision=1, result_revision=1, condition_tree=conditions(), fact_cutoff_at=timezone.now())
        export_job, _ = enqueue_job(self.owner, kind="export", payload={"snapshot_id": str(snapshot.pk)},
            idempotency_key="legacy-export-no-revision", conversation=self.conversation)
        BaichuanExport.objects.create(owner=self.owner, snapshot=snapshot, job=export_job,
            authorization={"scope": "review", "owner_id": str(self.owner.pk)})
        with patch("portal.baichuan_exports.process_export", side_effect=BaichuanError("synthetic_export_io", "受控导出失败。", 503)):
            self.assertTrue(run_one("legacy-export-worker", export_job.pk))
        export_job.refresh_from_db()
        self.assertEqual(export_job.status, "failed")
        self.assertEqual(export_job.error_code, "synthetic_export_io")
        self.assertEqual(export_job.lease_owner, "")
        self.assertIsNone(export_job.lease_expires_at)
        self.assertFalse(run_one("legacy-export-again", export_job.pk))
        message = self.conversation.messages.get(role="assistant")
        self.assertEqual(message.content, "受控导出失败。")
        self.assertEqual(message.condition_revision, snapshot.condition_revision)

    def test_gateway_timeout_uses_safe_whitelisted_reason_without_upstream_text(self):
        job = self.queued()
        with patch("portal.baichuan_assistant_worker.generate_for_use", side_effect=GatewayError("timeout", message="SECRET-UPSTREAM-RAW")):
            self.assertTrue(run_one("timeout-worker", job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_code, "timeout")
        message = self.conversation.messages.get(role="assistant")
        self.assertIn("超时", message.content)
        self.assertNotIn("尚未配置", message.content)
        self.assertNotIn("SECRET", message.content)

