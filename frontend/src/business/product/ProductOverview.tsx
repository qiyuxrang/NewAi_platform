import { ArrowRight, Download, Folder, Plus, RefreshCw } from "lucide-react";
import { CenterLink } from "../shared";
import { artifactDownload, artifactHistoryDownload, draftDownload, draftHistoryDownload, type TaskSummary } from "./product-api";
import { ProductStatistics, ProjectStatus } from "./ProductProjects";
import { DocumentSymbol, EmptyState, LoadState } from "./workbench-shared";
import { formatDate, outputNames, outputStatus, projectUrl, stageNames, useProductOverview } from "./workbench-state";
import "./product-project-list.css";

function todoAction(task: TaskSummary) {
  if (task.state === "WAITING_REVIEW" && task.stage === "BLUEPRINT") return { detail: "蓝图已形成，等待本人确认", label: "查看蓝图", tab: "blueprint" };
  if (task.state === "WAITING_INPUT" && task.error_code === "delivery_incomplete") return { detail: "部分成果需修复，已保存文件可先下载", label: "查看问题", tab: "technical-solution" };
  if (task.state === "WAITING_INPUT") return { detail: "项目需要补充资料或处理前置条件", label: "核对资料", tab: "sources" };
  if (task.state === "FAILED") return { detail: "处理已暂停，查看项目状态和已有成果", label: "查看状态", tab: "overview" };
  return { detail: "核对项目当前状态，已生成文件可直接查看", label: "查看项目", tab: "overview" };
}

export default function ProductOverview() {
  const { data, error, reload } = useProductOverview();
  const projectLink = (id: string, tab = "overview") => projectUrl(id, tab) + "&returnTo=" + encodeURIComponent("/departments/product");
  const listLink = (filter = "all") => "/centers/product/projects?" + new URLSearchParams({ filter, page: "1", page_size: "20" });
  return <div className="pd-workspace pp-page po-page">
    <header className="pp-heading"><div><h1>部门总览</h1><p>查看部门项目状态、待办和最近成果。</p></div><div className="po-heading-actions"><button className="po-refresh" onClick={reload} disabled={!data && !error}><RefreshCw size={17}/>刷新</button><CenterLink href="/centers/product/new" className="pp-primary"><Plus size={19}/>新建项目</CenterLink></div></header>
    <ProductStatistics metrics={data?.metrics ?? null} href={listLink}/>
    <p className="po-data-scope">统计范围：当前账号可访问的项目{data && <span>更新于 {formatDate(data.as_of)}</span>}</p>
    {!data ? <LoadState error={error} reload={reload}/> : <>
      <section className="po-section" aria-labelledby="po-todos-title">
        <div className="po-section-heading"><div><h2 id="po-todos-title">需要我处理</h2><p>优先查看等待确认、补充资料或处理失败的项目。</p></div><CenterLink href={listLink("attention")}>查看需处理项目<ArrowRight size={16}/></CenterLink></div>
        {data.todos.length ? <div className="po-todos">{data.todos.map(task => {
          const action = todoAction(task);
          return <article className="po-todo" key={task.id}><span className="po-folder"><Folder size={22}/></span><div className="po-todo-copy"><CenterLink href={projectLink(task.id, action.tab)}>{task.title}</CenterLink><p>{action.detail}</p></div><ProjectStatus task={task}/><CenterLink className="po-todo-action" href={projectLink(task.id, action.tab)}>{action.label}<ArrowRight size={16}/></CenterLink></article>;
        })}</div> : <EmptyState title="暂无待办项目" detail="当前没有等待确认、补充资料或处理失败的项目。"/>}
      </section>
      <section className="po-section" aria-labelledby="po-projects-title">
        <div className="po-section-heading"><div><h2 id="po-projects-title">最近项目</h2><p>继续处理最近更新的项目。</p></div><CenterLink href={listLink()}>全部项目<ArrowRight size={16}/></CenterLink></div>
        {data.recent_projects.length ? <div className="po-recent-projects">{data.recent_projects.map(task => <article className="po-project" key={task.id}><CenterLink className="pp-project-name" href={projectLink(task.id)}><Folder size={20}/><strong>{task.title}</strong></CenterLink><span>{stageNames[task.stage] || "阶段待确认"}</span><ProjectStatus task={task}/><time>{formatDate(task.updated_at)}</time><CenterLink href={projectLink(task.id)}>查看详情<ArrowRight size={16}/></CenterLink></article>)}</div> : <EmptyState title="尚未创建项目" detail="新建项目后即可开始蓝图与成果编制。" create/>}
      </section>
      <section className="po-section" aria-labelledby="po-outputs-title">
        <div className="po-section-heading"><div><h2 id="po-outputs-title">最近成果</h2><p>已生成的文件可逐份查看、下载。</p></div><CenterLink href="/centers/product/outputs">全部成果<ArrowRight size={16}/></CenterLink></div>
        {data.recent_outputs.length ? <div className="po-outputs">{data.recent_outputs.map(output => {
          const download = output.family === "technical-solution" ? (output.current ? artifactDownload(output.id) : artifactHistoryDownload(output.id)) : (output.current ? draftDownload(output.id) : draftHistoryDownload(output.id));
          const status = outputStatus(output);
          return <article className="po-output" key={output.id}><div className="po-output-main"><DocumentSymbol family={output.family}/><div><strong>{outputNames[output.family]}</strong><p title={output.title}>{output.title}</p></div></div><div className="po-output-meta"><span>V{output.version} · {status}</span><time>{formatDate(output.created_at)}</time></div><div className="po-output-actions"><CenterLink href={projectLink(output.task_id, output.current ? output.family : "history")}>查看{output.current ? "成果" : "版本"}<ArrowRight size={15}/></CenterLink><a href={download} download><Download size={16}/>下载文件</a></div></article>;
        })}</div> : <EmptyState title="暂无已生成成果" detail="项目生成文件后会出现在这里。"/>}
      </section>
    </>}
  </div>;
}
