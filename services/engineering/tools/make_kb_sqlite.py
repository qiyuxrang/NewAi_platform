# -*- coding: utf-8 -*-
"""把定额 JSON 转成 SQLite 知识库（引擎从库里读，省内存）。

输出： data/library/成本测算知识库.sqlite
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "library")
DB = os.path.join(LIB, "成本测算知识库.sqlite")


def main():
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("""CREATE TABLE quota_basis(
        code TEXT, major TEXT, chapter TEXT, name TEXT, unit TEXT, base_price REAL,
        labor_fee REAL, material_fee REAL, machine_fee REAL, overhead REAL,
        profit REAL, source TEXT)""")
    c.execute("""CREATE TABLE quota_cons(
        code TEXT, major TEXT, chapter TEXT, name TEXT, unit TEXT, work_content TEXT,
        labor_hours REAL, machine_shift REAL, detail TEXT, source TEXT)""")

    basis = json.load(open(os.path.join(LIB, "定额基价库.json"), encoding="utf-8"))
    c.executemany("""INSERT INTO quota_basis VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  [(r.get("编号"), r.get("专业"), r.get("章节"), r.get("项目名称"),
                    r.get("单位"), r.get("基价"), r.get("人工费"), r.get("材料费"),
                    r.get("机械费"), r.get("管理费"), r.get("利润"), r.get("来源"))
                   for r in basis])
    del basis
    cons = json.load(open(os.path.join(LIB, "定额含量库.json"), encoding="utf-8"))
    c.executemany("""INSERT INTO quota_cons VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  [(r.get("编号"), r.get("专业"), r.get("章节"), r.get("项目名称"),
                    r.get("单位"), r.get("工作内容"), r.get("人工工日"), r.get("机械台班"),
                    None, r.get("来源")) for r in cons])
    c.executescript("""
        CREATE INDEX idx_qb ON quota_basis(major, code);
        CREATE INDEX idx_qc ON quota_cons(major, code);
        CREATE INDEX idx_qb_name ON quota_basis(name);
    """)
    con.commit()
    n1 = c.execute("SELECT COUNT(*) FROM quota_basis").fetchone()[0]
    n2 = c.execute("SELECT COUNT(*) FROM quota_cons").fetchone()[0]
    con.close()
    print("入库：定额基价 %d 条、定额含量 %d 条 → %s（%.0f MB）"
          % (n1, n2, DB, os.path.getsize(DB) / 1024 / 1024))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
