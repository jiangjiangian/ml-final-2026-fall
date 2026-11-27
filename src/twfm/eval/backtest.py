"""回測（不 import torch）：權重、扣成本的每天損益、比賽分數、損益兩平成本、總報告。

輸入都是 long 格式的 DataFrame，鍵是 `date, stock_id`（`date` 會轉成 `datetime64[ns]`，
`stock_id` 轉成 `str`，同一個 `(date, stock_id)` 出現兩次丟 `ValueError`）：
- `pred`：`date, stock_id, score`（`Trainer.predict` 的輸出，多的欄會被忽略）。
- `weights`：`date, stock_id, weight`（`make_weights` 的輸出）。
- `labels`：`date, stock_id, label_r`，加上可選的 `exec_long_ok, exec_short_ok, is_etf`
  （`SampleIndex.to_frame()` 可以直接用；沒有 `is_etf` 就當作都不是 ETF）。

`run_backtest` 回傳以 `date` 為索引（不是欄）的 DataFrame，欄是
`gross, cost, net, turnover, exposure, n_long, n_short`：
- `exposure`：當天實際持有的部位 Σ|w|（本金的比例）。
- `turnover`：當天的成交金額（買加賣）÷ 本金。當沖開盤進、收盤出，所以是 2 × exposure；
  `hold_h` 是 Σ|w_t − w_{t−1}|。
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd

from .costs import TaiwanCostModel
from .metrics import (
    _date_series,
    _finite_1d,
    _float_values,
    daily_ic,
    ic_summary,
    sharpe_ratio,
    summarize_daily,
)

WEIGHT_MODES: tuple[str, ...] = ("half_half", "top_bottom_k", "long_top_k")
HOLDINGS: tuple[str, ...] = ("intraday", "hold_h")
BACKTEST_COLUMNS: tuple[str, ...] = ("gross", "cost", "net", "turnover", "exposure", "n_long", "n_short")
LABEL_OPTIONAL_COLS: tuple[str, ...] = ("exec_long_ok", "exec_short_ok", "is_etf")
_KEYS: list[str] = ["date", "stock_id"]
_NAN = float("nan")


# ---------------------------------------------------------------------------
# 輸入整理
# ---------------------------------------------------------------------------


def _prepare(
    df: pd.DataFrame,
    name: str,
    float_cols: Sequence[str],
    optional_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """整理成新的 DataFrame：`date`（ns）、`stock_id`（str）、數值欄（float64），RangeIndex。

    `date`、`stock_id` 在索引裡也可以。可選欄有才帶上。bool、0/1 的欄也轉成 float64，
    這樣 left merge 之後缺的列是 NaN，不會變成 object 型別。
    """
    frame = df
    index_names = [n for n in (frame.index.names or []) if n is not None]
    to_reset = [c for c in _KEYS if c not in frame.columns and c in index_names]
    if to_reset:
        frame = frame.reset_index(level=to_reset)
    missing = [c for c in (*_KEYS, *float_cols) if c not in frame.columns]
    if missing:
        raise ValueError(f"{name} 缺欄：{missing}")
    data: dict[str, Any] = {
        "date": _date_series(frame["date"]).to_numpy(dtype="datetime64[ns]"),
        "stock_id": frame["stock_id"].astype(str).to_numpy(dtype=object),
    }
    for col in float_cols:
        data[col] = _float_values(frame[col])
    for col in optional_cols:
        if col in frame.columns:
            data[col] = _float_values(frame[col])
    out = pd.DataFrame(data)
    if out["date"].isna().any():
        raise ValueError(f"{name} 的 date 有缺值")
    dup = out.duplicated(_KEYS)
    if dup.any():
        first = out.loc[dup, _KEYS].iloc[0]
        raise ValueError(f"{name} 有重複的 (date, stock_id)，例如 {first['date'].date()} {first['stock_id']}")
    return out


def _flag(frame: pd.DataFrame, col: str) -> npt.NDArray[np.bool_]:
    """0/1 欄轉成 bool。沒有這欄或缺值都當 False。"""
    if col not in frame.columns:
        return np.zeros(len(frame), dtype=bool)
    v = frame[col].to_numpy(dtype=np.float64)
    return np.nan_to_num(v, nan=0.0) > 0.5


def _empty_backtest() -> pd.DataFrame:
    index = pd.DatetimeIndex(np.zeros(0, dtype="datetime64[ns]"), name="date")
    out = pd.DataFrame({c: np.zeros(0, dtype=np.float64) for c in BACKTEST_COLUMNS}, index=index)
    out["n_long"] = out["n_long"].astype(np.int64)
    out["n_short"] = out["n_short"].astype(np.int64)
    return out


def _finish(
    dates: npt.NDArray[np.datetime64],
    gross: npt.NDArray[np.float64],
    cost: npt.NDArray[np.float64],
    turnover: npt.NDArray[np.float64],
    exposure: npt.NDArray[np.float64],
    n_long: npt.NDArray[np.int64],
    n_short: npt.NDArray[np.int64],
) -> pd.DataFrame:
    index = pd.DatetimeIndex(np.asarray(dates, dtype="datetime64[ns]"), name="date")
    out = pd.DataFrame(
        {
            "gross": np.asarray(gross, dtype=np.float64),
            "cost": np.asarray(cost, dtype=np.float64),
            "net": np.asarray(gross, dtype=np.float64) - np.asarray(cost, dtype=np.float64),
            "turnover": np.asarray(turnover, dtype=np.float64),
            "exposure": np.asarray(exposure, dtype=np.float64),
            "n_long": np.asarray(n_long, dtype=np.int64),
            "n_short": np.asarray(n_short, dtype=np.int64),
        },
        index=index,
    )
    return out.loc[:, list(BACKTEST_COLUMNS)]


# ---------------------------------------------------------------------------
# 權重
# ---------------------------------------------------------------------------


def _rank_weights(pos: npt.NDArray[np.int64], n: npt.NDArray[np.int64], mode: str, k: int | None) -> npt.NDArray[np.float64]:
    """依名次算權重。`pos` 是當天名次（1 是分數最高），`n` 是當天檔數。"""
    w = np.zeros(pos.shape, dtype=np.float64)
    if mode == "half_half":
        m = n // 2
        long = pos <= m
        short = pos > n - m
        w[long] = 1.0 / n[long]
        w[short] = -1.0 / n[short]
        return w
    assert k is not None
    if mode == "top_bottom_k":
        ke = np.minimum(int(k), n // 2)
        long = (ke > 0) & (pos <= ke)
        short = (ke > 0) & (pos > n - ke)
        w[long] = 1.0 / (2.0 * ke[long])
        w[short] = -1.0 / (2.0 * ke[short])
        return w
    ke = np.minimum(int(k), n)
    long = (ke > 0) & (pos <= ke)
    w[long] = 1.0 / ke[long]
    return w


def make_weights(pred: pd.DataFrame, mode: str = "half_half", k: int | None = None) -> pd.DataFrame:
    """把每天的分數變成權重。回傳 `date, stock_id, weight`，按 `date, stock_id` 排序。

    名次：每天分數由高到低排，同分時代號小的排前面（結果固定）。N 是當天分數有效的檔數。
    - `half_half`：前 ⌊N/2⌋ 名 +1/N，後 ⌊N/2⌋ 名 −1/N，N 是奇數時中間那檔 0。
      比賽每天 50 檔、25 猜漲 25 猜跌就是這個，Σ w·r 等於比賽分數。
    - `top_bottom_k`：前 k 名 +1/(2k)，後 k 名 −1/(2k)。當天不到 2k 檔時 k 改成 ⌊N/2⌋。
    - `long_top_k`：前 k 名 +1/k。當天不到 k 檔時 k 改成 N。

    分數是 NaN、inf 的列保留在輸出裡，權重 0，也不算進 N。
    """
    if mode not in WEIGHT_MODES:
        raise ValueError(f"mode 要是 {WEIGHT_MODES} 之一，拿到 {mode!r}")
    if mode != "half_half":
        if k is None or int(k) < 1:
            raise ValueError(f"mode={mode!r} 要給 k ≥ 1，拿到 {k!r}")
        k = int(k)
    frame = _prepare(pred, "pred", ("score",))
    frame = frame.sort_values(_KEYS, kind="mergesort").reset_index(drop=True)
    weight = np.zeros(len(frame), dtype=np.float64)
    valid = np.isfinite(frame["score"].to_numpy())
    if valid.any():
        sub = frame.loc[valid, ["date", "stock_id", "score"]]
        order = sub.sort_values(["date", "score", "stock_id"], ascending=[True, False, True], kind="mergesort")
        grouped = order.groupby("date", sort=False)
        pos = grouped.cumcount().to_numpy(dtype=np.int64) + 1
        n = grouped["score"].transform("count").to_numpy(dtype=np.int64)
        weight[order.index.to_numpy()] = _rank_weights(pos, n, mode, k)
    out = frame.loc[:, _KEYS].copy()
    out["weight"] = weight
    return out


# ---------------------------------------------------------------------------
# 回測
# ---------------------------------------------------------------------------


def run_backtest(
    weights: pd.DataFrame,
    labels: pd.DataFrame,
    cost_model: TaiwanCostModel,
    holding: str = "intraday",
    executable: bool = False,
) -> pd.DataFrame:
    """每天扣成本的損益。回傳以 `date` 為索引的 DataFrame（欄見模組說明），只含 `weights` 有的日期。

    `holding="intraday"`（預設，配 `horizon=1`）：每天開盤建倉、收盤平倉，是當沖。
    - `gross = Σ w · label_r`。
    - `cost = Σ |w| × round_trip_rate(daytrade=True)`：一買一賣的手續費加一次當沖稅（ETF 用 ETF 稅率）。
      當沖減半稅率照每列的日期判斷（2017-04-28 到 2027-12-31 用減半稅率，其他日期用一般稅率）。
      `capital_ntd` 有給時，每邊的手續費至少 NT$20（按 |w| × 本金算每筆金額）。
    - 賣出金額用開盤的部位近似，忽略當天漲跌對賣出金額（和稅）的影響。

    `holding="hold_h"`：部位一直拿著，只在 `weights` 的日期調整。
    - 每個日期的 `gross = Σ w · label_r`，`label_r` 要涵蓋到下一個調整日（例如 `horizon=h` 時每 h 個交易日給一次權重）。
      權重日期重疊的話報酬會重複算。調整日之間的隔夜跳空不算。
    - 換手 Δ = w_t − w_{t−1}（第一天從 0 開始，前一天有、今天沒有的股票算賣光）。
      `turnover = Σ|Δ|`，`cost = Σ|Δ| × (手續費 + 滑價) + Σ max(−Δ, 0) × 一般證交稅`（不是當沖；
      做空開倉也是賣出，一樣收稅）。最後一天不算平倉成本。融券費用沒有算。

    `executable=True`（`labels` 要有 `exec_long_ok`、`exec_short_ok`）：做多但 `exec_long_ok=0`
    （開盤漲停買不到）、做空但 `exec_short_ok=0`（開盤跌停空不到）的那一格，當天報酬和成本都算 0，
    也不算進 `exposure`、`n_long`、`n_short`。`hold_h` 也是逐格照這條，不追蹤沒成交造成的部位差異。
    遮罩只看進場那一腳。收盤鎖在跌停的多單、收盤鎖在漲停的空單，實際上常常平不了倉，
    這裡照樣當作在收盤平倉，所以 `executable=True` 的淨報酬在漲跌停的日子偏樂觀。

    `weights` 有權重但 `labels` 沒有報酬（缺列或 NaN）的格子：報酬算 0 並發 `RuntimeWarning`；
    `intraday` 那格也不收成本（沒有成交），`hold_h` 照換手收成本。
    """
    if holding not in HOLDINGS:
        raise ValueError(f"holding 要是 {HOLDINGS} 之一，拿到 {holding!r}")
    w = _prepare(weights, "weights", ("weight",))
    w["weight"] = np.where(np.isfinite(w["weight"].to_numpy()), w["weight"].to_numpy(), 0.0)
    lab = _prepare(labels, "labels", ("label_r",), LABEL_OPTIONAL_COLS)
    if executable:
        missing = [c for c in ("exec_long_ok", "exec_short_ok") if c not in lab.columns]
        if missing:
            raise ValueError(f"executable=True 時 labels 要有 {missing}")
    if len(w) == 0:
        return _empty_backtest()
    if holding == "intraday":
        return _run_intraday(w, lab, cost_model, executable)
    return _run_hold(w, lab, cost_model, executable)


def _run_intraday(w: pd.DataFrame, lab: pd.DataFrame, cost_model: TaiwanCostModel, executable: bool) -> pd.DataFrame:
    m = w.merge(lab, on=_KEYS, how="left", validate="one_to_one", sort=False)
    wt = m["weight"].to_numpy(dtype=np.float64)
    r = m["label_r"].to_numpy(dtype=np.float64)
    has_label = np.isfinite(r)
    no_label = (wt != 0.0) & ~has_label
    if no_label.any():
        warnings.warn(
            f"run_backtest：{int(no_label.sum())} 個有權重的格子沒有報酬，報酬和成本都算 0",
            RuntimeWarning,
            stacklevel=3,
        )
    active = (wt != 0.0) & has_label
    if executable:
        blocked = ((wt > 0.0) & ~_flag(m, "exec_long_ok")) | ((wt < 0.0) & ~_flag(m, "exec_short_ok"))
        active &= ~blocked
    w_eff = np.where(active, wt, 0.0)
    size = np.abs(w_eff)
    gross_i = w_eff * np.where(active, r, 0.0)
    etf = _flag(m, "is_etf")
    dates = m["date"].to_numpy(dtype="datetime64[ns]")
    cost_i = cost_model.trade_cost_fraction(size, "buy", daytrade=True, is_etf=etf, dates=dates)
    cost_i = cost_i + cost_model.trade_cost_fraction(size, "sell", daytrade=True, is_etf=etf, dates=dates)
    per = pd.DataFrame(
        {
            "date": dates,
            "gross": gross_i,
            "cost": cost_i,
            "exposure": size,
            "n_long": (w_eff > 0.0).astype(np.int64),
            "n_short": (w_eff < 0.0).astype(np.int64),
        }
    )
    daily = per.groupby("date", sort=True)[["gross", "cost", "exposure", "n_long", "n_short"]].sum()
    exposure = daily["exposure"].to_numpy(dtype=np.float64)
    return _finish(
        dates=daily.index.to_numpy(dtype="datetime64[ns]"),
        gross=daily["gross"].to_numpy(dtype=np.float64),
        cost=daily["cost"].to_numpy(dtype=np.float64),
        turnover=2.0 * exposure,
        exposure=exposure,
        n_long=daily["n_long"].to_numpy(dtype=np.int64),
        n_short=daily["n_short"].to_numpy(dtype=np.int64),
    )


def _wide(frame: pd.DataFrame, col: str, dates: pd.DatetimeIndex, stocks: pd.Index) -> npt.NDArray[np.float64]:
    """long 轉成 `[日期, 股票]` 的 float64 矩陣，沒有的格子是 NaN。"""
    if col not in frame.columns or len(frame) == 0:
        return np.full((len(dates), len(stocks)), np.nan, dtype=np.float64)
    table = frame.pivot(index="date", columns="stock_id", values=col)
    table = table.reindex(index=dates, columns=stocks)
    return table.to_numpy(dtype=np.float64, na_value=np.nan)


def _run_hold(w: pd.DataFrame, lab: pd.DataFrame, cost_model: TaiwanCostModel, executable: bool) -> pd.DataFrame:
    dates = pd.DatetimeIndex(w["date"].to_numpy(dtype="datetime64[ns]")).unique().sort_values().rename("date")
    stocks = pd.Index(sorted(set(w["stock_id"].tolist())), name="stock_id")
    W = np.nan_to_num(_wide(w, "weight", dates, stocks), nan=0.0)
    prev = np.vstack([np.zeros((1, W.shape[1]), dtype=np.float64), W[:-1]])
    delta = W - prev

    lab_in = lab.loc[lab["date"].isin(dates) & lab["stock_id"].isin(stocks)]
    R = _wide(lab_in, "label_r", dates, stocks)
    has_label = np.isfinite(R)
    no_label = (W != 0.0) & ~has_label
    if no_label.any():
        warnings.warn(
            f"run_backtest：{int(no_label.sum())} 個有權重的格子沒有報酬，報酬算 0",
            RuntimeWarning,
            stacklevel=3,
        )
    keep = np.ones(W.shape, dtype=bool)
    if executable:
        long_ok = np.nan_to_num(_wide(lab_in, "exec_long_ok", dates, stocks), nan=0.0) > 0.5
        short_ok = np.nan_to_num(_wide(lab_in, "exec_short_ok", dates, stocks), nan=0.0) > 0.5
        keep = ~(((W > 0.0) & ~long_ok) | ((W < 0.0) & ~short_ok))

    if "is_etf" in lab.columns:
        etf_by_stock = (
            lab.loc[lab["stock_id"].isin(stocks)]
            .assign(is_etf=lambda d: np.nan_to_num(d["is_etf"].to_numpy(dtype=np.float64), nan=0.0))
            .groupby("stock_id")["is_etf"]
            .max()
            .reindex(stocks)
            .to_numpy(dtype=np.float64, na_value=0.0)
        )
        etf_vec = np.nan_to_num(etf_by_stock, nan=0.0) > 0.5
    else:
        etf_vec = np.zeros(len(stocks), dtype=bool)
    etf = np.broadcast_to(etf_vec[None, :], W.shape)

    w_eff = np.where(keep, W, 0.0)
    ret = np.where(keep & has_label, R, 0.0)
    buys = np.where(keep, np.maximum(delta, 0.0), 0.0)
    sells = np.where(keep, np.maximum(-delta, 0.0), 0.0)
    cost = cost_model.trade_cost_fraction(buys, "buy", daytrade=False, is_etf=etf)
    cost = cost + cost_model.trade_cost_fraction(sells, "sell", daytrade=False, is_etf=etf)
    return _finish(
        dates=dates.to_numpy(dtype="datetime64[ns]"),
        gross=(w_eff * ret).sum(axis=1),
        cost=cost.sum(axis=1),
        turnover=(buys + sells).sum(axis=1),
        exposure=np.abs(w_eff).sum(axis=1),
        n_long=(w_eff > 0.0).sum(axis=1).astype(np.int64),
        n_short=(w_eff < 0.0).sum(axis=1).astype(np.int64),
    )


# ---------------------------------------------------------------------------
# 比賽分數、損益兩平、報告
# ---------------------------------------------------------------------------


def _merge_pred_labels(pred: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """pred 和 labels 用 `(date, stock_id)` 內部合併，只留分數和報酬都有限的列。"""
    p = _prepare(pred, "pred", ("score",))
    lab = _prepare(labels, "labels", ("label_r",), LABEL_OPTIONAL_COLS)
    m = p.merge(lab, on=_KEYS, how="inner", validate="one_to_one", sort=False)
    ok = np.isfinite(m["score"].to_numpy()) & np.isfinite(m["label_r"].to_numpy())
    m = m.loc[ok].sort_values(_KEYS, kind="mergesort").reset_index(drop=True)
    return m


def competition_score(
    pred: pd.DataFrame,
    labels: pd.DataFrame,
    stock_ids: Sequence[str] | None = None,
) -> pd.Series:
    """比賽分數：每天 `(2p − 1) · r` 的平均，p 是 `half_half` 的猜漲（1）或猜跌（0）。

    只用分數和報酬都有的股票。N 是奇數時中間那檔記 0（比賽每天 50 檔，不會遇到）。
    N 是偶數時等於 `half_half` 權重的 Σ w·r。
    `stock_ids` 有給時（例如比賽的 50 檔），先只留這些股票，再在它們之間排名、分猜漲猜跌，
    這樣才能和 c2v2d 的每天分數直接比。沒給時是 pred 裡全部股票（整個股票池）的分數。
    回傳以 `date` 為索引的 `pd.Series`，名稱 `competition_score`。
    """
    m = _merge_pred_labels(pred, labels)
    if stock_ids is not None:
        keep = sorted({str(s) for s in stock_ids})
        m = m.loc[m["stock_id"].isin(keep)].reset_index(drop=True)
    if len(m) == 0:
        index = pd.DatetimeIndex(np.zeros(0, dtype="datetime64[ns]"), name="date")
        return pd.Series(np.zeros(0, dtype=np.float64), index=index, name="competition_score")
    wts = make_weights(m.loc[:, ["date", "stock_id", "score"]], "half_half")
    both = wts.merge(m.loc[:, ["date", "stock_id", "label_r"]], on=_KEYS, how="inner", validate="one_to_one")
    contrib = np.sign(both["weight"].to_numpy()) * both["label_r"].to_numpy()
    per = pd.DataFrame({"date": both["date"].to_numpy(dtype="datetime64[ns]"), "x": contrib})
    daily = per.groupby("date", sort=True)["x"].mean()
    index = pd.DatetimeIndex(daily.index.to_numpy(dtype="datetime64[ns]"), name="date")
    return pd.Series(daily.to_numpy(dtype=np.float64), index=index, name="competition_score")


def break_even_cost(
    daily_gross: pd.Series | npt.ArrayLike,
    gross_exposure: pd.Series | npt.ArrayLike | float,
) -> float:
    """損益兩平的成本率 c：使 mean(gross − c × exposure) = 0，也就是 c = Σ gross / Σ exposure。

    `gross_exposure` 要傳每天的部位 Σ|w|（`run_backtest` 的 `exposure` 欄）。傳當沖的 `turnover` 會讓 c 少一半。
    c 和 `round_trip_rate` 同單位：當沖來回成本率低於 c 才有正的淨報酬。
    負的 c 代表毛報酬本身就是負的。兩個都是 Series 時按索引對齊；`gross_exposure` 也可以是常數。
    只用兩邊都有限的天，總部位是 0 時回傳 NaN。
    """
    if isinstance(daily_gross, pd.Series) and isinstance(gross_exposure, pd.Series):
        both = pd.concat({"g": daily_gross, "e": gross_exposure}, axis=1, join="inner")
        g = both["g"].to_numpy(dtype=np.float64, na_value=np.nan)
        e = both["e"].to_numpy(dtype=np.float64, na_value=np.nan)
    else:
        if isinstance(daily_gross, pd.Series):
            g = daily_gross.to_numpy(dtype=np.float64, na_value=np.nan)
        else:
            g = np.asarray(daily_gross, dtype=np.float64).reshape(-1)
        if np.ndim(gross_exposure) == 0:
            e = np.full(g.shape, float(gross_exposure), dtype=np.float64)  # type: ignore[arg-type]
        elif isinstance(gross_exposure, pd.Series):
            e = gross_exposure.to_numpy(dtype=np.float64, na_value=np.nan)
        else:
            e = np.asarray(gross_exposure, dtype=np.float64).reshape(-1)
        if g.shape != e.shape:
            raise ValueError(f"daily_gross 和 gross_exposure 長度不同：{g.shape} 和 {e.shape}")
    ok = np.isfinite(g) & np.isfinite(e)
    total_exposure = float(e[ok].sum())
    if not total_exposure > 0.0:
        return _NAN
    return float(g[ok].sum()) / total_exposure


def _discount_key(d: float) -> str:
    return f"{float(d):g}"


def _mean(s: pd.Series) -> float:
    v = _finite_1d(s)
    return float(v.mean()) if v.size else _NAN


def backtest_report(
    pred: pd.DataFrame,
    labels: pd.DataFrame,
    cost_model: TaiwanCostModel,
    discounts: Sequence[float] = (1.0, 0.6, 0.28),
    *,
    modes: Sequence[str] = WEIGHT_MODES,
    k: int | None = None,
    lags: int = 10,
    horizon: int = 1,
    competition_stocks: Sequence[str] | None = None,
) -> dict[str, Any]:
    """一份可以直接 `json.dump` 的評估報告。

    `horizon=1`（預設）：每天開盤進、收盤出的當沖（`holding="intraday"`），Sharpe 用每年 252 期。
    `horizon=h > 1`：`label_r` 是 t 開盤到 t+h−1 收盤的報酬，天和天之間重疊。IC 照樣每天算
    （Newey-West 的 lag 至少 h）；權重只在每 h 個有樣本的交易日調整一次（不重疊），用 `holding="hold_h"`
    （換手收手續費，賣出收一般證交稅，不是當沖），Sharpe 用每年 252 / h 期；`competition` 是 None，
    比賽分數只對 `horizon=1` 有意義。

    內容：
    - `horizon`、`holding`、`periods_per_year`：上面說的設定。
    - `n_rows`、`n_days`、`median_stocks_per_day`：pred 和 labels 對得上的列數、天數、每天檔數中位數。
      `n_rebalance_days`：回測用到的調整日數（`horizon=1` 時等於 `n_days`）。
    - `ic`、`rank_ic`：每天 Pearson、Spearman IC 的 `ic_summary`。
    - `competition`：`competition_score` 的 `summarize_daily`（每天分數）。
      `competition_stocks` 有給時（例如比賽的 50 檔）只用這些股票排名，才能和 c2v2d 的每天分數直接比；
      沒給時是整個股票池的分數，只能和 c2v2d 比方向和穩定度。`competition_scope` 是 `"stock_ids"` 或
      `"universe"`，`competition_n_stocks` 是給的檔數（沒給是 None）。
    - `cost`：`cost_model` 的設定、當沖來回成本率（`round_trip_rate`、各折扣的 `round_trip_rate_by_discount`）
      和一般來回成本率（`round_trip_rate_normal`）。這些是沒給日期的現行稅率；回測本身照每天的日期算稅。
    - `k`：`top_bottom_k`、`long_top_k` 用的 k。沒給時是每天檔數中位數的 10%（四捨五入，至少 1）。
    - `modes[mode]`：每種權重的 `gross`、`net`（用 `cost_model` 本身的折扣）的 `summarize_daily`，
      labels 有 `exec_*` 時再加 `gross_executable`、`net_executable`；`mean_cost`、`mean_exposure`、
      `mean_turnover`；`break_even_cost`（`Σ gross / Σ exposure`，`horizon > 1` 時是 None，改給
      `break_even_cost_per_turnover = Σ gross / Σ turnover`）；各折扣的淨 Sharpe 和淨平均
      （`net_sharpe_by_discount`、`net_mean_by_discount`，鍵是 `"1"`、`"0.6"`、`"0.28"` 這種字串）。
    計數一律是 Python int，NaN 照 `json.dump` 的預設寫成 `NaN`。
    """
    horizon = int(horizon)
    if horizon < 1:
        raise ValueError(f"horizon 至少 1，拿到 {horizon}")
    for mode in modes:
        if mode not in WEIGHT_MODES:
            raise ValueError(f"modes 只能有 {WEIGHT_MODES}，拿到 {mode!r}")
    comp_ids: list[str] | None = None
    if competition_stocks is not None:
        comp_ids = sorted({str(s) for s in competition_stocks})
        if not comp_ids:
            raise ValueError("competition_stocks 是空的")
    m = _merge_pred_labels(pred, labels)
    counts = m.groupby("date", sort=True).size() if len(m) else pd.Series(dtype=np.int64)
    median_n = float(np.median(counts.to_numpy())) if len(counts) else _NAN
    if k is None:
        k_used = max(1, int(round(0.1 * median_n))) if math.isfinite(median_n) else 1
    else:
        k_used = int(k)
        if k_used < 1:
            raise ValueError(f"k 至少 1，拿到 {k}")

    holding = "intraday" if horizon == 1 else "hold_h"
    periods = 252.0 / float(horizon)
    ic_lags = max(int(lags), horizon)
    if horizon == 1:
        m_bt = m
        competition: dict[str, float] | None = summarize_daily(competition_score(m, m, stock_ids=comp_ids), lags=lags)
    else:
        days = pd.DatetimeIndex(np.unique(m["date"].to_numpy(dtype="datetime64[ns]")))
        rebalance = days[::horizon]
        m_bt = m.loc[m["date"].isin(rebalance)].reset_index(drop=True)
        competition = None
    n_rebalance = int(m_bt["date"].nunique()) if len(m_bt) else 0

    cfg = cost_model.cfg
    report: dict[str, Any] = {
        "horizon": horizon,
        "holding": holding,
        "periods_per_year": periods,
        "n_rows": int(len(m)),
        "n_days": int(len(counts)),
        "n_rebalance_days": n_rebalance,
        "median_stocks_per_day": median_n,
        "ic": ic_summary(daily_ic(m, "score", "label_r", method="pearson"), lags=ic_lags),
        "rank_ic": ic_summary(daily_ic(m, "score", "label_r", method="spearman"), lags=ic_lags),
        "competition": competition,
        "competition_scope": "universe" if comp_ids is None else "stock_ids",
        "competition_n_stocks": None if comp_ids is None else int(len(comp_ids)),
        "cost": {
            "commission_rate": float(cfg.commission_rate),
            "commission_discount": float(cfg.commission_discount),
            "daytrade_sell_tax_rate": float(cfg.daytrade_sell_tax_rate),
            "sell_tax_rate": float(cfg.sell_tax_rate),
            "slippage_bps": float(cfg.slippage_bps),
            "capital_ntd": None if cfg.capital_ntd is None else float(cfg.capital_ntd),
            "round_trip_rate": float(cost_model.round_trip_rate(daytrade=True)),
            "round_trip_rate_normal": float(cost_model.round_trip_rate(daytrade=False)),
            "round_trip_rate_by_discount": {
                _discount_key(d): float(cost_model.with_discount(d).round_trip_rate(daytrade=True)) for d in discounts
            },
        },
        "k": int(k_used),
        "modes": {},
    }

    pred_m = m_bt.loc[:, ["date", "stock_id", "score"]]
    label_cols = ["date", "stock_id", "label_r", *[c for c in LABEL_OPTIONAL_COLS if c in m_bt.columns]]
    labels_m = m_bt.loc[:, label_cols]
    has_exec = all(c in m_bt.columns for c in ("exec_long_ok", "exec_short_ok"))
    for mode in modes:
        mode_k = None if mode == "half_half" else k_used
        wts = make_weights(pred_m, mode, mode_k)
        bt = run_backtest(wts, labels_m, cost_model, holding=holding, executable=False)
        entry: dict[str, Any] = {
            "k": None if mode_k is None else int(mode_k),
            "gross": summarize_daily(bt["gross"], periods_per_year=periods, lags=lags),
            "net": summarize_daily(bt["net"], periods_per_year=periods, lags=lags),
            "mean_cost": _mean(bt["cost"]),
            "mean_exposure": _mean(bt["exposure"]),
            "mean_turnover": _mean(bt["turnover"]),
            "break_even_cost": break_even_cost(bt["gross"], bt["exposure"]) if horizon == 1 else None,
        }
        if horizon > 1:
            entry["break_even_cost_per_turnover"] = break_even_cost(bt["gross"], bt["turnover"])
        if has_exec:
            bt_x = run_backtest(wts, labels_m, cost_model, holding=holding, executable=True)
            entry["gross_executable"] = summarize_daily(bt_x["gross"], periods_per_year=periods, lags=lags)
            entry["net_executable"] = summarize_daily(bt_x["net"], periods_per_year=periods, lags=lags)
        sharpe_by: dict[str, float] = {}
        mean_by: dict[str, float] = {}
        for d in discounts:
            bt_d = run_backtest(wts, labels_m, cost_model.with_discount(d), holding=holding, executable=False)
            sharpe_by[_discount_key(d)] = sharpe_ratio(bt_d["net"], periods_per_year=periods)
            mean_by[_discount_key(d)] = _mean(bt_d["net"])
        entry["net_sharpe_by_discount"] = sharpe_by
        entry["net_mean_by_discount"] = mean_by
        report["modes"][mode] = entry
    return report
