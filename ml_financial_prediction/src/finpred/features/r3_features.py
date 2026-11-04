"""R3 research features built only from inputs known before 08:10 Asia/Taipei.

Inputs are read from a checkout of the read-only data branch
(``claude/peaceful-babbage-09xeie``):

* ``data/transform/panel_lag.csv.gz`` - 50 verified lag features (+ labels)
* ``data/features/market_features.csv`` - as-of market features (source date <= t-1)
* ``data/teacher/market/*.csv`` and ``data/teacher_live/market/*.csv`` - teacher rows

Timing rules (see the data branch ``schema.json`` ``timing_verification``):

* teacher stock rows (prices, volume, institutional flows, indicators, ``y``) are
  known only after the close, so every stock-history feature for target date t
  is computed from rows strictly before t (``shift(1)`` inside each stock);
* teacher ``^TWII``/``^KS11`` same-day values and same-day ``TX_OI`` are never used;
* market features use the last source session ``s <= t - 1 calendar day``.

Labels are returned in a separate frame and no feature column may start with
``label_``. This is research tooling: readiness stays ``research_assumption``.
"""

from __future__ import annotations

import glob
import hashlib
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FEATURE_VERSION = "r3-v1"
DATA_BRANCH = "claude/peaceful-babbage-09xeie"
TRAINING_LAST_DATE = pd.Timestamp("2026-08-31")

TEACHER_COLUMNS = {
    "etl:adj_close": "close",
    "etl:adj_open": "open",
    "etl:adj_high": "high",
    "etl:adj_low": "low",
    "price:成交筆數": "trades",
    "price:成交金額": "turnover",
    "price:成交股數": "volume",
    "foreign_investors_shareholding:全體外資及陸資持股比率": "foreign_hold_pct",
    "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)": "foreign_net",
    "institutional_investors_trading_summary:投信買賣超股數": "trust_net",
    "institutional_investors_trading_summary:自營商買賣超股數(自行買賣)": "dealer_net",
    "institutional_investors_trading_summary:自營商買賣超股數(避險)": "dealer_hedge_net",
    "RSI": "rsi",
    "SMA": "sma",
    "MACD": "macd",
    "ATR": "atr",
    "BBANDS_upper": "bb_upper",
    "BBANDS_mid": "bb_mid",
    "BBANDS_lower": "bb_lower",
    "y": "y",
}

# One-session as-of returns of the most recent source session (H2) plus freshness.
MARKET_1S_COLUMNS = [
    "sox_ret_1s", "tsm_adr_ret_1s", "nvda_ret_1s", "dji_ret_1s", "dxy_ret_1s",
    "us10y_change_bp_1s", "usd_twd_ret_1s", "n225_ret_1s", "hsi_ret_1s",
    "sse_ret_1s", "stoxx50e_ret_1s", "gdaxi_ret_1s", "wti_ret_1s", "gold_ret_1s",
    "etf_0050_ret_1s", "etf_0052_ret_1s", "etf_0055_ret_1s", "etf_006201_ret_1s",
    "sox_ret_20s", "dji_ret_20s", "etf_0050_ret_20s",
    "sox_age_days", "dji_age_days", "^VIX",
]

FORBIDDEN_MARKET_COLUMNS = {"^TWII", "^KS11", "TX_OI"}

# Stock-history columns used for per-date cross-sectional ranks (H4).
XS_SOURCE_COLUMNS = [
    "intra_l1", "intra_m5", "intra_m20", "gap_l1", "gap_m5", "cc_l1",
    "mom20", "vol20", "hl_l1", "volu_ratio", "foreign_net_ratio",
    "trust_net_ratio", "rsi_l1", "sma_dev", "bb_pos", "stock_ret_lag2",
    "stock_ret_lag5",
]

ALL_GROUPS = ("panel", "stock_hist", "market_1s", "xs_rank", "beta", "calendar")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def teacher_hashes(data_root: str) -> dict:
    """Digest of every teacher stock CSV (Training and Live) used for labels/features."""
    out = {}
    for key in ("teacher", "teacher_live"):
        digest = hashlib.sha256()
        for path in sorted(glob.glob(os.path.join(_paths(data_root)[key], "*.csv"))):
            digest.update(os.path.basename(path).encode())
            digest.update(sha256_file(path).encode())
        out[key] = digest.hexdigest()
    return out


def _paths(data_root: str) -> dict[str, str]:
    root = os.path.abspath(data_root)
    return {
        "panel": os.path.join(root, "data", "transform", "panel_lag.csv.gz"),
        "market": os.path.join(root, "data", "features", "market_features.csv"),
        "teacher": os.path.join(root, "data", "teacher", "market"),
        "teacher_live": os.path.join(root, "data", "teacher_live", "market"),
        "info": os.path.join(root, "data", "teacher", "info.json"),
    }


def load_panel(data_root: str) -> pd.DataFrame:
    panel = pd.read_csv(_paths(data_root)["panel"], dtype={"stock_id": str}, parse_dates=["date"])
    if panel.duplicated(["date", "stock_id"]).any():
        raise ValueError("panel has duplicate stock/date keys")
    return panel


def panel_feature_columns(panel: pd.DataFrame) -> list[str]:
    columns = [c for c in panel.columns if "_ret_lag" in c]
    if len(columns) != 50 or any(c.startswith("label_") for c in columns):
        raise ValueError("unexpected panel feature columns")
    return columns


def _read_teacher_dir(directory: str) -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        frame = pd.read_csv(path, parse_dates=["date"])
        frame.insert(0, "stock_id", os.path.basename(path)[:-4])
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"no teacher csv files under {directory}")
    return pd.concat(frames, ignore_index=True)


def load_teacher_stocks(data_root: str, *, max_date: str | pd.Timestamp) -> pd.DataFrame:
    """Training rows plus Live rows after the Training end and <= ``max_date``.

    Live marks pending values with -1; such rows are kept as all-NaN so later
    shifted features see a missing day instead of a fake number.
    """
    max_date = pd.Timestamp(max_date)
    paths = _paths(data_root)
    training = _read_teacher_dir(paths["teacher"])
    if training["date"].max() != TRAINING_LAST_DATE:
        raise ValueError("unexpected teacher Training end date")
    frames = [training]
    if max_date > TRAINING_LAST_DATE:
        live = _read_teacher_dir(paths["teacher_live"])
        live = live[(live["date"] > TRAINING_LAST_DATE) & (live["date"] <= max_date)].copy()
        value_columns = [c for c in live.columns if c not in ("stock_id", "date")]
        pending = (live[value_columns] == -1).all(axis=1)
        live.loc[pending, value_columns] = np.nan
        live.loc[live["y"] == -1, "y"] = np.nan
        frames.append(live)
    stocks = pd.concat(frames, ignore_index=True)
    stocks = stocks[stocks["date"] <= max_date]
    missing = set(TEACHER_COLUMNS) - set(stocks.columns)
    if missing:
        raise ValueError(f"teacher columns missing: {sorted(missing)}")
    stocks = stocks.rename(columns=TEACHER_COLUMNS)[["stock_id", "date", *TEACHER_COLUMNS.values()]]
    if stocks.duplicated(["stock_id", "date"]).any():
        raise ValueError("teacher rows have duplicate stock/date keys")
    return stocks.sort_values(["stock_id", "date"]).reset_index(drop=True)


def build_labels(stocks: pd.DataFrame) -> pd.DataFrame:
    """Label frame: only rows with complete binary y and positive adjusted prices."""
    frame = stocks[["stock_id", "date", "open", "close", "y"]].copy()
    frame = frame[frame["y"].isin([0, 1]) & (frame["open"] > 0) & (frame["close"] > 0)]
    frame["r"] = (frame["close"] - frame["open"]) / frame["open"]
    if ((frame["close"] > frame["open"]).astype(int) != frame["y"].astype(int)).any():
        raise ValueError("teacher y disagrees with adjusted prices")
    frame["y"] = frame["y"].astype(int)
    return frame.rename(columns={"open": "adj_open", "close": "adj_close"}).reset_index(drop=True)


def _rolling(series_by_stock, window, func):
    return series_by_stock.transform(lambda s: getattr(s.rolling(window, min_periods=window), func)())


def stock_history_features(stocks: pd.DataFrame) -> pd.DataFrame:
    """Per-stock features for row t using only that stock's rows before t."""
    s = stocks.sort_values(["stock_id", "date"]).copy()
    g = s.groupby("stock_id", sort=False)
    prev_close = g["close"].shift(1)
    s["_intra"] = s["close"] / s["open"] - 1.0
    s["_cc"] = s["close"] / prev_close - 1.0
    s["_gap"] = s["open"] / prev_close - 1.0
    s["_hl"] = s["high"] / s["low"] - 1.0
    for name in ("foreign_net", "trust_net", "dealer_net"):
        s[f"_{name}_ratio"] = s[name] / s["volume"].where(s["volume"] > 0)
    s["_logvol"] = np.log(s["volume"].where(s["volume"] > 0))
    s["_logturn"] = np.log(s["turnover"].where(s["turnover"] > 0))
    s["_sma_dev"] = s["close"] / s["sma"] - 1.0
    s["_macd_n"] = s["macd"] / s["close"]
    s["_atr_n"] = s["atr"] / s["close"]
    width = s["bb_upper"] - s["bb_lower"]
    s["_bb_pos"] = (s["close"] - s["bb_lower"]) / width.where(width > 0)

    # Every feature below is a function of rows <= t-1: shift first, then roll.
    lag = s.groupby("stock_id", sort=False)[[
        "_intra", "_cc", "_gap", "_hl", "_foreign_net_ratio", "_trust_net_ratio",
        "_dealer_net_ratio", "_logvol", "_logturn", "_sma_dev", "_macd_n", "_atr_n",
        "_bb_pos", "rsi", "close", "foreign_hold_pct",
    ]].shift(1)
    lag["stock_id"] = s["stock_id"].to_numpy()
    lg = lag.groupby("stock_id", sort=False)

    out = pd.DataFrame({"stock_id": s["stock_id"].to_numpy(), "date": s["date"].to_numpy()})
    out["intra_l1"] = lag["_intra"].to_numpy()
    out["intra_l2"] = lg["_intra"].shift(1).to_numpy()
    out["intra_m5"] = _rolling(lg["_intra"], 5, "mean").to_numpy()
    out["intra_m20"] = _rolling(lg["_intra"], 20, "mean").to_numpy()
    out["gap_l1"] = lag["_gap"].to_numpy()
    out["gap_m5"] = _rolling(lg["_gap"], 5, "mean").to_numpy()
    out["cc_l1"] = lag["_cc"].to_numpy()
    out["mom20"] = (lag["close"] / lg["close"].shift(20) - 1.0).to_numpy()
    out["vol20"] = _rolling(lg["_cc"], 20, "std").to_numpy()
    out["intra_vol20"] = _rolling(lg["_intra"], 20, "std").to_numpy()
    out["hl_l1"] = lag["_hl"].to_numpy()
    out["hl_m5"] = _rolling(lg["_hl"], 5, "mean").to_numpy()
    out["volu_ratio"] = (lag["_logvol"] - _rolling(lg["_logvol"], 20, "mean")).to_numpy()
    out["log_turnover"] = lag["_logturn"].to_numpy()
    out["foreign_net_ratio"] = lag["_foreign_net_ratio"].to_numpy()
    out["foreign_net_m5"] = _rolling(lg["_foreign_net_ratio"], 5, "mean").to_numpy()
    out["trust_net_ratio"] = lag["_trust_net_ratio"].to_numpy()
    out["dealer_net_ratio"] = lag["_dealer_net_ratio"].to_numpy()
    out["foreign_hold_chg5"] = (lag["foreign_hold_pct"] - lg["foreign_hold_pct"].shift(5)).to_numpy()
    out["rsi_l1"] = lag["rsi"].to_numpy()
    out["sma_dev"] = lag["_sma_dev"].to_numpy()
    out["macd_n"] = lag["_macd_n"].to_numpy()
    out["atr_n"] = lag["_atr_n"].to_numpy()
    out["bb_pos"] = lag["_bb_pos"].to_numpy()
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def beta_features(stocks: pd.DataFrame, market: pd.DataFrame, *, window: int = 60) -> pd.DataFrame:
    """Past-only gap response of each stock to the latest SOX/DJI session (H2b).

    beta_gap_x(t) = cov(gap_i, x) / var(x) over the stock's previous ``window``
    rows (all < t), where x is the as-of US one-session return aligned to the same
    Taiwan target date. pred_gap_x(t) = beta_gap_x(t) * x(t) uses today's known x.
    """
    s = stocks.sort_values(["stock_id", "date"])[["stock_id", "date", "open", "close"]].copy()
    s["_gap"] = s["open"] / s.groupby("stock_id", sort=False)["close"].shift(1) - 1.0
    m = market[["date", "sox_ret_1s", "dji_ret_1s"]]
    s = s.merge(m, on="date", how="left")
    out = s[["stock_id", "date"]].copy()
    for x in ("sox_ret_1s", "dji_ret_1s"):
        prev = s.groupby("stock_id", sort=False)[["_gap", x]].shift(1)
        prev["stock_id"] = s["stock_id"].to_numpy()
        prev["_xy"] = prev["_gap"] * prev[x]
        prev["_xx"] = prev[x] * prev[x]
        valid = prev["_gap"].notna() & prev[x].notna()
        for col in ("_gap", x, "_xy", "_xx"):
            prev[col] = prev[col].where(valid)
        pg = prev.groupby("stock_id", sort=False)
        mean = {c: pg[c].transform(lambda v: v.rolling(window, min_periods=window // 2).mean())
                for c in ("_gap", x, "_xy", "_xx")}
        var = mean["_xx"] - mean[x] ** 2
        beta = (mean["_xy"] - mean["_gap"] * mean[x]) / var.where(var > 1e-12)
        short = x.replace("_ret_1s", "")
        out[f"beta_gap_{short}"] = beta.to_numpy()
        out[f"pred_gap_{short}"] = (beta * s[x]).to_numpy()
    return out.replace([np.inf, -np.inf], np.nan)


def calendar_features(dates: pd.Series) -> pd.DataFrame:
    """Known-in-advance calendar fields; ``gap_days`` uses the observed date union."""
    unique = pd.Series(sorted(pd.unique(dates)))
    frame = pd.DataFrame({"date": unique})
    frame["dow"] = frame["date"].dt.dayofweek.astype(float)
    frame["gap_days"] = frame["date"].diff().dt.days.astype(float)
    frame["dom"] = frame["date"].dt.day.astype(float)
    frame["month"] = frame["date"].dt.month.astype(float)
    return frame


def cross_sectional_ranks(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Per-date percentile ranks over the stocks present that day (pre-open features only)."""
    present = [c for c in columns if c in frame.columns]
    ranks = frame.groupby("date")[present].rank(pct=True)
    ranks.columns = [f"xs_{c}" for c in present]
    return ranks


@dataclass
class FeatureFrame:
    frame: pd.DataFrame
    labels: pd.DataFrame
    groups: dict[str, list[str]]
    meta: dict = field(default_factory=dict)

    def columns(self, groups, exclude=()) -> list[str]:
        out = []
        for name in groups:
            out.extend(c for c in self.groups[name] if c not in exclude)
        if len(set(out)) != len(out):
            raise ValueError("duplicate feature columns across groups")
        return out


def build_feature_frame(data_root: str, *, max_date: str = "2026-09-30") -> FeatureFrame:
    """Full research frame keyed by (date, stock_id) for all panel rows <= max_date."""
    paths = _paths(data_root)
    max_ts = pd.Timestamp(max_date)
    panel = load_panel(data_root)
    panel = panel[panel["date"] <= max_ts].copy()
    panel_cols = panel_feature_columns(panel)
    stocks = load_teacher_stocks(data_root, max_date=max_ts)
    labels = build_labels(stocks)

    check = panel.dropna(subset=["label_intraday_return"]).merge(
        labels[["stock_id", "date", "r", "y"]], on=["stock_id", "date"], how="left")
    if check["r"].isna().any():
        raise ValueError("panel labels without matching teacher rows")
    if not np.allclose(check["r"], check["label_intraday_return"], rtol=1e-9, atol=1e-12):
        raise ValueError("panel intraday return disagrees with teacher prices")
    if (check["y"] != check["label_y"]).any():
        raise ValueError("panel y disagrees with teacher y")

    market = pd.read_csv(paths["market"], parse_dates=["date"])
    if FORBIDDEN_MARKET_COLUMNS & set(market.columns):
        raise ValueError("market table carries forbidden same-day teacher columns")
    market = market[market["date"] <= max_ts]
    market_1s = market[["date", *MARKET_1S_COLUMNS]].rename(columns={"^VIX": "vix_level"})
    market_cols = [c if c != "^VIX" else "vix_level" for c in MARKET_1S_COLUMNS]

    hist = stock_history_features(stocks)
    hist_cols = [c for c in hist.columns if c not in ("stock_id", "date")]
    beta = beta_features(stocks, market)
    beta_cols = [c for c in beta.columns if c not in ("stock_id", "date")]
    cal = calendar_features(panel["date"])
    cal_cols = [c for c in cal.columns if c != "date"]

    frame = panel[["date", "stock_id", "is_top50", "has_teacher_row", *panel_cols]].copy()
    frame = frame.merge(hist, on=["stock_id", "date"], how="left")
    frame = frame.merge(beta, on=["stock_id", "date"], how="left")
    frame = frame.merge(market_1s, on="date", how="left")
    frame = frame.merge(cal, on="date", how="left")
    ranks = cross_sectional_ranks(frame, XS_SOURCE_COLUMNS)
    frame = pd.concat([frame, ranks], axis=1)
    if len(frame) != len(panel):
        raise ValueError("feature joins changed the panel row count")
    groups = {
        "panel": panel_cols,
        "stock_hist": hist_cols,
        "market_1s": market_cols,
        "xs_rank": list(ranks.columns),
        "beta": beta_cols,
        "calendar": cal_cols,
    }
    for cols in groups.values():
        if any(c.startswith("label_") or c == "y" for c in cols):
            raise ValueError("label column leaked into a feature group")
    frame = frame.sort_values(["date", "stock_id"]).reset_index(drop=True)
    meta = {
        "feature_version": FEATURE_VERSION,
        "data_branch": DATA_BRANCH,
        "max_date": max_ts.date().isoformat(),
        "panel_sha256": sha256_file(paths["panel"]),
        "market_features_sha256": sha256_file(paths["market"]),
        "teacher_sha256": teacher_hashes(data_root),
        "readiness": "research_assumption",
    }
    return FeatureFrame(frame=frame, labels=labels, groups=groups, meta=meta)
