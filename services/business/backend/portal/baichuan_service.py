"""One permission boundary, exact qualification queries and atomic snapshots."""
import re
import uuid
from datetime import date
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from .baichuan_models import Company, CompanyPerson, CompanyQualification, QUALIFICATION_GRADES, WEBSITE_KINDS
from .product_service import product_user_allowed
from .security import audit, is_business_manager

COMPANY_FIELDS = ("name", "credit_code", "province", "city", "address", "website", "website_kind", "phone", "contact_name", "contact_phone", "email", "description", "source", "verified_on")
QUALIFICATION_FIELDS = ("category", "status", "grade", "certificate_no", "valid_until", "source", "verified_on")
PERSON_FIELDS = ("name", "department", "position", "reports_to_text", "specialties", "credentials", "achievements", "source", "verified_on")


class BaichuanError(Exception):
    def __init__(self, code, detail, status=400, errors=None):
        super().__init__(detail)
        self.code, self.detail, self.status, self.errors = code, detail, status, errors or {}


def invalid(field, detail):
    raise BaichuanError("invalid_request", detail, errors={field: detail})


def can_access(user, write=False):
    if not getattr(settings, "PORTAL_BAICHUAN_SCOPE_CONFIRMED", False) or not product_user_allowed(user):
        return False
    if not (is_business_manager(user) or user.roles.filter(code="product").exists()):
        return False
    readers = {str(value) for value in getattr(settings, "PORTAL_BAICHUAN_READ_USER_IDS", ())}
    writers = {str(value) for value in getattr(settings, "PORTAL_BAICHUAN_WRITE_USER_IDS", ())}
    read_roles = set(getattr(settings, "PORTAL_BAICHUAN_READ_ROLE_CODES", ())) & {"product", "general_manager"}
    read_allowed = str(user.pk) in readers or user.roles.filter(code__in=read_roles).exists()
    if not read_allowed or not write:
        return read_allowed
    write_roles = set(getattr(settings, "PORTAL_BAICHUAN_WRITE_ROLE_CODES", ())) & {"product", "general_manager"}
    return str(user.pk) in writers or user.roles.filter(code__in=write_roles).exists()


def require_access(user, write=False):
    if not can_access(user, write):
        raise BaichuanError("baichuan_forbidden", "没有百川阁维护权限。" if write else "没有百川阁访问权限。", 403)


def company_for(user, company_id, *, lock=False):
    # Deny object reads uniformly, including objects that do not exist.
    if not can_access(user):
        raise BaichuanError("not_found", "公司不存在或不可访问。", 404)
    try:
        rows = Company.objects.select_for_update() if lock else Company.objects.all()
        return rows.get(pk=company_id)
    except (Company.DoesNotExist, ValueError, TypeError, ValidationError):
        raise BaichuanError("not_found", "公司不存在或不可访问。", 404) from None


def _object(value, fields, required, path):
    if not isinstance(value, dict):
        invalid(path, "必须提交 JSON 对象。")
    if set(value) - set(fields) or set(required) - set(value):
        invalid(path, "字段不完整或包含不支持的字段。")


def _fields(value, model, fields, required, path):
    _object(value, (*fields, "id") if path != "company" else fields, required, path)
    result = {}
    for field in fields:
        item, key = value.get(field), f"{path}.{field}"
        if field in ("verified_on", "valid_until"):
            if item is not None:
                if not isinstance(item, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item):
                    invalid(key, "日期必须为 YYYY-MM-DD 或 null。")
                try:
                    item = date.fromisoformat(item)
                except ValueError:
                    invalid(key, "日期无效。")
        else:
            maximum = model._meta.get_field(field).max_length or 20000
            if item is not None and (not isinstance(item, str) or len(item) > maximum or "\x00" in item):
                invalid(key, f"请填写不超过 {maximum} 字的文本或 null。")
            item = item.strip() or None if isinstance(item, str) else item
        result[field] = item
    return result


def validate_payload(payload, company=None):
    """Pure normalization/validation; existing child ownership is read, never written."""
    update = company is not None
    required = ("company", "qualifications", "people", "expected_version") if update else ("company",)
    _object(payload, ("company", "qualifications", "people", "expected_version"), required, "payload")
    data = _fields(payload["company"], Company, COMPANY_FIELDS, tuple(field for field in COMPANY_FIELDS if field != "website_kind") if update else ("name",), "company")
    # Older full snapshots omit this field; preserve an existing classified homepage.
    data["website_kind"] = data["website_kind"] or (company.website_kind if update else "corporate")
    if data["website_kind"] not in WEBSITE_KINDS:
        invalid("company.website_kind", "请选择企业独立官网、集团专属介绍页或官方公众号。")
    if not data["name"]:
        invalid("company.name", "公司名称必填。")
    if data["credit_code"] and not re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", data["credit_code"]):
        invalid("company.credit_code", "统一社会信用代码须为18位大写字母或数字。")
    if data["website"]:
        try:
            value = data["website"]
            parsed = urlsplit(value)
            parsed.port
            URLValidator(schemes=["http", "https"])(value)
            if parsed.username is not None or parsed.password is not None or "\\" in value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
                raise ValueError
        except (ValidationError, ValueError):
            invalid("company.website", "官网须为合法 HTTP(S) 地址，且不能包含凭据。")
    if data["email"]:
        try:
            validate_email(data["email"])
        except ValidationError:
            invalid("company.email", "邮箱格式无效。")
    result = {"company": data}
    if "expected_version" in payload:
        version = payload["expected_version"]
        if type(version) is not int or not 1 <= version <= 2147483647:
            invalid("expected_version", "预期版本须为正整数。")
        if update and version != company.version:
            raise BaichuanError("version_conflict", "资料已被更新，请重新获取并人工核对。", 409)
        result["expected_version"] = version
    for key, model, fields, required in (("qualifications", CompanyQualification, QUALIFICATION_FIELDS, ("category", "status")), ("people", CompanyPerson, PERSON_FIELDS, ("name",))):
        rows = payload.get(key, [])
        if not isinstance(rows, list) or len(rows) > 1000:
            invalid(key, "须为不超过1000条的数组。")
        result[key], seen_ids = [], set()
        owned = set(str(value) for value in getattr(company, key).values_list("id", flat=True)) if update else set()
        for index, row in enumerate(rows):
            path = f"{key}.{index}"
            clean = _fields(row, model, fields, required, path)
            if "id" in row:
                try:
                    child_id = str(uuid.UUID(row["id"]))
                except (ValueError, TypeError, AttributeError):
                    invalid(f"{path}.id", "子项ID无效。")
                if child_id not in owned or child_id in seen_ids:
                    invalid(f"{path}.id", "子项ID重复或不属于此公司。")
                seen_ids.add(child_id)
                clean["id"] = child_id
            if key == "people" and not clean["name"]:
                invalid(f"{path}.name", "人员姓名必填。")
            if key == "qualifications":
                category, status, grade = clean["category"], clean["status"], clean["grade"]
                if category not in QUALIFICATION_GRADES or status not in ("UNKNOWN", "ABSENT", "PRESENT"):
                    invalid(path, "资质类别或状态无效。")
                if grade is not None and (status != "PRESENT" or grade not in QUALIFICATION_GRADES[category]):
                    invalid(f"{path}.grade", "此类别和状态不接受该等级。")
            result[key].append(clean)
    states, records, certificates = {}, set(), set()
    for row in result["qualifications"]:
        category = row["category"]
        states.setdefault(category, set()).add(row["status"])
        if len(states[category]) > 1:
            invalid("qualifications", "同类别存在相互矛盾的具备状态，请人工核对。")
        fingerprint = tuple(row[field] for field in QUALIFICATION_FIELDS)
        certificate = (category, row["certificate_no"])
        if fingerprint in records or row["certificate_no"] and certificate in certificates:
            invalid("qualifications", "存在重复资质记录或证书编号。")
        records.add(fingerprint)
        certificates.add(certificate)
    return result


def parse_query(params):
    allowed = {"q", "page", "page_size", *QUALIFICATION_GRADES}
    for key in params:
        if key not in allowed or len(params.getlist(key)) != 1:
            invalid(key, "未知或重复的查询参数。")
    q = params.get("q", "").strip()
    if len(q) > 200 or "\x00" in q:
        invalid("q", "名称搜索内容过长或无效。")
    result = {"q": q, "filters": {}}
    for key, default, maximum in (("page", 1, 2147483647), ("page_size", 20, 100)):
        value = params.get(key, str(default))
        if not re.fullmatch(r"[1-9][0-9]{0,9}", value) or int(value) > maximum:
            invalid(key, "分页须为合法正整数，页长不超过100。")
        result[key] = int(value)
    for category, grades in QUALIFICATION_GRADES.items():
        if category not in params:
            continue
        values = params[category].split(",")
        if values == ["any"]:
            result["filters"][category] = ["any"]
        elif not values or any(value not in grades for value in values):
            invalid(category, "请选择此类别的合法等级或单独使用 any。")
        else:
            result["filters"][category] = [grade for grade in grades if grade in values]
    return result


def _serialized(row, fields):
    result = {"id": str(row.pk)}
    for field in fields:
        value = getattr(row, field)
        result[field] = value.isoformat() if isinstance(value, date) else value
    return result


def company_detail(company, user):
    data = _serialized(company, COMPANY_FIELDS)
    data.update(version=company.version, created_at=company.created_at.isoformat(), updated_at=company.updated_at.isoformat())
    return {"company": data, "qualifications": [_serialized(row, QUALIFICATION_FIELDS) for row in company.qualifications.all()],
            "people": [_serialized(row, PERSON_FIELDS) for row in company.people.all()], "permissions": {"can_edit": can_access(user, True)}}


def list_companies(user, params):
    require_access(user)
    query = parse_query(params)
    rows = Company.objects.all()
    if query["q"]:
        rows = rows.filter(name__icontains=query["q"])
    for category, grades in query["filters"].items():
        matches = CompanyQualification.objects.filter(company_id=OuterRef("pk"), category=category, status="PRESENT")
        if grades != ["any"]:
            matches = matches.filter(grade__in=grades)
        rows = rows.filter(Exists(matches))
    total = rows.count()
    start = (query["page"] - 1) * query["page_size"]
    items = []
    for row in rows.order_by("name", "id").prefetch_related("qualifications")[start:start + query["page_size"]]:
        item = _serialized(row, ("name", "province", "city", "website", "website_kind", "phone", "contact_name", "contact_phone", "email"))
        qualifications = [_serialized(value, QUALIFICATION_FIELDS) for value in row.qualifications.all()]
        item["qualifications"] = qualifications
        item["matched_qualification_ids"] = [value["id"] for value in qualifications if value["status"] == "PRESENT"
            and value["category"] in query["filters"] and (query["filters"][value["category"]] == ["any"] or value["grade"] in query["filters"][value["category"]])]
        items.append(item)
    return {"items": items, "total": total, "page": query["page"], "page_size": query["page_size"], "has_more": start + len(items) < total,
            "query": {"q": query["q"], "filters": query["filters"]}, "permissions": {"can_create": can_access(user, True)}}


def duplicate_name_warning(company):
    if Company.objects.filter(name=company.name).exclude(pk=company.pk).exists():
        return [{"code": "duplicate_name", "detail": "存在同名公司，请人工核对信用代码与资料，系统未合并。"}]
    return []


def save_company(user, payload, company_id=None):
    require_access(user, True)
    try:
        with transaction.atomic():
            company = company_for(user, company_id, lock=True) if company_id is not None else None
            data = validate_payload(payload, company)
            from .baichuan_facts import manual_snapshot, record_manual_changes
            before = manual_snapshot(company)
            code = data["company"]["credit_code"]
            if code and Company.objects.filter(credit_code=code).exclude(pk=company_id).exists():
                raise BaichuanError("duplicate_company", "统一社会信用代码已存在。", 409)
            if company is None:
                company = Company.objects.create(**data["company"], created_by=user, updated_by=user)
                action = "baichuan_create"
            else:
                # CAS acquires the row's write lock before touching any child snapshot.
                updated = Company.objects.filter(pk=company.pk, version=data["expected_version"]).update(
                    **data["company"], version=F("version") + 1, updated_by=user, updated_at=timezone.now())
                if not updated:
                    raise BaichuanError("version_conflict", "资料已被更新，请重新获取并人工核对。", 409)
                action = "baichuan_update"
            for key, model in (("qualifications", CompanyQualification), ("people", CompanyPerson)):
                kept = []
                for child in data[key]:
                    values = dict(child)
                    child_id = values.pop("id", None)
                    if child_id:
                        model.objects.filter(company=company, pk=child_id).update(**values)
                    else:
                        child_id = model.objects.create(company=company, **values).pk
                    kept.append(child_id)
                model.objects.filter(company=company).exclude(pk__in=kept).delete()
            audit(user, action, company.pk, changes=[*COMPANY_FIELDS, "qualifications", "people"])
            company.refresh_from_db()
            record_manual_changes(user, company, before)
            return company
    except IntegrityError:
        # Only the known unique constraint becomes a business conflict; other DB faults remain failures.
        code = payload.get("company", {}).get("credit_code") if isinstance(payload, dict) else None
        if code and Company.objects.filter(credit_code=code.strip()).exclude(pk=company_id).exists():
            raise BaichuanError("duplicate_company", "统一社会信用代码已存在。", 409) from None
        raise
