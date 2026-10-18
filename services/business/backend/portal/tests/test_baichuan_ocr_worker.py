"""Low OCR reliability must block confirmation even with satisfied catalog facts."""
import json
import tempfile
import uuid
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanAttachment, BaichuanConversation,
    BaichuanEvidence, BaichuanFactRevision)
from portal.baichuan_assistant_service import submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_matching import match_companies
from portal.baichuan_models import Company
from .base import PortalTestCase


class OCRWorkerSafetyTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("ocr-worker-owner", "product")
        temp = tempfile.TemporaryDirectory(prefix="ocr-worker-safety-");self.addCleanup(temp.cleanup)
        settings = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="ocr-worker-test",
            BAICHUAN_STORAGE_ROOT=temp.name, BAICHUAN_RESEARCH_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        settings.enable();self.addCleanup(settings.disable)
        self.company = Company.objects.create(name="FICTIONAL OCR SAFETY COMPANY", city="广州市",
            created_by=self.owner, updated_by=self.owner)
        evidence = BaichuanEvidence.objects.create(scope="ocr-worker-test", source_type="fixture",
            url="https://example.com/synthetic-ocr-safety", retrieved_at=timezone.now(), verified_on=timezone.localdate(),
            content_hash="a"*64, excerpt=self.company.name+"位于广州市。仅为隔离测试。", locator={"fixture":"synthetic-city"},
            access_status="verified", subject={"company_id":str(self.company.pk), "identity_verified":True,
                "identity_method":"full_legal_name_on_public_page", "field_assertions":{"city":["广州市"]}})
        BaichuanFactRevision.objects.create(company=self.company, field="city", actor=self.owner, baseline_version=1,
            new_value="广州市", verification_status="verified", review_status="applied", evidence=evidence)
        self.tree = {"schema_version":1,"revision":1,"must":{"field":"company.city","op":"eq","value":"广州市"}}
        self.assertEqual(match_companies(self.owner,self.tree)[3]["confirmed"],1)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner,scope="ocr-worker-test")

    def send(self, status, *, cached=False, confidence=.61):
        block={"id":"b1","kind":"page" if status=="completed" else "ocr","text":"只要广州市企业", "location":{"page":1},"confidence":confidence}
        attachment=BaichuanAttachment.objects.create(owner=self.owner,conversation=self.conversation,
            original_name="synthetic-scan.pdf",media_type="application/pdf",size_bytes=5,
            sha256="b"*64,storage_ref=str(uuid.uuid4()),parse_status=status if cached else "pending",
            extracted_text="只要广州市企业" if cached else "",locators=[block] if cached else [])
        _,job,_=submit_message(self.owner,self.conversation.pk,{"text":"","attachment_ids":[str(attachment.pk)],
            "parent_revision":0,"client_request_id":uuid.uuid4().hex})
        parsed={"status":status,"blocks":[block],"warnings":[{"code":"low_ocr_confidence",
            "detail":"部分文字识别置信度较低，请对照原图核对。","location":{"page":1}}] if status=="needs_review" else []}
        # Storage bytes are synthetic too; no deployed parser/model/DB involved.
        from portal.baichuan_assistant_service import storage_path
        data=b"%PDF-";storage_path(attachment.storage_ref).write_bytes(data)
        import hashlib
        attachment.sha256=hashlib.sha256(data).hexdigest();attachment.save(update_fields=["sha256"])
        ref=f"attachment:{attachment.pk}:b1"
        response={**self.tree,"must":{**self.tree["must"],"source_refs":[ref]},"source_refs":[ref]}
        with patch("portal.baichuan_assistant_worker.run_parser",return_value=parsed) as parser, \
                patch("portal.baichuan_assistant_worker.generate_for_use",return_value={"content":json.dumps(response)}) as model:
            self.assertTrue(run_one("ocr-test-worker",job.pk))
        model.assert_called_once()
        if cached:parser.assert_not_called()
        else:parser.assert_called_once()
        job.refresh_from_db();return job

    def test_native_completed_control_can_confirm_verified_satisfied_fact(self):
        job=self.send("completed",confidence=1)
        self.assertEqual(job.status,"completed")
        self.assertEqual(job.snapshots.get().counts["confirmed"],1)

    def test_low_confidence_warning_downgrades_satisfied_hard_fact(self):
        job=self.send("needs_review")
        snapshot=job.snapshots.get()
        self.assertEqual(snapshot.counts,{"confirmed":0,"candidate":1,"excluded":0})
        self.assertEqual(snapshot.results[0]["conditions"][0]["verdict"],"satisfied")
        self.assertEqual(snapshot.results[0]["verdict"],"unknown")
        self.assertTrue(any("置信度" in text for text in snapshot.condition_tree["unresolved"]))

    def test_cached_needs_review_is_not_promoted_when_parser_warning_not_repeated(self):
        job=self.send("needs_review",cached=True)
        self.assertEqual(job.snapshots.get().counts["confirmed"],0)
        self.assertEqual(job.snapshots.get().counts["candidate"],1)
        self.assertTrue(any("提取需人工核对" in text for text in job.snapshots.get().condition_tree["unresolved"]))
