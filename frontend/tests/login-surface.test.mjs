import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
  configFile: false, appType: 'custom', server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } });
after(() => server.close());
const { default: Login } = await server.ssrLoadModule('/src/pages/Login.tsx');
const { default: MarkdownContent } = await server.ssrLoadModule('/src/components/MarkdownContent.tsx');

test('enterprise login keeps native validation, accessible password control and original company branding', () => {
  const html = renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(Login)));
  assert.match(html, /src="\/company-logo\.png"/);
  assert.match(html, /<label for="auth-username">/);
  assert.match(html, /id="auth-username"[^>]*required=""[^>]*autoComplete="username"/);
  assert.match(html, /id="auth-password"[^>]*type="password"[^>]*required=""[^>]*autoComplete="current-password"/);
  assert.match(html, /type="button"[^>]*aria-label="显示密码"[^>]*aria-pressed="false"/);
  assert.match(html, /type="submit"[^>]*>登录<\/button>/);
  assert.match(html, /忘记密码？请联系管理员/);
});

test('assistant code blocks retain explicit foreground and theme-aware background', () => {
  const html = renderToStaticMarkup(React.createElement(MarkdownContent, { content: '```js\nconst value = 1;\n```' }));
  assert.match(html, /bg-dark-bg text-dark-text/);
  assert.match(html, /<pre[^>]*>[\s\S]*?const value = 1;/);
});
