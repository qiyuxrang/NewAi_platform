import { useEffect, useRef, useState } from 'react'
import { fetchJSON } from '../lib/api'

interface ChildSession {
  key: string
  spawnedBy: string
  label: string | null
  status: string | null
  startedAt: number | null
  endedAt: number | null
  model: string | null
  modelProvider: string | null
  lastMessagePreview: string | null
}

interface ChildSessionResult {
  parent: string
  children: ChildSession[]
}

interface SubagentPanelProps {
  sessionKey: string | null
  onOpenSession: (key: string) => void
  /** Increment when the parent receives SSE updates. */
  refreshToken?: number
}

const statuses: Record<string, string> = {
  running: '运行中', done: '已完成', failed: '失败', timeout: '超时', killed: '已终止',
}
const completed = new Set(['done', 'failed', 'timeout', 'killed'])

function timestamp(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '未返回'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '未返回' : date.toLocaleString('zh-CN', { hour12: false })
}

export default function SubagentPanel({ sessionKey, onOpenSession, refreshToken = 0 }: SubagentPanelProps) {
  const [result, setResult] = useState<ChildSessionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<{ parent: string; text: string } | null>(null)
  const [messages, setMessages] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const activeParent = useRef(sessionKey)
  activeParent.current = sessionKey

  useEffect(() => {
    setMessages({})
    setNotice(null)
    setBusy(null)
  }, [sessionKey])

  useEffect(() => {
    if (!sessionKey) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetchJSON<ChildSessionResult>(`/api/openclaw/subagents?parent=${encodeURIComponent(sessionKey)}`, {
      signal: controller.signal,
    }).then(data => {
      if (!controller.signal.aborted) setResult(data)
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '无法读取子任务')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [sessionKey, refreshToken, revision])

  async function control(child: ChildSession, action: 'steer' | 'kill' | 'send') {
    if (!sessionKey || busy) return
    const parent = sessionKey
    const message = messages[child.key]?.trim() ?? ''
    if (action !== 'kill' && !message) return
    setBusy(child.key)
    setNotice(null)
    try {
      const acknowledgement = await fetchJSON<{ submitted: boolean; runId: string | null; verified?: boolean; status?: string }>(
        `/api/openclaw/subagents/${encodeURIComponent(child.key)}/control`,
        { method: 'POST', body: JSON.stringify({ parent, action, ...(action === 'kill' ? {} : { message }) }) },
      )
      if (activeParent.current !== parent) return
      if (!acknowledgement.submitted) throw new Error('网关未确认指令提交')
      setMessages(current => ({ ...current, [child.key]: '' }))
      setNotice({ parent, text: acknowledgement.verified === true && acknowledgement.status === 'killed' ? '子任务已终止。' : '指令已提交，请查看主会话回复与任务状态确认结果。' })
      setRevision(current => current + 1)
    } catch (cause) {
      if (activeParent.current === parent) setNotice({ parent, text: cause instanceof Error ? cause.message : '指令提交失败' })
    } finally {
      if (activeParent.current === parent) setBusy(null)
    }
  }

  if (!sessionKey) return null
  const children = result?.parent === sessionKey ? result.children : []
  return <details className="rounded-xl border border-dark-border bg-dark-card p-4">
    <summary className="cursor-pointer text-sm font-semibold text-dark-text">子任务执行{children.length > 0 ? ` · ${children.length}` : ''}</summary>
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between gap-3 text-xs text-dark-text-secondary">
        <span>由智能助手按当前需求创建子任务。</span>
        <button type="button" onClick={() => setRevision(current => current + 1)} disabled={loading} className="text-accent-blue disabled:opacity-50">{loading ? '读取中…' : '刷新'}</button>
      </div>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {!loading && !error && result?.parent === sessionKey && children.length === 0 && <p className="text-sm text-dark-text-secondary">当前会话尚无子任务。</p>}
      {notice?.parent === sessionKey && <p role="status" className="text-sm text-dark-text-secondary">{notice.text}</p>}
      {children.map(child => {
        const running = child.status === 'running'
        const canContinue = child.status !== null && completed.has(child.status)
        const isBusy = busy === child.key
        return <article key={child.key} className="rounded-lg border border-dark-border p-3">
          <div className="flex items-start justify-between gap-3">
            <button type="button" onClick={() => onOpenSession(child.key)} className="break-all text-left text-sm font-medium text-accent-blue hover:underline">{child.label || child.key}</button>
            <span className="shrink-0 text-xs text-dark-text-secondary">{child.status ? statuses[child.status] ?? child.status : '状态未返回'}</span>
          </div>
          <p className="mt-2 break-all text-xs text-dark-text-secondary">模型：{child.model ? [child.modelProvider, child.model].filter(Boolean).join('/') : '未返回'}</p>
          <p className="mt-1 text-xs text-dark-text-secondary">开始：{timestamp(child.startedAt)}{child.endedAt !== null ? ` · 结束：${timestamp(child.endedAt)}` : ''}</p>
          {child.lastMessagePreview && <p className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words text-sm text-dark-text-secondary">{child.lastMessagePreview}</p>}
          {(running || canContinue) && <div className="mt-3 space-y-2">
            <textarea aria-label={`向 ${child.label || child.key} 追加指令`} value={messages[child.key] ?? ''} maxLength={32000} rows={2}
              onChange={event => setMessages(current => ({ ...current, [child.key]: event.target.value }))}
              placeholder={running ? '追加指令，原生 Agent 将调整当前任务' : '输入后续任务，继续此子会话'}
              className="w-full resize-y rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-sm text-dark-text" />
            <div className="flex flex-wrap gap-3 text-xs">
              <button type="button" disabled={busy !== null || !messages[child.key]?.trim()} onClick={() => void control(child, running ? 'steer' : 'send')}
                className="text-accent-blue disabled:opacity-40">{isBusy ? '提交中…' : running ? '追加指令' : '继续任务'}</button>
              {running && <button type="button" disabled={busy !== null} onClick={() => void control(child, 'kill')} className="text-red-400 disabled:opacity-40">终止任务</button>}
              <button type="button" onClick={() => onOpenSession(child.key)} className="text-dark-text-secondary hover:underline">打开子会话</button>
            </div>
          </div>}
        </article>
      })}
    </div>
  </details>
}
