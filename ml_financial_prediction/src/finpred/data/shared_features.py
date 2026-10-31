"""Deterministic, label-separated research feature exports for private sharing.

Caller verifies that the destination repository is private. This module neither
publishes Git changes nor upgrades reconstructed historical data to verified.
"""

from bisect import bisect_left
import csv
from datetime import date, datetime, time
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from finpred.data.training_table import ASSUMPTION, read_course_archives
from finpred.features.market import FEATURE_COLUMNS
from finpred.features.stock import STOCK_FEATURES, stock_lags
from finpred.labels.intraday import build_intraday_labels

VERSION = 'shared-research-features-v1'
MAX_PAYLOAD_BYTES = 100 * 1024 * 1024
OUTPUTS = ('features/stock_lags.csv.gz', 'labels/stock_outcomes.csv.gz',
           'features/market.csv', 'features/market_report.json', 'features/schema.json')
STOCK_DEFINITIONS = {
    'stock_prev_intraday_return': ('C[obs-1]/O[obs-1]-1', 'decimal_return', 'previous_observed_stock_row'),
    'stock_return_between_observed_rows': ('C[obs-1]/C[obs-2]-1', 'decimal_return', 'two_previous_observed_stock_rows'),
    'stock_prev_log_volume': ('log(1+volume[obs-1])', 'log_shares', 'previous_observed_stock_row'),
    'stock_prev_rsi': ('RSI[obs-1]', 'provider_RSI_units', 'previous_observed_stock_row'),
    'stock_prev_atr_fraction': ('ATR[obs-1]/C[obs-1]', 'price_fraction', 'previous_observed_stock_row'),
    'stock_prev_sma_deviation': ('C[obs-1]/SMA[obs-1]-1', 'price_fraction', 'previous_observed_stock_row'),
    'stock_previous_observation_gap_days': ('target_date-date[obs-1]', 'calendar_days', 'previous_observed_stock_row'),
}


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _root(value, *, create=False):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('feature storage cannot use symlinks')
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError('feature storage root is missing')
    return path.resolve()


def _output(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(root):
        raise ValueError('feature output escaped storage root')
    return path


def _write(root, relative, payload):
    path = _output(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == payload:
        return
    descriptor, name = tempfile.mkstemp(prefix='.features-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _aware(value):
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.utcoffset() is None:
        raise ValueError('source fetched_at requires a timezone')
    return instant


def _latest(raw_root):
    selected = {}
    for directory in sorted(raw_root.glob('*/manifests')):
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            raise ValueError('snapshot manifest directories cannot use symlinks')
        candidates = []
        for path in directory.glob('*.json'):
            if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('snapshot manifest must be a bounded regular file')
            record = json.loads(path.read_bytes())
            if record.get('schema_version') != 'snapshot-v1' or record.get('source') != directory.parent.name:
                raise ValueError('snapshot manifest identity mismatch')
            candidates.append((_aware(record['fetched_at']), path.name, path, record))
        if not candidates:
            continue
        candidates.sort(key=lambda x: (x[0], x[1]))
        newest = candidates[-1]
        if len({x[3]['sha256'] for x in candidates if x[0] == newest[0]}) != 1:
            raise ValueError('same acquisition time has ambiguous source versions')
        _, _, path, record = newest
        payload_path = Path(record['payload_path'])
        if (any(p.is_symlink() for p in (payload_path, *payload_path.parents))
                or not payload_path.resolve().is_relative_to(raw_root)
                or not payload_path.is_file() or payload_path.stat().st_size > MAX_PAYLOAD_BYTES):
            raise ValueError('snapshot payload must be bounded and inside private raw storage')
        payload = payload_path.read_bytes()
        if len(payload) != record.get('size_bytes') or _sha(payload) != record.get('sha256'):
            raise ValueError('snapshot payload hash or size mismatch')
        selected[record['source']] = {'manifest': record, 'manifest_path': path, 'payload': payload}
    return selected


def _csv(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def _provenance(selected):
    result = []
    for source, item in sorted(selected.items()):
        manifest = item['manifest']
        parts = urlsplit(manifest['source_url'])
        if parts.scheme != 'https' or not parts.netloc or parts.username or parts.password:
            raise ValueError('snapshot source URL contains invalid or credential material')
        result.append({'source': source, 'payload_sha256': manifest['sha256'],
                       'source_fetched_at': manifest['fetched_at'],
                       'source_manifest_sha256': _sha(item['manifest_path'].read_bytes()),
                       'source_url': urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))})
    return result


def _schema(market_fields):
    stock = {name: {'formula': formula, 'unit': unit, 'lag_basis': lag,
                    'native_session_lag_certified': False,
                    'missing_policy': 'null_if_predecessor_missing_or_pending; never_skip_pending_row'}
             for name, (formula, unit, lag) in STOCK_DEFINITIONS.items()}
    market = {}
    for name in market_fields:
        if name.endswith('_ret_1s'):
            details = {'formula': 'P[s]/P[previous_native_session(s)]-1', 'unit': 'decimal_return',
                       'lag_basis': 'latest_source_native_session_available_at_target_cutoff'}
        elif name == 'vix_level':
            details = {'formula': 'VIX[s]', 'unit': 'index_points', 'lag_basis': 'latest_available_native_session'}
        elif name == 'vix_change_points':
            details = {'formula': 'VIX[s]-VIX[previous_native_session(s)]', 'unit': 'index_points',
                       'lag_basis': 'latest_available_native_session'}
        elif name.startswith('tx_foreign_net_oi') and not any(t in name for t in ('source_', 'age_', 'is_')):
            details = {'formula': 'signed_net_OI[s]' if not name.endswith('_change') else 'net_OI[s]-net_OI[prev]',
                       'unit': 'contracts', 'lag_basis': 'latest_available_source_session',
                       'status': 'missing_pending_date_and_sentinel_evidence; never_percentage_return'}
        elif name.endswith('_age_hours'):
            details = {'formula': '(feature_cutoff-selected_source_available_at)/3600', 'unit': 'hours'}
        elif name.endswith('_is_missing'):
            details = {'formula': 'required_input_or_native_predecessor_missing', 'unit': 'boolean'}
        elif name.endswith('_is_new_session_since_previous_tw_target'):
            details = {'formula': 'selected_source_session_newer_than_previous_target_selection', 'unit': 'boolean_or_null_first_target'}
        else:
            details = {'formula': 'trace_of_selected_asof_source_or_target_key', 'unit': 'date_or_timestamp_or_version'}
        market[name] = details
    return {'schema_version': VERSION, 'readiness': 'research_assumption',
            'production_eligible': False, 'historical_vintage_verified': False,
            'cutoff_policy': '08:10 Asia/Taipei project proposal; official deadline 09:00',
            'stock': stock, 'market': market,
            'labels_location': 'labels/stock_outcomes.csv.gz; never model inputs',
            'return_notation': 'Two prices make one return. lag2 is an older return, not a two-price formula.',
            'not_exported_as_ready_features': {'FRED_FX_and_yield': 'raw_only_here; separate bounded research expansion',
                                               'industry_history': 'single raw snapshot cannot produce historical returns'}}


def _blocked(root, reason, sources):
    # A new Git commit is an atomic publication boundary. Remove managed stale
    # tables if this new commit reports blocked, rather than labelling them fresh.
    for name in OUTPUTS:
        _output(root, name).unlink(missing_ok=True)
    result = {'schema_version': VERSION, 'status': 'blocked', 'reason': reason,
              'production_eligible': False, 'historical_vintage_verified': False,
              'sources': sources, 'files': {}}
    _write(root, 'features/lineage.json', _json(result))
    return result


def _build_shared_features(runtime_root, bundle_root, *, allow_research=True):
    """Export current immutable sources; historical availability remains assumed.

    No future target session is invented. Dates are the union of actual course
    observations and each date retains all 50 target stocks, including missing
    or pending labels. Consumers must use lineage and selected source versions.
    """
    runtime, bundle = _root(runtime_root), _root(bundle_root, create=True)
    raw = _root(runtime / 'raw')
    selected = _latest(raw)
    provenance = _provenance(selected)
    if not allow_research:
        return _blocked(bundle, 'historical_availability_not_verified; research opt-in required', provenance)
    if 'course-training' not in selected:
        return _blocked(bundle, 'course_training_snapshot_missing', provenance)
    stocks, _ = read_course_archives(selected['course-training']['payload'],
                                    [selected['course-live']['payload']] if 'course-live' in selected else [])
    if len(stocks) != 50:
        raise ValueError('shared feature table requires the complete 50-stock target universe')
    dates = sorted({row['date'] for values in stocks.values() for row in values})
    targets = [{'target_date': day, 'feature_cutoff': datetime.combine(date.fromisoformat(day), time(8, 10),
                                         ZoneInfo('Asia/Taipei')).isoformat()} for day in dates]
    cutoffs = {r['target_date']: r['feature_cutoff'] for r in targets}
    feature_rows, label_rows, pending_count = [], [], 0
    for sid, values in sorted(stocks.items()):
        raw_days = [row['date'] for row in values]
        labels = build_intraday_labels(values, stock_id=sid, prices_verified_adjusted=True)
        completed = {row['target_date']: row for row in labels.complete}
        pending = {row['target_date'] for row in labels.pending}
        for day in dates:
            stop = bisect_left(raw_days, day)
            prefix = values[max(0, stop - 2):stop]
            feature_rows.append({'stock_id': sid, 'target_date': day, 'feature_cutoff': cutoffs[day],
                                 'stock_source_observation_date': prefix[-1]['date'] if prefix else None,
                                 **stock_lags(prefix, day)})
            label = completed.get(day)
            status = 'complete' if label else ('pending' if day in pending else 'missing_observation')
            label_rows.append({'stock_id': sid, 'target_date': day, 'status': status,
                               'y': label['y'] if label else None,
                               'target_intraday_return': label['target_intraday_return'] if label else None})
            pending_count += status == 'pending'
    feature_rows.sort(key=lambda r: (r['target_date'], r['stock_id']))
    label_rows.sort(key=lambda r: (r['target_date'], r['stock_id']))
    history = [item['manifest_path'] for source, item in sorted(selected.items()) if source.startswith('yahoo-')]
    market_rows, market_report = [], {'readiness': 'blocked', 'reason': 'no_yahoo_history_snapshots'}
    if history:
        from finpred.data.normalization import build_history_market_features
        market = build_history_market_features(history, targets, mode='research')
        market_rows = market['rows']
        full = market['report']
        for series, details in full.get('additional_series', {}).items():
            previous_session = None
            audits = {row['target_date']: row for row in details['targets']}
            for index, row in enumerate(market_rows):
                audit = audits[row['target_date']]
                inputs = [r for r in (audit['current'], audit['previous']) if r is not None]
                available = max((_aware(r['available_at']) for r in inputs), default=None)
                current_session = row[series + '_source_session_date']
                row[series + '_source_available_at'] = available.isoformat() if available else None
                row[series + '_age_hours'] = ((_aware(row['feature_cutoff']) - available).total_seconds() / 3600
                                                if available else None)
                row[series + '_is_new_session_since_previous_tw_target'] = (
                    None if index == 0 else current_session is not None and
                    (previous_session is None or current_session > previous_session))
                previous_session = current_session
        market_report = {key: full[key] for key in ('readiness', 'mode', 'historical_vintage_verified',
                         'assumed_provider_delay_seconds', 'limitations', 'missing_counts',
                         'series_status', 'source_rows') if key in full}
        market_report['detailed_alignment_audit_omitted'] = True
        market_report['provenance'] = [p for p in provenance if p['source'].startswith('yahoo-')]
    market_fields = list(market_rows[0]) if market_rows else ['target_date', 'feature_cutoff', *FEATURE_COLUMNS]
    if not market_rows:
        market_rows = [{**target, **dict.fromkeys(FEATURE_COLUMNS)} for target in targets]
    stock_fields = ['stock_id', 'target_date', 'feature_cutoff', 'stock_source_observation_date', *STOCK_FEATURES]
    output = {'features/stock_lags.csv.gz': gzip.compress(_csv(feature_rows, stock_fields), mtime=0),
              'labels/stock_outcomes.csv.gz': gzip.compress(_csv(label_rows, ['stock_id', 'target_date', 'status', 'y',
                                                                          'target_intraday_return']), mtime=0),
              'features/market.csv': _csv(market_rows, market_fields),
              'features/market_report.json': _json(market_report),
              'features/schema.json': _json(_schema(market_fields))}
    catalog = None
    pointer = bundle / 'catalog/latest.json'
    if pointer.exists():
        catalog = json.loads(pointer.read_bytes()).get('catalog_sha256')
        if not isinstance(catalog, str) or not re.fullmatch('[a-f0-9]{64}', catalog):
            raise ValueError('invalid raw catalog pointer identity')
    lineage = {'schema_version': VERSION, 'status': 'exported', 'readiness': 'research_assumption',
               'production_eligible': False, 'historical_vintage_verified': False,
               'availability_evidence': ASSUMPTION, 'sources': provenance,
               'raw_catalog_sha256': catalog,
               'target_date_count': len(dates), 'stock_count': len(stocks),
               'stock_feature_rows': len(feature_rows), 'pending_label_rows': pending_count,
               'missing_label_rows': sum(r['status'] == 'missing_observation' for r in label_rows),
               'market_readiness': market_report['readiness'],
               'source_fetched_at_policy': 'actual source acquisition times preserved; never inferred historical releases',
               'calendar_basis': 'union_of_course_observation_dates_not_certified_TWSE_session_calendar',
               'files': {name: {'sha256': _sha(payload), 'size_bytes': len(payload)} for name, payload in output.items()},
               'code_sha256': {name: _sha((Path(__file__).parents[1] / name).read_bytes())
                               for name in ('data/shared_features.py', 'features/stock.py', 'data/normalization.py', 'features/market.py')}}
    for name, payload in output.items():
        _write(bundle, name, payload)
    _write(bundle, 'features/lineage.json', _json(lineage))
    return {key: value for key, value in lineage.items() if key not in ('sources', 'availability_evidence')}


def _catalog_identity(bundle):
    path = _output(bundle, 'catalog/latest.json')
    return json.loads(path.read_bytes()).get('catalog_sha256') if path.exists() else None


def build_shared_features(runtime_root, bundle_root, *, allow_research=True):
    """Build exports and persist a separate success/failure marker for consumers.

    A failed new build may leave the previous valid files available for a pinned
    old run, but never marks them as refreshed for the new raw catalog.
    """
    bundle = _root(bundle_root, create=True)
    try:
        result = _build_shared_features(runtime_root, bundle, allow_research=allow_research)
    except (OSError, ValueError, TypeError, KeyError, ImportError):
        _write(bundle, 'features/build_status.json', _json({
            'schema_version': VERSION, 'status': 'failed',
            'reason': 'source_integrity_schema_or_feature_build_failed',
            'raw_catalog_sha256': _catalog_identity(bundle),
            'production_eligible': False,
        }))
        raise
    lineage_bytes = _output(bundle, 'features/lineage.json').read_bytes()
    _write(bundle, 'features/build_status.json', _json({
        'schema_version': VERSION, 'status': result['status'],
        'raw_catalog_sha256': _catalog_identity(bundle), 'lineage_sha256': _sha(lineage_bytes),
        'production_eligible': False,
    }))
    return result


def validate_shared_feature_exports(bundle_root):
    """Reject failed, blocked, stale-catalog or corrupted shared feature files."""
    bundle = _root(bundle_root)
    status = json.loads(_output(bundle, 'features/build_status.json').read_bytes())
    lineage_bytes = _output(bundle, 'features/lineage.json').read_bytes()
    if status.get('status') != 'exported' or status.get('lineage_sha256') != _sha(lineage_bytes):
        raise ValueError('shared feature build is failed, blocked or inconsistent')
    lineage = json.loads(lineage_bytes)
    if (lineage.get('schema_version') != VERSION or lineage.get('status') != 'exported'
            or set(lineage.get('files', {})) != set(OUTPUTS)
            or status.get('raw_catalog_sha256') != _catalog_identity(bundle)
            or lineage.get('raw_catalog_sha256') != _catalog_identity(bundle)):
        raise ValueError('shared features have incomplete metadata or belong to a different raw catalog')
    for name, expected in lineage['files'].items():
        if name not in OUTPUTS:
            raise ValueError('unexpected feature export path')
        payload = _output(bundle, name).read_bytes()
        if len(payload) != expected['size_bytes'] or _sha(payload) != expected['sha256']:
            raise ValueError('shared feature output hash or size mismatch')
    return lineage
