# -*- coding: utf-8 -*-
"""定额库：把『消耗量定额 + 基价表』用于劳务与包工包料项的组价。

内部成本 = 人工费 + 辅材费（材料费扣除未计价主材） + 机械费
对外计价 = 基价（定额已含管理费与利润）
"""
import json
import os
import re


def _norm(s):
    return re.sub(r"[\s\u3000]+", "", str(s or ""))


def _major(text):
    """从来源/册别里判专业：市政 / 通用安装 / 房建 / 园林 / 管廊 / 绿色 / 其他。"""
    t = str(text or "")
    for key, name in (("市政", "市政"), ("通用安装", "通用安装"), ("房屋建筑", "房建"),
                      ("房建", "房建"), ("园林", "园林"), ("管廊", "管廊"), ("绿色", "绿色")):
        if key in t:
            return name
    return "其他"


class QuotaLibrary:
    @classmethod
    def from_db(cls, db_path):
        """从 SQLite 知识库读（比 60MB JSON 省内存，适合内存紧张的容器）。"""
        import sqlite3
        self = cls.__new__(cls)
        self.items, self.cons_items = [], []
        self._basis_idx, self._cons_idx, self._gram_idx = {}, {}, {}
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        for r in con.execute("""SELECT code, major, chapter, name, unit, base_price,
                                       labor_fee, material_fee, machine_fee, overhead,
                                       profit, source FROM quota_basis"""):
            self.items.append({
                "编号": _norm(r["code"]),
                "专业": r["major"] or _major(r["source"]),   # 库里没写专业就从来源文件名推
                "章节": r["chapter"], "项目名称": r["name"], "单位": r["unit"],
                "基价": r["base_price"], "人工费": r["labor_fee"],
                "材料费": r["material_fee"], "机械费": r["machine_fee"],
                "管理费": r["overhead"], "利润": r["profit"], "来源": r["source"]})
        for r in con.execute("""SELECT code, major, chapter, name, unit, work_content,
                                       labor_hours, machine_shift FROM quota_cons"""):
            rec = {"编号": _norm(r["code"]), "专业": r["major"] or "其他",
                   "章节": r["chapter"], "项目名称": r["name"], "单位": r["unit"],
                   "工作内容": r["work_content"], "人工工日": r["labor_hours"],
                   "机械台班": r["machine_shift"], "人工": [], "材料": [], "机械": []}
            self.cons_items.append(rec)
        con.close()
        for r in self.items:
            self._basis_idx.setdefault((r["专业"], r["编号"]), r)
        for r in self.cons_items:
            self._cons_idx.setdefault((r["专业"], r["编号"]), r)
        return self

    def __init__(self, basis_path, consumption_path):
        self.items = []            # 全部基价子目（同一个编号在不同专业里是不同子目）
        self.cons_items = []
        self._basis_idx = {}
        self._cons_idx = {}
        self._gram_idx = {}        # 2 字倒排索引：(专业,编号) → 文本，用于加速关键词检索
        if os.path.exists(basis_path):
            for r in json.load(open(basis_path, encoding="utf-8")):
                r["专业"] = _major(r.get("来源"))
                r["编号"] = _norm(r["编号"])
                self.items.append(r)
                self._basis_idx.setdefault((r["专业"], r["编号"]), r)
        if os.path.exists(consumption_path):
            for r in json.load(open(consumption_path, encoding="utf-8")):
                r["专业"] = _major(r.get("册别") or r.get("来源"))
                r["编号"] = _norm(r["编号"])
                self.cons_items.append(r)
                self._cons_idx.setdefault((r["专业"], r["编号"]), r)

    def price(self, code, major=None):
        code = _norm(code)
        if major:
            hit = self._basis_idx.get((major, code))
            if hit:
                return hit
        for (mj, cd), rec in self._basis_idx.items():
            if cd == code:
                return rec
        return None

    def consumption(self, code, major=None):
        code = _norm(code)
        if major:
            hit = self._cons_idx.get((major, code))
            if hit:
                return hit
        for (mj, cd), rec in self._cons_idx.items():
            if cd == code:
                return rec
        return None

    def main_materials(self, code):
        """未计价主材（定额里带括号的量）——组价时要单独按采购价计。"""
        c = self.consumption(code)
        if not c:
            return []
        return [m for m in c.get("材料", []) if m.get("未计价")]

    def aux_material_cost(self, code):
        """辅材费 = 基价里的材料费（定额材料费本身不含未计价主材）。"""
        b = self.price(code)
        return float(b.get("材料费") or 0) if b else 0.0

    def search(self, keywords, unit=None, top=5, books=None, code_prefix=None, source_kw=None):
        """按关键词在章节与子目名称里检索，返回带评分与理由的候选。

        books:       来源文件关键词（如 "市政"）
        code_prefix: 定额编号前缀（如 "8-" 表示该专业第八册）
        """
        # 先用 2 字倒排索引把候选压到几百条，再精确打分（全量 2.9 万条时提速 10 倍以上）
        if not self._gram_idx:
            for i, b in enumerate(self.items):
                text = _norm(b.get("章节")) + _norm(b.get("项目名称"))
                for g in {text[j:j + 2] for j in range(len(text) - 1)}:
                    self._gram_idx.setdefault(g, []).append(i)
        kws = [_norm(k) for k in keywords if k]
        cand_idx = None
        for k in kws:
            grams = {k[j:j + 2] for j in range(max(1, len(k) - 1))}
            hit = set()
            for g in grams:
                hit.update(self._gram_idx.get(g, ()))
            cand_idx = hit if cand_idx is None else (cand_idx & hit)
        items = ([self.items[i] for i in sorted(cand_idx)] if cand_idx is not None
                 else self.items)
        out = []
        for b in items:
            code = b["编号"]
            if code_prefix and not code.startswith(code_prefix):
                continue
            if source_kw and source_kw not in (b.get("来源") or ""):
                continue
            c = self.consumption(code, b.get("专业")) or {}
            text = _norm(b.get("章节")) + " " + _norm(b.get("项目名称"))
            if books and not any(bk in (b.get("来源") or "") for bk in books):
                continue
            hits = [k for k in kws if k in text]
            if not hits:
                continue
            score = len(hits) / max(1, len(kws))
            reasons = ["命中：" + "、".join(hits)]
            # 子目名称以关键词开头的，更可能是主子目（如『带肋钢筋直径(mm)18』比『钢筋笼 带肋钢筋』更贴）
            if kws and _norm(b.get("项目名称")).startswith(kws[0]):
                score += 0.2
                reasons.append("名称以关键词开头")
            bunit = _norm(b.get("单位"))
            if unit and bunit:
                if _norm(unit) == bunit:
                    score += 0.25
                    reasons.append("单位一致（%s）" % bunit)
                else:
                    score -= 0.15
                    reasons.append("单位不同（清单 %s / 定额 %s）" % (unit, bunit))
            if b.get("人工费"):
                reasons.append("含人工费 %.2f 元/%s" % (b["人工费"], bunit or "单位"))
            if c.get("人工工日"):
                reasons.append("人工含量 %.3f 工日" % c["人工工日"])
            out.append({
                "编号": code,
                "专业": b.get("专业"),
                "章节": b.get("章节"),
                "项目名称": b.get("项目名称"),
                "单位": b.get("单位"),
                "基价": b.get("基价"),
                "人工费": b.get("人工费"),
                "材料费": b.get("材料费"),
                "机械费": b.get("机械费"),
                "管理费": b.get("管理费"),
                "利润": b.get("利润"),
                "人工工日": (c or {}).get("人工工日"),
                "score": round(score, 3),
                "理由": "；".join(reasons),
            })
        out.sort(key=lambda x: (-x["score"], x["编号"]))
        return out[:top]


def labor_cost(lib, code, qty, cfg, region=None, conditions=None, major=None):
    """把一个定额子目折算成劳务报价（内部成本 + 对外计价）。"""
    b = lib.price(code, major)
    if not b:
        return None
    labor_cfg = cfg.get("labor", {})
    rf = labor_cfg.get("region_factor", {}).get(region,
          labor_cfg.get("default_region_factor", 1.0)) if region else 1.0
    cf = 1.0
    for c in (conditions or []):
        cf *= labor_cfg.get("condition_factor", {}).get(c, 1.0)

    labor_fee = float(b.get("人工费") or 0)
    mech_fee = float(b.get("机械费") or 0)
    aux_fee = float(b.get("材料费") or 0)
    overhead = float(b.get("管理费") or 0) + float(b.get("利润") or 0)

    internal = (labor_fee + mech_fee + aux_fee) * rf * cf
    quote = (labor_fee + mech_fee + aux_fee + overhead) * rf * cf
    qty = float(qty or 0)
    return {
        "编号": code,
        "项目名称": b.get("项目名称"),
        "单位": b.get("单位"),
        "数量": qty,
        "人工费": labor_fee,
        "机械费": mech_fee,
        "辅材费": aux_fee,
        "管理费利润": overhead,
        "地区系数": rf,
        "条件系数": round(cf, 3),
        "内部成本单价": round(internal, 2),
        "对外计价单价": round(quote, 2),
        "内部成本合计": round(internal * qty, 2),
        "对外计价合计": round(quote * qty, 2),
    }
