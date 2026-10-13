import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({ root, configFile: false, appType: 'custom',
  server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } });
after(() => server.close());
const { default: ProjectStages } = await server.ssrLoadModule('/src/business/product/ProjectStages.tsx');
const { blueprintChapters, manualBlueprint } = await server.ssrLoadModule('/src/business/product/product-api.ts');
globalThis.window = { location: { search: '?tab=blueprint', origin: 'http://localhost' } };

const chapter = (id, family, title = id) => ({ id, family, title, scope: `${title}设计范围`, source_ids: ['r1'] });
function fixture(chapters) {
  return { id: 'task-1', title: '隔离测试项目', version: 4, state: 'WAITING_REVIEW', stage: 'BLUEPRINT',
    input_version: 1, blueprint_version: 2, blueprint_approved: false,
    blueprint_review: { revision_count: 0, revision_limit: 3, revisions_remaining: 3 },
    output_targets: { 'technical-solution': 50000, feasibility: 70000 },
    input: { requirements: '项目要求', items: [], conditions: [] },
    blueprint: { id: 'blueprint-1', version: 2, sha256: 'blueprint-current', input_hash: 'input-current',
      payload: { purpose: '两类报告设计', audience: '项目评审人员', chapters, conditions: [], missing: [], conflicts: [] } },
    chapters: [], sources: [], reports: [], artifacts: [], approvals: [], issues: [], input_issues: [],
    blockers: {}, actions: [], owner_id: 1, reviewer_id: 1, error_code: '', impact: {} };
}
function render(task, tab = 'blueprint') {
  window.location.search = `?tab=${tab}`;
  return renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(ProjectStages,
    { task, outputs: [], history: null, outputsError: '', historyError: '', busy: false, conflict: false,
      disabled: () => false, onAction: async () => assert.fail('rendering must not change blueprint or approval'),
      onReload: () => {}, onUpload: async () => {} })));
}

test('dual report groups have separate budget denominators and one joint approval', () => {
  const task = fixture([chapter('t1', 'technical-solution'), chapter('f1', 'feasibility'),
    chapter('t2', 'technical-solution'), chapter('f2', 'feasibility'), chapter('f3', 'feasibility')]);
  const original = structuredClone(task);
  const html = render(task);
  const technical = html.match(/<section class="pd-chapter-family" aria-label="技术方案目录">([\s\S]*?)<\/section>/)[1];
  const feasibility = html.match(/<section class="pd-chapter-family" aria-label="可研报告目录">([\s\S]*?)<\/section>/)[1];
  assert.match(technical, /技术方案 · 2 个章节/);
  assert.equal((technical.match(/至少 25,000 字/g) || []).length, 2);
  assert.doesNotMatch(technical, /f1|f2|f3|23,334/);
  assert.match(feasibility, /可研报告 · 3 个章节/);
  assert.equal((feasibility.match(/至少 23,334 字/g) || []).length, 3);
  assert.doesNotMatch(feasibility, /t1|t2|25,000/);
  assert.equal((html.match(/批准蓝图并生成成果/g) || []).length, 1);
  assert.deepEqual(task, original);
});

test('legacy blueprint remains a shared directory without adding a family field', () => {
  const task = fixture([{ id: 'old-1', title: '旧目录1', scope: '原范围1', source_ids: ['r1'] },
    { id: 'old-2', title: '旧目录2', scope: '原范围2', source_ids: ['r1'] }]);
  const original = structuredClone(task.blueprint.payload);
  const html = render(task);
  assert.match(html, /沿用历史共享目录/);
  assert.match(html, /历史共享目录 · 2 个章节/);
  assert.match(html, /技术方案：至少 25,000 字/);
  assert.match(html, /可行性研究报告：至少 35,000 字/);
  assert.equal(blueprintChapters(task.blueprint.payload, 'technical-solution').length, 2);
  assert.equal(blueprintChapters(task.blueprint.payload, 'feasibility').length, 2);
  assert.deepEqual(task.blueprint.payload, original);
});

test('manual blueprint starts with distinct report directories, unique IDs and original conditions', () => {
  const input = { requirements: '供配电改造目标', conditions: ['现场参数需核对'] };
  const payload = manualBlueprint(input);
  const technical = blueprintChapters(payload, 'technical-solution');
  const feasibility = blueprintChapters(payload, 'feasibility');
  assert.equal(technical.length, 5);
  assert.equal(feasibility.length, 5);
  assert.equal(new Set(payload.chapters.map(chapter => chapter.id)).size, payload.chapters.length);
  assert.notDeepEqual(technical.map(chapter => chapter.title), feasibility.map(chapter => chapter.title));
  assert.ok(technical.every(chapter => chapter.family === 'technical-solution'));
  assert.ok(feasibility.every(chapter => chapter.family === 'feasibility'));
  assert.equal(payload.purpose, input.requirements);
  assert.deepEqual(payload.conditions, [{ text: input.conditions[0], type: 'human' }]);
  assert.equal(payload.template_version, 'frozen-original-v1');
  payload.conditions[0].text = '本地编辑';
  assert.equal(input.conditions[0], '现场参数需核对');
});

test('saved body with the wrong report family is excluded even when title and sources match', () => {
  const task = fixture([chapter('t1', 'technical-solution', '共同标题'), chapter('f1', 'feasibility', '共同标题')]);
  task.blueprint_approved = true;
  task.state = 'FAILED';
  task.stage = 'WRITING';
  const saved = (id, family, chapterId, text) => ({ id, family, version: 1,
    input_hash: 'input-current', blueprint_hash: 'blueprint-current',
    payload: { chapter_id: chapterId, title: '共同标题', paragraphs: [text], source_ids: ['r1'] } });
  task.chapters = [saved('valid-t', 'technical-solution', 't1', '有效技术正文'),
    saved('valid-f', 'feasibility', 'f1', '有效可研正文'),
    saved('wrong-t', 'technical-solution', 'f1', '串入技术报告的可研稿'),
    saved('wrong-f', 'feasibility', 't1', '串入可研报告的技术稿')];
  const original = structuredClone(task);
  const technical = render(task, 'technical-solution');
  assert.match(technical, /有效技术正文/);
  assert.doesNotMatch(technical, /有效可研正文|串入技术报告的可研稿|串入可研报告的技术稿/);
  const feasibility = render(task, 'feasibility');
  assert.match(feasibility, /有效可研正文/);
  assert.doesNotMatch(feasibility, /有效技术正文|串入技术报告的可研稿|串入可研报告的技术稿/);
  assert.deepEqual(task, original);
});
