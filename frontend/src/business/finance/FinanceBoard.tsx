import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Banknote, CalendarDays, CircleDollarSign, Clock3, FileText, Info, RefreshCw, Search, ShieldCheck, Wallet } from 'lucide-react'
import { collectionComposition, financeError, financeMetrics, financeValue, isSourceFinance, loadFinanceBoard } from './finance-board'
import type { FinanceBoardPayload } from './finance-board'
import './finance-board.css'

const icons = [FileText, Wallet, CircleDollarSign, Clock3, CalendarDays]

function DistributionChart({ data }: { data: FinanceBoardPayload }) {
  const items = data.distribution
  const max = Math.max(...items.map(item => item.count), 0)
  return <section className="finance-chart" aria-label={isSourceFinance(data) ? '主体或类型条目分布' : '结清状态分布'}>
    <h3>{isSourceFinance(data) ? '主体 / 类型条目分布' : '结清状态分布'}</h3>
    <p>当前筛选范围 · 条目数</p>
    {data.available && data.filtered_count > 0 && max > 0 ? <div className="finance-bars">{items.map(item => <div className="finance-bar-row" key={item.label}>
      <span title={item.label}>{item.label}</span><div className="finance-bar-track"><div style={{ width: `${item.count / max * 100}%` }} title={`${item.label}：${item.count} 条`} /></div><strong>{item.count}</strong>
    </div>)}</div> : <div className="finance-chart-empty">暂无数据</div>}
  </section>
}

function CollectionChart({ data }: { data: FinanceBoardPayload }) {
  const values = collectionComposition(data)
  const ratio = values ? values.received / (values.received + values.receivable) : 0
  return <section className="finance-chart" aria-label="已收待收构成">
    <h3>已收 / 待收构成</h3><p>当前筛选范围 · 元</p>
    {values ? <div className="finance-donut-layout">
      <svg viewBox="0 0 120 120" role="img" aria-label={`已收 ${financeValue(values.received)} 元，待收 ${financeValue(values.receivable)} 元`}>
        <title>{`已收 ${financeValue(values.received)} 元，待收 ${financeValue(values.receivable)} 元`}</title>
        <circle cx="60" cy="60" r="42" fill="none" stroke="#dbeafe" strokeWidth="15" />
        <circle cx="60" cy="60" r="42" fill="none" stroke="#2563eb" strokeWidth="15" pathLength="100" strokeDasharray={`${ratio * 100} 100`} transform="rotate(-90 60 60)" />
        <text x="60" y="57" textAnchor="middle" className="finance-donut-label">已收占比</text><text x="60" y="75" textAnchor="middle" className="finance-donut-number">{(ratio * 100).toFixed(1)}%</text>
      </svg>
      <div className="finance-legend">{['received', 'receivable'].map((key, index) => { const metric = data.metrics.find(item => item.key === key); return <div key={key}><span className={`finance-dot finance-dot-${index}`} /><span>{index ? '待收' : '已收'}</span><strong>{financeValue(metric?.value)} 元</strong></div> })}</div>
    </div> : <div className="finance-chart-empty">暂无可绘制金额</div>}
  </section>
}

export function FinanceBoardContent({ data, query }: { data: FinanceBoardPayload; query: string }) {
  const sourceMode = isSourceFinance(data)
  const [selectedId, setSelectedId] = useState('')
  const selected = data.records.find(record => record.project_id === selectedId)
  const columns = sourceMode ? ['project_name', 'client_name', 'contract_amount', 'opening_receivable', 'receivable_balance', 'owner', 'current_status'] : ['project_name', 'contract_amount', 'received_amount', 'due_date']
  return <>
    <div className="finance-source"><ShieldCheck size={16} aria-hidden="true" /><span>已发布台账 · 来源：{data.source?.name || '—'}</span><span>截止日期：{data.source?.as_of || '—'}</span></div>
    {sourceMode && <p className="finance-notice"><Info size={16} aria-hidden="true" />原表金额单位未核实，保留原始数值，暂不绘制金额图。月份所属来源年度未确认，请查阅原始来源。</p>}
    <p className="finance-scope">{data.scope}</p>
    <p className="finance-range">{query ? `筛选：${query} · ` : '全部已发布条目 · '}当前 {data.filtered_count} 条 / 台账共 {data.total} 条；指标、图表及明细均使用当前筛选范围。</p>
    <div className="finance-metrics">{financeMetrics(data).map((metric, index) => { const Icon = icons[index]; return <article className="finance-metric" key={metric.key}><div><span>{metric.label}</span><span className="finance-metric-icon"><Icon size={19} aria-hidden="true" /></span></div><strong>{financeValue(data.available ? metric.value : null)}</strong><small>{sourceMode ? '原表数值 · 单位未核实' : metric.unit || '—'}</small></article> })}</div>
    <div className={`finance-charts${sourceMode ? ' finance-charts-single' : ''}`}>{!sourceMode && <CollectionChart data={data} />}<DistributionChart data={data} /></div>
    <section className="finance-records" aria-label="财务项目明细"><div className="finance-records-heading"><h3>项目明细</h3><span>只读 · {data.filtered_count} 条</span></div>
      {data.available && data.records.length > 0 ? <div className="finance-table-scroll"><table><thead><tr>{columns.map(field => <th key={field}>{data.fields[field] || field}</th>)}<th>查看</th></tr></thead><tbody>{data.records.map(record => <tr key={record.project_id}>{columns.map(field => <td key={field} title={record[field] || ''}>{['contract_amount', 'opening_receivable', 'receivable_balance', 'received_amount'].includes(field) ? financeValue(record[field]) : record[field] || '—'}</td>)}<td><button type="button" className="finance-text-button" onClick={() => setSelectedId(record.project_id)} aria-label={`查看 ${record.project_name} 明细`}>明细</button></td></tr>)}</tbody></table></div> : <p className="finance-empty">{data.available ? '当前筛选范围暂无项目。' : '暂无已发布财务台账。'}</p>}
    </section>
    {selected && <dialog className="finance-detail" aria-label="项目完整明细" ref={dialog => { if (dialog && !dialog.open) dialog.showModal() }} onClose={() => setSelectedId('')}><div className="finance-records-heading"><h3>{selected.project_name}</h3><button type="button" autoFocus className="finance-text-button" onClick={event => event.currentTarget.closest('dialog')?.close()}>关闭明细</button></div><dl>{Object.entries(data.fields).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>{selected[field] || '—'}</dd></div>)}</dl></dialog>}
  </>
}

export default function FinanceBoard() {
  const [params, setParams] = useSearchParams()
  const query = (params.get('q') || '').trim()
  const [attempt, setAttempt] = useState(0)
  const requestKey = JSON.stringify([query, attempt])
  const [result, setResult] = useState<{ key: string; data?: FinanceBoardPayload; error?: string } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void loadFinanceBoard(query, controller.signal).then(data => { if (!controller.signal.aborted) setResult({ key: requestKey, data }) }).catch(cause => { if (!controller.signal.aborted) setResult({ key: requestKey, error: financeError(cause) }) })
    return () => controller.abort()
  }, [query, requestKey])
  const current = result?.key === requestKey ? result : null
  return <div className="finance-board">
    <header className="finance-heading"><div><p>经营管理</p><h2>财务看板</h2><span>合同、回款与应收的已发布台账</span></div><Banknote size={26} aria-hidden="true" /></header>
    <form className="finance-filters" onSubmit={event => { event.preventDefault(); const value = String(new FormData(event.currentTarget).get('q') || '').trim(); const next = new URLSearchParams(params); if (value) next.set('q', value); else next.delete('q'); setParams(next) }}>
      <label htmlFor="finance-query"><Search size={17} aria-hidden="true" /><input key={query} id="finance-query" name="q" aria-label="搜索项目、业主、负责人或状态" maxLength={100} defaultValue={query} placeholder="搜索项目、业主、负责人或状态" /></label><button type="submit">筛选</button><button type="button" className="finance-secondary" onClick={() => setAttempt(value => value + 1)} aria-label="刷新财务看板"><RefreshCw size={16} aria-hidden="true" />刷新</button>
    </form>
    {!current && <p className="finance-empty" role="status">正在读取财务台账…</p>}
    {current?.error && <p className="finance-error" role="alert">{current.error}</p>}
    {current?.data && <FinanceBoardContent key={current.key} data={current.data} query={query} />}
  </div>
}
