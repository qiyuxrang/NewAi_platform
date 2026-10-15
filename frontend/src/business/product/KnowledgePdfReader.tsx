import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { loadKnowledgePdfPages } from "./knowledge-documents";
import type { DocumentReference, PdfManifest, PdfPageBatch } from "./knowledge-documents";

interface BatchState { loading?: boolean; pages?: PdfPageBatch["pages"]; error?: string }

export default function KnowledgePdfReader({ document, manifest, onAccessRevoked }: {
  document: DocumentReference; manifest: PdfManifest; onAccessRevoked: () => void;
}) {
  const reader = useRef<HTMLDivElement>(null);
  const retryBatch = useRef<(index: number) => void>(() => {});
  const imageFailure = useRef<(index: number) => void>(() => {});
  const [batches, setBatches] = useState<Record<number, BatchState>>({});
  const [pageInput, setPageInput] = useState("1");
  const [jumpError, setJumpError] = useState("");
  const groups = Array.from({ length: Math.ceil(manifest.page_count / 3) }, (_, index) => manifest.pages.slice(index * 3, index * 3 + 3));

  useEffect(() => {
    const root = reader.current;
    if (!root) return;
    let stopped = false;
    const near = new Set<number>();
    const elements = Array.from(root.querySelectorAll<HTMLElement>("[data-pdf-batch]"));
    const live = new Map<number, { controller: AbortController; state: BatchState }>();
    const publish = () => { if (!stopped) setBatches(Object.fromEntries(Array.from(live, ([index, item]) => [index, item.state]))); };
    function reconcile() {
      if (stopped) return;
      // ponytail: keep four near batches (12 images); widen only if measured scroll latency warrants it.
      const wanted = new Set(Array.from(near).sort((a, b) => Math.abs(elements[a].offsetTop - root!.scrollTop) - Math.abs(elements[b].offsetTop - root!.scrollTop)).slice(0, 4));
      let changed = false;
      for (const [index, item] of live) if (!wanted.has(index)) { item.controller.abort(); live.delete(index); changed = true; }
      for (const index of wanted) {
        if (live.has(index)) continue;
        const item = { controller: new AbortController(), state: { loading: true } as BatchState };
        live.set(index, item); changed = true;
        void loadKnowledgePdfPages({ dataset_id: document.dataset_id, document_id: document.document_id, title: document.title }, manifest, index * 3 + 1, item.controller.signal).then(result => {
          if (stopped || item.controller.signal.aborted || live.get(index) !== item) return;
          item.state = { pages: result.pages }; publish();
        }).catch(reason => {
          if (stopped || item.controller.signal.aborted || live.get(index) !== item) return;
          if (reason instanceof ApiError && [401, 403].includes(reason.status)) {
            for (const request of live.values()) request.controller.abort();
            live.clear(); near.clear(); publish(); stopped = true; onAccessRevoked(); return;
          }
          item.state = { error: reason instanceof Error ? `${reason.message}${reason instanceof ApiError && reason.code ? `（${reason.code}）` : ""}` : "页面读取失败，请重试。" };
          publish();
        });
      }
      if (changed) publish();
    }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const index = Number((entry.target as HTMLElement).dataset.pdfBatch);
        if (entry.isIntersecting) near.add(index); else near.delete(index);
      }
      reconcile();
    }, { root, rootMargin: "600px 0px" });
    elements.forEach(element => observer.observe(element));
    root.addEventListener("scroll", reconcile, { passive: true });
    retryBatch.current = index => { live.get(index)?.controller.abort(); live.delete(index); reconcile(); };
    imageFailure.current = index => {
      const item = live.get(index);
      if (item) { item.state = { error: "页面图像无法显示，请重试或下载原文件查阅。" }; publish(); }
    };
    return () => {
      stopped = true; observer.disconnect(); root.removeEventListener("scroll", reconcile);
      for (const item of live.values()) item.controller.abort();
      live.clear(); near.clear(); retryBatch.current = () => {}; imageFailure.current = () => {};
    };
  }, [document.dataset_id, document.document_id, document.title, manifest, onAccessRevoked]);

  function jump() {
    const page = Number(pageInput);
    if (!Number.isInteger(page) || page < 1 || page > manifest.page_count) { setJumpError(`请输入 1 至 ${manifest.page_count} 的页码。`); return; }
    const root = reader.current;
    const target = root?.querySelector<HTMLElement>(`[data-pdf-page="${page}"]`);
    if (!root || !target) return;
    setJumpError("");
    root.scrollTop += target.getBoundingClientRect().top - root.getBoundingClientRect().top - 12;
    root.focus({ preventScroll: true });
  }
  return <section className="pk-pdf-reader" aria-label={`${document.title} PDF 全文`}>
    <form className="pk-pdf-page-controls" onSubmit={event => { event.preventDefault(); jump(); }}>
      <label htmlFor="knowledge-pdf-page">页码</label><input id="knowledge-pdf-page" type="number" min={1} max={manifest.page_count} step={1} required value={pageInput} onChange={event => setPageInput(event.target.value)} aria-invalid={!!jumpError}/><span>共 {manifest.page_count} 页</span><button className="button secondary">跳转</button>
    </form>
    {jumpError && <p className="pk-document-error" role="alert">{jumpError}</p>}
    <div ref={reader} className="pk-pdf-scroll" tabIndex={0} aria-label="PDF 连续页阅读区">
      {groups.map((pages, index) => {
        const state = batches[index];
        return <div key={index} data-pdf-batch={index} className="pk-pdf-batch">{pages.map((page, offset) => <figure key={page.page} data-pdf-page={page.page} className="pk-pdf-page">
          <div className="pk-pdf-page-canvas" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
            {state?.pages ? <img src={state.pages[offset].image} alt={`${document.title} · 第 ${page.page} 页`} draggable={false} onError={() => imageFailure.current(index)}/> : <div className="pk-pdf-placeholder">
              {state?.error ? <div role="alert"><p>第 {pages[0].page}–{pages[pages.length - 1].page} 页读取失败：{state.error}</p><button type="button" className="button secondary" onClick={() => retryBatch.current(index)}>重试本批页面</button></div> : <span>{state?.loading ? "正在读取页面…" : "滚动到此页即可查阅"}</span>}
            </div>}
          </div><figcaption>第 {page.page} / {manifest.page_count} 页</figcaption>
        </figure>)}</div>;
      })}
    </div>
  </section>;
}
