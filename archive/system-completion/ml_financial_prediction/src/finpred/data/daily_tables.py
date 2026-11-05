"""Prepare private daily tables from actual cutoff-eligible raw acquisitions.

Observing bytes before today's freeze proves today's feature availability.
It does not establish when any historical adjusted value was published; training
therefore remains research-only until a historical point-in-time adapter exists.
"""

import hashlib
import json
import os
import stat
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from finpred.data.snapshots import _exclusive_write
from finpred.data.training_table import build_research_table, read_course_archives
from finpred.features.stock import STOCK_FEATURES, stock_lags
from finpred.labels.intraday import aware_datetime

TAIPEI = ZoneInfo('Asia/Taipei')
SOURCE_URLS = {
    'course-training': 'https://final.html2026.csie.org/downloads/fin_pred_data.zip',
    'course-live': 'https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip',
}
FEATURE_VERSION = 'course-research-lags-v1'


class DailyTableError(ValueError):
    """A bounded explanation that contains no response bodies or credentials."""


def _root(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise DailyTableError('runtime must not use symlinks')
    path = path.resolve()
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise DailyTableError('daily data must remain outside Git')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise DailyTableError('runtime must be privately owned with mode 0700')
    return path


def _private_bytes(path, root):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(root):
        raise DailyTableError('source path must be inside private runtime without symlinks')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise DailyTableError('source files must be locally owned private regular files')
        return stream.read()


def _cutoff(target_date, hour, minute):
    day = date.fromisoformat(target_date)
    if day.isoformat() != target_date:
        raise DailyTableError('target date must be canonical ISO')
    return datetime.combine(day, time(hour, minute), TAIPEI)


def live_fetch_in_prediction_window(fetched_at, target_date):
    """Actual Live retrieval must be within the target day's collection window.

    This proves retrieval freshness only, not that the provider updated prices.
    """
    fetched = aware_datetime(fetched_at, name='live fetched_at')
    return _cutoff(target_date, 4, 0) <= fetched <= _cutoff(target_date, 8, 10)


def _sources(root, cutoff):
    """Select the newest eligible acquisition per course source, never a late revision.

    Persisted manifest directories permit fallback after a transient collection
    failure. The collection index is still read when present, including partial
    results. A source's equal-time conflicting payloads are ambiguous and block.
    """
    paths = set()
    latest = root / 'latest_collection.json'
    if latest.exists():
        collection = json.loads(_private_bytes(latest, root))
        if not isinstance(collection, dict) or not isinstance(collection.get('manifests'), list):
            raise DailyTableError('collection manifest index is malformed')
        paths.update(Path(path).absolute() for path in collection['manifests'])
    for source in SOURCE_URLS:
        paths.update((root / 'raw' / source / 'manifests').glob('*.json'))
    if not paths:
        raise DailyTableError('no private source acquisitions are available')
    candidates = {name: [] for name in SOURCE_URLS}
    for path in sorted(paths):
        raw = _private_bytes(path, root)
        record = json.loads(raw)
        if not isinstance(record, dict):
            raise DailyTableError('snapshot manifest must be a JSON object')
        source = record.get('source')
        declared_directory_source = path.parent.parent.name
        if declared_directory_source in SOURCE_URLS and source != declared_directory_source:
            raise DailyTableError('course snapshot source differs from its private source directory')
        if source not in SOURCE_URLS:
            continue
        if record.get('schema_version') != 'snapshot-v1' or record.get('source_url') != SOURCE_URLS[source]:
            raise DailyTableError('course snapshot identity is invalid')
        fetched = aware_datetime(record.get('fetched_at'), name='snapshot fetched_at')
        if fetched > cutoff:
            continue
        candidates[source].append((fetched, str(path), raw, record))
    selected = []
    for source, values in candidates.items():
        if not values:
            raise DailyTableError('both training and live require an eligible private snapshot')
        newest_time = max(item[0] for item in values)
        newest = [item for item in values if item[0] == newest_time]
        if len({item[3].get('sha256') for item in newest}) != 1:
            raise DailyTableError('same-time conflicting source revisions are ambiguous')
        _, path, raw, record = max(newest, key=lambda item: item[1])
        payload = _private_bytes(record['payload_path'], root)
        metadata = record.get('metadata')
        if (hashlib.sha256(payload).hexdigest() != record.get('sha256')
                or len(payload) != record.get('size_bytes')
                or not isinstance(metadata, dict) or metadata.get('tls_verified') is not True):
            raise DailyTableError('course snapshot integrity or verified TLS evidence failed')
        selected.append({'record': record, 'manifest_path': path,
                         'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'payload': payload})
    stocks, provenance = read_course_archives(selected[0]['payload'], [selected[1]['payload']])
    if len(stocks) != 50:
        raise DailyTableError('daily stock universe must contain exactly 50 stocks')
    return stocks, provenance, selected


def _save(root, target_date, kind, value):
    content = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()
    digest = hashlib.sha256(content).hexdigest()
    directory = root / 'tables' / target_date / kind
    for path in (root / 'tables', root / 'tables' / target_date, directory):
        path.mkdir(exist_ok=True, mode=0o700)
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            raise DailyTableError('table store must be locally owned and private')
    destination = directory / (digest + '.json')
    try:
        _exclusive_write(destination, content)
    except FileExistsError:
        if _private_bytes(destination, root) != content:
            raise DailyTableError('immutable table path failed its content hash') from None
    return str(destination), digest


def _blocked(root, target_date, kind, reason):
    report = {'status': 'blocked', 'reason': reason, 'target_date': target_date,
              'historical_vintage_verified': False}
    path, _ = _save(root, target_date, kind + '-report', report)
    return {'status': 'blocked', 'table_path': None, 'report_path': path, 'report': report}


def _transform_hashes():
    package = Path(__file__).resolve().parents[1]
    return {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
            for name in ('data/daily_tables.py', 'data/training_table.py', 'features/stock.py')}


def prediction_rows_from_history(stocks, target_date):
    """Deterministic current input transform, shared by producer and verifier.

    Only earlier stock observations are passed to stock_lags. A freshly fetched
    archive is not evidence that the provider populated the latest session.
    """
    if len(stocks) != 50:
        raise DailyTableError('daily stock universe must contain exactly 50 stocks')
    cutoff = _cutoff(target_date, 8, 10)
    rows, latest_dates = [], {}
    for sid, history in sorted(stocks.items()):
        before = [row for row in history if row['date'] < target_date]
        if not before:
            raise DailyTableError('each target stock needs an earlier observed row')
        latest_dates[sid] = before[-1]['date']
        rows.append({'stock_id': sid, 'target_date': target_date,
                     'feature_cutoff': cutoff.isoformat(), **stock_lags(before[-2:], target_date)})
    return rows, latest_dates


def verify_prediction_values(table, target_date, payloads):
    """Bind supported daily inputs to the exact verified course ZIP bytes.

    Caller authenticates payloads against private, cutoff-eligible manifests.
    This never promotes historical data, model readiness or provider freshness.
    """
    if (table.get('schema_version') != 'prediction-table-v1'
            or table.get('feature_version') != FEATURE_VERSION
            or table.get('feature_columns') != list(STOCK_FEATURES)):
        raise DailyTableError('unsupported prediction input schema, feature version or ordered features')
    if set(payloads) != set(SOURCE_URLS):
        raise DailyTableError('prediction values require exactly Training and Live source bytes')
    if table.get('transform_code_sha256') != _transform_hashes():
        raise DailyTableError('prediction transform hashes differ from the current trusted builder')
    stocks, provenance = read_course_archives(payloads['course-training'], [payloads['course-live']])
    expected, latest_dates = prediction_rows_from_history(stocks, target_date)
    if table.get('provenance') != provenance:
        raise DailyTableError('prediction provenance differs from the bound course bytes')
    actual = table.get('rows')
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise DailyTableError('prediction rows differ from the trusted source reconstruction')
    for row, rebuilt in zip(actual, expected):
        if not isinstance(row, dict) or set(row) != set(rebuilt):
            raise DailyTableError('prediction rows contain unsupported or missing fields')
        for key in ('stock_id', 'target_date', 'feature_cutoff'):
            if row[key] != rebuilt[key]:
                raise DailyTableError('prediction row order, identity or cutoff differs from source reconstruction')
        for key in STOCK_FEATURES:
            value, expected_value = row[key], rebuilt[key]
            if (value is None) != (expected_value is None) or isinstance(value, bool):
                raise DailyTableError('prediction input values differ from source reconstruction')
            if value is not None and (not isinstance(value, (int, float)) or value != expected_value):
                raise DailyTableError('prediction input values differ from source reconstruction')
    return latest_dates


def prepare_training_table(runtime_root, target_date, allow_research=False):
    """Build stock-only history only with research opt-in; never certify history."""
    root = _root(runtime_root)
    cutoff = _cutoff(target_date, 7, 20)
    try:
        stocks, provenance, selected = _sources(root, cutoff)
        if not allow_research:
            return _blocked(root, target_date, 'training',
                            'historical publication and adjustment vintages are unverified; research opt-in required')
        history = {sid: [row for row in rows if row['date'] < target_date] for sid, rows in stocks.items()}
        table = build_research_table(history, provenance=provenance)
        table['rows'] = [row for row in table['rows']
                         if aware_datetime(row['label_available_at'], name='label available_at') <= cutoff]
        if not table['rows']:
            raise DailyTableError('no completed earlier labels available for research training')
        table['audit']['completed_rows'] = len(table['rows'])
        report = {'status': 'prepared', 'readiness': 'research_assumption',
                  'target_date': target_date, 'fit_cutoff': cutoff.isoformat(),
                  'rows': len(table['rows']), 'historical_vintage_verified': False,
                  'snapshot_manifests': [item['manifest_path'] for item in selected],
                  'limitation': 'Historical label release at 23:59 and adjusted vintages remain explicit research assumptions.'}
        table['daily_preparation'] = report
        table['transform_code_sha256'] = _transform_hashes()
        path, digest = _save(root, target_date, 'training', table)
        report_path, _ = _save(root, target_date, 'training-report', report)
        return {'status': 'prepared', 'readiness': 'research_assumption', 'table_path': path,
                'table_sha256': digest, 'report_path': report_path, 'report': report}
    except DailyTableError as error:
        return _blocked(root, target_date, 'training', str(error))
    except (ValueError, OSError, KeyError, TypeError):
        return _blocked(root, target_date, 'training', 'source schema, integrity, eligibility or private storage validation failed')


def prepare_prediction_table(runtime_root, target_date):
    """Prepare observed features; target-day outcomes never enter the transform."""
    root = _root(runtime_root)
    cutoff = _cutoff(target_date, 8, 10)
    try:
        stocks, provenance, selected = _sources(root, cutoff)
        live = next(item['record'] for item in selected if item['record']['source'] == 'course-live')
        if not live_fetch_in_prediction_window(live['fetched_at'], target_date):
            raise DailyTableError('course-live requires a target-day 04:00–08:10 Taipei acquisition')
        rows, latest_dates = prediction_rows_from_history(stocks, target_date)
        evidence = []
        for item in selected:
            record = item['record']
            evidence.append({'source': record['source'], 'payload_sha256': record['sha256'],
                'snapshot_manifest': item['manifest_path'], 'snapshot_manifest_sha256': item['manifest_sha256'],
                'feature_columns': list(STOCK_FEATURES),
                'availability_basis': {'kind': 'observed_fetch', 'reference': item['manifest_path']},
                'available_at': record['fetched_at'], 'fetched_at': record['fetched_at']})
        report = {'status': 'prepared', 'readiness': 'verified', 'target_date': target_date,
                  'feature_cutoff': cutoff.isoformat(), 'rows': len(rows),
                  'verification_scope': 'current_feature_availability_from_observed_bytes_only',
                  'historical_vintage_verified': False, 'latest_observation_dates': latest_dates,
                  'freshness_policy': 'observed-row lags retain age and pending gaps; not a native-session freshness certification',
                  'legacy_feature_version': 'Legacy research name identifies the unchanged transform, not readiness.'}
        table = {'schema_version': 'prediction-table-v1', 'feature_version': FEATURE_VERSION,
                 'feature_columns': list(STOCK_FEATURES), 'readiness': 'verified',
                 'availability_evidence': 'Actual immutable source bytes acquired before this target freeze; '
                                          'no historical publication or vintage claim.',
                 'provenance': provenance, 'feature_evidence': evidence, 'rows': rows,
                 'transform_code_sha256': _transform_hashes(),
                 'daily_preparation': report}
        path, digest = _save(root, target_date, 'prediction', table)
        report_path, _ = _save(root, target_date, 'prediction-report', report)
        return {'status': 'prepared', 'readiness': 'verified', 'table_path': path,
                'table_sha256': digest, 'report_path': report_path, 'report': report}
    except DailyTableError as error:
        return _blocked(root, target_date, 'prediction', str(error))
    except (ValueError, OSError, KeyError, TypeError):
        return _blocked(root, target_date, 'prediction', 'source schema, integrity, eligibility or private storage validation failed')
