import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { businessFileUrl, downloadBusinessFile } from './api'
import './business-surface.css'

export default function BusinessSurface({ children }: { children: ReactNode }) {
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [preview, setPreview] = useState('')
  useEffect(() => {
    function follow(event: MouseEvent) {
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!(anchor instanceof HTMLAnchorElement) || anchor.origin !== window.location.origin) return
      if (/^\/api\/(product|engineering)\//.test(anchor.pathname)) {
        event.preventDefault(); event.stopPropagation()
        if (anchor.pathname.includes('/preview/')) { setPreview(`${anchor.pathname}${anchor.search}`); return }
        setError(''); setDownloading(true)
        void downloadBusinessFile(`${anchor.pathname}${anchor.search}`, '业务文件').catch(cause => setError(cause instanceof Error ? cause.message : '下载失败')).finally(() => setDownloading(false))
      } else if (anchor.href !== window.location.href && !window.dispatchEvent(new Event('portal:navigation-guard', { cancelable: true }))) {
        event.preventDefault(); event.stopPropagation()
      }
    }
    document.addEventListener('click', follow, true)
    return () => document.removeEventListener('click', follow, true)
  }, [])
  return <div className="enterprise-business">
    {error && <p className="pd-feedback" role="alert">{error}</p>}
    {downloading && <p role="status">正在下载业务文件…</p>}
    {preview && <section className="center-panel" aria-label="业务文件预览"><button type="button" className="button secondary" onClick={() => setPreview('')}>关闭预览</button><BusinessImage key={preview} src={preview} alt="业务文件原件预览" /></section>}
    {children}
  </div>
}

export function BusinessImage({ src, alt }: { src: string; alt: string }) {
  const [loaded, setLoaded] = useState<{ src: string; url: string } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let url = ''
    void businessFileUrl(src, controller.signal).then(value => {
      if (controller.signal.aborted) { URL.revokeObjectURL(value); return }
      url = value; setLoaded({ src, url: value })
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '预览读取失败') })
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [src])
  if (error) return <p role="alert">原件预览不可用：{error}</p>
  return loaded?.src === src ? <img src={loaded.url} alt={alt} onError={() => setError('无法显示当前页，请下载原文件核对。')} /> : <p role="status">正在读取原件预览…</p>
}
