"""Run against Vite: python frontend/tests/finance-board-browser.py [base URL] [evidence dir].

All API calls are intercepted. This checks the real React page, not live ledger data.
"""
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:3080'
output = Path(sys.argv[2] if len(sys.argv) > 2 else 'output/finance-detail-browser')
output.mkdir(parents=True, exist_ok=True)
manager = dict(id='isolated-manager', username='隔离验收总经理', role='user',
               business_role='general_manager', department_code=None, portal_user_id=77,
               capabilities=['general_manager', 'product', 'engineering', 'hr'])


def board(source):
    fields = dict(project_id='项目编号', project_name='项目名称', client_name='业主单位',
                  contract_amount='合同金额', received_amount='已收金额', due_date='应收日期',
                  opening_receivable='年初应收', receivable_balance='应收结余',
                  owner='回款负责人', current_status='目前状态', notes='完整备注')
    fields.update({f'month_{i}': f'{i}月原始记录' for i in range(1, 13)})
    records = [dict(project_id=f'F{i}', project_name=f'隔离财务项目{i}', client_name='业主单位',
                    contract_amount='100.00', received_amount='20.00', due_date='',
                    opening_receivable='', receivable_balance='80.00', owner='负责人',
                    current_status='待核对', notes='仅隔离样例；完整备注必须可见。' * 30,
                    **{f'month_{m}': '原始记录；不推断年份和金额单位。' for m in range(1, 13)})
               for i in range(1, 41)]
    keys = ['contract', 'received', 'receivable', 'overdue']
    if source:
        keys = ['contract', 'opening_receivable', 'received', 'receivable', 'planned']
    return dict(department='finance', available=True, title='财务看板', snapshot_id='isolated',
                fields=fields, records=records, statuses=[], currency='CNY',
                metrics=[dict(key=key, label=key, value='100.00', unit='元') for key in keys],
                distribution=[dict(label='未结清', count=40)], total=40, filtered_count=40,
                scope='隔离只读样例', source=dict(name='隔离样例', as_of='2026-10-15',
                imported_at='', kind='department_published', revision=1, state='published'))


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        for source in (False, True):
            for width, height in ((1280, 800), (1920, 1080)):
                context = browser.new_context(viewport=dict(width=width, height=height), service_workers='block')
                context.add_init_script("localStorage.setItem('openclaw_access_token','isolated-finance-browser-token')")
                unexpected, errors, calls = [], [], []

                def route_api(route):
                    request = route.request
                    path = urlparse(request.url).path.replace('/api/enterprise/business/', '/api/')
                    calls.append(dict(path=path, method=request.method))
                    responses = {
                        '/api/auth/me': manager,
                        '/api/enterprise/status': dict(configured=True, linked=True, available=True, message='隔离验收'),
                        '/api/openclaw/ping': dict(message='ok'),
                        '/api/openclaw/container/info': dict(status='running'),
                        '/api/business/ledgers/permissions/': dict(departments=[]),
                        '/api/product/tasks/': dict(tasks=[]),
                        '/api/business/boards/finance/': board(source),
                    }
                    if path == '/api/openclaw/events/stream' and request.method == 'GET':
                        return route.fulfill(status=204)
                    if request.method != 'GET' or path not in responses:
                        unexpected.append(dict(path=path, method=request.method))
                        return route.fulfill(status=501, json=dict(detail='Unexpected isolated API request'))
                    route.fulfill(json=responses[path])

                context.route('**/api/**', route_api)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/departments/business/finance')
                page.wait_for_load_state('networkidle')
                expect(page.locator('.finance-records tbody tr')).to_have_count(40)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                aside_before = page.locator('.enterprise-shell > aside').bounding_box()
                main = page.locator('.enterprise-shell main')
                first = page.get_by_role('button', name='查看 隔离财务项目1 明细', exact=True)
                first.scroll_into_view_if_needed()
                assert first.bounding_box()['x'] + first.bounding_box()['width'] <= width
                scroll_before = main.evaluate('(element) => element.scrollTop')
                first.click()
                detail = page.get_by_role('dialog', name='项目完整明细')
                expect(detail).to_be_visible()
                assert detail.evaluate('(element) => element.matches(":modal")')
                box = detail.bounding_box()
                assert box['x'] >= 0 and box['y'] >= 0
                assert box['x'] + box['width'] <= width and box['y'] + box['height'] <= height
                expect(detail.get_by_role('heading', name='隔离财务项目1', exact=True)).to_be_visible()
                expect(detail.get_by_text('完整备注', exact=True)).to_be_visible()
                assert page.locator('.finance-records td').first.evaluate('(el) => getComputedStyle(el).fontSize') == '15px'
                assert detail.locator('dd').first.evaluate('(el) => getComputedStyle(el).fontSize') == '16px'
                detail.evaluate('(element) => element.scrollTop = element.scrollHeight')
                expect(detail.get_by_role('button', name='关闭明细')).to_be_in_viewport()
                page.screenshot(path=str(output / f'detail-{source}-{width}.png'))
                page.keyboard.press('Escape')
                expect(detail).to_have_count(0)
                expect(first).to_be_focused()
                assert main.evaluate('(element) => element.scrollTop') == scroll_before
                first.click()
                detail.get_by_role('button', name='关闭明细').click()
                expect(detail).to_have_count(0)
                last = page.get_by_role('button', name='查看 隔离财务项目40 明细', exact=True)
                last.click()
                expect(detail.get_by_role('heading', name='隔离财务项目40', exact=True)).to_be_visible()
                detail.get_by_role('button', name='关闭明细').click()
                assert page.locator('.enterprise-shell > aside').bounding_box() == aside_before
                assert not unexpected, unexpected
                assert not errors, errors
                results.append(dict(source=source, viewport=[width, height], dialog_bounds=box,
                                    api_calls=calls, checks='first/last row; modal in viewport; long detail scroll; close/Escape/reopen; focus; fixed sidebar; 15/16px text'))
                context.close()
    finally:
        browser.close()

(output / 'results.json').write_text(json.dumps(dict(scope='Isolated API fixtures only; no live ledger writes or data verification', results=results), ensure_ascii=False, indent=2), encoding='utf-8')
print(f'PASS: {len(results)} desktop/mode combinations; evidence: {output.resolve()}')
