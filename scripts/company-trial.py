"""Start a reproducible, private company-department trial on this workstation.

Uses actual Django and gateway routers with isolated SQLite. An optional private
model configuration enables the model gateway and business workers. Docker, PostgreSQL,
OCR and RAG remain separate acceptance items. No production settings are changed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime/company-trial'
CONFIG = RUNTIME / 'config.json'


def private_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    if os.name == 'nt':
        principal = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', principal + ':(F)'],
                       check=True, stdout=subprocess.DEVNULL)
    else:
        path.chmod(0o600)


def model_configuration():
    """Read only supported private fields; upstream credentials stay out of Django."""
    from dotenv import dotenv_values
    file = RUNTIME / 'model.env'
    if not file.exists():
        return None
    values = dotenv_values(file, interpolate=False)
    required = ('MODEL_BASE_URL', 'MODEL_NAME', 'PORTAL_MODEL_KEY_PRIMARY')
    if not any(values.get(name) for name in required):
        return None
    if not all(isinstance(values.get(name), str) and values[name].strip() for name in required):
        raise ValueError('Private model configuration requires Base URL, model name and key.')
    base = values['MODEL_BASE_URL'].strip()
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == 'https' and bool(parsed.hostname) and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                 and not any(ord(char) <= 32 or ord(char) >= 127 for char in base)
                 and not any(char in base for char in '\\%?#@'))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Model Base URL must be a canonical HTTPS API root on port 443.')
    name = values['MODEL_NAME'].strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', name):
        raise ValueError('Invalid model identifier.')
    key = values['PORTAL_MODEL_KEY_PRIMARY'].strip()
    if any(ord(char) <= 32 or ord(char) >= 127 for char in key):
        raise ValueError('Invalid credential format; credential contents are not displayed.')
    vision = values.get('MODEL_SUPPORTS_VISION', '0')
    if vision not in ('0', '1'):
        raise ValueError('MODEL_SUPPORTS_VISION must be 0 or 1.')
    numbers = {}
    for field, default, maximum in (('MODEL_MAX_OUTPUT_TOKENS', '4096', 8192), ('MODEL_TIMEOUT_SECONDS', '120', 600)):
        value = values.get(field, default)
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 1 <= int(value) <= maximum:
            raise ValueError(field + ' is outside its supported integer range.')
        numbers[field] = int(value)
    return {'base_url': base, 'model_name': name, 'key': key, 'supports_vision': vision == '1',
            'max_output_tokens': numbers['MODEL_MAX_OUTPUT_TOKENS'], 'timeout_seconds': numbers['MODEL_TIMEOUT_SECONDS']}


def environment(config):
    blocked = ('PORTAL_', 'PLATFORM_', 'MODEL_GATEWAY_')
    env = {key: value for key, value in os.environ.items() if not key.startswith(blocked)}
    secure = json.loads((RUNTIME / 'secrets.json').read_text(encoding='utf-8'))
    env.update(PORTAL_DEBUG='1', PORTAL_HTTPS='0', PORTAL_SECRET_KEY=secure['portal'],
        PORTAL_SQLITE_PATH=str(RUNTIME / 'portal.sqlite3'), PORTAL_ALLOWED_HOSTS='127.0.0.1,localhost,testserver',
        PORTAL_CSRF_TRUSTED_ORIGINS='http://127.0.0.1:18100,http://127.0.0.1:18080,http://127.0.0.1:13180',
        PORTAL_PRODUCT_DOCUMENT_PYTHON=config['python'],
        PORTAL_PRODUCT_PARSER_PYTHON=config.get('parser_python', config['python']),
        PORTAL_PRODUCT_OFFICE_RENDER_ENABLED='0', PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED='0',
        PORTAL_AGENT_ENABLED='0', PORTAL_PRODUCT_P1_ENABLED='1', PORTAL_PRODUCT_STORAGE_ROOT=str(RUNTIME / 'product-private'),
        PORTAL_HR_STORAGE_ROOT=str(RUNTIME / 'hr-private'), PORTAL_ENGINEERING_STORAGE_ROOT=str(RUNTIME / 'engineering-private'),
        PORTAL_TENDER_STORAGE_ROOT=str(RUNTIME / 'tender-private'),
        PORTAL_ENGINEERING_PYTHON=config['python'],
        PORTAL_ENGINEERING_COST_CLI=str(ROOT / 'services/engineering/tools/cost_skill.py'),
        PORTAL_ENGINEERING_DATA_ROOT=str(RUNTIME / 'engineering-data'),
        PORTAL_ENGINEERING_ALLOW_ONLINE='0', DISABLE_WEB_LOOKUP='1',
        PLATFORM_DATABASE_URL='sqlite+aiosqlite:///' + (RUNTIME / 'platform.sqlite3').as_posix(),
        PLATFORM_JWT_SECRET=secure['platform'], PLATFORM_PORTAL_BASE_URL='http://127.0.0.1:18100',
        PLATFORM_SHARED_OPENCLAW_ENABLED='false', PLATFORM_CORS_ORIGINS='http://127.0.0.1:13180,http://127.0.0.1:13181',
        COMPANY_TRIAL_ROOT=str(RUNTIME), PYTHONIOENCODING='utf-8',
        NEXT_PUBLIC_API_URL='http://127.0.0.1:18080', VITE_ADMIN_URL='http://127.0.0.1:13181/')
    model = model_configuration()
    if model:
        token = secure.get('model_gateway', '')
        if len(token) < 40:
            raise ValueError('A private model gateway service token must be configured first.')
        env.update(PORTAL_MODEL_GATEWAY_URL='http://127.0.0.1:18410',
                   PORTAL_MODEL_GATEWAY_ALLOWED_URLS='http://127.0.0.1:18410', PORTAL_MODEL_GATEWAY_TOKEN=token,
                   PORTAL_PRODUCT_MODEL_CALLS_ALLOWED='1', PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE='source_only_preview')
    return env


def prepare(args):
    if CONFIG.exists() or (RUNTIME / 'portal.sqlite3').exists():
        raise ValueError('Trial already exists. Use start/status; existing accounts are never overwritten.')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    config = {'python': str(Path(args.python).resolve()), 'node': str(Path(shutil.which(args.node) or args.node).resolve()),
              'infrastructure': 'isolated_sqlite_not_cloud_acceptance'}
    runtime_keys = ['python', 'node']
    parser_python = getattr(args, 'parser_python', None)
    if parser_python:
        config['parser_python'] = str(Path(parser_python).resolve())
        runtime_keys.append('parser_python')
    for key in runtime_keys:
        if not Path(config[key]).is_file():
            raise ValueError('Missing runtime: ' + key)
    private_json(RUNTIME / 'secrets.json', {'portal': secrets.token_hex(32), 'platform': secrets.token_hex(32),
                                          'model_gateway': secrets.token_hex(32)})
    accounts = []
    for role, department, label in [('product', 'product', '产品部'), ('hr', 'hr', '人事部'),
            ('engineering', 'engineering', '工程部'), ('general_manager', None, '总经理'),
            ('platform_admin', None, '管理员')]:
        accounts.append({'username': 'trial-' + role, 'password': 'Trial!' + secrets.token_hex(12),
                         'role': role, 'department': department, 'label': label})
    private_json(RUNTIME / 'accounts.json', {'synthetic': True, 'accounts': accounts})
    subprocess.run([config['python'], str(ROOT / 'scripts/company-trial-seed.py')],
                   env=environment(config), cwd=ROOT, check=True)
    private_json(CONFIG, config)
    print('Trial prepared. Private account file: ' + str(RUNTIME / 'accounts.json'))


def available(port):
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', port))


def materials():
    """Copy only labelled, synthetic inputs; refuse changed existing samples."""
    sources = [('hr', ROOT / '.runtime/company-test/hr/materials'),
               ('engineering', ROOT / '.runtime/company-test/engineering/inputs'),
               ('management', ROOT / '.runtime/company-test/management/http-20261011-153940'),
               ('workbooks', ROOT / '.runtime/company-test/management/workbooks')]
    count = 0
    for name, source in sources:
        if not source.is_dir():
            raise ValueError('Extract the company test package first: ' + str(source))
        target = RUNTIME / 'materials' / name
        target.mkdir(parents=True, exist_ok=True)
        for sample in source.iterdir():
            if sample.suffix.lower() not in {'.txt', '.docx', '.pdf', '.csv', '.xls', '.xlsx'}:
                continue
            content = sample.read_bytes()
            destination = target / sample.name
            if destination.exists():
                if destination.read_bytes() != content:
                    raise ValueError('Existing sample changed; refusing overwrite: ' + destination.name)
            else:
                destination.write_bytes(content)
            count += 1
    library = RUNTIME / 'engineering-data/library'
    library.mkdir(parents=True, exist_ok=True)
    for name in ('设备价格库_入库版.xlsx', '定额基价库.json', '定额含量库.json', '历史价格库.json'):
        source = ROOT / '.runtime/company-test/engineering/data/library' / name
        destination = library / name
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise ValueError('Existing synthetic library changed; refusing overwrite.')
        if not destination.exists():
            shutil.copy2(source, destination)
    print('Synthetic materials ready: ' + str(RUNTIME / 'materials') + ' (' + str(count) + ' files)')


def process_identity(pid):
    if os.name != 'nt':
        return {'start_ticks': (Path('/proc') / str(pid) / 'stat').read_text().split()[21]}
    code = "$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:TRIAL_PID); if ($p) { @{created=$p.CreationDate.ToFileTimeUtc().ToString(); executable=$p.ExecutablePath; command=$p.CommandLine} | ConvertTo-Json -Compress }"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code],
        env={**os.environ, 'TRIAL_PID': str(pid)}, capture_output=True, text=True,
        check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if not result.stdout.strip():
        raise RuntimeError('Trial process exited during startup: ' + str(pid))
    return json.loads(result.stdout)


def start(config, backend_only=False):
    model = model_configuration()
    ports = (18100, 18080) if backend_only else (18100, 18080, 13180, 13181)
    for port in ports + ((18410,) if model else ()):
        available(port)
    env = environment(config)
    commands = [
        ('portal', [config['python'], str(ROOT / 'services/business/backend/manage.py'), 'runserver', '127.0.0.1:18100', '--noreload']),
        ('gateway', [config['python'], str(ROOT / 'scripts/company-trial-gateway.py')]),
        ('engineering-worker', [config['python'], str(ROOT / 'services/business/backend/manage.py'), 'run_engineering_worker']),
        ('frontend', [config['node'], str(ROOT / 'scripts/company-trial-frontend.mjs')]),
        ('admin', [config['node'], str(ROOT / 'manage_front/node_modules/next/dist/bin/next'), 'dev', '--hostname', '127.0.0.1', '--port', '13181']),
    ]
    if model:
        commands.insert(0, ('model-gateway', [config['python'], '-m', 'uvicorn', 'model_gateway.app:app',
                          '--host', '127.0.0.1', '--port', '18410', '--no-access-log']))
        commands.append(('hr-worker', [config['python'], str(ROOT / 'services/business/backend/manage.py'),
                                      'run_hr_worker', '--concurrency', '1']))
        commands.append(('product-worker', [config['python'], str(ROOT / 'services/business/backend/manage.py'),
                                           'run_product_worker']))
    if backend_only:
        commands = [(name, command) for name, command in commands if name not in ('frontend', 'admin')]
    children = []
    handles = []
    try:
        for name, command in commands:
            service_env = env
            if name == 'model-gateway':
                service_env = {**env, 'PYTHONPATH': str(ROOT / 'services/business'),
                               'MODEL_GATEWAY_SERVICE_TOKEN': env['PORTAL_MODEL_GATEWAY_TOKEN'],
                               'MODEL_GATEWAY_ALLOWED_BASE_URLS': model['base_url'],
                               'MODEL_GATEWAY_CONCURRENCY': '2', 'PORTAL_MODEL_KEY_PRIMARY': model['key']}
            log = (RUNTIME / (name + '.log')).open('ab')
            proc = subprocess.Popen(command, env=service_env, cwd=ROOT / 'manage_front' if name == 'admin' else ROOT,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            log.close()
            handles.append(proc)
            children.append({'name': name, 'pid': proc.pid, 'command': command,
                             'identity': process_identity(proc.pid)})
            (RUNTIME / 'processes.json').write_text(json.dumps(children, indent=2), encoding='utf-8')
        ready_urls = ('http://127.0.0.1:18100/health/', 'http://127.0.0.1:18080/api/ping')
        if not backend_only:
            ready_urls += ('http://127.0.0.1:13180/login', 'http://127.0.0.1:13181/login')
        if model:
            ready_urls += ('http://127.0.0.1:18410/health',)
        for url in ready_urls:
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urlopen(url, timeout=3) as response:
                        if response.status == 200:
                            break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Startup failed; inspect private runtime logs: ' + url) from None
                    time.sleep(0.5)
        print('Backend ready: http://127.0.0.1:18080 | Portal http://127.0.0.1:18100/admin/' if backend_only else
              'Workspace http://127.0.0.1:13180 | Admin http://127.0.0.1:13181 | Portal http://127.0.0.1:18100/admin/')
    except Exception:
        stop()
        for proc in handles:
            if proc.poll() is None:
                proc.terminate()  # The owned Popen handle cannot target a reused PID.
        raise


def stop():
    file = RUNTIME / 'processes.json'
    if not file.exists():
        return
    for record in json.loads(file.read_text(encoding='utf-8')):
        # Prove ownership via exact executable/command line before stopping a PID.
        if os.name == 'nt':
            identity = record.get('identity')
            if not identity:
                raise ValueError('Missing process identity; refusing to stop an unverified PID.')
            code = "function Stop-OwnedTree([int]$ownedId) { foreach ($child in (Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$ownedId))) { Stop-OwnedTree $child.ProcessId }; Stop-Process -Id $ownedId -ErrorAction SilentlyContinue }; $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$env:TRIAL_PID); if ($p) { if ($p.CreationDate.ToFileTimeUtc().ToString() -ne $env:TRIAL_CREATED -or $p.ExecutablePath -ne $env:TRIAL_EXE -or $p.CommandLine -cne $env:TRIAL_COMMAND) { throw 'Trial process identity mismatch; refusing stop' }; Stop-OwnedTree $p.ProcessId }"
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code],
                env={**os.environ, 'TRIAL_PID': str(record['pid']), 'TRIAL_CREATED': identity['created'],
                     'TRIAL_EXE': identity['executable'], 'TRIAL_COMMAND': identity['command']},
                check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            command = Path('/proc') / str(record['pid']) / 'cmdline'
            if command.exists() and record['command'][1].encode() in command.read_bytes().split(b'\0') and process_identity(record['pid']) == record['identity']:
                os.kill(record['pid'], signal.SIGTERM)
    file.unlink()
    print('Owned trial processes stopped; databases and evidence retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'materials', 'start', 'status', 'stop'))
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--parser-python', help='Optional Python interpreter for product document parsing.')
    parser.add_argument('--node', default='node')
    parser.add_argument('--backend-only', action='store_true', help='Start only the API, model gateway and business workers.')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
    elif args.command == 'stop':
        stop()
    elif args.command == 'materials':
        if not CONFIG.exists():
            raise ValueError('Prepare the private trial environment before copying materials.')
        materials()
    elif args.command == 'status':
        print('Credentials: ' + str(RUNTIME / 'accounts.json'))
        print('Runtime: ' + str(CONFIG))
    else:
        start(json.loads(CONFIG.read_text(encoding='utf-8')), backend_only=args.backend_only)
