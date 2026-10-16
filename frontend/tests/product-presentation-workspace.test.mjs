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
const { outputStatus } = await server.ssrLoadModule('/src/business/product/workbench-state.ts');
globalThis.window = { location: { search: '?tab=presentation', origin: 'http://localhost' } };

const plan = (style = 'engineering', style_label = '技术评审') => ({ style, style_label,
  selection_reason: '项目用途明确为技术评审，按后台规则匹配。', goal: 'department', goal_label: '部门评审',
  audience: '评审组', sources: [{ family: 'technical-solution', version: 3, sha256: 't' }, { family: 'feasibility', version: 2, sha256: 'f' }],
  pages: [{ page: 1, title: '项目依据与边界', type: 'summary', core_message: '设备数量以清单为准',
    items: ['建设范围已保存', '预算待确认'], speaker_notes: '保留报告中的缺口，不补造金额。', source_refs: ['technical-solution:P1', 'feasibility:P2'] }] });
const output = (family, extra = {}) => ({ id: `${family}-saved`, family, version: 2, current: true,
  stale: false, draft: true, approved: false, sha256: `${family}-hash`, ...extra });
const fixture = (extra = {}) => ({ id: 'ppt-task', title: '隔离 PPT 验收', version: 7, state: 'RUNNING', stage: 'RENDER',
  input_version: 1, blueprint_version: 2, blueprint_approved: true,
  blueprint_review: { revision_count: 0, revision_limit: 3, revisions_remaining: 3 },
  input: { requirements: '技术评审', items: [], conditions: [] }, blueprint: null,
  chapters: [], reports: [], artifacts: [], sources: [], approvals: [], issues: [], input_issues: [],
  blockers: {}, actions: ['queue_presentation'], owner_id: 1, reviewer_id: 1, error_code: '', impact: {}, ...extra });
function render(task, outputs = [], disabled = () => false) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(ProjectStages,
    { task, outputs, disabled, history: null, outputsError: '', historyError: '', busy: false, conflict: false,
      onAction: async () => assert.fail('reading plans must not submit generation or approval'), onReload: () => {}, onUpload: async () => {} })));
}

test('persisted plan is readable before export, with exact backend counts and no approval gate', () => {
  const task = fixture({ presentation_plan: plan(), analysis_progress: { presentation: {
    status: 'running', detail: '正在制作第 3 页', completed_count: 2, total_count: 8 } } });
  const original = structuredClone(task);
  const html = render(task, [output('technical-solution'), output('feasibility')]);
  assert.match(html, /汇报 PPT/);
  assert.match(html, /本次视觉风格<\/dt><dd>技术评审/);
  assert.match(html, /项目用途明确为技术评审/);
  assert.match(html, /逐页大纲 · 1 页/);
  assert.match(html, /第 1 页 · 项目依据与边界/);
  assert.match(html, /设备数量以清单为准|预算待确认|演讲备注/);
  assert.match(html, /技术方案 v3、可研报告 v2/);
  assert.match(html, /<progress max="8" value="2"[^>]*aria-label="PPT 逐页制作进度"/);
  assert.match(html, /已制作 2 \/ 8 页/);
  assert.equal((html.match(/>下载文件</g) || []).length, 2, 'both reports download independently while PPT runs');
  for (const style of ['auto', 'business', 'consulting', 'government', 'engineering', 'dark-tech', 'minimal']) {
    assert.match(html, new RegExp(`<option value="${style}"`));
  }
  assert.doesNotMatch(html, /确认风格|批准大纲|<img|%/);
  assert.deepEqual(task, original);
});

test('new attempt style is separated from saved file style and failures retain all downloads', () => {
  const saved = output('presentation', { presentation_plan: plan('business', '商务汇报') });
  const outputs = [output('technical-solution'), output('feasibility'), saved];
  const original = structuredClone(outputs);
  for (const status of ['running', 'failed', 'blocked']) {
    const html = render(fixture({ state: status === 'running' ? 'RUNNING' : 'FAILED', presentation_plan: plan(),
      analysis_progress: { presentation: { status, detail: '后台保存的本次制作状态', completed_count: 1, total_count: 8 } } }), outputs);
    assert.match(html, /可下载文件：第 2 版 · 商务汇报/);
    assert.match(html, /本次视觉风格<\/dt><dd>技术评审/);
    assert.match(html, /本次制作期间保留现有文件下载/);
    assert.equal((html.match(/>下载文件</g) || []).length, 4);
    assert.match(html, /按所选风格生成新 PPT 版本/);
    assert.doesNotMatch(html, /<img/);
  }
  assert.deepEqual(outputs, original);
});

test('legacy or invalid progress never invents page counts or an automatic style', () => {
  const legacy = render(fixture());
  assert.match(legacy, /等待后台保存 PPT 风格与逐页大纲/);
  assert.doesNotMatch(legacy, /本次视觉风格|PPT 逐页制作进度|已制作 \d|<img/);
  for (const counts of [{}, { completed_count: -1, total_count: 8 }, { completed_count: 9, total_count: 8 },
    { completed_count: 1, total_count: 0 }, { completed_count: 1.5, total_count: 8 }]) {
    const html = render(fixture({ analysis_progress: { presentation: { status: 'running', detail: '正在等待后台制作记录', ...counts } } }));
    assert.match(html, /正在等待后台制作记录/);
    assert.doesNotMatch(html, /PPT 逐页制作进度|已制作 \d/);
  }
});

test('server permission locks style regeneration while saved exports stay available', () => {
  const html = render(fixture({ state: 'COMPLETED' }), [output('presentation', { presentation_plan: plan() })], () => true);
  assert.match(html, /<select id="presentation-style" disabled=""/);
  assert.match(html, /<button type="submit" class="button secondary" disabled="">按所选风格生成新 PPT 版本/);
  assert.match(html, />下载文件</);
  assert.match(html, /逐页大纲 · 1 页/);
  const stale = render(fixture(), [output('presentation', { stale: true, presentation_plan: plan() })]);
  assert.doesNotMatch(stale, />下载文件<|本次视觉风格/);
});

test('finished retrieval is blocked when backend evidence is insufficient, while legacy snapshots remain readable', () => {
  const previous = window.location.search;
  window.location.search = '?tab=blueprint';
  try {
    const knowledge = { mode: 'ragflow_required', required: true, status: 'ready', ragflow_used: true,
      source_count: 1, ragflow_source_count: 0, web_source_count: 1, evidence_ready: false,
      detail: '设备与验收领域参考证据不足，暂不可生成正式蓝图',
      web_search: { status: 'blocked', source_count: 1, queries: [], missing_domains: ['验收'], detail: '联网公开参考仍缺少验收依据' } };
    const task = fixture({ knowledge, analysis_progress: { knowledge: { status: 'completed', detail: '检索请求执行完成' } },
      blueprint: { id: 'blueprint', version: 2, sha256: 'blueprint-hash', payload: {
        purpose: '项目目标', audience: '评审组', chapters: [], conditions: [], missing: [], conflicts: [] } } });
    const html = render(task);
    assert.match(html, /参考证据尚不足/);
    assert.match(html, /设备与验收领域参考证据不足/);
    assert.match(html, /知识库来源 0 项 · 联网公开参考 1 项/);
    assert.match(html, /联网公开资料只作参考，不作为当前项目事实/);
    assert.match(html, /<li[^>]*data-status="blocked"[^>]*>(?:(?!<li(?:\s|>))[\s\S])*?知识库检索/);
    assert.doesNotMatch(html, /本版本未执行知识库检索/);
    assert.match(render({ ...task, knowledge: { mode: 'ragflow_required', required: true,
      status: 'ready', ragflow_used: true, source_count: 2, detail: '旧版知识来源记录' } }), /知识库检索已完成/);
  } finally { window.location.search = previous; }
});

test('delivered outputs do not require legacy approval or expose a second review tail', () => {
  const outputs = ['technical-solution', 'feasibility', 'presentation'].map(family => output(family, {
    approved: false, draft: false, delivered: true, review_status: 'delivered',
    delivery_decision: { status: 'delivered', delivered: true, blocking_issues: [] } }));
  for (const tab of ['technical-solution', 'feasibility', 'presentation', 'history']) {
    window.location.search = `?tab=${tab}`;
    const html = render(fixture({ state: 'COMPLETED' }), outputs);
    assert.match(html, /已交付/);
    assert.doesNotMatch(html, /草稿 · 待完善|草稿待审核|审批状态|待批准|待审核/);
    assert.match(html, /下载文件|下载当前文件/);
    if (tab === 'presentation') assert.match(html, /<button type="submit" class="button secondary">按所选风格生成新 PPT 版本/);
  }
  window.location.search = '?tab=presentation';
  assert.equal(outputStatus({ current: true, delivered: true, approved: false }), '已交付');
  assert.equal(outputStatus({ current: true, review_status: 'delivered' }), '已交付');
  assert.equal(outputStatus({ current: true, delivered: false, approved: false }), '草稿 · 待完善');
  assert.equal(outputStatus({ current: false, delivered: true }), '历史 · 已过期');
});

test('incomplete delivery offers recovery and real blocking reasons while keeping all saved downloads', () => {
  window.location.search = '?tab=presentation';
  const outputs = [output('technical-solution', { delivered: true, draft: false, review_status: 'delivered' }),
    output('feasibility', { delivered: true, draft: false, review_status: 'delivered' }),
    output('presentation', { delivered: false, draft: true, review_status: 'pending_review',
      delivery_decision: { status: 'draft', delivered: false, blocking_issues: [{ code: 'presentation_quality_failed' },
        { code: 'diagram_pending' }] } })];
  const html = render(fixture({ state: 'WAITING_INPUT', error_code: 'delivery_incomplete', actions: ['retry'],
    retry_budget: { used: 1, limit: 3, remaining: 2 } }), outputs);
  assert.match(html, />继续生成</);
  assert.match(html, />查看问题</);
  assert.match(html, /草稿已保存，以下问题待修复/);
  assert.match(html, /<summary>查看全部 2 项交付问题<\/summary>/);
  // Browser acceptance expands the disclosure and verifies both blocking-code descriptions.
  assert.doesNotMatch(html, /PPT 质量检查尚未通过|图表仍需补生成/);
  assert.match(html, /草稿 · 待完善/);
  assert.equal((html.match(/>下载文件</g) || []).length, 4);
  assert.doesNotMatch(html, /待审核|批准成果|成果审批/);
});
