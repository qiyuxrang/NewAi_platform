"""Certificate reconciliation regressions; synthetic, isolated, no acquisition."""
from datetime import date
import uuid
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (
    BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision, map_legacy_qualifications,
)
from portal.baichuan_facts import json_value, propose_certificate
from portal.baichuan_models import Company, CompanyQualification
from .base import PortalTestCase


class CertificateReconciliationTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("certificate-reconciliation-maintainer", "product")
        config = override_settings(
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[],
        )
        config.enable()
        self.addCleanup(config.disable)
        # Fail immediately if a regression unexpectedly tries public acquisition.
        for target in ("socket.getaddrinfo", "socket.create_connection", "socket.socket.connect"):
            guard = patch(target, side_effect=AssertionError("Network forbidden in certificate reconciliation tests"))
            guard.start()
            self.addCleanup(guard.stop)
        self.company = Company.objects.create(
            name="Certificate reconciliation synthetic company", version=3,
            created_by=self.actor, updated_by=self.actor,
        )

    def declaration(self, **changes):
        result = dict(
            category="itss", grade="2", holder_type="bidder", holder_name=self.company.name,
            holder_company_id=self.company.pk, certificate_no="SYNTHETIC-001",
            issuer="Synthetic issuer", standard="Synthetic standard v1",
            scope_text="Operation and maintenance synthetic scope",
            valid_from=date(2025, 1, 1), valid_until=date(2027, 12, 31),
            assertion_status="PRESENT", revocation_status="clear",
        )
        result.update(changes)
        return result

    def evidence(self, scope="default"):
        today = timezone.localdate()
        return BaichuanEvidence.objects.create(
            scope=scope, url="https://issuer.example.test/synthetic-certificate",
            source_type="web", retrieved_at=timezone.now(), verified_on=today,
            content_hash="a" * 64, excerpt="Synthetic original issuer certificate disclosure",
            locator={"table": "synthetic-certificate", "row": 1}, access_status="verified",
            subject={"company_id": str(self.company.pk), "identity_verified": True,
                     "holder_type": "bidder", "scope_verified": True, "authority": "issuer",
                     "revocation_checked": True, "revocation_checked_on": today.isoformat()},
            created_by=self.actor,
        )

    def existing(self, *, evidence_scope="default", verification_status="verified", **changes):
        declaration = self.declaration(**changes)
        evidence = self.evidence(evidence_scope)
        revision = BaichuanFactRevision.objects.create(
            company=self.company, field="certificate", actor=self.actor,
            baseline_version=3, new_value=json_value(declaration), evidence=evidence,
            review_status="applied" if verification_status == "verified" else "proposed",
            verification_status=verification_status,
        )
        return BaichuanCertificate.objects.create(
            company=self.company, **declaration, evidence=evidence, source_revision=revision,
            verification_status=verification_status,
            verified_at=timezone.now() if verification_status == "verified" else None,
        )

    def propose(self, **changes):
        return propose_certificate(
            self.actor, self.company.pk, self.declaration(**changes), self.evidence(), 3,
        )

    def assert_conflict_preserves_old(self, old, **changes):
        original = json_value(BaichuanCertificate.objects.filter(pk=old.pk).values().get())
        revision = self.propose(**changes)
        self.assertEqual(revision.review_status, "conflict")
        self.assertNotEqual(revision.pk, old.source_revision_id)
        self.assertEqual(BaichuanCertificate.objects.count(), 1)
        self.assertEqual(json_value(BaichuanCertificate.objects.filter(pk=old.pk).values().get()), original)
        self.company.refresh_from_db()
        self.assertEqual(self.company.version, 3)

    def test_other_scope_identical_certificate_does_not_deduplicate(self):
        old = self.existing(evidence_scope="another-deployment")
        revision = self.propose()
        self.assertEqual(revision.review_status, "applied")
        self.assertNotEqual(revision.pk, old.source_revision_id)
        self.assertEqual(revision.evidence.scope, "default")
        self.assertEqual(BaichuanCertificate.objects.count(), 2)
        old.refresh_from_db()
        self.assertEqual(old.evidence.scope, "another-deployment")

    def test_other_scope_same_number_different_grade_does_not_conflict(self):
        self.existing(evidence_scope="another-deployment", grade="3")
        revision = self.propose()
        self.assertEqual(revision.review_status, "applied")
        self.assertEqual(BaichuanCertificate.objects.count(), 2)

    def test_other_scope_source_revision_without_direct_evidence_is_isolated(self):
        old = self.existing(evidence_scope="another-deployment")
        old.evidence = None
        old.save(update_fields=["evidence"])
        revision = self.propose()
        self.assertEqual(revision.review_status, "applied")
        self.assertNotEqual(revision.pk, old.source_revision_id)
        self.assertEqual(BaichuanCertificate.objects.count(), 2)

    def test_no_evidence_manual_same_number_is_not_excluded_from_conflicts(self):
        old = self.existing()
        old.evidence, old.source_revision = None, None
        old.save(update_fields=["evidence", "source_revision"])
        self.assert_conflict_preserves_old(old)

    def test_invalid_incoming_evidence_is_not_hidden_by_old_verified_record(self):
        old = self.existing()
        revision = propose_certificate(self.actor, self.company.pk, self.declaration(),
                                       self.evidence("another-deployment"), 3)
        self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
        self.assertNotEqual(revision.pk, old.source_revision_id)
        self.assertEqual(BaichuanCertificate.objects.count(), 1)

    def test_same_scope_fully_identical_verified_certificate_is_idempotent(self):
        old = self.existing()
        revision = self.propose()
        self.assertEqual(revision.pk, old.source_revision_id)
        self.assertEqual(BaichuanCertificate.objects.count(), 1)
        self.company.refresh_from_db()
        self.assertEqual(self.company.version, 3)

    def test_same_scope_same_number_changed_dates_remains_conflict(self):
        self.assert_conflict_preserves_old(self.existing(valid_until=date(2027, 1, 1)))

    def test_same_scope_same_number_changed_holder_name_remains_conflict(self):
        self.assert_conflict_preserves_old(self.existing(holder_name="Another synthetic holder"))

    def test_manual_legacy_number_remains_protected(self):
        legacy = CompanyQualification.objects.create(
            company=self.company, category="itss", grade="2", status="PRESENT",
            certificate_no="MANUAL-PROTECTED-001", source="Synthetic manual declaration",
        )
        map_legacy_qualifications(self.company, self.actor)
        revision = self.propose()
        self.assertEqual(revision.review_status, "conflict")
        legacy.refresh_from_db()
        self.assertEqual(legacy.certificate_no, "MANUAL-PROTECTED-001")
        self.assertEqual(BaichuanCertificate.objects.count(), 1)

    def test_missing_explicit_valid_from_does_not_apply(self):
        revision = self.propose(valid_from=None)
        self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
        self.assertFalse(BaichuanCertificate.objects.exists())


def _changed_old_declaration(changes):
    def test(self):
        self.assert_conflict_preserves_old(self.existing(**changes))
    return test


for _name, _changes in {
    "issuer": {"issuer": "Another synthetic issuer"},
    "standard": {"standard": "Different synthetic standard"},
    "declared_scope": {"scope_text": "Different declared certificate scope"},
    "holder_type": {"holder_type": "manufacturer"},
    "holder_company_id": {"holder_company_id": uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")},
    "assertion_status": {"assertion_status": "ABSENT"},
    "verification_status": {"verification_status": "unverified"},
}.items():
    setattr(CertificateReconciliationTests, f"test_same_number_changed_{_name}_is_not_idempotent",
            _changed_old_declaration(_changes))
