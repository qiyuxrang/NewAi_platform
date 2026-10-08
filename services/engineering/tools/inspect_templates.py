# -*- coding: utf-8 -*-
"""检查输入清单与两个输出模板的结构。只读。"""
import os
import sys

import pandas as pd

FILES = [
    ("输入·设备清单", r"C:\Users\123\Documents\xwechat_files\wxid_5r77z7p0y51t22_beab\msg\file\2026-09\报价清单--照明9.4.xlsx"),
    ("输出模板·报价单", r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\报价清单\2026-榆林市公安局交警支队经济技术开发区大队道路监控卡口改造项目报价单.xlsx"),
    ("输出模板·劳务", r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）\02-工程技术部\成本测算\报价清单\劳务报价清单.xlsx"),
]


def dump(tag, path, max_rows=14):
    print("\n" + "=" * 78)
    print("%s  |  %s" % (tag, os.path.basename(path)))
    print("=" * 78)
    if not os.path.exists(path):
        print("  文件不存在")
        return
    xls = pd.ExcelFile(path)
    print("Sheet: %s" % xls.sheet_names)
    for sh in xls.sheet_names:
        raw = pd.read_excel(path, sheet_name=sh, header=None, dtype=object)
        print("\n---- [%s]  shape=%s ----" % (sh, raw.shape))
        with pd.option_context("display.max_columns", 30, "display.width", 250,
                               "display.max_colwidth", 32):
            print(raw.head(max_rows).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for tag, p in FILES:
        dump(tag, p)
