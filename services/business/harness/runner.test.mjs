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
const truncated = "[System: The AI model's output was truncated or didn't complete successfully. Please continue generating the remaining content from where it was interrupted.]";

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

test('an omitted tool placeholder is held back and corrected through real Harness tools', async () => {
  let models = 0, tools = 0;
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') {
      models++;
      if (models === 1) {
        for (const delta of ['  [Tool ', 'call ', 'omitted]\n'])
          send({ type: 'model_event', id: event.id, event: { delta } });
        send({ type: 'model_event', id: event.id, event: { done: true, content: '  [Tool call omitted]\n' } });
      } else if (models === 2) {
        assert.ok(event.messages.some(message => message.content === '以前的问题'));
        assert.ok(event.messages.some(message => message.content === start.question));
        assert.match(event.messages.at(-1).content, /真实工具调用/);
        send({ type: 'model_event', id: event.id, event: { done: true,
          tool_calls: [{ id: 'recovered', type: 'function', function: {
            name: 'search_knowledge', arguments: '{"query":"公司"}' } }] } });
      } else {
        assert.equal(event.messages.at(-1).role, 'tool');
        assert.match(event.messages.at(-1).content, /授权资料/);
        send({ type: 'model_event', id: event.id, event: { done: true, content: '根据授权资料回答。' } });
      }
    }
    if (event.type === 'tool') {
      tools++;
      send({ type: 'tool_result', id: event.id, result: { evidence: '授权资料' } });
    }
  });
  assert.equal(code, 0);
  assert.equal(models, 3);
  assert.equal(tools, 1);
  assert.equal(events.filter(event => event.type === 'delta').map(event => event.text).join(''), '根据授权资料回答。');
  assert.equal(events.at(-1).final_answer, '根据授权资料回答。');
});

test('a repeated omitted tool placeholder fails after one correction', async () => {
  let models = 0;
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') {
      models++;
      send({ type: 'model_event', id: event.id, event: { done: true, content: '[Tool call omitted]' } });
    }
  });
  assert.equal(code, 1);
  assert.equal(models, 2);
  assert.ok(!events.some(event => ['delta', 'done', 'tool'].includes(event.type)));
  assert.deepEqual(events.at(-1), { type: 'error', code: 'invalid_response' });
});

test('a fragmented truncation notice is corrected once and never streamed as an answer', async () => {
  for (const repeated of [false, true]) {
    let models = 0;
    const { events, code } = await exercise(start, (event, send) => {
      if (event.type !== 'model') return;
      models++;
      if (models === 1) {
        for (const delta of ['  [Sys', truncated.slice(4, 75), truncated.slice(75), '\n'])
          send({ type: 'model_event', id: event.id, event: { delta } });
        send({ type: 'model_event', id: event.id, event: { done: true, content: `  ${truncated}\n` } });
      } else send({ type: 'model_event', id: event.id, event: { done: true,
        content: repeated ? '[Tool call omitted]' : '上一轮回答未完成，请提供要检索的公开关键词。' } });
    });
    assert.equal(models, 2);
    assert.equal(code, repeated ? 1 : 0);
    assert.ok(!events.some(event => ['delta', 'done'].includes(event.type) && JSON.stringify(event).includes('truncated')));
    if (repeated) {
      assert.ok(!events.some(event => ['delta', 'done'].includes(event.type)));
      assert.equal(events.at(-1).code, 'invalid_response');
    } else assert.equal(events.at(-1).final_answer, '上一轮回答未完成，请提供要检索的公开关键词。');
  }
});

test('placeholder correction never exceeds the model call cap', async () => {
  let models = 0;
  const { events, code } = await exercise({ ...start, max_model_calls: 1 }, (event, send) => {
    if (event.type === 'model') {
      models++;
      send({ type: 'model_event', id: event.id, event: { done: true, content: '[Tool call omitted]' } });
    }
  });
  assert.equal(code, 1);
  assert.equal(models, 1);
  assert.ok(!events.some(event => ['delta', 'done'].includes(event.type)));
  assert.deepEqual(events.at(-1), { type: 'error', code: 'invalid_response' });
});

test('holding a placeholder prefix preserves ordinary Markdown links', async () => {
  const text = '[Tool documentation](https://example.test/tools)';
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model') {
      for (const delta of ['[', 'Tool ', 'documentation](https://example.test/tools)'])
        send({ type: 'model_event', id: event.id, event: { delta } });
      send({ type: 'model_event', id: event.id, event: { done: true, content: text } });
    }
  });
  assert.equal(code, 0);
  assert.equal(events.filter(event => event.type === 'delta').map(event => event.text).join(''), text);
  assert.equal(events.at(-1).final_answer, text);
});

test('a final literal bracket is released when it is not a complete placeholder', async () => {
  const { events, code } = await exercise(start, (event, send) => {
    if (event.type === 'model')
      send({ type: 'model_event', id: event.id, event: { done: true, content: '[' } });
  });
  assert.equal(code, 0);
  assert.equal(events.filter(event => event.type === 'delta').map(event => event.text).join(''), '[');
  assert.equal(events.at(-1).final_answer, '[');
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
