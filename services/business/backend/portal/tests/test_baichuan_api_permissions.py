"""Actual assistant route permissions, isolated SQL/storage and zero providers.

AuditEvent writes for rejected requests are expected. All catalog, assistant,
evidence, manifest and artifact state must otherwise remain exactly unchanged.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from portal import baichuan_assistant_models as models
from portal.baichuan_assistant_service import store_attachment
from portal.baichuan_exports import enqueue_export, process_export
from portal.baichuan_jobs import claim_job, enqueue_job
from portal.baichuan_models import Company, CompanyPerson, CompanyQualification
from portal.baichuan_research import create_manifest
from .base import PortalTestCase


ROOT = '/api/product/baichuan/'


class AssistantApiPermissionMatrixTests(PortalTestCase):
    def setUp(self):
        for target in ('socket.create_connection', 'socket.getaddrinfo',
            'portal.baichuan_assistant_worker.generate_for_use',
            'portal.baichuan_research_runtime.generate_for_use',
            'portal.baichuan_research_runtime.search_public_query',
            'portal.baichuan_research_runtime.fetch_public_page'):
            guard = patch(target, side_effect=AssertionError('Permission matrix forbids external calls'))
            mocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mocked.assert_not_called)
        self.owner = self.create_user('api-matrix-owner', 'product')
        self.other = self.create_user('api-matrix-other-maintainer', 'product')
        self.reader = self.create_user('api-matrix-gm-reader', 'general_manager')
        self.temp = tempfile.TemporaryDirectory(prefix='baichuan-permission-matrix-')
        self.addCleanup(self.temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True,
            BAICHUAN_ASSISTANT_SCOPE='permission-isolated', BAICHUAN_STORAGE_ROOT=self.temp.name,
            BAICHUAN_RESEARCH_ENABLED=True, BAICHUAN_FACT_WRITE_ENABLED=True,
            BAICHUAN_DATASET_KIND='isolation', BAICHUAN_ENVIRONMENT_LABEL='synthetic permission matrix',
            PRODUCT_WEB_SEARCH_ENABLED=False, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk, self.reader.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk, self.other.pk],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable()
        self.addCleanup(config.disable)
        self.company = Company.objects.create(name='SYNTHETIC SHARED CATALOG COMPANY', phone='00123',
            source='Synthetic manual original', created_by=self.owner, updated_by=self.owner)
        self.factory = APIRequestFactory()
        self.bundle = self.make_bundle(self.owner, research=True)

    def make_bundle(self, user, *, research=False):
        conversation = models.BaichuanConversation.objects.create(owner=user, scope='permission-isolated',
            condition_revision=1)
        message = models.BaichuanMessage.objects.create(conversation=conversation, role='user',
            content='SYNTHETIC PRIVATE REQUEST', condition_revision=1)
        job, _ = enqueue_job(user, kind='query', payload={'condition_revision': 1},
            conversation=conversation, message=message, idempotency_key='query-' + str(user.pk))
        failed, _ = enqueue_job(user, kind='query', payload={'condition_revision': 1},
            conversation=conversation, idempotency_key='failed-' + str(user.pk))
        failed.status = 'failed'
        failed.save(update_fields=['status'])
        attachment = store_attachment(user, conversation.pk,
            SimpleUploadedFile('synthetic.pdf', b'%PDF-1.7\nSYNTHETIC; no parser call'))
        evidence = models.BaichuanEvidence.objects.create(scope='permission-isolated',
            url='https://example.test/synthetic-evidence', retrieved_at=timezone.now(),
            subject={'company_id': str(self.company.pk)}, locator={'page': 1},
            excerpt='SYNTHETIC PUBLIC DECLARATION', access_status='unverified')
        snapshot = models.BaichuanMatchSnapshot.objects.create(conversation=conversation, job=job,
            condition_revision=1, result_revision=1, fact_cutoff_at=timezone.now(),
            condition_tree={'schema_version': 1, 'revision': 1, 'must': {'field': 'company.city',
                'op': 'eq', 'value': 'SYNTHETIC'}, 'output': {'fields': ['name', 'phone'], 'limit': 20}},
            counts={'confirmed': 0, 'candidate': 1, 'excluded': 0},
            results=[{'company_id': str(self.company.pk), 'company': {'name': self.company.name, 'phone': '00123'},
                'status': 'candidate', 'conditions': [{'condition_id': 'must', 'verdict': 'unknown',
                    'evidence_ids': [str(evidence.pk)]}]}])
        exported_job = enqueue_export(user, snapshot.pk,
            {'client_request_id': 'export-' + str(user.pk), 'include_candidates': True})
        claimed = claim_job('permission-fixture', job_id=exported_job.pk)
        artifact = process_export(claimed, 'permission-fixture')
        manifest = create_manifest(user, 'manifest-' + str(user.pk), fields=['phone'])[0] if research else None
        return dict(conversation=conversation, message=message, job=job, failed=failed,
            attachment=attachment, evidence=evidence, snapshot=snapshot, export=artifact,
            export_job=exported_job, manifest=manifest)

    def routes(self, bundle=None, *, missing=False):
        bundle = bundle or self.bundle
        def identifier(key):
            # Reader fixtures deliberately cannot create research manifests.
            # Their research denial route targets the existing maintainer manifest.
            return uuid.uuid4() if missing else (bundle[key] or self.bundle[key]).pk
        conversation = identifier('conversation')
        snapshot = identifier('snapshot')
        return [
            ('config', 'GET', ROOT + 'assistant/config/', None, False),
            ('conversation-create', 'POST', ROOT + 'assistant/conversations/', {}, False),
            ('conversation-detail', 'GET', ROOT + f'assistant/conversations/{conversation}/', None, True),
            ('message-submit', 'POST', ROOT + f'assistant/conversations/{conversation}/messages/',
                {'text': 'SYNTHETIC', 'parent_revision': 1, 'client_request_id': 'matrix-request'}, True),
            ('attachment-upload', 'POST', ROOT + f'assistant/conversations/{conversation}/attachments/', 'upload', True),
            ('query-job', 'GET', ROOT + f'assistant/jobs/{identifier("job")}/', None, True),
            ('query-stream', 'POST', ROOT + f'assistant/jobs/{identifier("job")}/stream/', {}, True),
            ('job-cancel', 'POST', ROOT + f'assistant/jobs/{identifier("job")}/cancel/', {}, True),
            ('job-retry', 'POST', ROOT + f'assistant/jobs/{identifier("failed")}/retry/', {'client_request_id': 'matrix-retry'}, True),
            ('results-with-inline-sources', 'GET', ROOT + f'assistant/results/{snapshot}/', None, True),
            ('export-create', 'POST', ROOT + f'assistant/results/{snapshot}/exports/',
                {'client_request_id': 'matrix-export', 'include_candidates': True}, True),
            ('export-job', 'GET', ROOT + f'assistant/jobs/{identifier("export_job")}/', None, True),
            ('export-download', 'GET', ROOT + f'assistant/exports/{identifier("export")}/download/', None, True),
            ('research-create', 'POST', ROOT + 'research/manifests/', {'client_request_id': 'matrix-manifest', 'fields': ['phone']}, False),
            ('research-report', 'GET', ROOT + f'research/manifests/{identifier("manifest")}/', None, True),
        ]

    def request(self, user, route, *, client=None):
        _, method, path, payload, _ = route
        if payload == 'upload':
            payload = {'file': SimpleUploadedFile('rejected.pdf', b'%PDF-1.7\nSYNTHETIC REJECTED')}
            request = self.factory.post(path, payload, format='multipart') if client is None else None
        else:
            request = getattr(self.factory, method.lower())(path, payload or {}, format='json') if client is None else None
        if client is not None:
            if payload and 'file' in payload:
                return client.post(path, payload)
            return getattr(client, method.lower())(path, json.dumps(payload or {}) if method == 'POST' else {},
                content_type='application/json')
        force_authenticate(request, user=user)
        match = resolve(path)
        return match.func(request, **match.kwargs)

    def protected_state(self):
        types = [Company, CompanyQualification, CompanyPerson,
            models.BaichuanConversation, models.BaichuanMessage, models.BaichuanAttachment,
            models.BaichuanJob, models.BaichuanJobItem, models.BaichuanMatchSnapshot,
            models.BaichuanEvidence, models.BaichuanFactRevision, models.BaichuanCertificate,
            models.BaichuanResearchManifest, models.BaichuanResearchItem, models.BaichuanExport]
        return {model.__name__: list(model.objects.order_by('pk').values()) for model in types}, {
            str(path.relative_to(self.temp.name)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(self.temp.name).rglob('*') if path.is_file()}

    def assert_denied(self, user, route, status, *, client=None, code=None):
        before = self.protected_state()
        response = self.request(user, route, client=client)
        self.assertEqual(response.status_code, status, (route[0], getattr(response, 'data', None)))
        if code:
            self.assertEqual(response.data['code'], code)
        self.assertEqual(self.protected_state(), before, route[0] + ' changed protected state')

    def test_cross_owner_and_nonexistent_objects_share_not_found_without_side_effects(self):
        # The other owner is also a maintainer: research 404 is ownership, not a role accident.
        for missing in (False, True):
            for route in self.routes(missing=missing):
                if route[4]:
                    with self.subTest(route=route[0], missing=missing):
                        self.assert_denied(self.other, route, 404, code='not_found')

    def test_cross_scope_and_nonexistent_objects_share_not_found_without_side_effects(self):
        with override_settings(BAICHUAN_ASSISTANT_SCOPE='another-deployment'):
            for missing in (False, True):
                for route in self.routes(missing=missing):
                    if route[4]:
                        with self.subTest(route=route[0], missing=missing):
                            self.assert_denied(self.owner, route, 404, code='not_found')

    def test_revoked_read_grant_denies_every_real_entry_without_side_effects(self):
        with override_settings(PORTAL_BAICHUAN_READ_USER_IDS=[]):
            for route in self.routes():
                with self.subTest(route=route[0]):
                    # Research report hides objects with 404; entry gates use existing 403.
                    expected = 404 if route[0] == 'research-report' else 403
                    self.assert_denied(self.owner, route, expected,
                        code='not_found' if expected == 404 else 'baichuan_forbidden')

    def test_disabled_authenticated_session_denies_every_real_entry_without_side_effects(self):
        client = Client()
        self.login(client, self.owner)
        type(self.owner).objects.filter(pk=self.owner.pk).update(is_active=False)
        for route in self.routes():
            with self.subTest(route=route[0]):
                # Full authentication path, not force_authenticate on an inactive object.
                self.assert_denied(self.owner, route, 401, client=client)

    def test_reader_owned_reads_sources_download_and_private_creation_work_without_fact_writes(self):
        own = self.make_bundle(self.reader)
        for route in self.routes(own):
            if route[0] in {'config', 'conversation-detail', 'query-job', 'query-stream', 'export-job', 'results-with-inline-sources', 'export-download'}:
                with self.subTest(route=route[0]):
                    before = self.protected_state()
                    response = self.request(self.reader, route)
                    self.assertEqual(response.status_code, 200)
                    if route[0] == 'results-with-inline-sources':
                        self.assertEqual(set(response.data['evidence']), {str(own['evidence'].pk)})
                        self.assertEqual(response.data['results'][0]['status'], 'candidate')
                    if route[0] == 'export-download':
                        try:
                            self.assertEqual(hashlib.sha256(b''.join(response.streaming_content)).hexdigest(), own['export'].file_hash)
                        finally:
                            response.file_to_stream.close()
                    if route[0] == 'query-stream':
                        self.assertTrue(response['Content-Type'].startswith('text/event-stream'))
                        # This factory-created observer has not been iterated;
                        # it holds no file/socket/DB resources. Response.close
                        # sends request_finished and closes this TestCase's
                        # outer SQLite transaction, unlike generator cleanup.
                        response._iterator.close()
                    self.assertEqual(self.protected_state(), before)
        create = self.routes()[1]
        before_company = list(Company.objects.values())
        response = self.request(self.reader, create)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(models.BaichuanConversation.objects.get(pk=response.data['id']).owner_id, self.reader.pk)
        self.assertEqual(list(Company.objects.values()), before_company)
        for route in self.routes():
            if route[0] in {'research-create', 'research-report'}:
                self.assert_denied(self.reader, route, 403 if route[0] == 'research-create' else 404)

    def test_global_config_and_new_conversation_use_current_owner_and_scope(self):
        with override_settings(BAICHUAN_ASSISTANT_SCOPE='another-deployment'):
            self.assertEqual(self.request(self.other, self.routes()[0]).status_code, 200)
            response = self.request(self.other, self.routes()[1])
            self.assertEqual(response.status_code, 201)
            conversation = models.BaichuanConversation.objects.get(pk=response.data['id'])
            self.assertEqual((conversation.owner_id, conversation.scope), (self.other.pk, 'another-deployment'))

    def test_route_inventory_has_no_unimplemented_attachment_preview_or_source_download_claim(self):
        from portal.baichuan_urls import urlpatterns
        assistant_patterns = [str(pattern.pattern) for pattern in urlpatterns
            if str(pattern.pattern).startswith(('assistant/', 'research/'))]
        self.assertEqual(len(assistant_patterns), 14)
        self.assertEqual(len({resolve(route[2]).route for route in self.routes()}), 14)
        # These actions do not exist; sources are inline in owner-scoped results.
        self.assertNotIn('assistant/conversations/<uuid:conversation_id>/attachments/<uuid:attachment_id>/download/', assistant_patterns)
        self.assertNotIn('assistant/attachments/<uuid:attachment_id>/preview/', assistant_patterns)
        self.assertNotIn('assistant/sources/<uuid:source_id>/', assistant_patterns)
