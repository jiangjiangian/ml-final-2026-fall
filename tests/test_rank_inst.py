"""法人組排名集成（src/models/m6_rank_inst.py，使用者 2026-11-20）：只給影子跑；早上法人資料沒到就傍晚補算。

資料都是假的（test_rank_ensemble 的 fake_market）。不連網、不讀 data/。
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.models import MODEL_KINDS, SHADOW_ONLY, m3_rank_ensemble as rank_ensemble, m6_rank_inst as ri
from src.pipeline import step3_train_predict as tp, step6_evening_score as ev
from tests.test_evening_score import SECRETS, STOCKS, T, env, ledger  # noqa: F401（env 是 fixture）
from tests.test_rank_ensemble import CFG as BASE_CFG, fake_market, morning_of

LOG = logging.getLogger("test_rank_inst")
NEW = ["f_foreign_pct20", "f_trust_pct5", "f_trust_pct20", "f_inst_pct", "f_foreign_streak", "f_trust_streak",
       "f_foreign_z60", "f_foreign_hold", "f_foreign_hold_chg20", "f_foreign_ema5_gap", "f_foreign_ema10_gap",
       "f_foreign_ema20_gap", "f_trust_ema5_gap", "f_trust_ema10_gap", "f_trust_ema20_gap", "f_inst_ema5_gap",
       "f_inst_ema10_gap", "f_inst_ema20_gap"]
INST = ["c_trust_pct", "c_dealer_pct", "c_foreign_pct5"] + NEW   # 假的設定裡 c_foreign_pct、c_foreign_hold_chg5 已經在價量欄
CFG = {**BASE_CFG, "rank_inst": {"columns": INST, "min_filled_share": 0.9}}
BOTH = BASE_CFG["rank_ensemble"]["columns"] + INST


@pytest.fixture(scope="module")
def market():
    table, teacher, days = fake_market()
    codes = sorted(table.loc[table["is_top50"] == 1, "stock_id"].unique())
    return table, teacher, days, codes


def manifest(tmp_path, t, **live) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"run": {"target_date": f"{t:%Y-%m-%d}"}, "teacher_live": live}))
    return path


# ---------------------------------------------------------------- 法人欄


def test_streak_counts_runs_and_resets_on_zero():
    sign = pd.Series([1.0, 1.0, 1.0, -1.0, -1.0, 0.0, 1.0])
    assert ri.streak(sign).tolist() == [1.0, 2.0, 3.0, -1.0, -2.0, 0.0, 1.0]
    assert ri.streak(pd.Series([1.0] * 30)).iloc[-1] == 20.0          # 截在 ±20
    assert ri.streak(pd.Series([-1.0] * 30)).iloc[-1] == -20.0


def test_institution_features_follow_the_notebook_formulas(market):
    _, teacher, _, _ = market
    stock = teacher[teacher["stock_id"] == "S00"].reset_index(drop=True)
    got = ri.institution_features(stock)
    assert list(got.columns) == NEW                                   # 順序和 notebook 25 一樣
    total = stock["foreign_net"] + stock["trust_net"] + stock["dealer_self_net"] + stock["dealer_hedge_net"]
    i = len(stock) - 1
    assert got["f_inst_pct"].iloc[i] == pytest.approx(np.clip(total.iloc[i] / stock["volume"].iloc[i], -1, 1))
    assert got["f_foreign_pct20"].iloc[i] == pytest.approx(stock["foreign_net"].iloc[i - 19:].sum()
                                                           / stock["volume"].iloc[i - 19:].sum())
    assert got["f_foreign_hold"].iloc[i] == pytest.approx(stock["foreign_hold"].iloc[i] / 100)
    assert got["f_foreign_hold_chg20"].iloc[i] == pytest.approx(stock["foreign_hold"].iloc[i]
                                                                - stock["foreign_hold"].iloc[i - 20])
    ema = stock["trust_net"].ewm(span=10, adjust=False).mean().iloc[i]
    assert got["f_trust_ema10_gap"].iloc[i] == pytest.approx((stock["trust_net"].iloc[i] - ema)
                                                             / stock["volume"].iloc[i - 19:].mean())


def test_the_t_row_holds_the_previous_day_values(market):
    table, teacher, days, _ = market
    d = days[-1]
    frame = ri.build_frame(*morning_of(table, teacher, d), CFG, t=d)
    stock = teacher[(teacher["stock_id"] == "S03") & (teacher["date"] < d)].reset_index(drop=True)
    raw = ri.institution_features(stock).iloc[-1]                     # d 的前一天收盤後的值
    row = frame[(frame["date"] == d) & (frame["stock_id"] == "S03")].iloc[0]
    assert row[NEW].astype(float).to_numpy() == pytest.approx(raw.to_numpy())
    assert not frame.loc[frame["date"] == d, BOTH].isna().any().any()
    assert frame.attrs["stale_days"] == 0                             # m3 的檢查要用，接欄以後還在


def test_data_on_the_day_and_later_change_nothing(market):
    table, teacher, days, codes = market
    d = days[-10]
    before = ri.predict(None, CFG, [d], codes, frame=ri.build_frame(table, teacher, CFG), fit_dates={d: d})
    poisoned_table, poisoned_teacher = table.copy(), teacher.copy()
    poisoned_table.loc[pd.to_datetime(table["date"]) >= d, "label_intraday_return"] *= -3.0
    later = poisoned_teacher["date"] >= d
    poisoned_teacher.loc[later, ["open", "high", "low", "volume", "foreign_net", "trust_net", "dealer_self_net",
                                 "dealer_hedge_net", "foreign_hold"]] *= 1.7
    after = ri.predict(None, CFG, [d], codes, frame=ri.build_frame(poisoned_table, poisoned_teacher, CFG),
                       fit_dates={d: d})
    pd.testing.assert_frame_equal(before, after)


def test_the_unlabeled_day_gets_the_same_prediction_as_with_full_data(market):
    table, teacher, days, codes = market
    d = days[-1]
    full = ri.predict(None, CFG, [d], codes, frame=ri.build_frame(table, teacher, CFG), fit_dates={d: d})
    blind = ri.predict(None, CFG, [d], codes, frame=ri.build_frame(*morning_of(table, teacher, d), CFG, t=d))
    pd.testing.assert_frame_equal(full, blind)
    assert list(blind.columns) == ["date", "stock_id", "ridge", "kridge", "lgbm", "prob", "pred", "inst_filled", "late"]
    assert blind["pred"].sum() == len(codes) // 2 and (blind["late"] == 0).all()


def test_the_models_see_the_price_columns_then_the_institution_columns(market, monkeypatch):
    table, teacher, days, codes = market
    seen = {}

    def fake(data, cfg, dates, stocks, **kwargs):
        seen["columns"] = cfg["rank_ensemble"]["columns"]
        return pd.DataFrame({"date": f"{days[-1]:%Y-%m-%d}", "stock_id": sorted(stocks), "pred": 1, "prob": 0.5})

    monkeypatch.setattr(rank_ensemble, "predict", fake)
    ri.predict(None, CFG, [days[-1]], codes, frame=ri.build_frame(table, teacher, CFG))
    assert seen["columns"] == BOTH
    assert CFG["rank_ensemble"]["columns"] == BASE_CFG["rank_ensemble"]["columns"]   # 原本的設定沒被改到


# ---------------------------------------------------------------- 早上的檢查和傍晚補算


@pytest.fixture
def morning(market, monkeypatch):
    """predict 自己讀資料的那條路：load_frame 換成假資料 d 早上的表。"""
    table, teacher, days, codes = market
    d = days[-1]
    box = {"frame": ri.build_frame(*morning_of(table, teacher, d), CFG, t=d)}
    monkeypatch.setattr(ri, "load_frame", lambda cfg, t: box["frame"])
    return d, codes, box


def test_a_normal_morning_counts_the_filled_stocks(morning, tmp_path):
    d, codes, _ = morning
    out = ri.predict(None, CFG, [d], codes, manifest_path=manifest(tmp_path, d))
    assert (out["inst_filled"] == len(codes)).all() and (out["late"] == 0).all()
    assert out["pred"].sum() == len(codes) // 2


def test_an_unfilled_previous_day_waits_for_the_evening(morning, tmp_path):
    d, codes, _ = morning
    path = manifest(tmp_path, d, prev_day_never_filled=True)
    with pytest.raises(ri.InstError, match="等傍晚補算"):
        ri.predict(None, CFG, [d], codes, manifest_path=path)
    out = ri.predict(None, CFG, [d], codes, late=True, manifest_path=path)   # 傍晚不看早上的紀錄
    assert (out["late"] == 1).all() and (out["inst_filled"] == len(codes)).all()


def test_missing_institution_values_wait_for_the_evening(morning, tmp_path):
    d, codes, box = morning
    frame = box["frame"].copy()
    frame.attrs = dict(box["frame"].attrs)
    frame.loc[(frame["date"] == d) & frame["stock_id"].isin(codes[:3]), ["f_inst_pct"]] = np.nan
    box["frame"] = frame
    with pytest.raises(ri.InstError, match="只有 5 檔有值，等傍晚補算"):
        ri.predict(None, CFG, [d], codes, manifest_path=manifest(tmp_path, d))
    with pytest.raises(ri.InstError, match="只有 5 檔有值$"):
        ri.predict(None, CFG, [d], codes, late=True, manifest_path=manifest(tmp_path, d))


def test_too_many_stocks_unfilled_yesterday_raise_our_error(morning, tmp_path):
    d, codes, _ = morning
    path = manifest(tmp_path, d, prev_day_missing_stocks=codes[:4])
    with pytest.raises(ri.InstError):
        ri.predict(None, CFG, [d], codes, manifest_path=path)


def test_a_bad_column_name_raises(market):
    table, teacher, _, _ = market
    bad = {**CFG, "rank_inst": {**CFG["rank_inst"], "columns": INST + ["f_no_such_column"]}}
    with pytest.raises(ri.InstError, match="f_no_such_column"):
        ri.build_frame(table, teacher, bad)


# ---------------------------------------------------------------- 只能影子跑、影子檔、傍晚補算


def test_rank_inst_can_only_be_a_shadow_model(caplog):
    assert "rank_inst" in MODEL_KINDS and "rank_inst" in SHADOW_ONLY
    with pytest.raises(tp.ModelChoiceError):
        tp.model_order({"daily_model": {"kind": "rank_inst"}}, LOG)
    with caplog.at_level(logging.ERROR):
        assert tp.model_order({"daily_model": {"kind": "persist", "fallback": ["rank_inst"]}}, LOG) == ["persist"]
    assert tp.shadow_models({"daily_model": {"shadow": ["persist", "rank_inst"]}}) == ["persist", "rank_inst"]


def shadow_cfg(tmp_path, shadow=("persist", "rank_inst")) -> dict:
    return {"daily_model": {"kind": "persist", "shadow": list(shadow)}, "data": {"submission_dir": str(tmp_path)}}


def fake_prediction(stocks, late=False):
    return pd.DataFrame({"date": T, "stock_id": sorted(stocks), "pred": [1, 0] * (len(stocks) // 2),
                         "prob": np.linspace(0.9, 0.1, len(stocks)), "inst_filled": len(stocks), "late": int(late)})


def test_the_shadow_file_gets_the_extra_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(ri, "predict", lambda data, cfg, dates, stocks: fake_prediction(stocks))
    cfg = shadow_cfg(tmp_path, ["rank_inst"])
    table = pd.read_csv(tp.shadow_predict(cfg, None, T, STOCKS, LOG), dtype={"stock_id": str})
    assert table["pred_rank_inst"].tolist() == [1, 0, 1, 0]
    assert table["inst_filled_rank_inst"].tolist() == [4] * 4 and table["late_rank_inst"].tolist() == [0] * 4


def write_shadow(tmp_path, **columns) -> Path:
    path = tmp_path / f"shadow_{T}.csv"
    pd.DataFrame({"date": T, "stock_id": sorted(STOCKS), "pred_persist": [1, 1, 0, 0], "prob_persist": 0.5,
                  **columns}).to_csv(path, index=False)
    return path


def test_backfill_fills_the_blank_model_and_leaves_the_others(monkeypatch, tmp_path, caplog):
    calls = []

    def late_predict(data, cfg, dates, stocks, late=False):
        calls.append((dates, list(stocks), late))
        return fake_prediction(stocks, late)

    monkeypatch.setattr(ri, "predict", late_predict)
    path = write_shadow(tmp_path, pred_rank_inst=np.nan, prob_rank_inst=np.nan, inst_filled_rank_inst=np.nan,
                        late_rank_inst=np.nan)
    with caplog.at_level(logging.INFO):
        assert tp.shadow_backfill(shadow_cfg(tmp_path), T, LOG) == ["rank_inst"]
    assert calls == [([T], sorted(STOCKS), True)]
    table = pd.read_csv(path, dtype={"stock_id": str})
    assert table["pred_rank_inst"].tolist() == [1, 0, 1, 0] and table["late_rank_inst"].tolist() == [1] * 4
    assert table["inst_filled_rank_inst"].tolist() == [4] * 4
    assert table["pred_persist"].tolist() == [1, 1, 0, 0] and table["stock_id"].tolist() == sorted(STOCKS)
    assert "影子跑補算" in caplog.text
    assert tp.shadow_backfill(shadow_cfg(tmp_path), T, LOG) == [] and len(calls) == 1   # 已經有了，不重算


def test_backfill_adds_the_columns_when_the_morning_file_has_none(monkeypatch, tmp_path):
    monkeypatch.setattr(ri, "predict", lambda data, cfg, dates, stocks, late=False: fake_prediction(stocks, late))
    path = write_shadow(tmp_path)
    assert tp.shadow_backfill(shadow_cfg(tmp_path), T, LOG) == ["rank_inst"]
    assert pd.read_csv(path)["pred_rank_inst"].tolist() == [1, 0, 1, 0]


def test_backfill_does_nothing_without_the_model_the_file_or_a_result(monkeypatch, tmp_path, caplog):
    def broken(data, cfg, dates, stocks, late=False):
        raise ri.InstError("法人欄只有 0 檔有值")

    monkeypatch.setattr(ri, "predict", broken)
    assert tp.shadow_backfill(shadow_cfg(tmp_path), T, LOG) == []                     # 沒有影子檔
    path = write_shadow(tmp_path, pred_rank_inst=np.nan)
    before = path.read_bytes()
    assert tp.shadow_backfill(shadow_cfg(tmp_path, ["persist"]), T, LOG) == []        # shadow 沒列 rank_inst
    with caplog.at_level(logging.WARNING):
        assert tp.shadow_backfill(shadow_cfg(tmp_path), T, LOG) == []                 # 還是算不出來
    assert path.read_bytes() == before and "還是算不出來" in caplog.text


def test_the_evening_run_backfills_before_scoring(env, monkeypatch):  # noqa: F811
    cfg, site, _, tmp = env
    cfg["daily_model"] = {"kind": "persist", "shadow": ["rank_inst"]}
    path = Path(cfg["data"]["submission_dir"]) / f"shadow_{T}.csv"
    table = pd.read_csv(path, dtype={"stock_id": str}).assign(pred_rank_inst=np.nan)
    table.to_csv(path, index=False)
    monkeypatch.setattr(ri, "predict", lambda data, cfg, dates, stocks, late=False: fake_prediction(stocks, late))
    assert ev.main(cfg, 2, T, LOG, site=site, secrets=SECRETS) == "scored"
    filled = pd.read_csv(path, dtype={"stock_id": str})
    assert filled["pred_rank_inst"].tolist() == [1, 0, 1, 0] and filled["late_rank_inst"].tolist() == [1] * 4
    assert "rank_inst" in ledger(env)["model"].tolist()                              # 補算的當天就打分


def test_a_broken_backfill_does_not_stop_the_scoring(env, monkeypatch, caplog):  # noqa: F811
    cfg, site, _, _ = env
    cfg["daily_model"] = {"kind": "persist", "shadow": ["rank_inst"]}

    def explode(cfg, t, log):
        raise OSError("disk")

    monkeypatch.setattr(tp, "shadow_backfill", explode)
    with caplog.at_level(logging.WARNING):
        assert ev.main(cfg, 2, T, LOG, site=site, secrets=SECRETS) == "scored"
    assert "影子跑補算沒做完" in caplog.text
