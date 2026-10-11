import { Routes, Route, Navigate, Link, useParams } from 'react-router-dom'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import AgentDetail from './pages/AgentDetail'
import AgentCreate from './pages/AgentCreate'
import SkillStore from './pages/SkillStore'
import Channels from './pages/Channels'
import AIModels from './pages/AIModels'
import Sessions from './pages/Sessions'
import Chat from './pages/Chat'
import CronJobs from './pages/CronJobs'
import FileManager from './pages/FileManager'
import KnowledgeBase from './pages/KnowledgeBase'
import SystemSettings from './pages/SystemSettings'
import ApiAccess from './pages/ApiAccess'
import Nodes from './pages/Nodes'
import Plugins from './pages/Plugins'
import TerminalPage from './pages/Terminal'
import EnterpriseHome from './pages/EnterpriseHome'
import DepartmentWorkspace from './pages/DepartmentWorkspace'
import SettingsHome from './pages/SettingsHome'
import BusinessLink from './pages/BusinessLink'
import { EnterpriseAccountStatus, EnterpriseProvider } from './components/EnterpriseContext'
import { useEnterprise } from './components/enterprise-context'
import { canAccessDepartment, canAccessSetting } from './enterprise-navigation'
import { isLoggedIn } from './lib/api'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequirePermission({ children, setting }: { children: React.ReactNode; setting?: string }) {
  const { user, loading, error } = useEnterprise()
  const { department } = useParams()
  if (loading || error) return <EnterpriseAccountStatus />
  const allowed = setting ? canAccessSetting(user, setting) : canAccessDepartment(user, department ?? '')
  if (!allowed) return <div role="alert" className="rounded-xl border border-dark-border bg-dark-card p-6 text-dark-text">
    <h1 className="text-lg font-semibold">没有访问权限</h1>
    <p className="mt-2 text-sm text-dark-text-secondary">当前账号未获此功能授权，请联系管理员。</p>
    <Link to="/dashboard" className="mt-4 inline-block text-sm text-accent-blue">返回工作首页</Link>
  </div>
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><EnterpriseProvider><Layout /></EnterpriseProvider></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<EnterpriseHome />} />
        <Route path="departments/:department" element={<RequirePermission><DepartmentWorkspace /></RequirePermission>} />
        <Route path="departments/:department/:feature" element={<RequirePermission><DepartmentWorkspace /></RequirePermission>} />
        <Route path="agents" element={<RequirePermission setting="personal"><Agents /></RequirePermission>} />
        <Route path="agents/create" element={<RequirePermission setting="personal"><AgentCreate /></RequirePermission>} />
        <Route path="agents/:id" element={<RequirePermission setting="personal"><AgentDetail /></RequirePermission>} />
        <Route path="chat" element={<Chat />} />
        <Route path="skills" element={<RequirePermission setting="personal"><SkillStore /></RequirePermission>} />
        <Route path="channels" element={<RequirePermission setting="admin"><Channels /></RequirePermission>} />
        <Route path="plugins" element={<RequirePermission setting="admin"><Plugins /></RequirePermission>} />
        <Route path="models" element={<RequirePermission setting="admin"><AIModels /></RequirePermission>} />
        <Route path="files" element={<RequirePermission setting="personal"><FileManager /></RequirePermission>} />
        <Route path="knowledge" element={<RequirePermission setting="personal"><KnowledgeBase /></RequirePermission>} />
        <Route path="terminal" element={<RequirePermission setting="admin"><TerminalPage /></RequirePermission>} />
        <Route path="sessions" element={<RequirePermission setting="personal"><Sessions /></RequirePermission>} />
        <Route path="cron" element={<RequirePermission setting="personal"><CronJobs /></RequirePermission>} />
        <Route path="nodes" element={<RequirePermission setting="admin"><Nodes /></RequirePermission>} />
        <Route path="api" element={<RequirePermission setting="personal"><ApiAccess /></RequirePermission>} />
        <Route path="settings" element={<SettingsHome />} />
        <Route path="settings/business-link" element={<RequirePermission setting="account"><BusinessLink /></RequirePermission>} />
        <Route path="settings/overview" element={<RequirePermission setting="personal"><Dashboard /></RequirePermission>} />
        <Route path="settings/system" element={<RequirePermission setting="admin"><SystemSettings /></RequirePermission>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}
