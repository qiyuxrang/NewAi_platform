"""Reuse existing private model config only in the marked owned local database.

configure registers a dedicated local product route without modifying user/role
grants or original trial files. probe makes exactly one bounded synthetic request
through the existing business permission checks and internal model gateway.
No keys, upstream output or complete environment values are printed or persisted.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('owned_local_dev', ROOT / 'scripts/baichuan/local_dev.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def configure():
    local.ensure_local()
    model = local.helper().model_configuration()
    if not model:
        raise ValueError('No existing private model configuration is present')
    host = urlsplit(model['base_url']).hostname or ''
    if host.endswith(('.invalid', '.example', '.test', '.localhost')) or host in {'localhost', '127.0.0.1'}:
        raise ValueError('No non-placeholder HTTPS upstream is configured')
    secure_path = local.RUNTIME / 'secrets.json'
    secure = local.read_json(secure_path)
    if 'model_gateway' not in secure:
        secure['model_gateway'] = secrets.token_hex(32)
        secure_path.write_text(json.dumps(secure, indent=2), encoding='utf-8')
    flag = local.RUNTIME / 'model-link.json'
    record = {'enabled': True, 'source': '.runtime/company-trial/model.env', 'upstream_probe': 'not_run'}
    if flag.exists():
        flag.write_text(json.dumps(record, indent=2), encoding='utf-8')
    else:
        local.private_json(flag, record)
    application()
    from django.db import transaction
    from portal.models import GatewayModel, ModelRoute, Module, Provider
    with transaction.atomic():
        provider, _ = Provider.objects.get_or_create(code='baichuan-local-existing')
        provider.name = '本地隔离既有模型连接'
        provider.base_url = model['base_url']
        provider.api_key_env = 'PORTAL_MODEL_KEY_PRIMARY'
        provider.protocol = 'openai_chat'
        provider.enabled = True
        provider.full_clean(); provider.save()
        gateway_model, _ = GatewayModel.objects.get_or_create(provider=provider, model_name=model['model_name'])
        gateway_model.name = '隔离开发既有模型'
        gateway_model.enabled = True
        gateway_model.supports_text = True
        gateway_model.supports_vision = model['supports_vision']
        gateway_model.timeout_seconds = min(30, model['timeout_seconds'])
        gateway_model.max_output_tokens = 256
        gateway_model.token_parameter = 'max_tokens'
        gateway_model.full_clean(); gateway_model.save()
        route, created = ModelRoute.objects.get_or_create(code='product_assistant', defaults={
            'name': '本地百川条件理解', 'module': Module.objects.get(code='product'), 'model': gateway_model,
            'enabled': True, 'max_calls_per_minute': 4})
        if not created and route.model.provider_id != provider.pk:
            raise ValueError('Local route is owned by a different provider; refusing overwrite')
        route.model = gateway_model; route.enabled = True; route.full_clean(); route.save()
    print(json.dumps({'configured': True, 'upstream_class': 'https_nonplaceholder', 'source_files_modified': False,
                      'upstream_key_only_in_model_gateway': True, 'probe_calls': 0}))


def application():
    env = local.environment()
    if not local.local_model_enabled():
        raise ValueError('Owned model connection must be configured first')
    for key in list(os.environ):
        if key.startswith(('PORTAL_', 'PLATFORM_', 'MODEL_GATEWAY_', 'COMPANY_TRIAL_')):
            del os.environ[key]
    os.environ.update(env)
    # These scripts are already running: changing PYTHONPATH cannot update their
    # import path. Resolve both repository packages before Django starts.
    sys.path.insert(0, str(ROOT / 'services/business'))
    sys.path.insert(0, str(ROOT / 'services/business/backend'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    import django
    django.setup()
    from django.conf import settings
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3' or Path(settings.DATABASES['default']['NAME']).resolve() != local.RUNTIME / 'portal.sqlite3':
        raise ValueError('Refusing model work outside owned SQLite')


def probe():
    application()
    from portal.models import User, ModelCallLog
    from portal.model_gateway import GatewayError, generate_for_use
    receipt_path = local.RUNTIME / 'model-probe.json'
    if receipt_path.exists():
        raise ValueError('A bounded probe receipt already exists; refusing implicit repeated remote call')
    before = ModelCallLog.objects.count()
    record = {'kind': 'one_synthetic_public_prompt', 'budget_calls': 1, 'success': False}
    user = User.objects.get(username='baichuan-dev-product')
    try:
        value = generate_for_use(user, 'product_assistant', [{'role': 'user', 'content': 'Reply with OK.'}])
        record.update(success=bool(value.get('content', '').strip()), prompt_tokens=value.get('prompt_tokens'),
                      completion_tokens=value.get('completion_tokens'), duration_ms=value.get('duration_ms'))
    except GatewayError as error:
        record.update(error_code=error.code, status=error.status)
        # No exception text or vendor body: these could echo credentials/prompts.
    record['model_call_log_delta'] = ModelCallLog.objects.count() - before
    local.private_json(receipt_path, record)
    print(json.dumps(record, indent=2))


def activate():
    """Restore the existing bounded model limits only after the single probe."""
    receipt = local.read_json(local.RUNTIME / 'model-probe.json')
    if receipt.get('success') is not True or receipt.get('model_call_log_delta') != 1:
        raise ValueError('A successful single-call probe is required before activation')
    application()
    from portal.models import GatewayModel
    model = local.helper().model_configuration()
    row = GatewayModel.objects.get(provider__code='baichuan-local-existing')
    row.max_output_tokens = min(4096, model['max_output_tokens'])
    row.timeout_seconds = min(60, model['timeout_seconds'])
    row.full_clean(); row.save(update_fields=['max_output_tokens', 'timeout_seconds', 'updated_at'])
    flag_path = local.RUNTIME / 'model-link.json'
    flag = local.read_json(flag_path)
    flag['upstream_probe'] = 'success'
    flag_path.write_text(json.dumps(flag, indent=2), encoding='utf-8')
    print(json.dumps({'activated': True, 'extra_network_calls': 0, 'max_output_tokens': row.max_output_tokens,
                      'timeout_seconds': row.timeout_seconds}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'probe', 'activate'))
    args = parser.parse_args()
    if args.command == 'configure':
        configure()
    elif args.command == 'probe':
        probe()
    else:
        activate()
