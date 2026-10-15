import { apiRequest, ApiError } from '../api'

export interface FinanceMetric { key: string; label: string; value: string | number | null; unit: string }
export interface FinanceDistribution { label: string; count: number }
export interface FinanceBoardPayload {
  department: 'finance'; title: string; available: boolean; snapshot_id: string
  fields: Record<string, string>; statuses: string[]; metrics: FinanceMetric[]
  distribution: FinanceDistribution[]; records: Record<string, string>[]
  total: number; filtered_count: number; currency: string; scope: string
  source: { name: string; as_of: string; imported_at: string; kind: string; revision: number; state: string } | null
}

export function loadFinanceBoard(query: string, signal: AbortSignal): Promise<FinanceBoardPayload> {
  const params = new URLSearchParams()
  if (query.trim()) params.set('q', query.trim())
  return apiRequest(`/api/business/boards/finance/${params.size ? `?${params}` : ''}`, { signal })
}

export function financeError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 401) return `${cause.message} 请重新登录或绑定业务账号。`
  return cause instanceof Error ? cause.message : '财务看板读取失败，请稍后重试。'
}

export function isSourceFinance(data: FinanceBoardPayload): boolean {
  return data.metrics.some(item => item.key === 'opening_receivable')
}

export function financeMetrics(data: FinanceBoardPayload): FinanceMetric[] {
  const keys = isSourceFinance(data) ? ['contract', 'opening_receivable', 'received', 'receivable', 'planned'] : ['contract', 'received', 'receivable', 'overdue']
  return keys.map(key => data.metrics.find(item => item.key === key)).filter((item): item is FinanceMetric => !!item)
}

export function financeValue(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const text = String(value)
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text
  const [integer, fraction] = text.split('.')
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${fraction === undefined ? '' : `.${fraction}`}`
}

export function collectionComposition(data: FinanceBoardPayload): { received: number; receivable: number } | null {
  if (!data.available || isSourceFinance(data)) return null
  const values = ['received', 'receivable'].map(key => data.metrics.find(item => item.key === key)?.value)
  if (values.some(value => value == null || value === '' || !/^\d+(\.\d+)?$/.test(String(value)))) return null
  const [received, receivable] = values.map(Number)
  return Number.isFinite(received + receivable) && received + receivable > 0 ? { received, receivable } : null
}
