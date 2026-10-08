"""GM local capabilities retain owner, source and ledger-author boundaries."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, override_settings
from django.utils import timezone

from portal import engineering_worker, hr_screening_worker, product_worker
from portal.business_models import BusinessLedgerGrant, BusinessLedgerRevision
from portal.engineering_models import EngineeringJob
from portal.hr_agent import current_artifact
from portal.hr_recruitment_models import JDVersion, RecruitmentRequest
from portal.hr_screening_models import ResumeArtifact, ResumeScreeningBatch
from portal.models import Module
from portal.product_knowledge_service import authorize
from portal.product_models import DocumentTask
from portal.product_service import ProductError
from portal.product_storage import StorageError

from .base import PortalTestCase, json_body


class ManagerDomainWorkflowTests(PortalTestCase):
    def setUp(self):
        self.manager = self.create_user('domain-manager', 'general_manager')
        self.other = self.create_user('domain-other', 'product', 'hr', 'engineering')
        self.other_client = Client()
        self.login(self.client, self.manager)
        self.login(self.other_client, self.other)
        self.manager.refresh_from_db()
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.enterContext(override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MAX_ATTEMPTS=8,
            PRODUCT_STORAGE_ROOT=root / 'product', ENGINEERING_STORAGE_ROOT=root / 'engineering',
            PRODUCT_KNOWLEDGE_AUTHORIZATIONS={}))

    def post(self, url, client=None, **data):
        return (client or self.client).post(url, json_body(**data), content_type='application/json')

    def test_product_owner_scope_worker_reclaim_and_knowledge_grants(self):
        result = self.client.post('/api/product/tasks/', json_body(title='经理项目', input={
            'project': '经理项目', 'requirements': '技术方案', 'background': '', 'conditions': [],
            'items': []}), content_type='application/json', HTTP_IDEMPOTENCY_KEY='manager-product')
        self.assertEqual(result.status_code, 201, result.content)
        task = DocumentTask.objects.get(pk=result.json()['id'])
        detail = f'/api/product/tasks/{task.pk}/'
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual([row['id'] for row in self.client.get('/api/product/tasks/').json()], [str(task.pk)])
        self.assertEqual(self.other_client.get(detail).status_code, 404)
        foreign = DocumentTask.objects.create(owner=self.other, title='他人项目', idempotency_key='other', payload_hash='x')
        foreign_url = f'/api/product/tasks/{foreign.pk}/'
        self.assertEqual(self.client.get(foreign_url).status_code, 404)
        self.assertEqual(self.client.patch(foreign_url, json_body(expected_version=1, title='改写'),
            content_type='application/json').status_code, 404)
        self.manager.refresh_from_db()
        with self.assertRaises(ProductError) as denied:
            authorize(self.manager)
        self.assertEqual(denied.exception.code, 'scope_revoked')
        self.assertEqual(self.client.get('/api/product/knowledge/status/').json()['code'], 'scope_revoked')
        with override_settings(PRODUCT_KNOWLEDGE_ENABLED=True,
                PRODUCT_KNOWLEDGE_AUTHORIZATIONS={str(self.manager.pk): {'dataset-gm': ['document-gm']}}), \
                patch('portal.product_knowledge_service.ready', return_value=('test', 'token', 'product_knowledge')):
            self.assertEqual(authorize(self.manager)['datasets'], {'dataset-gm': ['document-gm']})
            knowledge_status = self.client.get('/api/product/knowledge/status/').json()
            self.assertEqual(knowledge_status['available'], True, knowledge_status)
            conversation = self.post('/api/product/knowledge/conversations/')
            self.assertEqual(conversation.status_code, 201, conversation.content)
            self.assertEqual(self.other_client.get(
                f"/api/product/knowledge/conversations/{conversation.json()['id']}/").status_code, 403)
        self.manager.refresh_from_db()
        DocumentTask.objects.filter(pk=task.pk).update(state='QUEUED', pending_action='analyze',
            checkpoint={'grant_version': self.manager.grant_version})
        first = product_worker.claim_task()
        self.assertIsNotNone(first)
        task.refresh_from_db()
        with transaction.atomic():
            product_worker._guard(task.pk, task.fence)
        DocumentTask.objects.filter(pk=task.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertIsNotNone(product_worker.claim_task())
        task.refresh_from_db()
        self.assertEqual(task.attempt_count, 2)
        Module.objects.filter(code='product').update(enabled=False)
        with transaction.atomic(), self.assertRaises(product_worker.ExecutionError):
            product_worker._guard(task.pk, task.fence)
        self.assertEqual(self.client.get(detail).status_code, 404)

    def test_hr_own_drafts_and_existing_manager_reads_are_separate(self):
        result = self.post('/api/hr/recruitment/requests/', position_name='经理岗位')
        self.assertEqual(result.status_code, 201, result.content)
        owned = RecruitmentRequest.objects.get(pk=result.json()['id'])
        hidden = RecruitmentRequest.objects.create(created_by=self.other, updated_by=self.other, position_name='未确认岗位')
        published = RecruitmentRequest.objects.create(created_by=self.other, updated_by=self.other, position_name='已确认岗位')
        official = JDVersion.objects.create(request=published, version=1, input_version=1,
            state='confirmed', body='已确认JD', created_by=self.other)
        published.official_jd = official
        published.save(update_fields=['official_jd'])
        root = '/api/hr/recruitment/requests/'
        rows = self.client.get(root).json()
        self.assertEqual({row['id'] for row in rows}, {str(owned.pk), str(published.pk)})
        self.assertEqual(self.client.get(f'{root}{owned.pk}/').json()['created_by_id'], self.manager.pk)
        self.assertEqual(self.client.get(f'{root}{owned.pk}/history/').status_code, 200)
        self.assertEqual(self.client.get(f'{root}{published.pk}/').status_code, 200)
        self.assertEqual([jd['id'] for jd in self.client.get(f'{root}{published.pk}/jd-versions/').json()], [str(official.pk)])
        self.assertEqual(self.post(f'{root}{published.pk}/jd-versions/', expected_version=1,
            base_jd_id=str(official.pk), body='越权').status_code, 404)
        self.assertEqual(self.client.get(f'{root}{hidden.pk}/').status_code, 404)
        for row in (hidden, published):
            self.assertEqual(self.client.patch(f'{root}{row.pk}/', json_body(expected_version=1,
                position_name='越权'), content_type='application/json').status_code, 404)
            self.assertEqual(self.client.get(f'{root}{row.pk}/history/').status_code, 404)
        self.assertEqual(self.other_client.get(f'{root}{owned.pk}/').status_code, 404)
        Module.objects.filter(code='hr').update(enabled=False)
        self.assertEqual(self.client.get(root).status_code, 403)
        self.assertEqual(self.client.get(f'{root}{published.pk}/').status_code, 403)

    def test_hr_worker_reclaims_and_stops_after_module_revocation(self):
        row = RecruitmentRequest.objects.create(created_by=self.manager, updated_by=self.manager)
        jd = JDVersion.objects.create(request=row, version=1, input_version=1, state='confirmed',
            body='经理JD', created_by=self.manager)
        row.official_jd = jd
        row.save(update_fields=['official_jd'])
        batch = ResumeScreeningBatch.objects.create(jd_version=jd, created_by=self.manager,
            idempotency_key='gm-worker', input_version=1, status='queued')
        item = ResumeArtifact.objects.create(batch=batch, file_id='local-test', filename='resume.txt',
            sha256='a' * 64, size=1, uploaded_by=self.manager, processing_status='queued')
        self.assertEqual(hr_screening_worker.claim_one(), (item.pk, 1))
        current_artifact(item.pk, 1)
        ResumeArtifact.objects.filter(pk=item.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(hr_screening_worker.claim_one(), (item.pk, 2))
        Module.objects.filter(code='hr').update(enabled=False)
        with self.assertRaises(StorageError) as denied:
            current_artifact(item.pk, 2)
        self.assertEqual(denied.exception.code, 'permission_changed')

    def test_engineering_owner_scope_internal_draft_worker_and_revocation(self):
        ready = {'status': 'ready', 'detail': 'test'}
        with patch('portal.engineering_api.runtime_state', return_value=ready):
            result = self.client.post('/api/engineering/jobs/', {'files': SimpleUploadedFile('input.xlsx', b'test')})
        self.assertEqual(result.status_code, 201, result.content)
        job = EngineeringJob.objects.get(pk=result.json()['job']['id'])
        self.assertEqual(result.json()['job']['result']['classification'], 'internal_draft')
        self.assertFalse(result.json()['job']['result']['formal_pricing'])
        detail = f'/api/engineering/jobs/{job.pk}/'
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.other_client.get(detail).status_code, 404)
        foreign = EngineeringJob.objects.create(owner=self.other)
        for suffix in ('', 'download/'):
            self.assertEqual(self.client.get(f'/api/engineering/jobs/{foreign.pk}/{suffix}').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/engineering/jobs/{foreign.pk}/').status_code, 404)
        with patch('portal.engineering_worker.runtime_state', return_value=ready):
            self.assertEqual(engineering_worker.claim_job(), (job.pk, 1))
            engineering_worker._guard_job(job.pk, 1)
            EngineeringJob.objects.filter(pk=job.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
            self.assertEqual(engineering_worker.claim_job(), (job.pk, 2))
        Module.objects.filter(code='cost').update(enabled=False)
        with self.assertRaises(StorageError) as denied:
            engineering_worker._guard_job(job.pk, 2)
        self.assertEqual(denied.exception.code, 'permission_changed')
        self.assertEqual(self.client.get(detail).status_code, 403)

    def test_finance_requires_grant_and_publishes_only_exact_own_record(self):
        root = '/api/business/ledgers/finance/'
        record = {'project_id': 'GM', 'project_name': '经理记录', 'contract_amount': '100.00',
                  'received_amount': '10.00', 'due_date': ''}
        self.assertEqual(self.post(root + 'records/', expected_revision=0, record=record).status_code, 403)
        BusinessLedgerGrant.objects.create(user=self.manager, department='finance', can_edit=True)
        BusinessLedgerGrant.objects.create(user=self.other, department='finance', can_edit=True)
        result = self.post(root + 'records/', expected_revision=0, record=record)
        self.assertEqual(result.status_code, 201, result.content)
        record_id, meta = next(iter(result.json()['record_meta'].items()))
        foreign = self.post(root + 'records/', client=self.other_client, expected_revision=1,
            record={**record, 'project_id': 'OTHER'})
        self.assertEqual(foreign.status_code, 201, foreign.content)
        self.assertEqual(self.client.put(root + 'records/OTHER/', json_body(expected_revision=2, record=record),
            content_type='application/json').status_code, 400)
        selection = {'record_id': record_id, 'source_revision': meta['draft_revision'], 'source_checksum': meta['draft_checksum']}
        self.assertEqual(self.post(root + 'publish/', expected_revision=2, expected_published_revision=0,
            records=[{**selection, 'source_checksum': 'b' * 64}]).status_code, 409)
        published = self.post(root + 'publish/', expected_revision=2, expected_published_revision=0, records=[selection])
        self.assertEqual(published.status_code, 200, published.content)
        snapshot = BusinessLedgerRevision.objects.get(action='publish')
        self.assertEqual([row['project_id'] for row in snapshot.records], ['GM'])
        Module.objects.filter(code='business').update(enabled=False)
        self.assertEqual(self.client.get(root).status_code, 403)
        self.assertEqual(self.post(root + 'records/', expected_revision=3, record=record).status_code, 403)
