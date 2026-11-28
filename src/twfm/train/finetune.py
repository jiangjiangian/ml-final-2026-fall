"""分階段微調、linear probe、checkpoint 和預測。

流程（`Trainer.fit`）：照 `FinetuneConfig.stages` 一階一階做。
1. 每階開始前載入目前最好的權重（第一階沒有就用現在的）。
2. `configure_stage` 決定哪些參數可訓練（`head`、`last_k`、`lora`、`all`）。
3. AdamW 用 `model.param_groups`（分層學習率），linear warmup 加 cosine，CUDA 上用 AMP（A100 bf16、T4 fp16）。
4. 每個 epoch 結束在驗證集算每天 RankIC（Spearman）再平均。比目前最好的高就存 `best.pt`。
   連續 `early_stop_patience` 個 epoch 沒有超過目前最好的，就換下一階。
5. 全部做完載入 `best.pt`，所以之後的 `predict` 用的是最好的那組權重。

checkpoint（Kaggle 一次最長 12 小時，要能接續）：
- `last.pt`：模型、optimizer、GradScaler、scheduler、下一步要做的位置（第幾階、第幾個 epoch、
  這個 epoch 已經做了幾個 batch）、最好的分數、歷史紀錄、亂數狀態、LoRA 注入了哪些層。
  每 `checkpoint_every_steps` 步、每 `checkpoint_every_minutes` 分鐘、每個 epoch 結束都會存。
- `best.pt`：目前最好的模型權重和它的 LoRA 結構。
- 存檔先寫 `.tmp` 再 `os.replace`，存到一半被砍掉也不會壞掉舊檔。
- `fit(..., resume=True)` 從 `last.pt` 接續：先照存下來的結構注入 LoRA，再 `load_state_dict`。
  epoch 中途接續時，跳過已經做過的 batch（在 sampler 層跳，不會重新讀那些資料）。

AMP：只在 CUDA 開。compute capability ≥ 8（A100、L4）用 bf16、不用 GradScaler；T4 用 fp16 加 GradScaler（`FinetuneConfig.amp_dtype` 可以指定）。優先用 `torch.amp.autocast("cuda")`、`torch.amp.GradScaler("cuda")`，
舊版 torch 改用 `torch.cuda.amp`。CPU 一律 fp32，不開 autocast。損失一律在 fp32 算。
推論用 `torch.no_grad()`，不用 `inference_mode`（推論時建的快取之後訓練還要用）。
"""

from __future__ import annotations

import contextlib
import math
import os
import random
import time
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ContextManager

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from scipy.stats import spearmanr
from torch import nn
from torch.utils.data import DataLoader

from ..config import FinetuneConfig, StageConfig
from ..models.lora import LoRALinear, inject_lora, lora_parameters, merge_lora

if TYPE_CHECKING:
    from ..data.dataset import SampleIndex
    from ..models.model import TWFMModel

LossFn = Callable[[Mapping[str, torch.Tensor], Mapping[str, torch.Tensor]], tuple[torch.Tensor, dict[str, float]]]

CHECKPOINT_FORMAT: str = "twfm-trainer-v1"
LAST_NAME: str = "last.pt"
BEST_NAME: str = "best.pt"
# sampler 的 epoch 編號 = 階序號 × 這個數 + epoch，每一階每個 epoch 的順序都不同，接續時也一樣。
_EPOCH_ID_STRIDE: int = 10_000
# 連續這麼多個 batch 的損失都不是有限值就停下來（資料或模型壞了，不要白跑）。
_MAX_BAD_STREAK: int = 50
# 主幹裡永遠不訓練的模組名稱（`unfreeze_all` 不存在時的備用判斷）。
_NEVER_TRAIN_SEGMENTS: frozenset[str] = frozenset({"tokenizer", "head", "dep_layer"})


class TrainingInterrupted(RuntimeError):
    """超過 `max_seconds` 時丟出。丟出前已經存好 `last.pt`，下次用 `fit(..., resume=True)` 接續。"""


# ---------------------------------------------------------------------------
# 裝置、AMP、亂數
# ---------------------------------------------------------------------------


def resolve_device(device: torch.device | str | None) -> torch.device:
    """`"auto"` 或 None：有 CUDA 用 CUDA，否則 CPU。其他照字面。"""
    if device is None or str(device) == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device)


def resolve_amp_dtype(device: torch.device | str, pref: str = "auto") -> torch.dtype:
    """混合精度用的 dtype。`pref` 是 `auto`、`fp16`、`bf16`。

    auto：CUDA 裝置的 compute capability ≥ 8（A100、L4、H100）用 bf16，其他用 fp16。
    不用 `torch.cuda.is_bf16_supported()`：新版 torch 預設把模擬也算支援，T4 會回 True，但 T4 跑 bf16 很慢。
    """
    if pref == "bf16":
        return torch.bfloat16
    if pref == "fp16":
        return torch.float16
    dev = torch.device(device)
    if dev.type == "cuda" and torch.cuda.is_available():
        major, _minor = torch.cuda.get_device_capability(dev)
        if major >= 8:
            return torch.bfloat16
    return torch.float16


def _autocast(device: torch.device, enabled: bool, dtype: torch.dtype = torch.float16) -> ContextManager[Any]:
    """CUDA 上的 autocast（fp16 或 bf16）。CPU 或關掉時回傳空的 context（fp32）。"""
    if not enabled or device.type != "cuda":
        return contextlib.nullcontext()
    amp_mod = getattr(torch, "amp", None)
    if amp_mod is not None and hasattr(amp_mod, "autocast"):
        return amp_mod.autocast("cuda", dtype=dtype)
    return torch.cuda.amp.autocast(dtype=dtype)


def _make_scaler(enabled: bool) -> Any:
    """GradScaler。新版用 `torch.amp.GradScaler("cuda")`，舊版用 `torch.cuda.amp.GradScaler`。

    `enabled=False` 時 `scale`、`unscale_`、`step`、`update` 都是直通，CPU 也能用同一套程式。
    """
    amp_mod = getattr(torch, "amp", None)
    scaler_cls = getattr(amp_mod, "GradScaler", None) if amp_mod is not None else None
    if scaler_cls is not None:
        try:
            return scaler_cls("cuda", enabled=enabled)
        except TypeError:
            pass
    return torch.cuda.amp.GradScaler(enabled=enabled)


def set_seed(seed: int) -> None:
    """設定 Python、numpy、torch（含所有 CUDA 裝置）的亂數種子。"""
    s = int(seed)
    random.seed(s)
    np.random.seed(s % (2**32))
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


def _rng_state() -> dict[str, Any]:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def _set_rng_state(state: Mapping[str, Any] | None) -> None:
    if not state:
        return
    if state.get("python") is not None:
        random.setstate(state["python"])
    if state.get("numpy") is not None:
        np.random.set_state(state["numpy"])
    if state.get("torch") is not None:
        torch.set_rng_state(torch.as_tensor(state["torch"], dtype=torch.uint8).cpu())
    cuda_states = state.get("cuda")
    if cuda_states is not None and torch.cuda.is_available():
        try:
            torch.cuda.set_rng_state_all([torch.as_tensor(s, dtype=torch.uint8).cpu() for s in cuda_states])
        except (RuntimeError, IndexError, ValueError) as exc:
            warnings.warn(f"CUDA 亂數狀態還原失敗（裝置數不同？），沿用目前的：{exc}", stacklevel=2)


def _to_device(batch: Mapping[str, Any], device: torch.device) -> dict[str, Any]:
    non_blocking = device.type == "cuda"
    return {
        k: (v.to(device, non_blocking=non_blocking) if isinstance(v, torch.Tensor) else v) for k, v in batch.items()
    }


def _float_out(out: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    """模型輸出裡的浮點張量轉成 fp32（損失在 fp32 算）。"""
    return {k: (v.float() if isinstance(v, torch.Tensor) and v.is_floating_point() else v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# checkpoint 小工具
# ---------------------------------------------------------------------------


def _atomic_save(obj: Any, path: Path) -> None:
    """先寫 `<name>.tmp` 再換名，存到一半中斷也不會弄壞舊檔。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)


def _torch_load(path: Path) -> Any:
    """讀 checkpoint 到 CPU。torch ≥ 2.6 預設 `weights_only=True` 讀不了亂數狀態，所以明確關掉。

    `weights_only=False` 會 unpickle 任意物件，只用來讀這個 Trainer 自己存的檔，不要讀別人給的 checkpoint。
    """
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(path, map_location="cpu")


def lora_layout(model: nn.Module) -> dict[str, dict[str, float]]:
    """模型裡每個 `LoRALinear` 的完整名稱（相對於 `model`）對 `{"r", "alpha", "dropout"}`。

    存進 checkpoint，接續時照這份重新注入，結構才和存檔時一樣。
    """
    layout: dict[str, dict[str, float]] = {}
    for name, m in model.named_modules():
        if not isinstance(m, LoRALinear):
            continue
        r = int(getattr(m, "r", m.lora_A.shape[0]))
        alpha = float(getattr(m, "alpha", float(getattr(m, "scale", 1.0)) * r))
        drop = getattr(m, "lora_dropout", None)
        p = float(drop.p) if isinstance(drop, nn.Dropout) else 0.0
        layout[name] = {"r": r, "alpha": alpha, "dropout": p}
    return layout


def load_model_state(
    model: nn.Module,
    state: Mapping[str, torch.Tensor],
    lora_layers: Mapping[str, Mapping[str, float]] | None = None,
    default_alpha: float = 16.0,
    default_dropout: float = 0.0,
) -> None:
    """把 state_dict 載入模型，LoRA 結構不同時先調整再載入（`strict=True`）。

    - state 裡有 `<名字>.lora_A` 的層就是存檔時注入過 LoRA 的層。
      `r` 從 `lora_A` 的形狀讀，`alpha`、`dropout` 從 `lora_layers` 讀（沒有就用預設值）。
    - 模型現在的 LoRA 結構和 state 一樣：直接載入。
    - 不一樣：先 `merge_lora` 把模型現有的 LoRA 合併掉，再照 state 的結構逐層注入，然後載入。
      所以 LoRA 階段沒有贏時，載回沒有 LoRA 的最佳權重也不會對不上鍵名。
    """
    meta = dict(lora_layers or {})
    wanted: dict[str, dict[str, float]] = {}
    for key, value in state.items():
        if not key.endswith(".lora_A"):
            continue
        name = key[: -len(".lora_A")]
        info = meta.get(name, {})
        wanted[name] = {
            "r": int(value.shape[0]),
            "alpha": float(info.get("alpha", default_alpha)),
            "dropout": float(info.get("dropout", default_dropout)),
        }
    have = lora_layout(model)
    if wanted != have:
        if have:
            merge_lora(model)
        for name in sorted(wanted):
            info = wanted[name]
            leaf = name.rpartition(".")[2]
            done = inject_lora(
                model,
                [leaf],
                r=int(info["r"]),
                alpha=float(info["alpha"]),
                dropout=float(info["dropout"]),
                layer_filter=lambda n, target=name: n == target,
            )
            if done != [name]:
                raise RuntimeError(f"checkpoint 有 LoRA 層 {name!r}，但模型裡找不到同名的 nn.Linear 可以注入")
    # 直接傳原本的物件，保留 state_dict 的 `_metadata`（模組版本資訊）。
    model.load_state_dict(state, strict=True)


# ---------------------------------------------------------------------------
# 階段設定
# ---------------------------------------------------------------------------


def _never_train_ids(backbone: nn.Module) -> set[int]:
    fn = getattr(backbone, "never_train_params", None)
    if callable(fn):
        return {id(p) for p in fn()}
    return set()


def _unfreeze_all_fallback(backbone: nn.Module) -> None:
    """主幹沒有 `unfreeze_all` 時的備用：名稱裡有 tokenizer、head、dep_layer 這幾段的不打開。"""
    never = _never_train_ids(backbone)
    for name, p in backbone.named_parameters():
        if id(p) in never or any(part in _NEVER_TRAIN_SEGMENTS for part in name.split(".")):
            continue
        p.requires_grad_(True)


def _count_lora_targets(blocks: nn.Module, targets: Iterable[str]) -> int:
    """`blocks` 裡名字最後一段在 `targets` 的 `nn.Linear`（或已注入的 `LoRALinear`）有幾個。"""
    target_set = {str(t) for t in targets}
    count = 0
    for name, m in blocks.named_modules():
        if name and name.rpartition(".")[2] in target_set and isinstance(m, (nn.Linear, LoRALinear)):
            count += 1
    return count


def configure_stage(model: TWFMModel, stage: StageConfig, ft: FinetuneConfig) -> list[str]:
    """設定這一階哪些參數可訓練，回傳可訓練參數的完整名稱。

    先 `model.backbone.freeze_all()`，head 一律打開，再依 `stage.trainable`：
    - `head`：只訓練 head。
    - `last_k`：再 `unfreeze_last(stage.last_k)`。
    - `lora`：對 `model.backbone.blocks` 注入 LoRA（`ft.lora_targets`、`lora_r`、`lora_alpha`、`lora_dropout`），
      只訓練 LoRA 參數和 head。已經注入過的層不重複注入，只把它的 LoRA 參數重新打開。
      一個目標層都找不到時丟 `ValueError`（不默默變成只訓練 head）。
    - `all`：主幹除了 Kronos 的 tokenizer、`head`、`dep_layer` 全部打開（用 `backbone.unfreeze_all()`）。
    最後 `model.train(model.training)`，讓主幹依新的可訓練狀態重新決定 train/eval。
    """
    bb = model.backbone
    bb.freeze_all()
    kind = stage.trainable
    if kind == "head":
        pass
    elif kind == "last_k":
        bb.unfreeze_last(int(stage.last_k))
    elif kind == "lora":
        if _count_lora_targets(bb.blocks, ft.lora_targets) == 0:
            raise ValueError(
                f"階段 {stage.name!r} 要注入 LoRA，但主幹的 blocks 裡沒有名字在 {list(ft.lora_targets)} 的 nn.Linear"
            )
        inject_lora(
            bb.blocks,
            ft.lora_targets,
            r=int(ft.lora_r),
            alpha=float(ft.lora_alpha),
            dropout=float(ft.lora_dropout),
        )
        if not lora_parameters(bb.blocks):
            raise ValueError(f"階段 {stage.name!r} 注入 LoRA 後沒有任何 LoRA 參數")
    elif kind == "all":
        unfreeze_all = getattr(bb, "unfreeze_all", None)
        if callable(unfreeze_all):
            unfreeze_all()
        else:
            _unfreeze_all_fallback(bb)
    else:
        raise ValueError(f"不認得的 trainable {kind!r}")
    for p in model.head.parameters():
        p.requires_grad_(True)
    model.train(model.training)
    return [name for name, p in model.named_parameters() if p.requires_grad]


def _backbone_trainable(model: TWFMModel) -> bool:
    never = _never_train_ids(model.backbone)
    return any(p.requires_grad and id(p) not in never for p in model.backbone.parameters())


# ---------------------------------------------------------------------------
# RankIC
# ---------------------------------------------------------------------------


def _spearman(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> float:
    res = spearmanr(a, b)
    rho = getattr(res, "statistic", None)
    if rho is None:
        rho = getattr(res, "correlation", None)
    if rho is None:
        rho = res[0]
    return float(rho)


def mean_daily_rank_ic(
    scores: npt.ArrayLike,
    labels: npt.ArrayLike,
    day_ids: npt.ArrayLike,
    min_count: int = 3,
) -> float:
    """每天分數和報酬的 Spearman 相關（`scipy.stats.spearmanr`），再對天平均。

    - 分數或報酬不是有限值的列先丟掉。
    - 一天少於 `min_count` 檔、或分數或報酬當天全部一樣（相關沒有定義）的天不算。
    - 沒有任何一天可以算時回傳 NaN。
    """
    s = np.asarray(scores, dtype=np.float64).reshape(-1)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    d = np.asarray(day_ids).reshape(-1)
    if not (len(s) == len(y) == len(d)):
        raise ValueError(f"scores {len(s)}、labels {len(y)}、day_ids {len(d)} 長度不同")
    ok = np.isfinite(s) & np.isfinite(y)
    s, y, d = s[ok], y[ok], d[ok]
    if len(s) == 0:
        return float("nan")
    order = np.argsort(d, kind="stable")
    d_sorted = d[order]
    cuts = np.flatnonzero(d_sorted[1:] != d_sorted[:-1]) + 1
    ics: list[float] = []
    for rows in np.split(order, cuts):
        if len(rows) < int(min_count):
            continue
        a = s[rows]
        b = y[rows]
        if np.ptp(a) == 0.0 or np.ptp(b) == 0.0:
            continue
        rho = _spearman(a, b)
        if math.isfinite(rho):
            ics.append(rho)
    return float(np.mean(ics)) if ics else float("nan")


# ---------------------------------------------------------------------------
# embedding 快取和 linear probe
# ---------------------------------------------------------------------------


def extract_embeddings(
    model: TWFMModel,
    loader: DataLoader,
    device: torch.device | str,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64]]:
    """主幹凍結時一次算好每個樣本的表示，給 linear probe 和 embedding 快取用。

    回傳 `(repr [N, d_model] float32, index [N] int64)`，按 `index`（樣本序號）由小到大排。
    loader 涵蓋全部樣本時 `index` 就是 `0..N−1`，`repr[k]` 對應 `samples` 的第 k 列。
    在 `torch.no_grad()` 裡跑，CUDA 上用 autocast（A100 bf16、T4 fp16），跑完恢復模型原本的 train/eval。
    結果陣列一開始就按 dataset 大小配置，不會因為串接多佔一倍記憶體。
    """
    dev = resolve_device(device)
    model.to(dev)
    use_amp = dev.type == "cuda"
    amp_dtype = resolve_amp_dtype(dev)
    n_total = len(loader.dataset)  # type: ignore[arg-type]
    reps: npt.NDArray[np.float32] | None = None
    filled = np.zeros(n_total, dtype=bool)
    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            for batch in loader:
                idx = batch["index"].reshape(-1).cpu().numpy().astype(np.int64)
                b = _to_device(batch, dev)
                with _autocast(dev, use_amp, amp_dtype):
                    rep = model.backbone.encode(b)
                rep_np = rep.float().cpu().numpy()
                if reps is None:
                    reps = np.zeros((n_total, rep_np.shape[1]), dtype=np.float32)
                reps[idx] = rep_np
                filled[idx] = True
    finally:
        model.train(was_training)
    if reps is None:
        d = int(getattr(model.backbone, "d_model", 0))
        return np.zeros((0, d), dtype=np.float32), np.zeros(0, dtype=np.int64)
    index = np.flatnonzero(filled).astype(np.int64)
    if len(index) == n_total:
        return reps, index
    return reps[index], index


@dataclass
class RidgeProbe:
    """閉式解的 ridge 線性探針。`predict(X) = X @ coef + intercept`（原始特徵尺度）。

    `alpha` 是選中的懲罰；`val_rank_ic` 是每個候選 alpha 在驗證期的每天 RankIC 平均（沒給驗證資料時是空的）。
    """

    coef: npt.NDArray[np.float64]
    intercept: float
    alpha: float
    val_rank_ic: dict[float, float] = field(default_factory=dict)
    n_train: int = 0

    def predict(self, X: npt.ArrayLike, chunk_size: int = 65536) -> npt.NDArray[np.float64]:
        return _linear_predict(np.asarray(X), self.coef, self.intercept, chunk_size)


def _linear_predict(
    X: np.ndarray,
    coef: npt.NDArray[np.float64],
    intercept: float,
    chunk_size: int,
) -> npt.NDArray[np.float64]:
    if X.ndim != 2 or X.shape[1] != len(coef):
        raise ValueError(f"X 要是 [N, {len(coef)}]，拿到 {list(X.shape)}")
    out = np.empty(X.shape[0], dtype=np.float64)
    step = max(1, int(chunk_size))
    for start in range(0, X.shape[0], step):
        end = min(start + step, X.shape[0])
        out[start:end] = np.asarray(X[start:end], dtype=np.float64) @ coef + intercept
    return out


def _default_alpha(alphas: Sequence[float]) -> float:
    """沒有驗證資料時的 alpha：取對數尺度上最接近 1 的那個。"""
    return float(min(alphas, key=lambda a: abs(math.log(float(a)))))


def fit_ridge_probe(
    X: npt.ArrayLike,
    y: npt.ArrayLike,
    alphas: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    X_val: npt.ArrayLike | None = None,
    y_val: npt.ArrayLike | None = None,
    day_val: npt.ArrayLike | None = None,
    chunk_size: int = 65536,
) -> RidgeProbe:
    """Ridge 回歸的閉式解，用驗證期每天 RankIC 平均選 alpha。

    - 特徵先用訓練資料的平均和標準差標準化（只用訓練資料 fit），目標減平均。
      目標函數是 `(1/n) Σ (y − ŷ)² + alpha · ‖w‖²`（w 在標準化後的尺度），
      所以 alpha 和樣本數無關：0.1 接近 OLS，100 接近只看單變量相關。
    - `XᵀX` 分塊用 float64 累加（兩趟：先算平均再算離差），不會一次複製整個 X。
      特徵分解只做一次，每個 alpha 共用。
    - 標準差是 0 的特徵係數設 0。X 或 y 有非有限值的列不進訓練。
    - 有 `X_val` 時要一起給 `y_val`（通常是 `label_r`）和 `day_val`（天編號），
      選每天 RankIC 平均最高的 alpha（同分取先出現的）；沒有驗證資料時取對數尺度上最接近 1 的 alpha。
    """
    alpha_list = [float(a) for a in alphas]
    if not alpha_list:
        raise ValueError("alphas 不能是空的")
    if any(not (a > 0.0) for a in alpha_list):
        raise ValueError("alphas 每個都要大於 0")
    X_arr = np.asarray(X)
    if X_arr.ndim != 2:
        raise ValueError(f"X 要是二維 [N, d]，拿到 {X_arr.ndim} 維")
    y_arr = np.asarray(y, dtype=np.float64).reshape(-1)
    n, d = X_arr.shape
    if len(y_arr) != n:
        raise ValueError(f"y 有 {len(y_arr)} 個，X 有 {n} 列")
    step = max(1, int(chunk_size))

    # 第一趟：可用的列、平均。
    mask = np.isfinite(y_arr)
    sum_x = np.zeros(d, dtype=np.float64)
    sum_y = 0.0
    for start in range(0, n, step):
        end = min(start + step, n)
        xb = np.asarray(X_arr[start:end], dtype=np.float64)
        ok = mask[start:end] & np.isfinite(xb).all(axis=1)
        mask[start:end] = ok
        sum_x += xb[ok].sum(axis=0)
        sum_y += float(y_arr[start:end][ok].sum())
    n_ok = int(mask.sum())
    if n_ok < 2:
        raise ValueError(f"可用的訓練列只有 {n_ok} 列，至少要 2 列")
    mean_x = sum_x / n_ok
    mean_y = sum_y / n_ok

    # 第二趟：離差的 XᵀX、Xᵀy。
    sxx = np.zeros((d, d), dtype=np.float64)
    sxy = np.zeros(d, dtype=np.float64)
    for start in range(0, n, step):
        end = min(start + step, n)
        ok = mask[start:end]
        if not ok.any():
            continue
        xb = np.asarray(X_arr[start:end], dtype=np.float64)[ok] - mean_x
        yb = y_arr[start:end][ok] - mean_y
        sxx += xb.T @ xb
        sxy += xb.T @ yb
    cov = sxx / n_ok
    cxy = sxy / n_ok
    std = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    const = std < 1e-12
    std_safe = np.where(const, 1.0, std)
    corr = cov / np.outer(std_safe, std_safe)
    corr[const, :] = 0.0
    corr[:, const] = 0.0
    b = cxy / std_safe
    b[const] = 0.0
    eigval, eigvec = np.linalg.eigh(corr)
    eigval = np.clip(eigval, 0.0, None)
    qb = eigvec.T @ b

    def solve(alpha: float) -> tuple[npt.NDArray[np.float64], float]:
        w_std = eigvec @ (qb / (eigval + alpha))
        coef = w_std / std_safe
        coef[const] = 0.0
        return coef, float(mean_y - mean_x @ coef)

    val_scores: dict[float, float] = {}
    if X_val is not None:
        if y_val is None or day_val is None:
            raise ValueError("給了 X_val 也要給 y_val 和 day_val")
        X_val_arr = np.asarray(X_val)
        best_alpha = alpha_list[0]
        best_score = -math.inf
        for a in alpha_list:
            coef, intercept = solve(a)
            pred = _linear_predict(X_val_arr, coef, intercept, step)
            score = mean_daily_rank_ic(pred, y_val, day_val)
            val_scores[a] = score
            if math.isfinite(score) and score > best_score:
                best_alpha, best_score = a, score
        if not math.isfinite(best_score):
            warnings.warn("驗證期每個 alpha 的 RankIC 都算不出來，改用預設 alpha", stacklevel=2)
            best_alpha = _default_alpha(alpha_list)
    else:
        best_alpha = _default_alpha(alpha_list)
    coef, intercept = solve(best_alpha)
    return RidgeProbe(coef=coef, intercept=intercept, alpha=best_alpha, val_rank_ic=val_scores, n_train=n_ok)


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


def _lr_factor(step: int, warmup: int, total: int) -> float:
    """學習率倍數：前 `warmup` 步線性從 1/warmup 升到 1，之後 cosine 降到 0。"""
    if warmup > 0 and step < warmup:
        return float(step + 1) / float(warmup)
    if total <= warmup:
        return 1.0
    progress = min(1.0, float(step - warmup) / float(max(1, total - warmup)))
    return 0.5 * (1.0 + math.cos(math.pi * progress))


@dataclass
class _EpochAcc:
    """一個 epoch 的累計，epoch 中途存檔時一起存。"""

    loss_sum: float = 0.0
    loss_count: int = 0
    parts_sum: dict[str, float] = field(default_factory=dict)
    batches: int = 0
    skipped: int = 0
    seconds_before: float = 0.0
    t0: float = field(default_factory=time.time)

    def add(self, loss: float, parts: Mapping[str, float]) -> None:
        self.loss_sum += float(loss)
        self.loss_count += 1
        for k, v in parts.items():
            self.parts_sum[k] = self.parts_sum.get(k, 0.0) + float(v)

    def seconds(self) -> float:
        return self.seconds_before + (time.time() - self.t0)

    def mean_loss(self) -> float:
        return self.loss_sum / self.loss_count if self.loss_count else float("nan")

    def mean_parts(self) -> dict[str, float]:
        if not self.loss_count:
            return {}
        return {k: v / self.loss_count for k, v in self.parts_sum.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "loss_sum": self.loss_sum,
            "loss_count": self.loss_count,
            "parts_sum": dict(self.parts_sum),
            "batches": self.batches,
            "skipped": self.skipped,
            "seconds_before": self.seconds(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> _EpochAcc:
        if not d:
            return cls()
        return cls(
            loss_sum=float(d.get("loss_sum", 0.0)),
            loss_count=int(d.get("loss_count", 0)),
            parts_sum={str(k): float(v) for k, v in dict(d.get("parts_sum", {})).items()},
            batches=int(d.get("batches", 0)),
            skipped=int(d.get("skipped", 0)),
            seconds_before=float(d.get("seconds_before", 0.0)),
        )


@dataclass
class _StageRun:
    """一階訓練中的狀態。"""

    index: int
    stage: StageConfig
    optimizer: torch.optim.Optimizer
    scheduler: torch.optim.lr_scheduler.LambdaLR
    scaler: Any
    params: list[nn.Parameter]
    total_steps: int
    warmup_steps: int
    backbone_trainable: bool
    step: int = 0


class _SkipBatches:
    """batch sampler 的前 `skip` 個 batch 跳過（epoch 中途接續用）。先 `set_epoch` 再建。"""

    def __init__(self, batches: list[list[int]]) -> None:
        self._batches = batches

    def __iter__(self) -> Any:
        return iter(self._batches)

    def __len__(self) -> int:
        return len(self._batches)


class Trainer:
    """分階段微調。用法：`Trainer(model, loss_fn, ft, device).fit(train_loader, val_loader, val_samples)`。

    參數：
    - `loss_fn(out, batch) -> (loss, parts)`，通常是 `CompositeLoss`。
    - `device`：`"auto"`、`"cuda"`、`"cpu"` 或 `torch.device`。模型會被搬到這個裝置。
    - `checkpoint_dir`：沒給就用 `ft.checkpoint_dir`。
    - `checkpoint_every_steps`、`checkpoint_every_minutes`：epoch 中途多久存一次 `last.pt`（任一個到了就存，
      None 或 0 是不用這個條件）。每個 epoch 結束一定會存。
    - `max_seconds`：從 `fit` 開始算，超過就存 `last.pt` 再丟 `TrainingInterrupted`（給 Kaggle 12 小時上限留餘裕）。
    - `quantiles`：`predict` 的分位數欄名用，沒給就讀 `model.quantiles`，再沒有就讀 `loss_fn.quantiles`。

    `train_loader` 要用 `DayBatchSampler`（`make_loader`），驗證和預測的 loader 要 `shuffle=False`、
    `max_stocks_per_day=None`，才不會漏樣本。
    """

    def __init__(
        self,
        model: TWFMModel,
        loss_fn: LossFn,
        ft: FinetuneConfig,
        device: torch.device | str,
        checkpoint_dir: str | os.PathLike[str] | None = None,
        checkpoint_every_steps: int | None = 500,
        checkpoint_every_minutes: float | None = 15.0,
        max_seconds: float | None = None,
        log_every: int = 50,
        verbose: bool = True,
        quantiles: Sequence[float] | None = None,
    ) -> None:
        self.device = resolve_device(device)
        self.model = model.to(self.device)
        self.loss_fn = loss_fn
        if isinstance(loss_fn, nn.Module):
            loss_fn.to(self.device)
        self.ft = ft
        self.use_amp = bool(ft.amp) and self.device.type == "cuda"
        self.amp_dtype: torch.dtype = resolve_amp_dtype(self.device, ft.amp_dtype)
        # bf16 的指數範圍和 fp32 一樣，不會下溢，不需要 GradScaler。
        self.use_scaler = self.use_amp and self.amp_dtype == torch.float16
        self.checkpoint_dir = Path(checkpoint_dir if checkpoint_dir is not None else ft.checkpoint_dir)
        self.last_path = self.checkpoint_dir / LAST_NAME
        self.best_path = self.checkpoint_dir / BEST_NAME
        self.checkpoint_every_steps = int(checkpoint_every_steps) if checkpoint_every_steps else 0
        self.checkpoint_every_minutes = float(checkpoint_every_minutes) if checkpoint_every_minutes else 0.0
        self.max_seconds = None if max_seconds is None else float(max_seconds)
        self.log_every = int(log_every)
        self.verbose = bool(verbose)
        if quantiles is None:
            quantiles = getattr(model, "quantiles", None) or getattr(loss_fn, "quantiles", None) or ()
        self.quantiles: tuple[float, ...] = tuple(float(q) for q in quantiles)

        self.history: list[dict[str, Any]] = []
        self.best_score: float = -math.inf
        self.has_best: bool = False
        self.best_stage: int = -1
        self.best_epoch: int = -1
        self.global_step: int = 0
        self._bad_epochs: int = 0
        self._bad_streak: int = 0
        self._t_start: float = time.time()
        self._last_ckpt_time: float = time.time()
        self._n_train_batches: int = 0

    # ---- 小工具 -------------------------------------------------------------

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[twfm.finetune] {msg}", flush=True)

    def _autocast(self) -> ContextManager[Any]:
        return _autocast(self.device, self.use_amp, self.amp_dtype)

    def _stage_names(self) -> list[str]:
        return [s.name for s in self.ft.stages]

    def _quantile_names(self, q_count: int) -> list[str]:
        """分位數欄名：`q_0.1`、`q_0.5`、`q_0.9`（`f"q_{q:g}"`）；不知道分位點時是 `q_0`、`q_1`…。"""
        if len(self.quantiles) == q_count:
            return [f"q_{q:g}" for q in self.quantiles]
        return [f"q_{j}" for j in range(q_count)]

    # ---- checkpoint -------------------------------------------------------

    def _save_last(
        self,
        next_stage: int,
        next_epoch: int,
        next_batch: int,
        run: _StageRun | None,
        acc: _EpochAcc | None,
    ) -> None:
        obj: dict[str, Any] = {
            "format": CHECKPOINT_FORMAT,
            "stage_names": self._stage_names(),
            "next_stage": int(next_stage),
            "next_epoch": int(next_epoch),
            "next_batch": int(next_batch),
            "n_train_batches": int(self._n_train_batches),
            "step_in_stage": int(run.step) if run is not None else 0,
            "global_step": int(self.global_step),
            "model": self.model.state_dict(),
            "lora_layers": lora_layout(self.model),
            "lora_injected": bool(lora_layout(self.model)),
            "optimizer": run.optimizer.state_dict() if run is not None else None,
            "scheduler": run.scheduler.state_dict() if run is not None else None,
            "scaler": run.scaler.state_dict() if run is not None else None,
            "best_score": float(self.best_score),
            "has_best": bool(self.has_best),
            "best_stage": int(self.best_stage),
            "best_epoch": int(self.best_epoch),
            "bad_epochs": int(self._bad_epochs),
            "history": [dict(h) for h in self.history],
            "epoch_acc": acc.to_dict() if acc is not None else None,
            "rng": _rng_state(),
            "saved_at": time.time(),
        }
        _atomic_save(obj, self.last_path)
        self._last_ckpt_time = time.time()

    def _save_best(self, stage_idx: int, epoch: int, val: float) -> None:
        obj = {
            "format": CHECKPOINT_FORMAT,
            "model": self.model.state_dict(),
            "lora_layers": lora_layout(self.model),
            "stage_idx": int(stage_idx),
            "stage_name": self.ft.stages[stage_idx].name,
            "epoch": int(epoch),
            "val_rank_ic": float(val),
        }
        _atomic_save(obj, self.best_path)

    def _load_state(self, ckpt: Mapping[str, Any]) -> None:
        load_model_state(
            self.model,
            ckpt["model"],
            ckpt.get("lora_layers"),
            default_alpha=float(self.ft.lora_alpha),
            default_dropout=float(self.ft.lora_dropout),
        )

    def load_best(self) -> None:
        """載入 `best.pt` 的權重（LoRA 結構不同時會先調整）。"""
        if not self.best_path.exists():
            raise FileNotFoundError(f"找不到 {self.best_path}")
        self._load_state(_torch_load(self.best_path))

    def _read_last(self) -> dict[str, Any] | None:
        if not self.last_path.exists():
            self._log(f"resume=True 但沒有 {self.last_path}，從頭開始")
            return None
        ckpt = _torch_load(self.last_path)
        if not isinstance(ckpt, dict) or ckpt.get("format") != CHECKPOINT_FORMAT:
            raise ValueError(f"{self.last_path} 不是這個版本的 Trainer checkpoint")
        if list(ckpt.get("stage_names", [])) != self._stage_names():
            raise ValueError(
                f"checkpoint 的階段 {ckpt.get('stage_names')} 和現在的設定 {self._stage_names()} 不同，"
                "不能接續（改了 stages 就用 resume=False 重新開始）"
            )
        return ckpt

    # ---- 單階 -------------------------------------------------------------

    def _build_stage(self, stage_idx: int, stage: StageConfig, n_batches: int) -> _StageRun:
        """建這一階的 AdamW、學習率排程、GradScaler。要在 `configure_stage` 之後呼叫。"""
        raw_groups = self.model.param_groups(stage, float(self.ft.weight_decay))
        groups: list[dict[str, Any]] = []
        for g in raw_groups:
            params = [p for p in g["params"] if p.requires_grad]
            if not params:
                continue
            new_g = dict(g)
            new_g["params"] = params
            new_g.setdefault("lr", float(stage.lr_head))
            new_g.setdefault("weight_decay", float(self.ft.weight_decay))
            groups.append(new_g)
        covered = {id(p) for g in groups for p in g["params"]}
        never = _never_train_ids(self.model.backbone)
        missing = [p for p in self.model.parameters() if p.requires_grad and id(p) not in covered and id(p) not in never]
        if missing:
            warnings.warn(
                f"有 {len(missing)} 個可訓練參數不在 param_groups 裡，用 lr_head 補一組", stacklevel=2
            )
            groups.append(
                {
                    "name": "uncovered",
                    "params": missing,
                    "lr": float(stage.lr_head),
                    "weight_decay": float(self.ft.weight_decay),
                }
            )
        if not groups:
            raise ValueError(f"階段 {stage.name!r} 沒有任何可訓練參數")
        optimizer = torch.optim.AdamW(groups, lr=float(stage.lr_head), weight_decay=float(self.ft.weight_decay))
        steps_per_epoch = math.ceil(n_batches / int(self.ft.grad_accum))
        total = int(stage.epochs) * steps_per_epoch
        if stage.max_steps is not None:
            total = min(total, int(stage.max_steps))
        total = max(1, total)
        warmup = min(int(stage.warmup_steps), total // 2)
        scheduler = torch.optim.lr_scheduler.LambdaLR(
            optimizer, lr_lambda=lambda s, w=warmup, t=total: _lr_factor(int(s), w, t)
        )
        params = [p for g in groups for p in g["params"]]
        return _StageRun(
            index=stage_idx,
            stage=stage,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=_make_scaler(self.use_scaler),
            params=params,
            total_steps=total,
            warmup_steps=warmup,
            backbone_trainable=_backbone_trainable(self.model),
        )

    def _restore_run(self, run: _StageRun, ckpt: Mapping[str, Any]) -> None:
        try:
            run.optimizer.load_state_dict(ckpt["optimizer"])
        except ValueError as exc:
            raise ValueError(f"optimizer 狀態對不上現在的參數分組（模型或設定改過？）：{exc}") from exc
        if ckpt.get("scheduler") is not None:
            run.scheduler.load_state_dict(ckpt["scheduler"])
        scaler_state = ckpt.get("scaler")
        if scaler_state and run.scaler.is_enabled():
            run.scaler.load_state_dict(scaler_state)
        run.step = int(ckpt.get("step_in_stage", 0))

    def _epoch_batches(self, loader: DataLoader, epoch_id: int, skip: int) -> Iterable[Any]:
        """設定 sampler 的 epoch，需要時跳過前 `skip` 個 batch（在 sampler 層跳，不讀那些資料）。"""
        sampler = getattr(loader, "batch_sampler", None)
        if sampler is not None and hasattr(sampler, "set_epoch"):
            sampler.set_epoch(int(epoch_id))
        if skip <= 0:
            return loader
        if sampler is None:
            raise RuntimeError("loader 沒有 batch_sampler，沒辦法從 epoch 中途接續")
        remaining = [list(b) for b in sampler][int(skip) :]
        kwargs: dict[str, Any] = {
            "batch_sampler": _SkipBatches(remaining),
            "num_workers": loader.num_workers,
            "collate_fn": loader.collate_fn,
            "pin_memory": loader.pin_memory,
            "worker_init_fn": loader.worker_init_fn,
        }
        if loader.num_workers > 0:
            kwargs["prefetch_factor"] = loader.prefetch_factor
            kwargs["timeout"] = loader.timeout
        return DataLoader(loader.dataset, **kwargs)

    def _forward_train(self, batch: Mapping[str, torch.Tensor], backbone_trainable: bool) -> dict[str, torch.Tensor]:
        """主幹完全凍結時，主幹在 `no_grad` 裡跑（不存中間值，省記憶體），只有 head 建計算圖。"""
        if not backbone_trainable and hasattr(self.model, "forward_from_repr"):
            with torch.no_grad():
                rep = self.model.backbone(batch)
            return self.model.forward_from_repr(rep, batch.get("stock_cov"), batch.get("market_cov"))
        return self.model(batch)

    def _optimizer_step(self, run: _StageRun) -> None:
        scaler = run.scaler
        scaler.unscale_(run.optimizer)
        skip_step = False
        if self.ft.grad_clip and self.ft.grad_clip > 0:
            norm = torch.nn.utils.clip_grad_norm_(run.params, float(self.ft.grad_clip))
            # 有 GradScaler 時它自己會跳過 inf/NaN 的步；fp32（CPU）沒有，要自己跳。
            if not scaler.is_enabled() and not bool(torch.isfinite(norm)):
                skip_step = True
        if skip_step:
            warnings.warn("梯度不是有限值，跳過這一步", stacklevel=2)
        else:
            scaler.step(run.optimizer)
            scaler.update()
        run.scheduler.step()
        run.optimizer.zero_grad(set_to_none=True)
        run.step += 1
        self.global_step += 1

    def _after_step(self, run: _StageRun, epoch: int, acc: _EpochAcc) -> None:
        """每步之後：記錄、定期存檔、時間上限。"""
        if self.log_every > 0 and run.step % self.log_every == 0:
            lr = max(float(g["lr"]) for g in run.optimizer.param_groups)
            self._log(
                f"{run.stage.name} epoch {epoch} step {run.step}/{run.total_steps} "
                f"loss {acc.mean_loss():.5f} lr {lr:.2e} batches {acc.batches}"
            )
        now = time.time()
        due = bool(self.checkpoint_every_steps) and run.step % self.checkpoint_every_steps == 0
        if self.checkpoint_every_minutes and now - self._last_ckpt_time >= self.checkpoint_every_minutes * 60.0:
            due = True
        over = self.max_seconds is not None and now - self._t_start >= self.max_seconds
        if due or over:
            self._save_last(run.index, epoch, acc.batches, run, acc)
        if over:
            raise TrainingInterrupted(
                f"超過 max_seconds={self.max_seconds:.0f} 秒，已存 {self.last_path}，用 fit(..., resume=True) 接續"
            )

    def _run_epoch(self, run: _StageRun, loader: DataLoader, epoch: int, skip: int, acc: _EpochAcc) -> None:
        """訓練一個 epoch（或從中途接續到結束）。到 `total_steps` 就提早結束。"""
        self.model.train()
        if run.step >= run.total_steps:
            return
        accum = int(self.ft.grad_accum)
        batches = self._epoch_batches(loader, run.index * _EPOCH_ID_STRIDE + epoch, skip)
        run.optimizer.zero_grad(set_to_none=True)
        micro = 0
        for batch in batches:
            b = _to_device(batch, self.device)
            with self._autocast():
                out = self._forward_train(b, run.backbone_trainable)
            loss, parts = self.loss_fn(_float_out(out), b)
            acc.batches += 1
            if not bool(torch.isfinite(loss.detach())):
                acc.skipped += 1
                self._bad_streak += 1
                if self._bad_streak <= 3:
                    warnings.warn(f"第 {acc.batches} 個 batch 的損失不是有限值，跳過", stacklevel=2)
                if self._bad_streak >= _MAX_BAD_STREAK:
                    raise RuntimeError(f"連續 {self._bad_streak} 個 batch 的損失不是有限值，停止訓練")
                continue
            self._bad_streak = 0
            run.scaler.scale(loss / accum).backward()
            micro += 1
            acc.add(float(loss.detach()), parts)
            if micro == accum:
                self._optimizer_step(run)
                micro = 0
                self._after_step(run, epoch, acc)
                if run.step >= run.total_steps:
                    return
        if micro > 0:
            self._optimizer_step(run)
            self._after_step(run, epoch, acc)

    # ---- 推論 -------------------------------------------------------------

    def _score_loader(
        self, loader: DataLoader
    ) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float32], npt.NDArray[np.float32] | None]:
        """跑過 loader，回傳 `(index, score, quantiles)`，照 loader 的順序。"""
        self.model.eval()
        idx_parts: list[np.ndarray] = []
        score_parts: list[np.ndarray] = []
        q_parts: list[np.ndarray] = []
        with torch.no_grad():
            for batch in loader:
                idx_parts.append(batch["index"].reshape(-1).cpu().numpy().astype(np.int64))
                b = _to_device(batch, self.device)
                with self._autocast():
                    out = self.model(b)
                score_parts.append(out["score"].float().reshape(-1).cpu().numpy())
                if out.get("quantiles") is not None:
                    q_parts.append(out["quantiles"].float().cpu().numpy())
        if not idx_parts:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32), None
        idx = np.concatenate(idx_parts)
        score = np.concatenate(score_parts).astype(np.float32)
        quant = np.concatenate(q_parts).astype(np.float32) if q_parts else None
        if len(score) != len(idx):
            raise RuntimeError(f"score 有 {len(score)} 個，index 有 {len(idx)} 個")
        return idx, score, quant

    @staticmethod
    def _check_index(idx: np.ndarray, samples: SampleIndex) -> None:
        if len(idx) and (int(idx.min()) < 0 or int(idx.max()) >= len(samples)):
            raise ValueError(f"loader 的 index 超出 samples 的範圍（{len(samples)} 列），loader 和 samples 不是同一組？")

    def evaluate(self, loader: DataLoader, samples: SampleIndex) -> float:
        """驗證集的每天 RankIC 平均（分數對 `label_r` 的 Spearman）。"""
        idx, score, _ = self._score_loader(loader)
        if len(idx) == 0:
            return float("nan")
        self._check_index(idx, samples)
        return mean_daily_rank_ic(score, samples.label_r[idx], samples.day_ids[idx])

    def predict(self, loader: DataLoader, samples: SampleIndex) -> pd.DataFrame:
        """預測。回傳欄 `date, stock_id, score`，有分位數頭時再加 `q_0.1` 這類欄（`f"q_{q:g}"`）。

        按樣本序號排序（`samples` 本身按 `(date, stock_id)` 排，所以結果也是）。
        `loader.dataset` 要是用同一個 `samples` 建的。
        """
        ds_len = len(loader.dataset)  # type: ignore[arg-type]
        if ds_len != len(samples):
            raise ValueError(f"loader 的 dataset 有 {ds_len} 列，samples 有 {len(samples)} 列，不是同一組")
        idx, score, quant = self._score_loader(loader)
        self._check_index(idx, samples)
        order = np.argsort(idx, kind="stable")
        idx = idx[order]
        df = pd.DataFrame(
            {
                "date": samples.dates[idx],
                "stock_id": samples.stock_ids[idx],
                "score": score[order],
            }
        )
        if quant is not None:
            quant = quant[order]
            for j, name in enumerate(self._quantile_names(quant.shape[1])):
                df[name] = quant[:, j]
        return df

    # ---- 主流程 -----------------------------------------------------------

    def _update_best(self, val: float, stage_idx: int, epoch: int, has_val: bool) -> bool:
        """這個 epoch 是不是新的最好。是就存 `best.pt`。

        沒有驗證集時每個 epoch 都算最好（最後一個就是 best）。第一個 epoch 一定存，
        就算 RankIC 算不出來（NaN），下一階才有東西可以載入。
        """
        if not has_val or not self.has_best:
            improved = True
        else:
            improved = math.isfinite(val) and val > self.best_score
        if improved:
            self._save_best(stage_idx, epoch, val)
            self.has_best = True
            self.best_score = val if math.isfinite(val) else -math.inf
            self.best_stage = stage_idx
            self.best_epoch = epoch
        return improved

    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader | None,
        val_samples: SampleIndex | None,
        resume: bool = False,
        stop_after: tuple[int, int] | None = None,
    ) -> list[dict[str, Any]]:
        """照 `ft.stages` 依序訓練，回傳每個 epoch 的紀錄。

        每筆紀錄有 `stage, stage_idx, trainable, epoch, train_loss, val_rank_ic, seconds`，
        另有 `val_seconds, steps, global_step, batches, skipped_batches, is_best, lr_max` 和 `loss_<名稱>`（各項損失的平均）。
        `resume=True` 時從 `last.pt` 接續；沒有 `last.pt` 就從頭開始。
        `stop_after=(階段, epoch)`：跑完那一階的那個 epoch 就整個停下，後面的階段不跑。
        學習率排程照那一階設定的 epoch 數排，所以停下時的權重和完整跑時同一個位置的一樣
        （最後重訓用：照驗證期挑到的點停）。
        做完會載入 `best.pt`，模型就是驗證期最好的那組權重。
        """
        stages = list(self.ft.stages)
        n_batches = len(train_loader)
        if n_batches == 0:
            raise ValueError("train_loader 是空的")
        if val_loader is not None and val_samples is None:
            raise ValueError("給了 val_loader 也要給 val_samples")
        stop_si, stop_ep = (-1, -1) if stop_after is None else (int(stop_after[0]), int(stop_after[1]))
        if stop_after is not None and not (0 <= stop_si < len(stages) and 0 <= stop_ep < int(stages[stop_si].epochs)):
            raise ValueError(f"stop_after {stop_after} 不在階段設定的範圍裡")
        self._n_train_batches = n_batches
        for st in stages:
            if st.trainable == "lora" and _count_lora_targets(self.model.backbone.blocks, self.ft.lora_targets) == 0:
                raise ValueError(
                    f"階段 {st.name!r} 要注入 LoRA，但主幹的 blocks 裡沒有名字在 {list(self.ft.lora_targets)} 的 nn.Linear"
                )
        self._t_start = time.time()
        self._last_ckpt_time = time.time()
        self._bad_streak = 0

        ckpt = self._read_last() if resume else None
        start_stage, start_epoch, start_batch = 0, 0, 0
        if ckpt is None:
            set_seed(self.ft.seed)
            self.history = []
            self.best_score = -math.inf
            self.has_best = False
            self.best_stage = -1
            self.best_epoch = -1
            self.global_step = 0
            self._bad_epochs = 0
        else:
            self._load_state(ckpt)
            self.history = [dict(h) for h in ckpt.get("history", [])]
            self.best_score = float(ckpt.get("best_score", -math.inf))
            self.has_best = bool(ckpt.get("has_best", False))
            self.best_stage = int(ckpt.get("best_stage", -1))
            self.best_epoch = int(ckpt.get("best_epoch", -1))
            self.global_step = int(ckpt.get("global_step", 0))
            self._bad_epochs = int(ckpt.get("bad_epochs", 0))
            start_stage = int(ckpt["next_stage"])
            start_epoch = int(ckpt["next_epoch"])
            start_batch = int(ckpt["next_batch"])
            saved_batches = int(ckpt.get("n_train_batches", n_batches))
            if saved_batches != n_batches:
                warnings.warn(
                    f"checkpoint 存檔時每個 epoch 有 {saved_batches} 個 batch，現在是 {n_batches}，"
                    "資料可能變了，接續的位置不一定對",
                    stacklevel=2,
                )
            if self.has_best and not self.best_path.exists():
                warnings.warn(f"checkpoint 說有最佳權重，但找不到 {self.best_path}", stacklevel=2)
                self.has_best = False
            # 模型結構（含 LoRA）都還原後才還原亂數，之後的流程和沒中斷時一樣。
            _set_rng_state(ckpt.get("rng"))
            self._log(
                f"從 {self.last_path} 接續：階段 {start_stage}、epoch {start_epoch}、batch {start_batch}，"
                f"目前最好 RankIC {self.best_score:.5f}"
            )

        for si in range(start_stage, len(stages)):
            if stop_after is not None and si > stop_si:
                break
            stage = stages[si]
            mid_stage = ckpt is not None and si == start_stage and ckpt.get("optimizer") is not None
            acc: _EpochAcc | None = None
            if mid_stage:
                assert ckpt is not None
                first_epoch, skip = start_epoch, start_batch
                acc = _EpochAcc.from_dict(ckpt.get("epoch_acc")) if skip > 0 else None
            else:
                if self.has_best:
                    self.load_best()
                first_epoch, skip = 0, 0
                acc = None
                self._bad_epochs = 0
            names = configure_stage(self.model, stage, self.ft)
            run = self._build_stage(si, stage, n_batches)
            if mid_stage:
                assert ckpt is not None
                self._restore_run(run, ckpt)
            ckpt = None
            n_train = sum(p.numel() for p in run.params)
            self._log(
                f"階段 {si} {stage.name!r}（{stage.trainable}）：可訓練 {len(names)} 個張量、{n_train:,} 個參數，"
                f"{run.total_steps} 步（warmup {run.warmup_steps}），從 epoch {first_epoch} 開始"
            )

            epoch = first_epoch
            while epoch < stage.epochs:
                if run.step >= run.total_steps and skip == 0:
                    break
                if acc is None:
                    acc = _EpochAcc()
                self._run_epoch(run, train_loader, epoch, skip, acc)
                skip = 0
                t_val = time.time()
                if val_loader is not None:
                    assert val_samples is not None
                    val = self.evaluate(val_loader, val_samples)
                else:
                    val = float("nan")
                val_seconds = time.time() - t_val
                improved = self._update_best(val, si, epoch, val_loader is not None)
                self._bad_epochs = 0 if improved else self._bad_epochs + 1
                rec: dict[str, Any] = {
                    "stage": stage.name,
                    "stage_idx": si,
                    "trainable": stage.trainable,
                    "epoch": epoch,
                    "train_loss": acc.mean_loss(),
                    "val_rank_ic": val,
                    "seconds": acc.seconds() + val_seconds,
                    "val_seconds": val_seconds,
                    "steps": run.step,
                    "global_step": self.global_step,
                    "batches": acc.batches,
                    "skipped_batches": acc.skipped,
                    "is_best": improved,
                    "lr_max": max(float(g["lr"]) for g in run.optimizer.param_groups),
                }
                for k, v in acc.mean_parts().items():
                    rec[f"loss_{k}"] = v
                self.history.append(rec)
                self._log(
                    f"階段 {stage.name} epoch {epoch}：train_loss {rec['train_loss']:.5f}，"
                    f"val RankIC {val:.5f}{'（最好）' if improved else ''}，{rec['seconds']:.0f} 秒"
                )
                acc = None
                epoch += 1
                reached = si == stop_si and epoch > stop_ep
                stage_over = (
                    epoch >= stage.epochs
                    or run.step >= run.total_steps
                    or self._bad_epochs >= int(self.ft.early_stop_patience)
                    or reached
                )
                if stage_over:
                    break
                self._save_last(si, epoch, 0, run, None)
            self._bad_epochs = 0
            self._save_last(si + 1, 0, 0, None, None)
            if si == stop_si:
                self._log(f"照 stop_after 停在階段 {stop_si}、epoch {stop_ep}")
                break

        if self.has_best:
            self.load_best()
            self._log(
                f"完成，載入最好的權重：階段 {self.best_stage}、epoch {self.best_epoch}、RankIC {self.best_score:.5f}"
            )
        else:
            warnings.warn("沒有任何 epoch 跑完，沒有 best.pt", stacklevel=2)
        return list(self.history)
