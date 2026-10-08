# -*- coding: utf-8 -*-
"""扫一遍桌面「成本测算输出」里的所有六件套，重新生成批量汇总表（含自检）。

批量跑完之后用它重出总表——自检规则改了、或某几份后来重跑过，都靠这个对齐。
"""
import glob
import os
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from run_batch import sanity, read_sheets  # noqa: E402

OUT_ROOT = r"C:\Users\123\Desktop\成本测算输出"
HEAD = openpyxl.styles.PatternFill("solid", fgColor="D9E1F2")
RED = openpyxl.styles.PatternFill("solid", fgColor="FCE4D6")
YEL = openpyxl.styles.PatternFill("solid", fgColor="FFF2CC")
F = "微软雅黑"
THIN = openpyxl.styles.Side(style="thin", color="000000")
BORDER = openpyxl.styles.Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def main():
    files = sorted(glob.glob(os.path.join(OUT_ROOT, "*", "1.成本测算六件套.xlsx")))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "批量汇总"
    heads = ["序号", "项目（输出文件夹）", "设备材料项数", "甲供C30版(万)",
             "不提供C30版(万)", "折合元/单位", "自检", "输出文件"]
    ws.append(["共享资料库 · 采购清单批量测算汇总"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(heads))
    ws.cell(row=1, column=1).font = openpyxl.styles.Font(name=F, size=14, bold=True,
                                                         color="1F3864")
    ws.append(heads)
    rows = []
    for i, p in enumerate(files, 1):
        proj = os.path.basename(os.path.dirname(p))
        try:
            sh = read_sheets(p)
        except Exception as e:  # noqa: BLE001
            rows.append([i, proj, "", "", "", "", "打不开：%s" % str(e)[:60], p])
            continue
        ok, issues = sanity(sh)
        a = b = unit = n = None
        # 成本测算总计取③④表新增的"成本测算总计（…）"行：
        # 那才是"设备材料 + 劳务 + 取费"的完整成本口径；
        # ⑤⑥是劳务/采购的对外报价，采购清单里等于设备总价、有劳务时又不含设备，
        # 直接拿⑤当"总价"会张冠李戴
        def total_of(sheet):
            for r in sh.get(sheet) or []:
                nm = str(r[1] or "")
                if nm.startswith("成本测算总计"):
                    return r[5]
                if "对外报价总额" in nm:
                    return r[6]        # 老版本文件没有总计行时退回⑤
            return None
        a = total_of("③成本测算（库+网检索）")
        b = total_of("④成本测算（纯网检索）")
        unit = None
        ws3 = sh.get("③成本测算（库+网检索）") or []
        for r in ws3:
            if not (isinstance(r[0], (int, float)) and r[1]):
                continue
            nm = str(r[1])
            if nm.startswith("甲供 C30 版 合计"):
                a = a or r[3]
                unit = r[4]
            if "不提供 C30 版 合计" in nm or "不提供C30版" in nm:
                b = b or r[3]
        ws1 = sh.get("①设备清单") or []
        n = sum(1 for r in ws1[3:] if isinstance(r[0], (int, float)) and r[1])
        rows.append([i, proj, n, round(a / 10000, 2) if a else "",
                     round(b / 10000, 2) if b else "", unit,
                     "通过" if ok else "；".join(issues)[:110], p])
    for r in rows:
        ws.append(r)
    tot = sum((r[3] or 0) for r in rows if isinstance(r[3], (int, float)))
    ws.append(["", "合计 %d 份" % len(rows), "", round(tot, 2), "", "", "", ""])
    for i, w in enumerate([5, 34, 12, 15, 16, 13, 62, 56], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.value is None:
                continue
            c.font = openpyxl.styles.Font(name=F, size=10)
            c.border = BORDER
            c.alignment = openpyxl.styles.Alignment(vertical="center", wrap_text=True)
    for c in ws[2]:
        c.font = openpyxl.styles.Font(name=F, size=10, bold=True)
        c.fill = HEAD
    for row in ws.iter_rows(min_row=3):
        v = row[6].value or ""
        if v and v != "通过":
            for c in row:
                c.fill = RED if "打不开" in v else YEL
    out = os.path.join(OUT_ROOT, "00_批量汇总.xlsx")
    wb.save(out)
    print("已生成 %s（%d 份）" % (out, len(rows)))
    for r in rows:
        print("  %2d %-32s %8s 万  自检:%s" % (r[0], str(r[1])[:32],
                                            r[3] if r[3] != "" else "—", r[6]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
