"""Exercise research-only hosted training, prediction, persistence and isolation."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from finpred.pipelines.daily import PipelineBlocked
from test_daily_pipeline import canonical_prediction_table
from test_shadow_forecast import DAY, moment

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))
import runtime_store as store_module  # noqa: E402

spec = importlib.util.spec_from_file_location('hosted_shadow_subject', PROJECT / 'scripts/run_hosted_shadow.py')
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


class HostedShadowTests(unittest.TestCase):
    def setUp(self):
        # GitHub runners use 022; do not let this workspace's restrictive umask
        # hide unsafe intermediate directories created by parents=True.
        self.addCleanup(os.umask, os.umask(0o022))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'runtime'
        self.root.mkdir(mode=0o700)
        self.data = Path(self.temporary.name) / 'data'
        self.data.mkdir()
        self.table = canonical_prediction_table(self.root, prior_close=9)

    def train(self):
        result = hosted.train_research(self.root, DAY, clock=lambda: moment('07:25:00'))
        self.assertEqual(result['status'], 'research_model_fitted')
        return result

    def client(self, *, official_day=True):
        client = Mock()
        client.state.return_value = {
            'phase2Days': [{'tradingDate': DAY, 'enabled': True,
                            'openAt': DAY + 'T04:00:00+08:00',
                            'deadline': DAY + 'T09:00:00+08:00'}] if official_day else [],
            'user': {'email': 'never-persist-account@example.invalid'},
            'token': 'never-persist-session-token',
        }
        client.daily_template.return_value = (
            'id,' + DAY + '\n' + ''.join(row['stock_id'] + ',0\n' for row in self.table['rows'])).encode()
        client.post_predictions.side_effect = AssertionError('prediction POST forbidden')
        return client

    def test_actual_single_fit_stays_research_and_can_make_isolated_prediction(self):
        result = self.train()
        model = json.loads((Path(result['model_path']) / 'manifest.json').read_bytes())
        self.assertEqual(model['train_rows'], 150)
        self.assertLess(model['train_end_date'], DAY)
        self.assertEqual(model['readiness'], 'research_assumption')
        self.assertFalse(model['production_eligible'])
        client = self.client()
        with patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected network')):
            prediction = hosted.predict_shadow(self.root, DAY, clock=lambda: moment('08:11:00'),
                                               client_factory=lambda: client)
        self.assertEqual(prediction['status'], 'prospective_shadow')
        self.assertTrue((Path(prediction['directory']) / 'completion.json').is_file())
        client.post_predictions.assert_not_called()
        client.close.assert_called_once()
        for name in ('approved.json', 'predictions', 'submission', 'verified'):
            self.assertFalse((self.root / name).exists())
        archive = store_module.pack_runtime(self.root, self.data)
        self.assertTrue(any(item['path'].startswith('shadow/') for item in archive['files']))
        for path in self.root.glob('shadow/**/*.json'):
            self.assertNotIn('never-persist-', path.read_text())
        kept = Path(prediction['directory']) / 'prediction.csv'
        before = kept.read_bytes()
        kept.unlink()
        store_module.restore_runtime(self.data, self.root)
        self.assertEqual(kept.read_bytes(), before)

    def test_missing_official_session_is_not_fabricated_and_never_posts(self):
        self.train()
        client = self.client(official_day=False)
        with self.assertRaisesRegex(ValueError, 'official session'):
            hosted.predict_shadow(self.root, DAY, clock=lambda: moment('08:11:00'),
                                   client_factory=lambda: client)
        client.post_predictions.assert_not_called()
        client.daily_template.assert_not_called()
        self.assertFalse(list(self.root.glob('shadow/**/completion.json')))
        client.close.assert_called_once()

    def test_pointer_cannot_escape_shadow_model_store_using_parent_segments(self):
        trained = self.train()
        outside = self.root / 'candidates/other-model'
        shutil.copytree(trained['model_path'], outside)
        pointer_path = self.root / 'shadow/model-latest.json'
        pointer = json.loads(pointer_path.read_bytes())
        pointer['model_path'] = str(self.root / 'shadow/models/../../candidates/other-model')
        store_module.write_json(pointer_path, pointer)
        factory = Mock(side_effect=AssertionError('must reject before login'))
        with self.assertRaisesRegex(PipelineBlocked, 'internally created'):
            hosted.predict_shadow(self.root, DAY, clock=lambda: moment('08:11:00'), client_factory=factory)
        factory.assert_not_called()

    def test_late_training_never_updates_model_pointer(self):
        with patch.object(hosted, 'prepare_training_table') as prepare:
            with self.assertRaises(PipelineBlocked):
                hosted.train_research(self.root, DAY, clock=lambda: moment('07:19:59'))
            prepare.assert_not_called()
        current = [moment('07:25:00')]

        def late_fit(*args):
            current[0] = moment('07:50:00')
            return {'status': 'fitted'}

        with self.assertRaisesRegex(PipelineBlocked, 'deadline'):
            hosted.train_research(self.root, DAY, clock=lambda: current[0], fit_worker=late_fit)
        self.assertFalse((self.root / 'shadow/model-latest.json').exists())
        self.assertFalse((self.root / 'approved.json').exists())
        self.assertEqual(hosted.bounded_research_fit({}, self.root / 'unused', '', 0)['status'], 'timeout')

    def test_rehearsal_restores_without_lease_login_or_training(self):
        store = SimpleNamespace(parent='a' * 40, acquire=Mock(), publish=Mock(), release=Mock())
        with patch.object(hosted, 'import_snapshot_bundle', return_value={'status': 'imported'}) as imported, patch.object(
            hosted, 'restore_runtime', return_value={'status': 'no_prior_runtime_state', 'files': 0}
        ), patch.object(hosted, 'CourseSubmissionClient', side_effect=AssertionError('login forbidden')), patch.object(
            hosted, 'train_research', side_effect=AssertionError('fit forbidden')
        ):
            factory = Mock(return_value=store)
            result = hosted.run_hosted_shadow(self.data, 'team/public', runtime_root=self.root,
                                              allow_public_data=True, store_factory=factory)
        self.assertEqual(result['status'], 'shadow_rehearsal_passed')
        factory.assert_called_once_with(self.data, 'team/public', allow_public_data=True)
        imported.assert_called_once_with(self.data, self.root, revision='a' * 40)
        store.acquire.assert_not_called()
        store.publish.assert_not_called()
        store.release.assert_not_called()
        self.assertFalse(result['submitted'])

    def test_training_pointer_crossing_deadline_restores_previous_model(self):
        previous = self.train()
        pointer_path = self.root / 'shadow/model-latest.json'
        previous_bytes = pointer_path.read_bytes()
        current = [moment('07:49:59')]
        original_write = hosted.write_json

        def slow_write(path, value):
            original_write(path, value)
            if Path(path) == pointer_path:
                current[0] = moment('07:50:00')

        with patch.object(hosted, 'write_json', side_effect=slow_write):
            with self.assertRaisesRegex(PipelineBlocked, 'pointer missed'):
                hosted.train_research(self.root, DAY, clock=lambda: current[0])
        self.assertEqual(pointer_path.read_bytes(), previous_bytes)
        self.assertEqual(json.loads(pointer_path.read_bytes())['model_path'], previous['model_path'])

    def test_remote_publication_deadline_is_separate_from_local_completion(self):
        for late in (False, True):
            with self.subTest(late=late), tempfile.TemporaryDirectory() as temporary:
                root, data = Path(temporary) / 'runtime', Path(temporary) / 'data'
                root.mkdir(mode=0o700)
                data.mkdir()
                directory = root / 'shadow' / DAY / 'identity'
                directory.mkdir(parents=True, mode=0o700)
                store_module.write_json(directory / 'manifest.json', {'deadline': DAY + 'T09:00:00+08:00'})
                current = [moment('08:11:00')]
                store = SimpleNamespace(parent='a' * 40, acquire=Mock(), publish=Mock(), release=Mock())

                def publish(reason):
                    current[0] = moment('09:00:00' if late else '08:12:00')
                    return 'b' * 40

                store.publish.side_effect = publish
                forecast = {'status': 'prospective_shadow', 'directory': str(directory), 'csv_sha256': 'c' * 64}
                with patch.object(hosted, 'import_snapshot_bundle', return_value={
                    'status': 'imported', 'git_revision': 'a' * 40
                }), patch.object(hosted, 'restore_runtime', return_value={}), patch.object(
                    hosted, 'predict_shadow', return_value=forecast
                ):
                    result = hosted.run_hosted_shadow(
                        data, 'team/public', mode='predict', runtime_root=root, target_date=DAY,
                        allow_public_data=True, clock=lambda: current[0], store_factory=lambda *a, **k: store)
                self.assertEqual(result['source_revision'], 'a' * 40)
                self.assertEqual(result['hosted_persistence_before_deadline'], not late)
                self.assertEqual(result['status'], 'shadow_hosted_persistence_missed_deadline' if late
                                 else 'prospective_shadow')
                store.acquire.assert_called_once()
                store.release.assert_called_once()
                self.assertFalse(result['submitted'])

    def test_shadow_archive_retains_existing_credential_rejection(self):
        store_module.write_json(self.root / 'shadow/unsafe.json', {'cookie': 'never-export'})
        with self.assertRaises(store_module.HostedBlocked):
            store_module.pack_runtime(self.root, self.data)

    def test_shell_schedules_cannot_turn_into_another_stage_or_submit(self):
        binary = Path(self.temporary.name) / 'python'
        capture = Path(self.temporary.name) / 'args.json'
        binary.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                          'open(os.environ["SHADOW_TEST_CAPTURE"],"w").write(json.dumps(sys.argv[1:]))\n')
        binary.chmod(0o700)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('FINPRED_', 'GITHUB_', 'COURSE_'))}
        environment.update(PATH=str(binary.parent) + os.pathsep + os.environ.get('PATH', ''),
                           FINPRED_DATA_ROOT=str(self.data), FINPRED_DATA_REPOSITORY='team/public',
                           FINPRED_EVENT_NAME='schedule', FINPRED_SHADOW_MODE='predict',
                           SHADOW_TEST_CAPTURE=str(capture), FINPRED_ALLOW_PUBLIC_DATA='true')
        for schedule, expected in (('25 23 * * *', 'train'), ('13 0 * * *', 'predict'), ('unknown', None)):
            with self.subTest(schedule=schedule):
                capture.unlink(missing_ok=True)
                result = subprocess.run(['bash', str(PROJECT / 'deployment/hosted/run-shadow.sh')],
                                        env={**environment, 'FINPRED_SCHEDULE': schedule},
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, expected is not None)
                if expected is not None:
                    args = json.loads(capture.read_bytes())
                    self.assertEqual(args[args.index('--mode') + 1], expected)
                    self.assertIn('--allow-public-data', args)
                    self.assertNotIn('--submit', args)
                else:
                    self.assertFalse(capture.exists())


if __name__ == '__main__':
    unittest.main()
