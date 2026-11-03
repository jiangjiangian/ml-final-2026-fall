"""Prospective research evidence must not acquire production permissions."""

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from finpred.inference.predict import predict_rows
from finpred.pipelines.daily import PipelineBlocked
from finpred.pipelines.shadow import (
    SESSION_SCHEMA, STATE_URL, build_shadow_session_evidence, run_shadow_forecast,
)
from finpred.training.fit import fit_model, save_model_bundle
from test_daily_pipeline import canonical_prediction_table

DAY = '2026-11-02'


def moment(value):
    return datetime.fromisoformat(DAY + 'T' + value + '+08:00')


def private_file(path, value):
    path.write_bytes(value if isinstance(value, bytes) else (json.dumps(value) + '\n').encode())
    path.chmod(0o600)
    return path


def inputs(root, *, fit_objective='classification'):
    root = Path(root)
    table = canonical_prediction_table(root)
    table_path = private_file(root / 'prediction-table.json', table)
    training = {'schema_version': 'training-table-v1', 'readiness': 'research_assumption',
                'feature_columns': table['feature_columns'], 'feature_version': table['feature_version'],
                'availability_evidence': 'synthetic fixture, no historical verification', 'rows': []}
    for day in ('2026-10-29', '2026-10-30'):
        for i, prediction_row in enumerate(table['rows']):
            row = deepcopy(prediction_row)
            closing = 11 if i % 2 else 9
            row.update(target_date=day, feature_cutoff=day + 'T08:10:00+08:00',
                       adj_open=10, adj_close=closing, y=int(closing > 10),
                       target_intraday_return=(closing - 10) / 10)
            row[table['feature_columns'][0]] = 0.1 if i % 2 else -0.1
            training['rows'].append(row)
    bundle = fit_model(training, fit_cutoff=DAY + 'T07:20:00+08:00', objective=fit_objective,
                       allow_research=True)
    model_directory = root / 'research-model'
    save_model_bundle(bundle, model_directory)
    template = ('id,' + DAY + '\n' + ''.join(row['stock_id'] + ',0\n' for row in table['rows'])).encode()
    template_path = private_file(root / 'template.csv', template)
    session = {'schema_version': SESSION_SCHEMA, 'source_url': STATE_URL,
               'fetched_at': DAY + 'T08:10:00+08:00', 'tls_verified': True,
               'session': {'tradingDate': DAY, 'enabled': True,
                           'openAt': DAY + 'T04:00:00+08:00', 'deadline': DAY + 'T09:00:00+08:00'},
               'template': {'source_url': 'https://final.html2026.csie.org/api/sample-submission?phase=2&tradingDate=' + DAY,
                            'fetched_at': DAY + 'T08:10:00+08:00', 'tls_verified': True,
                            'sha256': hashlib.sha256(template).hexdigest()}}
    session_path = private_file(root / 'session.json', session)
    return {'trusted_model_dir': model_directory, 'prediction_table': table_path,
            'template_path': template_path, 'session_evidence_path': session_path,
            'target_date': DAY}, table, bundle


class ShadowForecastTests(unittest.TestCase):
    def test_pure_session_extract_excludes_accounts_and_rejects_missing_official_day(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, _, _ = inputs(directory)
            original = json.loads(kwargs['session_evidence_path'].read_bytes())
            state = {'phase2Days': [original['session']],
                     'user': {'email': 'exclude-email@example.invalid'}, 'token': 'exclude-token',
                     'submissions': [{'receipt': 'exclude-receipt'}]}
            evidence = build_shadow_session_evidence(
                state, DAY, state_fetched_at=moment('08:10:00'),
                template_payload=kwargs['template_path'].read_bytes(),
                template_fetched_at=moment('08:10:00'), tls_verified=True)
            text = json.dumps(evidence)
            for excluded in ('exclude-email', 'exclude-token', 'exclude-receipt', 'user', 'submissions'):
                self.assertNotIn(excluded, text)
            self.assertEqual(evidence, original)
            with self.assertRaises(ValueError):
                build_shadow_session_evidence(
                    {'phase2Days': []}, DAY, state_fetched_at=moment('08:10:00'),
                    template_payload=kwargs['template_path'].read_bytes(),
                    template_fetched_at=moment('08:10:00'), tls_verified=True)

    def test_research_bundle_predicts_without_approval_or_network_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kwargs, table, bundle = inputs(root)
            official_paths = [root / 'approved.json', root / 'predictions', root / 'submission', root / 'verified']
            before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}
            with patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')), patch(
                'finpred.pipelines.daily.CourseSubmissionClient', side_effect=AssertionError('client forbidden')
            ), patch('finpred.pipelines.daily.execute_submission', side_effect=AssertionError('submit forbidden')), patch(
                'finpred.pipelines.daily.train_candidate', side_effect=AssertionError('fit forbidden')
            ):
                result = run_shadow_forecast(root, **kwargs, clock=lambda: moment('08:11:00'))
            destination = Path(result['directory'])
            self.assertTrue((destination / 'completion.json').exists())
            expected = predict_rows(bundle, table['rows'], feature_columns=table['feature_columns'],
                                    feature_version=table['feature_version'])
            actual = (destination / 'prediction.csv').read_text().splitlines()[1:]
            self.assertEqual(actual, [row['stock_id'] + ',' + str(row['prediction']) for row in expected])
            metadata = json.loads((destination / 'manifest.json').read_bytes())
            self.assertEqual(metadata['model_readiness'], 'research_assumption')
            self.assertFalse(metadata['production_eligible'])
            self.assertFalse(metadata['historical_availability_verified'])
            self.assertFalse(metadata['submitted'])
            self.assertEqual(metadata['feature_verification_scope'], 'current_observed_bytes_only')
            self.assertFalse(any(path.exists() for path in official_paths))
            for relative, content in before.items():
                self.assertEqual((root / relative).read_bytes(), content)
            completion = json.loads((destination / 'completion.json').read_bytes())
            self.assertEqual(completion['manifest_sha256'], hashlib.sha256((destination / 'manifest.json').read_bytes()).hexdigest())
            original = (destination / 'prediction.csv').read_bytes()
            private_file(root / 'later-labels.json', {'observed_after_prediction': True})
            self.assertEqual((destination / 'prediction.csv').read_bytes(), original)
            with self.assertRaises(FileExistsError):
                run_shadow_forecast(root, **kwargs, clock=lambda: moment('08:12:00'))
            self.assertEqual((destination / 'prediction.csv').read_bytes(), original)

    def test_official_template_can_reorder_the_same_canonical_stock_universe(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, table, bundle = inputs(directory)
            template = ('id,' + DAY + '\n' + ''.join(
                row['stock_id'] + ',0\n' for row in reversed(table['rows']))).encode()
            private_file(kwargs['template_path'], template)
            session = json.loads(kwargs['session_evidence_path'].read_bytes())
            session['template']['sha256'] = hashlib.sha256(template).hexdigest()
            private_file(kwargs['session_evidence_path'], session)
            result = run_shadow_forecast(directory, **kwargs, clock=lambda: moment('08:11:00'))
            expected = predict_rows(bundle, table['rows'])
            actual = (Path(result['directory']) / 'prediction.csv').read_text().splitlines()[1:]
            self.assertEqual(actual, [row['stock_id'] + ',' + str(row['prediction']) for row in reversed(expected)])

    def test_freeze_and_deadline_use_actual_clock_and_late_completion_has_no_valid_marker(self):
        for value in ('08:09:59', '09:00:00'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                kwargs, _, _ = inputs(directory)
                with self.assertRaises(PipelineBlocked):
                    run_shadow_forecast(directory, **kwargs, clock=lambda: moment(value))
                self.assertFalse((Path(directory) / 'shadow').exists())
        for ticks in (
                ['08:59:58', '09:00:00'],
                ['08:59:58', '08:59:59', '09:00:00'],
                ['08:59:58', '08:59:59', '08:59:59', '09:00:00']):
            with self.subTest(ticks=ticks), tempfile.TemporaryDirectory() as directory:
                kwargs, _, _ = inputs(directory)
                clock = iter(map(moment, ticks))
                with self.assertRaises(PipelineBlocked):
                    run_shadow_forecast(directory, **kwargs, clock=lambda: next(clock))
                self.assertFalse(list((Path(directory) / 'shadow').rglob('completion.json')))

    def test_prediction_tampering_still_uses_canonical_source_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, table, _ = inputs(directory)
            for mutation in ('value', 'missing_mask', 'order', 'version', 'payload', 'old_live'):
                with self.subTest(mutation=mutation):
                    changed = deepcopy(table)
                    if mutation == 'value':
                        changed['rows'][0][changed['feature_columns'][0]] = 1234
                    elif mutation == 'missing_mask':
                        changed['rows'][0][changed['feature_columns'][0]] = None
                    elif mutation == 'order':
                        changed['rows'].reverse()
                    elif mutation == 'version':
                        changed['feature_version'] += '-market'
                    elif mutation == 'payload':
                        changed['feature_evidence'][-1]['payload_sha256'] = '0' * 64
                    else:
                        changed['feature_evidence'][-1]['fetched_at'] = '2026-10-30T07:00:00+08:00'
                    private_file(kwargs['prediction_table'], changed)
                    with self.assertRaises(PipelineBlocked):
                        run_shadow_forecast(directory, **kwargs, clock=lambda: moment('08:11:00'))
            self.assertFalse((Path(directory) / 'shadow').exists())

    def test_session_template_retrieval_evidence_and_earlier_official_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, _, _ = inputs(directory)
            original = json.loads(kwargs['session_evidence_path'].read_bytes())
            for mutation in ('credentials', 'wrong_template', 'future_fetch', 'prior_fetch', 'unverified_tls',
                             'disabled', 'wrong_date', 'earlier_deadline'):
                with self.subTest(mutation=mutation):
                    changed = deepcopy(original)
                    if mutation == 'credentials':
                        changed['user'] = {'email': 'must-not-copy@example.invalid'}
                    elif mutation == 'wrong_template':
                        changed['template']['sha256'] = 'f' * 64
                    elif mutation == 'future_fetch':
                        changed['fetched_at'] = DAY + 'T08:12:00+08:00'
                    elif mutation == 'prior_fetch':
                        changed['fetched_at'] = '2026-11-01T08:10:00+08:00'
                    elif mutation == 'unverified_tls':
                        changed['template']['tls_verified'] = False
                    elif mutation == 'disabled':
                        changed['session']['enabled'] = False
                    elif mutation == 'wrong_date':
                        changed['session']['tradingDate'] = '2026-11-03'
                    else:
                        changed['session']['deadline'] = DAY + 'T08:11:00+08:00'
                    private_file(kwargs['session_evidence_path'], changed)
                    with self.assertRaises(ValueError):
                        run_shadow_forecast(directory, **kwargs, clock=lambda: moment('08:11:00'))
            self.assertFalse((Path(directory) / 'shadow').exists())

    def test_interrupted_final_check_does_not_leave_a_completion_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, _, _ = inputs(directory)
            clock = Mock(side_effect=[moment('08:11:00')] * 3 + [KeyboardInterrupt])
            with self.assertRaises(KeyboardInterrupt):
                run_shadow_forecast(directory, **kwargs, clock=clock)
            self.assertFalse(list((Path(directory) / 'shadow').rglob('completion.json')))

    def test_recipe_is_frozen_and_does_not_promote_research_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs, _, _ = inputs(directory)
            run_shadow_forecast(directory, **kwargs, clock=lambda: moment('08:11:00'))
            recipe = Path(directory) / 'shadow/recipe.json'
            content = recipe.read_bytes()
            with tempfile.TemporaryDirectory(dir=directory) as second:
                other, _, _ = inputs(second, fit_objective='regression')
                with self.assertRaisesRegex(PipelineBlocked, 'recipe is frozen'):
                    run_shadow_forecast(directory, **other, clock=lambda: moment('08:12:00'))
            self.assertEqual(recipe.read_bytes(), content)
            self.assertFalse((Path(directory) / 'approved.json').exists())


if __name__ == '__main__':
    unittest.main()
