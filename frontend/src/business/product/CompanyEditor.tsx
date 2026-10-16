import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { ApiError, apiRequest } from '../api'
import { baichuanError, draftFrom, emptyDraft, gradeName, qualificationTypes, safeWebsite, websiteTypes } from './Baichuan-data'
import type { CompanyDetailData, CompanyDraft, CompanyList, CompanyFields, Person, Qualification } from './Baichuan-data'

const baseLabels: [keyof CompanyFields, string, string?][] = [['name', '公司名称', 'text'], ['credit_code', '统一社会信用代码'], ['province', '省份'], ['city', '城市'], ['address', '详细地址'], ['website', '官方主页地址', 'url'], ['contact_name', '业务联系人'], ['contact_phone', '业务联系电话', 'tel'], ['phone', '公司电话', 'tel'], ['email', '邮箱', 'email'], ['source', '资料来源'], ['verified_on', '资料核实日期', 'date']]
const personLabels: [keyof Omit<Person, 'id'>, string][] = [['name', '姓名'], ['position', '岗位'], ['department', '部门'], ['specialties', '专业方向'], ['credentials', '职称认证'], ['achievements', '代表项目 / 成果'], ['reports_to_text', '有依据的汇报关系'], ['source', '来源'], ['verified_on', '核实日期']]

export default function CompanyEditor({ detail, onClose, onSaved }: { detail: CompanyDetailData | null; onClose: () => void; onSaved: (data: CompanyDetailData) => void }) {
  const initial = useRef(detail ? draftFrom(detail) : emptyDraft())
  const [draft, setDraft] = useState<CompanyDraft>(initial.current)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const dialog = useRef<HTMLDialogElement>(null), lock = useRef(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial.current)
  const leave = () => { if (!busy && (!dirty || window.confirm('还有未保存的公司资料，确定放弃修改？'))) onClose() }
  useEffect(() => { const element = dialog.current!; element.showModal(); element.querySelector<HTMLInputElement>('input')?.focus(); return () => element.close() }, [])
  useEffect(() => { if (!busy && Object.keys(errors).length) dialog.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus() }, [errors, busy])
  useEffect(() => {
    if (!dirty && !busy) return
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const guard = (event: Event) => { if (busy || !window.confirm('还有未保存的公司资料，确定离开？')) event.preventDefault() }
    window.addEventListener('beforeunload', unload); window.addEventListener('portal:navigation-guard', guard)
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('portal:navigation-guard', guard) }
  }, [dirty, busy])
  const company = (field: keyof CompanyFields, value: string) => setDraft(current => ({ ...current, company: { ...current.company, [field]: value } }))
  const qualification = (index: number, patch: Partial<Qualification>) => setDraft(current => ({ ...current, qualifications: current.qualifications.map((item, position) => position === index ? { ...item, ...patch } : item) }))
  const person = (index: number, field: keyof Person, value: string) => setDraft(current => ({ ...current, people: current.people.map((item, position) => position === index ? { ...item, [field]: value } : item) }))
  const remove = (key: 'qualifications' | 'people', index: number) => { if (window.confirm('确定移除此条资料？保存后将从公司资料中移除。')) setDraft(current => ({ ...current, [key]: current[key].filter((_, position) => position !== index) })) }
  async function save() {
    if (lock.current) return
    const invalid: Record<string, string> = {}
    if (!draft.company.name?.trim()) invalid.name = '请输入公司名称。'
    if (draft.company.credit_code?.trim() && !/^[0-9A-HJ-NPQRTUWXY]{18}$/.test(draft.company.credit_code.trim())) invalid.credit_code = '统一社会信用代码须为18位大写字母或数字。'
    if (draft.company.website && !safeWebsite(draft.company.website)) invalid.website = '请输入不带用户名密码的 HTTP(S) 官网地址。'
    draft.people.forEach((item, index) => { if (!item.name.trim()) invalid[`person-${index}-name`] = '请输入人员姓名，或明确移除此条记录。' })
    qualificationTypes.forEach(type => {
      const rows = draft.qualifications.filter(item => item.category === type.code)
      if (rows.length > 1 && rows.some(item => item.status !== 'PRESENT')) invalid[`qualification-${type.code}`] = '同类别多条记录必须均为具备；未知或不具备不能与其他记录并存，请人工核对。'
    })
    setErrors(invalid); setError('')
    if (Object.keys(invalid).length) return
    lock.current = true; setBusy(true)
    try {
      // Name is intentionally non-unique; ask for a human decision before writing.
      let page = 1, duplicate = false
      do {
        const found = await apiRequest<CompanyList>(`/api/product/baichuan/companies/?q=${encodeURIComponent(draft.company.name!.trim())}&page=${page}&page_size=100`)
        duplicate = found.items.some(item => item.id !== detail?.company.id && item.name.trim() === draft.company.name!.trim())
        if (duplicate || !found.has_more) break
        page++
      } while (!duplicate)
      if (duplicate && !window.confirm('发现同名公司，可能存在重复资料。请核对信用代码和来源；同名不同公司可分别保存。确认仍要保存？')) return
      const payload: CompanyDraft = { ...draft, company: Object.fromEntries(Object.entries(draft.company).map(([key, value]) => [key, value?.trim() || null])) as CompanyFields, people: draft.people.map(item => ({ ...item, verified_on: item.verified_on || null })) }
      const result = await apiRequest<CompanyDetailData>(`/api/product/baichuan/companies/${detail ? `${encodeURIComponent(detail.company.id)}/` : ''}`, { method: detail ? 'PUT' : 'POST', body: JSON.stringify(payload) })
      onSaved(result)
    } catch (reason) {
      setError(baichuanError(reason))
      if (reason instanceof ApiError && reason.errors) {
        const fields: Record<string, string> = {}
        for (const [path, message] of Object.entries(reason.errors)) {
          const key = path.replace(/^company\./, '').replace(/^people\.(\d+)\./, 'person-$1-')
          const qualificationIndex = path.match(/^qualifications\.(\d+)/)?.[1]
          fields[qualificationIndex ? `qualification-${draft.qualifications[Number(qualificationIndex)]?.category}` : key] = message
        }
        setErrors(fields)
      }
    }
    finally { lock.current = false; setBusy(false) }
  }
  return <dialog ref={dialog} className="bc-editor bc" aria-labelledby="bc-editor-title" onCancel={event => { event.preventDefault(); leave() }}>
    <form onSubmit={event => { event.preventDefault(); void save() }}>
      <header><div><h2 id="bc-editor-title">{detail ? '编辑公司资料' : '新增公司'}</h2><p>基础资料、企业资质与核心人员统一保存；空白信息可后续补充。</p></div><button type="button" className="bc-icon-button" aria-label="关闭公司表单" disabled={busy} onClick={leave}><X size={20}/></button></header>
      <div className="bc-editor-body">
        <fieldset disabled={busy}><legend>基础资料与联系</legend><div className="bc-form-grid">{baseLabels.map(([field, label, type]) => <label key={field}>{label}{field === 'name' && <span aria-hidden="true"> *</span>}<input name={field} type={type || 'text'} required={field === 'name'} value={draft.company[field] || ''} onChange={event => company(field, event.target.value)} aria-invalid={!!errors[field]} aria-describedby={errors[field] ? `bc-error-${field}` : undefined}/>{errors[field] && <small id={`bc-error-${field}`} className="bc-field-error">{errors[field]}</small>}</label>)}<label>官方主页类型<select name="website_kind" value={draft.company.website_kind || 'corporate'} onChange={event => company('website_kind', event.target.value)} aria-invalid={!!errors.website_kind}>{websiteTypes.map(item => <option key={item.code} value={item.code}>{item.label}</option>)}</select>{errors.website_kind && <small className="bc-field-error">{errors.website_kind}</small>}</label><label className="bc-wide">公司简介<textarea name="description" rows={3} value={draft.company.description || ''} onChange={event => company('description', event.target.value)}/></label></div></fieldset>
        <fieldset disabled={busy}><legend>企业资质</legend><p className="bc-muted">无记录表示尚未提供。未知等级不等于不具备；同类别可保留多份具备的证书。</p>{qualificationTypes.map(type => <section className="bc-qualification-editor" key={type.code}><div className="bc-section-heading"><h3>{type.label}</h3><button type="button" className="bc-link" onClick={() => setDraft(current => ({ ...current, qualifications: [...current.qualifications, { category: type.code, status: 'UNKNOWN', grade: null, certificate_no: null, valid_until: null, source: null, verified_on: null }] }))}><Plus size={15}/>添加记录</button></div>{!draft.qualifications.some(item => item.category === type.code) && <p className="bc-muted">尚未提供</p>}{draft.qualifications.map((item, index) => item.category === type.code && <div className="bc-subrecord" key={item.id || index}><div className="bc-form-grid"><label>具备状态<select value={item.status} aria-invalid={!!errors[`qualification-${type.code}`]} onChange={event => qualification(index, { status: event.target.value as Qualification['status'], grade: event.target.value === 'PRESENT' ? item.grade : null })}><option value="UNKNOWN">待核实</option><option value="ABSENT">不具备</option><option value="PRESENT">具备</option></select></label>{item.status === 'PRESENT' && type.code !== 'labor' && <label>精确等级<select value={item.grade || ''} onChange={event => qualification(index, { grade: event.target.value || null })}><option value="">等级待补充</option>{type.grades.map(grade => <option key={grade} value={grade}>{gradeName(grade)}</option>)}</select></label>}{([['certificate_no', '证书编号'], ['valid_until', '有效期至'], ['source', '来源'], ['verified_on', '核实日期']] as const).map(([field, label]) => <label key={field}>{label}<input type={field === 'valid_until' || field === 'verified_on' ? 'date' : 'text'} value={item[field] || ''} onChange={event => qualification(index, { [field]: event.target.value || null })}/></label>)}</div><button type="button" className="bc-remove" onClick={() => remove('qualifications', index)}>移除此条资质</button></div>)}{errors[`qualification-${type.code}`] && <p className="bc-field-error">{errors[`qualification-${type.code}`]}</p>}</section>)}</fieldset>
        <fieldset disabled={busy}><legend>核心人员（选填）</legend><p className="bc-muted">仅记录已提供的能力与组织关系，个人证书不参与企业资质筛选。</p>{draft.people.map((item, index) => <section className="bc-subrecord" key={item.id || index}><h3>人员 {index + 1}</h3><div className="bc-form-grid">{personLabels.map(([field, label]) => <label key={field}>{label}{field === 'name' && ' *'}<input type={field === 'verified_on' ? 'date' : 'text'} required={field === 'name'} value={item[field] || ''} aria-invalid={!!errors[`person-${index}-${field}`]} onChange={event => person(index, field, event.target.value)}/>{errors[`person-${index}-${field}`] && <small className="bc-field-error">{errors[`person-${index}-${field}`]}</small>}</label>)}</div><button type="button" className="bc-remove" onClick={() => remove('people', index)}>移除此人</button></section>)}<button type="button" className="bc-button" onClick={() => setDraft(current => ({ ...current, people: [...current.people, { name: '', department: null, position: null, reports_to_text: null, specialties: null, credentials: null, achievements: null, source: null, verified_on: null }] }))}><Plus size={16}/>添加人员</button></fieldset>
        {error && <p className="bc-error" role="alert">{error}</p>}
      </div>
      <footer><span role="status">{busy ? '正在核对并保存…' : dirty ? '有未保存的修改' : '尚未修改'}</span><button type="button" className="bc-button" disabled={busy} onClick={leave}>取消</button><button className="bc-button bc-primary" disabled={busy}>{busy ? '保存中…' : '保存公司资料'}</button></footer>
    </form>
  </dialog>
}
