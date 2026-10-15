"""Local, owner-private knowledge conversations (import from portal.models at integration)."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductKnowledgeConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, default="新对话")
    scope = models.JSONField(default=dict)
    turns = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=0)
    pending_id = models.UUIDField(null=True, blank=True)
    pending_request_id = models.UUIDField(null=True, blank=True)
    pending_until = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def archive(self, version):
        now = timezone.now()
        return (type(self).objects.filter(pk=self.pk, owner_id=self.owner_id, version=version,
                                         archived_at__isnull=True)
                .filter(models.Q(pending_id__isnull=True) | models.Q(pending_until__lte=now))
                .update(archived_at=now, version=models.F("version") + 1,
                        pending_id=None, pending_request_id=None, pending_until=None, updated_at=now))

    class Meta:
        app_label = "portal"
        ordering = ["-updated_at", "id"]
