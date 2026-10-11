"""Seed synthetic, non-default company trial accounts in explicitly selected DBs."""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/business/backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
runtime = Path(os.environ['COMPANY_TRIAL_ROOT']).resolve()
if runtime != ROOT / '.runtime/company-trial':
    raise ValueError('Trial seed requires the owned runtime directory.')
if (os.environ.get('PORTAL_DB_NAME') or
        Path(os.environ.get('PORTAL_SQLITE_PATH', '')).resolve() != runtime / 'portal.sqlite3' or
        os.environ.get('PLATFORM_DATABASE_URL') != 'sqlite+aiosqlite:///' + (runtime / 'platform.sqlite3').as_posix()):
    raise ValueError('Trial seed refuses databases outside the isolated runtime.')
import django
django.setup()
from django.core.management import call_command
from portal.models import Role, User

credentials = json.loads((runtime / 'accounts.json').read_text(encoding='utf-8'))
call_command('migrate', interactive=False)
call_command('seed_portal')
for account in credentials['accounts']:
    user = User.objects.create_user(username=account['username'], password=account['password'],
        display_name='合成测试 ' + account['label'], must_change_password=False,
        department_code=account.get('department') or '',
        is_staff=account['role'] == 'platform_admin')
    user.roles.set(Role.objects.filter(code=account['role']))
    account['portal_user_id'] = user.pk
(runtime / 'accounts.json').write_text(json.dumps(credentials, ensure_ascii=False, indent=2), encoding='utf-8')

sys.path.insert(0, str(ROOT / 'platform'))
from app.db.engine import engine, async_session
from app.db.models import Base, User as PlatformUser
from app.auth.service import hash_password


async def seed():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        for account in credentials['accounts']:
            if account['role'] == 'finance':
                continue  # Existing platform supports only three employee departments.
            session.add(PlatformUser(username=account['username'], email=account['username'] + '@synthetic.test',
                password_hash=hash_password(account['password']),
                role='admin' if account['role'] == 'platform_admin' else 'user',
                business_role='general_manager' if account['role'] == 'general_manager' else
                    ('employee' if account.get('department') else 'unassigned'),
                department_code=account.get('department'), portal_user_id=account['portal_user_id']))
        await session.commit()
    await engine.dispose()


asyncio.run(seed())
print('Synthetic trial accounts created. Credentials retained in the private accounts.json; no model configured.')
