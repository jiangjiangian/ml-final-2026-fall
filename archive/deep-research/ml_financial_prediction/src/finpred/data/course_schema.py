"""Validate course raw archives without inferring historical availability."""

import csv
import hashlib
import io
import json
import math
import re
import stat
import zipfile
from datetime import date
from pathlib import PurePosixPath

GLOBAL_COLUMNS = ('date', '^VIX', '^IXIC', '^GSPC', '^TWII', '^KS11', 'TX_OI')
STOCK_COLUMNS = (
    'date', 'etl:adj_close', 'etl:adj_open', 'etl:adj_high', 'etl:adj_low',
    'price:成交筆數', 'price:成交金額', 'price:成交股數',
    'foreign_investors_shareholding:全體外資及陸資持股比率',
    'institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)',
    'institutional_investors_trading_summary:投信買賣超股數',
    'institutional_investors_trading_summary:自營商買賣超股數(自行買賣)',
    'institutional_investors_trading_summary:自營商買賣超股數(避險)',
    'RSI', 'SMA', 'MACD', 'ATR', 'BBANDS_upper', 'BBANDS_mid', 'BBANDS_lower', 'y',
)
LABEL_COLUMNS = ('y', 'etl:adj_open', 'etl:adj_close', 'etl:adj_high', 'etl:adj_low')
MISSING = {'', 'nan', 'null', 'none'}
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


class CourseSchemaError(ValueError):
    """A source payload violates the known course archive contract."""


def _number(raw):
    if raw.strip().lower() in MISSING:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise CourseSchemaError('nonnumeric value in numeric column') from None
    if not math.isfinite(value):
        raise CourseSchemaError('nonfinite value in numeric column')
    return value


def partition_stock_row(row, stock_id):
    """Separate outcomes from raw candidates; candidates still need time validation.

    All values remain raw strings. Current-day volume/indicators in candidates are
    NOT approved premarket features and must pass the availability adapter later.
    """
    key = {'stock_id': str(stock_id), 'target_date': row['date']}
    return (
        {**key, **{name: row[name] for name in LABEL_COLUMNS}},
        {**key, **{name: value for name, value in row.items()
                  if name not in LABEL_COLUMNS and name != 'date'}},
    )


def _rows(raw, expected_columns):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise CourseSchemaError('unexpected CSV columns or column order')
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise CourseSchemaError('malformed CSV encoding or syntax') from None
    if not rows:
        raise CourseSchemaError('empty CSV')
    dates, missing, minus_one = [], dict.fromkeys(expected_columns[1:], 0), dict.fromkeys(expected_columns[1:], 0)
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise CourseSchemaError('CSV row has incorrect width')
        try:
            parsed = date.fromisoformat(row['date'])
            if parsed.isoformat() != row['date']:
                raise ValueError
        except ValueError:
            raise CourseSchemaError('invalid ISO date') from None
        dates.append(row['date'])
        for key in expected_columns[1:]:
            value = _number(row[key])
            missing[key] += value is None
            minus_one[key] += value == -1
    if dates != sorted(set(dates)):
        raise CourseSchemaError('CSV dates must be sorted and unique')
    return rows, {'row_count': len(rows), 'date_min': dates[0], 'date_max': dates[-1],
                  'missing_by_column': missing, 'minus_one_by_column': minus_one}


def audit_course_zip(payload, kind='training', expected_stock_ids=None, expected_stock_count=100,
                     expected_target_count=50):
    """Audit every CSV and y. This does not establish point-in-time readiness."""
    if kind not in {'training', 'live'}:
        raise CourseSchemaError('kind must be training or live')
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise CourseSchemaError('archive payload empty or exceeds size limit')
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise CourseSchemaError('download is not a ZIP archive') from None
    with archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 1000:
            raise CourseSchemaError('duplicate or excessive ZIP members')
        if sum(item.file_size for item in members) > MAX_UNCOMPRESSED_BYTES:
            raise CourseSchemaError('ZIP exceeds uncompressed size limit')
        for item in members:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or item.is_dir() or stat.S_ISLNK(mode) or item.flag_bits & 1):
                raise CourseSchemaError('unsafe ZIP member')
        try:
            if archive.testzip() is not None:
                raise CourseSchemaError('ZIP CRC check failed')
            stock_names = [name for name in names if re.fullmatch(r'data/market/[0-9]+\.csv', name)]
            stock_ids = sorted(PurePosixPath(name).stem for name in stock_names)
            if len(stock_ids) != expected_stock_count:
                raise CourseSchemaError('unexpected stock universe size')
            required = set(stock_names) | {'data/global/global_data.csv'}
            if kind == 'training':
                required.add('data/info.json')
            if set(names) != required:
                raise CourseSchemaError('unexpected or missing ZIP members')
            info = None
            if kind == 'training':
                info = json.loads(archive.read('data/info.json').decode('utf-8-sig'))
                if set(info) != {'Top50@Y', 'Top100@Y'}:
                    raise CourseSchemaError('unexpected stock-list metadata')
                for key in info:
                    if not isinstance(info[key], list) or not info[key]:
                        raise CourseSchemaError('invalid stock-list metadata')
                    info[key] = [str(value) for value in info[key]]
                    if len(info[key]) != len(set(info[key])):
                        raise CourseSchemaError('duplicate stock-list entry')
                if set(info['Top100@Y']) != set(stock_ids) or not set(info['Top50@Y']) <= set(stock_ids):
                    raise CourseSchemaError('stock-list metadata differs from archive universe')
                if len(info['Top50@Y']) != expected_target_count:
                    raise CourseSchemaError('unexpected target stock universe size')
            if expected_stock_ids is not None and set(map(str, expected_stock_ids)) != set(stock_ids):
                raise CourseSchemaError('stock universe differs from reference snapshot')
            _, global_summary = _rows(archive.read('data/global/global_data.csv'), GLOBAL_COLUMNS)
            summaries, complete, pending, pending_dates = {}, 0, 0, set()
            for name in sorted(stock_names):
                rows, summary = _rows(archive.read(name), STOCK_COLUMNS)
                summary.update({'complete_labels': 0, 'pending_labels': 0})
                for row in rows:
                    label = _number(row['y'])
                    if label == -1 and kind == 'live':
                        pending += 1
                        summary['pending_labels'] += 1
                        pending_dates.add(row['date'])
                        continue
                    if label not in {0, 1}:
                        raise CourseSchemaError('invalid or missing binary label')
                    opening, closing = _number(row['etl:adj_open']), _number(row['etl:adj_close'])
                    if opening is None or closing is None or opening <= 0 or closing <= 0:
                        raise CourseSchemaError('completed label has invalid prices')
                    if label != int(closing > opening):
                        raise CourseSchemaError('binary label disagrees with adjusted prices')
                    complete += 1
                    summary['complete_labels'] += 1
                summaries[PurePosixPath(name).stem] = summary
        except (zipfile.BadZipFile, RuntimeError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            raise CourseSchemaError('malformed archive data') from None
    return {
        'schema_version': 'course-raw-v1', 'kind': kind,
        'payload_sha256': hashlib.sha256(payload).hexdigest(), 'member_count': len(names),
        'zip_crc_checked': True, 'stock_count': len(stock_ids), 'stock_ids': stock_ids,
        'stock_columns': list(STOCK_COLUMNS), 'global_columns': list(GLOBAL_COLUMNS),
        'global': global_summary, 'stocks': summaries, 'info': info,
        'stock_rows': sum(item['row_count'] for item in summaries.values()),
        'complete_labels': complete, 'pending_labels': pending, 'pending_label_dates': sorted(pending_dates),
        'partitions': {'outcome_columns': list(LABEL_COLUMNS),
                       'raw_candidate_columns': [name for name in STOCK_COLUMNS if name not in LABEL_COLUMNS and name != 'date']},
        'readiness': {'raw_schema': 'validated', 'labels': 'partial' if pending else 'complete',
                      'historical_availability': 'unverified', 'training': 'blocked_pending_time_evidence'},
        'minus_one_policy': 'Raw -1 preserved; may be unknown or a real signed value; no per-cell mask inferred.',
    }


def compare_course_archives(before_bytes, after_bytes, kind='live', *, expected_stock_count=100,
                            expected_target_count=50):
    """Compare validated raw snapshots by stock/date and global/date keys.

    Cell changes use exact raw strings and can include representation changes.
    Missing rows describe these snapshots, never an upstream deletion instruction.
    A caller must merge history under its own version policy rather than blindly
    appending (revisions exist) or treating a short Live window as replacement.
    """
    before = audit_course_zip(before_bytes, kind, expected_stock_count=expected_stock_count,
                              expected_target_count=expected_target_count)
    after = audit_course_zip(after_bytes, kind, expected_stock_ids=before['stock_ids'],
                             expected_stock_count=expected_stock_count,
                             expected_target_count=expected_target_count)

    def keyed_tables(payload):
        stock, global_rows = {}, {}
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if re.fullmatch(r'data/market/[0-9]+\.csv', name):
                    stock_id = PurePosixPath(name).stem
                    rows, _ = _rows(archive.read(name), STOCK_COLUMNS)
                    stock.update({(stock_id, row['date']): row for row in rows})
                elif name == 'data/global/global_data.csv':
                    rows, _ = _rows(archive.read(name), GLOBAL_COLUMNS)
                    global_rows.update({row['date']: row for row in rows})
        return stock, global_rows

    def difference(old, new, is_stock):
        shared = old.keys() & new.keys()
        by_column, changed, pending_to_complete = {}, 0, 0
        for key in shared:
            columns = [column for column in old[key] if old[key][column] != new[key][column]]
            changed += bool(columns)
            for column in columns:
                by_column[column] = by_column.get(column, 0) + 1
            if is_stock and _number(old[key]['y']) == -1 and _number(new[key]['y']) in {0, 1}:
                pending_to_complete += 1
        result = {'before_keys': len(old), 'after_keys': len(new),
                  'added_keys': len(new.keys() - old.keys()),
                  'removed_keys': len(old.keys() - new.keys()),
                  'changed_keys': changed, 'unchanged_shared_keys': len(shared) - changed,
                  'changed_by_column': dict(sorted(by_column.items()))}
        if is_stock:
            result['pending_to_complete'] = pending_to_complete
        return result

    old_stock, old_global = keyed_tables(before_bytes)
    new_stock, new_global = keyed_tables(after_bytes)
    return {'schema_version': 'course-snapshot-diff-v1', 'kind': kind,
            'before_sha256': before['payload_sha256'], 'after_sha256': after['payload_sha256'],
            'stocks': difference(old_stock, new_stock, True),
            'global': difference(old_global, new_global, False),
            'info_changed': before['info'] != after['info'],
            'change_semantics': 'Exact raw cells; numeric formatting changes are included.',
            'absence_semantics': 'Missing keys describe snapshot contents, not proven upstream deletions.'}
