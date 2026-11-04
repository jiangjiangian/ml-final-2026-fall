"""Synthetic Phase 1 wire, chronology, durability and receipt behavior."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import requests

from finpred.features.market import FEATURE_COLUMNS as MARKET_FEATURES
from finpred.submission.course import SubmissionError
from finpred.submission.phase1 import build_phase1_csv
from finpred.submission.phase1_submit import (
    EXPECTED_FEATURES, FIXED_RECIPE, FORECAST_CODE_FILES, SOURCE_URLS, Phase1SubmissionClient,
    execute_phase1_submission, phase1_guard, phase1_payload,
    validate_forecast_evidence,
)
from test_phase1_forecast import fixture as forecast_fixture, market_fixture
from test_submission import Response, Session

NOW = datetime.fromisoformat('2026-11-03T13:30:00+00:00')  # 21:30 Taipei, not a Phase 2 window.
DEADLINE = datetime.fromisoformat('2026-12-24T15:59:00+00:00')
PROJECT = Path(__file__).resolve().parents[1]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = value if isinstance(value, bytes) else (json.dumps(value) + '\n').encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    return payload


def official_state():
    return {'config': {'phase1OpenAt': '2026-09-16T00:00:00Z',
                       'phase1Deadline': DEADLINE.isoformat()},
            'user': {'role': 'student'}, 'team': {'id': 'synthetic-team'},
            'mySubmissions': [], 'uploadQuota': {'phase1': {
                'day': '2026-11-03', 'userLimit': 0, 'userCount': 0, 'teamLimit': 10, 'teamCount': 0}}}


def fixture(directory):
    """Fake private bytes exercise binding only; they are not actual fitted models."""
    root = Path(directory)
    root.chmod(0o700)
    days, current = [], date(2026, 6, 1)
    while len(days) < 84:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    ids = [f'{i:04}' for i in range(1, 51)]
    template = ('id,' + ','.join(days) + '\n' + ''.join(
        stock + ',' + ','.join(['0'] * 84) + '\n' for stock in ids)).encode()
    predictions = [{'stock_id': stock, 'target_date': day, 'prediction': (i + j) % 2}
                   for i, stock in enumerate(ids) for j, day in enumerate(days)]
    csv_bytes = build_phase1_csv(predictions, template)
    sources = []
    for name in SOURCE_URLS:
        payload_path = root / 'sources' / (name + '.zip')
        payload = private(payload_path, template if name == 'course-template' else
                          b'not-real-source: synthetic integrity fixture')
        manifest_path = root / 'sources' / (name + '.json')
        record = {'schema_version': 'snapshot-v1', 'source': name, 'source_url': SOURCE_URLS[name],
                  'sha256': digest(payload), 'payload_path': str(payload_path), 'size_bytes': len(payload),
                  'fetched_at': '2026-11-03T12:00:00Z', 'metadata': {'tls_verified': True}}
        raw = private(manifest_path, record)
        sources.append({'source': name, 'source_url': SOURCE_URLS[name],
                        'manifest_path': str(manifest_path), 'manifest_sha256': digest(raw),
                        'payload_path': str(payload_path), 'payload_sha256': digest(payload),
                        'fetched_at': record['fetched_at'], 'tls_verified': True})
    training = {'readiness': 'research_assumption', 'feature_version': 'test-v1',
                'feature_columns': EXPECTED_FEATURES, 'rows': [
                    {'stock_id': ids[0], 'target_date': '2026-05-29', 'y': 0,
                     'feature_cutoff': '2026-05-29T08:10:00+08:00', **dict.fromkeys(MARKET_FEATURES, 0.0)}]}
    features = {'schema_version': 'sequence-feature-table-v1', 'readiness': 'research_assumption',
                'production_eligible': False, 'feature_version': 'test-v1',
                'feature_columns': EXPECTED_FEATURES, 'stock_ids': ids, 'rows': []}
    from finpred.training.architecture_comparison import digest as document_digest
    from finpred.training.phase1_forecast import frozen_market_features, selection_reference

    market_payload = market_fixture({stock: [{'date': '2026-05-29'}] for stock in ids}, template)
    report_value = json.loads(forecast_fixture()[2])
    report_value['feature_metadata']['feature_document_sha256'] = document_digest(json.loads(market_payload))
    report = json.dumps(report_value).encode()
    _, binding = frozen_market_features(market_payload, report, ids)
    features['frozen_market_feature_binding'] = binding
    code = {name: digest((PROJECT / name).read_bytes()) for name in FORECAST_CODE_FILES}
    packages = dict.fromkeys(('numpy', 'scikit-learn', 'joblib', 'torch'), 'synthetic-test')
    values = {
        'registration.json': {'schema_version': 'phase1-fixed-registration-v1',
            'registered_at': '2026-11-03T12:01:00Z', 'source_snapshots': sources, 'recipe_id': 'M3-2',
            'scope': 'static_phase1_backtest_not_phase2_production', 'recipe': FIXED_RECIPE,
            'readiness': 'research_assumption', 'historical_availability_verified': False,
            'production_eligible': False, 'no_phase1_labels_used': True, 'target_dates_scored': False,
            'template_sha256': digest(template), 'target_dates': days, 'stock_ids': ids, 'panel_stock_ids': ids,
            'training_rows': 1, 'training_label_start_date': '2026-05-29',
            'training_label_end_date': '2026-05-29', 'training_table_sha256': document_digest(training),
            'training_table_file_sha256': digest((json.dumps(training) + '\n').encode()),
            'feature_rows_sha256': document_digest(features),
            'feature_rows_file_sha256': digest((json.dumps(features) + '\n').encode()),
            'market_feature_rows_sha256': digest(market_payload),
            'market_feature_document_sha256': binding['market_feature_document_sha256'],
            'market_feature_binding': binding,
            'code_sha256': code, 'code_git_revision_at_registration': '0' * 40,
            'package_versions': packages, 'selection_reference': selection_reference(report)},
        'training-table.json': training,
        'feature-rows.json': features,
        'feature-evidence.json': [],
        'template.csv': template,
        'selection-report.json': report,
        'market-feature-rows.json': market_payload,
        'predictions.json': predictions,
        'model/preprocessor.joblib': b'synthetic-not-a-pickle',
        'model/weights.npz': b'synthetic-not-model-weights',
        'model/metadata.json': {'schema_version': 'phase1-tcn-model-v1', 'recipe_id': 'M3-2',
            'recipe': FIXED_RECIPE, 'readiness': 'research_assumption', 'production_eligible': False,
            'feature_columns': EXPECTED_FEATURES, 'feature_version': 'test-v1', 'stock_ids': ids,
            'input_channels': 31, 'package_versions': packages,
            'training_mse_percentage_point_history': [0.1] * 20},
        'submission/predictions.csv': csv_bytes,
        'submission/manifest.json': {'csv_sha256': digest(csv_bytes), 'template_sha256': digest(template)},
    }
    hashes = {name: digest(private(root / name, value)) for name, value in values.items()}
    manifest = {
        'schema_version': 'phase1-forecast-v1', 'phase': 1, 'readiness': 'research_assumption',
        'historical_availability_verified': False, 'production_eligible': False, 'submitted': False,
        'no_phase1_labels_used': True, 'phase1_targets_scored': False, 'model_fit_count': 1,
        'recipe_id': 'M3-2', 'stock_count': 50, 'date_count': 84, 'prediction_count': 4200,
        'generated_at': '2026-11-03T13:00:00Z', 'training_label_end_date': '2026-05-29',
        'template_sha256': digest(template), 'csv_sha256': digest(csv_bytes),
        'prediction_json_sha256': hashes['predictions.json'], 'registration_sha256': hashes['registration.json'],
        'artifact_sha256': hashes, 'source_snapshots': sources,
        'market_feature_rows_sha256': digest(market_payload),
        'market_feature_document_sha256': binding['market_feature_document_sha256'],
        'code_sha256': code,
    }
    path = root / 'manifest.json'
    private(path, manifest)
    return csv_bytes, template, path


class Client(Phase1SubmissionClient):
    def __init__(self, template, csv_bytes):
        self.data, self.template_bytes, self.current_csv = official_state(), template, csv_bytes
        self.post_count, self.ack_only, self.fail_post = 0, False, False
        self.read_calls = []

    def template(self):
        return self.template_bytes

    def state(self):
        return deepcopy(self.data)

    def set_receipt(self):
        self.data['mySubmissions'] = [{'id': 'phase1/record', 'phase': 1, 'predictionCount': 4200,
            'submittedAt': '2026-11-03T13:30:00Z', 'score': None}]

    def post_phase1(self, name, payload):
        self.post_count += 1
        if self.fail_post:
            raise SubmissionError('synthetic unknown network result')
        if not self.ack_only:
            self.set_receipt()

    def read(self, method, path, **kwargs):
        self.read_calls.append((method, path))
        if method != 'GET' or path != '/api/submissions/phase1%2Frecord?record=current':
            raise AssertionError('wrong Phase 1 receipt endpoint')
        return self.current_csv


class Phase1SubmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.forecast = self.root / 'forecast'
        self.forecast.mkdir(mode=0o700)
        self.csv, self.template, self.manifest = fixture(self.forecast)
        self.runtime = self.root / 'runtime'
        self.client = Client(self.template, self.csv)

    def execute(self, **options):
        arguments = {'forecast_manifest': self.manifest, 'dry_run': False,
                     'clock': lambda: NOW, 'poll_interval': 0}
        arguments.update(options)
        return execute_phase1_submission(self.client, self.csv, self.template, self.runtime, **arguments)

    def test_static_payload_4200_and_afternoon_dry_run_need_no_phase2_state(self):
        wire = phase1_payload(self.csv, self.template)
        self.assertEqual(set(wire), {'stockIds', 'dates', 'predictions'})
        self.assertEqual((len(wire['stockIds']), len(wire['dates'])), (50, 84))
        self.assertEqual(sum(map(len, wire['predictions'])), 4200)
        result = self.execute(dry_run=True)
        self.assertEqual(result['status'], 'dry_run')
        self.assertTrue(result['would_submit'])
        self.assertFalse(self.runtime.exists())
        self.assertEqual(self.client.post_count, 0)

    def test_first_post_requires_downloaded_current_csv_then_is_idempotent(self):
        result = self.execute()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['record_id'], 'phase1/record')
        self.assertTrue(result['submitted'])
        self.assertFalse(result['production_eligible'])
        self.assertEqual(self.execute()['status'], 'verified')
        self.assertEqual(self.client.post_count, 1)
        ledger = self.runtime / 'submission/phase1/latest.json'
        self.assertEqual(json.loads(ledger.read_bytes())['csv_sha256'], digest(self.csv))
        self.assertEqual(ledger.stat().st_mode & 0o777, 0o600)
        for directory in (self.runtime, self.runtime / 'submission', ledger.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_unknown_post_outcome_never_repeats_and_can_reconcile(self):
        self.client.fail_post = True
        with self.assertRaisesRegex(SubmissionError, 'unverified'):
            self.execute()
        with self.assertRaisesRegex(SubmissionError, 'unresolved'):
            self.execute()
        self.assertEqual(self.client.post_count, 1)
        self.client.set_receipt()
        self.assertEqual(self.execute(verify_only=True)['status'], 'verified')
        self.assertEqual(self.client.post_count, 1)

    def test_ack_or_wrong_current_csv_is_not_a_receipt_or_retried(self):
        self.client.current_csv = self.template
        with self.assertRaisesRegex(SubmissionError, 'lacks a verified'):
            self.execute()
        with self.assertRaisesRegex(SubmissionError, 'unresolved'):
            self.execute()
        self.assertEqual(self.client.post_count, 1)
        self.client.data['mySubmissions'] = []
        self.assertEqual(self.execute(verify_only=True)['status'], 'no_matching_current_receipt')
        self.assertEqual(self.client.post_count, 1)

    def test_open_deadline_account_and_fresh_daily_quota_fail_closed(self):
        mutations = [lambda s: s['config'].update(phase1OpenAt='2026-11-04T00:00:00Z'),
                     lambda s: s['config'].update(phase1Deadline=NOW.isoformat()),
                     lambda s: s.update(team=None),
                     lambda s: s['uploadQuota'].update(phase1=None),
                     lambda s: s['uploadQuota']['phase1'].update(day='2026-11-02'),
                     lambda s: s['uploadQuota']['phase1'].update(teamCount=10),
                     lambda s: s['uploadQuota']['phase1'].update(userLimit=True),
                     lambda s: s.update(user={})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.client.data = official_state()
                mutate(self.client.data)
                with self.assertRaises(SubmissionError):
                    self.execute()
                self.assertEqual(self.client.post_count, 0)
        self.assertTrue(phase1_guard(official_state(), NOW))

    def test_deadline_rechecked_after_durable_checkpoint_before_post(self):
        ticks = iter([NOW, NOW, DEADLINE])
        with self.assertRaisesRegex(SubmissionError, 'deadline'):
            self.execute(clock=lambda: next(ticks))
        self.assertEqual(self.client.post_count, 0)
        ledger = json.loads((self.runtime / 'submission/phase1/latest.json').read_bytes())
        self.assertEqual(ledger['status'], 'blocked_before_post')

    def test_failed_checkpoint_never_posts(self):
        with patch('finpred.submission.phase1_submit._write_ledger', side_effect=OSError('synthetic disk full')):
            with self.assertRaises(OSError):
                self.execute()
        self.assertEqual(self.client.post_count, 0)

    def test_changed_artifact_or_source_is_rejected_before_post(self):
        for path in (self.forecast / 'model/weights.npz', self.forecast / 'sources/course-live.zip'):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b'changed')
                with self.assertRaises(SubmissionError):
                    self.execute()
                path.write_bytes(original)
                self.assertEqual(self.client.post_count, 0)

    def test_declared_or_actual_phase1_training_labels_are_rejected(self):
        original = json.loads(self.manifest.read_bytes())
        for field, value in (('training_label_end_date', '2026-06-01'),
                             ('phase1_targets_scored', True), ('model_fit_count', 2),
                             ('no_phase1_labels_used', False), ('production_eligible', True)):
            with self.subTest(field=field):
                private(self.manifest, {**original, field: value})
                with self.assertRaises(SubmissionError):
                    self.execute()
        private(self.manifest, original)
        path = self.forecast / 'training-table.json'
        raw = private(path, {'readiness': 'research_assumption', 'rows': [{'target_date': '2026-06-01'}]})
        original['artifact_sha256']['training-table.json'] = digest(raw)
        private(self.manifest, original)
        with self.assertRaisesRegex(SubmissionError, 'label prefix'):
            self.execute()
        self.assertEqual(self.client.post_count, 0)

    def test_unsafe_artifact_path_unknown_source_code_change_and_future_generation_rejected(self):
        original = json.loads(self.manifest.read_bytes())
        bad = deepcopy(original)
        bad['artifact_sha256']['../outside'] = '0' * 64
        cases = [bad, {**original, 'source_snapshots': []},
                 {**original, 'code_sha256': {'src/finpred/submission/phase1_submit.py': '0' * 64}},
                 {**original, 'generated_at': '2026-11-03T14:00:00Z'}]
        for changed in cases:
            with self.subTest(changed=next(iter(changed))):
                private(self.manifest, changed)
                with self.assertRaises(SubmissionError):
                    self.execute()
                self.assertEqual(self.client.post_count, 0)

    def test_current_effective_version_not_highest_historical_score(self):
        self.client.data['submissionHistory'] = [{'id': 'historical-best', 'phase': 1, 'score': 100}]
        self.client.set_receipt()
        self.assertEqual(self.execute(verify_only=True)['record_id'], 'phase1/record')
        self.assertTrue(all('record=current' in path for _, path in self.client.read_calls))
        self.assertEqual(self.client.post_count, 0)

    def test_older_job_cannot_replace_newer_local_or_official_version(self):
        self.execute()
        self.client.current_csv = self.template
        original = json.loads(self.manifest.read_bytes())
        private(self.manifest, {**original, 'generated_at': '2026-11-03T12:59:00Z'})
        with self.assertRaisesRegex(SubmissionError, 'older Phase 1'):
            self.execute()
        self.assertEqual(self.client.post_count, 1)
        private(self.manifest, original)
        ledger = self.runtime / 'submission/phase1/latest.json'
        ledger.unlink()
        with self.assertRaisesRegex(SubmissionError, 'newer official'):
            self.execute()
        self.assertEqual(self.client.post_count, 1)

    def test_verify_only_can_reconcile_after_phase1_deadline_without_post(self):
        self.client.set_receipt()
        self.assertEqual(self.execute(verify_only=True, clock=lambda: DEADLINE)['status'], 'verified')
        self.assertEqual(self.client.post_count, 0)

    def test_recipe_selection_and_model_metadata_must_agree(self):
        original = json.loads(self.manifest.read_bytes())
        cases = [('registration.json', lambda value: value['recipe'].update(seed=43)),
                 ('registration.json', lambda value: value['selection_reference'].update(
                     selection_scope='phase1_leaderboard_search')),
                 ('model/metadata.json', lambda value: value['recipe'].update(dropout=.2)),
                 ('model/metadata.json', lambda value: value.update(training_mse_percentage_point_history=[.1])),
                 ('selection-report.json', lambda value: value.update(holdout_evaluated=True))]
        for name, mutate in cases:
            with self.subTest(artifact=name):
                path = self.forecast / name
                before = path.read_bytes()
                changed = json.loads(before)
                mutate(changed)
                raw = private(path, changed)
                manifest = deepcopy(original)
                manifest['artifact_sha256'][name] = digest(raw)
                if name == 'registration.json':
                    manifest['registration_sha256'] = digest(raw)
                private(self.manifest, manifest)
                with self.assertRaises(SubmissionError):
                    self.execute()
                private(path, before)
                private(self.manifest, original)
        self.assertEqual(self.client.post_count, 0)

    def test_template_snapshot_bytes_are_required_not_just_matching_manifest_hashes(self):
        manifest = json.loads(self.manifest.read_bytes())
        source = next(item for item in manifest['source_snapshots'] if item['source'] == 'course-template')
        source['payload_sha256'] = digest(private(source['payload_path'], b'changed template source'))
        snapshot = json.loads(Path(source['manifest_path']).read_bytes())
        snapshot.update(sha256=source['payload_sha256'], size_bytes=len(b'changed template source'))
        source['manifest_sha256'] = digest(private(source['manifest_path'], snapshot))
        registration_path = self.forecast / 'registration.json'
        registration = json.loads(registration_path.read_bytes())
        registration['source_snapshots'] = manifest['source_snapshots']
        manifest['registration_sha256'] = digest(private(registration_path, registration))
        manifest['artifact_sha256']['registration.json'] = manifest['registration_sha256']
        private(self.manifest, manifest)
        with self.assertRaisesRegex(SubmissionError, 'collected template source'):
            self.execute()
        self.assertEqual(self.client.post_count, 0)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'optional neural extra absent')
class GenuineForecasterIntegrationTests(unittest.TestCase):
    def test_audited_three_source_archives_to_actual_frozen_fit_to_submission_evidence(self):
        """Small synthetic market history, real loader/model/formatter/validator, no HTTP."""
        from finpred.data.course_schema import GLOBAL_COLUMNS, STOCK_COLUMNS
        from finpred.data.snapshots import snapshot_bytes
        from finpred.training.phase1_forecast import forecast_fixed_phase1, load_source_manifests
        from test_daily_tables import IDS, csv_payload, row

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'wire-fixture').mkdir(mode=0o700)
            _, template, _ = fixture(root / 'wire-fixture')
            dates = phase1_payload(template, template)['dates']

            def archive(kind):
                days = ['2026-05-28', '2026-05-29'] if kind == 'training' else dates
                values = [row(day, close=11 if index % 2 else 9) for index, day in enumerate(days)]
                output = io.BytesIO()
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
                    for stock in IDS:
                        zipped.writestr('data/market/' + stock + '.csv', csv_payload(STOCK_COLUMNS, values))
                    global_row = dict.fromkeys(GLOBAL_COLUMNS, '1') | {'date': days[-1]}
                    zipped.writestr('data/global/global_data.csv', csv_payload(GLOBAL_COLUMNS, [global_row]))
                    if kind == 'training':
                        zipped.writestr('data/info.json', json.dumps({'Top50@Y': IDS[:50], 'Top100@Y': IDS}))
                return output.getvalue()

            paths = []
            for source, payload in (('course-training', archive('training')),
                                    ('course-live', archive('live')), ('course-template', template)):
                acquired = snapshot_bytes(payload, root / 'raw', source, SOURCE_URLS[source],
                                          '.csv' if source == 'course-template' else '.zip',
                                          {'tls_verified': True})
                paths.append(acquired['manifest_path'])
            stocks, official_template, sources, provenance = load_source_manifests(paths)
            market_payload = market_fixture(stocks, official_template)
            report_value = json.loads(forecast_fixture()[2])
            from finpred.training.architecture_comparison import digest as document_digest
            report_value['feature_metadata']['feature_document_sha256'] = document_digest(json.loads(market_payload))
            with patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')):
                forecast = forecast_fixed_phase1(stocks, official_template, root / 'forecast',
                    source_snapshots=sources, archive_provenance=provenance,
                    selection_report_payload=json.dumps(report_value).encode(),
                    market_feature_rows_payload=market_payload)
                csv_bytes = Path(forecast['directory'], 'submission/predictions.csv').read_bytes()
                validated = validate_forecast_evidence(forecast['manifest_path'], csv_bytes, official_template,
                                                       now=datetime.now(timezone.utc))
            self.assertEqual(validated['recipe_id'], 'M3-2')
            self.assertEqual(validated['training_label_end_date'], '2026-05-29')
            self.assertFalse(validated['historical_availability_verified'])
            self.assertFalse(validated['production_eligible'])
            self.assertEqual(forecast['prediction_count'], 4200)


class Phase1TransportTests(unittest.TestCase):
    def test_wire_fields_tls_no_redirect_and_single_post(self):
        session = Session(Response())
        client = Phase1SubmissionClient(session=session)
        matrix = {'stockIds': ['0001'], 'dates': ['2026-06-01'], 'predictions': [[1]]}
        client.post_phase1('predictions.csv', matrix)
        args, kwargs = session.calls[0]
        self.assertEqual(args, ('POST', 'https://final.html2026.csie.org/api/submissions'))
        self.assertEqual(set(kwargs['json']), {'phase', 'fileName', 'payload', 'note'})
        self.assertEqual(kwargs['json']['phase'], 1)
        self.assertEqual(kwargs['json']['payload'], matrix)
        self.assertTrue(kwargs['verify'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertTrue(session.response.closed)

    def test_redirect_bad_ack_and_network_error_are_never_replayed_or_exposed(self):
        for response in (Response(307), Response(200, b'not-json'),
                         requests.ConnectionError('do-not-expose-test-secret')):
            with self.subTest(response=type(response).__name__):
                session = Session(response)
                with self.assertRaises(SubmissionError) as caught:
                    Phase1SubmissionClient(session=session).post_phase1('predictions.csv', {})
                self.assertNotIn('do-not-expose-test-secret', str(caught.exception))
                self.assertEqual(len(session.calls), 1)


if __name__ == '__main__':
    unittest.main()
