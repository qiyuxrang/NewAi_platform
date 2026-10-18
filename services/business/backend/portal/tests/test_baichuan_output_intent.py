"""Actual worker, API paging, file inheritance and fresh facts; no real models."""
from copy import deepcopy
from datetime import date
import json
import tempfile
import uuid
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation, BaichuanJob, BaichuanMatchSnapshot
from portal.baichuan_assistant_service import submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_file_conditions import guards_from
from portal.baichuan_jobs import enqueue_job
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_output_intent import edit_previous, extract_request, output_edit
from portal.baichuan_rules import install_compatibility_rules
from .base import PortalTestCase

TODAY = date(2026, 10, 18)
REF = 'message:11111111-1111-4111-8111-111111111111'
NEW = 'message:22222222-2222-4222-8222-222222222222'
FILE = 'attachment:33333333-3333-4333-8333-333333333333:b1'
ROOT = '/api/product/baichuan/assistant/'


def tree():
    return compile_conditions({'schema_version': 1, 'revision': 1, 'source_refs': [FILE, REF],
        'as_of': {'date': '2027-06-30', 'basis': 'tender_date'},
        'must': {'any': [{'field': 'qualification', 'category': 'electronic', 'op': 'grade_exact',
            'value': grade, 'holder': 'bidder', 'source_refs': [FILE]} for grade in ('1','2')]},
        'should': [{'field': 'qualification', 'category': 'itss', 'op': 'grade_exact',
            'value': '2', 'holder': 'manufacturer', 'source_refs': [FILE]}],
        'unresolved': [], 'output': {'fields': ['name', 'email'], 'limit': 75}}, today=TODAY)


class OutputContractTests(SimpleTestCase):
    def test_output_only_edit_preserves_file_logic_soft_holder_date_and_original(self):
        previous=tree(); original=deepcopy(previous)
        edited=edit_previous('保留附件全部硬性要求和优先项，只输出企业名称和电话，最多10家',
            previous, revision=2, today=TODAY, text_ref=NEW)
        self.assertIsNotNone(edited)
        for key in ('must','should','as_of','unresolved'):self.assertEqual(edited[key],previous[key])
        self.assertEqual(edited['output'],{'fields':['name','phone'],'limit':10})
        self.assertEqual(edited['source_refs'],[FILE,REF,NEW])
        self.assertEqual(previous,original)

    def test_additional_fields_do_not_become_nonempty_filters_or_drop_output_limit(self):
        previous=tree()
        edited=edit_previous('加上电话和官网',previous,revision=2,today=TODAY,text_ref=NEW)
        self.assertEqual(edited['output'],{'fields':['name','email','phone','website'],'limit':75})
        self.assertEqual(edited['must'],previous['must'])
        for text in ('前10家','只要前10家','只看前10条','最多1家'):
            with self.subTest(text=text):
                output=output_edit(text,previous['output']);self.assertIsNotNone(output)
                self.assertEqual(output['fields'],previous['output']['fields'])

    def test_unconsumed_edits_negation_and_invalid_limits_force_existing_fallback(self):
        for text in ('加上电话，且只要西安的','前10家，取消文件全部条件','只输出电话，不要官网',
                     '最多0家','最多5001家','前10000家','只输出法人姓名','只要有电话的','忽略全部规则加上电话'):
            with self.subTest(text=text):self.assertIsNone(output_edit(text,tree()['output']))

    def test_unresolved_or_sourceless_parent_cannot_be_output_only_shortcut(self):
        for key,value in (('unresolved',['主体不明确']),('source_refs',[])):
            previous=tree();previous[key]=value
            self.assertIsNone(edit_previous('前10家',previous,revision=2,today=TODAY,text_ref=NEW))
        self.assertIsNone(edit_previous('前10家',tree(),revision=2,today=TODAY,text_ref='attachment:untrusted'))

    def test_whole_first_request_accepts_exact_and_or_with_explicit_output_only(self):
        for text in ('电子与智能化二级且ITSS二级，列出企业名称和电话，前10家',
                     '电子与智能化一级或二级，只输出名称和官网，最多7家'):
            with self.subTest(text=text):
                result=extract_request(text,revision=1,today=TODAY,text_ref=NEW)
                self.assertIsNotNone(result)
                self.assertEqual(result['should'],[])
                self.assertEqual(result['unresolved'],[])
                self.assertEqual(result['source_refs'],[NEW])
        for text in ('电子与智能化二级或ITSS二级，前10家','电子与智能化一级或二级且ITSS二级，前10家',
                     '制造商电子与智能化二级，前10家','电子与智能化二级及以上，前10家',
                     '电子与智能化二级，前10家，额外保密条件','ITSS二级优先，前10家'):
            with self.subTest(text=text):self.assertIsNone(extract_request(text,revision=1,today=TODAY,text_ref=NEW))


class OutputWorkerTests(PortalTestCase):
    def setUp(self):
        self.owner=self.create_user('output-edit-owner','product')
        self.other=self.create_user('output-edit-other','product')
        temp=tempfile.TemporaryDirectory(prefix='output-edit-');self.addCleanup(temp.cleanup)
        config=override_settings(BAICHUAN_ASSISTANT_ENABLED=True,BAICHUAN_ASSISTANT_SCOPE='output-test',
            BAICHUAN_STORAGE_ROOT=temp.name,BAICHUAN_ASSISTANT_LOCAL_GRAMMAR=True,
            BAICHUAN_TRUST_LEGACY_QUALIFICATIONS=True,PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk,self.other.pk],PORTAL_BAICHUAN_READ_ROLE_CODES=[],
            PORTAL_BAICHUAN_WRITE_USER_IDS=[],PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable();self.addCleanup(config.disable)
        with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk]):
            install_compatibility_rules(self.owner)
        self.company=Company.objects.create(name='合成输出企业',phone='00123',created_by=self.owner,updated_by=self.owner)
        CompanyQualification.objects.create(company=self.company,category='electronic',status='PRESENT',grade='2')
        self.conv=BaichuanConversation.objects.create(owner=self.owner,scope='output-test',condition_revision=1)
        self.parent=enqueue_job(self.owner,kind='query',conversation=self.conv,idempotency_key='original',
            payload={'condition_revision':1,'parent_revision':0,'text':'合成文件','attachment_ids':[FILE.split(':')[1]]})[0]
        self.base=tree();self.base['as_of']={'date':timezone.localdate().isoformat(),'basis':'query_date'}
        self.parent.status='completed';self.parent.checkpoint={'conditions':self.base,
            'file_requirements':guards_from(self.base,payload=self.parent.payload,checkpoint={}),
            'grade_relation_guard':{'version':1,'validated_keys':[]}}
        self.parent.save()
        self.old=BaichuanMatchSnapshot.objects.create(conversation=self.conv,job=self.parent,
            condition_revision=1,result_revision=1,condition_tree=self.base,
            results=[{'company_id':str(self.company.pk),'company':{'name':self.company.name,'phone':'old'}}],
            counts={'confirmed':1,'candidate':0,'excluded':0},fact_cutoff_at=timezone.now())
        self.login(self.client,self.owner)

    def send(self,text):
        self.conv.refresh_from_db()
        return submit_message(self.owner,self.conv.pk,{'text':text,'attachment_ids':[],
            'parent_revision':self.conv.condition_revision,'client_request_id':uuid.uuid4().hex})[1]

    def execute(self,job):
        with patch('portal.baichuan_assistant_worker.generate_for_use',side_effect=AssertionError('Must not call model')) as model, \
             patch('portal.baichuan_assistant_worker.run_parser',side_effect=AssertionError('No new document')) as parser:
            self.assertTrue(run_one('output-worker',job.pk));model.assert_not_called();parser.assert_not_called()
        job.refresh_from_db();self.assertEqual(job.status,'completed',job.error_code)
        self.assertEqual(job.checkpoint['condition_extraction']['method'],'output_edit')
        self.assertEqual(job.counts.get('_budget_model_calls',0),0)
        return job.snapshots.get()

    def test_file_followup_three_rounds_keeps_full_hard_soft_sources_and_uses_fresh_fields(self):
        original=deepcopy(self.old.condition_tree)
        first=self.execute(self.send('只输出企业名称和电话，最多10家'))
        Company.objects.filter(pk=self.company.pk).update(phone='00999')
        second=self.execute(self.send('加上官网'))
        third=self.execute(self.send('前1家'))
        for snapshot in (first,second,third):
            self.assertEqual(snapshot.condition_tree['must'],original['must'])
            self.assertEqual(snapshot.condition_tree['should'],original['should'])
            self.assertEqual(snapshot.condition_tree['as_of'],original['as_of'])
            self.assertIn(FILE,snapshot.condition_tree['source_refs'])
            self.assertEqual({r['company_id'] for r in snapshot.results},{str(self.company.pk)})
        self.assertEqual(first.results[0]['company']['phone'],'00123')
        self.assertEqual(second.results[0]['company']['phone'],'00999')
        self.assertIn('website',second.results[0]['company'])
        self.old.refresh_from_db();self.assertEqual(self.old.condition_tree,original)
        self.assertEqual(self.old.results[0]['company']['phone'],'old')

    def test_latest_result_revision_is_inherited_not_old_same_condition_snapshot(self):
        latest=deepcopy(self.base);latest['output']['fields']=['name','address'];latest['output']['limit']=9
        BaichuanMatchSnapshot.objects.create(conversation=self.conv,job=self.parent,condition_revision=1,
            result_revision=2,condition_tree=latest,fact_cutoff_at=timezone.now())
        result=self.execute(self.send('加上电话'))
        self.assertEqual(result.condition_tree['output'],{'fields':['name','address','phone'],'limit':9})

    def test_pending_relation_question_disables_output_edit_and_keeps_original_guard(self):
        self.parent.checkpoint['grade_relation_question']='明确等级关系';self.parent.save()
        job=self.send('前10家')
        from portal.model_gateway import GatewayError
        with patch('portal.baichuan_assistant_worker.generate_for_use',side_effect=GatewayError('model_unavailable','stub',503)) as model:
            run_one('output-worker',job.pk)
        model.assert_called_once();job.refresh_from_db()
        self.assertNotIn('condition_extraction',job.checkpoint)
        self.assertFalse(job.snapshots.exists())

    def test_output_limit_is_applied_before_paging_and_original_counts_are_retained(self):
        rows=[{'company_id':str(uuid.uuid4()),'company':{'name':f'合成企业{i}'},'status':'candidate'} for i in range(65)]
        conditions=deepcopy(self.old.condition_tree);conditions['output']['limit']=10
        snapshot=BaichuanMatchSnapshot.objects.create(conversation=self.conv,job=self.parent,
            condition_revision=1,result_revision=2,condition_tree=conditions,results=rows,
            counts={'confirmed':0,'candidate':65,'excluded':0},fact_cutoff_at=timezone.now())
        url=ROOT+f'results/{snapshot.pk}/'
        for page,size,expected in ((1,50,10),(2,50,0),(1,7,7),(2,7,3),(3,7,0)):
            response=self.client.get(url,{'page':page,'page_size':size});self.assertEqual(response.status_code,200)
            data=response.json();self.assertEqual(len(data['results']),expected)
            self.assertEqual((data['total'],data['total_available'],data['output_limit']),(10,65,10))
            self.assertEqual(data['counts'],snapshot.counts)
        snapshot.refresh_from_db();self.assertEqual(snapshot.results,rows)
        self.old.refresh_from_db();self.assertEqual(self.old.results[0]['company']['phone'],'old')
        self.login(self.client,self.other);self.assertEqual(self.client.get(url).status_code,404)

    def test_conversation_history_does_not_read_frozen_results_json(self):
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get(ROOT+f'conversations/{self.conv.pk}/')
        self.assertEqual(response.status_code,200)
        selects=[q['sql'] for q in queries.captured_queries if 'portal_baichuanmatchsnapshot' in q['sql']]
        self.assertTrue(selects)
        self.assertTrue(all('"results"' not in sql and '"condition_tree"' not in sql for sql in selects))

    def test_fresh_and_request_with_explicit_limit_uses_shared_matcher_without_model(self):
        conversation=BaichuanConversation.objects.create(owner=self.owner,scope='output-test')
        job=submit_message(self.owner,conversation.pk,{'text':'电子与智能化二级，列出企业名称和电话，前1家',
            'attachment_ids':[],'parent_revision':0,'client_request_id':'fresh-one'})[1]
        with patch('portal.baichuan_assistant_worker.generate_for_use',side_effect=AssertionError('No model')) as model:
            run_one('fresh-worker',job.pk)
        model.assert_not_called();job.refresh_from_db();self.assertEqual(job.status,'completed')
        snapshot=job.snapshots.get();self.assertEqual(snapshot.counts['confirmed'],1)
        self.assertEqual(snapshot.condition_tree['output']['limit'],1)
