"""組員的邏輯迴歸（src/online_lr.py）：個股特徵不偷看當天和之後的資料，每天的模式和回測一樣。"""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from src import crawler, online_lr, utils

RAW_NUMERIC = ["close", "open", "high", "low", "n_trades", "value", "shares", "foreign_hold_pct", "foreign_net",
               "trust_net", "dealer_net", "dealer_hedge_net", "RSI", "SMA", "MACD", "ATR", "BBANDS_upper",
               "BBANDS_mid", "BBANDS_lower", "y"]


def small_cfg():
    cfg = copy.deepcopy(utils.load_config())
    cfg["features"]["model_series"] = ["stock"]
    cfg["features"]["lags"] = [1, 2]
    return cfg


def fake_raw(codes, days, seed=0):
    """teacher_table 輸出的樣子：每檔每天一列，數值隨機但合理（價格 > 0）。"""
    rng = np.random.default_rng(seed)
    rows = []
    for c in codes:
        price = 100.0
        for d in days:
            price *= 1 + rng.normal(0, 0.02)
            o = price * (1 + rng.normal(0, 0.01))
            rows.append({"stock_id": c, "date": pd.Timestamp(d), "close": price, "open": o,
                         "high": max(price, o) * 1.01, "low": min(price, o) * 0.99, "n_trades": float(rng.integers(100, 999)),
                         "value": rng.uniform(1e6, 1e8), "shares": rng.uniform(1e4, 1e6),
                         "foreign_hold_pct": rng.uniform(10, 80), "foreign_net": rng.normal(0, 1e3),
                         "trust_net": rng.normal(0, 1e3), "dealer_net": rng.normal(0, 1e3),
                         "dealer_hedge_net": rng.normal(0, 1e3), "RSI": rng.uniform(0, 100), "SMA": price * 0.99,
                         "MACD": rng.normal(0, 1), "ATR": price * 0.02, "BBANDS_upper": price * 1.05,
                         "BBANDS_mid": price, "BBANDS_lower": price * 0.95, "y": float(price > o)})
    return pd.DataFrame(rows).sort_values(["stock_id", "date"], ignore_index=True)


# ---------------------------------------------------------------- 讀老師檔


def stock_line(d, close="10.0", foreign_net="5", y="1"):
    cells = [d, close, "9.0", "11.0", "8.0", "100", "1000", "100", "50", foreign_net, "3", "2", "1", "55", "9.5",
             "0.1", "0.2", "11", "10", "9", y]
    assert len(cells) == len(crawler.STOCK_COLUMNS)
    return cells


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([",".join(header)] + [",".join(r) for r in rows]) + "\n", encoding="utf-8")


def test_teacher_table_keeps_training_minus_one_and_blanks_live_minus_one(tmp_path):
    train, live = tmp_path / "training", tmp_path / "live"
    write_csv(train / "market" / "A.csv", crawler.STOCK_COLUMNS,
              [stock_line("2026-08-28", foreign_net="-1"), stock_line("2026-08-31")])
    write_csv(train / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS, [["2026-08-31", "15", "1", "2", "3", "4", "5"]])
    (train / "info.json").write_text(json.dumps({"Top50@Y": ["A"]}))
    pending = ["2026-09-02"] + ["-1"] * (len(crawler.STOCK_COLUMNS) - 1)
    write_csv(live / "market" / "A.csv", crawler.STOCK_COLUMNS,
              [stock_line("2026-08-31", close="99"), stock_line("2026-09-01", foreign_net="-1"), pending])
    df = online_lr.teacher_table(train, live)
    by_date = df.set_index(df["date"].dt.strftime("%Y-%m-%d"))
    assert list(by_date.index) == ["2026-08-28", "2026-08-31", "2026-09-01"]   # 待定的 9/2 不算填好
    assert by_date.loc["2026-08-28", "foreign_net"] == -1                      # Training 的 -1 是真的
    assert np.isnan(by_date.loc["2026-09-01", "foreign_net"])                   # Live 的 -1 是待定
    assert by_date.loc["2026-08-31", "close"] == 10.0                           # Live 只取 Training 之後


# ---------------------------------------------------------------- 個股特徵


def test_stock_features_are_26():
    assert len(online_lr.STOCK_FEATURES) == 26 == len(set(online_lr.STOCK_FEATURES))


def test_attach_uses_last_filled_row_strictly_before():
    raw = fake_raw(["A"], ["2026-01-05", "2026-01-06", "2026-01-08"])
    sf = online_lr.stock_features(raw)
    table = pd.DataFrame({"date": ["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"], "stock_id": "A"})
    out = online_lr.attach(table, sf)
    assert out["feat_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-05", "2026-01-06", "2026-01-06",
                                                                 "2026-01-08"]


def test_features_do_not_use_same_day_or_later():
    """把 cutoff 當天和之後的老師資料亂改，日期 ≤ cutoff 的列特徵不變（組員 check_no_lookahead 的做法）。"""
    days = pd.bdate_range("2025-01-01", periods=80).strftime("%Y-%m-%d").tolist()
    raw = fake_raw(["A", "B", "C"], days)
    t = (pd.Timestamp(days[-1]) + pd.offsets.BDay(1)).strftime("%Y-%m-%d")
    table = pd.DataFrame([(d, c) for d in days + [t] for c in "ABC"], columns=["date", "stock_id"])
    cutoff = pd.Timestamp(days[50])
    poisoned = raw.copy()
    future = poisoned["date"] >= cutoff
    rng = np.random.default_rng(1)
    poisoned.loc[future, RAW_NUMERIC] *= rng.uniform(0.5, 1.5, size=(future.sum(), len(RAW_NUMERIC)))
    a = online_lr.attach(table, online_lr.stock_features(raw))
    b = online_lr.attach(table, online_lr.stock_features(poisoned))
    past = a["date"] <= cutoff
    pd.testing.assert_frame_equal(a.loc[past, online_lr.STOCK_FEATURES], b.loc[past, online_lr.STOCK_FEATURES])
    assert not a.loc[a["date"] > cutoff + pd.offsets.BDay(1), online_lr.STOCK_FEATURES].equals(
        b.loc[b["date"] > cutoff + pd.offsets.BDay(1), online_lr.STOCK_FEATURES])
    assert (a["feat_date"].dropna() < a.loc[a["feat_date"].notna(), "date"]).all()


# ---------------------------------------------------------------- 模型


def fake_data(cfg, days, codes, seed=0):
    rng = np.random.default_rng(seed)
    cols = online_lr.feature_columns(cfg)
    n = len(days) * len(codes)
    df = pd.DataFrame({"date": np.repeat(pd.to_datetime(days), len(codes)), "stock_id": np.tile(codes, len(days))})
    for c in cols:
        df[c] = rng.normal(size=n)
    df.loc[rng.random(n) < 0.05, cols[0]] = np.nan
    signal = df[cols[1]].fillna(0) + 0.5 * df[cols[2]] + rng.normal(0, 1, n)
    df["label_y"] = pd.array((signal > 0).astype(int), dtype="Int64")
    df["label_intraday_return"] = signal / 100
    return df


def test_daily_mode_matches_holdout_and_ignores_labels_from_t_on():
    cfg = small_cfg()
    days = pd.bdate_range("2024-01-01", "2025-09-30").strftime("%Y-%m-%d").tolist()
    codes = [f"S{i:02d}" for i in range(12)]
    data = fake_data(cfg, days, codes)
    target = [d for d in days if d >= "2025-08-01"]
    hold = online_lr.predict(data, cfg, target, codes[:6])
    assert len(hold) == len(target) * 6 and set(hold["pred"]) <= {0, 1}
    for t in ["2025-08-13", "2025-09-01", "2025-09-30"]:
        daily = data[data["date"] <= t].copy()
        daily.loc[daily["date"] == t, ["label_y", "label_intraday_return"]] = pd.NA, np.nan
        one = online_lr.predict(daily, cfg, [t], codes[:6])
        want = hold[hold["date"] == t].reset_index(drop=True)
        np.testing.assert_allclose(one["prob"].to_numpy(), want["prob"].to_numpy(), rtol=0, atol=1e-12)
    flipped = data.copy()
    later = flipped["date"] >= pd.Timestamp("2025-09-01")
    flipped.loc[later, "label_y"] = 1 - flipped.loc[later, "label_y"]
    again = online_lr.predict(flipped, cfg, ["2025-09-01"], codes[:6])
    np.testing.assert_allclose(again["prob"], hold[hold["date"] == "2025-09-01"]["prob"], atol=1e-12)


def test_predict_stops_when_a_stock_has_no_row():
    cfg = small_cfg()
    days = pd.bdate_range("2024-01-01", "2025-03-31").strftime("%Y-%m-%d").tolist()
    data = fake_data(cfg, days, ["A", "B"])
    with pytest.raises(online_lr.ModelError):
        online_lr.predict(data, cfg, ["2025-03-31"], ["A", "Z"])
    with pytest.raises(online_lr.ModelError):
        online_lr.predict(data, cfg, ["2025-04-01"], ["A"])


def test_official_score():
    data = pd.DataFrame({"date": pd.to_datetime(["2025-01-02"] * 2), "stock_id": ["A", "B"],
                         "label_y": pd.array([1, 0], dtype="Int64"), "label_intraday_return": [0.02, -0.01]})
    pred = pd.DataFrame({"date": ["2025-01-02"] * 2, "stock_id": ["A", "B"], "pred": [1, 1]})
    s = online_lr.official_score(pred, data)
    assert s["score"] == pytest.approx((0.02 - 0.01) / 2) and s["accuracy"] == 0.5
    assert s["all_0"] == pytest.approx(-0.005)
