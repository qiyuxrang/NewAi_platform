from hashlib import sha256
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation, BaichuanEvidence,
    BaichuanFactRevision, BaichuanJob, BaichuanMatchSnapshot, map_legacy_qualifications)
from portal.baichuan_conditions import compile_conditions, evaluate_conditions
from portal.baichuan_facts import evidence_is_valid
from portal.baichuan_legacy_evidence import backfill_legacy_source_evidence, plan_legacy_source_links
from portal.baichuan_matching import company_facts
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


class LegacySourceEvidenceTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user('source-link-maintainer', 'product')
        self.reader = self.create_user('source-link-reader', 'product')
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, BAICHUAN_ASSISTANT_SCOPE='source-link-test',
            BAICHUAN_FACT_WRITE_ENABLED=False, PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name='来源补链虚构样本', phone='001234', source='人工资料保留',
            version=4, created_by=self.actor, updated_by=self.actor)
        self.legacy = CompanyQualification.objects.create(company=self.company, category='electronic', grade='2',
            status='PRESENT', source='源表声明，未逐证核实\n总表第9行；分类表第3行')
        map_legacy_qualifications(self.company, self.actor)
        self.certificate = BaichuanCertificate.objects.get(legacy_qualification_id=self.legacy.pk)

    def test_additive_link_preserves_values_original_revision_and_old_snapshot_and_replays_zero(self):
        before = list(Company.objects.values()), list(CompanyQualification.objects.values())
        original = self.certificate.source_revision
        conversation = BaichuanConversation.objects.create(owner=self.actor)
        job = BaichuanJob.objects.create(owner=self.actor, kind='query', conversation=conversation, idempotency_key='old')
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1, result_revision=1,
            fact_cutoff_at=timezone.now(), results=[{'evidence_ids': [], 'status': 'candidate'}])
        self.assertEqual(backfill_legacy_source_evidence(self.company, self.actor), {'created': 1, 'already_linked': 0, 'empty_source': 0})
        self.certificate.refresh_from_db()
        evidence, revision = self.certificate.evidence, self.certificate.source_revision
        self.assertEqual(evidence.excerpt, self.legacy.source)
        self.assertEqual(evidence.content_hash, sha256(self.legacy.source.encode()).hexdigest())
        self.assertEqual(evidence.scope, 'source-link-test')
        self.assertEqual(evidence.access_status, 'unverified')
        self.assertIsNone(evidence.verified_on)
        self.assertFalse(evidence.subject['identity_verified'])
        self.assertFalse(evidence_is_valid(evidence, self.company, scope='source-link-test'))
        self.assertEqual(revision.supersedes_id, original.pk)
        self.assertEqual(BaichuanFactRevision.objects.get(pk=original.pk).new_value['source'], self.legacy.source)
        self.assertEqual(self.certificate.verification_status, 'unverified')
        self.assertEqual(self.certificate.revocation_status, 'unknown')
        self.assertEqual(backfill_legacy_source_evidence(self.company, self.actor), {'created': 0, 'already_linked': 1, 'empty_source': 0})
        self.assertEqual(BaichuanEvidence.objects.count(), 1)
        self.assertEqual(BaichuanFactRevision.objects.count(), 2)
        self.assertEqual(before, (list(Company.objects.values()), list(CompanyQualification.objects.values())))
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.results, [{'evidence_ids': [], 'status': 'candidate'}])

    def test_explicit_reviewed_locator_requires_exact_source_and_hash(self):
        context = {'source': self.legacy.source, 'source_sha256': sha256(self.legacy.source.encode()).hexdigest(),
            'import_ref': 'sha256:' + 'a' * 64, 'locator': {'sheet': '总表', 'row': 9, 'section': {'sheet': '电子', 'row': 3}}}
        backfill_legacy_source_evidence(self.company, self.actor, source_context_by_legacy_id={str(self.legacy.pk): context})
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.evidence.locator, context['locator'])

    def test_reader_revoked_actor_and_stale_version_cannot_link(self):
        for actor in (self.reader,):
            with self.assertRaises(BaichuanError) as result:
                backfill_legacy_source_evidence(self.company, actor)
            self.assertEqual(result.exception.status, 403)
        with self.assertRaises(BaichuanError) as result:
            backfill_legacy_source_evidence(self.company, self.actor, expected_version=3)
        self.assertEqual(result.exception.code, 'version_conflict')
        self.actor.is_active = False
        self.actor.save(update_fields=['is_active'])
        with self.assertRaises(BaichuanError):
            backfill_legacy_source_evidence(self.company, self.actor)
        self.assertFalse(BaichuanEvidence.objects.exists())

    def test_changed_legacy_or_certificate_fails_without_partial_link(self):
        self.legacy.source = '后来人工修订来源'
        self.legacy.save(update_fields=['source'])
        with self.assertRaises(BaichuanError) as result:
            backfill_legacy_source_evidence(self.company, self.actor)
        self.assertEqual(result.exception.code, 'legacy_source_conflict')
        self.assertFalse(BaichuanEvidence.objects.exists())
        self.certificate.refresh_from_db()
        self.assertIsNone(self.certificate.evidence_id)

    def test_bad_context_and_cross_company_locator_are_rejected(self):
        for context in ({'source': 'wrong'}, {'source': self.legacy.source, 'source_sha256': sha256(self.legacy.source.encode()).hexdigest(),
                'import_ref': 'reviewed', 'locator': {'sheet': '总表', 'row': -1}}):
            with self.assertRaises(BaichuanError):
                backfill_legacy_source_evidence(self.company, self.actor, source_context_by_legacy_id={str(self.legacy.pk): context})
        with self.assertRaises(BaichuanError):
            backfill_legacy_source_evidence(self.company, self.actor, source_context_by_legacy_id={'unknown-id': {}})
        self.assertFalse(BaichuanEvidence.objects.exists())

    def test_existing_wrong_scope_or_changed_declaration_is_not_reported_as_successful_replay(self):
        other = BaichuanEvidence.objects.create(scope='other-deployment', source_type='legacy_import',
            retrieved_at=timezone.now(), excerpt=self.legacy.source, subject={'company_id': str(self.company.pk)})
        self.certificate.evidence = other
        self.certificate.save(update_fields=['evidence'])
        with self.assertRaises(BaichuanError):
            backfill_legacy_source_evidence(self.company, self.actor)
        self.certificate.evidence = None
        self.certificate.save(update_fields=['evidence'])
        backfill_legacy_source_evidence(self.company, self.actor)
        self.legacy.grade = '1'
        self.legacy.save(update_fields=['grade'])
        with self.assertRaises(BaichuanError):
            backfill_legacy_source_evidence(self.company, self.actor)
        self.assertEqual(BaichuanEvidence.objects.count(), 2)

    def test_invalid_versions_false_contexts_and_revocation_during_preflight_fail_closed(self):
        for version in (True, False, 0, -1, '4'):
            with self.assertRaises(BaichuanError) as result:
                backfill_legacy_source_evidence(self.company, self.actor, expected_version=version)
            self.assertEqual(result.exception.status, 400)
        for contexts in ([], False, ''):
            with self.assertRaises(BaichuanError):
                backfill_legacy_source_evidence(self.company, self.actor, source_context_by_legacy_id=contexts)
        real_plan = plan_legacy_source_links
        def revoke(*args, **kwargs):
            result = real_plan(*args, **kwargs)
            type(self.actor).objects.filter(pk=self.actor.pk).update(is_active=False)
            return result
        with patch('portal.baichuan_legacy_evidence.plan_legacy_source_links', side_effect=revoke):
            with self.assertRaises(BaichuanError):
                backfill_legacy_source_evidence(self.company, self.actor)
        self.assertFalse(BaichuanEvidence.objects.exists())

    def test_no_source_is_explicitly_skipped_and_audit_failure_rolls_back(self):
        with patch('portal.baichuan_legacy_evidence.audit', side_effect=RuntimeError('fixture audit write failure')):
            with self.assertRaises(RuntimeError):
                backfill_legacy_source_evidence(self.company, self.actor)
        self.assertFalse(BaichuanEvidence.objects.exists())
        self.assertEqual(BaichuanFactRevision.objects.count(), 1)
        self.legacy.source = ''
        self.legacy.save(update_fields=['source'])
        self.certificate.source_revision = None
        # Rebuild the isolated declaration exactly as a genuine empty-source mapping.
        self.certificate.delete()
        map_legacy_qualifications(self.company, self.actor)
        self.assertEqual(backfill_legacy_source_evidence(self.company, self.actor)['empty_source'], 1)

    def test_unknown_stays_unknown_but_deterministic_match_now_returns_source_id(self):
        self.assertEqual(plan_legacy_source_links(self.company)[0]['action'], 'link')
        backfill_legacy_source_evidence(self.company, self.actor)
        compiled = compile_conditions({'schema_version': 1, 'revision': 1, 'must': {'field': 'qualification',
            'category': 'electronic', 'op': 'grade_exact', 'value': '2', 'holder': 'bidder'}}, today=timezone.localdate())
        rules = {'electronic': {'enabled': True, 'version': 'fixture:1', 'source': 'fixture-only', 'grades': ['1', '2']}}
        result = evaluate_conditions(compiled, company_facts(self.company), rules=rules)
        self.assertEqual((result['status'], result['conditions'][0]['verdict']), ('candidate', 'unknown'))
        self.assertEqual(len(result['conditions'][0]['evidence_ids']), 1)
