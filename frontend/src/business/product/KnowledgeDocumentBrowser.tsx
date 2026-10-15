import { useEffect, useState } from "react";
import { ArrowLeft, Download, FileText, Search, X } from "lucide-react";
import { ApiError, downloadBusinessFile } from "../api";
import { knowledgeDocumentPath, loadKnowledgeDocuments, loadKnowledgePreview } from "./knowledge-documents";
import type { DocumentPage, DocumentReference, KnowledgeDataset, KnowledgePreview } from "./knowledge-documents";
import KnowledgePdfReader from "./KnowledgePdfReader";

function requestError(reason: unknown, onAccessRevoked: () => void) {
  if (reason instanceof ApiError && [401, 403].includes(reason.status)) onAccessRevoked();
  return reason instanceof Error ? reason.message : "读取失败，请重试。";
}

function useDocumentList(datasetId: string, page: number, query: string, retry: number, onAccessRevoked: () => void) {
  const key = JSON.stringify([datasetId, page, query, retry]);
  const [loaded, setLoaded] = useState<{ key: string; result?: DocumentPage; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void loadKnowledgeDocuments(datasetId, page, query, controller.signal).then(result => {
      if (!controller.signal.aborted) setLoaded({ key, result });
    }).catch(reason => {
      if (!controller.signal.aborted) setLoaded({ key, error: requestError(reason, onAccessRevoked) });
    });
    return () => controller.abort();
  }, [datasetId, page, query, key, onAccessRevoked]);
  return loaded?.key === key ? loaded : null;
}

function useDocumentPreview(document: DocumentReference, retry: number, onAccessRevoked: () => void) {
  const key = JSON.stringify([document.dataset_id, document.document_id, document.title, retry]);
  const [loaded, setLoaded] = useState<({ key: string; error?: string } & Partial<KnowledgePreview>) | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void loadKnowledgePreview({ dataset_id: document.dataset_id, document_id: document.document_id, title: document.title }, controller.signal).then(preview => {
      if (preview && !controller.signal.aborted) setLoaded({ key, ...preview });
    }).catch(reason => {
      if (!controller.signal.aborted) setLoaded({ key, error: requestError(reason, onAccessRevoked) });
    });
    return () => controller.abort();
  }, [document.dataset_id, document.document_id, document.title, key, onAccessRevoked]);
  return loaded?.key === key ? loaded : null;
}

export function KnowledgeDocumentBrowser({ dataset, selected, onOpen, onBack, onAccessRevoked }: {
  dataset: KnowledgeDataset; selected: DocumentReference | null; onOpen: (document: DocumentReference) => void;
  onBack: () => void; onAccessRevoked: () => void;
}) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const loaded = useDocumentList(dataset.id, page, query, retry, onAccessRevoked);
  const result = loaded?.result;
  return <section className="pk-document-browser" aria-label={`${dataset.name}文档列表`} aria-busy={!loaded}>
    <header className="pk-document-heading"><button type="button" className="text-button pk-back" onClick={onBack}><ArrowLeft size={16}/>返回问答</button><h1>{dataset.name}</h1><p>点击文档，在右侧查阅完整原文。</p></header>
    <form className="pk-document-search" role="search" onSubmit={event => { event.preventDefault(); setQuery(input.trim()); setPage(1); }}>
      <label className="pk-sr-only" htmlFor="knowledge-document-search">搜索文档名称</label><input id="knowledge-document-search" type="search" placeholder="搜索文档名称" value={input} onChange={event => setInput(event.target.value)}/><button className="button secondary"><Search size={16}/>搜索</button>
    </form>
    <div className="pk-document-list" aria-label="文档">
      {!loaded && <p className="pk-pending" role="status"><span className="pd-spinner"/>正在读取文档列表…</p>}
      {loaded?.error && <div className="pk-document-error" role="alert"><p>{loaded.error}</p><button type="button" className="button secondary" onClick={() => setRetry(value => value + 1)}>重试文档列表</button></div>}
      {result && !result.documents.length && <div className="pd-empty"><FileText size={28}/><h3>{query ? "没有匹配的文档" : "该知识库暂无文档"}</h3><p>{query ? "请换个关键词重新搜索。" : "资料入库后会显示在这里。"}</p></div>}
      {result && !!result.documents.length && <ul>{result.documents.map(document => {
        const active = selected?.dataset_id === dataset.id && selected.document_id === document.id;
        return <li key={document.id}><button type="button" className={`pk-document-row${active ? " selected" : ""}`} aria-pressed={active} onClick={() => onOpen({ dataset_id: dataset.id, document_id: document.id, title: document.name })}>
          <span className="pk-document-file-icon"><FileText size={21}/></span><span className="pk-document-title"><strong>{document.name || "未命名文档"}</strong><small>{document.type?.toUpperCase() || "文档"}{document.size > 0 ? ` · ${document.size < 1048576 ? `${Math.ceil(document.size / 1024)} KB` : `${(document.size / 1048576).toFixed(1)} MB`}` : ""}{document.updated_at ? ` · ${document.updated_at}` : ""}</small></span><span className="pk-document-open">查阅</span>
        </button></li>;
      })}</ul>}
    </div>
    {result && <footer className="pk-document-pagination"><span>共 {result.total} 篇 · 第 {result.page} 页</span><div><button type="button" className="button secondary" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><button type="button" className="button secondary" disabled={!result.has_more} onClick={() => setPage(value => value + 1)}>下一页</button></div></footer>}
  </section>;
}

export function KnowledgeDocumentPreview({ document, onClose, onAccessRevoked }: {
  document: DocumentReference; onClose: () => void; onAccessRevoked: () => void;
}) {
  const [retry, setRetry] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const loaded = useDocumentPreview(document, retry, onAccessRevoked);
  async function download() {
    setDownloading(true); setDownloadError("");
    try { await downloadBusinessFile(`${knowledgeDocumentPath(document.dataset_id, document.document_id)}download/`, document.title); }
    catch (reason) { setDownloadError(requestError(reason, onAccessRevoked)); }
    finally { setDownloading(false); }
  }
  return <aside className="pk-document-preview" aria-label="完整文档预览" aria-busy={!loaded}>
    <header className="pk-preview-heading"><div><small>完整原文</small><h2 title={document.title}>{document.title || "未命名文档"}</h2></div><button type="button" className="pk-preview-close" aria-label="关闭文档预览" title="关闭预览" onClick={onClose}><X size={18}/></button></header>
    <div className="pk-preview-toolbar"><span>滚动查看全文</span><button type="button" className="button secondary" disabled={downloading} onClick={() => void download()}><Download size={15}/>{downloading ? "下载中…" : "下载原文件"}</button></div>
    {loaded?.contentType === "text/html" && <p className="pk-preview-format-note">全文阅读视图，原始排版请下载原文件。</p>}
    {downloadError && <p className="pk-document-error" role="alert">{downloadError}</p>}
    {!loaded && <p className="pk-pending" role="status"><span className="pd-spinner"/>正在读取完整原文…</p>}
    {loaded?.error && <div className="pk-document-error" role="alert"><p>全文预览不可用：{loaded.error}</p><p>可下载原文件查阅。</p><button type="button" className="button secondary" onClick={() => setRetry(value => value + 1)}>重试全文预览</button></div>}
    {loaded?.content && <iframe className="pk-document-frame" srcDoc={loaded.content} title={`${document.title || "文档"}完整原文`} sandbox="" referrerPolicy="no-referrer"/>}
    {loaded?.pdf && <KnowledgePdfReader document={document} manifest={loaded.pdf} onAccessRevoked={onAccessRevoked}/>}
  </aside>;
}
