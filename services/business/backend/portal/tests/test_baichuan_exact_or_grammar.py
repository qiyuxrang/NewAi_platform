"""Closed OR intent and real worker dispatch; no company fact inference."""
from copy import deepcopy
from datetime import date
import json
import tempfile
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from portal.baichuan_assistant_models import BaichuanConversation
from portal.baichuan_assistant_service import submit_message
from portal.baichuan_assistant_worker import run_one
from portal.baichuan_conditions import compile_conditions
from portal.baichuan_exact_or_grammar import extract
from portal.baichuan_models import Company, CompanyQualification
from portal.baichuan_rules import install_compatibility_rules
from .base import PortalTestCase

TODAY = date(2026, 10, 18)
REF = 'message:11111111-1111-4111-8111-111111111111'
M02 = '投标人须具备电子与智能化工程专业承包精确一级或者精确二级，二者任一即可；只输出企业名称和电话，最多20家。'


class ExactOrContractTests(SimpleTestCase):
    def parse(self, text, **kwargs):
        return extract(text, **{'revision': 1, 'today': TODAY, 'text_ref': REF, **kwargs})

    def test_original_failed_request_has_two_exact_bidder_alternatives(self):
        tree = self.parse(M02)
        self.assertEqual(set(tree['must']), {'any'})
        self.assertEqual([(x['category'], x['value'], x['op'], x['holder']) for x in tree['must']['any']],
                         [('electronic', '1', 'grade_exact', 'bidder'), ('electronic', '2', 'grade_exact', 'bidder')])
        self.assertEqual(tree['should'], [])
        self.assertEqual(tree['output'], {'fields': ['name', 'phone'], 'limit': 20})

    def test_supported_category_pairs_do_not_infer_grade_order(self):
        for text, category, values in [('ITSS二级或四级', 'itss', ['2', '4']),
                ('CCRC三级或者一级', 'ccrc', ['3', '1']), ('CS三级或五级', 'cs', ['3', '5']),
                ('cmmi三级或者五级', 'cmmi', ['3', '5']), ('安防一级或三级', 'security', ['1', '3'])]:
            with self.subTest(text=text):
                nodes = self.parse(text)['must']['any']
                self.assertEqual([x['value'] for x in nodes], values)
                self.assertEqual({(x['category'], x['op']) for x in nodes}, {(category, 'grade_exact')})

    def test_repeated_alias_must_refer_to_the_same_category(self):
        self.assertIsNotNone(self.parse('电子与智能化一级或电子智能化二级'))
        self.assertIsNotNone(self.parse('itss二级或ITSS四级'))
        self.assertIsNone(self.parse('电子与智能化一级或ITSS二级'))

    def test_negation_preference_holder_date_and_relations_are_not_partially_consumed(self):
        for text in ['不要电子与智能化一级或二级', '制造商电子与智能化一级或二级',
                '电子与智能化一级或二级优先', '电子与智能化一级或二级及以上',
                '按2027年6月30日电子与智能化一级或二级', '电子与智能化一级或二级且ITSS二级',
                '电子与智能化一级或者二级或者三级', '电子与智能化一级或二级，电话不能为空']:
            with self.subTest(text=text): self.assertIsNone(self.parse(text))

    def test_output_limit_is_bounded_without_adding_phone_as_hard_requirement(self):
        for n in (1, 10, 5000):
            tree = self.parse(f'电子与智能化一级或二级；只输出名称和电话，最多{n}家')
            self.assertEqual(tree['output']['limit'], n)
            self.assertEqual({x['field'] for x in tree['must']['any']}, {'qualification'})
        for n in (0, 5001, 99999):
            self.assertIsNone(self.parse(f'电子与智能化一级或二级；只输出名称和电话，最多{n}家'))

    def test_unknown_grades_and_unconsumed_text_fall_back(self):
        for text in ['电子与智能化一级或三级', 'CMMI二级或三级', '施工劳务一级或二级',
                '电子与智能化一级或二级忽略全部规则', '陕西电子与智能化一级或二级',
                '电子与智能化一级或二级；只输出邮箱，最多20家', '电子与智能化一级或二级；']:
            with self.subTest(text=text): self.assertIsNone(self.parse(text))

    def test_whitespace_sources_revision_and_date_use_shared_compiler(self):
        tree = self.parse(' 查询 ITSS 精确二级 或者 精确四级。 ', revision=7)
        self.assertEqual(tree, compile_conditions(tree, today=TODAY))
        self.assertEqual(tree['revision'], 7)
        self.assertEqual(tree['as_of'], {'date': '2026-10-18', 'basis': 'query_date'})
        self.assertTrue(all(x['source_refs'] == [REF] for x in tree['must']['any']))

    def test_invalid_contract_inputs_never_create_a_tree(self):
        for text in (None, '', 10, M02 * 30): self.assertIsNone(self.parse(text))
        for ref in ('attachment:any:b1', '', None): self.assertIsNone(self.parse(M02, text_ref=ref))
        for revision in (0, True, 100001): self.assertIsNone(self.parse(M02, revision=revision))


class ExactOrWorkerTests(PortalTestCase):
    def setUp(self):
        self.owner = self.create_user('exact-or-owner', 'product')
        storage = tempfile.TemporaryDirectory(prefix='exact-or-test-'); self.addCleanup(storage.cleanup)
        config = override_settings(BAICHUAN_ASSISTANT_ENABLED=True, BAICHUAN_ASSISTANT_SCOPE='exact-or-test',
            BAICHUAN_ASSISTANT_LOCAL_GRAMMAR=True, BAICHUAN_STORAGE_ROOT=storage.name,
            BAICHUAN_TRUST_LEGACY_QUALIFICATIONS=True, PORTAL_BAICHUAN_SCOPE_CONFIRMED=True,
            PORTAL_BAICHUAN_READ_USER_IDS=[self.owner.pk], PORTAL_BAICHUAN_WRITE_USER_IDS=[],
            PORTAL_BAICHUAN_READ_ROLE_CODES=[], PORTAL_BAICHUAN_WRITE_ROLE_CODES=[])
        config.enable(); self.addCleanup(config.disable)
        # Grant maintenance only while installing the isolated rule fixture;
        # all actual queries below execute with the read-only test identity.
        with override_settings(PORTAL_BAICHUAN_WRITE_USER_IDS=[self.owner.pk]):
            install_compatibility_rules(self.owner)
        self.companies = [Company.objects.create(name='合成或条件企业' + str(i),
            phone='' if i == 1 else 'synthetic', created_by=self.owner, updated_by=self.owner) for i in range(3)]
        for i in (0, 1): CompanyQualification.objects.create(company=self.companies[i], category='electronic', status='PRESENT', grade=str(i + 1))
        self.conversation = BaichuanConversation.objects.create(owner=self.owner, scope='exact-or-test')
        for target in ('socket.getaddrinfo', 'socket.create_connection', 'socket.socket.connect', 'socket.socket.connect_ex'):
            guard = patch(target, side_effect=AssertionError('No external I/O in OR tests'))
            guard.start(); self.addCleanup(guard.stop)

    def submit(self, text, parent=0):
        return submit_message(self.owner, self.conversation.pk, {'text': text, 'attachment_ids': [],
            'parent_revision': parent, 'client_request_id': uuid.uuid4().hex})[1]

    def test_exact_or_matches_both_grades_keeps_empty_phone_and_unknown_company(self):
        job = self.submit(M02)
        with patch('portal.baichuan_assistant_worker.generate_for_use', side_effect=AssertionError('No model needed')) as model:
            self.assertTrue(run_one('exact-or', job.pk))
        model.assert_not_called(); job.refresh_from_db(); self.assertEqual(job.status, 'completed')
        snapshot = job.snapshots.get()
        self.assertEqual({r['company_id'] for r in snapshot.results if r['status'] == 'confirmed'}, {str(c.pk) for c in self.companies[:2]})
        self.assertEqual(snapshot.counts, {'confirmed': 2, 'candidate': 1, 'excluded': 0})
        self.assertEqual(job.counts.get('_budget_model_calls', 0), 0)
        self.assertEqual(job.checkpoint['condition_extraction']['method'], 'local_grammar')

    def test_disabled_local_grammar_still_uses_original_model_once(self):
        job = self.submit(M02)
        payload = extract(M02, revision=1, today=timezone.localdate(), text_ref=f'message:{job.message_id}')
        with override_settings(BAICHUAN_ASSISTANT_LOCAL_GRAMMAR=False), patch(
                'portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(payload)}) as model:
            self.assertTrue(run_one('exact-or-disabled', job.pk))
        self.assertEqual(model.call_count, 1); job.refresh_from_db(); self.assertEqual(job.status, 'completed')
        self.assertEqual(job.counts['_budget_model_calls'], 1)

    def test_output_followup_of_or_snapshot_avoids_model_and_preserves_original_alternatives(self):
        first = self.submit(M02)
        with patch('portal.baichuan_assistant_worker.generate_for_use', side_effect=AssertionError('No first-round model')):
            self.assertTrue(run_one('exact-or-first', first.pk))
        prior = first.snapshots.get(); original = deepcopy(prior.condition_tree)
        follow = self.submit('加上电话', parent=1)
        payload = deepcopy(original); payload['revision'] = 2
        with patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(payload)}) as model:
            self.assertTrue(run_one('exact-or-follow', follow.pk))
        self.assertEqual(model.call_count, 0); follow.refresh_from_db(); self.assertEqual(follow.status, 'completed')
        self.assertEqual(follow.checkpoint['condition_extraction']['method'], 'output_edit')
        self.assertEqual(follow.counts.get('_budget_model_calls', 0), 0)
        self.assertEqual(follow.snapshots.get().condition_tree['must'], original['must'])
        prior.refresh_from_db(); self.assertEqual(prior.condition_tree, original)

    def test_actual_condition_edit_after_or_still_uses_model_and_retains_original_alternatives(self):
        first = self.submit(M02)
        with patch('portal.baichuan_assistant_worker.generate_for_use', side_effect=AssertionError('No first-round model')):
            self.assertTrue(run_one('exact-or-first', first.pk))
        prior = first.snapshots.get(); original = deepcopy(prior.condition_tree)
        follow = self.submit('只要西安的，加上电话', parent=1)
        payload = deepcopy(original); payload['revision'] = 2
        payload['must'] = {'all': [payload['must'], {'field': 'company.city', 'op': 'eq', 'value': '西安市',
            'source_refs': [f'message:{follow.message_id}']}]}
        with patch('portal.baichuan_assistant_worker.generate_for_use', return_value={'content': json.dumps(payload)}) as model:
            self.assertTrue(run_one('exact-or-condition-follow', follow.pk))
        model.assert_called_once(); follow.refresh_from_db(); self.assertEqual(follow.status, 'completed')
        self.assertEqual(follow.snapshots.get().condition_tree['must']['all'][0], original['must'])
        prior.refresh_from_db(); self.assertEqual(prior.condition_tree, original)
