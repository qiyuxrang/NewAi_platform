# -*- coding: utf-8 -*-
"""通用项目产出器：任意工程量清单进 → 六件套交付文件出。

与 project_lamp.py 的区别：那个是太阳能路灯项目的专用模板（参数、工序、甲供范围都写死），
这个是**以清单为输入**的通用版：
    清单 → 甲供判定 → 分类 → 取价（价格库/历史价/定额/网价）→ 套取费链 → 六份文件

项目参数（项目名称、地区、队伍配置、取费费率、是否甲方提供 C30 等）可传参覆盖，
不传就用默认值；清单里的数量、甲供范围、类别由清单本身决定。
"""
import json
import math
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from engine import boq as boq_mod
from engine import content as content_mod
from engine import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = pipeline.data_path("output")

# ── 默认项目参数（可由调用方覆盖）──
# 清单首行可能是表头而不是项目名，这些词不能当项目名用
HEADER_WORDS = {
    "顺序", "序号", "编号", "项次", "名称", "项目名称", "设备名称", "物料名称",
    "材料名称", "产品名称", "标的名称", "设备材料名称", "单位", "计量单位",
    "数量", "工程量", "清单数量", "备注", "规格", "型号", "规格型号", "技术参数",
}


DEFAULTS = {
    "项目名称": "",
    "地区": "陕西",
    "劳务总包": True,
    # 队伍配置（用于纯成本口径；也可改用定额人工费）
    "工种": [("小工", 5, 200), ("钢筋工", 2, 330), ("木工", 1, 330),
             ("电工/信号司索", 3, 350), ("挖机司机", 1, 450),
             ("专职交通引导员", 2, 200), ("班组长", 1, 350)],
    "挖机台班摊": 800, "小机具耗材": 150, "交通器材折旧": 350,
    "日完成量": 2.5,                      # 按"座"计的项目才有意义
    # 取费链
    "降效率": 0.06, "风险率": 0.04, "管理费率": 0.10, "税率": 0.03,
    "材料采购管理费率": 0.05,
    # 交通安措（按主体工作量计取；为 0 表示不计）
    "安措元每单位": 295,
    "安措计费数量": 0,          # 0 = 自动：按「安措计费单位」的数量合计
    "安措计费单位": "座",       # 交通安措按哪个单位计（路灯项目按"座"；按"处/项"混加是错的）
    # 甲供材料只免材料费，安装人工仍要报（备注写"甲供"的设备，按定额补一条安装劳务）
    "甲供计安装劳务": True,
    # 甲方不提供 C30 时的口径
    "C30单价": 280, "C30方量": 0, "C30损耗": 1.02,
    "C30浇筑人工元每单位": 340, "落地配合费元每单位": 65,
    "单列浇筑人工": False,
    "可选项": [],
    "背景规格": {},          # 从「基础要求/技术方案」里读出来的基础规格（方量/钢筋/基坑）
    "共享网价": None,        # 两条线共用的联网取价结果（由 foursheet 注入，避免重复搜）
    "工日系数": 1.0,         # 工日单价系数：纯网络检索口径下按网查当地工日单价折算
}

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FONT = "微软雅黑"
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
DARK = PatternFill("solid", fgColor="1F3864")
YELLOW = PatternFill("solid", fgColor="FFF2CC")
BAND = {"A": PatternFill("solid", fgColor="E6F1FB"),
        "B": PatternFill("solid", fgColor="FCE4D6"),
        "C": PatternFill("solid", fgColor="E2EFDA"),
        "D": PatternFill("solid", fgColor="FAEEDA")}

EQUIP_CATS = {"设备", "材料", "其他"}


def merge_params(over=None):
    p = json.loads(json.dumps(DEFAULTS, ensure_ascii=False))
    for k, v in (over or {}).items():
        if k in p and v not in (None, ""):
            p[k] = v
    return p


def safe_title(name, used=None):
    """Excel sheet 名不能含 \\ / * ? : [ ]，且不超过 31 字符。"""
    t = str(name)
    for ch in "\\/*?:[]":
        t = t.replace(ch, "-")
    t = t.strip()[:31] or "Sheet"
    if used is not None:
        base, i = t, 1
        while t in used:
            i += 1
            t = ("%s(%d)" % (base[:28], i))
        used.add(t)
    return t


def crew_cost(p):
    wage = sum(n * w for _, n, w in p["工种"])
    day = wage + p["挖机台班摊"] + p["小机具耗材"] + p["交通器材折旧"]
    return wage, day, day / max(0.1, p["日完成量"])


QUOTA_UNIT_FACTOR = {"m": 0.01, "米": 0.01, "100m": 1.0, "10m": 0.1, "km": 0.001,
                     "t": 1.0, "吨": 1.0, "kg": 0.001, "台": 1.0, "套": 1.0, "根": 1.0,
                     "个": 1.0, "座": 1.0, "10套": 0.1, "处": 1.0, "组": 1.0, "块": 1.0,
                     "m²": 0.01, "10m²": 0.1, "m³": 0.01, "10m³": 0.1, "100m³": 0.01}


def unit_factor(quota_unit, list_unit):
    """把定额单位折算到清单单位：定额单位 100m、清单 m → 0.01。"""
    qu = str(quota_unit or "").strip().replace(" ", "")
    lu = str(list_unit or "").strip().replace(" ", "")
    if not qu or not lu or qu == lu:
        return 1.0
    # 同量纲直接按系数换算
    base = {"米": "m", "m": "m", "千米": "km", "kg": "kg", "吨": "t",
            "平方米": "m²", "立方米": "m³", "处": "处", "根": "根", "个": "个",
            "台": "台", "套": "套", "块": "块", "组": "组", "座": "座"}
    qu2, lu2 = base.get(qu, qu), base.get(lu, lu)
    if qu2 == lu2:
        return 1.0
    # 定额里常见 100m / 10m² / 10只 这类前缀
    import re as _re
    m = _re.match(r"^(\d+(?:\.\d+)?)\s*(.+)$", qu)
    if m and base.get(m.group(2), m.group(2)) == lu2:
        return 1.0 / float(m.group(1))
    m2 = _re.match(r"^(\d+(?:\.\d+)?)\s*(.+)$", lu)
    if m2 and base.get(m2.group(2), m2.group(2)) == qu2:
        return float(m2.group(1))
    # 单位不同但同为"个/只/套/台"这类计件单位，按 1 处理
    piece = {"个", "只", "套", "台", "根", "块", "组", "座", "处"}
    if qu2 in piece and lu2 in piece:
        return 1.0
    if qu2 in piece and _re.match(r"^\d+(\.\d+)?\s*(个|只|套|台|根|块|组|座)$", qu):
        return 1.0
    return 1.0


def style(ws, widths, header_row=2, wrap_cols=None, dyn_from=None):
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
            c.font = Font(name=FONT, size=10, bold=True)
            c.fill = HEAD_FILL
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if dyn_from:
        for r in range(dyn_from, ws.max_row + 1):
            lines = 1
            for i in range(1, len(widths) + 1):
                v = ws.cell(row=r, column=i).value
                if v is None or (wrap_cols and i not in wrap_cols):
                    continue
                lines = max(lines, math.ceil(len(str(v)) / max(6, widths[i - 1] / 2.1)))
            ws.row_dimensions[r].height = lines * 14 + 8


def owner_install_rows(items, n0=0, mult=1.0):
    """甲供材料只免材料费，安装人工照计：给每个甲供项补一条安装劳务。

    单价优先取「人工含量库」（工日含量 × 工日单价），定额命中时在备注里做交叉校核。
    """
    from engine import pipeline as _pl
    from engine import content as _ct
    qlib = _pl.load_quota()
    rows = []
    for i, x in enumerate([y for y in items if y.get("甲供") == "是"], 1):
        qty = x["数量"] if isinstance(x["数量"], (int, float)) else 0
        c_cost, c_detail, _ = _ct.unit_content(x["项目名称"], x["单位"], mult)
        q_cost, q_detail = 0.0, ""
        pick = _pl.pick_quota(qlib, x["项目名称"], x["单位"])
        if pick:
            f = unit_factor(pick.get("单位"), x["单位"])
            q_cost = (float(pick.get("人工费") or 0) + float(pick.get("机械费") or 0)) * f
            q_detail = "定额 %s %s（%s）" % (pick["编号"], pick.get("项目名称"),
                                         pick.get("理由"))
        if c_cost:
            _rule = _ct.find_rule(x["项目名称"]) or {}
            unit_cost, src = c_cost, "人工含量库｜甲供材安装·工序：%s" % _rule.get("工序", "—")
            why = "甲供只免材料费，安装人工照计；%s" % c_detail
            if q_cost and q_cost > c_cost:
                why += "｜定额校核：%s（人工费+机械费 %.2f 元）" % (q_detail, q_cost)
        elif q_cost:
            unit_cost, src = q_cost, "企业定额库｜甲供材安装·%s %s" % (
                pick.get("专业"), pick["编号"])
            why = "甲供只免材料费，安装人工照计；%s" % q_detail
        else:
            unit_cost, src = 0.0, "暂估｜甲供材安装，定额与含量库均未命中"
            why = "未匹配到安装定额或含量，需人工确认安装单价"
        rows.append([n0 + i, "%s（甲供材安装）" % x["项目名称"], x["备注"][:40],
                     x["单位"], qty, src, round(unit_cost, 2),
                     round(unit_cost * qty, 2), "", why, "", ""])
    return rows


def run(boq_path, over=None, ctx=None, write_files=True):
    """清单进 → 取价 → 六件套出。返回 (参数, 汇总, 文件字典)。

    ctx 不为空时，把中间结果（清单明细 / 带价行 / 取费链）回填进去，
    供上层（四件套装配、校验）复用，避免重复解析与重复取价。
    """
    title, items = boq_mod.parse(boq_path)
    if not items:
        raise SystemExit("清单没解析出明细，请检查表头")
    p = merge_params(over)
    p["项目名称"] = p["项目名称"] or title.split("\n")[0].strip()
    # ⚠ 有些清单第一行就是表头（首个单元格写「顺序」「设备材料名称」），标题会取成
    # "顺序"这种玩意儿，导出的项目文件夹就全叫"顺序"、几十份互相覆盖。
    # 表头词/纯数字标题一律回落到文件名。
    if not p["项目名称"] or p["项目名称"] in HEADER_WORDS or re.fullmatch(
            r"\d+", p["项目名称"]):
        p["项目名称"] = os.path.splitext(os.path.basename(boq_path))[0]
    tag = p["项目名称"][:20].replace("/", "_").replace("\\", "_").strip() or "项目"
    out_dir = os.path.join(OUT_ROOT, tag)
    os.makedirs(out_dir, exist_ok=True)

    kept, dropped, equip, labor = pipeline.est.split_items(items)

    # ── 取价（不联网：库 → 历史 → 定额；联网留给上层工作流按需触发）──
    cfg = pipeline.json.load(open(os.path.join(ROOT, "config", "settings.json"), encoding="utf-8"))
    cfg["project_region"] = p["地区"]
    cost_rows = pipeline.price_equipment(equip, cfg,
                                         shared_web=p.get("共享网价"))
    mult = float(p.get("工日系数") or 1.0)
    labor_rows = pipeline.price_labor(labor, cfg, spec=p.get("背景规格"), mult=mult)

    # 甲供材料：免材料费，但安装人工必须计（备注标注"甲供"的设备按定额补一条安装劳务）
    if p.get("甲供计安装劳务"):
        labor_rows += owner_install_rows(items, len(labor_rows), mult)

    def num(v):
        return float(v) if isinstance(v, (int, float)) else 0.0

    equip_total = sum(num(r[7]) for r in cost_rows)
    labor_total = sum(num(r[7]) for r in labor_rows)

    # ── 取费链 ──
    # 安措基数：优先按「安措计费单位」（如"座"）合计；没有该单位时回落到主体数量最大的那种单位
    unit_key = str(p.get("安措计费单位") or "座")
    from collections import Counter
    cnt = Counter()
    for x in kept:
        if isinstance(x["数量"], (int, float)):
            cnt[str(x.get("单位") or "")] += x["数量"]
    cnt.pop("", None)
    labor_units = cnt.get(unit_key, 0)
    if not labor_units:
        # 没有"座"这类主体单位时，取主体类单位里数量最大的（套/台/间…），
        # 绝不把 米/m³/t 这种材料计量单位当成作业面数量
        cand = [(cnt.get(u, 0), u) for u in
                ("处", "套", "台", "间", "项", "个", "组", "根", "块", "站", "系统")]
        cand = [c for c in cand if c[0]]
        if cand:
            labor_units, unit_key = max(cand)
        else:
            labor_units = cnt.most_common(1)[0][1] if cnt else 0
    n_units = float(p.get("安措计费数量") or 0) or labor_units or 1
    measure_unit = float(p["安措元每单位"] or 0)
    measure = measure_unit * n_units
    # 交通安措只在"有施工内容"时计取：
    #  ① 纯采购清单（没有劳务子目）根本没有占道施工，不该收交通安措；
    #  ② 有施工时按"主体单位数量 × 单价"，但兜住上下限——
    #     下限 3%（机电类小项目按"座"算会小得离谱），
    #     上限 15%（纯电缆清单没有"座"，单位会回落成"米"，
    #     295 元/米 × 20 万米 = 5900 万，这个上限就是拦它的）
    if labor_total <= 0:
        measure = 0.0
        n_units = n_units or 1
    elif equip_total + labor_total:
        base = equip_total + labor_total
        measure = max(measure, round(base * 0.03, 2))
        measure = min(measure, round(base * 0.15, 2))

    def chain(direct, r=p):
        de = direct * r["降效率"]
        ri = direct * r["风险率"]
        sub = direct + de + ri
        mg = sub * r["管理费率"]
        sub2 = sub + mg
        tx = sub2 * r["税率"]
        return {"直接费": direct, "降效": de, "风险": ri, "管理费": mg,
                "税金": tx, "取费小计": de + ri + mg + tx, "总计": sub2 + tx}

    a = chain(equip_total + labor_total + measure)
    # 甲方不提供 C30：材料线单列（按可选项里给的 C30 单价与方量估算；无参数则为 0）
    pour = float(p["C30浇筑人工元每单位"]) * n_units if p["单列浇筑人工"] else 0.0
    fit = float(p["落地配合费元每单位"]) * n_units
    b_labor = chain(equip_total + labor_total + measure + pour + fit)
    material = float(p.get("C30方量", 0) or 0) * float(p["C30单价"])
    b_material = material * (1 + p["材料采购管理费率"]) * (1 + p["税率"])
    b_total = b_labor["总计"] + b_material

    summary = {
        "项目名称": p["项目名称"], "清单行数": len(items),
        "需报价": len(kept), "甲供剔除": len(dropped),
        "设备材料合计": round(equip_total, 2), "劳务合计": round(labor_total, 2),
        "安措合计": round(measure, 2),
        "单位": unit_key, "单位数": round(n_units, 2),
        "安措元每单位": measure_unit,
        "主体数量": round(labor_units, 2),
        "甲供C30版": {"直接费": round(a["直接费"], 2),
                      "降效": round(a["降效"], 2), "风险": round(a["风险"], 2),
                      "管理费": round(a["管理费"], 2), "税金": round(a["税金"], 2),
                      "取费": round(a["取费小计"], 2), "总计": round(a["总计"], 2)},
        "不提供C30版": {"劳务线含税": round(b_labor["总计"], 2),
                        "材料线含税": round(b_material, 2),
                        "总计": round(b_total, 2)},
        "参数": {k: v for k, v in p.items() if k not in ("工种",)},
    }
    if write_files:
        files = _write_files(out_dir, p, title, items, kept, dropped, cost_rows,
                             labor_rows, summary, a, b_labor, b_material)
    else:
        files = {}
    summary["输出目录"] = out_dir
    summary["文件"] = files
    if ctx is not None:
        ctx.update({"标题": title, "清单明细": items, "带价设备": cost_rows,
                    "带价劳务": labor_rows, "参数": p, "甲供链": a,
                    "不提供链": b_labor, "材料款": b_material,
                    "需报价": kept, "甲供剔除": dropped})
    return p, summary, files


def _write_files(out_dir, p, title, items, kept, dropped, cost_rows, labor_rows,
                 summary, a, b_labor, b_material):
    files = {}
    # 1) 设备清单（分甲供与我方采购）
    wb = Workbook()
    wb.remove(wb.active)
    groups = {}
    for x in items:
        key = ("甲供（不计材料费）" if x["甲供"] == "是" else
               ("设备/材料（我方采购）" if x["类别"] in EQUIP_CATS else "施工/劳务项"))
        groups.setdefault(key, []).append(x)
    for gname, rows in groups.items():
        ws = wb.create_sheet(safe_title(gname))
        ws["A1"] = "%s　%s" % (p["项目名称"], gname)
        ws.merge_cells("A1:E1")
        ws["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26
        for i, h in enumerate(["序号", "设备名称", "技术参数", "数量", "单位"], 1):
            ws.cell(row=2, column=i, value=h)
        for k, x in enumerate(rows, 1):
            ws.cell(row=2 + k, column=1, value=k)
            ws.cell(row=2 + k, column=2, value=x["项目名称"])
            ws.cell(row=2 + k, column=3, value=x["备注"][:200])
            ws.cell(row=2 + k, column=4, value=x["数量"])
            ws.cell(row=2 + k, column=5, value=x["单位"])
        style(ws, [6, 28, 50, 10, 8], header_row=2, wrap_cols={2, 3}, dyn_from=3)
    files["1"] = os.path.join(out_dir, "1.设备清单（分甲供与我方采购）.xlsx")
    wb.save(files["1"])

    # 2) 劳务清单（按施工分类分 sheet）
    wb = Workbook()
    wb.remove(wb.active)
    by_cat = {}
    for x in kept:
        if x["类别"] in EQUIP_CATS:
            continue
        by_cat.setdefault(x["类别"], []).append(x)
    for cat, rows in by_cat.items():
        ws = wb.create_sheet(safe_title(cat))
        ws["A1"] = "%s　劳务清单—%s" % (p["项目名称"], cat)
        ws.merge_cells("A1:E1")
        ws["A1"].font = Font(name=FONT, size=12, bold=True, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26
        for i, h in enumerate(["序号", "项目名称", "工作内容/规格", "数量", "单位"], 1):
            ws.cell(row=2, column=i, value=h)
        for k, x in enumerate(rows, 1):
            ws.cell(row=2 + k, column=1, value=k)
            ws.cell(row=2 + k, column=2, value=x["项目名称"])
            ws.cell(row=2 + k, column=3, value=x["备注"][:200])
            ws.cell(row=2 + k, column=4, value=x["数量"])
            ws.cell(row=2 + k, column=5, value=x["单位"])
        style(ws, [6, 30, 50, 10, 8], header_row=2, wrap_cols={2, 3}, dyn_from=3)
    if not wb.worksheets:   # 纯设备采购清单没有劳务子目——不能让 save 崩
        ws = wb.create_sheet("劳务清单")
        ws["A1"] = "%s　劳务清单" % p["项目名称"]
        ws["A2"] = ("本清单为纯设备 / 材料采购清单，没有劳务子目，本表为空。"
                    "如需安装劳务报价，请见六件套的⑤⑥劳务报价。")
    files["2"] = os.path.join(out_dir, "2.劳务清单（按施工分类）.xlsx")
    wb.save(files["2"])

    # 3) 成本测算表（两口径）
    wb = Workbook()
    ws = wb.active
    ws.title = "成本测算（两口径）"
    ws["A1"] = "%s　成本测算表" % p["项目名称"]
    ws.merge_cells("A1:E1")
    ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws.row_dimensions[1].height = 28
    for i, h in enumerate(["序号", "费用项", "口径", "金额（元）", "备注"], 1):
        ws.cell(row=2, column=i, value=h)
    wage, crew_day, unit_cost = crew_cost(p)
    r = 3
    lines = [
        ("一、内部成本", "", "", ""),
        ("队日人工", "工种配置合计", wage, ""),
        ("队日综合费用", "人工+机械+耗材+交通器材", crew_day, "元/队·日"),
        ("纯成本（按座折算）", "队日费用 ÷ 日完成量", round(unit_cost, 2), "元/单位"),
        ("设备材料（取价结果）", "价格库/历史价/网价", summary["设备材料合计"], ""),
        ("劳务（定额组价）", "人工费+机械费", summary["劳务合计"], ""),
        ("交通安措", "%s 元/单位" % p["安措元每单位"], summary["安措合计"], ""),
        ("二、对外报价—甲供 C30 口径", "", "", ""),
        ("直接费", "设备材料 + 劳务 + 安措", a["直接费"], ""),
        ("人工降效与窝工", "直接费 × %.0f%%" % (p["降效率"] * 100), a["降效"], ""),
        ("不可预见风险", "直接费 × %.0f%%" % (p["风险率"] * 100), a["风险"], ""),
        ("管理费", "(直接费+降效+风险) × %.0f%%" % (p["管理费率"] * 100), a["管理费"], ""),
        ("税金", "简易计税 %.0f%%" % (p["税率"] * 100), a["税金"], ""),
        ("报价总计（甲供 C30）", "含税", a["总计"], ""),
        ("三、对外报价—甲方不提供 C30", "", "", ""),
        ("劳务线含税", "同上口径 + 浇筑人工与落地配合", b_labor["总计"], ""),
        ("材料线含税", "材料款 ×1.05×1.03", b_material, "不进 6%/4% 基数"),
        ("报价总计（不提供 C30）", "劳务线 + 材料线", b_labor["总计"] + b_material, ""),
    ]
    for name, basis, amount, note in lines:
        ws.cell(row=r, column=1, value=r - 2)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=basis)
        ws.cell(row=r, column=4, value=round(amount, 2) if isinstance(amount, (int, float)) else amount)
        ws.cell(row=r, column=5, value=note)
        if name.startswith(("一、", "二、", "三、")) or "总计" in name:
            for i in range(1, 6):
                ws.cell(row=r, column=i).fill = YELLOW
        r += 1
    style(ws, [6, 26, 40, 16, 26], header_row=2, wrap_cols={3, 5}, dyn_from=3)
    files["3"] = os.path.join(out_dir, "3.成本测算表（两口径）.xlsx")
    wb.save(files["3"])

    # 4/5) 对外报价清单（两版）
    for ver, fname in (("甲供C30", "4.对外劳务报价清单（甲供C30版）.xlsx"),
                       ("不提供C30", "5.对外劳务报价清单（甲方不提供C30版）.xlsx")):
        wb = Workbook()
        ws = wb.active
        ws.title = "对外劳务报价清单"
        ws["A1"] = "%s　对外报价清单（%s）" % (p["项目名称"], ver)
        ws.merge_cells("A1:H1")
        ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
        ws.row_dimensions[1].height = 30
        for i, h in enumerate(["序号", "分项名称", "工作内容", "计量单位", "暂定工程量",
                               "综合单价(元)", "合价(元)", "备注（费用归集口径）"], 1):
            ws.cell(row=2, column=i, value=h)
        r = 3
        ws.cell(row=r, column=2, value="一、主体（设备材料 + 劳务）")
        r += 1
        idx = 0
        for row in cost_rows + labor_rows:
            if not row[1]:
                continue
            idx += 1
            price = row[6] if isinstance(row[6], (int, float)) else None
            for i, v in enumerate([idx, row[1], row[2], row[3], row[4], price, row[7], row[5]], 1):
                ws.cell(row=r, column=i, value=v)
            r += 1
        ws.cell(row=r, column=2, value="小计（主体）")
        ws.cell(row=r, column=7, value=round(summary["设备材料合计"] + summary["劳务合计"], 2))
        r += 1
        ws.cell(row=r, column=2, value="二、交通安措（必选）")
        r += 1
        ws.cell(row=r, column=2, value="边通车边施工交通安措")
        ws.cell(row=r, column=6, value=p["安措元每单位"])
        ws.cell(row=r, column=7, value=summary["安措合计"])
        ws.cell(row=r, column=8, value="%s 元/单位" % p["安措元每单位"])
        r += 2
        ws.cell(row=r, column=2, value="报价总额（含税）")
        total = summary["甲供C30版"]["总计"] if ver == "甲供C30" else summary["不提供C30版"]["总计"]
        ws.cell(row=r, column=7, value=total)
        ws.cell(row=r, column=8, value="已含降效 6%% / 风险 4%% / 管理费 10%% / 税金 3%%"
                if ver == "甲供C30" else "劳务线与材料线分别取费")
        for i in range(1, 9):
            c = ws.cell(row=r, column=i)
            c.fill = YELLOW
            c.font = Font(name=FONT, size=11, bold=True, color="C00000")
        style(ws, [6, 30, 46, 10, 12, 14, 16, 44], header_row=2, wrap_cols={2, 3, 8}, dyn_from=3)
        files["4" if ver == "甲供C30" else "5"] = os.path.join(out_dir, fname)
        wb.save(files["4" if ver == "甲供C30" else "5"])

    # 6) 采购责任分类表
    wb = Workbook()
    ws = wb.active
    ws.title = "采购责任分类"
    ws["A1"] = "%s　设备采购责任分类表" % p["项目名称"]
    ws.merge_cells("A1:F1")
    ws["A1"].font = Font(name=FONT, size=13, bold=True, color="1F3864")
    ws.row_dimensions[1].height = 28
    ws["A2"] = ("A 甲供（备注标注，材料不计）　B 甲方不提供（转我方采购）　"
                "C 我方采购辅材　D 劳务方自备")
    ws.merge_cells("A2:F2")
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="595959")
    for i, h in enumerate(["类别", "序号", "名称", "规格/工作内容", "数量", "是否计入报价"], 1):
        ws.cell(row=3, column=i, value=h)
    r = 4
    for k, x in enumerate(items, 1):
        if x["甲供"] == "是":
            key, lab, inc = "A", "A 甲供", "不计材料费；计入安装劳务费"
        elif x["类别"] in EQUIP_CATS:
            key, lab, inc = "C", "C 我方采购", "计入设备材料费"
        else:
            key, lab, inc = "D", "D 劳务承担", "计入劳务费"
        ws.cell(row=r, column=1, value=lab)
        ws.cell(row=r, column=2, value=k)
        ws.cell(row=r, column=3, value=x["项目名称"])
        ws.cell(row=r, column=4, value=x["备注"][:160])
        ws.cell(row=r, column=5, value=x["数量"])
        ws.cell(row=r, column=6, value=inc)
        for i in range(1, 7):
            ws.cell(row=r, column=i).fill = BAND[key]
        r += 1
    style(ws, [16, 6, 26, 48, 10, 30], header_row=3, wrap_cols={3, 4, 6}, dyn_from=4)
    files["6"] = os.path.join(out_dir, "6.设备采购责任分类表.xlsx")
    wb.save(files["6"])

    with open(os.path.join(out_dir, "项目参数.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in p.items() if k != "工种"}, f, ensure_ascii=False, indent=2)
    return files
