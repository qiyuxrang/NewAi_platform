"""Explicit versioned grade rules; unsupported relationships stay unknown."""
import hashlib
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .baichuan_assistant_models import BaichuanEvidence, BaichuanQualificationRule
from .baichuan_models import QUALIFICATION_GRADES, QUALIFICATION_LABELS
from .baichuan_service import require_access


ALIASES = {
    "electronic": ("电子与智能化", "电子智能化", "电子与智能化工程专业承包"),
    "labor": ("施工劳务", "劳务资质", "施工劳务资质"),
    "cs": ("cs", "CS", "信息系统建设和服务能力"),
    "cmmi": ("cmmi", "CMMI", "软件能力成熟度"),
    "ccrc": ("ccrc", "CCRC", "信息安全服务资质"),
    "itss": ("itss", "ITSS", "信息技术服务运行维护"),
    "security": ("安防", "安防工程企业设计施工维护能力"),
}
CS_SOURCE = "https://www.cc.cesi.cn/service/show-4611.aspx"


def canonical_category(value):
    for category, aliases in ALIASES.items():
        if value == category or value in aliases:
            return category
    return value


@transaction.atomic
def install_compatibility_rules(actor):
    """Explicit maintenance operation, never a migration or import side effect.

    All seven exact-grade sets preserve existing hand-filter semantics. Only CS
    ordering has a retrieved primary source here; the others intentionally have
    no at-least relation until their standard/version is verified.
    """
    actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    require_access(actor, write=True)
    created = []
    for category, grades in QUALIFICATION_GRADES.items():
        if BaichuanQualificationRule.objects.filter(category=category, version=1).exists():
            continue
        payload = {"category": category, "grades": list(grades), "aliases": list(ALIASES[category]),
                   "exact_basis": "existing-seven-category-filter-v1", "at_least": {}}
        if category == "cs":
            payload["at_least"] = {"1": ["1", "2", "3", "4", "5"], "2": ["2", "3", "4", "5"],
                                   "3": ["3", "4", "5"], "4": ["4", "5"], "5": ["5"]}
        content = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        evidence = BaichuanEvidence.objects.create(scope=settings.BAICHUAN_ASSISTANT_SCOPE,
            source_type="rule_basis", url=CS_SOURCE if category == "cs" else "",
            import_ref="repository:portal/baichuan_models.py:QUALIFICATION_GRADES@ef1676cd",
            publisher="北京赛西认证有限责任公司" if category == "cs" else "项目既有手工筛选契约",
            title=QUALIFICATION_LABELS[category] + "规则版本1", retrieved_at=timezone.now(),
            verified_on=timezone.localdate(), content_hash=hashlib.sha256(content.encode()).hexdigest(),
            excerpt="既有七类精确等级保持原手工筛选语义。" + ("CS 等级从 CS1 到 CS5 递增。" if category == "cs" else "尚未启用等级高低映射。"),
            locator={"code": "QUALIFICATION_GRADES", "primary_section": "能力等级" if category == "cs" else ""},
            subject={"kind": "qualification_rule", "category": category}, access_status="verified", created_by=actor)
        rule = BaichuanQualificationRule.objects.create(category=category, version=1,
            aliases=payload["aliases"], legal_grades=payload["grades"],
            grade_relations={"at_least": payload["at_least"]}, evidence=evidence)
        created.append(rule.pk)
    return created
