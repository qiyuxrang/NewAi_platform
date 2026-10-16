import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

test('blueprint progress is visible without expanding details and elapsed time uses only a valid stage start', () => {
  const text = readFileSync(new URL('../src/business/product/ProjectStages.tsx', import.meta.url), 'utf8');
  const source = ts.createSourceFile('ProjectStages.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const declarations = ['workflowPhases', 'PhaseElapsed'].map(name => {
    const node = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === name);
    assert.ok(node, name);
    return ts.transpileModule(node.getText(source), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
    }).outputText;
  }).join('\n');
  let now = Date.parse('2026-10-15T08:02:05Z');
  let state;
  let tick;
  let cleanup;
  let intervals = 0;
  let clears = 0;
  class Clock extends Date { static now() { return now; } }
  const context = {
    Date: Clock, failureMessages: {},
    React: { createElement: (type, props, ...children) => ({ type, props, children }) },
    useState: initial => [state ??= initial(), value => { state = value; }],
    useEffect: effect => { cleanup = effect(); },
    window: { setInterval: (callback, delay) => { assert.equal(delay, 1000); intervals++; tick = callback; return 7; },
      clearInterval: timer => { assert.equal(timer, 7); clears++; } },
  };
  const { workflowPhases, PhaseElapsed } = vm.runInNewContext(`${declarations}; ({ workflowPhases, PhaseElapsed })`, context);
  const detail = '基础目录已保存，已完成 2/5 批；已细化 12/30 个章节节点';
  const task = { analysis_progress: { blueprint: { status: 'running', detail, started_at: '2026-10-15T08:00:00Z',
    updated_at: '2026-10-15T08:02:00Z', completed_count: 2, total_count: 5 } }, blueprint_review: { revision_count: 0, revision_limit: 3 } };
  const phase = workflowPhases(task, []).find(item => item.id === 'blueprint');
  assert.equal(phase.detail, detail);
  assert.equal(phase.startedAt, task.analysis_progress.blueprint.started_at);
  const start = text.indexOf('<section className="pd-compact-progress"');
  const end = text.indexOf('</section>', start);
  assert.ok(start >= 0 && end > start);
  const visible = text.slice(start, end);
  assert.match(visible, /runtimeDetail\(currentPhase\.detail\)/);
  assert.doesNotMatch(visible, /<details/);
  assert.match(visible, /aria-haspopup="dialog"[^>]*>查看处理详情/);
  assert.match(visible, /task\.state === 'RUNNING' && currentPhase\?\.status === 'running' && currentPhase\.startedAt && <PhaseElapsed key=\{currentPhase\.startedAt\}/);

  let timer = PhaseElapsed({ startedAt: phase.startedAt });
  assert.equal(timer.children.join(''), '本阶段已等待 2 分 5 秒');
  assert.equal(intervals, 1);
  now += 1000;
  tick();
  cleanup();
  assert.equal(clears, 1);
  timer = PhaseElapsed({ startedAt: phase.startedAt });
  assert.equal(timer.children.join(''), '本阶段已等待 2 分 6 秒');
  cleanup();
  const scheduled = intervals;
  for (const startedAt of ['', 'invalid', '2026-10-16T08:00:00Z']) {
    assert.equal(PhaseElapsed({ startedAt }), null);
  }
  assert.equal(intervals, scheduled, 'invalid or future starts must not run a timer');
  delete task.analysis_progress.blueprint.started_at;
  assert.equal(workflowPhases(task, []).find(item => item.id === 'blueprint').startedAt, undefined,
    'updated_at must never substitute for the phase start');
});
