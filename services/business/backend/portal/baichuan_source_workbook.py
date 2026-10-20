"""Read-only normalization of the eight-sheet qualification source workbook.

No Django, database, network, model calls or fuzzy identity resolution. The
summary and seven category sheets must agree as multisets before rows can leave
this boundary. Outputs are source assertions, never independently verified facts.

Run the CLI with the existing .runtime/company-test/python/Scripts/python.exe;
it reuses defusedxml 0.7.1 from that verified environment. This maintenance CLI
is not imported by application request paths and adds no core runtime dependency.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
import uuid
from zipfile import ZipFile

from defusedxml import ElementTree as ET

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
CATEGORIES = ("electronic", "labor", "cs", "cmmi", "ccrc", "itss", "security")
CATEGORY_NAMES = (
    "电子与智能化工程专业承包", "施工劳务资质", "CS 信息系统建设和服务能力等级",
    "CMMI 软件能力成熟度模型", "CCRC 信息系统安全集成服务",
    "ITSS 信息技术运行维护服务符合性", "安防工程企业设计施工维护能力")
SUMMARY_HEADERS = ("序号", "地区", "资质分类", "企业名称", "资质等级", "所在城市", "联系电话")
DETAIL_HEADERS = ("序号", "地区", "企业名称", "资质等级", "所在城市", "联系电话")
CITY_LITERALS = {"西安", "咸阳", "宝鸡", "渭南", "铜川", "延安", "榆林", "汉中", "安康", "商洛"}
PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8}|(?:400|800)(?:[- ]?\d){7}|95\d{3,4}|100\d{2})(?:[-转]\d{1,5})?(?!\d)")
MISSING_PHONE = re.compile(r"未找到|未公开|未披露|未查询到|未检索|暂无|无公开|待补|待查|未提供")


def normalized_name(value):
    """Only whitespace and ASCII/fullwidth parentheses are equivalent here."""
    return re.sub(r"\s+", "", value).translate(str.maketrans({"（": "(", "）": ")"}))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def explicit_grade(category, raw):
    text = re.sub(r"\s+", "", raw)
    if category == "labor":
        return None, "labor_has_no_grade"
    digits = {**dict(zip("一二三四五", "12345")), **dict(zip("壹贰叁肆伍", "12345"))}
    if category == "ccrc":
        matches = re.findall(r"(?:信息系统)?安全集成(?:服务)?([一二三123])级", text)
        grades = {digits.get(value, value) for value in matches}
        return (next(iter(grades)), "explicit_scope_grade") if len(grades) == 1 else (None, "scope_or_grade_unconfirmed")
    if category == "cmmi":
        pattern, valid = r"ML([345])(?:[（(](?:定义级|定量管理级|优化级)[）)])?", "345"
    elif category == "cs":
        pattern, valid = r"CS([1-5])级(?:[（(](?:初始级|基本级|良好级|优秀级|杰出级)[）)])?", "12345"
    else:
        pattern, valid = r"([一二三四五壹贰叁肆伍12345])级(?:[（(]拓展级[）)])?", {"electronic": "12", "itss": "1234", "security": "123"}[category]
    match = re.fullmatch(pattern, text, re.I)
    if match:
        grade = digits.get(match[1], match[1])
        if grade in valid:
            return grade, "explicit_grade"
    return None, "grade_unconfirmed_or_conflicting"


def _sheets(content):
    with ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > 1500 or len(names) != len(set(names)) or sum(item.file_size for item in entries) > 50 * 1024 * 1024:
            raise ValueError("Workbook archive exceeds limits or has duplicate entries")
        for item in entries:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.flag_bits & 1:
                raise ValueError("Unsafe archive entry")
            if "vbaproject" in item.filename.lower() or item.filename.startswith("xl/externalLinks/"):
                raise ValueError("Macros and external workbook links are unsupported")
        def xml(name):
            return ET.fromstring(archive.read(name), forbid_dtd=True, forbid_entities=True, forbid_external=True)
        shared = ["".join(node.itertext()) for node in xml("xl/sharedStrings.xml")] if "xl/sharedStrings.xml" in names else []
        relationships = {}
        for node in xml("xl/_rels/workbook.xml.rels"):
            if node.get("TargetMode") == "External":
                raise ValueError("External sheet relationship")
            target = node.get("Target", "")
            path = PurePosixPath(target.lstrip("/")) if target.startswith("/") else PurePosixPath("xl") / target
            if ".." in path.parts or "\\" in target:
                raise ValueError("Unsafe sheet relationship")
            relationships[node.get("Id")] = str(path)
        result = {}
        for sheet in xml("xl/workbook.xml").findall("s:sheets/s:sheet", NS):
            if sheet.get("state", "visible") != "visible":
                raise ValueError("Hidden source sheets require review")
            name = sheet.get("name", "")
            if name in result:
                raise ValueError("Duplicate source sheet name")
            rows = []
            seen = set()
            for row in xml(relationships[sheet.get(REL)]).findall("s:sheetData/s:row", NS):
                number = int(row.get("r", "0"))
                if number < 1 or number in seen:
                    raise ValueError("Invalid or duplicate source row")
                seen.add(number)
                cells = {}
                for cell in row.findall("s:c", NS):
                    ref = cell.get("r", "")
                    if not re.fullmatch(r"[A-Z]+[1-9][0-9]*", ref) or int(re.search(r"\d+", ref)[0]) != number:
                        raise ValueError("Invalid source cell address")
                    column = re.sub(r"\d", "", ref)
                    if column in cells or cell.find("s:f", NS) is not None or cell.get("t") in {"e", "b"}:
                        raise ValueError("Duplicate cell, formula, error or boolean requires review")
                    raw = cell.findtext("s:v", "", NS)
                    if cell.get("t") == "s":
                        raw = shared[int(raw)] if raw else ""
                    elif cell.get("t") == "inlineStr":
                        inline = cell.find("s:is", NS)
                        raw = "".join(inline.itertext()) if inline is not None else ""
                    if number >= 3 and column != "A" and raw and cell.get("t", "n") == "n":
                        raise ValueError("Source identifiers and phones must be text; leading zero cannot be reconstructed")
                    cells[column] = raw
                rows.append((number, cells))
            result[name] = rows
        return result


def normalize_workbook(path):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Workbook exceeds 20 MB")
    content = path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    sheets = _sheets(content)
    numbered = {}
    for name in sheets:
        match = re.fullmatch(r"([0-7])-.+", name)
        if not match or int(match[1]) in numbered:
            raise ValueError("Expected exactly one summary and seven numbered category sheets")
        numbered[int(match[1])] = name
    if set(numbered) != set(range(8)):
        raise ValueError("Missing summary or category sheet")
    summary, detail = [], defaultdict(deque)
    category_lookup = {re.sub(r"\s+", "", label): code for label, code in zip(CATEGORY_NAMES, CATEGORIES)}
    def records(index):
        name = numbered[index]
        rows = sheets[name]
        headers = SUMMARY_HEADERS if index == 0 else DETAIL_HEADERS
        expected = dict(zip("ABCDEFG", headers))
        if next((cells for number, cells in rows if number == 2), None) != expected:
            raise ValueError(f"Unexpected header row 2 in sheet {name}")
        for number, cells in rows:
            if number < 3 or not any(cells.values()):
                continue
            if any(col not in expected and value for col, value in cells.items()):
                raise ValueError("Nonempty unmapped source column")
            values = {field: cells.get(col, "") for col, field in expected.items()}
            category = category_lookup.get(re.sub(r"\s+", "", values.get("资质分类", ""))) if index == 0 else CATEGORIES[index - 1]
            if category is None or not normalized_name(values["企业名称"]):
                raise ValueError("Unknown source category or empty company name")
            record = {"region": values["地区"], "name": values["企业名称"], "raw_grade": values["资质等级"],
                      "city": values["所在城市"], "phone": values["联系电话"], "category": category}
            locator = {"sheet": name, "row": number, "cells": {f"{col}{number}": value for col, value in cells.items()}}
            yield record, locator
    def signature(record):
        # Exact original values: name normalization must not hide source mismatch.
        return _canonical(record)
    for index in range(1, 8):
        for record, locator in records(index):
            detail[signature(record)].append(locator)
    for record, locator in records(0):
        identity = signature(record)
        if not detail[identity]:
            raise ValueError(f"Summary/category multiset mismatch at {locator['sheet']}:{locator['row']}")
        summary.append((record, locator, detail[identity].popleft()))
    if any(detail.values()):
        raise ValueError("Category sheets contain unmatched extra rows or multiplicities")
    companies, claims, grouped = [], [], {}
    grade_decisions = Counter()
    for record, summary_locator, detail_locator in summary:
        name = normalized_name(record["name"])
        if name not in grouped:
            company = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "baichuan-source-name:" + name)), "name": name,
                       "original_names": [], "regions": [], "cities": [], "phones": [], "phone_candidates": [],
                       "source_rows": [], "identity_verified": False}
            grouped[name] = company
            companies.append(company)
        company = grouped[name]
        for key, raw in (("original_names", record["name"]), ("regions", record["region"]), ("cities", record["city"]), ("phones", record["phone"])):
            if raw not in company[key]:
                company[key].append(raw)
        company["source_rows"].append({"summary": summary_locator, "detail": detail_locator})
        if record["phone"] and not MISSING_PHONE.search(record["phone"]) and PHONE.search(record["phone"]):
            if record["phone"] not in company["phone_candidates"]:
                company["phone_candidates"].append(record["phone"])
        grade, decision = explicit_grade(record["category"], record["raw_grade"])
        grade_decisions[decision] += 1
        claims.append({"company_id": company["id"], "company_name": name, "category": record["category"],
                       "raw_category": summary_locator["cells"][f"C{summary_locator['row']}"], "raw_grade": record["raw_grade"],
                       "source_sheet": summary_locator["sheet"], "source_row": summary_locator["row"],
                       "source_rows": {"summary": summary_locator, "detail": detail_locator},
                       "proposed_grade": grade, "grade_decision": decision, "verification": "SOURCE_CLAIM_UNVERIFIED"})
    for company in companies:
        provinces = {region.strip() for region in company["regions"] if re.fullmatch(r"[\u4e00-\u9fff]{2,8}省", region.strip())}
        cities = {region.strip() for region in company["regions"] if re.fullmatch(r"[\u4e00-\u9fff]{2,8}市", region.strip())}
        cities |= {city.strip() for city in company["cities"] if city.strip() in CITY_LITERALS or city.strip().removesuffix("市") in CITY_LITERALS}
        company.update(province=next(iter(provinces)) if len(provinces) == 1 else None,
                       city=next(iter(cities)) if len(cities) == 1 else None,
                       phone_missing=not company["phone_candidates"])
        company["location_candidates"] = {"province": sorted(provinces), "city": sorted(cities)}
    audit = {"schema": 1, "source_sha256": file_hash, "source_bytes": len(content),
             "source_record_count": len(claims), "normalized_name_count": len(companies),
             "original_name_count": len({record["name"] for record, _, _ in summary}),
             "category_record_counts": dict(Counter(claim["category"] for claim in claims)),
             "multiset_verified": True, "multiset_sha256": hashlib.sha256(_canonical(sorted(signature(row) for row, _, _ in summary)).encode()).hexdigest(),
             "name_normalization": "whitespace_removed_ascii_fullwidth_parentheses_only",
             "identity_verified": False, "grade_decisions": dict(grade_decisions),
             "normalization_groups": [{"company_id": company["id"], "name": company["name"], "original_names": company["original_names"]}
                                      for company in companies if len(company["original_names"]) > 1],
             "source_sheet_rows": {name: len([1 for number, cells in rows if number >= 3 and any(cells.values())]) for name, rows in sheets.items()},
             "facts": 0, "verified_on": None, "database_writes": 0}
    if hashlib.sha256(path.read_bytes()).hexdigest() != file_hash:
        raise ValueError("Source workbook changed during normalization")
    return companies, claims, [], audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    options = parser.parse_args()
    source = Path(options.input).resolve(strict=True)
    target = Path(options.output_dir).resolve()
    if target.exists() or target == source or source.is_relative_to(target):
        raise ValueError("Output must be a fresh directory outside the input path")
    values = normalize_workbook(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".baichuan-source-", dir=target.parent) as temporary:
        staging = Path(temporary) / "result"
        staging.mkdir()
        for name, value in zip(("companies", "claims", "facts", "audit"), values):
            (staging / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(target)
    audit = values[-1]
    print(json.dumps({key: audit[key] for key in ("source_sha256", "source_record_count", "normalized_name_count", "multiset_verified", "database_writes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
