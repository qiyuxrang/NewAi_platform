import { useEffect, useId, useRef, useState } from "react";
import { ArrowRight, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Clock3, Folder, MoreHorizontal, Pin, Plus, Search, Trash2 } from "lucide-react";
import { ApiError } from "../api";
import { CenterLink } from "../shared";
import { deleteTask, pinTask } from "./product-api";
import type { ProductOverview, TaskSummary } from "./product-api";
import { EmptyState, LoadState } from "./workbench-shared";
import { formatDate, goProduct, projectUrl, stageNames, stateNames, useProductOverview } from "./workbench-state";
import "./project-workbench.css";
import "./product-project-list.css";

const filters = [
  { code: "all", label: "全部项目", metric: "all", icon: Folder, tone: "blue", detail: "当前账号可访问的全部项目" },
  { code: "active", label: "未结束项目", metric: "active", icon: Clock3, tone: "blue", detail: "包含待完善、生成中、待确认和处理失败的项目" },
  { code: "review", label: "待确认", metric: "review", icon: Clock3, tone: "orange", detail: "当前处于待确认状态的项目" },
  { code: "completed", label: "已完成", metric: "completed", icon: CheckCircle2, tone: "green", detail: "以服务端项目完成状态为准" },
  { code: "completed_month", label: "本月完成", metric: "completed_month", icon: CalendarDays, tone: "blue", detail: "已完成且最近更新时间在本月的项目" },
] as const;
const extraFilters = [{ code: "attention", label: "需处理" }, { code: "generation", label: "正文／文档阶段（未结束）" }];
const views = {
  projects: { title: "历史项目", description: "管理全部项目，查看进展、资料和已生成成果。", action: "查看详情", tab: "overview" },
  sources: { title: "项目资料", description: "按项目查看上传资料。", action: "查看资料", tab: "sources" },
  outputs: { title: "文档成果", description: "查看当前成果和版本。", action: "查看成果", tab: "technical-solution" },
  history: { title: "版本记录", description: "追溯项目版本记录。", action: "查看版本", tab: "history" },
} as const;
const errorLabels: Record<string, string> = {
  model_authorization_required: "等待生成授权",
  revision_requested: "蓝图待修改",
  source_permission_changed: "资料权限需确认",
};

function ProjectActions({ task, busy, onAction }: { task: TaskSummary; busy: boolean; onAction: (task: TaskSummary, action: "pin" | "delete") => void }) {
  const id = useId(), menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = () => menu.current?.hidePopover();
    window.addEventListener("scroll", close, true); window.addEventListener("resize", close);
    return () => { window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close); };
  }, [open]);
  const act = (action: "pin" | "delete") => { menu.current?.hidePopover(); onAction(task, action); };
  return <>
    <button type="button" disabled={busy} popoverTarget={id} aria-label={task.title + "的更多操作"} aria-expanded={open} aria-controls={id} onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect();
      setPosition({ left: Math.max(8, Math.min(rect.right - 148, window.innerWidth - 156)), top: rect.bottom + 104 > window.innerHeight ? Math.max(8, rect.top - 104) : rect.bottom + 6 });
    }}><MoreHorizontal size={20}/></button>
    <div id={id} ref={menu} popover="auto" className="pp-project-menu" role="group" aria-label={task.title + "的项目操作"} style={position} onToggle={event => setOpen(event.newState === "open")}>
      <button type="button" disabled={busy} autoFocus onClick={() => act("pin")}><Pin size={16}/>{task.is_pinned ? "取消置顶" : "置顶"}</button>
      <button type="button" disabled={busy} className="pp-delete-project" onClick={() => act("delete")}><Trash2 size={16}/>删除</button>
    </div>
  </>;
}

export function ProjectStatus({ task }: { task: TaskSummary }) {
  const tone = task.state === "COMPLETED" ? "good" : ["FAILED", "WAITING_INPUT"].includes(task.state) ? "warning" : ["CANCELLED", "DRAFT"].includes(task.state) ? "neutral" : "info";
  const label = task.state === "WAITING_REVIEW" && task.stage === "BLUEPRINT" ? "蓝图待确认" : stateNames[task.state] || "状态待确认";
  const note = task.error_code ? errorLabels[task.error_code] || "请查看详情" : task.state === "FAILED" ? "处理已暂停，请查看详情" : "";
  return <span className="pp-status"><span className={"pp-badge " + tone}>{label}</span>{note && <small>{note}</small>}</span>;
}

export function ProductStatistics({ metrics, selected = "", href }: { metrics: ProductOverview["metrics"] | null; selected?: string; href: (filter: string) => string }) {
  return <div className="pp-statistics">{filters.map(item => {
    const count = metrics?.[item.metric];
    const Icon = item.icon;
    return <CenterLink key={item.code} href={href(item.code)} className={"pp-stat-card " + item.tone + (selected === item.code ? " selected" : "")}>
      <span className="pp-stat-icon"><Icon size={29} strokeWidth={1.8}/></span>
      <span className="pp-stat-copy" title={item.detail}><span>{item.label}</span><strong>{count == null ? "—" : count.toLocaleString("zh-CN")}<small> 个</small></strong></span>
    </CenterLink>;
  })}</div>;
}

export default function ProductProjects({ view = "projects" }: { view?: keyof typeof views }) {
  const params = new URLSearchParams(window.location.search);
  const requestedFilter = params.get("filter") || "all";
  const filter = [...filters, ...extraFilters].some(item => item.code === requestedFilter) ? requestedFilter : "all";
  const query = (params.get("q") || "").slice(0, 200);
  const requestedPage = Number(params.get("page"));
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 && requestedPage <= 1000000 ? requestedPage : 1;
  const requestedSize = Number(params.get("page_size"));
  const pageSize = [12, 20, 50].includes(requestedSize) ? requestedSize : 20;
  return <ProjectList key={[view, filter, query, page, pageSize].join(":")} view={view} filter={filter} query={query} page={page} pageSize={pageSize}/>;
}

function ProjectList({ view, filter, query, page, pageSize }: { view: keyof typeof views; filter: string; query: string; page: number; pageSize: number }) {
  const [search, setSearch] = useState(query);
  const lock = useRef(false);
  const [busy, setBusy] = useState(false), [actionError, setActionError] = useState("");
  const requestQuery = new URLSearchParams({ filter, q: query, page: String(page), page_size: String(pageSize) }).toString();
  const { data, error, reload } = useProductOverview(requestQuery, true, lock);
  const config = views[view];
  const returnTo = window.location.pathname + window.location.search;
  const link = (nextFilter = filter, nextPage = 1, nextQuery = query, nextSize = pageSize) => "/centers/product/" + view + "?" + new URLSearchParams({ filter: nextFilter, page: String(nextPage), q: nextQuery, page_size: String(nextSize) });
  const projectLink = (id: string) => projectUrl(id, config.tab) + "&returnTo=" + encodeURIComponent(returnTo);
  const currentPage = data?.pagination.page ?? page;
  const totalPages = data?.pagination.pages ?? 0;

  async function act(task: TaskSummary, action: "pin" | "delete") {
    if (lock.current || !task.can_manage) return;
    lock.current = true;
    if (action === "delete" && !window.confirm(`确认删除项目“${task.title}”？删除后将结束该项目的后台任务，并从项目列表移除，且不可恢复。`)) { lock.current = false; return; }
    setBusy(true); setActionError("");
    try {
      if (action === "delete") await deleteTask(task.id, task.version);
      else await pinTask(task.id, task.version, !task.is_pinned);
      window.dispatchEvent(new Event("product:tasks-changed"));
      if (action === "delete" && data?.projects.length === 1 && currentPage > 1) goProduct(link(filter, currentPage - 1));
      else reload();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "项目操作失败，请重试。");
      if (reason instanceof ApiError && reason.status === 409) reload();
    } finally { lock.current = false; setBusy(false); }
  }

  return <div className="pd-workspace pp-page">
    <header className="pp-heading"><div><h1>{config.title}</h1><p>{config.description}</p></div><CenterLink href="/centers/product/new" className="pp-primary"><Plus size={19}/>新建项目</CenterLink></header>
    <ProductStatistics metrics={data?.metrics ?? null} selected={filter} href={next => link(next)}/>
    <section className="pp-panel" aria-label="项目清单">
      <div className="pp-tools">
        <nav className="pp-tabs" aria-label="项目状态筛选">{filters.map(item => <CenterLink key={item.code} href={link(item.code)} current={filter === item.code} className={filter === item.code ? "active" : ""}>{item.label}</CenterLink>)}</nav>
        <form className="pp-search" role="search" onSubmit={event => { event.preventDefault(); goProduct(link(filter, 1, search.trim())); }}>
          <Search size={18}/><input aria-label="搜索项目名称" value={search} onChange={event => setSearch(event.target.value)} maxLength={200} placeholder="搜索项目名称"/><button type="submit">搜索</button>
        </form>
      </div>
      <div className="pp-filter-row">
        <label>当前阶段<select disabled title="当前接口暂不支持按阶段筛选" aria-describedby="pp-filter-note"><option>全部阶段</option></select></label>
        <label>状态<select value={filter} onChange={event => goProduct(link(event.target.value))}>{[...filters, ...extraFilters].map(item => <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
        <label>所有者<select disabled title="当前接口暂不支持按所有者筛选" aria-describedby="pp-filter-note"><option>全部所有者</option></select></label>
        <label className="pp-date-filter">最近更新<span><input type="date" aria-label="更新开始日期" disabled title="当前接口暂不支持按日期筛选"/><b>—</b><input type="date" aria-label="更新结束日期" disabled title="当前接口暂不支持按日期筛选"/></span></label>
        <button className="pp-reset" onClick={() => goProduct(link("all", 1, "", pageSize))}>重置</button>
      </div>
      <p id="pp-filter-note" className="pp-filter-note">仅显示当前账号可访问的项目。阶段、所有者和日期筛选暂不可用。</p>
      {actionError && <p className="pp-action-error" role="alert">{actionError}</p>}
      {!data ? <LoadState error={error} reload={reload}/> : data.projects.length ? <div className="pp-table-wrap"><table className="pp-table">
        <colgroup><col style={{ width: "35%" }}/><col style={{ width: "12%" }}/><col style={{ width: "13%" }}/><col style={{ width: "12%" }}/><col style={{ width: "14%" }}/><col style={{ width: "14%" }}/></colgroup>
        <thead><tr><th>项目名称</th><th>当前阶段</th><th>状态</th><th>项目所有者</th><th>最近更新</th><th>操作</th></tr></thead>
        <tbody>{data.projects.map(task => <tr key={task.id}>
          <td><div className="pp-project-title"><CenterLink href={projectLink(task.id)} className="pp-project-name"><Folder size={20}/><strong title={task.title}>{task.title}</strong></CenterLink>{task.is_pinned && <span className="pp-pinned"><Pin size={12}/>置顶</span>}</div></td>
          <td>{stageNames[task.stage] || "阶段待确认"}</td><td><ProjectStatus task={task}/></td>
          <td>{task.owner_name || "未提供"}</td><td>{formatDate(task.updated_at)}</td>
          <td><div className="pp-row-actions"><CenterLink href={projectLink(task.id)}>{config.action}<ArrowRight size={16}/></CenterLink>{task.can_manage && <ProjectActions task={task} busy={busy} onAction={(item, action) => void act(item, action)}/>}</div></td>
        </tr>)}</tbody>
      </table></div> : <EmptyState title={query || filter !== "all" ? "没有符合条件的项目" : "尚未创建项目"} detail={query || filter !== "all" ? "调整关键词或状态筛选后再试。" : "新建项目后即可开始蓝图与成果编制。"} create={!query && filter === "all"}/>}
      <footer className="pp-pagination">
        <span>{data ? "共 " + data.pagination.total.toLocaleString("zh-CN") + " 个项目" : "项目数量待读取"}</span>
        <div><button aria-label="上一页" disabled={!data || currentPage <= 1} onClick={() => goProduct(link(filter, currentPage - 1))}><ChevronLeft size={17}/></button><span className="pp-current-page" aria-label={"第 " + currentPage + " 页"}>{currentPage}</span><button aria-label="下一页" disabled={!data || currentPage >= totalPages} onClick={() => goProduct(link(filter, currentPage + 1))}><ChevronRight size={17}/></button><label className="pp-page-size"><span className="sr-only">每页项目数</span><select value={pageSize} onChange={event => goProduct(link(filter, 1, query, Number(event.target.value)))}><option value={12}>12 条/页</option><option value={20}>20 条/页</option><option value={50}>50 条/页</option></select></label></div>
      </footer>
    </section>
  </div>;
}
