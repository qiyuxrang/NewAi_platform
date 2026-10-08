# -*- coding: utf-8 -*-
"""钢制管材（镀锌钢管 / 焊接钢管 / 无缝钢管）专项估价。

钢管的价 90% 由「每米重量 × 钢材单价」决定，规格给了就能算准：
    每米重量 kg/m（标准壁厚，见下表） × 钢材到场单价(元/kg) + 加工费

标定：2026-09 热镀锌钢管到货 5200~6200 元/吨（6.0 元/kg 上下），
工程批量到场口径（含税、含运费与流通环节）取 8.5 元/kg。
校验：DN100（SC100）算得 ≈96 元/m，与市场 70~90 元/m 同量级；
而网上抓到的 2293 元/m（把别的规格/按吨的价抓回来了）会被拦掉。
"""
import re

# DN → 标准壁厚下每米重量 kg/m（焊接/镀锌钢管常用壁厚）
DN_KG = [(15, 1.26), (20, 1.63), (25, 2.42), (32, 3.13), (40, 3.84),
         (50, 4.88), (65, 6.64), (80, 8.34), (100, 11.29), (125, 15.05),
         (150, 18.18), (200, 26.10), (250, 35.60), (300, 46.00),
         (350, 56.00), (400, 66.00)]

SC_RE = re.compile(r"(?:SC|DN|Sc|dc|sc|dn)\s*[-－]?\s*(\d{2,4})")
PHI_RE = re.compile(r"[ΦφøØ]\s*(\d{2,4})")
WALL_RE = re.compile(r"[×xX*]\s*(\d{1,2}(?:\.\d)?)\s*(?:mm)?")

STEEL_KG = 7.0          # 元/kg（到场价口径，含税、含镀锌与流通）
MIN_PRICE = 3.0         # 元/m 下限，防止算出离谱的小数


def is_pipe(text):
    """是不是"按米卖的钢制管材"。桥架/母线/线槽是钢结构件，不走这个公式。"""
    t = str(text or "")
    if re.search(r"桥架|母线|线槽|槽盒|支架|法兰|弯头|三通|接头", t):
        return False
    if re.search(r"钢管|焊接管|无缝管|镀锌管|衬塑管", t):
        return True
    return bool(re.search(r"\b(?:SC|DN)\s*\d{2,4}", t.upper())) and "管" in t


def unit_ok(unit):
    u = str(unit or "").strip().lower()
    return u in ("", "m", "米", "km", "千米")


def _kg_by_dn(dn):
    if dn is None:
        return None
    prev = DN_KG[0]
    for dn_i, kg in DN_KG:
        if dn <= dn_i:
            if dn == dn_i:
                return kg
            # 落在两档之间：按重量近似线性插值（DN 越大壁厚越大）
            lo_dn, lo_kg = prev
            if dn_i == lo_dn:
                return kg
            return round(lo_kg + (kg - lo_kg) * (dn - lo_dn) / (dn_i - lo_dn), 3)
        prev = (dn_i, kg)
    return DN_KG[-1][1]


def parse(text):
    """解析出 (DN, 每米重量 kg/m)；解析不到返回 (None, None)。"""
    t = str(text or "")
    up = t.upper()
    m = SC_RE.search(up)
    dn = float(m.group(1)) if m else None
    m2 = PHI_RE.search(t)
    if m2:
        od = float(m2.group(1))
        # 外径 → 公称直径：DN ≈ (OD-10)/1.05（114→99、89→75、165→147）
        dn2 = max(15.0, round((od - 10) / 1.05))
        mw = WALL_RE.search(t[t.find(m2.group(0)) + len(m2.group(0)):])
        if mw:
            wall = float(mw.group(1))
            if 0.5 <= wall <= 20:
                import math
                kg = math.pi * (od - wall) * wall * 7.85 / 1000.0
                return dn2, round(kg, 3)
        dn = dn if dn is not None else dn2
    if dn is None:
        return None, None
    return dn, _kg_by_dn(dn)


def by_formula(text):
    """返回 (每米价, 说明)；识别不出规格返回 (None, 原因)。"""
    if not is_pipe(text):
        return None, "不是按米计的钢制管材"
    dn, kg = parse(text)
    if not kg:
        return None, "没写 DN/SC/Φ 规格，钢管算不了"
    price = max(MIN_PRICE, round(kg * STEEL_KG, 2))
    return price, ("钢管规格公式｜DN%g → 每米 %.2f kg × 钢材到场价 %.1f 元/kg = %.2f 元/m"
                   % (dn, kg, STEEL_KG, price))
