import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowLeft, BookOpen, Files, Folder, Layers, Plus, Search, Settings } from 'lucide-react'
import { listTasks } from './product-api'
import type { TaskSummary } from './product-api'
import BusinessSurface from '../BusinessSurface'
import NewProductProject from './NewProductProject'
import ProductProjectDetail from './ProductProjectDetail'
import ProductProjects from './ProductProjects'
import ProductOutputs from './ProductOutputs'
import ProductKnowledge from './ProductKnowledge'
import TenderOpportunities from './TenderOpportunities'
import './product-division.css'
import './workbuddy-workspace.css'

export default function ProductWorkspace({ feature }: { feature: string }) {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const task = params.get('task')
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
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
    return () => { controller.abort(); clearInterval(timer) }
  }, [task, revision])
  const states: Record<string, string> = { DRAFT: '草稿', QUEUED: '排队中', RUNNING: '进行中', WAITING_INPUT: '待补充', WAITING_REVIEW: '待确认', FAILED: '需重试', COMPLETED: '已完成', CANCELLED: '已取消' }
  const title = { documents: '项目工作台', knowledge: '部门资料库', outputs: '项目成果', opportunities: '项目机会' }[feature] || '产品事业部'
  return <BusinessSurface><div className="wb-shell">
    <aside className="wb-navigation" aria-label="产品事业部导航">
      <Link className="wb-brand" to="/departments/product"><span><Layers size={20}/></span><div><strong>NewAi</strong><small>产品事业部</small></div></Link>
      <Link className="wb-new-task" to="/departments/product/documents"><Plus size={17}/>新建项目</Link>
      <nav className="wb-links">
        <Link to="/departments/product/documents?view=projects" aria-current={feature === 'documents' && params.get('view') === 'projects' ? 'page' : undefined}><Folder size={16}/>全部项目</Link>
        <Link to="/departments/product/knowledge" aria-current={feature === 'knowledge' ? 'page' : undefined}><BookOpen size={16}/>资料库</Link>
        <Link to="/departments/product/outputs" aria-current={feature === 'outputs' ? 'page' : undefined}><Files size={16}/>成果文件</Link>
        <Link to="/departments/product/opportunities" aria-current={feature === 'opportunities' ? 'page' : undefined}><Search size={16}/>项目机会</Link>
      </nav>
      <div className="wb-task-label">最近项目</div>
      <label className="wb-search"><Search size={15}/><input aria-label="搜索最近项目" placeholder="搜索项目" value={query} onChange={event => setQuery(event.target.value)}/></label>
      <div className="wb-task-list">
        {loading && <p role="status">正在读取项目…</p>}
        {error && <div role="alert"><p>{error}</p><button onClick={() => setRevision(value => value + 1)}>重新加载</button></div>}
        {!loading && !error && !tasks.length && <p>创建项目后会显示在这里。</p>}
        {!loading && !error && !!tasks.length && !tasks.some(item => item.title.toLowerCase().includes(query.toLowerCase())) && <p>没有匹配的项目。</p>}
        {tasks.filter(item => item.title.toLowerCase().includes(query.toLowerCase())).slice(0, 30).map(item => <Link key={item.id} to={`/departments/product/documents?task=${encodeURIComponent(item.id)}`} aria-current={task === item.id ? 'page' : undefined}><span className={`wb-task-dot ${item.state.toLowerCase()}`}/><div><strong>{item.title}</strong><small>{states[item.state] || item.state}</small></div></Link>)}
      </div>
      <nav className="wb-navigation-foot"><Link to="/dashboard"><ArrowLeft size={16}/>企业工作台</Link><Link to="/settings"><Settings size={16}/>账号与设置</Link></nav>
    </aside>
    <div className="wb-work-area"><header className="wb-toolbar"><span>{title}</span><small>技术方案 · 可研报告 · 汇报演示文稿</small></header><div className="wb-work-content">
    {feature === 'documents' && (task ? <ProductProjectDetail key={task} id={task} artifact={params.get('artifact') || ''} /> : params.get('view') === 'projects' ? <ProductProjects view="projects" /> : <NewProductProject />)}
    {feature === 'opportunities' && <TenderOpportunities />}
    {feature === 'knowledge' && <ProductKnowledge />}
    {feature === 'outputs' && <ProductOutputs />}
    </div></div>
  </div></BusinessSurface>
}
