"""Document grants shared by business APIs and their MCP callers.

A department policy is an explicit cutover: once present, an empty or disabled
policy denies access and never falls back to legacy environment grants.
"""
import hashlib
import json
import re

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant
from .models import User
from .security import can_use_department


class KnowledgeAccessDenied(Exception):
    pass


def authorize(user, department, *, action="ai_use"):
    policy = KnowledgeAccessPolicy.objects.filter(department_code=department).first()
    if policy is None:
        if getattr(settings, "KNOWLEDGE_AUTHORIZATION_REQUIRED", True):
            raise KnowledgeAccessDenied()
        return None
    if not policy.enabled or action not in {"read", "ai_use", "download"}:
        raise KnowledgeAccessDenied()
    current = User.objects.filter(pk=getattr(user, "pk", None), is_active=True,
                                  must_change_password=False).first()
    capability = "cost" if department == "engineering" else department
    if (current is None or not can_use_department(current, capability)
            or current.session_version != user.session_version
            or current.grant_version != user.grant_version):
        raise KnowledgeAccessDenied()
    principals = (Q(user=current) | Q(role__user=current)
                  | Q(project__owner=current)
                  | Q(project__knowledge_members__user=current,
                      project__knowledge_members__enabled=True))
    if current.department_code:
        principals |= Q(recipient_department=current.department_code)
    rows = KnowledgeDocumentGrant.objects.filter(
        principals, policy=policy, enabled=True, can_read=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    if action == "ai_use":
        rows = rows.filter(can_ai_use=True)
    elif action == "download":
        rows = rows.filter(can_download=True)
    datasets = {}
    for dataset, document in rows.values_list("dataset_id", "document_id").distinct():
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in (dataset, document)):
            raise KnowledgeAccessDenied()
        datasets.setdefault(dataset, set()).add(document)
    # Keep outbound retrieval bounded, matching the existing product contract.
    if not datasets or len(datasets) > 4 or any(len(docs) > 100 for docs in datasets.values()):
        raise KnowledgeAccessDenied()
    scope = {"datasets": {key: sorted(value) for key, value in sorted(datasets.items())},
             "policy_id": policy.pk, "action": action,
             "allow_assistant_export": policy.allow_assistant_export,
             "user_id": current.pk, "session_version": current.session_version,
             "grant_version": current.grant_version,
             "policy_updated": policy.updated_at.isoformat()}
    scope["revision"] = hashlib.sha256(json.dumps(
        scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return scope


def recheck(user, department, snapshot, *, action="ai_use"):
    if authorize(user, department, action=action) != snapshot:
        raise KnowledgeAccessDenied()
