"""Queries never start research, even with the legacy research switch enabled."""
from contextlib import ExitStack
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import (BaichuanConversation, BaichuanEvidence, BaichuanFactRevision,
    BaichuanJob, BaichuanMatchSnapshot, BaichuanResearchManifest)
from portal.baichuan_assistant_service import store_attachment, submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_jobs import claim_job, retry_job, save_job
from portal.baichuan_models import Company
from portal.baichuan_research import create_manifest, research_report
from .base import PortalTestCase


def tree():
    return {"schema_version": 1, "revision": 1, "must": {"field": "qualification", "category": "itss",
        "op": "grade_exact", "value": "2", "holder": "bidder"}}


class QueryResearchPolicyTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('query-policy-owner', 'product')
        self.temp = TemporaryDirectory(prefix='baichuan-query-policy-')
        self.addCleanup(self.temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE='query-policy-test',
            BAICHUAN_STORAGE_ROOT=self.temp.name, BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
            BAICHUAN_DATASET_KIND='isolation', BAICHUAN_ENVIRONMENT_LABEL='虚构查询边界测试',
            PRODUCT_WEB_SEARCH_ENABLED=True, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name='查询策略虚构企业', website='https://fixture.example.test/',
            source='原有人工资料', phone='001234', created_by=self.owner, updated_by=self.owner)
        self.company_before = list(Company.objects.values())
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.guards = [self.stack.enter_context(patch('portal.baichuan_research_runtime.' + name,
            side_effect=AssertionError('A user query must not call research: ' + name))) for name in (
                'run_query_research', '_research_company', 'search_public_query', 'fetch_public_page', 'generate_for_use')]

    def send(self, conversation=None, *, text='ITSS二级企业', key='query', parent=0, attachment_ids=None):
        conversation = conversation or BaichuanConversation.objects.create(owner=self.owner, scope='query-policy-test')
        _, job, _ = submit_message(self.owner, conversation.pk, {'text': text, 'client_request_id': key,
            'parent_revision': parent, 'attachment_ids': attachment_ids or []})
        return conversation, job

    def run_query(self, job, conditions=None, *, expected_condition_calls=1):
        with patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(conditions or tree())}) as condition_model:
            self.assertTrue(run_one('query-policy-worker', job.pk))
        self.assertEqual(condition_model.call_count, expected_condition_calls)
        job.refresh_from_db()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.checkpoint['research_policy'], 'independent_manifest_only')
        self.assertEqual(job.checkpoint['capability_gaps'], [])
        self.assertEqual(job.snapshots.count(), 1)
        snapshot = job.snapshots.get()
        self.assertEqual(snapshot.research_status, 'not_requested')
        self.assertEqual(snapshot.counts['candidate'], 1)
        self.assertEqual(snapshot.counts['confirmed'], 0)
        for guard in self.guards:
            guard.assert_not_called()
        self.assertEqual(list(Company.objects.values()), self.company_before)
        self.assertFalse(BaichuanResearchManifest.objects.exists())
        self.assertFalse(BaichuanEvidence.objects.exists())
        self.assertFalse(BaichuanFactRevision.objects.exists())
        return snapshot

    def test_plain_query_does_not_research_even_when_research_and_fact_writes_are_enabled(self):
        _, job = self.send()
        self.run_query(job)
        self.assertEqual(BaichuanJob.objects.count(), 1)

    @override_settings(BAICHUAN_RESEARCH_ENABLED=False)
    def test_query_completes_without_false_research_disabled_gap(self):
        _, job = self.send()
        self.run_query(job)

    def test_file_only_query_uses_shared_matching_path_and_never_researches(self):
        conversation = BaichuanConversation.objects.create(owner=self.owner, scope='query-policy-test')
        attachment = store_attachment(self.owner, conversation.pk, SimpleUploadedFile('fixture.pdf', b'%PDF-1.7\nfixture'))
        _, job = self.send(conversation, text='', attachment_ids=[str(attachment.pk)])
        parsed = {'status': 'completed', 'blocks': [{'id': 'b1', 'text': '投标人具备ITSS二级',
            'location': {'page': 1}}], 'warnings': []}
        conditions = tree()
        conditions['source_refs'] = [f'attachment:{attachment.pk}:b1']
        conditions['must']['source_refs'] = conditions['source_refs']
        with patch('portal.baichuan_assistant_worker.run_parser', return_value=parsed) as parser:
            snapshot = self.run_query(job, conditions)
        parser.assert_called_once()
        attachment.refresh_from_db()
        self.assertEqual(attachment.parse_status, 'completed')
        self.assertEqual(snapshot.condition_tree['source_refs'], conditions['source_refs'])
        self.assertEqual(snapshot.condition_tree['must']['source_refs'], conditions['source_refs'])

    def test_followup_and_explicit_export_do_not_create_research_jobs(self):
        conversation, first = self.send()
        self.run_query(first)
        _, followup = self.send(conversation, text='继续精确二级，导出前5条Excel', key='followup', parent=1)
        self.run_query(followup)
        exported = BaichuanJob.objects.get(kind='export')
        self.assertTrue(run_one('query-policy-export', exported.pk))
        exported.refresh_from_db()
        self.assertEqual(exported.status, 'completed')
        self.assertFalse(BaichuanJob.objects.filter(kind='research').exists())
        for guard in self.guards:
            guard.assert_not_called()

    def test_linked_retry_of_legacy_partial_query_cannot_restart_old_research(self):
        _, old = self.send()
        claimed = claim_job('legacy-partial', job_id=old.pk)
        compiled = compile_conditions(tree(), today=timezone.localdate())
        save_job(old.pk, 'legacy-partial', claimed.fence, status='partial',
            checkpoint={'conditions': compiled, 'query_research_done': {}, 'capability_gaps': ['old_research_failure']},
            counts={'researched_companies': 1})
        fresh, created = retry_job(self.owner, old.pk, idempotency_key='explicit-query-retry')
        self.assertTrue(created)
        self.run_query(fresh, expected_condition_calls=0)
        fresh.refresh_from_db()
        self.assertEqual(fresh.parent_job_id, old.pk)
        self.assertEqual(fresh.counts['researched_companies'], 1)  # Historical checkpoint, no new research.
        self.assertEqual(fresh.counts.get('_budget_model_calls', 0), 0)

    def test_resume_committed_old_snapshot_keeps_history_without_research_revision(self):
        conversation, job = self.send()
        compiled = compile_conditions(tree(), today=timezone.localdate())
        snapshot = BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job, condition_revision=1,
            result_revision=2, condition_tree=compiled, counts={'confirmed': 0, 'candidate': 1, 'excluded': 0},
            fact_cutoff_at=timezone.now(), research_status='partial')
        job.checkpoint = {'conditions': compiled}
        job.save(update_fields=['checkpoint'])
        with patch('portal.baichuan_assistant_worker.generate_for_use', side_effect=AssertionError('No new model')):
            self.assertTrue(run_one('resume-old-snapshot', job.pk))
        job.refresh_from_db()
        snapshot.refresh_from_db()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(snapshot.research_status, 'partial')
        self.assertEqual(job.snapshots.count(), 1)
        self.assertEqual(job.result_ref['snapshot_id'], str(snapshot.pk))
        for guard in self.guards:
            guard.assert_not_called()

    def test_independent_manifest_worker_still_researches_and_records_fixed_field_progress(self):
        manifest, created = create_manifest(self.owner, 'independent-still-available', fields=['phone', 'website'])
        self.assertTrue(created)
        outcome = {'sources': [], 'readable': True, 'facts': [], 'certificates': [], 'cache_hits': 0,
                   'gaps': [], 'extraction_failed': False, 'search_error': ''}
        with patch('portal.baichuan_research_runtime._research_company', return_value=outcome) as independent:
            self.assertTrue(run_one('independent-manifest-worker', manifest.job_id))
        independent.assert_called_once()
        self.assertEqual(independent.call_args.args[2].pk, self.company.pk)
        self.assertEqual(set(independent.call_args.args[3]), {'phone', 'website'})
        report = research_report(self.owner, manifest.pk)
        self.assertEqual(report['state'], 'completed')
        self.assertEqual(report['total_companies'], 1)
        self.assertEqual(report['field_statuses']['not_found'], 2)
        self.assertEqual(report['verified_fields'], 0)
        self.assertFalse(BaichuanMatchSnapshot.objects.exists())
        self.assertEqual(list(Company.objects.values()), self.company_before)
