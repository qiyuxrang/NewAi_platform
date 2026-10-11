"""Run inside the built Linux business image; no database or provider calls."""
import importlib
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


# A new Python subprocess does not inherit a parent's socket monkeypatch.
# Exercise the production CLI's own guard in its actual interpreter.
OFFLINE_PARSER_BOOTSTRAP = r'''
import json
from pathlib import Path
import runpy
import socket
import sys

def prove_socket_guard():
    refused = []
    calls = (('socket', lambda: socket.socket()),
             ('create_connection', lambda: socket.create_connection(('127.0.0.1', 9), timeout=1)),
             ('getaddrinfo', lambda: socket.getaddrinfo('localhost', 9)))
    for name, call in calls:
        try:
            result = call()
        except OSError as error:
            # A normal connection/DNS error must not be counted as a guard.
            if str(error) != 'Parser network access is disabled':
                raise RuntimeError('Unexpected socket probe failure: ' + name) from error
            refused.append(name)
        else:
            if hasattr(result, 'close'):
                result.close()
            raise RuntimeError('Socket guard did not refuse: ' + name)
    return refused

cli, source, output, evidence = sys.argv[1:]
# Creating an unconnected local socket proves this fresh child starts without
# the parent's monkeypatch. It makes no connection, DNS request, or bind call.
with socket.socket():
    before = 'socket_construction_available'
sys.argv = [cli, source, output]
runpy.run_path(cli, run_name='__main__')
after = prove_socket_guard()
Path(evidence).write_text(json.dumps({'before_parser': before, 'after_parser': after}), encoding='utf-8')
'''


def verify_ocr_payload(payload, suffix):
    parsed = payload.get('parsed', {})
    blocks = parsed.get('blocks', [])
    recognized = ''.join(''.join(block.get('text', '').split()) for block in blocks)
    failures = {'ocr_unavailable', 'no_text', 'image_no_text', 'ocr_limit'}
    if (payload.get('ok') is not True or parsed.get('method') != 'ocr'
            or parsed.get('status') not in {'completed', 'needs_review'}
            or not blocks or any(block.get('kind') != 'ocr' for block in blocks)
            or any(warning.get('code') in failures for warning in parsed.get('warnings', []))
            or not all(token in recognized for token in ('CLOUD', '7319', '\u6d4b\u8bd5'))):
        raise RuntimeError('Real offline OCR failed for synthetic ' + suffix.upper())
    return len(blocks)


def ocr_worker(backend):
    """Exercise the production parser on synthetic inputs, without Django or keys."""
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('OCR must run in the isolated Python 3.12 interpreter')
    from PIL import Image, ImageDraw, ImageFont
    import onnxruntime
    import pypdfium2 as pdfium
    if 'CPUExecutionProvider' not in onnxruntime.get_available_providers():
        raise RuntimeError('Missing ONNX CPU provider')
    if os.name == 'nt':
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    else:
        font_path = Path(subprocess.check_output(
            ['fc-match', '-f', '%{file}', 'Noto Sans CJK SC'], text=True).strip())
    if not font_path.is_file():
        raise RuntimeError('Missing CJK font for the synthetic OCR fixture')
    font = ImageFont.truetype(str(font_path), 64)
    cli = Path(backend) / 'portal/source_parsers/cli.py'
    if not cli.is_file():
        raise RuntimeError('Missing production parser CLI')
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}}
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1',
                       PRODUCT_PARSER_OCR='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    checks = []
    with tempfile.TemporaryDirectory(prefix='cloud-ocr-') as directory:
        folder = Path(directory)
        image = Image.new('RGB', (1800, 900), 'white')
        try:
            draw = ImageDraw.Draw(image)
            draw.text((100, 120), 'CLOUD OCR SAMPLE 7319', fill='black', font=font)
            draw.text((100, 260), '\u4e91\u90e8\u7f72\u6d4b\u8bd5\u6750\u6599', fill='black', font=font)
            image.save(folder / 'sample.png')
            # Pillow embeds only the bitmap, so this PDF has no text layer.
            image.save(folder / 'sample.pdf', resolution=100)
        finally:
            image.close()
        with pdfium.PdfDocument(folder / 'sample.pdf') as document:
            page = document[0]
            try:
                text_page = page.get_textpage()
                try:
                    if text_page.count_chars():
                        raise RuntimeError('OCR PDF fixture unexpectedly has a text layer')
                finally:
                    text_page.close()
            finally:
                page.close()
        for suffix in ('png', 'pdf'):
            output = folder / (suffix + '.json')
            guard_evidence = folder / (suffix + '-socket-guard.json')
            subprocess.run([sys.executable, '-I', '-B', '-c', OFFLINE_PARSER_BOOTSTRAP,
                            str(cli), str(folder / ('sample.' + suffix)), str(output),
                            str(guard_evidence)],
                           env=environment, check=True, timeout=120,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            guard = json.loads(guard_evidence.read_text(encoding='utf-8'))
            expected = ['socket', 'create_connection', 'getaddrinfo']
            if guard != {'before_parser': 'socket_construction_available', 'after_parser': expected}:
                raise RuntimeError('Actual parser child socket guard was not verified')
            payload = json.loads(output.read_text(encoding='utf-8'))
            count = verify_ocr_payload(payload, suffix)
            checks.append({'format': suffix, 'method': 'ocr', 'blocks': count,
                           'english_number_chinese': 'passed', 'child_socket_guard': guard})
    print(json.dumps({'local_ocr': 'passed', 'platform': sys.platform,
                      'python': sys.version.split()[0], 'synthetic_inputs': checks,
                      'network': 'python_socket_calls_refused_in_parser_child',
                      'os_network_isolation': 'not_exercised', 'real_model_calls': False}))


def check_ocr():
    runtime = os.environ.get('PORTAL_PRODUCT_PARSER_PYTHON', '/opt/product-parser/bin/python')
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}}
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1')
    subprocess.run(['uv', 'pip', 'check', '--python', runtime], env=environment, check=True)
    subprocess.run([runtime, '-I', '-B', str(Path(__file__).resolve()), '--ocr-worker',
                    '--backend', '/app/services/business/backend'], env=environment,
                   check=True, timeout=300)


def main():
    if sys.platform != 'linux':
        raise SystemExit('Run this check in the target Linux business image')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd process isolation is unavailable')
    descriptor = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(descriptor, 0)
    finally:
        os.close(descriptor)
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    for module in ('django', 'rest_framework', 'psycopg', 'asyncpg', 'sqlalchemy',
                   'greenlet', 'fastapi', 'mcp.server', 'deepagents', 'langchain',
                   'docx', 'pptx', 'PIL', 'fitz', 'yaml', 'pypdfium2'):
        importlib.import_module(module)
    from deepagents import AsyncSubAgent, HarnessProfile, create_deep_agent
    from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile
    for executable in ('libreoffice', 'chromium', 'node', 'pdftoppm', 'fc-match'):
        if not shutil.which(executable):
            raise RuntimeError('Missing executable: ' + executable)
    subprocess.run(['/usr/bin/python3', '-c', 'import uno; print("System UNO import passed")'], check=True)
    for family in ('Microsoft YaHei', 'SimSun', 'Calibri'):
        subprocess.run(['fc-match', family], check=True)
    root = Path('/app/services/business/backend/portal/product_assets/mermaid-runtime')
    if not (root / 'dist').is_dir():
        raise RuntimeError('Missing built Mermaid bundle')
    subprocess.run(['node', '--input-type=module', '-e',
                    "import {readVerifiedBundle} from './bundle-contract.mjs'; await readVerifiedBundle('./dist'); console.log('Mermaid bundle verified');"],
                   cwd=root, check=True)
    if not os.access('/data/product', os.W_OK):
        raise RuntimeError('Product volume is not writable by the business user')
    check_ocr()
    print(json.dumps({'image_structure': 'passed', 'real_model_calls': False,
                      'local_ocr': 'passed', 'rendering': 'not_exercised',
                      'business_acceptance': 'pending'}))


if __name__ == '__main__':
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--ocr-worker', action='store_true')
    arguments.add_argument('--backend', type=Path)
    options = arguments.parse_args()
    if options.ocr_worker:
        if options.backend is None:
            arguments.error('--ocr-worker requires --backend')
        ocr_worker(options.backend)
    else:
        main()
