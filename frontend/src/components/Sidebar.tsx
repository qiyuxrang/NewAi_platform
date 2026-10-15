import { useState, useEffect, useRef } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { changePassword, logout } from '../lib/api'
import { useEnterprise } from './enterprise-context'
import { availableDepartments, availableManagerEntries, departmentPath, enterpriseHomePath, hasCapability } from '../enterprise-navigation'
import Brand from './Brand'
import RecentProjects from './RecentProjects'
import { useEntryAccess } from '../business/entry-access'
import {
  Search, FileText, Calculator, BookOpen, ChartNoAxesCombined,
  LayoutDashboard,
  Settings,
  User,
  KeyRound,
  LogOut,
  X,
  Eye,
  EyeOff,
  Loader2,
} from 'lucide-react'

export default function Sidebar() {
  const location = useLocation()
  const { user, loading, error } = useEnterprise()
  const visibleDepartments = availableDepartments(user)
  const entryAllowed = useEntryAccess()
  const manager = user?.business_role === 'general_manager'
  const [menuOpen, setMenuOpen] = useState(false)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdError, setPwdError] = useState('')
  const [pwdSuccess, setPwdSuccess] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)
  const [showOld, setShowOld] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  const openPwdModal = () => {
    setMenuOpen(false)
    setOldPwd('')
    setNewPwd('')
    setConfirmPwd('')
    setPwdError('')
    setPwdSuccess('')
    setShowOld(false)
    setShowNew(false)
    setPwdModalOpen(true)
  }

  const handleChangePwd = async () => {
    setPwdError('')
    setPwdSuccess('')
    if (!oldPwd) { setPwdError('请输入旧密码'); return }
    if (newPwd.length < 6) { setPwdError('新密码至少需要6个字符'); return }
    if (newPwd !== confirmPwd) { setPwdError('两次输入的新密码不一致'); return }
    setPwdLoading(true)
    try {
      await changePassword(oldPwd, newPwd)
      setPwdSuccess('密码修改成功')
      setTimeout(() => setPwdModalOpen(false), 1500)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '修改失败'
      setPwdError(msg.includes('旧密码不正确') ? '旧密码不正确' : msg)
    } finally {
      setPwdLoading(false)
    }
  }

  return (
    <aside className="flex w-56 shrink-0 flex-col bg-dark-sidebar border-r border-dark-border">
      {/* Logo */}
      <Brand />

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {!manager && enterpriseHomePath(user) === '/dashboard' && <NavLink to="/dashboard" className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-accent-blue/15 text-accent-blue' : 'text-dark-text-secondary hover:bg-dark-card hover:text-dark-text'}`}>
          <LayoutDashboard size={18} />工作首页
        </NavLink>}
        <div className="my-4 space-y-2">
          {loading && <p role="status" className="px-3 text-xs text-dark-text-secondary">正在加载权限…</p>}
          {error && <p role="status" className="px-3 text-xs text-accent-red">权限加载失败</p>}
          {!loading && !error && !visibleDepartments.length && <p className="px-3 text-xs text-dark-text-secondary">部门未分配</p>}
          {manager && availableManagerEntries(user).map((entry) => {
            const Icon = { '商机看板': Search, '文档生成': FileText, '产品报价': Calculator, '智能助手': BookOpen, '财务看板': ChartNoAxesCombined }[entry.label]
            const active = entry.label === '文档生成' ? /^\/departments\/product\/(documents|outputs)/.test(location.pathname) : location.pathname === entry.to.split('?')[0]
            return <Link key={entry.to} to={entry.to} aria-current={active ? 'page' : undefined} className={`gm-nav-link ${active ? 'active' : ''}`}><Icon size={19} />{entry.label}</Link>
          })}
          {!manager && visibleDepartments.map(department => {
            const links = <div className="space-y-1">
              <NavLink end to={departmentPath(department.code)} className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-accent-blue/15 text-accent-blue' : 'text-dark-text-secondary hover:bg-dark-card hover:text-dark-text'}`}>部门首页</NavLink>
              {department.functions.filter(feature => feature.code !== 'entry' || entryAllowed).map(feature => <NavLink key={feature.code} to={departmentPath(department.code, feature.code)} className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-accent-blue/15 text-accent-blue' : 'text-dark-text-secondary hover:bg-dark-card hover:text-dark-text'}`}>{feature.label}</NavLink>)}
            </div>
            return manager ? <details key={department.code} open={location.pathname.startsWith(departmentPath(department.code))}>
              <summary className="cursor-pointer rounded-lg px-3 py-2 text-sm font-medium text-dark-text hover:bg-dark-card">{department.label}</summary>
              {links}
            </details> : <div key={department.code}>
              <div className="mb-2 px-3 text-xs font-medium text-dark-text-secondary">{department.label}</div>
              {links}
            </div>
          })}
        </div>
        {manager && hasCapability(user, 'product') && <RecentProjects key={user?.portal_user_id} />}
        <NavLink to="/settings" className={({ isActive }) => `mt-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-accent-blue/15 text-accent-blue' : 'text-dark-text-secondary hover:bg-dark-card hover:text-dark-text'}`}>
          <Settings size={18} />设置
        </NavLink>
      </nav>

      {/* User */}
      <div className="relative border-t border-dark-border px-4 py-3" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex w-full items-center gap-3 rounded-lg p-1 hover:bg-dark-card transition-colors"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-purple text-sm font-medium text-white">
            <User size={16} />
          </div>
          <div className="text-left">
            <div className="text-sm font-medium text-dark-text">{user?.username ?? (loading ? '加载中' : '账号信息不可用')}</div>
            <div className="text-xs text-dark-text-secondary">{manager ? '总经理' : visibleDepartments[0]?.label ?? '部门未分配'}</div>
          </div>
        </button>

        {/* Popup menu */}
        {menuOpen && (
          <div className="absolute bottom-full left-4 mb-2 w-48 rounded-lg border border-dark-border bg-dark-sidebar shadow-lg py-1 z-50">
            <button
              onClick={openPwdModal}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-dark-text hover:bg-dark-card transition-colors"
            >
              <KeyRound size={15} />
              修改密码
            </button>
            <button
              onClick={() => logout()}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-accent-red hover:bg-dark-card transition-colors"
            >
              <LogOut size={15} />
              退出登录
            </button>
          </div>
        )}
      </div>

      {/* Password Change Modal */}
      {pwdModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-96 rounded-xl border border-dark-border bg-dark-sidebar p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-semibold text-dark-text">修改密码</h3>
              <button onClick={() => setPwdModalOpen(false)} className="text-dark-text-secondary hover:text-dark-text">
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              {/* Old password */}
              <div>
                <label className="block text-xs text-dark-text-secondary mb-1">旧密码</label>
                <div className="relative">
                  <input
                    type={showOld ? 'text' : 'password'}
                    value={oldPwd}
                    onChange={e => setOldPwd(e.target.value)}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 pr-9 text-sm text-dark-text focus:border-accent-blue focus:outline-none"
                    placeholder="请输入旧密码"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOld(!showOld)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-dark-text-secondary hover:text-dark-text"
                  >
                    {showOld ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* New password */}
              <div>
                <label className="block text-xs text-dark-text-secondary mb-1">新密码</label>
                <div className="relative">
                  <input
                    type={showNew ? 'text' : 'password'}
                    value={newPwd}
                    onChange={e => setNewPwd(e.target.value)}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 pr-9 text-sm text-dark-text focus:border-accent-blue focus:outline-none"
                    placeholder="至少6个字符"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNew(!showNew)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-dark-text-secondary hover:text-dark-text"
                  >
                    {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* Confirm password */}
              <div>
                <label className="block text-xs text-dark-text-secondary mb-1">确认新密码</label>
                <input
                  type={showNew ? 'text' : 'password'}
                  value={confirmPwd}
                  onChange={e => setConfirmPwd(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleChangePwd()}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-sm text-dark-text focus:border-accent-blue focus:outline-none"
                  placeholder="再次输入新密码"
                />
              </div>

              {/* Error / Success */}
              {pwdError && <div className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{pwdError}</div>}
              {pwdSuccess && <div className="rounded-lg bg-green-500/10 px-3 py-2 text-xs text-green-400">{pwdSuccess}</div>}

              {/* Submit */}
              <button
                onClick={handleChangePwd}
                disabled={pwdLoading}
                className="w-full rounded-lg bg-accent-blue py-2 text-sm font-medium text-white hover:bg-accent-blue/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {pwdLoading && <Loader2 size={14} className="animate-spin" />}
                确认修改
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
