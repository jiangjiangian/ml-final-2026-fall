"""對齊協變量：每個要預測的台股交易日 t，只用 t 開盤前已經知道的資訊。

時間規則：
- i 是 t 之前最後一個台股交易日（`calendar` 裡 t 的前一個）。
- 個股的價量、法人（d 日約 16:30 公布）、融資（d 日約 21:30 公布）都只用 `date ≤ i`，
  而且只取 i 那一列；i 那天沒有列就是 NaN，不往前找。
- 美股：美國 d 日那根在台北 d+1 日約 05:00 收完，早於 t 的 09:00。t 用 `us_date < t`
  （日曆日比較）的最後一根。
- t 的開盤、收盤、成交量、跳空、漲跌停都不是輸入。

標準化：個股協變量用同一個 t、股票池內的橫斷面 rank-gauss；市場協變量用以 t 為索引、
只含 ≤ t 已知值的滾動 z-score。兩者都沒有要 fit 的參數。
"""

from __future__ import annotations

import re
import warnings
from typing import Sequence

import numpy as np
import pandas as pd
from scipy.special import ndtri

from ..config import DataConfig
from .adjust import _limit_flags_sorted, _log_returns_sorted, _scatter, _Sorted, group_rolling_sum, group_shift, signed_streak
from .schema import (
    INST_COLS,
    MARGIN_COLS,
    as_datetime_index,
    common_stock_mask,
    normalize_keys,
    stock_date_order,
    validate_calendar,
    validate_us,
)
from .universe import build_universe

STOCK_STATE_COLS: tuple[str, ...] = (
    "ret_cc_i",
    "ret_gap_i",
    "ret_oc_i",
    "ret_hl_i",
    "close_at_up_i",
    "close_at_down_i",
    "limit_streak_i",
    "beta_i",
    "amount_rank_i",
)
INST_FEATURE_COLS: tuple[str, ...] = ("foreign_ratio_i", "trust_streak_i", "dealer_ratio_i")
MARGIN_FEATURE_COLS: tuple[str, ...] = ("margin_chg_i", "margin_chg5_i")
STOCK_COV_BASE_COLS: tuple[str, ...] = STOCK_STATE_COLS + INST_FEATURE_COLS + MARGIN_FEATURE_COLS
TW_MARKET_COLS: tuple[str, ...] = (
    "tw_ret_cc_i",
    "tw_ret_gap_i",
    "tw_ret_oc_i",
    "tw_ret_cc5_i",
    "tw_up_frac_i",
    "tw_down_frac_i",
)

# 每列特徵在內部表的欄名，對到輸出的 `<名稱>_i`。
_STATE_SRC: tuple[str, ...] = tuple(c[:-2] for c in STOCK_STATE_COLS)
# 算全市場等權報酬時，把單日對數報酬裁在這個範圍（新上市前幾天沒有漲跌幅限制）。
_MARKET_RET_CLIP = 0.2


def us_symbol_name(symbol: str) -> str:
    """美股代號轉成欄名用的短名：`^SOX` → `sox`、`^IXIC` → `ixic`。"""
    name = re.sub(r"[^0-9a-z]+", "_", str(symbol).lower()).strip("_")
    if not name:
        raise ValueError(f"無法從 {symbol!r} 取欄名")
    return name


def us_feature_cols(symbols: Sequence[str]) -> list[str]:
    """`align_us_overnight` 的輸出欄：每個 symbol 的 `_ret`、`_ret5`，最後是 `us_stale_days`。"""
    cols: list[str] = []
    for sym in symbols:
        name = us_symbol_name(sym)
        cols += [f"us_{name}_ret", f"us_{name}_ret5"]
    cols.append("us_stale_days")
    return cols


def stock_cov_columns() -> list[str]:
    """`build_covariates` 回傳的 `stock_cov` 欄，順序固定：14 個特徵，再 14 個 `_isna`。"""
    return list(STOCK_COV_BASE_COLS) + [f"{c}_isna" for c in STOCK_COV_BASE_COLS]


def market_cov_columns(symbols: Sequence[str]) -> list[str]:
    """`build_covariates` 回傳的 `market_cov` 欄，順序固定：美股欄，再台股大盤欄。"""
    return us_feature_cols(symbols) + list(TW_MARKET_COLS)


def prev_trading_day(calendar: object, dates: object) -> pd.DatetimeIndex:
    """每個 t 的 i（calendar 裡 t 的前一個交易日），順序和 `dates` 一樣。

    t 不在 calendar 裡丟 `ValueError`。t 是 calendar 的第一天（沒有 i）也丟 `ValueError`。
    """
    cal = validate_calendar(calendar)
    cal_v = cal.to_numpy()
    d = as_datetime_index(dates).to_numpy()
    if len(d) == 0:
        return pd.DatetimeIndex([], dtype="datetime64[ns]")
    if len(cal_v) == 0:
        raise ValueError("calendar 是空的")
    pos = np.searchsorted(cal_v, d, side="left")
    in_cal = pos < len(cal_v)
    in_cal[in_cal] = cal_v[pos[in_cal]] == d[in_cal]
    if not in_cal.all():
        bad = pd.DatetimeIndex(d[~in_cal][:5])
        raise ValueError(f"這些 t 不是 calendar 裡的交易日：{list(bad.strftime('%Y-%m-%d'))}")
    if (pos == 0).any():
        raise ValueError(f"t = {pd.Timestamp(cal_v[0]).date()} 是 calendar 的第一天，沒有前一個交易日")
    return pd.DatetimeIndex(cal_v[pos - 1])


def _pairs(calendar: pd.DatetimeIndex, target_dates: object) -> pd.DataFrame:
    """不重複的 (t, i) 表，欄 `date`（t）、`i_date`。"""
    t = as_datetime_index(target_dates)
    t = pd.DatetimeIndex(np.unique(t.to_numpy()))
    i = prev_trading_day(calendar, t)
    return pd.DataFrame({"date": t.to_numpy(), "i_date": i.to_numpy()})


def _keys_at_i(pairs: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """(t, stock_id, i_date)：每個 t，`rows` 裡在 i 那天有列的股票。按 (date, stock_id) 排序。"""
    right = rows[["date", "stock_id"]].rename(columns={"date": "i_date"})
    keys = pairs.merge(right, on="i_date", how="inner")
    keys = keys[["date", "stock_id", "i_date"]].sort_values(["date", "stock_id"], kind="mergesort")
    return keys.reset_index(drop=True)


def _attach(keys: pd.DataFrame, rows: pd.DataFrame, src_cols: Sequence[str], out_cols: Sequence[str]) -> pd.DataFrame:
    """把 `rows` 在 (i_date, stock_id) 的值接到 `keys` 上。沒有那一列是 NaN。index 和 `keys` 一樣。"""
    rename = {"date": "i_date"}
    rename.update({s: o for s, o in zip(src_cols, out_cols)})
    right = rows[["date", "stock_id", *src_cols]].rename(columns=rename)
    merged = keys[["i_date", "stock_id"]].merge(right, on=["i_date", "stock_id"], how="left", validate="many_to_one")
    out = merged[list(out_cols)]
    out.index = keys.index
    return out


def _with_index(keys: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
    idx = pd.MultiIndex.from_arrays([keys["date"].to_numpy(), keys["stock_id"].to_numpy(dtype=object)], names=["date", "stock_id"])
    out = feat.copy()
    out.index = idx
    return out


# ---------- 每列（每檔每天）的狀態 ----------


def _row_state(panel: pd.DataFrame, cfg: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全部列的個股狀態，和每天的全市場統計。

    回傳 `(rows, market)`：
    - `rows` 欄 `date, stock_id, volume, ret_cc, ret_gap, ret_oc, ret_hl, close_at_up, close_at_down,
      limit_streak, beta, amount_rank`，每列是那一天收盤後就知道的值。
    - `market` 以日期為 index，欄 `tw_ret_cc, tw_ret_gap, tw_ret_oc, tw_up_frac, tw_down_frac`：
      普通股的等權平均（報酬先裁在 ±0.2）、收在漲停和跌停的比例。
    """
    s = _Sorted(panel)
    r = _log_returns_sorted(s)
    f = _limit_flags_sorted(s, cfg)
    id_codes, id_uniques = pd.factorize(panel["stock_id"].astype(str))
    ids = np.asarray(id_uniques, dtype=object)[id_codes][s.order]
    common = common_stock_mask(ids)
    dates = s.dates

    def _clip(x: np.ndarray) -> np.ndarray:
        return np.clip(x, -_MARKET_RET_CLIP, _MARKET_RET_CLIP)

    mk = pd.DataFrame(
        {
            "date": dates[common],
            "tw_ret_cc": _clip(r["ret_cc"][common]),
            "tw_ret_gap": _clip(r["ret_gap"][common]),
            "tw_ret_oc": _clip(r["ret_oc"][common]),
            "tw_up_frac": f["close_at_up"][common].astype(np.float64),
            "tw_down_frac": f["close_at_down"][common].astype(np.float64),
        }
    )
    market = mk.groupby("date", sort=True).mean()
    market.index = pd.DatetimeIndex(market.index).as_unit("ns")
    market.index.name = "date"

    # beta：個股 ret_cc 對同一天全市場等權 ret_cc，滾動 beta_window 列，視窗結束在這一列。
    y = market["tw_ret_cc"].reindex(pd.DatetimeIndex(dates)).to_numpy(dtype=np.float64)
    x = r["ret_cc"]
    valid = np.isfinite(x) & np.isfinite(y)
    xv = np.where(valid, x, 0.0)
    yv = np.where(valid, y, 0.0)
    w = int(cfg.beta_window)
    cnt = group_rolling_sum(valid.astype(np.float64), s.first, w)
    sx = group_rolling_sum(xv, s.first, w)
    sy = group_rolling_sum(yv, s.first, w)
    sxy = group_rolling_sum(xv * yv, s.first, w)
    syy = group_rolling_sum(yv * yv, s.first, w)
    min_periods = max(2, w // 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = sxy - sx * sy / cnt
        var = syy - sy * sy / cnt
        beta = np.where((cnt >= min_periods) & (var > 1e-12), cov / var, np.nan)

    amount_rank = pd.Series(s.amount).groupby(dates).rank(method="average", pct=True).to_numpy(dtype=np.float64)

    rows = pd.DataFrame(
        {
            "date": dates,
            "stock_id": ids,
            "volume": s.volume,
            "ret_cc": r["ret_cc"],
            "ret_gap": r["ret_gap"],
            "ret_oc": r["ret_oc"],
            "ret_hl": r["ret_hl"],
            "close_at_up": f["close_at_up"].astype(np.float64),
            "close_at_down": f["close_at_down"].astype(np.float64),
            "limit_streak": f["limit_streak"].astype(np.float64),
            "beta": beta,
            "amount_rank": amount_rank,
        }
    )
    return rows, market


def _inst_rows(inst_daily: pd.DataFrame, panel_keys: pd.DataFrame) -> pd.DataFrame:
    """法人表對到 panel 的每一列 `(date, stock_id)`，加上 `trust_streak`。

    `trust_streak`：投信連續買超天數為正、連續賣超為負，0 的那天歸零。連續天數按這一檔在 panel 有列的
    交易日算：有成交但沒有法人列（或 `trust_net` 缺值）的那天當作 0 歸零，那天的 streak 是 NaN；
    停牌（panel 沒有列）不中斷。回傳的列就是 `panel_keys` 去重後的列，法人欄沒有對到的是 NaN；
    法人表裡 panel 沒有的 `(date, stock_id)` 用不到，直接丟掉。法人表同一個 `(date, stock_id)` 重複時丟錯。
    """
    missing = [c for c in INST_COLS if c not in inst_daily.columns]
    if missing:
        raise ValueError(f"inst_daily 少了欄：{missing}")
    inst = normalize_keys(inst_daily[list(INST_COLS)])
    for c in ("foreign_net", "trust_net", "dealer_net"):
        inst[c] = pd.to_numeric(inst[c], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    base = normalize_keys(panel_keys[["date", "stock_id"]]).drop_duplicates(["date", "stock_id"])
    rows = base.merge(inst, on=["date", "stock_id"], how="left", validate="many_to_one").reset_index(drop=True)
    order, first = stock_date_order(rows["stock_id"], rows["date"])
    tn = rows["trust_net"].to_numpy(dtype=np.float64, na_value=np.nan)[order]
    known = np.isfinite(tn)
    state = np.sign(np.where(known, tn, 0.0)).astype(np.int64)
    streak = signed_streak(state, first).astype(np.float64)
    streak[~known] = np.nan
    rows["trust_streak"] = _scatter(order, streak)
    return rows


def _inst_at_keys(keys: pd.DataFrame, inst: pd.DataFrame, volume_i: np.ndarray) -> pd.DataFrame:
    m = _attach(keys, inst, ["foreign_net", "trust_streak", "dealer_net"], ["foreign_net", "trust_streak", "dealer_net"])
    vol = np.asarray(volume_i, dtype=np.float64)
    ok = np.isfinite(vol) & (vol > 0)
    safe = np.where(ok, vol, 1.0)
    fn = m["foreign_net"].to_numpy(dtype=np.float64)
    dn = m["dealer_net"].to_numpy(dtype=np.float64)
    out = pd.DataFrame(
        {
            "foreign_ratio_i": np.where(ok, fn / safe, np.nan),
            "trust_streak_i": m["trust_streak"].to_numpy(dtype=np.float64),
            "dealer_ratio_i": np.where(ok, dn / safe, np.nan),
        },
        index=keys.index,
    )
    return out


def _margin_rows(margin_daily: pd.DataFrame) -> pd.DataFrame:
    """融資表加上 `margin_chg`（對前一列）和 `margin_chg5`（對前 5 列）的變化率。前一列是 0 或缺值時 NaN。"""
    missing = [c for c in MARGIN_COLS if c not in margin_daily.columns]
    if missing:
        raise ValueError(f"margin_daily 少了欄：{missing}")
    m = normalize_keys(margin_daily[list(MARGIN_COLS)]).reset_index(drop=True)
    b_all = pd.to_numeric(m["margin_balance"], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    order, first = stock_date_order(m["stock_id"], m["date"])
    b = b_all[order]
    out: dict[str, np.ndarray] = {}
    for name, k in (("margin_chg", 1), ("margin_chg5", 5)):
        prev = group_shift(b, first, k)
        ok = np.isfinite(prev) & (prev > 0) & np.isfinite(b)
        chg = np.where(ok, b / np.where(ok, prev, 1.0) - 1.0, np.nan)
        out[name] = _scatter(order, chg)
    m["margin_chg"] = out["margin_chg"]
    m["margin_chg5"] = out["margin_chg5"]
    return m


# ---------- 公開的特徵函式 ----------


def align_us_overnight(
    us_daily: pd.DataFrame,
    target_dates: object,
    symbols: Sequence[str] = ("^SOX", "^IXIC"),
) -> pd.DataFrame:
    """美股隔夜特徵，索引 t（名稱 `date`，順序和 `target_dates` 一樣）。

    對每個 symbol，取美國當地日期 `us_date < t`（日曆日比較）的最後一根 j：
    `us_<name>_ret = log(close_j / close_{j−1})`、`us_<name>_ret5 = log(close_j / close_{j−5})`（5 根累計）。
    `us_stale_days = (t − us_date_j).days`，用 `^IXIC` 的日期，沒有 `^IXIC` 的資料就用第一個有資料的 symbol。
    週二的 t 用美國週一；週一的 t 用美國週五（3 天）；美國週一放假時週二的 t 用週五（4 天）。

    為什麼 `<` 是對的：美國 d 日收盤在台北 d+1 日約 05:00，早於 t = d+1 的 09:00 開盤。
    即時抓取時不得在台北 22:30 之後抓（那時美國 t 當天已經開盤，抓到的會是盤中的價）。
    用 `np.searchsorted(..., side="left")` 實作嚴格小於。
    """
    us = validate_us(us_daily)
    t = as_datetime_index(target_dates)
    t_v = t.to_numpy()
    n = len(t_v)
    data: dict[str, np.ndarray] = {}
    stale_by_symbol: dict[str, np.ndarray] = {}
    for sym in symbols:
        name = us_symbol_name(sym)
        sub = us[us["symbol"] == sym]
        ret = np.full(n, np.nan)
        ret5 = np.full(n, np.nan)
        stale = np.full(n, np.nan)
        if len(sub) == 0:
            warnings.warn(f"us_daily 沒有 {sym} 的資料，相關欄全是 NaN", stacklevel=2)
        else:
            d = sub["us_date"].to_numpy(dtype="datetime64[ns]")
            logc = np.log(sub["close"].to_numpy(dtype=np.float64))
            j = np.searchsorted(d, t_v, side="left") - 1
            ok1 = j >= 1
            ret[ok1] = logc[j[ok1]] - logc[j[ok1] - 1]
            ok5 = j >= 5
            ret5[ok5] = logc[j[ok5]] - logc[j[ok5] - 5]
            ok0 = j >= 0
            stale[ok0] = (t_v[ok0] - d[j[ok0]]) / np.timedelta64(1, "D")
            stale_by_symbol[sym] = stale
        data[f"us_{name}_ret"] = ret
        data[f"us_{name}_ret5"] = ret5
    if "^IXIC" in stale_by_symbol:
        data["us_stale_days"] = stale_by_symbol["^IXIC"]
    else:
        chosen = next((stale_by_symbol[s] for s in symbols if s in stale_by_symbol), None)
        data["us_stale_days"] = chosen if chosen is not None else np.full(n, np.nan)
    out = pd.DataFrame(data, index=pd.DatetimeIndex(t_v, name="date"))
    return out[us_feature_cols(symbols)]


def institutional_features(
    inst_daily: pd.DataFrame,
    panel: pd.DataFrame,
    target_dates: object,
    calendar: object,
) -> pd.DataFrame:
    """法人特徵，索引 `(date=t, stock_id)`，每個 t 包含 i 那天在 `panel` 有列的股票。

    `foreign_ratio_i = foreign_net_i / volume_i`（i 日成交量是 0 或缺值時 NaN；單位都是股）。
    `trust_streak_i`：投信連續買超天數為正、連續賣超為負，0 的那天歸零，截至 i。按這檔在 panel 有列的
    交易日算：有成交但沒有法人列的那天歸零，停牌（沒有列）不中斷。
    `dealer_ratio_i = dealer_net_i / volume_i`。
    i 那天沒有法人列就是 NaN，不往前找。法人 d 日約 16:30 公布，i 的值在 t 開盤前已知。
    """
    cal = validate_calendar(calendar)
    pairs = _pairs(cal, target_dates)
    pv = normalize_keys(panel[["date", "stock_id", "volume"]])
    pv["volume"] = pd.to_numeric(pv["volume"], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    keys = _keys_at_i(pairs, pv)
    vol = _attach(keys, pv, ["volume"], ["volume_i"])["volume_i"].to_numpy(dtype=np.float64)
    feat = _inst_at_keys(keys, _inst_rows(inst_daily, pv), vol)
    return _with_index(keys, feat)


def margin_features(margin_daily: pd.DataFrame, target_dates: object, calendar: object) -> pd.DataFrame:
    """融資特徵，索引 `(date=t, stock_id)`，每個 t 包含 i 那天在融資表有列的股票。

    `margin_chg_i = balance_i / balance_{i 的前一列} − 1`，`margin_chg5_i` 是對前 5 列。
    融資 d 日約 21:30 公布，i 的值在 t 開盤前已知。i 那天沒有列就不在結果裡（接到股票池時是 NaN）。
    """
    cal = validate_calendar(calendar)
    pairs = _pairs(cal, target_dates)
    m = _margin_rows(margin_daily)
    keys = _keys_at_i(pairs, m)
    feat = _attach(keys, m, ["margin_chg", "margin_chg5"], list(MARGIN_FEATURE_COLS))
    return _with_index(keys, feat)


def stock_state_features(
    panel: pd.DataFrame,
    target_dates: object,
    calendar: object,
    cfg: DataConfig,
) -> pd.DataFrame:
    """個股截至 i 的狀態，索引 `(date=t, stock_id)`，每個 t 包含 i 那天有列的股票。

    欄：`ret_cc_i, ret_gap_i, ret_oc_i, ret_hl_i`（i 那天的對數報酬，見 `adjust.log_returns`）、
    `close_at_up_i, close_at_down_i`（0/1）、`limit_streak_i`、
    `beta_i`（`beta_window` 列的個股 `ret_cc` 對同一天普通股等權 `ret_cc` 的滾動 beta，視窗結束在 i，
    至少要 `beta_window // 2` 列，否則 NaN）、`amount_rank_i`（i 那天成交金額在當天所有列裡的百分位）。
    """
    cal = validate_calendar(calendar)
    pairs = _pairs(cal, target_dates)
    rows, _ = _row_state(panel, cfg)
    keys = _keys_at_i(pairs, rows)
    feat = _attach(keys, rows, _STATE_SRC, STOCK_STATE_COLS)
    return _with_index(keys, feat)


def cross_sectional_rank_gauss(df: pd.DataFrame, cols: Sequence[str], by: str = "date") -> pd.DataFrame:
    """每天每欄做 rank-gauss：`rank(average) / (n + 1)` 再取常態分位數（`norm.ppf`）。

    `by` 可以是欄名或 index level 名。n 是那天那一欄不是 NaN 的個數。NaN（含 ±inf）保留到最後，
    另外加 `<col>_isna`（1.0 表示原本是 NaN），最後把 NaN 填 0。回傳新表，原本的其他欄保留，
    `_isna` 欄接在最後面。只用同一天的值，沒有時間方向的洩漏。
    """
    cols = list(cols)
    out = df.copy()
    if by in out.columns:
        keys = out[by].to_numpy()
    elif by in (out.index.names or []):
        keys = out.index.get_level_values(by).to_numpy()
    else:
        raise KeyError(f"找不到分組的欄或 index level：{by!r}")
    if len(cols) == 0:
        return out
    X = out[cols].astype(np.float64)
    X = X.replace([np.inf, -np.inf], np.nan)
    isna = X.isna().to_numpy()
    if len(X) == 0:
        for c in cols:
            out[c] = X[c].to_numpy()
        for c in cols:
            out[f"{c}_isna"] = np.zeros(0)
        return out
    g = X.groupby(keys, sort=False)
    R = g.rank(method="average").to_numpy(dtype=np.float64)
    N = g.transform("count").to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = ndtri(R / (N + 1.0))
    Z[isna | ~np.isfinite(Z)] = 0.0
    for k, c in enumerate(cols):
        out[c] = Z[:, k]
    for k, c in enumerate(cols):
        out[f"{c}_isna"] = isna[:, k].astype(np.float64)
    return out


def rolling_market_zscore(df: pd.DataFrame, window: int = 250, min_periods: int = 60) -> pd.DataFrame:
    """以 t 為索引的滾動 z-score：`(x − rolling_mean) / rolling_std`，視窗是到 t（含）為止的 `window` 列。

    t 那列的市場協變量在 t 開盤前已知，所以視窗含 t 不洩漏。不足 `min_periods` 個值、std 是 0、
    原本是 NaN 的位置都填 0。先按 index 排序。列數就是視窗，請傳連續的交易日。
    """
    x = df.sort_index().astype(np.float64)
    x = x.replace([np.inf, -np.inf], np.nan)
    roll = x.rolling(window, min_periods=min_periods)
    mean = roll.mean()
    std = roll.std()
    z = (x - mean) / std
    z = z.where(std > 1e-12, 0.0)
    z = z.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return z


def _market_covariates(
    us_daily: pd.DataFrame | None,
    market: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    cfg: DataConfig,
) -> pd.DataFrame:
    """整條 calendar（第二天起）的市場協變量，z-score 後回傳。結果和之後要哪幾天無關。"""
    t = calendar[1:]
    if us_daily is not None:
        us = align_us_overnight(us_daily, t, cfg.us_symbols)
    else:
        us = pd.DataFrame(np.nan, index=pd.DatetimeIndex(t, name="date"), columns=us_feature_cols(cfg.us_symbols))
    full = market.reindex(calendar)
    full["tw_ret_cc5"] = full["tw_ret_cc"].rolling(5, min_periods=5).sum()
    at_i = full.iloc[:-1]
    tw = pd.DataFrame(
        {
            "tw_ret_cc_i": at_i["tw_ret_cc"].to_numpy(dtype=np.float64),
            "tw_ret_gap_i": at_i["tw_ret_gap"].to_numpy(dtype=np.float64),
            "tw_ret_oc_i": at_i["tw_ret_oc"].to_numpy(dtype=np.float64),
            "tw_ret_cc5_i": at_i["tw_ret_cc5"].to_numpy(dtype=np.float64),
            "tw_up_frac_i": at_i["tw_up_frac"].to_numpy(dtype=np.float64),
            "tw_down_frac_i": at_i["tw_down_frac"].to_numpy(dtype=np.float64),
        },
        index=pd.DatetimeIndex(t, name="date"),
    )
    raw = pd.concat([us, tw], axis=1)
    raw = raw[market_cov_columns(cfg.us_symbols)]
    return rolling_market_zscore(raw, window=250, min_periods=60)


def build_covariates(
    panel: pd.DataFrame,
    us_daily: pd.DataFrame | None,
    inst_daily: pd.DataFrame | None,
    margin_daily: pd.DataFrame | None,
    target_dates: object,
    calendar: object,
    cfg: DataConfig,
    universe: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """建好模型要的協變量，回傳 `(stock_cov, market_cov)`。

    `stock_cov`：索引 `(date, stock_id)`，剛好是股票池在 `target_dates` 裡的每一組 (t, 股票)；
    欄見 `stock_cov_columns()`（14 個特徵再 14 個 `_isna`），已在同一個 t、股票池內 rank-gauss，float32、沒有 NaN。
    `market_cov`：索引 `date`（`target_dates` 排序去重），欄見 `market_cov_columns(cfg.us_symbols)`，
    已做滾動 250 天 z-score（`min_periods=60`），float32、沒有 NaN。z-score 用整條 calendar 算完再取，
    所以只要驗證期或只要訓練期，同一天的值都一樣。

    `universe`：`build_universe` 的結果；沒給就用 `build_universe(panel, calendar, cfg)` 算。
    `target_dates` 是 None 時用股票池的全部日期。`inst_daily`、`margin_daily`、`us_daily` 可以是 None，
    那些欄全 0（個股欄另有 `_isna = 1`）。
    """
    cal = validate_calendar(calendar)
    if universe is None:
        universe = build_universe(panel, cal, cfg)
    uni = normalize_keys(universe[["date", "stock_id"]])
    if target_dates is not None:
        t_all = pd.DatetimeIndex(np.unique(as_datetime_index(target_dates).to_numpy()), name="date")
        uni = uni[uni["date"].isin(t_all)]
    else:
        t_all = pd.DatetimeIndex(np.unique(uni["date"].to_numpy()), name="date")
    uni = uni.drop_duplicates(["date", "stock_id"]).sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    keys = uni.copy()
    keys["i_date"] = prev_trading_day(cal, keys["date"]).to_numpy()

    rows, market = _row_state(panel, cfg)
    state = _attach(keys, rows, [*_STATE_SRC, "volume"], [*STOCK_STATE_COLS, "volume_i"])
    if inst_daily is not None:
        inst = _inst_at_keys(keys, _inst_rows(inst_daily, rows), state["volume_i"].to_numpy(dtype=np.float64))
    else:
        inst = pd.DataFrame(np.nan, index=keys.index, columns=list(INST_FEATURE_COLS))
    if margin_daily is not None:
        margin = _attach(keys, _margin_rows(margin_daily), ["margin_chg", "margin_chg5"], list(MARGIN_FEATURE_COLS))
    else:
        margin = pd.DataFrame(np.nan, index=keys.index, columns=list(MARGIN_FEATURE_COLS))

    raw = pd.concat([keys[["date", "stock_id"]], state[list(STOCK_STATE_COLS)], inst, margin], axis=1)
    ranked = cross_sectional_rank_gauss(raw, STOCK_COV_BASE_COLS, by="date")
    stock_cov = _with_index(keys, ranked[stock_cov_columns()]).astype(np.float32)

    market_all = _market_covariates(us_daily, market, cal, cfg)
    market_cov = market_all.reindex(t_all).fillna(0.0).astype(np.float32)
    market_cov.index = pd.DatetimeIndex(t_all, name="date")
    return stock_cov, market_cov
