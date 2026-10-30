"""Meaningful chronology, objective and model-bundle boundary tests."""

from datetime import date, timedelta
from importlib import import_module
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

try:
    import numpy as np
    from finpred.training.fit import (
        fit_model,
        load_model_bundle,
        save_model_bundle,
        train_candidate,
        validate_table,
    )
except ImportError as error:
    raise unittest.SkipTest("model tests require the models extra") from error


def table(days=24, readiness="synthetic"):
    rows = []
    for i in range(days):
        day = (date(2024, 1, 1) + timedelta(days=i)).isoformat()
        for stock in ["0010", "2330"]:
            signal = (i % 4) - 1.5
            ret = 0.01 if signal > 0 else -0.02
            rows.append(
                dict(
                    stock_id=stock,
                    target_date=day,
                    feature_cutoff=day + "T08:10:00+08:00",
                    label_available_at=day + "T23:59:00+08:00",
                    signal=signal,
                    sparse=None if i % 3 == 0 else float(i),
                    y=int(ret > 0),
                    adj_open=100.0,
                    adj_close=100 * (1 + ret),
                    target_intraday_return=ret,
                )
            )
    return dict(
        schema_version="training-table-v1",
        feature_columns=["signal", "sparse"],
        feature_version="fixture-v1",
        readiness=readiness,
        availability_evidence="Synthetic observations with explicit per-date timestamps; no real market claim.",
        rows=rows,
    )


class TrainingTests(unittest.TestCase):
    def test_unverified_requires_explicit_opt_in_and_cannot_promote(self):
        value = table(readiness="research_assumption")
        with self.assertRaisesRegex(ValueError, "research opt-in"):
            fit_model(value, fit_cutoff="2024-02-01T07:20:00+08:00")
        model = fit_model(
            value, fit_cutoff="2024-02-01T07:20:00+08:00", allow_research=True
        )
        self.assertFalse(model.metadata["production_eligible"])

    def test_outcome_features_and_missing_verified_timestamps_rejected(self):
        value = table()
        value["feature_columns"] = ["y"]
        with self.assertRaisesRegex(ValueError, "outcome"):
            validate_table(value)
        value = table(readiness="verified")
        del value["rows"][0]["label_available_at"]
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            validate_table(value)

    def test_cutoff_future_target_late_label_and_duplicate_key_rejected(self):
        for change in ["cutoff", "future", "label", "duplicate"]:
            value = table()
            if change == "cutoff":
                value["rows"][0]["feature_cutoff"] = "2024-01-01T09:00:00.000001+08:00"
            if change == "future":
                value["rows"][-1]["target_date"] = "2024-02-01"
                value["rows"][-1]["feature_cutoff"] = "2024-02-01T08:10:00+08:00"
            if change == "label":
                value["rows"][0]["label_available_at"] = "2024-02-02T00:00:00+08:00"
            if change == "duplicate":
                value["rows"].append(dict(value["rows"][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                fit_model(value, fit_cutoff="2024-02-01T07:20:00+08:00")

    def test_all_sklearn_families_and_three_objectives_fit(self):
        for family in ["linear", "hist_gbdt", "mlp"]:
            for objective in [
                "classification",
                "weighted_classification",
                "regression",
            ]:
                with (
                    self.subTest(family=family, objective=objective),
                    warnings.catch_warnings(),
                ):
                    warnings.simplefilter("ignore")
                    model = fit_model(
                        table(),
                        fit_cutoff="2024-02-01T07:20:00+08:00",
                        family=family,
                        objective=objective,
                    )
                    self.assertEqual(model.metadata["family"], family)
                    self.assertIn("scikit-learn", model.metadata["package_versions"])
                    self.assertEqual(model.metadata["train_rows"], 48)

    def test_train_only_preprocessor_does_not_include_future_extreme(self):
        from finpred.inference.predict import predict_rows

        value = table()
        model = fit_model(value, fit_cutoff="2024-02-01T07:20:00+08:00")
        original_mean = model.preprocessor.named_steps["scaler"].mean_.copy()
        predict_rows(
            model,
            [
                dict(
                    stock_id="0010",
                    target_date="2024-02-02",
                    feature_cutoff="2024-02-02T08:10:00+08:00",
                    signal=1000000.0,
                    sparse=1000000.0,
                )
            ],
        )
        np.testing.assert_array_equal(
            original_mean, model.preprocessor.named_steps["scaler"].mean_
        )
        self.assertAlmostEqual(
            model.preprocessor.named_steps["scaler"].mean_[0],
            np.mean([r["signal"] for r in value["rows"]]),
        )
        self.assertNotEqual(model.preprocessor.named_steps["scaler"].mean_[0], 1000000)

    def test_bundle_requires_trusted_store_and_rejects_tampering(self):
        model = fit_model(table(), fit_cutoff="2024-02-01T07:20:00+08:00")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle"
            save_model_bundle(model, path)
            with self.assertRaisesRegex(ValueError, "trusted"):
                load_model_bundle(path)
            restored = load_model_bundle(path, trusted=True)
            self.assertEqual(restored.metadata, model.metadata)
            with self.assertRaisesRegex(ValueError, "empty"):
                save_model_bundle(model, path)
            (path / "model.joblib").write_bytes(b"not the model")
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_model_bundle(path, trusted=True)

    def test_candidate_fair_configuration_retrain_and_research_gate(self):
        value = table(readiness="research_assumption")
        with tempfile.TemporaryDirectory() as tmp:
            report = train_candidate(
                value,
                tmp,
                fit_cutoff="2024-02-01T07:20:00+08:00",
                min_train_dates=10,
                validation_dates=5,
                allow_research=True,
                incumbent_configuration={
                    "family": "linear",
                    "objective": "classification",
                },
            )
            self.assertEqual(
                report["evaluation_scope"], "configuration_retrained_on_same_time_split"
            )
            self.assertFalse(report["eligible_for_promotion"])
            self.assertEqual(len(report["validation_keys"]), 10)
            self.assertTrue((Path(tmp) / "model/manifest.json").exists())

    def test_verified_same_recipe_refreshes_on_new_completed_history(self):
        value = table(readiness="verified")
        value["availability_policy_version"] = "fixture-policy-v1"
        recipe = {"family": "linear", "objective": "weighted_classification", "seed": 42}
        previous = fit_model(dict(value, rows=value["rows"][:-4]),
                             fit_cutoff="2024-02-01T07:20:00+08:00", **recipe)
        with tempfile.TemporaryDirectory() as root:
            report = train_candidate(value, root, fit_cutoff="2024-02-01T07:20:00+08:00",
                min_train_dates=10, validation_dates=5, incumbent_configuration=recipe,
                incumbent_metadata=previous.metadata)
            self.assertFalse(report["candidate_improved"])
            self.assertTrue(report["eligible_for_promotion"])
            self.assertTrue(report["history_advanced"])
            self.assertEqual(report["promotion_reason"], "same_configuration_new_history_refresh")
            saved = json.loads((Path(root) / "model/manifest.json").read_text())
            self.assertEqual(saved["train_end_date"], "2024-01-24")
            self.assertEqual(saved["availability_policy_version"], "fixture-policy-v1")

    def test_same_recipe_rejects_stale_history_unknown_metadata_and_policy_change(self):
        value = table(readiness="verified")
        recipe = {"family": "linear", "objective": "weighted_classification", "seed": 42}
        previous = fit_model(value, fit_cutoff="2024-02-01T07:20:00+08:00", **recipe)
        variants = [
            (previous.metadata, "no_new_completed_history"),
            (None, "refresh_requires_verified_incumbent_metadata"),
            (dict(previous.metadata, train_end_date="2024-01-22", feature_version="other"),
             "incumbent_schema_or_policy_incompatible"),
            (dict(previous.metadata, train_end_date="2024-01-22", availability_evidence="changed policy"),
             "incumbent_schema_or_policy_incompatible"),
            (dict(previous.metadata, train_end_date="2024-01-22", availability_policy_version="old"),
             "incumbent_schema_or_policy_incompatible"),
            (dict(previous.metadata, train_end_date="2024-01-22", readiness="research_assumption"),
             "incumbent_schema_or_policy_incompatible"),
        ]
        for metadata, reason in variants:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as root:
                result = train_candidate(value, root, fit_cutoff="2024-02-01T07:20:00+08:00",
                    min_train_dates=10, validation_dates=5, incumbent_configuration=recipe,
                    incumbent_metadata=metadata)
                self.assertFalse(result["eligible_for_promotion"])
                self.assertEqual(result["promotion_reason"], reason)

    def test_refresh_rejects_validation_degradation_and_new_recipe_requires_strict_gain(self):
        value = table(readiness="verified")
        recipe = {"family": "linear", "objective": "weighted_classification", "seed": 42}
        previous = fit_model(dict(value, rows=value["rows"][:-4]),
                             fit_cutoff="2024-02-01T07:20:00+08:00", **recipe)
        cases = [
            ("weighted_classification", 0.01, 0.02, False, "same_configuration_validation_degraded"),
            ("classification", 0.02, 0.02, False, "no_validation_improvement"),
            ("classification", 0.03, 0.02, True, "strict_validation_improvement"),
        ]
        for objective, candidate, incumbent, eligible, reason in cases:
            with self.subTest(objective=objective, candidate=candidate), tempfile.TemporaryDirectory() as root:
                with patch.object(import_module("finpred.evaluation.official_score"), "evaluate_predictions", side_effect=[
                    SimpleNamespace(score=candidate), SimpleNamespace(score=incumbent),
                ]):
                    result = train_candidate(value, root, fit_cutoff="2024-02-01T07:20:00+08:00",
                        objective=objective, min_train_dates=10, validation_dates=5,
                        incumbent_configuration=recipe, incumbent_metadata=previous.metadata)
                self.assertEqual(result["eligible_for_promotion"], eligible)
                self.assertEqual(result["promotion_reason"], reason)

    def test_experiment_harness_baselines_and_all_configs(self):
        spec = importlib.util.spec_from_file_location(
            "run_experiments",
            Path(__file__).resolve().parents[1] / "scripts/run_experiments.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            report = module.run_experiments(
                table(),
                tmp,
                families=("linear",),
                objectives=("classification", "weighted_classification", "regression"),
                folds=[dict(name="fixture", start="2024-01-15", end="2024-02-01")],
            )
            self.assertEqual(len(report["results"]), 6)
            self.assertFalse(report["holdout_evaluated"])
            self.assertFalse(report["production_performance_claim"])
            self.assertEqual(
                json.loads((Path(tmp) / "report.json").read_text())["seed"], 42
            )
            with self.assertRaisesRegex(ValueError, "immutable"):
                module.run_experiments(table(), tmp)

    def test_abs_return_weighted_error_identity(self):
        for r in [-0.3, 0.0, 0.02]:
            for prediction in [0, 1]:
                wrong = prediction != int(r > 0)
                self.assertAlmostEqual(
                    abs(r) * wrong, (abs(r) - (2 * prediction - 1) * r) / 2
                )


if __name__ == "__main__":
    unittest.main()
