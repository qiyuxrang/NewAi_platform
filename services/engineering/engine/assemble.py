# -*- coding: utf-8 -*-
"""四件套装配：一个 Excel、四张表。

    ①成本测算（库+网检索）   设备材料：价格库 → 历史价 → 互联网检索
    ②成本测算（纯网检索）     设备材料：全部走互联网检索
    ③劳务报价（库+网检索）   劳务：定额/人工含量库 + 网查工日单价校核 → 对外总包报价
    ④劳务报价（纯网检索）     劳务：人工单价全部取网查当地工日单价 → 对外总包报价

硬性要求：单价与合价任何一行都不允许空白；取不到价也必须给出「暂估价」并写明依据。
"""
import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

F = "微软雅黑"
THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="D9E1F2")
YEL = PatternFill("solid", fgColor="FFF2CC")
GREY = PatternFill("solid", fgColor="F2F2F2")
OWN = PatternFill("solid", fgColor="E6F1FB")
BAND = {"甲供": OWN, "小计": YEL, "总价": YEL, "说明": GREY}


def _style(ws, widths, header_row=3, dyn_from=4, wrap=None, ncol=None):
    ncol = ncol or len(widths)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if c.row >= header_row:
                c.font = Font(name=F, size=10)
    for c in ws[header_row]:
        if c.value is not None:
            c.font = Font(name=F, size=10, bold=True)
            c.fill = HEAD
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in range(dyn_from, ws.max_row + 1):
        lines = 1
        for i in range(1, ncol + 1):
            v = ws.cell(row=r, column=i).value
            if v is None or (wrap and i not in wrap):
                continue
            lines = max(lines, math.ceil(len(str(v)) / max(6, widths[i - 1] / 2.1)))
        ws.row_dimensions[r].height = lines * 14 + 8
    for rng in list(ws.merged_cells.ranges):
        for r in range(rng.min_row, rng.max_row + 1):
            for cidx in range(rng.min_col, rng.max_col + 1):
                ws.cell(row=r, column=cidx).border = BORDER


def _title(ws, text, ncol, sub=None):
    ws.cell(row=1, column=1, value=text)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    ws.cell(row=1, column=1).font = Font(name=F, size=13, bold=True, color="1F3864")
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26
    if sub:
        ws.cell(row=2, column=1, value=sub)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
        ws.cell(row=2, column=1).font = Font(name=F, size=9, italic=True, color="C00000")
        return 3
    return 2


HEADS = ["序号", "项目名称", "规格 / 工作内容", "单位", "数量",
         "单价（元）", "合价（元）", "价格来源", "备注（取价依据 / 风险）", "数据来源",
         "核验链接", "可信度"]
WIDTHS = [5, 28, 44, 7, 9, 12, 14, 22, 46, 30, 36, 13]

EQ_HEADS = ["序号", "设备 / 材料名称", "技术参数 / 规格", "数量", "单位",
            "供应归属", "是否计入报价", "单价（元）", "合价（元）",
            "备注（归属依据 / 取价）", "数据来源", "核验链接", "可信度"]
EQ_WIDTHS = [5, 28, 40, 9, 7, 22, 20, 12, 14, 42, 28, 36, 13]

LAB_HEADS = ["序号", "分类", "项目名称", "工作内容 / 工序", "单位", "数量",
             "综合单价（元）", "合价（元）", "备注（含量 / 依据）", "数据来源",
             "核验链接", "可信度"]
LAB_WIDTHS = [5, 13, 30, 36, 7, 9, 12, 14, 46, 28, 36, 13]

# 可信度分级（借鉴同事技能包的溯源要求：每行都要能看出这个价敢不敢用）
CONF = [("企业价格库", "高（企业成交价）"), ("企业历史报价库", "高（历史成交价）"),
        ("互联网检索", "中（真实挂牌价，已过真实性校验）"),
        ("人工含量库", "中（工日含量×工种单价）"),
        ("企业定额库", "中（定额组价）"),
        ("电缆行情公式", "中（铜价公式，非挂牌价）"),
        ("取费口径", "高（企业取费参数）"),
        ("AI经验估值", "低（AI经验估值，必须询价）"),
        ("品类经验暂估", "低（品类经验区间，必须询价）"),
        ("甲方供料", "—"), ("不计入", "—")]


def _conf(row, src=None):
    s = str(src if src is not None else (row[5] if len(row) > 5 else ""))
    for k, v in CONF:
        if s.startswith(k) or k in s:
            return v
    if not s or s.startswith("暂估"):
        return "无（未取到价，待询价）"
    return "低（需复核）"

CATS = (("基础工程", ("基础", "土方", "开挖", "钢筋", "模板", "浇筑", "混凝土", "砼", "垫层")),
        ("拆除", ("拆除", "拆旧")),
        ("电气与接地", ("导线", "电线", "电缆", "接地", "敷设", "接线", "灌胶", "穿刺",
                    "绝缘", "穿线管")),
        ("灯杆与灯具安装", ("灯", "杆", "光伏", "电池", "组件", "控制器")))


def _cat_of(name):
    for c, kws in CATS:
        if any(k in name for k in kws):
            return c
    return "措施与管理"


def _equipment_sheet(wb, project, tagged, labor_a, cost_a, owner_names, nature=""):
    """①设备清单：逐行标出供应归属、是否计入报价、单价与合价（绝不留空）。"""
    ws = wb.create_sheet("①设备清单")
    pure_buy = (nature == "采购清单")
    hr = _title(ws, "%s　设备清单" % project, len(EQ_HEADS),
                ("本清单为设备采购清单：全部由我方采购，单价为采购价（含税），不含安装；"
                 "如采购合同含安装，安装费见⑤⑥劳务报价"
                 ) if pure_buy else
                ("A 甲供（材料不计价、安装人工照计）｜B 我方采购/施工｜C 我方辅材｜"
                 "D 劳务自备｜E 存疑（已自动按我方采购暂估，不阻塞）"))
    heads = list(EQ_HEADS)
    if pure_buy:
        heads[5], heads[6] = "采购方式", "报价口径"
    for i, h in enumerate(heads, 1):
        ws.cell(row=hr, column=i, value=h)
    inst, bought, lab, bulk = {}, {}, {}, {}
    for r in labor_a:
        nm = str(r[1] or "")
        if nm.endswith("（甲供材安装）"):
            inst[nm[:-len("（甲供材安装）")]] = r
        lab.setdefault(nm, r)
        if " — " in nm:
            base = nm.split(" — ", 1)[0]
            u = r[6] if isinstance(r[6], (int, float)) else 0
            t = r[7] if isinstance(r[7], (int, float)) else 0
            cu, ct, steps = bulk.get(base, (0.0, 0.0, []))
            bulk[base] = (cu + float(u), ct + float(t), steps + [nm.split(" — ", 1)[1]])
    for r in cost_a:
        bought.setdefault(str(r[1] or ""), r)

    row_i = hr + 1
    for i, x in enumerate(tagged, 1):
        owner = str(x.get("供应归属") or "B 我方采购（设备/主材）")
        nm = str(x.get("项目名称") or "")
        cat = str(x.get("类别") or "")
        inc = {"A": "不计材料费，计安装劳务", "B": "计入我方报价",
               "C": "计入辅材费", "D": "不计入", "E": "存疑，暂按我方采购计"}.get(owner[:1], "计入")
        if cat == "包工包料":
            inc = "计入（包工包料，甲供材除外）"
        elif owner[:1] == "B" and "纯劳务" in owner:
            inc = "计入（只计人工与机械）"
        if pure_buy:
            owner, inc = "我方采购", "设备采购价（不含安装）"
        price, total, note = 0.0, 0.0, str(x.get("归属依据") or "")
        if owner[:1] == "A" and nm in inst:
            price, total = inst[nm][6] or 0, inst[nm][7] or 0
            note = "%s；单价＝甲供材安装劳务（材料不计价）" % note
        elif cat == "劳务施工" and nm in lab:
            price, total = lab[nm][6] or 0, lab[nm][7] or 0
            note = "%s；纯劳务口径（只计人工与机械）" % note
        elif nm in bulk:
            price, total = round(bulk[nm][0], 2), round(bulk[nm][1], 2)
            note = "%s；含 %d 道工序（%s），明细见②劳务清单" % (
                note, len(bulk[nm][2]), "／".join(bulk[nm][2]))
        elif nm in bought:
            price, total = bought[nm][6] or 0, bought[nm][7] or 0
            note = "%s；取价来源：%s" % (note, bought[nm][5] or "—")
        ws.cell(row=row_i, column=1, value=i)
        ws.cell(row=row_i, column=2, value=nm)
        ws.cell(row=row_i, column=3, value=str(x.get("备注") or "")[:200] or "—")
        ws.cell(row=row_i, column=4, value=x.get("数量"))
        ws.cell(row=row_i, column=5, value=x.get("单位") or "—")
        ws.cell(row=row_i, column=6, value=owner)
        ws.cell(row=row_i, column=7, value=inc)
        ws.cell(row=row_i, column=8, value=round(float(price or 0), 2))
        ws.cell(row=row_i, column=9, value=round(float(total or 0), 2))
        ws.cell(row=row_i, column=10, value=note[:500] or "—")
        src_eq = "—"
        if owner[:1] == "A" and nm in inst:
            src_eq = _src(inst[nm])
        elif cat == "劳务施工" and nm in lab:
            src_eq = _src(lab[nm])
        elif nm in bulk:
            src_eq = "人工含量库｜包工包料工序分解：%s" % "／".join(bulk[nm][2])
        elif nm in bought:
            src_eq = _src(bought[nm])
        ws.cell(row=row_i, column=11, value=src_eq)
        link_row = (inst.get(nm) if owner[:1] == "A" and nm in inst else
                    lab.get(nm) if cat == "劳务施工" and nm in lab else
                    bought.get(nm))
        if link_row:
            _link(ws, row_i, 12, link_row)
        else:
            ws.cell(row=row_i, column=12, value="—（本地库/含量库口径，无需外部链接）")
        ws.cell(row=row_i, column=13, value=_conf(link_row if link_row else None,
                                                  src_eq) if link_row
                else _conf(None, src_eq))
        fill = OWN if owner[:1] == "A" else None
        if fill:
            for k in range(1, 14):
                ws.cell(row=row_i, column=k).fill = fill
        row_i += 1
    ws.cell(row=row_i, column=2, value="合计（%d 项）" % len(tagged))
    ws.cell(row=row_i, column=9, value=round(sum(
        (ws.cell(row=r, column=9).value or 0) for r in range(hr + 1, row_i)), 2))
    ws.cell(row=row_i, column=10,
            value=("全部为我方采购设备；如采购合同含安装，安装费见⑤⑥劳务报价"
                   if pure_buy else
                   "甲供项材料不计价（蓝底，单价为其安装劳务）；成本与劳务报价明细见③④⑤⑥"))
    for k in range(1, 14):
        ws.cell(row=row_i, column=k).fill = YEL
        ws.cell(row=row_i, column=k).font = Font(name=F, size=10, bold=True)
    _style(ws, EQ_WIDTHS, header_row=hr, dyn_from=hr + 1,
           wrap={2, 3, 6, 7, 10, 11, 12, 13}, ncol=13)


def _labor_list_sheet(wb, project, labor_a):
    """②劳务清单：按施工分类，只计人工与机械。"""
    ws = wb.create_sheet("②劳务清单")
    hr = _title(ws, "%s　劳务清单（按施工分类）" % project, len(LAB_HEADS),
                "只计人工与机械；甲供材料不计价；综合单价已含工日含量口径")
    for i, h in enumerate(LAB_HEADS, 1):
        ws.cell(row=hr, column=i, value=h)
    r = hr + 1
    idx = 0
    for row in labor_a:
        nm = str(row[1] or "")
        if not nm:
            continue
        idx += 1
        price = row[6] if isinstance(row[6], (int, float)) else 0.0
        qty = row[4] if isinstance(row[4], (int, float)) else 0
        total = row[7] if isinstance(row[7], (int, float)) else round(price * qty, 2)
        ws.cell(row=r, column=1, value=idx)
        ws.cell(row=r, column=2, value=_cat_of(nm))
        ws.cell(row=r, column=3, value=nm)
        ws.cell(row=r, column=4, value=str(row[2] or "")[:250] or "—")
        ws.cell(row=r, column=5, value=row[3] or "—")
        ws.cell(row=r, column=6, value=qty)
        ws.cell(row=r, column=7, value=round(price, 2))
        ws.cell(row=r, column=8, value=round(total, 2))
        ws.cell(row=r, column=9, value=str(row[9] or "")[:520] or "—")
        ws.cell(row=r, column=10, value=_src(row))
        _link(ws, r, 11, row)
        ws.cell(row=r, column=12, value=_conf(row))
        r += 1
    ws.cell(row=r, column=3, value="合　计")
    ws.cell(row=r, column=8, value=round(sum(
        (ws.cell(row=x, column=8).value or 0) for x in range(hr + 1, r)), 2))
    for k in range(1, 13):
        ws.cell(row=r, column=k).fill = YEL
        ws.cell(row=r, column=k).font = Font(name=F, size=10, bold=True)
    _style(ws, LAB_WIDTHS, header_row=hr, dyn_from=hr + 1,
           wrap={2, 3, 4, 9, 10, 11, 12}, ncol=12)


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _src(row):
    """数据来源：单独一列写清"出自哪本库 / 哪个网站 / 哪条定额"。"""
    s = str(row[5] or "").strip() if len(row) > 5 else ""
    if not s or s == "待互联网检索":
        return "暂估（无外部来源）"
    return s


def _link(ws, r, col, row):
    """核验链接：只有"线上检索"的价才有链接，点开回到抓价页面；其余写 —。"""
    url = str(row[11] or "").strip() if len(row) > 11 else ""
    if url.startswith(("http://", "https://")):
        c = ws.cell(row=r, column=col, value=url)
        c.hyperlink = url
        c.font = Font(name=F, size=10, color="0563C1", underline="single")
        return
    if str(row[5] or "").startswith("互联网检索"):
        c = ws.cell(row=r, column=col, value="（未取到具体链接）")
        return
    ws.cell(row=r, column=col, value="—（本地库/含量库口径，无需外部链接）")


def _write_rows(ws, rows, hr, owner_names=None, mark=True):
    """写明细行，返回下一个可用行号。单价/合价绝不留空。"""
    r = hr + 1
    idx = 0
    for row in rows:
        name = str(row[1] or "")
        if not name:
            continue
        idx += 1
        price = _num(row[6])
        total = _num(row[7])
        qty = _num(row[4])
        if price is None:
            price = 0.0
        if total is None:
            total = round(price * (qty or 0), 2)
        note = str(row[9] or "")
        if not (price or total):
            note = (note + "；⚠ 未取到价，本行按 0 列入，须询价后回填").strip("；")
        ws.cell(row=r, column=1, value=idx)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=str(row[2] or "")[:300])
        ws.cell(row=r, column=4, value=row[3] or "")
        ws.cell(row=r, column=5, value=qty if qty is not None else "")
        ws.cell(row=r, column=6, value=round(price, 2))
        ws.cell(row=r, column=7, value=round(total, 2))
        ws.cell(row=r, column=8, value=row[5] or "（未标注来源）")
        ws.cell(row=r, column=9, value=note[:600] or "—")
        ws.cell(row=r, column=10, value=_src(row))
        _link(ws, r, 11, row)
        ws.cell(row=r, column=12, value=_conf(row))
        if mark and owner_names and name.replace("（甲供材安装）", "") in owner_names:
            for k in range(1, 13):
                ws.cell(row=r, column=k).fill = OWN
        r += 1
    return r, idx


def _notes_block(ws, r, notes, ncol, mark=True):
    r += 1
    for t in (notes or []):
        ws.cell(row=r, column=1, value=t)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
        ws.cell(row=r, column=1).font = Font(name=F, size=10)
        ws.cell(row=r, column=1).alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[r].height = max(16, (len(t) // 62 + 1) * 15 + 4)
        r += 1
    return r


def _cost_sheet(wb, title, sub, rows, owner_names, notes, tag, totals=None):
    """①②成本测算（设备材料）。"""
    ws = wb.create_sheet(title)
    hr = _title(ws, title, len(HEADS), sub)
    for i, h in enumerate(HEADS, 1):
        ws.cell(row=hr, column=i, value=h)
    r, n = _write_rows(ws, rows, hr, owner_names)
    buy = sum(x[7] for x in rows if isinstance(x[7], (int, float)))
    n_own = len(owner_names or [])
    ws.cell(row=r, column=2, value="设备材料合计（%d 项，其中甲供 %d 项不计价）" % (n, n_own))
    ws.cell(row=r, column=7, value=round(buy, 2))
    ws.cell(row=r, column=9, value="甲供项材料费不计价（已标蓝，单价记 0），"
                                   "其安装人工已计入③④劳务报价")
    for k in range(1, 12):
        ws.cell(row=r, column=k).fill = YEL
        ws.cell(row=r, column=k).font = Font(name=F, size=10, bold=True)
    r += 1

    # 成本测算合计块：设备材料 + 劳务 → 直接费 → 取费链 → 成本测算总计（含税）。
    # 少了这一块，"成本测算表"就只有材料费，看不出这个项目到底要花多少钱。
    if totals:
        chain = totals.get("chain") or {}

        def _line(label, calc, amount, note):
            nonlocal r
            ws.cell(row=r, column=2, value=label)
            ws.cell(row=r, column=3, value=calc)
            ws.cell(row=r, column=6, value=round(amount or 0, 2))
            ws.cell(row=r, column=9, value=note)
            ws.cell(row=r, column=10, value="取费口径｜企业取费参数配置")
            ws.cell(row=r, column=11, value="—（取费口径，无需外部链接）")
            ws.cell(row=r, column=12, value="高（企业取费参数）")
            r += 1

        if totals.get("labor"):
            _line("劳务费合计（人工+机械）", "见⑤⑥劳务报价明细", totals["labor"],
                  "甲供材料不计价，只计安装人工；含量库逐行来源见⑤⑥")
        _line("直接费合计", "设备材料 + 劳务 + 交通安措", chain.get("直接费", buy),
              "交通安措按主体工作量计取，无机型项目为 0")
        if chain.get("降效"):
            _line("人工降效与窝工", "直接费 × 6%", chain.get("降效"),
                  "边通车分段跳槽、间断作业降效")
        if chain.get("风险"):
            _line("不可预见风险包干", "直接费 × 4%", chain.get("风险"), "包干不另计")
        if chain.get("管理费"):
            _line("管理费", "(直接费 + 降效 + 风险) × %s" % (
                "5%" if not chain.get("降效") else "10%"), chain.get("管理费"),
                "采购组织/项目管理/驻地库房/检测验收/资料")
        _line("税金", "简易计税 3%", chain.get("税金"), "9% 专票按差额计取")
        ws.cell(row=r, column=2, value="成本测算总计（%s·含税）"
                % ("采购总包口径" if not chain.get("降效") else "施工取费口径"))
        ws.cell(row=r, column=3, value="上列逐级累加")
        ws.cell(row=r, column=6, value=round(chain.get("总计", 0), 2))
        ws.cell(row=r, column=9, value="含税总价；可选项按现场签证另计")
        ws.cell(row=r, column=10, value="取费口径｜企业取费参数配置")
        ws.cell(row=r, column=11, value="—（取费口径，无需外部链接）")
        ws.cell(row=r, column=12, value="高（企业取费参数）")
        for k in range(1, 13):
            ws.cell(row=r, column=k).fill = YEL
            ws.cell(row=r, column=k).font = Font(name=F, size=11, bold=True, color="C00000")
        r += 1
    _notes_block(ws, r, notes, len(HEADS))
    _style(ws, WIDTHS, header_row=hr, dyn_from=hr + 1, wrap={2, 3, 8, 9, 10, 11, 12})
    return round(buy, 2)


def _labor_sheet(wb, title, sub, rows, owner_names, summary, chain, notes, tag):
    """③④劳务报价（对外总包）。chain 为已经算好的取费链。"""
    ws = wb.create_sheet(title)
    hr = _title(ws, title, len(HEADS), sub)
    for i, h in enumerate(HEADS, 1):
        ws.cell(row=hr, column=i, value=h)
    r, n = _write_rows(ws, rows, hr, owner_names)
    direct = sum(x[7] for x in rows if isinstance(x[7], (int, float)))
    units = summary.get("主体数量") or summary.get("单位数") or 0
    unit_key = summary.get("单位") or "座"
    env = summary.get("环境修正", {}) or {}

    def line(label, calc, amount, note, bold=False, fill=None, src="取费口径｜企业取费参数配置"):
        nonlocal r
        ws.cell(row=r, column=2, value=label)
        ws.cell(row=r, column=3, value=calc)
        ws.cell(row=r, column=7, value=round(amount or 0, 2))
        ws.cell(row=r, column=8, value=src)
        ws.cell(row=r, column=9, value=note)
        ws.cell(row=r, column=10, value=src)
        ws.cell(row=r, column=11, value="—（取费口径，无需外部链接）")
        ws.cell(row=r, column=12, value="高（企业取费参数）")
        if units:
            ws.cell(row=r, column=5, value="折合 %.2f 元/%s" % ((amount or 0) / units, unit_key))
        if fill:
            for k in range(1, 13):
                ws.cell(row=r, column=k).fill = fill
        if bold:
            for k in range(1, 13):
                ws.cell(row=r, column=k).font = Font(name=F, size=10, bold=True)
        r += 1

    supply_only = bool(summary.get("纯采购清单"))
    if supply_only:
        # 采购清单：只走「设备材料直接费 → 采购管理费 5% → 税金 3%」。
        # 施工类的 交通安措 / 降效 / 风险 一律不出现（没有施工，收这些就是乱收费）
        # 折合"元/单位"也不出：采购清单里 米/台/套 混着加起来除总数没有意义
        units = 0
        line("一、设备材料直接费", "上列逐项 单价 × 数量（明细同①③）",
             chain.get("直接费", direct),
             "设备材料到场价（含税）；本清单不含施工内容", bold=True,
             src="设备清单取价结果（企业价格库 / 历史报价库 / 互联网检索）")
        line("二、采购管理费", "直接费 × %d%%" % round(
            (chain.get("管理费", 0) / chain["直接费"] * 100) if chain.get("直接费") else 5),
             chain.get("管理费", 0), "采购组织、比价询价、到货验收、资金占用",
             src="取费口径｜材料采购管理费 5%")
        line("三、税金", "简易计税 3%", chain.get("税金", 0), "9% 专票按差额计取")
        line("四、对外报价总额（总包·含税）", "1~3 逐级累加", chain.get("总计", 0),
             "折合 %.2f 元/%s；可选项按现场签证另计" % (
                 (chain.get("总计", 0) or 0) / units if units else 0, unit_key),
             bold=True, fill=YEL)
        for c in ws[r - 1]:
            c.font = Font(name=F, size=11, bold=True, color="C00000")
        _notes_block(ws, r, notes, len(HEADS))
        _style(ws, WIDTHS, header_row=hr, dyn_from=hr + 1, wrap={2, 3, 8, 9, 10, 11, 12})
        return round(direct, 2)

    line("一、劳务直接费小计", "上列各工序综合单价 × 数量", direct,
         "已含人工与机械；甲供材料不计价，只计安装人工", bold=True,
         src="人工含量库 + 企业定额库（逐行来源见各明细行）")
    # 交通安措只在真的有施工、且真计了这笔钱时才出一行
    if summary.get("安措合计"):
        line("二、交通安措（必选）", "%d 元/%s × %s" % (summary.get("安措元每单位", 295),
                                                  unit_key, units),
             summary.get("安措合计", 0), "路障锥桶警示牌 70 + 摇旗指挥 120 + 警戒瞭望 40 "
                                         "+ 夜间警示 25 + 清理恢复 40", bold=True,
             src="企业取费参数｜交通安措 295 元/%s" % unit_key)
    if env.get("金额"):
        line("三、环境与条件修正", "劳务直接费 × %.1f%%（上限 8%%）" % ((env.get("系数") or 0) * 100),
             env.get("金额", 0), "命中条件：%s；边通车/占道已含在降效 6%% 内，不重复计取"
             % ("、".join(h.get("条件", "") for h in env.get("命中", [])) or "无"),
             src="项目技术方案原文（环境与条件修正规则）")
    line("四、人工降效与窝工", "直接费 × 6%", chain.get("降效", 0),
         "边通车分段跳槽、间断作业降效")
    line("五、不可预见风险包干", "直接费 × 4%", chain.get("风险", 0), "包干不另计")
    line("六、管理费", "(直接费 + 降效 + 风险) × 10%", chain.get("管理费", 0),
         "含驻地、库房、交安设施、检测验收、资料")
    line("七、税金", "简易计税 3%", chain.get("税金", 0), "9% 专票按差额计取")
    line("八、对外报价总额（总包·含税）", "1~7 逐级累加", chain.get("总计", 0),
         "折合 %.2f 元/%s；可选项按现场签证另计" % (
             (chain.get("总计", 0) or 0) / units if units else 0, unit_key),
         bold=True, fill=YEL)
    for c in ws[r - 1]:
        c.font = Font(name=F, size=11, bold=True, color="C00000")
    _notes_block(ws, r, notes, len(HEADS))
    _style(ws, WIDTHS, header_row=hr, dyn_from=hr + 1, wrap={2, 3, 8, 9, 10, 11, 12})
    return round(direct, 2)


def build(project, tagged, cost_a, cost_b, labor_a, labor_b, summary, out_path,
          notes=None, owner_names=None):
    """六件套：①设备清单 ②劳务清单 ③④成本测算 ⑤⑥劳务报价。

    cost_a/b、labor_a/b 均为 12 列行数据（库+网 / 纯网）。
    """
    wb = Workbook()
    wb.remove(wb.active)
    # 清单性质：整张清单没有任何一项标"甲供"，说明这是一份纯采购清单，
    # 就不该出现甲供/劳务分包那套口径
    nature = "采购清单" if not owner_names else "工程量清单"
    chain_a = summary.get("劳务报价库网") or summary.get("甲供C30版", {}) or {}
    chain_b = summary.get("劳务报价纯网") or chain_a
    supply_only = bool(summary.get("纯采购清单"))
    if not labor_a:      # 纯设备采购清单：劳务表给一句说明，不留空表
        labor_a = [["", "（本清单无劳务子目）",
                    "整张清单都是设备材料采购项，不含施工内容", "", "项", 1,
                    "—", 0.0, "—", "—", "—", "—"]]
        labor_b = list(labor_a)
    if supply_only:
        # 采购清单没有劳务分包这回事。⑤⑥改成"设备材料采购总包报价"：
        # 明细直接引用③④的设备行，取费走 采购管理费 5% + 税金 3%，
        # 不再是"劳务直接费 0 元 + 交通安措 295 元/座 × 一堆米"的鬼表
        labor_a, labor_b = cost_a, cost_b
    _equipment_sheet(wb, project, tagged, labor_a, cost_a, owner_names, nature)
    _labor_list_sheet(wb, project, labor_a)
    _cost_sheet(wb, "③成本测算（库+网检索）",
                ("本清单为设备材料采购清单，单价＝采购价（含税）；无甲供、无劳务子目"
                 if nature == "采购清单" else
                 "设备材料：价格库 → 历史报价库 → 互联网检索；甲供项材料不计价（蓝底），"
                 "安装人工见⑤⑥"),
                cost_a, owner_names, notes, "库网",
                totals={"chain": summary.get("甲供C30版") or chain_a,
                        "labor": summary.get("劳务合计") or 0})
    _cost_sheet(wb, "④成本测算（纯网检索）",
                "设备材料：全部走互联网检索；含税 ÷1.13 → 不含税 → 按品类与采购量折算工程价",
                cost_b, owner_names, notes, "纯网",
                totals={"chain": summary.get("纯网报价") or chain_a,
                        "labor": summary.get("纯网劳务合计") or 0})
    sub_a = ("设备材料采购总包报价：明细同③，取费＝采购管理费 5% + 税金 3%"
             "（本清单无劳务内容）" if supply_only else
             "劳务：定额 / 人工含量库（工日含量×工日单价）+ 网查工日单价校核 → 对外总包报价")
    sub_b = ("设备材料采购总包报价：明细同④，取费＝采购管理费 5% + 税金 3%"
             "（本清单无劳务内容）" if supply_only else
             "劳务：人工单价全部取网查当地工日单价，含量不变 → 对外总包报价")
    _labor_sheet(wb, "⑤劳务报价（库+网检索）", sub_a,
                 labor_a, owner_names, summary, chain_a, notes, "库网")
    _labor_sheet(wb, "⑥劳务报价（纯网检索）", sub_b,
                 labor_b, owner_names, summary, chain_b, notes, "纯网")
    wb.save(out_path)
    return out_path
