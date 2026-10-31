"""Portable transfer must preserve source times and reject corrupt or private data."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finpred.data import sharing
from finpred.data.snapshots import snapshot_bytes

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sync_live_data.py'
SPEC = importlib.util.spec_from_file_location('sync_live_data_guard_tests', SCRIPT)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class DataSharingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'producer'
        self.bundle = self.root / 'bundle'
        self.consumer = self.root / 'consumer'

    def snapshot(self, source='course-live', payload=b'date,value\n2026-10-29,1\n', **metadata):
        return snapshot_bytes(payload, self.runtime / 'raw', source,
                              'https://example.com/data.csv?token=excluded', '.csv',
                              {'tls_verified': True, 'audit': {
                                  'stock_count': 100, 'complete_labels': 3900,
                                  'pending_labels': 100, 'date_max': '2026-10-30',
                                  'pending_label_dates': ['2026-10-23'],
                                  'readiness': {'labels': 'partial'},
                              }, **metadata})

    def catalog(self):
        pointer = json.loads((self.bundle / 'catalog/latest.json').read_text())
        return json.loads((self.bundle / pointer['catalog_key']).read_text())

    def test_roundtrip_source_time_payload_and_provenance(self):
        original = self.snapshot()
        exported = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        result = sharing.import_snapshot_bundle(self.bundle, self.consumer,
                                                 revision='a' * 40)
        self.assertEqual(exported['catalog_sha256'], result['catalog_sha256'])
        local = json.loads(next((self.consumer / 'raw/course-live/manifests').glob('*.json')).read_text())
        self.assertEqual(original['fetched_at'], local['fetched_at'])
        self.assertEqual(original['sha256'], local['sha256'])
        self.assertEqual(Path(original['payload_path']).read_bytes(), Path(local['payload_path']).read_bytes())
        self.assertTrue(Path(local['payload_path']).is_relative_to(self.consumer))
        original_hash = hashlib.sha256(Path(original['manifest_path']).read_bytes()).hexdigest()
        self.assertEqual(original_hash, local['source_snapshot_manifest_sha256'])
        receipt = json.loads(Path(result['transport_receipt']).read_text())
        self.assertEqual('a' * 40, receipt['git_revision'])
        self.assertGreaterEqual(receipt['consumer_received_at'], original['fetched_at'])
        self.assertEqual(100, self.catalog()['sources']['course-live']['pending_labels'])
        self.assertNotIn('token=', json.dumps(self.catalog()))

    def test_duplicate_acquisitions_deduplicate_object_and_retries(self):
        for _ in range(20):
            self.snapshot()
        original_read = sharing._read
        reads = []

        def tracked(path, **kwargs):
            if '/objects/' in str(path):
                reads.append(str(path))
            return original_read(path, **kwargs)

        with patch.object(sharing, '_read', side_effect=tracked):
            exported = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.assertEqual(20, exported['manifest_count'])
        self.assertEqual(1, exported['objects_written'])
        # Read/verify each content object, not each acquisition. No payload buffers
        # are retained in the prepared per-acquisition array.
        self.assertLessEqual(len(reads), 3)
        retried = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.assertEqual(0, retried['objects_written'])
        self.assertEqual(0, retried['manifests_written'])
        self.assertFalse(retried['catalog_changed'])
        sharing.import_snapshot_bundle(self.bundle, self.consumer)
        self.assertEqual(1, len(list((self.consumer / 'raw/course-live/objects').glob('*'))))
        self.assertEqual(20, len(list((self.consumer / 'raw/course-live/manifests').glob('*'))))

    def test_import_reexport_preserves_original_manifest_hash_and_source_history(self):
        self.snapshot()
        original = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        sharing.import_snapshot_bundle(self.bundle, self.consumer)
        second = sharing.export_snapshot_bundle(self.consumer, self.root / 'second-bundle')
        # The consumer's collection status changes from absent to restored, but
        # no new source acquisition or portable source manifest is fabricated.
        self.assertEqual(original['latest'], second['latest'])

    def test_revision_keeps_old_object_and_pending_source(self):
        self.snapshot(payload=b'old')
        first = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.snapshot(payload=b'new')
        revised = sharing.export_snapshot_bundle(self.runtime, self.bundle, required_sources=['course-training'])
        self.assertNotEqual(first['catalog_sha256'], revised['catalog_sha256'])
        self.assertEqual('partial', revised['status'])
        self.assertEqual(2, len(list((self.bundle / 'objects').glob('*'))))
        self.assertEqual(2, len(self.catalog()['sources']['course-live']['history']))

    def test_failed_source_retains_previous_success(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        (self.runtime / 'latest_collection.json').write_text(json.dumps({
            'status': 'partial', 'failures': [{'source': 'course-live', 'error_type': 'ValueError'}]}))
        result = sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.assertEqual('partial', result['status'])
        self.assertEqual(1, result['manifest_count'])
        self.assertEqual([{'source': 'course-live', 'error_type': 'ValueError'}], self.catalog()['collection']['failures'])

    def test_new_corrupt_source_does_not_replace_successful_pointer(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        before = (self.bundle / 'catalog/latest.json').read_bytes()
        bad = self.snapshot(payload=b'new')
        Path(bad['payload_path']).write_bytes(b'changed')
        with self.assertRaises(sharing.SharingError):
            sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.assertEqual(before, (self.bundle / 'catalog/latest.json').read_bytes())

    def test_corrupt_bundle_rejected_before_any_runtime_data(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        next((self.bundle / 'objects').iterdir()).write_bytes(b'corrupt')
        with self.assertRaises(sharing.SharingError):
            sharing.import_snapshot_bundle(self.bundle, self.consumer)
        self.assertFalse((self.consumer / 'raw').exists())

    def test_query_and_unknown_free_text_metadata_are_removed(self):
        self.snapshot(password='never', arbitrary={'email': 'not-for-export'},
                      notes='a private free text', request={'token': 'not-for-export'})
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        manifest = next((self.bundle / 'manifests/course-live').glob('*.json')).read_text()
        self.assertNotIn('never', manifest)
        self.assertNotIn('not-for-export', manifest)
        self.assertNotIn('private free text', manifest)
        self.assertNotIn('token=', manifest)

    def test_active_credential_literal_in_payload_is_rejected(self):
        value = 'credential-fixture-that-must-never-be-published'
        self.snapshot(payload=value.encode())
        with patch.dict(os.environ, {'FINPRED_SECRET': value}):
            with self.assertRaises(sharing.SharingError):
                sharing.export_snapshot_bundle(self.runtime, self.bundle)
        self.assertFalse((self.bundle / 'catalog/latest.json').exists())

    def test_symlink_payload_and_root_are_rejected(self):
        record = self.snapshot()
        payload = Path(record['payload_path'])
        target = self.root / 'outside'
        target.write_bytes(payload.read_bytes())
        payload.unlink()
        payload.symlink_to(target)
        with self.assertRaises(sharing.SharingError):
            sharing.export_snapshot_bundle(self.runtime, self.bundle)
        alias = self.root / 'alias'
        alias.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(sharing.SharingError):
            sharing.export_snapshot_bundle(alias, self.bundle)

    def test_relative_path_escape_rejected(self):
        for path in ('../outside', '/absolute', 'objects/../../outside', 'objects\\outside'):
            with self.subTest(path=path), self.assertRaises(sharing.SharingError):
                sharing._inside(self.root, path)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO test requires POSIX')
    def test_special_file_is_rejected_without_blocking(self):
        fifo = self.root / 'not-a-regular-file'
        os.mkfifo(fifo)
        with self.assertRaises(sharing.SharingError):
            sharing._read(fifo)

    def test_consumer_must_be_outside_git_and_not_before_source(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        (self.consumer / '.git').mkdir(parents=True)
        with self.assertRaises(sharing.SharingError):
            sharing.import_snapshot_bundle(self.bundle, self.consumer)
        with self.assertRaises(sharing.SharingError):
            sharing.import_snapshot_bundle(self.bundle, self.root / 'earlier',
                                           received_at='2000-01-01T00:00:00+00:00')

    def test_utc_z_transfer_timestamp_is_accepted_on_python_310(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        received = '2099-01-01T00:00:00Z'
        result = sharing.import_snapshot_bundle(self.bundle, self.consumer, received_at=received)
        receipt = json.loads(Path(result['transport_receipt']).read_text())
        self.assertEqual(received, receipt['consumer_received_at'])

    def test_public_repository_is_rejected_before_export(self):
        with patch.object(publisher, 'command', return_value='false'):
            with self.assertRaises(sharing.SharingError):
                publisher.require_private_repository('owner/project')

    def test_private_identity_cannot_publish_to_different_origin(self):
        responses = [str(self.root), 'live-data', '', 'https://github.com/public/another.git']
        with patch.object(publisher, 'command', side_effect=responses):
            with self.assertRaises(sharing.SharingError):
                publisher.publication_preflight(self.root, 'owner/private-project')

    def test_main_branch_cannot_be_used_as_data_publish_destination(self):
        with patch.object(publisher, 'command', side_effect=[str(self.root), 'main']):
            with self.assertRaises(sharing.SharingError):
                publisher.publication_preflight(self.root, 'owner/private-project')

    def test_remote_advance_is_rejected_before_mutation(self):
        responses = [str(self.root), 'live-data', '',
                     'https://github.com/owner/private-project.git', 'a' * 40,
                     'b' * 40 + '\trefs/heads/live-data']
        with patch.object(publisher, 'command', side_effect=responses):
            with self.assertRaises(sharing.SharingError):
                publisher.publication_preflight(self.root, 'owner/private-project')

    def test_fixed_shared_features_and_labels_restore_with_matching_hashes(self):
        from finpred.data.shared_features import build_shared_features
        from test_shared_features import _seed

        _seed(self.runtime)
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        build_shared_features(self.runtime, self.bundle)
        sharing.import_snapshot_bundle(self.bundle, self.consumer, revision='a' * 40)
        result = sharing.import_shared_feature_exports(self.bundle, self.consumer, revision='a' * 40)
        self.assertEqual('imported', result['status'])
        self.assertFalse(result['production_eligible'])
        self.assertEqual(7, len(result['files']))
        for name in result['files']:
            self.assertEqual((self.bundle / name).read_bytes(),
                             (self.consumer / 'shared-data' / name).read_bytes())
        self.assertTrue((self.consumer / 'shared-data/labels/stock_outcomes.csv.gz').exists())

    def test_missing_feature_export_does_not_prevent_raw_transfer(self):
        self.snapshot()
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        raw = sharing.import_snapshot_bundle(self.bundle, self.consumer)
        derived = sharing.import_shared_feature_exports(self.bundle, self.consumer)
        self.assertEqual('imported', raw['status'])
        self.assertEqual('blocked', derived['status'])
        self.assertTrue(next((self.consumer / 'raw/course-live/objects').glob('*')).is_file())
        self.assertEqual('blocked', json.loads((self.consumer / 'shared-data/transfer.json').read_text())['status'])

    def test_corrupt_derived_export_does_not_write_partial_feature_files(self):
        from finpred.data.shared_features import build_shared_features
        from test_shared_features import _seed

        _seed(self.runtime)
        sharing.export_snapshot_bundle(self.runtime, self.bundle)
        build_shared_features(self.runtime, self.bundle)
        sharing.import_snapshot_bundle(self.bundle, self.consumer)
        (self.bundle / 'features/market.csv').write_bytes(b'corrupt')
        result = sharing.import_shared_feature_exports(self.bundle, self.consumer)
        self.assertEqual('blocked', result['status'])
        self.assertFalse((self.consumer / 'shared-data/features').exists())
        self.assertFalse((self.consumer / 'shared-data/labels').exists())


if __name__ == '__main__':
    unittest.main()
