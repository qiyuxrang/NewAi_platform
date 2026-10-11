import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { NotificationProvider } from './NotificationProvider'

export default function Layout() {
  const { pathname } = useLocation()
  const product = pathname === '/departments/product' || pathname.startsWith('/departments/product/')
  return (
    <NotificationProvider>
      <div className={`flex h-screen overflow-hidden${product ? ' workbuddy-product' : ''}`}>
        {!product && <Sidebar />}
        <div className="flex flex-1 flex-col overflow-hidden">
          {!product && <TopBar />}
          <main className={`flex-1 overflow-y-auto${product ? ' wb-page' : ' p-6'}`}>
            <Outlet />
          </main>
        </div>
      </div>
    </NotificationProvider>
  )
}
