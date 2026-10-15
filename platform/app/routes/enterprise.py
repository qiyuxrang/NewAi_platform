"""Bind each platform account to its own real portal session."""

import asyncio
import re
from tempfile import SpooledTemporaryFile

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.business_client import (
    CSRF_COOKIE, SESSION_COOKIE, json_response, open_session, portal_client,
    portal_origin, portal_profile, safe_business_path, seal_session,
)
from app.config import settings
from app.db.engine import get_db
from app.db.models import User
from app.enterprise import enterprise_identity

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=150)
    password: SecretStr = Field(min_length=1, max_length=1024)


def status_data(user, *, linked: bool, available: bool, message: str):
    return {"configured": bool(settings.portal_base_url), "linked": linked,
            "available": available, "message": message, **enterprise_identity(user)}


async def save_identity(db, user, identity, expected_session):
    # An administrator may revoke/rebind the account while the portal responds.
    await db.refresh(user)
    if user.portal_session_enc != expected_session:
        raise HTTPException(409, "企业业务会话已变化，请重试")
    if not user.is_active:
        raise HTTPException(401, "平台账号已停用")
    changed = False
    for name, value in identity.items():
        if getattr(user, name) != value:
            setattr(user, name, value)
            changed = True
    if changed:
        await db.commit()


async def invalidate(db, user, expected_session=None):
    if expected_session is not None:
        await db.refresh(user)
        if user.portal_session_enc != expected_session:
            return
    user.portal_session_enc = None
    await db.commit()


@router.post("/link")
async def link(req: LinkRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    previous = {name: getattr(user, name) for name in ("portal_user_id", "portal_session_enc", "business_role", "department_code")}
    try:
        async with portal_client() as client:
            csrf = json_response(await client.get("/api/csrf/"), dict).get("csrfToken")
            if not isinstance(csrf, str) or not csrf:
                raise HTTPException(502, "企业业务安全校验响应异常")
            headers = {"X-CSRFToken": csrf, "Origin": portal_origin(), "Referer": portal_origin() + "/"}
            json_response(await client.post("/api/login/", json={"username": req.username, "password": req.password.get_secret_value()}, headers=headers), dict)
            identity, _ = await portal_profile(client)
            # Django rotates the CSRF secret on login.
            csrf = json_response(await client.get("/api/csrf/"), dict).get("csrfToken")
            cookies = {key: client.cookies.get(key) for key in (SESSION_COOKIE, CSRF_COOKIE)}
            if not isinstance(csrf, str) or not csrf or not all(cookies.values()):
                raise HTTPException(502, "企业业务会话创建失败")
            encoded = seal_session(user.id, identity["portal_user_id"], cookies, csrf)
    except httpx.HTTPError:
        raise HTTPException(503, "企业业务服务暂时不可用") from None
    if previous["portal_user_id"] is not None and previous["portal_user_id"] != identity["portal_user_id"]:
        raise HTTPException(409, "账号已分配给其他企业用户，请由管理员解除原映射后再绑定")
    existing = (await db.execute(select(User).where(User.portal_user_id == identity["portal_user_id"], User.id != user.id))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "该企业业务账号已绑定其他平台账号")
    try:
        changed = await db.execute(update(User).where(User.id == user.id, User.is_active.is_(True),
            *(getattr(User, name) == value for name, value in previous.items()))
            .values(**identity, portal_session_enc=encoded))
        if changed.rowcount != 1:
            await db.rollback()
            raise HTTPException(409, "企业账号配置或状态已变化，请刷新后重新绑定")
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "该企业业务账号已绑定其他平台账号") from None
    return status_data(user, linked=True, available=True, message="企业业务账号已绑定")


@router.delete("/link")
async def unlink(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Preserve administrator-managed mapping and menu identity.
    await invalidate(db, user)
    return status_data(user, linked=False, available=False, message="企业业务会话已断开")


@router.get("/status")
async def get_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.portal_session_enc or not settings.portal_base_url:
        return status_data(user, linked=False, available=False, message="请绑定企业业务账号" if settings.portal_base_url else "企业业务服务尚未配置")
    try:
        expected_session = user.portal_session_enc
        session = open_session(user)
        async with portal_client(session["cookies"]) as client:
            identity, _ = await portal_profile(client, user.portal_user_id)
        await save_identity(db, user, identity, expected_session)
    except httpx.HTTPError:
        return status_data(user, linked=True, available=False, message="企业业务服务暂时不可用")
    except HTTPException as exc:
        if exc.status_code in {401, 403}:
            await invalidate(db, user, expected_session)
        return status_data(user, linked=bool(user.portal_session_enc), available=False, message=exc.detail)
    return status_data(user, linked=True, available=True, message="企业业务服务可用")


@router.api_route("/business/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_business(path: str, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    upstream_path = safe_business_path(path, request.method)
    expected_session = user.portal_session_enc
    session = open_session(user)
    client = portal_client(session["cookies"])
    upstream = None
    body_file = None
    try:
        identity, _ = await portal_profile(client, user.portal_user_id)
        await save_identity(db, user, identity, expected_session)
        if not enterprise_identity(user)["capabilities"]:
            raise HTTPException(403, "未分配企业业务权限")
        headers = {key: request.headers[key] for key in ("accept", "content-type", "range", "if-range", "idempotency-key") if key in request.headers}
        headers.update({"X-CSRFToken": session["csrf"], "Origin": portal_origin(), "Referer": portal_origin() + "/"})
        url = httpx.URL(portal_origin() + upstream_path).copy_with(query=request.scope.get("query_string", b""))
        length = request.headers.get("content-length")
        content = None
        if length is not None:
            if not length.isascii() or not length.isdecimal():
                raise HTTPException(400, "请求长度无效")
            headers["content-length"] = length
            content = request.stream() if int(length) else None
        elif request.method not in {"GET", "HEAD"}:
            # Django's WSGI server requires Content-Length. Spool unknown-length
            # uploads to disk instead of buffering a whole resume batch in RAM.
            body_file = SpooledTemporaryFile(max_size=1024 * 1024)
            async for chunk in request.stream():
                await asyncio.to_thread(body_file.write, chunk)
            headers["content-length"] = str(body_file.tell())
            body_file.seek(0)

            async def spooled_body():
                while chunk := await asyncio.to_thread(body_file.read, 65536):
                    yield chunk
            content = spooled_body()
        outgoing = client.build_request(request.method, url, headers=headers, content=content)
        if "text/event-stream" in headers.get("accept", ""):
            outgoing.extensions["timeout"]["read"] = None
        upstream = await client.send(outgoing, stream=True)
        if upstream.status_code == 401:
            await invalidate(db, user, expected_session)
        document_preview = (request.method == "GET" and upstream.status_code == 200
            and re.fullmatch(r"product/knowledge/datasets/[A-Za-z0-9_-]+/documents/[A-Za-z0-9_-]+/preview/", path)
            and upstream.headers.get("content-security-policy", "").startswith("sandbox;"))
        if 300 <= upstream.status_code < 400 or ("text/html" in upstream.headers.get("content-type", "").lower() and not document_preview):
            raise HTTPException(502, "企业业务服务响应异常，请检查业务会话")
        response_headers = {key: upstream.headers[key] for key in ("content-type", "content-disposition", "content-range", "accept-ranges", "retry-after", "content-security-policy") if key in upstream.headers}
        response_headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Accel-Buffering": "no"})

        async def body():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(body(), status_code=upstream.status_code, headers=response_headers)
    except httpx.HTTPError:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        raise HTTPException(503, "企业业务服务暂时不可用") from None
    except BaseException as exc:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        if isinstance(exc, HTTPException) and exc.status_code == 401:
            await invalidate(db, user, expected_session)
        raise
    finally:
        if body_file is not None:
            body_file.close()
