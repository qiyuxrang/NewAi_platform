import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { runInNewContext } from 'node:vm'
import test from 'node:test'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const bridge = new URL('../../openclaw/bridge/', import.meta.url)

function loadSource(relative, mocks = {}) {
  const source = readFileSync(new URL(relative, bridge), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    reportDiagnostics: true,
  })
  assert.equal(compiled.diagnostics?.length ?? 0, 0)
  const module = { exports: {} }
  runInNewContext(compiled.outputText, {
    module, exports: module.exports,
    require: id => Object.hasOwn(mocks, id) ? mocks[id] : require(id),
  }, { filename: fileURLToPath(new URL(relative, bridge)) })
  return module.exports
}

const utils = loadSource('utils.ts')
const parent = 'agent:main:parent'
const childKey = 'agent:main:subagent:child'
const child = { key: childKey, spawnedBy: parent, status: 'running', label: '检查证据', startedAt: 1234, model: 'actual-model' }

test('native target resolver accepts the exact full child key', () => {
  const { resolveSubagentTargetFromRuns } = loadSource('../src/auto-reply/reply/subagents-utils.ts', {
    '../../shared/string-coerce.js': {
      normalizeOptionalString: value => typeof value === 'string' ? value.trim() || undefined : undefined,
      normalizeLowercaseStringOrEmpty: value => typeof value === 'string' ? value.toLowerCase() : '',
    },
    '../../tasks/task-status.js': { sanitizeTaskStatusText: value => value },
    '../../utils.js': { truncateUtf16Safe: (value, length) => value.slice(0, length) },
  })
  const entry = { childSessionKey: childKey, startedAt: 1234, runId: 'real-run' }
  const resolution = resolveSubagentTargetFromRuns({
    runs: [entry], token: childKey, recentWindowMinutes: 60, label: () => 'task',
    errors: { missingTarget: 'missing', unknownSession: value => `unknown ${value}` },
  })
  assert.equal(resolution.entry, entry)
})

function setup(sessions = [child], failMethod) {
  const handlers = new Map()
  const calls = []
  const router = {
    get(path, handler) { handlers.set(`GET ${path}`, handler) },
    post(path, handler) { handlers.set(`POST ${path}`, handler) },
  }
  const { subagentsRoutes } = loadSource('routes/subagents.ts', {
    express: { Router: () => router }, '../utils.js': utils,
  })
  subagentsRoutes({ async request(method, params) {
    calls.push({ method, params })
    if (method === failMethod) throw new Error('native unavailable')
    return method === 'sessions.list' ? { sessions } : { runId: 'parent-command-run' }
  } })
  async function invoke(route, request) {
    return new Promise((resolve, reject) => {
      let status = 200
      const response = {
        status(value) { status = value; return response },
        json(body) { resolve({ status, body }) },
      }
      const handler = handlers.get(route)
      assert.ok(handler, `Registered route ${route}`)
      handler(request, response, reject)
    })
  }
  return { calls, handlers, invoke }
}

test('lists native children and retains real status/model/timestamps only', async () => {
  const { invoke, calls, handlers } = setup([child, { ...child, key: 'agent:main:alien', spawnedBy: 'other' }])
  const result = await invoke('GET /subagents', { query: { parent } })
  assert.equal(result.status, 200)
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{ method: 'sessions.list', params: { spawnedBy: parent, includeLastMessage: true } }])
  assert.equal(result.body.children.length, 1)
  assert.equal(result.body.children[0].status, 'running')
  assert.equal(result.body.children[0].model, 'actual-model')
  assert.equal(result.body.children[0].startedAt, 1234)
  assert.equal(result.body.children[0].endedAt, null)
  assert.ok(![...handlers.keys()].some(path => path.includes('/sessions/')))
})

test('empty native list stays empty and missing state stays null', async () => {
  const empty = setup([])
  assert.equal((await empty.invoke('GET /subagents', { query: { parent } })).body.children.length, 0)
  const noStatus = setup([{ key: childKey, spawnedBy: parent }])
  assert.equal((await noStatus.invoke('GET /subagents', { query: { parent } })).body.children[0].status, null)
})

test('403 prevents controls for missing or differently owned children', async () => {
  for (const sessions of [[], [{ ...child, spawnedBy: 'agent:main:another-parent' }]]) {
    const { invoke, calls } = setup(sessions)
    const result = await invoke('POST /subagents/:childKey/control', { params: { childKey }, body: { parent, action: 'kill' } })
    assert.equal(result.status, 403)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].method, 'sessions.list')
  }
})

test('steer and send use native full-key commands and acknowledge only dispatch', async () => {
  for (const action of ['steer', 'send']) {
    const { invoke, calls } = setup([{ ...child, status: action === 'send' ? 'done' : 'running' }])
    const result = await invoke('POST /subagents/:childKey/control', { params: { childKey }, body: { parent, action, message: '  后续核验  ' } })
    assert.equal(result.status, 202)
    assert.equal(result.body.submitted, true)
    assert.equal(result.body.runId, 'parent-command-run')
    const command = calls[1]
    assert.equal(command.method, 'chat.send')
    assert.equal(command.params.sessionKey, parent)
    assert.equal(command.params.message, `/subagents ${action} ${childKey} 后续核验`)
    assert.equal(command.params.deliver, false)
    assert.match(command.params.idempotencyKey, /^[a-f0-9-]{36}$/)
    assert.equal(Object.hasOwn(result.body, 'completed'), false)
  }
})

test('invalid actions, targets and empty instructions never call native controls', async () => {
  for (const request of [
    { params: { childKey }, body: { parent, action: 'spawn', message: 'test' } },
    { params: { childKey: `${childKey}\nall` }, body: { parent, action: 'kill' } },
    { params: { childKey: 'all' }, body: { parent, action: 'kill' } },
    { params: { childKey }, body: { parent, action: 'steer', message: '  ' } },
  ]) {
    const { invoke, calls } = setup()
    assert.equal((await invoke('POST /subagents/:childKey/control', request)).status, 400)
    assert.equal(calls.length, 0)
  }
})

test('native list and control failures propagate instead of fabricated success', async () => {
  const listing = setup([], 'sessions.list')
  await assert.rejects(listing.invoke('GET /subagents', { query: { parent } }), /native unavailable/)
  const control = setup([child], 'chat.send')
  await assert.rejects(control.invoke('POST /subagents/:childKey/control', { params: { childKey }, body: { parent, action: 'steer', message: '核验' } }), /native unavailable/)
})
