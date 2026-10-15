"""Server-side portal sessions. No platform tokens or user-supplied origins."""

import base64
import hashlib
import json
import re
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings

SESSION_COOKIE = "enterprise_portal_session"
CSRF_COOKIE = "enterprise_portal_csrf"


def session_cipher() -> Fernet:
    secret = settings.jwt_secret
    if len(secret) < 32 or secret == "change-me-in-production":
        raise HTTPException(503, "企业会话加密尚未配置")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("enterprise-session:" + secret).encode()).digest()))


def seal_session(user_id: str, portal_user_id: int, cookies: dict, csrf: str) -> str:
    data = {"user_id": user_id, "portal_user_id": portal_user_id, "cookies": cookies, "csrf": csrf}
    return session_cipher().encrypt(json.dumps(data).encode()).decode()


def open_session(user) -> dict:
    try:
        data = json.loads(session_cipher().decrypt(user.portal_session_enc.encode()))
        if data["user_id"] != user.id or data["portal_user_id"] != user.portal_user_id:
            raise ValueError("account mismatch")
        cookies = data["cookies"]
        if set(cookies) != {SESSION_COOKIE, CSRF_COOKIE} or not all(isinstance(v, str) and v for v in cookies.values()):
            raise ValueError("invalid cookies")
        if not isinstance(data["csrf"], str) or not data["csrf"]:
            raise ValueError("invalid csrf")
        return data
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(401, "请重新绑定企业业务账号") from None


def portal_origin() -> str:
    value = settings.portal_base_url.rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(503, "企业业务服务尚未配置")
    return value


def portal_client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=portal_origin(), timeout=settings.portal_timeout_seconds,
                            follow_redirects=False, trust_env=False, cookies=cookies,
                            headers={"Accept": "application/json"})


def json_response(response: httpx.Response, expected_type):
    if response.status_code in {401, 403}:
        raise HTTPException(response.status_code, "企业会话已失效或业务权限不足")
    if response.status_code == 429:
        raise HTTPException(429, "企业账号登录尝试过多，请稍后重试")
    if response.status_code != 200 or "application/json" not in response.headers.get("content-type", ""):
        raise HTTPException(502, "企业业务服务响应异常")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "企业业务服务响应异常") from None
    if not isinstance(data, expected_type):
        raise HTTPException(502, "企业业务服务响应异常")
    return data


async def portal_profile(client: httpx.AsyncClient, expected_id: int | None = None):
    profile = json_response(await client.get("/api/me/"), dict)
    portal_id = profile.get("id")
    if type(portal_id) is not int or portal_id <= 0 or not isinstance(profile.get("roles"), list):
        raise HTTPException(502, "企业业务身份响应异常")
    if expected_id is not None and portal_id != expected_id:
        raise HTTPException(401, "企业会话身份不匹配，请重新绑定")
    if profile.get("must_change_password") is not False:
        raise HTTPException(403, "请在企业业务门户完成初始密码修改后重新绑定")
    modules = json_response(await client.get("/api/modules/"), list)
    enabled = {item["code"] for item in modules if isinstance(item, dict) and item.get("enabled") is True and isinstance(item.get("code"), str)}
    roles = {item["code"] for item in profile["roles"] if isinstance(item, dict) and isinstance(item.get("code"), str)}
    if "general_manager" in roles and "business" in enabled:
        role, department = "general_manager", None
    else:
        mapping = {"product": "product", "hr": "hr", "cost": "engineering"}
        departments = [mapping[code] for code in mapping if code in enabled]
        primary = profile.get("department_code")
        primary = mapping.get(primary, primary) if isinstance(primary, str) else None
        if primary == "finance" and "business" in enabled and "general_manager" not in roles:
            # The portal's business module may come from a different ledger grant.
            permissions = json_response(await client.get("/api/business/ledgers/permissions/"), dict)
            grants = permissions.get("departments")
            if not isinstance(grants, list):
                raise HTTPException(502, "企业业务身份响应异常")
            if any(isinstance(grant, dict) and grant.get("department") == "finance" for grant in grants):
                departments.append("finance")
        department = primary if primary in departments else next(iter(departments), None)
        role = "employee" if department else "unassigned"
    return {"portal_user_id": portal_id, "business_role": role, "department_code": department}, enabled


def safe_business_path(path: str, method: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_./~-]+", path) or "//" in path or any(part in {"", ".", ".."} for part in path.rstrip("/").split("/")):
        raise HTTPException(400, "业务路径无效")
    root = path.split("/", 1)[0]
    allowed = root in {"product", "hr", "engineering", "business"}
    allowed |= path.rstrip("/") == "work/summary" and method in {"GET", "HEAD"}
    allowed |= bool(re.fullmatch(r"models/routes/[A-Za-z0-9_-]+/options/?", path)) and method in {"GET", "HEAD"}
    allowed |= bool(re.fullmatch(r"models/departments/(product|hr|cost)/ask/?", path)) and method == "POST"
    # Only historical reads: the new runtime owns agent execution.
    allowed |= bool(re.fullmatch(r"agent/(work(?:/[A-Za-z0-9_-]+(?:/events)?)?|management/(?:work|usage|references/[A-Za-z0-9_-]+(?:/download)?))/?", path)) and method in {"GET", "HEAD"}
    if not allowed:
        raise HTTPException(403, "此接口不在企业业务代理范围")
    return "/api/" + path
