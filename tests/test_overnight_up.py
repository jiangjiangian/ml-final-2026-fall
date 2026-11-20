"""隔夜大跌全猜漲（src/models/m5_overnight_up.py，使用者 2026-11-20）：只給影子跑的規則。

資料都是假的：台股和美股都用週一到週五當交易日，美股K棒的日期早台股一天。不訓練、不連網、不讀 data/。
"""

import logging

import numpy as np
import pandas as pd
import pytest

from src.models import MODEL_KINDS, SHADOW_ONLY, m5_overnight_up as ou
from src.pipeline import step3_train_predict as tp

LOG = logging.getLogger("test_overnight_up")
CFG = {"overnight_up": {"std_days": 250, "min_std_days": 200, "min_parts": 2, "rank_days": 250, "min_rank_share": 0.8,
                        "quantile": 0.90}}
DAYS = pd.bdate_range("2024-01-01", periods=620)   # 台股交易日，最後一天是 t
T = DAYS[-1]
STOCKS = ["1101", "2317", "2330", "2454"]


def levels(seed: int, last_return: float | None = None) -> pd.Series:
    """每個美股交易日（和 DAYS 同一批日期）的收盤價。last_return 給的話，t 前一晚那場的報酬換成它。"""
    returns = np.random.default_rng(seed).normal(0, 0.01, len(DAYS))
    if last_return is not None:
        returns[-2] = last_return    # DAYS[-2] 那場美股在 t 清晨收盤，是 t 開盤前的最後一根
    return pd.Series(100 * np.cumprod(1 + returns), index=DAYS)


def make(last_return: float | None = None, base_pred=(1, 1, 0, 0)):
    """假的 inputs（base、frame、world）和 bars。t 那天沒有答案，之前每天都有。"""
    series = {name: levels(seed, last_return) for seed, name in enumerate(ou.PARTS)}
    bars = {name: pd.DataFrame({"date": DAYS, "adj_close": series[name].to_numpy()}) for name in ou.YF_PARTS}
    world = pd.DataFrame({"date": DAYS[1:], "^GSPC": series["gspc"].to_numpy()[:-1]})   # 第 d 列 = d 之前最後一場的收盤
    frame = pd.DataFrame({"date": DAYS, "r": [0.001] * (len(DAYS) - 1) + [np.nan]})
    base = pd.DataFrame({"date": f"{T:%Y-%m-%d}", "stock_id": STOCKS, "prob": [0.8, 0.6, 0.4, 0.2], "pred": list(base_pred)})
    return {"base": base, "frame": frame, "world": world}, bars


def run(last_return=None, **kwargs):
    inputs, bars = make(last_return, **kwargs)
    return ou.predict(None, CFG, [f"{T:%Y-%m-%d}"], STOCKS, inputs=inputs, bars=bars)


# ---------------------------------------------------------------- 小函式


def test_trailing_share_counts_only_earlier_rows():
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 0.5, 10.0])
    out = ou.trailing_share(values, 4, 1.0)
    assert out.iloc[:4].isna().all()
    assert out.iloc[4] == 0.0     # 前四個都比 0.5 大
    assert out.iloc[5] == 1.0     # 前四個（2、3、4、0.5）都 ≤ 10
    with_gap = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0])
    assert ou.trailing_share(with_gap, 4, 1.0).isna().all()          # 前四個只有三個有值
    assert ou.trailing_share(with_gap, 4, 0.75).iloc[4] == 1.0


def test_last_before_never_uses_the_bar_dated_the_same_day():
    bars = pd.DataFrame({"date": pd.to_datetime(["2026-11-17", "2026-11-18", "2026-11-19"]), "adj_close": [1.0, 2.0, 3.0]})
    days = pd.DatetimeIndex(pd.to_datetime(["2026-11-18", "2026-11-19", "2026-11-20"]))
    got = ou.last_before(days, bars)
    assert got["adj_close"].tolist() == [1.0, 2.0, 3.0]
    assert got["bar_date"].tolist() == list(pd.to_datetime(["2026-11-17", "2026-11-18", "2026-11-19"]))


def test_since_close_spans_every_us_session_while_taiwan_was_closed():
    bars = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]),
                         "adj_close": [100.0, 110.0, 121.0, 133.1]})
    days = pd.DatetimeIndex(pd.to_datetime(["2026-01-02", "2026-01-07"]))    # 台股中間休了兩天
    world = pd.DataFrame({"date": days, "^GSPC": [50.0, 55.0]})
    parts = ou.since_close(days, world, CFG, {"tsm_adr": bars, "sox": bars})
    assert parts.at[days[1], "tsm_adr"] == pytest.approx(133.1 / 100 - 1)    # 三場美股的漲跌合在一起
    assert parts.at[days[1], "gspc"] == pytest.approx(0.1)
    assert parts.attrs["last_bar"]["sox"] == pd.Timestamp("2026-01-06")


def test_missing_teacher_row_leaves_gspc_blank_instead_of_reusing_an_old_row():
    days = pd.DatetimeIndex(pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))
    bars = pd.DataFrame({"date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]), "adj_close": [1.0, 1.0, 1.0]})
    world = pd.DataFrame({"date": days[:2], "^GSPC": [50.0, 55.0]})          # 沒有 01-07 那列
    parts = ou.since_close(days, world, CFG, {"tsm_adr": bars, "sox": bars})
    assert np.isnan(parts.at[days[2], "gspc"])


# ---------------------------------------------------------------- predict


def test_crash_night_calls_every_stock_up():
    out = run(-0.08)
    assert out["pred"].tolist() == [1, 1, 1, 1] and out["all_up"].tolist() == [1] * 4
    assert out["base_pred"].tolist() == [1, 1, 0, 0]                         # rank_ensemble 的猜法還留著
    assert (out["o"] < 0).all() and (out["o_absq"] >= 0.90).all()
    assert out["us_last_bar"].unique().tolist() == [f"{DAYS[-2]:%Y-%m-%d}"]


def test_rally_night_keeps_the_rank_ensemble_book():
    out = run(0.08)
    assert out["pred"].tolist() == [1, 1, 0, 0] and out["all_up"].tolist() == [0] * 4
    assert (out["o"] > 0).all() and (out["o_absq"] >= 0.90).all()            # 一樣極端，但方向是漲，不觸發


def test_small_drop_keeps_the_rank_ensemble_book():
    out = run(-0.001)
    assert out["pred"].tolist() == [1, 1, 0, 0] and out["all_up"].tolist() == [0] * 4
    assert (out["o"] < 0).all() and (out["o_absq"] < 0.90).all()


def test_signal_only_uses_days_before_t_for_the_scale():
    """t 前一晚的漲跌放大十倍，前面每天的 o 都不變（標準差和分位都不含自己那天）。"""
    days = ou.trading_days(make()[0]["frame"], T)
    small_inputs, small_bars = make(-0.01)
    big_inputs, big_bars = make(-0.10)
    small = ou.signal(ou.since_close(days, small_inputs["world"], CFG, small_bars), CFG["overnight_up"])
    big = ou.signal(ou.since_close(days, big_inputs["world"], CFG, big_bars), CFG["overnight_up"])
    pd.testing.assert_frame_equal(small.iloc[:-1], big.iloc[:-1])
    assert big["o"].iloc[-1] < small["o"].iloc[-1] < 0


def test_missing_teacher_row_for_t_falls_back_to_the_two_yfinance_parts():
    inputs, bars = make(-0.08)
    inputs["world"] = inputs["world"].iloc[:-1]                              # 老師 global 沒有 t 那列（美國或韓國休市）
    out = ou.predict(None, CFG, [f"{T:%Y-%m-%d}"], STOCKS, inputs=inputs, bars=bars)
    assert out["o_parts"].tolist() == [2] * 4 and out["pred"].tolist() == [1, 1, 1, 1]
    assert run(-0.08)["o_parts"].tolist() == [3] * 4


def test_fewer_parts_than_min_parts_raises():
    inputs, bars = make(-0.08)
    inputs["world"] = inputs["world"].iloc[:-1]
    strict = {"overnight_up": {**CFG["overnight_up"], "min_parts": 3}}
    with pytest.raises(ou.OvernightError, match="只有 2 個"):
        ou.predict(None, strict, [f"{T:%Y-%m-%d}"], STOCKS, inputs=inputs, bars=bars)


def test_one_stale_yfinance_series_raises():
    inputs, bars = make(-0.08)
    bars["sox"] = bars["sox"].iloc[:-2]                                      # 費半少了 t 前一晚那根
    with pytest.raises(ou.OvernightError, match="不是同一天"):
        ou.predict(None, CFG, [f"{T:%Y-%m-%d}"], STOCKS, inputs=inputs, bars=bars)


def test_short_history_raises():
    inputs, bars = make(-0.08)
    inputs["frame"] = inputs["frame"].iloc[-300:]                            # 標準差夠算，分位的 250 天不夠
    with pytest.raises(ou.OvernightError, match="空的"):
        ou.predict(None, CFG, [f"{T:%Y-%m-%d}"], STOCKS, inputs=inputs, bars=bars)


# ---------------------------------------------------------------- 只能影子跑


def test_shadow_only_model_cannot_be_the_daily_model_or_a_fallback(caplog):
    assert "overnight_up" in MODEL_KINDS and "overnight_up" in SHADOW_ONLY
    with pytest.raises(tp.ModelChoiceError):
        tp.model_order({"daily_model": {"kind": "overnight_up"}}, LOG)
    with caplog.at_level(logging.ERROR):
        order = tp.model_order({"daily_model": {"kind": "persist", "fallback": ["overnight_up", "online_lr"]}}, LOG)
    assert order == ["persist", "online_lr"] and "overnight_up" in caplog.text
    assert tp.shadow_models({"daily_model": {"shadow": ["persist", "overnight_up"]}}) == ["persist", "overnight_up"]


def test_shadow_file_gets_the_signal_columns(monkeypatch, tmp_path):
    day = f"{T:%Y-%m-%d}"
    crash = run(-0.08)
    monkeypatch.setattr(ou, "predict", lambda data, cfg, dates, stocks: crash)
    cfg = {"daily_model": {"kind": "persist", "shadow": ["overnight_up"]}, "data": {"submission_dir": str(tmp_path)}}
    table = pd.read_csv(tp.shadow_predict(cfg, None, day, STOCKS, LOG), dtype={"stock_id": str})
    assert table["pred_overnight_up"].tolist() == [1, 1, 1, 1]
    assert {"prob_overnight_up", "o_overnight_up", "o_absq_overnight_up", "o_parts_overnight_up",
            "us_last_bar_overnight_up"} <= set(table.columns)
    assert (table["o_overnight_up"] < 0).all() and table["us_last_bar_overnight_up"].nunique() == 1
