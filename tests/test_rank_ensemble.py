"""排名集成（src/rank_ensemble.py）：沒有答案的那天只用之前的資料、每天猜漲猜跌各一半；資料不對會丟錯；
run_daily_test.py 的備援順序。"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_daily_test as rdt
from src import crawler, features, online_lr, persist_rule, rank_ensemble, site_api, utils

COLUMNS = ["stock_ret_lag1", "stock_ret_lag2", "a_ret1", "a_intraday", "a_gap", "a_high", "a_low", "a_volume_ratio",
           "a_rsi", "a_bb_pos", "a_bb_width", "a_macd", "a_ema5_dev", "a_ema20_dev", "a_ema60_dev", "a_ema5_20",
           "a_ema20_60", "c_foreign_pct", "c_foreign_hold_chg5", "c_intraday_mean5", "c_intraday_mean20", "c_ret5",
           "c_ret20", "c_atr_pct", "c_sma_dev", "c_amount_z60", "o_gap_mean5", "o_gap_mean20", "o_gap_std20",
           "o_intraday_std20", "o_gap_intraday_corr60", "o_intraday_minus_gap5", "o_parkinson20", "o_garman_klass20",
           "o_close_location", "o_intraday_up_frac20", "o_intraday_rank", "o_gap_rank", "gap_rel", "p_e_mean20",
           "p_e_mean120", "p_e_up60", "p_gap_rel20"]
CFG = {"rank_ensemble": {
    "columns": COLUMNS, "train_days": 60, "min_train_days": 30, "max_missing": 0.10, "target_clip": 3.0,
    "ridge_alpha": 10.0, "kernel_components": 40, "kernel_gamma_scale": 0.2, "kernel_alpha": 10.0, "seeds": [0],
    "max_stale_days": 0,
    "lgbm": {"objective": "regression", "num_leaves": 4, "min_child_samples": 5, "n_estimators": 15,
             "learning_rate": 0.1, "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.7, "verbose": -1,
             "n_jobs": 1}}}
LOG = logging.getLogger("test_rank_ensemble")


def fake_market(n_days=230, n_stocks=12, seed=0):
    """隨機但合理的老師檔（read_teacher_stock 接起來的樣子）和對應的長表（每檔每天一列，有答案）。"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=n_days)
    teacher, table = [], []
    for k in range(n_stocks):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.02, n_days))
        open_price = np.r_[100.0, close[:-1]] * (1 + rng.normal(0, 0.01, n_days))
        high, low = np.maximum(close, open_price) * 1.01, np.minimum(close, open_price) * 0.99
        stock = pd.DataFrame({
            "date": days, "stock_id": f"S{k:02d}", "close": close, "open": open_price, "high": high, "low": low,
            "volume": rng.uniform(1e4, 1e6, n_days), "amount": rng.uniform(1e6, 1e8, n_days),
            "foreign_hold": rng.uniform(10, 80, n_days), "foreign_net": rng.normal(0, 1e3, n_days),
            "trust_net": rng.normal(0, 1e3, n_days), "dealer_self_net": rng.normal(0, 1e3, n_days),
            "dealer_hedge_net": rng.normal(0, 1e3, n_days), "rsi": rng.uniform(0, 100, n_days), "sma": close * 0.99,
            "macd": rng.normal(0, 1, n_days), "atr": close * 0.02, "bb_upper": close * 1.05, "bb_mid": close,
            "bb_lower": close * 0.95, "y_teacher": (close > open_price).astype(float)})
        teacher.append(stock)
        previous = pd.Series(close).shift(1)
        table.append(pd.DataFrame({
            "date": days.strftime("%Y-%m-%d"), "stock_id": f"S{k:02d}", "is_top50": int(k < 8),
            "stock_ret_lag1": (previous / pd.Series(close).shift(2) - 1).to_numpy(),
            "stock_ret_lag2": (previous / pd.Series(close).shift(3) - 1).to_numpy(),
            "label_intraday_return": close / open_price - 1, "label_y": (close > open_price).astype(float)}))
    return pd.concat(table, ignore_index=True), pd.concat(teacher, ignore_index=True), days


def morning_of(table, teacher, d):
    """d 早上看得到的資料：長表到 d 那列為止、d 沒有答案；老師檔只到 d 的前一天。"""
    cut = table[pd.to_datetime(table["date"]) <= d].copy()
    cut.loc[pd.to_datetime(cut["date"]) == d, ["label_intraday_return", "label_y"]] = np.nan
    return cut, teacher[teacher["date"] < d]


@pytest.fixture(scope="module")
def market():
    table, teacher, days = fake_market()
    codes = sorted(table.loc[table["is_top50"] == 1, "stock_id"].unique())
    return table, teacher, days, codes


def test_the_unlabeled_day_gets_the_same_prediction_as_with_full_data(market):
    table, teacher, days, codes = market
    d = days[-1]
    full = rank_ensemble.predict(None, CFG, [d], codes, frame=rank_ensemble.build_frame(table, teacher, CFG),
                                 fit_dates={d: d})
    blind_frame = rank_ensemble.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    blind = rank_ensemble.predict(None, CFG, [d], codes, frame=blind_frame)
    assert not blind_frame.loc[blind_frame["date"] == d, COLUMNS].isna().any().any()   # t 那列的欄都有值
    assert list(blind.columns) == ["date", "stock_id", "ridge", "kridge", "lgbm", "prob", "pred"]
    pd.testing.assert_frame_equal(full, blind)
    assert blind["pred"].sum() == len(codes) // 2 and blind["date"].unique().tolist() == [d.strftime("%Y-%m-%d")]


def test_data_on_the_day_and_later_change_nothing(market):
    table, teacher, days, codes = market
    d = days[-10]
    before = rank_ensemble.predict(None, CFG, [d], codes, frame=rank_ensemble.build_frame(table, teacher, CFG),
                                   fit_dates={d: d})
    later = pd.to_datetime(table["date"]) >= d
    poisoned_table, poisoned_teacher = table.copy(), teacher.copy()
    poisoned_table.loc[later, "label_intraday_return"] *= -3.0
    poisoned_teacher.loc[poisoned_teacher["date"] >= d, ["open", "high", "low", "volume", "foreign_net"]] *= 1.7
    after = rank_ensemble.predict(None, CFG, [d], codes,
                                  frame=rank_ensemble.build_frame(poisoned_table, poisoned_teacher, CFG),
                                  fit_dates={d: d})
    pd.testing.assert_frame_equal(before[["date", "stock_id", "ridge", "kridge", "lgbm"]],
                                  after[["date", "stock_id", "ridge", "kridge", "lgbm"]])


def test_stale_answers_missing_stocks_and_short_history_raise(market):
    table, teacher, days, codes = market
    d = days[-1]
    cut_table, cut_teacher = morning_of(table, teacher, d)
    stale = cut_table.copy()
    stale.loc[pd.to_datetime(stale["date"]) == days[-2], ["label_intraday_return", "label_y"]] = np.nan
    stale.loc[pd.to_datetime(stale["date"]) == d, ["stock_ret_lag1", "stock_ret_lag2"]] = np.nan   # 前一天沒有價格，長表留空白
    stale_frame = rank_ensemble.build_frame(stale, cut_teacher[cut_teacher["date"] < days[-2]], CFG, t=d)
    assert stale_frame.attrs["stale_days"] == 1
    with pytest.raises(rank_ensemble.EnsembleError, match="還沒有答案"):
        rank_ensemble.predict(None, CFG, [d], codes, frame=stale_frame)
    frame = rank_ensemble.build_frame(cut_table, cut_teacher, CFG, t=d)
    with pytest.raises(rank_ensemble.EnsembleError, match="沒有全部要預測的股票"):
        rank_ensemble.predict(None, CFG, [d], codes + ["ZZZ"], frame=frame)
    with pytest.raises(rank_ensemble.EnsembleError, match="個有答案的交易日"):
        rank_ensemble.predict(None, CFG, [days[20]], codes, frame=frame, fit_dates={days[20]: days[20]})
    wrong = {"rank_ensemble": {**CFG["rank_ensemble"], "columns": COLUMNS + ["no_such_column"]}}
    with pytest.raises(rank_ensemble.EnsembleError, match="不存在的欄"):
        rank_ensemble.build_frame(cut_table, cut_teacher, wrong, t=d)


def test_an_unfilled_previous_day_is_caught_from_the_crawler_record(market, tmp_path, monkeypatch):
    table, teacher, days, codes = market
    d, gone = days[-1], days[-2]   # 老師 Live 沒填 gone：features.py 會把那天整天從長表拿掉，t 的 lag 欄退到更前一天
    dates = pd.to_datetime(table["date"])
    stale = table[(dates <= d) & (dates != gone)].copy()
    stale.loc[dates == d, ["label_intraday_return", "label_y"]] = np.nan
    lags = table.loc[dates == gone, ["stock_ret_lag1", "stock_ret_lag2"]].to_numpy()
    stale.loc[dates == d, ["stock_ret_lag1", "stock_ret_lag2"]] = lags
    frame = rank_ensemble.build_frame(stale, teacher[teacher["date"] < gone], CFG, t=d)
    assert frame.attrs["stale_days"] == 0   # 從表看不出來，對齊檢查也會過
    monkeypatch.setattr(rank_ensemble, "load_frame", lambda cfg, t: frame)
    record = tmp_path / "manifest.json"

    def write(target, unfilled):
        record.write_text(json.dumps({"run": {"target_date": target},
                                      "teacher_live": {"prev_day_never_filled": unfilled}}), encoding="utf-8")

    write(d.strftime("%Y-%m-%d"), True)
    with pytest.raises(rank_ensemble.EnsembleError, match="還沒填"):
        rank_ensemble.predict(None, CFG, [d], codes, manifest_path=record)
    for target, unfilled in ((d.strftime("%Y-%m-%d"), False), ("2000-01-03", True)):   # 有填；別的 t 的紀錄
        write(target, unfilled)
        assert rank_ensemble.predict(None, CFG, [d], codes, manifest_path=record)["pred"].sum() == len(codes) // 2
    assert not rank_ensemble.previous_day_unfilled(d, tmp_path / "no_such_file.json")
    record.write_text("不是 JSON", encoding="utf-8")
    assert not rank_ensemble.previous_day_unfilled(d, record)


def test_the_default_crawler_record_path_is_read(market, tmp_path, monkeypatch):
    table, teacher, days, codes = market
    d = days[-1]
    frame = rank_ensemble.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    monkeypatch.setattr(rank_ensemble, "load_frame", lambda cfg, t: frame)
    monkeypatch.setattr(utils, "ROOT", tmp_path)
    record = tmp_path / "data" / "raw" / "manifest.json"   # 排程用的路徑：config 的 data.raw_dir 加 manifest.json
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"run": {"target_date": d.strftime("%Y-%m-%d")},
                                  "teacher_live": {"prev_day_never_filled": True}}), encoding="utf-8")
    cfg = {**CFG, "data": {"raw_dir": "data/raw"}}
    with pytest.raises(rank_ensemble.EnsembleError, match="還沒填"):
        rank_ensemble.predict(None, cfg, [d], codes)


def test_stocks_unfilled_on_the_previous_day_count_as_blank(market, tmp_path, monkeypatch):
    table, teacher, days, codes = market
    d = days[-1]
    frame = rank_ensemble.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    monkeypatch.setattr(rank_ensemble, "load_frame", lambda cfg, t: frame)
    record = tmp_path / "manifest.json"
    record.write_text(json.dumps({"run": {"target_date": d.strftime("%Y-%m-%d")},
                                  "teacher_live": {"prev_day_never_filled": False,
                                                   "prev_day_missing_stocks": [codes[0]]}}), encoding="utf-8")
    with pytest.raises(rank_ensemble.EnsembleError, match="的格子是空的"):   # 8 檔裡 1 檔整列空白，12.5% > 10%
        rank_ensemble.predict(None, CFG, [d], codes, manifest_path=record)
    loose = {"rank_ensemble": {**CFG["rank_ensemble"], "max_missing": 0.2}}
    blanked = rank_ensemble.predict(None, loose, [d], codes, manifest_path=record)
    kept = rank_ensemble.predict(None, loose, [d], codes, frame=frame)
    assert len(blanked) == len(codes) and not blanked.equals(kept)
    assert frame.loc[frame["date"] == d, COLUMNS].notna().all().all()   # 傳進來的表沒有被改到


def test_predictions_that_are_not_finite_raise(market, monkeypatch):
    table, teacher, days, codes = market
    d = days[-1]
    frame = rank_ensemble.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    real = rank_ensemble.fit_predict

    def broken(*args):
        scores = real(*args)
        scores["lgbm"] = np.full(len(scores["lgbm"]), np.nan)
        return scores

    monkeypatch.setattr(rank_ensemble, "fit_predict", broken)
    with pytest.raises(rank_ensemble.EnsembleError, match="不是有限的數"):
        rank_ensemble.predict(None, CFG, [d], codes, frame=frame)


def test_blank_columns_on_the_prediction_day_raise(market):
    table, teacher, days, codes = market
    d = days[-1]
    frame = rank_ensemble.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    on_d = frame["date"] == d
    one_column = frame.copy()
    one_column.loc[on_d, "a_rsi"] = np.nan   # 一欄全部空白
    with pytest.raises(rank_ensemble.EnsembleError, match="1 欄全部空白：a_rsi"):
        rank_ensemble.predict(None, CFG, [d], codes, frame=one_column)
    one_stock = frame.copy()
    one_stock.loc[on_d & (one_stock["stock_id"] == codes[0]), COLUMNS] = np.nan   # 8 檔裡 1 檔全空，12.5% > 10%
    with pytest.raises(rank_ensemble.EnsembleError, match="的格子是空的"):
        rank_ensemble.predict(None, CFG, [d], codes, frame=one_stock)
    assert len(rank_ensemble.predict(None, CFG, [d], codes, frame=one_stock, allow_missing=True)) == len(codes)


def test_the_real_config_has_what_the_code_reads(market):
    table, teacher, days, codes = market
    m = utils.load_config()["rank_ensemble"]
    assert set(m) == {"columns", "train_days", "min_train_days", "max_missing", "target_clip", "ridge_alpha",
                      "kernel_components", "kernel_gamma_scale", "kernel_alpha", "seeds", "max_stale_days", "lgbm"}
    assert len(m["columns"]) == len(set(m["columns"])) == 41
    frame = rank_ensemble.build_frame(table, teacher, CFG)
    assert set(m["columns"]) <= set(frame.columns)
    assert not {"kospi_open_gap", "n225_open_gap"} & set(m["columns"])
    assert m["min_train_days"] <= m["train_days"] and m["lgbm"]["n_jobs"] == 1


def test_read_teacher_stock_drops_live_rows_without_prices(tmp_path):
    header = list(crawler.STOCK_COLUMNS)

    def line(d, close="10.0", foreign_net="5"):
        return [d, close, "9.0", "11.0", "8.0", "100", "1000", "100", "50", foreign_net, "3", "2", "1", "55", "9.5",
                "0.1", "0.2", "11", "10", "9", "1"]

    def write(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(",".join(r) for r in [header] + rows) + "\n", encoding="utf-8")

    write(tmp_path / "training" / "market" / "A.csv", [line("2026-08-28", foreign_net="-1"), line("2026-08-31")])
    write(tmp_path / "live" / "market" / "A.csv",
          [line("2026-08-31", close="99"), line("2026-09-01", foreign_net="-1"), ["2026-09-02"] + ["-1"] * 20])
    stock = rank_ensemble.read_teacher_stock(tmp_path, "A").set_index("date")
    assert [d.strftime("%Y-%m-%d") for d in stock.index] == ["2026-08-28", "2026-08-31", "2026-09-01"]
    assert stock.loc["2026-08-31", "close"] == 10.0            # Live 只取 Training 之後
    assert stock.loc["2026-08-28", "foreign_net"] == -1        # Training 的 -1 是真的值
    assert np.isnan(stock.loc["2026-09-01", "foreign_net"])    # Live 的 -1 是還沒公布


# ---------------------------------------------------------------- run_daily_test.py 的備援順序


@pytest.fixture
def chain(monkeypatch):
    for name, module in (("crawler", crawler), ("features", features), ("online_lr", online_lr),
                         ("site_api", site_api)):
        monkeypatch.setattr(rdt, name, module)
    calls = []

    def fake(name, fail):
        def predict(data, cfg, dates, ids):
            calls.append(name)
            if fail:
                raise RuntimeError(f"{name} 壞了")
            return name
        return predict

    def install(failing):
        for name, module in (("rank_ensemble", rank_ensemble), ("persist", persist_rule), ("online_lr", online_lr)):
            monkeypatch.setattr(module, "predict", fake(name, name in failing))
        return calls

    return install


def test_fallbacks_are_tried_in_order(chain, caplog):
    cfg = {"daily_model": {"kind": "rank_ensemble", "fallback": ["persist", "online_lr"]}}
    calls = chain(failing=())
    assert rdt.daily_predict(cfg, None, ["2026-11-12"], ["2330"], LOG) == ("rank_ensemble", "rank_ensemble")
    assert calls == ["rank_ensemble"]
    calls = chain(failing=("rank_ensemble", "persist"))
    calls.clear()
    with caplog.at_level(logging.ERROR):
        name, pred = rdt.daily_predict(cfg, None, ["2026-11-12"], ["2330"], LOG)
    assert (name, pred) == ("online_lr（rank_ensemble 的備援）", "online_lr")
    assert calls == ["rank_ensemble", "persist", "online_lr"] and "rank_ensemble 算不出來" in caplog.text
    chain(failing=("rank_ensemble", "persist", "online_lr"))
    with pytest.raises(RuntimeError, match="online_lr 壞了"):
        rdt.daily_predict(cfg, None, ["2026-11-12"], ["2330"], LOG)


def test_the_model_names_in_the_config_are_checked(chain, caplog):
    for kind in ("xgboost", "none"):   # 主模型不認得、或填 none：停下，不要默默換成備援
        with pytest.raises(rdt.StopRun, match="daily_model.kind"):
            rdt.daily_predict({"daily_model": {"kind": kind, "fallback": ["persist"]}}, None, [], [], LOG)
    calls = chain(failing=("persist",))
    calls.clear()
    cfg = {"daily_model": {"kind": "persist", "fallback": ["online-lr", "None", "persist", "online_lr", "online_lr"]}}
    with caplog.at_level(logging.ERROR):
        name, pred = rdt.daily_predict(cfg, None, ["2026-11-12"], ["2330"], LOG)
    assert (name, pred) == ("online_lr（persist 的備援）", "online_lr") and calls == ["persist", "online_lr"]
    assert "online-lr 不認得或重複" in caplog.text and "None 不認得" not in caplog.text
    calls.clear()
    chain(failing=())
    assert rdt.daily_predict({"daily_model": {"kind": "persist", "fallback": ["xgboost"]}}, None, [], [], LOG)[0] == "persist"


def test_the_fallback_log_does_not_write_the_home_directory(chain, monkeypatch, caplog):
    chain(failing=())

    def broken(data, cfg, dates, ids):
        raise FileNotFoundError(f"{rdt.ROOT}/data/raw/teacher/x.csv 和 {Path.home()}/y 不見了")

    monkeypatch.setattr(rank_ensemble, "predict", broken)
    with caplog.at_level(logging.ERROR):
        rdt.daily_predict({"daily_model": {"kind": "rank_ensemble", "fallback": "persist"}}, None, [], [], LOG)
    assert "./data/raw/teacher/x.csv" in caplog.text and "~/y" in caplog.text
    assert str(Path.home()) not in caplog.text


def test_a_model_that_cannot_be_loaded_falls_back(chain, monkeypatch, caplog):
    cfg = {"daily_model": {"kind": "rank_ensemble", "fallback": ["persist", "online_lr"]}}
    calls = chain(failing=())
    monkeypatch.setitem(sys.modules, "src.rank_ensemble", None)   # 等於這個檔不見了：import 會丟 ImportError
    with caplog.at_level(logging.ERROR):
        name, pred = rdt.daily_predict(cfg, None, ["2026-11-12"], ["2330"], LOG)
    assert (name, pred) == ("persist（rank_ensemble 的備援）", "persist") and calls == ["persist"]
    assert "rank_ensemble 算不出來（ModuleNotFoundError" in caplog.text
