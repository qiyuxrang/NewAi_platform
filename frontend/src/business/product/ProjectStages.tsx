import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, CircleAlert, Clock3, FileCheck2, FileText, PanelRightClose, PanelRightOpen, RefreshCw, Target, UserRound, UsersRound, X } from "lucide-react";
import { BusinessImage } from "../BusinessSurface";
import { downloadBusinessFile } from "../api";
import { CenterLink, Field } from "../shared";
import { artifactDownload, artifactHistoryDownload, artifactPreview, blueprintChapters, draftDownload, draftHistoryDownload, draftPreview, manualBlueprint, savedDraftDownload, sourceDownload, type Artifact, type BlueprintPayload, type DocumentTask, type DraftOutput, type OutputFamily, type OutputQualityWarnings, type ProductWorkflowPhase, type ProductWorkflowProgress, type TaskHistory } from "./product-api";
import { DocumentSymbol, EmptyState, ProductIcon, StatusBadge } from "./workbench-shared";
import { formatBytes, formatDate, goProduct, outputNames, outputStatus, projectListUrl, projectUrl, stageNames, stateNames, useUnsavedWarning } from "./workbench-state";

import { blueprintDisplayText } from "./blueprint-display";
import ProjectInputPanel from "./ProjectInputPanel";
import './project-analysis.css';
import ProjectReviewPanel, { type ProjectReviewSection } from "./ProjectReviewPanel";
import { clampPanelWidth, useElementWidth } from "./workbench-resize";
import { SOURCE_ACCEPT, extractionNames, type SourceAction } from "./product-api";
import { presentationStyles, type PresentationStyle, type ProductKnowledgeStatus } from './product-api';
import { currentOutputVersions } from './project-refresh';

type Action = (endpoint: string, body: object) => Promise<unknown>;
interface Props { task: DocumentTask; outputs: DraftOutput[]; outputsLoaded: boolean; history: TaskHistory | null; outputsError: string; historyError: string; busy: boolean; conflict: boolean; confirmedUpload?: File | null; disabled: (action: string) => boolean; onAction: Action; onReload: () => void; onUpload: (file: File, purpose?: 'equipment' | 'background') => Promise<unknown>; onSourceAction?: SourceAction }
const tabs = [{ id: "blueprint", name: "蓝图审批" }, { id: "technical-solution", name: "技术方案" }, { id: "feasibility", name: "可研报告" }, { id: "presentation", name: "汇报 PPT" }, { id: "sources", name: "项目资料" }, { id: "history", name: "版本记录" }] as const;
type WorkspaceTab = typeof tabs[number]["id"];
const readTab = (fallback: WorkspaceTab = 'blueprint'): WorkspaceTab => {
  const requested = new URLSearchParams(window.location.search).get("tab") || fallback;
  const tab = requested === "overview" ? "blueprint" : requested === "outputs" ? "technical-solution" : requested;
  return tabs.some(item => item.id === tab) ? tab as WorkspaceTab : "blueprint";
};
const lines = (value: string) => value.split("\n").map(text => text.trim()).filter(Boolean);
const outputTargetLabel = (target: number) => `至少 ${target.toLocaleString()} 字`;
const reportFamilies = ['technical-solution', 'feasibility'] as const;
type ReportFamily = typeof reportFamilies[number];
const chapterGroups = (chapters: BlueprintPayload['chapters']): (ReportFamily | undefined)[] => chapters.some(chapter => chapter.family) ? [...reportFamilies] : [undefined];
const savedCharacters = (chapters: DocumentTask['chapters']) => chapters.reduce((total, chapter) => total + chapter.payload.paragraphs.reduce((count, paragraph) => count + Array.from(paragraph.replace(/\s/g, '')).length, 0), 0);
function currentSavedChapters({ chapters, blueprint, blueprint_approved }: Pick<DocumentTask, 'chapters' | 'blueprint' | 'blueprint_approved'>): DocumentTask['chapters'] {
  if (!blueprint_approved || !blueprint) return [];
  const planned = new Map(blueprint.payload.chapters.map(chapter => [chapter.id, chapter]));
  const latest = new Map<string, DocumentTask['chapters'][number]>();
  for (const chapter of chapters) {
    if (chapter.blueprint_hash && blueprint.sha256 && chapter.blueprint_hash !== blueprint.sha256) continue;
    if (chapter.input_hash && blueprint.input_hash && chapter.input_hash !== blueprint.input_hash) continue;
    const key = `${chapter.family}:${chapter.payload.chapter_id}`;
    const previous = latest.get(key);
    if (!previous || (chapter.version ?? 0) > (previous.version ?? 0)) latest.set(key, chapter);
  }
  return [...latest.values()].filter(chapter => {
    const spec = planned.get(chapter.payload.chapter_id);
    return spec && (!spec.family || spec.family === chapter.family) && spec.title === chapter.payload.title && chapter.payload.source_ids.every(source => spec.source_ids.includes(source));
  });
}

function generationStepLabel(key: string) {
  const family = key.includes('technical-solution') ? '技术方案' : key.includes('feasibility') ? '可研报告' : key.includes('presentation') ? '汇报文稿' : '';
  const step = key.startsWith('writing:') ? '正文生成' : key.startsWith('diagram:') ? '图表渲染' : key.includes('review') ? '内容审核' : key.includes('render') || key.includes('office') ? '文档排版' : '生成步骤';
  return `${family}${step}`;
}

function GenerationSteps({ task }: { task: DocumentTask }) {
  if (!task.generation_steps?.length) return null;
  const labels: Record<string, string> = { completed: '已缓存，可恢复时复用', running: '处理中', retry_wait: '临时故障，等待自动恢复', failed: '已暂停', pending: '等待开始' };
  return <section className="pd-recovery-records"><h3>已保存步骤与恢复状态</h3><p className="pd-muted">已保存的有效步骤会在恢复时复用；输入或蓝图变化后，以当前版本校验结果为准。</p><ol aria-label="已保存生成步骤">{task.generation_steps.map((step, index) => <li key={`${step.key}-${index}`}><strong>{generationStepLabel(step.key)}</strong><span>{labels[step.status] || '状态待确认'} · 已尝试 {step.attempts} 次</span>{step.retry_after && <p>预计 {formatDate(step.retry_after)} 后自动恢复</p>}</li>)}</ol></section>;
}

const qualityIssueNames: Record<string, string> = {
  quantity_mismatch: '设备数量与项目底稿不一致，需核对原始清单',
  quantity_source_ambiguous: '设备数量的来源范围待确认',
  unsupported_number: '正文数值缺少可靠依据',
  near_duplicate_content: '正文存在相近重复段落',
  partial_duplicate_content: '正文部分内容重复',
  internal_body_fragment: '正文含内部字段或占位残片，导出时已过滤，需核对该段',
  chapter_body_missing: '章节缺少有效正文，需补充该章内容',
  unresolved_input_items: '输入资料仍有未解决问题',
  unresolved_blueprint_items: '蓝图中的资料缺口或冲突待确认',
  source_review_required: '引用来源需要人工核对',
  source_outside_blueprint: '引用资料超出已批准蓝图范围',
};
const pendingFigureCount = (warnings?: OutputQualityWarnings) => warnings?.figures?.pending_count ?? warnings?.figures?.pending.length ?? 0;
const QualityWarnings = memo(function QualityWarnings({ warnings }: { warnings?: OutputQualityWarnings }) {
  const [open, setOpen] = useState(false);
  if (!warnings) return null;
  const pending = pendingFigureCount(warnings);
  const belowTarget = warnings.actual_characters !== undefined && warnings.minimum_characters !== undefined && warnings.actual_characters < warnings.minimum_characters;
  if (!warnings.issue_count && !pending && !belowTarget) return null;
  return <div className="pd-feedback" role="note" aria-label="成果质量提示"><strong>质量待核对</strong>{pending > 0 && <p>图表待补：已渲染 {warnings.figures!.rendered} / {warnings.figures!.planned} 张，待补 {pending} 张。已保存文件可先下载。</p>}{belowTarget && <p>正文已保存 {warnings.actual_characters!.toLocaleString()} 字，低于当前最低 {warnings.minimum_characters!.toLocaleString()} 字，需补充篇幅。</p>}{warnings.issue_count > 0 && <p>有 {warnings.issue_count} 项质量问题需人工核对；请对照项目资料与审核记录确认。</p>}{warnings.issues.length > 0 && <details onToggle={event => setOpen(event.currentTarget.open)}><summary>查看待核对问题</summary>{open && <ul>{warnings.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.text || qualityIssueNames[issue.code] || '内容待人工核对'}</li>)}</ul>}</details>}</div>;
});

// Draft preview availability is independent from formal candidate evidence.
// The candidate endpoint retains its own current-version and approval guards.
function currentPreview(output: DraftOutput | undefined, artifact: Artifact | undefined): string {
  if (!output?.current || output.stale) return '';
  if (output.has_preview === true && (output.page_count || 0) > 0) return draftPreview(output.id);
  return artifact?.render_evidence?.kind === 'candidate' && artifact.render_evidence.pages.length ? artifactPreview(artifact.id, 1) : '';
}

const failureMessages: Record<string, string> = {
  delivery_incomplete: '部分成果尚未通过交付检查；有效成果已交付，其余草稿可先下载。请查看问题后继续生成，无需再次审批成果。',
  busy: '模型服务繁忙，请稍后从已保存进度重试。',
  rate_limited: '模型服务调用频率受限，请稍后重试。',
  timeout: '模型响应超时，请稍后从已保存进度重试。',
  invalid_request: '模型请求未通过参数校验，请联系负责人检查调用配置。',
  invalid_model_output: '模型返回结果未通过格式或正文内容校验，自动纠正后仍未通过。已保存现有章节，可从已保存进度重试。',
  content_review_required: '正文已保存，仍有质量问题待核对。请查看草稿质量提示并核对资料缺项、数字和设备数量；原任务的恢复入口会保留有效步骤。',
  internal_error: '模型调用服务发生异常，请重试或联系负责人查看诊断记录。',
  upstream_error: '模型服务调用失败，已保存现有进度；自动重试仍失败时，可稍后从原任务继续。',
  upstream_invalid_request: '模型服务拒绝了请求参数，请先检查调用配置，再从原任务继续。',
  upstream_auth: '模型服务身份验证失败，请先检查模型访问权限，再从原任务继续。',
  unsupported_capability: '当前模型不支持所需能力，请联系负责人检查模型配置。',
  model_configuration_changed: '模型配置已变更，请刷新后重试。',
  ragflow_disabled: '产品知识库检索尚未启用或尚未获得调用授权，请联系管理员确认后重试。',
  ragflow_unconfigured: '知识库地址、访问凭据或专用模型路由尚未正确配置，请联系管理员检查后重试。',
  ragflow_forbidden: '当前账号无权检索产品知识库，请联系管理员核对账号权限后重试。',
  ragflow_scope_revoked: '当前账号尚未获得有效的知识库授权，或授权已变更、撤销。请联系管理员核对知识库授权范围后重试。',
  ragflow_unavailable: '知识库服务暂时无法连接，请恢复服务后从已保存进度重试；无需重新上传资料。',
  ragflow_invalid_response: '知识库返回内容未通过协议或授权范围校验，请联系管理员检查服务响应后重试。',
  equipment_analysis_required: '未解析出设备清单条目。请核对设备清单文件，补充设备名称、数量和单位后再生成；项目背景正文不能代替设备清单。',
  web_search_unconfigured: '知识库未命中；联网搜索服务尚未接入，已暂停生成。请补充知识库资料后重新检索。',
  output_length_below_target: '正文篇幅未达到当前最低要求，任务未完成；已保存现有章节，可续写补足篇幅，或从已保存进度重试。',
  diagram_generation_required: '图表尚未生成，正文已保存。已保存的草稿文件可先下载，缺图可从原任务恢复步骤补齐。',
  diagram_generation_invalid: '图表代码或正文依据未通过校验，正文已保存。请查看图表待补记录，从原任务恢复步骤补齐。',
  diagram_render_failed: '图表渲染失败，正文已保存。已保存的草稿文件可先下载，失败图表可从原任务恢复步骤补齐。',
  model_call_limit: '模型调用预算已耗尽，任务未完成；已保存现有进度，补充预算后可继续，或从已保存进度重试。',
};

function taskNextStep(task: DocumentTask): string {
  if (task.state === 'QUEUED') return '任务已进入后台队列；可离开页面，之后从当前项目查看进度。无需再次提交生成。';
  if (task.state === 'RUNNING') return '后台正在处理，节点与成果按保存记录更新；可离开后返回当前项目继续查看。';
  if (task.state === 'WAITING_REVIEW') return task.stage === 'BLUEPRINT' ? '请在“蓝图审批”中核对章节与来源，填写确认依据后批准或退回修改。' : '请核对当前成果、问题与审核记录，按后台提供的操作继续确认。';
  if (task.state === 'FAILED' || task.state === 'WAITING_INPUT') return '请先查看下方原因与完整处理节点，补齐资料、授权或服务条件后再继续；已保存的成果可在右侧及版本记录中查看。';
  if (task.state === 'COMPLETED') return '请在右侧下载已保存的成果，并核对文件版本与草稿或批准状态。';
  if (task.state === 'CANCELLED') return '任务已取消，原始资料和历史成果仍可查看。';
  return '请先核对项目资料，再根据可用操作生成蓝图。';
}

type VisibleStatus = ProductWorkflowProgress['status'];
const statusLabels: Record<VisibleStatus, string> = { pending: '等待开始', running: '处理中', completed: '已完成', failed: '处理失败', blocked: '暂时受阻', waiting: '等待确认', skipped: '未执行' };
const runtimeDetail = (detail: string) => detail.replaceAll('RAGFlow', '知识库').replaceAll('PPT', '汇报文稿').replaceAll('execution_failed', '执行失败').replace(/\bv(\d+)\b/g, '第 $1 版');
type VisiblePhase = { id: string; title: string; status: VisibleStatus; detail: string; statusLabel?: string; startedAt?: string; updatedAt?: string };
function RetrievalSummary({ task, kind }: { task: DocumentTask; kind: 'knowledge' | 'web-search' }) {
  const sources = (task.input?.knowledge_sources || []).filter(source => kind === 'knowledge'
    ? source.provider === 'ragflow' : source.fact_scope === 'PUBLIC_REFERENCE');
  const brief = (value: string | undefined, limit: number) => {
    const text = typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
    return Array.from(text).length > limit ? Array.from(text).slice(0, limit).join('') + '…' : text;
  };
  return <details className="pd-retrieval-summary"><summary>查看检索内容{sources.length ? `（${sources.length} 项）` : ''}</summary>
    {sources.length ? <><ul>{sources.slice(0, 3).map((source, index) => <li key={`${source.id}-${index}`}><strong>{brief(source.title, 60) || `来源 ${index + 1}`}</strong><p>{brief(source.text, 120) || '该来源未保存摘要。'}</p></li>)}</ul>{sources.length > 3 && <small>仅展示前 3 项，共 {sources.length} 项。</small>}{kind === 'web-search' && <small>公开资料仅作参考，不作为项目事实。</small>}</> : <p>本版本未保存可展示的检索内容。</p>}
  </details>;
}
function PhaseElapsed({ startedAt }: { startedAt: string }) {
  const [now, setNow] = useState(Date.now);
  const started = Date.parse(startedAt);
  const valid = Number.isFinite(started) && started <= now;
  useEffect(() => {
    if (!valid) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [started, valid]);
  if (!valid) return null;
  const seconds = Math.floor((now - started) / 1000);
  return <p>本阶段已等待 {Math.floor(seconds / 60)} 分 {seconds % 60} 秒</p>;
}
function workflowPhases(task: DocumentTask, outputs: DraftOutput[]): VisiblePhase[] {
  const persisted: Partial<Record<ProductWorkflowPhase | 'writing_editor', ProductWorkflowProgress>> = { ...task.analysis_progress, ...task.checkpoint?.analysis_progress };
  const phase = (key: keyof typeof persisted) => persisted[key];
  const knowledge = task.knowledge || task.blueprint_knowledge;
  const currentFamilies = new Set(outputs.filter(item => item.current && !item.stale).map(item => item.family));
  const requestedFamilies = task.output_families || ['technical-solution', 'feasibility', 'presentation'];
  const knowledgePhase = phase('knowledge');
  const knowledgeReady = knowledge?.status === 'ready' && knowledge.ragflow_used && knowledge.evidence_ready !== false;
  const knowledgeStatus = knowledgePhase?.status === 'completed' && !knowledgeReady ? knowledge?.evidence_ready === false ? 'blocked' : 'pending' : knowledgePhase?.status || (knowledgeReady ? 'completed' : knowledge?.status === 'waiting_for_ragflow' ? 'waiting' : knowledge?.status === 'source_only_preview' ? 'skipped' : 'pending');
  const reviewPhase = phase('review');
  const revision = task.blueprint_review;
  const currentRound = Math.min(revision.revision_count + 1, revision.revision_limit || 3);
  const reportPhases = (family: 'technical-solution' | 'feasibility', suffix: 'technical' | 'feasibility', title: string): VisiblePhase[] => {
    const writing = phase(`writing_${suffix}`);
    const review = phase(`review_${suffix}`);
    const diagrams = phase(`diagrams_${suffix}`);
    const render = phase(`render_${suffix}`);
    const progress = task.output_generation?.[family];
    const target = task.output_targets?.[family];
    const belowTarget = progress !== undefined && target !== undefined && progress.actual_characters < target;
    return [
      { id: `writing_${suffix}`, title: `${title}正文`, status: writing?.status || 'pending', statusLabel: writing?.status === 'completed' ? '正文已生成' : undefined, detail: `${writing?.detail || (progress ? `已保存 ${progress.actual_characters.toLocaleString()} 字${target === undefined ? '' : `；最低 ${target.toLocaleString()} 字`}` : '蓝图确认后开始正文编制')}${belowTarget ? '；篇幅待补，草稿可先下载' : ''}` },
      ...(review ? [{ id: `review_${suffix}`, title: `${title}独立复核`, status: review.status, detail: review.status === 'failed' ? failureMessages[task.error_code] || '正文复核已暂停，可从已保存进度重试。' : review.detail || '核对正文事实、数量与来源' }] : []),
      { id: `diagrams_${suffix}`, title: `${title}图表渲染`, status: diagrams?.status || 'pending', statusLabel: diagrams && ['pending', 'blocked', 'failed'].includes(diagrams.status) && currentFamilies.has(family) ? '图表待补' : undefined, detail: diagrams?.detail || '等待服务端提供图表渲染记录' },
      { id: `render_${suffix}`, title: `${title}文档排版`, status: render?.status || 'pending', detail: render?.detail || '等待 Word 排版与文件保存记录' },
    ];
  };
  const [technicalWriting, ...technicalFinishing] = reportPhases('technical-solution', 'technical', '技术方案');
  const [feasibilityWriting, ...feasibilityFinishing] = reportPhases('feasibility', 'feasibility', '可研报告');
  const editor = phase('writing_editor');
  const phases: VisiblePhase[] = [
    { id: 'documents', title: '解析项目背景', status: phase('documents')?.status || 'pending', detail: phase('documents')?.detail || '等待服务端提供背景材料解析记录' },
    { id: 'equipment', title: '分析设备清单', status: phase('equipment')?.status || 'pending', detail: phase('equipment')?.status === 'failed' ? failureMessages[task.error_code] || '设备清单分析失败，请核对设备清单文件后重试。' : phase('equipment')?.detail || '等待服务端提供设备事实分析记录' },
    { id: 'knowledge', title: '知识库检索', status: knowledgeStatus, detail: knowledgeStatus === 'failed' ? failureMessages[task.error_code] || '知识库检索失败，项目资料已保留，请联系管理员核对原因后重试。' : knowledge?.evidence_ready === false ? knowledge.detail : knowledgePhase?.detail || (knowledgeReady ? `知识库检索完成，命中 ${knowledge.ragflow_source_count ?? knowledge.source_count} 项知识来源${knowledge.web_source_count ? `；另有 ${knowledge.web_source_count} 项联网公开参考` : ''}` : knowledge?.detail || '知识检索状态尚未由服务端返回') },
    ...(phase('web_search') ? [{ id: 'web-search', title: '联网补充检索', status: phase('web_search')!.status, detail: phase('web_search')!.detail || '按服务端记录显示' }] : []),
    { id: 'blueprint', title: '生成项目蓝图', status: phase('blueprint')?.status || (task.blueprint ? 'completed' : 'pending'), startedAt: phase('blueprint')?.started_at, detail: phase('blueprint')?.detail || (task.blueprint ? `项目蓝图 v${task.blueprint.version} 已保存` : '等待前置分析完成') },
    { id: 'review', title: '本人确认蓝图', status: reviewPhase?.status || (task.blueprint_approved ? 'completed' : task.blueprint && task.state === 'WAITING_REVIEW' ? 'waiting' : 'pending'), detail: reviewPhase?.detail || (task.blueprint_approved ? '蓝图已确认' : `蓝图生成后需人工确认；第 ${currentRound}/${revision.revision_limit} 轮`) },
    technicalWriting,
    feasibilityWriting,
    ...(editor ? [{ id: 'writing_editor', title: '总编复核', status: editor.status, detail: editor.status === 'failed' ? failureMessages[task.error_code] || '总编复核已暂停，可从已保存进度重试。' : editor.detail || '核对章节与两份报告的共同口径' }] : []),
    ...technicalFinishing,
    ...feasibilityFinishing,
    ...(requestedFamilies.includes('presentation') ? [{ id: 'presentation', title: '汇报 PPT', status: phase('presentation')?.status || (currentFamilies.has('presentation') ? 'completed' : 'pending'), detail: phase('presentation')?.detail || '基于两份报告制作，不新增项目事实' }] : []),
    { id: 'downloads', title: '项目成果下载', status: requestedFamilies.every(family => currentFamilies.has(family)) ? 'completed' : 'pending', statusLabel: currentFamilies.size ? `${currentFamilies.size} 类成果可下载` : undefined, detail: '每份已保存的当前成果均可独立下载；草稿质量与正式交付状态单独显示' },
  ];
  return phases.map(item => ({ ...item, updatedAt: phase(item.id === 'web-search' ? 'web_search' : item.id as keyof typeof persisted)?.updated_at }));
}
export default function ProjectStages(props: Props) {
  const { task, outputs, outputsLoaded, history, outputsError, historyError, busy, conflict, confirmedUpload, disabled, onAction, onReload, onUpload, onSourceAction } = props;
  const results = useRef<HTMLElement | null>(null);
  const layout = useRef<HTMLDivElement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const layoutWidth = useElementWidth(layout);
  const [reviewPanel, setReviewPanel] = useState<{ section: ProjectReviewSection; sourceId?: string; sequence: number } | null>(null);
  const [reviewWidth, setReviewWidth] = useState<number | null>(null);
  const [reviewExpanded, setReviewExpanded] = useState(false);
  const availableWidth = layoutWidth || 1000;
  const reviewMin = Math.min(520, availableWidth);
  const reviewMax = Math.max(reviewMin, availableWidth - 240);
  const visibleReviewWidth = clampPanelWidth(reviewWidth ?? Math.min(840, availableWidth * .64), reviewMin, reviewMax);
  const openReview = (section: ProjectReviewSection, sourceId?: string) => {
    if (busy) return;
    if (reviewPanel && !window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) return;
    if (!reviewPanel) returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setReviewPanel(current => ({ section, sourceId, sequence: (current?.sequence ?? 0) + 1 }));
  };
  const closeReview = () => {
    if (busy) return;
    if (!window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) return;
    setReviewPanel(null);
    requestAnimationFrame(() => returnFocus.current?.focus({ preventScroll: true }));
  };
  const previousOutputs = useRef<Map<OutputFamily, string> | null>(null);
  useEffect(() => {
    if (!outputsLoaded) return;
    const next = currentOutputVersions(outputs);
    const previous = previousOutputs.current;
    previousOutputs.current = new Map([...(previous || []), ...next]);
    if (!previous || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const animations: Animation[] = [];
    for (const [family, version] of next) {
      if (previous.get(family) === version) continue;
      const card = results.current?.querySelector<HTMLElement>(`[data-output-family="${family}"]`);
      if (card?.animate) animations.push(card.animate([{ backgroundColor: '#fff' }, { backgroundColor: '#edf6ff' }, { backgroundColor: '#fff' }], { duration: 420, iterations: 2 }));
    }
    return () => animations.forEach(animation => animation.cancel());
  }, [outputs, outputsLoaded]);
  const [tab, setTab] = useState(() => readTab(task.blueprint_approved ? 'technical-solution' : 'blueprint'));
  const [progressOpen, setProgressOpen] = useState(false);
  const progressTrigger = useRef<HTMLButtonElement | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sourcePurpose, setSourcePurpose] = useState<'equipment' | 'background'>('background');
  useEffect(() => { if (file && file === confirmedUpload) { setFile(null); setSourcePurpose('background'); } }, [file, confirmedUpload]);
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState('');
  const [resultsOpen, setResultsOpen] = useState(true);
  useEffect(() => { let active = true; const sync = () => queueMicrotask(() => { if (active) setTab(readTab(task.blueprint_approved ? 'technical-solution' : 'blueprint')); }); window.addEventListener("popstate", sync); return () => { active = false; window.removeEventListener("popstate", sync); }; }, [task.blueprint_approved]);
  const returnTo = projectListUrl();
  const projectHref = (value: WorkspaceTab) => `${projectUrl(task.id, value)}&returnTo=${encodeURIComponent(returnTo)}`;
  const move = (value: WorkspaceTab) => {
    if (value !== activeTab && !window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) return;
    if (reviewPanel && value === activeTab && !window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) return;
    setReviewPanel(null);
    goProduct(projectHref(value));
  };
  const visibleTabs = tabs.filter(item => item.id !== 'presentation' || !task.output_families || task.output_families.includes('presentation'));
  const activeTab = visibleTabs.some(item => item.id === tab) ? tab : 'technical-solution';
  const download = async (path: string, filename: string) => {
    setDownloading(path); setDownloadError('');
    try { await downloadBusinessFile(path, filename); }
    catch (reason) { setDownloadError(reason instanceof Error ? reason.message : '下载失败，请重试。'); }
    finally { setDownloading(''); }
  };
  const running = ["RUNNING", "QUEUED"].includes(task.state);
  const automaticRecovery = task.state === 'QUEUED' && Boolean(task.retry_after);
  const pendingDraftDiagrams = task.state === 'WAITING_REVIEW' && task.stage === 'FINAL_REVIEW' && (outputs.some(output => output.current && !output.stale && output.draft && pendingFigureCount(output.quality_warnings) > 0) || task.quality_warnings?.some(warnings => pendingFigureCount(warnings) > 0));
  const retryAllowed = Array.isArray(task.actions) ? task.actions.includes('retry') : task.actions?.retry === true;
  const retryLimitReached = (task.state === 'FAILED' || task.state === 'WAITING_INPUT' || pendingDraftDiagrams) && task.retry_budget?.remaining === 0;
  const savedChapters = useMemo(() => currentSavedChapters({ chapters: task.chapters, blueprint: task.blueprint, blueprint_approved: task.blueprint_approved }), [task.chapters, task.blueprint, task.blueprint_approved]);
  const phases = workflowPhases(task, outputs);
  const settledPhases = phases.filter(phase => phase.status === 'completed' || phase.status === 'skipped').length;
  const paused = task.state === 'FAILED' || task.state === 'WAITING_INPUT';
  const failedPhase = phases.filter(phase => phase.status === 'failed' || phase.status === 'blocked')
    .sort((left, right) => (Date.parse(right.updatedAt || '') || 0) - (Date.parse(left.updatedAt || '') || 0))[0];
  const currentPhase = (paused && failedPhase) || phases.find(phase => phase.status === 'running') || failedPhase || phases.find(phase => phase.status === 'waiting') || phases.find(phase => phase.status === 'pending');
  const failureReason = task.error_code && !automaticRecovery ? task.error_code === 'model_authorization_required' ? '尚未取得模型调用与资料外发授权。项目已保留，可以先完善资料与人工蓝图。' : task.error_code === 'revision_requested' ? '蓝图已退回修改，请查看确认记录并修订。' : failureMessages[task.error_code] || (task.blueprint_approved ? '生成未完成，已保存项目资料和已完成章节。可从现有进度继续，不需要重新审批蓝图。' : '生成未完成，项目资料已保留，请核对提示后重试。') : '';
  const progressTitle = automaticRecovery ? '临时故障，已安排从保存进度自动恢复' : task.state === 'CANCELLED' ? '任务已取消' : paused ? `${currentPhase && currentPhase.status !== 'pending' ? currentPhase.title : '任务'}已暂停${savedChapters.length ? ' · 已保存部分正文' : ''}` : task.state === 'COMPLETED' ? '后台记录任务已完成，节点详情与成果以保存记录为准' : task.state === 'QUEUED' ? '排队中，等待开始处理' : task.state === 'WAITING_REVIEW' && task.stage === 'BLUEPRINT' ? '蓝图已生成，等待您确认' : settledPhases === phases.length ? '全部流程节点已结束' : currentPhase ? `${currentPhase.title} · ${currentPhase.statusLabel || { pending: '等待开始', running: '处理中', completed: '已完成', failed: '处理失败', blocked: '暂时受阻', waiting: '等待确认', skipped: '未执行' }[currentPhase.status]}` : '项目资料已保存';
  const stateHeading = task.state === "WAITING_REVIEW" && task.stage === "BLUEPRINT" ? "蓝图等待人工确认" : stateNames[task.state] || "项目状态待确认";
  const groupStatus = (ids: string[]): VisibleStatus => {
    const states = phases.filter(phase => ids.includes(phase.id)).map(phase => phase.status);
    if (states.length && states.every(state => state === 'skipped')) return 'skipped';
    if (states.length && states.every(state => state === 'completed' || state === 'skipped')) return 'completed';
    return (['failed', 'blocked', 'running', 'waiting'] as const).find(state => states.includes(state)) || 'pending';
  };
  const deliveryFiles = (task.output_families || ['technical-solution', 'feasibility', 'presentation']).map(family => outputs.filter(output => output.family === family && output.current && !output.stale).at(-1));
  const deliveryStatus: VisibleStatus = deliveryFiles.length && deliveryFiles.every(output => output?.delivered) ? 'completed' : task.error_code === 'delivery_incomplete' ? 'blocked' : groupStatus(['downloads']) === 'completed' ? 'waiting' : groupStatus(['downloads']);
  const visualSteps = [
    { title: '资料准备', status: task.blueprint ? 'completed' : groupStatus(['documents', 'equipment', 'knowledge', 'web-search', 'blueprint']) },
    { title: '蓝图确认', status: task.blueprint_approved ? 'completed' : groupStatus(['review']) },
    { title: '文档生成', status: groupStatus(['writing_technical', 'writing_feasibility', 'writing_editor', 'review_technical', 'diagrams_technical', 'render_technical', 'review_feasibility', 'diagrams_feasibility', 'render_feasibility', ...(!task.output_families || task.output_families.includes('presentation') ? ['presentation'] : [])]) },
    { title: '成果交付', status: deliveryStatus },
  ] as { title: string; status: VisibleStatus }[];
  const conditionCount = task.blueprint?.payload.conditions?.length ?? task.input?.conditions?.length ?? 0;
  const gapCount = (task.blueprint?.payload.missing?.filter(Boolean).length ?? 0) + (task.blueprint?.payload.conflicts?.filter(Boolean).length ?? 0);
  const openProgress = () => {
    if (reviewPanel && !window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) return;
    setReviewPanel(null);
    setProgressOpen(true);
  };
  const closeProgress = () => {
    setProgressOpen(false);
    requestAnimationFrame(() => progressTrigger.current?.focus({ preventScroll: true }));
  };
  const issueMessages = (task.issues || []).flatMap(issue => typeof issue === 'string' ? [issue] : issue && typeof issue === 'object' && 'text' in issue && typeof issue.text === 'string' ? [issue.text] : []);

  return <div ref={layout} className={`wb-project-layout${resultsOpen ? '' : ' wb-results-collapsed'}${reviewPanel ? ' wb-review-open' : ''}`}>
    <div className="pd-project-overview">
    <header className="pd-page-title pd-project-header"><div><CenterLink href={returnTo} className="pd-back-link">← 返回项目列表</CenterLink><h1>{task.title}<span className="wb-project-version">v{task.version}</span></h1><p>项目编号：{task.id} · 创建时间：{formatDate(task.created_at)} · 最近更新：{formatDate(task.updated_at)}</p></div><div className="pd-actions"><button className="button secondary" disabled={busy} onClick={onReload}><RefreshCw size={15}/>刷新状态</button>{!disabled("cancel") && <button className="button secondary pd-danger" onClick={() => setCancelling(true)}>取消任务</button>}</div></header>
    <ol className="pd-visual-steps" aria-label="项目阶段总览">{visualSteps.map((step, index) => <li key={step.title} data-status={step.status} aria-current={step.status === 'running' || step.status === 'waiting' ? 'step' : undefined}><span className="pd-visual-step-dot" aria-hidden="true">{step.status === 'completed' ? <Check/> : index + 1}</span><strong>{step.title}</strong><small>{step.title === '成果交付' && step.status === 'completed' ? '已交付' : statusLabels[step.status]}</small></li>)}</ol>
    <details className="pd-project-meta"><summary>项目信息 · {stageNames[task.stage] || '阶段待确认'}</summary><section className="pd-project-statusline" aria-label="项目当前状态" aria-live="polite">
      <div><Clock3/><span>当前状态</span><strong title={stateHeading}><StatusBadge task={task}/></strong></div>
      <div><FileText/><span>当前阶段</span><strong>{stageNames[task.stage] || "阶段待确认"}</strong></div>
      <div><UserRound/><span>项目所有者</span><strong>{task.owner_name || "未提供"}</strong></div>
      <div><UsersRound/><span>蓝图确认人</span><strong>{task.owner_name || "未提供"}</strong></div>
      <div><Clock3/><span>更新时间</span><strong>{formatDate(task.updated_at)}</strong></div>
    </section></details>
    {conflict && <div className="pd-feedback" role="alert">版本或前置条件发生变化。未保存的编辑已保留，请刷新后核对；不会自动覆盖服务端内容。</div>}
    {downloadError && <div className="pd-feedback" role="alert">{downloadError}</div>}
    {cancelling && <section role="alertdialog" aria-label="确认取消任务" className="pd-feedback"><h3>确认取消当前任务？</h3><p>取消后不能继续编辑这个任务。已上传资料和历史成果仍保留，不会删除。</p><div className="pd-actions"><button className="button secondary" onClick={() => setCancelling(false)}>继续处理</button><button className="button primary" disabled={busy || disabled("cancel")} onClick={async () => { if (await onAction("cancel/", {})) setCancelling(false); }}>确认取消</button></div></section>}
    <div className="pd-project-summary-row">
    <section className="pd-compact-progress" data-running={running} data-attention={Boolean(task.error_code) && !automaticRecovery} aria-label="项目处理进度">
      <div className="pd-task-summary"><div className="pd-current-task-heading">{task.error_code && !automaticRecovery ? <CircleAlert size={30}/> : <Target size={30}/>}<div><h3>当前任务：{progressTitle}</h3>
      {!!savedChapters.length && <p aria-label="正文保存情况">已保存正文：{savedChapters.length} 章 · {savedCharacters(savedChapters).toLocaleString()} 非空白字</p>}
      {currentPhase?.detail && !failureReason && <p role="status">{runtimeDetail(currentPhase.detail)}</p>}
      {failureReason && <p role="alert">{failureReason}</p>}
      {task.state === 'RUNNING' && currentPhase?.status === 'running' && currentPhase.startedAt && <PhaseElapsed key={currentPhase.startedAt} startedAt={currentPhase.startedAt}/>}
      {automaticRecovery && <p role="status">临时故障，预计 {formatDate(task.retry_after!)} 后从已保存进度自动恢复。已保存的正文和有效步骤已保留，无需重新提交或审批蓝图。</p>}
      <p className="pd-muted">{taskNextStep(task)}</p>
      </div></div><div className="pd-actions pd-task-actions">
      {task.error_code && !automaticRecovery && !pendingDraftDiagrams && (retryLimitReached || !disabled('retry')) && <button className="button primary" disabled={busy || retryLimitReached} aria-describedby={retryLimitReached ? 'retry-limit-note' : undefined} onClick={() => void onAction('retry/', {})}>{task.error_code === 'delivery_incomplete' ? '继续生成' : '从已保存进度重试'}</button>}
      {pendingDraftDiagrams && retryAllowed && <button className="button primary" disabled={disabled('retry') || retryLimitReached} aria-describedby={retryLimitReached ? 'diagram-repair-limit-note' : undefined} onClick={() => void onAction('retry/', {})}>补生成待补图表</button>}
      <button ref={progressTrigger} type="button" className="button secondary" aria-haspopup="dialog" aria-controls="project-progress-dialog" onClick={openProgress}>查看处理详情</button>
      </div></div>
      {retryLimitReached && <p id={pendingDraftDiagrams ? 'diagram-repair-limit-note' : 'retry-limit-note'} role="note">已执行 {task.retry_budget!.used} 次，执行上限为 {task.retry_budget!.limit} 次，当前额度已用完。已保存正文和蓝图批准仍保留；需由负责人确认并调整执行上限后继续。</p>}
    </section>
    <section className="pd-project-facts" aria-label="项目资料概况"><button type="button" aria-label="资料解析" onClick={() => openReview('sources')} title={`${task.input?.items.length ?? 0} 行清单事实 · 查看来源`}><FileText/><div><strong>资料</strong><b>{task.sources.length}</b></div><ChevronRight/></button><button type="button" onClick={() => openReview('review')} title={`输入问题 · 另有 ${conditionCount} 项实施条件`}><FileCheck2/><div><strong>待核验事项</strong><b>{task.input_issues.length}</b></div><ChevronRight/></button><button type="button" onClick={() => openReview('gaps')}><CircleAlert/><div><strong>缺口与冲突</strong><b>{gapCount}</b></div><ChevronRight/></button></section>
    </div></div>
    <div className="wb-project-center"><div className="pd-workspace pd-project-detail">
    {outputsError && <div className="pd-feedback pd-output-read-error" role="alert"><span>{outputsError}</span><button className="button secondary" disabled={busy} onClick={onReload}><RefreshCw size={14}/>重新读取成果</button></div>}
    <div className="pd-project-tabs">
      <div className="pd-detail-tabs" role="tablist" aria-label="项目交付工作区" onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button")); const current = buttons.indexOf(document.activeElement as HTMLButtonElement); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length; buttons[next]?.focus(); }}>{visibleTabs.map(item => <button key={item.id} id={`tab-${item.id}`} type="button" role="tab" aria-controls={`panel-${item.id}`} aria-selected={activeTab === item.id} data-state={activeTab === item.id ? "active" : "inactive"} tabIndex={activeTab === item.id ? 0 : -1} onClick={() => move(item.id)}>{item.name}{item.id === "sources" && <small>{task.sources.length}</small>}</button>)}</div>
      {activeTab === "blueprint" && <section id="panel-blueprint" role="tabpanel" aria-labelledby="tab-blueprint" className="pd-tab-panel">
        {!task.blueprint && <section className="pd-workbench-command" aria-labelledby="blueprint-start-title"><div><span className="pd-section-label">可执行操作</span><h3 id="blueprint-start-title">开始蓝图编制</h3></div><div className="pd-actions">{task.blueprint_knowledge?.required && task.blueprint_knowledge.status !== "ready" && <button className="button primary" disabled={disabled("queue_blueprint_knowledge")} onClick={() => void onAction("queue/", { action: "knowledge" })}>先检索知识库</button>}<button className={task.blueprint_knowledge?.required && task.blueprint_knowledge.status !== "ready" ? "button secondary" : "button primary"} disabled={disabled("queue_blueprint")} onClick={() => void onAction("queue/", { action: "blueprint" })}>生成项目蓝图</button></div><BlockerNotes task={task}/></section>}
        <BlueprintPanel task={task} disabled={disabled} busy={busy} onAction={onAction} onReview={openReview}/>
      </section>}
      {(["technical-solution", "feasibility", "presentation"] as const).map(family => activeTab === family && <section key={family} id={`panel-${family}`} role="tabpanel" aria-labelledby={`tab-${family}`} className="pd-tab-panel"><ArtifactWorkspace family={family} task={task} outputs={outputs} outputsError={outputsError} disabled={disabled} onAction={onAction} move={move} onDownload={download} downloading={Boolean(downloading)}/></section>)}
      {activeTab === "sources" && <section id="panel-sources" role="tabpanel" aria-labelledby="tab-sources" className="pd-tab-panel pd-sources-workspace">
        <ProjectInputPanel task={task} disabled={disabled} onAction={onAction}/>
        <section className="pd-workbench-section"><div className="pd-panel-heading"><h3>原始资料</h3><span className="pd-muted">{task.sources.length} 份资料</span></div>{task.sources.length ? <ul className="pd-upload-list">{task.sources.map(source => <li key={source.id}><ProductIcon name="file"/><div><strong>{source.original_name}</strong><small>{source.purpose === 'equipment' ? '设备清单 · ' : source.purpose === 'background' ? '项目背景材料 · ' : ''}{source.parsed ? `${extractionNames[source.parsed.status]} · ` : ""}{formatBytes(source.size)} · {formatDate(source.created_at)}{source.warnings?.length ? ` · ${source.warnings.length} 项待核对` : ""}</small></div><div className="pd-actions"><button className="button secondary" type="button" onClick={() => openReview('sources', source.id)}>查看解析</button><button className="text-button" type="button" disabled={Boolean(downloading)} onClick={() => void download(sourceDownload(source.id), source.original_name)}>下载原文件</button></div></li>)}</ul> : <EmptyState title="尚未上传附件" detail="可以先填写建设目标，也可以补充设备清单和背景资料。"/>}<div className="pd-source-upload">{task.intake_mode === 'equipment_background' && <><label htmlFor="source-purpose">资料类型</label><select id="source-purpose" value={sourcePurpose} onChange={event => setSourcePurpose(event.target.value as 'equipment' | 'background')}><option value="background">项目背景材料</option><option value="equipment" disabled={task.sources.some(source => source.purpose === 'equipment')}>设备清单（仅一份）</option></select></>}<label htmlFor="project-more-file">补充资料</label><input id="project-more-file" type="file" accept={SOURCE_ACCEPT} disabled={disabled("add_source")} onChange={event => setFile(event.target.files?.[0] || null)}/><button className="button primary" disabled={disabled("add_source") || !file} onClick={async () => { if (file && await onUpload(file, task.intake_mode === 'equipment_background' ? sourcePurpose : undefined)) { setFile(null); setSourcePurpose('background'); } }}>{busy ? "正在上传并解析…" : "上传并保存"}</button></div><p className="pd-muted">补充资料会形成新的输入版本，相关蓝图和成果需重新核对。上传不会覆盖原始文件。</p></section>
      </section>}
      {activeTab === "history" && <section id="panel-history" role="tabpanel" aria-labelledby="tab-history" className="pd-tab-panel">
        <section className="pd-workbench-section"><div className="pd-panel-heading"><h3>成果历史版本</h3><span className="pd-muted">保留旧版，不覆盖</span></div>{outputsError ? <p role="alert">{outputsError}</p> : outputs.length ? <div className="pd-table-wrap"><table className="pd-table"><thead><tr><th>成果</th><th>版本</th><th>状态</th><th>完整性摘要</th><th>下载</th></tr></thead><tbody>{[...outputs].reverse().map(item => <tr key={item.id}><td>{outputNames[item.family]}</td><td>v{item.version}</td><td>{outputStatus(item)}</td><td><code title={item.sha256}>{item.sha256.slice(0, 12)}…</code></td><td><button className="text-button" disabled={Boolean(downloading)} onClick={() => void download(item.family === "technical-solution" ? item.current ? artifactDownload(item.id) : artifactHistoryDownload(item.id) : item.current ? draftDownload(item.id) : draftHistoryDownload(item.id), `${task.title}-${outputNames[item.family]}-v${item.version}.${item.family === "presentation" ? "pptx" : "docx"}`)}>{item.current ? "下载当前文件" : "下载历史文件"}</button></td></tr>)}</tbody></table></div> : <EmptyState title="暂无成果版本" detail="已保存的输入和蓝图记录仍可在下方追溯。"/>}</section>
        {!!issueMessages.length && <section className="pd-workbench-section" aria-label="当前核对问题"><h3>当前需核对的问题</h3><p className="pd-muted">以下为后台保存的资料、蓝图及正文审核问题；请结合来源核对，重试不会代替人工处理。</p><ul>{issueMessages.map((message, index) => <li key={index}>{message}</li>)}</ul></section>}
        <section className="pd-workbench-section"><h3>项目生成与审核记录</h3>{historyError ? <p role="alert">{historyError}</p> : !history ? <p role="status">正在读取版本链…</p> : <ol className="pd-timeline">{[...history.timeline].reverse().map(event => <li key={`${event.event}-${event.id}`}><span className="pd-timeline-dot"/><div><strong>{({ revision: "版本保存", external_upload: "资料上传", ai_task: "后台处理", artifact: "成果生成", approval: "人工审核" } as Record<string, string>)[event.event] || "项目记录"}{event.family ? ` · ${outputNames[event.family] || event.family}` : ""}{event.version ? ` v${event.version}` : ""}</strong><p>{event.reason || event.kind || "服务端已记录"} · {event.actor?.name || "系统"}</p>{event.sha256 && <small>摘要 {event.sha256.slice(0, 16)}…</small>}</div></li>)}</ol>}</section>
      </section>}
    </div>
  </div></div>
    <aside ref={results} className="wb-results" aria-label="项目成果"><header><div><FilesHeading/><strong>{resultsOpen ? '项目成果' : ''}</strong></div><button type="button" aria-label={resultsOpen ? '折叠成果面板' : '展开成果面板'} aria-expanded={resultsOpen} aria-controls="project-results" onClick={() => setResultsOpen(value => !value)}>{resultsOpen ? <PanelRightClose size={18}/> : <PanelRightOpen size={18}/>}</button></header>
      {resultsOpen && <div id="project-results" className="wb-results-body"><p className="wb-results-hint">技术方案、可研与汇报文稿<br/>基于同一份项目资料编制</p>
      <section className="wb-result-cards" aria-label="当前成果文件">{(['technical-solution', 'feasibility', 'presentation'] as const).map(family => {
        const output = outputs.filter(item => item.family === family && item.current && !item.stale).at(-1);
        const path = output ? family === 'technical-solution' ? artifactDownload(output.id) : draftDownload(output.id) : '';
        const requested = !task.output_families || task.output_families.includes(family);
        const warnings = output?.quality_warnings || task.quality_warnings?.find(item => item.family === family);
        const savedBody = savedChapters.some(chapter => chapter.family === family);
        return <article key={family} className="wb-result-card" data-output-family={family}><div className="wb-result-name"><DocumentSymbol family={family}/><div><strong>{outputNames[family]}</strong><small>{family === 'presentation' ? 'PowerPoint · PPTX' : 'Word · DOCX'}</small></div></div><p>{output ? `第 ${output.version} 版 · ${outputStatus(output)}` : outputsError ? '成果状态读取失败' : savedBody ? '正文已保存，文件待生成' : requested ? '等待文件生成' : '当前项目未请求此成果'}</p><QualityWarnings warnings={warnings}/>{output ? <div className="pd-actions"><button className="button primary" disabled={Boolean(downloading) || Boolean(outputsError)} onClick={() => void download(path, `${task.title}-${outputNames[family]}.${family === 'presentation' ? 'pptx' : 'docx'}`)}><ProductIcon name="download"/>{downloading === path ? '下载中…' : '下载文件'}</button><button className="text-button" type="button" onClick={() => move(family)}>打开{outputNames[family]}</button></div> : requested && <button type="button" className="text-button" onClick={() => move(family)}>打开{outputNames[family]}</button>}</article>;
      })}</section><button type="button" className="wb-history-link" onClick={() => move('history')}>查看全部版本与生成记录 →</button><section className="wb-source-summary"><h3>项目资料 <small>{task.sources.length}</small></h3>{task.sources.length ? <ul>{task.sources.map(source => <li key={source.id}><ProductIcon name="file"/><span>{source.original_name}</span></li>)}</ul> : <p>尚未上传资料</p>}<button className="text-button" type="button" onClick={() => move('sources')}>管理资料与核对事实 →</button></section></div>}
    </aside>
    <ProgressDetails task={task} phases={phases} title={progressTitle} open={progressOpen} onClose={closeProgress} reason={failureReason} onIssues={() => { closeProgress(); move(outputs.find(output => output.current && !output.stale && output.delivery_decision?.blocking_issues.length)?.family || (task.output_families || ['technical-solution', 'feasibility', 'presentation']).find(family => !outputs.some(output => output.family === family && output.current && !output.stale)) || 'technical-solution'); }}/>
    {reviewPanel && <ProjectReviewPanel key={`${task.id}-${reviewPanel.sequence}`} task={task} section={reviewPanel.section} sourceId={reviewPanel.sourceId} busy={busy} disabled={disabled} onAction={onAction} onSourceAction={onSourceAction} onChange={openReview} onClose={closeReview} onBlueprint={() => move('blueprint')} width={visibleReviewWidth} min={reviewMin} max={reviewMax} expanded={reviewExpanded} onResize={setReviewWidth} onExpand={() => setReviewExpanded(value => !value)}/>}
  </div>;
}

function ProgressDetails({ task, phases, title, open, onClose, reason, onIssues }: { task: DocumentTask; phases: VisiblePhase[]; title: string; open: boolean; onClose: () => void; reason: string; onIssues: () => void }) {
  const dialog = useRef<HTMLDialogElement | null>(null);
  const [section, setSection] = useState<'progress' | 'recovery'>('progress');
  useEffect(() => {
    const node = dialog.current;
    if (open && node && !node.open) node.showModal();
    else if (!open && node?.open) node.close();
  }, [open]);
  return <dialog ref={dialog} id="project-progress-dialog" className="pd-progress-dialog" aria-labelledby="project-progress-title" onClose={onClose} onClick={event => {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.currentTarget.close();
  }}>
    <header className="pd-progress-dialog-heading"><div><h2 id="project-progress-title">处理详情</h2><p>{task.title}</p></div><button type="button" aria-label="关闭处理详情" onClick={() => dialog.current?.close()}><X size={20}/></button></header>
    <div className="pd-progress-dialog-tabs" role="tablist" aria-label="处理详情分类" onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : section === 'progress' ? 1 : 0;
      buttons[next]?.click(); buttons[next]?.focus();
    }}>{([{ id: 'progress', name: '处理进度' }, { id: 'recovery', name: '恢复记录' }] as const).map(item => <button key={item.id} id={`progress-tab-${item.id}`} type="button" role="tab" aria-selected={section === item.id} aria-controls={`progress-panel-${item.id}`} tabIndex={section === item.id ? 0 : -1} onClick={() => setSection(item.id)}>{item.name}</button>)}</div>
    <div className="pd-progress-dialog-content">
      <section id="progress-panel-progress" role="tabpanel" aria-labelledby="progress-tab-progress" hidden={section !== 'progress'}>
        <div className="pd-progress-current"><strong>{title}</strong><p>完成 {phases.filter(phase => phase.status === 'completed').length} / {phases.length} 个节点 · 未执行 {phases.filter(phase => phase.status === 'skipped').length} 个</p></div>
        {reason && <section id="project-failure-reason" className="pd-progress-reason" aria-label="处理原因"><h3>当前任务需要处理</h3><p>{reason}</p>{task.error_code === 'delivery_incomplete' && <button type="button" className="button secondary" onClick={onIssues}>查看问题</button>}</section>}
        <ol className="pd-progress-node-list" aria-label="完整处理链路">{phases.map((phase, index) => <li key={phase.id} data-status={phase.status} aria-current={phase.status === 'running' ? 'step' : undefined}>
          <span className="pd-progress-node-index" aria-hidden="true">{phase.status === 'completed' ? <Check size={15}/> : phase.status === 'failed' || phase.status === 'blocked' ? <CircleAlert size={16}/> : index + 1}</span>
          <div><div className="pd-progress-node-heading"><h3>{phase.title}</h3><span>{phase.statusLabel || statusLabels[phase.status]}</span></div><p>{runtimeDetail(phase.detail)}</p>
          {(phase.id === 'knowledge' || phase.id === 'web-search') && !['pending', 'running', 'skipped'].includes(phase.status) && <RetrievalSummary task={task} kind={phase.id}/>}</div>
        </li>)}</ol>
      </section>
      <section id="progress-panel-recovery" role="tabpanel" aria-labelledby="progress-tab-recovery" hidden={section !== 'recovery'}>
        {task.generation_steps?.length ? <GenerationSteps task={task}/> : <p className="pd-muted">当前版本暂无已保存步骤记录。</p>}
      </section>
    </div>
    <footer className="pd-progress-dialog-footer"><span>进度自动更新，阅读位置保持不变</span><button type="button" className="button secondary" onClick={() => dialog.current?.close()}>返回文档</button></footer>
  </dialog>;
}

function FilesHeading() { return <ProductIcon name="layers"/>; }

const SavedChapter = memo(function SavedChapter({ chapter, initialOpen = false }: { chapter: DocumentTask['chapters'][number]; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)}><summary>{chapter.payload.title}</summary>{open && <>{chapter.payload.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}<small>引用 {chapter.payload.source_ids.length} 项资料</small></>}</details>;
});

function ArtifactWorkspace({ family, task, outputs, outputsError, disabled, onAction, move, onDownload, downloading }: { family: OutputFamily; task: DocumentTask; outputs: DraftOutput[]; outputsError: string; disabled: (action: string) => boolean; onAction: Action; move: (tab: WorkspaceTab) => void; onDownload: (path: string, filename: string) => Promise<void>; downloading: boolean }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState('');
  const [copyFallback, setCopyFallback] = useState(false);
  const [deliveryIssuesOpen, setDeliveryIssuesOpen] = useState(false);
  const output = outputs.filter(item => item.family === family && item.current && !item.stale).at(-1);
  const artifact = output && task.artifacts.find(item => item.id === output.id);
  const warnings = output?.quality_warnings || task.quality_warnings?.find(item => item.family === family);
  const preview = currentPreview(output, artifact);
  const progress = family === "presentation" ? undefined : task.output_generation?.[family];
  const target = family === "presentation" ? undefined : task.output_targets?.[family];
  const targetLabel = target === undefined ? undefined : outputTargetLabel(target);
  const meetsMinimum = progress !== undefined && target !== undefined && progress.actual_characters >= target;
  const format = family === "presentation" ? "PowerPoint · PPTX" : "Word · DOCX";
  const content = useMemo(() => {
    const chapterOrder = new Map((family === 'presentation' ? [] : blueprintChapters(task.blueprint?.payload, family)).map((chapter, index) => [chapter.id, index]));
    return currentSavedChapters({ chapters: task.chapters, blueprint: task.blueprint, blueprint_approved: task.blueprint_approved }).filter(chapter => chapter.family === family).sort((a, b) => (chapterOrder.get(a.payload.chapter_id) ?? Infinity) - (chapterOrder.get(b.payload.chapter_id) ?? Infinity));
  }, [family, task.chapters, task.blueprint, task.blueprint_approved]);
  const fullText = useMemo(() => content.map(chapter => [chapter.payload.title, ...chapter.payload.paragraphs].join('\n\n')).join('\n\n'), [content]);
  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopyStatus('已复制全部已保存正文。'); setCopyFallback(false);
    } catch {
      setCopyStatus('浏览器未允许自动复制，请在下方原文框中全选后按 Ctrl+C。'); setCopyFallback(true);
    }
  };
  return <section className="pd-artifact-workspace" aria-labelledby={`${family}-title`}>
    <header className="pd-artifact-title"><div className="pd-artifact-head"><DocumentSymbol family={family}/><div><span className="pd-section-label">成果工作区</span><h3 id={`${family}-title`}>{outputNames[family]}</h3><small>{format}</small></div></div>{outputsError ? <span className="pd-badge warning">成果状态读取失败</span> : output ? <span className={`pd-badge ${(output.delivered || output.approved) ? "good" : "warning"}`}>{outputStatus(output)}</span> : <span className={`pd-badge ${content.length ? "warning" : "neutral"}`}>{content.length ? "正文已保存，文件待生成" : "尚未生成"}</span>}</header>
    {output ? <>
      <details className="pd-file-details"><summary>文件信息与交付状态</summary><dl className="pd-artifact-facts"><div><dt>当前版本</dt><dd>v{output.version}</dd></div><div><dt>交付状态</dt><dd>{outputStatus(output)}</dd></div><div><dt>内容来源</dt><dd>{output.content_version ? `内容 v${output.content_version} · 来源快照` : "结构化内容来源"}</dd></div>{targetLabel && <div><dt>篇幅结果</dt><dd>{progress ? `${progress.actual_characters.toLocaleString()} / ${targetLabel} · ${meetsMinimum ? "已达目标" : "未达当前最低要求，可续写或重试"}` : targetLabel}</dd></div>}</dl></details>
      <div className="pd-workbench-command"><div><span className="pd-section-label">可执行操作</span><h3>当前成果文件</h3></div><div className="pd-actions"><button className="button primary" disabled={downloading || Boolean(outputsError)} onClick={() => void onDownload(family === "technical-solution" ? artifactDownload(output.id) : draftDownload(output.id), `${task.title}-${outputNames[family]}.${family === "presentation" ? "pptx" : "docx"}`)}><ProductIcon name="download"/>{downloading ? "正在下载…" : "下载文件"}</button>{preview ? <button type="button" className="button secondary" aria-expanded={previewOpen} onClick={() => setPreviewOpen(value => !value)}>{previewOpen ? '收起首页预览' : '预览第 1 页'}</button> : <span className="pd-muted">暂无 Office 预览证据</span>}<button className="button secondary" onClick={() => move("history")}>查看历史版本</button></div></div>
      {previewOpen && preview ? <BusinessImage key={`${output.id}-${output.sha256}`} src={preview} alt={`${outputNames[family]}第 1 页授权预览`}/> : null}
    </> : !content.length && <div className="pd-artifact-empty"><h3>{task.blueprint_approved ? runningOutputMessage(task) : "蓝图尚未确认，成果生成保持锁定"}</h3><p>{task.blueprint_approved ? "每份当前成果文件保存后即可下载；已保存正文可先下载 TXT 草稿。" : "请先在蓝图审批中完成确认。"}</p><div className="pd-actions"><button className="button primary" onClick={() => move("blueprint")}>查看蓝图审批</button>{task.retry_budget?.remaining !== 0 && !disabled("retry") && <button className="button secondary" onClick={() => void onAction("retry/", {})}>重试生成</button>}</div></div>}
    {family === 'presentation' && <PresentationWorkspace task={task} output={output} artifact={artifact} disabled={disabled} onAction={onAction}/>}
    <QualityWarnings warnings={warnings}/>
    {!!output?.delivery_decision?.blocking_issues.length && <section className="pd-feedback" aria-label={`${outputNames[family]}交付问题`}><strong>草稿已保存，以下问题待修复</strong><details onToggle={event => setDeliveryIssuesOpen(event.currentTarget.open)}><summary>查看全部 {output.delivery_decision.blocking_issues.length} 项交付问题</summary>{deliveryIssuesOpen && <ul>{output.delivery_decision.blocking_issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.text || qualityIssueNames[issue.code] || failureMessages[issue.code] || ({ chapters_incomplete: '章节尚未齐备', stale_report_review: '内容检查记录与当前正文版本不一致', program_checks_incomplete: '内容检查尚未完成', model_content_issues: '内容检查发现需修正的问题', document_structure_incomplete: '文档结构尚未齐备', source_report_not_delivered: '来源报告尚未通过交付检查', presentation_quality_failed: 'PPT 质量检查尚未通过', presentation_program_checks_failed: 'PPT 排版检查尚未通过', diagram_pending: '图表仍需补生成', artifact_hash_mismatch: '文件完整性需重新校验', output_missing: '成果文件尚未生成', blueprint_approval_required: '需要先确认项目蓝图', stale_output: '成果对应旧版项目资料' } as Record<string, string>)[issue.code] || '生成检查未通过，请继续生成或联系负责人核对'}{issue.family && `（${outputNames[issue.family as OutputFamily] || '报告'}）`}</li>)}</ul>}</details></section>}
    {!!content.length && <section className="wb-saved-content" aria-label={`${outputNames[family]}已保存正文`}><div className="pd-panel-heading"><h3>已保存的正文内容 · {content.length} 章 · {savedCharacters(content).toLocaleString()} 非空白字</h3><div className="pd-actions"><button type="button" className="button secondary" onClick={() => void copyText()}>复制全文</button>{family !== "presentation" && <button type="button" className="button secondary" disabled={downloading} onClick={() => void onDownload(savedDraftDownload(task, family), `已保存正文草稿-${task.title}-${outputNames[family]}.txt`)}><ProductIcon name="download"/>{downloading ? "正在下载…" : "下载正文草稿 TXT"}</button>}</div></div><p className="pd-muted">按蓝图章节顺序显示当前版本已保存原文。TXT 草稿会保留待配图、待排版等未完成提示；正文保存不代表成果文件已生成或正式交付。</p>{copyStatus && <p role="status">{copyStatus}</p>}{copyFallback && <textarea aria-label={`${outputNames[family]}全文复制原文`} readOnly value={fullText} rows={12} onFocus={event => event.currentTarget.select()}/>} {content.map((chapter, index) => <SavedChapter key={chapter.id} chapter={chapter} initialOpen={index === 0}/>)}</section>}
    <BlockerNotes task={task}/>
  </section>;
}

function runningOutputMessage(task: DocumentTask) { return ["RUNNING", "QUEUED"].includes(task.state) ? "后台正在生成成果" : "当前版本尚无可下载成果"; }

function PresentationWorkspace({ task, output, artifact, disabled, onAction }: { task: DocumentTask; output?: DraftOutput; artifact?: Artifact; disabled: (action: string) => boolean; onAction: Action }) {
  const [style, setStyle] = useState<PresentationStyle>('auto');
  const filePlan = output?.presentation_plan || artifact?.render_evidence?.presentation_plan;
  const plan = task.presentation_plan || filePlan;
  const progress = task.checkpoint?.analysis_progress?.presentation || task.analysis_progress?.presentation;
  const statuses: Record<VisibleStatus, string> = { pending: '等待制作', running: '制作中', completed: '文件已保存', failed: '制作失败', blocked: '制作受阻', waiting: '等待处理', skipped: '未执行' };
  const counted = progress && Number.isInteger(progress.completed_count) && Number.isInteger(progress.total_count) && progress.total_count! > 0 && progress.completed_count! >= 0 && progress.completed_count! <= progress.total_count!;
  return <section className="pd-presentation-plan" aria-label="PPT 风格与大纲">
    <div className="pd-panel-heading"><div><h3>汇报设计与制作进度</h3><p className="pd-muted">两份报告完成后自动选择风格并制作 PPT。</p></div>{progress && <span className="pd-badge neutral">{statuses[progress.status]}</span>}</div>
    {progress && <div className="pd-presentation-progress" role="status" aria-live="polite"><p>{progress.detail || statuses[progress.status]}</p>{counted && <><progress max={progress.total_count} value={progress.completed_count} aria-label="PPT 逐页制作进度" aria-valuetext={`已制作 ${progress.completed_count} / ${progress.total_count} 页`}/><p>已制作 {progress.completed_count} / {progress.total_count} 页</p></>}</div>}
    {output && <p className="pd-muted">可下载文件：第 {output.version} 版{filePlan ? ` · ${filePlan.style_label}` : ''}。{progress && ['running', 'failed', 'blocked'].includes(progress.status) ? '本次制作期间保留现有文件下载。' : ''}</p>}
    {plan ? <><dl className="pd-artifact-facts"><div><dt>本次视觉风格</dt><dd>{plan.style_label}</dd></div><div><dt>汇报目标</dt><dd>{plan.goal_label}</dd></div><div><dt>依据报告</dt><dd>{plan.sources.map(source => `${outputNames[source.family as OutputFamily] || '报告'} v${source.version}`).join('、')}</dd></div></dl><p className="pd-muted">选择依据：{plan.selection_reason}</p><details className="pd-presentation-outline" open><summary>逐页大纲 · {plan.pages.length} 页</summary><ol>{plan.pages.map(page => <li key={page.page}><details><summary>第 {page.page} 页 · {page.title}</summary>{page.core_message && page.core_message !== page.title && <p>{page.core_message}</p>}{page.items.length > 0 && <ul>{page.items.map((item, index) => <li key={index}>{item}</li>)}</ul>}{page.speaker_notes && <details><summary>演讲备注</summary><p>{page.speaker_notes}</p></details>}<small>引用 {page.source_refs.length} 项报告依据</small></details></li>)}</ol></details></> : <p className="pd-muted">等待后台保存 PPT 风格与逐页大纲。</p>}
    <form className="pd-presentation-style" onSubmit={event => { event.preventDefault(); if (!disabled('queue_presentation')) void onAction('queue/', { action: 'presentation', presentation_style: style }); }}><Field id="presentation-style" label="可选：更换 PPT 风格"><select id="presentation-style" value={style} disabled={disabled('queue_presentation')} onChange={event => setStyle(event.target.value as PresentationStyle)}>{Object.entries(presentationStyles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><button type="submit" className="button secondary" disabled={disabled('queue_presentation')}>{output ? '按所选风格生成新 PPT 版本' : '按所选风格制作 PPT'}</button><p className="pd-muted">仅生成新的 PPT 版本，保留两份报告与历史成果；生成失败仍可下载已有文件。</p></form>
  </section>;
}

function BlockerNotes({ task }: { task: DocumentTask }) { const notes = Array.from(new Set(Object.entries(task.blockers || {}).filter(([action]) => action !== 'queue_retrieve').map(([, value]) => value.detail))); return notes.length ? <div className="pd-blockers">{notes.map(note => <p key={note}><ProductIcon name="shield"/>{note}</p>)}</div> : null; }

function BlueprintPanel({ task, disabled, busy, onAction, onReview }: { task: DocumentTask; disabled: (action: string) => boolean; busy: boolean; onAction: Action; onReview: (section: ProjectReviewSection) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<BlueprintPayload | null>(null);
  const [baseVersion, setBaseVersion] = useState(task.version);
  const [commentDraft, setCommentDraft] = useState({ key: '', value: '' });
  useUnsavedWarning(editing);
  const blueprint = task.blueprint;
  const commentKey = `${blueprint?.id || ''}:${blueprint?.sha256 || ''}`;
  const comment = commentDraft.key === commentKey ? commentDraft.value : '';
  const setComment = (value: string) => setCommentDraft({ key: commentKey, value });
  const pendingReview = Boolean(blueprint && task.state === "WAITING_REVIEW" && task.stage === "BLUEPRINT" && !task.blueprint_approved);
  const changed = editing && task.version !== baseVersion;
  const decide = async (decision: "approve" | "revise") => {
    if (!blueprint) return;
    if (await onAction("decisions/", { target: "blueprint", target_id: blueprint.id, sha256: blueprint.sha256, decision, comment: comment.trim() })) setComment("");
  };
  function edit() {
    setDraft(blueprint ? structuredClone(blueprint.payload) : manualBlueprint(task.input));
    setBaseVersion(task.version); setEditing(true);
  }
  const sourceChoices = [...task.sources.map(source => ({ id: source.id, name: source.original_name })), ...(task.input?.items || []).filter(item => item.row_id).map(item => ({ id: String(item.row_id), name: `清单行 ${item.row_id}：${item.name}` })),  ...(task.input?.knowledge_sources || []).map(source => ({ id: source.id, name: source.location }))];
  return <section className="pd-panel pd-blueprint"><div className="pd-panel-heading"><div><h3>项目蓝图 {blueprint && <span className="pd-badge info">v{blueprint.version}</span>}</h3><p className="pd-muted">确认每章标题、计划字数、主要内容及资料依据后，再进入正文编制。</p></div><div className="pd-actions">{!editing && <button className="button secondary" disabled={disabled("save_blueprint")} onClick={edit}>{blueprint ? "修改蓝图" : "人工编制蓝图"}</button>}</div></div>
    {editing && draft ? <form onSubmit={async event => { event.preventDefault(); if (!changed && await onAction("blueprint/", { payload: { ...draft, missing: lines(draft.missing.join("\n")), conflicts: lines(draft.conflicts.join("\n")) } })) setEditing(false); }}>
      {changed && <p role="alert" className="pd-feedback">服务端已出现新版本。当前编辑仍保留，请取消本地编辑并重新载入后核对，不能直接覆盖。</p>}
      <fieldset className="pd-form-fields" disabled={busy || changed || disabled("save_blueprint")}>
        <div className="pd-form-columns"><Field id="visual-blueprint-purpose" label="建设目标"><textarea id="visual-blueprint-purpose" required maxLength={5000} value={draft.purpose} onChange={event => setDraft({ ...draft, purpose: event.target.value })}/></Field><Field id="visual-blueprint-audience" label="文档受众"><input id="visual-blueprint-audience" required maxLength={1000} value={draft.audience} onChange={event => setDraft({ ...draft, audience: event.target.value })}/></Field></div>
        <h4>章节与建设范围</h4>{!draft.chapters.some(chapter => chapter.family) && <p className="pd-muted">沿用历史共享目录，技术方案与可研使用同一目录。</p>}
        {chapterGroups(draft.chapters).map(family => {
          const group = draft.chapters.map((chapter, index) => ({ chapter, index })).filter(({ chapter }) => !family || !chapter.family || chapter.family === family);
          const name = family ? outputNames[family] : '历史共享目录';
          return <section className="pd-chapter-family" aria-label={`${name}章节编辑`} key={family || 'shared'}><h4>{name} · {group.length} 个章节</h4>
            {group.map(({ chapter, index }, position) => <div className="pd-blueprint-chapter" key={chapter.id}><span className="pd-number">{position + 1}</span><div><Field id={`visual-chapter-${index}`} label={`${name}第 ${position + 1} 章标题`}><input id={`visual-chapter-${index}`} value={chapter.title} required maxLength={160} onChange={event => setDraft({ ...draft, chapters: draft.chapters.map((value, i) => i === index ? { ...value, title: event.target.value } : value) })}/></Field><Field id={`visual-scope-${index}`} label={`${name}第 ${position + 1} 章范围`}><textarea id={`visual-scope-${index}`} value={chapter.scope} maxLength={5000} onChange={event => setDraft({ ...draft, chapters: draft.chapters.map((value, i) => i === index ? { ...value, scope: event.target.value } : value) })}/></Field><fieldset className="pd-source-choices"><legend>引用资料</legend>{sourceChoices.length ? sourceChoices.map(source => <label key={source.id}><input type="checkbox" checked={chapter.source_ids.includes(source.id)} onChange={event => setDraft({ ...draft, chapters: draft.chapters.map((value, i) => i === index ? { ...value, source_ids: event.target.checked ? [...value.source_ids, source.id] : value.source_ids.filter(id => id !== source.id) } : value) })}/>{source.name}</label>) : <small>尚无附件，可先整理章节范围。</small>}</fieldset></div><button className="text-button pd-danger" type="button" disabled={group.length <= 1} aria-label={`移除${name}第 ${position + 1} 章`} onClick={() => setDraft({ ...draft, chapters: draft.chapters.filter((_, i) => i !== index) })}>移除</button></div>)}
            <button className="button secondary" type="button" disabled={draft.chapters.length >= 200} onClick={() => setDraft({ ...draft, chapters: [...draft.chapters, { id: `chapter-${crypto.randomUUID()}`, title: "", scope: "", source_ids: [], ...(family ? { family } : {}) }] })}>＋ 添加{name}章节</button>
          </section>;
        })}
        <h4>实施与审核条件</h4>{draft.conditions.map((condition, index) => <div className="pd-condition-row" key={index}><input aria-label={`条件 ${index + 1}`} value={condition.text} required maxLength={1000} onChange={event => setDraft({ ...draft, conditions: draft.conditions.map((value, i) => i === index ? { ...value, text: event.target.value } : value) })}/><select aria-label={`条件 ${index + 1} 核对方式`} value={condition.type} onChange={event => setDraft({ ...draft, conditions: draft.conditions.map((value, i) => i === index ? { ...value, type: event.target.value as "human" | "program" | "model" } : value) })}><option value="human">人工核对</option><option value="program">程序校验</option><option value="model">模型辅助</option></select><button className="text-button" type="button" disabled={task.input?.conditions.includes(condition.text)} onClick={() => setDraft({ ...draft, conditions: draft.conditions.filter((_, i) => i !== index) })}>移除</button></div>)}<button className="text-button" type="button" onClick={() => setDraft({ ...draft, conditions: [...draft.conditions, { text: "", type: "human" }] })}>＋ 添加条件</button>
        <div className="pd-form-columns"><Field id="visual-missing" label="资料缺口（每行一项）"><textarea id="visual-missing" value={draft.missing.join("\n")} onChange={event => setDraft({ ...draft, missing: event.target.value.split("\n") })}/></Field><Field id="visual-conflicts" label="来源冲突（每行一项）"><textarea id="visual-conflicts" value={draft.conflicts.join("\n")} onChange={event => setDraft({ ...draft, conflicts: event.target.value.split("\n") })}/></Field></div>
      </fieldset><div className="pd-actions"><button type="submit" className="button primary" disabled={changed || disabled("save_blueprint")}>保存蓝图新版本</button><button type="button" className="button secondary" disabled={busy} onClick={() => { if (window.confirm("放弃当前未保存的蓝图编辑？")) setEditing(false); }}>取消编辑</button></div>
    </form> : blueprint ? <>
      <BlueprintReview task={task} blueprint={blueprint} canReview={pendingReview && !disabled("confirm_blueprint")} busy={busy} comment={comment} setComment={setComment} onDecide={decide} onReview={onReview}/>
    </> : <EmptyState title="等待形成项目蓝图" detail="可通过模型生成，也可由项目负责人先人工整理目标、章节与条件。模型授权不足不会阻止人工准备。"/>}
  </section>;
}

function BlueprintReview({ task, blueprint, canReview, busy, comment, setComment, onDecide, onReview }: { task: DocumentTask; blueprint: NonNullable<DocumentTask["blueprint"]>; canReview: boolean; busy: boolean; comment: string; setComment: (value: string) => void; onDecide: (decision: "approve" | "revise") => Promise<void>; onReview: (section: ProjectReviewSection) => void }) {
  const readOnlyMessage = task.blueprint_approved ? "该蓝图已批准，审核内容只读。" : "当前用户无蓝图审批权限，内容仅供查看。";
  return <section className="pd-blueprint-inline" aria-label={`项目蓝图 v${blueprint.version}`}>
      <BlueprintReviewContent task={task} blueprint={blueprint} onReview={onReview}/>
      <div className="pd-blueprint-review">
        {canReview ? <>
          <Field id="visual-blueprint-comment" label="蓝图确认依据"><textarea id="visual-blueprint-comment" disabled={busy} value={comment} onChange={event => setComment(event.target.value)} rows={3} placeholder="请填写确认依据；如需调整，请描述修改要求。" maxLength={10000}/></Field>
          {task.blueprint_review.revisions_remaining === 0 && <p className="pd-muted">自动修改次数已用完，仍可批准当前蓝图。</p>}
          <div className="pd-form-footer pd-review-actions"><div className="pd-actions"><button className="button secondary" disabled={busy || !comment.trim() || task.blueprint_review.revisions_remaining === 0} onClick={() => void onDecide("revise")}>退回修改（剩余 {task.blueprint_review.revisions_remaining}/{task.blueprint_review.revision_limit} 次）</button><button className="button primary" disabled={busy || !comment.trim()} onClick={() => void onDecide("approve")}>批准蓝图并生成成果<ProductIcon name="arrow"/></button></div></div>
        </> : <p className="pd-blueprint-readonly" role="status">{readOnlyMessage}</p>}
      </div>
  </section>;
}

function BlueprintReviewContent({ task, blueprint, onReview }: { task: DocumentTask; blueprint: NonNullable<DocumentTask["blueprint"]>; onReview: (section: ProjectReviewSection) => void }) {
  const knowledge: ProductKnowledgeStatus = task.knowledge || task.blueprint_knowledge || { mode: 'source_only_preview', required: false, status: "source_only_preview", ragflow_used: false, source_count: 0, detail: "知识检索状态尚未由服务端返回。" };
  const verified = knowledge.status === "ready" && knowledge.ragflow_used && knowledge.evidence_ready !== false;
  const unavailable = knowledge.status === "waiting_for_ragflow";
  return <>
    <div className="pd-blueprint-summary"><h4>项目概述</h4><p>{blueprintDisplayText(blueprint.payload.purpose)}</p><small>受众：{blueprintDisplayText(blueprint.payload.audience)}</small></div>
    <section className="pd-chapter-plan" aria-label="章节设计"><h4>章节设计 · {blueprint.payload.chapters.length} 个章节</h4><p className="pd-muted">计划字数按当前生成规则均分至各章，不是已生成字数；技术方案与可研分别计算。</p>{!blueprint.payload.chapters.some(chapter => chapter.family) && <p className="pd-muted">沿用历史共享目录，技术方案与可研使用同一目录。</p>}
      {chapterGroups(blueprint.payload.chapters).map(family => {
        const chapters = family ? blueprintChapters(blueprint.payload, family) : blueprint.payload.chapters;
        return <section className="pd-chapter-family" aria-label={`${family ? outputNames[family] : '历史共享'}目录`} key={family || 'shared'}><h4>{family ? outputNames[family] : '历史共享目录'} · {chapters.length} 个章节</h4><ol>{chapters.map((chapter, index) => <li key={chapter.id}><details className="pd-chapter-disclosure"><summary><strong>{index + 1}. {chapter.title}</strong><span>{chapter.source_ids.length} 项依据 · 展开详情</span></summary><div><div className="pd-chapter-budgets">{(family ? [family] : reportFamilies).map(reportFamily => <span key={reportFamily}>{reportFamily === 'technical-solution' ? '技术方案' : '可行性研究报告'}：{task.output_targets?.[reportFamily] !== undefined ? outputTargetLabel(Math.ceil(task.output_targets[reportFamily] / chapters.length)) : '字数目标未提供'}</span>)}</div><p className="pd-chapter-scope"><strong>主要内容</strong>{blueprintDisplayText(chapter.scope) || "尚未说明，请在修改蓝图中补充本章主要内容。"}</p><small>引用 {chapter.source_ids.length} 项资料</small></div></details></li>)}</ol></section>;
      })}
    </section>
    {blueprint.payload.feasibility_guide && <details className="pd-chapter-disclosure"><summary><strong>可研编制范围与裁剪依据</strong></summary><ul>{blueprint.payload.feasibility_guide.sections.map(section => <li key={section.section_id}><strong>{section.section_id} · {section.status === 'include' ? '适用' : section.status === 'pending' ? '待补充' : '不适用'}</strong>：{section.reason}{section.chapter_ids.length > 0 && <span>（对应：{section.chapter_ids.map(id => blueprint.payload.chapters.find(chapter => chapter.id === id)?.title || '章节已移除，需重新核对').join('、')}）</span>}</li>)}</ul></details>}
    <div className="pd-issue-grid"><section><strong>{task.input?.items.length || 0}<small>清单事实行</small></strong><p>来自项目输入与上传清单</p><button className="text-button" type="button" onClick={() => onReview('sources')}>查看来源 →</button></section><section><strong>{blueprint.payload.conditions.length}<small>实施与审核条件</small></strong><p>单独核对，审批保留原始条件</p><button className="text-button" type="button" onClick={() => onReview('review')}>查看待核验事项 →</button></section><section><strong>{blueprint.payload.missing.filter(Boolean).length + blueprint.payload.conflicts.filter(Boolean).length}<small>缺口与冲突</small></strong><p>按资料缺口与来源冲突分别查看</p><button className="text-button" type="button" onClick={() => onReview('gaps')}>查看事项 →</button></section></div>
    <div className={`pd-feedback ${verified ? "success" : "pd-knowledge-preview"}`} role="status"><strong>{verified ? "知识库检索已完成" : knowledge.evidence_ready === false ? "参考证据尚不足" : unavailable ? "知识库暂不可用" : "仅使用项目资料"}</strong><p>{verified ? `已记录 ${knowledge.source_count} 项可追溯参考来源。` : knowledge.evidence_ready === false ? knowledge.detail : unavailable ? "正式蓝图生成保持锁定；可先整理项目资料与人工蓝图。" : "本版本未执行知识库检索，未产生知识库命中记录。"}</p>{knowledge.ragflow_source_count !== undefined && <p>知识库来源 {knowledge.ragflow_source_count} 项 · 联网公开参考 {knowledge.web_source_count ?? 0} 项</p>}{knowledge.web_search && <p>{knowledge.web_search.detail}</p>}{(knowledge.web_source_count ?? 0) > 0 && <p>联网公开资料只作参考，不作为当前项目事实。</p>}</div>
    <p className="pd-review-round"><strong>蓝图审核轮次</strong><span>已修改 {task.blueprint_review.revision_count} 次 · 最多 {task.blueprint_review.revision_limit} 次 · 剩余 {task.blueprint_review.revisions_remaining} 次</span></p>
  </>;
}
