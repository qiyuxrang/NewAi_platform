// Fresh checkout: node scripts/check-enterprise-bridge.mjs --prepare
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
if (process.argv.includes('--prepare')) {
  const checkDir = path.join(root, '.runtime/bridge-check')
  fs.mkdirSync(checkDir, { recursive: true })
  fs.copyFileSync(path.join(root, 'openclaw/bridge-package.json'), path.join(checkDir, 'package.json'))
  fs.copyFileSync(path.join(root, 'openclaw/bridge-enterprise-package-lock.json'), path.join(checkDir, 'package-lock.json'))
  const install = process.platform === 'win32'
    ? spawnSync(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', 'npm ci --no-audit --no-fund'], { cwd: checkDir, stdio: 'inherit' })
    : spawnSync('npm', ['ci', '--no-audit', '--no-fund'], { cwd: checkDir, stdio: 'inherit' })
  assert.equal(install.status, 0, 'Bridge dependency installation failed')
  fs.writeFileSync(path.join(checkDir, 'tsconfig.json'), JSON.stringify({
    compilerOptions: { target: 'ES2022', module: 'NodeNext', moduleResolution: 'NodeNext', strict: true, esModuleInterop: true, skipLibCheck: true,
      typeRoots: ['./node_modules/@types'], baseUrl: '.', paths: { express: ['./node_modules/@types/express'], ws: ['./node_modules/@types/ws'] },
      rootDir: '../../openclaw/bridge', outDir: './dist' },
    include: ['model-catalog.ts', 'config.ts', 'routes/sessions.ts', 'routes/agents.ts', 'routes/events.ts', 'routes/subagents.ts'].map(file => '../../openclaw/bridge/' + file),
  }, null, 2))
  const compile = spawnSync(process.execPath, [path.join(checkDir, 'node_modules/typescript/bin/tsc'), '-p', path.join(checkDir, 'tsconfig.json')], { cwd: root, stdio: 'inherit' })
  assert.equal(compile.status, 0, 'Bridge typecheck failed')
}
const require = createRequire(path.join(root, '.runtime/bridge-check/package.json'))
const express = require('express')
const { loadConfig, writeOpenclawConfig } = await import('../.runtime/bridge-check/dist/config.js')
const { configuredModelCatalog } = await import('../.runtime/bridge-check/dist/model-catalog.js')
const { sessionsRoutes } = await import('../.runtime/bridge-check/dist/routes/sessions.js')
const { agentsRoutes } = await import('../.runtime/bridge-check/dist/routes/agents.js')
const { eventsRoutes } = await import('../.runtime/bridge-check/dist/routes/events.js')
const { subagentsRoutes } = await import('../.runtime/bridge-check/dist/routes/subagents.js')

const home = path.join(root, '.runtime/bridge-check/test-home')
process.env.OPENCLAW_STATE_DIR = home
process.env.NANOBOT_PROXY__TOKEN = 'test-only-container-token'
process.env.NANOBOT_AGENTS__DEFAULTS__MODEL = 'configured-one'
process.env.NANOBOT_PROXY__MODELS = 'configured-one,configured-two'
process.env.NANOBOT_MCP__URL = 'http://host.docker.internal:8080/api/enterprise/mcp'
fs.mkdirSync(home, { recursive: true })
fs.writeFileSync(path.join(home, 'openclaw.json'), JSON.stringify({ mcp: { servers: { preserved: { command: 'test-server' } } } }))
writeOpenclawConfig(loadConfig())
const config = JSON.parse(fs.readFileSync(path.join(home, 'openclaw.json'), 'utf8'))
assert.ok(config.mcp.servers.preserved)
assert.equal(config.mcp.servers['department-knowledge'].headers.Authorization, 'Bearer test-only-container-token')
const catalog = configuredModelCatalog(config)
assert.deepEqual(catalog.models.map(item => item.id), ['platform-proxy/configured-one', 'platform-proxy/configured-two'])
assert.ok(!JSON.stringify(catalog).includes('test-only-container-token'))
assert.equal(configuredModelCatalog({ agents: { defaults: { model: { primary: 'provider/model' } } } }).configuredModel, 'provider/model')

const calls = [], listeners = new Set()
const parent = 'agent:main:control-test', childKey = 'agent:product:subagent:control-test'
let childStatus = 'running', childOwner = parent, killMode = 'success', killCalls = 0
const client = {
  async request(method, params) {
    calls.push({ method, params })
    if (method === 'sessions.list') return { sessions: [{ key: childKey, spawnedBy: childOwner, status: childStatus }] }
    return method === 'chat.send' ? { runId: 'test-run', status: 'started' } : { sessions: [] }
  },
  onEvent(listener) { listeners.add(listener) },
  offEvent(listener) { listeners.delete(listener) },
}
const gatewayApp = express()
gatewayApp.post('/sessions/:key/kill', (req, res) => {
  killCalls++
  assert.equal(req.params.key, childKey)
  assert.equal(req.headers['x-openclaw-requester-session-key'], parent)
  if (killMode === 'failure') return res.status(503).json({ ok: false })
  if (killMode === 'invalid') return res.json({ ok: true, killed: 'true' })
  if (killMode === 'done') return res.json({ ok: true, killed: false })
  if (killMode === 'success') childStatus = 'killed'
  if (killMode === 'owner-changed') childOwner = 'agent:main:other-parent'
  res.json({ ok: true, killed: true })
})
const gatewayServer = gatewayApp.listen(0, '127.0.0.1')
await new Promise(resolve => gatewayServer.once('listening', resolve))
const app = express()
app.use(express.json())
app.use('/api', sessionsRoutes(client), agentsRoutes(client), eventsRoutes(client), subagentsRoutes(client, { gatewayPort: gatewayServer.address().port }))
const server = app.listen(0, '127.0.0.1')
await new Promise(resolve => server.once('listening', resolve))
const base = `http://127.0.0.1:${server.address().port}`
let streamController
try {
  const modelResponse = await fetch(base + '/api/models/catalog')
  assert.equal(modelResponse.status, 200)
  assert.deepEqual(await modelResponse.json(), catalog)
  const send = model => fetch(base + '/api/sessions/agent:main:test/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'test', model }) })
  assert.equal((await send('unconfigured/model')).status, 400)
  assert.equal(calls.length, 0)
  assert.equal((await send('platform-proxy/configured-two')).status, 200)
  assert.deepEqual(calls.map(call => call.method), ['sessions.patch', 'chat.send'])
  assert.deepEqual(calls[0].params, { key: 'agent:main:test', model: 'platform-proxy/configured-two' })
  calls.length = 0
  assert.equal((await send('')).status, 200)
  assert.equal(calls[0].params.model, null)

  streamController = new AbortController()
  const stream = await fetch(base + '/api/events/stream', { signal: streamController.signal })
  const reader = stream.body.getReader(), decoder = new TextDecoder()
  let text = decoder.decode((await reader.read()).value)
  const emitted = [
    { event: 'chat', payload: { sessionKey: 'parent', state: 'delta', message: { content: [{ type: 'text', text: 'A' }] } } },
    { event: 'chat', payload: { sessionKey: 'child', state: 'delta', message: { content: [{ type: 'text', text: 'B' }] } } },
    { event: 'chat', payload: { sessionKey: 'parent', state: 'delta', message: { content: [{ type: 'text', text: 'AC' }] } } },
    { event: 'sessions.changed', payload: { sessionKey: 'child', reason: 'created' } },
    { event: 'chat', payload: { sessionKey: 'parent', state: 'final' } },
  ]
  emitted.forEach(event => listeners.forEach(listener => listener(event)))
  const deadline = setTimeout(() => streamController.abort(), 3000)
  try {
    while ((text.match(/^data:/gm) || []).length < emitted.length) text += decoder.decode((await reader.read()).value)
  } finally { clearTimeout(deadline) }
  const received = text.split('\n').filter(line => line.startsWith('data: ')).map(line => JSON.parse(line.slice(6)))
  assert.deepEqual(received, emitted)
  streamController.abort()
  calls.length = 0
  const control = (action, owner = parent) => fetch(base + '/api/subagents/' + encodeURIComponent(childKey) + '/control', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent: owner, action, ...(action === 'kill' ? {} : { message: 'test follow-up' }) }),
  })
  for (const action of ['kill', 'steer', 'send']) assert.equal((await control(action, 'agent:main:other-parent')).status, 403)
  assert.equal(killCalls, 0)
  assert.ok(calls.every(call => call.method === 'sessions.list'))
  for (const action of ['steer', 'send']) {
    const response = await control(action)
    assert.equal(response.status, 202)
    assert.deepEqual(await response.json(), { submitted: true, runId: 'test-run' })
    assert.equal(calls.at(-1).params.message, `/subagents ${action} ${childKey} test follow-up`)
  }
  calls.length = 0
  const killed = await control('kill')
  assert.equal(killed.status, 200)
  assert.deepEqual(await killed.json(), { submitted: true, killed: true, verified: true, status: 'killed', runId: null })
  assert.ok(calls.every(call => call.method === 'sessions.list'), 'Kill must bypass parent chat.send even while it is busy')
  for (const [mode, expected] of [['done', 409], ['failure', 503], ['invalid', 502], ['unverified', 409], ['owner-changed', 409]]) {
    killMode = mode
    childStatus = mode === 'done' ? 'done' : 'running'
    childOwner = parent
    const response = await control('kill')
    assert.equal(response.status, expected, mode)
    assert.notEqual((await response.json()).verified, true, mode)
  }
  console.log('Bridge configured-model, MCP, SSE and child-control checks passed; native kill receipt and killed status both required, foreign parents rejected.')
} finally {
  streamController?.abort()
  server.closeAllConnections()
  await new Promise(resolve => server.close(resolve))
  gatewayServer.closeAllConnections()
  await new Promise(resolve => gatewayServer.close(resolve))
}
