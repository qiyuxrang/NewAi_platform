# -*- coding: utf-8 -*-
"""取价：按优先级从报价记录里挑一个价格，并给出区间。"""


def pick_price(quotes, cfg, project=None):
    """返回 dict：price / low / high / count / supplier / source / note"""
    usable = [q for q in quotes if q["price_type"] not in cfg["exclude_price_types"]]
    if not usable:
        return {"price": None, "low": None, "high": None, "count": 0,
                "supplier": "", "source": "无可用报价",
                "note": "该物料只有包价，不能作为单价使用" if quotes else "价格库无此物料"}

    pool = usable
    source = "价格库"
    if cfg.get("prefer_same_project") and project:
        same = [q for q in usable if q["project"] == project]
        if same:
            pool, source = same, "同项目历史价"

    prices = [q["price"] for q in pool]
    pick = cfg.get("pick", "min")
    if pick == "max":
        target = max(prices)
    elif pick == "avg":
        target = sum(prices) / float(len(prices))
    else:
        target = min(prices)

    hit = [q for q in pool if q["price"] == target][0]
    return {
        "price": target,
        "low": min(prices),
        "high": max(prices),
        "count": len(pool),
        "supplier": hit["supplier"],
        "source": source,
        "note": hit["note"] or "",
    }
