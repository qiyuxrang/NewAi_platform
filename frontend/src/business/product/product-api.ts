import { ApiError, apiRequest } from "../api";

export const SOURCE_ACCEPT = ".csv,.txt,.pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff";
export interface SourceLocation { page?: number; paragraph?: number; table?: number; row?: number; sheet?: string; range?: string; part?: string; image?: number; bbox?: number[][]; image_width?: number; image_height?: number }
export interface ExtractionSummary { status: "completed" | "needs_review" | "partial" | "failed"; method: "native" | "ocr" | "mixed"; extraction_hash: string; parser_version: string; block_count: number; item_count: number; character_count: number; truncated: boolean; metadata: { pages?: number; sheets?: number; images?: number } }
export interface ExtractedBlock { id: string; kind: string; text: string; location: SourceLocation; location_label: string; cells?: string[]; confidence?: number; original_text?: string; correction?: { actor_id: number; reason: string } }
export interface SourceWarning { code: string; detail?: string; row?: number; severity?: string; location?: SourceLocation }
export interface SourceDetail { id: string; task_id: string; task_version: number; name: string; sha256: string; size: number; media_type: string; summary: ExtractionSummary; blocks: ExtractedBlock[]; warnings: SourceWarning[]; issues: (SourceWarning & { issue_hash: string })[]; revisions: { version: number; sha256: string; created_at: string; reason: string }[]; pagination: { page: number; page_size: number; total: number }; can_reparse: boolean; can_correct: boolean; can_preview: boolean }
export const getSourceDetail = (id: string, query: string, signal: AbortSignal) => apiRequest<SourceDetail>(`/api/product/sources/${encodeURIComponent(id)}/?${query}`, { signal });
export const sourcePreview = (id: string, page = 1) => `/api/product/sources/${encodeURIComponent(id)}/preview/?page=${page}`;
export const updateSource = (id: string, endpoint: "reparse/" | "correction/", body: object, signal: AbortSignal) => apiRequest<unknown>(`/api/product/sources/${encodeURIComponent(id)}/${endpoint}`, { method: endpoint === "correction/" ? "PATCH" : "POST", body: JSON.stringify(body), signal });
export type SourceAction = (id: string, endpoint: "reparse/" | "correction/", body: object) => Promise<unknown>;
export const extractionNames = { completed: "解析完成", needs_review: "解析待核对", partial: "部分解析", failed: "未提取到文字" };

export interface TaskInput {
  project: string;
  requirements: string;
  items: { row_id: string | number; name: string; quantity: string | number; unit: string; source_item_id?: string; source_location?: SourceLocation; source_id?: string }[];
  background: string;
  conditions: string[];
  knowledge_sources?: { id: string; location?: string; provider?: string; title?: string; text?: string; url?: string; fact_scope?: string }[];
}
export interface BlueprintPayload {
  purpose: string;
  audience: string;
  chapters: { id: string; title: string; scope: string; source_ids: string[]; family?: Exclude<OutputFamily, "presentation"> }[];
  conditions: { text: string; type: "program" | "model" | "human" }[];
  missing: string[];
  conflicts: string[];
  template_version: string;
  feasibility_guide?: { asset_sha256: string; sections: { section_id: string; status: 'include' | 'pending' | 'not_applicable'; chapter_ids: string[]; reason: string }[] };
}
export interface ChapterPayload { chapter_id: string; title: string; paragraphs: string[]; source_ids: string[] }
export type OutputFamily = "technical-solution" | "feasibility" | "presentation";
export const presentationStyles = { auto: '自动选择', business: '商务汇报', consulting: '咨询决策', government: '政务汇报', engineering: '技术评审', 'dark-tech': '深色科技', minimal: '简约展示' } as const;
export type PresentationStyle = keyof typeof presentationStyles;
export interface PresentationPlan {
  style: Exclude<PresentationStyle, 'auto'>;
  style_label: string;
  selection_reason: string;
  goal: string;
  goal_label: string;
  audience: string;
  sources: { family: string; version: number; sha256: string }[];
  pages: { page: number; title: string; type: string; core_message?: string; items: string[]; speaker_notes: string; source_refs: string[] }[];
}
export const blueprintChapters = (payload: BlueprintPayload | null | undefined, family: Exclude<OutputFamily, "presentation">) =>
  (payload?.chapters || []).filter(chapter => !chapter.family || chapter.family === family);
export function manualBlueprint(input: TaskInput | null): BlueprintPayload {
  const titles = {
    'technical-solution': ['需求分析与设计依据', '总体技术路线与系统架构', '子系统与设备配置设计', '部署实施与接口联调', '测试验收与运维设计'],
    feasibility: ['建设背景与必要性', '建设范围与基础条件', '技术与组织可行性', '投资估算与资金安排', '效益分析与风险评价'],
  };
  return { purpose: input?.requirements || '', audience: '项目评审人员',
    chapters: (['technical-solution', 'feasibility'] as const).flatMap(family => titles[family].map((title, index) => ({
      id: `${family}-chapter-${index + 1}`, family, title, scope: '', source_ids: [],
    }))), conditions: (input?.conditions || []).map(text => ({ text, type: 'human' as const })),
    missing: [], conflicts: [], template_version: 'frozen-original-v1' };
}
export interface OutputQualityWarnings {
  issue_count: number;
  issues: { code: string; text?: string }[];
  figures?: { planned: number; rendered: number; pending_count?: number; pending: { figure_id: string; error_code: string }[] };
  actual_characters?: number;
  minimum_characters?: number;
}
export type OutputReviewStatus = 'stale' | 'approved' | 'pending_review' | 'delivered';
export interface DeliveryDecision { status: 'stale' | 'draft' | 'delivered'; delivered: boolean; blocking_issues: { code: string; text?: string; family?: string }[]; warnings?: { code: string; text?: string }[]; quality_scope?: string }
export interface DraftOutput { id: string; family: OutputFamily; version: number; sha256: string; current: boolean; stale: boolean; draft: boolean; approved: boolean; delivered?: boolean; delivery_decision?: DeliveryDecision; review_status: OutputReviewStatus; quality_warnings?: OutputQualityWarnings; engine: string; content_version: number | null; content_sha256: string | null; content_approved: boolean | null; source_versions: { family: string; version: number; sha256: string; approval_id?: string }[]; has_preview?: boolean; page_count?: number; preview_url?: string | null; presentation_plan?: PresentationPlan | null }
export type ReviewCategory = "fact" | "inference" | "conflict" | "missing";
export interface InputIssue { issue_hash: string; [key: string]: unknown }
export interface RenderEvidence {
  presentation_plan?: PresentationPlan | null;
  kind: "candidate";
  status: "rendered" | "verified";
  page_count: number;
  pages: { page: number; sha256: string }[];
}
export interface Artifact { id: string; family?: OutputFamily; version: number; sha256: string; approved?: boolean; draft?: boolean; delivered?: boolean; delivery_decision?: DeliveryDecision; render_evidence?: RenderEvidence }
export interface ReportRevision { id: string; family: Exclude<OutputFamily, "presentation">; version: number; sha256: string; input_hash: string; blueprint_hash: string; current: boolean; approved: boolean; created_at: string }
export interface HistoryEvent { event: string; id: string; family?: OutputFamily; kind?: string; version?: number; sha256?: string; parent_sha256?: string; reason?: string; source_refs?: string[]; actor?: { type: string; id: string | number | null; name: string } }
export interface TaskHistory { task_id: string; task_version: number; history_immutable: boolean; tamper_claim: string; timeline: HistoryEvent[] }
export interface ContentChecks {
  facts: boolean;
  quantities: boolean;
  terms: boolean;
  sources: boolean;
  completeness: boolean;
  conditions: boolean;
}
export interface ArtifactVerification {
  expected_version: number;
  sha256: string;
  pages: { page: number; sha256: string; passed: boolean; comment: string }[];
  content_checks: ContentChecks;
  comment: string;
}
export interface TaskSummary { id: string; title: string; state: string; stage: string; version: number; created_at?: string; updated_at?: string; owner_name?: string; reviewer_name?: string | null; pending_action?: string; error_code?: string; is_pinned?: boolean; can_manage?: boolean }
export type ProductWorkflowPhase = 'documents' | 'equipment' | 'knowledge' | 'web_search' | 'blueprint' | 'review' | 'outputs' | 'writing_technical' | 'writing_feasibility' | 'review_technical' | 'review_feasibility' | 'diagrams_technical' | 'diagrams_feasibility' | 'render_technical' | 'render_feasibility' | 'presentation';
export interface ProductWorkflowProgress {
  started_at?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'waiting' | 'skipped';
  updated_at?: string;
  source_count?: number;
  item_count?: number;
  issue_count?: number;
  detail?: string;
  completed_count?: number;
  total_count?: number;
}
export interface ProductKnowledgeStatus {
  evidence_ready?: boolean;
  ragflow_source_count?: number;
  web_source_count?: number;
  web_search?: { status: 'skipped' | 'running' | 'completed' | 'blocked'; source_count: number; queries: string[]; missing_domains: string[]; detail: string; provider?: 'tavily' | 'brave'; code?: string; fact_scope?: 'PUBLIC_REFERENCE' };
  mode: 'source_only_preview' | 'ragflow_required';
  required: boolean;
  status: 'source_only_preview' | 'waiting_for_ragflow' | 'ready';
  ragflow_used: boolean;
  source_count: number;
  detail: string;
}
export interface DocumentTask extends TaskSummary {
  presentation_plan?: PresentationPlan | null;
  retry_after?: string | null;
  retry_budget?: { used: number; limit: number; remaining: number };
  quality_warnings?: ({ family: OutputFamily } & OutputQualityWarnings)[];
  generation_steps?: { key: string; status: string; attempts: number; error_code: string; retry_after?: string | null }[];
  intake_mode?: 'manual' | 'equipment_background';
  analysis_progress?: Partial<Record<ProductWorkflowPhase, ProductWorkflowProgress>>;
  activity?: { phase: string; status: ProductWorkflowProgress['status']; detail?: string; updated_at: string }[];
  /** New orchestration payloads are optional so older deployments remain readable. */
  checkpoint?: { analysis_progress?: Partial<Record<ProductWorkflowPhase, ProductWorkflowProgress>>; current_node?: string; detail?: string };
  workflow?: { current_node?: string; status?: string; detail?: string };
  knowledge?: ProductKnowledgeStatus;
  blueprint_approved?: boolean;
  blueprint_review: { revision_count: number; revision_limit: number; revisions_remaining: number };
  blueprint_knowledge?: ProductKnowledgeStatus;
  output_profile?: 'formal';
  output_families?: OutputFamily[];
  output_targets?: { 'technical-solution': number; feasibility: number };
  output_generation?: Partial<Record<'technical-solution' | 'feasibility', { target_characters: number; actual_characters: number; minimum_characters: number; status: 'target_met' | 'below_target'; updated_at: string }>>;
  input_version: number;
  blueprint_version: number;
  input: TaskInput | null;
  blueprint: (Artifact & { payload: BlueprintPayload; input_hash?: string }) | null;
  chapters: { id: string; family: Exclude<OutputFamily, "presentation">; version?: number; input_hash?: string; blueprint_hash?: string; payload: ChapterPayload }[];
  reports: ReportRevision[];
  artifacts: Artifact[];
  sources: { id: string; original_name: string; purpose?: '' | 'equipment' | 'background'; size?: number; media_type?: string; sha256?: string; created_at?: string; warnings?: SourceWarning[]; parsed?: ExtractionSummary }[];
  approvals: unknown[];
  issues: unknown[];
  error_code: string;
  pending_action?: string;
  actions: string[] | Record<string, boolean>;
  blockers: Record<string, { code: string; detail: string }>;
  reviewer_id: string | number | null;
  owner_id: string | number;
  input_issues: InputIssue[];
  impact: Record<string, unknown>;
}
export interface CreateTask { title: string; input: TaskInput; reviewer_id?: number; intake_mode?: 'equipment_background'; output_families?: OutputFamily[] }
export interface ConversationTaskResult {
  task: DocumentTask;
  intent: {
    mode: "deterministic_fallback";
    model_called: false;
    requested_outputs: { type: "technical_solution" | "feasibility" | "presentation"; status: string; code: string }[];
    detected_paths: string[];
  };
  blockers: Record<string, string>;
}
export interface ProductOverview {
  as_of: string;
  scope: "authorized_projects";
  metrics: { all?: number; active: number; completed?: number; review: number; generation: number; completed_month: number };
  projects: TaskSummary[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  recent_projects: TaskSummary[];
  todos: TaskSummary[];
  recent_outputs: { id: string; task_id: string; title: string; family: OutputFamily; version: number; created_at: string; current: boolean; delivered?: boolean; review_status: OutputReviewStatus }[];
  reviewers: { id: number; name: string }[];
  capabilities: { model_generation: boolean; retrieval: boolean; formal_release: boolean; office_preview: boolean; upload_extensions: string[]; upload_max_bytes: number; local_ocr?: boolean; parser_ready?: boolean };
  templates: { id: string; name: string; version: string; families: OutputFamily[]; approved: boolean; description: string }[];
}
export const getProductOverview = (query: string, signal: AbortSignal) => apiRequest<ProductOverview>(`/api/product/workspace/${query ? `?${query}` : ""}`, { signal });
export interface ProductOutputHistory {
  outputs: { id: string; task_id: string; title: string; family: OutputFamily; version: number; created_at: string; current: boolean; delivered?: boolean; review_status: OutputReviewStatus; download_url: string }[];
  pagination: { page: number; page_size: number; total: number; pages: number };
}
export const getProductOutputHistory = (query: string, signal: AbortSignal) => apiRequest<ProductOutputHistory>(`/api/product/workspace/outputs/${query ? `?${query}` : ''}`, { signal });
export const sourceDownload = (id: string) => `/api/product/sources/${encodeURIComponent(id)}/download/`;
const root = "/api/product/tasks/";
const pathFor = (id: string) => `${root}${encodeURIComponent(id)}/`;

export async function listTasks(signal: AbortSignal): Promise<{ tasks: TaskSummary[] }> {
  const result = await apiRequest<TaskSummary[] | { tasks: TaskSummary[] }>(root, { signal });
  return Array.isArray(result) ? { tasks: result } : result;
}
export const getTask = (id: string, signal: AbortSignal) => apiRequest<DocumentTask>(pathFor(id), { signal });
export const pinTask = (id: string, expected_version: number, pinned: boolean) => apiRequest<unknown>(`${pathFor(id)}pin/`, {
  method: "POST", body: JSON.stringify({ expected_version, pinned }),
});
export const deleteTask = (id: string, expected_version: number) => apiRequest<unknown>(pathFor(id), {
  method: "DELETE", body: JSON.stringify({ expected_version }),
});
export const createTask = (body: CreateTask, key: string, signal: AbortSignal) => apiRequest<DocumentTask>(root, {
  method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": key }, signal,
});
export const createConversationTask = (body: { message: string }, key: string, signal: AbortSignal) => apiRequest<ConversationTaskResult>("/api/product/conversations/", {
  method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": key }, signal,
});
export const continueConversation = (id: string, body: { expected_version: number; message: string }, signal: AbortSignal) => apiRequest<ConversationTaskResult>(`${pathFor(id)}conversation/`, {
  method: "POST", body: JSON.stringify(body), signal,
});
export const updateTask = (id: string, endpoint: string, body: object, signal: AbortSignal) => apiRequest<unknown>(`${pathFor(id)}${endpoint}`, {
  method: endpoint === "" || endpoint === "blueprint/" ? "PATCH" : "POST", body: JSON.stringify(body), signal,
});
export const artifactDownload = (id: string) => `/api/product/artifacts/${encodeURIComponent(id)}/download/`;
export const artifactHistoryDownload = (id: string) => `${artifactDownload(id)}?history=1`;
export const draftDownload = (id: string) => `/api/product/outputs/${encodeURIComponent(id)}/download/`;
export const draftHistoryDownload = (id: string) => `${draftDownload(id)}?history=1`;
export const draftPreview = (id: string, page = 1) => `/api/product/outputs/${encodeURIComponent(id)}/preview/?page=${encodeURIComponent(String(page))}`;
export const savedDraftDownload = (task: Pick<DocumentTask, 'id' | 'input_version' | 'blueprint_version'>, family: Exclude<OutputFamily, 'presentation'>) => `${pathFor(task.id)}saved-draft/download/?${new URLSearchParams({ family, input_version: String(task.input_version), blueprint_version: String(task.blueprint_version) })}`;
export const getDraftOutputs = (id: string, signal: AbortSignal) => apiRequest<{ task_version: number; outputs: DraftOutput[] }>(`${pathFor(id)}outputs/`, { signal });
export const getTaskHistory = (id: string, signal: AbortSignal) => apiRequest<TaskHistory>(`${pathFor(id)}history/`, { signal });
export const artifactPreview = (id: string, page: number) => `/api/product/artifacts/${encodeURIComponent(id)}/preview/?page=${encodeURIComponent(String(page))}`;
export const verifyArtifact = (id: string, body: ArtifactVerification, signal: AbortSignal) => apiRequest<unknown>(`/api/product/artifacts/${encodeURIComponent(id)}/verification/`, {
  method: "POST", body: JSON.stringify(body), signal,
});
export async function confirmSourceUpload(task: DocumentTask, file: File, previousSources: DocumentTask['sources'], purpose?: 'equipment' | 'background'): Promise<boolean> {
  if (!globalThis.crypto?.subtle) return false;
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))).map(byte => byte.toString(16).padStart(2, '0')).join('');
  return task.sources.some(source => !previousSources.some(previous => previous.id === source.id) && source.original_name === file.name && source.size === file.size && source.sha256 === hash && (source.purpose || '') === (purpose || ''));
}

export async function uploadSource(id: string, file: File, version: number, signal: AbortSignal, purpose?: 'equipment' | 'background', previousSources?: DocumentTask['sources']): Promise<DocumentTask> {
  const body = new FormData();
  body.append("file", file);
  body.append("expected_version", String(version));
  if (purpose) body.append('purpose', purpose);
  try {
    const result = await apiRequest<{ source_id: string; task: DocumentTask }>(`${pathFor(id)}sources/`, { method: "POST", body, signal });
    return result.task;
  } catch (reason) {
    if (signal.aborted || !previousSources || (reason instanceof ApiError && reason.status < 500 && reason.status !== 409)) throw reason;
    // An upload can commit before its HTTP response is lost. Accept only a new,
    // exact source snapshot; never repeat the write while reconciling its result.
    try {
      const fresh = await getTask(id, signal);
      if (await confirmSourceUpload(fresh, file, previousSources, purpose) && !signal.aborted) return fresh;
    } catch (reconcileError) {
      if (reconcileError instanceof ApiError && [401, 403, 404].includes(reconcileError.status)) throw reconcileError;
      // Keep the original failure if the result cannot be confirmed.
    }
    throw reason;
  }
}
