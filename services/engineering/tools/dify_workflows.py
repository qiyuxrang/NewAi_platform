# -*- coding: utf-8 -*-
"""一次生成两条 Dify 工作流并试跑发布：

  ① 快线（应用「成本测算 Agent」）        —— 5 个节点，秒级出四件套
  ② 拆分线（应用「成本测算 Agent（全流程·拆分版）」） —— 13 个节点，每一步都能看见

用法：
    .venv\\Scripts\\python.exe tools\\dify_workflows.py [--file 清单.xlsx] [--line fast|split|both]
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dify_setup import Dify  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID_FILE = os.path.join(ROOT, "data", "tmp", "dify_app_id.txt")
PROVIDER_ID = "0f4d0002-e58a-4424-8043-433176c83af9"
DATASET_ID = os.environ.get("DIFY_KB_DATASET_ID", "d9715f59-80d0-4a9f-92d9-e459ed163503")
ENGINE = "http://host.docker.internal:18080"
SPLIT_APP_NAME = "成本测算 Agent（全流程·拆分版）"

START_VARS = [
    {"variable": "boq_file", "label": "① 设备/工程量清单（必须）", "type": "file",
     "required": True, "hint": "支持 .xlsx / .xlsm",
     "allowed_file_types": ["document"], "allowed_file_extensions": [".xlsx", ".xlsm"],
     "allowed_file_upload_methods": ["local_file", "remote_url"],
     "options": [], "placeholder": ""},
    {"variable": "bg_file", "label": "② 项目要求/背景/技术方案（含劳务时必填）",
     "type": "file", "required": False,
     "hint": "招标文件、技术要求、施工方案、施组等；背景里写到的施工条件才会加修正系数",
     "allowed_file_types": ["document"], "allowed_file_extensions": [],
     "allowed_file_upload_methods": ["local_file", "remote_url"],
     "options": [], "placeholder": ""},
    {"variable": "note", "label": "③ 其他/备注（可选）", "type": "paragraph",
     "required": False, "max_length": 2000, "options": [],
     "hint": "写「入库」=只入库；写「确认」=直接出四件套；留空=先出项目理解卡等你确认。",
     "placeholder": "例：确认；本项目边通车施工，主要设备甲供，甲方不提供C30",
     "default": ""},
]


def node(nid, ntype, title, x, y, **data):
    d = {"type": ntype, "title": title, "desc": "", "selected": False}
    d.update(data)
    return {"id": nid, "type": "custom", "data": d,
            "position": {"x": x, "y": y}, "positionAbsolute": {"x": x, "y": y},
            "width": 244, "height": 116, "sourcePosition": "right",
            "targetPosition": "left", "zIndex": 0, "selected": False}


def edge(src, dst, src_type, dst_type, handle="source", eid=None):
    return {"id": eid or ("e-%s-%s-%s" % (src, dst, handle)),
            "source": src, "target": dst, "sourceHandle": handle, "targetHandle": "target",
            "type": "custom",
            "data": {"isInIteration": False, "isInLoop": False, "sourceType": src_type,
                     "targetType": dst_type, "loop_id": None, "iteration_id": None}}


def http_node(nid, title, path, x, y, fields, desc="", timeout=1800, retry=True):
    """fields: [(id, key, kind, value)]，kind ∈ text|file。"""
    data = []
    for fid, key, kind, value in fields:
        if kind == "file":
            data.append({"id": fid, "key": key, "type": "file", "file": value, "value": ""})
        else:
            data.append({"id": fid, "key": key, "type": "text", "file": [], "value": value})
    return node(nid, "http-request", title, x, y, desc=desc,
                method="post", url=ENGINE + path, headers="", params="",
                authorization={"type": "no-auth", "config": None},
                body={"type": "form-data", "data": data},
                timeout={"connect": 60, "read": timeout, "write": 120,
                         "max_connect_timeout": 120, "max_read_timeout": timeout,
                         "max_write_timeout": 120},
                retry_config={"retry_enabled": retry, "max_retries": 3,
                              "retry_interval": 3000},
                ssl_verify=False)


def code_node(nid, title, x, y, code, variables, outputs):
    return node(nid, "code", title, x, y, code=code, code_language="python3",
                variables=[{"variable": k, "value_selector": v} for k, v in variables],
                outputs={k: {"type": t, "children": None} for k, t in outputs})


def kb_node(nid, title, x, y, query_selector):
    return node(nid, "knowledge-retrieval", title, x, y,
                query_variable_selector=query_selector,
                metadata_filtering_mode="disabled", metadata_filtering_conditions=None,
                retrieval_mode="multiple", single_retrieval_config=None,
                multiple_retrieval_config={
                    "top_k": 5, "score_threshold": 0.1, "reranking_enable": False,
                    "reranking_mode": "weighted_score", "reranking_model": None,
                    "weights": {"vector_setting": {
                        "vector_weight": 0.3,
                        "embedding_provider_name": "langgenius/tongyi/tongyi",
                        "embedding_model_name": "text-embedding-v3"},
                        "keyword_setting": {"keyword_weight": 0.7}}},
                dataset_ids=[DATASET_ID])


def if_else_node(nid, title, x, y, conditions, desc=""):
    return node(nid, "if-else", title, x, y, desc=desc,
                cases=[{"case_id": "true", "id": "true", "logical_operator": "and",
                        "conditions": conditions}])


def cond(cid, selector, value, op="is", var_type="string"):
    return {"id": cid, "varType": var_type, "variable_selector": selector,
            "comparison_operator": op, "value": value}


def start_node():
    return node("start_node", "start", "开始", 60, 320,
                variables=START_VARS, desc="输入三个：清单（必须）、背景/技术方案（可选）、备注")


# ────────────────────────────── 快线（5 节点）──────────────────────────────
def graph_fast():
    kb = kb_node("kb_node", "历史做法检索", 60, 60, ["start_node", "note"])
    run = http_node("upload_node", "六件套测算", "/run_all", 420, 320, [
        ("f1", "file", "file", ["start_node", "boq_file"]),
        ("f2", "bg_file", "file", ["start_node", "bg_file"]),
        ("f3", "note", "text", "{{#start_node.note#}}"),
        ("f4", "region", "text", "陕西"),
        ("f5", "measure_per_unit", "text", "295"),
        ("f6", "c30_volume", "text", "0"),
    ], desc="一个 Excel 六张表：设备清单 / 劳务清单 / 成本测算(库+网) / 成本测算(纯网) "
            "/ 劳务报价(库+网) / 劳务报价(纯网)")
    report = node("llm_node", "tool", "生成交付说明", 820, 320,
                  desc="引擎侧出中文交付说明（含导出目录与文件名）",
                  provider_id=PROVIDER_ID, provider_type="api", provider_name="cost-engine",
                  tool_name="report_report_post", tool_label="生成测算报告",
                  tool_parameters={
                      "estimate_json": {"type": "variable", "value": ["upload_node", "body"]},
                      "query": {"type": "variable", "value": ["start_node", "note"]},
                      "knowledge_id": {"type": "mixed", "value": ""},
                      "background": {"type": "variable", "value": ["start_node", "note"]}},
                  tool_configurations={}, is_team_authorization=False)
    end = node("end_node", "end", "结束", 1180, 320, outputs=[
        {"variable": "交付说明", "value_selector": ["llm_node", "text"]},
        {"variable": "六件套结果", "value_selector": ["upload_node", "body"]}])
    sync = http_node("sync_node", "知识库同步", "/sync_kb", 1010, 320, [
        ("h1", "path", "text", "{{#upload_node.body#}}"),
    ], desc="把本次过筛的网价回写企业知识库，下次直接命中；节点会从返回 JSON 里自动取文件路径",
        retry=False)
    nodes = [start_node(), kb, run, sync, report, end]
    edges = [
        edge("start_node", "kb_node", "start", "knowledge-retrieval"),
        edge("kb_node", "upload_node", "knowledge-retrieval", "http-request"),
        edge("upload_node", "sync_node", "http-request", "http-request"),
        edge("sync_node", "llm_node", "http-request", "tool"),
        edge("llm_node", "end_node", "tool", "end"),
    ]
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.85}}


# ───────────────────── 拆分线（13 节点，全流程可视化）─────────────────────
SPLIT_CODE = '''def main(note: str) -> dict:
    n = (note or "").strip()
    if "入库" in n and "测算" not in n and "六件套" not in n:
        return {"mode": "入库", "reason": "备注写了「入库」，本次只入库不出测算"}
    if "只看理解卡" in n or "先看理解卡" in n:
        return {"mode": "待确认", "reason": "按备注要求本次只出理解卡"}
    return {"mode": "出四件套", "reason": "全自动：直接出六件套（备注留空 = 默认出结果）"}
'''

PARSE_CODE = '''import json


def main(raw: str) -> dict:
    try:
        d = json.loads(raw or "{}")
    except Exception:
        return {"path": "", "summary": "未能解析测算结果"}
    a = d.get("甲供C30版") or {}
    b = d.get("不提供C30版") or {}
    ok = d.get("校验") or {}
    env = d.get("环境修正") or {}
    net = d.get("纯网报价") or {}
    hc = d.get("取价健康度") or {}
    lines = [
        "项目：%s" % d.get("项目名称", ""),
        "甲供C30版：%.2f 万元（%.0f 元/单位）"
        % ((a.get("总计") or 0) / 10000.0, a.get("每单位") or 0),
        "纯网络检索口径：%.2f 万元（%.0f 元/单位）"
        % ((net.get("总计") or 0) / 10000.0, net.get("每单位") or 0),
        "甲方不提供C30版：%.2f 万元（%.0f 元/单位）"
        % ((b.get("总计") or 0) / 10000.0, b.get("每单位") or 0),
        "环境与条件修正：%.1f%%（命中 %s）"
        % ((env.get("系数") or 0) * 100, "、".join(env.get("命中") or []) or "无"),
        "供应归属：%s" % json.dumps(d.get("供应归属清点") or {}, ensure_ascii=False),
        "导出目录：%s" % d.get("导出目录", ""),
        "文件：%s" % "、".join(d.get("导出文件") or []),
        "自检：%s/%s 项通过" % (ok.get("通过数"), ok.get("总检查")),
        "取价健康度：%s｜命中率 %.0f%%（%s 行里 %s 行无价）"
        % (hc.get("结论"), (hc.get("命中率") or 0) * 100,
           hc.get("行数"), hc.get("零价项")),
    ]
    for w in (hc.get("警告") or []):
        lines.append("　⚠ " + w)
    return {"path": d.get("四件套文件", ""), "summary": "\\n".join(lines)}
'''

FINAL_CODE = '''import json


def main(summary: str, checkup: str, syncinfo: str = "") -> dict:
    parts = ["【六件套已生成】一个 Excel、六张表："
             "①设备清单 ②劳务清单 ③成本测算（库+网检索）④成本测算（纯网检索）"
             "⑤劳务报价（库+网检索）⑥劳务报价（纯网检索）\\n"
             "⑤⑥为劳务分包对外总包报价，已含降效 6% / 风险 4% / 管理费 10% / 税金 3%，"
             "单价与合价无空白。",
             summary or ""]
    if checkup:
        parts.append("【通用校验】" + checkup[:900])
    try:
        s = json.loads(syncinfo or "{}")
        if s.get("可入库") is not None:
            parts.append("【知识库同步】可入库 %s 条（新增 %s / 覆盖 %s），"
                         "被价格带与真实性校验拒绝 %s 条；下次测算先命中历史价"
                         % (s.get("可入库"), s.get("新增"), s.get("覆盖"),
                            s.get("被价格带拒绝")))
    except Exception:
        pass
    return {"text": "\\n\\n".join([p for p in parts if p])}
'''


def graph_split():
    sc = code_node("s1", "①指令分流", 380, 320, SPLIT_CODE,
                   [("note", ["start_node", "note"])],
                   [("mode", "string"), ("reason", "string")])
    gate0 = if_else_node("s1b", "①指令识别", 660, 320,
                         [cond("c-in", ["s1", "mode"], "入库")],
                         desc="命中「入库」走入库通道，其余走测算通道")
    ing = http_node("s2", "②入库通道", "/ingest_file", 700, 100, [
        ("g1", "file", "file", ["start_node", "boq_file"]),
        ("g2", "hint", "text", ""),
    ], desc="识别定额/价格数据并落库，只入库不出测算")
    und = http_node("s3", "③背景理解卡", "/understand", 700, 540, [
        ("g1", "bg_file", "file", ["start_node", "bg_file"]),
        ("g2", "text", "text", "{{#start_node.note#}}"),
    ], desc="从背景/技术方案逐条找依据，没依据的项如实标「未见依据」")
    gate = if_else_node("s4", "④是否只出理解卡", 1020, 540,
                        [cond("c-mode", ["s1", "mode"], "出四件套")],
                        desc="默认全自动出六件套；只有备注写「只看理解卡」才停在这里")
    own = http_node("s5", "⑤供应归属判定", "/ownership", 1340, 420, [
        ("g1", "file", "file", ["start_node", "boq_file"]),
    ], desc="先判清单性质（采购清单 / 工程量清单），再逐项判 A甲供 B我方采购 C辅材 D劳务自备 E存疑")
    kb = kb_node("s6", "⑥历史做法检索", 1660, 420, ["start_node", "note"])
    run = http_node("s7", "⑦六件套测算", "/run_all", 1980, 420, [
        ("g1", "file", "file", ["start_node", "boq_file"]),
        ("g2", "bg_file", "file", ["start_node", "bg_file"]),
        ("g3", "note", "text", "{{#start_node.note#}}"),
        ("g4", "region", "text", "陕西"),
        ("g5", "measure_per_unit", "text", "295"),
        ("g6", "c30_volume", "text", "0"),
    ], desc="含量库+定额+价格库组价，出六件套并导出到桌面")
    par = code_node("s8", "⑧结果解析", 2300, 420, PARSE_CODE,
                    [("raw", ["s7", "body"])], [("path", "string"), ("summary", "string")])
    chk = http_node("s9", "⑨通用校验", "/checkup", 2620, 420, [
        ("g1", "path", "text", "{{#s8.path#}}"),
        ("g2", "reference", "text", "0"),
    ], desc="Sheet 齐全 / 逐行勾稽 / 字体边框 / 列宽 / ±10% 偏差", retry=False)
    syn = http_node("s9b", "⑩知识库同步", "/sync_kb", 2940, 420, [
        ("h1", "path", "text", "{{#s8.path#}}"),
    ], desc="把本次过真实性校验的网价回写企业知识库，下次直接命中历史价", retry=False)
    fin = code_node("s10", "⑪交付说明", 3260, 420, FINAL_CODE,
                    [("summary", ["s8", "summary"]), ("checkup", ["s9", "body"]),
                     ("syncinfo", ["s9b", "body"])],
                    [("text", "string")])
    agg = node("s11", "variable-aggregator", "⑫结果聚合", 3580, 320,
               output_type="string", advanced_settings={"group_enabled": False, "groups": []},
               variables=[["s10", "text"], ["s2", "body"], ["s3", "body"]])
    end = node("s12", "end", "⑬结束", 3880, 320, outputs=[
        {"variable": "结果", "value_selector": ["s11", "output"]}])
    nodes = [start_node(), sc, gate0, ing, und, gate, own, kb, run, par, chk, syn, fin,
             agg, end]
    edges = [
        edge("start_node", "s1", "start", "code"),
        edge("s1", "s1b", "code", "if-else"),
        edge("s1b", "s2", "if-else", "http-request", handle="true", eid="e-s1b-ing"),
        edge("s1b", "s3", "if-else", "http-request", handle="false", eid="e-s1b-und"),
        edge("s3", "s4", "http-request", "if-else"),
        edge("s4", "s5", "if-else", "http-request", handle="true", eid="e-s4-go"),
        edge("s4", "s11", "if-else", "variable-aggregator", handle="false",
             eid="e-s4-hold"),
        edge("s5", "s6", "http-request", "knowledge-retrieval"),
        edge("s6", "s7", "knowledge-retrieval", "http-request"),
        edge("s7", "s8", "http-request", "code"),
        edge("s8", "s9", "code", "http-request"),
        edge("s9", "s9b", "http-request", "http-request"),
        edge("s9b", "s10", "http-request", "code"),
        edge("s10", "s11", "code", "variable-aggregator"),
        edge("s2", "s11", "http-request", "variable-aggregator", eid="e-s2-agg"),
        edge("s11", "s12", "variable-aggregator", "end"),
    ]
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.7}}


# ────────────────────────────── 通用 ──────────────────────────────
def find_app(d, name):
    for a in d._call("/console/api/apps?page=1&limit=100").get("data", []):
        if a["name"] == name:
            return a["id"]
    r = d._call("/console/api/apps", {"name": name, "mode": "workflow",
                                      "icon": "🧮", "icon_background": "#E4FBCC",
                                      "description": "清单进 → 四件套出（全流程可视化）"},
                method="POST")
    return r.get("id") or (r.get("app") or {}).get("id")


def save_graph(d, app_id, graph):
    payload = {"graph": graph, "features": {}}
    try:
        cur = d._call("/console/api/apps/%s/workflows/draft" % app_id)
        if cur.get("hash"):
            payload["hash"] = cur["hash"]
    except Exception:  # noqa: BLE001
        pass
    d._call("/console/api/apps/%s/workflows/draft" % app_id, payload, method="POST")
    return True


def run_draft(d, app_id, inputs, files=None):
    body = json.dumps({"inputs": inputs, "files": files or []},
                      ensure_ascii=False).encode()
    req = urllib.request.Request(
        "http://127.0.0.1/console/api/apps/%s/workflows/draft/run" % app_id,
        data=body, method="POST",
        headers={"Authorization": "Bearer " + d.token, "X-CSRF-Token": d.csrf,
                 "Content-Type": "application/json", "Accept": "text/event-stream"})
    final, failed = None, []
    with d.opener.open(req, timeout=1800) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                evt = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            et = evt.get("event")
            if et == "node_finished":
                nd = evt.get("data", {})
                mark = "✓" if nd.get("status") == "succeeded" else "✗"
                print("   %s %s (%s)" % (mark, nd.get("title"), nd.get("status")))
                if nd.get("status") != "succeeded":
                    failed.append((nd.get("title"), str(nd.get("error"))[:300]))
            if et == "workflow_finished":
                final = evt.get("data", {})
    return final, failed


def upload_file(d, path):
    boundary = uuid.uuid4().hex
    fname = os.path.basename(path)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        content = f.read()
    head = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: %s\r\n\r\n" % (boundary, fname, ctype)).encode()
    tail = ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        "http://127.0.0.1/console/api/files/upload", data=head + content + tail, method="POST",
        headers={"Authorization": "Bearer " + d.token, "X-CSRF-Token": d.csrf,
                 "Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with d.opener.open(req, timeout=300) as resp:
        return json.load(resp).get("id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=r"data\input\报价清单--照明9.4.xlsx")
    ap.add_argument("--bg", default="")
    ap.add_argument("--note", default="确认：测试跑通")
    ap.add_argument("--line", default="both", choices=["fast", "split", "both"])
    ap.add_argument("--skip-run", action="store_true")
    a = ap.parse_args()

    # 账号从 .env / 环境变量读，不写死在代码里（交付包要能直接发给别人）
    env = {}
    _envp = os.path.join(ROOT, ".env")
    if os.path.exists(_envp):
        for line in open(_envp, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    _email = os.environ.get("DIFY_EMAIL") or env.get("DIFY_EMAIL") or ""
    _pwd = os.environ.get("DIFY_PASSWORD") or env.get("DIFY_PASSWORD") or ""
    if not (_email and _pwd):
        sys.exit("缺 Dify 账号：在项目根目录 .env 里写 DIFY_EMAIL / DIFY_PASSWORD。")
    d = Dify(_email, _pwd)
    print("已登录 Dify")
    app_fast = (open(APP_ID_FILE, encoding="utf-8").read().strip()
                if os.path.exists(APP_ID_FILE) else "") or find_app(d, "成本测算 Agent")
    app_split = find_app(d, SPLIT_APP_NAME)
    print("快线应用 id:", app_fast)
    print("拆分线应用 id:", app_split)

    which = []
    if a.line in ("fast", "both"):
        which.append(("快线（5 节点）", app_fast, graph_fast()))
    if a.line in ("split", "both"):
        which.append(("拆分线（14 节点）", app_split, graph_split()))

    for label, app_id, g in which:
        print("\n【%s】保存草稿：%d 个节点 / %d 条连线"
              % (label, len(g["nodes"]), len(g["edges"])))
        try:
            save_graph(d, app_id, g)
            print("   草稿已保存")
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:80]
            try:
                msg = e.read().decode()[:500]
            except Exception:
                pass
            print("   保存失败：", msg)
            continue
        if a.skip_run:
            continue
        try:
            fid = upload_file(d, a.file)
            inputs = {"note": a.note,
                      "boq_file": {"type": "document", "transfer_method": "local_file",
                                   "upload_file_id": fid}}
            if a.bg:
                inputs["bg_file"] = {"type": "document", "transfer_method": "local_file",
                                     "upload_file_id": upload_file(d, a.bg)}
            print("   试跑中……")
            final, failed = run_draft(d, app_id, inputs)
            if final:
                print("   状态:", final.get("status"),
                      "| 耗时 %.1f 秒" % (final.get("elapsed_time") or 0))
                if final.get("error"):
                    print("   错误:", str(final["error"])[:400])
                for k, v in (final.get("outputs") or {}).items():
                    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                    print("   %s: %s" % (k, s[:400]))
            for t, err in failed:
                print("   失败节点：%s → %s" % (t, err))
            if final and final.get("status") == "succeeded":
                try:
                    d._call("/console/api/apps/%s/workflows/publish" % app_id,
                            {"marked_name": "v2", "marked_comment": label}, method="POST")
                    print("   已发布")
                except Exception as e:  # noqa: BLE001
                    msg = str(e)[:80]
                    try:
                        msg = e.read().decode()[:200]
                    except Exception:
                        pass
                    print("   发布失败：", msg)
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:100]
            try:
                msg = e.read().decode()[:400]
            except Exception:
                pass
            print("   试跑失败：", msg)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
