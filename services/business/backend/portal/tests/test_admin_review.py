from datetime import timedelta

from django.test import Client, override_settings
from django.utils import timezone

from portal.engineering_models import EngineeringJob
from portal.hr_recruitment_models import RecruitmentRequest, JDVersion
from portal.hr_screening_models import ResumeScreeningBatch, ResumeArtifact
from portal.knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant
from portal.model_config import ModelCallLog
from .base import ADMIN_PASSWORD, PortalTestCase


@override_settings(KNOWLEDGE_AUTHORIZATION_REQUIRED=True)
class AdminReviewTests(PortalTestCase):
    def setUp(self):
        self.admin = self.create_admin()
        self.login(self.client, self.admin, ADMIN_PASSWORD)

    def test_admin_only_read_only_and_no_business_content(self):
        user = self.create_user("review-engineering", "cost")
        EngineeringJob.objects.create(owner=user, status="failed", error_code="worker_unavailable",
                                      error_detail="PRIVATE-BODY", inputs=["PRIVATE-INPUT"])
        ModelCallLog.objects.create(purpose="business", status="pending", duration_ms=0)
        ModelCallLog.objects.create(purpose="business", status="success", duration_ms=200)
        response = self.client.get("/admin/review/")
        self.assertContains(response, "worker_unavailable")
        self.assertNotContains(response, "PRIVATE-BODY")
        self.assertNotContains(response, "PRIVATE-INPUT")
        self.assertEqual(response.context["usage"]["average_ms"], 200)
        self.assertEqual(response.context["usage"]["pending"], 1)
        self.assertContains(response, "未采集 worker 进程心跳")
        self.assertEqual(self.client.post("/admin/review/").status_code, 405)
        self.assertEqual(Client().get("/admin/review/").status_code, 302)
        other = Client()
        self.login(other, user)
        self.assertEqual(other.get("/admin/review/").status_code, 302)

    def test_preview_reuses_live_authorization_and_expiry(self):
        user = self.create_user("review-product", "product")
        policy = KnowledgeAccessPolicy.objects.create(department_code="product", enabled=True)
        grant = KnowledgeDocumentGrant.objects.create(policy=policy, dataset_id="dataset-A", document_id="document-A",
                                                       user=user, enabled=True, can_read=True, can_ai_use=False)
        query = {"user": user.pk, "department": "product"}
        response = self.client.get("/admin/review/", query)
        rows = response.context["access"]
        self.assertEqual(rows[0]["datasets"], {"dataset-A": ["document-A"]})
        self.assertEqual(rows[1]["datasets"], {})
        self.assertEqual(rows[2]["datasets"], {})
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        response = self.client.get("/admin/review/", query)
        self.assertTrue(all(not row["datasets"] for row in response.context["access"]))
        self.assertEqual(KnowledgeDocumentGrant.objects.count(), 1)
        self.assertFalse(self.client.get("/admin/review/", {"user": "invalid", "department": "product"}).context["access"])

    def test_hr_overview_excludes_archived_records_and_counts_expired_running(self):
        user = self.create_user("review-hr", "hr")
        request = RecruitmentRequest.objects.create(created_by=user, updated_by=user)
        jd = JDVersion.objects.create(request=request, created_by=user, version=1, input_version=1, body="PRIVATE-JD")
        batch = ResumeScreeningBatch.objects.create(jd_version=jd, created_by=user, input_version=1,
                                                     idempotency_key="review-batch", requirements={})
        for index, archive in enumerate(("active", "deleted")):
            ResumeArtifact.objects.create(batch=batch, file_id=str(index), filename="PRIVATE-RESUME", sha256=str(index),
                                          size=1, uploaded_by=user, processing_status="running", archive_state=archive,
                                          lease_until=timezone.now() - timedelta(seconds=1))
        response = self.client.get("/admin/review/")
        hr = response.context["queues"][1]
        self.assertEqual(hr["counts"], [{"state": "running", "count": 1}])
        self.assertEqual(hr["expired"], 1)
        self.assertNotContains(response, "PRIVATE-RESUME")
        self.assertNotContains(response, "PRIVATE-JD")
