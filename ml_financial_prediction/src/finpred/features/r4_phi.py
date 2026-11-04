"""Phi-v1: locked, pre-registered raw -> concrete features (docs/r4/PHI_V1_CATALOGUE.md).

Implementation notes (the catalogue is the specification; nothing here was tuned):

* Wide frames are indexed by the actual Taiwan trading calendar (past sessions are
  known at 08:10). A quantity "after row d" uses rows <= d; the feature for target
  t uses D1 = previous trading row, i.e. ``.shift(1)`` on that calendar index, or a
  window ending at TW(k) = ``.shift(k)``.
* US windows use the XNYS schedule and native yfinance bars with session date <= t-1.
* Forward-looking calendar features (S3, S8) use the XTAI scheduled sessions only.
* After centring/scaling every feature maps NaN -> 0 (catalogue rule 4.3.4).
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from finpred.features.r4_raw import RawData

PHI_VERSION = "phi-v1"
CORE = ["us_overnight_shock_z", "mkt_foreign_flow_z", "tx_foreign_net_oi_change_z",
        "tug_of_war_20d", "attention_shock", "foreign_flow_persistence"]
SECONDARY = ["lottery_max5e", "trust_flow_persistence", "trust_quarter_end_dressing",
             "foreign_clientele_x_us_shock", "vix_regime", "mkt_intraday_lag_z",
             "lagged_move_x_vix", "pre_long_closure", "closure_length_log", "us_shock_x_long_gap"]
MIN_CS = 40


# ----------------------------------------------------------------------------- inputs

def read_yahoo_chart(path: str) -> pd.DataFrame:
    """yfinance/Yahoo chart JSON -> native daily bars keyed by exchange-local date."""
    with open(path, encoding="utf-8") as handle:
        result = json.load(handle)["chart"]["result"][0]
    tz = result["meta"].get("exchangeTimezoneName", "America/New_York")
    stamps = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(tz)
    close = result["indicators"]["quote"][0]["close"]
    frame = pd.DataFrame({"date": stamps.tz_localize(None).normalize(), "close": close})
    frame = frame.dropna(subset=["close"]).drop_duplicates("date", keep="last")
    return frame.sort_values("date").reset_index(drop=True)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ----------------------------------------------------------------------------- helpers

def _wide(stocks: pd.DataFrame, column: str, cal: pd.DatetimeIndex) -> pd.DataFrame:
    return stocks.pivot(index="date", columns="stock_id", values=column).reindex(cal)


def _csrank(frame: pd.DataFrame, universe) -> pd.DataFrame:
    """Per-date percentile rank over valid U50 stocks, (rank-0.5)/n - 0.5; <40 valid -> 0."""
    sub = frame[universe]
    n = sub.notna().sum(axis=1)
    rank = sub.rank(axis=1, method="average")
    out = (rank - 0.5).div(n, axis=0) - 0.5
    out = out.where(n >= MIN_CS, 0.0)
    return out.fillna(0.0).reindex(columns=frame.columns)


def _rolling_beta(y: pd.DataFrame, x: pd.Series, *, window: int, end_lag: int, min_n: int):
    """Shrunk OLS slope of y on x over rows [t-end_lag-window+1, t-end_lag]; b=0.5*b_hat+0.5."""
    xs = pd.DataFrame(np.repeat(x.to_numpy()[:, None], y.shape[1], axis=1), index=y.index, columns=y.columns)
    valid = y.notna() & xs.notna()
    yv, xv = y.where(valid), xs.where(valid)
    roll = lambda f: f.rolling(window, min_periods=1).sum()  # noqa: E731
    n = valid.astype(float).rolling(window, min_periods=1).sum()
    sx, sy = roll(xv.fillna(0)), roll(yv.fillna(0))
    sxy, sxx = roll((xv * yv).fillna(0)), roll((xv * xv).fillna(0))
    var = sxx / n - (sx / n) ** 2
    cov = sxy / n - (sx / n) * (sy / n)
    b_hat = (cov / var.where(var > 1e-14)).where(n >= min_n)
    b_hat = b_hat.shift(end_lag)
    return 0.5 * b_hat.fillna(1.0) + 0.5


def _scaled_z(series: pd.Series, *, value_lag: int, std_lag: int, window=60, min_n=20, clip=4.0):
    std = series.rolling(window, min_periods=min_n).std()
    return (series.shift(value_lag) / std.shift(std_lag)).clip(-clip, clip)


def _third_wednesdays(cal: pd.DatetimeIndex) -> set:
    """TX final settlement: third Wednesday; if not a trading day, the next trading day."""
    out = set()
    for period in pd.period_range(cal.min(), cal.max(), freq="M"):
        first = period.start_time
        wed = first + pd.Timedelta(days=(2 - first.weekday()) % 7 + 14)
        later = cal[cal >= wed]
        if len(later):
            out.add(later[0])
    return out


# ----------------------------------------------------------------------------- Phi-v1

def build_phi(raw: RawData, *, gspc: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    import exchange_calendars as xc

    cal = raw.tw_calendar
    u50 = sorted(raw.top50)
    S = raw.stocks
    OPN, C = _wide(S, "open", cal), _wide(S, "close", cal)
    VAL, SH = _wide(S, "turnover", cal), _wide(S, "volume", cal)
    F, IT, FOWN = _wide(S, "foreign_net", cal), _wide(S, "trust_net", cal), _wide(S, "foreign_hold_pct", cal)
    for frame in (OPN, C):
        frame[frame <= 0] = np.nan
    VAL = VAL.where(VAL > 0)
    SH_pos = SH.where(SH > 0)
    FOWN = FOWN.where((FOWN >= 0) & (FOWN <= 100))
    stocks = list(OPN.columns)

    with np.errstate(divide="ignore", invalid="ignore"):
        r_on = np.log(OPN / C.shift(1))
        r_id = np.log(C / OPN)
        r_cc = np.log(C / C.shift(1))
    R = np.exp(r_cc) - 1

    def mkt(frame, how):
        sub = frame[u50]
        n = sub.notna().sum(axis=1)
        val = sub.median(axis=1) if how == "median" else sub.mean(axis=1)
        return val.where(n >= MIN_CS)

    m_on, m_id, m_cc = mkt(r_on, "median"), mkt(r_id, "median"), mkt(R, "mean")
    b_on = _rolling_beta(r_on, m_on, window=60, end_lag=21, min_n=40)
    b_id = _rolling_beta(r_id, m_id, window=60, end_lag=21, min_n=40)
    b_cc = _rolling_beta(R, m_cc, window=119, end_lag=22, min_n=60)

    out = {}
    days_since = pd.Series(cal.to_series().diff().dt.days.to_numpy(), index=cal)

    # ---- C1 us_overnight_shock_z (XNYS windows, native closes, session date <= t-1)
    xnys = xc.get_calendar("XNYS")
    us_sessions = xnys.sessions_in_range(pd.Timestamp("2019-01-01"), cal.max())
    us_sessions = pd.DatetimeIndex(us_sessions.tz_localize(None) if us_sessions.tz else us_sessions)
    sox = raw.extra["sox"][["date", "close"]]
    zs = []
    for bars in (sox, gspc):
        px = bars.set_index("date")["close"].reindex(us_sessions)
        logp = np.log(px)
        ret = logp.diff()                      # consecutive scheduled sessions; NaN if a bar is missing
        sigma = ret.rolling(60, min_periods=20).std()
        z = pd.Series(np.nan, index=cal)
        for pos in range(1, len(cal)):
            t, d1 = cal[pos], cal[pos - 1]
            lo = us_sessions.searchsorted(d1, side="left")
            hi = us_sessions.searchsorted(t - pd.Timedelta(days=1), side="right")
            n_t = hi - lo
            if lo == 0:
                continue
            b_t = us_sessions[lo - 1]
            if n_t == 0:
                z.iloc[pos] = 0.0
                continue
            window = us_sessions[lo:hi]
            if px.loc[window].isna().any() or np.isnan(px.loc[b_t]):
                continue
            R_x = logp.loc[window[-1]] - logp.loc[b_t]
            sig = sigma.loc[b_t]
            if not np.isfinite(sig) or sig <= 0:
                continue
            z.iloc[pos] = float(np.clip(R_x / (sig * np.sqrt(max(n_t, 1))), -4, 4))
        zs.append(z)
    c1 = 0.5 * zs[0].fillna(0.0) + 0.5 * zs[1].fillna(0.0)
    out["us_overnight_shock_z"] = c1

    # ---- C2 mkt_foreign_flow_z (U100 on D1)
    valid = SH_pos.notna() & VAL.notna() & F.notna()
    n_valid = valid.sum(axis=1)
    vwap = VAL / SH_pos
    ff = (F * vwap).where(valid).sum(axis=1) / VAL.where(valid).sum(axis=1)
    ff = ff.where(n_valid >= 80)
    out["mkt_foreign_flow_z"] = _scaled_z(ff, value_lag=1, std_lag=2).fillna(0.0)

    # ---- C3 tx_foreign_net_oi_change_z (global rows <= D1; no differencing across gaps)
    g = raw.global_.set_index("date")["TX_OI"].reindex(cal)
    d_oi = g - g.shift(1)
    settle = pd.Series(cal.isin(list(_third_wednesdays(cal))), index=cal)
    d_valid = d_oi.where(~settle)
    s_valid = d_valid.dropna().rolling(60, min_periods=20).std().reindex(cal).ffill()
    c3 = (d_valid.shift(1) / s_valid.shift(2)).clip(-4, 4)
    out["tx_foreign_net_oi_change_z"] = c3.fillna(0.0)

    # ---- C4 tug_of_war_20d (beta-residualised intraday minus overnight, 20 days to D1)
    ok = r_on.notna() & r_id.notna()
    ok = ok & pd.DataFrame({c: m_on.notna() & m_id.notna() for c in stocks})
    sum20 = lambda f: f.where(ok).fillna(0.0).rolling(20, min_periods=1).sum().shift(1)  # noqa: E731
    m_on_w = pd.DataFrame({c: m_on for c in stocks})
    m_id_w = pd.DataFrame({c: m_id for c in stocks})
    n20 = ok.astype(float).rolling(20, min_periods=1).sum().shift(1)
    diff = (sum20(r_id) - b_id * sum20(m_id_w)) - (sum20(r_on) - b_on * sum20(m_on_w))
    sig20 = r_cc.rolling(20, min_periods=15).std().shift(1).clip(lower=0.005)
    t20 = (diff / (sig20 * np.sqrt(n20))).where(n20 >= 15)
    out_c4 = _csrank(t20, u50)

    # ---- C5 attention_shock (stock row must exist on D1)
    lv = np.log(VAL)
    base_med = lv.rolling(60, min_periods=40).median()
    mad = lv.rolling(60, min_periods=40).apply(lambda a: np.nanmedian(np.abs(a - np.nanmedian(a))), raw=True)
    a_v = ((lv.shift(1) - base_med.shift(2)) / (1.4826 * mad.shift(2)).clip(lower=0.05)).clip(-5, 5)
    sig_pre = r_cc.rolling(20, min_periods=15).std().shift(2).clip(lower=0.005)
    a_r = ((r_cc.shift(1).abs() / sig_pre - 0.798) / 0.603).clip(-5, 5)
    has_d1 = C.shift(1).notna() & VAL.shift(1).notna()
    A = (0.5 * a_v.fillna(0.0) + 0.5 * a_r.fillna(0.0)).where(has_d1)
    a_u = A[u50]
    n_a = a_u.notna().sum(axis=1)
    c5 = A.sub(a_u.mean(axis=1), axis=0).where(pd.DataFrame({c: n_a >= MIN_CS for c in stocks}))
    out_c5 = c5.fillna(0.0)

    # ---- C6 foreign_flow_persistence (half-life 2 trading days over TW(1)..TW(10))
    num = pd.DataFrame(0.0, index=cal, columns=stocks)
    den = pd.DataFrame(0.0, index=cal, columns=stocks)
    cnt = pd.DataFrame(0.0, index=cal, columns=stocks)
    for j in range(1, 11):
        w = 0.5 ** ((j - 1) / 2)
        sh, f = SH_pos.shift(j), F.shift(j)
        v = sh.notna() & f.notna()
        num += (w * f).where(v).fillna(0.0)
        den += (w * sh).where(v).fillna(0.0)
        cnt += v.astype(float)
    ffp = (num / den.where(den > 0)).clip(-1, 1).where(cnt >= 5)
    out_c6 = _csrank(ffp, u50)

    # ---- S1 lottery_max5e (idiosyncratic top-5 mean over TW(1)..TW(21), b_cc fixed at t)
    stack = []
    for k in range(1, 22):
        e = R.shift(k) - b_cc * pd.DataFrame({c: m_cc.shift(k) for c in stocks})
        stack.append(e.to_numpy())
    arr = np.stack(stack)                                   # (21, T, N)
    n_e = np.isfinite(arr).sum(axis=0)
    filled = np.where(np.isfinite(arr), arr, -np.inf)
    top5 = -np.sort(-filled, axis=0)[:5]
    with np.errstate(invalid="ignore"):
        max5 = np.where(np.isfinite(top5), top5, np.nan).mean(axis=0)
    max5 = pd.DataFrame(np.where(n_e >= 15, max5, np.nan), index=cal, columns=stocks)
    out_s1 = _csrank(max5, u50)

    # ---- S2 trust_flow_persistence (TW(1)..TW(5))
    num2 = pd.DataFrame(0.0, index=cal, columns=stocks)
    den2 = pd.DataFrame(0.0, index=cal, columns=stocks)
    cnt2 = pd.DataFrame(0.0, index=cal, columns=stocks)
    for j in range(1, 6):
        sh, it = SH_pos.shift(j), IT.shift(j)
        v = sh.notna() & it.notna()
        num2 += it.where(v).fillna(0.0)
        den2 += sh.where(v).fillna(0.0)
        cnt2 += v.astype(float)
    tfp = (num2 / den2.where(den2 > 0)).clip(-1, 1).where(cnt2 >= 3)
    out_s2 = _csrank(tfp, u50)

    # ---- S3 trust_quarter_end_dressing (scheduled XTAI quarter boundaries)
    xtai = xc.get_calendar("XTAI")
    sched = xtai.sessions_in_range(pd.Timestamp("2019-01-01"), pd.Timestamp("2027-06-30"))
    sched = pd.DatetimeIndex(sched.tz_localize(None) if sched.tz else sched)
    sched_s = pd.Series(sched, index=sched)
    last_q = set(sched_s.groupby([sched.year, sched.month]).max()[lambda s: s.dt.month.isin([3, 6, 9, 12])])
    first_q = set(sched_s.groupby([sched.year, sched.month]).min()[lambda s: s.dt.month.isin([1, 4, 7, 10])])
    out_s3 = pd.DataFrame(0.0, index=cal, columns=stocks)
    for pos in range(1, len(cal)):
        t = cal[pos]
        w_t = 1 if t in last_q else (-1 if t in first_q else 0)
        if w_t == 0:
            continue
        d1 = cal[pos - 1]
        q_start = pd.Timestamp(year=t.year, month=3 * ((t.month - 1) // 3) + 1, day=1)
        if w_t == 1:
            mask = (cal >= q_start) & (cal <= d1)
        else:
            prev_start = (q_start - pd.DateOffset(months=3))
            mask = (cal >= prev_start) & (cal < q_start) & (cal <= d1)
        it, sh = IT.loc[mask], SH_pos.loc[mask]
        v = it.notna() & sh.notna()
        h = it.where(v).sum() / sh.where(v).sum().where(lambda s: s > 0)
        h = h.where(v.sum() >= 30)
        row = _csrank(pd.DataFrame([h.reindex(stocks)], index=[t]), u50).iloc[0]
        out_s3.loc[t] = w_t * row

    # ---- S4 foreign_clientele_x_us_shock (ownership residualised on b_on, times C1)
    own = _csrank(FOWN.shift(1), u50)
    own_valid = FOWN.shift(1).notna()
    out_s4 = pd.DataFrame(0.0, index=cal, columns=stocks)
    for t in cal:
        if c1.loc[t] == 0:
            continue
        cols = [c for c in u50 if own_valid.at[t, c] and np.isfinite(b_on.at[t, c])]
        if len(cols) < MIN_CS:
            continue
        x, y = b_on.loc[t, cols].to_numpy(float), own.loc[t, cols].to_numpy(float)
        xm = x - x.mean()
        c = (xm @ (y - y.mean())) / (xm @ xm) if (xm @ xm) > 0 else 0.0
        a = y.mean() - c * x.mean()
        res = own.loc[t, cols] - a - c * b_on.loc[t, cols]
        out_s4.loc[t, cols] = (res * c1.loc[t]).to_numpy()

    # ---- S5 vix_regime (native ^VIX close, session <= t-1)
    vbar = vix.set_index("date")["close"]
    v_asof = vbar.reindex(vbar.index.union(cal - pd.Timedelta(days=1))).ffill()
    v_t = pd.Series(v_asof.reindex(cal - pd.Timedelta(days=1)).to_numpy(), index=cal)
    s5 = np.log(v_t / 20.0).clip(-1, 2).fillna(0.0)
    out["vix_regime"] = s5

    # ---- S6 mkt_intraday_lag_z, S7 lagged_move_x_vix
    m50 = mkt(r_id, "mean")
    s6 = _scaled_z(m50, value_lag=1, std_lag=2).fillna(0.0)
    out["mkt_intraday_lag_z"] = s6
    out["lagged_move_x_vix"] = (s6 * s5).clip(-4, 4)

    # ---- S8 pre_long_closure (scheduled next session), S9, S10
    nxt_pos = sched.searchsorted(cal, side="right")
    nxt = pd.Series([sched[p] if p < len(sched) else pd.NaT for p in nxt_pos], index=cal)
    out["pre_long_closure"] = ((nxt - cal.to_series()).dt.days >= 4).astype(float)
    out["closure_length_log"] = np.log(days_since).fillna(0.0)
    out["us_shock_x_long_gap"] = c1 * (days_since >= 4).astype(float)

    market = pd.DataFrame(out)
    market.index.name = "date"
    per_stock = {
        "tug_of_war_20d": out_c4, "attention_shock": out_c5, "foreign_flow_persistence": out_c6,
        "lottery_max5e": out_s1, "trust_flow_persistence": out_s2,
        "trust_quarter_end_dressing": out_s3, "foreign_clientele_x_us_shock": out_s4,
    }
    parts = []
    for name, frame in per_stock.items():
        wide = frame.reindex(index=cal, columns=stocks).copy()
        wide.index.name, wide.columns.name = "date", "stock_id"
        parts.append(wide.stack(future_stack=True).rename(name))
    long = pd.concat(parts, axis=1)
    if long.index.duplicated().any():
        raise AssertionError("duplicate (date, stock) keys in Phi output")
    long = long.reset_index().merge(market.reset_index(), on="date", how="left")
    cols = CORE + SECONDARY
    long[cols] = long[cols].astype(float).fillna(0.0)
    # Stock-relative features are defined over U50 only.
    rel = list(per_stock)
    long.loc[~long["stock_id"].isin(u50), rel] = 0.0
    return long[["date", "stock_id", *cols]]


def build_r4_feature_frame(data_root: str, *, gspc_path: str, vix_path: str, max_date="2026-09-30"):
    """R3 frame (panel + baseline groups) plus the locked Phi-v1 groups."""
    from importlib.metadata import version

    from finpred.features import r3_features as rf
    from finpred.features.r4_raw import load_raw

    ff = rf.build_feature_frame(data_root, max_date=max_date)
    raw = load_raw(data_root, max_date=max_date)
    phi = build_phi(raw, gspc=read_yahoo_chart(gspc_path), vix=read_yahoo_chart(vix_path))
    frame = ff.frame.merge(phi, on=["date", "stock_id"], how="left")
    if len(frame) != len(ff.frame):
        raise ValueError("Phi merge changed the row count")
    frame[CORE + SECONDARY] = frame[CORE + SECONDARY].fillna(0.0)
    groups = {**ff.groups, "phi_core": list(CORE), "phi_secondary": list(SECONDARY)}
    meta = {**ff.meta, "feature_version": f"{ff.meta['feature_version']}+{PHI_VERSION}",
            "phi_version": PHI_VERSION, "phi_raw": raw.meta,
            "gspc_sha256": file_sha256(gspc_path), "vix_sha256": file_sha256(vix_path),
            "exchange_calendars": version("exchange-calendars")}
    return rf.FeatureFrame(frame=frame, labels=ff.labels, groups=groups, meta=meta)
