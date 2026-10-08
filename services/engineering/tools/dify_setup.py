# -*- coding: utf-8 -*-
"""全自动配置 Dify：登录 → 注册自定义工具 → 配外部知识库 → 建工作流应用。

用法：  .venv\\Scripts\\python.exe tools\\dify_setup.py [--step tool|kb|app|all]
凭据从 .env 读（DIFY_EMAIL / DIFY_PASSWORD / RAGFLOW_DATASET_ID）。
"""
import argparse
import base64
import http.cookiejar
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = "http://127.0.0.1"
ENGINE = "http://host.docker.internal:18080"
RAGFLOW_DATASET = os.environ.get("RAGFLOW_DATASET_ID",
                                 "5ff45c20b72511f1a67d53208e003dfe")


class Dify:
    def __init__(self, email, password):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        pw = base64.b64encode(password.encode()).decode()
        self._call("/console/api/login",
                   {"email": email, "password": pw, "language": "zh-Hans",
                    "remember_me": True}, method="POST", raw=True)
        self.token = [c.value for c in self.jar if c.name == "access_token"][0]
        self.csrf = [c.value for c in self.jar if c.name == "csrf_token"][0]

    def _call(self, path, payload=None, method="GET", raw=False):
        headers = {"Authorization": "Bearer " + getattr(self, "token", ""),
                   "X-CSRF-Token": getattr(self, "csrf", ""),
                   "Content-Type": "application/json"}
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        with self.opener.open(req, timeout=120) as r:
            txt = r.read().decode()
        if raw:
            return txt
        return json.loads(txt) if txt.strip() else {}


def register_tool(d):
    """把引擎服务的 OpenAPI 注册成 Dify 自定义工具。"""
    # 本机取 schema 用 127.0.0.1；写进 Dify 的 servers 地址用容器能访问的 host.docker.internal
    with urllib.request.urlopen("http://127.0.0.1:18080/openapi.json", timeout=30) as r:
        schema = json.load(r)
    schema["servers"] = [{"url": ENGINE, "description": "成本测算引擎（本机）"}]
    payload = {
        "provider": "cost-engine",
        "icon": {"background": "#E4FBCC", "content": "🧮"},
        "credentials": {"auth_type": "none"},
        "schema_type": "openapi",
        "schema": json.dumps(schema, ensure_ascii=False),
        "privacy_policy": "",
        "custom_disclaimer": "",
        "labels": [],
    }
    try:
        d._call("/console/api/workspaces/current/tool-provider/api/add",
                payload, method="POST")
        print("  自定义工具已注册：cost-engine（7 个接口）")
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:80]
        try:
            msg = e.read().decode()[:160]
        except Exception:
            pass
        if "already" in msg or "exist" in msg:
            d._call("/console/api/workspaces/current/tool-provider/api/update",
                    dict(payload, original_provider="cost-engine"), method="POST")
            print("  自定义工具已存在 → 已更新")
        else:
            print("  注册失败：%s" % msg)


def setup_kb(d):
    """配置外部知识库 API，并把 RAGFlow 的库挂进来。"""
    apis = d._call("/console/api/datasets/external-knowledge-api?page=1&limit=50")
    items = apis.get("data") or []
    hit = next((x for x in items if x.get("name") == "成本测算知识库API"), None)
    settings = {"endpoint": ENGINE, "api_key": "ragflow-key"}
    if hit:
        api_id = hit["id"]
        d._call("/console/api/datasets/external-knowledge-api/" + api_id,
                {"name": "成本测算知识库API", "settings": settings}, method="PUT")
        print("  外部知识库 API 已存在 → 已更新")
    else:
        r = d._call("/console/api/datasets/external-knowledge-api",
                    {"name": "成本测算知识库API", "settings": settings}, method="POST")
        api_id = r["id"]
        print("  外部知识库 API 已创建 id=%s" % api_id)

    ds = d._call("/console/api/datasets?page=1&limit=50")
    names = [x.get("name") for x in (ds.get("data") or [])]
    if "成本测算资料库" in names:
        print("  外部知识库绑定已存在，跳过")
        return api_id
    r = d._call("/console/api/datasets/external", {
        "external_knowledge_api_id": api_id,
        "external_knowledge_id": RAGFLOW_DATASET,
        "name": "成本测算资料库",
        "description": "历年报价单、项目清单、定额节选（后端是 RAGFlow）",
        "external_retrieval_model": {"top_k": 5, "score_threshold": 0.1,
                                     "score_threshold_enabled": True},
    }, method="POST")
    print("  外部知识库绑定完成：%s" % r.get("id"))
    return api_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all")
    a = ap.parse_args()
    env = dict()
    if os.path.exists(os.path.join(ROOT, ".env")):
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    email = os.environ.get("DIFY_EMAIL") or env.get("DIFY_EMAIL") or ""
    password = os.environ.get("DIFY_PASSWORD") or env.get("DIFY_PASSWORD") or ""
    if not (email and password):
        sys.exit("缺 Dify 账号：在项目根目录 .env 里写 DIFY_EMAIL / DIFY_PASSWORD，"
                 "或设成同名环境变量后再跑。")
    d = Dify(email, password)
    print("已登录 Dify：%s" % email)
    if a.step in ("tool", "all"):
        print("① 注册自定义工具")
        register_tool(d)
    if a.step in ("kb", "all"):
        print("② 配置外部知识库（Dify → 引擎 → RAGFlow）")
        setup_kb(d)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
