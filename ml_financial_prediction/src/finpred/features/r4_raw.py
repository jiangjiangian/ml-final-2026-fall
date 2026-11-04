"""Raw-data loading and pre-open as-of alignment for R4 concrete features.

Every concrete feature in R4 is computed in two steps:

1. on the source's *own* row/session sequence, a value that uses rows/sessions
   up to and including j ("after row j");
2. aligned to Taiwan target date t by taking the latest j that was known before
   08:10 on t:
   * teacher stock rows: the latest row with ``date < t`` (``stock_asof``);
   * teacher global rows: the latest row with ``date < t`` (``^TWII``/``^KS11``/
     ``TX_OI`` are same-day closes, so only earlier rows are allowed);
   * yfinance sessions: the latest session with ``date <= t - 1 calendar day``
     (``source_asof``; timing verified in the data branch ``schema.json``).

Because alignment never looks at whether row t exists, a stock without a teacher
row on t (e.g. suspended) does not change any day-t feature.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from finpred.features.r3_features import TEACHER_COLUMNS, TRAINING_LAST_DATE, sha256_file

GLOBAL_SAME_DAY = ("^TWII", "^KS11", "TX_OI")
EXTRA_SERIES = (
    "sox", "tsm_adr", "nvda", "usd_twd", "dxy", "us10y", "us13w", "etf_0050", "etf_0052",
    "etf_0055", "etf_006201", "dji", "n225", "hsi", "sse", "stoxx50e", "gdaxi", "wti", "gold",
)


@dataclass
class RawData:
    stocks: pd.DataFrame          # teacher rows (renamed columns), sorted by stock/date
    global_: pd.DataFrame         # teacher global rows (Training + Live), -1 -> NaN
    extra: dict                   # series_id -> native daily bars
    tw_calendar: pd.DatetimeIndex  # union of teacher stock dates
    top50: list
    meta: dict


def _read_dir(directory):
    frames = []
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        frame = pd.read_csv(path, parse_dates=["date"])
        frame.insert(0, "stock_id", os.path.basename(path)[:-4])
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _hash_dir(directory):
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        digest.update(os.path.basename(path).encode())
        digest.update(sha256_file(path).encode())
    return digest.hexdigest()


def load_raw(data_root: str, *, max_date="2026-09-30") -> RawData:
    root = os.path.join(os.path.abspath(data_root), "data")
    max_ts = pd.Timestamp(max_date)
    training = _read_dir(os.path.join(root, "teacher", "market"))
    if training["date"].max() != TRAINING_LAST_DATE:
        raise ValueError("unexpected teacher Training end date")
    parts = [training]
    g_parts = [pd.read_csv(os.path.join(root, "teacher", "global", "global_data.csv"), parse_dates=["date"])]
    if max_ts > TRAINING_LAST_DATE:
        live = _read_dir(os.path.join(root, "teacher_live", "market"))
        live = live[(live["date"] > TRAINING_LAST_DATE) & (live["date"] <= max_ts)].copy()
        values = [c for c in live.columns if c not in ("stock_id", "date")]
        # Any pending marker in a core field makes the whole row unknown.
        core = ["etl:adj_open", "etl:adj_close", "etl:adj_high", "etl:adj_low", "price:成交股數", "y"]
        pending = (live[core] == -1).any(axis=1)
        live.loc[pending, values] = np.nan
        parts.append(live)
        glive = pd.read_csv(os.path.join(root, "teacher_live", "global", "global_data.csv"), parse_dates=["date"])
        glive = glive[(glive["date"] > TRAINING_LAST_DATE) & (glive["date"] <= max_ts)].copy()
        gcols = [c for c in glive.columns if c != "date"]
        glive[gcols] = glive[gcols].where(glive[gcols] != -1)
        g_parts.append(glive)
    stocks = pd.concat(parts, ignore_index=True)
    stocks = stocks[stocks["date"] <= max_ts].rename(columns=TEACHER_COLUMNS)
    stocks = stocks[["stock_id", "date", *TEACHER_COLUMNS.values()]]
    if stocks.duplicated(["stock_id", "date"]).any():
        raise ValueError("duplicate teacher stock/date keys")
    stocks = stocks.sort_values(["stock_id", "date"]).reset_index(drop=True)
    global_ = pd.concat(g_parts, ignore_index=True)
    global_ = global_[global_["date"] <= max_ts].sort_values("date").reset_index(drop=True)
    if global_["date"].duplicated().any():
        raise ValueError("duplicate teacher global dates")
    extra = {}
    for sid in EXTRA_SERIES:
        frame = pd.read_csv(os.path.join(root, "extra", "yfinance", f"{sid}.csv"), parse_dates=["date"])
        extra[sid] = frame[frame["date"] <= max_ts].sort_values("date").reset_index(drop=True)
    info = json.load(open(os.path.join(root, "teacher", "info.json"), encoding="utf-8"))
    meta = {
        "teacher_market_sha256": _hash_dir(os.path.join(root, "teacher", "market")),
        "teacher_live_market_sha256": _hash_dir(os.path.join(root, "teacher_live", "market")),
        "extra_sha256": _hash_dir(os.path.join(root, "extra", "yfinance")),
        "max_date": max_ts.date().isoformat(),
    }
    return RawData(stocks=stocks, global_=global_, extra=extra,
                   tw_calendar=pd.DatetimeIndex(sorted(stocks["date"].unique())),
                   top50=list(info["Top50@Y"]), meta=meta)


def stock_asof(per_row: pd.DataFrame, grid: pd.DataFrame, columns) -> pd.DataFrame:
    """Values computed 'after row j' -> target (stock, t) using the latest row with date < t."""
    left = grid[["stock_id", "date"]].sort_values("date").reset_index()
    right = per_row[["stock_id", "date", *columns]].sort_values("date")
    merged = pd.merge_asof(left, right.rename(columns={"date": "_row_date"}), left_on="date",
                           right_on="_row_date", by="stock_id", allow_exact_matches=False,
                           direction="backward")
    merged = merged.set_index("index").sort_index()
    if (merged["_row_date"] >= merged["date"]).any():
        raise AssertionError("stock as-of used a row on or after the target date")
    out = merged[["stock_id", "date", *columns]].copy()
    out["row_age_days"] = (merged["date"] - merged["_row_date"]).dt.days
    return out


def source_asof(series: pd.DataFrame, targets: pd.Series, columns, *, prefix: str,
                lag_days: int = 1) -> pd.DataFrame:
    """Native-session values -> target t using the last session with date <= t - lag_days."""
    left = pd.DataFrame({"date": pd.to_datetime(pd.Series(targets).unique())}).sort_values("date")
    left["_cutoff"] = left["date"] - pd.Timedelta(days=lag_days)
    right = series[["date", *columns]].rename(columns={"date": "_session"}).sort_values("_session")
    merged = pd.merge_asof(left, right, left_on="_cutoff", right_on="_session",
                           allow_exact_matches=True, direction="backward")
    if (merged["_session"] > merged["_cutoff"]).any():
        raise AssertionError("source as-of used a session after the cutoff")
    out = merged[["date"]].copy()
    for col in columns:
        out[f"{prefix}{col}"] = merged[col].to_numpy()
    out[f"{prefix}age_days"] = (merged["date"] - merged["_session"]).dt.days.to_numpy()
    return out


def global_prev_row(global_: pd.DataFrame, targets: pd.Series, columns, *, prefix="g_",
                    same_row_ok=False) -> pd.DataFrame:
    """Teacher global values aligned to target t.

    ``same_row_ok=False`` (default, required for ^TWII/^KS11/TX_OI): latest row with
    date < t. ``same_row_ok=True`` is only for ^VIX/^IXIC/^GSPC, whose row-t value is
    the previous US close; whether row t is published before 08:10 is a production
    assumption that must be checked against the Live feed.
    """
    if same_row_ok and set(columns) & set(GLOBAL_SAME_DAY):
        raise ValueError("^TWII/^KS11/TX_OI are same-day closes; only earlier rows are allowed")
    left = pd.DataFrame({"date": pd.to_datetime(pd.Series(targets).unique())}).sort_values("date")
    right = global_[["date", *columns]].rename(columns={"date": "_row"}).sort_values("_row")
    merged = pd.merge_asof(left, right, left_on="date", right_on="_row",
                           allow_exact_matches=same_row_ok, direction="backward")
    if (merged["_row"] > merged["date"]).any() or (
            not same_row_ok and (merged["_row"] >= merged["date"]).any()):
        raise AssertionError("global as-of used a forbidden row")
    out = merged[["date"]].copy()
    for col in columns:
        out[f"{prefix}{col}"] = merged[col].to_numpy()
    out[f"{prefix}row_age_days"] = (merged["date"] - merged["_row"]).dt.days.to_numpy()
    return out


def trading_grid(raw: RawData, *, universe="all100") -> pd.DataFrame:
    """Complete (date, stock) grid over the Taiwan calendar, keeping missing teacher rows."""
    stocks = sorted(raw.stocks["stock_id"].unique()) if universe == "all100" else sorted(raw.top50)
    grid = pd.MultiIndex.from_product([raw.tw_calendar, stocks], names=["date", "stock_id"]).to_frame(index=False)
    grid["is_top50"] = grid["stock_id"].isin(raw.top50).astype(int)
    return grid
