import { Link, useSearchParams } from 'react-router-dom'
import { useBusinessResource } from './useBusinessResource'
import './department-projects.css'

const departments = { presales: '售前项目', engineering: '工程项目', finance: '财务项目' } as const
type Code = keyof typeof departments
interface Project { id: string; name: string; status: string; owner: string; record_count: number; updated_at: string | null }
interface Source { name: string; as_of: string; revision: number; state: string }
interface Projects { projects: Project[]; source: Source | null; scope: string; available: boolean; total: number }
interface Detail { project: Project; records: Record<string, string>[]; fields: Record<string, string>; source: Source; updates: { at: string; summary: string; actor?: { name: string } }[] }

export default function DepartmentProjects() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('source') || 'presales'
  const code: Code = Object.hasOwn(departments, raw) ? raw as Code : 'presales'
  const query = params.get('q') || ''
  const selected = params.get('project') || ''
  const list = useBusinessResource<Projects>(`/api/business/boards/${code}/projects/?${new URLSearchParams({ q: query })}`)
  const detail = useBusinessResource<Detail>(selected && !list.denied ? `/api/business/boards/${code}/projects/${encodeURIComponent(selected)}/` : null)
  return <div className="department-projects space-y-6">
    <header><h1 className="text-2xl font-bold">部门项目汇总</h1><p>各部门已发布台账；文档生成任务在文档工作台单独查看。</p></header>
    <nav className="flex flex-wrap gap-3" aria-label="项目来源部门">{Object.entries(departments).map(([value, label]) => <button className="button secondary" key={value} aria-pressed={code === value} onClick={() => setParams({ source: value })}>{label}</button>)}<Link className="button secondary" to="/departments/business/finance">财务看板</Link></nav>
    <form className="flex gap-3" onSubmit={event => { event.preventDefault(); const q = String(new FormData(event.currentTarget).get('q') || '').trim(); setParams({ source: code, q }) }}><input key={`${code}/${query}`} name="q" defaultValue={query} maxLength={100} aria-label="搜索项目名称" placeholder="搜索项目名称" /><button className="button secondary">搜索</button><button type="button" className="button secondary" onClick={() => { list.reload(); detail.reload() }}>刷新</button></form>
    {list.error && <p role="alert">刷新失败：{list.error}{list.data && '；以下保留上次成功读取的结果。'}</p>}
    {list.updatedAt && <p className="text-sm">最近读取：{list.updatedAt} · 页面可见时每 15 秒刷新</p>}
    {!list.data && !list.error && <p role="status">正在读取已发布项目…</p>}
    {list.data && <section className="center-panel"><p>{list.data.scope}</p><p>来源：{list.data.source?.name || '暂无发布'} · 截止：{list.data.source?.as_of || '—'} · 发布版本：{list.data.source?.revision ?? '—'}</p>
      {!list.data.projects.length ? <p>暂无已发布项目；员工保存草稿后仍需按部门规则发布。</p> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['项目名称', '负责人', '状态', '来源记录数', '更新', '操作'].map(label => <th className="p-3" key={label}>{label}</th>)}</tr></thead><tbody>{list.data.projects.map(project => <tr key={`${code}/${project.id}`}><td className="p-3">{project.name}</td><td>{project.owner || '—'}</td><td>{project.status || '待核实'}</td><td>{project.record_count}</td><td>{project.updated_at ? new Date(project.updated_at).toLocaleString('zh-CN') : '—'}</td><td><button className="button secondary" onClick={() => setParams({ source: code, q: query, project: project.id })}>查看明细</button></td></tr>)}</tbody></table></div>}
    </section>}
    {selected && <section className="center-panel" aria-label="项目明细"><button className="button secondary" onClick={() => setParams({ source: code, q: query })}>关闭明细</button>{detail.error && <p role="alert">{detail.error}</p>}{!detail.data && !detail.error && <p role="status">正在读取项目明细…</p>}{detail.data && <><h2>{detail.data.project.name}</h2><p>已发布 v{detail.data.source.revision} · 截止 {detail.data.source.as_of}</p>{detail.data.records.map((record, index) => <details key={index} open><summary>来源记录 {index + 1}</summary><dl className="grid gap-2">{Object.entries(detail.data!.fields).map(([field, label]) => <div key={field}><dt className="font-semibold">{label}</dt><dd className="whitespace-pre-wrap">{record[field] || '—'}</dd></div>)}</dl></details>)}</>}</section>}
  </div>
}
