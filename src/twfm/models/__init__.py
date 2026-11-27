"""模型：主幹（Kronos、PatchTransformer）、RevIN、LoRA、FiLM 協變量 head、完整模型。

這裡不在 import 時載入任何子模組，`import twfm.models` 不會載入 torch。
`from twfm.models import TWFMModel` 這類寫法用 PEP 562 的 `__getattr__` 延後載入，
第一次取用時才 import 對應的子模組（那時才需要 torch）。

模組：
    revin      RevIN（逐樣本標準化，Kronos 的輸入處理）
    lora       LoRALinear、inject_lora、merge_lora 等（自己寫，不用 peft）
    backbones  Backbone、KronosBackbone、PatchTransformerBackbone、build_backbone
    heads      FiLMCovariateHead
    model      TWFMModel、build_model（含 LLRD 的參數分組）
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, str] = {
    "RevIN": "revin",
    "LoRALinear": "lora",
    "inject_lora": "lora",
    "lora_parameters": "lora",
    "merge_lora": "lora",
    "count_trainable": "lora",
    "has_lora": "lora",
    "adapt_state_dict_for_lora": "lora",
    "Backbone": "backbones",
    "KronosBackbone": "backbones",
    "PatchTransformerBackbone": "backbones",
    "build_backbone": "backbones",
    "import_kronos": "backbones",
    "FiLMCovariateHead": "heads",
    "TWFMModel": "model",
    "build_model": "model",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f".{module_name}", __name__)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
