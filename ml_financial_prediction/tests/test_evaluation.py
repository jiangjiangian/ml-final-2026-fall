"""Synthetic official-score, label-isolation and date-group split checks."""

import copy
import math
import unittest

from finpred.evaluation import evaluate_predictions, official_score
from finpred.labels import build_intraday_labels
from finpred.training import walk_forward_splits


def raw(day="2026-01-02", stock="0050", opening=100, closing=110, **changes):
    row = {
        "stock_id": stock, "date": day, "etl:adj_open": opening,
        "etl:adj_close": closing, "y": int(closing > opening),
        "etl:adj_high": 999999, "not_a_label": "must not be copied",
    }
    row.update(changes)
    return row


def labels(*rows):
    return build_intraday_labels(rows, prices_verified_adjusted=True).complete


def pred(stock="0050", day="2026-01-02", prediction=1):
    return {"stock_id": stock, "target_date": day, "prediction": prediction}


def split_rows(*, availability=False):
    result = []
    for day in range(2, 7):
        for stock in ("0050", "2330"):
            row = {"stock_id": stock, "target_date": f"2026-01-{day:02d}", "y": 1}
            if availability:
                row["label_available_at"] = f"2026-01-{day:02d}T14:00:00+08:00"
            result.append(row)
    return result


def cutoffs():
    return {f"2026-01-{day:02d}": f"2026-01-{day:02d}T08:10:00+08:00" for day in range(2, 7)}


class LabelTests(unittest.TestCase):
    def test_complete_output_keeps_only_labels_and_preserves_stock_string(self):
        source = [raw()]
        before = copy.deepcopy(source)
        result = build_intraday_labels(source, prices_verified_adjusted=True)
        row = result.complete[0]
        self.assertEqual(row["stock_id"], "0050")
        self.assertEqual(row["y"], 1)
        self.assertAlmostEqual(row["target_intraday_return"], 0.1)
        self.assertNotIn("etl:adj_high", row)
        self.assertNotIn("not_a_label", row)
        self.assertEqual(source, before)

    def test_pending_minus_one_never_becomes_zero_or_uses_incomplete_prices(self):
        source = raw(**{"etl:adj_open": -1, "etl:adj_close": -1, "y": -1})
        result = build_intraday_labels([source], prices_verified_adjusted=True)
        self.assertEqual(result.complete, [])
        self.assertEqual(result.pending, [{
            "stock_id": "0050", "target_date": "2026-01-02",
            "status": "pending", "reason": "source_y_minus_one",
        }])

    def test_flat_price_is_completed_zero_label(self):
        self.assertEqual(labels(raw(closing=100))[0]["y"], 0)

    def test_refuses_unverified_price_meaning(self):
        with self.assertRaisesRegex(ValueError, "adjusted-price"):
            build_intraday_labels([raw()], prices_verified_adjusted=False)

    def test_rejects_inconsistent_y_and_invalid_completed_prices(self):
        cases = [raw(y=0), raw(y=2), raw(y=True)]
        for price in (0, -1, math.inf, math.nan, None):
            cases.append(raw(**{"etl:adj_open": price}))
        for row in cases:
            with self.subTest(row=row), self.assertRaises(ValueError):
                labels(row)

    def test_numeric_csv_fields_are_supported_but_missing_y_is_not_generated(self):
        row = raw(**{"etl:adj_open": "100.0", "etl:adj_close": "110.0", "y": "1.0"})
        self.assertEqual(labels(row)[0]["y"], 1)
        del row["y"]
        with self.assertRaises(ValueError):
            labels(row)

    def test_duplicate_keys_dates_and_conflicting_stock_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            labels(raw(), raw())
        with self.assertRaises(ValueError):
            labels(raw(day="20260102"))
        with self.assertRaisesRegex(ValueError, "stock_id differs"):
            build_intraday_labels([raw()], prices_verified_adjusted=True, stock_id="2330")

    def test_label_availability_is_preserved_but_never_synthesized(self):
        row = raw(label_available_at="2026-01-02T06:00:00Z")
        self.assertEqual(labels(row)[0]["label_available_at"], "2026-01-02T06:00:00+00:00")
        self.assertNotIn("label_available_at", labels(raw())[0])
        with self.assertRaises(ValueError):
            labels(raw(label_available_at="2026-01-02T14:00:00"))

    def test_extreme_prices_cannot_create_nonfinite_return(self):
        with self.assertRaisesRegex(ValueError, "return must be finite"):
            labels(raw(opening=1e-308, closing=1e308))


class OfficialScoreTests(unittest.TestCase):
    def test_score_uses_return_magnitude_not_only_accuracy_and_matches_by_key(self):
        truth = labels(raw(stock="0050", closing=101), raw(stock="2330", closing=80))
        result = evaluate_predictions([pred("2330", prediction=0), pred(prediction=0)], truth)
        self.assertAlmostEqual(result.score, (-0.01 + 0.2) / 2)
        self.assertEqual(result.accuracy, 0.5)
        self.assertEqual(result.count, 2)
        self.assertAlmostEqual(result.daily_scores["2026-01-02"], result.score)
        self.assertEqual(official_score([pred()], labels(raw())), 0.1)

    def test_default_coverage_does_not_silently_drop_stocks_or_add_dates(self):
        truth = labels(raw(), raw(stock="2330"))
        for predictions in ([pred()], [pred(), pred("2330"), pred("9999")]):
            with self.subTest(predictions=predictions), self.assertRaisesRegex(ValueError, "exactly"):
                evaluate_predictions(predictions, truth)

    def test_explicit_template_subset_allows_extra_historical_labels(self):
        truth = labels(raw(), raw(day="2026-01-05"))
        result = evaluate_predictions([pred()], truth, expected_keys=[("0050", "2026-01-02")])
        self.assertEqual(result.count, 1)
        with self.assertRaisesRegex(ValueError, "cover"):
            evaluate_predictions([pred("2330")], truth, expected_keys=[("2330", "2026-01-02")])

    def test_invalid_predictions_never_become_implicit_thresholded_classes(self):
        for value in (-1, 0.5, 2, math.nan, math.inf, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                official_score([pred(prediction=value)], labels(raw()))

    def test_duplicate_and_empty_target_sets_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate prediction"):
            official_score([pred(), pred()], labels(raw()))
        with self.assertRaisesRegex(ValueError, "duplicate label"):
            official_score([pred()], labels(raw()) * 2)
        with self.assertRaisesRegex(ValueError, "nonempty"):
            official_score([], [])
        with self.assertRaisesRegex(ValueError, "duplicate expected"):
            official_score([pred()], labels(raw()), expected_keys=[("0050", "2026-01-02")] * 2)

    def test_pending_inconsistent_or_nonfinite_evaluation_labels_rejected(self):
        for field, value in (("y", -1), ("y", 0), ("adj_open", 0), ("adj_close", math.nan),
                             ("target_intraday_return", 0.8)):
            truth = labels(raw())
            truth[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                official_score([pred()], truth)

    def test_score_means_pairs_not_means_of_unequal_size_days(self):
        truth = labels(raw(), raw(stock="2330"), raw(day="2026-01-05", closing=70))
        predictions = [pred(), pred("2330"), pred(day="2026-01-05", prediction=1)]
        self.assertAlmostEqual(official_score(predictions, truth), (0.1 + 0.1 - 0.3) / 3)


class DateSplitTests(unittest.TestCase):
    def test_unsorted_input_keeps_complete_dates_together_with_expanding_train(self):
        rows = list(reversed(split_rows()))
        folds = walk_forward_splits(rows, min_train_dates=2, validation_dates=1)
        self.assertEqual(len(folds), 3)
        self.assertFalse(folds[0].label_availability_checked)
        for fold in folds:
            train = {rows[i]["target_date"] for i in fold.train_indices}
            validation = {rows[i]["target_date"] for i in fold.validation_indices}
            self.assertTrue(max(train) < min(validation))
            self.assertFalse(train & validation)
            for day in train | validation:
                indices = {i for i, row in enumerate(rows) if row["target_date"] == day}
                self.assertTrue(indices <= set(fold.train_indices) or indices <= set(fold.validation_indices))

    def test_gap_and_complete_validation_blocks(self):
        folds = walk_forward_splits(split_rows(), min_train_dates=2, validation_dates=2, gap_dates=1)
        self.assertEqual(len(folds), 1)
        self.assertEqual(folds[0].train_dates, ("2026-01-02", "2026-01-03"))
        self.assertEqual(folds[0].validation_dates, ("2026-01-05", "2026-01-06"))

    def test_late_label_excludes_entire_training_date_until_release(self):
        rows = split_rows(availability=True)
        rows[4]["label_available_at"] = "2026-01-06T00:10:00Z"
        folds = walk_forward_splits(
            rows, min_train_dates=2, validation_dates=1, validation_cutoffs=cutoffs(),
            require_label_availability=True,
        )
        self.assertEqual(folds[0].validation_dates, ("2026-01-04",))
        self.assertEqual(folds[1].excluded_train_dates, ("2026-01-04",))
        self.assertNotIn("2026-01-04", folds[1].train_dates)
        self.assertIn("2026-01-04", folds[2].train_dates)
        self.assertTrue(folds[2].label_availability_checked)

    def test_missing_mixed_naive_or_cutoffless_availability_rejected(self):
        with self.assertRaisesRegex(ValueError, "required"):
            walk_forward_splits(split_rows(), min_train_dates=2, validation_dates=1,
                                require_label_availability=True)
        with self.assertRaisesRegex(ValueError, "validation_cutoffs"):
            walk_forward_splits(split_rows(availability=True), min_train_dates=2, validation_dates=1)
        for value in (None, "2026-01-02T14:00:00"):
            rows = split_rows(availability=True)
            rows[0]["label_available_at"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                walk_forward_splits(rows, min_train_dates=2, validation_dates=1,
                                    validation_cutoffs=cutoffs())

    def test_cutoff_cannot_be_after_first_validation_morning(self):
        for cutoff in ("2026-01-04T09:00:00.000001+08:00", "2026-01-05T08:10:00+08:00"):
            times = cutoffs()
            times["2026-01-04"] = cutoff
            with self.subTest(cutoff=cutoff), self.assertRaisesRegex(ValueError, "by 09:00"):
                walk_forward_splits(split_rows(availability=True), min_train_dates=2,
                                    validation_dates=1, validation_cutoffs=times)

    def test_earliest_fold_fails_if_not_enough_eligible_labels(self):
        rows = split_rows(availability=True)
        rows[0]["label_available_at"] = "2026-01-09T14:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "insufficient eligible"):
            walk_forward_splits(rows, min_train_dates=2, validation_dates=1,
                                validation_cutoffs=cutoffs())

    def test_duplicates_pending_labels_and_invalid_sizes_rejected(self):
        for name, value in (("min_train_dates", 0), ("validation_dates", 0), ("step_dates", 0),
                            ("gap_dates", -1), ("min_train_dates", True)):
            options = {"min_train_dates": 2, "validation_dates": 1, name: value}
            with self.subTest(options=options), self.assertRaises(ValueError):
                walk_forward_splits(split_rows(), **options)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            walk_forward_splits(split_rows() + split_rows()[:1], min_train_dates=2, validation_dates=1)
        rows = split_rows()
        rows[0]["y"] = -1
        with self.assertRaisesRegex(ValueError, "completed"):
            walk_forward_splits(rows, min_train_dates=2, validation_dates=1)


if __name__ == "__main__":
    unittest.main()
