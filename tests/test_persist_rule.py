"""持續性規則（src/persist_rule.py）：算法和 notebook 14 一樣、不偷看當天和之後的答案；run_daily_test.py 的模型開關。"""

import logging

import numpy as np
import pandas as pd
import pytest

import run_daily_test as rdt
from src import crawler, features, online_lr, persist_rule, site_api, utils

CFG = {"persist_rule": {"days": 20, "min_days": 10, "max_stale_days": 3, "min_scored_share": 0.8}}
LOG = logging.getLogger("test_persist_rule")


def make_table(n_days=60, n_stocks=10, seed=0, unlabeled=1):
    """n_days 個交易日 × n_stocks 檔的長表；最後 unlabeled 天沒有答案，像早上的 t 那列。"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=n_days)
    codes = [f"S{k:02d}" for k in range(n_stocks)]
    table = pd.DataFrame({"date": np.repeat(days, n_stocks), "stock_id": np.tile(codes, n_days)})
    table["label_intraday_return"] = rng.normal(0, 0.01, len(table))
    table.loc[table["date"].isin(days[n_days - unlabeled:]), "label_intraday_return"] = np.nan
    return table, days, codes


def notebook_scores(table, codes, days_back, min_days):
    """notebook 14 第 3 節的寫法：pivot 之後 shift(1) 再 rolling，每列是那一天開盤前的分數。"""
    history = table[table["stock_id"].isin(codes) & table["label_intraday_return"].notna()].copy()
    history["e"] = history["label_intraday_return"] - history.groupby("date")["label_intraday_return"].transform("mean")
    relative = history.pivot(index="date", columns="stock_id", values="e").sort_index()
    return relative.shift(1).rolling(days_back, min_periods=min_days).mean()


def notebook_sides(scores):
    """notebook 14 的 day_rank 和 neutral_score：名次的前一半是 1。"""
    rank = (scores.rank(pct=True) - 0.5).fillna(0.0)
    return (rank.rank(method="first") > len(scores) / 2).astype(int)


def test_scores_and_sides_match_the_notebook_on_every_labeled_day():
    table, days, codes = make_table(unlabeled=0)
    want = notebook_scores(table, codes, 20, 10)
    target = [d.strftime("%Y-%m-%d") for d in days[15:]]
    got = persist_rule.predict(table, CFG, target, codes)
    assert list(got.columns) == ["date", "stock_id", "score", "prob", "pred"] and len(got) == len(target) * len(codes)
    for d in days[15:]:
        day = got[got["date"] == d.strftime("%Y-%m-%d")].set_index("stock_id")
        np.testing.assert_allclose(day["score"].to_numpy(), want.loc[d, codes].to_numpy(), rtol=0, atol=1e-15)
        assert day["pred"].tolist() == notebook_sides(want.loc[d, codes]).tolist()
        assert day["pred"].sum() == len(codes) // 2


def test_the_unlabeled_day_uses_the_days_before_it():
    table, days, codes = make_table(unlabeled=1)
    t = days[-1]
    got = persist_rule.predict(table, CFG, [t.strftime("%Y-%m-%d")], codes).set_index("stock_id")
    past = table[table["date"].isin(days[-21:-1])].copy()   # t 之前 20 個有答案的日子
    past["e"] = past["label_intraday_return"] - past.groupby("date")["label_intraday_return"].transform("mean")
    np.testing.assert_allclose(got["score"].to_numpy(), past.groupby("stock_id")["e"].mean().loc[codes].to_numpy(),
                               rtol=0, atol=1e-15)
    assert got["pred"].sum() == 5 and set(got["pred"]) == {0, 1}


def test_answers_on_the_day_and_later_change_nothing():
    table, days, codes = make_table(unlabeled=0)
    d = days[40]
    before = persist_rule.predict(table, CFG, [d.strftime("%Y-%m-%d")], codes)
    poisoned = table.copy()
    poisoned.loc[poisoned["date"] >= d, "label_intraday_return"] = 9.0
    pd.testing.assert_frame_equal(before, persist_rule.predict(poisoned, CFG, [d.strftime("%Y-%m-%d")], codes))
    earlier = table.copy()
    earlier.loc[(earlier["date"] == days[39]) & (earlier["stock_id"] == codes[0]), "label_intraday_return"] = 9.0
    assert not before.equals(persist_rule.predict(earlier, CFG, [d.strftime("%Y-%m-%d")], codes))


def test_a_stock_without_enough_history_sits_in_the_middle():
    table, days, codes = make_table(unlabeled=1)
    table.loc[(table["stock_id"] == codes[3]) & (table["date"] < days[-6]), "label_intraday_return"] = np.nan
    got = persist_rule.predict(table, CFG, [days[-1].strftime("%Y-%m-%d")], codes).set_index("stock_id")
    assert np.isnan(got.loc[codes[3], "score"]) and got.loc[codes[3], "prob"] == 0.5
    assert got["pred"].sum() == 5


def test_equal_scores_break_ties_by_code():
    table, days, codes = make_table(unlabeled=1)
    table.loc[table["label_intraday_return"].notna(), "label_intraday_return"] = 0.01   # 每檔都一樣，e 全是 0
    got = persist_rule.predict(table, CFG, [days[-1].strftime("%Y-%m-%d")], list(reversed(codes)))
    assert got["stock_id"].tolist() == codes and got["pred"].tolist() == [0] * 5 + [1] * 5


def test_stale_answers_or_too_few_scores_raise():
    table, days, codes = make_table(unlabeled=5)   # t 之前還有 4 個交易日沒有答案
    with pytest.raises(persist_rule.RuleError, match="隔了 4 個交易日"):
        persist_rule.predict(table, CFG, [days[-1].strftime("%Y-%m-%d")], codes)
    table, days, codes = make_table(unlabeled=1)
    table.loc[table["stock_id"].isin(codes[:3]) & (table["date"] < days[-6]), "label_intraday_return"] = np.nan
    with pytest.raises(persist_rule.RuleError, match="只有 7 檔有分數"):
        persist_rule.predict(table, CFG, [days[-1].strftime("%Y-%m-%d")], codes)
    with pytest.raises(persist_rule.RuleError):
        persist_rule.predict(table, CFG, ["2024-12-31"], codes)   # 之前沒有任何答案
    with pytest.raises(persist_rule.RuleError):
        persist_rule.predict(table, CFG, [], codes)


def test_config_selects_known_models_and_has_the_rule_settings():
    cfg = utils.load_config()
    fallback = cfg["daily_model"]["fallback"]
    order = [cfg["daily_model"]["kind"]] + ([fallback] if isinstance(fallback, str) else list(fallback))
    assert order[0] in rdt.MODEL_KINDS and len(set(order)) == len(order)
    assert all(kind in rdt.MODEL_KINDS or kind == "none" for kind in order[1:])
    assert set(cfg["persist_rule"]) == {"days", "min_days", "max_stale_days", "min_scored_share"}
    assert cfg["persist_rule"]["min_days"] <= cfg["persist_rule"]["days"]


# ---------------------------------------------------------------- run_daily_test.py 的模型開關


@pytest.fixture
def switch(monkeypatch):
    """rdt 的 src 模組換成真的（平常 import_src 之後才有），online_lr.predict 換成只回傳記號的假函式。"""
    for name, module in (("crawler", crawler), ("features", features), ("online_lr", online_lr),
                         ("site_api", site_api)):
        monkeypatch.setattr(rdt, name, module)
    monkeypatch.setattr(online_lr, "predict", lambda data, cfg, dates, ids: "組員的模型")
    table, days, codes = make_table(unlabeled=1)
    return table, [days[-1].strftime("%Y-%m-%d")], codes


def test_persist_is_used_when_selected(switch):
    table, dates, codes = switch
    name, pred = rdt.daily_predict({**CFG, "daily_model": {"kind": "persist", "fallback": "online_lr"}},
                                   table, dates, codes, LOG)
    assert name == "persist" and pred["pred"].sum() == 5


def test_persist_failure_falls_back_to_online_lr(switch, caplog):
    table, dates, codes = switch
    cfg = {"persist_rule": {**CFG["persist_rule"], "min_scored_share": 2.0},   # 要求 200% 的股票有分數，一定不夠
           "daily_model": {"kind": "persist", "fallback": "online_lr"}}
    with caplog.at_level(logging.ERROR):
        name, pred = rdt.daily_predict(cfg, table, dates, codes, LOG)
    assert pred == "組員的模型" and name == "online_lr（persist 的備援）" and "persist 算不出來" in caplog.text
    cfg["daily_model"]["fallback"] = "none"
    with pytest.raises(persist_rule.RuleError):
        rdt.daily_predict(cfg, table, dates, codes, LOG)


def test_online_lr_is_the_default_and_unknown_kinds_stop(switch):
    table, dates, codes = switch
    assert rdt.daily_predict(CFG, table, dates, codes, LOG) == ("online_lr", "組員的模型")
    assert rdt.daily_predict({**CFG, "daily_model": {"kind": "online_lr"}}, table, dates, codes, LOG)[0] == "online_lr"
    with pytest.raises(rdt.StopRun):
        rdt.daily_predict({**CFG, "daily_model": {"kind": "lightgbm"}}, table, dates, codes, LOG)
