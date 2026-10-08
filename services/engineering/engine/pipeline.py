# -*- coding: utf-8 -*-
"""成本测算 agent 主流程：清单进 → 四版测算出。

取价链：
  设备/材料：价格库 → 历史报价库 → 待互联网检索
  劳务/包工包料：定额库（人工费 + 机械费 + 辅材）× 地区系数 × 施工条件系数
"""
import difflib
import json
import os
import re
import urllib.parse

from engine import boq as boq_mod
from engine import cable
from engine import content as content_mod
from engine import estimate as est
from engine import pipe as pipe_mod
from engine import webprice
from engine.library import PriceLibrary
from engine.matcher import Matcher
from engine.pricing import pick_price
from engine.quota import QuotaLibrary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LABOR_STEPS = [
    {"工序": "土方综合施工", "关键词": ["人工挖一般土方"], "专业": "市政",
     "含量": 1.2 * 1.2 * 1.6, "定额单位": 100.0, "取费": ["人工费", "机械费"],
     "依据": "基坑 1.2×1.2×1.6m，人工挖一般土方（一、二类土 ≤2m）"},
    {"工序": "基础结构施工（钢筋制作绑扎）", "关键词": ["带肋钢筋"], "专业": "市政",
     "含量": 0.0526, "定额单位": 1.0, "取费": ["人工费", "机械费"],
     "依据": "钢筋 52.6kg/座（甲供），只计制作绑扎人工"},
    {"工序": "混凝土浇筑及养护", "关键词": ["混凝土基础 预拌"], "专业": "市政",
     "含量": 2.2, "定额单位": 1.0, "取费": ["人工费", "机械费"],
     "依据": "C30 混凝土 2.2m³/座（甲供），只计浇筑养护人工与机械"},
]

MEASURE_RATE = 0.05
# 特殊地质（硬地层破碎等）属于"可选项、按现场签证"，默认不计入总额。
# 需要时用参数 special_geology 传入总金额，会在包工包料工序里按数量平摊。
SPECIAL_GEOLOGY = 0.0
OUT_HEADS = est.OUT_HEADS
NAME_STOP = re.compile(r"[\s,，。;；:：/、()（）\[\]【】]+")


def _norm(s):
    return NAME_STOP.sub("", str(s or "")).lower()


def strip_paren(s):
    """去掉括号里的内容再比对：定额里常见『光(电)缆』『摄像机安装(高度m以内)』。"""
    return re.sub(r"[（(][^）)]*[）)]", "", str(s or ""))


def keywords_of(name):
    """从清单项名称里提炼定额检索关键词。"""
    text = re.sub(r"[（(].*?[)）]", " ", str(name or ""))
    parts = [p for p in re.split(r"[\s,，。;；/、]+", text) if len(p) >= 2]
    return parts[:3] or [text[:6]]


UNIT_ALIAS = {"米": "m", "m": "m", "千米": "km", "km": "km", "公斤": "kg", "kg": "kg",
              "吨": "t", "t": "t", "台": "台", "套": "套", "个": "个", "只": "只",
              "处": "处", "座": "座", "箱": "箱", "卷": "卷", "根": "根", "对": "对",
              "组": "组", "项": "项", "批": "批", "面": "面", "块": "块"}


def unit_same(a, b):
    a, b = _norm(a), _norm(b)
    # 单位写法归一到同一口径：供应商表常写"元/米""元/套"，清单写"米""套"，
    # 不去掉前缀就永远匹配不上（这是入库价"入而不用"的第二个原因）
    # 注意 _norm 已经把斜杠删掉了，"元/米"到这一步是"元米"，所以直接去前缀
    a = re.sub(r"^(?:元|人民币|¥|￥)", "", a)
    b = re.sub(r"^(?:元|人民币|¥|￥)", "", b)
    a = re.sub(r"^(?:人民币)", "", a)
    b = re.sub(r"^(?:人民币)", "", b)
    # 历史价库里很多行没填单位（尤其供应商报价单），不能因为空单位就整条弃用
    if not a or not b:
        return True
    return UNIT_ALIAS.get(a, a) == UNIT_ALIAS.get(b, b)


def unit_same_strict(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return UNIT_ALIAS.get(a, a) == UNIT_ALIAS.get(b, b)


def match_history(name, hist, unit="", spec=""):
    """在历史报价库里按名称相似度找价。

    ⚠ 必须单位一致才敢用：单位不一致的历史价（比如按『箱』报的网线配按『米』的清单）
    会把金额放大几十倍，宁可不用。
    """
    key = _norm(name)
    if not key:
        return None
    # 名称往往很泛（"线缆""低压电缆"），真正区分规格的信息在规格串里，
    # 所以名称与规格各占一半权重，任意一边高度吻合也能命中。
    skey = _norm(spec)
    scored = []
    for h in hist:
        if not h.get("单价元"):
            continue
        if not unit_same(h.get("单位"), unit):
            continue
        # 历史价格库里的"单价元"有的存成字符串（"52.35"），直接相乘会 TypeError
        try:
            hprice = float(str(h["单价元"]).replace(",", "").replace("元", ""))
        except (TypeError, ValueError):
            continue
        if hprice <= 0:
            continue
        hk = _norm(h["名称"])
        if not hk:
            continue
        # ⚠ 相似度必须按"名称"算。以前把名称+规格拼起来比，历史价那条规格很长、
        # 清单又没填规格时，相似度会被稀释到 0.4 以下，真价反而匹配不上。
        ratio = difflib.SequenceMatcher(None, key, hk).ratio()
        if key in hk or hk in key:
            ratio += 0.15
        hspec = _norm(h.get("规格"))
        if skey and hspec and (hspec in skey or skey in hspec):
            ratio += 0.20          # 规格也吻合，加分
        if ratio >= 0.86:
            scored.append((ratio, h, hprice))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    top = [s[1] for s in scored[:3]]
    prices = sorted(s[2] for s in scored[:3])
    mid = prices[len(prices) // 2]
    return {"单价": mid, "来源": top[0]["来源文件"], "名称": top[0]["名称"],
            "相似度": round(scored[0][0], 2), "样本数": len(prices),
            "区间": "%s~%s" % (prices[0], prices[-1]),
            "链接": top[0].get("链接") or "",
            "平台": top[0].get("品牌") or "",
            "网价入库": str(top[0].get("来源文件", "")).startswith("互联网检索自动入库")}


_QUOTA_CACHE = {}
_HIST_CACHE = {}


def load_history():
    if "hist" in _HIST_CACHE:
        return _HIST_CACHE["hist"]
    p = os.path.join(ROOT, "data", "library", "历史价格库.json")
    data = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    # 把历次联网查到、已自动入库的价并进来——下次先命中历史价，不用再联网
    data = list(data) + webprice.load_memo()
    # ⚠ 以前入库通道写的 入库数据.sqlite 根本没被取价用上（写进去等于白写）。
    # 这里把它并进历史价，入库的价才能被 match_history 命中。
    db = os.path.join(ROOT, "data", "library", "入库数据.sqlite")
    if os.path.exists(db):
        try:
            import sqlite3
            con = sqlite3.connect(db)
            rows = con.execute(
                "SELECT source, name, brand, model, spec, unit, price, note "
                "FROM price_rows").fetchall()
            con.close()
            for src, nm, brand, model, spec, unit, price, note in rows:
                if not (nm and price):
                    continue
                data.append({
                    "来源文件": "入库通道｜%s" % (src or "手工入库"),
                    "表名": "入库", "行号": "", "类别": "设备/材料",
                    "名称": nm, "品牌": brand or "", "型号": model or "",
                    "规格": spec or "", "单位": unit or "", "数量": None,
                    "单价元": price, "金额元": None, "备注": note or "",
                    "出现次数": 1, "入库": True})
        except Exception:  # noqa: BLE001
            pass
    _HIST_CACHE["hist"] = data
    return data


def load_quota():
    """定额库只加载一次；优先读 SQLite 知识库（省内存），没有则回落 JSON。"""
    if "quota" not in _QUOTA_CACHE:
        db = os.path.join(ROOT, "data", "library", "成本测算知识库.sqlite")
        if os.path.exists(db):
            try:
                _QUOTA_CACHE["quota"] = QuotaLibrary.from_db(db)
                return _QUOTA_CACHE["quota"]
            except Exception:  # noqa: BLE001
                pass
        _QUOTA_CACHE["quota"] = QuotaLibrary(
            os.path.join(ROOT, "data", "library", "定额基价库.json"),
            os.path.join(ROOT, "data", "library", "定额含量库.json"))
    return _QUOTA_CACHE["quota"]


OBJECT_RULES = [
    # 土建/基础类放最前：『路灯基础』『拆除旧路灯』这类要先按土建走，不能落到灯具上
    (r"基础|土方|开挖|沟槽|基坑|浇筑|钢筋|模板|拆除|立杆|铺砂|盖板|破除",
     ["基础", "土方", "开挖", "沟槽", "基坑", "浇筑", "钢筋", "模板", "拆除", "立杆", "破除"],
     ["市政"]),
    (r"枪机|球机|半球|摄像机|监控", ["摄像机", "摄像", "电视监控"], ["通用安装"]),
    (r"交换机", ["交换机"], ["通用安装"]),
    (r"服务器", ["服务器"], ["通用安装"]),
    (r"机柜|机箱", ["机柜", "机箱"], ["通用安装"]),
    (r"配电箱|配电柜|控制箱|配电设备", ["配电箱", "配电柜", "控制箱"], ["通用安装", "市政"]),
    (r"灯具|路灯|灯杆|灯架", ["路灯", "灯具", "灯"], ["市政"]),
    (r"电缆|光缆|网线|导线|线缆|跳线|光纤", ["光缆", "电缆", "网线", "导线"],
     ["通用安装", "市政"]),
    (r"接地|避雷", ["接地", "避雷"], ["通用安装", "市政"]),
]


def object_rule(name):
    for pat, words, majors in OBJECT_RULES:
        if re.search(pat, str(name or "")):
            return words, majors
    return None, None


def _step_unit_cost(pick, step, rate_web=None, uplift=0.0):
    """把一个定额子目换算成『单位含量』的劳务成本。

    step: {"取费": [...], "定额单位": 100.0, "含量": 2.304}
    rate_web: 联网查到的人工工日单价；给了就把人工费按 含量 × 工日单价 重算，
              并按「不压价」取网查价与定额价的较高者。
    """
    unit = float(step.get("定额单位") or 1.0)
    qty = float(step.get("含量") or 1.0)
    labor_fee = float(pick.get("人工费") or 0)
    mech_fee = float(pick.get("机械费") or 0)
    if rate_web:
        hours = float(pick.get("人工工日") or 0)
        if hours > 0:
            quota_rate = labor_fee / hours if hours else 0
            # 不压价：两个口径取高者，再按配置上浮（劳务往大走）
            use_rate = max(rate_web, quota_rate) * (1.0 + float(uplift or 0))
            labor_fee = hours * use_rate
    total = 0.0
    for k in (step.get("取费") or ["人工费", "机械费"]):
        total += labor_fee if k == "人工费" else (mech_fee if k == "机械费" else 0.0)
    return total / unit * qty


def pick_quota(qlib, name, unit):
    """按『对象词 + 专业范围』挑定额子目。

    宁可返回 None（标注未命中）也不要硬塞一个错子目——错子目会直接把金额算飞。
    """
    words, majors = object_rule(name)
    item_text = strip_paren(name)
    plans = []
    if words:
        # 用清单项自己出现的那个对象词作为硬约束（光缆就必须找光缆，不能拿同轴电缆顶）
        require = [w for w in words if w in item_text] or words
        for major in majors:
            plans.append({"kws": require, "source_kw": major, "require": require})
    else:
        plans.append({"kws": keywords_of(name), "source_kw": None,
                      "require": keywords_of(name)[:1]})
    for plan in plans:
        # 单位只作为排序偏好，不用来硬过滤（清单写『套』、定额写『台』很常见）
        cands = qlib.search(plan["kws"], unit=None, top=12, source_kw=plan["source_kw"])
        cands.sort(key=lambda c: (0 if "安装" in strip_paren(c.get("项目名称")) else 1,
                                  0 if unit_same(c.get("单位"), unit) else 1,
                                  -c.get("score", 0)))
        for cand in cands:
            text = strip_paren(cand.get("项目名称")) + strip_paren(cand.get("章节"))
            if plan["require"] and not any(w in text for w in plan["require"]):
                continue
            if cand.get("score", 0) < 0.5:
                continue
            return cand
    return None


def resolve_path(p):
    """配置里的路径支持相对写法（相对项目根目录），方便搬到容器/服务器。"""
    if not p:
        return p
    if os.path.isabs(p) and os.path.exists(p):
        return p
    cand = os.path.join(ROOT, p.replace("/", os.sep))
    return cand if os.path.exists(cand) else p


def price_equipment(items, cfg, pure_online=False, shared_web=None):
    """设备/材料取价。

    pure_online=False：价格库 → 历史报价库 → 互联网检索
    pure_online=True ：全部走互联网检索
    """
    plib = PriceLibrary(resolve_path(cfg["library_file"]),
                        mats_sheet=cfg["sheets"]["materials"],
                        quotes_sheet=cfg["sheets"]["quotes"])
    matcher = Matcher(plib.materials, cfg["matching"])
    hist = load_history()
    cache = webprice.Cache()
    llm_key = webprice.read_dashscope_key()
    # 第一遍：先用本地库与历史价（快），把没取到的挑出来
    out = []
    need_web = []
    for n, x in enumerate(items, 1):
        name, spec, unit = x["项目名称"], x["备注"], x["单位"]
        # 数量一律走 to_number：清单里写成 "1,200"、"1200 米" 也能算，
        # 兜住老数据里没归一化的字符串数量，避免单价×数量直接崩
        qty = boq_mod.to_number(x["数量"]) or 0
        row = [n, name, spec[:40], unit, qty, "", "", "", "", "", "", ""]
        res = None if pure_online else matcher.match(name, spec, unit)
        hit = res[0] if res else None
        if hit and hit.level == "自动采纳" and not pure_online:
            p = pick_price(plib.quotes.get(hit.material.code, []), cfg["pricing"])
            row[5] = "企业价格库｜%s %s" % (hit.material.code, hit.material.name or "物料")
            row[6] = p["price"]
            row[7] = round((p["price"] or 0) * qty, 2)
            row[9] = "%s｜价格库：%s %s" % (x["依据/说明"], hit.material.name, hit.reasons)
        else:
            h = None if pure_online else cable.price_from_history(
                name, spec, unit, hist) or match_history(name, hist, unit, spec)
            if h:
                # 钢管：历史价/网价入库前可能就把错价存进去了（比如 2293 元/m 的
                # DN100 镀锌管），命中历史价时也要过一遍规格公式，偏太多就弃用
                if pipe_mod.is_pipe("%s %s" % (name, spec)) and pipe_mod.unit_ok(unit):
                    fp, fnote = pipe_mod.by_formula("%s %s" % (name, spec))
                    hp = float(h["单价"] or 0)
                    if fp and hp and (hp > fp * 2.5 or hp < fp * 0.4):
                        row[5] = "钢管规格公式｜历史价 %.2f 偏离 %.0f%%，已弃用" % (
                            hp, abs(hp - fp) / fp * 100)
                        row[6] = fp
                        row[7] = round(fp * qty, 2)
                        row[9] = ("%s｜库内价 %.2f 元/%s 与规格公式 %.2f 元/%s 差 %.0f 倍，"
                                  "判为抓错规格/抓错单位，改按公式计取；%s"
                                  % (x["依据/说明"], hp, unit, fp, unit, hp / max(fp, 0.01),
                                     fnote))
                        out.append(row)
                        continue
                # 电缆：历史价也要过铜价公式校验——一旦坏价进了知识库，
                # 下次就会从历史价命中，绕过网价那一层的校验
                if cable.is_cable("%s %s" % (name, spec)) and cable.unit_ok(unit):
                    cop = float((cfg.get("cable") or {}).get("copper_yuan_per_kg")
                                or cable.DEFAULT_COPPER)
                    fp, fnote = cable.by_formula("%s %s" % (name, spec), cop)
                    hp = float(h["单价"] or 0)
                    if fp and hp and abs(hp - fp) / max(fp, 0.01) > 0.40:
                        row[5] = "电缆行情公式｜铜价 %.0f 元/kg（历史价 %.2f 偏离 %.0f%%，已弃用）" % (
                            cop, hp, abs(hp - fp) / fp * 100)
                        row[6] = fp
                        row[7] = round(fp * qty, 2)
                        row[9] = ("%s｜库内价 %.2f 元/%s 与铜价公式 %.2f 元/%s 偏差 %.0f%%，"
                                  "判为散价/错价，改按公式计取；%s"
                                  % (x["依据/说明"], hp, unit, fp, unit,
                                     abs(hp - fp) / fp * 100, fnote))
                        out.append(row)
                        continue
                if h.get("网价入库"):
                    row[5] = "互联网检索（已入库）｜%s" % h["来源"]
                    # 链接必须带给人工审核。早年回写知识库时把链接丢了，
                    # 这里回到网价缓存里按「名称+规格+单位」把链接捡回来
                    link = h.get("链接") or ""
                    if not link:
                        try:
                            hit = cache.get(webprice.cache_key(name, spec, unit),
                                            days=3650)
                            link = (hit or {}).get("链接") or ""
                        except Exception:  # noqa: BLE001
                            link = ""
                    row[11] = link
                elif h.get("入库"):
                    row[5] = "企业知识库（入库）｜%s" % os.path.basename(
                        str(h["来源"]).replace("入库通道｜", ""))
                else:
                    row[5] = "企业历史报价库｜%s" % os.path.basename(h["来源"])
                row[6] = h["单价"]
                row[7] = round(float(h["单价"]) * qty, 2)
                row[9] = "%s｜历史价：%s（相似度 %s，样本 %d，区间 %s）" % (
                    x["依据/说明"], h["名称"], h["相似度"], h["样本数"], h["区间"])
            else:
                row[5] = "待互联网检索"
                row[8] = "%s %s" % (name, spec[:30])
                row[9] = "%s｜本地库与历史价未命中，转互联网检索" % x["依据/说明"]
                if llm_key:
                    need_web.append((len(out), name, spec, unit, qty,
                                     x["依据/说明"]))
        out.append(row)

    # 第二遍：联网取价并行跑（缓存里已有的会直接命中，很快）
    if need_web:
        # 同一次测算里，库+网 与 纯网 两条线要搜同一批物料——第一遍搜过的
        # 结果直接复用，不再搜第二遍（这是端到端时间减半的关键）
        shared = shared_web if shared_web is not None else {}
        todo = [(t[1], t[2], t[3], t[4]) for t in need_web
                if t[1] not in shared]
        if todo:
            got_web = webprice.price_many_parallel(
                todo, cfg, workers=int(os.environ.get("WEB_WORKERS", "4")))
            shared.update(got_web)
        web = dict(shared)
        # 检索没取到的：先用「品类经验区间」即时兜底（零耗时），
        # 只有连品类区间都没有的才去问大模型（每条最多 45 秒，是真正的耗时大头）
        missed = [(t[1], t[2], t[3], t[4]) for t in need_web
                  if not (web.get(t[1]) or {}).get("found")]
        PACK_UNITS2 = {"箱", "盘", "卷", "包", "桶", "袋", "捆", "扎", "托"}
        for (n2, s2, u2, q2) in missed:
            # 电缆/电线有标定过的铜价公式，别用品类中值估：
            # 「PLC电源线 ZC-RVVP 3×4mm²」名字里有 PLC，会被 PLC 品类区间
            # （200~200000）估成 6325 元/m——而按铜价算只有 7 元/m
            if cable.is_cable("%s %s" % (n2, s2)) and cable.unit_ok(u2):
                continue
            # 钢管同理：DN/SC 规格一给，按"每米重量×钢价"就能算准，
            # 品类区间（元/米）估不出 DN100 和 DN15 的差别
            if pipe_mod.is_pipe("%s %s" % (n2, s2)) and pipe_mod.unit_ok(u2):
                continue
            # 整箱/整盘件同理：品类区间是"元/米/台"，按箱折算会小两个数量级
            if str(u2 or "") in PACK_UNITS2:
                continue
            guess, band, fnote = webprice.band_guess(n2, s2, u2)
            if not band:
                continue
            web[n2] = {"found": True, "工程价": guess, "价格区间": list(band),
                       "平台": "品类经验暂估（非网价）",
                       "标题": "%s 按品类合理区间 %.0f~%.0f 元/%s，取代表值"
                                "（区间中值）%.0f 元暂估"
                       % (n2, band[0], band[1], u2, guess),
                       "依据": "同品类工程经验区间" + ("；" + fnote if fnote else ""),
                       "备注": "⚠ 网价未取到，按品类经验区间暂估，必须询价复核"}
        # 电缆/整箱件不送去问大模型估值：电缆有铜价公式（比经验估值准），
        # 整箱件按"元/米"的品类区间估会差两个数量级。这两类留给第三遍兜底。
        missed = [(n, s, u, q) for (n, s, u, q) in missed
                  if not (web.get(n) or {}).get("found")
                  and not (cable.is_cable("%s %s" % (n, s)) and cable.unit_ok(u))
                  and not (pipe_mod.is_pipe("%s %s" % (n, s)) and pipe_mod.unit_ok(u))
                  and str(u or "") not in PACK_UNITS2]
        if missed and llm_key:
            import concurrent.futures as _cf
            # 两轮：第一轮 3 并发；个别被模型限流失败的，第二轮串行再问一次
            for round_i, batch in ((1, missed), (2, [])):
                if round_i == 2:
                    batch = [(n, s, u, q) for (n, s, u, q) in missed
                             if not (web.get(n) or {}).get("found")]
                if not batch:
                    break
                with _cf.ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(webprice.estimate_by_llm, n, s, u, q, cfg,
                                      llm_key, webprice.Cache()): n
                            for (n, s, u, q) in batch}
                    for fu in _cf.as_completed(futs):
                        n2 = futs[fu]
                        try:
                            est = fu.result()
                        except Exception:
                            continue
                        if est.get("found"):
                            web[n2] = est
        for idx, name, spec, unit, qty, basis in need_web:
            w = web.get(name)
            row = out[idx]
            if w and w.get("found"):
                plat = w.get("平台") or "网络平台"
                if "AI经验估值" in plat or "品类经验暂估" in plat:
                    row[5] = "%s｜%s" % (plat, (w.get("标题") or "")[:60])
                else:
                    row[5] = "互联网检索｜%s｜%s" % (
                        plat, (w.get("标题") or w.get("来源") or "")[:70])
                row[6] = w.get("工程价")
                row[7] = round((w.get("工程价") or 0) * qty, 2)
                if "AI经验估值" in plat or "品类经验暂估" in plat:
                    row[9] = ("%s｜⚠ 未在电商/行业站取到真实报价，本条为经验估值："
                              "区间 %s 元/%s，取值 %s 元；依据：%s；必须询价复核"
                              % (basis, w.get("价格区间"), unit, w.get("工程价"),
                                 w.get("依据") or w.get("备注") or "—"))
                    continue
                # 电缆专项：电缆价格 80% 由铜重决定，我们有标定过的铜价公式，
                # 比"百度知道"这类问答页抓来的散价可靠得多。两者差太多时以公式为准。
                if pipe_mod.is_pipe("%s %s" % (name, spec)) and pipe_mod.unit_ok(unit):
                    pp, pnote = pipe_mod.by_formula("%s %s" % (name, spec))
                    wp = w.get("工程价") or 0
                    if pp and wp and (wp > pp * 2.5 or wp < pp * 0.4):
                        row[5] = "钢管规格公式｜网价 %.2f 元/%s 偏离 %.0f%%，已弃用" % (
                            wp, unit, abs(wp - pp) / pp * 100)
                        row[6], row[7] = pp, round(pp * qty, 2)
                        row[9] = ("%s｜网价 %.2f 元/%s 与规格公式 %.2f 元/%s 差 %.0f 倍，"
                                  "判为抓错规格/抓错单位，改按公式计取；%s"
                                  % (basis, wp, unit, pp, unit, wp / max(pp, 0.01), pnote))
                        continue
                if cable.is_cable("%s %s" % (name, spec)) and cable.unit_ok(unit):
                    cop = float((cfg.get("cable") or {}).get("copper_yuan_per_kg")
                                or cable.DEFAULT_COPPER)
                    fp, fnote = cable.by_formula("%s %s" % (name, spec), cop)
                    wp = w.get("工程价") or 0
                    if fp and wp and abs(wp - fp) / max(fp, 0.01) > 0.40:
                        row[5] = "电缆行情公式｜铜价 %.0f 元/kg（网价 %.2f 偏离 %.0f%%，已弃用）" % (
                            cop, wp, abs(wp - fp) / fp * 100)
                        row[6], row[7] = fp, round(fp * qty, 2)
                        row[9] = ("%s｜网价 %.2f 元/%s 与铜价公式 %.2f 元/%s 偏差 %.0f%%，"
                                  "判为散价/错价，改按公式计取；%s"
                                  % (basis, wp, unit, fp, unit,
                                     abs(wp - fp) / fp * 100, fnote))
                        continue
                # 真实性三道闸：过不了闸的网价一律不许落表（宁可空缺，不可错挂）
                why = webprice.reject_reason(name, spec, w.get("工程价"),
                                             w.get("来源") or w.get("平台"),
                                             w.get("标题") or "", w.get("链接") or "")
                if why:
                    row[5] = "互联网检索（未过真实性校验，弃用）"
                    row[6], row[7] = 0.0, 0.0
                    row[9] = "%s｜🚫 真实性校验拒绝：%s" % (basis, why)
                    continue
                # 核验链接：人工审核时点开就能回到抓价的那个页面
                row[11] = (w.get("链接") or (w.get("检索页") or [""])[0]
                           or ("https://www.baidu.com/s?wd=" + urllib.parse.quote(
                               "%s %s 价格" % (name, spec or "")))).strip()
                row[9] = ("%s｜网价 %s 元（含税）→ 不含税 %s → %s 系数 %s → 工程价 %s；"
                          "区间 %s；抓取日期 %s；来源页 %s"
                          % (basis, w.get("原始网价（含税）"), w.get("不含税"),
                             w.get("品类"), w.get("系数"), w.get("工程价"),
                             w.get("价格区间"), w.get("抓取日期"),
                             (w.get("链接") or (w.get("检索页") or ["—"])[0])))
                if w.get("预警"):
                    row[9] += "｜" + w["预警"]
            else:
                row[9] = "%s｜未取到网价（%s）" % (basis, (w or {}).get("备注", "检索无结果"))

    # 第三遍：仍然没价的，绝不留空——
    #   ① 能落到"工序含量库"的（窖井、井室这类土建构筑物，本来就不是商品）按含量组价；
    #   ② 其余做同类类比，但必须"同单位 + 名称有共同词"，否则宁可标 0 待询价，
    #      绝不许把一个 17 万的站套到线圈头上。
    import re as _re

    def _tokens(s):
        return set(_re.findall(r"[\u4e00-\u9fa5]{2}", str(s or "")))

    PENDING = _re.compile(r"暂无[^，。;；]{0,6}图纸|无[^，。;；]{0,6}图纸|待[^，。;；]{0,6}图纸|"
                          r"核减|取消|暂不实施|待定|暂不施工")
    priced = [r for r in out if isinstance(r[6], (int, float)) and r[6]]
    _flag_price_reuse(out)
    for row in out:
        if isinstance(row[6], (int, float)) and row[6]:
            continue
        qty = row[4] if isinstance(row[4], (int, float)) else 0
        # 清单自己写明"暂无图纸/估计核减"的，计价依据不存在：
        # 成本测算必须算全：照常按含量库组价计入成本，但在备注里醒目标"预计核减"，
        # 方便投标报价时决定是否下调（全自动口径，不再问人）
        if PENDING.search("%s %s" % (row[2] or "", row[9] or "")):
            c_cost2, c_detail2, _ = content_mod.unit_content(row[1], row[3])
            if c_cost2:
                rule2 = content_mod.find_rule(row[1]) or {}
                row[5] = "人工含量库｜工序：%s（暂估计入成本）" % rule2.get("工序", "—")
                row[6] = c_cost2
                row[7] = round(c_cost2 * qty, 2)
                row[9] = ("%s｜⚠ 清单自述「无施工图纸 / 预计核减」，成本测算仍按含量库"
                          "暂估计入，投标报价时可下调或核减；%s" % (row[9], c_detail2))
            else:
                keep9 = row[9]
                row[5] = "暂估｜清单自述待定，且无含量可算"
                row[6], row[7] = 0.0, 0.0
                row[9] = "%s｜⚠ 清单自述待定且无参照，本行暂按 0，须询价后回填" % keep9
            continue
        # 电缆类：网上没有挂牌价，但铜价公式算得准（用企业历史电缆价标定过）
        if cable.is_cable("%s %s" % (row[1], row[2])) and cable.unit_ok(row[3]):
            cop = float((cfg.get("cable") or {}).get("copper_yuan_per_kg")
                        or cable.DEFAULT_COPPER)
            cp, cnote = cable.by_formula("%s %s" % (row[1], row[2]), cop)
            if cp:
                row[5] = "电缆行情公式｜铜价 %.0f 元/kg" % cop
                row[6], row[7] = cp, round(cp * qty, 2)
                row[9] = "%s｜%s" % (row[9], cnote)
                continue
        # 钢制管材：DN/SC 规格能算每米重量，比品类区间可靠
        if pipe_mod.is_pipe("%s %s" % (row[1], row[2])) and pipe_mod.unit_ok(row[3]):
            pp, pnote = pipe_mod.by_formula("%s %s" % (row[1], row[2]))
            if pp:
                row[5] = "钢管规格公式"
                row[6], row[7] = pp, round(pp * qty, 2)
                row[9] = "%s｜%s" % (row[9], pnote)
                continue
        # 品类经验区间：比"同类类比"可靠——整包设备不会被单体件带偏
        # （比如"车道称重吊装"曾被类比成"地感线圈 36 元/套"）
        # ⚠ 整箱/整盘件不能用品类单价折算：网线的区间是"元/米"，
        # 碰到「六类网线 300米每箱」这种按"箱"计量的行，按米价折出来就是
        # 3 元一箱的鬼数。这类一律交给下面的「按计量单位保守暂估」。
        PACK_UNITS = {"箱", "盘", "卷", "包", "桶", "袋", "捆", "扎", "托"}
        if str(row[3] or "") in PACK_UNITS:
            guess, band, fnote = None, None, ""
        else:
            guess, band, fnote = webprice.band_guess(row[1], row[2], row[3])
        if band:
            row[5] = "品类经验暂估（非网价）｜合理区间 %.0f~%.0f 元/%s%s" % (
                band[0], band[1], row[3], ("，已按规格尺寸调档" if fnote else ""))
            row[6], row[7] = guess, round(guess * qty, 2)
            row[9] = ("%s｜⚠ 网价与AI估值均未取到，按「%s」品类工程经验区间 %.0f~%.0f 元/%s"
                      "取区间代表值（中值）暂估 %s 元；%s；必须询价复核"
                      % (row[9], row[1][:14], band[0], band[1], row[3], guess,
                         fnote or "规格里没有可解析的尺寸"))
            continue
        # 只有"实物构筑物"类工序才允许给设备/材料行兜底；
        # 安装类工序（敷设/组立/接线…）是人工费，不能当材料价
        c_cost, c_detail = None, ""
        if content_mod.is_built_up(row[1]):
            c_cost, c_detail, _ = content_mod.unit_content(row[1], row[3])
        if c_cost:
            row[5] = "人工含量库｜工序：%s（暂估，市场无此商品）" % (content_mod.find_rule(row[1]) or {}).get("工序", "—")
            row[6] = c_cost
            row[7] = round(c_cost * qty, 2)
            row[9] = "%s｜该条目不是商品，市场检索无意义；按工序含量组价——%s" % (row[9], c_detail)
            continue
        # 【严格铁律】不再做"同类类比"。同事技能包的血泪教训 + 你抓到的实例：
        # 类比会把「地感线圈 36 元」挂到「车道称重吊装」上、把「一条 MNS 通用报价」
        # 挂到 4 种柜子上——**宁可空缺，不可错挂**。这里只留明确标注的经验估值。
        # 最后一层：按计量单位给"保守暂估"，仍然明确标注是估值、必须询价。
        # 用户口径是不许出现 0 元；按单位给保守值总比 0 元可靠，且不构成"错挂"。
        unit = str(row[3] or "")
        floor_map = {"套": 800, "台": 800, "个": 200, "只": 200, "件": 200, "面": 3000,
                     "座": 5000, "处": 1000, "间": 20000, "项": 3000, "组": 300,
                     "根": 100, "块": 100, "m": 10, "米": 10, "km": 5000, "千米": 5000,
                     "m²": 60, "m³": 120,
                     # 整箱/整盘件：一箱网线几百米、一盘电缆上千米，按"根/米"的
                     # 量级估会小两个数量级。以前这些单位不在表里 → 直接标 0 元
                     "箱": 800, "盘": 1200, "卷": 400, "包": 200, "桶": 300,
                     "袋": 60, "捆": 200, "扎": 100, "张": 60, "片": 120,
                     "支": 80, "束": 200, "对": 100, "付": 100, "批": 5000,
                     # 服务/计费类计量单位
                     "年": 20000, "月": 3000, "次": 800, "人日": 800,
                     "工日": 400, "天": 500, "台班": 1500, "人月": 15000,
                     "台套": 1500, "套件": 1500}
        # 单位大小写要统一："M" 和 "m" 是同一个东西，以前 M 查不到就直接标 0
        guess = floor_map.get(unit) or floor_map.get(str(unit or "").strip().lower())
        if guess:
            row[5] = "保守暂估（非网价）｜按计量单位 %s 的工程最低量级取值" % unit
            row[6], row[7] = guess, round(guess * qty, 2)
            row[9] = ("%s｜⚠ 库价/网价/AI估值/品类经验值均未取到，按「%s」的工程最低量级"
                      "保守暂估 %s 元；务必询价后替换（不做同类类比，避免错挂）"
                      % (row[9], unit, guess))
        else:
            row[5] = "暂估｜无任何可参照价"
            row[6], row[7] = 0.0, 0.0
            row[9] = ("%s｜⚠ 库价/网价/AI估值/品类经验值均未取到，且单位「%s」无保守量级，"
                      "本行标 0 等人工询价" % (row[9], unit))
    return out


def _flag_price_reuse(rows):
    """同一个价（同来源+同单价）被套到 3 个以上不同名称的设备上，
    基本可以断定是"一个通用报价打天下"（比如一条 MNS 柜的挂牌价被当成
    进线柜/联络柜/馈出柜的价），标出来让人复核。"""
    from collections import defaultdict
    groups = defaultdict(set)
    for r in rows:
        if not (isinstance(r[6], (int, float)) and r[6]):
            continue
        if not str(r[5] or "").startswith(("互联网检索", "企业历史报价库")):
            continue
        # ⚠ 只按"单价"分组：以前按"单价+来源"分组，两行来源不同（一条是百度爱采购、
        # 一条是六件套回写）就漏判了，结果 1000kVA 和 2500kVA 的变压器同价。
        groups[round(float(r[6]), 2)].add(str(r[1]))
    import re as _re
    bad = set()
    for k, names in groups.items():
        names = sorted(names)
        if len(names) >= 3:
            bad.add(k)                      # 一个价打到 3 个以上不同设备
            continue
        if len(names) >= 2:
            # 两个设备：名称里的数字规格不同却同价（如 1000kVA 与 2500kVA 的变压器），
            # 说明至少有一个是套错的
            nums = [set(_re.findall(r"\d+", n)) for n in names]
            if any(nums[i] != nums[0] for i in range(1, len(nums))):
                bad.add(k)
    if not bad:
        return
    _rescale_by_capacity(rows, groups, bad)
    for r in rows:
        if not (isinstance(r[6], (int, float)) and r[6]):
            continue
        k = round(float(r[6]), 2)
        if k in bad:
            n = len(groups[k])
            r[9] = ("%s｜⚠ 同一个价被套用到 %d 个不同设备上（%s），"
                    "很可能是通用报价/挂单价，务必逐个复核" % (
                        r[9], n, "、".join(sorted(groups[k])[:4])))


KV = re.compile(r"(\d{3,6})\s*k\s*va", re.I)
KV2 = re.compile(r"\bSCB\w*[-–]\s*(\d{3,6})", re.I)      # SCB18-2000/10
KV3 = re.compile(r"(\d{3,6})\s*[）)]?\s*$")               # …/0.69kV 2000）


def _capacity_of(text):
    """从设备名里抠出容量 kVA：kVA 字样可能被截断，所以多试几种写法。"""
    t = str(text or "")
    for rx in (KV, KV2, KV3):
        m = rx.search(t)
        if m:
            v = float(m.group(1))
            if 50 <= v <= 100000:
                return v
    return None


def _rescale_by_capacity(rows, groups, bad):
    """同一价打到不同容量的变压器上：按 (容量比)^0.65 折算。

    变压器价格不随容量线性增长（400→2000kVA 线性外推会得到 38 万，实际主流 13-18 万），
    行业常用的经验指数是 0.6~0.7，这里取 0.65，并保留"暂估"标注。
    """
    idx = {}
    for r in rows:
        if not (isinstance(r[6], (int, float)) and r[6]):
            continue
        if round(float(r[6]), 2) not in bad:
            continue
        k = _capacity_of(r[1])
        if k:
            idx.setdefault(round(float(r[6]), 2), []).append((r, k))
    for price, items in idx.items():
        if len(items) < 2:
            continue
        base = min(k for _, k in items)          # 同价里容量最小的那个当基准
        for r, kva in items:
            if kva <= base:
                continue
            f = (kva / base) ** 0.65
            old = r[6]
            r[6] = round(float(old) * f, 2)
            if isinstance(r[4], (int, float)):
                r[7] = round(r[6] * r[4], 2)
            r[5] = "容量折算暂估（非网价）"
            r[9] = ("%s｜⚠ 原取价与 %gkVA 同价（通用报价），已按 (容量比)^0.65 折算："
                    "%g→%gkVA ×%.2f = %.2f 元；必须按目标容量单独询价"
                    % (r[9], base, base, kva, f, r[6]))


def price_labor(items, cfg, pure_online=False, spec=None, mult=1.0):
    """劳务/包工包料取价。

    pure_online=False：定额基价的人工费（陕西 2025 定额口径）
    pure_online=True ：人工单价改用联网查到的当地工日单价；
                       按用户口径「不压价」——网查价与定额价取高者。
    """
    qlib = load_quota()
    rate_web = None
    rate_info = None
    uplift = float(cfg.get("labor", {}).get("pure_online_uplift", 0.10)) if pure_online else 0.0
    if pure_online:
        key = webprice.read_dashscope_key()
        if key:
            rate_info = webprice.labor_day_rate(cfg.get("project_region") or "陕西",
                                                cfg, key, webprice.Cache())
            if rate_info.get("found"):
                rate_web = float(rate_info["工日单价"])
    out = []
    n = 0
    for x in items:
        qty = x["数量"] or 0
        if x["类别"] == "包工包料":
            # 含量库优先：按备注里的实际尺寸拆成土方/钢筋/模板/浇筑四道工序，
            # 清单没给尺寸时用 1100×1100×1700 默认口径；每一项都带工日含量说明。
            vol = content_mod.bulk_volume(x["项目名称"], x.get("备注", ""), x["单位"],
                                          spec=spec)
            steps, direct = [], 0.0
            for step_name, base_cost, detail, man in content_mod.steps_for_bulk(
                    x["项目名称"], x["单位"], mult):
                k = content_mod.step_scale(step_name, vol["体积"], vol["钢筋kg"])
                unit_cost = round(base_cost * k, 2)
                direct += unit_cost
                steps.append((step_name, unit_cost, detail, round(man * k, 3)))
            if not steps:      # 含量库没盖到 → 退回定额
                for st in LABOR_STEPS:
                    cands = qlib.search(st["关键词"], source_kw=st["专业"], top=3)
                    if not cands:
                        continue
                    pick = cands[0]
                    unit_cost = _step_unit_cost(pick, st, rate_web, uplift)
                    direct += unit_cost
                    steps.append((st["工序"], unit_cost,
                                  "定额 %s %s" % (pick["编号"], pick.get("项目名称")),
                                  0.0))
            measure = direct * MEASURE_RATE
            special = SPECIAL_GEOLOGY / qty if qty else 0
            for step_name, unit_cost, detail, man in steps:
                n += 1
                out.append([n, "%s — %s" % (x["项目名称"], step_name), detail,
                            x["单位"], qty,
                            "人工含量库｜工序：%s（包工包料工序分解）" % step_name,
                            round(unit_cost, 2), round(unit_cost * qty, 2), "",
                            "%s｜%s｜工程量口径：%s（%.3f m³、钢筋 %.1f kg/单位）" % (
                                x["依据/说明"], detail, vol["来源"],
                                vol["体积"], vol["钢筋kg"]), "", ""])
            extra = [("安全文明及措施费", measure, "按直接费 5% 计取")]
            if special:
                extra.append(("特殊地质基础开挖", special, "按项目给定金额平摊"))
            for label, cost, note in extra:
                n += 1
                out.append([n, "%s — %s" % (x["项目名称"], label), note, x["单位"], qty,
                            "取费口径｜按包工包料工序直接费的 5% 计提措施费",
                            round(cost, 2), round(cost * qty, 2), "",
                            "%s｜%s" % (x["依据/说明"], note), "", ""])
        elif x["类别"] == "劳务施工":
            n += 1
            # 电缆敷设：按被敷设电缆的截面联动——3×4 和 3×240 的活儿差好几倍，
            # 不能一个价打天下
            if "敷设" in x["项目名称"] and cable.is_cable("%s %s" % (x["项目名称"], x["备注"])):
                cop = float((cfg.get("cable") or {}).get("copper_yuan_per_kg")
                            or cable.DEFAULT_COPPER)
                mat, _ = cable.by_formula("%s %s" % (x["项目名称"], x["备注"]), cop)
                if mat:
                    lay = round(max(6.0, min(80.0, mat * 0.10)), 2)
                    out.append([n, x["项目名称"], x["备注"][:40], x["单位"], qty,
                                "人工含量库｜电缆敷设（按截面联动，材料价 %s 元/m 的 10%%）" % mat,
                                lay, round(lay * qty, 2), "",
                                "%s｜敷设人工按电缆截面联动：材料价 %s 元/m × 10%%，"
                                "下限 6 元/m、上限 80 元/m" % (x["依据/说明"], mat), "", ""])
                    continue
            c_cost, c_detail, c_man = content_mod.unit_content(x["项目名称"], x["单位"], mult)
            pick = pick_quota(qlib, x["项目名称"], x["单位"])
            q_cost = 0.0
            if pick:
                q_cost = _step_unit_cost(pick, {"取费": ["人工费", "机械费"],
                                                "定额单位": 1.0, "含量": 1.0},
                                         rate_web, uplift)
            if c_cost:
                # 含量库优先：每一项都能说清"用了多少工日、什么工种"，可复算可复核。
                # 定额若也命中，就在备注里带上定额号做交叉校核，最终取两者中的合理者（不压价）。
                rule = content_mod.find_rule(x["项目名称"]) or {}
                src = "人工含量库｜工序：%s（工日含量×工日单价）" % rule.get("工序", "—")
                unit_cost, detail = c_cost, c_detail
                if q_cost and q_cost > c_cost:
                    detail += "｜定额校核：%s %s（人工费+机械费 %.2f 元，本行仍按含量库计取）" % (
                        pick["编号"], pick["项目名称"], q_cost)
            elif q_cost:
                src = "企业定额库｜%s %s %s" % (pick["专业"], pick["编号"],
                                              pick.get("项目名称") or "")
                if rate_web:
                    src += "＋网查人工单价"
                unit_cost, detail = q_cost, "定额 %s %s" % (pick["编号"], pick["项目名称"])
            else:
                out.append([n, x["项目名称"], x["备注"][:40], x["单位"], qty,
                            "待互联网检索", 0.0, 0.0, "",
                            "%s｜定额与含量库均未命中，待按同类项类比估价" % x["依据/说明"],
                            "", ""])
                continue
            out.append([n, x["项目名称"], x["备注"][:40], x["单位"], qty, src,
                        round(unit_cost, 2), round(unit_cost * qty, 2), "",
                        "%s｜%s" % (x["依据/说明"], detail), "", ""])
        else:
            n += 1
            out.append([n, x["项目名称"], x["备注"][:40], x["单位"], qty,
                        "取费口径｜按费率计取（不重复计入总额）", 0.0, 0.0, "",
                        x["依据/说明"], "", ""])

    # 兜底：仍然 0 元的劳务行，也绝不留空——
    #   ① 先按名称里的工序关键词找含量库（"XX设备安装"这类没有专有工序的走②）
    #   ② 按同类项（名称有共同前缀/关键词）类比单价
    priced = [r for r in out if isinstance(r[6], (int, float)) and r[6]]
    import re as _re
    for row in out:
        if isinstance(row[6], (int, float)) and row[6]:
            continue
        # 只兜"真的没取到价的清单项"；措施费/特殊地质/按费率计取 这类派生行
        # 本来就是 0（在各表里另有取费口径），不能瞎填一个数
        if row[5] != "待互联网检索":
            continue
        qty = row[4] if isinstance(row[4], (int, float)) else 0
        c_cost, c_detail, _ = content_mod.unit_content(row[1], row[3], mult)
        if not c_cost:
            # 设备安装类：按"设备安装"通用含量兜底（就位、固定、接线、单机调试）
            for kw in ("安装", "调试", "试验", "敷设", "组立", "吊装"):
                if kw in str(row[1]):
                    trades = {"电工": 0.15, "小工": 0.20}
                    c_cost = round(sum(content_mod.wage_of(t) * h * mult
                                       for t, h in trades.items()) + 20, 2)
                    c_detail = ("通用设备安装含量（暂估）：电工 0.150 工日 + 小工 0.200 工日 "
                                "+ 机械 20 元")
                    break
        # 【严格铁律】劳务侧也不做同类类比（工日含量差一个档，价就差一倍）
        if c_cost:
            row[5] = "人工含量库｜%s" % str(c_detail)[:60]
            row[6] = round(c_cost, 2)
            row[7] = round(c_cost * qty, 2)
            row[9] = "%s｜%s" % (row[9], c_detail)
        else:
            # 劳务侧最后一层：按计量单位给保守暂估，不留 0 元
            uw = str(row[3] or "")
            lf = {"套": 400, "台": 400, "个": 150, "只": 150, "面": 800, "座": 800,
                  "处": 300, "间": 3000, "项": 1000, "组": 200, "根": 60, "块": 80,
                  "m": 15, "米": 15, "km": 3000, "千米": 3000, "m²": 40, "m³": 80}
            g = lf.get(uw)
            if g:
                row[5] = "保守暂估（非网价）｜按计量单位 %s 的工程最低量级取值" % uw
                row[6], row[7] = g, round(g * qty, 2)
                row[9] = ("%s｜⚠ 含量库没有对应工序，按「%s」的工程最低量级保守暂估 %s 元，"
                          "务必按实组价" % (row[9], uw, g))
            else:
                row[5] = "暂估｜无含量可算"
                row[6], row[7] = 0.0, 0.0
            row[9] = "%s｜无任何可参照价，暂按 0 列入，须询价后回填" % row[9]
    return out


def run(cfg, in_path, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    title, items = boq_mod.parse(in_path)
    if not items:
        raise SystemExit("没解析出明细，请检查清单表头")
    kept, dropped, equip, labor = est.split_items(items)

    print("  取价中：① 库+网 ……")
    cost_rows = price_equipment(equip, cfg)
    print("  取价中：② 纯网 ……")
    cost_rows_net = price_equipment(equip, cfg, pure_online=True)
    labor_rows = price_labor(labor, cfg)

    # 管理费：按（设备材料 + 劳务）直接费计取，费率可配
    direct = sum(r[7] for r in cost_rows if isinstance(r[7], (int, float))) + \
             sum(r[7] for r in labor_rows if isinstance(r[7], (int, float)))
    fee_rate = cfg.get("fees", {}).get("management", 0.05)
    for r in labor_rows:
        if r[5] == "按费率计取":
            fee = round(direct * fee_rate, 2)
            r[6], r[7] = fee, fee
            r[9] = "%s｜按直接费 %.2f 元 × %.0f%% 计取（费率可配）" % (r[9], direct, fee_rate * 100)

    # ④ 纯网版：人工单价改用联网查到的当地工日单价（查不到就回落定额口径）
    print("  取价中：④ 劳务纯网（联网查人工工日单价）……")
    labor_rows_net = price_labor(labor, cfg, pure_online=True)
    rate_note = ""
    key2 = webprice.read_dashscope_key()
    if key2:
        info = webprice.labor_day_rate(cfg.get("project_region") or "陕西", cfg, key2,
                                       webprice.Cache())
        if info.get("found"):
            rate_note = "｜人工工日单价来源：%s %s 元/工日（%s）" % (
                info.get("来源") or "联网检索", info.get("工日单价"),
                info.get("依据") or info.get("年度") or "")
    if rate_note:
        for r in labor_rows_net:
            if r[6] not in ("", None):
                r[9] = str(r[9]) + rate_note

    # ④ 的管理费：按（② 设备材料 + ④ 劳务）直接费计取
    direct_net = sum(r[7] for r in cost_rows_net if isinstance(r[7], (int, float))) + \
                 sum(r[7] for r in labor_rows_net if isinstance(r[7], (int, float)))
    for r in labor_rows_net:
        if r[5] == "按费率计取":
            fee = round(direct_net * fee_rate, 2)
            r[6], r[7] = fee, fee
            r[9] = "%s｜按直接费 %.2f 元 × %.0f%% 计取（费率可配）" % (r[9], direct_net,
                                                              fee_rate * 100)

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    yellow = PatternFill("solid", fgColor="FFF2CC")
    grey = PatternFill("solid", fgColor="F2F2F2")

    def add_sheet(name, subtitle, rows, note=None):
        ws = wb.create_sheet(name)
        ws["A1"] = title or "工程量清单"
        ws["A1"].font = Font(name="Microsoft YaHei", size=13, bold=True, color="1F3864")
        ws["A2"] = subtitle
        ws["A2"].font = Font(name="Microsoft YaHei", size=9, italic=True, color="595959")
        ws["A3"] = note or ("已剔除甲供 %d 项（设备类甲供不计入报价）；『备注』与『审核』列留空供人工填写。"
                            % len(dropped))
        ws["A3"].font = Font(name="Microsoft YaHei", size=9, italic=True, color="C00000")
        hr = 5
        for i, h in enumerate(OUT_HEADS, 1):
            c = ws.cell(row=hr, column=i, value=h)
            c.font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = border
        for k, row in enumerate(rows):
            r = hr + 1 + k
            for i, v in enumerate(row, 1):
                c = ws.cell(row=r, column=i, value=v)
                c.font = Font(name="Microsoft YaHei", size=10)
                c.alignment = Alignment(vertical="center", wrap_text=(i in (2, 3, 9, 10)))
                c.border = border
                if i in (7, 8, 11, 12):
                    c.fill = yellow
                if row[5] == "甲供不计":
                    c.fill = grey
        for i, w in enumerate([6, 40, 34, 7, 9, 26, 12, 13, 30, 46, 20, 12], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A%d" % (hr + 1)
        ws.row_dimensions[hr].height = 26
        dv = DataValidation(type="list", formula1='"待审核,已审核,需复核"', allow_blank=True)
        ws.add_data_validation(dv)
        if rows:
            dv.add("L%d:L%d" % (hr + 1, hr + len(rows)))
        return ws

    add_sheet("① 成本测算(库+网)", "设备/材料：价格库 → 历史报价库 → 未命中待联网", cost_rows)
    add_sheet("② 成本测算(纯网)",
              "设备/材料：全部走互联网检索价；含税 ÷1.13 → 不含税 → 按品类与采购量折算成工程价",
              cost_rows_net)
    add_sheet("③ 劳务报价(库+网)", "劳务/包工包料：按定额组价（人工费＋机械费＋辅材），含措施与特殊地质", labor_rows)
    add_sheet("④ 劳务报价(纯网)",
              "劳务：人工单价取『网查当地工日单价（如陕建发〔2021〕1097号 136 元/工日）"
              "与定额口径的高者』，再按配置上浮（不压价）；含量取自定额",
              labor_rows_net)

    ws5 = wb.create_sheet("甲供剔除明细")
    ws5["A1"] = "本次剔除的甲供项"
    ws5["A1"].font = Font(name="Microsoft YaHei", size=12, bold=True, color="1F3864")
    for i, h in enumerate(["序号", "项目名称", "单位", "数量", "备注"], 1):
        c = ws5.cell(row=3, column=i, value=h)
        c.font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
    for k, x in enumerate(dropped):
        for i, v in enumerate([x["序号"], x["项目名称"], x["单位"], x["数量"], x["备注"]], 1):
            ws5.cell(row=4 + k, column=i, value=v).font = Font(name="Microsoft YaHei", size=10)
    for i, w in enumerate([7, 42, 8, 10, 60], 1):
        ws5.column_dimensions[get_column_letter(i)].width = w

    wb.save(out_path)
    total_cost = sum(r[7] for r in cost_rows if isinstance(r[7], (int, float)))
    total_labor = sum(r[7] for r in labor_rows if isinstance(r[7], (int, float)))
    miss = sum(1 for r in cost_rows if r[5] == "待互联网检索")
    print("清单：%s" % (title or in_path))
    print("  明细 %d 项 → 需报价 %d，甲供剔除 %d" % (len(items), len(kept), len(dropped)))
    print("  ① 成本测算(库+网)  %2d 行，已取价 %d，待联网 %d，合计 %.2f 元"
          % (len(cost_rows), len(cost_rows) - miss, miss, total_cost))
    miss_net = sum(1 for r in cost_rows_net if r[5] == "待互联网检索")
    print("  ② 成本测算(纯网)   %2d 行，已取价 %d，未取到 %d" % (
        len(cost_rows_net), len(cost_rows_net) - miss_net, miss_net))
    print("  ③ 劳务报价(库+网)  %2d 行，定额组价合计 %.2f 元" % (len(labor_rows), total_labor))
    miss_labor_net = sum(1 for r in labor_rows_net if r[5].startswith("待互联网检索"))
    print("  ④ 劳务报价(纯网)   %2d 行，已取价 %d，未取到 %d" % (
        len(labor_rows_net), len(labor_rows_net) - miss_labor_net, miss_labor_net))
    print("→", out_path)
    return {"title": title, "cost_rows": cost_rows, "labor_rows": labor_rows,
            "cost_rows_net": cost_rows_net, "labor_rows_net": labor_rows_net,
            "dropped": dropped, "total_cost": total_cost, "total_labor": total_labor}
