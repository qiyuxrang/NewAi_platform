"""Headless console layout checks against a built frontend; all APIs/WS isolated.

Usage: python frontend/scripts/check-console-layout.py --url http://127.0.0.1:5173
The server must already be running. This script never starts or restarts services.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from playwright.sync_api import sync_playwright


ROUTES = [
    "/dashboard", "/settings", "/settings/business-link", "/agents",
    "/agents/create", "/agents/main", "/skills", "/channels", "/plugins",
    "/models", "/files", "/knowledge", "/sessions", "/cron", "/nodes",
    "/api", "/settings/overview", "/settings/system", "/terminal",
]
STAMP = "2026-10-14T01:00:00Z"
LONG_NAME = "LayoutFixtureLongFileNameWithoutAnySpaces" * 6 + ".txt"
SESSION_KEY = "agent:main:layout-fixture"


def fixture(path, query, mode):
    loaded = mode == "loaded"
    agent = {"id": "main", "name": "布局测试助手", "identity": {"emoji": "🤖"}}
    agents = {"defaultId": "main", "mainKey": "main", "scope": "user", "agents": [agent] if loaded else []}
    session = {"key": SESSION_KEY, "title": "布局测试会话", "created_at": STAMP, "updated_at": STAMP}
    browse_path = query.get("path", [""])[0]
    file_entry = {"name": LONG_NAME, "path": f"{browse_path}/{LONG_NAME}".lstrip("/"), "type": "file", "size": 2048, "content_type": "text/plain", "modified": STAMP}
    values = {
        "/api/auth/me": {"id": "layout-fixture", "username": "布局验收账号", "email": "fixture@example.invalid", "created_at": STAMP, "role": "admin", "business_role": "unassigned", "department_code": None, "portal_user_id": None, "capabilities": []},
        "/api/openclaw/ping": {"message": "pong"},
        "/api/openclaw/container/info": {"container_name": "layout-fixture", "status": "running", "docker_id": None, "created_at": STAMP, "ports": []},
        "/api/enterprise/status": {"configured": True, "linked": False, "available": False, "message": "布局测试：业务账号未连接", "portal_user_id": None},
        "/api/openclaw/agents": agents,
        "/api/openclaw/agents/main/files": {"agentId": "main", "workspace": "workspace", "files": [{"name": "SOUL.md", "path": "workspace/SOUL.md", "missing": False, "size": 1024, "updatedAtMs": 0}] if loaded else []},
        "/api/openclaw/agents/main/files/SOUL.md": {"agentId": "main", "workspace": "workspace", "file": {"name": "SOUL.md", "content": "# 布局测试\n这是用于文件详情的只读测试正文。"}},
        "/api/openclaw/sessions": [session] if loaded else [],
        f"/api/openclaw/sessions/{SESSION_KEY}": {**session, "messages": [{"role": "assistant", "content": "这是详情面板的测试正文。\n\n| 项目 | 状态 |\n| --- | --- |\n| 布局 | 已加载 |", "timestamp": STAMP}]},
        "/api/openclaw/skills": [{"name": "fixture-skill", "description": "布局测试技能", "source": "fixture", "disabled": False}] if loaded else [],
        "/api/openclaw/marketplaces/recommended": {"categories": [{"id": "fixture", "name": "布局测试", "name_en": "Fixture", "icon": "📄", "description": "测试技能分类", "order": 1, "skills": [{"name": "fixture-recommended", "description": "只读推荐技能", "category": "fixture"}]}] if loaded else []},
        "/api/openclaw/channels/status": {"ts": 0, "channelOrder": ["telegram"] if loaded else [], "channelLabels": {"telegram": "Telegram"}, "channels": {}, "channelAccounts": {"telegram": [{"accountId": "fixture", "name": "测试渠道", "enabled": True, "configured": True, "running": True, "connected": True}]}, "channelDefaultAccountId": {"telegram": "fixture"}},
        "/api/openclaw/channels/configured": {"success": True, "channels": ["telegram"] if loaded else []},
        "/api/openclaw/channels/telegram/config": {"config": {"enabled": True}},
        "/api/openclaw/plugins": [{"name": "fixture-plugin", "description": "已加载插件", "source": "fixture", "version": "1.0", "enabled": True, "agents": [], "commands": [], "skills": []}] if loaded else [],
        "/api/openclaw/models": {"models": [{"id": "fixture/model", "name": "测试模型", "provider": "fixture"}] if loaded else [], "configuredModel": "fixture/model" if loaded else "", "configuredProviders": {"fixture": {"api": "openai-completions", "baseUrl": "https://example.invalid/v1", "models": [{"id": "model", "name": "测试模型"}]}} if loaded else {}},
        "/api/openclaw/filemanager/browse": {"type": "directory", "path": browse_path, "root": "/workspace", "items": [file_entry] if loaded else []},
        "/api/openclaw/cron/jobs": [{"id": "fixture-cron", "name": "布局测试任务", "enabled": True, "schedule_kind": "cron", "schedule_display": "每日 09:00", "schedule_expr": "0 9 * * *", "schedule_every_ms": None, "message": "检查布局测试数据", "deliver": False, "channel": None, "to": None, "next_run_at_ms": 1791939600000, "last_run_at_ms": 1791853200000, "last_status": "ok", "last_error": None, "created_at_ms": 1791853200000}] if loaded else [],
        "/api/openclaw/nodes": {"nodes": [{"nodeId": "fixture-node", "displayName": "布局测试节点", "platform": "linux", "version": "1.0", "caps": ["browser"], "commands": ["browser.open"], "permissions": {"browser": True}, "paired": True, "connected": True}] if loaded else [], "pending": [], "paired": []},
        "/api/openclaw/nodes/fixture-node": {"nodeId": "fixture-node", "displayName": "布局测试节点", "connected": True},
        "/api/openclaw/status": {"gateway_connected": True, "config_path": "/workspace/openclaw.json", "workspace": "workspace", "model": "fixture/model"},
        "/api/openclaw/settings/config": {"config": {"gateway": {"mode": "local", "port": 18789, "bind": "loopback", "controlUi": {"allowedOrigins": []}}}},
    }
    if path == "/api/openclaw/filemanager/browse" and browse_path.endswith(LONG_NAME):
        return {"type": "file", "path": browse_path, "name": LONG_NAME, "size": 2048, "content_type": "text/plain", "modified": STAMP, "content": "布局文件预览正文。"}
    return values.get(path)


GEOMETRY = r"""() => {
  const main = document.querySelector('.enterprise-shell > div > main');
  const aside = document.querySelector('.enterprise-shell > aside');
  const describe = el => ({tag:el.tagName, class:el.className?.baseVal ?? el.className, text:(el.innerText || '').slice(0,120)});
  const box = el => { const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,width:r.width,top:r.top,bottom:r.bottom}; };
  const login=document.querySelector('.login-card');
  const result = {document:{width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth},sidebar:aside ? box(aside) : null,main:null,root:null,login:login ? box(login) : null,dialogs:Array.from(document.querySelectorAll('.fixed.inset-0 > div')).map(box),overflow:[],animations:[]};
  if (!main) return result;
  const mb=box(main), style=getComputedStyle(main), left=mb.left+parseFloat(style.paddingLeft), right=mb.right-parseFloat(style.paddingRight)-(main.offsetWidth-main.clientWidth);
  result.main={...mb,clientWidth:main.clientWidth,scrollWidth:main.scrollWidth,contentLeft:left,contentRight:right,contentWidth:right-left};
  if (main.firstElementChild) result.root={...box(main.firstElementChild),...describe(main.firstElementChild)};
  // Local horizontal scrollers may contain wider tables; a hidden shell is not an exemption.
  const contained = el => { for(let p=el.parentElement;p && p!==main;p=p.parentElement) { const s=getComputedStyle(p),r=box(p); if(['auto','scroll'].includes(s.overflowX) && r.left>=left-2 && r.right<=right+2) return true; } return false; };
  for(const el of main.querySelectorAll('*')) {
    const r=box(el),s=getComputedStyle(el);
    if (!r.width || !r.bottom || s.position==='fixed' || contained(el)) continue;
    if (r.left<left-2 || r.right>right+2) result.overflow.push({...describe(el),...r,reason:'box outside main content'});
    else if(el.clientWidth>0 && el.scrollWidth>el.clientWidth+2 && s.overflowX==='visible') {
      let clipped=false;
      for(let p=el.parentElement;p && p!==main;p=p.parentElement) { const ps=getComputedStyle(p); if(ps.textOverflow==='ellipsis' || ps.overflowX==='auto' || ps.overflowX==='scroll') { clipped=true; break; } }
      if(!clipped) result.overflow.push({...describe(el),...r,clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,reason:'uncontained visible content overflow'});
    }
  }
  result.overflow=result.overflow.slice(0,30);
  result.animations=main.getAnimations().map(a=>({playState:a.playState,keyframes:a.effect?.getKeyframes()}));
  return result;
}"""


def run(args):
    if args.gm_dashboard_only:
        args.routes = ["/dashboard"]
    output = Path(args.output or f"frontend/layout-evidence/console-{datetime.now().strftime('%Y%m%d-%H%M%S')}").resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "RUNNING", "checks": [], "failures": [], "requests": [], "errors": [], "scope": {"routes": args.routes, "widths": args.widths, "states": args.states, "isolation": "Every API and WebSocket is intercepted; no backend requests are forwarded.", "not_tested": ["department routes", "real backend health or data", "write actions, login submission, restart/doctor, installs/deletes", "every possible configuration modal and error-response branch", "authenticated employee department-home redirect", "real terminal execution", "direct hard-load of /api (server API namespace overlaps the frontend route; tested through React Router Link)"]}}
    if args.check_api_reload:
        report["scope"]["not_tested"].pop()
    report["scope"]["roles"] = ["admin/general_manager"] if args.gm_dashboard_only else ["admin/unassigned", "admin/general_manager"]
    evidence = output / "console-layout.json"
    origin = urlsplit(args.url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in args.widths:
            for mode in args.states:
                context = browser.new_context(viewport={"width": width, "height": 1000}, service_workers="block")
                context.add_init_script("localStorage.setItem('openclaw_access_token','layout-fixture'); localStorage.setItem('openclaw_refresh_token','layout-fixture');")
                current = {"route": "initial", "state": mode}
                if args.gm_dashboard_only:
                    current["role"] = "general_manager"

                def request_handler(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = unquote(url.path)
                    if request.method != "GET":
                        report["requests"].append({"width": width, "state": mode, "route": current["route"], "method": request.method, "path": path, "result": "blocked_write"})
                        route.fulfill(status=403, json={"detail": "Layout fixture blocks all writes"})
                        return
                    if path.startswith("/api/"):
                        entry = {"width": width, "state": mode, "route": current["route"], "method": request.method, "path": path, "query": url.query}
                        report["requests"].append(entry)
                        if path == "/api/openclaw/events/stream":
                            entry["result"] = "fixture_sse"
                            route.fulfill(status=200, content_type="text/event-stream", body=": layout fixture\n\n")
                            return
                        value = fixture(path, parse_qs(url.query), mode)
                        if path == "/api/auth/me" and current.get("role") == "general_manager":
                            value = {**value, "business_role": "general_manager", "portal_user_id": 1, "capabilities": ["product", "hr", "engineering", "finance", "general_manager"]}
                        elif path == "/api/enterprise/business/product/tasks/":
                            value = {"tasks": []}
                        entry["result"] = "fixture" if value is not None else "unmapped_api"
                        if value is None:
                            report["errors"].append({**entry, "message": "API fixture is missing"})
                        route.fulfill(status=200 if value is not None else 404, json=value if value is not None else {"detail": "Unmapped fixture API"})
                    elif (url.scheme, url.netloc) == (origin.scheme, origin.netloc):
                        route.continue_()
                    else:
                        report["requests"].append({"width": width, "state": mode, "route": current["route"], "method": request.method, "url": request.url, "result": "blocked_external"})
                        route.abort()

                def websocket_handler(ws):
                    report["requests"].append({"width": width, "state": mode, "route": current["route"], "method": "WS", "url": ws.url, "result": "isolated_websocket"})
                    ws.on_message(lambda message: report["requests"].append({"width": width, "state": mode, "route": current["route"], "method": "WS_MESSAGE", "message": str(message), "result": "isolated_no_forward"}))

                context.route("**/*", request_handler)
                context.route_web_socket("**/*", websocket_handler)
                page = context.new_page()
                page.on("pageerror", lambda error: report["errors"].append({"width": width, "state": mode, "route": current["route"], "type": "pageerror", "message": str(error)}))
                page.on("console", lambda message: report["errors"].append({"width": width, "state": mode, "route": current["route"], "type": "console", "message": message.text}) if message.type == "error" else None)
                error_cursor = [len(report["errors"])]

                def check(label, expected_path=None, shell=True):
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(120)
                    measurement = page.evaluate(GEOMETRY)
                    errors = []
                    new_errors = report["errors"][error_cursor[0]:]
                    error_cursor[0] = len(report["errors"])
                    if new_errors:
                        errors.append("Browser/API errors occurred: " + "; ".join(item.get("message", "") for item in new_errors))
                    if expected_path and urlsplit(page.url).path != expected_path:
                        errors.append(f"Expected route {expected_path}; received {page.url}")
                    if shell:
                        if not measurement["main"] or not measurement["sidebar"] or not measurement["root"]:
                            errors.append("Expected shell/sidebar/page root is missing")
                        else:
                            if abs(measurement["sidebar"]["width"] - 224) > 1:
                                errors.append("Sidebar width is not 224px")
                            if abs(measurement["root"]["width"] - measurement["main"]["contentWidth"]) > 2:
                                errors.append("Page root does not fill main content width")
                            if measurement["main"]["scrollWidth"] > measurement["main"]["clientWidth"] + 2:
                                errors.append("Main has horizontal overflow")
                            if measurement["overflow"]:
                                errors.append("Descendant DOM has uncontained horizontal overflow")
                            if measurement["animations"]:
                                errors.append("Main has route animation")
                    if measurement["document"]["scrollWidth"] > measurement["document"]["width"] + 2:
                        errors.append("Document has horizontal overflow")
                    item = {"width": width, "state": mode, "route": current["route"], "role": current.get("role", "unassigned"), "label": label, "status": "FAIL" if errors else "PASS", "measurement": measurement}
                    report["checks"].append(item)
                    if errors:
                        screenshot = output / f"{len(report['checks']):03d}-{width}-{mode}-{re.sub(r'[^a-zA-Z0-9]+', '-', label).strip('-')}.png"
                        page.screenshot(path=str(screenshot), full_page=True)
                        report["failures"].append({**item, "reasons": errors, "screenshot": str(screenshot)})

                for route_path in args.routes:
                    current["route"] = route_path
                    try:
                        if route_path == "/api":
                            page.goto(args.url.rstrip("/") + "/settings")
                            page.locator('main a[href="/api"]').click()
                        else:
                            page.goto(args.url.rstrip("/") + route_path)
                        page.wait_for_selector("main h1", timeout=10000)
                        if args.gm_dashboard_only:
                            page.get_by_role("heading", name="总经理工作首页", exact=True).wait_for()
                        check("initial", route_path)
                        if route_path == "/api" and args.check_api_reload:
                            response = page.reload()
                            report["requests"].append({"width": width, "state": mode, "route": route_path, "method": "GET_DOCUMENT", "path": "/api", "status": response.status if response else None, "result": "api_hard_reload"})
                            if not response or response.status != 200 or "text/html" not in response.headers.get("content-type", ""):
                                raise AssertionError("/api hard reload did not return 200 HTML")
                            page.wait_for_selector("main h1", timeout=10000)
                            check("api-hard-reload", route_path)
                        if mode == "loaded" and route_path == "/sessions":
                            page.get_by_title("查看会话").first.click()
                            page.get_by_text("1 条消息", exact=False).wait_for()
                            check("session-detail", route_path)
                        if mode == "loaded" and route_path == "/agents/main":
                            page.get_by_role("button", name="查看", exact=True).click()
                            page.get_by_text("这是用于文件详情的只读测试正文。", exact=False).wait_for()
                            check("agent-file-detail", route_path)
                        if mode == "loaded" and route_path in ("/files", "/knowledge"):
                            page.get_by_text(LONG_NAME, exact=True).click()
                            page.get_by_text("布局文件预览正文。", exact=False).wait_for()
                            check("file-preview", route_path)
                        if mode == "loaded" and route_path == "/models":
                            page.get_by_role("button", name="添加提供商", exact=True).click()
                            modal = page.locator(".fixed.inset-0 > div").last
                            modal.wait_for()
                            modal_width = modal.bounding_box()["width"]
                            if modal_width > 550 or modal_width < 300:
                                raise AssertionError(f"Provider picker modal has unreasonable width {modal_width}")
                            check("provider-picker", route_path)
                    except Exception as error:
                        screenshot = output / f"exception-{width}-{mode}-{route_path.strip('/').replace('/', '-')}.png"
                        page.screenshot(path=str(screenshot), full_page=True)
                        report["failures"].append({"width": width, "state": mode, "route": route_path, "label": "exception", "reasons": [str(error)], "screenshot": str(screenshot)})

                if args.gm_dashboard_only:
                    context.close()
                    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"checked GM dashboard width={width} state={mode}", flush=True)
                    continue
                for source, target in (("/", "/dashboard"), ("/chat", "/dashboard"), ("/layout-fixture-not-found", "/dashboard")):
                    current["route"] = source
                    page.goto(args.url.rstrip("/") + source)
                    page.wait_for_selector("main h1")
                    check("redirect", target)
                current["route"] = "/login"
                page.goto(args.url.rstrip("/") + "/login")
                page.wait_for_selector(".login-card")
                check("login", "/login", shell=False)
                login_width = page.locator(".login-card").bounding_box()["width"]
                if not 300 <= login_width <= 560.5:
                    report["failures"].append({"width": width, "state": mode, "route": "/login", "reasons": [f"Login card width {login_width} outside expected range"]})

                # Verify real React Router links preserve the same document and sidebar element.
                current["route"] = "/settings -> /agents -> /settings"
                page.goto(args.url.rstrip("/") + "/settings")
                page.wait_for_selector("main h1")
                page.evaluate("window.__layoutDocumentMarker='fixture'; window.__layoutSidebar=document.querySelector('.enterprise-shell > aside')")
                page.locator('main a[href="/agents"]').click()
                page.wait_for_selector("main h1")
                check("spa-agents", "/agents")
                page.locator('aside a[href="/settings"]').click()
                page.wait_for_selector("main h1")
                check("spa-settings", "/settings")
                if not page.evaluate("window.__layoutDocumentMarker==='fixture' && window.__layoutSidebar===document.querySelector('.enterprise-shell > aside')"):
                    report["failures"].append({"width": width, "state": mode, "route": current["route"], "reasons": ["SPA navigation reloaded the document or replaced sidebar"]})
                current["role"] = "general_manager"
                current["route"] = "/dashboard (general_manager)"
                page.goto(args.url.rstrip("/") + "/dashboard")
                page.get_by_role("heading", name="总经理工作首页", exact=True).wait_for()
                check("manager-dashboard", "/dashboard")
                context.close()
                evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"checked width={width} state={mode} checks={len(report['checks'])} failures={len(report['failures'])} errors={len(report['errors'])}", flush=True)
        browser.close()

    report["status"] = "FAIL" if report["failures"] or report["errors"] else "PASS"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "failures": len(report["failures"]), "errors": len(report["errors"]), "evidence": str(evidence)}, ensure_ascii=False))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--output")
    parser.add_argument("--widths", nargs="+", type=int, default=[1280, 1440, 1920, 2450])
    parser.add_argument("--routes", nargs="+", default=ROUTES)
    parser.add_argument("--states", nargs="+", choices=["loaded", "empty"], default=["loaded", "empty"])
    parser.add_argument("--check-api-reload", action="store_true", help="Also verify /api hard reload after opening its React Router Link")
    parser.add_argument("--gm-dashboard-only", action="store_true", help="Only recheck the general manager dashboard fixture branch")
    raise SystemExit(run(parser.parse_args()))
