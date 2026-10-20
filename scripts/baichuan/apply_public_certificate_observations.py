"""Offline owned-local ITSS publication maintenance. Default inert; never verifies certificates."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_provenance(item, archive_root):
    """Bind approved body to actual frozen acquisition bytes/receipt, without fetching."""
    from local_search import _plain_path
    origin = item['provenance']
    keys = {'raw_file', 'raw_sha256', 'body_file', 'body_sha256', 'receipt_file', 'receipt_sha256'}
    if not isinstance(origin, dict) or set(origin) != keys:
        raise ValueError('Explicit actual acquisition provenance is required')
    files = {}
    archive_root = _plain_path(archive_root)
    for kind in ['raw', 'body', 'receipt']:
        value = origin[kind + '_file']
        if not isinstance(value, str) or Path(value).is_absolute() or '..' in Path(value).parts:
            raise ValueError('Acquisition paths must remain in the owned frozen research archive')
        path = _plain_path(archive_root / value)
        if archive_root not in path.parents or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Acquisition artifact outside owned bounded archive')
        if not re.fullmatch('[a-f0-9]{64}', origin[kind + '_sha256'] or '') or sha(path) != origin[kind + '_sha256']:
            raise ValueError('Actual acquisition artifact hash differs')
        files[kind] = path
    source = item['source']
    receipt = json.loads(files['receipt'].read_bytes().decode('utf-8'))
    if (files['raw'].read_bytes().decode('utf-8') != source['body']
            or files['body'].read_bytes().decode('utf-8') != source['body']
            or origin['body_sha256'] != source['content_sha256'] or receipt.get('status') != 'completed'
            or receipt.get('http_status') != 200 or receipt.get('url') != source['url']
            or receipt.get('at') != source['retrieved_at'] or receipt.get('tls_standard_verification') is not True
            or receipt.get('body_sha256') != origin['body_sha256'] or receipt.get('raw_sha256') != origin['raw_sha256']
            or Path(receipt.get('raw_file', '')).name != files['raw'].name
            or len({files[kind].parent for kind in ['raw', 'body', 'receipt']}) != 1
            or files['raw'].stem != files['body'].stem or files['receipt'].name != files['raw'].stem + '.receipt.json'
            or ('body_file' in receipt and Path(receipt['body_file']).name != files['body'].name)
            or not receipt.get('public_ips')
            or any(not ipaddress.ip_address(ip).is_global for ip in receipt['public_ips'])):
        raise ValueError('Frozen completed public acquisition does not bind this exact source')


def validate_batch(batch, archive_root):
    from portal.baichuan_facts import validate_public_certificate_observation
    from datetime import datetime
    from django.utils import timezone
    keys = {'schema_version', 'kind', 'source_workbook_sha256', 'reviewer', 'reviewed_at', 'items'}
    if (not isinstance(batch, dict) or set(batch) != keys or type(batch['schema_version']) is not int
            or batch['schema_version'] != 1 or batch['kind'] != 'itss_public_observations_v1'
            or batch['reviewer'] != 'assistant_source_review'
            or not re.fullmatch('[a-f0-9]{64}', batch['source_workbook_sha256'] or '')
            or not isinstance(batch['items'], list) or not 1 <= len(batch['items']) <= 50):
        raise ValueError('Bounded explicit public observation batch required')
    reviewed = datetime.fromisoformat(batch['reviewed_at'])
    if timezone.is_naive(reviewed) or reviewed > timezone.now():
        raise ValueError('Explicit non-future review time required')
    import uuid
    seen = set()
    for item in batch['items']:
        if (not isinstance(item, dict) or set(item) != {'company_id', 'name', 'expected_version', 'record', 'source', 'provenance'}
                or type(item['expected_version']) is not int or item['expected_version'] < 1):
            raise ValueError('Invalid observation item')
        identifier = str(uuid.UUID(item['company_id']))
        if identifier != item['company_id'] or identifier in seen:
            raise ValueError('Duplicate/noncanonical company ID')
        seen.add(identifier)
        validate_public_certificate_observation(item['record'], item['source'], item['name'])
        if datetime.fromisoformat(item['source']['retrieved_at']) > reviewed:
            raise ValueError('Review precedes acquisition')
        validate_provenance(item, archive_root)
    return batch


def execute(batch_file, expected_hash):
    from apply_reviewed_enrichment import read_batch, _guard_network
    original, content, batch = read_batch(batch_file, expected_hash)
    _guard_network()
    import local_model
    import local_search
    import research_source_pilot as pilot
    local_model.application()
    from django.conf import settings
    from django.test import override_settings
    from portal.baichuan_facts import record_public_certificate_observation, public_certificate_observation_identity
    from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision, BaichuanMatchSnapshot
    from portal.baichuan_models import Company, CompanyQualification, CompanyPerson
    from portal.baichuan_service import require_access
    from portal.models import ModelCallLog, User
    runtime = local_search._runtime()
    archive = runtime / 'independent-enrichment-20261017'
    validate_batch(batch, archive)
    source = json.loads((ROOT / 'doc/baichuan-sdd/ai-assistant/checkpoint.json').read_text(encoding='utf-8'))['source_workbook']
    source_hash = batch['source_workbook_sha256']
    db = local_search._plain_path(settings.DATABASES['default']['NAME'])
    restore = runtime / ('source-restore-' + source_hash[:8])
    state = local_model.local.source_state()
    if (runtime != local_model.local.RUNTIME or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3'
            or db != runtime / 'portal.sqlite3' or source.get('sha256') != source_hash
            or state.get('source_connected') is not True or state.get('source_sha256') != source_hash
            or state.get('imported_company_count') != 1283 or Company.objects.count() != 1283
            or pilot.sha256(local_search._plain_path(source['path'])) != source_hash
            or pilot.sha256(local_search._plain_path(restore / 'original.xlsx')) != source_hash
            or settings.BAICHUAN_RESEARCH_ENABLED or settings.BAICHUAN_FACT_WRITE_ENABLED
            or getattr(settings, 'BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED', False)):
        raise ValueError('Owned original-source DB and all default-off gates required')
    manifest = json.loads((restore / 'reviewed-manifest.json').read_text(encoding='utf-8'))
    records = {r['id']: r for r in manifest['records']}
    if len(records) != 1283 or set(records) != {str(pk) for pk in Company.objects.values_list('pk', flat=True)}:
        raise ValueError('Restored catalog identity set differs')
    accounts = json.loads((runtime / 'accounts.json').read_text(encoding='utf-8'))['accounts']
    actor = User.objects.get(username=next(a['username'] for a in accounts if a['role'] == 'general_manager'))
    require_access(actor, write=True)
    import msvcrt
    lock_path = local_search._plain_path(runtime / 'reviewed-enrichment.lock')
    with lock_path.open('a+b') as lock:
        lock.seek(0)
        lock.write(b'1')
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            # Full preflight under the common maintenance lock before any backup/write.
            with override_settings(BAICHUAN_FACT_WRITE_ENABLED=True, BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED=True):
                for item in batch['items']:
                    company = Company.objects.get(pk=item['company_id'])
                    if company.name != item['name'] or records[str(company.pk)]['company']['name'] != company.name:
                        raise ValueError('Exact current/restored legal-name binding required')
                    record_public_certificate_observation(actor, company.pk, item['record'], item['source'],
                        item['expected_version'], scope=settings.BAICHUAN_ASSISTANT_SCOPE, validate_only=True)
            out = local_search._plain_path(runtime / ('public-certificates-' + expected_hash))
            out.mkdir(exist_ok=True, mode=0o700)
            # Apply the same private Windows ownership rule as the existing maintenance CLI.
            import csv, io, subprocess
            identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
            sid = list(csv.reader(io.StringIO(identity.stdout.strip())))[0][-1]
            if not re.fullmatch(r'S-1-[0-9-]+', sid):
                raise ValueError('Current Windows identity unavailable')
            subprocess.run(['icacls', str(out), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F'], capture_output=True, check=True)
            state_path = out / 'state.json'
            if state_path.exists():
                checkpoint = json.loads(state_path.read_text(encoding='utf-8'))
                if checkpoint['batch_sha256'] != expected_hash or sha(checkpoint['backup']['file']) != checkpoint['backup']['sha256'] or sha(out / 'batch.json') != expected_hash:
                    raise ValueError('Resume archive or original backup changed')
            else:
                if any(out.iterdir()):
                    raise ValueError('Unknown incomplete operation retained; refusing overwrite')
                backup = pilot.online_backup(db, out / 'before.sqlite3')
                (out / 'batch.json').write_bytes(content)
                checkpoint = {'status': 'running', 'kind': batch['kind'], 'batch_sha256': expected_hash, 'backup': backup, 'items': {}}
                local_search._private_create(state_path, checkpoint)
            before_calls = ModelCallLog.objects.count()
            old_certificates = {str(c['id']): c for c in BaichuanCertificate.objects.values()}
            old_evidence_ids = list(BaichuanEvidence.objects.values_list('pk', flat=True))
            old_revision_ids = list(BaichuanFactRevision.objects.values_list('pk', flat=True))
            def digest(values):
                return hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()
            def protected():
                company_fields = [f.attname for f in Company._meta.concrete_fields if f.attname not in {'version','updated_at','updated_by_id'}]
                return digest({'company': list(Company.objects.order_by('pk').values(*company_fields)),
                    'qualifications': list(CompanyQualification.objects.order_by('pk').values()),
                    'people': list(CompanyPerson.objects.order_by('pk').values()),
                    'old_certificates': list(BaichuanCertificate.objects.filter(pk__in=old_certificates).order_by('pk').values()),
                    'old_evidence': list(BaichuanEvidence.objects.filter(pk__in=old_evidence_ids).order_by('pk').values()),
                    'old_revisions': list(BaichuanFactRevision.objects.filter(pk__in=old_revision_ids).order_by('pk').values()),
                    'old_snapshots': list(BaichuanMatchSnapshot.objects.order_by('pk').values()),
                    'users': list(User.objects.order_by('pk').values())})
            preserved = protected()
            created = replayed = conflicts = 0
            with override_settings(BAICHUAN_FACT_WRITE_ENABLED=True, BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED=True):
                for item in batch['items']:
                    result = record_public_certificate_observation(actor, item['company_id'], item['record'], item['source'],
                        item['expected_version'], scope=settings.BAICHUAN_ASSISTANT_SCOPE)
                    created += not result['replayed']
                    replayed += result['replayed']
                    conflicts += bool(result['conflicts'])
                    checkpoint['items'][item['company_id']] = result
                    temporary = out / ('state-' + str(__import__('uuid').uuid4()) + '.new')
                    local_search._private_create(temporary, checkpoint)
                    temporary.replace(state_path)
            if (protected() != preserved or ModelCallLog.objects.count() != before_calls or Path(original).read_bytes() != content
                    or settings.BAICHUAN_FACT_WRITE_ENABLED or getattr(settings, 'BAICHUAN_PUBLIC_CERTIFICATE_WRITE_ENABLED', False)):
                raise ValueError('Post-commit preservation failed; archive/checkpoint/backup retained')
            checkpoint.update(status='completed', created_this_run=created, replayed_this_run=replayed,
                same_number_review_conflicts=conflicts, model_calls=0, HTTP=0, verified_certificates_added=0)
            temporary = out / ('state-' + str(__import__('uuid').uuid4()) + '.new')
            local_search._private_create(temporary, checkpoint)
            temporary.replace(state_path)
            return {key: value for key, value in checkpoint.items() if key not in {'items', 'backup'}}
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--batch')
    parser.add_argument('--batch-sha256')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'inert', 'SQL': 0, 'database_writes': 0, 'HTTP': 0, 'model': 0,
            'requires': '--execute --batch PATH --batch-sha256 HASH'}))
        return
    if not args.batch or not re.fullmatch('[a-f0-9]{64}', args.batch_sha256 or ''):
        parser.error('Explicit batch path and complete SHA256 required')
    try:
        result = execute(args.batch, args.batch_sha256)
    except Exception:
        parser.exit(2, 'Public certificate maintenance stopped; preserve batch, checkpoint and original backup.\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
