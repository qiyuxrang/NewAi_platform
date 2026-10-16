import { ApiError } from '../api'

export const qualificationTypes = [
  { code: 'electronic', label: '电子与智能化工程专业承包', short: '电子与智能化', grades: ['1', '2'] },
  { code: 'labor', label: '施工劳务资质', short: '施工劳务', grades: [] },
  { code: 'cs', label: 'CS 信息系统建设和服务能力等级认证', short: 'CS', grades: ['1', '2', '3', '4', '5'] },
  { code: 'cmmi', label: 'CMMI 软件能力成熟度模型', short: 'CMMI', grades: ['3', '4', '5'] },
  { code: 'ccrc', label: 'CCRC 信息系统安全集成服务', short: 'CCRC', grades: ['1', '2', '3'] },
  { code: 'itss', label: 'ITSS 信息技术运行维护服务符合性认证', short: 'ITSS', grades: ['1', '2', '3', '4'] },
  { code: 'security', label: '安防工程企业设计施工维护能力', short: '安防工程', grades: ['1', '2', '3'] },
] as const
export type Category = typeof qualificationTypes[number]['code']
export const gradeName = (grade: string) => ({ '1': '一级', '2': '二级', '3': '三级', '4': '四级', '5': '五级' }[grade] || grade)
export const websiteTypes = [
  { code: 'corporate', label: '企业独立官网', short: '官网', action: '访问企业官网' },
  { code: 'group_profile', label: '集团专属介绍页', short: '集团介绍', action: '访问官方主页' },
  { code: 'official_wechat', label: '官方公众号', short: '官方公众号', action: '访问官方主页' },
] as const
export const websiteType = (kind: string | null | undefined) => websiteTypes.find(item => item.code === kind) || websiteTypes[0]
export const companyFields = ['name', 'credit_code', 'province', 'city', 'address', 'website', 'website_kind', 'phone', 'contact_name', 'contact_phone', 'email', 'description', 'source', 'verified_on'] as const
export type CompanyFields = Record<typeof companyFields[number], string | null>
export interface Company extends CompanyFields { id: string; name: string; version: number; updated_at?: string; created_at?: string }
export interface Qualification { id?: string; category: Category; status: 'PRESENT' | 'ABSENT' | 'UNKNOWN'; grade: string | null; certificate_no: string | null; valid_until: string | null; source: string | null; verified_on: string | null }
export interface Person { id?: string; name: string; department: string | null; position: string | null; reports_to_text: string | null; specialties: string | null; credentials: string | null; achievements: string | null; source: string | null; verified_on: string | null }
export interface CompanyDetailData { company: Company; qualifications: Qualification[]; people: Person[]; permissions: { can_edit: boolean } }
export interface CompanyRow extends Company { qualifications: Qualification[]; matched_qualification_ids: string[] }
export interface CompanyList { items: CompanyRow[]; total: number; page: number; page_size: number; has_more: boolean; permissions: { can_create: boolean } }
export interface CompanyDraft { company: CompanyFields; qualifications: Qualification[]; people: Person[]; expected_version?: number }
export const emptyDraft = (): CompanyDraft => ({ company: Object.fromEntries(companyFields.map(field => [field, field === 'website_kind' ? 'corporate' : ''])) as CompanyFields, qualifications: [], people: [] })
export function draftFrom(detail: CompanyDetailData): CompanyDraft {
  return { company: Object.fromEntries(companyFields.map(field => [field, detail.company[field] ?? (field === 'website_kind' ? 'corporate' : '')])) as CompanyFields, qualifications: detail.qualifications.map(item => ({ ...item })), people: detail.people.map(item => ({ ...item })), expected_version: detail.company.version }
}
export function listQuery(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('company')
  if (!params.has('page')) params.set('page', '1')
  if (!params.has('page_size')) params.set('page_size', '20')
  return params.toString()
}
export function toggleGrade(current: string, grade: string): string {
  const selected = current && current !== 'any' ? current.split(',') : []
  return (selected.includes(grade) ? selected.filter(value => value !== grade) : [...selected, grade]).sort().join(',')
}
export function safeWebsite(value: string | null | undefined): string | null {
  const text = value?.trim() || ''
  if (!/^https?:\/\//i.test(text) || /[\s\\]/.test(text) || /^https?:\/\/[^/?#]*@/i.test(text)) return null
  try { const url = new URL(text); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}
export function qualificationLabel(item: Qualification, full = false): string {
  const type = qualificationTypes.find(type => type.code === item.category)
  const status = item.status === 'ABSENT' ? '不具备' : item.status === 'UNKNOWN' ? '待核实' : item.category === 'labor' ? '不分等级' : item.grade ? gradeName(item.grade) : '等级待补充'
  return `${full ? type?.label : type?.short} · ${status}`
}
export function matchesQuery(draft: CompanyDraft, search: string): boolean {
  const params = new URLSearchParams(search)
  if (params.get('q') && !draft.company.name?.toLowerCase().includes(params.get('q')!.toLowerCase())) return false
  return qualificationTypes.every(type => { const value = params.get(type.code); return !value || draft.qualifications.some(item => item.category === type.code && item.status === 'PRESENT' && (value === 'any' || value.split(',').includes(item.grade || ''))) })
}
export function baichuanError(reason: unknown): string {
  if (reason instanceof ApiError) {
    if (reason.status === 401) return '登录已失效，请重新登录。'
    if (reason.status === 403) return `没有百川阁访问权限。${reason.message}`
    if (reason.status === 404) return '公司不存在或当前不可访问，请返回列表核对。'
    if (reason.code === 'version_conflict') return '资料已被其他人修改。当前输入已保留，请先另开详情核对最新版本，再重新编辑；系统不会覆盖他人的修改。'
    if (reason.code === 'duplicate_company') return '统一社会信用代码已存在，请核对公司资料。当前输入已保留。'
  }
  return reason instanceof Error ? reason.message : '连接暂时不可用，请重试。'
}
