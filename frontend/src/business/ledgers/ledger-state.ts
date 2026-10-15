export type LedgerDepartment = 'presales' | 'engineering'
export type LedgerRecord = Record<string, string | number | null> & { project_id: string; project_name: string }
export type LedgerPermissions = { can_edit: boolean; can_submit: boolean; can_publish: boolean }
export type Ledger = {
  department: LedgerDepartment
  state: 'draft' | 'submitted' | 'published'
  revision: number
  as_of: string | null
  source_name: string
  records: LedgerRecord[]
  fields: Record<string, string>
  statuses: string[]
  permissions: LedgerPermissions
  updated_at: string | null
  updated_by: { id: number; name: string } | null
  last_return_reason: string
}
export type LedgerEditor = { baseline: LedgerRecord; draft: LedgerRecord; projectId: string | null; revision: number }

const presalesSourceFields = ['source_sheet', 'source_row', 'source_group', 'source_sequence', 'source_amount', 'amount_unit', 'follow_up_history', 'notes', 'annual_plan', 'expected_signing']
export const sourceLabels: Record<string, string> = { source_sheet: '来源工作表', source_row: '来源行', source_group: '来源分组', source_sequence: '来源序号', source_amount: '原始额度', amount_unit: '原表单位' }
export const entryTitles = { presales: '售前填报', engineering: '工程填报' }
export const cellText = (value: string | number | null | undefined) => value == null || value === '' ? '—' : String(value)
export const inputText = (value: string | number | null | undefined) => value == null ? '' : String(value)

export function isSourceRecord(record: LedgerRecord, department: LedgerDepartment): boolean {
  const fields = department === 'presales' ? presalesSourceFields : []
  return fields.some(key => inputText(record[key]).trim() !== '')
}

export function newLedgerRecord(department: LedgerDepartment): LedgerRecord {
  const base = { project_id: `${department === 'presales' ? 'PS' : 'EG'}-${crypto.randomUUID()}`, project_name: '', status: '', owner: '' }
  return department === 'engineering' ? { ...base, planned_end: '', progress: '' } : {
    ...base, amount: '', follow_up_date: '', project_progress: '', description: '', client_contact: '', project_type: '', maturity: '',
  }
}

export function requiredEntryFields(department: LedgerDepartment, record: LedgerRecord): string[] {
  return ['project_name', ...(department === 'engineering' ? ['status', 'progress'] : isSourceRecord(record, department) ? [] : ['status', 'amount'])]
}

export function missingEntryFields(department: LedgerDepartment, record: LedgerRecord): string[] {
  return requiredEntryFields(department, record).filter(key => inputText(record[key]).trim() === '')
}

export function ledgerActions(ledger: Ledger) {
  return {
    edit: ledger.permissions.can_edit && ledger.state !== 'submitted',
    submit: ledger.permissions.can_submit && ledger.state === 'draft' && ledger.records.length > 0 && !!ledger.as_of,
    publish: ledger.permissions.can_publish && ledger.state === 'submitted',
    return: ledger.permissions.can_publish && ledger.state === 'submitted',
  }
}

export const editorIsDirty = (editor: LedgerEditor | null) => !!editor && JSON.stringify(editor.baseline) !== JSON.stringify(editor.draft)

// Only after the user reviews a conflict: retain their changed fields, preserving other users' untouched fields.
export function reconcileEditor(editor: LedgerEditor, latest: Ledger): LedgerEditor | null {
  const baseline = editor.projectId ? latest.records.find(row => row.project_id === editor.projectId) : editor.baseline
  if (!baseline) return null
  const changes = Object.fromEntries(Object.entries(editor.draft).filter(([key, value]) => value !== editor.baseline[key]))
  return { ...editor, baseline: { ...baseline }, draft: { ...baseline, ...changes }, revision: latest.revision }
}
