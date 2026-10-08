# -*- coding: utf-8 -*-
"""背景与方案分析 → 项目理解卡（分析项 · 结论 · 对测算的影响 · 原文出处）。

规则做定位（可追溯到具体句子），模型只做归纳；每条必须带原文片段，
没有依据的项明确标「未见依据」，避免凭空理解。
"""
import re

# (分析项, 强关键词, 弱关键词, 对测算的影响)
ITEMS = [
    ("范围与规模",
     ["座", "套", "处", "台", "盏", "公里", "km", "标段", "新建", "改建", "规模"],
     ["工程量", "数量", "共计", "合计"],
     "决定工程量口径与作业面数量"),
    ("甲供范围",
     ["甲供", "甲方提供", "发包人提供", "甲方供货"],
     ["材料", "设备"],
     "材料不计价、安装人工照计；卸车保管与损耗责任写进报价说明"),
    ("甲方不提供",
     ["甲方不提供", "甲方不负责", "乙方自购", "承包方采购", "我方采购", "自行采购"],
     [],
     "转我方采购：材料款单列（采购管理费+税金），不进降效/风险取费基数"),
    ("施工条件",
     ["边通车", "占道", "导改", "导流", "夜间施工", "隧道内", "井下", "高空作业",
      "带电", "不停机", "高原", "雨季", "冬季施工", "交叉施工", "保通"],
     ["通车", "夜间", "隧道", "高空", "交通"],
     "影响人工效率与措施费：有据才加，小幅上调并注明出处"),
    ("工期节点",
     ["工期", "开工", "完工", "竣工", "日历天", "节点"],
     ["个月"],
     "反推作业队数量与资源配置；工期紧需预备窝工与加队成本"),
    ("质量与验收",
     ["验收", "隐蔽", "监理", "试运行", "检测"],
     ["质量目标"],
     "决定检测费、试运行费与资料费，需在措施与管理费中体现"),
    ("风险与调差",
     ["调差", "信息价", "波动", "损耗", "质保", "保证金", "计量", "支付"],
     ["违约"],
     "决定报价说明中的调差、损耗、支付与质保条款"),
    ("品牌与档次",
     ["品牌", "甲指", "指定", "国产", "进口"],
     ["档次", "同等"],
     "影响设备与材料单价取值区间"),
    ("现场条件",
     ["驻地", "临时设施", "围挡", "占地", "运距"],
     ["运输", "库房"],
     "影响临时设施、运输与措施费"),
]

# 明显是"编制依据/文件清单"的句子要降权
REF_PENALTY = re.compile(r"《|》|\.pdf|\.docx|\.xlsx|^\(?\d+\)|指导意见|管理办法|可研报告")


def _sentences(text):
    out = []
    for pi, para in enumerate(re.split(r"[\n\r]+", text or "")):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        for s in re.split(r"(?<=[。；;！!？?])", para):
            s = s.strip()
            if len(s) >= 6:
                out.append((pi + 1, s))
    return out


def _score(sent, strong, weak):
    sc = 0
    for k in strong:
        if k in sent:
            sc += 3
    for k in weak:
        if k in sent:
            sc += 1
    if REF_PENALTY.search(sent):
        sc -= 6
    if len(sent) < 12:
        sc -= 2
    return sc


def analyze(text, max_sent=3):
    sents = _sentences(text)
    cards = []
    for name, strong, weak, impact in ITEMS:
        # 硬约束：必须命中至少一个"强关键词"，弱关键词只能加分不能独立成立
        scored = [(name, _score(s, strong, weak), pi, s) for pi, s in sents
                  if any(k in s for k in strong)]
        hits = [(sc, pi, s) for _, sc, pi, s in scored if sc > 0]
        hits.sort(key=lambda x: -x[0])
        if not hits:
            cards.append({"分析项": name, "结论": "未见依据", "对测算的影响": impact,
                          "原文出处": [], "状态": "缺"})
            continue
        picks = hits[:max_sent]
        cards.append({
            "分析项": name,
            "结论": picks[0][2][:120],
            "对测算的影响": impact,
            "原文出处": ["第%d段：%s" % (pi, s[:160]) for _, pi, s in picks],
            "状态": "已识别",
        })
    return cards


def to_markdown(cards, title="项目理解卡"):
    lines = ["## %s" % title, "",
             "| 分析项 | 结论（依据原文） | 对测算的影响 | 原文出处 |",
             "|---|---|---|---|"]
    for c in cards:
        ev = c["原文出处"][0] if c["原文出处"] else "—"
        mark = "" if c["状态"] == "已识别" else "（未见依据）"
        lines.append("| %s | %s%s | %s | %s |" % (
            c["分析项"], c["结论"][:60], mark, c["对测算的影响"], ev[:70]))
    missing = [c["分析项"] for c in cards if c["状态"] == "缺"]
    lines += ["", ("**需人工确认**：未找到依据的项：%s，请补充或在备注里说明按常规处理。"
                   % "、".join(missing)) if missing
              else "**需人工确认**：各项均已找到依据，请核对结论是否准确。"]
    return "\n".join(lines)
