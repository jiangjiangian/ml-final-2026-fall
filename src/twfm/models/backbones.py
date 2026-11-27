"""主幹（backbone）：把一個視窗變成一個向量 `[B, d_model]`（視窗最後一個位置的表示）。

兩種：
- `KronosBackbone`：預訓練的 Kronos（預設 Kronos-small，搭 Kronos-Tokenizer-base）。
  輸入是還原後的價格水準 `levels [B, L, 6]`，和 Kronos 預訓練看的一樣。
- `PatchTransformerBackbone`：從頭訓練的對照，輸入是對數報酬 `rets [B, L, 5]`。

時間規則：視窗的每一列都在 i 以前（`PanelStore.window` 已保證），
Kronos 的 transformer 是因果注意力，最後一個位置只看得到它自己和之前的列。

分層解凍和 LLRD（分層學習率）用的介面在 `Backbone`：
`blocks`（由淺到深）、`embedding_params()`（最底層）、`top_params()`（最後一個 block 之上的 norm）、
`never_train_params()`（永遠不訓練，例如 Kronos 的 tokenizer、`head`、`dep_layer`）。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from collections.abc import Iterable, Mapping
from typing import Any

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint

from ..config import ModelConfig
from ._amp import active_autocast_dtype, autocast_disabled
from .revin import RevIN

# 從 `Kronos.from_pretrained` 讀回來重建隨機初始化模型用的設定欄位。
KRONOS_CONFIG_KEYS: tuple[str, ...] = (
    "s1_bits",
    "s2_bits",
    "n_layers",
    "d_model",
    "n_heads",
    "ff_dim",
    "ffn_dropout_p",
    "attn_dropout_p",
    "resid_dropout_p",
    "token_dropout_p",
    "learn_te",
)
N_LEVEL_FEATURES: int = 6
N_RET_FEATURES: int = 5
N_STAMP_FEATURES: int = 5


def _unique_params(modules: Iterable[nn.Module]) -> list[nn.Parameter]:
    """多個模組的參數接起來，同一個參數只出現一次。"""
    seen: set[int] = set()
    out: list[nn.Parameter] = []
    for m in modules:
        for p in m.parameters():
            if id(p) not in seen:
                seen.add(id(p))
                out.append(p)
    return out


def _require(batch: Mapping[str, torch.Tensor], key: str) -> torch.Tensor:
    if key not in batch:
        raise KeyError(f"batch 少了 {key!r}，現有的鍵：{sorted(batch.keys())}")
    return batch[key]


class Backbone(nn.Module):
    """主幹的抽象基底。

    子類別要提供：
    - `d_model: int`：輸出向量的維度。
    - `blocks`：`nn.ModuleList`，由淺到深，給分層解凍、LLRD 和 LoRA 用。
    - `encode(batch) -> [B, d_model]`：視窗最後一個位置的表示。
    - `embedding_modules()`：最底層（LLRD 用最小學習率）。

    可以覆寫：`top_modules()`（最後一個 block 之上，例如最後的 norm，學習率和最深的 block 一樣）、
    `never_train_params()`（永遠凍結，`unfreeze_*` 不會打開，`param_groups` 也不收）。

    `frozen_eval`（預設 True）：主幹沒有任何可訓練參數時，`train()` 會讓主幹維持 eval，
    dropout 關掉。這樣只訓練 head 時看到的表示，和快取 embedding、linear probe 看到的一樣。
    主幹只要有一個參數可訓練（`last_k`、`lora`、`all`），就照一般的 train 模式（dropout 打開）。
    `freeze_all`、`unfreeze_*` 之後會依最近一次要求的模式重新套用。

    `gradient_checkpointing`：True 時訓練中每個 block 用 `torch.utils.checkpoint` 重算，省記憶體。
    """

    d_model: int

    def __init__(self) -> None:
        super().__init__()
        self.gradient_checkpointing: bool = False
        self.frozen_eval: bool = True
        self._requested_train: bool = True

    # ---- 子類別要實作的 ----------------------------------------------------

    @property
    def blocks(self) -> nn.ModuleList:
        """由淺到深的 block。"""
        raise NotImplementedError

    def encode(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        """回傳 `[B, d_model]`，視窗最後一個位置的表示（fp32）。"""
        raise NotImplementedError

    def embedding_modules(self) -> list[nn.Module]:
        """最底層的模組。"""
        raise NotImplementedError

    def top_modules(self) -> list[nn.Module]:
        """最後一個 block 之上的模組（預設沒有）。"""
        return []

    def never_train_params(self) -> list[nn.Parameter]:
        """永遠不訓練的參數（預設沒有）。"""
        return []

    # ---- 共用的 ------------------------------------------------------------

    def forward(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        """同 `encode`，但先確認 train/eval 符合 `frozen_eval` 的規則。

        例如 `freeze_all()` 之後才 `inject_lora`（LoRA 參數變成可訓練），
        不用再呼叫一次 `train()`，這裡就會切回 train 模式。
        """
        if self._requested_train:
            want = not (self.frozen_eval and not self.has_trainable())
            if want != self.training:
                self._sync_mode()
        return self.encode(batch)

    def embedding_params(self) -> list[nn.Parameter]:
        """最底層的參數（LLRD 用 `lr_backbone × layer_decay^n`）。不含永遠凍結的。"""
        never = {id(p) for p in self.never_train_params()}
        return [p for p in _unique_params(self.embedding_modules()) if id(p) not in never]

    def top_params(self) -> list[nn.Parameter]:
        """最後一個 block 之上的參數（LLRD 用 `lr_backbone`）。不含永遠凍結的。"""
        never = {id(p) for p in self.never_train_params()}
        return [p for p in _unique_params(self.top_modules()) if id(p) not in never]

    def block_params(self, j: int) -> list[nn.Parameter]:
        """第 j 個 block 的參數（0 最淺）。不含永遠凍結的。"""
        never = {id(p) for p in self.never_train_params()}
        return [p for p in self.blocks[j].parameters() if id(p) not in never]

    def freeze_all(self) -> None:
        """主幹所有參數都設成 `requires_grad=False`（含 LoRA）。"""
        for p in self.parameters():
            p.requires_grad_(False)
        self._sync_mode()

    def unfreeze_last(self, k: int) -> None:
        """打開最後 k 個 block，k ≥ 1 時連 block 之上的 norm 一起打開。

        k 大於 block 數就全部 block 打開；k = 0 什麼都不做。
        已注入 LoRA 的 block，原權重也會一起打開（整個 block 都可訓練）。
        """
        k = int(k)
        if k < 0:
            raise ValueError(f"k 不能是負的，拿到 {k}")
        n = len(self.blocks)
        k = min(k, n)
        if k == 0:
            return
        never = {id(p) for p in self.never_train_params()}
        for j in range(n - k, n):
            for p in self.blocks[j].parameters():
                if id(p) not in never:
                    p.requires_grad_(True)
        for p in self.top_params():
            p.requires_grad_(True)
        self._sync_mode()

    def unfreeze_all(self) -> None:
        """除了 `never_train_params()` 以外全部打開（`all` 那一階用）。"""
        never = {id(p) for p in self.never_train_params()}
        for p in self.parameters():
            if id(p) not in never:
                p.requires_grad_(True)
        self._sync_mode()

    def has_trainable(self) -> bool:
        """主幹有沒有任何可訓練的參數（不算永遠凍結的）。"""
        never = {id(p) for p in self.never_train_params()}
        return any(p.requires_grad and id(p) not in never for p in self.parameters())

    def train(self, mode: bool = True) -> Backbone:
        """照 `frozen_eval` 的規則設定 train/eval，再呼叫 `_after_set_mode`。"""
        if not isinstance(mode, bool):
            raise ValueError("train 的 mode 要是 bool")
        self._requested_train = mode
        effective = mode and not (self.frozen_eval and not self.has_trainable())
        super().train(effective)
        self._after_set_mode()
        return self

    def _after_set_mode(self) -> None:
        """設定 train/eval 之後的掛鉤（例如讓 tokenizer 一直是 eval）。"""

    def _sync_mode(self) -> None:
        self.train(self._requested_train)

    def _use_checkpoint(self) -> bool:
        return bool(self.gradient_checkpointing and self.training and torch.is_grad_enabled())


# ---------------------------------------------------------------------------
# Kronos
# ---------------------------------------------------------------------------


def _module_under(mod: Any, root: str) -> bool:
    """模組 `mod` 的檔案是不是在 `root` 底下。"""
    paths: list[str] = []
    f = getattr(mod, "__file__", None)
    if f:
        paths.append(str(f))
    paths.extend(str(p) for p in list(getattr(mod, "__path__", []) or []))
    if not paths:
        return False
    root_abs = os.path.realpath(root)
    for p in paths:
        p_abs = os.path.realpath(p)
        if p_abs != root_abs and not p_abs.startswith(root_abs + os.sep):
            return False
    return True


def import_kronos(src_dir: str | None) -> tuple[type, type]:
    """從 Kronos 原始碼目錄 import `(Kronos, KronosTokenizer)`。

    - `src_dir` 是 clone 下來的 `shiyu-coder/Kronos` 根目錄（裡面有 `model/kronos.py`）。
      None 時改用環境變數 `KRONOS_SRC`；兩個都沒有就假設 `model` 已經在 `sys.path` 上。
    - 根目錄放到 `sys.path[0]`。官方 `kronos.py` 用 `from model.module import *`，所以一定要這樣。
    - `sys.modules` 裡已經有別的 `model`（不在這個根目錄底下）就先移掉，並發出警告。
    - 這裡才會 import `huggingface_hub`、`einops`（官方程式在 import 時載入）。
    """
    src = src_dir or os.environ.get("KRONOS_SRC")
    root: str | None = None
    if src:
        root = os.path.realpath(os.path.expanduser(str(src)))
        if not os.path.isfile(os.path.join(root, "model", "kronos.py")):
            raise FileNotFoundError(
                f"{root} 底下找不到 model/kronos.py。kronos_src_dir 要指到 clone 下來的 Kronos 根目錄"
            )
        sys.path[:] = [p for p in sys.path if os.path.realpath(p or ".") != root]
        sys.path.insert(0, root)
        loaded = sys.modules.get("model")
        if loaded is not None and not _module_under(loaded, os.path.join(root, "model")):
            warnings.warn(
                f"sys.modules 裡的 'model' 不是 {root} 的 Kronos，先移掉再重新 import",
                stacklevel=2,
            )
            for name in [n for n in list(sys.modules) if n == "model" or n.startswith("model.")]:
                del sys.modules[name]
    try:
        mod = importlib.import_module("model")
    except ImportError as exc:
        raise ImportError(
            "import Kronos 失敗。請設定 ModelConfig.kronos_src_dir 或環境變數 KRONOS_SRC，"
            "並確認已安裝 huggingface_hub、einops、safetensors、tqdm"
        ) from exc
    if root is not None and not _module_under(mod, os.path.join(root, "model")):
        raise ImportError(f"import 到的 'model' 不在 {root}：{getattr(mod, '__file__', None)}")
    kronos_cls = getattr(mod, "Kronos", None)
    tokenizer_cls = getattr(mod, "KronosTokenizer", None)
    if kronos_cls is None or tokenizer_cls is None:
        raise ImportError("Kronos 的 model 套件裡沒有 Kronos 或 KronosTokenizer")
    return kronos_cls, tokenizer_cls


class KronosBackbone(Backbone):
    """預訓練的 Kronos 當主幹。

    載入：`kronos_src_dir`（或環境變數 `KRONOS_SRC`）加進 `sys.path`，`from model import Kronos, KronosTokenizer`，
    再 `KronosTokenizer.from_pretrained(kronos_tokenizer_id)`、`Kronos.from_pretrained(kronos_model_id)`。
    兩個 id 可以是 Hugging Face 的名稱（要連網）或本機資料夾。

    `kronos_pretrained=False`：讀預訓練模型的設定（`s1_bits` 等 11 個欄位）重建一個隨機初始化的 Kronos。
    tokenizer 仍用預訓練的、凍結。完全從頭（連 tokenizer 一起）要另外用官方 `finetune_csv` 訓練 tokenizer。

    `encode` 的流程：
    `levels [B, L, 6]`（open, high, low, close, volume, amount）
    → `RevIN(6, affine=False, clip=kronos_clip)`（和官方 Kronos 的輸入處理一樣，fp32）
    → `tokenizer.encode(x, half=True)` 得 `[s1_ids, s2_ids]`（凍結、eval、`no_grad`、fp32）
    → `model.embedding([s1_ids, s2_ids])` → 有 `use_time_stamp` 就加 `model.time_emb(stamps)`
    → `model.token_drop` → 依序過 `model.transformer` 的每個 block → `model.norm` → 取 `[:, -1, :]`。

    不呼叫 `model.head`、`model.dep_layer`：`dep_layer` 的交叉注意力在 `eval()` 時不是因果的，會看到後面的位置。
    它們的參數設成 `requires_grad=False`，列在 `never_train_params()`，不進任何 optimizer。

    tokenizer 是註冊的子模組（跟著 `.to(device)` 走、會存進 state_dict），但永遠凍結：
    `train()` 之後會被設回 eval，`unfreeze_*` 不會打開它，前向一律在 `no_grad` 裡。
    """

    def __init__(self, cfg: ModelConfig, gradient_checkpointing: bool = False) -> None:
        super().__init__()
        kronos_cls, tokenizer_cls = import_kronos(cfg.kronos_src_dir)
        tokenizer = tokenizer_cls.from_pretrained(cfg.kronos_tokenizer_id)
        model = kronos_cls.from_pretrained(cfg.kronos_model_id)
        if not cfg.kronos_pretrained:
            conf = {key: getattr(model, key) for key in KRONOS_CONFIG_KEYS}
            del model
            model = kronos_cls(**conf)
        # 官方類別都會存這些屬性；萬一某一版沒有，就跳過那項檢查，不讓建構失敗。
        bits_tok = (getattr(tokenizer, "s1_bits", None), getattr(tokenizer, "s2_bits", None))
        bits_model = (getattr(model, "s1_bits", None), getattr(model, "s2_bits", None))
        if None not in bits_tok and None not in bits_model:
            if tuple(int(b) for b in bits_tok) != tuple(int(b) for b in bits_model):
                raise ValueError(f"tokenizer 的 s1/s2 bits {bits_tok} 和模型的 {bits_model} 對不上")
        d_in = getattr(tokenizer, "d_in", None)
        if d_in is not None and int(d_in) != N_LEVEL_FEATURES:
            raise ValueError(f"Kronos tokenizer 的 d_in 是 {d_in}，這裡的 levels 有 {N_LEVEL_FEATURES} 欄")

        for p in tokenizer.parameters():
            p.requires_grad_(False)
        tokenizer.eval()
        for p in model.head.parameters():
            p.requires_grad_(False)
        for p in model.dep_layer.parameters():
            p.requires_grad_(False)

        self.tokenizer = tokenizer
        self.model = model
        self.revin = RevIN(N_LEVEL_FEATURES, eps=1e-5, affine=False, clip=cfg.kronos_clip)
        self.d_model = int(model.d_model)
        self.use_time_stamp = bool(cfg.use_time_stamp)
        self.gradient_checkpointing = bool(gradient_checkpointing)
        self.model_id = str(cfg.kronos_model_id)
        self.tokenizer_id = str(cfg.kronos_tokenizer_id)
        self.pretrained = bool(cfg.kronos_pretrained)
        # 一開始就不可訓練的參數（learn_te=False 時的固定 sin/cos 時間編碼），用名字記，`.to()` 之後也對得上。
        self._fixed_param_names: frozenset[str] = frozenset(
            f"model.{name}" for name, p in model.named_parameters() if not p.requires_grad
        )
        self._rope_key: tuple[torch.device, int, torch.dtype] | None = None
        self.train(True)

    # ---- Backbone 介面 ------------------------------------------------------

    @property
    def blocks(self) -> nn.ModuleList:
        return self.model.transformer

    def embedding_modules(self) -> list[nn.Module]:
        return [self.model.embedding, self.model.time_emb]

    def top_modules(self) -> list[nn.Module]:
        return [self.model.norm]

    def never_train_params(self) -> list[nn.Parameter]:
        params = _unique_params([self.tokenizer, self.model.head, self.model.dep_layer])
        seen = {id(p) for p in params}
        for name, p in self.named_parameters():
            if name in self._fixed_param_names and id(p) not in seen:
                seen.add(id(p))
                params.append(p)
        return params

    def _after_set_mode(self) -> None:
        self.tokenizer.eval()

    # ---- 前向 ---------------------------------------------------------------

    def encode(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        """`batch["levels"]` `[B, L, 6]`，有 `use_time_stamp` 時另需 `batch["stamps"]` `[B, L, 5]`。回傳 `[B, d_model]`。"""
        levels = _require(batch, "levels")
        if levels.dim() != 3 or levels.shape[-1] != N_LEVEL_FEATURES:
            raise ValueError(f"levels 要是 [B, L, {N_LEVEL_FEATURES}]，拿到 {tuple(levels.shape)}")
        stamps = _require(batch, "stamps") if self.use_time_stamp else None
        x_norm = self.revin(levels, "norm")
        hidden = self._forward_normalized(x_norm, stamps)
        return hidden[:, -1, :]

    def _tokenize(self, x_norm: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """已標準化的 `[B, L, 6]` → `(s1_ids, s2_ids)`，各 `[B, L]` int64。凍結、fp32、不留梯度。"""
        with torch.no_grad(), autocast_disabled(x_norm.device):
            ids = self.tokenizer.encode(x_norm.float(), half=True)
        s1_ids, s2_ids = ids[0], ids[1]
        return s1_ids.long(), s2_ids.long()

    def _forward_normalized(self, x_norm: torch.Tensor, stamps: torch.Tensor | None = None) -> torch.Tensor:
        """從已標準化的輸入算每個位置的隱藏狀態 `[B, L, d_model]`（fp32）。

        私有介面：給因果測試用（只改最後一根，前面位置的輸出要不變）。
        正常使用請呼叫 `encode`。
        """
        if x_norm.dim() != 3 or x_norm.shape[-1] != N_LEVEL_FEATURES:
            raise ValueError(f"x_norm 要是 [B, L, {N_LEVEL_FEATURES}]，拿到 {tuple(x_norm.shape)}")
        self._prepare_rope(x_norm.device, x_norm.shape[1])
        m = self.model
        s1_ids, s2_ids = self._tokenize(x_norm)
        h = m.embedding([s1_ids, s2_ids])
        if stamps is not None:
            if stamps.dim() != 3 or tuple(stamps.shape[:2]) != tuple(x_norm.shape[:2]) or stamps.shape[-1] != N_STAMP_FEATURES:
                raise ValueError(
                    f"stamps 要是 [B, L, {N_STAMP_FEATURES}] 且 B、L 和 levels 一樣，拿到 {tuple(stamps.shape)}"
                )
            h = h + m.time_emb(stamps)
        h = m.token_drop(h)
        use_ckpt = self._use_checkpoint()
        for block in m.transformer:
            if use_ckpt:
                h = checkpoint(block, h, None, use_reentrant=False)
            else:
                h = block(h, key_padding_mask=None)
        h = m.norm(h)
        return h.float()

    # ---- RoPE 快取 ----------------------------------------------------------

    @staticmethod
    def _rope_modules_of(root: nn.Module) -> list[nn.Module]:
        """`root` 裡所有官方的 `RotaryPositionalEmbedding`（看屬性認，不 import 類別）。"""
        return [m for m in root.modules() if hasattr(m, "seq_len_cached") and hasattr(m, "inv_freq")]

    def _reset_rope_cache(self) -> None:
        """清掉官方 RoPE 的 cos/sin 快取。

        官方 `RotaryPositionalEmbedding` 把快取存成一般屬性、只看序列長度，
        `.to(device)` 不會搬它，換裝置後同樣長度會拿到舊裝置的快取而出錯。
        """
        for m in self._rope_modules_of(self):
            m.seq_len_cached = None
            m.cos_cached = None
            m.sin_cached = None
        self._rope_key = None

    def _prepare_rope(self, device: torch.device, seq_len: int) -> None:
        """裝置、長度或 autocast 狀態變了，就重建 RoPE 的 cos/sin 快取。

        - 角度一律在 fp32（關掉 autocast）算，結果是確定的，不會因為先跑訓練還是預測而不同。
          官方的快取在第一次前向時才算，如果那時在 AMP 裡，角度會用 fp16 算，位置越後面誤差越大。
        - tokenizer 的快取留在 fp32（tokenizer 一律在 fp32 跑）。
        - transformer 的快取轉成目前 autocast 的 dtype（AMP 裡是 fp16，沒有 AMP 是 fp32），
          這樣 q、k 乘上 cos/sin 之後仍和 v 同一個 dtype，`scaled_dot_product_attention` 不會拿到混合 dtype。
        - 快取一律在 `inference_mode` 之外建：預測若用 `torch.inference_mode()`，
          在裡面建的快取之後拿去訓練會出錯（inference tensor 不能存給反向傳播）。
        """
        amp_dtype = active_autocast_dtype(device)
        model_dtype = amp_dtype if amp_dtype is not None else torch.float32
        key = (device, int(seq_len), model_dtype)
        if self._rope_key == key:
            return
        groups = ((self.tokenizer, torch.float32), (self.model, model_dtype))
        with torch.inference_mode(False), torch.no_grad(), autocast_disabled(device):
            dummy = torch.empty(0, device=device)
            for root, dtype in groups:
                for m in self._rope_modules_of(root):
                    m.seq_len_cached = None
                    m.cos_cached = None
                    m.sin_cached = None
                    update = getattr(m, "_update_cos_sin_cache", None)
                    if not callable(update):
                        continue
                    update(dummy, int(seq_len))
                    if m.cos_cached is not None and m.sin_cached is not None:
                        m.cos_cached = m.cos_cached.float().to(dtype)
                        m.sin_cached = m.sin_cached.float().to(dtype)
        self._rope_key = key

    def _apply(self, *args: Any, **kwargs: Any) -> KronosBackbone:
        out = super()._apply(*args, **kwargs)
        self._reset_rope_cache()
        return out


# ---------------------------------------------------------------------------
# PatchTransformer（從頭訓練的對照）
# ---------------------------------------------------------------------------


class PatchTransformerBackbone(Backbone):
    """從頭訓練的 PatchTST 式主幹（對照組）。

    `rets [B, L, 5]` → `RevIN(5, affine=True)` → 切成長度 `patch_len` 不重疊的 patch
    （L 不整除時丟掉最前面的餘數，保留最近的列）→ 線性投影到 `patch_d_model`
    → 加可學的位置編碼 → `patch_layers` 層 `nn.TransformerEncoderLayer(batch_first=True, norm_first=True)`
    → 取最後一個 patch → `LayerNorm`。

    所有 patch 都在 i 以前，所以不需要因果遮罩。
    位置編碼從最後面往回對齊：最近的 patch 永遠用同一個位置向量，換 lookback 也不會錯位。
    patch 數最多 `max_patches`，超過丟 `ValueError`。

    LoRA 注意：`nn.TransformerEncoderLayer` 裡的線性層叫 `self_attn.out_proj`、`linear1`、`linear2`
    （q/k/v 是合在一起的 `in_proj_weight`，不是 `nn.Linear`）。
    預設的 `lora_targets` 在這裡只會碰到 `out_proj`；要連 FFN 一起，請在 targets 加 `linear1`、`linear2`。
    """

    def __init__(
        self,
        cfg: ModelConfig,
        n_features: int = N_RET_FEATURES,
        max_patches: int = 256,
        dropout: float = 0.1,
        gradient_checkpointing: bool = False,
    ) -> None:
        super().__init__()
        if max_patches < 1:
            raise ValueError("max_patches 至少 1")
        self.n_features = int(n_features)
        self.patch_len = int(cfg.patch_len)
        self.max_patches = int(max_patches)
        self.d_model = int(cfg.patch_d_model)
        self.gradient_checkpointing = bool(gradient_checkpointing)

        self.revin = RevIN(self.n_features, eps=1e-5, affine=True)
        self.patch_proj = nn.Linear(self.patch_len * self.n_features, self.d_model)
        self.pos_emb = nn.Parameter(torch.zeros(self.max_patches, self.d_model))
        nn.init.trunc_normal_(self.pos_emb, std=0.02)
        self.layers = nn.ModuleList(
            [
                nn.TransformerEncoderLayer(
                    d_model=self.d_model,
                    nhead=int(cfg.patch_heads),
                    dim_feedforward=4 * self.d_model,
                    dropout=float(dropout),
                    activation="gelu",
                    batch_first=True,
                    norm_first=True,
                )
                for _ in range(int(cfg.patch_layers))
            ]
        )
        self.final_norm = nn.LayerNorm(self.d_model)
        self.train(True)

    @property
    def blocks(self) -> nn.ModuleList:
        return self.layers

    def embedding_modules(self) -> list[nn.Module]:
        return [self.revin, self.patch_proj]

    def embedding_params(self) -> list[nn.Parameter]:
        return super().embedding_params() + [self.pos_emb]

    def top_modules(self) -> list[nn.Module]:
        return [self.final_norm]

    def _patchify(self, x: torch.Tensor) -> torch.Tensor:
        """`[B, L, C]` → `[B, n, patch_len · C]`，丟掉最前面 `L mod patch_len` 列。"""
        b, length, c = x.shape
        n = length // self.patch_len
        if n < 1:
            raise ValueError(f"視窗長度 {length} 比 patch_len {self.patch_len} 短")
        if n > self.max_patches:
            raise ValueError(f"patch 數 {n} 超過 max_patches {self.max_patches}，請調大 max_patches")
        start = length - n * self.patch_len
        x = x[:, start:, :].contiguous()
        return x.reshape(b, n, self.patch_len * c)

    def encode(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        """`batch["rets"]` `[B, L, 5]` → `[B, patch_d_model]`。"""
        rets = _require(batch, "rets")
        if rets.dim() != 3 or rets.shape[-1] != self.n_features:
            raise ValueError(f"rets 要是 [B, L, {self.n_features}]，拿到 {tuple(rets.shape)}")
        x = self.revin(rets, "norm")
        patches = self._patchify(x)
        n = patches.shape[1]
        h = self.patch_proj(patches) + self.pos_emb[self.max_patches - n :].unsqueeze(0)
        use_ckpt = self._use_checkpoint()
        for layer in self.layers:
            if use_ckpt:
                h = checkpoint(layer, h, use_reentrant=False)
            else:
                h = layer(h)
        return self.final_norm(h[:, -1, :]).float()


def build_backbone(cfg: ModelConfig, gradient_checkpointing: bool = False) -> Backbone:
    """依 `cfg.backbone` 建主幹：`"kronos"` → `KronosBackbone`，`"patch"` → `PatchTransformerBackbone`。"""
    if cfg.backbone == "kronos":
        return KronosBackbone(cfg, gradient_checkpointing=gradient_checkpointing)
    if cfg.backbone == "patch":
        return PatchTransformerBackbone(cfg, gradient_checkpointing=gradient_checkpointing)
    raise ValueError(f"不認得的 backbone：{cfg.backbone!r}（要是 'kronos' 或 'patch'）")
