import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowLeft, BookOpen, Building2, ChevronDown, Files, Folder, PanelLeftClose, PanelLeftOpen, Plus, Search, Settings } from 'lucide-react'
import { listTasks } from './product-api'
import type { TaskSummary } from './product-api'
import { useEnterprise } from '../../components/enterprise-context'
import { useEntryAccess } from '../entry-access'
import BusinessSurface from '../BusinessSurface'
import LedgerEntry from '../ledgers/LedgerEntry'
import NewProductProject from './NewProductProject'
import ProductProjectDetail from './ProductProjectDetail'
import ProductProjects from './ProductProjects'
import ProductOverview from './ProductOverview'
import ProductOutputs from './ProductOutputs'
import ProductKnowledge from './ProductKnowledge'
import Baichuan from './Baichuan'
import TenderOpportunities from './TenderOpportunities'
import WorkbenchSeparator from './WorkbenchSeparator'
import { clampPanelWidth, useElementWidth } from './workbench-resize'
import './product-division.css'
import './workbuddy-workspace.css'
import './product-reference.css'

export default function ProductWorkspace({ feature }: { feature: string }) {
  const location = useLocation()
  const { user } = useEnterprise()
  const manager = user?.business_role === 'general_manager'
  const entryAllowed = useEntryAccess()
  const params = new URLSearchParams(location.search)
  const task = params.get('task')
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [navigationHidden, setNavigationHidden] = useState(false)
  const [navigationWidth, setNavigationWidth] = useState<number | null>(() => {
    try {
      const width = Number(window.sessionStorage.getItem('product-navigation-width'))
      return Number.isFinite(width) && width >= 160 && width <= 360 ? width : null
    } catch { return null }
  })
  const shellRef = useRef<HTMLDivElement>(null)
  const shellWidth = useElementWidth(shellRef)
  const knowledge = feature === 'knowledge'
  const navigationMax = Math.min(360, Math.max(160, (shellWidth || 1600) - 514))
  const defaultNavigationWidth = 224
  const visibleNavigationWidth = clampPanelWidth(navigationWidth ?? defaultNavigationWidth, 160, navigationMax)
  const resizeNavigation = (width: number) => {
    setNavigationWidth(width)
    try { window.sessionStorage.setItem('product-navigation-width', String(width)) } catch { /* Keep resizing available when storage is disabled. */ }
  }
  useEffect(() => {
    if (manager) return
    let controller: AbortController
    const read = () => {
      controller?.abort()
      controller = new AbortController()
      const signal = controller.signal
      void listTasks(signal).then(result => {
        if (!signal.aborted) { if (!Array.isArray(result.tasks)) throw new Error('项目列表格式无效，请重新加载。'); setTasks(result.tasks); setError(''); setLoading(false) }
      }).catch(reason => {
        if (!signal.aborted) { setTasks([]); setError(reason instanceof Error ? reason.message : '任务列表读取失败'); setLoading(false) }
      })
    }
    read()
    const timer = setInterval(read, 30000)
    window.addEventListener('product:tasks-changed', read)
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener('product:tasks-changed', read) }
  }, [revision, manager])
  const states: Record<string, string> = { DRAFT: '草稿', QUEUED: '排队中', RUNNING: '进行中', WAITING_INPUT: '待补充', WAITING_REVIEW: '待确认', FAILED: '需重试', COMPLETED: '已完成', CANCELLED: '已取消' }
  const view = feature === 'documents' ? task ? 'detail' : (params.get('view') === 'projects' || (manager && params.get('view') !== 'new')) ? 'projects' : 'new' : feature
  const title = { overview: '产品事业部 / 部门总览', documents: view === 'projects' ? '项目工作台 / 历史项目' : '项目工作台 / 新建项目', knowledge: '产品事业部 / 智能助手', outputs: '项目成果 / 成果文件', opportunities: '项目机会', entry: '产品事业部 / 售前填报', baichuan: '产品事业部 / 百川阁' }[feature] || '产品事业部'
  const content = <>
    {feature === 'overview' && <ProductOverview />}
    {feature === 'documents' && (task ? <ProductProjectDetail key={task} id={task} artifact={params.get('artifact') || ''} /> : view === 'projects' ? <ProductProjects view="projects" /> : <NewProductProject />)}
    {feature === 'opportunities' && <TenderOpportunities />}
    {feature === 'knowledge' && <ProductKnowledge />}
    {feature === 'baichuan' && <Baichuan />}
    {feature === 'outputs' && <ProductOutputs />}
    {feature === 'entry' && <LedgerEntry department="presales" />}
  </>
  if (manager) return <BusinessSurface><div className="wb-shell wb-reference gm-product-shell" data-view={view}><div className="wb-work-area">
    {(feature === 'documents' || feature === 'outputs') && <nav className="gm-document-nav" aria-label="文档内导航"><Link to="/departments/product/documents?view=projects" aria-current={view === 'projects' ? 'page' : undefined}>历史项目</Link><Link to="/departments/product/documents?view=new" aria-current={view === 'new' ? 'page' : undefined}>新建项目</Link><Link to="/departments/product/outputs" aria-current={feature === 'outputs' ? 'page' : undefined}>成果文件</Link></nav>}
    <div className="wb-work-content">{content}</div>
  </div></div></BusinessSurface>
  return <BusinessSurface><div ref={shellRef} className="wb-shell wb-reference" data-view={view} style={{ '--nav-width': `${knowledge && navigationHidden ? 0 : visibleNavigationWidth}px` } as CSSProperties}>
    <aside id="product-workspace-navigation" className="wb-navigation" aria-label="产品事业部导航" hidden={knowledge && navigationHidden}>
      <Link className="wb-brand" to="/departments/product" aria-label="产品事业部总览"><img src="/company-logo.png" alt="陕西一二三数字信息技术有限公司"/></Link>
      <Link className="wb-new-task" to="/departments/product/documents"><Plus size={17}/>新建项目</Link>
      <nav className="wb-links">
        <Link to="/departments/product/documents?view=projects" aria-current={feature === 'documents' && params.get('view') === 'projects' ? 'page' : undefined}><Folder size={16}/>全部项目</Link>
        <Link to="/departments/product/knowledge" aria-current={feature === 'knowledge' ? 'page' : undefined}><BookOpen size={16}/>智能助手</Link>
        <Link to="/departments/product/outputs" aria-current={feature === 'outputs' ? 'page' : undefined}><Files size={16}/>成果文件</Link>
        <Link to="/departments/product/opportunities" aria-current={feature === 'opportunities' ? 'page' : undefined}><Search size={16}/>项目机会</Link>
        <Link to="/departments/product/baichuan" aria-current={feature === 'baichuan' ? 'page' : undefined}><Building2 size={16}/>百川阁</Link>
        {entryAllowed && <Link to="/departments/product/entry" aria-current={feature === 'entry' ? 'page' : undefined}><Files size={16}/>售前填报</Link>}
      </nav>
      <div className="wb-task-label">最近项目</div>
      <label className="wb-search"><Search size={15}/><input aria-label="搜索最近项目" placeholder="搜索项目" value={query} onChange={event => setQuery(event.target.value)}/></label>
      <div className="wb-task-list">
        {loading && <p role="status">正在读取项目…</p>}
        {error && <div role="alert"><p>{error}</p><button onClick={() => setRevision(value => value + 1)}>重新加载</button></div>}
        {!loading && !error && !tasks.length && <p>创建项目后会显示在这里。</p>}
        {!loading && !error && !!tasks.length && !tasks.some(item => item.title.toLowerCase().includes(query.toLowerCase())) && <p>没有匹配的项目。</p>}
        {tasks.filter(item => item.title.toLowerCase().includes(query.toLowerCase())).slice(0, 30).map(item => <Link key={item.id} to={`/departments/product/documents?task=${encodeURIComponent(item.id)}`} aria-current={task === item.id ? 'page' : undefined}><span className={`wb-task-dot ${item.state.toLowerCase()}`}/><div><strong title={item.title}>{item.title}</strong><small><span>{states[item.state] || item.state}</span>{item.updated_at && Number.isFinite(Date.parse(item.updated_at)) && <time dateTime={item.updated_at}>{new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(item.updated_at))}</time>}</small></div></Link>)}
      </div>
      <nav className="wb-navigation-foot"><Link to="/dashboard"><ArrowLeft size={16}/>企业工作台</Link><Link to="/settings"><Settings size={16}/>账号与设置</Link></nav>
    </aside>
    {knowledge && !navigationHidden && <WorkbenchSeparator className="wb-navigation-separator" label="调整产品导航宽度" width={visibleNavigationWidth} min={160} max={navigationMax} onResize={resizeNavigation}/>}
    <div className="wb-work-area"><header className="wb-toolbar">{knowledge ? <div className="wb-toolbar-title"><button type="button" className="wb-navigation-toggle" aria-controls="product-workspace-navigation" aria-expanded={!navigationHidden} onClick={() => setNavigationHidden(hidden => !hidden)}>{navigationHidden ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}<span>{navigationHidden ? '展开产品导航' : '隐藏产品导航'}</span></button><span>{title}</span></div> : <span>{title}</span>}<div className="wb-toolbar-right"><small>技术方案 · 可研报告 · 汇报演示文稿</small><Link to="/settings" className="wb-account"><span aria-hidden="true">产</span>产品事业部<ChevronDown size={13}/></Link></div></header><div className="wb-work-content">
    {content}
    </div></div>
  </div></BusinessSurface>
}
