# -*- coding: utf-8 -*-
"""四件套交付：一个 Excel、四个 Sheet（设备清单 / 劳务清单 / 成本测算表 / 对外报价清单）。

链路：清单 → 供应归属判定 → 取价 → 环境与条件修正 → 四件套装配 → 通用校验 → 导出到桌面。
口径、依据、风险与报价说明全部写进表内备注列，不再单独出报告文件。

用法：
    from engine import foursheet
    r = foursheet.run("清单.xlsx", over={"地区": "陕西", "C30方量": 5101},
                      bg_text="本项目边通车施工……")
"""
import os
import shutil

from engine import (assemble, checkup, content as content_mod, health, ownership,
                    project_quote)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT_DIR = os.environ.get("EXPORT_DIR") or os.path.join(ROOT, "data", "export")
HOST_EXPORT_DIR = os.environ.get("HOST_EXPORT_DIR") or EXPORT_DIR

# ── 环境与条件修正：单项 ≤1.15、累计 ≤1.08，对总额影响控制在 5% 以内 ──
ENV_SINGLE_CAP = 0.15
ENV_TOTAL_CAP = 0.08
ENV_RULES = [
    # 注意：边通车/占道/导改/保通 已在取费链的「人工降效 6%」里体现，这里不重复计取，
    # 只对"超出常规工地"的额外条件做小幅上调（有据才加，累计 ≤8%）。
    ("夜间施工", 0.04), ("隧道内", 0.05), ("隧道", 0.03), ("井下", 0.06),
    ("高空作业", 0.03), ("带电", 0.03), ("不停机", 0.04), ("高原", 0.05),
    ("雨季", 0.03), ("冬季施工", 0.04), ("交叉施工", 0.02), ("抢工", 0.05),
    ("有限空间", 0.05), ("深基坑", 0.03),
    # 陕北/陕西项目常见的地基与气候条件（用户 2026-09-24 确认加入）
    ("冻土", 0.04), ("冻深", 0.04), ("冻胀", 0.04),
    ("湿陷性黄土", 0.04), ("黄土湿陷", 0.04), ("湿陷", 0.04),
    ("黄土", 0.04),
]

# 这些条件只在"背景/技术方案里明确写了"时才加，属于有据才加、小幅上调
ENV_HINT = {"夜间施工": "夜间作业降效并需照明与警示设施",
            "隧道内": "隧道内作业照明、通风与限时施工影响效率",
            "井下": "井下作业条件受限、安全监护加人",
            "高空作业": "高空作业需专项安全措施、效率下降",
            "高原": "高原环境人工与机械效率下降",
    "冬季施工": "冬季施工需保温养护、效率下降",
    "冻土": "冻土/冻深条件下开挖与基础施工需破除冻层、控制冻胀，效率下降",
    "冻深": "冻深范围内需超挖换填并做防冻胀处理，效率下降",
    "冻胀": "基础需做防冻胀处理（换填/加深），效率下降",
    "湿陷性黄土": "湿陷性黄土地基需处理（换填/夯实/防水），开挖与回填效率下降",
    "黄土湿陷": "湿陷性黄土地基需处理（换填/夯实/防水），开挖与回填效率下降",
    "湿陷": "湿陷性黄土地基需处理（换填/夯实/防水），开挖与回填效率下降",
    "黄土": "黄土地基（可塑/湿陷）需处理，开挖与回填效率下降",
            "雨季": "雨季施工需排水与抢晴，效率下降",
            "抢工": "工期紧张需增配作业队与夜间班次"}


def env_adjust(text):
    """按背景/技术方案里的施工条件算环境系数，返回 (系数, 命中项列表)。"""
    t = text or ""
    hits, seen = [], set()
    for kw, up in ENV_RULES:
        if kw in t and kw not in seen:
            seen.add(kw)
            hits.append({"条件": kw, "上调": min(up, ENV_SINGLE_CAP),
                         "影响": ENV_HINT.get(kw, "作业条件受限")})
    # 同一条只算一次：命中"湿陷性黄土"就不再单独加"黄土"，命中"隧道内"就不再加"隧道"
    hits = [h for h in hits
            if not any(h["条件"] != o["条件"] and h["条件"] in o["条件"] for o in hits)]
    total = min(sum(h["上调"] for h in hits), ENV_TOTAL_CAP)
    return round(total, 4), hits


def build_notes(p, summary, env_hits, env_rate, ask, chain_a, chain_b):
    """报价说明：全部写进表内备注，不单独出文件。

    ⚠ 铁律：**有什么才写什么**。这张表是采购清单就不该出现甲供/C30 口径，
    没有劳务项就不该出现劳务谈判区间——不能拿一套模板硬套所有项目。
    """
    n = []
    has_owner = bool(summary.get("甲供项数") or summary.get("有甲供"))
    has_c30 = bool(summary.get("C30方量"))
    has_labor = bool(summary.get("有劳务"))
    pure_buy = not has_owner and not has_labor
    if pure_buy:
        n.append("【本表口径】本清单为**设备材料采购清单**，全部由我方采购，"
                 "单价为设备采购价（含税）；不含安装。不涉及甲供/C30/劳务分包口径。")
    else:
        if has_c30 or has_owner:
            n.append("【口径】本表同时给出「甲供 C30 版」与「甲方不提供 C30 版」两个口径；"
                     "甲供材料只免材料费，安装人工照计，不进入材料取费基数。")
        else:
            n.append("【口径】设备材料计材料费、劳务计人工与机械；"
                     "管理费与税金按取费链逐级计取。")
    if env_rate > 0:
        n.append("【环境与条件修正】%s（累计系数 %.1f%%，上限 8%%，只在编制依据中有出处时才计取，"
                 "且只作用在人工直接费上，材料不跟着取费）。"
                 % ("、".join("%s +%.0f%%" % (h["条件"], h["上调"] * 100) for h in env_hits),
                    env_rate * 100))
    if has_labor:
        n.append("【取费链】人工降效与窝工 6% → 不可预见风险包干 4%（同基数）→ "
                 "管理费 10%（基数＝直接费＋降效＋风险）→ 税金 3%（简易计税）。"
                 + ("材料款单列时只计采购管理费 5%＋税金 3%，不进入 6%/4% 基数。"
                    if has_c30 else ""))
    else:
        n.append("【取费链】设备材料直接费 → 采购管理费 5% → 税金 3%（简易计税）。"
                 "本清单是设备材料采购清单，无劳务子目，不涉及人工降效、风险包干与"
                 "交通安措；对外报价即设备材料到场价 ＋ 采购管理费 ＋ 税金。")
    bs = summary.get("背景规格") or {}
    if bs:
        parts = []
        if bs.get("基础体积"):
            parts.append("基础 %.3f m³/座%s" % (
                bs["基础体积"],
                "（%g×%g×%g m）" % (bs["基础长"], bs["基础宽"], bs["基础高"])
                if bs.get("基础长") else ""))
        if bs.get("基坑体积"):
            parts.append("基坑 %.3f m³/座（%g×%g×%g m）" % (
                bs["基坑体积"], bs["基坑长"], bs["基坑宽"], bs["基坑高"]))
        if bs.get("钢筋kg"):
            parts.append("钢筋 %.1f kg/座" % bs["钢筋kg"])
        if bs.get("C15方量"):
            parts.append("C15 垫层 %.3f m³/座" % bs["C15方量"])
        n.append("【基础与含量口径】取自项目「基础要求/技术方案」：%s（%s）；"
                 "此项覆盖清单备注里的尺寸，含量库按此口径折算工日。"
                 % ("；".join(parts), bs.get("尺寸来源", "")))
    if has_owner:
        n.append("【甲供材责任】甲供材料由甲方运至现场指定地点，我方负责卸车、保管与二次倒运；"
                 "安装损耗超 2% 的部分按材料价扣赔。")
    if has_labor:
        n.append("【交通导改】占道、导改报批与持证引导员由我方负责并已计入安措；"
                 "因甲方或交管原因导致停工待料，按窝工签证计取。")
    n.append("【计量与支付】月计量 80%，完工验收后付至 95%，余 5% 为质保金；"
             "质保期按合同约定，质保金到期无息退还。")
    if has_labor:
        adj = "人工单价较基准期波动 ±10% 以外"
        if has_c30:
            adj += "、C30 到场价波动 ±5% 以外"
        n.append("【调差】%s时按当地信息价调差，只调价差不调取费；"
                 "基准期以合同签订当月为准。" % adj)
    if has_c30:
        n.append("【损耗包干】我方采购的 C30 混凝土按 2% 以内损耗包干，超出部分按实计量。")
    n.append("【有效期】本报价自出具之日起 30 天有效；未列项按现场签证另计。")
    if has_labor:
        n.append("【谈判区间】底线＝总价下浮 0~12%（材料款实报实销时下浮主要作用在劳务费）；"
                 "推荐签约区间＝±2~4%；条件切换项：劳务方自带交通安措器材可减；"
                 "材料款实报实销＋固定配合费对双方更稳。")
        n.append("【可选项｜暂不计入总额，按现场签证】硬地层破碎、夜间施工补贴、管制窝工、"
                 "吊车待机、管线探测配合、临时占地围挡。")
    else:
        n.append("【采购说明】价格为设备材料到场价（含税），含运输、装卸与保险；"
                 "不含安装、调试与土建配合。规格变更或数量增减按合同约定调整。")
    if summary.get("C30方量"):
        n.append("【甲方不提供 C30 口径】C30 方量 %.0f m³（%s），到场价 %.0f 元/m³；"
                 "材料款按 采购管理费 5%%＋税金 3%% 单列，不进入 6%%/4%% 取费基数；"
                 "浇筑人工已含在基础包工包料工序中，此处只加落地配合费 %.0f 元/单位。"
                 % (summary["C30方量"], summary.get("C30方量口径", ""),
                    summary.get("参数", {}).get("C30单价", 0),
                    summary.get("参数", {}).get("落地配合费元每单位", 0)))
    if ask:
        n.append("【待确认】%d 项供应归属存疑，已在「①设备清单」中标为 E 存疑，"
                 "需业主或设计确认后再定稿。" % len(ask))
    n.append(("【数据来源】设备材料单价取自企业价格库 / 历史报价库 / 互联网检索，"
              "基准期为当期；偏差控制目标 ±10%。" if pure_buy else
              "【数据来源】劳务与材料单价取自企业价格库 / 定额库 / 联网当期行情，"
              "基准期为当期；偏差控制目标 ±10%、命中率 60% 左右（用户给定口径）。"))
    return n


def web_wage_mult(pl_mod, cfg_json, params):
    """纯网口径的工日单价系数 = 网查当地工日单价 ÷ 我们锁定的基准工日单价。"""
    try:
        key = pl_mod.webprice.read_dashscope_key()
        if not key:
            return 1.0, ""
        info = pl_mod.webprice.labor_day_rate(cfg_json.get("project_region") or "陕西",
                                              cfg_json, key, pl_mod.webprice.Cache())
        if not info.get("found"):
            return 1.0, "未查到当地工日单价，回落基准工日单价"
        crew = params.get("工种") or []
        base = (sum(n * w for _, n, w in crew) / sum(n for _, n, _ in crew)) if crew else 282.67
        mult = round(float(info["工日单价"]) / base, 4)
        if mult < 1.0:
            # 用户口径「不压价」：网查工日单价低于我们锁定的基准价时不往下压
            return 1.0, ("网查 %s 元/工日（%s）低于基准 %.2f 元/工日，"
                         "按「不压价」口径仍取基准价（系数 1.000）"
                         % (info["工日单价"], info.get("来源") or "联网检索", base))
        return mult, "网查 %s 元/工日（%s）÷ 基准 %.2f 元/工日 = 系数 %.3f" % (
            info["工日单价"], info.get("来源") or "联网检索", base, mult)
    except Exception as e:  # noqa: BLE001
        return 1.0, "网查工日单价失败（%s），回落基准价" % str(e)[:40]


def run(boq_path, over=None, bg_text="", reference=None, out_name="1.成本测算六件套.xlsx",
        export=True, tolerance=0.10, out_dir=None):
    """跑完整链路，产出四件套并返回校验结果。"""
    ctx = {}
    over = dict(over or {})
    # 先读技术方案/基础要求里的规格，再进组价链（清单备注里的尺寸会被它覆盖）
    spec = content_mod.spec_from_text(bg_text)
    if spec:
        over["背景规格"] = spec
    shared_web = {}          # 两条线共用的联网取价结果
    over["共享网价"] = shared_web
    # write_files=False：不再生成那 6 个分散文件（六件套才是交付物），
    # 也避免"纯采购清单没有劳务子目 → 0 个 sheet → openpyxl 保存崩"这类问题
    p, summary, files = project_quote.run(boq_path, over, ctx=ctx, write_files=False)
    items = ctx["清单明细"]
    tagged, ask = ownership.classify_items(items)
    labor_rows = ctx["带价劳务"]
    cost_rows = ctx["带价设备"]
    rates = ctx["参数"]
    n_units = float(summary.get("单位数") or 1) or 1.0

    # ── 纯网络检索口径：设备材料全部走网价；劳务人工单价改用网查当地工日单价 ──
    from engine import pipeline as _pl
    cfg_json = _pl.json.load(open(os.path.join(ROOT, "config", "settings.json"),
                                  encoding="utf-8"))
    _kept, _dropped, equip_items, labor_items = _pl.est.split_items(items)
    cost_rows_net = _pl.price_equipment(equip_items, cfg_json, pure_online=True,
                                        shared_web=shared_web)
    # 甲供项也列进成本测算表（单价 0、蓝底、注明"材料不计价"），保证表格完整可见
    owner_rows = []
    for i, x in enumerate([y for y in items if y.get("甲供") == "是"], 1):
        inst = next((r for r in labor_rows
                     if str(r[1]) == "%s（甲供材安装）" % x["项目名称"]), None)
        owner_rows.append([i, x["项目名称"], x["备注"][:40], x["单位"], x["数量"],
                           ("甲方供料·材料不计价（无材料报价来源）；"
                            "安装劳务来源：%s" % inst[5]) if inst else
                           "甲方供料·材料不计价（无材料报价来源）",
                           0, 0, "",
                           "甲方供料：材料费不计价、不作取费基数；本项安装人工见⑤⑥劳务报价",
                           "", ""])
    cost_rows = list(cost_rows) + owner_rows
    cost_rows_net = list(cost_rows_net) + owner_rows
    web_mult, web_rate_note = web_wage_mult(_pl, cfg_json, p)
    labor_rows_net = _pl.price_labor(labor_items, cfg_json, pure_online=True,
                                     spec=spec, mult=web_mult)
    if p.get("甲供计安装劳务"):
        labor_rows_net += project_quote.owner_install_rows(
            items, len(labor_rows_net), web_mult)
    if web_rate_note:
        for row in labor_rows_net:
            row[9] = ("%s｜纯网口径：%s" % (row[9], web_rate_note)).strip("｜")

    # ── 环境与条件修正：只加在人工直接费上 ──
    env_rate, env_hits = env_adjust(bg_text)
    env_add = round(float(summary["劳务合计"]) * env_rate, 2)

    def chain(direct):
        de = direct * rates["降效率"]
        ri = direct * rates["风险率"]
        sub = direct + de + ri
        mg = sub * rates["管理费率"]
        tx = (sub + mg) * rates["税率"]
        return {"直接费": round(direct, 2), "降效": round(de, 2), "风险": round(ri, 2),
                "管理费": round(mg, 2), "税金": round(tx, 2),
                "取费": round(de + ri + mg + tx, 2), "总计": round(sub + mg + tx, 2)}

    direct_a = (float(summary["设备材料合计"]) + float(summary["劳务合计"])
                + float(summary["安措合计"]) + env_add)
    # 纯设备材料采购清单（没有任何劳务子目）：按用户口径只计
    # 「采购管理费 5% + 税金 3%」，不套施工类的降效 6% / 风险 4% / 管理费 10%。
    # 以前这里对采购清单也套施工取费链，材料被多收 24%，且⑤⑥劳务报价表是 0 元。
    supply_only = float(summary["劳务合计"]) <= 0

    def chain_material(direct):
        mg = direct * float(rates["材料采购管理费率"])
        sub = direct + mg
        tx = sub * float(rates["税率"])
        return {"直接费": round(direct, 2), "降效": 0.0, "风险": 0.0,
                "管理费": round(mg, 2), "税金": round(tx, 2),
                "取费": round(mg + tx, 2), "总计": round(sub + tx, 2)}

    a = (chain_material(float(summary["设备材料合计"])) if supply_only
         else chain(direct_a))

    # 甲方不提供 C30：劳务线（含浇筑人工＋落地配合）＋材料线（只计采购管理费与税金）
    # 甲方不提供 C30 时的方量：调用方没给就按"包工包料项的基础体积×数量×损耗"自动推
    c30_vol = float(rates.get("C30方量") or 0)
    auto_c30 = False
    if not c30_vol:
        tot = 0.0
        for x in items:
            if x.get("类别") == "包工包料":
                v = content_mod.bulk_volume(x["项目名称"], x.get("备注", ""), x["单位"],
                                            spec=spec)
                q = x["数量"] if isinstance(x["数量"], (int, float)) else 0
                tot += v["体积"] * q * float(rates["C30损耗"])
        if tot:
            c30_vol, auto_c30 = round(tot, 2), True
    # 基础本身是包工包料，浇筑人工已含在「混凝土浇筑及养护」工序里；
    # 只有调用方明确要求把浇筑人工单列时才另计，避免重复计价。
    pour = (float(rates["C30浇筑人工元每单位"]) * n_units
            if (c30_vol and rates.get("单列浇筑人工")) else 0.0)
    fit = float(rates["落地配合费元每单位"]) * n_units
    b_labor = chain(direct_a + pour + fit) if c30_vol else dict(a)
    b_material = (c30_vol * float(rates["C30单价"]) * (1 + rates["材料采购管理费率"])
                  * (1 + rates["税率"]))
    b_total = b_labor["总计"] + b_material

    asm = dict(summary)
    asm["甲供项数"] = sum(1 for x in items if x.get("甲供") == "是")
    asm["有甲供"] = asm["甲供项数"] > 0
    asm["有劳务"] = len(labor_rows) > 0
    asm["甲供C30版"] = a
    asm["不提供C30版"] = {"劳务线含税": b_labor["总计"], "材料线含税": round(b_material, 2),
                          "总计": round(b_total, 2)}
    asm["环境修正"] = {"系数": env_rate, "命中": env_hits, "金额": env_add}
    asm["甲供计安装劳务"] = p.get("甲供计安装劳务")
    asm["项目名称"] = p["项目名称"]
    # ③④劳务报价的对外总包价：劳务直接费 + 交通安措 + 环境修正，再走取费链
    asm["甲供C30版"] = a
    net_direct = (sum(x[7] for x in cost_rows_net if isinstance(x[7], (int, float)))
                  + sum(x[7] for x in labor_rows_net if isinstance(x[7], (int, float)))
                  + float(summary["安措合计"]) + env_add)
    asm["纯网报价"] = chain(net_direct)
    asm["纯网工日系数"] = web_mult
    asm["纯网工日说明"] = web_rate_note
    # ③④劳务报价是"劳务分包对外总包"，取费基数只含 劳务 + 交通安措 + 环境修正，
    # 不含甲供设备材料（那部分不在劳务分包范围里）
    labor_direct_a = (sum(x[7] for x in labor_rows if isinstance(x[7], (int, float)))
                      + float(summary["安措合计"]) + env_add)
    labor_direct_b = (sum(x[7] for x in labor_rows_net if isinstance(x[7], (int, float)))
                      + float(summary["安措合计"]) + env_add)
    if supply_only:
        # 采购清单的⑤⑥给"设备材料采购总包报价"：明细用设备行，
        # 取费走 采购管理费 5% + 税金 3%，不再是 0 元空表
        equip_a = sum(x[7] for x in cost_rows if isinstance(x[7], (int, float)))
        equip_b = sum(x[7] for x in cost_rows_net if isinstance(x[7], (int, float)))
        asm["劳务报价库网"] = chain_material(equip_a)
        asm["劳务报价纯网"] = chain_material(equip_b)
        asm["采购口径"] = True
    else:
        asm["劳务报价库网"] = chain(labor_direct_a)
        asm["劳务报价纯网"] = chain(labor_direct_b)
    asm["纯采购清单"] = supply_only

    asm["C30方量"] = c30_vol
    asm["C30方量口径"] = ("按各包工包料项的基础体积×数量×损耗 %.0f%% 自动推算"
                          % ((float(rates["C30损耗"]) - 1) * 100)) if auto_c30 else "由调用方给定"
    if spec:
        asm["背景规格"] = spec
    notes = build_notes(p, asm, env_hits, env_rate, ask, a, b_labor)
    # 取价健康度自检：搜索被风控 / 大批没价，不能悄悄过去
    hc = health.audit(cost_rows, labor_rows)
    asm["健康度"] = hc
    notes = [health.to_text(hc)] + list(notes)
    out_dir = out_dir or summary["输出目录"]
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    owner_names = {x["项目名称"] for x in items if x.get("甲供") == "是"}
    assemble.build(p["项目名称"], tagged, cost_rows, cost_rows_net, labor_rows,
                   labor_rows_net, asm, out_path, notes=notes, owner_names=owner_names)

    chk = checkup.verify(out_path, reference=reference, tolerance=tolerance)
    dst, exported = ("", [])
    if export:
        dst, exported = export_files([out_path], p["项目名称"])
    renamed = list(getattr(export_files, "renamed", []) or [])

    return {
        "项目名称": p["项目名称"], "地区": p["地区"],
        "四件套文件": out_path, "输出目录": out_dir,
        "导出目录": dst, "导出文件": exported,
        "被占用另存": renamed,
        "校验": chk,
        "甲供C30版": {"直接费": a["直接费"], "取费": a["取费"], "总计": a["总计"],
                      "每单位": round(a["总计"] / n_units, 2)},
        "不提供C30版": {"劳务线": b_labor["总计"], "材料线": round(b_material, 2),
                        "总计": round(b_total, 2), "每单位": round(b_total / n_units, 2)},
        "纯网报价": {"直接费": asm["纯网报价"]["直接费"], "总计": asm["纯网报价"]["总计"],
                     "每单位": round(asm["纯网报价"]["总计"] / n_units, 2),
                     "工日系数": web_mult, "工日说明": web_rate_note},
        "劳务报价总包": asm["劳务报价库网"]["总计"],
        "纯采购清单": supply_only,
        "环境修正": {"系数": env_rate, "金额": env_add,
                     "命中": [h["条件"] for h in env_hits]},
        "供应归属清点": ownership.summarize(tagged),
        "待确认项": ask,
        "健康度": hc,
        "备注条目数": len(notes),
    }


def export_files(paths, project=""):
    """把生成的 Excel 复制到固定导出目录（宿主机桌面），方便直接打开。

    目标文件被 Excel/WPS 占用时不让整次测算失败：另存「（新）」或编号名，
    并把这个情况写进返回结果，提醒使用者以新版为准。
    """
    raw = "".join(c for c in (project or "输出") if c not in '\\/:*?"<>|')
    safe = " ".join(raw.replace("\u3000", " ").split())[:30] or "输出"
    dst_dir = os.path.join(EXPORT_DIR, safe)
    os.makedirs(dst_dir, exist_ok=True)
    out, renamed = [], []
    for src in paths or []:
        base = os.path.basename(src)
        stem, ext = os.path.splitext(base)
        cands = [base] + ["%s（新%s）%s" % (stem, "" if i == 1 else i, ext)
                          for i in range(1, 10)]
        for name in cands:
            dst = os.path.join(dst_dir, name)
            try:
                shutil.copy2(src, dst)
                out.append(dst)
                if name != base:
                    renamed.append(os.path.basename(dst))
                break
            except Exception:
                continue
    host_dir = HOST_EXPORT_DIR.rstrip("\\/") + "\\" + safe
    export_files.renamed = renamed
    return host_dir, out
