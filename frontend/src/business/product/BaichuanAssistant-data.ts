export const assistantRoot = '/api/product/baichuan/assistant/'

export interface AssistantConfig {
  enabled: boolean
  capabilities?: Record<string, boolean | string | { available?: boolean; reason?: string }>
  environment_label?: string
  limits?: { file_bytes?: number; files?: number }
}
export interface AssistantJob {
  id: string; kind?: string; status: string; stage?: string
  counts?: Record<string, unknown>; result_ref?: unknown; error_code?: string
}
export interface AssistantMessage { id: string; role: string; content: string; condition_revision?: number; metadata?: Record<string, unknown> }
export interface AssistantSnapshot { id: string; condition_revision?: number; result_revision?: number; counts?: Record<string, unknown> }
export interface AssistantConversation {
  id: string; condition_revision: number; messages?: AssistantMessage[]
  attachments?: { id: string; original_name: string; parse_status?: string }[]
  jobs?: AssistantJob[]; snapshots?: AssistantSnapshot[]
}
export interface AssistantResult {
  id: string; condition_revision?: number; counts?: Record<string, unknown>; conditions?: unknown; research_status?: unknown
  page?: number; page_size?: number; total?: number
  evidence?: Record<string, { title?: string; url?: string; excerpt?: string; locator?: unknown; verified_on?: string; retrieved_at?: string }>
  results?: { company_id: string; company?: { name?: string; phone?: string }; status?: string; verdict?: string
    conditions?: { condition_id: string; verdict?: string; reason?: string; evidence_ids?: string[] }[] }[]
}

export function assistantStorageKey(origin: string, owner: string, portalOwner: number | null): string {
  return `baichuan-assistant:v1:${encodeURIComponent(origin)}:${encodeURIComponent(owner)}:${portalOwner ?? 'unlinked'}`
}
export function jobActive(status: string): boolean {
  return ['queued', 'pending', 'running', 'retrying', 'recovering', 'cancel_requested'].includes(status.toLowerCase())
}
export function jobLabel(status: string): string {
  const labels: Record<string, string> = { queued: '等待执行', pending: '等待执行', running: '执行中', retrying: '重试中',
    recovering: '恢复中', completed: '已完成', succeeded: '已完成', done: '已完成', failed: '执行失败',
    cancelled: '已取消', canceled: '已取消', waiting_input: '等待补充信息', waiting_for_input: '等待补充信息',
    blocked: '需要处理', partial: '已返回部分结果', awaiting_input: '等待补充信息', cancel_requested: '正在取消' }
  return labels[status.toLowerCase()] || '状态待确认'
}
export function countSummary(counts?: Record<string, unknown>): string {
  const labels: Record<string, string> = { total: '总计', completed: '已处理', processed: '已处理', verified: '已核实',
    matched: '确认匹配', confirmed: '确认匹配', pending: '待核实', unknown: '待核实', conflict: '冲突', failed: '失败',
    researched: '已尝试研究', researched_companies: '已尝试研究企业', research_sources: '可读来源',
    research_suggestions: '资料建议', research_cache_hits: '复用来源',
    excluded: '不满足', candidates: '候选', candidate: '待核实候选' }
  return Object.entries(counts || {}).filter(([key, value]) => key in labels && Number.isInteger(value) && (value as number) >= 0)
    .map(([key, value]) => `${labels[key]} ${value}`).join(' · ')
}
export function verdictLabel(verdict?: string): string {
  const labels: Record<string, string> = { satisfied: '满足', pass: '满足', true: '满足', matched: '确认匹配', confirmed: '确认匹配',
    confirmed_match: '确认匹配', fail: '不满足', false: '不满足', unsatisfied: '不满足', excluded: '不满足',
    mismatch: '不满足', failed: '不满足', conflict: '存在冲突', unknown: '待核实', pending: '待核实', candidate: '待核实候选' }
  return labels[(verdict || '').toLowerCase()] || '待核实'
}
export function capabilityAvailable(value: unknown): boolean {
  return value === true || value === 'available' || value === 'enabled' ||
    (!!value && typeof value === 'object' && 'available' in value && value.available === true)
}
export function latestCurrentSnapshot(conversation: AssistantConversation): AssistantSnapshot | undefined {
  return [...(conversation.snapshots || [])].filter(item => item.condition_revision === conversation.condition_revision)
    .sort((a, b) => (b.result_revision || 0) - (a.result_revision || 0)).at(0)
}
export function validateAttachment(file: { name: string; size: number }): string {
  if (!/\.(pdf|docx)$/i.test(file.name)) return '请上传 PDF 或 DOCX 文件。'
  if (file.size <= 0) return '文件为空，请重新选择。'
  if (file.size > 20 * 1024 * 1024) return '单个文件不能超过 20 MB。'
  return ''
}

export function conditionLabel(tree: unknown, path: string): string {
  const parts = path.split('.')
  const kind = parts[0] === 'should' ? '优先项' : '硬性要求'
  if (!tree || typeof tree !== 'object') return `${kind} ${path}`
  let node: unknown = (tree as Record<string, unknown>)[parts[0]]
  for (const part of parts.slice(1)) {
    const index = Number(part)
    if (!Number.isInteger(index) || index < 0) return `${kind} ${path}`
    if (Array.isArray(node)) node = node[index]
    else if (node && typeof node === 'object') {
      const item = node as Record<string, unknown>
      node = Array.isArray(item.all) ? item.all[index] : Array.isArray(item.any) ? item.any[index] : index === 0 ? item.not : undefined
    } else node = undefined
  }
  if (!node || typeof node !== 'object') return `${kind} ${path}`
  const item = node as Record<string, unknown>
  const categories: Record<string, string> = { electronic: '电子与智能化', labor: '施工劳务', cs: 'CS', cmmi: 'CMMI', ccrc: 'CCRC', itss: 'ITSS', security: '安防工程' }
  const holders: Record<string, string> = { bidder: '投标企业', manufacturer: '制造商', person: '人员', group: '集团' }
  const field = typeof item.field === 'string' ? ({ 'company.name': '企业名称', 'company.province': '省份', 'company.city': '城市' } as Record<string, string>)[item.field] : ''
  const category = typeof item.category === 'string' ? categories[item.category] || item.category : ''
  const value = typeof item.value === 'string' ? item.value : ''
  const operation = item.op === 'grade_exact' ? '等级精确为 ' : item.op === 'grade_at_least' ? '等级及以上 ' : item.op === 'present' ? '具备' : '为 '
  const holder = typeof item.holder === 'string' ? holders[item.holder] || '主体待核实' : ''
  return `${kind} · ${field || category || path} ${operation}${value}${holder ? `（${holder}）` : ''}`
}
