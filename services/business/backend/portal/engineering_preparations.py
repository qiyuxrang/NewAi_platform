"""Versioned preparation; preflight never starts a cost run."""
import hashlib
import json
import subprocess
import sqlite3
import uuid
from contextlib import closing
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import F, Q
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .engineering_api import (EngineeringError, _job_data, _region, _require_engineering,
                              engineering_endpoint)
from .engineering_models import EngineeringJob, EngineeringPreparation, EngineeringPreparationStep
from .engineering_storage import StorageError, read_upload, save_inputs, verified_input
from . import engineering_worker as worker
from .security import audit
from django.contrib.auth import get_user_model


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def cache_records(cache):
    rows_by_table = {}
    if not cache.is_file():
        return rows_by_table
    try:
        with closing(sqlite3.connect(cache.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('BEGIN')
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            for (table,) in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                rows = db.execute('SELECT * FROM ' + quoted).fetchall()
                if rows:
                    rows_by_table[table] = sorted([list(row) for row in rows], key=repr)
    except sqlite3.Error:
        raise StorageError('basis_unavailable', '本地价格缓存损坏或不可读取，请恢复后重新准备。') from None
    return rows_by_table


def fingerprint(config):
    """Pin local executable code, configuration and price libraries (exclude outputs)."""
    cli = Path(config['cli'])
    root = cli.parent.parent
    data = Path(worker._configured('ENGINEERING_DATA_ROOT', 'PORTAL_ENGINEERING_DATA_ROOT') or root / 'data')
    paths = {cli}
    for folder in (root / 'engine', root / 'tools', root / 'config', data / 'library'):
        if folder.is_dir():
            paths.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    # The legacy engine lazily creates an empty web cache even in offline mode.
    # Pin its logical records, so creating an empty DB is not a price change;
    # adding/changing a cached price remains a change and blocks execution.
    cache = data / 'library' / '网价缓存.sqlite'
    cache_rows = cache_records(cache)
    values = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
              if p != cache and not p.name.startswith(cache.name + '-')}
    values[str(cache.resolve())] = digest(cache_rows)
    return digest(values)


def basis_for(prep, config):
    return {'version': prep.version, 'region': prep.region,
            'files': [{k: f[k] for k in ('name', 'size', 'sha256')} for f in prep.inputs],
            'rules_sha256': fingerprint(config), 'online_allowed': False,
            'classification': 'internal_draft', 'recovery': 'whole_input_cost_stage'}


def data(prep):
    return {'id': str(prep.pk), 'version': prep.version, 'state': prep.state,
            'basis': prep.basis, 'basis_sha256': prep.basis_sha256,
            'inspection': prep.inspection, 'error_code': prep.error_code,
            'files': [{k: f[k] for k in ('name', 'size', 'sha256')} for f in prep.inputs],
            'region': prep.region, 'history': prep.history,
            'confirmed_at': prep.confirmed_at.isoformat() if prep.confirmed_at else None,
            'confirmed_by': prep.confirmed_by_id,
            'steps': [{'name': step.name, 'version': step.version, 'sha256': step.sha256}
                      for step in prep.steps.order_by('version', 'created_at')],
            'job': _job_data(prep.job) if prep.job_id else None}


def owned(user, pk, lock=False):
    query = EngineeringPreparation.objects.select_related('job')
    if lock:
        query = query.select_for_update(of=('self',))
    prep = query.filter(pk=pk, owner=user).first()
    if prep is None:
        raise EngineeringError('not_found', '准备记录不存在。', 404)
    return prep


def uploads(request):
    if not isinstance(request.data, Mapping) or set(request.data) - {'files', 'region', 'expected_version'}:
        raise EngineeringError('invalid_request', '请求字段无效。')
    items = request.FILES.getlist('files')
    if not 1 <= len(items) <= 2:
        raise EngineeringError('invalid_request', '请上传1～2份 XLSX 清单。')
    return [read_upload(f) for f in items]


@api_view(['GET', 'POST'])
@engineering_endpoint
def preparations(request):
    _require_engineering(request)
    if request.method == 'GET':
        return Response({'preparations': [data(p) for p in EngineeringPreparation.objects.filter(owner=request.user).select_related('job')]})
    if not isinstance(request.data, Mapping) or set(request.data) - {'files', 'region'}:
        raise EngineeringError('invalid_request', '请求字段无效。')
    files = uploads(request)
    region = _region(request)
    key = request.headers.get('Idempotency-Key', '')
    if not key or len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise EngineeringError('invalid_request', '请提供有效的 Idempotency-Key。')
    payload_hash = digest({'region': region, 'files': [{'name': name, 'sha256': hashlib.sha256(content).hexdigest()}
                                                     for name, content in files]})
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        previous = EngineeringPreparation.objects.filter(owner=request.user, idempotency_key=key).first()
        if previous:
            if previous.payload_sha256 != payload_hash:
                raise EngineeringError('idempotency_conflict', '相同提交标识已用于不同的清单或地区。', 409)
            return Response(data(previous))
        prep = EngineeringPreparation.objects.create(owner=request.user, region=region,
            idempotency_key=key, payload_sha256=payload_hash)
        prep.inputs = save_inputs(uuid.uuid4(), files)
        prep.save(update_fields=['inputs'])
        audit(request.user, 'engineering_prepare', prep.pk)
    return Response(data(prep), status=201)


@api_view(['GET'])
@engineering_endpoint
def detail(request, pk):
    _require_engineering(request)
    return Response(data(owned(request.user, pk)))


@api_view(['POST'])
@engineering_endpoint
def revise(request, pk):
    _require_engineering(request)
    files = uploads(request)
    with transaction.atomic():
        prep = owned(request.user, pk, True)
        if str(request.data.get('expected_version')) != str(prep.version):
            raise EngineeringError('version_conflict', '准备版本已变化，请刷新。', 409)
        if prep.job_id:
            raise EngineeringError('already_confirmed', '已执行的依据保留为历史，请创建新的准备记录。', 409)
        prep.history.append({'version': prep.version, 'basis': prep.basis, 'basis_sha256': prep.basis_sha256})
        prep.version += 1
        prep.fence += 1
        prep.region = _region(request)
        prep.inputs = save_inputs(uuid.uuid4(), files)
        prep.inspection, prep.basis, prep.basis_sha256 = {}, {}, ''
        prep.state, prep.error_code, prep.attempt_count, prep.lease_until = 'queued', '', 0, None
        prep.save()
        audit(request.user, 'engineering_prepare_revise', prep.pk, changes=[str(prep.version)])
    return Response(data(prep))


@api_view(['POST'])
@engineering_endpoint
def retry(request, pk):
    _require_engineering(request)
    with transaction.atomic():
        prep = owned(request.user, pk, True)
        if (not isinstance(request.data, dict) or type(request.data.get('expected_version')) is not int
                or request.data != {'expected_version': prep.version} or prep.state != 'failed' or prep.job_id):
            raise EngineeringError('invalid_state', '仅可重试当前失败的准备版本。', 409)
        if prep.attempt_count >= worker.max_attempts():
            raise EngineeringError('attempt_limit', '预检重试次数已用完，请修改清单创建新版本。', 409)
        if prep.error_code != 'preflight_unavailable':
            raise EngineeringError('revision_required', '输入、授权或依据错误需修正后创建新准备版本。', 409)
        prep.state, prep.error_code = 'queued', ''
        prep.save()
    return Response(data(prep))


@api_view(['POST'])
@engineering_endpoint
def confirm(request, pk):
    _require_engineering(request)
    if not isinstance(request.data, dict):
        raise EngineeringError('invalid_request', '请提交版本和确认摘要。')
    with transaction.atomic():
        prep = owned(request.user, pk, True)
        if (type(request.data.get('expected_version')) is not int
                or request.data != {'expected_version': prep.version, 'basis_sha256': prep.basis_sha256}):
            raise EngineeringError('version_conflict', '依据已更新，请重新核对。', 409)
        if prep.job_id:
            return Response(data(prep))  # One confirmation creates exactly one job.
        config = worker.runtime_state()
        if config['status'] != 'ready':
            raise EngineeringError('worker_unavailable', config['detail'], 503)
        for item in prep.inputs:
            verified_input(item)
        step = prep.steps.filter(version=prep.version, name='preflight').first()
        if (prep.state != 'ready' or not prep.basis_sha256
                or not step or digest(step.output) != step.sha256
                or step.output != {'inspection': prep.inspection, 'basis': prep.basis}
                or digest(prep.basis) != prep.basis_sha256
                or basis_for(prep, config) != prep.basis):
            raise EngineeringError('basis_changed', '依据不可用或规则已变化，请重新预检新版本。', 409)
        job = EngineeringJob.objects.create(owner=request.user, region=prep.region, inspection=prep.inspection)
        job.inputs = save_inputs(job.pk, [(f['name'], verified_input(f).read_bytes()) for f in prep.inputs])
        job.save(update_fields=['inputs'])
        prep.job, prep.state = job, 'confirmed'
        prep.confirmed_by, prep.confirmed_at = request.user, timezone.now()
        prep.save()
        audit(request.user, 'engineering_prepare_confirm', prep.pk, changes=[prep.basis_sha256])
    return Response(data(prep))


def run_once():
    config = worker.runtime_state()
    if config['status'] != 'ready':
        return False
    now = timezone.now()
    eligible = Q(state='queued') | Q(state='running', lease_until__lte=now)
    EngineeringPreparation.objects.filter(eligible, attempt_count__gte=worker.max_attempts()).update(state='failed', error_code='attempt_limit', lease_until=None)
    snapshot = EngineeringPreparation.objects.filter(eligible, attempt_count__lt=worker.max_attempts()).order_by('created_at').first()
    if snapshot is None:
        return False
    fence = snapshot.fence + 1
    if not EngineeringPreparation.objects.filter(pk=snapshot.pk, fence=snapshot.fence).filter(eligible).update(
            state='running', fence=fence, attempt_count=F('attempt_count') + 1,
            lease_until=now + timedelta(seconds=worker.timeout_seconds() + 60)):
        return True
    error, inspection, basis = '', {}, {}
    try:
        if not worker._engineering_allowed(snapshot.owner):
            raise StorageError('permission_changed', '授权已变化。')
        paths = [verified_input(f) for f in snapshot.inputs]
        basis = basis_for(snapshot, config)
        code, payload = worker._invoke(config, 'inspect', paths)
        inspection = worker._inspection(payload, snapshot.inputs)
        if code != 0 or not inspection['ok']:
            error = 'preflight_failed'
        elif basis != basis_for(snapshot, config):
            error = 'basis_changed'
    except StorageError as exc:
        error = exc.code
    except (OSError, ValueError, worker.WorkerUnavailable, subprocess.TimeoutExpired):
        error = 'preflight_unavailable'
    with transaction.atomic():
        prep = EngineeringPreparation.objects.select_for_update().filter(pk=snapshot.pk, fence=fence,
            state='running', lease_until__gt=timezone.now()).first()
        if prep is None:
            return True
        if not worker._engineering_allowed(prep.owner):
            error = 'permission_changed'
        prep.inspection, prep.basis = inspection, basis
        prep.basis_sha256 = digest(basis) if not error else ''
        prep.state, prep.error_code, prep.lease_until = ('failed' if error else 'ready'), error, None
        prep.save()
        if not error:
            output = {'inspection': inspection, 'basis': basis}
            EngineeringPreparationStep.objects.update_or_create(preparation=prep, version=prep.version,
                name='preflight', defaults={'output': output, 'sha256': digest(output)})
    return True


def guard_confirmed_job(job, config):
    prep = EngineeringPreparation.objects.filter(job=job).first()
    if prep is None:
        return None
    if config['status'] != 'ready':
        raise StorageError('basis_unavailable', '工程运行环境已变化。')
    step = prep.steps.filter(version=prep.version, name='preflight').first()
    if (prep.state != 'confirmed' or not step or digest(step.output) != step.sha256
            or step.output != {'inspection': prep.inspection, 'basis': prep.basis}
            or digest(prep.basis) != prep.basis_sha256 or basis_for(prep, config) != prep.basis
            or [{k: f[k] for k in ('name', 'size', 'sha256')} for f in job.inputs] != prep.basis['files']
            or job.region != prep.region):
        raise StorageError('basis_changed', '已确认的输入或规则已变化，请重新准备。')
    return prep


urlpatterns = [path('', preparations), path('<uuid:pk>/', detail),
               path('<uuid:pk>/revisions/', revise), path('<uuid:pk>/confirm/', confirm),
               path('<uuid:pk>/retry/', retry)]
