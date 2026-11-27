"""評估指標（不 import torch）。

- `daily_ic`：每天分數和報酬的相關係數（預設 Spearman，也就是 RankIC）。
- `newey_west_se`：平均數的 Newey-West 標準誤（Bartlett 權重），處理每天 IC 的自我相關。
- `ic_summary`、`summarize_daily`：把每天的序列整理成一組數字，鍵名固定，其他模組照名字取。
- `sharpe_ratio`、`max_drawdown`：年化 Sharpe 和最大回撤。

共同規則：
- 序列裡的 NaN 和 inf 先丟掉再算。
- 變異數的分母一律用 n − 1（`ddof=1`）。`newey_west_se` 也乘上 n/(n − 1)，
  所以 `lags=0` 時和一般的 iid 標準誤完全一樣，`t_nw` 也等於 `t_iid`。
- 序列完全沒有波動（每個值都一樣）時，比值類的指標回傳 NaN，不回傳浮點誤差造成的天文數字。
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pandas as pd

IC_METHODS: tuple[str, ...] = ("spearman", "pearson")
MIN_STOCKS_PER_DAY: int = 3

IC_SUMMARY_KEYS: tuple[str, ...] = ("mean", "std", "icir", "t_iid", "t_nw", "n_days", "hit_rate")
DAILY_SUMMARY_KEYS: tuple[str, ...] = ("mean", "std", "sharpe", "mdd", "t_nw", "n_days", "win_rate")

_NAN = float("nan")


# ---------------------------------------------------------------------------
# 共用的小工具（backtest.py 也用）
# ---------------------------------------------------------------------------


def _finite_1d(x: npt.ArrayLike | pd.Series | pd.Index) -> npt.NDArray[np.float64]:
    """轉成一維 float64，丟掉 NaN、inf。pandas 的可空型別（`Float64`）的 NA 也當 NaN。"""
    if isinstance(x, (pd.Series, pd.Index)):
        arr = x.to_numpy(dtype=np.float64, na_value=np.nan)
    else:
        arr = np.asarray(x, dtype=np.float64)
    arr = arr.reshape(-1)
    return arr[np.isfinite(arr)]


def _float_values(s: pd.Series) -> npt.NDArray[np.float64]:
    """欄位轉成 float64 陣列。不是數字的值變 NaN，bool 變 0/1。"""
    num = pd.to_numeric(s, errors="coerce")
    return num.to_numpy(dtype=np.float64, na_value=np.nan)


def _date_series(values: pd.Series) -> pd.Series:
    """日期欄轉成無時區的 `datetime64[ns]`。

    pandas 3 從字串建日期可能給 `us` 解析度，不統一的話 merge、pivot 會對不上。
    """
    d = pd.to_datetime(values)
    if isinstance(d.dtype, pd.DatetimeTZDtype):
        raise ValueError("date 不能有時區，請先轉成台北日期再拿掉時區")
    return d.astype("datetime64[ns]")


def _empty_daily_series(name: str) -> pd.Series:
    return pd.Series(
        np.zeros(0, dtype=np.float64),
        index=pd.DatetimeIndex(np.zeros(0, dtype="datetime64[ns]"), name="date"),
        name=name,
    )


def _is_constant(v: npt.NDArray[np.float64]) -> bool:
    """每個值都完全一樣。用 `ptp == 0` 判斷，不用 `std == 0`（std 會有浮點殘差）。"""
    return v.size == 0 or float(np.ptp(v)) == 0.0


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------


def daily_ic(
    df: pd.DataFrame,
    score_col: str = "score",
    ret_col: str = "label_r",
    method: str = "spearman",
) -> pd.Series:
    """每天的 IC：同一天所有股票的分數和報酬的相關係數。

    `df` 要有 `date`、`score_col`、`ret_col` 三欄（`date` 也可以是索引）。
    `method="spearman"` 是 RankIC（先在每天內排名，同分取平均名次），`"pearson"` 是一般 IC。

    規則：
    - 分數或報酬是 NaN、inf 的列先丟掉。
    - 一天至少 `MIN_STOCKS_PER_DAY`（3）檔才算，不夠的那天不出現在結果裡。
    - 分數或報酬當天每檔都一樣時，IC 記 0（沒有排序資訊），那天不丟掉。
      這樣常數輸出的模型不會因為那些天被拿掉而看起來比較好。

    回傳以 `date` 為索引、按日期排序的 `pd.Series`，名稱 `ic`，值在 [−1, 1]。
    """
    if method not in IC_METHODS:
        raise ValueError(f"method 要是 {IC_METHODS} 之一，拿到 {method!r}")
    frame = df
    if "date" not in frame.columns and "date" in (frame.index.names or []):
        frame = frame.reset_index(level="date")
    missing = [c for c in ("date", score_col, ret_col) if c not in frame.columns]
    if missing:
        raise ValueError(f"daily_ic 的 df 缺欄：{missing}")

    data = pd.DataFrame(
        {
            "date": _date_series(frame["date"]).to_numpy(),
            "s": _float_values(frame[score_col]),
            "r": _float_values(frame[ret_col]),
        }
    )
    ok = np.isfinite(data["s"].to_numpy()) & np.isfinite(data["r"].to_numpy()) & data["date"].notna().to_numpy()
    data = data.loc[ok]
    if len(data) == 0:
        return _empty_daily_series("ic")
    size = data.groupby("date", sort=False)["s"].transform("count").to_numpy()
    data = data.loc[size >= MIN_STOCKS_PER_DAY].copy()
    if len(data) == 0:
        return _empty_daily_series("ic")

    if method == "spearman":
        data["s"] = data.groupby("date", sort=False)["s"].rank(method="average").to_numpy(dtype=np.float64)
        data["r"] = data.groupby("date", sort=False)["r"].rank(method="average").to_numpy(dtype=np.float64)

    grouped = data.groupby("date", sort=True)
    s_dm = data["s"].to_numpy() - grouped["s"].transform("mean").to_numpy()
    r_dm = data["r"].to_numpy() - grouped["r"].transform("mean").to_numpy()
    parts = pd.DataFrame(
        {"date": data["date"].to_numpy(), "sr": s_dm * r_dm, "ss": s_dm * s_dm, "rr": r_dm * r_dm}
    )
    sums = parts.groupby("date", sort=True)[["sr", "ss", "rr"]].sum()
    constant = (grouped["s"].nunique() <= 1) | (grouped["r"].nunique() <= 1)
    constant = constant.reindex(sums.index).to_numpy(dtype=bool)

    denom = np.sqrt(sums["ss"].to_numpy() * sums["rr"].to_numpy())
    usable = (~constant) & (denom > 0) & np.isfinite(denom)
    ic = np.zeros(len(sums), dtype=np.float64)
    ic[usable] = sums["sr"].to_numpy()[usable] / denom[usable]
    ic = np.clip(ic, -1.0, 1.0)

    index = pd.DatetimeIndex(sums.index.to_numpy(dtype="datetime64[ns]"), name="date")
    return pd.Series(ic, index=index, name="ic")


# ---------------------------------------------------------------------------
# 標準誤和摘要
# ---------------------------------------------------------------------------


def newey_west_se(x: npt.ArrayLike | pd.Series, lags: int = 10) -> float:
    """平均數的 Newey-West 標準誤（Bartlett 權重）。

    長期變異數 = γ0 + 2 Σ_{j=1..L} (1 − j/(L+1)) γj，γj = Σ e_t e_{t−j} / n，e 是去平均後的序列。
    再乘 n/(n − 1)（和 Stata `newey` 一樣的小樣本修正），標準誤 = sqrt(長期變異數 / n)。
    所以 `lags=0` 時等於 `std(ddof=1) / sqrt(n)`，就是一般的 iid 標準誤。

    `lags` 超過 n − 1 時用 n − 1。NaN、inf 先丟掉。少於 2 個值回傳 NaN。
    """
    lags_int = int(lags)
    if lags_int < 0:
        raise ValueError(f"lags 不能是負的，拿到 {lags}")
    v = _finite_1d(x)
    n = int(v.size)
    if n < 2:
        return _NAN
    e = v - v.mean()
    max_lag = min(lags_int, n - 1)
    lrv = float(e @ e) / n
    for j in range(1, max_lag + 1):
        weight = 1.0 - j / (max_lag + 1.0)
        gamma = float(e[j:] @ e[:-j]) / n
        lrv += 2.0 * weight * gamma
    lrv = max(lrv, 0.0) * n / (n - 1.0)
    return math.sqrt(lrv / n)


def ic_summary(ic: pd.Series | npt.ArrayLike, lags: int = 10) -> dict[str, float]:
    """每天 IC 的摘要。鍵固定是 `mean, std, icir, t_iid, t_nw, n_days, hit_rate`。

    - `std` 用 ddof=1；`icir = mean / std`（每天的，沒有年化）。
    - `t_iid = mean / (std / sqrt(n))`；`t_nw = mean / newey_west_se(ic, lags)`。
    - `hit_rate`：IC > 0 的天數比例。`n_days` 是 int。
    - 天數不足或 IC 完全沒有波動時，比值類的鍵是 NaN。
    """
    v = _finite_1d(ic)
    n = int(v.size)
    out: dict[str, float] = {
        "mean": _NAN,
        "std": _NAN,
        "icir": _NAN,
        "t_iid": _NAN,
        "t_nw": _NAN,
        "n_days": n,
        "hit_rate": _NAN,
    }
    if n == 0:
        return out
    mean = float(v.mean())
    out["mean"] = mean
    out["hit_rate"] = float(np.mean(v > 0.0))
    if n < 2:
        return out
    std = float(np.std(v, ddof=1))
    out["std"] = std
    if _is_constant(v) or not std > 0.0:
        return out
    out["icir"] = mean / std
    out["t_iid"] = mean / (std / math.sqrt(n))
    se = newey_west_se(v, lags)
    if math.isfinite(se) and se > 0.0:
        out["t_nw"] = mean / se
    return out


def sharpe_ratio(daily: pd.Series | npt.ArrayLike, periods_per_year: float = 252) -> float:
    """年化 Sharpe：`mean / std(ddof=1) × sqrt(periods_per_year)`，不扣無風險利率。

    少於 2 天，或每天的值完全一樣（沒有波動，Sharpe 沒有定義）時回傳 NaN。
    """
    v = _finite_1d(daily)
    if v.size < 2 or _is_constant(v):
        return _NAN
    std = float(np.std(v, ddof=1))
    if not std > 0.0:
        return _NAN
    return float(v.mean()) / std * math.sqrt(float(periods_per_year))


def max_drawdown(daily: pd.Series | npt.ArrayLike, compound: bool = True) -> float:
    """最大回撤，回傳 ≤ 0 的數（例如 −0.12 代表從高點跌 12%）。

    - `compound=True`：淨值 = Π(1 + r)，起點淨值 1 也算高點，回撤 = 淨值 / 之前最高淨值 − 1。
    - `compound=False`：累積報酬 = Σ r，起點 0 也算高點，回撤 = 累積報酬 − 之前最高的累積報酬（報酬單位）。
    沒有回撤回傳 0.0；沒有資料回傳 NaN。
    """
    v = _finite_1d(daily)
    if v.size == 0:
        return _NAN
    if compound:
        wealth = np.concatenate([[1.0], np.cumprod(1.0 + v)])
        peak = np.maximum.accumulate(wealth)
        dd = wealth / peak - 1.0
    else:
        cum = np.concatenate([[0.0], np.cumsum(v)])
        peak = np.maximum.accumulate(cum)
        dd = cum - peak
    return float(min(float(dd.min()), 0.0))


def summarize_daily(
    daily: pd.Series | npt.ArrayLike,
    periods_per_year: float = 252,
    lags: int = 10,
) -> dict[str, float]:
    """每天報酬（或每天分數）的摘要。鍵固定是 `mean, std, sharpe, mdd, t_nw, n_days, win_rate`。

    - `mean`、`std`（ddof=1）是每天的，沒有年化；`sharpe` 是年化的（`sharpe_ratio`）。
    - `mdd` 用複利淨值（`max_drawdown(compound=True)`）。
    - `t_nw = mean / newey_west_se(daily, lags)`。
    - `win_rate`：值 > 0 的天數比例。`n_days` 是 int。
    """
    v = _finite_1d(daily)
    n = int(v.size)
    out: dict[str, float] = {
        "mean": _NAN,
        "std": _NAN,
        "sharpe": _NAN,
        "mdd": _NAN,
        "t_nw": _NAN,
        "n_days": n,
        "win_rate": _NAN,
    }
    if n == 0:
        return out
    mean = float(v.mean())
    out["mean"] = mean
    out["win_rate"] = float(np.mean(v > 0.0))
    out["mdd"] = max_drawdown(v, compound=True)
    if n < 2:
        return out
    out["std"] = float(np.std(v, ddof=1))
    out["sharpe"] = sharpe_ratio(v, periods_per_year=periods_per_year)
    if not _is_constant(v):
        se = newey_west_se(v, lags)
        if math.isfinite(se) and se > 0.0:
            out["t_nw"] = mean / se
    return out
