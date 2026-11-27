"""`twfm.models.backbones.KronosBackbone` 的測試（要真的 Kronos 原始碼和權重）。

沒有環境變數 `KRONOS_SRC`（clone 下來的 `shiyu-coder/Kronos` 根目錄）就整個 skip。
有的話從 Hugging Face 載入 Kronos-small 和 Kronos-Tokenizer-base（要連網，或用
`KRONOS_MODEL_ID`、`KRONOS_TOKENIZER_ID` 指到本機資料夾），在 CPU、fp32 上跑：

- `encode` 輸出 `[B, d_model]`，Kronos-small 的 `d_model` 是 512，值都是有限的。
- 因果：只改「已標準化」視窗的最後一根，前面位置的 token 和隱藏狀態不變。
  不改原始價格的最後一根，因為那會改到整個視窗的 mean、std，所有位置本來就會變。
- `train()` 之後 tokenizer 仍是 eval；tokenizer、`head`、`dep_layer` 一直不可訓練。
- 分層解凍、LoRA 注入後輸出不變、梯度只到該到的地方。
- 有 CUDA 時另外測 fp16 AMP 加 gradient checkpointing 的訓練路徑（輸出、梯度都是有限值）。
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

if not os.environ.get("KRONOS_SRC"):
    pytest.skip("沒有設定環境變數 KRONOS_SRC，跳過 Kronos 測試", allow_module_level=True)

pytest.importorskip("huggingface_hub")
pytest.importorskip("einops")
pytest.importorskip("safetensors")
pytest.importorskip("tqdm")

import twfm.config as config  # noqa: E402
import twfm.models.backbones as backbones  # noqa: E402
import twfm.models.lora as lora  # noqa: E402
import twfm.models.model as model_mod  # noqa: E402

MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base")
B = 3
L = 48


@pytest.fixture(scope="module")
def backbone() -> backbones.KronosBackbone:
    cfg = config.ModelConfig(
        backbone="kronos",
        kronos_model_id=MODEL_ID,
        kronos_tokenizer_id=TOKENIZER_ID,
        kronos_src_dir=os.environ["KRONOS_SRC"],
    )
    bb = backbones.KronosBackbone(cfg)
    bb.eval()
    return bb


def _batch(seed: int = 0) -> dict[str, torch.Tensor]:
    """假的日 K：正的價格、量級很大的成交量和金額、真的日曆時間戳。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=L)
    levels = np.zeros((B, L, 6), dtype=np.float32)
    for b in range(B):
        close = 50.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, L)))
        open_ = close * np.exp(rng.normal(0.0, 0.01, L))
        high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.02, L))
        low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.02, L))
        volume = rng.uniform(1e6, 5e7, L)
        amount = volume * close
        levels[b] = np.stack([open_, high, low, close, volume, amount], axis=1)
    stamps = np.zeros((B, L, 5), dtype=np.float32)
    stamps[:, :, 2] = np.asarray(dates.weekday)
    stamps[:, :, 3] = np.asarray(dates.day)
    stamps[:, :, 4] = np.asarray(dates.month)
    return {"levels": torch.from_numpy(levels), "stamps": torch.from_numpy(stamps)}


def test_encode_shape(backbone: backbones.KronosBackbone) -> None:
    batch = _batch()
    with torch.no_grad():
        out = backbone.encode(batch)
    assert tuple(out.shape) == (B, backbone.d_model)
    assert out.dtype == torch.float32
    assert torch.isfinite(out).all()
    if MODEL_ID.endswith("Kronos-small"):
        assert backbone.d_model == 512
        assert tuple(out.shape) == (B, 512)
    # 同樣的輸入在 eval 下結果一樣（tokenizer、dropout 都是確定的）。
    with torch.no_grad():
        again = backbone.encode(batch)
    torch.testing.assert_close(again, out, rtol=0.0, atol=1e-6)


def test_causal_last_bar(backbone: backbones.KronosBackbone) -> None:
    batch = _batch(1)
    with torch.no_grad():
        x_norm = backbone.revin(batch["levels"], "norm")
        x_new = x_norm.clone()
        x_new[:, -1, :] = torch.clamp(-x_new[:, -1, :] + 1.5, -5.0, 5.0)
        s1_a, s2_a = backbone._tokenize(x_norm)
        s1_b, s2_b = backbone._tokenize(x_new)
        h_a = backbone._forward_normalized(x_norm, batch["stamps"])
        h_b = backbone._forward_normalized(x_new, batch["stamps"])
    assert tuple(h_a.shape) == (B, L, backbone.d_model)
    assert torch.equal(s1_a[:, :-1], s1_b[:, :-1])
    assert torch.equal(s2_a[:, :-1], s2_b[:, :-1])
    torch.testing.assert_close(h_a[:, :-1], h_b[:, :-1], rtol=0.0, atol=1e-5)
    # 最後一根真的有被改到（不然上面的檢查沒有意義）。
    assert not torch.equal(h_a[:, -1], h_b[:, -1])
    # encode 就是最後一個位置。
    with torch.no_grad():
        enc = backbone.encode(batch)
    torch.testing.assert_close(enc, h_a[:, -1], rtol=0.0, atol=1e-6)


def test_tokenizer_frozen_and_eval(backbone: backbones.KronosBackbone) -> None:
    try:
        backbone.unfreeze_all()
        backbone.train()
        assert backbone.training
        assert backbone.model.training
        assert not backbone.tokenizer.training
        assert all(not p.requires_grad for p in backbone.tokenizer.parameters())
        assert all(not p.requires_grad for p in backbone.model.head.parameters())
        assert all(not p.requires_grad for p in backbone.model.dep_layer.parameters())
        never = {id(p) for p in backbone.never_train_params()}
        assert {id(p) for p in backbone.tokenizer.parameters()} <= never
        # 全部凍結時 train() 讓主幹維持 eval（frozen_eval）。
        backbone.freeze_all()
        backbone.train()
        assert not backbone.training
        assert not backbone.model.training
    finally:
        backbone.freeze_all()
        backbone.eval()


def test_unfreeze_last_and_param_groups(backbone: backbones.KronosBackbone) -> None:
    try:
        backbone.freeze_all()
        assert not backbone.has_trainable()
        backbone.unfreeze_last(2)
        n = len(backbone.blocks)
        trainable = {id(p) for p in backbone.parameters() if p.requires_grad}
        expected = {id(p) for j in (n - 2, n - 1) for p in backbone.blocks[j].parameters()}
        expected |= {id(p) for p in backbone.top_params()}
        assert trainable == expected
        assert len(backbone.embedding_params()) > 0

        cfg = config.PipelineConfig(model=config.ModelConfig(kronos_src_dir=os.environ["KRONOS_SRC"]))
        head = model_mod.FiLMCovariateHead(backbone.d_model, 3, 2, cfg.model.head_hidden, 0.1)
        full = model_mod.TWFMModel(backbone, head)
        stage = config.StageConfig(name="last_k", trainable="last_k", lr_head=1e-3, lr_backbone=4e-5, layer_decay=0.8)
        groups = full.param_groups(stage, weight_decay=0.01)
        in_groups = {id(p) for g in groups for p in g["params"]}
        assert in_groups == expected | {id(p) for p in head.parameters()}
        lrs = {g["name"]: g["lr"] for g in groups}
        assert lrs[f"block_{n - 1}"] == pytest.approx(4e-5)
        assert lrs[f"block_{n - 2}"] == pytest.approx(4e-5 * 0.8)
        assert lrs["head"] == pytest.approx(1e-3)
        assert all(g["weight_decay"] == 0.0 for g in groups if g["name"].endswith("_no_wd"))
    finally:
        backbone.freeze_all()
        backbone.eval()


def test_grad_flow_last_block(backbone: backbones.KronosBackbone) -> None:
    try:
        backbone.freeze_all()
        backbone.unfreeze_last(1)
        backbone.train()
        backbone.zero_grad(set_to_none=True)
        out = backbone.encode(_batch(2))
        out.pow(2).mean().backward()
        last = backbone.blocks[-1]
        assert any(p.grad is not None and float(p.grad.abs().sum()) > 0 for p in last.parameters())
        assert all(p.grad is None for p in backbone.tokenizer.parameters())
        assert all(p.grad is None for p in backbone.blocks[0].parameters())
    finally:
        backbone.zero_grad(set_to_none=True)
        backbone.freeze_all()
        backbone.eval()


@pytest.mark.skipif(not torch.cuda.is_available(), reason="要 CUDA 才能測 fp16 AMP")
def test_cuda_amp_with_checkpointing() -> None:
    """T4 上實際的訓練路徑：CUDA、fp16 autocast、gradient checkpointing、最後一層可訓練。

    檢查輸出和梯度都是有限值（fp16 溢位、q/k/v 混合 dtype 都會在這裡出錯），
    也檢查 AMP 和 fp32 的輸出差不多（RoPE 快取用 fp32 算角度）。
    """
    cfg = config.ModelConfig(
        backbone="kronos",
        kronos_model_id=MODEL_ID,
        kronos_tokenizer_id=TOKENIZER_ID,
        kronos_src_dir=os.environ["KRONOS_SRC"],
    )
    bb = backbones.KronosBackbone(cfg, gradient_checkpointing=True).to("cuda")
    batch = {k: v.to("cuda") for k, v in _batch(4).items()}

    bb.eval()
    with torch.no_grad():
        ref = bb.encode(batch)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            amp_eval = bb.encode(batch)
    assert amp_eval.dtype == torch.float32
    assert torch.isfinite(amp_eval).all()
    rel = float((amp_eval - ref).norm() / ref.norm().clamp_min(1e-6))
    assert rel < 0.05, rel

    bb.freeze_all()
    bb.unfreeze_last(1)
    bb.train()
    assert bb.training and not bb.tokenizer.training
    with torch.autocast(device_type="cuda", dtype=torch.float16):
        out = bb(batch)
    assert out.dtype == torch.float32
    assert torch.isfinite(out).all()
    out.float().pow(2).mean().backward()
    grads = [p.grad for p in bb.blocks[-1].parameters() if p.requires_grad]
    assert grads and all(g is not None and torch.isfinite(g).all() for g in grads)
    assert any(float(g.abs().sum()) > 0 for g in grads if g is not None)
    assert all(p.grad is None for p in bb.tokenizer.parameters())


def test_lora_on_blocks_keeps_output() -> None:
    """另外建一個主幹（不動共用的 fixture），注入 LoRA 後 eval 的輸出不變。"""
    cfg = config.ModelConfig(
        backbone="kronos",
        kronos_model_id=MODEL_ID,
        kronos_tokenizer_id=TOKENIZER_ID,
        kronos_src_dir=os.environ["KRONOS_SRC"],
    )
    bb = backbones.KronosBackbone(cfg)
    bb.eval()
    batch = _batch(3)
    with torch.no_grad():
        before = bb.encode(batch)
    bb.freeze_all()
    names = lora.inject_lora(bb.blocks, config.FinetuneConfig().lora_targets, r=8, alpha=16.0, dropout=0.05)
    assert len(names) == 7 * len(bb.blocks)
    assert not any("dep_layer" in n or "tokenizer" in n for n in names)
    bb.eval()
    with torch.no_grad():
        after = bb.encode(batch)
    torch.testing.assert_close(after, before, rtol=0.0, atol=1e-5)
    trainable = {id(p) for p in bb.parameters() if p.requires_grad}
    assert trainable == {id(p) for p in lora.lora_parameters(bb)}
