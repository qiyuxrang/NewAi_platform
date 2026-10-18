"""Additive Baichuan assistant records. No existing company facts are rewritten.

Private storage references are internal keys, never public download URLs.
Legacy child IDs deliberately are scalar UUIDs: replacing a legacy edit snapshot
must not erase its evidence or block the existing editor's child replacement.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


VERIFICATION_STATUSES = ("verified", "unverified", "conflict", "inaccessible", "superseded")
JOB_STATUSES = ("queued", "running", "awaiting_input", "partial", "completed", "failed", "cancel_requested", "cancelled")


def choices(values):
    return [(value, value) for value in values]


class AssistantRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class AppendOnlyQuerySet(models.QuerySet):
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        if update_conflicts:
            raise ValidationError("Append-only assistant records cannot be upserted.")
        return super().bulk_create(objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=False, update_fields=update_fields, unique_fields=unique_fields)

    def update(self, **kwargs):
        raise ValidationError("Append-only assistant records cannot be updated.")

    def delete(self):
        raise ValidationError("Append-only assistant records cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Append-only assistant records cannot be updated.")


class AppendOnlyRecord(AssistantRecord):
    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding or kwargs.get("force_update"):
            raise ValidationError("Create a new revision instead of changing history.")
        # A freshly constructed instance with an existing UUID must also never
        # use Django's normal UPDATE-then-INSERT behavior.
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Assistant history must be retained.")

    class Meta:
        abstract = True


class BaichuanEvidence(AppendOnlyRecord):
    scope = models.CharField(max_length=100, default="default")
    source_type = models.CharField(max_length=30, default="web")
    url = models.URLField(max_length=2000, blank=True)
    import_ref = models.CharField(max_length=500, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    title = models.CharField(max_length=500, blank=True)
    retrieved_at = models.DateTimeField()
    published_on = models.DateField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    excerpt = models.TextField(blank=True)
    locator = models.JSONField(default=dict)
    subject = models.JSONField(default=dict)
    access_status = models.CharField(max_length=30, default="unknown")
    storage_ref = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="baichuan_evidence")

    class Meta:
        indexes = [models.Index(fields=["scope", "content_hash"], name="bc_evidence_hash")]


class BaichuanFactRevision(AppendOnlyRecord):
    company = models.ForeignKey("portal.Company", on_delete=models.PROTECT, related_name="fact_revisions")
    field = models.CharField(max_length=100)
    object_id = models.UUIDField(null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    evidence = models.ForeignKey(BaichuanEvidence, null=True, blank=True, on_delete=models.PROTECT, related_name="fact_revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_fact_revisions")
    execution_identity = models.CharField(max_length=200, blank=True)
    baseline_version = models.PositiveIntegerField()
    verification_status = models.CharField(max_length=20, choices=choices(VERIFICATION_STATUSES), default="unverified")
    review_status = models.CharField(max_length=20, default="proposed")
    reason = models.TextField(blank=True)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(baseline_version__gte=1), name="bc_revision_baseline")]
        indexes = [models.Index(fields=["company", "field", "created_at"], name="bc_revision_field")]


class BaichuanCertificate(AssistantRecord):
    company = models.ForeignKey("portal.Company", on_delete=models.PROTECT, related_name="certificates")
    category = models.CharField(max_length=100, blank=True)
    raw_category = models.CharField(max_length=500, blank=True)
    holder_type = models.CharField(max_length=30, default="unknown")
    holder_name = models.CharField(max_length=300, blank=True)
    holder_company_id = models.UUIDField(null=True, blank=True)
    standard = models.CharField(max_length=500, blank=True)
    scope_text = models.TextField(blank=True)
    grade = models.CharField(max_length=100, blank=True)
    raw_grade = models.CharField(max_length=200, blank=True)
    certificate_no = models.CharField(max_length=300, blank=True)
    issuer = models.CharField(max_length=500, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    assertion_status = models.CharField(max_length=10, choices=choices(("PRESENT", "ABSENT", "UNKNOWN")), default="UNKNOWN")
    verification_status = models.CharField(max_length=20, choices=choices(VERIFICATION_STATUSES), default="unverified")
    verified_at = models.DateTimeField(null=True, blank=True)
    revocation_status = models.CharField(max_length=20, choices=choices(("unknown", "clear", "revoked", "suspended")), default="unknown")
    evidence = models.ForeignKey(BaichuanEvidence, null=True, blank=True, on_delete=models.PROTECT, related_name="certificates")
    source_revision = models.ForeignKey(BaichuanFactRevision, null=True, blank=True, on_delete=models.PROTECT, related_name="certificates")
    legacy_qualification_id = models.UUIDField(null=True, blank=True, unique=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["company", "category", "verification_status"], name="bc_certificate_lookup")]
        constraints = [
            models.CheckConstraint(condition=models.Q(assertion_status__in=["PRESENT", "ABSENT", "UNKNOWN"]), name="bc_cert_assertion"),
            models.CheckConstraint(condition=models.Q(verification_status__in=VERIFICATION_STATUSES), name="bc_cert_verification"),
            models.CheckConstraint(condition=models.Q(valid_from__isnull=True) | models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=models.F("valid_from")), name="bc_cert_date_order"),
        ]


class BaichuanQualificationRule(AppendOnlyRecord):
    category = models.CharField(max_length=100)
    version = models.PositiveIntegerField(default=1)
    aliases = models.JSONField(default=list)
    legal_grades = models.JSONField(default=list)
    grade_relations = models.JSONField(default=dict)
    standard = models.CharField(max_length=500, blank=True)
    applicable_from = models.DateField(null=True, blank=True)
    applicable_until = models.DateField(null=True, blank=True)
    evidence = models.ForeignKey(BaichuanEvidence, on_delete=models.PROTECT, related_name="qualification_rules")
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["category", "version"], name="bc_rule_category_version"),
                       models.CheckConstraint(condition=models.Q(version__gte=1), name="bc_rule_version")]


class BaichuanConversation(AssistantRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_conversations")
    scope = models.CharField(max_length=100, default="default")
    title = models.CharField(max_length=200, blank=True)
    condition_revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "scope", "updated_at"], name="bc_conversation_owner")]


class BaichuanMessage(AssistantRecord):
    conversation = models.ForeignKey(BaichuanConversation, on_delete=models.PROTECT, related_name="messages")
    role = models.CharField(max_length=20, choices=choices(("user", "assistant", "system")))
    content = models.TextField(blank=True)
    condition_revision = models.PositiveIntegerField(default=0)
    client_request_id = models.CharField(max_length=100, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["conversation", "client_request_id"], name="bc_message_request")]


class BaichuanAttachment(AssistantRecord):
    conversation = models.ForeignKey(BaichuanConversation, on_delete=models.PROTECT, related_name="attachments")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_attachments")
    original_name = models.CharField(max_length=255)
    media_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    storage_ref = models.CharField(max_length=500)
    parse_status = models.CharField(max_length=30, default="pending")
    extracted_text = models.TextField(blank=True)
    locators = models.JSONField(default=list)
    error_code = models.CharField(max_length=100, blank=True)


class BaichuanJob(AssistantRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_jobs")
    execution_actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="baichuan_executed_jobs")
    scope = models.CharField(max_length=100, default="default")
    conversation = models.ForeignKey(BaichuanConversation, null=True, blank=True, on_delete=models.PROTECT, related_name="jobs")
    message = models.ForeignKey(BaichuanMessage, null=True, blank=True, on_delete=models.PROTECT, related_name="jobs")
    parent_job = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="retries")
    kind = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=choices(JOB_STATUSES), default="queued")
    stage = models.CharField(max_length=30, blank=True)
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict)
    budget = models.JSONField(default=dict)
    checkpoint = models.JSONField(default=dict)
    counts = models.JSONField(default=dict)
    result_ref = models.JSONField(default=dict)
    error_code = models.CharField(max_length=100, blank=True)
    lease_owner = models.CharField(max_length=100, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    fence = models.PositiveBigIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "scope", "idempotency_key"], name="bc_job_idempotency"),
                       models.CheckConstraint(condition=models.Q(status__in=JOB_STATUSES), name="bc_job_status")]
        indexes = [models.Index(fields=["status", "lease_expires_at", "created_at"], name="bc_job_queue")]


class BaichuanJobItem(AssistantRecord):
    job = models.ForeignKey(BaichuanJob, on_delete=models.PROTECT, related_name="items")
    item_key = models.CharField(max_length=200)
    company = models.ForeignKey("portal.Company", null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, default="pending")
    stage = models.CharField(max_length=30, blank=True)
    checkpoint = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error_code = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "item_key"], name="bc_job_item_key")]


class BaichuanMatchSnapshot(AppendOnlyRecord):
    conversation = models.ForeignKey(BaichuanConversation, on_delete=models.PROTECT, related_name="snapshots")
    job = models.ForeignKey(BaichuanJob, on_delete=models.PROTECT, related_name="snapshots")
    condition_revision = models.PositiveIntegerField()
    result_revision = models.PositiveIntegerField()
    condition_tree = models.JSONField(default=dict)
    rule_versions = models.JSONField(default=dict)
    candidate_ids = models.JSONField(default=list)
    results = models.JSONField(default=list)
    counts = models.JSONField(default=dict)
    fact_cutoff_at = models.DateTimeField()
    research_status = models.CharField(max_length=30, default="not_started")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "result_revision"], name="bc_snapshot_revision"),
                       models.CheckConstraint(condition=models.Q(condition_revision__gte=1, result_revision__gte=1), name="bc_snapshot_positive")]


class BaichuanResearchManifest(AppendOnlyRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_manifests")
    scope = models.CharField(max_length=100, default="default")
    job = models.OneToOneField(BaichuanJob, on_delete=models.PROTECT, related_name="research_manifest")
    parent_manifest = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="increments")
    company_versions = models.JSONField(default=list)
    total_count = models.PositiveIntegerField()
    fields = models.JSONField(default=list)


class BaichuanResearchItem(AssistantRecord):
    manifest = models.ForeignKey(BaichuanResearchManifest, on_delete=models.PROTECT, related_name="items")
    company = models.ForeignKey("portal.Company", on_delete=models.PROTECT, related_name="research_items")
    company_version = models.PositiveIntegerField()
    field = models.CharField(max_length=100)
    status = models.CharField(max_length=30, default="pending")
    verification_status = models.CharField(max_length=20, choices=choices(VERIFICATION_STATUSES), default="unverified")
    evidence = models.ForeignKey(BaichuanEvidence, null=True, blank=True, on_delete=models.PROTECT)
    checkpoint = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    reason = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["manifest", "company", "field"], name="bc_research_item_key")]


class BaichuanExport(AssistantRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_exports")
    snapshot = models.ForeignKey(BaichuanMatchSnapshot, on_delete=models.PROTECT, related_name="exports")
    job = models.OneToOneField(BaichuanJob, on_delete=models.PROTECT, related_name="export")
    selection = models.JSONField(default=dict)
    fields = models.JSONField(default=list)
    storage_ref = models.CharField(max_length=500, blank=True)
    file_hash = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    generated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    authorization = models.JSONField(default=dict)


@transaction.atomic
def map_legacy_qualifications(company, actor):
    """Explicit, idempotent declaration mapping; never promotes verification.

    This is intentionally absent from the schema migration. The caller must
    authorize its dataset/identity before invoking the maintenance operation.
    """
    from .baichuan_models import Company
    from .baichuan_service import BaichuanError, require_access

    actor.refresh_from_db(fields=["is_active", "must_change_password", "session_version"])
    require_access(actor, write=True)
    locked = Company.objects.select_for_update().get(pk=company.pk)
    if locked.version != company.version:
        raise BaichuanError("version_conflict", "企业已更新，请重新读取后映射。", 409)
    company = locked
    created_ids = []
    for legacy in company.qualifications.all().order_by("id"):
        if BaichuanCertificate.objects.filter(legacy_qualification_id=legacy.pk).exists():
            continue
        declaration = {"id": str(legacy.pk), "category": legacy.category, "status": legacy.status,
                       "grade": legacy.grade, "certificate_no": legacy.certificate_no,
                       "valid_until": legacy.valid_until.isoformat() if legacy.valid_until else None,
                       "source": legacy.source, "verified_on": legacy.verified_on.isoformat() if legacy.verified_on else None}
        revision = BaichuanFactRevision.objects.create(company=company, field="legacy_qualification",
            object_id=legacy.pk, new_value=declaration, actor=actor, baseline_version=company.version,
            review_status="mapped_declaration", reason="Preserved legacy assertion; source has not been revalidated.")
        certificate = BaichuanCertificate.objects.create(company=company, category=legacy.category,
            raw_category=legacy.category, holder_type="bidder", holder_name=company.name,
            holder_company_id=company.pk, grade=legacy.grade or "", raw_grade=legacy.grade or "",
            certificate_no=legacy.certificate_no or "", valid_until=legacy.valid_until,
            assertion_status=legacy.status, legacy_qualification_id=legacy.pk, source_revision=revision)
        created_ids.append(certificate.pk)
    return created_ids
