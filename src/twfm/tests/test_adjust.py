"""還原權息、對數報酬、漲跌停的測試（不需要 torch）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from twfm.config import DataConfig
from twfm.data.adjust import (
    adjusted_levels,
    cumulative_factor,
    event_factors,
    limit_flags,
    limit_prices,
    log_returns,
    tick_size,
)
from twfm.data.schema import validate_panel
from twfm.data.synthetic import ETF_IDS, TDR_IDS, make_synthetic_market


def _panel(rows: list[tuple]) -> pd.DataFrame:
    """(date, stock_id, open, high, low, close, volume, amount, ref_price) 的 list 轉成 panel。"""
    df = pd.DataFrame(rows, columns=["date", "stock_id", "open", "high", "low", "close", "volume", "amount", "ref_price"])
    df["date"] = pd.to_datetime(df["date"]).astype("datetime64[ns]")
    df["market"] = "twse"
    for c in ("open", "high", "low", "close", "volume", "amount", "ref_price"):
        df[c] = df[c].astype(np.float64)
    return df


@pytest.fixture(scope="module")
def market():
    return make_synthetic_market(n_stocks=24, n_days=260, seed=3)


def test_limit_price_examples() -> None:
    cfg = DataConfig()
    up, dn = limit_prices(np.array([100.0, 15.3]), pd.DatetimeIndex(["2020-03-02", "2020-03-02"]), cfg)
    np.testing.assert_allclose(up, [110.0, 16.80])
    np.testing.assert_allclose(dn, [90.0, 13.80])
    up, dn = limit_prices(np.array([100.0]), pd.Timestamp("2010-03-01"), cfg)
    np.testing.assert_allclose(up, [107.0])
    np.testing.assert_allclose(dn, [93.0])


def test_limit_change_date_boundary() -> None:
    cfg = DataConfig()
    up, dn = limit_prices(np.array([100.0, 100.0]), pd.DatetimeIndex(["2015-05-29", "2015-06-01"]), cfg)
    np.testing.assert_allclose(up, [107.0, 110.0])
    np.testing.assert_allclose(dn, [93.0, 90.0])


def test_limit_prices_nan_ref() -> None:
    up, dn = limit_prices(np.array([np.nan, 50.0]), pd.Timestamp("2020-01-02"), DataConfig())
    assert np.isnan(up[0]) and np.isnan(dn[0])
    np.testing.assert_allclose([up[1], dn[1]], [55.0, 45.0])


def test_tick_size_brackets() -> None:
    p = np.array([9.99, 10.0, 49.95, 50.0, 99.9, 100.0, 499.5, 500.0, 999.0, 1000.0, np.nan])
    expected = np.array([0.01, 0.05, 0.05, 0.1, 0.1, 0.5, 0.5, 1.0, 1.0, 5.0, np.nan])
    np.testing.assert_allclose(tick_size(p), expected, equal_nan=True)


def test_ex_dividend_uses_ref_price() -> None:
    rows = [
        ("2020-07-01", "1101", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0e5, 100.0),
        ("2020-07-02", "1101", 95.5, 97.0, 95.0, 96.0, 2000.0, 1.9e5, 95.0),  # 除息 5 元
        ("2020-07-03", "1101", 96.0, 97.0, 95.5, 97.0, 3000.0, 2.9e5, np.nan),  # 參考價缺值，用前收 96
        ("2020-07-01", "2330", 50.0, 51.0, 49.0, 50.0, 500.0, 2.5e4, 50.0),
        ("2020-07-02", "2330", 50.5, 51.0, 50.0, 51.0, 600.0, 3.0e4, np.nan),
    ]
    panel = _panel(rows)
    # 打亂順序、換一組 index，確認結果是用 index 對回去。
    panel = panel.iloc[[4, 2, 0, 3, 1]]
    panel.index = [40, 20, 0, 30, 10]

    f = event_factors(panel)
    F = cumulative_factor(panel)
    r = log_returns(panel)
    adj = adjusted_levels(panel)

    assert list(f.index) == list(panel.index)
    np.testing.assert_allclose(f.loc[[0, 10, 20]].to_numpy(), [1.0, 0.95, 1.0])
    np.testing.assert_allclose(F.loc[[0, 10, 20]].to_numpy(), [1.0, 0.95, 0.95])
    np.testing.assert_allclose(f.loc[[30, 40]].to_numpy(), [1.0, 1.0])

    # 除息日的收盤到收盤報酬用參考價，不是前一天收盤。
    assert r.loc[10, "ret_cc"] == pytest.approx(np.log(96.0 / 95.0))
    assert r.loc[10, "ret_cc"] != pytest.approx(np.log(96.0 / 100.0))
    assert r.loc[10, "ret_gap"] == pytest.approx(np.log(95.5 / 95.0))
    assert r.loc[20, "ret_cc"] == pytest.approx(np.log(97.0 / 96.0))
    assert r.loc[10, "ret_oc"] == pytest.approx(np.log(96.0 / 95.5))
    assert r.loc[10, "ret_hl"] == pytest.approx(np.log(97.0 / 95.0))
    assert r.loc[10, "log_amount"] == pytest.approx(np.log1p(1.9e5))
    assert r.loc[0, "ret_cc"] == pytest.approx(0.0)
    assert r.loc[40, "ret_cc"] == pytest.approx(np.log(51.0 / 50.0))

    # 還原價的比等於還原報酬；量乘上累積因子；金額不變。
    np.testing.assert_allclose(adj.loc[[0, 10, 20], "adj_close"].to_numpy(), [100.0, 96.0 / 0.95, 97.0 / 0.95])
    assert adj.loc[10, "adj_close"] / adj.loc[0, "adj_close"] == pytest.approx(np.exp(r.loc[10, "ret_cc"]))
    np.testing.assert_allclose(adj.loc[[0, 10, 20], "adj_volume"].to_numpy(), [1000.0, 2000.0 * 0.95, 3000.0 * 0.95])
    np.testing.assert_allclose(adj["amount"].to_numpy(), panel["amount"].to_numpy())
    assert list(adj.columns) == ["adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "amount"]


def test_inputs_are_not_modified() -> None:
    rows = [
        ("2020-07-01", "1101", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0e5, np.nan),
        ("2020-07-02", "1101", 95.5, 97.0, 95.0, 96.0, 2000.0, 1.9e5, 95.0),
    ]
    panel = _panel(rows)
    before = panel.copy()
    event_factors(panel)
    adjusted_levels(panel)
    log_returns(panel)
    limit_flags(panel, DataConfig())
    pd.testing.assert_frame_equal(panel, before)


def test_limit_flags_and_streak() -> None:
    rows = [
        ("2020-03-02", "2330", 100.0, 110.0, 100.0, 110.0, 1000.0, 1.0e5, 100.0),  # 收漲停 110
        ("2020-03-03", "2330", 121.0, 121.0, 121.0, 121.0, 100.0, 1.2e4, np.nan),  # 一字漲停 121
        ("2020-03-04", "2330", 118.0, 120.0, 109.0, 109.0, 900.0, 1.0e5, np.nan),  # 跌停 109
        ("2020-03-05", "2330", 105.0, 106.0, 99.0, 100.0, 800.0, 8.0e4, np.nan),  # 都不是
    ]
    panel = _panel(rows)
    flags = limit_flags(panel, DataConfig())
    assert flags["close_at_up"].tolist() == [True, True, False, False]
    assert flags["open_at_up"].tolist() == [False, True, False, False]
    assert flags["close_at_down"].tolist() == [False, False, True, False]
    assert flags["open_at_down"].tolist() == [False, False, False, False]
    assert flags["limit_streak"].tolist() == [1, 2, -1, 0]


def test_limit_streak_down_run_and_reset_per_stock() -> None:
    rows = [
        ("2020-03-02", "1101", 50.0, 50.0, 45.0, 45.0, 1000.0, 4.5e4, 50.0),  # 跌停 45
        ("2020-03-03", "1101", 40.5, 40.5, 40.5, 40.5, 100.0, 4.0e3, np.nan),  # 跌停 40.5
        ("2020-03-02", "1102", 20.0, 22.0, 20.0, 22.0, 1000.0, 2.1e4, 20.0),  # 另一檔漲停，不接續 1101
    ]
    panel = _panel(rows)
    flags = limit_flags(panel, DataConfig())
    assert flags["limit_streak"].tolist() == [-1, -2, 1]


def test_point_in_time_adjustment(market) -> None:
    """改掉某天之後的事件，之前任何視窗標準化後的價格都不變；改掉視窗裡的事件就會變。"""
    panel = market.panel.reset_index(drop=True)
    cal = market.calendar
    cut = cal[150]
    lookback = 40
    base = adjusted_levels(panel)

    rng = np.random.default_rng(0)
    mod = panel.copy()
    after = (mod["date"] >= cut).to_numpy()
    hit = after & (rng.random(len(mod)) < 0.2)
    ref_after = mod.loc[hit, "ref_price"].fillna(100.0)
    mod.loc[hit, "ref_price"] = ref_after * rng.uniform(0.5, 1.5, int(hit.sum()))
    mod.loc[after, ["open", "high", "low", "close"]] = mod.loc[after, ["open", "high", "low", "close"]] * 1.3
    alt = adjusted_levels(mod)

    before = ~after
    np.testing.assert_allclose(alt.loc[before].to_numpy(), base.loc[before].to_numpy(), rtol=0, atol=0)

    def zwin(levels: pd.DataFrame, idx: np.ndarray) -> np.ndarray:
        w = levels.loc[idx, ["adj_open", "adj_high", "adj_low", "adj_close"]].to_numpy()
        return (w - w.mean()) / w.std()

    # 全域還原序列切出的視窗，和站在視窗最後一天往回還原的價格，標準化後一樣。
    f_all = event_factors(panel).to_numpy()
    checked = 0
    for sid, grp in panel[panel["date"] < cut].groupby("stock_id"):
        grp = grp.sort_values("date")
        if len(grp) < lookback:
            continue
        idx = grp.index.to_numpy()[-lookback:]
        np.testing.assert_allclose(zwin(base, idx), zwin(alt, idx), rtol=1e-12, atol=1e-12)
        f = f_all[idx]
        back_mult = np.ones(lookback)
        for k in range(lookback - 2, -1, -1):
            back_mult[k] = back_mult[k + 1] * f[k + 1]
        back = panel.loc[idx, ["open", "high", "low", "close"]].to_numpy() * back_mult[:, None]
        back_z = (back - back.mean()) / back.std()
        np.testing.assert_allclose(zwin(base, idx), back_z, rtol=1e-9, atol=1e-9)
        checked += 1
    assert checked > 5

    # 對照：在視窗中間加一個事件，標準化後的視窗就不同（測試不是空的）。
    sid = panel.loc[panel["date"] < cut, "stock_id"].value_counts().index[0]
    grp = panel[(panel["stock_id"] == sid) & (panel["date"] < cut)].sort_values("date")
    idx = grp.index.to_numpy()[-lookback:]
    mid = idx[lookback // 2]
    mod2 = panel.copy()
    mod2.loc[mid, "ref_price"] = panel.loc[idx[lookback // 2 - 1], "close"] * 0.8
    alt2 = adjusted_levels(mod2)
    assert not np.allclose(zwin(base, idx), zwin(alt2, idx))


def test_synthetic_has_required_events() -> None:
    m = make_synthetic_market()
    panel = m.panel
    cfg = DataConfig()
    validate_panel(panel)
    assert panel["ref_price"].isna().any()  # 有缺值的參考價（含每檔第一列）

    f = event_factors(panel)
    assert (f < 1 - 1e-3).sum() >= 5  # 除息、除權
    assert (f > 1 + 1e-3).any()  # 減資

    flags = limit_flags(panel, cfg)
    assert flags["open_at_up"].any()
    assert flags["open_at_down"].any()
    assert flags["close_at_up"].any()
    assert flags["close_at_down"].any()
    assert flags["limit_streak"].max() >= 2
    assert flags["limit_streak"].min() <= -1

    # 每個價格都在當天的漲跌停價之間，而且對齊升降單位。
    v = validate_panel(panel)
    up, dn = limit_prices(v["ref_price"].to_numpy(), v["date"], cfg)
    has_ref = np.isfinite(up)
    for c in ("open", "high", "low", "close"):
        x = v[c].to_numpy()
        assert (x[has_ref] <= up[has_ref] + 1e-9).all()
        assert (x[has_ref] >= dn[has_ref] - 1e-9).all()
        ticks = tick_size(x)
        assert np.allclose(np.round(x / ticks) * ticks, x, atol=1e-9)

    # 兩種漲跌幅都有、ETF 和 TDR 在、有下市和晚上市的股票、有千元股和跨 10 元的低價股。
    assert (panel["date"] < pd.Timestamp(cfg.limit_change_date)).any()
    assert (panel["date"] >= pd.Timestamp(cfg.limit_change_date)).any()
    ids = set(panel["stock_id"])
    assert set(ETF_IDS) <= ids and set(TDR_IDS) <= ids
    info = m.stock_info
    assert info["delisted"].any() and info["late_listed"].any()
    assert panel["close"].max() >= 1000.0
    low = panel.groupby("stock_id")["close"].agg(["min", "max"])
    assert ((low["min"] < 10.0) & (low["max"] >= 10.0)).any()
