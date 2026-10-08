# -*- coding: utf-8 -*-
"""生成最终入库版：物料主数据 + 报价记录。输出 JSON。"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = os.path.join(ROOT, "data", "tmp", "device_prices.json")
ISSUES = os.path.join(ROOT, "data", "tmp", "issues_resolved.json")
OUT = os.path.join(ROOT, "data", "tmp", "final_tables.json")

# 包价（选项 A：标记为包价，不作为单价使用）
PACKAGE_IDS = {299, 463, 121}
# 判定数值存疑（仍按单价入库，但标注）
SUSPECT_IDS = {505}

CATEGORY_RULES = [
    ("软件平台", r"软件|平台|系统|网管|链路|授权终端"),
    ("收费系统", r"ETC|收费|费显|车道|栏杆|RSU|天线|读写器|PSAM|通行券|键盘|发卡|称重|超限"),
    ("视频监控", r"摄像|视频|监控|球机|卡口|录像|录放"),
    ("情报板显示", r"情报板|显示屏|信息标志|标志牌|雨棚信号灯|黄闪|信号灯|雾灯"),
    ("通信网络", r"交换机|路由器|光端机|服务器|存储|磁盘|防火墙|网关|ONU|光纤收发"),
    ("供配电", r"配电|高压|低压|馈线|柜|变压器|发电|UPS|电源|蓄电池|避雷|接地"),
    ("通风机电", r"风机|射流|空调|水泵|电机"),
    ("消防", r"火灾|报警|消防"),
    ("线缆管材", r"线缆|电缆|光缆|硅芯管|管箱|集束管|网线|跳线|钢纤维|地感线圈"),
    ("土建结构", r"门架|立柱|杆|基础|预埋|收费岛|防护|防撞|亭|爬梯|支架|法兰"),
]

UNIT_RULES = [
    (r"线缆|电缆|光缆|硅芯管|集束管|管箱|网线|跳线|钢纤维|地感线圈|光缆", "米"),
    (r"软件|平台|系统|网管|链路|服务", "项"),
    (r"门架|立柱|杆|基础|预埋|收费岛|防护|防撞|亭", "套"),
]


def guess_category(name):
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, name):
            return cat
    return "其他"


def guess_unit(name, raw_unit):
    if raw_unit:
        return re.sub(r"^元\s*/\s*", "", raw_unit).strip() or "项", "原表"
    for pat, u in UNIT_RULES:
        if re.search(pat, name):
            return u, "推断"
    return "台", "推断"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = json.load(open(PRICES, encoding="utf-8"))
    issues = json.load(open(ISSUES, encoding="utf-8"))
    spec_fix = {x["序号"]: x for x in issues["规格整理"]}

    # 物料归并
    key_of = {}
    materials = []
    for r in rows:
        k = (r["设备名称"].strip(), (r["规格参数"] or "").strip())
        if k not in key_of:
            key_of[k] = len(materials) + 1
            fix = spec_fix.get(r["序号"], {})
            unit, unit_src = guess_unit(r["设备名称"], r["单位"])
            status = fix.get("状态", "")
            if not status:
                spec_status = "正常"
            elif status in ("已整理", "已从括号提取"):
                spec_status = "已整理"
            elif status == "需查原始图纸":
                spec_status = "规格未定（原表指向图纸）"
            else:
                spec_status = "规格未定（原表为空）"
            materials.append({
                "物料编码": "MAT-%04d" % key_of[k],
                "设备名称": r["设备名称"],
                "规格参数（原表）": r["规格参数"],
                "关键参数（整理）": fix.get("整理后关键参数", ""),
                "型号": fix.get("型号", ""),
                "单位": unit,
                "单位来源": unit_src,
                "设备类别": guess_category(r["设备名称"]),
                "规格状态": spec_status,
            })

    quotes = []
    for r in rows:
        k = (r["设备名称"].strip(), (r["规格参数"] or "").strip())
        code = "MAT-%04d" % key_of[k]
        if r["序号"] in PACKAGE_IDS:
            ptype, note = "包价", "系统/平台整体报价，不作为单价使用"
        elif r["序号"] in SUSPECT_IDS:
            ptype, note = "单价", "数值存疑：与同供应商门架式情报板同价，需核实"
        else:
            ptype, note = "单价", ""
        quotes.append({
            "物料编码": code, "项目": r["项目"], "供应商": r["供应商"],
            "单价（元）": r["单价"], "是否含税": r["是否含税"],
            "价格类型": ptype, "价格年份": r["价格年份"], "备注": note,
        })

    # 回填每个物料的报价条数与项目数
    cnt = collections.Counter(q["物料编码"] for q in quotes)
    proj = collections.defaultdict(set)
    for q in quotes:
        proj[q["物料编码"]].add(q["项目"])
    for m in materials:
        m["报价条数"] = cnt[m["物料编码"]]
        m["涉及项目数"] = len(proj[m["物料编码"]])

    data = {"物料主数据": materials, "报价记录": quotes}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("物料主数据 : %d 条" % len(materials))
    print("报价记录   : %d 条（单价 %d / 包价 %d）" % (
        len(quotes),
        sum(1 for q in quotes if q["价格类型"] == "单价"),
        sum(1 for q in quotes if q["价格类型"] == "包价")))
    print("规格状态   :", dict(collections.Counter(m["规格状态"] for m in materials)))
    print("设备类别   :", dict(collections.Counter(m["设备类别"] for m in materials)))
    print("单位       :", dict(collections.Counter(m["单位来源"] for m in materials)))
    print("→", OUT)


if __name__ == "__main__":
    main()
