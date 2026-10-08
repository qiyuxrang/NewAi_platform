# -*- coding: utf-8 -*-
"""供应归属四路判定：A 甲供（材料） / B 我方采购 / C 我方辅材 / D 劳务自备 / E 存疑。

规则读 config/ownership_rules.json（业务人员可自行改词），按数组顺序优先命中；
每一项都返回命中依据，便于复核；判不了的进追问清单。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, "config", "ownership_rules.json")


def load_rules():
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _has(text, kw):
    return kw in text


def classify(name, note="", unit="", qty=None, category="", rules=None):
    """返回 {归属, 依据, 材料计入, 劳务计入, 取费}。"""
    r = rules or load_rules()
    text = "%s %s" % (name or "", note or "")
    # 存疑：名称过短 / 没有单位 / 数量为 0
    if len(re.sub(r"\s+", "", str(name or ""))) < 3:
        return {"归属": "E 存疑", "依据": "名称过短（少于 3 字），无法判断归属",
                "材料计入": None, "劳务计入": None,
                "取费": r["存疑"]["处理"]}
    # 包工包料优先：备注里可能提到"钢筋/混凝土甲供"，但这一项本身要报价
    if "包工包料" in text:
        return {"归属": "B 我方采购 + 包工包料施工",
                "依据": "备注含「包工包料」：材料中标注甲供的部分不计，其余材料与施工照计",
                "材料计入": True, "劳务计入": True,
                "取费": "施工走劳务取费线；甲供材料不计价，只计施工"}
    for rule in r["rules"]:
        for kw in rule["关键词"]:
            if _has(text, kw):
                return {"归属": rule["归属"], "依据": "命中关键词「%s」" % kw,
                        "材料计入": rule["材料计入"], "劳务计入": rule["劳务计入"],
                        "取费": rule["取费"]}
    d = r["默认"]
    why = "备注未标甲供/不提供，也非辅材或劳保 → 按我方采购处理"
    if not unit:
        why += "；注意：该行未填单位"
    return {"归属": d["归属"], "依据": why, "材料计入": d["材料计入"],
            "劳务计入": d["劳务计入"], "取费": d["取费"]}


def classify_items(items, rules=None):
    """批量判定，返回 (带归属的行, 追问清单)。"""
    r = rules or load_rules()
    tagged, ask = [], []
    for x in items:
        c = classify(x.get("项目名称", ""), x.get("备注", ""), x.get("单位", ""),
                     x.get("数量"), x.get("类别", ""), r)
        x = dict(x)
        x["供应归属"] = c["归属"]
        x["归属依据"] = c["依据"]
        x["材料计入"] = c["材料计入"]
        x["劳务计入"] = c["劳务计入"]
        tagged.append(x)
        if c["归属"].startswith("E"):
            ask.append({"项目名称": x.get("项目名称"), "单位": x.get("单位"),
                        "数量": x.get("数量"), "原因": c["依据"]})
    return tagged, ask


def summarize(tagged):
    from collections import Counter
    c = Counter(x["供应归属"] for x in tagged)
    return dict(c)
