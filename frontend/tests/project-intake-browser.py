"""Run against the frontend: python frontend/tests/project-intake-browser.py [base URL] [evidence dir].

Uses isolated API fixtures, rejects every API write, and never submits the form.
"""
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:3080'
output = Path(sys.argv[2] if len(sys.argv) > 2 else 'output/project-intake-browser')
output.mkdir(parents=True, exist_ok=True)
layout_failures = []
overview = dict(
    as_of='2026-10-15T00:00:00Z', scope='authorized_projects', projects=[],
    metrics=dict(active=0, review=0, generation=0, completed_month=0),
    pagination=dict(page=1, page_size=20, total=0, pages=0), recent_projects=[],
    todos=[], recent_outputs=[], reviewers=[], templates=[],
    capabilities=dict(model_generation=True, retrieval=True, formal_release=False,
                      office_preview=False, upload_extensions=['.xlsx', '.docx', '.pdf'],
                      upload_max_bytes=4096))


def file(name, size):
    return dict(name=name, mimeType='application/octet-stream', buffer=b'x' * size)


def bounds(page, width, height):
    if not page.evaluate('document.documentElement.scrollWidth <= innerWidth'):
        layout_failures.append(dict(role=role, viewport=[width, height], issue='Outer horizontal overflow'))
    workspace = page.locator('.wb-new-project')
    if not workspace.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'):
        layout_failures.append(dict(role=role, viewport=[width, height], issue='Workspace horizontal overflow'))
    button = page.get_by_role('button', name='开始生成', exact=True)
    box = button.bounding_box()
    box['visible_ratio'] = button.evaluate('''el => new Promise(resolve => {
        const observer = new IntersectionObserver(([entry]) => {observer.disconnect(); resolve(entry.intersectionRatio)});
        observer.observe(el);
    })''')
    if not (box['visible_ratio'] >= 0.99 and box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= width and box['y'] + box['height'] <= height):
        layout_failures.append(dict(role=role, viewport=[width, height], issue='Submit outside viewport', bounds=box))
    return box


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        for role in ('general_manager', 'employee'):
            for width, height in ((1280, 800), (1920, 1080)):
                context = browser.new_context(viewport=dict(width=width, height=height), service_workers='block')
                context.add_init_script("localStorage.setItem('openclaw_access_token','isolated-project-intake-token')")
                unexpected, errors, calls = [], [], []
                user = dict(id='isolated-product-user', username='隔离资料验收', role='user',
                            business_role=role, department_code=None if role == 'general_manager' else 'product',
                            portal_user_id=77, capabilities=['general_manager', 'product', 'engineering', 'hr']
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
                        '/api/product/tasks/': dict(tasks=[]),
                        '/api/product/workspace/': overview,
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
                page.goto(base + '/departments/product/documents?view=new')
                page.wait_for_load_state('networkidle')
                equipment_button = page.get_by_role('button', name='选择设备清单', exact=True)
                background_button = page.get_by_role('button', name='选择背景材料', exact=True)
                expect(equipment_button).to_be_visible()
                expect(background_button).to_be_visible()
                equipment_input = page.locator('#equipment-source')
                background_input = page.get_by_label('选择项目资料文件', exact=True)
                assert background_input.get_attribute('multiple') is not None
                assert equipment_input.get_attribute('accept') == '.xlsx,.docx,.pdf'
                assert background_input.get_attribute('accept') == '.xlsx,.docx,.pdf'
                initial_bounds = bounds(page, width, height)
                page.screenshot(path=str(output / f'{role}-{width}-empty.png'))

                equipment_name = '隔离设备清单.xlsx'
                background_names = ['隔离项目需求.pdf', '隔离现场背景.docx']
                with page.expect_file_chooser() as chooser:
                    equipment_button.click()
                chooser.value.set_files(file(equipment_name, 2048))
                expect(page.get_by_text(equipment_name, exact=True)).to_be_visible()
                expect(page.get_by_text('2.0 KB', exact=True)).to_be_visible()
                with page.expect_file_chooser() as chooser:
                    background_button.click()
                chooser.value.set_files([file(background_names[0], 1024), file(background_names[1], 3072)])
                upload_list = page.get_by_role('list', name='待上传项目资料', exact=True)
                expect(upload_list.locator('li')).to_have_count(2)
                for name, size in zip(background_names, ['1.0 KB', '3.0 KB']):
                    item = upload_list.locator('li').filter(has_text=name)
                    expect(item.get_by_text(name, exact=True)).to_be_visible()
                    expect(item.get_by_text(size, exact=True)).to_be_visible()
                selected_bounds = bounds(page, width, height)
                selected_layout = page.evaluate("""() => Object.fromEntries([
                    '.wb-work-content', '.wb-new-project', '.pd-page-title', '.pd-project-form',
                    '.pd-intake-uploads', '.pd-intake-upload-card', '.pd-intake-dropzone',
                    '.pd-intake-formats', '.pd-optional-project-fields', '.pd-form-footer', '.pd-new-aside'
                ].map(selector => {const el=document.querySelector(selector); const r=el.getBoundingClientRect();
                    return [selector, {x:r.x,y:r.y,width:r.width,height:r.height,
                                      clientWidth:el.clientWidth,scrollWidth:el.scrollWidth}]}))""")
                page.screenshot(path=str(output / f'{role}-{width}-selected.png'))

                # Validate extension, empty content, and size without replacing accepted files.
                for name, size in [('无效设备.exe', 1), ('空白设备.xlsx', 0), ('超限设备.xlsx', 4097)]:
                    equipment_input.set_input_files(file(name, size))
                    expect(page.get_by_role('alert')).to_contain_text('设备清单格式、大小或内容不符合要求')
                    expect(page.get_by_text(equipment_name, exact=True)).to_be_visible()
                for name, size in [('无效背景.exe', 1), ('空白背景.pdf', 0), ('超限背景.pdf', 4097)]:
                    background_input.set_input_files(file(name, size))
                    expect(page.get_by_role('alert')).to_contain_text(name)
                    expect(upload_list.locator('li')).to_have_count(2)

                page.get_by_role('button', name=f'移除 {background_names[0]}', exact=True).click()
                expect(upload_list.locator('li')).to_have_count(1)
                page.get_by_role('button', name='移除设备清单', exact=True).click()
                expect(page.get_by_text(equipment_name, exact=True)).to_have_count(0)

                # Locate the drop target by its input; keep this independent of CSS class names.
                dropzone = equipment_input.locator('xpath=ancestor::*[@class][contains(@class,"dropzone")][1]')
                expect(dropzone).to_have_count(1)
                transfer = page.evaluate_handle("""() => {
                    const data = new DataTransfer();
                    data.items.add(new File(['drag equipment'], '拖拽设备清单.xlsx', {type:'application/octet-stream'}));
                    return data;
                }""")
                dropzone.dispatch_event('dragover', dict(dataTransfer=transfer))
                dropzone.dispatch_event('drop', dict(dataTransfer=transfer))
                transfer.dispose()
                expect(page.get_by_text('拖拽设备清单.xlsx', exact=True)).to_be_visible()
                expect(page.get_by_role('alert')).to_have_count(0)

                long_name = '项目背景' + '超长材料名称用于验证上传列表不会挤出页面' * 5 + '.docx'
                background_input.set_input_files(file(long_name, 512))
                expect(upload_list.locator('li')).to_have_count(2)
                bounds(page, width, height)
                page.screenshot(path=str(output / f'{role}-{width}-long-name.png'))
                long_name_layout = page.locator('.wb-new-project').evaluate('''root => [root, ...root.querySelectorAll('*')]
                    .filter(el => el.scrollWidth > el.clientWidth + 1 || el.matches('.pd-upload-list li, .pd-upload-list li > div')).map(el => {
                        const r=el.getBoundingClientRect(), s=getComputedStyle(el);
                        return {tag:el.tagName, className:el.className, clientWidth:el.clientWidth,
                            scrollWidth:el.scrollWidth, x:r.x,width:r.width,
                            minWidth:s.minWidth,display:s.display,overflowX:s.overflowX};
                    })''')
                page.get_by_role('button', name=f'移除 {long_name}', exact=True).click()
                page.get_by_role('button', name=f'移除 {background_names[1]}', exact=True).click()
                expect(upload_list).to_have_count(0)
                page.get_by_role('button', name='移除设备清单', exact=True).click()
                assert not unexpected, unexpected
                assert not errors, errors
                assert all(call['method'] == 'GET' for call in calls), calls
                results.append(dict(role=role, viewport=[width, height], initial_submit_bounds=initial_bounds,
                                    selected_submit_bounds=selected_bounds, selected_layout=selected_layout,
                                    long_name_layout=long_name_layout, api_calls=calls,
                                    checks='two picker buttons; equipment and multiple backgrounds; names/sizes; removals; extension/empty/size validation; equipment drop; long filename; visible submit; no outer horizontal overflow'))
                context.close()
    finally:
        browser.close()

(output / 'results.json').write_text(json.dumps(dict(
    scope='Isolated API fixtures only; no form submission or live project writes', results=results,
    layout_failures=layout_failures),
    ensure_ascii=False, indent=2), encoding='utf-8')
assert not layout_failures, layout_failures
print(f'PASS: {len(results)} desktop/role combinations; evidence: {output.resolve()}')
