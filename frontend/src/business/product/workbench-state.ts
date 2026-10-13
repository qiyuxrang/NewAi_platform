import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../api";
import { workspaceHref } from "../workspace-navigation";
import { getProductOverview, type OutputFamily, type OutputReviewStatus, type ProductOverview } from "./product-api";

export const outputNames: Record<OutputFamily, string> = { "technical-solution": "技术方案", feasibility: "可研报告", presentation: "汇报 PPT" };
export function outputStatus(output: { current?: boolean; stale?: boolean; delivered?: boolean; approved?: boolean; review_status?: OutputReviewStatus }) {
  return output.current === false || output.stale || output.review_status === 'stale' ? '历史 · 已过期' : output.delivered || output.review_status === 'delivered' ? '已交付' : output.approved || output.review_status === 'approved' ? '已批准' : '草稿 · 待完善';
}
export const stateNames: Record<string, string> = { DRAFT: "待完善资料", WAITING_INPUT: "待处理", QUEUED: "排队中", RUNNING: "生成中", WAITING_REVIEW: "待确认", FAILED: "处理失败", CANCELLED: "已取消", COMPLETED: "已完成" };
export const stageNames: Record<string, string> = { INTAKE: "资料整理", BLUEPRINT: "项目蓝图", WRITING: "正文编制", CONTENT_CHECK: "内容检查", RENDER: "文档生成", FINAL_REVIEW: "成果汇总" };
export const projectUrl = (id: string, tab = "overview") => `/centers/product/projects?task=${encodeURIComponent(id)}&tab=${encodeURIComponent(tab)}`;
export function goProduct(url: string) { window.history.pushState({}, "", workspaceHref(url)); window.dispatchEvent(new PopStateEvent("popstate")); }
export function projectListUrl() {
  const value = new URLSearchParams(window.location.search).get('returnTo');
  if (value === '/departments/product') return value;
  if (!value || !/^\/(?:departments\/product\/(?:documents|outputs)(?:[?]|$)|centers\/(?:product\/|business\/(?:projects|history|outputs)(?:[?]|$)))/.test(value)) return workspaceHref('/centers/product/projects');
  const url = new URL(value, window.location.origin);
  return url.searchParams.has('task') ? workspaceHref('/centers/product/projects') : workspaceHref(`${url.pathname}${url.search}`);
}
export const formatDate = (value?: string) => value && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) : "时间未提供";
export const formatBytes = (bytes?: number) => bytes == null ? "大小未提供" : bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
export function productError(reason: unknown): string {
  if (reason instanceof ApiError && reason.status === 409) return `项目版本或前置条件已变化。${reason.message} 请刷新核对后重试。`;
  if (reason instanceof ApiError && reason.code === "product_disabled") return "产品业务服务尚未启用，请联系平台管理员。";
  if (reason instanceof ApiError && [401, 403, 404].includes(reason.status)) return "项目不存在或访问权限已变化，当前资料已隐藏。";
  return reason instanceof Error ? reason.message : "暂时无法读取数据，请稍后重试。";
}

export function useProductOverview(query = "", enabled = true, refreshPaused?: { current: boolean }) {
  const [refresh, setRefresh] = useState(0);
  const requestKey = useMemo(() => ({ query, enabled, refresh }), [query, enabled, refresh]);
  const [response, setResponse] = useState<{ key: typeof requestKey; data: ProductOverview | null; error: string } | null>(null);
  useEffect(() => {
    if (!requestKey.enabled) return;
    const controller = new AbortController();
    void getProductOverview(requestKey.query, controller.signal).then(value => {
      if (!value || !Array.isArray(value.projects) || !value.metrics || !value.capabilities) throw new Error("服务端工作台数据不完整，请重新加载。");
      if (!controller.signal.aborted) setResponse({ key: requestKey, data: value, error: "" });
    }).catch(reason => { if (!controller.signal.aborted) setResponse({ key: requestKey, data: null, error: productError(reason) }); });
    return () => controller.abort();
  }, [requestKey]);
  useEffect(() => {
    if (!enabled) return;
    const check = () => { if (!document.hidden && !refreshPaused?.current) setRefresh(value => value + 1); };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    return () => { window.removeEventListener("focus", check); document.removeEventListener("visibilitychange", check); };
  }, [enabled, refreshPaused]);
  // A response belongs to one request, including permission enablement and refresh.
  // Hide it during render as soon as that request changes, before effects run.
  const current = enabled && response?.key === requestKey ? response : null;
  return { data: current?.data ?? null, error: current?.error ?? "", reload: () => setRefresh(value => value + 1) };
}

export function useUnsavedWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const leave = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const guard = (event: Event) => { if (!window.confirm("还有未保存的内容，确定离开当前页面？")) event.preventDefault(); };
    window.addEventListener("beforeunload", leave);
    window.addEventListener("portal:navigation-guard", guard);
    return () => { window.removeEventListener("beforeunload", leave); window.removeEventListener("portal:navigation-guard", guard); };
  }, [dirty]);
}
