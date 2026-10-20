"""Owned source-restore evidence repair. Default is inert; never calls a model/web.

Run with the company-test interpreter. --execute requires the original workbook
SHA256 and independently checks original bytes, reviewed import rows, current
IDs and every legacy declaration before creating a fresh online backup.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    temporary.replace(path)


def execute(source_hash):
    import local_model
    import research_source_pilot as pilot
    local_model.application()
    from django.conf import settings
    from portal.baichuan_assistant_models import BaichuanCertificate, BaichuanEvidence, BaichuanFactRevision
    from portal.baichuan_legacy_evidence import backfill_legacy_source_evidence, plan_legacy_source_links
    from portal.baichuan_models import Company, CompanyQualification
    from portal.baichuan_service import require_access
    from portal.baichuan_source import _qualification
    from portal.baichuan_import import _source
    from portal.models import ModelCallLog, User

    local = local_model.local
    runtime = local.RUNTIME.resolve()
    source = read(ROOT / 'doc/baichuan-sdd/ai-assistant/checkpoint.json')['source_workbook']
    restore = runtime / ('source-restore-' + source_hash[:8])
    state = local.source_state()
    receipt = read(restore / 'verification-receipt.json')
    original = Path(source['path']).resolve(strict=True)
    if (runtime != ROOT / '.runtime/baichuan-ai-local' or local.RUNTIME.is_symlink()
            or local.read_json(runtime / 'environment.json').get('kind') != local.IDENTITY
            or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3'
            or Path(settings.DATABASES['default']['NAME']).resolve() != runtime / 'portal.sqlite3'
            or source.get('sha256') != source_hash or state.get('source_sha256') != source_hash
            or state.get('source_connected') is not True or state.get('imported_company_count') != 1283
            or receipt.get('original_unchanged') is not True or receipt.get('source_sha256') != source_hash
            or Company.objects.count() != 1283 or CompanyQualification.objects.count() != 1460
            or pilot.sha256(original) != source_hash or pilot.sha256(restore / 'original.xlsx') != source_hash
            or settings.BAICHUAN_RESEARCH_ENABLED or settings.BAICHUAN_FACT_WRITE_ENABLED):
        raise ValueError('Owned original-source database/hash/default-off confirmation failed')
    manifest = read(restore / 'reviewed-manifest.json')
    records = {row['id']: row for row in manifest['records']}
    if len(records) != 1283 or set(records) != set(str(pk) for pk in Company.objects.values_list('pk', flat=True)):
        raise ValueError('Catalog ID set differs from independently reviewed restoration')
    accounts = local.read_json(runtime / 'accounts.json')['accounts']
    actor = User.objects.get(username=next(row['username'] for row in accounts if row['role'] == 'general_manager'))
    require_access(actor, write=True)
    claims = read(restore / 'normalized/claims.json')
    claim_sources = {}
    for claim in claims:
        item, _ = _qualification(claim)
        if item:
            own = claim_sources.setdefault(claim['company_name'], {})
            if item['source'] in own:
                raise ValueError('Ambiguous repeated claim source text; no guessed locator')
            positions = claim['source_rows']
            own[item['source']] = {'sheet': positions['summary']['sheet'], 'row': positions['summary']['row'],
                'section': {'sheet': positions['detail']['sheet'], 'row': positions['detail']['row']}}
    out = runtime / ('source-evidence-' + source_hash[:12])
    out.mkdir(exist_ok=True)
    # Windows releases this lock even after interruption; the durable plan/state
    # remains available for an explicit same-command resume.
    import msvcrt
    with (out / 'operation.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'1')
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            calls_before = ModelCallLog.objects.count()
            baseline = pilot.catalog_digest()
            plan, counts = [], Counter()
            for company in Company.objects.order_by('pk').iterator():
                expected = records[str(company.pk)]
                if company.version != expected['version'] or any(getattr(company, key) != value for key, value in expected['company'].items()):
                    raise ValueError('Company changed since reviewed source import; do not overwrite')
                qualification_rows = {str(row.pk): row for row in company.qualifications.all()}
                if set(qualification_rows) != {item['id'] for item in expected['qualifications']}:
                    raise ValueError('Legacy qualification ID set differs from reviewed import')
                contexts = {}
                # Reuse the importer's exact provenance append operation. Its
                # reviewed intermediate workbook hash/row/notes are part of the
                # stored source; do not strip them or match a prose substring.
                imported_sources = {_source(text, expected['source'], manifest['file_sha256'],
                    manifest['mapping']['notes_reviewed'].get(expected['source'])): locator
                    for text, locator in claim_sources.get(expected['company']['name'], {}).items()}
                for item in expected['qualifications']:
                    legacy = qualification_rows[item['id']]
                    if any((getattr(legacy, key).isoformat() if key in {'valid_until', 'verified_on'} and getattr(legacy, key) else getattr(legacy, key)) != value
                           for key, value in item.items() if key != 'id'):
                        raise ValueError('Legacy declaration differs from reviewed import')
                    if legacy.source not in imported_sources:
                        raise ValueError('Legacy source lacks exact normalized-claim match')
                    contexts[str(legacy.pk)] = {'source': legacy.source, 'source_sha256': hashlib.sha256(legacy.source.encode()).hexdigest(),
                        'locator': imported_sources[legacy.source], 'import_ref': 'sha256:' + source_hash}
                entries = plan_legacy_source_links(company, source_context_by_legacy_id=contexts)
                if len(entries) != len(qualification_rows):
                    raise ValueError('Mapped certificate count differs from source qualifications')
                counts.update(entry['action'] for entry in entries)
                plan.append({'company_id': str(company.pk), 'version': company.version, 'contexts': contexts})
            if counts['empty_source'] or counts['link'] + counts['already_linked'] != 1460:
                raise ValueError('Full preflight expected1460 links with no empty/conflicting declaration')
            prior = read(out / 'state.json') if (out / 'state.json').exists() else None
            if prior and prior['catalog_digest_before'] != baseline:
                raise ValueError('Catalog changed since evidence repair checkpoint')
            if prior and prior.get('status') == 'completed' and counts['link'] == 0:
                replay = {'kind': 'source_evidence_replay_v1', 'created': 0, 'already_linked': counts['already_linked'],
                    'model_call_delta': ModelCallLog.objects.count() - calls_before, 'catalog_digest_unchanged': True}
                write(out / 'replay.json', replay)
                return replay
            if not prior:
                backup = pilot.online_backup(runtime / 'portal.sqlite3', out / ('before-' + time.strftime('%Y%m%d-%H%M%S') + '.sqlite3'))
                prior = {'kind': 'source_evidence_repair_v1', 'source_sha256': source_hash, 'backup': backup,
                    'catalog_digest_before': baseline, 'model_calls_before': calls_before, 'preflight': dict(counts),
                    'status': 'running', 'completed_companies': [], 'created': 0}
                write(out / 'plan.json', plan)
                write(out / 'state.json', prior)
            else:
                backup_file = Path(prior['backup']['file'])
                if not backup_file.is_file() or pilot.sha256(backup_file) != prior['backup']['sha256']:
                    raise ValueError('Original online backup is unavailable; refusing resume')
            created_this_attempt = 0
            for entry in plan:
                company = Company.objects.get(pk=entry['company_id'])
                result = backfill_legacy_source_evidence(company, actor, expected_version=entry['version'],
                    source_context_by_legacy_id=entry['contexts'])
                prior['created'] += result['created']
                created_this_attempt += result['created']
                if entry['company_id'] not in prior['completed_companies']:
                    prior['completed_companies'].append(entry['company_id'])
                write(out / 'state.json', prior)
            after = pilot.catalog_digest()
            evidence_count = BaichuanEvidence.objects.filter(scope=settings.BAICHUAN_ASSISTANT_SCOPE,
                source_type='legacy_import', import_ref='sha256:' + source_hash).count()
            linked = BaichuanCertificate.objects.filter(legacy_qualification_id__isnull=False, evidence__source_type='legacy_import',
                evidence__scope=settings.BAICHUAN_ASSISTANT_SCOPE, evidence__import_ref='sha256:' + source_hash).count()
            for company in Company.objects.order_by('pk').iterator():
                if any(entry['action'] != 'already_linked' for entry in plan_legacy_source_links(company,
                        source_context_by_legacy_id=next(row['contexts'] for row in plan if row['company_id'] == str(company.pk)))):
                    raise ValueError('Post-repair scope/subject/revision/source replay validation failed')
            if after != baseline or linked != 1460 or evidence_count != 1460 or ModelCallLog.objects.count() != calls_before:
                raise ValueError('Post-repair integrity/count/model-call check failed; preserve checkpoint')
            # Reconstruct from durable DB facts: an interruption after commit but
            # before state.json must never permanently undercount completed links.
            prior.update(status='completed', created=evidence_count, created_this_attempt=created_this_attempt,
                catalog_digest_after=after, evidence_count=evidence_count, linked_certificates=linked,
                model_call_delta=ModelCallLog.objects.count() - calls_before, company_count=1283, verified_evidence=BaichuanEvidence.objects.filter(
                    scope=settings.BAICHUAN_ASSISTANT_SCOPE, source_type='legacy_import', import_ref='sha256:' + source_hash,
                    access_status='verified').count(), source_link_revisions=BaichuanFactRevision.objects.filter(
                    field='legacy_source_evidence_link', evidence__scope=settings.BAICHUAN_ASSISTANT_SCOPE,
                    evidence__import_ref='sha256:' + source_hash).count())
            write(out / 'state.json', prior)
            return {key: prior[key] for key in ('status', 'created', 'linked_certificates', 'company_count', 'verified_evidence', 'model_call_delta')}
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'inert', 'database_writes': 0, 'network_calls': 0,
                          'requires': '--execute --source-sha256 ORIGINAL_HASH'}))
        return
    if not args.source_sha256 or len(args.source_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in args.source_sha256):
        parser.error('Original lowercase SHA256 is required')
    print(json.dumps(execute(args.source_sha256), ensure_ascii=True))


if __name__ == '__main__':
    main()
