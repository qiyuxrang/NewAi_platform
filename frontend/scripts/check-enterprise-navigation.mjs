import assert from 'node:assert/strict'
import { availableDepartments, canAccessDepartment, canAccessSetting, departmentPath, enterpriseHomePath, readBusinessRows } from '../src/enterprise-navigation.ts'

const employee = { role: 'user', business_role: 'employee', department_code: 'hr', capabilities: ['hr'] }
const manager = { role: 'user', business_role: 'general_manager', department_code: null, capabilities: ['general_manager', 'product', 'hr', 'engineering'] }
const unassigned = { role: 'user', business_role: 'unassigned', department_code: null, capabilities: [] }
assert.deepEqual(availableDepartments(employee).map(item => item.code), ['hr'])
assert.deepEqual(availableDepartments(manager).map(item => item.code), ['product', 'hr', 'engineering'])
assert.equal(canAccessDepartment(employee, 'product'), false)
assert.equal(canAccessDepartment({ ...employee, capabilities: ['hr', 'product'] }, 'product'), false)
assert.equal(canAccessDepartment({ ...manager, capabilities: [] }, 'hr'), false)
assert.equal(canAccessDepartment(manager, 'unknown'), false)
assert.deepEqual(availableDepartments(unassigned), [])
assert.equal(canAccessDepartment({ ...unassigned, department_code: 'hr', capabilities: ['hr'] }, 'hr'), false)
assert.equal(canAccessDepartment(null, 'hr'), false)
assert.equal(canAccessSetting(employee, 'personal'), true)
assert.equal(canAccessSetting(employee, 'admin'), false)
assert.equal(canAccessSetting(manager, 'admin'), false)
assert.equal(canAccessSetting(unassigned, 'personal'), false)
assert.equal(canAccessSetting(unassigned, 'account'), true)
assert.equal(canAccessSetting({ ...unassigned, role: 'admin' }, 'admin'), true)
assert.equal(canAccessSetting(null, 'account'), false)
assert.equal(departmentPath('hr', 'resumes'), '/departments/hr/resumes')
for (const department of ['product', 'hr', 'engineering', 'finance']) {
  assert.equal(enterpriseHomePath({ ...employee, department_code: department, capabilities: [department] }), `/departments/${department}`)
  assert.equal(enterpriseHomePath({ ...employee, department_code: department, capabilities: [] }), '/dashboard')
}
assert.equal(canAccessDepartment(manager, 'finance'), false)
assert.equal(canAccessDepartment({ ...employee, department_code: 'finance', capabilities: ['finance'] }, 'finance'), true)
assert.equal(canAccessDepartment({ ...employee, capabilities: ['hr', 'finance'] }, 'finance'), false)
assert.equal(enterpriseHomePath(manager), '/dashboard')
assert.equal(enterpriseHomePath({ ...manager, capabilities: ['hr'] }), '/departments/hr')
assert.equal(enterpriseHomePath(unassigned), '/dashboard')
assert.equal(enterpriseHomePath(null), '/dashboard')
assert.deepEqual(readBusinessRows({ tasks: [{ id: 'real-task' }] }, 'tasks'), [{ id: 'real-task' }])
assert.deepEqual(readBusinessRows([]), [])
assert.throws(() => readBusinessRows({ unavailable: true }, 'tasks'))
assert.throws(() => readBusinessRows({ tasks: [null] }, 'tasks'))
console.log('Enterprise navigation permission checks passed.')
