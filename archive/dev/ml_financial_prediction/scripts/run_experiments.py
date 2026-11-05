"""Run frozen date-fold comparisons; research assumptions need explicit opt-in."""

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.evaluation.official_score import evaluate_predictions
from finpred.inference.predict import predict_rows
from finpred.models.estimators import FAMILIES, OBJECTIVES
from finpred.training.fit import (
    fit_model,
    save_model_bundle,
    target_cutoff,
    validate_table,
)

DEFAULT_FOLDS = [
    {"name": "2025Q1", "start": "2025-01-01", "end": "2025-04-01"},
    {"name": "2025Q2", "start": "2025-04-01", "end": "2025-07-01"},
    {"name": "2025Q3", "start": "2025-07-01", "end": "2025-10-01"},
    {"name": "2025Q4", "start": "2025-10-01", "end": "2026-01-01"},
]


def code_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), *[
        root / "src/finpred" / name for name in (
            "training/fit.py", "models/estimators.py", "inference/predict.py",
            "evaluation/official_score.py", "labels/intraday.py", "data/training_table.py",
        )
    ]]
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def diagnostics(predictions, labels):
    result = asdict(evaluate_predictions(predictions, labels))
    months = sorted({r["target_date"][:7] for r in labels})
    result["monthly_scores"] = {
        month: evaluate_predictions(
            [r for r in predictions if r["target_date"].startswith(month)],
            [r for r in labels if r["target_date"].startswith(month)],
        ).score for month in months
    }
    return result


def run_experiments(
    table,
    out_dir,
    *,
    families=FAMILIES,
    objectives=OBJECTIVES,
    folds=None,
    allow_research=False,
    include_holdout=False,
    seed=42,
    epochs=8,
    loaded_input_bytes=None,
):
    started_at, started = datetime.now(timezone.utc).isoformat(), perf_counter()
    source_hashes = code_hashes()
    rows, _ = validate_table(table, allow_research=allow_research)
    if (not families or not objectives or len(set(families)) != len(families)
            or len(set(objectives)) != len(objectives)
            or set(families) - set(FAMILIES) or set(objectives) - set(OBJECTIVES)):
        raise ValueError("unique supported model families and objectives required")
    if loaded_input_bytes is not None and json.loads(loaded_input_bytes) != table:
        raise ValueError("loaded input buffer disagrees with the experiment table")
    folds = DEFAULT_FOLDS if folds is None else folds
    if not folds or len({f["name"] for f in folds}) != len(folds):
        raise ValueError("fold names must be nonempty and unique")
    previous_end = None
    for fold in folds:
        begin, end = date.fromisoformat(fold["start"]), date.fromisoformat(fold["end"])
        if begin >= end or previous_end is not None and begin < previous_end:
            raise ValueError("validation folds must be ordered, nonempty and disjoint")
        if include_holdout and end > date(2026, 1, 1):
            raise ValueError("validation must precede the January-May 2026 holdout")
        previous_end = end
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError(
            "experiment directory must be empty; previous results are immutable"
        )
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.chmod(0o700)
    results, all_predictions, fold_evidence = [], [], []
    for fold in folds:
        train = [r for r in rows if "2020-01-01" <= r["target_date"] < fold["start"]]
        validation = [
            r for r in rows if fold["start"] <= r["target_date"] < fold["end"]
        ]
        if not train or not validation:
            raise ValueError(
                "every requested fold requires earlier training and validation rows"
            )
        cutoff = min(target_cutoff(r) for r in validation)
        unavailable = {
            r["target_date"]
            for r in train
            if r.get("label_available_at") is not None
            and datetime.fromisoformat(
                r["label_available_at"].replace("Z", "+00:00")
            )
            > cutoff
        }
        train = [r for r in train if r["target_date"] not in unavailable]
        if not train:
            raise ValueError("no training data released before fold cutoff")
        fold_evidence.append({
            "fold": fold["name"], "fit_cutoff": cutoff.isoformat(),
            "training_dates": [min(r["target_date"] for r in train), max(r["target_date"] for r in train)],
            "training_rows": len(train), "validation_rows": len(validation),
            "excluded_late_label_dates": sorted(unavailable),
            "validation_keys_sha256": hashlib.sha256(json.dumps(
                sorted((r["stock_id"], r["target_date"]) for r in validation)
            ).encode()).hexdigest(),
            "training_missing_fraction": {
                f: sum(r[f] is None for r in train) / len(train) for f in table["feature_columns"]
            },
        })
        for name, value in [
            ("always_0", 0),
            ("always_1", 1),
            ("train_majority", int(sum(r["y"] for r in train) > len(train) / 2)),
        ]:
            predictions = [
                dict(
                    stock_id=r["stock_id"],
                    target_date=r["target_date"],
                    prediction=value,
                )
                for r in validation
            ]
            results.append(
                dict(
                    fold=fold["name"],
                    family=name,
                    objective="baseline",
                    **diagnostics(predictions, validation),
                )
            )
        for family in families:
            for objective in objectives:
                fit_started = perf_counter()
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    bundle = fit_model(
                        dict(table, rows=train),
                        fit_cutoff=cutoff,
                        family=family,
                        objective=objective,
                        seed=seed,
                        allow_research=allow_research,
                        epochs=epochs,
                    )
                fit_seconds = perf_counter() - fit_started
                inference_started = perf_counter()
                predictions = predict_rows(bundle, validation)
                inference_seconds = perf_counter() - inference_started
                all_predictions.extend(
                    dict(p, fold=fold["name"], family=family, objective=objective)
                    for p in predictions
                )
                score = diagnostics(predictions, validation)
                results.append(
                    dict(
                        fold=fold["name"],
                        family=family,
                        objective=objective,
                        training_rows=len(train),
                        fit_seconds=fit_seconds,
                        inference_seconds=inference_seconds,
                        warnings=sorted(set(str(w.message) for w in caught)),
                        **score,
                    )
                )
                checkpoint = out / "progress.json.tmp"
                checkpoint.write_text(
                    json.dumps(
                        {"status": "running", "results": results},
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                )
                checkpoint.chmod(0o600)
                checkpoint.replace(out / "progress.json")
    pairs = [(f, o) for f in families for o in objectives]
    averages = {
        pair: sum(
            r["score"] * r["count"]
            for r in results
            if (r["family"], r["objective"]) == pair
        )
        / sum(r["count"] for r in results if (r["family"], r["objective"]) == pair)
        for pair in pairs
    }
    winner = max(pairs, key=lambda p: (averages[p], -pairs.index(p)))
    report = {
        "schema_version": "experiment-report-v1",
        "readiness": table["readiness"],
        "availability_evidence": table["availability_evidence"],
        "production_performance_claim": False,
        "seed": seed,
        "feature_columns": table["feature_columns"],
        "feature_version": table["feature_version"],
        "input_table_sha256": hashlib.sha256(
            json.dumps(
                table, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest(),
        "folds": folds,
        "fold_evidence": fold_evidence,
        "code_sha256": source_hashes,
        "input_payload_sha256": hashlib.sha256(loaded_input_bytes).hexdigest() if loaded_input_bytes is not None else None,
        "input_payload_provenance": "exact parsed bytes" if loaded_input_bytes is not None else "API object only; no byte-level provenance supplied",
        "package_versions": {name: version(name) for name in (
            "scikit-learn", "numpy", "joblib", *(["torch"] if "gru" in families else [])
        )},
        "python_version": sys.version,
        "started_at": started_at,
        "stock_universe": sorted({r["stock_id"] for r in rows}),
        "epochs": epochs,
        "results": results,
        "validation_selected_configuration": dict(
            family=winner[0], objective=winner[1]
        ),
        "selection_metric": "pooled official score over frozen validation folds",
        "holdout_evaluated": False,
    }
    if include_holdout:
        train = [r for r in rows if "2020-01-01" <= r["target_date"] < "2026-01-01"]
        held_out = [r for r in rows if "2026-01-01" <= r["target_date"] < "2026-06-01"]
        if not train or not held_out:
            raise ValueError("holdout requires 2026 January-May data")
        cutoff = min(target_cutoff(r) for r in held_out)
        bundle = fit_model(
            dict(table, rows=train),
            fit_cutoff=cutoff,
            family=winner[0],
            objective=winner[1],
            seed=seed,
            allow_research=allow_research,
            epochs=epochs,
        )
        predictions = predict_rows(bundle, held_out)
        report["holdout"] = diagnostics(predictions, held_out)
        report["holdout_evaluated"] = True
        report["holdout_policy"] = (
            "Winner fixed using 2025 validation before this one pass; do not tune against holdout."
        )
        save_model_bundle(bundle, out / "selected_model")
        all_predictions.extend(
            dict(p, fold="2026JanMay_holdout", family=winner[0], objective=winner[1])
            for p in predictions
        )
    if code_hashes() != source_hashes:
        raise ValueError("experiment source changed during execution; results are not finalized")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["elapsed_seconds"] = perf_counter() - started
    for filename, value in [
        ("report.json", report),
        ("predictions.json", all_predictions),
    ]:
        p = out / filename
        p.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        p.chmod(0o600)
    (out / "progress.json").unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--families", default=",".join(FAMILIES))
    parser.add_argument("--objectives", default=",".join(OBJECTIVES))
    parser.add_argument("--folds", type=Path)
    parser.add_argument("--research-if-unverified", action="store_true")
    parser.add_argument("--include-holdout", action="store_true")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if any(
        (p / ".git").exists()
        for p in [args.out_dir.resolve(), *args.out_dir.resolve().parents]
    ):
        parser.error("private experiment artifacts must be outside Git checkout")
    try:
        payload = args.table.read_bytes()
        table = json.loads(payload)
        report = run_experiments(
            table,
            args.out_dir,
            families=tuple(args.families.split(",")),
            objectives=tuple(args.objectives.split(",")),
            folds=json.loads(args.folds.read_text()) if args.folds else None,
            allow_research=args.research_if_unverified,
            include_holdout=args.include_holdout,
            seed=args.seed,
            epochs=args.epochs,
            loaded_input_bytes=payload,
        )
        print(
            json.dumps(
                {
                    "status": "evaluated",
                    "readiness": report["readiness"],
                    "selected": report["validation_selected_configuration"],
                    "holdout_evaluated": report["holdout_evaluated"],
                    "report": str(args.out_dir / "report.json"),
                }
            )
        )
    except (ValueError, OSError, ImportError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
