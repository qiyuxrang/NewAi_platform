"""Deployment-scoped company resources; creator fields are audit metadata."""
import uuid

from django.conf import settings
from django.db import models


QUALIFICATION_GRADES = {
    "electronic": ("1", "2"), "labor": (), "cs": ("1", "2", "3", "4", "5"),
    "cmmi": ("3", "4", "5"), "ccrc": ("1", "2", "3"),
    "itss": ("1", "2", "3", "4"), "security": ("1", "2", "3"),
}
QUALIFICATION_LABELS = {
    "electronic": "电子与智能化工程专业承包", "labor": "施工劳务资质",
    "cs": "CS 信息系统建设和服务能力等级认证", "cmmi": "CMMI 软件能力成熟度模型",
    "ccrc": "CCRC 信息系统安全集成服务", "itss": "ITSS 信息技术运行维护服务符合性认证",
    "security": "安防工程企业设计施工维护能力",
}
WEBSITE_KINDS = {"corporate": "企业独立官网", "group_profile": "集团专属介绍页", "official_wechat": "官方公众号"}


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    credit_code = models.CharField(max_length=18, null=True, blank=True, unique=True)
    province = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    website = models.URLField(max_length=2000, null=True, blank=True)
    website_kind = models.CharField(max_length=20, choices=list(WEBSITE_KINDS.items()), default="corporate")
    phone = models.CharField(max_length=100, null=True, blank=True)
    contact_name = models.CharField(max_length=100, null=True, blank=True)
    contact_phone = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="baichuan_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["name", "id"], name="baichuan_company_sort")]
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="baichuan_company_name"),
                       models.CheckConstraint(condition=models.Q(version__gte=1), name="baichuan_company_version")]


class CompanyQualification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="qualifications")
    category = models.CharField(max_length=20, choices=[(key, QUALIFICATION_LABELS[key]) for key in QUALIFICATION_GRADES])
    status = models.CharField(max_length=10, choices=[(value, value) for value in ("UNKNOWN", "ABSENT", "PRESENT")])
    grade = models.CharField(max_length=1, null=True, blank=True)
    certificate_no = models.CharField(max_length=200, null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["category", "id"]
        indexes = [models.Index(fields=["category", "status", "grade", "company"], name="baichuan_qual_filter")]
        constraints = [models.CheckConstraint(condition=models.Q(category__in=list(QUALIFICATION_GRADES)), name="baichuan_qual_category"),
            models.CheckConstraint(
            condition=models.Q(status__in=["UNKNOWN", "ABSENT", "PRESENT"]), name="baichuan_qual_status"),
            models.CheckConstraint(condition=(models.Q(status="PRESENT") | models.Q(grade__isnull=True)), name="baichuan_qual_no_grade"),
            models.CheckConstraint(condition=(
                models.Q(category="labor", grade__isnull=True)
                | models.Q(category="electronic", grade__in=["1", "2"])
                | models.Q(category="cs", grade__in=["1", "2", "3", "4", "5"])
                | models.Q(category="cmmi", grade__in=["3", "4", "5"])
                | models.Q(category="ccrc", grade__in=["1", "2", "3"])
                | models.Q(category="itss", grade__in=["1", "2", "3", "4"])
                | models.Q(category="security", grade__in=["1", "2", "3"])
                | models.Q(category__in=list(QUALIFICATION_GRADES), grade__isnull=True)
            ), name="baichuan_qual_grade")]


class CompanyPerson(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="people")
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=200, null=True, blank=True)
    position = models.CharField(max_length=200, null=True, blank=True)
    reports_to_text = models.CharField(max_length=500, null=True, blank=True)
    specialties = models.TextField(null=True, blank=True)
    credentials = models.TextField(null=True, blank=True)
    achievements = models.TextField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)
    verified_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="baichuan_person_name")]
