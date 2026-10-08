# -*- coding: utf-8 -*-
"""成本测算引擎 HTTP 接口（给 Dify 工作流调用）。

启动：
    .venv\\Scripts\\python.exe tools\\server.py --port 18080

接口（Dify 用 /openapi.json 导入自定义工具）：
    GET  /health          健康检查
    POST /estimate        清单进 → 四版测算出（上传 xlsx 或传服务器路径）
    POST /webprice        单个设备/材料联网取价
    POST /labor_quote     单个劳务项按定额组价
"""
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import pipeline, webprice  # noqa: E402

CONFIG = os.path.join(ROOT, "config", "settings.json")
OUT_DIR = os.path.join(ROOT, "data", "output")
IN_DIR = os.path.join(ROOT, "data", "input")
EXPORT_DIR = os.environ.get("EXPORT_DIR") or os.path.join(ROOT, "data", "export")
# 宿主机上对应的真实路径（给用户看的），容器内路径是 /app/data/export
HOST_EXPORT_DIR = os.environ.get("HOST_EXPORT_DIR") or EXPORT_DIR


def export_files(paths, project=""):
    """把生成的 Excel 再导出到固定目录（宿主机桌面），方便直接打开。"""
    import shutil as _sh
    safe = "".join(c for c in (project or "输出") if c not in '\\/:*?"<>|')[:30] or "输出"
    dst_dir = os.path.join(EXPORT_DIR, safe)
    os.makedirs(dst_dir, exist_ok=True)
    out = []
    for p in (paths or []):
        try:
            dst = os.path.join(dst_dir, os.path.basename(p))
            _sh.copy2(p, dst)
            out.append(dst)
        except Exception:
            continue
    host_dir = HOST_EXPORT_DIR.rstrip("\\/") + "\\" + safe
    return host_dir, out


def load_cfg():
    return json.load(open(CONFIG, encoding="utf-8"))


BASE_URL = os.environ.get("PUBLIC_BASE_URL") or "http://host.docker.internal:18080"
RAGFLOW_BASE = os.environ.get("RAGFLOW_BASE") or "http://host.docker.internal:8080"
RAGFLOW_API_KEY = os.environ.get("RAGFLOW_API_KEY", "")

app = FastAPI(
    title="成本测算引擎",
    description="工程量清单进 → 成本测算 / 劳务报价四版出；支持定额组价与联网取价。",
    version="1.0.0",
    servers=[{"url": BASE_URL,
              "description": "成本测算引擎服务地址（可用环境变量 PUBLIC_BASE_URL 覆盖）"}],
)


@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok", "service": "成本测算引擎"}


class ReportReq(BaseModel):
    estimate_json: str = ""
    query: str = ""
    knowledge_id: str = ""
    background: str = ""


REPORT_PROMPT = """你是市政工程成本测算工程师，给项目经理写一份中文测算报告。

要求：
1. 第一行给结论：清单名称、需报价项数、甲供剔除项数、设备材料合计、劳务合计。
2. 用 Markdown 表格列出四版明细（行数多就每版选前 10 行 + 注明"共 N 行"）。
3. 单列"风险与待办"：没取到价的项、备注里提到核减或缺图纸的项。
4. 若有知识库检索结果，加一段"参考同类项目做法"，只写检索到的内容。
5. 只讲事实，不要编造数字，不要复述这段指令。
6. 报告最后单独加一节「交付文件」：把数据里「导出目录」和「下载地址」原样写出来（这是 Excel 的位置和下载链接），
   并列出「导出文件」里的文件名。
7. 如果给了【项目背景】，第二行加「项目背景要点」（地点 / 工期 / 施工条件 / 甲供范围），
   并在「风险与待办」里结合背景写影响（如边通车降效、隧道作业、冬季养护、甲供范围变化）。

【测算原始数据】
{estimate}

【知识库检索结果】
{kb}

【项目背景（若下方为空表示没提供）】
{bg}
"""


def extract_background(text):
    """从项目背景文字里按规则抽取要点（不靠模型），返回 Markdown 片段。"""
    t = re.sub(r"\s+", " ", text or "")
    if not t.strip():
        return ""
    cfg = load_cfg().get("project_context", {}).get("keys", {})
    found = []
    for name, pattern in cfg.items():
        try:
            m = re.search(pattern, t)
        except re.error:
            continue
        if not m:
            continue
        # 取命中处前后各 40 字作为依据
        s = max(0, m.start() - 30)
        seg = t[s:m.end() + 45].strip()
        found.append((name, seg))
    if not found:
        return "**项目背景要点**：`%s`" % t[:150]
    lines = ["**项目背景要点（系统按规则提取）**"]
    for name, seg in found:
        lines.append("- %s：…%s…" % (name, seg))
    return "\n".join(lines)


@app.post("/report", summary="把测算结果整理成中文报告（引擎侧出，Dify 不用配模型）")
def report(req: ReportReq):
    """纯代码生成交付说明：不走大模型，速度快、数字与四件套逐项一致，不会编造。"""
    try:
        d = json.loads(req.estimate_json or "{}")
    except Exception:
        d = {}
    if isinstance(d, dict) and d.get("报告"):        # 传进来的已经是报告
        return {"报告": d["报告"], "模型": "无（代码生成）"}
    if not d:
        return {"报告": "没有拿到测算原始数据（estimate_json 为空或不是合法 JSON）。",
                "模型": "无（代码生成）"}

    def money(v):
        try:
            return "%.2f 万元" % (float(v) / 10000.0)
        except Exception:
            return "—"

    a = d.get("甲供C30版") or {}
    b = d.get("不提供C30版") or {}
    env = d.get("环境修正") or {}
    chk = d.get("校验") or {}
    L = []
    L.append("# %s｜成本测算与对外劳务报价" % (d.get("项目名称") or d.get("清单文件名") or "项目"))
    L.append("")
    L.append("**结论**：%s，地区 %s。"
             % (d.get("模式", "六件套"), d.get("地区", "—")))
    L.append("* 甲供 C30 版：**%s**（%s 元/单位）；直接费 %s，取费 %s"
             % (money(a.get("总计")), a.get("每单位", "—"),
                money(a.get("直接费")), money(a.get("取费"))))
    # 报价在 ⑤⑥ 两张表（采购清单口径下就是"设备材料采购总包报价"），不是③
    _is_buy = bool(d.get("纯采购清单"))
    L.append("* **%s**：%s（%s；表内「对外报价总额」行同此数）。"
             % ("⑤设备材料采购总包报价（含税）" if _is_buy else
                "⑤劳务报价（对外总包·含税）",
                money(d.get("劳务报价总包")),
                "设备材料到场价 + 采购管理费 5% + 税金 3%，不含安装" if _is_buy
                else "劳务分包口径，不含甲供设备材料"))
    net = d.get("纯网报价") or {}
    if net:
        L.append("* 纯网络检索口径：**%s**（%s 元/单位）%s"
                 % (money(net.get("总计")), net.get("每单位", "—"),
                    ("；" + net["工日说明"]) if net.get("工日说明") else ""))
    if b:
        L.append("* 甲方不提供 C30 版：**%s**（%s 元/单位）；其中劳务线 %s、材料线 %s"
                 % (money(b.get("总计")), b.get("每单位", "—"),
                    money(b.get("劳务线")), money(b.get("材料线"))))
    if env:
        L.append("* 环境与条件修正：%.1f%%（命中 %s；边通车/占道已含在降效 6%% 内，不重复计取）"
                 % ((env.get("系数") or 0) * 100,
                    "、".join(env.get("命中") or []) or "无"))
    own = d.get("供应归属清点") or {}
    if own:
        L.append("* 供应归属：%s" % "；".join("%s %d 项" % (k, v) for k, v in own.items()))
    hc = d.get("取价健康度") or {}
    if hc:
        L.append("* **取价健康度：%s**｜命中率 %.0f%%（%d 行里 %d 行无价）"
                 % (hc.get("结论"), (hc.get("命中率") or 0) * 100,
                    hc.get("行数") or 0, hc.get("零价项") or 0))
        for w in (hc.get("警告") or []):
            L.append("  * ⚠ %s" % w)
    L.append("")
    L.append("## 交付文件（一个 Excel，六张表）")
    L.append("")
    L.append("① 设备清单　② 劳务清单　③ 成本测算（库+网检索）　④ 成本测算（纯网检索）　"
             "⑤ 劳务报价（库+网检索）　⑥ 劳务报价（纯网检索）")
    L.append("")
    # 采购清单没有劳务分包这回事，取费链和⑤⑥的口径必须分开写，别拿一套模板硬套
    if _is_buy:
        L.append("本清单是**设备材料采购清单**：③④表尾给出「成本测算总计（采购总包口径）」＝"
                 "设备材料到场价 + 采购管理费 5% + 税金 3%；⑤⑥是按同一口径出的采购总包报价。"
                 "不含施工内容，因此不计人工降效、风险包干与交通安措。")
    else:
        L.append("⑤⑥是劳务分包对外总包报价（取费链：降效 6% → 风险 4% → 管理费 10% → 税金 3%，"
                 "基数只含劳务与交通安措，不含甲供设备材料）。")
    L.append("每行的取价来源、核验链接、可信度都写在③④表末三列；单价与合价不留空白，"
             "取不到市场价的按品类经验区间或含量库暂估并在备注里标「必须询价复核」。")
    if d.get("导出目录"):
        L.append("")
        L.append("**导出目录（宿主机，直接打开）**：`%s`" % d["导出目录"])
    for f in (d.get("导出文件") or []):
        L.append("* %s" % os.path.basename(str(f)))
    if d.get("下载地址"):
        L.append("")
        L.append("**下载链接**：%s" % d["下载地址"])
    L.append("")
    L.append("## 风险与待办")
    L.append("")
    if chk:
        L.append("* 通用校验：%s/%s 项通过%s"
                 % (chk.get("通过数"), chk.get("总检查"),
                    "" if chk.get("通过") else "；未过项：%s" % "、".join(chk.get("问题") or [])))
    todo = d.get("待确认项") or []
    if todo:
        L.append("* 供应归属存疑 %d 项，需业主或设计确认：" % len(todo))
        for t in todo[:8]:
            L.append("  * %s（原因：%s）" % (t.get("项目名称"), t.get("原因")))
    cards = d.get("项目理解卡") or []
    miss = [c.get("分析项") for c in cards if c.get("状态") == "缺"]
    if miss:
        L.append("* 背景/技术方案中没有找到依据的项：%s —— 按常规口径处理，"
                 "补充资料后可再跑一次修正。" % "、".join(miss))
    if not (todo or miss):
        L.append("* 暂无需人工确认项。")
    return {"报告": "\n".join(L), "模型": "无（代码生成）",
            "甲供C30版": a.get("总计"), "不提供C30版": b.get("总计")}


def _report_llm(req):
    """旧版：走大模型写报告（保留备用，默认不走）。"""
    key = webprice.read_dashscope_key()
    if not key:
        raise HTTPException(500, "未配置 DASHSCOPE_API_KEY")
    kb_text = ""
    if req.query and RAGFLOW_API_KEY:
        try:
            r = retrieval(RetrievalReq(knowledge_id=req.knowledge_id or
                                       os.environ.get("RAGFLOW_DATASET_ID", ""),
                                       query=req.query,
                                       retrieval_setting={"top_k": 3, "score_threshold": 0.1}))
            kb_text = "\n".join("[%s] %s" % (x.get("title"), x.get("content"))
                                for x in (r.get("records") or []))
        except Exception as e:  # noqa: BLE001
            kb_text = "（检索失败：%s）" % str(e)[:60]
    bg = (req.background or "").strip()
    if not bg:
        try:
            bg = (json.loads(req.estimate_json or "{}").get("项目背景") or "")
        except Exception:
            bg = ""
    prompt = REPORT_PROMPT.format(estimate=(req.estimate_json or "")[:5000],
                                  kb=kb_text[:2000] or "（无）",
                                  bg=(bg or "（无）")[:2500])
    # 报告用快模型 + 限长：Dify 工具节点有超时，必须压到 40 秒内
    model = os.environ.get("DASHSCOPE_MODEL_REPORT") or "qwen-turbo"
    try:
        text = webprice.ask_llm(prompt, key, model=model, timeout=120, max_tokens=1200)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, "生成报告失败：%s" % str(e)[:120])

    # 交付文件这一节由代码确定性追加，不依赖模型（模型常因长度限制写不到这里）
    extra = ""
    bg_section = extract_background(bg)
    if bg_section:
        extra += "\n\n---\n\n## 项目背景\n\n" + bg_section + "\n"
    try:
        data = json.loads(req.estimate_json or "{}")
        exp_dir = data.get("导出目录") or ""
        url = data.get("下载地址") or ""
        files = data.get("导出文件") or []
        if exp_dir or url or files:
            lines = ["", "---", "", "## 交付文件（Excel）", ""]
            if exp_dir:
                lines.append("**导出目录（宿主机，直接打开即可）**：`%s`" % exp_dir)
            if files:
                lines.append("")
                lines.append("文件清单：")
                for f in files:
                    lines.append("- %s" % os.path.basename(str(f)))
            if url:
                # 下载链接放最后一行，复制时不会带上后面的文字
                lines.append("")
                lines.append("**下载链接（复制整行到浏览器）**：")
                lines.append(url)
            extra = "\n".join(lines)
    except Exception:
        extra = ""
    return {"报告": (text or "") + extra, "知识库片段数": kb_text.count("["),
            "模型": model}


class RetrievalReq(BaseModel):
    knowledge_id: str = ""
    query: str
    retrieval_setting: dict = {}


@app.get("/retrieval", summary="外部知识库连通性检查（Dify 外部知识库用）")
def retrieval_probe():
    return {"status": "ok", "backend": "ragflow", "datasets": _ragflow_datasets()}


def _ragflow_datasets():
    if not RAGFLOW_API_KEY:
        return []
    try:
        import urllib.request as _u
        req = _u.Request(RAGFLOW_BASE + "/api/v1/datasets?page_size=50",
                         headers={"Authorization": "Bearer " + RAGFLOW_API_KEY})
        with _u.urlopen(req, timeout=15) as r:
            d = json.load(r)
        return [{"id": x["id"], "name": x["name"], "docs": x.get("document_count")}
                for x in (d.get("data") or [])]
    except Exception:
        return []


@app.post("/retrieval", summary="外部知识库检索（Dify → 本服务 → RAGFlow）")
def retrieval(req: RetrievalReq):
    """按 Dify『外部知识库 API』规范返回检索结果，后端是 RAGFlow。"""
    if not RAGFLOW_API_KEY:
        return {"records": [], "说明": "未配置 RAGFLOW_API_KEY，本次跳过知识库检索"}
    setting = req.retrieval_setting or {}
    top_k = int(setting.get("top_k") or 5)
    threshold = float(setting.get("score_threshold") or 0.0)
    ds = req.knowledge_id or os.environ.get("RAGFLOW_DATASET_ID") or ""
    body = {"question": req.query, "page_size": top_k,
            "similarity_threshold": threshold, "top_k": top_k,
            # 向量权重调低一点，关键词权重调高：定额编号、型号这类精确词更依赖关键词命中
            "vector_similarity_weight": float(os.environ.get("RAGFLOW_VECTOR_WEIGHT", "0.3")),
            "keyword": True}
    rerank_id = os.environ.get("RAGFLOW_RERANK_ID")
    if rerank_id:
        body["rerank_id"] = rerank_id
    if ds:
        body["dataset_ids"] = [ds]
    data = json.dumps(body).encode()
    r = urllib.request.Request(RAGFLOW_BASE + "/api/v1/retrieval", data=data,
                               headers={"Authorization": "Bearer " + RAGFLOW_API_KEY,
                                        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            got = json.load(resp)
    except Exception as e:  # noqa: BLE001
        # RAGFlow 没起来（内存紧张时常被停掉）不应该把整条工作流打断：
        # 返回空结果并说明原因，测算照常进行，只是少了"参考同类项目做法"这一段。
        return {"records": [],
                "说明": "知识库（RAGFlow）当前不可用：%s；本次跳过检索，不影响测算。"
                        % str(e)[:120]}

    records = []
    for ch in (got.get("data") or {}).get("chunks", []) if isinstance(got.get("data"), dict) \
            else (got.get("data") or []):
        records.append({
            "content": (ch.get("content") or ch.get("content_with_weight") or "")[:2000],
            "score": round(float(ch.get("similarity") or ch.get("score") or 0), 4),
            "title": ch.get("document_keyword") or ch.get("docnm_kwd") or "RAGFlow",
            "metadata": {"dataset": ch.get("dataset_id"), "doc": ch.get("docnm_kwd")},
        })
    return {"records": records[:top_k]}


@app.post("/estimate", summary="清单进 → 四版测算出")
def estimate(          # 同步函数：FastAPI 会放到线程池里跑，避免与内部 asyncio.run 冲突
    file: Optional[UploadFile] = File(None, description="工程量清单 xlsx"),
    path: Optional[str] = Form(None, description="或直接给服务器上的清单路径"),
    out_name: str = Form("成本测算_四版.xlsx", description="输出文件名"),
):
    if file is None and not path:
        raise HTTPException(400, "要么上传 file，要么给 path")
    if file is not None:
        tmpd = tempfile.mkdtemp(prefix="boq_")
        src = os.path.join(tmpd, file.filename or "清单.xlsx")
        with open(src, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file.file.close()
    else:
        src = path
    if not os.path.exists(src):
        raise HTTPException(400, "清单文件不存在：%s" % src)

    return _run_estimate(src, out_name)


@app.get("/download", summary="下载最近一次生成的结果文件")
def download(name: str = "成本测算_四版.xlsx", project: str = ""):
    """容错下载：名字里带换行/空格/反引号也能认；找不到就按文件名在导出目录里搜。"""
    raw = (name or "").replace("\r", "\n").split("\n")[0].strip().strip("`'\" ")
    raw = os.path.basename(raw) or "成本测算_四版.xlsx"
    cands = [os.path.join(OUT_DIR, raw)]
    if project:
        cands.append(os.path.join(EXPORT_DIR, project, raw))
    for c in cands:
        if os.path.exists(c):
            return FileResponse(c, filename=os.path.basename(c))
    # 兜底：在整个导出目录里按文件名找
    for dirpath, _, names in os.walk(EXPORT_DIR):
        for f in names:
            if f == raw:
                return FileResponse(os.path.join(dirpath, f), filename=f)
    # 再兜底：只给名字片段也能匹配
    for dirpath, _, names in os.walk(EXPORT_DIR):
        for f in names:
            if raw and raw in f:
                return FileResponse(os.path.join(dirpath, f), filename=f)
    raise HTTPException(404, "文件不存在：%s" % raw)


@app.get("/download_latest", summary="下载最新一次生成的文件（不用记文件名）")
def download_latest(kind: str = "四版", project: str = ""):
    """kind：四版 / 设备清单 / 劳务清单 / 成本测算表 / 对外劳务报价 / 采购责任。"""
    base = os.path.join(EXPORT_DIR, project) if project else EXPORT_DIR
    best, best_t = None, 0.0
    for dirpath, _, names in os.walk(base):
        for f in names:
            if not f.lower().endswith((".xlsx", ".xlsm")):
                continue
            if kind and kind not in f:
                continue
            p = os.path.join(dirpath, f)
            t = os.path.getmtime(p)
            if t > best_t:
                best, best_t = p, t
    if not best:
        raise HTTPException(404, "没找到匹配的文件（kind=%s）" % kind)
    return FileResponse(best, filename=os.path.basename(best))


@app.get("/list_exports", summary="列出已导出到桌面的交付文件")
def list_exports(project: str = ""):
    base = os.path.join(EXPORT_DIR, project) if project else EXPORT_DIR
    if not os.path.isdir(base):
        return {"目录": base, "文件": []}
    out = []
    for dirpath, _, names in os.walk(base):
        for f in names:
            if f.lower().endswith((".xlsx", ".xlsm")):
                out.append(os.path.join(dirpath, f))
    return {"目录": base, "文件": sorted(out)}


class EstimateNamedReq(BaseModel):
    file_name: str
    out_name: str = "成本测算_四版.xlsx"


@app.post("/estimate_named", summary="按文件名测算（文件放在 data/input 目录）")
def estimate_named(req: EstimateNamedReq):
    src = os.path.join(IN_DIR, os.path.basename(req.file_name))
    if not os.path.exists(src):
        raise HTTPException(400, "data/input 里没有这个文件：%s" % req.file_name)
    return _run_estimate(src, req.out_name)


class EstimateLatestReq(BaseModel):
    out_name: str = "成本测算_四版.xlsx"


@app.post("/estimate_latest", summary="测算 data/input 里最新的那份清单")
def estimate_latest(req: EstimateLatestReq = EstimateLatestReq()):
    files = [os.path.join(IN_DIR, f) for f in os.listdir(IN_DIR)
             if f.lower().endswith((".xlsx", ".xlsm")) and not f.startswith("~$")]
    if not files:
        raise HTTPException(400, "data/input 目录里没有 xlsx 清单")
    src = max(files, key=os.path.getmtime)
    return _run_estimate(src, req.out_name)


@app.get("/list_inputs", summary="列出 data/input 里的清单")
def list_inputs():
    if not os.path.isdir(IN_DIR):
        return {"files": []}
    return {"files": sorted(f for f in os.listdir(IN_DIR)
                            if f.lower().endswith((".xlsx", ".xlsm")))}


def _run_estimate(src, out_name):
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, out_name)
    result = pipeline.run(load_cfg(), src, out)
    return {
        "清单": result["title"],
        "甲供剔除": len(result["dropped"]),
        "成本测算_库加网": result["cost_rows"],
        "成本测算_纯网": result["cost_rows_net"],
        "劳务报价_库加网": result["labor_rows"],
        "劳务报价_纯网": result["labor_rows_net"],
        "设备材料合计": round(result["total_cost"], 2),
        "劳务合计": round(result["total_labor"], 2),
        "结果文件": out,
    }


class WebPriceReq(BaseModel):
    name: str
    spec: str = ""
    unit: str = ""
    qty: float = 1


@app.post("/webprice", summary="单个设备/材料联网取价")
def web_price(req: WebPriceReq):
    key = webprice.read_dashscope_key()
    if not key:
        raise HTTPException(500, "未配置 DASHSCOPE_API_KEY")
    res = webprice.price_item(req.name, req.spec, req.unit, req.qty,
                              load_cfg(), key, webprice.Cache())
    return JSONResponse(res)


class LaborReq(BaseModel):
    name: str
    unit: str = "座"
    qty: float = 1
    region: str = "陕西"


@app.post("/labor_quote", summary="劳务项按定额组价")
def labor_quote(req: LaborReq):
    qlib = pipeline.load_quota()
    pick = pipeline.pick_quota(qlib, req.name, req.unit)
    if not pick:
        return {"匹配": False, "说明": "定额未命中，建议人工询价",
                "检索词": pipeline.keywords_of(req.name)}
    unit_cost = float(pick.get("人工费") or 0) + float(pick.get("机械费") or 0)
    return {"匹配": True, "定额编号": pick["编号"], "定额名称": pick["项目名称"],
            "专业": pick["专业"], "单位": pick["单位"], "人工费": pick.get("人工费"),
            "机械费": pick.get("机械费"), "人工工日": pick.get("人工工日"),
            "劳务单价": round(unit_cost, 2), "合价": round(unit_cost * req.qty, 2),
            "匹配理由": pick.get("理由")}


@app.post("/lamp_quote", summary="生成太阳能路灯项目六件套交付文件")
def lamp_quote():
    """一键生成：设备清单 / 劳务清单 / 成本测算表 / 两版对外报价 / 采购责任分类表。"""
    from engine import project_lamp as pl
    v, files = pl.build_all()
    a, b = v["甲供C30"], v["不提供C30"]
    return {
        "项目": pl.P["项目名称"],
        "路灯数量": pl.P["路灯数量"],
        "拆除数量": pl.P["拆除数量"],
        "纯成本每座": round(v["纯成本每座"], 2),
        "甲供C30版": {"总价": round(a["总计"], 2), "每座": round(a["单价每座"], 2),
                      "直接费": round(a["直接费"], 2), "取费": round(a["取费小计"], 2)},
        "不提供C30版": {"总价": round(b["总计"], 2), "每座": round(b["单价每座"], 2),
                        "劳务线": round(b["劳务线含税"], 2),
                        "材料线": round(b["材料线含税"], 2)},
        "文件": files,
        "输出目录": pl.OUT_DIR,
    }


class ProjectQuoteReq(BaseModel):
    file_name: str
    project_name: str = ""
    region: str = "陕西"
    measure_per_unit: float = 295
    c30_price: float = 280
    c30_volume: float = 0
    params: dict = {}


@app.post("/project_quote", summary="任意清单 → 六件套交付文件（通用版）")
def project_quote(req: ProjectQuoteReq):
    from engine import project_quote as pq
    src = os.path.join(IN_DIR, os.path.basename(req.file_name))
    if not os.path.exists(src):
        raise HTTPException(400, "data/input 里没有这个文件：%s" % req.file_name)
    over = dict(req.params or {})
    if req.project_name:
        over["项目名称"] = req.project_name
    if req.region:
        over["地区"] = req.region
    over["安措元每单位"] = req.measure_per_unit
    over["C30单价"] = req.c30_price
    if req.c30_volume:
        over["C30方量"] = req.c30_volume
    _, summary, files = pq.run(src, over)
    dst, exported = export_files(list(files.values()), summary.get("项目名称"))
    return {"汇总": summary, "文件": files, "输出目录": summary.get("输出目录"),
            "导出目录": dst, "导出文件": exported}


@app.post("/sync_kb", summary="将人工审核后确认的网价同步进企业知识库（下次直接命中）")
def sync_kb(
    file: Optional[UploadFile] = File(None, description="六件套 xlsx；不传就用最近导出的那份"),
    project: str = Form("", description="按项目名找最近的导出文件"),
    path: str = Form("", description="或直接给六件套文件路径（工作流里传上一步返回的路径）"),
):
    src = ""
    if path:
        p = path.strip()
        # 工作流可以把上一步返回的整段 JSON 直接丢进来，这里自动取文件路径
        if p.startswith("{"):
            try:
                obj = json.loads(p)
                p = (obj.get("四件套文件") or obj.get("path")
                     or (obj.get("导出文件") or [""])[0])
            except Exception:
                p = ""
        if p and os.path.exists(p):
            src = p
    if not src and file is not None:
        src = _save_upload(file, "kb_")
    if not src:
        best, bt = None, 0.0
        for dirpath, _, names in os.walk(EXPORT_DIR):
            for f in names:
                if f.endswith(".xlsx") and "六件套" in f and (not project or project in dirpath):
                    p = os.path.join(dirpath, f)
                    if os.path.getmtime(p) > bt:
                        best, bt = p, os.path.getmtime(p)
        src = best or ""
    if not src or not os.path.exists(src):
        raise HTTPException(400, "没找到可同步的六件套文件")
    from engine import kbsync
    out = kbsync.sync(src)
    out["文件"] = os.path.basename(src)
    return out


def _save_upload(f: UploadFile, prefix="up_"):
    tmpd = tempfile.mkdtemp(prefix=prefix)
    p = os.path.join(tmpd, f.filename or "上传文件")
    with open(p, "wb") as fh:
        shutil.copyfileobj(f.file, fh)
    f.file.close()
    return p


@app.post("/understand", summary="背景/技术方案 → 项目理解卡（供人工确认）")
def understand_endpoint(
    bg_file: Optional[UploadFile] = File(None, description="项目背景/技术要求文档"),
    text: str = Form("", description="或直接粘贴背景文字"),
):
    t = (text or "").strip()
    if bg_file is not None:
        p = _save_upload(bg_file, "bg_")
        try:
            if p.lower().endswith(".docx"):
                import docx as _docx
                t = "\n".join(x.text for x in _docx.Document(p).paragraphs if x.text.strip())
            else:
                t = open(p, "rb").read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            t = (t + "\n（文档解析失败：%s）" % str(e)[:60]).strip()
    if not t:
        return {"分析项": [], "理解卡": "未提供背景或技术方案，跳过背景分析。",
                "说明": "没有背景文本时不产出理解卡，直接按清单口径测算。"}
    from engine import understanding as un
    cards = un.analyze(t[:8000])
    return {"分析项": cards, "理解卡": un.to_markdown(cards),
            "须确认项": [c["分析项"] for c in cards if c["状态"] == "缺"],
            "说明": "核对无误后在备注里写「确认」再跑一次即可产出四件套。"}


@app.post("/ownership", summary="清单 → 供应归属四路判定（A甲供/B我方采购/C我方辅材/D劳务自备/E存疑）")
def ownership_endpoint(
    file: Optional[UploadFile] = File(None, description="工程量清单 xlsx"),
    path: Optional[str] = Form(None, description="或服务器上的清单路径"),
):
    src = _save_upload(file, "own_") if file is not None else (path or "")
    if not src or not os.path.exists(src):
        raise HTTPException(400, "清单文件不存在")
    from engine import boq as boq_mod
    from engine import ownership as own
    title, items = boq_mod.parse(src)
    if not items:
        raise HTTPException(400, "清单没解析出明细，请检查表头")
    tagged, ask = own.classify_items(items)
    has_owner = any(x.get("甲供") == "是" for x in items)
    nature = "工程量清单（含甲供）" if has_owner else "采购清单（全部我方采购）"
    counts = own.summarize(tagged)
    return {"清单": title, "行数": len(items), "清单性质": nature,
            "甲供项数": sum(1 for x in items if x.get("甲供") == "是"),
            "清点": counts,
            "明细": [{"项目名称": x["项目名称"], "单位": x["单位"], "数量": x["数量"],
                      "供应归属": x["供应归属"], "归属依据": x["归属依据"]} for x in tagged],
            "待确认项": ask,
            "说明": ("整张清单没有任何『甲供』标注 → 判定为设备采购清单，"
                     "输出不出现甲供/劳务分包口径" if not has_owner else
                     "A 甲供只免材料费、安装人工照计；E 存疑需业主或设计确认后再定稿。")}


@app.post("/checkup", summary="对已生成的四件套 Excel 跑通用校验")
def checkup_endpoint(
    file: Optional[UploadFile] = File(None, description="要校验的 xlsx"),
    path: str = Form("", description="或服务器上的文件路径"),
    reference: float = Form(0, description="参考总价（给了就校核 ±10% 偏差）"),
):
    src = _save_upload(file, "chk_") if file is not None else path
    if not src or not os.path.exists(src):
        raise HTTPException(400, "待校验文件不存在")
    from engine import checkup
    return checkup.verify(src, reference=reference or None)


@app.post("/ingest_file", summary="定额/价格文件 → 入库（只入库，不出测算）")
def ingest_endpoint(
    file: UploadFile = File(..., description="定额或价格数据 xlsx"),
    hint: str = Form("", description="可选：定额数据 / 价格数据；留空自动识别"),
):
    src = _save_upload(file, "ing_")
    from engine import ingest as ing
    rep = ing.ingest(src, hint)
    return {"模式": "入库", "入库报告": rep,
            "说明": "本次只入库，未产出测算文件；下次测算时价格库/定额库会自动读到。"}


@app.post("/run_all", summary="一次上传：出四件套（一个 Excel 四个 Sheet）")
def run_all(
    file: Optional[UploadFile] = File(None, description="工程量清单 xlsx"),
    bg_file: Optional[UploadFile] = File(None, description="项目背景/技术要求文档（可选）"),
    path: Optional[str] = Form(None, description="或服务器上的清单路径"),
    out_name: str = Form("1.成本测算六件套.xlsx", description="六件套文件名"),
    project_name: str = Form("", description="项目名称（留空取清单标题）"),
    region: str = Form("陕西", description="地区"),
    measure_per_unit: float = Form(295, description="交通安措 元/单位"),
    c30_price: float = Form(280, description="C30 到场价 元/m³"),
    c30_volume: float = Form(0, description="C30 方量 m³（甲方不提供口径用；0=不单列材料线）"),
    background_text: str = Form("", description="项目背景文字（可选）"),
    note: str = Form("", description="备注：写「入库」则只入库；写「出四件套」或留空则出测算"),
    also_estimate: bool = Form(False, description="是否同时出「四版测算」文件"),
    sync_kb: bool = Form(False, description="默认不自动回写；人工审核后请调用 /sync_kb 同步"),
):
    """工作流一次调用即可拿到：一个 Excel、四个 Sheet（设备清单/劳务清单/成本测算表/对外报价清单）。"""
    if file is None and not path:
        raise HTTPException(400, "要么上传 file，要么给 path")
    asked_name = ""
    if file is not None:
        asked_name = file.filename or "清单.xlsx"
        tmpd = tempfile.mkdtemp(prefix="boq_")
        src = os.path.join(tmpd, asked_name)
        with open(src, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file.file.close()
    else:
        src = path
        asked_name = os.path.basename(path)
    if not os.path.exists(src):
        raise HTTPException(400, "清单文件不存在：%s" % src)

    # ── 指令分流：备注写「入库」就只入库，不出测算 ──
    want_ingest = "入库" in (note or "")
    want_quote = ("四件套" in (note or "")) or ("测算" in (note or "")) or not (note or "").strip()
    if want_ingest and not want_quote:
        from engine import ingest as ing
        hint = "定额数据" if "定额" in note else ("价格数据" if ("价格" in note or "报价" in note) else "")
        rep = ing.ingest(src, hint)
        return {"模式": "入库", "入库报告": rep,
                "说明": "本次按备注只做入库，未产出测算文件"}

    # 项目背景：既支持上传文档（docx/txt/pdf 抽文字），也支持直接粘贴文字
    bg_text = (background_text or "").strip()
    if bg_file is not None:
        try:
            raw = bg_file.file.read()
            tmpb = tempfile.mkdtemp(prefix="bg_")
            bp = os.path.join(tmpb, bg_file.filename or "背景.txt")
            with open(bp, "wb") as f:
                f.write(raw)
            bg_file.file.close()
            if bp.lower().endswith(".docx"):
                import docx as _docx
                bg_text = "\n".join(p.text for p in _docx.Document(bp).paragraphs if p.text.strip())
            else:
                bg_text = raw.decode("utf-8", "ignore")
            bg_text = bg_text[:6000]
        except Exception as e:  # noqa: BLE001
            bg_text = (bg_text + "\n（背景文档解析失败：%s）" % str(e)[:60]).strip()

    # 没单独给背景时，把备注里除"确认/入库"这类指令词以外的文字当背景用，
    # 这样用户在备注里写的施工条件（边通车/夜间/隧道…）也能参与环境修正。
    if not bg_text.strip() and len((note or "").strip()) >= 10:
        bg_text = re.sub(r"(出四件套|四件套|确认|入库|[：:]\s*)", " ", note or "").strip()

    # ── 项目理解卡：默认只作为附件信息随结果一起给出，不再挡在测算前面 ──
    #    要单独先看理解卡，备注里写「只看理解卡」即可（全自动是默认行为）
    cards = None
    if bg_text.strip():
        from engine import understanding as un
        cards = un.analyze(bg_text)
        if "只看理解卡" in (note or "") or "先看理解卡" in (note or ""):
            return {"模式": "理解卡（待确认）",
                    "项目理解卡": cards,
                    "理解卡": un.to_markdown(cards),
                    "说明": "按备注要求本次只输出理解卡；去掉「只看理解卡」再跑一次即出六件套。"}

    # ── 四件套：一个 Excel 四个 Sheet（设备/劳务/成本测算/对外报价），备注写进表内 ──
    from engine import foursheet
    over = {"项目名称": project_name or "", "地区": region or "陕西",
            "安措元每单位": measure_per_unit, "C30单价": c30_price}
    if c30_volume:
        over["C30方量"] = c30_volume
    res = foursheet.run(src, {k: v for k, v in over.items() if v},
                        bg_text=bg_text, out_name=out_name, export=True)
    sync_info = {"说明": "网价未自动回写知识库，待人工审核后请调用 /sync_kb 同步。"}
    if sync_kb:
        try:
            from engine import kbsync
            sync_info = kbsync.sync(res["四件套文件"])
            sync_info.pop("明细", None)
        except Exception as e:  # noqa: BLE001
            sync_info = {"错误": str(e)[:120]}

    out = {"模式": "六件套", "清单文件名": asked_name,
           "项目名称": res["项目名称"], "地区": res["地区"],
           "四件套文件": res["四件套文件"],
           "输出目录": res["输出目录"], "导出目录": res["导出目录"],
           "导出文件": res["导出文件"],
           "被占用另存": res.get("被占用另存") or [],
           "校验": res["校验"], "环境修正": res["环境修正"],
           "供应归属清点": res["供应归属清点"], "待确认项": res["待确认项"],
           "取价健康度": res.get("健康度"),
           "知识库同步": sync_info,
           "甲供C30版": res["甲供C30版"], "不提供C30版": res["不提供C30版"],
           "纯网报价": res.get("纯网报价"),
           "劳务报价总包": res.get("劳务报价总包"),
           "项目背景": bg_text[:1200], "项目理解卡": cards or [],
           "下载地址": "http://127.0.0.1:18080/download?name=" + os.path.basename(
               res["四件套文件"]),
           "导出目录说明": "宿主机上直接打开该文件夹即可看到四件套 Excel"}
    if also_estimate:
        est = _run_estimate(src, "成本测算_四版.xlsx")
        xlsx = os.path.basename(est.get("结果文件", ""))
        dst, exported = export_files([est.get("结果文件")], res["项目名称"])
        out["四版测算"] = {k: v for k, v in est.items() if k != "结果文件"}
        out["四版文件"] = est.get("结果文件")
        out["导出文件"] = list(out["导出文件"]) + list(exported)
    return out


# ──────────────────────────────────────────────────────────────────────
#  网页前端（给人用的工作台；Dify 走的是上面的接口）
# ──────────────────────────────────────────────────────────────────────
import threading          # noqa: E402
import time               # noqa: E402
import traceback          # noqa: E402
import uuid               # noqa: E402

WEB_DIR = os.path.join(HERE, "webapp")
JOBS = {}                 # job_id → 任务状态
JOB_ORDER = []            # 最近完成的任务（给首页"最近输出"用）
JOB_LOCK = threading.Lock()
ACTIVE = [None]           # 同一时间只跑一份：两份同时跑会互相把检索源打到风控


def _safe_upload_name(fn, default_ext=""):
    """上传文件名的兜底处理。

    有的客户端（PowerShell 的 -Form、部分脚本、Dify 的某些版本）会把中文名按
    RFC2047 编码成 `=?utf-8?B?...?=`，直接当文件名存下来就没有 .xlsx 后缀，
    openpyxl 直接报 "does not support  file format"。这里解码 + 补后缀。
    """
    name = str(fn or "").strip()
    m = re.match(r"^=\?([^?]+)\?([BbQq])\?([^?]*)\?=$", name)
    if m:
        charset, enc, data = m.group(1), m.group(2).upper(), m.group(3)
        try:
            import base64
            if enc == "B":
                raw = base64.b64decode(data + "=" * (-len(data) % 4))
            else:
                raw = urllib.parse.unquote_to_bytes(data.replace("_", " "))
            name = raw.decode(charset, "ignore")
        except Exception:  # noqa: BLE001
            pass
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "清单" + (default_ext or "")
    elif default_ext and not name.lower().endswith(default_ext):
        name += default_ext
    return name


def _bg_text_from_file(bp):
    """背景文档抽文字：docx 走 python-docx，其余按文本读。"""
    if not bp or not os.path.exists(bp):
        return ""
    if bp.lower().endswith(".docx"):
        try:
            import docx as _docx
            return "\n".join(p.text for p in _docx.Document(bp).paragraphs if p.text.strip())
        except Exception:  # noqa: BLE001
            return ""
    try:
        with open(bp, "rb") as f:
            return f.read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""


def _run_job(jid, boq_path, bg_path, note, over):
    job = JOBS.get(jid)
    if not job:
        return
    t0 = time.time()
    job.update(status="running", started=t0,
               step="解析清单：表头识别 / 甲供判定 / 分类")

    def step(s):
        job["step"] = s
        job.setdefault("轨迹", []).append(
            {"秒": round(time.time() - t0, 1), "步骤": s})

    try:
        bg_text = _bg_text_from_file(bg_path)
        if not bg_text.strip() and len((note or "").strip()) >= 10:
            bg_text = re.sub(r"(出六件套|六件套|四件套|确认|入库|[：:]\s*)", " ", note).strip()
        step("取价：企业价格库 → 历史报价库 → 公式 → 互联网检索")
        from engine import foursheet
        res = foursheet.run(boq_path, over, bg_text=bg_text, export=True)
        step("装配六件套 + 通用校验 34 项")
        sync = {"说明": "网价未自动回写知识库，待人工审核后请调用 /sync_kb 同步。"}
        step("生成交付说明")
        d = {"模式": "六件套", "清单文件名": job["清单文件名"],
             "项目名称": res["项目名称"], "地区": res["地区"],
             "四件套文件": res["四件套文件"], "输出目录": res["输出目录"],
             "导出目录": res["导出目录"], "导出文件": res["导出文件"],
             "被占用另存": res.get("被占用另存") or [],
             "校验": res["校验"], "环境修正": res["环境修正"],
             "供应归属清点": res["供应归属清点"], "待确认项": res["待确认项"],
             "取价健康度": res.get("健康度"), "知识库同步": sync,
             "甲供C30版": res["甲供C30版"], "不提供C30版": res["不提供C30版"],
             "纯网报价": res.get("纯网报价"),
             "劳务报价总包": res.get("劳务报价总包"),
             "纯采购清单": res.get("纯采购清单"),
             "项目背景": bg_text[:1200], "项目理解卡": []}
        try:
            d["报告"] = report(ReportReq(
                estimate_json=json.dumps(d, ensure_ascii=False)))["报告"]
        except Exception as e:  # noqa: BLE001
            d["报告"] = "交付说明生成失败：%s" % str(e)[:120]
        job.update(status="done", step="完成", result=d,
                   耗时_seconds=round(time.time() - t0, 1),
                   finished=time.time())
        with JOB_LOCK:
            JOB_ORDER.append(jid)
            del JOB_ORDER[:-30]
    except BaseException as e:  # noqa: BLE001
        job.update(status="error", step="失败", error=str(e)[:300],
                   trace=traceback.format_exc()[-800:],
                   耗时_seconds=round(time.time() - t0, 1), finished=time.time())
    finally:
        ACTIVE[0] = None


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    p = os.path.join(WEB_DIR, "index.html")
    if not os.path.exists(p):
        raise HTTPException(500, "前端页面缺失：%s" % p)
    return HTMLResponse(open(p, encoding="utf-8").read())


@app.get("/static/{name}", include_in_schema=False)
def static_file(name: str):
    if name not in ("app.css", "app.js"):
        raise HTTPException(404, "没有这个静态文件")
    return FileResponse(os.path.join(WEB_DIR, name))


@app.get("/api/library", summary="知识库底数（给前端首页显示用）")
def api_library():
    lib = os.path.join(ROOT, "data", "library")
    hist = 0
    p = os.path.join(lib, "历史价格库.json")
    if os.path.exists(p):
        try:
            hist = len(json.load(open(p, encoding="utf-8")))
        except Exception:  # noqa: BLE001
            hist = 0
    memo = 0
    p = os.path.join(lib, "网价入库.jsonl")
    if os.path.exists(p):
        memo = sum(1 for line in open(p, encoding="utf-8") if line.strip())
    db_rows = 0
    p = os.path.join(lib, "入库数据.sqlite")
    if os.path.exists(p):
        try:
            import sqlite3
            con = sqlite3.connect(p)
            db_rows = con.execute("SELECT COUNT(*) FROM price_rows").fetchone()[0]
            con.close()
        except Exception:  # noqa: BLE001
            db_rows = 0
    web = 0
    p = os.path.join(lib, "网价缓存.sqlite")
    if os.path.exists(p):
        try:
            import sqlite3
            con = sqlite3.connect(p)
            web = con.execute(
                "SELECT COUNT(*) FROM webprice WHERE payload LIKE '%\"found\": true%'"
            ).fetchone()[0]
            con.close()
        except Exception:  # noqa: BLE001
            web = 0
    return {"材料库": db_rows, "历史报价": hist, "网价入库": memo,
            "联网缓存": web, "合计": db_rows + hist + memo,
            "地区": "陕西"}


@app.post("/api/jobs", summary="提交一份清单开始测算（网页用）")
def api_new_job(
    file: UploadFile = File(..., description="清单 xlsx"),
    bg_file: Optional[UploadFile] = File(None, description="项目背景/技术方案（可选）"),
    note: str = Form("", description="备注（可选）"),
    project_name: str = Form("", description="项目名称（可选，留空取清单标题）"),
    region: str = Form("陕西"),
    mode: str = Form("quote", description="quote=出六件套；ingest=只入库"),
):
    if ACTIVE[0]:
        raise HTTPException(409, "正在跑一份清单，跑完再提交下一份")
    jid = uuid.uuid4().hex[:12]
    work = os.path.join(IN_DIR, "_web", jid)
    os.makedirs(work, exist_ok=True)
    # 顺手清一下 14 天前的网页上传件，别让 data/input 越攒越大
    try:
        root_web = os.path.join(IN_DIR, "_web")
        cut = time.time() - 14 * 86400
        for d in os.listdir(root_web):
            p = os.path.join(root_web, d)
            if d != jid and os.path.isdir(p) and os.path.getmtime(p) < cut:
                shutil.rmtree(p, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    boq_name = _safe_upload_name(file.filename, ".xlsx")
    boq = os.path.join(work, boq_name)
    with open(boq, "wb") as f:
        shutil.copyfileobj(file.file, f)
    file.file.close()
    bg_path = ""
    if bg_file is not None:
        bg_path = os.path.join(work, _safe_upload_name(bg_file.filename, ".txt"))
        with open(bg_path, "wb") as f:
            shutil.copyfileobj(bg_file.file, f)
        bg_file.file.close()
    # 和 /run_all 一套口径：备注里写「入库」就只入库，不出测算
    want_ingest = (mode == "ingest") or ("入库" in (note or ""))
    want_quote = ("测算" in (note or "")) or ("六件套" in (note or "")) \
        or ("四件套" in (note or "")) or not (note or "").strip()
    if want_ingest and not want_quote:
        from engine import ingest as ing
        hint = "定额数据" if "定额" in note else (
            "价格数据" if ("价格" in note or "报价" in note) else "")
        rep = ing.ingest(boq, hint)
        return {"job_id": "", "模式": "入库", "入库报告": rep,
                "说明": "已按「只入库」处理，没有出测算文件；下次测算会直接命中这些价。"}
    ACTIVE[0] = jid
    JOBS[jid] = {"id": jid, "status": "queued", "step": "排队中",
                 "清单文件名": boq_name,
                 "项目名称": project_name, "提交时间": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "轨迹": []}
    over = {k: v for k, v in {"项目名称": project_name, "地区": region}.items() if v}
    threading.Thread(target=_run_job, args=(jid, boq, bg_path, note, over),
                     name="job-%s" % jid, daemon=True).start()
    return {"job_id": jid}


@app.get("/api/jobs/{jid}", summary="查任务进度 / 取结果")
def api_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "没有这个任务")
    return job


@app.get("/api/jobs/{jid}/download", summary="下载这份清单的六件套 Excel")
def api_job_download(jid: str):
    job = JOBS.get(jid) or {}
    res = job.get("result") or {}
    p = res.get("四件套文件") or ""
    if not p or not os.path.exists(p):
        raise HTTPException(404, "文件还没生成或已被移动")
    return FileResponse(p, filename=os.path.basename(p),
                        media_type="application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet")


@app.get("/api/recent", summary="最近跑过的清单")
def api_recent():
    out = []
    for jid in reversed(JOB_ORDER[-12:]):
        j = JOBS.get(jid) or {}
        r = j.get("result") or {}
        out.append({"id": jid, "项目": r.get("项目名称") or j.get("清单文件名"),
                    "时间": j.get("提交时间"), "秒": j.get("耗时_seconds"),
                    "总计": (r.get("甲供C30版") or {}).get("总计")})
    return {"最近": out}


if __name__ == "__main__":
    import argparse

    import uvicorn

    # 用 pythonw（无窗口）启动时 sys.stdout/stderr 是 None，日志会报错，这里转存到文件
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(os.path.join(ROOT, "data", "tmp"), exist_ok=True)
        _log = open(os.path.join(ROOT, "data", "tmp", "server.log"), "a",
                    encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or _log
        sys.stderr = sys.stderr or _log

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=18080)
    a = ap.parse_args()
    print("成本测算引擎服务启动： http://%s:%d/docs" % (a.host, a.port))
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
