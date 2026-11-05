"""Verified course endpoints with bounded HTTPS and memory-only sessions."""

import csv
import io
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from finpred.data.course_schema import MAX_ARCHIVE_BYTES, audit_course_zip
from finpred.data.snapshots import _exclusive_write, _private_dir, snapshot_bytes

COURSE_BASE = 'https://final.html2026.csie.org'
LIVE_BASE = 'https://fin-pred-daily.jiangxuehaokeai.chatgpt.site'
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'


class CourseDownloadError(RuntimeError):
    """A bounded public error; source response bodies and credentials are omitted."""


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' and attributes.get('src'):
            self.paths.append(attributes['src'])


class VerifiedSession:
    """Allow only the configured HTTPS origin, including across redirects."""

    def __init__(self, base_url, session=None):
        self.base = base_url
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT, 'Accept': '*/*'})
        retry = Retry(total=2, connect=2, read=0, status=2, backoff_factor=0.5,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods={'GET'},
                      respect_retry_after_header=False)
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    def close(self):
        self.session.close()

    def read(self, method, path, *, max_bytes=MAX_ARCHIVE_BYTES, **kwargs):
        url = urljoin(self.base + '/', path)
        origin = urlsplit(self.base)
        for _ in range(4):
            parts = urlsplit(url)
            if (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc) or parts.username or parts.password:
                raise CourseDownloadError('cross-origin or unsafe redirect rejected')
            try:
                response = self.session.request(method, url, timeout=(10, 90), verify=True,
                                                allow_redirects=False, stream=True, **kwargs)
            except requests.RequestException:
                raise CourseDownloadError('HTTPS request failed; response and credentials omitted') from None
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location')
                    if not location:
                        raise CourseDownloadError('redirect missing destination')
                    url = urljoin(url, location)
                    if response.status_code == 303 or (response.status_code in (301, 302) and method == 'POST'):
                        method, kwargs = 'GET', {}
                    continue
                if response.status_code != 200:
                    raise CourseDownloadError(f'endpoint returned HTTP {response.status_code}; body omitted')
                chunks, length = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    length += len(chunk)
                    if length > max_bytes:
                        raise CourseDownloadError('response exceeds payload size limit')
                    chunks.append(chunk)
                return b''.join(chunks)
            except requests.RequestException:
                raise CourseDownloadError('HTTPS response interrupted; credentials omitted') from None
            finally:
                response.close()
        raise CourseDownloadError('redirect limit exceeded')


class CourseClient(VerifiedSession):
    def __init__(self, session=None):
        super().__init__(COURSE_BASE, session)

    def login(self, email, password):
        if not email or not password:
            raise CourseDownloadError('COURSE_EMAIL and COURSE_PASSWORD are required')
        raw = self.read('POST', '/api/auth/login', max_bytes=1024 * 1024,
                        json={'email': email, 'password': password},
                        headers={'Origin': COURSE_BASE, 'Referer': COURSE_BASE + '/login'})
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CourseDownloadError('course login did not return expected JSON') from None
        if not isinstance(result, dict) or result.get('success') is False or result.get('error'):
            raise CourseDownloadError('course login rejected; response omitted')

    def training_zip(self):
        return self.read('GET', '/downloads/fin_pred_data.zip')

    def template(self):
        return self.read('GET', '/api/sample-submission?phase=1', max_bytes=1024 * 1024)

    def published_live_key(self):
        """Read the exact public frontend pattern already verified for this course."""
        parser = _Scripts()
        parser.feed(self.read('GET', '/', max_bytes=4 * 1024 * 1024).decode('utf-8'))
        pattern = r'https://140\.112\.31\.182:8444/["\']\s*,\s*[A-Za-z_$][\w$]*=["\']([A-Za-z0-9_-]+)["\']'
        for path in parser.paths[:20]:
            source = self.read('GET', path, max_bytes=8 * 1024 * 1024).decode('utf-8')
            match = re.search(pattern, source)
            if match:
                return match.group(1)
        raise CourseDownloadError('published live key not found; set COURSE_LIVE_KEY via secret environment')


class LiveClient(VerifiedSession):
    def __init__(self, session=None):
        super().__init__(LIVE_BASE, session)

    def login(self, key):
        if not key:
            raise CourseDownloadError('live access key is required')
        raw = self.read('POST', '/login', data={'key': key}, max_bytes=4 * 1024 * 1024,
                        headers={'Origin': LIVE_BASE, 'Referer': LIVE_BASE + '/'})
        if not re.search(rb'href=["\']/data\.zip["\']', raw):
            raise CourseDownloadError('live login did not expose the verified download link')

    def data_zip(self):
        return self.read('GET', '/data.zip', headers={'Referer': LIVE_BASE + '/'})


def audit_template(payload, expected_stock_ids=None, *, expected_target_count=50):
    try:
        rows = list(csv.reader(io.StringIO(payload.decode('utf-8-sig'))))
        if len(rows) < 2 or rows[0][0] != 'id' or len(rows[0]) < 2:
            raise ValueError
        dates = rows[0][1:]
        if dates != sorted(set(dates)) or any(date.fromisoformat(day).isoformat() != day for day in dates):
            raise ValueError
        ids = [row[0] for row in rows[1:]]
        if len(ids) != expected_target_count:
            raise ValueError
        if len(ids) != len(set(ids)) or not all(re.fullmatch(r'[0-9]+', sid) for sid in ids):
            raise ValueError
        if any(len(row) != len(rows[0]) for row in rows):
            raise ValueError
        if any(value not in {'0', '1'} for row in rows[1:] for value in row[1:]):
            raise ValueError
        if expected_stock_ids is not None and ids != list(expected_stock_ids):
            raise ValueError
    except (ValueError, IndexError, UnicodeDecodeError, csv.Error):
        raise CourseDownloadError('malformed Phase 1 template') from None
    return {'stock_count': len(ids), 'target_dates': dates, 'stock_ids': ids}


def download_course_sources(root, source='both', *, email=None, password=None, live_key=None):
    """Acquire independently manifested sources; previous snapshots survive failures."""
    if source not in {'training', 'live', 'both'}:
        raise ValueError('source must be training, live, or both')
    root = Path(root).resolve()
    live_key = live_key or os.environ.get('COURSE_LIVE_KEY')
    course, live = CourseClient(), LiveClient()
    records, training_audit = [], None
    try:
        if source != 'live' or not live_key:
            course.login(email or os.environ.get('COURSE_EMAIL'), password or os.environ.get('COURSE_PASSWORD'))
        if source in {'training', 'both'}:
            payload = course.training_zip()
            training_audit = audit_course_zip(payload, 'training')
            records.append(snapshot_bytes(payload, root, 'course-training', COURSE_BASE + '/downloads/fin_pred_data.zip',
                                          '.zip', {'tls_verified': True, 'audit': training_audit}))
            template = course.template()
            template_audit = audit_template(template, training_audit['info']['Top50@Y'])
            records.append(snapshot_bytes(template, root, 'course-template', COURSE_BASE + '/api/sample-submission',
                                          '.csv', {'tls_verified': True, 'audit': template_audit}))
        if source in {'live', 'both'}:
            key = live_key or os.environ.get('COURSE_LIVE_KEY') or course.published_live_key()
            live.login(key)
            payload = live.data_zip()
            reference = training_audit['stock_ids'] if training_audit else None
            report = audit_course_zip(payload, 'live', expected_stock_ids=reference)
            records.append(snapshot_bytes(payload, root, 'course-live', LIVE_BASE + '/data.zip',
                                          '.zip', {'tls_verified': True, 'audit': report}))
        return records
    except Exception as error:
        _private_dir(root)
        failure = {'status': 'failed', 'source': source, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                   'error_type': type(error).__name__, 'completed_manifests': [r['manifest_path'] for r in records],
                   'detail': 'Acquisition failed; original response, credentials and exception text omitted.'}
        path = root / ('failure_' + uuid.uuid4().hex + '.json')
        _exclusive_write(path, (json.dumps(failure, indent=2) + '\n').encode())
        raise
    finally:
        course.close()
        live.close()
