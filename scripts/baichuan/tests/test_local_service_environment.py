"""Import-path checks use fake setup and cannot open a DB or network socket."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


local = load('service_environment_local', 'local_dev.py')
model = load('service_environment_model', 'local_model.py')


class LocalServiceEnvironmentTests(unittest.TestCase):
    def test_portal_and_worker_replace_external_pythonpath(self):
        for name in ('portal', 'baichuan-worker'):
            with self.subTest(name=name), patch.object(local, 'environment',
                    return_value={'PYTHONPATH': 'C:/untrusted', 'OTHER': 'retained'}):
                env = local.service_environment(name)
                self.assertEqual(env['PYTHONPATH'], str(local.ROOT / 'services/business'))
                self.assertEqual(env['OTHER'], 'retained')

    def test_model_gateway_keeps_its_existing_environment(self):
        private = {'base_url': 'https://synthetic.invalid', 'key': 'test-key'}
        helper = SimpleNamespace(model_configuration=lambda: private)
        with patch.object(local, 'environment', return_value={'PORTAL_MODEL_GATEWAY_TOKEN': 'test-token'}), \
                patch.object(local, 'helper', return_value=helper):
            env = local.service_environment('model-gateway')
        self.assertEqual(env['PYTHONPATH'], str(local.ROOT / 'services/business'))
        self.assertEqual(env['MODEL_GATEWAY_SERVICE_TOKEN'], 'test-token')
        self.assertEqual(env['PORTAL_MODEL_KEY_PRIMARY'], 'test-key')

    def test_application_installs_both_paths_before_setup_without_db(self):
        expected_business = str(model.ROOT / 'services/business')
        expected_backend = str(model.ROOT / 'services/business/backend')
        fake_settings = SimpleNamespace(DATABASES={'default': {
            'ENGINE': 'django.db.backends.sqlite3', 'NAME': model.local.RUNTIME / 'portal.sqlite3'}})
        called = []

        def setup():
            self.assertEqual(sys.path[:2], [expected_backend, expected_business])
            from model_gateway import transport
            self.assertEqual(Path(transport.__file__).resolve().parent,
                             model.ROOT / 'services/business/model_gateway')
            called.append(True)

        fake_django = SimpleNamespace(setup=setup)
        old_path = list(sys.path)
        try:
            sys.path[:] = [entry for entry in sys.path if entry not in (expected_backend, expected_business)]
            with patch.dict(os.environ, {'PYTHONPATH': 'C:/untrusted'}, clear=True), \
                    patch.object(model.local, 'environment', return_value={}), \
                    patch.object(model.local, 'local_model_enabled', return_value=True), \
                    patch.dict(sys.modules, {'django': fake_django,
                                            'django.conf': SimpleNamespace(settings=fake_settings)}), \
                    patch('sqlite3.connect', side_effect=AssertionError('SQL forbidden')), \
                    patch('socket.socket.connect', side_effect=AssertionError('network forbidden')), \
                    patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
                model.application()
        finally:
            sys.path[:] = old_path
        self.assertEqual(called, [True])


if __name__ == '__main__':
    unittest.main()
