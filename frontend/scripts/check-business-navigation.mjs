import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import Module, { createRequire } from 'node:module'
import ts from 'typescript'

const sourceFile = fileURLToPath(new URL('../src/business/workspace-navigation.ts', import.meta.url))
const compiled = ts.transpileModule(readFileSync(sourceFile, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
const checkedModule = new Module(sourceFile)
checkedModule.filename = sourceFile
checkedModule.paths = Module._nodeModulePaths(fileURLToPath(new URL('..', import.meta.url)))
checkedModule.require = createRequire(sourceFile)
checkedModule._compile(compiled, sourceFile)
const { workspaceHref } = checkedModule.exports
assert.equal(workspaceHref('/centers/product/new'), '/departments/product/documents')
assert.equal(workspaceHref('/centers/product/projects'), '/departments/product/documents?view=projects')
assert.equal(workspaceHref('/centers/product/projects?task=real&tab=history'), '/departments/product/documents?task=real&tab=history')
assert.equal(workspaceHref('/centers/product/outputs?page=2'), '/departments/product/outputs?page=2')
assert.equal(workspaceHref('/centers/product/opportunities'), '/departments/product/opportunities')
assert.equal(workspaceHref('/centers/product/knowledge'), '/departments/product/knowledge')
assert.equal(workspaceHref('/centers/hr/job?task=r1'), '/departments/hr/jobs?task=r1')
assert.equal(workspaceHref('/centers/hr/results?batch=b1'), '/departments/hr/resumes?batch=b1&results=1')
assert.equal(workspaceHref('/centers/hr/history'), '/departments/hr/history')
assert.equal(workspaceHref('/centers/cost'), '/departments/engineering/estimate')
assert.equal(workspaceHref('https://original-source.example/notice'), 'https://original-source.example/notice')

// Invoke the actual private URL updater without rendering or issuing business requests.
const tenderFile = fileURLToPath(new URL('../src/business/product/TenderOpportunities.tsx', import.meta.url))
const tenderCompiled = ts.transpileModule(readFileSync(tenderFile, 'utf8') + '\nexport { updateUrl };', {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText
const tenderModule = new Module(tenderFile)
tenderModule.filename = tenderFile
const tenderRequire = createRequire(tenderFile)
tenderModule.require = name => name.startsWith('.') ? {} : tenderRequire(name)
tenderModule._compile(tenderCompiled, tenderFile)
const previousWindow = globalThis.window
const changes = []
try {
  globalThis.window = {
    location: { pathname: '/departments/product/opportunities', search: '?q=legacy' },
    history: { pushState: (...args) => changes.push(args), replaceState: (...args) => changes.push(args) },
  }
  tenderModule.exports.updateUrl({ region: '陕西' }, 2, 17)
  assert.equal(changes.length, 1)
  const changedUrl = new URL(changes[0][2], 'http://localhost')
  assert.equal(changedUrl.pathname, '/departments/product/opportunities')
  assert.equal(changedUrl.searchParams.get('region'), '陕西')
  assert.equal(changedUrl.searchParams.get('notice'), '17')
  assert.equal(changedUrl.searchParams.get('page'), '2')
  assert.equal(changedUrl.searchParams.has('q'), false)
  globalThis.window.location.pathname = '/departments/hr/history'
  tenderModule.exports.updateUrl({ notice_category: 'procurement' }, 1)
  assert.equal(changes.length, 1, 'Other pages must not inherit opportunity URL parameters')
} finally {
  if (previousWindow === undefined) delete globalThis.window
  else globalThis.window = previousWindow
}
console.log('Reused business navigation checks passed.')
