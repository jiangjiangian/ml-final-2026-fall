"""Optuna hyper-parameter search confined to an early tuning window (R3-3).

Protocol: trials are scored only on walk-forward folds inside ``tune_start..tune_end``
(default 2022-01..2023-12, quarterly refits). The chosen parameters are then run
once as an ordinary development attempt; its 2024-2025 sub-period is the
out-of-tuning confirmation. The study itself is logged as one attempt that
records every trial, so search effort is never hidden.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from finpred.evaluation import walkforward as wf
from finpred.training import r3_experiment as rx

SPACES = {
    "lightgbm": {
        "num_leaves": ("int_log", 7, 63),
        "learning_rate": ("float_log", 0.01, 0.1),
        "n_estimators": ("int", 100, 600),
        "min_child_samples": ("int_log", 50, 1000),
        "colsample_bytree": ("float", 0.3, 1.0),
        "subsample": ("float", 0.5, 1.0),
        "reg_lambda": ("float_log", 1e-3, 30.0),
    },
}
FIXED = {"lightgbm": {"subsample_freq": 1}}


def _suggest(trial, space):
    params = {}
    for name, (kind, lo, hi) in space.items():
        if kind == "int":
            params[name] = trial.suggest_int(name, lo, hi)
        elif kind == "int_log":
            params[name] = trial.suggest_int(name, lo, hi, log=True)
        elif kind == "float":
            params[name] = trial.suggest_float(name, lo, hi)
        else:
            params[name] = trial.suggest_float(name, lo, hi, log=True)
    return params


def tune(base_cfg: dict, *, data_root: str, out_root: str, log_path: Path, n_trials=30,
         tune_start="2022-01-01", tune_end="2023-12-31", refit="quarterly", threads=4,
         seed=42) -> dict:
    import optuna

    family = base_cfg["family"]
    space = SPACES[family]
    started = datetime.now(timezone.utc)
    ff = rx.load_features(data_root, out_root, max_date=rx.DEFAULTS["max_date"])
    trials = []

    def objective(trial):
        params = {**FIXED.get(family, {}), **_suggest(trial, space)}
        cfg = rx.resolve({**copy.deepcopy(base_cfg), "params": params, "test_start": tune_start,
                          "test_end": tune_end, "refit": refit})
        pred, _, _ = rx.run_predictions(cfg, ff, threads=threads)
        daily = wf.daily_table(pred)
        score = float(daily["sum_c"].sum() / daily["n"].sum())
        trials.append({"number": trial.number, "params": params, "score": score})
        return score

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    try:
        # catch=: a failing trial is recorded as failed instead of aborting the study.
        study.optimize(objective, n_trials=n_trials, catch=(Exception,))
        failed = [t.number for t in study.trials if t.state.name == "FAIL"]
        best = {**FIXED.get(family, {}), **study.best_params}
    except Exception as exc:  # the study itself failed: still log every scored trial
        rx.append_attempt(log_path, {
            "name": f"{base_cfg['name']}_optuna_study", "stage": base_cfg.get("stage", "R3-3"),
            "status": "failed", "error": f"{type(exc).__name__}: {exc}", "trials": trials,
            "started_utc": started.isoformat(timespec="seconds"),
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        raise
    record = {
        "name": f"{base_cfg['name']}_optuna_study", "stage": base_cfg.get("stage", "R3-3"),
        "hypothesis": "hyper-parameter search on tuning window only",
        "started_utc": started.isoformat(timespec="seconds"), "status": "ok",
        "config": {"base": base_cfg, "tune_start": tune_start, "tune_end": tune_end,
                   "refit": refit, "n_trials": n_trials, "sampler": "TPE", "seed": seed},
        "code": rx.code_state(), "packages": rx.package_versions(), "data": ff.meta,
        "best_params": best, "best_tuning_score": study.best_value, "trials": trials,
        "failed_trials": failed,
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out = Path(out_root) / "studies"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{started.strftime('%Y%m%dT%H%M%S')}-{base_cfg['name']}.json").write_text(
        json.dumps(record, indent=1))
    record["attempt"] = rx.append_attempt(log_path, record)
    return record
