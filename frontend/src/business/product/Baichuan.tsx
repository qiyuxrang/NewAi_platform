import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Building2, ChevronDown, ExternalLink, Phone, Plus, RotateCcw, Search, X } from 'lucide-react'
import { apiRequest } from '../api'
import { baichuanError, draftFrom, gradeName, listQuery, matchesQuery, qualificationLabel, qualificationTypes, safeWebsite, toggleGrade, websiteType } from './Baichuan-data'
import type { Category, CompanyDetailData, CompanyList } from './Baichuan-data'
import CompanyDetail from './CompanyDetail'
import CompanyEditor from './CompanyEditor'
import './Baichuan.css'

function QualificationFilter({ category, value, onChange }: { category: typeof qualificationTypes[number]; value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false)
  const [selection, setSelection] = useState(value)
  const [previousValue, setPreviousValue] = useState(value)
  if (previousValue !== value) { setPreviousValue(value); setSelection(value) }
  const choose = (next: string) => { setSelection(next); onChange(next) }
  const root = useRef<HTMLDivElement>(null), button = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    root.current?.querySelector<HTMLInputElement>('input')?.focus()
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const keyboard = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); setOpen(false); button.current?.focus() } }
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', keyboard)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keyboard) }
  }, [open])
  const selected = selection === 'any' ? '具备即可' : selection ? selection.split(',').map(gradeName).join('、') : '不限'
  return <div className="bc-filter" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <button ref={button} type="button" className={`bc-filter-button${selection ? ' selected' : ''}`} title={`${category.label}：${selected}`} aria-expanded={open} aria-controls={`bc-filter-${category.code}`} onClick={() => setOpen(current => !current)} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true) } }}><span>{category.short}{selection && <small>{selected}</small>}</span><ChevronDown size={16}/></button>
    {open && <div id={`bc-filter-${category.code}`} className="bc-filter-menu" role="group" aria-label={category.label}><strong>{category.label}</strong><label><input type="checkbox" checked={!selection} onChange={() => choose('')}/>不限</label><label><input type="checkbox" checked={selection === 'any'} onChange={() => choose(selection === 'any' ? '' : 'any')}/>具备即可</label>{category.grades.map(grade => <label key={grade}><input type="checkbox" checked={selection.split(',').includes(grade)} onChange={() => choose(toggleGrade(selection, grade))}/>{gradeName(grade)}</label>)}</div>}
  </div>
}

export default function Baichuan() {
  const location = useLocation(), navigate = useNavigate()
  const params = new URLSearchParams(location.search), companyId = params.get('company') || ''
  const query = listQuery(location.search)
  const [revision, setRevision] = useState(0), [search, setSearch] = useState(params.get('q') || '')
  const [listResponse, setListResponse] = useState<{ key: object; data: CompanyList | null; error: string } | null>(null)
  const [detailResponse, setDetailResponse] = useState<{ key: object; data: CompanyDetailData | null; error: string } | null>(null)
  const [editor, setEditor] = useState<{ detail: CompanyDetailData | null } | null>(null), [notice, setNotice] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const listKey = useMemo(() => ({ query, revision }), [query, revision])
  const detailKey = useMemo(() => ({ companyId, revision }), [companyId, revision])
  const currentList = listResponse?.key === listKey ? listResponse : null
  const currentDetail = detailResponse?.key === detailKey ? detailResponse : null
  useEffect(() => { setSearch(new URLSearchParams(location.search).get('q') || '') }, [location.search])
  useEffect(() => {
    const controller = new AbortController()
    void apiRequest<CompanyList>(`/api/product/baichuan/companies/?${listKey.query}`, { signal: controller.signal }).then(data => {
      if (!data || !Array.isArray(data.items) || !Number.isInteger(data.total) || !data.permissions) throw new Error('公司列表响应不完整，请重试。')
      if (!controller.signal.aborted) setListResponse({ key: listKey, data, error: '' })
    }).catch(reason => { if (!controller.signal.aborted) setListResponse({ key: listKey, data: null, error: baichuanError(reason) }) })
    return () => controller.abort()
  }, [listKey])
  useEffect(() => {
    if (!detailKey.companyId) return
    const controller = new AbortController()
    void apiRequest<CompanyDetailData>(`/api/product/baichuan/companies/${encodeURIComponent(detailKey.companyId)}/`, { signal: controller.signal }).then(data => {
      if (!data?.company || !Array.isArray(data.qualifications) || !Array.isArray(data.people) || !data.permissions) throw new Error('公司详情响应不完整，请重试。')
      if (!controller.signal.aborted) setDetailResponse({ key: detailKey, data, error: '' })
    }).catch(reason => { if (!controller.signal.aborted) setDetailResponse({ key: detailKey, data: null, error: baichuanError(reason) }) })
    return () => controller.abort()
  }, [detailKey])
  useEffect(() => {
    const pane = root.current?.closest('.wb-work-content')
    if (!pane || companyId) return
    const key = `baichuan-scroll:${query}`
    const remember = () => { try { sessionStorage.setItem(key, String(pane.scrollTop)) } catch { /* Scroll remains usable without storage. */ } }
    pane.addEventListener('scroll', remember)
    return () => pane.removeEventListener('scroll', remember)
  }, [query, companyId])
  useEffect(() => {
    const pane = root.current?.closest('.wb-work-content')
    if (!pane) return
    if (companyId) { pane.scrollTop = 0; return }
    if (!currentList?.data) return
    let top = 0
    try { top = Number(sessionStorage.getItem(`baichuan-scroll:${query}`)) || 0 } catch { /* Default to top. */ }
    const frame = requestAnimationFrame(() => { pane.scrollTop = top })
    return () => cancelAnimationFrame(frame)
  }, [companyId, query, currentList?.data])
  // Opening adds one same-URL entry, so browser Back can confirm before leaving a draft.
  useEffect(() => {
    if (editor && !(location.state as { bcEditor?: boolean } | null)?.bcEditor) {
      if (window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) setEditor(null)
      else navigate(1)
    }
  // Only navigation should run this guard, not draft renders.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key])
  const update = (change: (next: URLSearchParams) => void) => { const next = new URLSearchParams(location.search); next.delete('company'); change(next); navigate({ search: next.toString() }); setNotice('') }
  const setFilter = (category: Category, value: string) => update(next => { if (value) next.set(category, value); else next.delete(category); next.set('page', '1') })
  const back = () => { const next = new URLSearchParams(location.search); next.delete('company'); navigate({ search: next.toString() }, { replace: true }) }
  const showCompany = (id: string) => { const next = new URLSearchParams(location.search); next.set('company', id); navigate({ search: next.toString() }) }
  const edit = (detail: CompanyDetailData | null) => { navigate(`${location.pathname}${location.search}`, { state: { bcEditor: true } }); setEditor({ detail }) }
  const closeEditor = () => { setEditor(null); navigate(-1) }
  const saved = (data: CompanyDetailData) => {
    const remains = matchesQuery(draftFrom(data), query)
    setEditor(null); setRevision(value => value + 1)
    setNotice(remains ? '公司资料已保存。' : '公司资料已保存；该公司已不符合当前名称或资质条件，已从筛选结果中移出。')
    const next = new URLSearchParams(location.search)
    if (remains) next.set('company', data.company.id); else next.delete('company')
    navigate({ search: next.toString() }, { replace: true, state: null })
  }
  const filters = qualificationTypes.filter(type => params.get(type.code))
  const filtered = !!params.get('q') || filters.length > 0
  const matched = new Set(currentDetail?.data?.qualifications.filter(item => { const selection = params.get(item.category); return item.status === 'PRESENT' && selection && (selection === 'any' || selection.split(',').includes(item.grade || '')) }).map(item => item.id).filter((id): id is string => !!id))
  const lastPage = Math.max(1, Math.ceil((currentList?.data?.total || 0) / (currentList?.data?.page_size || 20)))
  const currentPage = currentList?.data?.page || 1
  const pageNumbers = [...new Set([1, ...Array.from({ length: 5 }, (_, index) => currentPage - 2 + index).filter(page => page > 1 && page < lastPage), lastPage])]
  return <div ref={root} className="bc">
    {notice && <p className="bc-notice" role="status">{notice}</p>}
    {companyId ? <>{!currentDetail && <p role="status" className="bc-card">正在读取公司资料…</p>}{currentDetail?.error && <section className="bc-card bc-error" role="alert"><p>{currentDetail.error}</p><div className="bc-actions"><button className="bc-button" onClick={back}>返回公司列表</button><button className="bc-button" onClick={() => setRevision(value => value + 1)}>重试</button></div></section>}{currentDetail?.data && <CompanyDetail data={currentDetail.data} matched={matched} onBack={back} onEdit={() => edit(currentDetail.data)}/>}</> : <>
      <header className="bc-page-heading"><div><h1>百川阁</h1><p>企业资质检索与合作资源库</p></div>{currentList?.data?.permissions.can_create && <button className="bc-button" onClick={() => edit(null)}><Plus size={18}/>新增公司</button>}</header>
      <section className="bc-card bc-search-card" aria-label="公司查询条件"><form className="bc-search-row" onSubmit={event => { event.preventDefault(); update(next => { if (search.trim()) next.set('q', search.trim()); else next.delete('q'); next.set('page', '1') }) }}><label className="bc-name-search"><Search size={20}/><input aria-label="搜索公司名称" placeholder="搜索公司名称…" value={search} onChange={event => setSearch(event.target.value)}/></label><button type="button" className="bc-button" onClick={() => { setSearch(''); navigate({ search: '' }); setNotice('') }}><RotateCcw size={17}/>重置</button><button className="bc-visually-hidden" type="submit">搜索</button></form><div className="bc-filter-row">{qualificationTypes.map(type => <QualificationFilter key={type.code} category={type} value={params.get(type.code) || ''} onChange={value => setFilter(type.code, value)}/>)}</div>{filtered && <div className="bc-selected" aria-label="已选条件">{params.get('q') && <button onClick={() => update(next => { next.delete('q'); next.set('page', '1') })}>名称：{params.get('q')}<X size={13}/></button>}{filters.flatMap(type => (params.get(type.code) === 'any' ? ['any'] : params.get(type.code)!.split(',')).map(grade => <button key={`${type.code}-${grade}`} onClick={() => setFilter(type.code, grade === 'any' ? '' : toggleGrade(params.get(type.code) || '', grade))}>{type.short}：{grade === 'any' ? '具备即可' : gradeName(grade)}<X size={13}/></button>))}</div>}</section>
      <section className="bc-card bc-list-card" aria-busy={!currentList}><div className="bc-section-heading"><h2>公司列表</h2><p className="bc-muted" aria-live="polite">{!currentList ? '正在查询…' : currentList.data ? `共 ${currentList.data.total} 家公司` : '查询未完成'}</p></div>{!currentList && <div className="bc-empty" role="status">正在读取公司列表…</div>}{currentList?.error && <div className="bc-empty bc-error" role="alert"><p>{currentList.error}</p><button className="bc-button" onClick={() => setRevision(value => value + 1)}>重新查询</button></div>}{currentList?.data && <><table className="bc-table"><thead><tr><th>企业信息</th><th>核心资质</th><th>联系方式</th><th>操作</th></tr></thead><tbody>{currentList.data.items.map(item => {
        const phones = [...new Set([item.contact_phone, item.phone].flatMap(phone => phone?.split(/[;；]+/).map(value => value.trim()).filter(Boolean) || []))]
        const website = safeWebsite(item.website)
        return <tr key={item.id}><td><div className="bc-company-cell"><span className="bc-list-mark" aria-hidden="true"><Building2 size={27}/></span><div><button className="bc-company-name" onClick={() => showCompany(item.id)}>{item.name}</button><p className="bc-muted">{[item.province, item.city].filter(Boolean).join(' · ') || '—'}</p></div></div></td><td><div className="bc-tags">{item.qualifications?.length ? item.qualifications.map((qualification, index) => <span key={qualification.id || index} data-category={qualification.category} className={qualification.id && item.matched_qualification_ids?.includes(qualification.id) ? 'matched' : ''}>{qualificationLabel(qualification)}{qualification.id && item.matched_qualification_ids?.includes(qualification.id) && <small>命中</small>}</span>) : <span className="bc-muted">—</span>}</div></td><td><div className="bc-primary-contact"><Phone size={16}/><span>{phones[0] || item.contact_name || item.email || '—'}</span></div>{(phones.length > 1 || (phones.length > 0 && (item.contact_name || item.email))) && <details className="bc-more-contact"><summary>更多联系</summary>{phones.slice(1).map(phone => <p key={phone}>{phone}</p>)}{item.contact_name && <p>{item.contact_name}</p>}{item.email && <p>{item.email}</p>}</details>}</td><td><div className="bc-row-actions"><button className="bc-button bc-primary" onClick={() => showCompany(item.id)}>查看详情</button>{website && <a className="bc-button" href={website} target="_blank" rel="noopener noreferrer" title={websiteType(item.website_kind).label}><ExternalLink size={15}/>{websiteType(item.website_kind).short}</a>}</div></td></tr>
      })}</tbody></table>{!currentList.data.items.length && <div className="bc-empty"><Building2 size={58} strokeWidth={1.2}/><strong>{currentList.data.total ? '该页暂无公司' : filtered ? '没有符合条件的公司' : '企业库暂无资料'}</strong><p>{currentList.data.total ? '请选择前面的页码。' : filtered ? '可调整名称或资质条件后重试。' : '已授权的公司资料录入后将在此展示。'}</p></div>}<div className="bc-pagination"><span>共 {currentList.data.total} 家</span><button className="bc-button" disabled={currentList.data.page <= 1} onClick={() => update(next => next.set('page', String(currentList.data!.page - 1)))}>上一页</button>{pageNumbers.map((page, index) => <span className="bc-page-number" key={page}>{index > 0 && page - pageNumbers[index - 1] > 1 && <span aria-hidden="true">…</span>}<button className={`bc-button${page === currentList.data!.page ? ' bc-primary' : ''}`} aria-label={`第 ${page} 页`} aria-current={page === currentList.data!.page ? 'page' : undefined} onClick={() => update(next => next.set('page', String(page)))}>{page}</button></span>)}<button className="bc-button" disabled={!currentList.data.has_more} onClick={() => update(next => next.set('page', String(currentList.data!.page + 1)))}>下一页</button><label>每页 <select aria-label="每页公司数量" value={currentList.data.page_size} onChange={event => update(next => { next.set('page_size', event.target.value); next.set('page', '1') })}>{![10, 20, 50, 100].includes(currentList.data.page_size) && <option value={currentList.data.page_size}>{currentList.data.page_size} 家</option>}{[10, 20, 50, 100].map(size => <option key={size} value={size}>{size} 家</option>)}</select></label></div></>}</section>
    </>}
    {editor && <CompanyEditor detail={editor.detail} onClose={closeEditor} onSaved={saved}/>}
  </div>
}
