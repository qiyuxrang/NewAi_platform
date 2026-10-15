import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

test('project refresh preserves safe snapshots, rejects obsolete responses and highlights only changed files', async () => {
  // Isolate component hooks and network responses; no browser, backend or new test dependency.
  const original = { fetch: globalThis.fetch, window: globalThis.window, document: globalThis.document, localStorage: globalThis.localStorage };
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, appType: 'custom',
    server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' },
    plugins: [{ name: 'isolated-project-hooks', resolveId: id => id === '/@project-test-hooks' ? '\0project-test-hooks' : null,
      load: id => id === '\0project-test-hooks' ? `export { memo } from 'react'; ${['useState', 'useRef', 'useEffect', 'useMemo', 'useCallback'].map(name => `export const ${name} = (...args) => globalThis.projectTestHooks.${name}(...args);`).join(' ')}` : null,
      transform: (code, id) => /\/(DocumentWorkspace\.tsx|ProjectStages\.tsx|workbench-state\.ts)$/.test(id.replaceAll('\\', '/')) ? code.replaceAll('from "react"', 'from "/@project-test-hooks"') : null }] });
  const requests = [];
  const noop = () => {};
  let reducedMotion = false;
  globalThis.localStorage = { getItem: () => 'isolated-token' };
  globalThis.window = { location: { search: '?tab=technical-solution', origin: 'https://local.invalid' }, addEventListener: noop, removeEventListener: noop,
    setInterval: () => 1, clearInterval: noop, matchMedia: () => ({ matches: reducedMotion }) };
  globalThis.document = { hidden: false, addEventListener: noop, removeEventListener: noop };
  globalThis.fetch = (path, options) => new Promise(resolve => requests.push({ path, options, resolve }));
  class Hooks {
    slots = []; index = 0; effects = [];
    useState = initial => { const index = this.index++; this.slots[index] ??= { value: typeof initial === 'function' ? initial() : initial }; return [this.slots[index].value, next => { this.slots[index].value = typeof next === 'function' ? next(this.slots[index].value) : next; }]; };
    useRef = initial => { const index = this.index++; return this.slots[index] ??= { current: initial }; };
    useMemo = (fn, deps) => { const index = this.index++; const old = this.slots[index]; if (!old || deps.some((value, i) => value !== old.deps[i])) this.slots[index] = { value: fn(), deps }; return this.slots[index].value; };
    useCallback = (fn, deps) => this.useMemo(() => fn, deps);
    useEffect = (fn, deps) => { const index = this.index++; const old = this.slots[index]; if (!old || deps.some((value, i) => value !== old.deps[i])) { this.effects.push(() => { old?.cleanup?.(); this.slots[index] = { deps, cleanup: fn() }; }); } };
    render(component, props) { this.index = 0; globalThis.projectTestHooks = this; return component(props); }
    flush() { for (const effect of this.effects.splice(0)) effect(); }
    dispose() { for (const slot of this.slots) slot?.cleanup?.(); }
  }
  const find = (element, predicate) => {
    if (!element || typeof element !== 'object') return undefined;
    if (predicate(element)) return element;
    for (const child of [element.props?.children].flat(Infinity)) { const match = find(child, predicate); if (match) return match; }
  };
  const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
  const answer = async (suffix, data, status = 200) => {
    const index = requests.findIndex(request => request.path.endsWith(suffix)); assert.notEqual(index, -1, suffix);
    const [request] = requests.splice(index, 1); request.resolve(Response.json(data, { status })); await settle(); return request;
  };
  try {
    const { TaskEditor } = await server.ssrLoadModule('/src/business/product/DocumentWorkspace.tsx');
    const { default: ProjectStages } = await server.ssrLoadModule('/src/business/product/ProjectStages.tsx');
    const { stableTaskSnapshot, outputBasisChanged } = await server.ssrLoadModule('/src/business/product/project-refresh.ts');
    const task = { id: 'task-1', title: '测试项目', version: 1, state: 'WAITING_INPUT', stage: 'FINAL_REVIEW', input_version: 1, blueprint_version: 1,
      input: { project: '测试', requirements: '', background: '', conditions: [], items: [] }, blueprint: { id: 'b1', sha256: 'bhash', payload: { chapters: [], conditions: [], missing: [], conflicts: [] } }, blueprint_approved: true,
      chapters: [], artifacts: [], reports: [], sources: [], input_issues: [], blockers: {}, actions: [], blueprint_review: { revision_count: 0, revision_limit: 3 }, error_code: '' };
    const output = { id: 'file-1', family: 'technical-solution', version: 1, sha256: 'hash-1', current: true, stale: false, quality_warnings: { issue_count: 813, issues: [{ code: 'unsupported_number', text: '完整待核对问题' }] }, delivery_decision: { blocking_issues: Array.from({ length: 813 }, () => ({ code: 'unsupported_number' })) } };
    const history = { task_version: 1, timeline: [{ id: '1', event: 'revision' }] };
    const same = stableTaskSnapshot(task, structuredClone(task)); assert.equal(same, task);
    const progressed = stableTaskSnapshot(task, { ...structuredClone(task), version: 2 }); assert.equal(progressed.chapters, task.chapters); assert.equal(progressed.input, task.input);
    assert.equal(outputBasisChanged(task, progressed), false);
    for (const change of [{ input_version: 2 }, { blueprint_version: 2 }, { blueprint_approved: false }, { input: { ...task.input, project: '变更' } }, { blueprint: { ...task.blueprint, sha256: 'new' } }]) assert.equal(outputBasisChanged(task, { ...task, ...change }), true);
    const hooks = new Hooks(); const fatal = [];
    const props = { id: task.id, requestedArtifact: '', deepLinked: true, business: true, onFatal: text => fatal.push(text) };
    const render = () => { const tree = hooks.render(TaskEditor, props); hooks.flush(); return find(tree, node => node.type === ProjectStages)?.props; };
    render(); await answer('/task-1/', task);
    await answer('/outputs/', { task_version: 1, outputs: [output] }); await answer('/history/', history);
    let view = render(); assert.equal(view.outputs.length, 1); const firstOutputs = view.outputs; const firstHistory = view.history;
    view.onReload(); await settle(); await answer('/task-1/', structuredClone(task));
    view = render(); assert.equal(view.outputs, firstOutputs); assert.equal(view.history, firstHistory, 'refresh must not blank history');
    await answer('/outputs/', { task_version: 1, outputs: [output] }); await answer('/history/', history);
    view = render(); assert.equal(view.outputs, firstOutputs, 'unchanged outputs keep identity');
    view.onReload(); await settle(); await answer('/task-1/', task);
    await answer('/outputs/', { detail: '暂不可用' }, 503); await answer('/history/', { detail: '暂不可用' }, 503);
    view = render(); assert.equal(view.outputs, firstOutputs); assert.equal(view.history, firstHistory); assert.ok(view.outputsError);
    view.onReload(); await settle(); await answer('/task-1/', { ...task, version: 2 });
    await answer('/outputs/', { task_version: 1, outputs: [output] }); await answer('/history/', { ...history, task_version: 2 });
    view = render(); assert.equal(view.outputs.length, 0); assert.match(view.outputsError, /版本已变化/);
    view.onReload(); await settle(); await answer('/task-1/', task); await answer('/outputs/', { task_version: 1, outputs: [output] }); await answer('/history/', history);
    view = render(); view.onReload(); await settle(); await answer('/task-1/', { ...task, version: 2, input_version: 2 });
    view = render(); assert.equal(view.outputs.length, 0, 'changed input invalidates cached downloads immediately');
    const obsolete = requests.find(request => request.path.endsWith('/outputs/'));
    view.onReload(); await settle(); await answer('/task-1/', { ...task, version: 3, input_version: 2 });
    assert.equal(obsolete.options.signal.aborted, true);
    requests.splice(requests.indexOf(obsolete), 1); obsolete.resolve(Response.json({ task_version: 2, outputs: [output] })); await settle();
    assert.equal(render().outputs.length, 0, 'obsolete response cannot restore downloads');
    await answer('/outputs/', { detail: '权限撤销' }, 403);
    assert.equal(render(), undefined); assert.match(fatal.at(-1), /隐藏/); hooks.dispose();
    for (const status of [401, 404]) {
      const deniedHooks = new Hooks(); deniedHooks.render(TaskEditor, props); deniedHooks.flush(); await answer('/task-1/', { detail: '不可访问' }, status);
      assert.equal(find(deniedHooks.render(TaskEditor, props), node => node.type === ProjectStages), undefined); deniedHooks.dispose();
    }

    const stageHooks = new Hooks(); const animations = [];
    const stageProps = { ...view, task, outputsLoaded: true, outputs: [output], history, outputsError: '', historyError: '', disabled: () => true, busy: false, conflict: false, onAction: noop, onReload: noop, onUpload: noop };
    const renderStage = changes => { const tree = stageHooks.render(ProjectStages, { ...stageProps, ...changes }); find(tree, node => node.type === 'aside').props.ref.current = { querySelector: selector => ({ animate: (frames, timing) => { animations.push({ selector, frames, timing }); return { cancel: noop }; } }) }; stageHooks.flush(); return tree; };
    renderStage({ outputs: [], outputsLoaded: false }); renderStage(); assert.equal(animations.length, 0, 'initial files do not flash');
    renderStage(); assert.equal(animations.length, 0, 'same files do not flash');
    const changed = { ...output, sha256: 'hash-2' }; renderStage({ outputs: [changed] });
    assert.equal(animations.length, 1); assert.match(animations[0].selector, /technical-solution/); assert.equal(animations[0].timing.iterations, 2);
    renderStage({ outputs: [changed] }); assert.equal(animations.length, 1, 'repeated polling does not flash');
    const latest = { ...changed, sha256: 'hash-3' };
    reducedMotion = true; renderStage({ outputs: [latest] }); assert.equal(animations.length, 1);
    reducedMotion = false; const tree = renderStage({ outputs: [latest, { ...output, id: 'file-2', family: 'feasibility' }] });
    assert.equal(animations.length, 2); assert.match(animations[1].selector, /feasibility/); stageHooks.dispose();
    const workspace = find(tree, node => node.type?.name === 'ArtifactWorkspace'); const contentHooks = new Hooks();
    let content = contentHooks.render(workspace.type, workspace.props);
    assert.equal(find(content, node => node.type === 'ul'), undefined, '813 blocking items remain unmounted until expanded');
    const details = find(content, node => node.type === 'details' && !!node.props.onToggle);
    assert.match(JSON.stringify(details.props.children[0].props.children), /813/);
    details.props.onToggle({ currentTarget: { open: true } }); content = contentHooks.render(workspace.type, workspace.props);
    assert.equal(find(content, node => node.type === 'ul').props.children.length, 813, 'expanded list includes every issue');
    const warning = find(content, node => !!node.props?.warnings); const warningHooks = new Hooks();
    let warningTree = warningHooks.render(warning.type.type, warning.props); assert.equal(find(warningTree, node => node.type === 'ul'), undefined);
    find(warningTree, node => node.type === 'details').props.onToggle({ currentTarget: { open: true } });
    warningTree = warningHooks.render(warning.type.type, warning.props); assert.equal(find(warningTree, node => node.type === 'li').props.children, '完整待核对问题');
  } finally { Object.assign(globalThis, original); delete globalThis.projectTestHooks; await server.close(); }
});
