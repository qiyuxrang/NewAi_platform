import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listTasks, type TaskSummary } from '../business/product/product-api'

export default function RecentProjects() {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let controller: AbortController
    const read = () => {
      controller?.abort()
      controller = new AbortController()
      const signal = controller.signal
      void listTasks(signal).then(result => {
        if (!signal.aborted) { setTasks(result.tasks); setError('') }
      }).catch(reason => { if (!signal.aborted) { setTasks([]); setError(reason instanceof Error ? reason.message : '项目读取失败') } })
        .finally(() => { if (!signal.aborted) setLoading(false) })
    }
    read()
    window.addEventListener('product:tasks-changed', read)
    return () => { controller.abort(); window.removeEventListener('product:tasks-changed', read) }
  }, [])
  return <section className="gm-recent" aria-label="最近文档项目"><h2>最近文档项目</h2>
    {loading && <p role="status">正在读取项目…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && !tasks.length && <p>暂无项目</p>}
    {tasks.slice(0, 12).map(task => <Link key={task.id} to={`/departments/product/documents?task=${encodeURIComponent(task.id)}`} title={task.title}>{task.title}</Link>)}
  </section>
}
