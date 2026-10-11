"""Offline CLI tests. Only a temporary SQLite database is created/migrated.

Run: python scripts/test-company-model.py
Never loads trial config, credentials or model.env, and never contacts a service.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('company_model_test_subject', ROOT / 'scripts/company-model.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
VALUE = {'base_url': 'https://example.invalid/v1', 'model_name': 'synthetic-qwen',
         'supports_vision': False, 'max_output_tokens': 4096, 'timeout_seconds': 120}


class GuardTests(unittest.TestCase):
    def test_rejects_unsafe_numeric_values(self):
        for field in ('timeout_seconds', 'max_output_tokens'):
            for value in (True, False, 0, -1, '120', 1.5, float('nan'), 99999):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    subject.safe_model_settings({**VALUE, field: value})

    def test_discards_key_and_rejects_nonboolean_capability(self):
        self.assertEqual(subject.safe_model_settings({**VALUE, 'key': 'synthetic-only'}), VALUE)
        with self.assertRaises(ValueError):
            subject.safe_model_settings({**VALUE, 'supports_vision': 'false'})

    def test_owned_paths_and_database_redirects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime = root / '.runtime/company-trial'
            runtime.mkdir(parents=True)
            config = runtime / 'config.json'
            config.write_text('{}', encoding='utf-8')
            database = runtime / 'portal.sqlite3'
            database.touch()
            env = {'PORTAL_SQLITE_PATH': str(database), 'COMPANY_TRIAL_ROOT': str(runtime),
                   'PLATFORM_DATABASE_URL': 'sqlite+aiosqlite:///' + (runtime / 'platform.sqlite3').as_posix()}
            self.assertEqual(subject.assert_trial_paths(runtime, config, env, root), database)
            for changed in ({**env, 'PORTAL_DB_NAME': 'shared'},
                            {**env, 'PORTAL_SQLITE_PATH': str(root / 'shared.sqlite3')},
                            {**env, 'PLATFORM_DATABASE_URL': 'postgres://shared'},
                            {**env, 'COMPANY_TRIAL_ROOT': str(root)}):
                with self.assertRaises(ValueError):
                    subject.assert_trial_paths(runtime, config, changed, root)
            database.unlink()
            with self.assertRaises(ValueError):
                subject.assert_trial_paths(runtime, config, env, root)

    def test_actual_django_database_guard(self):
        expected = ROOT / '.runtime/company-trial/portal.sqlite3'
        valid = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': expected}}
        subject.assert_django_database(valid, expected)
        for invalid in ({'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': expected}},
                        {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
                        {**valid, 'shared': valid['default']}):
            with self.assertRaises(ValueError):
                subject.assert_django_database(invalid, expected)


class IsolatedDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        sys.path.insert(0, str(ROOT / 'services/business/backend'))
        # Use a standalone settings object, with no trial files or inherited DB env.
        from django.conf import settings
        settings.configure(SECRET_KEY='synthetic-test-secret-' * 3, DEBUG=True, USE_TZ=True,
            BASE_DIR=Path(cls.temp.name),
            INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'portal'],
            AUTH_USER_MODEL='portal.User', DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
            DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3',
                                  'NAME': str(Path(cls.temp.name) / 'test.sqlite3')}},
            MODEL_PROVIDER_LOCAL_HTTP=False)
        import django
        django.setup()
        from django.db import connections
        cls.addClassCleanup(connections.close_all)
        from django.core.management import call_command
        call_command('migrate', verbosity=0, interactive=False)

    def setUp(self):
        from django.core.management import call_command
        from portal.models import Module, Role
        call_command('flush', verbosity=0, interactive=False)
        for code in subject.ROUTES:
            Module.objects.create(code=code, name=code)
        self.role = Role.objects.create(code='synthetic-reader', name='Synthetic reader')
        self.role.modules.add(Module.objects.get(code='hr'))

    def test_idempotent_shared_public_id_and_unchanged_grants(self):
        from portal.models import GatewayModel, ModelRoute, Provider, User
        with patch('portal.model_gateway.test_connection', side_effect=AssertionError('No network during configure')):
            first = subject.configure_model(VALUE)
            second = subject.configure_model(VALUE)
        self.assertEqual(first['model_public_id'], second['model_public_id'])
        self.assertEqual(ModelRoute.objects.count(), 10)
        self.assertEqual(GatewayModel.objects.count(), 1)
        self.assertEqual(Provider.objects.get().api_key_env, subject.KEY_VARIABLE)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(list(self.role.modules.values_list('code', flat=True)), ['hr'])
        parse = ModelRoute.objects.get(code='hr_resume_parse')
        match = ModelRoute.objects.get(code='hr_match_summary')
        self.assertEqual(parse.model.public_id, match.model.public_id)
        self.assertEqual(parse.model.timeout_seconds, 120)
        self.assertEqual(parse.model.max_output_tokens, 4096)

    def test_foreign_route_is_never_overwritten(self):
        from portal.models import GatewayModel, ModelRoute, Module, Provider
        foreign = Provider.objects.create(code='foreign', name='Synthetic foreign',
            base_url='https://example.invalid/v1', api_key_env='PORTAL_MODEL_KEY_SYNTHETIC')
        model = GatewayModel.objects.create(provider=foreign, name='Foreign', model_name='foreign')
        route = ModelRoute.objects.create(code='hr_match_summary', name='Existing',
            module=Module.objects.get(code='hr'), model=model, enabled=False)
        with self.assertRaises(ValueError):
            subject.configure_model(VALUE)
        route.refresh_from_db()
        self.assertEqual(route.model_id, model.pk)
        self.assertFalse(route.enabled)
        self.assertFalse(Provider.objects.filter(code=subject.PROVIDER_CODE).exists())
        self.assertEqual(ModelRoute.objects.count(), 1)

    def test_invalid_model_rolls_back_provider_change(self):
        from django.core.exceptions import ValidationError
        from portal.models import Provider
        subject.configure_model(VALUE)
        original = Provider.objects.get(code=subject.PROVIDER_CODE).base_url
        with self.assertRaises(ValidationError):
            subject.configure_model({**VALUE, 'base_url': 'https://changed.invalid/v1', 'model_name': 'x' * 201})
        self.assertEqual(Provider.objects.get(code=subject.PROVIDER_CODE).base_url, original)

    def test_preserves_existing_option_scope_and_disabled_flag(self):
        from portal.models import GatewayModel, ModelRoute, ModelRouteOption
        subject.configure_model(VALUE)
        route = ModelRoute.objects.get(code='hr_resume_parse')
        option = ModelRouteOption.objects.create(route=route, model=GatewayModel.objects.get(), enabled=False)
        option.allowed_roles.add(self.role)
        subject.configure_model(VALUE)
        option.refresh_from_db()
        self.assertFalse(option.enabled)
        self.assertEqual(list(option.allowed_roles.values_list('pk', flat=True)), [self.role.pk])

    def test_probe_outputs_safe_metadata_only(self):
        from portal.models import Role, User
        subject.configure_model(VALUE)
        user = User.objects.create_user(username='trial-platform_admin', password='synthetic-password')
        user.roles.add(Role.objects.create(code='platform_admin', name='Synthetic admin'))
        with patch('portal.model_gateway.test_connection', return_value={
                'content': 'SYNTHETIC_PRIVATE_UPSTREAM_CONTENT', 'prompt_tokens': 4,
                'completion_tokens': 1, 'duration_ms': 1}) as call:
            result = subject.probe_model(VALUE)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['usage'], {'prompt_tokens': 4, 'completion_tokens': 1})
        self.assertNotIn('content', result)
        self.assertNotIn('SYNTHETIC_PRIVATE', str(result))


if __name__ == '__main__':
    unittest.main(verbosity=2)
