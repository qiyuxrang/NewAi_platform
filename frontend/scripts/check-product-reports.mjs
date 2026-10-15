import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { apiRequest, downloadBusinessFile } from '../src/business/api.ts'

const stages = readFileSync(new URL('../src/business/product/ProjectStages.tsx', import.meta.url), 'utf8')
const source = ts.createSourceFile('ProjectStages.tsx', stages, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const node = source.statements.find(item => ts.isFunctionDeclaration(item) && item.name?.text === 'workflowPhases')
assert.ok(node, 'Workflow state mapping must remain available for this runnable check.')
const messages = source.statements.find(item => ts.isVariableStatement(item) && item.declarationList.declarations.some(declaration => declaration.name.getText(source) === 'failureMessages'))
assert.ok(messages, 'Failure descriptions must be shared by workflow nodes and the task alert.')
const js = ts.transpileModule(`${messages.getText(source)}\n${node.getText(source)}`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
const phasesFor = vm.runInNewContext(`${js}; workflowPhases`)
const task = {
  state: 'RUNNING', output_families: ['technical-solution', 'feasibility'],
  blueprint_review: { revision_count: 0, revision_limit: 3 },
  analysis_progress: { documents: { status: 'completed' }, equipment: { status: 'completed' } },
  checkpoint: { analysis_progress: { writing_technical: { status: 'running', detail: 'saved chapter 4' } } },
}
let phases = phasesFor(task, [])
assert.equal(phases.find(item => item.id === 'documents').status, 'completed', 'Partial checkpoint must preserve background progress.')
assert.equal(phases.find(item => item.id === 'writing_technical').detail, 'saved chapter 4')
assert.equal(phases.some(item => item.id === 'presentation'), false, 'Two-report mode must finish independently of PPT.')
assert.equal(phases.some(item => item.id === 'web-search'), false, 'Unconfigured optional stages must not be fabricated.')
assert.equal(phases.find(item => item.id === 'diagrams_technical').status, 'pending', 'Missing Mermaid evidence cannot be complete.')
assert.equal(phasesFor({ ...task, state: 'COMPLETED' }, []).find(item => item.id === 'render_technical').status, 'pending', 'Task completion cannot manufacture a missing node record.')
assert.equal(phasesFor({ ...task, output_families: undefined }, []).some(item => item.id === 'presentation'), true, 'Legacy tasks retain the PPT path.')
const records = [{ family: 'technical-solution', current: true }, { family: 'feasibility', current: true }]
assert.equal(phasesFor(task, records).find(item => item.id === 'downloads').status, 'completed')
assert.equal(phasesFor(task, [records[0], { ...records[1], stale: true }]).find(item => item.id === 'downloads').status, 'pending', 'Stale files are not current deliverables.')
phases = phasesFor({ ...task, knowledge: { status: 'ready', ragflow_used: false }, analysis_progress: { knowledge: { status: 'completed' } } }, [])
assert.notEqual(phases.find(item => item.id === 'knowledge').status, 'completed', 'Knowledge retrieval requires actual retrieval evidence.')
const failedKnowledge = { ...task, state: 'WAITING_INPUT', checkpoint: undefined, analysis_progress: { knowledge: { status: 'failed', detail: '正在核对知识库授权并检索项目相关资料' } } }
for (const [code, reason] of Object.entries({ ragflow_scope_revoked: /知识库授权范围/, ragflow_forbidden: /账号权限/, ragflow_disabled: /尚未启用/, ragflow_unconfigured: /尚未正确配置/, ragflow_invalid_response: /协议或授权范围校验/, ragflow_unavailable: /暂时无法连接/ })) {
  const phase = phasesFor({ ...failedKnowledge, error_code: code }, []).find(item => item.id === 'knowledge')
  assert.equal(phase.status, 'failed')
  assert.match(phase.detail, reason, `${code} must describe the specific knowledge failure.`)
  assert.doesNotMatch(phase.detail, /正在/, 'A failed node must not retain its running description.')
}
assert.match(phasesFor({ ...failedKnowledge, error_code: 'unknown' }, []).find(item => item.id === 'knowledge').detail, /知识库检索失败/)
assert.equal(phasesFor({ ...failedKnowledge, analysis_progress: { knowledge: { status: 'running', detail: '正在检索' } } }, []).find(item => item.id === 'knowledge').detail, '正在检索')
const failedEquipment = phasesFor({ ...task, checkpoint: undefined, error_code: 'equipment_analysis_required', analysis_progress: { equipment: { status: 'failed', detail: '正在分析设备清单' } } }, []).find(item => item.id === 'equipment')
assert.match(failedEquipment.detail, /未解析出设备清单条目/)
assert.doesNotMatch(failedEquipment.detail, /正在/)
phases = phasesFor({ ...task, checkpoint: undefined, output_targets: { 'technical-solution': 50000 }, output_generation: { 'technical-solution': { actual_characters: 49999 } }, analysis_progress: { writing_technical: { status: 'completed' }, diagrams_technical: { status: 'failed', detail: 'render rejected' } } }, [])
const writingPhase = phases.find(item => item.id === 'writing_technical')
assert.equal(writingPhase.status, 'completed', 'A saved writing-step status is distinct from minimum-length and delivery checks.')
assert.equal(writingPhase.statusLabel, '正文已生成')
assert.match(writingPhase.detail, /已保存 49,999 字；最低 50,000 字/)
assert.match(writingPhase.detail, /篇幅待补，草稿可先下载/, 'Below-target content must remain visible even when the writing step is completed.')
assert.equal(phases.find(item => item.id === 'diagrams_technical').status, 'failed')
for (const status of ['failed', 'blocked']) {
  assert.equal(phasesFor({ ...task, checkpoint: undefined, analysis_progress: { writing_technical: { status } } }, []).find(item => item.id === 'writing_technical').status, status, 'Real backend failure and blocking statuses must be preserved.')
}
assert.equal(phasesFor({ ...task, state: 'COMPLETED', checkpoint: undefined, output_generation: { 'technical-solution': { actual_characters: 50000 } }, analysis_progress: {} }, []).find(item => item.id === 'writing_technical').status, 'pending', 'Task completion or saved character counts cannot invent a missing writing-step status.')

const apiSource = readFileSync(new URL('../src/business/product/product-api.ts', import.meta.url), 'utf8')
const compiledApi = ts.transpileModule(apiSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const apiExports = {}
vm.runInNewContext(compiledApi, { exports: apiExports, require: () => ({ apiRequest }), encodeURIComponent, JSON })
globalThis.localStorage = { getItem: key => key === 'openclaw_access_token' ? 'product-check-token' : null }
const calls = []
globalThis.fetch = async (url, options) => {
  calls.push({ url, options })
  return url.includes('/download/') ? new Response('report bytes', { headers: { 'Content-Disposition': 'attachment; filename="report.docx"' } }) : Response.json({ id: 'check-task' })
}
await apiExports.createTask({ title: 'check', input: {}, intake_mode: 'equipment_background', output_families: ['technical-solution', 'feasibility'] }, 'check-key', new AbortController().signal)
assert.deepEqual(JSON.parse(calls.at(-1).options.body).output_families, ['technical-solution', 'feasibility'])
let savedName
globalThis.document = { createElement: () => ({ set href(value) {}, set download(value) { savedName = value }, click() {} }) }
for (const path of [apiExports.artifactDownload('technical'), apiExports.draftDownload('feasibility'), apiExports.artifactHistoryDownload('history'), apiExports.sourceDownload('source')]) {
  await downloadBusinessFile(path, 'fallback.docx')
  assert.ok(calls.at(-1).url.startsWith('/api/enterprise/business/product/'))
  assert.equal(calls.at(-1).options.headers.get('Authorization'), 'Bearer product-check-token')
  assert.equal(calls.at(-1).options.credentials, 'omit')
  assert.equal(savedName, 'report.docx')
}
console.log('Product report mode, persisted nodes, knowledge failure reasons, stale output, minimum length, Mermaid failure, and authenticated download checks passed.')
