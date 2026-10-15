import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

test('answer requests accept SSE and JSON errors, preserve retry identity, and never retry automatically', async () => {
  const original = { fetch: globalThis.fetch, localStorage: globalThis.localStorage };
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false,
    appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false },
    optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    globalThis.localStorage = { getItem: () => 'isolated-token' };
    const { apiEventStream, ApiError } = await server.ssrLoadModule('/src/business/api.ts');
    const path = '/api/product/knowledge/conversations/conversation-1/';
    const payload = { question: '你好', version: 0, request_id: 'same-request-id', stream: true };
    const controller = new AbortController(), deltas = [], activities = [];
    let calls = 0, failure = null;
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.equal(url, '/api/enterprise/business/product/knowledge/conversations/conversation-1/');
      assert.equal(options.method, 'POST');
      assert.equal(options.credentials, 'omit');
      assert.equal(options.signal, controller.signal);
      assert.equal(options.headers.get('Authorization'), 'Bearer isolated-token');
      assert.equal(options.headers.get('Content-Type'), 'application/json');
      assert.deepEqual(JSON.parse(options.body), payload);
      const accept = options.headers.get('Accept');
      assert.match(accept, /text\/event-stream/);
      if (!accept.includes('application/json')) return Response.json({ detail: '无法满足Accept HTTP头的请求。' }, { status: 406 });
      if (failure) return Response.json({ code: failure.code, detail: failure.detail }, { status: failure.status });
      return new Response('data: {"activity":{"id":"A1","tool":"knowledge_search","status":"running","summary":"检索已授权资料"}}\n\ndata: {"delta":"你好"}\n\ndata: {"activity":{"id":"A1","tool":"knowledge_search","status":"completed","summary":"找到2项来源"}}\n\ndata: {"done":{"version":1,"turns":[{"request_id":"same-request-id"}]}}\n\n',
        { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } });
    };
    const send = () => apiEventStream(path, payload, controller.signal, delta => deltas.push(delta), activity => activities.push(activity));
    assert.equal((await send()).version, 1);
    assert.deepEqual(deltas, ['你好']);
    assert.deepEqual(activities.map(item => item.status), ['running', 'completed']);
    assert.equal(activities[0].id, activities[1].id);
    for (failure of [{ status: 403, code: 'forbidden', detail: '没有访问权限' }, { status: 409, code: 'conflict', detail: '版本已变化' }]) {
      const before = calls;
      await assert.rejects(send(), error => error instanceof ApiError && error.status === failure.status
        && error.code === failure.code && error.message === failure.detail);
      assert.equal(calls, before + 1);
    }
    failure = null;
    assert.equal((await send()).turns[0].request_id, payload.request_id);
    assert.equal(calls, 4);
    for (const tool of ['knowledge_list', 'knowledge_read', 'web_fetch', 'calculate', 'plan']) {
      globalThis.fetch = async () => new Response(`data: ${JSON.stringify({ activity: { id: 'A2', tool, status: 'completed', summary: '实际工具已完成' } })}\n\ndata: {"done":{"version":1}}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } });
      assert.equal((await send()).version, 1);
      assert.equal(activities.at(-1).tool, tool);
    }
    const history = { id: 'conversation-1', title: '完整历史', version: 40, turns: Array.from({ length: 40 }, (_, index) => ({
      question: `历史问题${index}`, answer: '历史回答', outcome: 'answered', request_id: `history-${index}`,
      sources: [{ id: 'K1', title: '已授权文档', content: '完整引用'.repeat(1500) }],
    })) };
    const frame = `data: ${JSON.stringify({ done: history })}\n\n`;
    assert.ok(frame.length > 65536);
    globalThis.fetch = async () => new Response(new ReadableStream({ start(stream) {
      for (let offset = 0; offset < frame.length; offset += 32000) stream.enqueue(new TextEncoder().encode(frame.slice(offset, offset + 32000)));
      stream.close();
    } }), { headers: { 'Content-Type': 'text/event-stream' } });
    assert.deepEqual(await send(), history, 'a complete conversation can exceed 64 KiB');
    for (const suffix of ['', '\n\n']) {
      globalThis.fetch = async () => new Response(`data: ${'x'.repeat(8 * 1024 * 1024)}${suffix}`, { headers: { 'Content-Type': 'text/event-stream' } });
      await assert.rejects(send(), error => error instanceof ApiError && error.code === 'invalid_response' && /回答流过长/.test(error.message));
    }
    globalThis.fetch = async () => new Response(`data: ${JSON.stringify({ delta: 'x'.repeat(4001) })}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } });
    await assert.rejects(send(), error => error instanceof ApiError && error.code === 'invalid_response');
    const validActivities = [
      { id: 'H1', tool: 'web_search', status: 'running', summary: '正在检索今天的新闻😀' },
      { id: 'H1', tool: 'web_search', status: 'completed', summary: '已获取公开新闻摘要' },
      { id: 'H2', tool: 'web_fetch', status: 'running', summary: '正在读取新闻页面' },
      { id: 'H2', tool: 'web_fetch', status: 'failed', summary: '网页暂时无法读取，可使用搜索摘要。' },
    ];
    const invalidActivities = [null, 'invalid', [], {},
      { id: 'A1', tool: 'execute', status: 'running', summary: 'invalid' },
      { id: 'A1', tool: 'answer', status: 'thought', summary: 'invalid' },
      { id: '无效标识', tool: 'answer', status: 'running', summary: 'invalid' },
      { id: 'A'.repeat(65), tool: 'answer', status: 'running', summary: 'invalid' },
      { id: 'A1', tool: 'plan', status: 'completed', summary: '中'.repeat(501) },
      { id: 'A1', tool: 'plan', status: 'completed', summary: '😀'.repeat(251) },
      { id: 'A1', tool: 'answer', status: 'running', summary: null },
      { id: 'A1', tool: { toString: null, valueOf: null }, status: 'running', summary: 'invalid' },
      { id: 'A1', tool: 'answer', status: { toString: null, valueOf: null }, summary: 'invalid' },
    ];
    const beforeActivities = activities.length, beforeDeltas = deltas.length;
    globalThis.fetch = async () => new Response([
      ...validActivities.slice(0, 1).map(activity => ({ activity })),
      ...invalidActivities.map(activity => ({ activity })),
      ...validActivities.slice(1).map(activity => ({ activity })),
      { delta: '今天的新闻摘要😀' }, { done: { version: 2 } },
    ].map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } });
    assert.equal((await send()).version, 2, 'invalid progress must not interrupt the answer');
    assert.deepEqual(activities.slice(beforeActivities), validActivities, 'invalid progress must never reach the UI');
    assert.deepEqual(deltas.slice(beforeDeltas), ['今天的新闻摘要😀']);
    const resets = [];
    globalThis.fetch = async () => new Response([
      { delta: '我先检索资料。' },
      { activity: { id: 'bad', tool: 'execute', status: 'completed', summary: 'invalid' }, reset_answer: true },
      { activity: { id: 'H1', tool: 'knowledge_search', status: 'completed', summary: '工具完成' }, reset_answer: true },
      { activity: { id: 'M1', tool: 'plan', status: 'completed', summary: '我先检索资料。' }, reset_answer: true },
      { delta: '正式回答' }, { done: { version: 3 } },
    ].map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } });
    assert.equal((await apiEventStream(path, payload, controller.signal, (delta, reset) => resets.push([delta, reset === true]))).version, 3);
    assert.deepEqual(resets, [['我先检索资料。', false], ['', true], ['正式回答', false]], 'only validated completed process notes reset the draft');
    globalThis.fetch = async () => new Response('data: {"error":{"code":"scope_revoked","detail":"授权已撤销"}}\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
    await assert.rejects(send(), error => error instanceof ApiError && error.status === 403);
  } finally {
    Object.assign(globalThis, original);
    await server.close();
  }
});
