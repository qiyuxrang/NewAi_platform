import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'
import { departments, availableManagerEntries } from '../src/enterprise-navigation.ts'
import { apiRequest as actualRequest, ApiError as ActualApiError } from '../src/business/api.ts'

class ApiError extends Error { constructor(status, message, code, errors) { super(message); this.status = status; this.code = code; this.errors = errors } }
function load(name, mocks = {}) {
  const exports = {}
  const compiled = ts.transpileModule(readFileSync(new URL(`../src/business/product/${name}`, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  vm.runInNewContext(compiled, { exports, require: module => module === 'react/jsx-runtime' ? jsx : module === '../api' ? { ApiError, ...mocks.api } : module === './Baichuan-data' ? data : module.endsWith('.png') ? { default: module } : mocks[module] || {}, URL, URLSearchParams, AbortController, Event, navigator: mocks.navigator || {}, requestAnimationFrame: fn => { fn(); return 1 }, cancelAnimationFrame() {}, sessionStorage: { getItem: () => null }, window: { confirm: () => true, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => true }, document: { addEventListener() {}, removeEventListener() {} } })
  return exports
}
const data = load('Baichuan-data.ts')
const plain = value => JSON.parse(JSON.stringify(value))
const row = (category, grade, status = 'PRESENT') => ({ id: `${category}-${grade}`, category, grade, status, certificate_no: null, valid_until: null, source: null, verified_on: null })
const company = { ...data.emptyDraft().company, id: 'a', version: 7, name: '样例A' }
const detail = { company, qualifications: [row('electronic', '1'), row('electronic', '2'), row('cmmi', '3')], people: [{ id: 'p', name: '人员甲', credentials: 'CMMI五级', verified_on: null }], permissions: { can_edit: true } }
test('API preserves validated field errors while retaining three-argument ApiError compatibility', async () => {
  assert.equal(new ActualApiError(400, 'legacy', 'invalid_request').errors, undefined)
  const originalFetch = globalThis.fetch, originalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'isolated-token' }
  globalThis.fetch = async () => Response.json({ detail: '字段错误', code: 'invalid_request', errors: { 'company.name': '名称必填', unsupported: ['not a string'] } }, { status: 400 })
  try { await assert.rejects(actualRequest('/api/product/baichuan/companies/'), reason => reason instanceof ActualApiError && reason.status === 400 && reason.errors['company.name'] === '名称必填' && !Object.hasOwn(reason.errors, 'unsupported')) }
  finally { globalThis.fetch = originalFetch; globalThis.localStorage = originalStorage }
})
test('fixed qualification dictionary, any/grade exclusivity and URL retain server validation', () => {
  assert.deepEqual(plain(data.qualificationTypes.map(item => [item.code, item.grades])), [['electronic', ['1', '2']], ['labor', []], ['cs', ['1', '2', '3', '4', '5']], ['cmmi', ['3', '4', '5']], ['ccrc', ['1', '2', '3']], ['itss', ['1', '2', '3', '4']], ['security', ['1', '2', '3']]])
  assert.equal(data.toggleGrade('any', '1'), '1'); assert.equal(data.toggleGrade('2', '1'), '1,2'); assert.equal(data.toggleGrade('1,2', '2'), '1'); assert.equal(data.toggleGrade('1', '1'), '')
  const query = new URLSearchParams(data.listQuery('?q=样例&electronic=1,2&page=2&company=a'))
  assert.equal(query.get('company'), null); assert.equal(query.get('page'), '2'); assert.equal(query.get('page_size'), '20'); assert.equal(query.get('q'), '样例')
  assert.equal(new URLSearchParams(data.listQuery('?page=0&cs=1&cs=2')).get('page'), '0'); assert.equal(new URLSearchParams(data.listQuery('?cs=1&cs=2')).getAll('cs').length, 2)
})
test('websites reject unsafe protocols and credentials; snapshots retain child IDs and expected version', () => {
  for (const invalid of ['', null, 'javascript:alert(1)', 'data:text/html,hi', 'https://user:secret@example.com', 'https://@example.com', 'https://example.com/\\evil', 'https://exam ple.com', 'broken']) assert.equal(data.safeWebsite(invalid), null)
  assert.equal(data.safeWebsite('https://example.com'), 'https://example.com/')
  const draft = data.draftFrom(detail)
  assert.equal(draft.expected_version, 7); assert.equal(draft.qualifications.length, 3); assert.equal(draft.people[0].id, 'p'); assert.equal(Object.hasOwn(draft.company, 'id'), false)
  draft.qualifications[0].grade = '2'; assert.equal(detail.qualifications[0].grade, '1')
})
test('post-save membership uses exact grades, OR within and AND across categories, without personnel inference', () => {
  const draft = data.draftFrom(detail)
  assert.equal(data.matchesQuery(draft, '?electronic=1,2&cmmi=3'), true)
  assert.equal(data.matchesQuery(draft, '?electronic=1&cmmi=5'), false)
  assert.equal(data.matchesQuery(draft, '?q=其他'), false)
  draft.qualifications = [row('electronic', '1'), row('cmmi', null)]
  assert.equal(data.matchesQuery(draft, '?electronic=2'), false); assert.equal(data.matchesQuery(draft, '?cmmi=any'), true); assert.equal(data.matchesQuery(draft, '?cmmi=3'), false)
  draft.qualifications = [row('electronic', null, 'ABSENT')]
  assert.equal(data.matchesQuery(draft, '?electronic=any'), false)
})
test('both entrypoints share the product feature while preserving capability restrictions', () => {
  assert.ok(departments.find(item => item.code === 'product').functions.some(item => item.code === 'baichuan'))
  assert.equal(availableManagerEntries({ business_role: 'general_manager', capabilities: ['product'] }).find(item => item.label === '百川阁').to, '/departments/product/baichuan')
  assert.equal(availableManagerEntries({ business_role: 'general_manager', capabilities: [] }).some(item => item.label === '百川阁'), false)
})
function hooks() {
  const slots = []; let cursor = 0; let effects = []
  const same = (a, b) => a?.length === b?.length && a.every((value, index) => Object.is(value, b[index]))
  return { clear() { slots.length = 0 }, begin() { cursor = 0; effects = [] }, run() { effects.forEach(fn => fn()) }, react: {
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial }; return [slots[index].value, next => { slots[index].value = typeof next === 'function' ? next(slots[index].value) : next }] },
    useRef(value) { const index = cursor++; return slots[index] ||= { current: value } },
    useMemo(fn, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) slots[index] = { deps, value: fn() }; return slots[index].value },
    useEffect(fn, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) { slots[index]?.cleanup?.(); slots[index] = { deps }; effects.push(() => { slots[index].cleanup = fn() }) } },
  } }
}
function nodes(tree) { if (!tree || typeof tree !== 'object') return []; return [tree, ...[tree.props?.children].flat(Infinity).flatMap(nodes)] }
function text(tree) { if (typeof tree === 'string' || typeof tree === 'number') return String(tree); return [tree?.props?.children].flat(Infinity).map(item => item && typeof item === 'object' ? text(item) : item ?? '').join(' ') }
const flush = async () => { for (let index = 0; index < 8; index++) await Promise.resolve() }

test('detail preserves source statements and line breaks, linking only safe HTTP(S) evidence without surrounding punctuation', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  const source = '原始声明：待核实\n证据（https://example.com/a_(b)?q=1&x=2）。\nhttps://example.org/report.pdf, https://example.net/contact：公开资料\n危险 javascript:https://blocked.example https://user:secret@example.com https://@example.com https://example.com/\\evil'
  const longUrl = `https://example.edu/evidence/${'long-'.repeat(70)}?key=value`
  const tree = Detail({ data: { ...detail, company: { ...company, source, description: `原始资质声明\n证据：${longUrl}` }, qualifications: [ { ...row('cs', '1'), source: '历史来源\nhttps://qualification.example/certificate' } ], people: [{ ...detail.people[0], source: '来源时点2024年\nhttp://people.example/profile' }] }, matched: new Set(), onBack() {}, onEdit() {} })
  const anchors = nodes(tree).filter(node => node.type === 'a')
  assert.deepEqual(anchors.map(node => node.props.href), [longUrl, 'https://example.com/a_(b)?q=1&x=2', 'https://example.org/report.pdf', 'https://example.net/contact', 'https://qualification.example/certificate', 'http://people.example/profile'])
  assert.ok(anchors.every(node => node.props.target === '_blank' && node.props.rel === 'noopener noreferrer'))
  const exactText = item => typeof item === 'string' || typeof item === 'number' ? String(item) : Array.isArray(item) ? item.map(exactText).join('') : exactText(item?.props?.children ?? '')
  assert.ok(nodes(tree).some(node => node.type === 'div' && exactText(node) === source))
  assert.ok(nodes(tree).some(node => node.type === 'p' && node.props.className === 'bc-overview-text' && exactText(node) === `原始资质声明\n证据：${longUrl}`))
  assert.match(text(tree), /公开人员资料/); assert.doesNotMatch(text(tree), /统一社会信用代码|核实日期|系统修改时间|未提供|未查询|核心团队/)
  assert.match(text(tree), /CS 信息系统建设和服务能力等级认证 · 一级/)
  const css = readFileSync(new URL('../src/business/product/Baichuan.css', import.meta.url), 'utf8')
  assert.match(css, /bc-description[^}]*white-space:pre-wrap[^}]*overflow-wrap:anywhere/)
  assert.match(css, /bc-details dd[^}]*overflow-wrap:anywhere[^}]*white-space:pre-wrap/)
})
test('details hide empty fields and metadata, preserve all sources in one closed disclosure and expose safe official links', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  const source = `${'原始声明'.repeat(80)}\n证据：https://evidence.example/full-source。`
  const supplied = { ...detail, company: { ...company, description: '源表资质声明\n原始证书声明', source, phone: '029-12345678', credit_code: '91610000123456789X', verified_on: '2024-01-01', updated_at: '2026-01-01', website: 'https://official.example/' }, qualifications: [{ ...row('cs', '1'), source, verified_on: '2024-01-01' }], people: [{ ...detail.people[0], position: '项目联系人', source, verified_on: '2024-01-01' }] }
  const render = data => Detail({ data, matched: new Set(), onBack() {}, onEdit() {} })
  const tree = render(supplied), disclosures = nodes(tree).filter(node => node.type === 'details')
  assert.equal(disclosures.length, 1)
  const disclosure = disclosures[0]
  assert.equal(disclosure.props.open, undefined)
  assert.equal(text(nodes(disclosure).find(node => node.type === 'summary')), '资料来源')
  assert.equal(nodes(disclosure).filter(node => node.type === 'a' && node.props.href === 'https://evidence.example/full-source').length, 3)
  assert.match(text(disclosure), /原始证书声明/)
  const sourceNodes = nodes(disclosure).filter(node => node.props?.className === 'bc-source')
  assert.equal(sourceNodes.length, 4)
  assert.ok(sourceNodes.slice(1).every(node => node.props.children[1].props.children.map(part => typeof part === 'string' ? part : part.props.children).join('') === source))
  assert.doesNotMatch(text(tree), /统一社会信用代码|核实日期|系统修改时间|未提供|未查询|91610000123456789X|2024-01-01|2026-01-01/)
  assert.ok(nodes(tree).some(node => node.type === 'dd' && text(node) === '029-12345678'))
  assert.ok(nodes(tree).some(node => node.type === 'dd' && text(node) === '项目联系人'))
  const officialLinks = nodes(tree).filter(node => node.type === 'a' && node.props.href === 'https://official.example/')
  assert.equal(officialLinks.length, 3)
  assert.equal(text(officialLinks[1]).trim(), '访问企业官网')
  assert.ok(officialLinks.every(node => node.props.target === '_blank' && node.props.rel === 'noopener noreferrer'))
  const empty = render({ ...detail, company, qualifications: [], people: [] })
  assert.doesNotMatch(text(empty), /公司资料|企业资质|联系方式|公开人员资料|资料来源|未提供|未查询/)
  const invalidWebsite = render({ ...detail, company: { ...company, website: 'javascript:alert(1)' }, qualifications: [], people: [] })
  assert.equal(nodes(invalidWebsite).filter(node => node.type === 'a').length, 0)
  const short = render({ ...detail, company: { ...company, source: '短来源' }, qualifications: [], people: [] })
  assert.equal(nodes(short).filter(node => node.type === 'details').length, 1, 'short sources also stay closed')
})

test('detail business tiles use only explicit areas, keep all labels and limit photos to decoration', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  const areas = ['建筑智能化EPC总承包', '城市亮化及道路照明工程', '计算机网络系统集成', '智慧园区通讯网络运营', '智慧城市', '物联网智能综合平台', '已公开的其他业务']
  const tree = Detail({ data: { ...detail, company: { ...company, description: `公开的公司简介。\n业务领域：${areas.join('；')}。`, province: '陕西', city: '西安', phone: '029-12345678' } }, matched: new Set(), onBack() {}, onEdit() {} })
  const grid = nodes(tree).find(node => node.props?.className === 'bc-business-grid')
  const tiles = grid.props.children
  assert.deepEqual(plain(tiles.map(tile => text(nodes(tile).find(node => node.type === 'strong')))), areas)
  const photos = nodes(grid).filter(node => node.type === 'img')
  assert.equal(photos.length, 6)
  assert.equal(new Set(photos.map(node => node.props.src)).size, 6)
  assert.ok(photos.every(node => node.props.alt === '' && node.props['aria-hidden'] === 'true'))
  assert.equal(nodes(tiles.at(-1)).some(node => node.type === 'img'), false)
  const overview = nodes(tree).find(node => node.props?.className === 'bc-overview-text')
  assert.equal(text(overview), '公开的公司简介。')
  const columns = nodes(tree).find(node => node.props?.className === 'bc-detail-columns')
  assert.deepEqual(plain(columns.props.children.map(node => node.props.className)), ['bc-card bc-overview-card', 'bc-card bc-qualifications-card', 'bc-card bc-business-card', 'bc-card bc-contacts-card'])
  for (const label of ['COMPANY OVERVIEW', 'QUALIFICATIONS', 'BUSINESS AREAS', 'CONTACT INFORMATION']) assert.match(text(columns), new RegExp(label))
  const proseOnly = Detail({ data: { ...detail, company: { ...company, description: '本公司从事智慧城市及物联网业务。' } }, matched: new Set(), onBack() {}, onEdit() {} })
  assert.equal(nodes(proseOnly).some(node => node.props?.className === 'bc-business-grid'), false, 'prose must not infer business tile labels')
})

test('the supplied company logo belongs only to its exact company, while sparse Wanbang retains actual structured fields', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  const render = name => Detail({ data: { ...detail, company: { ...company, name, province: '陕西', city: '西安' }, qualifications: [row('electronic', '1')], people: [] }, matched: new Set(['electronic-1']), onBack() {}, onEdit() {} })
  const exact = render('陕西凯笙信息技术有限公司')
  assert.equal(nodes(exact).filter(node => node.type === 'img' && node.props.src.endsWith('ksznkj-logo.png')).length, 1)
  for (const name of ['陕西凯笙信息技术有限公司分公司', '万邦建工集团有限公司']) {
    const tree = render(name)
    assert.equal(nodes(tree).filter(node => node.type === 'img' && node.props.src.endsWith('ksznkj-logo.png')).length, 0)
    assert.equal(nodes(tree).filter(node => node.type === 'header' && node.props.className.includes('bc-company-hero')).length, 1)
    assert.match(text(tree), new RegExp(name))
    assert.match(text(tree), /陕西 · 西安/)
    assert.match(text(tree), /命中筛选/)
    assert.doesNotMatch(text(tree), /业务领域|联系方式|高新技术企业|企业定位|行业领域|智慧城市|未提供/)
    assert.equal(nodes(tree).filter(node => node.props?.className === 'bc-hero-architecture' && node.props.alt === '').length, 1)
  }
})

test('actual addresses and websites show contacts independently, and editing follows permission', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  for (const fields of [{ address: '公开地址18层' }, { website: 'https://official.example/' }]) {
    const tree = Detail({ data: { company: { ...company, ...fields }, qualifications: [], people: [], permissions: { can_edit: false } }, matched: new Set(), onBack() {}, onEdit() { assert.fail('read-only company cannot be edited') } })
    assert.equal(nodes(tree).filter(node => node.props?.className === 'bc-card bc-contacts-card').length, 1)
    assert.doesNotMatch(text(tree), /编辑资料|业务联系人|业务联系电话|公司电话|邮箱/)
    for (const expected of Object.values(fields)) assert.ok(text(tree).includes(expected))
  }
})

test('the top website action stays visible without a safe URL, and adding one uses the authorized editor', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  for (const website of [null, '', 'javascript:alert(1)', 'https://user:password@example.com']) {
    for (const can_edit of [false, true]) {
      let edited = 0
      const tree = Detail({ data: { company: { ...company, website }, qualifications: [], people: [], permissions: { can_edit } }, matched: new Set(), onBack() {}, onEdit() { edited++ } })
      const action = nodes(tree).find(node => node.type === 'button' && text(node).trim() === '访问企业官网')
      assert.equal(action.props.disabled, true)
      assert.equal(action.props.onClick, undefined)
      assert.equal(nodes(tree).filter(node => node.type === 'a').length, 0)
      assert.doesNotMatch(text(tree), /未查询|未提供|复制官网链接/)
      const add = nodes(tree).find(node => node.type === 'button' && text(node).trim() === '添加官网地址')
      assert.equal(Boolean(add), can_edit)
      if (add) { add.props.onClick(); assert.equal(edited, 1) }
    }
  }
})

test('clipboard success and rejection report their real outcome without leaking status to another website', async () => {
  for (const failure of [false, true]) {
    const state = hooks(), copied = []
    const Detail = load('CompanyDetail.tsx', { react: state.react, navigator: { clipboard: { async writeText(url) { copied.push(url); if (failure) throw new Error('permission denied') } } } }).default
    let website = 'https://official.example/'
    const render = () => { state.begin(); return Detail({ data: { ...detail, company: { ...company, website } }, matched: new Set(), onBack() {}, onEdit() {} }) }
    let tree = render()
    await nodes(tree).find(node => node.type === 'button' && text(node).trim() === '复制官网链接').props.onClick()
    tree = render()
    assert.deepEqual(copied, ['https://official.example/'])
    const status = nodes(tree).find(node => node.props?.role === 'status')
    assert.equal(text(status), failure ? '复制失败，请手动复制上方网址' : '官网链接已复制')
    website = 'https://another.example/'
    assert.equal(nodes(render()).some(node => node.props?.role === 'status'), false)
  }
})

test('official homepages explicitly distinguish corporate, group profile and official WeChat', () => {
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] } }).default
  for (const kind of data.websiteTypes) {
    const tree = Detail({ data: { ...detail, company: { ...company, website: 'https://example.com/company', website_kind: kind.code } }, matched: new Set(), onBack() {}, onEdit() {} })
    assert.ok(text(tree).includes(kind.label))
    const action = nodes(tree).find(node => node.type === 'a' && text(node).trim() === kind.action)
    assert.equal(action.props.href, 'https://example.com/company')
    assert.equal(action.props.target, '_blank')
    assert.equal(action.props.rel, 'noopener noreferrer')
    assert.equal(data.draftFrom({ ...detail, company: { ...company, website_kind: kind.code } }).company.website_kind, kind.code)
  }
})

test('qualification cards retain each declared status and certificate and use category icons', () => {
  const icons = { Building2: 'Building2', Hammer: 'Hammer', BadgeCheck: 'BadgeCheck', Settings: 'Settings', Settings2: 'Settings2', ShieldCheck: 'ShieldCheck' }
  const Detail = load('CompanyDetail.tsx', { react: { useState: () => [{ url: '', message: '' }, () => {}] }, 'lucide-react': icons }).default
  const qualifications = [row('electronic', '1'), row('labor', null), { ...row('cs', null, 'UNKNOWN'), certificate_no: '已公开证号', valid_until: '2028-01-01' }, row('cmmi', '3'), row('ccrc', '2'), row('itss', '2'), row('security', null, 'ABSENT')]
  const tree = Detail({ data: { ...detail, qualifications }, matched: new Set(), onBack() {}, onEdit() {} })
  const cards = nodes(tree).filter(node => node.type === 'article' && node.props['data-category'])
  assert.deepEqual(plain(cards.map(card => card.props.children[0].type)), ['Building2', 'Hammer', 'BadgeCheck', 'Settings', 'ShieldCheck', 'Settings2', 'ShieldCheck'])
  assert.match(text(cards[2]), /待核实/); assert.match(text(cards[2]), /已公开证号/); assert.match(text(cards[2]), /2028-01-01/)
  assert.match(text(cards[6]), /不具备/)
})

test('checkbox selection updates immediately while the router still exposes the previous URL', () => {
  const state = hooks()
  const Component = load('Baichuan.tsx', { react: state.react, 'react-router-dom': { useLocation: () => ({ search: '', pathname: '/departments/product/baichuan', key: 'a', state: null }), useNavigate: () => () => {} } }).default
  state.begin(); const root = Component()
  const Filter = nodes(root).find(node => node.props?.category?.code === 'electronic').type
  state.clear(); let selected = ''
  const render = () => { state.begin(); return Filter({ category: data.qualificationTypes[0], value: '', onChange: value => { selected = value } }) }
  let tree = render(); nodes(tree).find(node => node.type === 'button').props.onClick(); tree = render()
  nodes(tree).find(node => node.type === 'label' && text(node).trim() === '二级').props.children[0].props.onChange()
  tree = render()
  assert.equal(selected, '2'); assert.equal(nodes(tree).find(node => node.type === 'label' && text(node).trim() === '二级').props.children[0].props.checked, true)
})
test('list exposes actual safe websites, extra contacts and server page controls without inventing fields', async () => {
  const state = hooks(), navigations = [], location = { search: '?page=2&page_size=10', pathname: '/departments/product/baichuan', key: 'a', state: null }
  const items = [{ ...company, phone: '029-12345678；029-23456789', website: 'https://official.example/', email: 'public@example.com', qualifications: [row('cs', '1')] }, { ...company, id: 'b', name: '样例B', website: 'javascript:alert(1)', qualifications: [] }]
  const Component = load('Baichuan.tsx', { react: state.react, 'react-router-dom': { useLocation: () => location, useNavigate: () => (...args) => navigations.push(args) }, api: { apiRequest: async () => ({ items, total: 31, page: 2, page_size: 10, has_more: true, permissions: { can_create: false } }) } }).default
  const render = () => { state.begin(); const tree = Component(); state.run(); return tree }
  render(); await flush(); const tree = render()
  const websites = nodes(tree).filter(node => node.type === 'a')
  assert.equal(websites.length, 1); assert.equal(websites[0].props.href, 'https://official.example/')
  assert.equal(websites[0].props.target, '_blank'); assert.equal(websites[0].props.rel, 'noopener noreferrer')
  const extra = nodes(tree).find(node => node.type === 'details')
  assert.equal(extra.props.open, undefined); assert.match(text(extra), /029-23456789/); assert.match(text(extra), /public@example.com/)
  nodes(tree).find(node => node.type === 'button' && node.props['aria-label'] === '第 3 页').props.onClick()
  assert.equal(new URLSearchParams(navigations.at(-1)[0].search).get('page'), '3')
  nodes(tree).find(node => node.type === 'select' && node.props['aria-label'] === '每页公司数量').props.onChange({ target: { value: '50' } })
  const changed = new URLSearchParams(navigations.at(-1)[0].search)
  assert.equal(changed.get('page_size'), '50'); assert.equal(changed.get('page'), '1')
})

test('stale success and stale failure cannot replace the latest query, and loading never reports zero', async () => {
  const state = hooks(), requests = [], location = { search: '', pathname: '/departments/product/baichuan', key: 'a', state: null }
  const Component = load('Baichuan.tsx', { react: state.react, 'react-router-dom': { useLocation: () => location, useNavigate: () => () => {} }, api: { apiRequest: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })) } }).default
  const render = () => { state.begin(); const tree = Component(); state.run(); return tree }
  assert.doesNotMatch(text(render()), /共 0 家/)
  location.search = '?electronic=2'; location.key = 'b'; render(); assert.equal(requests[0].options.signal.aborted, true)
  requests[1].resolve({ items: [], total: 2, page: 1, page_size: 20, has_more: false, permissions: { can_create: false } }); await flush()
  assert.match(text(render()), /共 2 家/)
  requests[0].resolve({ items: [], total: 99, permissions: {} }); await flush(); assert.match(text(render()), /共 2 家/)
  location.search = '?cmmi=3'; location.key = 'c'; render()
  location.search = '?cmmi=5'; location.key = 'd'; render()
  requests[3].resolve({ items: [], total: 1, page: 1, page_size: 20, has_more: false, permissions: { can_create: false } }); requests[2].reject(new Error('stale error')); await flush()
  assert.match(text(render()), /共 1 家/); assert.doesNotMatch(text(render()), /stale error/)
})
test('a filtered page beyond the last page preserves the total and explains the empty page', async () => {
  const state = hooks()
  const Component = load('Baichuan.tsx', { react: state.react, 'react-router-dom': { useLocation: () => ({ search: '?electronic=1&page=999', pathname: '/departments/product/baichuan', key: 'a', state: null }), useNavigate: () => () => {} }, api: { apiRequest: async () => ({ items: [], total: 5, page: 999, page_size: 20, has_more: false, permissions: { can_create: false } }) } }).default
  const render = () => { state.begin(); const tree = Component(); state.run(); return tree }
  render(); await flush(); const result = text(render())
  assert.match(result, /共 5 家/); assert.match(result, /该页暂无公司/); assert.match(result, /请选择前面的页码/); assert.doesNotMatch(result, /没有符合条件的公司/)
})
test('editor submits a complete atomic snapshot, keeps inputs on conflict, and serializes cleared dates to null', async () => {
  const state = hooks(), requests = []
  const Editor = load('CompanyEditor.tsx', { react: state.react, api: { apiRequest: async (url, options) => { requests.push({ url, options }); if (!options) return { items: [], has_more: false }; throw new ApiError(409, 'conflict', 'version_conflict') } } }).default
  const render = () => { state.begin(); return Editor({ detail, onClose() {}, onSaved() { assert.fail('conflict must not count as success') } }) }
  let tree = render()
  nodes(tree).find(node => node.type === 'input' && node.props.name === 'name').props.onChange({ target: { value: '更改名称' } })
  nodes(tree).find(node => node.type === 'select' && node.props.name === 'website_kind').props.onChange({ target: { value: 'group_profile' } })
  tree = render(); nodes(tree).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await flush(); tree = render()
  const payload = JSON.parse(requests.find(item => item.options)?.options.body)
  assert.equal(payload.expected_version, 7); assert.equal(payload.company.name, '更改名称'); assert.equal(payload.company.verified_on, null); assert.equal(payload.people[0].verified_on, null); assert.equal(payload.qualifications.length, 3); assert.equal(payload.people[0].id, 'p')
  assert.match(text(tree), /资料已被其他人修改/)
  assert.equal(nodes(tree).find(node => node.type === 'input' && node.props.name === 'name').props.value, '更改名称')
  assert.equal(payload.company.website_kind, 'group_profile')
  assert.equal(nodes(tree).find(node => node.type === 'select' && node.props.name === 'website_kind').props.value, 'group_profile')
})
test('server field errors appear at the affected company input and retain its draft value', async () => {
  const state = hooks()
  const Editor = load('CompanyEditor.tsx', { react: state.react, api: { apiRequest: async (_url, options) => { if (!options) return { items: [], has_more: false }; throw new ApiError(400, '地址输入无效', 'invalid_request', { 'company.address': '地址超出长度' }) } } }).default
  const render = () => { state.begin(); return Editor({ detail, onClose() {}, onSaved() { assert.fail('invalid input must not save') } }) }
  let tree = render(); nodes(tree).find(node => node.type === 'input' && node.props.name === 'address').props.onChange({ target: { value: '保留地址' } })
  tree = render(); nodes(tree).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); await flush(); tree = render()
  const input = nodes(tree).find(node => node.type === 'input' && node.props.name === 'address')
  assert.equal(input.props['aria-invalid'], true); assert.equal(input.props.value, '保留地址'); assert.match(text(tree), /地址超出长度/)
  let focused = false
  tree.props.ref.current = { querySelector(selector) { assert.equal(selector, '[aria-invalid="true"]'); return { focus() { assert.equal(nodes(tree).find(node => node.type === 'fieldset').props.disabled, false); focused = true } } } }
  state.run()
  assert.equal(focused, true, 'field focus must run after the committed fieldset is enabled')
})
