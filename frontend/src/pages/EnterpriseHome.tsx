import { Link } from 'react-router-dom'
import { ArrowRight, MessageSquare } from 'lucide-react'
import { EnterpriseAccountStatus, useEnterprise } from '../components/EnterpriseContext'
import { availableDepartments, departmentPath } from '../enterprise-navigation'

export default function EnterpriseHome() {
  const { user, loading, error } = useEnterprise()
  if (loading || error) return <EnterpriseAccountStatus />
  const assigned = availableDepartments(user)
  const manager = user?.business_role === 'general_manager'
  const title = manager ? '总经理工作首页' : assigned[0] ? `${assigned[0].label}工作首页` : '工作首页'

  return <div className="mx-auto max-w-6xl space-y-6">
    <div>
      <h1 className="text-2xl font-bold text-dark-text">{title}</h1>
      <p className="mt-2 text-sm text-dark-text-secondary">{user?.username}，从这里进入日常工作。</p>
    </div>
    {!assigned.length && <div role="status" className="rounded-xl border border-dark-border bg-dark-card p-6">
      <h2 className="font-semibold text-dark-text">部门权限未分配</h2>
      <p className="mt-2 text-sm text-dark-text-secondary">当前账号尚未分配可访问的部门，请联系管理员完成账号绑定与授权。</p>
      <Link to="/settings/business-link" className="mt-4 inline-block text-sm text-accent-blue">连接业务账号</Link>
    </div>}
    <div className={`grid gap-4 ${manager ? 'grid-cols-3' : 'grid-cols-1'}`}>
      {assigned.map(department => <section key={department.code} className="rounded-xl border border-dark-border bg-dark-card p-6">
        <Link to={departmentPath(department.code)} className="flex items-center justify-between text-dark-text hover:text-accent-blue">
          <h2 className="text-lg font-semibold">{department.label}</h2><ArrowRight size={18} />
        </Link>
        <p className="mb-5 mt-2 text-sm text-dark-text-secondary">{department.description}</p>
        <div className="space-y-2">
          {department.functions.map(feature => <Link key={feature.code} to={departmentPath(department.code, feature.code)} className="flex items-center justify-between rounded-lg border border-dark-border px-3 py-3 text-sm text-dark-text hover:border-accent-blue">
            {feature.label}<ArrowRight size={14} />
          </Link>)}
        </div>
      </section>)}
    </div>
    <Link to="/chat" className="flex items-center gap-4 rounded-xl border border-dark-border bg-dark-card p-6 hover:border-accent-blue">
      <MessageSquare size={24} className="text-accent-blue" />
      <div><h2 className="font-semibold text-dark-text">智能助手</h2><p className="mt-1 text-sm text-dark-text-secondary">开始对话，处理当前工作问题。</p></div>
      <ArrowRight size={18} className="ml-auto text-dark-text-secondary" />
    </Link>
  </div>
}
