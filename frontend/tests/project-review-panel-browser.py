"""Isolated real-React checks: python frontend/tests/project-review-panel-browser.py [URL] [evidence dir].

All API requests are intercepted; unexpected reads and every write fail locally.
Never starts a server, restarts a service, or accesses a real project.
"""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:3080'
OUTPUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'output/project-review-panel-browser')
TASK_ID = 'isolated-review-panel'
SOURCE_ID = 'isolated-equipment'
SOURCE_NAME = '隔离设备清单.xlsx'
BACKGROUND_ID = 'isolated-background'
BACKGROUND_NAME = '隔离项目背景.docx'
SUMMARY = dict(status='needs_review', method='native', extraction_hash='e' * 64,
               parser_version='isolated-v1', block_count=48, item_count=48,
               character_count=2400, truncated=False, metadata=dict(sheets=1))


def fixtures():
    sources = [dict(id=SOURCE_ID, original_name=SOURCE_NAME, purpose='equipment', size=2048,
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    sha256='a' * 64, created_at='2026-10-15T00:00:00Z', warnings=[], parsed=SUMMARY),
               dict(id=BACKGROUND_ID, original_name=BACKGROUND_NAME, purpose='background', size=1024,
                    media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    sha256='b' * 64, created_at='2026-10-15T00:00:00Z', warnings=[], parsed=SUMMARY)]
    task = dict(id=TASK_ID, title='隔离核对面板验收', state='WAITING_REVIEW', stage='BLUEPRINT',
                version=3, input_version=2, blueprint_version=1, owner_id=77, owner_name='隔离所有者',
                reviewer_id=77, reviewer_name='隔离所有者', created_at='2026-10-15T00:00:00Z',
                updated_at='2026-10-15T00:00:00Z', intake_mode='equipment_background',
                output_families=['technical-solution', 'feasibility', 'presentation'],
                output_targets={'technical-solution': 60000, 'feasibility': 50000},
                blueprint_approved=False,
                blueprint_review=dict(revision_count=0, revision_limit=3, revisions_remaining=3),
                input=dict(project='隔离核对面板验收', requirements='隔离验收建设目标',
                           background='隔离背景，只用于前端验收。', conditions=['输入阶段待核条件'],
                           items=[dict(row_id=i, name=f'隔离设备{i}', quantity=i, unit='台',
                                       source_id=SOURCE_ID, source_item_id=f'item-{i}',
                                       source_location=dict(sheet='设备配置表', row=i + 1, range=f'A{i + 1}:D{i + 1}'))
                                  for i in range(1, 49)], knowledge_sources=[]),
                blueprint=dict(id='isolated-blueprint', version=1, sha256='c' * 64,
                               payload=dict(purpose='建设目标', audience='评审人员',
                                            chapters=[dict(id='chapter-1', family='technical-solution',
                                                           title='隔离总体设计', scope='隔离章节范围', source_ids=[SOURCE_ID])],
                                            conditions=[dict(text='现场供电条件需核对', type='human'),
                                                        dict(text='既有接口条件需确认', type='program')],
                                            missing=['未提供现场拓扑', '未提供运维责任界面'],
                                            conflicts=['设备清单和背景材料的端口数量不一致'],
                                            template_version='isolated-v1')),
                chapters=[], reports=[], artifacts=[], sources=sources, approvals=[], issues=[],
                input_issues=[dict(issue_hash='isolated-input-1', code='quantity_missing',
                                   detail='第 2 行设备数量需对照原件核验', source_id=SOURCE_ID),
                              dict(issue_hash='isolated-input-2', code='source_conflict',
                                   detail='接口描述与清单记录需要核验', source_id=BACKGROUND_ID)],
                error_code='', pending_action='核对资料后确认蓝图',
                actions=['review_input', 'correct_source', 'add_source', 'save_input', 'save_blueprint'],
                blockers={}, impact={})
    overview = dict(as_of='2026-10-15T00:00:00Z', scope='authorized_projects', projects=[task],
                    metrics=dict(active=1, review=1, generation=0, completed_month=0),
                    pagination=dict(page=1, page_size=20, total=1, pages=1), recent_projects=[task],
                    todos=[], recent_outputs=[], reviewers=[], templates=[],
                    capabilities=dict(model_generation=True, retrieval=True, formal_release=False,
                                      office_preview=False, upload_extensions=['.xlsx', '.docx', '.pdf'],
                                      upload_max_bytes=4096))
    details = {}
    for source in sources:
        details[source['id']] = dict(
            id=source['id'], task_id=TASK_ID, task_version=3, name=source['original_name'],
            sha256=source['sha256'], size=source['size'], media_type=source['media_type'], summary=SUMMARY,
            blocks=[dict(id=f'block-{i}', kind='table_row', text=f'隔离设备{i} {i} 台',
                         cells=[str(i), f'隔离设备{i}', str(i), '台'],
                         location=dict(sheet='设备配置表', row=i + 1, range=f'A{i + 1}:D{i + 1}'),
                         location_label=f'设备配置表 · 第 {i + 1} 行') for i in range(1, 41)],
            warnings=[dict(code='isolated-warning', detail='表格内容需要结合原始资料核对')],
            issues=[dict(issue_hash=f"{source['id']}-issue", code='isolated-source-issue',
                         detail='隔离解析疑点需要人工核对')],
            revisions=[dict(version=2, sha256=source['sha256'], created_at='2026-10-15T00:00:00Z', reason='隔离解析')],
            pagination=dict(page=1, page_size=40, total=48), can_reparse=True,
            can_correct=True, can_preview=False)
        blocks = details[source['id']]['blocks']
        blocks[33]['cells'] = ['', '', '', '']
        blocks[35]['location'] = dict(sheet='其他工作表', row=1)
        blocks[35]['location_label'] = '其他工作表 · 第 1 行'
        blocks[36]['location'] = dict(table=2, row=1)
        blocks[36]['location_label'] = '表 2 · 第 1 行'
        blocks[37]['location'] = dict(table=2, part='附件', row=2)
        blocks[37]['location_label'] = '附件 · 表 2 · 第 2 行'
        blocks[38]['cells'] = ['仅有两列', '列数不同必须独立']
        blocks[39] = dict(id='block-paragraph', kind='paragraph', text='隔离补充说明文段保留',
                          location=dict(paragraph=1), location_label='正文 · 第 1 段')
    return task, overview, details


def no_overflow(page, width, height):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page has horizontal overflow'
    layout = page.locator('.wb-project-layout')
    assert layout.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), 'Project has horizontal overflow'
    panel = page.get_by_role('complementary', name='项目资料核对面板', exact=True)
    box = panel.bounding_box()
    assert box and box['x'] >= 0 and box['y'] >= 0, box
    assert box['x'] + box['width'] <= width + 1 and box['y'] + box['height'] <= height + 1, box
    return box


def run_case(browser, role, width, height, stale_issue=False):
    task, overview, details = fixtures()
    context = browser.new_context(viewport=dict(width=width, height=height), service_workers='block')
    context.add_init_script("localStorage.setItem('openclaw_access_token','isolated-review-panel-token')")
    unexpected, errors, calls, dialogs = [], [], [], []
    user = dict(id='isolated-product-user', username='隔离核对验收', role='user', business_role=role,
                department_code=None if role == 'general_manager' else 'product', portal_user_id=77,
                capabilities=['general_manager', 'product', 'engineering', 'hr']
                if role == 'general_manager' else ['product'])

    def route_api(route):
        request = route.request
        path = urlparse(request.url).path.replace('/api/enterprise/business/', '/api/')
        calls.append(dict(path=path, method=request.method))
        responses = {
            '/api/auth/me': user,
            '/api/enterprise/status': dict(configured=True, linked=True, available=True, message='隔离验收'),
            '/api/openclaw/ping': dict(message='ok'),
            '/api/openclaw/container/info': dict(status='running'),
            '/api/business/ledgers/permissions/': dict(departments=[]),
            '/api/product/tasks/': dict(tasks=[task]),
            '/api/product/workspace/': overview,
            f'/api/product/tasks/{TASK_ID}/': task,
            f'/api/product/tasks/{TASK_ID}/outputs/': dict(task_version=task['version'], outputs=[]),
            f'/api/product/tasks/{TASK_ID}/history/': dict(task_id=TASK_ID, task_version=task['version'],
                                                        history_immutable=True, tamper_claim='', timeline=[]),
            **{f'/api/product/sources/{key}/': value for key, value in details.items()},
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
    try:
        page.goto(BASE + f'/departments/product/documents?task={TASK_ID}')
        page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading', name='隔离核对面板验收', exact=False)).to_be_visible()
        if stale_issue:
            page.locator('.pd-project-facts').get_by_role('button', name=re.compile('待核验事项')).click()
            panel = page.get_by_role('complementary', name='项目资料核对面板', exact=True)
            panel.get_by_role('combobox', name='核对分类 1', exact=True).select_option('fact')
            original_reason = '后台版本更新后仍须保留的隔离核对依据'
            panel.get_by_role('textbox', name='核对依据 1', exact=True).fill(original_reason)
            panel.get_by_role('group', name='关联来源 1', exact=True).get_by_role('checkbox').first.check()
            task.update(version=4, input_issues=[task['input_issues'][1]])
            with page.expect_response(lambda response: urlparse(response.url).path.endswith(f'/tasks/{TASK_ID}/')):
                page.evaluate("window.dispatchEvent(new Event('focus'))")
            retained = panel.get_by_role('textbox', name='已保留的核对依据', exact=True)
            expect(retained).to_have_value(original_reason)
            expect(retained).to_have_attribute('readonly', '')
            draft = retained.locator('xpath=ancestor::section[1]')
            expect(draft.get_by_role('alert')).to_contain_text('问题')
            expect(draft.get_by_role('button', name='保存核对', exact=True)).to_have_count(0)
            expect(panel.get_by_role('textbox', name='核对依据 1', exact=True)).to_have_value('')

            def reject_stale_close(dialog):
                dialogs.append(dict(type=dialog.type, message=dialog.message, action='dismiss'))
                dialog.dismiss()

            page.on('dialog', reject_stale_close)
            panel.get_by_role('button', name='关闭核对面板', exact=True).click()
            expect(retained).to_have_value(original_reason)
            assert len(dialogs) == 1 and '未保存' in dialogs[0]['message'], dialogs
            page.remove_listener('dialog', reject_stale_close)
            page.screenshot(path=str(OUTPUT / 'stale-issue-retained.png'))
            draft.get_by_role('button', name='放弃此草稿', exact=True).click()
            expect(retained).to_have_count(0)
            panel.get_by_role('button', name='关闭核对面板', exact=True).click()
            expect(panel).to_have_count(0)
            expect(page.get_by_role('complementary', name='项目成果', exact=True)).to_be_visible()
            assert not unexpected, unexpected
            assert not errors, errors
            assert all(call['method'] == 'GET' for call in calls), calls
            return dict(role=role, viewport=[width, height], scenario='issue_removed_after_background_refresh',
                        api_calls=calls, dialogs=dialogs,
                        checks='version 3 to 4 focus refresh; removed issue draft retained read-only; '
                               'no old-hash save; close guard; explicit discard then close')
        page.screenshot(path=str(OUTPUT / f'{role}-{width}-initial.png'))
        results = page.get_by_role('complementary', name='项目成果', exact=True)
        expect(results).to_be_visible()
        page.locator('.pd-project-facts').get_by_role('button', name=re.compile('资料解析')).click()
        panel = page.get_by_role('complementary', name='项目资料核对面板', exact=True)
        expect(panel).to_be_visible()
        expect(results).to_be_hidden()
        tabs = panel.get_by_role('tablist', name='资料核对分类')
        expect(tabs.get_by_role('tab')).to_have_count(3)
        expect(tabs.get_by_role('tab', name='资料解析', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(panel.get_by_role('combobox', name='选择解析资料', exact=True)).to_contain_text(SOURCE_NAME)
        expect(panel.get_by_role('combobox', name='选择解析资料', exact=True)).to_contain_text(BACKGROUND_NAME)
        expect(panel.get_by_role('link', name='下载原文件', exact=True)).to_have_attribute(
            'href', re.compile(f'/product/sources/{SOURCE_ID}/download/'))
        bounds = no_overflow(page, width, height)

        separator = page.get_by_role('separator', name='调整项目核对面板宽度', exact=True)
        separator.focus()
        separator.press('Home')
        minimum = float(separator.get_attribute('aria-valuemin'))
        expect(separator).to_have_attribute('aria-valuenow', str(int(minimum)))
        separator.press('ArrowLeft')
        assert float(separator.get_attribute('aria-valuenow')) > minimum
        separator.press('ArrowRight')
        expect(separator).to_have_attribute('aria-valuenow', str(int(minimum)))
        handle = separator.bounding_box()
        page.mouse.move(handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2)
        page.mouse.down()
        page.mouse.move(handle['x'] - 80, handle['y'] + handle['height'] / 2, steps=8)
        page.mouse.up()
        wider = float(separator.get_attribute('aria-valuenow'))
        assert wider > minimum, (minimum, wider)
        handle = separator.bounding_box()
        page.mouse.move(handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2)
        page.mouse.down()
        page.mouse.move(handle['x'] + 45, handle['y'] + handle['height'] / 2, steps=8)
        page.mouse.up()
        assert float(separator.get_attribute('aria-valuenow')) < wider
        no_overflow(page, width, height)
        panel.get_by_role('button', name='放大核对面板', exact=True).click()
        enlarged = no_overflow(page, width, height)
        assert enlarged['width'] > bounds['width'], (bounds, enlarged)
        page.screenshot(path=str(OUTPUT / f'{role}-{width}-expanded.png'))
        panel.get_by_role('button', name='还原核对面板', exact=True).click()
        no_overflow(page, width, height)

        tabs.get_by_role('tab', name='缺口与冲突', exact=True).click()
        expect(panel.get_by_text('未提供现场拓扑', exact=True)).to_be_visible()
        expect(panel.get_by_text('设备清单和背景材料的端口数量不一致', exact=True)).to_be_visible()
        tabs.get_by_role('tab', name='待核验事项', exact=True).click()
        expect(panel.get_by_text('现场供电条件需核对', exact=True)).to_be_visible()
        category = panel.get_by_role('combobox', name='核对分类 1', exact=True)
        reason = panel.get_by_role('textbox', name='核对依据 1', exact=True)
        expect(category).to_be_enabled()
        expect(reason).to_be_enabled()
        form = category.locator('xpath=ancestor::form')
        expect(form.get_by_role('button', name='保存核对', exact=True)).to_be_disabled()
        category.select_option('fact')
        reason.fill('隔离验收依据；仅本地编辑，不提交。')
        sources = form.get_by_role('group', name='关联来源 1', exact=True)
        expect(sources).to_contain_text(SOURCE_NAME)
        expect(sources).to_contain_text(BACKGROUND_NAME)
        expect(form.get_by_role('button', name='保存核对', exact=True)).to_be_disabled()
        sources.get_by_role('checkbox').first.check()
        expect(form.get_by_role('button', name='保存核对', exact=True)).to_be_enabled()

        def dismiss(dialog):
            dialogs.append(dict(type=dialog.type, message=dialog.message, action='dismiss'))
            dialog.dismiss()

        page.on('dialog', dismiss)
        tabs.get_by_role('tab', name='缺口与冲突', exact=True).click()
        expect(tabs.get_by_role('tab', name='待核验事项', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(reason).to_have_value('隔离验收依据；仅本地编辑，不提交。')
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        expect(panel).to_be_visible()
        expect(reason).to_have_value('隔离验收依据；仅本地编辑，不提交。')
        assert len(dialogs) == 2 and all('未保存' in item['message'] for item in dialogs), dialogs
        page.remove_listener('dialog', dismiss)

        def accept(dialog):
            dialogs.append(dict(type=dialog.type, message=dialog.message, action='accept'))
            dialog.accept()

        page.on('dialog', accept)
        tabs.get_by_role('tab', name='资料解析', exact=True).click()
        page.remove_listener('dialog', accept)
        expect(tabs.get_by_role('tab', name='资料解析', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(panel.locator('.pd-source-table tbody tr')).to_have_count(39)
        assert panel.locator('.pd-source-table').count() >= 5
        expect(panel.locator('.pd-source-table').first).to_contain_text('第 1 列')
        expect(panel.locator('.pd-source-table').first).to_contain_text('设备配置表 · 第 2 行')
        expect(panel.get_by_text('隔离补充说明文段保留', exact=True)).to_have_count(1)
        expect(panel.get_by_text('列数不同必须独立', exact=True)).to_have_count(1)

        panel.locator('.pd-source-block-actions').get_by_role('button', name='校正内容', exact=True).first.click()
        cell = panel.get_by_role('textbox', name='第 1 列', exact=True)
        cell.fill('隔离编辑未保存')
        panel.get_by_role('textbox', name='校正依据', exact=True).fill('隔离编辑依据，不提交')
        page.on('dialog', dismiss)
        panel.get_by_role('combobox', name='选择解析资料', exact=True).select_option(BACKGROUND_ID)
        expect(cell).to_have_value('隔离编辑未保存')
        tabs.get_by_role('tab', name='缺口与冲突', exact=True).click()
        expect(tabs.get_by_role('tab', name='资料解析', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(cell).to_have_value('隔离编辑未保存')
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        expect(cell).to_have_value('隔离编辑未保存')
        page.remove_listener('dialog', dismiss)
        panel.get_by_role('button', name='取消校正', exact=True).click()

        scroll = panel.locator('.wb-review-content')
        header = panel.locator(':scope > header')
        footer = panel.locator(':scope > footer')
        before_header, before_footer = header.bounding_box(), footer.bounding_box()
        center_scroll = page.locator('.wb-project-center').evaluate('(el) => el.scrollTop')
        scroll.evaluate('(el) => el.scrollTop = el.scrollHeight')
        assert scroll.evaluate('(el) => el.scrollTop') > 0
        assert header.bounding_box() == before_header
        assert footer.bounding_box() == before_footer
        assert page.locator('.wb-project-center').evaluate('(el) => el.scrollTop') == center_scroll
        expect(panel.get_by_role('button', name='关闭核对面板', exact=True)).to_be_in_viewport()
        no_overflow(page, width, height)
        page.screenshot(path=str(OUTPUT / f'{role}-{width}-source-scroll.png'))

        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        expect(panel).to_have_count(0)
        expect(results).to_be_visible()
        page.locator('.pd-project-facts').get_by_role('button', name=re.compile('待核验事项')).click()
        expect(tabs.get_by_role('tab', name='待核验事项', exact=True)).to_have_attribute('aria-selected', 'true')
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        page.locator('.pd-project-facts').get_by_role('button', name=re.compile('缺口与冲突')).click()
        expect(tabs.get_by_role('tab', name='缺口与冲突', exact=True)).to_have_attribute('aria-selected', 'true')
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        page.get_by_role('tab', name=re.compile('^项目资料')).click()
        expect(page.locator('#panel-sources .pd-extraction-blocks')).to_have_count(0)
        expect(page.locator('#panel-sources .pd-source-table')).to_have_count(0)
        expect(page.locator('#panel-sources').get_by_text('资料解析与来源核对', exact=True)).to_have_count(0)
        expect(page.locator('#panel-sources').get_by_text('设备清单事实', exact=True)).to_have_count(0)
        expect(page.locator('#panel-sources').get_by_role('button', name='查看并核验输入问题 →', exact=True)).to_have_count(0)
        source_row = page.locator('#panel-sources').locator('tr, .pd-upload-list > li').filter(has_text=BACKGROUND_NAME)
        source_row.get_by_role('button', name='查看解析', exact=True).click()
        expect(panel).to_be_visible()
        expect(panel.locator('.pd-source-heading')).to_contain_text(BACKGROUND_NAME)
        expect(panel.get_by_role('link', name='下载原文件', exact=True)).to_have_attribute(
            'href', re.compile(f'/product/sources/{BACKGROUND_ID}/download/'))
        no_overflow(page, width, height)
        page.screenshot(path=str(OUTPUT / f'{role}-{width}-source-entry.png'))
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        expect(results).to_be_visible()
        assert not unexpected, unexpected
        assert not errors, errors
        assert all(call['method'] == 'GET' for call in calls), calls
        return dict(role=role, viewport=[width, height], panel_bounds=bounds, expanded_bounds=enlarged,
                    api_calls=calls, dialogs=dialogs,
                    checks='three entries/tabs; source row entry; drag both directions; keyboard widths; '
                           'expand/restore; fixed header/footer; independent scroll; close restores outputs; '
                           'no horizontal overflow; compact table; source references; review draft guards')
    except Exception:
        prefix = 'stale-issue' if stale_issue else f'{role}-{width}'
        page.screenshot(path=str(OUTPUT / f'{prefix}-failure.png'))
        (OUTPUT / f'{prefix}-failure.html').write_text(page.content(), encoding='utf-8')
        raise
    finally:
        context.close()


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for business_role in ('general_manager', 'employee'):
                for viewport_width, viewport_height in ((1280, 800), (1920, 1080)):
                    results.append(run_case(browser, business_role, viewport_width, viewport_height))
            results.append(run_case(browser, 'general_manager', 1280, 800, stale_issue=True))
        finally:
            browser.close()
    (OUTPUT / 'results.json').write_text(json.dumps(dict(
        scope='Isolated API fixtures; every API write rejected; no real project access', results=results),
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: 4 role/viewport combinations + 1 background-refresh regression; evidence: {OUTPUT.resolve()}')
