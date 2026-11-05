"""Published history permits bounded state without dropping active evidence."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))
import runtime_store as store  # noqa: E402


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class RuntimeRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.data, self.remote = (self.base / name for name in ('runtime', 'data', 'remote.git'))
        self.root.mkdir(mode=0o700)
        self.git('init', '--bare', '-q', str(self.remote), cwd=self.base)
        self.git('clone', '-q', str(self.remote), str(self.data), cwd=self.base)
        self.git('checkout', '-q', '-b', 'live-data')

    def git(self, *arguments, cwd=None):
        result = subprocess.run(['git', *arguments], cwd=cwd or self.data,
                                capture_output=True, check=True)
        return result.stdout

    def publish(self):
        self.git('add', '--all')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                 'commit', '-q', '-m', 'durable test state')
        self.git('push', '-q', 'origin', 'live-data')
        return self.git('rev-parse', 'HEAD').decode().strip()

    def put(self, name, value):
        path = self.root / name
        store.write_json(path, value)
        return path

    def table(self, name, identity):
        return self.put(name, {'schema_version': 'training-table-v1', 'identity': identity,
                               'rows': [{'padding': 'x' * 1800}]})

    def compact(self, limit=18000):
        with patch.object(store, 'LARGE_TABLE_BYTES', 1024), patch.object(store, 'MAX_STATE_BYTES', limit):
            return store.pack_runtime(self.root, self.data)

    def test_many_days_prune_only_published_unreferenced_tables_and_keep_active_chains(self):
        tables = [self.table(f'tables/2026-10-{day:02}/training/data.json', str(day))
                  for day in range(1, 21)]
        # Active course approval reaches its table through the run registration.
        model = self.root / 'candidates/course-benchmark-v1/runs/current/model'
        self.put('candidates/course-benchmark-v1/approved.json', {'model_path': str(model)})
        self.put('candidates/course-benchmark-v1/runs/current/model/manifest.json', {'scope': 'active'})
        self.put('candidates/course-benchmark-v1/runs/current/registration.json',
                 {'training_table_path': str(tables[0])})
        # Merely retaining an old report does not keep all its old table bytes.
        old_report = self.put('candidates/course-benchmark-v1/runs/old/registration.json',
                              {'training_table_path': str(tables[1])})
        self.put('shadow/model-latest.json', {'training_table_file_sha256': digest(tables[2].read_bytes())})
        # A pending old POST keeps its exact older prediction's input, even when
        # a newer latest prediction exists for the same policy.
        pending_hash = 'a' * 64
        ledger = self.put('submission/2026-10-04/latest.json',
                          {'status': 'unverified', 'csv_sha256': pending_hash})
        self.put('predictions/course-benchmark-v1/2026-10-04/old/manifest.json',
                 {'csv_sha256': pending_hash, 'feature_table_path': str(tables[3])})
        self.put('predictions/course-benchmark-v1/2026-10-20/latest.json',
                 {'csv_sha256': 'b' * 64, 'feature_table_path': str(tables[19])})
        receipt = self.put('verified/2026-09-01.json', {'status': 'verified'})
        before = store.pack_runtime(self.root, self.data)
        committed = self.publish()
        new_table = self.table('tables/2026-10-21/training/data.json', 'new unpublished')
        unknown = self.data / 'runtime/objects/user-note.txt'
        unknown.write_text('must remain untouched')
        result = self.compact()
        kept = {item['path'] for item in result['files']}
        self.assertLessEqual(result['total_bytes'], 18000)
        for path in (tables[0], tables[2], tables[3], tables[19], new_table, ledger, old_report, receipt):
            self.assertTrue(path.exists(), path)
            self.assertIn(path.relative_to(self.root).as_posix(), kept)
        self.assertFalse(tables[1].exists())
        self.assertIn(tables[1].relative_to(self.root).as_posix(), result['retention']['pruned_paths'])
        self.assertEqual(result['retention']['archived_commit'], committed)
        old_entry = next(item for item in before['files']
                         if item['path'] == tables[1].relative_to(self.root).as_posix())
        self.assertFalse((self.data / old_entry['object_key']).exists())
        # The removed latest-tree object remains reproducible from its recorded
        # immutable Git commit; neither force push nor history rewriting occurs.
        self.assertEqual(digest(self.git('show', committed + ':' + old_entry['object_key'])), old_entry['sha256'])
        self.assertEqual(unknown.read_text(), 'must remain untouched')

    def test_unpublished_index_does_not_authorize_deleting_new_data(self):
        first = self.table('tables/2026-10-01/training/a.json', 'first')
        second = self.table('tables/2026-10-02/training/a.json', 'second')
        store.pack_runtime(self.root, self.data)
        index = (self.data / 'runtime/state.json').read_bytes()
        with self.assertRaises(store.HostedBlocked):
            self.compact(limit=3000)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual((self.data / 'runtime/state.json').read_bytes(), index)

    def test_changed_previously_published_table_is_unpublished_and_cannot_be_pruned(self):
        table = self.table('tables/2026-10-01/training/a.json', 'published')
        store.pack_runtime(self.root, self.data)
        self.publish()
        changed = {'schema_version': 'training-table-v1', 'rows': ['new data' * 700]}
        store.write_json(table, changed)
        with self.assertRaises(store.HostedBlocked):
            self.compact(limit=3000)
        self.assertEqual(json.loads(table.read_bytes()), changed)

    def test_strict_model_training_table_canonical_hash_is_a_live_reference(self):
        active = self.table('tables/2026-10-01/training/pretty.json', 'strict-active')
        self.table('tables/2026-10-02/training/old.json', 'obsolete')
        canonical = digest(json.dumps(json.loads(active.read_bytes()), sort_keys=True,
                                      ensure_ascii=False, allow_nan=False).encode())
        model = self.root / 'candidates/day/id/model'
        self.put('approved.json', {'model_path': str(model)})
        self.put('candidates/day/id/model/manifest.json', {'training_table_sha256': canonical})
        store.pack_runtime(self.root, self.data)
        self.publish()
        result = self.compact(limit=5500)
        self.assertTrue(active.exists())
        self.assertIn(active.relative_to(self.root).as_posix(), {entry['path'] for entry in result['files']})

    def test_newer_day_latest_does_not_keep_all_historical_model_training_tables(self):
        old = self.table('tables/2026-10-01/training/a.json', 'old')
        current = self.table('tables/2026-10-20/training/a.json', 'current')
        self.put('predictions/2026-10-01/latest.json', {'feature_table_path': str(old)})
        self.put('predictions/2026-10-20/latest.json', {'feature_table_path': str(current)})
        self.put('submission/2026-10-01/latest.json', {'status': 'verified'})
        store.pack_runtime(self.root, self.data)
        self.publish()
        result = self.compact(limit=5500)
        self.assertFalse(old.exists())
        self.assertTrue(current.exists())
        self.assertLessEqual(result['total_bytes'], 5500)

    def test_non_table_files_and_new_unknown_objects_are_not_retention_targets(self):
        self.table('tables/2026-10-01/training/a.json', 'old')
        report = self.put('runs/large-report.json', {'message': 'evidence' * 400})
        store.pack_runtime(self.root, self.data)
        self.publish()
        unknown = self.data / 'runtime/objects' / ('c' * 64 + '.bin')
        unknown.write_bytes(b'not a previously published managed object')
        result = self.compact(limit=6500)
        self.assertTrue(report.exists())
        self.assertIn('runs/large-report.json', {entry['path'] for entry in result['files']})
        self.assertEqual(unknown.read_bytes(), b'not a previously published managed object')


if __name__ == '__main__':
    unittest.main()
