import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { BookOpen, Check, ChevronRight, Copy, Globe, MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Send, Sparkles, Square, UserRound } from "lucide-react";
import { ApiError, apiEventStream, apiRequest } from "../api";
import type { AssistantActivity } from "../api";
import MarkdownContent from "../../components/MarkdownContent";
import { ProductIcon } from "./workbench-shared";
import { KnowledgeDocumentBrowser, KnowledgeDocumentPreview } from "./KnowledgeDocumentBrowser";
import type { DocumentReference, KnowledgeDataset } from "./knowledge-documents";
import WorkbenchSeparator from "./WorkbenchSeparator";
import { clampPanelWidth, useElementWidth } from "./workbench-resize";
import "./knowledge-workbench.css";

interface KnowledgeStatus { available: boolean; code: string; help: string; knowledge?: { available: boolean; code: string; help: string }; web_search?: { available: boolean; code: string; help: string }; assistant?: { runtime: 'deepseek_harness'; version?: string; available: boolean; code: string; help: string } }
interface Session { id: string; title: string; version: number }
interface Source { id: string; dataset_id?: string; document_id?: string; title: string; content: string; type?: 'knowledge' | 'web'; url?: string }
interface Turn { question: string; answer: string; sources: Source[]; outcome: "answered" | "empty"; request_id: string; assistant?: boolean; activities?: AssistantActivity[] }
interface Conversation extends Session { turns: Turn[] }
interface Attempt { question: string; version: number; request_id: string; assistant?: boolean; web_search?: boolean }
interface ActiveAssistantRequest { conversationId: string; requestId: string; signal: AbortSignal; stopping: boolean; ended: boolean }
const root = "/api/product/knowledge/";
const conversationPath = (id: string) => `${root}conversations/${encodeURIComponent(id)}/`;
const activityLabels: Record<AssistantActivity['tool'], string> = { knowledge_search: '检索知识库', knowledge_list: '查阅文档目录', knowledge_read: '阅读知识文档', web_search: '搜索网页', web_fetch: '阅读网页', calculate: '计算核对', plan: '整理任务步骤', answer: '组织回答' };
const accessRevoked = (reason: unknown) => reason instanceof ApiError && (reason.status === 401 || reason.status === 403 && ['forbidden', 'scope_revoked'].includes(reason.code || ''));

function ProcessingSteps({ activities }: { activities: AssistantActivity[] }) {
  if (!activities.length) return null;
  return <details className="pk-processing">
    <summary>处理过程 <small>{activities.filter(item => item.status === 'completed').length} 项完成</small></summary>
    <ol>{activities.map(item => <li key={item.id} data-status={item.status}>
      {item.status === 'running' ? <span className="pd-spinner"/> : item.status === 'completed' ? <Check size={14}/> : <span aria-hidden="true">!</span>}
      <span><strong>{activityLabels[item.tool]}</strong><small>{item.summary}</small></span>
    </li>)}</ol>
  </details>;
}

function publicSourceUrl(source: Source) {
  try { const url = new URL(source.url || ''); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; }
  catch { return undefined; }
}

export default function ProductKnowledge() {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [datasets, setDatasets] = useState<KnowledgeDataset[] | null>(null);
  const [activeDataset, setActiveDataset] = useState<KnowledgeDataset | null>(null);
  const [previewDocument, setPreviewDocument] = useState<DocumentReference | null>(null);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const [previewWidth, setPreviewWidth] = useState<number | null>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const measuredWidth = useElementWidth(layoutRef);
  const layoutWidth = measuredWidth || 1200;
  const compact = typeof window !== "undefined" && window.innerWidth <= 1250;
  const gap = compact ? 18 : 24;
  const sidebarMax = Math.min(480, Math.max(220, layoutWidth - 240 - gap));
  const visibleSidebarWidth = clampPanelWidth(sidebarWidth ?? (compact ? 300 : 338), 220, sidebarMax);
  const availableForReading = layoutWidth - (sidebarHidden ? 0 : visibleSidebarWidth) - gap * (sidebarHidden ? 1 : 2);
  const previewOverlay = availableForReading < 520;
  const previewMin = Math.min(280, layoutWidth);
  const previewMax = Math.min(900, previewOverlay ? layoutWidth : availableForReading - 240);
  const visiblePreviewWidth = clampPanelWidth(previewWidth ?? (previewOverlay ? Math.min(600, layoutWidth) : availableForReading / 2), previewMin, previewMax);
  const [datasetError, setDatasetError] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [selected, setSelected] = useState("");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [activities, setActivities] = useState<AssistantActivity[]>([]);
  const [stopping, setStopping] = useState(false);
  const activeRequest = useRef<ActiveAssistantRequest | null>(null);
  const controller = useRef<AbortController | null>(null);
  const datasetController = useRef<AbortController | null>(null);
  const turnsRef = useRef<HTMLDivElement | null>(null);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);
  const followStream = useRef(false);
  const focusAfterOpen = useRef(false);
  const locked = useRef(false);
  const assistantAvailable = !!status?.available && status.assistant?.available !== false;
  const knowledgeAvailable = !!status?.available && status.knowledge?.available !== false;
  const knowledgeUnavailableLabel = status?.knowledge?.code === "knowledge_not_authorized" ? "知识库未授权" : "知识库暂不可用";
  const visibleSessions = sessions.filter(item => (item.title || "未命名会话").toLocaleLowerCase().includes(historyQuery.trim().toLocaleLowerCase()));

  const revokeAccess = useCallback(() => {
    controller.current?.abort(); datasetController.current?.abort(); locked.current = false;
    activeRequest.current = null; setStopping(false);
    followStream.current = false;
    setConversation(null); setAttempt(null); setQuestion(""); setDraft(""); setActivities([]); setSessions([]); setSelected(""); setBusy("");
    setDatasets(null); setDatasetError(""); setActiveDataset(null); setPreviewDocument(null);
    setStatus({ available: false, code: "access_revoked", help: "访问权限已变化，旧回答、引用和文档已清除。请确认授权后重新检查。" });
  }, []);
  function openDataset(dataset: KnowledgeDataset) {
    setActiveDataset(dataset); setPreviewDocument(null);
  }
  function returnToConversation() { setActiveDataset(null); setPreviewDocument(null); }

  function begin(label: string) {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    locked.current = true;
    setBusy(label); setError(""); setNotice("");
    return next.signal;
  }
  function finish(signal: AbortSignal) {
    if (!signal.aborted) { locked.current = false; setBusy(""); }
  }
  function clearConversation() {
    followStream.current = false;
    activeRequest.current = null; setStopping(false);
    setConversation(null); setAttempt(null); setQuestion(""); setDraft(""); setActivities([]);
  }
  function fail(reason: unknown, signal: AbortSignal) {
    if (signal.aborted) return;
    if (accessRevoked(reason)) {
      revokeAccess();
    }
    setError(reason instanceof Error ? `${reason.message}${reason instanceof ApiError && reason.code ? `（${reason.code}）` : ""}` : "请求失败，请重试。");
  }
  async function checkStatus(signal: AbortSignal, requireAssistant = false) {
    const value = await apiRequest<KnowledgeStatus>(`${root}status/`, { signal });
    if (signal.aborted) return false;
    setStatus(value);
    if (!value.available) { clearConversation(); setSessions([]); setSelected(""); datasetController.current?.abort(); setDatasets(null); setActiveDataset(null); setPreviewDocument(null); }
    if (value.knowledge?.available === false) { datasetController.current?.abort(); setDatasets(null); setDatasetError(""); setActiveDataset(null); setPreviewDocument(null); }
    return value.available && (!requireAssistant || value.assistant?.available !== false) ? value : null;
  }
  function accept(value: Conversation) {
    setConversation(value); setSelected(value.id);
    setSessions(previous => [{ id: value.id, title: value.title, version: value.version }, ...previous.filter(item => item.id !== value.id)]);
  }
  async function loadDatasets() {
    datasetController.current?.abort();
    const next = new AbortController();
    datasetController.current = next;
    setDatasets(null); setDatasetError("");
    try {
      const result = await apiRequest<{ datasets: KnowledgeDataset[] }>(`${root}datasets/`, { signal: next.signal });
      if (!next.signal.aborted) setDatasets(result.datasets);
    } catch (reason) {
      if (!next.signal.aborted) {
        if (accessRevoked(reason)) { revokeAccess(); return; }
        setDatasetError(reason instanceof Error ? reason.message : "读取知识库列表失败，请重试。");
      }
    }
  }
  async function initialize() {
    const signal = begin("正在检查知识库服务…");
    datasetController.current?.abort();
    clearConversation(); setSelected(""); setSessions([]); setStatus(null); setDatasets(null); setDatasetError(""); setActiveDataset(null); setPreviewDocument(null);
    try {
      const ready = await checkStatus(signal);
      if (!ready) return;
      const conversations = apiRequest<{ conversations: Session[] }>(`${root}conversations/`, { signal });
      if (ready.knowledge?.available !== false) void loadDatasets();
      const result = await conversations;
      if (!signal.aborted) setSessions(result.conversations);
    } catch (reason) { fail(reason, signal); }
    finally { finish(signal); }
  }
  useEffect(() => {
    void initialize();
    return () => { controller.current?.abort(); datasetController.current?.abort(); };
    // All requests are owned by this mount; switching sessions cancels the previous request.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Initialize once per mount; subsequent checks are explicit actions.
  }, []);
  useEffect(() => {
    if (focusAfterOpen.current && conversation && !busy) {
      questionRef.current?.focus({ preventScroll: true });
      focusAfterOpen.current = false;
    }
  }, [busy, conversation]);
  useEffect(() => {
    if (followStream.current && turnsRef.current) turnsRef.current.scrollTop = turnsRef.current.scrollHeight;
  }, [draft, activities, conversation?.turns.length]);

  async function openSession(id?: string) {
    if (locked.current || !status?.available) return;
    returnToConversation();
    const signal = begin(id ? "正在读取会话历史…" : "正在新建会话…");
    setHistoryQuery("");
    setHistoryExpanded(false);
    clearConversation(); setSelected(id || "");
    try {
      if (!await checkStatus(signal)) return;
      const value = await apiRequest<Conversation>(id ? conversationPath(id) : `${root}conversations/`, id ? { signal } : { method: "POST", body: "{}", signal });
      if (!signal.aborted) { focusAfterOpen.current = true; accept(value); }
    } catch (reason) { fail(reason, signal); }
    finally { finish(signal); }
  }
  async function send(retry = false) {
    if (locked.current || !assistantAvailable || (!conversation && !!selected) || (!retry && attempt) || (retry && !conversation)) return;
    if (!retry && !question.trim()) return;
    let payload = retry ? attempt : null;
    let id = conversation?.id || "";
    let request: ActiveAssistantRequest | null = null;
    const signal = begin("正在处理你的问题…");
    followStream.current = true;
    setDraft("");
    setActivities([]);
    try {
      const ready = await checkStatus(signal, true);
      if (!ready) return;
      let current = conversation;
      if (!current) {
        setBusy("正在新建会话…");
        current = await apiRequest<Conversation>(`${root}conversations/`, { method: "POST", body: "{}", signal });
        if (signal.aborted) return;
        accept(current);
      }
      id = current.id;
      payload = retry ? attempt : { question: question.trim(), version: current.version, request_id: crypto.randomUUID(), assistant: true, web_search: !!ready.web_search?.available };
      if (!payload) return;
      setAttempt(payload);
      setQuestion("");
      setBusy("正在处理你的问题…");
      request = { conversationId: id, requestId: payload.request_id, signal, stopping: false, ended: false };
      activeRequest.current = request;
      const value = await apiEventStream<Conversation>(conversationPath(id), { ...payload, stream: true }, signal,
        (delta, reset) => { if (!signal.aborted) setDraft(previous => reset ? delta : previous + delta); },
        activity => { if (!signal.aborted) setActivities(previous => [...previous.filter(item => item.id !== activity.id), activity]); });
      if (!signal.aborted) { accept(value); setAttempt(null); setQuestion(""); setDraft(""); setActivities([]); setError(""); request.stopping = false; }
    } catch (reason) {
      if (signal.aborted) return;
      if (request?.stopping && !accessRevoked(reason)) return;
      setDraft("");
      setActivities(previous => previous.map(item => item.status === "running" ? { ...item, status: "failed", summary: "本次处理未完成，可重试原问题。" } : item));
      if (!payload) { fail(reason, signal); return; }
      const failedAttempt = payload;
      if (reason instanceof ApiError && reason.status === 409 && reason.code === "history_limit") {
        setAttempt(null);
        setQuestion(failedAttempt.question);
        fail(reason, signal);
        setNotice("此对话已达到历史上限，请新建会话继续提问。");
      } else if (reason instanceof ApiError && reason.status === 409) {
        setConversation(null); setAttempt(null); setQuestion(failedAttempt.question);
        setBusy("会话已变化，正在重新读取历史…");
        try {
          const value = await apiRequest<Conversation>(conversationPath(id), { signal });
          if (!signal.aborted) {
            accept(value);
            if (value.turns.some(turn => turn.request_id === failedAttempt.request_id)) {
              setQuestion(""); setNotice("历史已更新，本次问题已处理，请查看回答。");
            } else if (value.version > failedAttempt.version) {
              setNotice("历史已更新，请核对后重新发送；这将创建新的请求。");
            } else {
              setAttempt(failedAttempt);
              setQuestion("");
              setError("对话仍在处理或上次请求尚未确认，请稍后重试本次问题");
            }
          }
        } catch (reloadError) { fail(reloadError, signal); }
      } else {
        if (reason instanceof ApiError && reason.status === 400) { setAttempt(null); setQuestion(failedAttempt.question); }
        fail(reason, signal);
      }
    } finally {
      if (request) request.ended = true;
      if (!request || (activeRequest.current === request && !request.stopping)) {
        activeRequest.current = null; setStopping(false); finish(signal);
      }
    }
  }

  async function stop() {
    const request = activeRequest.current;
    if (!request || request.stopping || request.signal.aborted) return;
    request.stopping = true; setStopping(true); setError("");
    try {
      const value = await apiRequest<Conversation>(`${conversationPath(request.conversationId)}cancel/`, {
        method: "POST", body: JSON.stringify({ request_id: request.requestId }), signal: request.signal,
      });
      if (activeRequest.current !== request || request.signal.aborted) return;
      accept(value); setAttempt(null); setDraft(""); setActivities([]); setError("");
      setNotice(value.turns.some(turn => turn.request_id === request.requestId) ? "本次回答已完成，请查看历史。" : "已停止本次回答，可以继续提问。");
      activeRequest.current = null; setStopping(false); finish(request.signal);
      controller.current?.abort();
    } catch (reason) {
      if (activeRequest.current !== request || request.signal.aborted) return;
      request.stopping = false; setStopping(false); fail(reason, request.signal);
      if (request.ended) { activeRequest.current = null; finish(request.signal); }
    }
  }

  return <div className="pd-workspace pk-workspace">
    <div className="pk-pane-controls"><button type="button" className="text-button pk-sidebar-toggle" aria-controls="knowledge-sidebar" aria-expanded={!sidebarHidden} onClick={() => setSidebarHidden(hidden => !hidden)}>{sidebarHidden ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}<span>{sidebarHidden ? "展开知识库与会话栏" : "隐藏知识库与会话栏"}</span></button></div>
    <div ref={layoutRef} className={`pk-layout${previewDocument ? " has-preview" : ""}${sidebarHidden ? " sidebar-collapsed" : ""}${previewOverlay ? " preview-overlay" : ""}`} style={{ "--pk-sidebar-width": `${visibleSidebarWidth}px`, "--pk-preview-width": `${visiblePreviewWidth}px`, "--pk-gap": `${gap}px` } as CSSProperties}>
      <aside id="knowledge-sidebar" className="pd-panel pk-sidebar" aria-label="知识库会话" hidden={sidebarHidden}>
        <section className="pk-datasets" aria-label="已授权知识库">
          <div className="pk-sidebar-heading"><h2>已授权知识库</h2><button type="button" className="button primary pk-compact-button" disabled title="当前未提供新建知识库功能"><Plus size={15}/>新建库 · 未开通</button></div>
          {knowledgeAvailable && !datasets && !datasetError && <p className="pd-muted" role="status">正在加载知识库列表…</p>}
          {status?.available && !knowledgeAvailable && <p className="pd-muted">{knowledgeUnavailableLabel}。</p>}
          {datasetError && <div className="pk-dataset-error" role="alert"><p>知识库列表读取失败：{datasetError}</p><button type="button" className="text-button" onClick={() => void loadDatasets()}>重新加载列表</button></div>}
          {datasets && !datasets.length && <p className="pd-muted">暂无已授权知识库。</p>}
          {datasets && !!datasets.length && <ul>{datasets.map((item, index) => <li key={item.id}><button type="button" className={activeDataset?.id === item.id ? "selected" : ""} aria-pressed={activeDataset?.id === item.id} onClick={() => openDataset(item)}><span className={`pk-library-icon tone-${index % 3}`}><BookOpen size={17}/></span><span className="pk-library-name" title={item.name}>{item.name}</span><small>{item.document_count} 篇文档</small></button></li>)}</ul>}
          {knowledgeAvailable && <p className="pk-range-note">点击知识库查阅文档；助手可检索全部已授权资料。</p>}
        </section>
        <button type="button" className="button secondary pk-mobile-history-toggle" aria-controls="knowledge-history-list" aria-expanded={historyExpanded} onClick={() => setHistoryExpanded(previous => !previous)}>{historyExpanded ? "收起历史会话" : "查看历史会话"}<span>{sessions.length} 个会话</span></button>
        <section id="knowledge-history-list" className={`pk-history${historyExpanded ? " expanded" : ""}`}>
          <div className="pk-history-heading"><h2>历史会话 <small>{sessions.length}</small></h2><button type="button" className="button secondary pk-compact-button" disabled={!status?.available || !!busy} onClick={() => void openSession()}><Plus size={15}/>新建会话</button></div>
          {!!sessions.length && <input className="pk-history-search" type="search" aria-label="搜索历史会话" placeholder="按标题搜索会话" value={historyQuery} onChange={event => setHistoryQuery(event.target.value)}/>}
          {!sessions.length && !busy && <p className="pd-muted">暂无会话。服务可用时可新建会话开始提问。</p>}
          <nav aria-label="历史会话">{visibleSessions.map(item => <button key={item.id} className={selected === item.id ? "selected" : ""} aria-pressed={selected === item.id} title={item.title || "未命名会话"} disabled={!status?.available || !!busy} onClick={() => void openSession(item.id)}><MessageSquare size={15}/><span className="pk-session-title">{item.title || "未命名会话"}</span><small>v{item.version}</small></button>)}</nav>
          {!!historyQuery && !visibleSessions.length && <p className="pk-no-matches">没有匹配的会话，请换个关键词。</p>}
        </section>
        <div className="pk-sidebar-footer"><button className="button secondary" disabled title="当前未提供清空历史会话功能">清空历史 · 未开通</button><button type="button" className="text-button" disabled={!!busy} onClick={() => void initialize()}><RefreshCw size={13}/>重新检查服务</button></div>
      </aside>
      {!sidebarHidden && <WorkbenchSeparator className="pk-sidebar-separator" label="调整知识库与会话栏宽度" width={visibleSidebarWidth} min={220} max={sidebarMax} onResize={setSidebarWidth}/>}
      {activeDataset && <KnowledgeDocumentBrowser key={activeDataset.id} dataset={activeDataset} selected={previewDocument} onOpen={setPreviewDocument} onBack={returnToConversation} onAccessRevoked={revokeAccess}/>}
      <section className="pk-conversation" hidden={!!activeDataset} aria-label="知识库问答内容" aria-busy={!!busy}>
        <header className="pk-page-header"><div><h1>智能助手</h1><p>直接对话，按需检索企业知识库或网页，查看处理过程与参考来源。</p></div><span className={`pd-badge ${assistantAvailable ? "good" : "warning"}`}>{status ? assistantAvailable ? "服务可用" : status.available ? "助手暂不可用" : "服务不可用" : busy ? "检查服务中" : "服务状态未确认"}</span></header>
        {status && !status.available && <div className="pk-unavailable" role="status"><ProductIcon name="shield"/><div><h2>知识库暂不可用</h2><p>{status.help || "请联系管理员检查知识库服务与授权。"}</p><small>{status.code}</small></div></div>}
        {status?.available && status.assistant?.available === false && <p className="pd-service-note" role="status">{status.assistant.help || "助手暂不可用，请稍后重新检查服务。知识库文档和历史仍可查阅。"}</p>}
        {status?.available && status.knowledge?.available === false && <p className="pd-service-note" role="status">{status.knowledge.help || "知识库暂不可用，仍可直接对话和查看历史。"}</p>}
        {conversation && <div className="pk-conversation-heading"><span title={conversation.title}>{conversation.title || "未命名会话"}</span><small>版本 {conversation.version}</small></div>}
        {error && <div className="pk-error" role="alert"><div><strong>未能完成本次请求</strong><p>{error}</p></div>{status?.available && !busy && (attempt ? <button className="button secondary" disabled={!assistantAvailable} onClick={() => void send(true)}>重试本次问题</button> : selected ? <button className="button secondary" onClick={() => void openSession(selected)}>重新加载历史</button> : <button className="button secondary" onClick={() => void initialize()}>重新加载会话列表</button>)}</div>}
        {notice && <p className="pd-service-note" role="status">{notice}</p>}
        {busy && <p role="status" className="pk-pending"><span className="pd-spinner"/>{busy}</p>}
        <div className="pk-turns" aria-label="问答历史" ref={turnsRef} onScroll={event => { const element = event.currentTarget; followStream.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80; }}>
          {!conversation && !busy && <div className="pd-empty"><ProductIcon name="search"/><h3>直接提问，或打开历史会话</h3><p>可以讨论问题、整理内容，或让助手查找企业资料。首次发送会自动新建会话。</p></div>}
          {conversation && !conversation.turns.length && !attempt && <div className="pd-empty"><h3>这个会话还没有问题</h3><p>试试“查找知识库中相关的技术方案”，或直接提出你的问题。</p></div>}
          {conversation?.turns.map((turn, index) => <article className="pk-turn" key={turn.request_id}>
            <div className="pk-question-block"><span className="pk-question-avatar"><UserRound size={19}/><span className="pk-sr-only">问题 {index + 1}</span></span><p>{turn.question}</p></div>
            <div className="pk-answer-row"><span className="pk-answer-avatar"><Sparkles size={22}/></span><div className="pk-answer-block"><div className="pk-answer-heading"><h3>{turn.assistant ? "智能助手" : "资料库回答"}</h3><div className="pk-answer-tools"><span className={`pd-badge ${turn.outcome === "empty" ? "neutral" : "good"}`}>{turn.outcome === "empty" ? "未命中资料" : turn.sources.length ? "附参考来源" : "对话回答"}</span><button type="button" disabled={!turn.answer || !navigator.clipboard} title="复制回答" onClick={() => void navigator.clipboard.writeText(turn.answer).then(() => setNotice("回答已复制。"), () => setNotice("复制失败，请选择回答文字复制。"))}><Copy size={14}/><span>复制</span></button></div></div>{turn.outcome === "empty" ? <p className="pk-no-answer">未找到足够的相关资料。请补充关键词或确认资料授权范围。</p> : <MarkdownContent fileLinks={false} className="pk-answer pk-markdown" content={turn.answer}/>}
              {!!turn.sources.length && <details className="pk-sources"><summary className="pk-sources-heading"><ChevronRight size={15} aria-hidden="true"/>参考资料 <span>{turn.sources.length}</span></summary><div className="pk-source-grid">{turn.sources.map((source, sourceIndex) => <div className="pk-source-card" key={`${source.id}-${sourceIndex}`}><details><summary><span className={`pk-source-icon ${/\.pdf$/i.test(source.title) ? "pdf" : ""}`}>{/\.pdf$/i.test(source.title) ? "PDF" : /\.docx?$/i.test(source.title) ? "W" : <ProductIcon name="file"/>}</span><span className="pk-source-title"><strong>{source.title || "未命名来源"}</strong><small>来源：{source.type === "web" ? "公开网页" : datasets?.find(item => item.id === source.dataset_id)?.name || "已授权资料"}</small><small>引用 [{source.id}] · 展开引用节选</small></span></summary><blockquote>{source.content}</blockquote></details>{source.type === "web" ? publicSourceUrl(source) && <a className="text-button pk-source-full" href={publicSourceUrl(source)} target="_blank" rel="noopener noreferrer"><Globe size={14}/>打开网页</a> : <button type="button" className="text-button pk-source-full" disabled={!source.dataset_id || !source.document_id || !knowledgeAvailable} onClick={() => { if (source.dataset_id && source.document_id) setPreviewDocument({ ...source, dataset_id: source.dataset_id, document_id: source.document_id }); }}><BookOpen size={14}/>查看全文</button>}</div>)}</div></details>}
            </div></div>
          </article>)}
          {attempt && <div className="pk-question-block pk-attempt"><span className="pk-question-avatar"><UserRound size={19}/></span><div><p>{attempt.question}</p><small>{busy ? "待回答" : "待重试"}</small></div></div>}
          {!!busy && !!activities.length && <ProcessingSteps activities={activities}/>}
          {draft && !!busy && <article className="pk-answer-row pk-streaming" aria-label="正在生成回答"><span className="pk-answer-avatar"><Sparkles size={22}/></span><div className="pk-answer-block"><div className="pk-answer-heading"><h3>回答生成中</h3><span className="pd-badge info">流式回答</span></div><MarkdownContent fileLinks={false} className="pk-answer pk-markdown" content={draft}/><small className="pd-muted">回答完成后保存到当前会话。</small></div></article>}
        </div>
        <form className="pk-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
          <label className="pk-sr-only" htmlFor="knowledge-question">你的问题</label>
          <textarea id="knowledge-question" ref={questionRef} rows={2} maxLength={2000} value={question} disabled={!assistantAvailable || (!conversation && !!selected) || !!busy || !!attempt} onChange={event => setQuestion(event.target.value)} placeholder="提问、检索资料或讨论想法…" aria-describedby="knowledge-keyboard knowledge-count" onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); void send(); }
          }}/>
          {status?.web_search?.available && <p className="pk-web-notice">优先查阅已授权知识库，按需联网补充；企业资料和历史不会发送给搜索服务。</p>}
          <div className="pk-composer-footer"><div className="pk-composer-context"><span className="pk-authorized-scope" title={status?.web_search?.available ? "助手自动判断是否需要公开网页资料。" : status?.web_search?.help || "联网搜索尚未配置"}><Globe size={15}/>{status?.web_search?.available ? "按需联网" : "联网暂不可用"}</span><span className="pk-authorized-scope" title={knowledgeAvailable ? "知识库检索范围由授权决定，助手按需检索。" : status?.knowledge?.help}><BookOpen size={15}/>{knowledgeAvailable ? "知识库检索" : knowledgeUnavailableLabel}{knowledgeAvailable && datasets && <small> · {datasets.length} 个库</small>}</span></div><div className="pk-send-controls"><small id="knowledge-keyboard">Enter 发送 · Shift+Enter 换行</small><small id="knowledge-count">{question.length}/2000</small>{attempt && busy === "正在处理你的问题…" ? <button type="button" className="button secondary" disabled={stopping} onClick={() => void stop()}><Square size={14}/>{stopping ? "正在停止…" : "停止"}</button> : <button className="button primary" disabled={!assistantAvailable || (!conversation && !!selected) || !!busy || !!attempt || !question.trim()}>发送<Send size={16}/></button>}</div></div>
        </form>
      </section>
      {previewDocument && knowledgeAvailable && <div className="pk-preview-pane"><WorkbenchSeparator className="pk-preview-separator" label="调整全文预览宽度" direction={-1} width={visiblePreviewWidth} min={previewMin} max={previewMax} onResize={setPreviewWidth}/><KnowledgeDocumentPreview key={JSON.stringify([previewDocument.dataset_id, previewDocument.document_id])} document={previewDocument} onClose={() => setPreviewDocument(null)} onAccessRevoked={revokeAccess}/></div>}
    </div>
  </div>;
}

