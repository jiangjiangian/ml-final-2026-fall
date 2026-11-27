"""完整模型：主幹（Kronos 或 PatchTransformer）加 FiLM 協變量 head，和分層學習率的參數分組。"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from typing import Any

import torch
from torch import nn

from ..config import PipelineConfig, StageConfig
from .backbones import Backbone, build_backbone
from .heads import FiLMCovariateHead


def _no_weight_decay(p: nn.Parameter) -> bool:
    """bias 和 norm 的權重（都是一維）不做 weight decay。"""
    return p.ndim <= 1


class TWFMModel(nn.Module):
    """`backbone.encode(batch)` 得 `repr [B, d_model]`，再進 `head` 得分數。

    `forward(batch)` 回傳 `score [B]`、`repr [B, d_model]`，有分位數頭時另有 `quantiles [B, Q]`，都是 fp32。
    `batch` 是 `PanelWindowDataset` 的 dict：Kronos 用 `levels`、`stamps`，PatchTransformer 用 `rets`，
    head 用 `stock_cov`、`market_cov`（沒有協變量時是 `[B, 0]` 或不給）。
    """

    def __init__(self, backbone: Backbone, head: FiLMCovariateHead, quantiles: Iterable[float] = ()) -> None:
        super().__init__()
        if head.d_model != backbone.d_model:
            raise ValueError(f"head 的 d_model {head.d_model} 和主幹的 {backbone.d_model} 不同")
        self.backbone = backbone
        self.head = head
        self.quantiles: tuple[float, ...] = tuple(float(q) for q in quantiles)
        if len(self.quantiles) != head.n_quantiles:
            raise ValueError(f"quantiles 有 {len(self.quantiles)} 個，head 的分位數頭有 {head.n_quantiles} 個")

    def forward(self, batch: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        rep = self.backbone(batch)
        return self.forward_from_repr(rep, batch.get("stock_cov"), batch.get("market_cov"))

    def forward_from_repr(
        self,
        rep: torch.Tensor,
        stock_cov: torch.Tensor | None = None,
        market_cov: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """從已算好的主幹表示（例如快取的 embedding）只跑 head。輸出格式和 `forward` 一樣。"""
        out = self.head(rep, stock_cov, market_cov)
        out["repr"] = rep
        return out

    def param_groups(self, stage: StageConfig, weight_decay: float) -> list[dict[str, Any]]:
        """給 AdamW 的參數分組（LLRD，分層學習率）。只收 `requires_grad=True` 的參數。

        - head：`lr_head`。
        - 主幹最後一個 block 之上的 norm（`top_params`）：`lr_backbone`，和最深的 block 一樣。
        - 主幹第 j 個 block（共 n 個，0 最淺）：`lr_backbone × layer_decay^(n − 1 − j)`。
        - embedding（最底層）：`lr_backbone × layer_decay^n`。
        - 其他還可訓練的主幹參數（正常不會有）也用 embedding 的學習率，並發出警告。
        - `never_train_params()`（Kronos 的 tokenizer、`head`、`dep_layer`）一律不收。
        - 每組再分成要不要 weight decay：一維的參數（bias、norm 權重）weight decay 0。
        - LoRA 參數在它所在的 block 裡，學習率照那個 block 的 LLRD。

        回傳的每個 dict 有 `params`、`lr`、`weight_decay`、`name`（AdamW 會保留 `name`，方便記錄）。
        空的組不放；沒有任何可訓練參數時回傳空 list。
        """
        bb = self.backbone
        n = len(bb.blocks)
        lr_bb = float(stage.lr_backbone)
        decay = float(stage.layer_decay)
        never = {id(p) for p in bb.never_train_params()}
        seen: set[int] = set()
        groups: list[dict[str, Any]] = []

        def add(name: str, params: Iterable[nn.Parameter], lr: float) -> None:
            with_wd: list[nn.Parameter] = []
            without_wd: list[nn.Parameter] = []
            for p in params:
                if id(p) in seen or id(p) in never or not p.requires_grad:
                    continue
                seen.add(id(p))
                (without_wd if _no_weight_decay(p) else with_wd).append(p)
            if with_wd:
                groups.append({"name": name, "params": with_wd, "lr": lr, "weight_decay": float(weight_decay)})
            if without_wd:
                groups.append({"name": f"{name}_no_wd", "params": without_wd, "lr": lr, "weight_decay": 0.0})

        add("head", self.head.parameters(), float(stage.lr_head))
        add("backbone_top", bb.top_params(), lr_bb)
        for j in reversed(range(n)):
            add(f"block_{j}", bb.blocks[j].parameters(), lr_bb * decay ** (n - 1 - j))
        lr_emb = lr_bb * decay**n
        add("embedding", bb.embedding_params(), lr_emb)

        leftover = [p for p in self.parameters() if p.requires_grad and id(p) not in seen and id(p) not in never]
        if leftover:
            warnings.warn(
                f"有 {len(leftover)} 個可訓練參數不在 head、block、embedding 裡，用 embedding 的學習率",
                stacklevel=2,
            )
            add("backbone_other", leftover, lr_emb)
        leaked = [p for p in bb.never_train_params() if p.requires_grad]
        if leaked:
            warnings.warn(
                f"有 {len(leaked)} 個永遠凍結的參數被設成可訓練，已排除在 optimizer 之外",
                stacklevel=2,
            )
        return groups


def build_model(
    cfg: PipelineConfig,
    n_stock_cov: int,
    n_market_cov: int,
    gradient_checkpointing: bool = False,
) -> TWFMModel:
    """依設定建完整模型。主幹見 `build_backbone`，head 用 `head_hidden`、`head_dropout`、`quantiles`。

    模型建好在 CPU，要自己 `.to(device)`。
    """
    mc = cfg.model
    backbone = build_backbone(mc, gradient_checkpointing=gradient_checkpointing)
    head = FiLMCovariateHead(
        d_model=backbone.d_model,
        n_stock_cov=int(n_stock_cov),
        n_market_cov=int(n_market_cov),
        hidden=int(mc.head_hidden),
        dropout=float(mc.head_dropout),
        n_quantiles=len(mc.quantiles),
    )
    return TWFMModel(backbone, head, quantiles=mc.quantiles)
