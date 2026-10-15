import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { test } from 'node:test';

const knowledge = { type: 'function', function: {
  name: 'search_knowledge', description: 'Search authorized business knowledge.',
  parameters: { type: 'object', properties: {
    query: { type: 'string', minLength: 1, maxLength: 2000 },
    limit: { type: 'integer', minimum: 1, maximum: 20 },
    tags: { type: 'array', minItems: 1, maxItems: 3, items: { type: 'string', maxLength: 100 } },
  }, required: ['query'], additionalProperties: false },
} };
const start = { type: 'start', question: '查公司资料', history: [{ question: '以前的问题', answer: '以前的回答' }],
  tools: [knowledge], system_prompt: 'Use only authorized business evidence.', max_model_calls: 8 };

async function exercise(input, respond) {
  const child = spawn(process.execPath, ['runner.mjs'], { cwd: import.meta.dirname, stdio: ['pipe', 'pipe', 'pipe'] });
  const events = [], errors = [];
  let failure;
  const send = message => child.stdin.write(`${JSON.stringify(message)}\n`);
  child.stderr.on('data', chunk => errors.push(chunk.toString()));
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => {
    try { const event = JSON.parse(line); events.push(event); respond?.(event, send); }
    catch (error) { failure = error; child.kill(); }
  });
  const timer = setTimeout(() => { failure = new Error('bridge timed out'); child.kill(); }, 15000);
  const closed = new Promise(resolve => child.once('close', code => resolve(code)));
  send(input);
  const code = await closed;
  clearTimeout(timer);
  if (failure) throw failure;
  assert.equal(errors.join(''), '', 'the isolated kernel must not write logs');
  return { events, code };
}

test('real Harness calls only the authorized tool, resumes, and streams its answer', async () => {
  let models = 0, tools = 0, finalModelId;
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') {
      models++;
      assert.deepEqual(event.tools.map(tool => tool.function.name), ['search_knowledge']);
      const parameters = event.tools[0].function.parameters;
      assert.deepEqual(parameters.properties.query, { type: 'string' });
      assert.deepEqual(parameters.properties.limit, { type: 'integer' });
      assert.deepEqual(parameters.properties.tags, { type: 'array', items: { type: 'string' } });
      assert.equal(event.messages[0].role, 'system');
      assert.equal(event.messages[1].content, '以前的问题');
      if (models === 1) send({ type: 'model_event', id: event.id, event: { done: true, content: '正在检索。',
        tool_calls: [{ id: 'call1', type: 'function', function: { name: 'search_knowledge', arguments: '{"query":"公司"}' } }] } });
      else {
        assert.equal(event.messages.at(-1).role, 'tool');
        assert.match(event.messages.at(-1).content, /授权资料/);
        finalModelId = event.id;
        send({ type: 'model_event', id: event.id, event: { delta: '根据' } });
      }
    }
    // Completion is withheld until a live delta reaches the host.
    if (event.type === 'delta' && event.text === '根据') {
      send({ type: 'model_event', id: finalModelId, event: { delta: '授权资料。' } });
      send({ type: 'model_event', id: finalModelId, event: { done: true, content: '根据授权资料。', prompt_tokens: 8, completion_tokens: 5 } });
    }
    if (event.type === 'tool') {
      tools++;
      assert.equal(event.name, 'search_knowledge');
      assert.deepEqual(event.arguments, { query: '公司' });
      send({ type: 'tool_result', id: event.id, result: { evidence: '授权资料' } });
    }
  });
  assert.equal(code, 0);
  assert.equal(models, 2);
  assert.equal(tools, 1);
  assert.deepEqual(events[0], { type: 'ready', runtime: 'deepseek_harness', version: '0.2.1-alpha.3' });
  assert.equal(events.filter(event => event.type === 'delta').map(event => event.text).join(''), '正在检索。\n根据授权资料。');
  assert.equal(events.at(-1).answer, '正在检索。\n根据授权资料。');
  assert.equal(events.at(-1).final_answer, '根据授权资料。');
});

test('cancel aborts an actual pending Harness model call', async () => {
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') send({ type: 'cancel' });
  });
  assert.equal(code, 1);
  assert.deepEqual(events.at(-1), { type: 'error', code: 'cancelled' });
  assert.ok(!events.some(event => event.type === 'done'));
});

test('unregistered model tools never reach the host callback', async () => {
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') send({ type: 'model_event', id: event.id, event: { done: true, content: '',
      tool_calls: [{ id: 'bad', type: 'function', function: { name: 'run_shell', arguments: '{}' } }] } });
  });
  assert.equal(code, 1);
  assert.ok(!events.some(event => event.type === 'tool'));
  assert.deepEqual(events.at(-1), { type: 'error', code: 'unauthorized_tool' });
});

test('model call cap stops a tool loop without dispatching another model request', async () => {
  let models = 0;
  const { events, code } = await exercise({ ...start, max_model_calls: 1 }, (event, send) => {
    if (event.type === 'model') {
      models++;
      send({ type: 'model_event', id: event.id, event: { done: true, content: '',
        tool_calls: [{ id: 'loop', type: 'function', function: { name: 'search_knowledge', arguments: '{"query":"公司"}' } }] } });
    }
    if (event.type === 'tool') send({ type: 'tool_result', id: event.id, result: {} });
  });
  assert.equal(code, 1);
  assert.equal(models, 1);
  assert.deepEqual(events.at(-1), { type: 'error', code: 'model_limit' });
});

test('malformed startup fails closed with a sanitized error', async () => {
  const { events, code } = await exercise({ ...start, tools: [{ ...knowledge, function: { ...knowledge.function, name: 'run_code' } }] });
  assert.equal(code, 1);
  assert.deepEqual(events, [{ type: 'error', code: 'invalid_protocol' }]);
});

test('a tool batch crossing the budget skips host calls and preserves unexecuted feedback', async () => {
  let models = 0, tools = 0;
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') {
      models++;
      if (models <= 2) send({ type: 'model_event', id: event.id, event: { done: true, content: '',
        tool_calls: Array.from({ length: models === 1 ? 11 : 2 }, (_, index) => ({
          id: `batch-${models}-${index}`, type: 'function',
          function: { name: 'search_knowledge', arguments: '{"query":"公司"}' },
        })) } });
      else {
        assert.match(event.messages.at(-1).content, /tool_budget_exhausted/);
        assert.match(event.messages.at(-1).content, /未执行/);
        send({ type: 'model_event', id: event.id, event: { done: true, content: '基于现有资料回答，剩余工具未执行。' } });
      }
    }
    if (event.type === 'tool') {
      tools++;
      send({ type: 'tool_result', id: event.id, result: { evidence: '授权资料' } });
    }
  });
  assert.equal(code, 0);
  assert.equal(models, 3);
  assert.equal(tools, 12);
  assert.equal(events.at(-1).answer, '基于现有资料回答，剩余工具未执行。');
});

test('normalization does not silently accept unsupported structural schema keywords', async () => {
  const tool = { ...knowledge, function: { ...knowledge.function,
    parameters: { ...knowledge.function.parameters, anyOf: [{ type: 'object' }, { type: 'string' }] } } };
  const { events, code } = await exercise({ ...start, tools: [tool] });
  assert.equal(code, 1);
  assert.deepEqual(events, [{ type: 'error', code: 'runtime_failed' }]);
});
