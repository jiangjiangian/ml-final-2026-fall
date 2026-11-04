"""Phi-v1 timing and definition tests on synthetic data (no course data needed)."""

import importlib.util
import math
import unittest

HAVE_DEPS = all(importlib.util.find_spec(m) is not None for m in ("pandas", "exchange_calendars"))

if HAVE_DEPS:
    import numpy as np
    import pandas as pd

    from finpred.features import r4_phi
    from finpred.features.r4_raw import RawData


def synthetic_raw(seed=0, n_days=300):
    rng = np.random.default_rng(seed)
    cal = pd.bdate_range("2021-01-04", periods=n_days)
    stocks = [f"{1000 + k}" for k in range(100)]
    rows = []
    for sid in stocks:
        close = 100.0
        for day in cal:
            o = close * (1 + rng.normal(0, 0.01))
            c = o * (1 + rng.normal(0, 0.015))
            vol = float(rng.integers(1_000, 100_000))
            rows.append({"stock_id": sid, "date": day, "open": o, "close": c,
                         "high": max(o, c) * 1.01, "low": min(o, c) * 0.99, "trades": 10.0,
                         "turnover": vol * c, "volume": vol, "foreign_hold_pct": 30 + rng.normal(),
                         "foreign_net": rng.normal() * vol * 0.1, "trust_net": rng.normal() * vol * 0.05,
                         "dealer_net": 0.0, "dealer_hedge_net": 0.0, "rsi": 50.0, "sma": c,
                         "macd": 0.0, "atr": 1.0, "bb_upper": c * 1.05, "bb_mid": c,
                         "bb_lower": c * 0.95, "y": int(c > o)})
            close = c
    stock_frame = pd.DataFrame(rows).sort_values(["stock_id", "date"]).reset_index(drop=True)
    global_ = pd.DataFrame({"date": cal, "^VIX": 20.0, "^IXIC": 1.0, "^GSPC": 1.0, "^TWII": 1.0,
                            "^KS11": 1.0, "TX_OI": np.cumsum(rng.normal(0, 1000, len(cal)))})
    us = pd.bdate_range("2020-10-01", cal.max() + pd.Timedelta(days=5))

    def bars(scale):
        return pd.DataFrame({"date": us, "close": 100 * np.exp(np.cumsum(rng.normal(0, scale, len(us))))})

    raw = RawData(stocks=stock_frame, global_=global_, extra={"sox": bars(0.02)},
                  tw_calendar=pd.DatetimeIndex(cal), top50=stocks[:50], meta={})
    return raw, bars(0.01), bars(0.05)


@unittest.skipUnless(HAVE_DEPS, "optional research/data extras absent")
class PhiV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.gspc, cls.vix = synthetic_raw()
        cls.base = r4_phi.build_phi(cls.raw, gspc=cls.gspc, vix=cls.vix).set_index(["date", "stock_id"])

    def test_nothing_dated_t_reaches_features_of_t(self):
        cal = self.raw.tw_calendar
        t, nxt = cal[250], cal[251]
        raw2, gspc2, vix2 = synthetic_raw()
        s = raw2.stocks
        m = s["date"] == t
        for col in ("open", "close", "turnover", "volume", "foreign_net", "trust_net", "foreign_hold_pct"):
            s.loc[m, col] = s.loc[m, col] * 1.7 + (5.0 if col != "foreign_hold_pct" else 0.5)
        raw2.global_.loc[raw2.global_["date"] == t, "TX_OI"] += 1e6
        for frame in (raw2.extra["sox"], gspc2, vix2):
            frame.loc[frame["date"] >= t, "close"] *= 3.0
        moved = r4_phi.build_phi(raw2, gspc=gspc2, vix=vix2).set_index(["date", "stock_id"])
        before = self.base.xs(t, level="date")
        after = moved.xs(t, level="date")
        pd.testing.assert_frame_equal(before, after)
        self.assertFalse(self.base.xs(nxt, level="date").equals(moved.xs(nxt, level="date")))

    def test_shapes_ranges_and_neutral_fill(self):
        cols = r4_phi.CORE + r4_phi.SECONDARY
        self.assertEqual(len(cols), 16)
        self.assertFalse(self.base[cols].isna().any().any())
        late = self.base.xs(self.raw.tw_calendar[200], level="date")
        u50 = self.raw.top50
        for col in ("tug_of_war_20d", "foreign_flow_persistence", "lottery_max5e"):
            vals = late.loc[u50, col]
            self.assertTrue(vals.between(-0.5, 0.5).all())
            self.assertAlmostEqual(vals.mean(), 0.0, places=9)
            self.assertTrue((late.drop(index=u50)[col] == 0).all())
        for col in ("us_overnight_shock_z", "mkt_foreign_flow_z", "tx_foreign_net_oi_change_z",
                    "mkt_intraday_lag_z"):
            self.assertTrue(self.base[col].between(-4, 4).all())
            self.assertGreater((self.base[col] != 0).mean(), 0.5)

    def test_market_flow_and_calendar_definitions(self):
        cal = self.raw.tw_calendar
        t, d1 = cal[120], cal[119]
        s = self.raw.stocks
        row = s[s["date"] == d1]
        vwap = row["turnover"] / row["volume"]
        ff_d1 = (row["foreign_net"] * vwap).sum() / row["turnover"].sum()
        hist = []
        for d in cal[59:119]:  # 60 trading days ending at D2
            r = s[s["date"] == d]
            hist.append((r["foreign_net"] * r["turnover"] / r["volume"]).sum() / r["turnover"].sum())
        expected = float(np.clip(ff_d1 / np.std(hist[:-1] + [hist[-1]], ddof=1), -4, 4))
        got = self.base.loc[(t, "1000"), "mkt_foreign_flow_z"]
        # std window: 60 TW days ending at D2 = cal[59..118]
        hist2 = hist[:-1] if len(hist) > 60 else hist
        expected = float(np.clip(ff_d1 / np.std(
            [(s[s["date"] == d]["foreign_net"] * s[s["date"] == d]["turnover"] / s[s["date"] == d]["volume"]).sum()
             / s[s["date"] == d]["turnover"].sum() for d in cal[59:119]], ddof=1), -4, 4))
        self.assertAlmostEqual(got, expected, places=9)
        self.assertEqual(len(hist2), 60)
        monday = next(i for i in range(1, len(cal)) if (cal[i] - cal[i - 1]).days == 3)
        self.assertAlmostEqual(self.base.loc[(cal[monday], "1000"), "closure_length_log"], math.log(3))


if __name__ == "__main__":
    unittest.main()
