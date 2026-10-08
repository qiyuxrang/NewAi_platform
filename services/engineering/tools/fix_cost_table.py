# -*- coding: utf-8 -*-
"""修正用户用提示词生成的《3.成本测算表（甲供混凝土版）》：
  修正口径（甲供设备不进管理费基数、混凝土只计人工）、补交通安措、补漏项、
  补取费链与合计、重写注意事项。
用法：  .venv\\Scripts\\python.exe tools\\fix_cost_table.py
输出：  桌面\\成本测算输出\\210项目EPC段道路照明系统工程量清单\\3.成本测算表（甲供混凝土版_修正v2）.xlsx
"""
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = r"C:\Users\123\Desktop\成本测算输出\210项目EPC段道路照明系统工程量清单"
NAME = "3.成本测算表（甲供混凝土版_修正v2）.xlsx"

N, ND = 2431, 610            # 路灯座数 / 拆除处数
THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
F = "微软雅黑"
HEAD = PatternFill("solid", fgColor="D9E1F2")
YEL = PatternFill("solid", fgColor="FFF2CC")
GREY = PatternFill("solid", fgColor="F2F2F2")

# 甲供设备参考价（甲方采购，仅列示、不计入我方报价）
SUPPLIED = [
    ("LED 灯具", "LED 200W / DC24V", 2431, "套", 1200),
    ("单臂灯杆", "H12m，热镀锌喷塑", 2431, "套", 2500),
    ("FVL 导线", "FVL-450/500V-2.5mm²", 19448, "米", 3.5),
    ("BV 导线", "BV-450/500V-2.5mm²", 9771, "米", 3.2),
    ("太阳能锂电池", "DC24V 140Ah（每座 2 块）", 4862, "套", 5500),
    ("单晶硅光伏板", "250WP", 4862, "套", 800),
    ("灌胶树脂绝缘盒", "防水密封型", 2431, "个", 25),
    ("穿刺线夹", "绝缘穿刺型", 4815, "个", 8),
    ("C15 混凝土（垫层）", "0.09m³/座", 2431, "座", 0.09 * 280),
    ("C30 混凝土（基础主体）", "2.057m³/座", 2431, "座", 2.057 * 280),
    ("HRB400E 钢筋", "103kg/座（甲供）", 2431, "座", 103 / 1000 * 3500),
    ("M27 地脚螺栓预埋件", "热镀锌，含法兰", 2431, "套", 160),
    ("接地装置", "40×4 扁钢 + φ50×2.5m 接地棒", 2055, "组", 150),
    ("单灯控制器", "LED 路灯单灯控制器", 2431, "套", 180),
    ("集中控制器", "含远程管理", 17, "套", 3500),
    ("路灯管理机", "含控制软件", 1, "套", 28000),
]

# 我方采购辅材
AUX = [
    ("DN63 PVC-C 穿线管", "壁厚≥3.0mm", 12155, "米", 20),
    ("定位箍 Φ10 圆钢", "钢筋定位", 2431, "套", 3),
    ("M27 配套螺母垫片", "双螺母 + 双垫片", 2431, "套", 8),
    ("防水密封材料", "管口与接线防水", 2431, "套", 5),
    ("扎丝及焊条", "绑扎扎丝、接地焊接焊条", 2431, "套", 8),
    ("切割片及磨片", "切割、打磨耗材", 2431, "套", 4),
]

# 劳务（只计人工与机械；甲供混凝土只计浇筑人工）
LABOR = [
    ("土方综合施工", "基坑开挖、清底、外运、夯实", N, "座", 250),
    ("钢筋加工绑扎", "HRB400E 钢筋加工绑扎（钢筋甲供）", N, "座", 120),
    ("预埋件安装定位", "地脚螺栓定位、法兰调平（预埋件甲供）", N, "座", 60),
    ("模板安拆", "基础模板支设与拆除", N, "座", 120),
    ("C30 混凝土浇筑及养护", "只计浇筑养护人工与机械（C30 甲供，材料不计）", N, "座", 340),
    ("C15 垫层浇筑", "只计浇筑人工（C15 甲供，材料不计）", N, "座", 25),
    ("12m 灯杆安装", "吊装、校正、紧固（灯杆甲供）", N, "座", 280),
    ("LED 灯具安装", "安装接线调试（灯具甲供）", N, "座", 60),
    ("光伏板安装", "安装接线（光伏板甲供）", 4862, "套", 50),
    ("锂电池安装", "安装接线（电池甲供）", 4862, "套", 40),
    ("灌胶树脂盒安装", "安装与灌胶密封", N, "个", 10),
    ("穿刺线夹安装", "安装接线", 4815, "个", 3),
    ("单灯控制器安装", "安装调试", N, "套", 15),
    ("集中控制器安装", "安装调试", 17, "套", 120),
    ("路灯管理机安装", "含软件安装调试", 1, "套", 1500),
    ("FVL 导线敷设", "导线敷设（导线甲供）", 19448, "米", 1.2),
    ("BV 导线敷设", "导线敷设（导线甲供）", 9771, "米", 1.0),
    ("接地装置安装", "**原表漏项，本次补入**", 2055, "组", 45),
    ("拆除旧路灯、废弃立杆", "含机械、外运、场地清理（原 160 元/处偏低，按 480 元/处）",
     ND, "处", 480),
]

MEASURE = [("路障/锥桶/警示牌布撤", 70), ("摇旗指挥", 120), ("安全警戒瞭望", 40),
           ("夜间警示设施", 25), ("作业区清理恢复", 40)]
SPECIAL_GEOLOGY = 122 * 800


def money(ws, row, col, value, bold=False, color="000000", fill=None):
    c = ws.cell(row=row, column=col, value=value)
    c.font = Font(name=F, size=10, bold=bold, color=color)
    c.border = BORDER
    c.alignment = Alignment(vertical="center", wrap_text=True)
    if isinstance(value, (int, float)):
        c.number_format = "#,##0.00"
    if fill:
        c.fill = fill
    return c


def style(ws, widths, header_row=2, dyn_from=3, wrap_cols=None):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            c.font = Font(name=F, size=10)
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=True)
    for c in ws[header_row]:
        if c.value is not None:
            c.font = Font(name=F, size=10, bold=True)
            c.fill = HEAD
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    import math
    for r in range(dyn_from, ws.max_row + 1):
        lines = 1
        for i in range(1, len(widths) + 1):
            v = ws.cell(row=r, column=i).value
            if v is None or (wrap_cols and i not in wrap_cols):
                continue
            lines = max(lines, math.ceil(len(str(v)) / max(6, widths[i - 1] / 2.1)))
        ws.row_dimensions[r].height = lines * 14 + 8


def main():
    os.makedirs(OUT, exist_ok=True)
    wb = Workbook()

    # ── Sheet1 成本汇总（修正版）──
    ws = wb.active
    ws.title = "成本汇总（修正版）"
    ws["A1"] = "210 国道 EPC 段道路照明工程　成本测算汇总（修正版）"
    ws.merge_cells("A1:G1")
    ws["A1"].font = Font(name=F, size=13, bold=True, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28
    ws["A2"] = "口径：甲供 C30 版（C30 混凝土由甲方提供，材料费不计入我方任何费用）"
    ws.merge_cells("A2:G2")
    ws["A2"].font = Font(name=F, size=9, italic=True, color="C00000")
    for i, h in enumerate(["序号", "费用类别", "说明", "数量", "单位", "单价（元）", "合价（元）"], 1):
        ws.cell(row=3, column=i, value=h)

    labor_sum = sum(q * u for _, _, q, _, u in LABOR)
    aux_sum = sum(q * u for _, _, q, _, u in AUX)
    measure_sum = sum(v for _, v in MEASURE) * N
    direct = labor_sum + aux_sum + measure_sum + SPECIAL_GEOLOGY
    degrade = direct * 0.06
    risk = direct * 0.04
    sub = direct + degrade + risk
    manage = sub * 0.10
    subtotal2 = sub + manage
    tax = subtotal2 * 0.03
    total = subtotal2 + tax
    supplied_sum = sum(q * u for _, _, q, _, u in SUPPLIED)

    r = 4
    rows = [
        ("一、我方报价范围（甲供 C30 版）", "", "", "", None),
        ("劳务成本", "详见「劳务成本」sheet（只计人工与机械）", 1, "项", labor_sum),
        ("我方采购辅材", "详见「我方采购辅材」sheet", 1, "项", aux_sum),
        ("交通安措（必选，单列）", "295 元/座 × 2431 座，明细见「交通安措」sheet", N, "座", measure_sum),
        ("特殊地质基础开挖", "122 座 × 800 元/座（清单口径）", 122, "座", SPECIAL_GEOLOGY),
        ("直接费小计", "劳务 + 辅材 + 安措 + 特殊地质", "", "", direct),
        ("人工降效与窝工", "直接费 × 6%（边通车分段跳槽、间断作业）", "", "", degrade),
        ("不可预见风险包干", "直接费 × 4%", "", "", risk),
        ("管理费", "（直接费 + 降效 + 风险）× 10%", "", "", manage),
        ("税金", "简易计税 3%", "", "", tax),
        ("我方报价合计（含税）", "折合 %.0f 元/座" % (total / N), "", "", total),
        ("二、甲供设备（甲方采购，仅列示参考）", "", "", "", None),
        ("甲供设备参考价", "不计入我方报价，也不作为任何取费基数", 1, "项", supplied_sum),
    ]
    for i, (a, b, c2, d, e) in enumerate(rows, 1):
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=a)
        ws.cell(row=r, column=3, value=b)
        ws.cell(row=r, column=4, value=c2)
        ws.cell(row=r, column=5, value=d)
        if isinstance(e, (int, float)):
            ws.cell(row=r, column=7, value=e)
        if a.startswith(("一、", "二、")) or "合计" in a or "小计" in a:
            for k in range(1, 8):
                ws.cell(row=r, column=k).fill = YEL
        if "报价合计" in a:
            ws.cell(row=r, column=7).font = Font(name=F, size=11, bold=True, color="C00000")
        r += 1
    r += 1

    notes = [
        "【口径说明】",
        "1. 本表为「甲供 C30 版」：C30 混凝土与 C15 垫层混凝土由甲方提供，材料费不计入我方任何费用，劳务中只计浇筑人工。",
        "2. 甲供设备（灯具/灯杆/光伏板/锂电池/控制器/导线/接地/钢筋/预埋件等）只列参考价，**不计入我方报价，也不作为管理费、降效、风险的取费基数**（原表按甲供设备计取了 8% 管理费，属重复取费，本次已剔除）。",
        "3. 取费链条：降效与窝工 6%（基数=我方直接费）→ 不可预见风险 4%（同基数）→ 管理费 10%（基数=直接费+降效+风险）→ 税金 3%（简易计税）。",
        "4. 交通安措为必选项、单列计取：295 元/座（路障布撤 70 + 摇旗指挥 120 + 安全警戒瞭望 40 + 夜间警示设施 25 + 作业区清理恢复 40）。",
        "",
        "【本次修正内容（相对原表）】",
        "5. 原表「C30 混凝土浇筑 534.82 元/座」「C15 垫层 25.41 元/座」实际是材料价（2.057×280 与 0.09×280），在甲供版里属口径错误，已改为只计人工：C30 浇筑 340 元/座、C15 浇筑 25 元/座。",
        "6. 原表漏「接地装置安装」劳务（2055 组，45 元/组），已补入。",
        "7. 原表拆除旧路灯按 160 元/处（9.76 万），与参考口径（480 元/处、29.3 万）差 3 倍，已按 480 元/处修正。",
        "8. 原表缺交通安措（295 元/座、71.7 万），已单列补入。",
        "9. 原表「合计」行为空未计算，本表全部逐级勾稽（数量×单价=合价、分部小计、取费链、总价）。",
        "10. 原表管理费说明写「按前三项之和的 8%」，实际把第 4 项特殊地质也纳入了基数，说明与算法不一致，本表按取费链重算并写明基数。",
        "",
        "【风险与责任条款（对外提交时须保留）】",
        "11. 甲供材卸车、保管与场内二次搬运由我方负责；甲供材安装损耗超过 2% 的部分按材料价扣赔。",
        "12. C30 到场价波动 ±5% 以外按信息价调差，不调整取费；我方采购 C30 按 2% 以内损耗包干。",
        "13. 边通车施工须报批导改方案并配备持证交通引导员；因导改审批延误的工期相应顺延。",
        "14. 计量与支付：月计量支付 80%，完工验收支付 95%，余 5% 为质保金，质保期满无息退还。",
        "15. 报价有效期 30 天；人工基准期为本报价期，人工单价波动 ±10% 以外按实调整。",
        "16. 工期节点：开工后 90 日历天完成基础及立杆 80%，120 日历天完工；混凝土浇筑后养护不少于 3 天。",
        "17. 可选项（暂不计入总额，按现场签证）：硬地层破碎 80 元/m³×500、夜间施工补贴 300 元/工日×150、管制窝工 1800 元/队·日×120、吊车待机 1800 元/台班×40、管线探测配合 200 元/处×50、临时占地围挡 18 元/m²×800。",
        "18. 谈判区间：底线为报价 ×(1−10%~12%)；推荐签约区间为 ±2%~4%；条件切换项——劳务方自带安措器材可降 40~55 元/座。",
        "",
        "【交叉校核】",
        "19. 队日模型校核：15 人队日人工 4240 元 + 挖机台班 800 + 小机具 150 + 交通器材 350 = 5540 元/队·日，日完成 2.5 座 → 纯成本 2216 元/座（全项目约 538.7 万）。",
        "20. 本表劳务（不含拆除）折合 %.0f 元/座，与队日模型的 2216 元/座相差 %.0f 元/座——差异来自人工单价口径（本表用市场包工价，队日模型含机械与器材摊销），对外报价建议以本表为准、用队日模型做下限校核。" % (
            (labor_sum - ND * 480) / N, 2216 - (labor_sum - ND * 480) / N),
    ]
    for t in notes:
        ws.cell(row=r, column=1, value=t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        ws.cell(row=r, column=1).alignment = Alignment(vertical="center", wrap_text=True)
        ws.cell(row=r, column=1).font = Font(name=F, size=10,
                                             bold=t.startswith("【"))
        ws.cell(row=r, column=1).border = BORDER
        ws.row_dimensions[r].height = max(16, (len(t) // 62 + 1) * 15 + 4)
        r += 1
    style(ws, [6, 24, 52, 8, 8, 12, 16], header_row=3, dyn_from=4, wrap_cols={2, 3})

    # ── 各明细 sheet ──
    def detail(title, rows, note=None):
        w = wb.create_sheet(title[:31])
        w["A1"] = "210 国道 EPC 段道路照明工程　" + title
        w.merge_cells("A1:G1")
        w["A1"].font = Font(name=F, size=12, bold=True, color="1F3864")
        w["A1"].alignment = Alignment(horizontal="center", vertical="center")
        w.row_dimensions[1].height = 24
        for i, h in enumerate(["序号", "名称", "规格 / 说明", "数量", "单位", "单价（元）", "合价（元）"], 1):
            w.cell(row=2, column=i, value=h)
        rr = 3
        for i, (nm, spec, qty, unit, price) in enumerate(rows, 1):
            w.cell(row=rr, column=1, value=i)
            w.cell(row=rr, column=2, value=nm)
            w.cell(row=rr, column=3, value=spec)
            w.cell(row=rr, column=4, value=qty)
            w.cell(row=rr, column=5, value=unit)
            w.cell(row=rr, column=6, value=round(price, 2))
            w.cell(row=rr, column=7, value=round(qty * price, 2))
            rr += 1
        w.cell(row=rr, column=2, value="合　计")
        w.cell(row=rr, column=7, value=round(sum(q * u for _, _, q, _, u in rows), 2))
        for k in range(1, 8):
            w.cell(row=rr, column=k).fill = YEL
            w.cell(row=rr, column=k).font = Font(name=F, size=10, bold=True)
        if note:
            rr += 2
            w.cell(row=rr, column=1, value=note)
            w.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=7)
        style(w, [6, 26, 46, 10, 8, 12, 16], header_row=2, dyn_from=3, wrap_cols={2, 3})
        return w

    detail("甲供设备（参考价，不计入报价）", SUPPLIED,
           "注：本页为甲方采购设备的参考价，仅用于成本对照，不计入我方报价，也不作为取费基数。")
    detail("我方采购辅材", AUX, "注：辅材由我方采购，计入报价，走取费链条。")
    detail("劳务成本", LABOR,
           "注：劳务只计人工与机械；甲供材料（灯具/灯杆/电池/导线/钢筋/混凝土等）不计材料费；接地安装与拆除单价已按修正口径调整。")
    m = detail("交通安措", [(nm, "边通车边施工必备", N, "座", v) for nm, v in MEASURE],
               "注：必选项，按座计取，合计 295 元/座 × 2431 座 = %.2f 元。" % measure_sum)

    # 测算底稿
    d = wb.create_sheet("测算底稿")
    d["A1"] = "测算底稿（取费链条 · 谈判区间 · 交叉校核）"
    d.merge_cells("A1:D1")
    d["A1"].font = Font(name=F, size=12, bold=True, color="1F3864")
    for i, h in enumerate(["项目", "口径 / 计算式", "数值", "说明"], 1):
        d.cell(row=2, column=i, value=h)
    draft = [
        ("我方直接费", "劳务 + 辅材 + 安措 + 特殊地质", direct, ""),
        ("降效窝工", "直接费 × 6%", degrade, "边通车分段跳槽、间断作业降效"),
        ("不可预见风险", "直接费 × 4%", risk, "包干"),
        ("管理费", "(直接费+降效+风险) × 10%", manage, ""),
        ("税金", "简易计税 3%", tax, ""),
        ("我方报价合计（含税）", "逐级累加", total, "折合 %.0f 元/座" % (total / N)),
        ("甲供设备参考价", "不计入我方报价、不作取费基数", supplied_sum, "仅列示"),
        ("队日模型纯成本", "5540 元/队·日 ÷ 2.5 座", 2216.0, "全项目约 %.1f 万" % (2216 * N / 1e4)),
        ("底线区间", "报价 ×(1−10%~12%)",
         "%.0f ~ %.0f 万" % (total * 0.88 / 1e4, total * 0.90 / 1e4), "谈判底线"),
        ("推荐签约区间", "报价 ±2%~4%",
         "%.0f ~ %.0f 万" % (total * 0.98 / 1e4, total * 1.02 / 1e4), ""),
        ("可选项合计（×1.13）", "按现场签证",
         0.0 if True else 0, "硬地层、夜间、窝工、吊车待机、管线探测、临时围挡"),
    ]
    aux_opt = (80 * 500 + 300 * 150 + 1800 * 120 + 1800 * 40 + 200 * 50 + 18 * 800) * 1.13
    draft[-1] = ("可选项合计（×1.13）", "按现场签证", round(aux_opt, 2), "硬地层、夜间、窝工、吊车待机、管线探测、临时围挡")
    rr = 3
    for a, b, c2, d2 in draft:
        d.cell(row=rr, column=1, value=a)
        d.cell(row=rr, column=2, value=b)
        d.cell(row=rr, column=3, value=c2)
        d.cell(row=rr, column=4, value=d2)
        rr += 1
    style(d, [22, 40, 18, 34], header_row=2, dyn_from=3, wrap_cols={2, 4})

    path = os.path.join(OUT, NAME)
    wb.save(path)
    print("已生成：", path)
    print("劳务合计 %.2f | 辅材 %.2f | 安措 %.2f | 直接费 %.2f" % (labor_sum, aux_sum, measure_sum, direct))
    print("取费 %.2f | 我方报价合计 %.2f 元（%.0f 元/座）" % (degrade + risk + manage + tax, total, total / N))
    print("甲供设备参考价 %.2f（不计入报价）" % supplied_sum)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
