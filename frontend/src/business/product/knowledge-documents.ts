import { ApiError, apiRequest, businessFilePreview } from "../api";

export interface KnowledgeDataset { id: string; name: string; document_count: number }
export interface KnowledgeDocument { id: string; name: string; type: string; size: number; chunk_count: number; run: string; progress: number; updated_at: string }
export interface DocumentReference { dataset_id: string; document_id: string; title: string }
export interface DocumentPage { documents: KnowledgeDocument[]; total: number; page: number; page_size: number; has_more: boolean }
export interface PdfPage { page: number; width: number; height: number }
export interface PdfManifest { kind: "pdf"; page_count: number; pages: PdfPage[] }
export interface PdfPageBatch { kind: "pdf_pages"; page_count: number; pages: (PdfPage & { image: string })[]; next_page: number | null }
export interface KnowledgePreview { contentType: string; content?: string; pdf?: PdfManifest }

export function knowledgeDocumentPath(datasetId: string, documentId?: string) {
  const path = `/api/product/knowledge/datasets/${encodeURIComponent(datasetId)}/documents/`;
  return documentId ? `${path}${encodeURIComponent(documentId)}/` : path;
}

export function loadKnowledgeDocuments(datasetId: string, page: number, query: string, signal: AbortSignal) {
  const params = new URLSearchParams({ page: String(page), page_size: "20", q: query });
  return apiRequest<DocumentPage>(`${knowledgeDocumentPath(datasetId)}?${params}`, { signal });
}

export async function loadKnowledgePreview(document: DocumentReference, signal: AbortSignal) {
  const preview = await businessFilePreview(`${knowledgeDocumentPath(document.dataset_id, document.document_id)}preview/`, signal);
  if (signal.aborted) return null;
  if (preview.contentType === "application/json") {
    let value: unknown;
    try { value = JSON.parse(preview.content); } catch { throw invalidPdf(); }
    return { pdf: validatePdfManifest(value), contentType: preview.contentType };
  }
  return { content: knowledgePreviewHtml(preview.content, preview.contentType), contentType: preview.contentType };
}

function invalidPdf() { return new ApiError(502, "PDF 页数据不完整或格式无效，请重试或下载原文件查阅。", "invalid_response"); }
function validPdfPage(value: unknown): value is PdfPage {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const page = value as PdfPage;
  return Number.isInteger(page.page) && Number.isFinite(page.width) && page.width > 0 && Number.isFinite(page.height) && page.height > 0;
}
export function validatePdfManifest(value: unknown): PdfManifest {
  if (!value || typeof value !== "object") throw invalidPdf();
  const manifest = value as PdfManifest;
  if (manifest.kind !== "pdf" || !Number.isInteger(manifest.page_count) || manifest.page_count < 1 || manifest.page_count > 10000 ||
    !Array.isArray(manifest.pages) || manifest.pages.length !== manifest.page_count || manifest.pages.some((page, index) =>
      !validPdfPage(page) || page.page !== index + 1 || "image" in page)) throw invalidPdf();
  return manifest;
}
function validPageImage(value: unknown): value is string {
  if (typeof value !== "string" || !/^data:image\/jpeg;base64,\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(value)) return false;
  const payload = value.slice("data:image/jpeg;base64,".length);
  if (payload.length % 4) return false;
  try { return atob(payload.slice(-8)).endsWith("\xff\xd9"); } catch { return false; }
}
export function validatePdfPageBatch(value: unknown, manifest: PdfManifest, startPage: number): PdfPageBatch {
  if (!Number.isInteger(startPage) || startPage < 1 || startPage > manifest.page_count || !value || typeof value !== "object") throw invalidPdf();
  const batch = value as PdfPageBatch;
  const count = Math.min(3, manifest.page_count - startPage + 1);
  const next = startPage + count <= manifest.page_count ? startPage + count : null;
  if (batch.kind !== "pdf_pages" || batch.page_count !== manifest.page_count || batch.next_page !== next || !Array.isArray(batch.pages) || batch.pages.length !== count ||
    batch.pages.some((page, index) => {
      const expected = manifest.pages[startPage - 1 + index];
      return !validPdfPage(page) || page.page !== expected.page || page.width !== expected.width || page.height !== expected.height || !validPageImage((page as { image?: unknown }).image);
    })) throw invalidPdf();
  return batch;
}
export async function loadKnowledgePdfPages(document: DocumentReference, manifest: PdfManifest, startPage: number, signal: AbortSignal) {
  if (!Number.isInteger(startPage) || startPage < 1 || startPage > manifest.page_count) throw invalidPdf();
  const params = new URLSearchParams({ start_page: String(startPage), page_size: "3" });
  const result = await apiRequest<unknown>(`${knowledgeDocumentPath(document.dataset_id, document.document_id)}preview/pages/?${params}`, { signal });
  if (signal.aborted) throw new DOMException("Preview cancelled", "AbortError");
  return validatePdfPageBatch(result, manifest, startPage);
}

export function knowledgePreviewHtml(content: string, contentType: string) {
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">`;
  if (contentType === "text/html") {
    const head = /<head(?:\s[^>]*)?>/i;
    return head.test(content) ? content.replace(head, match => match + policy) : `<!doctype html><html><head>${policy}</head><body>${content}</body></html>`;
  }
  const escaped = content.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  return `<!doctype html><html><head><meta charset="utf-8">${policy}</head><body><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 monospace;padding:16px;margin:0">${escaped}</pre></body></html>`;
}
