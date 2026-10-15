import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const root = fileURLToPath(new URL('../', import.meta.url))
const server = await createServer({ root, configFile: false, appType: 'custom', server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } })
after(() => server.close())
const state = await server.ssrLoadModule('/src/business/ledgers/ledger-state.ts')
const api = await server.ssrLoadModule('/src/business/ledgers/ledger-api.ts')
const { installLedgerBrowserBoundary, installLedgerNavigationGuard } = await server.ssrLoadModule('/src/business/ledgers/ledger-navigation.ts')
const { LedgerRecordForm } = await server.ssrLoadModule('/src/business/ledgers/LedgerEntry.tsx')

const presales = { project_id: 'PS-1', project_name: '测试售前项目', status: '报价', owner: '', amount: '0',
  follow_up_date: '', project_progress: '', description: '', client_contact: '', project_type: '', maturity: '' }
const engineering = { project_id: 'EG-1', project_name: '测试工程项目', status: '待开工', owner: '', planned_end: '', progress: '' }
const fixture = (department = 'presales', extra = {}) => ({ department, state: 'draft', revision: 3, as_of: '2026-10-01',
  source_name: '手工录入', records: department === 'presales' ? [presales] : [engineering], fields: {},
  statuses: department === 'presales' ? ['线索', '需求沟通', '方案编制', '报价', '商务谈判', '已赢单', '已丢单'] : ['待开工', '实施中', '待验收', '整改中', '已验收', '质保中', '已结束'],
  permissions: { can_edit: true, can_submit: true, can_publish: true }, updated_at: null, updated_by: null, last_return_reason: '', ...extra })

test('records keep their own source mode, real zero and every original field', () => {
  const source = { ...presales, status: '', amount: '', source_sheet: 'Sheet7', source_row: '8', source_amount: '1651.17',
    amount_unit: '万元', source_group: '预算', source_sequence: '1', follow_up_history: '第一行\n第二行',
    notes: '原始备注', annual_plan: '推进计划', expected_signing: '2026年10月' }
  assert.equal(state.isSourceRecord(source, 'presales'), true)
  assert.equal(state.isSourceRecord(presales, 'presales'), false)
  assert.deepEqual(state.missingEntryFields('presales', source), [])
  assert.deepEqual(state.missingEntryFields('presales', { ...presales, amount: '' }), ['amount'])
  assert.deepEqual(state.missingEntryFields('engineering', engineering), ['progress'])
  assert.deepEqual(state.missingEntryFields('engineering', { ...engineering, progress: '0' }), [])
  const snapshot = structuredClone(source)
  const editor = { baseline: source, draft: { ...source, project_progress: '本次修改' }, projectId: source.project_id, revision: 3 }
  const latest = fixture('presales', { revision: 4, records: [{ ...source, notes: '另一员工更新的备注' }] })
  const reconciled = state.reconcileEditor(editor, latest)
  assert.equal(reconciled.revision, 4)
  assert.equal(reconciled.draft.project_progress, '本次修改')
  assert.equal(reconciled.draft.notes, '另一员工更新的备注')
  for (const key of ['source_amount', 'amount_unit', 'follow_up_history', 'expected_signing', 'source_sheet', 'source_row']) assert.equal(reconciled.draft[key], source[key])
  assert.equal(reconciled.draft.amount, '')
  assert.deepEqual(source, snapshot)
  assert.equal(state.reconcileEditor(editor, { ...latest, records: [] }), null)
  assert.equal(state.cellText('0'), '0')
  assert.equal(state.cellText(null), '—')
  assert.equal(state.cellText(''), '—')
  for (const department of ['presales', 'engineering']) {
    const first = state.newLedgerRecord(department), second = state.newLedgerRecord(department)
    assert.notEqual(first.project_id, second.project_id)
    assert.equal(first.project_name, '')
    assert.equal(first.progress ?? first.amount, '')
    assert.equal('source_sheet' in first, false)
  }
})

test('state and returned permissions independently govern every operation', () => {
  assert.deepEqual(state.ledgerActions(fixture()), { edit: true, submit: true, publish: false, return: false })
  assert.deepEqual(state.ledgerActions(fixture('presales', { state: 'submitted' })), { edit: false, submit: false, publish: true, return: true })
  assert.deepEqual(state.ledgerActions(fixture('presales', { state: 'published' })), { edit: true, submit: false, publish: false, return: false })
  assert.deepEqual(state.ledgerActions(fixture('presales', { permissions: { can_edit: false, can_submit: false, can_publish: false } })), { edit: false, submit: false, publish: false, return: false })
  assert.equal(state.ledgerActions(fixture('presales', { records: [] })).submit, false)
  assert.equal(state.ledgerActions(fixture('presales', { as_of: null })).submit, false)
})

test('forms expose real required fields, source precision and unknown engineering progress', () => {
  function render(department, record, extra = {}) {
    const ledger = fixture(department, extra)
    return renderToStaticMarkup(React.createElement(LedgerRecordForm, { department, ledger,
      editor: { baseline: record, draft: record, projectId: record.project_id, revision: 3 }, busy: false, conflict: false,
      onChange: () => assert.fail('static render must not change records'), onSave: () => assert.fail('static render must not write'), onClose: () => {} }))
  }
  const standard = render('presales', presales)
  assert.match(standard, /id="entry-status"[^>]*required=""/)
  assert.match(standard, /id="entry-amount"[^>]*required=""/)
  assert.doesNotMatch(standard, /id="entry-notes"|导入来源（只读）/)
  const source = render('presales', { ...presales, source_sheet: 'Sheet7', status: '', amount: '', expected_signing: '2026年10月', source_amount: '1651.17', amount_unit: '万元' })
  assert.doesNotMatch(source, /id="entry-status"[^>]*required=""|id="entry-amount"[^>]*required=""/)
  assert.match(source, /折算金额（元）/)
  assert.match(source, /id="entry-expected_signing"[^>]*value="2026年10月"/)
  assert.match(source, /导入来源（只读）/)
  assert.match(source, /1651.17/)
  const engineer = render('engineering', engineering)
  assert.match(engineer, /id="entry-progress"[^>]*required=""/)
  assert.match(engineer, /id="entry-progress"[^>]*value=""/)
  assert.match(engineer, /未知进度保持空白/)
  assert.match(engineer, /max="100" step="0.01"/)
  const readOnly = render('engineering', engineering, { state: 'submitted' })
  assert.match(readOnly, /查看项目/)
  assert.match(readOnly, /disabled=""[^>]*>[^<]*<svg[^>]*[\s\S]*?保存草稿/)
})

test('API reads permissions first and uses single-record revisions without bulk replacement or retry', async () => {
  const originalFetch = globalThis.fetch, originalStorage = globalThis.localStorage
  const calls = []
  let grants = [{ department: 'presales', can_edit: true, can_submit: false, can_publish: false }]
  let failWrite = false
  globalThis.localStorage = { getItem: () => 'isolated-test-token' }
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method ?? 'GET', body: options.body && JSON.parse(options.body), headers: options.headers })
    const payload = url.endsWith('/permissions/') ? { departments: grants } : failWrite && options.method ? { detail: '台账已被其他人更新，请刷新后重试。' } : fixture()
    return new Response(JSON.stringify(payload), { status: failWrite && options.method ? 409 : 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const result = await api.getAuthorizedLedger('presales')
    assert.equal(result.revision, 3)
    assert.deepEqual(calls.map(call => call.url), ['/api/enterprise/business/business/ledgers/permissions/', '/api/enterprise/business/business/ledgers/presales/'])
    assert.equal(calls[0].headers.get('Authorization'), 'Bearer isolated-test-token')
    calls.length = 0; grants = []
    await assert.rejects(api.getAuthorizedLedger('engineering'), error => error.status === 403)
    assert.equal(calls.length, 1)
    calls.length = 0
    await api.saveLedgerRecord('presales', 3, presales, null)
    await api.saveLedgerRecord('presales', 4, presales, '来源 编号')
    await api.ledgerMutation('presales', 5, 'submit')
    await api.ledgerMutation('presales', 6, 'publish')
    await api.ledgerMutation('presales', 7, 'return', { reason: '请核对来源' })
    await api.ledgerMutation('presales', 8, 'metadata', { as_of: '2026-10-01' })
    assert.deepEqual(calls.map(call => call.method), ['POST', 'PUT', 'POST', 'POST', 'POST', 'PATCH'])
    assert.equal(calls[1].url.endsWith('/records/%E6%9D%A5%E6%BA%90%20%E7%BC%96%E5%8F%B7/'), true)
    assert.deepEqual(calls.map(call => call.body.expected_revision), [3, 4, 5, 6, 7, 8])
    assert.deepEqual(calls[0].body.record, presales)
    assert.deepEqual(calls[2].body, { expected_revision: 5 })
    assert.deepEqual(calls[4].body, { expected_revision: 7, reason: '请核对来源' })
    assert.deepEqual(calls[5].body, { expected_revision: 8, as_of: '2026-10-01' })
    assert.equal(calls.some(call => Array.isArray(call.body.records)), false)
    calls.length = 0; failWrite = true
    await assert.rejects(api.saveLedgerRecord('presales', 8, presales, presales.project_id), error => error.status === 409)
    assert.equal(calls.length, 1)
  } finally { globalThis.fetch = originalFetch; globalThis.localStorage = originalStorage }
})

test('dirty guards preserve router state when browser back or forward is cancelled and clean up', () => {
  const browser = new EventTarget(), steps = []
  browser.location = { href: 'http://localhost/departments/product/entry' }
  browser.history = { state: { idx: 2 }, go: delta => steps.push(delta), replaceState: (state, _, href) => { browser.history.state = state; browser.location.href = href } }
  // Match the app's registration order: the global boundary precedes BrowserRouter; page guards mount later.
  installLedgerBrowserBoundary(browser)
  installLedgerBrowserBoundary(browser)
  let routerCalls = 0
  browser.addEventListener('popstate', () => routerCalls++)
  let leave = false
  const cleanup = installLedgerNavigationGuard(browser, () => leave)
  assert.equal(browser.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true })), false)
  const unload = new Event('beforeunload', { cancelable: true })
  browser.dispatchEvent(unload)
  assert.equal(unload.defaultPrevented, true)
  browser.location.href = 'http://localhost/departments/product/knowledge'; browser.history.state = { idx: 1 }
  browser.dispatchEvent(new Event('popstate'))
  assert.deepEqual(steps, [1]); assert.equal(routerCalls, 0)
  browser.location.href = 'http://localhost/departments/product/entry'; browser.history.state = { idx: 2 }
  browser.dispatchEvent(new Event('popstate'))
  assert.equal(routerCalls, 1)
  browser.location.href = 'http://localhost/departments/product/opportunities'; browser.history.state = { idx: 3 }
  browser.dispatchEvent(new Event('popstate'))
  assert.deepEqual(steps, [1, -1]); assert.equal(routerCalls, 1)
  browser.location.href = 'http://localhost/departments/product/entry'; browser.history.state = { idx: 2 }
  browser.dispatchEvent(new Event('popstate'))
  leave = true
  browser.location.href = 'http://localhost/departments/product/opportunities'; browser.history.state = { idx: 3 }
  browser.dispatchEvent(new Event('popstate'))
  assert.equal(routerCalls, 3)
  cleanup()
  assert.equal(browser.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true })), true)
  browser.location.href = 'http://localhost/settings'; browser.history.state = { idx: 4 }
  browser.dispatchEvent(new Event('popstate'))
  assert.equal(routerCalls, 4)
  const oldCleanup = installLedgerNavigationGuard(browser, () => false)
  const newCleanup = installLedgerNavigationGuard(browser, () => false)
  oldCleanup()
  browser.location.href = 'http://localhost/departments/product/knowledge'; browser.history.state = { idx: 5 }
  browser.dispatchEvent(new Event('popstate'))
  assert.equal(routerCalls, 4)
  assert.deepEqual(steps, [1, -1, -1])
  newCleanup()
})
