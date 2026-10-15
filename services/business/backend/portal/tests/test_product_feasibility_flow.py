"""Isolated real worker calls, checkpoint reuse and draft guide enforcement."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings

from portal import product_feasibility as guide
from portal.product_models import DocumentApproval
from portal.product_service import append_revision, approval_authorization, validate_blueprint
from portal.product_service import digest
from portal.product_content_quality import content_quality_policy_hash
from portal.product_documents import content_document
from portal.product_diagrams import validate_document_requirements
from portal.product_worker import (_content_review_current, _ensure_content_review, _generate_family,
                                    _model, _planned_review_requests, _review_family, claim_task, ExecutionError)
from . import test_product_worker as fixture
from .base import PortalTestCase


@override_settings(PRODUCT_P1_ENABLED=True, PRODUCT_MODEL_CALLS_ALLOWED=True,
                   PRODUCT_TECHNICAL_TARGET_CHARACTERS=3, PRODUCT_FEASIBILITY_TARGET_CHARACTERS=3,
                   PRODUCT_COST_POLICY={"approval_ref": "isolated-test-only", "currency": "TEST",
                       "max_task_cost": "100", "route_cost_caps": {
                           "product_blueprint": "1", "product_writing": "1", "product_review": "1"}})
class FeasibilityFlowTests(PortalTestCase):
    def setUp(self):
        fixture.ProductWorkerTests.setUp(self)
        catalog = guide.catalog()
        sections = [section for chapter in catalog['chapters'] for section in chapter['sections']]
        sections += catalog['appendices']
        payload = {**self.blueprint_payload, 'chapters': [
            {**self.blueprint_payload['chapters'][0], 'family': 'technical-solution'},
            {'id': 'feas-overview', 'title': '项目概述', 'scope': '验证项目名称的具体描述，其他范围在合成用例中明确排除。',
             'source_ids': ['r1'], 'family': 'feasibility'}],
            'feasibility_guide': {'asset_sha256': guide.asset_hash(), 'sections': [
                {'section_id': section['id'], 'status': 'include' if section['id'] == '1.1' else 'not_applicable',
                 'chapter_ids': ['feas-overview'] if section['id'] == '1.1' else [],
                 'reason': '合成单元测试只验证名称规则，不代表真实业务适用性判断。'} for section in sections]}}
        self.blueprint = append_revision(self.task, 'blueprint', validate_blueprint(payload, self.input_payload),
            input_hash=self.input_revision.sha256, actor=self.owner)
        self.task.blueprint_version = self.blueprint.version
        self.task.pending_action = 'generate_outputs'
        self.task.save(update_fields=['blueprint_version', 'pending_action'])
        DocumentApproval.objects.create(task=self.task, revision=self.blueprint, actor=self.owner,
            decision='approve', sha256=self.blueprint.sha256,
            authorization=approval_authorization(self.task, self.owner))
        self.task_id, self.fence, self.attempt_id = claim_task()
        self.task.refresh_from_db()

    def saved_chapter(self):
        return append_revision(self.task, 'chapter', {'chapter_id': 'feas-overview', 'title': '项目概述',
            'paragraphs': ['项目名称为隔离合成方案，沿用本次项目资料给出的名称，简称应在编制前由建设单位确认。'],
            'source_ids': ['r1']}, input_hash=self.input_revision.sha256,
            blueprint_hash=self.blueprint.sha256, family='feasibility')

    @staticmethod
    def covered_reply(*args, **kwargs):
        request = json.loads(args[2][1]['content'])
        chapter = request['chapters'][0]
        response = {'passed': True, 'issues': [], 'guide_checks': [
            {'id': item['id'], 'status': 'covered',
             'evidence': [{'chapter_id': chapter['chapter_id'], 'quote': chapter['paragraphs'][0]}],
             'reason': '本合成回执引用实际发送正文，验证协议与缓存，不证明模型判断能力。'}
            for item in request['guide_requirements']]}
        return {'content': json.dumps(response, ensure_ascii=False), 'prompt_tokens': 1, 'completion_tokens': 1}

    @patch('portal.product_worker.generate_for_use')
    def test_writing_receives_full_approved_requirements_without_source_duplicates(self, model):
        reply = {'chapter_id': 'feas-overview', 'title': '项目概述',
            'paragraphs': ['项目名称为隔离合成方案，采用资料中给出的原名。'], 'source_ids': ['r1']}
        model.side_effect = [{'content': json.dumps(reply)}, {'content': json.dumps({**reply,
            'paragraphs': ['## 项目名称\n' + reply['paragraphs'][0]]})}]
        _generate_family(self.task_id, self.fence, self.attempt_id, self.task, self.input_revision,
                         self.blueprint, 'feasibility')
        request = json.loads(model.call_args.args[2][1]['content'])
        self.assertEqual([section['id'] for section in request['feasibility_requirements']], ['1.1'])
        self.assertTrue(request['feasibility_requirements'][0]['writing_requirements'])
        self.assertNotIn('source_text', request['feasibility_requirements'][0])
        self.assertEqual(model.call_count, 2)

    @patch('portal.product_worker.generate_for_use', side_effect=covered_reply)
    def test_draft_runs_guide_review_and_reuses_only_verified_checkpoint(self, model):
        chapters = [self.saved_chapter()]
        first = _ensure_content_review(self.task, self.fence, self.attempt_id,
            self.input_revision, self.blueprint, chapters, 'feasibility')
        self.assertEqual(first.payload['model_review']['status'], 'not_run')
        self.assertTrue(first.payload['guide_review']['guide_coverage']['complete'])
        self.assertTrue(first.payload['full_document_human_review_required'])
        self.assertFalse(first.payload['passed'])
        self.assertTrue(_content_review_current(self.task, first, self.input_revision, self.blueprint, chapters))
        calls = model.call_count
        second = _ensure_content_review(self.task, self.fence, self.attempt_id,
            self.input_revision, self.blueprint, chapters, 'feasibility')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(model.call_count, calls)

        self.task.refresh_from_db()
        self.task.checkpoint['content_review_batches']['feasibility']['batches'][0]['guide_checks'][0]['evidence'][0]['quote'] = '伪造证据'
        self.task.save(update_fields=['checkpoint'])
        # The completed review has its own valid receipts; a poisoned resume
        # checkpoint must not erase it, and must never be reused in a rescan.
        self.assertTrue(_content_review_current(self.task, first, self.input_revision, self.blueprint, chapters))
        _review_family(self.task_id, self.fence, self.attempt_id, self.task,
            self.input_revision, self.blueprint, chapters, 'feasibility', guide_only=True)
        self.assertGreater(model.call_count, calls)

    @override_settings(PRODUCT_MAX_MODEL_CALLS=1)
    @patch('portal.product_worker.generate_for_use')
    def test_invalid_evidence_correction_cannot_bypass_task_call_budget(self, model):
        chapters = [self.saved_chapter()]
        requests, _ = _planned_review_requests(self.task, self.input_revision, self.blueprint,
            chapters, 'feasibility', guide_only=True)
        invalid = json.loads(self.covered_reply(None, None, [{'content': ''},
            {'content': json.dumps(requests[0], ensure_ascii=False)}])['content'])
        invalid['guide_checks'][0]['evidence'][0]['quote'] = '未发送的正文'
        model.return_value = {'content': json.dumps(invalid, ensure_ascii=False)}
        with self.assertRaises(ExecutionError) as caught:
            _model(self.task_id, self.fence, self.attempt_id, 'product_review', requests[0])
        self.assertEqual(caught.exception.code, 'model_call_limit')
        self.assertEqual(model.call_count, 1)

    def test_approved_scope_creates_native_tables_and_only_applicable_figures(self):
        chapter = self.saved_chapter()
        chapter.payload['paragraphs'] = ['## 项目名称\n项目名称沿用建设单位提供的正式名称。',
            '表1-1 项目名称核对\n| 字段 | 项目资料 |\n| --- | --- |\n| 名称 | 待确认 |']
        content = content_document(self.task, self.input_revision, self.blueprint, [chapter], 'feasibility', draft=True)
        self.assertEqual(validate_document_requirements(content)['figure_count'], 0)
        table = next(block for block in content['blocks'] if block['type'] == 'table')
        self.assertEqual(table['rows'], [['名称', '待确认']])
        plan = self.blueprint.payload['feasibility_guide']['sections']
        entry = next(entry for entry in plan if entry['section_id'] == '5.2.2')
        entry.update(status='include', chapter_ids=['feas-overview'])
        content = content_document(self.task, self.input_revision, self.blueprint, [chapter], 'feasibility', draft=True)
        self.assertEqual(validate_document_requirements(content)['figure_count'], 2)
        content['blocks'] = [block for block in content['blocks'] if block.get('id') != 'DIAGRAM_01_FIGURE']
        with self.assertRaises(ValueError):
            validate_document_requirements(content)

    @patch('portal.product_worker.generate_for_use')
    def test_normal_review_cache_rechecks_whole_guide_reduction(self, model):
        chapters = [self.saved_chapter()]
        def reply(*args, **kwargs):
            request = json.loads(args[2][1]['content'])
            if not request.get('review_contract', {}).get('guide_audit_only'):
                response = {'passed': True, 'issues': []}
            else:
                response = {'passed': True, 'issues': [], 'guide_checks': [
                    {'id': item['id'], 'status': 'not_seen', 'evidence': [],
                     'reason': '本批尚未出现该项要求的正文证据。'} for item in request['guide_requirements']]}
            return {'content': json.dumps(response, ensure_ascii=False)}
        model.side_effect = reply
        result = _review_family(self.task_id, self.fence, self.attempt_id, self.task,
            self.input_revision, self.blueprint, chapters, 'feasibility')
        self.assertFalse(result['guide_coverage']['passed'])
        checked = {'model_review': result, 'quality_policy_sha256': content_quality_policy_hash(),
                   'chapter_hashes': {chapter.payload['chapter_id']: chapter.sha256 for chapter in chapters}}
        review = SimpleNamespace(change_reason='worker_review', payload=checked, sha256=digest(checked),
            family='feasibility', input_hash=self.input_revision.sha256, blueprint_hash=self.blueprint.sha256)
        self.assertTrue(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
        checked['model_review']['guide_coverage']['passed'] = True
        review.sha256 = digest(checked)
        self.assertFalse(_content_review_current(self.task, review, self.input_revision, self.blueprint, chapters))
