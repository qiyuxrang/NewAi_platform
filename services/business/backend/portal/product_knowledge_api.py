"""Owner-scoped HTTP endpoints; optimistic lease prevents overlapping turns on SQLite too."""
import json
from hashlib import sha256
import uuid
from datetime import timedelta
from functools import wraps
from itertools import islice

from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse, StreamingHttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.http import content_disposition_header
from rest_framework.decorators import api_view
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

from .product_knowledge_models import ProductKnowledgeConversation as Conversation
from .models import User
from . import product_knowledge_service as service
from .product_service import ProductError
from .security import audit


def endpoint(function=None, *, assistant=False):
    if function is None:
        return lambda view: endpoint(view, assistant=assistant)
    @wraps(function)
    def wrapped(request, *args, **kwargs):
        try:
            request.knowledge_scope = service.authorize(request.user, allow_empty=True) if assistant else service.authorize(request.user)
            response = function(request, *args, **kwargs)
        except ProductError as error:
            response = Response({"code": error.code, "detail": error.detail}, status=error.status)
        except ParseError:
            response = Response({"code": "invalid_request", "detail": "请求 JSON 格式无效。"}, status=400)
        response["Cache-Control"] = "private, no-store"
        return response
    return wrapped


def body(request, keys):
    if not isinstance(request.data, dict) or set(request.data) != set(keys):
        raise ProductError("invalid_request", "请求字段无效。", 400)
    return request.data


def browse_query(request, default_page_size, include_query=False):
    allowed = {"page", "page_size"} | ({"q"} if include_query else set())
    if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise ProductError("invalid_request", "查询参数无效。", 400)
    values = []
    for key, default, maximum in (("page", 1, 10000), ("page_size", default_page_size, 50)):
        raw = request.query_params.get(key, str(default))
        if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= maximum:
            raise ProductError("invalid_request", "分页参数无效。", 400)
        values.append(int(raw))
    query = request.query_params.get("q", "").strip() if include_query else ""
    if (len(query) > 200
            or any((ord(char) < 32 and char not in "\r\n\t") or 0xD800 <= ord(char) <= 0xDFFF
                   for char in query)):
        raise ProductError("invalid_request", "搜索关键词无效。", 400)
    return values[0], values[1], query


def browsing_scope(request, dataset_id, document_id=None):
    documents = request.knowledge_scope["datasets"].get(dataset_id)
    if documents is None or (document_id is not None and document_id not in documents):
        raise ProductError("not_found", "对象不存在。", 404)
    return documents


def browsing_recheck(request, config):
    if service.configuration() != config:
        service.fail("unconfigured")
    service.recheck(request.user, request.knowledge_scope)


def authorization_revision(request):
    # An opaque equality check for this user's complete live grant; no catalogue.
    return sha256(json.dumps(request.knowledge_scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def visible(request, conversation):
    service.recheck(request.user, request.knowledge_scope)
    if not Conversation.objects.filter(pk=conversation.pk, archived_at__isnull=True).exists():
        raise ProductError("not_found", "对象不存在。", 404)
    if conversation.scope != request.knowledge_scope:
        service.fail("scope_revoked", 403)


def summary(conversation):
    return {"id": str(conversation.pk), "title": conversation.title, "version": conversation.version}


def detail(request, conversation):
    visible(request, conversation)
    return {**summary(conversation), "turns": conversation.turns}


def stream_event(payload):
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def assistant_turn(request, item, claim, question, request_id, version, config, web_search):
    from . import product_knowledge_agent as agent
    from .model_gateway import GatewayError

    purpose = service.assistant_ready(request.user)

    def check():
        visible(request, item)
        if service.assistant_ready(request.user) != purpose:
            service.fail("unconfigured")
        if not Conversation.objects.filter(pk=item.pk, owner=request.user, version=version,
                                           pending_id=claim, pending_until__gt=timezone.now()).exists():
            service.fail("conflict", 409)

    item.refresh_from_db()
    check()
    result = None
    events = agent.run(request.user, question, item.turns, item.scope, config,
                       web_search=web_search, recheck=check, run_id=str(claim), purpose_code=purpose)
    try:
        for event in events:
            check()
            if "result" in event:
                result = event["result"]
            else:
                yield event
    except GatewayError as error:
        raise ProductError(error.code, error.message, error.status) from None
    finally:
        events.close()
    if result is None:
        service.fail("invalid_response", 502)
    check()
    turns = item.turns + [{"question": question, "request_id": request_id, **result}]
    saved = Conversation.objects.filter(pk=item.pk, owner=request.user, archived_at__isnull=True,
                                        version=version, pending_id=claim, pending_until__gt=timezone.now()).update(
        turns=turns, title=question[:100] if not item.turns else item.title,
        version=F("version") + 1, pending_id=None, pending_request_id=None, pending_until=None, updated_at=timezone.now())
    if not saved:
        service.fail("conflict", 409)
    item.refresh_from_db()
    yield {"done": detail(request, item)}


def stream_turn(request, item, claim, question, request_id, version, config, assistant=False, web_search=False):
    from .model_gateway import GatewayError, stream_for_use
    try:
        if assistant:
            for event in assistant_turn(request, item, claim, question, request_id, version, config, web_search):
                yield stream_event(event)
            return
        item.refresh_from_db()
        visible(request, item)
        sources = service.retrieve(question, item.turns, item.scope, config)
        visible(request, item)
        if service.ready(request.user) != config:
            service.fail("unconfigured")
        if sources:
            raw, preview, completed = "", "", False
            events = stream_for_use(request.user, config[2], service.answer_messages(question, item.turns, sources))
            try:
                for event in events:
                    # A provider stream can outlive a dataset grant or route change.
                    # Check before releasing each chunk, not only before saving it.
                    visible(request, item)
                    if service.ready(request.user) != config:
                        service.fail("unconfigured")
                    if "delta" in event and type(event["delta"]) is str:
                        raw += event["delta"]
                        if len(raw) > 12000:
                            service.fail("invalid_response", 502)
                        current = service.preview_answer(raw)
                        if not current.startswith(preview):
                            service.fail("invalid_response", 502)
                        if len(current) > len(preview):
                            yield stream_event({"delta": current[len(preview):]})
                            preview = current
                    elif event.get("done") is True:
                        completed = True
                    else:
                        service.fail("invalid_response", 502)
            finally:
                if hasattr(events, "close"):
                    events.close()
            if not completed:
                service.fail("invalid_response", 502)
            answer, sources = service.parse_answer(raw, sources)
            outcome = "answered"
        else:
            answer, outcome = "已授权资料中未检索到相关内容，请补充具体设备或项目名称后重试。", "empty"
            yield stream_event({"delta": answer})
        visible(request, item)
        if service.ready(request.user) != config:
            service.fail("unconfigured")
        turns = item.turns + [{"question": question, "answer": answer, "sources": sources,
                               "outcome": outcome, "request_id": request_id}]
        saved = Conversation.objects.filter(pk=item.pk, owner=request.user, archived_at__isnull=True, version=version, pending_id=claim,
                                            pending_until__gt=timezone.now()).update(
            turns=turns, title=question[:100] if not item.turns else item.title,
            version=F("version") + 1, pending_id=None, pending_request_id=None, pending_until=None, updated_at=timezone.now())
        if not saved:
            service.fail("conflict", 409)
        item.refresh_from_db()
        yield stream_event({"done": detail(request, item)})
    except ProductError as error:
        yield stream_event({"error": {"code": error.code, "detail": error.detail}})
    except GatewayError as error:
        yield stream_event({"error": {"code": error.code, "detail": error.message}})
    except Exception:
        yield stream_event({"error": {"code": "unavailable", "detail": "知识服务暂时不可用，请稍后重试。"}})
    finally:
        Conversation.objects.filter(pk=item.pk, pending_id=claim).update(pending_id=None, pending_request_id=None, pending_until=None)


@api_view(["GET"])
@endpoint(assistant=True)
def status(request):
    from .product_knowledge_agent import web_status, runtime_status
    assistant = runtime_status()
    try:
        service.assistant_ready(request.user)
    except ProductError as error:
        assistant = {**assistant, "available": False, "code": error.code,
                     "help": "对话模型暂不可用，仍可查阅历史和已授权文档。"}
    knowledge = knowledge_status(request)
    service.recheck(request.user, request.knowledge_scope)
    return Response({"available": True, "code": "ready", "help": "直接对话，按需检索可用资料。",
                     "web_search": web_status(), "assistant": assistant, "knowledge": knowledge,
                     "authorization_revision": authorization_revision(request)})


def knowledge_status(request):
    if not request.knowledge_scope["datasets"]:
        return {"available": False, "code": "knowledge_not_authorized",
                "help": "当前账号未授权知识库，仍可对话、计算或使用联网搜索。"}
    try:
        service.configuration()
    except ProductError as error:
        return {"available": False, "code": error.code,
                "help": "知识库暂不可用，仍可对话、计算或使用联网搜索。"}
    return {"available": True, "code": "ready", "help": "可检索当前账号已授权的知识资料。"}


def assistant_knowledge_config(request):
    if not request.knowledge_scope["datasets"]:
        return None
    try:
        return service.configuration()
    except ProductError:
        return None


@api_view(["POST"])
@endpoint
def retrieve(request):
    data = body(request, ("question",))
    question = data["question"]
    if (request.query_params or not isinstance(question, str) or not question.strip() or len(question) > 2000
            or any((ord(c) < 32 and c not in "\r\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in question)):
        raise ProductError("invalid_request", "问题须为1–2000字符，不支持额外检索参数。", 400)
    config = service.ready(request.user)
    browsing_recheck(request, config)
    sources = service.retrieve(question.strip(), [], request.knowledge_scope, config)
    browsing_recheck(request, config)
    if service.ready(request.user) != config:
        service.fail("unconfigured")
    service.recheck(request.user, request.knowledge_scope)
    return Response({"status": "completed", "sources": sources,
                     "authorization_revision": authorization_revision(request)})


@api_view(["GET"])
@endpoint
def datasets(request):
    config = service.configuration()
    items = service.list_datasets(request.knowledge_scope, config)
    service.recheck(request.user, request.knowledge_scope)
    return Response({"datasets": items})


@api_view(["GET"])
@endpoint
def documents(request, dataset_id):
    allowed = browsing_scope(request, dataset_id)
    page, page_size, query = browse_query(request, 20, include_query=True)
    config = service.configuration()
    result = service.list_documents(dataset_id, allowed, page, page_size, query, config)
    browsing_recheck(request, config)
    return Response(result)


@api_view(["GET"])
@endpoint
def chunks(request, dataset_id, document_id):
    browsing_scope(request, dataset_id, document_id)
    page, page_size, _ = browse_query(request, 10)
    config = service.configuration()
    result = service.list_chunks(dataset_id, document_id, page, page_size, config)
    browsing_recheck(request, config)
    return Response(result)


def original_input(request, dataset_id, document_id, *, fresh=False):
    browsing_scope(request, dataset_id, document_id)
    config = service.configuration()
    browsing_recheck(request, config)
    metadata = service.original_document_metadata(dataset_id, document_id, config)
    browsing_recheck(request, config)
    reader = service.original_document if fresh else service.cached_original_document
    raw = reader(dataset_id, document_id, metadata, config)
    browsing_recheck(request, config)
    return metadata, raw, config


def original_response(request, dataset_id, document_id, *, download):
    browsing_scope(request, dataset_id, document_id)
    if request.query_params:
        raise ProductError("invalid_request", "原文件查阅不支持额外参数。", 400)
    metadata, raw, config = original_input(request, dataset_id, document_id, fresh=download)
    content, content_type = raw, "application/octet-stream"
    if not download:
        from .product_knowledge_preview import preview
        content, content_type = preview(raw, metadata["name"])
        browsing_recheck(request, config)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(download, metadata["filename"])
    response["Content-Length"] = str(len(content))
    response["X-Content-Type-Options"] = "nosniff"
    # Rendering has no scripts, links, remote images or form interactions.
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"
    return response


@api_view(["GET"])
@endpoint
def document_preview(request, dataset_id, document_id):
    return original_response(request, dataset_id, document_id, download=False)


@api_view(["GET"])
@endpoint
def document_download(request, dataset_id, document_id):
    return original_response(request, dataset_id, document_id, download=True)


@api_view(["GET"])
@endpoint
def document_pages(request, dataset_id, document_id):
    browsing_scope(request, dataset_id, document_id)
    allowed = {"start_page", "page_size"}
    if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise ProductError("invalid_request", "PDF 分页参数无效。", 400)
    values = []
    for key, default, maximum in (("start_page", 1, 10000), ("page_size", 3, 5)):
        raw = request.query_params.get(key, str(default))
        if (not raw.isascii() or not raw.isdigit() or len(raw) > 5
                or not 1 <= int(raw) <= maximum):
            raise ProductError("invalid_request", "PDF 页码或批次大小无效。", 400)
        values.append(int(raw))
    metadata, raw, config = original_input(request, dataset_id, document_id)
    if not metadata["name"].lower().endswith(".pdf"):
        from .product_knowledge_preview import unsupported
        unsupported()
    from .product_knowledge_preview import pdf_preview
    result = pdf_preview(raw, start_page=values[0], page_size=values[1])
    browsing_recheck(request, config)
    response = Response(result)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["GET", "POST"])
@endpoint(assistant=True)
def conversations(request):
    if request.method == "GET":
        # Filter before emitting titles: even a conversation's first question can contain secrets.
        items = [summary(item) for item in Conversation.objects.filter(owner=request.user, archived_at__isnull=True).only("id", "title", "version", "scope")[:100]
                 if item.scope == request.knowledge_scope]
        service.recheck(request.user, request.knowledge_scope)
        return Response({"conversations": items})
    body(request, ())
    with transaction.atomic():
        check_capacity(request)
        conversation = Conversation.objects.create(owner=request.user, scope=request.knowledge_scope)
    return Response(detail(request, conversation), status=201)


def check_capacity(request):
    # A write lock serializes create/restore on SQLite as well as PostgreSQL.
    # Call inside atomic, before reading the quota; the owner's grant stays unchanged.
    User.objects.filter(pk=request.user.pk).update(grant_version=F("grant_version"))
    service.recheck(request.user, request.knowledge_scope)
    if Conversation.objects.filter(owner=request.user, archived_at__isnull=True).count() >= 100:
        raise ProductError("conversation_limit", "最多保留100个活跃对话，请归档旧对话；不可见旧对话可联系管理员归档。", 409)


@api_view(["GET"])
@endpoint(assistant=True)
def archived_conversations(request):
    page, page_size, _ = browse_query(request, 20)
    candidates = Conversation.objects.filter(owner=request.user, archived_at__isnull=False).only("id", "title", "version", "scope")
    # ponytail: pagination scans owner history; use a scope index if archive volume grows.
    items = islice((summary(item) for item in candidates.iterator() if item.scope == request.knowledge_scope),
                   (page - 1) * page_size, page * page_size)
    result = list(items)
    service.recheck(request.user, request.knowledge_scope)
    return Response({"conversations": result, "page": page, "page_size": page_size})


@api_view(["POST"])
@endpoint(assistant=True)
def archive_conversation(request, conversation_id):
    version = lifecycle_version(request)
    item = Conversation.objects.filter(pk=conversation_id, owner=request.user).first()
    if item is None:
        raise ProductError("not_found", "对象不存在。", 404)
    with transaction.atomic():
        service.recheck(request.user, request.knowledge_scope)
        if not item.archive(version):
            service.fail("conflict", 409)
        audit(request.user, "productknowledgeconversation_archive", item.pk, changes=["archived_at"])
    # Old-scope content remains inaccessible, including its title and sources.
    return Response({"id": str(item.pk), "version": version + 1, "archived": True})


@api_view(["POST"])
@endpoint(assistant=True)
def restore_conversation(request, conversation_id):
    version = lifecycle_version(request)
    item = Conversation.objects.filter(pk=conversation_id, owner=request.user).first()
    if item is None:
        raise ProductError("not_found", "对象不存在。", 404)
    if item.scope != request.knowledge_scope:
        service.fail("scope_revoked", 403)
    with transaction.atomic():
        check_capacity(request)
        restored = Conversation.objects.filter(pk=item.pk, owner=request.user, version=version,
                                               archived_at__isnull=False).filter(
            Q(pending_id__isnull=True) | Q(pending_until__lte=timezone.now())).update(
            archived_at=None, version=F("version") + 1, updated_at=timezone.now())
        if not restored:
            service.fail("conflict", 409)
        audit(request.user, "productknowledgeconversation_restore", item.pk, changes=["archived_at"])
    return Response({"id": str(item.pk), "version": version + 1, "archived": False})


def lifecycle_version(request):
    data = body(request, ("version",))
    if request.query_params or type(data["version"]) is not int or data["version"] < 0:
        raise ProductError("invalid_request", "version须为非负整数，不支持额外参数。", 400)
    return data["version"]


@api_view(["GET", "POST"])
@endpoint(assistant=True)
def conversation(request, conversation_id):
    item = Conversation.objects.filter(pk=conversation_id, owner=request.user).first()
    if item is None:
        raise ProductError("not_found", "对象不存在。", 404)
    visible(request, item)
    if request.method == "GET":
        return Response(detail(request, item))
    streaming = isinstance(request.data, dict) and request.data.get("stream") is True
    assistant = isinstance(request.data, dict) and request.data.get("assistant") is True
    keys = {"question", "version", "request_id"} | ({"stream"} if streaming else set())
    if assistant:
        keys.add("assistant")
        if "web_search" in request.data:
            keys.add("web_search")
    data = body(request, keys)
    web_search = data.get("web_search", False)
    if type(web_search) is not bool:
        raise ProductError("invalid_request", "web_search须为布尔值。", 400)
    question = data["question"]
    if (not isinstance(question, str) or not question.strip() or len(question) > 2000
            or any((ord(c) < 32 and c not in "\r\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in question)
            or type(data["version"]) is not int or data["version"] < 0):
        raise ProductError("invalid_request", "问题须为1–2000字符，version须为非负整数。", 400)
    question = question.strip()
    try:
        request_id = str(uuid.UUID(data["request_id"]))
    except (ValueError, TypeError, AttributeError):
        raise ProductError("invalid_request", "request_id须为UUID。", 400) from None
    for turn in item.turns:
        if turn["request_id"] == request_id:
            if (turn["question"] != question or bool(turn.get("assistant")) != assistant
                    or bool(turn.get("web_search")) != web_search):
                service.fail("conflict", 409)
            if streaming:
                return StreamingHttpResponse(iter([stream_event({"done": detail(request, item)})]),
                                             content_type="text/event-stream; charset=utf-8",
                                             headers={"X-Accel-Buffering": "no"})
            return Response(detail(request, item))
    if len(item.turns) >= 40:
        raise ProductError("history_limit", "此对话已达40轮，请新建对话。", 409)
    if assistant:
        service.assistant_ready(request.user)
        config = assistant_knowledge_config(request)
    else:
        service.authorize(request.user)
        config = service.ready(request.user)
    now = timezone.now()
    claim = uuid.uuid4()
    from .product_knowledge_agent import LEASE_SECONDS
    # Single conditional UPDATE, rather than select_for_update (ineffective on SQLite).
    claimed = (Conversation.objects.filter(pk=item.pk, owner=request.user, archived_at__isnull=True, version=data["version"])
               .filter(Q(pending_id__isnull=True) | Q(pending_until__lt=now))
               .update(pending_id=claim, pending_request_id=request_id,
                       pending_until=now + timedelta(seconds=LEASE_SECONDS if assistant else 180)))
    if not claimed:
        service.fail("conflict", 409)
    if streaming:
        return StreamingHttpResponse(stream_turn(request, item, claim, question, request_id, data["version"], config,
                                                  assistant, web_search),
                                     content_type="text/event-stream; charset=utf-8",
                                     headers={"X-Accel-Buffering": "no"})
    try:
        if assistant:
            completed = None
            for event in assistant_turn(request, item, claim, question, request_id, data["version"], config, web_search):
                if "done" in event:
                    completed = event["done"]
            return Response(completed)
        item.refresh_from_db()
        visible(request, item)
        sources = service.retrieve(question, item.turns, item.scope, config)
        visible(request, item)
        # Recheck switches/route immediately before sending private evidence to the gateway.
        if service.ready(request.user) != config:
            service.fail("unconfigured")
        visible(request, item)
        if sources:
            answer, sources = service.answer(request.user, question, item.turns, sources, config)
            outcome = "answered"
        else:
            answer, outcome = "已授权资料中未检索到相关内容，请补充具体设备或项目名称后重试。", "empty"
        visible(request, item)
        if service.ready(request.user) != config:
            service.fail("unconfigured")
        visible(request, item)
        turns = item.turns + [{"question": question, "answer": answer, "sources": sources,
                               "outcome": outcome, "request_id": request_id}]
        saved = Conversation.objects.filter(pk=item.pk, owner=request.user, archived_at__isnull=True, version=data["version"], pending_id=claim, pending_until__gt=timezone.now()).update(
            turns=turns, title=question[:100] if not item.turns else item.title,
            version=F("version") + 1, pending_id=None, pending_request_id=None, pending_until=None, updated_at=timezone.now())
        if not saved:
            service.fail("conflict", 409)
        item.refresh_from_db()
        return Response(detail(request, item))
    finally:
        # An expired worker cannot release a newer worker's lease or overwrite its result.
        Conversation.objects.filter(pk=item.pk, pending_id=claim).update(pending_id=None, pending_request_id=None, pending_until=None)


@api_view(["POST"])
@endpoint(assistant=True)
def cancel_conversation(request, conversation_id):
    data = body(request, ("request_id",))
    if request.query_params:
        raise ProductError("invalid_request", "不支持额外参数。", 400)
    try:
        request_id = uuid.UUID(data["request_id"])
    except (ValueError, TypeError, AttributeError):
        raise ProductError("invalid_request", "request_id须为UUID。", 400) from None
    item = Conversation.objects.filter(pk=conversation_id, owner=request.user).first()
    if item is None:
        raise ProductError("not_found", "对象不存在。", 404)
    visible(request, item)
    if not any(turn["request_id"] == str(request_id) for turn in item.turns):
        claim = item.pending_id
        if claim is not None:
            revoked = Conversation.objects.filter(pk=item.pk, owner=request.user, pending_id=claim,
                pending_request_id=request_id, archived_at__isnull=True).update(
                    pending_id=None, pending_request_id=None, pending_until=None)
            if not revoked:
                item.refresh_from_db()
                if not any(turn["request_id"] == str(request_id) for turn in item.turns):
                    service.fail("conflict", 409)
            else:
                from .product_assistant_runtime import cancel_run
                cancel_run(str(claim))
                audit(request.user, "assistant_cancel", item.pk, result="cancelled")
    item.refresh_from_db()
    return Response(detail(request, item))


urlpatterns = [path("knowledge/status/", status), path("knowledge/datasets/", datasets),
               path("knowledge/retrieve/", retrieve),
               path("knowledge/datasets/<str:dataset_id>/documents/", documents),
               path("knowledge/datasets/<str:dataset_id>/documents/<str:document_id>/chunks/", chunks),
               path("knowledge/datasets/<str:dataset_id>/documents/<str:document_id>/preview/", document_preview),
               path("knowledge/datasets/<str:dataset_id>/documents/<str:document_id>/preview/pages/", document_pages),
               path("knowledge/datasets/<str:dataset_id>/documents/<str:document_id>/download/", document_download),
               path("knowledge/conversations/", conversations),
               path("knowledge/conversations/archived/", archived_conversations),
               path("knowledge/conversations/<uuid:conversation_id>/archive/", archive_conversation),
               path("knowledge/conversations/<uuid:conversation_id>/restore/", restore_conversation),
               path("knowledge/conversations/<uuid:conversation_id>/cancel/", cancel_conversation),
               path("knowledge/conversations/<uuid:conversation_id>/", conversation)]
