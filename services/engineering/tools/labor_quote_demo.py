# -*- coding: utf-8 -*-
"""劳务组价示例：把『路灯基础（包工包料）』按定额拆成工序并算出每座单价。

含量取自工程量清单自带的基础尺寸与材料用量（1200×1200×1600、钢筋 52.6kg/座、
C30 混凝土 2.2m³/座），甲供材料只计人工与机械。

用法：  .venv\\Scripts\\python.exe tools\\labor_quote_demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.quota import QuotaLibrary  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 工序 → (定额检索关键词, 专业, 每座含量换算, 取费口径)
STEPS = [
    {"工序": "土方综合施工", "kws": ["人工挖一般土方"], "source": "市政",
     "含量": 1.2 * 1.2 * 1.6, "定额单位": 100.0, "取": ["人工费", "机械费"],
     "依据": "基坑 1.2×1.2×1.6m，人工挖一般土方（一、二类土 ≤2m）"},
    {"工序": "基础结构施工（钢筋制作绑扎）", "kws": ["带肋钢筋"], "source": "市政",
     "含量": 0.0526, "定额单位": 1.0, "取": ["人工费", "机械费"],
     "依据": "钢筋 52.6kg/座（甲供），只计制作绑扎人工"},
    {"工序": "混凝土浇筑及养护", "kws": ["混凝土基础 预拌"], "source": "市政",
     "含量": 2.2, "定额单位": 1.0, "取": ["人工费", "机械费"],
     "依据": "C30 混凝土 2.2m³/座（甲供），只计浇筑养护人工与机械"},
]


def main():
    cfg = json.load(open(os.path.join(ROOT, "config", "settings.json"), encoding="utf-8"))
    lib = QuotaLibrary(os.path.join(ROOT, "data", "library", "定额基价库.json"),
                       os.path.join(ROOT, "data", "library", "定额含量库.json"))
    region = cfg.get("labor", {}).get("region_factor", {}).get("榆林", 1.05)

    qty = 2431.0            # 清单数量：座
    rows = []
    subtotal = 0.0
    for st in STEPS:
        cands = lib.search(st["kws"], source_kw=st["source"], top=3)
        if not cands:
            print("未匹配：%s" % st["工序"])
            continue
        pick = cands[0]
        unit_cost = sum(float(pick.get(k) or 0) for k in st["取"]) / st["定额单位"] * st["含量"]
        subtotal += unit_cost
        rows.append((st["工序"], pick["编号"], pick["项目名称"], unit_cost, st["依据"]))

    # 措施费与特殊地质
    measure = subtotal * 0.05
    special = 122 * 800 / qty
    per_seat = (subtotal + measure + special) * region

    print("路灯基础 劳务组价（包工包料，甲供材料不计）")
    print("-" * 78)
    for name, code, quota_name, cost, why in rows:
        print("  %-22s %-8s %8.2f 元/座   %s" % (name[:22], code, cost, (quota_name or "")[:26]))
    print("  %-22s %-8s %8.2f 元/座   按直接费 5%% 计取" % ("安全文明及措施费", "费率", measure))
    print("  %-22s %-8s %8.2f 元/座   共线路段混凝土破除，122座×800元平摊" % ("特殊地质基础开挖", "清单口径", special))
    print("-" * 78)
    print("  内部成本合计（未含地区系数）        %8.2f 元/座" % (subtotal + measure + special))
    print("  榆林地区系数                         %8.2f" % region)
    print("  劳务单价                             %8.2f 元/座" % per_seat)
    print("  数量                                 %8.0f 座" % qty)
    print("  劳务合价                         %10.2f 元" % (per_seat * qty))

    out = os.path.join(ROOT, "data", "output", "劳务组价_路灯基础示例.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"步骤": [{"工序": r[0], "定额编号": r[1], "定额名称": r[2],
                        "元每座": round(r[3], 2), "依据": r[4]} for r in rows],
               "措施费元每座": round(measure, 2), "特殊地质元每座": round(special, 2),
               "地区系数": region, "劳务单价": round(per_seat, 2), "数量": qty,
               "劳务合价": round(per_seat * qty, 2)},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("→", out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
