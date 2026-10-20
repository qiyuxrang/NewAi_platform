import { apiRequest, isApiError } from '../api.ts';
export const root = '/api/hr/recruitment/';
export interface Requirement {
  created_by_id?: number | string;
  id: string; position_name: string; headcount: number | null; responsibilities: string;
  required_requirements: string; preferred_requirements: string; education_requirement: string;
  experience_requirement: string; skill_requirements: string[]; work_location: string; notes: string;
  salary?: string; benefits?: string; social_insurance?: string; original_text?: string; intake_source?: string;
  input_version: number; current_jd_id: string | null; official_jd_id: string | null; official_jd_stale?: boolean;
  missing_items: { field: string; reason: string }[]; updated_at: string; created_at?: string;
}
export interface Jd { id: string; request_id: string; version: number; input_version: number; body: string;
  state: string; channel: string; source?: string; requirements?: Record<string, unknown>; missing_items?: { field: string; reason: string }[]; stale: boolean; source_jd_id: string | null;
  model_selection?: { model_id: string; config_version: string; model_name?: string } | null }
export interface Resume { id: string; filename: string; processing_status: string; error_code: string; size: number }
export interface Batch { id: string; position_name: string; jd_version_id: string; jd_version: number;
  version: number; status: string; stale: boolean; total: number; completed: number; failed: number;
  progress: number; updated_at: string; created_at?: string; request_id?: string; jd_body?: string; pending?: number; prescreened?: number; status_counts?: Record<string, number>; artifacts?: Resume[];
  model_selection?: { model_id: string; config_version: string; model_name?: string } | null }
export interface Result extends Resume { score: number | null; unknown_count: number | null; hard_gap_count: number;
  verification_questions?: { requirement_id: string; question: string; reason: string }[];
  stale: boolean; rule_version: string | null; matrix: { id: string; text: string; verdict: string; evidence: { quote: string; locator: string }[] }[] }
export const get = <T,>(path: string, signal?: AbortSignal) => apiRequest<T>(root + path, { signal });
export const mutate = <T,>(path: string, body: object, method = 'POST', headers?: Record<string, string>) =>
  apiRequest<T>(root + path, { method, body: JSON.stringify(body), headers });
export const upload = (batch: Batch, files: File[]) => {
  const body = new FormData(); body.set('expected_version', String(batch.version));
  files.forEach(file => body.append('files', file));
  return apiRequest<{ batch: Batch }>(root + `batches/${batch.id}/resumes/`, { method: 'POST', body });
};
const statusLabels: Record<string, string> = { pending: '待上传/待开始', queued: '排队中', running: '处理中', completed: '已完成',
  partial_failed: '部分失败', failed: '处理失败', draft: '草稿', confirmed: '已确认' };
export const statusText = (status: string) => statusLabels[status] || status;
export const message = (error: unknown) => error instanceof Error ? error.message : '请求失败，请重试';
export const outcomeUnknown = (error: unknown) => !isApiError(error) || error.status >= 500;
export function actionMessage(error: unknown) {
  if (outcomeUnknown(error)) return `${message(error)} 提交结果尚未核实，请先刷新记录核对状态，避免重复提交。`;
  if (isApiError(error) && error.status === 409) return `${message(error)} 请先刷新记录，再根据最新状态操作。`;
  return message(error);
}
export function failureGuidance(code: string) {
  const reasons: Record<string, string> = {
    invalid_file: '文件损坏、加密或格式不受支持；请检查原件，修复后建立新批次。',
    invalid_encoding: 'TXT 编码无效；请另存为 UTF-8 后建立新批次。',
    text_unavailable: '未能提取正文；请核对原件，提供可识别的文件后建立新批次。',
    text_too_large: '正文超出模型或解析限制，未截断；请人工核对并整理原件后建立新批次。',
    vision_review_required: '页面识别不完整；请人工核对原件，不应据此判断候选人。',
    attempt_limit: '已达到处理尝试上限；请联系管理员核查，不再重试本项。',
    permission_changed: '业务授权已变化；请联系管理员核对授权。',
    forbidden: '模型或资料授权不足；请联系管理员核对授权。',
    stale_revision: '岗位要求已变化；请使用当前正式 JD 建立新批次。',
    extractor_unavailable: '解析运行时不可用或超时；请管理员恢复后重试失败项。',
    invalid_model_output: '模型返回内容未通过校验；可重试失败项，持续失败请联系管理员。',
    worker_error: '后台处理异常；可重试失败项，持续失败请联系管理员。',
  };
  return code ? reasons[code] || `处理失败（${code}）；请核对原件与授权，可重试失败项，持续失败请联系管理员。` : '—';
}

export const retentionNotice = '获准招聘资料长期归档，不自动到期；人工删除、撤权及旧规则下已失效的资料仍不可访问。';
export function screeningCounts(batch: Batch) {
  const counts = batch.status_counts ?? (batch.artifacts ? batch.artifacts.reduce<Record<string, number>>((all, item) => {
    all[item.processing_status] = (all[item.processing_status] || 0) + 1; return all;
  }, {}) : null);
  return { screened: batch.completed, pending: batch.pending ?? (counts ? (counts.queued || 0) + (counts.running || 0) : null),
    prescreened: batch.prescreened ?? (counts ? counts.pending || 0 : null) };
}
// Only the exact same browser File object is a proven duplicate here; content dedup belongs to the server.
export function selectResumeFiles(existing: File[], incoming: File[]) {
  const files = [...existing]; const rejected: string[] = []; let duplicates = 0;
  const seen = new Set(files);
  for (const file of incoming) {
    if (!/\.(txt|docx|pdf)$/i.test(file.name) || file.size === 0 || file.size > 2 * 1024 * 1024) { rejected.push(file.webkitRelativePath || file.name); continue; }
    if (seen.has(file)) { duplicates++; continue; }
    seen.add(file); files.push(file);
  }
  return { files, rejected, duplicates };
}
export async function uploadSequential(batch: Batch, files: File[], onChunk: (batch: Batch, sent: number) => void) {
  let current = batch;
  for (let offset = 0; offset < files.length; offset += 20) {
    const response = await upload(current, files.slice(offset, offset + 20));
    current = response.batch;
    onChunk(current, Math.min(offset + 20, files.length));
  }
  return current;
}

export interface IntakeResponse { request: Requirement; jd: Jd }
export const uploadJd = (file: File) => {
  const body = new FormData(); body.set('file', file);
  return apiRequest<IntakeResponse>(root + 'requests/upload-jd/', { method: 'POST', body });
};
export interface RecruitmentHistoryData {
  request: Requirement;
  messages: { id: string | number; role: string; content: string; created_at: string; input_version: number; jd_version_id: string | null }[];
  jd_versions: Jd[];
  batches: (Batch & { results: Result[] })[];
}
