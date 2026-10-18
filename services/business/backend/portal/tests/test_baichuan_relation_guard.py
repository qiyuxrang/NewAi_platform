"""Source-scoped relation claims, with an inert gateway and isolated database."""
from copy import deepcopy
import json
import tempfile
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from portal.baichuan_assistant_models import BaichuanAttachment, BaichuanConversation
from portal.baichuan_assistant_service import submit_message
from portal.baichuan_assistant_worker import run_one, SYSTEM
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_jobs import claim_job, save_job
from portal.baichuan_relation_guard import check_relations, relation_key
from .base import PortalTestCase


REF = "attachment:synthetic:b1"


def predicate(op="grade_at_least", category="ccrc", holder="manufacturer", refs=(REF,)):
    return {"field": "qualification", "category": category, "holder": holder,
            "value": "2", "op": op, "source_refs": list(refs)}


def tree(node=None):
    return compile_conditions({"schema_version": 1, "revision": 1, "source_refs": [REF],
                               "must": node or predicate()})


class SourceRelationPureTests(SimpleTestCase):
    def check(self, source, node=None, text="", **kwargs):
        return check_relations(tree(node), text=text, source_blocks={REF: source}, **kwargs)

    def test_system_defaults_explicit_grade_to_exact(self):
        self.assertIn("明确等级默认grade_exact", SYSTEM)
        self.assertIn("制造商必须提供CCRC二级证书", SYSTEM)

    def test_exact_default_requires_no_relation(self):
        self.assertEqual(self.check("制造商必须提供CCRC二级证书", predicate("grade_exact")), ([], []))

    def test_broadening_default_file_is_not_rewritten_as_exact(self):
        original = tree()
        gaps, accepted = check_relations(original, text="", source_blocks={REF: "制造商必须提供CCRC二级证书"})
        self.assertEqual(len(gaps), 1)
        self.assertFalse(accepted)
        self.assertEqual(original["must"]["op"], "grade_at_least")

    def test_explicit_file_relation_is_proven_by_own_block(self):
        for text in ("制造商必须提供CCRC二级及以上证书", "制造商CCRC不低于二级", "制造商至少CCRC二级"):
            with self.subTest(text=text):
                gaps, accepted = self.check(text)
                self.assertFalse(gaps)
                self.assertEqual(accepted, [relation_key(predicate())])

    def test_user_text_relation_does_not_need_an_attachment(self):
        gaps, accepted = check_relations(tree(predicate(holder="bidder", refs=())),
            text="投标人ITSS二级及以上".replace("ITSS", "CCRC"), source_blocks={})
        self.assertFalse(gaps)
        self.assertEqual(len(accepted), 1)

    def test_other_category_comparator_same_clause_cannot_license_ccrc(self):
        gaps, _ = self.check("制造商ITSS二级及以上且CCRC二级")
        self.assertEqual(len(gaps), 1)

    def test_other_category_earlier_comparator_cannot_span_to_node(self):
        gaps, _ = self.check("制造商至少ITSS二级且CCRC二级")
        self.assertEqual(len(gaps), 1)

    def test_other_block_and_top_level_refs_cannot_license_node(self):
        source = {REF: "制造商CCRC二级", "attachment:synthetic:b2": "制造商CCRC二级及以上"}
        gaps, _ = check_relations(tree(), text="", source_blocks=source)
        self.assertEqual(len(gaps), 1)
        gaps, _ = self.check("制造商CCRC二级及以上", predicate(refs=()))
        self.assertEqual(len(gaps), 1)

    def test_wrong_subject_cannot_license_node(self):
        self.assertEqual(len(self.check("投标人CCRC二级及以上")[0]), 1)
        self.assertEqual(len(self.check("CCRC二级及以上")[0]), 1)

    def test_negated_or_exact_relation_is_not_license(self):
        for source in ("制造商CCRC不是二级及以上", "制造商CCRC精确二级，不要二级及以上", "不得把制造商CCRC二级及以上作为要求"):
            with self.subTest(source=source):self.assertEqual(len(self.check(source)[0]), 1)

    def test_wrong_grade_or_numeric_substring_is_not_license(self):
        for source in ("制造商CCRC三级及以上", "制造商CCRC12级及以上", "制造商CCRC十二级及以上"):
            with self.subTest(source=source):self.assertEqual(len(self.check(source)[0]), 1)

    def test_nonmandatory_wording_never_licenses_broad_relation(self):
        for word in ("无需", "无须", "不必", "不需要", "不需", "可不", "免于"):
            with self.subTest(word=word):
                self.assertEqual(len(self.check(f"制造商{word}提供CCRC至少二级")[0]), 1)

    def test_missing_predicate_refs_and_different_category_in_user_text_fail_closed(self):
        gaps, _ = check_relations(tree(predicate(holder="bidder", refs=())),
            text="投标人ITSS二级及以上", source_blocks={REF: "投标人CCRC二级及以上"})
        self.assertEqual(len(gaps), 1)

    def test_multiple_subject_clauses_are_conservatively_ambiguous(self):
        self.assertEqual(len(self.check("制造商CCRC二级及以上而投标人CCRC精确二级")[0]), 1)

    def test_inherit_guard_validated_relation_without_repeating_wording(self):
        previous = tree()
        gaps, accepted = check_relations(tree(), text="只要广州市的", source_blocks={}, previous=previous,
            validated_previous=[relation_key(previous["must"])])
        self.assertFalse(gaps)
        self.assertEqual(len(accepted), 1)

    def test_unvalidated_previous_relation_cannot_bypass_gate(self):
        self.assertEqual(len(check_relations(tree(), text="继续", source_blocks={}, previous=tree())[0]), 1)

    def test_other_category_exact_or_city_change_keeps_validated_relation(self):
        previous = tree()
        for text in ("改为广州市", "保留电子与智能化精确二级"):
            with self.subTest(text=text):
                gaps, _ = check_relations(tree(), text=text, source_blocks={}, previous=previous,
                    validated_previous=[relation_key(previous["must"])])
                self.assertFalse(gaps)

    def test_global_exact_change_requires_new_model_relation_instead_of_inheritance(self):
        previous = tree()
        gaps, _ = check_relations(tree(), text="全部等级改为精确", source_blocks={}, previous=previous,
            validated_previous=[relation_key(previous["must"])])
        self.assertEqual(len(gaps), 1)

    def test_current_grade_change_is_not_unrelated_inheritance(self):
        previous = tree()
        gaps, _ = check_relations(tree(), text="制造商CCRC二级", source_blocks={}, previous=previous,
            validated_previous=[relation_key(previous["must"])])
        self.assertEqual(len(gaps), 1)

    def test_priority_and_not_branches_are_also_validated(self):
        compiled = tree({"not": predicate()})
        compiled["should"] = [predicate(holder="bidder")]
        gaps, _ = check_relations(compiled, text="", source_blocks={REF: "CCRC二级"})
        self.assertEqual(len(gaps), 2)


class RelationWorkerTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("relation-guard-owner", "product")
        temp = tempfile.TemporaryDirectory(prefix="relation-guard-")
        self.addCleanup(temp.cleanup)
        settings = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="relation-test",
            BAICHUAN_STORAGE_ROOT=temp.name, BAICHUAN_RESEARCH_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        settings.enable();self.addCleanup(settings.disable)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope="relation-test")

    def attachment(self, text):
        return BaichuanAttachment.objects.create(conversation=self.conversation, owner=self.owner,
            original_name="synthetic.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=4, sha256="a"*64, storage_ref=str(uuid.uuid4()), parse_status="completed",
            extracted_text=text, locators=[{"id": "b1", "text": text, "location": {"paragraph": 1}}])

    def send(self, text, node, attachment=None, include_export=False):
        self.conversation.refresh_from_db()
        if include_export:text += "，导出前10条Excel"
        _, job, _ = submit_message(self.owner, self.conversation.pk, {"text": text,
            "parent_revision": self.conversation.condition_revision, "client_request_id": uuid.uuid4().hex,
            "attachment_ids": [str(attachment.pk)] if attachment else []})
        response = tree(node);response["source_refs"] = list(node.get("source_refs", []))
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(response)}) as model, \
                patch("portal.baichuan_assistant_worker.run_parser") as parser:
            self.assertTrue(run_one("relation-worker", job.pk))
        model.assert_called_once();parser.assert_not_called();job.refresh_from_db()
        return job

    def test_unproven_file_relation_waits_releases_lease_and_does_not_export(self):
        attachment = self.attachment("制造商必须提供CCRC二级证书")
        node = predicate(refs=[f"attachment:{attachment.pk}:b1"])
        job = self.send("", node, attachment, include_export=True)
        self.assertEqual(job.status, "awaiting_input")
        self.assertIsNone(job.lease_expires_at)
        self.assertFalse(job.lease_owner)
        self.assertFalse(job.snapshots.exists())
        self.assertFalse(self.conversation.jobs.filter(kind="export").exists())
        self.assertEqual(job.checkpoint["pending_attachment_ids"], [str(attachment.pk)])
        self.assertIn("精确二级", job.checkpoint["summary"])
        self.assertEqual(job.checkpoint["conditions"]["must"]["op"], "grade_at_least")

    def test_default_exact_file_completes(self):
        attachment = self.attachment("制造商必须提供CCRC二级证书")
        job = self.send("", predicate("grade_exact", refs=[f"attachment:{attachment.pk}:b1"]), attachment)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.snapshots.get().condition_tree["must"]["op"], "grade_exact")

    def test_explicit_relation_file_completes_and_followup_keeps_same_relation(self):
        attachment = self.attachment("制造商必须提供CCRC二级及以上证书")
        node = predicate(refs=[f"attachment:{attachment.pk}:b1"])
        initial = self.send("", node, attachment)
        self.assertEqual(initial.status, "completed")
        original = deepcopy(initial.snapshots.get().condition_tree)
        continued = self.send("只要广州的", node)
        self.assertEqual(continued.status, "completed")
        self.assertEqual(continued.snapshots.get().condition_tree["must"]["op"], "grade_at_least")
        self.assertEqual(initial.snapshots.get().condition_tree, original)

    def test_clarification_reuses_pending_file_without_parser_or_relation_resurrection(self):
        attachment = self.attachment("制造商必须提供CCRC二级证书")
        node = predicate(refs=[f"attachment:{attachment.pk}:b1"])
        initial = self.send("", node, attachment)
        self.assertEqual(initial.status, "awaiting_input")
        continued = self.send("制造商CCRC精确二级", {**node, "op": "grade_exact"})
        self.assertEqual(continued.status, "completed")
        self.assertEqual(continued.payload["attachment_ids"], [str(attachment.pk)])
        self.assertNotIn("pending_attachment_ids", continued.checkpoint)
        self.assertEqual(continued.snapshots.get().condition_tree["must"]["op"], "grade_exact")
        self.assertEqual(initial.status, "awaiting_input")

    def test_pending_relation_cannot_be_inherited_without_new_proof(self):
        attachment = self.attachment("制造商CCRC二级")
        node = predicate(refs=[f"attachment:{attachment.pk}:b1"])
        self.assertEqual(self.send("", node, attachment).status, "awaiting_input")
        continued = self.send("继续", node)
        self.assertEqual(continued.status, "awaiting_input")
        self.assertFalse(continued.snapshots.exists())

    def test_cancelling_other_file_category_preserves_validated_relationship_for_followup(self):
        attachment = self.attachment("制造商CCRC二级及以上。投标人电子与智能化二级。")
        ref = f"attachment:{attachment.pk}:b1"
        ccrc = predicate(refs=[ref])
        node = {"all": [ccrc, predicate("grade_exact", category="electronic", holder="bidder", refs=[ref])]}
        initial = self.send("", node, attachment)
        self.assertEqual(initial.status, "completed")
        self.conversation.refresh_from_db()
        _, cancelled, _ = submit_message(self.owner, self.conversation.pk, {"text": "取消文件中的电子与智能化硬性要求",
            "attachment_ids": [], "parent_revision": self.conversation.condition_revision, "client_request_id": uuid.uuid4().hex})
        with patch("portal.baichuan_assistant_worker.generate_for_use") as gateway:
            run_one("relation-worker", cancelled.pk)
        gateway.assert_not_called();cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, "completed")
        continued = self.send("继续", ccrc)
        self.assertEqual(continued.status, "completed")
        self.assertEqual(continued.snapshots.get().condition_tree["must"]["op"], "grade_at_least")

    def test_existing_durable_checkpoint_and_snapshot_are_not_rewritten(self):
        _, job, _ = submit_message(self.owner, self.conversation.pk, {"text": "旧请求", "attachment_ids": [],
            "parent_revision": 0, "client_request_id": uuid.uuid4().hex})
        claimed = claim_job("old-worker", job_id=job.pk)
        existing = tree();save_job(job.pk, "old-worker", claimed.fence, checkpoint={"conditions": existing})
        from portal.baichuan_assistant_worker import process_query
        with patch("portal.baichuan_assistant_worker.generate_for_use") as model:process_query(claimed, "old-worker")
        model.assert_not_called()
        self.assertEqual(job.snapshots.get().condition_tree, existing)
