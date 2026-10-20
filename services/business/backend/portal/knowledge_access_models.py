from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


DEPARTMENTS = [("product", "产品"), ("hr", "人事"), ("engineering", "工程"), ("finance", "财务")]
IDENTIFIER = RegexValidator(r"\A[A-Za-z0-9_-]{1,128}\Z", "请输入有效的资料库或文档标识。")


class KnowledgeAccessPolicy(models.Model):
    department_code = models.CharField("业务部门", max_length=20, choices=DEPARTMENTS, unique=True)
    enabled = models.BooleanField("启用资料访问", default=False)
    allow_assistant_export = models.BooleanField("允许向通用助手提供正文", default=False,
        help_text="通用助手未绑定业务模型路由；仅在其模型与运行环境获准处理这些资料后启用。")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "资料授权策略"
        verbose_name_plural = "资料授权策略"

    def __str__(self):
        return self.get_department_code_display()


class ProjectMembership(models.Model):
    project = models.ForeignKey("portal.AgentProject", verbose_name="项目", on_delete=models.PROTECT,
                                related_name="knowledge_members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="成员", on_delete=models.PROTECT)
    enabled = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "项目资料成员"
        verbose_name_plural = "项目资料成员"
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="knowledge_project_member")]


class KnowledgeDocumentGrant(models.Model):
    policy = models.ForeignKey(KnowledgeAccessPolicy, verbose_name="授权策略", on_delete=models.PROTECT)
    dataset_id = models.CharField("资料库标识", max_length=128, validators=[IDENTIFIER])
    document_id = models.CharField("文档标识", max_length=128, validators=[IDENTIFIER])
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="个人", null=True, blank=True,
                             on_delete=models.PROTECT)
    role = models.ForeignKey("portal.Role", verbose_name="角色", null=True, blank=True, on_delete=models.PROTECT)
    recipient_department = models.CharField("接收部门", max_length=20, choices=DEPARTMENTS, blank=True)
    project = models.ForeignKey("portal.AgentProject", verbose_name="项目成员", null=True, blank=True,
                                on_delete=models.PROTECT)
    can_read = models.BooleanField("允许查看", default=True)
    can_ai_use = models.BooleanField("允许 AI 使用", default=False)
    can_download = models.BooleanField("允许下载", default=False)
    enabled = models.BooleanField("启用", default=False)
    expires_at = models.DateTimeField("到期时间", null=True, blank=True)

    class Meta:
        verbose_name = "文档授权"
        verbose_name_plural = "文档授权"
        indexes = [models.Index(fields=["policy", "enabled", "dataset_id"], name="knowledge_grant_scope")]
        constraints = [models.CheckConstraint(condition=(
            models.Q(user__isnull=False, role__isnull=True, recipient_department="", project__isnull=True)
            | models.Q(user__isnull=True, role__isnull=False, recipient_department="", project__isnull=True)
            | (models.Q(user__isnull=True, role__isnull=True, project__isnull=True)
               & ~models.Q(recipient_department=""))
            | models.Q(user__isnull=True, role__isnull=True, recipient_department="", project__isnull=False)
        ), name="knowledge_grant_one_recipient")]

    def clean(self):
        super().clean()
        if sum(bool(value) for value in (self.user_id, self.role_id, self.recipient_department, self.project_id)) != 1:
            raise ValidationError("个人、角色、接收部门和项目只能选择一项。")
        if (self.can_ai_use or self.can_download) and not self.can_read:
            raise ValidationError("AI 使用或下载必须同时允许查看。")

    def __str__(self):
        return f"文档授权 #{self.pk}"
