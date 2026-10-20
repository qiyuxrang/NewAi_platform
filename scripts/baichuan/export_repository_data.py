"""Export the owned local company catalog without users, sessions or messages.

This command only reads SQLite, creates a new interchange directory, and never
imports into a live database. The GitHub publication decision is separate.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.runtime/baichuan-ai-local'
TABLES = (
    'portal_company', 'portal_companyqualification', 'portal_companyperson',
    'portal_baichuanevidence', 'portal_baichuanfactrevision',
    'portal_baichuancertificate', 'portal_baichuanqualificationrule',
    'portal_baichuanresearchmanifest', 'portal_baichuanresearchitem',
)
SOURCE_PREFIXES = (
    'independent-enrichment-', 'source-restore-', 'source-evidence-',
    'research-source-', 'public-certificates-', 'reviewed-enrichment-',
)
PRUNED = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'tools',
          'dist', 'build', 'site-packages', 'playwright', 'browser-profile',
          'profiles', 'user-data', '.cache', 'cache'}
BODY_EXTENSIONS = {'.html', '.pdf', '.txt', '.raw'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def rows_from(db, table):
    return [dict(row) for row in db.execute('SELECT * FROM "' + table + '" ORDER BY id')]


def validate(directory):
    """Independently read every exported row/blob and check internal relations."""
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    data = {}
    for table, item in manifest['tables'].items():
        path = directory / item['file']
        assert digest(path) == item['sha256'], table
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert len(rows) == item['rows'], table
        assert len({row['id'] for row in rows}) == len(rows), table
        assert hashlib.sha256(b'\n'.join(encode(row) for row in rows)).hexdigest() == item['rows_sha256'], table
        data[table] = rows
    for table, rows in data.items():
        for relation in manifest['tables'][table]['foreign_keys']:
            target, source_column, target_column = relation[2], relation[3], relation[4]
            if target not in data:
                continue  # Explicit external actor/job references; no auth/job rows exported.
            target_ids = {row[target_column] for row in data[target]}
            assert all(row[source_column] is None or row[source_column] in target_ids for row in rows), (table, source_column)
    for item in manifest['files']:
        path = directory / item['file']
        assert path.stat().st_size == item['bytes'] and digest(path) == item['sha256']
    index = json.loads((directory / 'source-index.json').read_text(encoding='utf-8'))
    validated = set()
    for item in index:
        if item['blob'] not in validated:
            body = gzip.decompress((directory / item['blob']).read_bytes())
            assert len(body) == item['bytes'] and hashlib.sha256(body).hexdigest() == item['sha256']
            validated.add(item['blob'])
    with (directory / 'companies.csv').open(encoding='utf-8-sig', newline='') as stream:
        companies = list(csv.DictReader(stream))
    assert len(companies) == len(data['portal_company'])
    return {'status': 'PASS', 'tables': len(data), 'rows': sum(len(v) for v in data.values()),
            'companies': len(companies), 'source_paths': len(index), 'unique_source_blobs': len(validated),
            'internal_foreign_keys': 'PASS', 'original_database_writes': 0}


def export(output):
    output = output.resolve()
    assert not output.exists(), 'Use a fresh output directory; existing datasets are never overwritten'
    assert not output.is_relative_to(RUNTIME), 'Use a separate repository interchange directory'
    assert json.loads((RUNTIME / 'environment.json').read_text(encoding='utf-8'))['kind'] == 'baichuan_ai_isolated_local_v1'
    db_path = (RUNTIME / 'portal.sqlite3').resolve(strict=True)
    assert db_path.parent == RUNTIME.resolve() and not (RUNTIME / 'portal.sqlite3').is_symlink()
    output.mkdir(parents=True)
    (output / 'tables').mkdir()
    (output / 'sources').mkdir()
    manifest = {'format': 'baichuan-company-interchange-v1', 'captured_at': datetime.now(timezone.utc).isoformat(),
                'source_kind': 'owned_local_original_workbook_with_existing_enrichment',
                'historical_enriched_database_restored': False,
                'original_sdd_research_complete': False,
                'excluded': ['account/password/token/secret tables', 'sessions', 'model configuration and logs',
                             'conversation/message/query/export jobs', 'private uploaded tender documents',
                             'browser profiles', 'trial/production databases', 'installed tools/dependencies'],
                'external_references': 'Actor and research job IDs are audit metadata only; their referenced rows are deliberately excluded. Restore requires explicit destination actor/job mapping.',
                'tables': {}, 'files': []}
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for table in TABLES:
            rows = rows_from(db, table)
            relative = 'tables/' + table + '.jsonl'
            path = output / relative
            body = b'\n'.join(encode(row) for row in rows)
            path.write_bytes(body + (b'\n' if rows else b''))
            manifest['tables'][table] = {'file': relative, 'rows': len(rows), 'sha256': digest(path),
                'rows_sha256': hashlib.sha256(body).hexdigest(),
                'columns': [dict(row) for row in db.execute('PRAGMA table_info("' + table + '")')],
                'foreign_keys': [list(row) for row in db.execute('PRAGMA foreign_key_list("' + table + '")')],
                'original_schema': db.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?', (table,)).fetchone()[0]}
            if table == 'portal_company':
                with (output / 'companies.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
                    writer.writeheader()
                    writer.writerows(rows)
                manifest['coverage_nonempty'] = {field: sum(bool(str(row[field] or '').strip()) for row in rows)
                    for field in ('website', 'phone', 'address', 'email', 'province', 'city', 'contact_name', 'contact_phone')}
        db.rollback()
    # Original/reviewed spreadsheets are company source material, not conversation uploads.
    exact = {'original.xlsx', 'reviewed-source.xlsx', 'reviewed-manifest.json', 'verification-receipt.json',
             'field-baseline.json', 'rules-install-receipt.json'}
    paths = []
    for directory in sorted(RUNTIME.iterdir()):
        if not directory.is_dir() or not directory.name.startswith(SOURCE_PREFIXES):
            continue
        for base, names, files in os.walk(directory, followlinks=False):
            names[:] = sorted(n for n in names if n not in PRUNED and not (Path(base) / n).is_symlink())
            for name in sorted(files):
                path = Path(base) / name
                if path.is_symlink():
                    continue
                if path.suffix.lower() in BODY_EXTENSIONS or (directory.name.startswith('source-restore-') and name in exact):
                    paths.append(path)
    index = []
    for path in paths:
        raw = path.read_bytes()
        hash_value = hashlib.sha256(raw).hexdigest()
        relative = 'sources/' + hash_value + '.gz'
        blob = output / relative
        if not blob.exists():
            blob.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
        index.append({'original_path': path.relative_to(ROOT).as_posix(), 'blob': relative,
                      'sha256': hash_value, 'bytes': len(raw), 'original_suffix': path.suffix})
    write_json(output / 'source-index.json', index)
    for path in sorted(output.rglob('*')):
        if path.is_file():
            manifest['files'].append({'file': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    write_json(output / 'manifest.json', manifest)
    receipt = validate(output)
    write_json(output / 'validation.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        parser.error('Choose exactly one of --output or --verify')
    if args.verify:
        print(json.dumps(validate(args.verify.resolve()), ensure_ascii=False))
    else:
        export(args.output)
