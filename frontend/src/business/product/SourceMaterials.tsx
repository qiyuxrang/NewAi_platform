import { useEffect, useMemo, useState } from "react";
import { Field } from "../shared";
import { extractionNames, getSourceDetail, sourceDownload, sourcePreview, type DocumentTask, type ExtractedBlock, type SourceAction, type SourceDetail } from "./product-api";
import { LoadState, ProductIcon } from "./workbench-shared";
import { formatBytes, formatDate, productError, useUnsavedWarning } from "./workbench-state";
import "./source-materials.css";
import { BusinessImage } from '../BusinessSurface';

interface Props {
  task: DocumentTask;
  busy: boolean;
  sourceId?: string;
  compact?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  onSourceAction?: SourceAction;
  onAction: (endpoint: string, body: object) => Promise<unknown>;
  disabled: (action: string) => boolean;
}
interface EditDraft { block: ExtractedBlock; text: string; cells?: string[]; reason: string; version: number; hash: string }

function sourceBlockGroups(blocks: ExtractedBlock[]) {
  const groups: ExtractedBlock[][] = [];
  for (const block of blocks) {
    const group = groups.at(-1);
    const previous = group?.at(-1);
    const location = block.location;
    const previousLocation = previous?.location;
    const sameTable = block.cells?.length && previous?.cells?.length === block.cells.length
      && (location.sheet || location.table != null)
      && (["sheet", "part", "table", "page", "image"] as const).every(key => location[key] === previousLocation?.[key])
      && location.row != null && previousLocation?.row != null && location.row === previousLocation.row + 1;
    if (sameTable) group!.push(block);
    else groups.push([block]);
  }
  return groups;
}

export default function SourceMaterials(props: Props) {
  return <ProjectSourceMaterials key={props.task.id} {...props}/>;
}

function ProjectSourceMaterials(props: Props) {
  const [selected, setSelected] = useState(props.sourceId || "");
  const id = props.task.sources.some(source => source.id === selected) ? selected : props.task.sources[0]?.id || "";
  return id ? <SourceInspector key={id} {...props} id={id} select={setSelected}/> : null;
}

function SourceInspector({ task, busy, onSourceAction, onAction, disabled, compact, onDirtyChange, id, select }: Props & { id: string; select: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [review, setReview] = useState<Record<string, { category: string; reason: string }>>({});
  const hasUnsaved = Boolean(draft) || Object.values(review).some(value => value.category || value.reason);
  useUnsavedWarning(hasUnsaved);
  useEffect(() => {
    onDirtyChange?.(hasUnsaved);
    return () => onDirtyChange?.(false);
  }, [hasUnsaved, onDirtyChange]);
  const taskId = task.id;
  const taskVersion = task.version;
  const requestQuery = new URLSearchParams({ q: query, page: String(page), revision }).toString();
  const requestKey = useMemo(() => ({ id, taskId, taskVersion, requestQuery, refresh }), [id, taskId, taskVersion, requestQuery, refresh]);
  const [response, setResponse] = useState<{ key: typeof requestKey; data: SourceDetail | null; error: string } | null>(null);
  const current = response?.key === requestKey ? response : null;
  const data = current?.data ?? null;
  const error = current?.error ?? "";
  const [preview, setPreview] = useState<{ key: typeof requestKey; page: number | null; error: boolean } | null>(null);
  const previewPage = preview?.key === requestKey ? preview.page : null;
  const previewError = preview?.key === requestKey && preview.error;
  function setPreviewPage(nextPage: number | null) {
    setPreview(value => ({ key: requestKey, page: nextPage, error: value?.key === requestKey && value.error }));
  }
  function setPreviewError(nextError: boolean) {
    setPreview(value => ({ key: requestKey, page: value?.key === requestKey ? value.page : null, error: nextError }));
  }

  useEffect(() => {
    const controller = new AbortController();
    void getSourceDetail(requestKey.id, requestKey.requestQuery, controller.signal)
      .then(value => {
        if (!value.summary || !Array.isArray(value.blocks) || value.id !== requestKey.id || value.task_id !== requestKey.taskId) throw new Error("资料响应与当前项目不一致，请重新加载。");
        if (!controller.signal.aborted) setResponse({ key: requestKey, data: value, error: "" });
      }).catch(reason => { if (!controller.signal.aborted) setResponse({ key: requestKey, data: null, error: productError(reason) }); });
    return () => controller.abort();
  }, [requestKey]);

  function choose(next: string) {
    if (next === id) return;
    if (hasUnsaved && !window.confirm("当前资料有尚未保存的解析校正或人工核对依据。切换资料将放弃这些内容，继续？")) return;
    select(next);
  }
  function edit(block: ExtractedBlock) {
    if (!data) return;
    setDraft({ block, text: block.text, cells: block.cells ? [...block.cells] : undefined, reason: "", version: task.version, hash: data.summary.extraction_hash });
  }
  const stale = !!draft && (draft.version !== task.version || data?.task_version !== task.version || data?.summary.extraction_hash !== draft.hash);
  const base = data ? { expected_version: task.version, source_sha256: data.sha256, extraction_hash: data.summary.extraction_hash } : {};
  async function save() {
    if (!data || !draft || !onSourceAction || stale || busy) return;
    const body = { ...base, block_id: draft.block.id, text: draft.cells ? draft.cells.join("\t") : draft.text, ...(draft.cells ? { cells: draft.cells } : {}), reason: draft.reason.trim() };
    if (await onSourceAction(id, "correction/", body)) { setDraft(null); setRefresh(value => value + 1); }
  }
  function blockActions(block: ExtractedBlock) {
    return <div className="pd-source-block-actions">{block.confidence != null && <small>OCR 置信度 {(block.confidence * 100).toFixed(1)}%</small>}{block.correction && <span className="pd-badge info">已人工校正</span>}{data?.can_correct && <button className="text-button" disabled={busy || !!draft || !onSourceAction} onClick={() => edit(block)}>校正内容</button>}{data?.can_preview && block.location.page && <button className="text-button" onClick={() => { setPreviewPage(block.location.page!); setPreviewError(false); }}>查看原页</button>}</div>;
  }
  function originalText(block: ExtractedBlock) {
    return block.original_text != null && <details className="pd-source-original"><summary>校正前提取文字</summary><p>{block.original_text || "未识别到文字"}</p><small>依据：{block.correction?.reason}</small></details>;
  }
  return <section className={`pd-panel pd-source-inspector${compact ? " pd-source-compact" : ""}`} aria-label="资料解析与来源核对">
    {!compact && <div className="pd-panel-heading"><div><h3>资料解析与来源核对</h3><p>按原位置查看文字与表格，校正后形成新版本，原文件保持不变。</p></div><span className="pd-badge info">本地解析</span></div>}
    <div className="pd-source-shell">
      {compact ? <label className="pd-source-picker">核对资料<select aria-label="选择解析资料" value={id} disabled={busy} onChange={event => choose(event.target.value)}>{task.sources.map(source => <option key={source.id} value={source.id}>{source.original_name} · {source.parsed ? extractionNames[source.parsed.status] : "已接收"}</option>)}</select></label> : <nav className="pd-source-list" aria-label="选择解析资料">
        {task.sources.map(source => <button type="button" key={source.id} onClick={() => choose(source.id)} className={id === source.id ? "selected" : ""} aria-pressed={id === source.id} disabled={busy}>
          <ProductIcon name="file"/><span><strong>{source.original_name}</strong><small>{source.parsed ? extractionNames[source.parsed.status] : "已接收"} · {formatBytes(source.size)}</small></span>
        </button>)}
      </nav>}
      <div className="pd-source-content">
        {!data ? <LoadState error={error} reload={() => setRefresh(value => value + 1)}/> : <>
          <div className="pd-source-heading"><div><h4>{data.name}</h4><p>{({ native: "原生文字与表格提取", ocr: "本地 OCR 文字识别", mixed: "原生文字 + 本地 OCR" })[data.summary.method]} · {data.summary.character_count} 字 · {data.summary.item_count} 行设备清单</p></div><span className={`pd-badge ${data.summary.status === "completed" ? "good" : "warning"}`}>{extractionNames[data.summary.status]}</span></div>
          <div className="pd-source-tools"><a className="pd-quiet-link" href={sourceDownload(id)}>下载原文件</a>
            {data.can_preview && <button className="text-button" onClick={() => { setPreviewError(false); setPreviewPage(previewPage ? null : 1); }}>{previewPage ? "收起原件预览" : "预览原件"}</button>}
            <button className="text-button" disabled={busy || !data.can_reparse || !onSourceAction || hasUnsaved} onClick={async () => { if (window.confirm("重新解析会生成新的项目输入版本，并要求重新核对蓝图。保留原文件和历史解析，继续？") && await onSourceAction?.(id, "reparse/", base)) setRefresh(value => value + 1); }}>重新解析</button>
            <label>解析版本<select aria-label="选择解析版本" disabled={hasUnsaved || busy} value={revision} onChange={event => { setRevision(event.target.value); setPage(1); }}><option value="">当前解析</option>{data.revisions.map(item => <option key={item.version} value={item.version}>v{item.version} · {formatDate(item.created_at)}</option>)}</select></label>
          </div>
          {!!revision && <p className="pd-service-note">正在查看历史解析快照；校正和重试请切回当前解析。</p>}
          {data.warnings.length > 0 && <details className="pd-source-warnings" open={data.summary.status === "partial" || data.summary.status === "failed"}><summary>解析提示 {data.warnings.length} 项 · 当前待核对 {data.issues.length} 项</summary>{data.warnings.map((warning, index) => <p key={index}><strong>{warning.severity === "partial" ? "未完整解析：" : ""}</strong>{warning.detail || warning.code}</p>)}</details>}
          {previewPage !== null && <div className="pd-source-preview"><div className="pd-actions"><label>原件页码<input type="number" min={1} max={data.summary.metadata.pages || 1} value={previewPage} onChange={event => { const page = Number(event.target.value); if (Number.isInteger(page) && page >= 1 && page <= (data.summary.metadata.pages || 1)) { setPreviewPage(page); setPreviewError(false); } }}/></label><span className="pd-muted">预览仅为原件图像，不执行链接或文档脚本。</span></div>{previewError ? <p role="alert">无法生成当前页预览，请下载原文件核对。</p> : <BusinessImage key={`${id}-${previewPage}`} src={sourcePreview(id, previewPage)} alt={`${data.name} 原件第 ${previewPage} 页`}/>}</div>}
          <form className="pd-search" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); setPage(1); }}><ProductIcon name="search"/><input aria-label="搜索解析文字" placeholder="搜索当前资料中的文字…" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} disabled={!!draft}/><button className="text-button" disabled={!!draft}>查找</button></form>
          {draft && <form className="pd-source-editor" onSubmit={event => { event.preventDefault(); void save(); }}>
            <h4>校正：{draft.block.location_label}</h4>{stale && <p role="alert" className="pd-feedback">项目或解析版本已变化。本地编辑已保留，请重新核对后再保存。</p>}
            {draft.cells ? <div className="pd-source-cell-editor">{draft.cells.map((cell, index) => <Field key={index} id={`source-cell-${index}`} label={`第 ${index + 1} 列`}><input id={`source-cell-${index}`} maxLength={2000} value={cell} disabled={busy || stale} onChange={event => setDraft({ ...draft, cells: draft.cells!.map((value, i) => i === index ? event.target.value : value) })}/></Field>)}</div> : <Field id="source-corrected-text" label="校正后的文字"><textarea id="source-corrected-text" required rows={6} maxLength={16000} value={draft.text} disabled={busy || stale} onChange={event => setDraft({ ...draft, text: event.target.value })}/></Field>}
            <Field id="source-correction-reason" label="校正依据"><input id="source-correction-reason" required maxLength={2000} value={draft.reason} disabled={busy || stale} onChange={event => setDraft({ ...draft, reason: event.target.value })} placeholder="例如：已对照原图第 2 行核对设备型号"/></Field>
            <div className="pd-actions"><button className="button primary" disabled={busy || stale || !draft.reason.trim() || !data.can_correct}>保存解析校正</button><button type="button" className="button secondary" disabled={busy} onClick={() => setDraft(null)}>取消校正</button></div>
          </form>}
          <div className="pd-extraction-blocks" aria-label="解析内容块">{sourceBlockGroups(data.blocks).map(group => {
            const first = group[0];
            return first.cells ? <div className="pd-source-table-wrap" key={first.id} tabIndex={0} role="region" aria-label={`${first.location_label} 表格内容`}><table className="pd-source-table">
              <caption>{[first.location.sheet && `工作表 ${first.location.sheet}`, first.location.part, first.location.table != null && `表格 ${first.location.table}`].filter(Boolean).join(" · ") || first.location_label}</caption>
              <thead><tr><th scope="col">原位置</th>{first.cells.map((_, index) => <th scope="col" key={index}>第 {index + 1} 列</th>)}<th scope="col">核对</th></tr></thead>
              <tbody>{group.map(block => <tr key={block.id}><th scope="row">{block.location_label}</th>{block.cells!.map((cell, index) => <td key={index}>{cell || <span className="pd-source-blank" aria-label="空白单元格">空白</span>}</td>)}<td className="pd-source-table-review">{blockActions(block)}{originalText(block)}</td></tr>)}</tbody>
            </table></div> : <article key={first.id}><header><span>{first.location_label}</span>{blockActions(first)}</header><p>{first.text}</p>{originalText(first)}</article>;
          })}</div>
          {!data.blocks.length && <div className="pd-empty"><h4>{query ? "没有匹配文字" : "暂无可用解析文字"}</h4><p>{query ? "请调整搜索词。" : "可重传更清晰的资料，或依据原文件补录文字。"}</p>{!query && data.can_correct && <button className="button secondary" disabled={busy || !!draft} onClick={() => edit({ id: "manual1", text: "", kind: "paragraph", location: {}, location_label: "人工补录原件文字" })}>补录文字</button>}</div>}
          <div className="pd-pagination"><span>共 {data.pagination.total} 段 · 第 {page} 页</span><div><button className="text-button" disabled={page <= 1 || !!draft} onClick={() => setPage(value => value - 1)}>上一页</button><button className="text-button" disabled={page * 40 >= data.pagination.total || !!draft} onClick={() => setPage(value => value + 1)}>下一页</button></div></div>
          {data.issues.length > 0 && <details className="pd-source-review"><summary>人工核对待处理项（{data.issues.length}）</summary><p className="pd-muted">由项目所有者依据原件分类并记录核对依据；历史项目的授权审核人仍可核对资料。解析完成不代表事实已确认。</p>{data.issues.map(issue => {
            const value = review[issue.issue_hash] || { category: "", reason: "" };
            return <form key={issue.issue_hash} onSubmit={async event => { event.preventDefault(); if (await onAction("input-review/", { resolutions: [{ issue_hash: issue.issue_hash, category: value.category, reason: value.reason.trim(), source_ids: [id] }] })) { setReview(current => { const next = { ...current }; delete next[issue.issue_hash]; return next; }); setRefresh(current => current + 1); } }}><p>{issue.detail || issue.code}</p><div className="pd-actions"><select aria-label={`核对分类 ${issue.code}`} value={value.category} disabled={disabled("review_input")} onChange={event => setReview({ ...review, [issue.issue_hash]: { ...value, category: event.target.value } })}><option value="">请选择判断</option><option value="fact">事实</option><option value="inference">推断</option><option value="conflict">冲突</option><option value="missing">缺项</option></select><input aria-label={`核对依据 ${issue.code}`} value={value.reason} maxLength={4000} disabled={disabled("review_input")} onChange={event => setReview({ ...review, [issue.issue_hash]: { ...value, reason: event.target.value } })} placeholder="对照原件填写核对依据"/><button className="button secondary" disabled={disabled("review_input") || !value.category || !value.reason.trim()}>保存核对</button></div></form>;
          })}</details>}
        </>}
      </div>
    </div>
  </section>;
}

