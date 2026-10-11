"""Generate private .env or validate it; never print credential values."""
import argparse
import os
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parent
SECRET_KEYS = ('POSTGRES_PASSWORD', 'PLATFORM_JWT_SECRET', 'PLATFORM_ADMIN_PASSWORD',
               'PORTAL_SECRET_KEY', 'MODEL_GATEWAY_SERVICE_TOKEN')
DOMAIN_KEYS = ('APP_DOMAIN', 'ADMIN_DOMAIN', 'PORTAL_DOMAIN')
KNOWLEDGE_MODES = ('ragflow_required', 'source_only_preview')


def read_env(path):
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise ValueError('Invalid env assignment')
        if key in result:
            raise ValueError('Duplicate env key: ' + key)
        result[key] = value.strip()
    return result


def validate(values):
    errors = []
    for key in DOMAIN_KEYS:
        value = values.get(key, '')
        if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', value):
            errors.append(key + ': use a DNS hostname without scheme/path')
        elif value.endswith('.example.com') or value in {'example.com', 'localhost'}:
            errors.append(key + ': replace example domain')
    if len({values.get(key) for key in DOMAIN_KEYS}) != 3:
        errors.append('Three distinct domains are required')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values.get('TLS_EMAIL', '')):
        errors.append('TLS_EMAIL: valid email required')
    for key in SECRET_KEYS:
        value = values.get(key, '')
        if not re.fullmatch(r'[a-f0-9]{64,128}', value):
            errors.append(key + ': require 64+ random hexadecimal characters')
        elif len(set(value)) < 8:
            errors.append(key + ': credential appears repetitive')
    if len({values.get(key) for key in SECRET_KEYS}) != len(SECRET_KEYS):
        errors.append('Use independent credentials')
    for key in ('POSTGRES_USER', 'PLATFORM_ADMIN_USERNAME'):
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{2,63}', values.get(key, '')):
            errors.append(key + ': use an alphanumeric username')
    for key in ('RELEASE_TAG', 'PLATFORM_DEPLOY_VERSION'):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', values.get(key, '')):
            errors.append(key + ': valid version tag required')
    if values.get('PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE') not in KNOWLEDGE_MODES:
        errors.append('PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE: require ragflow_required or source_only_preview')
    for key in ('PORTAL_PRODUCT_MODEL_CALLS_ALLOWED', 'PORTAL_PRODUCT_KNOWLEDGE_ENABLED',
                'PORTAL_PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED'):
        if values.get(key) not in {'0', '1'}:
            errors.append(key + ': require 0 or 1')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['generate', 'check'])
    parser.add_argument('--env', type=Path, default=ROOT / '.env')
    parser.add_argument('--app-domain')
    parser.add_argument('--admin-domain')
    parser.add_argument('--portal-domain')
    parser.add_argument('--email')
    parser.add_argument('--product-knowledge-mode', choices=KNOWLEDGE_MODES,
                        help='Generate an explicit knowledge mode; default is ragflow_required. Preview produces review drafts.')
    args = parser.parse_args()
    if args.action != 'generate' and args.product_knowledge_mode is not None:
        parser.error('--product-knowledge-mode applies only to generate; check validates the saved file')
    try:
        if args.action == 'generate':
            values = read_env(ROOT / '.env.example')
            for key in SECRET_KEYS:
                values[key] = secrets.token_hex(32)
            for key, supplied in zip(DOMAIN_KEYS, (args.app_domain, args.admin_domain, args.portal_domain)):
                values[key] = (supplied or '').lower()
            values['TLS_EMAIL'] = args.email or ''
            if args.product_knowledge_mode is not None:
                values['PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE'] = args.product_knowledge_mode
            errors = validate(values)
            if errors:
                raise ValueError('\n'.join(errors))
            args.env.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(args.env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write('# PRIVATE: credentials generated independently; never commit or share.\n')
                stream.writelines(f'{key}={value}\n' for key, value in values.items())
            print('Private configuration generated. Credentials were not printed.')
        else:
            errors = validate(read_env(args.env))
            if errors:
                raise ValueError('\n'.join(errors))
            print('Configuration structure valid. External service authorization remains a separate gate.')
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
