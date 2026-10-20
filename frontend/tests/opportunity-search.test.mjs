import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const compile = async path => ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const component = await compile('../src/business/product/TenderOpportunities.tsx');
const api = await compile('../src/business/product/tender-api.ts');
const find = (tree, predicate) => {
  if (!tree || typeof tree !== 'object') return undefined;
  if (predicate(tree)) return tree;
  for (const child of [tree.props?.children].flat(Infinity)) {
    const match = find(child, predicate);
    if (match) return match;
  }
};
const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

function mount(search) {
  const requests = [], listeners = new Map(), slots = [], effects = [];
  let index = 0, historyIndex = 0;
  const locations = [`/departments/product/opportunities${search}`];
  const location = {};
  const navigate = url => Object.assign(location, { pathname: url.split('?')[0], search: url.includes('?') ? `?${url.split('?')[1]}` : '' });
  navigate(locations[0]);
  const window = {
    location, setTimeout: () => 1, clearTimeout: () => {},
    addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name),
    history: {
      replaceState: (_state, _unused, url) => { locations[historyIndex] = url; navigate(url); },
      pushState: (_state, _unused, url) => { locations.splice(++historyIndex, locations.length, url); navigate(url); },
      back: () => { if (historyIndex > 0) { navigate(locations[--historyIndex]); listeners.get('popstate')?.(); } },
      forward: () => { if (historyIndex + 1 < locations.length) { navigate(locations[++historyIndex]); listeners.get('popstate')?.(); } },
    },
  };
  const hooks = {
    useState: initial => {
      const slot = index++;
      if (!slots[slot]) slots[slot] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[slot].value, next => { slots[slot].value = typeof next === 'function' ? next(slots[slot].value) : next; }];
    },
    useRef: initial => slots[index++] ??= { current: initial },
    useCallback: fn => fn,
    useEffect: (fn, deps) => {
      const slot = index++, old = slots[slot];
      // Callback identities are stable in React; the test deliberately stubs useCallback.
      const values = deps.filter(value => typeof value !== 'function');
      if (!old || values.some((value, i) => value !== old.deps[i])) effects.push(() => {
        old?.cleanup?.(); slots[slot] = { deps: values, cleanup: fn() };
      });
    },
  };
  const apiExports = {};
  vm.runInNewContext(api, { exports: apiExports, URLSearchParams, require: () => ({
    apiRequest: async path => {
      requests.push(path);
      if (path.includes('opportunities/')) return {
        items: [{ id: 1, project_name: '测试商机', status: 'ACTIVE', budget: {}, publish_precision: 'unknown' }],
        total: 41, page: Number(new URL(path, 'https://local.invalid').searchParams.get('page') || 1), has_more: true,
      };
      if (path.endsWith('options/')) return {
        regions: ['陕西', '山西'], industries: [], notice_categories: [],
        publish_period: [{ value: 'week', label: '后台近7天' }, { value: 'today', label: '今天' }],
        deadline_period: [{ value: 'month', label: '后台未来30天' }],
        budget_band: [{ value: 'lt1m', label: '后台100万元以下' }],
      };
      if (path.endsWith('sources/')) return [];
      return { available: false, consumer_online: false };
    },
  }) });
  const exports = {};
  vm.runInNewContext(component, { exports, URLSearchParams, AbortController, window,
    document: { hidden: false, addEventListener: () => {}, removeEventListener: () => {} },
    require: name => name === 'react/jsx-runtime' ? jsx : name === 'react' ? hooks
      : name.includes('enterprise-context') ? { useEnterprise: () => ({ user: { business_role: 'employee' } }) }
        : name === 'lucide-react' ? new Proxy({}, { get: (_, key) => String(key) })
          : name === './tender-api' ? apiExports : {},
  });
  return {
    window, requests,
    render: () => { index = 0; return exports.default(); },
    flush: async () => { for (const run of effects.splice(0)) run(); await settle(); },
    listParams: () => new URL(requests.filter(path => path.includes('opportunities/')).at(-1), 'https://local.invalid').searchParams,
    dispose: () => { for (const slot of slots) slot?.cleanup?.(); },
  };
}

test('keyword and advanced filters reach the API, survive filter changes and synchronize with browser history', async () => {
  const app = mount('?q=%20系统%26软件%20&page=3&publish_period=week&deadline_period=month&budget_band=lt1m');
  const input = tree => find(tree, node => node.type === 'input' && node.props['aria-label'] === '搜索商机');
  const select = (tree, label) => find(find(tree, node => node.type === 'label' && node.props.children?.[0] === label), node => node.type === 'select');
  try {
    let tree = app.render(); await app.flush(); tree = app.render();
    assert.equal(input(tree).props.value, '系统&软件');
    assert.equal(input(tree).props.disabled, undefined);
    assert.equal(app.listParams().get('q'), '系统&软件');
    assert.equal(app.listParams().get('page'), '3');
    assert.equal(app.listParams().get('publish_period'), 'week');
    assert.equal(app.listParams().get('deadline_period'), 'month');
    assert.equal(app.listParams().get('budget_band'), 'lt1m');
    assert.equal(find(select(tree, '发布时间'), node => node.type === 'option' && node.props.value === 'week').props.children, '后台近7天');
    assert.equal(find(select(tree, '截止时间'), node => node.type === 'option' && node.props.value === 'month').props.children, '后台未来30天');
    assert.equal(find(select(tree, '预算'), node => node.type === 'option' && node.props.value === 'lt1m').props.children, '后台100万元以下');
    assert.equal(find(tree, node => node.props.id === 'tender-advanced-filters').props.hidden, false);
    const scrollRegion = find(tree, node => node.props.className === 'tender-table-wrap');
    assert.equal(scrollRegion.props.tabIndex, 0);
    assert.match(scrollRegion.props['aria-label'], /横向滚动/);

    select(tree, '地区').props.onChange({ target: { value: '陕西' } });
    tree = app.render(); await app.flush();
    assert.equal(app.listParams().get('q'), '系统&软件');
    assert.equal(app.listParams().get('region'), '陕西');
    assert.equal(app.listParams().get('page'), '1');
    assert.equal(new URLSearchParams(app.window.location.search).get('q'), '系统&软件');
    find(tree, node => node.props.entries && node.props.onChange).props.onChange('coal');
    tree = app.render(); await app.flush();
    assert.equal(app.listParams().get('industry'), 'coal');
    assert.equal(app.listParams().get('q'), '系统&软件');

    input(tree).props.onChange({ target: { value: '  榆林矿区  ' } });
    tree = app.render();
    assert.equal(app.listParams().get('q'), '系统&软件');
    let prevented = false;
    find(tree, node => node.type === 'form' && node.props.role === 'search').props.onSubmit({ preventDefault: () => { prevented = true; } });
    tree = app.render(); await app.flush();
    assert.equal(prevented, true);
    assert.equal(input(tree).props.value, '榆林矿区');
    assert.equal(app.listParams().get('q'), '榆林矿区');
    assert.equal(app.listParams().get('region'), '陕西');
    assert.equal(app.listParams().get('budget_band'), 'lt1m');

    app.window.history.back(); tree = app.render(); await app.flush();
    assert.equal(input(tree).props.value, '系统&软件');
    assert.equal(app.listParams().get('q'), '系统&软件');
    app.window.history.forward(); tree = app.render(); await app.flush();
    assert.equal(input(tree).props.value, '榆林矿区');
    select(tree, '发布时间').props.onChange({ target: { value: 'today' } });
    tree = app.render(); await app.flush();
    assert.equal(app.listParams().get('publish_period'), 'today');
    assert.equal(app.listParams().get('q'), '榆林矿区');

    find(tree, node => node.type === 'button' && node.props.children === '重置').props.onClick();
    tree = app.render(); await app.flush();
    assert.equal(input(tree).props.value, '');
    assert.equal(app.listParams().has('q'), false);
    assert.equal(app.listParams().has('region'), false);
    assert.equal(app.listParams().has('publish_period'), false);
    assert.equal(find(tree, node => node.props.id === 'tender-advanced-filters').props.hidden, true);
    assert.equal(new URLSearchParams(app.window.location.search).has('q'), false);
    app.window.history.back(); tree = app.render(); await app.flush();
    assert.equal(input(tree).props.value, '榆林矿区');
    assert.equal(select(tree, '发布时间').props.value, 'today');
  } finally { app.dispose(); }
});

test('unsupported advanced URL values are removed before requesting the list', async () => {
  const app = mount('?publish_period=invalid&deadline_period=invalid&budget_band=invalid');
  try {
    app.render(); await app.flush();
    for (const key of ['publish_period', 'deadline_period', 'budget_band']) {
      assert.equal(app.listParams().has(key), false);
      assert.equal(new URLSearchParams(app.window.location.search).has(key), false);
    }
  } finally { app.dispose(); }
});
