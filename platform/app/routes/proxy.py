"""Request routing — reverse-proxy from gateway to per-user openclaw containers.

Authenticated users' API requests (chat, sessions, WebSocket) are
forwarded to their individual Docker container.
"""

from __future__ import annotations

import logging

import docker
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.container.manager import ensure_running, get_container
from app.db.engine import async_session, get_db
from app.db.models import User

logger = logging.getLogger("platform.routes.proxy")
router = APIRouter(prefix="/api/openclaw", tags=["proxy"])


async def _container_target(db: AsyncSession, user: User, dev_url: str | None = None) -> tuple[str, dict[str, str]]:
    """Resolve the user's own Bridge and its server-side container credential."""
    if user.role != "admin" and user.business_role == "unassigned":
        raise HTTPException(status_code=403, detail="请先连接业务账号，或由管理员分配部门")
    if user.runtime_mode == "shared":
        raise HTTPException(status_code=409, detail="User is assigned to shared OpenClaw mode; use /api/shared-openclaw instead")
    # Local dev mode: bypass Docker, forward to local openclaw web directly
    if dev_url or settings.dev_openclaw_url:
        base_url, token = dev_url or settings.dev_openclaw_url, settings.dev_bridge_token
    else:
        try:
            container = await ensure_running(db, user.id)
        except docker.errors.ImageNotFound:
            raise HTTPException(status_code=503, detail="独立 Agent 运行镜像尚未构建，可以先使用部门功能") from None
        if container.user_id != user.id:
            raise HTTPException(status_code=403, detail="运行环境账号不匹配")
        base_url = f"http://{container.internal_host}:{container.internal_port}"
        token = container.container_token
    if not token or token == "dev-token":
        raise HTTPException(status_code=503, detail="运行环境鉴权尚未配置")
    return base_url, {"Authorization": "Bearer " + token}


async def _container_api_request(
    db: AsyncSession,
    user: User,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    timeout: float = 30.0,
) -> object:
    """Send a direct API request to the user's dedicated OpenClaw runtime."""
    base_url, bridge_headers = await _container_target(db, user)
    await db.close()

    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.request(
                method=method,
                url=f"{base_url}{path}",
                json=json,
                headers=bridge_headers,
            )
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务首次使用正在初始化中，请等待几秒钟",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenClaw request failed: {exc}",
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        raise HTTPException(
            status_code=response.status_code,
            detail=detail or "OpenClaw request failed",
        )

    return payload


# ---------------------------------------------------------------------------
# Container info & maintenance (must be before the catch-all route)
# ---------------------------------------------------------------------------

@router.get("/container/info")
async def container_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's container name and status for troubleshooting."""
    container = await get_container(db, user.id)
    if container is None:
        return {"container_name": None, "status": "none", "docker_id": None}
    short_id = user.id[:8]
    container_name = f"openclaw-user-{short_id}"

    # Get real Docker status and port mappings
    docker_status = container.status
    ports: list[dict] = []
    try:
        client = docker.from_env()
        dc = client.containers.get(container.docker_id)
        docker_status = dc.status
        # Extract port mappings: {container_port: [{HostIp, HostPort}]}
        port_bindings = dc.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for container_port, bindings in port_bindings.items():
            entry: dict = {"container_port": container_port, "host_port": None}
            if bindings:
                host_port = bindings[0].get("HostPort", "")
                host_ip = bindings[0].get("HostIp", "0.0.0.0")
                if host_port:
                    entry["host_port"] = f"{host_ip}:{host_port}"
            ports.append(entry)
    except Exception:
        pass

    return {
        "container_name": container_name,
        "status": docker_status,
        "docker_id": container.docker_id,
        "created_at": container.created_at.isoformat() if container.created_at else None,
        "ports": ports,
    }


def _sanitize_openclaw_config(config_json: str) -> tuple[str, list[str]]:
    """Remove known invalid config entries that prevent openclaw from starting.

    Returns (fixed_json, list_of_fixes_applied).
    """
    import json as _json

    fixes: list[str] = []
    try:
        cfg = _json.loads(config_json)
    except _json.JSONDecodeError:
        return config_json, ["Config is not valid JSON — cannot auto-fix"]

    # Fix: remove unknown channel ids (e.g. "web" which is not a valid channel)
    known_channels = {"telegram", "discord", "slack", "signal", "imessage", "feishu", "qqbot", "whatsapp", "matrix", "msteams", "zalo"}
    channels = cfg.get("channels", {})
    bad_channels = [ch for ch in list(channels.keys()) if ch not in known_channels]
    for ch in bad_channels:
        del channels[ch]
        fixes.append(f"Removed unknown channel: channels.{ch}")

    # Fix: remove duplicate plugin entries that cause warnings
    # (just a cleanup, not a blocker)

    return _json.dumps(cfg, indent=2, ensure_ascii=False), fixes


@router.post("/container/doctor-fix")
async def container_doctor_fix(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fix the user's container config and restart.

    Directly edits openclaw.json to remove known invalid entries, then runs
    'openclaw doctor --fix', and restarts the container. Works even when the
    container is in a restart loop.
    """
    container = await get_container(db, user.id)
    if container is None:
        raise HTTPException(status_code=404, detail="No container found")

    short_id = user.id[:8]
    volume_name = f"openclaw-data-{short_id}"

    try:
        client = docker.from_env()
        dc = client.containers.get(container.docker_id)
        docker_status = dc.status

        # Step 1: Stop the container if it's misbehaving
        need_external_fix = docker_status in ("restarting", "exited", "created")
        if need_external_fix:
            logger.info("Container %s is %s, stopping for repair", short_id, docker_status)
            try:
                dc.stop(timeout=5)
            except Exception:
                try:
                    dc.kill()
                except Exception:
                    pass

        # Step 2: Sanitize config via a lightweight helper container
        # Read config
        read_result = client.containers.run(
            image="python:3.13-alpine",
            command=["cat", "/data/openclaw.json"],
            volumes={volume_name: {"bind": "/data", "mode": "ro"}},
            remove=True,
            detach=False,
            stdout=True,
            stderr=False,
        )
        config_content = read_result.decode("utf-8", errors="replace") if isinstance(read_result, bytes) else str(read_result)
        fixed_content, fixes = _sanitize_openclaw_config(config_content)

        if fixes:
            # Write fixed config back
            import base64
            b64 = base64.b64encode(fixed_content.encode("utf-8")).decode("ascii")
            client.containers.run(
                image="python:3.13-alpine",
                command=["sh", "-c", f"echo '{b64}' | base64 -d > /data/openclaw.json"],
                volumes={volume_name: {"bind": "/data", "mode": "rw"}},
                remove=True,
                detach=False,
            )
            logger.info("Config sanitized for %s: %s", short_id, fixes)

        # Step 3: Run openclaw doctor --fix
        doctor_stdout = ""
        if docker_status == "running" and not need_external_fix:
            exit_code, output = dc.exec_run(
                cmd=["node", "/app/openclaw.mjs", "doctor", "--fix"],
                user="root",
                demux=True,
            )
            doctor_stdout = (output[0] or b"").decode("utf-8", errors="replace")
            doctor_stderr = (output[1] or b"").decode("utf-8", errors="replace")
            if doctor_stderr:
                doctor_stdout += "\n" + doctor_stderr
        else:
            # Run via helper container
            try:
                image = dc.image.id
                result = client.containers.run(
                    image=image,
                    command=["node", "/app/openclaw.mjs", "doctor", "--fix"],
                    volumes={volume_name: {"bind": "/root/.openclaw", "mode": "rw"}},
                    user="root",
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                )
                doctor_stdout = result.decode("utf-8", errors="replace") if isinstance(result, bytes) else str(result)
            except Exception as e:
                doctor_stdout = f"doctor --fix skipped: {e}"

        # Step 4: Restart the container
        dc.reload()
        if dc.status != "running":
            dc.start()
        else:
            dc.restart(timeout=10)

        summary = "\n".join(f"- {f}" for f in fixes) if fixes else "No config issues found"
        return {
            "exit_code": 0,
            "stdout": f"Config fixes:\n{summary}\n\nDoctor output:\n{doctor_stdout}",
            "stderr": "",
            "restarted": True,
        }

    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Docker container not found")
    except Exception as e:
        logger.error("doctor --fix failed for %s: %s", short_id, e, exc_info=True)
        # Try to restart the container even if fix failed
        try:
            dc = client.containers.get(container.docker_id)
            if dc.status != "running":
                dc.start()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Abort endpoints (must be before the catch-all route)
# These endpoints handle stopping an active model run/session
# ---------------------------------------------------------------------------

@router.post("/runs/{run_id}/abort")
async def abort_run(
    run_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Abort a specific agent run (stop model inference)."""
    import json as _json
    body = await request.body()
    try:
        parsed = _json.loads(body) if body else {}
        session_key = parsed.get("sessionKey") or parsed.get("session_key")
    except (_json.JSONDecodeError, AttributeError):
        session_key = None

    logger.info("[abort_run] User %s requested abort for run %s, session: %s", user.id, run_id, session_key)
    payload = {"sessionKey": session_key} if session_key else {}
    return await _container_api_request(
        db,
        user,
        "POST",
        f"/api/runs/{run_id}/abort",
        json=payload,
    )


@router.post("/sessions/{session_key}/abort-active")
async def abort_active_session_run(
    session_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Abort the currently active run in a session."""
    logger.info("[abort_active] User %s requested abort for session %s", user.id, session_key)
    return await _container_api_request(
        db,
        user,
        "POST",
        f"/api/sessions/{session_key}/abort-active",
    )


# ---------------------------------------------------------------------------
# SSE event stream (must be before the catch-all route)
# ---------------------------------------------------------------------------

@router.get("/events/stream")
async def proxy_events_stream(
    request: Request,
    token: str = "",
):
    """SSE proxy for chat events — auth via query param since EventSource can't set headers."""
    from app.auth.service import decode_token, get_user_by_id
    from fastapi.responses import StreamingResponse

    # Authenticate via query param token
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async with async_session() as db:
        user = await get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found")
        base_url, bridge_headers = await _container_target(db, user)

    target_url = f"{base_url}/api/events/stream"
    client = httpx.AsyncClient(timeout=None, trust_env=False)
    upstream = None
    try:
        upstream = await client.send(client.build_request("GET", target_url, headers=bridge_headers), stream=True)
        if upstream.status_code != 200:
            raise HTTPException(
                status_code=upstream.status_code if upstream.status_code >= 400 else 502,
                detail="运行环境鉴权失败" if upstream.status_code in {401, 403} else "运行环境事件服务暂时不可用",
            )
    except BaseException as exc:
        try:
            if upstream is not None:
                await upstream.aclose()
        finally:
            await client.aclose()
        if isinstance(exc, httpx.HTTPError):
            raise HTTPException(status_code=503, detail="运行环境事件服务暂时不可用") from None
        raise

    async def _stream_sse():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            yield b"data: {\"error\":\"upstream disconnected\"}\n\n"
        finally:
            try:
                await upstream.aclose()
            finally:
                await client.aclose()

    return StreamingResponse(
        _stream_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# File proxy (supports token as query param for <img> tags)
# Covers both /filemanager/download and /filemanager/serve
# ---------------------------------------------------------------------------

async def _proxy_file_request(request: Request, token: str, bridge_path: str):
    """Shared helper: authenticate via query-param or header, then proxy to bridge."""
    from app.auth.service import decode_token, get_user_by_id
    from fastapi.responses import Response

    # Try query-param token first, fall back to Authorization header
    user = None
    if token:
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            async with async_session() as db:
                user = await get_user_by_id(db, payload["sub"])
    if not user:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_token(auth_header[7:])
            if payload and payload.get("type") == "access":
                async with async_session() as db:
                    user = await get_user_by_id(db, payload["sub"])

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    async with async_session() as db:
        base_url, bridge_headers = await _container_target(db, user)

    target_url = f"{base_url}/api/{bridge_path}"
    params = [(key, value) for key, value in request.query_params.multi_items() if key != "token"]

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            resp = await client.request(method="GET", url=target_url, params=params, headers=bridge_headers)
        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Container not ready",
            )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/octet-stream"),
        headers={k: v for k, v in resp.headers.items() if k.lower() in ("content-disposition",)},
    )


@router.get("/filemanager/download")
async def proxy_file_download(request: Request, token: str = ""):
    """Proxy file download — supports query-param token for <img> tags."""
    return await _proxy_file_request(request, token, "filemanager/download")


@router.get("/filemanager/serve")
async def proxy_file_serve(request: Request, token: str = ""):
    """Proxy file serve — supports query-param token for <img> tags."""
    return await _proxy_file_request(request, token, "filemanager/serve")


# ---------------------------------------------------------------------------
# HTTP reverse proxy  (catch-all for /api/openclaw/{path})
# ---------------------------------------------------------------------------

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_http(
    path: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Forward HTTP requests to the user's openclaw container or shared runtime."""
    from fastapi.responses import Response, JSONResponse
    import json as _json

    if any(segment in (".", "..") for segment in path.split("/")) or any(c in path for c in ("%", "\\", "?", "#")) or "//" in path:
        raise HTTPException(status_code=400, detail="Invalid runtime path")
    admin_roots = {"models", "plugins", "channels", "settings", "nodes", "terminal"}
    root = path.split("/", 1)[0]
    if user.role != "admin" and root in admin_roots and not (path == "models/catalog" and request.method == "GET"):
        raise HTTPException(status_code=403, detail="管理员权限不足")

    # For shared mode users, redirect to /api/shared-openclaw endpoint
    if user.runtime_mode == "shared":
        if not settings.shared_openclaw_enabled:
            raise HTTPException(status_code=409, detail="企业模式需要独立账号运行环境")
        from app.shared_runtime import shared_runtime_request, ensure_shared_agent_binding
        ctx = await ensure_shared_agent_binding(db, user)

        body = await request.body()
        json_body = None
        if body:
            try:
                json_body = _json.loads(body)
            except _json.JSONDecodeError:
                pass

        # Build params dict from query string
        params = dict(request.query_params) if request.query_params else None

        # Forward to shared runtime
        result = await shared_runtime_request(
            method=request.method,
            path=f"/api/{path}",
            json=json_body,
            params=params,
            timeout=120,
        )
        return JSONResponse(content=result if isinstance(result, dict) else {"data": result})

    # For non-shared mode, use regular container routing
    base_url, bridge_headers = await _container_target(db, user)
    # Close the session explicitly so the connection returns to the pool
    # before the potentially long upstream call (up to 120s).
    await db.close()

    target_url = f"{base_url}/api/{path}"

    # Forward query params
    params = [(key, value) for key, value in request.query_params.multi_items() if key != "token"]

    body = await request.body()

    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                params=params,
                headers={**bridge_headers, "content-type": request.headers.get("content-type", "application/json")},
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="服务首次使用正在初始化中，请等待几秒钟",
            )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
        headers={k: v for k, v in resp.headers.items() if k.lower() in ("content-disposition",)},
    )


# ---------------------------------------------------------------------------
# WebSocket reverse proxy
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def proxy_websocket(
    websocket: WebSocket,
    token: str = "",  # passed as query param ?token=xxx
):
    """Forward WebSocket connections directly to OpenClaw Gateway."""
    from app.auth.service import decode_token, get_user_by_id

    # Authenticate, then release DB session immediately
    async with async_session() as db:
        payload = decode_token(token)
        if payload is None or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return

        user = await get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            await websocket.close(code=4001, reason="User not found")
            return

        if user.role != "admin":
            await websocket.close(code=4003, reason="Admin access required for raw gateway RPC")
            return

        base_url, bridge_headers = await _container_target(db, user, settings.dev_gateway_url or None)
        target_ws_url = base_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        if not settings.dev_gateway_url:
            target_ws_url = target_ws_url.rstrip("/") + "/ws"
    # DB session is now released — not held during long-lived WebSocket relay

    await websocket.accept()

    import asyncio
    import websockets
    from websockets.legacy.client import connect as connect_ws

    try:
        # Retry connection — container gateway may still be starting
        upstream = None
        for _attempt in range(10):
            try:
                upstream = await connect_ws(target_ws_url, origin="http://127.0.0.1:8080", extra_headers=bridge_headers)
                break
            except (ConnectionRefusedError, OSError):
                if _attempt < 9:
                    await asyncio.sleep(2)
        if upstream is None:
            await websocket.close(code=1013, reason="Container gateway not ready")
            return

        async def client_to_upstream():
            try:
                while True:
                    data = await websocket.receive_text()
                    await upstream.send(data)
            except (WebSocketDisconnect, Exception):
                pass

        async def upstream_to_client():
            try:
                async for message in upstream:
                    try:
                        await websocket.send_text(message)
                    except RuntimeError:
                        break
            except websockets.ConnectionClosed:
                pass

        tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
        finally:
            await upstream.close()

    except Exception as exc:
        logger.error("WebSocket 代理异常: %s", exc, exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/terminal/ws")
async def proxy_terminal_websocket(
    websocket: WebSocket,
    token: str = "",
):
    """Forward WebSocket terminal stream to per-user bridge terminal endpoint."""
    from app.auth.service import decode_token, get_user_by_id

    async with async_session() as db:
        payload = decode_token(token)
        if payload is None or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return

        user = await get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            await websocket.close(code=4001, reason="User not found")
            return

        if user.role != "admin":
            await websocket.close(code=4003, reason="Admin access required")
            return

        base_url, bridge_headers = await _container_target(db, user)
        target_ws_url = base_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1).rstrip("/") + "/api/terminal/ws"

    await websocket.accept()

    import asyncio
    import websockets
    from websockets.legacy.client import connect as connect_ws

    try:
        upstream = None
        for _attempt in range(10):
            try:
                upstream = await connect_ws(target_ws_url, origin="http://127.0.0.1:8080", extra_headers=bridge_headers)
                break
            except (ConnectionRefusedError, OSError):
                if _attempt < 9:
                    await asyncio.sleep(1)
        if upstream is None:
            await websocket.close(code=1013, reason="Terminal service not ready")
            return

        async def client_to_upstream():
            try:
                while True:
                    data = await websocket.receive_text()
                    await upstream.send(data)
            except (WebSocketDisconnect, Exception):
                pass

        async def upstream_to_client():
            try:
                async for message in upstream:
                    try:
                        await websocket.send_text(message)
                    except RuntimeError:
                        break
            except websockets.ConnectionClosed:
                pass

        tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
        try:
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
        finally:
            await upstream.close()
    except Exception as exc:
        logger.error("Terminal WebSocket 代理异常: %s", exc, exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
