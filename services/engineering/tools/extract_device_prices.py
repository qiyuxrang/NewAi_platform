# -*- coding: utf-8 -*-
"""从 供应商库.xlsx 抽出 5 个项目价目表，标准化为可入库的记录，输出 JSON。只读源文件。

输出：data/tmp/device_prices.json
"""
import json
import os
import re
import sys

import pandas as pd

CONFIRMED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "config", "confirmed_fields.json")


def load_confirmed():
    with open(CONFIRMED, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("是否含税", ""), d.get("价格年份", "")

SRC = os.path.join(os.path.expanduser("~"), "Desktop", "供应商库.xlsx")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "tmp", "device_prices.json")

# 源表 sheet 顺序（含原始尾部空格）
SHEETS = ["336（一标段）", "336（二标段）", "安康北项目产品价目表",
          "北客站项目产品价目表", "店红路项目产品价目表 "]

# 项目名规范：源表 Sheet 名是文档标题，入库应存短名
PROJECT_NAME = {
    "336（一标段）": "336项目（一标段）",
    "336（二标段）": "336项目（二标段）",
    "安康北项目产品价目表": "安康北项目",
    "北客站项目产品价目表": "北客站项目",
    "店红路项目产品价目表": "店红路项目",
}


def project_name(sheet):
    return PROJECT_NAME.get(sheet.strip(), sheet.strip())

# 供应商名归一：只列需要合并的写法，其余保留原文
SUPPLIER_ALIAS = {
    "瑞坤（镀锌）": "陕西瑞坤",
    "瑞坤（镀锌喷塑）": "陕西瑞坤",
    "陕西瑞坤（镀锌喷塑）": "陕西瑞坤",
    "瑞坤（热镀锌含双母）": "陕西瑞坤",
    "瑞坤定制（镀锌）": "陕西瑞坤",
    "榆林鑫众邦商贸（景泰市场）": "榆林鑫众邦商贸",
    "陕西蓝德智慧交通科技有限公司（长安大学）": "陕西蓝德智慧交通科技有限公司",
    "陕西蓝德智慧交通科技有限公司(长安大学）": "陕西蓝德智慧交通科技有限公司",
    "陕西蓝德智慧交通": "陕西蓝德智慧交通科技有限公司",
    "龙岗市西禾商贸有限公司（淘宝）": "西禾商贸",
    "龙港市西禾商贸有限公司": "西禾商贸",
    "合创翼联（浪潮）": "合创翼联",
    "航天信息股份有限公司北京航天金卡分公司": "航天信息",
    "海康": "海康威视",
    "海康威视": "海康威视",
    "西古": "西古光通信",
    "西古光缆": "西古光通信",
    "交通电子": "陕西交通电子工程科技有限公司",
    "陕西交通电子": "陕西交通电子工程科技有限公司",
    "北京万集": "北京万集科技股份有限公司",
    "沣雷": "广州沣雷",
    "成谷科技": "深圳成谷科技有限公司",
    "榆林浩凯德": "榆林浩凯德电子科技有限公司",
    "陕西一通": "陕西一通通信设备有限公司",
    "昌润锦工贸": "榆林昌润锦工贸有限公司",
    "陕西友达未来": "陕西友达未来信息科技有限公司",
    "西安永士达": "西安永士达电子科技有限公司",
    "河北广拓": "河北广拓玻璃钢有限公司",
    "陕西袖翰": "陕西袖翰实业有限公司",
    "陕西中交信通": "陕西中交信通网络科技有限公司",
}


def clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def norm_supplier(raw):
    s = clean_text(raw)
    if not s:
        return "未标注"
    if s in SUPPLIER_ALIAS:
        return SUPPLIER_ALIAS[s]
    core = re.sub(r"[（(][^）)]*[）)]", "", s).strip()
    return SUPPLIER_ALIAS.get(core, s)


def parse_price(v):
    """单价列里混着单位，如 '4.5元/米'，拆成数值和单位。"""
    t = clean_text(v)
    if not t:
        return None, ""
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(.*)$", t)
    if not m:
        return None, ""
    return float(m.group(1)), m.group(2).strip()


def load_sheet(sheet):
    raw = pd.read_excel(SRC, sheet_name=sheet, header=None, dtype=object)
    hdr = None
    for i in range(min(6, len(raw))):
        if clean_text(raw.iloc[i, 0]) == "序号":
            hdr = i
            break
    if hdr is None:
        raise RuntimeError("未找到表头: " + sheet)
    df = raw.iloc[hdr + 1:].copy()
    df.columns = ["序号", "名称", "规格参数", "单价", "备注"][:len(df.columns)]
    df = df[df["名称"].notna()]
    df = df[df["名称"].map(lambda x: clean_text(x) != "")]
    return df


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tax, year = load_confirmed()
    print("已确认口径：含税=%s  年份=%s" % (tax, year))
    rows = []
    n = 0

    if not os.path.exists(SRC):
        # 源表不在原地时，直接给已有结果补字段，避免重跑丢数据
        if not os.path.exists(OUT):
            raise SystemExit("源表与中间结果都不存在，无法继续：%s" % SRC)
        old = json.load(open(OUT, encoding="utf-8"))
        for r in old:
            r["是否含税"] = tax
            r["价格年份"] = year
            r["项目"] = PROJECT_NAME.get(r["项目"], r["项目"])
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1)
        print("源表 %s 不存在，改为给已有 %d 行补字段" % (SRC, len(old)))
        print("→", OUT)
        return

    for sheet in SHEETS:
        project = project_name(sheet)
        df = load_sheet(sheet)
        kept = 0
        for _, r in df.iterrows():
            price, unit = parse_price(r["单价"])
            if price is None:
                continue
            n += 1
            kept += 1
            rows.append({
                "序号": n,
                "项目": project,
                "设备名称": clean_text(r["名称"]),
                "规格参数": clean_text(r["规格参数"]),
                "单价": price,
                "单位": unit,
                "供应商_原文": clean_text(r["备注"]),
                "供应商": norm_supplier(r["备注"]),
                "是否含税": tax,
                "价格年份": year,
                "来源表": sheet.strip(),
            })
        print("%-24s 提取 %d 行" % (project, kept))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("\n合计 %d 行 → %s" % (len(rows), OUT))
    sup = pd.Series([r["供应商"] for r in rows]).value_counts()
    print("归并后供应商 %d 家（原文写法 %d 种）" % (
        len(sup), len({r["供应商_原文"] for r in rows})))
    print("无单位标注的行: %d" % sum(1 for r in rows if not r["单位"]))


if __name__ == "__main__":
    main()
