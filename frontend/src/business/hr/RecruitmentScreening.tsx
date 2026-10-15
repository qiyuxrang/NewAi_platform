import { useEffect, useRef, useState } from 'react';
import { CenterLink } from './CenterLink';
import { get, mutate, uploadSequential, selectResumeFiles, screeningCounts, retentionNotice, uploadJd, root, statusText, message } from './recruitment-api';
import type { Batch, Jd, Result } from './recruitment-api';
import { downloadBusinessFile } from '../api';
import { installLedgerNavigationGuard } from '../ledgers/ledger-navigation';

export default function RecruitmentScreening({ results = false }: { results?: boolean }) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selected, setSelected] = useState(new URLSearchParams(window.location.search).get('batch') || ''), [jd, setJd] = useState(''), [jdFilename, setJdFilename] = useState(''), [files, setFiles] = useState<File[]>([]);
  const [batch, setBatch] = useState<Batch | null>(null), [rows, setRows] = useState<Result[]>([]);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [sort, setSort] = useState('score'), [verdict, setVerdict] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [draftJd, setDraftJd] = useState<Jd | null>(null), [confirmedJds, setConfirmedJds] = useState<Jd[]>([]);
  const [compared, setCompared] = useState<string[]>([]);
  useEffect(() => { const c = new AbortController(); void get<Jd[]>('confirmed-jds/', c.signal).then(setConfirmedJds).catch(e => { if (!c.signal.aborted) setError(message(e)); }); return () => c.abort(); }, []);
  useEffect(() => { setCompared([]); setDraftJd(null); }, [selected]);
  const [progressRefresh, setProgressRefresh] = useState(0);
  const lock = useRef(false), createKey = useRef(crypto.randomUUID());
  const hasLocalWork = !results && (files.length > 0 || !!draftJd);
  useEffect(() => {
    if (!hasLocalWork) return;
    return installLedgerNavigationGuard(window, () => !lock.current && window.confirm('有尚未提交的简历或尚未确认的 JD，确定离开当前页面？'));
  }, [hasLocalWork]);
  const selectedRef = useRef(selected); selectedRef.current = selected;
  const requestedBatch = new URLSearchParams(window.location.search).get('batch') || '';
  useEffect(() => { setSelected(requestedBatch); setJd(''); setJdFilename(''); setFiles([]); setNotice(''); }, [requestedBatch]);
  async function reload() { setBatches(await get<Batch[]>('batches/')); }
  async function work(action: () => Promise<void>, refreshProgress = true) {
    if (lock.current) return; lock.current = true; setBusy(true); setError('');
    try { await action(); } catch (e) { setError(message(e)); } finally { lock.current = false; setBusy(false); if (refreshProgress) setProgressRefresh(current => current + 1); }
  }
  useEffect(() => { if (!results) return; const c = new AbortController();
    get<Batch[]>('batches/', c.signal)
      .then(bs => { if (!c.signal.aborted) setBatches(bs); })
      .catch(e => { if (!c.signal.aborted) setError(message(e)); });
    return () => c.abort();
  }, [results]);
  useEffect(() => {
    if (lock.current) return;
    setBatch(null); setRows([]); setDetail(null); if (!selected) return;
    const c = new AbortController(); let timer: ReturnType<typeof setTimeout>; let stopped = false;
    const load = async () => {
      try {
        const next = await get<Batch>(`batches/${selected}/progress/`, c.signal);
        const list = results ? await get<Result[]>(`batches/${selected}/summary/?sort_by=${sort}&verdict=${verdict}`, c.signal) : [];
        if (stopped) return; setBatch(next); setRows(list);
        if (['queued', 'running'].includes(next.status)) timer = setTimeout(load, 3000);
      } catch (e) { if (!stopped) { setBatch(null); setRows([]); setError(message(e)); } }
    };
    void load(); return () => { stopped = true; c.abort(); clearTimeout(timer); };
  }, [selected, results, sort, verdict, progressRefresh]);
  function addFiles(incoming: File[]) {
    const next = selectResumeFiles(files, incoming); setFiles(next.files);
    setNotice(`已选 ${next.files.length} 份；跳过重复 ${next.duplicates} 份${next.rejected.length ? `；不支持、空文件或超过2MiB：${next.rejected.join('、')}` : ''}`);
  }
  async function runScreening() {
    let current = batch;
    if (!current) {
      current = await mutate<Batch>('batches/', { jd_version_id: jd }, 'POST', { 'Idempotency-Key': createKey.current });
      setBatch(current); setSelected(current.id); createKey.current = crypto.randomUUID();
    }
    if (files.length) {
      const queued = [...files];
      current = await uploadSequential(current, queued, (next, sent) => {
        setBatch(next); setFiles(queued.slice(sent)); setNotice(`已上传 ${sent}/${queued.length} 份，服务端按内容去重。`);
      });
    }
    setBatch(current);
    if (!current.total) throw new Error('请先选择至少一份有效简历。');
    await mutate(`batches/${current.id}/run/`, { expected_version: current.version });
    setNotice('筛选已提交，后台正在处理。');
  }
  function startNewScreening() {
    setSelected(''); setBatch(null); setJd(''); setJdFilename(''); setFiles([]); setRows([]); setDetail(null); setError(''); setNotice('');
    createKey.current = crypto.randomUUID();
  }
  const counts = batch ? screeningCounts(batch) : null;
  const params = `sort_by=${sort}&verdict=${verdict}`;
  return <><header className="hr-title"><div><h1>{results ? '筛选结果' : '简历筛选'}</h1><p>{results ? '查看往期批次、逐条证据和版本记录。' : '上传 JD 和简历，由后台逐份处理。'}</p></div></header>
    {error && <p role="alert" className="hr-error">{error}</p>}
    <p className="hr-muted">{retentionNotice}</p>
    {!results && <section className="hr-card" aria-busy={busy}><div className="hr-screening-layout">
      <div><h2>岗位说明</h2><label className="hr-upload">上传 JD 文件（TXT、DOCX、PDF）<input type="file" accept=".txt,.docx,.pdf" disabled={busy || !!selected} onChange={e => {
        const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
        if (selectResumeFiles([], [file]).rejected.length) { setError('JD 须为非空 TXT、DOCX、PDF，且不超过2MiB。'); return; }
        setJd(''); setJdFilename(''); void work(async () => {
          const imported = await uploadJd(file);
          setDraftJd(imported.jd); setJdFilename(file.name); createKey.current = crypto.randomUUID(); setNotice('请先核对 JD 正文及筛选标准，再确认使用。');
        });
      }} /></label>
      {jdFilename && <p>已上传 JD：<strong>{jdFilename}</strong></p>}
      <p className="hr-muted">确认岗位标准后才能开始筛选；年龄只作备注，不参与筛选。</p>
      <label>使用已确认 JD<select value={jd} disabled={busy || !!selected} onChange={e => { setJd(e.target.value); setDraftJd(null); setJdFilename(''); createKey.current = crypto.randomUUID(); }}><option value="">请选择正式 JD</option>{confirmedJds.filter(j => !j.stale).map(j => <option key={j.id} value={j.id}>v{j.version} · {j.body.slice(0, 50)}</option>)}</select></label>
      {(draftJd || confirmedJds.find(j => j.id === jd)) && <details open><summary>岗位正文与筛选标准</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{(draftJd || confirmedJds.find(j => j.id === jd))?.body}</pre><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify((draftJd || confirmedJds.find(j => j.id === jd))?.requirements, null, 2)}</pre></details>}
      {draftJd && <button disabled={busy || !!selected} onClick={() => void work(async () => { const confirmed = await mutate<Jd>(`requests/${draftJd.request_id}/jd-versions/${draftJd.id}/confirm/`, { expected_version: draftJd.input_version }); setJd(confirmed.id); setConfirmedJds(previous => [confirmed, ...previous.filter(j => j.id !== confirmed.id)]); setDraftJd(null); setNotice('已确认该版本 JD，可以开始筛选。'); })}>确认该版本 JD 及筛选标准</button>}</div>
      <div><h2>简历</h2><label className="hr-upload">批量上传简历（TXT、DOCX、PDF）<input type="file" multiple accept=".txt,.docx,.pdf" disabled={busy || (!!selected && (!batch || batch.status !== 'pending' || batch.stale))} onChange={e => { addFiles(Array.from(e.target.files || [])); e.target.value = ''; }} /></label>
      <p className="hr-muted">支持 TXT、DOCX、PDF；单份最大2MiB；最多200份。</p>
      <ul className="hr-file-list">{files.map((file, i) => <li key={`${file.webkitRelativePath || file.name}-${i}`}>{file.webkitRelativePath || file.name}</li>)}</ul>
      <button disabled={busy || !files.length} onClick={() => { setFiles([]); setNotice(''); }}>清空待上传文件</button></div>
    </div><div className="hr-screening-run"><button className="hr-primary" disabled={busy || (!!selected && !batch) || (!batch && (!jd || !files.length)) || (!!batch && (batch.status !== 'pending' || batch.stale || (!batch.total && !files.length)))} onClick={() => void work(runScreening)}>{busy ? '正在提交…' : '进行筛选'}</button></div>
    {notice && <p role="status">{notice}</p>}</section>}
    {(results || batch) && <section className="hr-card"><div className="hr-card-head"><h2>{results ? '历史筛选记录' : '处理进度'}</h2>{results ? <button disabled={busy} onClick={() => void work(reload)}>刷新</button> : <button disabled={busy} onClick={() => setProgressRefresh(current => current + 1)}>刷新进度</button>}</div>
      {results && <><label>选择批次<select value={selected} disabled={busy} onChange={e => { setSelected(e.target.value); setBatch(null); setFiles([]); setError(''); setNotice(''); }}><option value="">请选择筛选批次</option>{batches.map(item => <option key={item.id} value={item.id}>{item.position_name} · JD v{item.jd_version} · {new Date(item.updated_at).toLocaleString()} · {statusText(item.status)}</option>)}</select></label>
      {!batches.length && <p className="hr-muted">暂无筛选记录。</p>}</>}
      {batch && <><div className="hr-metrics"><span>总数 <b>{batch.total}</b></span><span>已筛选 <b>{counts?.screened}</b></span><span>待筛选 <b>{counts?.pending ?? '未记录'}</b></span><span>预筛选 <b>{counts?.prescreened ?? '未记录'}</b></span><span>失败 <b>{batch.failed}</b></span><span>{statusText(batch.status)}</span>{batch.model_selection && <span>模型 <b>{batch.model_selection.model_name || batch.model_selection.model_id}</b></span>}</div>
        <progress value={batch.progress} max={100} aria-label="批次处理进度" /><span> {batch.progress}%</span>
        {batch.stale && <p className="hr-warning">关联岗位需求已变化：本批次为历史结果，不代表当前要求。</p>}
        <p className="hr-muted">已筛选：模型处理完成；待筛选：已排队或处理中；预筛选：文件接收校验通过、尚未启动模型。失败单独统计，重试排队后计入待筛选。获准结果长期归档。</p>
        {!results && <><div className="hr-actions"><button disabled={busy || !batch.failed || batch.stale || ['queued', 'running'].includes(batch.status)} onClick={() => void work(async () => { await mutate(`batches/${batch.id}/retry/`, { expected_version: batch.version }); })}>重试失败项</button><button disabled={busy || ['pending', 'queued', 'running'].includes(batch.status)} onClick={startNewScreening}>开始新的筛选</button><CenterLink className="hr-outline" href={`/centers/hr/results?batch=${batch.id}`}>查看筛选结果</CenterLink></div>
          <div className="hr-table-wrap"><table><thead><tr><th>简历</th><th>大小</th><th>状态</th><th>异常</th></tr></thead><tbody>{batch.artifacts?.map(item => <tr key={item.id}><td>{item.filename}</td><td>{Math.ceil(item.size / 1024)} KB</td><td>{statusText(item.processing_status)}</td><td>{item.error_code || '—'}</td></tr>)}</tbody></table></div></>}
        {results && <><div className="hr-actions"><label>排序<select value={sort} onChange={e => setSort(e.target.value)}><option value="score">辅助分</option><option value="hard_gap_count">硬条件缺口</option><option value="unknown_count">UNKNOWN 数量</option></select></label>
        <label>匹配状态<select value={verdict} onChange={e => setVerdict(e.target.value)}><option value="">全部</option>{['MATCH', 'PARTIAL', 'UNKNOWN', 'NOT_MATCH'].map(v => <option key={v}>{v}</option>)}</select></label>
        <button className="hr-outline" disabled={busy} onClick={() => void work(() => downloadBusinessFile(root + `batches/${batch.id}/export/?${params}`, '筛选结果.csv'), false)}>导出 CSV</button></div>
        <div className="hr-table-wrap"><table><thead><tr><th>简历</th><th>处理状态</th><th>辅助分</th><th>硬缺口</th><th>UNKNOWN</th><th>操作</th></tr></thead><tbody>{rows.map(item => <tr key={item.id}><td>{item.filename}</td><td>{statusText(item.processing_status)}</td><td>{item.score ?? '—'}</td><td>{item.hard_gap_count}</td><td>{item.unknown_count ?? '—'}</td><td><button onClick={() => void work(async () => { setDetail(null); const result = await get<Record<string, unknown>>(`resumes/${item.id}/`); if (selectedRef.current === selected) setDetail(result); }, false)}>查看证据</button> <button disabled={busy} onClick={() => void work(() => downloadBusinessFile(root + `resumes/${item.id}/download/`, item.filename), false)}>下载原件</button></td></tr>)}</tbody></table></div>
        <p className="hr-muted">辅助匹配不是录用或淘汰决定；缺少证据显示 UNKNOWN。</p>
        <fieldset className="hr-compare-picker"><legend>同批候选人对比（最多3份）</legend>{rows.filter(r => r.processing_status === 'completed').map(row => <label key={row.id}><input type="checkbox" checked={compared.includes(row.id)} disabled={!compared.includes(row.id) && compared.length >= 3} onChange={e => setCompared(previous => e.target.checked ? [...previous, row.id] : previous.filter(id => id !== row.id))} />{row.filename}</label>)}</fieldset>
        {!!compared.length && <div className="hr-table-wrap"><table aria-label="候选人对比"><thead><tr><th>候选人</th><th>辅助分 / 硬缺口 / UNKNOWN</th><th>逐条判断与证据</th><th>待核实问题</th></tr></thead><tbody>{rows.filter(r => compared.includes(r.id)).map(row => <tr key={row.id}><td>{row.filename}</td><td>{row.score ?? '—'} / {row.hard_gap_count} / {row.unknown_count ?? '—'}</td><td style={{ whiteSpace: 'normal' }}>{row.matrix.map(m => <p key={m.id}>{m.text}：{m.verdict} · {m.evidence.map(e => `${e.quote} (${e.locator})`).join('；') || '无有效证据'}</p>)}</td><td style={{ whiteSpace: 'normal' }}>{row.verification_questions?.map(q => <p key={q.requirement_id}>{q.question}</p>)}</td></tr>)}</tbody></table></div>}</>}
      </>}
    </section>}
    {detail && <section className="hr-card"><h2>证据矩阵与解析记录</h2>
      <div className="hr-table-wrap"><table><thead><tr><th>岗位要求</th><th>判断</th><th>引用证据</th><th>来源位置</th></tr></thead><tbody>
        {((detail.match as { matrix?: Result['matrix'] })?.matrix || []).map(item => <tr key={item.id}><td>{item.text}</td><td>{item.verdict}</td><td style={{ whiteSpace: 'normal' }}>{item.evidence.map(e => e.quote).join('；') || '无有效证据'}</td><td>{item.evidence.map(e => e.locator).join('；')}</td></tr>)}
      </tbody></table></div><h3>待核实问题</h3>{((detail.match as { verification_questions?: { requirement_id: string; question: string }[] })?.verification_questions || []).map(q => <p key={q.requirement_id}>{q.question}</p>)}<details><summary>查看结构化解析和来源记录</summary><pre>{JSON.stringify(detail, null, 2)}</pre></details><button onClick={() => setDetail(null)}>关闭详情</button></section>}
  </>;
}
