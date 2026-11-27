"""LoRA（低秩適配，Hu et al., 2021），自己寫，不用 peft。

`LoRALinear` 包住一個 `nn.Linear`：原權重凍結，另外學 `B @ A`（秩 r），
輸出 = `base(x) + scale · B(A(dropout(x)))`，`scale = alpha / r`。
`B` 初始為 0，所以剛注入時輸出和原層完全一樣。

state_dict 的鍵名（給存讀 checkpoint 的人）：
- 原層變成 `<名字>.base.weight`、`<名字>.base.bias`。
- LoRA 參數是 `<名字>.lora_A` `[r, in]`、`<名字>.lora_B` `[out, r]`。
所以接續訓練時要先 `inject_lora`（同樣的 targets 和 r），再 `load_state_dict`。
注入之前存的檔（例如 last_k 那一階的 `best.pt`）要讀進注入之後的模型，先過 `adapt_state_dict_for_lora`。

直接讀 `.weight` 的程式（例如 `nn.MultiheadAttention` 的 `out_proj`、
`nn.TransformerEncoderLayer` 在 eval 的快速路徑）會拿到合併後的有效權重
`base.weight + scale · B @ A`，所以 LoRA 在那些路徑也有效，梯度也會傳到 A、B；
只是那條路徑不經過 LoRA 的 dropout。
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Iterable, Mapping

import torch
import torch.nn.functional as F
from torch import nn

from ._amp import autocast_disabled


class LoRALinear(nn.Module):
    """包住 `nn.Linear` 的 LoRA 層。

    - `base`：原本的 `nn.Linear`，`weight`、`bias` 設成 `requires_grad=False`。
    - `lora_A` `[r, in]`：kaiming uniform（`a = sqrt(5)`，和 `nn.Linear` 的預設一樣）。
    - `lora_B` `[out, r]`：全 0。
    - dropout 只作用在進 `A` 之前的輸入，不影響原層那一路。
    - `weight`、`bias`、`in_features`、`out_features` 和 `nn.Linear` 同名，
      `weight` 是合併後的有效權重（可微）。
    """

    def __init__(self, base: nn.Linear, r: int, alpha: float, dropout: float = 0.0) -> None:
        super().__init__()
        if not isinstance(base, nn.Linear):
            raise TypeError(f"LoRALinear 只包 nn.Linear，拿到 {type(base).__name__}")
        if r < 1:
            raise ValueError(f"LoRA 的 r 至少 1，拿到 {r}")
        if not (0.0 <= dropout < 1.0):
            raise ValueError(f"LoRA 的 dropout 要在 [0, 1)，拿到 {dropout}")
        self.base = base
        self.in_features = int(base.in_features)
        self.out_features = int(base.out_features)
        self.r = int(r)
        self.alpha = float(alpha)
        self.scale = self.alpha / self.r
        base.weight.requires_grad_(False)
        if base.bias is not None:
            base.bias.requires_grad_(False)

        ref = base.weight
        dtype = ref.dtype if ref.is_floating_point() else torch.float32
        self.lora_A = nn.Parameter(torch.empty(self.r, self.in_features, device=ref.device, dtype=dtype))
        self.lora_B = nn.Parameter(torch.zeros(self.out_features, self.r, device=ref.device, dtype=dtype))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
        self.lora_dropout: nn.Module = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.train(base.training)

    def extra_repr(self) -> str:
        return f"in_features={self.in_features}, out_features={self.out_features}, r={self.r}, alpha={self.alpha}"

    @property
    def weight(self) -> torch.Tensor:
        """合併後的有效權重 `base.weight + scale · B @ A`（可微）。"""
        return self.base.weight + (self.lora_B @ self.lora_A) * self.scale

    @property
    def bias(self) -> torch.Tensor | None:
        """原層的 bias（凍結）。"""
        return self.base.bias

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.base(x)
        delta = F.linear(F.linear(self.lora_dropout(x), self.lora_A), self.lora_B)
        return out + delta * self.scale

    def merge(self) -> nn.Linear:
        """回傳合併後的新 `nn.Linear`，權重 = `base.weight + scale · B @ A`。

        在 fp32 算完再轉回原層的 dtype。新層的 `requires_grad` 和原層一樣（通常是凍結），
        train/eval 狀態也照抄。原本這一層不會被改動。
        """
        base_w = self.base.weight
        has_bias = self.base.bias is not None
        merged = nn.Linear(
            self.in_features,
            self.out_features,
            bias=has_bias,
            device=base_w.device,
            dtype=base_w.dtype,
        )
        with torch.no_grad(), autocast_disabled(base_w.device):
            w = base_w.float() + (self.lora_B.float() @ self.lora_A.float()) * self.scale
            merged.weight.copy_(w.to(base_w.dtype))
            if has_bias:
                assert self.base.bias is not None
                merged.bias.copy_(self.base.bias)
        merged.weight.requires_grad_(base_w.requires_grad)
        if has_bias:
            assert self.base.bias is not None
            merged.bias.requires_grad_(self.base.bias.requires_grad)
        merged.train(self.training)
        return merged


def _parent_and_child(root: nn.Module, name: str) -> tuple[nn.Module, str]:
    parent_name, _, child = name.rpartition(".")
    parent = root.get_submodule(parent_name) if parent_name else root
    return parent, child


def inject_lora(
    module: nn.Module,
    target_names: Iterable[str],
    r: int,
    alpha: float,
    dropout: float = 0.0,
    layer_filter: Callable[[str], bool] | None = None,
) -> list[str]:
    """遞迴把名字最後一段在 `target_names` 的 `nn.Linear` 換成 `LoRALinear`。

    - 回傳這次新換掉的完整名稱（相對於 `module`，例如 `"0.self_attn.q_proj"`），照遍歷順序。
    - `layer_filter(name)` 回傳 False 的層跳過。
    - 已經是 `LoRALinear` 的層不重複注入，但會把它的 `lora_A`、`lora_B` 重新設成可訓練
      （`freeze_all()` 之後再呼叫一次就能接著訓練 LoRA）。它不算在回傳的名單裡。
    - 新的 `lora_A`、`lora_B` 放在原權重的裝置和 dtype 上。
    - `module` 自己就是 `nn.Linear` 時沒辦法原地換，會跳過。
    """
    targets = {str(t) for t in target_names}
    if not targets:
        raise ValueError("target_names 不能是空的")
    if r < 1:
        raise ValueError(f"LoRA 的 r 至少 1，拿到 {r}")
    entries = list(module.named_modules())
    lora_names = {name for name, sub in entries if isinstance(sub, LoRALinear)}
    replaced: list[str] = []
    for name, sub in entries:
        if not name:
            continue
        parent_name, _, child = name.rpartition(".")
        if child not in targets:
            continue
        if layer_filter is not None and not layer_filter(name):
            continue
        if isinstance(sub, LoRALinear):
            if sub.r != int(r):
                warnings.warn(f"{name} 已經注入 r={sub.r} 的 LoRA，這次要求 r={r}，沿用原本的", stacklevel=2)
            sub.lora_A.requires_grad_(True)
            sub.lora_B.requires_grad_(True)
            continue
        if not isinstance(sub, nn.Linear):
            continue
        if parent_name in lora_names:
            continue
        parent, child_name = _parent_and_child(module, name)
        setattr(parent, child_name, LoRALinear(sub, r=r, alpha=alpha, dropout=dropout))
        replaced.append(name)
    return replaced


def has_lora(module: nn.Module) -> bool:
    """`module` 裡有沒有任何 `LoRALinear`。"""
    return any(isinstance(m, LoRALinear) for m in module.modules())


def lora_parameters(module: nn.Module) -> list[nn.Parameter]:
    """所有 `LoRALinear` 的 `lora_A`、`lora_B`，照遍歷順序。"""
    params: list[nn.Parameter] = []
    for m in module.modules():
        if isinstance(m, LoRALinear):
            params.append(m.lora_A)
            params.append(m.lora_B)
    return params


def merge_lora(module: nn.Module) -> int:
    """就地把每個 `LoRALinear` 換回合併後的 `nn.Linear`，回傳換了幾個。

    合併後 state_dict 的鍵名回到原本的 `<名字>.weight`、`<名字>.bias`。
    `module` 自己就是 `LoRALinear` 時沒辦法原地換，請直接用 `module.merge()`。
    """
    entries = [(name, m) for name, m in module.named_modules() if name and isinstance(m, LoRALinear)]
    for name, m in entries:
        parent, child = _parent_and_child(module, name)
        setattr(parent, child, m.merge())
    return len(entries)


def adapt_state_dict_for_lora(module: nn.Module, state_dict: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    """把「注入 LoRA 之前」存的 state_dict 改成目前（已注入 LoRA）的 `module` 能讀的鍵名。

    用途：預設三階是 head → last_k → lora，最好的 epoch 可能在 last_k，那份 `best.pt` 的鍵是
    `...q_proj.weight`；注入 LoRA 後模型要的是 `...q_proj.base.weight`、`...lora_A`、`...lora_B`。
    - `<名字>.weight`、`<名字>.bias` 改名成 `<名字>.base.weight`、`<名字>.base.bias`。
    - 沒有 `lora_A`、`lora_B` 的層：`lora_A` 用目前的值，`lora_B` 填 0，所以讀進來的函數和存檔時完全一樣。
    - 本來就有 LoRA 鍵的 state_dict 原樣回傳（只複製 dict，不複製張量）。
    `module` 要和存檔時是同一層（通常是整個 `TWFMModel`），鍵名才對得上。
    用法：`model.load_state_dict(adapt_state_dict_for_lora(model, ckpt["model"]))`。
    """
    sd = dict(state_dict)
    for name, m in module.named_modules():
        if not isinstance(m, LoRALinear):
            continue
        prefix = f"{name}." if name else ""
        for leaf in ("weight", "bias"):
            old_key = f"{prefix}{leaf}"
            new_key = f"{prefix}base.{leaf}"
            if old_key in sd and new_key not in sd:
                sd[new_key] = sd.pop(old_key)
        a_key = f"{prefix}lora_A"
        b_key = f"{prefix}lora_B"
        if f"{prefix}base.weight" in sd and a_key not in sd and b_key not in sd:
            sd[a_key] = m.lora_A.detach().clone()
            sd[b_key] = torch.zeros_like(m.lora_B, requires_grad=False)
    return sd


def count_trainable(module: nn.Module) -> tuple[int, int]:
    """回傳 `(可訓練參數個數, 全部參數個數)`，以元素數計，共用的參數只算一次。"""
    trainable = 0
    total = 0
    for p in module.parameters():
        n = p.numel()
        total += n
        if p.requires_grad:
            trainable += n
    return trainable, total
