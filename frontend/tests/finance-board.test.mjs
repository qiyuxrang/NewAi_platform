import assert from 'node:assert/strict'
import { after, afterEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
  server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } })
const model = await server.ssrLoadModule('/src/business/finance/finance-board.ts')
const { FinanceBoardContent } = await server.ssrLoadModule('/src/business/finance/FinanceBoard.tsx')
const { ApiError } = await server.ssrLoadModule('/src/business/api.ts')
const original = { fetch: globalThis.fetch, localStorage: globalThis.localStorage }
globalThis.localStorage = { getItem: () => 'isolated-finance-token' }
afterEach(() => { globalThis.fetch = original.fetch })
after(() => { Object.assign(globalThis, original); return server.close() })

const standard = () => ({ department: 'finance', available: true, title: '财务部看板', snapshot_id: 'test-snapshot', statuses: [], currency: 'CNY',
  fields: { project_id: '项目编号', project_name: '项目名称', contract_amount: '合同金额', received_amount: '已收金额', due_date: '应收日期' },
  metrics: [{ key: 'contract', label: '合同金额', value: '100.00', unit: '元' }, { key: 'received', label: '已收金额', value: '20.00', unit: '元' },
    { key: 'receivable', label: '待收余额', value: '80.00', unit: '元' }, { key: 'overdue', label: '逾期待收', value: null, unit: '元' }],
  distribution: [{ label: '未结清', count: 1 }], records: [{ project_id: 'P1', project_name: '一期项目', contract_amount: '100.00', received_amount: '20.00', due_date: '' }],
  total: 30, filtered_count: 1, scope: '部门最新已发布台账；未发布草稿不会进入总经理看板。',
  source: { name: '已发布标准财务', as_of: '2026-10-14', imported_at: '2026-10-14T00:00:00Z', kind: 'department_published', revision: 3, state: 'published' } })
const source = () => ({ ...standard(), metrics: [{ key: 'contract', label: '合同金额', value: '100.00', unit: '元' },
  { key: 'opening_receivable', label: '年初应收总额', value: null, unit: '元' }, { key: 'received', label: '已实现回款（1-7月）', value: null, unit: '元' },
  { key: 'receivable', label: '实际应收结余', value: '70.00', unit: '元' }, { key: 'planned', label: '计划回款（8-12月）', value: '0.00', unit: '元' },
  { key: 'overdue', label: '逾期待收', value: null, unit: '元' }],
  fields: { project_name: '项目名称', client_name: '业主单位', contract_amount: '合同金额', opening_receivable: '年初应收', receivable_balance: '应收结余', owner: '回款负责人', current_status: '目前状态' },
  records: [{ project_id: 'P1', project_name: '一期项目', contract_amount: '100.00', opening_receivable: '', receivable_balance: '70.00', billing_entity: '主体一' }],
  distribution: [{ label: '主体一', count: 1 }], source: { ...standard().source, name: '手工录入', as_of: '2027-01-01' } })
const html = data => renderToStaticMarkup(React.createElement(FinanceBoardContent, { data, query: '一期' }))

test('one authenticated GET carries encoded search and preserves server filtered metrics, distribution and full records', async () => {
  const payload = standard(), controller = new AbortController()
  let calls = 0
  globalThis.fetch = async (path, options) => {
    calls++
    const url = new URL(path, 'https://isolated.invalid')
    assert.equal(url.pathname, '/api/enterprise/business/business/boards/finance/')
    assert.equal(url.searchParams.get('q'), '一期 & 主体')
    assert.equal(url.searchParams.has('page'), false)
    assert.equal(options.method, undefined)
    assert.equal(options.body, undefined)
    assert.equal(options.signal, controller.signal)
    assert.equal(options.headers.get('Authorization'), 'Bearer isolated-finance-token')
    assert.equal(options.credentials, 'omit')
    return Response.json(payload)
  }
  assert.deepEqual(await model.loadFinanceBoard('  一期 & 主体  ', controller.signal), payload)
  assert.equal(calls, 1)
  const markup = html(payload)
  assert.match(markup, /当前 1 条 \/ 台账共 30 条/)
  assert.match(markup, /一期项目/)
  assert.match(markup, /已收 \/ 待收构成/)
  assert.match(markup, /20\.0%/)
  assert.match(markup, /截止日期：2026-10-14/)
})

test('unknown amounts stay unknown; missing, blank, negative and unavailable values never create a donut', () => {
  for (const value of [null, undefined, '', '-1', 'NaN']) {
    const data = standard()
    data.metrics[1].value = value
    assert.equal(model.collectionComposition(data), null)
    assert.doesNotMatch(html(data), /role="img" aria-label="已收/)
  }
  const empty = { ...standard(), available: false, source: null, records: [], filtered_count: 0, total: 0,
    metrics: standard().metrics.map(metric => ({ ...metric, value: null })), distribution: [{ label: '未结清', count: 0 }] }
  assert.equal(model.financeValue(null), '—')
  assert.equal(model.financeValue(''), '—')
  assert.equal(model.financeValue('0.00'), '0.00')
  assert.match(html(empty), /暂无已发布财务台账/)
  assert.doesNotMatch(html(empty), /role="img" aria-label="已收/)
  const zero = standard()
  zero.metrics[1].value = '0.00'; zero.metrics[2].value = '0.00'
  assert.equal(model.collectionComposition(zero), null)
})

test('source mode keeps five genuine metrics, forbids money charts despite yuan label and never infers year from cutoff', () => {
  const data = source()
  assert.equal(model.financeMetrics(data).length, 5)
  assert.equal(model.collectionComposition(data), null)
  const markup = html(data)
  assert.match(markup, /原表金额单位未核实/)
  assert.match(markup, /月份所属来源年度未确认/)
  assert.match(markup, /已实现回款（1-7月）/)
  assert.match(markup, /主体一/)
  assert.match(markup, /截止日期：2027-01-01/)
  assert.doesNotMatch(markup, /role="img" aria-label="已收|已收占比|逾期待收|2027年|2026年/)
  assert.equal((markup.match(/class="finance-metric"/g) || []).length, 5)
  const filteredEmpty = { ...data, filtered_count: 0, records: [], distribution: [{ label: '未标注', count: 0 }] }
  assert.equal(model.isSourceFinance(filteredEmpty), true, 'filter cannot switch ledger mode based on visible rows')
  assert.doesNotMatch(html(filteredEmpty), /role="img" aria-label="已收/)
})

test('401 and 403 remain real errors and never load board content or write grants', async () => {
  for (const [status, detail] of [[401, '业务账号未绑定。'], [403, '无总经理看板权限。']]) {
    globalThis.fetch = async () => Response.json({ detail }, { status })
    await assert.rejects(model.loadFinanceBoard('', new AbortController().signal), error => {
      assert.equal(error.status, status)
      assert.match(model.financeError(error), new RegExp(detail))
      if (status === 401) assert.match(model.financeError(error), /重新登录或绑定/)
      return true
    })
  }
  assert.equal(model.financeError(new ApiError(403, '无总经理看板权限。')), '无总经理看板权限。')
})

test('filter changes discard stale responses and permission revocation unmounts previously visible data', async () => {
  const isolated = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' },
    plugins: [{ name: 'finance-test-hooks', resolveId: id => id === '/@finance-test-hooks' ? '\0finance-test-hooks' : null,
      load: id => id === '\0finance-test-hooks' ? 'export const useState = (...args) => globalThis.financeTestHooks.useState(...args); export const useEffect = (...args) => globalThis.financeTestHooks.useEffect(...args); export const useSearchParams = () => [globalThis.financeTestHooks.params, () => {}];' : null,
      transform: (code, id) => id.replaceAll('\\', '/').endsWith('/finance/FinanceBoard.tsx') ? code.replace(/from ["']react["']/g, "from '/@finance-test-hooks'").replace(/from ["']react-router-dom["']/g, "from '/@finance-test-hooks'") : null }] })
  const requests = [], slots = []
  let index = 0
  const hooks = {
    params: new URLSearchParams('q=一期'),
    useState(initial) { const slot = index++; slots[slot] ??= { value: initial }; return [slots[slot].value, value => { slots[slot].value = typeof value === 'function' ? value(slots[slot].value) : value }] },
    useEffect(effect, deps) { const slot = index++, old = slots[slot]; if (!old || deps.some((value, i) => value !== old.deps[i])) { old?.cleanup?.(); slots[slot] = { deps, cleanup: effect() } } },
  }
  const find = (node, predicate) => {
    if (!node || typeof node !== 'object') return undefined
    if (predicate(node)) return node
    for (const child of [node.props?.children].flat(Infinity)) { const result = find(child, predicate); if (result) return result }
  }
  const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)) }
  globalThis.financeTestHooks = hooks
  globalThis.fetch = (path, options) => new Promise(resolve => requests.push({ path, options, resolve }))
  try {
    const { default: Board, FinanceBoardContent: Content } = await isolated.ssrLoadModule('/src/business/finance/FinanceBoard.tsx')
    const render = () => { index = 0; return Board() }
    render()
    hooks.params = new URLSearchParams('q=二期')
    let tree = render()
    assert.equal(requests.length, 2)
    assert.equal(requests[0].options.signal.aborted, true)
    assert.equal(find(tree, node => node.type === Content), undefined)
    requests[0].resolve(Response.json(standard())); await settle()
    tree = render()
    assert.equal(find(tree, node => node.type === Content), undefined, 'aborted first filter cannot reappear')
    const second = { ...standard(), records: [{ ...standard().records[0], project_name: '二期项目' }], metrics: standard().metrics.map(item => ({ ...item, value: '44.00' })) }
    requests[1].resolve(Response.json(second)); await settle()
    tree = render()
    assert.deepEqual(find(tree, node => node.type === Content).props.data, second)
    assert.equal(find(tree, node => node.type === Content).props.query, '二期')
    find(tree, node => node.props?.['aria-label'] === '刷新财务看板').props.onClick()
    tree = render()
    assert.equal(find(tree, node => node.type === Content), undefined)
    requests[2].resolve(Response.json({ detail: '无总经理看板权限。' }, { status: 403 })); await settle()
    tree = render()
    assert.equal(find(tree, node => node.type === Content), undefined)
    assert.equal(find(tree, node => node.props?.role === 'alert').props.children, '无总经理看板权限。')
  } finally { for (const slot of slots) slot?.cleanup?.(); delete globalThis.financeTestHooks; await isolated.close() }
})
