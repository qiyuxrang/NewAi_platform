# -*- coding: utf-8 -*-
"""把项目文档灌进 RAGFlow 知识库（建库 → 上传 → 触发解析）。

用法：  .venv\\Scripts\\python.exe tools\\ragflow_ingest.py [--batch 1|2]
Key 从环境变量 RAGFLOW_API_KEY 或 .env 读取。
"""
import argparse
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = "http://127.0.0.1:8080/api/v1"

RAGFLOW_API_KEY = os.environ.get("RAGFLOW_API_KEY", "").strip()

KB = "成本测算资料库"

BATCH1 = [
    r"C:\Users\123\Documents\xwechat_files\wxid_5r77z7p0y51t22_beab\msg\file\2026-09\基础要求(1).docx",
    r"C:\Users\123\Documents\xwechat_files\wxid_5r77z7p0y51t22_beab\msg\file\2026-09\报价清单--照明9.4.xlsx",
    r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\报价清单\2026-榆林市公安局交警支队经济技术开发区大队道路监控卡口改造项目报价单.xlsx",
    r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\报价清单\劳务报价清单.xlsx",
    r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\工程量清单\2025-337神盘项目劳务机电1.23.xlsx",
    r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\工程量清单\2024-府谷高新产业园区智慧园区供货内容一览表.xlsx",
    r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\供应商库\供应商库.xlsx",
]

BATCH2 = [
    r"C:\Users\123\Desktop\计价定额标准_Word版\P020250321392720342372\各专业工程消耗量定额\10.陕西省市政工程消耗量定额\第八册 路灯工程.docx",
    r"C:\Users\123\Desktop\计价定额标准_Word版\P020250321392720342372\各专业工程消耗量定额\9.陕西省通用安装工程消耗量定额\第四册 电气设备与线缆安装工程.docx",
    r"C:\Users\123\Desktop\计价定额标准_Word版\P020250321392720342372\各专业工程消耗量定额\9.陕西省通用安装工程消耗量定额\第五册 建筑智能化工程.docx",
    r"C:\Users\123\Desktop\计价定额标准_Word版\P020250321392720342372\各专业工程消耗量定额\9.陕西省通用安装工程消耗量定额\第十一册 信息通信设备与线缆安装工程.docx",
]


def headers():
    return {"Authorization": "Bearer " + RAGFLOW_API_KEY}


def ensure_dataset(name):
    r = requests.get(BASE + "/datasets", headers=headers(),
                     params={"page_size": 100}, timeout=30)
    r.raise_for_status()
    for d in r.json().get("data") or []:
        if d.get("name") == name:
            return d["id"]
    # 不指定 embedding_model，用 RAGFlow 里已配好的默认模型
    r = requests.post(BASE + "/datasets", headers=headers(),
                      json={"name": name, "chunk_method": "naive",
                            "language": "Chinese"}, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["id"]


def list_docs(ds):
    r = requests.get("%s/datasets/%s/documents" % (BASE, ds), headers=headers(),
                     params={"page_size": 200}, timeout=30)
    r.raise_for_status()
    return {d["name"]: d["id"] for d in (r.json().get("data") or {}).get("docs", [])}


def upload(ds, path):
    with open(path, "rb") as f:
        r = requests.post("%s/datasets/%s/documents" % (BASE, ds), headers=headers(),
                          files={"file": (os.path.basename(path), f)}, timeout=300)
    r.raise_for_status()
    return r.json()


def parse(ds, ids):
    if not ids:
        return 0, "没有可解析的文档"
    r = requests.post("%s/datasets/%s/chunks" % (BASE, ds), headers=headers(),
                      json={"document_ids": ids}, timeout=120)
    return r.status_code, r.text[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="1")
    a = ap.parse_args()
    files = BATCH1 if a.batch == "1" else BATCH2
    if not RAGFLOW_API_KEY:
        raise SystemExit("缺 RAGFLOW_API_KEY（放环境变量或 .env）")

    ds = ensure_dataset(KB)
    print("知识库：%s  id=%s" % (KB, ds))
    known = list_docs(ds)
    new_ids = []
    for p in files:
        if not os.path.exists(p):
            print("  跳过（不存在）：%s" % os.path.basename(p))
            continue
        name = os.path.basename(p)
        if name in known:
            print("  已存在：%s" % name)
            continue
        try:
            upload(ds, p)
            print("  已上传：%s" % name)
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            print("  上传失败 %s：%s" % (name, str(e)[:80]))
    known = list_docs(ds)
    new_ids = list(known.values())
    code, msg = parse(ds, new_ids)
    print("触发解析：HTTP %s %s" % (code, msg))
    print("库内文档合计 %d 份" % len(known))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
