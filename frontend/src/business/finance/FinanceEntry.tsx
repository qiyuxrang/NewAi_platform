import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, CheckCircle2, ClipboardList, Plus, RefreshCw, Save } from 'lucide-react'
import { useEnterprise } from '../../components/enterprise-context'
import { ApiError } from '../api'
import { installLedgerNavigationGuard } from '../ledgers/ledger-navigation'
import { entryCell, entryText, financeBookMode, financeDirty, financeEditable, financeEditorValidation, financeEntryError, financeSelection, loadFinanceEntry, newFinanceRecord, ownsFinanceRecord, publishFinanceRecords, reconcileFinanceEditor, recordIdentity, saveFinanceMetadata, saveFinanceRecord, sourceFinanceRecord } from './finance-entry'
import type { FinanceData, FinanceEditor, FinanceRecord, FinanceSelection } from './finance-entry'
import '../ledgers/ledger-entry.css'
import './finance-entry.css'

type Field = { key: string; label: string; money?: boolean; long?: boolean; multiline?: boolean; date?: boolean }
const sourceFields: Field[] = [
  { key: 'project_name', label: '项目名称' }, { key: 'client_name', label: '业主单位', multiline: true },
  { key: 'contract_amount', label: '合同金额', money: true }, { key: 'opening_receivable', label: '年初应收', money: true },
  { key: 'receivable_balance', label: '应收结余', money: true }, { key: 'owner', label: '回款负责人', multiline: true },
  { key: 'current_status', label: '目前状态', multiline: true, long: true },
]
const standardFields: Field[] = [sourceFields[0], sourceFields[2], { key: 'received_amount', label: '已收金额', money: true }, { key: 'due_date', label: '应收日期', date: true }]
const entityFields: Field[] = [{ key: 'contract_type', label: '类型', multiline: true }, { key: 'affiliate', label: '挂靠单位', multiline: true }, { key: 'billing_entity', label: '挂账主体', multiline: true }]
const stateLabel = { draft: '草稿', submitted: '已提交', published: '已发布' }

export function FinanceRecordForm({ data, editor, actor, busy, conflict, onChange, onSave, onClose }: {
  data: FinanceData; editor: FinanceEditor; actor: number | null; busy: boolean; conflict: boolean
  onChange: (row: FinanceRecord) => void; onSave: () => void; onClose: () => void
}) {
  const source = sourceFinanceRecord(editor.projectId ? editor.baseline : editor.draft)
  const sourceBook = data.ledger.records.some(sourceFinanceRecord)
  const sourceForm = source || !editor.projectId && sourceBook
  const readOnly = !financeEditable(data.ledger) || actor === null || !!editor.projectId && !ownsFinanceRecord(data.ledger, editor.baseline, actor)
  const renderField = (field: Field) => {
    const required = field.key === 'project_name' || field.key === 'contract_amount' || field.key === 'received_amount' && !source
    const common = { id: `finance-${field.key}`, value: entryText(editor.draft[field.key]), required, disabled: busy, readOnly,
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange({ ...editor.draft, [field.key]: event.target.value }) }
    return <label className={`ledger-field${field.long ? ' ledger-field-wide' : ''}`} key={field.key} htmlFor={common.id}>
      <span>{field.label}{field.money && (sourceForm ? '（原表单位未核实）' : '（元）')}{required && <span className="ledger-required" aria-label="必填"> *</span>}</span>
      {field.multiline ? <textarea {...common} rows={field.long ? 3 : 2} maxLength={200} /> : <input {...common} type={field.money ? 'number' : field.date ? 'date' : 'text'}
        min={field.money ? 0 : undefined} max={field.money ? 999999999999.99 : undefined} step={field.money ? '0.01' : undefined} maxLength={!field.money && !field.date ? 200 : undefined} />}
    </label>
  }
  return <section className="ledger-card ledger-editor" aria-labelledby="finance-editor-title">
    <div className="ledger-card-heading"><div><h2 id="finance-editor-title">{readOnly ? '查看记录' : editor.projectId ? '编辑本人记录' : '新增本人记录'}</h2><p>项目编号：{editor.draft.project_id} · 编辑基于 v{editor.revision}</p></div>
      <button type="button" className="ledger-button" disabled={busy} onClick={onClose}><ArrowLeft size={16} />返回列表</button></div>
    <form onSubmit={event => { event.preventDefault(); if (!readOnly && !busy && !conflict) onSave() }}>
      <fieldset className="ledger-form-grid" disabled={busy}>{(sourceForm ? sourceFields : standardFields).map(renderField)}{sourceForm && !source && standardFields.slice(2).map(renderField)}</fieldset>
      <p className="ledger-help">{source ? '原表单位未标注，保持原始数值；月份所属来源年度未核实，不由截止日期推定。未知金额保持空白，0 仅表示已确认的零。'
        : '标准记录按元填写；已收金额必填，应收日期可空。空白表示未知，不补 0 或伪造来源以绕过校验。'}</p>
      {!editor.projectId && sourceBook && <p className="ledger-help">新记录没有来源；仅在填写真实年初应收或应收结余后按源表校验。三者皆空时接口要求标准已收金额，纯源表台账禁止因此混入标准记录；未知值不能补 0 或假来源。</p>}
      <details className="ledger-details"><summary>主体及其他信息</summary><fieldset className="ledger-form-grid" disabled={busy}>
        {!sourceForm && sourceFields.filter(field => !['project_name', 'contract_amount', 'opening_receivable', 'receivable_balance'].includes(field.key) || ['opening_receivable', 'receivable_balance'].includes(field.key) && Object.hasOwn(editor.draft, field.key)).map(renderField)}
        {entityFields.map(renderField)}
        {source && (Object.hasOwn(editor.draft, 'received_amount') || Object.hasOwn(editor.draft, 'due_date')) && standardFields.slice(2).map(renderField)}
      </fieldset></details>
      {(sourceForm || Object.keys(editor.draft).some(key => /^(received_\d{2}|planned_\d{2})$/.test(key))) && <details className="ledger-details"><summary>月度回款（来源年度未核实）</summary>
        <div className="ledger-table-wrap"><table className="finance-months"><thead><tr><th>月份</th><th>口径</th><th>金额（原表单位未核实）</th></tr></thead><tbody>
          {Array.from({ length: 12 }, (_, i) => i + 1).map(month => { const key = `${month <= 7 ? 'received' : 'planned'}_${String(month).padStart(2, '0')}`
            return <tr key={key}><th>{month}月</th><td>{month <= 7 ? '实际回款' : '计划回款'}</td><td><input aria-label={`${month}月${month <= 7 ? '实际' : '计划'}回款`} type="number" min={0} max={999999999999.99} step="0.01" value={entryText(editor.draft[key])} readOnly={readOnly} disabled={busy} onChange={event => onChange({ ...editor.draft, [key]: event.target.value })} /></td></tr>
          })}</tbody></table></div></details>}
      {(Object.hasOwn(editor.draft, 'source_sheet') || Object.hasOwn(editor.draft, 'source_row')) && <div className="ledger-source"><p>来源信息（只读）</p><dl><div><dt>来源工作表</dt><dd>{entryCell(editor.draft.source_sheet)}</dd></div><div><dt>来源行</dt><dd>{entryCell(editor.draft.source_row)}</dd></div></dl></div>}
      <div className="ledger-form-actions"><p className="ledger-help">{readOnly ? '他人、归属未知记录或当前权限仅可查看。' : '先保存草稿，再选择本人精确版本确认发布。'}</p><button className="ledger-button ledger-primary" type="submit" disabled={busy || readOnly || conflict}><Save size={16} />保存草稿</button></div>
    </form>
  </section>
}

export default function FinanceEntry() {
  const { user, loading, error } = useEnterprise()
  if (loading) return <section className="ledger-entry finance-entry"><p role="status">正在核对财务身份…</p></section>
  if (!user) return <section className="ledger-entry finance-entry"><p role="alert">{error || '请先登录并核对业务绑定。'}</p></section>
  return <FinanceEntryPage key={user.portal_user_id ?? 'unknown'} actor={user.portal_user_id} />
}

function FinanceEntryPage({ actor }: { actor: number | null }) {
  const [data, setData] = useState<FinanceData | null>(null), [editor, setEditor] = useState<FinanceEditor | null>(null)
  const [cutoff, setCutoff] = useState<string | null>(null), [selected, setSelected] = useState<FinanceSelection[]>([])
  const [conflict, setConflict] = useState<{ before: number; latest: FinanceData | null } | null>(null)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [query, setQuery] = useState('')
  const lock = useRef(false), cutoffDirty = cutoff !== null && cutoff !== (data?.ledger.as_of ?? '')
  const dirty = financeDirty(editor) || cutoffDirty
  useEffect(() => {
    const controller = new AbortController()
    void loadFinanceEntry(controller.signal).then(result => { if (!controller.signal.aborted) { setData(result); setLoading(false) } })
      .catch(reason => { if (!controller.signal.aborted) { setError(financeEntryError(reason)); setLoading(false) } })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!dirty && !busy) return
    return installLedgerNavigationGuard(window, () => busy ? false : window.confirm('还有未保存的财务内容，确定离开当前页面？'))
  }, [dirty, busy])

  function report(reason: unknown) {
    setError(financeEntryError(reason))
    if (reason instanceof ApiError && [401, 403].includes(reason.status)) { setData(null); setLoading(false); setSelected([]) }
  }
  async function work(action: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setNotice('')
    try { await action() } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        const before = editor?.revision ?? data?.ledger.revision ?? 0
        setSelected([]); setConflict({ before, latest: null }); setError('版本已变化，未保存内容已保留。请读取最新版本并人工核对；不会自动重试。')
        try { const latest = await loadFinanceEntry(); setData(latest); setConflict({ before, latest }) } catch (readError) { report(readError) }
      } else report(reason)
    } finally { lock.current = false; setBusy(false) }
  }
  async function refresh() {
    const latest = await loadFinanceEntry()
    if (conflict || dirty && latest.ledger.revision !== (editor?.revision ?? data?.ledger.revision)) setConflict({ before: conflict?.before ?? editor?.revision ?? data?.ledger.revision ?? 0, latest })
    setData(latest); setSelected([]); setLoading(false)
  }
  async function afterMutation(ledger: FinanceData['ledger'], message: string) {
    setData({ ledger, published: null, publishedRevision: null }); setSelected([]); setNotice(message)
    setData(await loadFinanceEntry())
  }
  function open(record?: FinanceRecord) {
    if (!data || busy || conflict || cutoffDirty || financeDirty(editor) && !window.confirm('本次编辑尚未保存，确定放弃并打开其他记录？')) return
    const baseline = record ? { ...record } : newFinanceRecord()
    setEditor({ baseline, draft: { ...baseline }, projectId: record?.project_id ?? null, revision: data.ledger.revision }); setSelected([]); setError('')
  }
  function reconcile() {
    if (!conflict?.latest) return
    if (editor) {
      const result = reconcileFinanceEditor(editor, conflict.latest, actor)
      if (!result) { setError('记录已删除、归属或权限已变化，不能继续覆盖；请关闭编辑后核对最新列表。'); return }
      setEditor(result)
    }
    setSelected([]); setConflict(null); setError(''); setNotice('已核对最新版本，保留本次修改。请重新保存；发布记录须重新选择并确认。')
  }
  if (!data) return <section className="ledger-entry finance-entry"><header className="ledger-heading"><h1>财务填报</h1></header>{loading ? <p role="status">正在核对台账权限及已发布版本…</p> : <div className="ledger-card"><p role="alert">{error || '无法读取财务台账。'}</p><button className="ledger-button" disabled={busy} onClick={() => void work(refresh)}>重新读取</button></div>}</section>
  const { ledger } = data, editable = financeEditable(ledger) && actor !== null
  const mode = financeBookMode(ledger)
  const columns = mode === 'standard' ? standardFields : mode === 'mixed' ? [...sourceFields, ...standardFields.slice(2)] : sourceFields
  const snapshotSource = data.published?.records.filter(sourceFinanceRecord).length ?? 0
  const snapshotColumns = snapshotSource === 0 ? standardFields : snapshotSource < (data.published?.records.length ?? 0) ? [...sourceFields, ...standardFields.slice(2)] : sourceFields
  const workflowDisabled = busy || !!editor || !!conflict || cutoffDirty
  const latestRecord = editor?.projectId ? conflict?.latest?.ledger.records.find(row => row.project_id === editor.projectId) : undefined
  const differences = editor ? [...new Set([...Object.keys(latestRecord ?? {}), ...Object.keys(editor.draft)])].filter(key => latestRecord?.[key] !== editor.draft[key]) : []
  const rows = ledger.records.filter(row => [row.project_name, row.client_name, row.owner, row.current_status].some(value => entryText(value).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())))
  return <section className="ledger-entry finance-entry" aria-busy={busy}>
    <header className="ledger-heading"><div className="ledger-title"><span className="ledger-title-icon"><ClipboardList size={23} /></span><div><h1>财务填报</h1><p>维护本人记录，核对精确草稿版本后发布。</p></div></div><button className="ledger-button" disabled={busy} onClick={() => void work(refresh)}><RefreshCw size={16} />刷新数据</button></header>
    {error && <p className="ledger-alert" role="alert">{error}</p>}{notice && <p className="ledger-notice" role="status">{notice}</p>}
    {actor === null && <p className="ledger-alert">业务人员身份未核实，当前仅可查看。</p>}
    {conflict && <section className="ledger-conflict"><h2>版本冲突，请人工核对</h2><p>本次基于 v{conflict.before}；最新版本 {conflict.latest ? `v${conflict.latest.ledger.revision}` : '尚未读取成功'}。未保存内容保留，不会自动重试。</p>
      <p>最新截止日期：{entryCell(conflict.latest?.ledger.as_of)}；待保存日期：{entryCell(cutoff)}</p>
      {editor && <div className="ledger-table-wrap"><table className="ledger-table"><thead><tr><th>字段</th><th>最新记录</th><th>本次内容</th></tr></thead><tbody>{differences.map(key => <tr key={key}><th>{ledger.fields[key] || key}</th><td>{entryCell(latestRecord?.[key])}</td><td>{entryCell(editor.draft[key])}</td></tr>)}</tbody></table></div>}
      <div className="ledger-toolbar"><button className="ledger-button" disabled={busy} onClick={() => void work(refresh)}>读取最新版本</button><button className="ledger-button ledger-primary" disabled={busy || !conflict.latest} onClick={reconcile}>已核对，继续本次修改</button></div></section>}
    <section className="ledger-card ledger-summary"><div className="ledger-status-row"><span className={`ledger-status ledger-status-${ledger.state}`}>{stateLabel[ledger.state]}</span><span>台账 v{ledger.revision}</span><span>已发布版本：{data.publishedRevision === null ? '未核实' : data.publishedRevision === 0 ? '暂无' : `v${data.publishedRevision}`}</span><span>来源：{entryCell(ledger.source_name)}</span></div>
      <div className="ledger-summary-bottom"><form className="ledger-cutoff" onSubmit={event => { event.preventDefault(); if (!editable || busy || editor || conflict || !cutoffDirty || !cutoff) return; void work(async () => { const result = await saveFinanceMetadata(ledger.revision, cutoff); setCutoff(null); await afterMutation(result, '截止日期已保存。') }) }}>
        <label htmlFor="finance-cutoff">台账截止日期<input id="finance-cutoff" type="date" value={cutoff ?? ledger.as_of ?? ''} readOnly={!editable || !!editor} disabled={busy} onChange={event => setCutoff(event.target.value)} /></label>
        <button className="ledger-button" disabled={busy || !editable || !!editor || !!conflict || !cutoffDirty || !cutoff}>保存日期</button>{cutoffDirty && <button type="button" className="ledger-button" disabled={busy} onClick={() => setCutoff(null)}>恢复已保存日期</button>}
      </form></div><p className="ledger-help">截止日期不是月份所属年度。财务无需提交或退回；保存草稿不等于发布，发布只包含本人选定记录。</p>
      {data.publishedRevision === null && <p className="ledger-alert">已发布基线未核实，暂不能发布。请重新读取；版本列表达到 200 条且未找到发布版本时不能假定尚未发布。</p>}
      <details className="ledger-details"><summary>已发布快照（{data.published?.records.length ?? 0} 条）</summary>{data.published ? <><p>来源：{entryCell(data.published.source_name)} · 截止日期：{entryCell(data.published.as_of)} · {data.published.records.some(sourceFinanceRecord) ? '原表金额单位及月份年度未核实' : '标准金额单位：元'}</p><div className="ledger-table-wrap"><table className="ledger-table"><thead><tr>{snapshotColumns.map(field => <th key={field.key}>{field.label}</th>)}</tr></thead><tbody>{data.published.records.map(row => <tr key={row.project_id}>{snapshotColumns.map(field => <td key={field.key}>{entryCell(row[field.key])}</td>)}</tr>)}</tbody></table></div></> : <p>{data.publishedRevision === 0 ? '暂无已发布记录。' : '已发布快照未核实。'}</p>}</details>
    </section>
    {editor && <FinanceRecordForm data={data} editor={editor} actor={actor} busy={busy} conflict={!!conflict} onChange={draft => setEditor({ ...editor, draft })} onClose={() => { if (!busy && (!financeDirty(editor) || window.confirm('本次编辑尚未保存，确定返回列表？'))) setEditor(null) }}
      onSave={() => { if (!editable || conflict || editor.projectId && !ownsFinanceRecord(ledger, editor.baseline, actor)) return; const invalid = financeEditorValidation(editor, ledger); if (invalid) { setError(invalid); return } void work(async () => { const result = await saveFinanceRecord(editor, ledger); setEditor(null); await afterMutation(result, '本人草稿已保存，尚未发布。') }) }} />}
    <section className="ledger-card"><div className="ledger-card-heading"><div><h2>财务记录</h2><p>台账共 {ledger.records.length} 条；当前筛选 {rows.length} 条。他人及归属未知记录只读。</p></div><div className="ledger-toolbar"><input className="finance-search" type="search" aria-label="筛选项目、业主、负责人或状态" placeholder="项目 / 业主 / 负责人 / 状态" maxLength={100} value={query} onChange={event => setQuery(event.target.value)} /><button className="ledger-button ledger-primary" disabled={busy || !editable || !!conflict || cutoffDirty} onClick={() => open()}><Plus size={16} />新增记录</button></div></div>
      <p className="ledger-help">{mode === 'mixed' ? '台账存在源表与标准混合记录，保留各条原字段及口径；源表单位、月份年度未核实，标准金额单位为元。' : mode === 'source' ? '金额保留原始数值，原表单位未核实。月份所属年度未核实。' : '标准金额单位：元。'}</p>
      <div className="ledger-table-wrap"><table className="ledger-table finance-records"><thead><tr><th>发布</th>{columns.map(field => <th key={field.key}>{field.label}</th>)}<th>归属 / 操作</th></tr></thead><tbody>
        {rows.map(row => { const own = ownsFinanceRecord(ledger, row, actor), identity = recordIdentity(ledger, row), candidate = financeSelection(data, row, actor)
          return <tr key={row.project_id}><td><input type="checkbox" aria-label={`选择发布 ${row.project_name}`} disabled={workflowDisabled || !candidate} checked={selected.some(item => item.record_id === identity?.id)} onChange={event => { if (!candidate) return; const checked = event.target.checked; setSelected(current => checked ? [...current.filter(item => item.record_id !== candidate.record_id), candidate] : current.filter(item => item.record_id !== candidate.record_id)) }} /></td>{columns.map(field => <td key={field.key} title={entryText(row[field.key])}>{entryCell(row[field.key])}</td>)}<td><span className="finance-ownership">{own ? '本人' : Number.isSafeInteger(identity?.meta.record_author_id) && (identity?.meta.record_author_id ?? 0) > 0 ? '他人' : '归属未核实'}</span><button className="ledger-table-link" disabled={busy || !!conflict || cutoffDirty} onClick={() => open(row)}>{own && editable ? '编辑' : '查看'}</button></td></tr>
        })}{!rows.length && <tr><td colSpan={columns.length + 2} className="ledger-empty">没有符合条件的记录。</td></tr>}</tbody></table></div>
      <div className="ledger-form-actions"><p className="ledger-help">已选择 {selected.length} 条本人草稿。{selected.length > 0 && selected.some(item => !rows.some(row => recordIdentity(ledger, row)?.id === item.record_id)) ? '包含当前筛选外的记录；发布前请核对下面的精确清单。' : '作者及最后修改人须为本人，发布版本由后台再次校验。'}</p><button className="ledger-button ledger-primary" disabled={workflowDisabled || !editable || !selected.length || data.publishedRevision === null} onClick={() => {
        const names = selected.map(item => `${ledger.records.find(row => recordIdentity(ledger, row)?.id === item.record_id)?.project_name ?? item.record_id}（草稿 v${item.source_revision}）`).join('\n')
        if (!window.confirm(`确认发布以下本人精确草稿？\n${names}\n台账 v${ledger.revision}，已发布基线 v${data.publishedRevision}`)) return
        void work(async () => { const result = await publishFinanceRecords(data, selected, actor); await afterMutation(result, '选定本人记录已发布。') })
      }}><CheckCircle2 size={16} />确认发布本人记录</button></div>
      {selected.length > 0 && <details className="ledger-details"><summary>选定精确草稿清单（{selected.length} 条）</summary><ul>{selected.map(item => <li key={item.record_id}>{ledger.records.find(row => recordIdentity(ledger, row)?.id === item.record_id)?.project_name} · 草稿 v{item.source_revision}<br /><small>记录 {item.record_id} · 校验值 {item.source_checksum}</small></li>)}</ul></details>}
    </section>
  </section>
}
