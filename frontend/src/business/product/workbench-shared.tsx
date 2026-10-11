import { CenterLink } from "../shared";
import type { OutputFamily, TaskSummary } from "./product-api";
import { stateNames } from "./workbench-state";

const iconPaths = {
  home: "m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9", folder: "M3 6h7l2 2h9v12H3V6Z", file: "M6 3h8l4 4v14H6V3Zm8 0v5h4M9 12h6m-6 4h6",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z", upload: "M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6", check: "m5 12 4 4L19 6", plus: "M12 4v16M4 12h16", arrow: "M4 12h16m-6-6 6 6-6 6",
  search: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z", layers: "m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5", shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4Zm-4 10 3 3 5-6", download: "M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4", settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2",
} as const;
export type ProductIconName = keyof typeof iconPaths;
export function ProductIcon({ name }: { name: ProductIconName }) { return <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={iconPaths[name]} /></svg>; }
export function CompanyMark() { return <svg className="pd-company-mark" width="45" height="34" viewBox="0 0 74 52" aria-hidden="true"><path d="M12 40V13c0-10 14-10 18-2s12 8 18 1" stroke="#00a0e9" strokeWidth="13" strokeLinecap="round" fill="none"/><circle cx="12" cy="40" r="9" fill="#00a0e9"/><circle cx="46" cy="10" r="9" fill="#00a0e9"/><path d="M41 42c7-12 14 12 23 0" stroke="#ffbe00" strokeWidth="13" strokeLinecap="round" fill="none"/><circle cx="65" cy="10" r="8" fill="#ee1729"/></svg>; }
export function StatusBadge({ task }: { task: Pick<TaskSummary, "state" | "stage"> }) { return <span className={`pd-badge ${task.state === "COMPLETED" ? "good" : ["FAILED", "WAITING_INPUT"].includes(task.state) ? "warning" : task.state === "CANCELLED" ? "neutral" : "info"}`}>{stateNames[task.state] || "状态待确认"}</span>; }
export function EmptyState({ title, detail, create = false }: { title: string; detail: string; create?: boolean }) { return <div className="pd-empty"><span className="pd-empty-icon"><ProductIcon name="folder" /></span><h3>{title}</h3><p>{detail}</p>{create && <CenterLink href="/centers/product/new" className="button primary"><ProductIcon name="plus" />新建项目</CenterLink>}</div>; }
export function LoadState({ error, reload }: { error: string; reload: () => void }) { return error ? <div className="pd-feedback" role="alert"><strong>暂时无法读取工作台</strong><p>{error}</p><button className="button secondary" onClick={reload}>重新加载</button></div> : <div className="pd-loading" role="status" aria-busy="true"><span className="pd-spinner" />正在读取项目数据…</div>; }
export function DocumentSymbol({ family }: { family: OutputFamily }) { return <span className={`pd-document-symbol ${family === "presentation" ? "ppt" : "word"}`}>{family === "presentation" ? "P" : "W"}</span>; }

