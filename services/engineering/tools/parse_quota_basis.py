# -*- coding: utf-8 -*-
"""把『陕西省基价表』Word 版解析成结构化定额库。

源结构（每个子目一行）：
    编号 | 项目名称 | 单位 | 基价 | 人工费 | 材料费 | 施工机具使用费 | 管理费 | 利润

输出：
    data/library/定额基价库.xlsx
    data/library/定额基价库.json

用法：
    python tools/parse_quota_basis.py 文件1.docx 文件2.docx ...
    python tools/parse_quota_basis.py --scan 目录        # 递归找所有 *基价表*.docx
"""
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "data", "library")

CODE_RE = re.compile(r"^\s*(\d+(?:\s*[-–—]\s*\d+){1,3}[a-zA-Z]?)\s*$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

COL_ALIASES = {
    "编号": ["编号", "定额编号", "子目编号"],
    "项目名称": ["项目名称", "项目 名称", "名称", "子目名称"],
    "单位": ["单位", "计量单位"],
    "基价": ["基价"],
    "人工费": ["人工费"],
    "材料费": ["材料费"],
    "机械费": ["施工机具使用费", "机械费", "施工机械使用费"],
    "管理费": ["管理费"],
    "利润": ["利润"],
}


def iter_blocks(doc):
    """按文档顺序产出段落与表格。"""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def norm(v):
    return re.sub(r"\s+", " ", (v or "").replace("\u3000", " ")).strip()


def to_num(v):
    s = norm(v).replace(",", "")
    if not s or s in ("--", "—", "-", "－"):
        return None
    if not NUM_RE.match(s):
        return None
    try:
        return float(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def map_header(row_cells):
    """返回 {字段: 列号}；认不出『编号 + 项目名称』就返回 None。"""
    texts = [norm(c) for c in row_cells]
    mapping = {}
    for field, names in COL_ALIASES.items():
        for i, t in enumerate(texts):
            if any(t == n or (n in t and len(t) <= len(n) + 4) for n in names):
                mapping[field] = i
                break
    if "编号" in mapping and "项目名称" in mapping:
        return mapping
    return None


def parse_file(path, book=""):
    doc = docx.Document(path)
    rows = []
    section = ""
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            t = norm(block.text)
            # 章节标题：长度适中、不是纯数字/页码/日期
            if (2 <= len(t) <= 60 and not t.endswith("。")
                    and not re.fullmatch(r"[\d\s·.．()（）年月日-]+", t)):
                section = t
            continue

        table = block
        if not table.rows:
            continue
        mapping = map_header([c.text for c in table.rows[0].cells])
        if not mapping:
            continue

        for r in table.rows[1:]:
            cells = [norm(c.text) for c in r.cells]
            code = cells[mapping["编号"]] if mapping["编号"] < len(cells) else ""
            m = CODE_RE.match(code)
            if not m:
                continue
            rec = {
                "册别": book,
                "章节": section,
                "编号": re.sub(r"\s+", "", m.group(1)),
                "项目名称": cells[mapping["项目名称"]] if mapping["项目名称"] < len(cells) else "",
                "单位": cells[mapping["单位"]] if mapping.get("单位", 99) < len(cells) else "",
            }
            for f in ("基价", "人工费", "材料费", "机械费", "管理费", "利润"):
                idx = mapping.get(f)
                rec[f] = to_num(cells[idx]) if idx is not None and idx < len(cells) else None
            rec["来源"] = os.path.basename(path)
            if rec["项目名称"]:
                rows.append(rec)
    return rows


def dedupe(rows):
    """同一编号只留一条（重复表格/页眉重复时会出现），保留信息更全的。"""
    best = {}
    for r in rows:
        # 注意：编号只在「同一本基价表」内唯一（房建 1-1-1 与市政 1-1-1 是不同子目）
        key = (r["来源"], r["编号"])
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        score_new = sum(1 for f in ("基价", "人工费", "材料费", "机械费", "管理费", "利润") if r[f] is not None)
        score_old = sum(1 for f in ("基价", "人工费", "材料费", "机械费", "管理费", "利润") if cur[f] is not None)
        if score_new > score_old or (score_new == score_old and len(r["项目名称"]) > len(cur["项目名称"])):
            best[key] = r
    return list(best.values())


def find_files(root):
    out = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".docx") and "基价表" in f and not f.startswith("~$"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def write_outputs(rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    from openpyxl import Workbook

    heads = ["册别", "章节", "编号", "项目名称", "单位", "基价", "人工费", "材料费",
             "机械费", "管理费", "利润", "来源"]
    wb = Workbook()
    ws = wb.active
    ws.title = "定额基价库"
    ws.append(heads)
    for r in rows:
        ws.append([r.get(h) for h in heads])
    ws.freeze_panes = "A2"
    for i, w in enumerate([16, 30, 12, 40, 8, 11, 11, 11, 13, 10, 10, 30], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    xlsx = os.path.join(OUT_DIR, "定额基价库.xlsx")
    wb.save(xlsx)

    js = os.path.join(OUT_DIR, "定额基价库.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return xlsx, js


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--scan":
        files = find_files(args[1])
    else:
        files = args

    all_rows = []
    for f in files:
        book = os.path.splitext(os.path.basename(f))[0]
        try:
            rows = parse_file(f, book=book)
        except Exception as e:  # noqa: BLE001
            print("解析失败 %s: %s" % (f, e))
            continue
        print("%-60s 子目 %5d  %s" % (os.path.basename(f)[:58], len(rows), book))
        all_rows.extend(rows)

    uniq = dedupe(all_rows)
    print("-" * 70)
    print("解析行数 %d，去重后 %d" % (len(all_rows), len(uniq)))
    with_price = [r for r in uniq if r["基价"] is not None]
    print("有基价的子目 %d（%.0f%%）" % (len(with_price), len(with_price) / max(1, len(uniq)) * 100))
    xlsx, js = write_outputs(uniq)
    print("→", xlsx)
    print("→", js)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
