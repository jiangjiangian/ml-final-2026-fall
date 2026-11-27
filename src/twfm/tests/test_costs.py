"""`twfm.eval.costs` 和 `twfm.eval.backtest` 的測試：成本的例子、回測的毛報酬、成本、可成交遮罩。"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

import twfm.config as config
import twfm.eval.costs as costs
import twfm.eval.backtest as backtest


def _model(**kwargs: Any) -> Any:
    return costs.TaiwanCostModel(config.CostConfig(**kwargs))


def _frame(rows: list[tuple[str, str, float]], col: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime([r[0] for r in rows]),
            "stock_id": [r[1] for r in rows],
            col: [r[2] for r in rows],
        }
    )


# 兩天、四檔。第一天 2 多 2 空，第二天 1 多 1 空（C、D 沒有權重列，但有報酬列）。
D1, D2 = "2025-07-01", "2025-07-02"
WEIGHTS = _frame(
    [
        (D1, "1101", 0.25),
        (D1, "1102", 0.25),
        (D1, "1103", -0.25),
        (D1, "1104", -0.25),
        (D2, "1101", 0.5),
        (D2, "1102", -0.5),
    ],
    "weight",
)
LABELS = pd.DataFrame(
    {
        "date": pd.to_datetime([D1] * 4 + [D2] * 4),
        "stock_id": ["1101", "1102", "1103", "1104"] * 2,
        "label_r": [0.02, -0.01, 0.03, -0.04, 0.01, 0.02, -0.03, 0.05],
        # 第一天 1101 開盤漲停（做多買不到）、1103 開盤漲停但它是空單（照樣成交）；
        # 第二天 1102 開盤跌停（做空空不到）。
        "exec_long_ok": [0, 1, 0, 1, 1, 1, 1, 1],
        "exec_short_ok": [1, 1, 1, 1, 1, 0, 1, 1],
    }
)


# ---------------------------------------------------------------------------
# 成本模型
# ---------------------------------------------------------------------------


def test_round_trip_examples() -> None:
    assert _model(commission_discount=0.28).round_trip_rate(daytrade=True) == pytest.approx(0.002298, abs=1e-12)
    assert _model(commission_discount=1.0).round_trip_rate(daytrade=False) == pytest.approx(0.00585, abs=1e-12)
    m = _model(commission_discount=0.6)
    assert m.commission_rate_effective == pytest.approx(0.000855, abs=1e-15)
    assert m.round_trip_rate() == pytest.approx(2 * 0.000855 + 0.0015, abs=1e-15)
    slip = _model(commission_discount=1.0, slippage_bps=5.0)
    assert slip.round_trip_rate(daytrade=True) == pytest.approx(0.00285 + 0.0015 + 0.001, abs=1e-15)
    assert m.with_discount(1.0).round_trip_rate(daytrade=False) == pytest.approx(0.00585, abs=1e-12)
    assert m.cfg.commission_discount == 0.6


def test_sell_tax_rates_and_daytrade_cut_end() -> None:
    m = _model()
    assert m.sell_tax(True, False) == pytest.approx(0.0015)
    assert m.sell_tax(False, False) == pytest.approx(0.003)
    assert m.sell_tax(True, True) == pytest.approx(0.001)
    assert m.sell_tax(False, True) == pytest.approx(0.001)
    # 當沖減半到 2027-12-31（含），之後改回一般稅率；ETF 不受影響
    assert m.sell_tax(True, False, date="2027-12-31") == pytest.approx(0.0015)
    assert m.sell_tax(True, False, date="2028-01-03") == pytest.approx(0.003)
    assert m.sell_tax(True, True, date="2028-01-03") == pytest.approx(0.001)
    assert m.round_trip_rate(daytrade=True, date="2028-01-03") == pytest.approx(m.round_trip_rate(daytrade=False))
    rates = m.sell_tax_rates(
        (3,),
        daytrade=True,
        is_etf=np.array([False, False, True]),
        dates=np.array(["2025-07-01", "2028-01-03", "2028-01-03"], dtype="datetime64[ns]"),
    )
    np.testing.assert_allclose(rates, [0.0015, 0.003, 0.001])
    # 減半從 2017-04-28 才開始，之前的當沖用一般稅率
    assert m.sell_tax(True, False, date="2016-06-01") == pytest.approx(0.003)
    assert m.sell_tax(True, False, date="2017-04-27") == pytest.approx(0.003)
    assert m.sell_tax(True, False, date="2017-04-28") == pytest.approx(0.0015)
    assert m.round_trip_rate(daytrade=True, date="2016-06-01") == pytest.approx(m.round_trip_rate(daytrade=False))
    early = m.sell_tax_rates(
        (3,),
        daytrade=True,
        dates=np.array(["2016-06-01", "2017-04-28", "NaT"], dtype="datetime64[ns]"),
    )
    np.testing.assert_allclose(early, [0.003, 0.0015, 0.0015])


def test_order_cost_and_min_fee() -> None:
    no_cap = _model(commission_discount=0.6)
    assert no_cap.order_cost(10_000, "buy", True, False) == pytest.approx(8.55)
    assert no_cap.order_cost(10_000, "sell", True, False) == pytest.approx(8.55 + 15.0)
    assert no_cap.order_cost(-10_000, "sell", False, False) == pytest.approx(8.55 + 30.0)
    cap = _model(commission_discount=0.6, capital_ntd=1_000_000)
    assert cap.order_cost(10_000, "buy", True, False) == pytest.approx(20.0)
    assert cap.order_cost(10_000, "sell", False, False) == pytest.approx(20.0 + 30.0)
    assert cap.order_cost(10_000, "sell", True, True) == pytest.approx(20.0 + 10.0)
    assert cap.order_cost(1_000_000, "buy", True, False) == pytest.approx(855.0)
    assert cap.order_cost(0.0, "buy", True, False) == 0.0
    with pytest.raises(ValueError):
        cap.order_cost(100.0, "hold", True, False)
    frac = cap.trade_cost_fraction(np.array([0.0, 0.01, 1.0]), "buy", daytrade=True)
    np.testing.assert_allclose(frac, [0.0, 20.0 / 1e6, 0.000855])


# ---------------------------------------------------------------------------
# 權重和回測
# ---------------------------------------------------------------------------


def test_make_weights_modes() -> None:
    pred = _frame([(D1, s, v) for s, v in zip(["1101", "1102", "1103", "1104", "1105"], [5.0, 4.0, 3.0, 2.0, 1.0])], "score")
    hh = backtest.make_weights(pred, "half_half")
    assert list(hh.columns) == ["date", "stock_id", "weight"]
    np.testing.assert_allclose(hh["weight"], [0.2, 0.2, 0.0, -0.2, -0.2])
    np.testing.assert_allclose(backtest.make_weights(pred, "top_bottom_k", k=1)["weight"], [0.5, 0, 0, 0, -0.5])
    np.testing.assert_allclose(backtest.make_weights(pred, "top_bottom_k", k=10)["weight"], [0.25, 0.25, 0, -0.25, -0.25])
    np.testing.assert_allclose(backtest.make_weights(pred, "long_top_k", k=2)["weight"], [0.5, 0.5, 0, 0, 0])
    # 同分照代號，NaN 分數權重 0 也不算進 N
    tied = _frame([(D1, "2002", 1.0), (D1, "2001", 1.0), (D1, "2003", float("nan")), (D1, "2004", 0.0)], "score")
    w = backtest.make_weights(tied, "half_half").set_index("stock_id")["weight"]
    assert w["2001"] == pytest.approx(1 / 3) and w["2002"] == 0.0
    assert w["2003"] == 0.0 and w["2004"] == pytest.approx(-1 / 3)
    with pytest.raises(ValueError):
        backtest.make_weights(pred, "top_bottom_k")
    with pytest.raises(ValueError):
        backtest.make_weights(pred, "sideways")
    with pytest.raises(ValueError):
        backtest.make_weights(pd.concat([pred, pred]), "half_half")


def test_run_backtest_gross_cost_and_executable() -> None:
    m = _model(commission_discount=0.6)
    rt = m.round_trip_rate(daytrade=True)
    bt = backtest.run_backtest(WEIGHTS, LABELS, m)
    assert list(bt.columns) == list(backtest.BACKTEST_COLUMNS)
    assert bt.index.name == "date"
    assert list(bt.index) == [pd.Timestamp(D1), pd.Timestamp(D2)]
    np.testing.assert_allclose(bt["gross"], [0.25 * (0.02 - 0.01 - 0.03 + 0.04), 0.5 * 0.01 - 0.5 * 0.02], atol=1e-15)
    np.testing.assert_allclose(bt["cost"], [rt, rt], atol=1e-15)
    np.testing.assert_allclose(bt["net"], bt["gross"] - bt["cost"], atol=1e-15)
    np.testing.assert_allclose(bt["exposure"], [1.0, 1.0])
    np.testing.assert_allclose(bt["turnover"], [2.0, 2.0])
    assert bt["n_long"].tolist() == [2, 1] and bt["n_short"].tolist() == [2, 1]

    ex = backtest.run_backtest(WEIGHTS, LABELS, m, executable=True)
    # 第一天 1101 做多買不到；1103 是空單，exec_long_ok=0 不影響。第二天 1102 做空空不到。
    np.testing.assert_allclose(ex["gross"], [0.25 * (-0.01 - 0.03 + 0.04), 0.5 * 0.01], atol=1e-15)
    np.testing.assert_allclose(ex["cost"], [0.75 * rt, 0.5 * rt], atol=1e-15)
    assert ex["n_long"].tolist() == [1, 1] and ex["n_short"].tolist() == [2, 0]
    with pytest.raises(ValueError):
        backtest.run_backtest(WEIGHTS, LABELS.drop(columns=["exec_long_ok"]), m, executable=True)


def test_run_backtest_etf_tax_and_min_fee() -> None:
    m = _model(commission_discount=0.6)
    labels = LABELS.assign(is_etf=[1, 0, 0, 0, 0, 0, 0, 0])
    bt = backtest.run_backtest(WEIGHTS, labels, m)
    expected_d1 = 1.0 * 2 * 0.000855 + 0.75 * 0.0015 + 0.25 * 0.001
    assert bt["cost"].iloc[0] == pytest.approx(expected_d1, abs=1e-15)

    # 本金 100 萬、50 檔各 2%：每筆 2 萬，手續費 17.1 元，最低 20 元有作用
    ids = [f"{1101 + j}" for j in range(50)]
    w = pd.DataFrame({"date": pd.Timestamp(D1), "stock_id": ids, "weight": [0.02] * 25 + [-0.02] * 25})
    lab = pd.DataFrame({"date": pd.Timestamp(D1), "stock_id": ids, "label_r": 0.0})
    no_cap = backtest.run_backtest(w, lab, m)
    assert no_cap["cost"].iloc[0] == pytest.approx(m.round_trip_rate(), abs=1e-15)
    cap = backtest.run_backtest(w, lab, _model(commission_discount=0.6, capital_ntd=1_000_000))
    per_stock = (20.0 + 20.0 + 20_000 * 0.0015) / 1e6
    assert cap["cost"].iloc[0] == pytest.approx(50 * per_stock, abs=1e-15)


def test_run_backtest_hold_turnover() -> None:
    m = _model(commission_discount=1.0)
    comm = 0.001425
    bt = backtest.run_backtest(WEIGHTS, LABELS, m, holding="hold_h")
    # 第一天從 0 建倉：買 1101、1102 各 0.25，空 1103、1104 各 0.25（做空開倉是賣出）
    # 第二天：1101 +0.25、1102 −0.75、1103 +0.25、1104 +0.25（前一天有、今天沒有的回補）
    np.testing.assert_allclose(bt["turnover"], [1.0, 1.5])
    np.testing.assert_allclose(bt["cost"], [1.0 * comm + 0.5 * 0.003, 1.5 * comm + 0.75 * 0.003], atol=1e-15)
    np.testing.assert_allclose(bt["gross"], [0.005, -0.005], atol=1e-15)
    np.testing.assert_allclose(bt["exposure"], [1.0, 1.0])
    assert bt["n_long"].tolist() == [2, 1] and bt["n_short"].tolist() == [2, 1]
    with pytest.raises(ValueError):
        backtest.run_backtest(WEIGHTS, LABELS, m, holding="overnight")


def test_run_backtest_missing_label_warns() -> None:
    m = _model()
    extra = pd.concat([WEIGHTS, _frame([(D2, "9999", 0.1)], "weight")], ignore_index=True)
    with pytest.warns(RuntimeWarning):
        bt = backtest.run_backtest(extra, LABELS, m)
    base = backtest.run_backtest(WEIGHTS, LABELS, m)
    np.testing.assert_allclose(bt["gross"], base["gross"], atol=1e-15)
    np.testing.assert_allclose(bt["cost"], base["cost"], atol=1e-15)


def _random_market(n_days: int = 30, n_stocks: int = 50, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-07-01", periods=n_days)
    ids = [f"{2000 + j}" for j in range(n_stocks)]
    idx = pd.MultiIndex.from_product([dates, ids], names=["date", "stock_id"]).to_frame(index=False)
    r = rng.normal(0.0, 0.02, len(idx))
    idx["label_r"] = r
    idx["exec_long_ok"] = (rng.random(len(idx)) > 0.03).astype(np.int8)
    idx["exec_short_ok"] = (rng.random(len(idx)) > 0.03).astype(np.int8)
    pred = idx.loc[:, ["date", "stock_id"]].copy()
    pred["score"] = 0.3 * r + rng.normal(0.0, 0.02, len(idx))
    return pred, idx


def test_competition_score_matches_half_half_gross() -> None:
    pred = _frame([(D1, "1101", 3.0), (D1, "1102", 2.0), (D1, "1103", 1.0), (D1, "1104", 0.0)], "score")
    s = backtest.competition_score(pred, LABELS)
    assert s.name == "competition_score" and s.index.name == "date"
    assert s.iloc[0] == pytest.approx((0.02 - 0.01 - 0.03 + 0.04) / 4)
    # 只用指定的股票（例如比賽的 50 檔）：在它們之間重新排名。1101 猜漲、1104 猜跌
    s2 = backtest.competition_score(pred, LABELS, stock_ids=["1104", "1101"])
    assert s2.iloc[0] == pytest.approx((0.02 + 0.04) / 2)

    pred, labels = _random_market()
    comp = backtest.competition_score(pred, labels)
    bt = backtest.run_backtest(backtest.make_weights(pred, "half_half"), labels, _model())
    np.testing.assert_allclose(comp.to_numpy(), bt["gross"].to_numpy(), atol=1e-15)


def test_break_even_cost_uses_exposure() -> None:
    pred, labels = _random_market(seed=1)
    m = _model()
    bt = backtest.run_backtest(backtest.make_weights(pred, "top_bottom_k", k=5), labels, m)
    c = backtest.break_even_cost(bt["gross"], bt["exposure"])
    assert c == pytest.approx(bt["gross"].sum() / bt["exposure"].sum())
    assert (bt["gross"] - c * bt["exposure"]).mean() == pytest.approx(0.0, abs=1e-15)
    # 淨報酬 = 毛報酬 − 來回成本率 × 部位
    assert bt["net"].mean() == pytest.approx(bt["gross"].mean() - m.round_trip_rate() * bt["exposure"].mean(), abs=1e-15)
    assert backtest.break_even_cost(np.array([0.01, 0.03]), 1.0) == pytest.approx(0.02)
    assert math.isnan(backtest.break_even_cost(np.array([0.01]), 0.0))


def test_backtest_report_is_json_ready() -> None:
    pred, labels = _random_market(seed=2)
    report = backtest.backtest_report(pred, labels, _model())
    text = json.dumps(report)
    assert "rank_ic" in json.loads(text)
    assert report["n_days"] == 30 and report["n_rows"] == 1500 and report["k"] == 5
    assert set(report["modes"]) == {"half_half", "top_bottom_k", "long_top_k"}
    hh = report["modes"]["half_half"]
    assert set(hh["net_sharpe_by_discount"]) == {"1", "0.6", "0.28"}
    assert "net_executable" in hh
    assert hh["mean_exposure"] == pytest.approx(1.0)
    assert hh["mean_turnover"] == pytest.approx(2.0)
    assert report["rank_ic"]["mean"] > 0
    assert report["cost"]["round_trip_rate_by_discount"]["0.28"] == pytest.approx(0.002298, abs=1e-12)
    assert isinstance(report["n_days"], int) and isinstance(report["ic"]["n_days"], int)
    assert report["horizon"] == 1 and report["holding"] == "intraday"
    assert report["competition_scope"] == "universe" and report["competition_n_stocks"] is None

    ids = sorted(labels["stock_id"].astype(str).unique().tolist())[:10]
    rep2 = backtest.backtest_report(pred, labels, _model(), competition_stocks=ids)
    assert rep2["competition_scope"] == "stock_ids" and rep2["competition_n_stocks"] == 10
    expected = backtest.competition_score(pred, labels, stock_ids=ids).mean()
    assert rep2["competition"]["mean"] == pytest.approx(expected)
    assert rep2["rank_ic"]["mean"] == pytest.approx(report["rank_ic"]["mean"])


def test_backtest_report_horizon_2_rebalances_every_2_days() -> None:
    pred, labels = _random_market(seed=3)
    m = _model()
    report = backtest.backtest_report(pred, labels, m, horizon=2)
    json.dumps(report)
    assert report["horizon"] == 2 and report["holding"] == "hold_h"
    assert report["competition"] is None
    assert report["n_days"] == 30 and report["n_rebalance_days"] == 15
    assert report["periods_per_year"] == pytest.approx(126.0)
    hh = report["modes"]["half_half"]
    assert hh["gross"]["n_days"] == 15
    assert hh["break_even_cost"] is None
    assert math.isfinite(hh["break_even_cost_per_turnover"])
    # 和直接拿每 2 天的權重跑 hold_h 一樣
    days = pd.DatetimeIndex(np.unique(pred["date"].to_numpy()))[::2]
    sub = pred.loc[pred["date"].isin(days)]
    bt = backtest.run_backtest(backtest.make_weights(sub, "half_half"), labels, m, holding="hold_h")
    assert len(bt) == 15
    assert hh["gross"]["mean"] == pytest.approx(bt["gross"].mean())
    assert hh["net"]["mean"] == pytest.approx(bt["net"].mean())
    assert hh["mean_turnover"] == pytest.approx(bt["turnover"].mean())
    with pytest.raises(ValueError):
        backtest.backtest_report(pred, labels, m, horizon=0)
