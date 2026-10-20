"""AI-AC04 unreadable files stop before model; usable partial input stays unknown.

FAILED_SCAN is the actual 2026-10-18 disabled-OCR parser return frozen at
.runtime/baichuan-ai-local/night-acceptance-20261018/
ocr-disabled-real-worker-20261018-0826/actual-parser-return.json
(SHA256 41f1a3644cdd754cdc684feb574c2d9f5519ff87c2f7dc85f57ee7f510b9e699).
These deterministic worker tests reuse that return; the separate physical
integration probe executes the real parser. No runtime-private fixture dependency.
"""
from copy import deepcopy
import hashlib
import json
import tempfile
import uuid
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanEvidence, BaichuanFactRevision
from portal.baichuan_assistant_service import storage_path, store_attachment, submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_matching import match_companies
from portal.baichuan_models import Company
from portal.product_storage import StorageError
from .base import PortalTestCase


FAILED_SCAN = {
    'schema_version': 1, 'parser_version': 'product-intake-1', 'status': 'failed', 'method': 'native',
    'blocks': [], 'items': [], 'warnings': [
        {'code': 'ocr_unavailable', 'detail': '本页扫描内容未识别，请拆分文件或启用本地 OCR 后重试。',
         'location': {'page': 1}, 'severity': 'partial'},
        {'code': 'no_text', 'detail': '未提取到可用文字。原文件已保留，请核对扫描清晰度或补充文字资料。',
         'location': {}, 'severity': 'review'}],
    'character_count': 0, 'block_count': 0, 'truncated': False,
    'metadata': {'ocr_enabled': False, 'pages': 1},
}


class UnreadableAttachmentTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('unreadable-fixture-owner', 'product')
        temp = tempfile.TemporaryDirectory(prefix='unreadable-attachment-test-')
        self.addCleanup(temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True,
            BAICHUAN_ASSISTANT_SCOPE='unreadable-test', BAICHUAN_STORAGE_ROOT=temp.name,
            BAICHUAN_RESEARCH_ENABLED=False, BAICHUAN_FACT_WRITE_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)
        for name in ['socket.create_connection', 'socket.getaddrinfo', 'socket.socket.connect',
                     'portal.model_gateway.generate_for_use']:
            guard = patch(name, side_effect=AssertionError('No network or real models in worker fixtures'))
            guard.start(); self.addCleanup(guard.stop)
        self.company = Company.objects.create(name='FICTIONAL UNREADABLE TEST COMPANY', city='广州市',
            created_by=self.owner, updated_by=self.owner)
        evidence = BaichuanEvidence.objects.create(scope='unreadable-test', source_type='fixture',
            url='https://example.com/synthetic-city-assertion',
            retrieved_at=timezone.now(), verified_on=timezone.localdate(), content_hash='a'*64,
            excerpt=self.company.name+'位于广州市。仅为隔离测试。', locator={'fixture': True}, access_status='verified',
            subject={'company_id': str(self.company.pk), 'identity_verified': True,
                     'identity_method': 'full_legal_name_on_public_page', 'field_assertions': {'city': ['广州市']}})
        BaichuanFactRevision.objects.create(company=self.company, field='city', actor=self.owner, baseline_version=1,
            new_value='广州市', verification_status='verified', review_status='applied', evidence=evidence)
        self.tree = dict(schema_version=1, revision=1, must=dict(field='company.city', op='eq', value='广州市'))
        self.assertEqual(match_companies(self.owner, self.tree)[3]['confirmed'], 1)
        self.content = b'%PDF-1.4\n% fictional unit fixture; parser return frozen from actual physical probe\n'

    def send(self, parsed=None, *, cached=False, cached_text=None, text='', parser_error=None):
        conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unreadable-test')
        attachment = None
        if parsed is not None:
            attachment = store_attachment(self.owner, conversation.pk,
                SimpleUploadedFile('frozen-scan.pdf', self.content, content_type='application/pdf'))
            if cached:
                attachment.parse_status = parsed['status']
                attachment.extracted_text = (cached_text if cached_text is not None else
                    '\n'.join(b.get('text', '') for b in parsed['blocks']))
                attachment.locators = deepcopy(parsed['blocks'])
                attachment.save(update_fields=['parse_status', 'extracted_text', 'locators'])
        _, job, created = submit_message(self.owner, conversation.pk,
            dict(text=text, attachment_ids=[str(attachment.pk)] if attachment else [], parent_revision=0,
                 client_request_id=uuid.uuid4().hex))
        self.assertTrue(created)
        ref = f'attachment:{attachment.pk}:b1' if attachment else f'message:{job.message_id}'
        tree = deepcopy(self.tree); tree['source_refs'] = [ref]; tree['must']['source_refs'] = [ref]
        before = list(Company.objects.values())
        with patch('portal.baichuan_assistant_worker.run_parser', return_value=deepcopy(parsed),
                   side_effect=parser_error) as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use',
                      return_value={'content': json.dumps(tree)}) as model:
            self.assertTrue(run_one('unreadable-fixture-worker', job.pk))
        job.refresh_from_db()
        if attachment:
            attachment.refresh_from_db()
            self.assertEqual(storage_path(attachment.storage_ref).read_bytes(), self.content)
            self.assertEqual(attachment.sha256, hashlib.sha256(self.content).hexdigest())
        self.assertEqual(before, list(Company.objects.values()))
        if parsed is not None and not cached:
            parser.assert_called_once()
        else:
            parser.assert_not_called()
        return job, attachment, model

    def assert_unreadable(self, job, attachment, model):
        model.assert_not_called()
        self.assertEqual((job.status, job.error_code), ('failed', 'attachment_unreadable'))
        self.assertEqual(job.counts.get('_budget_model_calls', 0), 0)
        self.assertEqual(job.counts.get('_budget_sources', 0), 0)
        self.assertFalse(job.snapshots.exists())
        issue = job.checkpoint['attachment_issue']
        self.assertEqual(issue['attachment_id'], str(attachment.pk))
        self.assertEqual(issue['parse_status'], attachment.parse_status)
        replies = list(job.conversation.messages.filter(role='assistant'))
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0].metadata['error_code'], 'attachment_unreadable')
        self.assertIn(attachment.original_name, replies[0].content)
        self.assertIn('DOCX', replies[0].content)
        self.assertIn('OCR', replies[0].content)
        self.assertIn('输入框', replies[0].content)
        self.assertIn('暂未检索或调用模型', replies[0].content)

    def test_actual_failed_scan_stops_model_and_preserves_original_page_diagnostic(self):
        job, attachment, model = self.send(FAILED_SCAN)
        self.assert_unreadable(job, attachment, model)
        self.assertEqual(job.checkpoint['attachment_issue']['warnings'], FAILED_SCAN['warnings'])
        self.assertIn('启用本地 OCR', job.conversation.messages.get(role='assistant').content)

    def test_corrupt_or_encrypted_content_records_safe_issue_before_any_model(self):
        for code in ('invalid_document', 'encrypted_document', 'invalid_image',
                     'format_mismatch', 'invalid_page'):
            with self.subTest(code=code):
                job, attachment, model = self.send(FAILED_SCAN,
                    parser_error=StorageError(code, 'UPSTREAM PRIVATE DIAGNOSTIC'))
                self.assert_unreadable(job, attachment, model)
                self.assertEqual(attachment.parse_status, 'failed')
                self.assertEqual(job.checkpoint['attachment_issue']['warnings'][0]['code'], code)
                self.assertNotIn('UPSTREAM PRIVATE', job.conversation.messages.get(role='assistant').content)

    def test_infrastructure_and_safety_errors_are_not_reclassified_as_content(self):
        for code in ('parser_unavailable', 'parser_busy', 'parse_timeout', 'parse_failed',
                     'unsafe_archive', 'active_content', 'archive_limit', 'page_limit'):
            with self.subTest(code=code):
                job, attachment, model = self.send(FAILED_SCAN,
                    parser_error=StorageError(code, 'Controlled parser failure'))
                model.assert_not_called()
                self.assertEqual((job.status, job.error_code), ('failed', code))
                self.assertEqual(attachment.parse_status, 'pending')
                self.assertNotIn('attachment_issue', job.checkpoint)
                self.assertFalse(job.snapshots.exists())

    def test_claimed_completed_but_only_whitespace_block_is_unreadable(self):
        parsed = deepcopy(FAILED_SCAN)
        parsed.update(status='completed', blocks=[dict(id='b1', kind='page', text=' \n\t ', location={'page': 1})])
        job, attachment, model = self.send(parsed)
        self.assert_unreadable(job, attachment, model)

    def test_cached_completed_without_blocks_never_calls_parser_or_model(self):
        parsed = deepcopy(FAILED_SCAN); parsed.update(status='completed', warnings=[])
        job, attachment, model = self.send(parsed, cached=True)
        self.assert_unreadable(job, attachment, model)
        self.assertEqual(job.checkpoint['attachment_issue']['warnings'], [])

    def test_cached_completed_whitespace_is_unreadable(self):
        parsed = deepcopy(FAILED_SCAN)
        parsed.update(status='completed', warnings=[], blocks=[dict(id='b1', kind='page', text=' \n ', location={'page': 1})])
        job, attachment, model = self.send(parsed, cached=True)
        self.assert_unreadable(job, attachment, model)

    def test_legacy_cached_aggregate_text_with_locator_only_remains_readable(self):
        parsed = deepcopy(FAILED_SCAN)
        parsed.update(status='completed', warnings=[], blocks=[dict(id='b1', location={'page': 1})])
        job, attachment, model = self.send(parsed, cached=True, cached_text='只要广州市企业')
        model.assert_called_once()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(attachment.extracted_text, '只要广州市企业')
        self.assertEqual(attachment.locators, parsed['blocks'])
        self.assertNotIn('text', attachment.locators[0])
        self.assertEqual(job.snapshots.get().counts['confirmed'], 1)

    def test_mixed_missing_and_explicit_blank_blocks_are_not_legacy_cache(self):
        parsed = deepcopy(FAILED_SCAN)
        parsed.update(status='completed', warnings=[], blocks=[dict(id='b1', location={'page': 1}),
            dict(id='b2', text=' \n ', location={'page': 2})])
        job, attachment, model = self.send(parsed, cached=True, cached_text='[第1页]')
        self.assert_unreadable(job, attachment, model)

    def test_usable_partial_retains_location_and_remains_candidate(self):
        parsed = deepcopy(FAILED_SCAN)
        parsed.update(status='partial', blocks=[dict(id='b1', kind='page', text='只要广州市企业',
            location={'page': 1}, location_label='第 1 页')], warnings=[dict(code='ocr_unavailable',
            detail='第2页扫描内容未识别，请启用OCR后重试。', location={'page': 2}, severity='partial')])
        job, attachment, model = self.send(parsed)
        model.assert_called_once()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.counts['_budget_model_calls'], 1)
        snapshot = job.snapshots.get()
        self.assertEqual(snapshot.counts, dict(confirmed=0, candidate=1, excluded=0))
        self.assertEqual(snapshot.results[0]['conditions'][0]['verdict'], 'satisfied')
        self.assertEqual(snapshot.results[0]['verdict'], 'unknown')
        self.assertTrue(snapshot.condition_tree['unresolved'])
        self.assertEqual(attachment.locators[0]['location'], {'page': 1})
        self.assertIn(f'attachment:{attachment.pk}:b1', snapshot.condition_tree['must']['source_refs'])
        self.assertIn('人工核对', job.conversation.messages.get(role='assistant').content)

    def test_plain_text_without_attachment_still_matches(self):
        job, attachment, model = self.send(text='只要广州市企业')
        self.assertIsNone(attachment)
        model.assert_called_once()
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.snapshots.get().counts, dict(confirmed=1, candidate=0, excluded=0))
        self.assertNotIn('attachment_issue', job.checkpoint)
