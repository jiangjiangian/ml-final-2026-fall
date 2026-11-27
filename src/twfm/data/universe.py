"""股票池：每個 t 可以拿來訓練和評估的股票，處理存活偏差。

規則（`build_universe`）：
1. 只收普通股（`schema.is_common_stock`）。
2. 名單每期換一次。`yearly`：Y 年的名單用「Y 年第一個交易日的前一個交易日」（就是 Y−1 年最後一個交易日，
   叫錨點）往回 `universe_lookback_days` 個交易日的成交金額總和排名，取前 `universe_size` 檔。
   `monthly` 一樣，錨點是上個月最後一個交易日。只用錨點（含）以前的資料。
   排名只收在視窗最後 20 個交易日內有成交、視窗內金額大於 0 的股票（錨點時已經知道停止交易的不收）。
   錨點不存在（calendar 的第一期）時那一期沒有名單。視窗超出 calendar 開頭時用現有的天數。
3. 名單裡的股票在 t 還要滿足：i 那天有列、i 的原始收盤 ≥ `min_close`、截至 i（含）至少有 `lookback` 列。
4. 不用「現在還在交易」或「最後一天的名單」篩。下市股在下市前照常進池。

注意：`yearly` 時 calendar 第一年沒有錨點，股票池從第二年才開始。假資料只有一年多的話，
用 `monthly` 或把切分放在有股票池的日期上。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import DataConfig
from .schema import common_stock_mask, normalize_keys, stock_date_order, validate_calendar

# 排名時要求在視窗最後這麼多個交易日內有成交。
_RECENT_DAYS = 20


def _period_keys(cal: pd.DatetimeIndex, refresh: str) -> np.ndarray:
    years = np.asarray(cal.year, dtype=np.int64)
    if refresh == "yearly":
        return years
    if refresh == "monthly":
        return years * 12 + (np.asarray(cal.month, dtype=np.int64) - 1)
    raise ValueError(f"universe_refresh 要是 'yearly' 或 'monthly'，拿到 {refresh!r}")


def _empty_universe() -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.Series([], dtype="datetime64[ns]"), "stock_id": pd.Series([], dtype=object)}
    )


def build_universe(panel: pd.DataFrame, calendar: object, cfg: DataConfig) -> pd.DataFrame:
    """每個可以當 t 的交易日一組股票。回傳欄 `date, stock_id`，按 (date, stock_id) 排序、RangeIndex。

    `date` 是 t。規則見模組說明。panel 的日期都要在 calendar 裡，否則丟 `ValueError`。
    calendar 比 panel 多一天時，panel 最後一天的下一個交易日也會有名單（給即時預測用，那天還沒有標籤）。
    """
    cal = validate_calendar(calendar)
    cal_v = cal.to_numpy()
    n_cal = len(cal_v)
    if n_cal < 2 or len(panel) == 0:
        return _empty_universe()

    p = normalize_keys(panel[["date", "stock_id", "close", "amount"]]).reset_index(drop=True)
    p = p.loc[common_stock_mask(p["stock_id"])].reset_index(drop=True)
    if len(p) == 0:
        return _empty_universe()

    d_v = p["date"].to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(cal_v, d_v, side="left")
    in_cal = pos < n_cal
    in_cal[in_cal] = cal_v[pos[in_cal]] == d_v[in_cal]
    if not in_cal.all():
        bad = pd.DatetimeIndex(np.unique(d_v[~in_cal])[:5])
        raise ValueError(f"panel 有不在 calendar 裡的日期：{list(bad.strftime('%Y-%m-%d'))}")

    codes, uniques = pd.factorize(p["stock_id"])
    uniq = np.asarray(uniques, dtype=object)
    n_stk = len(uniq)
    close = p["close"].to_numpy(dtype=np.float64, na_value=np.nan)
    amount = p["amount"].to_numpy(dtype=np.float64, na_value=np.nan)
    amount = np.where(np.isfinite(amount) & (amount > 0), amount, 0.0)

    # 每列是那一檔的第幾列（1 起算，日期遞增）。stock_date_order 也檢查 (stock_id, date) 不重複。
    order, first = stock_date_order(p["stock_id"], d_v)
    n = len(order)
    starts = np.maximum.accumulate(np.where(first, np.arange(n), 0))
    rownum = np.empty(n, dtype=np.int64)
    rownum[order] = np.arange(n) - starts + 1

    # 日期 × 股票的成交金額和有沒有成交，前面補一列 0 的累加和。
    amt = np.zeros((n_cal, n_stk), dtype=np.float64)
    amt[pos, codes] = amount
    cum_amt = np.zeros((n_cal + 1, n_stk), dtype=np.float64)
    np.cumsum(amt, axis=0, out=cum_amt[1:])
    del amt
    present = np.zeros((n_cal, n_stk), dtype=np.int64)
    present[pos, codes] = 1
    cum_present = np.zeros((n_cal + 1, n_stk), dtype=np.int64)
    np.cumsum(present, axis=0, dtype=np.int64, out=cum_present[1:])
    del present

    # 名字的排名，金額相同時用代號決定先後，結果才固定。
    name_rank = np.empty(n_stk, dtype=np.int64)
    name_rank[np.argsort(uniq.astype(str), kind="mergesort")] = np.arange(n_stk)

    keys = _period_keys(cal, cfg.universe_refresh)
    start_flag = np.ones(n_cal, dtype=bool)
    start_flag[1:] = keys[1:] != keys[:-1]
    period_id = np.cumsum(start_flag) - 1
    period_start = np.flatnonzero(start_flag)
    member = np.zeros((len(period_start), n_stk), dtype=bool)
    L = int(cfg.universe_lookback_days)
    recent = min(_RECENT_DAYS, L)
    for pid, s in enumerate(period_start):
        if s == 0:
            continue  # calendar 的第一期沒有錨點
        a = s - 1
        w0 = max(0, a - L + 1)
        sums = cum_amt[a + 1] - cum_amt[w0]
        r0 = max(w0, a - recent + 1)
        alive = (cum_present[a + 1] - cum_present[r0]) > 0
        cand = np.flatnonzero(alive & (sums > 0))
        if cand.size == 0:
            continue
        rank_order = np.lexsort((name_rank[cand], -sums[cand]))
        member[pid, cand[rank_order[: int(cfg.universe_size)]]] = True

    # 每一列當作 i，對應的 t 是 calendar 的下一天。
    t_pos = pos + 1
    ok = (t_pos < n_cal) & np.isfinite(close) & (close >= cfg.min_close) & (rownum >= int(cfg.lookback))
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return _empty_universe()
    keep = member[period_id[t_pos[idx]], codes[idx]]
    idx = idx[keep]
    out = pd.DataFrame({"date": cal_v[t_pos[idx]], "stock_id": uniq[codes[idx]]})
    out["date"] = out["date"].astype("datetime64[ns]")
    out = out.sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    return out


def universe_audit(universe: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """股票池的年度摘要。回傳欄 `year, n_days, n_stocks, n_delisted_later, avg_per_day, min_per_day, max_per_day`。

    `n_stocks`：那一年至少進池一天的股票數。`n_delisted_later`：其中在 panel 最後一天以前就沒有列的
    （之後下市或長期停牌）。用來確認下市股有進池，不是只留到現在還活著的。
    """
    cols = ["year", "n_days", "n_stocks", "n_delisted_later", "avg_per_day", "min_per_day", "max_per_day"]
    if len(universe) == 0:
        return pd.DataFrame({c: pd.Series([], dtype=np.float64) for c in cols})
    u = normalize_keys(universe[["date", "stock_id"]])
    p = normalize_keys(panel[["date", "stock_id"]])
    last = p.groupby("stock_id")["date"].max()
    end = p["date"].max()
    gone = set(last.index[last < end].astype(str))
    u["year"] = u["date"].dt.year
    u["gone"] = u["stock_id"].isin(gone)
    per_day = u.groupby("date").size()
    per_day_year = pd.Series(per_day.index.year, index=per_day.index)
    rows = []
    for year, sub in u.groupby("year", sort=True):
        counts = per_day[per_day_year == year]
        rows.append(
            {
                "year": int(year),
                "n_days": int(sub["date"].nunique()),
                "n_stocks": int(sub["stock_id"].nunique()),
                "n_delisted_later": int(sub.loc[sub["gone"], "stock_id"].nunique()),
                "avg_per_day": float(counts.mean()),
                "min_per_day": int(counts.min()),
                "max_per_day": int(counts.max()),
            }
        )
    return pd.DataFrame(rows, columns=cols)
