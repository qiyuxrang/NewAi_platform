"""Assistant authority, public-query privacy, persistence and cancellation regressions."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import force_authenticate

from portal import product_knowledge_agent as agent
from portal import product_knowledge_api as api
from portal import product_assistant_tools as tools
from portal.product_service import ProductError

from .base import PortalTestCase
from .test_product_knowledge_api import _ProductKnowledgeApiFixture
from .test_product_knowledge_service import CONFIG, SCOPE


class AssistantToolTests(SimpleTestCase):
    def setUp(self):
        guard = patch.object(tools.knowledge, 'configuration', return_value=CONFIG)
        guard.start()
        self.addCleanup(guard.stop)

    def toolset(self, **kwargs):
        return tools.AssistantTools(kwargs.get('question', '请检索Python公开文档'), SCOPE, CONFIG,
                                    web_search=kwargs.get('web_search', True), recheck=lambda: None)

    def test_calculation_is_decimal_and_never_executes_code(self):
        self.assertEqual(tools.calculate('0.1 + 0.2'), '0.3')
        self.assertEqual(tools.calculate('(2+3)*4'), '20')
        for expression in ["__import__('os').getcwd()", '2**10000000', '1e9999', '1/0', 'True+1']:
            with self.subTest(expression=expression), self.assertRaises((ValueError, ArithmeticError)):
                tools.calculate(expression)

    def test_knowledge_scope_cannot_be_injected_or_expanded(self):
        toolbox = self.toolset()
        with patch.object(tools.knowledge, 'retrieve', return_value=[{
                'dataset_id': 'dataset-1', 'document_id': 'document-1', 'title': '文件', 'content': '来源'}]) as retrieve:
            result = toolbox.execute('knowledge_search', {'query': '设备'})
            retrieve.assert_called_once_with('设备', [], SCOPE, CONFIG)
            self.assertEqual(result['sources'][0]['id'], 'K1')
        for name, args in [('knowledge_read', {'dataset_id': 'other', 'document_id': 'secret'}),
                           ('knowledge_list', {'dataset_id': 'other'})]:
            with self.subTest(name=name), patch.object(tools.knowledge, 'list_chunks') as read, \
                    patch.object(tools.knowledge, 'list_documents') as listing:
                self.assertEqual(toolbox.execute(name, args)['error'], 'invalid_tool_arguments')
                read.assert_not_called()
                listing.assert_not_called()
        for name, args in [('knowledge_search', {'query': '设备', 'scope': {'all': True}}),
                           ('shell', {'command': 'whoami'})]:
            with self.subTest(name=name), self.assertRaises(ProductError):
                toolbox.execute(name, args)

    def test_document_reader_uses_only_allowed_document_and_bounded_page(self):
        toolbox = self.toolset()
        with patch.object(tools.knowledge, 'list_chunks', return_value={
                'document': {'name': '设备文档'}, 'chunks': [{'content': '原文'}], 'has_more': False}) as read:
            result = toolbox.execute('knowledge_read', {'dataset_id': 'dataset-1', 'document_id': 'document-1'})
        read.assert_called_once_with('dataset-1', 'document-1', 1, 4, CONFIG)
        self.assertEqual(result['sources'][0]['document_id'], 'document-1')

    def test_public_query_never_contains_model_added_private_context(self):
        toolbox = self.toolset()
        with patch.object(tools.web, 'search_public_query', return_value=[]) as search:
            self.assertIn('error', toolbox.execute('web_search', {'query': '秘密客户预算八百万'}))
            search.assert_not_called()
            toolbox.execute('web_search', {'query': 'Python'})
            search.assert_called_once_with('Python')
        with self.assertRaises(ProductError):
            self.toolset(web_search=False).execute('web_search', {})

    def test_page_fetch_requires_exact_user_or_search_url(self):
        toolbox = self.toolset(question='请读 https://example.com/manual')
        with patch.object(tools, 'fetch_public_page', return_value='公开原文') as fetch:
            self.assertIn('error', toolbox.execute('web_fetch', {'url': 'https://example.com/manual?private=secret'}))
            fetch.assert_not_called()
            self.assertEqual(toolbox.execute('web_fetch', {'url': 'https://example.com/manual'})['sources'][0]['type'], 'web')
        with patch('model_gateway.transport._resolve') as resolve:
            for url in ['http://127.0.0.1/', 'https://user:pass@example.com/', 'https://example.com:8443/']:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    tools.fetch_public_page(url)
            resolve.assert_not_called()

    def test_tool_budgets_and_argument_types_are_enforced(self):
        toolbox = self.toolset()
        for _ in range(12):
            self.assertEqual(toolbox.execute('calculate', {'expression': '1+1'})['value'], '2')
        with self.assertRaises(ProductError):
            toolbox.execute('calculate', {'expression': '1+1'})
        with self.assertRaises(ProductError):
            self.toolset().execute('knowledge_list', {'page': True})


def fake_run(*args, **kwargs):
    kwargs['recheck']()
    yield {'delta': '真实边界测试回答'}
    yield {'result': {'answer': '真实边界测试回答', 'sources': [], 'activities': [], 'assistant': True,
                       'web_search': kwargs['web_search'], 'outcome': 'answered', 'runtime': 'deepseek_harness'}}


class AssistantPersistenceTests(_ProductKnowledgeApiFixture, PortalTestCase):
    def assistant_request(self, item, **changes):
        payload = {'question': '你好', 'version': 0, 'request_id': str(uuid.uuid4()), 'assistant': True, **changes}
        request = self.factory.post('/api/product/knowledge/', payload, format='json')
        force_authenticate(request, user=self.owner)
        response = api.conversation(request, conversation_id=item.pk)
        if response.streaming:
            events = [json.loads(line[6:]) for chunk in response.streaming_content
                      for line in chunk.decode().splitlines() if line.startswith('data: ')]
            return response, events, payload
        return response, response.data, payload

    def cancel(self, item, request_id, user=None):
        request = self.factory.post('/api/product/knowledge/', {'request_id': str(request_id)}, format='json')
        force_authenticate(request, user=user or self.owner)
        return api.cancel_conversation(request, conversation_id=item.pk)

    def test_json_stream_and_idempotency_preserve_owner_and_scope(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                item = self.create()
                with patch.object(agent, 'run', side_effect=fake_run) as run:
                    response, result, payload = self.assistant_request(item, **({'stream': True} if streaming else {}))
                    self.assertEqual(response.status_code, 200)
                    done = result[-1]['done'] if streaming else result
                    self.assertEqual(done['version'], 1)
                    self.assertEqual(done['turns'][0]['runtime'], 'deepseek_harness')
                    replay, _, _ = self.assistant_request(item, **payload)
                    self.assertEqual(replay.status_code, 200)
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(self.cancel(item, payload['request_id']).data['version'], 1)
                self.outbound.assert_not_called()

    def test_stream_error_never_saves_partial_turn(self):
        item = self.create()
        def broken(*args, **kwargs):
            yield {'delta': '部分输出'}
            raise ProductError('unavailable', '未完成', 503)
        with patch.object(agent, 'run', side_effect=broken):
            _, events, _ = self.assistant_request(item, stream=True)
        self.assertIn('error', events[-1])
        self.assert_unchanged(item)

    def test_cancellation_revokes_only_matching_request_lease(self):
        item = self.create()
        claim, request_id = uuid.uuid4(), uuid.uuid4()
        type(item).objects.filter(pk=item.pk).update(pending_id=claim, pending_request_id=request_id,
            pending_until=timezone.now() + timedelta(seconds=120))
        with patch('portal.product_assistant_runtime.cancel_run') as stop:
            self.assertEqual(self.cancel(item, uuid.uuid4()).status_code, 409)
            stop.assert_not_called()
            self.assertEqual(self.cancel(item, request_id).status_code, 200)
            stop.assert_called_once_with(str(claim))
            self.assertEqual(self.cancel(item, request_id).status_code, 200)
        item.refresh_from_db()
        self.assertIsNone(item.pending_id)
        self.assertIsNone(item.pending_request_id)
        self.assertEqual(item.version, 0)

    def test_midstream_revocation_stops_release_and_save(self):
        item = self.create()
        def revoke(*args, **kwargs):
            self.grants[str(self.owner.pk)] = {'dataset-1': ['document-2']}
            yield {'delta': '禁止泄露'}
        with patch.object(agent, 'run', side_effect=revoke):
            _, events, _ = self.assistant_request(item, stream=True)
        self.assertEqual(events[-1]['error']['code'], 'scope_revoked')
        self.assertFalse(any('delta' in event for event in events))
        self.assert_unchanged(item)
