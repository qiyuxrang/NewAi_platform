import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { EnterpriseAccountStatus, useEnterprise } from '../components/EnterpriseContext'
import { canAccessSetting, settingEntries } from '../enterprise-navigation'

export default function SettingsHome() {
  const { user, loading, error } = useEnterprise()
  if (loading || error) return <EnterpriseAccountStatus />
  const entries = settingEntries.filter(entry => canAccessSetting(user, entry.capability))
  return <div className="mx-auto max-w-6xl">
    <h1 className="text-2xl font-bold text-dark-text">设置</h1>
    <p className="mb-6 mt-2 text-sm text-dark-text-secondary">智能助手、技能与平台配置。</p>
    {!entries.length && <p role="status" className="rounded-xl border border-dark-border bg-dark-card p-6 text-dark-text-secondary">当前账号未获设置权限。修改密码与退出登录可通过左下角账号菜单操作。</p>}
    <div className="grid grid-cols-3 gap-4">
      {entries.map(entry => {
        const content = <>
        <div className="flex items-center justify-between font-semibold text-dark-text">{entry.label}<ArrowRight size={16} /></div>
        <p className="mt-2 text-sm text-dark-text-secondary">{entry.description}</p>
        </>
        const className = 'rounded-xl border border-dark-border bg-dark-card p-5 hover:border-accent-blue'
        return 'external' in entry
          ? <a key={entry.to} href={entry.to} target="_blank" rel="noopener noreferrer" className={className}>{content}</a>
          : <Link key={entry.to} to={entry.to} className={className}>{content}</Link>
      })}
    </div>
  </div>
}
