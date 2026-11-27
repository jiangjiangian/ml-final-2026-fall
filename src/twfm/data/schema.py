"""資料格式：欄名常數、檢查函式、普通股代號規則。

全部是 long 格式的 `pd.DataFrame`。`date` 是 `datetime64[ns]`（台北交易日，沒有時區、沒有時間），
`stock_id` 是字串。`validate_*` 回傳整理好的新表（型別轉好、排序、RangeIndex），不改輸入；
不合格丟 `SchemaError`。

排序：`panel`、`inst_daily`、`margin_daily` 按 `(date, stock_id)`，`us_daily` 按 `(us_date, symbol)`。
其他模組不依賴輸入的順序，都會自己排序再對回原本的 index。
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

PANEL_COLS: tuple[str, ...] = (
    "date",
    "stock_id",
    "market",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "ref_price",
)
PRICE_COLS: tuple[str, ...] = ("open", "high", "low", "close")
US_COLS: tuple[str, ...] = ("us_date", "symbol", "close")
INST_COLS: tuple[str, ...] = ("date", "stock_id", "foreign_net", "trust_net", "dealer_net")
MARGIN_COLS: tuple[str, ...] = ("date", "stock_id", "margin_balance")
MARKETS: tuple[str, ...] = ("twse", "tpex")

# 普通股：四碼、第一碼 1～9。00 開頭（ETF）、六碼（權證、ETF）、帶英文字母（特別股）都不符合。
_COMMON_RE = re.compile(r"[1-9][0-9]{3}")
# 91 開頭是台灣存託憑證（TDR），四碼的也有（例如 9103），另外排除。
_TDR_PREFIX = "91"


class SchemaError(ValueError):
    """資料不符合格式。"""


def is_common_stock(stock_id: object) -> bool:
    """是不是普通股代號：四碼數字、第一碼 1～9、不是 91 開頭。

    排除 00 開頭的 ETF、91 開頭的 TDR、六碼的權證和 ETF、帶字母的特別股。
    """
    s = str(stock_id).strip()
    return _COMMON_RE.fullmatch(s) is not None and not s.startswith(_TDR_PREFIX)


def common_stock_mask(stock_ids: Iterable[object]) -> np.ndarray:
    """向量版的 `is_common_stock`，回傳 bool 陣列。先對不重複的代號算一次再對回去。"""
    if isinstance(stock_ids, (pd.Series, pd.Index, np.ndarray)):
        arr = np.asarray(stock_ids, dtype=object)
    else:
        arr = np.asarray(list(stock_ids), dtype=object)
    ids = pd.Series(arr)
    if len(ids) == 0:
        return np.zeros(0, dtype=bool)
    codes, uniques = pd.factorize(ids)
    flags = np.array([is_common_stock(u) for u in uniques], dtype=bool)
    out = np.zeros(len(ids), dtype=bool)
    valid = codes >= 0
    out[valid] = flags[codes[valid]]
    return out


def _examples(df: pd.DataFrame, mask: np.ndarray | pd.Series, cols: Sequence[str], k: int = 5) -> str:
    """不合格的前幾列，放進錯誤訊息。"""
    m = np.asarray(mask, dtype=bool)
    sub = df.loc[m, [c for c in cols if c in df.columns]].head(k)
    return sub.to_string(index=False)


def _require_columns(df: pd.DataFrame, cols: Sequence[str], name: str) -> None:
    if not isinstance(df, pd.DataFrame):
        raise SchemaError(f"{name} 要是 pd.DataFrame，拿到 {type(df).__name__}")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} 少了欄：{missing}")


def coerce_dates(values: pd.Series, name: str) -> pd.Series:
    """轉成 `datetime64[ns]` 的日期。有時區、有時間、有缺值都丟 `SchemaError`。"""
    try:
        d = pd.to_datetime(values)
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"{name} 無法轉成日期：{exc}") from exc
    if isinstance(d.dtype, pd.DatetimeTZDtype):
        raise SchemaError(f"{name} 不能有時區（要用台北的日期，無時區）")
    d = d.astype("datetime64[ns]")
    if d.isna().any():
        raise SchemaError(f"{name} 有缺值")
    if (d != d.dt.normalize()).any():
        raise SchemaError(f"{name} 只能是日期，不能有時間")
    return d


def coerce_ids(values: pd.Series, name: str) -> pd.Series:
    """轉成字串代號並去掉前後空白。浮點數代號（例如 2330.0）和缺值丟 `SchemaError`。"""
    if values.isna().any():
        raise SchemaError(f"{name} 有缺值")
    if pd.api.types.is_float_dtype(values.dtype):
        raise SchemaError(f"{name} 不能是浮點數（會變成 '2330.0'），請先轉成字串")
    return values.astype(str).str.strip()


def _coerce_float(values: pd.Series, name: str) -> pd.Series:
    try:
        out = pd.to_numeric(values, errors="raise")
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"{name} 不是數字：{exc}") from exc
    arr = pd.Series(out).to_numpy(dtype=np.float64, na_value=np.nan)
    return pd.Series(arr, index=values.index, name=values.name)


def _check_unique(df: pd.DataFrame, keys: list[str], name: str) -> None:
    dup = df.duplicated(keys, keep=False).to_numpy()
    if dup.any():
        raise SchemaError(f"{name} 的 {tuple(keys)} 有重複，例如：\n{_examples(df, dup, keys)}")


def as_datetime_index(dates: object) -> pd.DatetimeIndex:
    """把一個日期、一串日期或 DatetimeIndex 轉成 `datetime64[ns]` 的 DatetimeIndex（保留順序）。"""
    if isinstance(dates, pd.DatetimeIndex):
        idx = dates
    else:
        if np.ndim(dates) == 0:
            dates = [dates]
        idx = pd.DatetimeIndex(pd.to_datetime(dates))
    if idx.tz is not None:
        raise ValueError("日期不能有時區")
    return idx.as_unit("ns")


def validate_calendar(calendar: object) -> pd.DatetimeIndex:
    """檢查交易日曆：日期、沒有時間、不重複。回傳排序好的 `datetime64[ns]` DatetimeIndex。"""
    try:
        cal = as_datetime_index(calendar)
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"calendar 無法轉成日期：{exc}") from exc
    if cal.hasnans:
        raise SchemaError("calendar 有缺值")
    if not (cal == cal.normalize()).all():
        raise SchemaError("calendar 只能是日期，不能有時間")
    if cal.has_duplicates:
        raise SchemaError("calendar 有重複的日期")
    cal = cal.sort_values()
    return pd.DatetimeIndex(cal, name="date")


def validate_panel(df: pd.DataFrame) -> pd.DataFrame:
    """檢查個股日 K，回傳整理好的新表。

    檢查：必要欄、`date` 是日期、`stock_id` 是字串、`market` 是 twse/tpex、價量是數字、
    `(date, stock_id)` 唯一、開高低收都大於 0、`high ≥ max(open, close)`、`low ≤ min(open, close)`、
    量和金額不是負的、`ref_price` 有值時大於 0。
    整理：按 `(date, stock_id)` 排序、RangeIndex；`ref_price` 的缺值用同一檔前一列的 `close` 補
    （等於那天沒有除權息事件），每檔第一列沒有前一列，維持缺值。多的欄保留在後面。
    """
    _require_columns(df, PANEL_COLS, "panel")
    out = df.copy()
    out["date"] = coerce_dates(out["date"], "panel.date")
    out["stock_id"] = coerce_ids(out["stock_id"], "panel.stock_id")
    if out["market"].isna().any():
        raise SchemaError("panel.market 有缺值")
    out["market"] = out["market"].astype(str).str.strip().str.lower()
    bad_market = ~out["market"].isin(MARKETS).to_numpy()
    if bad_market.any():
        raise SchemaError(f"panel.market 只能是 {MARKETS}，例如：\n{_examples(out, bad_market, ['date', 'stock_id', 'market'])}")
    for c in ("open", "high", "low", "close", "volume", "amount", "ref_price"):
        out[c] = _coerce_float(out[c], f"panel.{c}")
    for c in ("open", "high", "low", "close", "volume", "amount"):
        bad = ~np.isfinite(out[c].to_numpy())
        if bad.any():
            raise SchemaError(f"panel.{c} 有缺值或無限大，例如：\n{_examples(out, bad, ['date', 'stock_id', c])}")
    cols = list(PANEL_COLS) + [c for c in out.columns if c not in PANEL_COLS]
    out = out[cols].sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    _check_unique(out, ["date", "stock_id"], "panel")

    o = out["open"].to_numpy()
    h = out["high"].to_numpy()
    lo = out["low"].to_numpy()
    c = out["close"].to_numpy()
    show = ["date", "stock_id", "open", "high", "low", "close"]
    nonpos = (o <= 0) | (h <= 0) | (lo <= 0) | (c <= 0)
    if nonpos.any():
        raise SchemaError(f"panel 的開高低收要大於 0，例如：\n{_examples(out, nonpos, show)}")
    tol = 1e-9 * np.maximum(1.0, np.abs(h))
    bad_high = h + tol < np.maximum(o, c)
    if bad_high.any():
        raise SchemaError(f"panel 的 high 小於 max(open, close)，例如：\n{_examples(out, bad_high, show)}")
    tol = 1e-9 * np.maximum(1.0, np.abs(lo))
    bad_low = lo - tol > np.minimum(o, c)
    if bad_low.any():
        raise SchemaError(f"panel 的 low 大於 min(open, close)，例如：\n{_examples(out, bad_low, show)}")
    neg = (out["volume"].to_numpy() < 0) | (out["amount"].to_numpy() < 0)
    if neg.any():
        raise SchemaError(f"panel 的 volume、amount 不能是負的，例如：\n{_examples(out, neg, ['date', 'stock_id', 'volume', 'amount'])}")

    ref = out["ref_price"].to_numpy()
    bad_ref = np.isfinite(ref) & (ref <= 0)
    bad_ref |= np.isinf(ref)
    if bad_ref.any():
        raise SchemaError(f"panel.ref_price 有值時要大於 0，例如：\n{_examples(out, bad_ref, ['date', 'stock_id', 'ref_price'])}")
    prev_close = out.groupby("stock_id", sort=False)["close"].shift(1)
    out["ref_price"] = out["ref_price"].fillna(prev_close)
    return out


def validate_us(df: pd.DataFrame) -> pd.DataFrame:
    """檢查美股指數日 K。`us_date` 是美國當地交易日。按 `(us_date, symbol)` 排序。"""
    _require_columns(df, US_COLS, "us_daily")
    out = df.copy()
    out["us_date"] = coerce_dates(out["us_date"], "us_daily.us_date")
    if out["symbol"].isna().any():
        raise SchemaError("us_daily.symbol 有缺值")
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["close"] = _coerce_float(out["close"], "us_daily.close")
    c = out["close"].to_numpy()
    bad = ~np.isfinite(c) | (c <= 0)
    if bad.any():
        raise SchemaError(f"us_daily.close 要是大於 0 的數字，例如：\n{_examples(out, bad, list(US_COLS))}")
    cols = list(US_COLS) + [x for x in out.columns if x not in US_COLS]
    out = out[cols].sort_values(["us_date", "symbol"], kind="mergesort").reset_index(drop=True)
    _check_unique(out, ["us_date", "symbol"], "us_daily")
    return out


def validate_inst(df: pd.DataFrame) -> pd.DataFrame:
    """檢查三大法人買賣超（股數）。缺值可以（當成那天不知道）。按 `(date, stock_id)` 排序。"""
    _require_columns(df, INST_COLS, "inst_daily")
    out = df.copy()
    out["date"] = coerce_dates(out["date"], "inst_daily.date")
    out["stock_id"] = coerce_ids(out["stock_id"], "inst_daily.stock_id")
    for c in ("foreign_net", "trust_net", "dealer_net"):
        out[c] = _coerce_float(out[c], f"inst_daily.{c}")
        bad = np.isinf(out[c].to_numpy())
        if bad.any():
            raise SchemaError(f"inst_daily.{c} 有無限大，例如：\n{_examples(out, bad, ['date', 'stock_id', c])}")
    cols = list(INST_COLS) + [x for x in out.columns if x not in INST_COLS]
    out = out[cols].sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    _check_unique(out, ["date", "stock_id"], "inst_daily")
    return out


def validate_margin(df: pd.DataFrame) -> pd.DataFrame:
    """檢查融資餘額（張或股都可以，只算變化率）。缺值可以，有值時不能是負的。"""
    _require_columns(df, MARGIN_COLS, "margin_daily")
    out = df.copy()
    out["date"] = coerce_dates(out["date"], "margin_daily.date")
    out["stock_id"] = coerce_ids(out["stock_id"], "margin_daily.stock_id")
    out["margin_balance"] = _coerce_float(out["margin_balance"], "margin_daily.margin_balance")
    b = out["margin_balance"].to_numpy()
    bad = np.isinf(b) | (np.isfinite(b) & (b < 0))
    if bad.any():
        raise SchemaError(f"margin_daily.margin_balance 不能是負的或無限大，例如：\n{_examples(out, bad, list(MARGIN_COLS))}")
    cols = list(MARGIN_COLS) + [x for x in out.columns if x not in MARGIN_COLS]
    out = out[cols].sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    _check_unique(out, ["date", "stock_id"], "margin_daily")
    return out


def normalize_keys(df: pd.DataFrame, date_col: str = "date", id_col: str | None = "stock_id") -> pd.DataFrame:
    """輕量版的整理：只把日期轉成 `datetime64[ns]`、代號轉成字串，回傳新表。

    給內部函式用，避免每一步都做完整檢查。不排序、不改 index。
    """
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col]).astype("datetime64[ns]")
    if id_col is not None:
        out[id_col] = out[id_col].astype(str)
    return out


def stock_date_order(stock_ids: object, dates: object) -> tuple[np.ndarray, np.ndarray]:
    """按 (stock_id, date) 排序的位置和「每檔第一列」標記。

    回傳 `(order, first)`：`order` 是原本的位置（0 起算），照它取值後同一檔連在一起、日期遞增；
    `first[k]` 表示排序後第 k 列是那一檔的第一列。代號的先後不是字母順序（用 factorize），
    只保證同一檔連續。(stock_id, date) 重複時丟 `ValueError`。
    """
    codes, _ = pd.factorize(pd.Series(np.asarray(stock_ids, dtype=object)))
    if (codes < 0).any():
        raise ValueError("stock_id 有缺值")
    d = np.asarray(dates).astype("datetime64[ns]").astype(np.int64)
    order = np.lexsort((d, codes))
    n = len(order)
    first = np.ones(n, dtype=bool)
    if n > 1:
        cs = codes[order]
        ds = d[order]
        first[1:] = cs[1:] != cs[:-1]
        dup = (~first[1:]) & (ds[1:] == ds[:-1])
        if dup.any():
            k = int(np.flatnonzero(dup)[0]) + 1
            pos = int(order[k])
            raise ValueError(f"(stock_id, date) 有重複，例如第 {pos} 列")
    return order, first
