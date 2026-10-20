"""Read-only administrative summaries. Never fetch business document contents."""
from datetime import timedelta

from django import forms
from django.db.models import Avg, Count, Q
from django.http import HttpResponseNotAllowed
from django.template.response import TemplateResponse
from django.utils import timezone

from .engineering_models import EngineeringJob
from .hr_screening_models import ResumeArtifact
from .hr_retention import active_artifacts
from .knowledge_access import KnowledgeAccessDenied, authorize
from .knowledge_access_models import DEPARTMENTS
from .model_config import ModelCallLog, ModelRoute
from .models import User
from .product_models import DocumentTask


class AccessReviewForm(forms.Form):
    user = forms.ModelChoiceField(label="核对账号", queryset=User.objects.none())
    department = forms.ChoiceField(label="业务部门", choices=DEPARTMENTS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.order_by("username")


def review(site, request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    now = timezone.now()
    form = AccessReviewForm(request.GET if request.GET else None)
    access = []
    if form.is_bound and form.is_valid():
        for action, label in (("read", "查看"), ("ai_use", "AI 使用"), ("download", "下载")):
            try:
                scope = authorize(form.cleaned_data["user"], form.cleaned_data["department"], action=action)
                message = "已核验" if scope else "兼容模式：未核验数据库授权"
            except KnowledgeAccessDenied:
                scope, message = None, "拒绝访问：核对账号状态、业务模块、授权策略、文档权限或有效期"
            access.append({"label": label, "message": message,
                           "datasets": scope["datasets"] if scope else {}})
    queues = []
    for label, query, field, running in (
        ("产品任务", DocumentTask.objects.all(), "state", "RUNNING"),
        ("简历处理", active_artifacts(ResumeArtifact.objects.all()), "processing_status", "running"),
        ("工程报价", EngineeringJob.objects.all(), "status", "running"),
    ):
        queues.append({"label": label,
                       "counts": list(query.order_by().values(field).annotate(count=Count("pk"))),
                       "field": field,
                       "expired": query.filter(**{field: running}, lease_until__lt=now).count(),
                       "failures": list(query.filter(**{field: "FAILED" if field == "state" else "failed"})
                                        .order_by("-updated_at").values("id", "error_code", "updated_at")[:10])})
        for row in queues[-1]["counts"]:
            row["state"] = row.pop(field)
    calls = ModelCallLog.objects.filter(purpose="business", created_at__gte=now - timedelta(hours=24))
    usage = calls.aggregate(calls=Count("pk"), pending=Count("pk", filter=Q(status="pending")),
                            failures=Count("pk", filter=~Q(status__in=("pending", "success"))),
                            average_ms=Avg("duration_ms", filter=~Q(status="pending")))
    return TemplateResponse(request, "admin/platform_review.html", {
        **site.each_context(request), "title": "运行情况与资料权限核对", "checked_at": now,
        "form": form, "access": access, "queues": queues, "usage": usage,
        "routes": ModelRoute.objects.order_by("code").values("code", "enabled", "max_calls_per_minute"),
    })
