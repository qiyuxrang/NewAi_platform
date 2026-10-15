import { readFileSync, existsSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')
const evidence = resolve(root, 'doc/implementation-evidence')
const baseline = JSON.parse(readFileSync(resolve(evidence, 'finance-phase-backend-baseline.json'), 'utf8').replace(/^\uFEFF/, ''))
const changesAllowed = new Set(['platform/app/enterprise.py', 'platform/app/db/models.py', 'platform/app/business_client.py', 'platform/tests/test_enterprise_identity.py'])
const additionsAllowed = new Set(['platform/alembic/versions/20261014_finance_department.py', 'platform/tests/test_finance_identity.py', 'platform/tests/test_finance_department_migration.py'])
const hash = path => createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex')
const missing = baseline.filter(item => !existsSync(resolve(root, item.path))).map(item => item.path)
const changed = baseline.filter(item => existsSync(resolve(root, item.path)) && hash(item.path).toLowerCase() !== item.sha256.toLowerCase())
const original = new Set(baseline.map(item => item.path))
const added = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', 'platform', 'services'], { cwd: root, encoding: 'utf8' }).trim().split(/\r?\n/).filter(path => path && !original.has(path))
const logo = JSON.parse(readFileSync(resolve(evidence, 'logo-baseline.json'), 'utf8'))
const result = { baselineFiles: baseline.length, unchangedFiles: baseline.length - changed.length - missing.length,
  approvedChanges: changed.filter(item => changesAllowed.has(item.path)).map(item => ({ ...item, currentSha256: hash(item.path) })),
  approvedAdditions: added.filter(path => additionsAllowed.has(path)), missing,
  unapprovedChanges: changed.filter(item => !changesAllowed.has(item.path)).map(item => item.path), unapprovedAdditions: added.filter(path => !additionsAllowed.has(path)),
  servicesUnchanged: !missing.some(path => path.startsWith('services/')) && !changed.some(item => item.path.startsWith('services/')) && !added.some(path => path.startsWith('services/')),
  logoUnchanged: hash(logo.path).toLowerCase() === logo.sha256.toLowerCase() }
result.status = !result.missing.length && !result.unapprovedChanges.length && !result.unapprovedAdditions.length && result.servicesUnchanged && result.logoUnchanged ? 'PASS' : 'FAIL'
writeFileSync(resolve(evidence, 'finance-backend-verification.json'), JSON.stringify(result, null, 2))
console.log(JSON.stringify(result, null, 2))
if (result.status !== 'PASS') process.exitCode = 1
