import assert from 'node:assert/strict'
import { ApiError, apiEventStream, apiRequest, businessPath, downloadBusinessFile } from '../src/business/api.ts'
import { selectResumeFiles, screeningCounts, uploadSequential } from '../src/business/hr/recruitment-api.ts'

globalThis.localStorage = { getItem: key => key === 'openclaw_access_token' ? 'check-platform-token' : null }
const calls = []
globalThis.fetch = async (url, options) => {
  calls.push({ url, options })
  if (url.includes('/conflict/')) return Response.json({ detail: '版本已变更，请刷新后重试。', code: 'version_conflict' }, { status: 409 })
  if (url.includes('/stream-error/')) return new Response('data: {"error":{"code":"scope_revoked","detail":"授权已撤销"}}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  if (url.includes('/stream/')) return new Response('data: {"delta":"实际引用回答"}\n\ndata: {"done":{"id":"real-session","version":2}}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  if (url.includes('/incomplete/')) return new Response('data: {"delta":"未完成"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  if (url.includes('/download/')) return new Response('original bytes', { headers: { 'Content-Disposition': "attachment; filename*=UTF-8''%E7%AE%80%E5%8E%86.txt" } })
  if (options.body instanceof FormData) return Response.json({ batch: { id: 'b1', version: Number(options.body.get('expected_version')) + 1 } })
  return Response.json({ ok: true })
}
assert.equal(businessPath('/api/hr/recruitment/requests/'), '/api/enterprise/business/hr/recruitment/requests/')
assert.throws(() => businessPath('https://external.invalid/api/hr/'))
assert.throws(() => businessPath('/api/hr/../auth/'))
assert.equal(businessPath('/api/models/routes/product_knowledge/options/'), '/api/enterprise/business/models/routes/product_knowledge/options/')
assert.throws(() => businessPath('/api/models/admin/'))
await apiRequest('/api/hr/recruitment/requests/intake/', { method: 'POST', body: JSON.stringify({ text: '实际招聘要求' }) })
assert.equal(calls.at(-1).options.headers.get('Authorization'), 'Bearer check-platform-token')
assert.equal(calls.at(-1).options.headers.get('Content-Type'), 'application/json')
await assert.rejects(apiRequest('/api/hr/conflict/'), error => error instanceof ApiError && error.status === 409 && error.code === 'version_conflict' && /版本已变更/.test(error.message))
const deltas = []
const completed = await apiEventStream('/api/product/knowledge/stream/', {}, new AbortController().signal, delta => deltas.push(delta))
assert.deepEqual(completed, { id: 'real-session', version: 2 })
assert.deepEqual(deltas, ['实际引用回答'])
assert.equal(calls.at(-1).options.headers.get('Accept'), 'text/event-stream')
await assert.rejects(apiEventStream('/api/product/knowledge/stream-error/', {}, new AbortController().signal, () => {}), error => error instanceof ApiError && error.status === 403 && error.code === 'scope_revoked')
await assert.rejects(apiEventStream('/api/product/knowledge/incomplete/', {}, new AbortController().signal, () => {}), error => error instanceof ApiError && error.code === 'incomplete_stream')

const files = Array.from({ length: 21 }, (_, index) => new File(['resume'], `resume-${index}.txt`))
const progress = []
const uploaded = await uploadSequential({ id: 'b1', version: 5 }, files, (batch, sent) => progress.push([batch.version, sent]))
assert.equal(uploaded.version, 7)
assert.deepEqual(progress, [[6, 20], [7, 21]])
for (const call of calls.filter(call => call.options.body instanceof FormData)) {
  assert.equal(call.options.headers.get('Authorization'), 'Bearer check-platform-token')
  assert.equal(call.options.headers.has('Content-Type'), false)
  assert.equal(call.options.credentials, 'omit')
}
assert.equal(selectResumeFiles([files[0]], [files[0]]).duplicates, 1)
assert.equal(selectResumeFiles([], [new File([], 'empty.txt')]).rejected.length, 1)
assert.deepEqual(screeningCounts({ completed: 3, status_counts: { pending: 2, queued: 1, running: 1 } }), { screened: 3, pending: 2, prescreened: 2 })

let saved
globalThis.document = { createElement: () => ({ set href(value) {}, set download(value) { saved = value }, click() {} }) }
await downloadBusinessFile('/api/hr/recruitment/resumes/r1/download/', 'fallback.txt')
assert.equal(saved, '简历.txt')
assert.equal(calls.at(-1).options.headers.get('Authorization'), 'Bearer check-platform-token')
console.log('Business proxy, conflict, upload version, authorized download, and SSE permission checks passed.')
