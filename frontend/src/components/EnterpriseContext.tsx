import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getMe } from '../lib/api'
import { EnterpriseContext, useEnterprise, type EnterpriseUser } from './enterprise-context'

export function EnterpriseProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<EnterpriseUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    getMe().then(result => {
      if (active) setUser(result)
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : '账号信息加载失败')
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [revision])

  function reload() {
    setUser(null)
    setError('')
    setLoading(true)
    setRevision(value => value + 1)
  }

  return <EnterpriseContext.Provider value={{ user, loading, error, reload }}>{children}</EnterpriseContext.Provider>
}

export function EnterpriseAccountStatus() {
  const { loading, error, reload } = useEnterprise()
  if (loading) return <p role="status" className="py-10 text-dark-text-secondary">正在加载账号权限…</p>
  if (error) return <div role="alert" className="rounded-xl border border-dark-border bg-dark-card p-6 text-dark-text">
    <p>账号权限加载失败：{error}</p>
    <button onClick={reload} className="mt-4 rounded-lg bg-accent-blue px-4 py-2 text-sm text-white">重新加载</button>
  </div>
  return null
}
