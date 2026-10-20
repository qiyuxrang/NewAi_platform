import { useEffect, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../api'
import { useBusinessResource } from '../useBusinessResource'
import { installLedgerNavigationGuard } from '../ledgers/ledger-navigation'
import './engineering-preparation.css'

function submissionMayHaveSucceeded(reason: unknown): boolean {
  return !(reason instanceof ApiError && reason.status >= 400 && reason.status < 500);
}
function uploadIssue(files: Pick<File, "name" | "size">[]): string {
  if (files.length < 1 || files.length > 2 || files.some((file) => !file.name.toLowerCase().endsWith(".xlsx"))) return "仅支持 1 至 2 个 .xlsx 清单文件。";
  if (files.some((file) => file.size === 0)) return "清单文件不能为空，请重新选择。";
  if (files.some((file) => file.size > 20 * 1024 * 1024)) return "单份工程清单不得超过 20MiB，请调整后重新选择。";
  return "";
}

const root = '/api/engineering/preparations/'
interface Preparation {
  id: string; version: number; state: string; error_code: string; region: string;
  basis: { rules_sha256?: string }; basis_sha256: string;
  files: { name: string; sha256: string }[]; inspection: unknown;
  job: { id: string; status: string } | null;
}
const labels: Record<string, string> = { queued: '等待预检', running: '正在预检', ready: '待确认测算依据', failed: '预检失败', confirmed: '已确认并创建测算任务' }

export default function EngineeringPreparationPanel({ onJob }: { onJob: (id: string) => void }) {
  const list = useBusinessResource<{ preparations: Preparation[] }>(root)
  const [files, setFiles] = useState<File[]>([]), [region, setRegion] = useState('陕西')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const locked = useRef(false), uploadKey = useRef(crypto.randomUUID())
  useEffect(() => {
    if (!files.length) return
    return installLedgerNavigationGuard(window, () => window.confirm('已选择的清单尚未上传，确定离开？'))
  }, [files.length])
  async function work(action: () => Promise<void>) {
    if (locked.current || uncertain) return
    locked.current = true
    setBusy(true); setError('')
    try { await action(); list.reload() } catch (cause) { const unknown = submissionMayHaveSucceeded(cause); setUncertain(unknown); setError(`${cause instanceof Error ? cause.message : '提交失败'}${unknown ? ' 提交结果尚未核实，请刷新准备记录，核对是否已接收或确认，避免重复提交。' : ''}`); list.reload() } finally { setBusy(false); locked.current = false }
  }
  return <section className="center-panel engineering-preparations" aria-label="测算准备与确认"><h3>上传清单，先核对测算依据</h3>
    <p>预检只检查文件。确认具体版本后，后台才执行内部成本测算。</p>
    <form onSubmit={event => { event.preventDefault(); const form = event.currentTarget; void work(async () => {
      const issue = uploadIssue(files); if (issue) throw new ApiError(400, issue)
      const body = new FormData(); files.forEach(f => body.append('files', f)); body.set('region', region)
      await apiRequest(root, { method: 'POST', body, headers: { 'Idempotency-Key': uploadKey.current } }); setFiles([]); uploadKey.current = crypto.randomUUID(); form.reset()
    }) }}><label className="center-field">清单文件<input type="file" multiple accept=".xlsx" disabled={busy || uncertain} onChange={event => { setFiles(Array.from(event.target.files || [])); uploadKey.current = crypto.randomUUID() }} /></label>
      <label className="center-field">测算地区<input value={region} maxLength={80} required disabled={busy || uncertain} onChange={event => { setRegion(event.target.value); uploadKey.current = crypto.randomUUID() }} /></label>
      <button className="button primary" disabled={busy || uncertain || !files.length}>上传并预检</button></form>
    <p>本流程使用本地规则与价格库；网络取价关闭。清单修改后请上传新准备记录；已确认版本保留审计记录。</p>
    {uncertain && <p role="alert">请先核对下方准备记录与测算任务，再决定是否重新提交。<button type="button" disabled={busy} onClick={() => { setUncertain(false); setError('') }}>已核对记录，允许继续</button></p>}
    {error && <p role="alert">{error}</p>}{list.error && <p role="alert">{list.error}</p>}
    <button className="button secondary" disabled={busy} onClick={list.reload}>刷新准备记录</button>
    {list.data?.preparations.map(prep => <article key={prep.id}><h4>{prep.files.map(f => f.name).join('、')} · v{prep.version}</h4><p>{labels[prep.state] || prep.state} · {prep.region}</p>
      {prep.error_code && <p role="alert">{prep.error_code} · 请检查清单，或在运行环境恢复后重试预检。</p>}
      <details open={prep.state === 'ready'}><summary>预检与测算依据</summary><ul>{prep.files.map((f, i) => <li key={i}>{f.name} · SHA256 {f.sha256}</li>)}</ul><p>本地规则版本：{prep.basis.rules_sha256 || '预检后生成'}</p><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(prep.inspection, null, 2)}</pre><p>成果为内部成本草稿，需要人工复核；成本阶段失败时按整份输入重试。</p></details>
      {prep.state === 'ready' && <button className="button primary" disabled={busy || uncertain} onClick={() => void work(async () => { const result = await apiRequest<Preparation>(`${root}${prep.id}/confirm/`, { method: 'POST', body: JSON.stringify({ expected_version: prep.version, basis_sha256: prep.basis_sha256 }) }); if (result.job) onJob(result.job.id) })}>确认 v{prep.version} 清单与依据，开始测算</button>}
      {prep.state === 'failed' && prep.error_code === 'preflight_unavailable' && <button className="button secondary" disabled={busy || uncertain} onClick={() => void work(async () => { await apiRequest(`${root}${prep.id}/retry/`, { method: 'POST', body: JSON.stringify({ expected_version: prep.version }) }) })}>重试预检</button>}
      {prep.job && <button className="button secondary" onClick={() => onJob(prep.job!.id)}>查看测算任务</button>}
    </article>)}
  </section>
}
