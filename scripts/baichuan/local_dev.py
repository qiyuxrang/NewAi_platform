"""Owned, loopback-only Baichuan development services with fresh isolated DBs.

Usage: python scripts/baichuan/local_dev.py start|status|stop|migrate
Existing trial/production databases and accounts are never imported or modified.
Development credentials stay in ignored .runtime/baichuan-ai-local/accounts.json.
"""
import argparse
import asyncio
from contextlib import contextmanager
import importlib.util
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

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime/baichuan-ai-local'
IDENTITY = 'baichuan_ai_isolated_local_v1'
EMPTY_LABEL = '隔离开发库，尚未连接现有企业资料'
SOURCE_LABEL = '本地源表资料，历史官网补查未恢复'


@contextmanager
def service_lock():
    """Serialize helpers without trusting a stale PID/lock-file claim."""
    with (RUNTIME / 'services.lock').open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            if stream.read(1) == b'':
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def private_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    if os.name == 'nt':
        principal = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', principal + ':(F)'],
                       check=True, stdout=subprocess.DEVNULL)
    else:
        path.chmod(0o600)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_state(runtime=None):
    """A source receipt identifies local restoration, never historical deployment.

    The importer writes this private receipt only after a successful transaction.
    Merely locating an Excel file or an incomplete/invalid receipt changes no label.
    """
    path = (runtime or RUNTIME) / 'source-status.json'
    state = {'dataset_kind': 'isolation', 'source_kind': 'unconnected',
             'source_connected': False, 'local_source_only': False,
             'historical_enrichment_restored': False, 'environment_label': EMPTY_LABEL}
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return state
    if not isinstance(value, dict):
        return state
    count = value.get('imported_company_count')
    digest = value.get('source_sha256')
    if (value.get('source_kind') != 'local_original_excel'
            or value.get('import_completed') is not True
            or type(count) is not int or count <= 0
            or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest)
            or value.get('historical_enrichment_restored', False) is not False):
        return state
    return {**state, 'source_kind': 'local_original_excel', 'source_connected': True,
            'local_source_only': True, 'environment_label': SOURCE_LABEL,
            'imported_company_count': count, 'source_sha256': digest.lower()}


def environment():
    if RUNTIME.resolve() != RUNTIME or RUNTIME.is_symlink():
        raise ValueError('Local runtime must not redirect outside its owned path')
    marker = read_json(RUNTIME / 'environment.json')
    if marker.get('kind') != IDENTITY:
        raise ValueError('Local environment ownership marker is invalid')
    secure = read_json(RUNTIME / 'secrets.json')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PORTAL_', 'PLATFORM_', 'MODEL_GATEWAY_', 'COMPANY_TRIAL_'))}
    env.update(PORTAL_DEBUG='1', PORTAL_HTTPS='0', PORTAL_SECRET_KEY=secure['portal'],
        PORTAL_SQLITE_PATH=str(RUNTIME / 'portal.sqlite3'),
        PORTAL_ALLOWED_HOSTS='127.0.0.1,localhost,testserver',
        PORTAL_CSRF_TRUSTED_ORIGINS='http://127.0.0.1:18100,http://127.0.0.1:18080,http://127.0.0.1:13180',
        PORTAL_BAICHUAN_SCOPE_CONFIRMED='1', PORTAL_BAICHUAN_READ_ROLE_CODES='product,general_manager',
        PORTAL_BAICHUAN_WRITE_ROLE_CODES='product,general_manager', PORTAL_AGENT_ENABLED='0',
        PORTAL_BAICHUAN_ASSISTANT_ENABLED='1', PORTAL_BAICHUAN_ASSISTANT_SCOPE='baichuan-ai-local',
        PORTAL_BAICHUAN_ASSISTANT_LOCAL_GRAMMAR='1',
        PORTAL_BAICHUAN_ASSISTANT_UNLIMITED_QUERY_MODELS='1',
        # AI-D28: this source-restored local catalog was explicitly confirmed by its owner.
        PORTAL_BAICHUAN_TRUST_LEGACY_QUALIFICATIONS='1' if source_state()['source_connected'] else '0',
        PORTAL_BAICHUAN_STORAGE_ROOT=str(RUNTIME / 'baichuan-private'),
        PORTAL_BAICHUAN_ENVIRONMENT_LABEL=source_state()['environment_label'],
        PORTAL_BAICHUAN_DATASET_KIND='isolation',
        PORTAL_PRODUCT_PARSER_PYTHON=str(ROOT / '.runtime/company-test/cloud-ocr/Scripts/python.exe'),
        PORTAL_PRODUCT_P1_ENABLED='1', PORTAL_PRODUCT_MODEL_CALLS_ALLOWED='0',
        PORTAL_PRODUCT_OFFICE_RENDER_ENABLED='0', PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED='0',
        PORTAL_ENGINEERING_ALLOW_ONLINE='0', DISABLE_WEB_LOOKUP='1',
        PLATFORM_DATABASE_URL='sqlite+aiosqlite:///' + (RUNTIME / 'platform.sqlite3').as_posix(),
        PLATFORM_JWT_SECRET=secure['platform'], PLATFORM_PORTAL_BASE_URL='http://127.0.0.1:18100',
        PLATFORM_SHARED_OPENCLAW_ENABLED='false', PLATFORM_CORS_ORIGINS='http://127.0.0.1:13180',
        PYTHONIOENCODING='utf-8')
    for namespace in ('PRODUCT', 'HR', 'ENGINEERING', 'TENDER'):
        env['PORTAL_' + namespace + '_STORAGE_ROOT'] = str(RUNTIME / (namespace.lower() + '-private'))
    if local_model_enabled():
        env.update(PORTAL_MODEL_GATEWAY_URL='http://127.0.0.1:18412',
            PORTAL_MODEL_GATEWAY_ALLOWED_URLS='http://127.0.0.1:18412',
            PORTAL_MODEL_GATEWAY_TOKEN=secure['model_gateway'], PORTAL_PRODUCT_MODEL_CALLS_ALLOWED='1')
    return env


def local_model_enabled():
    path = RUNTIME / 'model-link.json'
    return path.is_file() and read_json(path).get('enabled') is True


def ensure_local():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    marker = RUNTIME / 'environment.json'
    if not marker.exists():
        if any(RUNTIME.iterdir()):
            raise ValueError('Unowned runtime is not empty; refusing initialization')
        private_json(marker, {'kind': IDENTITY, 'synthetic': True, 'real_company_source_connected': False})
    if not (RUNTIME / 'secrets.json').exists():
        private_json(RUNTIME / 'secrets.json', {'portal': secrets.token_hex(32), 'platform': secrets.token_hex(32)})
    if not (RUNTIME / 'accounts.json').exists():
        private_json(RUNTIME / 'accounts.json', {'synthetic': True, 'accounts': [
            {'username': 'baichuan-dev-' + role, 'password': 'Dev!' + secrets.token_hex(16), 'role': role}
            for role in ('product', 'general_manager')]})


def seed():
    """Only this process environment's owned new SQLite files are writable."""
    env = environment()
    if os.environ.get('PORTAL_SQLITE_PATH') != env['PORTAL_SQLITE_PATH'] or os.environ.get('PORTAL_DB_NAME'):
        raise ValueError('Seed refuses a database outside the owned isolated configuration')
    sys.path.insert(0, str(ROOT / 'services/business/backend'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    import django
    django.setup()
    from django.core.management import call_command
    from portal.models import Role, User
    call_command('migrate', interactive=False, verbosity=1)
    call_command('seed_portal')
    accounts = read_json(RUNTIME / 'accounts.json')['accounts']
    for account in accounts:
        user, created = User.objects.get_or_create(username=account['username'], defaults={
            'display_name': '隔离开发 ' + account['role'], 'must_change_password': False,
            'department_code': 'product' if account['role'] == 'product' else ''})
        if created:
            user.set_password(account['password'])
            user.save(update_fields=['password'])
            user.roles.set(Role.objects.filter(code=account['role']))
        account['portal_user_id'] = user.pk
    sys.path.insert(0, str(ROOT / 'platform'))
    from sqlalchemy import select
    from app.db.engine import engine, async_session
    from app.db.models import Base, User as PlatformUser
    from app.auth.service import hash_password

    async def platform_seed():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            for account in accounts:
                existing = await session.scalar(select(PlatformUser).where(PlatformUser.username == account['username']))
                if existing is None:
                    session.add(PlatformUser(username=account['username'], email=account['username']+'@synthetic.test',
                        password_hash=hash_password(account['password']), role='user',
                        business_role='general_manager' if account['role'] == 'general_manager' else 'employee',
                        department_code='product' if account['role'] == 'product' else None,
                        portal_user_id=account['portal_user_id']))
            await session.commit()
        await engine.dispose()
    asyncio.run(platform_seed())
    print('Owned local schema ready; no companies imported; existing passwords retained.')


def helper():
    spec = importlib.util.spec_from_file_location('company_trial_helpers', ROOT / 'scripts/company-trial.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def owned(record):
    try:
        return helper().process_identity(record['pid']) == record['identity']
    except (subprocess.SubprocessError, OSError, RuntimeError):
        return False


def services():
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is unavailable')
    commands = [
        ('portal', 18100, [sys.executable, str(ROOT / 'services/business/backend/manage.py'), 'runserver', '127.0.0.1:18100', '--noreload']),
        ('gateway', 18080, [sys.executable, str(ROOT / 'scripts/company-trial-gateway.py')]),
        ('baichuan-worker', 0, [sys.executable, str(ROOT / 'services/business/backend/manage.py'), 'run_baichuan_worker', '--poll-seconds', '0.1']),
        ('frontend', 13180, [node, str(ROOT / 'scripts/baichuan/local_frontend.mjs')])]
    if local_model_enabled():
        commands.insert(0, ('model-gateway', 18412, [sys.executable, '-m', 'uvicorn',
            'model_gateway.app:app', '--host', '127.0.0.1', '--port', '18412', '--no-access-log']))
    return commands


def service_environment(name):
    env = environment()
    if name in {'portal', 'baichuan-worker'}:
        # manage.py adds backend, but public-page/RSS transports also import the
        # sibling model_gateway package. Never inherit an external module path.
        env['PYTHONPATH'] = str(ROOT / 'services/business')
    if name == 'model-gateway':
        model = helper().model_configuration()
        if not model:
            raise ValueError('Owned model link requires existing validated private configuration')
        env.update(PYTHONPATH=str(ROOT / 'services/business'),
            MODEL_GATEWAY_SERVICE_TOKEN=env['PORTAL_MODEL_GATEWAY_TOKEN'],
            MODEL_GATEWAY_ALLOWED_BASE_URLS=model['base_url'], MODEL_GATEWAY_CONCURRENCY='1',
            PORTAL_MODEL_KEY_PRIMARY=model['key'])
    return env


def start():
    ensure_local()
    state_path = RUNTIME / 'processes.json'
    records = read_json(state_path) if state_path.exists() else []
    for name, port, command in services():
        matches = [record for record in records if record['name'] == name and owned(record)]
        if matches:
            if matches[0].get('command') != command:
                raise ValueError('Owned command changed; stop local services before restarting')
            continue
        with socket.socket() as check:
            check.bind(('127.0.0.1', port))  # Never reuse somebody else's listener.
    # Migrate only the new explicit local database, even on repeated start.
    subprocess.run([sys.executable, str(Path(__file__)), '_seed'], env=environment(), cwd=ROOT, check=True)
    launched = []
    try:
        for name, port, command in services():
            if any(record['name'] == name and owned(record) for record in records):
                continue
            with (RUNTIME / (name + '.log')).open('ab') as log:
                child = subprocess.Popen(command, env=service_environment(name), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            launched.append(child)
            record = {'name': name, 'pid': child.pid, 'command': command,
                      'identity': helper().process_identity(child.pid)}
            records = [old for old in records if old['name'] != name] + [record]
            state_path.write_text(json.dumps(records, indent=2), encoding='utf-8')
        ready_urls = ('http://127.0.0.1:18100/health/', 'http://127.0.0.1:18080/api/ping', 'http://127.0.0.1:13180/login')
        if local_model_enabled():
            ready_urls += ('http://127.0.0.1:18412/health',)
        for url in ready_urls:
            deadline = time.monotonic() + 45
            while True:
                try:
                    with urlopen(url, timeout=3) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('Local health failed: ' + url + '; inspect owned runtime logs')
                time.sleep(0.5)
        print(source_state()['environment_label'])
        print('http://127.0.0.1:13180/departments/product/baichuan')
        print('Private development credentials: .runtime/baichuan-ai-local/accounts.json')
    except Exception:
        for child in launched:
            if child.poll() is None:
                child.terminate()
        raise


def stop():
    environment()  # Confirm ownership before considering a PID.
    path = RUNTIME / 'processes.json'
    if not path.exists():
        return
    records = read_json(path)
    for record in records:
        if owned(record):
            if os.name == 'nt':
                subprocess.run(['taskkill.exe', '/PID', str(record['pid']), '/T', '/F'],
                               check=True, stdout=subprocess.DEVNULL)
            else:
                import signal
                os.kill(record['pid'], signal.SIGTERM)
    path.unlink()
    print('Owned local processes stopped; all databases retained.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('start', 'stop', 'status', 'migrate', '_seed'))
    args = parser.parse_args()
    if args.command == 'start':
        ensure_local()
        with service_lock():
            start()
    elif args.command == '_seed':
        seed()
    elif args.command == 'migrate':
        ensure_local()
        with service_lock():
            subprocess.run([sys.executable, str(Path(__file__)), '_seed'], env=environment(), cwd=ROOT, check=True)
    elif args.command == 'stop':
        environment()
        with service_lock():
            stop()
    else:
        environment()
        state = RUNTIME / 'processes.json'
        print(json.dumps({'kind': IDENTITY, **source_state(),
            'services': [{'name': item['name'], 'owned_running': owned(item)}
                         for item in read_json(state)] if state.exists() else []}, indent=2))
