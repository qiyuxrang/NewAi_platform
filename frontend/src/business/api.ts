import { getAccessToken } from '../lib/api.ts'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function businessPath(path: string): string {
  const departmentPath = /^\/api\/(product|hr|engineering|business)\//.test(path)
  const modelPath = /^\/api\/models\/(?:routes\/[^/?]+\/options\/|departments\/[^/?]+\/ask\/)(?:\?.*)?$/.test(path)
  if ((!departmentPath && !modelPath) || path.includes('..')) {
    throw new Error('业务接口地址无效。')
  }
  return path.replace(/^\/api\//, '/api/enterprise/business/')
}

async function authenticatedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getAccessToken()
  if (!token) throw new ApiError(401, '登录已失效，请重新登录。')
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(businessPath(path), { ...options, headers, credentials: 'omit' })
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: unknown; code?: unknown } | null
    throw new ApiError(response.status, typeof detail?.detail === 'string' ? detail.detail : `业务请求失败 (${response.status})`, typeof detail?.code === 'string' ? detail.code : undefined)
  }
  return response
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  // Browser sets the multipart boundary; preserve the original upload and version fields.
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await authenticatedFetch(path, { ...options, headers })
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function businessFileUrl(path: string, signal: AbortSignal): Promise<string> {
  const response = await authenticatedFetch(path, { signal })
  return URL.createObjectURL(await response.blob())
}

export async function businessFilePreview(path: string, signal: AbortSignal): Promise<{ content: string; contentType: string }> {
  const response = await authenticatedFetch(path, { signal })
  const contentType = (response.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase()
  if (!['text/html', 'text/plain', 'application/json'].includes(contentType)) throw new ApiError(502, '全文预览格式不可用，请下载原文件查阅。', 'invalid_response')
  const content = await response.text()
  if (signal.aborted) throw new DOMException('Preview cancelled', 'AbortError')
  return { content, contentType }
}

export async function downloadBusinessFile(path: string, fallbackName: string): Promise<void> {
  const response = await authenticatedFetch(path)
  const disposition = response.headers.get('Content-Disposition') || ''
  let filename = disposition.match(/filename="([^"]+)"/)?.[1] || fallbackName
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try { filename = decodeURIComponent(encoded) } catch { /* Keep the ordinary filename. */ }
  }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename.replace(/[\\/]/g, '_')
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface AssistantActivity {
  id: string
  tool: 'knowledge_search' | 'knowledge_list' | 'knowledge_read' | 'web_search' | 'web_fetch' | 'calculate' | 'plan' | 'answer'
  status: 'running' | 'completed' | 'failed'
  summary: string
}

export async function apiEventStream<T>(path: string, body: unknown, signal: AbortSignal, onDelta: (delta: string, reset?: boolean) => void, onActivity?: (activity: AssistantActivity) => void): Promise<T> {
  const response = await authenticatedFetch(path, { method: "POST", body: JSON.stringify(body), signal, headers: { "Content-Type": "application/json", "Accept": "text/event-stream, application/json" } });
  const reader = response.body?.getReader();
  if (!reader || !response.headers.get("Content-Type")?.startsWith("text/event-stream")) {
    throw new ApiError(502, "回答流格式无效，请重试。", "invalid_response");
  }
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let pending = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      if (pending.length > 8 * 1024 * 1024) throw new ApiError(502, "回答流过长，请重试。", "invalid_response");
      let boundary = pending.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        if (!frame.startsWith("data: ")) throw new ApiError(502, "回答流格式无效，请重试。", "invalid_response");
        let event: unknown;
        try { event = JSON.parse(frame.slice(6)); } catch { throw new ApiError(502, "回答流格式无效，请重试。", "invalid_response"); }
        if (!event || typeof event !== "object") throw new ApiError(502, "回答流格式无效，请重试。", "invalid_response");
        const value = event as Record<string, unknown>;
        if (value.error && typeof value.error === "object") {
          const error = value.error as Record<string, unknown>;
          const code = typeof error.code === "string" ? error.code : "invalid_response";
          const status = code === "scope_revoked" || code === "forbidden" ? 403 : code === "conflict" ? 409 : 502;
          throw new ApiError(status, typeof error.detail === "string" ? error.detail : "回答未完成，请重试。", code);
        }
        if ('activity' in value) {
          if (value.activity && typeof value.activity === 'object' && !Array.isArray(value.activity)) {
            const activity = value.activity as Record<string, unknown>;
            if (typeof activity.id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(activity.id)
              && typeof activity.tool === 'string' && ['knowledge_search', 'knowledge_list', 'knowledge_read', 'web_search', 'web_fetch', 'calculate', 'plan', 'answer'].includes(activity.tool)
              && typeof activity.status === 'string' && ['running', 'completed', 'failed'].includes(activity.status)
              && typeof activity.summary === 'string' && activity.summary.length <= 500) {
              if (value.reset_answer === true && activity.tool === 'plan' && activity.status === 'completed') onDelta('', true);
              onActivity?.(activity as unknown as AssistantActivity);
            }
          }
        }
        else if (typeof value.delta === "string" && value.delta.length <= 4000) onDelta(value.delta);
        else if (value.done && typeof value.done === "object") return value.done as T;
        else throw new ApiError(502, "回答流格式无效，请重试。", "invalid_response");
        boundary = pending.indexOf("\n\n");
      }
    }
    throw new ApiError(502, "回答连接中断，请重试原问题。", "incomplete_stream");
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}


