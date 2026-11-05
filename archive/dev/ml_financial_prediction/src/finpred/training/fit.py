"""Explicit-evidence training tables and immutable model bundles.

Research-assumption tables can be evaluated only with an explicit opt-in; their
bundles are never production eligible. This validates declarations and chronology,
not the truth of a caller's source-publication evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from importlib.metadata import version
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from finpred.labels.intraday import aware_datetime, finite_number, row_key
from finpred.models.estimators import OBJECTIVES, fit_estimator, make_estimator

FORBIDDEN_FEATURES = {
    "y",
    "adj_open",
    "adj_close",
    "target_intraday_return",
    "etl:adj_open",
    "etl:adj_close",
    "etl:adj_high",
    "etl:adj_low",
}


def target_cutoff(row):
    key = row_key(row)
    value = aware_datetime(row.get("feature_cutoff"), name="feature_cutoff")
    local = value.astimezone(ZoneInfo("Asia/Taipei"))
    if local.date().isoformat() != key[1] or (
        local.hour,
        local.minute,
        local.second,
        local.microsecond,
    ) > (9, 0, 0, 0):
        raise ValueError("feature cutoff must be on its target date by 09:00 Taipei")
    return value


def validate_table(table, *, allow_research=False):
    if table.get("schema_version") != "training-table-v1":
        raise ValueError("expected training-table-v1")
    features = table.get("feature_columns")
    if (
        not isinstance(features, list)
        or not features
        or len(set(features)) != len(features)
    ):
        raise ValueError("feature_columns must be a nonempty unique ordered list")
    if any(
        not isinstance(f, str) or not f or f in FORBIDDEN_FEATURES for f in features
    ):
        raise ValueError("outcome columns cannot be input features")
    if (
        not isinstance(table.get("feature_version"), str)
        or not table["feature_version"]
    ):
        raise ValueError("feature_version is required")
    readiness = table.get("readiness")
    if readiness not in {"verified", "research_assumption", "synthetic"}:
        raise ValueError("explicit table readiness is required")
    if readiness == "research_assumption" and not allow_research:
        raise ValueError(
            "unverified historical evidence requires explicit research opt-in"
        )
    if (
        not isinstance(table.get("availability_evidence"), str)
        or not table["availability_evidence"].strip()
    ):
        raise ValueError("nonempty availability_evidence is required")
    if "availability_policy_version" in table and (
        not isinstance(table["availability_policy_version"], str)
        or not table["availability_policy_version"].strip()
    ):
        raise ValueError("availability_policy_version must be a nonempty string when supplied")
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("training table requires nonempty rows")
    keys = set()
    for row in rows:
        key = row_key(row)
        if key in keys:
            raise ValueError("duplicate training-table stock/date key")
        keys.add(key)
        target_cutoff(row)
        feature_matrix([row], features)
        if readiness == "verified":
            aware_datetime(row.get("label_available_at"), name="label_available_at")
        y = finite_number(row.get("y"), name="y")
        opening = finite_number(row.get("adj_open"), name="adj_open")
        closing = finite_number(row.get("adj_close"), name="adj_close")
        if (
            y not in (0, 1)
            or opening <= 0
            or closing <= 0
            or y != int(closing > opening)
        ):
            raise ValueError(
                "completed labels and consistent positive adjusted prices are required"
            )
        actual = (closing - opening) / opening
        if not math.isfinite(actual) or not math.isclose(
            finite_number(row.get("target_intraday_return"), name="return"),
            actual,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("return must agree with adjusted outcome prices")
    return rows, features


def feature_matrix(rows, features):
    result = []
    for row in rows:
        values = []
        for name in features:
            if name not in row:
                raise ValueError("model feature column is absent")
            value = row[name]
            values.append(np.nan if value is None else finite_number(value, name=name))
        result.append(values)
    return np.asarray(result, dtype=float)


@dataclass
class ModelBundle:
    preprocessor: Any
    estimator: Any
    metadata: dict


def fit_model(
    table,
    *,
    fit_cutoff: str | datetime,
    family="linear",
    objective="classification",
    seed=42,
    allow_research=False,
    epochs=8,
):
    rows, features = validate_table(table, allow_research=allow_research)
    cutoff = aware_datetime(fit_cutoff, name="fit_cutoff")
    local_day = cutoff.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
    if objective not in OBJECTIVES:
        raise ValueError("unknown objective")
    for row in rows:
        if row["target_date"] >= local_day or target_cutoff(row) >= cutoff:
            raise ValueError("training target must precede fit cutoff date")
        released = row.get("label_available_at")
        if (
            released is not None
            and aware_datetime(released, name="label_available_at") > cutoff
        ):
            raise ValueError("late label cannot enter training")
    x = feature_matrix(rows, features)
    preprocessing = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                ),
            ),
            ("scaler", StandardScaler()),
        ]
    )
    x = preprocessing.fit_transform(x)
    y = np.asarray(
        [
            row["target_intraday_return"] if objective == "regression" else row["y"]
            for row in rows
        ]
    )
    weights = (
        np.abs(np.asarray([row["target_intraday_return"] for row in rows]))
        if objective == "weighted_classification"
        else None
    )
    if weights is not None:
        weights = (
            weights / weights.mean() if weights.mean() > 0 else np.ones(len(weights))
        )
    estimator = make_estimator(family, objective, seed=seed, epochs=epochs)
    estimator = fit_estimator(
        estimator, x, y, keys=[row_key(r) for r in rows], sample_weight=weights
    )
    digest = hashlib.sha256(
        json.dumps(table, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    metadata = {
        "schema_version": "model-bundle-v1",
        "created_by": "finpred.training.fit",
        "family": family,
        "objective": objective,
        "seed": seed,
        "feature_columns": features,
        "feature_version": table["feature_version"],
        "fit_cutoff": cutoff.isoformat(),
        "train_end_date": max(r["target_date"] for r in rows),
        "train_rows": len(rows),
        "readiness": table["readiness"],
        "availability_evidence": table["availability_evidence"],
        "production_eligible": table["readiness"] == "verified",
        "training_table_sha256": digest,
        "epochs": epochs,
    }
    if "availability_policy_version" in table:
        metadata["availability_policy_version"] = table["availability_policy_version"]
    metadata["package_versions"] = {
        name: version(name) for name in ["scikit-learn", "numpy", "joblib"]
    }
    if family == "gru":
        metadata["package_versions"]["torch"] = version("torch")
    package = Path(__file__).resolve().parents[1]
    code_paths = [
        Path(__file__),
        package / "models/estimators.py",
        package / "inference/predict.py",
    ]
    metadata["code_sha256"] = {
        str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in code_paths
    }
    return ModelBundle(preprocessing, estimator, metadata)


def save_model_bundle(bundle, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(directory.iterdir()):
        raise ValueError(
            "model bundle destination must be empty; never overwrite a prior model"
        )
    directory.chmod(0o700)
    model = directory / "model.joblib"
    joblib.dump(bundle, model)
    model.chmod(0o600)
    metadata = dict(
        bundle.metadata, model_sha256=hashlib.sha256(model.read_bytes()).hexdigest()
    )
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    manifest.chmod(0o600)
    return metadata


def load_model_bundle(directory, *, trusted=False):
    """Load only locally controlled bundles; a checksum is not an authenticity proof.

    joblib uses pickle. Never set trusted=True for downloaded/user-supplied models.
    The caller must establish ownership/provenance, e.g. its private model store.
    """
    if not trusted:
        raise ValueError(
            "joblib requires an explicitly trusted internally created model store"
        )
    directory = Path(directory)
    manifest = directory / "manifest.json"
    model = directory / "model.joblib"
    for path in (directory, manifest, model):
        if (
            path.is_symlink()
            or path.stat().st_mode & 0o022
            or path.stat().st_uid != os.getuid()
        ):
            raise ValueError(
                "model store must be locally owned and not writable by other users"
            )
    metadata = json.loads(manifest.read_text())
    if metadata.get("created_by") != "finpred.training.fit" or hashlib.sha256(
        model.read_bytes()
    ).hexdigest() != metadata.get("model_sha256"):
        raise ValueError("model provenance or checksum failed")
    bundle = joblib.load(model)
    if not isinstance(bundle, ModelBundle) or bundle.metadata != {
        k: v for k, v in metadata.items() if k != "model_sha256"
    }:
        raise ValueError("bundle metadata disagrees with manifest")
    return bundle


def train_candidate(
    table,
    out_dir,
    *,
    fit_cutoff,
    family="linear",
    objective="weighted_classification",
    seed=42,
    incumbent_configuration=None,
    incumbent_metadata=None,
    min_train_dates=252,
    validation_dates=60,
    allow_research=False,
    epochs=8,
):
    """Fairly compare configurations, then refit selected configuration on history.

    The incumbent configuration is freshly fitted on the SAME earlier fold; its
    recent artifact is never evaluated against dates that artifact may have seen.
    An already approved recipe may refresh on newly completed history without a
    fictional strict gain over its own identical refit. This requires matching
    schema/policy, verified incumbent metadata and nondegrading same-fold score.
    Different recipes and the initial bootstrap still require strict gain.
    A research/synthetic result is never eligible for production promotion.
    """
    from finpred.evaluation.official_score import evaluate_predictions
    from finpred.inference.predict import predict_rows

    rows, _ = validate_table(table, allow_research=allow_research)
    if incumbent_metadata is not None and not isinstance(incumbent_metadata, dict):
        raise ValueError("incumbent_metadata must be a model metadata mapping")
    cutoff = aware_datetime(fit_cutoff, name="fit_cutoff")
    if min_train_dates < 1 or validation_dates < 1:
        raise ValueError("training and validation date counts must be positive")
    dates = sorted({row["target_date"] for row in rows})
    if len(dates) < min_train_dates + validation_dates:
        raise ValueError("insufficient training and validation dates")
    if any(
        row["target_date"]
        >= cutoff.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
        for row in rows
    ):
        raise ValueError(
            "candidate history includes the prediction date or future dates"
        )
    if any(
        row.get("label_available_at") is not None
        and aware_datetime(row["label_available_at"], name="label_available_at")
        > cutoff
        for row in rows
    ):
        raise ValueError(
            "candidate contains labels unavailable at the current training cutoff"
        )
    validation_start = dates[-validation_dates]
    validation = [r for r in rows if r["target_date"] >= validation_start]
    fold_cutoff = min(target_cutoff(r) for r in validation)
    early = [r for r in rows if r["target_date"] < validation_start]
    unavailable = {
        r["target_date"]
        for r in early
        if r.get("label_available_at") is not None
        and aware_datetime(r["label_available_at"], name="label_available_at")
        > fold_cutoff
    }
    early = [r for r in early if r["target_date"] not in unavailable]
    if len({r["target_date"] for r in early}) < min_train_dates:
        raise ValueError(
            "insufficient earlier dates after historical label-release filtering"
        )
    train_table = dict(table, rows=early)
    candidate = fit_model(
        train_table,
        fit_cutoff=fold_cutoff,
        family=family,
        objective=objective,
        seed=seed,
        allow_research=allow_research,
        epochs=epochs,
    )
    candidate_score = evaluate_predictions(
        predict_rows(candidate, validation), validation
    )
    incumbent_epochs = (incumbent_metadata or {}).get(
        "epochs", (incumbent_configuration or {}).get("epochs", epochs)
    )
    if incumbent_configuration:
        incumbent = fit_model(
            train_table,
            fit_cutoff=fold_cutoff,
            family=incumbent_configuration["family"],
            objective=incumbent_configuration["objective"],
            seed=incumbent_configuration.get("seed", seed),
            allow_research=allow_research,
            epochs=incumbent_epochs,
        )
        incumbent_score = evaluate_predictions(
            predict_rows(incumbent, validation), validation
        )
        comparison = "configuration_retrained_on_same_time_split"
    else:
        majority = int(sum(r["y"] for r in early) > len(early) / 2)
        baseline = [
            dict(
                stock_id=r["stock_id"],
                target_date=r["target_date"],
                prediction=majority,
            )
            for r in validation
        ]
        incumbent_score = evaluate_predictions(baseline, validation)
        comparison = "train_majority_baseline_on_same_validation_keys"
    improved = candidate_score.score > incumbent_score.score
    selected = {"family": family, "objective": objective, "seed": seed}
    incumbent_recipe = None
    if incumbent_configuration:
        incumbent_recipe = {
            "family": incumbent_configuration["family"],
            "objective": incumbent_configuration["objective"],
            "seed": incumbent_configuration.get("seed", seed),
        }
    configuration_unchanged = bool(
        incumbent_recipe == selected
        and incumbent_epochs == epochs
    )
    schema_policy_compatible = bool(
        isinstance(incumbent_metadata, dict)
        and incumbent_metadata.get("production_eligible") is True
        and incumbent_metadata.get("readiness") == "verified"
        and incumbent_metadata.get("feature_columns") == table["feature_columns"]
        and incumbent_metadata.get("feature_version") == table["feature_version"]
        and incumbent_metadata.get("availability_evidence") == table["availability_evidence"]
        and incumbent_metadata.get("availability_policy_version") == table.get("availability_policy_version")
        and incumbent_recipe is not None
        and all(incumbent_metadata.get(k) == v for k, v in incumbent_recipe.items())
    )
    history_advanced = False
    if schema_policy_compatible:
        try:
            old_end = date.fromisoformat(incumbent_metadata["train_end_date"])
            history_advanced = max(date.fromisoformat(r["target_date"]) for r in rows) > old_end
        except (KeyError, TypeError, ValueError):
            history_advanced = False
    if not improved and incumbent_configuration:
        selected = dict(incumbent_configuration)
    selected_epochs = incumbent_epochs if not improved and incumbent_configuration else epochs
    final = fit_model(
        table,
        fit_cutoff=cutoff,
        family=selected["family"],
        objective=selected["objective"],
        seed=selected.get("seed", seed),
        allow_research=allow_research,
        epochs=selected_epochs,
    )
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle_path = destination / "model"
    save_model_bundle(final, bundle_path)
    eligible = False
    if not final.metadata["production_eligible"]:
        promotion_reason = "non_verified_model"
    elif incumbent_metadata is not None and not schema_policy_compatible:
        promotion_reason = "incumbent_schema_or_policy_incompatible"
    elif configuration_unchanged:
        if incumbent_metadata is None:
            promotion_reason = "refresh_requires_verified_incumbent_metadata"
        elif not history_advanced:
            promotion_reason = "no_new_completed_history"
        elif candidate_score.score < incumbent_score.score:
            promotion_reason = "same_configuration_validation_degraded"
        else:
            eligible = True
            promotion_reason = "same_configuration_new_history_refresh"
    elif improved:
        eligible = True
        promotion_reason = "strict_validation_improvement"
    else:
        promotion_reason = "no_validation_improvement"
    report = {
        "schema_version": "candidate-report-v1",
        "evaluation_scope": comparison,
        "candidate_score": candidate_score.score,
        "incumbent_score": incumbent_score.score,
        "candidate_improved": improved,
        "selected_configuration": selected,
        "selected_epochs": selected_epochs,
        "eligible_for_promotion": eligible,
        "promotion_reason": promotion_reason,
        "configuration_unchanged": configuration_unchanged,
        "schema_policy_compatible": schema_policy_compatible,
        "history_advanced": history_advanced,
        "readiness": table["readiness"],
        "training_dates": len({r["target_date"] for r in early}),
        "validation_dates": validation_dates,
        "validation_keys": [[r["stock_id"], r["target_date"]] for r in validation],
        "validation_key_sha256": hashlib.sha256(
            json.dumps(
                sorted((r["stock_id"], r["target_date"]) for r in validation)
            ).encode()
        ).hexdigest(),
        "model_path": str(bundle_path),
        "historical_feature_evidence_certified_by_code": False,
    }
    report_path = destination / "candidate_report.json"
    if report_path.exists():
        raise ValueError("candidate report already exists")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    report_path.chmod(0o600)
    return report
