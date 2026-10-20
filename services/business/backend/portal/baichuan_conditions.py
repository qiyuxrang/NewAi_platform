"""Bounded condition language and conservative four-valued matching.

No model output is executable. Grade ordering comes only from an explicitly
versioned, sourced rule supplied by the caller; numeric grade order is never used.
"""
from copy import deepcopy
from datetime import date
import json

from .baichuan_rules_aliases import canonical_category


VERDICTS = {"satisfied", "failed", "unknown", "conflict"}
COMPANY_FIELDS = {"company.province": "province", "company.city": "city", "company.name": "name"}
OUTPUT_FIELDS = {"name", "province", "city", "website", "phone", "email", "credit_code", "address"}
HOLDERS = {"bidder", "consortium_member", "manufacturer", "person", "product"}


class ConditionError(ValueError):
    pass


def _object(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ConditionError("条件包含未知字段或缺少必要字段。")


def _text(value, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ConditionError("条件文本无效或超限。")
    return value


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ConditionError("日期必须为 YYYY-MM-DD。")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ConditionError("日期无效。") from None


def compile_conditions(payload, *, today=None):
    """Validate and normalize an untrusted tree, assigning stable local node IDs."""
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ConditionError("条件不是有效 JSON。") from None
    if len(encoded.encode("utf-8")) > 65536:
        raise ConditionError("条件大小超限。")
    _object(payload, {"schema_version", "revision", "source_refs", "as_of", "must", "should", "unresolved", "output"},
            {"schema_version", "revision", "must"})
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ConditionError("不支持的条件版本。")
    if type(payload["revision"]) is not int or not 1 <= payload["revision"] <= 100000:
        raise ConditionError("条件修订号无效。")
    result = deepcopy(payload)
    result.setdefault("source_refs", [])
    result.setdefault("should", [])
    result.setdefault("unresolved", [])
    for field in ("source_refs", "unresolved"):
        if not isinstance(result[field], list) or len(result[field]) > 100:
            raise ConditionError("来源或待澄清项超限。")
        for value in result[field]:
            _text(value, 1000)
    as_of = result.setdefault("as_of", {"date": (today or date.today()).isoformat(), "basis": "query_date"})
    _object(as_of, {"date", "basis"}, {"date", "basis"})
    _date(as_of["date"])
    if as_of["basis"] not in {"query_date", "tender_date", "user_date"}:
        raise ConditionError("日期依据无效。")
    output = result.setdefault("output", {"fields": ["name", "phone"], "limit": 20})
    _object(output, {"fields", "limit"}, {"fields", "limit"})
    if (not isinstance(output["fields"], list) or not output["fields"]
            or any(not isinstance(f, str) or f not in OUTPUT_FIELDS for f in output["fields"])
            or len(set(output["fields"])) != len(output["fields"])):
        raise ConditionError("导出字段无效。")
    if type(output["limit"]) is not int or not 1 <= output["limit"] <= 5000:
        raise ConditionError("结果数量必须在 1 至 5000 之间。")
    count = 0

    def visit(node, path, depth):
        nonlocal count
        count += 1
        if depth > 8 or count > 100:
            raise ConditionError("条件深度或数量超限。")
        if not isinstance(node, dict):
            raise ConditionError("条件节点必须是对象。")
        groups = set(node) & {"all", "any", "not"}
        if groups:
            if len(node) != 1 or len(groups) != 1:
                raise ConditionError("逻辑节点不能混入其他字段。")
            operator = next(iter(groups))
            if operator == "not":
                visit(node[operator], path + ".not", depth + 1)
            else:
                children = node[operator]
                if not isinstance(children, list) or not 1 <= len(children) <= 50:
                    raise ConditionError("逻辑条件必须包含 1 至 50 个子项。")
                for i, child in enumerate(children):
                    visit(child, f"{path}.{i}", depth + 1)
            return
        _object(node, {"field", "op", "value", "category", "holder", "source_refs", "rule_version", "scope"},
                {"field", "op", "value"})
        _text(node["field"])
        _text(node["op"])
        _text(node["value"])
        if node["field"] in COMPANY_FIELDS:
            if node["op"] != "eq" or set(node) & {"category", "holder", "scope", "rule_version"}:
                raise ConditionError("企业字段仅允许等值条件。")
        elif node["field"] == "qualification":
            if node["op"] not in {"grade_exact", "grade_at_least", "present"}:
                raise ConditionError("资质操作无效。")
            _text(node.get("category"), 100)
            node["category"] = canonical_category(node["category"])
            if node.get("holder") not in HOLDERS:
                raise ConditionError("必须明确证书主体。")
            if "scope" in node:
                _text(node["scope"])
            if "rule_version" in node:
                _text(node["rule_version"], 100)
        else:
            raise ConditionError("不支持的条件字段。")
        if "source_refs" in node:
            if not isinstance(node["source_refs"], list) or len(node["source_refs"]) > 30:
                raise ConditionError("条件来源无效。")
            for ref in node["source_refs"]:
                _text(ref, 1000)

    visit(result["must"], "must", 0)
    if not isinstance(result["should"], list) or len(result["should"]) > 30:
        raise ConditionError("优先条件无效或超限。")
    for i, node in enumerate(result["should"]):
        visit(node, f"should.{i}", 0)
    return result


def combine(operator, values):
    if not values or any(value not in VERDICTS for value in values):
        raise ConditionError("判定值无效。")
    if operator == "not":
        if len(values) != 1:
            raise ConditionError("NOT 仅允许一个值。")
        return {"satisfied": "failed", "failed": "satisfied"}.get(values[0], values[0])
    if operator == "all":
        if "failed" in values:
            return "failed"
        if all(v == "satisfied" for v in values):
            return "satisfied"
    elif operator == "any":
        if "satisfied" in values:
            return "satisfied"
        if all(v == "failed" for v in values):
            return "failed"
    else:
        raise ConditionError("逻辑操作无效。")
    return "conflict" if "conflict" in values else "unknown"


def _result(verdict, reason, evidence_ids=()):
    return {"verdict": verdict, "reason": reason, "evidence_ids": list(evidence_ids)}


def _certificate_verdict(node, company, certificate, as_of, rule):
    # Caller supplies evidence metadata loaded from trusted persisted records,
    # never directly from a model response or a search snippet.
    evidence_ids = certificate.get("evidence_ids", [])
    if certificate.get("holder_type") != node["holder"]:
        return _result("unknown", "证书主体类型不适用。", evidence_ids)
    if node["holder"] != "bidder":
        return _result("unknown", "尚未建立该主体与本次投标的结构化适用关系。", evidence_ids)
    if str(certificate.get("holder_company_id")) != str(company["id"]):
        return _result("unknown", "证书持有人未核实为该企业。", evidence_ids)
    if certificate.get("verification_status") == "conflict":
        return _result("conflict", "证书来源存在冲突。", evidence_ids)
    if rule.get("standard") and certificate.get("standard") != rule["standard"]:
        return _result("unknown", "证书适用标准与等级规则不一致。", evidence_ids)
    if (certificate.get("verification_status") != "verified" or not evidence_ids
            or certificate.get("evidence_status") != "verified"):
        return _result("unknown", "缺少已核实的证书正文依据。", evidence_ids)
    if node.get("scope") and certificate.get("scope") != node["scope"]:
        return _result("unknown", "适用范围尚未核实符合要求。", evidence_ids)
    if certificate.get("revocation_status") in {"revoked", "suspended"}:
        return _result("failed", "证书已撤销或暂停。", evidence_ids)
    if certificate.get("assertion_status") == "ABSENT":
        # Absence of one certificate does not establish absence of all certificates.
        return _result("unknown", "单份证书否定声明不足以排除该企业其他证书。", evidence_ids)
    if certificate.get("assertion_status") != "PRESENT":
        return _result("unknown", "证书持有状态尚未核实。", evidence_ids)
    try:
        valid_from = _date(certificate.get("valid_from"))
        valid_until = _date(certificate.get("valid_until"))
    except ConditionError:
        return _result("unknown", "证书有效区间不完整。", evidence_ids)
    if valid_from > valid_until:
        return _result("conflict", "证书日期区间矛盾。", evidence_ids)
    if not valid_from <= as_of <= valid_until:
        return _result("failed", "证书在要求日期无效。", evidence_ids)
    if certificate.get("revocation_status") != "clear":
        return _result("unknown", "撤销或暂停状态未核实。", evidence_ids)
    grade = certificate.get("grade")
    if node["op"] == "grade_exact" and grade != node["value"]:
        return _result("failed", "该证书等级与精确条件不符。", evidence_ids)
    if node["op"] == "grade_at_least":
        accepted = rule.get("at_least", {}).get(node["value"])
        if not isinstance(accepted, list) or not accepted:
            return _result("unknown", "此等级关系尚无已启用的规则依据。", evidence_ids)
        if grade not in accepted:
            return _result("failed", "该证书等级不在规则认可范围。", evidence_ids)
    return _result("satisfied", "主体、证书依据、等级和要求日期均已核实。", evidence_ids)


def evaluate_conditions(compiled, company, *, rules):
    """Evaluate one company without prefiltering missing or conflicting facts.

    A failed individual certificate cannot establish that a company has no other
    qualifying certificate. Only a verified exhaustive category check can do so.
    """
    as_of = _date(compiled["as_of"]["date"])
    from .baichuan_legacy_matching import trusted_legacy_verdict
    details = []

    def evaluate(node, path):
        for operator in ("all", "any", "not"):
            if operator in node:
                children = [node[operator]] if operator == "not" else node[operator]
                return combine(operator, [evaluate(child, f"{path}.{i}") for i, child in enumerate(children)])
        if node["field"] in COMPANY_FIELDS:
            field = COMPANY_FIELDS[node["field"]]
            value = company.get(field)
            fact = company.get("field_verification", {}).get(field, {})
            if fact.get("status") == "conflict":
                result = _result("conflict", "企业字段来源冲突。", fact.get("evidence_ids", []))
            elif value and 'trusted_legacy_qualifications' in company:
                result = _result('satisfied' if value == node['value'] else 'failed',
                                 '按用户确认的企业库当前字段比较。')
            elif not value or fact.get("status") != "verified" or not fact.get("evidence_ids"):
                result = _result("unknown", "企业字段缺少已核实依据。")
            else:
                result = _result("satisfied" if value == node["value"] else "failed", "按已核实企业字段比较。", fact["evidence_ids"])
        else:
            category = node["category"]
            rule = rules.get(category, {})
            if (not rule.get("enabled") or not rule.get("version") or not rule.get("source")
                    or (node.get("rule_version") and node["rule_version"] != rule["version"])):
                result = _result("unknown", "类别或指定版本尚无有效规则。")
            elif node["op"] != "present" and node["value"] not in rule.get("grades", []):
                result = _result("unknown", "等级未被该类别规则覆盖。")
            else:
                certificates = [c for c in company.get("certificates", []) if c.get("category") == category
                                and c.get("verification_status") != "superseded"]
                results = [_certificate_verdict(node, company, c, as_of, rule) for c in certificates]
                legacy = trusted_legacy_verdict(node, company, compiled, rule, certificates)
                if any(r["verdict"] == "conflict" for r in results):
                    result = _result("conflict", "相关证书存在冲突。", [i for r in results for i in r["evidence_ids"]])
                elif legacy is not None and legacy['verdict'] == 'conflict':
                    result = legacy
                elif any(r["verdict"] == "satisfied" for r in results):
                    result = next(r for r in results if r["verdict"] == "satisfied")
                elif legacy is not None:
                    result = legacy
                else:
                    coverage = company.get("category_verification", {}).get(category, {})
                    exhaustive = (coverage.get("status") == "verified" and coverage.get("exhaustive") is True
                                  and coverage.get("as_of") == as_of.isoformat() and coverage.get("evidence_ids")
                                  and coverage.get("holder") == node["holder"])
                    if exhaustive and (not results or all(r["verdict"] == "failed" for r in results)):
                        result = _result("failed", "该时点的完整资质核查未满足条件。", coverage["evidence_ids"])
                    else:
                        result = _result("unknown", "现有证书不足以确认满足；未查到不等于没有。", [i for r in results for i in r["evidence_ids"]])
        details.append({"condition_id": path, **result})
        return result["verdict"]

    hard = evaluate(compiled["must"], "must")
    if compiled["unresolved"] and hard == "satisfied":
        hard = "unknown"
    preferences = [evaluate(node, f"should.{i}") for i, node in enumerate(compiled["should"])]
    status = {"satisfied": "confirmed", "failed": "excluded"}.get(hard, "candidate")
    return {"company_id": str(company["id"]), "status": status, "verdict": hard,
            "preferences": preferences, "conditions": details, "unresolved": compiled["unresolved"]}
