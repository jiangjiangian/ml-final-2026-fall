"""Date-only walk-forward folds, official scoring and date-level bootstrap for R3.

Folds never split one trading date across train and test. Training labels end at
least ``embargo`` trading days before each test block. Period guards make the
spent 2026-01..05 holdout, the Phase 1 target window and the final holdout
unreachable from development runs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from finpred.evaluation.official_score import evaluate_predictions

DEV_START = pd.Timestamp("2022-01-01")
DEV_END = pd.Timestamp("2025-12-31")
SPENT_HOLDOUT = (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-05-31"))
PHASE1_WINDOW = (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-30"))
FINAL_HOLDOUT = (pd.Timestamp("2026-10-01"), pd.Timestamp("2026-11-13"))

MODES = ("dev", "final_holdout", "phase1_forecast")


@dataclass(frozen=True)
class Fold:
    index: int
    train_end: str
    test_start: str
    test_end: str
    embargo_days: int

    def as_dict(self):
        return asdict(self)


def check_period(mode: str, test_start, test_end) -> None:
    """Refuse evaluation windows that the research protocol forbids."""
    start, end = pd.Timestamp(test_start), pd.Timestamp(test_end)
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if start > end:
        raise ValueError("test_start after test_end")
    if mode == "dev":
        if start < DEV_START - pd.Timedelta(days=366 * 2) or end > DEV_END:
            raise ValueError("dev evaluation must stay inside 2020..2025-12-31")
    elif mode == "final_holdout":
        if (start, end) != FINAL_HOLDOUT:
            raise ValueError("final holdout window is fixed at 2026-10-01..2026-11-13")
    elif mode == "phase1_forecast":
        if (start, end) != PHASE1_WINDOW:
            raise ValueError("phase1 forecast window is fixed at 2026-06-01..2026-09-30")


def block_starts(dates: list[pd.Timestamp], refit: str) -> list[int]:
    """Indices into ``dates`` where a new model is fitted."""
    if refit == "static":
        return [0]
    keys = []
    for day in dates:
        if refit == "monthly":
            keys.append((day.year, day.month))
        elif refit == "quarterly":
            keys.append((day.year, (day.month - 1) // 3))
        elif refit == "weekly":
            iso = day.isocalendar()
            keys.append((iso[0], iso[1]))
        elif refit == "daily":
            keys.append(day)
        else:
            raise ValueError(f"unknown refit cadence {refit!r}")
    return [i for i, key in enumerate(keys) if i == 0 or key != keys[i - 1]]


def make_folds(calendar, *, test_start, test_end, refit="monthly", embargo=5, mode="dev"):
    check_period(mode, test_start, test_end)
    if embargo < 5:
        raise ValueError("protocol requires at least 5 trading days of embargo")
    cal = sorted(pd.Timestamp(d) for d in pd.unique(pd.Series(calendar)))
    position = {d: i for i, d in enumerate(cal)}
    test_days = [d for d in cal if pd.Timestamp(test_start) <= d <= pd.Timestamp(test_end)]
    if not test_days:
        raise ValueError("no trading dates in the test window")
    starts = block_starts(test_days, refit)
    folds = []
    for n, s in enumerate(starts):
        e = (starts[n + 1] - 1) if n + 1 < len(starts) else len(test_days) - 1
        first = position[test_days[s]]
        train_end_pos = first - embargo - 1
        if train_end_pos < 0:
            raise ValueError("not enough history before the first test block")
        folds.append(Fold(n, cal[train_end_pos].date().isoformat(),
                          test_days[s].date().isoformat(), test_days[e].date().isoformat(),
                          embargo))
    return folds


def official_check(pred: pd.DataFrame, labels: pd.DataFrame):
    """Score with the project's single official scorer (exact key coverage)."""
    keyed = labels.set_index(["stock_id", "date"])
    rows_pred, rows_label = [], []
    for stock, day, p in zip(pred["stock_id"], pred["date"], pred["prediction"]):
        iso = pd.Timestamp(day).date().isoformat()
        rows_pred.append({"stock_id": stock, "target_date": iso, "prediction": int(p)})
        lab = keyed.loc[(stock, pd.Timestamp(day))]
        rows_label.append({"stock_id": stock, "target_date": iso, "y": int(lab["y"]),
                           "adj_open": float(lab["adj_open"]), "adj_close": float(lab["adj_close"])})
    return evaluate_predictions(rows_pred, rows_label)


def daily_table(pred: pd.DataFrame) -> pd.DataFrame:
    """Per-date contribution sums with the market/cross-sectional decomposition.

    contribution = (2p-1) r = (2p-1) m_t + (2p-1)(r - m_t), m_t = mean r over the
    scored keys of that date. Both parts are summed per date so ratios of sums
    reproduce the key-weighted official score.
    """
    frame = pred[["date", "prediction", "r"]].copy()
    frame["s"] = 2 * frame["prediction"].astype(int) - 1
    frame["m"] = frame.groupby("date")["r"].transform("mean")
    frame["c"] = frame["s"] * frame["r"]
    frame["c_mkt"] = frame["s"] * frame["m"]
    frame["c_xs"] = frame["s"] * (frame["r"] - frame["m"])
    frame["hit"] = (frame["prediction"].astype(int) == (frame["r"] > 0).astype(int)).astype(int)
    out = frame.groupby("date").agg(sum_c=("c", "sum"), sum_mkt=("c_mkt", "sum"),
                                    sum_xs=("c_xs", "sum"), n=("c", "size"),
                                    hits=("hit", "sum"), frac_up=("prediction", "mean"))
    return out.sort_index()


def moving_block_indices(n_days: int, *, block=5, reps=2000, seed=20261104):
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n_days / block)
    starts = rng.integers(0, max(n_days - block, 0) + 1, size=(reps, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)
    return idx[:, :n_days]


def bootstrap_ratio_ci(sums: np.ndarray, counts: np.ndarray, *, block=5, reps=2000,
                       seed=20261104, alpha=0.05):
    idx = moving_block_indices(len(sums), block=block, reps=reps, seed=seed)
    stats = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi), float(np.mean(stats > 0))


def paired_diff(daily_a: pd.DataFrame, daily_b: pd.DataFrame, **kw):
    """Key-weighted score difference A-B with a paired date-block bootstrap CI."""
    if not daily_a.index.equals(daily_b.index) or not np.array_equal(daily_a["n"], daily_b["n"]):
        raise ValueError("paired comparison requires identical scored dates and keys")
    diff = daily_a["sum_c"].to_numpy() - daily_b["sum_c"].to_numpy()
    n = daily_a["n"].to_numpy().astype(float)
    lo, hi, p_pos = bootstrap_ratio_ci(diff, n, **kw)
    return {"diff": float(diff.sum() / n.sum()), "ci95": [lo, hi], "p_boot_gt0": p_pos}


def summarize(daily: pd.DataFrame, *, block=5, reps=2000, seed=20261104) -> dict:
    n = daily["n"].to_numpy().astype(float)
    total = float(n.sum())
    score = float(daily["sum_c"].sum() / total)
    lo, hi, p_pos = bootstrap_ratio_ci(daily["sum_c"].to_numpy(), n, block=block, reps=reps, seed=seed)
    idx = daily.index
    monthly = (daily.groupby([idx.year, idx.month])[["sum_c", "n"]].sum())
    monthly_scores = (monthly["sum_c"] / monthly["n"])
    yearly = daily.groupby(idx.year)[["sum_c", "n"]].sum()
    yearly_scores = (yearly["sum_c"] / yearly["n"]).to_dict()
    worst_key = monthly_scores.idxmin()
    sub = {}
    for name, mask in (("2022_2024", (idx.year >= 2022) & (idx.year <= 2024)),
                       ("2025", idx.year == 2025),
                       ("2022_2023", (idx.year >= 2022) & (idx.year <= 2023)),
                       ("2024_2025", (idx.year >= 2024) & (idx.year <= 2025))):
        part = daily[mask]
        if len(part):
            sub[name] = float(part["sum_c"].sum() / part["n"].sum())
    return {
        "score": score,
        "ci95": [lo, hi],
        "p_boot_gt0": p_pos,
        "accuracy": float(daily["hits"].sum() / total),
        "market_part": float(daily["sum_mkt"].sum() / total),
        "cross_sectional_part": float(daily["sum_xs"].sum() / total),
        "frac_predicted_up": float((daily["frac_up"] * daily["n"]).sum() / total),
        "n_keys": int(total),
        "n_days": int(len(daily)),
        "first_day": idx.min().date().isoformat(),
        "last_day": idx.max().date().isoformat(),
        "yearly": {str(k): float(v) for k, v in yearly_scores.items()},
        "subperiods": sub,
        "months_positive": int((monthly_scores > 0).sum()),
        "months": int(len(monthly_scores)),
        "worst_month": {"month": f"{worst_key[0]}-{worst_key[1]:02d}",
                        "score": float(monthly_scores.min())},
        "monthly": {f"{y}-{m:02d}": float(v) for (y, m), v in monthly_scores.items()},
    }
