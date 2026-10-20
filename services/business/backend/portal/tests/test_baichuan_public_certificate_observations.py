"""Maintenance publication regressions; isolated SQLite, no acquisition or models."""
import copy
from datetime import timedelta
import hashlib
import json
import uuid
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout
from io import StringIO
import sys
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection
from django.test import override_settings, SimpleTestCase
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision,
    BaichuanConversation, BaichuanJob, BaichuanMatchSnapshot, map_legacy_qualifications)
from portal.baichuan_conditions import compile_conditions, evaluate_conditions
from portal.baichuan_facts import record_public_certificate_observation, validate_public_certificate_observation
from portal.baichuan_matching import company_facts
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_service import BaichuanError
from .base import PortalTestCase


class PublicCertificateObservationTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user('public-certificate-maintainer', 'product')
        self.reader = self.create_user('public-certificate-reader', 'product')
        config = override_settings(PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
            BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE='observation-tests',
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        for target in ['socket.getaddrinfo', 'socket.create_connection', 'socket.socket.connect']:
            guard = patch(target, side_effect=AssertionError('Acquisition forbidden in observation tests'))
            guard.start()
            self.addCleanup(guard.stop)
        self.company = Company.objects.create(name='公开证书虚构隔离企业有限公司', version=3,
            phone='000-protected-manual-phone', source='protected-original', created_by=self.actor, updated_by=self.actor)

    def record(self, **changes):
        data = {'orgName': self.company.name, 'certificateCode': 'ITSS-YW-3-610020230387',
            'cityName': '陕西省', 'itssTypeText': '运行维护', 'certificateName': '三级',
            'validFlag': '有效', 'pgjg': '公开评估机构（不是issuer）', 'getType': '再评估',
            'startDate': '2023-03-20', 'getDate': '2026-01-27', 'endDate': '2029-03-19'}
        data.update(changes)
        return data

    def source(self, record):
        body = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
        return {'url': 'https://www.itss.cn/api/itss/web/certificate/' + '1' * 32,
            'title': '隔离公开证书结构样本', 'publisher': '公开目录发布机构',
            'retrieved_at': (timezone.now() - timedelta(seconds=2)).isoformat(), 'read_status': 'completed',
            'publication_kind': 'industry', 'body': body, 'excerpt': body,
            'content_sha256': hashlib.sha256(body.encode()).hexdigest(),
            'locator': {'text_start': 0, 'text_end': len(body), 'section': 'Complete actual JSON'},
            'field_assertions': {key: [value] for key, value in record.items()}}

    def apply(self, record=None, source=None, actor=None, version=3, scope='observation-tests'):
        record = record or self.record()
        return record_public_certificate_observation(actor or self.actor, self.company.pk, record,
            source or self.source(record), version, scope=scope)

    def counts(self):
        self.company.refresh_from_db()
        return (BaichuanCertificate.objects.count(), BaichuanEvidence.objects.count(), BaichuanFactRevision.objects.count(), self.company.version)

    def test_default_publication_gate_and_both_explicit_gates_fail_closed(self):
        for flags in [{"BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED": False}, {"BAICHUAN_FACT_WRITE_ENABLED": False}]:
            with self.subTest(flags=flags), override_settings(**flags), self.assertRaises(BaichuanError):
                self.apply()
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_reader_inactive_and_password_change_identity_cannot_write(self):
        with self.assertRaises(BaichuanError):
            self.apply(actor=self.reader)
        for field in ['is_active', 'must_change_password']:
            setattr(self.actor, field, field == 'must_change_password')
            self.actor.save()
            with self.assertRaises(BaichuanError):
                self.apply()
            setattr(self.actor, field, field == 'is_active')
            self.actor.save()
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_stale_boolean_float_version_and_other_scope_are_rejected(self):
        for version in [2, True, 3.0, None]:
            with self.subTest(version=version), self.assertRaises(BaichuanError):
                self.apply(version=version)
        with self.assertRaises(BaichuanError):
            self.apply(scope='other-scope')
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_three_actual_public_shapes_preserve_unknowns_and_general_requirement(self):
        # Representative original public shapes: reassessment grade3, grade2, ungraded YH.
        variants = [self.record(), self.record(certificateName='二级', certificateCode='ITSS-YW-2-610020230016'),
            self.record(certificateName='通用要求', certificateCode='ITSS-YW-YH-610020230017')]
        for index, record in enumerate(variants):
            result = self.apply(record=record, version=3 + index)
            cert = BaichuanCertificate.objects.get(pk=result['certificate_id'])
            self.assertEqual(cert.grade, ['3', '2', ''][index])
            self.assertIsNone(cert.valid_from)
            self.assertIsNone(cert.verified_at)
            self.assertEqual((cert.issuer, cert.standard, cert.scope_text, cert.revocation_status), ('', '', '', 'unknown'))
            self.assertEqual(cert.verification_status, 'unverified')
            self.assertIsNone(cert.evidence.verified_on)
            self.assertFalse(cert.evidence.subject['identity_verified'])
            self.assertEqual(cert.evidence.subject['public_record']['startDate'], record['startDate'])
            self.assertEqual(cert.source_revision.verification_status, 'unverified')
        self.assertFalse(CompanyQualification.objects.exists())

    def test_complete_identical_replay_has_zero_record_and_version_increment(self):
        record = self.record()
        source = self.source(record)
        first = self.apply(record, source)
        before = self.counts()
        # Replay tolerates the old reviewed baseline; no later manual fact is rewritten.
        Company.objects.filter(pk=self.company.pk).update(version=8)
        again = self.apply(record, source)
        self.assertTrue(again['replayed'])
        self.assertEqual(first['certificate_id'], again['certificate_id'])
        self.assertEqual(self.counts(), (*before[:3], 8))

    def test_source_or_raw_record_changes_are_not_incorrectly_deduplicated(self):
        record = self.record()
        source = self.source(record)
        first = self.apply(record, source)
        changed = self.record(getDate='2026-02-01')
        changed_source = self.source(changed)
        second = self.apply(changed, changed_source, version=4)
        self.assertNotEqual(first['certificate_id'], second['certificate_id'])
        self.assertEqual(second['conflicts'], [first['certificate_id']])
        original = BaichuanCertificate.objects.get(pk=first['certificate_id'])
        self.assertEqual(original.evidence.subject['public_record']['getDate'], '2026-01-27')
        self.assertEqual(BaichuanCertificate.objects.get(pk=second['certificate_id']).verification_status, 'conflict')
        before_replay = self.counts()
        replay = self.apply(changed, changed_source, version=4)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['conflicts'], [first['certificate_id']])
        self.assertEqual(self.counts(), before_replay)

    def test_legacy_same_grade_and_manual_number_remain_byte_for_byte(self):
        legacy = CompanyQualification.objects.create(company=self.company, category='itss', status='PRESENT', grade='3',
            certificate_no='MANUAL-NUMBER', source='untouched manual original')
        map_legacy_qualifications(self.company, self.actor)
        old_legacy = list(CompanyQualification.objects.values())
        old_cert = list(BaichuanCertificate.objects.values())
        self.apply()
        self.assertEqual(list(CompanyQualification.objects.values()), old_legacy)
        self.assertEqual(list(BaichuanCertificate.objects.filter(legacy_qualification_id=legacy.pk).values()), old_cert)
        self.company.refresh_from_db()
        self.assertEqual((self.company.phone, self.company.source, self.company.version), ('000-protected-manual-phone', 'protected-original', 4))

    def test_same_number_manual_dates_are_conflict_without_overwrite(self):
        record = self.record()
        old = BaichuanCertificate.objects.create(company=self.company, category='itss', certificate_no=record['certificateCode'],
            grade='3', holder_name=self.company.name, valid_until='2027-01-01', verification_status='unverified')
        before = list(BaichuanCertificate.objects.filter(pk=old.pk).values())
        result = self.apply(record)
        self.assertEqual(result['conflicts'], [str(old.pk)])
        self.assertEqual(list(BaichuanCertificate.objects.filter(pk=old.pk).values()), before)

    def test_verified_same_number_cannot_hide_new_public_conflict(self):
        today = timezone.localdate()
        evidence = BaichuanEvidence.objects.create(scope='observation-tests', source_type='fixture',
            url='https://example.com/cert', retrieved_at=timezone.now(), verified_on=today,
            content_hash='a' * 64, excerpt='Isolated original verified source', locator={'page': 1}, access_status='verified',
            subject={'company_id': str(self.company.pk), 'identity_verified': True, 'holder_type': 'bidder',
                'scope_verified': True, 'authority': 'issuer', 'revocation_checked': True,
                'revocation_checked_on': today.isoformat()})
        old = BaichuanCertificate.objects.create(company=self.company, category='itss', grade='3', holder_type='bidder',
            holder_name=self.company.name, holder_company_id=self.company.pk, certificate_no=self.record()['certificateCode'],
            valid_from=today - timedelta(days=1), valid_until=today + timedelta(days=20), verification_status='verified',
            assertion_status='PRESENT', revocation_status='clear', evidence=evidence, verified_at=timezone.now())
        compiled = compile_conditions({'schema_version': 1, 'revision': 1, 'must': {'field':'qualification', 'op':'grade_exact', 'value':'3', 'category':'itss', 'holder':'bidder'}}, today=today)
        rules = {'itss': {'enabled':True, 'version':'isolated', 'source':'https://example.com/isolated-rule', 'grades':['3'], 'at_least':{}}}
        self.assertEqual(evaluate_conditions(compiled, company_facts(self.company), rules=rules)['verdict'], 'satisfied')
        previous = list(BaichuanCertificate.objects.filter(pk=old.pk).values())
        result = self.apply()
        evaluated = evaluate_conditions(compiled, company_facts(self.company), rules=rules)
        self.assertEqual((evaluated['verdict'], evaluated['status']), ('conflict', 'candidate'))
        self.assertEqual(list(BaichuanCertificate.objects.filter(pk=old.pk).values()), previous)
        cert = BaichuanCertificate.objects.get(pk=result['certificate_id'])
        self.assertEqual(cert.verification_status, 'conflict')
        self.assertIsNone(cert.verified_at)
        self.assertEqual(cert.source_revision.verification_status, 'unverified')
        self.assertEqual(cert.source_revision.review_status, 'public_conflict')

    def test_new_unknowns_do_not_conflict_with_old_known_verified_fields(self):
        record = self.record()
        old = BaichuanCertificate.objects.create(company=self.company, category='itss', grade='3', raw_grade='ITSS三级同义',
            raw_category='ITSS运维同义', certificate_no=record['certificateCode'], holder_type='bidder',
            holder_name=self.company.name, holder_company_id=self.company.pk,
            issuer='Previously known issuer', standard='Previously known standard', scope_text='Previously known scope',
            valid_from=timezone.localdate() - timedelta(days=5), valid_until=record['endDate'],
            verification_status='verified', verified_at=timezone.now(), revocation_status='clear', assertion_status='PRESENT')
        previous = list(BaichuanCertificate.objects.filter(pk=old.pk).values())
        result = self.apply(record)
        self.assertEqual(result['conflicts'], [])
        self.assertEqual(BaichuanCertificate.objects.get(pk=result['certificate_id']).verification_status, 'unverified')
        self.assertEqual(list(BaichuanCertificate.objects.filter(pk=old.pk).values()), previous)

    def test_full_preflight_does_not_create_records_or_CAS(self):
        record = self.record()
        result = record_public_certificate_observation(self.actor, self.company.pk, record, self.source(record), 3,
            scope='observation-tests', validate_only=True)
        self.assertTrue(result['validate_only'])
        self.assertEqual(self.counts(), (0,0,0,3))

    def test_full_body_hash_locator_assertion_identity_and_origin_fail_closed(self):
        record = self.record()
        source = self.source(record)
        invalid = []
        for key, value in [('content_sha256', '0' * 64), ('excerpt', 'search snippet'), ('read_status', 'snippet'),
            ('url', 'http://www.itss.cn/api/itss/web/certificate/' + '1' * 32),
            ('url', 'https://127.0.0.1/api/itss/web/certificate/' + '1' * 32),
            ('url', 'https://www.itss.cn/api/itss/web/certificate/?orgName=x'),
            ('retrieved_at', (timezone.now() + timedelta(days=1)).isoformat()), ('publication_kind', 'model_output')]:
            case = copy.deepcopy(source)
            case[key] = value
            invalid.append(case)
        case = copy.deepcopy(source)
        case['locator']['text_start'] = True
        invalid.append(case)
        case = copy.deepcopy(source)
        case['field_assertions']['certificateCode'] = ['unrelated']
        invalid.append(case)
        for case in invalid:
            with self.subTest(case=case), self.assertRaises(BaichuanError):
                self.apply(record, case)
        for changed in [self.record(orgName='Other company'), self.record(issuer='unsupported'), self.record(endDate='not-date')]:
            with self.subTest(changed=changed), self.assertRaises(BaichuanError):
                self.apply(changed)
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_midtransaction_failure_rolls_back_evidence_revision_certificate_and_CAS(self):
        with patch.object(BaichuanCertificate, 'save', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):
                self.apply()
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_CAS_rechecks_revoked_permission_and_rolls_back(self):
        from portal import baichuan_facts
        actual = baichuan_facts._cas_company
        def revoked(company, actor, **values):
            actor.is_active = False
            actor.save(update_fields=['is_active'])
            return actual(company, actor, **values)
        with patch.object(baichuan_facts, '_cas_company', side_effect=revoked), self.assertRaises(BaichuanError):
            self.apply()
        self.assertEqual(self.counts(), (0, 0, 0, 3))

    def test_replay_rejects_changed_certificate_linkage_or_fields(self):
        record = self.record()
        source = self.source(record)
        result = self.apply(record, source)
        cert = BaichuanCertificate.objects.get(pk=result['certificate_id'])
        cert.issuer = 'unreviewed tampering'
        cert.save(update_fields=['issuer'])
        before = self.counts()
        with self.assertRaises(BaichuanError):
            self.apply(record, source)
        self.assertEqual(self.counts(), before)

    def test_replay_rejects_changed_evidence_and_revision_binding(self):
        record = self.record()
        source = self.source(record)
        result = self.apply(record, source)
        before = self.counts()
        evidence = BaichuanEvidence.objects.get(pk=result['evidence_id'])
        original_subject = copy.deepcopy(evidence.subject)
        # The append-only manager rejects ORM updates too. Simulate corruption
        # only through SQL inside this disposable test database.
        def corrupt(model, pk, field, value):
            table = connection.ops.quote_name(model._meta.db_table)
            column = connection.ops.quote_name(model._meta.get_field(field).column)
            prepared = model._meta.get_field(field).get_db_prep_save(value, connection)
            identifier = model._meta.pk.get_db_prep_value(pk, connection)
            with connection.cursor() as cursor:
                cursor.execute(f'UPDATE {table} SET {column}=%s WHERE id=%s', [prepared, identifier])
        corrupt(BaichuanEvidence, evidence.pk, 'subject', {**original_subject, 'identity_verified':True})
        with self.assertRaises(BaichuanError):
            self.apply(record, source)
        corrupt(BaichuanEvidence, evidence.pk, 'subject', original_subject)
        corrupt(BaichuanFactRevision, uuid.UUID(result['revision_id']), 'field', 'certificate')
        with self.assertRaises(BaichuanError):
            self.apply(record, source)
        self.assertEqual(self.counts(), before)

    def test_new_observation_stays_unknown_and_old_snapshot_is_immutable(self):
        conversation = BaichuanConversation.objects.create(owner=self.actor, scope='observation-tests')
        job = BaichuanJob.objects.create(owner=self.actor, scope='observation-tests', conversation=conversation, kind='query')
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
            result_revision=1, condition_tree={'old': True}, results=[{'immutable': True}], fact_cutoff_at=timezone.now())
        old = list(BaichuanMatchSnapshot.objects.values())
        self.apply()
        facts = company_facts(self.company)
        compiled = compile_conditions({'schema_version': 1, 'revision': 1,
            'must': {'field': 'qualification', 'category': 'itss', 'op': 'grade_exact', 'holder': 'bidder', 'value': '3'}}, today=timezone.localdate())
        result = evaluate_conditions(compiled, facts, rules={'itss': {'enabled': True, 'version': 'test', 'source':'https://example.com/isolated-rule', 'grades': ['1','2','3','4'], 'at_least': {}}})
        self.assertEqual((result['verdict'], result['status']), ('unknown', 'candidate'))
        self.assertIn('现有证书不足', result['conditions'][0]['reason'])
        self.assertEqual(list(BaichuanMatchSnapshot.objects.values()), old)


class PublicationDefaultGateTests(SimpleTestCase):
    def test_no_deployment_setting_enables_the_publication_gate(self):
        self.assertFalse(getattr(settings, 'BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED', False))


class PublicCertificateCLITests(SimpleTestCase):
    def setUp(self):
        self.scripts = Path(__file__).resolve().parents[5] / 'scripts/baichuan'
        spec = importlib.util.spec_from_file_location('public_certificate_maintenance_cli_tests', self.scripts / 'apply_public_certificate_observations.py')
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def artifact(self, directory):
        body = '{"orgName":"Synthetic fixture","certificateCode":"ITSS-YW-3-TEST"}'
        raw = directory / 'fixture.raw'
        txt = directory / 'fixture.txt'
        receipt = directory / 'fixture.receipt.json'
        raw.write_text(body, encoding='utf-8')
        txt.write_text(body, encoding='utf-8')
        source = {'body': body, 'content_sha256': self.cli.sha(txt),
            'url': 'https://www.itss.cn/api/itss/web/certificate/' + '1' * 32, 'retrieved_at':'2026-10-17T20:00:00+00:00'}
        details = {'status':'completed','http_status':200,'url':source['url'],'at':source['retrieved_at'],
            'tls_standard_verification':True,'body_sha256':self.cli.sha(txt),'raw_sha256':self.cli.sha(raw),
            'raw_file':raw.name,'body_file':txt.name,'public_ips':['47.94.8.148']}
        receipt.write_text(json.dumps(details), encoding='utf-8')
        item = {'source':source,'provenance':{'raw_file':raw.name,'raw_sha256':self.cli.sha(raw),
            'body_file':txt.name,'body_sha256':self.cli.sha(txt),'receipt_file':receipt.name,'receipt_sha256':self.cli.sha(receipt)}}
        return item, details, receipt

    def test_default_cli_is_inert_even_with_a_batch_path(self):
        output = StringIO()
        with patch.object(sys,'argv',['maintenance','--batch','must-not-read.json']), redirect_stdout(output), \
                patch('sqlite3.connect', side_effect=AssertionError('SQL forbidden')), \
                patch('socket.getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            self.cli.main()
        self.assertEqual(json.loads(output.getvalue())['mode'], 'inert')

    def test_real_raw_body_receipt_binding_and_modified_body_attack(self):
        with TemporaryDirectory() as temp, patch.object(sys,'path',[str(self.scripts), *sys.path]):
            directory=Path(temp)
            item, details, receipt = self.artifact(directory)
            self.cli.validate_provenance(item, directory)
            changed = item['source']['body'].replace('ITSS-YW-3-TEST','ITSS-YW-2-FAKE')
            (directory/'fixture.txt').write_text(changed, encoding='utf-8')
            item['source']['body']=changed
            item['source']['content_sha256']=self.cli.sha(directory/'fixture.txt')
            item['provenance']['body_sha256']=item['source']['content_sha256']
            details['body_sha256']=item['source']['content_sha256']
            receipt.write_text(json.dumps(details), encoding='utf-8')
            item['provenance']['receipt_sha256']=self.cli.sha(receipt)
            with self.assertRaises(ValueError):
                self.cli.validate_provenance(item, directory)

    def test_cross_directory_or_false_receipt_source_are_refused(self):
        with TemporaryDirectory() as temp, patch.object(sys,'path',[str(self.scripts), *sys.path]):
            directory=Path(temp)
            item, details, receipt = self.artifact(directory)
            other=directory/'other'
            other.mkdir()
            (other/'fixture.txt').write_bytes((directory/'fixture.txt').read_bytes())
            item['provenance']['body_file']='other/fixture.txt'
            with self.assertRaises(ValueError):
                self.cli.validate_provenance(item,directory)
            item['provenance']['body_file']='fixture.txt'
            details['url']='https://www.itss.cn/api/itss/web/certificate/'+'2'*32
            receipt.write_text(json.dumps(details),encoding='utf-8')
            item['provenance']['receipt_sha256']=self.cli.sha(receipt)
            with self.assertRaises(ValueError):
                self.cli.validate_provenance(item,directory)
