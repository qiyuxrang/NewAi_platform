"""File requirements need their own authorized, recoverable source locator."""
from copy import deepcopy
import json
import tempfile
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.baichuan_assistant_models import BaichuanAttachment, BaichuanConversation, BaichuanMessage, BaichuanMatchSnapshot
from portal.baichuan_assistant_service import submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_jobs import claim_job, save_job
from portal.baichuan_source_guard import missing_hard_sources
from django.utils import timezone
from .base import PortalTestCase


REF = "attachment:synthetic:b4"
TEXT = "message:synthetic"


def node(refs=()):
    return {"field": "qualification", "category": "electronic", "op": "grade_exact",
            "value": "2", "holder": "bidder", "source_refs": list(refs)}


def tree(leaf=None):
    return compile_conditions({"schema_version": 1, "revision": 1, "source_refs": [REF], "must": leaf or node()})


class SourceAttributionPureTests(SimpleTestCase):
    def test_top_level_citation_does_not_fill_missing_leaf(self):
        original = tree()
        self.assertEqual(len(missing_hard_sources(original, current_refs={REF})), 1)
        self.assertFalse(original["must"]["source_refs"])

    def test_exact_authorized_leaf_reference_is_accepted(self):
        self.assertFalse(missing_hard_sources(tree(node([REF])), current_refs={REF}))

    def test_mixed_text_condition_uses_only_real_message_ref(self):
        city = {"field": "company.city", "op": "eq", "value": "西安市", "source_refs": [TEXT]}
        compiled = tree({"all": [city, node([REF])]})
        self.assertFalse(missing_hard_sources(compiled, current_refs={REF}, text_ref=TEXT))
        self.assertTrue(missing_hard_sources(compiled, current_refs={REF}, text_ref="message:other"))

    def test_prior_text_condition_can_survive_new_attachment(self):
        previous = tree({"field": "company.city", "op": "eq", "value": "西安市"})
        previous["source_refs"] = []
        current = tree({"all": [previous["must"], node([REF])]})
        self.assertFalse(missing_hard_sources(current, current_refs={REF}, previous=previous))

    def test_legacy_unattributed_file_cannot_certify_its_own_omission(self):
        self.assertTrue(missing_hard_sources(tree(), current_refs={REF}, previous=tree()))

    def test_prior_sourced_leaf_survives_without_fabricated_current_citation(self):
        self.assertFalse(missing_hard_sources(tree(), current_refs={REF}, previous=tree(node([REF]))))

    def test_nested_or_not_hard_leaves_are_not_skipped(self):
        compiled = tree({"any": [node([REF]), {"not": node()}]})
        self.assertEqual(len(missing_hard_sources(compiled, current_refs={REF})), 1)

    def test_text_only_requests_do_not_require_file_citations(self):
        self.assertFalse(missing_hard_sources(tree(), current_refs=set(), text_ref=TEXT))


class SourceAttributionWorkerTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("source-guard-owner", "product")
        temp = tempfile.TemporaryDirectory(prefix="source-guard-"); self.addCleanup(temp.cleanup)
        settings = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="source-test",
            BAICHUAN_STORAGE_ROOT=temp.name, BAICHUAN_RESEARCH_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        settings.enable(); self.addCleanup(settings.disable)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="source-test")
        self.attachment = BaichuanAttachment.objects.create(owner=self.owner, conversation=self.conversation,
            original_name="synthetic-table.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=4, sha256="a"*64, storage_ref=str(uuid.uuid4()), parse_status="completed",
            extracted_text="投标人必须具备电子与智能化精确二级。",
            locators=[{"id": "b4", "text": "投标人必须具备电子与智能化精确二级。", "location": {"table": 1, "row": 2}}])
        self.ref = f"attachment:{self.attachment.pk}:b4"

    def enqueue(self, text="", attachments=None):
        self.conversation.refresh_from_db()
        _, job, _ = submit_message(self.owner, self.conversation.pk, {"text": text,
            "attachment_ids": [str(self.attachment.pk)] if attachments is None else attachments,
            "parent_revision": self.conversation.condition_revision, "client_request_id": uuid.uuid4().hex})
        return job

    def execute(self, job, compiled):
        compiled = deepcopy(compiled); compiled["source_refs"] = [self.ref]
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(compiled)}) as gateway, \
                patch("portal.baichuan_assistant_worker.run_parser") as parser:
            run_one("source-worker", job.pk)
        gateway.assert_called_once(); parser.assert_not_called(); job.refresh_from_db()
        return job, gateway.call_args.args[2]

    def test_missing_leaf_waits_without_snapshot_or_export_and_releases_lease(self):
        job, messages = self.execute(self.enqueue("导出前10条Excel"), tree())
        self.assertEqual(job.status, "awaiting_input")
        self.assertFalse(job.snapshots.exists())
        self.assertFalse(self.conversation.jobs.filter(kind="export").exists())
        self.assertIsNone(job.lease_expires_at)
        self.assertFalse(job.lease_owner)
        self.assertEqual(job.checkpoint["pending_attachment_ids"], [str(self.attachment.pk)])
        self.assertFalse(job.checkpoint["conditions"]["must"]["source_refs"])
        context = json.loads(messages[1]["content"])
        self.assertEqual(context["documents"][0]["blocks"][0]["source_ref"], self.ref)
        self.assertEqual(context["documents"][0]["blocks"][0]["location"], {"table": 1, "row": 2})

    def test_mixed_city_and_file_preserves_separate_provenance_and_cancellation(self):
        job = self.enqueue("只要西安市")
        city = {"field": "company.city", "op": "eq", "value": "西安市", "source_refs": [f"message:{job.message_id}"]}
        job, messages = self.execute(job, tree({"all": [city, node([self.ref])]}))
        self.assertEqual(job.status, "completed")
        original = deepcopy(job.snapshots.get().condition_tree)
        self.assertEqual(json.loads(messages[1]["content"])["text_source_ref"], f"message:{job.message_id}")
        guards = job.checkpoint["file_requirements"]
        self.assertEqual(len(guards), 1)
        self.assertEqual(guards[0]["node"]["category"], "electronic")
        cancelled = self.enqueue("取消文件中的电子与智能化硬性要求", attachments=[])
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:
            run_one("source-worker", cancelled.pk)
        model.assert_not_called(); cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, "completed")
        self.assertEqual(cancelled.snapshots.get().condition_tree["must"], city)
        self.assertEqual(job.snapshots.get().condition_tree, original)

    def test_forged_message_or_foreign_attachment_reference_fails_closed(self):
        foreign_owner = self.create_user("source-other-owner", "product")
        foreign_conversation = BaichuanConversation.objects.create(owner=foreign_owner, scope="source-test")
        foreign_message = BaichuanMessage.objects.create(conversation=foreign_conversation, role="user",
            content="只要西安市", condition_revision=1)
        for ref in ("message:" + str(uuid.uuid4()), f"message:{foreign_message.pk}", "attachment:" + str(uuid.uuid4()) + ":b4"):
            with self.subTest(ref=ref):
                self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="source-test")
                self.attachment.conversation = self.conversation; self.attachment.save(update_fields=["conversation"])
                job, _ = self.execute(self.enqueue("只要西安市"), tree(node([ref])))
                self.assertEqual(job.status, "failed")
                self.assertEqual(job.error_code, "invalid_model_sources")
                self.assertFalse(job.snapshots.exists())

    def test_followup_reuses_pending_file_once_and_keeps_original_failed_conditions(self):
        first, _ = self.execute(self.enqueue(), tree())
        frozen = deepcopy(first.checkpoint)
        continued, _ = self.execute(self.enqueue("按附件和本轮文字逐项标注来源后继续", attachments=[]), tree(node([self.ref])))
        self.assertEqual(continued.status, "completed")
        self.assertEqual(continued.payload["attachment_ids"], [str(self.attachment.pk)])
        self.assertNotIn("source_attribution_question", continued.checkpoint)
        first.refresh_from_db(); self.assertEqual(first.checkpoint, frozen)

    def test_recovered_question_checkpoint_never_calls_model_again(self):
        job = self.enqueue()
        claimed = claim_job("source-recover", job_id=job.pk)
        compiled = tree()
        save_job(job.pk, "source-recover", claimed.fence, checkpoint={"conditions": compiled,
            "source_attribution_question": "缺少逐项来源", "pending_attachment_ids": [str(self.attachment.pk)]})
        from portal.baichuan_assistant_worker import process_query
        with patch("portal.baichuan_assistant_worker.generate_for_use") as gateway:
            process_query(claimed, "source-recover")
        gateway.assert_not_called(); job.refresh_from_db()
        self.assertEqual(job.status, "awaiting_input")
        self.assertFalse(job.snapshots.exists())

    def test_retry_with_old_unattributed_checkpoint_waits_without_replaying_model(self):
        job = self.enqueue()
        claimed = claim_job("source-recover", job_id=job.pk)
        compiled = tree(); compiled["source_refs"] = [self.ref]
        save_job(job.pk, "source-recover", claimed.fence, checkpoint={"conditions": compiled,
            "file_requirements": [{"node": compiled["must"], "known": False}]})
        from portal.baichuan_assistant_worker import process_query
        with patch("portal.baichuan_assistant_worker.generate_for_use") as gateway:
            process_query(claimed, "source-recover")
        gateway.assert_not_called(); job.refresh_from_db()
        self.assertEqual(job.status, "awaiting_input")
        self.assertFalse(job.snapshots.exists())
        self.assertEqual(job.checkpoint["pending_attachment_ids"], [str(self.attachment.pk)])

    def test_legacy_unattributed_file_guard_omitted_by_followup_cannot_bypass_gate(self):
        self.assert_legacy_guard_waits(with_attachment=False)

    def test_new_upload_cannot_hide_merged_legacy_unattributed_file_guard(self):
        self.assert_legacy_guard_waits(with_attachment=True)

    def assert_legacy_guard_waits(self, *, with_attachment):
        old = self.enqueue("按附件原要求")
        claimed = claim_job("legacy-source", job_id=old.pk)
        legacy = tree(); legacy["source_refs"] = [self.ref]
        save_job(old.pk, "legacy-source", claimed.fence, status="completed", checkpoint={"conditions": legacy,
            "file_requirements": [{"node": legacy["must"], "known": False}]})
        snapshot = BaichuanMatchSnapshot.objects.create(job=old, conversation=self.conversation,
            condition_revision=1, result_revision=1, condition_tree=legacy, fact_cutoff_at=timezone.now(),
            counts={"confirmed": 0, "candidate": 0, "excluded": 0})
        continued = self.enqueue("只要西安市", attachments=[str(self.attachment.pk)] if with_attachment else [])
        city = {"field": "company.city", "op": "eq", "value": "西安市",
                "source_refs": [f"message:{continued.message_id}"]}
        continued, _ = self.execute(continued, tree(city))
        self.assertEqual(continued.status, "awaiting_input")
        self.assertFalse(continued.snapshots.exists())
        self.assertEqual(continued.checkpoint["pending_attachment_ids"], [str(self.attachment.pk)])
        snapshot.refresh_from_db(); self.assertEqual(snapshot.condition_tree, legacy)
