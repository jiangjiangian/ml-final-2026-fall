"""features.py：yfinance 清理、交易日、lag、usd_twd_am，以及和 data-collection 凍結資料的對照測試 (a)、(a2)。

對照測試的規格見 memory/projects/features.md「對照測試」。
"""

import copy
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src import crawler, features, utils

REF = utils.ROOT / "tests" / "fixtures" / "data-collection"
CFG = utils.load_config()
MAIN_RULES = ("bad_tick", "bond_holiday", "placeholder", "split", "dividend")
MANIFEST_KEYS = {"bad_ticks_dropped": ("bad_tick", "date"), "bond_holiday_bars_dropped": ("bond_holiday", "date"),
                 "placeholder_bars_dropped": ("placeholder", "date"),
                 "split_adjustments": ("split", "yahoo_adjustment_boundary"),
                 "dividend_adjustments_rescaled": ("dividend", "ex_date")}
needs_reference = pytest.mark.skipif(not (REF / "transform" / "panel_lag.csv.gz").exists(),
                                     reason="沒有 tests/fixtures/data-collection")


def cfg_with(lags=None, **crawler_overrides):
    cfg = copy.deepcopy(CFG)
    if lags is not None:
        cfg["features"]["lags"] = lags
    cfg["crawler"].update(crawler_overrides)
    return cfg


# ---------------------------------------------------------------- 對照測試 (a)：凍結資料重算長表


@pytest.fixture(scope="module")
def frozen():
    cfg = cfg_with(lags=[1, 2, 5])
    raw = features.load_raw(cfg, teacher_dir=utils.ROOT / "data" / "raw" / "teacher" / "training",
                            live_dir=REF / "teacher_live", yf_dir=REF / "extra" / "yfinance")
    return raw, features.build_features(raw, cfg)


@needs_reference
def test_frozen_files_need_no_cleaning(frozen):
    raw, _ = frozen
    assert raw["cleaning"] == []


@needs_reference
def test_calendar_is_1660_days_without_typhoon_day(frozen):
    _, df = frozen
    days = df["date"].unique()
    assert len(days) == 1660
    assert days[0] == "2020-01-02" and days[-1] == "2026-11-04"
    assert "2026-10-23" not in set(days)
    assert len(df) == 1660 * 100


@needs_reference
def test_lags_and_labels_match_panel_lag(frozen):
    """stock_ret 和 24 個市場序列的 lag2、lag5 和舊長表逐格相同，空白位置也一樣。"""
    _, df = frozen
    panel = pd.read_csv(REF / "transform" / "panel_lag.csv.gz", dtype={"stock_id": str, "date": str},
                        float_precision="round_trip")
    assert (df["date"].to_numpy() == panel["date"].to_numpy()).all()
    assert (df["stock_id"].to_numpy() == panel["stock_id"].to_numpy()).all()
    assert (df["is_top50"].to_numpy() == panel["is_top50"].to_numpy()).all()
    columns = [c for c in panel.columns if "_ret_lag" in c]
    assert len(columns) == 50
    different = {c: int((~((df[c] == panel[c]) | (df[c].isna() & panel[c].isna()))).sum())
                 for c in columns if not np.array_equal(df[c].to_numpy(float), panel[c].to_numpy(float), equal_nan=True)}
    assert different == {}
    label_y = df["label_y"].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
    assert np.array_equal(label_y, panel["label_y"].to_numpy(float), equal_nan=True)
    assert np.array_equal(df["label_intraday_return"].to_numpy(float),
                          panel["label_intraday_return"].to_numpy(float), equal_nan=True)


@needs_reference
def test_lag2_non_missing_days(frozen):
    _, df = frozen
    first = df.groupby("date").first()
    counts = {s: int(first[f"{s}_ret_lag2"].notna().sum())
              for s in ("sox", "usd_twd", "us13w", "etf_0050", "n225", "teacher_vix", "teacher_ixic",
                        "teacher_gspc", "teacher_twii", "teacher_ks11")}
    assert counts == {"sox": 1603, "usd_twd": 1654, "us13w": 1585, "etf_0050": 1649, "n225": 1552,
                      "teacher_vix": 1545, "teacher_ixic": 1545, "teacher_gspc": 1545, "teacher_twii": 1545,
                      "teacher_ks11": 1545}


@needs_reference
@pytest.mark.parametrize("stock_id, column, t, lag1, lag2", [
    ("2330", "stock", "2026-11-04", "-0.015021459227467818", "-0.03164556962025325"),
    ("2330", "stock", "2026-10-27", "-0.014462809917355376", "-0.00831600831600827"),
    ("2330", "sox", "2026-11-04", "0.02634213957551902", "-0.008270284379704918"),
    ("2330", "sox", "2026-10-27", "-0.06723524369545192", "-0.04890450322862169"),
    ("2330", "sox", "2026-09-08", "nan", "nan"),   # i = 9/07 是美國勞動節，SOX 沒有那根
    ("2330", "teacher_vix", "2026-10-27", "-0.10418906802463328", "-0.10418906802463328"),
])
def test_lag1_known_values(frozen, stock_id, column, t, lag1, lag2):
    """lag1 沒有舊長表可以比，用 features.md 記的測試值（凍結資料算過兩次）。"""
    _, df = frozen
    row = df[(df["date"] == t) & (df["stock_id"] == stock_id)].iloc[0]
    assert (repr(float(row[f"{column}_ret_lag1"])), repr(float(row[f"{column}_ret_lag2"]))) == (lag1, lag2)


@needs_reference
def test_suspended_stock_lag_spans_the_gap(frozen):
    """2327 在 2022-10-20～10-28 停牌：t = 11/01 的 i 是 10/31，i−1 是 10/19；停牌期間的 lag 都空白。"""
    _, df = frozen
    rows = df[df["stock_id"] == "2327"].set_index("date")
    assert repr(float(rows.loc["2022-11-01", "stock_ret_lag1"])) == "0.09880239520958087"
    assert rows.loc["2022-10-21":"2022-10-31", "stock_ret_lag1"].isna().all()


# ---------------------------------------------------------------- 對照測試 (a2)：清理 Yahoo 原樣


@pytest.fixture(scope="module")
def raw_0820473():
    out = {}
    for name, ticker in CFG["yfinance"]["tickers"].items():
        rows = features.read_yfinance(REF / "yfinance_raw_0820473" / f"{name}.csv")
        out[name] = features.clean_series(rows, name, ticker, CFG)
    return out


def manifest_records(last_day):
    series = json.loads((REF / "extra" / "manifest.json").read_text(encoding="utf-8"))["series"]
    out = {}
    for name, entry in series.items():
        for key, (rule, date_key) in MANIFEST_KEYS.items():
            for r in entry["cleaning"][key]:
                if r[date_key] <= last_day:
                    out[name, rule, r[date_key]] = r
    return out


@needs_reference
def test_cleaning_records_match_manifest(raw_0820473):
    """56 筆：壞報價 2、債市假日 22、佔位 25、分割 1、股利 6。和 manifest 的 62 筆差 10/12、10/23 那 6 筆。"""
    expected = manifest_records("2026-08-31")
    got = {(r["series"], r["rule"], r["date"]): r for _, records in raw_0820473.values() for r in records}
    assert set(got) == set(expected)
    counts = {rule: sum(k[1] == rule for k in got) for rule in MAIN_RULES}
    assert counts == {"bad_tick": 2, "bond_holiday": 22, "placeholder": 25, "split": 1, "dividend": 6}
    split = got["etf_0052", "split", "2025-11-17"]
    assert split["factor"] == 7.0
    for key, r in got.items():
        if key[1] == "dividend":
            assert abs(r["yahoo_fraction"] - expected[key]["yahoo_fraction"]) < 2e-6
            assert abs(r["rescaled_fraction"] - expected[key]["rescaled_fraction"]) < 1e-5


@needs_reference
def test_cleaned_prices_match_frozen_files(raw_0820473):
    """日期、開高低收、成交量完全相同；adj_close 是 Yahoo 後來重算的，相對差 ≤ 2e-6（實測 6.7e-7）。"""
    for name, (kept, _) in raw_0820473.items():
        frozen = [r for r in features.read_yfinance(REF / "extra" / "yfinance" / f"{name}.csv")
                  if r["date"] <= "2026-08-31"]
        kept = [r for r in kept if r["date"] <= "2026-08-31"]
        assert [r["date"] for r in kept] == [r["date"] for r in frozen], name
        for a, b in zip(kept, frozen):
            assert [a[k] for k in ("open", "high", "low", "close", "volume")] == \
                   [b[k] for k in ("open", "high", "low", "close", "volume")], (name, a["date"])
            assert abs(a["adj_close"] / b["adj_close"] - 1) <= 2e-6, (name, a["date"])


@needs_reference
@pytest.mark.parametrize("name, day", [
    ("usd_twd", "2020-03-31"), ("etf_006201", "2021-09-13"),     # 超出高低區間不到 0.5%
    ("us10y", "2023-11-10"),                                     # 退伍軍人節，但不是平盤
    ("etf_0050", "2025-04-07"), ("etf_0050", "2025-04-10"),      # 跌停平盤，成交量正常
    ("etf_0052", "2025-04-07"), ("etf_0052", "2025-04-10"),
    ("etf_006201", "2023-11-01"),                                # 平盤，成交量是中位數的 5%
    ("etf_0055", "2020-09-18"),                                  # close 等於前一列，成交量是中位數的 25%
])
def test_counterexamples_are_kept(raw_0820473, name, day):
    kept, _ = raw_0820473[name]
    assert day in {r["date"] for r in kept}


# ---------------------------------------------------------------- 清理的單元測試


def bar(day, close, *, open_=None, high=None, low=None, adj=None, volume=1000.0):
    return {"date": day, "open": close if open_ is None else open_, "high": close if high is None else high,
            "low": close if low is None else low, "close": close, "adj_close": close if adj is None else adj,
            "volume": volume}


def weekdays(n, start="2025-01-06"):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_nonpositive_close_and_duplicates_drop_only_that_row():
    """使用者 2026-11-06：只丟那一列；重複的日期留最後一列。舊程式會讓整個序列失敗。"""
    d = weekdays(4)
    rows = [bar(d[0], 10, high=11, low=9), bar(d[1], -1.0, high=11, low=-2), bar(d[2], 10.5, high=11, low=9),
            bar(d[2], 10.6, high=11, low=9), bar(d[3], 10.7, high=11, low=9)]
    kept, records = features.clean_series(rows, "sox", "^SOX", CFG)
    assert [(r["date"], r["close"]) for r in kept] == [(d[0], 10), (d[2], 10.6), (d[3], 10.7)]
    assert [(r["rule"], r["date"]) for r in records] == [("nonpositive_close", d[1]), ("duplicate_date", d[2])]


def test_futures_and_yields_keep_nonpositive_close():
    rows = [bar("2020-04-17", 18.27, high=19, low=17), bar("2020-04-20", -37.63, high=17.85, low=-40.32)]
    kept, records = features.clean_series(rows, "wti", "CL=F", CFG)
    assert len(kept) == 2 and records == []


def test_empty_close_row_is_removed_not_left_blank():
    d = weekdays(3)
    rows = [bar(d[0], 10), {**bar(d[1], 10), "close": None}, bar(d[2], 11)]
    kept, records = features.clean_series(rows, "sox", "^SOX", CFG)
    assert [r["date"] for r in kept] == [d[0], d[2]]
    assert [r["rule"] for r in records] == ["empty_close"]


def test_partial_bar_uses_upper_median():
    """前面成交量 [100, 200]：上中位數 200 的 1% 是 2，量 1.5 算不完整K棒；用一般中位數 150 就不會丟。"""
    d = weekdays(3)
    rows = [bar(d[0], 10, high=11, low=9, volume=100.0), bar(d[1], 10.5, high=11, low=9, volume=200.0),
            bar(d[2], 10.2, volume=1.5)]
    kept, records = features.clean_series(rows, "etf_0050", "0050.TW", CFG)
    assert [r["date"] for r in kept] == d[:2]
    assert [(r["rule"], r["date"]) for r in records] == [("placeholder", d[2])]


def test_reverse_split_fixes_prices_without_dividend_rescale():
    """反向合併（使用者交給 Claude 決定）：價格和成交量照樣修，但不做 R5 的股利乘回。"""
    d = weekdays(4)
    rows = [bar(d[0], 10.0, high=10.5, low=9.5, adj=9.0), bar(d[1], 10.2, high=10.5, low=9.5, adj=10.1),
            bar(d[2], 50.5, high=52, low=49, adj=50.5), bar(d[3], 51.0, high=52, low=49, adj=51.0)]
    kept, records = features.clean_series(rows, "etf_0050", "0050.TW", CFG)
    assert [r["rule"] for r in records] == ["reverse_split"]
    assert [kept[0][k] for k in ("close", "adj_close", "volume")] == pytest.approx([50.0, 45.0, 200.0])
    assert rows[0]["close"] == 10.0                                       # 傳進來的列不會被改到


def test_split_outside_taiwan_is_only_recorded():
    d = weekdays(2)
    rows = [bar(d[0], 100.0, high=101, low=99), bar(d[1], 10.0, high=10.1, low=9.9)]
    kept, records = features.clean_series(rows, "nvda", "NVDA", CFG)
    assert [r["close"] for r in kept] == [100.0, 10.0]
    assert [r["rule"] for r in records] == ["suspected_split_not_applied"]


def test_bond_holiday_dates():
    assert features.is_bond_holiday("2026-10-12") and features.is_bond_holiday("2026-11-11")
    assert features.is_bond_holiday("2023-11-10")      # 11/11 是週六，提前一天
    assert features.is_bond_holiday("2029-11-11") is False and features.is_bond_holiday("2029-11-12")   # 週日順延
    assert features.is_bond_holiday("2026-10-19") is False


def test_k_returns_blank_when_either_end_is_missing_or_not_positive():
    dates = ["d1", "d2", "d3", "d4"]
    assert features.k_returns(dates, [10.0, None, 12.0, 15.0], 1) == {"d4": 0.25}
    assert features.k_returns(dates, [10.0, -1.0, 12.0, 15.0], 2) == {"d3": 0.2}


# ---------------------------------------------------------------- 交易日


def stock_row(day, close=10.0, *, open_=10.0, y="1", foreign="0"):
    row = [""] * len(crawler.STOCK_COLUMNS)
    row[0] = day
    row[crawler.COL_CLOSE], row[crawler.COL_OPEN], row[crawler.COL_Y] = str(close), str(open_), y
    row[crawler.STOCK_COLUMNS.index("institutional_investors_trading_summary:投信買賣超股數")] = foreign
    return row


def test_trading_days_need_min_stocks_filled():
    stocks = {"A": {"d1": stock_row("d1"), "d2": stock_row("d2"), "d3": stock_row("d3", -1, open_=-1, y="-1")},
              "B": {"d1": stock_row("d1"), "d3": stock_row("d3", -1, open_=-1, y="-1")},
              "C": {"d1": stock_row("d1"), "d2": stock_row("d2"), "d3": stock_row("d3", -1, open_=-1, y="-1")}}
    assert crawler.trading_days(stocks, 2) == ["d1", "d2"]      # B 在 d2 停牌也算；d3 整天 -1 不算
    assert crawler.trading_days(stocks, 3) == ["d1"]


def test_closed_day_with_values_stops():
    stocks = {"A": {"d1": stock_row("d1"), "d2": stock_row("d2")}}
    assert crawler.trading_days(stocks, 1, ["d3"]) == ["d1", "d2"]
    with pytest.raises(crawler.CrawlerError):
        crawler.trading_days(stocks, 1, ["d2"])


# ---------------------------------------------------------------- 合成資料：t 那列、usd_twd_am


def small_cfg(**am):
    cfg = cfg_with(min_stocks_filled=2, closed_days=[])
    cfg["yfinance"]["tickers"] = {"usd_twd": "TWD=X"}
    cfg["features"]["teacher_global"] = ["^VIX"]
    cfg["features"]["model_series"] = ["stock", "usd_twd", "teacher_vix", "usd_twd_am"]
    cfg["features"]["usd_twd_am"].update(am)
    return cfg


def small_raw(days, hourly=None):
    stocks = {c: {d: stock_row(d, 10 + j + (c == "B")) for j, d in enumerate(days)} for c in ("A", "B")}
    glob = {d: [d, str(20 + j), "", "", "", "", ""] for j, d in enumerate(days)}
    yf = [bar(d, 30 + j) for j, d in enumerate(days)]
    return {"stocks": stocks, "global": glob, "top50": {"A"}, "yfinance": {"usd_twd": yf}, "hourly": hourly,
            "cleaning": [], "warnings": []}


def hour(start, close):
    return {"start": datetime.fromisoformat(start), "open": close, "high": close, "low": close, "close": close,
            "volume": 0.0}


def test_prediction_day_row():
    days = weekdays(5)
    raw = small_raw(days)
    t = "2025-01-13"
    df = features.build_features(raw, small_cfg(), t)
    assert list(df["date"].unique()) == days + [t]
    last = df[df["date"] == t]
    assert last["label_y"].isna().all() and last["label_intraday_return"].isna().all()
    a = last.set_index("stock_id").loc["A"]
    assert a["stock_ret_lag1"] == (14 - 13) / 13            # i = 1/10
    assert a["teacher_vix_ret_lag2"] == (24 - 22) / 22
    assert a["usd_twd_ret_lag1"] == (34 - 33) / 33


def test_usd_twd_am_hourly_and_backfill():
    """分界日前用日K；分界日起取 06:00 前最後一根 1h，冬令週一取到週五收盤；t 用自己的值。"""
    days = ["2024-01-18", "2024-01-19", "2024-01-22", "2024-01-23"]       # 1/22 是週一
    hourly = [hour("2024-01-20T05:00:00+08:00", 31.0),     # 週五 16:00 紐約收盤那根（台北週六 05:00 開始）
              hour("2024-01-23T05:00:00+08:00", 31.5),
              hour("2024-01-23T06:00:00+08:00", 99.0),     # 06:00 開始的那根 07:00 才結束，不能用
              hour("2024-01-24T04:00:00+08:00", 32.0)]
    raw = small_raw(days[:3] + ["2024-01-23"], hourly)
    cfg = small_cfg(hourly_from="2024-01-20")
    x = features.usd_twd_am_values(days + ["2024-01-24"], raw, cfg)
    assert x == [30, 31, 31.0, 31.5, 32.0]
    df = features.build_features(raw, cfg, "2024-01-24")
    t_row = df[df["date"] == "2024-01-24"].iloc[0]
    assert t_row["usd_twd_am_ret_lag1"] == (32.0 - 31.5) / 31.5
    assert t_row["usd_twd_am_ret_lag2"] == (32.0 - 31.0) / 31.0


def test_usd_twd_am_lookback_cap():
    """最多往回 4 天：週五 06:00 結束的那根，下週一還能用，下週三就太舊了。"""
    hourly = [hour("2024-01-19T05:00:00+08:00", 31.0)]
    raw = small_raw(["2024-01-19"], hourly)
    cfg = small_cfg(hourly_from="2024-01-01")
    assert features.usd_twd_am_values(["2024-01-19", "2024-01-22", "2024-01-24"], raw, cfg) == [31.0, 31.0, None]


def test_hourly_switch_follows_the_file():
    """1h 檔的第一天比 config 晚時，分界跟著檔案走，中間不會空一段；沒有 1h 檔時用 config 的日期。"""
    cfg = small_cfg(hourly_from="2024-01-22")
    assert features.hourly_switch(None, cfg) == date(2024, 1, 22)
    assert features.hourly_switch([hour("2024-03-04T05:00:00+08:00", 31)], cfg) == date(2024, 3, 4)
    assert features.hourly_switch([hour("2024-03-04T07:00:00+08:00", 31)], cfg) == date(2024, 3, 5)
    assert features.hourly_switch([hour("2023-12-01T05:00:00+08:00", 31)], cfg) == date(2024, 1, 22)


def test_missing_hourly_file_blanks_after_switch(tmp_path):
    days = ["2024-01-18", "2024-01-19", "2024-01-22"]
    raw = small_raw(days)
    x = features.usd_twd_am_values(days, raw, small_cfg(hourly_from="2024-01-22"))
    assert x == [30, 31, None]


def test_model_columns_are_28():
    columns = features.model_columns(CFG)
    assert len(columns) == 28
    assert columns[:2] == ["stock_ret_lag1", "stock_ret_lag2"]
    assert "usd_twd_am_ret_lag2" in columns and "us10y_ret_lag1" in columns


def test_unknown_model_series_stops():
    cfg = small_cfg()
    cfg["features"]["model_series"] = ["stock", "nope"]
    with pytest.raises(features.FeatureError):
        features.build_features(small_raw(weekdays(3)), cfg)


def test_csv_round_trip(tmp_path):
    df = features.build_features(small_raw(weekdays(5)), small_cfg())
    path = tmp_path / "f.csv.gz"
    path.write_bytes(features.to_csv_gz(df))
    back = pd.read_csv(path, dtype={"stock_id": str, "date": str}, float_precision="round_trip")
    assert list(back.columns) == list(df.columns)
    for c in df.columns:
        if c in ("date", "stock_id"):
            assert (back[c] == df[c]).all()
        else:
            assert np.array_equal(back[c].to_numpy(float), df[c].astype("Float64").to_numpy(float, na_value=np.nan),
                                  equal_nan=True), c
    assert features.to_csv_gz(df) == features.to_csv_gz(df)


# ---------------------------------------------------------------- 讀老師檔


def write_csv(path, header, rows, newline="\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((newline.join([",".join(header)] + [",".join(r) for r in rows]) + newline).encode())


def test_load_teacher_joins_live_after_training(tmp_path):
    train, live = tmp_path / "teacher", tmp_path / "live"
    write_csv(train / "market" / "A.csv", crawler.STOCK_COLUMNS, [stock_row("2026-08-28"), stock_row("2026-08-31")])
    write_csv(train / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS, [["2026-08-31", "15", "1", "2", "3", "4", "-1"]])
    (train / "info.json").write_text(json.dumps({"Top50@Y": ["A"], "Top100@Y": ["A"]}))
    write_csv(live / "market" / "A.csv", crawler.STOCK_COLUMNS,
              [stock_row("2026-08-31", 99), stock_row("2026-09-01"), stock_row("2026-09-02", -1, open_=-1, y="-1")],
              newline="\r\n")
    write_csv(live / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS,
              [["2026-09-01", "16", "1", "2", "-1", "-1", "-1"]], newline="\r\n")
    stocks, glob, top50 = features.load_teacher(train, live)
    assert sorted(stocks["A"]) == ["2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02"]
    assert stocks["A"]["2026-08-31"][crawler.COL_CLOSE] == "10.0"        # Live 只取 Training 最後一天之後
    assert glob["2026-08-31"][6] == "-1"                                  # Training 的 -1 是真的數字
    assert glob["2026-09-01"][4:] == ["", "", ""]                         # Live 的 -1 是待定
    assert top50 == {"A"}


# ---------------------------------------------------------------- 一個月一檔


def month_df(days):
    return features.build_features(small_raw(days), small_cfg())


def test_write_months_leaves_old_months_alone(tmp_path):
    days = ["2025-09-30", "2025-10-01", "2025-10-31", "2025-11-03", "2025-11-04"]
    df = month_df(days)
    assert features.write_months(df, tmp_path, 2) == ["2025-09", "2025-10", "2025-11"]
    assert features.write_months(df, tmp_path, 2) == []                   # 內容沒變就不寫
    changed = df.copy()
    changed.loc[changed["date"] == "2025-09-30", "is_top50"] = 9
    changed.loc[changed["date"] == "2025-11-04", "is_top50"] = 9
    old_sep = (tmp_path / "features" / "2025-09.csv.gz").read_bytes()
    assert features.write_months(changed, tmp_path, 2) == ["2025-11"]     # 只動最後兩個月裡真的變了的
    assert (tmp_path / "features" / "2025-09.csv.gz").read_bytes() == old_sep
    assert features.write_months(changed, tmp_path, 2, rebuild=True) == ["2025-09"]


def test_rebuild_removes_months_that_are_gone(tmp_path):
    features.write_months(month_df(["2025-10-31", "2025-11-03"]), tmp_path, 2)
    features.write_months(month_df(["2025-11-03", "2025-11-04"]), tmp_path, 2, rebuild=True)
    assert sorted(p.name for p in (tmp_path / "features").iterdir()) == ["2025-11.csv.gz"]


def fake_repo(tmp_path, monkeypatch, days):
    """tmp_path 當 repo 根目錄：data/raw/teacher 放兩檔股票，config 用 small_cfg。"""
    teacher = tmp_path / "data" / "raw" / "teacher" / "training"
    for c in ("A", "B"):
        write_csv(teacher / "market" / f"{c}.csv", crawler.STOCK_COLUMNS, [stock_row(d, 10 + j) for j, d in enumerate(days)])
    write_csv(teacher / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS,
              [[d, str(20 + j), "1", "2", "3", "4", "5"] for j, d in enumerate(days)])
    (teacher / "info.json").write_text(json.dumps({"Top50@Y": ["A"], "Top100@Y": ["A", "B"]}))
    yf = tmp_path / "data" / "raw" / "yfinance"
    write_csv(yf / "usd_twd.csv", crawler.YF_COLUMNS, [[d] + [str(30.0 + j)] * 5 + ["0"] for j, d in enumerate(days)])
    write_csv(yf / "usd_twd_1h.csv", crawler.HOURLY_COLUMNS,
              [[f"{d}T05:00:00+08:00"] + [str(31.0 + j)] * 4 + ["0"] for j, d in enumerate(days)])
    cfg = small_cfg()
    monkeypatch.setattr(utils, "ROOT", tmp_path)
    monkeypatch.setattr(utils, "load_config", lambda *a: cfg)
    return cfg


def test_main_writes_months_and_manifest(tmp_path, monkeypatch):
    days = ["2025-10-30", "2025-10-31", "2025-11-03", "2025-11-04"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    assert features.main(["--date", "2025-11-05"]) == 0
    processed = tmp_path / "data" / "processed"
    info = json.loads((processed / "manifest.json").read_text())
    assert info["months"] == ["2025-10", "2025-11"] and info["last_date"] == "2025-11-05"
    assert info["warnings"] == []
    assert info["model_columns"] == features.model_columns(cfg)
    back = features.load_features(processed)
    expected = features.build_features(features.load_raw(cfg), cfg, "2025-11-05")
    assert list(back["date"].unique()) == days + ["2025-11-05"]
    assert np.array_equal(back["stock_ret_lag1"].to_numpy(float), expected["stock_ret_lag1"].to_numpy(float),
                          equal_nan=True)
    # 拿較舊的 t 跑，不會把較新的月份蓋掉
    with pytest.raises(features.FeatureError, match="--rebuild"):
        features.main(["--date", "2025-11-03"])
    assert json.loads((processed / "manifest.json").read_text())["last_date"] == "2025-11-05"
    assert features.main(["--date", "2025-11-03", "--rebuild"]) == 0


def test_main_takes_t_from_crawler_manifest(tmp_path, monkeypatch):
    fake_repo(tmp_path, monkeypatch, ["2025-11-03", "2025-11-04"])
    crawler.write_atomic(tmp_path / "data" / "raw" / "manifest.json",
                         json.dumps({"run": {"target_date": "2025-11-05"}}).encode())
    features.main([])
    info = json.loads((tmp_path / "data" / "processed" / "manifest.json").read_text())
    assert info["target_date"] == info["last_date"] == "2025-11-05"


def test_missing_input_does_not_freeze_old_months(tmp_path, monkeypatch):
    """yfinance 檔不見（例如還沒爬過就先跑 features）：只寫最後兩個月，舊月份不建立，manifest 只列有檔的月份。"""
    fake_repo(tmp_path, monkeypatch, ["2025-08-29", "2025-09-30", "2025-10-31", "2025-11-03"])
    (tmp_path / "data" / "raw" / "yfinance" / "usd_twd.csv").unlink()
    features.main(["--date", "2025-11-04"])
    processed = tmp_path / "data" / "processed"
    assert sorted(p.name for p in (processed / "features").iterdir()) == ["2025-10.csv.gz", "2025-11.csv.gz"]
    info = json.loads((processed / "manifest.json").read_text())
    assert info["months"] == ["2025-10", "2025-11"] and info["warnings"]
    with pytest.raises(features.FeatureError, match="rebuild"):
        features.main(["--date", "2025-11-04", "--rebuild"])
