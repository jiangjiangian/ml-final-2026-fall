"""Bounded, resumable TWSE price-sector history; publication time stays unknown."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
import uuid
from zoneinfo import ZoneInfo

from finpred.data.snapshots import _exclusive_write, snapshot_bytes
from finpred.ingestion.external import network_failure_category

SOURCE = 'twse-sector-history'
BASE_URL = 'https://www.twse.com.tw/exchangeReport/MI_INDEX'
SERIES = {'電子工業類指數': 'tw_electronics', '半導體類指數': 'tw_semiconductor',
          '金融保險類指數': 'tw_financials'}
MAX_BYTES = 8 * 1024 * 1024
NO_DATA = {'很抱歉，沒有符合條件的資料!', '很抱歉，沒有符合條件的資料！'}


class SectorHistoryError(ValueError):
    """A controlled source/storage failure without response contents."""


def _day(value):
    if not isinstance(value, str):
        raise SectorHistoryError('requested date must be an ISO date')
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise SectorHistoryError('requested date must be an ISO date') from None
    if result.isoformat() != value:
        raise SectorHistoryError('requested date must be canonical')
    return result


def request_url(requested_date):
    return BASE_URL + '?response=json&date=' + _day(requested_date).strftime('%Y%m%d') + '&type=IND'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SectorHistoryError('duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise SectorHistoryError('nonfinite JSON constant')


def parse_sector_history(payload, requested_date):
    """Extract exactly three positive PRICE indices for the echoed request day.

    Explicit no-data is retained as a provider response, never certified holiday
    evidence. No returns, publication timestamps or historical vintages are made.
    """
    day = _day(requested_date)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES:
        raise SectorHistoryError('empty or oversized sector response')
    try:
        text = payload.decode('utf-8-sig')
        if text.lstrip().startswith('<'):
            raise SectorHistoryError('sector source returned markup')
        document = json.loads(text, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SectorHistoryError('sector response is not UTF-8 JSON') from None
    if not isinstance(document, dict):
        raise SectorHistoryError('sector response must be an object')
    echoed = document.get('date')
    expected = day.strftime('%Y%m%d')
    if echoed is not None and echoed != expected:
        raise SectorHistoryError('sector source echoed a different date')
    status = document.get('stat')
    if not isinstance(status, str):
        raise SectorHistoryError('sector response lacks a status string')
    if status in NO_DATA:
        if not isinstance(document.get('tables', []), list):
            raise SectorHistoryError('invalid no-data tables')
        if any(table.get('data') for table in document.get('tables', []) if isinstance(table, dict)):
            raise SectorHistoryError('no-data response contains observations')
        return {'status': 'no_data', 'requested_date': requested_date, 'observations': [],
                'date_echo_present': echoed is not None, 'native_calendar_verified': False,
                'historical_vintage_verified': False, 'publication_times_verified': False}
    if status != 'OK' or echoed != expected or not isinstance(document.get('tables'), list):
        raise SectorHistoryError('sector status, echoed date or tables are invalid')
    values = {}
    for table in document['tables']:
        if not isinstance(table, dict):
            raise SectorHistoryError('invalid sector table')
        fields = table.get('fields')
        # Total-return indices use a different first field (報酬指數). A table
        # with another layout is irrelevant, not a substitute for this table.
        if not isinstance(fields, list) or not fields or fields[0] != '指數':
            continue
        if fields.count('收盤指數') != 1 or not isinstance(table.get('data'), list):
            raise SectorHistoryError('invalid price-index table layout')
        column = fields.index('收盤指數')
        for row in table['data']:
            if not isinstance(row, list) or len(row) != len(fields):
                raise SectorHistoryError('invalid price-index row')
            if not isinstance(row[0], str):
                raise SectorHistoryError('invalid price-index name')
            if row[0] not in SERIES:
                continue
            series = SERIES[row[0]]
            if series in values or not isinstance(row[column], str):
                raise SectorHistoryError('duplicate or nonnumeric sector value')
            try:
                value = float(row[column].replace(',', ''))
            except ValueError:
                raise SectorHistoryError('invalid sector number') from None
            if not math.isfinite(value) or value <= 0:
                raise SectorHistoryError('sector values must be positive and finite')
            values[series] = value
    if set(values) != set(SERIES.values()):
        raise SectorHistoryError('price-index table must contain all three sectors')
    return {'status': 'captured', 'requested_date': requested_date,
            'date_echo_present': True,
            'observations': [{'series_id': series, 'provider_observation_date': requested_date,
                              'value': values[series], 'unit': 'index_point'} for series in SERIES.values()],
            'native_calendar_verified': False, 'historical_vintage_verified': False,
            'publication_times_verified': False}


def calendar_dates(start, end):
    """Inclusive calendar dates, including weekends; no assumed exchange calendar."""
    first, last = _day(start), _day(end)
    if last < first or (last - first).days > 20_000:
        raise SectorHistoryError('invalid or oversized calendar range')
    return [(first + timedelta(days=index)).isoformat() for index in range((last - first).days + 1)]


def _root(value):
    path = Path(value).absolute()
    if any(part.is_symlink() or (part / '.git').exists() for part in (path, *path.parents)):
        raise SectorHistoryError('history storage must be outside Git without symlinks')
    missing, parent = [], path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for part in reversed(missing):
        part.mkdir(mode=0o700)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise SectorHistoryError('history storage must be a locally owned directory')
    path.chmod(0o700)
    for name in ('raw', 'coverage', 'runs', 'raw/' + SOURCE,
                 'raw/' + SOURCE + '/objects', 'raw/' + SOURCE + '/manifests'):
        child = path / name
        if child.is_symlink():
            raise SectorHistoryError('history storage contains a symlink')
        child.mkdir(mode=0o700, exist_ok=True)
        if not child.is_dir() or child.stat().st_uid != os.getuid():
            raise SectorHistoryError('history child must be a locally owned directory')
        child.chmod(0o700)
    return path


def _read(path, limit=MAX_BYTES):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise SectorHistoryError('history input cannot contain symlinks')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > limit):
            raise SectorHistoryError('history input must be a bounded private regular file')
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise SectorHistoryError('history input exceeded its bound')
    return payload


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def _persist(path, value):
    _exclusive_write(path, _json(value))
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cached(root, day):
    receipt_path = root / 'coverage' / (day + '.json')
    if not receipt_path.exists():
        return None
    receipt = json.loads(_read(receipt_path), object_pairs_hook=_unique)
    if (receipt.get('schema_version') != 'twse-sector-day-v1' or receipt.get('requested_date') != day
            or receipt.get('request_url') != request_url(day)):
        raise SectorHistoryError('cached sector coverage identity mismatch')
    manifest_key = receipt.get('manifest_key')
    if not isinstance(manifest_key, str):
        raise SectorHistoryError('cached manifest key is missing')
    manifest_path = root / manifest_key
    if (manifest_path.parent != root / 'raw' / SOURCE / 'manifests'
            or manifest_path.suffix != '.json'):
        raise SectorHistoryError('cached manifest escaped its source')
    manifest_bytes = _read(manifest_path)
    if hashlib.sha256(manifest_bytes).hexdigest() != receipt.get('manifest_sha256'):
        raise SectorHistoryError('cached sector manifest hash mismatch')
    manifest = json.loads(manifest_bytes, object_pairs_hook=_unique)
    digest = manifest.get('sha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise SectorHistoryError('cached sector payload hash is invalid')
    payload = _read(root / 'raw' / SOURCE / 'objects' / (digest + '.json'))
    metadata = manifest.get('metadata', {})
    if (manifest.get('source') != SOURCE or manifest.get('source_url') != BASE_URL
            or manifest.get('size_bytes') != len(payload) or hashlib.sha256(payload).hexdigest() != digest
            or metadata.get('tls_verified') is not True or metadata.get('request_url') != request_url(day)
            or metadata.get('requested_date') != day or receipt.get('fetched_at') != manifest.get('fetched_at')
            or receipt.get('sha256') != digest):
        raise SectorHistoryError('cached sector provenance mismatch')
    parsed = parse_sector_history(payload, day)
    if any(receipt.get(key) != value for key, value in parsed.items()):
        raise SectorHistoryError('cached sector values differ from raw response')
    return receipt


def _fetch(session, day):
    import requests
    response = None
    try:
        response = session.get(request_url(day), timeout=(10, 25), allow_redirects=False,
                               verify=True, stream=True,
                               headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        if response.status_code != 200:
            raise SectorHistoryError('sector HTTP status was not 200')
        if 'html' in response.headers.get('Content-Type', '').lower():
            raise SectorHistoryError('sector source returned HTML')
        parts, size = [], 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise SectorHistoryError('sector response exceeded its bound')
            parts.append(chunk)
        return b''.join(parts)
    except requests.RequestException as error:
        raise SectorHistoryError('sector_network_' + network_failure_category(error)) from None
    finally:
        if response is not None:
            response.close()


def collect_sector_history(root_dir, requested_dates, *, max_new_dates=3, interval_seconds=2.0,
                           session=None, sleeper=time.sleep, clock=None):
    """Acquire at most 30 uncached calendar dates; cache is hash-checked on resume.

    One GET per new date; failures do not become coverage and can be retried on a
    later bounded invocation. A flock excludes concurrent writers to this cache.
    """
    if (isinstance(max_new_dates, bool) or not isinstance(max_new_dates, int)
            or not 1 <= max_new_dates <= 30):
        raise SectorHistoryError('max-new-dates must be between 1 and 30')
    if (isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds) or not 1 <= interval_seconds <= 30):
        raise SectorHistoryError('request interval must be between 1 and 30 seconds')
    days = sorted(set(requested_dates))
    if not days or len(days) > 20_001:
        raise SectorHistoryError('request between 1 and 20001 calendar dates')
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.utcoffset() is None:
        raise SectorHistoryError('acquisition clock needs a timezone')
    for day in days:
        if _day(day) > now.astimezone(ZoneInfo('Asia/Taipei')).date():
            raise SectorHistoryError('future calendar dates cannot be acquired')
    root = _root(root_dir)
    lock_fd = os.open(root / '.collection.lock',
                      os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    lock_info = os.fstat(lock_fd)
    if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.getuid()
            or lock_info.st_mode & 0o077):
        os.close(lock_fd)
        raise SectorHistoryError('collection lock must be a locally owned private regular file')
    owned_session = session is None
    result = {'schema_version': 'twse-sector-collection-v1', 'started_at': now.isoformat(),
              'source': SOURCE, 'calendar_basis': 'all_requested_calendar_dates_including_weekends',
              'native_calendar_verified': False, 'historical_vintage_verified': False,
              'publication_times_verified': False, 'production_eligible': False,
              'requested_count': len(days), 'attempted_new_dates': 0, 'cached_dates': 0,
              'deferred_dates': 0, 'dates': [], 'failures': []}
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if owned_session:
            import requests
            session = requests.Session()  # No automatic network/POST retry.
        for day in days:
            cached = _cached(root, day)
            if cached is not None:
                result['cached_dates'] += 1
                result['dates'].append({'requested_date': day, 'status': cached['status'], 'cached': True})
                continue
            if result['attempted_new_dates'] >= max_new_dates:
                result['deferred_dates'] += 1
                continue
            if result['attempted_new_dates']:
                sleeper(interval_seconds)
            result['attempted_new_dates'] += 1
            try:
                payload = _fetch(session, day)
                parsed = parse_sector_history(payload, day)
                manifest = snapshot_bytes(payload, root / 'raw', SOURCE, request_url(day), '.json',
                                          metadata={'requested_date': day, 'request_url': request_url(day),
                                                    'tls_verified': True, 'audit': parsed,
                                                    'historical_vintage_verified': False,
                                                    'publication_times_verified': False})
                manifest_path = Path(manifest['manifest_path'])
                receipt = {'schema_version': 'twse-sector-day-v1', **parsed,
                           'request_url': request_url(day), 'sha256': manifest['sha256'],
                           'fetched_at': manifest['fetched_at'],
                           'manifest_key': str(manifest_path.relative_to(root)),
                           'manifest_sha256': hashlib.sha256(_read(manifest_path)).hexdigest(),
                           'published_at': None, 'available_at': None,
                           'limitation': 'No-data is a provider response, not certified holiday evidence; '
                                         'historical publication and adjustment vintages are unverified.'}
                _persist(root / 'coverage' / (day + '.json'), receipt)
                result['dates'].append({'requested_date': day, 'status': parsed['status'], 'cached': False})
            except SectorHistoryError as error:
                result['failures'].append({'requested_date': day, 'status': 'failed', 'category': str(error)})
        result['status'] = ('partial_failure' if result['failures'] else
                            'bounded_partial' if result['deferred_dates'] else 'captured')
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        run = root / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ_') + uuid.uuid4().hex + '.json')
        _persist(run, result)
        result['run_path'] = str(run)
        return result
    finally:
        if owned_session and session is not None:
            session.close()
        os.close(lock_fd)
