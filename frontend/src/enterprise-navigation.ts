export const departments = [
  { code: 'product', label: '产品事业部', description: '文档生成、商机管理、知识库问答与文档成果', functions: [
    { code: 'documents', label: '文档生成', description: '生成项目方案与交付文档' },
    { code: 'opportunities', label: '商机管理', description: '处理商机与方案需求' },
    { code: 'knowledge', label: '知识库问答', description: '围绕部门知识与参考资料提问' },
    { code: 'outputs', label: '文档成果', description: '查看已生成的方案与交付文档' },
  ] },
  { code: 'hr', label: '人事部', description: 'JD 生成、简历筛选与招聘记录', functions: [
    { code: 'jobs', label: 'JD 生成', description: '根据岗位需求生成 JD' },
    { code: 'resumes', label: '简历筛选', description: '处理简历与岗位匹配' },
    { code: 'history', label: '招聘历史', description: '查看已有招聘需求记录' },
  ] },
  { code: 'engineering', label: '工程部', description: '报价分析与报价任务', functions: [
    { code: 'estimate', label: '报价分析', description: '分析工程报价与成本' },
    { code: 'jobs', label: '报价任务', description: '跟进报价分析任务与结果' },
  ] },
] as const

export type DepartmentCode = typeof departments[number]['code']

export interface EnterpriseAccess {
  role?: string
  business_role?: string | null
  department_code?: string | null
  capabilities?: readonly string[]
}

export function hasCapability(user: EnterpriseAccess | null, capability: string): boolean {
  return user?.capabilities?.includes(capability) === true
}

export function canAccessDepartment(user: EnterpriseAccess | null, department: string): boolean {
  if (!departments.some(item => item.code === department)) return false
  return (user?.business_role === 'general_manager' || (user?.business_role === 'employee' && user?.department_code === department))
    && hasCapability(user, department)
}

export function availableDepartments(user: EnterpriseAccess | null) {
  return departments.filter(department => canAccessDepartment(user, department.code))
}

export function departmentPath(department: DepartmentCode, feature?: string) {
  return `/departments/${department}${feature ? `/${feature}` : ''}`
}

export const settingEntries = [
  { to: 'http://127.0.0.1:3081/', label: '平台管理', description: '分配账号、部门身份、配额与运行环境', capability: 'admin', external: true },
  { to: '/settings/business-link', label: '业务账号连接', description: '连接原业务工作台账号', capability: 'account' },
  { to: '/agents', label: 'Agents', description: '配置智能助手与工作空间', capability: 'personal' },
  { to: '/skills', label: '技能商店', description: '管理可用技能', capability: 'personal' },
  { to: '/channels', label: '渠道管理', description: '配置消息渠道', capability: 'admin' },
  { to: '/plugins', label: '插件管理', description: '管理扩展插件', capability: 'admin' },
  { to: '/models', label: 'AI 模型', description: '配置模型与服务', capability: 'admin' },
  { to: '/files', label: '文件管理', description: '管理助手工作空间文件', capability: 'personal' },
  { to: '/knowledge', label: '知识目录', description: '管理助手知识目录', capability: 'personal' },
  { to: '/sessions', label: '会话历史', description: '查看历史会话', capability: 'personal' },
  { to: '/cron', label: '定时任务', description: '配置与查看自动任务', capability: 'personal' },
  { to: '/nodes', label: 'Node 管理', description: '管理运行节点', capability: 'admin' },
  { to: '/terminal', label: '实时终端', description: '查看运行终端', capability: 'admin' },
  { to: '/api', label: 'API 设定', description: '管理 API 接入', capability: 'personal' },
  { to: '/settings/overview', label: '助手运行概览', description: '查看 Agent 运行状态', capability: 'personal' },
  { to: '/settings/system', label: '系统设置', description: '配置平台与网关', capability: 'admin' },
] as const

export function canAccessSetting(user: EnterpriseAccess | null, capability: string): boolean {
  if (!user) return false
  if (capability === 'account') return true
  if (user.role === 'admin') return true
  return capability === 'personal' && availableDepartments(user).length > 0
}

export const businessLists: Record<string, { path: string; key?: string }> = {
  'product/documents': { path: 'product/tasks/', key: 'tasks' },
  'product/opportunities': { path: 'product/opportunities/', key: 'items' },
  'product/outputs': { path: 'product/workspace/outputs/', key: 'outputs' },
  'hr/jobs': { path: 'hr/recruitment/requests/' },
  'hr/resumes': { path: 'hr/recruitment/batches/' },
  'hr/history': { path: 'hr/recruitment/requests/' },
  'engineering/estimate': { path: 'engineering/jobs/', key: 'jobs' },
  'engineering/jobs': { path: 'engineering/jobs/', key: 'jobs' },
}

export function readBusinessRows(value: unknown, key?: string): Record<string, unknown>[] {
  const rows = Array.isArray(value) ? value : key && value && typeof value === 'object'
    ? (value as Record<string, unknown>)[key] : undefined
  if (!Array.isArray(rows) || rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
    throw new Error('业务服务返回了无法识别的列表，暂时无法展示数据。')
  }
  return rows as Record<string, unknown>[]
}
