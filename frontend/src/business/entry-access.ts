import { useEffect, useState } from 'react'
import { apiRequest } from './api'
import { useEnterprise } from '../components/enterprise-context'
import { canAccessEntry } from '../enterprise-navigation'

export function useEntryAccess() {
  const { user } = useEnterprise()
  const [result, setResult] = useState<{ key: string; allowed: string[] } | null>(null)
  const department = user?.department_code ?? ''
  const key = JSON.stringify([user?.portal_user_id, department, user?.username])
  const eligible = canAccessEntry(user, department)
  useEffect(() => {
    if (!eligible) return
    const controller = new AbortController()
    void apiRequest<{ departments: { department: string }[] }>('/api/business/ledgers/permissions/', { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setResult({ key, allowed: result.departments.map(item => item.department) })
    }).catch(() => { if (!controller.signal.aborted) setResult({ key, allowed: [] }) })
    return () => controller.abort()
  }, [eligible, key])
  return eligible && result?.key === key && result.allowed.includes(department === 'product' ? 'presales' : department)
}
