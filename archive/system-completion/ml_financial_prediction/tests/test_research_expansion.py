"""Financial units, native gaps and cutoff counterexamples for frozen R1 groups."""

from datetime import date, timedelta
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finpred.features.research_expansion import (
    MARKET_SERIES, build_research_expansion, fred_feature_rows, frozen_schema,
    native_feature_rows,
)
from finpred.features.stock import STOCK_FEATURES


def fixture(series='ixic', count=24):
    days = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(count)]
    cal = {'session_dates': days, 'calendar_evidence': 'SYNTHETIC native calendar'}
    observations = [{'series_id': series, 'session_date': day, 'value': 100.0 + i,
                     'event_time': day + 'T21:00:00Z', 'available_at': day + 'T23:00:00Z',
                     'revision_id': 'a', 'payload_sha256': 'a' * 64} for i, day in enumerate(days)]
    return observations, {series: cal}


def target(day='2020-01-25'):
    return {'target_date': day, 'feature_cutoff': day + 'T08:10:00+08:00'}


class ResearchExpansionTests(unittest.TestCase):
    def test_windows_use_native_sessions_not_target_rows(self):
        observations, calendars = fixture()
        rows = native_feature_rows(observations, calendars, [target('2020-01-24'), target()])
        self.assertAlmostEqual(rows[-1]['ixic_ret_20s'], 123 / 103 - 1)
        self.assertAlmostEqual(rows[-1]['ixic_ret_5s'], 123 / 118 - 1)
        self.assertEqual(rows[-1]['ixic_source_session_date'], '2020-01-24')

    def test_gap_in_intervening_native_session_blocks_full_window(self):
        observations, calendars = fixture()
        observations = [r for r in observations if r['session_date'] != '2020-01-21']
        row = native_feature_rows(observations, calendars, [target()])[0]
        self.assertIsNone(row['ixic_ret_5s'])
        self.assertIsNone(row['ixic_vol_20s'])
        self.assertIsNotNone(row['ixic_ret_1s'])

    def test_missing_native_predecessor_does_not_skip_to_previous_observed(self):
        observations, calendars = fixture()
        observations = [r for r in observations if r['session_date'] != '2020-01-23']
        row = native_feature_rows(observations, calendars, [target()])[0]
        self.assertIsNone(row['ixic_ret_1s'])
        self.assertEqual(row['ixic_is_missing'], 1)

    def test_future_same_day_close_cannot_enter_morning_feature(self):
        observations, calendars = fixture(count=25)
        observations[-1]['value'] = 999999
        row = native_feature_rows(observations, calendars, [target()])[0]
        self.assertAlmostEqual(row['ixic_ret_1s'], 123 / 122 - 1)

    def test_late_revision_changes_only_later_cutoff_and_not_latest_session(self):
        observations, calendars = fixture()
        revision = dict(observations[-2], value=61.0, revision_id='b',
                        available_at='2020-01-25T12:00:00Z')
        early = native_feature_rows(observations + [revision], calendars, [target()])[0]
        later = native_feature_rows(observations + [revision], calendars, [target('2020-01-26')])[0]
        self.assertAlmostEqual(early['ixic_ret_1s'], 123 / 122 - 1)
        self.assertAlmostEqual(later['ixic_ret_1s'], 123 / 61 - 1)
        self.assertEqual(later['ixic_source_session_date'], '2020-01-24')

    def test_zero_denominator_is_missing_not_infinite(self):
        observations, calendars = fixture()
        observations[-2]['value'] = 0
        row = native_feature_rows(observations, calendars, [target()])[0]
        self.assertIsNone(row['ixic_ret_1s'])
        self.assertIsNone(row['ixic_vol_20s'])

    def test_vix_is_level_and_points_not_asset_return(self):
        observations, calendars = fixture('vix')
        row = native_feature_rows(observations, calendars, [target()])[0]
        self.assertEqual(row['vix_level'], 123)
        self.assertEqual(row['vix_change_points'], 1)
        self.assertNotIn('vix_ret_1s', row)

    def test_age_and_freshness_keep_holiday_old_source(self):
        observations, calendars = fixture()
        rows = native_feature_rows(observations, calendars, [target(), target('2020-01-27')])
        self.assertEqual(rows[0]['ixic_age_hours'], 1 + 10 / 60)
        self.assertIsNone(rows[0]['ixic_is_new_session'])
        self.assertEqual(rows[1]['ixic_is_new_session'], 0)
        self.assertAlmostEqual(rows[1]['ixic_age_hours'] - rows[0]['ixic_age_hours'], 48)

    def test_cutoff_after_deadline_or_on_other_date_rejected(self):
        for cutoff in ('2020-01-25T09:01:00+08:00', '2020-01-24T08:10:00+08:00'):
            with self.assertRaises(ValueError):
                native_feature_rows([], {}, [{'target_date': '2020-01-25', 'feature_cutoff': cutoff}])

    def test_strict_blocks_and_research_opt_in_is_required(self):
        result = build_research_expansion({}, [])
        self.assertEqual(result['report']['readiness'], 'blocked')
        self.assertEqual(result['tables'], {})
        with self.assertRaises(ValueError):
            build_research_expansion({}, [], mode='research')

    def _fred_manifest(self, root, source, values):
        series = 'DGS10' if source == 'fred_us10y' else 'DEXTAUS'
        body = ('observation_date,' + series + '\n' + ''.join(f'{d},{v}\n' for d, v in values)).encode()
        payload = root / (source + '.csv')
        payload.write_bytes(body)
        manifest = root / (source + '.json')
        manifest.write_text(json.dumps({'source': source, 'payload_path': str(payload),
                                        'sha256': hashlib.sha256(body).hexdigest(),
                                        'fetched_at': '2026-10-30T00:00:00Z'}))
        return manifest

    def test_fred_yield_percent_to_signed_basis_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._fred_manifest(Path(temporary), 'fred_us10y', [('2020-01-01', '-0.1'), ('2020-01-02', '0.1')])
            rows, audit = fred_feature_rows([path], [target('2020-01-10')])
            self.assertAlmostEqual(rows[0]['us_10y_yield_change_bp_1obs'], 20)
            self.assertEqual(rows[0]['us_10y_yield_percent'], .1)
            self.assertFalse(audit['fred_us10y']['historical_vintage_verified'])

    def test_fred_holiday_null_not_skipped_and_quarantine_not_backdated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._fred_manifest(Path(temporary), 'fred_usd_twd',
                                       [('2020-01-01', '30'), ('2020-01-02', '.'), ('2020-01-03', '33')])
            rows, _ = fred_feature_rows([path], [target('2020-01-09'), target('2020-01-11')])
            self.assertEqual(rows[0]['usd_twd_source_observation_date'], '2020-01-01')
            self.assertIsNone(rows[1]['usd_twd_ret_1obs'])
            self.assertEqual(rows[1]['usd_twd_is_missing'], 1)

    def test_fred_fixed_quote_return_and_hash_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._fred_manifest(Path(temporary), 'fred_usd_twd', [('2020-01-01', '30'), ('2020-01-02', '33')])
            rows, _ = fred_feature_rows([path], [target('2020-01-10')])
            self.assertAlmostEqual(rows[0]['usd_twd_ret_1obs'], .1)
            data = json.loads(path.read_text())
            Path(data['payload_path']).write_text('corrupted')
            with self.assertRaises(ValueError):
                fred_feature_rows([path], [target('2020-01-10')])

    def test_target_universe_order_and_labels_preserved_sector_group_blocked(self):
        observations, calendars = [], {}
        for series in MARKET_SERIES:
            obs, cal = fixture(series)
            observations += obs
            calendars.update(cal)
        rows = [dict(target(), stock_id=sid, y=index, target_intraday_return=(-.01, .02)[index],
                     **dict.fromkeys(STOCK_FEATURES, .1)) for index, sid in enumerate(('B', 'A'))]
        baseline = {'schema_version': 'training-table-v1', 'feature_columns': list(STOCK_FEATURES),
                    'rows': rows, 'availability_evidence': 'SYNTHETIC research history', 'provenance': [], 'audit': {}}
        with patch('finpred.features.research_expansion.normalize_history_snapshots',
                   return_value={'observations': observations, 'native_sessions': calendars, 'report': {}}):
            result = build_research_expansion(baseline, [], mode='research', allow_research=True)
        for group, table in result['tables'].items():
            self.assertEqual([(r['stock_id'], r['target_date'], r['y'], r['target_intraday_return']) for r in table['rows']],
                             [(r['stock_id'], r['target_date'], r['y'], r['target_intraday_return']) for r in rows])
            self.assertNotIn('y', table['feature_columns'])
            self.assertNotIn('target_intraday_return', table['feature_columns'])
            self.assertNotIn('adj_close', table['feature_columns'])
            self.assertFalse(table['audit']['production_eligible'])
        self.assertEqual(result['tables']['F3']['readiness'], 'blocked')
        self.assertEqual(result['schema']['search_budget']['maximum_fits'], 32)

    def test_frozen_schema_is_deterministic_and_has_no_label_features(self):
        first, second = frozen_schema(), frozen_schema()
        self.assertEqual(first, second)
        self.assertEqual(len(first['group_extra_columns']['F1']), 21)
        self.assertEqual(first['model_columns']['F0'], list(STOCK_FEATURES))
        for columns in first['model_columns'].values():
            self.assertEqual(len(columns), len(set(columns)))
            self.assertNotIn('y', columns)

    def test_portable_ablation_cli_respects_blocked_slots_and_immutable_results(self):
        """Execute tiny synthetic folds; never count these fits as market evidence."""
        script = Path(__file__).resolve().parents[1] / 'scripts/run_feature_ablation.py'
        spec = importlib.util.spec_from_file_location('feature_ablation_test', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'inputs', Path(temporary) / 'results'
            source.mkdir()
            schema = frozen_schema()
            rows = []
            for day in ('2024-12-02', '2025-01-02', '2025-04-02', '2025-07-02', '2025-10-02'):
                for stock in range(50):
                    rows.append({'stock_id': str(1000 + stock), 'target_date': day,
                                 'feature_cutoff': day + 'T08:10:00+08:00',
                                 'label_available_at': day + 'T23:59:00+08:00',
                                 'adj_open': 100., 'adj_close': 101., 'y': 1,
                                 'target_intraday_return': .01,
                                 **dict.fromkeys(STOCK_FEATURES, .1)})
            table = {'schema_version': 'training-table-v1', 'readiness': 'research_assumption',
                     'availability_evidence': 'SYNTHETIC TEST; not observed financial evidence',
                     'feature_columns': list(STOCK_FEATURES), 'feature_version': 'synthetic-test-v1',
                     'rows': rows}
            hashes = {}
            for filename, value in [('frozen_schema.json', schema), ('F0.json', table)]:
                body = json.dumps(value).encode()
                (source / filename).write_bytes(body)
                hashes[filename] = hashlib.sha256(body).hexdigest()
            (source / 'expansion_report.json').write_text(json.dumps({
                'artifact_sha256': hashes, 'group_status': {
                    group: {'status': 'research_assumption' if group == 'F0' else 'blocked',
                            'reasons': [] if group == 'F0' else ['SYNTHETIC absent source']}
                    for group in ('F0', 'F1', 'F2', 'F3')}}))
            with redirect_stdout(io.StringIO()):
                report = module.run(source, output)
            self.assertEqual(report['R1_completed_fits'], 8)
            self.assertEqual(report['R1_blocked_fit_slots'], 24)
            self.assertEqual(report['E04_completed_fits'], 0)
            self.assertEqual(report['E04_status'], 'not_requested')
            registration = json.loads((output / 'registration.json').read_text())
            self.assertFalse(registration['E04']['requested'])
            self.assertEqual(len(registration['R1']['blocked_slots']), 24)
            original = (output / 'report.json').read_bytes()
            with self.assertRaises(ValueError):
                module.run(source, output)
            self.assertEqual((output / 'report.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
