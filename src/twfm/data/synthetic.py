"""假資料：給測試和 smoke 用的小市場，涵蓋資料規則裡的每種情況。

`make_synthetic_market` 產生：
- 台股交易日曆：週一到週五，扣掉元旦、農曆年、228、清明、勞動節、國慶（台股假日）。
- 美股 `^SOX`、`^IXIC` 日 K：從台股第一天往前 60 天開始，扣掉美國假日（含週一的 MLK、總統日、
  Memorial Day、Labor Day，和耶穌受難日、感恩節），所以有 `us_stale_days` 是 4 的日子。
- 個股：四碼普通股，加 3 檔 ETF（`0050`、`0056`、`00878`，成交金額最大）和 1 檔 TDR（`9105`），
  後兩種要被股票池排除。有中途下市、上市晚、停牌幾天（沒有列）、低價股跨過 10 元、千元股（升降單位 5）。
- 除息（`ref_price < 前一天收盤`）、一次除權（參考價 = 前收 ÷ 1.1，量變多）、一次減資（參考價 = 前收 × 1.25）。
- 漲跌停：開盤就漲停（含連續幾天一字漲停）、開盤跌停、盤中衝到漲停或殺到跌停。價格都對齊升降單位、
  夾在漲跌停價之間。少數列的 `ref_price` 是缺值（那幾天沒有事件，缺值要用前一列收盤補）。
- 三大法人和融資餘額，各隨機少 2% 的列。

可學的訊號放在 t 的盤中報酬 `log(close_t / open_t)`，而且只用 t 開盤前看得到的值：
`+0.25 × beta × us_sox_ret`（美股隔夜 × beta）、`−0.2 × ret_gap_i`（前一天的跳空）、
`+0.04 × foreign_ratio_i`（前一天外資買超佔成交量）。理想的每日 IC 大約 0.1～0.15。
亂數全部來自 `numpy.random.default_rng(seed)`。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from ..config import DataConfig
from .adjust import limit_prices, tick_size
from .schema import validate_inst, validate_margin, validate_panel, validate_us

# 農曆正月初一（台股封關前後約一週不交易）。表外的年份用 2 月 1 日近似。
_LUNAR_NEW_YEAR: dict[int, str] = {
    2004: "2004-01-22",
    2005: "2005-02-09",
    2006: "2006-01-29",
    2007: "2007-02-18",
    2008: "2008-02-07",
    2009: "2009-01-26",
    2010: "2010-02-14",
    2011: "2011-02-03",
    2012: "2012-01-23",
    2013: "2013-02-10",
    2014: "2014-01-31",
    2015: "2015-02-19",
    2016: "2016-02-08",
    2017: "2017-01-28",
    2018: "2018-02-16",
    2019: "2019-02-05",
    2020: "2020-01-25",
    2021: "2021-02-12",
    2022: "2022-02-01",
    2023: "2023-01-22",
    2024: "2024-02-10",
    2025: "2025-01-29",
    2026: "2026-02-17",
    2027: "2027-02-06",
    2028: "2028-01-26",
}

ETF_IDS: tuple[str, ...] = ("0050", "0056", "00878")
TDR_IDS: tuple[str, ...] = ("9105",)


@dataclass
class SyntheticMarket:
    """假市場。前五個欄位和真資料的格式一樣（見 `schema`）。

    `panel` 已排序但沒有補 `ref_price` 的缺值（留給 `validate_panel` 或 `adjust` 處理）。
    `stock_info` 是每檔的真實參數（beta、波動、上市和最後交易日、是否下市、有沒有除息等），只給測試對答案。
    """

    panel: pd.DataFrame
    us_daily: pd.DataFrame
    inst_daily: pd.DataFrame
    margin_daily: pd.DataFrame
    calendar: pd.DatetimeIndex
    stock_info: pd.DataFrame = field(default_factory=pd.DataFrame)


# ---------- 日曆 ----------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """某月第 n 個星期幾（weekday：週一 0）。"""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    """某月最後一個星期幾。"""
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> dt.date:
    """復活節（格里曆，匿名演算法）。"""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _observed(day: dt.date) -> dt.date:
    """美國固定日期假日遇到週末時的補假：週六提前到週五，週日延到週一。"""
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def _us_holidays(years: Iterable[int]) -> set[pd.Timestamp]:
    """美股休市日（簡化版的 NYSE 規則）。"""
    out: set[dt.date] = set()
    for y in years:
        ny = dt.date(y, 1, 1)
        if ny.weekday() == 6:
            out.add(ny + dt.timedelta(days=1))
        elif ny.weekday() != 5:
            out.add(ny)
        out.add(_nth_weekday(y, 1, 0, 3))  # 金恩紀念日
        out.add(_nth_weekday(y, 2, 0, 3))  # 總統日
        out.add(_easter(y) - dt.timedelta(days=2))  # 耶穌受難日
        out.add(_last_weekday(y, 5, 0))  # 陣亡將士紀念日
        if y >= 2022:
            out.add(_observed(dt.date(y, 6, 19)))  # 六月節
        out.add(_observed(dt.date(y, 7, 4)))
        out.add(_nth_weekday(y, 9, 0, 1))  # 勞動節
        out.add(_nth_weekday(y, 11, 3, 4))  # 感恩節
        out.add(_observed(dt.date(y, 12, 25)))
    return {pd.Timestamp(d) for d in out}


def _tw_holidays(years: Iterable[int]) -> set[pd.Timestamp]:
    """台股休市日（簡化）：元旦、農曆年前後、228、清明、勞動節、國慶。"""
    out: set[dt.date] = set()
    for y in years:
        for m, d in ((1, 1), (2, 28), (4, 4), (5, 1), (10, 10)):
            out.add(dt.date(y, m, d))
        lny = pd.Timestamp(_LUNAR_NEW_YEAR.get(y, f"{y}-02-01")).date()
        for k in range(-3, 4):
            out.add(lny + dt.timedelta(days=k))
    return {pd.Timestamp(d) for d in out}


def _business_days(first: pd.Timestamp, last: pd.Timestamp, holidays: set[pd.Timestamp]) -> pd.DatetimeIndex:
    days = pd.bdate_range(first, last)
    days = days[~days.isin(list(holidays))]
    return pd.DatetimeIndex(days, name="date").as_unit("ns")


def _tw_calendar(start: str, n_days: int) -> pd.DatetimeIndex:
    first = pd.Timestamp(start).normalize()
    span_days = int(n_days * 1.6) + 60
    while True:
        last = first + pd.Timedelta(days=span_days)
        days = _business_days(first, last, _tw_holidays(range(first.year, last.year + 1)))
        if len(days) >= n_days:
            return days[:n_days]
        span_days *= 2


# ---------- 價格工具 ----------


def _round_tick(p: np.ndarray) -> np.ndarray:
    """四捨五入到升降單位。用取整後價格的級距再取一次，確保落在正確的級距。"""
    t = tick_size(p)
    r = np.round(p / t) * t
    t2 = tick_size(r)
    return np.round(np.round(r / t2) * t2, 2)


def _ceil_tick(p: np.ndarray) -> np.ndarray:
    t = tick_size(p)
    return np.round(np.ceil((p - 1e-9) / t) * t, 2)


def _floor_tick(p: np.ndarray) -> np.ndarray:
    t = tick_size(p)
    return np.round(np.floor((p + 1e-9) / t) * t, 2)


# ---------- 主函式 ----------


def make_synthetic_market(
    n_stocks: int = 60,
    n_days: int = 420,
    seed: int = 0,
    start: str = "2014-01-02",
    delist_frac: float = 0.15,
    dividend_frac: float = 0.3,
    include_limits: bool = True,
) -> SyntheticMarket:
    """產生一個假市場（見模組說明）。

    n_stocks：普通股檔數（另外加 3 檔 ETF、1 檔 TDR），至少 10。
    n_days：台股交易日數，至少 30。預設從 2014-01-02 起 420 天（到 2015 年 8 月左右），
    跨過 2015-06-01 漲跌幅從 7% 改成 10% 的那天。
    delist_frac：中途下市的普通股比例。dividend_frac：每年 7～9 月除息一次的普通股比例。
    include_limits：False 時不另外製造漲跌停事件（自然碰到漲跌停仍會發生，但很少）。
    """
    if n_stocks < 10:
        raise ValueError("n_stocks 至少 10，才放得下每種情況")
    if n_days < 30:
        raise ValueError("n_days 至少 30")
    rng = np.random.default_rng(seed)
    cfg = DataConfig()
    T = int(n_days)

    cal = _tw_calendar(start, T)
    cal_v = cal.to_numpy()

    # ---- 美股 ----
    us_first = pd.Timestamp(cal_v[0]) - pd.Timedelta(days=60)
    us_last = pd.Timestamp(cal_v[-1])
    us_cal = _business_days(us_first, us_last, _us_holidays(range(us_first.year, us_last.year + 1)))
    us_v = us_cal.to_numpy()
    n_us = len(us_v)
    r_ixic = rng.normal(0.0004, 0.011, n_us)
    r_sox = 1.3 * r_ixic + rng.normal(0.0, 0.010, n_us)
    r_ixic[0] = 0.0
    r_sox[0] = 0.0
    ixic_close = np.round(4000.0 * np.exp(np.cumsum(r_ixic)), 2)
    sox_close = np.round(600.0 * np.exp(np.cumsum(r_sox)), 2)
    us_daily = pd.DataFrame(
        {
            "us_date": np.concatenate([us_v, us_v]),
            "symbol": ["^SOX"] * n_us + ["^IXIC"] * n_us,
            "close": np.concatenate([sox_close, ixic_close]),
        }
    )
    # 訊號用的美股報酬，和 align_us_overnight 一樣：us_date < t 的最後一根對前一根（用取整後的收盤）。
    sox_ret = np.zeros(n_us)
    sox_ret[1:] = np.diff(np.log(sox_close))
    j_us = np.searchsorted(us_v, cal_v, side="left") - 1
    u_t = np.where(j_us >= 1, sox_ret[np.maximum(j_us, 0)], 0.0)

    # ---- 股票 ----
    common_codes = np.sort(rng.choice(np.arange(1101, 9000), size=n_stocks, replace=False))
    common_ids = [f"{c:04d}" for c in common_codes]
    ids = common_ids + list(ETF_IDS) + list(TDR_IDS)
    N = len(ids)
    n_c = n_stocks
    kind = np.array(["common"] * n_c + ["etf"] * len(ETF_IDS) + ["tdr"] * len(TDR_IDS), dtype=object)
    is_common = kind == "common"

    market = np.where(rng.random(N) < 0.65, "twse", "tpex").astype(object)
    market[~is_common] = "twse"
    beta = np.where(is_common, rng.uniform(0.4, 1.6, N), 1.0)
    beta[kind == "tdr"] = 0.8
    sigma = np.where(is_common, rng.uniform(0.012, 0.030, N), 0.006)
    sigma[kind == "tdr"] = 0.02
    price0 = np.exp(rng.uniform(np.log(12.0), np.log(700.0), N))
    amount_target = np.exp(rng.normal(np.log(1.5e8), 1.0, N))
    mu = np.zeros(N)  # 每天的漂移（只有兩檔低價股有）

    etf_pos = n_c + np.arange(len(ETF_IDS))
    price0[etf_pos] = [60.0, 25.0, 17.0]
    amount_target[etf_pos] = [3.0e9, 2.0e9, 1.5e9]
    tdr_pos = n_c + len(ETF_IDS)
    price0[tdr_pos] = 30.0
    amount_target[tdr_pos] = 3.0e8

    # 角色（互不重疊）：千元股、兩檔跨 10 元的低價股、下市、晚上市、停牌，最後兩檔做除權和減資。
    perm = rng.permutation(n_c)
    n_del = int(round(delist_frac * n_c)) if delist_frac > 0 else 0
    n_late = max(1, int(round(0.1 * n_c)))
    n_susp = max(1, int(round(0.08 * n_c)))
    if 3 + n_del + n_late + n_susp + 2 > n_c:
        n_del = max(0, n_c - (3 + n_late + n_susp + 2))
    k = 0
    high_pos = perm[k]
    k += 1
    low_up_pos, low_dn_pos = perm[k], perm[k + 1]
    k += 2
    del_pos = perm[k : k + n_del]
    k += n_del
    late_pos = perm[k : k + n_late]
    k += n_late
    susp_pos = perm[k : k + n_susp]
    k += n_susp
    split_pos, reduce_pos = perm[-1], perm[-2]

    price0[high_pos] = 1150.0
    amount_target[high_pos] = max(amount_target[high_pos], 5.0e8)
    # 兩檔低價股：一檔從 8 元漲過 10 元，一檔從 11 元跌破 10 元（漂移大、波動小，確定會跨過）。
    price0[low_up_pos] = 8.0
    mu[low_up_pos] = 0.003
    price0[low_dn_pos] = 11.0
    mu[low_dn_pos] = -0.003
    sigma[[low_up_pos, low_dn_pos]] = 0.015
    if n_del > 0:
        # 第一檔下市股成交金額大，確定會進股票池。
        amount_target[del_pos[0]] *= 4.0
        price0[del_pos[0]] = max(price0[del_pos[0]], 30.0)
    base_volume = amount_target / price0

    list_idx = np.zeros(N, dtype=np.int64)
    last_idx = np.full(N, T - 1, dtype=np.int64)
    if n_late > 0:
        list_idx[late_pos] = rng.integers(int(0.15 * T), max(int(0.5 * T), int(0.15 * T) + 1), size=n_late)
    if n_del > 0:
        last_idx[del_pos] = rng.integers(int(0.6 * T), max(int(0.95 * T), int(0.6 * T) + 1), size=n_del)

    trade = np.zeros((T, N), dtype=bool)
    for s in range(N):
        trade[list_idx[s] : last_idx[s] + 1, s] = True
    for s in susp_pos:
        s0 = int(rng.integers(int(0.2 * T), int(0.8 * T)))
        length = int(rng.integers(3, 11))
        trade[s0 : min(s0 + length, last_idx[s] - 5), s] = False

    # 事件：現金股利（每年 7～9 月一次）、除權、減資。事件那天停牌就延到下一個交易日。
    cash_event = np.ones((T, N))
    share_event = np.ones((T, N))
    n_div = int(round(dividend_frac * n_c))
    div_pos = rng.choice(n_c, size=min(n_div, n_c), replace=False) if n_div > 0 else np.zeros(0, dtype=np.int64)
    months = cal.month.to_numpy()
    years = cal.year.to_numpy()
    n_cash = 0
    for s in div_pos:
        for y in np.unique(years):
            cand = np.flatnonzero((years == y) & (months >= 7) & (months <= 9))
            cand = cand[(cand > list_idx[s] + 5) & (cand < last_idx[s])]
            if cand.size == 0:
                continue
            d_e = int(rng.choice(cand))
            cash_event[d_e, s] *= 1.0 - rng.uniform(0.015, 0.06)
            n_cash += 1
    if n_cash == 0 and len(div_pos) > 0:
        s = int(div_pos[0])
        d_e = int(min(max(list_idx[s] + 10, T // 2), last_idx[s] - 1))
        cash_event[d_e, s] *= 0.96
    share_event[int(0.45 * T), split_pos] = 1.0 / 1.1
    share_event[int(0.70 * T), reduce_pos] = 1.25

    # ---- 逐日模擬 ----
    shape = (T, N)
    O = np.full(shape, np.nan)
    H = np.full(shape, np.nan)
    Lo = np.full(shape, np.nan)
    C = np.full(shape, np.nan)
    V = np.full(shape, np.nan)
    A = np.full(shape, np.nan)
    REF = np.full(shape, np.nan)
    FN = np.full(shape, np.nan)
    TN = np.full(shape, np.nan)
    DN = np.full(shape, np.nan)
    MB = np.full(shape, np.nan)

    prev_close = np.full(N, np.nan)
    prev_gap = np.zeros(N)
    prev_f = np.zeros(N)
    traded_prev = np.zeros(N, dtype=bool)
    has_traded = np.zeros(N, dtype=bool)
    f_state = rng.normal(0.0, 1.0, N)
    trust_sign = np.zeros(N, dtype=np.int64)
    pend_cash = np.ones(N)
    pend_share = np.ones(N)
    vol_scale = np.ones(N)
    run_left = np.zeros(N, dtype=np.int64)
    margin_bal = np.round(base_volume / 1000.0 * rng.uniform(0.5, 3.0, N)) + 10.0
    m_gap = rng.normal(0.0, 0.004, T)
    m_oc = rng.normal(0.0, 0.008, T)
    limit_ok = is_common.copy()

    for d in range(T):
        tr = trade[d]
        pend_cash *= cash_event[d]
        pend_share *= share_event[d]
        first_row = tr & ~has_traded
        cont = tr & has_traded

        ref = np.where(cont, prev_close, 1.0)
        ref[first_row] = price0[first_row]
        factor = pend_cash * pend_share
        apply = cont & (factor != 1.0)
        ref[apply] = np.round(prev_close[apply] * factor[apply], 2)
        vol_scale[apply] /= pend_share[apply]
        pend_cash[apply] = 1.0
        pend_share[apply] = 1.0
        reported = ref.copy()
        reported[first_row] = np.nan
        reported[cont & ~apply & (rng.random(N) < 0.005)] = np.nan

        up, dn = limit_prices(ref, cal_v[d], cfg)

        # 跳空和盤中報酬。訊號只在 i（前一個交易日）有交易時才有。
        u = u_t[d]
        gap = beta * (0.4 * u + m_gap[d]) + 0.35 * sigma * rng.standard_normal(N)
        oc = mu + beta * m_oc[d] + 0.25 * beta * u + sigma * rng.standard_normal(N)
        sig_ok = cont & traded_prev
        oc = oc + np.where(sig_ok, -0.2 * prev_gap + 0.002 * prev_f, 0.0)

        # 一字價（開高低收都在漲停或都在跌停）的日子。
        one_price = np.zeros(N, dtype=bool)
        if include_limits:
            # 連續一字漲停：開始那天就算第一天，連續 2～4 個交易日。
            start_run = tr & limit_ok & (run_left == 0) & (rng.random(N) < 0.002)
            run_left = np.where(start_run, rng.integers(2, 5, N), run_left)
            in_run = tr & limit_ok & (run_left > 0)
            ev = rng.random(N)
            coin = rng.random(N)
            open_up = limit_ok & ((ev < 0.006) | in_run)
            open_dn = limit_ok & ~open_up & (ev >= 0.006) & (ev < 0.009)
            close_up = limit_ok & ~open_up & ~open_dn & (ev >= 0.009) & (ev < 0.015)
            close_dn = limit_ok & ~open_up & ~open_dn & ~close_up & (ev >= 0.015) & (ev < 0.019)
            stuck_up = open_up & ((coin < 0.7) | in_run)
            stuck_dn = open_dn & (coin < 0.6)
            # 跳空 ±0.2 一定超過 ±10%，取整後被夾在漲跌停價，所以開盤就在漲跌停。
            gap = np.where(open_up, 0.2, gap)
            gap = np.where(open_dn, -0.2, gap)
            oc = np.where(stuck_up | close_up, 0.2, oc)
            oc = np.where(stuck_dn | close_dn, -0.2, oc)
            one_price = tr & (stuck_up | stuck_dn)
            run_left = np.where(in_run, run_left - 1, run_left)

        o = np.clip(_round_tick(ref * np.exp(gap)), dn, up)
        c = np.clip(_round_tick(o * np.exp(oc)), dn, up)
        hi = np.minimum(_ceil_tick(np.maximum(o, c) * np.exp(np.abs(rng.normal(0.0, 0.4, N)) * sigma)), up)
        hi = np.maximum(hi, np.maximum(o, c))
        lo = np.maximum(_floor_tick(np.minimum(o, c) * np.exp(-np.abs(rng.normal(0.0, 0.4, N)) * sigma)), dn)
        lo = np.minimum(lo, np.minimum(o, c))
        hi = np.where(one_price, o, hi)
        lo = np.where(one_price, o, lo)

        realized_oc = np.log(c / o)
        vol = base_volume * vol_scale * np.exp(rng.normal(0.0, 0.35, N)) * (1.0 + 10.0 * np.abs(realized_oc))
        vol = np.where(one_price, vol * 0.25, vol)
        vol = np.maximum(1000.0, np.round(vol / 1000.0) * 1000.0)
        amt = np.round(vol * (o + hi + lo + c) / 4.0)

        O[d, tr] = o[tr]
        H[d, tr] = hi[tr]
        Lo[d, tr] = lo[tr]
        C[d, tr] = c[tr]
        V[d, tr] = vol[tr]
        A[d, tr] = amt[tr]
        REF[d, tr] = reported[tr]

        # 法人：外資買超 = 0.05 × f × 成交量，f 是 AR(1)；投信有連續買賣超；自營商是雜訊。
        f_new = 0.7 * f_state + np.sqrt(1.0 - 0.49) * rng.standard_normal(N)
        f_state = np.where(tr, f_new, f_state)
        stay = rng.random(N) < 0.75
        redraw = rng.choice(np.array([-1, 0, 0, 1]), size=N)
        trust_sign = np.where(tr & ~stay, redraw, trust_sign)
        FN[d, tr] = np.round(0.05 * f_state * vol)[tr]
        TN[d, tr] = np.round(trust_sign * np.abs(rng.normal(0.0, 0.01, N)) * vol + trust_sign)[tr]
        DN[d, tr] = np.round(rng.normal(0.0, 0.02, N) * vol)[tr]
        margin_bal = np.where(tr, np.round(margin_bal * np.exp(rng.normal(0.0, 0.015, N))), margin_bal)
        margin_bal = np.maximum(margin_bal, 0.0)
        MB[d, tr] = margin_bal[tr]

        gap_real = np.where(cont, np.log(o / ref), 0.0)
        prev_gap = np.where(tr, gap_real, prev_gap)
        prev_f = np.where(tr, f_state, prev_f)
        prev_close = np.where(tr, c, prev_close)
        has_traded |= tr
        traded_prev = tr.copy()

    # ---- 組成 long 表 ----
    di, si = np.nonzero(trade)
    ids_arr = np.asarray(ids, dtype=object)
    panel = pd.DataFrame(
        {
            "date": cal_v[di],
            "stock_id": ids_arr[si],
            "market": market[si],
            "open": O[di, si],
            "high": H[di, si],
            "low": Lo[di, si],
            "close": C[di, si],
            "volume": V[di, si],
            "amount": A[di, si],
            "ref_price": REF[di, si],
        }
    )
    panel["date"] = panel["date"].astype("datetime64[ns]")
    panel = panel.sort_values(["date", "stock_id"], kind="mergesort").reset_index(drop=True)
    validate_panel(panel)  # 只檢查，回傳的 panel 保留 ref_price 缺值

    keep_inst = rng.random(len(di)) >= 0.02
    inst = pd.DataFrame(
        {
            "date": cal_v[di][keep_inst],
            "stock_id": ids_arr[si][keep_inst],
            "foreign_net": FN[di, si][keep_inst],
            "trust_net": TN[di, si][keep_inst],
            "dealer_net": DN[di, si][keep_inst],
        }
    )
    inst_daily = validate_inst(inst)

    keep_margin = (rng.random(len(di)) >= 0.02) & (kind[si] != "etf")
    margin = pd.DataFrame(
        {
            "date": cal_v[di][keep_margin],
            "stock_id": ids_arr[si][keep_margin],
            "margin_balance": MB[di, si][keep_margin],
        }
    )
    margin_daily = validate_margin(margin)
    us_daily = validate_us(us_daily)

    delisted = last_idx < T - 1
    info = pd.DataFrame(
        {
            "stock_id": ids_arr,
            "kind": kind,
            "market": market,
            "beta": beta,
            "sigma": sigma,
            "list_date": cal_v[list_idx],
            "last_date": cal_v[last_idx],
            "delisted": delisted,
            "late_listed": list_idx > 0,
            "dividend": np.isin(np.arange(N), div_pos),
            "suspended": np.isin(np.arange(N), susp_pos),
            "stock_split": np.arange(N) == split_pos,
            "capital_reduction": np.arange(N) == reduce_pos,
        }
    )
    info["list_date"] = info["list_date"].astype("datetime64[ns]")
    info["last_date"] = info["last_date"].astype("datetime64[ns]")
    return SyntheticMarket(
        panel=panel,
        us_daily=us_daily,
        inst_daily=inst_daily,
        margin_daily=margin_daily,
        calendar=pd.DatetimeIndex(cal, name="date"),
        stock_info=info,
    )
