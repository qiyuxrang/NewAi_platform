"""MCP over existing portal knowledge permissions; no RAGFlow key in runtimes."""

import json
import re
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from mcp import types
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser, BearerAuthBackend, RequireAuthMiddleware,
)
from mcp.server.auth.provider import AccessToken
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Route

from app.business_client import json_response, open_session, portal_client, portal_origin, portal_profile
from app.config import settings
from app.container.manager import get_container_by_token
from app.db.engine import async_session
from app.db.models import User
from app.enterprise import enterprise_identity


async def container_user(db, token):
    container = await get_container_by_token(db, token)
    user = None if container is None else (await db.execute(select(User).where(User.id == container.user_id))).scalar_one_or_none()
    if user is None or not user.is_active or not user.portal_session_enc or not enterprise_identity(user)["capabilities"]:
        raise HTTPException(401, "请先绑定已授权的企业业务账号")
    open_session(user)  # Ciphertext must belong to this platform/portal account.
    return user


class ContainerTokenVerifier:
    async def verify_token(self, token: str):
        if not token or len(token) > 512:
            return None
        async with async_session() as db:
            try:
                user = await container_user(db, token)
            except HTTPException:
                return None
            return AccessToken(token=token, client_id=user.id, subject=user.id, scopes=["enterprise_knowledge"])


def portal_json(response, expected_type=dict, expected_status=200):
    if expected_status == 200 or response.status_code >= 400:
        return json_response(response, expected_type)
    if response.status_code != expected_status or "application/json" not in response.headers.get("content-type", ""):
        raise HTTPException(502, "企业服务响应状态异常")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "企业服务响应格式异常") from None
    if not isinstance(data, expected_type):
        raise HTTPException(502, "企业服务响应格式异常")
    return data


def checked_text(value, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or len(value) > limit or any(
        (ord(c) < 32 and c not in "\r\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value
    ):
        raise HTTPException(400, "输入内容无效或超过长度限制")
    return value.strip()


def object_id(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(502, "企业业务对象标识无效") from None


def version(value):
    if type(value) is not int or value < 1:
        raise HTTPException(502, "企业业务版本无效")
    return value


@asynccontextmanager
async def bound_portal(token, department, write=False):
    if department not in {"product", "hr", "engineering"}:
        raise HTTPException(403, "部门不在允许范围")
    async with async_session() as db:
        user = await container_user(db, token)
        if department not in enterprise_identity(user)["capabilities"]:
            raise HTTPException(403, "无权使用该部门业务")
        original_session, original_portal_id = user.portal_session_enc, user.portal_user_id
        bound = open_session(user)
        async with portal_client(bound["cookies"]) as client:
            # Existing retrieval is bounded to 25 seconds; keep normal connect timeout.
            client.timeout = httpx.Timeout(settings.portal_timeout_seconds, read=max(30, settings.portal_timeout_seconds))
            await portal_profile(client, original_portal_id)
            headers = {"X-CSRFToken": bound["csrf"], "Origin": portal_origin(), "Referer": portal_origin() + "/"}
            yield user, client, headers
            await portal_profile(client, original_portal_id)
        await db.refresh(user)
        container = await get_container_by_token(db, token)
        if container is None or container.user_id != user.id or not user.is_active or user.portal_session_enc != original_session or user.portal_user_id != original_portal_id or department not in enterprise_identity(user)["capabilities"]:
            message = "企业业务授权已变化；创建操作可能已提交，请在业务页面核对后再操作" if write else "企业业务授权已变化，请重新确认绑定"
            raise HTTPException(403, message)


async def knowledge_question(token, department, question):
    question = checked_text(question, 2000 if department == "product" else 1000)
    async with bound_portal(token, department) as (_, client, headers):
        if department == "product":
            before = portal_json(await client.get("/api/product/knowledge/status/"))
            revision = before.get("authorization_revision")
            if before.get("available") is not True or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
                raise HTTPException(503, "产品知识检索尚未就绪")
            result = portal_json(await client.post("/api/product/knowledge/retrieve/", json={"question": question}, headers=headers))
            after = portal_json(await client.get("/api/product/knowledge/status/"))
            # Compare the exact live scope, not merely status or module membership.
            # A partial document revoke changes this hash even if another remains.
            if after.get("available") is not True or after.get("authorization_revision") != revision or result.get("authorization_revision") != revision:
                raise HTTPException(403, "产品知识授权已变化，请重新检索")
            if result.get("status") != "completed" or not isinstance(result.get("sources"), list):
                raise HTTPException(502, "产品知识检索响应异常")
            result = {"status": result["status"], "sources": result["sources"]}
        elif department == "engineering":
            result = portal_json(await client.post("/api/engineering/knowledge/retrieve/", json={"question": question}, headers=headers))
            state = portal_json(await client.get("/api/engineering/knowledge/"))
            if state.get("status") != "ready":
                raise HTTPException(403, "工程知识授权或任务检查状态已变化")
            if result.get("status") != "completed" or not isinstance(result.get("sources"), list):
                raise HTTPException(502, "工程知识检索响应异常")
        else:
            raise HTTPException(403, "该部门尚无已接入的知识接口")
    return result


async def create_draft(token, department, text):
    if department not in {"product", "hr"}:
        raise HTTPException(403, "该部门不提供草稿创建工具")
    text = checked_text(text, 8000)
    async with bound_portal(token, department, write=True) as (user, client, headers):
        if department == "product":
            # Explicit empty paths suppress server-path extraction from the message.
            headers = {**headers, "Idempotency-Key": "mcp-draft-" + str(uuid.uuid4())}
            response = portal_json(await client.post("/api/product/conversations/", headers=headers,
                json={"message": text, "paths": [], "requested_outputs": []}), expected_status=201)
            task = response.get("task")
            if not isinstance(task, dict) or task.get("owner_id") != user.portal_user_id:
                raise HTTPException(403, "项目草稿不属于当前账号")
            task_id = object_id(task.get("id"))
            current = portal_json(await client.get(f"/api/product/tasks/{task_id}/"))
            if current.get("owner_id") != user.portal_user_id or current.get("id") != task_id:
                raise HTTPException(403, "项目草稿不属于当前账号")
            if current.get("state") != "DRAFT" or current.get("stage") != "INTAKE":
                raise HTTPException(409, "项目状态已变化，请在页面核对；未生成交付文档")
            result = {"status": "draft_created", "task_id": task_id, "version": version(current.get("version")),
                "state": "DRAFT", "artifact_available": False, "review_url": f"/departments/product/documents?task={task_id}"}
        else:
            response = portal_json(await client.post("/api/hr/recruitment/requests/intake/", headers=headers,
                                                    json={"text": text}), expected_status=201)
            row, draft = response.get("request"), response.get("jd")
            if not isinstance(row, dict) or not isinstance(draft, dict) or row.get("created_by_id") != user.portal_user_id:
                raise HTTPException(403, "招聘草稿不属于当前账号")
            request_id, draft_id = object_id(row.get("id")), object_id(draft.get("id"))
            current = portal_json(await client.get(f"/api/hr/recruitment/requests/{request_id}/"))
            drafts = portal_json(await client.get(f"/api/hr/recruitment/requests/{request_id}/jd-versions/"), list)
            if current.get("created_by_id") != user.portal_user_id or current.get("id") != request_id:
                raise HTTPException(403, "招聘草稿不属于当前账号")
            saved = next((d for d in drafts if isinstance(d, dict) and d.get("id") == draft_id), None)
            if not saved or saved.get("request_id") != request_id or saved.get("state") != "draft":
                raise HTTPException(409, "招聘草稿状态已变化，请在页面核对")
            result = {"status": "draft_created", "request_id": request_id, "draft_id": draft_id,
                "input_version": version(current.get("input_version")), "version": version(saved.get("version")),
                "state": "draft", "artifact_available": False, "review_url": "/departments/hr/jobs"}
    return result


async def work_list(token, department):
    paths = {"product": "/api/product/tasks/", "hr": "/api/hr/recruitment/requests/", "engineering": "/api/engineering/jobs/"}
    if department not in paths:
        raise HTTPException(403, "部门不在允许范围")
    async with bound_portal(token, department) as (user, client, _):
        data = portal_json(await client.get(paths[department]), dict if department == "engineering" else list)
        rows = data.get("jobs") if department == "engineering" else data
        if not isinstance(rows, list):
            raise HTTPException(502, "部门工作列表响应异常")
        owner_key = {"product": "owner_id", "hr": "created_by_id"}.get(department)
        owned = [row for row in rows if isinstance(row, dict) and (owner_key is None or row.get(owner_key) == user.portal_user_id)]
        # Engineering's existing jobs endpoint filters owner=request.user in ORM.
        fields = {"product": ("title", "state", "stage", "version", "updated_at"),
                  "hr": ("position_name", "input_version", "official_jd_stale", "updated_at"),
                  "engineering": ("status", "region", "updated_at")}[department]
        items = []
        for row in owned[:20]:
            item = {"id": object_id(row.get("id"))}
            item.update({key: value[:200] if isinstance(value, str) else value for key in fields
                         if isinstance(value := row.get(key), (str, int, bool))})
            items.append(item)
        result = {"department": department, "items": items, "truncated": len(owned) > 20}
    return result


def create_mcp_app():
    server = Server("enterprise-knowledge", instructions="按本人现有授权使用部门知识和输入草稿；空结果不编造来源，草稿保存不代表文档已生成，不调用审批。")
    tools = [types.Tool(name=name, description=description, inputSchema={
        "type": "object", "properties": {"question": {"type": "string", "minLength": 1, "maxLength": limit}},
        "required": ["question"], "additionalProperties": False,
    }) for name, description, limit in (
        ("product_knowledge_retrieve", "按本人现有产品知识授权检索真实来源，供当前对话模型使用。", 2000),
        ("engineering_knowledge_retrieve", "按本人现有工程任务和部门权限检索工程知识来源。", 1000),
    )]
    tools += [types.Tool(name=name, description=description, inputSchema={"type": "object",
        "properties": {field: schema}, "required": [field], "additionalProperties": False})
        for name, description, field, schema in (
            ("product_create_draft", "保存本人项目输入草稿供页面审查，不生成文档或启动工作队列。", "message", {"type": "string", "minLength": 1, "maxLength": 8000}),
            ("hr_create_intake_draft", "从招聘说明保存本人本地提取草稿，供人事页面审查；不生成或确认正式JD。", "text", {"type": "string", "minLength": 1, "maxLength": 8000}),
            ("department_work_list", "列出本人可读的部门工作摘要，最多20条，不返回正文与配置。", "department", {"type": "string", "enum": ["product", "hr", "engineering"]}),
        )]

    @server.list_tools()
    async def list_tools():
        return tools

    @server.call_tool()
    async def call_tool(name, arguments):
        request = server.request_context.request
        actor = getattr(request, "user", None)
        if not isinstance(actor, AuthenticatedUser):
            return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text="企业知识会话未认证")])
        department = {"product_knowledge_retrieve": "product", "engineering_knowledge_retrieve": "engineering"}.get(name)
        try:
            if name == "product_create_draft":
                result = await create_draft(actor.access_token.token, "product", arguments.get("message"))
            elif name == "hr_create_intake_draft":
                result = await create_draft(actor.access_token.token, "hr", arguments.get("text"))
            elif name == "department_work_list":
                result = await work_list(actor.access_token.token, arguments.get("department"))
            elif department is None:
                raise HTTPException(403, "知识工具不在允许范围")
            else:
                result = await knowledge_question(actor.access_token.token, department, arguments.get("question"))
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))])
        except HTTPException as exc:
            error = {"code": "knowledge_denied" if exc.status_code in {401, 403} else "knowledge_unavailable", "message": exc.detail}
        except httpx.HTTPError:
            error = {"code": "knowledge_unavailable", "message": "企业服务暂时不可用；创建草稿时请先在页面核对，避免重复创建" if name in {"product_create_draft", "hr_create_intake_draft"} else "企业服务暂时不可用"}
        return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=json.dumps(error, ensure_ascii=False))])

    hosts = ["localhost", "127.0.0.1", "gateway", "openclaw-gateway", "host.docker.internal"]
    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True, max_request_body_size=32768,
        security_settings=TransportSecuritySettings(allowed_hosts=hosts + [h + ":*" for h in hosts],
            allowed_origins=["http://" + h + ":*" for h in hosts] + ["https://" + h + ":*" for h in hosts]))
    starlette_app = Starlette(routes=[Route("/mcp", RequireAuthMiddleware(manager.handle_request, ["enterprise_knowledge"]))],
        middleware=[Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(ContainerTokenVerifier()))],
        lifespan=lambda app: manager.run())

    async def app(scope, receive, send):
        async def no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]
            await send(message)
        await starlette_app(scope, receive, no_cache)
    return app, manager


# Mount at /api/enterprise and enter mcp_session_manager.run() in the parent's
# lifespan (mounted Starlette lifespans are not automatically entered).
mcp_http_app, mcp_session_manager = create_mcp_app()
