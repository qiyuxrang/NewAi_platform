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
    if (section === 'new') params.set('view', 'new')
    if (['projects', 'history'].includes(section) && !params.has('task')) params.set('view', 'projects')
  }
  return `${target}${params.size ? `?${params}` : ''}${hash}`
}

