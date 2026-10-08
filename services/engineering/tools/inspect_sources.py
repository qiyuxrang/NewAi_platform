# -*- coding: utf-8 -*-
"""只读检查：把三份原始资料的结构、字段、样例行、数据质量打印出来。

用法：python tools/inspect_sources.py
不修改任何源文件。
"""
import os
import subprocess
import sys

import pandas as pd

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
XLSX_FILES = ["供应商库.xlsx", "劳务报价清单.xlsx"]
RAR_FILE = "计价定额标准.rar"


def sep(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def inspect_excel(path):
    sep("EXCEL: " + os.path.basename(path))
    print("size: %.1f KB" % (os.path.getsize(path) / 1024))
    xls = pd.ExcelFile(path)
    print("sheets: %s" % xls.sheet_names)
    for sh in xls.sheet_names:
        raw = pd.read_excel(path, sheet_name=sh, header=None, dtype=object)
        print("\n---- sheet: %s  shape=%s ----" % (sh, raw.shape))
        print("前 8 行原始内容：")
        with pd.option_context("display.max_columns", 50, "display.width", 250,
                               "display.max_colwidth", 40):
            print(raw.head(8).to_string())
        df = pd.read_excel(path, sheet_name=sh, dtype=object)
        print("\n推断表头: %s" % list(df.columns))
        print("数据行数: %d" % len(df))
        print("\n各列非空数量 / 唯一值数量：")
        for c in df.columns:
            sample = repr(df[c].dropna().iloc[0])[:40] if df[c].notna().any() else ""
            print("  %-22s 非空=%-5d 唯一=%-5d 示例=%s" % (
                str(c)[:22], df[c].notna().sum(), df[c].nunique(dropna=True), sample))
        print("\n前 15 行数据：")
        with pd.option_context("display.max_columns", 50, "display.width", 300,
                               "display.max_colwidth", 30):
            print(df.head(15).to_string())


def inspect_rar(path):
    sep("RAR: " + os.path.basename(path))
    print("size: %.1f MB" % (os.path.getsize(path) / 1024 / 1024))
    tar = os.path.join(os.environ.get("SystemRoot", r"C:\WINDOWS"), "system32", "tar.exe")
    if not os.path.exists(tar):
        print("未找到 tar.exe，跳过")
        return
    p = subprocess.run([tar, "-tf", path], capture_output=True)
    raw = p.stdout
    text = None
    for enc in ("gbk", "utf-8", "cp936"):
        try:
            text = raw.decode(enc)
            print("编码: %s" % enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        print("解码失败")
        return
    lines = [l for l in text.splitlines() if l.strip()]
    print("条目总数: %d" % len(lines))
    for l in lines:
        print("  " + l)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for f in XLSX_FILES:
        p = os.path.join(DESKTOP, f)
        if os.path.exists(p):
            inspect_excel(p)
        else:
            print("缺失: " + p)
    p = os.path.join(DESKTOP, RAR_FILE)
    if os.path.exists(p):
        inspect_rar(p)
