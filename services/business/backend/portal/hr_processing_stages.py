"""Private, checksummed checkpoints. Reuse never widens the source's live scope."""
import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from .hr_agent import current_artifact, lock_artifact, check_artifact
from .hr_screening_models import ResumeProcessingStage
from .hr_retention import active_artifacts
from .product_storage import StorageError
from .product_service import ProductError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def implementation_version():
    root = Path(__file__).parent
    names = ['hr_resume_extract.py', 'hr_resume_vision.py', 'hr_matching.py',
             'hr_screening_worker.py', 'hr_processing_stages.py']
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})


def model_version(owner, route, selection=None):
    from .model_config import ModelRoute
    from .model_gateway import validate_model_selection
    # A missing route cannot produce a successful real model stage. Including it
    # in the key also invalidates stages produced before a route was removed.
    if not ModelRoute.objects.filter(code=route).exists():
        return {'missing_route': route}
    return validate_model_selection(owner, route, selection)


def save_stage(item_id, fence, name, key, output, key_factory):
    with transaction.atomic():
        locked = lock_artifact(item_id, fence)
        if locked is None:
            raise StorageError('lease_lost', '处理记录已清理。')
        item, batch, owner, _, _ = locked
        check_artifact(item, batch, owner, fence)
        if (item.processing_status != 'running' or not item.lease_until
                or item.lease_until <= timezone.now()):
            raise StorageError('lease_lost', '处理租约已失效。')
        if key_factory() != key:
            raise StorageError('stage_configuration_changed', '处理依据已变化。')
        ResumeProcessingStage.objects.update_or_create(artifact=item, name=name,
            defaults={'cache_key': key, 'output': output, 'sha256': digest(output)})
    return output


def run_stage(item, fence, name, key_factory, action, *, reusable=False):
    key = key_factory()
    current_artifact(item.pk, fence)
    candidates = ResumeProcessingStage.objects.filter(name=name, cache_key=key)
    if reusable:
        sources = active_artifacts(type(item).objects.filter(
            sha256=item.sha256, uploaded_by_id=item.uploaded_by_id,
            batch__created_by_id=item.batch.created_by_id,
            created_at__lte=item.created_at))
        candidates = candidates.filter(artifact__in=sources)
    else:
        candidates = candidates.filter(artifact=item)
    for stage in candidates.order_by('-created_at')[:20]:
        if digest(stage.output) != stage.sha256:
            continue
        try:
            with transaction.atomic():
                source, owner, _ = current_artifact(stage.artifact_id)
                if source.uploaded_by_id != item.uploaded_by_id or source.sha256 != item.sha256:
                    continue
                from .hr_resume_storage import read_file
                read_file(source.file_id, source.sha256)
                # Re-read after locking source so deletion cannot race this use.
                fresh = ResumeProcessingStage.objects.filter(pk=stage.pk).first()
                if not fresh or fresh.cache_key != key or digest(fresh.output) != fresh.sha256:
                    continue
                return save_stage(item.pk, fence, name, key, fresh.output, key_factory)
        except (StorageError, ProductError):
            current_artifact(item.pk, fence)  # A revoked target must fail, not miss the cache.
    return save_stage(item.pk, fence, name, key, action(), key_factory)


def verification_questions(matrix):
    return [{'requirement_id': row['id'], 'question': f'请核实：{row["text"]}。请提供具体案例或可核验证明。',
             'reason': row['verdict'], 'evidence': row.get('evidence', [])}
            for row in matrix if row['verdict'] in {'UNKNOWN', 'PARTIAL'}]
