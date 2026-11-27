"""`twfm.eval.metrics` 的測試：Sharpe、最大回撤、Newey-West 標準誤、每天 IC、摘要的鍵，
以及 `twfm.eval` 三個模組 import 時都不載入 torch。"""

from __future__ import annotations

import math
import os
import statistics
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

import twfm.eval.metrics as metrics


# ---------------------------------------------------------------------------
# Sharpe
# ---------------------------------------------------------------------------


def test_sharpe_constant_series_is_nan() -> None:
    # 每個值都一樣就回傳 NaN（用 ptp == 0 判斷）。0.1 + 0.1 + 0.1 != 0.3，
    # 三個 0.1 的平均不精確，std 可能不是 0，用 std == 0 判斷的話會擋不住
    assert math.isnan(metrics.sharpe_ratio(pd.Series([0.1, 0.1, 0.1])))
    assert math.isnan(metrics.sharpe_ratio(pd.Series([0.1] * 250)))
    assert math.isnan(metrics.sharpe_ratio(pd.Series([0.0] * 10)))
    assert math.isnan(metrics.sharpe_ratio(pd.Series([0.01])))
    assert math.isnan(metrics.summarize_daily(pd.Series([0.1] * 250))["sharpe"])
    assert math.isnan(metrics.summarize_daily(pd.Series([0.1] * 250))["t_nw"])


def test_sharpe_known_series() -> None:
    x = [0.01, -0.02, 0.03, 0.0]
    expected = statistics.mean(x) / statistics.stdev(x) * math.sqrt(252)
    assert metrics.sharpe_ratio(pd.Series(x)) == pytest.approx(expected, rel=1e-12)
    assert metrics.sharpe_ratio(np.array(x), periods_per_year=1) == pytest.approx(expected / math.sqrt(252), rel=1e-12)
    with_nan = pd.Series([0.01, float("nan"), -0.02, 0.03, float("inf"), 0.0])
    assert metrics.sharpe_ratio(with_nan) == pytest.approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------
# 最大回撤
# ---------------------------------------------------------------------------


def test_max_drawdown_known_series() -> None:
    # 淨值 1.1 → 0.55 → 0.66，從 1.1 跌到 0.55 是 −50%
    assert metrics.max_drawdown(pd.Series([0.1, -0.5, 0.2])) == pytest.approx(-0.5)
    # 起點淨值 1 也算高點：第一天就跌 10%
    assert metrics.max_drawdown(pd.Series([-0.1, 0.05])) == pytest.approx(-0.1)
    # 淨值 1.2 → 0.96 → 1.152 → 0.8064，高點一直是 1.2，最低點 0.8064 是 −32.8%
    assert metrics.max_drawdown(pd.Series([0.2, -0.2, 0.2, -0.3])) == pytest.approx(0.8064 / 1.2 - 1.0)
    # 不複利：累積 0.1, −0.1, −0.2, 0.1，從 0.1 跌到 −0.2
    assert metrics.max_drawdown(pd.Series([0.1, -0.2, -0.1, 0.3]), compound=False) == pytest.approx(-0.3)
    assert metrics.max_drawdown(pd.Series([0.01, 0.02, 0.0])) == 0.0
    assert math.isnan(metrics.max_drawdown(pd.Series([], dtype=float)))


# ---------------------------------------------------------------------------
# Newey-West
# ---------------------------------------------------------------------------


def test_newey_west_lag0_equals_iid() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.01, 0.05, 300)
    iid = statistics.stdev(x.tolist()) / math.sqrt(len(x))
    assert metrics.newey_west_se(x, lags=0) == pytest.approx(iid, rel=1e-10)
    s = metrics.ic_summary(pd.Series(x), lags=0)
    assert s["t_nw"] == pytest.approx(s["t_iid"], rel=1e-10)
    assert s["t_iid"] == pytest.approx(statistics.mean(x.tolist()) / iid, rel=1e-10)


def test_newey_west_hand_value_and_autocorrelation() -> None:
    # x = 1..4：γ0 = 1.25，γ1 = 0.3125，L = 1 的權重 0.5；長期變異數 1.5625，乘 4/3，再除以 n
    assert metrics.newey_west_se(np.array([1.0, 2.0, 3.0, 4.0]), lags=1) == pytest.approx(
        math.sqrt(1.5625 * 4.0 / 3.0 / 4.0), rel=1e-12
    )
    # lags 超過 n − 1 時用 n − 1，不出錯
    assert math.isfinite(metrics.newey_west_se(np.array([1.0, 3.0, 2.0]), lags=50))
    assert math.isnan(metrics.newey_west_se(np.array([1.0]), lags=3))
    with pytest.raises(ValueError):
        metrics.newey_west_se(np.array([1.0, 2.0]), lags=-1)
    # 正的自我相關：NW 標準誤明顯大於 iid
    rng = np.random.default_rng(1)
    eps = rng.normal(0.0, 1.0, 3000)
    ar = np.empty_like(eps)
    ar[0] = eps[0]
    for t in range(1, len(eps)):
        ar[t] = 0.6 * ar[t - 1] + eps[t]
    assert metrics.newey_west_se(ar, lags=10) > 1.3 * metrics.newey_west_se(ar, lags=0)


# ---------------------------------------------------------------------------
# 每天 IC 和摘要
# ---------------------------------------------------------------------------


def _ic_frame() -> pd.DataFrame:
    rows: list[tuple[str, str, float, float]] = []
    ids = ["1101", "1102", "1103", "1104", "1105"]
    for sid, s, r in zip(ids, [1, 2, 3, 4, 5], [0.01, 0.02, 0.05, 0.06, 0.09]):
        rows.append(("2025-07-01", sid, float(s), r))  # 完全同向
    for sid, s, r in zip(ids, [1, 2, 3, 4, 5], [0.09, 0.06, 0.05, 0.02, 0.01]):
        rows.append(("2025-07-02", sid, float(s), r))  # 完全反向
    for sid, s, r in zip(ids[:2], [1, 2], [0.01, 0.02]):
        rows.append(("2025-07-03", sid, float(s), r))  # 只有 2 檔，不算
    for sid, r in zip(ids, [0.01, -0.02, 0.05, 0.0, 0.03]):
        rows.append(("2025-07-04", sid, 7.0, r))  # 分數全部一樣，IC 記 0
    rows.append(("2025-07-04", "1106", float("nan"), 0.5))  # NaN 分數丟掉
    return pd.DataFrame(rows, columns=["date", "stock_id", "score", "label_r"])


def test_daily_ic_rules() -> None:
    df = _ic_frame()
    ric = metrics.daily_ic(df)
    assert ric.index.name == "date"
    assert list(ric.index) == [pd.Timestamp("2025-07-01"), pd.Timestamp("2025-07-02"), pd.Timestamp("2025-07-04")]
    np.testing.assert_allclose(ric.to_numpy(), [1.0, -1.0, 0.0], atol=1e-12)
    ic = metrics.daily_ic(df, method="pearson")
    day1 = df[df["date"] == "2025-07-01"]
    expected = np.corrcoef(day1["score"], day1["label_r"])[0, 1]
    assert ic.iloc[0] == pytest.approx(expected, rel=1e-12)
    with pytest.raises(ValueError):
        metrics.daily_ic(df, method="kendall")


def test_daily_ic_spearman_with_ties_matches_pandas() -> None:
    rng = np.random.default_rng(3)
    n = 40
    score = np.round(rng.normal(size=n), 1)  # 故意有同分
    ret = rng.normal(size=n)
    df = pd.DataFrame({"date": pd.Timestamp("2025-07-01"), "stock_id": [str(1000 + j) for j in range(n)], "score": score, "label_r": ret})
    expected = pd.Series(score).corr(pd.Series(ret), method="spearman")
    assert metrics.daily_ic(df).iloc[0] == pytest.approx(expected, rel=1e-10)


def test_ic_summary_known_values_and_keys() -> None:
    ic = pd.Series([0.1, 0.2, -0.1, 0.0])
    s = metrics.ic_summary(ic, lags=2)
    assert tuple(s) == ("mean", "std", "icir", "t_iid", "t_nw", "n_days", "hit_rate")
    sd = statistics.stdev([0.1, 0.2, -0.1, 0.0])
    assert s["mean"] == pytest.approx(0.05)
    assert s["std"] == pytest.approx(sd)
    assert s["icir"] == pytest.approx(0.05 / sd)
    assert s["t_iid"] == pytest.approx(0.05 / (sd / 2.0))
    assert s["t_nw"] == pytest.approx(0.05 / metrics.newey_west_se(ic.to_numpy(), lags=2))
    assert s["n_days"] == 4 and isinstance(s["n_days"], int)
    assert s["hit_rate"] == pytest.approx(0.5)
    empty = metrics.ic_summary(pd.Series([], dtype=float))
    assert empty["n_days"] == 0 and math.isnan(empty["mean"])


def test_summarize_daily_keys_and_values() -> None:
    x = pd.Series([0.01, -0.02, 0.03, 0.0, 0.02])
    s = metrics.summarize_daily(x)
    assert tuple(s) == ("mean", "std", "sharpe", "mdd", "t_nw", "n_days", "win_rate")
    assert s["mean"] == pytest.approx(statistics.mean(x.tolist()))
    assert s["std"] == pytest.approx(statistics.stdev(x.tolist()))
    assert s["sharpe"] == pytest.approx(metrics.sharpe_ratio(x))
    assert s["mdd"] == pytest.approx(metrics.max_drawdown(x))
    assert s["n_days"] == 5 and isinstance(s["n_days"], int)
    assert s["win_rate"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 不載入 torch
# ---------------------------------------------------------------------------


def test_eval_modules_do_not_import_torch() -> None:
    """SPEC：`twfm.eval.costs`、`twfm.eval.metrics` 只用 numpy、pandas、scipy；`backtest` 也一樣。"""
    package = metrics.__name__.rsplit(".", 1)[0]
    names = [f"{package}.metrics", f"{package}.costs", f"{package}.backtest", package]
    code = (
        "import importlib, sys\n"
        f"for name in {names!r}:\n"
        "    importlib.import_module(name)\n"
        "print('torch' in sys.modules)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.getcwd(),
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "False"
