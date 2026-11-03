"""Offline prospective forecasts from research bundles, isolated from production.

This records engineering evidence only. It neither certifies historical vintages
nor promotes a model. The CLI has no clock override or network/submission path.
A completed run has completion.json; incomplete/late runs retain diagnostic bytes
without that marker and must never be counted as prospective evidence.
"""

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from finpred.data.daily_tables import FEATURE_VERSION, _root
from finpred.inference.predict import predict_rows
from finpred.labels.intraday import aware_datetime
from finpred.pipelines.daily import PipelineBlocked, TAIPEI, _at, _prediction_table, _private_file_bytes
from finpred.submission.course import _aware, _session, validate_prediction_csv
from finpred.training.fit import load_model_bundle

STATE_URL = 'https://final.html2026.csie.org/api/state'
SESSION_SCHEMA = 'shadow-session-evidence-v1'


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _persist(path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _store_directory(path):
    path.mkdir(exist_ok=True, mode=0o700)
    info = path.stat()
    if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PipelineBlocked('shadow store must be locally owned and private')


def _session_evidence(raw, template, day, now):
    record = json.loads(raw)
    if (not isinstance(record, dict) or set(record) != {
            'schema_version', 'source_url', 'fetched_at', 'tls_verified', 'session', 'template'}
            or record.get('schema_version') != SESSION_SCHEMA
            or record.get('source_url') != STATE_URL or record.get('tls_verified') is not True):
        raise PipelineBlocked('minimal verified offline session evidence required')
    template_record = record.get('template')
    if (not isinstance(template_record, dict) or set(template_record) != {
            'source_url', 'fetched_at', 'tls_verified', 'sha256'}
            or template_record.get('source_url') != (
                'https://final.html2026.csie.org/api/sample-submission?phase=2&tradingDate=' + day)
            or template_record.get('tls_verified') is not True
            or template_record.get('sha256') != _digest(template)):
        raise PipelineBlocked('offline template retrieval evidence or hash invalid')
    for acquired in (record.get('fetched_at'), template_record.get('fetched_at')):
        if not _at(day, 4) <= aware_datetime(acquired, name='offline evidence fetched_at') <= now:
            raise PipelineBlocked('session and template must have actual target-day acquisitions')
    session = record.get('session')
    if (not isinstance(session, dict) or set(session) != {'tradingDate', 'enabled', 'openAt', 'deadline'}):
        raise PipelineBlocked('offline session must contain only minimal official fields')
    session = _session({'phase2Days': [session]}, day)
    if session.get('enabled') not in (True, 1):
        raise PipelineBlocked('offline official session is disabled')
    deadline = min(_aware(session.get('deadline'), server=True), _at(day, 9))
    if not _aware(session.get('openAt'), server=True) <= now < deadline:
        raise PipelineBlocked('offline official session is not open or deadline passed')
    return record, deadline


def build_shadow_session_evidence(state, target_date, *, state_fetched_at, template_payload,
                                  template_fetched_at, tls_verified=False):
    """Pure extraction: omit account/quota/receipts and bind only observed bytes.

    The verified network adapter supplies actual retrieval times. Passing this
    function fabricated timestamps cannot establish prospective provenance.
    """
    if tls_verified is not True:
        raise PipelineBlocked('verified TLS is required for offline session evidence')
    session = _session(state, target_date)
    extracted = {name: session[name] for name in ('tradingDate', 'enabled', 'openAt', 'deadline')}
    _aware(extracted['openAt'], server=True)
    _aware(extracted['deadline'], server=True)
    validate_prediction_csv(template_payload, template_payload, target_date)
    return {
        'schema_version': SESSION_SCHEMA, 'source_url': STATE_URL,
        'fetched_at': aware_datetime(state_fetched_at, name='state fetched_at').isoformat(),
        'tls_verified': True, 'session': extracted,
        'template': {
            'source_url': 'https://final.html2026.csie.org/api/sample-submission?phase=2&tradingDate=' + target_date,
            'fetched_at': aware_datetime(template_fetched_at, name='template fetched_at').isoformat(),
            'tls_verified': True, 'sha256': _digest(template_payload),
        },
    }


def _recipe(metadata):
    return {name: metadata[name] for name in (
        'family', 'objective', 'seed', 'epochs', 'feature_version', 'feature_columns',
        'package_versions', 'code_sha256')}


def run_shadow_forecast(runtime_dir, *, trusted_model_dir, prediction_table,
                        template_path, session_evidence_path, target_date=None, clock=None):
    """Tests may inject a clock; the public CLI always reads the actual UTC clock.

    Session evidence is a locally controlled, minimal extract from an observed
    official state and template. Hashes bind bytes, not their authenticity; callers
    must obtain these through the verified collector, never construct fake dates.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = aware_datetime(clock(), name='shadow start')
    day = target_date or started.astimezone(TAIPEI).date().isoformat()
    if not _at(day, 8, 10) <= started < _at(day, 9):
        raise PipelineBlocked('shadow requires target-day 08:10-09:00 Taipei real-time window')
    root = _root(runtime_dir)
    model_directory = Path(trusted_model_dir).absolute()
    model_manifest = _private_file_bytes(model_directory / 'manifest.json')
    table_bytes = _private_file_bytes(Path(prediction_table))
    template = _private_file_bytes(Path(template_path))
    session_bytes = _private_file_bytes(Path(session_evidence_path))
    session, deadline = _session_evidence(session_bytes, template, day, started)
    table = json.loads(table_bytes)
    cutoff = _prediction_table(table, day, started)
    bundle = load_model_bundle(model_directory, trusted=True)
    metadata = bundle.metadata
    if (metadata.get('family') not in {'linear', 'hist_gbdt'}
            or metadata.get('readiness') != 'research_assumption'
            or metadata.get('production_eligible') is not False
            or metadata.get('feature_version') != FEATURE_VERSION):
        raise PipelineBlocked('shadow requires compatible stock-only linear or hist_gbdt research bundle')
    packages = metadata.get('package_versions')
    if (not isinstance(packages, dict) or set(packages) != {'scikit-learn', 'numpy', 'joblib'}
            or any(version(name) != expected for name, expected in packages.items())):
        raise PipelineBlocked('shadow model requires its recorded package versions')
    if metadata.get('code_sha256') != {
            name: _digest((Path(__file__).resolve().parents[1] / name).read_bytes())
            for name in ('training/fit.py', 'models/estimators.py', 'inference/predict.py')}:
        raise PipelineBlocked('shadow model code differs from its trained implementation')
    predictions = predict_rows(bundle, table['rows'], feature_columns=table['feature_columns'],
                               feature_version=table['feature_version'], require_production=False)
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['id', day])
    template_order = validate_prediction_csv(template, template, day)['stockIds']
    ordered = {row['stock_id']: row['prediction'] for row in predictions}
    if set(template_order) != set(ordered):
        raise PipelineBlocked('shadow prediction IDs differ from the official template')
    for stock_id in template_order:
        writer.writerow([stock_id, ordered[stock_id]])
    payload = output.getvalue().encode()
    validate_prediction_csv(payload, template, day)
    recipe = _recipe(metadata)
    recipe_bytes = _json_bytes(recipe)
    shadow = root / 'shadow'
    _store_directory(shadow)
    recipe_path = shadow / 'recipe.json'
    try:
        _persist(recipe_path, recipe_bytes)
        _sync_directory(shadow)
    except FileExistsError:
        if _private_file_bytes(recipe_path) != recipe_bytes:
            raise PipelineBlocked('shadow recipe is frozen; no configuration search across future days') from None
    package_root = Path(__file__).resolve().parents[1]
    code_hashes = {name: _digest((package_root / name).read_bytes()) for name in (
        'pipelines/shadow.py', 'pipelines/daily.py', 'data/daily_tables.py', 'features/stock.py',
        'data/training_table.py', 'inference/predict.py', 'training/fit.py', 'models/estimators.py')}
    identity_fields = {
        'target_date': day, 'model_manifest_sha256': _digest(model_manifest),
        'feature_table_sha256': _digest(table_bytes), 'session_evidence_sha256': _digest(session_bytes),
        'template_sha256': _digest(template), 'recipe_sha256': _digest(recipe_bytes),
        'csv_sha256': _digest(payload), 'code_sha256': code_hashes,
    }
    identity = _digest(_json_bytes(identity_fields))
    date_store = shadow / day
    _store_directory(date_store)
    destination = date_store / identity
    destination.mkdir(mode=0o700)  # A repeated identity must never overwrite prior bytes.
    artifacts = {
        'prediction.csv': payload, 'features.json': table_bytes, 'template.csv': template,
        'model-manifest.json': model_manifest, 'session-evidence.json': _json_bytes(session),
        'recipe.json': recipe_bytes,
    }
    completion_path = destination / 'completion.json'
    try:
        for name, content in artifacts.items():
            _persist(destination / name, content)
        _sync_directory(destination)
        persisted = aware_datetime(clock(), name='shadow artifact persistence time')
        if not started <= persisted < deadline:
            raise PipelineBlocked('shadow artifacts were not persisted before the real deadline')
        manifest = {
            'schema_version': 'prospective-shadow-v1', 'status': 'prospective_shadow',
            **identity_fields, 'identity': identity, 'generated_at': started.isoformat(),
            'predictions_persisted_at': persisted.isoformat(), 'deadline': deadline.isoformat(),
            'feature_cutoff': cutoff.isoformat(), 'model_readiness': metadata['readiness'],
            'production_eligible': False, 'model_validated_for_production': False,
            'feature_verification_scope': 'current_observed_bytes_only',
            'historical_availability_verified': False, 'submitted': False,
            'artifacts': {name: _digest(content) for name, content in artifacts.items()},
        }
        manifest_bytes = _json_bytes(manifest)
        _persist(destination / 'manifest.json', manifest_bytes)
        _sync_directory(destination)
        recorded = aware_datetime(clock(), name='shadow completion recording time')
        if not persisted <= recorded < deadline:
            raise PipelineBlocked('shadow evidence missed its real deadline')
        _persist(completion_path, _json_bytes({
            'schema_version': 'shadow-completion-v1', 'manifest_sha256': _digest(manifest_bytes),
            'recorded_at': recorded.isoformat(), 'deadline': deadline.isoformat(),
        }))
        _sync_directory(destination)
        _sync_directory(date_store)
        finished = aware_datetime(clock(), name='shadow final deadline check')
        if not recorded <= finished < deadline:
            raise PipelineBlocked('shadow completion was not persisted before its real deadline')
    except Exception:
        completion_path.unlink(missing_ok=True)
        _sync_directory(destination)
        raise
    return {'status': 'prospective_shadow', 'target_date': day, 'identity': identity,
            'directory': str(destination), 'csv_sha256': _digest(payload),
            'completed_at': finished.isoformat(), 'production_eligible': False, 'submitted': False}
