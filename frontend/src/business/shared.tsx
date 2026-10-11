import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { workspaceHref } from './workspace-navigation'

export interface WorkspaceProps { section: string }

export function CenterLink({ href, children, className, current = false }: { href: string; children: ReactNode; className?: string; current?: boolean }) {
  return <Link to={workspaceHref(href)} className={className} aria-current={current ? 'page' : undefined}>{children}</Link>
}

export function SectionHeader({ title, description, eyebrow }: { title: string; description: string; eyebrow?: string }) {
  return <div className="center-section-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2><p>{description}</p></div></div>
}

export function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return <div className="center-field"><label htmlFor={id}>{label}</label>{children}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>
}
