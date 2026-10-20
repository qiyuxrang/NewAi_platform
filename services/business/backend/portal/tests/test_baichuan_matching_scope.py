"""Deployment-scoped facts must not leak or shadow another deployment's data."""
from datetime import timedelta
import json
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision, BaichuanQualificationRule
from portal.baichuan_matching import company_facts, match_companies
from portal.baichuan_models import Company
from .base import PortalTestCase


class MatchingScopeTests(PortalTestCase):
    def setUp(self):
        self.owner=self.create_user('scope-matching-owner','product')
        config=override_settings(BAICHUAN_ASSISTANT_SCOPE='own-matching-scope',PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[],PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable();self.addCleanup(config.disable)
        for target in ['socket.getaddrinfo','socket.create_connection','socket.socket.connect','portal.model_gateway.generate_for_use']:
            guard=patch(target,side_effect=AssertionError('Scope matching forbids acquisition/model'))
            mocked=guard.start();self.addCleanup(guard.stop);self.addCleanup(mocked.assert_not_called)
        self.today=timezone.localdate()
        self.company=Company.objects.create(name='FICTIONAL SCOPE MATCHING COMPANY',city='西安市',created_by=self.owner,updated_by=self.owner)
        self.own=self.evidence()
        self.foreign=self.evidence(scope='foreign-matching-scope')
        BaichuanQualificationRule.objects.create(category='itss',version=1,legal_grades=['2'],evidence=self.own)

    def evidence(self,scope='own-matching-scope'):
        return BaichuanEvidence.objects.create(scope=scope,source_type='fixture',url='https://example.com/isolated-scope',
            retrieved_at=timezone.now(),verified_on=self.today,content_hash='a'*64,excerpt='Synthetic scope matching evidence.',
            locator={'fixture':'page1'},access_status='verified',subject={'company_id':str(self.company.pk),'identity_verified':True,
                'holder_type':'bidder','authority':'issuer','scope_verified':True,'revocation_checked':True,
                'revocation_checked_on':self.today.isoformat()})

    def certificate(self,**changes):
        values=dict(company=self.company,category='itss',grade='2',holder_type='bidder',holder_company_id=self.company.pk,
            holder_name=self.company.name,certificate_no='SYNTHETIC-002',verification_status='verified',assertion_status='PRESENT',
            valid_from=self.today-timedelta(days=1),valid_until=self.today+timedelta(days=30),revocation_status='clear',evidence=self.own)
        values.update(changes);return BaichuanCertificate.objects.create(**values)

    def revision(self,**changes):
        values=dict(company=self.company,actor=self.owner,field='city',baseline_version=1,new_value='西安市',evidence=self.own,
            verification_status='verified',review_status='applied')
        values.update(changes);return BaichuanFactRevision.objects.create(**values)

    def match(self,node=None):
        node=node or {'field':'qualification','category':'itss','op':'grade_exact','value':'2','holder':'bidder'}
        return match_companies(self.owner,{'schema_version':1,'revision':1,'must':node})

    def assert_no_foreign_reference(self,value):
        self.assertNotIn(str(self.foreign.pk),json.dumps(value,default=str))

    def test_foreign_conflict_cannot_poison_current_verified_certificate(self):
        self.certificate()
        self.certificate(evidence=self.foreign,verification_status='conflict',certificate_no='FOREIGN-SECRET-NUMBER')
        _,_,rows,counts=self.match()
        self.assertEqual(counts['confirmed'],1)
        self.assertEqual(rows[0]['verdict'],'satisfied')
        self.assert_no_foreign_reference(rows)
        self.assertNotIn('FOREIGN-SECRET-NUMBER',json.dumps(rows))

    def test_foreign_only_certificate_not_exposed_or_treated_as_conflict(self):
        self.certificate(evidence=self.foreign,verification_status='conflict')
        facts=company_facts(self.company)
        self.assertEqual(facts['certificates'],[])
        _,_,rows,counts=self.match()
        self.assertEqual((counts['confirmed'],rows[0]['verdict']),(0,'unknown'))
        self.assertEqual(rows[0]['conditions'][0]['evidence_ids'],[])
        self.assert_no_foreign_reference(rows)

    def test_current_scope_conflict_still_blocks_confirmation(self):
        self.certificate();self.certificate(verification_status='conflict')
        _,_,rows,counts=self.match()
        self.assertEqual((counts['confirmed'],rows[0]['verdict']),(0,'conflict'))
        self.assertIn(str(self.own.pk),rows[0]['conditions'][0]['evidence_ids'])

    def test_no_evidence_manual_statement_retained_as_unknown(self):
        self.certificate(evidence=None,verification_status='unverified')
        facts=company_facts(self.company)
        self.assertEqual(len(facts['certificates']),1)
        self.assertEqual(facts['certificates'][0]['evidence_ids'],[])
        _,_,rows,counts=self.match()
        self.assertEqual((counts['confirmed'],rows[0]['verdict']),(0,'unknown'))

    def test_foreign_revision_ignored_before_current_field_seen(self):
        self.revision()
        self.revision(evidence=self.foreign,verification_status='conflict')
        facts=company_facts(self.company)
        self.assertEqual(facts['field_verification']['city'],{'status':'verified','evidence_ids':[str(self.own.pk)]})
        _,_,rows,counts=self.match({'field':'company.city','op':'eq','value':'西安市'})
        self.assertEqual(counts['confirmed'],1)
        self.assert_no_foreign_reference(rows)

    def test_foreign_only_field_conflict_is_unknown_without_references(self):
        self.revision(evidence=self.foreign,verification_status='conflict')
        self.assertEqual(company_facts(self.company)['field_verification'],{})
        _,_,rows,counts=self.match({'field':'company.city','op':'eq','value':'西安市'})
        self.assertEqual((counts['confirmed'],rows[0]['verdict']),(0,'unknown'))
        self.assert_no_foreign_reference(rows)

    def test_manual_unverified_field_revision_still_shadows_older_verified_fact(self):
        self.revision();self.revision(evidence=None,verification_status='unverified',review_status='manual')
        self.assertEqual(company_facts(self.company)['field_verification'],{})
        self.assertEqual(self.match({'field':'company.city','op':'eq','value':'西安市'})[3]['confirmed'],0)

    def test_fallback_revision_evidence_identifies_foreign_certificate(self):
        revision=self.revision(field='certificate',evidence=self.foreign)
        self.certificate(evidence=None,source_revision=revision,verification_status='conflict')
        self.assertEqual(company_facts(self.company)['certificates'],[])
        _,_,rows,counts=self.match()
        self.assertEqual((counts['confirmed'],rows[0]['verdict']),(0,'unknown'))
        self.assert_no_foreign_reference(rows)

    def test_direct_evidence_takes_priority_over_foreign_revision_evidence(self):
        revision=self.revision(field='certificate',evidence=self.foreign)
        self.certificate(evidence=self.own,source_revision=revision)
        _,_,rows,counts=self.match()
        self.assertEqual(counts['confirmed'],1)
        self.assert_no_foreign_reference(rows)

    def test_fallback_scope_check_does_not_add_query_per_certificate(self):
        revision=self.revision(field='certificate',evidence=self.foreign)
        self.certificate(evidence=None,source_revision=revision,verification_status='conflict')
        with CaptureQueriesContext(connection) as first:self.match()
        for _ in range(8):self.certificate(evidence=None,source_revision=revision,verification_status='conflict')
        with CaptureQueriesContext(connection) as more:self.match()
        self.assertEqual(len(first),len(more),'Fallback source scope must be prefetched, not queried once per certificate')
