from datetime import timedelta
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation, BaichuanEvidence,
    BaichuanFactRevision, BaichuanJob, BaichuanMatchSnapshot, BaichuanQualificationRule)
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_matching import match_companies
from portal.baichuan_models import Company
from portal.model_gateway import GatewayError
from portal.baichuan_rules import install_compatibility_rules
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


ROOT = "/api/product/baichuan/assistant/"


def conditions():
    return {"schema_version": 1, "revision": 1, "must": {"field": "qualification", "category": "itss",
        "op": "grade_exact", "value": "2", "holder": "bidder"}}


class AssistantTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user("assistant-owner", "product")
        self.other = self.create_user("assistant-other", "product")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE="test-scope",
            BAICHUAN_STORAGE_ROOT=self.temp.name, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_ROLE_CODES=[], PRODUCT_WEB_SEARCH_ENABLED=False)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.login(self.client, self.owner)

    def post(self, path, payload):
        return self.client.post(ROOT + path, json.dumps(payload), content_type="application/json")

    def conversation(self):
        result = self.post("conversations/", {})
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()["id"]

    def send(self, conversation, text="广东 ITSS 二级", key="test-one", parent=0, attachments=None):
        return self.post(f"conversations/{conversation}/messages/", {"text": text,
            "attachment_ids": attachments or [], "client_request_id": key, "parent_revision": parent})

    def test_owner_scope_and_refresh_recovery_are_checked_on_each_read(self):
        identifier = self.conversation()
        sent = self.send(identifier)
        self.assertEqual(sent.status_code, 202, sent.content)
        job_id = sent.json()["job"]["id"]
        recovered = self.client.get(ROOT + f"conversations/{identifier}/").json()
        self.assertEqual(recovered["condition_revision"], 1)
        self.assertEqual(recovered["jobs"][0]["id"], job_id)
        self.assertEqual(recovered["messages"][0]["content"], "广东 ITSS 二级")
        self.login(self.client, self.other)
        self.assertEqual(self.client.get(ROOT + f"conversations/{identifier}/").status_code, 404)
        self.assertEqual(self.client.get(ROOT + f"jobs/{job_id}/").status_code, 404)
        self.assertEqual(self.send(identifier).status_code, 404)
        self.login(self.client, self.owner)
        with override_settings(BAICHUAN_ASSISTANT_SCOPE="another-deployment"):
            self.assertEqual(self.client.get(ROOT + f"conversations/{identifier}/").status_code, 404)

    def test_message_idempotency_revision_conflict_and_invalid_inputs(self):
        identifier = self.conversation()
        sent = self.send(identifier)
        self.assertEqual(sent.status_code, 202)
        repeated = self.send(identifier)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["job"]["id"], sent.json()["job"]["id"])
        self.assertEqual(BaichuanJob.objects.count(), 1)
        self.assertEqual(self.send(identifier, text="different").status_code, 409)
        self.assertEqual(self.send(identifier, key="two").status_code, 409)
        self.assertEqual(self.send(identifier, key="two", parent=1, text="").status_code, 400)
        self.assertEqual(self.send(identifier, key="two", parent=1, attachments=["not-a-uuid"]).status_code, 404)
        self.assertEqual(BaichuanConversation.objects.get(pk=identifier).condition_revision, 1)

    def test_attachment_format_bomb_and_other_conversation_rejected(self):
        identifier, another = self.conversation(), self.conversation()
        path = ROOT + f"conversations/{identifier}/attachments/"
        upload = SimpleUploadedFile("sample.pdf", b"%PDF-1.7\nfixture")
        response = self.client.post(path, {"file": upload})
        self.assertEqual(response.status_code, 201, response.content)
        attachment = response.json()["id"]
        self.assertEqual(self.send(another, attachments=[attachment]).status_code, 404)
        self.assertEqual(self.client.post(path, {"file": SimpleUploadedFile("fake.pdf", b"not pdf")}).status_code, 400)
        self.assertEqual(self.client.post(path, {"file": SimpleUploadedFile("old.doc", b"old")}).status_code, 400)
        archive = io.BytesIO()
        with ZipFile(archive, "w") as stream:
            stream.writestr("../escape.xml", "<x/>")
            stream.writestr("[Content_Types].xml", "<x/>")
            stream.writestr("word/document.xml", "<x/>")
        self.assertEqual(self.client.post(path, {"file": SimpleUploadedFile("unsafe.docx", archive.getvalue())}).status_code, 400)

    def test_missing_gateway_records_real_failed_job_without_inventing_results(self):
        identifier = self.conversation()
        sent = self.send(identifier).json()
        with patch("portal.baichuan_assistant_worker.generate_for_use", side_effect=GatewayError("unconfigured")):
            self.assertTrue(run_one("test-worker", sent["job"]["id"]))
        job = BaichuanJob.objects.get(pk=sent["job"]["id"])
        self.assertEqual(job.status, "failed")
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())
        self.assertIn("模型网关尚未配置", self.client.get(ROOT + f"conversations/{identifier}/").json()["messages"][-1]["content"])

    def test_worker_deterministic_results_and_late_round_isolation(self):
        identifier = self.conversation()
        first = self.send(identifier).json()
        second = self.send(identifier, text="只要广州", key="two", parent=1).json()
        model = {"content": json.dumps(conditions())}
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value=model):
            run_one("second", second["job"]["id"])
            pending = BaichuanJob.objects.get(pk=second["job"]["id"])
            self.assertEqual(pending.status, "queued")
            self.assertEqual(pending.attempts, 0)
            self.assertEqual(pending.lease_owner, "")
            self.assertFalse(pending.snapshots.exists())
            run_one("first-late", first["job"]["id"])
            run_one("second-resumed", pending.pk)
        revisions = set(BaichuanMatchSnapshot.objects.values_list("condition_revision", flat=True))
        self.assertEqual(revisions, {1, 2})
        self.assertEqual(BaichuanConversation.objects.get(pk=identifier).condition_revision, 2)
        for snapshot in BaichuanMatchSnapshot.objects.all():
            response = self.client.get(ROOT + f"results/{snapshot.pk}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["counts"], {"confirmed": 0, "candidate": 0, "excluded": 0})
        self.login(self.client, self.other)
        self.assertEqual(self.client.get(ROOT + f"results/{snapshot.pk}/").status_code, 404)

    def test_model_sql_and_fabricated_source_are_rejected_before_matching(self):
        for key, payload in (("sql", {**conditions(), "sql": "SELECT * FROM portal_company"}),
                             ("source", {**conditions(), "source_refs": ["attachment:other:fake"]})):
            identifier = self.conversation()
            job_id = self.send(identifier, key=key).json()["job"]["id"]
            with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(payload)}):
                run_one("invalid-output", job_id)
            self.assertEqual(BaichuanJob.objects.get(pk=job_id).status, "failed")
            self.assertFalse(BaichuanMatchSnapshot.objects.filter(job_id=job_id).exists())

    def test_capability_config_disabled_switch_and_permission_revoked(self):
        config = self.client.get(ROOT + "config/")
        self.assertEqual(config.status_code, 200, config.content)
        self.assertFalse(config.json()["capabilities"]["search"])
        with override_settings(BAICHUAN_ASSISTANT_ENABLED=False):
            self.assertFalse(self.client.get(ROOT + "config/").json()["enabled"])
            self.assertEqual(self.post("conversations/", {}).status_code, 503)
        identifier = self.conversation()
        with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[]):
            self.assertEqual(self.client.get(ROOT + f"conversations/{identifier}/").status_code, 403)

    def test_matching_requires_current_evidence_not_legacy_present(self):
        company = Company.objects.create(name="虚构隔离企业", created_by=self.owner, updated_by=self.owner)
        evidence = BaichuanEvidence.objects.create(scope="test-scope", url="https://example.com/fixture",
            retrieved_at=timezone.now(), verified_on=timezone.localdate(), content_hash=hashlib.sha256(b"fixture").hexdigest(),
            excerpt="FICTIONAL certificate", locator={"page": 1}, access_status="verified",
            subject={"company_id": str(company.pk), "identity_verified": True, "holder_type": "bidder",
                "authority": "issuer", "scope_verified": True, "revocation_checked": True,
                "revocation_checked_on": timezone.localdate().isoformat()})
        BaichuanQualificationRule.objects.create(category="itss", version=1, evidence=evidence, legal_grades=["1", "2", "3", "4"])
        cert = BaichuanCertificate.objects.create(company=company, category="itss", holder_type="bidder",
            holder_company_id=company.pk, grade="2", assertion_status="PRESENT", verification_status="verified",
            valid_from=timezone.localdate() - timedelta(days=1), valid_until=timezone.localdate() + timedelta(days=30),
            revocation_status="clear", evidence=evidence)
        self.assertEqual(match_companies(self.owner, conditions())[3]["confirmed"], 1)
        cert.verification_status = "unverified"
        cert.save()
        self.assertEqual(match_companies(self.owner, conditions())[3]["candidate"], 1)
        self.assertEqual(Company.objects.get(pk=company.pk).version, 1)

    def test_rules_install_requires_maintenance_and_preserves_uncovered_relations(self):
        with self.assertRaises(BaichuanError):
            install_compatibility_rules(self.owner)
        with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk]):
            self.assertEqual(len(install_compatibility_rules(self.owner)), 7)
            self.assertEqual(install_compatibility_rules(self.owner), [])
        cs = BaichuanQualificationRule.objects.get(category="cs")
        itss = BaichuanQualificationRule.objects.get(category="itss")
        self.assertEqual(cs.grade_relations["at_least"]["2"], ["2", "3", "4", "5"])
        self.assertEqual(itss.grade_relations["at_least"], {})
        self.assertEqual(Company.objects.count(), 0)

    def test_file_only_real_docx_parser_retains_clause_location(self):
        runtime = Path(__file__).resolve().parents[5] / ".runtime/company-test/cloud-ocr/Scripts/python.exe"
        if not runtime.is_file():
            self.skipTest("Local parser runtime absent; capability probe must be run for deployment")
        content = io.BytesIO()
        with ZipFile(content, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>投标人必须具备ITSS二级；制造商ISO证书为优先项。</w:t></w:r></w:p></w:body></w:document>')
        identifier = self.conversation()
        uploaded = self.client.post(ROOT + f"conversations/{identifier}/attachments/",
            {"file": SimpleUploadedFile("fictional.docx", content.getvalue())})
        self.assertEqual(uploaded.status_code, 201, uploaded.content)
        attachment_id = uploaded.json()["id"]
        job_id = self.send(identifier, text="", attachments=[attachment_id]).json()["job"]["id"]
        result = conditions()
        result["source_refs"] = [f"attachment:{attachment_id}:b1"]
        result["must"]["source_refs"] = list(result["source_refs"])
        with override_settings(PRODUCT_PARSER_PYTHON=runtime, PRODUCT_STORAGE_ROOT=self.temp.name), patch(
                "portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(result)}) as model:
            run_one("docx-real-parser", job_id)
        prompt = json.loads(model.call_args.args[2][1]["content"])
        self.assertIn("投标人必须具备ITSS二级", prompt["documents"][0]["text"])
        snapshot = BaichuanMatchSnapshot.objects.get(job_id=job_id)
        self.assertEqual(snapshot.condition_tree["source_refs"], [f"attachment:{attachment_id}:b1"])
        parsed = BaichuanConversation.objects.get(pk=identifier).attachments.get()
        self.assertEqual(parsed.parse_status, "completed")
        self.assertEqual(parsed.locators[0]["location"]["paragraph"], 1)

    def test_export_in_same_input_preserves_condition_revision_and_is_idempotent(self):
        identifier = self.conversation()
        job_id = self.send(identifier).json()["job"]["id"]
        with patch("portal.baichuan_assistant_worker.generate_for_use", return_value={"content": json.dumps(conditions())}):
            run_one("query-first", job_id)
        exported = self.send(identifier, text="导出前10条Excel", key="export-only", parent=1)
        self.assertEqual(exported.status_code, 202, exported.content)
        export_job = exported.json()["job"]
        self.assertEqual(export_job["kind"], "export")
        self.assertEqual(BaichuanConversation.objects.get(pk=identifier).condition_revision, 1)
        self.assertEqual(self.send(identifier, text="导出前10条Excel", key="export-only", parent=1).json()["job"]["id"], export_job["id"])
        run_one("export-same-input", export_job["id"])
        self.assertEqual(BaichuanJob.objects.get(pk=export_job["id"]).status, "completed")
