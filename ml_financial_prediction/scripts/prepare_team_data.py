"""Prepare label-separated research JSON from hash-verified shared course ZIPs.

This is the offline bridge from fetch_live_data.py to train_model.py. Historical
features remain exploratory latest-vintage data, not live prediction inputs.
"""

import argparse
from bisect import bisect_left
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.shared_features import _latest, _provenance  # noqa: E402
from finpred.data.training_table import build_research_table, read_course_archives  # noqa: E402
from finpred.features.stock import STOCK_FEATURES, stock_lags  # noqa: E402

TAIPEI = ZoneInfo('Asia/Taipei')
SOURCES = {
    'course-training': 'https://final.html2026.csie.org/downloads/fin_pred_data.zip',
    'course-live': 'https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip',
}


def _path(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('research paths must not use symlinks')
    return path


def _reserve(value):
    path = _path(value)
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise ValueError('research output must remain outside Git')
    missing, parent = [], path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    path.mkdir(mode=0o700)
    return path


def _payload(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _write(path, payload):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _sync(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_team_data(runtime_dir, out_dir, *, train_before=None, allow_research=False, clock=None):
    """Keep only target dates strictly before train_before, before making labels.

    The outcome-free historical feature table preserves all stocks on the union
    of actual observation dates, including pending/missing outcomes. No unseen
    official session is invented. This command never fits, evaluates or submits.
    """
    if allow_research is not True:
        raise ValueError('historical research preparation requires explicit opt-in')
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.utcoffset() is None:
        raise ValueError('actual preparation time must have a timezone')
    today = now.astimezone(TAIPEI).date()
    limit = today if train_before is None else date.fromisoformat(train_before)
    if (train_before is not None and limit.isoformat() != train_before) or limit > today:
        raise ValueError('exclusive training cutoff must be canonical and no later than today')
    runtime = _path(runtime_dir)
    if not runtime.is_dir() or any((p / '.git').exists() for p in (runtime, *runtime.parents)):
        raise ValueError('runtime must be an existing directory outside Git')
    selected = _latest(runtime / 'raw')
    if not set(SOURCES).issubset(selected):
        raise ValueError('shared Training and Live snapshots are both required')
    sources = {source: selected[source] for source in SOURCES}
    for source, item in sources.items():
        record = item['manifest']
        acquired = datetime.fromisoformat(record['fetched_at'].replace('Z', '+00:00'))
        if (record.get('source_url') != SOURCES[source]
                or record.get('metadata', {}).get('tls_verified') is not True
                or acquired > now):
            raise ValueError('course snapshot source, verified TLS or acquisition time is invalid')
    stocks, archive_provenance = read_course_archives(
        sources['course-training']['payload'], [sources['course-live']['payload']])
    if len(stocks) != 50:
        raise ValueError('team data requires the full 50-stock course universe')
    # Filtering before build_research_table prevents even reading excluded
    # target outcomes during label construction. Earlier completed OHLC remains
    # a lag feature; pending predecessors are retained rather than skipped.
    prefix = {sid: [row for row in values if row['date'] < limit.isoformat()]
              for sid, values in stocks.items()}
    provenance = _provenance(sources)
    table = build_research_table(prefix, provenance=archive_provenance)
    table['source_snapshots'] = provenance
    table['training_target_exclusive_upper_bound'] = limit.isoformat()
    days = sorted({row['date'] for rows in prefix.values() for row in rows})
    rows = []
    for sid, values in sorted(prefix.items()):
        raw_days = [row['date'] for row in values]
        for day in days:
            stop = bisect_left(raw_days, day)
            # stock_lags uses y solely as a completion mask. Discard its binary
            # direction here so the feature construction cannot read outcomes.
            previous = [{**row, 'y': 1 if row['y'] in ('0', '1', 0, 1) else -1}
                        for row in values[max(0, stop - 2):stop]]
            rows.append({'stock_id': sid, 'target_date': day,
                         'feature_cutoff': datetime.combine(date.fromisoformat(day), time(8, 10), TAIPEI).isoformat(),
                         **stock_lags(previous, day)})
    rows.sort(key=lambda row: (row['target_date'], row['stock_id']))
    features = {'schema_version': 'sequence-feature-table-v1',
                'feature_version': table['feature_version'], 'feature_columns': list(STOCK_FEATURES),
                'readiness': 'research_assumption', 'production_eligible': False,
                'historical_vintage_verified': False,
                'availability_evidence': table['availability_evidence'], 'rows': rows,
                'scope': 'historical_exploration; not input for a model fitted after these cutoffs'}
    files = {'training-table.json': _payload(table), 'features.json': _payload(features)}
    lineage = {'schema_version': 'team-research-data-v1', 'status': 'research_data_prepared',
               'prepared_at': now.isoformat(), 'readiness': 'research_assumption',
               'production_eligible': False, 'historical_vintage_verified': False,
               'training_target_exclusive_upper_bound': limit.isoformat(),
               'training_rows': len(table['rows']), 'feature_rows': len(rows), 'stock_count': len(stocks),
               'train_end_date': max(row['target_date'] for row in table['rows']),
               'pending_training_rows': table['audit']['pending_rows'],
               'target_calendar_basis': 'union_of_course_observation_dates; not certified official sessions',
               'sources': provenance, 'archive_precedence': archive_provenance,
               'source_time_policy': 'actual source acquisition preserved; not historical publication evidence',
               'model_fit_count': 0, 'submitted': False,
               'files': {name: {'sha256': hashlib.sha256(payload).hexdigest(), 'size_bytes': len(payload)}
                         for name, payload in files.items()},
               'entrypoint_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    destination = _reserve(out_dir)
    staging = Path(tempfile.mkdtemp(prefix='.finpred-team-data-', dir=destination.parent))
    try:
        for name, payload in files.items():
            _write(staging / name, payload)
        _write(staging / 'lineage.json', _payload(lineage))
        _sync(staging)
        os.rename(staging, destination)
        staging = None
        _sync(destination.parent)
    finally:
        if staging is not None:
            shutil.rmtree(staging)
    return {key: lineage[key] for key in ('status', 'training_rows', 'feature_rows', 'stock_count',
                                         'train_end_date', 'training_target_exclusive_upper_bound',
                                         'production_eligible', 'submitted')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True, help='New research-data directory outside Git')
    parser.add_argument('--train-before', help='Exclusive ISO target date; default is today in Asia/Taipei')
    parser.add_argument('--allow-research', action='store_true')
    args = parser.parse_args()
    try:
        result = prepare_team_data(args.runtime_dir, args.out_dir, train_before=args.train_before,
                                   allow_research=args.allow_research)
    except Exception as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__,
                          'detail': 'research data preparation failed; input details omitted'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
