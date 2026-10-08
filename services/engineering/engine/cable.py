# -*- coding: utf-8 -*-
"""电缆专项取价：结构化匹配历史价 + 铜价公式法兜底。

电缆是采购清单里金额最大、也最难联网查的一类：网上没有"ZC-YJV 3×4 每米多少钱"
这种公开挂牌价。但电缆价格 80% 由铜重决定，是可以用公式算准的：

    每米铜重(kg) = Σ(芯数 × 截面mm²) × 8.89 / 1000
    每米价 = 铜重 × 铜价 × 1.02(损耗) × 1.18(绝缘护套) + 加工费(按截面档)

用企业历史价库里的 149 条电缆价标定过：2*35 / 3*35 / 4*6 三档偏差都在 2% 以内。
口径：先按"芯数×截面"结构化匹配历史价，匹配不到再用公式算并标注。
"""
import re

CU_DENSITY = 8.89          # 铜密度 g/cm³
# 默认铜价 元/kg。用企业历史价库里的电缆价反标定：2*35→65.2、3*35→66.5、4*6→63.1，
# 取 65 与我们其他价格口径一致；联网查到当日铜价时会自动覆盖。
DEFAULT_COPPER = 65.0
JACKET_RATIO = 0.18        # 绝缘+护套+填充占铜材成本的比例
CU_LOSS = 1.02             # 铜材损耗

MODEL_RE = re.compile(
    r"(ZC|ZR|NH|WDZ|WDZN|YJV22|YJV32|YJLV22|YJLV|YJV|VV22|VV|BV|BVR|RTTZ|KVV|KVVP|"
    r"RVV|RVS|RVVP|YCW|YC|YZ|YH|"
    # 矿用电缆型号（MYQ/MYP/MYPTJ/MCP…）：以前不在型号表里，矿用电缆被当成
    # 普通"按米"材料走保守暂估，3×1.5 的 MYQ 会被估成 10 元/m 的常数
    r"MYPTJ|MYJV22|MYJV|MYQ|MYP|MCPT|MCP|UCP|UGFP|UGF)")
SECTION_RE = re.compile(r"(\d{1,2})\s*[×xX*]\s*(\d{1,4}(?:\.\d+)?)")


def is_cable(text):
    t = str(text or "")
    up = t.upper()
    if re.search(r"桥架|母线|线槽|支架|导管|穿线管|电缆沟|电缆头|终端|中间接头", t):
        return False          # 桥架/母线/管是钢制的，不能按铜截面算
    # 型号 + 芯数×截面 就认：以前还要求必须有 kV/mm² 标记，
    # 「信号线 RVVP 10×1.5」这种只写芯数×截面的电缆就漏了，最后按"米"兜底又取不到 → 0 元
    return bool(MODEL_RE.search(up)) and (
        "KV" in up or "MM" in up or "²" in t or bool(SECTION_RE.search(t)))


def parse(text):
    """解析电缆型号/规格 → (型号, [(芯数,截面)...], 总铜截面mm², 是否高压)。"""
    t = str(text or "")
    up = t.upper()
    m = MODEL_RE.search(up)
    model = m.group(1) if m else ""
    pairs = [(int(a), float(b)) for a, b in SECTION_RE.findall(t)]
    # 名称和备注里常常都把规格写了一遍（"…3×240mm² … 3×240mm²"），
    # 不去重会把铜截面算成两倍、价格翻番
    n = len(pairs)
    for per in range(1, n // 2 + 1):
        if n % per == 0 and all(pairs[i] == pairs[i % per] for i in range(n)):
            pairs = pairs[:per]
            break
    total = sum(n * s for n, s in pairs)
    # ⚠ 高压判定：以前写成"数字/数字 KV"就算高压，结果 0.6/1kV 这种
    # 低压电缆也被套上 ×1.25 的高压系数，全线电缆价格虚高 25%。
    # 现在按"相电压 ≥6kV"判：0.6/1kV、0.45/0.75kV 都是低压，8.7/10kV、26/35kV 才是高压。
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*KV", up)
    high = bool(m2 and float(m2.group(1)) >= 6.0)
    if not high:
        high = bool(re.search(r"(?<![\d.])(?:6|10|20|35|66|110)\s*KV", up))
    return model, pairs, total, high


def copper_weight(total_mm2):
    """每米铜重 kg/m。"""
    return total_mm2 * CU_DENSITY / 1000.0


def process_fee(main_section):
    """每米加工费（拉丝、绞合、挤绝缘、铠装、成缆），按主截面分档。"""
    s = float(main_section or 0)
    for lim, fee in ((6, 2.0), (16, 2.6), (35, 3.5), (70, 5.0),
                     (120, 7.0), (240, 9.0)):
        if s <= lim:
            return fee
    return 12.0


def by_formula(text, copper=DEFAULT_COPPER):
    """铜价公式法算电缆每米价，返回 (单价, 说明) 或 (None, 原因)。"""
    model, pairs, total, high = parse(text)
    if not pairs or total <= 0:
        return None, "未识别出芯数×截面"
    w = copper_weight(total)
    cu = w * float(copper) * CU_LOSS
    jacket = cu * JACKET_RATIO
    main = max((s for _, s in pairs), default=0)
    fee = process_fee(main)
    price = cu + jacket + fee
    if high:
        price *= 1.25
    note = ("铜价公式｜%d 处截面共 %gmm² → 铜重 %.4f kg/m × 铜价 %.0f 元/kg × 1.02 损耗 "
            "× 1.18(绝缘护套) + 加工费 %.1f 元/m%s = %.2f 元/m"
            % (len(pairs), total, w, copper, fee,
               "（高压 ×1.25）" if high else "", price))
    return round(price, 2), note


def _similar(a, b, tol):
    return abs(a - b) <= max(1e-6, tol * max(abs(a), abs(b)))


def unit_ok(unit):
    """电缆清单单位一般是 m/km，历史价常不填单位；根/盘/箱这类不能直接比。"""
    u = str(unit or "").strip().lower()
    return u in ("", "m", "米", "km", "千米", "米/根")


def price_from_history(name, spec, unit, hist):
    """按"芯数×截面"结构化匹配历史价；找不到返回 None。"""
    text = "%s %s" % (name, spec)
    if not is_cable(text) or not unit_ok(unit):
        return None
    model, pairs, total, high = parse(text)
    if total <= 0:
        return None
    cands = []
    for h in hist:
        if not h.get("单价元"):
            continue
        ht = "%s %s" % (h.get("名称", ""), h.get("规格", ""))
        if not is_cable(ht):
            continue
        hm, hp, htotal, hhigh = parse(ht)
        if htotal <= 0 or high != hhigh:
            continue
        try:
            price = float(str(h["单价元"]).replace(",", ""))
        except Exception:
            continue
        same_model = bool(hm and model and hm[:3] == model[:3])
        # ⚠ 不同型号之间只比"总铜截面"会串味：KVVP 8×1.5 控制电缆和
        # YJV 3×4 电力电缆总截面都是 12mm²，价差却有 50%~80%。
        # 型号不同就必须**芯数**也一致，才认这条历史价。
        if not same_model and sum(n for n, _ in hp) != sum(n for n, _ in pairs):
            continue
        if _similar(total, htotal, 0.06 if same_model else 0.02):
            cands.append((price, h, same_model, _src_rank(h)))
    if not cands:
        return None
    # 优先序：同型号 > 来源是供应商/采购价（不是劳务价）> 价格低者
    material = [c for c in cands if c[3] > 0]
    if material:
        cands = material
    cands.sort(key=lambda x: (-x[2], -x[3], x[0]))
    top = cands[:3]
    prices = sorted(c[0] for c in top)
    return {"单价": prices[len(prices) // 2],
            "来源": "企业历史报价库｜%s（%s）" % (
                top[0][1].get("来源文件", ""), top[0][1].get("规格", "")),
            "名称": top[0][1].get("名称"),
            "相似度": 1.0 if top[0][2] else 0.9,
            "样本数": len(prices),
            "区间": "%s~%s" % (prices[0], prices[-1]),
            "匹配口径": "按芯数×截面结构化匹配（总铜截面 %gmm²）" % total,
            "来源类型": "电缆历史价"}


def _src_rank(h):
    """来源文件是"供应商/采购/价格库"这类材料价的加 1 分；"劳务/人工"的减 1 分。"""
    f = str(h.get("来源文件", "")) + str(h.get("表名", ""))
    if re.search(r"劳务|人工|安装|施工", f):
        return -1
    if re.search(r"供应商|采购|价格|询价|材料|设备", f):
        return 1
    return 0


def price_any(name, spec, unit, hist, copper=DEFAULT_COPPER):
    """电缆取价总入口：历史价优先，取不到用铜价公式。"""
    text = "%s %s" % (name, spec)
    if not is_cable(text) or not unit_ok(unit):
        return None
    h = price_from_history(name, spec, unit, hist)
    if h:
        return h
    p, note = by_formula(text, copper)
    if not p:
        return None
    return {"单价": p, "来源": "电缆行情公式｜" + note, "名称": name,
            "相似度": 0.0, "样本数": 1, "区间": "%s~%s" % (p, p),
            "匹配口径": note, "来源类型": "电缆公式"}
