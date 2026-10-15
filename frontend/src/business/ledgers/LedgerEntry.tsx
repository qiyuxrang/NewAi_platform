import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, CheckCircle2, ClipboardList, Plus, RefreshCw, Save, Send } from 'lucide-react'
import { ApiError } from '../api'
import { getAuthorizedLedger, ledgerMutation, saveLedgerRecord } from './ledger-api'
import { installLedgerNavigationGuard } from './ledger-navigation'
import { cellText, editorIsDirty, entryTitles, inputText, isSourceRecord, ledgerActions, missingEntryFields, newLedgerRecord, reconcileEditor, requiredEntryFields, sourceLabels } from './ledger-state'
import type { Ledger, LedgerDepartment, LedgerEditor, LedgerRecord } from './ledger-state'
import './ledger-entry.css'

const stateLabels = { draft: '草稿', submitted: '已提交 · 待发布', published: '已发布' }
type EntryField = { key: string; label: string; kind?: 'text' | 'date' | 'number' | 'textarea' | 'status'; long?: boolean; limit?: number }
const presalesFields: EntryField[] = [
  { key: 'project_name', label: '项目名称' }, { key: 'owner', label: '跟进人员', kind: 'textarea' },
  { key: 'status', label: '项目阶段', kind: 'status' }, { key: 'follow_up_date', label: '跟进日期', kind: 'date' },
  { key: 'project_progress', label: '项目进展', kind: 'textarea', long: true, limit: 4000 },
  { key: 'amount', label: '预计金额（元）', kind: 'number' },
]
const engineeringFields: EntryField[] = [
  { key: 'project_name', label: '项目名称' }, { key: 'owner', label: '项目负责人' },
  { key: 'status', label: '实施状态', kind: 'status' }, { key: 'planned_end', label: '计划完成', kind: 'date' },
  { key: 'progress', label: '完成进度（%）', kind: 'number' },
]
const commonDetails: EntryField[] = [
  { key: 'description', label: '项目概况', kind: 'textarea', long: true, limit: 4000 },
  { key: 'client_contact', label: '甲方对接人', kind: 'textarea' },
  { key: 'project_type', label: '项目定型', kind: 'textarea' }, { key: 'maturity', label: '成熟度', kind: 'textarea' },
]
const sourceDetails: EntryField[] = [
  { key: 'expected_signing', label: '预计签约时间' },
  { key: 'annual_plan', label: '推进计划', kind: 'textarea', long: true, limit: 4000 },
  { key: 'notes', label: '备注', kind: 'textarea', long: true, limit: 4000 },
  { key: 'follow_up_history', label: '已有跟进记录', kind: 'textarea', long: true, limit: 20000 },
]

export function LedgerRecordForm({ department, ledger, editor, busy, conflict, onChange, onSave, onClose }: {
  department: LedgerDepartment; ledger: Ledger; editor: LedgerEditor; busy: boolean; conflict: boolean
  onChange: (record: LedgerRecord) => void; onSave: () => void; onClose: () => void
}) {
  const source = isSourceRecord(editor.draft, department)
  const readOnly = !ledgerActions(ledger).edit
  const required = requiredEntryFields(department, editor.draft)
  const renderField = (field: EntryField) => {
    const value = inputText(editor.draft[field.key]), mustFill = required.includes(field.key)
    const label = field.key === 'amount' && source ? '折算金额（元）' : field.label
    const common = { id: `entry-${field.key}`, value, required: mustFill, disabled: busy, readOnly,
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => onChange({ ...editor.draft, [field.key]: event.target.value }) }
    return <label className={`ledger-field${field.long ? ' ledger-field-wide' : ''}`} key={field.key} htmlFor={common.id}>
      <span>{label}{mustFill && <span className="ledger-required" aria-label="必填"> *</span>}</span>
      {field.kind === 'status' ? <select {...common} disabled={busy || readOnly} aria-readonly={readOnly}>
        <option value="">{mustFill ? '请选择' : '未标注'}</option>{ledger.statuses.map(status => <option value={status} key={status}>{status}</option>)}
      </select> : field.kind === 'textarea' ? <textarea {...common} maxLength={field.limit ?? 200} rows={field.long ? 3 : 2} />
        : <input {...common} type={field.kind ?? 'text'} maxLength={field.kind === 'text' || !field.kind ? 200 : undefined}
          min={field.kind === 'number' ? 0 : undefined} max={field.key === 'progress' ? 100 : field.kind === 'number' ? 999999999999.99 : undefined}
          step={field.kind === 'number' ? '0.01' : undefined} />}
    </label>
  }
  return <section className="ledger-card ledger-editor" aria-labelledby="ledger-editor-title">
    <div className="ledger-card-heading"><div><h2 id="ledger-editor-title">{editor.projectId ? readOnly ? '查看项目' : '编辑项目' : '新增项目'}</h2>
      <p>项目编号：{editor.draft.project_id} · 当前编辑版本 v{editor.revision}</p></div>
      <button className="ledger-button" type="button" disabled={busy} onClick={onClose}><ArrowLeft size={16} />返回列表</button></div>
    <form onSubmit={event => { event.preventDefault(); if (!readOnly && !conflict && !busy) onSave() }}>
      <fieldset disabled={busy} className="ledger-form-grid">{(department === 'presales' ? presalesFields : engineeringFields).map(renderField)}</fieldset>
      {department === 'engineering' ? <p className="ledger-help">进度由负责人确认。未知进度保持空白，现有规则不允许保存；0% 仅表示已确认尚未完成。</p>
        : <><p className="ledger-help">{source ? '按本条来源记录填写；未知阶段、日期或折算金额可保留空白。原始额度与单位保持原值。' : '标准记录须填写阶段和预计金额；空白表示未知，不会自动填成 0。'}</p>
          <details className="ledger-details"><summary>其他信息</summary><fieldset disabled={busy} className="ledger-form-grid">
            {commonDetails.map(renderField)}{source && sourceDetails.map(renderField)}
          </fieldset>{source && <div className="ledger-source" aria-label="导入来源信息">
            <p>导入来源（只读）</p><dl>{Object.entries(sourceLabels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{cellText(editor.draft[key])}</dd></div>)}</dl>
            {!inputText(editor.draft.amount_unit).trim() && <p>原表单位未标注，不根据原始额度推算折算金额。</p>}
          </div>}</details></>}
      <div className="ledger-form-actions"><p className="ledger-help">{readOnly ? '当前台账或账号仅可查看。' : '保存为草稿；提交和发布须按台账授权分别操作。'}</p>
        <button className="ledger-button ledger-primary" type="submit" disabled={busy || readOnly || conflict}><Save size={16} />{busy ? '处理中…' : '保存草稿'}</button></div>
    </form>
  </section>
}

export default function LedgerEntry({ department }: { department: LedgerDepartment }) {
  return <LedgerPage key={department} department={department} />
}

function LedgerPage({ department }: { department: LedgerDepartment }) {
  const [ledger, setLedger] = useState<Ledger | null>(null)
  const [editor, setEditor] = useState<LedgerEditor | null>(null)
  const [cutoff, setCutoff] = useState<string | null>(null)
  const [returnReason, setReturnReason] = useState('')
  const [conflict, setConflict] = useState<{ beforeRevision: number; latest: Ledger | null } | null>(null)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [query, setQuery] = useState('')
  const lock = useRef(false)
  const cutoffDirty = cutoff !== null && cutoff !== (ledger?.as_of ?? '')
  const unsaved = editorIsDirty(editor) || cutoffDirty || !!returnReason.trim()

  useEffect(() => {
    const controller = new AbortController()
    void getAuthorizedLedger(department, controller.signal).then(value => {
      if (!controller.signal.aborted) { setLedger(value); setLoading(false) }
    }).catch(reason => { if (!controller.signal.aborted) { setError(errorMessage(reason)); setLoading(false) } })
    return () => controller.abort()
  }, [department])

  useEffect(() => {
    if (!unsaved && !busy) return
    return installLedgerNavigationGuard(window, () => {
      if (busy) { setNotice('正在处理台账，请等待结果后离开。'); return false }
      return window.confirm('还有未保存的填报内容，确定离开当前页面？')
    })
  }, [unsaved, busy])

  function reportError(reason: unknown) {
    setError(errorMessage(reason))
    if (reason instanceof ApiError && [401, 403].includes(reason.status)) setLedger(null)
  }

  async function work(action: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try { await action() } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        const beforeRevision = editor?.revision ?? ledger?.revision ?? 0
        setConflict({ beforeRevision, latest: null })
        setError('台账已被更新。本次未保存内容已保留，请读取并核对最新版本后继续。')
        try {
          const latest = await getAuthorizedLedger(department)
          setLedger(latest); setConflict({ beforeRevision, latest })
        } catch (readError) { reportError(readError) }
      } else reportError(reason)
    } finally { lock.current = false; setBusy(false) }
  }

  async function refresh() {
    const latest = await getAuthorizedLedger(department)
    if (conflict) setConflict({ ...conflict, latest })
    else if (editor && latest.revision !== editor.revision || ledger && latest.revision !== ledger.revision && unsaved) setConflict({ beforeRevision: editor?.revision ?? ledger?.revision ?? 0, latest })
    setLedger(latest); setLoading(false)
  }

  function openEditor(record?: LedgerRecord) {
    if (!ledger || busy || cutoffDirty || returnReason.trim() || conflict) return
    if (editorIsDirty(editor) && !window.confirm('本次编辑尚未保存，确定放弃并打开其他记录？')) return
    const baseline = record ? { ...record } : newLedgerRecord(department)
    setEditor({ baseline, draft: { ...baseline }, projectId: record?.project_id ?? null, revision: ledger.revision })
    setError(''); setNotice('')
  }

  function closeEditor() {
    if (busy || editorIsDirty(editor) && !window.confirm('本次编辑尚未保存，确定返回列表？')) return
    setEditor(null)
  }

  async function saveRecord() {
    if (!ledger || !editor || conflict || !ledgerActions(ledger).edit) return
    const missing = missingEntryFields(department, editor.draft)
    if (missing.length) { setError(`请填写${missing.map(key => ledger.fields[key] || key).join('、')}；未知值不能用 0 代替。`); return }
    const result = await saveLedgerRecord(department, editor.revision, editor.draft, editor.projectId)
    setLedger(result); setEditor(null); setNotice('草稿已保存，尚未提交或发布。')
  }

  async function action(kind: 'submit' | 'publish' | 'return' | 'metadata') {
    if (!ledger || conflict || editor) return
    const allowed = ledgerActions(ledger)
    if (kind === 'metadata' ? !allowed.edit || !cutoffDirty || !cutoff : !allowed[kind]) return
    if (kind !== 'metadata' && cutoffDirty || kind !== 'return' && returnReason.trim()) return
    const result = await ledgerMutation(department, ledger.revision, kind, kind === 'metadata' ? { as_of: cutoff! } : kind === 'return' ? { reason: returnReason.trim() } : {})
    setLedger(result)
    if (kind === 'metadata') setCutoff(null)
    if (kind === 'return') setReturnReason('')
    setNotice(kind === 'submit' ? '台账已提交，等待授权发布。' : kind === 'publish' ? '台账已发布。' : kind === 'return' ? '台账已退回，可继续编辑。' : '台账截止日期已保存。')
  }

  function acknowledgeConflict() {
    if (!conflict?.latest) return
    if (editor) {
      const reconciled = reconcileEditor(editor, conflict.latest)
      if (!reconciled) { setError('该记录已被删除，请关闭编辑并核对列表。'); return }
      setEditor(reconciled)
    }
    setConflict(null); setError(''); setNotice(editor ? '已核对最新版本。本次修改已保留，其他字段采用最新记录；请再点击保存。' : '已核对最新版本，请按最新台账状态继续操作。')
  }

  const title = entryTitles[department]
  if (!ledger) return <section className="ledger-entry"><header className="ledger-heading"><ClipboardList size={24} /><h1>{title}</h1></header>
    {loading ? <p role="status">正在核对台账权限…</p> : <div className="ledger-card"><p role="alert">{error || '无法读取台账。'}</p>
      <div className="ledger-toolbar"><button className="ledger-button" type="button" disabled={busy} onClick={() => void work(refresh)}>重新读取</button>
        <a className="ledger-button" href="/settings/business-link">检查业务绑定</a></div></div>}
  </section>

  const allowed = ledgerActions(ledger), workflowDisabled = busy || !!conflict || !!editor || cutoffDirty
  const columns = department === 'engineering' ? engineeringFields : presalesFields
  const rows = ledger.records.filter(row => [row.project_name, row.owner, row.status].some(value => inputText(value).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())))
  const currentRecord = editor?.projectId ? conflict?.latest?.records.find(row => row.project_id === editor.projectId) : undefined
  const differingKeys = editor ? [...new Set([...Object.keys(currentRecord ?? {}), ...Object.keys(editor.draft)])].filter(key => editor.draft[key] !== currentRecord?.[key]) : []

  return <section className="ledger-entry" aria-busy={busy}>
    <header className="ledger-heading"><div className="ledger-title"><span className="ledger-title-icon"><ClipboardList size={23} /></span><div><h1>{title}</h1><p>维护项目台账，按授权保存、提交与发布。</p></div></div>
      <button className="ledger-button" type="button" disabled={busy} onClick={() => void work(refresh)}><RefreshCw size={16} />刷新数据</button></header>
    {error && <p className="ledger-alert" role="alert">{error}</p>}{notice && <p className="ledger-notice" role="status">{notice}</p>}
    {conflict && <section className="ledger-conflict" aria-label="版本冲突核对"><h2>请核对版本变化</h2>
      <p>本次操作基于 v{conflict.beforeRevision}；{conflict.latest ? `最新台账为 v${conflict.latest.revision}（${stateLabels[conflict.latest.state]}）。` : '最新版本尚未读取成功。'}未保存内容仍保留，不会自动重试。</p>
      {conflict.latest && <><p>最新截止日期：{cellText(conflict.latest.as_of)}{cutoffDirty ? `；本次待保存日期：${cellText(cutoff)}` : ''}</p>
        {editor && <><p>{editor.projectId && !currentRecord ? '该记录已从最新台账删除，请关闭编辑并核对。' : '核对以下差异；确认后保留本次修改，其他字段采用最新记录。'}</p>
          <div className="ledger-table-wrap"><table className="ledger-table"><thead><tr><th>字段</th><th>最新记录</th><th>本次未保存内容</th></tr></thead>
            <tbody>{differingKeys.map(key => <tr key={key}><th>{sourceLabels[key] || ledger.fields[key] || key}</th><td>{cellText(currentRecord?.[key])}</td><td>{cellText(editor.draft[key])}</td></tr>)}</tbody></table></div></>}
      </>}
      <div className="ledger-toolbar"><button type="button" className="ledger-button" disabled={busy} onClick={() => void work(refresh)}>读取最新版本</button>
        <button type="button" className="ledger-button ledger-primary" disabled={busy || !conflict.latest || !!editor?.projectId && !currentRecord} onClick={acknowledgeConflict}>已核对，继续本次修改</button></div>
    </section>}
    <section className="ledger-card ledger-summary" aria-label="台账状态">
      <div className="ledger-status-row"><span className={`ledger-status ledger-status-${ledger.state}`}>{stateLabels[ledger.state]}</span><span>v{ledger.revision}</span><span>{ledger.records.length} 条记录</span><span>数据来源：{ledger.source_name || '—'}</span>
        <span>{ledger.updated_by ? `最近操作：${ledger.updated_by.name}` : '暂无操作记录'}</span></div>
      {ledger.last_return_reason && <p className="ledger-help">退回原因：{ledger.last_return_reason}</p>}
      <div className="ledger-summary-bottom"><form className="ledger-cutoff" onSubmit={(event: FormEvent) => { event.preventDefault(); void work(() => action('metadata')) }}>
        <label htmlFor="ledger-cutoff">台账截止日期<input id="ledger-cutoff" type="date" required value={cutoff ?? ledger.as_of ?? ''} readOnly={!allowed.edit || !!editor} disabled={busy} onChange={event => setCutoff(event.target.value)} /></label>
        <button type="submit" className="ledger-button" disabled={busy || !allowed.edit || !!editor || !!conflict || !cutoffDirty || !cutoff || !!returnReason.trim()}>保存日期</button>
        {cutoffDirty && <button type="button" className="ledger-button" disabled={busy} onClick={() => setCutoff(null)}>恢复已保存日期</button>}
      </form><div className="ledger-toolbar"><button className="ledger-button" type="button" disabled={workflowDisabled || !allowed.submit || !!returnReason.trim()} onClick={() => void work(() => action('submit'))}><Send size={16} />提交台账</button>
        <button className="ledger-button ledger-primary" type="button" disabled={workflowDisabled || !allowed.publish || !!returnReason.trim()} onClick={() => void work(() => action('publish'))}><CheckCircle2 size={16} />发布台账</button></div></div>
      <p className="ledger-help">{ledger.state === 'submitted' ? '台账已提交，修改须由授权发布人退回。' : ledger.state === 'published' ? '编辑已发布台账后将形成新草稿，已有发布版本保留。' : '草稿保存后仍须授权提交、发布；提交需要有效的台账截止日期。'}</p>
      {(allowed.return || !!returnReason) && <form className="ledger-return" onSubmit={event => { event.preventDefault(); void work(() => action('return')) }}>
        <label htmlFor="ledger-return-reason">退回原因<textarea id="ledger-return-reason" rows={2} required maxLength={500} value={returnReason} disabled={busy || !!editor} onChange={event => setReturnReason(event.target.value)} /></label>
        <button className="ledger-button" type="submit" disabled={workflowDisabled || !allowed.return || !returnReason.trim()}>退回修改</button>
        {returnReason && <button className="ledger-button" type="button" disabled={busy} onClick={() => setReturnReason('')}>清空退回原因</button>}
      </form>}
    </section>
    {editor && <LedgerRecordForm department={department} ledger={ledger} editor={editor} busy={busy} conflict={!!conflict}
      onChange={record => setEditor({ ...editor, draft: record })} onSave={() => void work(saveRecord)} onClose={closeEditor} />}
    <section className="ledger-card" aria-labelledby="ledger-list-title"><div className="ledger-card-heading"><div><h2 id="ledger-list-title">项目记录</h2><p>共 {ledger.records.length} 条{query.trim() ? `，筛选后 ${rows.length} 条` : ''}</p></div>
      <div className="ledger-toolbar"><label className="ledger-search"><span className="ledger-sr-only">筛选项目、负责人或状态</span><input type="search" placeholder="项目 / 负责人 / 状态" value={query} onChange={event => setQuery(event.target.value)} maxLength={100} /></label>
        <button className="ledger-button ledger-primary" type="button" disabled={busy || !allowed.edit || cutoffDirty || !!returnReason.trim() || !!conflict} onClick={() => openEditor()}><Plus size={16} />新增项目</button></div></div>
      <div className="ledger-table-wrap"><table className="ledger-table"><thead><tr>{columns.map(field => <th key={field.key}>{field.key === 'amount' && ledger.records.some(row => isSourceRecord(row, department)) ? '预计 / 折算金额（元）' : field.label}</th>)}<th>操作</th></tr></thead><tbody>
        {rows.map(row => <tr key={row.project_id}>{columns.map(field => <td key={field.key} className={field.key === 'project_progress' ? 'ledger-progress-cell' : undefined} title={inputText(row[field.key])}>
          {cellText(row[field.key])}{field.key === 'progress' && inputText(row.progress) !== '' ? '%' : ''}</td>)}
          <td><button className="ledger-table-link" type="button" disabled={busy || cutoffDirty || !!returnReason.trim() || !!conflict} onClick={() => openEditor(row)}>{allowed.edit ? '编辑' : '查看'}</button></td></tr>)}
        {!rows.length && <tr><td colSpan={columns.length + 1} className="ledger-empty">{query.trim() ? '没有符合条件的项目。' : '暂无台账记录。'}</td></tr>}
      </tbody></table></div>
    </section>
  </section>
}

function errorMessage(reason: unknown): string {
  if (reason instanceof ApiError && reason.status === 401) return '登录或业务绑定已失效，请重新登录或检查业务绑定。'
  if (reason instanceof ApiError && reason.status === 403) return `无台账权限：${reason.message}`
  return reason instanceof Error ? reason.message : '台账请求失败，请稍后重试。'
}
