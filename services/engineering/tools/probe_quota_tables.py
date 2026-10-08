# -*- coding: utf-8 -*-
"""在定额 Word 里找出真正的『定额子目表』并完整打印样例。

用法：  python tools/probe_quota_tables.py "路径.docx" [样例数]
"""
import re
import sys

import docx


CODE_RE = re.compile(r"^\s*\d+\s*-\s*\d+\s*-\s*\d+")
KEY_RE = re.compile(r"定额编号|计量单位|工作内容")


def table_text(t):
    return "\n".join(" ".join(c.text for c in r.cells) for r in t.rows)


def main():
    path = sys.argv[1]
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    d = docx.Document(path)
    hits = []
    for i, t in enumerate(d.tables):
        txt = table_text(t)
        score = 0
        if "定额编号" in txt:
            score += 2
        if "计量单位" in txt:
            score += 1
        if "工作内容" in txt:
            score += 1
        if CODE_RE.search(txt):
            score += 2
        if score >= 3:
            hits.append((i, score, len(t.rows), len(t.columns), txt))

    print("总表数 %d，疑似定额子目表 %d 个" % (len(d.tables), len(hits)))
    for i, score, rows, cols, txt in hits[:want]:
        print("=" * 40)
        print("表 %d  评分 %d  行 %d  列 %d" % (i, score, rows, cols))
        print(txt[:2000])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
