import { apiRequest, ApiError } from '../api'

export type FinanceRecord = Record<string, string | number | null> & { project_id: string; project_name: string }
export type FinanceMeta = { project_id: string; record_author_id: number | null; draft_actor_id: number | null; draft_revision: number; draft_checksum: string; deleted: boolean }
export type FinanceLedger = {
  department: 'finance'; state: 'draft' | 'submitted' | 'published'; revision: number; as_of: string | null; source_name: string
  records: FinanceRecord[]; record_meta: Record<string, FinanceMeta>; fields: Record<string, string>
  permissions: { can_edit: boolean; can_submit: boolean; can_publish: boolean }
}
export type FinanceSnapshot = { id: string; department: 'finance'; state: 'published'; revision: number; as_of: string | null; source_name: string; records: FinanceRecord[]; record_meta: Record<string, FinanceMeta> }
export type FinanceData = { ledger: FinanceLedger; published: FinanceSnapshot | null; publishedRevision: number | null }
export type FinanceEditor = { baseline: FinanceRecord; draft: FinanceRecord; projectId: string | null; revision: number }
export type FinanceSelection = { record_id: string; source_revision: number; source_checksum: string }
export const financeLedgerPath = '/api/business/ledgers/finance/'
export const entryText = (value: unknown) => value == null ? '' : String(value)
export const entryCell = (value: unknown) => entryText(value) === '' ? '—' : entryText(value)
export const sourceFinanceRecord = (row: FinanceRecord) => ['opening_receivable', 'receivable_balance', 'source_sheet'].some(key => entryText(row[key]).trim() !== '')
export function financeBookMode(ledger: FinanceLedger): 'source' | 'standard' | 'mixed' {
  const source = ledger.records.filter(sourceFinanceRecord).length
  return source === 0 ? 'standard' : source === ledger.records.length ? 'source' : 'mixed'
}
export const financeEditable = (ledger: FinanceLedger) => ledger.permissions.can_edit && ledger.state !== 'submitted'
export const financeDirty = (editor: FinanceEditor | null) => !!editor && JSON.stringify(editor.baseline) !== JSON.stringify(editor.draft)
const verifiedId = (id: unknown): id is number => typeof id === 'number' && Number.isSafeInteger(id) && id > 0

export function recordIdentity(ledger: FinanceLedger, row: FinanceRecord) {
  const entries = Object.entries(ledger.record_meta).filter(([, meta]) => meta && meta.project_id === row.project_id && meta.deleted === false)
  return entries.length === 1 ? { id: entries[0][0], meta: entries[0][1] } : null
}

export function ownsFinanceRecord(ledger: FinanceLedger, row: FinanceRecord, actor: number | null) {
  const identity = recordIdentity(ledger, row)
  return verifiedId(actor) && verifiedId(identity?.meta.record_author_id) && identity?.meta.record_author_id === actor
}

export function financeSelection(data: FinanceData, row: FinanceRecord, actor: number | null): FinanceSelection | null {
  const identity = recordIdentity(data.ledger, row)
  if (!financeEditable(data.ledger) || data.publishedRevision === null || !ownsFinanceRecord(data.ledger, row, actor)
    || !identity || identity.meta.draft_actor_id !== actor || !Number.isSafeInteger(identity.meta.draft_revision)
    || identity.meta.draft_revision < 1 || identity.meta.draft_revision > data.ledger.revision
    || !/^[0-9a-f]{64}$/.test(identity.meta.draft_checksum) || !/^[0-9a-f-]{36}$/i.test(identity.id)) return null
  const published = data.published?.record_meta[identity.id]
  if (published && published.deleted === false && published.draft_checksum === identity.meta.draft_checksum && published.draft_revision === identity.meta.draft_revision) return null
  return { record_id: identity.id, source_revision: identity.meta.draft_revision, source_checksum: identity.meta.draft_checksum }
}

export function newFinanceRecord(): FinanceRecord {
  return { project_id: `FN-${crypto.randomUUID()}`, project_name: '', client_name: '', contract_amount: '', received_amount: '', due_date: '', owner: '', current_status: '' }
}

export function financeValidation(row: FinanceRecord): string {
  const required = ['project_name', 'contract_amount', ...(!sourceFinanceRecord(row) ? ['received_amount'] : [])]
  const missing = required.filter(key => !entryText(row[key]).trim())
  const labels: Record<string, string> = { project_name: '项目名称', contract_amount: '合同金额', received_amount: '已收金额' }
  if (missing.length) return `请填写${missing.map(key => labels[key]).join('、')}；未知金额不能用 0 代替。`
  return ''
}

export function financeEditorValidation(editor: FinanceEditor, ledger: FinanceLedger): string {
  if (editor.projectId && sourceFinanceRecord(editor.baseline) !== sourceFinanceRecord(editor.draft)) return '已有记录的源表/标准口径不能在编辑中转换。请保留真实的原口径字段，不补 0 或伪造来源。'
  if (!editor.projectId && financeBookMode(ledger) === 'source' && !sourceFinanceRecord(editor.draft)) return '本台账为源表口径。新增须填写真实年初应收或应收结余；三者皆空时接口要求标准已收金额，但不能在本台账主动混入标准记录。未知值不可补 0 或伪造来源。'
  if (!editor.projectId && financeBookMode(ledger) === 'standard' && sourceFinanceRecord(editor.draft)) return '本台账为标准口径，不能主动新增源表口径记录。'
  return financeValidation(editor.draft)
}

export function reconcileFinanceEditor(editor: FinanceEditor, data: FinanceData, actor: number | null): FinanceEditor | null {
  const latest = editor.projectId ? data.ledger.records.find(row => row.project_id === editor.projectId) : editor.baseline
  if (!latest || !financeEditable(data.ledger) || editor.projectId && !ownsFinanceRecord(data.ledger, latest, actor)
    || !editor.projectId && data.ledger.records.some(row => row.project_id === editor.draft.project_id)) return null
  const changed = Object.fromEntries(Object.entries(editor.draft).filter(([key, value]) => value !== editor.baseline[key]))
  return { ...editor, baseline: { ...latest }, draft: { ...latest, ...changed }, revision: data.ledger.revision }
}

function validateLedger(value: FinanceLedger): FinanceLedger {
  if (value?.department !== 'finance' || !Array.isArray(value.records) || !value.record_meta || !value.fields
    || !Number.isSafeInteger(value.revision) || value.revision < 0 || !['draft', 'submitted', 'published'].includes(value.state)
    || !value.permissions || ['can_edit', 'can_submit', 'can_publish'].some(key => typeof value.permissions[key as keyof FinanceLedger['permissions']] !== 'boolean')) throw new Error('财务台账数据不完整，请重新读取。')
  return value
}

export async function loadFinanceEntry(signal?: AbortSignal): Promise<FinanceData> {
  const access = await apiRequest<{ departments: { department: string }[] }>('/api/business/ledgers/permissions/', { signal })
  if (!Array.isArray(access?.departments)) throw new Error('台账权限数据不完整，请重新读取。')
  if (!access.departments.some(item => item.department === 'finance')) throw new ApiError(403, '当前账号未获财务台账访问权限。')
  const ledger = validateLedger(await apiRequest<FinanceLedger>(financeLedgerPath, { signal }))
  const history = await apiRequest<{ department: string; versions: { id: string; revision: number; state: string }[] }>(financeLedgerPath + 'versions/', { signal })
  if (history?.department !== 'finance' || !Array.isArray(history.versions)
    || history.versions.some(item => !Number.isSafeInteger(item.revision) || item.revision < 1 || typeof item.id !== 'string')) throw new Error('财务版本信息不完整，请重新读取。')
  const latest = history.versions.filter(item => item.state === 'published').sort((a, b) => b.revision - a.revision)[0]
  if (history.versions.some(item => item.revision > ledger.revision)) throw new ApiError(409, '读取期间台账已更新，请重新读取并核对。')
  if (!latest) return { ledger, published: null, publishedRevision: history.versions.length >= 200 ? null : 0 }
  const published = await apiRequest<FinanceSnapshot>(financeLedgerPath + `versions/${encodeURIComponent(latest.id)}/`, { signal })
  if (published?.department !== 'finance' || published.state !== 'published' || published.id !== latest.id || published.revision !== latest.revision
    || !Array.isArray(published.records) || !published.record_meta) throw new Error('财务已发布快照不完整，请重新读取。')
  if (published.revision > ledger.revision) throw new ApiError(409, '读取期间台账已更新，请重新读取并核对。')
  return { ledger, published, publishedRevision: published.revision }
}

export async function saveFinanceRecord(editor: FinanceEditor, ledger: FinanceLedger): Promise<FinanceLedger> {
  const invalid = financeEditorValidation(editor, ledger)
  if (invalid) throw new Error(invalid)
  return validateLedger(await apiRequest<FinanceLedger>(financeLedgerPath + (editor.projectId ? `records/${encodeURIComponent(editor.projectId)}/` : 'records/'), {
    method: editor.projectId ? 'PUT' : 'POST', body: JSON.stringify({ expected_revision: editor.revision, record: editor.draft }),
  }))
}

export async function saveFinanceMetadata(revision: number, asOf: string): Promise<FinanceLedger> {
  return validateLedger(await apiRequest<FinanceLedger>(financeLedgerPath, { method: 'PATCH', body: JSON.stringify({ expected_revision: revision, as_of: asOf }) }))
}

export async function publishFinanceRecords(data: FinanceData, selections: FinanceSelection[], actor: number | null): Promise<FinanceLedger> {
  if (!selections.length || data.publishedRevision === null) throw new Error('请先核对已发布版本并选择本人草稿。')
  const eligible = data.ledger.records.map(row => financeSelection(data, row, actor)).filter(item => item !== null)
  if (new Set(selections.map(item => item.record_id)).size !== selections.length || selections.some(item => !eligible.some(current => current.record_id === item.record_id && current.source_revision === item.source_revision && current.source_checksum === item.source_checksum))) throw new Error('选定草稿归属或版本已变化，请重新读取并选择。')
  return validateLedger(await apiRequest<FinanceLedger>(financeLedgerPath + 'publish/', { method: 'POST', body: JSON.stringify({
    expected_revision: data.ledger.revision, expected_published_revision: data.publishedRevision, records: selections,
  }) }))
}

export function financeEntryError(reason: unknown): string {
  if (reason instanceof ApiError && reason.status === 401) return `${reason.message} 请重新登录或检查业务绑定。`
  return reason instanceof Error ? reason.message : '财务台账操作失败，请重新读取。'
}
