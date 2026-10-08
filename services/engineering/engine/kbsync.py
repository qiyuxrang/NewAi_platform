# -*- coding: utf-8 -*-
"""知识库同步：供人工审核后将六件套网价回写进企业知识库，形成正循环。

下次同样的设备直接命中历史价，不用再联网（省时间、也不再受搜索源风控影响）。
写库前统一过「工程经验价格带」，明显不合理的价一律拒绝入库。
"""
import os

import openpyxl

from engine import webprice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EOK = "互联网检索"


def extract_from_workbook(path, include=("互联网检索",), only_priced=True):
    """从六件套 Excel 里抽出可入库的价，返回记录列表。"""
    from collections import defaultdict
    wb = openpyxl.load_workbook(path, data_only=True)
    out, skipped = [], 0
    # 先扫一遍：找出"一个价打天下"的（同一价+同来源被打到 3 个以上不同设备）→ 不入库
    reuse = defaultdict(set)
    for name in wb.sheetnames:
        if not (name.startswith("③") or name.startswith("④")):
            continue
        for r in wb[name].iter_rows(min_row=4, values_only=True):
            if isinstance(r[0], (int, float)) and r[1] and isinstance(r[5], (int, float)):
                reuse[(round(float(r[5]), 2), str(r[7] or "")[:80])].add(str(r[1]))
    import re as _re
    bad = set()
    for k, names in ((k, sorted(v)) for k, v in reuse.items()):
        if len(names) >= 3:
            bad.add(k)
            continue
        if len(names) >= 2:
            nums = [set(_re.findall(r"\d+", n)) for n in names]
            if any(nums[i] != nums[0] for i in range(1, len(nums))):
                bad.add(k)
    for name in wb.sheetnames:
        if not (name.startswith("③") or name.startswith("④")):
            continue                     # 以"库+网"和"纯网"两张成本表为准
        ws = wb[name]
        for r in ws.iter_rows(min_row=4, values_only=True):
            if not isinstance(r[0], (int, float)) or not r[1]:
                continue
            src = str(r[7] or "")
            note = str(r[8] or "")
            price = r[5]
            if not isinstance(price, (int, float)) or not price:
                continue
            if not any(k in src for k in include):
                continue
            # 不入库的几类：类比暂估、低位价预警（这类价复核前不能沉淀成"历史价"，
            # 否则以后每次都会被它带偏）
            if ("类比" in src or "暂估" in src
                    or "低位价" in note or "务必复核" in note):
                skipped += 1
                continue
            if (round(float(price), 2), src[:80]) in bad:
                skipped += 1
                continue
            band = webprice.price_band(r[1])
            if band and not (band[0] <= price <= band[1]):
                skipped += 1
                continue
            out.append({"名称": r[1], "规格": str(r[2] or ""), "单位": r[3],
                        "单价": round(float(price), 2),
                        "来源说明": src, "备注": str(r[8] or "")[:200],
                        "数据来源": str(r[9] or "")[:200],
                        # ⚠ 核验链接必须一起入库。以前这里没取，回写时又把
                        # 网价原记录整条覆盖掉 → 链接丢了，出表只能写「未取到具体链接」，
                        # 人工审核时点不回去，用户明确要求过"线上检索的价必须带链接"。
                        "链接": (str(r[10] or "").strip()
                                 if len(r) > 10 and str(r[10] or "").startswith("http")
                                 else "")})
    wb.close()
    return out, skipped


def merge(records, tag="六件套回写"):
    """合并进自动入库文件（同名同规格同单位只留最新一条），返回 (新增, 覆盖)。"""
    path = webprice.MEMO
    old = {}
    if os.path.exists(path):
        import json
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            old[(d.get("名称"), d.get("规格"), d.get("单位"))] = d
    added = updated = 0
    for rec in records:
        key = (rec["名称"], rec["规格"], rec["单位"])
        if key in old:
            if abs(float(old[key].get("单价元") or 0) - rec["单价"]) < 0.01:
                continue
            updated += 1
        else:
            added += 1
        # 链接能留就留：本次没抓到（或来源是本地库）时，沿用库里已有的那条链接
        link = rec.get("链接") or (old.get(key) or {}).get("链接") or ""
        old[key] = {"来源文件": "互联网检索自动入库｜%s" % tag, "表名": "网价",
                    "行号": "", "类别": "设备/材料", "名称": rec["名称"],
                    "品牌": "", "型号": "", "规格": rec["规格"], "单位": rec["单位"],
                    "数量": None, "单价元": rec["单价"], "金额元": None,
                    "备注": rec["备注"], "出现次数": 1,
                    "链接": link,
                    "入库时间": __import__("datetime").date.today().isoformat()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import json
    with open(path, "w", encoding="utf-8") as f:
        for d in old.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    from engine import pipeline
    pipeline._HIST_CACHE.clear()
    return added, updated


def sync(path, include=("互联网检索",)):
    recs, skipped = extract_from_workbook(path, include=include)
    added, updated = merge(recs)
    return {"可入库": len(recs), "新增": added, "覆盖": updated,
            "被价格带拒绝": skipped,
            "明细": recs[:30],
            "说明": "已写入 data/library/网价入库.jsonl，下次测算会先命中历史价库"}
