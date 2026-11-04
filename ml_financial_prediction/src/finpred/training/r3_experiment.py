"""Run one R3 research configuration end to end and log every attempt.

Outputs that contain per-key predictions stay outside Git (``out_root``). Only
aggregate metrics are appended to the in-repo attempt log, so failed and
negative attempts are counted exactly like successful ones.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pickle
import subprocess
import time
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd

from finpred.evaluation import walkforward as wf
from finpred.features import r3_features as rf
from finpred.models.r3_estimators import build_model

PROJECT = Path(__file__).resolve().parents[3]
CODE_FILES = (
    "src/finpred/features/r3_features.py",
    "src/finpred/evaluation/walkforward.py",
    "src/finpred/evaluation/official_score.py",
    "src/finpred/models/r3_estimators.py",
    "src/finpred/training/r3_experiment.py",
    "src/finpred/training/r3_tune.py",
)
PACKAGES = ("numpy", "pandas", "scikit-learn", "lightgbm", "catboost", "xgboost", "torch")

BASELINES = {
    "all0": {"family": "rule", "rule": "all0", "feature_groups": []},
    "all1": {"family": "rule", "rule": "all1", "feature_groups": []},
    "prevday": {"family": "rule", "rule": "prevday", "feature_groups": []},
    "ridge_panel": {"family": "ridge", "params": {"alpha": 1.0}, "feature_groups": ["panel"]},
    "lgbm_panel": {
        "family": "lightgbm", "objective": "regression", "feature_groups": ["panel"],
        "params": {"n_estimators": 300, "learning_rate": 0.03, "num_leaves": 15,
                   "min_child_samples": 200, "subsample": 0.8, "subsample_freq": 1,
                   "colsample_bytree": 0.8, "reg_lambda": 1.0},
    },
}

DEFAULTS = {
    "mode": "dev", "test_start": "2022-01-01", "test_end": "2025-12-31",
    "refit": "monthly", "embargo": 5, "train_start": "2020-01-02",
    "train_universe": "all100", "seeds": [42], "objective": "regression",
    "feature_exclude": [], "max_date": "2026-09-30",
}


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


# Hash the source at import time: the hashes must describe the code this
# process actually runs, even if files are edited while a long batch runs.
_IMPORT_FILE_HASHES = {rel: _sha_bytes((PROJECT / rel).read_bytes()) for rel in CODE_FILES}


def code_state() -> dict:
    files = dict(_IMPORT_FILE_HASHES)
    changed = sorted(rel for rel in CODE_FILES
                     if _sha_bytes((PROJECT / rel).read_bytes()) != files[rel])
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", *CODE_FILES],
                                    cwd=PROJECT, capture_output=True, text=True,
                                    check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    return {"git_head": head, "dirty_r3_files": dirty, "files_sha256": files,
            "hash_basis": "import_time", "edited_since_import": changed}


def package_versions() -> dict:
    out = {}
    for name in PACKAGES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None
    return out


def load_features(data_root: str, out_root: str, *, max_date: str) -> rf.FeatureFrame:
    """Build or reuse a cached feature frame keyed by input and code hashes."""
    paths = rf._paths(data_root)
    key = _sha_bytes(canonical({
        "panel": rf.sha256_file(paths["panel"]),
        "market": rf.sha256_file(paths["market"]),
        "teacher": rf.teacher_hashes(data_root),
        "code": _sha_bytes((PROJECT / CODE_FILES[0]).read_bytes()),
        "max_date": max_date,
    }))[:16]
    cache = Path(out_root) / "cache" / f"features-{rf.FEATURE_VERSION}-{key}.pkl"
    if cache.exists():
        with open(cache, "rb") as handle:
            return pickle.load(handle)
    frame = rf.build_feature_frame(data_root, max_date=max_date)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    with open(tmp, "wb") as handle:
        pickle.dump(frame, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, cache)
    return frame


def resolve(config: dict) -> dict:
    merged = copy.deepcopy(DEFAULTS)
    merged.update(copy.deepcopy(config))
    if merged["mode"] != "dev":
        raise ValueError("this runner only executes development walk-forward runs")
    if merged["train_universe"] not in ("all100", "top50"):
        raise ValueError(f"unknown train_universe {merged['train_universe']!r}")
    if merged["refit"] not in ("monthly", "quarterly", "weekly", "daily", "static"):
        raise ValueError(f"unknown refit cadence {merged['refit']!r}")
    return merged


def _key_hash(pred: pd.DataFrame) -> str:
    keys = sorted(f"{s}|{pd.Timestamp(d).date().isoformat()}" for s, d in zip(pred["stock_id"], pred["date"]))
    return _sha_bytes("\n".join(keys).encode())


def _label_hash(pred: pd.DataFrame) -> str:
    rows = sorted(f"{s}|{pd.Timestamp(d).date().isoformat()}|{float(r)!r}"
                  for s, d, r in zip(pred["stock_id"], pred["date"], pred["r"]))
    return _sha_bytes("\n".join(rows).encode())


def run_predictions(cfg: dict, ff: rf.FeatureFrame, *, threads=4):
    """Walk-forward predictions for every scored test key of the configuration."""
    if cfg.get("mode") != "dev":
        raise ValueError("run_predictions only serves development walk-forward runs")
    model_spec = {k: cfg[k] for k in ("family", "rule", "params", "objective", "market_columns",
                                      "stock_model", "components", "weights") if k in cfg}
    if model_spec.get("family") == "blend":
        model_spec["components"] = [
            {**c, "_columns": ff.columns(c["feature_groups"])} if c.get("feature_groups") else dict(c)
            for c in model_spec["components"]]
    if model_spec.get("family") == "two_head":
        resolved = []
        for item in model_spec["market_columns"]:
            if item == "panel_market":  # panel lag columns that are identical across stocks
                resolved += [c for c in ff.groups["panel"] if not c.startswith("stock_")]
            elif item in ff.groups:
                resolved += ff.groups[item]
            else:
                resolved.append(item)
        model_spec["market_columns"] = list(dict.fromkeys(resolved))
        stock = dict(model_spec["stock_model"])
        if stock.get("feature_groups"):
            stock["_columns"] = ff.columns(stock["feature_groups"])
        model_spec["stock_model"] = stock
    columns = ff.columns(cfg.get("feature_groups", []), exclude=cfg["feature_exclude"])
    probe = build_model(model_spec, threads=threads)
    needed = list(dict.fromkeys([*columns, *probe.needs]))
    data = ff.frame.merge(ff.labels[["stock_id", "date", "r", "y"]], on=["stock_id", "date"], how="left")
    labelled = data["r"].notna()
    calendar = data["date"].drop_duplicates().sort_values()
    folds = wf.make_folds(calendar, test_start=cfg["test_start"], test_end=cfg["test_end"],
                          refit=cfg["refit"], embargo=cfg["embargo"], mode=cfg["mode"])
    universe = data["is_top50"] == 1 if cfg["train_universe"] == "top50" else np.ones(len(data), bool)
    train_start = pd.Timestamp(cfg["train_start"])
    outputs, fold_log = [], []
    for fold in folds:
        train_end = pd.Timestamp(fold.train_end)
        test_start, test_end = pd.Timestamp(fold.test_start), pd.Timestamp(fold.test_end)
        if train_end >= test_start:
            raise AssertionError("training labels overlap the test block")
        tr = labelled & universe & (data["date"] >= train_start) & (data["date"] <= train_end)
        te = labelled & (data["is_top50"] == 1) & (data["date"] >= test_start) & (data["date"] <= test_end)
        train, test = data[tr], data[te]
        if train["date"].max() >= test["date"].min():
            raise AssertionError("same or later date in train and test")
        started = time.perf_counter()
        decision = np.zeros(len(test))
        for seed in cfg["seeds"]:
            model = build_model(model_spec, threads=threads)
            if getattr(model, "uses_dates", False):
                model.fit(train[needed], train["r"].to_numpy(), train["y"].to_numpy(), seed=seed,
                          dates=train["date"].to_numpy())
                decision += model.decision(test[needed], dates=test["date"].to_numpy())
            else:
                model.fit(train[needed], train["r"].to_numpy(), train["y"].to_numpy(), seed=seed)
                decision += model.decision(test[needed])
        decision /= len(cfg["seeds"])
        if not np.all(np.isfinite(decision)):
            raise ValueError("model produced non-finite decisions")
        elapsed = time.perf_counter() - started
        outputs.append(pd.DataFrame({
            "stock_id": test["stock_id"].to_numpy(), "date": test["date"].to_numpy(),
            "decision": decision, "prediction": (decision > 0).astype(int),
            "r": test["r"].to_numpy(), "y": test["y"].astype(int).to_numpy(), "fold": fold.index,
        }))
        fold_log.append({**fold.as_dict(), "n_train": int(tr.sum()), "n_test": int(te.sum()),
                         "fit_predict_seconds": round(elapsed, 3)})
    pred = pd.concat(outputs, ignore_index=True)
    if pred.duplicated(["stock_id", "date"]).any():
        raise AssertionError("duplicate predicted keys across folds")
    window = (data["is_top50"] == 1) & (data["date"] >= pd.Timestamp(cfg["test_start"])) & \
        (data["date"] <= pd.Timestamp(cfg["test_end"]))
    expected = set(zip(data.loc[window & labelled, "stock_id"], data.loc[window & labelled, "date"]))
    if set(zip(pred["stock_id"], pred["date"])) != expected:
        raise AssertionError("predicted keys differ from the labelled Top50 keys of the window")
    pred.attrs["unlabelled_top50_keys_excluded"] = int((window & ~labelled).sum())
    return pred, fold_log, needed


def verify_official(pred: pd.DataFrame, ff: rf.FeatureFrame, daily: pd.DataFrame) -> dict:
    result = wf.official_check(pred, ff.labels)
    fast = float(daily["sum_c"].sum() / daily["n"].sum())
    if not math.isclose(result.score, fast, rel_tol=1e-9, abs_tol=1e-13):
        raise AssertionError(f"official score {result.score} != fast score {fast}")
    return {"official_score": result.score, "official_accuracy": result.accuracy,
            "official_count": result.count}


def window_tag(cfg: dict) -> str:
    return f"{cfg['mode']}_{cfg['test_start']}_{cfg['test_end']}_{cfg['refit']}_e{cfg['embargo']}"


def append_attempt(log_path: Path, record: dict) -> int:
    """Append under an exclusive lock so concurrent runs never share a number."""
    import fcntl

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(log_path) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
        record = {"attempt": len([line for line in existing if line.strip()]) + 1, **record}
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record["attempt"]


def _compact(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k != "monthly"}


def execute(config: dict, *, data_root: str, out_root: str, log_path: Path, threads=4,
            baseline_daily: dict | None = None, ff: rf.FeatureFrame | None = None) -> dict:
    """Run one configuration, log it as an attempt and return the full report."""
    started = datetime.now(timezone.utc)
    base_record = {
        "name": config.get("name"), "stage": config.get("stage"),
        "hypothesis": config.get("hypothesis"), "started_utc": started.isoformat(timespec="seconds"),
        "config": config, "code": code_state(), "packages": package_versions(),
    }
    try:
        cfg = resolve(config)
        base_record.update(config=cfg, config_sha256=_sha_bytes(canonical(cfg)))
        ff = ff or load_features(data_root, out_root, max_date=cfg["max_date"])
        if ff.meta.get("max_date") != cfg["max_date"]:
            raise ValueError("config max_date differs from the loaded feature frame")
        pred, folds, columns = run_predictions(cfg, ff, threads=threads)
        daily = wf.daily_table(pred)
        official = verify_official(pred, ff, daily)
        summary = wf.summarize(daily)
        keys, labels_hash = _key_hash(pred), _label_hash(pred)
        comparisons = {}
        for name, other in (baseline_daily or {}).items():
            if other.get("key_hash") != keys or other.get("label_hash") != labels_hash:
                comparisons[name] = {"error": "different scored keys or outcomes; not comparable"}
                continue
            comparisons[name] = {"baseline_score": other["summary"]["score"],
                                 **wf.paired_diff(daily, other["daily"])}
        run_dir = Path(out_root) / "runs" / f"{started.strftime('%Y%m%dT%H%M%S')}-{cfg['name']}"
        run_dir.mkdir(parents=True, exist_ok=False)
        pred.assign(date=pred["date"].dt.strftime("%Y-%m-%d")).to_csv(
            run_dir / "predictions.csv.gz", index=False)
        daily.to_csv(run_dir / "daily.csv")
        report = {
            **base_record, "status": "ok", "feature_columns": columns, "n_features": len(columns),
            "data": ff.meta, "key_hash": keys, "label_hash": labels_hash, "official": official, "summary": summary,
            "paired_vs_baselines": comparisons, "folds": folds,
            "total_fit_predict_seconds": round(sum(f["fit_predict_seconds"] for f in folds), 2),
            "unlabelled_top50_keys_excluded": pred.attrs.get("unlabelled_top50_keys_excluded"),
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_dir": str(run_dir),
        }
        (run_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
        log_record = {k: v for k, v in report.items() if k not in ("folds", "feature_columns")}
        log_record["summary"] = _compact(summary)
        log_record["fold_count"] = len(folds)
        report["attempt"] = append_attempt(log_path, log_record)
        report["daily"] = daily
        return report
    except Exception as exc:  # every failure is still an attempt
        append_attempt(log_path, {**base_record, "status": "failed",
                                  "error": f"{type(exc).__name__}: {exc}",
                                  "traceback_tail": traceback.format_exc().splitlines()[-6:],
                                  "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        raise


def load_baseline_reports(out_root: str, cfg: dict, data_meta: dict | None = None) -> dict:
    """Latest successful canonical baselines for the same window, data and spec.

    A report counts as baseline ``name`` only if its resolved config hash equals the
    canonical ``baseline_config(name, window)`` and (when given) its data metadata
    equals ``data_meta``; key and outcome hashes are re-checked at comparison time.
    """
    found = {}
    runs = sorted((Path(out_root) / "runs").glob("*")) if (Path(out_root) / "runs").exists() else []
    window = resolve(cfg)
    expected = {name: _sha_bytes(canonical(resolve(baseline_config(name, window))))
                for name in BASELINES}
    for run in runs:
        report_path = run / "report.json"
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text())
        name = str(report.get("config", {}).get("name", "")).removeprefix("baseline_")
        if report.get("status") != "ok" or name not in expected:
            continue
        if report.get("config_sha256") != expected[name]:
            continue
        if data_meta is not None and report.get("data") != data_meta:
            continue
        daily = pd.read_csv(run / "daily.csv", index_col=0, parse_dates=[0])
        found[name] = {"key_hash": report["key_hash"], "label_hash": report.get("label_hash"),
                       "summary": report["summary"], "daily": daily}
    return found


def baseline_config(name: str, window: dict) -> dict:
    spec = copy.deepcopy(BASELINES[name])
    return {"name": f"baseline_{name}", "stage": "R3-0", "hypothesis": "baseline",
            **{k: window[k] for k in ("test_start", "test_end", "refit", "embargo") if k in window},
            **spec}
