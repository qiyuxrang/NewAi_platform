import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, X } from "lucide-react";
import type { DocumentTask, InputIssue, ReviewCategory, SourceAction } from "./product-api";
import SourceMaterials from "./SourceMaterials";
import WorkbenchSeparator from "./WorkbenchSeparator";
import { useUnsavedWarning } from "./workbench-state";
import "./project-review-panel.css";

export type ProjectReviewSection = "sources" | "gaps" | "review";
const sections: { id: ProjectReviewSection; label: string }[] = [
  { id: "sources", label: "资料解析" }, { id: "gaps", label: "缺口与冲突" }, { id: "review", label: "待核验事项" },
];
interface Props {
  task: DocumentTask; section: ProjectReviewSection; sourceId?: string; busy: boolean;
  disabled: (action: string) => boolean; onAction: (endpoint: string, body: object) => Promise<unknown>;
  onSourceAction?: SourceAction; onChange: (section: ProjectReviewSection, sourceId?: string) => void;
  onClose: () => void; onBlueprint: () => void;
  width: number; min: number; max: number; expanded: boolean;
  onResize: (width: number) => void; onExpand: () => void;
}

export default function ProjectReviewPanel({ task, section, sourceId, busy, disabled, onAction, onSourceAction, onChange, onClose, onBlueprint, width, min, max, expanded, onResize, onExpand }: Props) {
  const pane = useRef<HTMLElement | null>(null);
  useEffect(() => { pane.current?.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]')?.focus({ preventScroll: true }); }, []);
  const conditions = task.blueprint?.payload.conditions ?? task.input?.conditions.map(text => ({ text, type: "human" })) ?? [];
  const missing = task.blueprint?.payload.missing.filter(Boolean) ?? [];
  const conflicts = task.blueprint?.payload.conflicts.filter(Boolean) ?? [];
  return <aside ref={pane} className="wb-review-pane" aria-label="项目资料核对面板" style={{ width: expanded ? "100%" : width }} onKeyDown={event => { if (event.key === "Escape" && !busy) { event.stopPropagation(); onClose(); } }}>
    {!expanded && <WorkbenchSeparator className="wb-review-separator" label="调整项目核对面板宽度" direction={-1} width={width} min={min} max={max} onResize={onResize}/>}
    <header className="wb-review-heading"><div><strong>项目资料核对</strong><small>资料与蓝图按当前项目版本核对</small></div><div className="pd-actions"><button type="button" aria-label={expanded ? "还原核对面板" : "放大核对面板"} onClick={onExpand}>{expanded ? <Minimize2 size={17}/> : <Maximize2 size={17}/>}</button><button type="button" aria-label="关闭核对面板" disabled={busy} onClick={onClose}><X size={19}/></button></div></header>
    <div className="wb-review-tabs" role="tablist" aria-label="资料核对分类">{sections.map(item => <button key={item.id} type="button" id={`review-tab-${item.id}`} role="tab" aria-selected={section === item.id} aria-controls="project-review-content" disabled={busy} onClick={() => { if (section !== item.id) onChange(item.id); }}>{item.label}</button>)}</div>
    <div id="project-review-content" className="wb-review-content" role="tabpanel" aria-labelledby={`review-tab-${section}`} key={`${task.id}-${section}-${sourceId || ""}`}>
      {section === "sources" && (task.sources.length ? <SourceMaterials task={task} busy={busy} disabled={disabled} onAction={onAction} onSourceAction={onSourceAction} sourceId={sourceId} compact/> : <p className="pd-muted">尚未上传项目资料，请先在项目资料页补充文件。</p>)}
      {section === "gaps" && <>
        <p className="pd-muted">按蓝图原文分别列出资料缺口与来源冲突；未提供来源关联的事项需对照项目资料核对。</p>
        {!task.blueprint && <p role="status">蓝图尚未生成，暂无蓝图缺口与冲突记录。</p>}
        {([{ title: "资料缺口", items: missing }, { title: "来源冲突", items: conflicts }]).map(group => <section key={group.title} className="wb-review-group"><h3>{group.title}<small>{group.items.length} 项</small></h3>{group.items.length ? <ol className="wb-review-issues">{group.items.map((text, index) => <li key={index}><p>{text}</p><button className="text-button" type="button" onClick={() => onChange("sources")}>对照项目资料 →</button></li>)}</ol> : <p className="pd-muted">{task.blueprint ? "蓝图当前未记录此类事项。" : "等待蓝图记录。"}</p>}</section>)}
        <button className="button secondary" type="button" onClick={onBlueprint}>返回蓝图查看与修改</button>
      </>}
      {section === "review" && <>
        <section className="wb-review-group"><h3>实施条件<small>{conditions.length} 项</small></h3><p className="pd-muted">实施条件单独核对，不等同于输入问题；没有单项核验记录时不标记为已完成。</p>{conditions.length ? <ol className="wb-review-conditions">{conditions.map((condition, index) => <li key={index}><span>{({ program: "程序校验", model: "模型辅助", human: "人工核对" } as Record<string, string>)[condition.type] || "核对方式待确认"}</span><p>{condition.text}</p></li>)}</ol> : <p className="pd-muted">当前未记录实施条件。</p>}</section>
        <InputReview task={task} disabled={disabled} onAction={onAction} onSource={id => onChange("sources", id)}/>
      </>}
    </div>
    <footer className="wb-review-footer"><span>校正与核验保留来源和版本记录</span><button type="button" className="button secondary" disabled={busy} onClick={onClose}>完成查看</button></footer>
  </aside>;
}

interface Resolution { category: ReviewCategory | ""; reason: string; source_ids: string[]; version: number; issue?: string }
function issueText(issue: InputIssue) {
  return [issue.detail, issue.message, issue.text, issue.code].find(value => typeof value === "string" && value.trim()) as string || "此项输入需要对照来源核对。";
}
function InputReview({ task, disabled, onAction, onSource }: Pick<Props, "task" | "disabled" | "onAction"> & { onSource: (id: string) => void }) {
  const [drafts, setDrafts] = useState<Record<string, Resolution>>({});
  const issues = task.input_issues;
  const dirty = Object.values(drafts).some(value => value.category || value.reason || value.source_ids.length);
  const staleDrafts = Object.entries(drafts).filter(([hash]) => !issues.some(issue => issue.issue_hash === hash));
  useUnsavedWarning(dirty);
  const sources = Array.from(new Map([
    ...task.sources.map(source => ({ id: source.id, name: source.original_name })),
    ...(task.input?.items || []).filter(item => String(item.row_id)).map(item => ({ id: String(item.row_id), name: `清单行 ${item.row_id}：${item.name}` })),
    ...(task.input?.knowledge_sources || []).map(source => ({ id: source.id, name: `知识来源：${source.location}` })),
  ].map(source => [source.id, source])).values());
  const sourceIds = new Set(sources.map(source => source.id));
  return <section className="wb-review-group"><h3>输入问题<small>{issues.length} 项待核验</small></h3><p className="pd-muted">判断需同时填写核对依据并关联当前项目来源。解析完成不代表事实已确认。</p>
    {staleDrafts.map(([hash, value]) => <section className="wb-input-review" key={hash}><p className="pd-feedback" role="alert">此问题已变化或已被核验，本地编辑仍保留，不能提交到旧问题。</p>{value.issue && <p>{value.issue}</p>}<label>已保留的核对依据<textarea aria-label="已保留的核对依据" readOnly rows={3} value={value.reason}/></label><button className="button secondary" type="button" onClick={() => setDrafts(current => { const next = { ...current }; delete next[hash]; return next; })}>放弃此草稿</button></section>)}
    {!issues.length && <p className="pd-muted">当前没有待核验的输入问题。</p>}
    {issues.map((issue, index) => {
      const value = drafts[issue.issue_hash] || { category: "", reason: "", source_ids: [], version: task.version };
      const stale = value.version !== task.version;
      const update = (change: Partial<Resolution>) => setDrafts(current => ({ ...current, [issue.issue_hash]: { ...value, issue: issueText(issue), ...change } }));
      return <form key={issue.issue_hash} className="wb-input-review" onSubmit={async event => {
        event.preventDefault();
        if (disabled("review_input") || stale || !value.category || !value.reason.trim() || !value.source_ids.length || value.source_ids.some(id => !sourceIds.has(id))) return;
        if (await onAction("input-review/", { resolutions: [{ issue_hash: issue.issue_hash, category: value.category, reason: value.reason.trim(), source_ids: value.source_ids }] })) setDrafts(current => { const next = { ...current }; delete next[issue.issue_hash]; return next; });
      }}>
        <h4>问题 {index + 1}</h4><p>{issueText(issue)}</p>
        {stale && <div className="pd-feedback" role="alert">项目版本已变化，编辑内容仍保留。请重新对照当前来源后继续。<button className="text-button" type="button" onClick={() => update({ version: task.version, source_ids: value.source_ids.filter(id => sourceIds.has(id)) })}>已重新对照当前版本</button></div>}
        <label>核对判断<select aria-label={`核对分类 ${index + 1}`} disabled={disabled("review_input") || stale} value={value.category} onChange={event => update({ category: event.target.value as Resolution["category"] })}><option value="">请选择判断</option><option value="fact">事实</option><option value="inference">推断</option><option value="conflict">冲突</option><option value="missing">缺项</option></select></label>
        <label>核对依据<textarea aria-label={`核对依据 ${index + 1}`} rows={3} maxLength={4000} disabled={disabled("review_input") || stale} value={value.reason} onChange={event => update({ reason: event.target.value })} placeholder="对照来源说明判断依据"/></label>
        <fieldset disabled={disabled("review_input") || stale}><legend>关联来源 {index + 1}</legend>{sources.map(source => <div key={source.id}><label><input type="checkbox" checked={value.source_ids.includes(source.id)} onChange={event => update({ source_ids: event.target.checked ? [...value.source_ids, source.id] : value.source_ids.filter(id => id !== source.id) })}/>{source.name}</label>{task.sources.some(item => item.id === source.id) && <button type="button" className="text-button" onClick={() => onSource(source.id)}>查看解析</button>}</div>)}{!sources.length && <p className="pd-muted">暂无可关联来源，请先补充项目资料。</p>}</fieldset>
        <button className="button primary" disabled={disabled("review_input") || stale || !value.category || !value.reason.trim() || !value.source_ids.length || value.source_ids.some(id => !sourceIds.has(id))}>保存核对</button>
      </form>;
    })}
  </section>;
}
