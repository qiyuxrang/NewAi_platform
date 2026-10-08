# -*- coding: utf-8 -*-
"""聚焦检查：供应商库的价目表 Sheet、劳务报价清单全部 Sheet。只读。"""
import os
import sys

import pandas as pd

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def sep(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def dump(path, sheets, max_rows=12):
    sep("FILE: %s" % os.path.basename(path))
    xls = pd.ExcelFile(path)
    for sh in xls.sheet_names:
        if sheets is not None and sh not in sheets:
            continue
        df = pd.read_excel(path, sheet_name=sh, dtype=object)
        print("\n---- sheet: %s  rows=%d cols=%d ----" % (sh, len(df), len(df.columns)))
        print("列名: %s" % list(df.columns))
        for c in df.columns:
            nn = df[c].notna().sum()
            sample = repr(df[c].dropna().iloc[0])[:36] if nn else ""
            print("   %-24s 非空=%-5d 唯一=%-5d 示例=%s" % (str(c)[:24], nn, df[c].nunique(dropna=True), sample))
        with pd.option_context("display.max_columns", 30, "display.width", 260, "display.max_colwidth", 40):
            print("\n样本:")
            print(df.head(max_rows).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dump(os.path.join(DESKTOP, "供应商库.xlsx"),
         {"4.劳务队供应商", "336（一标段）", "336（二标段）", "安康北项目产品价目表",
          "北客站项目产品价目表", "店红路项目产品价目表 "}, max_rows=10)
    dump(os.path.join(DESKTOP, "劳务报价清单.xlsx"), None, max_rows=8)
