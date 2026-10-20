// Run: node frontend/src/business/product/check-product-workflow.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

class ApiError extends Error { constructor(status) { super(`HTTP ${status}`); this.status = status; } }
const read = file => readFileSync(new URL(file, import.meta.url), 'utf8');
const compile = (source, context) => {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, { exports, ...context });
  return exports;
};
const stagesSource = ts.createSourceFile('ProjectStages.tsx', read('./ProjectStages.tsx'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const nextStepNode = stagesSource.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'taskNextStep');
const nextStep = vm.runInNewContext(`${ts.transpileModule(nextStepNode.getText(stagesSource), {}).outputText}; taskNextStep`);
assert.match(nextStep({ state: 'QUEUED' }), /无需再次提交/);
assert.match(nextStep({ state: 'RUNNING' }), /可离开后返回/);
assert.match(nextStep({ state: 'WAITING_REVIEW', stage: 'BLUEPRINT' }), /确认依据/);
assert.match(nextStep({ state: 'FAILED' }), /补齐资料、授权或服务条件/);
assert.match(nextStep({ state: 'COMPLETED' }), /草稿或批准状态/);
const stateSource = ts.createSourceFile('state.ts', read('./workbench-state.ts'), ts.ScriptTarget.Latest, true);
const stateNamesNode = stateSource.statements.find(node => ts.isVariableStatement(node) && node.declarationList.declarations.some(item => item.name.getText(stateSource) === 'stateNames'));
const stateNames = compile(stateNamesNode.getText(stateSource), {}).stateNames;
for (const [state, label] of Object.entries({ FAILED: '处理失败', QUEUED: '排队中', RUNNING: '生成中', WAITING_REVIEW: '待确认', WAITING_INPUT: '待处理', COMPLETED: '已完成' })) assert.equal(stateNames[state], label);

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const task = { id: 'task-1', title: '测试项目', version: 1, state: 'RUNNING', artifacts: [], sources: [], input: { project: '', requirements: '', items: [], background: '', conditions: [] }, actions: ['queue_blueprint', 'add_source'], blockers: {}, input_issues: [] };
const output = { id: 'output-1', family: 'technical-solution', current: true, stale: false };
const refreshHelpers = compile(read('./project-refresh.ts'), {});
const uploadEvidence = compile(read('./product-api.ts'), { require: () => ({ ApiError }), crypto, Uint8Array });
function editorHarness(getTask = async () => task) {
  const values = [], timers = [], fatals = [], confirmations = [];
  let cursor = 0, effects = [], writes = 0, outputReads = 0;
  const react = {
    useCallback(callback) { return callback; },
    useState(initial) { const i = cursor++; if (!(i in values)) values[i] = initial; return [values[i], value => { values[i] = typeof value === 'function' ? value(values[i]) : value; }]; },
    useRef(initial) { const i = cursor++; return values[i] ??= { current: initial }; },
    useEffect(effect) { effects.push(effect); },
  };
  const api = { getTask, confirmSourceUpload: (...args) => { const confirmation = uploadEvidence.confirmSourceUpload(...args); confirmations.push(confirmation); return confirmation; }, getDraftOutputs: async () => { outputReads++; return { task_version: task.version, outputs: [output] }; }, getTaskHistory: async () => ({ task_version: task.version, timeline: [] }), updateTask: async () => { writes++; } };
  const jsx = (type, props) => ({ type, props });
  const module = compile(read('./DocumentWorkspace.tsx'), {
    require: name => name === 'react' ? react : name === 'react/jsx-runtime' ? { jsx, jsxs: jsx, Fragment: 'fragment' } : name === '../api' ? { ApiError } : name === './product-api' ? api : name === './ProjectStages' ? { default: 'ProjectStages' } : name === './project-refresh' ? refreshHelpers : { useUnsavedWarning() {} },
    AbortController, TypeError, SyntaxError, Date,
    window: { setTimeout: callback => { timers.push(callback); return timers.length; }, clearTimeout() {} },
  });
  const findStage = element => !element || typeof element !== 'object' ? undefined : element.type === 'ProjectStages' ? element.props : Array.isArray(element.props?.children) ? element.props.children.map(findStage).find(Boolean) : findStage(element.props?.children);
  return {
    api, timers, fatals, waitForUploads: () => Promise.all(confirmations),
    render() { cursor = 0; effects = []; const tree = module.TaskEditor({ id: task.id, requestedArtifact: '', deepLinked: true, business: true, onFatal: message => fatals.push(message) }); return { tree, stage: findStage(tree), effects }; },
    writes: () => writes, outputReads: () => outputReads,
  };
}
const editor = editorHarness();
let view = editor.render();
view.effects[0](); view.effects[1](); await flush();
view = editor.render();
assert.equal(view.stage.outputs.length, 1);
assert.equal(editor.outputReads(), 1);
view.effects[2](); editor.timers.at(-1)(); await flush();
view = editor.render();
assert.equal(editor.outputReads(), 1, 'An unchanged task poll must not refetch or clear output evidence.');
assert.equal(view.stage.outputs[0].id, output.id);

let release;
editor.api.updateTask = () => { editor.api.writeCount = (editor.api.writeCount || 0) + 1; return new Promise(resolve => { release = resolve; }); };
const first = view.stage.onAction('queue/', {});
await view.stage.onAction('queue/', {});
assert.equal(editor.api.writeCount, 1, 'Rapid duplicate clicks must result in one mutation.');
release(); await first;
editor.api.updateTask = async () => { throw new TypeError('Connection lost'); };
view = editor.render(); await view.stage.onAction('queue/', {});
view = editor.render();
assert.equal(view.stage.disabled('queue_blueprint'), true, 'An uncertain write must require status reconciliation.');
view.stage.onReload(); await flush();
view = editor.render();
assert.equal(view.stage.disabled('queue_blueprint'), false, 'A successful refresh restores allowed actions.');
editor.api.getTask = async () => { throw new TypeError('Offline'); };
view.effects[2](); editor.timers.at(-1)(); await flush();
view = editor.render();
assert.equal(view.stage.outputs[0].id, output.id, 'A transient read failure must preserve last confirmed evidence.');
assert.equal(view.stage.disabled('queue_blueprint'), true);
assert.equal(editor.fatals.length, 0);

for (const [error, fatal] of [[new TypeError('Offline'), false], [new ApiError(404), true]]) {
  const initial = editorHarness(async () => { throw error; });
  const initialView = initial.render(); initialView.effects[0](); initialView.effects[1](); await flush();
  assert.equal(initial.fatals.length > 0, fatal, 'Transient failures must not masquerade as missing or unauthorized tasks.');
}

assert(!read('./DocumentWorkspace.tsx').includes('composer={<form'), 'The SDD review workspace must not regain the retired follow-up composer.');

const bytes = new TextEncoder().encode('equipment evidence');
const hash = Buffer.from(await crypto.subtle.digest('SHA-256', bytes)).toString('hex');
const file = new File([bytes], 'equipment.txt');
const saved = { id: 'new-source', original_name: file.name, size: file.size, sha256: hash, purpose: 'equipment' };
for (const purpose of ['equipment', undefined]) {
  let uploadPosts = 0;
  const lostApi = compile(read('./product-api.ts'), {
    require: () => ({ ApiError, apiRequest: async (_url, options) => { if (options.method === 'POST') { uploadPosts++; throw new TypeError('POST committed but response lost'); } throw new TypeError('Immediate recovery GET is offline'); } }),
    FormData, crypto, Uint8Array, TypeError, encodeURIComponent, JSON,
  });
  const recovered = editorHarness(); recovered.api.uploadSource = lostApi.uploadSource;
  let current = recovered.render(); current.effects[0](); current.effects[1](); await flush(); current = recovered.render();
  await current.stage.onUpload(file, purpose);
  current = recovered.render(); assert.equal(current.stage.disabled('add_source'), true);
  current.stage.onReload(); await flush(); await recovered.waitForUploads(); await flush();
  current = recovered.render(); assert.equal(current.stage.disabled('add_source'), true, 'A successful GET without matching upload evidence must keep writes blocked.');
  recovered.api.getTask = async () => ({ ...task, version: 2, sources: [{ ...saved, purpose: purpose || '' }] });
  current.stage.onReload(); await flush(); await recovered.waitForUploads(); await flush();
  current = recovered.render();
  assert.equal(current.stage.disabled('add_source'), false, 'Only an exact new source snapshot may resolve the uncertain upload.');
  assert.equal(current.stage.confirmedUpload, file, 'Confirmed single-file selection must be cleared by the workspace.');
  current.stage.onReload(); await flush();
  assert.equal(uploadPosts, 1, 'A later refresh must never repeat the committed upload.');
}
let source = saved, postCount = 0, readCount = 0, failure = new TypeError('Lost upload response'), readFailure;
const api = compile(read('./product-api.ts'), {
  require: () => ({ ApiError, apiRequest: async (_url, options) => { if (options.method === 'POST') { postCount++; throw failure; } readCount++; if (readFailure) throw readFailure; return { ...task, sources: [source] }; } }),
  FormData, crypto, Uint8Array, TypeError, encodeURIComponent, JSON,
});
const signal = new AbortController().signal;
assert.equal((await api.uploadSource(task.id, file, 1, signal, 'equipment', [])).sources[0].id, saved.id);
assert.equal(postCount, 1, 'Reconciling a lost upload response must never repeat the POST.');
for (const mismatch of [{ ...saved, sha256: 'wrong' }, { ...saved, purpose: 'background' }, { ...saved, size: 1 }]) {
  source = mismatch;
  await assert.rejects(api.uploadSource(task.id, file, 1, signal, 'equipment', []), TypeError);
}
source = saved;
await assert.rejects(api.uploadSource(task.id, file, 1, signal, 'equipment', [saved]), TypeError, 'An older source cannot prove that a new upload committed.');
failure = new ApiError(403); const before = readCount;
await assert.rejects(api.uploadSource(task.id, file, 1, signal, 'equipment', []), ApiError);
assert.equal(readCount, before, 'Denied uploads must not attempt a recovery read.');
failure = new TypeError('Lost upload response'); readFailure = new ApiError(403);
await assert.rejects(api.uploadSource(task.id, file, 1, signal, 'equipment', []), error => error.status === 403, 'Revoked access during upload reconciliation must remain visible as a permission error.');
console.log('PASS: real state guidance, stable evidence, duplicate-submit lock, uncertain-write reconciliation, transient versus denied reads, and upload hash/size/purpose/new-source checks.');
