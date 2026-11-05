"""Small causal temporal models; targets never participate in input masking.

The neural extra is optional. Both networks consume [date, stock, lookback,
feature] tensors. Fixed windows include the current prediction-cutoff vector;
earlier padding stays zero and the final channel explicitly marks input presence.
"""

from __future__ import annotations

import numpy as np

try:
    import torch
    from torch import nn
except ImportError:
    torch = None
    nn = None

Module = nn.Module if nn is not None else object


def require_torch():
    if torch is None:
        raise ImportError("TCN/attention require the optional neural extra (PyTorch)")


class CausalResidualBlock(Module):
    """Two left-padded convolutions without normalization across time."""

    def __init__(self, channels, *, kernel_size=3, dilation=1, dropout=0.0):
        require_torch()
        super().__init__()
        self.left_padding = (kernel_size - 1) * dilation
        self.convolutions = nn.ModuleList([
            nn.Conv1d(channels, channels, kernel_size, dilation=dilation)
            for _ in range(2)
        ])
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        result = x
        for convolution in self.convolutions:
            result = convolution(nn.functional.pad(result, (self.left_padding, 0)))
            result = self.dropout(nn.functional.relu(result))
        return nn.functional.relu(x + result)


class CausalTCN(Module):
    """Stock-independent causal TCN; returns unnormalised return estimates."""

    def __init__(self, input_features, *, hidden=32, dropout=0.0):
        require_torch()
        super().__init__()
        self.project = nn.Conv1d(input_features, hidden, 1)
        self.blocks = nn.Sequential(*[
            CausalResidualBlock(hidden, dilation=d, dropout=dropout)
            for d in (1, 2, 4)
        ])
        self.head = nn.Linear(hidden, 1)

    def encode_sequence(self, x):
        batch, stocks, length, features = x.shape
        flat = x.reshape(batch * stocks, length, features).transpose(1, 2)
        encoded = self.blocks(self.project(flat)).transpose(1, 2)
        return encoded.reshape(batch, stocks, length, -1)

    def forward(self, x, stock_mask=None):
        return self.head(self.encode_sequence(x)[:, :, -1]).squeeze(-1)


class MarketGatedAttention(Module):
    """Past-only stock GRU, known-market gate and same-cutoff stock attention.

The common market head and zero-mean *predicted* residual retain absolute market
direction. The target is never demeaned across stocks. key_padding_mask is based
only on available feature context, including for stocks without a known label.
"""

    def __init__(self, input_features, *, market_indices=(), hidden=32, dropout=0.0):
        require_torch()
        super().__init__()
        self.market_indices = tuple(market_indices) or tuple(range(input_features - 1))
        if not self.market_indices:
            raise ValueError("market gate requires at least one known input feature")
        self.temporal = nn.GRU(input_features, hidden, batch_first=True)
        self.gate = nn.Linear(len(self.market_indices), hidden)
        self.market_head = nn.Linear(len(self.market_indices), 1)
        self.attention = nn.MultiheadAttention(hidden, 2, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(hidden)
        self.dropout = nn.Dropout(dropout)
        self.stock_head = nn.Linear(hidden, 1)

    def forward(self, x, stock_mask=None):
        batch, stocks, length, features = x.shape
        if stock_mask is None:
            stock_mask = x[:, :, :, -1].gt(0).any(dim=-1)
        flat = x.reshape(batch * stocks, length, features)
        encoded, _ = self.temporal(flat)
        encoded = encoded[:, -1].reshape(batch, stocks, -1)
        # Use only current-cutoff known features; no outcome or label mask.
        current = x[:, :, -1, self.market_indices]
        current_mask = x[:, :, -1, -1].gt(0)
        market = (current * current_mask.unsqueeze(-1)).sum(dim=1)
        market = market / current_mask.sum(dim=1, keepdim=True).clamp_min(1)
        gated = encoded * torch.sigmoid(self.gate(market)).unsqueeze(1)
        gated = gated * stock_mask.unsqueeze(-1)
        key_mask = ~stock_mask.clone()
        # MultiheadAttention must have a legal key even for all-missing batches.
        key_mask[~stock_mask.any(dim=1), 0] = False
        attended, _ = self.attention(gated, gated, gated, key_padding_mask=key_mask,
                                     need_weights=False)
        residual = self.stock_head(self.norm(gated + self.dropout(attended))).squeeze(-1)
        residual = residual - residual.mean(dim=1, keepdim=True)
        return self.market_head(market) + residual


def make_windows(values, date_indices, *, lookback=20):
    """Construct windows from complete ordered target sessions, retaining gaps."""
    values = np.asarray(values, dtype=np.float32)
    indices = np.asarray(date_indices, dtype=int)
    if values.ndim != 3 or lookback < 1 or np.any(indices < 0) or np.any(indices >= len(values)):
        raise ValueError("ordered date/stock/features and in-range window dates required")
    result = np.zeros((len(indices), values.shape[1], lookback, values.shape[2]), np.float32)
    for position, day in enumerate(indices):
        start = max(0, day - lookback + 1)
        window = values[start:day + 1].transpose(1, 0, 2)
        result[position, :, -window.shape[1]:] = window
    return result


class TemporalRegressor:
    """Deterministic CPU MSE fit with labels separated from model input masks."""

    def __init__(self, family, *, dropout=0.0, epochs=20, lookback=20,
                 hidden=32, seed=42, batch_dates=64, market_indices=()):
        if family not in {"M3", "M4"} or epochs < 1 or batch_dates < 1:
            raise ValueError("supported temporal family and positive budgets required")
        self.family, self.dropout, self.epochs = family, dropout, epochs
        self.lookback, self.hidden, self.seed = lookback, hidden, seed
        self.batch_dates, self.market_indices = batch_dates, tuple(market_indices)

    def fit(self, values, returns, label_mask, train_dates):
        require_torch()
        torch.set_num_threads(1)
        torch.manual_seed(self.seed)
        torch.use_deterministic_algorithms(True)
        self.network_ = (CausalTCN(values.shape[-1], hidden=self.hidden, dropout=self.dropout)
                         if self.family == "M3" else
                         MarketGatedAttention(values.shape[-1], hidden=self.hidden,
                                              dropout=self.dropout, market_indices=self.market_indices))
        optimizer = torch.optim.Adam(self.network_.parameters(), lr=0.001)
        generator = torch.Generator().manual_seed(self.seed)
        dates = np.asarray(train_dates, dtype=int)
        dates = dates[np.asarray(label_mask)[dates].any(axis=1)]
        if not len(dates):
            raise ValueError("no completed training labels")
        self.loss_history_ = []
        for _ in range(self.epochs):
            losses = []
            for order in torch.randperm(len(dates), generator=generator).split(self.batch_dates):
                batch = dates[order.numpy()]
                windows = torch.from_numpy(make_windows(values, batch, lookback=self.lookback))
                mask = torch.from_numpy(np.asarray(label_mask[batch], dtype=bool))
                targets = torch.from_numpy(np.asarray(returns[batch], np.float32)) * 100.0
                optimizer.zero_grad()
                estimate = self.network_(windows)
                # Scaling every return by 100 changes MSE only by a fixed factor.
                loss = ((estimate[mask] - targets[mask]) ** 2).mean()
                if not torch.isfinite(loss):
                    raise ValueError("nonfinite neural loss")
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.network_.parameters(), 5.0)
                optimizer.step()
                losses.append(float(loss.detach()))
            self.loss_history_.append(float(np.mean(losses)))
        self.network_.eval()
        return self

    def predict(self, values, date_indices):
        require_torch()
        result = []
        self.network_.eval()
        with torch.no_grad():
            for batch in np.array_split(np.asarray(date_indices, dtype=int),
                                        max(1, (len(date_indices) + self.batch_dates - 1) // self.batch_dates)):
                if not len(batch):
                    continue
                output = self.network_(torch.from_numpy(make_windows(values, batch, lookback=self.lookback)))
                result.append(output.numpy() / 100.0)
        return np.concatenate(result, axis=0) if result else np.empty((0, values.shape[1]))
