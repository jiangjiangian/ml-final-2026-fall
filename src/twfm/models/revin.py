"""RevIN：每個樣本用自己視窗的平均和標準差標準化（Kim et al., ICLR 2022）。

時間規則：統計量只看輸入視窗 `[B, L, C]` 的 L 維，也就是到 i 為止的列，不看未來。
Kronos 原本的輸入處理就是 `RevIN(affine=False, clip=5)`：
官方 `KronosPredictor` 和 `finetune/dataset.py` 都是 `(x − mean) / (std + 1e-5)`，
std 用母體標準差（numpy 的 `np.std`，ddof=0），再裁在 ±5。這裡的公式和它完全一樣。
"""

from __future__ import annotations

from typing import Literal

import torch
from torch import nn

from ._amp import autocast_disabled


class RevIN(nn.Module):
    """可逆的逐樣本標準化。

    `norm`：`y = clip((x − mean) / (std + eps))`，有 `affine` 時再 `y * weight + bias`。
    `denorm`：反過來，用上一次 `norm` 存下的 mean、std。

    - mean、std 對 L 維算（每個樣本、每個特徵各一組），`detach` 掉，梯度不經過統計量。
    - 一律在 fp32 算，AMP 裡也一樣（成交金額到 1e10，fp16 會溢位）。輸出是 fp32。
    - `clip` 有值時在標準化之後、仿射之前裁切，所以可學的仿射仍可放大縮小。
    - 同一個模組一次只記一組統計量，`denorm` 要接在對應的 `norm` 後面。
    """

    def __init__(
        self,
        num_features: int,
        eps: float = 1e-5,
        affine: bool = True,
        clip: float | None = None,
    ) -> None:
        super().__init__()
        if num_features < 1:
            raise ValueError(f"num_features 至少 1，拿到 {num_features}")
        if eps <= 0:
            raise ValueError(f"eps 要大於 0，拿到 {eps}")
        if clip is not None and clip <= 0:
            raise ValueError(f"clip 是 None 或大於 0，拿到 {clip}")
        self.num_features = int(num_features)
        self.eps = float(eps)
        self.affine = bool(affine)
        self.clip = None if clip is None else float(clip)
        if self.affine:
            self.affine_weight = nn.Parameter(torch.ones(self.num_features))
            self.affine_bias = nn.Parameter(torch.zeros(self.num_features))
        self._mean: torch.Tensor | None = None
        self._std: torch.Tensor | None = None

    def extra_repr(self) -> str:
        return f"num_features={self.num_features}, eps={self.eps}, affine={self.affine}, clip={self.clip}"

    def forward(self, x: torch.Tensor, mode: Literal["norm", "denorm"]) -> torch.Tensor:
        """`x` 是 `[B, L, C]`。`mode` 是 `"norm"` 或 `"denorm"`。"""
        if x.dim() != 3:
            raise ValueError(f"RevIN 要 [B, L, C] 的輸入，拿到形狀 {tuple(x.shape)}")
        if x.shape[-1] != self.num_features:
            raise ValueError(f"RevIN 設定 {self.num_features} 個特徵，輸入有 {x.shape[-1]} 個")
        if mode == "norm":
            return self._normalize(x)
        if mode == "denorm":
            return self._denormalize(x)
        raise ValueError(f"mode 要是 'norm' 或 'denorm'，拿到 {mode!r}")

    def stats(self) -> tuple[torch.Tensor, torch.Tensor]:
        """上一次 `norm` 的 `(mean, std)`，形狀都是 `[B, 1, C]`。還沒 `norm` 過丟 `RuntimeError`。"""
        if self._mean is None or self._std is None:
            raise RuntimeError("RevIN 還沒做過 norm")
        return self._mean, self._std

    def _normalize(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] < 1:
            raise ValueError("RevIN 的視窗長度至少 1")
        with autocast_disabled(x.device):
            x32 = x.float()
            mean = x32.mean(dim=1, keepdim=True).detach()
            var = (x32 - mean).pow(2).mean(dim=1, keepdim=True)
            std = var.sqrt().detach()
            y = (x32 - mean) / (std + self.eps)
            if self.clip is not None:
                y = y.clamp(-self.clip, self.clip)
            if self.affine:
                y = y * self.affine_weight.float() + self.affine_bias.float()
        self._mean = mean
        self._std = std
        return y

    def _denormalize(self, x: torch.Tensor) -> torch.Tensor:
        mean, std = self.stats()
        if x.shape[0] != mean.shape[0]:
            raise ValueError(f"denorm 的 batch 大小 {x.shape[0]} 和上一次 norm 的 {mean.shape[0]} 不同")
        with autocast_disabled(x.device):
            y = x.float()
            if self.affine:
                y = (y - self.affine_bias.float()) / (self.affine_weight.float() + self.eps * self.eps)
            y = y * (std + self.eps) + mean
        return y
