"""Version-bound step results. No model retry can reset the task cost budget."""
from copy import deepcopy
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .product_models import DocumentStep
from .product_service import digest


TRANSIENT_ERRORS = frozenset({"timeout", "gateway_unavailable", "busy", "rate_limited", "internal_error",
                              "office_render_timeout", "office_render_failed", "output_truncated"})


class StepRetryPending(Exception):
    code = "step_retry_pending"

    def __init__(self, retry_after, cause_code):
        self.retry_after = retry_after
        self.cause_code = cause_code
        super().__init__(self.code)


def run_step(task_id, fence, key, binding, operation, *, validate=None):
    """Commit a validated result before proceeding; reclaim unfinished steps by fence."""
    from .product_worker import _guard

    input_hash = digest(binding)
    with transaction.atomic():
        task = _guard(task_id, fence)
        step, _ = DocumentStep.objects.get_or_create(task=task, key=key[:160], input_hash=input_hash)
        if step.status == "failed" and task.checkpoint.get("recovery_mode") is True:
            from .product_worker import ExecutionError
            raise ExecutionError(step.error_code or "execution_failed")
        if step.status == "completed" and step.output_hash == digest(step.output):
            cached = deepcopy(step.output)
            if validate is None or validate(cached):
                return cached
        if step.status == "retry_wait" and step.retry_after and step.retry_after > timezone.now():
            raise StepRetryPending(step.retry_after, step.error_code)
        step.status, step.fence = "running", fence
        step.attempts += 1
        step.retry_after = None
        step.save()
    try:
        output = operation()
    except Exception as error:
        code = getattr(error, "code", "execution_failed")
        diagnostic = getattr(error, "diagnostic", {})
        timed_out = (code in {"presentation_unavailable", "document_render_failed", "diagram_render_failed"}
                     and isinstance(diagnostic, dict) and diagnostic.get("reason") in
                     {"timeout", "process_timeout", "office_render_timeout", "office_render_failed"})
        office_failed = (code == "document_render_failed" and isinstance(diagnostic, dict)
                         and diagnostic.get("stage") == "office_render"
                         and diagnostic.get("reason") == "renderer_failed")
        transient = code in TRANSIENT_ERRORS or timed_out or office_failed
        terminal_child = getattr(error, "_product_failed_step", None) is not None
        retry_after = None
        with transaction.atomic():
            _guard(task_id, fence)
            step = DocumentStep.objects.select_for_update().get(pk=step.pk)
            if isinstance(error, StepRetryPending):
                # Waiting for a child step does not consume this stage's failure budget.
                retry_after, code = error.retry_after, error.cause_code
            elif not terminal_child and transient:
                step.retry_count += 1
            if not isinstance(error, StepRetryPending) and not terminal_child and transient and step.retry_count < settings.PRODUCT_STEP_MAX_ATTEMPTS:
                delay = min(settings.PRODUCT_STEP_RETRY_MAX_SECONDS,
                            settings.PRODUCT_STEP_RETRY_BASE_SECONDS * 2 ** (step.retry_count - 1))
                retry_after = timezone.now() + timedelta(seconds=delay)
            step.status = "retry_wait" if retry_after else "failed"
            step.error_code, step.retry_after = code, retry_after
            step.save()
        if retry_after:
            raise StepRetryPending(retry_after, code) from error
        error._product_failed_step = step.pk
        raise
    with transaction.atomic():
        _guard(task_id, fence)
        step = DocumentStep.objects.select_for_update().get(pk=step.pk)
        step.status, step.output, step.output_hash = "completed", deepcopy(output), digest(output)
        step.error_code, step.retry_after = "", None
        step.save()
    return deepcopy(output)


def public_steps(task):
    # Expose progress only. Accepted model text and private paths stay private.
    return [
        {"key": step.key, "status": step.status, "attempts": step.attempts,
         "error_code": step.error_code, "retry_count": step.retry_count,
         "retry_after": step.retry_after.isoformat() if step.retry_after else None}
        for step in task.steps.order_by("-updated_at", "-pk")[:100]]
