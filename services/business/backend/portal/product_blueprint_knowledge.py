"""RAGFlow gate and adapters for blueprint generation.

Preview mode is deliberately source-only and records no synthetic retrieval
hits. Formal mode calls the existing allow-listed RAGFlow retrieval service,
then supplements missing technical and feasibility references with bounded public queries.
Authorization and network failures stay explicit, recoverable gates.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .product_service import ProductError, digest
from .product_web_search import ERRORS, evidence_coverage, public_queries, search_public_references


PREVIEW = "source_only_preview"
RAGFLOW_REQUIRED = "ragflow_required"


def _ragflow_snapshot(input_payload):
    value = input_payload.get("blueprint_knowledge") if isinstance(input_payload, Mapping) else None
    if not isinstance(value, Mapping):
        return None
    sources = value.get("sources")
    scope_hash = value.get("scope_hash")
    if (value.get("provider") != "ragflow" or value.get("status") != "completed"
            or not isinstance(sources, list) or not isinstance(scope_hash, str)
            or len(scope_hash) != 64):
        return None
    return value


def blueprint_knowledge_status(input_payload):
    mode = getattr(settings, "PRODUCT_BLUEPRINT_KNOWLEDGE_MODE", PREVIEW)
    snapshot = _ragflow_snapshot(input_payload)
    if snapshot is not None:
        web = snapshot.get("web_search", {})
        evidence_ready = snapshot.get("evidence_ready", bool(snapshot["sources"]))
        return {
            "mode": mode,
            "required": mode == RAGFLOW_REQUIRED,
            "status": "ready",
            "ragflow_used": True,
            "source_count": len(snapshot["sources"]),
            "ragflow_source_count": snapshot.get("ragflow_source_count", len(snapshot["sources"])),
            "web_source_count": snapshot.get("web_source_count", 0),
            "web_search": web,
            "evidence_ready": evidence_ready,
            "coverage": snapshot.get("coverage", {}),
            "query_hash": snapshot.get("query_hash", ""),
            "retrieval_outcome": snapshot.get("retrieval_outcome", "hits" if snapshot["sources"] else "no_hits"),
            "detail": ("授权知识检索与公开资料补充已完成；公开来源仅作写作参考，项目事实仍以项目资料为准。"
                       if web.get("status") == "completed" else web.get("detail", "当前输入版本已完成 RAGFlow 授权检索。")),
        }
    if mode == RAGFLOW_REQUIRED:
        return {
            "mode": mode,
            "required": True,
            "status": "waiting_for_ragflow",
            "ragflow_used": False,
            "source_count": 0,
            "evidence_ready": False,
            "query_hash": "",
            "retrieval_outcome": "not_run",
            "detail": "正式模式必须先完成 RAGFlow 授权检索；服务不可用时不会绕过该步骤。",
        }
    return {
        "mode": PREVIEW,
        "required": False,
        "status": "source_only_preview",
        "ragflow_used": False,
        "source_count": 0,
        "evidence_ready": False,
        "query_hash": "",
        "retrieval_outcome": "not_run",
        "detail": "当前为资料直生成预览，仅使用本项目上传资料；没有伪造 RAGFlow 命中。",
    }


def require_blueprint_knowledge(input_payload, owner=None):
    status = blueprint_knowledge_status(input_payload)
    snapshot = _ragflow_snapshot(input_payload)
    if status["required"] and status["status"] != "ready":
        raise ProductError("ragflow_required", status["detail"], 409)
    if snapshot is not None and owner is not None:
        from .product_knowledge_service import recheck

        recheck(owner, snapshot.get("authorization"))
    return status


def require_generation_knowledge(input_payload, owner=None):
    status = require_blueprint_knowledge(input_payload, owner)
    if status["required"] and not status["evidence_ready"]:
        web = status.get("web_search", {})
        code = web.get("code") if web.get("code") in ERRORS else "web_search_unconfigured"
        raise ProductError(
            code,
            web.get("detail") or ERRORS[code],
            409,
        )
    return status


def require_task_generation_knowledge(task_id):
    from .product_models import DocumentTask
    from .product_service import current_revision

    task = DocumentTask.objects.select_related("owner").get(pk=task_id)
    revision = current_revision(task, "input")
    if revision is None:
        raise ProductError("input_required", "请先保存输入。", 409)
    return require_generation_knowledge(revision.payload, task.owner)


def _query(payload):
    # Reserve room for each input kind so a long background cannot hide the list/materials.
    # ponytail: first 30 rows/6 material excerpts; use targeted retrieval if larger projects need full coverage.
    items = "\n".join(" ".join(str(item.get(key, ""))[:200] for key in (
        "name", "specification", "source_section", "quantity", "unit"))
        for item in payload.get("items", [])[:30])[:1700]
    materials = "\n".join(str(source.get("text", ""))[:300]
                          for source in payload.get("source_materials", [])[:6])[:1700]
    return "\n".join((
        str(payload.get("project", ""))[:300],
        str(payload.get("requirements", ""))[:1200],
        "设备清单：\n" + items,
        "上传资料：\n" + materials,
        str(payload.get("background", ""))[:700],
        "\n".join(str(value)[:100] for value in payload.get("conditions", [])[:3])[:300],
    )).strip()[:6000]


def _query_hash(payload):
    # Hash complete inputs, including text outside the bounded retrieval question.
    return digest({"strategy": "blueprint-v3-feasibility-topics-3-public-queries", "query": _query(payload),
                   "input": {key: payload.get(key) for key in (
                       "project", "requirements", "background", "conditions", "items", "source_materials", "sources")}})


def _preview_checkpoint(task, fence):
    with transaction.atomic():
        from .product_models import DocumentTask

        locked = DocumentTask.objects.select_for_update().get(pk=task.pk)
        if locked.state != DocumentTask.State.RUNNING or locked.fence != fence:
            raise ProductError("lease_lost", "任务租约已失效。", 409)
        locked.checkpoint = {
            **locked.checkpoint,
            "blueprint_knowledge": {
                "adapter": "source_only_preview",
                "status": "skipped",
                "ragflow_used": False,
                "source_count": 0,
                "updated_at": timezone.now().isoformat(),
            },
        }
        locked.save(update_fields=["checkpoint", "updated_at"])


def prepare_blueprint_knowledge(task_id, fence):
    """Idempotently prepare knowledge evidence for the current input version."""
    from .product_knowledge_service import authorize, configuration, retrieve
    from .product_models import DocumentTask
    from .product_service import append_revision, current_revision
    from .product_worker import _renew

    task = DocumentTask.objects.select_related("owner").get(pk=task_id)
    if task.state != DocumentTask.State.RUNNING or task.fence != fence:
        raise ProductError("lease_lost", "任务租约已失效。", 409)
    revision = current_revision(task, "input")
    if revision is None:
        raise ProductError("input_required", "请先保存输入。", 409)
    mode = getattr(settings, "PRODUCT_BLUEPRINT_KNOWLEDGE_MODE", PREVIEW)
    if mode == PREVIEW:
        _preview_checkpoint(task, fence)
        return blueprint_knowledge_status(revision.payload)

    existing = _ragflow_snapshot(revision.payload)
    scope = authorize(task.owner)
    scope_hash = digest(scope)
    query = _query(revision.payload)
    query_hash = _query_hash(revision.payload)
    reuse = (existing is not None and existing.get("authorization") == scope
             and existing.get("scope_hash") == scope_hash and existing.get("query_hash") == query_hash)
    if reuse and existing.get("evidence_ready", bool(existing.get("sources"))):
        return blueprint_knowledge_status(revision.payload)

    if reuse:
        knowledge_sources = [source for source in revision.payload.get("knowledge_sources", [])
                             if source.get("provider") == "ragflow"
                             or source.get("fact_scope") == "PUBLIC_REFERENCE"]
    else:
        _renew(task_id, fence)
        hits = retrieve(query, [], scope, configuration(), blueprint=True)
        knowledge_sources = [{
            "id": f"ragflow:{source['id']}",
            "provider": "ragflow",
            "chunk_id": source["chunk_id"],
            "dataset_id": source["dataset_id"],
            "document_id": source["document_id"],
            "title": source["title"],
            "text": source["content"],
        } for source in hits]
    ragflow_source_count = sum(source.get("provider") == "ragflow" for source in knowledge_sources)
    coverage = evidence_coverage(revision.payload, knowledge_sources, feasibility=True)
    web = {"status": "skipped", "source_count": len(knowledge_sources) - ragflow_source_count,
           "queries": [], "missing_domains": [], "missing_writing_topics": [],
           "detail": "授权知识来源覆盖主要技术领域与可研写作参考，本次未触发联网搜索。"}
    if not coverage["sufficient"]:
        from .product_worker import _analysis_progress

        queries = public_queries(coverage)
        web = {"status": "running", "source_count": len(knowledge_sources) - ragflow_source_count,
               "queries": queries, "attempted_queries": [],
               "missing_domains": coverage["missing_domains"],
               "missing_writing_topics": coverage["missing_writing_topics"],
               "fact_scope": "PUBLIC_REFERENCE",
               "detail": "写作参考不足，正在以通用专业分类检索公开资料。"}
        _analysis_progress(task_id, fence, "web_search", "running", **{key: value for key, value in web.items() if key != "status"})
        try:
            for query in queries:
                _renew(task_id, fence)
                web["attempted_queries"].append(query)
                public_sources = search_public_references([query])
                known = {source["id"] for source in knowledge_sources}
                knowledge_sources.extend(source for source in public_sources if source["id"] not in known)
                coverage = evidence_coverage(revision.payload, knowledge_sources, feasibility=True)
                if public_sources:
                    web["provider"] = public_sources[0]["provider"]
                if coverage["sufficient"]:
                    break
            if not coverage["sufficient"]:
                raise ProductError("web_search_no_hits", ERRORS["web_search_no_hits"], 409)
            web.update(status="completed", detail="公开资料检索完成，来源仅作写作参考，适用性与时效待审核，不能补造项目事实。")
        except ProductError as error:
            if error.code not in ERRORS:
                raise
            web.update(status="blocked", code=error.code, detail=ERRORS[error.code])
        web["source_count"] = len(knowledge_sources) - ragflow_source_count
        web["remaining_domains"] = coverage["missing_domains"]
        web["remaining_writing_topics"] = coverage["missing_writing_topics"]
    snapshot = {
        "provider": "ragflow",
        "status": "completed",
        "ragflow_used": True,
        "query_hash": query_hash,
        "scope_hash": scope_hash,
        "retrieval_outcome": "hits" if ragflow_source_count else "no_hits",
        "ragflow_source_count": ragflow_source_count,
        "web_source_count": web["source_count"],
        "web_search": web,
        "coverage": coverage,
        "evidence_ready": coverage["sufficient"],
        "authorization": scope,
        "sources": [{key: source[key] for key in (
            "id", "provider", "chunk_id", "dataset_id", "document_id", "title", "url",
            "retrieved_at", "query_hash", "fact_scope", "reference_only", "untrusted", "source_trust", "timeliness",
            "content_kind", "content_truncated", "applicability"
        ) if key in source} for source in knowledge_sources],
        "retrieved_at": timezone.now().isoformat(),
    }
    with transaction.atomic():
        locked = DocumentTask.objects.select_for_update().get(pk=task_id)
        if locked.state != DocumentTask.State.RUNNING or locked.fence != fence:
            raise ProductError("lease_lost", "任务租约已失效。", 409)
        current = current_revision(locked, "input")
        if current.pk != revision.pk:
            raise ProductError("source_snapshot_changed", "输入版本已变化，请重试。", 409)
        payload = json.loads(json.dumps(current.payload, ensure_ascii=False))
        payload["blueprint_knowledge"] = snapshot
        payload["knowledge_sources"] = knowledge_sources
        prepared = append_revision(
            locked,
            "input",
            payload,
            actor=locked.owner,
            reason="ragflow_blueprint_retrieval",
        )
        locked.input_version = prepared.version
        locked.blueprint_version = 0
        locked.checkpoint = {
            **locked.checkpoint,
            "blueprint_knowledge": {
                "adapter": "ragflow",
                "status": "completed",
                "ragflow_used": True,
                "source_count": len(knowledge_sources),
                "ragflow_source_count": ragflow_source_count,
                "web_source_count": web["source_count"],
                "web_search": web,
                "evidence_ready": coverage["sufficient"],
                "query_hash": snapshot["query_hash"],
                "updated_at": snapshot["retrieved_at"],
            },
        }
        locked.save(update_fields=[
            "input_version", "blueprint_version", "checkpoint", "updated_at"
        ])
    return blueprint_knowledge_status(payload)
