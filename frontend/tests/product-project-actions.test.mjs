import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const compile = async name => ts.transpileModule(await readFile(new URL(`../src/business/product/${name}`, import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const apiCode = await compile('product-api.ts'), listCode = await compile('ProductProjects.tsx');
const findAll = (element, predicate) => {
  if (!element || typeof element !== 'object') return [];
  return [...(predicate(element) ? [element] : []), ...[element.props?.children].flat(Infinity).flatMap(child => findAll(child, predicate))];
};
const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); };

test('project actions enforce permission, versions, failure retention, refresh, delete confirmation and pagination', async () => {
  class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
  let slots = [], index = 0, data, reloads = 0, confirmed = true;
  const calls = [], events = [], navigations = [], confirmations = [];
  const state = { useState: initial => {
    const slot = index++;
    const cell = slots[slot] ??= { value: initial };
    return [cell.value, next => { cell.value = typeof next === 'function' ? next(cell.value) : next; }];
  }, useRef: initial => { const slot = index++; return slots[slot] ??= { current: initial }; }, useId: () => 'project-menu', useEffect: () => {} };
  const api = {};
  vm.runInNewContext(apiCode, { exports: api, require: () => ({ apiRequest: (path, options) => new Promise((resolve, reject) => calls.push({ path, options, resolve, reject })) }) });
  const window = { location: { search: '', pathname: '/centers/product/projects' }, innerWidth: 1200, innerHeight: 800,
    confirm: message => { confirmations.push(message); return confirmed; }, dispatchEvent: event => events.push(event.type) };
  const exports = {};
  const workbench = { stageNames: {}, stateNames: {}, formatDate: () => '', goProduct: url => navigations.push(url), projectUrl: id => `/projects?task=${id}`,
    useProductOverview: () => ({ data, error: '', reload: () => reloads++ }) };
  vm.runInNewContext(listCode, { exports, window, URLSearchParams, Event, Error, require: name => {
    if (name === 'react') return state;
    if (name === 'react/jsx-runtime') return jsx;
    if (name === '../api') return { ApiError };
    if (name === './product-api') return api;
    if (name === './workbench-state') return workbench;
    if (name === 'lucide-react') return new Proxy({}, { get: (_, name) => name });
    return {};
  } });
  const owner = { id: 'owner /1', title: '测试项目', version: 7, can_manage: true, is_pinned: false, state: 'RUNNING' };
  const reviewer = { ...owner, id: 'reviewer', can_manage: false };
  data = { projects: [owner, reviewer], pagination: { page: 1, pages: 1, total: 2 }, metrics: {} };
  const render = () => { index = 0; const element = exports.default({}); return element.type(element.props); };
  const actions = tree => findAll(tree, node => typeof node.type === 'function' && !!node.props?.onAction);
  const alert = tree => findAll(tree, node => node.props?.role === 'alert')[0]?.props.children;

  let rows = actions(render());
  assert.equal(rows.length, 1, 'reviewer has no mutation controls');
  rows[0].props.onAction(reviewer, 'delete'); assert.equal(calls.length, 0, 'handler also rejects non-managers');
  rows[0].props.onAction(owner, 'pin'); rows[0].props.onAction(owner, 'pin');
  assert.equal(calls.length, 1, 'synchronous lock blocks repeated clicks before render');
  let request = calls.shift();
  assert.equal(request.path, '/api/product/tasks/owner%20%2F1/pin/');
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(JSON.parse(request.options.body), { expected_version: 7, pinned: true });
  assert.equal(actions(render())[0].props.busy, true);
  request.reject(new ApiError(503, '真实后端错误')); await settle();
  assert.equal(alert(render()), '真实后端错误');
  assert.equal(actions(render()).length, 1); assert.equal(reloads, 0, 'failed request preserves project');

  rows = actions(render()); rows[0].props.onAction({ ...owner, is_pinned: true }, 'pin');
  request = calls.shift(); assert.equal(JSON.parse(request.options.body).pinned, false);
  request.resolve({}); await settle();
  assert.equal(reloads, 1); assert.deepEqual(events, ['product:tasks-changed']);

  actions(render())[0].props.onAction(owner, 'pin'); calls.shift().reject(new ApiError(409, '项目版本已变化')); await settle();
  assert.equal(reloads, 2); assert.equal(alert(render()), '项目版本已变化');
  confirmed = false; actions(render())[0].props.onAction(owner, 'delete');
  assert.equal(calls.length, 0); assert.match(confirmations.at(-1), /结束.*后台任务.*列表移除/);
  confirmed = true; window.location.search = '?page=2'; slots = [];
  data = { ...data, projects: [owner], pagination: { page: 2, pages: 2, total: 21 } };
  actions(render())[0].props.onAction(owner, 'delete'); request = calls.shift();
  assert.equal(request.options.method, 'DELETE');
  assert.equal(request.path, '/api/product/tasks/owner%20%2F1/');
  assert.deepEqual(JSON.parse(request.options.body), { expected_version: 7 });
  request.resolve({}); await settle();
  assert.match(navigations.at(-1), /page=1/); assert.equal(events.length, 2);

  // Execute the production menu: native auto-popover supplies Escape/outside dismissal and top-layer placement.
  const row = actions(render())[0]; index = 0; slots = [];
  let menuTree = row.type(row.props);
  const popover = findAll(menuTree, node => node.props?.popover === 'auto')[0];
  assert.ok(popover); assert.equal(popover.props.role, 'group');
  const menuButtons = findAll(popover, node => node.type === 'button');
  assert.equal(menuButtons[0].props.autoFocus, true);
  const trigger = findAll(menuTree, node => node.props?.popoverTarget)[0];
  trigger.props.onClick({ currentTarget: { getBoundingClientRect: () => ({ right: 1198, bottom: 780, top: 756 }) } });
  index = 0; menuTree = row.type(row.props);
  const positioned = findAll(menuTree, node => node.props?.popover === 'auto')[0];
  assert.equal(positioned.props.style.left, 1044); assert.equal(positioned.props.style.top, 652);
  let hidden = false; positioned.props.ref.current = { hidePopover: () => { hidden = true; } };
  findAll(positioned, node => node.type === 'button')[0].props.onClick();
  assert.equal(hidden, true, 'action closes the menu before request'); calls.shift().resolve({}); await settle();
});
