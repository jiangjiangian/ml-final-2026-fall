"""Inference never fits or updates the preprocessing/model state."""

import numpy as np

from finpred.labels.intraday import aware_datetime, row_key
from finpred.models.estimators import GRUEstimator
from finpred.training.fit import feature_matrix, target_cutoff


def predict_rows(
    bundle,
    rows,
    *,
    feature_columns=None,
    feature_version=None,
    require_production=False,
):
    rows = list(rows)
    metadata = bundle.metadata
    if require_production and not metadata["production_eligible"]:
        raise ValueError(
            "research or synthetic model cannot produce production predictions"
        )
    if (
        feature_columns is not None
        and list(feature_columns) != metadata["feature_columns"]
    ):
        raise ValueError("feature column order differs from the trained schema")
    if feature_version is not None and feature_version != metadata["feature_version"]:
        raise ValueError("feature version differs from the trained model")
    keys = [row_key(row) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate inference stock/date key")
    for row in rows:
        cutoff = target_cutoff(row)
        if aware_datetime(metadata["fit_cutoff"], name="model fit cutoff") > cutoff:
            raise ValueError("model was fitted after the requested prediction cutoff")
        if row["target_date"] <= metadata["train_end_date"]:
            raise ValueError("prediction target must be after the training range")
    if not rows:
        return []
    x = bundle.preprocessor.transform(feature_matrix(rows, metadata["feature_columns"]))
    values = (
        bundle.estimator.predict(x, keys=keys)
        if isinstance(bundle.estimator, GRUEstimator)
        else bundle.estimator.predict(x)
    )
    if not np.all(np.isfinite(values)):
        raise ValueError("model produced nonfinite output")
    if metadata["objective"] != "regression" and not np.all(np.isin(values, [0, 1])):
        raise ValueError("classifier must return binary labels, not probabilities")
    predictions = (
        (values > 0).astype(int)
        if metadata["objective"] == "regression"
        else np.asarray(values, dtype=int)
    )
    if not np.all(np.isin(predictions, [0, 1])):
        raise ValueError("model produced invalid binary output")
    return [
        {"stock_id": stock, "target_date": day, "prediction": int(p)}
        for (stock, day), p in zip(keys, predictions)
    ]
