# -*- coding: utf-8 -*-
"""在 Dify 里搭好『清单进 → 四版测算出』工作流：写草稿 → 试跑 → 发布。

用法：  .venv\\Scripts\\python.exe tools\\dify_workflow.py [--file 清单.xlsx]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dify_setup import Dify  # noqa: E402

APP_ID_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "tmp", "dify_app_id.txt")
PROVIDER_ID = "0f4d0002-e58a-4424-8043-433176c83af9"
TOOL_NAME = "estimate_named_estimate_named_post"
DATASET_ID = "d9715f59-80d0-4a9f-92d9-e459ed163503"      # Dify 里的外部知识库（后端 RAGFlow）
LLM_MODEL = {"name": "qwen3.7-flash", "provider": "langgenius/tongyi/tongyi",
             "completion_params": {"temperature": 0.2}, "mode": "chat"}


REPORT_PROMPT = """你是市政工程成本测算工程师。下面是系统跑出来的四版测算原始数据，
以及从企业知识库检索到的历史做法。请输出一份能给项目经理看的中文报告：

1. 先一行结论：清单名称、需报价项数、甲供剔除项数、①②两队合计、③④劳务合计。
2. 表格列出每一版的明细行（名称/单位/数量/单价/小计/来源）。
3. 单独列出风险与待办：未取到价的项、备注里提示过核减或缺图纸的项。
4. 如果知识库里查到同类项目的历史做法或单价，写一段"参考"。
只讲事实，不要编造数字。

【测算原始数据】
{{#tool_node.text#}}

【知识库检索结果】
{{#kb_node.result#}}
"""


def graph(simple=False):
    if simple:
        g = graph_full()
        keep = {"start_node", "tool_node", "end_node"}
        g["nodes"] = [n for n in g["nodes"] if n["id"] in keep]
        g["edges"] = [{"id": "e-start-tool", "source": "start_node", "target": "tool_node",
                       "sourceHandle": "source", "targetHandle": "target", "type": "custom",
                       "data": {"isInIteration": False, "sourceType": "start",
                                "targetType": "tool"}},
                      {"id": "e-tool-end", "source": "tool_node", "target": "end_node",
                       "sourceHandle": "source", "targetHandle": "target", "type": "custom",
                       "data": {"isInIteration": False, "sourceType": "tool",
                                "targetType": "end"}}]
        for n in g["nodes"]:
            if n["id"] == "end_node":
                n["data"]["outputs"] = [{"variable": "测算结果",
                                         "value_selector": ["tool_node", "text"]}]
        return g
    return graph_full()


def graph_full():
    start = {
        "id": "start_node",
        "type": "custom",
        "data": {
            "type": "start", "title": "开始", "desc": "上传工程量清单（xlsx）",
            "variables": [
                {"variable": "boq_file", "label": "① 设备/工程量清单（必须）", "type": "file",
                 "required": True, "hint": "支持 .xlsx / .xlsm",
                 "allowed_file_types": ["document"], "allowed_file_extensions": [".xlsx", ".xlsm"],
                 "allowed_file_upload_methods": ["local_file", "remote_url"],
                 "options": [], "placeholder": ""},
                {"variable": "bg_file", "label": "② 项目要求/背景/技术方案（含劳务时必填）",
                 "type": "file", "required": False,
                 "hint": "招标文件、技术要求、施工方案、施组等",
                 "allowed_file_types": ["document"], "allowed_file_extensions": [],
                 "allowed_file_upload_methods": ["local_file", "remote_url"],
                 "options": [], "placeholder": ""},
                {"variable": "note", "label": "③ 其他/备注（可选）",
                 "type": "paragraph", "required": False, "max_length": 2000, "options": [],
                 "hint": "说明本次要做什么：写「入库」=只入库；写「出四件套」或留空=出测算；"
                         "也可补充项目背景文字",
                 "placeholder": "例：出四件套；本项目边通车施工，主要设备甲供",
                 "default": ""},
            ],
            "selected": False,
        },
        "position": {"x": 80, "y": 260}, "positionAbsolute": {"x": 80, "y": 260},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    tool = {
        "id": "tool_node",
        "type": "custom",
        "data": {
            "type": "tool", "title": "成本测算引擎", "desc": "调本机引擎跑四版测算",
            "provider_id": PROVIDER_ID, "provider_type": "api",
            "provider_name": "cost-engine", "tool_name": TOOL_NAME,
            "tool_label": "成本测算（按文件名）",
            "tool_parameters": {
                "file_name": {"type": "variable", "value": ["start_node", "file_name"]},
                "out_name": {"type": "mixed", "value": "成本测算_四版.xlsx"},
            },
            "tool_configurations": {}, "is_team_authorization": False, "selected": False,
        },
        "position": {"x": 420, "y": 240}, "positionAbsolute": {"x": 420, "y": 240},
        "width": 244, "height": 150, "sourcePosition": "right", "targetPosition": "left",
    }
    end = {
        "id": "end_node",
        "type": "custom",
        "data": {"type": "end", "title": "结束", "desc": "",
                 "outputs": [{"variable": "测算报告", "value_selector": ["llm_node", "text"]},
                             {"variable": "原始数据", "value_selector": ["upload_node", "body"]}],
                 "selected": False},
        "position": {"x": 1180, "y": 260}, "positionAbsolute": {"x": 1180, "y": 260},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    kb = {
        "id": "kb_node",
        "type": "custom",
        "data": {
            "type": "knowledge-retrieval", "title": "历史做法检索", "desc": "",
            "query_variable_selector": ["start_node", "note"],
            "metadata_filtering_mode": "disabled",
            "metadata_filtering_conditions": None,
            "retrieval_mode": "multiple",
            "single_retrieval_config": None,
            "multiple_retrieval_config": {"top_k": 5, "score_threshold": 0.1,
                                          "reranking_enable": False,
                                          "reranking_mode": "weighted_score",
                                          "reranking_model": None,
                                          "weights": {
                                              "vector_setting": {
                                                  "vector_weight": 0.3,
                                                  "embedding_provider_name": "langgenius/tongyi/tongyi",
                                                  "embedding_model_name": "text-embedding-v3"},
                                              "keyword_setting": {"keyword_weight": 0.7}}},
            "dataset_ids": [DATASET_ID],
            "selected": False,
        },
        "position": {"x": 80, "y": 60}, "positionAbsolute": {"x": 80, "y": 60},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    # upload_node：把上传的清单用 multipart 打给引擎（Dify 原生 HTTP 节点支持文件体）
    upload = {
        "id": "upload_node",
        "type": "custom",
        "data": {
            "type": "http-request", "title": "上传清单测算", "desc": "",
            "method": "post",
            "url": "http://host.docker.internal:18080/run_all",
            "headers": "",
            "params": "",
            "authorization": {"type": "no-auth", "config": None},
            "body": {"type": "form-data", "data": [
                {"id": "f1", "key": "file", "type": "file",
                 "file": ["start_node", "boq_file"], "value": ""},
                {"id": "f2", "key": "out_name", "type": "text",
                 "file": [], "value": "成本测算_四版.xlsx"},
                {"id": "f3", "key": "region", "type": "text",
                 "file": [], "value": "陕西"},
                {"id": "f4", "key": "measure_per_unit", "type": "text",
                 "file": [], "value": "295"},
                {"id": "f6", "key": "note", "type": "text",
                 "file": [], "value": "{{#start_node.note#}}"},
            ]},
            # 大清单冷启动（物料多、要联网取价）可能跑十几分钟，读超时给到最大
            "timeout": {"connect": 60, "read": 1800, "write": 120,
                        "max_connect_timeout": 120, "max_read_timeout": 1800,
                        "max_write_timeout": 120},
            # 引擎重启/网络瞬断时自动重试，避免"Zero Sized Reply"这类 502 直接判失败
            "retry_config": {"retry_enabled": True, "max_retries": 3, "retry_interval": 3000},
            "ssl_verify": False,
            "selected": False,
        },
        "position": {"x": 420, "y": 240}, "positionAbsolute": {"x": 420, "y": 240},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    # 报告这步放引擎侧（/report：百炼 + RAGFlow 检索），Dify 不用配模型
    lamp = {
        "id": "lamp_node",
        "type": "custom",
        "data": {
            "type": "tool", "title": "生成项目六件套", "desc": "设备清单/劳务清单/两版报价等",
            "provider_id": PROVIDER_ID, "provider_type": "api",
            "provider_name": "cost-engine", "tool_name": "lamp_quote_lamp_quote_post",
            "tool_label": "太阳能路灯六件套",
            "tool_parameters": {}, "tool_configurations": {}, "is_team_authorization": False,
            "selected": False,
        },
        "position": {"x": 640, "y": 440}, "positionAbsolute": {"x": 640, "y": 440},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    llm = {
        "id": "llm_node",
        "type": "custom",
        "data": {
            "type": "tool", "title": "生成测算报告", "desc": "引擎侧出中文报告",
            "provider_id": PROVIDER_ID, "provider_type": "api",
            "provider_name": "cost-engine", "tool_name": "report_report_post",
            "tool_label": "生成测算报告",
            "tool_parameters": {
                "estimate_json": {"type": "variable", "value": ["upload_node", "body"]},
                "query": {"type": "variable", "value": ["start_node", "query_text"]},
                "knowledge_id": {"type": "mixed", "value": ""},
                "background": {"type": "variable", "value": ["start_node", "background_text"]},
            },
            "tool_configurations": {}, "is_team_authorization": False, "selected": False,
        },
        "position": {"x": 820, "y": 240}, "positionAbsolute": {"x": 820, "y": 240},
        "width": 244, "height": 116, "sourcePosition": "right", "targetPosition": "left",
    }
    edges = [
        {"id": "e-start-kb", "source": "start_node", "target": "kb_node",
         "sourceHandle": "source", "targetHandle": "target", "type": "custom",
         "data": {"isInIteration": False, "sourceType": "start", "targetType": "knowledge-retrieval"}},
        {"id": "e-kb-up", "source": "kb_node", "target": "upload_node",
         "sourceHandle": "source", "targetHandle": "target", "type": "custom",
         "data": {"isInIteration": False, "sourceType": "knowledge-retrieval",
                  "targetType": "http-request"}},
        {"id": "e-upload-report", "source": "upload_node", "target": "llm_node",
         "sourceHandle": "source", "targetHandle": "target", "type": "custom",
         "data": {"isInIteration": False, "sourceType": "http-request", "targetType": "tool"}},
        {"id": "e-llm-end", "source": "llm_node", "target": "end_node",
         "sourceHandle": "source", "targetHandle": "target", "type": "custom",
         "data": {"isInIteration": False, "sourceType": "tool", "targetType": "end"}},
    ]
    llm["position"] = {"x": 820, "y": 240}
    llm["positionAbsolute"] = {"x": 820, "y": 240}
    upload["position"] = {"x": 420, "y": 420}
    upload["positionAbsolute"] = {"x": 420, "y": 420}
    tool["position"] = {"x": 150, "y": 420}
    tool["positionAbsolute"] = {"x": 150, "y": 420}
    return {"nodes": [start, kb, upload, llm, end], "edges": edges,
            "viewport": {"x": 0, "y": 0, "zoom": 0.9}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=r"data\input\报价清单--照明9.4.xlsx")
    ap.add_argument("--simple", action="store_true", help="只保留 开始→测算→结束 三步")
    a = ap.parse_args()
    app_id = open(APP_ID_FILE, encoding="utf-8").read().strip()
    # 账号从 .env / 环境变量读（这个脚本是早期单工作流版本，已被 dify_workflows.py 取代）
    _env = {}
    _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_p):
        for line in open(_p, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                _env[k] = v
    _email = os.environ.get("DIFY_EMAIL") or _env.get("DIFY_EMAIL") or ""
    _pwd = os.environ.get("DIFY_PASSWORD") or _env.get("DIFY_PASSWORD") or ""
    if not (_email and _pwd):
        sys.exit("缺 Dify 账号：在项目根目录 .env 里写 DIFY_EMAIL / DIFY_PASSWORD。")
    d = Dify(_email, _pwd)
    print("应用 id:", app_id)

    payload = {"graph": graph(a.simple), "features": {}}
    try:
        cur = d._call("/console/api/apps/%s/workflows/draft" % app_id)
        if cur.get("hash"):
            payload["hash"] = cur["hash"]
    except Exception:
        pass
    try:
        d._call("/console/api/apps/%s/workflows/draft" % app_id, payload, method="POST")
        print("① 工作流草稿已保存")
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:100]
        try:
            msg = e.read().decode()[:400]
        except Exception:
            pass
        print("草稿保存失败:", msg)
        return

    try:
        # 先把清单上传到 Dify，拿到 upload_file_id，再作为文件变量传进工作流
        import urllib.request
        import uuid
        import mimetypes
        path = a.file
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
            up = json.load(resp)
        fid = up.get("id")
        print("已上传清单到 Dify：%s（id=%s）" % (fname, fid))

        # 这个接口是 SSE 流，逐行读事件
        body = json.dumps({
            "inputs": {
                "note": "确认：测试跑通",
                "boq_file": {"type": "document", "transfer_method": "local_file",
                             "upload_file_id": fid},
            },
            "files": [],
        }, ensure_ascii=False).encode()
        req = urllib.request.Request(
            "http://127.0.0.1/console/api/apps/%s/workflows/draft/run" % app_id,
            data=body, method="POST",
            headers={"Authorization": "Bearer " + d.token, "X-CSRF-Token": d.csrf,
                     "Content-Type": "application/json", "Accept": "text/event-stream"})
        print("② 试跑中（走 SSE，可能要 1~3 分钟）……")
        final = None
        with d.opener.open(req, timeout=1200) as resp:
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
                    print("   节点完成：%s" % (evt.get("data", {}).get("title")))
                if et == "workflow_finished":
                    final = evt.get("data", {})
        if final:
            print("   状态:", final.get("status"), "| 耗时 %.1f 秒" % (final.get("elapsed_time") or 0))
            outs = final.get("outputs") or {}
            for k, v in outs.items():
                s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                print("   %s: %s" % (k, s[:220]))
            if final.get("error"):
                print("   错误:", str(final["error"])[:300])
        if final and final.get("status") == "succeeded":
            try:
                d._call("/console/api/apps/%s/workflows/publish" % app_id,
                        {"marked_name": "v1", "marked_comment": "清单进 → 四版测算出"}, method="POST")
                print("③ 已发布为正式版本")
            except Exception as e:  # noqa: BLE001
                msg = str(e)[:80]
                try:
                    msg = e.read().decode()[:200]
                except Exception:
                    pass
                print("   发布失败:", msg)
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:100]
        try:
            msg = e.read().decode()[:400]
        except Exception:
            pass
        print("试跑失败:", msg)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
