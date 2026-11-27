"""混合精度的小工具：在 AMP 裡面暫時關掉 autocast，和查目前 autocast 的 dtype。

RevIN、Kronos tokenizer、LoRA 合併都要在 fp32 算：`amount`、`adj_volume` 可到 1e10，
fp16 最大約 6.5e4，直接進 fp16 會溢位；tokenizer 的量化是看正負號，精度掉了 token 會變。
"""

from __future__ import annotations

import contextlib
from typing import ContextManager

import torch

_AUTOCAST_DEVICES: tuple[str, ...] = ("cuda", "cpu")


def autocast_disabled(device: torch.device | str) -> ContextManager[object]:
    """回傳關掉 autocast 的 context。

    只有 `cuda`、`cpu` 有 autocast，其他裝置（例如 `mps`）回傳空的 context，
    避免舊版 torch 對不支援的 `device_type` 丟錯。
    """
    device_type = torch.device(device).type
    if device_type in _AUTOCAST_DEVICES:
        return torch.autocast(device_type=device_type, enabled=False)
    return contextlib.nullcontext()


def active_autocast_dtype(device: torch.device | str) -> torch.dtype | None:
    """這個裝置目前 autocast 開著的話回傳它的 dtype（例如 fp16），沒開回傳 None。

    torch ≥ 2.4 用 `torch.is_autocast_enabled(device_type)`、`torch.get_autocast_dtype`；
    更舊的版本用 GPU、CPU 各自的舊函式。
    """
    device_type = torch.device(device).type
    if device_type not in _AUTOCAST_DEVICES:
        return None
    if hasattr(torch, "get_autocast_dtype"):
        try:
            if torch.is_autocast_enabled(device_type):
                return torch.get_autocast_dtype(device_type)
            return None
        except TypeError:
            pass
    if device_type == "cuda":
        return torch.get_autocast_gpu_dtype() if torch.is_autocast_enabled() else None
    return torch.get_autocast_cpu_dtype() if torch.is_autocast_cpu_enabled() else None
