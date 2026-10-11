"""Offline package checks. Does not claim Docker/LibreOffice/cloud validation."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('cloud_configure', ROOT / 'configure.py')
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class PackageTests(unittest.TestCase):
    def test_compose_service_contract(self):
        data = yaml.safe_load((ROOT / 'compose.yml').read_text(encoding='utf-8'))
        services = data['services']
        self.assertEqual(data['name'], 'aicompany-cloud')
        self.assertEqual(data['networks']['internal']['name'], 'aicompany-cloud-internal')
        for name, service in services.items():
            if name != 'edge':
                self.assertNotIn('ports', service, name)
            if 'build' in service:
                build = service['build']
                context = (ROOT / build['context']).resolve()
                self.assertTrue(context.is_dir(), name)
                self.assertTrue((context / build['dockerfile']).is_file(), name)
        self.assertEqual(services['portal-init']['profiles'], ['setup'])
        self.assertEqual(services['portal-init']['restart'], 'no')
        environment = services['gateway']['environment']
        self.assertEqual(environment['PLATFORM_CONTAINER_NETWORK'], data['networks']['internal']['name'])
        self.assertEqual(environment['PLATFORM_USER_CONTAINER_PUBLISH_PORTS'], 'false')
        self.assertEqual(environment['PLATFORM_SHARED_OPENCLAW_ENABLED'], 'false')
        self.assertIn('openclaw-gateway', services['gateway']['networks']['internal']['aliases'])
        self.assertEqual(services['portal']['environment']['PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED'], '0')
        for name in ('portal', 'portal-init', 'product-worker', 'hr-worker'):
            self.assertEqual(services[name]['environment']['PORTAL_PRODUCT_PARSER_PYTHON'],
                             '/opt/product-parser/bin/python')
            self.assertEqual(services[name]['environment']['PORTAL_PRODUCT_DOCUMENT_PYTHON'],
                             '/usr/local/bin/python')
        self.assertIn('ADMIN_DOMAIN', services['frontend']['build']['args']['VITE_ADMIN_URL'])

    def test_template_requires_real_configuration(self):
        values = configure.read_env(ROOT / '.env.example')
        self.assertTrue(configure.validate(values))
        import secrets
        for key in configure.SECRET_KEYS:
            values[key] = secrets.token_hex(32)
        for key, value in zip(configure.DOMAIN_KEYS, ('work.company.test', 'admin.company.test', 'portal.company.test')):
            values[key] = value
        self.assertEqual(configure.validate(values), [])
        values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'] = 'source_only_preview'
        self.assertEqual(configure.validate(values), [])
        values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'] = 'unknown-mode'
        self.assertTrue(any('KNOWLEDGE_MODE' in item for item in configure.validate(values)))
        values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'] = 'ragflow_required'
        values['POSTGRES_PASSWORD'] = 'a' * 64
        self.assertTrue(configure.validate(values))
        values['PORTAL_DOMAIN'] = values['APP_DOMAIN']
        self.assertTrue(any('distinct' in item for item in configure.validate(values)))

    def test_no_missing_copy_sources(self):
        for dockerfile in ROOT.glob('*.Dockerfile'):
            for line in dockerfile.read_text().splitlines():
                if not line.startswith('COPY ') or '--from=' in line:
                    continue
                tokens = line.split()[1:]
                for source in tokens[:-1]:
                    self.assertTrue((PROJECT / source).exists(), f'{dockerfile.name}: {source}')

    def test_generator_no_overwrite_or_secret_output(self):
        temporary_root = PROJECT / '.runtime' / 'cloud-package'
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cloud-config-', dir=temporary_root) as directory:
            target = Path(directory) / 'private.env'
            command = [sys.executable, str(ROOT / 'configure.py'), 'generate', '--env', str(target),
                       '--app-domain', 'work.company.test', '--admin-domain', 'admin.company.test',
                       '--portal-domain', 'portal.company.test', '--email', 'ops@company.test']
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = target.read_bytes()
            values = configure.read_env(target)
            self.assertEqual(configure.validate(values), [])
            self.assertEqual(values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'], 'ragflow_required')
            for key in configure.SECRET_KEYS:
                self.assertNotIn(values[key], first.stdout + first.stderr)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(target.read_bytes(), content)

    def test_explicit_preview_generation_preserves_closed_authorization_and_saved_mode(self):
        temporary_root = PROJECT / '.runtime' / 'cloud-package'
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cloud-preview-', dir=temporary_root) as directory:
            target = Path(directory) / 'private.env'
            command = [sys.executable, str(ROOT / 'configure.py'), 'generate', '--env', str(target),
                       '--app-domain', 'work.company.test', '--admin-domain', 'admin.company.test',
                       '--portal-domain', 'portal.company.test', '--email', 'ops@company.test',
                       '--product-knowledge-mode', 'source_only_preview']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            content = target.read_bytes()
            values = configure.read_env(target)
            self.assertEqual(values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'], 'source_only_preview')
            self.assertEqual(configure.validate(values), [])
            for key in ('PORTAL_PRODUCT_MODEL_CALLS_ALLOWED', 'PORTAL_PRODUCT_KNOWLEDGE_ENABLED',
                        'PORTAL_PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED'):
                self.assertEqual(values[key], '0')
            for key in configure.SECRET_KEYS:
                self.assertNotIn(values[key], result.stdout + result.stderr)
            check = [sys.executable, str(ROOT / 'configure.py'), 'check', '--env', str(target)]
            checked = subprocess.run(check, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            misleading_override = subprocess.run(check + ['--product-knowledge-mode', 'ragflow_required'],
                                                 capture_output=True, text=True)
            self.assertNotEqual(misleading_override.returncode, 0)
            self.assertEqual(target.read_bytes(), content)

    def test_sources_and_dependency_pins(self):
        for source in ROOT.glob('*.py'):
            ast.parse(source.read_text(encoding='utf-8-sig'), filename=str(source))
        pins = (ROOT / 'requirements.lock').read_text(encoding='utf-8-sig').splitlines()
        self.assertTrue(all(re.fullmatch(r'[A-Za-z0-9_.-]+==[^\s]+', line) for line in pins if line))
        self.assertIn('mcp==1.30.0', pins)
        self.assertIn('greenlet==3.5.6', pins)
        self.assertIn('httpx-sse==0.4.3', pins)
        self.assertIn('deepagents==0.7.19', pins)
        self.assertIn('langchain==1.4.2', pins)
        self.assertIn('langgraph-sdk==0.4.5', pins)
        self.assertIn('pypdfium2==5.13.0', pins)
        self.assertIn('djangorestframework==3.18.3', pins)
        self.assertFalse(any(line.lower().startswith('pywin32') for line in pins))
        self.assertFalse(any(line.lower().startswith('rapidocr') for line in pins))
        dockerfile = (ROOT / 'business.Dockerfile').read_text()
        self.assertIn('FROM python:3.13-slim-bookworm', dockerfile)
        self.assertIn('uv python install 3.12', dockerfile)
        self.assertIn('uv pip sync --python /opt/product-parser/bin/python /tmp/intake-requirements.txt', dockerfile)
        self.assertIn('libgl1 libglib2.0-0', dockerfile)
        parser_pins = (PROJECT / 'services/business/backend/portal/source_parsers/requirements.txt').read_text()
        self.assertIn('rapidocr-onnxruntime==1.4.4', parser_pins)
        image_spec = importlib.util.spec_from_file_location('cloud_image_checks', ROOT / 'image_checks.py')
        image_checks = importlib.util.module_from_spec(image_spec)
        image_spec.loader.exec_module(image_checks)
        # A successful CLI exit cannot stand in for usable OCR output.
        for payload in ({'ok': True, 'parsed': {'status': 'failed', 'method': 'native', 'blocks': []}},
                        {'ok': True, 'parsed': {'status': 'partial', 'method': 'ocr',
                         'blocks': [{'kind': 'ocr', 'text': 'CLOUD 7319 \u6d4b\u8bd5'}],
                         'warnings': [{'code': 'ocr_unavailable'}]}}):
            with self.assertRaises(RuntimeError):
                image_checks.verify_ocr_payload(payload, 'pdf')
        # Exercise the bootstrap in a real fresh child; a parent monkeypatch
        # cannot establish this property. No OCR dependencies are needed here.
        with tempfile.TemporaryDirectory(prefix='cloud-socket-guard-') as directory:
            folder = Path(directory)
            child = folder / 'probe_cli.py'
            child.write_text('import socket\ndef deny(*args, **kwargs):\n'
                             '    raise OSError("Parser network access is disabled")\n'
                             'socket.socket = socket.create_connection = socket.getaddrinfo = deny\n',
                             encoding='utf-8')
            evidence = folder / 'guard.json'
            subprocess.run([sys.executable, '-I', '-B', '-c', image_checks.OFFLINE_PARSER_BOOTSTRAP,
                            str(child), str(folder / 'unused.png'), str(folder / 'unused.json'),
                            str(evidence)], check=True, timeout=15, capture_output=True)
            expected = ['socket', 'create_connection', 'getaddrinfo']
            self.assertEqual(json.loads(evidence.read_text(encoding='utf-8')),
                             {'before_parser': 'socket_construction_available', 'after_parser': expected})
            # The bootstrap must not install a replacement guard that masks
            # a CLI which fails to disable sockets. No external network calls.
            child.write_text('pass\n', encoding='utf-8')
            refused = subprocess.run([sys.executable, '-I', '-B', '-c', image_checks.OFFLINE_PARSER_BOOTSTRAP,
                                     str(child), str(folder / 'unused.png'), str(folder / 'unused.json'),
                                     str(evidence)], timeout=15, capture_output=True)
            self.assertNotEqual(refused.returncode, 0)

    def test_private_build_exclusions(self):
        ignored = (PROJECT / '.dockerignore').read_text().splitlines()
        for pattern in ('**/.env', '**/.env.*', '**/node_modules/', '.runtime/',
                        '**/data/', '**/backups/', '**/*.pem', '**/*.key'):
            self.assertIn(pattern, ignored)
        config = (ROOT / 'Caddyfile').read_text()
        self.assertIn('@backend path /admin /admin/* /api/* /static/* /health/', config)
        self.assertIn('@access path /login /password', config)
        page = (ROOT / 'portal-access.html').read_text(encoding='utf-8')
        self.assertIn("'/api/password/'", page)
        self.assertIn('X-CSRFToken', page)
        self.assertNotIn('localStorage', page)

    def test_backup_shell_quiesce_and_failure_restore(self):
        shell = shutil.which('sh')
        if not shell:
            git = shutil.which('git')
            candidate = Path(git).parent.parent / 'bin/sh.exe' if git else None
            shell = str(candidate) if candidate and candidate.is_file() else None
        if not shell:
            self.skipTest('No POSIX shell available; target Linux backup rehearsal remains required')
        subprocess.run([shell, '-n', str(ROOT / 'backup.sh')], check=True)
        mock = r'''#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$MOCK_LOG"
if [ "$1" = compose ]; then
  shift 5
  case "$1" in
    ps) cat "$MOCK_STATE/services";;
    stop)
      for service do :; done
      [ "$MOCK_FAIL" != stop ] || [ "$service" != gateway ] || exit 8
      sed "/^$service$/d" "$MOCK_STATE/services" > "$MOCK_STATE/temp"
      mv "$MOCK_STATE/temp" "$MOCK_STATE/services";;
    start)
      for service do :; done
      grep -qx "$service" "$MOCK_STATE/services" || printf '%s\n' "$service" >> "$MOCK_STATE/services";;
    exec)
      [ ! -s "$MOCK_STATE/runtimes" ] || exit 12
      ! grep -qx gateway "$MOCK_STATE/services" || exit 13
      [ "$MOCK_FAIL" != dump ] || exit 7
      printf 'mock database dump\n';;
    images) printf '{}\n';;
    *) exit 90;;
  esac
else
  case "$1" in
    ps)
      cat "$MOCK_STATE/runtimes"
      if [ "$MOCK_FAIL" = active ] && [ ! -s "$MOCK_STATE/runtimes" ]; then printf 'unexpected-runtime\n'; fi;;
    stop)
      [ "$MOCK_FAIL" != runtime ] || exit 9
      : > "$MOCK_STATE/runtimes"
      if grep -qx gateway "$MOCK_STATE/services"; then printf 'race-container\n' >> "$MOCK_STATE/runtimes"; fi;;
    start) grep -qx "$2" "$MOCK_STATE/runtimes" || printf '%s\n' "$2" >> "$MOCK_STATE/runtimes";;
    volume)
      [ "$MOCK_FAIL" != volumes ] || exit 10
      printf 'aicompany-cloud_postgres_data\naicompany-cloud_business_data\nopenclaw-data-test\n';;
    run) :;;
    *) exit 91;;
  esac
fi
'''
        def shell_path(path):
            value = str(path).replace('\\', '/')
            return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value
        temporary_root = PROJECT / '.runtime' / 'cloud-package'
        temporary_root.mkdir(parents=True, exist_ok=True)
        for failure, expected in (('none', 0), ('stop', 8), ('runtime', 9), ('dump', 7), ('volumes', 10), ('active', 1)):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix='backup-mock-', dir=temporary_root) as directory:
                folder = Path(directory)
                (folder / 'bin').mkdir()
                (folder / 'state').mkdir()
                binary = folder / 'bin/docker'
                binary.write_text(mock, encoding='utf-8', newline='\n')
                binary.chmod(0o755)
                initial = ['postgres', 'portal', 'product-worker', 'gateway', 'frontend', 'edge']
                (folder / 'state/services').write_text('\n'.join(initial) + '\n', encoding='utf-8', newline='\n')
                (folder / 'state/runtimes').write_text('runtime-original\n', encoding='utf-8', newline='\n')
                shutil.copyfile(ROOT / 'backup.sh', folder / 'backup.sh')
                for name in ('.env', 'compose.yml', 'Caddyfile'):
                    (folder / name).write_text('mock-only\n', encoding='utf-8')
                environment = dict(os.environ, MOCK_STATE=shell_path(folder / 'state'),
                                   MOCK_LOG=shell_path(folder / 'commands.log'), MOCK_FAIL=failure)
                result = subprocess.run([shell, '-c', 'PATH="$1/bin:$PATH"; export PATH; sh "$1/backup.sh" "$1/backup"',
                                         'sh', shell_path(folder)], env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(sorted((folder / 'state/services').read_text().splitlines()), sorted(initial))
                self.assertEqual((folder / 'state/runtimes').read_text().splitlines(), ['runtime-original'])
                self.assertEqual((folder / 'backup/BACKUP_COMPLETE').exists(), failure == 'none')
                commands = (folder / 'commands.log').read_text().splitlines()
                if failure == 'none':
                    stops = [commands.index('compose --env-file .env -f compose.yml stop -t 60 ' + name) for name in ('edge', 'gateway')]
                    snapshot = commands.index('ps -q --filter label=openclaw.platform.network=aicompany-cloud-internal')
                    self.assertLess(stops[0], stops[1])
                    self.assertLess(stops[1], snapshot)
                    self.assertLess(snapshot, commands.index('stop -t 60 runtime-original'))
                    starts = [line for line in commands if ' start ' in line or line.startswith('start ')]
                    self.assertEqual(starts[-2:], ['compose --env-file .env -f compose.yml start edge', 'start runtime-original'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
