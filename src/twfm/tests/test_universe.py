"""股票池的測試：存活偏差、只用過去的金額、排除 ETF（不需要 torch）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from twfm.config import DataConfig
from twfm.data.align import prev_trading_day
from twfm.data.schema import is_common_stock
from twfm.data.synthetic import ETF_IDS, TDR_IDS, make_synthetic_market
from twfm.data.universe import build_universe, universe_audit


@pytest.fixture(scope="module")
def market():
    # 預設 2014-01-02 起 420 天：2014 年整年加 2015 年 1～8 月。
    return make_synthetic_market(seed=2)


def _year(u: pd.DataFrame, year: int) -> pd.DataFrame:
    return u[u["date"].dt.year == year].reset_index(drop=True)


def test_etf_and_tdr_excluded(market) -> None:
    cfg = DataConfig(lookback=20, universe_size=30, universe_refresh="monthly")
    u = build_universe(market.panel, market.calendar, cfg)
    assert len(u) > 0
    excluded = set(ETF_IDS) | set(TDR_IDS)
    assert not u["stock_id"].isin(list(excluded)).any()
    assert all(is_common_stock(s) for s in u["stock_id"].unique())
    assert u.groupby("date").size().max() <= cfg.universe_size

    # 對照：把 0050 改成普通股代號，成交金額最大的它就會進池（排除不是因為金額）。
    renamed = market.panel.copy()
    renamed["stock_id"] = renamed["stock_id"].astype(str).replace({"0050": "1000"})
    u2 = build_universe(renamed, market.calendar, cfg)
    assert "1000" in set(u2["stock_id"])


def test_rule3_filters_hold(market) -> None:
    cfg = DataConfig(lookback=40, universe_size=40, universe_refresh="monthly", min_close=10.0)
    u = build_universe(market.panel, market.calendar, cfg)
    assert len(u) > 0
    p = market.panel.sort_values(["stock_id", "date"]).reset_index(drop=True)
    p["rownum"] = p.groupby("stock_id").cumcount() + 1
    keys = u.copy()
    keys["i_date"] = prev_trading_day(market.calendar, u["date"]).to_numpy()
    merged = keys.merge(
        p[["date", "stock_id", "close", "rownum"]].rename(columns={"date": "i_date"}),
        on=["i_date", "stock_id"],
        how="left",
    )
    assert merged["close"].notna().all()  # i 那天有列
    assert (merged["close"] >= cfg.min_close).all()
    assert (merged["rownum"] >= cfg.lookback).all()
    # 有股票因為收盤低於 10 元被擋掉（低價股那檔）。
    low = p[(p["close"] < cfg.min_close) & (p["rownum"] >= cfg.lookback)]
    assert len(low) > 0


@pytest.mark.parametrize("refresh", ["monthly", "yearly"])
def test_delisted_stocks_enter_before_delisting(market, refresh: str) -> None:
    cfg = DataConfig(lookback=20, universe_size=60, universe_refresh=refresh)
    u = build_universe(market.panel, market.calendar, cfg)
    cal = market.calendar
    info = market.stock_info
    delisted = info[info["delisted"]]
    assert len(delisted) > 0
    found = 0
    for sid, last in zip(delisted["stock_id"], delisted["last_date"]):
        dates = u.loc[u["stock_id"] == sid, "date"]
        if len(dates) > 0:
            found += 1
        # 最晚只到最後一筆成交的下一個交易日（那天 i 有列，還不知道之後下市）。
        nxt = cal[cal.get_loc(last) + 1]
        assert (dates <= nxt).all()
    assert found >= 1


def test_yearly_list_uses_only_prior_year_amounts(market) -> None:
    cfg = DataConfig(lookback=20, universe_size=15, universe_refresh="yearly")
    base = build_universe(market.panel, market.calendar, cfg)
    # calendar 第一年（2014）沒有錨點，所以沒有股票池；2015 用 2014 的金額。
    assert (base["date"].dt.year >= 2015).all()
    assert len(_year(base, 2015)) > 0

    # 改掉 2015 年的金額，2015 年的名單完全不變。
    rng = np.random.default_rng(0)
    changed = market.panel.copy()
    in_2015 = (changed["date"].dt.year == 2015).to_numpy()
    changed.loc[in_2015, "amount"] = changed.loc[in_2015, "amount"] * rng.uniform(0.01, 100.0, int(in_2015.sum()))
    alt = build_universe(changed, market.calendar, cfg)
    pd.testing.assert_frame_equal(_year(base, 2015), _year(alt, 2015))

    # 對照：把一檔不在 2015 名單的股票 2014 年的金額放大，它就會進 2015 的名單。
    members = set(_year(base, 2015)["stock_id"])
    info = market.stock_info
    plain = info[(info["kind"] == "common") & ~info["delisted"] & ~info["late_listed"] & ~info["suspended"]]
    p15 = market.panel[market.panel["date"].dt.year == 2015]
    ok_close = set(p15.loc[p15["close"] >= 2.0 * cfg.min_close, "stock_id"])
    target = next(s for s in plain["stock_id"] if s not in members and s in ok_close)
    changed2 = market.panel.copy()
    sel = ((changed2["stock_id"] == target) & (changed2["date"].dt.year == 2014)).to_numpy()
    changed2.loc[sel, "amount"] = changed2.loc[sel, "amount"] * 1.0e4
    alt2 = build_universe(changed2, market.calendar, cfg)
    assert target in set(_year(alt2, 2015)["stock_id"])


def test_monthly_list_uses_only_prior_month_amounts(market) -> None:
    cfg = DataConfig(lookback=20, universe_size=15, universe_refresh="monthly")
    base = build_universe(market.panel, market.calendar, cfg)
    month = (base["date"].dt.year == 2015) & (base["date"].dt.month == 3)
    assert month.any()
    changed = market.panel.copy()
    later = (changed["date"] >= pd.Timestamp("2015-03-01")).to_numpy()
    changed.loc[later, "amount"] = changed.loc[later, "amount"][::-1].to_numpy()
    alt = build_universe(changed, market.calendar, cfg)
    alt_month = (alt["date"].dt.year == 2015) & (alt["date"].dt.month == 3)
    pd.testing.assert_frame_equal(base[month].reset_index(drop=True), alt[alt_month].reset_index(drop=True))


def test_universe_audit(market) -> None:
    cfg = DataConfig(lookback=20, universe_size=60, universe_refresh="yearly")
    u = build_universe(market.panel, market.calendar, cfg)
    audit = universe_audit(u, market.panel)
    assert list(audit.columns) == [
        "year",
        "n_days",
        "n_stocks",
        "n_delisted_later",
        "avg_per_day",
        "min_per_day",
        "max_per_day",
    ]
    row = audit[audit["year"] == 2015].iloc[0]
    assert row["n_stocks"] > 0
    assert row["n_delisted_later"] >= 1
    assert row["min_per_day"] <= row["avg_per_day"] <= row["max_per_day"]
