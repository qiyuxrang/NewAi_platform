import { useEffect, useRef, useState } from 'react'
import { Download, Paperclip, RotateCcw, Send, Square, X } from 'lucide-react'
import { useEnterprise } from '../../components/enterprise-context'
import { apiEventStream, apiRequest, downloadBusinessFile, isApiError } from '../api'
import { assistantRoot, assistantStorageKey, capabilityAvailable, conditionLabel, jobActive, jobLabel,
  latestCurrentSnapshot, validateAttachment, verdictLabel } from './BaichuanAssistant-data'
import type { AssistantConfig, AssistantConversation, AssistantJob, AssistantResult } from './BaichuanAssistant-data'
import { safeWebsite } from './Baichuan-data'
import mascot from './assets/baichuan/assistant-mascot.webp'
import './BaichuanAssistant.css'

function messageFor(reason: unknown): string {
  if (isApiError(reason) && reason.status === 409) return '条件已更新，请等候同步后重试。当前输入已保留。'
  if (reason instanceof TypeError && /failed to fetch|networkerror|load failed|network request failed/i.test(reason.message)) {
    return '连接暂时不可用，当前输入已保留，请检查网络后重试。'
  }
  return reason instanceof Error ? reason.message : '连接暂时不可用，当前输入已保留，请重试。'
}
type DraftFile = { file: File; id?: string }

// Content projection only: keep durable messages, matching and source records intact.
function enterpriseReply(content: string): string {
  const stages = new Set(['已接收本轮需求，任务在后台继续。', '正在读取附件正文，未能识别的内容不会推测。',
    '正在理解需求，区分硬性要求、优先项和证书主体。', '检索条件已校验，正在按当前库资料逐项匹配。'])
  return content.split('\n').filter(line => ![...stages].some(stage => line.trim() && stage.startsWith(line.trim()))).join('\n')
    .replace(/^已检索当前授权库：已确认 \d+ 家，待核实 \d+ 家，排除 \d+ 家。/, '')
    .replace('本次在库范围为空，不能据此判断市场上不存在符合条件的企业。', '当前库暂无企业。').trim()
}

type CompanyResult = NonNullable<AssistantResult['results']>[number]

function CompanyInfo({ item, conditions }: { item: CompanyResult; conditions: unknown }) {
  const company = item.company as Record<string, unknown> | undefined
  const fields: [string, string][] = [['province', '省份'], ['city', '城市'], ['address', '地址'],
    ['website', '官网'], ['email', '邮箱'], ['contact_name', '联系人'], ['contact_phone', '联系电话']]
  // A satisfied positive qualification can be displayed as a matching item.
  // Unknown/failed/negative predicates must never become company credentials.
  const qualifications = [...new Set((item.conditions || []).flatMap(condition => {
    if (condition.verdict !== 'satisfied') return []
    const label = conditionLabel(conditions, condition.condition_id)
    if (!/^(硬性要求|优先项) · (电子与智能化|施工劳务|CS|CMMI|CCRC|ITSS|安防工程) /.test(label)) return []
    return [label.replace(/^硬性要求 · /, '').replace(/（投标企业）$/, '')
      .replace(/ 等级精确为 ([1-5])$/, (_, grade: string) => ` · ${['一', '二', '三', '四', '五'][Number(grade) - 1]}级`)]
  }))]
  return <>{fields.map(([field, label]) => {
    const value = company?.[field]
    if (typeof value !== 'string' || !value.trim()) return null
    const url = field === 'website' ? safeWebsite(value) : null
    if (field === 'website' && !url) return null
    return <div className="bca-condition" key={field}><small>{label}</small>{url
      ? <a href={url} target="_blank" rel="noopener noreferrer">{value}</a> : <strong>{value}</strong>}</div>
  })}{qualifications.map(value => <div className="bca-condition" key={value}><small>资质</small><strong>{value}</strong></div>)}</>
}

function OwnedAssistant({ owner, portalOwner, onCompany }: { owner: string; portalOwner: number | null; onCompany: (id: string) => void }) {
  const storageKey = assistantStorageKey(window.location.origin, owner, portalOwner)
  const [config, setConfig] = useState<AssistantConfig | null>(null)
  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState(() => {
    try { return window.localStorage.getItem(storageKey) || '' } catch { return '' }
  })
  const [conversation, setConversation] = useState<AssistantConversation | null>(null)
  const [result, setResult] = useState<AssistantResult | null>(null)
  const [resultPage, setResultPage] = useState(1), [resultLoading, setResultLoading] = useState(false)
  const [listSnapshot, setListSnapshot] = useState<{ id: string; revision: number } | null>(null)
  const [listResult, setListResult] = useState<AssistantResult | null>(null)
  const [listPage, setListPage] = useState(1), [listLoading, setListLoading] = useState(false), [listError, setListError] = useState('')
  const [text, setText] = useState(''), [files, setFiles] = useState<DraftFile[]>([])
  const [sending, setSending] = useState(false), [error, setError] = useState('')
  const [exportJob, setExportJob] = useState<AssistantJob | null>(null)
  const [exporting, setExporting] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [liveReply, setLiveReply] = useState<{ conversation: string; job: string; revision: number; content: string } | null>(null)
  const launcher = useRef<HTMLButtonElement>(null), input = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null), panel = useRef<HTMLElement>(null)
  const composing = useRef(false), mounted = useRef(true), sendingRef = useRef(false)
  const hasOpened = useRef(false)
  const submission = useRef<{ fingerprint: string; key: string; parentRevision: number } | null>(null)
  const creation = useRef<Promise<AssistantConversation> | null>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  useEffect(() => {
    const controller = new AbortController()
    void apiRequest<AssistantConfig>(assistantRoot + 'config/', { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setConfig(value) })
      .catch(() => { /* Existing company list stays usable when the assistant is disabled/unavailable. */ })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!config?.enabled || !conversationId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const read = async () => {
      try {
        const value = await apiRequest<AssistantConversation>(`${assistantRoot}conversations/${encodeURIComponent(conversationId)}/`, { signal: controller.signal })
        if (controller.signal.aborted) return
        if (!value || value.id !== conversationId || !Number.isInteger(value.condition_revision)) throw new Error('会话响应不完整，请重试。')
        setConversation(previous => !previous || previous.id !== value.id || previous.condition_revision <= value.condition_revision ? value : previous)
        setError('')
        if ((value.jobs || []).some(job => jobActive(job.status))) timer = setTimeout(() => { void read() }, 1500)
      } catch (reason) {
        if (controller.signal.aborted) return
        setError(messageFor(reason))
        if (isApiError(reason) && [401, 403, 404].includes(reason.status)) {
          try { window.localStorage.removeItem(storageKey) } catch { /* No local persistence required for permissions. */ }
          setConversation(null); setConversationId(''); setResult(null); setListSnapshot(null); setListResult(null)
          return
        }
        timer = setTimeout(() => { void read() }, 5000)
      }
    }
    void read()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [config?.enabled, conversationId, refresh, storageKey])

  const streamJobId = conversation?.jobs?.find(job => job.kind === 'query' && jobActive(job.status))?.id
  const streamRevision = conversation?.condition_revision
  useEffect(() => {
    if (!config?.enabled || config.capabilities?.answer_stream !== true || !conversationId || !streamJobId || streamRevision === undefined) return
    const controller = new AbortController()
    const receive = async () => {
      try {
        // Bounded observer windows. Reconnecting never submits a message or
        // executes/retries a job. Existing polling remains the recovery path.
        for (let window = 0; window < 6 && !controller.signal.aborted; window++) {
          let content = ''
          const done = await apiEventStream<{ job: AssistantJob; reconnect?: boolean; superseded?: boolean }>(
            `${assistantRoot}jobs/${encodeURIComponent(streamJobId)}/stream/`, {}, controller.signal, delta => {
              if (controller.signal.aborted || !delta) return
              content += delta
              if (content.length > 16000) throw new Error('回答流超出本轮范围。')
              setLiveReply({ conversation: conversationId, job: streamJobId, revision: streamRevision, content })
            })
          if (controller.signal.aborted) return
          if (done.superseded) setLiveReply(null)
          if (!done.reconnect) { setRefresh(value => value + 1); return }
        }
      } catch {
        if (!controller.signal.aborted) {
          setLiveReply(null)
          setRefresh(value => value + 1)
        }
      }
    }
    void receive()
    return () => controller.abort()
  }, [config?.enabled, config?.capabilities?.answer_stream, conversationId, streamJobId, streamRevision])

  const snapshot = conversation ? latestCurrentSnapshot(conversation) : undefined
  useEffect(() => {
    if (!open || !result || result.id !== snapshot?.id
        || (result.condition_revision !== undefined && result.condition_revision !== conversation?.condition_revision)) return
    const content = panel.current?.querySelector<HTMLElement>('.bca-content')
    const first = content?.querySelector<HTMLElement>('.bca-results')
    if (content && first) content.scrollTop = Math.max(0,
      content.scrollTop + first.getBoundingClientRect().top - content.getBoundingClientRect().top - 8)
  }, [open, result?.id, snapshot?.id, conversation?.condition_revision, result])
  useEffect(() => { setResultPage(1) }, [snapshot?.id])
  useEffect(() => {
    if (!snapshot?.id) { setResult(null); return }
    const controller = new AbortController()
    setResultLoading(true)
    void apiRequest<AssistantResult>(`${assistantRoot}results/${encodeURIComponent(snapshot.id)}/?page=${resultPage}&page_size=50`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) { setResult(value); setResultLoading(false) } })
      .catch(reason => { if (!controller.signal.aborted) { setError(messageFor(reason)); setResultLoading(false) } })
    return () => controller.abort()
  }, [snapshot?.id, snapshot?.result_revision, resultPage])

  // The pinned list has its own immutable snapshot ID. New conversation results
  // never replace it, and the existing manual list/filter state stays mounted.
  useEffect(() => {
    if (!listSnapshot) { setListResult(null); return }
    const controller = new AbortController()
    setListLoading(true); setListError('')
    void apiRequest<AssistantResult>(`${assistantRoot}results/${encodeURIComponent(listSnapshot.id)}/?page=${listPage}&page_size=50`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) {
        if (value.id !== listSnapshot.id) throw new Error('快照响应不一致，请重试。')
        setListResult(value); setListLoading(false)
      } })
      .catch(reason => { if (!controller.signal.aborted) { setListError(messageFor(reason)); setListLoading(false) } })
    return () => controller.abort()
  }, [listSnapshot, listPage, refresh])

  useEffect(() => {
    if (!exportJob || !jobActive(exportJob.status)) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      void apiRequest<AssistantJob>(`${assistantRoot}jobs/${encodeURIComponent(exportJob.id)}/`, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted) setExportJob(value) })
        .catch(reason => { if (!controller.signal.aborted) { setError(messageFor(reason)); setExportJob(null) } })
    }, 1500)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [exportJob])
  useEffect(() => {
    if (!open) { if (hasOpened.current) launcher.current?.focus(); return }
    hasOpened.current = true
    input.current?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.isComposing) { event.preventDefault(); setOpen(false); launcher.current?.focus() }
    }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [open])

  const ensureConversation = () => {
    if (conversation) return Promise.resolve(conversation)
    if (!creation.current) creation.current = apiRequest<AssistantConversation>(assistantRoot + 'conversations/', { method: 'POST', body: '{}' })
      .then(value => {
        if (!value?.id || !Number.isInteger(value.condition_revision)) throw new Error('会话创建响应不完整。')
        if (mounted.current) {
          setConversation(value); setConversationId(value.id)
          try { window.localStorage.setItem(storageKey, value.id) } catch { /* Server work continues without browser persistence. */ }
        }
        return value
      }).finally(() => { creation.current = null })
    return creation.current
  }
  const send = async () => {
    if (sendingRef.current || (!text.trim() && !files.length)) return
    if (files.length && !capabilityAvailable(config?.capabilities?.parser)) { setError('当前文件解析不可用，请输入文字需求；尚未提交文件。'); return }
    sendingRef.current = true; setSending(true); setError('')
    try {
      const current = await ensureConversation()
      const attachmentIds = []
      for (const draft of files) {
        if (draft.id) { attachmentIds.push(draft.id); continue }
        const form = new FormData(); form.append('file', draft.file)
        const uploaded = await apiRequest<{ id: string }>(`${assistantRoot}conversations/${encodeURIComponent(current.id)}/attachments/`, { method: 'POST', body: form })
        if (!uploaded?.id) throw new Error('附件响应不完整，请重试。')
        attachmentIds.push(uploaded.id)
        if (mounted.current) setFiles(previous => previous.map(item => item.file === draft.file ? { ...item, id: uploaded.id } : item))
      }
      const fingerprint = JSON.stringify([current.id, text.trim(), attachmentIds])
      if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID(), parentRevision: current.condition_revision }
      await apiRequest(`${assistantRoot}conversations/${encodeURIComponent(current.id)}/messages/`, { method: 'POST', body: JSON.stringify({
        text: text.trim(), attachment_ids: attachmentIds, parent_revision: submission.current.parentRevision,
        client_request_id: submission.current.key }) })
      if (mounted.current) { setText(''); setFiles([]); submission.current = null; setRefresh(value => value + 1) }
    } catch (reason) { if (mounted.current) {
      if (isApiError(reason) && reason.code === 'revision_conflict') submission.current = null
      setError(messageFor(reason)); setRefresh(value => value + 1)
    } }
    finally { sendingRef.current = false; if (mounted.current) { setSending(false); input.current?.focus() } }
  }
  const changeJob = async (job: AssistantJob, action: 'cancel' | 'retry') => {
    try {
      await apiRequest(`${assistantRoot}jobs/${encodeURIComponent(job.id)}/${action}/`, { method: 'POST', body: JSON.stringify({ client_request_id: crypto.randomUUID() }) })
      if (mounted.current) setRefresh(value => value + 1)
    } catch (reason) { if (mounted.current) setError(messageFor(reason)) }
  }
  const exportResult = async () => {
    if (!result || exporting) return
    setExporting(true); setError('')
    try {
      const value = await apiRequest<{ job: AssistantJob }>(`${assistantRoot}results/${encodeURIComponent(result.id)}/exports/`, { method: 'POST', body: JSON.stringify({ scope: 'confirmed', client_request_id: crypto.randomUUID() }) })
      if (mounted.current) { setExportJob(value.job); setRefresh(previous => previous + 1) }
    } catch (reason) { if (mounted.current) setError(messageFor(reason)) }
    finally { if (mounted.current) setExporting(false) }
  }
  const download = async (job: AssistantJob | null = exportJob) => {
    const ref = job?.result_ref
    const exportId = typeof ref === 'string' ? ref : ref && typeof ref === 'object' && 'export_id' in ref ? String(ref.export_id) : ''
    if (!exportId) { setError('导出文件尚未准备完成，请稍后重试。'); return }
    try { await downloadBusinessFile(`${assistantRoot}exports/${encodeURIComponent(exportId)}/download/`, '百川匹配结果.xlsx') }
    catch (reason) { if (mounted.current) setError(messageFor(reason)) }
  }
  if (!config?.enabled) return null
  const active = (conversation?.jobs || []).some(job => jobActive(job.status))
  const showResult = result && result.id === snapshot?.id && (result.condition_revision === undefined || result.condition_revision === conversation?.condition_revision)
  const messages = (conversation?.messages || []).map(message => message.role === 'user' ? message
    : { ...message, content: enterpriseReply(message.content) }).filter(message => message.role === 'user' || message.content)
  if (liveReply && liveReply.conversation === conversationId && liveReply.job === streamJobId && liveReply.revision === conversation?.condition_revision
      && !messages.some(message => message.role === 'assistant' && message.metadata?.job_id === liveReply.job)) {
    const content = enterpriseReply(liveReply.content)
    if (content) messages.push({ id: `stream:${liveReply.job}`, role: 'assistant', content, condition_revision: liveReply.revision })
  }
  return <div className="bca">
    {listSnapshot && <section className="bca-snapshot-list" role="region" aria-label="固定快照企业列表" aria-busy={listLoading}>
      <header><div><h2>助手结果 · 固定快照</h2><p>企业信息</p></div><button type="button" aria-label="关闭企业结果列表" onClick={() => { setListSnapshot(null); setListResult(null); launcher.current?.focus() }}><X size={18}/>关闭</button></header>

      {listError && <p className="bca-error" role="alert">{listError}<button type="button" onClick={() => setRefresh(value => value + 1)}>重新读取</button></p>}
      {listLoading && <p role="status">读取固定快照…</p>}
      {listResult?.id === listSnapshot.id && <>{!listResult.results?.length && <p>此快照没有企业结果。尚未连接现有企业资料时，不代表市场上没有符合企业。</p>}
        {(listResult.results || []).map((item, index) => <article className="bca-result" key={`${item.company_id}-${index}`}><button type="button" className="bca-company" onClick={() => { setListSnapshot(null); setListResult(null); onCompany(item.company_id) }}>{item.company?.name || '查看企业资料'}</button>{!['confirmed', 'satisfied'].includes(item.status || item.verdict || '') && <span className="bca-verdict">{item.status === 'candidate' ? '候选' : verdictLabel(item.status || item.verdict)}</span>}{item.company?.phone && <p>联系电话：{item.company.phone}</p>}<CompanyInfo item={item} conditions={listResult.conditions}/></article>)}
        {typeof listResult.total === 'number' && <div className="bca-result-pages"><span>共 {listResult.total} 家 · 第 {listResult.page || listPage} 页</span><button type="button" disabled={listLoading || listPage <= 1} onClick={() => setListPage(value => Math.max(1, value - 1))}>上一页快照</button><button type="button" disabled={listLoading || listPage * (listResult.page_size || 50) >= listResult.total} onClick={() => setListPage(value => value + 1)}>下一页快照</button></div>}</>}
    </section>}
    <button className="bca-launcher" ref={launcher} type="button" aria-label="打开百川 AI 助手" aria-expanded={open} aria-controls="baichuan-assistant-panel" hidden={open}
      onClick={() => setOpen(true)}><img src={mascot} alt=""/><span>百川 AI 助手{active && <i aria-label="后台任务执行中"/>}</span></button>
    {open && <aside id="baichuan-assistant-panel" className="bca-panel" role="region" aria-label="百川 AI 助手" ref={panel}>
      <header className="bca-header"><div><strong>百川 AI 助手</strong><small>输入需求或上传文件，查询企业</small></div><button type="button" className="bca-icon" aria-label="收起助手，后台任务继续" onClick={() => { setOpen(false); launcher.current?.focus() }}><X size={21}/></button></header>
      <div className="bca-content">

        {(!capabilityAvailable(config.capabilities?.model) || !capabilityAvailable(config.capabilities?.parser)) && <p className="bca-capabilities" role="note">{[
          !capabilityAvailable(config.capabilities?.model) && '模型理解暂不可用',
          !capabilityAvailable(config.capabilities?.parser) && '文件解析暂不可用'].filter(Boolean).join('；')}。</p>}
        {!conversation?.messages?.length && <div className="bca-welcome"><img src={mascot} alt=""/><h2>想找什么样的企业？</h2><p>例如：广东电子与智能化二级，且 ITSS 二级。也可直接上传招标文件。</p></div>}
        <div className="bca-messages" aria-live="polite" aria-relevant="additions text">{messages.map(message => <article key={message.id} className={`bca-message ${message.role === 'user' ? 'bca-user' : ''}`}><small>{message.role === 'user' ? '你' : '百川助手'}</small><p>{message.content || (Array.isArray(message.metadata?.attachment_ids) && message.metadata.attachment_ids.length ? '已上传附件' : '')}</p>{Array.isArray(message.metadata?.attachment_ids) && <ul className="bca-message-files">{message.metadata.attachment_ids.filter((id): id is string => typeof id === 'string').map(id => { const file = conversation?.attachments?.find(item => item.id === id); return <li key={id}><Paperclip size={12}/>{file?.original_name || '会话附件'}{file?.parse_status === 'completed' && <small>已提取文本</small>}</li> })}</ul>}</article>)}</div>
        <div className="bca-jobs" aria-live="polite">{(conversation?.jobs || []).filter(job => jobActive(job.status) || ['failed', 'blocked'].includes(job.status.toLowerCase()) || job.kind === 'export').map(job => <section className="bca-job" key={job.id}><div><strong>{jobLabel(job.status)}</strong></div>{job.error_code && <p className="bca-error">任务未完成：{job.error_code}</p>}{jobActive(job.status) && <button type="button" onClick={() => { void changeJob(job, 'cancel') }}><Square size={13}/>取消任务</button>}{job.kind === 'export' && ['completed', 'succeeded', 'done'].includes(job.status.toLowerCase()) && <button type="button" onClick={() => { void download(job) }}><Download size={14}/>下载 Excel</button>}{['failed', 'blocked'].includes(job.status.toLowerCase()) && <button type="button" onClick={() => { void changeJob(job, 'retry') }}><RotateCcw size={13}/>重试</button>}</section>)}</div>
        {showResult && <section className="bca-results" aria-label="匹配结果" aria-busy={resultLoading}><div className="bca-results-header"><h3>匹配结果</h3><button type="button" onClick={() => { setListSnapshot({ id: result.id, revision: result.condition_revision ?? conversation?.condition_revision ?? 0 }); setListPage(1); setOpen(false) }}>在列表查看</button><button type="button" disabled={exporting || !capabilityAvailable(config.capabilities?.export)} onClick={() => { void exportResult() }}><Download size={14}/>{exporting ? '准备导出…' : capabilityAvailable(config.capabilities?.export) ? '导出确认匹配' : 'Excel 暂不可用'}</button></div>{!(result.results || []).length && <p>当前没有确认结果。可继续说明需求；条件不会自动放宽。</p>}{(result.results || []).map((item, index) => <article className="bca-result" key={`${item.company_id}-${index}`}><button className="bca-company" type="button" onClick={() => onCompany(item.company_id)}>{item.company?.name || '查看企业资料'}</button>{!['confirmed', 'satisfied'].includes(item.status || item.verdict || '') && <span className="bca-verdict">{item.status === 'candidate' ? '候选' : verdictLabel(item.status || item.verdict)}</span>}{item.company?.phone && <p>联系电话：{item.company.phone}</p>}<CompanyInfo item={item} conditions={result.conditions}/></article>)}{typeof result.total === 'number' && <div className="bca-result-pages"><span>共 {result.total} 家 · 第 {result.page || resultPage} 页</span><button type="button" disabled={resultLoading || (result.page || resultPage) <= 1} onClick={() => setResultPage(value => Math.max(1, value - 1))}>上一页结果</button><button type="button" disabled={resultLoading || (result.page || resultPage) * (result.page_size || 50) >= result.total} onClick={() => setResultPage(value => value + 1)}>下一页结果</button></div>}</section>}
        {exportJob && <section className="bca-job"><p>Excel：{jobLabel(exportJob.status)}</p>{['completed', 'succeeded', 'done'].includes(exportJob.status.toLowerCase()) && <button type="button" onClick={() => { void download() }}><Download size={14}/>下载 Excel</button>}</section>}
      </div>
      <form className="bca-composer" onSubmit={event => { event.preventDefault(); if (!composing.current) void send() }}>
        {error && <p className="bca-error" role="alert">{error}<button type="button" aria-label="重新同步会话" onClick={() => setRefresh(value => value + 1)}><RotateCcw size={13}/></button></p>}
        {!!files.length && <ul className="bca-files">{files.map((draft, index) => <li key={`${draft.file.name}-${index}`}><span>{draft.file.name}</span><button type="button" disabled={sending} aria-label={`移除 ${draft.file.name}`} onClick={() => setFiles(previous => previous.filter((_, item) => item !== index))}><X size={13}/></button></li>)}</ul>}
        <textarea ref={input} aria-label="需求或补充说明" placeholder="输入需求，或附上招标文件…" rows={3} value={text} disabled={sending} onChange={event => setText(event.target.value)}
          onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }}
          onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !composing.current && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) { event.preventDefault(); void send() } }}/>
        <div className="bca-composer-actions"><input ref={fileInput} type="file" accept=".pdf,.docx" multiple hidden disabled={sending} onChange={event => {
          const chosen = [...(event.target.files || [])]; const issue = chosen.map(validateAttachment).find(Boolean)
          const limit = config.limits?.files || 3
          if (issue) setError(issue); else if (files.length + chosen.length > limit) setError(`一次最多选择 ${limit} 份文件。`); else { setFiles(previous => [...previous, ...chosen.map(file => ({ file }))]); setError('') }
          event.target.value = ''
        }}/><button type="button" disabled={sending || !capabilityAvailable(config.capabilities?.parser)} onClick={() => fileInput.current?.click()} title="PDF / DOCX，每份最多 20 MB"><Paperclip size={17}/>附件</button><small>收起后继续执行</small><button className="bca-send" type="submit" disabled={sending || (!text.trim() && !files.length)}><Send size={16}/>{sending ? '提交中…' : '发送'}</button></div>
      </form>
    </aside>}
  </div>
}

export default function BaichuanAssistant({ allowed, onCompany }: { allowed: boolean; onCompany: (id: string) => void }) {
  const { user } = useEnterprise()
  if (!allowed || !user?.id || !user.portal_user_id) return null
  return <OwnedAssistant key={`${user.id}:${user.portal_user_id}`} owner={user.id} portalOwner={user.portal_user_id} onCompany={onCompany}/>
}
