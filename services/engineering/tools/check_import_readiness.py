# -*- coding: utf-8 -*-
"""入库就绪度检查：物料归并、规格可用性、单价异常、供应商与品牌混杂情况。只读。"""
import collections
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "data", "tmp", "device_prices.json")
SRC = os.path.join(os.path.expanduser("~"), "Desktop", "供应商库.xlsx")


def norm(s):
    s = "" if s is None else str(s)
    out = []
    for ch in s:
        c = ord(ch)
        if c == 0x3000:
            c = 32
        elif 0xFF01 <= c <= 0xFF5E:
            c -= 0xFEE0
        out.append(chr(c))
    s = "".join(out).replace("*", "x").replace("×", "x").replace("φ", "d").replace("Φ", "d")
    return re.sub(r"\s+", "", s).lower()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = json.load(open(JSON_PATH, encoding="utf-8"))

    print("=" * 78)
    print("一、物料归并（决定入库是几张表）")
    print("=" * 78)
    print("报价记录行数            : %d" % len(rows))
    print("唯一『名称+规格』组合    : %d" % len({(norm(r["设备名称"]), norm(r["规格参数"])) for r in rows}))
    print("唯一『名称』            : %d" % len({norm(r["设备名称"]) for r in rows}))
    print("唯一『供应商+名称+规格』  : %d" % len({(r["供应商"], norm(r["设备名称"]), norm(r["规格参数"])) for r in rows}))
    dup = collections.Counter((norm(r["设备名称"]), norm(r["规格参数"])) for r in rows)
    print("同一物料出现在多个项目的: %d 个" % sum(1 for v in dup.values() if v > 1))

    print("\n" + "=" * 78)
    print("二、物料键的可用性（有多少行能靠名称+规格定位）")
    print("=" * 78)
    empty_spec = [r for r in rows if not r["规格参数"].strip()]
    long_spec = [r for r in rows if len(r["规格参数"]) > 60]
    vague = [r for r in rows if re.search(r"详见图纸|详见设计|按图纸|见附图", r["规格参数"])]
    print("规格为空              : %d 行" % len(empty_spec))
    print("规格超过 60 字（长描述）: %d 行" % len(long_spec))
    print("规格写『详见图纸』类    : %d 行" % len(vague))
    if long_spec:
        r = max(long_spec, key=lambda x: len(x["规格参数"]))
        print("  最长一条: %s | %d 字" % (r["设备名称"], len(r["规格参数"])))
    print("→ 可结构化定位的行      : %d / %d (%.0f%%)" % (
        len(rows) - len(empty_spec) - len(long_spec) - len(vague), len(rows),
        (len(rows) - len(empty_spec) - len(long_spec) - len(vague)) / len(rows) * 100))

    print("\n" + "=" * 78)
    print("三、单价异常")
    print("=" * 78)
    s = sorted(rows, key=lambda r: r["单价"])
    print("最低 5 条:")
    for r in s[:5]:
        print("   %-22s %-30s %10.2f  %s" % (r["设备名称"][:22], r["规格参数"][:30], r["单价"], r["供应商"]))
    print("最高 5 条:")
    for r in s[-5:]:
        print("   %-22s %-30s %10.2f  %s" % (r["设备名称"][:22], r["规格参数"][:30], r["单价"], r["供应商"]))
    print("超过 10 万的行: %d" % sum(1 for r in rows if r["单价"] > 100000))

    print("\n" + "=" * 78)
    print("四、供应商列里混了品牌（入库要拆成两个字段）")
    print("=" * 78)
    sup = sorted({r["供应商"] for r in rows if r["供应商"] != "未标注"})
    # 从供应商库.xlsx 取真实公司名
    known = set()
    for sh in ["1.设备供应商", "2.材料供应商", "3.软件供应商", "4.劳务队供应商"]:
        d = pd.read_excel(SRC, sheet_name=sh, dtype=object)
        for v in d["供应商名称"].dropna():
            v = str(v).strip()
            if v:
                known.add(norm(v))
    hit, miss = [], []
    for a in sup:
        n = norm(a)
        (hit if any(n in k or k in n for k in known) else miss).append(a)
    print("能在『供应商库』里找到对应公司的: %d 家" % len(hit))
    print("找不到的（多为品牌或简称）      : %d 家" % len(miss))
    print("\n找不到的名单:")
    for a in miss:
        print("   " + a)


if __name__ == "__main__":
    main()
