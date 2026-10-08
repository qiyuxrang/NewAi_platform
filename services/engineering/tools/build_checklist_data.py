# -*- coding: utf-8 -*-
"""生成『待人工确认清单』所需的数据，输出 JSON。只读源数据。"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = os.path.join(ROOT, "data", "tmp", "device_prices.json")
OUT = os.path.join(ROOT, "data", "tmp", "checklist_data.json")

PROJECT_ORDER = ["336项目（一标段）", "336项目（二标段）", "安康北项目", "北客站项目", "店红路项目"]

# 已判定的疑点（人工核对确认过的明显异常）
SUSPECT = {
    312000.0: "与『门架式情报板 12*2』完全同价同供应商。车道费额显示器通常 1~3 万，疑为复制错误",
    206701.95: "ONU 设备通常几千元；带两位小数，疑为包价按比例分摊，非单价",
    200000.0: "规格写『详见图纸要求』，无从核对；请确认是否为网管系统包价",
}


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


def spec_problem(spec):
    s = (spec or "").strip()
    if not s:
        return "规格为空"
    if re.search(r"详见图纸|详见设计|按图纸|见附图|详见", s):
        return "指向图纸，不可定位"
    if len(s) > 60:
        return "长描述（超60字），需提炼关键参数"
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = json.load(open(PRICES, encoding="utf-8"))

    # ① 项目年度
    years = []
    for p in PROJECT_ORDER:
        n = sum(1 for r in rows if r["项目"] == p)
        years.append({"项目": p, "记录数": n, "年份": "", "备注": ""})

    # ② 异常单价（>10万）
    abnormal = []
    for r in sorted([x for x in rows if x["单价"] > 100000], key=lambda x: -x["单价"]):
        note = SUSPECT.get(r["单价"], "单价较大，请确认是单价而非包价")
        abnormal.append({
            "序号": r["序号"], "项目": r["项目"], "设备名称": r["设备名称"],
            "规格参数": r["规格参数"], "单价": r["单价"], "供应商": r["供应商"],
            "疑点": note,
            "判定": "高度可疑" if r["单价"] in SUSPECT else "需确认",
        })

    # ③ + ④ 供应商分类与归一复核（合并为一张，避免重复劳动）
    cnt = collections.Counter(r["供应商"] for r in rows if r["供应商"] != "未标注")
    examples = collections.defaultdict(list)
    for r in rows:
        if len(examples[r["供应商"]]) < 2:
            examples[r["供应商"]].append(r["设备名称"])
    raw_map = collections.defaultdict(collections.Counter)
    for r in rows:
        raw_map[r["供应商"]][r["供应商_原文"]] += 1

    # 仅列出可确定为设备品牌的名称；其余多为厂家或代理
    BRANDS = {"华为", "海康威视", "宇视", "欧姆龙", "奇安信", "浪潮", "大唐保镖", "德亚"}

    def suggest(name):
        return "品牌" if name in BRANDS else "供货商/厂家"

    review = []
    for name, n in cnt.most_common():
        ctr = raw_map[name]
        review.append({
            "供应商（标准名）": name,
            "记录数": n,
            "涉及设备示例": "、".join(examples[name]),
            "原表写法": " / ".join(ctr.keys()),
            "原写法种数": len(ctr),
            "预判": suggest(name),
            "确认（品牌/供货商）": "",
            "归一是否正确": "",
        })
    review.append({"供应商（标准名）": "未标注", "记录数": 2, "涉及设备示例": "",
                   "原表写法": "（原表备注为空）", "原写法种数": 0,
                   "预判": "需补录", "确认（品牌/供货商）": "", "归一是否正确": ""})

    # ⑤ 规格待补充
    spec_rows = []
    for r in rows:
        prob = spec_problem(r["规格参数"])
        if prob:
            spec_rows.append({
                "序号": r["序号"], "项目": r["项目"], "设备名称": r["设备名称"],
                "规格参数（原表）": r["规格参数"] or "（空）",
                "单价": r["单价"], "供应商": r["供应商"],
                "问题类型": prob, "补充后规格": "",
            })

    data = {"项目年度": years, "异常单价": abnormal,
            "供应商复核": review, "规格待补充": spec_rows}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for k, v in data.items():
        print("%-10s %d 条" % (k, len(v)))
    print("→", OUT)


if __name__ == "__main__":
    main()
