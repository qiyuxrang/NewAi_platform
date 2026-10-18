"""Persist local model admission waits; never retry an upstream request."""
from datetime import timedelta

from django.utils import timezone

from .baichuan_jobs import leased_job
from .baichuan_service import BaichuanError
from .model_gateway import GatewayError


def defer_model_admission(job, worker, error):
    if not (isinstance(error, GatewayError) and error.reservation_rejected
            and error.code in {"rate_limited", "busy"} and error.retry_after):
        return False
    with leased_job(job.pk, worker, job.fence) as current:
        if current.kind != "query":
            return False
        prior = current.checkpoint.get("model_wait", {})
        count = prior.get("count", 0)
        exhausted = type(count) is not int or count < 0 or count >= 12
        counts = dict(current.counts)
        # The caller reserved a task allowance immediately before generate.
        # Local admission happened before any model log or provider invocation.
        if counts.get("_budget_model_calls", 0) < 1:
            raise BaichuanError("invalid_checkpoint", "模型等待计量不一致，已保存任务。", 409)
        counts["_budget_model_calls"] -= 1
        current.counts = counts
        if not exhausted:
            current.checkpoint = {**current.checkpoint, "model_wait": {
                "count": count + 1, "reason": error.code,
                "not_before": (timezone.now() + timedelta(seconds=error.retry_after)).isoformat()}}
            current.status, current.stage, current.error_code = "queued", "planning", ""
            current.lease_owner, current.lease_expires_at = "", None
            current.attempts = max(0, current.attempts - 1)
            current.fence += 1
        current.save()
    if exhausted:
        raise BaichuanError("model_queue_exhausted", "模型等待次数已达上限，已保存任务，请稍后重试。", 429)
    return True
