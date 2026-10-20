from django.contrib import admin

from .admin import ManagedAdmin, site
from .knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant, ProjectMembership
from .agent_models import AgentProject


@admin.register(AgentProject, site=site)
class KnowledgeProjectAdmin(ManagedAdmin):
    admin_label = admin_label_plural = "资料项目"
    fields = ("name", "owner", "department_code")
    list_display = ("name", "owner", "department_code")
    raw_id_fields = ("owner",)

    def get_readonly_fields(self, request, obj=None):
        return ("owner", "department_code") if obj else ()


@admin.register(KnowledgeAccessPolicy, site=site)
class KnowledgeAccessPolicyAdmin(ManagedAdmin):
    admin_label = admin_label_plural = "资料授权策略"
    list_display = ("department_code", "enabled")
    fields = ("department_code", "enabled", "allow_assistant_export")

    def get_readonly_fields(self, request, obj=None):
        # Moving an existing policy would silently move all of its grants.
        return ("department_code",) if obj else ()


@admin.register(KnowledgeDocumentGrant, site=site)
class KnowledgeDocumentGrantAdmin(ManagedAdmin):
    admin_label = admin_label_plural = "文档授权"
    fields = ("policy", "dataset_id", "document_id", "user", "role", "recipient_department", "project",
              "can_read", "can_ai_use", "can_download", "enabled", "expires_at")
    list_display = ("id", "policy", "user", "role", "recipient_department", "project", "can_read", "can_ai_use", "can_download", "enabled", "expires_at")
    list_filter = ("policy", "enabled", "can_read", "can_ai_use", "can_download")
    raw_id_fields = ("user", "project")
    search_fields = ("dataset_id", "document_id")


@admin.register(ProjectMembership, site=site)
class ProjectMembershipAdmin(ManagedAdmin):
    admin_label = admin_label_plural = "项目资料成员"
    fields = ("project", "user", "enabled")
    list_display = ("id", "project", "user", "enabled")
    raw_id_fields = ("project", "user")
