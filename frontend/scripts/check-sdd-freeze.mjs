import { readFileSync, existsSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')
const evidence = resolve(root, 'doc/implementation-evidence')
const baseline = JSON.parse(readFileSync(resolve(evidence, 'backend-baseline.json'), 'utf8').replace(/^\uFEFF/, ''))
const hash = path => createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex')
const differences = baseline.filter(item => !existsSync(resolve(root, item.path)) || hash(item.path).toLowerCase() !== item.sha256.toLowerCase()).map(item => item.path)
const originalPaths = new Set(baseline.map(item => item.path))
const added = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', 'platform', 'services'], {cwd:root, encoding:'utf8'}).trim().split(/\r?\n/).filter(path => path && !originalPaths.has(path))
const logo = JSON.parse(readFileSync(resolve(evidence, 'logo-baseline.json'), 'utf8'))
const result = { protectedFiles: baseline.length, unchangedFiles: baseline.length - differences.length, differences, added, logoUnchanged: hash(logo.path).toLowerCase() === logo.sha256.toLowerCase() }
result.status = !differences.length && !added.length && result.logoUnchanged ? 'PASS' : 'FAIL'
writeFileSync(resolve(evidence, 'backend-verification.json'), JSON.stringify(result, null, 2))
console.log(JSON.stringify(result))
if (result.status !== 'PASS') process.exitCode = 1
