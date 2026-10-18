"""A source conflict must reach the existing conversation reply, not only JSON."""
import hashlib
import io
import json
import tempfile
import uuid
from zipfile import ZipFile
from unittest.mock import patch

from django.test import override_settings
from portal.baichuan_assistant_models import BaichuanAttachment, BaichuanConversation, BaichuanMessage
from portal.baichuan_assistant_service import storage_path, submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_rules import install_compatibility_rules
from .base import PortalTestCase


class UnresolvedReplyTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('unresolved-reply-owner', 'product')
        temp = tempfile.TemporaryDirectory(prefix='unresolved-reply-')
        self.addCleanup(temp.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True,
            BAICHUAN_ASSISTANT_SCOPE='unresolved-reply-test', BAICHUAN_STORAGE_ROOT=temp.name,
            BAICHUAN_TRUST_LEGACY_QUALIFICATIONS=True, BAICHUAN_RESEARCH_ENABLED=False,
            PORTAL_BAICHUAN_SCOPE_CONFIRMED=True, PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)
        install_compatibility_rules(self.owner)
        self.company = Company.objects.create(name='虚构待澄清验收企业', created_by=self.owner, updated_by=self.owner)
        CompanyQualification.objects.create(company=self.company, category='electronic', status='PRESENT', grade='2')
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='unresolved-reply-test')
        for target in ('socket.getaddrinfo', 'socket.create_connection', 'socket.socket.connect', 'socket.socket.connect_ex'):
            guard = patch(target, side_effect=AssertionError('No network in reply tests'))
            guard.start(); self.addCleanup(guard.stop)

    def execute(self, unresolved, *, file=False):
        ids=[]; ref=None
        if file:
            content=io.BytesIO()
            with ZipFile(content, 'w') as z:
                z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
                z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>投标人电子与智能化精确二级。</w:t></w:r></w:p></w:body></w:document>')
            data=content.getvalue()
            attachment=BaichuanAttachment.objects.create(owner=self.owner, conversation=self.conversation,
                original_name='synthetic-conflict.docx', media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_ref=str(uuid.uuid4()),
                parse_status='completed', extracted_text='投标人电子与智能化精确二级。',
                locators=[{'id':'b1','kind':'paragraph','text':'投标人电子与智能化精确二级。', 'location':{'paragraph':1},'confidence':1}])
            storage_path(attachment.storage_ref).write_bytes(data)
            ids=[str(attachment.pk)];ref=f'attachment:{attachment.pk}:b1'
        _,job,_=submit_message(self.owner,self.conversation.pk, {'text':'合成文字：精确一级，与文件二级冲突。' if file else '合成精确二级检索',
            'attachment_ids':ids,'parent_revision':0,'client_request_id':uuid.uuid4().hex})
        ref=ref or f'message:{job.message_id}'
        tree={'schema_version':1,'revision':1,'must':{'field':'qualification','category':'electronic',
            'holder':'bidder','op':'grade_exact','value':'2','source_refs':[ref]},
            'source_refs':[ref],'unresolved':unresolved,'should':[], 'output':{'fields':['name','phone'],'limit':10}}
        with patch('portal.baichuan_assistant_worker.generate_for_use',return_value={'content':json.dumps(tree)}) as model:
            self.assertTrue(run_one('unresolved-reply-worker',job.pk))
        model.assert_called_once();job.refresh_from_db()
        self.assertEqual(job.status,'completed',job.error_code)
        snapshot=job.snapshots.get()
        replies=list(BaichuanMessage.objects.filter(conversation=self.conversation,role='assistant').values_list('content',flat=True))
        self.assertEqual(len(replies),1)
        return job,snapshot,replies[0]

    def test_mixed_file_conflict_is_visible_without_confirming_or_removing_file_requirement(self):
        issue='文字要求投标人精确一级，附件要求同一投标人精确二级，存在冲突，请澄清最终要求。'
        job,snapshot,reply=self.execute([issue],file=True)
        self.assertEqual(snapshot.counts,{'confirmed':0,'candidate':1,'excluded':0})
        self.assertEqual(snapshot.condition_tree['must']['value'],'2')
        self.assertTrue(snapshot.condition_tree['must']['source_refs'][0].startswith('attachment:'))
        self.assertIn(issue,reply)
        self.assertEqual(job.checkpoint['summary'],reply)
        self.assertEqual(snapshot.condition_tree['unresolved'],[issue])

    def test_ordinary_confirmed_reply_does_not_add_a_spurious_clarification(self):
        _,snapshot,reply=self.execute([])
        self.assertEqual(snapshot.counts['confirmed'],1)
        self.assertNotIn('尚需澄清',reply)
        self.assertIn('已确认 1 家',reply)

    def test_existing_ocr_review_issue_reaches_reply_and_stays_unknown(self):
        issue='附件第2页识别置信度较低，请对照原图核对，不可直接确认。'
        _,snapshot,reply=self.execute([issue])
        self.assertEqual(snapshot.counts['confirmed'],0)
        self.assertIn(issue,reply)

    def test_reply_is_bounded_but_snapshot_keeps_all_unresolved_items(self):
        issues=[f'第{i}项需澄清：'+('合成提示'*150) for i in range(8)]
        job,snapshot,reply=self.execute(issues)
        self.assertEqual(snapshot.condition_tree['unresolved'],issues)
        self.assertLessEqual(len(reply),2200)
        self.assertIn('第0项需澄清',reply)
        self.assertNotIn('第7项需澄清',reply)
        self.assertEqual(job.checkpoint['summary'],reply)
