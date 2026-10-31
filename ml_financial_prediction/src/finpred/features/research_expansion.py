"""Frozen, bounded external-feature ablations; never certify latest vintages.

Price transforms use explicit native sessions before as-of alignment. FRED
observation rows are deliberately *not* named native sessions. Its seven-day
quarantine is a declared research assumption, not a verified release policy.
"""

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

from finpred.data.availability import aware_instant
from finpred.data.normalization import normalize_history_snapshots
from finpred.features.stock import STOCK_FEATURES
from finpred.ingestion.external import parse_external_payload

PRICE_SERIES = ('ixic', 'gspc', 'twii', 'ks11', 'sox', 'tsm_adr', 'nvda')
MARKET_SERIES = PRICE_SERIES + ('vix',)
SECTOR_SERIES = ('tw_electronics', 'tw_semiconductor', 'tw_financials')
FRED_QUARANTINE_DAYS = 7
VERSION = 'research-expansion-native-v1'
TAIPEI = ZoneInfo('Asia/Taipei')


def frozen_schema():
    """Exact feature lists/formulas, fixed before evaluating any model score."""
    groups = {'F0': list(STOCK_FEATURES), 'F1': [], 'F2': [], 'F3': []}
    descriptions = {}

    def add(group, name, formula, unit, lag):
        groups[group].append(name)
        descriptions[name] = {'group': group, 'formula': formula, 'unit': unit,
                              'lag_meaning': lag, 'historical_vintage_verified': False}

    for series in PRICE_SERIES:
        for window in (1, 5, 20):
            add('F1', f'{series}_ret_{window}s', f'P[s]/P[s-{window}]-1', 'decimal',
                f'{window} native source sessions ending at the latest cutoff-available session; '
                'all intervening sessions must exist and be available; not a Taiwan row shift')
    add('F2', 'vix_level', 'VIX[s]', 'index_point', 'latest cutoff-available VIX session')
    add('F2', 'vix_change_points', 'VIX[s]-VIX[s-1]', 'index_point',
        'one native-session point difference; not a tradable asset return')
    for series in PRICE_SERIES:
        add('F2', f'{series}_vol_20s', 'population_std(P[u]/P[u-1]-1, last 20 native sessions)',
            'decimal_not_annualized', '21 complete cutoff-available native price levels')
    for series in MARKET_SERIES:
        add('F2', f'{series}_age_hours', '(cutoff-source_available_at)/3600', 'hours',
            'age of latest eligible source version, not time since last Taiwan row')
        add('F2', f'{series}_is_missing', '1 if latest source value or one-session transform missing else 0',
            'binary', 'a missing native predecessor remains missing; no backward search')
        add('F2', f'{series}_is_new_session', '1 if selected source session advanced since previous target else 0',
            'binary', 'first target unknown; a revision is not a new source session')
    for window in (1, 5):
        add('F3', f'usd_twd_ret_{window}obs', f'FX[o]/FX[o-{window}]-1', 'decimal_TWD_per_USD',
            f'{window} FRED observation-row steps; not certified consecutive fixing sessions')
    add('F3', 'us_10y_yield_percent', 'DGS10[o]', 'percent_per_annum', 'latest eligible observation row')
    for window in (1, 5):
        add('F3', f'us_10y_yield_change_bp_{window}obs', f'100*(DGS10[o]-DGS10[o-{window}])', 'basis_point',
            f'{window} observation-row steps; negative yields and differences remain signed')
    for series in ('usd_twd', 'us_10y_yield'):
        add('F3', f'{series}_age_hours', '(cutoff-assumed_available_at)/3600', 'hours',
            'explicit research quarantine, not measured publication time')
        add('F3', f'{series}_is_missing', '1 if latest observation or required predecessor missing else 0',
            'binary', 'FRED holiday/missing rows retained; no backward fill')
    for series in SECTOR_SERIES:
        add('F3', f'{series}_ret_1s', 'sector_index[s]/sector_index[s-1]-1', 'decimal',
            'blocked until at least complete historical native calendar/value evidence exists')
    value = {'schema_version': VERSION, 'group_extra_columns': groups,
             'model_columns': {g: list(STOCK_FEATURES) + (cols if g != 'F0' else [])
                               for g, cols in groups.items()},
             'feature_definitions': descriptions,
             'F0_definition': 'Unchanged seven stock features from finpred.features.stock.stock_lags',
             'fred_assumption': f'observation date + {FRED_QUARANTINE_DAYS} calendar days at 23:59 Asia/Taipei; '
                                'a research quarantine, not a documented publication calendar',
             'search_budget': {'R1_configurations': 8, 'models': 2, 'groups': 4,
                               'quarter_folds': 4, 'maximum_fits': 32}}
    value['schema_sha256'] = _hash(value)
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _numeric(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('source values must be finite JSON numbers or null')
    return float(value)


def _records_by_series(observations, calendars):
    """Validate source revisions before any prefix is exposed to target rows."""
    output = defaultdict(list)
    revision_keys = set()
    availability_keys = set()
    native_sets = {}
    for series, calendar in calendars.items():
        native = calendar['session_dates']
        if native != sorted(set(native)):
            raise ValueError('native calendars must be sorted and unique')
        native_sets[series] = set(native)
    for row in observations:
        series, day = row['series_id'], row['session_date']
        if series not in MARKET_SERIES or series not in calendars:
            raise ValueError('unsupported series or missing native calendar')
        if day not in native_sets[series]:
            raise ValueError('source session is not in the explicit native calendar')
        available = aware_instant(row['available_at'])
        event = aware_instant(row['event_time'])
        if available < event:
            raise ValueError('availability cannot precede source event')
        key = (series, day, row['revision_id'])
        time_key = (series, day, available)
        if key in revision_keys or time_key in availability_keys:
            raise ValueError('duplicate or ambiguous source revision')
        revision_keys.add(key)
        availability_keys.add(time_key)
        value = _numeric(row['value'])
        if value is not None and value < 0:
            raise ValueError('negative price/volatility index level is invalid')
        output[series].append((available, day, dict(row, value=value)))
    for values in output.values():
        values.sort(key=lambda item: (item[0], item[1]))
    return output


def native_feature_rows(observations, calendars, targets):
    """Compute frozen price/VIX features on complete native windows, then align.

    Any session missing a level or eligible version invalidates the full window.
    Same-endpoint revisions update denominators only once their available_at
    passes the target cutoff. A late revision of an older session cannot replace
    the latest selected session.
    """
    prepared = _records_by_series(observations, calendars)
    ordered_targets = _targets(targets)
    result = {day: {'target_date': day, 'feature_cutoff': cutoff} for day, cutoff in ordered_targets}
    for series in MARKET_SERIES:
        events = prepared[series]
        native = calendars.get(series, {}).get('session_dates', [])
        positions = {day: i for i, day in enumerate(native)}
        active, cursor, previous_session = {}, 0, None
        for target_index, (day, cutoff_text) in enumerate(ordered_targets):
            cutoff = aware_instant(cutoff_text)
            while cursor < len(events) and events[cursor][0] <= cutoff:
                _, source_day, record = events[cursor]
                active[source_day] = record
                cursor += 1
            selected_day = max(active) if active else None
            current = active.get(selected_day)
            position = positions.get(selected_day, -1)

            def values(window):
                if position < window:
                    return None
                records = [active.get(source_day) for source_day in native[position - window:position + 1]]
                if any(record is None or record['value'] is None for record in records):
                    return None
                return [record['value'] for record in records]

            def price_return(window):
                prices = values(window)
                return prices[-1] / prices[0] - 1 if prices and all(p > 0 for p in prices) else None

            row = result[day]
            one = values(1)
            one_value = (one[-1] - one[0]) if series == 'vix' and one else price_return(1)
            if series in PRICE_SERIES:
                for window in (1, 5, 20):
                    row[f'{series}_ret_{window}s'] = price_return(window)
                levels = values(20)
                row[f'{series}_vol_20s'] = (statistics.pstdev([b / a - 1 for a, b in zip(levels, levels[1:])])
                                           if levels and all(p > 0 for p in levels) else None)
            else:
                row['vix_level'] = current['value'] if current else None
                row['vix_change_points'] = one_value
            row[f'{series}_source_session_date'] = selected_day
            row[f'{series}_source_available_at'] = current['available_at'] if current else None
            row[f'{series}_age_hours'] = ((cutoff - aware_instant(current['available_at'])).total_seconds() / 3600
                                          if current else None)
            row[f'{series}_is_missing'] = float(one_value is None)
            row[f'{series}_is_new_session'] = (None if target_index == 0 else
                                               float(selected_day is not None and
                                                     (previous_session is None or selected_day > previous_session)))
            previous_session = selected_day
    return list(result.values())


def _targets(targets):
    by_day = {}
    for row in targets:
        day, cutoff = row['target_date'], row['feature_cutoff']
        instant = aware_instant(cutoff)
        local = instant.astimezone(TAIPEI)
        if local.date().isoformat() != day or local.timetz().replace(tzinfo=None) > time(9):
            raise ValueError('cutoff must be on target Taipei date and no later than 09:00')
        if day in by_day and aware_instant(by_day[day]) != instant:
            raise ValueError('ambiguous cutoff for the same target date')
        by_day[day] = cutoff
    if not by_day:
        raise ValueError('targets must be nonempty')
    return sorted(by_day.items())


def _load_manifest(path):
    path = Path(path)
    manifest = json.loads(path.read_text())
    payload = Path(manifest['payload_path']).read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest['sha256']:
        raise ValueError('snapshot payload differs from immutable manifest')
    aware_instant(manifest['fetched_at'])
    return manifest, payload


def fred_feature_rows(manifests, targets):
    """Observation-row FX returns/yield differences with honest assumption tags."""
    records = {}
    source_times = {}
    source_audit = {}
    ordered_targets = _targets(targets)
    for path in manifests:
        manifest, payload = _load_manifest(path)
        source = manifest['source']
        if source not in ('fred_usd_twd', 'fred_us10y'):
            continue
        if source in records:
            raise ValueError('choose one immutable FRED snapshot per source')
        parsed = parse_external_payload(source, payload)
        eligible = []
        fetched = aware_instant(manifest['fetched_at'])
        for row in parsed:
            day = datetime.fromisoformat(row['provider_observation_date']).date()
            event = datetime.combine(day, time(23, 59), TAIPEI)
            if event.astimezone(fetched.tzinfo) > fetched:
                continue
            available = event + timedelta(days=FRED_QUARANTINE_DAYS)
            eligible.append(dict(row, available_at=available.isoformat()))
        records[source] = eligible
        source_times[source] = [aware_instant(record['available_at']) for record in eligible]
        source_audit[source] = {'source_sha256': manifest['sha256'], 'source_fetched_at': manifest['fetched_at'],
                               'rows': len(parsed), 'eligible_historical_rows': len(eligible),
                               'historical_vintage_verified': False, 'published_at': None,
                               'availability_basis': 'conservative_assumption',
                               'assumption': frozen_schema()['fred_assumption'],
                               'calendar_evidence': 'FRED observation-row dates including explicit missing rows; '
                                                    'not a certified fixing/trading-session calendar'}
    result = []
    for day, cutoff_text in ordered_targets:
        cutoff = aware_instant(cutoff_text)
        row = {'target_date': day, 'feature_cutoff': cutoff_text}
        for source, series in (('fred_usd_twd', 'usd_twd'), ('fred_us10y', 'us_10y_yield')):
            data = records.get(source, [])
            available = source_times.get(source, [])
            position = bisect_right(available, cutoff) - 1
            current = data[position] if position >= 0 else None

            def window_values(window):
                if position < window:
                    return None
                subset = data[position - window:position + 1]
                if any(record['value'] is None for record in subset):
                    return None
                return [record['value'] for record in subset]

            for window in (1, 5):
                values = window_values(window)
                if series == 'usd_twd':
                    row[f'{series}_ret_{window}obs'] = (values[-1] / values[0] - 1
                                                       if values and all(value > 0 for value in values) else None)
                else:
                    row[f'{series}_change_bp_{window}obs'] = 100 * (values[-1] - values[0]) if values else None
            if series == 'us_10y_yield':
                row['us_10y_yield_percent'] = current['value'] if current else None
            one = window_values(1)
            row[f'{series}_age_hours'] = ((cutoff - aware_instant(current['available_at'])).total_seconds() / 3600
                                         if current else None)
            row[f'{series}_is_missing'] = float(one is None)
            row[f'{series}_source_observation_date'] = current['provider_observation_date'] if current else None
            row[f'{series}_source_available_at'] = current['available_at'] if current else None
        result.append(row)
    return result, source_audit


def build_research_expansion(stock_table, history_manifests, external_manifests=(), *,
                             mode='strict', allow_research=False):
    """Preserve every baseline stock/date/label while attaching frozen groups.

    F3 includes industry native returns and stays blocked until their historical
    source/calendar evidence is available. E04 FX/rate values are still exported
    as a diagnostic subset; they do not silently replace the frozen F3 group.
    """
    if mode not in {'strict', 'research'}:
        raise ValueError('mode must be strict or research')
    schema = frozen_schema()
    report = {'schema_version': VERSION, 'schema_sha256': schema['schema_sha256'],
              'readiness': 'blocked', 'production_eligible': False,
              'historical_vintage_verified': False, 'mode': mode,
              'new_fits_executed': 0}
    if mode == 'strict':
        report['reason'] = 'Latest historical Yahoo/FRED and course snapshots lack historical release/vintage evidence'
        return {'tables': {}, 'market_rows': [], 'schema': schema, 'report': report}
    if not allow_research:
        raise ValueError('research features require explicit allow_research=True')
    if stock_table.get('schema_version') != 'training-table-v1' or not stock_table.get('rows'):
        raise ValueError('nonempty training-table-v1 required')
    if list(stock_table.get('feature_columns', [])) != list(STOCK_FEATURES):
        raise ValueError('input must be the unchanged seven-feature F0 stock baseline')
    keys = [(row['stock_id'], row['target_date']) for row in stock_table['rows']]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate baseline stock/date')
    targets = [{'target_date': day, 'feature_cutoff': cutoff}
               for day, cutoff in _targets(stock_table['rows'])]
    prepared = normalize_history_snapshots(history_manifests, mode='research')
    market = native_feature_rows(prepared['observations'], prepared['native_sessions'], targets)
    fred, fred_audit = fred_feature_rows(external_manifests, targets)
    fred_by_day = {row['target_date']: row for row in fred}
    for row in market:
        row.update(fred_by_day[row['target_date']])
        for series in SECTOR_SERIES:
            row[f'{series}_ret_1s'] = None
    by_day = {row['target_date']: row for row in market}
    missing_sources = sorted(set(MARKET_SERIES) - set(prepared['native_sessions']))
    missing_fred = sorted({'fred_usd_twd', 'fred_us10y'} - set(fred_audit))
    group_status = {'F0': {'status': 'research_assumption', 'reasons': []},
                    'F1': {'status': 'blocked' if set(missing_sources) & set(PRICE_SERIES) else 'research_assumption',
                           'reasons': missing_sources},
                    'F2': {'status': 'blocked' if missing_sources else 'research_assumption', 'reasons': missing_sources},
                    'F3': {'status': 'blocked', 'reasons': ['industry complete historical native sessions/levels unavailable',
                                                         *missing_fred]}}
    tables = {}
    baseline_hash = _hash(stock_table)
    for group in ('F0', 'F1', 'F2', 'F3'):
        extras = schema['group_extra_columns'][group] if group != 'F0' else []
        rows = [dict(row, **{name: by_day[row['target_date']].get(name) for name in extras})
                for row in stock_table['rows']]
        table = dict(stock_table, rows=rows, feature_columns=schema['model_columns'][group],
                     feature_version=VERSION + '-' + group.lower(), readiness=group_status[group]['status'],
                     availability_evidence=stock_table['availability_evidence'] + ' ' +
                     'External features are latest-vintage research assumptions; see expansion_report.',
                     expansion_report={'schema_sha256': schema['schema_sha256'],
                                       'group': group, **group_status[group], 'production_eligible': False},
                     provenance={'base': stock_table['provenance'],
                                 'base_canonical_sha256': baseline_hash,
                                 'history_snapshot_hashes': sorted({o['payload_sha256'] for o in prepared['observations']}),
                                 'fred_sources': fred_audit})
        table['audit'] = dict(stock_table.get('audit', {}), production_eligible=False,
                              unchanged_stock_date_keys=True, preserved_labels=True,
                              extra_missing_counts={name: sum(row[name] is None for row in rows) for name in extras})
        tables[group] = table
    report.update(readiness='research_assumption', target_dates=len(targets), stock_rows=len(keys),
                  group_status=group_status, source_status=prepared['report'], fred_sources=fred_audit,
                  columns={group: table['feature_columns'] for group, table in tables.items()},
                  missing_counts={group: table['audit']['extra_missing_counts'] for group, table in tables.items()},
                  sector_status='blocked_single_snapshot_cannot_produce_historical_native_returns',
                  label_fields_unchanged=True, baseline_keys_sha256=_hash(keys),
                  limitations=['Latest historical vintages are not certified point-in-time inputs.',
                               'FRED quarantine is a frozen research assumption, not verified publication timing.',
                               'F3 industry requirements are not replaced by an easier FX-only group.',
                               'No model was trained; no production feature promotion is implied.'])
    return {'tables': tables, 'market_rows': market, 'schema': schema, 'report': report}
