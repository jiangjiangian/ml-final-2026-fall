"""Snapshot eligibility, real-buffer integrity and target-outcome isolation."""

import csv
import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from finpred.data.course_schema import GLOBAL_COLUMNS, STOCK_COLUMNS
from finpred.data.daily_tables import (
    SOURCE_URLS, prediction_rows_from_history, prepare_prediction_table, prepare_training_table,
)
from finpred.data.snapshots import snapshot_bytes
from finpred.features.stock import STOCK_FEATURES

IDS = [f'{n:04}' for n in range(1, 101)]
DAY = '2026-11-02'


def csv_payload(columns, rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def row(day, *, close=11, pending=False):
    output = dict.fromkeys(STOCK_COLUMNS, '1')
    output.update({'date': day, 'etl:adj_open': '10', 'etl:adj_close': str(close),
                   'RSI': '50', 'SMA': '10', 'ATR': '1', 'price:成交股數': '100',
                   'y': '-1' if pending else str(int(close > 10))})
    return output


def archive(kind, *, prior_close=11, pending=False, current_close=12):
    rows = ([row('2026-10-28'), row('2026-10-29')]
            if kind == 'training' else [row('2026-10-30', close=prior_close, pending=pending),
                                       row(DAY, close=current_close)])
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for sid in IDS:
            zipped.writestr(f'data/market/{sid}.csv', csv_payload(STOCK_COLUMNS, rows))
        global_rows = [dict.fromkeys(GLOBAL_COLUMNS, '1') | {'date': rows[-1]['date']}]
        zipped.writestr('data/global/global_data.csv', csv_payload(GLOBAL_COLUMNS, global_rows))
        if kind == 'training':
            zipped.writestr('data/info.json', json.dumps({'Top50@Y': IDS[:50], 'Top100@Y': IDS}))
    return output.getvalue()


def acquire(root, kind, fetched_at, **kwargs):
    source = 'course-' + kind
    with patch('finpred.data.snapshots.datetime') as clock:
        clock.now.return_value = datetime.fromisoformat(fetched_at)
        return snapshot_bytes(archive(kind, **kwargs), Path(root) / 'raw', source,
                              SOURCE_URLS[source], '.zip', {'tls_verified': True})


def index(root, records):
    path = Path(root) / 'latest_collection.json'
    path.write_text(json.dumps({'status': 'collected', 'manifests': [r['manifest_path'] for r in records]}))
    path.chmod(0o600)


class DailyTablesTests(unittest.TestCase):
    def inputs(self, root, **live_options):
        training = acquire(root, 'training', DAY + 'T06:00:00+08:00')
        live = acquire(root, 'live', DAY + 'T07:00:00+08:00', **live_options)
        index(root, [training, live])
        return training, live

    def test_training_cannot_certify_historical_vintage_and_is_complete_past_only(self):
        with tempfile.TemporaryDirectory() as root:
            self.inputs(root)
            blocked = prepare_training_table(root, DAY)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertFalse(blocked['report']['historical_vintage_verified'])
            result = prepare_training_table(root, DAY, allow_research=True)
            self.assertEqual(result['status'], 'prepared')
            table = json.loads(Path(result['table_path']).read_bytes())
            self.assertEqual(table['readiness'], 'research_assumption')
            self.assertFalse(table['audit']['production_eligible'])
            self.assertEqual(len(table['rows']), 150)
            self.assertTrue(all(r['target_date'] < DAY and r['y'] in (0, 1) for r in table['rows']))
            self.assertEqual(Path(result['table_path']).stat().st_mode & 0o077, 0)
            repeated = prepare_training_table(root, DAY, allow_research=True)
            self.assertEqual(result['table_path'], repeated['table_path'])

    def test_latest_eligible_revision_and_late_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            training, live = self.inputs(root)
            eligible = acquire(root, 'live', DAY + 'T08:10:00+08:00', prior_close=12)
            late = acquire(root, 'live', DAY + 'T08:10:01+08:00', prior_close=20)
            index(root, [training, late])
            result = prepare_prediction_table(root, DAY)
            self.assertEqual(result['status'], 'prepared')
            table = json.loads(Path(result['table_path']).read_bytes())
            self.assertAlmostEqual(table['rows'][0]['stock_prev_intraday_return'], 0.2)
            actual = {r['source']: r for r in table['feature_evidence']}
            self.assertEqual(actual['course-live']['payload_sha256'], eligible['sha256'])
            self.assertNotEqual(actual['course-live']['payload_sha256'], live['sha256'])
            self.assertEqual(actual['course-live']['available_at'], actual['course-live']['fetched_at'])
            self.assertEqual(actual['course-live']['availability_basis']['kind'], 'observed_fetch')
            research = prepare_training_table(root, DAY, allow_research=True)
            train = json.loads(Path(research['table_path']).read_bytes())
            source = next(p for p in train['provenance'] if p['kind'] == 'live')
            self.assertEqual(source['sha256'], live['sha256'])

    def test_current_outcomes_never_enter_features_and_pending_previous_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            training, _ = self.inputs(root, pending=True)
            first = prepare_prediction_table(root, DAY)
            table = json.loads(Path(first['table_path']).read_bytes())
            self.assertEqual(len(table['rows']), 50)
            self.assertEqual(table['rows'][0]['stock_id'], '0001')
            self.assertIsNone(table['rows'][0]['stock_prev_intraday_return'])
            self.assertIsNone(table['rows'][0]['stock_return_between_observed_rows'])
            self.assertEqual(table['rows'][0]['stock_previous_observation_gap_days'], 3)
            self.assertFalse(set(table['rows'][0]) & {'y', 'adj_open', 'adj_close', 'target_intraday_return'})
            changed = acquire(root, 'live', DAY + 'T07:30:00+08:00', pending=True, current_close=1)
            index(root, [training, changed])
            second = prepare_prediction_table(root, DAY)
            after = json.loads(Path(second['table_path']).read_bytes())
            self.assertEqual(table['rows'], after['rows'])

    def test_corrupt_or_public_source_bytes_and_symlink_are_blocked(self):
        for mutation in ('payload', 'manifest_source', 'manifest_shape', 'public', 'symlink'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                _, live = self.inputs(root)
                payload_path = Path(live['payload_path'])
                if mutation == 'payload':
                    payload_path.write_bytes(b'corrupt')
                elif mutation == 'manifest_source':
                    path = Path(live['manifest_path'])
                    record = json.loads(path.read_bytes())
                    record['source_url'] = 'https://wrong.invalid/data.zip'
                    path.write_text(json.dumps(record))
                elif mutation == 'manifest_shape':
                    Path(live['manifest_path']).write_text('[]')
                elif mutation == 'public':
                    payload_path.chmod(0o644)
                else:
                    moved = payload_path.with_suffix('.saved')
                    payload_path.rename(moved)
                    payload_path.symlink_to(moved)
                result = prepare_prediction_table(root, DAY)
                self.assertEqual(result['status'], 'blocked')
                self.assertIsNone(result['table_path'])

    def test_missing_eligible_snapshot_and_timezone_ambiguity_block(self):
        with tempfile.TemporaryDirectory() as root:
            training = acquire(root, 'training', DAY + 'T06:00:00+08:00')
            late = acquire(root, 'live', DAY + 'T08:10:01+08:00')
            index(root, [training, late])
            self.assertEqual(prepare_prediction_table(root, DAY)['status'], 'blocked')
            path = Path(late['manifest_path'])
            record = json.loads(path.read_bytes())
            record['fetched_at'] = DAY + 'T07:00:00'
            path.write_text(json.dumps(record))
            self.assertEqual(prepare_prediction_table(root, DAY)['status'], 'blocked')

    def test_prediction_requires_live_fetch_on_target_day_not_stale_weekend_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            training = acquire(root, 'training', '2026-10-30T20:00:00+08:00')
            stale = acquire(root, 'live', '2026-10-30T23:47:00+08:00')
            index(root, [training, stale])
            blocked = prepare_prediction_table(root, DAY)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertIn('target-day', blocked['report']['reason'])
            fresh = acquire(root, 'live', '2026-11-01T20:00:00+00:00')
            index(root, [training, fresh])
            result = prepare_prediction_table(root, DAY)
            self.assertEqual(result['status'], 'prepared')
            self.assertEqual(set(result['report']['latest_observation_dates'].values()), {'2026-10-30'})
            self.assertFalse(result['report']['historical_vintage_verified'])

    def test_previous_day_and_just_before_collection_window_block(self):
        for fetched in ('2026-11-01T23:59:59+08:00', '2026-11-02T03:59:59+08:00'):
            with self.subTest(fetched=fetched), tempfile.TemporaryDirectory() as root:
                training = acquire(root, 'training', DAY + 'T03:00:00+08:00')
                live = acquire(root, 'live', fetched)
                index(root, [training, live])
                self.assertEqual(prepare_prediction_table(root, DAY)['status'], 'blocked')

    def test_late_fetch_does_not_make_old_live_fresh(self):
        with tempfile.TemporaryDirectory() as root:
            training = acquire(root, 'training', DAY + 'T03:00:00+08:00')
            acquire(root, 'live', '2026-10-30T23:00:00+08:00')
            late = acquire(root, 'live', DAY + 'T08:10:01+08:00')
            index(root, [training, late])
            self.assertEqual(prepare_prediction_table(root, DAY)['status'], 'blocked')

    def test_training_inclusive_cutoff_and_same_time_conflicting_revisions(self):
        with tempfile.TemporaryDirectory() as root:
            training = acquire(root, 'training', DAY + 'T06:00:00+08:00')
            eligible = acquire(root, 'live', DAY + 'T07:20:00+08:00', prior_close=12)
            late = acquire(root, 'live', DAY + 'T07:20:01+08:00', prior_close=20)
            index(root, [training, late])
            result = prepare_training_table(root, DAY, allow_research=True)
            self.assertEqual(result['status'], 'prepared')
            table = json.loads(Path(result['table_path']).read_bytes())
            live = next(p for p in table['provenance'] if p['kind'] == 'live')
            self.assertEqual(live['sha256'], eligible['sha256'])
            conflict = acquire(root, 'live', DAY + 'T07:20:00+08:00', prior_close=13)
            index(root, [training, conflict])
            # Late acquisition stays ineligible, and two equally latest but
            # conflicting eligible values cannot be ordered by UUID filename.
            self.assertEqual(prepare_training_table(root, DAY, allow_research=True)['status'], 'blocked')

    def test_shared_transform_matches_research_feature_rows(self):
        from finpred.data.training_table import build_research_table
        from finpred.features.stock import stock_lags
        history = [row('2026-10-28'), row('2026-10-29'), row('2026-10-30')]
        research = build_research_table({'0001': history}, provenance=[])
        expected = {name: research['rows'][-1][name] for name in STOCK_FEATURES}
        self.assertEqual(stock_lags(history[:-1], '2026-10-30'), expected)

    def test_shared_prediction_transform_is_ordered_and_ignores_current_outcomes(self):
        prior = [row('2026-10-29'), row('2026-10-30', pending=True)]
        stocks = {sid: prior + [row(DAY, close=99)] for sid in reversed(IDS[:50])}
        first, latest = prediction_rows_from_history(stocks, DAY)
        changed = {sid: prior + [row(DAY, close=1)] for sid in IDS[:50]}
        second, _ = prediction_rows_from_history(changed, DAY)
        self.assertEqual(first, second)
        self.assertEqual([r['stock_id'] for r in first], IDS[:50])
        self.assertEqual(set(latest.values()), {'2026-10-30'})
        self.assertIsNone(first[0]['stock_prev_intraday_return'])
        self.assertEqual(first[0]['stock_previous_observation_gap_days'], 3)
        self.assertEqual(set(first[0]), {'stock_id', 'target_date', 'feature_cutoff', *STOCK_FEATURES})


if __name__ == '__main__':
    unittest.main()
