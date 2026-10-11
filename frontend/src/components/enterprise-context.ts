import { createContext, useContext } from 'react'
import type { AuthUser } from '../lib/api'
import type { EnterpriseAccess } from '../enterprise-navigation'

export type EnterpriseUser = AuthUser & EnterpriseAccess
export const EnterpriseContext = createContext<{
  user: EnterpriseUser | null
  loading: boolean
  error: string
  reload: () => void
}>({ user: null, loading: true, error: '', reload: () => {} })

export function useEnterprise() {
  return useContext(EnterpriseContext)
}
