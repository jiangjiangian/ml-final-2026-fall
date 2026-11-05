"""The teammate bridge must retain source evidence and exclude later labels."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finpred.data.snapshots import snapshot_bytes
from test_shared_features import _archive

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare_team_data.py'
SPEC = importlib.util.spec_from_file_location('team_data_tests', SCRIPT)
team = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(team)


class PrepareTeamDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'runtime'
        self.output = self.root / 'output'

    def seed(self, **changes):
        result = []
        for source, payload in [('course-training', _archive()),
                                ('course-live', _archive(live=True, **changes))]:
            result.append(snapshot_bytes(payload, self.runtime / 'raw', source, team.SOURCES[source],
                                         '.zip', {'tls_verified': True}))
        return result

    def prepare(self, *, output=None, before='2025-01-07', **kwargs):
        return team.prepare_team_data(self.runtime, output or self.output,
                                      train_before=before, allow_research=True, **kwargs)

    def read(self, name, output=None):
        return json.loads(((output or self.output) / name).read_bytes())

    def test_hash_verified_prefix_is_trainable_and_features_contain_no_outcomes(self):
        original = self.seed()
        result = self.prepare()
        self.assertEqual(150, result['training_rows'])
        self.assertEqual(150, result['feature_rows'])
        self.assertEqual(50, result['stock_count'])
        table = self.read('training-table.json')
        self.assertEqual('research_assumption', table['readiness'])
        self.assertEqual(50, len({r['stock_id'] for r in table['rows']}))
        self.assertTrue(all(r['target_date'] < '2025-01-07' for r in table['rows']))
        features = self.read('features.json')
        self.assertTrue(all(set(r) == {'stock_id', 'target_date', 'feature_cutoff', *team.STOCK_FEATURES}
                            for r in features['rows']))
        last = next(r for r in features['rows'] if r['stock_id'] == '1000' and r['target_date'] == '2025-01-06')
        self.assertEqual(3, last['stock_previous_observation_gap_days'])
        self.assertAlmostEqual(12 / 11 - 1, last['stock_return_between_observed_rows'])
        lineage = self.read('lineage.json')
        self.assertFalse(lineage['production_eligible'])
        self.assertFalse(lineage['historical_vintage_verified'])
        self.assertEqual(0, lineage['model_fit_count'])
        for source in lineage['sources']:
            before = next(r for r in original if r['source'] == source['source'])
            self.assertEqual(before['fetched_at'], source['source_fetched_at'])
            self.assertEqual(before['sha256'], source['payload_sha256'])
        for name, expected in lineage['files'].items():
            self.assertEqual(expected['sha256'], hashlib.sha256((self.output / name).read_bytes()).hexdigest())
        self.assertEqual(0o700, self.output.stat().st_mode & 0o777)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.output.iterdir()))

    def test_cutoff_is_applied_before_any_label_construction(self):
        self.seed()
        original_builder = team.build_research_table
        with patch.object(team, 'build_research_table', wraps=original_builder) as build:
            result = self.prepare(before='2025-01-06')
        self.assertEqual(100, result['training_rows'])
        supplied = build.call_args.args[0]
        self.assertTrue(all(r['date'] < '2025-01-06' for rows in supplied.values() for r in rows))
        # The future complete Live target cannot leak via labels or features.
        self.assertEqual({'2025-01-02', '2025-01-03'}, {r['target_date'] for r in self.read('features.json')['rows']})

    def test_pending_predecessor_is_retained_as_missing(self):
        self.seed(pending=True)
        stocks = {str(1000 + i): [
            {'date': '2025-01-02', 'etl:adj_open': '10', 'etl:adj_close': '11', 'y': '1'},
            {'date': '2025-01-03', 'etl:adj_open': '-1', 'etl:adj_close': '-1', 'y': '-1'},
            {'date': '2025-01-06', 'etl:adj_open': '10', 'etl:adj_close': '11', 'y': '1'},
        ] for i in range(50)}
        with patch.object(team, 'read_course_archives', return_value=(stocks, [])):
            result = self.prepare()
        self.assertEqual(100, result['training_rows'])
        self.assertEqual(150, result['feature_rows'])
        last = self.read('features.json')['rows'][-1]
        self.assertIsNone(last['stock_prev_intraday_return'])
        self.assertIsNone(last['stock_return_between_observed_rows'])
        self.assertEqual(3, last['stock_previous_observation_gap_days'])

    def test_wrong_hash_or_unverified_tls_or_source_is_rejected(self):
        manifests = self.seed()
        live = manifests[-1]
        path = Path(live['manifest_path'])
        original = path.read_bytes()
        for key, value in [('source_url', 'https://wrong.invalid/data.zip'),
                           ('metadata', {'tls_verified': False})]:
            record = json.loads(original)
            record[key] = value
            path.write_text(json.dumps(record))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare()
            self.assertFalse(self.output.exists())
        path.write_bytes(original)
        Path(live['payload_path']).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_opt_in_missing_sources_and_future_cutoff_are_rejected(self):
        with self.assertRaises(ValueError):
            team.prepare_team_data(self.runtime, self.output)
        self.runtime.mkdir()
        with self.assertRaises(ValueError):
            self.prepare()
        self.seed()
        with self.assertRaises(ValueError):
            self.prepare(before='2099-01-01')
        with self.assertRaises(ValueError):
            self.prepare(before='20250107')
        self.assertFalse(self.output.exists())

    def test_existing_output_git_and_symlink_paths_are_rejected(self):
        self.seed()
        self.prepare()
        original = (self.output / 'lineage.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(original, (self.output / 'lineage.json').read_bytes())
        checkout = self.root / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        with self.assertRaises(ValueError):
            self.prepare(output=checkout / 'out')
        alias = self.root / 'alias'
        alias.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(ValueError):
            team.prepare_team_data(alias, self.root / 'new', allow_research=True)

    def test_default_cutoff_uses_taipei_today_and_cli_omits_source_contents(self):
        records = self.seed()
        for record in records:
            record['fetched_at'] = '2025-01-06T00:00:00+00:00'
            Path(record['manifest_path']).write_text(json.dumps(record))

        def clock():
            return datetime(2025, 1, 6, 17, tzinfo=timezone.utc)

        result = self.prepare(before=None, clock=clock)
        self.assertEqual('2025-01-07', result['training_target_exclusive_upper_bound'])
        arguments = ['prepare_team_data.py', '--runtime-dir', str(self.runtime),
                     '--out-dir', str(self.root / 'cli-output'), '--allow-research']
        buffer = io.StringIO()
        with patch.object(team.sys, 'argv', arguments), redirect_stdout(buffer):
            self.assertEqual(0, team.main())
        result = json.loads(buffer.getvalue())
        self.assertEqual(datetime.now(team.TAIPEI).date().isoformat(), result['training_target_exclusive_upper_bound'])
        self.assertNotIn('https://', buffer.getvalue())
        self.assertNotIn('payload_path', buffer.getvalue())


if __name__ == '__main__':
    unittest.main()
