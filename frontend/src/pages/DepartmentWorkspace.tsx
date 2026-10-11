import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { fetchJSON } from '../lib/api'
import { departments, departmentPath } from '../enterprise-navigation'
import HrWorkspace from '../business/hr/HrWorkspace'
import ProductWorkspace from '../business/product/ProductWorkspace'
import EngineeringWorkspace from '../business/engineering/EngineeringWorkspace'
import BusinessSurface from '../business/BusinessSurface'
import WorkspaceBoundary from '../business/WorkspaceBoundary'

interface BusinessConnection {
  configured: boolean
  linked: boolean
  available: boolean
  message: string
}

export default function DepartmentWorkspace() {
  const { department: departmentCode, feature: featureCode } = useParams()
  const department = departments.find(item => item.code === departmentCode)
  const feature = department?.functions.find(item => item.code === featureCode)
  const [connection, setConnection] = useState<BusinessConnection | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const hrFeature = departmentCode === 'hr' && !!featureCode

  useEffect(() => {
    let active = true
    fetchJSON<BusinessConnection>('/api/enterprise/status').then(result => {
      if (active) setConnection(result)
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : '业务连接状态加载失败')
    })
    return () => { active = false }
  }, [revision])

  if (!department || (featureCode && !feature)) return <p className="text-dark-text-secondary">该工作页面不存在。</p>

  return <div className={departmentCode === 'product' ? 'wb-department' : 'mx-auto max-w-6xl space-y-6'}>
    <div hidden={departmentCode === 'product' && connection?.available}>
      {feature && <Link to={departmentPath(department.code)} className="text-sm text-accent-blue">返回{department.label}</Link>}
      <h1 className="mt-2 text-2xl font-bold text-dark-text">{feature?.label ?? `${department.label}工作台`}</h1>
      <p className="mt-2 text-sm text-dark-text-secondary">{feature?.description ?? department.description}</p>
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
      {connection?.available && departmentCode === 'product' && <ProductWorkspace feature={featureCode || 'documents'} />}
      {connection?.available && departmentCode === 'engineering' && featureCode && <BusinessSurface><EngineeringWorkspace section="estimate" /></BusinessSurface>}
    </WorkspaceBoundary>
    {!feature && departmentCode !== 'product' && <div className="grid grid-cols-2 gap-4">
      {department.functions.map(item => <Link key={item.code} to={departmentPath(department.code, item.code)} className="rounded-xl border border-dark-border bg-dark-card p-5 hover:border-accent-blue">
        <div className="flex items-center justify-between font-semibold text-dark-text">{item.label}<ArrowRight size={16} /></div>
        <p className="mt-2 text-sm text-dark-text-secondary">{item.description}</p>
      </Link>)}
    </div>}
  </div>
}
