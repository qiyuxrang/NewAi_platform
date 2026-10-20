"""Foundation acceptance using synthetic data in Django's isolated test DB."""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation,
    BaichuanEvidence, BaichuanFactRevision, BaichuanJob, BaichuanJobItem,
    BaichuanMatchSnapshot, BaichuanMessage, map_legacy_qualifications)
from portal.baichuan_models import Company, CompanyPerson, CompanyQualification
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


class AssistantModelTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("foundation-maintainer", "product")
        self.reader = self.create_user("foundation-reader", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name="隔离虚构企业", phone="0012345", source="人工 Excel 原始来源",
            website="https://example.test/", version=4, created_by=self.actor, updated_by=self.actor)
        self.legacy = CompanyQualification.objects.create(company=self.company, category="itss", grade="2",
            status="PRESENT", certificate_no="00123", source="旧官网声明页（定位待确认）", verified_on=date(2025, 1, 1))
        self.person = CompanyPerson.objects.create(company=self.company, name="虚构业务联系人", source="人工公开资料")

    def evidence(self):
        return BaichuanEvidence.objects.create(url="https://example.test/evidence", retrieved_at=timezone.now(),
            excerpt="隔离测试正文", created_by=self.actor)

    def test_legacy_mapping_is_explicit_idempotent_and_preserves_manual_data(self):
        before = list(Company.objects.values()), list(CompanyQualification.objects.values()), list(CompanyPerson.objects.values())
        self.assertEqual(BaichuanCertificate.objects.count(), 0)
        self.assertEqual(len(map_legacy_qualifications(self.company, self.actor)), 1)
        self.assertEqual(map_legacy_qualifications(self.company, self.actor), [])
        mapped = BaichuanCertificate.objects.get(legacy_qualification_id=self.legacy.pk)
        self.assertEqual((mapped.assertion_status, mapped.verification_status, mapped.revocation_status),
                         ("PRESENT", "unverified", "unknown"))
        self.assertEqual(mapped.certificate_no, "00123")
        self.assertEqual(mapped.source_revision.new_value["source"], self.legacy.source)
        self.assertEqual(mapped.source_revision.new_value["verified_on"], "2025-01-01")
        self.assertEqual(before, (list(Company.objects.values()), list(CompanyQualification.objects.values()), list(CompanyPerson.objects.values())))

    def test_mapping_requires_maintenance_permission_and_current_version(self):
        with self.assertRaises(BaichuanError) as denied:
            map_legacy_qualifications(self.company, self.reader)
        self.assertEqual(denied.exception.status, 403)
        Company.objects.filter(pk=self.company.pk).update(version=5)
        with self.assertRaises(BaichuanError) as stale:
            map_legacy_qualifications(self.company, self.actor)
        self.assertEqual(stale.exception.status, 409)
        self.assertFalse(BaichuanCertificate.objects.exists())

    def test_legacy_child_removal_retains_mapped_history_and_source(self):
        map_legacy_qualifications(self.company, self.actor)
        old_id = self.legacy.pk
        self.legacy.delete()
        mapped = BaichuanCertificate.objects.get(legacy_qualification_id=old_id)
        self.assertEqual(mapped.source_revision.new_value["source"], "旧官网声明页（定位待确认）")
        with self.assertRaises(ProtectedError):
            self.company.delete()

    def test_revision_and_evidence_reject_save_update_delete_and_uuid_overwrite(self):
        evidence = self.evidence()
        revision = BaichuanFactRevision.objects.create(company=self.company, field="phone", old_value="0012345",
            new_value="0087654", actor=self.actor, evidence=evidence, baseline_version=4)
        for obj in (evidence, revision):
            with self.subTest(model=type(obj).__name__):
                with self.assertRaises(ValidationError):
                    obj.save()
                with self.assertRaises(ValidationError):
                    type(obj).objects.filter(pk=obj.pk).update(id=obj.pk)
                with self.assertRaises(ValidationError):
                    obj.delete()
                with self.assertRaises(ValidationError):
                    type(obj).objects.filter(pk=obj.pk).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanEvidence(id=evidence.pk, retrieved_at=timezone.now(), title="覆盖攻击").save()
        with self.assertRaises(ValidationError):
            BaichuanEvidence.objects.bulk_create([BaichuanEvidence(id=evidence.pk, retrieved_at=timezone.now(), title="upsert")],
                update_conflicts=True, update_fields=["title"], unique_fields=["id"])
        self.assertEqual(BaichuanEvidence.objects.get(pk=evidence.pk).title, "")

    def test_job_and_message_idempotency_and_unique_work_items(self):
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        BaichuanMessage.objects.create(conversation=conversation, role="user", client_request_id="request-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanMessage.objects.create(conversation=conversation, role="user", client_request_id="request-1")
        job = BaichuanJob.objects.create(owner=self.actor, kind="query", conversation=conversation, idempotency_key="request-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanJob.objects.create(owner=self.actor, kind="query", idempotency_key="request-1")
        BaichuanJob.objects.create(owner=self.reader, kind="query", idempotency_key="request-1")
        BaichuanJobItem.objects.create(job=job, item_key="company-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanJobItem.objects.create(job=job, item_key="company-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanJob.objects.create(owner=self.actor, kind="query", status="pretend_done")

    def test_result_revision_is_immutable_and_dates_cannot_reverse(self):
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        job = BaichuanJob.objects.create(owner=self.actor, conversation=conversation, kind="query")
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
            result_revision=1, fact_cutoff_at=timezone.now(), results=[{"company_id": str(self.company.pk), "verdict": "unknown"}])
        with self.assertRaises(ValidationError):
            BaichuanMatchSnapshot.objects.filter(pk=snapshot.pk).update(results=[])
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
                result_revision=1, fact_cutoff_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            BaichuanCertificate.objects.create(company=self.company, valid_from=date(2027, 1, 1), valid_until=date(2026, 1, 1))


class AssistantMigrationTests(TransactionTestCase):
    """Rehearse old schema -> additive schema -> empty-new-table schema rollback.

    Never use migration reversal after collecting new assistant facts. Production
    rollback closes feature flags and retains the tables and append-only history.
    """
    serialized_rollback = False

    def test_additive_migration_and_empty_rollback_preserve_all_legacy_rows(self):
        old_target = [("portal", "0045_company_website_kind")]
        new_target = [("portal", "0046_baichuan_assistant_foundation")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        User = old_apps.get_model("portal", "User")
        OldCompany = old_apps.get_model("portal", "Company")
        Qualification = old_apps.get_model("portal", "CompanyQualification")
        Person = old_apps.get_model("portal", "CompanyPerson")
        actor = User.objects.create(username="migration-synthetic", password="unused")
        company = OldCompany.objects.create(name="迁移演练虚构企业", phone="000123", source="人工 Excel 来源", version=9,
            website="https://example.test/", created_by_id=actor.pk, updated_by_id=actor.pk)
        Qualification.objects.create(company=company, category="electronic", grade="2", status="PRESENT", source="历史官网原文")
        Person.objects.create(company=company, name="虚构公开联系人", source="人工联系人来源")
        models = (OldCompany, Qualification, Person)
        before = [list(model.objects.order_by("id").values()) for model in models]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(new_target)
            new_apps = executor.loader.project_state(new_target).apps
            after = [list(new_apps.get_model("portal", model.__name__).objects.order_by("id").values()) for model in models]
            self.assertEqual(before, after)
            self.assertEqual(new_apps.get_model("portal", "BaichuanCertificate").objects.count(), 0)
            self.assertEqual(new_apps.get_model("portal", "BaichuanFactRevision").objects.count(), 0)
            executor = MigrationExecutor(connection)
            executor.migrate(old_target)
            self.assertEqual(before, [list(model.objects.order_by("id").values()) for model in models])
        finally:
            MigrationExecutor(connection).migrate(latest)
