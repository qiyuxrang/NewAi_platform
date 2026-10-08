import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import test from 'node:test'
import ts from 'typescript'

function compile(relative, context = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8')
  const result = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true })
  assert.equal(result.diagnostics?.length ?? 0, 0)
  const module = { exports: {} }
  runInNewContext(result.outputText, { module, exports: module.exports, TextEncoder, ...context })
  return module.exports
}
const { businessAssignmentPayload, userCredentialsPayload } = compile('../src/lib/business-assignment.ts')
const plain = value => JSON.parse(JSON.stringify(value))

test('employee payload has department and positive integer portal ID', () => {
  assert.deepEqual(plain(businessAssignmentPayload('employee', 'hr', ' 42 ')), {
    business_role: 'employee', department_code: 'hr', portal_user_id: 42,
  })
})
test('unassigned and manager allow null department and explicit ID clearing', () => {
  for (const role of ['unassigned', 'general_manager']) {
    assert.deepEqual(plain(businessAssignmentPayload(role, 'none', '')), {
      business_role: role, department_code: null, portal_user_id: null,
    })
  }
  assert.equal(businessAssignmentPayload('unassigned', 'product', '').department_code, null)
})
test('employee without department and invalid portal IDs fail before any request', () => {
  assert.throws(() => businessAssignmentPayload('employee', 'none', '1'), /所属部门/)
  for (const value of ['0', '-1', '1.5', '1e3', 'NaN', '9007199254740992']) {
    assert.throws(() => businessAssignmentPayload('employee', 'product', value), /正整数/)
  }
})
test('creation credentials obey backend username/email/password bounds', () => {
  const payload = userCredentialsPayload('employee', 'person@example.invalid', 'password-fixture')
  assert.equal(payload.username, 'employee')
  assert.equal(payload.email, 'person@example.invalid')
  for (const name of ['', 'white space', 'x'.repeat(65), 'control\u0000']) {
    assert.throws(() => userCredentialsPayload(name, 'person@example.invalid', 'password-fixture'), /用户名/)
  }
  assert.throws(() => userCredentialsPayload('employee', 'invalid', 'password-fixture'), /邮箱/)
  assert.throws(() => userCredentialsPayload('employee', 'person@example.invalid', 'short'), /密码/)
  assert.throws(() => userCredentialsPayload('employee', 'person@example.invalid', '密'.repeat(25)), /UTF-8/)
})

function apiSpy(response = { ok: true, status: 200, json: async () => ({ ok: true }) }) {
  const calls = []
  const api = compile('../src/lib/api.ts', {
    process: { env: {} },
    require: name => {
      assert.equal(name, './auth')
      return { getAccessToken: () => 'fixture-jwt' }
    },
    fetch: async (path, options) => { calls.push({ path, options }); return response },
  })
  return { calls, api }
}
test('actual PUT keeps legacy settings and uses explicit null assignment fields', async () => {
  const { api, calls } = apiSpy()
  const payload = { role: 'user', quota_tier: 'pro', runtime_mode: 'dedicated', is_active: false,
    ...businessAssignmentPayload('general_manager', 'none', '') }
  await api.updateUser('user-fixture', payload)
  assert.equal(calls[0].path, '/api/admin/users/user-fixture')
  assert.equal(calls[0].options.method, 'PUT')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer fixture-jwt')
  assert.deepEqual(JSON.parse(calls[0].options.body), payload)
})
test('creation uses authenticated admin API and never anonymous registration', async () => {
  const { api, calls } = apiSpy()
  await api.createUser({ ...userCredentialsPayload('employee', 'person@example.invalid', 'password-fixture'),
    ...businessAssignmentPayload('employee', 'engineering', '7'), role: 'user' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].path, '/api/admin/users')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer fixture-jwt')
  assert.equal(JSON.parse(calls[0].options.body).department_code, 'engineering')
})
test('409 conflicts and 422 field errors surface without response inputs or secrets', async () => {
  for (const [status, detail, expected] of [
    [409, 'portal_user_id is already mapped', /already mapped/],
    [422, [{ loc: ['body', 'password'], msg: 'Too short', input: 'must-not-display' }], /password: Too short/],
  ]) {
    const { api } = apiSpy({ ok: false, status, json: async () => ({ detail }) })
    await assert.rejects(api.createUser({}), error => expected.test(error.message) && !error.message.includes('must-not-display'))
  }
})
