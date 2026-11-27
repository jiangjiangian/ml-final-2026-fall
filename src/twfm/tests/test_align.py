"""對齊協變量的測試：只用 t 開盤前已知的資訊（不需要 torch）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from twfm.config import DataConfig
from twfm.data.align import (
    align_us_overnight,
    build_covariates,
    cross_sectional_rank_gauss,
    institutional_features,
    margin_features,
    market_cov_columns,
    prev_trading_day,
    rolling_market_zscore,
    stock_cov_columns,
    stock_state_features,
)
from twfm.data.schema import is_common_stock
from twfm.data.synthetic import make_synthetic_market
from twfm.data.universe import build_universe

# 美股 2024 年 1 月：1/1 元旦、1/15 金恩紀念日（週一）休市。
_US_DATES = [
    "2024-01-02",
    "2024-01-03",
    "2024-01-04",
    "2024-01-05",
    "2024-01-08",
    "2024-01-09",
    "2024-01-10",
    "2024-01-11",
    "2024-01-12",
    "2024-01-16",
    "2024-01-17",
]


def _us_frame() -> pd.DataFrame:
    n = len(_US_DATES)
    ixic = 100.0 + np.arange(n)
    sox = 50.0 * np.exp(0.01 * np.arange(n) ** 1.5)
    df = pd.DataFrame(
        {
            "us_date": list(_US_DATES) * 2,
            "symbol": ["^IXIC"] * n + ["^SOX"] * n,
            "close": np.concatenate([ixic, sox]),
        }
    )
    df["us_date"] = pd.to_datetime(df["us_date"]).astype("datetime64[ns]")
    return df


def _scramble_panel(panel: pd.DataFrame, t0: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    """把 date ≥ t0 的價、量、金額、參考價每列各自換成亂數（仍然是合法的 K 棒）。

    每列獨立抽，同一天的比例（收盤 ÷ 開盤、最高 ÷ 最低）和當天的橫斷面排名都會變，
    所以 9 個狀態欄任何一欄偷看 ≥ t0 的列都會被抓到（整體乘一個倍數抓不到 ret_oc、ret_hl、amount_rank）。
    """
    p = panel.copy()
    for col in ("open", "high", "low", "close", "volume", "amount", "ref_price"):
        p[col] = p[col].astype("float64")
    m = (pd.to_datetime(p["date"]) >= t0).to_numpy()
    n = int(m.sum())
    assert n > 0
    o = rng.uniform(5.0, 900.0, n)
    c = rng.uniform(5.0, 900.0, n)
    p.loc[m, "open"] = o
    p.loc[m, "close"] = c
    p.loc[m, "high"] = np.maximum(o, c) * rng.uniform(1.0, 1.08, n)
    p.loc[m, "low"] = np.minimum(o, c) * rng.uniform(0.92, 1.0, n)
    p.loc[m, "ref_price"] = rng.uniform(5.0, 900.0, n)
    p.loc[m, "volume"] = np.round(rng.uniform(1e3, 1e8, n))
    p.loc[m, "amount"] = rng.uniform(1e5, 1e11, n)
    return p


def _corrupt_inputs(
    market, t0: pd.Timestamp, mode: str, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """panel、美股、法人、融資裡日期 ≥ t0 的列全部換成亂數；`truncate` 再刪掉日期 > t0 的列。

    回傳 `(panel, us_daily, inst_daily, margin_daily)`。美股收盤和融資餘額保持大於 0（`validate_us` 會檢查）。
    """
    rng = np.random.default_rng(seed)
    panel = _scramble_panel(market.panel, t0, rng)
    us = market.us_daily.copy()
    us["close"] = us["close"].astype("float64")
    m = (us["us_date"] >= t0).to_numpy()
    us.loc[m, "close"] = rng.uniform(100.0, 10000.0, int(m.sum()))
    inst = market.inst_daily.copy()
    m = (inst["date"] >= t0).to_numpy()
    for c in ("foreign_net", "trust_net", "dealer_net"):
        inst[c] = inst[c].astype("float64")
        inst.loc[m, c] = np.round(rng.uniform(-1.0e6, 1.0e6, int(m.sum())))
    margin = market.margin_daily.copy()
    margin["margin_balance"] = margin["margin_balance"].astype("float64")
    m = (margin["date"] >= t0).to_numpy()
    margin.loc[m, "margin_balance"] = np.round(rng.uniform(10.0, 1.0e6, int(m.sum())))
    if mode == "truncate":
        panel = panel.loc[pd.to_datetime(panel["date"]) <= t0].reset_index(drop=True)
        us = us.loc[us["us_date"] <= t0].reset_index(drop=True)
        inst = inst.loc[inst["date"] <= t0].reset_index(drop=True)
        margin = margin.loc[margin["date"] <= t0].reset_index(drop=True)
    return panel, us, inst, margin


def _ids_on(df: pd.DataFrame, day: pd.Timestamp) -> set[str]:
    return set(df.loc[df["date"] == day, "stock_id"].astype(str).tolist())


@pytest.fixture(scope="module")
def market():
    return make_synthetic_market(n_stocks=24, n_days=160, seed=5)


@pytest.fixture(scope="module")
def small_cfg() -> DataConfig:
    return DataConfig(lookback=20, universe_size=15, universe_refresh="monthly", beta_window=20)


def test_us_weekday_and_holiday_mapping() -> None:
    us = _us_frame()
    t = pd.DatetimeIndex(["2024-01-09", "2024-01-08", "2024-01-16", "2024-01-17"])
    out = align_us_overnight(us, t, ("^SOX", "^IXIC"))
    assert list(out.columns) == ["us_sox_ret", "us_sox_ret5", "us_ixic_ret", "us_ixic_ret5", "us_stale_days"]
    assert list(out.index) == list(t)

    def c(day: str) -> float:
        return 100.0 + _US_DATES.index(day)

    ts = pd.Timestamp
    # 週二的 t 用美國週一。
    assert out.loc[ts("2024-01-09"), "us_ixic_ret"] == pytest.approx(np.log(c("2024-01-08") / c("2024-01-05")))
    assert out.loc[ts("2024-01-09"), "us_stale_days"] == 1
    # 週一的 t 用美國週五。
    assert out.loc[ts("2024-01-08"), "us_ixic_ret"] == pytest.approx(np.log(c("2024-01-05") / c("2024-01-04")))
    assert out.loc[ts("2024-01-08"), "us_stale_days"] == 3
    # 美國週一放假：週二的 t 用週五，us_stale_days 變大；t 當天的美國那根（1/16）不能用。
    assert out.loc[ts("2024-01-16"), "us_ixic_ret"] == pytest.approx(np.log(c("2024-01-12") / c("2024-01-11")))
    assert out.loc[ts("2024-01-16"), "us_stale_days"] == 4
    assert out.loc[ts("2024-01-16"), "us_ixic_ret5"] == pytest.approx(np.log(c("2024-01-12") / c("2024-01-05")))
    assert out.loc[ts("2024-01-17"), "us_stale_days"] == 1
    # 5 根累計在前面不足 5 根時是 NaN。
    assert np.isnan(out.loc[ts("2024-01-08"), "us_ixic_ret5"])


def test_us_strictly_before_t() -> None:
    us = _us_frame()
    t = pd.DatetimeIndex(["2024-01-10"])
    base = align_us_overnight(us, t, ("^SOX", "^IXIC"))
    changed = us.copy()
    fut = (changed["us_date"] >= t[0]).to_numpy()
    changed.loc[fut, "close"] = changed.loc[fut, "close"] * 3.0
    pd.testing.assert_frame_equal(base, align_us_overnight(changed, t, ("^SOX", "^IXIC")))
    # 對照：改 t 前一根，特徵就會變。
    changed2 = us.copy()
    last = (changed2["us_date"] == pd.Timestamp("2024-01-09")).to_numpy()
    changed2.loc[last, "close"] = changed2.loc[last, "close"] * 1.1
    alt = align_us_overnight(changed2, t, ("^SOX", "^IXIC"))
    assert not np.isclose(alt["us_ixic_ret"].iloc[0], base["us_ixic_ret"].iloc[0])


def test_us_stale_days_falls_back_to_first_symbol() -> None:
    us = _us_frame()
    us = us[us["symbol"] == "^SOX"].reset_index(drop=True)
    t = pd.DatetimeIndex(["2024-01-16"])
    out = align_us_overnight(us, t, ("^SOX",))
    assert list(out.columns) == ["us_sox_ret", "us_sox_ret5", "us_stale_days"]
    assert out["us_stale_days"].iloc[0] == 4


def test_prev_trading_day() -> None:
    cal = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"])
    i = prev_trading_day(cal, pd.DatetimeIndex(["2024-01-08", "2024-01-05", "2024-01-03"]))
    assert list(i) == list(pd.DatetimeIndex(["2024-01-05", "2024-01-03", "2024-01-02"]))
    with pytest.raises(ValueError):
        prev_trading_day(cal, pd.DatetimeIndex(["2024-01-04"]))
    with pytest.raises(ValueError):
        prev_trading_day(cal, pd.DatetimeIndex(["2024-01-02"]))


def test_institutional_uses_only_day_i(market) -> None:
    cal = market.calendar
    t = cal[100]
    i = cal[99]
    base = institutional_features(market.inst_daily, market.panel, [t], cal)
    assert list(base.index.names) == ["date", "stock_id"]
    assert set(base.index.get_level_values("date")) == {t}
    # 每檔的值等於 i 那天的外資買超 ÷ i 那天的成交量。
    inst_i = market.inst_daily[market.inst_daily["date"] == i].set_index("stock_id")
    vol_i = market.panel[market.panel["date"] == i].set_index("stock_id")["volume"]
    ratio = base.xs(t, level="date")["foreign_ratio_i"]
    common = ratio.index.intersection(inst_i.index)
    assert len(common) > 5
    expected = inst_i.loc[common, "foreign_net"] / vol_i.loc[common]
    np.testing.assert_allclose(ratio.loc[common].to_numpy(), expected.to_numpy())
    # i 那天沒有法人列的股票是 NaN，不往前找（假資料隨機少的列不一定剛好落在 i，下面再明確拿掉幾列）。
    missing = ratio.index.difference(inst_i.index)
    assert ratio.loc[missing].isna().all()

    # 明確拿掉 i 那天 3 檔的法人列（前一天的列還在，往前找就會拿到值）：那 3 檔三欄都要是 NaN。
    inst_all = market.inst_daily
    base_t = base.xs(t, level="date")
    ids_i = _ids_on(inst_all, i)
    ids_prev = _ids_on(inst_all, cal[98])
    cand = [
        s
        for s in base_t.index.tolist()
        if s in ids_i
        and s in ids_prev
        and np.isfinite(base_t.loc[s, "foreign_ratio_i"])
        and np.isfinite(base_t.loc[s, "trust_streak_i"])
        and np.isfinite(base_t.loc[s, "dealer_ratio_i"])
    ]
    drop_ids = cand[:3]
    assert len(drop_ids) == 3
    hit = (inst_all["date"] == i).to_numpy() & inst_all["stock_id"].astype(str).isin(drop_ids).to_numpy()
    assert int(hit.sum()) == 3
    dropped = institutional_features(inst_all.loc[~hit], market.panel, [t], cal).xs(t, level="date")
    assert set(drop_ids) <= set(dropped.index.tolist())
    for c in ("foreign_ratio_i", "trust_streak_i", "dealer_ratio_i"):
        assert dropped.loc[drop_ids, c].isna().all(), f"{c}：i 那天沒有法人列卻有值（往前找了）"
    others = [s for s in base_t.index.tolist() if s not in set(drop_ids)]
    pd.testing.assert_frame_equal(dropped.loc[others], base_t.loc[others])

    # 改掉 ≥ t 的法人列，t 的特徵不變。
    changed = market.inst_daily.copy()
    fut = (changed["date"] >= t).to_numpy()
    for c in ("foreign_net", "trust_net", "dealer_net"):
        changed.loc[fut, c] = -3.0 * changed.loc[fut, c] + 7.0
    pd.testing.assert_frame_equal(base, institutional_features(changed, market.panel, [t], cal))

    # 對照：改 i 那天的列，特徵會變。
    changed2 = market.inst_daily.copy()
    at_i = (changed2["date"] == i).to_numpy()
    changed2.loc[at_i, "foreign_net"] = changed2.loc[at_i, "foreign_net"] + 1.0e6
    changed2.loc[at_i, "trust_net"] = -changed2.loc[at_i, "trust_net"]
    alt = institutional_features(changed2, market.panel, [t], cal)
    assert not np.allclose(alt["foreign_ratio_i"].to_numpy(), base["foreign_ratio_i"].to_numpy(), equal_nan=True)


def test_trust_streak_counts_runs() -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"])
    dates = pd.DatetimeIndex(dates).as_unit("ns")
    cal = pd.DatetimeIndex(list(dates) + [pd.Timestamp("2024-01-10")]).as_unit("ns")
    inst = pd.DataFrame(
        {
            "date": dates,
            "stock_id": "1101",
            "foreign_net": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "trust_net": [5.0, 3.0, 0.0, -2.0, -1.0, 4.0],
            "dealer_net": 0.0,
        }
    )
    panel = pd.DataFrame(
        {
            "date": dates,
            "stock_id": "1101",
            "market": "twse",
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 100.0,
            "amount": 1000.0,
            "ref_price": 10.0,
        }
    )
    out = institutional_features(inst, panel, cal[1:], cal)
    assert out["trust_streak_i"].tolist() == [1.0, 2.0, 0.0, -1.0, -2.0, 1.0]
    np.testing.assert_allclose(out["foreign_ratio_i"].to_numpy(), np.arange(1.0, 7.0) / 100.0)


def test_trust_streak_resets_on_traded_day_without_inst_row() -> None:
    """有成交但沒有法人列的那天要歸零（那天是 NaN）；停牌（沒有 panel 列）不中斷。"""
    cal = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
                "2024-01-09",
                "2024-01-10",
                "2024-01-11",
                "2024-01-12",
            ]
        )
    ).as_unit("ns")
    # 1101 在 01-09 停牌（沒有列）；01-04 有成交，但法人表沒有那天的列。
    traded = [d for d in cal[:-1] if d != pd.Timestamp("2024-01-09")]
    panel = pd.DataFrame(
        {
            "date": pd.DatetimeIndex(traded).as_unit("ns"),
            "stock_id": "1101",
            "market": "twse",
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 100.0,
            "amount": 1000.0,
            "ref_price": 10.0,
        }
    )
    trust = {
        "2024-01-02": 5.0,
        "2024-01-03": 3.0,
        "2024-01-05": 2.0,
        "2024-01-08": 1.0,
        "2024-01-10": 4.0,
        "2024-01-11": -2.0,
    }
    inst = pd.DataFrame(
        {
            "date": pd.DatetimeIndex(pd.to_datetime(list(trust))).as_unit("ns"),
            "stock_id": "1101",
            "foreign_net": 1.0,
            "trust_net": list(trust.values()),
            "dealer_net": 0.0,
        }
    )
    out = institutional_features(inst, panel, cal[1:], cal)
    # i = 01-09 停牌，t = 01-10 沒有列；其他 t 的 i 依序是 01-02、03、04、05、08、10、11。
    expected_t = pd.DatetimeIndex(
        pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-11", "2024-01-12"])
    )
    assert list(out.index.get_level_values("date")) == list(expected_t)
    np.testing.assert_array_equal(out["trust_streak_i"].to_numpy(), [1.0, 2.0, np.nan, 1.0, 2.0, 3.0, -1.0])
    np.testing.assert_allclose(out["foreign_ratio_i"].to_numpy(), [0.01, 0.01, np.nan, 0.01, 0.01, 0.01, 0.01])


def test_margin_uses_only_day_i(market) -> None:
    cal = market.calendar
    t = cal[100]
    i = cal[99]
    base = margin_features(market.margin_daily, [t], cal)
    assert list(base.columns) == ["margin_chg_i", "margin_chg5_i"]
    changed = market.margin_daily.copy()
    fut = (changed["date"] >= t).to_numpy()
    changed.loc[fut, "margin_balance"] = changed.loc[fut, "margin_balance"] * 5.0 + 1.0
    pd.testing.assert_frame_equal(base, margin_features(changed, [t], cal))
    # 數值：i 對前一列的變化率。
    m = market.margin_daily
    sid = base.index.get_level_values("stock_id")[0]
    rows = m[(m["stock_id"] == sid) & (m["date"] <= i)].sort_values("date")
    expected = rows["margin_balance"].iloc[-1] / rows["margin_balance"].iloc[-2] - 1.0
    assert base.loc[(t, sid), "margin_chg_i"] == pytest.approx(expected)
    # 對照：改 i 那天的餘額，特徵會變。
    changed2 = market.margin_daily.copy()
    at_i = (changed2["date"] == i).to_numpy()
    changed2.loc[at_i, "margin_balance"] = changed2.loc[at_i, "margin_balance"] * 2.0 + 5.0
    alt = margin_features(changed2, [t], cal)
    assert not np.allclose(alt["margin_chg_i"].to_numpy(), base["margin_chg_i"].to_numpy(), equal_nan=True)

    # 明確拿掉 i 那天 3 檔的融資列（前一天的列還在）：那 3 檔不能出現在 t 的結果裡（不往前找）。
    # 接到股票池時是 NaN，見 test_build_covariates_missing_inst_margin_rows_are_nan。
    m_all = market.margin_daily
    base_t = base.xs(t, level="date")
    ids_prev = _ids_on(m_all, cal[98])
    cand = [s for s in base_t.index.tolist() if s in ids_prev and np.isfinite(base_t.loc[s, "margin_chg_i"])]
    drop_ids = cand[:3]
    assert len(drop_ids) == 3
    hit = (m_all["date"] == i).to_numpy() & m_all["stock_id"].astype(str).isin(drop_ids).to_numpy()
    assert int(hit.sum()) == 3
    out = margin_features(m_all.loc[~hit], [t], cal)
    got = set(out.xs(t, level="date").index.tolist())
    assert not (set(drop_ids) & got), "i 那天沒有融資列的股票卻有值（往前找了）"


def test_stock_state_ignores_rows_from_t(market, small_cfg) -> None:
    cal = market.calendar
    t = cal[100]
    i = cal[99]
    base = stock_state_features(market.panel, [t], cal, small_cfg)
    # ≥ t 的列每列各自亂改：同一天的比例和橫斷面排名都會變，任何一欄偷看 t 都會被抓到。
    # beta 用整條累加和算視窗和，別檔的列改了會讓最後幾位小數不同，所以用預設的相對誤差比較。
    changed = _scramble_panel(market.panel, t, np.random.default_rng(0))
    pd.testing.assert_frame_equal(base, stock_state_features(changed, [t], cal, small_cfg))
    # 對照：亂改確實改到 t 那天的盤中報酬、振幅和金額排名（它們是 t+1 的 i 日特徵）。
    nxt = cal[101]
    base_n = stock_state_features(market.panel, [nxt], cal, small_cfg)
    alt_n = stock_state_features(changed, [nxt], cal, small_cfg)
    common = base_n.index.intersection(alt_n.index)
    assert len(common) > 5
    for c in ("ret_oc_i", "ret_hl_i", "amount_rank_i", "ret_cc_i", "ret_gap_i"):
        a = base_n.loc[common, c].to_numpy(dtype=np.float64)
        b = alt_n.loc[common, c].to_numpy(dtype=np.float64)
        assert not np.allclose(a, b, equal_nan=True), f"亂改沒有改到 {c}"
    # 對照：改 i 那天的收盤，ret_cc_i 會變。
    changed2 = market.panel.copy()
    at_i = (changed2["date"] == i).to_numpy()
    changed2.loc[at_i, "close"] = changed2.loc[at_i, "high"]
    alt = stock_state_features(changed2, [t], cal, small_cfg)
    assert not np.allclose(alt["ret_cc_i"].to_numpy(), base["ret_cc_i"].to_numpy(), equal_nan=True)
    assert base["beta_i"].notna().mean() > 0.5


def test_cross_sectional_rank_gauss() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 4 + ["2024-01-03"] * 2),
            "x": [3.0, 1.0, np.nan, 2.0, 5.0, 5.0],
        }
    )
    out = cross_sectional_rank_gauss(df, ["x"], by="date")
    q = norm.ppf([0.75, 0.25, 0.5])
    np.testing.assert_allclose(out["x"].to_numpy(), [q[0], q[1], 0.0, q[2], 0.0, 0.0], atol=1e-12)
    assert out["x_isna"].tolist() == [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    # by 也可以是 index level。
    out2 = cross_sectional_rank_gauss(df.set_index("date"), ["x"], by="date")
    np.testing.assert_allclose(out2["x"].to_numpy(), out["x"].to_numpy())


def test_rolling_market_zscore_is_causal() -> None:
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=300)).as_unit("ns")
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"a": rng.normal(size=300), "const": 1.0}, index=idx)
    z = rolling_market_zscore(df, window=250, min_periods=60)
    assert (z.iloc[:59] == 0.0).all().all()
    assert (z["const"] == 0.0).all()
    changed = df.copy()
    changed.iloc[200:, 0] = 1.0e6
    z2 = rolling_market_zscore(changed, window=250, min_periods=60)
    pd.testing.assert_frame_equal(z.iloc[:200], z2.iloc[:200])
    assert not np.isclose(z.iloc[200, 0], z2.iloc[200, 0])


def test_build_covariates_shapes(market, small_cfg) -> None:
    cal = market.calendar
    uni = build_universe(market.panel, cal, small_cfg)
    assert len(uni) > 0
    stock_cov, market_cov = build_covariates(
        market.panel, market.us_daily, market.inst_daily, market.margin_daily, None, cal, small_cfg
    )
    assert list(stock_cov.columns) == stock_cov_columns()
    assert list(stock_cov.index.names) == ["date", "stock_id"]
    assert len(stock_cov) == len(uni)
    got = stock_cov.index.to_frame(index=False)
    assert got["date"].tolist() == uni["date"].tolist()
    assert got["stock_id"].astype(str).tolist() == uni["stock_id"].astype(str).tolist()
    assert not stock_cov.isna().any().any()
    assert (stock_cov.dtypes == np.float32).all()
    assert list(market_cov.columns) == market_cov_columns(small_cfg.us_symbols)
    assert market_cov.index.equals(pd.DatetimeIndex(np.unique(uni["date"].to_numpy())))
    assert not market_cov.isna().any().any()
    assert (market_cov.dtypes == np.float32).all()
    # 美股報酬有變化（不是全部填 0）。
    assert market_cov["us_sox_ret"].abs().sum() > 0

    # 只要一部分日期時，同一天的值完全一樣（市場 z-score 用整條 calendar 算）。
    dates = market_cov.index
    sub = dates[len(dates) // 2 :]
    s_sub, m_sub = build_covariates(
        market.panel, market.us_daily, market.inst_daily, market.margin_daily, sub, cal, small_cfg
    )
    pd.testing.assert_frame_equal(m_sub, market_cov.loc[sub], check_freq=False)
    pd.testing.assert_frame_equal(s_sub, stock_cov.loc[stock_cov.index.get_level_values("date").isin(sub)])

    # 沒有法人、融資：那些欄是 0，`_isna` 是 1，欄位不變。
    s_none, _ = build_covariates(market.panel, market.us_daily, None, None, None, cal, small_cfg)
    assert list(s_none.columns) == stock_cov_columns()
    for c in ("foreign_ratio_i", "trust_streak_i", "dealer_ratio_i", "margin_chg_i", "margin_chg5_i"):
        assert (s_none[c] == 0.0).all()
        assert (s_none[f"{c}_isna"] == 1.0).all()


def test_synthetic_signal_visible_through_features() -> None:
    """假資料的訊號要透過對齊後的特徵看得到：t 的盤中報酬和 i 的外資比例正相關、和 i 的跳空負相關。

    假資料和對齊函式對「i 是哪一天」的理解不一致時，這裡的 IC 會接近 0。
    """
    m = make_synthetic_market()
    cal = m.calendar
    t = cal[30:]
    inst = institutional_features(m.inst_daily, m.panel, t, cal)
    state = stock_state_features(m.panel, t, cal, DataConfig(beta_window=20))
    feat = inst[["foreign_ratio_i"]].join(state[["ret_gap_i"]], how="inner").reset_index()
    feat["stock_id"] = feat["stock_id"].astype(str)
    p = m.panel[["date", "stock_id", "open", "close"]].copy()
    p["stock_id"] = p["stock_id"].astype(str)
    p["label"] = p["close"] / p["open"] - 1.0
    df = feat.merge(p[["date", "stock_id", "label"]], on=["date", "stock_id"], how="inner")
    df = df[df["stock_id"].map(is_common_stock).astype(bool)].copy()
    df["neg_gap"] = -df["ret_gap_i"]
    rng = np.random.default_rng(0)
    df["shuffled"] = df.groupby("date")["foreign_ratio_i"].transform(lambda s: rng.permutation(s.to_numpy()))

    def mean_ic(col: str) -> float:
        ics = []
        for _, g in df.groupby("date"):
            g = g[[col, "label"]].dropna()
            if len(g) >= 10:
                ics.append(g[col].rank().corr(g["label"].rank()))
        assert len(ics) > 100
        return float(np.nanmean(ics))

    assert mean_ic("foreign_ratio_i") > 0.03
    assert mean_ic("neg_gap") > 0.03
    assert abs(mean_ic("shuffled")) < 0.03


def test_market_cov_ignores_future_us_rows(market, small_cfg) -> None:
    cal = market.calendar
    _, base = build_covariates(market.panel, market.us_daily, None, None, None, cal, small_cfg)
    t = base.index[len(base) // 2]
    changed = market.us_daily.copy()
    fut = (changed["us_date"] >= t).to_numpy()
    changed.loc[fut, "close"] = changed.loc[fut, "close"] * 1.5
    _, alt = build_covariates(market.panel, changed, None, None, None, cal, small_cfg)
    upto = base.index <= t
    pd.testing.assert_frame_equal(base.loc[upto], alt.loc[upto], check_freq=False)
    later = base.index > t
    assert not np.allclose(base.loc[later].to_numpy(), alt.loc[later].to_numpy())


@pytest.mark.parametrize("mode", ["scramble", "truncate"])
def test_build_covariates_ignores_rows_from_t0(market, small_cfg, mode: str) -> None:
    """截斷測試：panel、美股、法人、融資 ≥ t0 的列全部亂改（或刪掉 > t0），t ≤ t0 的協變量完全不變。

    `build_covariates` 自己對 i、自己接法人和融資、自己算台股大盤欄，不經過單獨的特徵函式，
    所以要直接測它。用同一個股票池，兩邊的列一樣。
    """
    cal = market.calendar
    uni = build_universe(market.panel, cal, small_cfg)
    days = pd.DatetimeIndex(np.unique(uni["date"].to_numpy()))
    t0 = days[len(days) // 2]
    base_s, base_m = build_covariates(
        market.panel, market.us_daily, market.inst_daily, market.margin_daily, None, cal, small_cfg, universe=uni
    )
    panel, us, inst, margin = _corrupt_inputs(market, t0, mode, seed=3)
    alt_s, alt_m = build_covariates(panel, us, inst, margin, None, cal, small_cfg, universe=uni)
    assert base_s.index.equals(alt_s.index)
    assert base_m.index.equals(alt_m.index)

    s_dates = base_s.index.get_level_values("date")
    s_up = np.asarray(s_dates <= t0)
    assert (s_dates == t0).sum() >= 3, "t0 當天股票池太小"
    assert s_up.sum() > 100 and (~s_up).sum() > 100
    # rank-gauss 之後只看名次，beta 最後幾位小數的差異不影響；用預設的相對誤差比較。
    pd.testing.assert_frame_equal(base_s.loc[s_up], alt_s.loc[s_up])
    m_up = np.asarray(base_m.index <= t0)
    pd.testing.assert_frame_equal(base_m.loc[m_up], alt_m.loc[m_up], check_freq=False)

    # 對照：t0 以後的列確實變了（亂改有生效）。
    assert not np.allclose(base_s.loc[~s_up].to_numpy(), alt_s.loc[~s_up].to_numpy())
    assert not np.allclose(base_m.loc[~m_up].to_numpy(), alt_m.loc[~m_up].to_numpy())
    # t0 的下一個 t（i = t0）就要看到改過的值：個股欄和台股大盤欄都要變。
    nxt = days[days > t0][0]
    s_next = np.asarray(s_dates == nxt)
    assert not np.allclose(base_s.loc[s_next].to_numpy(), alt_s.loc[s_next].to_numpy())
    tw_cols = [c for c in base_m.columns if c.startswith("tw_")]
    assert not np.allclose(base_m.loc[[nxt], tw_cols].to_numpy(), alt_m.loc[[nxt], tw_cols].to_numpy())


def test_build_covariates_missing_inst_margin_rows_are_nan(market, small_cfg) -> None:
    """i 那天沒有法人、融資列的股票：那 5 欄是 0、`_isna` 是 1，不往前找（i 的前一天有列）。"""
    cal = market.calendar
    uni = build_universe(market.panel, cal, small_cfg)
    days = pd.DatetimeIndex(np.unique(uni["date"].to_numpy()))
    t = days[len(days) // 2]
    pos = int(cal.get_loc(t))
    i, i_prev = cal[pos - 1], cal[pos - 2]
    inst, margin = market.inst_daily, market.margin_daily
    uni_t = set(uni.loc[uni["date"] == t, "stock_id"].astype(str).tolist())
    cand = sorted(uni_t & _ids_on(inst, i) & _ids_on(inst, i_prev) & _ids_on(margin, i) & _ids_on(margin, i_prev))
    drop_ids = cand[:2]
    assert len(drop_ids) == 2

    base_s, _ = build_covariates(market.panel, market.us_daily, inst, margin, [t], cal, small_cfg, universe=uni)
    hit_i = (inst["date"] == i).to_numpy() & inst["stock_id"].astype(str).isin(drop_ids).to_numpy()
    hit_m = (margin["date"] == i).to_numpy() & margin["stock_id"].astype(str).isin(drop_ids).to_numpy()
    assert int(hit_i.sum()) == 2 and int(hit_m.sum()) == 2
    alt_s, _ = build_covariates(
        market.panel, market.us_daily, inst.loc[~hit_i], margin.loc[~hit_m], [t], cal, small_cfg, universe=uni
    )
    cols = ("foreign_ratio_i", "trust_streak_i", "dealer_ratio_i", "margin_chg_i", "margin_chg5_i")
    for sid in drop_ids:
        # 對照：沒拿掉時這幾欄有值。
        for c in ("foreign_ratio_i", "trust_streak_i", "dealer_ratio_i", "margin_chg_i"):
            assert base_s.loc[(t, sid), f"{c}_isna"] == 0.0, (sid, c)
        for c in cols:
            assert alt_s.loc[(t, sid), f"{c}_isna"] == 1.0, (sid, c)
            assert alt_s.loc[(t, sid), c] == 0.0, (sid, c)
    # 個股的價量狀態欄不受影響（只有法人、融資那幾欄變）。
    state_cols = [c for c in stock_cov_columns() if c.startswith(("ret_", "close_at", "limit_streak", "beta", "amount_rank"))]
    for sid in drop_ids:
        np.testing.assert_allclose(
            alt_s.loc[(t, sid), state_cols].to_numpy(dtype=np.float64),
            base_s.loc[(t, sid), state_cols].to_numpy(dtype=np.float64),
        )
