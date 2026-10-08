# -*- coding: utf-8 -*-
"""文本归一化与规格参数抽取。零第三方依赖。"""
import re

# 只保留有区分度的单位，避免把 "2块"、"3根" 这类辅材数量当成规格
UNITS = ("mm", "cm", "km", "kw", "kva", "kwh", "wp", "w", "kv", "v", "a",
         "ah", "hz", "rpm", "db", "kg", "t", "m3/s", "m2", "m", "芯", "口",
         "路", "米", "套", "台", "%")

_NUM_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")",
                       re.IGNORECASE)
# 带连字符的完整型号，如 HF-IES-4000-K10P8T2SF
_MODEL = re.compile(r"[A-Za-z]{2,}[-/][A-Za-z0-9./-]{2,}")
# 电缆/光缆型号代码，如 BVV、YJV22、RVVP、GYTA
_CODE = re.compile(r"\b[A-Z]{2,}[0-9]{0,5}\b")
# 芯数×截面，如 3*2.5、4*25、2*1.5
_CABLE = re.compile(r"(\d+)\s*[x*×]\s*(\d+(?:\.\d+)?)")
# 纯单位缩写，不算型号
_STOP_CODES = {"MM", "CM", "KM", "KW", "KVA", "KWH", "KV", "AH", "HZ",
               "RPM", "DB", "KG", "WP", "GB", "TB", "MB", "M"}
_CN_WORD = re.compile(r"[\u4e00-\u9fa5]{2,}")

# 名称里的修饰词，匹配时应忽略
NOISE = ("采购", "安装", "含税", "甲供", "设备", "材料", "（新增）", "(新增)")


def normalize(s):
    """全角转半角、去空白、统一符号，供比较用。"""
    if s is None:
        return ""
    s = str(s)
    out = []
    for ch in s:
        c = ord(ch)
        if c == 0x3000:
            c = 32
        elif 0xFF01 <= c <= 0xFF5E:
            c -= 0xFEE0
        out.append(chr(c))
    s = "".join(out).replace("*", "x").replace("×", "x")
    s = s.replace("φ", "d").replace("Φ", "d").replace("￠", "d")
    return re.sub(r"\s+", "", s).lower()


def clean_name(name):
    s = str(name or "").strip()
    for w in NOISE:
        s = s.replace(w, "")
    return s.strip() or str(name or "").strip()


def params_of(name, spec):
    """抽取可用于比对的参数集合：型号 + 数值单位 + 中文关键词。"""
    text = "%s %s" % (name or "", spec or "")
    toks = set()
    for m in _MODEL.findall(text):
        toks.add("m:" + m.lower())
    for m in _CODE.findall(text):
        if m not in _STOP_CODES:
            toks.add("a:" + m.lower())
    for a, b in _CABLE.findall(text):
        val = b.rstrip("0").rstrip(".") if "." in b else b
        toks.add("c:%sx%s" % (a, val))
    for num, unit in _NUM_UNIT.findall(text):
        val = num.rstrip("0").rstrip(".") if "." in num else num
        toks.add("n:%s%s" % (val, unit.lower()))
    for w in _CN_WORD.findall(text):
        if len(w) <= 8 and not w.isdigit():
            toks.add("w:" + w)
    return toks


def jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def similarity(a, b):
    """归一化后的字符相似度，避免引入 difflib 之外的重依赖。"""
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()
