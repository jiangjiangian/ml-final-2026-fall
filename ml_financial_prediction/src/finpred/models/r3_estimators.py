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
    if family == "mlp":
        return MLPModel(objective, threads=threads, **params)
    if family == "blend":
        return BlendModel(spec["components"], spec.get("weights"), threads=threads)
    if family == "two_head":
        return TwoHeadModel(spec["market_columns"], spec["stock_model"],
                            threads=threads, **params)
    raise ValueError(f"unknown model family {family!r}")


class TwoHeadModel:
    """H9: day-level market head + stock-level head on market-demeaned returns.

    The market head is a Ridge on one row per training date (columns that are
    identical across stocks) predicting m_t, the mean training-universe return of
    that date. The stock head is a GBDT predicting r - m_t. Both targets use only
    training-fold labels; the decision is ``shrink * m_hat_t + e_hat_it``.
    """

    uses_dates = True

    def __init__(self, market_columns, stock_spec, market_alpha=10.0, shrink=1.0, threads=4):
        self.market_columns = list(market_columns)
        self.stock_spec = dict(stock_spec)
        self.market_alpha, self.shrink, self.threads = market_alpha, shrink, threads
        self.needs = []

    def _day_frame(self, X, dates):
        cols = [c for c in self.market_columns if c in X.columns]
        frame = X[cols].copy()
        frame["_date"] = np.asarray(dates)
        return frame.groupby("_date", sort=True)[cols].first()

    def fit(self, X, r, y, *, seed=42, dates=None):
        from sklearn.linear_model import Ridge

        if dates is None:
            raise ValueError("two-head model needs training dates")
        r = np.asarray(r, dtype=float)
        dates = np.asarray(dates)
        m = pd.Series(r).groupby(dates).transform("mean").to_numpy()
        day = self._day_frame(X, dates)
        m_day = pd.Series(r).groupby(dates).mean().reindex(day.index).to_numpy()
        self.pre = TrainOnlyPreprocessor().fit(day)
        self.market = Ridge(alpha=self.market_alpha).fit(self.pre.transform(day), m_day)
        self.stock = build_model(self.stock_spec, threads=self.threads)
        resid = r - m
        self.stock.fit(self._stock_x(X), resid, (resid > 0).astype(int), seed=seed)
        return self

    def _stock_x(self, X):
        cols = self.stock_spec.get("_columns")
        return X[cols] if cols else X

    def decision(self, X, dates=None):
        if dates is None:
            raise ValueError("two-head model needs prediction dates")
        dates = np.asarray(dates)
        day = self._day_frame(X, dates)
        m_hat = pd.Series(self.market.predict(self.pre.transform(day)), index=day.index)
        market = m_hat.reindex(dates).to_numpy()
        return self.shrink * market + self.stock.decision(self._stock_x(X))


class MLPModel:
    """Small PyTorch MLP on train-only standardized features (CPU, fixed epochs)."""

    def __init__(self, objective="regression", hidden=(64, 32), dropout=0.1, epochs=8,
                 lr=1e-3, weight_decay=1e-4, batch=1024, threads=4):
        if objective != "regression":
            raise ValueError("MLP supports regression only")
        self.hidden, self.dropout, self.epochs = tuple(hidden), dropout, epochs
        self.lr, self.weight_decay, self.batch, self.threads = lr, weight_decay, batch, threads
        self.needs = []

    def fit(self, X, r, y, *, seed=42):
        import torch

        torch.set_num_threads(self.threads)
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        self.pre = TrainOnlyPreprocessor().fit(X)
        Z = torch.tensor(self.pre.transform(X), dtype=torch.float32)
        r = np.asarray(r, dtype=float)
        self.scale = float(np.std(r)) or 1.0
        target = torch.tensor(r / self.scale, dtype=torch.float32)
        layers, width = [], Z.shape[1]
        for h in self.hidden:
            layers += [torch.nn.Linear(width, h), torch.nn.ReLU(), torch.nn.Dropout(self.dropout)]
            width = h
        layers.append(torch.nn.Linear(width, 1))
        self.net = torch.nn.Sequential(*layers)
        opt = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        loss_fn = torch.nn.MSELoss()
        n = len(Z)
        self.net.train()
        for _ in range(self.epochs):
            order = torch.tensor(rng.permutation(n))
            for start in range(0, n, self.batch):
                idx = order[start:start + self.batch]
                opt.zero_grad()
                loss = loss_fn(self.net(Z[idx]).squeeze(1), target[idx])
                loss.backward()
                opt.step()
        self.net.eval()
        return self

    def decision(self, X):
        import torch

        with torch.no_grad():
            Z = torch.tensor(self.pre.transform(X), dtype=torch.float32)
            return self.net(Z).squeeze(1).numpy().astype(float) * self.scale


class BlendModel:
    """Weighted average of components, each scaled by its training-fold decision std."""

    def __init__(self, components, weights=None, threads=4):
        self.specs = [dict(c) for c in components]
        self.weights = list(weights or [1.0] * len(self.specs))
        self.threads = threads
        self.needs = []
        self.uses_dates = any(c.get("family") == "two_head" for c in self.specs)

    def fit(self, X, r, y, *, seed=42, dates=None):
        self.models, self.scales = [], []
        for spec in self.specs:
            model = build_model(spec, threads=self.threads)
            cols = spec.get("_columns")
            Xi = X[cols] if cols else X
            if getattr(model, "uses_dates", False):
                model.fit(Xi, r, y, seed=seed, dates=dates)
                train_dec = model.decision(Xi, dates=dates)
            else:
                model.fit(Xi, r, y, seed=seed)
                train_dec = model.decision(Xi)
            self.models.append(model)
            self.scales.append(float(np.std(train_dec)) or 1.0)
        return self

    def decision(self, X, dates=None):
        total = np.zeros(len(X))
        for spec, model, scale, w in zip(self.specs, self.models, self.scales, self.weights):
            cols = spec.get("_columns")
            Xi = X[cols] if cols else X
            dec = model.decision(Xi, dates=dates) if getattr(model, "uses_dates", False) else model.decision(Xi)
            total += w * dec / scale
        return total / sum(self.weights)
