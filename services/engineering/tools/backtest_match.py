# -*- coding: utf-8 -*-
"""回测：用已有项目互相匹配，算出跨项目价格复用率。只读，不修改源文件。

逻辑：把 336（一标段）当作"价格库"，拿 安康北 / 北客站 / 店红路 的设备去匹配，
看能命中多少。这是判断成本测算 agent 可行性最直接的一个数。
"""
import os
import re
import sys

import pandas as pd

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
SRC = os.path.join(DESKTOP, "供应商库.xlsx")


def norm(s):
    """归一化：全角转半角、去空白、统一大小写与常见符号。"""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x3000:
            o = 32
        elif 0xFF01 <= o <= 0xFF5E:
            o -= 0xFEE0
        out.append(chr(o))
    s = "".join(out)
    s = s.replace("*", "x").replace("×", "x").replace("φ", "d").replace("Φ", "d")
    s = s.replace("／", "/").replace("－", "-")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def load_price_sheet(sheet):
    raw = pd.read_excel(SRC, sheet_name=sheet, header=None, dtype=object)
    hdr = None
    for i in range(min(6, len(raw))):
        if str(raw.iloc[i, 0]).strip() == "序号":
            hdr = i
            break
    if hdr is None:
        return pd.DataFrame()
    df = raw.iloc[hdr + 1:].copy()
    df.columns = ["序号", "名称", "规格参数", "单价", "备注"][: len(df.columns)]
    df = df[df["名称"].notna()]
    df = df[df["名称"].astype(str).str.strip() != ""]
    df["名称"] = df["名称"].astype(str).str.strip()
    df["规格参数"] = df["规格参数"].fillna("").astype(str).str.strip()
    df["备注"] = df["备注"].fillna("").astype(str).str.strip()
    # 单价里混了单位，拆出来
    def split_price(v):
        t = "" if pd.isna(v) else str(v)
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(.*)$", t)
        if m:
            return float(m.group(1)), m.group(2).strip()
        return None, ""
    parsed = df["单价"].apply(split_price)
    df["单价数值"] = [p[0] for p in parsed]
    df["单价单位"] = [p[1] for p in parsed]
    df["项目"] = sheet.strip()
    return df


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sheets = ["336（一标段）", "336（二标段）", "安康北项目产品价目表",
              "北客站项目产品价目表", "店红路项目产品价目表 "]
    frames = []
    print("=" * 80)
    print("一、五个项目价目表清点")
    print("=" * 80)
    for sh in sheets:
        d = load_price_sheet(sh)
        frames.append(d)
        bad = d["单价数值"].isna().sum()
        print("%-24s 设备行=%-5d 有单价=%-5d 单价无法解析=%-3d 带单位=%d" % (
            sh.strip(), len(d), d["单价数值"].notna().sum(), bad,
            (d["单价单位"] != "").sum()))
    allp = pd.concat(frames, ignore_index=True)
    print("\n合计设备价格记录: %d 行" % len(allp))
    print("品牌可识别（备注非空）: %d 行 (%.0f%%)" % (
        (allp["备注"] != "").sum(), (allp["备注"] != "").mean() * 100))
    addr = allp.groupby("名称").size().sort_values(ascending=False)
    print("名称唯一值: %d 个；出现最多的名称: %s" % (
        len(addr), ", ".join("%s(%d)" % (k, v) for k, v in addr.head(6).items())))

    print("\n" + "=" * 80)
    print("二、跨项目复用回测：库 = 336（一标段）")
    print("=" * 80)
    base = load_price_sheet("336（一标段）")
    base = base[base["单价数值"].notna()]
    base_keys_full = {(norm(r["名称"]), norm(r["规格参数"])) for _, r in base.iterrows()}
    base_keys_name = {norm(r["名称"]) for _, r in base.iterrows()}
    base_keys_core = {norm(r["名称"])[:6] for _, r in base.iterrows() if norm(r["名称"])}

    print("库规模: %d 行 / %d 个『名称+规格』组合 / %d 个不同名称\n" % (
        len(base), len(base_keys_full), len(base_keys_name)))
    print("%-22s %6s %10s %10s %10s" % ("待测算项目", "行数", "精确命中", "仅名称命中", "核心词命中"))
    for sh in ["336（二标段）", "安康北项目产品价目表", "北客站项目产品价目表", "店红路项目产品价目表 "]:
        t = load_price_sheet(sh)
        t = t[t["单价数值"].notna()]
        if not len(t):
            continue
        full = sum(1 for _, r in t.iterrows()
                   if (norm(r["名称"]), norm(r["规格参数"])) in base_keys_full)
        nm = sum(1 for _, r in t.iterrows() if norm(r["名称"]) in base_keys_name)
        core = sum(1 for _, r in t.iterrows()
                   if norm(r["名称"]) and norm(r["名称"])[:6] in base_keys_core)
        n = len(t)
        print("%-22s %6d %9.0f%% %9.0f%% %9.0f%%" % (
            sh.strip(), n, full / n * 100, nm / n * 100, core / n * 100))

    print("\n" + "=" * 80)
    print("三、同一设备在不同项目/标段的价格差异（比价样本）")
    print("=" * 80)
    key = allp.assign(k=allp["名称"].map(norm) + "|" + allp["规格参数"].map(norm))
    grp = key.groupby("k")["单价数值"].agg(["count", "min", "max", "nunique"])
    multi = grp[(grp["count"] > 1) & (grp["min"] > 0)]
    multi = multi.assign(spread=(multi["max"] / multi["min"] - 1) * 100)
    print("出现在 2 个及以上项目的『名称+规格』: %d 个" % len(multi))
    if len(multi):
        print("其中价格存在差异的: %d 个；最大价差 %.0f%%；中位价差 %.0f%%" % (
            (multi["spread"] > 0.5).sum(), multi["spread"].max(),
            multi["spread"].median()))
        print("\n价差最大的 8 个：")
        for k, r in multi.sort_values("spread", ascending=False).head(8).iterrows():
            print("  %-46s 出现%d次  %s ~ %s  (差%.0f%%)" % (
                k[:46], r["count"], r["min"], r["max"], r["spread"]))

    print("\n" + "=" * 80)
    print("四、劳务报价清单清点")
    print("=" * 80)
    lab = os.path.join(DESKTOP, "劳务报价清单.xlsx")
    xls = pd.ExcelFile(lab)
    names_all = []
    for sh in xls.sheet_names:
        raw = pd.read_excel(lab, sheet_name=sh, header=None, dtype=object)
        hdr = None
        for i in range(min(6, len(raw))):
            if str(raw.iloc[i, 0]).strip() == "子目号":
                hdr = i
                break
        if hdr is None:
            continue
        df = raw.iloc[hdr + 1:].copy()
        df.columns = ["c%d" % i for i in range(len(df.columns))]
        sub = df["c1"].dropna().astype(str).str.strip()
        sub = sub[sub != ""]
        names_all.extend(sub.tolist())
        print("%-6s 原始行=%-5d 有子目名称=%-5d" % (sh, len(df), len(sub)))
    uniq = pd.Series(names_all).drop_duplicates()
    print("\n四份清单合计子目行: %d；去重后不同子目: %d" % (len(names_all), len(uniq)))


if __name__ == "__main__":
    main()
