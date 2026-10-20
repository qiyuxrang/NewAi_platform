"""Permission-checked structured matching and immutable result revisions."""
from datetime import date
import hashlib
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.utils import timezone

from .baichuan_assistant_models import (BaichuanCertificate, BaichuanFactRevision, BaichuanJob,
                                      BaichuanMatchSnapshot, BaichuanQualificationRule)
from .baichuan_conditions import compile_conditions, evaluate_conditions
from .baichuan_models import Company
from .baichuan_service import BaichuanError, require_access
from .baichuan_facts import evidence_is_valid
from .baichuan_jobs import leased_job


def _evidence_current(evidence):
    return bool(evidence and evidence.verified_on and evidence.verified_on <= timezone.localdate()
                and evidence.retrieved_at and evidence.retrieved_at <= timezone.now())


def evidence_verified(evidence, company):
    # Official-host identity is bound to the current name, credit code and host,
    # so passing an ID-only placeholder both loses that check and can crash.
    return (_evidence_current(evidence)
            and evidence_is_valid(evidence, company, scope=settings.BAICHUAN_ASSISTANT_SCOPE))


def _field_evidence_verified(evidence, company, field, value):
    if not evidence_verified(evidence, company):
        return False
    if evidence.subject.get("identity_method") in {"official_host_name_credit_code", "full_legal_name_on_public_page"}:
        assertions = evidence.subject.get("field_assertions", {})
        values = assertions.get(field, []) if isinstance(assertions, dict) else []
        return isinstance(values, list) and value in values
    return True


def load_rules(as_of):
    result = {}
    for rule in BaichuanQualificationRule.objects.filter(evidence__scope=settings.BAICHUAN_ASSISTANT_SCOPE).select_related("evidence").order_by("category", "version"):
        grades = rule.legal_grades
        valid_grades = isinstance(grades, list) and all(isinstance(g, str) and g for g in grades)
        relations = rule.grade_relations if isinstance(rule.grade_relations, dict) else {}
        at_least = relations.get("at_least", {})
        at_least = ({grade: accepted for grade, accepted in at_least.items()
                     if valid_grades and grade in grades and isinstance(accepted, list) and accepted
                     and all(isinstance(g, str) and g in grades for g in accepted)}
                    if isinstance(at_least, dict) else {})
        # The most recent version supersedes previous versions, including disabling.
        result[rule.category] = {"enabled": bool(rule.enabled and valid_grades and rule.evidence.excerpt.strip() and rule.evidence.locator
            and _evidence_current(rule.evidence) and rule.evidence.access_status == "verified"
            and rule.evidence.source_type not in {"search_snippet", "model_output"}
            and re.fullmatch(r"[a-fA-F0-9]{64}", rule.evidence.content_hash)
            and (not rule.applicable_from or rule.applicable_from <= as_of)
            and (not rule.applicable_until or as_of <= rule.applicable_until)),
            "version": f"{rule.category}:{rule.version}", "source": rule.evidence.url or rule.evidence.import_ref,
            "grades": grades if valid_grades else [], "at_least": at_least,
            "standard": rule.standard}
    return result


def _iso(value):
    return value.isoformat() if value else None


def _revocation_at(evidence, as_of):
    subject = evidence.subject
    try:
        checked = date.fromisoformat(subject.get("revocation_checked_on", ""))
    except (ValueError, TypeError):
        return False
    return (as_of <= checked <= timezone.localdate() and checked == evidence.verified_on
            and subject.get("revocation_as_of", checked.isoformat()) == as_of.isoformat())


def _legacy_source_ids(company, legacy, certificates):
    """Cite an existing declaration link without granting source verification.

    The complete mapped-source chain must still describe the current old row.
    No source is generated, repaired or inferred during a query.
    """
    source = legacy.source or ""
    if not source.strip():
        return []
    digest = hashlib.sha256(source.encode()).hexdigest()
    declaration = {'id': str(legacy.pk), 'category': legacy.category, 'status': legacy.status,
        'grade': legacy.grade, 'certificate_no': legacy.certificate_no,
        'valid_until': _iso(legacy.valid_until), 'source': legacy.source,
        'verified_on': _iso(legacy.verified_on)}
    identifiers = []
    for certificate in certificates:
        if (certificate.company_id != company.pk or certificate.legacy_qualification_id != legacy.pk
                or certificate.category != legacy.category or certificate.grade != (legacy.grade or '')
                or certificate.certificate_no != (legacy.certificate_no or '')
                or certificate.valid_until != legacy.valid_until or certificate.assertion_status != legacy.status
                or certificate.holder_type != 'bidder' or certificate.holder_company_id != company.pk
                or certificate.verification_status != 'unverified' or certificate.verified_at is not None):
            continue
        evidence, link = certificate.evidence, certificate.source_revision
        original = link.supersedes if link and link.supersedes_id else None
        if (not evidence or not link or not original
                or original.company_id != company.pk or original.field != 'legacy_qualification'
                or original.object_id != legacy.pk or original.review_status != 'mapped_declaration'
                or original.new_value != declaration
                or link.company_id != company.pk or link.field != 'legacy_source_evidence_link'
                or link.object_id != certificate.pk or link.evidence_id != evidence.pk
                or link.review_status != 'mapped_source' or link.verification_status != 'unverified'
                or link.new_value != {'evidence_id': str(evidence.pk), 'source_revision_id': str(original.pk),
                    'legacy_qualification_id': str(legacy.pk), 'source_sha256': digest}
                or evidence.scope != settings.BAICHUAN_ASSISTANT_SCOPE
                or evidence.source_type != 'legacy_import' or evidence.access_status != 'unverified'
                or evidence.verified_on is not None or evidence.excerpt != source or evidence.content_hash != digest
                or not isinstance(evidence.subject, dict)
                or evidence.subject.get('company_id') != str(company.pk)
                or evidence.subject.get('legacy_qualification_id') != str(legacy.pk)
                or evidence.subject.get('source_revision_id') != str(original.pk)
                or evidence.subject.get('identity_verified') is not False
                or evidence.subject.get('holder_type') != 'bidder'
                or not isinstance(evidence.locator, dict) or not evidence.locator):
            continue
        identifiers.append(str(evidence.pk))
    return sorted(set(identifiers))


def company_facts(company, *, as_of=None):
    as_of = as_of or timezone.localdate()
    row = {"id": str(company.pk), "name": company.name, "province": company.province, "city": company.city,
           "field_verification": {}, "certificates": []}
    if getattr(settings, 'BAICHUAN_TRUST_LEGACY_QUALIFICATIONS', False):
        certificates = list(company.certificates.all())
        row['trusted_legacy_qualifications'] = [
            {'id': str(q.pk), 'category': q.category, 'status': q.status, 'grade': q.grade,
             'valid_until': _iso(q.valid_until), 'evidence_ids': _legacy_source_ids(company, q, certificates)}
            for q in company.qualifications.all()]
        row['legacy_trust_date'] = timezone.localdate().isoformat()
    # Only a current, applied revision that still equals the human-visible value
    # can verify a company field. Historical evidence is not silently resurrected.
    seen = set()
    revisions = sorted(company.fact_revisions.all(), key=lambda r: (r.created_at, r.pk), reverse=True)
    for revision in revisions:
        # A traceable foreign deployment must not shadow this deployment's
        # current fact, including through the newest-revision ``seen`` guard.
        # Evidence-less manual history remains authoritative history to inspect.
        if revision.evidence is not None and revision.evidence.scope != settings.BAICHUAN_ASSISTANT_SCOPE:
            continue
        if revision.review_status == "proposed":
            continue
        field = revision.field.removeprefix("company.")
        if field in seen or field not in {"name", "province", "city"}:
            continue
        seen.add(field)
        if revision.verification_status == "conflict":
            row["field_verification"][field] = {"status": "conflict", "evidence_ids": []}
        elif (revision.verification_status == "verified" and revision.review_status == "applied"
              and revision.new_value == row[field]
              and _field_evidence_verified(revision.evidence, company, field, revision.new_value)):
            row["field_verification"][field] = {"status": "verified", "evidence_ids": [str(revision.evidence_id)]}
    for certificate in company.certificates.all():
        # Resolve deployment ownership before exposing status or evidence IDs.
        # A direct source wins; a revision source can establish foreign scope
        # when the direct source is absent, but cannot verify that certificate.
        source = certificate.evidence
        if source is None and certificate.source_revision_id:
            source = certificate.source_revision.evidence
        if source is not None and source.scope != settings.BAICHUAN_ASSISTANT_SCOPE:
            continue
        row["certificates"].append({"category": certificate.category, "grade": certificate.grade,
            "holder_type": certificate.holder_type, "holder_company_id": str(certificate.holder_company_id),
            "verification_status": certificate.verification_status, "assertion_status": certificate.assertion_status,
            "valid_from": _iso(certificate.valid_from), "valid_until": _iso(certificate.valid_until),
            "scope": certificate.scope_text, "revocation_status": certificate.revocation_status,
            "standard": certificate.standard,
            "evidence_ids": [str(certificate.evidence_id)] if certificate.evidence_id else [],
            "evidence_status": "verified" if (evidence_verified(certificate.evidence, company)
                and (not certificate.holder_name or certificate.holder_name == company.name)
                and certificate.evidence.subject.get("holder_type") == "bidder"
                and certificate.evidence.subject.get("authority") in {"issuer", "regulator", "verifiable_certificate"}
                and certificate.evidence.subject.get("scope_verified") is True
                and certificate.evidence.subject.get("revocation_checked") is True
                and _revocation_at(certificate.evidence, as_of)) else "unverified"})
    return row


def _certificate_records(company, result, compiled):
    """Freeze display metadata without promoting a declaration into evidence.

    Only certificates actually cited by a qualification condition, belonging to
    this company and the active evidence scope, enter the immutable result.
    Holder identity remains the certificate's recorded identity, never bidder.
    """
    categories = {}

    def visit(node, path):
        if 'not' in node:
            visit(node['not'], path + '.not')
        elif 'all' in node or 'any' in node:
            for index, child in enumerate(node.get('all', node.get('any'))):
                visit(child, f'{path}.{index}')
        elif node.get('field') == 'qualification':
            categories[path] = node['category']

    visit(compiled['must'], 'must')
    for index, node in enumerate(compiled['should']):
        visit(node, f'should.{index}')
    records = []
    for certificate in sorted(company.certificates.all(), key=lambda value: str(value.pk)):
        evidence = certificate.evidence
        if (certificate.verification_status == 'superseded' or not evidence
                or evidence.scope != settings.BAICHUAN_ASSISTANT_SCOPE
                or not isinstance(evidence.subject, dict)
                or evidence.subject.get('company_id') != str(company.pk)):
            continue
        condition_ids = [condition['condition_id'] for condition in result['conditions']
            if categories.get(condition['condition_id']) == certificate.category
            and str(evidence.pk) in condition.get('evidence_ids', [])]
        if not condition_ids:
            continue
        records.append({'certificate_id': str(certificate.pk), 'company_id': str(company.pk),
            'evidence_id': str(evidence.pk), 'evidence_scope': evidence.scope, 'condition_ids': condition_ids,
            'certificate_no': certificate.certificate_no, 'category': certificate.category,
            'raw_category': certificate.raw_category, 'grade': certificate.grade, 'raw_grade': certificate.raw_grade,
            'holder_type': certificate.holder_type, 'holder_name': certificate.holder_name,
            'holder_company_id': str(certificate.holder_company_id) if certificate.holder_company_id else '',
            'issuer': certificate.issuer, 'valid_from': _iso(certificate.valid_from),
            'valid_until': _iso(certificate.valid_until), 'standard': certificate.standard,
            'scope_text': certificate.scope_text, 'verification_status': certificate.verification_status,
            'assertion_status': certificate.assertion_status, 'revocation_status': certificate.revocation_status,
            'verified_at': _iso(certificate.verified_at), 'evidence_access_status': evidence.access_status})
    return records


def match_companies(user, conditions):
    user = get_user_model().objects.get(pk=user.pk)
    require_access(user)
    compiled = compile_conditions(conditions, today=timezone.localdate())
    rules = load_rules(date.fromisoformat(compiled["as_of"]["date"]))
    rows = Company.objects.order_by("name", "id").prefetch_related(
        Prefetch("certificates", queryset=BaichuanCertificate.objects.select_related(
            "evidence", "source_revision__evidence", "source_revision__supersedes")),
        Prefetch("fact_revisions", queryset=BaichuanFactRevision.objects.filter(
            field__in=("name", "province", "city", "company.name", "company.province", "company.city")
        ).exclude(review_status="proposed").select_related("evidence").order_by("-created_at", "-id")))
    if getattr(settings, 'BAICHUAN_TRUST_LEGACY_QUALIFICATIONS', False):
        rows = rows.prefetch_related('qualifications')
    results = []
    for company in rows.iterator(chunk_size=200):
        facts = company_facts(company, as_of=date.fromisoformat(compiled["as_of"]["date"]))
        result = evaluate_conditions(compiled, facts, rules=rules)
        result["company"] = {field: getattr(company, field) or "" for field in compiled["output"]["fields"]}
        result["company"]["name"] = company.name
        result["company_version"] = company.version
        result["certificate_records"] = _certificate_records(company, result, compiled)
        results.append(result)
    # Preference order is explicit and lexicographic, never an invented score.
    ranking = {"satisfied": 0, "unknown": 1, "conflict": 2, "failed": 3}
    status = {"confirmed": 0, "candidate": 1, "excluded": 2}
    results.sort(key=lambda r: (status[r["status"]], tuple(ranking[v] for v in r["preferences"]),
                               r["company"]["name"], r["company_id"]))
    counts = {kind: sum(r["status"] == kind for r in results) for kind in status}
    return compiled, rules, results, counts


def save_match_snapshot(user, job_id, lease_owner, fence, conditions, *, result_revision=1, research_status="not_started"):
    """Compute without holding a write lock; recheck authority at publication."""
    compiled = compile_conditions(conditions, today=timezone.localdate())
    if type(result_revision) is not int or result_revision < 1:
        raise BaichuanError("invalid_request", "结果版本无效。")

    def boundary(job):
        if job.owner_id != user.pk:
            raise BaichuanError("not_found", "任务不存在或不可访问。", 404)
        if (job.kind != "query" or not job.conversation_id
                or job.conversation.owner_id != job.owner_id or job.conversation.scope != job.scope):
            raise BaichuanError("invalid_request", "匹配任务会话或执行范围无效。")
        if compiled["revision"] != job.payload.get("condition_revision"):
            raise BaichuanError("revision_conflict", "匹配条件不属于本轮任务。", 409)

    with leased_job(job_id, lease_owner, fence) as job:
        boundary(job)
        existing = job.snapshots.filter(result_revision=result_revision).first()
        if existing:
            if existing.condition_tree != compiled or existing.research_status != research_status:
                raise BaichuanError("revision_conflict", "该结果版本已保存其他内容。", 409)
            return existing
    current_user = get_user_model().objects.get(pk=user.pk)
    compiled, rules, results, counts = match_companies(current_user, compiled)
    with leased_job(job_id, lease_owner, fence) as job:
        boundary(job)
        existing = job.snapshots.filter(result_revision=result_revision).first()
        if existing:
            if existing.condition_tree != compiled or existing.research_status != research_status:
                raise BaichuanError("revision_conflict", "该结果版本已保存其他内容。", 409)
            return existing
        return BaichuanMatchSnapshot.objects.create(conversation=job.conversation, job=job,
            condition_revision=compiled["revision"], result_revision=result_revision, condition_tree=compiled,
            rule_versions={key: value["version"] for key, value in rules.items()},
            candidate_ids=[r["company_id"] for r in results if r["status"] != "excluded"],
            results=results, counts=counts, fact_cutoff_at=timezone.now(), research_status=research_status)
