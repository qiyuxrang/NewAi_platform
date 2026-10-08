# -*- coding: utf-8 -*-
"""通用交付校验：格式模板 / 勾稽一致 / 偏差 ±10% / 口径一致 / 备注列不缺。"""
import openpyxl


def sheet_of(wb, name):
    return wb[name] if name in wb.sheetnames else None


def verify(path, reference=None, tolerance=0.10):
    wb = openpyxl.load_workbook(path, data_only=True)
    issues, checks = [], []

    def ok(cond, good, bad):
        checks.append({"检查": good if cond else bad, "通过": bool(cond)})
        if not cond:
            issues.append(bad)
        return cond

    need = ["①设备清单", "②劳务清单", "③成本测算（库+网检索）", "④成本测算（纯网检索）",
            "⑤劳务报价（库+网检索）", "⑥劳务报价（纯网检索）"]
    ok(all(n in wb.sheetnames for n in need),
       "六件套齐全（设备清单 + 劳务清单 + 成本×2 + 劳务报价×2）",
       "缺 Sheet：%s" % [n for n in need if n not in wb.sheetnames])

    # 每张表的列位置不同：qty/price/total 都是 0 基索引
    COLS = {"①设备清单": (3, 7, 8), "②劳务清单": (5, 6, 7)}
    SRC = {"①设备清单": 10}

    for name in need:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        heads = []
        for row in ws.iter_rows(min_row=1, max_row=4, values_only=True):
            heads = [str(c) for c in row if c]
            if any("备注" in h for h in heads):
                break
        ok(any("备注" in h for h in heads), "%s 有备注列" % name, "%s 没有备注列" % name)

    # 逐行勾稽：只要有单价和数量，就必须 单价×数量＝合价
    for name in need:
        ws = sheet_of(wb, name)
        if not ws:
            continue
        iq, ip, it = COLS.get(name, (4, 5, 6))
        bad = 0
        for r in ws.iter_rows(min_row=4, values_only=True):
            if max(iq, ip, it) >= len(r):
                continue
            qty, price, total = r[iq], r[ip], r[it]
            if not isinstance(price, (int, float)) or not isinstance(total, (int, float)):
                continue
            if not isinstance(qty, (int, float)):
                continue
            if abs(price * qty - total) > max(1.0, 0.01 * abs(total)):
                bad += 1
        ok(bad == 0, "%s 逐行勾稽（单价×数量=合价）" % name,
           "%s 有 %d 行勾稽不平" % (name, bad))

    # 不留空：明细行的单价与合价必须都有数
    for name in need:
        ws = sheet_of(wb, name)
        if not ws:
            continue
        iq, ip, it = COLS.get(name, (4, 5, 6))
        blank = 0
        for r in ws.iter_rows(min_row=4, values_only=True):
            if max(iq, ip, it) >= len(r):
                continue
            if not r[1] or not isinstance(r[iq], (int, float)):
                continue          # 说明行 / 合计行不算明细
            if not isinstance(r[ip], (int, float)) or not isinstance(r[it], (int, float)):
                blank += 1
        ok(blank == 0, "%s 单价与合价无空白" % name,
           "%s 有 %d 行单价或合价是空的" % (name, blank))

    # 数据来源列：每一行明细都必须写清"出自哪本库 / 哪个网站"
    for name in need:
        ws = sheet_of(wb, name)
        if not ws:
            continue
        _, _, it = COLS.get(name, (4, 5, 6))
        isrc = SRC.get(name, 9)
        miss = 0
        for r in ws.iter_rows(min_row=4, values_only=True):
            if isrc >= len(r) or it >= len(r):
                continue
            # 序号是数字才算明细行（合计行/小计行不算）
            if not isinstance(r[0], (int, float)):
                continue
            if r[1] and isinstance(r[it], (int, float)) and not str(r[isrc] or "").strip():
                miss += 1
        ok(miss == 0, "%s 数据来源列无空白" % name,
           "%s 有 %d 行数据来源为空" % (name, miss))

    # 劳务报价的取费链勾稽（⑤⑥）
    for name in need[4:]:
        ws = sheet_of(wb, name)
        if not ws:
            continue
        vals = {}
        for r in ws.iter_rows(min_row=4, values_only=True):
            if r[1] and isinstance(r[6], (int, float)):
                vals[str(r[1])[:5]] = r[6]
        d = (vals.get("一、劳务直", 0) + vals.get("二、交通安", 0)
             + vals.get("三、环境与", 0))
        ok(abs(vals.get("四、人工降", 0) - d * 0.06) < 1,
           "%s 降效 6%% 勾稽" % name, "%s 降效不等于直接费×6%%" % name)
        ok(abs(vals.get("五、不可预", 0) - d * 0.04) < 1,
           "%s 风险 4%% 勾稽" % name, "%s 风险不等于直接费×4%%" % name)
        ok(abs(vals.get("六、管理费", 0)
               - (d + vals.get("四、人工降", 0) + vals.get("五、不可预", 0)) * 0.10) < 1,
           "%s 管理费 10%% 勾稽" % name, "%s 管理费勾稽不平" % name)
        if reference:
            got = vals.get("八、对外报", 0)
            if got:
                dev = got / reference - 1
                ok(abs(dev) <= tolerance,
                   "与参考值偏差 %.1f%%（±10%% 内）" % (dev * 100),
                   "与参考值偏差 %.1f%%，超出 ±10%%" % (dev * 100))

    bad_font = bad_border = 0
    for name in need:
        if name not in wb.sheetnames:
            continue
        for row in wb[name].iter_rows():
            for c in row:
                if c.value is None:
                    continue
                if c.font and c.font.name != "微软雅黑":
                    bad_font += 1
                if not (c.border and c.border.left and c.border.left.style):
                    bad_border += 1
    ok(bad_font == 0, "字体统一微软雅黑", "有 %d 个单元格字体不符" % bad_font)
    ok(bad_border == 0, "单元格全边框", "有 %d 个单元格缺边框" % bad_border)

    ws = sheet_of(wb, "⑥劳务报价（纯网检索）")
    if ws:
        c = ws.column_dimensions["C"].width or 0
        i = ws.column_dimensions["I"].width or 0
        ok(c >= 40 and i >= 44, "报价表列宽够看（C %.0f / I %.0f）" % (c, i),
           "报价表列宽不足（C %.0f / I %.0f）" % (c, i))
    wb.close()
    return {"通过": not issues, "问题": issues,
            "通过数": sum(1 for c in checks if c["通过"]), "总检查": len(checks),
            "检查项": checks}
