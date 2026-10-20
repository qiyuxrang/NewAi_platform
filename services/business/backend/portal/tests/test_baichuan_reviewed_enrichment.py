from copy import deepcopy
import hashlib
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanConversation, BaichuanEvidence, BaichuanFactRevision,
    BaichuanJob, BaichuanMatchSnapshot)
from portal.baichuan_models import Company, CompanyQualification, CompanyPerson
from portal.baichuan_reviewed_enrichment import apply_reviewed_company, validate_batch, stamp_id, item_digest
from portal.baichuan_facts import propose_field, evidence_is_valid
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


class ReviewedEnrichmentTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user("reviewed-source-maintainer", "product")
        self.reader = self.create_user("reviewed-source-reader", "product")
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, BAICHUAN_ASSISTANT_SCOPE="reviewed-source-test",
            BAICHUAN_FACT_WRITE_ENABLED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name="公开资料虚构科技（陕西）有限公司", version=3, phone="001234",
            credit_code="123456789012345678", source="既有人工来源保留", created_by=self.actor, updated_by=self.actor)
        self.qualification = CompanyQualification.objects.create(company=self.company, category="itss", status="PRESENT", grade="2", source="旧声明")
        self.person = CompanyPerson.objects.create(company=self.company, name="旧联系人", source="人工")
        now = timezone.now().isoformat()
        body = self.company.name + "\n公开联系电话029-12345678\n电子邮箱hello@example.com\n办公地址陕西省西安市示例路1号\n企业提供软件技术服务。"
        self.batch = {"schema_version": 1, "source_workbook_sha256": "b" * 64, "review_status": "reviewed_public_source",
            "reviewer": "assistant_source_review", "reviewed_at": now, "items": [{"company_id": str(self.company.pk),
                "name": self.company.name, "expected_version": 3, "sources": [{"id": "contact", "url": "https://www.example.com/contact",
                    "title": "企业官网公开页面", "read_status": "completed", "retrieved_at": now, "body": body,
                    "content_sha256": hashlib.sha256(body.encode()).hexdigest(), "excerpt": body,
                    "locator": {"section": "联系我们", "text_start": 0, "text_end": len(body)}, "official_site_basis": "legal_name_publication",
                    "publication_kind": "corporate"}],
                "fields": {field: {"value": value, "source_id": "contact"} for field, value in {
                    "website": "https://www.example.com/", "email": "hello@example.com", "address": "陕西省西安市示例路1号",
                    "phone": "029-12345678", "description": "企业提供软件技术服务。"}.items()}}]}
        self.digest = "a" * 64

    def apply(self, batch=None, actor=None):
        batch = batch or self.batch
        return apply_reviewed_company(actor or self.actor, batch, batch["items"][0], self.digest)

    def test_fills_only_empty_fields_preserves_conflict_and_history(self):
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        job = BaichuanJob.objects.create(owner=self.actor, conversation=conversation, kind="query", idempotency_key="old")
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
            result_revision=1, fact_cutoff_at=timezone.now(), results=[{"old": "immutable"}])
        fixed_before = list(CompanyQualification.objects.values()), list(CompanyPerson.objects.values())
        result = self.apply()
        self.assertEqual(result, {"applied": 4, "conflict": 1, "unchanged": 0, "replayed": False})
        self.company.refresh_from_db()
        self.assertEqual((self.company.version, self.company.phone, self.company.source, self.company.credit_code),
                         (7, "001234", "既有人工来源保留", "123456789012345678"))
        self.assertEqual(self.company.email, "hello@example.com")
        self.assertEqual(fixed_before, (list(CompanyQualification.objects.values()), list(CompanyPerson.objects.values())))
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.results, [{"old": "immutable"}])
        evidence = BaichuanEvidence.objects.get()
        self.assertEqual(evidence.subject["source_review"], "assistant_source_review")
        self.assertFalse(evidence.subject["legal_identity_verified"])
        self.assertEqual(evidence.subject["publication_status"], "reviewed_public_publication")
        self.assertEqual(evidence.subject["publication_kind"], "corporate")
        self.assertNotIn("authority", evidence.subject)
        self.assertEqual(BaichuanFactRevision.objects.filter(field="phone").get().review_status, "conflict")

    def test_commit_then_crash_before_external_checkpoint_replays_no_new_records(self):
        self.apply()
        before = BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count()
        self.assertTrue(self.apply()["replayed"])
        self.assertEqual(before, (BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count()))
        self.company.refresh_from_db()
        self.assertEqual(self.company.version, 7)

    def test_same_value_is_reused_without_evidence_or_field_revision(self):
        self.company.email = "hello@example.com"
        self.company.save(update_fields=["email"])
        self.batch["items"][0]["fields"] = {"email": {"value": "hello@example.com", "source_id": "contact"}}
        self.assertEqual(self.apply(), {"applied": 0, "conflict": 0, "unchanged": 1, "replayed": False})
        self.assertEqual(BaichuanEvidence.objects.count(), 0)
        self.assertEqual(BaichuanFactRevision.objects.count(), 1)

    def test_reader_revoked_disabled_and_stale_are_fail_closed(self):
        with self.assertRaises(BaichuanError):
            self.apply(actor=self.reader)
        with override_settings(BAICHUAN_FACT_WRITE_ENABLED=False), self.assertRaises(BaichuanError):
            self.apply()
        self.batch["items"][0]["expected_version"] = 2
        with self.assertRaises(BaichuanError):
            self.apply()
        self.batch["items"][0]["expected_version"] = 3
        self.actor.is_active = False
        self.actor.save(update_fields=["is_active"])
        with self.assertRaises(BaichuanError):
            self.apply()
        self.assertEqual(BaichuanEvidence.objects.count(), 0)

    def test_unsupported_certificate_creditcode_names_are_rejected(self):
        for field in ("certificate", "credit_code", "contact_name", "contact_phone", "source", "verified_on"):
            changed = deepcopy(self.batch)
            changed["items"][0]["fields"][field] = {"value": "hello@example.com", "source_id": "contact"}
            with self.subTest(field=field), self.assertRaises(BaichuanError):
                self.apply(changed)
        self.assertEqual(BaichuanFactRevision.objects.count(), 0)

    def test_wrong_legal_name_and_brand_only_text_are_rejected(self):
        changed = deepcopy(self.batch)
        changed["items"][0]["name"] = "另一企业完整名称"
        with self.assertRaises(BaichuanError):
            self.apply(changed)
        changed = deepcopy(self.batch)
        changed["items"][0]["sources"][0]["excerpt"] = "软件技术服务"
        with self.assertRaises(BaichuanError):
            self.apply(changed)

    def test_only_whitespace_and_parentheses_name_normalization(self):
        changed = deepcopy(self.batch)
        source = changed["items"][0]["sources"][0]
        source["body"] = source["body"].replace(self.company.name, "公开资料虚构科技 ( 陕西 ) 有限公司")
        source["excerpt"] = source["body"]
        source["content_sha256"] = hashlib.sha256(source["body"].encode()).hexdigest()
        source["locator"]["text_end"] = len(source["body"])
        validate_batch(changed)

    def test_hash_locator_excerpt_and_field_assertions_exact(self):
        for mutation in ("hash", "locator", "field", "summary", "future", "fake_human"):
            changed = deepcopy(self.batch)
            source = changed["items"][0]["sources"][0]
            if mutation == "hash": source["content_sha256"] = "0" * 64
            if mutation == "locator": source["locator"]["text_start"] = 1
            if mutation == "field": changed["items"][0]["fields"]["email"]["value"] = "invented@example.com"
            if mutation == "summary": changed["items"][0]["fields"]["description"]["value"] = "全国领先服务商"
            if mutation == "future": source["retrieved_at"] = "2099-01-01T00:00:00+00:00"
            if mutation == "fake_human": changed["review_status"] = "human_reviewed"
            with self.subTest(mutation=mutation), self.assertRaises(BaichuanError):
                self.apply(changed)

    def test_private_unsafe_sources_and_different_website_host_rejected(self):
        for url in ("https://127.0.0.1/", "https://169.254.169.254/",
                    "https://localhost/", "https://site.internal/", "https://user:secret@example.com/", "https://example.com:8443/",
                    "https://127.1/", "https://0x7f.0.0.1/", "https://224.0.0.1/"):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(BaichuanError):
                self.apply(changed)
        changed = deepcopy(self.batch)
        changed["items"][0]["fields"]["website"]["value"] = "https://other.example.com/"
        with self.assertRaises(BaichuanError):
            self.apply(changed)

    def test_reviewed_http_corporate_site_keeps_its_original_protocol(self):
        self.batch["items"][0]["sources"][0]["url"] = "http://www.example.com/contact"
        self.batch["items"][0]["fields"] = {"website": {"value": "http://www.example.com/", "source_id": "contact"}}
        self.assertEqual(self.apply()["applied"], 1)
        self.company.refresh_from_db()
        self.assertEqual(self.company.website, "http://www.example.com/")
        evidence = BaichuanEvidence.objects.get()
        self.assertEqual(evidence.url, "http://www.example.com/contact")
        self.assertEqual(evidence.subject["transport_status"], "http_unencrypted")
        self.assertEqual(evidence.subject["website_basis"], "same_http_origin")
        self.assertFalse(evidence.subject["legal_identity_verified"])
        self.assertFalse(evidence_is_valid(evidence, self.company, certificate=True, scope="reviewed-source-test"))
        before = (BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count(), self.company.version)
        self.assertTrue(self.apply()["replayed"])
        self.company.refresh_from_db()
        self.assertEqual(before, (BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count(), self.company.version))

    def test_http_requires_explicit_corporate_classification(self):
        for kind in (None, "government", "industry", "directory", "encyclopedia", "group", "unknown"):
            changed = deepcopy(self.batch)
            source = changed["items"][0]["sources"][0]
            source["url"] = "http://www.example.com/contact"
            if kind is None:
                source.pop("publication_kind")
            else:
                source["publication_kind"] = kind
            changed["items"][0]["fields"] = {"email": {"value": "hello@example.com", "source_id": "contact"}}
            with self.subTest(kind=kind), self.assertRaises(BaichuanError):
                self.apply(changed)
        self.assertFalse(BaichuanEvidence.objects.exists())

    def test_website_scheme_host_and_default_port_must_match_read_source(self):
        for source_url, website in (
            ("http://www.example.com/contact", "https://www.example.com/"),
            ("https://www.example.com/contact", "http://www.example.com/"),
            ("http://www.example.com/contact", "http://other.example.com/"),
            ("http://www.example.com:443/contact", "http://www.example.com/"),
            ("https://www.example.com:80/contact", "https://www.example.com/"),
            ("http://www.example.com/contact", "http://www.example.com:8080/"),
        ):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["url"] = source_url
            changed["items"][0]["fields"] = {"website": {"value": website, "source_id": "contact"}}
            with self.subTest(source_url=source_url, website=website), self.assertRaises(BaichuanError):
                validate_batch(changed)
        changed = deepcopy(self.batch)
        changed["items"][0]["sources"][0]["url"] = "http://www.example.com:80/contact"
        changed["items"][0]["fields"] = {"website": {"value": "http://www.example.com/", "source_id": "contact"}}
        validate_batch(changed)

    def test_http_retains_private_credential_port_and_path_rejections(self):
        for url in ("http://127.0.0.1/", "http://169.254.169.254/", "http://localhost/",
                    "http://site.internal/", "http://user:secret@example.com/", "http://example.com:8443/",
                    "http://127.1/", "http://0x7f.0.0.1/", "http://224.0.0.1/", "http://[::1]/",
                    "http://www.example.com./", "http://www.example.com/\\private", "file:///local"):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(BaichuanError):
                validate_batch(changed)
        for website in ("http://www.example.com/contact", "http://www.example.com/?x=1", "http://www.example.com/#a"):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["url"] = "http://www.example.com/contact"
            changed["items"][0]["fields"] = {"website": {"value": website, "source_id": "contact"}}
            with self.subTest(website=website), self.assertRaises(BaichuanError):
                validate_batch(changed)

    def test_late_audit_failure_rolls_back_all_fields_evidence_and_stamp(self):
        with patch("portal.baichuan_reviewed_enrichment.audit", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError): self.apply()
        self.company.refresh_from_db()
        self.assertEqual((self.company.version, self.company.email, self.company.website), (3, None, None))
        self.assertEqual((BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count()), (0, 0))

    def test_same_key_changed_payload_and_other_scope_do_not_reuse_stamp(self):
        self.apply()
        changed = deepcopy(self.batch)
        changed["items"][0]["fields"].pop("phone")
        with self.assertRaises(BaichuanError): self.apply(changed)
        with override_settings(BAICHUAN_ASSISTANT_SCOPE="other-deployment"), self.assertRaises(BaichuanError): self.apply()
        self.assertEqual(BaichuanFactRevision.objects.count(), 6)

    def test_duplicate_company_and_extra_fields_rejected(self):
        changed = deepcopy(self.batch)
        changed["items"].append(deepcopy(changed["items"][0]))
        with self.assertRaises(BaichuanError): validate_batch(changed)
        changed = deepcopy(self.batch)
        changed["items"][0]["sources"][0]["identity_verified"] = True
        with self.assertRaises(BaichuanError): validate_batch(changed)

    def test_third_party_publications_never_become_company_websites(self):
        for kind in ("government", "industry", "directory", "encyclopedia", "group", "unknown"):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["publication_kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(BaichuanError):
                validate_batch(changed)
        changed = deepcopy(self.batch)
        changed["items"][0]["sources"][0]["publication_kind"] = "corporate"
        validate_batch(changed)
        self.assertEqual(BaichuanEvidence.objects.count(), 0)

    def test_third_party_contact_is_preserved_as_public_disclosure_only(self):
        self.batch["items"][0]["sources"][0]["publication_kind"] = "industry"
        self.batch["items"][0]["fields"] = {"email": {"value": "hello@example.com", "source_id": "contact"}}
        self.assertEqual(self.apply()["applied"], 1)
        evidence = BaichuanEvidence.objects.get()
        self.assertEqual(evidence.subject["publication_kind"], "industry")
        self.assertEqual(evidence.subject["publication_status"], "reviewed_public_publication")
        self.assertNotIn("authority", evidence.subject)
        self.assertIsNone(evidence.subject["website_basis"])
        self.assertFalse(evidence.subject["legal_identity_verified"])
        self.company.refresh_from_db()
        revision = propose_field(self.actor, self.company.pk, "website", "https://invented.example.com/",
            evidence, self.company.version, scope="reviewed-source-test")
        self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
        self.company.refresh_from_db()
        self.assertIsNone(self.company.website)

    def test_invalid_publication_kind_is_rejected(self):
        for kind in ("issuer", True, [], {"corporate": True}):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["publication_kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(BaichuanError):
                validate_batch(changed)

    def test_invalid_official_site_basis_is_a_validation_error(self):
        for basis in (None, [], {}, True):
            changed = deepcopy(self.batch)
            changed["items"][0]["sources"][0]["official_site_basis"] = basis
            with self.subTest(basis=basis), self.assertRaises(BaichuanError):
                validate_batch(changed)

    def test_malformed_identity_metadata_and_publication_not_certificate_authority(self):
        self.apply()
        evidence = BaichuanEvidence.objects.get()
        self.assertFalse(evidence_is_valid(evidence, self.company, certificate=True, scope="reviewed-source-test"))
        for method, basis in (([], {}), ({}, {}), ("official_host_name_credit_code", None),
                              ("official_host_name_credit_code", [])):
            evidence.subject["identity_method"] = method
            evidence.subject["identity_basis"] = basis
            with self.subTest(method=method, basis=basis):
                self.assertFalse(evidence_is_valid(evidence, self.company, scope="reviewed-source-test"))

    def test_legacy_missing_kind_cannot_create_new_website_write(self):
        del self.batch["items"][0]["sources"][0]["publication_kind"]
        validate_batch(self.batch)  # Legacy archive format is still readable.
        with self.assertRaises(BaichuanError):
            self.apply()
        self.assertEqual((BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count()), (0, 0))

    def test_existing_legacy_batch_stamp_replays_without_new_writes(self):
        item = self.batch["items"][0]
        del item["sources"][0]["publication_kind"]
        counts = {"applied": 4, "conflict": 1, "unchanged": 0}
        BaichuanFactRevision.objects.create(id=stamp_id(self.company.pk, self.digest), company=self.company,
            field="reviewed_enrichment_batch", actor=self.actor, baseline_version=3,
            new_value={"item_sha256": item_digest(item), "batch_sha256": self.digest, "counts": counts},
            verification_status="unverified", review_status="reviewed_public_source")
        self.assertEqual(self.apply(), {**counts, "replayed": True})
        self.assertEqual((BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count()), (0, 1))

    def test_malformed_assertion_containers_never_verify_substrings_or_keys(self):
        self.batch["items"][0]["fields"] = {"email": {"value": "hello@example.com", "source_id": "contact"}}
        self.apply()
        evidence = BaichuanEvidence.objects.get()
        self.company.refresh_from_db()
        value = "企业提供软件技术服务。"
        for assertions in (None, [], {"description": None}, {"description": "prefix" + value + "suffix"},
                           {"description": {value: False}}):
            evidence.subject["field_assertions"] = assertions
            with self.subTest(assertions=assertions):
                revision = propose_field(self.actor, self.company.pk, "description", value, evidence,
                    self.company.version, scope="reviewed-source-test")
                self.assertEqual((revision.review_status, revision.verification_status), ("proposed", "unverified"))
                self.company.refresh_from_db()
                self.assertIsNone(self.company.description)
