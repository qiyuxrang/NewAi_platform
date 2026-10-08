# -*- coding: utf-8 -*-
"""批量测算：把共享资料库「采购清单及产品说明」下所有清单跑一遍，输出六件套 + 汇总自检表。

用法：
    .venv\\Scripts\\python.exe tools\\run_batch.py [--only 供电系统] [--limit 5]

要点：
- 全部文件共用同一份联网价格缓存，第 1 份冷启动，后面基本走缓存
- 每份都跑一次合情合理性自检（零价、异常单价、勾稽），汇总成一张总表
- 单份失败不影响其它份，失败清单会记进汇总
"""
import argparse
import glob
import json
import os
import sys
import time
import traceback

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 批量跑必须在宿主机执行，导出目录要显式指到桌面（four sheet 在 import 时读这个变量）
os.environ.setdefault("EXPORT_DIR", r"C:\Users\123\Desktop\成本测算输出")

from engine import foursheet  # noqa: E402

BASE = (r"C:\Users\123\Desktop\项目\企业共享资料库（2018-2026整理）"
        r"\02-工程技术部\成本测算\采购清单及产品说明")
OUT_ROOT = r"C:\Users\123\Desktop\成本测算输出"
LOG = os.path.join(ROOT, "data", "tmp", "batch_run.log")
DONE = os.path.join(ROOT, "data", "tmp", "batch_done.json")

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="D9E1F2")
YEL = PatternFill("solid", fgColor="FFF2CC")
RED = PatternFill("solid", fgColor="FCE4D6")
F = "微软雅黑"


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def project_name(path):
    """把文件路径转成一个能认出来的项目名：各层文件夹 + 文件名。

    ⚠ 必须带上最外层的项目分组。以前只取"内层文件夹-文件名"，
    智能化系统 / 横沟-供配电设备 / 生产集控及调度系统 三个分组下同名的
    「线缆管材类」「网络交换设备」…会写成同一个项目名，导出到桌面后
    后跑的把那前跑的覆盖掉——44 份跑完只剩 22 个文件夹。
    """
    rel = os.path.relpath(path, BASE)
    parts = rel.split(os.sep)
    parts[-1] = os.path.splitext(parts[-1])[0]
    # 去掉相邻重复层：供电系统/厂区照明/厂区照明.xlsx → 供电系统-厂区照明
    uniq = [x for i, x in enumerate(parts) if i == 0 or x != parts[i - 1]]
    return "-".join(uniq)


def collect(only=""):
    out = []
    for p in glob.glob(os.path.join(BASE, "**", "*.xlsx"), recursive=True):
        if only and only not in p:
            continue
        if os.path.basename(p).startswith("~$"):
            continue
        out.append(p)
    return sorted(out)


def load_done():
    """断点续跑：整批跑 2~3 小时，中途被系统杀掉（内存不足）不要从头再来。"""
    if os.path.exists(DONE):
        try:
            return set(json.load(open(DONE, encoding="utf-8")))
        except Exception:
            return set()
    return set()


def mark_done(p):
    s = load_done()
    s.add(p)
    with open(DONE, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f, ensure_ascii=False)


def sanity(sheets):
    """合情合理性自检：零价、单价异常、勾稽。返回 (通过, 问题列表)。"""
    issues = []
    for name, rows in sheets.items():
        if name.startswith("②"):
            iq, ip, it, iu = 5, 6, 7, 4
        elif name.startswith("①"):
            iq, ip, it, iu = 3, 7, 8, 4
        else:
            iq, ip, it, iu = 4, 5, 6, 3
        n = zero = bad = 0
        prices = []
        for r in rows:
            if max(iq, ip, it) >= len(r) or not r[1]:
                continue
            # 「（本清单无劳务子目）」这类占位说明行不是真子目，
            # 它本来就该是 0，别把它当成"有 1 行零价"报出来
            nm = str((r[2] if name.startswith("②") else r[1]) or "")
            if nm.startswith("（") or "无劳务子目" in nm or "无设备材料" in nm:
                continue
            if not isinstance(r[iq], (int, float)):
                continue
            n += 1
            # 单价不是数字的行（如"—"的说明行）不算"零价"，那是故意留的提示行
            if not isinstance(r[ip], (int, float)):
                n -= 1
                continue
            p = r[ip]
            t = r[it] if isinstance(r[it], (int, float)) else 0
            prices.append(p)
            if not t:
                zero += 1
            if r[iq] and abs(p * r[iq] - t) > max(1.0, 0.01 * abs(t)):
                bad += 1
        if n and zero:
            issues.append("%s 有 %d 行零价" % (name, zero))
        if bad:
            issues.append("%s 有 %d 行勾稽不平" % (name, bad))
        # 单价跨度只在"同单位"内比：一张表里 电缆敷设 6 元/m 和 变压器 30 万/台
        # 放一起比是正常的，不能当异常
        by_unit = {}
        for r in rows:
            if max(iq, ip, it, iu) >= len(r) or not isinstance(r[iq], (int, float)):
                continue
            if not isinstance(r[ip], (int, float)) or r[ip] <= 0:
                continue
            # ⚠ 必须按「单位」列分组。以前写的是 r[3] or r[4]，
            # 在设备清单里 r[3] 是"数量"，等于按数量分组，必然报假异常
            by_unit.setdefault(str(r[iu] or ""), []).append(r[ip])
        for u, ps in by_unit.items():
            # 同一单位里"小端子排 444 元 vs 2500kVA 变压器 24.5 万"是正常的，
            # 只有跨度离谱到 1000 倍以上才值得提一句，且只作提示不作异常
            if len(ps) >= 4 and max(ps) / min(ps) > 1000:
                issues.append("%s 同单位「%s」单价跨度大（%.2f ~ %.2f，量级差异大属正常，瞄一眼）"
                              % (name, u, min(ps), max(ps)))
    return (not issues), issues


def read_sheets(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {n: [list(r) for r in wb[n].iter_rows(values_only=True)] for n in wb.sheetnames}
    wb.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑路径里含这个词的")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = collect(a.only)
    done = load_done()
    skipped = [p for p in files if p in done]
    files = [p for p in files if p not in done]
    if skipped:
        log("断点续跑：已完成 %d 份，跳过" % len(skipped))
    if a.limit:
        files = files[:a.limit]
    log("待跑清单 %d 份" % len(files))
    results = []
    t_all = time.time()
    for i, p in enumerate(files, 1):
        name = project_name(p)
        t0 = time.time()
        try:
            # 项目名显式传进去：既让 Excel 封面/导出目录带上分组名，
            # 也保证同名清单（三个分组下的「线缆管材类」）不会互相覆盖
            r = foursheet.run(p, {"项目名称": name}, export=True,
                              out_name="1.成本测算六件套.xlsx")
            sheets = read_sheets(r["四件套文件"])
            ok, issues = sanity(sheets)
            h = r.get("健康度") or {}
            rec = {"序号": i, "项目": name, "文件": os.path.basename(p),
                   "行数": h.get("行数"), "零价": h.get("零价项"),
                   "命中率": h.get("命中率"), "甲供C30版(万)": round(r["甲供C30版"]["总计"] / 10000, 2),
                   "不提供C30版(万)": round(r["不提供C30版"]["总计"] / 10000, 2),
                   "校验": "%d/%d" % (r["校验"]["通过数"], r["校验"]["总检查"]),
                   "自检": "通过" if ok else "；".join(issues)[:120],
                   "耗时(秒)": round(time.time() - t0, 1),
                   "输出目录": r["导出目录"], "状态": "完成"}
            log("%2d/%d %-28s %6.1fs  甲供C30 %8.2f万  自检:%s"
                % (i, len(files), name[:28], time.time() - t0,
                   rec["甲供C30版(万)"], rec["自检"]))
            mark_done(p)
            if i % 5 == 0:
                import gc
                gc.collect()
        except BaseException as e:  # noqa: BLE001
            # ⚠ 必须抓 BaseException：解析失败时 project_quote 抛的是 SystemExit，
            # 而 except Exception 抓不到它，一份坏清单会把整批任务杀掉
            rec = {"序号": i, "项目": name, "文件": os.path.basename(p),
                   "状态": "失败", "自检": str(e)[:150],
                   "耗时(秒)": round(time.time() - t0, 1)}
            log("%2d/%d %-28s 失败：%s" % (i, len(files), name[:28], str(e)[:110]))
            log(traceback.format_exc()[-500:])
        results.append(rec)

    # 汇总表
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "批量汇总"
    heads = ["序号", "项目", "文件", "行数", "零价", "命中率", "甲供C30版(万)",
             "不提供C30版(万)", "校验", "自检", "耗时(秒)", "状态", "输出目录"]
    ws.append(["共享资料库 · 采购清单批量测算汇总"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(heads))
    ws.cell(row=1, column=1).font = Font(name=F, size=14, bold=True, color="1F3864")
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    ws.append(heads)
    for r in results:
        ws.append([r.get(h) for h in heads])
    tot = sum(r.get("甲供C30版(万)") or 0 for r in results)
    ws.append(["", "合计（%d 份，成功 %d）" % (len(results),
                                        sum(1 for r in results if r.get("状态") == "完成")),
               "", "", "", "", round(tot, 2), "", "", "", "",
               "", ""])
    for i, w in enumerate([5, 30, 30, 7, 7, 9, 15, 16, 9, 60, 10, 8, 46], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.value is None:
                continue
            c.font = Font(name=F, size=10)
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=True)
    for c in ws[2]:
        c.font = Font(name=F, size=10, bold=True)
        c.fill = HEAD
    for row in ws.iter_rows(min_row=3):
        st = row[11].value if len(row) > 11 else ""
        if st == "失败":
            for c in row:
                c.fill = RED
        elif (row[9].value or "") != "通过":
            for c in row:
                c.fill = YEL
    out = os.path.join(OUT_ROOT, "00_批量汇总.xlsx")
    wb.save(out)
    log("汇总表：%s" % out)
    log("总耗时 %.0f 秒（%.1f 分钟）" % (time.time() - t_all, (time.time() - t_all) / 60))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
