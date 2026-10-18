"""Verify restored source-table UI using real local HTTP/Edge, with no AI calls.

Requires a committed source-status receipt and explicitly labelled deterministic
fixtures from verify_source_snapshots.py. This is structured matching/export UI
verification, never evidence of natural-language extraction or online research.
No business records, credentials, grants or existing conversations are replaced.
"""
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
import uuid
import xml.etree.ElementTree as ET
import zipfile

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime/baichuan-ai-local'
BASE = 'http://127.0.0.1:13180'
PAGE = BASE + '/departments/product/baichuan'
API = BASE + '/api/enterprise/business/product/baichuan/'
LABEL = '本地源表资料，历史官网补查未恢复'
SHORT = {'electronic': '电子与智能化', 'labor': '施工劳务', 'cs': 'CS', 'cmmi': 'CMMI',
         'ccrc': 'CCRC', 'itss': 'ITSS', 'security': '安防工程'}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def owned_source():
    spec = importlib.util.spec_from_file_location('source_local', ROOT / 'scripts/baichuan/local_dev.py')
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    local.environment()  # Checks ownership and the fixed database location.
    state = local.source_state()
    if not state['source_connected'] or not state['local_source_only'] or state['dataset_kind'] != 'isolation':
        raise ValueError('A successful local source import receipt is required first')
    return state


def model_log_count():
    with sqlite3.connect((RUNTIME / 'portal.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.execute('PRAGMA query_only=ON')
        return conn.execute('SELECT COUNT(*) FROM portal_modelcalllog').fetchone()[0]


def api(client, headers, suffix, **kwargs):
    response = client.request(kwargs.pop('method', 'GET'), API + suffix, headers=headers, **kwargs)
    response.raise_for_status()
    return response.json()


def all_companies(client, headers, selection=None):
    items, page = [], 1
    while True:
        value = api(client, headers, 'companies/?' + urlencode({**(selection or {}), 'page': page, 'page_size': 100}))
        items.extend(value['items'])
        if not value['has_more']:
            assert len(items) == value['total']
            return items
        page += 1


def matching_ids(rows, selection):
    return {row['id'] for row in rows if all(any(
        q['category'] == category and q['status'] == 'PRESENT'
        and (grades == 'any' or q.get('grade') in grades.split(','))
        for q in row['qualifications']) for category, grades in selection.items())}


def choose_combination(rows):
    for row in rows:
        present = {q['category']: q.get('grade') or 'any' for q in row['qualifications'] if q['status'] == 'PRESENT'}
        if len(present) >= 2:
            categories = list(present)[:2]
            selection = {category: present[category] for category in categories}
            return selection
    raise ValueError('No source record has two parsed present categories; combination verification needs review')


def workbook_rows(content):
    """Read export row counts/statuses without rendering personal values to stdout."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        sheets = {}
        for sheet in workbook.find('s:sheets', NS):
            rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target = targets[rid]
            name = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            root = ET.fromstring(archive.read(name))
            rows = []
            for row in root.findall('s:sheetData/s:row', NS):
                if int(row.attrib['r']) <= 7:
                    continue
                cells = []
                for cell in row.findall('s:c', NS):
                    if cell.attrib.get('t') == 's':
                        cells.append(shared[int(cell.find('s:v', NS).text)])
                    else:
                        cells.append(''.join(cell.itertext()))
                rows.append(cells)
            sheets[sheet.attrib['name']] = rows
        return sheets


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    state = owned_source()
    fixture = json.loads((RUNTIME / 'source-browser-fixtures.json').read_text(encoding='utf-8'))
    if fixture.get('validation_label') != '源表确定规则验收' or fixture.get('validation_ready') is not True:
        raise ValueError('Explicit deterministic verification fixtures are required')
    accounts = json.loads((RUNTIME / 'accounts.json').read_text(encoding='utf-8'))['accounts']
    actors = {item['role']: item for item in fixture['actors']}
    output = RUNTIME / 'source-browser-verification'
    output.mkdir(exist_ok=True)
    before = model_log_count()
    results = []
    with httpx.Client(timeout=30) as client, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless=True)
        try:
            for index, account in enumerate(accounts):
                actor = actors[account['role']]
                for key in ['conversation_id', 'snapshot_id', 'export_id', 'default_export_id']:
                    uuid.UUID(actor[key])
                login = client.post(BASE + '/api/auth/login', json={'username': account['username'], 'password': account['password']})
                login.raise_for_status()
                tokens = login.json()
                headers = {'Authorization': 'Bearer ' + tokens['access_token']}
                client.post(BASE + '/api/enterprise/link', headers=headers,
                            json={'username': account['username'], 'password': account['password']}).raise_for_status()
                me = client.get(BASE + '/api/auth/me', headers=headers)
                me.raise_for_status()
                owner_id = me.json()['id']
                config = api(client, headers, 'assistant/config/')
                assert config['environment_label'] == LABEL
                rows = all_companies(client, headers)
                assert len(rows) == state['imported_company_count'] and len(rows) > 0
                selection = choose_combination(rows)
                selected = all_companies(client, headers, selection)
                assert {row['id'] for row in selected} == matching_ids(rows, selection)
                # Exact grades remain exact; grades within a category form an OR.
                electronic = all_companies(client, headers, {'electronic': '2'})
                assert {row['id'] for row in electronic} == matching_ids(rows, {'electronic': '2'})
                either = all_companies(client, headers, {'electronic': '1,2'})
                assert {row['id'] for row in either} == matching_ids(rows, {'electronic': '1,2'})
                chosen = selected[0]
                detail = api(client, headers, 'companies/' + quote(chosen['id'], safe='') + '/')
                assert detail['company']['source'] and detail['company'].get('verified_on') is None
                snapshot = api(client, headers, 'assistant/results/' + actor['snapshot_id'] + '/')
                assert snapshot['counts']['candidate'] > 0 and snapshot['counts']['confirmed'] == 0
                assert all(item['status'] != 'confirmed' for item in snapshot['results'])
                downloads = {}
                for key in ['export_id', 'default_export_id']:
                    response = client.get(API + 'assistant/exports/' + actor[key] + '/download/', headers=headers)
                    response.raise_for_status()
                    downloads[key] = response.content
                candidate_book = workbook_rows(downloads['export_id'])
                default_book = workbook_rows(downloads['default_export_id'])
                assert not candidate_book['企业结果'] and candidate_book['待核实信息']
                assert not default_book['企业结果'] and not default_book['待核实信息']
                assert all('待核实候选' in row for row in candidate_book['待核实信息'])
                context = browser.new_context(viewport={'width': 1440 if index == 0 else 1920, 'height': 1000}, reduced_motion='reduce', accept_downloads=True)
                blocked, errors = [], []

                def guard(route):
                    parsed = urlsplit(route.request.url)
                    if parsed.scheme in {'data', 'blob'} or (parsed.scheme in {'http', 'https', 'ws', 'wss'} and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}):
                        route.continue_()
                    else:
                        blocked.append(parsed.hostname or parsed.scheme)
                        route.abort()
                context.route('**/*', guard)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(BASE + '/login')
                storage_key = 'baichuan-assistant:v1:' + quote(BASE, safe='') + ':' + quote(str(owner_id), safe='') + ':' + str(actor['actor_id'])
                page.evaluate('data => { localStorage.setItem("openclaw_access_token",data.tokens.access_token); localStorage.setItem("openclaw_refresh_token",data.tokens.refresh_token); localStorage.setItem(data.key,data.cid) }',
                              {'tokens': tokens, 'key': storage_key, 'cid': actor['conversation_id']})
                page.goto(PAGE + '?' + urlencode(selection))
                expect(page.locator('#baichuan-local-environment')).to_have_text(LABEL)
                expect(page.locator('.bc-list-card .bc-section-heading')).to_contain_text(f'共 {len(selected)} 家公司')
                expect(page.locator('.bc-company-name').first).to_have_text(selected[0]['name'])
                page.locator('.bc-company-name').first.click()
                expect(page.locator('.bc-company-detail h1')).to_have_text(chosen['name'])
                page.locator('.bc-source-details summary').click()
                expect(page.locator('.bc-source-details')).to_contain_text(detail['company']['source'])
                page.screenshot(path=str(output / (account['role'] + '-source-detail.png')), full_page=True)
                page.get_by_role('button', name='返回公司列表', exact=True).click()
                for category, grade in selection.items():
                    assert dict(parse_qsl(urlsplit(page.url).query))[category] == grade
                launcher = page.get_by_role('button', name='打开百川 AI 助手')
                expect(launcher).to_be_visible()
                launcher.click()
                panel = page.get_by_role('region', name='百川 AI 助手')
                expect(panel).to_contain_text('待核实候选')
                expect(panel).to_contain_text('源表确定规则验收')
                with page.expect_download() as event:
                    panel.get_by_role('button', name='下载 Excel', exact=True).first.click()
                path = output / (account['role'] + '-browser-download.xlsx')
                event.value.save_as(str(path))
                assert path.read_bytes() in downloads.values()
                page.get_by_role('button', name='在列表查看', exact=True).click()
                fixed = page.get_by_role('region', name='固定快照企业列表')
                expect(fixed).to_be_visible()
                expect(fixed).to_contain_text('待核实候选')
                expect(fixed.locator('.bca-result')).to_have_count(min(50, snapshot['total']))
                page.screenshot(path=str(output / (account['role'] + '-fixed-candidates.png')), full_page=True)
                fixed.locator('.bca-company').first.click()
                expect(fixed).to_have_count(0)
                expect(page.locator('.bc-company-detail h1')).to_be_visible()
                page.get_by_role('button', name='返回公司列表', exact=True).click()
                expect(page.locator('.bc-list-card .bc-section-heading')).to_contain_text(f'共 {len(selected)} 家公司')
                assert not errors and not blocked
                results.append({'role': account['role'], 'validation_label': fixture['validation_label'],
                    'companies': len(rows), 'exact_grade_count': len(electronic), 'same_category_or_count': len(either),
                    'cross_category_count': len(selected), 'list_detail_source': True, 'manual_filters_preserved': True,
                    'candidate_count': snapshot['counts']['candidate'], 'confirmed_count': 0,
                    'fixed_candidate_detail_navigation': True, 'default_export_company_rows': 0,
                    'candidate_export_rows': len(candidate_book['待核实信息']), 'real_browser_download': True,
                    'page_errors': [], 'outbound_network_requests': 0, 'natural_language_acceptance': False})
                context.close()
        finally:
            browser.close()
    after = model_log_count()
    assert after == before, 'Model call log changed during no-AI browser verification'
    receipt = {'source_kind': state['source_kind'], 'local_source_only': True, 'dataset_kind': 'isolation',
               'model_call_delta': after - before, 'validation_label': fixture['validation_label'], 'results': results}
    (output / 'results.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
