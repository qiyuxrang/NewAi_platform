import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export interface WorkspaceProps { section: string }

export function workspaceHref(href: string): string {
  const match = href.match(/^\/centers\/(product|hr|cost)(?:\/([^?#/]+))?\/?(\?[^#]*)?(#.*)?$/)
  if (!match) return href
  const [, department, section = '', query = '', hash = ''] = match
  const params = new URLSearchParams(query)
  let target: string
  if (department === 'hr') {
    target = section === 'job' ? '/departments/hr/jobs' : section === 'history' ? '/departments/hr/history' : '/departments/hr/resumes'
    if (section === 'results') params.set('results', '1')
  } else if (department === 'cost') target = '/departments/engineering/estimate'
  else {
    target = ['knowledge', 'outputs', 'opportunities'].includes(section) ? `/departments/product/${section}` : '/departments/product/documents'
    if (['projects', 'history'].includes(section) && !params.has('task')) params.set('view', 'projects')
  }
  return `${target}${params.size ? `?${params}` : ''}${hash}`
}

export function CenterLink({ href, children, className, current = false }: { href: string; children: ReactNode; className?: string; current?: boolean }) {
  return <Link to={workspaceHref(href)} className={className} aria-current={current ? 'page' : undefined}>{children}</Link>
}

export function SectionHeader({ title, description, eyebrow }: { title: string; description: string; eyebrow?: string }) {
  return <div className="center-section-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2><p>{description}</p></div></div>
}

export function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return <div className="center-field"><label htmlFor={id}>{label}</label>{children}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>
}
