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
const { savedDraftDownload } = await server.ssrLoadModule('/src/business/product/product-api.ts');
const { projectListUrl } = await server.ssrLoadModule('/src/business/product/workbench-state.ts');
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
function render(task, props = {}) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(ProjectStages,
    { task, outputs: [], history: null, outputsError: '', historyError: '', busy: false,
      conflict: false, disabled: () => true, onAction: async () => {}, onReload: () => {}, onUpload: async () => {}, ...props })));
}

test('department return path is allowlisted and visual milestones retain real generation states', () => {
  const original = window.location.search;
  try {
    window.location.search = '?returnTo=' + encodeURIComponent('/departments/product');
    assert.equal(projectListUrl(), '/departments/product');
    for (const target of ['https://example.com', '//example.com', '/departments/product/../../settings']) {
      window.location.search = '?returnTo=' + encodeURIComponent(target);
      assert.equal(projectListUrl(), '/departments/product/documents?view=projects');
    }
    window.location.search = '?tab=technical-solution';
    const html = render(fixture({ output_families: ['technical-solution', 'feasibility'],
      analysis_progress: { writing_technical: { status: 'completed' }, writing_feasibility: { status: 'running' } } }));
    const steps = html.match(/<ol class="pd-visual-steps"[\s\S]*?<\/ol>/)[0];
    assert.match(steps, /data-status="running"[^>]*>[\s\S]*?文档生成/);
    assert.equal((steps.match(/<li /g) || []).length, 4);
    assert.doesNotMatch(steps, /PPT 生成/);
    assert.match(steps, /data-status="pending"[^>]*>[\s\S]*?成果交付/);
    const savedFiles = ['technical-solution', 'feasibility', 'presentation'].map(family => ({
      id: family, family, version: 1, current: true, stale: false, draft: true, approved: false,
    }));
    const deliveryStep = outputs => render(fixture(), { outputs }).match(/<ol class="pd-visual-steps"[\s\S]*?<\/ol>/)[0];
    assert.match(deliveryStep(savedFiles), /<li[^>]*data-status="waiting"[^>]*>(?:(?!<li)[\s\S])*?成果交付/);
    assert.match(deliveryStep(savedFiles.map(file => ({ ...file, delivered: true }))), /<li[^>]*data-status="completed"[^>]*>(?:(?!<li)[\s\S])*?成果交付/);
    assert.match(deliveryStep(savedFiles.map((file, index) => ({ ...file, delivered: index > 0 }))), /<li[^>]*data-status="waiting"[^>]*>(?:(?!<li)[\s\S])*?成果交付/);
    const failed = render(fixture({ analysis_progress: {
      diagrams_technical: { status: 'failed' }, presentation: { status: 'blocked' },
    } }), { outputs: savedFiles });
    const failedSteps = failed.match(/<ol class="pd-visual-steps"[\s\S]*?<\/ol>/)[0];
    assert.match(failedSteps, /<li[^>]*data-status="failed"[^>]*>(?:(?!<li)[\s\S])*?文档生成/);
    const pptBlocked = render(fixture({ analysis_progress: { presentation: { status: 'blocked' } } }));
    const pptSteps = pptBlocked.match(/<ol class="pd-visual-steps"[\s\S]*?<\/ol>/)[0];
    assert.match(pptSteps, /<li[^>]*data-status="blocked"[^>]*>(?:(?!<li)[\s\S])*?文档生成/);
    assert.match(failed, />下载文件</);
  } finally { window.location.search = original; }
});

test('current files remain downloadable during running or failed tasks with honest quality warnings', () => {
  const output = { id: 'output-1', family: 'technical-solution', version: 1, sha256: 'current-file',
    current: true, stale: false, approved: false, draft: true, quality_warnings: {
      issue_count: 1, issues: [{ code: 'quantity_mismatch', text: '设备数量需对照项目底稿核对' }],
      figures: { planned: 15, rendered: 13, pending: [{ figure_id: 'figure-14', error_code: 'diagram_render_failed' },
        { figure_id: 'figure-15', error_code: 'diagram_render_failed' }] },
      actual_characters: 40000, minimum_characters: 50000 } };
  for (const state of ['RUNNING', 'FAILED']) {
    const html = render(fixture({ state, analysis_progress: {
      writing_technical: { status: 'completed' }, diagrams_technical: { status: 'pending' } } }), { outputs: [output] });
    assert.match(html, />下载文件</);
    assert.match(html, /正文已生成/);
    assert.match(html, /草稿 · 待完善/);
    assert.match(html, /图表待补：已渲染 13 \/ 15 张，待补 2 张/);
    assert.match(html, /有 1 项质量问题需人工核对/);
    assert.match(html, /<summary>查看待核对问题<\/summary>/);
    // Browser acceptance expands this disclosure and checks the original issue text.
    assert.doesNotMatch(html, /设备数量需对照项目底稿核对/);
    assert.match(html, /低于当前最低 50,000 字/);
    assert.doesNotMatch(html, />已批准</);
    assert.doesNotMatch(render(fixture({ state }), { outputs: [{ ...output, stale: true }] }), />下载文件</);
    for (const family of ['feasibility', 'presentation']) {
      assert.match(render(fixture({ state }), { outputs: [{ ...output, family }] }), />下载文件</);
    }
  }
  const bounded = { ...output, quality_warnings: { ...output.quality_warnings,
    figures: { planned: 15, rendered: 2, pending_count: 13, pending: [{ figure_id: 'figure-3', error_code: 'diagram_render_failed' }] } } };
  assert.match(render(fixture(), { outputs: [bounded] }), /图表待补：已渲染 2 \/ 15 张，待补 13 张/);
});

test('quality warning survives before file generation and exhausted recovery remains disabled', () => {
  const html = render(fixture({ state: 'FAILED', error_code: 'diagram_render_failed',
    retry_budget: { used: 3, limit: 3, remaining: 0 }, quality_warnings: [{ family: 'technical-solution',
      issue_count: 1, issues: [{ code: 'quantity_mismatch' }] }] }), { disabled: () => false });
  assert.match(html, /有 1 项质量问题需人工核对/);
  assert.match(html, /<summary>查看待核对问题<\/summary>/);
  // The code-to-text mapping is checked after real browser disclosure expansion.
  assert.doesNotMatch(html, /设备数量与项目底稿不一致，需核对原始清单/);
  assert.match(html, /正文已保存，文件待生成/);
  assert.match(html, /disabled="" aria-describedby="retry-limit-note">从已保存进度重试/);
  assert.doesNotMatch(html, />下载文件</);
  assert.doesNotMatch(html, />重试生成</);
});

test('pending diagram repair uses the authorized original retry action without hiding existing files', () => {
  const output = { id: 'saved-output', family: 'technical-solution', version: 2, sha256: 'saved-file',
    current: true, stale: false, draft: true, approved: false,
    quality_warnings: { issue_count: 0, issues: [], figures: { planned: 15, rendered: 14,
      pending_count: 1, pending: [{ figure_id: 'figure-15', error_code: 'diagram_render_failed' }] } } };
  const task = fixture({ state: 'WAITING_REVIEW', stage: 'FINAL_REVIEW', actions: ['retry'],
    retry_budget: { used: 2, limit: 3, remaining: 1 } });
  const savedOutput = structuredClone(output);
  const props = { outputs: [output], disabled: () => false,
    onAction: async () => assert.fail('static rendering must not retry or overwrite saved outputs') };
  const html = render(task, props);
  assert.match(html, />补生成待补图表</);
  assert.match(html, />下载文件</);
  assert.match(html, /当前版本<\/dt><dd>v2/);
  assert.doesNotMatch(html, /当前任务需要处理/);
  assert.doesNotMatch(render({ ...task, actions: [] }, props), />补生成待补图表</);
  assert.doesNotMatch(render(task, { ...props, outputs: [{ ...output, stale: true }] }), />补生成待补图表</);
  const complete = { ...output, quality_warnings: { issue_count: 0, issues: [],
    figures: { planned: 15, rendered: 15, pending_count: 0, pending: [] } } };
  assert.doesNotMatch(render(task, { ...props, outputs: [complete] }), />补生成待补图表</);
  const exhausted = { ...task, retry_budget: { used: 3, limit: 3, remaining: 0 } };
  assert.match(render(exhausted, props), /disabled="" aria-describedby="diagram-repair-limit-note">补生成待补图表/);
  const noBudgetAction = render({ ...exhausted, actions: [] }, props);
  assert.match(noBudgetAction, /当前额度已用完/);
  assert.doesNotMatch(noBudgetAction, />补生成待补图表</);
  assert.deepEqual(props.outputs[0], savedOutput);
});

test('running and failed projects expose saved TXT draft alongside copied text', () => {
  for (const state of ['RUNNING', 'FAILED']) {
    const html = render(fixture({ state }));
    assert.match(html, /下载正文草稿 TXT/);
    assert.match(html, /已保存正文/);
    assert.match(html, /待配图、待排版等未完成提示/);
    assert.doesNotMatch(html, />下载文件</);
  }
});

test('one processing dialog owns the single node list and output errors have one recovery entry', () => {
  const html = render(fixture({ state: 'FAILED', error_code: 'diagram_render_failed',
    analysis_progress: { diagrams_technical: { status: 'failed', detail: '图表渲染暂时中断' } } }),
    { outputsError: '成果版本已变化，请刷新后重新读取。' });
  assert.equal((html.match(/<dialog /g) || []).length, 1);
  assert.equal((html.match(/aria-label="完整处理链路"/g) || []).length, 1);
  assert.equal((html.match(/成果版本已变化，请刷新后重新读取。/g) || []).length, 1);
  assert.equal((html.match(/>重新读取成果</g) || []).length, 1);
  assert.equal((html.match(/>查看处理详情</g) || []).length, 1);
  assert.doesNotMatch(html, /pd-task-details|pd-progress-milestones|>查看完整处理节点</);
  assert.match(html, /aria-controls="progress-panel-recovery"/);
  assert.match(html, /打开技术方案/);
});

test('persisted review failures identify the paused stage and explain the error on the main card', () => {
  const titles = { writing_editor: '总编复核', review_technical: '技术方案独立复核', review_feasibility: '可研报告独立复核' };
  const writing = { writing_technical: { status: 'completed' }, writing_feasibility: { status: 'completed' } };
  for (const [phase, title] of Object.entries(titles)) {
    const html = render(fixture({ state: 'WAITING_INPUT', error_code: 'invalid_model_output',
      analysis_progress: { ...writing, diagrams_technical: { status: 'running' },
        [phase]: { status: 'failed', detail: '处理已暂停：invalid_model_output。' },
        presentation: { status: 'waiting', detail: '等待两份报告文件完成后制作PPT' } } }), { disabled: () => false });
    const main = html.match(/<section class="pd-compact-progress"[\s\S]*?<\/section>/)[0];
    assert.match(main, new RegExp(`当前任务：${title}已暂停`));
    assert.match(main, /role="alert">模型返回结果未通过格式或正文内容校验，自动纠正后仍未通过。已保存现有章节，可从已保存进度重试。/);
    assert.match(main, />从已保存进度重试</);
    assert.doesNotMatch(main, /图表渲染已暂停|invalid_model_output/);
    const nodes = html.match(/<ol class="pd-progress-node-list"[\s\S]*?<\/ol>/)[0];
    assert.doesNotMatch(nodes, /invalid_model_output/);
    assert.match(nodes, new RegExp(`<li[^>]*data-status="failed"[^>]*>(?:(?!<li[ >])[\\s\\S])*?<h3>${title}</h3>`));
    for (const [other, otherTitle] of Object.entries(titles)) {
      if (other !== phase) assert.ok(!nodes.includes(otherTitle), 'unrecorded reviews must not be invented');
    }
    assert.match(html.match(/<ol class="pd-visual-steps"[\s\S]*?<\/ol>/)[0], /data-status="failed"[^>]*>(?:(?!<li)[\s\S])*?文档生成/);
  }
  const html = render(fixture({ analysis_progress: { ...writing, writing_editor: { status: 'pending' },
    review_technical: { status: 'completed' }, review_feasibility: { status: 'running' } } }));
  const nodes = html.match(/<ol class="pd-progress-node-list"[\s\S]*?<\/ol>/)[0];
  const ordered = ['技术方案正文', '可研报告正文', '总编复核', '技术方案独立复核', '技术方案图表渲染', '技术方案文档排版', '可研报告独立复核'];
  assert.deepEqual([...ordered].sort((a, b) => nodes.indexOf(a) - nodes.indexOf(b)), ordered);
  assert.match(nodes, /data-status="pending"[^>]*>(?:(?!<li)[\s\S])*?<h3>总编复核<\/h3><span>等待开始<\/span>/);
  assert.match(html, /当前任务：可研报告独立复核 · 处理中/);
  const recorded = { ...writing,
    review_feasibility: { status: 'failed', updated_at: '2026-10-16T04:08:00Z' },
    writing_editor: { status: 'failed', updated_at: '2026-10-16T06:20:00Z' } };
  assert.match(render(fixture({ state: 'WAITING_INPUT', error_code: 'invalid_model_output', analysis_progress: recorded })),
    /当前任务：总编复核已暂停/);
  const tied = { ...recorded, review_technical: { ...recorded.writing_editor } };
  assert.match(render(fixture({ state: 'WAITING_INPUT', analysis_progress: tied })), /当前任务：总编复核已暂停/);
  assert.match(render(fixture({ state: 'RUNNING', analysis_progress: { ...recorded,
    review_technical: { status: 'running', detail: '正在复核技术方案' } } })), /当前任务：技术方案独立复核 · 处理中/);
  const legacy = render(fixture({ state: 'WAITING_INPUT', error_code: 'invalid_model_output', analysis_progress: writing }));
  assert.match(legacy, /当前任务：任务已暂停/);
  assert.doesNotMatch(legacy, /总编复核|技术方案独立复核|可研报告独立复核|图表渲染已暂停/);
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
