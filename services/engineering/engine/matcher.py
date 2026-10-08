# -*- coding: utf-8 -*-
"""三级匹配：精确 → 强匹配 → 相似打分。"""
from engine.textutil import (clean_name, jaccard, normalize, params_of,
                             similarity)


class MatchResult(object):
    __slots__ = ("material", "score", "level", "reasons")

    def __init__(self, material, score, level, reasons):
        self.material = material
        self.score = score
        self.level = level
        self.reasons = reasons


def _unit_ok(a, b):
    a, b = normalize(a), normalize(b)
    return (not a or not b or a == b)


class Matcher(object):
    def __init__(self, materials, cfg):
        self.cfg = cfg
        self.w = cfg["weights"]
        self.items = []
        for m in materials:
            self.items.append((
                m,
                normalize(clean_name(m.name)),
                params_of(m.name, m.spec + " " + m.key_params),
                normalize(m.model),
            ))

    def match(self, name, spec="", unit="", top_n=None):
        top_n = top_n or self.cfg["top_n"]
        qn = normalize(clean_name(name))
        qp = params_of(name, spec)
        results = []
        for m, mn, mp, mm in self.items:
            if not _unit_ok(unit, m.unit):
                continue
            name_sim = similarity(qn, mn)
            param_j = jaccard(qp, mp)
            model_hit = 1.0 if (mm and mm in normalize(spec)) else (
                1.0 if (mm and mm in qn) else 0.0)
            unit_hit = 1.0 if _unit_ok(unit, m.unit) else 0.0
            # 该物料没有型号时，把型号权重按比例摊给其余项，避免满分只有 0.8
            parts = {"name": name_sim, "param": param_j, "unit": unit_hit}
            weights = {"name": self.w["name"], "param": self.w["param"],
                       "unit": self.w["unit"]}
            if mm:
                parts["model"] = model_hit
                weights["model"] = self.w["model"]
            total_w = sum(weights.values())
            score = sum(weights[k] * parts[k] for k in weights) / total_w
            if m.spec_status.startswith("规格未定"):
                score -= self.cfg["spec_undetermined_penalty"]
            if score <= 0:
                continue
            reasons = []
            if name_sim >= 0.6:
                reasons.append("名称接近")
            if param_j > 0:
                hit = sorted(qp & mp)[:4]
                reasons.append("参数命中 %s" % "、".join(hit))
            if model_hit:
                reasons.append("型号一致(%s)" % m.model)
            if m.spec_status.startswith("规格未定"):
                reasons.append("该物料规格未定")
            results.append(MatchResult(m, score, "", "; ".join(reasons) or "弱相关"))

        results.sort(key=lambda r: -r.score)
        out = results[:top_n]
        for r in out:
            if r.score >= self.cfg["auto_accept"]:
                r.level = "自动采纳"
            elif r.score >= self.cfg["candidate_floor"]:
                r.level = "候选待确认"
            else:
                r.level = "未匹配"
        return out
