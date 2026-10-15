import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listTasks, type TaskSummary } from '../business/product/product-api'

export default function RecentProjects() {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    void listTasks(controller.signal).then(result => {
      if (!controller.signal.aborted) setTasks(result.tasks)
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '项目读取失败') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])
  return <section className="gm-recent" aria-label="最近文档项目"><h2>最近文档项目</h2>
    {loading && <p role="status">正在读取项目…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && !tasks.length && <p>暂无项目</p>}
    {tasks.slice(0, 12).map(task => <Link key={task.id} to={`/departments/product/documents?task=${encodeURIComponent(task.id)}`} title={task.title}>{task.title}</Link>)}
  </section>
}
