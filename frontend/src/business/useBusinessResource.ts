import { useEffect, useState } from 'react'
import { ApiError, apiRequest } from './api'

/** Published records refresh while visible; failures retain the last verified view. */
export function useBusinessResource<T>(url: string | null) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{ url: string | null; data?: T; error?: string; updatedAt?: string; denied?: boolean }>({ url })
  useEffect(() => {
    if (!url) return
    const controller = new AbortController()
    let busy = false
    const load = async () => {
      if (busy || controller.signal.aborted) return
      busy = true
      try {
        const data = await apiRequest<T>(url, { signal: controller.signal })
        if (!controller.signal.aborted) setState({ url, data, updatedAt: new Date().toLocaleString('zh-CN') })
      } catch (cause) {
        if (!controller.signal.aborted) setState(previous => ({
          ...(previous.url === url && !(cause instanceof ApiError && [401, 403].includes(cause.status)) ? previous : {}),
          url, denied: cause instanceof ApiError && [401, 403].includes(cause.status),
          error: cause instanceof Error ? cause.message : '刷新失败，请重试',
        }))
      } finally { busy = false }
    }
    const visible = () => { if (!document.hidden && document.hasFocus()) void load() }
    void load()
    const timer = window.setInterval(visible, 15000)
    window.addEventListener('focus', visible)
    document.addEventListener('visibilitychange', visible)
    return () => {
      controller.abort(); window.clearInterval(timer)
      window.removeEventListener('focus', visible)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [url, attempt])
  return { ...(state.url === url ? state : { url }), reload: () => setAttempt(value => value + 1) }
}
