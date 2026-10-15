import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const source = await readFile(new URL('../src/business/product/TenderOpportunities.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;

function render(role, stats) {
  let slot = 0;
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, URLSearchParams,
    window: { location: { search: '' } },
    require: name => name === 'react/jsx-runtime' ? jsx : name === 'react' ? {
      useState: initial => [slot++ === 2 ? { kind: 'ready', data: {
        stats, items: [], total: 999, page: 1, has_more: false,
      } } : typeof initial === 'function' ? initial() : initial, () => {}],
      useRef: initial => ({ current: initial }), useEffect: () => {}, useCallback: fn => fn,
    } : name.includes('enterprise-context') ? { useEnterprise: () => ({ user: { business_role: role } }) }
      : name === 'lucide-react' ? new Proxy({}, { get: (_, key) => String(key) })
        : {},
  });
  return exports.default();
}

function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return undefined;
  if (predicate(tree)) return tree;
  for (const child of [tree.props?.children].flat(Infinity)) {
    const match = find(child, predicate);
    if (match) return match;
  }
}
const chart = tree => find(tree, node => node.props?.className === 'tender-activity-chart');
const rows = tree => find(chart(tree), node => node.type === 'ul').props.children;

test('manager BI uses API statistics, preserves unknown values and stays absent for employees', () => {
  const stats = { total: 320, today_new: 12, latest_batch_new: null, closing_soon: 3 };
  const manager = render('general_manager', stats);
  assert.match(manager.props.className, /tender-manager/);
  const values = Array.from(rows(manager), row => row.props.children[2].props.children);
  assert.deepEqual(values, [12, '—', 3]);
  assert.equal(rows(manager)[0].props.children[1].props.children.props.style.width, '100%');
  assert.equal(rows(manager)[1].props.children[1].props.children, false);
  assert.equal(rows(manager)[2].props.children[1].props.children.props.style.width, '25%');
  const cards = find(manager, node => node.props?.className === 'tender-stats').props.children;
  assert.equal(cards.length, 4);
  assert.equal(cards[0].props.children[1].props.children[1].props.children, 320);
  assert.match(find(chart(manager), node => node.type === 'p').props.children, /指标可能重叠/);
  assert.equal(chart(render('employee', stats)), undefined);
  for (const missing of [undefined, null, {}, { today_new: null, latest_batch_new: null, closing_soon: null }, { today_new: NaN, closing_soon: -1 }]) {
    assert.equal(chart(render('general_manager', missing)), undefined);
  }
  const zeros = rows(render('general_manager', { today_new: 0, closing_soon: 0 }));
  assert.equal(zeros[0].props.children[2].props.children, 0);
  assert.equal(zeros[0].props.children[1].props.children.props.style.width, '0%');
});
