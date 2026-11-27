"""按日期切訓練、驗證、測試（不 import torch）。

規則：
- 只按日期切。先取交易日，再把樣本對回去，同一天的股票一定在同一邊。
- 相鄰兩段之間至少隔 `max(embargo_days, horizon − 1)` 個交易日（`required_gap`）。
  `horizon` h 的標籤看到 t+h−1，所以前一段最後一天的標籤不會跨進下一段。
- 切出來的每一段都用 `assert_no_overlap` 檢查：互斥、順序對、間隔夠。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from ..config import SplitConfig

_PARTS: tuple[str, ...] = ("train", "val", "test")


@dataclass(eq=False)
class Split:
    """一組切分。三段都是排序好、不重複的 `pd.DatetimeIndex`（ns）。

    `calendar` 是切分時用的完整交易日曆（給 `assert_no_overlap` 數間隔用），可以不給。
    """

    name: str
    train_dates: pd.DatetimeIndex
    val_dates: pd.DatetimeIndex
    test_dates: pd.DatetimeIndex
    calendar: pd.DatetimeIndex | None = field(default=None, repr=False)

    def part(self, which: str) -> pd.DatetimeIndex:
        """用名字取一段：`train`、`val`、`test`。"""
        if which not in _PARTS:
            raise ValueError(f"which 要是 {_PARTS} 之一，拿到 {which!r}")
        return getattr(self, f"{which}_dates")

    def summary(self) -> dict[str, object]:
        """每段的天數和起訖日（字串），可以直接寫進 JSON。"""
        out: dict[str, object] = {"name": self.name}
        for which in _PARTS:
            d = self.part(which)
            out[f"{which}_days"] = int(len(d))
            out[f"{which}_first"] = str(d[0].date()) if len(d) else None
            out[f"{which}_last"] = str(d[-1].date()) if len(d) else None
        return out


def required_gap(embargo_days: int = 0, horizon: int = 1) -> int:
    """相鄰兩段之間至少要隔幾個交易日：`max(embargo_days, horizon − 1)`。"""
    if int(horizon) < 1:
        raise ValueError(f"horizon 要 ≥ 1，拿到 {horizon}")
    if int(embargo_days) < 0:
        raise ValueError(f"embargo_days 要 ≥ 0，拿到 {embargo_days}")
    return max(int(embargo_days), int(horizon) - 1)


def _to_index(values: object) -> pd.DatetimeIndex:
    """轉成 ns 解析度、無時區的 `DatetimeIndex`。"""
    idx = pd.DatetimeIndex(pd.to_datetime(values))
    if idx.tz is not None:
        raise ValueError("日期不能有時區")
    if idx.hasnans:
        raise ValueError("日期有缺值")
    return pd.DatetimeIndex(np.asarray(idx.to_numpy(), dtype="datetime64[ns]"))


def _as_calendar(calendar: object) -> pd.DatetimeIndex:
    """交易日曆：ns、排序、不重複，否則丟 `ValueError`。"""
    cal = _to_index(calendar)
    if len(cal) == 0:
        raise ValueError("calendar 是空的")
    if not cal.is_monotonic_increasing or not cal.is_unique:
        raise ValueError("calendar 要排序且不重複")
    return cal


def _ts(value: object) -> pd.Timestamp:
    """單一日期轉成無時區的 `pd.Timestamp`。"""
    ts = pd.Timestamp(value)
    if ts is pd.NaT:
        raise ValueError("日期是 NaT")
    if ts.tzinfo is not None:
        raise ValueError("日期不能有時區")
    return ts


def _between(cal: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """日曆裡 start ≤ d ≤ end 的交易日。"""
    return cal[(cal >= start) & (cal <= end)]


def _trim_tail(part: pd.DatetimeIndex, next_first: pd.Timestamp, cal: pd.DatetimeIndex, gap: int) -> pd.DatetimeIndex:
    """去掉 `part` 尾端的交易日，讓它和下一段的第一天之間至少隔 `gap` 個交易日。

    兩段在日曆上相鄰時，剛好去掉 `gap` 天；本來就隔得夠遠時不動。
    """
    pos_next = int(cal.get_loc(next_first))
    pos = cal.get_indexer(part)
    return part[pos <= pos_next - gap - 1]


def fixed_split(calendar: pd.DatetimeIndex, cfg: SplitConfig, horizon: int = 1) -> Split:
    """照 `SplitConfig` 的日期切三段。

    - 訓練：`train_start` ～ `train_end`；驗證：`val_start` ～ `val_end`；
      測試：`test_start` ～ `test_end`（`None` 表示到日曆最後一天）。
    - 訓練尾端去掉交易日，讓訓練和驗證之間至少隔 `max(embargo_days, horizon − 1)` 天。
      兩段相鄰時就是去掉這麼多天（和 SPEC 一樣）；本來就有空檔時只補不足的部分。
    - 驗證尾端用同樣規則對測試留間隔，驗證的標籤才不會跨進測試期。
      預設 `horizon` 1、`embargo_days` 0 時兩邊都不動。
    - 三段日期設定重疊、或訓練、驗證是空的，丟 `ValueError`。測試是空的只警告。
    """
    cal = _as_calendar(calendar)
    gap = required_gap(int(cfg.embargo_days), int(horizon))
    train = _between(cal, _ts(cfg.train_start), _ts(cfg.train_end))
    val = _between(cal, _ts(cfg.val_start), _ts(cfg.val_end))
    test_end = _ts(cfg.test_end) if cfg.test_end is not None else cal[-1]
    test = _between(cal, _ts(cfg.test_start), test_end)
    if len(train) == 0:
        raise ValueError(f"訓練期 {cfg.train_start} ～ {cfg.train_end} 在日曆裡沒有交易日")
    if len(val) == 0:
        raise ValueError(f"驗證期 {cfg.val_start} ～ {cfg.val_end} 在日曆裡沒有交易日")
    if train[-1] >= val[0]:
        raise ValueError(f"訓練期最後一天 {train[-1].date()} 沒有早於驗證期第一天 {val[0].date()}")
    if len(test) and val[-1] >= test[0]:
        raise ValueError(f"驗證期最後一天 {val[-1].date()} 沒有早於測試期第一天 {test[0].date()}")

    train = _trim_tail(train, val[0], cal, gap)
    if len(test):
        val = _trim_tail(val, test[0], cal, gap)
    else:
        warnings.warn(f"測試期 {cfg.test_start} ～ {test_end} 在日曆裡沒有交易日", stacklevel=2)
    if len(train) == 0:
        raise ValueError("訓練期去掉 embargo 之後沒有交易日")
    if len(val) == 0:
        raise ValueError("驗證期去掉 embargo 之後沒有交易日")

    split = Split(name="fixed", train_dates=train, val_dates=val, test_dates=test, calendar=cal)
    assert_no_overlap(split, horizon, embargo_days=int(cfg.embargo_days))
    return split


def walk_forward_splits(
    calendar: pd.DatetimeIndex,
    first_test_start: str | pd.Timestamp,
    test_months: int = 6,
    val_days: int = 120,
    mode: str = "expanding",
    train_years: float | None = None,
    embargo_days: int = 0,
    horizon: int = 1,
    end: str | pd.Timestamp | None = None,
) -> list[Split]:
    """滾動切分：每段測試 `test_months` 個月，往後一段一段推。

    第 k 段（k 從 0 起）：
    - 測試：`first_test_start + k × test_months 個月` 起、到下一段開始前一天，不超過 `end`。
    - 驗證：測試第一天往前隔 `gap` 個交易日之後，往前數 `val_days` 個交易日。
    - 訓練：驗證第一天往前隔 `gap` 個交易日為止。`expanding` 從日曆第一天開始；
      `rolling` 只留最後 `train_years` 年（訓練最後一天往前 `train_years` 年，不含那一天；
      可以是小數，換成整數個月）。
    - `gap = max(embargo_days, horizon − 1)`。
    名稱是 `wf00_20200102` 這種格式（序號加測試第一天）。
    第一段的歷史不夠放驗證和訓練時丟 `ValueError`。
    """
    cal = _as_calendar(calendar)
    if int(test_months) < 1:
        raise ValueError(f"test_months 要 ≥ 1，拿到 {test_months}")
    if int(val_days) < 1:
        raise ValueError(f"val_days 要 ≥ 1，拿到 {val_days}")
    if mode not in ("expanding", "rolling"):
        raise ValueError(f"mode 要是 expanding 或 rolling，拿到 {mode!r}")
    if mode == "rolling" and (train_years is None or not float(train_years) > 0):
        raise ValueError("rolling 模式要給正的 train_years")
    # pandas 的 DateOffset 不收非整數的年，換成月（1.5 年 = 18 個月）。
    rolling_months = int(round(float(train_years) * 12)) if mode == "rolling" else 0  # type: ignore[arg-type]
    if mode == "rolling" and rolling_months < 1:
        raise ValueError(f"train_years 太小：{train_years}")
    gap = required_gap(int(embargo_days), int(horizon))
    start0 = _ts(first_test_start)
    last = cal[-1] if end is None else min(_ts(end), cal[-1])
    if start0 > last:
        raise ValueError(f"first_test_start {start0.date()} 晚於資料最後一天 {last.date()}")

    splits: list[Split] = []
    k = 0
    while True:
        seg_start = start0 + pd.DateOffset(months=k * int(test_months))
        if seg_start > last:
            break
        seg_stop = start0 + pd.DateOffset(months=(k + 1) * int(test_months))
        k += 1
        test = cal[(cal >= seg_start) & (cal < seg_stop) & (cal <= last)]
        if len(test) == 0:
            continue
        p_test = int(cal.get_loc(test[0]))
        val_end = p_test - gap - 1
        val_start = val_end - int(val_days) + 1
        train_end = val_start - gap - 1
        if train_end < 0:
            raise ValueError(
                f"測試期 {test[0].date()} 之前的交易日不夠放 {val_days} 天驗證、"
                f"兩段 {gap} 天間隔和至少 1 天訓練"
            )
        val = cal[val_start : val_end + 1]
        train_last = cal[train_end]
        if mode == "expanding":
            train = cal[: train_end + 1]
        else:
            lo = train_last - pd.DateOffset(months=rolling_months)
            train = cal[(cal > lo) & (cal <= train_last)]
        split = Split(
            name=f"wf{len(splits):02d}_{test[0]:%Y%m%d}",
            train_dates=train,
            val_dates=val,
            test_dates=test,
            calendar=cal,
        )
        assert_no_overlap(split, horizon, embargo_days=int(embargo_days))
        splits.append(split)
    if not splits:
        raise ValueError("沒有切出任何一段（測試期在日曆裡沒有交易日）")
    return splits


def assert_no_overlap(
    split: Split,
    horizon: int = 1,
    embargo_days: int = 0,
    calendar: pd.DatetimeIndex | None = None,
) -> None:
    """檢查切分：每段排序不重複、三段互斥、train < val < test、相鄰兩段間隔夠。

    間隔用交易日數：前一段最後一天和下一段第一天之間至少 `max(embargo_days, horizon − 1)` 天。
    要數間隔時用 `calendar`，沒給就用 `split.calendar`；兩個都沒有又需要間隔時丟 `ValueError`。
    空的段跳過（例如還沒開放的測試期）。不合格丟 `AssertionError`（不用 assert 敘述，`python -O` 也照樣檢查）。
    """
    gap = required_gap(int(embargo_days), int(horizon))
    parts: list[tuple[str, pd.DatetimeIndex]] = []
    for which in _PARTS:
        d = _to_index(split.part(which))
        if not d.is_monotonic_increasing or not d.is_unique:
            raise AssertionError(f"{split.name} 的 {which} 日期沒有排序或有重複")
        parts.append((which, d))

    for a in range(len(parts)):
        for b in range(a + 1, len(parts)):
            common = parts[a][1].intersection(parts[b][1])
            if len(common):
                raise AssertionError(
                    f"{split.name} 的 {parts[a][0]} 和 {parts[b][0]} 有 {len(common)} 天重疊，例如 {common[0].date()}"
                )

    nonempty = [(w, d) for w, d in parts if len(d)]
    for (wa, da), (wb, db) in zip(nonempty[:-1], nonempty[1:]):
        if not da[-1] < db[0]:
            raise AssertionError(f"{split.name} 的 {wa} 最後一天 {da[-1].date()} 沒有早於 {wb} 第一天 {db[0].date()}")

    cal_src = calendar if calendar is not None else split.calendar
    if cal_src is None:
        if gap > 0:
            raise ValueError("需要檢查間隔，但沒有 calendar（請傳 calendar 或用 fixed_split、walk_forward_splits 建 Split）")
        return
    cal = _to_index(cal_src)
    for which, d in nonempty:
        missing = d.difference(cal)
        if len(missing):
            raise AssertionError(f"{split.name} 的 {which} 有 {len(missing)} 天不在 calendar 裡，例如 {missing[0].date()}")
    for (wa, da), (wb, db) in zip(nonempty[:-1], nonempty[1:]):
        between = int(cal.get_loc(db[0])) - int(cal.get_loc(da[-1])) - 1
        if between < gap:
            raise AssertionError(
                f"{split.name} 的 {wa} 和 {wb} 之間只隔 {between} 個交易日，"
                f"至少要 {gap}（embargo_days={embargo_days}、horizon={horizon}）"
            )
