import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'

function compile(name, require, globals = {}) {
  const exports = {}
  const source = readFileSync(new URL(`../src/business/product/${name}`, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  vm.runInNewContext(code, { exports, require, ...globals })
  return exports
}
const data = compile('BaichuanAssistant-data.ts', () => ({}))
const plain = value => JSON.parse(JSON.stringify(value))
const nodes = tree => !tree || typeof tree !== 'object' ? [] : [tree, ...[tree.props?.children].flat(Infinity).flatMap(nodes)]
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve() }

test('private browser recovery keys distinguish origin, platform owner and portal binding', () => {
  const keys = [data.assistantStorageKey('https://one.example', 'a', 1), data.assistantStorageKey('https://two.example', 'a', 1),
    data.assistantStorageKey('https://one.example', 'b', 1), data.assistantStorageKey('https://one.example', 'a', 2)]
  assert.equal(new Set(keys).size, 4)
})
test('only current condition snapshots can render and result revision determines latest result', () => {
  const conversation = { condition_revision: 3, snapshots: [{ id: 'stale', condition_revision: 2, result_revision: 90 },
    { id: 'current-old', condition_revision: 3, result_revision: 1 }, { id: 'current', condition_revision: 3, result_revision: 2 }] }
  assert.equal(data.latestCurrentSnapshot(conversation).id, 'current')
  assert.equal(data.latestCurrentSnapshot({ condition_revision: 4, snapshots: conversation.snapshots }), undefined)
})
test('unknown, failed and conflict verdicts never become satisfied and cancel requests keep polling', () => {
  for (const verdict of ['unknown', 'conflict', 'failed', 'nonsense', undefined]) assert.notEqual(data.verdictLabel(verdict), '满足')
  assert.equal(data.verdictLabel('failed'), '不满足')
  assert.equal(data.jobActive('cancel_requested'), true)
  for (const state of ['completed', 'failed', 'awaiting_input']) assert.equal(data.jobActive(state), false)
  assert.equal(data.countSummary({ total: 0, confirmed: 2, candidate: 1, failed: -2, invented: 99, verified: '100%' }), '总计 0 · 确认匹配 2 · 待核实候选 1')
  assert.equal(data.countSummary({ researched_companies: 3, research_sources: 5, research_suggestions: 2, research_cache_hits: 1 }), '已尝试研究企业 3 · 可读来源 5 · 资料建议 2 · 复用来源 1')
})
test('file selection rejects unsupported, empty and oversize inputs before upload', () => {
  assert.equal(data.validateAttachment({ name: '资格.PDF', size: 100 }), '')
  assert.equal(data.validateAttachment({ name: '资格.docx', size: 20 * 1024 * 1024 }), '')
  for (const file of [{ name: 'run.exe', size: 100 }, { name: 'empty.pdf', size: 0 }, { name: 'large.pdf', size: 20 * 1024 * 1024 + 1 }]) assert.ok(data.validateAttachment(file))
  assert.equal(data.capabilityAvailable({ available: false }), false)
  assert.equal(data.capabilityAvailable({ available: true }), true)
})
test('criterion labels keep hard, preference, holder and exact-grade distinctions', () => {
  const tree = { must: { all: [{ field: 'certificate', category: 'itss', op: 'grade_exact', value: '2', holder: 'bidder' }] },
    should: [{ field: 'certificate', category: 'cmmi', op: 'grade_at_least', value: '3', holder: 'manufacturer' }] }
  assert.match(data.conditionLabel(tree, 'must.0'), /硬性要求.*ITSS.*等级精确为 2.*投标企业/)
  assert.match(data.conditionLabel(tree, 'should.0'), /优先项.*CMMI.*制造商/)
})

function harness(api, stream) {
  const slots = []; let cursor = 0; let effects = []; let user = { id: 'platform-owner', portal_user_id: 7 }
  const storage = new Map(), listeners = new Map(), timers = new Map(); let timerId = 0
  const same = (a, b) => a?.length === b?.length && a.every((value, index) => Object.is(value, b[index]))
  const react = {
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial }; return [slots[index].value, next => { slots[index].value = typeof next === 'function' ? next(slots[index].value) : next }] },
    useRef(initial) { const index = cursor++; return slots[index] ||= { current: initial } },
    useEffect(fn, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) { slots[index]?.cleanup?.(); slots[index] = { deps }; effects.push(() => { slots[index].cleanup = fn() }) } },
  }
  const Component = compile('BaichuanAssistant.tsx', name => name === 'react/jsx-runtime' ? jsx : name === 'react' ? react :
    name === './BaichuanAssistant-data' ? data : name === './Baichuan-data' ? { safeWebsite: value => /^https:\/\/[^/@\\]+(?:\/|$)/.test(value) ? value : null } : name === '../api' ? { apiRequest: api, apiEventStream: stream, isApiError: () => false } :
    name.endsWith('enterprise-context') ? { useEnterprise: () => ({ user }) } : name === 'lucide-react' ? Object.fromEntries(['Download', 'Paperclip', 'RotateCcw', 'Send', 'Square', 'X'].map(name => [name, () => null])) : { default: 'mascot.webp' },
    { window: { location: { origin: 'http://test.local' }, localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) } },
      document: { addEventListener: (event, fn) => listeners.set(event, fn), removeEventListener: event => listeners.delete(event) },
      Error, TypeError, AbortController, crypto: { randomUUID: () => 'fixed-idempotency-key' }, FormData,
      setTimeout: fn => { timers.set(++timerId, fn); return timerId }, clearTimeout: id => timers.delete(id) }).default
  let tree
  return { storage, timers, listeners, setUser(value) { user = value }, wrapper: allowed => Component({ allowed, onCompany() {} }),
    render() { cursor = 0; effects = []; const wrapped = Component({ allowed: true, onCompany() {} }); tree = wrapped.type(wrapped.props); effects.forEach(fn => fn()); return tree },
    find(label) { return nodes(tree).find(node => node.props?.['aria-label'] === label) },
  }
}
test('assistant stays collapsed and creates no conversation until a deliberate send; IME Enter never sends', async () => {
  const calls = []
  const h = harness(async (url, options) => { calls.push({ url, options });
    if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, search: false, parser: true } }
    if (url.endsWith('conversations/')) return { id: 'conversation', condition_revision: 0 }
    if (url.endsWith('messages/')) return { job: { id: 'job', status: 'queued' } }
    return { id: 'conversation', condition_revision: 0, jobs: [] }
  })
  assert.equal(h.wrapper(false), null)
  h.render(); await flush(); let tree = h.render()
  assert.equal(nodes(tree).some(node => node.type === 'aside'), false)
  assert.equal(calls.length, 1)
  h.find('打开百川 AI 助手').props.onClick(); h.render()
  let input = h.find('需求或补充说明')
  input.props.onChange({ target: { value: '广东 ITSS 二级' } }); h.render(); input = h.find('需求或补充说明')
  input.props.onCompositionStart()
  let prevented = false
  input.props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: true }, preventDefault() { prevented = true } })
  await flush(); assert.equal(calls.length, 1); assert.equal(prevented, false)
  input.props.onCompositionEnd()
  input.props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() { prevented = true } })
  await flush(); h.render(); await flush()
  const sends = calls.filter(call => call.url.endsWith('messages/'))
  assert.equal(sends.length, 1)
  assert.deepEqual(plain(JSON.parse(sends[0].options.body)), { text: '广东 ITSS 二级', attachment_ids: [], parent_revision: 0, client_request_id: 'fixed-idempotency-key' })
  assert.equal(h.storage.size, 1)
  assert.equal(h.find('需求或补充说明').props.value, '')
  h.listeners.get('keydown')({ key: 'Escape', isComposing: false, preventDefault() {} }); tree = h.render()
  assert.equal(nodes(tree).some(node => node.type === 'aside'), false)
  assert.equal(calls.some(call => call.url.endsWith('/cancel/')), false)
})

test('network failures show a readable recovery message and preserve the draft without resubmission', async () => {
  for (const message of ['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.', 'Network request failed']) {
    const calls = []
    const h = harness(async (url, options) => {
      calls.push({ url, options })
      if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, parser: true } }
      if (url.endsWith('conversations/')) throw new TypeError(message)
      throw new Error('Unexpected API call')
    })
    h.render(); await flush(); h.render()
    h.find('打开百川 AI 助手').props.onClick(); h.render()
    h.find('需求或补充说明').props.onChange({ target: { value: '电子与智能化二级' } }); h.render()
    h.find('需求或补充说明').props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: {}, preventDefault() {} })
    await flush(); const html = renderToStaticMarkup(h.render())
    assert.match(html, /连接暂时不可用，当前输入已保留，请检查网络后重试。/)
    assert.equal(h.find('需求或补充说明').props.value, '电子与智能化二级')
    assert.equal(calls.filter(call => call.url.endsWith('conversations/')).length, 1)
    assert.equal(calls.some(call => /\/(messages|retry|cancel)\/$/.test(call.url)), false)
    assert.equal(h.storage.size, 0)
  }
})

test('company-only result paging keeps safe company links and omits audit messages', async () => {
  const calls = []
  const h = harness(async url => {
    calls.push(url)
    if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, search: true, parser: true } }
    if (url.includes('/conversations/')) return { id: 'conversation', condition_revision: 1, messages: [], jobs: [], snapshots: [{ id: 'snapshot', condition_revision: 1, result_revision: 1 }] }
    return { id: 'snapshot', condition_revision: 1, page: 1, page_size: 50, total: 51, conditions: { must: { field: 'company.city', value: '广州' } },
      evidence: { safe: { title: '<img src=x onerror=alert(1)>', url: 'https://example.com/source', verified_on: '2026-10-17' },
        unsafe: { title: 'Unsafe source', url: 'javascript:alert(1)' } },
      results: [{ company_id: 'company', company: { name: '<script>private</script>', phone: '029-00000000', website: 'https://example.com/source', city: '西安' }, status: 'candidate', conditions: [{ condition_id: 'must', verdict: 'unknown', reason: '待核实', evidence_ids: ['safe', 'unsafe'] }] }] }
  })
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick(); const tree = h.render()
  const html = renderToStaticMarkup(tree)
  assert.match(html, /href="https:\/\/example.com\/source"/)
  assert.match(html, /rel="noopener noreferrer"/)
  assert.match(html, /联系电话：029-00000000/)
  assert.match(html, /西安/)
  assert.match(html, /候选/)
  assert.match(html, /&lt;script&gt;private/)
  assert.doesNotMatch(html, /核验日期|2026-10-17|查看来源|Unsafe source|待核实|联网补查/)
  assert.doesNotMatch(html, /href="javascript:|<script>private/)
  const next = nodes(tree).find(node => node.type === 'button' && node.props.children === '下一页结果')
  assert.equal(next.props.disabled, false)
  next.props.onClick(); h.render(); await flush()
  assert.ok(calls.some(url => url.includes('page=2&page_size=50')))
})

test('structured company reply removes stage and duplicate summaries but preserves clarification and candidate semantics', async () => {
  const h = harness(async url => {
    if (url.endsWith('config/')) return { enabled: true, environment_label: '内部环境调试信息', capabilities: { model: true, parser: true, search: false } }
    if (url.includes('/conversations/')) return { id: 'conversation', condition_revision: 1,
      messages: [{ id: 'input', role: 'user', content: '查询企业' },
        { id: 'summary', role: 'assistant', content: '已检索当前授权库：已确认 1 家，待核实 1 家，排除 0 家。', metadata: { snapshot_id: 'snapshot' } },
        { id: 'clarify', role: 'assistant', content: '请补充检索要求：投标日期', metadata: { awaiting_input: true } }],
      jobs: [{ id: 'done', kind: 'query', status: 'completed', stage: 'internal_verification', counts: { verified: 500 } }],
      snapshots: [{ id: 'snapshot', condition_revision: 1, result_revision: 1 }] }
    return { id: 'snapshot', condition_revision: 1, total: 2, conditions: {
      must: { all: [{ field: 'qualification', category: 'electronic', op: 'grade_exact', value: '2', holder: 'bidder' },
        { field: 'qualification', category: 'itss', op: 'grade_exact', value: '2', holder: 'bidder' }] } },
      results: [{ company_id: 'known', company: { name: '合成企业甲', phone: '029-11111111', city: '西安' }, status: 'confirmed',
        conditions: [{ condition_id: 'must.0', verdict: 'satisfied', reason: '用户确认旧库，未执行新的联网核验', evidence_ids: ['evidence'] }] },
        { company_id: 'unknown', company: { name: '合成企业乙', website: 'javascript:alert(1)' }, status: 'candidate',
          conditions: [{ condition_id: 'must.1', verdict: 'unknown', reason: '缺少已核实证书正文依据', evidence_ids: ['private'] }] }] }
  })
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick()
  const html = renderToStaticMarkup(h.render())
  for (const text of ['合成企业甲', '合成企业乙', '联系电话：029-11111111', '西安', '资质', '电子与智能化 · 二级', '候选', '请补充检索要求：投标日期']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /已检索当前授权库|联网核验|证书正文依据|查看来源|internal_verification|内部环境调试信息|已完成|已核实|ITSS|href="javascript:/)
})

test('actual stream progress is received silently without re-submission; required questions still appear', async () => {
  const streams = [], calls = []
  const h = harness(async url => { calls.push(url); return url.endsWith('config/')
    ? { enabled: true, capabilities: { model: true, parser: true, answer_stream: true } }
    : { id: 'conversation', condition_revision: 1, messages: [], jobs: [{ id: 'job', kind: 'query', status: 'running' }] } },
  (path, body, signal, delta) => new Promise(resolve => streams.push({ delta, resolve, signal })))
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick(); h.render()
  const progress = '已接收本轮需求，任务在后台继续。\n正在理解需求，区分硬性要求、优先项和证书主体。\n检索条件已校验，正在按当前库资料逐项匹配。\n'
  for (const chunk of [progress.slice(0, 12), progress.slice(12)]) { streams[0].delta(chunk); h.render() }
  assert.doesNotMatch(renderToStaticMarkup(h.render()), /已接收本轮需求|检索条件已校验|区分硬性要求/)
  streams[0].delta('请选择投标企业或制造商。')
  assert.match(renderToStaticMarkup(h.render()), /请选择投标企业或制造商/)
  assert.equal(calls.some(url => /\/(messages|retry|cancel)\/$/.test(url)), false)
})

test('a lost acknowledgement retains the exact idempotent request after server revision advances', async () => {
  let serverRevision = 0
  const sends = []
  const h = harness(async (url, options) => {
    if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, search: false, parser: true } }
    if (url.endsWith('conversations/')) return { id: 'conversation', condition_revision: 0 }
    if (url.endsWith('messages/')) {
      sends.push(JSON.parse(options.body)); serverRevision = 1
      if (sends.length === 1) throw new Error('Acknowledgement lost after commit')
      return { job: { id: 'job', status: 'queued' } }
    }
    return { id: 'conversation', condition_revision: serverRevision, messages: [], jobs: [] }
  })
  h.render(); await flush(); h.render(); h.find('打开百川 AI 助手').props.onClick(); h.render()
  h.find('需求或补充说明').props.onChange({ target: { value: '广东 ITSS 二级' } }); h.render()
  const submit = () => h.find('需求或补充说明').props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() {} })
  submit(); await flush()
  for (let i = 0; i < 3; i++) { h.render(); await flush() }
  assert.equal(h.find('需求或补充说明').props.value, '广东 ITSS 二级')
  submit(); await flush(); h.render()
  assert.equal(sends.length, 2)
  assert.deepEqual(plain(sends[1]), plain(sends[0]))
  assert.equal(sends[1].parent_revision, 0)
  assert.equal(h.find('需求或补充说明').props.value, '')
})

test('fixed snapshot list keeps its ID and candidate verdict through new conversation results and paging', async () => {
  let revision = 1
  const calls = []
  const h = harness(async url => {
    calls.push(url)
    if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, search: false, parser: true } }
    if (url.includes('/conversations/')) return { id: 'conversation', condition_revision: revision, messages: [],
      jobs: [{ id: 'pending', status: revision === 1 ? 'running' : 'completed' }],
      snapshots: [{ id: `snapshot-${revision}`, condition_revision: revision, result_revision: 1 }] }
    const id = url.includes('snapshot-1') ? 'snapshot-1' : 'snapshot-2'
    return { id, condition_revision: id === 'snapshot-1' ? 1 : 2, page: url.includes('page=2') ? 2 : 1,
      page_size: 50, total: 51, results: [{ company_id: 'candidate', company: { name: `${id} 待核实企业` }, status: 'candidate' }] }
  })
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick(); let tree = h.render()
  nodes(tree).find(node => node.type === 'button' && node.props.children === '在列表查看').props.onClick()
  for (let i = 0; i < 3; i++) { tree = h.render(); await flush() }
  assert.ok(h.find('固定快照企业列表'))
  assert.equal(h.find('百川 AI 助手'), undefined)
  revision = 2
  const timer = [...h.timers.values()][0]
  timer(); await flush()
  for (let i = 0; i < 3; i++) { tree = h.render(); await flush() }
  let html = renderToStaticMarkup(tree)
  assert.doesNotMatch(html, /条件版本|快照：/)
  assert.match(html, /snapshot-1 待核实企业/)
  assert.match(html, /候选/)
  assert.doesNotMatch(html, /snapshot-2 待核实企业|确认匹配/)
  nodes(tree).find(node => node.type === 'button' && node.props.children === '下一页快照').props.onClick()
  h.render(); await flush(); tree = h.render()
  assert.ok(calls.some(url => url.includes('results/snapshot-1/?page=2')))
  h.find('关闭企业结果列表').props.onClick()
  h.render(); assert.equal(h.find('固定快照企业列表'), undefined)
  assert.equal(h.storage.get(data.assistantStorageKey('http://test.local', 'platform-owner', 7)), 'conversation')
  h.find('打开百川 AI 助手').props.onClick(); tree = h.render()
  assert.match(renderToStaticMarkup(tree), /snapshot-2 待核实企业/)
})


test('answer stream observes once, updates the existing bubble and reconciles the persisted reply', async () => {
  const calls = [], streams = []
  let value = { id: 'conversation', condition_revision: 1, messages: [], jobs: [{ id: 'stream-job', kind: 'query', status: 'running' }] }
  const h = harness(async url => { calls.push(url); return url.endsWith('config/') ? { enabled: true, capabilities: { answer_stream: true } } : value },
    (path, body, signal, delta) => new Promise(resolve => streams.push({ path, body, signal, delta, resolve })))
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  assert.equal(streams.length, 1)
  assert.match(streams[0].path, /jobs\/stream-job\/stream\/$/)
  assert.deepEqual(plain(streams[0].body), {})
  h.find('打开百川 AI 助手').props.onClick(); h.render()
  streams[0].delta('正在理解需求。\n'); h.render()
  streams[0].delta('<script>不执行</script>'); let tree = h.render()
  assert.match(renderToStaticMarkup(tree), /正在理解需求/)
  assert.match(renderToStaticMarkup(tree), /&lt;script&gt;/)
  h.find('收起助手，后台任务继续').props.onClick(); h.render()
  assert.equal(streams[0].signal.aborted, false)
  streams[0].delta('逐项匹配。'); h.render()
  h.find('打开百川 AI 助手').props.onClick(); tree = h.render()
  assert.match(renderToStaticMarkup(tree), /逐项匹配/)
  value = { ...value, jobs: [{ id: 'stream-job', kind: 'query', status: 'completed' }],
    messages: [{ id: 'persisted', role: 'assistant', content: '最终已校验结果', metadata: { job_id: 'stream-job' } }] }
  streams[0].resolve({ job: value.jobs[0] }); await flush()
  for (let i = 0; i < 4; i++) { tree = h.render(); await flush() }
  const html = renderToStaticMarkup(tree)
  assert.equal((html.match(/最终已校验结果/g) || []).length, 1)
  assert.doesNotMatch(html, /正在理解需求/)
  assert.equal(calls.some(url => url.endsWith('/messages/') || url.endsWith('/retry/') || url.endsWith('/cancel/')), false)
})

test('late stream deltas are ignored after a newer condition revision', async () => {
  const streams = []
  let value = { id: 'conversation', condition_revision: 1, messages: [], jobs: [{ id: 'first', kind: 'query', status: 'running' }] }
  const h = harness(async url => url.endsWith('config/') ? { enabled: true, capabilities: { answer_stream: true } } : value,
    (path, body, signal, delta) => new Promise(resolve => streams.push({ path, signal, delta, resolve })))
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick(); h.render()
  streams[0].delta('旧轮次'); h.render()
  value = { ...value, condition_revision: 2, jobs: [{ id: 'second', kind: 'query', status: 'running' }] }
  const timer = [...h.timers.values()][0]; timer(); await flush()
  for (let i = 0; i < 3; i++) { h.render(); await flush() }
  assert.equal(streams[0].signal.aborted, true)
  streams[0].delta('迟到不能覆盖'); streams[1].delta('新轮次内容')
  const html = renderToStaticMarkup(h.render())
  assert.match(html, /新轮次内容/); assert.doesNotMatch(html, /迟到不能覆盖|旧轮次/)
})

test('stream transport failure falls back to polling without resubmission', async () => {
  const calls = []
  const h = harness(async url => { calls.push(url); return url.endsWith('config/') ? { enabled: true, capabilities: { answer_stream: true } } :
    { id: 'conversation', condition_revision: 1, messages: [], jobs: [{ id: 'job', kind: 'query', status: 'running' }] } },
    async () => { throw new Error('Disconnected') })
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 6; i++) { h.render(); await flush() }
  assert.ok(h.timers.size > 0)
  assert.equal(calls.some(url => url.endsWith('/messages/') || url.endsWith('/retry/')), false)
})

test('a new current result scrolls inside the existing panel while stale results never steal focus', async () => {
  let revision = 1, ready = false
  const h = harness(async url => {
    if (url.endsWith('config/')) return { enabled: true, capabilities: { model: true, parser: true } }
    if (url.includes('/conversations/')) return { id: 'conversation', condition_revision: revision, messages: [],
      jobs: [{ id: 'running', kind: 'query', status: 'running' }],
      snapshots: ready ? [{ id: 'current', condition_revision: 1, result_revision: 1 }] : [] }
    return { id: 'current', condition_revision: 1, results: [{ company_id: 'one', company: { name: '合成企业' }, status: 'confirmed' }] }
  })
  h.storage.set(data.assistantStorageKey('http://test.local', 'platform-owner', 7), 'conversation')
  for (let i = 0; i < 5; i++) { h.render(); await flush() }
  h.find('打开百川 AI 助手').props.onClick(); h.render()
  const content = { scrollTop: 0, getBoundingClientRect: () => ({ top: 100 }),
    querySelector: () => ({ getBoundingClientRect: () => ({ top: 240 }) }) }
  h.find('百川 AI 助手').props.ref.current = { querySelector: () => content }
  ready = true; [...h.timers.values()][0](); await flush()
  for (let i = 0; i < 4; i++) { h.render(); await flush() }
  assert.equal(content.scrollTop, 132)
  content.scrollTop = 999; revision = 2
  ;[...h.timers.values()].at(-1)(); await flush()
  for (let i = 0; i < 4; i++) { h.render(); await flush() }
  assert.equal(content.scrollTop, 999)
})
