import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('assistant capabilities stay independent and cancellation preserves live streams and completion races', async () => {
  const original = { fetch: globalThis.fetch, window: globalThis.window, localStorage: globalThis.localStorage };
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' },
    plugins: [{ name: 'isolated-assistant-hooks', resolveId: id => id === '/@assistant-test-hooks' ? '\0assistant-test-hooks' : null,
      load: id => id === '\0assistant-test-hooks' ? ['useState', 'useRef', 'useEffect', 'useCallback'].map(name => `export const ${name} = (...args) => globalThis.assistantTestHooks.${name}(...args);`).join(' ') : null,
      transform: (code, id) => /\/(ProductKnowledge\.tsx|workbench-resize\.ts)$/.test(id.replaceAll('\\', '/')) ? code.replaceAll('from "react"', 'from "/@assistant-test-hooks"') : null }] });
  class Hooks {
    slots = []; index = 0; effects = [];
    useState = initial => { const index = this.index++; this.slots[index] ??= { value: typeof initial === 'function' ? initial() : initial }; return [this.slots[index].value, next => { this.slots[index].value = typeof next === 'function' ? next(this.slots[index].value) : next; }]; };
    useRef = initial => { const index = this.index++; return this.slots[index] ??= { current: initial }; };
    useCallback = fn => { this.index++; return fn; };
    useEffect = (fn, deps) => { const index = this.index++; const old = this.slots[index]; if (!old || deps.some((value, i) => value !== old.deps[i])) this.effects.push(() => { old?.cleanup?.(); this.slots[index] = { deps, cleanup: fn() }; }); };
    render(component) { this.index = 0; globalThis.assistantTestHooks = this; const tree = component(); for (const effect of this.effects.splice(0)) effect(); return tree; }
    dispose() { for (const slot of this.slots) slot?.cleanup?.(); }
  }
  const find = (node, predicate) => {
    if (!node || typeof node !== 'object') return undefined;
    if (predicate(node)) return node;
    for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  };
  const text = node => node == null || typeof node === 'boolean' ? '' : typeof node !== 'object' ? String(node) : [node.props?.children].flat(Infinity).map(text).join('');
  const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
  globalThis.localStorage = { getItem: () => 'isolated-token' };
  globalThis.window = { innerWidth: 1440 };
  try {
    const { default: ProductKnowledge } = await server.ssrLoadModule('/src/business/product/ProductKnowledge.tsx');
    const setup = async (assistantAvailable = true, options = {}) => {
      const hooks = new Hooks();
      const state = { stream: null, streamSignal: null, payload: null, cancel: null, cancelCalls: 0, datasetCalls: 0,
        status: { available: true, knowledge: options.knowledge, web_search: { available: options.web === true }, assistant: { runtime: 'deepseek_harness', available: assistantAvailable, help: '助手暂不可用，请稍后重试。' } } };
      const conversation = { id: 'conversation-1', title: '测试会话', version: 0, turns: options.turns || [] };
      globalThis.fetch = async (path, options) => {
        if (path.endsWith('/status/')) return Response.json(state.status);
        if (path.endsWith('/datasets/')) { state.datasetCalls++; return state.datasetError ? Response.json(state.datasetError, { status: 403 }) : Response.json({ datasets: state.datasets || [] }); }
        if (path.endsWith('/conversations/')) return Response.json(options.method === 'POST' ? conversation : { conversations: [conversation] });
        if (path.endsWith('/cancel/')) {
          state.cancelCalls++;
          assert.deepEqual(JSON.parse(options.body), { request_id: state.payload.request_id });
          assert.equal(options.signal.aborted, false);
          return new Promise(resolve => { state.cancel = resolve; });
        }
        if (options.method !== 'POST') return Response.json(state.finished || conversation);
        state.payload = JSON.parse(options.body); state.streamSignal = options.signal;
        return new Response(new ReadableStream({ start(controller) { state.stream = controller; } }), { headers: { 'Content-Type': 'text/event-stream' } });
      };
      const render = () => hooks.render(ProductKnowledge);
      const button = label => find(render(), node => node.type === 'button' && text(node) === label);
      const input = () => find(render(), node => node.type === 'textarea');
      const replay = async () => { find(render(), node => node.type === 'button' && node.props.title === conversation.title).props.onClick(); await settle(); };
      const event = value => state.stream.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`));
      const complete = async () => {
        state.finished = { ...conversation, version: 1, turns: [{ question: state.payload.question, answer: '已完成的回答', outcome: 'answered', request_id: state.payload.request_id, sources: [], assistant: true, activities: [{ id: 'A1', tool: 'plan', status: 'completed', summary: '历史过程' }] }] };
        event({ done: state.finished }); await settle();
      };
      render(); await settle();
      const send = async () => { input().props.onChange({ target: { value: '请阅读文档后计算' } }); find(render(), node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await settle(); };
      return { state, hooks, conversation, render, button, input, event, complete, send, replay };
    };

    let view;
    for (const available of [true, false]) {
      view = await setup(true, { web: !available });
      assert.equal(view.button('联网搜索'), undefined, 'retrieval has no manual switch');
      view.state.status.web_search.available = available;
      await view.send();
      assert.equal(view.state.payload.web_search, available, 'send uses freshly checked server capability automatically');
      await view.complete();
      view.hooks.dispose();
    }
    view = await setup(); await view.send();
    assert.equal(view.input().props.value, '');
    assert.equal(view.input().props.disabled, true);
    view.event({ activity: { id: 'A1', tool: 'knowledge_read', status: 'running', summary: '读取授权文档' } });
    view.event({ delta: '实时正文' }); await settle();
    const steps = find(view.render(), node => node.type?.name === 'ProcessingSteps');
    const processingMarkup = renderToStaticMarkup(React.createElement(steps.type, steps.props));
    assert.match(processingMarkup, /阅读知识文档/);
    assert.doesNotMatch(processingMarkup, /<details[^>]*\bopen(?:=|\s|>)/, 'processing starts collapsed');
    assert.ok(find(view.render(), node => node.props?.content === '实时正文'));
    view.event({ activity: { id: 'M1', tool: 'plan', status: 'completed', summary: '我先检索已授权资料。' }, reset_answer: true }); await settle();
    assert.equal(find(view.render(), node => node.props?.content === '实时正文'), undefined, 'a confirmed tool round moves out of the answer draft');
    const foldedSteps = find(view.render(), node => node.type?.name === 'ProcessingSteps');
    assert.match(renderToStaticMarkup(React.createElement(foldedSteps.type, foldedSteps.props)), /我先检索已授权资料/);
    view.event({ delta: '正式回答继续流式输出' }); await settle();
    assert.ok(find(view.render(), node => node.props?.content === '正式回答继续流式输出'));
    view.button('停止').props.onClick(); await settle();
    assert.equal(view.button('正在停止…').props.disabled, true);
    view.button('正在停止…').props.onClick(); assert.equal(view.state.cancelCalls, 1);
    assert.equal(view.state.streamSignal.aborted, false, 'cancel must be confirmed before aborting the stream');
    view.state.cancel(Response.json(view.conversation)); await settle();
    assert.equal(view.state.streamSignal.aborted, true);
    assert.equal(view.input().props.disabled, false);
    assert.match(text(view.render()), /已停止本次回答/);
    assert.equal(find(view.render(), node => node.type?.name === 'ProcessingSteps'), undefined);
    view.hooks.dispose();

    view = await setup(); await view.send();
    view.button('停止').props.onClick(); await settle();
    view.state.cancel(Response.json({ detail: '暂时无法停止' }, { status: 503 })); await settle();
    assert.equal(view.state.streamSignal.aborted, false);
    assert.equal(view.button('停止').props.disabled, false);
    view.event({ delta: '取消失败后仍继续' }); await settle();
    assert.ok(find(view.render(), node => node.props?.content === '取消失败后仍继续'));
    await view.complete();
    assert.equal(view.input().props.disabled, false);
    assert.equal(find(view.render(), node => node.type?.name === 'ProcessingSteps'), undefined);
    assert.ok(find(view.render(), node => node.props?.content === '已完成的回答'));
    assert.equal(find(view.render(), node => node.props?.role === 'alert'), undefined, 'a completed answer clears the earlier cancellation error');
    view.hooks.dispose();

    view = await setup(); await view.send();
    view.button('停止').props.onClick(); await settle();
    await view.complete();
    assert.equal(view.input().props.disabled, false, 'completion wins while cancel is pending');
    view.state.cancel(Response.json(view.conversation)); await settle();
    assert.ok(find(view.render(), node => node.props?.content === '已完成的回答'), 'late cancel cannot restore stale history');
    assert.doesNotMatch(text(view.render()), /已停止本次回答/);
    view.hooks.dispose();

    view = await setup(); await view.send();
    view.button('停止').props.onClick(); await settle();
    view.event({ error: { code: 'conflict', detail: '本次执行已取消' } }); await settle();
    assert.equal(view.input().props.disabled, true, 'lease revocation keeps controls locked until cancel confirms');
    view.state.cancel(Response.json(view.conversation)); await settle();
    assert.equal(view.input().props.disabled, false);
    view.hooks.dispose();

    const privateTurn = { question: '旧问题', answer: '私有历史正文', outcome: 'answered', request_id: 'history-1', sources: [{ id: 'K1', dataset_id: 'library-1', document_id: 'doc-1', title: '私有文档', content: '私有引用' }], assistant: true };
    for (const code of ['disabled', 'unconfigured', 'knowledge_not_authorized']) {
      view = await setup(true, { knowledge: { available: false, code, help: '知识库未开通，仍可直接对话。' }, turns: [privateTurn] });
      assert.equal(view.state.datasetCalls, 0, code);
      assert.equal(view.input().props.disabled, false);
      assert.match(text(view.render()), /知识库未开通，仍可直接对话/);
      if (code === 'knowledge_not_authorized') assert.match(text(view.render()), /知识库未授权/);
      assert.doesNotMatch(text(view.render()), /正在加载知识库列表/);
      await view.replay();
      assert.ok(find(view.render(), node => node.props?.content === '私有历史正文'));
      assert.equal(view.button('查看全文').props.disabled, true);
      await view.send(); await view.complete();
      assert.ok(find(view.render(), node => node.props?.content === '已完成的回答'));
      assert.equal(view.state.datasetCalls, 0, 'sending and replaying do not load unavailable knowledge');
      view.hooks.dispose();
    }

    view = await setup(false, { turns: [privateTurn] });
    assert.equal(view.input().props.disabled, true);
    assert.match(text(view.render()), /助手暂不可用，请稍后重试/);
    assert.equal(view.button('新建会话').props.disabled, false, 'history and documents remain available');
    view.state.datasets = [{ id: 'library-1', name: '授权知识库', document_count: 1 }];
    view.button('重新检查服务').props.onClick(); await settle();
    const datasetButton = find(view.render(), node => node.type === 'button' && text(node).includes('授权知识库'));
    datasetButton.props.onClick();
    assert.ok(find(view.render(), node => node.type?.name === 'KnowledgeDocumentBrowser'));
    await view.replay();
    assert.ok(find(view.render(), node => node.props?.content === '私有历史正文'));
    assert.equal(view.button('查看全文').props.disabled, false);
    assert.equal(view.input().props.disabled, true, 'history replay cannot enable an unavailable model');
    view.hooks.dispose();

    view = await setup(true, { turns: [privateTurn] });
    await view.replay();
    view.button('查看全文').props.onClick();
    assert.ok(find(view.render(), node => node.type?.name === 'KnowledgeDocumentPreview'));
    view.state.status.knowledge = { available: false, code: 'disabled', help: '知识库已暂停' };
    await view.send();
    assert.equal(find(view.render(), node => node.type?.name === 'KnowledgeDocumentPreview'), undefined, 'capability downgrade closes the old document preview');
    await view.complete();
    assert.equal(view.input().props.disabled, false);
    view.hooks.dispose();

    view = await setup(true, { turns: [privateTurn] });
    await view.replay();
    view.state.datasetError = { code: 'unconfigured', detail: '知识库服务未配置' };
    view.button('重新检查服务').props.onClick(); await settle();
    assert.equal(view.input().props.disabled, false, 'a knowledge service 403 cannot revoke chat access');
    await view.replay();
    assert.ok(find(view.render(), node => node.props?.content === '私有历史正文'));
    view.state.datasetError = { code: 'scope_revoked', detail: '授权已撤销' };
    view.button('重新加载列表').props.onClick(); await settle();
    assert.equal(view.input().props.disabled, true);
    assert.equal(find(view.render(), node => node.props?.content === '私有历史正文'), undefined);
    assert.doesNotMatch(text(view.render()), /私有引用|私有文档|测试会话v0/);
    assert.match(text(view.render()), /旧回答、引用和文档已清除/);
    view.hooks.dispose();
  } finally { Object.assign(globalThis, original); delete globalThis.assistantTestHooks; await server.close(); }
});
