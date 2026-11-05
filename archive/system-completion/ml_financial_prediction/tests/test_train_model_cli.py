"""Single-fit research entrypoint preserves chronology, provenance and isolation."""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from finpred.inference.predict import predict_rows
from finpred.training.fit import load_model_bundle
from test_training import table

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / 'scripts/train_model.py'
SPEC = importlib.util.spec_from_file_location('single_fit_cli_subject', SCRIPT)
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
FIXED = datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc)


class SingleFitCliTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.umask, os.umask(0o022))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'table.json'
        self.out = self.root / 'new-parent/models/single-fit'
        self.write_table(table(readiness='research_assumption'))

    def write_table(self, value):
        payload = (json.dumps(value, indent=2) + '\n').encode()
        self.source.write_bytes(payload)
        self.source.chmod(0o600)
        return payload

    def cli(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), '--table', str(self.source),
                               '--out-dir', str(self.out), *arguments], cwd=PROJECT,
                              capture_output=True, text=True, timeout=30)

    def test_real_cli_creates_one_loadable_research_bundle_with_actual_cutoff(self):
        before = datetime.now(timezone.utc)
        result = self.cli('--allow-research')
        after = datetime.now(timezone.utc)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['status'], 'research_model_fitted')
        self.assertEqual(summary['family'], 'linear')
        self.assertEqual(summary['objective'], 'weighted_classification')
        self.assertFalse(summary['production_eligible'])
        self.assertFalse(summary['submitted'])
        self.assertFalse(summary['holdout_evaluated'])
        self.assertFalse(summary['validation_evaluated'])
        cutoff = datetime.fromisoformat(summary['fit_cutoff'])
        self.assertLessEqual(before, cutoff)
        self.assertLessEqual(cutoff, after)
        self.assertEqual(set(p.name for p in self.out.iterdir()),
                         {'model.joblib', 'manifest.json', 'training-run.json'})
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        for path in self.out.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for path in (self.root / 'new-parent', self.root / 'new-parent/models'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        record = json.loads((self.out / 'training-run.json').read_bytes())
        self.assertEqual(record['input_payload_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(record['model_manifest_sha256'],
                         hashlib.sha256((self.out / 'manifest.json').read_bytes()).hexdigest())
        bundle = load_model_bundle(self.out, trusted=True)
        target = (after.astimezone(ZoneInfo('Asia/Taipei')).date() + timedelta(days=1)).isoformat()
        rows = [{'stock_id': '2330', 'target_date': target,
                 'feature_cutoff': target + 'T08:10:00+08:00', 'signal': 1.0, 'sparse': None}]
        with patch.object(bundle.preprocessor, 'fit', side_effect=AssertionError('inference cannot fit')):
            predictions = predict_rows(bundle, rows)
        self.assertIn(predictions[0]['prediction'], (0, 1))
        with self.assertRaisesRegex(ValueError, 'production'):
            predict_rows(bundle, rows, require_production=True)
        for forbidden in ('approved.json', 'submission', 'predictions', 'verified'):
            self.assertFalse((self.root / forbidden).exists())

    def test_research_opt_in_and_verified_input_cannot_be_bypassed(self):
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['status'], 'blocked')
        self.assertFalse(self.out.exists())
        self.write_table(table(readiness='verified'))
        result = self.cli('--allow-research')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())

    def test_both_supported_families_and_synthetic_explicit_opt_in(self):
        self.write_table(table(readiness='synthetic'))
        result = subject.train_model(self.source, self.out, family='hist_gbdt', objective='regression',
                                     seed=7, allow_research=True, clock=lambda: FIXED)
        self.assertEqual(result['family'], 'hist_gbdt')
        self.assertEqual(result['objective'], 'regression')
        self.assertEqual(result['readiness'], 'synthetic')
        self.assertFalse(result['production_eligible'])
        self.assertEqual(result['fit_cutoff'], FIXED.isoformat())

    def test_future_target_and_late_label_leave_failure_only(self):
        for mutation in ('target', 'label'):
            with self.subTest(mutation=mutation):
                value = table(readiness='research_assumption')
                if mutation == 'target':
                    value['rows'][-1].update(target_date='2024-02-01',
                                             feature_cutoff='2024-02-01T08:10:00+08:00')
                else:
                    value['rows'][0]['label_available_at'] = '2024-02-02T00:00:00+08:00'
                self.write_table(value)
                destination = self.root / ('failure-' + mutation)
                with self.assertRaises(ValueError):
                    subject.train_model(self.source, destination, allow_research=True, clock=lambda: FIXED)
                self.assertEqual([p.name for p in destination.iterdir()], ['failure.json'])
                record = json.loads((destination / 'failure.json').read_bytes())
                self.assertEqual(record['status'], 'failed')
                self.assertFalse(record['production_eligible'])

    def test_existing_output_is_never_reused_even_when_empty(self):
        for occupied in (False, True):
            with self.subTest(occupied=occupied):
                destination = self.root / ('existing-' + str(occupied))
                destination.mkdir()
                if occupied:
                    (destination / 'keep.txt').write_bytes(b'previous model evidence')
                before = {p.name: p.read_bytes() for p in destination.iterdir()}
                with patch.object(subject, 'fit_model', side_effect=AssertionError('must reject before fit')):
                    with self.assertRaises(FileExistsError):
                        subject.train_model(self.source, destination, allow_research=True, clock=lambda: FIXED)
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, before)

    def test_private_regular_input_and_output_paths_are_required(self):
        link = self.root / 'table-link.json'
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            subject.train_model(link, self.out, allow_research=True, clock=lambda: FIXED)
        self.source.chmod(0o644)
        with self.assertRaises(ValueError):
            subject.train_model(self.source, self.out, allow_research=True, clock=lambda: FIXED)
        self.source.chmod(0o600)
        git_root = self.root / 'git-checkout'
        git_root.mkdir()
        (git_root / '.git').write_text('gitdir: fixture')
        with self.assertRaisesRegex(ValueError, 'outside Git'):
            subject.train_model(self.source, git_root / 'model', allow_research=True, clock=lambda: FIXED)
        fifo = self.root / 'table.pipe'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            subject.train_model(fifo, self.out, allow_research=True, clock=lambda: FIXED)
        with patch.object(subject, 'MAX_TABLE_BYTES', 16):
            with self.assertRaises(ValueError):
                subject.train_model(self.source, self.out, allow_research=True, clock=lambda: FIXED)
        self.assertFalse(self.out.exists())

    def test_failed_serialization_does_not_publish_a_partial_model_or_exception_text(self):
        sensitive = 'must-not-log-credential-test-value'

        def failed_save(bundle, directory):
            (directory / 'model.joblib').write_bytes(b'incomplete serialization')
            raise ValueError(sensitive)

        with patch.object(subject, 'save_model_bundle', side_effect=failed_save):
            with self.assertRaises(ValueError):
                subject.train_model(self.source, self.out, allow_research=True, clock=lambda: FIXED)
        self.assertEqual([p.name for p in self.out.iterdir()], ['failure.json'])
        self.assertNotIn(sensitive, (self.out / 'failure.json').read_text())
        self.assertFalse(list(self.out.parent.glob('.finpred-single-fit-*')))
        value = table(readiness='research_assumption')
        value['rows'][0]['signal'] = sensitive
        self.write_table(value)
        self.out = self.root / 'bad-input-result'
        result = self.cli('--allow-research')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(sensitive, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'blocked')

    def test_payload_hash_and_parsed_model_use_the_same_original_buffer(self):
        original = self.source.read_bytes()
        original_reader = subject._table_bytes

        def replace_after_read(path):
            captured = original_reader(path)
            changed = table(readiness='research_assumption')
            changed['rows'][0]['signal'] = 99999
            self.write_table(changed)
            return captured

        with patch.object(subject, '_table_bytes', side_effect=replace_after_read):
            summary = subject.train_model(self.source, self.out, allow_research=True, clock=lambda: FIXED)
        expected_canonical = hashlib.sha256(json.dumps(
            json.loads(original), ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.assertEqual(summary['input_payload_sha256'], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(summary['input_payload_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(summary['training_table_sha256'], expected_canonical)

    def test_public_cli_has_no_fit_clock_override(self):
        result = self.cli('--allow-research', '--fit-cutoff', '2024-02-01T00:00:00+00:00')
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrecognized arguments', result.stderr)
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
