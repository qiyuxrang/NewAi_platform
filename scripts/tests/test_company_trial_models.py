import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'company-trial.py'
spec = importlib.util.spec_from_file_location('company_trial_model_tests', SCRIPT)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class PrivateModelConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.patcher = patch.object(trial, 'RUNTIME', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.directory.cleanup)
        self.values = {'MODEL_BASE_URL': 'https://provider.example/v1', 'MODEL_NAME': 'synthetic-model',
                       'PORTAL_MODEL_KEY_PRIMARY': 'synthetic-test-key', 'MODEL_SUPPORTS_VISION': '1',
                       'MODEL_MAX_OUTPUT_TOKENS': '4096', 'MODEL_TIMEOUT_SECONDS': '120'}
        (self.root / 'secrets.json').write_text(json.dumps({'portal': 'p' * 48, 'platform': 'a' * 48,
                                                        'model_gateway': 'g' * 48}), encoding='utf-8')
        self.config = {'python': 'synthetic-python', 'node': 'synthetic-node'}

    def write_config(self, values=None):
        data = self.values if values is None else values
        (self.root / 'model.env').write_text('\n'.join(key + '=' + value for key, value in data.items()), encoding='utf-8')

    def test_missing_and_empty_optional_configuration(self):
        self.assertIsNone(trial.model_configuration())
        self.write_config({'MODEL_BASE_URL': '', 'MODEL_NAME': '', 'PORTAL_MODEL_KEY_PRIMARY': ''})
        self.assertIsNone(trial.model_configuration())

    def test_partial_configuration_is_rejected(self):
        self.write_config({'MODEL_NAME': 'synthetic-model'})
        with self.assertRaises(ValueError):
            trial.model_configuration()

    def test_non_https_credentialed_and_nonstandard_port_urls_rejected(self):
        for address in ('http://provider.example/v1', 'https://user:pass@provider.example/v1',
                        'https://provider.example:8443/v1', 'https://provider.example/v1?token=x'):
            with self.subTest(address=address):
                self.write_config({**self.values, 'MODEL_BASE_URL': address})
                with self.assertRaises(ValueError):
                    trial.model_configuration()

    def test_numeric_and_vision_bounds_are_enforced(self):
        for field, value in (('MODEL_MAX_OUTPUT_TOKENS', '8193'), ('MODEL_MAX_OUTPUT_TOKENS', '0'),
                             ('MODEL_TIMEOUT_SECONDS', '601'), ('MODEL_TIMEOUT_SECONDS', '1.5'),
                             ('MODEL_SUPPORTS_VISION', 'true')):
            with self.subTest(field=field, value=value):
                self.write_config({**self.values, field: value})
                with self.assertRaises(ValueError):
                    trial.model_configuration()

    def test_portal_env_has_service_identity_but_no_upstream_key(self):
        self.write_config()
        with patch.dict(os.environ, {'PORTAL_MODEL_KEY_LEAK': 'inherited-secret',
                                    'MODEL_GATEWAY_SERVICE_TOKEN': 'inherited-secret'}):
            env = trial.environment(self.config)
        self.assertFalse(any(key.startswith('PORTAL_MODEL_KEY_') for key in env))
        self.assertNotIn('MODEL_GATEWAY_SERVICE_TOKEN', env)
        self.assertEqual(env['PORTAL_MODEL_GATEWAY_TOKEN'], 'g' * 48)
        self.assertEqual(env['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'], 'source_only_preview')
        self.assertEqual(env['PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED'], '0')

    def test_product_parser_can_use_an_independent_python_runtime(self):
        env = trial.environment({**self.config, 'parser_python': 'python-312'})
        self.assertEqual(env['PORTAL_PRODUCT_DOCUMENT_PYTHON'], 'synthetic-python')
        self.assertEqual(env['PORTAL_PRODUCT_PARSER_PYTHON'], 'python-312')

    def test_product_parser_defaults_to_the_business_python_runtime(self):
        env = trial.environment(self.config)
        self.assertEqual(env['PORTAL_PRODUCT_DOCUMENT_PYTHON'], 'synthetic-python')
        self.assertEqual(env['PORTAL_PRODUCT_PARSER_PYTHON'], 'synthetic-python')

    def test_missing_service_identity_rejected_without_secret_in_error(self):
        self.write_config()
        (self.root / 'secrets.json').write_text(json.dumps({'portal': 'p' * 48, 'platform': 'a' * 48}), encoding='utf-8')
        with self.assertRaises(ValueError) as error:
            trial.environment(self.config)
        self.assertNotIn(self.values['PORTAL_MODEL_KEY_PRIMARY'], str(error.exception))

    def test_fresh_prepare_creates_private_model_service_identity(self):
        (self.root / 'secrets.json').unlink()
        config_path = self.root / 'config.json'
        def write_private(path, value):
            with path.open('x', encoding='utf-8') as stream:
                json.dump(value, stream)
        with patch.object(trial, 'CONFIG', config_path), patch.object(trial, 'private_json', side_effect=write_private), \
             patch.object(trial, 'environment', return_value={}), patch.object(trial.subprocess, 'run'), \
             contextlib.redirect_stdout(io.StringIO()):
            trial.prepare(SimpleNamespace(python=__import__('sys').executable, node=__import__('sys').executable))
        value = json.loads((self.root / 'secrets.json').read_text(encoding='utf-8'))
        self.assertEqual(set(value), {'portal', 'platform', 'model_gateway'})
        self.assertTrue(all(len(token) == 64 for token in value.values()))
        self.assertEqual(len(set(value.values())), 3)

    def test_fresh_prepare_persists_independent_parser_python(self):
        (self.root / 'secrets.json').unlink()
        config_path = self.root / 'config.json'
        def write_private(path, value):
            with path.open('x', encoding='utf-8') as stream:
                json.dump(value, stream)
        with patch.object(trial, 'CONFIG', config_path), patch.object(trial, 'private_json', side_effect=write_private), \
             patch.object(trial, 'environment', return_value={}), patch.object(trial.subprocess, 'run'), \
             contextlib.redirect_stdout(io.StringIO()):
            trial.prepare(SimpleNamespace(python=__import__('sys').executable,
                                          parser_python=__import__('sys').executable,
                                          node=__import__('sys').executable))
        config = json.loads(config_path.read_text(encoding='utf-8'))
        self.assertEqual(config['parser_python'], str(Path(__import__('sys').executable).resolve()))

    def test_missing_parser_python_is_rejected_before_creating_secrets_or_accounts(self):
        (self.root / 'secrets.json').unlink()
        config_path = self.root / 'config.json'
        missing_parser = self.root / 'python-312-missing.exe'
        with patch.object(trial, 'CONFIG', config_path), patch.object(trial.subprocess, 'run') as run, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'Missing runtime: parser_python'):
                trial.prepare(SimpleNamespace(python=__import__('sys').executable,
                                              parser_python=str(missing_parser),
                                              node=__import__('sys').executable))
        self.assertFalse((self.root / 'secrets.json').exists())
        self.assertFalse((self.root / 'accounts.json').exists())
        self.assertFalse(config_path.exists())
        run.assert_not_called()

    def test_no_dotenv_interpolation_of_credentials(self):
        self.write_config({**self.values, 'PORTAL_MODEL_KEY_PRIMARY': '${UNRELATED_TEST_SECRET}'})
        with patch.dict(os.environ, {'UNRELATED_TEST_SECRET': 'different-secret'}):
            self.assertEqual(trial.model_configuration()['key'], '${UNRELATED_TEST_SECRET}')

    def test_only_model_gateway_child_receives_upstream_key(self):
        self.write_config()
        calls = []
        class Process:
            pid = 12345
            def poll(self):
                return None
        class Ready:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        def launch(command, **kwargs):
            calls.append((command, kwargs['env']))
            return Process()
        with patch.object(trial, 'available'), patch.object(trial, 'process_identity', return_value={'synthetic': True}), \
             patch.object(trial.subprocess, 'Popen', side_effect=launch), patch.object(trial, 'urlopen', return_value=Ready()), \
             contextlib.redirect_stdout(io.StringIO()):
            trial.start(self.config)
        keyed = [command for command, env in calls if 'PORTAL_MODEL_KEY_PRIMARY' in env]
        self.assertEqual(len(calls), 8)
        self.assertEqual(len(keyed), 1)
        self.assertIn('model_gateway.app:app', keyed[0])
        self.assertTrue(any('run_product_worker' in command for command, env in calls))

    def test_backend_only_skips_ui_ports_processes_and_health_checks(self):
        self.write_config()
        calls, urls = [], []
        class Process:
            pid = 12345
            def poll(self):
                return None
        class Ready:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        def launch(command, **kwargs):
            calls.append(command)
            return Process()
        def ready(url, **kwargs):
            urls.append(url)
            return Ready()
        with patch.object(trial, 'available') as ports, patch.object(trial, 'process_identity', return_value={'synthetic': True}), \
             patch.object(trial.subprocess, 'Popen', side_effect=launch), patch.object(trial, 'urlopen', side_effect=ready), \
             contextlib.redirect_stdout(io.StringIO()):
            trial.start(self.config, backend_only=True)
        self.assertEqual(len(calls), 6)
        self.assertEqual({call.args[0] for call in ports.call_args_list}, {18100, 18080, 18410})
        self.assertEqual(len(urls), 3)
        self.assertFalse(any('13180' in url or '13181' in url for url in urls))
        self.assertTrue(any('run_product_worker' in command for command in calls))
        self.assertFalse(any('next' in str(command) or 'company-trial-frontend' in str(command) for command in calls))


if __name__ == '__main__':
    unittest.main()
