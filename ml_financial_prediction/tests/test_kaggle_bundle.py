"""Private upload boundaries and input-version pinning for Kaggle bundles."""

import importlib.util
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare_kaggle_bundle.py'
SPEC = importlib.util.spec_from_file_location('prepare_kaggle_bundle', SCRIPT)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class KaggleBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'checkout/business'
        for directory in ['src/finpred', 'scripts', 'configs/research', 'configs/kaggle', 'notebooks']:
            (self.project / directory).mkdir(parents=True, exist_ok=True)
        (self.project / 'src/finpred/__init__.py').write_text('')
        (self.project / 'scripts/compare_architectures.py').write_text('print("fixture")\n')
        self.write(self.project / 'notebooks/financial_model_comparison.ipynb', {
            'cells': [{'cell_type': 'code', 'source': 'EXPECTED_BUNDLE_MANIFEST_SHA256 = ""',
                       'outputs': [], 'execution_count': None}], 'metadata': {}, 'nbformat': 4,
        })
        self.write(self.project / 'configs/kaggle/kernel-metadata.json', {
            'is_private': True, 'enable_internet': False, 'competition_sources': [],
            'kernel_sources': [], 'model_sources': [],
        })
        self.config = {'objective': {'expected_stocks': 50},
                       'validation': {'initial_configuration_budget': 12},
                       'models': [{'id': model, 'initial_tuning': {'values': [0.0, 0.1, 0.2]}}
                                  for model in ['M1', 'M2', 'M3', 'M4']]}
        self.write(self.project / 'configs/research/model_families.json', self.config)
        self.stocks = [str(1000 + i) for i in range(50)]
        self.feature_rows = {
            'schema_version': 'sequence-feature-table-v1', 'feature_columns': ['signal'],
            'stock_ids': self.stocks, 'target_dates': ['2025-01-02'],
            'rows': [{'stock_id': s, 'target_date': '2025-01-02', 'signal': 0.1,
                      'feature_present': True} for s in self.stocks],
        }
        self.table = {'schema_version': 'training-table-v1', 'readiness': 'research_assumption',
                      'feature_columns': ['signal'], 'rows': [
                          {'stock_id': s, 'target_date': '2025-01-02', 'signal': 0.1,
                           'target_intraday_return': 0.01, 'y': 1} for s in self.stocks]}
        self.table_path, self.feature_path = self.root / 'table.json', self.root / 'features.json'
        self.write(self.table_path, self.table)
        self.write(self.feature_path, self.feature_rows)
        self.output = self.root / 'private-output'

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def prepare(self):
        return bundle.prepare_bundle(self.table_path, self.feature_path, self.output,
                                     owner='fixture-owner', project=self.project)

    def test_private_and_exact_version_pinned_without_remote_calls(self):
        result = self.prepare()
        self.assertFalse(result['remote_uploaded'])
        self.assertFalse(result['kernel_executed_remotely'])
        self.assertTrue(bundle.validate_bundle(self.output)['input_manifest_pinned'])
        notebook = json.loads((self.output / 'kernel/financial_model_comparison.ipynb').read_text())
        self.assertIn(result['manifest_sha256'], notebook['cells'][0]['source'])
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.prepare()

    def test_tampered_payload_rejected(self):
        self.prepare()
        (self.output / 'data/feature-rows.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            bundle.validate_bundle(self.output)

    def test_unregistered_upload_file_rejected(self):
        self.prepare()
        (self.output / 'data/unregistered-credentials.txt').write_text('not-an-actual-secret')
        with self.assertRaisesRegex(ValueError, 'only registered'):
            bundle.validate_bundle(self.output)

    def test_credentials_in_metadata_rejected_before_bundle_creation(self):
        self.table['provenance'] = {'course_password': 'test-fixture-not-a-real-password'}
        self.write(self.table_path, self.table)
        with self.assertRaisesRegex(ValueError, 'credentials'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_symbolic_input_rejected(self):
        alias = self.root / 'alias.json'
        alias.symlink_to(self.table_path)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            bundle.prepare_bundle(alias, self.feature_path, self.output,
                                  owner='fixture-owner', project=self.project)

    def test_raw_outcome_cannot_enter_feature_rows(self):
        self.feature_rows['rows'][0]['y'] = 1
        self.write(self.feature_path, self.feature_rows)
        with self.assertRaisesRegex(ValueError, 'outcome'):
            self.prepare()

    def test_missing_stock_slot_is_not_silently_dropped(self):
        self.feature_rows['rows'].pop()
        self.write(self.feature_path, self.feature_rows)
        with self.assertRaisesRegex(ValueError, 'slots must be retained'):
            self.prepare()

    def test_input_columns_and_budget_cannot_drift(self):
        self.feature_rows['feature_columns'] = ['different_signal']
        with self.assertRaisesRegex(ValueError, 'columns must match'):
            bundle.validate_input_contract(self.table, self.feature_rows, self.config)
        self.feature_rows['feature_columns'] = ['signal']
        self.config['models'][0]['initial_tuning']['values'].append(0.3)
        with self.assertRaisesRegex(ValueError, 'budget'):
            bundle.validate_input_contract(self.table, self.feature_rows, self.config)

    def test_dataset_relicensing_is_rejected(self):
        self.prepare()
        path = self.output / 'data/dataset-metadata.json'
        metadata = json.loads(path.read_text())
        metadata['licenses'] = [{'name': 'CC0-1.0'}]
        self.write(path, metadata)
        with self.assertRaisesRegex(ValueError, 'license'):
            bundle.validate_bundle(self.output)

    def test_public_kernel_is_rejected(self):
        self.prepare()
        path = self.output / 'kernel/kernel-metadata.json'
        metadata = json.loads(path.read_text())
        metadata['is_private'] = False
        self.write(path, metadata)
        with self.assertRaisesRegex(ValueError, 'must be private'):
            bundle.validate_bundle(self.output)

    def test_even_hash_pinned_code_rejects_traversal_and_symlinks(self):
        self.prepare()
        archive_path = self.output / 'data/finpred-code.zip'
        original = archive_path.read_bytes()
        for name, symlink in [('../outside.py', False), ('src/finpred/link.py', True)]:
            with self.subTest(member=name):
                archive_path.write_bytes(original)
                with zipfile.ZipFile(archive_path, 'a') as archive:
                    entry = zipfile.ZipInfo(name)
                    if symlink:
                        entry.create_system = 3
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(entry, b'not_executed')
                manifest_path = self.output / 'data/bundle-manifest.json'
                manifest = json.loads(manifest_path.read_text())
                old_hash = bundle.sha256(manifest_path.read_bytes())
                payload = archive_path.read_bytes()
                manifest['files']['finpred-code.zip'] = {'sha256': bundle.sha256(payload), 'bytes': len(payload)}
                self.write(manifest_path, manifest)
                new_hash = bundle.sha256(manifest_path.read_bytes())
                notebook_path = self.output / 'kernel/financial_model_comparison.ipynb'
                notebook_path.write_text(notebook_path.read_text().replace(old_hash, new_hash))
                with self.assertRaisesRegex(ValueError, 'unsafe or unexpected path'):
                    bundle.validate_bundle(self.output)

    def test_private_output_cannot_live_inside_checkout(self):
        with self.assertRaisesRegex(ValueError, 'outside the Git checkout'):
            bundle.prepare_bundle(self.table_path, self.feature_path, self.project / 'private',
                                  owner='fixture-owner', project=self.project)


if __name__ == '__main__':
    unittest.main()
