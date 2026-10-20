"""Explicit, reviewed public-publication imports; never online acquisition."""
import hashlib
import ipaddress
import json
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .baichuan_assistant_models import BaichuanEvidence, BaichuanFactRevision
from .baichuan_facts import propose_field
from .baichuan_models import Company
from .baichuan_service import BaichuanError, require_access
from .security import audit

FIELDS = {"website", "address", "email", "description", "phone", "province", "city"}
PUBLICATION_KINDS = {"corporate", "government", "industry", "directory", "encyclopedia", "group", "unknown"}


def reject():
    raise BaichuanError("invalid_reviewed_enrichment", "复核批次或公开原文依据不合法，未提交该企业。", 400)


def _name(value):
    return re.sub(r"\s+", "", value.translate(str.maketrans("（）", "()")))


def public_source_url(value, *, allow_http=False):
    if not isinstance(value, str) or len(value) > 2000 or any(ord(c) <= 32 or c == "\\" for c in value):
        reject()
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        schemes = {"http", "https"} if allow_http else {"https"}
        default_port = 80 if parsed.scheme == "http" else 443
        if (parsed.scheme not in schemes or not host or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, default_port) or host.endswith(".") or "%" in host):
            reject()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if not address.is_global or address.is_multicast:
                reject()
        elif ("." not in host or host.endswith((".local", ".localhost", ".internal", ".test", ".invalid", ".example", ".home.arpa"))
              or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host, re.I)
              or not re.fullmatch(r"[a-z][a-z0-9-]*", host.rsplit(".", 1)[-1], re.I)
              or any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-") for part in host.split("."))):
            reject()
        return parsed
    except (ValueError, TypeError):
        reject()


def _date(value):
    try:
        result = datetime.fromisoformat(value)
        if timezone.is_naive(result) or result > timezone.now() + timedelta(minutes=1):
            reject()
        return result
    except (ValueError, TypeError):
        reject()


def validate_batch(batch):
    if (not isinstance(batch, dict) or set(batch) != {"schema_version", "source_workbook_sha256", "review_status", "reviewer", "reviewed_at", "items"}
            or type(batch["schema_version"]) is not int or batch["schema_version"] != 1
            or not isinstance(batch["source_workbook_sha256"], str)
            or not re.fullmatch("[a-f0-9]{64}", batch["source_workbook_sha256"])
            or batch["review_status"] != "reviewed_public_source" or batch["reviewer"] != "assistant_source_review"
            or not isinstance(batch["items"], list) or not 1 <= len(batch["items"]) <= 50):
        reject()
    reviewed = _date(batch["reviewed_at"])
    identifiers = set()
    for item in batch["items"]:
        if (not isinstance(item, dict) or set(item) != {"company_id", "name", "expected_version", "sources", "fields"}
                or not isinstance(item["name"], str) or not item["name"].strip() or len(item["name"]) > 200
                or type(item["expected_version"]) is not int or item["expected_version"] < 1
                or not isinstance(item["sources"], list) or not 1 <= len(item["sources"]) <= 10
                or not isinstance(item["fields"], dict) or not item["fields"] or set(item["fields"]) - FIELDS):
            reject()
        try:
            identifier = str(uuid.UUID(item["company_id"]))
        except (ValueError, TypeError, AttributeError):
            reject()
        if identifier != item["company_id"] or identifier in identifiers:
            reject()
        identifiers.add(identifier)
        sources = {}
        for source in item["sources"]:
            required = {"id", "url", "title", "read_status", "retrieved_at", "body", "content_sha256", "excerpt", "locator", "official_site_basis"}
            if (not isinstance(source, dict) or not required <= set(source) or set(source) - required - {"publication_kind"}
                    or not isinstance(source["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source["id"])
                    or source["id"] in sources or source["read_status"] != "completed"
                    or not isinstance(source["official_site_basis"], str)
                    or source["official_site_basis"] not in {"legal_name_publication", "user_confirmed"}
                    or not isinstance(source.get("publication_kind", "unknown"), str)
                    or source.get("publication_kind", "unknown") not in PUBLICATION_KINDS
                    or not isinstance(source["title"], str) or not 1 <= len(source["title"]) <= 300
                    or not isinstance(source["body"], str) or not 1 <= len(source["body"].encode("utf-8")) <= 524288
                    or not isinstance(source["excerpt"], str) or not 1 <= len(source["excerpt"]) <= 64000
                    or hashlib.sha256(source["body"].encode()).hexdigest() != source["content_sha256"]
                    or _name(item["name"]) not in _name(source["body"])
                    or _name(item["name"]) not in _name(source["excerpt"])):
                reject()
            # This offline importer preserves an actually read corporate HTTP
            # URL. It never fetches it, upgrades its scheme, or disables TLS.
            public_source_url(source["url"], allow_http=source.get("publication_kind") == "corporate")
            if _date(source["retrieved_at"]) > reviewed:
                reject()
            locator = source["locator"]
            if (not isinstance(locator, dict) or set(locator) - {"text_start", "text_end", "section", "page"}
                    or type(locator.get("text_start")) is not int or type(locator.get("text_end")) is not int
                    or not 0 <= locator["text_start"] < locator["text_end"] <= len(source["body"])
                    or source["body"][locator["text_start"]:locator["text_end"]] != source["excerpt"]
                    or ("section" in locator and (not isinstance(locator["section"], str) or not 1 <= len(locator["section"]) <= 500))
                    or ("page" in locator and (type(locator["page"]) is not int or locator["page"] < 1))):
                reject()
            sources[source["id"]] = source
        for field, claim in item["fields"].items():
            if (not isinstance(claim, dict) or set(claim) != {"value", "source_id"}
                    or not isinstance(claim["value"], str) or not claim["value"].strip() or len(claim["value"]) > 20000
                    or not isinstance(claim["source_id"], str) or claim["source_id"] not in sources):
                reject()
            source = sources[claim["source_id"]]
            if field == "website":
                url = public_source_url(claim["value"], allow_http=source.get("publication_kind") == "corporate")
                original = public_source_url(source["url"], allow_http=source.get("publication_kind") == "corporate")
                if (source.get("publication_kind") not in (None, "corporate")
                        or (url.scheme, url.hostname, url.port or (80 if url.scheme == "http" else 443))
                        != (original.scheme, original.hostname, original.port or (80 if original.scheme == "http" else 443))
                        or url.path not in ("", "/") or url.query or url.fragment):
                    reject()
            elif claim["value"] not in source["excerpt"]:
                reject()
    return batch


def stamp_id(company_id, batch_sha256):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"baichuan:reviewed-enrichment:{settings.BAICHUAN_ASSISTANT_SCOPE}:{batch_sha256}:{company_id}")


def item_digest(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@transaction.atomic
def apply_reviewed_company(actor, batch, item, batch_sha256):
    """One company commit with durable replay stamp; caller owns full preflight."""
    validate_batch(batch)
    if item not in batch["items"] or not re.fullmatch("[a-f0-9]{64}", batch_sha256):
        reject()
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    company = Company.objects.select_for_update().get(pk=item["company_id"])
    if company.name != item["name"]:
        reject()
    marker = BaichuanFactRevision.objects.filter(pk=stamp_id(company.pk, batch_sha256)).first()
    if marker:
        if (marker.company_id != company.pk or marker.field != "reviewed_enrichment_batch"
                or marker.new_value.get("item_sha256") != item_digest(item)
                or marker.new_value.get("batch_sha256") != batch_sha256):
            reject()
        return {**marker.new_value["counts"], "replayed": True}
    # Old immutable archives remain readable/replayable. A new website write
    # must explicitly classify its reviewed source as the company's own site.
    website = item["fields"].get("website")
    if website and next(source for source in item["sources"] if source["id"] == website["source_id"]).get("publication_kind") != "corporate":
        reject()
    if company.version != item["expected_version"]:
        raise BaichuanError("version_conflict", "企业资料已变，保留原值并停止该批次。", 409)
    if not settings.BAICHUAN_FACT_WRITE_ENABLED:
        raise BaichuanError("reviewed_write_disabled", "维护写入未在本子进程启用。", 409)
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    counts = {"applied": 0, "conflict": 0, "unchanged": 0}
    sources = {source["id"]: source for source in item["sources"]}
    evidence_by_source, revisions = {}, []
    for field, claim in sorted(item["fields"].items()):
        if getattr(company, field) == claim["value"]:
            counts["unchanged"] += 1
            continue
        source = sources[claim["source_id"]]
        if source["id"] not in evidence_by_source:
            assertions = {name: [entry["value"]] for name, entry in item["fields"].items() if entry["source_id"] == source["id"]}
            evidence_by_source[source["id"]] = BaichuanEvidence.objects.create(
                scope=settings.BAICHUAN_ASSISTANT_SCOPE, source_type="reviewed_public_page", url=source["url"],
                title=source["title"], retrieved_at=_date(source["retrieved_at"]), verified_on=_date(batch["reviewed_at"]).date(),
                content_hash=source["content_sha256"], excerpt=source["excerpt"], locator=source["locator"], access_status="verified",
                subject={"company_id": str(company.pk), "identity_verified": True,
                    "identity_method": "full_legal_name_on_public_page", "matched_name": company.name,
                    "legal_identity_verified": False, "publication_status": "reviewed_public_publication",
                    "publication_kind": source.get("publication_kind", "unknown"),
                    "source_review": "assistant_source_review", "official_site_basis": source["official_site_basis"],
                    "field_assertions": assertions, "batch_sha256": batch_sha256,
                    "source_workbook_sha256": batch["source_workbook_sha256"],
                    "transport_status": "http_unencrypted" if urlsplit(source["url"]).scheme == "http" else "https_url_recorded",
                    "website_basis": ("same_http_origin" if urlsplit(source["url"]).scheme == "http" else "same_https_origin")
                        if "website" in assertions else None}, created_by=actor)
        revision = propose_field(actor, company.pk, field, claim["value"], evidence_by_source[source["id"]],
                                 company.version, scope=settings.BAICHUAN_ASSISTANT_SCOPE)
        if revision.review_status not in {"applied", "conflict"}:
            reject()
        counts[revision.review_status] += 1
        revisions.append(str(revision.pk))
        company.refresh_from_db()
    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    BaichuanFactRevision.objects.create(id=stamp_id(company.pk, batch_sha256), company=company,
        field="reviewed_enrichment_batch", actor=actor, baseline_version=item["expected_version"],
        new_value={"batch_sha256": batch_sha256, "item_sha256": item_digest(item), "counts": counts,
                   "company_version_after": company.version, "revision_ids": revisions},
        verification_status="unverified", review_status="reviewed_public_source",
        reason="Assistant reviewed original public publication only; no legal identity or certificate verification.")
    audit(actor, "baichuan_reviewed_enrichment", company.pk, changes=revisions)
    return {**counts, "replayed": False}
