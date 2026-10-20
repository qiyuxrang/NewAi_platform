"""Only the current owner's exact replacement command can abandon one unread file."""
from copy import deepcopy
import hashlib
import json
import tempfile
import uuid
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanJob, BaichuanMatchSnapshot
from portal.baichuan_assistant_service import store_attachment, storage_path, submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_service import BaichuanError
from portal.baichuan_models import Company
from .base import PortalTestCase
from . import test_baichuan_unreadable_attachment as fixture

TEXT = '放弃本轮未读附件，改用本轮文字：'
FILE = '放弃本轮未读附件，改用本轮文件：'


class UnreadableRecoveryTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('unreadable-recovery-owner', 'product')
        self.other = self.create_user('unreadable-recovery-other', 'product')
        temp = tempfile.TemporaryDirectory(prefix='unreadable-recovery-test-'); self.addCleanup(temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE='unreadable-recovery',
            BAICHUAN_STORAGE_ROOT=temp.name, BAICHUAN_RESEARCH_ENABLED=False, BAICHUAN_FACT_WRITE_ENABLED=False,
            BAICHUAN_TRUST_LEGACY_QUALIFICATIONS=True, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk, self.other.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)
        for target in ['socket.create_connection', 'socket.getaddrinfo', 'portal.model_gateway.generate_for_use']:
            guard = patch(target, side_effect=AssertionError('No network/real model in recovery tests'))
            guard.start(); self.addCleanup(guard.stop)
        self.company = Company.objects.create(name='FICTIONAL RECOVERY COMPANY', created_by=self.owner, updated_by=self.owner)
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unreadable-recovery')
        self.content = b'%PDF-1.4\n% fictional deterministic recovery fixture\n'
        self.bad = self.attachment()
        _, self.failed, _ = self.send('', [self.bad])
        with patch('portal.baichuan_assistant_worker.run_parser', return_value=deepcopy(fixture.FAILED_SCAN)), \
                patch('portal.baichuan_assistant_worker.generate_for_use') as model:
            self.assertTrue(run_one('unreadable-recovery-first', self.failed.pk))
        model.assert_not_called(); self.failed.refresh_from_db()
        self.assertEqual(self.failed.error_code, 'attachment_unreadable')
        self.old_payload = deepcopy(self.failed.payload); self.old_checkpoint = deepcopy(self.failed.checkpoint)
        self.bad.refresh_from_db(); self.bad_fields = {k: deepcopy(v) for k, v in vars(self.bad).items() if k != '_state'}

    def attachment(self, *, owner=None, conversation=None, completed=False):
        row = store_attachment(owner or self.owner, (conversation or self.conversation).pk,
            SimpleUploadedFile('fictional-recovery.pdf', self.content, content_type='application/pdf'))
        if completed:
            row.parse_status = 'completed'; row.extracted_text = '投标人须具备ITSS精确二级'
            row.locators = [dict(id='b1', kind='page', text=row.extracted_text, location={'page': 1})]
            row.save(update_fields=['parse_status', 'extracted_text', 'locators'])
        return row

    def send(self, text, attachments=(), *, key=None, parent=None, owner=None):
        self.conversation.refresh_from_db()
        return submit_message(owner or self.owner, self.conversation.pk, dict(text=text,
            attachment_ids=[str(row.pk) if hasattr(row, 'pk') else row for row in attachments],
            parent_revision=self.conversation.condition_revision if parent is None else parent,
            client_request_id=key or uuid.uuid4().hex))

    def assert_original_preserved(self):
        self.failed.refresh_from_db(); self.bad.refresh_from_db()
        self.assertEqual(self.failed.payload, self.old_payload)
        self.assertEqual(self.failed.checkpoint, self.old_checkpoint)
        self.assertEqual({k: v for k, v in vars(self.bad).items() if k != '_state'}, self.bad_fields)
        self.assertEqual(storage_path(self.bad.storage_ref).read_bytes(), self.content)

    def assert_replacement(self, message, job, mode, remaining):
        marker = job.checkpoint['attachment_replacement']
        self.assertEqual(marker, dict(failed_job_id=str(self.failed.pk), attachment_id=str(self.bad.pk),
                                     mode=mode, message_id=str(message.pk)))
        self.assertEqual(job.payload['attachment_ids'], [str(row.pk) for row in remaining])
        self.assertEqual(message.metadata['attachment_ids'], job.payload['attachment_ids'])
        self.assertEqual(job.checkpoint['pending_attachment_ids'], job.payload['attachment_ids'])
        self.assertIn('pending_base_conditions', job.checkpoint)
        self.assert_original_preserved()

    def assert_error(self, code, text, attachments=(), **kwargs):
        self.conversation.refresh_from_db(); before = self.conversation.condition_revision
        messages, jobs = self.conversation.messages.count(), self.conversation.jobs.count()
        with self.assertRaises(BaichuanError) as caught:
            self.send(text, attachments, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.condition_revision, before)
        self.assertEqual((self.conversation.messages.count(), self.conversation.jobs.count()), (messages, jobs))

    def test_explicit_text_replacement_completes_same_conversation_without_parent_pending(self):
        message, job, _ = self.send(TEXT+'企业名称等于FICTIONAL RECOVERY COMPANY')
        self.assertEqual(message.content, TEXT+'企业名称等于FICTIONAL RECOVERY COMPANY')
        self.assertEqual(job.payload['text'], '企业名称等于FICTIONAL RECOVERY COMPANY')
        self.assert_replacement(message, job, 'text', [])
        tree = dict(schema_version=1, revision=1, must=dict(field='company.name', op='eq', value=self.company.name))
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(tree)}) as model:
            self.assertTrue(run_one('unreadable-recovery-text', job.pk))
        parser.assert_not_called(); model.assert_called_once(); job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ('completed', ''))
        self.assertEqual(job.snapshots.get().counts, dict(confirmed=1, candidate=0, excluded=0))

    def test_explicit_new_file_removes_only_diagnostic_attachment(self):
        other = self.attachment(completed=True); new = self.attachment(completed=True)
        self.failed.checkpoint['pending_attachment_ids'].append(str(other.pk)); self.failed.save()
        self.old_checkpoint = deepcopy(self.failed.checkpoint)
        message, job, _ = self.send(FILE+'按新文件完整要求检索', [new])
        self.assert_replacement(message, job, 'file', [other, new])

    def test_file_replacement_requires_explanation_even_with_actual_new_file(self):
        new = self.attachment(completed=True)
        self.assert_error('invalid_attachment_replacement', FILE, [new])

    def test_default_followup_keeps_bad_attachment(self):
        _, job, _ = self.send('只要陕西企业')
        self.assertEqual(job.payload['attachment_ids'], [str(self.bad.pk)])
        self.assertNotIn('attachment_replacement', job.checkpoint)

    def test_negated_quoted_ascii_colon_and_whitespace_do_not_authorize(self):
        for value in ['不要'+TEXT+'只要陕西', '“'+TEXT+'只要陕西”', ' '+TEXT+'只要陕西',
                      TEXT.replace('：', ':')+'只要陕西', '说明：'+TEXT+'只要陕西']:
            with self.subTest(value=value):
                try:
                    _, job, _ = self.send(value)
                except BaichuanError as e:
                    self.assertEqual(e.code, 'invalid_attachment_replacement')
                else:
                    self.assertIn(str(self.bad.pk), job.payload['attachment_ids'])
                    self.assertNotIn('attachment_replacement', job.checkpoint)
                    with patch('portal.baichuan_assistant_worker.run_parser', return_value=deepcopy(fixture.FAILED_SCAN)):
                        self.assertTrue(run_one('negated-authorization-remains-unreadable', job.pk))

    def test_empty_text_missing_file_or_mixed_mode_rejected(self):
        self.assert_error('invalid_attachment_replacement', TEXT+' \n ')
        self.assert_error('invalid_attachment_replacement', FILE+'看新文件')
        self.assert_error('invalid_attachment_replacement', TEXT+'只要陕西', [self.attachment()])

    def test_reuploading_same_bad_id_is_not_a_new_file(self):
        self.assert_error('invalid_attachment_replacement', FILE+'依然该文件', [self.bad])

    def test_carried_readable_file_cannot_impersonate_a_new_replacement_file(self):
        old = self.attachment(completed=True)
        self.failed.checkpoint['pending_attachment_ids'].append(str(old.pk)); self.failed.save()
        self.assert_error('invalid_attachment_replacement', FILE+'按已有文件查', [old])

    def test_diagnostic_uuid_missing_or_invalid_never_drops_other_files(self):
        for identity in [str(uuid.uuid4()), 'not-a-uuid']:
            with self.subTest(identity=identity):
                self.failed.checkpoint['attachment_issue']['attachment_id'] = identity; self.failed.save()
                self.assert_error('not_found', TEXT+'只要陕西')

    def test_foreign_diagnostic_is_validated_before_its_carry_is_removed(self):
        foreign_conversation = BaichuanConversation.objects.create(owner=self.other, scope='unreadable-recovery')
        foreign = self.attachment(owner=self.other, conversation=foreign_conversation)
        self.failed.checkpoint['pending_attachment_ids'] = [str(foreign.pk)]
        self.failed.checkpoint['attachment_issue']['attachment_id'] = str(foreign.pk); self.failed.save()
        self.assert_error('not_found', TEXT+'只要陕西')

    def test_new_file_from_other_conversation_or_owner_is_rejected(self):
        own_conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unreadable-recovery')
        foreign = self.attachment(conversation=own_conversation)
        self.assert_error('not_found', FILE+'按文件查', [foreign])
        self.assert_error('not_found', TEXT+'只要陕西', owner=self.other)

    def test_wrong_failure_cannot_authorize_discard(self):
        self.failed.error_code = 'invalid_model_conditions'; self.failed.save()
        self.assert_error('invalid_attachment_replacement', TEXT+'只要陕西')

    def test_duplicate_request_replays_exactly_once_and_changed_request_conflicts(self):
        self.conversation.refresh_from_db()
        parent = self.conversation.condition_revision
        key = 'exact-unreadable-replacement-once'
        message, job, created = self.send(TEXT+'只要陕西', key=key, parent=parent)
        same_message, same_job, same_created = self.send(TEXT+'只要陕西', key=key, parent=parent)
        self.assertTrue(created); self.assertFalse(same_created)
        self.assertEqual((message.pk, job.pk), (same_message.pk, same_job.pk))
        self.assertEqual(BaichuanJob.objects.filter(message=message).count(), 1)
        self.assert_error('idempotency_conflict', TEXT+'只要北京', key=key, parent=parent)

    def test_failed_replacement_keeps_prior_file_hard_requirements_even_with_empty_ids(self):
        # A previously parsed file requirement predates the unreadable upload.
        old = self.attachment(completed=True)
        guard = dict(field='qualification', category='itss', op='grade_exact', value='2', holder='bidder',
                     source_refs=[f'attachment:{old.pk}:b1'])
        base = compile_conditions(dict(schema_version=1, revision=1, must=guard, source_refs=guard['source_refs']))
        self.failed.checkpoint['pending_base_conditions'] = base
        self.failed.checkpoint['file_requirements'] = [dict(node=guard, known=True)]
        self.failed.save(); self.old_checkpoint = deepcopy(self.failed.checkpoint)
        message, job, _ = self.send(TEXT+'增加企业名称等于FICTIONAL RECOVERY COMPANY')
        self.assert_replacement(message, job, 'text', [])
        self.assertEqual(job.checkpoint['pending_base_conditions'], base)
        self.assertEqual(job.checkpoint['file_requirements'], [dict(node=guard, known=True)])
        model_tree = dict(schema_version=1, revision=1, must=dict(field='company.name', op='eq', value=self.company.name))
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(model_tree)}):
            self.assertTrue(run_one('unreadable-recovery-with-prior-guards', job.pk))
        parser.assert_not_called(); job.refresh_from_db()
        self.assertEqual(job.status, 'completed')
        tree = job.snapshots.get().condition_tree
        from portal.baichuan_file_conditions import predicates
        self.assertIn(guard, predicates(tree['must']))
        self.assertEqual(job.snapshots.get().counts['confirmed'], 0)

    def test_stale_parent_and_unknown_payload_fields_do_not_authorize(self):
        self.assert_error('revision_conflict', TEXT+'只要陕西', parent=0)
        payload=dict(text='普通补充',attachment_ids=[],parent_revision=self.conversation.condition_revision,
                     client_request_id='source-injection',attachment_replacement={'attachment_id':str(self.bad.pk)})
        with self.assertRaises(BaichuanError) as caught:
            submit_message(self.owner,self.conversation.pk,payload)
        self.assertEqual(caught.exception.code,'invalid_request')

    def test_actual_prior_file_snapshot_survives_failed_upload_then_text_replacement(self):
        # Build the three actual worker rounds; do not manufacture the inherited
        # checkpoint or add a snapshot to a failed job.
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unreadable-recovery')
        old = self.attachment(completed=True)
        guard = dict(field='qualification', category='itss', op='grade_exact', value='2', holder='bidder',
                     source_refs=[f'attachment:{old.pk}:b1'])
        _, first, _ = self.send('', [old])
        first_tree = dict(schema_version=1, revision=1, must=guard, source_refs=guard['source_refs'])
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(first_tree)}):
            self.assertTrue(run_one('recovery-prior-file-snapshot', first.pk))
        parser.assert_not_called(); first.refresh_from_db(); self.assertEqual(first.status, 'completed')
        snapshot = first.snapshots.get()
        frozen = deepcopy({field.attname: getattr(snapshot, field.attname)
                           for field in snapshot._meta.concrete_fields})
        bad = self.attachment()
        _, failed, _ = self.send('', [bad])
        self.assertEqual(failed.checkpoint['pending_base_conditions'], snapshot.condition_tree)
        with patch('portal.baichuan_assistant_worker.run_parser', return_value=deepcopy(fixture.FAILED_SCAN)), \
                patch('portal.baichuan_assistant_worker.generate_for_use') as model:
            self.assertTrue(run_one('recovery-failed-upload-after-snapshot', failed.pk))
        model.assert_not_called(); failed.refresh_from_db(); self.assertEqual(failed.error_code, 'attachment_unreadable')
        _, restored, _ = self.send(TEXT+'增加企业名称等于FICTIONAL RECOVERY COMPANY')
        self.assertEqual(restored.payload['attachment_ids'], [])
        self.assertEqual(restored.checkpoint['pending_base_conditions'], snapshot.condition_tree)
        added = dict(schema_version=1, revision=1, must=dict(field='company.name', op='eq', value=self.company.name))
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(added)}) as model:
            self.assertTrue(run_one('recovery-restored-with-real-prior-snapshot', restored.pk))
        parser.assert_not_called(); model.assert_called_once(); restored.refresh_from_db()
        self.assertEqual((restored.status, restored.error_code), ('completed', ''))
        from portal.baichuan_file_conditions import predicates
        self.assertIn(guard, predicates(restored.snapshots.get().condition_tree['must']))
        self.assertEqual(restored.snapshots.get().counts['confirmed'], 0)
        snapshot.refresh_from_db()
        self.assertEqual({field.attname: getattr(snapshot, field.attname)
                          for field in snapshot._meta.concrete_fields}, frozen)
        self.assertEqual(storage_path(bad.storage_ref).read_bytes(), self.content)
        self.assertEqual(storage_path(old.storage_ref).read_bytes(), self.content)

    def _grade_relation_recovery_rounds(self, proven):
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unreadable-recovery')
        old = self.attachment(completed=True)
        old.extracted_text = '制造商必须提供CCRC二级及以上证书' if proven else '制造商必须提供CCRC二级证书'
        old.locators = [dict(id='b1', text=old.extracted_text, location={'page': 1})]
        old.save(update_fields=['extracted_text', 'locators'])
        node = dict(field='qualification', category='ccrc', op='grade_at_least', value='2', holder='manufacturer',
                    source_refs=[f'attachment:{old.pk}:b1'])
        tree = dict(schema_version=1, revision=1, must=node, source_refs=node['source_refs'])
        _, initial, _ = self.send('', [old])
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(tree)}):
            self.assertTrue(run_one('grade-recovery-initial', initial.pk))
        parser.assert_not_called(); initial.refresh_from_db()
        self.assertEqual(initial.status, 'completed' if proven else 'awaiting_input')
        initial_guard = deepcopy(initial.checkpoint['grade_relation_guard'])
        self.assertEqual(bool(initial_guard['validated_keys']), proven)
        bad = self.attachment()
        _, failed, _ = self.send('继续处理新文件', [bad])
        self.assertEqual(failed.checkpoint['grade_relation_guard'], initial_guard)
        if not proven:
            self.assertEqual(failed.checkpoint['grade_relation_question'], initial.checkpoint['grade_relation_question'])
        with patch('portal.baichuan_assistant_worker.run_parser', return_value=deepcopy(fixture.FAILED_SCAN)), \
                patch('portal.baichuan_assistant_worker.generate_for_use') as model:
            self.assertTrue(run_one('grade-recovery-new-bad-file', failed.pk))
        model.assert_not_called(); failed.refresh_from_db()
        self.assertEqual(failed.error_code, 'attachment_unreadable')
        self.assertEqual(failed.checkpoint['grade_relation_guard'], initial_guard)
        _, restored, _ = self.send(TEXT+'只要广州市的')
        self.assertEqual(restored.checkpoint['grade_relation_guard'], initial_guard)
        if not proven:
            self.assertEqual(restored.checkpoint['grade_relation_question'], initial.checkpoint['grade_relation_question'])
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(tree)}):
            self.assertTrue(run_one('grade-recovery-explicit-text', restored.pk))
        parser.assert_not_called(); restored.refresh_from_db()
        self.assertEqual(restored.status, 'completed' if proven else 'awaiting_input')
        self.assertEqual(bool(restored.checkpoint['grade_relation_guard']['validated_keys']), proven)
        if proven:
            self.assertEqual(restored.snapshots.get().condition_tree['must'], node)
        else:
            self.assertFalse(restored.snapshots.exists())
            self.assertTrue(restored.checkpoint['grade_relation_question'])
        _, continued, _ = self.send('继续')
        with patch('portal.baichuan_assistant_worker.run_parser') as parser, \
                patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(tree)}):
            self.assertTrue(run_one('grade-recovery-unrelated-followup', continued.pk))
        parser.assert_not_called(); continued.refresh_from_db()
        self.assertEqual(continued.status, 'completed' if proven else 'awaiting_input')
        self.assertEqual(bool(continued.checkpoint['grade_relation_guard']['validated_keys']), proven)
        if not proven:
            self.assertFalse(continued.snapshots.exists())
        self.assertEqual(storage_path(bad.storage_ref).read_bytes(), self.content)
        self.assertEqual(storage_path(old.storage_ref).read_bytes(), self.content)

    def test_validated_file_grade_relation_survives_bad_upload_and_explicit_replacement(self):
        self._grade_relation_recovery_rounds(proven=True)

    def test_unresolved_file_grade_relation_remains_a_question_after_replacement(self):
        self._grade_relation_recovery_rounds(proven=False)
