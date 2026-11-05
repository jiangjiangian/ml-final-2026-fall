"""Frozen inference, schema and no-future-sequence regression tests."""

import copy
from datetime import date, timedelta
import unittest
from unittest.mock import patch

try:
    import numpy as np
    from finpred.inference.predict import predict_rows
    from finpred.training.fit import fit_model
except ImportError as error:
    raise unittest.SkipTest("inference tests require models extra") from error


def fixture():
    rows = []
    for i in range(12):
        day = (date(2024, 1, 1) + timedelta(days=i)).isoformat()
        y = i % 2
        for stock in ["0010", "2330"]:
            rows.append(
                dict(
                    stock_id=stock,
                    target_date=day,
                    feature_cutoff=day + "T08:10:00+08:00",
                    label_available_at=day + "T23:59:00+08:00",
                    x=float(y),
                    y=y,
                    adj_open=100,
                    adj_close=101 if y else 99,
                    target_intraday_return=0.01 if y else -0.01,
                )
            )
    return dict(
        schema_version="training-table-v1",
        feature_columns=["x"],
        feature_version="fixture-v1",
        readiness="synthetic",
        availability_evidence="synthetic fixture",
        rows=rows,
    )


def future_rows():
    return [
        dict(
            stock_id=s,
            target_date="2024-02-02",
            feature_cutoff="2024-02-02T08:10:00+08:00",
            x=float(i),
        )
        for i, s in enumerate(["0010", "2330"])
    ]


class InferenceTests(unittest.TestCase):
    def test_inference_never_fits_and_keeps_exact_keys(self):
        model = fit_model(fixture(), fit_cutoff="2024-02-01T07:20:00+08:00")
        with patch.object(
            model.preprocessor, "fit", side_effect=AssertionError("must not fit")
        ):
            result = predict_rows(
                model,
                future_rows(),
                feature_columns=["x"],
                feature_version="fixture-v1",
            )
        self.assertEqual(
            [(r["stock_id"], r["target_date"]) for r in result],
            [("0010", "2024-02-02"), ("2330", "2024-02-02")],
        )
        self.assertTrue(all(r["prediction"] in [0, 1] for r in result))

    def test_schema_missing_feature_past_target_and_production_gate(self):
        model = fit_model(fixture(), fit_cutoff="2024-02-01T07:20:00+08:00")
        for kwargs in [
            dict(feature_columns=["other"]),
            dict(feature_version="bad"),
            dict(require_production=True),
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                predict_rows(model, future_rows(), **kwargs)
        rows = future_rows()
        del rows[0]["x"]
        with self.assertRaises(ValueError):
            predict_rows(model, rows)
        rows = future_rows()
        rows[0]["target_date"] = "2024-01-01"
        rows[0]["feature_cutoff"] = "2024-01-01T08:10:00+08:00"
        with self.assertRaises(ValueError):
            predict_rows(model, rows)

    def test_regression_zero_is_class_zero(self):
        model = fit_model(
            fixture(), fit_cutoff="2024-02-01T07:20:00+08:00", objective="regression"
        )
        with patch.object(
            model.estimator, "predict", return_value=np.array([0.0, -0.1])
        ):
            self.assertEqual(
                [r["prediction"] for r in predict_rows(model, future_rows())], [0, 0]
            )

    def test_backdated_prediction_and_nonbinary_class_output_rejected(self):
        model = fit_model(fixture(), fit_cutoff="2024-02-03T07:20:00+08:00")
        with self.assertRaisesRegex(ValueError, "fitted after"):
            predict_rows(model, future_rows())
        model = fit_model(fixture(), fit_cutoff="2024-02-01T07:20:00+08:00")
        with patch.object(
            model.estimator, "predict", return_value=np.array([0.5, 1.0])
        ):
            with self.assertRaisesRegex(ValueError, "binary labels"):
                predict_rows(model, future_rows())

    def test_gru_three_objectives_and_future_invariance(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("optional neural extra not installed")
        for objective in ["classification", "weighted_classification", "regression"]:
            model = fit_model(
                fixture(),
                fit_cutoff="2024-02-01T07:20:00+08:00",
                family="gru",
                objective=objective,
                epochs=1,
            )
            rows = future_rows()
            before = predict_rows(model, rows)
            extended = copy.deepcopy(rows) + [
                dict(
                    stock_id="0010",
                    target_date="2024-02-03",
                    feature_cutoff="2024-02-03T08:10:00+08:00",
                    x=1000000,
                )
            ]
            self.assertEqual(before, predict_rows(model, extended)[:2])


if __name__ == "__main__":
    unittest.main()
