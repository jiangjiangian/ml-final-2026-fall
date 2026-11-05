"""Experiment chronology and provenance gates, without real market data."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

try:
    import sklearn  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest("experiments require the models extra") from error

from test_training import table

spec = importlib.util.spec_from_file_location(
    "finpred_experiments", Path(__file__).resolve().parents[1] / "scripts/run_experiments.py"
)
experiments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiments)


class ExperimentTests(unittest.TestCase):
    def test_disjoint_fold_and_holdout_boundaries(self):
        invalid = [
            ([{"name": "a", "start": "2024-01-10", "end": "2024-01-20"},
              {"name": "b", "start": "2024-01-19", "end": "2024-01-24"}], False),
            ([{"name": "a", "start": "2024-01-10", "end": "2024-01-10"}], False),
            ([{"name": "a", "start": "2026-01-01", "end": "2026-02-01"}], True),
        ]
        with tempfile.TemporaryDirectory() as root:
            for folds, include in invalid:
                with self.subTest(folds=folds), self.assertRaises(ValueError):
                    experiments.run_experiments(table(), root, folds=folds, include_holdout=include)

    def test_provenance_binds_actual_buffer_and_target_keys(self):
        value = table()
        payload = json.dumps(value, indent=3).encode()
        folds = [{"name": "a", "start": "2024-01-15", "end": "2024-01-25"}]
        with tempfile.TemporaryDirectory() as root:
            result = experiments.run_experiments(value, root, families=("linear",),
                objectives=("weighted_classification",), folds=folds, loaded_input_bytes=payload)
            self.assertEqual(result["input_payload_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(result["code_sha256"], experiments.code_hashes())
            self.assertFalse(result["holdout_evaluated"])
            self.assertEqual(result["fold_evidence"][0]["validation_rows"], 20)
            self.assertIn("2024-01", result["results"][-1]["monthly_scores"])
            with self.assertRaisesRegex(ValueError, "immutable"):
                experiments.run_experiments(value, root, families=("linear",),
                    objectives=("weighted_classification",), folds=folds)

    def test_different_loaded_buffer_rejected(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, "buffer"):
            experiments.run_experiments(table(), root, loaded_input_bytes=b"{}")


if __name__ == "__main__":
    unittest.main()
