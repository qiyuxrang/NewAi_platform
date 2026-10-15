import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const source = await readFile(new URL('../src/components/Layout.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;

function visit(pathname, reducedMotion = false) {
  const effects = [];
  const animations = [];
  let cancelled = false;
  const exports = {};
  const component = () => null;
  vm.runInNewContext(compiled, {
    exports,
    require: name => name === 'react/jsx-runtime' ? jsx : name === 'react' ? {
      useEffect: effect => effects.push(effect),
      useRef: () => ({ current: { animate: (...args) => {
        animations.push(args); return { cancel: () => { cancelled = true; } };
      } } }),
    } : name === 'react-router-dom' ? { Outlet: component,
      useLocation: () => ({ pathname, search: '?task=current&tab=technical-solution' }),
    } : { default: component, NotificationProvider: component, useEnterprise: () => ({ user: { business_role: 'employee' } }) },
    window: { matchMedia: () => ({ matches: reducedMotion }) },
  });
  const tree = exports.default();
  const cleanups = effects.map(effect => effect());
  return { shell: tree.props.children, animations, cleanup: () => {
    cleanups.forEach(cleanup => cleanup?.()); return cancelled;
  } };
}

test('all routes keep the workbench stable without page fades', () => {
  for (const pathname of ['/departments/product', '/departments/product/documents', '/departments/product/knowledge', '/departments/product/outputs', '/departments/product/entry']) {
    const result = visit(pathname);
    assert.equal(result.animations.length, 0);
    assert.match(result.shell.props.className, /workbuddy-product/);
    assert.match(result.shell.props.children[1].props.children[1].props.className, /min-h-0.*wb-page/);
  }
  const ordinary = visit('/departments/productivity');
  assert.equal(ordinary.animations.length, 0);
  assert.doesNotMatch(ordinary.shell.props.className, /workbuddy-product/);
  assert.equal(ordinary.cleanup(), false);
  assert.equal(visit('/dashboard', true).animations.length, 0);
});
