import assert from 'node:assert/strict';
import { after, afterEach, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({ root, configFile: false, appType: 'custom',
  server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, include: [] }, esbuild: { jsx: 'automatic' } });
const { loadKnowledgeDocuments, loadKnowledgePreview, loadKnowledgePdfPages, validatePdfManifest, validatePdfPageBatch, knowledgePreviewHtml } = await server.ssrLoadModule('/src/business/product/knowledge-documents.ts');
const { KnowledgeDocumentBrowser, KnowledgeDocumentPreview } = await server.ssrLoadModule('/src/business/product/KnowledgeDocumentBrowser.tsx');
const { ApiError, businessFilePreview } = await server.ssrLoadModule('/src/business/api.ts');
const { clampPanelWidth, dragPanelWidth, keyPanelWidth } = await server.ssrLoadModule('/src/business/product/workbench-resize.ts');
const { default: WorkbenchSeparator } = await server.ssrLoadModule('/src/business/product/WorkbenchSeparator.tsx');
const { default: ProductWorkspace } = await server.ssrLoadModule('/src/business/product/ProductWorkspace.tsx');
const { default: KnowledgePdfReader } = await server.ssrLoadModule('/src/business/product/KnowledgePdfReader.tsx');
const { default: MarkdownContent } = await server.ssrLoadModule('/src/components/MarkdownContent.tsx');
const originalFetch = globalThis.fetch;
const originalStorage = globalThis.localStorage;
globalThis.localStorage = { getItem: () => 'isolated-test-token' };
after(() => { globalThis.fetch = originalFetch; globalThis.localStorage = originalStorage; return server.close(); });
afterEach(() => { globalThis.fetch = originalFetch; });

test('assistant Markdown shows public links without enabling OpenClaw file access or remote images', () => {
  const html = renderToStaticMarkup(React.createElement(MarkdownContent, { fileLinks: false,
    content: '**结论** [网页](https://example.com/reference) [文件](workspace/private.pdf) [无效](javascript:alert(1)) ![图片](https://example.com/tracker.png)' }));
  assert.match(html, /<strong[^>]*>结论<\/strong>/);
  assert.match(html, /href="https:\/\/example.com\/reference" target="_blank" rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /href="(?:workspace|javascript)|filemanager|<img/);
});

const pdfManifest = count => ({ kind: 'pdf', page_count: count, pages: Array.from({ length: count }, (_, index) => ({ page: index + 1, width: 612, height: 792 })) });
const jpeg = extraBytes => 'data:image/jpeg;base64,' + Buffer.from([255, 216, 255, ...Array(extraBytes).fill(0), 255, 217]).toString('base64');
const pdfBatch = (manifest, start, image = jpeg(1)) => ({ kind: 'pdf_pages', page_count: manifest.page_count,
  pages: manifest.pages.slice(start - 1, start + 2).map(page => ({ ...page, image })),
  next_page: start + 3 <= manifest.page_count ? start + 3 : null });

test('document search sends authenticated, encoded dataset and server pagination without retrieving chunks', async () => {
  const controller = new AbortController();
  const result = { documents: [{ id: 'doc-1', name: '完整规范.docx' }], total: 23, page: 2, page_size: 20, has_more: false };
  globalThis.fetch = async (path, options) => {
    const url = new URL(path, 'https://local.invalid');
    assert.equal(url.pathname, '/api/enterprise/business/product/knowledge/datasets/library%2Fa/documents/');
    assert.equal(url.searchParams.get('page'), '2');
    assert.equal(url.searchParams.get('page_size'), '20');
    assert.equal(url.searchParams.get('q'), '设备 & 验收');
    assert.equal(options.signal, controller.signal);
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers.get('Authorization'), 'Bearer isolated-test-token');
    return Response.json(result);
  };
  assert.deepEqual(await loadKnowledgeDocuments('library/a', 2, '设备 & 验收', controller.signal), result);
});

test('preview decodes full HTML and plain text directly, preserves first and last paragraphs and never creates blob URLs', async () => {
  const originalCreate = URL.createObjectURL;
  URL.createObjectURL = () => assert.fail('text previews must not depend on blob navigation');
  try { for (const contentType of ['text/html; charset=utf-8', 'text/plain; charset=utf-8']) {
    const body = contentType.startsWith('text/html') ? '<!doctype html><html><head><style>p{line-height:1.8}</style></head><body><p>正文第一段</p>' + '<p>完整正文</p>'.repeat(120) + '<p>原文件最后一段</p></body></html>' : '正文第一段\n' + '完整正文\n'.repeat(120) + '原文件最后一段';
    globalThis.fetch = async path => {
      assert.equal(path, '/api/enterprise/business/product/knowledge/datasets/library/documents/doc%2Fa/preview/');
      return new Response(body, { headers: { 'Content-Type': contentType } });
    };
    const raw = await businessFilePreview('/api/product/knowledge/datasets/library/documents/doc%2Fa/preview/', new AbortController().signal);
    assert.equal(raw.content, body);
    assert.equal(raw.contentType, contentType.split(';')[0]);
    const preview = await loadKnowledgePreview({ dataset_id: 'library', document_id: 'doc/a', title: '完整文档' }, new AbortController().signal);
    assert.equal(preview.contentType, contentType.split(';')[0]);
    assert.match(preview.content, /正文第一段/);
    assert.match(preview.content, /原文件最后一段/);
    assert.equal((preview.content.match(/完整正文/g) || []).length, 120);
  } } finally { URL.createObjectURL = originalCreate; }
});

test('closing during slow text decoding cancels the preview without returning stale content', async () => {
  const controller = new AbortController();
  let release;
  let textStarted;
  const started = new Promise(resolve => { textStarted = resolve; });
  globalThis.fetch = async () => ({ ok: true, headers: new Headers({ 'Content-Type': 'text/plain' }), text: async () => {
    textStarted();
    return new Promise(resolve => { release = resolve; });
  } });
  const originalCreate = URL.createObjectURL;
  let created = 0;
  URL.createObjectURL = blob => { created++; return originalCreate(blob); };
  try {
    const pending = loadKnowledgePreview({ dataset_id: 'library', document_id: 'doc', title: 'slow' }, controller.signal);
    await started;
    controller.abort();
    release('complete text');
    await assert.rejects(pending, { name: 'AbortError' });
    assert.equal(created, 0);
  } finally { URL.createObjectURL = originalCreate; }
});

test('430 and 445 page manifests retain every consecutive page and render only sized placeholders before observation', async () => {
  for (const count of [430, 445]) {
    const manifest = pdfManifest(count);
    globalThis.fetch = async () => Response.json(manifest);
    const preview = await loadKnowledgePreview({ dataset_id: 'library', document_id: 'long-pdf', title: '长文件.pdf' }, new AbortController().signal);
    assert.deepEqual(preview.pdf, manifest);
    assert.equal(preview.content, undefined);
    const html = renderToStaticMarkup(React.createElement(KnowledgePdfReader, { document: { dataset_id: 'library', document_id: 'long-pdf', title: '长文件.pdf' }, manifest, onAccessRevoked: () => {} }));
    assert.match(html, new RegExp(`共 ${count} 页`));
    assert.match(html, /data-pdf-page="1"/);
    assert.match(html, new RegExp(`data-pdf-page="${count}"`));
    assert.equal((html.match(/data-pdf-page=/g) || []).length, count);
    assert.match(html, /aspect-ratio:612 \/ 792/);
    assert.doesNotMatch(html, /<img|<iframe|data:image/);
  }
  for (const invalid of [ { ...pdfManifest(445), page_count: 444 }, { ...pdfManifest(430), pages: [] },
    { ...pdfManifest(3), pages: [ { page: 2, width: 612, height: 792 }, ...pdfManifest(3).pages.slice(1) ] },
    { kind: 'pdf', page_count: 1, pages: [ { page: 1, width: Infinity, height: 792 } ] } ]) {
    assert.throws(() => validatePdfManifest(invalid), error => error instanceof ApiError && error.code === 'invalid_response');
  }
});

test('PDF batches enforce exact order, manifest sizes, page count, end marker and data JPEG without rejecting base64 padding', () => {
  const manifest = pdfManifest(445);
  for (const extraBytes of [0, 1, 2]) assert.equal(validatePdfPageBatch(pdfBatch(manifest, 445, jpeg(extraBytes)), manifest, 445).pages.length, 1);
  const valid = pdfBatch(manifest, 1);
  const invalid = [ { ...valid, kind: 'other' }, { ...valid, page_count: 430 }, { ...valid, next_page: 5 },
    { ...valid, pages: valid.pages.slice(1) }, { ...valid, pages: [valid.pages[1], valid.pages[0], valid.pages[2]] },
    { ...valid, pages: valid.pages.map((page, index) => index ? page : { ...page, width: 613 }) },
    { ...valid, pages: valid.pages.map((page, index) => index ? page : { ...page, image: 'https://remote.invalid/page.jpg' }) },
    { ...valid, pages: valid.pages.map((page, index) => index ? page : { ...page, image: 'data:image/png;base64,aA==' }) },
    { ...valid, pages: valid.pages.map((page, index) => index ? page : { ...page, image: 'data:image/jpeg;base64,/9j/AA==' }) } ];
  for (const batch of invalid) assert.throws(() => validatePdfPageBatch(batch, manifest, 1), error => error instanceof ApiError && error.code === 'invalid_response');
});

test('first and final PDF batches use authenticated three-page requests; cancellation and real API failures survive', async () => {
  const manifest = pdfManifest(445);
  const document = { dataset_id: 'library/a', document_id: 'long/pdf', title: '长文件.pdf' };
  for (const start of [1, 445]) {
    const controller = new AbortController();
    globalThis.fetch = async (path, options) => {
      const url = new URL(path, 'https://local.invalid');
      assert.equal(url.pathname, '/api/enterprise/business/product/knowledge/datasets/library%2Fa/documents/long%2Fpdf/preview/pages/');
      assert.equal(url.searchParams.get('start_page'), String(start));
      assert.equal(url.searchParams.get('page_size'), '3');
      assert.equal(options.headers.get('Authorization'), 'Bearer isolated-test-token');
      assert.equal(options.signal, controller.signal);
      return Response.json(pdfBatch(manifest, start));
    };
    const result = await loadKnowledgePdfPages(document, manifest, start, controller.signal);
    assert.equal(result.pages[0].page, start);
    assert.equal(result.pages.length, start === 1 ? 3 : 1);
  }
  const controller = new AbortController();
  let release;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: () => new Promise(resolve => { release = resolve; }) });
  const pending = loadKnowledgePdfPages(document, manifest, 1, controller.signal);
  await new Promise(resolve => setTimeout(resolve, 0));
  controller.abort(); release(pdfBatch(manifest, 1));
  await assert.rejects(pending, { name: 'AbortError' });
  for (const [status, code] of [[403, 'scope_revoked'], [413, 'preview_limit'], [502, 'invalid_response']]) {
    globalThis.fetch = async () => Response.json({ detail: '该批次原始错误', code }, { status });
    await assert.rejects(loadKnowledgePdfPages(document, manifest, 445, new AbortController().signal), error => error instanceof ApiError && error.status === status && error.code === code && error.message === '该批次原始错误');
  }
});

test('srcDoc keeps safe server HTML and escapes all plain text, with CSP and no script or same-origin permissions', async () => {
  const html = knowledgePreviewHtml('<!doctype html><html><head><style>p{color:navy}</style></head><body><p>完整首尾</p><img src="data:image/png;base64,aA=="></body></html>', 'text/html');
  assert.match(html, /<head><meta http-equiv="Content-Security-Policy"/);
  assert.match(html, /default-src 'none'; img-src data:; style-src 'unsafe-inline'/);
  assert.match(html, /<style>p\{color:navy\}<\/style>/);
  assert.match(html, /<img src="data:image\/png;base64,aA==">/);
  const plain = knowledgePreviewHtml('首段 & <script>bad()</script>\n<img src="https://remote.invalid">\n尾段 >', 'text/plain');
  assert.match(plain, /首段 &amp; &lt;script&gt;bad\(\)&lt;\/script&gt;/);
  assert.match(plain, /&lt;img src="https:\/\/remote\.invalid"&gt;/);
  assert.match(plain, /尾段 &gt;/);
  assert.match(plain, /white-space:pre-wrap;overflow-wrap:anywhere/);
  assert.doesNotMatch(plain, /<script|<img/);
  const browserSource = await readFile(new URL('../src/business/product/KnowledgeDocumentBrowser.tsx', import.meta.url), 'utf8');
  assert.match(browserSource, /<iframe[^>]*srcDoc=\{loaded\.content\}[^>]*sandbox=""/);
  assert.doesNotMatch(browserSource, /allow-scripts|allow-same-origin|revokeObjectURL/);
});

test('access revocation, oversized and unsupported previews retain server errors instead of returning partial text', async () => {
  for (const [status, code] of [[401, 'unauthorized'], [403, 'forbidden'], [413, 'document_too_large'], [415, 'unsupported_preview']]) {
    globalThis.fetch = async () => Response.json({ detail: '原文件预览不可用', code }, { status });
    await assert.rejects(loadKnowledgePreview({ dataset_id: 'library', document_id: 'doc', title: 'test' }, new AbortController().signal),
      error => error instanceof ApiError && error.status === status && error.code === code);
  }
});

test('list and reader expose separate pending states, document title, return, close and original download controls', () => {
  const common = { onAccessRevoked: () => assert.fail('reading must not revoke access') };
  const browser = renderToStaticMarkup(React.createElement(KnowledgeDocumentBrowser, { ...common,
    dataset: { id: 'library', name: '已授权工程库', document_count: 23 }, selected: null,
    onOpen: () => assert.fail('rendering must not open a document'), onBack: () => {} }));
  assert.match(browser, /已授权工程库文档列表/);
  assert.match(browser, /返回问答/);
  assert.match(browser, /搜索文档名称/);
  assert.match(browser, /正在读取文档列表/);
  const reader = renderToStaticMarkup(React.createElement(KnowledgeDocumentPreview, { ...common,
    document: { dataset_id: 'library', document_id: 'doc', title: '完整技术方案.docx' }, onClose: () => {} }));
  assert.match(reader, /完整技术方案\.docx/);
  assert.match(reader, /关闭文档预览/);
  assert.match(reader, /下载原文件/);
  assert.match(reader, /正在读取完整原文/);
  assert.doesNotMatch(reader, /chunk|切片|拼接/);
});

test('left and right separators follow physical drag direction, enforce limits and support keyboard extremes', () => {
  assert.equal(dragPanelWidth(300, 70, 1, 220, 480), 370);
  assert.equal(dragPanelWidth(475, -100, -1, 280, 710), 575);
  assert.equal(dragPanelWidth(300, -999, 1, 220, 480), 220);
  assert.equal(dragPanelWidth(475, -999, -1, 280, 710), 710);
  assert.equal(clampPanelWidth(474.6, 280, 710), 475);
  assert.equal(keyPanelWidth(300, 'ArrowLeft', 1, 220, 480), 290);
  assert.equal(keyPanelWidth(475, 'ArrowLeft', -1, 280, 710), 485);
  assert.equal(keyPanelWidth(475, 'ArrowRight', -1, 280, 710), 465);
  assert.equal(keyPanelWidth(280, 'ArrowRight', -1, 280, 710), 280);
  assert.equal(keyPanelWidth(475, 'Home', -1, 280, 710), 280);
  assert.equal(keyPanelWidth(475, 'End', -1, 280, 710), 710);
  assert.equal(keyPanelWidth(475, 'Enter', -1, 280, 710), null);
  const html = renderToStaticMarkup(React.createElement(WorkbenchSeparator, { label: '调整全文预览宽度', width: 475, min: 280, max: 710, direction: -1, onResize: () => {} }));
  assert.match(html, /role="separator" aria-orientation="vertical" aria-label="调整全文预览宽度"/);
  assert.match(html, /aria-valuemin="280" aria-valuemax="710" aria-valuenow="475"/);
  assert.match(html, /tabindex="0"/);
});

test('knowledge-only hide controls keep both left panes mounted and restore controls outside the hidden panes', async () => {
  const render = feature => renderToStaticMarkup(React.createElement(MemoryRouter, {}, React.createElement(ProductWorkspace, { feature })));
  const knowledge = render('knowledge');
  assert.match(knowledge, /aria-controls="product-workspace-navigation" aria-expanded="true"/);
  assert.match(knowledge, /隐藏产品导航/);
  assert.match(knowledge, /aria-controls="knowledge-sidebar" aria-expanded="true"/);
  assert.match(knowledge, /隐藏知识库与会话栏/);
  assert.match(knowledge, /aria-label="调整产品导航宽度"/);
  assert.match(knowledge, /aria-label="调整知识库与会话栏宽度"/);
  const source = await readFile(new URL('../src/business/product/ProductKnowledge.tsx', import.meta.url), 'utf8');
  assert.match(source, /<aside id="knowledge-sidebar"[^>]*hidden=\{sidebarHidden\}/);
  assert.doesNotMatch(source, /!sidebarHidden && <(?:KnowledgeDocumentBrowser|KnowledgeDocumentPreview)/);
  const css = await readFile(new URL('../src/business/product/knowledge-workbench.css', import.meta.url), 'utf8');
  assert.match(css, /\.pk-workspace \.pk-sidebar\[hidden\] \{ display:none; \}/);
  assert.match(css, /\.pk-layout\.sidebar-collapsed \{ grid-template-columns:minmax\(0,1fr\); \}/);
  assert.doesNotMatch(render('overview'), /隐藏产品导航|隐藏知识库与会话栏|role="separator"/);
  const separator = await readFile(new URL('../src/business/product/WorkbenchSeparator.tsx', import.meta.url), 'utf8');
  assert.match(separator, /setPointerCapture\(event\.pointerId\)/);
  assert.match(separator, /onPointerCancel=\{finish\} onLostPointerCapture=\{finish\}/);
  assert.match(separator, /delete current\.scope\.dataset\.resizing/);
  const reference = await readFile(new URL('../src/business/product/product-reference.css', import.meta.url), 'utf8');
  assert.match(reference, /\.wb-shell\[data-resizing\] iframe \{ pointer-events:none; \}/);
  const originalWindow = globalThis.window;
  try {
    for (const [stored, width] of [[null, 224], ['238', 238], ['NaN', 224], ['999', 224]]) {
      globalThis.window = { innerWidth: 1440, location: { search: '', pathname: '/departments/product/knowledge' }, sessionStorage: { getItem: () => stored } };
      for (const feature of ['knowledge', 'overview']) assert.match(render(feature), new RegExp(`style="--nav-width:${width}px"`));
    }
    globalThis.window.sessionStorage.getItem = () => { throw new Error('Storage disabled'); };
    assert.match(render('knowledge'), /style="--nav-width:224px"/);
  } finally { globalThis.window = originalWindow; }
});
