"""R3 model factory. Every learned transform is fitted on the training fold only.

``fit(X, r, y)`` receives pre-open features, the realized intraday return r and
the binary label y for training rows only; ``decision(X)`` returns a real-valued
score whose sign (regression) or excess over 0.5 (classification) is the call.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OBJECTIVES = ("regression", "weighted_classification", "classification")


class RuleModel:
    """Constant or previous-day rules; ``needs`` lists required feature columns."""

    def __init__(self, rule: str):
        if rule not in ("all0", "all1", "prevday"):
            raise ValueError(f"unknown rule {rule!r}")
        self.rule = rule
        self.needs = ["intra_l1"] if rule == "prevday" else []

    def fit(self, X, r, y, *, seed=42):
        return self

    def decision(self, X):
        if self.rule == "all0":
            return np.full(len(X), -1.0)
        if self.rule == "all1":
            return np.full(len(X), 1.0)
        prev = X["intra_l1"].to_numpy()
        return np.where(np.isfinite(prev) & (prev > 0), 1.0, -1.0)


class TrainOnlyPreprocessor:
    """Winsorize at train quantiles, median-impute, standardize (all train-only)."""

    def __init__(self, clip=0.005):
        self.clip = clip

    def fit(self, X: pd.DataFrame):
        values = X.to_numpy(dtype=float)
        with np.errstate(all="ignore"):
            self.lo = np.nanquantile(values, self.clip, axis=0)
            self.hi = np.nanquantile(values, 1 - self.clip, axis=0)
            clipped = np.clip(values, self.lo, self.hi)
            self.median = np.nanmedian(clipped, axis=0)
        self.median = np.where(np.isfinite(self.median), self.median, 0.0)
        self.lo = np.where(np.isfinite(self.lo), self.lo, -np.inf)
        self.hi = np.where(np.isfinite(self.hi), self.hi, np.inf)
        filled = np.where(np.isfinite(clipped), clipped, self.median)
        self.mean = filled.mean(axis=0)
        std = filled.std(axis=0)
        self.std = np.where(std > 1e-12, std, 1.0)
        return self

    def transform(self, X: pd.DataFrame):
        values = np.clip(X.to_numpy(dtype=float), self.lo, self.hi)
        values = np.where(np.isfinite(values), values, self.median)
        return (values - self.mean) / self.std


def _targets(objective, r, y):
    r = np.asarray(r, dtype=float)
    y = np.asarray(y, dtype=int)
    if objective == "regression":
        return r, None
    if objective == "weighted_classification":
        weight = np.abs(r)
        return y, weight / weight.mean()
    return y, None


class LinearModel:
    def __init__(self, objective="regression", alpha=1.0, clip=0.005):
        if objective not in ("regression", "weighted_classification"):
            raise ValueError("linear model supports regression or weighted_classification")
        self.objective, self.alpha, self.clip = objective, alpha, clip
        self.needs = []

    def fit(self, X, r, y, *, seed=42):
        from sklearn.linear_model import LogisticRegression, Ridge

        self.pre = TrainOnlyPreprocessor(self.clip).fit(X)
        Z = self.pre.transform(X)
        target, weight = _targets(self.objective, r, y)
        if self.objective == "regression":
            self.model = Ridge(alpha=self.alpha).fit(Z, target)
        else:
            self.model = LogisticRegression(C=1.0 / self.alpha, max_iter=500).fit(
                Z, target, sample_weight=weight)
        return self

    def decision(self, X):
        Z = self.pre.transform(X)
        if self.objective == "regression":
            return self.model.predict(Z)
        return self.model.predict_proba(Z)[:, 1] - 0.5


class GBDTModel:
    """LightGBM / CatBoost / XGBoost with native missing-value handling."""

    def __init__(self, family="lightgbm", objective="regression", params=None, threads=4):
        if objective not in OBJECTIVES:
            raise ValueError(f"unknown objective {objective!r}")
        self.family, self.objective = family, objective
        self.params = dict(params or {})
        self.threads = threads
        self.needs = []

    def fit(self, X, r, y, *, seed=42):
        target, weight = _targets(self.objective, r, y)
        regression = self.objective == "regression"
        p = dict(self.params)
        if self.family == "lightgbm":
            import lightgbm as lgb

            cls = lgb.LGBMRegressor if regression else lgb.LGBMClassifier
            self.model = cls(random_state=seed, n_jobs=self.threads, verbose=-1, **p)
            self.model.fit(X, target, sample_weight=weight)
        elif self.family == "catboost":
            import catboost as cb

            cls = cb.CatBoostRegressor if regression else cb.CatBoostClassifier
            self.model = cls(random_seed=seed, thread_count=self.threads, verbose=False,
                             allow_writing_files=False, **p)
            self.model.fit(X, target, sample_weight=weight)
        elif self.family == "xgboost":
            import xgboost as xgb

            cls = xgb.XGBRegressor if regression else xgb.XGBClassifier
            self.model = cls(random_state=seed, n_jobs=self.threads, tree_method="hist", **p)
            self.model.fit(X, target, sample_weight=weight)
        else:
            raise ValueError(f"unknown GBDT family {self.family!r}")
        return self

    def decision(self, X):
        if self.objective == "regression":
            return np.asarray(self.model.predict(X), dtype=float)
        return self.model.predict_proba(X)[:, 1] - 0.5


def build_model(spec: dict, *, threads=4):
    family = spec["family"]
    objective = spec.get("objective", "regression")
    params = spec.get("params", {})
    if family == "rule":
        return RuleModel(spec["rule"])
    if family == "ridge":
        return LinearModel("regression", **params)
    if family == "logistic":
        return LinearModel("weighted_classification", **params)
    if family in ("lightgbm", "catboost", "xgboost"):
        return GBDTModel(family, objective, params, threads=threads)
    raise ValueError(f"unknown model family {family!r}")
