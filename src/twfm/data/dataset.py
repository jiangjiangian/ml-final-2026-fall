"""PyTorch 資料集：長表 → 「到 i 為止的視窗」加標籤。

時間規則：
- t 的輸入只用 `date < t` 的列，視窗最後一天就是 i（t 的前一個交易日）。
- t 當天的開盤、收盤只出現在標籤（`label_r`、`target_z`）和評估用的 `exec_*`，
  不會進 `levels`、`rets`、`stamps`。
- `PanelStore.window` 用 `searchsorted(t, side="left")` 取嚴格小於 t 的列，並檢查最後一天 < t。

主要介面：
- `SampleIndex`、`build_samples`：每個 (t, 股票) 一列的樣本表和標籤。
- `PanelStore`：每檔排序好的 numpy 陣列，`window` 切視窗。
- `PanelWindowDataset`、`DayBatchSampler`、`make_loader`：給訓練迴圈用。
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset, Sampler

from .adjust import adjusted_levels, limit_flags, log_returns

if TYPE_CHECKING:
    from ..config import DataConfig

LEVEL_COLS: tuple[str, ...] = ("adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "amount")
RET_COLS: tuple[str, ...] = ("ret_cc", "ret_gap", "ret_oc", "ret_hl", "log_amount")
STAMP_COLS: tuple[str, ...] = ("minute", "hour", "weekday", "day", "month")

_PANEL_REQUIRED: tuple[str, ...] = ("date", "stock_id", "open", "high", "low", "close", "volume", "amount")
_PANEL_NUMERIC: tuple[str, ...] = ("open", "high", "low", "close", "volume", "amount", "ref_price")
# (股票編號, 日序) 合成一個 int64 鍵時，日序的上限（約一萬一千年，夠用）。
_DAY_KEY_BASE: int = 1 << 22


# ---------------------------------------------------------------------------
# 型別整理的小工具
# ---------------------------------------------------------------------------


def _to_ns_array(values: object) -> npt.NDArray[np.datetime64]:
    """轉成 `datetime64[ns]` 的 numpy 陣列。

    pandas 3 會推成 us 或 s 解析度，這裡一律轉 ns，後面的比較和合併才對得上。
    有時區或有缺值就丟 `ValueError`。
    """
    idx = pd.DatetimeIndex(pd.to_datetime(values))
    if idx.tz is not None:
        raise ValueError("日期不能有時區，請用台北交易日的 naive datetime")
    if idx.hasnans:
        raise ValueError("日期有缺值")
    return np.asarray(idx.to_numpy(), dtype="datetime64[ns]")


def _scalar_ns(t: object) -> np.datetime64:
    """單一日期轉成 `datetime64[ns]` 純量。"""
    if isinstance(t, np.datetime64):
        if np.isnat(t):
            raise ValueError("t 是 NaT")
        return t.astype("datetime64[ns]")
    ts = pd.Timestamp(t)
    if ts is pd.NaT:
        raise ValueError("t 是 NaT")
    if ts.tzinfo is not None:
        raise ValueError("t 不能有時區")
    return ts.to_datetime64().astype("datetime64[ns]")


def _as_calendar(calendar: object) -> pd.DatetimeIndex:
    """交易日曆轉成 ns 解析度的 `DatetimeIndex`，並確認排序、不重複。"""
    cal = pd.DatetimeIndex(_to_ns_array(calendar))
    if not cal.is_monotonic_increasing or not cal.is_unique:
        raise ValueError("calendar 要排序且不重複")
    return cal


def _str_array(values: object) -> npt.NDArray[np.str_]:
    """股票代號轉成 numpy `<U` 陣列（pandas 2 給 object、pandas 3 給 str，這裡統一）。"""
    return np.asarray(pd.Series(values, dtype=object).astype(str).to_numpy(), dtype=str)


def _flag_array(col: pd.Series) -> npt.NDArray[np.bool_]:
    """把漲跌停旗標欄轉成 bool。缺值當作「不在漲跌停」。

    不能直接對整數欄用 `~`（`~0` 是 -1），所以先轉 float 再比較。
    """
    arr = col.to_numpy(dtype="float64", na_value=np.nan)
    return np.nan_to_num(arr, nan=0.0) != 0.0


def _prepare_panel(panel: pd.DataFrame, stock_ids: Iterable[str] | None = None) -> pd.DataFrame:
    """複製長表，整理型別，按 (stock_id, date) 排序，索引改成 0..n-1。

    `ref_price` 缺的列用同一檔前一列的收盤補（等於沒有除權息事件）。
    同一檔同一天重複就丟 `ValueError`。
    """
    missing = [c for c in _PANEL_REQUIRED if c not in panel.columns]
    if missing:
        raise ValueError(f"panel 少了欄位：{missing}")
    p = panel.copy()
    p["stock_id"] = _str_array(p["stock_id"])
    if stock_ids is not None:
        keep = set(_str_array(list(stock_ids)).tolist())
        p = p.loc[p["stock_id"].isin(keep)].copy()
    p["date"] = _to_ns_array(p["date"])
    if "ref_price" not in p.columns:
        p["ref_price"] = np.nan
    for col in _PANEL_NUMERIC:
        p[col] = pd.to_numeric(p[col], errors="raise").astype("float64")
    p = p.sort_values(["stock_id", "date"], kind="mergesort").reset_index(drop=True)
    if p.duplicated(["stock_id", "date"]).any():
        raise ValueError("panel 的 (date, stock_id) 有重複")
    prev_close = p.groupby("stock_id", sort=False)["close"].shift(1)
    p["ref_price"] = p["ref_price"].fillna(prev_close)
    return p


def _align_output(out: pd.DataFrame, p: pd.DataFrame, cols: Sequence[str], fname: str) -> pd.DataFrame:
    """把 adjust 模組回傳的表對回 `p` 的列順序，只留 `cols`。

    先看索引是否和 `p` 一樣；不一樣時用 `date`、`stock_id` 欄合併；都不行就丟錯。
    回傳的索引是 0..n-1，和 `p` 一列一列對齊。
    """
    if not isinstance(out, pd.DataFrame):
        raise TypeError(f"{fname} 應該回傳 DataFrame，拿到 {type(out).__name__}")
    missing = [c for c in cols if c not in out.columns]
    if missing:
        raise ValueError(f"{fname} 的輸出少了欄位：{missing}")
    if len(out) != len(p):
        raise ValueError(f"{fname} 回傳 {len(out)} 列，輸入是 {len(p)} 列")
    if out.index.equals(p.index):
        res = out.loc[:, list(cols)]
    elif {"date", "stock_id"}.issubset(out.columns):
        left = pd.DataFrame({"date": p["date"].to_numpy(), "stock_id": p["stock_id"].to_numpy().astype(str)})
        right = pd.DataFrame(
            {
                "date": _to_ns_array(out["date"]),
                "stock_id": _str_array(out["stock_id"]),
            }
        )
        for col in cols:
            right[col] = out[col].to_numpy()
        res = left.merge(right, on=["date", "stock_id"], how="left", validate="one_to_one")
        res = res.loc[:, list(cols)]
    elif out.index.is_unique and out.index.sort_values().equals(p.index):
        res = out.loc[p.index, list(cols)]
    else:
        raise ValueError(f"{fname} 的輸出對不回輸入的列（索引不同，也沒有 date、stock_id 欄）")
    return res.reset_index(drop=True)


def _check_alignment(levels: np.ndarray, rets: np.ndarray, p: pd.DataFrame) -> None:
    """抽查還原價、報酬和原始列有沒有對齊，對不上就丟 `ValueError`。

    同一天的收盤 ÷ 開盤不受還原影響，`amount` 不還原，`ret_oc` = log(收盤 ÷ 開盤)。
    任何一列錯位，這三個檢查幾乎一定會抓到。
    """
    close = p["close"].to_numpy(dtype="float64")
    open_ = p["open"].to_numpy(dtype="float64")
    amount = p["amount"].to_numpy(dtype="float64")
    raw_ratio = close / open_
    with np.errstate(divide="ignore", invalid="ignore"):
        adj_ratio = levels[:, 3] / levels[:, 0]
    if not np.isclose(adj_ratio, raw_ratio, rtol=1e-5, atol=0.0).all():
        raise ValueError("adjusted_levels 的 adj_close / adj_open 和原始 close / open 對不上，列可能錯位")
    if not np.isclose(levels[:, 5], amount, rtol=1e-6, atol=1e-6, equal_nan=True).all():
        raise ValueError("adjusted_levels 的 amount 和原始 amount 對不上，列可能錯位")
    if not np.isclose(rets[:, 2], np.log(raw_ratio), rtol=1e-5, atol=1e-6).all():
        raise ValueError("log_returns 的 ret_oc 和 log(close / open) 對不上，列可能錯位")


def _check_flags(up: npt.NDArray[np.bool_], down: npt.NDArray[np.bool_], p: pd.DataFrame) -> None:
    """抽查 `limit_flags` 的列有沒有對齊：開盤在漲停不會低於參考價，在跌停不會高於參考價。

    留 1% 的寬容（極低價股的漲跌停可能只差一個 tick）。錯位的話，隨機的列很快就會違反。
    """
    open_ = p["open"].to_numpy(dtype="float64")
    ref = p["ref_price"].to_numpy(dtype="float64")
    has_ref = np.isfinite(ref)
    if np.any(up & has_ref & ~(open_ > ref * 0.99)):
        raise ValueError("limit_flags 的 open_at_up 出現在開盤明顯低於參考價的列，列可能錯位")
    if np.any(down & has_ref & ~(open_ < ref * 1.01)):
        raise ValueError("limit_flags 的 open_at_down 出現在開盤明顯高於參考價的列，列可能錯位")


def _stock_change_codes(sorted_ids: npt.NDArray[np.str_]) -> npt.NDArray[np.int64]:
    """已按股票排序的代號陣列 → 0, 0, 1, 1, 1, 2… 的遞增編號。"""
    if len(sorted_ids) == 0:
        return np.zeros(0, dtype=np.int64)
    new = np.empty(len(sorted_ids), dtype=bool)
    new[0] = True
    new[1:] = sorted_ids[1:] != sorted_ids[:-1]
    return (np.cumsum(new) - 1).astype(np.int64)


def _daily_zscore(r: npt.NDArray[np.float64], day_ids: npt.NDArray[np.int64], clip: float) -> npt.NDArray[np.float32]:
    """同一天內 (r − mean) / std，std 用母體公式（ddof=0），再裁在 ±clip。

    一天只有 1 檔或全部一樣時 std 是 0，那天的 z 全部設 0。
    """
    if len(r) == 0:
        return np.zeros(0, dtype=np.float32)
    _, inv = np.unique(day_ids, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    cnt = np.bincount(inv).astype(np.float64)
    mean = np.bincount(inv, weights=r) / cnt
    dev = r - mean[inv]
    std = np.sqrt(np.bincount(inv, weights=dev * dev) / cnt)
    std_row = std[inv]
    z = np.zeros_like(r)
    ok = std_row > 1e-12
    z[ok] = dev[ok] / std_row[ok]
    return np.clip(z, -clip, clip).astype(np.float32)


# ---------------------------------------------------------------------------
# 樣本表
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class SampleIndex:
    """每個 (t, 股票) 一列的樣本表，按 (date, stock_id) 排序。

    欄位：
    - `dates`：t，`datetime64[ns]`。
    - `stock_ids`：股票代號，numpy `<U` 字串。
    - `day_ids`：t 在交易日曆裡的位置（int64）。同一天同一個數字，train、val、test 之間也不會撞號。
    - `target_z`：同一天股票池內 `(r − mean) / std`（ddof=0），裁在 ±`target_clip_z`，float32。
    - `label_r`：原始報酬 `close_t / open_t − 1`；`horizon` h > 1 時是 t 開盤到 t+h−1 收盤，float32，不裁。
    - `exec_long_ok`、`exec_short_ok`：t 開盤在漲停就不能買、在跌停就不能放空，bool。只給評估用，不是輸入。
    """

    dates: npt.NDArray[np.datetime64]
    stock_ids: npt.NDArray[np.str_]
    day_ids: npt.NDArray[np.int64]
    target_z: npt.NDArray[np.float32]
    label_r: npt.NDArray[np.float32]
    exec_long_ok: npt.NDArray[np.bool_]
    exec_short_ok: npt.NDArray[np.bool_]

    def __post_init__(self) -> None:
        self.dates = _to_ns_array(self.dates) if len(self.dates) else np.zeros(0, dtype="datetime64[ns]")
        self.stock_ids = np.asarray(self.stock_ids, dtype=str).reshape(-1)
        self.day_ids = np.asarray(self.day_ids, dtype=np.int64).reshape(-1)
        self.target_z = np.asarray(self.target_z, dtype=np.float32).reshape(-1)
        self.label_r = np.asarray(self.label_r, dtype=np.float32).reshape(-1)
        self.exec_long_ok = np.asarray(self.exec_long_ok, dtype=bool).reshape(-1)
        self.exec_short_ok = np.asarray(self.exec_short_ok, dtype=bool).reshape(-1)
        n = len(self.dates)
        for name in ("stock_ids", "day_ids", "target_z", "label_r", "exec_long_ok", "exec_short_ok"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"SampleIndex.{name} 長度 {len(getattr(self, name))}，dates 是 {n}")

    def __len__(self) -> int:
        return len(self.dates)

    def subset(self, rows: npt.ArrayLike) -> SampleIndex:
        """取部分列（bool 遮罩或整數位置），回傳新的 `SampleIndex`。"""
        idx = np.asarray(rows)
        if idx.dtype == bool:
            if len(idx) != len(self):
                raise ValueError("bool 遮罩長度和樣本數不同")
            idx = np.flatnonzero(idx)
        idx = idx.astype(np.int64)
        return SampleIndex(
            dates=self.dates[idx],
            stock_ids=self.stock_ids[idx],
            day_ids=self.day_ids[idx],
            target_z=self.target_z[idx],
            label_r=self.label_r[idx],
            exec_long_ok=self.exec_long_ok[idx],
            exec_short_ok=self.exec_short_ok[idx],
        )

    def select_dates(self, dates: object) -> SampleIndex:
        """只留 t 在 `dates` 裡的樣本。整天一起留或一起丟，`target_z` 不用重算。"""
        keep = _to_ns_array(dates).view("i8")
        mask = np.isin(self.dates.view("i8"), keep)
        return self.subset(mask)

    def to_frame(self) -> pd.DataFrame:
        """轉成 DataFrame：`date, stock_id, day_id, label_r, target_z, exec_long_ok, exec_short_ok`。

        `exec_*` 輸出成 0/1 的 int8，可以直接當 `run_backtest` 的 `labels`。
        """
        return pd.DataFrame(
            {
                "date": self.dates,
                "stock_id": self.stock_ids,
                "day_id": self.day_ids,
                "label_r": self.label_r,
                "target_z": self.target_z,
                "exec_long_ok": self.exec_long_ok.astype(np.int8),
                "exec_short_ok": self.exec_short_ok.astype(np.int8),
            }
        )


def _prepare_universe(universe: pd.DataFrame) -> pd.DataFrame:
    """股票池只留 `date, stock_id`，型別整理好、去重複。"""
    missing = [c for c in ("date", "stock_id") if c not in universe.columns]
    if missing:
        raise ValueError(f"universe 少了欄位：{missing}")
    uni = pd.DataFrame(
        {
            "date": _to_ns_array(universe["date"]) if len(universe) else np.zeros(0, dtype="datetime64[ns]"),
            "stock_id": _str_array(universe["stock_id"]),
        }
    )
    return uni.drop_duplicates(["date", "stock_id"]).reset_index(drop=True)


def _horizon_labels(
    p: pd.DataFrame, cal: pd.DatetimeIndex, rows: npt.NDArray[np.int64], horizon: int
) -> npt.NDArray[np.float64]:
    """h > 1 的標籤：t 開盤到 t+h−1 收盤的報酬，用還原價（含除權息）。

    t+h−1 那天這檔沒有列（停牌或已下市）時，用 t+h−1 以前最後一筆收盤。
    t+h−1 超出交易日曆，或晚於整個 panel 的最後一天（日曆比資料長，例如即時預測時的全年日曆）時是 NaN，
    之後會丟掉。後者不能用最後一筆收盤代替，否則 h 天的標籤會悄悄變成比較短的報酬。
    """
    if len(rows) == 0:
        return np.zeros(0, dtype=np.float64)
    lv = _align_output(adjusted_levels(p), p, ("adj_open", "adj_close"), "adjusted_levels")
    adj_open = lv["adj_open"].to_numpy(dtype="float64")
    adj_close = lv["adj_close"].to_numpy(dtype="float64")
    raw_ratio = p["close"].to_numpy(dtype="float64") / p["open"].to_numpy(dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        if not np.isclose(adj_close / adj_open, raw_ratio, rtol=1e-5, atol=0.0).all():
            raise ValueError("adjusted_levels 的 adj_close / adj_open 和原始 close / open 對不上，列可能錯位")
    codes = _stock_change_codes(p["stock_id"].to_numpy().astype(str))
    days = p["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    d0 = int(days.min())
    key = codes * _DAY_KEY_BASE + (days - d0)

    t_pos = cal.get_indexer(pd.DatetimeIndex(p["date"].to_numpy()[rows]))
    end_pos = t_pos + horizon - 1
    valid = (t_pos >= 0) & (end_pos < len(cal))
    # t+h−1 要在 panel 的最後一天以前（含），那天的收盤才已經知道。
    last_day = p["date"].to_numpy().astype("datetime64[ns]").max()
    cal_v = cal.to_numpy().astype("datetime64[ns]")
    valid[valid] = cal_v[end_pos[valid]] <= last_day
    out = np.full(len(rows), np.nan, dtype=np.float64)
    if not valid.any():
        return out
    r_valid = rows[valid]
    end_days = cal.to_numpy()[end_pos[valid]].astype("datetime64[D]").astype(np.int64) - d0
    if end_days.max() >= _DAY_KEY_BASE:
        raise ValueError("日期跨度太大，超出內部鍵的範圍")
    target = codes[r_valid] * _DAY_KEY_BASE + end_days
    end_row = np.searchsorted(key, target, side="right") - 1
    if not (np.all(end_row >= r_valid) and np.all(codes[end_row] == codes[r_valid])):
        raise AssertionError("找 t+h−1 收盤時跑到別檔或 t 以前，排序有問題")
    out[valid] = adj_close[end_row] / adj_open[r_valid] - 1.0
    return out


def build_samples(
    panel: pd.DataFrame,
    universe: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    cfg: DataConfig,
    dates: pd.DatetimeIndex | None = None,
) -> SampleIndex:
    """建樣本表：只收在 `universe` 裡、而且 t 那天有列（有標籤）的 (t, 股票)。

    - `horizon` 1：`label_r = close_t / open_t − 1`，用原始價（同一天的比例不受還原影響）。
    - `horizon` h > 1：t 開盤到 t+h−1 收盤，用還原價，見 `_horizon_labels`。t+h−1 超出日曆或晚於 panel
      的最後一天時沒有標籤，樣本丟掉。
    - `target_z`：同一天、這批樣本內的 z-score（ddof=0），裁在 ±`cfg.target_clip_z`。
    - `exec_*`：t 開盤在不在漲跌停，來自 `limit_flags`，只給評估用。
    - `dates` 有給時只留這些 t。
    - `day_ids` 是 t 在 `calendar` 的位置；t 不在日曆裡丟 `ValueError`。
    回傳按 (date, stock_id) 排序。
    """
    horizon = int(cfg.horizon)
    if horizon < 1:
        raise ValueError(f"horizon 要 ≥ 1，拿到 {horizon}")
    clip = float(cfg.target_clip_z)
    if not clip > 0:
        raise ValueError(f"target_clip_z 要 > 0，拿到 {clip}")
    cal = _as_calendar(calendar)
    p = _prepare_panel(panel)
    uni = _prepare_universe(universe)
    if dates is not None:
        keep = _to_ns_array(dates).view("i8")
        uni = uni.loc[np.isin(uni["date"].to_numpy().view("i8"), keep)].reset_index(drop=True)
    off_cal = ~np.isin(uni["date"].to_numpy().view("i8"), cal.asi8)
    if off_cal.any():
        bad = pd.DatetimeIndex(uni["date"].to_numpy()[off_cal]).unique()[:5]
        raise ValueError(f"universe 裡有不在 calendar 的日期，例如 {list(bad)}")

    flags =_align_output(limit_flags(p, cfg), p, ("open_at_up", "open_at_down"), "limit_flags")
    at_up = _flag_array(flags["open_at_up"])
    at_down = _flag_array(flags["open_at_down"])
    _check_flags(at_up, at_down, p)
    long_ok_all = ~at_up
    short_ok_all = ~at_down

    rows_df = pd.DataFrame(
        {
            "date": p["date"].to_numpy(),
            "stock_id": p["stock_id"].to_numpy().astype(str),
            "_row": np.arange(len(p), dtype=np.int64),
        }
    )
    m = uni.merge(rows_df, on=["date", "stock_id"], how="inner")
    rows = m["_row"].to_numpy(dtype=np.int64)

    if horizon == 1:
        close = p["close"].to_numpy(dtype="float64")
        open_ = p["open"].to_numpy(dtype="float64")
        label = close[rows] / open_[rows] - 1.0
    else:
        label = _horizon_labels(p, cal, rows, horizon)

    ok = np.isfinite(label)
    rows = rows[ok]
    label = label[ok]
    s_dates = p["date"].to_numpy()[rows].astype("datetime64[ns]")
    s_ids = p["stock_id"].to_numpy().astype(str)[rows]
    day_ids = cal.get_indexer(pd.DatetimeIndex(s_dates)).astype(np.int64)
    if (day_ids < 0).any():
        bad = pd.DatetimeIndex(s_dates[day_ids < 0]).unique()[:5]
        raise ValueError(f"universe 裡有不在 calendar 的日期，例如 {list(bad)}")

    order = np.lexsort((s_ids, day_ids))
    rows = rows[order]
    label = label[order]
    s_dates = s_dates[order]
    s_ids = s_ids[order]
    day_ids = day_ids[order]
    target_z = _daily_zscore(label, day_ids, clip)
    return SampleIndex(
        dates=s_dates,
        stock_ids=s_ids,
        day_ids=day_ids,
        target_z=target_z,
        label_r=label.astype(np.float32),
        exec_long_ok=long_ok_all[rows],
        exec_short_ok=short_ok_all[rows],
    )


# ---------------------------------------------------------------------------
# 每檔的陣列和視窗
# ---------------------------------------------------------------------------


class PanelStore:
    """把每檔排序好的 numpy 陣列存起來，給 `window` 快速切視窗。

    全部股票接成一條長陣列，按 (stock_id, date) 排序，每檔記起訖位置。
    DataLoader 的 worker 用 fork 時共用同一份記憶體。

    屬性：
    - `dates`：`datetime64[ns]` `[n]`。
    - `levels`：`adj_open, adj_high, adj_low, adj_close, adj_volume, amount`，float32 `[n, 6]`。
      `amount`、`adj_volume` 是原始量級（可到 1e10），進 fp16 前要先在 fp32 做 RevIN。
    - `rets`：`ret_cc, ret_gap, ret_oc, ret_hl, log_amount`，float32 `[n, 5]`。缺值和無限大填 0
      （每檔第一列沒有參考價，`ret_cc`、`ret_gap` 會是 0）。
    - `stamps`：Kronos 的時間戳 `[minute=0, hour=0, weekday, day, month]`，`[n, 5]`，存成 int8，
      `window` 回傳 float32（和官方 Kronos 一樣，模型裡再 `.long()`）。
    - `stock_ids`：有資料的股票代號，排序好。
    """

    def __init__(self, panel: pd.DataFrame, stock_ids: Iterable[str] | None = None) -> None:
        """`stock_ids` 有給時只存這些股票（省記憶體）。"""
        p = _prepare_panel(panel, stock_ids)
        n = len(p)
        if n == 0:
            raise ValueError("PanelStore 沒有任何列")
        lv = _align_output(adjusted_levels(p), p, LEVEL_COLS, "adjusted_levels").to_numpy(dtype="float64")
        rt = _align_output(log_returns(p), p, RET_COLS, "log_returns").to_numpy(dtype="float64")
        _check_alignment(lv, rt, p)

        bad_price = ~np.isfinite(lv[:, :4]) | (lv[:, :4] <= 0)
        if bad_price.any():
            raise ValueError(f"還原價有 {int(bad_price.any(axis=1).sum())} 列不是正的有限值")
        bad_qty = ~np.isfinite(lv[:, 4:])
        if bad_qty.any():
            warnings.warn(f"adj_volume 或 amount 有 {int(bad_qty.sum())} 格缺值，填 0", stacklevel=2)
            lv[:, 4:] = np.where(bad_qty, 0.0, lv[:, 4:])
        self.n_filled_rets = int((~np.isfinite(rt)).sum())
        rt = np.nan_to_num(rt, nan=0.0, posinf=0.0, neginf=0.0)

        self.dates: npt.NDArray[np.datetime64] = p["date"].to_numpy().astype("datetime64[ns]")
        self.levels: npt.NDArray[np.float32] = np.ascontiguousarray(lv, dtype=np.float32)
        self.rets: npt.NDArray[np.float32] = np.ascontiguousarray(rt, dtype=np.float32)
        di = pd.DatetimeIndex(self.dates)
        stamps = np.zeros((n, len(STAMP_COLS)), dtype=np.int8)
        stamps[:, 2] = np.asarray(di.weekday, dtype=np.int8)
        stamps[:, 3] = np.asarray(di.day, dtype=np.int8)
        stamps[:, 4] = np.asarray(di.month, dtype=np.int8)
        self.stamps: npt.NDArray[np.int8] = stamps

        sid = p["stock_id"].to_numpy().astype(str)
        codes = _stock_change_codes(sid)
        starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
        ends = np.r_[starts[1:], n]
        self.stock_ids: npt.NDArray[np.str_] = sid[starts]
        self._slices: dict[str, tuple[int, int]] = {
            str(s): (int(a), int(b)) for s, a, b in zip(self.stock_ids, starts, ends)
        }

    def __len__(self) -> int:
        return len(self.dates)

    def __contains__(self, stock_id: object) -> bool:
        return str(stock_id) in self._slices

    def stock_dates(self, stock_id: str) -> npt.NDArray[np.datetime64]:
        """這檔所有列的日期（排序好）。"""
        a, b = self._slices[str(stock_id)]
        return self.dates[a:b].copy()

    def n_history(self, stock_ids: npt.ArrayLike, dates: npt.ArrayLike) -> npt.NDArray[np.int64]:
        """每個 (股票, t) 在 t 以前（嚴格小於）有幾列。不在 store 裡的股票是 0。"""
        sids = np.asarray(stock_ids, dtype=str).reshape(-1)
        ts = _to_ns_array(dates) if len(sids) else np.zeros(0, dtype="datetime64[ns]")
        if len(ts) != len(sids):
            raise ValueError("stock_ids 和 dates 長度不同")
        out = np.zeros(len(sids), dtype=np.int64)
        if len(sids) == 0:
            return out
        uniq, inv = np.unique(sids, return_inverse=True)
        inv = np.asarray(inv).reshape(-1)
        order = np.argsort(inv, kind="stable")
        bounds = np.r_[0, np.cumsum(np.bincount(inv, minlength=len(uniq)))]
        for k, s in enumerate(uniq.tolist()):
            sl = self._slices.get(str(s))
            if sl is None:
                continue
            a, b = sl
            pos = order[bounds[k] : bounds[k + 1]]
            out[pos] = np.searchsorted(self.dates[a:b], ts[pos], side="left")
        return out

    def window(
        self, stock_id: str, t: object, lookback: int
    ) -> tuple[npt.NDArray[np.datetime64], npt.NDArray[np.float32], npt.NDArray[np.float32], npt.NDArray[np.float32]]:
        """回傳 t 以前（嚴格小於 t）最後 `lookback` 列：`(dates, levels, rets, stamps)`。

        - `dates` `[L]` datetime64[ns]、`levels` `[L, 6]`、`rets` `[L, 5]`、`stamps` `[L, 5]`，後三個 float32。
        - 回傳的是複本，改了不會動到 store。
        - 不足 `lookback` 列丟 `ValueError`；股票不在 store 裡丟 `KeyError`。
        """
        lookback = int(lookback)
        if lookback < 1:
            raise ValueError(f"lookback 要 ≥ 1，拿到 {lookback}")
        sl = self._slices.get(str(stock_id))
        if sl is None:
            raise KeyError(f"PanelStore 沒有股票 {stock_id}")
        a, b = sl
        t64 = _scalar_ns(t)
        end = a + int(np.searchsorted(self.dates[a:b], t64, side="left"))
        start = end - lookback
        if start < a:
            raise ValueError(f"{stock_id} 在 {pd.Timestamp(t64).date()} 以前只有 {end - a} 列，不足 lookback={lookback}")
        window_dates = self.dates[start:end].copy()
        if not window_dates[-1] < t64:
            raise AssertionError(f"視窗最後一天 {window_dates[-1]} 沒有早於 t={t64}")
        return (
            window_dates,
            self.levels[start:end].copy(),
            self.rets[start:end].copy(),
            self.stamps[start:end].astype(np.float32),
        )


# ---------------------------------------------------------------------------
# Dataset、Sampler、DataLoader
# ---------------------------------------------------------------------------


def _numeric_block(df: pd.DataFrame, what: str) -> tuple[npt.NDArray[np.float64], list[str]]:
    """協變量表轉成 float64 陣列，非數字欄丟錯。"""
    cols = [str(c) for c in df.columns]
    try:
        values = df.to_numpy(dtype="float64", na_value=np.nan)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} 有非數字的欄") from exc
    return values, cols


def _align_stock_cov(
    stock_cov: pd.DataFrame | None, samples: SampleIndex
) -> tuple[npt.NDArray[np.float32], list[str]]:
    """把個股協變量（索引 (date, stock_id)）對到每個樣本。

    找不到的樣本整列填 0 並警告；缺值和無限大也填 0（rank-gauss 之後 0 就是中位數）。
    """
    n = len(samples)
    if stock_cov is None:
        return np.zeros((n, 0), dtype=np.float32), []
    df = stock_cov
    if isinstance(df.index, pd.MultiIndex):
        names = list(df.index.names)
        lvl_date = df.index.get_level_values("date" if "date" in names else 0)
        lvl_sid = df.index.get_level_values("stock_id" if "stock_id" in names else 1)
        values, cols = _numeric_block(df, "stock_cov")
    elif {"date", "stock_id"}.issubset(df.columns):
        lvl_date = df["date"]
        lvl_sid = df["stock_id"]
        values, cols = _numeric_block(df.drop(columns=["date", "stock_id"]), "stock_cov")
    else:
        raise ValueError("stock_cov 要用 (date, stock_id) 當索引，或有 date、stock_id 兩欄")
    right = pd.DataFrame(
        {
            "date": _to_ns_array(lvl_date) if len(df) else np.zeros(0, dtype="datetime64[ns]"),
            "stock_id": _str_array(lvl_sid),
            "_src": np.arange(len(df), dtype=np.int64),
        }
    )
    if right.duplicated(["date", "stock_id"]).any():
        raise ValueError("stock_cov 的 (date, stock_id) 有重複")
    left = pd.DataFrame({"date": samples.dates, "stock_id": samples.stock_ids})
    merged = left.merge(right, on=["date", "stock_id"], how="left", validate="many_to_one")
    src = merged["_src"].to_numpy(dtype="float64", na_value=np.nan)
    found = np.isfinite(src)
    out = np.zeros((n, len(cols)), dtype=np.float64)
    if found.any():
        out[found] = values[src[found].astype(np.int64)]
    if (~found).any():
        warnings.warn(f"stock_cov 找不到 {int((~found).sum())} 個樣本，整列填 0", stacklevel=3)
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return np.ascontiguousarray(out, dtype=np.float32), cols


def _align_market_cov(
    market_cov: pd.DataFrame | None, samples: SampleIndex
) -> tuple[npt.NDArray[np.float32], list[str]]:
    """把市場協變量（索引 date）對到每個樣本。找不到的日期填 0 並警告。"""
    n = len(samples)
    if market_cov is None:
        return np.zeros((n, 0), dtype=np.float32), []
    df = market_cov
    if isinstance(df.index, pd.MultiIndex):
        raise ValueError("market_cov 的索引只能是 date")
    if "date" in df.columns:
        idx_date = df["date"]
        values, cols = _numeric_block(df.drop(columns=["date"]), "market_cov")
    else:
        idx_date = df.index
        values, cols = _numeric_block(df, "market_cov")
    right = pd.DataFrame(
        {
            "date": _to_ns_array(idx_date) if len(df) else np.zeros(0, dtype="datetime64[ns]"),
            "_src": np.arange(len(df), dtype=np.int64),
        }
    )
    if right.duplicated(["date"]).any():
        raise ValueError("market_cov 的 date 有重複")
    left = pd.DataFrame({"date": samples.dates})
    merged = left.merge(right, on="date", how="left", validate="many_to_one")
    src = merged["_src"].to_numpy(dtype="float64", na_value=np.nan)
    found = np.isfinite(src)
    out = np.zeros((n, len(cols)), dtype=np.float64)
    if found.any():
        out[found] = values[src[found].astype(np.int64)]
    if (~found).any():
        warnings.warn(f"market_cov 找不到 {int((~found).sum())} 個樣本的日期，整列填 0", stacklevel=3)
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return np.ascontiguousarray(out, dtype=np.float32), cols


class PanelWindowDataset(Dataset):
    """每個樣本 = 一檔股票在一個 t 的視窗加協變量和標籤。

    `__getitem__` 回傳 `dict[str, torch.Tensor]`：
    - `levels [L, 6]`、`stamps [L, 5]`、`rets [L, 5]`：float32，全部在 i 以前。
    - `stock_cov [C_s]`、`market_cov [C_m]`：float32，沒有協變量時長度 0。
    - `target_z []`、`label_r []`：float32。
    - `day_id []`、`index []`：int64，`index` 是樣本序號，用來對回 `samples` 的 date 和 stock_id。
    - `exec_long_ok []`、`exec_short_ok []`：bool，只給評估用。
    """

    def __init__(
        self,
        store: PanelStore,
        samples: SampleIndex,
        stock_cov: pd.DataFrame | None,
        market_cov: pd.DataFrame | None,
        lookback: int,
    ) -> None:
        """建構時就檢查每個樣本的歷史夠不夠 `lookback`，不夠丟 `ValueError`（不等到訓練中途）。"""
        self.store = store
        self.samples = samples
        self.lookback = int(lookback)
        if self.lookback < 1:
            raise ValueError(f"lookback 要 ≥ 1，拿到 {lookback}")
        hist = store.n_history(samples.stock_ids, samples.dates)
        short = hist < self.lookback
        if short.any():
            k = int(np.flatnonzero(short)[0])
            raise ValueError(
                f"{int(short.sum())} 個樣本在 t 以前不足 lookback={self.lookback} 列，"
                f"例如 {samples.stock_ids[k]} 在 {pd.Timestamp(samples.dates[k]).date()} 只有 {int(hist[k])} 列"
            )
        self._stock_cov, self.stock_cov_cols = _align_stock_cov(stock_cov, samples)
        self._market_cov, self.market_cov_cols = _align_market_cov(market_cov, samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        k = int(idx)
        if k < 0:
            k += len(self.samples)
        if not 0 <= k < len(self.samples):
            raise IndexError(f"樣本序號 {idx} 超出範圍")
        s = self.samples
        _, levels, rets, stamps = self.store.window(str(s.stock_ids[k]), s.dates[k], self.lookback)
        return {
            "levels": torch.from_numpy(levels),
            "stamps": torch.from_numpy(stamps),
            "rets": torch.from_numpy(rets),
            "stock_cov": torch.from_numpy(self._stock_cov[k].copy()),
            "market_cov": torch.from_numpy(self._market_cov[k].copy()),
            "target_z": torch.tensor(float(s.target_z[k]), dtype=torch.float32),
            "label_r": torch.tensor(float(s.label_r[k]), dtype=torch.float32),
            "day_id": torch.tensor(int(s.day_ids[k]), dtype=torch.int64),
            "index": torch.tensor(k, dtype=torch.int64),
            "exec_long_ok": torch.tensor(bool(s.exec_long_ok[k]), dtype=torch.bool),
            "exec_short_ok": torch.tensor(bool(s.exec_short_ok[k]), dtype=torch.bool),
        }


class DayBatchSampler(Sampler[list[int]]):
    """每個 batch 是 `batch_days` 天的全部樣本，同一天一定在同一個 batch（給排序損失用）。

    - `shuffle=True`：每個 epoch 打亂天的順序；有 `max_stocks_per_day` 時每天隨機抽那麼多檔。
      亂數種子是 `(seed, epoch)`，同樣的 seed 和 epoch 一定得到同樣的順序。
    - `shuffle=False`：天按 `day_ids` 由小到大；有 `max_stocks_per_day` 時每個 epoch 抽到的檔都一樣。
      驗證和預測請用 `shuffle=False`、`max_stocks_per_day=None`，才不會漏樣本。
    - 每個 batch 裡按天、再按樣本序號排。最後一個 batch 可能不足 `batch_days` 天。
    """

    def __init__(
        self,
        day_ids: npt.ArrayLike,
        batch_days: int,
        shuffle: bool,
        seed: int,
        max_stocks_per_day: int | None = None,
    ) -> None:
        ids = np.asarray(day_ids, dtype=np.int64).reshape(-1)
        if int(batch_days) < 1:
            raise ValueError(f"batch_days 要 ≥ 1，拿到 {batch_days}")
        if max_stocks_per_day is not None and int(max_stocks_per_day) < 1:
            raise ValueError(f"max_stocks_per_day 要 ≥ 1，拿到 {max_stocks_per_day}")
        if int(seed) < 0:
            raise ValueError(f"seed 要 ≥ 0，拿到 {seed}")
        self.batch_days = int(batch_days)
        self.shuffle = bool(shuffle)
        self.seed = int(seed)
        self.max_stocks_per_day = None if max_stocks_per_day is None else int(max_stocks_per_day)
        self.epoch = 0
        order = np.argsort(ids, kind="stable")
        _, starts, counts = np.unique(ids[order], return_index=True, return_counts=True)
        self._groups: list[npt.NDArray[np.int64]] = [
            order[a : a + c].astype(np.int64) for a, c in zip(starts.tolist(), counts.tolist())
        ]

    @property
    def n_days(self) -> int:
        return len(self._groups)

    def set_epoch(self, epoch: int) -> None:
        """換 epoch（影響 `shuffle=True` 時的順序和抽樣）。"""
        self.epoch = int(epoch)

    def __len__(self) -> int:
        return math.ceil(self.n_days / self.batch_days)

    def __iter__(self) -> Iterator[list[int]]:
        if self.shuffle:
            rng = np.random.default_rng([self.seed, self.epoch])
            day_order = rng.permutation(self.n_days)
        else:
            rng = np.random.default_rng([self.seed])
            day_order = np.arange(self.n_days)
        cap = self.max_stocks_per_day
        for b in range(0, self.n_days, self.batch_days):
            parts: list[npt.NDArray[np.int64]] = []
            for d in day_order[b : b + self.batch_days].tolist():
                g = self._groups[d]
                if cap is not None and len(g) > cap:
                    g = np.sort(rng.choice(g, size=cap, replace=False))
                parts.append(g)
            yield np.concatenate(parts).astype(np.int64).tolist()


def make_loader(
    dataset: PanelWindowDataset,
    day_ids: npt.ArrayLike,
    batch_days: int,
    shuffle: bool,
    seed: int,
    num_workers: int,
    max_stocks_per_day: int | None = None,
) -> DataLoader:
    """用 `DayBatchSampler` 當 `batch_sampler` 的 DataLoader，預設 collate。

    換 epoch 時呼叫 `loader.batch_sampler.set_epoch(epoch)`。
    """
    ids = np.asarray(day_ids, dtype=np.int64).reshape(-1)
    if len(ids) != len(dataset):
        raise ValueError(f"day_ids 長度 {len(ids)}，dataset 是 {len(dataset)}")
    sampler = DayBatchSampler(ids, batch_days, shuffle, seed, max_stocks_per_day)
    num_workers = int(num_workers)
    if num_workers > 0:
        return DataLoader(
            dataset,
            batch_sampler=sampler,
            num_workers=num_workers,
            pin_memory=torch.cuda.is_available(),
            persistent_workers=False,
            prefetch_factor=2,
        )
    return DataLoader(
        dataset,
        batch_sampler=sampler,
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
    )
