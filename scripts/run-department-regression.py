"""Run company business regressions with fresh local databases and private paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def source_hashes():
    directories = ('services/business/backend', 'services/business/model_gateway', 'services/engineering', 'platform')
    files = {ROOT / 'scripts/run-department-regression.py', ROOT / '.dockerignore',
             ROOT / 'services/business/backend/portal/source_parsers/requirements.txt'}
    files.update(path for path in (ROOT / 'deploy/cloud').rglob('*')
                 if path.is_file() and path.suffix.lower() in {
                     '.py', '.dockerfile', '.yml', '.yaml', '.conf', '.lock', '.sh', '.html', '.md'}
                 or path.is_file() and path.name in {'Caddyfile', '.env.example', '.dockerignore'})
    for directory in directories:
        files.update((ROOT / directory).rglob('*.py'))
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files) if '__pycache__' not in path.parts and '.runtime' not in path.parts}


def prepare_engineering_materials(data_root):
    """Supply a self-contained synthetic library to the actual offline CLI test."""
    from openpyxl import Workbook

    library = data_root / 'library'
    library.mkdir()
    workbook = Workbook()
    materials = workbook.active
    materials.title = '物料主数据'
    materials.append(['物料编码', '设备名称', '单位', '规格状态'])
    materials.append(['SYNTHETIC-001', '配电箱', '台', '合成测试，不用于采购'])
    quotes = workbook.create_sheet('报价记录')
    quotes.append(['物料编码', '项目', '供应商', '单价（元）', '价格类型', '备注'])
    quotes.append(['SYNTHETIC-001', '合成回归测试', '虚构测试供应商', 1000,
                   '设备材料价', '纯测试价格，不用于采购'])
    workbook.save(library / '设备价格库_入库版.xlsx')
    workbook.close()
    for name in ('定额基价库.json', '定额含量库.json', '历史价格库.json'):
        (library / name).write_text('[]', encoding='utf-8')
    (data_root / 'synthetic-materials.json').write_text(json.dumps({
        'synthetic_only': True, 'procurement_use': False,
        'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(library.iterdir())},
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parallel', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.parallel <= 8:
        parser.error('--parallel must be between 1 and 8')
    output = ROOT / '.runtime' / ('department-regression-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    output.mkdir(parents=True, exist_ok=False)
    # Worker configuration requires an existing absolute directory, even when
    # the individual tests substitute the actual cost subprocess.
    (output / 'engineering-data').mkdir()
    prepare_engineering_materials(output / 'engineering-data')
    before = source_hashes()
    env = {key: value for key, value in os.environ.items() if not key.startswith(('PORTAL_', 'PLATFORM_', 'MODEL_GATEWAY_'))}
    env.update(PORTAL_SECRET_KEY=secrets.token_urlsafe(48), PORTAL_DEBUG='1', PORTAL_HTTPS='0',
               PYTHONPATH=os.pathsep.join([str(ROOT / 'services/business'), str(ROOT / 'services/business/backend')]),
               PORTAL_SQLITE_PATH=str(output / 'business.sqlite3'),
               PORTAL_ALLOWED_HOSTS='127.0.0.1,localhost,testserver',
               PORTAL_PRODUCT_DOCUMENT_PYTHON=sys.executable, PORTAL_PRODUCT_PARSER_PYTHON=sys.executable,
               PORTAL_PRODUCT_OFFICE_RENDER_ENABLED='0', PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED='0',
               PLATFORM_JWT_SECRET=secrets.token_urlsafe(48), PYTHONIOENCODING='utf-8',
               PORTAL_ENGINEERING_PYTHON=sys.executable,
               PORTAL_ENGINEERING_COST_CLI=str(ROOT / 'services/engineering/tools/cost_skill.py'),
               PORTAL_ENGINEERING_DATA_ROOT=str(output / 'engineering-data'),
               ENGINEERING_DATA_ROOT=str(output / 'engineering-data'), DISABLE_WEB_LOOKUP='1',
               PORTAL_ENGINEERING_ALLOW_ONLINE='0')
    for name in ('product', 'hr', 'engineering', 'tender'):
        env['PORTAL_' + name.upper() + '_STORAGE_ROOT'] = str(output / (name + '-private'))
    commands = [
        ('business', [sys.executable, str(ROOT / 'services/business/backend/manage.py'), 'test',
                      'portal.tests', '--verbosity', '2', '--parallel', str(args.parallel)]),
        ('platform', [sys.executable, '-m', 'unittest', 'discover', '-s', 'platform/tests', '-v']),
        ('model-gateway', [sys.executable, '-m', 'unittest', 'discover', '-s', 'services/business/model_gateway/tests', '-v']),
        ('cloud-package', [sys.executable, 'deploy/cloud/validate_package.py']),
    ]
    results = []
    for name, command in commands:
        started = time.monotonic()
        with (output / (name + '.log')).open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        text = (output / (name + '.log')).read_text(encoding='utf-8')
        count = re.search(r'Ran (\d+) tests?', text)
        skipped = re.search(r'OK \(skipped=(\d+)\)', text)
        results.append({'name': name, 'exit_code': result.returncode, 'command': command,
                        'elapsed_seconds': round(time.monotonic() - started, 3),
                        'tests': int(count[1]) if count else None,
                        'skipped': int(skipped[1]) if skipped else 0})
        print(name + ': exit ' + str(result.returncode), flush=True)
    (output / 'commands.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    after = source_hashes()
    (output / 'source-evidence.json').write_text(json.dumps({
        'source_unchanged': before == after, 'source_sha256_before': before,
        'source_sha256_after': after, 'external_model_calls': False,
        'database_and_storage': 'isolated', 'results': results,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Evidence: ' + str(output))
    return int(any(result['exit_code'] for result in results) or before != after)


if __name__ == '__main__':
    raise SystemExit(main())
