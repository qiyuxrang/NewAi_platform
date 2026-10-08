import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchJSON } from '../lib/api'
import { useEnterprise } from '../components/EnterpriseContext'

interface BusinessStatus {
  configured: boolean
  linked: boolean
  available: boolean
  message: string
  portal_user_id: number | null
}

export default function BusinessLink() {
  const { reload } = useEnterprise()
  const [status, setStatus] = useState<BusinessStatus | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    fetchJSON<BusinessStatus>('/api/enterprise/status').then(value => {
      if (active) setStatus(value)
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '无法读取连接状态') })
    return () => { active = false }
  }, [])

  async function connect(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const value = await fetchJSON<BusinessStatus>('/api/enterprise/link', {
        method: 'POST', body: JSON.stringify({ username, password }),
      })
      setPassword(''); setStatus(value); reload()
    } catch (cause) {
      setPassword(''); setError(cause instanceof Error ? cause.message : '连接失败')
    } finally { setBusy(false) }
  }

  async function disconnect() {
    setBusy(true); setError('')
    try {
      setStatus(await fetchJSON<BusinessStatus>('/api/enterprise/link', { method: 'DELETE' }))
      reload()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '断开失败') }
    finally { setBusy(false) }
  }

  return <section className="max-w-xl space-y-5">
    <Link className="text-accent-blue text-sm" to="/settings">返回设置</Link>
    <div><h1 className="text-2xl font-semibold text-dark-text">业务账号连接</h1>
      <p className="mt-2 text-dark-text-secondary">连接你在原公司平台的账号，沿用该账号的部门、资料与任务权限。密码仅用于本次登录。</p></div>
    {error && <p role="alert" className="rounded-lg bg-accent-red/10 p-3 text-accent-red">{error}</p>}
    {status && <div role="status" className="rounded-xl border border-dark-border bg-dark-card p-4">
      <p>{status.message}</p>
      {status.linked && <p className="mt-1 text-sm text-dark-text-secondary">业务用户：{status.portal_user_id} · {status.available ? '连接可用' : '需要重新连接'}</p>}
      {status.linked && <button type="button" disabled={busy} onClick={disconnect} className="mt-3 text-accent-red disabled:opacity-50">断开连接</button>}
    </div>}
    <form onSubmit={connect} className="space-y-4 rounded-xl border border-dark-border bg-dark-card p-5">
      <label className="block text-sm">原业务账号
        <input autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)}
          className="mt-2 w-full rounded-lg border border-dark-border bg-dark-bg p-3" /></label>
      <label className="block text-sm">原业务密码
        <input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)}
          className="mt-2 w-full rounded-lg border border-dark-border bg-dark-bg p-3" /></label>
      <button disabled={busy || status?.configured === false} className="rounded-lg bg-accent-blue px-5 py-2.5 text-white disabled:opacity-50">
        {busy ? '正在连接…' : status?.linked ? '重新连接' : '连接业务账号'}
      </button>
    </form>
  </section>
}
