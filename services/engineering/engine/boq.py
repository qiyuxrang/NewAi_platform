# -*- coding: utf-8 -*-
"""工程量清单解析：拆行、甲供判定、分类、标注计算方式。

规则（来自用户确认）：
- 设备类标注『甲供』的，不报价，直接排除；
- 其余项一律报价，包含劳务；
- 备注里同时出现『包工包料』的，即使提到甲供也要报价（如路灯基础，钢筋砼甲供但施工要报）。
"""
import os
import re

from openpyxl import load_workbook

# 施工动作词：名称里出现这些，说明这一行是"工序"而不是"东西"
ACTION_RE = re.compile(
    r"安装|敷设|开挖|浇筑|组立|拆除|砌筑|接地|调试|养护|架设|铺设|穿线|接线|"
    r"吊装|制作|绑扎|回填|夯实|试验|检测|安装调试|就位|搬运|清理")
# 物件名词：名称里有这些通常是可以采购/报价的东西
DEVICE_NOUN_RE = re.compile(
    r"器|机|柜|箱|屏|盘|缆|线|管|表|仪|泵|阀|灯|扇|杆|件|块|板|盒|架|槽|套")


HEAD_ALIASES = {
    "序号": ["序号", "顺序", "编号", "项次"],
    # 现场清单叫法很多：设备名称 / 物料名称 / 材料名称 / 产品名称 都要认
    "项目名称": ["项目名称", "设备名称", "物料名称", "材料名称", "产品名称", "标的名称",
                "分项工程名称", "子目名称", "名称", "品名"],
    "技术参数": ["技术参数", "规格型号", "规格参数", "技术要求", "型号及规格",
                "规格及型号", "规格", "型号", "参数"],
    "单位": ["单位", "计量单位"],
    "数量": ["数量", "工程量", "清单数量"],
    "备注": ["备注", "说明", "特征描述"],
}

# 大类识别，顺序即优先级
CATEGORY_RULES = [
    ("管理费", r"综合管理费|管理费|总承包服务费|规费|税金"),
    ("措施项目", r"安全文明|措施费|围挡|临时设施|脚手架|二次搬运"),
    ("劳务施工", r"基础|土方|开挖|浇筑|养护|安装|拆除|敷设|砌筑|电缆沟|接地|立杆|组立"),
    ("材料", r"混凝土|钢筋|砂石|砌块|穿线管|扁钢|接地棒|预埋件|法兰|螺栓"),
    ("设备", r"灯具|灯杆|电池|组件|控制器|箱|柜|机|屏|摄像机|交换机|服务器|线缆|导线|电缆|光缆|管"),
]


def _text(v):
    return "" if v is None else str(v).strip()


def to_number(v):
    """把清单里的数量列转成数字。

    现场清单的「数量」列什么写法都有：数字、`"1200"`、`"1,200"`、`"1200 米"`、
    `"约 3.5"`、`"1.2万"`。以前直接把原值往下传，最后在做
    `单价 × 数量` 时抛 `can't multiply sequence by non-int of type 'float'`，
    整份清单直接跑挂。这里统一收口：能转就转，转不出来返回 None（当 0 处理）。
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if not t or t in ("-", "—", "/", "无", "NaN", "nan"):
        return None
    t = t.replace(",", "").replace("，", "").replace(" ", "").replace("　", "")
    t = t.replace("约", "").replace("≈", "").replace("~", "").replace("－", "-")
    mult = 1.0
    if t.endswith("万"):
        mult, t = 10000.0, t[:-1]
    elif t.endswith("千"):
        mult, t = 1000.0, t[:-1]
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        n = float(m.group(0)) * mult
    except ValueError:
        return None
    return n if n == n else None


def find_header(rows):
    """在前 8 行里找表头行，返回 (行号, 列映射)。"""
    for i, r in enumerate(rows[:8]):
        cells = [_text(c) for c in r]
        mapping = {}
        for key, names in HEAD_ALIASES.items():
            for n in names:
                if n in cells:
                    mapping[key] = cells.index(n)
                    break
        # 表头写法太杂（"设备材料名称""产品目录中的型号及规格""顺序"），
        # 精确匹配找不到就退一步做"包含匹配"
        if "项目名称" not in mapping:
            for ci, c in enumerate(cells):
                if any(k in c for k in ("项目名称", "设备名称", "设备材料名称",
                                        "材料名称", "物料名称", "产品名称",
                                        "子目名称", "分项工程名称", "标的名称")) \
                        or (c.endswith("名称") and len(c) <= 12):
                    mapping["项目名称"] = ci
                    break
        for key, kws in (("序号", ("序号", "顺序", "项次")),
                         ("技术参数", ("型号", "规格", "参数")),
                         ("单位", ("单位",)),
                         ("数量", ("数量", "工程量")),
                         ("备注", ("备注", "说明"))):
            if key in mapping:
                continue
            for ci, c in enumerate(cells):
                if c and len(c) <= 16 and any(k in c for k in kws):
                    mapping[key] = ci
                    break
        if "项目名称" in mapping:
            return i, mapping
    return None, {}


def is_owner_supplied(note):
    """判断是否为甲供项。整项甲供才算；提到包工包料的不算。"""
    n = _text(note).replace("\n", " ")
    if not n:
        return False
    if "包工包料" in n:
        return False
    # 备注以「甲供」开头，或整条就是甲供
    return n.startswith("甲供") or n == "甲供"


def classify(name, note):
    nm, nt = _text(name), _text(note)
    text = "%s %s" % (nm, nt)
    if "包工包料" in nt:
        return "包工包料"
    # 结构类（基础/垫层/基坑/基座）一律按包工包料走工序分解，
    # 不然会被"劳务施工"吃掉，只按定额给一个偏低的单价
    if re.search(r"基础|垫层|基坑|基座", text) and not re.search(
            r"基础数据|基础平台|软件|平台|系统集成", text):
        return "包工包料"
    # ⚠ 名称本身就是个"东西"、且名称里没有施工动作时，备注/规格里出现
    # "安装/调试"只说明它要装，不能因此把整项按劳务算。
    # 实例："光纤收发器 工业级…导轨式安装" 被算成劳务 → 劳务含量库里没有
    # 收发器这条 → 单价 0、来源空白。
    if DEVICE_NOUN_RE.search(nm) and not ACTION_RE.search(nm):
        for cat, pat in CATEGORY_RULES:
            if cat in ("劳务施工", "措施项目", "管理费"):
                continue
            if re.search(pat, text):
                return cat
        return "设备"
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, text):
            return cat
    return "其他"


def calc_method(category, note):
    n = _text(note)
    if category == "包工包料":
        return "按工序分解：土方 / 结构 / 浇筑养护 / 措施 / 特殊地质"
    if category == "劳务施工":
        return "劳务综合单价 × 数量"
    if category == "措施项目":
        return "按费率或包干计取"
    if category == "管理费":
        return "按直接费费率计取"
    if category == "材料":
        return "材料单价 × 数量（甲供除外）"
    if category == "设备":
        return "匹配价格库 / 互联网检索"
    return "人工判定"


def auto_note(category, note, owner):
    """自动生成『依据/说明』：这一项为什么这么算、有什么风险。"""
    parts = []
    if owner:
        parts.append("甲方供料，不计入报价")
    elif category == "包工包料":
        parts.append("需包工包料报价；备注中标注甲供的材料（钢筋、混凝土、预埋件等）不计入材料费，只计施工")
    elif category == "劳务施工":
        parts.append("按劳务综合单价计取，不含设备材料")
    elif category == "管理费":
        parts.append("按直接费费率计取")
    elif category == "措施项目":
        parts.append("按费率或包干计取")
    elif category == "材料":
        parts.append("材料单价 × 数量")
    elif category == "设备":
        parts.append("匹配价格库取价，未命中转互联网检索")

    n = _text(note)
    if re.search(r"暂无.*图纸|没有.*图纸|待.*图纸", n):
        parts.append("⚠ 备注提示无施工图纸，需出图后核定")
    if "核减" in n:
        parts.append("⚠ 备注提示可能核减，报价前需确认")
    if "包工包料" in n and "甲供" in n:
        parts.append("⚠ 该项同时涉及甲供与包工包料，需逐项扣减材料")
    return "；".join(parts)


def parse_sheet(ws, max_scan=2000):
    """解析单个 sheet，返回明细行列表。支持合并单元格向下填充、多子项。"""
    rows = [list(r) for r in ws.iter_rows(values_only=True)][:max_scan]
    hdr, col = find_header(rows)
    if hdr is None:
        return []
    items = []
    last_name, last_unit = "", ""
    for excel_row, r in enumerate(rows[hdr + 1:], hdr + 2):
        def cell(key):
            i = col.get(key)
            return r[i] if i is not None and i < len(r) else None

        raw_seq = cell("序号")
        raw_name = cell("项目名称")
        raw_spec = cell("技术参数")
        raw_unit = cell("单位")
        raw_qty = cell("数量")
        name = _text(raw_name)
        spec = _text(raw_spec)
        unit = _text(raw_unit)
        qty = to_number(raw_qty)
        note = _text(cell("备注"))
        if name in ("小计", "合计", "总计", "合 计") or name.startswith("报价包含"):
            continue
        if not name:
            # 合并单元格：子项行的名称是空的，沿用上一行的名称（同一设备的多个规格）
            if last_name and (qty is not None or spec):
                name = last_name
            else:
                continue
        if not unit and last_unit:
            unit = last_unit
        last_name, last_unit = name, unit or last_unit
        if qty is None:
            continue
        # 技术参数并进备注：取价、判甲供都要看规格，不能丢
        full_note = ("%s %s" % (note, spec)).strip()
        cat = classify(name, full_note)
        owner = is_owner_supplied(full_note)
        items.append({
            "来源Sheet": ws.title,
            "来源Excel行号": excel_row,
            "原始序号": raw_seq,
            "原始名称": raw_name,
            "原始规格": raw_spec,
            "原始单位": raw_unit,
            "原始数量": raw_qty,
            "序号": _text(raw_seq),
            "项目名称": name.replace("\n", " "),
            "规格": spec.replace("\n", " "),
            "单位": unit,
            "数量": qty,
            "类别": cat,
            "甲供": "是" if owner else "",
            "是否报价": "否" if owner else "是",
            "计算方式": "" if owner else calc_method(cat, full_note),
            "依据/说明": auto_note(cat, full_note, owner),
            "备注": full_note.replace("\n", " "),
            "审核": "",
        })
    return items


def parse_all(path, max_scan=2000):
    """读整本清单（所有 sheet），返回 (标题, 明细行列表)。

    现场清单常见三种情况，这里都兼容：
      ① 表头写「设备名称」而不是「项目名称」；
      ② 合并单元格——同一设备的多个规格，名称只写第一行；
      ③ 一本多 sheet（分册 + 原始明细），同一行会在多个 sheet 重复出现。
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    ws_list = list(wb.worksheets)
    parsed = [(ws, parse_sheet(ws, max_scan)) for ws in ws_list]
    # 「原始明细/按子项」这类 sheet 和分册 sheet 是同一批东西（数量逐项一致），
    # 两边都读会翻倍。有分册就用分册，只有明细时才用明细。
    DETAIL = re.compile(r"原始|明细|按子项|分册明细")
    main = [(ws, xs) for ws, xs in parsed if xs and not DETAIL.search(ws.title)]
    detail = [(ws, xs) for ws, xs in parsed if xs and DETAIL.search(ws.title)]
    use = main if main else detail
    title = ""
    for ws, xs in (detail or main or parsed):
        rows = [list(r) for r in ws.iter_rows(max_row=1, values_only=True)]
        cand = _text(rows[0][0]) if rows and rows[0] else ""
        if cand and cand != ws.title:
            title = cand
            break
    if not title:
        import os as _os
        stem = _os.path.splitext(_os.path.basename(path))[0]
        title = stem
        rows = [list(r) for r in ws_list[0].iter_rows(max_row=1, values_only=True)] if ws_list else []
        cand = _text(rows[0][0]) if rows and rows[0] else ""
        # 首行就是分类名（等于 sheet 名）时，用文件名当项目名更准
        if cand and cand != ws_list[0].title:
            title = cand
    # 「十五、供电系统 原始明细（按子项）」这种标题去掉"原始明细"后缀，留项目名
    title = re.sub(r"[\s　]*(原始明细|按子项|明细表?|汇总表?)（?[^）)]*）?\s*$", "", title).strip()
    title = title or "未命名项目"
    items = []
    for ws, xs in use:
        items.extend(xs)
    # 同名不同规格的行（如"低压电容补偿柜"配 300kvar / 240kvar）必须把规格并进名称，
    # 否则下游按名称归集工序时会串行，单价×数量≠合价。
    from collections import Counter
    cnt = Counter(x["项目名称"] for x in items)
    for x in items:
        if cnt[x["项目名称"]] > 1 and x["规格"]:
            sp = x["规格"].replace("\n", " ").strip()
            x["项目名称"] = "%s（%s）" % (x["项目名称"], sp[:28])
    # 名称+规格仍重名（同一设备在两处出现、数量不同），再加数量保证唯一，
    # 否则下游按名称归集工序/取价会串行
    cnt2 = Counter(x["项目名称"] for x in items)
    for x in items:
        if cnt2[x["项目名称"]] > 1:
            x["项目名称"] = "%s〔%g%s〕" % (x["项目名称"], x["数量"], x["单位"])
    # 完全相同的合法行仍须保留，给下游使用的派生名称追加来源以避免串行。
    cnt3 = Counter(x["项目名称"] for x in items)
    for x in items:
        if cnt3[x["项目名称"]] > 1:
            x["项目名称"] = "%s〔%s:%s〕" % (x["项目名称"], x["来源Sheet"], x["来源Excel行号"])
    wb.close()
    return title, items


def parse(path, sheet=None, max_scan=2000):
    """读清单，返回 (标题, 明细行列表)。sheet 为空时读整本。"""
    if not sheet:
        return parse_all(path, max_scan)
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(values_only=True)][:max_scan]
    wb.close()

    title = _text(rows[0][0]) if rows else ""
    hdr, col = find_header(rows)
    if hdr is None:
        return title, []

    items = []
    for r in rows[hdr + 1:]:
        name = _text(r[col["项目名称"]]) if col["项目名称"] < len(r) else ""
        if not name or name in ("小计", "合计"):
            continue
        if name.startswith("报价包含"):  # 底部说明行
            continue
        note = _text(r[col["备注"]]) if col.get("备注", 99) < len(r) else ""
        cat = classify(name, note)
        owner = is_owner_supplied(note)
        items.append({
            "序号": _text(r[col["序号"]]) if col.get("序号", 99) < len(r) else "",
            "项目名称": name.replace("\n", " "),
            "单位": _text(r[col["单位"]]) if col.get("单位", 99) < len(r) else "",
            "数量": to_number(r[col["数量"]]) if col.get("数量", 99) < len(r) else None,
            "类别": cat,
            "甲供": "是" if owner else "",
            "是否报价": "否" if owner else "是",
            "计算方式": "" if owner else calc_method(cat, note),
            "依据/说明": auto_note(cat, note, owner),
            "备注": note.replace("\n", " "),
            "审核": "",
        })
    return title, items
