"""Leakage, period-guard and scoring tests for the R3 research harness (synthetic data).

Skipped when the optional ``research`` extra (pandas) is not installed.
"""

import importlib.util
import math
import unittest

HAVE_PANDAS = importlib.util.find_spec("pandas") is not None
HAVE_SKLEARN = importlib.util.find_spec("sklearn") is not None

if HAVE_PANDAS:
    import numpy as np
    import pandas as pd

    from finpred.evaluation import walkforward as wf
    from finpred.evaluation.official_score import evaluate_predictions
    from finpred.features import r3_features as rf
    from finpred.models.r3_estimators import TrainOnlyPreprocessor, build_model
    from finpred.training import r3_experiment as rx


def synthetic_stocks(n_stocks=6, n_days=140, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2021-06-01", periods=n_days)
    rows = []
    for k in range(n_stocks):
        close = 100.0
        for day in days:
            gap = rng.normal(0, 0.01)
            open_ = close * (1 + gap)
            intra = rng.normal(0, 0.015)
            close = open_ * (1 + intra)
            high, low = max(open_, close) * 1.005, min(open_, close) * 0.995
            vol = float(rng.integers(1_000, 10_000))
            rows.append({
                "stock_id": f"{1000 + k}", "date": day, "open": open_, "close": close,
                "high": high, "low": low, "trades": 10.0, "turnover": vol * close,
                "volume": vol, "foreign_hold_pct": 50 + rng.normal(), "foreign_net": rng.normal() * 100,
                "trust_net": rng.normal() * 10, "dealer_net": rng.normal() * 10,
                "dealer_hedge_net": 0.0, "rsi": 50 + rng.normal(), "sma": close * 0.99,
                "macd": rng.normal(), "atr": close * 0.02, "bb_upper": close * 1.05,
                "bb_mid": close, "bb_lower": close * 0.95, "y": int(close > open_),
            })
    return pd.DataFrame(rows)


def synthetic_market(days, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"date": days, "sox_ret_1s": rng.normal(0, 0.02, len(days)),
                         "dji_ret_1s": rng.normal(0, 0.01, len(days))})


def _perturb_row(stocks, stock_id, day):
    out = stocks.copy()
    mask = (out["stock_id"] == stock_id) & (out["date"] == day)
    for col in ("open", "close", "high", "low", "volume", "turnover", "foreign_net", "trust_net",
                "dealer_net", "rsi", "sma", "macd", "atr", "bb_upper", "bb_lower", "foreign_hold_pct"):
        out.loc[mask, col] = out.loc[mask, col] * 3.7 + 11.0
    return out


def _pred_frame(seed=3):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-01-02", periods=60)
    rows = []
    for day in days:
        for k in range(5):
            o = 100 + rng.normal()
            c = o * (1 + rng.normal(0, 0.02))
            rows.append({"stock_id": f"{2000 + k}", "date": day, "adj_open": o, "adj_close": c,
                         "y": int(c > o), "r": (c - o) / o, "prediction": int(rng.integers(0, 2))})
    return pd.DataFrame(rows)


def _synthetic_feature_frame():
    stocks = synthetic_stocks(n_stocks=4, n_days=700, seed=5)
    stocks["date"] = stocks.groupby("stock_id").cumcount().map(
        dict(enumerate(pd.bdate_range("2020-01-02", periods=700))))
    hist = rf.stock_history_features(stocks)
    frame = hist.copy()
    frame["is_top50"] = (frame["stock_id"] != "1003").astype(int)
    frame["has_teacher_row"] = 1
    labels = rf.build_labels(stocks)
    groups = {"stock_hist": [c for c in hist.columns if c not in ("stock_id", "date")]}
    return rf.FeatureFrame(frame=frame, labels=labels, groups=groups, meta={})


@unittest.skipUnless(HAVE_PANDAS and HAVE_SKLEARN, "optional research extra absent")
class R3HarnessTest(unittest.TestCase):
    def test_same_day_teacher_values_never_reach_that_day_features(self):
        stocks = synthetic_stocks()
        days = pd.Series(sorted(stocks["date"].unique()))
        market = synthetic_market(days)
        stock_id, day = "1002", days.iloc[100]
        builders = {"history": rf.stock_history_features,
                    "beta": lambda frame: rf.beta_features(frame, market)}
        for name, builder in builders.items():
            with self.subTest(builder=name):
                base = builder(stocks).set_index(["stock_id", "date"]).sort_index()
                moved = builder(_perturb_row(stocks, stock_id, day)).set_index(["stock_id", "date"]).sort_index()
                pd.testing.assert_series_equal(base.loc[(stock_id, day)], moved.loc[(stock_id, day)])
                # Earlier rows are untouched; the next row must react (else the test is vacuous).
                earlier = base.index.get_level_values("date") < day
                pd.testing.assert_frame_equal(base[earlier], moved[earlier])
                nxt = (stock_id, days.iloc[101])
                self.assertFalse(base.loc[nxt].equals(moved.loc[nxt]))


    def test_history_features_use_only_previous_rows(self):
        stocks = synthetic_stocks(n_stocks=1, n_days=40)
        hist = rf.stock_history_features(stocks).reset_index(drop=True)
        s = stocks.reset_index(drop=True)
        t = 30
        assert math.isclose(hist.loc[t, "intra_l1"], s.loc[t - 1, "close"] / s.loc[t - 1, "open"] - 1)
        assert math.isclose(hist.loc[t, "gap_l1"], s.loc[t - 1, "open"] / s.loc[t - 2, "close"] - 1)
        expected = np.mean([s.loc[i, "close"] / s.loc[i, "open"] - 1 for i in range(t - 5, t)])
        assert math.isclose(hist.loc[t, "intra_m5"], expected)
        assert math.isclose(hist.loc[t, "mom20"], s.loc[t - 1, "close"] / s.loc[t - 21, "close"] - 1)


    def test_folds_respect_embargo_and_never_share_dates(self):
        cal = pd.bdate_range("2020-01-02", "2025-12-31")
        folds = wf.make_folds(cal, test_start="2022-01-01", test_end="2025-12-31", refit="monthly")
        assert len(folds) == 48
        pos = {d: i for i, d in enumerate(cal)}
        for fold in folds:
            gap = pos[pd.Timestamp(fold.test_start)] - pos[pd.Timestamp(fold.train_end)] - 1
            assert gap >= 5
        weekly = wf.make_folds(cal, test_start="2025-01-01", test_end="2025-03-31", refit="weekly")
        assert len(weekly) >= 13
        with self.assertRaises(ValueError):
            wf.make_folds(cal, test_start="2022-01-01", test_end="2025-12-31", embargo=4)


    def test_dev_mode_refuses_protected_periods(self):
        for start, end in [("2025-06-01", "2026-01-15"), ("2026-02-01", "2026-03-01"),
                           ("2026-06-01", "2026-07-01"), ("2026-10-01", "2026-11-13")]:
            with self.assertRaises(ValueError):
                wf.check_period("dev", start, end)


    def test_protected_modes_only_accept_their_fixed_windows(self):
        wf.check_period("final_holdout", "2026-10-01", "2026-11-13")
        with self.assertRaises(ValueError):
            wf.check_period("final_holdout", "2026-10-01", "2026-12-01")
        with self.assertRaises(ValueError):
            wf.check_period("phase1_forecast", "2026-06-01", "2026-08-31")
        with self.assertRaises(ValueError):
            rx.resolve({"name": "x", "mode": "final_holdout"})


    def test_fast_daily_score_matches_official_scorer_and_decomposes(self):
        frame = _pred_frame()
        daily = wf.daily_table(frame)
        official = wf.official_check(frame[["stock_id", "date", "prediction"]],
                                     frame[["stock_id", "date", "adj_open", "adj_close", "y"]])
        fast = daily["sum_c"].sum() / daily["n"].sum()
        assert math.isclose(official.score, fast, rel_tol=1e-12, abs_tol=1e-15)
        parts = (daily["sum_mkt"].sum() + daily["sum_xs"].sum()) / daily["n"].sum()
        assert math.isclose(parts, fast, rel_tol=1e-9, abs_tol=1e-15)
        summary = wf.summarize(daily, reps=300)
        assert summary["ci95"][0] <= summary["score"] <= summary["ci95"][1]
        assert summary["n_keys"] == len(frame)
        zero = wf.paired_diff(daily, daily.copy(), reps=200)
        assert zero["diff"] == 0 and zero["ci95"] == [0.0, 0.0]


    def test_official_scorer_rejects_wrong_label_alignment(self):
        frame = _pred_frame()
        rows = [{"stock_id": s, "target_date": d.date().isoformat(), "prediction": int(p)}
                for s, d, p in zip(frame["stock_id"], frame["date"], frame["prediction"])]
        labels = [{"stock_id": s, "target_date": d.date().isoformat(), "y": 1 - int(y),
                   "adj_open": o, "adj_close": c}
                  for s, d, y, o, c in zip(frame["stock_id"], frame["date"], frame["y"],
                                           frame["adj_open"], frame["adj_close"])]
        with self.assertRaises(ValueError):
            evaluate_predictions(rows, labels)


    def test_preprocessor_statistics_come_from_training_rows_only(self):
        train = pd.DataFrame({"a": np.arange(100.0), "b": np.r_[np.arange(99.0), np.nan]})
        test = pd.DataFrame({"a": [1e9, -1e9], "b": [np.nan, 5.0]})
        pre = TrainOnlyPreprocessor(clip=0.01).fit(train)
        before = (pre.lo.copy(), pre.hi.copy(), pre.mean.copy(), pre.std.copy())
        out = pre.transform(test)
        assert np.all(np.isfinite(out))
        self.assertAlmostEqual(out[0, 0], (pre.hi[0] - pre.mean[0]) / pre.std[0])
        for old, new in zip(before, (pre.lo, pre.hi, pre.mean, pre.std)):
            np.testing.assert_array_equal(old, new)


    def test_rule_models(self):
        X = pd.DataFrame({"intra_l1": [0.01, -0.02, np.nan]})
        assert list(build_model({"family": "rule", "rule": "all0"}).decision(X)) == [-1, -1, -1]
        assert list(build_model({"family": "rule", "rule": "all1"}).decision(X)) == [1, 1, 1]
        assert list(build_model({"family": "rule", "rule": "prevday"}).decision(X)) == [1, -1, -1]


    def test_walk_forward_predictions_are_out_of_sample_and_top50_only(self):
        ff = _synthetic_feature_frame()
        cfg = rx.resolve({"name": "t", "family": "ridge", "params": {"alpha": 1.0},
                          "feature_groups": ["stock_hist"], "test_start": "2022-01-01",
                          "test_end": "2022-06-30"})
        pred, folds, cols = rx.run_predictions(cfg, ff, threads=1)
        assert set(pred["stock_id"]) == {"1000", "1001", "1002"}
        for fold in folds:
            part = pred[pred["fold"] == fold["index"]]
            assert part["date"].min() > pd.Timestamp(fold["train_end"])
        daily = wf.daily_table(pred)
        rx.verify_official(pred, ff, daily)

    def test_two_head_model_combines_market_and_stock_heads(self):
        ff = _synthetic_feature_frame()
        cfg = rx.resolve({"name": "t2", "family": "two_head", "params": {"market_alpha": 1.0},
                          "market_columns": ["intra_l1"],
                          "stock_model": {"family": "ridge", "params": {"alpha": 1.0}},
                          "feature_groups": ["stock_hist"], "test_start": "2022-01-01",
                          "test_end": "2022-03-31"})
        pred, folds, _ = rx.run_predictions(cfg, ff, threads=1)
        self.assertGreater(len(pred), 0)
        self.assertTrue(np.all(np.isfinite(pred["decision"])))
        for fold in folds:
            part = pred[pred["fold"] == fold["index"]]
            self.assertGreater(part["date"].min(), pd.Timestamp(fold["train_end"]))


if __name__ == "__main__":
    unittest.main()
