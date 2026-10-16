"""Pure, source-faithful conversion to reviewed-import rows; no database access."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


GRADES = {"electronic": ("1", "2"), "labor": (), "cs": ("1", "2", "3", "4", "5"),
          "cmmi": ("3", "4", "5"), "ccrc": ("1", "2", "3"),
          "itss": ("1", "2", "3", "4"), "security": ("1", "2", "3")}
LABELS = {"electronic": "电子与智能化工程专业承包", "labor": "施工劳务资质",
          "cs": "CS信息系统建设和服务能力等级认证", "cmmi": "CMMI软件能力成熟度模型",
          "ccrc": "CCRC信息系统安全集成服务", "itss": "ITSS信息技术运行维护服务符合性认证",
          "security": "安防工程企业设计施工维护能力"}
COMPANY_COLUMNS = dict(zip(
    ("公司名称（必填）", "统一社会信用代码", "省份", "城市", "办公地址", "官网首页", "公司电话", "业务联系人", "业务联系电话", "邮箱", "公司简介", "资料来源", "核实日期", "备注"),
    ("name", "credit_code", "province", "city", "address", "website", "phone", "contact_name", "contact_phone", "email", "description", "source", "verified_on", "notes")))
COMPANY_COLUMNS.update({label: category for category, label in LABELS.items()})
PERSON_COLUMNS = dict(zip(
    ("公司名称（必填）", "统一社会信用代码", "姓名（必填）", "部门", "岗位", "汇报对象", "专业方向", "职称与认证", "代表项目与成果", "资料来源", "核实日期", "备注"),
    ("company_name", "credit_code", "name", "department", "position", "reports_to_text", "specialties", "credentials", "achievements", "source", "verified_on", "notes")))
PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8}|(?:400|800)(?:[- ]?\d){7}|95\d{3,4}|100\d{2})(?:[-转]\d{1,5})?(?!\d)")
FIELD_LABELS = {"id": "原始企业编号", "name": "原始企业名称", "company_id": "所属企业编号", "company_name": "所属企业名称",
                "regions": "原表地区", "cities": "原表城市或区县", "phones": "原表全部电话及说明", "claims": "原表资质条目",
                "source_rows": "原表行号", "yulin": "原表标记榆林企业", "phone_missing": "原表电话缺失标记",
                "category": "类别", "grade": "等级原文", "row": "原表行号", "raw_category": "资质类别原文",
                "raw_grade": "资质等级原文", "source_sheet": "源工作表", "source_row": "源表行号",
                "proposed_grade": "整理时建议等级", "verification": "证据核验方式", "note": "原始说明", "notes": "补充说明",
                "kind": "资料类型", "value": "公开内容", "role": "公开用途或岗位", "person_name": "公开人员姓名或称谓",
                "source_url": "来源网址", "source_title": "来源标题", "source_kind": "来源类别", "source_date": "资料日期",
                "event_date": "事件日期", "evidence": "来源摘录或核验说明", "evidence_id": "证据编号",
                "partial_name": "是否为不完整姓名", "contact_type": "电话用途"}
ENUM_LABELS = {"verification": {"page_read": "已读来源页面（不等于现任职务或证书有效性确认）",
                                "search_snippet": "搜索摘要（尚未逐页核验）",
                                "SOURCE_CLAIM_UNVERIFIED": "原表声明，尚未逐证书核实"},
               "source_kind": {"official": "官方公开资料（主体见来源网址）", "government": "政府公开资料", "association": "行业协会",
                               "third_party": "第三方公开资料", "university": "高校公开资料", "official_procurement": "企业公开招采平台"},
               "kind": {"phone": "电话", "website": "网站", "person": "公开职业人员", "qualification": "资质补充说明",
                        "credit_code": "信用代码公开资料", "organization": "公开组织部门"}}
REASONS = {"CCRC_SCOPE_UNCONFIRMED": "原文未明确安全集成子类，仅保留原文待人工归类，不纳入安全集成筛选",
           "LABOR_NO_GRADE": "劳务资质不设置等级；A、AA、AAA等原表标记保留原文，不当作等级",
           "PRESENT_GRADE_UNSPECIFIED": "原表声明具备，但原文等级不能对应合法枚举，按具备、等级待补充保留",
           "SOURCE_GRADE_NORMALIZED": "按原文明确等级归一；仅为原表声明整理，未确认当前证书有效性"}


def bounded(value, limit, context):
    if len(value or "") > limit or "\x00" in (value or ""):
        raise ValueError(f"{context} 超过{limit}字或包含非法字符，拒绝截断来源")
    return value


def readable(value, indent=""):
    """Readable provenance, with unknown field names and all original values retained."""
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label = FIELD_LABELS.get(key, key)
            if isinstance(item, (dict, list)):
                lines.append(indent + label + "：\n" + readable(item, indent + "  "))
            else:
                meaning = ENUM_LABELS.get(key, {}).get(item) if isinstance(item, str) else None
                lines.append(indent + label + "：" + (meaning + "（" + item + "）" if meaning else readable(item)))
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return indent + "（空列表）"
        return "\n".join(indent + str(number) + ". " + readable(item, indent + "  ").lstrip() for number, item in enumerate(value, 1))
    if value is None:
        return "未提供（null）"
    if isinstance(value, bool):
        return "是（true）" if value else "否（false）"
    return str(value)


def _qualification(claim):
    category, raw = claim["category"], str(claim.get("raw_grade") or "")
    if category not in GRADES:
        raise ValueError(f"未知资质类别：{category}")
    if category == "ccrc" and "安全集成" not in raw:
        return None, "CCRC_SCOPE_UNCONFIRMED"
    grade = claim.get("proposed_grade")
    if category == "cs":
        match = re.search(r"CS\s*([1-5])", raw, re.I)
        grade = match[1] if match else grade
    if category == "ccrc":
        match = re.search(r"安全集成(?:服务)?\s*([一二三123])级", raw)
        grade = {"一": "1", "二": "2", "三": "3"}.get(match[1], match[1]) if match else None
    if category == "labor":
        grade, decision = None, "LABOR_NO_GRADE"
    elif grade not in GRADES[category]:
        grade, decision = None, "PRESENT_GRADE_UNSPECIFIED"
    else:
        decision = "SOURCE_GRADE_NORMALIZED"
    source = "源表声明，未经逐证书核实\n" + readable(claim) + "\n处理说明：" + REASONS[decision]
    return {"category": category, "status": "PRESENT", "grade": grade,
            "source": bounded(source, 19800, "资质来源"), "verified_on": None}, decision


def _homepage(fact):
    if fact.get("kind") != "website" or fact.get("source_kind") != "official":
        return None
    value = str(fact.get("value") or "")
    try:
        parsed = urlsplit(value)
        parsed.port
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/", "/index", "/index.html", "/index.php"}
                or "\\" in value or any(ord(char) <= 32 for char in value)):
            return None
    except ValueError:
        return None
    return bounded(value, 2000, "官网")


def _general_phone(fact):
    role = str(fact.get("role") or fact.get("contact_type") or "")
    return (fact.get("kind") == "phone" and fact.get("source_kind") == "official"
            and not fact.get("person_name") and not re.search(r"历史|招聘|项目|合同|办事处|研发中心|个人|证券|董事会|搜索片段", role)
            and bool(re.search(r"官网公开|企业公开联系电话|前台电话|公司热线|公司总机|公开企业联系电话", role)))


def _phones(company, facts):
    candidates = []
    if not company.get("phone_missing", False):
        for raw in company.get("phones", []):
            candidates.extend(match[0] for match in PHONE.finditer(str(raw)))
    for fact in facts:
        if _general_phone(fact):
            candidates.extend(match[0] for match in PHONE.finditer(str(fact.get("value") or "")))
    values, selected = list(dict.fromkeys(candidates)), []
    for value in values:
        if len("；".join([*selected, value])) > 100:
            break
        selected.append(value)
    return "；".join(selected) or None, values[len(selected):]


def convert_source(companies, claims, facts, audit):
    """Return text-only worksheet rows plus explicit, unconfirmed import mapping."""
    if not all(isinstance(value, list) for value in (companies, claims, facts)) or not isinstance(audit, dict):
        raise ValueError("企业、声明、证据须为数组，源表审计须为对象")
    by_id, by_name = {}, set()
    for company in companies:
        identifier, name = company["id"], bounded(company["name"], 200, "公司名称")
        if not identifier or not name.strip() or identifier in by_id or name in by_name:
            raise ValueError("企业ID或名称为空/重复；不能静默合并")
        by_id[identifier], by_name = company, by_name | {name}
    grouped_claims, grouped_facts = defaultdict(list), defaultdict(list)
    for rows, grouped, label in ((claims, grouped_claims, "声明"), (facts, grouped_facts, "证据")):
        for row in rows:
            if row["company_id"] not in by_id:
                raise ValueError(f"{label}引用未知企业：{row['company_id']}")
            grouped[row["company_id"]].append(row)
    for key, actual in (("normalized_name_count", len(companies)), ("source_record_count", len(claims))):
        if audit.get(key, actual) != actual:
            raise ValueError(f"源表审计数量不一致：{key}")
    mapping = {"company_sheet": "企业资料", "people_sheet": "核心人员", "company_columns": COMPANY_COLUMNS,
               "people_columns": PERSON_COLUMNS, "company_links": {}, "people_links": {},
               "qualification_overrides": {}, "notes_reviewed": {}}
    company_rows, person_rows, decisions, row_ids, overflow = [], [], [], {}, []
    for number, company in enumerate(companies, 2):
        identifier, name = company["id"], company["name"]
        own_claims, own_facts = grouped_claims[identifier], grouped_facts[identifier]
        source_key = f"企业资料:{number}"
        row_ids[identifier] = source_key
        qualifications, lines = [], ["源表资质声明（尚未逐证书核实；等级不代表当前有效性）"]
        for claim in own_claims:
            item, decision = _qualification(claim)
            if item:
                qualifications.append(item)
            lines.append(f"{claim.get('source_sheet', '')}:{claim.get('source_row', '')}　{claim.get('raw_category', claim['category'])}：{claim.get('raw_grade', '')}；{REASONS[decision]}")
            decisions.append({"company_id": identifier, "source_row": claim.get("source_row"), "category": claim["category"],
                              "raw_grade": claim.get("raw_grade"), "decision": decision, "reason": REASONS[decision], "grade": item["grade"] if item else None})
        source = "源表文件校验值（SHA256）：" + str(audit.get("source_sha256") or "未提供") + "\n企业原始资料\n" + readable(company)
        source += "\n检索证据（保留全部网址、资料日期、电话用途与来源时点；非证书核实结论）\n" + "\n\n".join(readable(fact) for fact in own_facts)
        phone, rest = _phones(company, own_facts)
        if rest:
            overflow.append({"company_id": identifier, "omitted_from_phone_field": rest})
        fields = {"name": name, "city": "；".join(dict.fromkeys(company.get("regions", []))) or None,
                  "website": next((url for fact in own_facts if (url := _homepage(fact))), None), "phone": phone,
                  "description": bounded("\n".join(lines), 20000, f"{identifier}简介"),
                  "source": bounded(source, 19800, f"{identifier}来源")}
        bounded(fields["city"], 100, "源表地区")
        fields.update({item["category"]: "PRESENT" for item in qualifications})
        company_rows.append([fields.get(field) for field in COMPANY_COLUMNS.values()])
        mapping["qualification_overrides"][source_key] = qualifications
        for fact in own_facts:
            if fact.get("kind") != "person":
                continue
            person_name = bounded(str(fact.get("person_name") or fact.get("value") or ""), 100, "人员姓名")
            if not person_name.strip():
                raise ValueError(f"{identifier}人员姓名为空")
            role = str(fact.get("role") or "公开资料所列人员（职务未明）")
            if re.search(r"(?:先生|女士|小姐|经理|工)$", person_name):
                role += "（公开称谓，非完整具名核心人员）"
            person = {"company_name": name, "name": person_name, "position": bounded(role, 200, "人员岗位"),
                      "source": bounded("公开职业资料，任职现状待核实\n" + readable(fact), 19800, "人员来源")}
            person_rows.append([person.get(field) for field in PERSON_COLUMNS.values()])
            mapping["people_links"][f"核心人员:{len(person_rows) + 1}"] = source_key
    report = {"mode": "source_conversion_only", "confirmed": False, "database_writes": 0,
              "counts": {"companies": len(company_rows), "source_claims": len(claims), "qualifications": sum(map(len, mapping["qualification_overrides"].values())),
                         "source_facts": len(facts), "people": len(person_rows), "companies_with_phone": sum(bool(row[list(COMPANY_COLUMNS.values()).index("phone")]) for row in company_rows)},
              "decisions": dict(Counter(row["decision"] for row in decisions)), "claim_decisions": decisions,
              "phone_overflow": overflow, "company_row_ids": row_ids,
              "source_claims": claims, "source_facts": facts,
              "qualification_verified_on": None, "credit_codes_assigned": 0,
              "next_step": "用artifact-tool把sheets的headers和rows写为文本XLSX，再用既有import_baichuan预检；不自动确认manifest或apply。"}
    return {"schema": 1, "sheets": [{"name": "企业资料", "headers": list(COMPANY_COLUMNS), "rows": company_rows},
                                    {"name": "核心人员", "headers": list(PERSON_COLUMNS), "rows": person_rows}]}, mapping, report


def prepare_source(companies_path, claims_path, facts_path, audit_path, output_dir):
    inputs = [Path(value).resolve(strict=True) for value in (companies_path, claims_path, facts_path, audit_path)]
    output = Path(output_dir).resolve()
    targets = [output / name for name in ("rows.json", "mapping.json", "conversion-report.json")]
    if any(target in inputs or target.exists() for target in targets):
        raise ValueError("输出必须是新文件，不能覆盖源数据或已有转换结果")
    loaded = [json.loads(path.read_text(encoding="utf-8-sig")) for path in inputs]
    rows, mapping, report = convert_source(*loaded)
    report["input_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    output.mkdir(parents=True, exist_ok=True)
    for target, value in zip(targets, (rows, mapping, report)):
        with target.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return report
