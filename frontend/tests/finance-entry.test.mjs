import assert from 'node:assert/strict'
import { after, afterEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
  server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } })
const model = await server.ssrLoadModule('/src/business/finance/finance-entry.ts')
const { FinanceRecordForm } = await server.ssrLoadModule('/src/business/finance/FinanceEntry.tsx')
const original = { fetch: globalThis.fetch, localStorage: globalThis.localStorage }
globalThis.localStorage = { getItem: () => 'isolated-finance-entry-token' }
afterEach(() => { globalThis.fetch = original.fetch })
after(() => { Object.assign(globalThis, original); return server.close() })
const recordId = '00000000-0000-4000-8000-000000000001', checksum = 'a'.repeat(64)
const row = () => ({ project_id: 'FN/1', project_name: '一期财务', contract_amount: '100.00', received_amount: '20.00', due_date: '', owner: '负责人', current_status: '待核对' })
const sourceRow = () => ({ ...row(), received_amount: '', opening_receivable: '', receivable_balance: '80.00', source_sheet: '应收总账', source_row: '8', received_01: '', received_07: '0.00', planned_08: '', planned_12: '10.00', affiliate: '原挂靠单位', billing_entity: '原主体' })
const ledger = (record = row()) => ({ department: 'finance', state: 'draft', revision: 3, as_of: '2027-01-01', source_name: '手工录入', records: [record],
  record_meta: { [recordId]: { project_id: record.project_id, record_author_id: 17, draft_actor_id: 17, draft_revision: 3, draft_checksum: checksum, deleted: false } },
  fields: { project_name: '项目名称', contract_amount: '合同金额' }, permissions: { can_edit: true, can_submit: false, can_publish: false } })
const data = (record = row()) => ({ ledger: ledger(record), published: null, publishedRevision: 0 })
const editor = (record = row(), projectId = record.project_id) => ({ baseline: { ...record }, draft: { ...record }, projectId, revision: 3 })
const prefix = '/api/enterprise/business/business/ledgers/'
function mockRead(value, versions = [], published = null) {
  const calls = []
  globalThis.fetch = async (path, options) => {
    calls.push([path, options])
    assert.equal(options.body, undefined); assert.equal(options.method, undefined)
    assert.equal(options.headers.get('Authorization'), 'Bearer isolated-finance-entry-token')
    assert.equal(options.credentials, 'omit')
    if (path === prefix + 'permissions/') return Response.json({ departments: [{ department: 'finance' }] })
    if (path === prefix + 'finance/') return Response.json(value.ledger)
    if (path === prefix + 'finance/versions/') return Response.json({ department: 'finance', versions })
    if (published && path === prefix + `finance/versions/${published.id}/`) return Response.json(published)
    throw new Error(`Unexpected read ${path}`)
  }
  return calls
}
const formHtml = (value, edit, actor = 17) => renderToStaticMarkup(React.createElement(FinanceRecordForm, { data: value, editor: edit, actor, busy: false, conflict: false, onChange() {}, onSave() {}, onClose() {} }))

test('permission first, ledger then latest published revision snapshot; no GM board or writes', async () => {
  const value = data(), published = { ...value.ledger, id: recordId, state: 'published', revision: 2 }
  const calls = mockRead(value, [{ id: recordId, state: 'published', revision: 2 }], published)
  const result = await model.loadFinanceEntry(new AbortController().signal)
  assert.equal(result.publishedRevision, 2); assert.deepEqual(result.published.records, published.records)
  assert.deepEqual(calls.map(([path]) => path), [prefix + 'permissions/', prefix + 'finance/', prefix + 'finance/versions/', prefix + `finance/versions/${recordId}/`])
})

test('401/403 and missing finance grant stop with real errors; no subsequent finance request', async () => {
  for (const status of [401, 403]) {
    let count = 0
    globalThis.fetch = async () => { count++; return Response.json({ detail: '真实权限提示' }, { status }) }
    await assert.rejects(model.loadFinanceEntry(), error => error.status === status && model.financeEntryError(error).includes('真实权限提示'))
    assert.equal(count, 1)
  }
  let count = 0
  globalThis.fetch = async () => { count++; return Response.json({ departments: [{ department: 'presales' }] }) }
  await assert.rejects(model.loadFinanceEntry(), error => error.status === 403)
  assert.equal(count, 1)
})

test('unknown values do not become zero, standard received amount stays required and source recognition is per record', () => {
  for (const empty of ['', null]) {
    const standard = { ...row(), received_amount: empty, opening_receivable: '', receivable_balance: '', source_sheet: '' }
    assert.equal(model.sourceFinanceRecord(standard), false)
    assert.match(model.financeValidation(standard), /已收金额/)
  }
  const realZero = { ...row(), received_amount: '0.00' }
  assert.equal(model.financeValidation(realZero), '')
  assert.equal(model.financeValidation(sourceRow()), '')
  assert.equal(model.entryCell(null), '—'); assert.equal(model.entryCell(''), '—'); assert.equal(model.entryCell('0.00'), '0.00')
  const fresh = model.newFinanceRecord()
  assert.equal(model.sourceFinanceRecord(fresh), false)
  assert.equal(Object.hasOwn(fresh, 'source_sheet'), false); assert.equal(Object.hasOwn(fresh, 'source_row'), false)
  const markup = formHtml(data(), editor())
  assert.match(markup, /已收金额（元）/); assert.match(markup, /id="finance-received_amount"[^>]*required/)
})

test('pure books prevent actively mixing new modes; existing mixed records retain their individual contracts', async () => {
  const standard = editor(row(), null), source = editor(sourceRow(), null)
  assert.match(model.financeEditorValidation(standard, ledger(sourceRow())), /不能在本台账主动混入标准记录/)
  assert.match(model.financeEditorValidation(source, ledger()), /不能主动新增源表/)
  let calls = 0
  globalThis.fetch = async () => { calls++; throw new Error('Must not write invalid new mode') }
  await assert.rejects(model.saveFinanceRecord(standard, ledger(sourceRow())), /不能在本台账主动混入/)
  assert.equal(calls, 0)
  const mixed = ledger(); mixed.records.push({ ...sourceRow(), project_id: 'source-two' })
  assert.equal(model.financeBookMode(mixed), 'mixed')
  assert.equal(model.financeEditorValidation(editor(row()), mixed), '')
  assert.equal(model.financeEditorValidation(editor(sourceRow()), mixed), '')
})

test('source form keeps seven main fields, monthly actual/plan and unknown year/unit without cutoff inference', () => {
  const value = data(sourceRow()), html = formHtml(value, editor(sourceRow()))
  for (const key of ['project_name', 'client_name', 'contract_amount', 'opening_receivable', 'receivable_balance', 'owner', 'current_status']) assert.match(html, new RegExp(`id="finance-${key}"`))
  assert.match(html, /原表单位未核实/); assert.match(html, /月份所属来源年度未核实/)
  assert.match(html, /7月实际回款/); assert.match(html, /8月计划回款/); assert.match(html, /12月计划回款/)
  assert.doesNotMatch(html, /2027年|2026年/)
  assert.match(html, /原挂靠单位|原主体|应收总账/)
  const freshHtml = formHtml(value, editor(model.newFinanceRecord(), null))
  assert.match(freshHtml, /id="finance-opening_receivable"/)
  assert.match(freshHtml, /id="finance-received_amount"[^>]*required/)
})

test('editing retains baseline record mode and refuses either direction of conversion without writing', async () => {
  const source = editor({ ...sourceRow(), source_sheet: '', received_amount: '20.00' })
  source.draft.receivable_balance = ''
  assert.match(model.financeEditorValidation(source, ledger(source.baseline)), /已有记录.*不能在编辑中转换/)
  assert.match(formHtml(data(source.baseline), source), /原表单位未核实/)
  const standard = editor({ ...row(), opening_receivable: '', receivable_balance: '' })
  standard.draft.receivable_balance = '80.00'
  assert.match(model.financeEditorValidation(standard, ledger(standard.baseline)), /已有记录.*不能在编辑中转换/)
  assert.match(formHtml(data(standard.baseline), standard), /id="finance-received_amount"[^>]*required/)
  let calls = 0
  globalThis.fetch = async () => { calls++; throw new Error('Mode conversion must not write') }
  await assert.rejects(model.saveFinanceRecord(source, ledger(source.baseline)), /不能在编辑中转换/)
  await assert.rejects(model.saveFinanceRecord(standard, ledger(standard.baseline)), /不能在编辑中转换/)
  assert.equal(calls, 0)
})

test('verified own authors only: unknown, other, duplicate metadata and changed draft actor block selection', () => {
  const value = data(), record = value.ledger.records[0]
  assert.equal(model.ownsFinanceRecord(value.ledger, record, 17), true)
  assert.deepEqual(model.financeSelection(value, record, 17), { record_id: recordId, source_revision: 3, source_checksum: checksum })
  for (const author of [null, 19, 0, -1, '17']) {
    const changed = structuredClone(value); changed.ledger.record_meta[recordId].record_author_id = author
    assert.equal(model.ownsFinanceRecord(changed.ledger, record, 17), false)
    assert.equal(model.financeSelection(changed, record, 17), null)
    assert.match(formHtml(changed, editor(record)), /readOnly=""/)
  }
  const otherActor = structuredClone(value); otherActor.ledger.record_meta[recordId].draft_actor_id = 19
  assert.equal(model.financeSelection(otherActor, record, 17), null)
  const duplicate = structuredClone(value); duplicate.ledger.record_meta['00000000-0000-4000-8000-000000000002'] = { ...duplicate.ledger.record_meta[recordId] }
  assert.equal(model.recordIdentity(duplicate.ledger, record), null)
  value.publishedRevision = null; assert.equal(model.financeSelection(value, record, 17), null)
})

test('single record update preserves full fields and exact expected_revision; metadata PATCH does not import or overwrite all records', async () => {
  const edit = editor(sourceRow()); edit.draft.current_status = '已核对'
  const calls = []
  globalThis.fetch = async (path, options) => { calls.push([path, options.method, JSON.parse(options.body)]); return Response.json(ledger(edit.draft)) }
  await model.saveFinanceRecord(edit, ledger(sourceRow()))
  await model.saveFinanceMetadata(3, '2026-10-14')
  assert.deepEqual(calls[0], [prefix + 'finance/records/FN%2F1/', 'PUT', { expected_revision: 3, record: edit.draft }])
  for (const key of ['source_sheet', 'source_row', 'planned_12', 'received_01', 'received_07', 'affiliate']) assert.equal(calls[0][2].record[key], sourceRow()[key])
  assert.deepEqual(calls[1], [prefix + 'finance/', 'PATCH', { expected_revision: 3, as_of: '2026-10-14' }])
})

test('own publication uses can_edit despite can_publish false; exact selection and concurrent checksum failures never auto retry', async () => {
  const value = data(), selected = [model.financeSelection(value, row(), 17)], calls = []
  globalThis.fetch = async (path, options) => { calls.push([path, options]); return Response.json(ledger()) }
  await model.publishFinanceRecords(value, selected, 17)
  assert.equal(calls[0][0], prefix + 'finance/publish/'); assert.equal(calls[0][1].method, 'POST')
  assert.deepEqual(JSON.parse(calls[0][1].body), { expected_revision: 3, expected_published_revision: 0, records: selected })
  const stale = [{ ...selected[0], source_checksum: 'b'.repeat(64) }]
  await assert.rejects(model.publishFinanceRecords(value, stale, 17), /归属或版本已变化/)
  assert.equal(calls.length, 1)
  let attempts = 0
  globalThis.fetch = async () => { attempts++; return Response.json({ detail: '真实并发冲突' }, { status: 409 }) }
  await assert.rejects(model.publishFinanceRecords(value, selected, 17), error => error.status === 409)
  assert.equal(attempts, 1)
  value.ledger.permissions.can_edit = false
  await assert.rejects(model.publishFinanceRecords(value, selected, 17), /归属或版本已变化/)
  assert.equal(attempts, 1)
})

test('409 retains draft; manual reconcile keeps local changes and latest untouched fields, refuses lost authors or deleted records', async () => {
  const edit = editor(sourceRow()); edit.draft.current_status = '本次未保存'
  let writes = 0
  globalThis.fetch = async () => { writes++; return Response.json({ detail: '台账已更新' }, { status: 409 }) }
  await assert.rejects(model.saveFinanceRecord(edit, ledger(sourceRow())), error => error.status === 409)
  assert.equal(writes, 1); assert.equal(edit.draft.current_status, '本次未保存'); assert.equal(edit.revision, 3)
  const latest = data(sourceRow()); latest.ledger.revision = 4; latest.ledger.records[0].affiliate = '最新主体信息'
  const reconciled = model.reconcileFinanceEditor(edit, latest, 17)
  assert.equal(reconciled.revision, 4); assert.equal(reconciled.draft.current_status, '本次未保存'); assert.equal(reconciled.draft.affiliate, '最新主体信息')
  latest.ledger.record_meta[recordId].record_author_id = 19
  assert.equal(model.reconcileFinanceEditor(edit, latest, 17), null)
  latest.ledger.records = []
  assert.equal(model.reconcileFinanceEditor(edit, latest, 17), null)
})

test('truncated history does not fake a zero published baseline; racing version read produces 409', async () => {
  const value = data(), histories = Array.from({ length: 200 }, () => ({ id: recordId, revision: 3, state: 'draft' }))
  mockRead(value, histories)
  assert.equal((await model.loadFinanceEntry()).publishedRevision, null)
  mockRead(value, [{ id: recordId, revision: 4, state: 'draft' }])
  await assert.rejects(model.loadFinanceEntry(), error => error.status === 409)
})

async function pageHarness() {
  const oldWindow = globalThis.window, oldHooks = globalThis.financeEntryTestHooks
  const slots = [], listeners = new Map()
  let index = 0
  globalThis.window = { confirm: () => true, location: { href: 'https://isolated.invalid/departments/finance/entry' }, history: { state: { idx: 1 } },
    addEventListener(name, callback) { listeners.set(name, callback) }, removeEventListener(name) { listeners.delete(name) } }
  globalThis.financeEntryTestHooks = {
    useEnterprise: () => ({ user: { portal_user_id: 17 }, loading: false, error: '' }),
    useState(initial) { const slot = index++; if (!slots[slot]) slots[slot] = { value: initial }; return [slots[slot].value, next => { slots[slot].value = typeof next === 'function' ? next(slots[slot].value) : next }] },
    useRef(initial) { const slot = index++; slots[slot] ??= { current: initial }; return slots[slot] },
    useEffect(effect, deps) { const slot = index++, old = slots[slot]; if (!old || deps.some((dep, i) => dep !== old.deps[i])) { old?.cleanup?.(); slots[slot] = { deps, cleanup: effect() } } },
  }
  const isolated = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' },
    plugins: [{ name: 'finance-entry-test-hooks', resolveId: id => id === '/@finance-entry-test-hooks' ? '\0finance-entry-test-hooks' : null,
      load: id => id === '\0finance-entry-test-hooks' ? 'export const useState = (...args) => globalThis.financeEntryTestHooks.useState(...args); export const useEffect = (...args) => globalThis.financeEntryTestHooks.useEffect(...args); export const useRef = (...args) => globalThis.financeEntryTestHooks.useRef(...args); export const useEnterprise = () => globalThis.financeEntryTestHooks.useEnterprise();' : null,
      transform: (code, id) => id.replaceAll('\\', '/').endsWith('/finance/FinanceEntry.tsx') ? code.replace(/from ["']react["']/g, "from '/@finance-entry-test-hooks'").replace(/from ["']\.\.\/\.\.\/components\/enterprise-context["']/g, "from '/@finance-entry-test-hooks'") : null }] })
  const module = await isolated.ssrLoadModule('/src/business/finance/FinanceEntry.tsx')
  const render = () => { index = 0; const root = module.default(); return typeof root.type === 'function' ? root.type(root.props) : root }
  const walk = element => [element, ...React.Children.toArray(element?.props?.children).flatMap(child => typeof child === 'object' ? walk(child) : [])]
  const find = (view, predicate) => walk(view).find(predicate)
  const label = node => React.Children.toArray(node?.props?.children).filter(child => typeof child === 'string').join('')
  return { render, find, label, listeners, settle: () => new Promise(resolve => setTimeout(resolve, 0)), html: view => renderToStaticMarkup(view),
    async close() { for (const slot of slots) slot?.cleanup?.(); await isolated.close(); globalThis.window = oldWindow; globalThis.financeEntryTestHooks = oldHooks } }
}

test('page saves dirty cutoff with exact PATCH revision and does not expose submit or return actions', async () => {
  const value = data(), writes = []
  const reads = (path, options) => {
    if (options.method === 'PATCH') { writes.push(JSON.parse(options.body)); value.ledger = { ...value.ledger, revision: 4, as_of: '2026-10-14' }; return Response.json(value.ledger) }
    if (path === prefix + 'permissions/') return Response.json({ departments: [{ department: 'finance' }] })
    if (path === prefix + 'finance/') return Response.json(value.ledger)
    if (path === prefix + 'finance/versions/') return Response.json({ department: 'finance', versions: [] })
    throw new Error(`Unexpected ${path}`)
  }
  globalThis.fetch = async (path, options) => reads(path, options)
  const app = await pageHarness()
  try {
    app.render(); await app.settle()
    let view = app.render()
    assert.doesNotMatch(app.html(view), /提交台账|退回修改/)
    app.find(view, node => node.props?.id === 'finance-cutoff').props.onChange({ target: { value: '2026-10-14' } })
    view = app.render()
    app.find(view, node => node.type === 'form' && node.props.className === 'ledger-cutoff').props.onSubmit({ preventDefault() {} })
    await app.settle(); view = app.render()
    assert.deepEqual(writes, [{ expected_revision: 3, as_of: '2026-10-14' }])
    assert.match(app.html(view), /截止日期已保存/)
  } finally { await app.close() }
})

test('page preserves unsaved fields through 409 and refresh, manually reconciles, and unmounts ledger on real 403', async () => {
  let current = ledger(sourceRow()), writes = 0, revoked = false
  globalThis.fetch = async (path, options) => {
    if (options.method === 'PUT') { writes++; current = { ...current, revision: 4, records: [{ ...sourceRow(), affiliate: '最新挂靠' }] }; return Response.json({ detail: '真实并发冲突' }, { status: 409 }) }
    if (revoked) return Response.json({ detail: '真实财务撤权' }, { status: 403 })
    if (path === prefix + 'permissions/') return Response.json({ departments: [{ department: 'finance' }] })
    if (path === prefix + 'finance/') return Response.json(current)
    if (path === prefix + 'finance/versions/') return Response.json({ department: 'finance', versions: [] })
    throw new Error(`Unexpected ${path}`)
  }
  const app = await pageHarness()
  try {
    app.render(); await app.settle()
    let view = app.render()
    app.find(view, node => node.type === 'button' && app.label(node) === '编辑').props.onClick()
    view = app.render()
    let form = app.find(view, node => node.type?.name === 'FinanceRecordForm')
    form.props.onChange({ ...form.props.editor.draft, current_status: '本次未保存正文' })
    view = app.render(); form = app.find(view, node => node.type?.name === 'FinanceRecordForm')
    assert.equal(app.listeners.has('beforeunload'), true)
    form.props.onSave(); await app.settle(); view = app.render()
    assert.equal(writes, 1); assert.match(app.html(view), /版本冲突/)
    form = app.find(view, node => node.type?.name === 'FinanceRecordForm')
    assert.equal(form.props.editor.draft.current_status, '本次未保存正文'); assert.equal(form.props.editor.revision, 3)
    app.find(view, node => node.type === 'button' && app.label(node) === '读取最新版本').props.onClick()
    await app.settle(); view = app.render()
    assert.equal(writes, 1)
    app.find(view, node => node.type === 'button' && app.label(node) === '已核对，继续本次修改').props.onClick()
    view = app.render(); form = app.find(view, node => node.type?.name === 'FinanceRecordForm')
    assert.equal(form.props.editor.revision, 4); assert.equal(form.props.editor.draft.current_status, '本次未保存正文'); assert.equal(form.props.editor.draft.affiliate, '最新挂靠')
    revoked = true
    app.find(view, node => node.type === 'button' && app.label(node) === '刷新数据').props.onClick()
    await app.settle(); view = app.render()
    assert.match(app.html(view), /真实财务撤权/); assert.doesNotMatch(app.html(view), /一期财务|本次未保存正文|最新挂靠/)
    assert.equal(writes, 1)
  } finally { await app.close() }
})
