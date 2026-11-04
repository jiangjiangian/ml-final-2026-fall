"""Timing tests for R4 pre-open as-of alignment (synthetic data)."""

import importlib.util
import unittest

HAVE_PANDAS = importlib.util.find_spec("pandas") is not None

if HAVE_PANDAS:
    import numpy as np
    import pandas as pd

    from finpred.features import r4_raw as rr


@unittest.skipUnless(HAVE_PANDAS, "optional research extra absent")
class R4AsOfTest(unittest.TestCase):
    def setUp(self):
        self.days = pd.bdate_range("2023-01-02", periods=30)
        self.grid = pd.MultiIndex.from_product([self.days, ["1000", "2000"]],
                                               names=["date", "stock_id"]).to_frame(index=False)

    def test_stock_asof_uses_only_earlier_rows_and_ignores_missing_today(self):
        rows = self.grid.copy()
        rows["v"] = np.arange(len(rows), dtype=float)
        t = self.days[10]
        base = rr.stock_asof(rows, self.grid, ["v"]).set_index(["stock_id", "date"])
        moved = rows.copy()
        moved.loc[moved["date"] == t, "v"] = 1e9
        after = rr.stock_asof(moved, self.grid, ["v"]).set_index(["stock_id", "date"])
        pd.testing.assert_series_equal(base.loc[("1000", t)], after.loc[("1000", t)])
        self.assertNotEqual(base.loc[("1000", self.days[11]), "v"], after.loc[("1000", self.days[11]), "v"])
        # Removing stock 2000's row on t must not change any day-t value.
        dropped = rows[~((rows["stock_id"] == "2000") & (rows["date"] == t))]
        again = rr.stock_asof(dropped, self.grid, ["v"]).set_index(["stock_id", "date"])
        pd.testing.assert_frame_equal(base.xs(t, level="date"), again.xs(t, level="date"))

    def test_source_asof_never_uses_same_calendar_day_session(self):
        series = pd.DataFrame({"date": pd.date_range("2022-12-20", "2023-03-01"), "close": 1.0})
        series["close"] = np.arange(len(series), dtype=float)
        out = rr.source_asof(series, self.grid["date"], ["close"], prefix="x_").set_index("date")
        for t in self.days:
            expected = series.loc[series["date"] <= t - pd.Timedelta(days=1), "close"].iloc[-1]
            self.assertEqual(out.loc[t, "x_close"], expected)
        moved = series.copy()
        moved.loc[moved["date"] == self.days[5], "close"] = -1e9
        out2 = rr.source_asof(moved, self.grid["date"], ["close"], prefix="x_").set_index("date")
        self.assertEqual(out.loc[self.days[5], "x_close"], out2.loc[self.days[5], "x_close"])

    def test_global_same_day_columns_are_refused_for_same_row(self):
        g = pd.DataFrame({"date": self.days, "^TWII": np.arange(30.0), "^VIX": np.arange(30.0)})
        with self.assertRaises(ValueError):
            rr.global_prev_row(g, self.grid["date"], ["^TWII"], same_row_ok=True)
        prev = rr.global_prev_row(g, self.grid["date"], ["^TWII"]).set_index("date")
        self.assertEqual(prev.loc[self.days[5], "g_^TWII"], 4.0)
        same = rr.global_prev_row(g, self.grid["date"], ["^VIX"], same_row_ok=True).set_index("date")
        self.assertEqual(same.loc[self.days[5], "g_^VIX"], 5.0)


if __name__ == "__main__":
    unittest.main()
