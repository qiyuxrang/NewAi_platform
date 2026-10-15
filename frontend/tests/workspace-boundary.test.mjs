import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as react from 'react';
import * as jsx from 'react/jsx-runtime';

const exports = {};
const source = readFileSync(new URL('../src/business/WorkspaceBoundary.tsx', import.meta.url), 'utf8');
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText, { exports, require: name => name === 'react/jsx-runtime' ? jsx : react });

test('feature changes preserve the boundary and recover errors only when the reset key changes', () => {
  const child = jsx.jsx('div', { children: 'Project content' });
  const before = exports.default({ children: child, resetKey: 'product/outputs' });
  const after = exports.default({ children: child, resetKey: 'product/documents' });
  assert.equal(before.key, null);
  assert.equal(after.key, null);
  assert.equal(before.type, after.type);
  assert.equal(after.props.children.type, react.Suspense);
  assert.equal(after.props.children.props.children, child);

  const boundary = new before.type(before.props);
  let resets = 0;
  boundary.setState = next => { resets++; boundary.state = { ...boundary.state, ...next }; };
  boundary.props = after.props;
  boundary.componentDidUpdate(before.props);
  assert.equal(resets, 0, 'healthy navigation must not update error state');
  assert.equal(boundary.render(), after.props.children);

  boundary.state = before.type.getDerivedStateFromError(new Error('broken child'));
  boundary.componentDidUpdate(after.props);
  assert.equal(boundary.state.failed, true, 'the same route keeps the error visible');
  assert.equal(boundary.render().props.role, 'alert');
  assert.equal(resets, 0);

  boundary.componentDidUpdate(before.props);
  assert.equal(boundary.state.failed, false, 'a new feature recovers from the old error');
  assert.equal(resets, 1);
  assert.equal(boundary.render(), after.props.children);
});
