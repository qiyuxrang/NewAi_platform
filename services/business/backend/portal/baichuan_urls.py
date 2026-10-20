from django.urls import path

from . import baichuan_api
from . import baichuan_assistant_api as assistant
from . import baichuan_export_api as assistant_export

urlpatterns = [
    path("assistant/config/", assistant.config),
    path("assistant/conversations/", assistant.conversations),
    path("assistant/conversations/<uuid:conversation_id>/", assistant.conversation),
    path("assistant/conversations/<uuid:conversation_id>/messages/", assistant.messages),
    path("assistant/conversations/<uuid:conversation_id>/attachments/", assistant.attachments),
    path("assistant/jobs/<uuid:job_id>/", assistant.job),
    path("assistant/jobs/<uuid:job_id>/stream/", assistant.job_stream),
    path("assistant/jobs/<uuid:job_id>/cancel/", assistant.cancel),
    path("assistant/jobs/<uuid:job_id>/retry/", assistant.retry),
    path("assistant/results/<uuid:snapshot_id>/", assistant.results),
    path("assistant/results/<uuid:snapshot_id>/exports/", assistant_export.exports),
    path("assistant/exports/<uuid:export_id>/download/", assistant_export.download),
    path("research/manifests/", assistant.research_manifests),
    path("research/manifests/<uuid:manifest_id>/", assistant.research_manifest),
    path("companies/", baichuan_api.companies),
    path("companies/<str:company_id>/", baichuan_api.company),
]
