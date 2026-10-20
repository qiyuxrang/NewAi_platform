"""AC08/09 gaps through real isolated snapshot/API and manifest/worker paths.

Only public provider boundaries are fixtures. No live model, DNS, socket, owned
catalog, frontend or service is used; older broad strategy tests are not rerun.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from portal.baichuan_assistant_api import results
from portal.baichuan_assistant_models import (BaichuanCertificate, BaichuanConversation,
    BaichuanEvidence, BaichuanFactRevision, BaichuanJob, BaichuanMatchSnapshot)
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_jobs import claim_job, enqueue_job, save_job
from portal.baichuan_matching import save_match_snapshot
from portal.baichuan_models import Company
from portal.baichuan_research import create_manifest, research_report
from portal.product_service import ProductError
from .base import PortalTestCase


class AcceptanceGapMatrixTests(PortalTestCase):
    def setUp(self):
        self.actor = self.create_user('acceptance-gap-maintainer', 'product')
        self.temp = TemporaryDirectory(prefix='baichuan-acceptance-gap-')
        self.addCleanup(self.temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True,
            BAICHUAN_ASSISTANT_SCOPE='acceptance-gap', BAICHUAN_STORAGE_ROOT=self.temp.name,
            BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
            BAICHUAN_DATASET_KIND='isolation', BAICHUAN_ENVIRONMENT_LABEL='synthetic AC08/09 only',
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.actor.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        for target in ('socket.create_connection', 'socket.getaddrinfo',
                'socket.socket.connect', 'socket.socket.connect_ex',
                'portal.baichuan_assistant_worker.generate_for_use'):
            guard = patch(target, side_effect=AssertionError('No live providers in acceptance gap matrix'))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)
        # The runner owns a fresh file-SQLite. A surprise second SQLite path,
        # including a mode=ro owned catalog connection, must fail this test.
        from django.db import connection
        allowed = Path(connection.settings_dict['NAME']).resolve()
        self.assertIn('baichuan-checks', allowed.parts)
        for target in ('sqlite3.connect', 'sqlite3.dbapi2.connect'):
            original = sqlite3.connect if target == 'sqlite3.connect' else sqlite3.dbapi2.connect
            def checked(database, *args, _original=original, **kwargs):
                self.assertEqual(Path(str(database)).resolve(), allowed)
                return _original(database, *args, **kwargs)
            guard = patch(target, side_effect=checked)
            guard.start()
            self.addCleanup(guard.stop)

    def company(self, **values):
        return Company.objects.create(name='公开合成验收缺口甲有限公司',
            created_by=self.actor, updated_by=self.actor, **values)

    def snapshot(self):
        conversation = BaichuanConversation.objects.create(owner=self.actor,
            scope='acceptance-gap', condition_revision=1)
        queued, _ = enqueue_job(self.actor, kind='query', payload={'condition_revision': 1},
            idempotency_key='existing-fixed-query', conversation=conversation)
        job = claim_job('gap-matcher', job_id=queued.pk)
        tree = {'schema_version': 1, 'revision': 1,
            'must': {'all': [
                {'field': 'qualification', 'category': 'electronic', 'op': 'grade_exact',
                    'value': '2', 'holder': 'bidder'},
                {'field': 'company.city', 'op': 'eq', 'value': '西安市'}]},
            'output': {'fields': ['name', 'phone'], 'limit': 20}, 'unresolved': []}
        snapshot = save_match_snapshot(self.actor, job.pk, 'gap-matcher', job.fence, tree,
            research_status='not_requested')
        save_job(job.pk, 'gap-matcher', job.fence, status='completed')
        return snapshot

    def snapshot_api(self, snapshot):
        request = APIRequestFactory().get('/synthetic/results/', {'page': 1, 'page_size': 50})
        force_authenticate(request, self.actor)
        response = results(request, snapshot.pk)
        self.assertEqual(response.status_code, 200)
        return response.data

    @staticmethod
    def digest(snapshot):
        snapshot.refresh_from_db()
        return hashlib.sha256(json.dumps({field: getattr(snapshot, field) for field in
            ('condition_tree', 'results', 'counts', 'fact_cutoff_at')},
            ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    def test_zero_confirmed_api_retains_exact_scope_and_each_unknown_gap(self):
        company = self.company(phone='SYNTHETIC_MANUAL_PHONE')
        snapshot = self.snapshot()
        before = self.digest(snapshot)
        data = self.snapshot_api(snapshot)
        self.assertEqual(data['counts'], {'confirmed': 0, 'candidate': 1, 'excluded': 0})
        self.assertEqual((data['total'], data['page'], data['page_size']), (1, 1, 50))
        self.assertEqual(data['conditions'], snapshot.condition_tree)
        must = data['conditions']['must']['all']
        self.assertEqual((must[0]['op'], must[0]['value'], must[0]['holder']), ('grade_exact', '2', 'bidder'))
        self.assertEqual((must[1]['op'], must[1]['value']), ('eq', '西安市'))
        self.assertEqual(data['research_status'], 'not_requested')
        self.assertEqual(data['results'][0]['company_id'], str(company.pk))
        row = data['results'][0]
        self.assertEqual((row['status'], row['verdict']), ('candidate', 'unknown'))
        self.assertEqual(len(row['conditions']), 2)
        self.assertTrue(all(c['verdict'] == 'unknown' and c['reason'].strip() for c in row['conditions']))
        self.assertEqual(data['evidence'], {})  # Missing citations are not fabricated.
        self.assertEqual(self.digest(snapshot), before)
        self.assertFalse(BaichuanEvidence.objects.exists())
        self.assertFalse(BaichuanFactRevision.objects.exists())

    def test_true_empty_api_has_zero_scope_counts_and_keeps_conditions_without_fake_rows(self):
        self.assertFalse(Company.objects.exists())
        snapshot = self.snapshot()
        before = self.digest(snapshot)
        data = self.snapshot_api(snapshot)
        self.assertEqual((data['total'], data['results'], data['evidence']), (0, [], {}))
        self.assertEqual(data['counts'], {'confirmed': 0, 'candidate': 0, 'excluded': 0})
        self.assertEqual(data['conditions'], snapshot.condition_tree)
        self.assertEqual(data['conditions']['must']['all'][0]['op'], 'grade_exact')
        self.assertEqual(data['conditions']['must']['all'][0]['value'], '2')
        self.assertEqual(self.digest(snapshot), before)
        self.assertFalse(Company.objects.exists())

    def manifest(self, *, max_sources):
        self.old_snapshot = self.snapshot()
        self.old_digest = self.digest(self.old_snapshot)
        self.company_before = list(Company.objects.order_by('pk').values())
        self.manifest_row, _ = create_manifest(self.actor, 'independent-failure-matrix',
            fields=['phone', 'email'], budget={'timeout_seconds': 30, 'max_sources': max_sources,
                'max_model_calls': 1, 'max_attempts': 1})
        return self.manifest_row

    def assert_protected(self):
        self.assertEqual(list(Company.objects.order_by('pk').values()), self.company_before)
        self.assertEqual(self.digest(self.old_snapshot), self.old_digest)
        self.assertEqual(BaichuanMatchSnapshot.objects.count(), 1)
        self.assertEqual(BaichuanJob.objects.count(), 2)
        self.assertFalse(BaichuanCertificate.objects.exists())
        job = BaichuanJob.objects.get(pk=self.manifest_row.job_id)
        self.assertEqual((job.status, job.lease_owner, job.lease_expires_at), ('completed', '', None))
        report = research_report(self.actor, self.manifest_row.pk)
        self.assertEqual((report['total_companies'], report['total_fields'],
            report['verified_fields'], report['fully_verified_companies']), (1, 2, 0, 0))
        self.assertEqual(self.manifest_row.company_versions,
            [{'id': str(self.target.pk), 'version': self.target.version}])
        return job, report

    def test_independent_slow_timeout_and_search_failure_spend_bounded_real_budget(self):
        self.target = self.company(website='https://timeout.example.test/', phone='MANUAL_UNCHANGED')
        self.manifest(max_sources=4)
        delays = []
        def timeout(url):
            self.assertEqual(url, self.target.website)
            start = time.perf_counter()
            time.sleep(0.01)  # Controlled delayed provider timeout, not a real HTTP request.
            delays.append(time.perf_counter() - start)
            raise TimeoutError('synthetic delayed provider timeout')
        with patch('portal.baichuan_research_runtime.search_public_query',
                side_effect=ProductError('web_search_unavailable', 'synthetic unavailable', 503)) as search, \
                patch('portal.baichuan_research_runtime.fetch_public_page', side_effect=timeout) as fetch, \
                patch('portal.baichuan_research_runtime.generate_for_use') as model:
            started = time.perf_counter()
            self.assertTrue(run_one('gap-research', self.manifest_row.job_id))
            elapsed = time.perf_counter() - started
        self.assertEqual((search.call_count, fetch.call_count, model.call_count), (1, 3, 0))
        self.assertEqual(len(delays), 3)
        self.assertTrue(all(seconds >= 0.009 for seconds in delays))
        self.assertLess(elapsed, 10)
        job, report = self.assert_protected()
        self.assertEqual((job.counts['_budget_sources'], job.counts.get('_budget_model_calls', 0)), (4, 0))
        self.assertEqual(report['field_statuses']['inaccessible'], 2)
        source = BaichuanEvidence.objects.get(source_type='web')
        self.assertEqual((source.access_status, source.locator['attempts'], source.locator['error_code']),
            ('inaccessible', 3, 'source_network_unavailable'))
        discovery = BaichuanEvidence.objects.get(source_type='search_index')
        self.assertEqual(discovery.locator['error_code'], 'web_search_unavailable')
        self.assertFalse(BaichuanFactRevision.objects.exists())

    def test_search_summary_phone_is_not_body_when_actual_page_is_unreadable(self):
        self.target = self.company(phone='MANUAL_UNCHANGED')
        self.manifest(max_sources=2)
        url = 'https://unreadable.example.test/'
        summary = self.target.name + ' 企业电话029-12345678 企业邮箱public@example.test'
        with patch('portal.baichuan_research_runtime.search_public_query',
                return_value=[{'title': self.target.name, 'text': summary, 'url': url}]) as search, \
                patch('portal.baichuan_research_runtime.fetch_public_page', side_effect=ValueError('unsupported')) as fetch, \
                patch('portal.baichuan_research_runtime.generate_for_use') as model:
            self.assertTrue(run_one('gap-research', self.manifest_row.job_id))
        self.assertEqual((search.call_count, fetch.call_count, model.call_count), (1, 1, 0))
        job, report = self.assert_protected()
        self.assertEqual((job.counts['_budget_sources'], job.counts.get('_budget_model_calls', 0)), (2, 0))
        self.assertEqual(report['field_statuses']['inaccessible'], 2)
        self.assertFalse(BaichuanFactRevision.objects.exists())
        web = BaichuanEvidence.objects.get(source_type='web')
        self.assertEqual((web.excerpt, web.content_hash, web.locator['attempts']), ('', '', 1))
        self.assertEqual(web.locator['error_code'], 'source_inaccessible_or_unsupported')
        self.assertFalse(BaichuanEvidence.objects.filter(access_status='verified').exists())

    def test_two_own_bodies_preserve_conflicts_manual_value_old_snapshot_and_exact_budget(self):
        self.target = self.company(website='https://company.example.test/', website_kind='corporate',
            credit_code='916100000000000001', phone='029-88888888')
        self.manifest(max_sources=3)
        contact = self.target.website + 'contact'
        bodies = {self.target.website: self.target.name + '\n916100000000000001\n公司电话029-12345678',
            contact: self.target.name + '\n916100000000000001\n公司电话029-87654321'}
        def extract(actor, route, messages, **kwargs):
            sources = json.loads(messages[-1]['content'])['sources']
            self.assertEqual({s['text'] for s in sources}, set(bodies.values()))
            return {'content': json.dumps({'facts': [{'field': 'phone', 'value': source['text'].split('公司电话')[1],
                'quote': '公司电话' + source['text'].split('公司电话')[1], 'source_id': source['source_id']}
                for source in sources], 'certificates': []})}
        with patch('portal.baichuan_research_runtime.search_public_query',
                return_value=[{'title': self.target.name, 'url': contact}]) as search, \
                patch('portal.baichuan_research_runtime.fetch_public_page', side_effect=bodies.__getitem__) as fetch, \
                patch('portal.baichuan_research_runtime.generate_for_use', side_effect=extract) as model:
            self.assertTrue(run_one('gap-research', self.manifest_row.job_id))
        self.assertEqual((search.call_count, fetch.call_count, model.call_count), (1, 2, 1))
        job, report = self.assert_protected()
        self.assertEqual((job.counts['_budget_sources'], job.counts['_budget_model_calls']), (3, 1))
        revisions = list(BaichuanFactRevision.objects.order_by('new_value'))
        self.assertEqual({r.new_value for r in revisions}, {'029-12345678', '029-87654321'})
        self.assertTrue(all((r.review_status, r.verification_status, r.old_value) ==
            ('conflict', 'conflict', '029-88888888') for r in revisions))
        self.assertTrue(all(r.evidence.subject['identity_verified'] is True and
            r.new_value in r.evidence.subject['field_assertions']['phone'] for r in revisions))
        self.assertEqual(report['field_statuses']['pending_review'], 1)
        self.assertEqual(report['field_statuses']['not_found'], 1)
        self.assertFalse(BaichuanFactRevision.objects.filter(review_status='applied').exists())
