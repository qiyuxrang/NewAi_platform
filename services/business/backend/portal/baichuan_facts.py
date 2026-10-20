"""Permission checked, versioned facts and protected manual-edit history.

Acquisition/identity checking happens before this boundary. Evidence metadata
must describe the checked original content, never a search-result snippet.
"""
import hashlib
import json
import re
import uuid
from datetime import date, datetime
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision
from .baichuan_models import Company, CompanyPerson, CompanyQualification
from .baichuan_service import BaichuanError, can_access, company_for, require_access


FACT_FIELDS = {"province", "city", "address", "website", "website_kind", "phone", "contact_name", "contact_phone", "email", "description"}
CERTIFICATE_FIELDS = {"category", "raw_category", "holder_type", "holder_name", "holder_company_id", "standard",
    "scope_text", "grade", "raw_grade", "certificate_no", "issuer", "valid_from", "valid_until",
    "assertion_status", "revocation_status", "fingerprint"}


def validate_public_certificate_observation(record, source, company_name):
    """Offline ITSS publication validation; these observations are never verification."""
    def reject():
        raise BaichuanError("invalid_certificate_observation", "公开证书正文、主体或字段依据不合法。")
    fields = {"orgName", "certificateCode", "itssTypeText", "certificateName", "validFlag",
              "startDate", "getDate", "endDate", "pgjg", "getType", "cityName"}
    required = {"orgName", "certificateCode", "itssTypeText", "certificateName", "validFlag"}
    source_fields = {"url", "title", "publisher", "retrieved_at", "body", "content_sha256",
                     "excerpt", "locator", "field_assertions", "publication_kind", "read_status"}
    if (not isinstance(record, dict) or not required <= set(record) or set(record) - fields
            or any(not isinstance(value, str) or len(value) > 5000 for value in record.values())
            or not isinstance(company_name, str) or not company_name
            or record["orgName"].translate(str.maketrans("（）", "()")) != company_name.translate(str.maketrans("（）", "()"))
            or record["itssTypeText"] != "运行维护" or record["certificateName"] not in {"一级", "二级", "三级", "四级", "通用要求"}
            or not record["validFlag"] or not re.fullmatch(r"ITSS-YW-(?:[1-4]|YH)-[A-Za-z0-9-]{1,100}", record["certificateCode"])
            or not isinstance(source, dict) or set(source) != source_fields
            or source["read_status"] != "completed" or source["publication_kind"] != "industry"):
        reject()
    for field, maximum in (("url", 2000), ("title", 500), ("publisher", 300), ("body", 524288), ("excerpt", 64000)):
        if not isinstance(source[field], str) or not 1 <= len(source[field]) <= maximum:
            reject()
    try:
        parsed = urlsplit(source["url"])
        if (parsed.scheme != "https" or parsed.hostname != "www.itss.cn" or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or not re.fullmatch(r"/api/itss/web/certificate/[0-9a-f]{32}", parsed.path)
                or any(ord(c) <= 32 or c == "\\" for c in source["url"])):
            reject()
        retrieved = datetime.fromisoformat(source["retrieved_at"])
        if timezone.is_naive(retrieved) or retrieved > timezone.now():
            reject()
        # Preserve the three independent published date labels, never derive valid_from.
        for field in ("startDate", "getDate", "endDate"):
            if record.get(field):
                date.fromisoformat(record[field])
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    reject()
                result[key] = value
            return result
        if json.loads(source["body"], object_pairs_hook=unique_pairs) != record:
            reject()
    except (ValueError, TypeError, AttributeError):
        reject()
    locator = source["locator"]
    if (len(source["body"].encode("utf-8")) > 524288 or source["excerpt"] != source["body"]
            or hashlib.sha256(source["body"].encode("utf-8")).hexdigest() != source["content_sha256"]
            or not isinstance(locator, dict) or type(locator.get("text_start")) is not int
            or type(locator.get("text_end")) is not int or locator["text_start"] != 0
            or locator["text_end"] != len(source["body"])
            or not isinstance(source["field_assertions"], dict)
            or source["field_assertions"] != {key: [value] for key, value in record.items()}):
        reject()
    return {"category": "itss", "raw_category": record["itssTypeText"],
            "grade": {"一级": "1", "二级": "2", "三级": "3", "四级": "4"}.get(record["certificateName"], ""),
            "raw_grade": record["certificateName"], "holder_type": "bidder", "holder_name": company_name,
            "certificate_no": record["certificateCode"], "issuer": "", "standard": "", "scope_text": "",
            "valid_from": None, "valid_until": date.fromisoformat(record["endDate"]) if record.get("endDate") else None,
            "assertion_status": "PRESENT", "revocation_status": "unknown"}


def public_certificate_observation_identity(company_id, record, source, scope):
    """Stable complete publication identity, shared by offline whole-batch preflight."""
    payload = {"scope": scope, "company_id": str(company_id), "record": record, "source": source}
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ids = {key: uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan:public-certificate:{scope}:{company_id}:{fingerprint}:{key}")
           for key in ("evidence", "revision", "certificate")}
    return payload, fingerprint, ids


@transaction.atomic
def record_public_certificate_observation(actor, company_id, record, source, expected_version, *, scope="default", validate_only=False):
    """Maintenance-only append of an unverified publication, with no legacy projection."""
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    if type(expected_version) is not int or expected_version < 1:
        raise BaichuanError("version_conflict", "企业版本不合法。", 409)
    if (not getattr(settings, "BAICHUAN_FACT_WRITE_ENABLED", False)
            or not getattr(settings, "BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED", False)
            or scope != settings.BAICHUAN_ASSISTANT_SCOPE):
        raise BaichuanError("certificate_observation_disabled", "公开证书维护未在本进程授权启用。", 409)
    company = company_for(actor, company_id, lock=True)
    values = validate_public_certificate_observation(record, source, company.name)
    values["holder_company_id"] = company.pk
    payload, fingerprint, ids = public_certificate_observation_identity(company.pk, record, source, scope)
    subject = {"company_id": str(company.pk), "matched_name": record["orgName"], "holder_type": "bidder",
        "identity_verified": False, "legal_identity_verified": False, "scope_verified": False,
        "authority": "official_public_directory", "publication_status": "reviewed_public_publication",
        "publication_kind": "industry", "source_review": "assistant_source_review",
        "field_assertions": source["field_assertions"], "public_record": record,
        "observation_fingerprint": fingerprint}
    evidence_values = {"scope": scope, "source_type": "public_certificate_record", "url": source["url"],
        "publisher": source["publisher"], "title": source["title"], "retrieved_at": datetime.fromisoformat(source["retrieved_at"]),
        "verified_on": None, "content_hash": source["content_sha256"], "excerpt": source["excerpt"],
        "locator": source["locator"], "access_status": "completed", "subject": subject,
        "published_on": None, "import_ref": "", "storage_ref": ""}
    existing = BaichuanCertificate.objects.select_related("evidence", "source_revision").filter(pk=ids["certificate"]).first()
    if existing:
        recorded_conflicts = existing.source_revision.new_value.get("conflicts") if existing.source_revision else None
        expected_status = "conflict" if recorded_conflicts else "unverified"
        if (existing.company_id != company.pk or existing.fingerprint != fingerprint
                or existing.evidence_id != ids["evidence"] or existing.source_revision_id != ids["revision"]
                or existing.verification_status != expected_status or existing.verified_at is not None
                or existing.legacy_qualification_id is not None
                or any(getattr(existing, key) != value for key, value in values.items())
                or any(getattr(existing.evidence, key) != value for key, value in evidence_values.items())
                or existing.source_revision.company_id != company.pk or existing.source_revision.field != "certificate_observation"
                or existing.source_revision.object_id != existing.pk or existing.source_revision.evidence_id != existing.evidence_id
                or existing.source_revision.review_status != ("public_conflict" if recorded_conflicts else "applied_observation")
                or existing.source_revision.verification_status != "unverified"
                or existing.source_revision.new_value.get("publication_payload") != payload
                or existing.source_revision.new_value.get("declaration") != json_value(values)
                or not isinstance(existing.source_revision.new_value.get("conflicts"), list)):
            raise BaichuanError("certificate_observation_conflict", "已有观察或来源已改变，保留原记录并停止。", 409)
        return {"replayed": True, "certificate_id": str(existing.pk), "evidence_id": str(existing.evidence_id),
                "revision_id": str(existing.source_revision_id), "conflicts": existing.source_revision.new_value["conflicts"]}
    if company.version != expected_version:
        raise BaichuanError("version_conflict", "企业资料已更新，请重新读取后复核。", 409)
    # A legacy statement without a number is not proof of a contradictory certificate.
    # Same-number differences are retained as distinct, unverified review records.
    conflicts = []
    for old in BaichuanCertificate.objects.filter(company=company, category="itss", certificate_no=values["certificate_no"]).exclude(verification_status="superseded").select_related("evidence", "source_revision__evidence"):
        old_evidence = old.evidence or (old.source_revision.evidence if old.source_revision else None)
        if old_evidence is not None and old_evidence.scope != scope:
            continue
        old_public_record = old_evidence.subject.get("public_record") if old_evidence and isinstance(old_evidence.subject, dict) else None
        # Missing public fields never deny a formerly known value. Raw spellings
        # of category/grade/name are compared through their normalized fields.
        known_fields = {"category", "grade", "holder_type", "holder_name", "holder_company_id", "certificate_no", "valid_until"}
        def known(value):
            return value not in (None, "", "unknown")
        def comparable(key, value):
            return value.translate(str.maketrans("（）", "()")) if key == "holder_name" and isinstance(value, str) else value
        contradiction = any(known(getattr(old, key)) and known(values[key])
            and comparable(key, getattr(old, key)) != comparable(key, values[key]) for key in known_fields)
        raw_contradiction = (isinstance(old_public_record, dict) and any(key not in {"certificateName", "itssTypeText", "orgName"}
            and known(value) and known(old_public_record.get(key)) and value != old_public_record[key] for key, value in record.items()))
        if contradiction or raw_contradiction:
            conflicts.append(str(old.pk))
    if validate_only:
        return {"replayed": False, "validate_only": True, "conflicts": sorted(conflicts)}
    evidence = BaichuanEvidence.objects.create(id=ids["evidence"], created_by=actor, **evidence_values)
    revision = BaichuanFactRevision.objects.create(id=ids["revision"], company=company, field="certificate_observation",
        object_id=ids["certificate"], actor=actor, baseline_version=company.version, evidence=evidence,
        verification_status="unverified", review_status="public_conflict" if conflicts else "applied_observation",
        new_value={"publication_payload": payload, "declaration": json_value(values), "conflicts": sorted(conflicts)},
        reason="Unverified public observation only; unknown fields and all original declarations retained.")
    certificate = BaichuanCertificate(id=ids["certificate"], company=company, **values, fingerprint=fingerprint,
        evidence=evidence, source_revision=revision, verification_status="conflict" if conflicts else "unverified", verified_at=None)
    try:
        certificate.full_clean()
    except ValidationError:
        raise BaichuanError("invalid_certificate_observation", "公开证书字段不合法，未提交。") from None
    _cas_company(company, actor)
    certificate.save(force_insert=True)
    from .security import audit
    audit(actor, "baichuan_public_certificate_observation", company.pk, changes=[str(certificate.pk), str(revision.pk)])
    return {"replayed": False, "certificate_id": str(certificate.pk), "evidence_id": str(evidence.pk),
            "revision_id": str(revision.pk), "conflicts": sorted(conflicts)}


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def evidence_is_valid(evidence, company, *, certificate=False, scope="default"):
    if not isinstance(evidence, BaichuanEvidence):
        return False
    subject = evidence.subject if isinstance(evidence.subject, dict) else {}
    if subject.get("identity_method") is not None and not isinstance(subject["identity_method"], str):
        return False
    valid = (evidence.scope == scope and evidence.access_status == "verified" and evidence.verified_on is not None
        and evidence.retrieved_at is not None and bool(evidence.excerpt.strip()) and bool(evidence.locator)
        and bool(re.fullmatch(r"[a-fA-F0-9]{64}", evidence.content_hash))
        and bool(evidence.url or evidence.import_ref)
        and subject.get("company_id") == str(company.pk) and subject.get("identity_verified") is True
        and evidence.source_type not in {"search_snippet", "model_output"})
    if certificate:
        valid = (valid and subject.get("holder_type") == "bidder" and subject.get("scope_verified") is True
            and subject.get("authority") in {"issuer", "regulator", "verifiable_certificate"})
    if subject.get("identity_method") == "official_host_name_credit_code":
        basis = subject.get("identity_basis", {})
        if not isinstance(basis, dict):
            return False
        try:
            valid = (valid and company.website_kind == "corporate" and basis.get("matched_name") == company.name
                and basis.get("matched_credit_code") == company.credit_code
                and basis.get("host") == urlsplit(company.website or "").hostname
                and basis.get("host") == urlsplit(evidence.url).hostname and urlsplit(evidence.url).scheme == "https")
        except ValueError:
            return False
    return bool(valid)


def _baseline(actor, company_id, expected_version):
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor)
    company = company_for(actor, company_id, lock=True)
    if isinstance(expected_version, bool) or expected_version != company.version:
        raise BaichuanError("version_conflict", "资料已被更新，请重新读取后核对。", 409)
    return company


def _cas_company(company, actor, **values):
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    changed = Company.objects.filter(pk=company.pk, version=company.version).update(
        **values, version=models.F("version") + 1, updated_by=actor, updated_at=timezone.now())
    if not changed:
        raise BaichuanError("version_conflict", "资料已被更新，请重新读取后核对。", 409)


@transaction.atomic
def propose_field(actor, company_id, field, value, evidence, expected_version, *, scope="default"):
    """Readers retain isolated suggestions; maintainers may fill verified blanks.

    A nonempty conflicting value is always retained. Merely setting a source's
    verification flag cannot overwrite an existing manual company fact.
    """
    if field not in FACT_FIELDS:
        raise BaichuanError("invalid_field", "不支持自动修改此企业字段。")
    company = _baseline(actor, company_id, expected_version)
    model_field = Company._meta.get_field(field)
    try:
        value = model_field.clean(value, company)
    except ValidationError:
        raise BaichuanError("invalid_fact", "企业字段内容不合法。") from None
    original = getattr(company, field)
    valid = evidence_is_valid(evidence, company, scope=scope)
    if valid and evidence.subject.get("identity_method") in {"official_host_name_credit_code", "full_legal_name_on_public_page"}:
        assertions = evidence.subject.get("field_assertions", {})
        declared = assertions.get(field, []) if isinstance(assertions, dict) else []
        valid = isinstance(declared, list) and value in declared
    # Wrong identity is never entered as a verified conflict or fact.
    conflict = valid and original not in (None, "") and original != value
    writable = can_access(actor, write=True) and getattr(settings, "BAICHUAN_FACT_WRITE_ENABLED", False)
    status = "conflict" if conflict and writable else "applied" if valid and writable else "proposed"
    verification = "conflict" if conflict else "verified" if valid else "unverified"
    # Proposals from readers or a disabled write phase never become shared
    # conflict state, and must not prevent a later authorized application.
    duplicate = BaichuanFactRevision.objects.filter(company=company, field=field, baseline_version=company.version,
        actor=actor, new_value=json_value(value), evidence=evidence, review_status=status).first()
    if duplicate:
        return duplicate
    revision = BaichuanFactRevision.objects.create(company=company, field=field, old_value=json_value(original),
        new_value=json_value(value), evidence=evidence, actor=actor, baseline_version=company.version,
        verification_status=verification, review_status=status,
        reason="Existing value retained for conflict review." if conflict else "Evidence checked; original nonempty values protected.")
    if status == "applied" and original != value:
        _cas_company(company, actor, **{field: value})
    return revision


@transaction.atomic
def propose_certificate(actor, company_id, declaration, evidence, expected_version, *, scope="default"):
    if not isinstance(declaration, dict) or set(declaration) - CERTIFICATE_FIELDS:
        raise BaichuanError("invalid_certificate", "证书声明含不支持字段。")
    company = _baseline(actor, company_id, expected_version)
    values = dict(declaration)
    for key in ("valid_from", "valid_until"):
        if isinstance(values.get(key), str):
            try:
                values[key] = date.fromisoformat(values[key])
            except ValueError:
                raise BaichuanError("invalid_certificate", "证书日期不合法。") from None
    certificate = BaichuanCertificate(company=company, **values)
    try:
        certificate.full_clean(exclude=["source_revision", "evidence"])
    except ValidationError:
        raise BaichuanError("invalid_certificate", "证书字段、日期或持有声明不合法。") from None
    subject = evidence.subject if isinstance(evidence, BaichuanEvidence) and isinstance(evidence.subject, dict) else {}
    valid = (evidence_is_valid(evidence, company, certificate=True, scope=scope)
        and certificate.holder_type == "bidder" and str(certificate.holder_company_id) == str(company.pk)
        and certificate.holder_name == company.name and bool(certificate.category)
        and certificate.valid_from is not None and certificate.valid_until is not None
        and certificate.assertion_status == "PRESENT")
    if certificate.revocation_status == "clear":
        valid = (valid and subject.get("revocation_checked") is True
            and subject.get("revocation_checked_on") == evidence.verified_on.isoformat())
    if certificate.assertion_status == "ABSENT":
        # A single missing or negative certificate can never assert the whole
        # category absent. Such declarations remain proposals for human review.
        valid = False
    old = []
    for item in (BaichuanCertificate.objects.filter(company=company, category=certificate.category)
                 .exclude(verification_status="superseded")
                 .select_related("evidence", "source_revision__evidence")):
        # No evidence is not proof of another deployment: keep manual legacy
        # declarations protected. A traceable, explicitly different scope is.
        source = item.evidence or (item.source_revision.evidence if item.source_revision else None)
        if source is None or source.scope == scope:
            old.append(item)

    def same_verified_declaration(item):
        revision = item.source_revision
        if not (valid and item.certificate_no and item.verification_status == "verified"
                and item.verified_at is not None
                and all(getattr(item, field) == getattr(certificate, field) for field in CERTIFICATE_FIELDS)
                and evidence_is_valid(item.evidence, company, certificate=True, scope=scope)
                and revision and revision.company_id == company.pk and revision.field == "certificate"
                and revision.review_status == "applied" and revision.verification_status == "verified"
                and revision.evidence_id == item.evidence_id):
            return False
        old_subject = item.evidence.subject
        return (item.revocation_status != "clear" or (old_subject.get("revocation_checked") is True
            and old_subject.get("revocation_checked_on") == item.evidence.verified_on.isoformat()))

    same = next((item for item in old if same_verified_declaration(item)), None)
    if same:
        return same.source_revision
    # Same category may contain several independent certificates. Only the same
    # certificate number (or same legacy category/grade declaration) conflicts.
    conflict = any((item.certificate_no and item.certificate_no == certificate.certificate_no)
        or (item.legacy_qualification_id and item.grade == certificate.grade) for item in old)
    writable = can_access(actor, write=True) and getattr(settings, "BAICHUAN_FACT_WRITE_ENABLED", False)
    status = "conflict" if valid and conflict and writable else "applied" if valid and writable else "proposed"
    duplicate = BaichuanFactRevision.objects.filter(company=company, field="certificate", baseline_version=company.version,
        actor=actor, new_value=json_value(values), evidence=evidence, review_status=status).first()
    if duplicate:
        return duplicate
    revision = BaichuanFactRevision.objects.create(company=company, field="certificate", actor=actor,
        new_value=json_value(values), evidence=evidence, baseline_version=company.version,
        verification_status="conflict" if status == "conflict" else "verified" if valid else "unverified",
        review_status=status, reason="Certificate declaration checked; existing certificates retained.")
    if status == "applied":
        _cas_company(company, actor)
        certificate.verification_status = "verified"
        certificate.verified_at = timezone.now()
        certificate.source_revision = revision
        certificate.evidence = evidence
        # The seven-category view remains a compatibility projection. Add only
        # an absent exact declaration, never delete or replace existing grades.
        from .baichuan_models import QUALIFICATION_GRADES
        if (certificate.category in QUALIFICATION_GRADES
                and (certificate.category == "labor" or certificate.grade in QUALIFICATION_GRADES[certificate.category])
                and not CompanyQualification.objects.filter(company=company, category=certificate.category,
                    status="PRESENT", grade=certificate.grade or None).exists()):
            projected = CompanyQualification.objects.create(company=company, category=certificate.category,
                status="PRESENT", grade=certificate.grade or None, certificate_no=certificate.certificate_no or None,
                valid_until=certificate.valid_until, source=evidence.url or evidence.import_ref,
                verified_on=evidence.verified_on)
            certificate.legacy_qualification_id = projected.pk
            BaichuanFactRevision.objects.create(company=company, field="legacy_projection", object_id=projected.pk,
                new_value={"certificate_id": str(certificate.pk), "category": certificate.category,
                    "grade": certificate.grade}, evidence=evidence, actor=actor, baseline_version=company.version,
                verification_status="verified", review_status="applied", reason="Traceable exact-grade compatibility projection.")
        certificate.save()
    return revision


@transaction.atomic
def revert_field(actor, revision_id):
    require_access(actor, write=True)
    revision = BaichuanFactRevision.objects.select_related("company").get(pk=revision_id)
    if revision.field not in FACT_FIELDS or revision.review_status != "applied":
        raise BaichuanError("invalid_revert", "此修订不能自动回撤。")
    company = company_for(actor, revision.company_id, lock=True)
    if company.version != revision.baseline_version + 1 or json_value(getattr(company, revision.field)) != revision.new_value:
        raise BaichuanError("version_conflict", "此后已有修改，不能自动回撤覆盖。", 409)
    _cas_company(company, actor, **{revision.field: revision.old_value})
    return BaichuanFactRevision.objects.create(company=company, field=revision.field, old_value=revision.new_value,
        new_value=revision.old_value, actor=actor, baseline_version=company.version, supersedes=revision,
        review_status="reverted", reason="Version-checked rollback of one applied field revision.")


def manual_snapshot(company):
    """Called only inside the existing editor's locked transaction."""
    if company is None:
        return {"version": 1, "company": {}, "qualifications": {}, "people": {}}
    from .baichuan_service import COMPANY_FIELDS
    return {"version": company.version,
        "company": {field: json_value(getattr(company, field)) for field in COMPANY_FIELDS},
        "qualifications": {str(item["id"]): json_value(item) for item in company.qualifications.values()},
        "people": {str(item["id"]): json_value(item) for item in company.people.values()}}


def record_manual_changes(actor, company, before):
    """Append manual changes, preserving replaced child statements and sources."""
    after = manual_snapshot(company)
    for field, value in after["company"].items():
        old = before["company"].get(field)
        if old != value:
            BaichuanFactRevision.objects.create(company=company, field=field, old_value=old, new_value=value,
                actor=actor, baseline_version=before["version"], review_status="manual",
                reason="Manual company editor change; no automatic verification upgrade.")
    for collection, field in (("qualifications", "legacy_qualification"), ("people", "legacy_person")):
        previous, current = before[collection], after[collection]
        for key in sorted(set(previous) | set(current)):
            old, new = previous.get(key), current.get(key)
            if old == new:
                continue
            BaichuanFactRevision.objects.create(company=company, field=field, object_id=key, old_value=old,
                new_value=new, actor=actor, baseline_version=before["version"], review_status="manual",
                reason="Manual child snapshot change; prior declaration and source retained.")
            if collection == "qualifications" and old is not None:
                BaichuanCertificate.objects.filter(legacy_qualification_id=key).update(verification_status="superseded")
