"""Offline Phase 1 contracts, including official-size synthetic matrices."""

from datetime import date, timedelta
import hashlib
import io
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from finpred.submission import phase1

PROJECT = Path(__file__).resolve().parents[1]
SMALL = {'expected_stock_count': 2, 'expected_date_count': 2}


def fixture(*, official_size=False):
    if official_size:
        ids = [f'{i:04}' for i in range(50)]
        # A synthetic shape, deliberately not a claim about exchange holidays.
        days = [(date(2026, 6, 1) + timedelta(days=i)).isoformat() for i in range(83)] + ['2026-09-30']
    else:
        ids, days = ['2330', '0050'], ['2026-06-01', '2026-06-02']
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['id', *days])
    for stock in ids:
        writer.writerow([stock, *([0] * len(days))])
    template = stream.getvalue().encode('utf-8-sig')
    predictions = [{'stock_id': stock, 'target_date': day, 'prediction': (i + j) % 2}
                   for i, stock in enumerate(ids) for j, day in enumerate(days)]
    return template, predictions


class Phase1Tests(unittest.TestCase):
    def test_exact_template_order_and_leading_zero_ids_with_shuffled_rows(self):
        template, rows = fixture()
        with patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')), patch(
            'joblib.load', side_effect=AssertionError('model loading forbidden')
        ):
            payload = phase1.build_phase1_csv(list(reversed(rows)), template, **SMALL)
        self.assertTrue(payload.startswith(b'\xef\xbb\xbf'))
        matrix = list(csv.reader(io.StringIO(payload.decode('utf-8-sig'))))
        self.assertEqual(matrix, [['id', '2026-06-01', '2026-06-02'], ['2330', '0', '1'], ['0050', '1', '0']])
        result = phase1.validate_phase1_csv(payload, template, **SMALL)
        self.assertEqual(result['prediction_count'], 4)
        self.assertFalse(result['production_eligible'])
        self.assertFalse(result['submitted'])

    def test_missing_extra_duplicate_and_wrong_identity_keys_are_rejected(self):
        template, rows = fixture()
        cases = [rows[:-1], rows + [dict(rows[0])],
                 [dict(rows[0], stock_id='50'), *rows[1:]],
                 [dict(rows[0], stock_id=2330), *rows[1:]],
                 [dict(rows[0], target_date='2026-06-03'), *rows[1:]],
                 [dict(rows[0], target_date='20260601'), *rows[1:]]]
        for values in cases:
            with self.subTest(values=values[0]), self.assertRaises(phase1.Phase1Error):
                phase1.build_phase1_csv(values, template, **SMALL)

    def test_only_integer_binary_predictions_no_probabilities_or_labels(self):
        template, rows = fixture()
        for value in (True, False, 0.0, 1.0, 0.25, '0', '1', None, -1, 2, float('nan')):
            with self.subTest(value=value), self.assertRaises(phase1.Phase1Error):
                phase1.build_phase1_csv([dict(rows[0], prediction=value), *rows[1:]], template, **SMALL)
        for field in ('y', 'adj_open', 'adj_close', 'target_intraday_return', 'label'):
            with self.subTest(field=field), self.assertRaises(phase1.Phase1Error):
                phase1.build_phase1_csv([dict(rows[0], **{field: 1}), *rows[1:]], template, **SMALL)
        for wrapper in ({'rows': rows, 'labels': []}, {'rows': rows, 'predictions': rows},
                        {'predictions': rows, 'model': {'code_sha256': {'y': 'forbidden'}}},
                        {'predictions': rows, 'model': {'feature_columns': ['y']}},
                        {'rows': rows, 'readiness': 'verified'}):
            with self.subTest(wrapper=list(wrapper)), self.assertRaises(phase1.Phase1Error):
                phase1.build_phase1_csv(wrapper, template, **SMALL)

    def test_existing_inference_wrapper_supported_without_copying_model_metadata(self):
        template, rows = fixture()
        model = {'schema_version': 'model-bundle-v1', 'family': 'linear', 'readiness': 'research_assumption',
                 'feature_columns': ['stock_prev_intraday_return'], 'training_table_sha256': 'a' * 64}
        wrapped = {'predictions': rows, 'model': model}
        self.assertEqual(phase1.build_phase1_csv(wrapped, template, **SMALL),
                         phase1.build_phase1_csv(rows, template, **SMALL))

    def test_json_duplicate_keys_nonfinite_and_bad_bytes_are_rejected(self):
        for payload in (b'{"rows":[],"rows":[]}', b'{"rows":[{"prediction":0,"prediction":1}]}',
                        b'[NaN]', b'[Infinity]', b'[-Infinity]', b'not json', b'\xff'):
            with self.subTest(payload=payload), self.assertRaises(phase1.Phase1Error):
                phase1.parse_prediction_json(payload)

    def test_template_dimensions_period_and_candidate_order_are_not_accepted_by_shape_alone(self):
        template, rows = fixture()
        payload = phase1.build_phase1_csv(rows, template, **SMALL)
        for changed in (template.replace(b'2026-06-01', b'2026-01-01'),
                        template.replace(b',2026-06-02', b''),
                        template.replace(b'2330,0,0\n0050,0,0', b'2330,0,0\n2330,0,0')):
            with self.subTest(changed=changed), self.assertRaises(phase1.Phase1Error):
                phase1.template_contract(changed, **SMALL)
        with self.assertRaises(phase1.Phase1Error):
            phase1.template_contract(template)  # CLI-size defaults cannot accept a small test matrix.
        swapped = payload.replace(b'2330,0,1\n0050,1,0', b'0050,1,0\n2330,0,1')
        with self.assertRaisesRegex(phase1.Phase1Error, 'order'):
            phase1.validate_phase1_csv(swapped, template, **SMALL)
        with self.assertRaises(phase1.Phase1Error):
            phase1.validate_phase1_csv(payload.replace(b'2026-06-02', b'2026-06-03'), template, **SMALL)

    def test_immutable_artifacts_preserve_original_input_hash_and_research_scope(self):
        template, rows = fixture()
        raw = json.dumps({'predictions': list(reversed(rows)), 'model': {'family': 'linear'}}, indent=4).encode()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'artifact'
            result = phase1.write_phase1_predictions(template, raw, target, **SMALL)
            manifest = json.loads((target / 'manifest.json').read_bytes())
            self.assertEqual(manifest['prediction_json_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(manifest['template_sha256'], hashlib.sha256(template).hexdigest())
            self.assertEqual(manifest['csv_sha256'], hashlib.sha256((target / 'predictions.csv').read_bytes()).hexdigest())
            self.assertFalse(manifest['production_eligible'])
            self.assertFalse(manifest['historical_availability_verified'])
            self.assertFalse(manifest['model_validated'])
            self.assertNotIn('model', manifest)
            self.assertEqual(result['status'], 'research_csv_written')
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            with self.assertRaises(FileExistsError):
                phase1.write_phase1_predictions(template, raw, target, **SMALL)
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})
            for path in target.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_write_cannot_leave_a_completed_manifest_or_overwrite_inputs(self):
        template, rows = fixture()
        raw = json.dumps(rows).encode()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'partial'
            original = phase1._exclusive_write

            def fail_manifest(path, value):
                if path.name == 'manifest.json':
                    raise OSError('synthetic interrupted manifest')
                original(path, value)

            with patch.object(phase1, '_exclusive_write', side_effect=fail_manifest):
                with self.assertRaises(OSError):
                    phase1.write_phase1_predictions(template, raw, target, **SMALL)
            self.assertFalse((target / 'manifest.json').exists())
            source = Path(directory) / 'source.json'
            source.write_bytes(raw)
            with self.assertRaises(FileExistsError):
                phase1.write_phase1_predictions(template, raw, source, **SMALL)
            self.assertEqual(source.read_bytes(), raw)
            link = Path(directory) / 'alias'
            link.symlink_to(source)
            with self.assertRaises(phase1.Phase1Error):
                phase1.read_input_bytes(link)
            fifo = Path(directory) / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(phase1.Phase1Error):
                phase1.read_input_bytes(fifo)

    def test_official_size_cli_build_and_validate_only_never_mutate_inputs(self):
        template, rows = fixture(official_size=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template_file, rows_file = root / 'template.csv', root / 'rows.json'
            template_file.write_bytes(template)
            raw = json.dumps({'predictions': rows, 'model': {'family': 'linear'}}).encode()
            rows_file.write_bytes(raw)
            target = root / 'artifact'
            command = [sys.executable, str(PROJECT / 'scripts/build_phase1_predictions.py'),
                       '--template', str(template_file)]
            result = subprocess.run([*command, '--predictions', str(rows_file), '--out-dir', str(target)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['prediction_count'], 4200)
            self.assertEqual(len((target / 'predictions.csv').read_text(encoding='utf-8-sig').splitlines()), 51)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            validated = subprocess.run([*command, '--validate-csv', str(target / 'predictions.csv')],
                                       capture_output=True, text=True, timeout=15)
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            self.assertEqual(json.loads(validated.stdout)['status'], 'format_validated')
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
