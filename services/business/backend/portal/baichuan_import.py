"""One-off, reviewed XLSX initialization. No workbook or business writes in preview."""
import hashlib
import copy
import json
import posixpath
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from django.db import transaction
from django.core.exceptions import ValidationError

from .baichuan_models import Company, CompanyPerson, CompanyQualification, QUALIFICATION_GRADES, QUALIFICATION_LABELS
from .baichuan_service import (BaichuanError, COMPANY_FIELDS, PERSON_FIELDS,
                               QUALIFICATION_FIELDS, require_access, validate_payload)
from .models import AuditEvent

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
COMPANY_HEADERS = dict(zip(
    ("公司名称（必填）", "统一社会信用代码", "省份", "城市", "办公地址", "官网首页", "公司电话", "业务联系人", "业务联系电话", "邮箱", "公司简介", "资料来源", "核实日期", "备注"),
    ("name", "credit_code", "province", "city", "address", "website", "phone", "contact_name", "contact_phone", "email", "description", "source", "verified_on", "notes")))
COMPANY_HEADERS.update({label.replace(" ", ""): category for category, label in QUALIFICATION_LABELS.items()})
PERSON_HEADERS = dict(zip(
    ("公司名称（必填）", "统一社会信用代码", "姓名（必填）", "部门", "岗位", "汇报对象", "专业方向", "职称与认证", "代表项目与成果", "资料来源", "核实日期", "备注"),
    ("company_name", "credit_code", "name", "department", "position", "reports_to_text", "specialties", "credentials", "achievements", "source", "verified_on", "notes")))
DEFAULT_MAPPING = {"company_sheet": "企业资料", "people_sheet": "核心人员",
                   "company_columns": COMPANY_HEADERS, "people_columns": PERSON_HEADERS,
                   "company_links": {}, "people_links": {}, "qualification_overrides": {}, "notes_reviewed": {}}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _issue(report, key, code, detail, **extra):
    report["issues"].append({"source": key, "code": code, "detail": detail, **extra})


def _read_xlsx(path):
    """Read values only; never evaluate formulas or open links."""
    with ZipFile(path) as book:
        if sum(item.file_size for item in book.infolist()) > 50 * 1024 * 1024:
            raise ValueError("工作簿解压大小超过50MB")
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = ["".join(item.itertext()) for item in ET.fromstring(book.read("xl/sharedStrings.xml"))]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        properties = workbook.find("m:workbookPr", NS)
        epoch = date(1904, 1, 1) if properties is not None and properties.get("date1904") in {"1", "true"} else date(1899, 12, 30)
        relationships = {item.get("Id"): item.get("Target") for item in ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            if sheet.get("name") in sheets:
                raise ValueError("工作簿有重复工作表名")
            target = relationships[sheet.get(REL)]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            rows = []
            seen_rows = set()
            for row in ET.fromstring(book.read(target)).findall("m:sheetData/m:row", NS):
                number = int(row.get("r"))
                if number < 1 or number in seen_rows:
                    raise ValueError("工作表行号非法或重复")
                seen_rows.add(number)
                cells = {}
                for cell in row.findall("m:c", NS):
                    reference = cell.get("r", "")
                    if not re.fullmatch(r"[A-Z]+[1-9][0-9]*", reference) or int(re.search(r"[0-9]+", reference)[0]) != number:
                        raise ValueError("单元格地址非法或不属于当前行")
                    kind = cell.get("t", "n")
                    raw = cell.findtext("m:v", "", NS)
                    if kind == "s":
                        raw = shared[int(raw)] if raw else ""
                    elif kind == "inlineStr":
                        inline = cell.find("m:is", NS)
                        raw = "".join(inline.itertext()) if inline is not None else ""
                    column = re.sub(r"\d", "", reference)
                    if column in cells:
                        raise ValueError("工作表有重复单元格地址")
                    cells[column] = {
                        "value": raw.strip(), "type": kind,
                        "invalid": cell.find("m:f", NS) is not None or kind in {"e", "b"}}
                rows.append((number, cells))
            sheets[sheet.get("name")] = rows
        return sheets, epoch


def _rows(sheets, sheet_name, columns, required, report, epoch):
    if sheet_name not in sheets:
        _issue(report, sheet_name, "missing_sheet", "缺少工作表")
        return []
    rows = sheets[sheet_name]
    headers = {col: cell["value"] for number, cells in rows if number == 1 for col, cell in cells.items()}
    if any(cell["invalid"] for number, cells in rows if number == 1 for cell in cells.values()):
        _issue(report, f"{sheet_name}:1", "invalid_header", "表头包含公式或错误值，须人工核对")
    fields = {col: columns.get(header) for col, header in headers.items()}
    if not required.issubset(set(fields.values())):
        _issue(report, sheet_name, "missing_columns", "缺少必需字段映射", fields=sorted(required - set(fields.values())))
    duplicates = [field for field in set(fields.values()) - {None} if list(fields.values()).count(field) > 1]
    if duplicates:
        _issue(report, sheet_name, "duplicate_columns", "多个列映射到同一字段", fields=duplicates)
    result = []
    for number, cells in rows:
        if number == 1 or not any(cell["value"] or cell["invalid"] for cell in cells.values()):
            continue
        key, values = f"{sheet_name}:{number}", {}
        for col, cell in cells.items():
            value, field = cell["value"], fields.get(col)
            if cell["invalid"]:
                _issue(report, key, "invalid_cell", "公式、错误值或布尔值须人工核对", cell=f"{col}{number}")
            if value and field is None:
                _issue(report, key, "unmapped_column", "非空列未映射，不能丢弃", cell=f"{col}{number}", value=value)
            if field:
                if value and cell["type"] == "n" and field in {"credit_code", "phone", "contact_phone"}:
                    _issue(report, key, "identifier_not_text", "信用代码和电话须保留为文本，无法恢复已丢失的前导零", field=field)
                if value and cell["type"] == "n" and field == "verified_on":
                    try:
                        numeric = float(value)
                        if not numeric.is_integer() or numeric < 0:
                            raise ValueError
                        if epoch == date(1899, 12, 30) and numeric <= 60:
                            if numeric == 60:
                                raise ValueError("Excel虚构的1900-02-29")
                            numeric += 1
                        value = (epoch + timedelta(days=int(numeric))).isoformat()
                    except (ValueError, OverflowError):
                        _issue(report, key, "invalid_date", "非法Excel日期", value=value)
                values[field] = value or None
        result.append((key, values))
        report["source_rows"].append({"source": key, "sheet": sheet_name, "row": number, "values": values})
    return result


def _source(original, key, file_hash, notes=None):
    return "\n".join(str(value) for value in (original, f"Excel SHA256={file_hash}; {key}", f"备注：{notes}" if notes else None) if value)


def _qualification(category, value):
    if not value:
        return None
    if value in {"UNKNOWN", "未知", "待核实", "未提供"}:
        return {"category": category, "status": "UNKNOWN", "grade": None}
    if value in {"ABSENT", "不具备"}:
        return {"category": category, "status": "ABSENT", "grade": None}
    if value in {"PRESENT", "具备", "具备（等级待补充）", "具备(等级待补充)"}:
        return {"category": category, "status": "PRESENT", "grade": None}
    grades = {"一级": "1", "二级": "2", "三级": "3", "四级": "4", "五级": "5"}
    grade = grades.get(value, value)
    if grade not in QUALIFICATION_GRADES[category]:
        raise ValueError(f"{category} 的等级或状态不合法：{value}；多等级须人工逐项归一")
    return {"category": category, "status": "PRESENT", "grade": grade}


def _snapshot(company):
    return {"id": str(company.id), "version": company.version,
            "company": {field: getattr(company, field) for field in COMPANY_FIELDS},
            "qualifications": sorted(({"id": str(item.id), **{field: getattr(item, field) for field in QUALIFICATION_FIELDS}}
                                      for item in company.qualifications.all()), key=lambda item: item["id"]),
            "people": sorted(({"id": str(item.id), **{field: getattr(item, field) for field in PERSON_FIELDS}}
                              for item in company.people.all()), key=lambda item: item["id"])}


def _content(snapshot, ignore_source=False):
    excluded = {"id", "source"} if ignore_source else {"id"}
    return {"company": {key: value for key, value in snapshot["company"].items() if key not in excluded}, **{
        group: sorted(({key: value for key, value in item.items() if key not in excluded} for item in snapshot[group]), key=canonical)
        for group in ("qualifications", "people")}}


def _validate_for_report(payload, key, report, person_sources):
    """The HTTP validator fails fast; preview must expose every invalid source field."""
    seen = set()

    def check(candidate, scope="company"):
        try:
            return validate_payload(candidate)
        except BaichuanError as error:
            identity = (scope, canonical(error.errors))
            if identity not in seen:
                seen.add(identity)
                source = person_sources[scope[1]] if isinstance(scope, tuple) and scope[0] == "people" else key
                _issue(report, source, error.code, error.detail, errors=error.errors)

    for field, value in payload["company"].items():
        check({"company": {"name": "预检字段校验", field: value}})
    for group, required in (("qualifications", ("category", "status")), ("people", ("name",))):
        rows = payload[group]
        if not isinstance(rows, list):
            check({"company": {"name": "预检字段校验"}, group: rows})
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                check({"company": {"name": "预检字段校验"}, group: [row]}, (group, index))
                continue
            for field, value in row.items():
                baseline = {name: row.get(name) for name in required}
                baseline[field] = value
                before = len(report["issues"])
                check({"company": {"name": "预检字段校验"}, group: [baseline]}, (group, index))
                if len(report["issues"]) > before:
                    report["issues"][-1].update(group=group, index=index)
    normalized = check(payload)
    return normalized if not seen else None


def preview_import(path, mapping=None):
    mapping = copy.deepcopy({**DEFAULT_MAPPING, **(mapping or {})})
    if set(mapping) != set(DEFAULT_MAPPING) or any(not isinstance(mapping[key], dict) for key in DEFAULT_MAPPING if key.endswith(("columns", "links", "overrides", "reviewed"))):
        raise ValueError("字段映射格式不合法")
    if set(mapping["company_columns"].values()) - set(COMPANY_FIELDS) - set(QUALIFICATION_GRADES) - {"notes"} or set(mapping["people_columns"].values()) - set(PERSON_FIELDS) - {"company_name", "credit_code", "notes"}:
        raise ValueError("字段映射包含未知目标字段")
    if Path(path).stat().st_size > 20 * 1024 * 1024:
        raise ValueError("工作簿大小超过20MB")
    file_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report = {"schema": 1, "mode": "dry_run", "confirmed": False, "file_sha256": file_hash,
              "mapping": mapping, "mapping_sha256": digest(mapping), "issues": [], "source_rows": [], "records": []}
    sheets, epoch = _read_xlsx(path)
    companies = _rows(sheets, mapping["company_sheet"], mapping["company_columns"], {"name"}, report, epoch)
    people = _rows(sheets, mapping["people_sheet"], mapping["people_columns"], {"company_name", "name"}, report, epoch)
    prepared = {}
    for key, values in companies:
        company = {field: values.get(field) for field in COMPANY_FIELDS}
        notes = values.get("notes")
        company["source"] = _source(company.get("source"), key, file_hash, notes)
        qualifications = []
        for category in QUALIFICATION_GRADES:
            if key in mapping["qualification_overrides"]:
                break
            try:
                item = _qualification(category, values.get(category))
                if item:
                    qualifications.append({**item, "source": company["source"], "verified_on": values.get("verified_on")})
            except ValueError as error:
                _issue(report, key, "invalid_qualification", str(error), field=category)
        if notes and mapping["notes_reviewed"].get(key) != notes:
            _issue(report, key, "notes_need_review", "备注须逐项人工核对；多份资质用 qualification_overrides 归一，notes_reviewed 保留原文确认", notes=notes)
        if key in mapping["qualification_overrides"]:
            qualifications = mapping["qualification_overrides"][key]
            if isinstance(qualifications, list):
                required_categories = {category for category in QUALIFICATION_GRADES if values.get(category)}
                supplied_categories = {item.get("category") for item in qualifications if isinstance(item, dict) and isinstance(item.get("category"), str)}
                if required_categories - supplied_categories:
                    _issue(report, key, "incomplete_qualification_override", "完整资质归一映射不能丢弃原表非空类别（含未知/不具备）", missing_categories=sorted(required_categories - supplied_categories))
                qualifications = [{**item, "source": _source(item.get("source"), key, file_hash, notes)} if isinstance(item, dict) else item for item in qualifications]
        prepared[key] = {"company": company, "qualifications": qualifications, "people": []}
    names = {}
    for key, payload in prepared.items():
        names.setdefault(payload["company"]["name"], []).append(key)
    for key, values in people:
        matches = [company_key for company_key in names.get(values.get("company_name"), [])
                   if not values.get("credit_code") or prepared[company_key]["company"]["credit_code"] == values["credit_code"]]
        explicit = mapping["people_links"].get(key)
        if explicit:
            matches = [explicit] if explicit in matches else []
        if len(matches) != 1:
            _issue(report, key, "ambiguous_person" if matches else "orphan_person", "人员必须唯一归属主表公司，不能凭重名自动合并", candidates=matches)
            continue
        if values.get("notes") and mapping["notes_reviewed"].get(key) != values["notes"]:
            _issue(report, key, "notes_need_review", "人员备注须人工确认，原文将保留在来源", notes=values["notes"])
        person = {field: values.get(field) for field in PERSON_FIELDS}
        person["source"] = _source(person.get("source"), key, file_hash, values.get("notes"))
        person["_source_key"] = key
        prepared[matches[0]]["people"].append(person)
    identities = {}
    for key, payload in prepared.items():
        name = payload["company"]["name"]
        same_name = names[name]
        if name and len(same_name) > 1 and any(not prepared[item]["company"]["credit_code"] for item in same_name):
            _issue(report, key, "ambiguous_company", "同名公司中存在缺失信用代码，须人工核对，不自动合并")
    for key, payload in prepared.items():
        for field in ("credit_code", "name"):
            value = payload["company"][field]
            if not value or field == "name" and payload["company"]["credit_code"]:
                continue
            identity = (field, value)
            if identity in identities:
                _issue(report, key, "duplicate_credit_code" if field == "credit_code" else "ambiguous_company", "主表重复标识须人工核对", other_source=identities[identity])
            identities[identity] = key
        person_sources = [item.pop("_source_key") for item in payload["people"]]
        normalized = _validate_for_report(payload, key, report, person_sources)
        if normalized is None:
            continue
        identifier = lambda suffix: str(uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan:{file_hash}:{report['mapping_sha256']}:{key}:{suffix}"))
        for index, item in enumerate(normalized["qualifications"]):
            item["id"] = identifier(f"qualification:{index}")
        for index, item in enumerate(normalized["people"]):
            item["id"] = identifier(f"person:{person_sources[index]}")
        for group in ("qualifications", "people"):
            normalized[group].sort(key=lambda item: item["id"])
        record = {"source": key, "id": identifier("company"), "version": 1,
                  **{group: normalized[group] for group in ("company", "qualifications", "people")}}
        linked = mapping["company_links"].get(key)
        if linked:
            try:
                current = Company.objects.get(pk=linked)
                snapshot = _snapshot(current)
                if digest(_content(snapshot, True)) != digest(_content(record, True)):
                    _issue(report, key, "linked_content_conflict", "明确关联的现有公司内容不同，禁止初始化覆盖")
                record.update(**snapshot, linked=True, link_note="仅关联已核对对象；原表现有来源在清单中保留，不覆盖数据库来源")
            except (Company.DoesNotExist, ValueError, ValidationError):
                _issue(report, key, "invalid_company_link", "明确关联的目标公司不存在")
        record["content_sha256"] = digest({field: value for field, value in record.items() if field != "source"})
        report["records"].append(json.loads(canonical(record)))
    _check_targets(report)
    report["manifest_sha256"] = digest({key: report[key] for key in ("schema", "file_sha256", "mapping_sha256", "records")})
    rejected = {item["source"] for item in report["issues"]}
    valid_ids = {item["id"] for item in report["records"] if item["source"] not in rejected}
    report["counts"] = {"companies": len(companies), "people": len(people), "valid_companies": len(valid_ids),
                        "rejected_companies": sum(key in rejected for key, _ in companies),
                        "create": sum(item.get("action") == "create" and item["id"] in valid_ids for item in report["targets"]),
                        "skip": sum(item.get("action") == "skip" and item["id"] in valid_ids for item in report["targets"]), "issues": len(report["issues"])}
    return report


def _check_targets(report, lock=False):
    report["targets"] = []
    query = Company.objects.select_for_update() if lock else Company.objects
    for record in report["records"]:
        current = query.filter(pk=record["id"]).first()
        if current:
            desired = {key: record[key] for key in ("id", "version", "company", "qualifications", "people")}
            if digest(_snapshot(current)) == digest(desired):
                report["targets"].append({"id": record["id"], "action": "skip", "linked": record.get("linked", False)})
                continue
            _issue(report, record["source"], "existing_content_conflict", "公司或子项已被修改，不能用初始化资料覆盖")
        elif record.get("linked"):
            _issue(report, record["source"], "missing_linked_company", "预检关联的公司已不存在")
        else:
            credit = record["company"].get("credit_code")
            duplicates = query.filter(credit_code=credit) if credit else query.filter(name=record["company"]["name"])
            if duplicates.exists():
                _issue(report, record["source"], "existing_company_conflict", "已有相同信用代码或无代码重名公司，须明确 company_links 并核对；不自动合并")
            else:
                report["targets"].append({"id": record["id"], "action": "create"})


def apply_import(path, manifest, user, mapping=None):
    require_access(user, write=True)
    if not isinstance(manifest, dict) or manifest.get("confirmed") is not True:
        raise BaichuanError("unconfirmed_manifest", "须人工核对预检清单并设置 confirmed=true")
    preview = preview_import(path, mapping if mapping is not None else manifest.get("mapping"))
    if any(preview[key] != manifest.get(key) for key in ("schema", "file_sha256", "mapping_sha256", "manifest_sha256")) or digest(manifest.get("records")) != digest(preview["records"]):
        raise BaichuanError("manifest_mismatch", "文件、映射、标准化内容或目标状态与已确认预检清单不符")
    if preview["issues"] or manifest.get("issues"):
        raise BaichuanError("import_conflicts", "预检存在未处理错误，整批零写入", errors=preview["issues"])
    with transaction.atomic():
        _check_targets(preview, lock=True)
        if preview["issues"]:
            raise BaichuanError("import_conflicts", "目标状态已变化，整批零写入", errors=preview["issues"])
        for record, target in zip(preview["records"], preview["targets"]):
            if target["action"] == "skip":
                continue
            normalized = validate_payload({key: record[key] if key == "company" else [
                {field: value for field, value in item.items() if field != "id"} for item in record[key]]
                for key in ("company", "qualifications", "people")})
            company = Company.objects.create(id=record["id"], created_by=user, updated_by=user, **normalized["company"])
            for group, model in (("qualifications", CompanyQualification), ("people", CompanyPerson)):
                for item, original in zip(normalized[group], record[group]):
                    model.objects.create(id=original["id"], company=company, **item)
            AuditEvent.objects.create(actor=user, action="baichuan.import", target=str(company.id), changes=["company", "qualifications", "people"])
    preview.update(mode="apply", database_status="committed", confirmed=True)
    preview["counts"].update(create=sum(item["action"] == "create" for item in preview["targets"]),
                             skip=sum(item["action"] == "skip" for item in preview["targets"]))
    return preview
