"""Explicit offline restoration of the public snapshot into an empty owned catalog.

Never merges/overwrites existing company data. Authentication, private model
configuration and historical task execution are deliberately not restored.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import export_repository_data as snapshot

ROOT = Path(__file__).resolve().parents[2]


def checked_snapshot(directory):
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('Snapshot symlinks are not allowed')
    directory = directory.resolve(strict=True)
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf8'))
    if set(manifest['tables']) != set(snapshot.TABLES):
        raise ValueError('Snapshot table allowlist mismatch')
    # Do not allow a manifest to read outside the explicitly selected snapshot.
    paths = [item['file'] for item in manifest['tables'].values()]
    paths += [item['file'] for item in manifest['files']]
    index = json.loads((directory/'source-index.json').read_text(encoding='utf8'))
    paths += [item['blob'] for item in index]
    for name in paths:
        path = directory/name
        if Path(name).is_absolute() or not path.resolve(strict=True).is_relative_to(directory):
            raise ValueError('Snapshot path escapes directory')
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Snapshot symlinks are not allowed')
    validation = snapshot.validate(directory)
    rows = {table:[json.loads(line) for line in (directory/item['file']).read_text(encoding='utf8').splitlines()]
            for table,item in manifest['tables'].items()}
    for table, items in rows.items():
        columns = [c['name'] for c in manifest['tables'][table]['columns']]
        if any(not c.replace('_','').isalnum() for c in columns):
            raise ValueError('Invalid column identifier')
        if any(set(row) != set(columns) for row in items):
            raise ValueError('Snapshot row columns mismatch')
    return manifest, rows, validation


def restore(database, directory, actor_id, backup_directory):
    """Restore only after all bytes pass validation; one atomic catalog transaction.

    Actor references are explicitly mapped to the destination operator. Original
    actor IDs remain in the immutable snapshot and are listed in the receipt.
    Required job references become cancelled archive stubs, never runnable jobs.
    """
    manifest, rows, validation = checked_snapshot(directory)
    if any(p.is_symlink() for p in (database, *database.parents, backup_directory, *backup_directory.parents)) or backup_directory.exists():
        raise ValueError('Use an existing real database and a new backup directory')
    database = database.resolve(strict=True)
    with closing(sqlite3.connect(database.as_uri()+'?mode=rw',uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            if any(db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in snapshot.TABLES):
                raise ValueError('Catalog is not empty; existing data is never merged or overwritten')
            if not db.execute('SELECT 1 FROM portal_user WHERE id=? AND is_active=1',(actor_id,)).fetchone():
                raise ValueError('Destination actor must be an existing active user')
            for table, item in manifest['tables'].items():
                actual = {r[1] for r in db.execute('PRAGMA table_info("'+table+'")')}
                if actual != {c['name'] for c in item['columns']}:
                    raise ValueError('Migrate destination schema first: '+table)
            # Separate read-only connection uses SQLite Backup API (including WAL).
            backup_directory.mkdir(parents=True,exist_ok=False)
            if os.name == 'nt':
                principal = os.environ.get('USERDOMAIN','')+'\\'+os.environ['USERNAME']
                subprocess.run(['icacls',str(backup_directory),'/inheritance:r','/grant:r',principal+':(OI)(CI)F'],
                               capture_output=True,check=True)
            else:
                backup_directory.chmod(0o700)
            with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as source:
                with closing(sqlite3.connect(backup_directory/'before.sqlite3')) as target:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Backup integrity check failed')
            now = datetime.now(timezone.utc).isoformat()
            archived = []
            for item in rows['portal_baichuanresearchmanifest']:
                if db.execute('SELECT 1 FROM portal_baichuanjob WHERE id=?',(item['job_id'],)).fetchone():
                    raise ValueError('Research job ID conflicts with destination')
                stub = dict(id=item['job_id'],created_at=now,updated_at=now,owner_id=actor_id,
                    scope=item['scope'],kind='research',status='cancelled',stage='archive_only',
                    request_hash='',payload='{}',budget='{}',checkpoint='{}',counts='{}',result_ref='{}',
                    error_code='REPOSITORY_ARCHIVE_ONLY',lease_owner='',fence=0,attempts=0,finished_at=now)
                columns = list(stub)
                db.execute('INSERT INTO portal_baichuanjob ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+
                           ','.join('?' for _ in columns)+')',[stub[c] for c in columns])
                archived.append(item['job_id'])
            mappings = {}
            expected = {}
            # All declared FK constraints are deferred until the transaction commits.
            db.execute('PRAGMA defer_foreign_keys=ON')
            for table in snapshot.TABLES:
                items = rows[table]
                actor_columns = [f[3] for f in manifest['tables'][table]['foreign_keys'] if f[2]=='portal_user']
                transformed = []
                for original in items:
                    item = dict(original)
                    for column in actor_columns:
                        if item[column] is not None:
                            mappings[str(item[column])] = actor_id
                            item[column] = actor_id
                    transformed.append(item)
                expected[table] = transformed
                if transformed:
                    columns = list(transformed[0])
                    db.executemany('INSERT INTO "'+table+'" ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+
                                   ','.join('?' for _ in columns)+')',[[r[c] for c in columns] for r in transformed])
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Foreign key validation failed')
            for table, expected_rows in expected.items():
                actual = [dict(r) for r in db.execute('SELECT * FROM "'+table+'" ORDER BY id')]
                if actual != sorted(expected_rows,key=lambda r:r['id']):
                    raise ValueError('Restored row readback differs: '+table)
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {'status':'RESTORED_EMPTY_LOCAL_CATALOG','snapshot_validation':validation,
        'snapshot_manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
        'restored_at':now,'actor_mapping':mappings,'archived_cancelled_job_ids':archived,
        'counts':{t:len(v) for t,v in rows.items()},'business_values_preserved':True,
        'actor_references_remapped':True,'live_research_resumed':False,'network_calls':0,
        'source_archives':'Preserved in data/baichuan/sources; historical paths are provenance, not executable paths',
        'backup':str(backup_directory/'before.sqlite3')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,default=ROOT/'data/baichuan')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--actor',default='baichuan-dev-product')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'VERIFY_ONLY','validation':checked_snapshot(args.snapshot)[2],
                          'database_writes':0},ensure_ascii=False))
        return
    import local_dev as local
    local.environment()  # Refuse unowned or redirected runtime; never initialize silently.
    with local.service_lock():
        state = local.RUNTIME/'processes.json'
        if state.exists() and any(local.owned(p) for p in local.read_json(state)):
            raise ValueError('Stop owned services before the explicit offline import')
        database = local.RUNTIME/'portal.sqlite3'
        if database.is_symlink() or database.resolve(strict=True) != database:
            raise ValueError('Database must be the owned local SQLite')
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            row = db.execute('SELECT id FROM portal_user WHERE username=? AND is_active=1',(args.actor,)).fetchone()
            if row is None:
                raise ValueError('Migrate and seed the owned local environment first')
        if (local.RUNTIME/'source-status.json').exists():
            raise ValueError('Existing source status retained; refusing a second source import')
        source_sha = next(i['sha256'] for i in json.loads((args.snapshot/'source-index.json').read_text(encoding='utf8'))
                          if i['original_path'].endswith('/original.xlsx'))
        backup = local.RUNTIME/'repository-imports'/uuid.uuid4().hex
        result = restore(database,args.snapshot,row[0],backup)
        local.private_json(backup/'receipt.json',result)
        # This well-known source label activates the existing explicit legacy trust policy.
        status = local.RUNTIME/'source-status.json'
        if status.exists():
            raise ValueError('Import committed; existing source status retained. See backup receipt.')
        local.private_json(status,{'source_kind':'local_original_excel','import_completed':True,
            'imported_company_count':result['counts']['portal_company'],'source_sha256':source_sha,
            'historical_enrichment_restored':False,'repository_snapshot':result['snapshot_manifest_sha256']})
        print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
