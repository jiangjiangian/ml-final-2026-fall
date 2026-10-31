"""Hosted durability, isolated state and real-clock guard invariants."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))
import runtime_store as store_module  # noqa: E402

spec = importlib.util.spec_from_file_location('hosted_pipeline_test_subject', PROJECT / 'scripts/run_hosted_pipeline.py')
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.runtime, self.data = self.base / 'runtime', self.base / 'data'
        self.runtime.mkdir()
        self.data.mkdir()

    def put(self, name, payload=b'bounded output'):
        path = self.runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_only_whitelisted_state_and_permissions_round_trip(self):
        kept = self.put('predictions/day/latest.json', b'{"status":"pending"}')
        self.put('raw/secret-source.bin', b'not part of state archive')
        self.put('runtime.env', b'not part of state archive')
        self.put('submission/day/submission.lock', b'local lock excluded')
        record = store_module.pack_runtime(self.runtime, self.data)
        self.assertEqual([f['path'] for f in record['files']], ['predictions/day/latest.json'])
        kept.unlink()
        result = store_module.restore_runtime(self.data, self.runtime)
        self.assertEqual(result['files'], 1)
        self.assertEqual(kept.read_bytes(), b'{"status":"pending"}')
        self.assertEqual(kept.stat().st_mode & 0o777, 0o600)

    def test_validate_all_hashes_before_restoring_any_member(self):
        a, b = self.put('runs/a.json', b'aaa'), self.put('runs/b.json', b'bbb')
        record = store_module.pack_runtime(self.runtime, self.data)
        (self.data / record['files'][1]['object_key']).write_bytes(b'corrupt')
        a.unlink()
        b.unlink()
        with self.assertRaises(store_module.HostedBlocked):
            store_module.restore_runtime(self.data, self.runtime)
        self.assertFalse(a.exists())
        self.assertFalse(b.exists())

    def test_no_silent_absolute_path_rebasing(self):
        self.put('approved.json', b'{}')
        store_module.pack_runtime(self.runtime, self.data)
        with self.assertRaises(store_module.HostedBlocked):
            store_module.restore_runtime(self.data, self.base / 'different-runtime')

    def test_traversal_and_duplicate_archive_paths_rejected(self):
        self.put('runs/a.json')
        record = store_module.pack_runtime(self.runtime, self.data)
        original = record['files'][0]
        for names in [['../outside'], ['/tmp/outside'], ['runs/a.json', 'runs/a.json']]:
            with self.subTest(names=names):
                record['files'] = [{**original, 'path': name} for name in names]
                store_module.write_json(self.data / 'runtime/state.json', record)
                with self.assertRaises(store_module.HostedBlocked):
                    store_module.restore_runtime(self.data, self.runtime)

    def test_symbolic_paths_and_fifo_rejected_without_reading(self):
        outside = self.base / 'outside'
        outside.write_bytes(b'data')
        (self.runtime / 'approved.json').symlink_to(outside)
        with self.assertRaises(store_module.HostedBlocked):
            store_module.pack_runtime(self.runtime, self.data)
        (self.runtime / 'approved.json').unlink()
        os.mkfifo(self.runtime / 'approved.json')
        with self.assertRaises(store_module.HostedBlocked):
            store_module.pack_runtime(self.runtime, self.data)

    def test_active_credentials_and_credential_filenames_never_pack(self):
        target = self.put('runs/a.json', b'{"detail":"private-test-secret-123"}')
        with patch.dict(os.environ, {'COURSE_PASSWORD': 'private-test-secret-123'}):
            with self.assertRaises(store_module.HostedBlocked):
                store_module.pack_runtime(self.runtime, self.data)
        target.unlink()
        self.put('candidates/model/cookies.json', b'{}')
        with self.assertRaises(store_module.HostedBlocked):
            store_module.pack_runtime(self.runtime, self.data)

    def test_conflicting_local_state_is_not_overwritten(self):
        target = self.put('submission/day/latest.json', b'{"status":"post_in_flight"}')
        store_module.pack_runtime(self.runtime, self.data)
        target.write_bytes(b'{"status":"unverified"}')
        with self.assertRaises(store_module.HostedBlocked):
            store_module.restore_runtime(self.data, self.runtime)
        self.assertIn(b'unverified', target.read_bytes())


class GitStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.remote, self.local = self.base / 'remote.git', self.base / 'local'
        self.command('git', 'init', '--bare', '-q', str(self.remote))
        self.command('git', 'clone', '-q', str(self.remote), str(self.local))
        self.command('git', '-C', str(self.local), 'checkout', '-q', '-b', 'live-data')
        (self.local / 'README.md').write_text('Private snapshot fixture\n')
        self.command('git', '-C', str(self.local), 'add', 'README.md')
        self.command('git', '-C', str(self.local), '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                     'commit', '-q', '-m', 'seed')
        self.command('git', '-C', str(self.local), 'push', '-q', 'origin', 'live-data')
        self.clock = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)

    @staticmethod
    def command(*args):
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()

    def store(self, path=None, **kwargs):
        return store_module.PrivateGitStore(path or self.local, 'owner/private-repo',
                  privacy_check=lambda: True, origin_check=lambda: True,
                  clock=lambda: self.clock, **kwargs)

    def clone_other(self):
        other = self.base / 'other'
        self.command('git', 'clone', '-q', '--branch', 'live-data', str(self.remote), str(other))
        return other

    def test_private_and_origin_checks_precede_any_publication(self):
        with self.assertRaises(store_module.HostedBlocked):
            store_module.PrivateGitStore(self.local, 'owner/private-repo', privacy_check=lambda: False)
        with self.assertRaises(store_module.HostedBlocked):
            store_module.PrivateGitStore(self.local, 'owner/private-repo', privacy_check=lambda: True)

    def test_lease_is_published_and_blocks_a_second_writer(self):
        first = self.store(owner='first')
        original = first.parent
        first.acquire()
        self.assertNotEqual(first.parent, original)
        first.assert_lease()
        second = self.store(self.clone_other(), owner='second')
        with self.assertRaises(store_module.HostedBlocked):
            second.acquire()
        first.release()
        self.assertFalse(json.loads((self.local / 'runtime/lease.json').read_text())['active'])

    def test_stale_parent_and_expired_owner_cannot_publish_or_post(self):
        first = self.store(owner='first')
        first.acquire()
        second = self.store(self.clone_other(), owner='second')
        self.clock += timedelta(minutes=46)
        with self.assertRaises(store_module.HostedBlocked):
            first.assert_lease()
        second.acquire()
        with self.assertRaises(store_module.HostedBlocked):
            first.publish('must not force or retry')

    def test_github_identity_strips_auth_without_accepting_other_hosts(self):
        self.assertEqual(store_module.github_origin_identity('https://secret@github.com/Owner/Repo.git'), 'owner/repo')
        self.assertEqual(store_module.github_origin_identity('git@github.com:Owner/Repo.git'), 'owner/repo')
        for value in ['https://github.com.evil.test/owner/repo', 'file:///tmp/repo', 'https://github.com/a/b/c']:
            with self.assertRaises(store_module.HostedBlocked):
                store_module.github_origin_identity(value)


class HostedFlowTests(unittest.TestCase):
    def test_stage_windows_are_exact_and_delays_do_not_catch_up(self):
        for instant, expected in [('2026-11-01T23:20:00+00:00', 'train'),
                                  ('2026-11-02T00:10:00+00:00', 'predict'),
                                  ('2026-11-02T00:20:00+00:00', 'submit'),
                                  ('2026-11-02T00:35:00+00:00', 'verify')]:
            self.assertEqual(hosted.select_stage(datetime.fromisoformat(instant)), expected)
        for value in ['2026-11-01T23:50:00+00:00', '2026-11-02T01:00:00+00:00']:
            with self.assertRaises(store_module.HostedBlocked):
                hosted.select_stage(datetime.fromisoformat(value))

    def test_collection_failures_are_separate_and_credentials_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            record = {'source': 'good', 'sha256': 'a' * 64, 'fetched_at': '2026-10-31T00:00:00+00:00',
                      'manifest_path': str(Path(directory) / 'raw/good/manifests/a.json')}
            with patch('finpred.ingestion.course.download_course_sources', side_effect=ValueError('secret-body')):
                with patch('finpred.ingestion.external.download_external', return_value=record):
                    with patch('finpred.ingestion.market_history.download_market_history', return_value=record) as history:
                        with patch('finpred.ingestion.market_history.download_twse_sector_snapshot', return_value=record):
                            result = hosted.collect_raw(directory)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(len(result['failures']), 2)
            self.assertEqual(len(result['acquired']), 13)
            self.assertNotIn('secret-body', json.dumps(result))
            self.assertNotIn('manifest_path', json.dumps(result))
            current = json.loads((Path(directory) / 'latest_collection.json').read_text())
            self.assertEqual(current['status'], 'partial')
            self.assertEqual(current['failures'], result['failures'])
            self.assertEqual(history.call_count, 8)
            self.assertTrue(all(call.args[-1] == Path(directory) / 'raw' for call in history.call_args_list))

    def test_post_requires_durable_checkpoint_then_fresh_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            ledger = runtime / 'submission/2026-11-02/latest.json'
            ledger.parent.mkdir(parents=True)
            ledger.write_text('{"status":"post_in_flight"}')
            store = Mock(spec=store_module.PrivateGitStore, root=runtime / 'data')
            client = hosted.durable_submission_client(runtime, store)
            self.addCleanup(client.close)
            events = []
            with patch.object(hosted, 'pack_runtime', side_effect=lambda *a: events.append('checkpoint')):
                with patch.object(store, 'publish', side_effect=lambda *a: events.append('publish')):
                    with patch.object(client, 'state', return_value={'safe': True}):
                        with patch('finpred.submission.course._guard', side_effect=lambda *a: events.append('guard')):
                            with patch.object(store, 'assert_lease', side_effect=lambda: events.append('lease')):
                                with patch('finpred.submission.course.CourseSubmissionClient.post_predictions',
                                           side_effect=lambda *a: events.append('post')):
                                    client.post_predictions('2026-11-02', 'prediction.csv', {})
            self.assertEqual(events, ['checkpoint', 'publish', 'lease', 'guard', 'post'])

    def test_checkpoint_or_deadline_failure_never_posts(self):
        from finpred.submission.course import SubmissionError
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            ledger = runtime / 'submission/2026-11-02/latest.json'
            ledger.parent.mkdir(parents=True)
            ledger.write_text('{"status":"post_in_flight"}')
            store = Mock(spec=store_module.PrivateGitStore, root=runtime / 'data')
            client = hosted.durable_submission_client(runtime, store)
            self.addCleanup(client.close)
            with patch.object(hosted, 'pack_runtime', side_effect=RuntimeError('private-text')):
                with patch('finpred.submission.course.CourseSubmissionClient.post_predictions') as post:
                    with self.assertRaises(SubmissionError):
                        client.post_predictions('2026-11-02', 'prediction.csv', {})
                    post.assert_not_called()
            with patch.object(hosted, 'pack_runtime'):
                with patch.object(client, 'state', return_value={}):
                    with patch('finpred.submission.course._guard', side_effect=SubmissionError('deadline')):
                        with patch('finpred.submission.course.CourseSubmissionClient.post_predictions') as post:
                            with self.assertRaises(SubmissionError):
                                client.post_predictions('2026-11-02', 'prediction.csv', {})
                            post.assert_not_called()

    def test_rehearsal_only_reads_without_acquiring_or_collecting(self):
        with tempfile.TemporaryDirectory() as directory:
            data, runtime = Path(directory) / 'data', Path(directory) / 'runtime'
            store = Mock()
            store.parent = 'a' * 40
            with patch('finpred.data.sharing.import_snapshot_bundle', return_value={'sources': 16}):
                with patch.object(hosted, 'restore_runtime', return_value={'status': 'no_prior_runtime_state'}):
                    with patch.object(hosted, 'collect_raw') as collect:
                        result = hosted.run_hosted(data, 'owner/repo', runtime_root=runtime,
                                                   store_factory=lambda *a: store)
            self.assertEqual(result['status'], 'rehearsal_passed')
            collect.assert_not_called()
            store.acquire.assert_not_called()
            self.assertFalse(result['prediction_posted'])

    def test_feature_failure_does_not_prevent_raw_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            data, runtime = Path(directory) / 'data', Path(directory) / 'runtime'
            data.mkdir()
            store = Mock()
            store.parent = 'a' * 40
            module = types.ModuleType('finpred.data.shared_features')
            module.build_shared_features = Mock(side_effect=ValueError('unavailable research feature'))
            with patch.dict(sys.modules, {'finpred.data.shared_features': module}):
                with patch('finpred.data.sharing.import_snapshot_bundle'):
                    with patch.object(hosted, 'restore_runtime'):
                        with patch.object(hosted, 'collect_raw', return_value={'status': 'collected'}):
                            with patch('finpred.data.sharing.export_snapshot_bundle') as export:
                                with patch.object(hosted, 'pack_runtime') as checkpoint:
                                    result = hosted.run_hosted(data, 'owner/repo', mode='collect',
                                          runtime_root=runtime, store_factory=lambda *a: store)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['features']['status'], 'blocked')
            export.assert_called_once()
            store.publish.assert_called_once_with('Synchronize validated private source snapshots')
            checkpoint.assert_called_once()
            store.release.assert_called_once()

    def test_blocked_model_stage_still_persists_failure_state(self):
        from finpred.pipelines.daily import PipelineBlocked
        with tempfile.TemporaryDirectory() as directory:
            data, runtime = Path(directory) / 'data', Path(directory) / 'runtime'
            data.mkdir()
            store, client = Mock(), Mock()
            store.parent = 'a' * 40
            events = []
            store.release.side_effect = lambda: events.append('release')
            with patch('finpred.data.sharing.import_snapshot_bundle'):
                with patch.object(hosted, 'restore_runtime'):
                    with patch.object(hosted, 'durable_submission_client', return_value=client):
                        with patch('finpred.pipelines.daily.run_stage', side_effect=PipelineBlocked('missing approved model')):
                            with patch.object(hosted, 'pack_runtime', side_effect=lambda *a: events.append('checkpoint')) as checkpoint:
                                with self.assertRaises(PipelineBlocked):
                                    hosted.run_hosted(data, 'owner/repo', mode='stage', stage='predict',
                                        runtime_root=runtime, store_factory=lambda *a: store)
            checkpoint.assert_called_once()
            store.release.assert_called_once()
            client.close.assert_called_once()
            self.assertEqual(events, ['checkpoint', 'release'])

    def test_existing_receipt_does_not_claim_a_new_post(self):
        with tempfile.TemporaryDirectory() as directory:
            data, runtime = Path(directory) / 'data', Path(directory) / 'runtime'
            data.mkdir()
            store, client = Mock(), Mock(post_attempted=False)
            store.parent = 'a' * 40
            with patch('finpred.data.sharing.import_snapshot_bundle'):
                with patch.object(hosted, 'restore_runtime'):
                    with patch.object(hosted, 'durable_submission_client', return_value=client):
                        with patch('finpred.pipelines.daily.run_stage', return_value={'status': 'verified'}):
                            with patch.object(hosted, 'pack_runtime'):
                                result = hosted.run_hosted(data, 'owner/repo', mode='stage', stage='verify',
                                     runtime_root=runtime, store_factory=lambda *a: store)
            self.assertTrue(result['receipt_verified'])
            self.assertFalse(result['prediction_post_attempted'])
            self.assertFalse(result['prediction_posted'])


if __name__ == '__main__':
    unittest.main()
