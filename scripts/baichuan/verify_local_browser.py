"""Real local Edge/HTTP verification; only the explicitly marked isolated DB.

Requires the verification interpreter's Playwright, httpx and python-docx. No
network, model, company API or browser response is mocked. Outputs go to ignored
.runtime/baichuan-ai-local; account secrets are read in memory and never printed.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import httpx
from docx import Document
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime/baichuan-ai-local'
BASE = 'http://127.0.0.1:13180'
PREFIX = '/api/enterprise/business/product/baichuan/assistant/'
MARKER = '隔离开发库，尚未连接现有企业资料'


def main(model_ready=False):
    if json.loads((RUNTIME / 'environment.json').read_text(encoding='utf-8')).get('kind') != 'baichuan_ai_isolated_local_v1':
        raise ValueError('Browser verification requires owned isolated runtime')
    accounts = json.loads((RUNTIME / 'accounts.json').read_text(encoding='utf-8'))['accounts']
    if model_ready:
        accounts = accounts[:1]  # Two real tasks maximum: one text and one DOCX.
    terminal = {'completed', 'partial'} if model_ready else {'failed'}
    output = RUNTIME / ('browser-model-verification' if model_ready else 'browser-verification')
    output.mkdir(exist_ok=True)
    fixture = output / 'synthetic-tender.docx'
    document = Document()
    document.add_heading('隔离开发合成招标文件', 0)
    document.add_paragraph('投标企业必须具有电子与智能化工程专业承包二级。')
    document.add_paragraph('优先项：投标企业具有 ITSS 二级。制造商证书不能代替投标企业证书。')
    document.save(fixture)
    results = []
    with httpx.Client(timeout=20) as client, sync_playwright() as p:
        browser = p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless=True)
        try:
            for index, account in enumerate(accounts):
                token_response = client.post(BASE+'/api/auth/login', json={'username': account['username'], 'password': account['password']})
                token_response.raise_for_status()
                tokens = token_response.json()
                headers = {'Authorization': 'Bearer ' + tokens['access_token']}
                client.post(BASE+'/api/enterprise/link', json={'username': account['username'], 'password': account['password']}, headers=headers).raise_for_status()
                config = client.get(BASE+PREFIX+'config/', headers=headers).json()
                assert config['enabled'] and config['environment_label'] == MARKER and config['capabilities']['model'] is model_ready
                context = browser.new_context(viewport={'width': 1440 if index == 0 else 1920, 'height': 1000}, reduced_motion='reduce')
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(BASE+'/login')
                page.evaluate('(tokens) => { localStorage.setItem("openclaw_access_token",tokens.access_token); localStorage.setItem("openclaw_refresh_token",tokens.refresh_token) }', tokens)
                page.goto(BASE+'/departments/product/baichuan')
                launch = page.get_by_role('button', name='打开百川 AI 助手')
                expect(launch).to_be_visible(timeout=20000)
                expect(page.get_by_role('region', name='百川 AI 助手')).to_have_count(0)
                expect(page.locator('#baichuan-local-environment')).to_contain_text(MARKER)
                before = page.locator('.bc-list-card').bounding_box()
                launch.click()
                panel = page.get_by_role('region', name='百川 AI 助手')
                expect(panel).to_be_visible()
                expect(page.get_by_label('需求或补充说明')).to_be_focused()
                expect(panel.get_by_role('note')).to_contain_text('联网补查暂不可用' if model_ready else '模型理解暂不可用')
                after = page.locator('.bc-list-card').bounding_box()
                assert abs(before['width'] - after['width']) < 1
                assert panel.bounding_box()['x'] > before['x']
                page.screenshot(path=str(output / (account['role']+'-open.png')), full_page=True)
                page.keyboard.press('Escape')
                expect(launch).to_be_visible()
                expect(launch).to_be_focused()
                launch.click()
                text = '隔离检查：广东电子与智能化二级企业'
                page.get_by_label('需求或补充说明').fill(text)
                page.get_by_role('button', name='发送', exact=True).click()
                expect(page.get_by_label('需求或补充说明')).to_have_value('', timeout=15000)
                page.get_by_role('button', name='收起助手，后台任务继续').click()
                expect(panel).to_have_count(0)
                # Server worker must finish after the panel has gone away.
                cid = page.evaluate('Object.entries(localStorage).find(([key])=>key.startsWith("baichuan-assistant:v1:"))?.[1]')
                assert cid
                for _ in range(120 if model_ready else 30):
                    current = client.get(BASE+PREFIX+'conversations/'+cid+'/', headers=headers).json()
                    if current['jobs'] and current['jobs'][0]['status'] in terminal:
                        break
                    time.sleep(.5)
                assert current['jobs'][0]['status'] in terminal, current['jobs'][0]
                page.reload()
                expect(launch).to_be_visible(timeout=15000)
                launch.click()
                expect(panel).to_contain_text(text, timeout=15000)
                expect(panel).to_contain_text('已检索当前授权库' if model_ready else '执行失败', timeout=15000)
                # A genuine file-only request exercises real DOCX parsing before
                # reaching the deliberately unavailable model gateway.
                page.locator('.bca-composer input[type=file]').set_input_files(str(fixture))
                page.get_by_role('button', name='发送', exact=True).click()
                expect(page.locator('.bca-files')).to_have_count(0, timeout=15000)
                for _ in range(120 if model_ready else 40):
                    current = client.get(BASE+PREFIX+'conversations/'+cid+'/', headers=headers).json()
                    if len(current['jobs']) >= 2 and current['jobs'][0]['status'] in terminal:
                        break
                    time.sleep(.5)
                assert len(current['jobs']) >= 2 and current['jobs'][0]['status'] in terminal, current['jobs'][0]
                assert current['attachments'][-1]['parse_status'] == 'completed'
                page.reload(); expect(launch).to_be_visible(timeout=15000); launch.click()
                expect(panel).to_contain_text('已检索当前授权库' if model_ready else '执行失败', timeout=15000)
                if model_ready:
                    assert len(current['snapshots']) >= 2
                    snapshot = current['snapshots'][0]
                    matched = client.get(BASE+PREFIX+'results/'+snapshot['id']+'/', headers=headers).json()
                    assert matched['total'] == 0
                    conditions = matched['conditions']
                    assert 'electronic' in json.dumps(conditions['must'])
                    assert 'itss' in json.dumps(conditions['should'])
                    assert conditions['source_refs']
                    (output/'synthetic-conditions.json').write_text(json.dumps(conditions,ensure_ascii=False,indent=2),encoding='utf-8')
                    page.get_by_role('button', name='在列表查看', exact=True).click()
                    fixed = page.get_by_role('region', name='固定快照企业列表')
                    expect(fixed).to_be_visible()
                    expect(fixed).to_contain_text('尚未连接现有企业资料时，不代表市场上没有符合企业')
                    expect(panel).to_have_count(0)
                    page.screenshot(path=str(output / 'product-fixed-snapshot.png'), full_page=True)
                    page.get_by_role('button', name='返回手工筛选列表', exact=True).click()
                    expect(fixed).to_have_count(0)
                    assert abs(page.locator('.bc-list-card').bounding_box()['width'] - before['width']) < 1
                    launch.click()
                page.screenshot(path=str(output / (account['role']+'-recovered-failure.png')), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                bound = panel.bounding_box()
                assert bound['x'] >= 0 and bound['x'] + bound['width'] <= 390
                page.screenshot(path=str(output / (account['role']+'-narrow.png')), full_page=True)
                assert not errors, errors
                results.append({'role': account['role'], 'default_collapsed': True, 'list_width_preserved': True,
                    'focus_and_escape': True, 'real_missing_model_failure': not model_ready, 'closed_task_persisted': True,
                    'refresh_recovered': True, 'real_docx_parse_status': current['attachments'][-1]['parse_status'],
                    'narrow_panel_within_viewport': True, 'page_errors': errors, 'real_model_condition_extraction': model_ready,
                    'real_company_count': 0, 'search_success_claimed': False})
                context.close()
        finally:
            browser.close()
    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-ready', action='store_true', help='Two bounded real synthetic model tasks; one product role')
    main(parser.parse_args().model_ready)
