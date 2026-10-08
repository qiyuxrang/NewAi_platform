# -*- coding: utf-8 -*-
"""太阳能路灯项目专用测算与交付文件生成（210 国道照明 EPC 段）。

产出（默认写到 data/output/太阳能路灯项目/）：
    1.设备清单（分甲供与我方采购）.xlsx
    2.劳务清单（按施工分类）.xlsx
    3.成本测算表（两口径）.xlsx
    4.对外劳务报价清单（甲供C30版）.xlsx
    5.对外劳务报价清单（甲方不提供C30版）.xlsx
    6.设备采购责任分类表.xlsx

全部数字由代码计算，逐级勾稽；格式规范按用户要求（微软雅黑 / thin 全边框 /
wrap_text / 列宽与动态行高 / 指定底色与命名）。
"""
import math
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "output", "太阳能路灯项目")

# ─────────────────────────── 项目参数（全部可改） ───────────────────────────
P = {
    "项目名称": "210国道西安过境下大寨至侯官寨公路照明工程（EPC段）",
    "灯型": "12m 单臂太阳能路灯",
    "路灯数量": 2431,          # 座
    "拆除数量": 610,           # 处
    "基础尺寸": "1100×1100×1700mm",
    "C30单座": 2.057,          # m³/座
    "C30损耗": 1.02,
    "C15单座": 0.09,           # m³/座（垫层，甲供）
    "钢筋单座": 103,           # kg/座（HRB400E，甲供）
    "C30到场价": 280,          # 元/m³
    # 工种配置：人数 × 日单价
    "工种": [
        ("小工", 5, 200),
        ("钢筋工", 2, 330),
        ("木工", 1, 330),
        ("电工/信号司索", 3, 350),
        ("挖机司机", 1, 450),
        ("专职交通引导员", 2, 200),
        ("班组长", 1, 350),
    ],
    "挖机台班摊": 800,         # 元/队·日
    "小机具耗材": 150,
    "交通器材折旧": 350,
    "日完成座数": 2.5,         # 边通车跳槽施工
    "每座工日": 11,            # 定额口径校核用
    # 交通安措（必选，按座）
    "安措明细": [("路障/锥桶/警示牌布撤", 70), ("摇旗指挥", 120),
                 ("安全警戒瞭望", 40), ("夜间警示设施", 25),
                 ("作业区清理恢复", 40)],
    # 取费
    "降效率": 0.06,
    "风险率": 0.04,
    "管理费率": 0.10,
    "税率": 0.03,
    "材料采购管理费率": 0.05,
    # C30 转我方采购时，走劳务线的两项
    "C30浇筑人工": 340,        # 元/座
    "落地配合费": 65,          # 元/座（二次倒运、振捣油料、试块、养护用水）
    # 拆除
    "拆除单价": 480,           # 元/处（含机械）
    # 可选项（暂不计入总额，按现场签证）
    "可选项": [
        ("硬地层破碎", "80 元/m³", 500, 80),
        ("夜间施工补贴", "300 元/工日", 150, 300),
        ("管制窝工", "1800 元/队·日", 120, 1800),
        ("吊车待机", "1800 元/台班", 40, 1800),
        ("管线探测配合", "200 元/处", 50, 200),
        ("临时占地围挡", "18 元/m²", 800, 18),
    ],
    "工期": {"合同天数": 120, "80%节点天数": 90, "每座工日": 11,
             "单队日产": 1.2, "双挖机队日产": 2.5},
}

# 对外主体单价相对纯成本的加成：0 = 与用户参考结果一致（总价约 800 万）；
# 若想直观体现"对外留 10% 微利"，改成 0.10（总价约 864 万）。
MICRO_PROFIT = 0.0
# C30 转我方采购时，浇筑人工 340 元/座是否在劳务线里"再单列一次"。
# 主体纯成本（2216 元/座）本身已含浇筑人工，所以默认不重复计取；
# 若甲方认可单独列项，改成 True（总价约 +100 万）。
ADD_POURING_LABOR = False

WAGE_SUM = sum(n * w for _, n, w in P["工种"])
CREW_DAY = WAGE_SUM + P["挖机台班摊"] + P["小机具耗材"] + P["交通器材折旧"]
UNIT_COST = CREW_DAY / P["日完成座数"]                    # 纯成本 元/座
MEASURE_UNIT = sum(v for _, v in P["安措明细"])            # 295 元/座

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FONT = "微软雅黑"
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")        # 内部清单表头浅蓝
DARK_HEAD = PatternFill("solid", fgColor="1F3864")
YELLOW = PatternFill("solid", fgColor="FFF2CC")
BAND = {"A": PatternFill("solid", fgColor="E6F1FB"),
        "B": PatternFill("solid", fgColor="FCE4D6"),
        "C": PatternFill("solid", fgColor="E2EFDA"),
        "D": PatternFill("solid", fgColor="FAEEDA")}


def style_sheet(ws, widths, header_row=2, dynamic_from=None, wrap_cols=None,
                per_line=18, head_fill=HEAD_FILL):
    """统一排版：字体、边框、列宽、动态行高。"""
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            c.font = Font(name=FONT, size=10)
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=True)
    for c in ws[header_row]:
        if c.value is not None:
            c.font = Font(name=FONT, size=10, bold=True, color="000000")
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if dynamic_from:
        for r in range(dynamic_from, ws.max_row + 1):
            lines = 1
            for i in range(1, len(widths) + 1):
                v = ws.cell(row=r, column=i).value
                if v is None:
                    continue
                if wrap_cols and i not in wrap_cols:
                    continue
                per = max(6, int(widths[i - 1] / 2.1))
                lines = max(lines, math.ceil(len(str(v)) / per))
            ws.row_dimensions[r].height = lines * 14 + 8


def calc_versions():
    """两口径的取费链，逐级可复算。"""
    n, nd = P["路灯数量"], P["拆除数量"]
    main = UNIT_COST * (1 + MICRO_PROFIT)          # 对外主体单价（默认 = 纯成本）
    main_sum = main * n
    measure = MEASURE_UNIT * n
    demolish = P["拆除单价"] * nd
    m3 = n * P["C30单座"] * P["C30损耗"]
    material = m3 * P["C30到场价"]

    def chain(direct):
        degrade = direct * P["降效率"]
        risk = direct * P["风险率"]
        sub = direct + degrade + risk
        manage = sub * P["管理费率"]
        sub2 = sub + manage
        tax = sub2 * P["税率"]
        return {"直接费": direct, "降效窝工": degrade, "不可预见风险": risk,
                "管理费": manage, "税金": tax, "合计": sub2 + tax,
                "取费小计": degrade + risk + manage + tax}

    # 甲供 C30：C30 与钢筋均为甲供，不进我方任何费用
    a_direct = main_sum + measure + demolish
    a = chain(a_direct)

    # 甲方不提供 C30：材料线单独取费；C30 浇筑人工与落地配合费走劳务线
    pour = P["C30浇筑人工"] * n if ADD_POURING_LABOR else 0.0
    b_direct_labor = (main_sum + pour + P["落地配合费"] * n
                      + measure + demolish)
    b_labor = chain(b_direct_labor)
    b_material = material * (1 + P["材料采购管理费率"]) * (1 + P["税率"])
    b_total = b_labor["合计"] + b_material
    return {
        "甲供C30": {
            "主体": main_sum, "安措": measure, "拆除": demolish,
            "直接费": a_direct, "降效窝工": a["降效窝工"], "不可预见风险": a["不可预见风险"],
            "管理费": a["管理费"], "税金": a["税金"], "取费小计": a["取费小计"],
            "总计": a["合计"], "单价每座": a["合计"] / n,
            "主体单价": main, "材料款": 0.0, "C30方量": m3,
        },
        "不提供C30": {
            "主体": main_sum, "安措": measure, "拆除": demolish,
            "浇筑人工": pour, "浇筑人工单列": ADD_POURING_LABOR,
            "落地配合": P["落地配合费"] * n,
            "劳务线直接费": b_direct_labor,
            "劳务线取费": b_labor["取费小计"], "劳务线含税": b_labor["合计"],
            "材料款": material, "材料线含税": b_material, "C30方量": m3,
            "总计": b_total, "单价每座": b_total / n,
            "材料采购管理费": material * P["材料采购管理费率"],
            "材料线税金": b_material - material * (1 + P["材料采购管理费率"]),
        },
        "纯成本每座": UNIT_COST, "队日": CREW_DAY, "人工日": WAGE_SUM,
        "微利单价": main, "对外主体单价": main,
    }


# ─────────────────────────── 设备清单（甲供 / 我方采购） ───────────────────────────
DEVICES = [
    ("主设备（甲供）", [
        ("LED 灯具", "200W，DC24V，含光源驱动", "2431", "套", "甲供"),
        ("太阳能路灯灯杆", "单臂，H=12m，热镀锌喷塑", "2431", "套", "甲供"),
        ("单晶硅光伏组件", "峰值功率 250WP", "2431", "套", "甲供"),
        ("光伏专用锂电池", "DC24V / 140Ah（每座 2 块）", "4862", "块", "甲供"),
        ("路灯控制器", "LED 单灯控制器", "2431", "套", "甲供"),
        ("路灯集中控制器", "含远程管理", "17", "套", "甲供"),
        ("导线", "BV-450/500V-2.5mm²、FVL-450/500V", "29219", "m", "甲供"),
        ("灌胶树脂绝缘盒", "配套灯具接线", "2431", "个", "甲供"),
        ("穿刺线夹", "配套导线分支", "4815", "个", "甲供"),
        ("钢筋", "HRB400E，103kg/座", "250.4", "t", "甲供"),
        ("地脚螺栓预埋件", "M27 热镀锌，含法兰", "2431", "套", "甲供"),
        ("接地装置", "40×4 扁钢 + φ50×2.5m 接地棒，成套", "2055", "组", "甲供"),
        ("C15 混凝土（垫层）", "0.09m³/座", "218.8", "m³", "甲供"),
    ]),
    ("甲方不提供→转我方采购", [
        ("C30 混凝土", "基础主体，2.057m³/座，到场价 280 元/m³", "5101", "m³", "我方采购"),
    ]),
    ("我方采购辅材", [
        ("电力穿线管", "DN63 PVC 预埋穿线管（甲供材预埋用）", "12155", "m", "我方采购"),
        ("定位箍 / 加固件", "模板与钢筋定位用", "2431", "套", "我方采购"),
        ("螺栓垫片及防腐", "地脚螺栓配套垫片、防腐漆", "2431", "套", "我方采购"),
        ("防水密封材料", "灯杆法兰及接线盒防水密封", "2431", "套", "我方采购"),
        ("杂项耗材", "扎带、绝缘胶带、焊条、模板辅材等", "2431", "座", "我方采购"),
    ]),
    ("劳务方自备", [
        ("安全帽 / 反光背心 / 劳保", "作业人员劳动保护", "2431", "座", "劳务自备"),
        ("手动工具及小机具", "扳手、切割、振捣等小型机具", "2431", "座", "劳务自备"),
        ("交通安措器材", "锥桶、警示牌、爆闪灯（折旧摊销）", "2431", "座", "劳务自备"),
        ("测量放线工具", "水平仪、卷尺、线绳", "2431", "座", "劳务自备"),
        ("现场清理工具", "清扫、绿化恢复用具", "2431", "座", "劳务自备"),
    ]),
]


def build_devices(path):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in DEVICES:
        ws = wb.create_sheet(name[:31])
        ws["A1"] = "%s　%s" % (P["项目名称"], name)
        ws.merge_cells("A1:E1")
        ws["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26
        for i, h in enumerate(["序号", "设备名称", "技术参数", "数量", "单位"], 1):
            ws.cell(row=2, column=i, value=h)
        for k, r in enumerate(rows, 1):
            ws.cell(row=2 + k, column=1, value=k)
            for i, v in enumerate(r[:4], 2):
                ws.cell(row=2 + k, column=i, value=v)
        style_sheet(ws, [6, 22, 46, 10, 8], header_row=2, dynamic_from=3,
                    wrap_cols={3})
        ws.freeze_panes = "A3"
    wb.save(path)
    return path


def build_labor_list(path):
    """劳务清单：按施工分类分 sheet。"""
    q = 12                          # 综合工日折算（定额口径参考）
    cats = [
        ("基础工程", [
            ("土方开挖（含清底、倒运、夯实）", "座", P["路灯数量"], "按基础 1.1×1.1×1.7m 计"),
            ("钢筋制作与绑扎", "座", P["路灯数量"], "103kg/座，甲供钢筋"),
            ("模板安拆", "座", P["路灯数量"], "含对拉螺杆等辅材"),
            ("C30 混凝土浇筑及养护", "座", P["路灯数量"], "2.057m³/座，养护≥3 天"),
        ]),
        ("灯杆与灯具安装", [
            ("灯杆吊装就位、找正、地脚螺栓紧固", "套", P["路灯数量"], "12m 单臂"),
            ("灯具安装与接线", "套", P["路灯数量"], "LED 200W/DC24V"),
            ("光伏组件安装", "套", P["路灯数量"], "250WP"),
            ("锂电池安装（每座 2 块）", "座", P["路灯数量"], "140Ah/DC24V"),
            ("控制器安装与参数设置", "套", P["路灯数量"], "单灯 + 集中"),
        ]),
        ("电气与接地", [
            ("导线敷设与接头", "座", P["路灯数量"], "含灌胶盒、穿刺线夹"),
            ("接地装置安装", "组", 2055, "40×4 扁钢 + φ50×2.5m 接地棒"),
            ("成套调试与试运行", "座", P["路灯数量"], "含 72 小时试运行"),
        ]),
        ("拆除", [
            ("拆除旧路灯及废弃立杆", "处", P["拆除数量"], "含机械、外运"),
        ]),
        ("措施与安措", [
            ("安全文明及措施费", "座", P["路灯数量"], "按直接费比例计取"),
            ("交通安措（必选，单列）", "座", P["路灯数量"], "295 元/座，五项明细"),
        ]),
    ]
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in cats:
        ws = wb.create_sheet(name[:31])
        ws["A1"] = "%s　劳务清单—%s" % (P["项目名称"], name)
        ws.merge_cells("A1:E1")
        ws["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26
        for i, h in enumerate(["序号", "设备名称", "技术参数", "数量", "单位"], 1):
            ws.cell(row=2, column=i, value=h)
        for k, (nm, unit, qty, note) in enumerate(rows, 1):
            ws.cell(row=2 + k, column=1, value=k)
            ws.cell(row=2 + k, column=2, value=nm)
            ws.cell(row=2 + k, column=3, value=note)
            ws.cell(row=2 + k, column=4, value=qty)
            ws.cell(row=2 + k, column=5, value=unit)
        style_sheet(ws, [6, 30, 44, 10, 8], header_row=2, dynamic_from=3, wrap_cols={3})
        ws.freeze_panes = "A3"
    wb.save(path)
    return path


def build_cost_table(path, v):
    wb = Workbook()
    ws = wb.active
    ws.title = "成本测算（两口径）"
    ws["A1"] = "%s　成本测算表" % P["项目名称"]
    ws.merge_cells("A1:E1")
    ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28
    heads = ["序号", "费用项", "计算口径", "金额（元）", "折合元/座"]
    for i, h in enumerate(heads, 1):
        ws.cell(row=2, column=i, value=h)

    r = 3
    def put(name, basis, amount, base_n=P["路灯数量"]):
        nonlocal r
        ws.cell(row=r, column=1, value=r - 2)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=basis)
        ws.cell(row=r, column=4, value=round(amount, 2))
        ws.cell(row=r, column=5, value=round(amount / base_n, 2))
        if "小计" in name or "总计" in name or "合计" in name:
            for i in range(1, 6):
                ws.cell(row=r, column=i).fill = YELLOW
        r += 1

    put("一、内部口径（净劳务，甲供 C30）", "", 0)
    put("　队日综合费用", "人工 %d + 挖机台班 %d + 小机具 %d + 交通器材 %d"
        % (WAGE_SUM, P["挖机台班摊"], P["小机具耗材"], P["交通器材折旧"]), CREW_DAY, 1)
    put("　队日完成量", "边通车分段跳槽施工", P["日完成座数"], 1)
    put("　纯成本", "队日费用 ÷ 日完成量", UNIT_COST, 1)
    put("　全项目纯成本", "纯成本 × %d 座" % P["路灯数量"], UNIT_COST * P["路灯数量"])
    put("二、对外报价—甲供 C30 口径", "", 0)
    put("　主体工程", "纯成本 %d 元/座 ×(1+%.0f%%) ×%d 座"
        % (UNIT_COST, MICRO_PROFIT * 100, P["路灯数量"]), v["甲供C30"]["主体"])
    put("　交通安措（必选）", "295 元/座 × %d 座" % P["路灯数量"], v["甲供C30"]["安措"])
    put("　拆除旧路灯", "480 元/处 × %d 处" % P["拆除数量"], v["甲供C30"]["拆除"])
    put("　直接费小计", "主体 + 安措 + 拆除", v["甲供C30"]["直接费"])
    put("　人工降效与窝工", "直接费 × 6%", v["甲供C30"]["降效窝工"])
    put("　不可预见风险包干", "直接费 × 4%", v["甲供C30"]["不可预见风险"])
    put("　管理费", "(直接费+降效+风险) × 10%", v["甲供C30"]["管理费"])
    put("　税金", "简易计税 3%", v["甲供C30"]["税金"])
    put("　报价总计（甲供 C30）", "含税总价", v["甲供C30"]["总计"])
    put("三、对外报价—甲方不提供 C30", "", 0)
    put("　劳务线直接费", "主体 + 浇筑人工 + 落地配合 + 安措 + 拆除",
        v["不提供C30"]["劳务线直接费"])
    put("　劳务线取费合计", "降效 6% + 风险 4% + 管理费 10% + 税金 3%",
        v["不提供C30"]["劳务线取费"])
    put("　劳务线含税", "劳务线直接费 + 取费", v["不提供C30"]["劳务线含税"])
    put("　C30 材料款", "%.0f m³ × 280 元/m³" % v["不提供C30"]["C30方量"],
        v["不提供C30"]["材料款"])
    put("　材料线含税", "材料款 ×1.05（采购管理费）×1.03（税）",
        v["不提供C30"]["材料线含税"])
    put("　报价总计（不提供 C30）", "劳务线 + 材料线", v["不提供C30"]["总计"])
    style_sheet(ws, [6, 28, 46, 16, 14], header_row=2, dynamic_from=3, wrap_cols={3})
    ws.freeze_panes = "A3"

    # 第二个 sheet：工期与资源配置分析
    ws2 = wb.create_sheet("工期与资源配置")
    ws2["A1"] = "%s　工期与资源配置分析" % P["项目名称"]
    ws2.merge_cells("A1:E1")
    ws2["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws2.row_dimensions[1].height = 28
    for i, h in enumerate(["队数", "日产量（座/天）", "完成 %d 座需要（天）" % P["路灯数量"],
                           "人工峰值（人）", "挖机（台）"], 1):
        ws2.cell(row=2, column=i, value=h)
    g = P["工期"]
    rows = []
    for crews, daily in ((10, 13.5), (12, 16.2), (14, 18.9), (15, 21.7)):
        days = P["路灯数量"] / daily
        rows.append((crews, daily, round(days, 1), crews * 15, crews))
    for k, (crews, daily, days, ppl, dig) in enumerate(rows, 1):
        ws2.cell(row=2 + k, column=1, value=crews)
        ws2.cell(row=2 + k, column=2, value=daily)
        ws2.cell(row=2 + k, column=3, value=days)
        ws2.cell(row=2 + k, column=4, value=ppl)
        ws2.cell(row=2 + k, column=5, value=dig)
        ws2.cell(row=2 + k, column=2).fill = YELLOW
    r = 2 + len(rows) + 2
    notes = [
        "单座综合工日 ≈ %d 工日（定额口径校核），全项目 ≈ %.1f 万工日（含拆除与调试摊销）。"
        % (g["每座工日"], P["路灯数量"] * g["每座工日"] / 1e4),
        "单作业队人工上限 ≈ %.1f 座/天；配双挖机、双作业面的队 ≈ %.1f 座/天。"
        % (g["单队日产"], g["双挖机队日产"]),
        "10 队常规配置仅 12~15 座/天 → 需 180~200 天，超过 %d 天合同工期。" % g["合同天数"],
        "满足 %d 天完工需 14~15 队、约 210~225 人、15~28 台挖机，日均 21~22 座（日历日，含雨休与导改停歇）。"
        % g["合同天数"],
        "合同「开工后 %d 日历天完成基础及立杆 80%%」隐含上述资源配置，劳务合同须写明作业面数量；"
        "否则窝工补偿条款反被利用。" % g["80%节点天数"],
    ]
    for txt in notes:
        ws2.cell(row=r, column=1, value="• %s" % txt)
        ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1
    style_sheet(ws2, [10, 20, 26, 18, 14], header_row=2, dynamic_from=3, wrap_cols={1})
    wb.save(path)
    return path


def quote_rows(v, version):
    """对外报价清单 8 列内容（分部 → 小计）。"""
    n = P["路灯数量"]
    rows = []
    if version == "甲供C30":
        unit = v["甲供C30"]["主体单价"]
        rows.append(("一、主体工程", "", "", "", "", "", "", ""))
        rows.append((1, "基础土方与结构施工", "基坑开挖、清底、倒运、夯实；钢筋笼制作绑扎（钢筋甲供）；模板安拆",
                     "座", n, round(unit * 0.38, 2), round(unit * 0.38 * n, 2),
                     "含人工与机械，钢筋甲供不计材料"))
        rows.append((2, "C30 混凝土浇筑及养护", "垫层与主体浇筑、振捣、收面、覆盖养护（C30 甲供）",
                     "座", n, round(unit * 0.26, 2), round(unit * 0.26 * n, 2),
                     "只计人工与机械，材料甲供"))
        rows.append((3, "灯杆及灯具安装", "12m 灯杆吊装就位、灯具安装接线、光伏组件、锂电池、控制器安装调试",
                     "座", n, round(unit * 0.28, 2), round(unit * 0.28 * n, 2),
                     "设备甲供，只计安装人工与机械"))
        rows.append((4, "电气敷设与接地", "导线敷设接头、灌胶盒与穿刺线夹、接地装置、成套调试与试运行",
                     "座", n, round(unit * 0.08, 2), round(unit * 0.08 * n, 2),
                     "含 72 小时试运行"))
        rows.append(("", "小计", "", "", "", "", round(unit * n, 2),
                     "主体按纯成本 %d 元/座 × %d 座" % (UNIT_COST, n)))
        rows.append(("二、交通安措（必选，单列）", "", "", "", "", "", "", ""))
        for nm, price in P["安措明细"]:
            rows.append(("", nm, "边通车边施工必备", "座", n, price, round(price * n, 2),
                         "安措合计 %d 元/座" % MEASURE_UNIT))
        rows.append(("", "安措小计", "", "", "", MEASURE_UNIT, round(MEASURE_UNIT * n, 2), ""))
        rows.append(("三、拆除工程", "", "", "", "", "", "", ""))
        rows.append((5, "拆除旧路灯、废弃立杆", "含机械、外运、场地清理", "处", P["拆除数量"],
                     P["拆除单价"], round(P["拆除单价"] * P["拆除数量"], 2), "按处计"))
    else:
        rows.append(("一、劳务线", "", "", "", "", "", "", ""))
        rows.append((1, "主体工程（同甲供版）", "基础、浇筑、安装、电气与接地",
                     "座", n, round(v["甲供C30"]["主体单价"], 2),
                     round(v["甲供C30"]["主体"]), "按纯成本口径"))
        if v["不提供C30"]["浇筑人工单列"]:
            rows.append((2, "C30 浇筑人工", "因甲方不提供 C30 单列的浇筑人工", "座", n,
                         P["C30浇筑人工"], round(P["C30浇筑人工"] * n, 2), "走劳务取费线"))
        else:
            rows.append((2, "C30 浇筑人工", "已含在主体纯成本（%d 元/座）内，不重复计取"
                         % UNIT_COST, "座", n, 0, 0, "如需单列，改配置开关"))
        rows.append((3, "落地配合费", "二次倒运、振捣油料、试块、养护用水", "座", n,
                     P["落地配合费"], round(P["落地配合费"] * n, 2), "走劳务取费线"))
        rows.append(("", "交通安措（必选）", "同甲供版五项明细", "座", n, MEASURE_UNIT,
                     round(MEASURE_UNIT * n, 2), ""))
        rows.append(("", "拆除工程", "同甲供版", "处", P["拆除数量"], P["拆除单价"],
                     round(P["拆除单价"] * P["拆除数量"], 2), ""))
        rows.append(("", "二、材料线（C30 转我方采购）", "", "", "", "", "", ""))
        rows.append((4, "C30 混凝土材料款", "%.0f m³（含 2%% 损耗）× 280 元/m³"
                     % v["不提供C30"]["C30方量"], "m³", round(v["不提供C30"]["C30方量"], 1),
                     P["C30到场价"], round(v["不提供C30"]["材料款"], 2),
                     "只计 5% 采购管理费 + 3% 税金，不进 6%/4% 基数"))
    return rows


def build_quote(path, v, version):
    wb = Workbook()
    ws = wb.active
    ws.title = "对外劳务报价清单"
    heads = ["序号", "分项名称", "工作内容", "计量单位", "暂定工程量",
             "综合单价(元)", "合价(元)", "备注（费用归集或工日测算口径）"]
    ws["A1"] = "%s　对外劳务分包报价清单（%s）" % (
        P["项目名称"], "甲供 C30 版" if version == "甲供C30" else "甲方不提供 C30 版")
    ws.merge_cells("A1:H1")
    ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30
    for i, h in enumerate(heads, 1):
        ws.cell(row=2, column=i, value=h)
    r = 3
    for row in quote_rows(v, version):
        for i, val in enumerate(row, 1):
            ws.cell(row=r, column=i, value=val if val != "" else None)
        r += 1
    # 总额行
    total = v[version]["总计"]
    ws.cell(row=r, column=2, value="报价总额（含税）")
    ws.cell(row=r, column=7, value=round(total, 2))
    ws.cell(row=r, column=8, value="折合 %.0f 元/座（%d 座）" % (total / P["路灯数量"], P["路灯数量"]))
    for i in range(1, 9):
        c = ws.cell(row=r, column=i)
        c.fill = YELLOW
        c.font = Font(name=FONT, size=11, bold=True, color="C00000")
    r += 2
    # 可选项
    ws.cell(row=r, column=2, value="可选项（暂不计入总额，按现场签证）")
    ws.cell(row=r, column=2).font = Font(name=FONT, size=10, bold=True)
    r += 1
    for nm, price, qty, unit_price in P["可选项"]:
        ws.cell(row=r, column=2, value=nm)
        ws.cell(row=r, column=4, value=unit_price)
        ws.cell(row=r, column=5, value=qty)
        ws.cell(row=r, column=7, value=round(unit_price * qty, 2))
        ws.cell(row=r, column=8, value=price)
        r += 1
    opt_total = sum(u * q for _, _, q, u in P["可选项"])
    ws.cell(row=r, column=2, value="可选项合计（×1.13 后）")
    ws.cell(row=r, column=7, value=round(opt_total * 1.13, 2))
    r += 2
    for i, txt in enumerate(REPORT_NOTES, 1):
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=txt)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        r += 1
    style_sheet(ws, [6, 30, 70, 10, 12, 14, 16, 46], header_row=2, dynamic_from=3,
                wrap_cols={2, 3, 8})

    # 第二 sheet：测算底稿
    ws2 = wb.create_sheet("测算底稿")
    ws2["A1"] = "测算底稿（工种配置 · 队日费用 · 取费链条 · 谈判区间）"
    ws2.merge_cells("A1:D1")
    ws2["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
    for i, h in enumerate(["项目", "口径 / 计算式", "数值", "说明"], 1):
        ws2.cell(row=2, column=i, value=h)
    r2 = 3
    draft = [("工种配置", "　".join("%s×%d（%d元/工日）" % (a, b, c) for a, b, c in P["工种"]),
              WAGE_SUM, "队日人工费合计")]
    for a, b, c in P["工种"]:
        draft.append(("　" + a, "%d 人 × %d 元/工日" % (b, c), b * c, ""))
    draft += [
        ("挖机台班摊", "元/队·日", P["挖机台班摊"], ""),
        ("小机具耗材", "元/队·日", P["小机具耗材"], ""),
        ("交通器材折旧", "元/队·日", P["交通器材折旧"], ""),
        ("队日综合费用", "人工 + 机械 + 耗材 + 交通", CREW_DAY, "元/队·日"),
        ("日完成量", "边通车跳槽施工", P["日完成座数"], "座/队·日"),
        ("纯成本", "队日费用 ÷ 日完成量", round(UNIT_COST, 2), "元/座"),
        ("每座工日校核", "定额口径", P["每座工日"], "工日/座，交叉验证用"),
        ("对外主体单价", "纯成本 ×(1+%.0f%%)" % (MICRO_PROFIT * 100),
         round(v["甲供C30"]["主体单价"], 2), "元/座；改成 10% 微利则总价约 864 万"),
        ("取费链条", "降效 6% + 风险 4% + 管理费 10% + 税金 3%", "", "基数见成本测算表"),
        ("底线区间", "对外总价 ×(1-10%~12%)",
         "%.0f ~ %.0f 万" % (v["甲供C30"]["总计"] * 0.88 / 1e4,
                             v["甲供C30"]["总计"] * 0.90 / 1e4), "谈判底线"),
        ("推荐签约区间", "对外总价 ±2%~4%",
         "%.0f ~ %.0f 万" % (v["甲供C30"]["总计"] * 0.98 / 1e4,
                             v["甲供C30"]["总计"] * 1.02 / 1e4), ""),
        ("条件切换项", "劳务方自带安措器材",
         "可降 40~55 元/座", "材料款实报实销 + 固定配合费更稳"),
    ]
    for a, b, c, d2 in draft:
        ws2.cell(row=r2, column=1, value=a)
        ws2.cell(row=r2, column=2, value=b)
        ws2.cell(row=r2, column=3, value=c)
        ws2.cell(row=r2, column=4, value=d2)
        r2 += 1
    style_sheet(ws2, [22, 46, 16, 34], header_row=2, dynamic_from=3, wrap_cols={2, 4})

    # 第三 sheet：设备采购责任分类表
    ws3 = wb.create_sheet("设备采购责任分类表")
    ws3["A1"] = "设备采购责任分类表（A 甲供 / B 甲方不提供转我方购 / C 我方采购辅材 / D 劳务方自备）"
    ws3.merge_cells("A1:F1")
    ws3["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
    for i, h in enumerate(["类别", "序号", "名称", "规格 / 说明", "数量", "是否计入报价"], 1):
        ws3.cell(row=2, column=i, value=h)
    r3 = 3
    tag = {"主设备（甲供）": "A 甲供", "甲方不提供→转我方采购": "B 甲方不提供，转我方购",
           "我方采购辅材": "C 我方采购辅材", "劳务方自备": "D 劳务方自备"}
    key = {"主设备（甲供）": "A", "甲方不提供→转我方采购": "B",
           "我方采购辅材": "C", "劳务方自备": "D"}
    include = {"A": "不计材料费；计入安装劳务费", "B": "材料款单列（5%采购管理费+3%税金）",
               "C": "计入辅材费（走劳务取费线）", "D": "不计入，由劳务方承担"}
    for name, rows in DEVICES:
        k = key[name]
        ws3.cell(row=r3, column=1, value=tag[name])
        ws3.cell(row=r3, column=2, value="")
        ws3.cell(row=r3, column=3, value=name)
        ws3.cell(row=r3, column=6, value=include[k])
        for i in range(1, 7):
            ws3.cell(row=r3, column=i).fill = BAND[k]
        r3 += 1
        for idx, (nm, spec, qty, unit, src) in enumerate(rows, 1):
            ws3.cell(row=r3, column=1, value=tag[name])
            ws3.cell(row=r3, column=2, value=idx)
            ws3.cell(row=r3, column=3, value=nm)
            ws3.cell(row=r3, column=4, value="%s（%s）" % (spec, unit))
            ws3.cell(row=r3, column=5, value=qty)
            ws3.cell(row=r3, column=6, value=include[k])
            for i in range(1, 7):
                ws3.cell(row=r3, column=i).fill = BAND[k]
            r3 += 1
    style_sheet(ws3, [22, 6, 24, 50, 10, 34], header_row=2, dynamic_from=3, wrap_cols={4, 6})
    wb.save(path)
    return path


REPORT_NOTES = [
    "综合单价为包干价：含完成本项工作所需人工、机械、辅材、施工措施、场地驻地、检测、资料与协调费用。",
    "甲供材卸车、保管与场内二次搬运由我方负责；甲供材安装损耗超过 2% 的部分按材料价扣赔。",
    "边通车边施工须报批导改方案，配备持证交通引导员；因导改审批延误的工期相应顺延。",
    "计量与支付：月计量支付 80%，完工验收支付 95%，余 5% 质保金质保期满无息退还。",
    "报价有效期 30 天；人工基准期为本报价期，人工单价波动 ±10% 以外按实调整。",
    "C30 到场价波动 ±5% 以外按信息价调差，不调整取费；材料款实报实销时只计固定配合费。",
    "总包形式按类别分包给作业队；劳务方须自备安措器材时可按 40~55 元/座下调。",
    "工期节点：开工后 90 日历天完成基础及立杆 80%，120 日历天完工；混凝土浇筑后养护不少于 3 天。",
]


def build_all(out_dir=OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    v = calc_versions()
    files = {}
    files["1"] = build_devices(os.path.join(out_dir, "1.设备清单（分甲供与我方采购）.xlsx"))
    files["2"] = build_labor_list(os.path.join(out_dir, "2.劳务清单（按施工分类）.xlsx"))
    files["3"] = build_cost_table(os.path.join(out_dir, "3.成本测算表（两口径）.xlsx"), v)
    files["4"] = build_quote(os.path.join(out_dir, "4.对外劳务报价清单（甲供C30版）.xlsx"),
                             v, "甲供C30")
    files["5"] = build_quote(os.path.join(out_dir, "5.对外劳务报价清单（甲方不提供C30版）.xlsx"),
                             v, "不提供C30")
    files["6"] = build_responsibility(os.path.join(out_dir, "6.设备采购责任分类表.xlsx"))
    return v, files


def build_responsibility(path):
    """设备采购责任分类表（单独一份，A/B/C/D 分色带）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "采购责任分类"
    ws["A1"] = "%s　设备采购责任分类表" % P["项目名称"]
    ws.merge_cells("A1:F1")
    ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28
    ws["A2"] = ("A 甲供（材料由甲方提供，我方只计安装人工）　B 甲方不提供→转我方采购（材料款单列）　"
                "C 我方采购辅材（计入辅材费）　D 劳务方自备（不计入报价）")
    ws.merge_cells("A2:F2")
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    for i, h in enumerate(["类别", "序号", "名称", "规格 / 说明", "数量", "是否计入报价与费用归集"], 1):
        ws.cell(row=3, column=i, value=h)
    tag = {"主设备（甲供）": "A 甲供", "甲方不提供→转我方采购": "B 甲方不提供转我方购",
           "我方采购辅材": "C 我方采购辅材", "劳务方自备": "D 劳务方自备"}
    key = {"主设备（甲供）": "A", "甲方不提供→转我方采购": "B",
           "我方采购辅材": "C", "劳务方自备": "D"}
    include = {"A": "不计材料费；计入安装劳务费", "B": "材料款单列：5% 采购管理费 + 3% 税金，不进 6%/4% 基数",
               "C": "计入辅材费，走劳务取费线", "D": "不计入报价，由劳务方承担"}
    r = 4
    for name, rows in DEVICES:
        k = key[name]
        ws.cell(row=r, column=1, value=tag[name])
        ws.cell(row=r, column=3, value=name + "（%d 项）" % len(rows))
        ws.cell(row=r, column=6, value=include[k])
        for i in range(1, 7):
            ws.cell(row=r, column=i).fill = BAND[k]
            ws.cell(row=r, column=i).font = Font(name=FONT, size=10, bold=True)
        r += 1
        for idx, (nm, spec, qty, unit, src) in enumerate(rows, 1):
            ws.cell(row=r, column=1, value=tag[name])
            ws.cell(row=r, column=2, value=idx)
            ws.cell(row=r, column=3, value=nm)
            ws.cell(row=r, column=4, value="%s（%s）" % (spec, unit))
            ws.cell(row=r, column=5, value=qty)
            ws.cell(row=r, column=6, value=include[k])
            for i in range(1, 7):
                ws.cell(row=r, column=i).fill = BAND[k]
            r += 1
    style_sheet(ws, [20, 6, 24, 48, 10, 40], header_row=3, dynamic_from=4, wrap_cols={4, 6})
    ws.freeze_panes = "A4"
    wb.save(path)
    return path
