import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { ApiError } from '../api.ts';
import { actionMessage, failureGuidance, mutate, outcomeUnknown, uploadSequential } from './recruitment-api.ts';

globalThis.localStorage = { getItem: key => key === 'openclaw_access_token' ? 'local-check-token' : null };
const calls = [];
globalThis.fetch = async (url, options) => {
  calls.push({ url, options });
  if (options.body instanceof FormData) {
    if (calls.length === 2) throw new TypeError('连接中断');
    return Response.json({ batch: { id: 'b1', version: 6 } });
  }
  return Response.json({ id: 'b1', version: 5 });
};
const files = Array.from({ length: 41 }, (_, index) => new File(['resume'], `${index}.txt`));
const acknowledged = [];
await assert.rejects(uploadSequential({ id: 'b1', version: 5 }, files, (batch, sent) => acknowledged.push([batch.version, sent])), TypeError);
assert.equal(calls.length, 2, 'unknown upload outcome must not continue to later chunks');
assert.deepEqual(acknowledged, [[6, 20]], 'only acknowledged chunks may clear local files');
assert.equal(calls[1].options.body.get('expected_version'), '6');
calls.length = 0;
await mutate('batches/', { jd_version_id: 'jd1' }, 'POST', { 'Idempotency-Key': 'same-attempt' });
await mutate('batches/', { jd_version_id: 'jd1' }, 'POST', { 'Idempotency-Key': 'same-attempt' });
assert(calls.every(call => call.options.headers.get('Idempotency-Key') === 'same-attempt'));
assert(outcomeUnknown(new TypeError('network')));
assert(outcomeUnknown(new ApiError(503, '服务异常')));
assert(!outcomeUnknown(new ApiError(409, '版本冲突')));
assert.match(actionMessage(new TypeError('network')), /先刷新记录核对状态/);
assert.match(actionMessage(new ApiError(409, '版本冲突')), /最新状态/);
assert.match(failureGuidance('attempt_limit'), /不再重试/);
assert.match(failureGuidance('invalid_encoding'), /UTF-8/);
assert.match(failureGuidance('unrecognized_code'), /unrecognized_code/);
for (const fileName of ['RecruitmentJobs.tsx', 'RecruitmentScreening.tsx', 'HrWorkspace.tsx']) {
  const source = await readFile(new URL(fileName, import.meta.url), 'utf8');
  const result = ts.transpileModule(source, { fileName, compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
  assert.deepEqual(result.diagnostics, [], `${fileName} must have valid TSX syntax`);
}
const jsx = (type, props, key) => ({ type, props, key });
async function compileComponent(fileName, modules, extra = {}) {
  const exports = {};
  const source = await readFile(new URL(fileName, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(compiled, { exports, require: name => name === 'react/jsx-runtime' ? { jsx, jsxs: jsx, Fragment: 'fragment' } : modules[name] || {}, AbortController, URLSearchParams, TypeError, ...extra });
  return exports.default;
}
let location = { pathname: '/departments/hr/resumes', search: '' };
const Workspace = await compileComponent('HrWorkspace.tsx', {
  react: { useEffect() {} }, 'react-router-dom': { useLocation: () => location },
  '../../components/enterprise-context': { useEnterprise: () => ({ user: null }) },
});
const initialKey = Workspace({ feature: 'resumes' }).key;
location = { ...location, search: '?batch=created-during-upload' };
assert.equal(Workspace({ feature: 'resumes' }).key, initialKey, 'Saving a batch URL must preserve the component subtree and its pending files/lock.');
location = { pathname: '/departments/hr/jobs', search: '' };
const jobKey = Workspace({ feature: 'jobs' }).key;
location = { ...location, search: '?task=created-during-generation' };
assert.equal(Workspace({ feature: 'jobs' }).key, jobKey, 'Saving a task URL must preserve the in-flight JD component.');
assert.notEqual(jobKey, initialKey, 'Changing HR features must still reset the subtree.');

const values = [], listeners = new Map();
let cursor = 0, effects = [], rejectIntake;
const Jobs = await compileComponent('RecruitmentJobs.tsx', {
  react: {
    useState(initial) { const i = cursor++; if (!(i in values)) values[i] = initial; return [values[i], value => { values[i] = typeof value === 'function' ? value(values[i]) : value; }]; },
    useRef(initial) { const i = cursor++; return values[i] ??= { current: initial }; },
    useEffect(effect) { effects.push(effect); },
  },
  'react-router-dom': { useSearchParams: () => [new URLSearchParams(), () => {}] },
  './recruitment-api': { mutate: () => new Promise((_resolve, reject) => { rejectIntake = reject; }), actionMessage, outcomeUnknown, message: error => error.message },
}, { window: { addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) } });
const renderJobs = () => { cursor = 0; effects = []; return Jobs({}); };
const find = (element, type) => !element || typeof element !== 'object' ? undefined : element.type === type ? element : (Array.isArray(element.props?.children) ? element.props.children : [element.props?.children]).map(child => find(child, type)).find(Boolean);
const guard = () => { listeners.clear(); effects.at(-1)(); const event = new Event('portal:navigation-guard', { cancelable: true }); listeners.get('portal:navigation-guard')?.(event); return event.defaultPrevented; };
let tree = renderJobs();
find(tree, 'textarea').props.onChange({ target: { value: '待核对的招聘说明' } });
tree = renderJobs(); assert(guard(), 'Ordinary unsaved text must still block leaving.');
find(tree, 'form').props.onSubmit({ preventDefault() {} });
tree = renderJobs(); assert(guard(), 'An active submission must still block leaving.');
rejectIntake(new TypeError('Lost intake response'));
for (let i = 0; i < 8; i++) await Promise.resolve();
tree = renderJobs(); assert.equal(guard(), false, 'An idle uncertain submission must allow navigation to history for reconciliation.');
const unload = new Event('beforeunload', { cancelable: true }); listeners.get('beforeunload')?.(unload);
assert(unload.defaultPrevented, 'A full browser unload must still warn about unsaved text.');
console.log('Recruitment partial-upload, idempotency, outcome guidance, stable URL subtree, uncertain-history navigation and TSX checks passed.');
