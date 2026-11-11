"""特徵只能用 t 之前的資料。唯一的例外是開盤跳空（*_open_gap），只能用到 d 當天開盤，不能進模型。"""

import copy

import pandas as pd
import pytest

from src import crawler, features
from tests.test_features import bar, hour, small_cfg, small_raw, stock_row, weekdays

KEYS = ("date", "stock_id", "is_top50")


def raw_with_hourly(days):
    """small_raw 加上 1h、台指期、老師 global 6 欄、n225 和 kospi 日K、證交所的估值和委買賣。"""
    hourly = [hour(f"{d}T05:00:00+08:00", 30 + j / 10) for j, d in enumerate(days)]
    raw = small_raw(days, hourly)
    raw["tx"] = [{"date": d, "expiry": "202501", "session": s, "close": 100.0 + j + (s == "night")}
                 for j, d in enumerate(days) for s in ("day", "night")]
    for j, d in enumerate(days):   # ^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI
        raw["global"][d] = [d, str(20 + j), str(1000 + 3 * j), str(500 + 2 * j), str(17000 + j), str(2500 + j),
                            str(90000 + j)]
    for name, base in (("n225", 300.0), ("kospi", 200.0)):
        raw["yfinance"][name] = [bar(d, base + j, open_=base + j - 0.5, high=base + j + 1, low=base + j - 1)
                                 for j, d in enumerate(days)]
    raw["exchange"] = {
        "valuation": {(d, c): (str(10 + j), str(1 + j / 10), str(2 + j / 10)) for j, d in enumerate(days) for c in "AB"},
        "quotes": {(d, c): (f"{50 + j:.2f}", str(10 + j), f"{50.1 + j:.2f}", "5") for j, d in enumerate(days) for c in "AB"}}
    raw["vixtwn"] = {d: 20.0 + j for j, d in enumerate(days)}
    raw["fear_greed"] = {d: 40.0 + 3 * j for j, d in enumerate(days)}   # 測試裡美國日期和台股日期一樣
    raw["yfinance"]["dji"] = [bar(d, 40000.0 + j, high=40100.0 + j) for j, d in enumerate(days)]   # 美股日曆
    cfg = small_cfg(hourly_from=days[0])
    cfg["cnn"]["start"] = days[0]
    cfg["yfinance"]["tickers"].update(n225="^N225", kospi="^KS11")
    cfg["features"]["teacher_global"] = ["^VIX", "^IXIC", "^GSPC", "^TWII", "^KS11"]
    cfg["features"]["open_gap"] = {"series": ["kospi", "n225"], "late_open": {}}
    return raw, cfg


def feature_columns(df, same_day=False):
    """鍵和答案以外的欄。same_day=False 時不含開盤跳空（它用到 d 當天開盤）。"""
    return [c for c in df.columns if c not in KEYS and c not in features.LABELS
            and (same_day or features.OPEN_GAP not in c)]


def gap_columns(df):
    return [c for c in df.columns if features.OPEN_GAP in c]


def change_day(raw, d):
    """把 d 當天收盤後才知道的東西都改掉：收盤價、y、global 的 ^VIX ^TWII ^KS11 TX_OI、日K、06:00 之後的 1h、
    d 的日盤、d 的證交所估值和委買賣、d 的 VIXTWN（13:45 收盤）。d 的夜盤（05:00 收盤）和 global 的 ^GSPC、^IXIC
    （d 開盤前的美股）不改。CNN 另外測（test_fear_greed_never_uses_the_last_cnn_day）。"""
    changed = copy.deepcopy(raw)
    changed["vixtwn"][d] = 99.0
    for code in ("A", "B"):
        row = changed["stocks"][code][d]
        row[crawler.COL_OPEN], row[crawler.COL_HIGH], row[crawler.COL_LOW] = "990", "1000", "980"
        row[crawler.COL_CLOSE], row[crawler.COL_Y] = "999", "0"
        row[crawler.COL_SHARES] = "999999"
        changed["exchange"]["valuation"][d, code] = ("-", "99", "9")
        changed["exchange"]["quotes"][d, code] = ("--", "0", "60.00", "7")
    for j in (1, 4, 5, 6):
        changed["global"][d][j] = "999"
    for rows in changed["yfinance"].values():
        for r in rows:
            if r["date"] == d:
                r.update(open=990.0, high=1000.0, low=980.0, close=999.0, adj_close=999.0)
    changed["hourly"] = sorted(changed["hourly"] + [hour(f"{d}T06:00:00+08:00", 999.0)], key=lambda r: r["start"])
    for r in changed["tx"]:
        if r["date"] == d and r["session"] == "day":   # d 的日盤（13:45 收盤）；d 的夜盤 05:00 就收了，d 那列可以用
            r["close"] = 999.0
    return changed


def test_changing_day_t_does_not_change_its_features():
    """把某一天 d 收盤後才知道的資料改掉，d 和更早的列的特徵不能變，只有 d 之後的列可以變。
    開盤跳空是例外：d 那列可以變（用 d 的開盤），d 之前的列不能變。"""
    days = weekdays(8)
    raw, cfg = raw_with_hourly(days)
    d = days[4]
    before, after = features.build_features(raw, cfg), features.build_features(change_day(raw, d), cfg)
    cols = feature_columns(before)
    assert {"val_ep_lag1", "quote_imbalance_lag1", "teacher_gspc_fresh_ret_lag1", "kospi_ret_lag1"} <= set(cols)
    upto = before["date"] <= d
    pd.testing.assert_frame_equal(before.loc[upto, cols], after.loc[upto, cols])
    gaps = gap_columns(before)
    assert gaps == ["kospi_open_gap", "n225_open_gap"]
    earlier = before["date"] < d
    pd.testing.assert_frame_equal(before.loc[earlier, gaps], after.loc[earlier, gaps])
    assert before.loc[before["date"] == d, gaps].notna().all().all()
    assert not before.loc[before["date"] == d, gaps].equals(after.loc[after["date"] == d, gaps])
    later = before["date"] == days[5]
    for c in ("stock_ret_lag1", "stock_intraday_ret_lag1", "stock_gap_ret_lag1", "stock_log_shares_lag1",
              "stock_open_lag1", "stock_close_lag1", "stock_high_lag1", "stock_low_lag1",
              "teacher_vix_ret_lag1", "usd_twd_ret_lag1",
              "tx_day_ret_lag1", "tx_night_ret_lag1",
              "teacher_twii_ret_lag1", "n225_ret_lag1", "val_ep_lag1", "val_pe_loss_lag1", "quote_spread_ticks_lag1",
              "quote_limit_down_lag1", "vixtwn_lag1", "vixtwn_ret_lag1"):
        assert not before.loc[later, c].equals(after.loc[later, c]), c
    # usd_twd_am 只用 06:00 以前結束的 1h，d 那根 06:00 開始的K棒哪一列都不會用到
    assert before["usd_twd_am_ret_lag1"].equals(after["usd_twd_am_ret_lag1"])


def test_open_gap_uses_d_open_not_d_close():
    """d 那列的開盤跳空只能用 d 的 open 和前一根的 close。change_day 把開高低收一起改，分不出用的是哪個，
    所以分開改（K棒都不是開高低收相同，不會被當成佔位K棒）：
    只改 d 的收盤（高低跟著放寬）時 d 那列不變、d+1 那列變；只改 d 的開盤時 d 那列變、d+1 那列不變。"""
    days = weekdays(8)
    raw, cfg = raw_with_hourly(days)
    d, nxt = days[4], days[5]
    close_only, open_only = copy.deepcopy(raw), copy.deepcopy(raw)
    for name in ("n225", "kospi"):
        for r in close_only["yfinance"][name]:
            if r["date"] == d:
                r.update(close=r["close"] + 0.7, adj_close=r["close"] + 0.7, high=r["high"] + 1, low=r["low"] - 1)
        for r in open_only["yfinance"][name]:
            if r["date"] == d:
                r.update(open=r["open"] + 0.3)
    base = features.build_features(raw, cfg)
    moved_close, moved_open = features.build_features(close_only, cfg), features.build_features(open_only, cfg)
    gaps = gap_columns(base)
    at_d, at_next = base["date"] == d, base["date"] == nxt
    pd.testing.assert_frame_equal(base.loc[at_d, gaps], moved_close.loc[at_d, gaps])
    assert (base.loc[at_next, gaps] != moved_close.loc[at_next, gaps]).all().all()
    assert (base.loc[at_d, gaps] != moved_open.loc[at_d, gaps]).all().all()
    pd.testing.assert_frame_equal(base.loc[at_next, gaps], moved_open.loc[at_next, gaps])


def test_fresh_teacher_uses_t_row_but_not_twii_ks11():
    """老師 global 第 d 列的 ^GSPC 是 d 開盤前的美股收盤：d 那列的 fresh 欄會用到它，原本的 teacher_gspc 不會。
    ^TWII、^KS11 第 d 列是 d 當天收盤，d 那列的任何欄都不能用到。"""
    days = weekdays(6)
    raw, cfg = raw_with_hourly(days)
    d = days[4]
    gspc = copy.deepcopy(raw)
    gspc["global"][d][3] = "999"
    base, moved = features.build_features(raw, cfg), features.build_features(gspc, cfg)
    row = base["date"] == d
    assert not base.loc[row, "teacher_gspc_fresh_ret_lag1"].equals(moved.loc[row, "teacher_gspc_fresh_ret_lag1"])
    assert base.loc[row, "teacher_gspc_ret_lag1"].equals(moved.loc[row, "teacher_gspc_ret_lag1"])
    earlier = base["date"] < d
    cols = feature_columns(base, same_day=True)
    pd.testing.assert_frame_equal(base.loc[earlier, cols], moved.loc[earlier, cols])
    twii = copy.deepcopy(raw)
    twii["global"][d][4], twii["global"][d][5] = "999", "999"
    pd.testing.assert_frame_equal(base.loc[base["date"] <= d, cols],
                                  features.build_features(twii, cfg).loc[base["date"] <= d, cols])


def test_fresh_teacher_refuses_same_day_columns():
    days = weekdays(4)
    raw, cfg = raw_with_hourly(days)
    for column in ("^TWII", "^KS11", "TX_OI", "^VIX"):
        cfg["features"]["teacher_fresh"] = ["^GSPC", column]
        with pytest.raises(features.FeatureError, match="teacher_fresh"):
            features.build_features(raw, cfg)


def test_prediction_day_has_no_label():
    """預測日 t 那一列的 label_y、label_intraday_return 一定是空白，就算資料裡 t 那天已經填好；特徵和沒給 t 時一樣。
    開盤跳空在 t 那列一律空白，就算資料裡已經有 t 那根。"""
    days = weekdays(6)
    raw, cfg = raw_with_hourly(days)
    t = days[-1]
    with_t, without_t = features.build_features(raw, cfg, t), features.build_features(raw, cfg)
    row_t, row_plain = with_t[with_t["date"] == t], without_t[without_t["date"] == t]
    assert row_t["label_y"].isna().all() and row_t["label_intraday_return"].isna().all()
    assert row_plain["label_y"].notna().all()
    cols = feature_columns(with_t)
    pd.testing.assert_frame_equal(row_t[cols].reset_index(drop=True), row_plain[cols].reset_index(drop=True))
    gaps = gap_columns(with_t)
    assert row_t[gaps].isna().all().all() and row_plain[gaps].notna().all().all()


def test_open_gap_can_never_be_a_model_column():
    """使用者 2026-11-08：開盤跳空是 t 當天的值，model_series 放了任何 open_gap 的名字都要停下。"""
    cfg = small_cfg()
    assert not [c for c in features.model_columns(cfg) if features.OPEN_GAP in c]
    for name in ("kospi_open_gap", "n225_open_gap", "open_gap"):
        cfg["features"]["model_series"] = ["stock", name]
        with pytest.raises(features.FeatureError, match="開盤跳空"):
            features.model_columns(cfg)
        with pytest.raises(features.FeatureError, match="開盤跳空"):
            features.build_features(small_raw(weekdays(3)), cfg)


def test_fear_greed_never_uses_the_last_cnn_day():
    """CNN 最後一天的分數收盤後還會被改（2026-11-09 量到），到美國下一個交易日才定住（使用者 2026-11-09）。
    改掉 CNN d 那天的分數：d 那列和下一個交易日那列都不能變（那時 d 還是最後一天），再下一列才會用到。"""
    days = weekdays(8)
    raw, cfg = raw_with_hourly(days)
    d = days[3]
    moved = copy.deepcopy(raw)
    moved["fear_greed"][d] = 1.0
    base, after = features.build_features(raw, cfg, days[-1]), features.build_features(moved, cfg, days[-1])
    cols = list(features.SIDE_COLUMNS)
    upto = base["date"] <= days[4]
    assert base.loc[upto & (base["date"] > days[1]), "fear_greed_lag1"].notna().all()
    pd.testing.assert_frame_equal(base.loc[upto, cols], after.loc[upto, cols])
    later = base["date"] == days[5]
    assert base.loc[later, "fear_greed_lag1"].notna().all()   # 兩邊都空白時 != 也會成立（審查 2026-11-09）
    assert (base.loc[later, "fear_greed_lag1"] != after.loc[later, "fear_greed_lag1"]).all()


def test_fear_greed_skips_a_us_holiday_cnn_point():
    """美股休市、台股有開的日子 H：CNN 在 H 也先建一點（值是前一天的），之後可能拿掉（審查 2026-11-09）。
    H 前一個美股日 e 的分數要到 H 之後美國開盤才定住，所以 H 隔天那列還不能用 e；H 那點哪一列都不用。"""
    days = weekdays(8)
    raw, cfg = raw_with_hourly(days)
    holiday, e = days[4], days[3]
    raw["yfinance"]["dji"] = [r for r in raw["yfinance"]["dji"] if r["date"] != holiday]
    cols = list(features.SIDE_COLUMNS)
    base = features.build_features(raw, cfg, days[-1])
    moved = copy.deepcopy(raw)
    moved["fear_greed"][e] = 1.0
    after = features.build_features(moved, cfg, days[-1])
    upto = base["date"] <= days[5]
    pd.testing.assert_frame_equal(base.loc[upto, cols], after.loc[upto, cols])
    later = base["date"] == days[6]
    assert base.loc[later, "fear_greed_lag1"].notna().all()
    assert (base.loc[later, "fear_greed_lag1"] != after.loc[later, "fear_greed_lag1"]).all()
    placeholder = copy.deepcopy(raw)
    placeholder["fear_greed"][holiday] = 1.0
    pd.testing.assert_frame_equal(base[cols], features.build_features(placeholder, cfg, days[-1])[cols])


def test_new_columns_are_not_model_columns():
    """2026-11-08、11-09 加的欄都只進長表；模型另有個股報酬、三組 5 日 lag 和前日 OHLC。"""
    columns = features.model_columns(features.utils.load_config())
    assert len(columns) == 55
    assert not [c for c in columns if c.startswith(("val_", "quote_", "kospi", "vixtwn", "fear_greed"))
                or "fresh" in c or "open_gap" in c]


def test_institutional_minus_one_does_not_unfill_a_day():
    """Training 法人欄裡真的 -1（例如剛好賣超 1 股）不影響「填好了」：那天還是交易日、有 label。
    Live global 表的 -1 是待定，見 test_features.test_load_teacher_joins_live_after_training。"""
    days = weekdays(4)
    raw, cfg = raw_with_hourly(days)
    for code in ("A", "B"):
        raw["stocks"][code][days[2]] = stock_row(days[2], 12, foreign="-1")
    df = features.build_features(raw, cfg)
    assert list(df["date"].unique()) == days
    assert df[df["date"] == days[2]]["label_y"].notna().all()
