"""特徵只能用 t 之前的資料。"""

import copy

import pandas as pd

from src import crawler, features
from tests.test_features import hour, small_cfg, small_raw, stock_row, weekdays


def raw_with_hourly(days):
    hourly = [hour(f"{d}T05:00:00+08:00", 30 + j / 10) for j, d in enumerate(days)]
    raw = small_raw(days, hourly)
    raw["tx"] = [{"date": d, "expiry": "202501", "session": s, "close": 100.0 + j + (s == "night")}
                 for j, d in enumerate(days) for s in ("day", "night")]
    return raw, small_cfg(hourly_from=days[0])


def feature_columns(df):
    return [c for c in df.columns if "_ret_lag" in c]


def test_changing_day_t_does_not_change_its_features():
    """把某一天 d 的收盤價、y、global、日K、06:00 之後的 1h 改掉，d 和更早的列的特徵不能變，只有 d 之後的列可以變。"""
    days = weekdays(8)
    raw, cfg = raw_with_hourly(days)
    d = days[4]
    changed = copy.deepcopy(raw)
    for code in ("A", "B"):
        row = changed["stocks"][code][d]
        row[crawler.COL_CLOSE], row[crawler.COL_Y] = "999", "0"
    changed["global"][d][1] = "999"
    for r in changed["yfinance"]["usd_twd"]:
        if r["date"] == d:
            r["close"] = 999.0
    changed["hourly"] = sorted(changed["hourly"] + [hour(f"{d}T06:00:00+08:00", 999.0)], key=lambda r: r["start"])
    for r in changed["tx"]:
        if r["date"] == d and r["session"] == "day":   # d 的日盤（13:45 收盤）；d 的夜盤 05:00 就收了，d 那列可以用
            r["close"] = 999.0
    before, after = features.build_features(raw, cfg), features.build_features(changed, cfg)
    cols = feature_columns(before)
    upto = before["date"] <= d
    pd.testing.assert_frame_equal(before.loc[upto, cols], after.loc[upto, cols])
    later = before["date"] == days[5]
    for c in ("stock_ret_lag1", "teacher_vix_ret_lag1", "usd_twd_ret_lag1", "tx_day_ret_lag1", "tx_night_ret_lag1"):
        assert not before.loc[later, c].equals(after.loc[later, c]), c
    # usd_twd_am 只用 06:00 以前結束的 1h，d 那根 06:00 開始的K棒哪一列都不會用到
    assert before["usd_twd_am_ret_lag1"].equals(after["usd_twd_am_ret_lag1"])


def test_prediction_day_has_no_label():
    """預測日 t 那一列的 label_y、label_intraday_return 一定是空白，就算資料裡 t 那天已經填好；特徵和沒給 t 時一樣。"""
    days = weekdays(6)
    raw, cfg = raw_with_hourly(days)
    t = days[-1]
    with_t, without_t = features.build_features(raw, cfg, t), features.build_features(raw, cfg)
    row_t, row_plain = with_t[with_t["date"] == t], without_t[without_t["date"] == t]
    assert row_t["label_y"].isna().all() and row_t["label_intraday_return"].isna().all()
    assert row_plain["label_y"].notna().all()
    cols = feature_columns(with_t)
    pd.testing.assert_frame_equal(row_t[cols].reset_index(drop=True), row_plain[cols].reset_index(drop=True))


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
