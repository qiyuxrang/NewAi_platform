# -*- coding: utf-8 -*-
"""品类分档与线上价折算。

线上价是零售/挂牌价，工程批量价更低。按品类分档折算，再按采购量微调：
采购量越大议价空间越大，系数越往下限走。
"""
import re

ORDER = ["专用定制件", "品牌设备", "通用标准品"]


def classify_tier(cfg, name, category="", supplier=""):
    """归入 专用定制件 / 品牌设备 / 通用标准品 / 通用设备 四档。"""
    text = "%s %s %s" % (name or "", category or "", supplier or "")
    kw = cfg.get("tier_keywords", {})
    for tier in ORDER:
        pat = kw.get(tier)
        if pat and re.search(pat, text):
            return tier
    return "通用设备"


def volume_factor(qty, cfg):
    """数量映射到 0（取上限，量小）~ 1（取下限，量大）。"""
    curve = cfg.get("volume_curve", {})
    small = float(curve.get("small_qty", 5))
    large = float(curve.get("large_qty", 100))
    if qty is None:
        return 0.0
    if qty <= small:
        return 0.0
    if qty >= large:
        return 1.0
    return (qty - small) / (large - small)


def discount_for(tier, qty, cfg):
    """返回 (系数, 说明)。专用定制件线上无价，返回 (None, 原因)。"""
    t = cfg.get("tiers", {}).get(tier)
    if not t or t.get("min") is None:
        return None, "该品类线上通常没有报价，须走询价"
    lo, hi = float(t["min"]), float(t["max"])
    f = volume_factor(qty, cfg)
    coef = hi - (hi - lo) * f
    note = "采购量 %s，%s" % (qty, "取折扣下限（走量大）" if f >= 1
                              else "取折扣上限（量小）" if f <= 0
                              else "按量居中折算")
    return round(coef, 4), note
