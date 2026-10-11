"""Configure or explicitly probe the owned company trial model, without key arguments.

Run with the Python runtime used to prepare the trial:
    python scripts/company-model.py configure
    python scripts/company-model.py probe
Configure validates and writes local model routes only; probe makes one billable
connection test through the independent model gateway. Neither command migrates
databases, creates users, or changes role/user/document grants.
Materials remain in source_only_preview mode; this CLI does not configure RAG.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_CODE = 'company-qwen'
KEY_VARIABLE = 'PORTAL_MODEL_KEY_PRIMARY'
ROUTES = {
    'product': ('product_assistant', 'product_blueprint', 'product_writing', 'product_review'),
    'hr': ('hr_assistant', 'hr_jd_draft', 'hr_resume_parse', 'hr_match_summary', 'hr_resume_extract'),
    'cost': ('engineering_assistant',),
}


def assert_trial_paths(runtime, config_path, env, root=ROOT):
    """Refuse redirected, missing or shared databases before importing Django."""
    expected = Path(root).resolve() / '.runtime/company-trial'
    if Path(runtime).resolve() != expected or Path(config_path).resolve() != expected / 'config.json':
        raise ValueError('Only the owned company trial runtime is allowed.')
    database = expected / 'portal.sqlite3'
    if not database.is_file() or database.resolve() != database or not Path(config_path).is_file():
        raise ValueError('Prepare the trial first; redirected databases are not allowed.')
    if (env.get('PORTAL_DB_NAME') or not env.get('PORTAL_SQLITE_PATH')
            or Path(env['PORTAL_SQLITE_PATH']).resolve() != database
            or env.get('COMPANY_TRIAL_ROOT') != str(expected)
            or env.get('PLATFORM_DATABASE_URL') != 'sqlite+aiosqlite:///' + (expected / 'platform.sqlite3').as_posix()):
        raise ValueError('Refusing a database outside the owned trial runtime.')
    return database


def assert_django_database(databases, expected):
    default = databases.get('default', {})
    if (set(databases) != {'default'} or default.get('ENGINE') != 'django.db.backends.sqlite3'
            or not default.get('NAME') or Path(default['NAME']).resolve() != expected):
        raise ValueError('Django must use only the owned trial SQLite database.')


def safe_model_settings(value):
    """Copy only non-secret metadata and enforce strict model numeric bounds."""
    if not isinstance(value, dict):
        raise ValueError('Configure the private trial model.env first.')
    selected = {field: value.get(field) for field in (
        'base_url', 'model_name', 'supports_vision', 'max_output_tokens', 'timeout_seconds')}
    for field, upper in (('max_output_tokens', 8192), ('timeout_seconds', 600)):
        if type(selected[field]) is not int or not 1 <= selected[field] <= upper:
            raise ValueError('Model token and timeout limits must be bounded integers.')
    if type(selected['supports_vision']) is not bool:
        raise ValueError('Model vision capability must be a boolean.')
    if any(not isinstance(selected[field], str) or not selected[field].strip()
           for field in ('base_url', 'model_name')):
        raise ValueError('Model endpoint and name are required.')
    return selected


def load_application():
    spec = importlib.util.spec_from_file_location('company_trial_model_cli', ROOT / 'scripts/company-trial.py')
    trial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trial)
    # The trial helper performs dotenv validation. The CLI never persists its key.
    model_settings = safe_model_settings(trial.model_configuration())
    config = json.loads(trial.CONFIG.read_text(encoding='utf-8'))
    env = trial.environment(config)
    expected = assert_trial_paths(trial.RUNTIME, trial.CONFIG, env)
    if any(name.startswith('PORTAL_MODEL_KEY_') for name in env):
        raise ValueError('Upstream keys must be restricted to the model gateway process.')
    for name in list(os.environ):
        if name.startswith(('PORTAL_', 'PLATFORM_')):
            del os.environ[name]
    os.environ.update(env)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    sys.path.insert(0, str(ROOT / 'services/business/backend'))
    from django.conf import settings
    assert_django_database(settings.DATABASES, expected)
    import django
    django.setup()
    assert_django_database(settings.DATABASES, expected)
    return model_settings


def configure_model(value):
    from django.db import transaction
    from portal.models import GatewayModel, ModelRoute, Module, Provider

    value = safe_model_settings(value)
    with transaction.atomic():
        modules = {item.code: item for item in Module.objects.filter(code__in=ROUTES)}
        if set(modules) != set(ROUTES) or any(not item.enabled for item in modules.values()):
            raise ValueError('Required trial modules must already exist and be enabled.')
        existing = {item.code: item for item in ModelRoute.objects.select_for_update()
                    .select_related('model__provider', 'module')
                    .filter(code__in=[code for codes in ROUTES.values() for code in codes])}
        for module_code, codes in ROUTES.items():
            for code in codes:
                route = existing.get(code)
                if route and (route.model.provider.code != PROVIDER_CODE or route.module.code != module_code):
                    raise ValueError('An existing model route is owned by another provider or module; no changes saved.')
        provider = Provider.objects.select_for_update().filter(code=PROVIDER_CODE).first()
        provider = provider or Provider(code=PROVIDER_CODE)
        provider.name = '公司试运行千问'
        provider.protocol = Provider.Protocol.OPENAI_CHAT
        provider.base_url = value['base_url']
        provider.api_key_env = KEY_VARIABLE
        provider.enabled = True
        provider.full_clean()
        provider.save()
        matches = list(GatewayModel.objects.select_for_update().filter(
            provider=provider, model_name=value['model_name'])[:2])
        if len(matches) > 1:
            raise ValueError('Duplicate trial models require manual review; no changes saved.')
        model = matches[0] if matches else GatewayModel(provider=provider, model_name=value['model_name'])
        model.name = '公司千问模型'
        model.supports_text = True
        model.supports_vision = value['supports_vision']
        model.max_output_tokens = value['max_output_tokens']
        model.timeout_seconds = value['timeout_seconds']
        model.token_parameter = GatewayModel.TokenParameter.MAX_TOKENS
        model.enabled = True
        model.full_clean()
        model.save()
        for module_code, codes in ROUTES.items():
            for code in codes:
                route = existing.get(code) or ModelRoute(code=code, module=modules[module_code])
                route.name = code
                route.model = model
                route.enabled = True
                route.full_clean()
                route.save()
        # Every default refers to one model row/public_id, including HR parse/match.
        return {'status': 'configured', 'code': 'ok', 'model_public_id': str(model.public_id),
                'routes': sum(len(codes) for codes in ROUTES.values()),
                'materials_mode': 'source_only_preview',
                'supports_vision': model.supports_vision,
                'max_output_tokens': model.max_output_tokens, 'timeout_seconds': model.timeout_seconds}


def probe_model(value):
    from portal.model_gateway import GatewayError, test_connection
    from portal.models import GatewayModel, User

    started = monotonic()
    model = GatewayModel.objects.filter(provider__code=PROVIDER_CODE, model_name=value['model_name'],
                                        enabled=True, provider__enabled=True)
    if model.count() != 1:
        raise ValueError('Configure exactly one trial model before probing.')
    user = User.objects.filter(username='trial-platform_admin', is_active=True).first()
    if user is None or not user.is_platform_admin:
        raise ValueError('The existing trial platform administrator is required.')
    try:
        result = test_connection(user, model.get().pk)
        return {'status': 'success', 'code': 'ok',
                'usage': {'prompt_tokens': result.get('prompt_tokens'),
                          'completion_tokens': result.get('completion_tokens')},
                'duration_ms': max(0, int((monotonic() - started) * 1000))}
    except GatewayError as error:
        return {'status': 'failed', 'code': error.code,
                'usage': {'prompt_tokens': None, 'completion_tokens': None},
                'duration_ms': max(0, int((monotonic() - started) * 1000))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'probe'))
    args = parser.parse_args()
    try:
        value = load_application()
        result = configure_model(value) if args.command == 'configure' else probe_model(value)
    except Exception:
        # Validation/database exceptions can contain submitted values. Never echo
        # exceptions, traceback frames, environment variables or upstream content.
        result = {'status': 'failed', 'code': 'configuration_error'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('configured', 'success') else 1


if __name__ == '__main__':
    sys.exit(main())
