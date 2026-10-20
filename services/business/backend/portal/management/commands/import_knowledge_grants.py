"""Cut over explicit legacy product grants, without adding any documents/users."""
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from portal.knowledge_access_models import KnowledgeAccessPolicy, KnowledgeDocumentGrant
from portal.models import User
from portal.security import audit


class Command(BaseCommand):
    help = "校验并导入已有产品文档授权；默认只校验，--apply 原子切换至数据库授权。"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        grants = getattr(settings, "PRODUCT_KNOWLEDGE_AUTHORIZATIONS", {})
        if not isinstance(grants, dict) or not grants:
            raise CommandError("没有可迁移的产品文档授权。")
        if KnowledgeAccessPolicy.objects.filter(department_code="product").exists():
            raise CommandError("产品资料已由数据库策略管理，不允许覆盖。")
        rows = []
        for user_id, datasets in grants.items():
            if (not isinstance(user_id, str) or not user_id.isascii() or not user_id.isdecimal()
                    or user_id != str(int(user_id)) or not User.objects.filter(pk=user_id).exists()
                    or not isinstance(datasets, dict) or not 1 <= len(datasets) <= 4):
                raise CommandError("既有授权的账号或资料范围无效，未执行迁移。")
            for dataset, documents in datasets.items():
                if (not isinstance(documents, (list, tuple)) or not 1 <= len(documents) <= 100
                        or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
                               for value in [dataset, *documents])
                        or len(set(documents)) != len(documents)):
                    raise CommandError("既有授权包含无效文档，未执行迁移。")
                rows.extend((int(user_id), dataset, document) for document in documents)
        if not options["apply"]:
            self.stdout.write(f"校验通过：{len(grants)} 个账号、{len(rows)} 条文档授权；尚未写入。")
            return
        with transaction.atomic():
            policy, created = KnowledgeAccessPolicy.objects.get_or_create(
                department_code="product", defaults={"enabled": False})
            if not created:
                raise CommandError("产品策略已存在，未覆盖。")
            KnowledgeDocumentGrant.objects.bulk_create([
                KnowledgeDocumentGrant(policy=policy, user_id=user_id, dataset_id=dataset,
                    document_id=document, can_read=True, can_ai_use=True, enabled=True)
                for user_id, dataset, document in rows])
            policy.enabled = True
            policy.save(update_fields=["enabled", "updated_at"])
            audit(None, "knowledge_grants_import", policy.pk,
                  changes=[f"accounts:{len(grants)}", f"grants:{len(rows)}"])
        self.stdout.write(self.style.SUCCESS(f"已切换产品资料授权：{len(rows)} 条，未增加原范围之外的授权。"))
