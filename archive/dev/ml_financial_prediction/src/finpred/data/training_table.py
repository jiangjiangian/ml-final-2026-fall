"""Explicitly exploratory stock lags; current outcomes never enter features.

Course archives contain latest adjusted history without publication/vintage
metadata. This adapter never certifies that snapshot as historically available.
"""

import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from finpred.data.course_schema import audit_course_zip
from finpred.features.market import FEATURE_COLUMNS
from finpred.features.stock import STOCK_FEATURES, number as _number, stock_lags
from finpred.labels.intraday import build_intraday_labels

TAIPEI = ZoneInfo('Asia/Taipei')
ASSUMPTION = (
    'Exploratory latest-vintage course archive. Previous observed stock row is '
    'assumed usable at 23:59 Taipei on its source date; labels are assumed '
    'complete at 23:59 on outcome date. Publication/revision and adjustment '
    'vintages are NOT verified. Stock return is between observed rows, not a '
    'certified one-native-session return. Not production eligible.'
)


def read_course_archives(training_payload, live_payloads=()):
    """Audit archives and merge revisions in explicit supplied snapshot order."""
    audit = audit_course_zip(training_payload, 'training')
    ids = audit['info']['Top50@Y']
    rows = {sid: {} for sid in ids}
    manifests = []
    for index, payload in enumerate([training_payload, *live_payloads]):
        kind = 'training' if index == 0 else 'live'
        if index:
            audit_course_zip(payload, kind, expected_stock_ids=audit['stock_ids'])
        manifests.append({'kind': kind, 'sha256': hashlib.sha256(payload).hexdigest(),
                          'precedence': index})
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for sid in ids:
                text = archive.read(f'data/market/{sid}.csv').decode('utf-8-sig')
                for row in csv.DictReader(io.StringIO(text)):
                    rows[sid][row['date']] = row
    return {sid: [by_date[d] for d in sorted(by_date)] for sid, by_date in rows.items()}, manifests


def build_research_table(stock_rows, *, provenance, market_rows=None, market_report=None, market_features=None):
    """Build only research-assumption tables, preserving all complete outcomes.

    market_rows, when supplied, must be M0 output for the exact target cutoff.
    The feature list is fixed; missing market dates remain missing, never inner
    joined away. The source report is required to retain its evidence/limits.
    """
    market = {}
    chosen_market = list(FEATURE_COLUMNS if market_features is None else market_features)
    allowed = set(FEATURE_COLUMNS) | {'sox_ret_1s', 'tsm_adr_ret_1s', 'nvda_ret_1s'}
    if not chosen_market or len(chosen_market) != len(set(chosen_market)) or set(chosen_market) - allowed:
        raise ValueError('unsupported or duplicate market feature list')
    if market_rows is not None:
        if not isinstance(market_report, dict) or not market_report:
            raise ValueError('market alignment report is required')
        for row in market_rows:
            day = row['target_date']
            if day in market:
                raise ValueError('duplicate market target date')
            market[day] = row
    result, pending, missing_market = [], [], 0
    for sid, values in sorted(stock_rows.items()):
        if not isinstance(sid, str) or not sid:
            raise ValueError('stock IDs must remain nonempty strings')
        raw = sorted(values, key=lambda r: r['date'])
        days = [row['date'] for row in raw]
        if len(days) != len(set(days)):
            raise ValueError('duplicate raw stock/date')
        labels = build_intraday_labels(raw, stock_id=sid, prices_verified_adjusted=True)
        by_day = {r['target_date']: r for r in labels.complete}
        pending.extend(labels.pending)
        for i, row in enumerate(raw):
            if row['date'] not in by_day:
                continue
            day = date.fromisoformat(row['date'])
            cutoff = datetime.combine(day, time(8, 10), TAIPEI).isoformat()
            output = dict(by_day[row['date']], feature_cutoff=cutoff,
                          label_available_at=datetime.combine(day, time(23, 59), TAIPEI).isoformat())
            output.update(stock_lags(raw[max(0, i - 2):i], row['date']))
            if market_rows is not None:
                match = market.get(row['date'])
                if match:
                    received = datetime.fromisoformat(match['feature_cutoff'].replace('Z', '+00:00'))
                    if received.utcoffset() is None or received != datetime.fromisoformat(cutoff):
                        raise ValueError('market cutoff must exactly match the stock-table cutoff')
                else:
                    missing_market += 1
                for name in chosen_market:
                    output[name] = _number(match.get(name)) if match else None
            result.append(output)
    if not result:
        raise ValueError('no completed labels available')
    result.sort(key=lambda r: (r['target_date'], r['stock_id']))
    features = list(STOCK_FEATURES) + (chosen_market if market_rows is not None else [])
    for row in result:
        if any(v is not None and not math.isfinite(v) for k, v in row.items() if k in features):
            raise ValueError('nonfinite transformed feature')
    version_suffix = '-market-' + hashlib.sha256(','.join(chosen_market).encode()).hexdigest()[:8] if market_rows is not None else ''
    return {'schema_version': 'training-table-v1', 'feature_version': 'course-research-lags-v1' + version_suffix,
            'feature_columns': features, 'readiness': 'research_assumption',
            'availability_evidence': ASSUMPTION, 'provenance': provenance,
            'market_alignment_report': market_report if market_rows is not None else None,
            'rows': result, 'audit': {'completed_rows': len(result), 'pending_rows': len(pending),
                                    'pending_dates': sorted({r['target_date'] for r in pending}),
                                    'missing_market_rows': missing_market,
                                    'production_eligible': False}}


def canonical_table_hash(table):
    return hashlib.sha256(json.dumps(table, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
