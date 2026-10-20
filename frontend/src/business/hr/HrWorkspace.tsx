import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useEnterprise } from '../../components/enterprise-context'
import RecruitmentJobs from './RecruitmentJobs'
import RecruitmentScreening from './RecruitmentScreening'
import RecruitmentHistory from './RecruitmentHistory'
import './hr-workspace.css'

export default function HrWorkspace({ feature }: { feature: string }) {
  const { user } = useEnterprise()
  const location = useLocation()
  const managerId = user?.business_role === 'general_manager' ? user.portal_user_id ?? undefined : undefined
  const results = new URLSearchParams(location.search).get('results') === '1'

  useEffect(() => {
    function guardNavigation(event: MouseEvent) {
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!anchor || !(anchor instanceof HTMLAnchorElement) || anchor.origin !== window.location.origin || anchor.href === window.location.href) return
      if (!window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    document.addEventListener('click', guardNavigation, true)
    return () => document.removeEventListener('click', guardNavigation, true)
  }, [])

  return <div className="enterprise-hr center-hr" key={`${location.pathname}:${feature}`}>
    {feature === 'jobs' && <RecruitmentJobs managerId={managerId} />}
    {feature === 'resumes' && <RecruitmentScreening results={results} />}
    {feature === 'history' && <RecruitmentHistory managerId={managerId} />}
  </div>
}
