# -*- coding: utf-8 -*-
"""对遗留问题给出结论：异常单价判定为单价还是包价；规格做结构化整理。

输出：data/tmp/issues_resolved.json
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = os.path.join(ROOT, "data", "tmp", "device_prices.json")
OUT = os.path.join(ROOT, "data", "tmp", "issues_resolved.json")

# 逐条判定（按序号）
JUDGE = {
    460: ("单价", "门架式情报板 12×2 米（24㎡），按块计价，31.2 万符合大屏量级"),
    505: ("单价（数值存疑）", "费额显示器按台计价，但 31.2 万与同供应商的门架式情报板分毫不差，疑为复制错误；同类应在 1~3 万"),
    464: ("单价", "窄条式超限检测系统按套计价，含称重传感器与控制器"),
    299: ("包价", "ONU 单价通常几千元；20.67 万还带两位小数，特征符合包价按比例分摊"),
    463: ("包价", "网管系统按项整体报价，20 万为整数，是系统总价而非单台设备价"),
    451: ("单价", "钢结构门架按座计价，含立柱与横撑"),
    267: ("单价", "情报板门架按座计价，跨度 15.85 米"),
    268: ("单价", "情报板门架按座计价，跨度 16.65 米"),
    336: ("单价", "IP SAN 存储阵列按套计价，13.46 万符合企业级存储量级"),
    121: ("包价", "软件平台按项计价，含开发与部署"),
    82: ("单价", "300KW 柴油发电机组按台计价"),
    217: ("单价", "300KW 柴油发电机组按台计价"),
    270: ("单价", "ETC 门架按座计价，跨度 14.67 米"),
    269: ("单价", "ETC 门架按座计价，跨度 13.73 米"),
}

MODEL = re.compile(r"\b[A-Z][A-Z0-9]{1,}(?:[-/][A-Z0-9A-Za-z]+){1,}\b")


def spec_problem(s):
    s = (s or "").strip()
    if not s:
        return "空"
    if re.search(r"详见图纸|详见设计|按图纸|见附图|详见", s):
        return "图纸"
    if len(s) > 60:
        return "长描述"
    return None


def condense(spec):
    """按分隔符切段并保留『标签：数值』的完整语义，只裁掉冗余长度。"""
    segs = [s.strip() for s in re.split(r"[；;]", spec) if s.strip()]
    if len(segs) < 2:
        # 没有分号：按『带冒号的标签』重新切
        segs = [s.strip() for s in re.split(r"\s+(?=[^\s：:]{1,10}[：:])", spec) if s.strip()]
    if len(segs) < 2:
        return spec if len(spec) <= 120 else spec[:118] + "…"
    out, total = [], 0
    for s in segs:
        if out and total + len(s) > 150:
            break
        out.append(s)
        total += len(s)
    return "；".join(out)


def pick_model(spec):
    m = MODEL.findall(spec or "")
    return m[0] if m else ""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = json.load(open(PRICES, encoding="utf-8"))

    # ① 异常单价判定
    price_issues = []
    for r in sorted([x for x in rows if x["单价"] > 100000], key=lambda x: -x["单价"]):
        verdict, why = JUDGE.get(r["序号"], ("待定", ""))
        price_issues.append({
            "序号": r["序号"], "项目": r["项目"], "设备名称": r["设备名称"],
            "规格参数": r["规格参数"], "单价（元）": r["单价"],
            "结论": verdict, "判断理由": why, "处理建议": "",
        })
    for it in price_issues:
        if it["结论"] == "包价":
            it["处理建议"] = "不作为单价入库；若要用，需除以包含的设备数量或另行拆分"
        elif "存疑" in it["结论"]:
            it["处理建议"] = "入库前请向江苏金晓核实费额显示器真实单价"
        else:
            it["处理建议"] = "可直接作为单价入库"

    # ② 规格整理
    spec_fixed = []
    for r in rows:
        p = spec_problem(r["规格参数"])
        if not p:
            continue
        raw = (r["规格参数"] or "").strip()
        if p == "长描述":
            fixed, status, model = condense(raw), "已整理", pick_model(raw)
        elif p == "图纸":
            m = re.search(r"[（(]([^）)]+)[）)]", raw)
            if m:
                fixed, status, model = "跨距 " + m.group(1), "已从括号提取", ""
            else:
                fixed, status, model = "", "需查原始图纸", ""
        else:
            fixed, status, model = "", "源表为空", ""
        spec_fixed.append({
            "序号": r["序号"], "项目": r["项目"], "设备名称": r["设备名称"],
            "规格参数（原表）": raw or "（空）", "单价（元）": r["单价"],
            "型号": model, "整理后关键参数": fixed, "状态": status,
        })

    data = {"异常单价": price_issues, "规格整理": spec_fixed}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    import collections
    c = collections.Counter(x["结论"] for x in price_issues)
    print("异常单价判定:", dict(c))
    c2 = collections.Counter(x["状态"] for x in spec_fixed)
    print("规格整理:", dict(c2))
    print("\n长描述整理样例:")
    for x in spec_fixed:
        if x["状态"] == "已整理":
            print("  %-18s → %s" % (x["设备名称"][:18], x["整理后关键参数"][:90]))
    print("\n拿不到的行数:", sum(1 for x in spec_fixed if not x["整理后关键参数"]))
    print("→", OUT)


if __name__ == "__main__":
    main()
