# -*- coding: utf-8 -*-
"""取价健康度自检：让"搜索被风控 / 整批取不到价"这类问题自动暴露，
而不是悄悄变成一堆 0 元，等人来发现。

每次测算结束都跑一遍，结论写进交付说明、也随接口返回给 Dify。
"""
from collections import Counter


def _kind(src):
    s = str(src or "")
    if s.startswith("互联网检索"):
        return "互联网检索"
    if s.startswith("电缆行情公式"):
        return "电缆行情公式"
    if s.startswith("企业历史报价库"):
        return "企业历史报价库"
    if s.startswith("企业价格库"):
        return "企业价格库"
    if s.startswith("人工含量库"):
        return "人工含量库"
    if any(label in s for label in ("暂估", "经验估值")) or s.startswith("不计入"):
        return "暂估/无价"
    return s.split("｜")[0] or "其他"


def audit(cost_rows, labor_rows=None, zero_warn=0.30, no_web_warn=40):
    """返回 {结论, 命中率, 零价项, 来源分布, 警告[]}。"""
    rows = [r for r in list(cost_rows or []) + list(labor_rows or [])
            if r and len(r) > 7 and r[1] and isinstance(r[4], (int, float))]
    dist = Counter(_kind(r[5]) for r in rows)
    # 甲供行是"0 元材料不计价"，不算"没取到价"
    zero = [r for r in rows
            if not (isinstance(r[6], (int, float)) and r[6])
            and not str(r[5] or "").startswith("甲方供料")
            and not str(r[5] or "").startswith("不计入")]
    n = len(rows) or 1
    zero_rate = len(zero) / n
    web = dist.get("互联网检索", 0)
    warns = []
    estimates = [r for r in rows if any(label in str(r[5] or "")
                 for label in ("暂估", "经验估值")) and not str(r[5] or "").startswith("不计入")]
    if estimates:
        warns.append("%d 项采用暂估或经验估值，尚未取得可核验报价，须询价复核后替换" % len(estimates))
    if zero_rate > zero_warn:
        warns.append("零价项占比 %.0f%%（%d/%d），偏高：多半是搜索被风控或清单缺规格，"
                     "这批结果的设备材料合计会明显偏低，建议复核后再用"
                     % (zero_rate * 100, len(zero), n))
    if web == 0 and zero_rate > 0.2:
        warns.append("本次一条网价都没取到——请确认外网是否可用、搜索源是否被限流；"
                     "也可把历史采购价入库存起来，下次直接命中")
    if len(zero) >= no_web_warn and web < len(zero) / 5:
        warns.append("大额缺口：%d 项没有价，其中多为柜体/专用设备。"
                     "建议把这些设备的询价单/历史采购价入库" % len(zero))
    if dist.get("电缆行情公式"):
        warns.append("电缆 %d 项按「铜价×铜截面」公式估算（不是市场挂牌价），"
                     "铜价波动时会同步变化" % dist["电缆行情公式"])
    return {"结论": "可疑" if warns else "正常",
            "命中率": round(1 - zero_rate, 4),
            "行数": len(rows), "零价项": len(zero),
            "暂估项": len(estimates),
            "零价占比": round(zero_rate, 4),
            "来源分布": dict(dist), "警告": warns}


def to_text(a):
    lines = ["【取价健康度】%s｜命中率 %.0f%%（%d 行里 %d 行无价）"
             % (a["结论"], a["命中率"] * 100, a["行数"], a["零价项"]),
             "　来源分布：" + "；".join("%s %d 项" % (k, v)
                                  for k, v in sorted(a["来源分布"].items(),
                                                     key=lambda x: -x[1]))]
    for w in a["警告"]:
        lines.append("　⚠ " + w)
    return "\n".join(lines)
