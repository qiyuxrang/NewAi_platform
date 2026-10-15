import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { NotificationProvider } from './NotificationProvider'
import { useEnterprise } from './enterprise-context'
import './manager-workspace.css'

export default function Layout() {
  const { pathname } = useLocation()
  const { user } = useEnterprise()
  const manager = user?.business_role === 'general_manager'
  const product = !manager && (pathname === '/departments/product' || pathname.startsWith('/departments/product/'))
  return (
    <NotificationProvider>
      <div className={`enterprise-shell flex h-screen overflow-hidden${product ? ' workbuddy-product' : ''}${manager ? ' manager-workspace' : ''}`}>
        {!product && <Sidebar />}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {!product && <TopBar />}
          <main className={`min-h-0 min-w-0 flex-1 overflow-y-auto${product ? ' wb-page' : ' p-6'}`}>
            <Outlet />
          </main>
        </div>
      </div>
    </NotificationProvider>
  )
}
