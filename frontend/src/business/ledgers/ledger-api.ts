import { apiRequest, ApiError } from '../api'
import type { Ledger, LedgerDepartment, LedgerPermissions, LedgerRecord } from './ledger-state'

export const ledgerPath = (department: LedgerDepartment) => `/api/business/ledgers/${department}/`

export async function getAuthorizedLedger(department: LedgerDepartment, signal?: AbortSignal): Promise<Ledger> {
  const access = await apiRequest<{ departments: (LedgerPermissions & { department: string })[] }>('/api/business/ledgers/permissions/', { signal })
  if (!Array.isArray(access?.departments)) throw new Error('台账权限数据不完整，请重新读取。')
  if (!access.departments.some(item => item.department === department)) throw new ApiError(403, '当前账号未获该台账访问权限。')
  const result = await apiRequest<Ledger>(ledgerPath(department), { signal })
  if (result.department !== department || !Array.isArray(result.records) || !Array.isArray(result.statuses)
    || !Number.isSafeInteger(result.revision) || result.revision < 0 || !['draft', 'submitted', 'published'].includes(result.state)
    || !result.fields || !result.permissions || ['can_edit', 'can_submit', 'can_publish'].some(key => typeof result.permissions[key as keyof LedgerPermissions] !== 'boolean')) {
    throw new Error('台账数据不完整，请重新读取。')
  }
  return result
}

export function saveLedgerRecord(department: LedgerDepartment, revision: number, record: LedgerRecord, projectId: string | null): Promise<Ledger> {
  return apiRequest<Ledger>(ledgerPath(department) + (projectId ? `records/${encodeURIComponent(projectId)}/` : 'records/'), {
    method: projectId ? 'PUT' : 'POST', body: JSON.stringify({ expected_revision: revision, record }),
  })
}

export function ledgerMutation(department: LedgerDepartment, revision: number, action: 'submit' | 'publish' | 'return' | 'metadata', data: { as_of?: string; reason?: string } = {}): Promise<Ledger> {
  return apiRequest<Ledger>(ledgerPath(department) + (action === 'metadata' ? '' : `${action}/`), {
    method: action === 'metadata' ? 'PATCH' : 'POST', body: JSON.stringify({ expected_revision: revision, ...data }),
  })
}
