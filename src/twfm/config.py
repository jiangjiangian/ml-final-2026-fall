"""twfm 的設定。全部是 frozen dataclass，改值用 `dataclasses.replace`。

`PipelineConfig` 把五組設定包在一起，欄名是 `data`、`split`、`model`、`finetune`、`cost`。
`PipelineConfig.from_dict` 讀 JSON 的 dict（缺的欄用預設值，未知的欄丟 `ValueError`），
`to_dict` 回傳可以直接 `json.dump` 的 dict，兩者互為反函數。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Mapping

_REFRESH_CHOICES = ("yearly", "monthly")
_BACKBONE_CHOICES = ("kronos", "patch")
_TRAINABLE_CHOICES = ("head", "last_k", "lora", "all")


def _as_tuple(obj: object, name: str, value: Any) -> None:
    """把 list 轉成 tuple 寫回 frozen dataclass。JSON 讀進來的都是 list。"""
    if isinstance(value, tuple):
        return
    if isinstance(value, (list, range)):
        object.__setattr__(obj, name, tuple(value))
        return
    raise TypeError(f"{type(obj).__name__}.{name} 要是 tuple 或 list，拿到 {type(value).__name__}")


@dataclass(frozen=True)
class DataConfig:
    """資料、股票池、標籤的設定。

    lookback：每個樣本的視窗長度（列數，到 i 為止）。
    universe_size：每期股票池取前幾檔（依成交金額）。
    universe_lookback_days：排名用的交易日數。
    universe_refresh：`"yearly"` 每年換一次名單，`"monthly"` 每月換一次。
    min_close：i 的原始收盤價至少多少才進池。
    horizon：標籤期數，1 是 t 開盤到 t 收盤。
    target_clip_z：每天 z-score 後的目標裁在 ±這個值。
    limit_change_date：漲跌幅從 7% 改成 10% 的第一天（含）。
    us_symbols：美股指數代號。
    beta_window：個股對大盤 beta 的滾動列數。
    """

    lookback: int = 128
    universe_size: int = 500
    universe_lookback_days: int = 250
    universe_refresh: str = "yearly"
    min_close: float = 10.0
    horizon: int = 1
    target_clip_z: float = 5.0
    limit_change_date: str = "2015-06-01"
    limit_pct_old: float = 0.07
    limit_pct_new: float = 0.10
    us_symbols: tuple[str, ...] = ("^SOX", "^IXIC")
    beta_window: int = 60

    def __post_init__(self) -> None:
        _as_tuple(self, "us_symbols", self.us_symbols)
        if self.universe_refresh not in _REFRESH_CHOICES:
            raise ValueError(f"universe_refresh 要是 {_REFRESH_CHOICES} 之一，拿到 {self.universe_refresh!r}")
        if self.lookback < 1:
            raise ValueError("lookback 至少 1")
        if self.universe_size < 1:
            raise ValueError("universe_size 至少 1")
        if self.universe_lookback_days < 1:
            raise ValueError("universe_lookback_days 至少 1")
        if self.horizon < 1:
            raise ValueError("horizon 至少 1")
        if self.beta_window < 2:
            raise ValueError("beta_window 至少 2")
        if self.target_clip_z <= 0:
            raise ValueError("target_clip_z 要大於 0")
        if not (0 < self.limit_pct_old < 1 and 0 < self.limit_pct_new < 1):
            raise ValueError("limit_pct_old、limit_pct_new 要在 0 和 1 之間")
        if len(self.us_symbols) == 0:
            raise ValueError("us_symbols 不能是空的")


@dataclass(frozen=True)
class SplitConfig:
    """固定切分的日期。都是台股交易日的日期字串，兩端都含。

    訓練看的是標籤日期，`fixed_split` 會在訓練尾端去掉 `max(embargo_days, horizon − 1)` 個交易日。
    """

    train_start: str = "2004-01-01"
    train_end: str = "2024-06-30"
    val_start: str = "2024-07-01"
    val_end: str = "2025-06-30"
    test_start: str = "2025-07-01"
    test_end: str | None = None
    embargo_days: int = 0

    def __post_init__(self) -> None:
        if self.embargo_days < 0:
            raise ValueError("embargo_days 不能是負的")


@dataclass(frozen=True)
class ModelConfig:
    """主幹和 head 的設定。

    backbone：`"kronos"`（預訓練的 Kronos-small）或 `"patch"`（從頭訓練的對照）。
    kronos_src_dir：clone 下來的 `shiyu-coder/Kronos` 根目錄，會加進 `sys.path`。
    kronos_pretrained：False 時用同一份設定重建隨機初始化的 Kronos（tokenizer 仍用預訓練的）。
    quantiles：分位數頭的分位點，空的就不建分位數頭。
    """

    backbone: str = "kronos"
    kronos_model_id: str = "NeoQuasar/Kronos-small"
    kronos_tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base"
    kronos_src_dir: str | None = None
    kronos_pretrained: bool = True
    kronos_clip: float = 5.0
    use_time_stamp: bool = True
    patch_len: int = 8
    patch_d_model: int = 128
    patch_layers: int = 4
    patch_heads: int = 4
    head_hidden: int = 256
    head_dropout: float = 0.1
    quantiles: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _as_tuple(self, "quantiles", self.quantiles)
        if self.backbone not in _BACKBONE_CHOICES:
            raise ValueError(f"backbone 要是 {_BACKBONE_CHOICES} 之一，拿到 {self.backbone!r}")
        qs = [float(q) for q in self.quantiles]
        if any(not (0.0 < q < 1.0) for q in qs):
            raise ValueError("quantiles 每個都要在 0 和 1 之間")
        if any(b <= a for a, b in zip(qs, qs[1:])):
            raise ValueError("quantiles 要嚴格遞增")
        object.__setattr__(self, "quantiles", tuple(qs))
        if self.patch_len < 1 or self.patch_d_model < 1 or self.patch_layers < 1 or self.patch_heads < 1:
            raise ValueError("patch_* 都要至少 1")
        if self.patch_d_model % self.patch_heads != 0:
            raise ValueError("patch_d_model 要能被 patch_heads 整除")
        if not (0.0 <= self.head_dropout < 1.0):
            raise ValueError("head_dropout 要在 [0, 1)")


@dataclass(frozen=True)
class StageConfig:
    """微調的一階。

    trainable：`"head"` 只訓練 head；`"last_k"` 再打開主幹最後 `last_k` 個 block；
    `"lora"` 注入 LoRA，只訓練 LoRA 和 head；`"all"` 主幹全部打開（Kronos 的 tokenizer 除外）。
    lr_backbone 是最深那個 block 的學習率，往淺每層乘 `layer_decay`。
    """

    name: str
    trainable: str
    last_k: int = 2
    epochs: int = 1
    max_steps: int | None = None
    lr_head: float = 1e-3
    lr_backbone: float = 4e-5
    layer_decay: float = 0.8
    warmup_steps: int = 100

    def __post_init__(self) -> None:
        if self.trainable not in _TRAINABLE_CHOICES:
            raise ValueError(f"trainable 要是 {_TRAINABLE_CHOICES} 之一，拿到 {self.trainable!r}")
        if self.last_k < 0:
            raise ValueError("last_k 不能是負的")
        if self.epochs < 1:
            raise ValueError("epochs 至少 1")
        if self.max_steps is not None and self.max_steps < 1:
            raise ValueError("max_steps 是 None 或至少 1")
        if not (0.0 < self.layer_decay <= 1.0):
            raise ValueError("layer_decay 要在 (0, 1]")
        if self.warmup_steps < 0:
            raise ValueError("warmup_steps 不能是負的")


def default_stages() -> tuple[StageConfig, ...]:
    """預設三階：先只訓練 head，再放開最後 2 層，最後試 LoRA（r 在 `FinetuneConfig.lora_r`）。"""
    return (
        StageConfig(name="head", trainable="head", epochs=1, lr_head=1e-3),
        StageConfig(name="last_k", trainable="last_k", last_k=2, lr_backbone=4e-5),
        StageConfig(name="lora", trainable="lora"),
    )


def default_loss_weights() -> dict[str, float]:
    """預設損失：Huber 1.0 加 IC 損失 0.2。"""
    return {"huber": 1.0, "ic": 0.2}


def _stage_from_any(value: Any) -> StageConfig:
    if isinstance(value, StageConfig):
        return value
    if isinstance(value, Mapping):
        return _from_mapping(StageConfig, value)
    raise TypeError(f"stages 的每一項要是 StageConfig 或 dict，拿到 {type(value).__name__}")


@dataclass(frozen=True)
class FinetuneConfig:
    """微調流程的設定。

    batch_days：每個 batch 幾個交易日（同一天的股票一定在同一個 batch）。
    max_stocks_per_day：每天最多抽幾檔，None 是全部。
    amp_dtype：CUDA 混合精度的型別。auto 在 compute capability ≥ 8（A100、L4）用 bf16，
    其他（T4）用 fp16 加 GradScaler。
    loss_weights：損失名稱對權重，名稱見 `twfm.train.losses.CompositeLoss`。
    """

    stages: tuple[StageConfig, ...] = field(default_factory=default_stages)
    batch_days: int = 8
    max_stocks_per_day: int | None = None
    amp: bool = True
    amp_dtype: str = "auto"
    grad_clip: float = 1.0
    weight_decay: float = 0.01
    grad_accum: int = 1
    lora_r: int = 8
    lora_alpha: float = 16.0
    lora_dropout: float = 0.05
    lora_targets: tuple[str, ...] = ("q_proj", "k_proj", "v_proj", "out_proj", "w1", "w2", "w3")
    loss_weights: dict[str, float] = field(default_factory=default_loss_weights)
    huber_delta: float = 1.0
    listnet_temperature: float = 1.0
    early_stop_patience: int = 2
    seed: int = 0
    num_workers: int = 2
    checkpoint_dir: str = "checkpoints"

    def __post_init__(self) -> None:
        if not isinstance(self.stages, (tuple, list)):
            raise TypeError("stages 要是 tuple 或 list")
        object.__setattr__(self, "stages", tuple(_stage_from_any(s) for s in self.stages))
        _as_tuple(self, "lora_targets", self.lora_targets)
        if not isinstance(self.loss_weights, Mapping):
            raise TypeError("loss_weights 要是 dict")
        object.__setattr__(self, "loss_weights", {str(k): float(v) for k, v in self.loss_weights.items()})
        if len(self.stages) == 0:
            raise ValueError("stages 不能是空的")
        if self.amp_dtype not in ("auto", "fp16", "bf16"):
            raise ValueError("amp_dtype 要是 auto、fp16 或 bf16")
        if self.batch_days < 1:
            raise ValueError("batch_days 至少 1")
        if self.max_stocks_per_day is not None and self.max_stocks_per_day < 2:
            raise ValueError("max_stocks_per_day 是 None 或至少 2（排序損失一天至少要 2 檔）")
        if self.grad_accum < 1:
            raise ValueError("grad_accum 至少 1")
        if self.lora_r < 1:
            raise ValueError("lora_r 至少 1")
        if not (0.0 <= self.lora_dropout < 1.0):
            raise ValueError("lora_dropout 要在 [0, 1)")
        if self.early_stop_patience < 1:
            raise ValueError("early_stop_patience 至少 1")
        if self.num_workers < 0:
            raise ValueError("num_workers 不能是負的")


@dataclass(frozen=True)
class CostConfig:
    """台股交易成本。

    commission_rate：手續費率上限 0.1425%，實收再乘 `commission_discount`。
    daytrade_sell_tax_rate：現股當沖證交稅 0.15%（減半從 2017-04-28 起，適用到 2027-12-31；
    回測照每天的日期判斷，這段期間以外用 `sell_tax_rate`）。
    capital_ntd：給了才套最低手續費 `min_fee_ntd`。
    """

    commission_rate: float = 0.001425
    commission_discount: float = 0.6
    min_fee_ntd: float = 20.0
    sell_tax_rate: float = 0.003
    daytrade_sell_tax_rate: float = 0.0015
    etf_sell_tax_rate: float = 0.001
    slippage_bps: float = 0.0
    capital_ntd: float | None = None

    def __post_init__(self) -> None:
        if self.commission_rate < 0 or self.commission_discount < 0:
            raise ValueError("手續費率和折扣不能是負的")
        if self.sell_tax_rate < 0 or self.daytrade_sell_tax_rate < 0 or self.etf_sell_tax_rate < 0:
            raise ValueError("稅率不能是負的")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps 不能是負的")
        if self.capital_ntd is not None and self.capital_ntd <= 0:
            raise ValueError("capital_ntd 是 None 或大於 0")


_SECTIONS: dict[str, type] = {
    "data": DataConfig,
    "split": SplitConfig,
    "model": ModelConfig,
    "finetune": FinetuneConfig,
    "cost": CostConfig,
}


def _from_mapping(cls: type, values: Mapping[str, Any]) -> Any:
    """用 dict 建一個 dataclass。未知的欄丟 `ValueError`，缺的欄用預設值。"""
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = sorted(set(values) - names)
    if unknown:
        raise ValueError(f"{cls.__name__} 沒有這些欄：{unknown}")
    return cls(**dict(values))


def _section_from_any(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return _from_mapping(cls, value)
    raise TypeError(f"{cls.__name__} 的設定要是 dict 或 {cls.__name__}，拿到 {type(value).__name__}")


def _jsonable(value: Any) -> Any:
    """把 tuple 換成 list、dict 的 key 換成 str，讓 `json.dump` 可以直接寫。"""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@dataclass(frozen=True)
class PipelineConfig:
    """端到端的設定：五組子設定加輸出資料夾和裝置。

    device：`"auto"` 有 CUDA 就用 CUDA，否則 CPU；也可以直接寫 `"cuda"`、`"cpu"`。
    """

    data: DataConfig = field(default_factory=DataConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    finetune: FinetuneConfig = field(default_factory=FinetuneConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    out_dir: str = "twfm_out"
    device: str = "auto"

    def __post_init__(self) -> None:
        for name, cls in _SECTIONS.items():
            value = getattr(self, name)
            if not isinstance(value, cls):
                object.__setattr__(self, name, _section_from_any(cls, value))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> PipelineConfig:
        """從 dict（通常是讀進來的 JSON）建設定。

        子設定可以只給一部分欄，其他用預設值。`finetune.stages` 是 dict 的 list。
        任何一層有未知的欄都丟 `ValueError`，避免打錯字卻沒發現。
        """
        values = dict(d or {})
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = sorted(set(values) - names)
        if unknown:
            raise ValueError(f"PipelineConfig 沒有這些欄：{unknown}")
        kwargs: dict[str, Any] = {}
        for name, sub_cls in _SECTIONS.items():
            if name in values and values[name] is not None:
                kwargs[name] = _section_from_any(sub_cls, values[name])
        for name in ("out_dir", "device"):
            if name in values and values[name] is not None:
                kwargs[name] = str(values[name])
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """回傳可以 `json.dump` 的 dict。`PipelineConfig.from_dict(c.to_dict()) == c`。"""
        return _jsonable(dataclasses.asdict(self))
