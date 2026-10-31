"""Counterexamples for the actual portable daily research feature handoff."""

import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

from finpred.data.course_schema import GLOBAL_COLUMNS, STOCK_COLUMNS
from finpred.data.shared_features import build_shared_features, validate_shared_feature_exports
from finpred.data.sharing import export_snapshot_bundle, import_snapshot_bundle
from finpred.data.snapshots import snapshot_bytes
import zipfile


def _csv(fields, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _archive(*, live=False, final_close='9', final_y='0', pending=False):
    ids = [str(1000 + i) for i in range(100)]
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for sid in ids:
            rows = []
            for day, opening, closing, y in ([('2025-01-06', '10', final_close, final_y)] if live else
                                           [('2025-01-02', '10', '11', '1'), ('2025-01-03', '11', '12', '1')]):
                row = dict.fromkeys(STOCK_COLUMNS, '1')
                row.update({'date': day, 'etl:adj_open': opening, 'etl:adj_close': closing,
                            'y': '-1' if pending else y, 'ATR': '1', 'SMA': '10', 'RSI': '55',
                            'price:成交股數': '100'})
                rows.append(row)
            archive.writestr('data/market/' + sid + '.csv', _csv(STOCK_COLUMNS, rows))
        global_row = dict.fromkeys(GLOBAL_COLUMNS, '1')
        global_row['date'] = '2025-01-06' if live else '2025-01-03'
        archive.writestr('data/global/global_data.csv', _csv(GLOBAL_COLUMNS, [global_row]))
        if not live:
            archive.writestr('data/info.json', json.dumps({'Top50@Y': ids[:50], 'Top100@Y': ids}))
    return output.getvalue()


def _seed(root, *, live=True, **updates):
    training = snapshot_bytes(_archive(), root / 'raw', 'course-training',
                              'https://example.invalid/training.zip', '.zip', {'tls_verification': True})
    if live:
        snapshot_bytes(_archive(live=True, **updates), root / 'raw', 'course-live',
                       'https://example.invalid/live.zip', '.zip', {'tls_verification': True})
    return training


def _read(root, relative):
    payload = (root / relative).read_bytes()
    if relative.endswith('.gz'):
        payload = gzip.decompress(payload)
    return list(csv.DictReader(io.StringIO(payload.decode())))


class SharedFeatureTests(unittest.TestCase):
    def test_real_archive_export_has_complete_50_stock_slots_and_known_return(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'runtime')
            result = build_shared_features(root / 'runtime', root / 'bundle')
            self.assertEqual(result['stock_feature_rows'], 150)
            self.assertEqual(result['stock_count'], 50)
            rows = _read(root / 'bundle', 'features/stock_lags.csv.gz')
            last = next(r for r in rows if r['stock_id'] == '1000' and r['target_date'] == '2025-01-06')
            self.assertAlmostEqual(float(last['stock_prev_intraday_return']), 12 / 11 - 1)
            self.assertAlmostEqual(float(last['stock_return_between_observed_rows']), 12 / 11 - 1)
            self.assertEqual(last['stock_previous_observation_gap_days'], '3')
            self.assertNotIn('y', last)
            self.assertNotIn('target_intraday_return', last)
            self.assertFalse(result['production_eligible'])
            self.assertEqual(result['market_readiness'], 'blocked')

    def test_today_outcome_does_not_change_today_features(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'before')
            _seed(root / 'after', final_close='1000', final_y='1')
            build_shared_features(root / 'before', root / 'bundle-before')
            build_shared_features(root / 'after', root / 'bundle-after')
            self.assertEqual((root / 'bundle-before/features/stock_lags.csv.gz').read_bytes(),
                             (root / 'bundle-after/features/stock_lags.csv.gz').read_bytes())
            self.assertNotEqual((root / 'bundle-before/labels/stock_outcomes.csv.gz').read_bytes(),
                                (root / 'bundle-after/labels/stock_outcomes.csv.gz').read_bytes())

    def test_pending_labels_stay_separate_and_slots_remain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'runtime', pending=True)
            result = build_shared_features(root / 'runtime', root / 'bundle')
            self.assertEqual(result['pending_label_rows'], 50)
            labels = _read(root / 'bundle', 'labels/stock_outcomes.csv.gz')
            pending = [r for r in labels if r['status'] == 'pending']
            self.assertEqual(len(pending), 50)
            self.assertTrue(all(r['y'] == '' and r['target_intraday_return'] == '' for r in pending))
            self.assertEqual(len(_read(root / 'bundle', 'features/stock_lags.csv.gz')), 150)

    def test_repeated_export_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'runtime')
            first = build_shared_features(root / 'runtime', root / 'bundle')
            before = {p.relative_to(root / 'bundle'): p.read_bytes() for p in (root / 'bundle').rglob('*') if p.is_file()}
            second = build_shared_features(root / 'runtime', root / 'bundle')
            after = {p.relative_to(root / 'bundle'): p.read_bytes() for p in (root / 'bundle').rglob('*') if p.is_file()}
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertEqual((root / 'bundle/features/stock_lags.csv.gz').read_bytes()[4:8], b'\x00' * 4)
            self.assertEqual(validate_shared_feature_exports(root / 'bundle')['stock_count'], 50)

    def test_portable_import_preserves_original_source_acquisition_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = _seed(root / 'producer')
            export_snapshot_bundle(root / 'producer', root / 'portable')
            import_snapshot_bundle(root / 'portable', root / 'consumer', revision='a' * 40)
            build_shared_features(root / 'consumer', root / 'portable')
            lineage = json.loads((root / 'portable/features/lineage.json').read_text())
            source = next(s for s in lineage['sources'] if s['source'] == 'course-training')
            self.assertEqual(source['source_fetched_at'], original['fetched_at'])
            self.assertEqual(source['payload_sha256'], original['sha256'])
            self.assertIsNotNone(lineage['raw_catalog_sha256'])

    def test_corrupt_source_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = _seed(root / 'runtime')
            Path(manifest['payload_path']).write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'hash or size'):
                build_shared_features(root / 'runtime', root / 'bundle')
            self.assertFalse((root / 'bundle/features/stock_lags.csv.gz').exists())

    def test_failed_refresh_retains_old_bytes_but_consumers_reject_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = _seed(root / 'runtime')
            build_shared_features(root / 'runtime', root / 'bundle')
            old_csv = (root / 'bundle/features/stock_lags.csv.gz').read_bytes()
            Path(manifest['payload_path']).write_bytes(b'corrupt new source')
            with self.assertRaises(ValueError):
                build_shared_features(root / 'runtime', root / 'bundle')
            self.assertEqual((root / 'bundle/features/stock_lags.csv.gz').read_bytes(), old_csv)
            self.assertEqual(json.loads((root / 'bundle/features/build_status.json').read_text())['status'], 'failed')
            with self.assertRaisesRegex(ValueError, 'failed, blocked'):
                validate_shared_feature_exports(root / 'bundle')

    def test_consumer_rejects_new_catalog_or_modified_feature_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'runtime')
            build_shared_features(root / 'runtime', root / 'bundle')
            (root / 'bundle/catalog').mkdir()
            (root / 'bundle/catalog/latest.json').write_text(json.dumps({'catalog_sha256': 'a' * 64}))
            with self.assertRaisesRegex(ValueError, 'different raw catalog'):
                validate_shared_feature_exports(root / 'bundle')
            (root / 'bundle/catalog/latest.json').unlink()
            (root / 'bundle/features/stock_lags.csv.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'hash or size'):
                validate_shared_feature_exports(root / 'bundle')

    def test_missing_training_invalidates_old_managed_tables(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'runtime/raw').mkdir(parents=True)
            (root / 'bundle/features').mkdir(parents=True)
            (root / 'bundle/features/stock_lags.csv.gz').write_bytes(b'stale')
            result = build_shared_features(root / 'runtime', root / 'bundle')
            self.assertEqual(result['status'], 'blocked')
            self.assertFalse((root / 'bundle/features/stock_lags.csv.gz').exists())
            self.assertEqual(json.loads((root / 'bundle/features/lineage.json').read_text())['files'], {})

    def test_research_opt_in_and_symlink_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _seed(root / 'runtime')
            result = build_shared_features(root / 'runtime', root / 'bundle', allow_research=False)
            self.assertEqual(result['status'], 'blocked')
            (root / 'linked').symlink_to(root / 'bundle', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                build_shared_features(root / 'runtime', root / 'linked')


if __name__ == '__main__':
    unittest.main()
