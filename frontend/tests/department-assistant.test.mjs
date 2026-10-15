import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'
import * as navigation from '../src/enterprise-navigation.ts'

const codes = ['product', 'hr', 'engineering', 'finance']
const employee = department => ({ business_role: 'employee', department_code: department, capabilities: codes })

test('every department owns one assistant path while existing employee and manager permissions stay scoped', () => {
  for (const code of codes) {
    const department = navigation.departments.find(item => item.code === code)
    assert.deepEqual(department.functions.filter(item => item.code === 'knowledge').map(item => item.label), ['智能助手'])
    assert.equal(navigation.departmentPath(code, 'knowledge'), `/departments/${code}/knowledge`)
    assert.deepEqual(navigation.availableDepartments(employee(code)).map(item => item.code), [code])
    for (const target of codes) assert.equal(navigation.canAccessDepartment(employee(code), target), code === target)
    assert.equal(navigation.canAccessDepartment({ ...employee(code), capabilities: [] }, code), false)
  }
  assert.deepEqual(navigation.availableDepartments({ business_role: 'unassigned', capabilities: codes }), [])
  const manager = { business_role: 'general_manager', capabilities: [...codes, 'general_manager'] }
  assert.deepEqual(navigation.availableManagerEntries(manager).map(item => [item.label, item.to]), [
    ['商机看板', '/departments/product/opportunities'], ['文档生成', '/departments/product/documents?view=projects'],
    ['产品报价', '/departments/engineering/estimate'], ['智能助手', '/departments/product/knowledge'],
    ['财务看板', '/departments/business/finance'],
  ])
})

test('department assistant renders the shared component once without invoking HR or engineering workspaces', () => {
  const compiled = ts.transpileModule(readFileSync(new URL('../src/pages/DepartmentWorkspace.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText
  function render(department, feature = 'knowledge') {
    const exports = {}, components = new Map()
    const component = name => { if (!components.has(name)) components.set(name, Object.assign(() => null, { displayName: name })); return components.get(name) }
    vm.runInNewContext(compiled, { exports, require: name => {
      if (name === 'react/jsx-runtime') return jsx
      if (name === 'react') return { useEffect() {}, useState: initial => [initial === null ? { available: true, linked: true, configured: true } : initial, () => {}] }
      if (name === 'react-router-dom') return { Link: component('Link'), useParams: () => ({ department, feature }) }
      if (name.endsWith('enterprise-navigation')) return navigation
      if (name.endsWith('enterprise-context')) return { useEnterprise: () => ({ user: employee(department) }) }
      if (name.endsWith('entry-access')) return { useEntryAccess: () => false }
      return { default: component(name.split('/').at(-1)), ArrowRight: component('ArrowRight') }
    } })
    return exports.default()
  }
  const elements = node => !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(elements)]
  for (const code of codes.slice(1)) {
    const tree = render(code), nodes = elements(tree)
    assert.match(tree.props.className, /assistant-department/)
    assert.equal(nodes.filter(node => node.type?.displayName === 'ProductKnowledge').length, 1, code)
    assert.equal(nodes.filter(node => ['HrWorkspace', 'EngineeringWorkspace', 'ProductWorkspace'].includes(node.type?.displayName)).length, 0, code)
    assert.equal(nodes.filter(node => node.type === 'h1' && !nodes.some(parent => parent.props?.hidden && elements(parent).includes(node))).length, 0, 'no duplicate visible department heading')
  }
  assert.equal(elements(render('product')).filter(node => node.type?.displayName === 'ProductWorkspace').length, 1)
  assert.equal(elements(render('hr', 'jobs')).filter(node => node.type?.displayName === 'HrWorkspace').length, 1)
  assert.equal(elements(render('engineering', 'estimate')).filter(node => node.type?.displayName === 'EngineeringWorkspace').length, 1)
  assert.equal(elements(render('finance', 'entry')).filter(node => node.type?.displayName === 'FinanceEntry').length, 1)
})
