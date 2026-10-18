from datetime import date

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision, map_legacy_qualifications
from portal.baichuan_facts import json_value, propose_certificate, propose_field, revert_field
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_service import BaichuanError, COMPANY_FIELDS, save_company
from .base import PortalTestCase


class FactServiceTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("facts-maintainer", "product")
        self.reader = self.create_user("facts-reader", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            BAICHUAN_FACT_WRITE_ENABLED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name="事实服务虚构样本", phone="00123", version=3,
            source="人工 Excel 既有成果", created_by=self.actor, updated_by=self.actor)

    def evidence(self, **overrides):
        values = dict(url="https://example.test/certificate", source_type="web", retrieved_at=timezone.now(),
            verified_on=date(2026, 10, 17), content_hash="a" * 64, excerpt="原始发布机构证书正文", locator={"page": 1},
            access_status="verified", subject={"company_id": str(self.company.pk), "identity_verified": True,
                "holder_type": "bidder", "scope_verified": True, "authority": "issuer",
                "revocation_checked": True, "revocation_checked_on": "2026-10-17"}, created_by=self.actor)
        values.update(overrides)
        return BaichuanEvidence.objects.create(**values)

    def declaration(self, **overrides):
        values = dict(category="itss", grade="2", holder_type="bidder", holder_name=self.company.name,
            holder_company_id=str(self.company.pk), certificate_no="001239", assertion_status="PRESENT",
            valid_from="2025-01-01", valid_until="2027-12-31", revocation_status="clear")
        values.update(overrides)
        return values

    def test_maintainer_fills_verified_blank_once_without_rewriting_manual_fields(self):
        evidence = self.evidence()
        revision = propose_field(self.actor, self.company.pk, "website", "https://example.test/", evidence, 3)
        self.company.refresh_from_db()
        self.assertEqual((revision.review_status, revision.verification_status), ("applied", "verified"))
        self.assertEqual((self.company.version, self.company.website, self.company.phone, self.company.source),
            (4, "https://example.test/", "00123", "人工 Excel 既有成果"))
        again = propose_field(self.actor, self.company.pk, "website", "https://example.test/", evidence, 4)
        self.assertEqual(propose_field(self.actor, self.company.pk, "website", "https://example.test/", evidence, 4).pk, again.pk)
        self.company.refresh_from_db()
        self.assertEqual(self.company.version, 4)

    def test_reader_proposal_never_writes_and_manual_conflict_is_retained(self):
        evidence = self.evidence()
        suggestion = propose_field(self.reader, self.company.pk, "email", "public@example.test", evidence, 3)
        self.assertEqual(suggestion.review_status, "proposed")
        reader_conflict = propose_field(self.reader, self.company.pk, "phone", "00888", evidence, 3)
        self.assertEqual(reader_conflict.review_status, "proposed")
        conflict = propose_field(self.actor, self.company.pk, "phone", "00999", evidence, 3)
        self.assertEqual((conflict.review_status, conflict.verification_status), ("conflict", "conflict"))
        self.company.refresh_from_db()
        self.assertEqual((self.company.email, self.company.phone, self.company.version), (None, "00123", 3))

    @override_settings(BAICHUAN_FACT_WRITE_ENABLED=False)
    def test_disabled_fact_writes_keep_verified_suggestions_without_company_changes(self):
        revision = propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(), 3)
        self.assertEqual(revision.review_status, "proposed")
        revision = propose_certificate(self.actor, self.company.pk, self.declaration(), self.evidence(), 3)
        self.assertEqual(revision.review_status, "proposed")
        self.company.refresh_from_db()
        self.assertIsNone(self.company.email)
        self.assertFalse(BaichuanCertificate.objects.exists())

    def test_body_locator_subject_scope_and_search_snippet_fail_closed(self):
        for overrides in ({"excerpt": ""}, {"locator": {}}, {"subject": {"company_id": "another-company", "identity_verified": True}},
                {"source_type": "search_snippet"}, {"scope": "another-deployment"}, {"access_status": "inaccessible"}):
            with self.subTest(overrides=overrides):
                revision = propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(**overrides), 3)
                self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
        self.company.refresh_from_db()
        self.assertIsNone(self.company.email)

    def test_stale_or_revoked_permission_does_not_write(self):
        Company.objects.filter(pk=self.company.pk).update(version=4)
        with self.assertRaises(BaichuanError) as result:
            propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(), 3)
        self.assertEqual(result.exception.status, 409)
        self.actor.is_active = False
        self.actor.save()
        with self.assertRaises(BaichuanError) as result:
            propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(), 4)
        self.assertEqual(result.exception.status, 403)
        self.assertFalse(BaichuanFactRevision.objects.exists())

    def test_certificate_requires_original_authority_and_projects_exact_legacy_grade(self):
        revision = propose_certificate(self.actor, self.company.pk, self.declaration(), self.evidence(), 3)
        self.assertEqual((revision.review_status, revision.verification_status), ("applied", "verified"))
        certificate = BaichuanCertificate.objects.get(source_revision=revision)
        self.assertEqual((certificate.verification_status, certificate.certificate_no), ("verified", "001239"))
        projected = CompanyQualification.objects.get(pk=certificate.legacy_qualification_id)
        self.assertEqual((projected.category, projected.grade, projected.status), ("itss", "2", "PRESENT"))
        self.assertTrue(BaichuanFactRevision.objects.filter(field="legacy_projection", object_id=projected.pk).exists())
        self.assertEqual(propose_certificate(self.actor, self.company.pk, self.declaration(), self.evidence(), 4).pk, revision.pk)
        self.assertEqual(BaichuanCertificate.objects.count(), 1)

    def test_certificate_wrong_subject_dates_or_unchecked_revocation_remain_suggestions(self):
        cases = [({"holder_type": "manufacturer"}, {}), ({"valid_from": None}, {}),
            ({}, {"subject": {"company_id": str(self.company.pk), "identity_verified": True,
                "holder_type": "bidder", "scope_verified": True, "authority": "corporate"}}),
            ({}, {"subject": {"company_id": str(self.company.pk), "identity_verified": True,
                "holder_type": "bidder", "scope_verified": True, "authority": "issuer"}}),
            ({"assertion_status": "ABSENT"}, {})]
        for declaration, evidence in cases:
            with self.subTest(declaration=declaration, evidence=evidence):
                revision = propose_certificate(self.actor, self.company.pk, self.declaration(**declaration), self.evidence(**evidence), 3)
                self.assertEqual(revision.review_status, "proposed")
        self.assertFalse(BaichuanCertificate.objects.exists())
        self.assertFalse(CompanyQualification.objects.exists())

    def test_certificate_conflict_does_not_overwrite_existing_manual_declaration(self):
        legacy = CompanyQualification.objects.create(company=self.company, category="itss", grade="2", status="PRESENT",
            certificate_no="manual-001", source="人工旧证书")
        map_legacy_qualifications(self.company, self.actor)
        revision = propose_certificate(self.actor, self.company.pk, self.declaration(), self.evidence(), 3)
        self.assertEqual(revision.review_status, "conflict")
        legacy.refresh_from_db()
        self.assertEqual(legacy.certificate_no, "manual-001")
        self.assertEqual(BaichuanCertificate.objects.count(), 1)

    def test_manual_editor_keeps_removed_child_history_and_supersedes_projection(self):
        legacy = CompanyQualification.objects.create(company=self.company, category="itss", grade="2", status="PRESENT", source="原始官网声明")
        map_legacy_qualifications(self.company, self.actor)
        payload = {"company": {field: json_value(getattr(self.company, field)) for field in COMPANY_FIELDS},
            "qualifications": [], "people": [], "expected_version": 3}
        payload["company"]["phone"] = "00777"
        save_company(self.actor, payload, self.company.pk)
        certificate = BaichuanCertificate.objects.get(legacy_qualification_id=legacy.pk)
        self.assertEqual(certificate.verification_status, "superseded")
        retained = BaichuanFactRevision.objects.get(field="legacy_qualification", review_status="manual")
        self.assertEqual(retained.old_value["source"], "原始官网声明")
        self.assertIsNone(retained.new_value)
        manual = BaichuanFactRevision.objects.get(field="phone", review_status="manual")
        self.assertEqual((manual.old_value, manual.new_value, manual.verification_status), ("00123", "00777", "unverified"))

    def test_revert_one_field_retains_history_and_rejects_later_manual_changes(self):
        revision = propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(), 3)
        reverted = revert_field(self.actor, revision.pk)
        self.company.refresh_from_db()
        self.assertEqual((self.company.email, self.company.version), (None, 5))
        self.assertEqual(reverted.supersedes_id, revision.pk)
        revision = propose_field(self.actor, self.company.pk, "email", "public@example.test", self.evidence(), 5)
        Company.objects.filter(pk=self.company.pk).update(version=7, phone="later manual value")
        with self.assertRaises(BaichuanError) as result:
            revert_field(self.actor, revision.pk)
        self.assertEqual(result.exception.status, 409)
        self.company.refresh_from_db()
        self.assertEqual(self.company.phone, "later manual value")
