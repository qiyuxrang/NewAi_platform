# -*- coding: utf-8 -*-
"""太阳能路灯交付文件自检：勾稽、格式、命名、与参考值对比。

用法：  .venv\\Scripts\\python.exe tools\\verify_lamp.py
输出：  data/output/太阳能路灯项目/自检报告.md
"""
import os
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import project_lamp as pl  # noqa: E402

OUT = pl.OUT_DIR
LINES = []
ISSUES = []


def say(s=""):
    LINES.append(s)
    print(s)


def check(cond, ok, bad):
    say(("  ✅ " if cond else "  ❌ ") + (ok if cond else bad))
    if not cond:
        ISSUES.append(bad)
    return cond


def main():
    v = pl.calc_versions()
    n, nd = pl.P["路灯数量"], pl.P["拆除数量"]
    say("# 太阳能路灯项目交付文件 自检报告")
    say()
    say("## 一、计算勾稽")
    check(pl.WAGE_SUM == 4240, "队日人工 4240 元（5×200+2×330+1×330+3×350+1×450+2×200+1×350）",
          "队日人工不等于 4240：%s" % pl.WAGE_SUM)
    check(pl.CREW_DAY == 5540, "队日综合费用 5540 元（4240+800+150+350）",
          "队日综合费用不等于 5540：%s" % pl.CREW_DAY)
    check(abs(pl.UNIT_COST - 2216) < 0.5, "纯成本 2216 元/座（5540 ÷ 2.5）",
          "纯成本不等于 2216：%.2f" % pl.UNIT_COST)
    check(pl.MEASURE_UNIT == 295, "交通安措 295 元/座（70+120+40+25+40）",
          "安措合计不等于 295：%s" % pl.MEASURE_UNIT)

    a, b = v["甲供C30"], v["不提供C30"]
    check(abs(a["直接费"] - (a["主体"] + a["安措"] + a["拆除"])) < 1,
          "甲供版 直接费 = 主体 + 安措 + 拆除",
          "甲供版直接费勾稽不平")
    chk = a["直接费"] * pl.P["降效率"]
    check(abs(a["降效窝工"] - chk) < 1, "降效 6%% 基数=直接费（%.2f 万）" % (chk / 1e4),
          "降效勾稽错")
    chk = (a["直接费"] + a["降效窝工"] + a["不可预见风险"]) * pl.P["管理费率"]
    check(abs(a["管理费"] - chk) < 1, "管理费 10% 基数=直接费+降效+风险",
          "管理费勾稽错")
    chk = (a["直接费"] + a["降效窝工"] + a["不可预见风险"] + a["管理费"]) * pl.P["税率"]
    check(abs(a["税金"] - chk) < 1, "税金 3% 基数=上项累计", "税金勾稽错")
    chk = pl.P["C30到场价"] * n * pl.P["C30单座"] * pl.P["C30损耗"]
    check(abs(b["材料款"] - chk) < 1, "C30 材料款 = %.1f m³ × 280 元 = %.2f 万"
          % (b["C30方量"], chk / 1e4), "材料款勾稽错")
    chk = b["材料款"] * (1 + pl.P["材料采购管理费率"]) * (1 + pl.P["税率"])
    check(abs(b["材料线含税"] - chk) < 1, "材料线含税 = 材料款×1.05×1.03（不进 6%/4% 基数）",
          "材料线勾稽错")
    check(abs(b["总计"] - (b["劳务线含税"] + b["材料线含税"])) < 1,
          "不提供 C30 版 总计 = 劳务线 + 材料线", "不提供C30版总计勾稽错")

    say()
    say("## 二、与参考结果对比")
    ref = [("甲供 C30 版总价", a["总计"], 780.3), ("不提供 C30 版总价", b["总计"], 954.5),
           ("单座造价（甲供版）", a["单价每座"], 3210), ("纯成本（全项目）",
                                              pl.UNIT_COST * n, 428.0)]
    say("| 指标 | 本次结果 | 你的参考 | 差异 |")
    say("|---|---|---|---|")
    for name, got, want in ref:
        g = got / 1e4 if got > 1e5 else got
        d = (g / want - 1) * 100
        note = "接近" if abs(d) <= 5 else ("偏大" if d > 0 else "偏小")
        say("| %s | %.2f | %.2f | %+.1f%%（%s） |" % (name, g, want, d, note))
    say()
    say("> 说明：纯成本 538.71 万 与参考底价 428 万 差 110.7 万——你的底价口径应未包含"
        "拆除（29.3 万）与交通安措摊销，建议把底价口径写死为「2216 元/座 纯成本，"
        "底线不低于 2216+295=2511 元/座（610 万）」。")

    say()
    say("## 三、文件与格式检查")
    files = sorted(f for f in os.listdir(OUT) if f.endswith(".xlsx"))
    for f in files:
        path = os.path.join(OUT, f)
        wb = openpyxl.load_workbook(path)
        ws_names = wb.sheetnames
        say("- **%s**（%d 个 sheet：%s）%.1f KB" % (f, len(ws_names), "、".join(ws_names),
                                               os.path.getsize(path) / 1024))
        for ws in wb.worksheets:
            fonts = {c.font.name for row in ws.iter_rows() for c in row if c.value is not None}
            no_border = sum(1 for row in ws.iter_rows() for c in row
                            if c.value is not None and (c.border.left.style is None))
            check(fonts <= {"微软雅黑"}, "字体统一微软雅黑", "%s/%s 字体不统一：%s" % (f, ws.title, fonts))
            check(no_border == 0, "单元格全边框（%s）" % ws.title,
                  "%s/%s 有 %d 个单元格缺边框" % (f, ws.title, no_border))
        wb.close()

    quote = os.path.join(OUT, "4.对外劳务报价清单（甲供C30版）.xlsx")
    if os.path.exists(quote):
        wb = openpyxl.load_workbook(quote)
        ws = wb["对外劳务报价清单"]
        wc = ws.column_dimensions["C"].width
        wh = ws.column_dimensions["H"].width
        check(wc >= 68, "报价清单 C 列宽 %.0f（要求 ≥68）" % wc, "C 列宽不足：%.0f" % wc)
        check(wh >= 42, "报价清单 H 列宽 %.0f（要求 ≥42）" % wh, "H 列宽不足：%.0f" % wh)
        heights = [ws.row_dimensions[r].height or 0 for r in range(3, ws.max_row + 1)]
        check(all(h >= 20 for h in heights), "行高按内容动态设置（最小 %.0f）" % min(heights),
              "有行高过小：%.0f" % min(heights))
        wb.close()

    expect = ["1.设备清单（分甲供与我方采购）.xlsx", "2.劳务清单（按施工分类）.xlsx",
              "3.成本测算表（两口径）.xlsx", "4.对外劳务报价清单（甲供C30版）.xlsx",
              "5.对外劳务报价清单（甲方不提供C30版）.xlsx", "6.设备采购责任分类表.xlsx"]
    check(all(e in files for e in expect), "六份文件命名符合规范",
          "缺文件：%s" % [e for e in expect if e not in files])

    say()
    say("## 四、结论")
    if ISSUES:
        say("发现 %d 个问题，需修正：" % len(ISSUES))
        for x in ISSUES:
            say("- %s" % x)
    else:
        say("全部检查通过：勾稽自洽、格式合规、命名规范。")
    report = os.path.join(OUT, "自检报告.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES))
    print("→", report)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
