"""Real React + production JWT/portal proxy + Django/CSRF, isolated SQLite only.

Run .runtime/python/Scripts/python.exe frontend/tests/baichuan-browser.py [Vite URL].
Start Vite separately on 55173. No live business data or accounts are touched.
Only unrelated OpenClaw service indicators and external example.com are stubbed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/business/.runtime/main-acceptance-venv/Lib/site-packages"))
sys.path.insert(0, str(ROOT / "services/business/backend"))
sys.path.insert(0, str(ROOT / "platform"))
sys.path.insert(0, str(ROOT / "platform/tests"))
RUNTIME = Path(tempfile.mkdtemp(prefix="baichuan-browser-", dir=ROOT / ".runtime"))
OUTPUT = Path(os.environ.get("BAICHUAN_BROWSER_OUTPUT", str(ROOT / "doc/baichuan-sdd/evidence/browser")))
OUTPUT.mkdir(parents=True, exist_ok=True)
for key in list(os.environ):
    if key.startswith("PORTAL_DB_"):
        del os.environ[key]
os.environ.update(PORTAL_SECRET_KEY="isolated-baichuan-browser-key-at-least-forty-characters",
                  PORTAL_DEBUG="1", PORTAL_HTTPS="0", PORTAL_SQLITE_PATH=str(RUNTIME / "portal.sqlite3"),
                  PORTAL_ALLOWED_HOSTS="baichuan-isolated.test,testserver,127.0.0.1,localhost",
                  PORTAL_CSRF_TRUSTED_ORIGINS="http://baichuan-isolated.test",
                  DJANGO_SETTINGS_MODULE="config.settings")

import django
django.setup()
from django.conf import settings as portal_settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from portal.models import Module, Role, User as PortalUser
from portal.baichuan_models import Company
from portal.baichuan_service import COMPANY_FIELDS

call_command("migrate", interactive=False, verbosity=0)
call_command("seed_portal", verbosity=0)
Module.objects.update(status="verified")
PASSWORD = "Isolated!Baichuan4279"
portal_users = {}
for name, role in (("M", "general_manager"), ("P", "product"), ("R", "product"), ("O", "product")):
    user = PortalUser.objects.create_user(username="baichuan-test-" + name, password=PASSWORD,
                                         must_change_password=False,
                                         department_code="product" if role == "product" else "")
    user.roles.add(Role.objects.get(code=role))
    portal_users[name] = user
portal_settings.PORTAL_BAICHUAN_SCOPE_CONFIRMED = True
portal_settings.PORTAL_BAICHUAN_READ_USER_IDS = [portal_users[name].pk for name in ("M", "P", "R")]
portal_settings.PORTAL_BAICHUAN_WRITE_USER_IDS = [portal_users[name].pk for name in ("M", "P")]

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.wsgi import WSGIMiddleware
from app.auth.service import hash_password
from app.config import settings as platform_settings
from app.db.engine import get_db
from app.db.models import Base, User
from app.routes import auth, enterprise
from test_business_bridge import AsyncSQLite
from playwright.sync_api import sync_playwright, expect

platform_settings.jwt_secret = "isolated-baichuan-browser-jwt-secret-32-characters"
platform_settings.portal_base_url = "http://baichuan-isolated.test"
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as db:
    db.add_all([User(id=name, username="browser-" + name, email=name + "@isolated.invalid",
                     password_hash=hash_password(PASSWORD)) for name in portal_users])
    db.commit()

class BrowserSQLite(AsyncSQLite):
    def add(self, row):
        self.session.add(row)

async def isolated_db():
    with Session(engine, expire_on_commit=False) as db:
        yield BrowserSQLite(db)

portal_wsgi = WSGIMiddleware(get_wsgi_application())
def isolated_portal_client(cookies=None):
    return httpx.AsyncClient(base_url=platform_settings.portal_base_url, cookies=cookies,
                             transport=httpx.ASGITransport(app=portal_wsgi), follow_redirects=False)

enterprise.portal_client = isolated_portal_client
app = FastAPI()
app.include_router(auth.router)
app.include_router(enterprise.router)
app.dependency_overrides[get_db] = isolated_db
client = TestClient(app)
tokens = {}
for name, user in portal_users.items():
    response = client.post("/api/auth/login", json={"username": "browser-" + name, "password": PASSWORD})
    assert response.status_code == 200, response.text
    tokens[name] = response.json()["access_token"]
    response = client.post("/api/enterprise/link", headers={"Authorization": "Bearer " + tokens[name]},
                           json={"username": user.username, "password": PASSWORD})
    assert response.status_code == 200, response.text

API = "/api/enterprise/business/product/baichuan/companies/"
def request(method, path=API, body=None, who="M"):
    return client.request(method, path, headers={"Authorization": "Bearer " + tokens[who]}, json=body)

def payload(name, qualifications=(), **fields):
    company = dict.fromkeys(COMPANY_FIELDS)
    company.update(name=name, source="隔离浏览器验收夹具", province="陕西省", city="西安市", **fields)
    return dict(company=company,
                qualifications=[dict(category=category, status=status, grade=grade)
                                for category, grade, status in qualifications], people=[])

fixtures = {
    "A": [("electronic", "1", "PRESENT"), ("cmmi", "3", "PRESENT"), ("itss", "2", "PRESENT")],
    "B": [("electronic", "2", "PRESENT"), ("cmmi", "5", "PRESENT"), ("itss", "3", "PRESENT"), ("labor", None, "PRESENT")],
    "C": [("electronic", "1", "PRESENT"), ("cmmi", None, "PRESENT"), ("labor", None, "ABSENT")],
    "D": [("electronic", None, "ABSENT")],
    "E": [("electronic", "1", "PRESENT"), ("electronic", "2", "PRESENT"), ("cmmi", "3", "PRESENT")],
    "F": [("electronic", "1", "PRESENT"), ("ccrc", "2", "PRESENT")],
    "G": [("electronic", None, "UNKNOWN")],
}
ids = {}
for letter, qualifications in fixtures.items():
    body = payload("样例" + letter, qualifications, website="https://example.com/" if letter == "E" else None,
                   contact_name="测试联系人" if letter == "A" else None,
                   contact_phone="+86 029 00123456" if letter == "A" else None)
    if letter == "D":
        body["people"] = [dict(name="隔离人员", credentials="电子与智能化一级", source="隔离夹具")]
    response = request("POST", body=body)
    assert response.status_code == 201, response.text
    ids[letter] = response.json()["company"]["id"]

results, calls, unexpected, errors = [], [], [], []
faults = {"write": False, "list": False, "hold": False, "network": False}
held = []
external = []
def record(name, **detail):
    results.append(dict(check=name, result="PASS", **detail))

def run_browser():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:55173"
    for who in ("M", "P", "R"):
        response = request("GET", who=who)
        assert response.status_code == 200 and response.json()["total"] == 7
    assert request("GET", who="O").status_code == 403
    assert request("POST", body=payload("拒绝写入"), who="R").status_code == 403
    assert client.get(API).status_code in (401, 403)
    record("AC-01/02 isolated identities and actual JWT/CSRF proxy", company_ids=list(ids.values()))

    def route_all(route):
        req = route.request
        parsed = urlsplit(req.url)
        if parsed.netloc != urlsplit(base).netloc:
            if parsed.hostname == "example.com":
                external.append(req.url)
                return route.fulfill(content_type="text/html", body="<title>Isolated external navigation</title>")
            unexpected.append(req.url)
            return route.abort()
        if not parsed.path.startswith("/api/"):
            return route.continue_()
        if parsed.path.startswith("/api/openclaw/"):
            if "events/stream" in parsed.path:
                return route.fulfill(status=204)
            return route.fulfill(json={"message": "ok", "status": "running"})
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        if faults["network"] and parsed.path.endswith("/baichuan/companies/"):
            return route.abort("internetdisconnected")
        if faults["write"] and req.method in ("POST", "PUT") and "/baichuan/" in path:
            faults["write"] = False
            calls.append(dict(method=req.method, path=path, status=503, injected=True))
            return route.fulfill(status=503, json={"detail": "隔离注入：保存服务暂时不可用"})
        if faults["list"] and req.method == "GET" and parsed.path.endswith("/baichuan/companies/"):
            return route.fulfill(status=503, json={"detail": "隔离注入：查询服务暂时不可用"})
        response = client.request(req.method, path, content=req.post_data_buffer,
                                  headers={key: value for key, value in req.headers.items()
                                           if key in ("authorization", "content-type", "accept")})
        calls.append(dict(method=req.method, path=path, status=response.status_code))
        if faults["hold"] and parsed.path.endswith("/baichuan/companies/"):
            faults["hold"] = False
            held.append((route, response))
            return
        route.fulfill(status=response.status_code, body=response.content,
                      content_type=response.headers.get("content-type", "application/json"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            def new_page(who="M", width=1440, height=900):
                context = browser.new_context(viewport=dict(width=width, height=height), service_workers="block")
                context.add_init_script("localStorage.setItem('openclaw_access_token'," + json.dumps(tokens[who]) + ")")
                context.route("**/*", route_all)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                return context, page

            def rows(page, letters):
                expect(page.locator(".bc-company-name")).to_have_text(["样例" + letter for letter in letters])

            def menu(page, index):
                page.locator(".bc-filter").nth(index).locator("button").click()
                return page.locator(".bc-filter-menu")

            context, page = new_page()
            page.goto(base + "/departments/product/baichuan")
            page.wait_for_load_state("networkidle")
            rows(page, "ABCDEFG")
            assert not external, external
            expect(page.get_by_role("button", name="新增公司", exact=True)).to_be_visible()
            expect(page.get_by_text("导入 Excel", exact=True)).to_have_count(0)
            assert page.locator(".bc-filter").count() == 7
            for index, count in enumerate((4, 2, 7, 5, 5, 6, 5)):
                panel = menu(page, index)
                expect(panel.get_by_role("checkbox")).to_have_count(count)
                bounds = panel.bounding_box()
                assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 1440
                assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 900
                page.get_by_role("heading", name="百川阁", exact=True).click()
                expect(page.locator(".bc-filter-menu")).to_have_count(0)
            for width, height in ((1440, 900), (1920, 1080)):
                page.set_viewport_size(dict(width=width, height=height))
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                aside = page.locator(".enterprise-shell > aside")
                top = page.locator(".enterprise-shell > div > header")
                before = [aside.bounding_box(), top.bounding_box()]
                pane = page.locator(".wb-work-content")
                pane.evaluate("el => el.scrollTop = el.scrollHeight")
                assert [aside.bounding_box(), top.bounding_box()] == before
                pane.evaluate("el => el.scrollTop = 0")
                page.screenshot(path=str(OUTPUT / f"manager-list-{width}.png"))
                record("AC-19 manager layout and fixed shell", viewport=[width, height], shell=before)
            page.set_viewport_size(dict(width=1440, height=900))
            panel = menu(page, 0)
            panel.get_by_role("checkbox", name="二级", exact=True).check()
            rows(page, "BE")
            panel.get_by_role("checkbox", name="一级", exact=True).check()
            rows(page, "ABCEF")
            page.screenshot(path=str(OUTPUT / "multi-grade.png"))
            page.keyboard.press("Escape")
            expect(page.locator(".bc-filter-menu")).to_have_count(0)
            expect(page.locator(".bc-filter").nth(0).locator("button")).to_be_focused()
            panel = menu(page, 3)
            panel.get_by_role("checkbox", name="三级", exact=True).check()
            rows(page, "AE")
            page.get_by_role("heading", name="百川阁", exact=True).click()
            panel = menu(page, 5)
            panel.get_by_role("checkbox", name="二级", exact=True).check()
            rows(page, "A")
            record("AC-04/05/06 exact multi-grade OR and cross-category AND")
            page.keyboard.press("Escape")
            page.get_by_role("button", name="重置", exact=True).click()
            rows(page, "ABCDEFG")
            panel = menu(page, 0)
            panel.get_by_role("checkbox", name="一级", exact=True).check()
            panel.get_by_role("checkbox", name="具备即可", exact=True).check()
            expect(panel.get_by_role("checkbox", name="一级", exact=True)).not_to_be_checked()
            rows(page, "ABCEF")
            panel.get_by_role("checkbox", name="二级", exact=True).check()
            expect(panel.get_by_role("checkbox", name="具备即可", exact=True)).not_to_be_checked()
            rows(page, "BE")
            panel.get_by_role("checkbox", name="二级", exact=True).uncheck()
            rows(page, "ABCDEFG")
            page.keyboard.press("Escape")
            panel = menu(page, 1)
            expect(panel.get_by_role("checkbox")).to_have_count(2)
            panel.get_by_role("checkbox", name="具备即可", exact=True).check()
            rows(page, "B")
            page.keyboard.press("Escape")
            page.get_by_role("button", name="重置", exact=True).click()
            record("AC-07 unrestricted, any/grades mutual exclusion and labor no grades")

            page.goto(base + "/departments/product/baichuan?electronic=1&page_size=2&page=2")
            rows(page, "EF")
            page.set_viewport_size(dict(width=1440, height=580))
            pane = page.locator(".wb-work-content")
            pane.evaluate("el => el.scrollTop = el.scrollHeight")
            page.get_by_role("button", name="样例E", exact=True).scroll_into_view_if_needed()
            scroll_before = pane.evaluate("el => el.scrollTop")
            assert scroll_before > 0
            page.get_by_role("button", name="样例E", exact=True).click()
            expect(page.get_by_role("heading", name="样例E", exact=True)).to_be_visible()
            expect(page.locator(".bc-detail-record")).to_have_count(3)
            expect(page.get_by_text("命中筛选", exact=True)).to_have_count(1)
            website = page.get_by_role("link", name="访问企业官网")
            assert website.get_attribute("target") == "_blank" and "noopener" in website.get_attribute("rel")
            assert not external
            with page.expect_popup() as popup:
                website.click()
            popup.value.wait_for_load_state()
            assert popup.value.url == "https://example.com/"
            popup.value.close()
            page.screenshot(path=str(OUTPUT / "detail.png"))
            page.get_by_role("button", name="返回公司列表", exact=True).click()
            rows(page, "EF")
            expect(pane).to_have_js_property("scrollTop", scroll_before)
            assert "page=2" in page.url and "electronic=1" in page.url
            page.get_by_role("button", name="样例E", exact=True).click()
            expect(page.get_by_role("heading", name="样例E", exact=True)).to_be_visible()
            page.go_back()
            rows(page, "EF")
            expect(pane).to_have_js_property("scrollTop", scroll_before)
            page.reload()
            rows(page, "EF")
            record("AC-11/12 full detail, match marker, both returns and refresh restoration, new-tab website", scroll=scroll_before)

            page.set_viewport_size(dict(width=1440, height=900))
            page.get_by_role("button", name="样例E", exact=True).click()
            page.get_by_role("button", name="编辑资料", exact=True).click()
            editor = page.get_by_role("dialog")
            expect(editor).to_be_visible()
            editor.locator("input[name=name]").fill("样例E 本地未保存")
            editor.locator("input[name=credit_code]").fill("BAD")
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(editor.locator("#bc-error-credit_code")).to_contain_text("18位")
            expect(editor.locator("input[name=credit_code]")).to_be_focused()
            expect(editor.locator("input[name=name]")).to_have_value("样例E 本地未保存")
            editor.locator("input[name=credit_code]").fill("")
            editor.locator("input[name=phone]").fill("0" * 101)
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(editor.get_by_role("alert")).to_contain_text("100")
            expect(editor.locator("input[name=phone]")).to_be_focused()
            expect(editor.locator("input[name=phone]")).to_have_value("0" * 101)
            editor.locator("input[name=phone]").fill("")
            faults["write"] = True
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(editor.get_by_role("alert")).to_contain_text("保存服务暂时不可用")
            expect(editor.locator("input[name=name]")).to_have_value("样例E 本地未保存")
            page.screenshot(path=str(OUTPUT / "save-failure-preserved.png"))
            editor.get_by_role("alert").scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT / "save-failure-alert.png"))
            latest = request("GET", API + ids["E"] + "/").json()
            change = dict(company={field: latest["company"][field] for field in COMPANY_FIELDS},
                          qualifications=latest["qualifications"], people=latest["people"],
                          expected_version=latest["company"]["version"])
            change["company"]["description"] = "另一会话已保存的资料"
            assert request("PUT", API + ids["E"] + "/", change).status_code == 200
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(editor.get_by_role("alert")).to_contain_text("其他人修改")
            expect(editor.locator("input[name=name]")).to_have_value("样例E 本地未保存")
            assert request("GET", API + ids["E"] + "/").json()["company"]["name"] == "样例E"
            page.screenshot(path=str(OUTPUT / "version-conflict.png"))
            editor.get_by_role("alert").scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT / "version-conflict-alert.png"))
            page.once("dialog", lambda dialog: dialog.dismiss())
            editor.get_by_role("button", name="取消", exact=True).click()
            expect(editor).to_be_visible()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.go_back()
            expect(editor).to_be_visible()
            expect(editor.locator("input[name=name]")).to_have_value("样例E 本地未保存")
            page.once("dialog", lambda dialog: dialog.accept())
            editor.get_by_role("button", name="取消", exact=True).click()
            expect(page.get_by_role("dialog")).to_have_count(0)
            record("AC-15/16/18 real validation400 and version409, injected503, close/back cancel preserve all draft")

            page.goto(base + "/departments/product/baichuan?electronic=1")
            rows(page, "ACEF")
            page.get_by_role("button", name="样例A", exact=True).click()
            page.get_by_role("button", name="编辑资料", exact=True).click()
            editor = page.get_by_role("dialog")
            page.once("dialog", lambda dialog: dialog.accept())
            editor.locator(".bc-qualification-editor").first.get_by_role("button", name="移除此条资质").click()
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            rows(page, "CEF")
            expect(page.get_by_role("status").filter(has_text="已不符合当前")).to_be_visible()
            record("AC-17 successful edit removes nonmatching company and explains why")

            page.get_by_role("button", name="重置", exact=True).click()
            rows(page, "ABCDEFG")
            faults["hold"] = True
            search = page.get_by_role("textbox", name="搜索公司名称")
            search.fill("样例B")
            search.press("Enter")
            expect(page.get_by_text("正在读取公司列表…", exact=True)).to_be_visible()
            deadline = monotonic() + 5
            while not held and monotonic() < deadline:
                page.wait_for_timeout(25)
            assert held
            search.fill("样例F")
            search.press("Enter")
            rows(page, "F")
            stale_route, stale_response = held.pop()
            stale_route.fulfill(status=stale_response.status_code, body=stale_response.content, content_type="application/json")
            rows(page, "F")
            page.screenshot(path=str(OUTPUT / "query-race.png"))
            record("AC-10 older query finishing last cannot replace latest results")
            faults["list"] = True
            page.get_by_role("button", name="重置", exact=True).click()
            expect(page.locator(".bc").get_by_role("alert")).to_contain_text("查询服务暂时不可用")
            expect(page.get_by_text("企业库暂无资料", exact=True)).to_have_count(0)
            faults["list"] = False
            page.get_by_role("button", name="重新查询", exact=True).click()
            rows(page, "ABCDEFG")
            search.fill("不存在的公司")
            search.press("Enter")
            expect(page.get_by_text("没有符合条件的公司", exact=True)).to_be_visible()
            record("AC-18 loading, query failure/retry and no matches remain distinct")
            context.close()

            for who in ("P", "R", "O"):
                context, page = new_page(who)
                page.goto(base + "/departments/product/baichuan")
                page.wait_for_load_state("networkidle")
                if who == "O":
                    expect(page.locator(".bc").get_by_role("alert")).to_contain_text("访问权限")
                    expect(page.locator(".bc-company-name")).to_have_count(0)
                else:
                    rows(page, "ABCDEFG")
                    expect(page.get_by_role("button", name="新增公司", exact=True)).to_have_count(1 if who == "P" else 0)
                    if who == "P":
                        for width, height in ((1440, 900), (1920, 1080)):
                            page.set_viewport_size(dict(width=width, height=height))
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                            sidebar = page.locator("#product-workspace-navigation")
                            top = page.locator(".wb-toolbar")
                            before = [sidebar.bounding_box(), top.bounding_box()]
                            pane = page.locator(".wb-work-content")
                            pane.evaluate("el => el.scrollTop = el.scrollHeight")
                            assert [sidebar.bounding_box(), top.bounding_box()] == before
                            pane.evaluate("el => el.scrollTop = 0")
                            page.screenshot(path=str(OUTPUT / f"product-list-{width}.png"))
                            record("AC-01/19 product original shell and shared resource", viewport=[width, height])
                context.close()

            context, page = new_page()
            page.goto(base + "/departments/product/baichuan")
            page.wait_for_load_state("networkidle")
            first_filter = page.locator(".bc-filter-button").first
            first_filter.focus()
            first_filter.press("ArrowDown")
            expect(page.locator(".bc-filter-menu").get_by_role("checkbox", name="不限", exact=True)).to_be_focused()
            page.keyboard.press("Tab")
            page.keyboard.press("Space")
            expect(page.locator(".bc-filter-menu").get_by_role("checkbox", name="具备即可", exact=True)).to_be_checked()
            page.keyboard.press("Escape")
            page.get_by_role("button", name="重置", exact=True).click()
            page.get_by_role("button", name="新增公司", exact=True).click()
            editor = page.get_by_role("dialog")
            editor.locator("input[name=name]").fill("浏览器新增隔离公司")
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(page.get_by_role("heading", name="浏览器新增隔离公司", exact=True)).to_be_visible()
            new_id = urlsplit(page.url).query.split("company=")[-1].split("&")[0]
            new_data = request("GET", API + new_id + "/").json()
            assert new_data["company"]["version"] == 1 and new_data["qualifications"] == [] and new_data["people"] == []
            page.get_by_role("button", name="编辑资料", exact=True).click()
            editor = page.get_by_role("dialog")
            editor.locator("input[name=phone]").fill("010001234")
            section = editor.locator(".bc-qualification-editor").first
            for grade in ("1", "2"):
                section.get_by_role("button", name="添加记录", exact=True).click()
                row = section.locator(".bc-subrecord").last
                row.get_by_label("具备状态").select_option("PRESENT")
                row.get_by_label("精确等级").select_option(grade)
            editor.get_by_role("button", name="添加人员", exact=True).click()
            person = editor.locator("fieldset").last.locator(".bc-subrecord")
            person.get_by_label("姓名", exact=False).fill("隔离测试员工")
            person.get_by_label("职称认证", exact=True).fill("个人认证，仅依据录入资料")
            person.get_by_label("核实日期", exact=True).fill("2026-10-16")
            person.get_by_label("核实日期", exact=True).fill("")
            editor.get_by_role("button", name="保存公司资料", exact=True).click()
            expect(page.get_by_role("heading", name="隔离测试员工", exact=True)).to_be_visible()
            new_data = request("GET", API + new_id + "/").json()
            assert new_data["company"]["phone"] == "010001234"
            assert sorted(item["grade"] for item in new_data["qualifications"]) == ["1", "2"]
            assert new_data["people"][0]["verified_on"] is None
            page.screenshot(path=str(OUTPUT / "created-company-team.png"))
            record("AC-14/15/19 actual minimal create, multi-certificate/person edit, nullable date, keyboard choice")
            for kind, label, action in (("corporate", "企业独立官网", "访问企业官网"), ("group_profile", "集团专属介绍页", "访问官方主页"), ("official_wechat", "官方公众号", "访问官方主页")):
                page.get_by_role("button", name="编辑资料", exact=True).click()
                editor = page.get_by_role("dialog")
                editor.locator("input[name=website]").fill("https://example.com/" + kind)
                editor.get_by_label("官方主页类型", exact=False).select_option(kind)
                faults["write"] = True
                editor.get_by_role("button", name="保存公司资料", exact=True).click()
                expect(editor.locator("select[name=website_kind]")).to_have_value(kind)
                expect(editor.locator("input[name=website]")).to_have_value("https://example.com/" + kind)
                editor.get_by_role("button", name="保存公司资料", exact=True).click()
                expect(editor).to_have_count(0)
                panel = page.get_by_role("complementary", name=label, exact=True)
                expect(panel).to_be_visible()
                assert panel.get_by_role("link", name=action, exact=True).get_attribute("target") == "_blank"
                with page.expect_popup() as popup_info:
                    panel.get_by_role("link", name=action, exact=True).click()
                popup_info.value.wait_for_url("https://example.com/" + kind)
                popup_info.value.close()
                stored = request("GET", API + new_id + "/").json()
                assert stored["company"]["website_kind"] == kind
                page.screenshot(path=str(OUTPUT / ("homepage-" + kind + ".png")))
            record("AC-32 three homepage types, explicit labels, retained failed draft and new-tab action")
            page.goto(base + "/departments/product/baichuan?page=999&page_size=2")
            expect(page.get_by_text("该页暂无公司", exact=True)).to_be_visible()
            expect(page.locator(".bc-company-name")).to_have_count(0)
            page.goto(base + "/departments/product/baichuan?company=00000000-0000-0000-0000-000000000001")
            expect(page.locator(".bc").get_by_role("alert")).to_contain_text("不存在")
            page.goto(base + "/departments/product/baichuan")
            expect(page.locator(".bc-company-name")).to_have_count(8)
            faults["network"] = True
            page.get_by_role("button", name="重置", exact=True).click()
            # Same URL reset may be a no-op; force a new query while disconnected.
            page.get_by_role("textbox", name="搜索公司名称").fill("网络异常")
            page.get_by_role("textbox", name="搜索公司名称").press("Enter")
            expect(page.locator(".bc").get_by_role("alert")).to_be_visible()
            expect(page.get_by_text("没有符合条件的公司", exact=True)).to_have_count(0)
            faults["network"] = False
            page.get_by_role("button", name="重置", exact=True).click()
            expect(page.locator(".bc-company-name")).to_have_count(8)
            def clear_isolated_companies():
                from django.db import close_old_connections
                close_old_connections()
                assert str(portal_settings.DATABASES["default"]["NAME"]) == str(RUNTIME / "portal.sqlite3")
                Company.objects.all().delete()
                close_old_connections()
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(clear_isolated_companies).result()
            page.reload()
            expect(page.get_by_text("企业库暂无资料", exact=True)).to_be_visible()
            record("AC-09/18 beyond last page, actual detail404, network interruption/recovery, empty isolated library")
            page.screenshot(path=str(OUTPUT / "empty-library.png"))
            context.close()
            assert not unexpected, unexpected
            assert not errors, errors
        finally:
            browser.close()
    print(f"PASS: {len(results)} browser/integration checks; screenshots: {OUTPUT}")

if __name__ == "__main__":
    overall = "FAIL"
    try:
        run_browser()
        overall = "PASS"
    finally:
        (OUTPUT / "results.json").write_text(json.dumps(dict(
            scope="isolated React + actual JWT/enterprise proxy + Django WSGI/CSRF/SQLite; no real account grants",
            overall=overall, executed_at=datetime.now(timezone.utc).isoformat(),
            runtime=str(RUNTIME), results=results, calls=calls, unexpected=unexpected, page_errors=errors,
        ), ensure_ascii=False, indent=2), encoding="utf-8")
        client.close()
        engine.dispose()
