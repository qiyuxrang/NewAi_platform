import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, Loader2, LockKeyhole, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { login, register } from '../lib/api'
import './login.css'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (loading) return
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(username, password)
      } else {
        await register(username, email, password)
      }
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="enterprise-login">
      <div className="login-decoration" aria-hidden="true">
        <span className="login-rings login-rings-left" />
        <span className="login-rings login-rings-right" />
        <span className="login-dots login-dots-left" />
        <span className="login-dots login-dots-right" />
      </div>
      <section className="login-card" aria-labelledby="login-title">
        <header className="login-brand">
          <img src="/company-logo.png" alt="陕西一二三数字信息技术有限公司" width="320" height="132" />
          <div className="login-title-row"><h1 id="login-title">企业智能工作平台</h1></div>
        </header>

        {error && <div className="login-error" role="alert">
          <AlertCircle size={18} aria-hidden="true" /><span>{error}</span>
        </div>}

        <form onSubmit={handleSubmit} className="login-form" aria-busy={loading}>
          <div className="login-field">
            <label htmlFor="auth-username">用户名{mode === 'login' && ' / 邮箱'}</label>
            <div className="login-input">
              <UserRound size={21} aria-hidden="true" />
              <input id="auth-username" name="username" type="text" placeholder={mode === 'login' ? '请输入用户名或邮箱' : '请输入用户名'}
                value={username} onChange={e => setUsername(e.target.value)} required autoComplete="username" disabled={loading} />
            </div>
          </div>
          {mode === 'register' && <div className="login-field">
            <label htmlFor="auth-email">邮箱</label>
            <div className="login-input">
              <Mail size={21} aria-hidden="true" />
              <input id="auth-email" name="email" type="email" placeholder="请输入邮箱" value={email}
                onChange={e => setEmail(e.target.value)} required autoComplete="email" disabled={loading} />
            </div>
          </div>}
          <div className="login-field">
            <label htmlFor="auth-password">密码</label>
            <div className="login-input">
              <LockKeyhole size={21} aria-hidden="true" />
              <input id="auth-password" name="password" type={showPassword ? 'text' : 'password'}
                placeholder={mode === 'login' ? '请输入密码' : '请设置至少 8 位密码'} value={password}
                onChange={e => setPassword(e.target.value)} required minLength={mode === 'register' ? 8 : undefined}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'} disabled={loading} />
              <button type="button" className="login-password-toggle" aria-label={showPassword ? '隐藏密码' : '显示密码'}
                aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>
                {showPassword ? <EyeOff size={21} /> : <Eye size={21} />}
              </button>
            </div>
          </div>
          {mode === 'login' && <p className="login-help">忘记密码？请联系管理员</p>}
          <button type="submit" className="login-submit" disabled={loading}>
            {loading && <Loader2 size={20} className="animate-spin" aria-hidden="true" />}
            {loading ? mode === 'login' ? '正在登录…' : '正在注册…' : mode === 'login' ? '登录' : '创建账号'}
          </button>
        </form>

        <p className="login-switch">
          {mode === 'login' ? '还没有账号？' : '已有账号？'}
          <button type="button" disabled={loading} onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError('')
            setShowPassword(false)
          }}>{mode === 'login' ? '注册' : '返回登录'}</button>
        </p>
        <footer className="login-security"><ShieldCheck size={20} aria-hidden="true" /><span>安全登录 · 企业内部系统</span></footer>
      </section>
    </main>
  )
}
