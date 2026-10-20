"""Reviewed, offline, append-only maintenance of the six-sheet national catalog."""
import hashlib
import re
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .baichuan_import import _read_xlsx, canonical, digest
from .baichuan_models import Company, CompanyPerson, CompanyQualification, QUALIFICATION_GRADES
from .baichuan_service import BaichuanError, COMPANY_FIELDS, QUALIFICATION_FIELDS, require_access, validate_payload
from .baichuan_source_workbook import normalized_name
from .models import AuditEvent

SHEETS = dict(zip(("1-电子与智能化", "2-CS信息系统", "3-CMMI", "4-CCRC信息安全", "5-ITSS运维符合性", "6-安防工程"),
                  ("electronic", "cs", "cmmi", "ccrc", "itss", "security")))
HEADERS = ("序号", "企业名称", "地区", "资质等级", "服务方向/备注", "证书编号/统一社会信用代码", "证书状态", "来源平台", "来源链接", "核验日期")
ACTION = "baichuan_national_import"
NOTICE = "用户提供名录声明；未联网核实，PRESENT不代表证书当前有效；原始状态及核验日期仅为来源原文。"
PROVINCES = ("河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾")
REGIONS = {**{name: name + "省" for name in PROVINCES}, **{name + "省": name + "省" for name in PROVINCES},
           **{name: name + "市" for name in ("北京", "天津", "上海", "重庆")},
           **{name + "市": name + "市" for name in ("北京", "天津", "上海", "重庆")},
           "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区", "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
           "香港": "香港特别行政区", "澳门": "澳门特别行政区"}
REGIONS.update({value: value for value in list(REGIONS.values())})


def _fail(detail):
    raise BaichuanError("national_import_conflict", detail, 409)


def _id(file_hash, key, kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan-national:{file_hash}:{key}:{kind}"))


def _region(raw):
    """Split explicit provinces; preserve city-only text without guessing province."""
    raw = raw.strip()
    province, separator, city = raw.partition("-")
    province = REGIONS.get(province.strip())
    if province:
        city = city.strip() if separator else ""
        if province in {"北京市", "天津市", "上海市", "重庆市"} and city in {province, province[:-1], "市辖区"}:
            city = ""
        return province, city or None
    for prefix in sorted(REGIONS, key=len, reverse=True):
        if raw.startswith(prefix) and raw[len(prefix):].endswith(("市", "自治州", "地区", "盟")):
            return REGIONS[prefix], raw[len(prefix):]
    return None, raw or None


def read_catalog(path):
    """Pure parsing: all nonempty cells, exact sheet/row and file hash survive."""
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("工作簿大小超过20MB")
    content = path.read_bytes()
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("工作簿大小超过20MB")
    file_hash = hashlib.sha256(content).hexdigest()
    sheets, epoch = _read_xlsx(BytesIO(content))
    if set(sheets) - set(SHEETS) - {"核验入口"} or set(SHEETS) - set(sheets):
        raise ValueError("全国名录必须包含约定的六类工作表，仅允许附加核验入口页")
    if any(cell["invalid"] for rows in sheets.values() for _, cells in rows for cell in cells.values()):
        raise ValueError("名录包含公式、错误或布尔单元格，拒绝执行")
    rows, companies = [], {}
    for sheet, category in SHEETS.items():
        headers = HEADERS[:7] + ("评估机构",) + HEADERS[7:] if category in {"itss", "security"} else HEADERS
        columns = dict(zip("ABCDEFGHIJK", headers))
        actual = {column: cell["value"] for number, cells in sheets[sheet] if number == 4 for column, cell in cells.items() if cell["value"]}
        if actual != columns:
            raise ValueError(f"{sheet}第4行表头与约定不符")
        for number, cells in sheets[sheet]:
            if number < 5 or not any(cell["value"] for cell in cells.values()):
                continue
            if any(column not in columns and cell["value"] for column, cell in cells.items()):
                raise ValueError(f"{sheet}:{number}存在无标题非空列")
            raw = {header: cells[column]["value"] for column, header in columns.items() if column in cells and cells[column]["value"]}
            if any(any(ord(char) < 32 and char not in "\t\n\r" for char in value) for value in raw.values()):
                raise ValueError(f"{sheet}:{number}包含非法控制字符")
            name = raw.get("企业名称", "")
            key = normalized_name(name)
            if not key:
                raise ValueError(f"{sheet}:{number}缺少企业名称")
            source = {"file_name": path.name, "file_sha256": file_hash, "sheet": sheet, "row": number, "raw": raw, "notice": NOTICE}
            date_column = "K" if category in {"itss", "security"} else "J"
            date_cell = cells.get(date_column, {})
            if date_cell.get("value") and date_cell.get("type") == "n":
                numeric = float(date_cell["value"])
                if not numeric.is_integer() or numeric < 61:
                    raise ValueError(f"{sheet}:{number}来源日期无效")
                source["source_date"] = (epoch + timedelta(days=int(numeric))).isoformat()
            text = canonical(source)
            grade_raw = raw.get("资质等级", "")
            grade = {"一级": "1", "二级": "2", "三级": "3", "四级": "4", "五级": "5", "CS1级": "1", "CS1级（初始级）": "1"}.get(grade_raw)
            if grade is None and re.fullmatch(r"(?:CS[1-5]|ML[345])", grade_raw):
                grade = grade_raw[-1]
            outside = (category == "ccrc" and grade_raw == "安全运维服务（等级未公示）") or (category == "itss" and grade_raw == "通用要求")
            if not outside and grade not in QUALIFICATION_GRADES[category]:
                raise ValueError(f"{sheet}:{number}等级无法明确归一")
            value = raw.get("证书编号/统一社会信用代码")
            scope = raw.get("服务方向/备注", "")
            if not outside and ((category == "ccrc" and "安全集成" not in scope and not re.fullmatch(r"CCRC-\d{4}-ISV-SI-\d+", value or ""))
                                or (category == "itss" and "运行维护" not in scope and not (value or "").startswith("ITSS-YW-"))):
                raise ValueError(f"{sheet}:{number}对应安全集成/运行维护范围不明确")
            certificate = None if category == "electronic" or outside else value
            patterns = {"cs": r"CS[1-5]-\d{4}-\d+", "cmmi": r"\d{1,30}", "ccrc": r"CCRC-\d{4}-ISV-SI-\d+",
                        "itss": r"ITSS-YW-(?:[1-4]|YH)-[A-Za-z0-9-]+", "security": r"ZAX-NP ?\d+(?:-\d+)?"}
            if certificate and not re.fullmatch(patterns[category], certificate):
                certificate = None
            credit = value if category == "electronic" else None
            if credit and not re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", credit):
                raise ValueError(f"{sheet}:{number}统一社会信用代码格式无效")
            qualification = None if outside else validate_payload({"company": {"name": name}, "qualifications": [{
                "category": category, "status": "PRESENT", "grade": grade, "certificate_no": certificate, "source": text}]})["qualifications"][0]
            if qualification:
                qualification["id"] = _id(file_hash, f"{sheet}:{number}", "qualification")
            item = {"sheet": sheet, "row": number, "name_key": key, "source": source, "qualification": qualification}
            rows.append(item)
            if key not in companies:
                province, city = _region(raw.get("地区", ""))
                company = validate_payload({"company": {"name": name, "province": province, "city": city}})["company"]
                companies[key] = {"id": _id(file_hash, f"{sheet}:{number}", "company"), "company": company, "rows": []}
            record = companies[key]
            if credit:
                if record["company"]["credit_code"] not in (None, credit):
                    raise ValueError("同名企业信用代码相互矛盾")
                record["company"]["credit_code"] = credit
            record["rows"].append(item)
    for record in companies.values():
        record["company"]["source"] = "\n".join(canonical(item["source"]) for item in record["rows"])
        validate_payload({"company": record["company"]})
    return {"file_sha256": file_hash, "rows": rows, "companies": companies,
            "counts": {"source_rows": len(rows), "source_companies": len(companies),
                       "source_qualifications": sum(item["qualification"] is not None for item in rows),
                       "source_only_rows": sum(item["qualification"] is None for item in rows),
                       "by_category": dict(Counter(SHEETS[item["sheet"]] for item in rows))}}


def _state():
    """Bind all company, qualification and personnel columns, including versions."""
    companies = list(Company.objects.order_by("id").values())
    qualifications = list(CompanyQualification.objects.order_by("id").values())
    state_hash = hashlib.sha256()
    for model, records in ((Company, companies), (CompanyQualification, qualifications),
                           (CompanyPerson, CompanyPerson.objects.order_by("id").values().iterator(chunk_size=500))):
        state_hash.update(model._meta.label.encode())
        for record in records:
            state_hash.update(canonical(record).encode())
            state_hash.update(b"\n")
    return companies, qualifications, state_hash.hexdigest()


def _plan(catalog, state):
    companies, qualifications, target_hash = state
    by_name, codes, by_company, by_id = defaultdict(list), {}, defaultdict(list), {}
    for company in companies:
        by_name[normalized_name(company["name"])].append(company)
        by_id[str(company["id"])] = company
        if company["credit_code"]:
            codes[company["credit_code"]] = str(company["id"])
    qual_by_id = {str(row["id"]): row for row in qualifications}
    for qualification in qualifications:
        by_company[str(qualification["company_id"])].append(qualification)
    new, additions, bumps, links, source_only, source_updates = [], [], {}, [], [], {}
    for key, record in catalog["companies"].items():
        matches = by_name.get(key, [])
        if len(matches) > 1:
            _fail("规范名称对应多个现有企业，拒绝整批导入")
        existing = matches[0] if matches else None
        company_id = str(existing["id"]) if existing else record["id"]
        credit = record["company"]["credit_code"]
        if credit and codes.get(credit, company_id) != company_id:
            _fail("来源信用代码指向不同企业，拒绝自动合并")
        if credit:
            codes[credit] = company_id
        if existing and credit and existing["credit_code"] not in (None, "", credit):
            _fail("同名现有企业信用代码与来源冲突")
        if not existing:
            if record["id"] in by_id:
                _fail("稳定企业ID被不同名称占用")
            new.append({"id": company_id, **record["company"]})
        else:
            links.append({"name_key": key, "company_id": company_id})
            if company_id == record["id"] and any(existing[field] != record["company"][field] for field in COMPANY_FIELDS):
                _fail("本批已导入企业内容发生变化，禁止覆写")
        for row in record["rows"]:
            if row["qualification"] is None:
                source_only.append({"company_id": company_id, "stored_in": "company.source", "source": row["source"]})
                if existing and company_id != record["id"]:
                    marker = f"[baichuan-national-source:{catalog['file_sha256']}:{row['sheet']}:{row['row']}]"
                    addition = marker + "\n" + canonical(row["source"])
                    current_source = source_updates.get(company_id, existing["source"]) or ""
                    if marker in current_source:
                        if current_source.count(marker) != 1 or addition not in current_source:
                            _fail("本批仅来源记录已发生变化，拒绝覆写")
                    else:
                        source_updates[company_id] = current_source + ("\n\n" if current_source else "") + addition
                        bumps[company_id] = existing["version"]
                continue
            expected = {"company_id": company_id, **row["qualification"]}
            current = qual_by_id.get(expected["id"])
            if current:
                if str(current["company_id"]) != company_id or any(current[field] != expected[field] for field in QUALIFICATION_FIELDS):
                    _fail("稳定资质ID的现有内容已变化，拒绝覆写")
                continue
            if any(item["category"] == expected["category"] and item["status"] != "PRESENT" for item in by_company[company_id]):
                _fail("现有同类资质为UNKNOWN或ABSENT，拒绝整批追加")
            additions.append(expected)
            if existing:
                bumps[company_id] = existing["version"]
    counts = {**catalog["counts"], "new_companies": len(new), "linked_companies": len(links), "add_qualifications": len(additions), "version_updates": len(bumps), "source_updates": len(source_updates)}
    plan = {"new": new, "additions": additions, "bumps": bumps, "links": links, "source_only_links": source_only, "source_updates": source_updates}
    return plan, counts, digest(plan), target_hash


def _manifest(catalog, state):
    plan, counts, plan_hash, target_hash = _plan(catalog, state)
    result = {"schema": 1, "mode": "preview", "confirmed": False, "file_sha256": catalog["file_sha256"],
              "target_sha256": target_hash, "plan_sha256": plan_hash, "counts": counts,
              "source_only_links": plan["source_only_links"], "notice": NOTICE}
    result["manifest_sha256"] = _manifest_digest(result)
    return result, plan


def _manifest_digest(manifest):
    return digest({key: manifest[key] for key in ("schema", "file_sha256", "target_sha256", "plan_sha256", "counts", "source_only_links", "notice")})


def preview_catalog(path):
    """SELECT-only preview; caller privately saves and explicitly confirms manifest."""
    catalog = read_catalog(path)
    with transaction.atomic():
        return _manifest(catalog, _state())[0]


def apply_catalog(path, manifest, actor):
    """One atomic append, CAS old versions; identical verified replay makes zero writes."""
    actor.refresh_from_db()
    require_access(actor, write=True)
    if not actor.is_active or actor.must_change_password:
        raise BaichuanError("baichuan_forbidden", "维护账号必须启用且已完成密码变更", 403)
    if not isinstance(manifest, dict) or manifest.get("confirmed") is not True or manifest.get("schema") != 1:
        _fail("需要明确确认的预检清单")
    if _manifest_digest(manifest) != manifest.get("manifest_sha256"):
        _fail("预检清单摘要不匹配")
    catalog = read_catalog(path)
    if catalog["file_sha256"] != manifest["file_sha256"]:
        _fail("原文件已在预检后变化")
    with transaction.atomic():
        # Lock the same parent rows used by normal editing; SQLite serializes at write.
        list(Company.objects.select_for_update().order_by("id").values_list("id", flat=True))
        fresh, plan = _manifest(catalog, _state())
        prior = AuditEvent.objects.filter(action=ACTION, target=catalog["file_sha256"]).first()
        if prior:
            if fresh["target_sha256"] != prior.changes["target_after_sha256"] or plan["new"] or plan["additions"] or plan["source_updates"]:
                _fail("已导入批次的目标内容已变化，不能以重放覆盖")
            if manifest["manifest_sha256"] not in {prior.changes["manifest_sha256"], fresh["manifest_sha256"]}:
                _fail("重放清单与本批次不符")
            return {"mode": "apply", "database_status": "unchanged", "replayed": True, "file_sha256": catalog["file_sha256"],
                    "counts": fresh["counts"], "source_only_links": fresh["source_only_links"], "notice": NOTICE}
        if fresh["manifest_sha256"] != manifest["manifest_sha256"]:
            _fail("目标资料已在预检后变化，须重新预检")
        actor.refresh_from_db()
        require_access(actor, write=True)
        if not actor.is_active or actor.must_change_password:
            raise BaichuanError("baichuan_forbidden", "维护账号状态已变化", 403)
        now = timezone.now()
        for company_id, version in plan["bumps"].items():
            values = {"source": plan["source_updates"][company_id]} if company_id in plan["source_updates"] else {}
            if Company.objects.filter(pk=company_id, version=version).update(version=F("version") + 1, updated_by=actor, updated_at=now, **values) != 1:
                _fail("追加资质时企业版本已变化")
        Company.objects.bulk_create([Company(**item, created_by=actor, updated_by=actor) for item in plan["new"]], batch_size=500)
        CompanyQualification.objects.bulk_create([CompanyQualification(**item) for item in plan["additions"]], batch_size=500)
        after_hash = _state()[2]
        AuditEvent.objects.create(actor=actor, action=ACTION, target=catalog["file_sha256"], changes={
            "manifest_sha256": manifest["manifest_sha256"], "target_before_sha256": manifest["target_sha256"], "target_after_sha256": after_hash,
            "fields": ["Company.insert", "CompanyQualification.insert", "Company.source.append", "Company.version", "Company.updated_by", "Company.updated_at"]})
        return {"mode": "apply", "database_status": "committed", "replayed": False, "file_sha256": catalog["file_sha256"],
                "target_after_sha256": after_hash, "counts": fresh["counts"], "source_only_links": fresh["source_only_links"], "notice": NOTICE}
