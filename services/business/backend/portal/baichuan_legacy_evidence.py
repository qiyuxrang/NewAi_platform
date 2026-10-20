"""Explicit maintenance of source links, never verification or legacy fact writes."""
import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision
from .baichuan_models import Company
from .baichuan_service import BaichuanError, require_access
from .security import audit


def _conflict(detail):
    raise BaichuanError("legacy_source_conflict", detail, 409)


def _declaration(legacy):
    return {"id": str(legacy.pk), "category": legacy.category, "status": legacy.status,
        "grade": legacy.grade, "certificate_no": legacy.certificate_no,
        "valid_until": legacy.valid_until.isoformat() if legacy.valid_until else None,
        "source": legacy.source, "verified_on": legacy.verified_on.isoformat() if legacy.verified_on else None}


def _context(value, source):
    if value is None:
        return {}
    if (not isinstance(value, dict) or set(value) - {"source", "source_sha256", "locator", "import_ref"}
            or value.get("source") != source
            or value.get("source_sha256") != hashlib.sha256(source.encode()).hexdigest()
            or not isinstance(value.get("locator"), dict)
            or not value["locator"] or not isinstance(value.get("import_ref"), str)
            or not value["import_ref"] or len(value["import_ref"]) > 500):
        _conflict("显式来源定位未与原声明逐字及校验值一致，未补链。")
    # An explicit reviewed mapping supplies positions, never evidence authority.
    allowed = {"sheet", "row", "column", "cell", "section", "location", "table"}
    def valid_locator(locator):
        if not isinstance(locator, dict) or not locator or set(locator) - allowed:
            return False
        for key, item in locator.items():
            if key == "section":
                if not valid_locator(item):
                    return False
            elif key in {"row", "column", "table"}:
                if type(item) is not int or item < 1:
                    return False
            elif not isinstance(item, str) or not item or len(item) > 500:
                return False
        return True
    if not valid_locator(value["locator"]):
        _conflict("来源定位格式无效，不能猜测或赋予核验身份。")
    return value


def plan_legacy_source_links(company, *, source_context_by_legacy_id=None):
    """Read-only full preflight. Call again under the company lock before writes.

    Optional context must be supplied by an independently reviewed converter
    mapping. No parsing of arbitrary prose into sheet/row or company identity.
    """
    contexts = {} if source_context_by_legacy_id is None else source_context_by_legacy_id
    if not isinstance(contexts, dict):
        _conflict("来源映射必须按旧资质ID显式提供。")
    legacy_rows = {str(item.pk): item for item in company.qualifications.all()}
    if set(contexts) - set(legacy_rows):
        _conflict("来源映射包含其他企业或已删除的资质ID。")
    result = []
    for certificate in company.certificates.select_related("source_revision", "source_revision__supersedes", "evidence").order_by("pk"):
        if not certificate.legacy_qualification_id:
            continue
        legacy = legacy_rows.get(str(certificate.legacy_qualification_id))
        if legacy is None:
            _conflict("旧资质已删除，当前原声明无法复核，未补链。")
        linked_revision = certificate.source_revision
        revision = (linked_revision.supersedes if linked_revision and linked_revision.field == "legacy_source_evidence_link"
                    else linked_revision)
        if (not revision or revision.company_id != company.pk or revision.field != "legacy_qualification"
                or revision.object_id != legacy.pk or revision.review_status != "mapped_declaration"
                or revision.new_value != _declaration(legacy)
                or certificate.category != legacy.category or certificate.grade != (legacy.grade or "")
                or certificate.certificate_no != (legacy.certificate_no or "")
                or certificate.valid_until != legacy.valid_until or certificate.assertion_status != legacy.status
                or certificate.verification_status != "unverified" or certificate.verified_at is not None):
            _conflict("映射证书或原声明已变化，必须先复核冲突，未补链。")
        source = legacy.source or ""
        context = _context(contexts.get(str(legacy.pk)), source)
        if certificate.evidence_id:
            evidence = certificate.evidence
            expected_hash = hashlib.sha256(source.encode()).hexdigest()
            if (not linked_revision or linked_revision.field != "legacy_source_evidence_link"
                    or linked_revision.evidence_id != evidence.pk or linked_revision.object_id != certificate.pk
                    or linked_revision.review_status != "mapped_source" or linked_revision.verification_status != "unverified"
                    or linked_revision.company_id != company.pk or linked_revision.supersedes_id != revision.pk
                    or linked_revision.new_value != {"evidence_id": str(evidence.pk), "source_revision_id": str(revision.pk),
                        "legacy_qualification_id": str(legacy.pk), "source_sha256": expected_hash}
                    or evidence.scope != settings.BAICHUAN_ASSISTANT_SCOPE or evidence.source_type != "legacy_import"
                    or evidence.excerpt != source or evidence.content_hash != expected_hash
                    or evidence.subject.get("company_id") != str(company.pk)
                    or evidence.subject.get("legacy_qualification_id") != str(legacy.pk)
                    or evidence.subject.get("source_revision_id") != str(revision.pk)
                    or evidence.subject.get("identity_verified") is not False
                    or evidence.verified_on is not None or evidence.access_status != "unverified"
                    or (context and (evidence.locator != context["locator"] or evidence.import_ref != context["import_ref"]))):
                _conflict("已有证据不是本次原声明的同范围补链，保留原值并要求复核。")
            result.append({"certificate": certificate, "action": "already_linked"})
            continue
        result.append({"certificate": certificate, "legacy": legacy, "source": source,
                       "context": context, "action": "link" if source.strip() else "empty_source"})
    return result


@transaction.atomic
def backfill_legacy_source_evidence(company, actor, *, expected_version=None, source_context_by_legacy_id=None):
    """Add unverified evidence/revision links atomically, with idempotent replay.

    This maintenance operation is separate from automatic verified fact writes;
    it never sets verified/identity authority, replaces manual values, updates a
    company version, or revises a saved match snapshot.
    """
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    version = company.version if expected_version is None else expected_version
    if type(version) is not int or version < 1:
        raise BaichuanError("invalid_request", "企业版本必须为正整数。", 400)
    locked = Company.objects.select_for_update().get(pk=company.pk)
    if locked.version != version:
        raise BaichuanError("version_conflict", "企业已更新，请重新读取后补链。", 409)
    list(BaichuanCertificate.objects.select_for_update().filter(company=locked).values_list("pk", flat=True))
    plan = plan_legacy_source_links(locked, source_context_by_legacy_id=source_context_by_legacy_id)
    # A company lock may have waited behind an editor; do not retain the
    # maintenance authorization from before that wait or the full preflight.
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    counts = {"created": 0, "already_linked": 0, "empty_source": 0}
    for entry in plan:
        if entry["action"] != "link":
            counts[entry["action"]] += 1
            continue
        certificate, legacy, source, context = (entry[key] for key in ("certificate", "legacy", "source", "context"))
        original = certificate.source_revision
        content_hash = hashlib.sha256(source.encode()).hexdigest()
        key = f"baichuan:legacy-source:{settings.BAICHUAN_ASSISTANT_SCOPE}:{locked.pk}:{legacy.pk}:{content_hash}"
        evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, key)
        locator = dict(context.get("locator") or {"location": f"legacy_qualification:{legacy.pk}/source;revision:{original.pk}"})
        evidence = BaichuanEvidence.objects.create(id=evidence_id, scope=settings.BAICHUAN_ASSISTANT_SCOPE,
            source_type="legacy_import", import_ref=context.get("import_ref") or f"legacy-qualification:{legacy.pk}",
            title="原始资质声明（未经独立核实）", retrieved_at=timezone.now(), verified_on=None,
            content_hash=content_hash, excerpt=source, locator=locator,
            subject={"company_id": str(locked.pk), "identity_verified": False,
                "holder_type": "bidder", "legacy_qualification_id": str(legacy.pk),
                "source_revision_id": str(original.pk)}, access_status="unverified", created_by=actor)
        revision = BaichuanFactRevision.objects.create(company=locked, field="legacy_source_evidence_link",
            object_id=certificate.pk, old_value={"evidence_id": None, "source_revision_id": str(original.pk)},
            new_value={"evidence_id": str(evidence.pk), "source_revision_id": str(original.pk),
                "legacy_qualification_id": str(legacy.pk), "source_sha256": content_hash},
            evidence=evidence, actor=actor, baseline_version=locked.version, verification_status="unverified",
            review_status="mapped_source", reason="Retained source declaration; linked evidence is not independent verification.",
            supersedes=original)
        certificate.evidence, certificate.source_revision = evidence, revision
        certificate.save(update_fields=["evidence", "source_revision", "updated_at"])
        audit(actor, "baichuan_legacy_source_linked", certificate.pk,
              changes=[str(evidence.pk), str(revision.pk), str(original.pk)])
        counts["created"] += 1
    return counts
