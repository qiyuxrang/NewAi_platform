from unittest.mock import patch

from django.test import override_settings

from portal.product_models import DocumentTask
from portal.product_service import append_revision
from .base import PortalTestCase
from . import test_product_api as fixture


class SavedDraftDownloadTests(PortalTestCase):
    input_payload = fixture.ProductApiTests.input_payload
    create_task = fixture.ProductApiTests.create_task
    save_blueprint = fixture.ProductApiTests.save_blueprint
    approve_blueprint = fixture.ProductApiTests.approve_blueprint

    def blueprint_payload(self):
        payload = fixture.ProductApiTests.blueprint_payload(self)
        payload['chapters'].append({'id': 'plan', 'title': '实施计划', 'scope': '项目实施', 'source_ids': ['1']})
        return payload

    def setUp(self):
        fixture.ProductApiTests.setUp(self)
        task = self.save_blueprint(self.create_task())
        with override_settings(PRODUCT_MODEL_CALLS_ALLOWED=True):
            self.approve_blueprint(task)
        self.task = DocumentTask.objects.get(pk=task['id'])
        self.current = self.task.revisions.get(kind='input', version=self.task.input_version)
        self.blueprint = self.task.revisions.get(kind='blueprint', version=self.task.blueprint_version)

    def chapter(self, text, family='technical-solution', **kwargs):
        payload = {'chapter_id': 'overview', 'title': '项目概述', 'paragraphs': [text], 'source_ids': ['1']}
        payload.update(kwargs.pop('payload', {}))
        return append_revision(self.task, 'chapter', payload, actor=self.owner, family=family,
                               input_hash=kwargs.pop('input_hash', self.current.sha256),
                               blueprint_hash=kwargs.pop('blueprint_hash', self.blueprint.sha256))

    def url(self, family='technical-solution', query=''):
        return f'/api/product/tasks/{self.task.pk}/saved-draft/download/?family={family}{query}'

    def text(self, response):
        self.assertEqual(response.status_code, 200, getattr(response, 'content', b''))
        return b''.join(response.streaming_content).decode('utf-8-sig')

    def test_running_and_failed_allow_partial_saved_text_without_artifacts(self):
        self.chapter('已保存技术正文。')
        for state in ('RUNNING', 'FAILED', 'QUEUED'):
            self.task.state = state
            self.task.save(update_fields=['state'])
            response = self.owner_client.get(self.url())
            text = self.text(response)
            for expected in ('已保存技术正文。', '未完成章节：实施计划', '已保存章节：1 / 2',
                             '正文快照', '未包含完整图文排版', '无需再次审批'):
                self.assertIn(expected, text)
            self.assertNotIn('未审批', text)
            self.assertIn('no-store', response['Cache-Control'])
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertIn('.txt', response['Content-Disposition'])
        self.assertFalse(self.task.artifacts.exists())
        self.assertEqual(self.task.approvals.count(), 1)

    def test_owner_and_assigned_reviewer_only_and_revoked_source_denied(self):
        self.chapter('授权正文')
        self.assertIn('授权正文', self.text(self.reviewer_client.get(self.url())))
        self.assertEqual(self.other_client.get(self.url()).status_code, 404)
        with override_settings(PRODUCT_REVIEWER_IDS=()):
            self.assertEqual(self.reviewer_client.get(self.url()).status_code, 404)
        with patch('portal.product_outputs.input_authorized', return_value=False):
            response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'source_permission_changed')

    def test_latest_current_chapter_only_with_family_isolation_and_blueprint_order(self):
        self.chapter('旧正文')
        self.chapter('可研正文', family='feasibility')
        self.chapter('新正文')
        self.chapter('实施正文', payload={'chapter_id': 'plan', 'title': '实施计划'})
        self.chapter('历史错误输入正文', input_hash='0' * 64)
        self.chapter('历史错误蓝图正文', blueprint_hash='1' * 64)
        self.chapter('蓝图外章节正文', payload={'chapter_id': 'extra', 'title': '额外章节'})
        text = self.text(self.owner_client.get(self.url(query='&history=1')))
        for excluded in ('旧正文', '可研正文', '历史错误输入正文', '历史错误蓝图正文', '蓝图外章节正文'):
            self.assertNotIn(excluded, text)
        self.assertLess(text.index('新正文'), text.index('实施正文'))
        self.assertIn('可研正文', self.text(self.owner_client.get(self.url('feasibility'))))

    def test_latest_invalid_source_does_not_fall_back_to_older_text(self):
        self.chapter('旧可导出正文')
        self.chapter('越权来源正文', payload={'source_ids': ['foreign-source']})
        response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'saved_draft_unavailable')

    def test_missing_saved_text_and_invalid_family_are_explicit(self):
        self.assertEqual(self.owner_client.get(self.url()).json()['code'], 'saved_draft_unavailable')
        for family in ('presentation', 'other', ''):
            self.assertEqual(self.owner_client.get(self.url(family)).status_code, 400)

    def test_input_and_blueprint_query_versions_guard_selected_text(self):
        self.chapter('当前正文')
        query = f'&input_version={self.task.input_version}&blueprint_version={self.task.blueprint_version}'
        self.assertIn('当前正文', self.text(self.owner_client.get(self.url(query=query))))
        for key in ('input_version', 'blueprint_version'):
            response = self.owner_client.get(self.url(query=f'&{key}=999'))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['code'], 'stale_draft')
            self.assertEqual(self.owner_client.get(self.url(query=f'&{key}=bad')).status_code, 400)

    def test_new_input_or_unapproved_blueprint_cannot_export_history(self):
        self.chapter('过期正文')
        newer = append_revision(self.task, 'input', {**self.current.payload, 'requirements': '新要求'}, actor=self.owner)
        self.task.input_version = newer.version
        self.task.save(update_fields=['input_version'])
        response = self.owner_client.get(self.url(query='&history=1'))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'blueprint_approval_required')

    def test_permission_and_blueprint_are_rechecked_before_releasing_bytes(self):
        self.chapter('不能释放的正文')
        with patch('portal.product_outputs.input_authorized', side_effect=[True, False]):
            response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 404)
        with patch('portal.product_outputs.approved_blueprint', side_effect=[self.blueprint, None]):
            response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 409)

    def test_current_input_pointer_excludes_newer_unselected_revision(self):
        self.chapter('当前正文')
        append_revision(self.task, 'input', {**self.current.payload, 'requirements': '未选中草稿输入'}, actor=self.owner)
        self.assertIn('当前正文', self.text(self.owner_client.get(self.url())))
