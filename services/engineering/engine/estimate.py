# -*- coding: utf-8 -*-
"""生成四版输出：① 成本测算(库+网) ② 成本测算(纯网) ③ 劳务报价(库+网) ④ 劳务报价(纯网)。

甲供逻辑：备注标了甲供的项默认剔除；再次循环时只对未剔除项计算。
"""
from engine import boq as boq_mod

EQUIP_CATS = {"设备", "材料", "其他"}
LABOR_CATS = {"劳务施工", "包工包料", "措施项目", "管理费"}

OUT_HEADS = ["序号", "项目名称", "规格/说明", "单位", "数量",
             "价格来源", "单价（元）", "小计（元）",
             "检索关键词", "依据/说明", "备注（可填）", "审核"]


def _source_label(from_library):
    return "知识库命中" if from_library else "待互联网检索"


def split_items(items):
    """甲供剔除后按成本类型分流。"""
    kept = [x for x in items if x["是否报价"] == "是"]
    dropped = [x for x in items if x["是否报价"] == "否"]
    equip = [x for x in kept if x["类别"] in EQUIP_CATS]
    labor = [x for x in kept if x["类别"] in LABOR_CATS]
    return kept, dropped, equip, labor


def build_rows(equip, labor, cfg, pure_online=False):
    """返回 ①/② 与 ③/④ 两张表的行数据。"""
    # -------- 设备/材料成本 --------
    cost_rows = []
    for n, x in enumerate(equip, 1):
        lib_hit = False  # 由调用方在接入价格库后回填
        cost_rows.append([
            n, x["项目名称"], x["备注"][:40], x["单位"], x["数量"],
            "待互联网检索" if pure_online else _source_label(lib_hit),
            "", "", "%s %s" % (x["项目名称"], x["备注"][:30]),
            x["依据/说明"], "", "",
        ])

    # -------- 劳务报价 --------
    labor_rows = []
    n = 0
    for x in labor:
        if x["类别"] == "包工包料":
            steps = cfg.get("labor_breakdown", {}).get("包工包料", [])
            for s in steps:
                n += 1
                labor_rows.append([
                    n, "%s — %s" % (x["项目名称"], s["工序"]), s["工作内容"],
                    x["单位"], x["数量"],
                    "待互联网检索" if pure_online else "知识库/当地劳务区间",
                    "", "", "", "按工序分解报价，材料甲供部分不计", "", "",
                ])
            n += 1
            labor_rows.append([
                n, "%s — 材料成本（甲供部分）" % x["项目名称"],
                "钢筋、C30混凝土、预埋穿线管等；备注标注甲供，仅作对照不计价",
                x["单位"], x["数量"], "甲供不计", "", "", "", "⚠ 材料甲供，不进入报价",
                "", "",
            ])
        else:
            n += 1
            labor_rows.append([
                n, x["项目名称"], x["备注"][:40], x["单位"], x["数量"],
                "待互联网检索" if pure_online else "知识库/当地劳务区间",
                "", "", "%s 劳务单价" % x["项目名称"], x["依据/说明"], "", "",
            ])
    return cost_rows, labor_rows
