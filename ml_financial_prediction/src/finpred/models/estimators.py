"""Reuse sklearn and PyTorch for four distinct model families."""

from __future__ import annotations

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPClassifier, MLPRegressor
from threadpoolctl import threadpool_limits

FAMILIES = ("linear", "hist_gbdt", "mlp", "gru")
OBJECTIVES = ("classification", "weighted_classification", "regression")


def make_estimator(family, objective, *, seed=42, epochs=8):
    if family not in FAMILIES or objective not in OBJECTIVES:
        raise ValueError("unknown model family or objective")
    regression = objective == "regression"
    if family == "linear":
        return (
            Ridge(alpha=1.0)
            if regression
            else LogisticRegression(C=1.0, max_iter=300, random_state=seed)
        )
    if family == "hist_gbdt":
        cls = (
            HistGradientBoostingRegressor
            if regression
            else HistGradientBoostingClassifier
        )
        return cls(
            max_iter=60,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=seed,
        )
    if family == "mlp":
        cls = MLPRegressor if regression else MLPClassifier
        return cls(
            hidden_layer_sizes=(32,),
            max_iter=80,
            batch_size=256,
            early_stopping=False,
            random_state=seed,
        )
    return GRUEstimator(regression=regression, seed=seed, epochs=epochs)


class GRUEstimator:
    """Small CPU GRU; each sequence contains only its stock's earlier/current X.

    Inputs are already train-fitted imputed/scaled. Padding repeats the oldest
    available feature vector; no future row, outcome or stock enters a window.
    Predict retains the final training context but never fits on validation.
    """

    def __init__(self, *, regression=False, seed=42, epochs=8, lookback=5):
        self.regression, self.seed, self.epochs, self.lookback = (
            regression,
            seed,
            epochs,
            lookback,
        )

    def _windows(self, x, keys, history=None):
        result = np.zeros((len(x), self.lookback, x.shape[1]), dtype=np.float32)
        tails = {stock: list(values) for stock, values in (history or {}).items()}
        for i in sorted(range(len(keys)), key=lambda j: (keys[j][0], keys[j][1])):
            stock, _ = keys[i]
            values = tails.setdefault(stock, [])
            values.append(np.asarray(x[i], dtype=np.float32))
            sequence = values[-self.lookback :]
            result[i] = [sequence[0]] * (self.lookback - len(sequence)) + sequence
            tails[stock] = sequence
        return result, tails

    def fit(self, x, y, *, keys, sample_weight=None):
        try:
            import torch
        except ImportError as exc:
            raise ImportError(
                "GRU requires the neural extra: uv sync --extra neural --extra models"
            ) from exc
        torch.set_num_threads(1)
        torch.manual_seed(self.seed)
        torch.use_deterministic_algorithms(True)
        windows, self.history_ = self._windows(x, keys)
        self.input_size_ = x.shape[1]
        network = torch.nn.GRU(self.input_size_, 16, batch_first=True)
        head = torch.nn.Linear(16, 1)
        optimizer = torch.optim.Adam(
            list(network.parameters()) + list(head.parameters()), lr=0.003
        )
        values = torch.tensor(windows)
        targets = torch.tensor(np.asarray(y, dtype=np.float32)).reshape(-1, 1)
        weights = torch.tensor(
            np.asarray(
                sample_weight if sample_weight is not None else np.ones(len(y)),
                dtype=np.float32,
            )
        ).reshape(-1, 1)
        generator = torch.Generator().manual_seed(self.seed)
        for _ in range(self.epochs):
            for indices in torch.randperm(len(y), generator=generator).split(256):
                optimizer.zero_grad()
                output, _ = network(values[indices])
                output = head(output[:, -1])
                loss = (
                    (output - targets[indices]) ** 2
                    if self.regression
                    else torch.nn.functional.binary_cross_entropy_with_logits(
                        output, targets[indices], reduction="none"
                    )
                )
                loss = (loss * weights[indices]).sum() / weights[
                    indices
                ].sum().clamp_min(1e-12)
                loss.backward()
                optimizer.step()
        # Store plain state arrays; recreate the network for prediction.
        self.network_state_ = {
            name: value.detach().numpy() for name, value in network.state_dict().items()
        }
        self.head_state_ = {
            name: value.detach().numpy() for name, value in head.state_dict().items()
        }
        return self

    def predict(self, x, *, keys):
        import torch

        windows, _ = self._windows(x, keys, self.history_)
        network = torch.nn.GRU(self.input_size_, 16, batch_first=True)
        head = torch.nn.Linear(16, 1)
        network.load_state_dict(
            {k: torch.tensor(v) for k, v in self.network_state_.items()}
        )
        head.load_state_dict({k: torch.tensor(v) for k, v in self.head_state_.items()})
        network.eval()
        head.eval()
        with torch.no_grad():
            output, _ = network(torch.tensor(windows))
            values = head(output[:, -1]).numpy().ravel()
        return values if self.regression else (values > 0).astype(int)


def fit_estimator(estimator, x, y, *, keys, sample_weight=None):
    if not getattr(estimator, "regression", False) and isinstance(
        estimator, GRUEstimator
    ):
        return estimator.fit(x, y, keys=keys, sample_weight=sample_weight)
    if isinstance(estimator, GRUEstimator):
        return estimator.fit(x, y, keys=keys, sample_weight=sample_weight)
    if hasattr(estimator, "predict_proba") and len(np.unique(y)) < 2:
        estimator = DummyClassifier(strategy="constant", constant=int(y[0]))
    arguments = {"sample_weight": sample_weight} if sample_weight is not None else {}
    with threadpool_limits(limits=1):
        estimator.fit(x, y, **arguments)
    return estimator
