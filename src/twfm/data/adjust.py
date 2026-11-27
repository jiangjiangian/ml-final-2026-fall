"""還原權息、對數報酬、漲跌停。

輸入都是 `panel`（見 `schema.PANEL_COLS`，交易所原始價、未還原）。函式內部按 (stock_id, date)
排序計算，結果對回輸入的 index，所以輸入不用先排序，也不會被修改。
「前一列」都是同一檔按日期的前一列（停牌日沒有列，所以停牌前最後一天就是前一列）。

`ref_price` 缺值時用同一檔前一列的 `close` 代替（等於那天沒有事件），見 `effective_ref_price`。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import DataConfig
from .schema import stock_date_order

# 事件因子和 1 的差在這以內就當成沒有事件（浮點誤差、四捨五入）。
_EVENT_TOL = 1e-4

# 台股升降單位（2005 年以後的級距）：價格 < 10、10～50、50～100、100～500、500～1000、≥ 1000。
_TICK_BOUNDS = np.array([10.0, 50.0, 100.0, 500.0, 1000.0])
_TICK_SIZES = np.array([0.01, 0.05, 0.1, 0.5, 1.0, 5.0])
_PRICE_EPS = 1e-9

RETURN_COLS: tuple[str, ...] = ("ret_cc", "ret_gap", "ret_oc", "ret_hl", "log_amount")
LEVEL_COLS: tuple[str, ...] = ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "amount")
FLAG_COLS: tuple[str, ...] = ("close_at_up", "close_at_down", "open_at_up", "open_at_down", "limit_streak")


# ---------- 分組陣列工具（排序後的陣列，同一檔連續） ----------


def group_starts(first: np.ndarray) -> np.ndarray:
    """每一列所屬那一檔的第一列位置。`first` 是排序後「每檔第一列」的標記。"""
    n = len(first)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    idx = np.where(first, np.arange(n, dtype=np.int64), 0)
    return np.maximum.accumulate(idx)


def group_shift(values: np.ndarray, first: np.ndarray, k: int) -> np.ndarray:
    """同一檔往前 k 列的值（k ≥ 1），不足 k 列是 NaN。"""
    if k < 0:
        raise ValueError("k 不能是負的")
    v = np.asarray(values, dtype=np.float64)
    if k == 0:
        return v.copy()
    n = len(v)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    src = np.arange(n, dtype=np.int64) - k
    ok = src >= group_starts(first)
    out[ok] = v[src[ok]]
    return out


def group_rolling_sum(values: np.ndarray, first: np.ndarray, window: int) -> np.ndarray:
    """同一檔最後 `window` 列（含這一列）的和。不足 `window` 列時加總現有的。"""
    v = np.asarray(values, dtype=np.float64)
    n = len(v)
    if n == 0:
        return np.zeros(0)
    c = np.concatenate([[0.0], np.cumsum(v)])
    pos = np.arange(n, dtype=np.int64)
    lo = np.maximum(pos - window + 1, group_starts(first))
    return c[pos + 1] - c[lo]


def signed_streak(state: np.ndarray, first: np.ndarray) -> np.ndarray:
    """連續天數：`state` 是 +1、−1、0，連續 +1 記 +1、+2…，連續 −1 記 −1、−2…，0 記 0。

    換檔（`first`）或狀態改變時重新計數。輸入是排序後的陣列。
    """
    s = np.asarray(state, dtype=np.int64)
    n = len(s)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    change = np.ones(n, dtype=bool)
    if n > 1:
        change[1:] = (s[1:] != s[:-1]) | np.asarray(first, dtype=bool)[1:]
    run_start = np.flatnonzero(change)
    run_id = np.cumsum(change) - 1
    count = np.arange(n, dtype=np.int64) - run_start[run_id] + 1
    return s * count


def _scatter(order: np.ndarray, sorted_values: np.ndarray) -> np.ndarray:
    """把排序後的值放回原本的位置。"""
    out = np.empty_like(sorted_values)
    out[order] = sorted_values
    return out


def _f64(series: pd.Series) -> np.ndarray:
    return series.to_numpy(dtype=np.float64, na_value=np.nan)


class _Sorted:
    """panel 按 (stock_id, date) 排序後的陣列，避免每個函式重算。"""

    def __init__(self, panel: pd.DataFrame) -> None:
        self.n = len(panel)
        self.order, self.first = stock_date_order(panel["stock_id"], panel["date"])
        o = self.order
        self.open = _f64(panel["open"])[o]
        self.high = _f64(panel["high"])[o]
        self.low = _f64(panel["low"])[o]
        self.close = _f64(panel["close"])[o]
        self.volume = _f64(panel["volume"])[o]
        self.amount = _f64(panel["amount"])[o]
        self.ref_raw = _f64(panel["ref_price"])[o]
        self.dates = np.asarray(panel["date"].to_numpy()).astype("datetime64[ns]")[o]
        self.prev_close = group_shift(self.close, self.first, 1)
        ref = self.ref_raw.copy()
        missing = ~np.isfinite(ref)
        ref[missing] = self.prev_close[missing]
        self.ref = ref


def effective_ref_price(panel: pd.DataFrame) -> pd.Series:
    """實際用的參考價：`ref_price`，缺值時用同一檔前一列的 `close`。每檔第一列沒有前一列時是 NaN。"""
    s = _Sorted(panel)
    return pd.Series(_scatter(s.order, s.ref), index=panel.index, name="ref_price")


def _event_factors_sorted(s: _Sorted) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        f = s.ref / s.prev_close
    bad = ~np.isfinite(f) | (f <= 0) | (np.abs(f - 1.0) <= _EVENT_TOL)
    f[bad] = 1.0
    f[s.first] = 1.0
    return f


def _cum_factor_sorted(s: _Sorted) -> np.ndarray:
    f = _event_factors_sorted(s)
    grp = np.cumsum(s.first) - 1
    return pd.Series(f).groupby(grp).cumprod().to_numpy(dtype=np.float64)


def event_factors(panel: pd.DataFrame) -> pd.Series:
    """每列的除權息事件因子 `f_d = ref_price_d / close_{d−1}`（同一檔前一列的收盤）。

    沒有事件時是 1。`|f_d − 1| ≤ 1e-4`、缺值、非正數都設 1，每檔第一列也設 1。
    除息、除權時 f < 1，減資這類參考價高於前一天收盤的事件 f > 1。
    """
    s = _Sorted(panel)
    return pd.Series(_scatter(s.order, _event_factors_sorted(s)), index=panel.index, name="factor")


def cumulative_factor(panel: pd.DataFrame) -> pd.Series:
    """累積因子 `F_d = Π_{k ≤ d} f_k`，同一檔從第一列往後累乘。

    d 日的 `F_d` 只用到 d 以前（含 d）的事件，所以時點正確，不偷看之後的除權息。
    """
    s = _Sorted(panel)
    return pd.Series(_scatter(s.order, _cum_factor_sorted(s)), index=panel.index, name="cum_factor")


def adjusted_levels(panel: pd.DataFrame) -> pd.DataFrame:
    """還原權息後的價格水準。回傳和 `panel` 同 index 的表（沒有 `date`、`stock_id` 欄，用 index 對回）。

    欄：`adj_open, adj_high, adj_low, adj_close`（原始價 ÷ `F_d`）、`adj_volume`（原始量 × `F_d`）、
    `amount`（成交金額不受除權息影響，不變）。

    為什麼可以用一條全域序列：任兩天 a < b 的還原價比
    `adj_b / adj_a = (p_b / p_a) × (F_a / F_b)`，而 `F_a / F_b` 只是 a、b 之間（a 之後到 b）的事件因子乘積。
    所以從這組序列切出一個視窗，和「站在視窗最後一天往回還原」的價格只差一個常數倍
    （那個常數是視窗最後一天以前的累積因子）。每個視窗自己標準化（例如 RevIN 用視窗的平均和標準差）
    之後完全一樣，視窗之後的事件完全不影響，不偷看。
    """
    s = _Sorted(panel)
    F = _cum_factor_sorted(s)
    o = s.order
    out = pd.DataFrame(
        {
            "adj_open": _scatter(o, s.open / F),
            "adj_high": _scatter(o, s.high / F),
            "adj_low": _scatter(o, s.low / F),
            "adj_close": _scatter(o, s.close / F),
            "adj_volume": _scatter(o, s.volume * F),
            "amount": _scatter(o, s.amount.copy()),
        },
        index=panel.index,
    )
    return out


def _log_returns_sorted(s: _Sorted) -> dict[str, np.ndarray]:
    with np.errstate(divide="ignore", invalid="ignore"):
        ret_cc = np.log(s.close / s.ref)
        ret_gap = np.log(s.open / s.ref)
        ret_oc = np.log(s.close / s.open)
        ret_hl = np.log(s.high / s.low)
        log_amount = np.log1p(np.maximum(s.amount, 0.0))
    out = {"ret_cc": ret_cc, "ret_gap": ret_gap, "ret_oc": ret_oc, "ret_hl": ret_hl, "log_amount": log_amount}
    for v in out.values():
        v[~np.isfinite(v)] = np.nan
    return out


def log_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """每列的對數報酬。回傳和 `panel` 同 index 的表。

    `ret_cc = log(close / ref_price)`：收盤到收盤，參考價已經扣掉除權息，所以等於已還原的報酬。
    `ret_gap = log(open / ref_price)`：跳空。`ret_oc = log(close / open)`：盤中。
    `ret_hl = log(high / low)`：振幅。`log_amount = log1p(amount)`。
    直接用參考價，不需要還原價。參考價缺值時用前一列收盤；每檔第一列沒有參考價時 `ret_cc`、`ret_gap` 是 NaN。
    """
    s = _Sorted(panel)
    r = _log_returns_sorted(s)
    return pd.DataFrame({k: _scatter(s.order, r[k]) for k in RETURN_COLS}, index=panel.index)


def tick_size(price: np.ndarray) -> np.ndarray:
    """台股升降單位。

    < 10：0.01；10～50：0.05；50～100：0.1；100～500：0.5；500～1000：1；≥ 1000：5（左閉右開）。
    這是 2005 年以後的級距，更早的年份（級距不同）只是近似。NaN 回傳 NaN。
    """
    p = np.asarray(price, dtype=np.float64)
    flat = p.reshape(-1)
    out = np.full(flat.shape, np.nan)
    ok = np.isfinite(flat)
    idx = np.searchsorted(_TICK_BOUNDS, flat[ok] + _PRICE_EPS, side="right")
    out[ok] = _TICK_SIZES[idx]
    return out.reshape(p.shape)


def _as_datetime_array(dates: object, n: int) -> np.ndarray:
    """日期轉成 `datetime64[ns]` 陣列，長度 1 時展開成 n。"""
    if np.ndim(dates) == 0:
        dates = [dates]
    arr = pd.DatetimeIndex(pd.to_datetime(dates)).as_unit("ns").to_numpy()
    if len(arr) == 1 and n != 1:
        arr = np.repeat(arr, n)
    if len(arr) != n:
        raise ValueError(f"dates 的長度 {len(arr)} 和 ref_price 的長度 {n} 不同")
    return arr


def limit_pct(dates: object, cfg: DataConfig, n: int | None = None) -> np.ndarray:
    """每個日期的漲跌幅：`limit_change_date`（含）以後 `limit_pct_new`，以前 `limit_pct_old`。"""
    if n is None:
        n = 1 if np.ndim(dates) == 0 else len(dates)  # type: ignore[arg-type]
    d = _as_datetime_array(dates, n)
    change = np.datetime64(pd.Timestamp(cfg.limit_change_date).as_unit("ns").to_datetime64())
    return np.where(d >= change, cfg.limit_pct_new, cfg.limit_pct_old)


def limit_prices(ref_price: object, dates: object, cfg: DataConfig) -> tuple[np.ndarray, np.ndarray]:
    """漲停價和跌停價。

    漲停 = `ref × (1 + p)` 往下取到升降單位，跌停 = `ref × (1 − p)` 往上取到升降單位；
    p 在 `limit_change_date` 以前是 `limit_pct_old`（7%），以後（含那天）是 `limit_pct_new`（10%）。
    升降單位用漲跌停價本身所在的級距（級距邊界 10、50、100、500、1000 剛好是大單位的倍數，
    所以用未取整的價格判斷級距，取整後還在同一級距）。`dates` 可以是一個日期（全部共用）或一串日期。
    回傳 `(up, down)`，四捨五入到小數兩位；ref 缺值的位置是 NaN。

    例：2020 年 ref 100 → 110、90；ref 15.3 → 16.80、13.80；2010 年 ref 100 → 107、93。
    """
    ref = np.asarray(ref_price, dtype=np.float64).reshape(-1)
    pct = limit_pct(dates, cfg, n=len(ref))
    raw_up = ref * (1.0 + pct)
    raw_dn = ref * (1.0 - pct)
    tick_up = tick_size(raw_up)
    tick_dn = tick_size(raw_dn)
    with np.errstate(invalid="ignore"):
        up = np.floor((raw_up + _PRICE_EPS) / tick_up) * tick_up
        dn = np.ceil((raw_dn - _PRICE_EPS) / tick_dn) * tick_dn
    return np.round(up, 2), np.round(dn, 2)


def _limit_flags_sorted(s: _Sorted, cfg: DataConfig) -> dict[str, np.ndarray]:
    up, dn = limit_prices(s.ref, s.dates, cfg)
    half_up = 0.5 * tick_size(up)
    half_dn = 0.5 * tick_size(dn)
    with np.errstate(invalid="ignore"):
        close_at_up = np.abs(s.close - up) < half_up
        close_at_down = np.abs(s.close - dn) < half_dn
        open_at_up = np.abs(s.open - up) < half_up
        open_at_down = np.abs(s.open - dn) < half_dn
    # 漲停和跌停不可能同時成立；萬一資料怪異，以漲停為準。
    close_at_down &= ~close_at_up
    open_at_down &= ~open_at_up
    state = close_at_up.astype(np.int64) - close_at_down.astype(np.int64)
    streak = signed_streak(state, s.first)
    return {
        "close_at_up": close_at_up,
        "close_at_down": close_at_down,
        "open_at_up": open_at_up,
        "open_at_down": open_at_down,
        "limit_streak": streak,
    }


def limit_flags(panel: pd.DataFrame, cfg: DataConfig) -> pd.DataFrame:
    """漲跌停標記。回傳和 `panel` 同 index 的表。

    `close_at_up`、`close_at_down`、`open_at_up`、`open_at_down`（bool）：和當天漲跌停價差小於半個升降單位。
    `limit_streak`（int64）：連續收在漲停記 +1、+2…，連續收在跌停記 −1、−2…，其他 0，同一檔按日期往前算。
    t 的開盤是否漲跌停不能當 t 的輸入，只能用在評估的可成交遮罩（欄名要以 `exec_` 開頭）。
    """
    s = _Sorted(panel)
    f = _limit_flags_sorted(s, cfg)
    return pd.DataFrame({k: _scatter(s.order, f[k]) for k in FLAG_COLS}, index=panel.index)
