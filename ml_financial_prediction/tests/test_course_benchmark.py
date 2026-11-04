"""A named deployment policy never turns retrospective assumptions into PIT."""

from datetime import date, datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from finpred.data.course_schema import GLOBAL_COLUMNS, STOCK_COLUMNS
from finpred.data.daily_tables import SOURCE_URLS
from finpred.data.snapshots import snapshot_bytes
from finpred.pipelines import course_benchmark as course
from finpred.pipelines.daily import PipelineBlocked
from finpred.submission.course import SubmissionError
from finpred.training.fit import train_candidate
from test_daily_tables import IDS, csv_payload, index, row

DAY = '2026-11-02'


def clock(value):
    return lambda: datetime.fromisoformat(DAY + 'T' + value + '+08:00')


class Client:
    def __init__(self):
        self.posts = 0
        self.posted = None
        self.unknown = False

    def state(self):
        return {'phase2Days': [
            {'tradingDate': DAY, 'enabled': True, 'openAt': DAY + 'T04:00:00+08:00',
             'deadline': DAY + 'T09:00:00+08:00'},
            {'tradingDate': '2026-10-30', 'enabled': True}],
            'user': {'role': 'student'}, 'team': {'id': 'synthetic-team'},
            'uploadQuota': {'phase2ByDate': {DAY: {
                'userLimit': 0, 'userCount': 0, 'teamLimit': 10, 'teamCount': 0}}}}

    def daily_template(self, day):
        return ('id,' + day + '\n' + ''.join(sid + ',0\n' for sid in IDS[:50])).encode()

    def current_receipt(self, state, day, expected, template):
        if self.posted == expected:
            return {'status': 'verified', 'record_id': 'synthetic-only',
                    'submitted_at': DAY + 'T08:20:00+08:00', 'scoring_status': 'pending'}
        return None

    def post_predictions(self, day, name, payload):
        self.posts += 1
        if self.unknown:
            raise SubmissionError('synthetic ambiguous network failure')
        self.posted = payload


def archive(kind):
    days = [(date(2026, 10, 29) - timedelta(days=i)).isoformat() for i in reversed(range(330))]
    selected = days if kind == 'training' else ['2026-10-30', DAY]
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for position, sid in enumerate(IDS):
            observations = []
            for i, day in enumerate(selected):
                # Long blocks make the preceding row predictive, with both
                # classes present. These are synthetic data, not market claims.
                up = ((i + (330 if kind == 'live' else 0)) // 20 + position) % 2
                observations.append(row(day, close=11 if up else 9,
                                        pending=kind == 'live' and day == DAY))
            zipped.writestr(f'data/market/{sid}.csv', csv_payload(STOCK_COLUMNS, observations))
        zipped.writestr('data/global/global_data.csv', csv_payload(
            GLOBAL_COLUMNS, [dict.fromkeys(GLOBAL_COLUMNS, '1') | {'date': selected[-1]}]))
        if kind == 'training':
            zipped.writestr('data/info.json', json.dumps({'Top50@Y': IDS[:50], 'Top100@Y': IDS}))
    return output.getvalue()


def acquire_sources(root):
    acquired = []
    for kind in ('training', 'live'):
        source = 'course-' + kind
        with patch('finpred.data.snapshots.datetime') as fixed:
            fixed.now.return_value = clock('07:00:00')()
            acquired.append(snapshot_bytes(archive(kind), root / 'raw', source,
                                            SOURCE_URLS[source], '.zip', {'tls_verified': True}))
    index(root, acquired)
    return acquired


def worker(table, destination, kwargs, timeout):
    if any(item['target_date'] >= DAY for item in table['rows']):
        raise AssertionError('current outcome reached fitting')
    return {'ok': True, 'report': train_candidate(table, destination, **kwargs)}


class CourseBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        acquire_sources(cls.root)
        cls.approval = course.run_course_benchmark(cls.root, 'train', client=Client(),
                clock=clock('07:21:00'), train_worker=worker)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_fixed_fit_preserves_scope_and_strict_pointer(self):
        self.assertEqual(self.approval['status'], 'course_model_approved')
        descriptor, bundle = course.load_course_approved(self.root, now=clock('08:10:00')())
        self.assertFalse(bundle.metadata['production_eligible'])
        self.assertEqual(bundle.metadata['readiness'], 'research_assumption')
        self.assertEqual(bundle.metadata['fit_cutoff'], clock('07:21:00')().isoformat())
        self.assertFalse(descriptor['historical_vintage_verified'])
        self.assertEqual(descriptor['deployment_policy'], 'course-benchmark-v1')
        self.assertFalse((self.root / 'approved.json').exists())

    def test_backup_train_reuses_same_data_without_fitting(self):
        def forbidden(*args):
            raise AssertionError('duplicate fixed fit')
        result = course.run_course_benchmark(self.root, 'train', client=Client(),
                clock=clock('07:35:00'), train_worker=forbidden)
        self.assertEqual(result['reason'], 'same_inputs_already_trained')

    def test_identical_redownload_preserves_true_fetch_without_another_fit(self):
        descriptor, _ = course.load_course_approved(self.root)
        acquired = []
        for source in descriptor['source_snapshots']:
            with patch('finpred.data.snapshots.datetime') as fixed:
                fixed.now.return_value = clock('07:30:00')()
                acquired.append(snapshot_bytes(Path(source['payload_path']).read_bytes(), self.root / 'raw',
                        source['source'], source['source_url'], '.zip', {'tls_verified': True}))
        index(self.root, acquired)
        with patch.object(course, 'bounded_training', side_effect=AssertionError('unexpected fit')):
            result = course.run_course_benchmark(self.root, 'train', client=Client(),
                    clock=clock('07:35:00'), train_worker=lambda *args: self.fail('duplicate fit'))
        self.assertEqual(result['reason'], 'same_inputs_already_trained')
        retained, _ = course.load_course_approved(self.root)
        self.assertEqual(retained['approved_at'], descriptor['approved_at'])

    def test_prediction_dryrun_actual_submission_receipt_and_no_duplicate(self):
        client = Client()
        predicted = course.run_course_benchmark(self.root, 'predict', client=client, clock=clock('08:13:00'))
        self.assertEqual(predicted['prediction_count'], 50)
        self.assertFalse(predicted['historical_vintage_verified'])
        dry = course.run_course_benchmark(self.root, 'submit', client=client, clock=clock('08:20:00'))
        self.assertTrue(dry['would_submit'])
        self.assertEqual(client.posts, 0)
        result = course.run_course_benchmark(self.root, 'submit', client=client,
                clock=clock('08:20:00'), dry_run=False)
        self.assertEqual(result['status'], 'verified')
        course.run_course_benchmark(self.root, 'submit', client=client,
                clock=clock('08:20:00'), dry_run=False)
        self.assertEqual(client.posts, 1)
        receipt = course.run_course_benchmark(self.root, 'verify', client=client, clock=clock('08:35:00'))
        self.assertEqual(receipt['status'], 'verified')

    def test_changed_training_table_invalidates_approval(self):
        descriptor = json.loads(course._pointer(self.root).read_bytes())
        registration = json.loads((Path(descriptor['model_path']).parent / 'registration.json').read_bytes())
        path = Path(registration['training_table_path'])
        saved = path.read_bytes()
        try:
            value = json.loads(saved)
            value['rows'][0]['stock_prev_rsi'] = 999
            path.write_text(json.dumps(value))
            with self.assertRaises(PipelineBlocked):
                course.load_course_approved(self.root)
        finally:
            path.write_bytes(saved)

    def test_changed_policy_and_nan_score_are_rejected(self):
        pointer = course._pointer(self.root)
        saved = pointer.read_bytes()
        descriptor = json.loads(saved)
        try:
            descriptor['historical_vintage_verified'] = True
            pointer.write_text(json.dumps(descriptor))
            with self.assertRaises(PipelineBlocked):
                course.load_course_approved(self.root)
        finally:
            pointer.write_bytes(saved)
        report_path = Path(descriptor['model_path']).parent / 'candidate_report.json'
        report_saved = report_path.read_bytes()
        try:
            report = json.loads(report_saved)
            report['candidate_score'] = float('nan')
            report_path.write_text(json.dumps(report))
            with self.assertRaises(PipelineBlocked):
                course.load_course_approved(self.root)
        finally:
            report_path.write_bytes(report_saved)

    def test_late_initializer_does_not_backdate_to_morning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            acquire_sources(root)
            result = course.run_course_benchmark(root, 'train', initialize=True,
                    clock=clock('14:00:00'), train_worker=worker)
            self.assertEqual(result['fit_cutoff'], clock('14:00:00')().isoformat())
            # Even asking with the earlier clock cannot relabel this approval.
            with self.assertRaises(PipelineBlocked):
                course.run_course_benchmark(root, 'predict', client=Client(), clock=clock('08:13:00'))

    def test_baseline_winner_gets_named_dummy_bundle_without_editing_linear(self):
        def baseline_wins(table, destination, kwargs, timeout):
            result = worker(table, destination, kwargs, timeout)
            # Deliberately controlled scores exercise the fixed selector; they
            # are not asserted as measured validation/model performance.
            result['report'].update(candidate_score=0.0, incumbent_score=1.0, candidate_improved=False)
            course._json(destination / 'candidate_report.json', result['report'])
            return result
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            acquire_sources(root)
            result = course.run_course_benchmark(root, 'train', client=Client(),
                    clock=clock('07:21:00'), train_worker=baseline_wins)
            self.assertEqual(result['selected_model'], 'train_majority')
            descriptor, bundle = course.load_course_approved(root)
            self.assertEqual(bundle.metadata['family'], 'dummy_majority')
            self.assertEqual(bundle.metadata['objective'], 'classification')
            self.assertFalse(bundle.metadata['production_eligible'])
            self.assertTrue((Path(descriptor['model_path']).parent / 'model/model.joblib').exists())

    def test_hard_deadline_and_unknown_post_never_retry(self):
        with self.assertRaises(PipelineBlocked):
            course.run_course_benchmark(self.root, 'submit', client=Client(), clock=clock('09:00:00'))
        client = Client()
        client.unknown = True
        course.run_course_benchmark(self.root, 'predict', client=client, clock=clock('08:13:01'))
        ledger = self.root / 'submission' / DAY / 'latest.json'
        saved = ledger.read_bytes() if ledger.exists() else None
        ledger.unlink(missing_ok=True)
        try:
            with self.assertRaises(SubmissionError):
                course.run_course_benchmark(self.root, 'submit', client=client,
                        clock=clock('08:20:00'), dry_run=False)
            with self.assertRaises(SubmissionError):
                course.run_course_benchmark(self.root, 'submit', client=client,
                        clock=clock('08:20:01'), dry_run=False)
            self.assertEqual(client.posts, 1)
        finally:
            if saved is None:
                ledger.unlink(missing_ok=True)
            else:
                ledger.write_bytes(saved)


if __name__ == '__main__':
    unittest.main()
