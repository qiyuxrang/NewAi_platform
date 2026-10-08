# -*- coding: utf-8 -*-
"""把结果 xlsx 的每个 Sheet 渲染成 PNG，便于在对话里直接看。

用法：  .venv\\Scripts\\python.exe tools\\preview_xlsx.py "data\\output\\xxx.xlsx"
"""
import html
import os
import subprocess
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


WIDTHS = [5, 22, 16, 6, 8, 16, 9, 11, 12, 46, 10, 8]


def sheet_html(name, rows, subtitle=""):
    head = rows[0] if rows else []
    body = rows[1:]
    th = "".join("<th>%s</th>" % html.escape(str(c or "")) for c in head)
    cols = "".join("<col class='c%d'>" % (i + 1) for i in range(len(head)))
    trs = []
    for r in body:
        src = str(r[5] or "") if len(r) > 5 else ""
        cls = " class=\"fill\"" if ("待互联网" in src or "甲供" in src) else ""
        tds = []
        for i, c in enumerate(r):
            v = "" if c is None else c
            if isinstance(v, float):
                v = ("%.2f" % v).rstrip("0").rstrip(".")
            s = str(v)
            if i in (2, 9) and len(s) > 130:      # 规格、依据说明：预览里截断
                s = s[:130] + "…"
            if i == 8 and len(s) > 40:
                s = s[:40] + "…"
            tds.append("<td>%s</td>" % html.escape(s))
        trs.append("<tr%s>%s</tr>" % (cls, "".join(tds)))
    tpl = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<style>
 body{margin:0;padding:18px 20px;background:#fff;font-family:"Microsoft YaHei",sans-serif;color:#1f2430}
 h1{font-size:17px;margin:0 0 4px;color:#1F3864}
 .sub{font-size:12px;color:#666;margin-bottom:10px}
 table{border-collapse:collapse;font-size:12.5px;table-layout:fixed;width:1460px}
 col.c1{width:40px}col.c2{width:200px}col.c3{width:150px}col.c4{width:52px}
 col.c5{width:64px}col.c6{width:150px}col.c7{width:80px}col.c8{width:100px}
 col.c9{width:110px}col.c10{width:400px}col.c11{width:88px}col.c12{width:60px}
 th{background:#1F3864;color:#fff;padding:7px 6px;text-align:left;font-weight:600;border:1px solid #d9d9d9}
 td{padding:6px;border:1px solid #e3e3e3;vertical-align:top;word-break:break-all}
 tr:nth-child(even) td{background:#fafbfc}
 tr.fill td{background:#FFF7E0}
 td:nth-child(2){font-weight:500}
 td{line-height:1.35}
</style></head><body>
 <h1>__TITLE__</h1><div class="sub">__SUB__</div>
 <table>__COLS__<thead><tr>__TH__</tr></thead><tbody>__TBODY__</tbody></table>
</body></html>"""
    return (tpl.replace("__TITLE__", html.escape(name))
               .replace("__SUB__", html.escape(subtitle))
               .replace("__TH__", th)
               .replace("__COLS__", cols)
               .replace("__TBODY__", "".join(trs)))


def main():
    path = sys.argv[1]
    wb = openpyxl.load_workbook(path, data_only=True)
    outdir = os.path.join(ROOT, "data", "tmp", "preview")
    os.makedirs(outdir, exist_ok=True)
    for ws in wb.worksheets:
        rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        # 去掉尾部整行空白
        while rows and all(v is None or str(v).strip() == "" for v in rows[-1]):
            rows.pop()
        if not rows:
            continue
        title = str(rows[0][0] or ws.title)
        sub = str(rows[1][0] or "") if len(rows) > 1 else ""
        body_rows = [r for r in rows[3:] if any(v is not None and str(v).strip() for v in r)]
        page = os.path.join(outdir, "sheet_%s.html" % ws.title.replace(" ", "_"))
        with open(page, "w", encoding="utf-8") as f:
            f.write(sheet_html("%s　%s" % (ws.title, title[:30]), body_rows, sub[:120]))
        h = min(4000, 170 + len(body_rows) * 150)
        png = os.path.join(outdir, "sheet_%s.png" % ws.title.replace(" ", "_"))
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--virtual-time-budget=2500", "--window-size=1500,%d" % h,
                        "--screenshot=%s" % png, "file:///" + page.replace("\\", "/")],
                       capture_output=True)
        print("→", png)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
