import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { fetchJSON } from '../lib/api'
import { departments, departmentPath } from '../enterprise-navigation'
import HrWorkspace from '../business/hr/HrWorkspace'
import ProductWorkspace from '../business/product/ProductWorkspace'
import ProductKnowledge from '../business/product/ProductKnowledge'
import EngineeringWorkspace from '../business/engineering/EngineeringWorkspace'
import BusinessSurface from '../business/BusinessSurface'
import FinanceBoard from '../business/finance/FinanceBoard'
import FinanceEntry from '../business/finance/FinanceEntry'
import LedgerEntry from '../business/ledgers/LedgerEntry'
import { useEntryAccess } from '../business/entry-access'
import { useEnterprise } from '../components/enterprise-context'
import WorkspaceBoundary from '../business/WorkspaceBoundary'
import DepartmentProjects from '../business/DepartmentProjects'

interface BusinessConnection {
  configured: boolean
  linked: boolean
  available: boolean
  message: string
}

export default function DepartmentWorkspace() {
  const { department: departmentCode, feature: featureCode } = useParams()
  const { user } = useEnterprise()
  const entryAllowed = useEntryAccess()
  const manager = user?.business_role === 'general_manager'
  const finance = departmentCode === 'business' && featureCode === 'finance'
  const projects = departmentCode === 'business' && featureCode === 'projects'
  const entry = featureCode === 'entry'
  const assistant = featureCode === 'knowledge'
  const department = departments.find(item => item.code === departmentCode)
  const feature = department?.functions.find(item => item.code === featureCode)
  const [connection, setConnection] = useState<BusinessConnection | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const hrFeature = departmentCode === 'hr' && !!featureCode && !assistant

  useEffect(() => {
    let active = true
    fetchJSON<BusinessConnection>('/api/enterprise/status').then(result => {
      if (active) setConnection(result)
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : '业务连接状态加载失败')
    })
    return () => { active = false }
  }, [revision])

  if (!finance && !projects && (!department || (featureCode && !feature))) return <p className="text-dark-text-secondary">该工作页面不存在。</p>

  return <div className={departmentCode === 'product' ? 'wb-department' : assistant ? 'assistant-department' : 'mx-auto max-w-6xl space-y-6'}>
    <div hidden={(manager || departmentCode === 'product' || entry || assistant) && connection?.available}>
      {feature && <Link to={departmentPath(department!.code)} className="text-sm text-accent-blue">返回{department?.label}</Link>}
      <h1 className="mt-2 text-2xl font-bold text-dark-text">{feature?.label ?? (finance ? '财务看板' : projects ? '部门项目汇总' : `${department?.label}工作台`)}</h1>
      <p className="mt-2 text-sm text-dark-text-secondary">{feature?.description ?? department?.description}</p>
    </div>
    {(!connection?.available || error) && <section className="rounded-xl border border-dark-border bg-dark-card p-6">
      <h2 className="font-semibold text-dark-text">业务连接状态</h2>
      {!connection && !error && <p role="status" className="mt-3 text-sm text-dark-text-secondary">正在检查业务服务…</p>}
      {error && <div role="alert" className="mt-3 text-sm text-accent-red">当前不可用：{error}</div>}
      {connection && <>
        <p role="status" className="mt-3 text-sm text-dark-text">{connection.available ? '业务账号已连接' : '当前业务不可用'}</p>
        <p className="mt-2 text-sm text-dark-text-secondary">{connection.message}</p>
        {!connection.linked && <Link to="/settings/business-link" className="mt-4 inline-flex rounded-lg bg-accent-blue px-4 py-2 text-sm text-white">连接业务账号</Link>}
      </>}
      {(connection || error) && <button onClick={() => { setConnection(null); setError(''); setRevision(value => value + 1) }} className="mt-4 ml-3 rounded-lg border border-dark-border px-4 py-2 text-sm text-dark-text-secondary hover:text-dark-text">重新检查</button>}
    </section>}
    <WorkspaceBoundary resetKey={`${departmentCode}/${featureCode}`}>
      {connection?.available && hrFeature && <HrWorkspace feature={featureCode!} />}
      {connection?.available && finance && <BusinessSurface><FinanceBoard /></BusinessSurface>}
      {connection?.available && projects && <BusinessSurface><DepartmentProjects /></BusinessSurface>}
      {connection?.available && entry && departmentCode === 'finance' && <BusinessSurface><FinanceEntry /></BusinessSurface>}
      {connection?.available && entry && departmentCode === 'engineering' && <BusinessSurface><LedgerEntry department="engineering" /></BusinessSurface>}
      {connection?.available && departmentCode === 'product' && <ProductWorkspace feature={featureCode || 'overview'} />}
      {connection?.available && assistant && departmentCode !== 'product' && <BusinessSurface><ProductKnowledge /></BusinessSurface>}
      {connection?.available && departmentCode === 'engineering' && featureCode && !entry && !assistant && <BusinessSurface><EngineeringWorkspace section="estimate" /></BusinessSurface>}
    </WorkspaceBoundary>
    {!finance && !projects && !feature && departmentCode !== 'product' && <div className="grid grid-cols-2 gap-4">
      {department!.functions.filter(item => item.code !== 'entry' || entryAllowed).map(item => <Link key={item.code} to={departmentPath(department!.code, item.code)} className="rounded-xl border border-dark-border bg-dark-card p-5 hover:border-accent-blue">
        <div className="flex items-center justify-between font-semibold text-dark-text">{item.label}<ArrowRight size={16} /></div>
        <p className="mt-2 text-sm text-dark-text-secondary">{item.description}</p>
      </Link>)}
    </div>}
  </div>
}
