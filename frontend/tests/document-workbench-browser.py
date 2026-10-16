"""Isolated UI acceptance: python frontend/tests/document-workbench-browser.py [URL] [evidence dir].

Requires an existing frontend. Every API request is fulfilled locally; only GET/HEAD
frontend assets may reach the supplied origin. The retry POST is checked and mocked.
Never starts a server or reads/writes a real business project.
"""
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:3080').rstrip('/')
OUTPUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'output/document-workbench-browser')
SPEC = importlib.util.spec_from_file_location(
    'review_panel_fixtures', Path(__file__).with_name('project-review-panel-browser.py'))
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)
FIRST_TEXT = '隔离验收正文第一段：已保存的项目建设目标和技术设计依据，可直接阅读。'


def fixtures(automatic):
    task, overview, details = FIXTURE.fixtures()
    task.update(title='正文编制隔离验收', state='QUEUED' if automatic else 'FAILED',
                stage='WRITING', blueprint_approved=True, error_code='timeout' if automatic else 'diagram_render_failed',
                actions=['review_input'] if automatic else ['retry', 'review_input'],
                retry_after='2099-10-16T08:00:00Z' if automatic else None,
                retry_budget=dict(used=1, limit=3, remaining=2),
                analysis_progress={key: dict(status=status, detail=detail) for key, status, detail in (
                    ('documents', 'completed', '项目背景已解析'),
                    ('equipment', 'completed', '设备清单已解析'),
                    ('blueprint', 'completed', '项目蓝图已保存'),
                    ('review', 'completed', '本人已确认蓝图'),
                    ('writing_technical', 'completed', '技术方案正文已保存'),
                    ('diagrams_technical', 'retry_wait' if automatic else 'failed', '待补图表，正文已保留'))},
                generation_steps=[dict(key='writing:technical-solution:isolated-private-hash',
                                       status='completed', attempts=1, error_code='', retry_after=None),
                                  dict(key='diagram:technical-solution:isolated-figure-key',
                                       status='retry_wait' if automatic else 'failed', attempts=1,
                                       error_code='timeout' if automatic else 'diagram_render_failed',
                                       retry_after='2099-10-16T08:00:00Z' if automatic else None)])
    # Workflow phases use the public phase contract; retry_wait belongs to saved steps.
    task['analysis_progress']['diagrams_technical']['status'] = 'pending' if automatic else 'failed'
    task['blueprint']['input_hash'] = 'd' * 64
    task['blueprint']['payload']['chapters'].append(dict(
        id='chapter-2', family='technical-solution', title='隔离实施计划',
        scope='第二章实施范围', source_ids=[FIXTURE.SOURCE_ID]))
    task['chapters'] = [dict(
        id=f'isolated-saved-{index}', family='technical-solution', version=1,
        input_hash='d' * 64, blueprint_hash=task['blueprint']['sha256'],
        payload=dict(chapter_id=chapter['id'], title=chapter['title'],
                     paragraphs=([FIRST_TEXT] + [f'隔离正文段落 {number}：项目设计依据和实施安排已保存。' for number in range(30)]
                                 if index == 0 else ['第二章已保存原文，默认保持折叠。']),
                     source_ids=[FIXTURE.SOURCE_ID]))
        for index, chapter in enumerate(task['blueprint']['payload']['chapters'])]
    return task, overview, details


def no_overflow(page):
    for locator in (page.locator('html'), page.locator('.wb-project-layout')):
        assert locator.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), 'Horizontal overflow'


def layout_rects(page):
    return {selector: page.locator(selector).bounding_box()
            for selector in ('.pd-project-overview', '.wb-project-center')}


def same_layout(page, before):
    after = layout_rects(page)
    for selector, rect in before.items():
        assert rect and after[selector], (selector, rect, after[selector])
        assert all(abs(rect[key] - after[selector][key]) <= 1 for key in ('x', 'y', 'width', 'height')), (selector, rect, after[selector])


def run_case(browser, role, width, height, automatic, running=False):
    task, overview, details = fixtures(automatic)
    scenario = 'running-poll' if running else 'automatic' if automatic else 'manual'
    if running:
        task.update(state='RUNNING', error_code='', retry_after=None, actions=[])
        task['analysis_progress']['diagrams_technical'].update(status='running', detail='隔离轮询更新第 0 次，已完成 1/8 批')
        task['generation_steps'][1].update(status='running', error_code='', retry_after=None)
    prefix = f'{role}-{width}x{height}-{scenario}'
    context = browser.new_context(viewport=dict(width=width, height=height), service_workers='block')
    context.add_init_script("localStorage.setItem('openclaw_access_token','isolated-document-workbench-token')")
    calls, unexpected, errors, retry_bodies = [], [], [], []
    poll_updates, poll_versions, polling_enabled = 0, [], False
    origin = urlparse(BASE)
    user = dict(id='isolated-product-user', username='隔离正文验收', role='user', business_role=role,
                department_code=None if role == 'general_manager' else 'product', portal_user_id=77,
                capabilities=['general_manager', 'product', 'engineering', 'hr']
                if role == 'general_manager' else ['product'])

    def intercept(route):
        nonlocal poll_updates
        request = route.request
        url = urlparse(request.url)
        path = url.path.replace('/api/enterprise/business/', '/api/')
        is_api = bool(re.search(r'/api(?:/|$)', url.path, re.I))
        if not is_api:
            if (url.scheme, url.netloc) == (origin.scheme, origin.netloc) and request.method in ('GET', 'HEAD'):
                return route.continue_()
            unexpected.append(dict(path=url.path, method=request.method, reason='non-asset request'))
            return route.abort()
        calls.append(dict(path=path, method=request.method))
        if running and polling_enabled and path == f'/api/product/tasks/{FIXTURE.TASK_ID}/' and request.method == 'GET':
            poll_updates += 1
            task['version'] += 1
            poll_versions.append(task['version'])
            task['analysis_progress']['diagrams_technical']['detail'] = f'隔离轮询更新第 {poll_updates} 次，已完成 {poll_updates + 1}/8 批'
        # This is the only accepted write, and is fulfilled before network access.
        if path == f'/api/product/tasks/{FIXTURE.TASK_ID}/retry/' and request.method == 'POST' and not automatic:
            body = request.post_data_json
            retry_bodies.append(body)
            if body != dict(expected_version=task['version']) or len(retry_bodies) != 1:
                unexpected.append(dict(path=path, method=request.method, body=body))
                return route.fulfill(status=409, json=dict(detail='Isolated retry version mismatch'))
            task.update(version=task['version'] + 1, state='QUEUED', actions=[],
                        retry_after='2099-10-16T08:00:00Z')
            return route.fulfill(json=task)
        responses = {
            '/api/auth/me': user,
            '/api/enterprise/status': dict(configured=True, linked=True, available=True, message='隔离验收'),
            '/api/openclaw/ping': dict(message='ok'),
            '/api/openclaw/container/info': dict(status='running'),
            '/api/business/ledgers/permissions/': dict(departments=[]),
            '/api/product/tasks/': dict(tasks=[task]),
            '/api/product/workspace/': overview,
            f'/api/product/tasks/{FIXTURE.TASK_ID}/': task,
            f'/api/product/tasks/{FIXTURE.TASK_ID}/outputs/': dict(task_version=task['version'], outputs=[]),
            f'/api/product/tasks/{FIXTURE.TASK_ID}/history/': dict(
                task_id=FIXTURE.TASK_ID, task_version=task['version'],
                history_immutable=True, tamper_claim='', timeline=[]),
            **{f'/api/product/sources/{key}/': value for key, value in details.items()},
        }
        if path == '/api/openclaw/events/stream' and request.method == 'GET':
            return route.fulfill(status=204)
        if request.method != 'GET' or path not in responses:
            unexpected.append(dict(path=path, method=request.method))
            return route.fulfill(status=501, json=dict(detail='Unexpected isolated API request'))
        route.fulfill(json=responses[path])

    context.route('**/*', intercept)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        # Intentionally omit tab: approved saved text should select the report workspace.
        page.goto(BASE + f'/departments/product/documents?task={FIXTURE.TASK_ID}')
        page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading', name='正文编制隔离验收', exact=False)).to_be_visible()
        expect(page.get_by_role('tab', name='技术方案', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(page.locator('#panel-technical-solution')).to_be_visible()
        overview_box = page.locator('.pd-project-overview').bounding_box()
        layout_box = page.locator('.wb-project-layout').bounding_box()
        assert overview_box and layout_box and abs(overview_box['x'] - (layout_box['x'] + 18)) <= 2 and abs(overview_box['width'] - (layout_box['width'] - 36)) <= 2
        expect(page.get_by_role('list', name='项目阶段总览')).to_be_visible()
        expect(page.locator('.pd-project-facts button')).to_have_count(3)
        body = page.get_by_role('region', name='技术方案已保存正文', exact=True)
        expect(body).to_be_visible()
        chapters = body.locator(':scope > details')
        expect(chapters).to_have_count(2)
        assert chapters.first.evaluate('(el) => el.open'), 'First saved chapter must open by default'
        assert not chapters.nth(1).evaluate('(el) => el.open'), 'Other saved chapters should remain folded'
        expect(page.get_by_text(FIRST_TEXT, exact=True)).to_be_in_viewport(ratio=0.5)
        initial_scroll = page.locator('.wb-project-center').evaluate('(el) => el.scrollTop')
        assert initial_scroll == 0, f'Initial saved body required scrolling: {initial_scroll}'
        expect(page.get_by_role('button', name='下载正文草稿 TXT', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='下载文件', exact=True)).to_have_count(0)
        results = page.get_by_role('complementary', name='项目成果', exact=True)
        expect(results.locator('[data-output-family="technical-solution"]')).to_contain_text('正文已保存，文件待生成')
        expect(body).to_contain_text('正文保存不代表成果文件已生成或正式交付')
        expect(results).not_to_contain_text('已交付')
        expect(results).not_to_contain_text('文件已保存')
        for name in ('打开技术方案', '打开可研报告', '打开汇报 PPT'):
            expect(results.get_by_role('button', name=name, exact=True)).to_be_visible()
        no_overflow(page)
        page.screenshot(path=str(OUTPUT / f'{prefix}-initial.png'))

        retry = page.get_by_role('button', name='从已保存进度重试', exact=True)
        if running:
            expect(page.locator('.pd-compact-progress')).to_contain_text('隔离轮询更新第 0 次')
            expect(retry).to_have_count(0)
        elif automatic:
            expect(page.locator('.pd-compact-progress')).to_contain_text('自动恢复')
            expect(retry).to_have_count(0)
            expect(page.get_by_role('button', name='重试生成', exact=True)).to_have_count(0)
        else:
            expect(retry).to_be_enabled()

        expect(page.locator('.pd-task-details, .pd-progress-milestones')).to_have_count(0)
        assert page.locator('.pd-project-overview').evaluate("(el) => getComputedStyle(el).maxHeight === 'none' && !['auto', 'scroll'].includes(getComputedStyle(el).overflowY)")
        main = page.locator('.wb-project-center')
        main_scroll = main.evaluate('(el) => { el.scrollTop = Math.min(120, el.scrollHeight - el.clientHeight); return el.scrollTop; }')
        assert main_scroll > 0, 'Long saved body must exercise main reading-position preservation'
        before = layout_rects(page)
        trigger = page.get_by_role('button', name='查看处理详情', exact=True)
        expect(trigger).to_have_attribute('aria-haspopup', 'dialog')
        progress = page.locator('#project-progress-dialog')
        expect(progress).to_be_hidden()
        trigger.click()
        expect(progress).to_be_visible()
        assert progress.evaluate('(el) => el.open && el.matches(":modal")'), 'Details must use native modal behavior'
        expect(progress.get_by_role('heading', name='处理详情', exact=True)).to_be_visible()
        same_layout(page, before)
        chain = progress.get_by_role('list', name='完整处理链路', exact=True)
        expect(chain).to_be_visible()
        expect(progress.locator('ol[aria-label="完整处理链路"]')).to_have_count(1)
        node_titles = chain.locator(':scope > li h3').all_text_contents()
        assert len(node_titles) >= 10 and len(node_titles) == len(set(node_titles)), node_titles
        expect(chain.locator(':scope > li')).to_have_count(len(node_titles))
        expect(progress.locator('details details, .pd-task-details, .pd-progress-milestones')).to_have_count(0)
        scroll_containers = progress.evaluate("""(el) => [el, ...el.querySelectorAll('*')].filter(node =>
            node.getClientRects().length && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY))
            .map(node => node.className)""")
        assert scroll_containers == ['pd-progress-dialog-content'], scroll_containers
        if not automatic and not running:
            expect(progress.locator('#project-failure-reason')).to_be_visible()
            expect(progress.locator('#project-failure-reason')).to_contain_text('正文已保存')
        else:
            expect(progress.locator('#project-failure-reason')).to_have_count(0)
        progress_tab = progress.get_by_role('tab', name='处理进度', exact=True)
        recovery_tab = progress.get_by_role('tab', name='恢复记录', exact=True)
        progress_tab.focus()
        progress_tab.press('ArrowRight')
        expect(recovery_tab).to_be_focused()
        expect(recovery_tab).to_have_attribute('aria-selected', 'true')
        expect(chain).to_be_hidden()
        steps = progress.locator('section.pd-recovery-records')
        expect(steps.get_by_role('list', name='已保存生成步骤', exact=True)).to_be_visible()
        expect(steps).to_contain_text('已缓存，可恢复时复用')
        assert 'isolated-private-hash' not in steps.inner_text()
        assert 'isolated-figure-key' not in steps.inner_text()
        expect(steps.locator('details')).to_have_count(0)
        recovery_tab.press('Home')
        expect(progress_tab).to_be_focused()
        expect(progress_tab).to_have_attribute('aria-selected', 'true')
        progress_tab.press('End')
        expect(recovery_tab).to_be_focused()
        recovery_tab.press('ArrowLeft')
        expect(progress_tab).to_be_focused()
        for key in ['Tab'] * 8 + ['Shift+Tab'] * 8:
            page.keyboard.press(key)
            # Native modal may yield to browser chrome (body), but never to background controls.
            assert progress.evaluate('(el) => el.contains(document.activeElement) || (document.activeElement === document.body && el.matches(":modal"))'), f'Background control received focus on {key}'
        content = progress.locator('.pd-progress-dialog-content')
        dialog_scroll = content.evaluate('(el) => { el.scrollTop = Math.min(220, el.scrollHeight - el.clientHeight); return el.scrollTop; }')
        assert dialog_scroll > 0, 'Progress list must exercise detail scrolling'
        if running:
            # Arm only after the reader has positioned the dialog; two real 3-second polls stay local.
            progress_tab.evaluate('(el) => el.focus({preventScroll:true})')
            polling_enabled = True
            for update in (1, 2):
                expect(chain).to_contain_text(f'隔离轮询更新第 {update} 次', timeout=10000)
                expect(page.locator('.wb-project-version')).to_have_text(f"v{task['version']}")
                assert abs(content.evaluate('(el) => el.scrollTop') - dialog_scroll) <= 1
                expect(progress_tab).to_be_focused()
                same_layout(page, before)
            polling_enabled = False
            assert poll_updates == 2 and poll_versions[1] == poll_versions[0] + 1, poll_versions
        no_overflow(page)
        page.screenshot(path=str(OUTPUT / f'{prefix}-progress.png'))
        for close_method in ('Escape', '返回文档', '关闭处理详情', 'backdrop'):
            if close_method == 'Escape':
                page.keyboard.press('Escape')
            elif close_method == 'backdrop':
                bounds = progress.bounding_box()
                assert bounds and bounds['x'] > 20
                page.mouse.click(bounds['x'] / 2, height / 2)
            else:
                progress.get_by_role('button', name=close_method, exact=True).click()
            expect(progress).to_be_hidden()
            expect(trigger).to_be_focused()
            same_layout(page, before)
            assert abs(main.evaluate('(el) => el.scrollTop') - main_scroll) <= 1
            if close_method != 'backdrop':
                trigger.click()
                expect(progress).to_be_visible()
                same_layout(page, before)
        if running:
            assert not unexpected and not errors and not retry_bodies, (unexpected, errors, retry_bodies)
            assert all(call['method'] == 'GET' for call in calls), calls
            return dict(role=role, viewport=[width, height], scenario=scenario, api_calls=calls,
                        poll_versions=poll_versions, detail_scroll=dialog_scroll, main_scroll=main_scroll,
                        checks='two 3-second polls update version and progress; modal focus/scroll and page rectangles preserved')
        main.evaluate('(el) => { el.scrollTop = 0; }')

        results.get_by_role('button', name='折叠成果面板', exact=True).click()
        expect(page.locator('#project-results')).to_have_count(0)
        expect(results.get_by_role('button', name='展开成果面板', exact=True)).to_be_visible()
        no_overflow(page)
        results.get_by_role('button', name='展开成果面板', exact=True).click()
        expect(page.locator('#project-results')).to_be_visible()
        page.locator('.pd-project-facts button').first.click()
        panel = page.get_by_role('complementary', name='项目资料核对面板', exact=True)
        expect(panel).to_be_visible()
        expect(results).to_be_hidden()
        expect(panel.get_by_role('combobox', name='选择解析资料', exact=True)).to_contain_text(FIXTURE.SOURCE_NAME)
        no_overflow(page)
        bounds = panel.bounding_box()
        assert bounds and bounds['x'] >= 0 and bounds['y'] >= 0
        assert bounds['x'] + bounds['width'] <= width + 1
        assert bounds['y'] + bounds['height'] <= height + 1
        page.screenshot(path=str(OUTPUT / f'{prefix}-sources.png'))
        panel.get_by_role('button', name='关闭核对面板', exact=True).click()
        expect(panel).to_have_count(0)
        expect(results).to_be_visible()

        guard_dialogs = []
        if role == 'general_manager' and width == 1920 and not automatic:
            page.locator('.pd-project-facts button').nth(1).click()
            expect(panel).to_be_visible()
            reason = panel.get_by_role('textbox', name='核对依据 1', exact=True)
            draft_text = '查看处理详情前必须保留的隔离核对草稿'
            reason.fill(draft_text)

            def reject_guard(dialog):
                guard_dialogs.append(dict(type=dialog.type, message=dialog.message, action='dismiss'))
                dialog.dismiss()

            page.on('dialog', reject_guard)
            # The keyboard can reach the top action even when the review pane overlays its visual position.
            trigger.focus()
            trigger.press('Enter')
            expect(progress).to_be_hidden()
            expect(panel).to_be_visible()
            expect(reason).to_have_value(draft_text)
            assert len(guard_dialogs) == 1 and '未保存' in guard_dialogs[0]['message'], guard_dialogs
            page.remove_listener('dialog', reject_guard)

            def accept_guard(dialog):
                guard_dialogs.append(dict(type=dialog.type, message=dialog.message, action='accept'))
                dialog.accept()

            page.on('dialog', accept_guard)
            trigger.focus()
            trigger.press('Enter')
            expect(progress).to_be_visible()
            expect(panel).to_have_count(0)
            assert len(guard_dialogs) == 2, guard_dialogs
            expect(page.locator('dialog:modal')).to_have_count(1)
            page.remove_listener('dialog', accept_guard)
            page.screenshot(path=str(OUTPUT / f'{prefix}-guard-accepted.png'))
            page.keyboard.press('Escape')
            expect(progress).to_be_hidden()
            expect(trigger).to_be_focused()

        if not automatic:
            expected_version = task['version']
            retry.click()
            expect(page.locator('.pd-compact-progress')).to_contain_text('自动恢复')
            assert retry_bodies == [dict(expected_version=expected_version)], retry_bodies
            expect(page.get_by_text(FIRST_TEXT, exact=True)).to_be_visible()
            expect(retry).to_have_count(0)
            page.screenshot(path=str(OUTPUT / f'{prefix}-retry-mocked.png'))
        assert not unexpected, unexpected
        assert not errors, errors
        assert len([call for call in calls if call['method'] != 'GET']) == (0 if automatic else 1), calls
        return dict(role=role, viewport=[width, height], scenario=scenario, api_calls=calls,
                    retry_bodies=retry_bodies, guard_dialogs=guard_dialogs,
                    first_screen=True, horizontal_overflow=False,
                    main_scroll=main_scroll, detail_scroll=dialog_scroll,
                    checks='stable overview/main rectangles; one modal scroll container and node list; keyboard tabs/focus trap; '
                           'Escape/footer/X/backdrop close and restore focus/main scroll; recovery records; isolated retry')
    except Exception:
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
            for role in ('general_manager', 'employee'):
                for width, height in ((1920, 1080), (1440, 900)):
                    for automatic in (False, True):
                        results.append(run_case(browser, role, width, height, automatic))
            results.append(run_case(browser, 'general_manager', 1920, 1080, True, running=True))
        finally:
            browser.close()
    (OUTPUT / 'results.json').write_text(json.dumps(dict(
        scope='All API responses isolated; retry POST version checked and mocked; real writes rejected',
        results=results), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: {len(results)} isolated role/viewport/recovery cases; evidence: {OUTPUT.resolve()}')
