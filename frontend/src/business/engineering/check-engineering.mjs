// Run with Node 24+: node frontend/src/business/engineering/check-engineering.mjs
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { stripTypeScriptTypes } from 'node:module'
import vm from 'node:vm'

const source = readFileSync(new URL('./EngineeringWorkspace.tsx', import.meta.url), 'utf8')
class ApiError extends Error { constructor(status) { super('request failed'); this.status = status } }
// Execute the actual parser and decision helpers; no duplicated implementation.
const helpers = source.slice(source.indexOf('const root ='), source.indexOf('interface KnowledgeStatus'))
const { readJob, nextStep } = vm.runInNewContext(
  `${stripTypeScriptTypes(helpers)}; ({ readJob, nextStep })`, { ApiError },
)
const preparation = readFileSync(new URL('./EngineeringPreparationPanel.tsx', import.meta.url), 'utf8')
const boundaries = preparation.slice(preparation.indexOf('function submissionMayHaveSucceeded'), preparation.indexOf("const root ="))
const { uploadIssue, submissionMayHaveSucceeded } = vm.runInNewContext(`${stripTypeScriptTypes(boundaries)}; ({ uploadIssue, submissionMayHaveSucceeded })`, { ApiError })
assert(preparation.includes('basis_sha256: prep.basis_sha256'), 'Cost execution must keep exact preparation basis confirmation.')
assert(source.includes('<EngineeringPreparationPanel'), 'The confirmed preparation flow must remain the upload entry.')
assert(!source.includes('const submit = async'), 'The workspace must not bypass preparation confirmation with direct creation.')
const raw = {
  id: 'job-1', status: 'completed', files: [{ name: '清单.xlsx' }],
  attempt_count: 2, max_attempts: 3, next_retry_at: '2026-10-20T10:00:00Z',
  result: { download_available: true, filename: '成本草稿.xlsx', sha256: 'abc', summary: { files: [{
    status: 'completed', validation_passed: true, preflight_issues: [], validation_issues: [], pending_confirmations: [],
    source_health: { audit: { 结论: '正常', 警告: [], 零价项: 0, 来源分布: { 历史价: 3 } } },
  }] } },
}
const parsed = readJob(raw)
assert.equal(parsed.needsReview, false)
assert.equal(parsed.downloadAvailable, true)
assert.equal(parsed.resultFilename, '成本草稿.xlsx')
assert.equal(parsed.resultHash, 'abc')
assert.equal(parsed.attemptCount, 2)
assert.equal(parsed.maxAttempts, 3)
assert.equal(parsed.summary[0].sourceHealth.sourceDistribution, '历史价：3')
for (const patch of [
  { validation_passed: false }, { validation_passed: undefined }, { preflight_issues: ['待核对'] },
  { validation_issues: ['合计不符'] }, { pending_confirmations: ['数量待确认'] },
  { source_health: { audit: { 结论: '可疑' } } }, { source_health: { audit: { 警告: ['零价'] } } },
]) {
  const value = structuredClone(raw)
  Object.assign(value.result.summary.files[0], patch)
  assert.equal(readJob(value).needsReview, true, `Unresolved evidence must require review: ${JSON.stringify(patch)}`)
}
assert.equal(readJob({ ...raw, result: {} }).needsReview, true, 'Missing summaries cannot imply verified quality.')
assert.equal(readJob({ ...raw, status: 'failed' }).needsReview, true)
assert.equal(readJob({ id: 'missing-status' }), null)
assert.equal(uploadIssue([{ name: '清单.XLSX', size: 1 }]), '')
for (const files of [[], [{ name: '清单.csv', size: 1 }], [{ name: '空.xlsx', size: 0 }], [{ name: '大.xlsx', size: 20 * 1024 * 1024 + 1 }], Array(3).fill({ name: '清单.xlsx', size: 1 })]) {
  assert.notEqual(uploadIssue(files), '', 'Invalid uploads must be rejected before sending.')
}
assert.equal(uploadIssue([{ name: '边界.xlsx', size: 20 * 1024 * 1024 }]), '')
assert.equal(submissionMayHaveSucceeded(new ApiError(400)), false)
assert.equal(submissionMayHaveSucceeded(new ApiError(403)), false)
assert.equal(submissionMayHaveSucceeded(new ApiError(503)), true)
assert.equal(submissionMayHaveSucceeded(new TypeError('Network disconnected')), true)
assert.equal(submissionMayHaveSucceeded(new Error('Malformed create response')), true)
assert.match(nextStep({ status: 'queued', error: { retryable: true } }), /后台将自动重试/)
assert.match(nextStep({ status: 'blocked', error: { code: 'worker_not_configured' } }), /会继续处理/)
assert.match(nextStep({ status: 'blocked', error: { code: 'permission_changed' } }), /权限或文件问题/)
assert.match(nextStep({ status: 'failed' }), /修正后重新上传/)
assert.match(nextStep({ status: 'completed', needsReview: true }), /待确认项/)
assert.match(nextStep({ status: 'completed', needsReview: false }), /仍需人工复核/)
console.log('Engineering upload bounds, result evidence, retry guidance, and uncertain submission checks passed.')
