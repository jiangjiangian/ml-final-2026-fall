"""Course-policy hosted publication, deadline rollback and safe stage routing."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))
spec = importlib.util.spec_from_file_location('hosted_course_test_subject', PROJECT / 'scripts/run_hosted_course.py')
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


def moment(clock='07:21:00'):
    return datetime.fromisoformat('2026-11-04T' + clock + '+08:00')


class HostedCourseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.data, self.runtime = self.base / 'data', self.base / 'runtime'
        self.data.mkdir(mode=0o700)
        self.store = Mock()
        self.store.parent = 'a' * 40
        self.store.publish.return_value = 'b' * 40
        self.client = Mock(post_attempted=False)
        self.collector = Mock(return_value={'status': 'collected', 'failures': []})
        self.importer = patch.object(hosted, 'import_snapshot_bundle', return_value={
            'status': 'imported', 'git_revision': 'a' * 40})
        self.restorer = patch.object(hosted, 'restore_runtime', return_value={'status': 'restored'})
        self.packer = patch.object(hosted, 'pack_runtime')
        self.exporter = patch.object(hosted, 'export_snapshot_bundle')
        self.features = patch('finpred.data.shared_features.build_shared_features',
                              return_value={'status': 'exported'})
        self.importer.start()
        self.restorer.start()
        self.checkpoint = self.packer.start()
        self.exporter.start()
        self.features.start()
        self.addCleanup(self.importer.stop)
        self.addCleanup(self.restorer.stop)
        self.addCleanup(self.packer.stop)
        self.addCleanup(self.exporter.stop)
        self.addCleanup(self.features.stop)

    def run_hosted(self, mode='rehearsal', runner=None, clock=None, **options):
        return hosted.run_hosted_course(
            self.data, 'owner/repo', mode=mode, runtime_root=self.runtime,
            store_factory=lambda *args, **kwargs: self.store,
            client_factory=lambda *args: self.client, stage_runner=runner,
            clock=clock or (lambda: moment()), collector=self.collector, **options)

    def create_pointer(self, value=b'{"model":"first"}\n'):
        target = hosted._pointer(self.runtime)
        hosted.write_private(target, value)
        return target

    def approve(self, *, initialize=False, clock=None):
        def runner(*args, **kwargs):
            self.create_pointer()
            return {'status': 'course_model_approved'}
        return self.run_hosted('initialize' if initialize else 'train', runner,
                               clock=clock or (lambda: moment()))

    def test_rehearsal_has_no_authentication_fit_lease_or_git_publication(self):
        runner = Mock()
        result = self.run_hosted(runner=runner)
        self.assertEqual(result['status'], 'course_rehearsal_passed')
        self.assertFalse(result['prediction_posted'])
        self.assertFalse(result['historical_vintage_verified'])
        runner.assert_not_called()
        self.client.login.assert_not_called()
        self.store.acquire.assert_not_called()
        self.store.publish.assert_not_called()
        self.store.release.assert_not_called()
        self.checkpoint.assert_not_called()
        self.collector.assert_not_called()

    def test_approval_requires_remote_commit_then_hash_bound_publication(self):
        result = self.approve()
        marker = hosted.verify_hosted_approval(self.runtime)
        self.assertEqual(marker['published_commit'], 'b' * 40)
        self.assertEqual(marker['deadline'], moment('07:50:00').isoformat())
        self.assertFalse(marker['initialize'])
        self.assertFalse(result['prediction_posted'])
        self.store.publish.assert_called_once()
        self.store.release.assert_called_once()
        self.assertEqual(self.checkpoint.call_count, 2)

    def test_late_remote_publication_rolls_back_existing_pointer_and_blocks(self):
        self.approve()
        previous = hosted._pointer(self.runtime).read_bytes()
        def changed(*args, **kwargs):
            self.create_pointer(b'{"model":"late"}\n')
            return {'status': 'course_model_approved'}
        with self.assertRaisesRegex(hosted.HostedBlocked, 'publication deadline'):
            self.run_hosted('train', changed, clock=Mock(side_effect=[moment('07:49:00')] * 3 + [moment('07:50:00')]))
        self.assertEqual(hosted._pointer(self.runtime).read_bytes(), previous)
        hosted.verify_hosted_approval(self.runtime)

    def test_late_first_approval_removes_pointer_without_marking_ready(self):
        with self.assertRaisesRegex(hosted.HostedBlocked, 'publication deadline'):
            self.approve(clock=Mock(side_effect=[moment('07:49:00')] * 3 + [moment('07:50:00')]))
        self.assertFalse(hosted._pointer(self.runtime).exists())
        self.assertFalse(hosted._publication_marker(self.runtime).exists())

    def test_publish_failure_rolls_back_before_release(self):
        self.approve()
        previous = hosted._pointer(self.runtime).read_bytes()
        self.store.publish.side_effect = hosted.HostedBlocked('injected Git failure')
        def changed(*args, **kwargs):
            self.create_pointer(b'{"model":"not-published"}\n')
            return {'status': 'course_model_approved'}
        with self.assertRaises(hosted.HostedBlocked):
            self.run_hosted('train', changed)
        self.assertEqual(hosted._pointer(self.runtime).read_bytes(), previous)

    def test_initialize_records_real_later_time_without_retroactive_training_deadline(self):
        result = self.approve(initialize=True, clock=lambda: moment('12:00:00'))
        marker = hosted.verify_hosted_approval(self.runtime)
        self.assertTrue(marker['initialize'])
        self.assertIsNone(marker['deadline'])
        self.assertEqual(marker['published_at'], moment('12:00:00').isoformat())
        self.assertFalse(result['historical_vintage_verified'])

    def test_existing_pointer_without_matching_publication_blocks_predict_and_post(self):
        self.runtime.mkdir(mode=0o700)
        self.create_pointer()
        runner = Mock()
        for mode in ('predict', 'submit', 'verify'):
            with self.subTest(mode=mode), self.assertRaises((hosted.HostedBlocked, FileNotFoundError)):
                self.run_hosted(mode, runner)
        runner.assert_not_called()
        self.client.login.assert_not_called()

    def test_pointer_changed_after_publication_is_rejected(self):
        self.approve()
        self.create_pointer(b'{"model":"different"}\n')
        with self.assertRaisesRegex(hosted.HostedBlocked, 'matching durable'):
            hosted.verify_hosted_approval(self.runtime)

    def test_tampered_publication_time_or_commit_is_rejected(self):
        self.approve()
        marker_path = hosted._publication_marker(self.runtime)
        original = json.loads(marker_path.read_bytes())
        for changed in ({'published_at': moment('07:50:00').isoformat()},
                        {'published_commit': 'not-a-commit'}, {'hosted_persistence_eligible': False}):
            with self.subTest(changed=changed):
                hosted.write_json(marker_path, {**original, **changed})
                with self.assertRaises(hosted.HostedBlocked):
                    hosted.verify_hosted_approval(self.runtime)

    def test_retained_model_does_not_publish_a_second_approval(self):
        self.approve()
        self.store.publish.reset_mock()
        runner = Mock(return_value={'status': 'course_model_retained'})
        result = self.run_hosted('train', runner)
        self.assertEqual(result['status'], 'course_model_retained')
        self.store.publish.assert_not_called()

    def test_retained_valid_model_repairs_missing_mismatched_or_malformed_marker_without_fit(self):
        self.approve()
        original_pointer = hosted._pointer(self.runtime).read_bytes()
        original_marker = hosted._publication_marker(self.runtime).read_bytes()
        for failure in ('missing', 'mismatched', 'malformed'):
            with self.subTest(failure=failure):
                hosted.write_private(hosted._pointer(self.runtime), original_pointer)
                hosted.write_private(hosted._publication_marker(self.runtime), original_marker)
                if failure == 'missing':
                    hosted._publication_marker(self.runtime).unlink()
                elif failure == 'mismatched':
                    self.create_pointer(b'{"model":"published-before-crash"}\n')
                else:
                    hosted.write_private(hosted._publication_marker(self.runtime), b'not-json\n')
                self.store.publish.reset_mock()
                runner = Mock(return_value={'status': 'course_model_retained'})
                with patch('finpred.pipelines.course_benchmark.load_course_approved') as validate:
                    result = self.run_hosted('train', runner)
                validate.assert_called_once_with(self.runtime, now=moment())
                runner.assert_called_once()
                self.store.publish.assert_called_once()
                self.assertEqual(result['status'], 'course_model_retained')
                marker = hosted.verify_hosted_approval(self.runtime)
                self.assertEqual(marker['published_at'], moment().isoformat())
                self.assertFalse(marker['initialize'])

    def test_marker_recovery_rejects_invalid_local_model_without_publication(self):
        self.approve()
        self.create_pointer(b'{"model":"invalid-chain"}\n')
        marker_before = hosted._publication_marker(self.runtime).read_bytes()
        self.store.publish.reset_mock()
        runner = Mock(return_value={'status': 'course_model_retained'})
        with patch('finpred.pipelines.course_benchmark.load_course_approved',
                   side_effect=ValueError('invalid model chain')):
            with self.assertRaisesRegex(ValueError, 'invalid model chain'):
                self.run_hosted('train', runner)
        self.store.publish.assert_not_called()
        self.assertEqual(hosted._publication_marker(self.runtime).read_bytes(), marker_before)

    def test_marker_recovery_cannot_publish_after_the_original_daily_deadline(self):
        self.approve()
        self.create_pointer(b'{"model":"published-before-crash"}\n')
        pointer_before = hosted._pointer(self.runtime).read_bytes()
        marker_before = hosted._publication_marker(self.runtime).read_bytes()
        self.store.publish.reset_mock()
        runner = Mock(return_value={'status': 'course_model_retained'})
        clock = Mock(side_effect=[moment('07:49:00')] * 3 + [moment('07:50:00')])
        with patch('finpred.pipelines.course_benchmark.load_course_approved') as validate:
            with self.assertRaisesRegex(hosted.HostedBlocked, 'recovery missed publication deadline'):
                self.run_hosted('train', runner, clock=clock)
        validate.assert_not_called()
        self.store.publish.assert_not_called()
        self.assertEqual(hosted._pointer(self.runtime).read_bytes(), pointer_before)
        self.assertEqual(hosted._publication_marker(self.runtime).read_bytes(), marker_before)

    def test_explicit_initializer_repairs_marker_at_its_actual_afternoon_time(self):
        self.approve()
        self.create_pointer(b'{"model":"published-before-crash"}\n')
        runner = Mock(return_value={'status': 'course_model_retained'})
        with patch('finpred.pipelines.course_benchmark.load_course_approved') as validate:
            self.run_hosted('initialize', runner, clock=lambda: moment('13:10:00'))
        validate.assert_called_once_with(self.runtime, now=moment('13:10:00'))
        marker = hosted.verify_hosted_approval(self.runtime)
        self.assertEqual(marker['published_at'], moment('13:10:00').isoformat())
        self.assertTrue(marker['initialize'])
        self.assertIsNone(marker['deadline'])

    def test_submission_release_and_stage_scope_are_required(self):
        runner = Mock()
        with patch.dict(os.environ, {'FINPRED_SUBMISSION_RELEASED': 'false'}):
            with self.assertRaisesRegex(hosted.HostedBlocked, 'release gate'):
                self.run_hosted('submit', runner, submit=True)
        with self.assertRaisesRegex(hosted.HostedBlocked, 'submit stage'):
            self.run_hosted('predict', runner, submit=True)
        runner.assert_not_called()

    def test_current_receipt_is_verified_without_claiming_new_post(self):
        self.approve()
        runner = Mock(return_value={'status': 'verified'})
        result = self.run_hosted('verify', runner)
        self.assertTrue(result['receipt_verified'])
        self.assertFalse(result['prediction_post_attempted'])
        self.assertFalse(result['prediction_posted'])

    def test_blocked_stage_still_checkpoints_and_releases_without_exception_text(self):
        self.approve()
        self.checkpoint.reset_mock()
        self.store.release.reset_mock()
        with self.assertRaisesRegex(ValueError, 'injected'):
            self.run_hosted('predict', Mock(side_effect=ValueError('injected')))
        self.checkpoint.assert_called_once()
        self.store.release.assert_called_once()

    def test_known_schedule_keeps_its_stage_unknown_never_runs(self):
        binary = self.base / 'python'
        captured = self.base / 'arguments.txt'
        binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_ARGUMENTS"\n')
        binary.chmod(0o700)
        env = dict(os.environ, PATH=str(self.base) + os.pathsep + os.environ.get('PATH', ''),
                   FINPRED_DATA_ROOT=str(self.data), FINPRED_DATA_REPOSITORY='owner/repo',
                   FINPRED_ALLOW_PUBLIC_DATA='true', FINPRED_EVENT_NAME='schedule',
                   FINPRED_COURSE_MODE='initialize', FINPRED_SUBMISSION_RELEASED='true',
                   CAPTURE_ARGUMENTS=str(captured))
        for schedule, mode in (('20 23 * * *', 'train'), ('35 23 * * *', 'train'),
                               ('10 0 * * *', 'predict'), ('14 0 * * *', 'predict'),
                               ('20 0 * * *', 'submit'), ('27 0 * * *', 'submit'),
                               ('35 0 * * *', 'verify'), ('42 0 * * *', 'verify'), ('unknown', None)):
            with self.subTest(schedule=schedule):
                captured.unlink(missing_ok=True)
                result = subprocess.run(['bash', str(PROJECT / 'deployment/hosted/run-course.sh')],
                                        env={**env, 'FINPRED_SCHEDULE': schedule}, capture_output=True)
                if mode is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(captured.exists())
                else:
                    self.assertEqual(result.returncode, 0)
                    arguments = captured.read_text().splitlines()
                    self.assertEqual(arguments[arguments.index('--mode') + 1], mode)
                    self.assertEqual('--submit' in arguments, mode == 'submit')
                    self.assertIn('--allow-public-data', arguments)


if __name__ == '__main__':
    unittest.main()
