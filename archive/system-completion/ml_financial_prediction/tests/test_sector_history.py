"""Sector parsing, no-data semantics, bounded fetch and immutable resume."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import requests

from finpred.ingestion.sector_history import (
    BASE_URL, SERIES, SectorHistoryError, calendar_dates, collect_sector_history,
    parse_sector_history, request_url,
)


def payload(day='20200102', **changes):
    value = {'stat': 'OK', 'date': day, 'tables': [
        {'fields': ['指數', '收盤指數', '漲跌'],
         'data': [[name, number, '+'] for name, number in zip(SERIES, ['535.08', '228.87', '1,360.12'])]},
        {'fields': ['報酬指數', '收盤指數'],
         'data': [[name, '999999'] for name in SERIES]}]}
    value.update(changes)
    return json.dumps(value, ensure_ascii=False).encode()


class Response:
    def __init__(self, content, status=200, content_type='application/json'):
        self.content = content
        self.status_code = status
        self.headers = {'Content-Type': content_type}
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class SectorHistoryTests(unittest.TestCase):
    def test_price_indices_only_and_exact_values(self):
        rows = parse_sector_history(payload(), '2020-01-02')['observations']
        self.assertEqual([r['value'] for r in rows], [535.08, 228.87, 1360.12])
        self.assertEqual([r['series_id'] for r in rows], list(SERIES.values()))
        self.assertTrue(all(r['provider_observation_date'] == '2020-01-02' for r in rows))
        self.assertTrue(all(r['unit'] == 'index_point' for r in rows))

    def test_wrong_date_html_duplicates_nonfinite_and_missing_price_fail(self):
        duplicate = json.loads(payload())
        duplicate['tables'][0]['data'].append(duplicate['tables'][0]['data'][0])
        for bad in [payload('20200103'), b'<html>error</html>', b'{"stat":"OK","stat":"OK"}',
                    payload(tables=[{'fields': ['報酬指數', '收盤指數'],
                                     'data': [[n, '100'] for n in SERIES]}]),
                    json.dumps(duplicate).encode(), payload(date=None)]:
            with self.subTest(bad=bad[:100]), self.assertRaises(SectorHistoryError):
                parse_sector_history(bad, '2020-01-02')
        for invalid in ['NaN', 'Infinity', '-1', '0', '--', 100, True]:
            document = json.loads(payload())
            document['tables'][0]['data'][0][1] = invalid
            with self.subTest(value=invalid), self.assertRaises(SectorHistoryError):
                parse_sector_history(json.dumps(document).encode(), '2020-01-02')

    def test_explicit_no_data_is_not_an_exchange_holiday(self):
        result = parse_sector_history(json.dumps({'stat': '很抱歉，沒有符合條件的資料!'}).encode(), '2020-01-04')
        self.assertEqual(result['status'], 'no_data')
        self.assertEqual(result['observations'], [])
        self.assertFalse(result['native_calendar_verified'])
        self.assertFalse(result['date_echo_present'])
        for bad in [payload(stat='service unavailable'), payload(stat='很抱歉，沒有符合條件的資料!'),
                    payload(stat='很抱歉，沒有符合條件的資料!', tables=1)]:
            with self.assertRaises(SectorHistoryError):
                parse_sector_history(bad, '2020-01-02')

    def test_calendar_range_keeps_weekends_and_has_finite_bounds(self):
        self.assertEqual(calendar_dates('2020-01-03', '2020-01-06'),
                         ['2020-01-03', '2020-01-04', '2020-01-05', '2020-01-06'])
        self.assertIn('date=20200102&type=IND', request_url('2020-01-02'))
        for first, last in [('20200103', '2020-01-06'), ('2020-01-06', '2020-01-03')]:
            with self.assertRaises(SectorHistoryError):
                calendar_dates(first, last)

    def test_bounded_fetch_and_resume_preserve_hash_time_and_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'history'
            responses = [Response(payload()), Response(payload('20200103'))]
            session = Session(responses)
            sleeps = []
            days = calendar_dates('2020-01-02', '2020-01-04')
            first = collect_sector_history(root, days, max_new_dates=2, interval_seconds=1,
                                           session=session, sleeper=sleeps.append)
            self.assertEqual((first['attempted_new_dates'], first['deferred_dates']), (2, 1))
            self.assertEqual(sleeps, [1])
            self.assertTrue(all(response.closed for response in responses))
            for url, options in session.calls:
                self.assertTrue(url.startswith(BASE_URL + '?response=json&date='))
                self.assertIs(options['verify'], True)
                self.assertIs(options['allow_redirects'], False)
                self.assertEqual(options['timeout'], (10, 25))
            receipt_path = root / 'coverage' / '2020-01-02.json'
            original = receipt_path.read_bytes()
            receipt = json.loads(original)
            manifest = json.loads((root / receipt['manifest_key']).read_bytes())
            self.assertEqual(manifest['source_url'], BASE_URL)
            self.assertEqual(manifest['metadata']['request_url'], request_url('2020-01-02'))
            self.assertEqual(receipt['sha256'], hashlib.sha256(payload()).hexdigest())
            self.assertGreater(datetime.fromisoformat(receipt['fetched_at']).year, 2020)
            self.assertIsNone(receipt['published_at'])
            no_data = Response(json.dumps({'stat': '很抱歉，沒有符合條件的資料!'}).encode())
            second_session = Session([no_data])
            resumed = collect_sector_history(root, days, max_new_dates=1, session=second_session)
            self.assertEqual((resumed['cached_dates'], resumed['attempted_new_dates']), (2, 1))
            self.assertEqual(receipt_path.read_bytes(), original)
            self.assertEqual(len(second_session.calls), 1)
            self.assertEqual(resumed['dates'][-1]['status'], 'no_data')
            self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(receipt_path).st_mode & 0o777, 0o600)

    def test_network_failure_and_no_data_are_distinct_and_failure_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'history'
            result = collect_sector_history(root, ['2020-01-02'], session=Session([requests.exceptions.SSLError('secret')]))
            self.assertEqual(result['status'], 'partial_failure')
            self.assertEqual(result['failures'][0]['category'], 'sector_network_tls_failure')
            self.assertNotIn('secret', json.dumps(result))
            self.assertFalse((root / 'coverage' / '2020-01-02.json').exists())
            retried = collect_sector_history(root, ['2020-01-02'], session=Session([Response(payload())]))
            self.assertEqual(retried['status'], 'captured')

    def test_redirect_html_and_corrupted_cache_are_rejected(self):
        for response in [Response(payload(), status=302), Response(payload(), content_type='text/html')]:
            with tempfile.TemporaryDirectory() as temporary:
                result = collect_sector_history(temporary, ['2020-01-02'], session=Session([response]))
                self.assertEqual(result['status'], 'partial_failure')
                self.assertTrue(response.closed)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collect_sector_history(root, ['2020-01-02'], session=Session([Response(payload())]))
            receipt = json.loads((root / 'coverage' / '2020-01-02.json').read_bytes())
            manifest_path = root / receipt['manifest_key']
            manifest_path.write_bytes(b'{}')
            with self.assertRaises(SectorHistoryError):
                collect_sector_history(root, ['2020-01-02'], session=Session([]))

    def test_bounds_future_date_and_storage_symlinks_are_rejected(self):
        def now():
            return datetime(2026, 11, 4, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            for kwargs in [{'max_new_dates': 0}, {'max_new_dates': 31}, {'interval_seconds': 0},
                           {'interval_seconds': float('nan')}]:
                with self.assertRaises(SectorHistoryError):
                    collect_sector_history(temporary, ['2020-01-02'], session=Session([]), **kwargs)
            with self.assertRaises(SectorHistoryError):
                collect_sector_history(temporary, ['2026-11-05'], session=Session([]), clock=now)
            root = Path(temporary) / 'bad'
            root.mkdir()
            (root / 'raw').symlink_to(Path(temporary))
            with self.assertRaises(SectorHistoryError):
                collect_sector_history(root, ['2020-01-02'], session=Session([]))


if __name__ == '__main__':
    unittest.main()
