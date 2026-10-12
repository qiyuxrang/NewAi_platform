import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({ root, configFile: false, appType: 'custom',
  server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } });
after(() => server.close());
const { default: ProjectStages } = await server.ssrLoadModule('/src/business/product/ProjectStages.tsx');
const { savedDraftDownload } = await server.ssrLoadModule('/src/business/product/product-api.ts');
globalThis.window = { location: { search: '?tab=technical-solution', origin: 'http://localhost' } };

function fixture(extra = {}) {
  return { id: 'task-1', title: '测试项目', version: 4, state: 'RUNNING', stage: 'WRITING',
    input_version: 1, blueprint_version: 2, blueprint_approved: true,
    blueprint_review: { revision_count: 0, revision_limit: 3, revisions_remaining: 3 },
    input: { requirements: '项目要求', items: [], conditions: [] },
    blueprint: { id: 'blueprint-1', version: 2, sha256: 'blueprint-current', input_hash: 'input-current',
      payload: { chapters: [{ id: 'overview', title: '项目概述', source_ids: ['1'] }] } },
    chapters: [{ id: 'chapter-1', family: 'technical-solution', version: 1,
      input_hash: 'input-current', blueprint_hash: 'blueprint-current',
      payload: { chapter_id: 'overview', title: '项目概述', paragraphs: ['已保存正文'], source_ids: ['1'] } }],
    sources: [], reports: [], artifacts: [], approvals: [], issues: [], input_issues: [],
    blockers: {}, actions: [], owner_id: 1, reviewer_id: null, error_code: '', impact: {}, ...extra };
}
function render(task) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(ProjectStages,
    { task, outputs: [], history: null, outputsError: '', historyError: '', busy: false,
      conflict: false, disabled: () => true, onAction: async () => {}, onReload: () => {}, onUpload: async () => {} })));
}

test('running and failed projects expose saved TXT draft alongside copied text', () => {
  for (const state of ['RUNNING', 'FAILED']) {
    const html = render(fixture({ state }));
    assert.match(html, /下载正文草稿 TXT/);
    assert.match(html, /已保存正文/);
    assert.match(html, /待配图、待排版与未审批/);
    assert.doesNotMatch(html, />下载文件</);
  }
});

test('draft API URL carries family and input/blueprint versions', () => {
  const url = savedDraftDownload(fixture(), 'technical-solution');
  assert.equal(url, '/api/product/tasks/task-1/saved-draft/download/?family=technical-solution&input_version=1&blueprint_version=2');
});

test('automatic recovery and cached steps have readable labels without internal hashes', () => {
  const privateKey = 'writing:technical-solution:0123456789abcdef';
  const html = render(fixture({ state: 'QUEUED', retry_after: '2026-10-12T10:30:00Z', error_code: 'timeout',
    generation_steps: [{ key: privateKey, status: 'completed', attempts: 1, error_code: '', retry_after: null },
      { key: 'diagram:technical-solution:internal-figure-id', status: 'retry_wait', attempts: 2,
        error_code: 'timeout', retry_after: '2026-10-12T10:30:00Z' }] }));
  assert.match(html, /临时故障/);
  assert.match(html, /自动恢复/);
  assert.match(html, /已缓存，可恢复时复用/);
  assert.match(html, /技术方案正文生成/);
  assert.match(html, /技术方案图表渲染/);
  assert.doesNotMatch(html, /当前任务需要处理/);
  assert.doesNotMatch(html, /0123456789abcdef|internal-figure-id/);
});

test('legacy payload without step fields renders normally; stale and unapproved text is hidden', () => {
  assert.match(render(fixture()), /下载正文草稿 TXT/);
  assert.doesNotMatch(render(fixture()), /查看已保存步骤与恢复状态/);
  assert.doesNotMatch(render(fixture({ blueprint_approved: false })), /下载正文草稿 TXT|已保存正文：/);
  const task = fixture();
  task.chapters[0].blueprint_hash = 'old-blueprint';
  assert.doesNotMatch(render(task), /下载正文草稿 TXT/);
});
