"""`twfm.models.lora` 的測試。

- 注入後輸出和原本一樣（`B = 0`）。
- 凍結後再注入，只有 LoRA 參數可訓練，反向傳播也只有 LoRA 拿到梯度。
- 合併前後輸出一樣（`B` 填非 0 的值，atol 1e-5）。
- 重複注入不會包兩層，`freeze_all` 之後再注入會把 LoRA 重新打開。
- `nn.TransformerEncoderLayer`（PatchTransformer 用的）：`out_proj` 被 `nn.MultiheadAttention`
  直接讀 `.weight`，eval 的快速路徑也直接讀 `.weight`，兩條路徑都要看得到 LoRA。
"""

from __future__ import annotations

import copy

import pytest

torch = pytest.importorskip("torch")
from torch import nn  # noqa: E402

import twfm.models.lora as lora  # noqa: E402

TARGETS = ("q_proj", "k_proj", "v_proj", "out_proj", "w1", "w2", "w3")


class _ToyAttention(nn.Module):
    """和 Kronos 同名的線性層：q/k/v/out_proj。"""

    def __init__(self, d: int) -> None:
        super().__init__()
        self.q_proj = nn.Linear(d, d)
        self.k_proj = nn.Linear(d, d)
        self.v_proj = nn.Linear(d, d)
        self.out_proj = nn.Linear(d, d)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        q, k, v = self.q_proj(x), self.k_proj(x), self.v_proj(x)
        att = torch.softmax(q @ k.transpose(-1, -2) / q.shape[-1] ** 0.5, dim=-1)
        return self.out_proj(att @ v)


class _ToyFFN(nn.Module):
    """和 Kronos 同名的 SwiGLU：w1、w2、w3（沒有 bias）。"""

    def __init__(self, d: int, ff: int) -> None:
        super().__init__()
        self.w1 = nn.Linear(d, ff, bias=False)
        self.w3 = nn.Linear(d, ff, bias=False)
        self.w2 = nn.Linear(ff, d, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.w2(torch.nn.functional.silu(self.w1(x)) * self.w3(x))


class _ToyBlock(nn.Module):
    def __init__(self, d: int, ff: int) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(d)
        self.self_attn = _ToyAttention(d)
        self.norm2 = nn.LayerNorm(d)
        self.ffn = _ToyFFN(d, ff)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.self_attn(self.norm1(x))
        return x + self.ffn(self.norm2(x))


class _ToyModel(nn.Module):
    def __init__(self, d: int = 16, ff: int = 32, n_blocks: int = 2) -> None:
        super().__init__()
        self.blocks = nn.ModuleList([_ToyBlock(d, ff) for _ in range(n_blocks)])
        self.head = nn.Linear(d, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for b in self.blocks:
            x = b(x)
        return self.head(x).squeeze(-1)


def _make(seed: int = 0) -> tuple[_ToyModel, torch.Tensor]:
    torch.manual_seed(seed)
    model = _ToyModel()
    x = torch.randn(3, 5, 16)
    return model, x


def _randomize_b(module: nn.Module, std: float = 0.1) -> None:
    with torch.no_grad():
        for m in module.modules():
            if isinstance(m, lora.LoRALinear):
                m.lora_B.normal_(0.0, std)


def test_injection_keeps_output() -> None:
    model, x = _make()
    model.eval()
    with torch.no_grad():
        before = model(x)
    names = lora.inject_lora(model.blocks, TARGETS, r=4, alpha=8.0, dropout=0.1)
    assert len(names) == 2 * len(TARGETS)
    assert "0.self_attn.q_proj" in names and "1.ffn.w2" in names
    assert lora.has_lora(model)
    model.eval()
    with torch.no_grad():
        after = model(x)
    torch.testing.assert_close(after, before, rtol=0.0, atol=1e-7)
    # train 模式下 dropout 只在 A 之前，B = 0 時輸出仍然一樣。
    model.train()
    with torch.no_grad():
        after_train = model(x)
    torch.testing.assert_close(after_train, before, rtol=0.0, atol=1e-7)


def test_lora_layer_shapes_and_scale() -> None:
    torch.manual_seed(1)
    base = nn.Linear(7, 5)
    layer = lora.LoRALinear(base, r=3, alpha=6.0, dropout=0.0)
    assert tuple(layer.lora_A.shape) == (3, 7)
    assert tuple(layer.lora_B.shape) == (5, 3)
    assert float(layer.lora_B.abs().sum()) == 0.0
    assert layer.scale == pytest.approx(2.0)
    assert not base.weight.requires_grad and not base.bias.requires_grad
    assert layer.in_features == 7 and layer.out_features == 5
    assert layer.bias is base.bias


def test_only_lora_trainable() -> None:
    model, x = _make()
    for p in model.parameters():
        p.requires_grad_(False)
    lora.inject_lora(model.blocks, TARGETS, r=4, alpha=8.0, dropout=0.0)
    lora_ids = {id(p) for p in lora.lora_parameters(model)}
    assert len(lora_ids) == 2 * 2 * len(TARGETS)
    trainable = {id(p) for p in model.parameters() if p.requires_grad}
    assert trainable == lora_ids
    n_train, n_total = lora.count_trainable(model)
    assert n_train == sum(p.numel() for p in lora.lora_parameters(model))
    assert n_total == sum(p.numel() for p in model.parameters())
    assert 0 < n_train < n_total

    _randomize_b(model)
    model.train()
    loss = model(x).pow(2).mean()
    loss.backward()
    for name, p in model.named_parameters():
        if id(p) in lora_ids:
            assert p.grad is not None, name
            assert torch.isfinite(p.grad).all(), name
        else:
            assert p.grad is None, name
    assert any(float(p.grad.abs().sum()) > 0 for p in lora.lora_parameters(model) if p.grad is not None)


def test_merge_matches() -> None:
    model, x = _make()
    lora.inject_lora(model.blocks, TARGETS, r=4, alpha=8.0, dropout=0.2)
    _randomize_b(model)
    model.eval()
    with torch.no_grad():
        unmerged = model(x)
    n = lora.merge_lora(model)
    assert n == 2 * len(TARGETS)
    assert not lora.has_lora(model)
    assert all(type(m) is nn.Linear for name, m in model.named_modules() if name.endswith(("q_proj", "w2")))
    with torch.no_grad():
        merged = model(x)
    torch.testing.assert_close(merged, unmerged, rtol=0.0, atol=1e-5)
    # 合併後鍵名回到原本的樣子。
    keys = set(model.state_dict().keys())
    assert "blocks.0.self_attn.q_proj.weight" in keys
    assert not any("lora_" in k or ".base." in k for k in keys)


def test_single_layer_merge_and_weight_property() -> None:
    torch.manual_seed(2)
    layer = lora.LoRALinear(nn.Linear(6, 4), r=2, alpha=4.0, dropout=0.0)
    with torch.no_grad():
        layer.lora_B.normal_(0.0, 0.5)
    x = torch.randn(10, 6)
    with torch.no_grad():
        y = layer(x)
        y_weight = torch.nn.functional.linear(x, layer.weight, layer.bias)
        y_merged = layer.merge()(x)
    torch.testing.assert_close(y_weight, y, rtol=0.0, atol=1e-5)
    torch.testing.assert_close(y_merged, y, rtol=0.0, atol=1e-5)
    assert not layer.merge().weight.requires_grad


def test_no_double_injection_and_reenable() -> None:
    model, _ = _make()
    first = lora.inject_lora(model.blocks, TARGETS, r=4, alpha=8.0)
    assert len(first) == 2 * len(TARGETS)
    for p in model.parameters():
        p.requires_grad_(False)
    second = lora.inject_lora(model.blocks, TARGETS, r=4, alpha=8.0)
    assert second == []
    n_lora = sum(1 for m in model.modules() if isinstance(m, lora.LoRALinear))
    assert n_lora == 2 * len(TARGETS)
    assert not any(isinstance(m.base, lora.LoRALinear) for m in model.modules() if isinstance(m, lora.LoRALinear))
    assert all(p.requires_grad for p in lora.lora_parameters(model))
    keys = set(model.state_dict().keys())
    assert "blocks.0.self_attn.q_proj.base.weight" in keys
    assert "blocks.0.self_attn.q_proj.lora_A" in keys
    assert "blocks.0.self_attn.q_proj.lora_B" in keys


def test_load_pre_lora_state_dict_into_lora_model() -> None:
    """注入前存的 state_dict（例如 last_k 的 best.pt）讀進注入後的模型，輸出要和存檔的模型一樣。"""
    saved_model, x = _make(seed=4)
    saved_model.eval()
    with torch.no_grad():
        expected = saved_model(x)
    saved = {k: v.clone() for k, v in saved_model.state_dict().items()}

    target, _ = _make(seed=5)
    lora.inject_lora(target.blocks, TARGETS, r=4, alpha=8.0)
    _randomize_b(target)
    with pytest.raises(RuntimeError):
        target.load_state_dict(saved)
    target.load_state_dict(lora.adapt_state_dict_for_lora(target, saved))
    target.eval()
    with torch.no_grad():
        got = target(x)
    torch.testing.assert_close(got, expected, rtol=0.0, atol=1e-6)
    assert all(float(p.abs().sum()) == 0.0 for name, p in target.named_parameters() if name.endswith("lora_B"))
    # 已經是 LoRA 鍵名的 state_dict 原樣讀得進去。
    lora_sd = target.state_dict()
    target.load_state_dict(lora.adapt_state_dict_for_lora(target, lora_sd))


def test_layer_filter() -> None:
    model, _ = _make()
    names = lora.inject_lora(model.blocks, TARGETS, r=2, alpha=2.0, layer_filter=lambda n: n.startswith("1."))
    assert names and all(n.startswith("1.") for n in names)
    assert not any(isinstance(m, lora.LoRALinear) for m in model.blocks[0].modules())
    assert isinstance(model.head, nn.Linear) and not isinstance(model.head, lora.LoRALinear)


def test_transformer_encoder_layer_paths() -> None:
    """PatchTransformer 的 block：`out_proj` 靠 `.weight` 屬性，eval 快速路徑也是。"""
    torch.manual_seed(3)
    layer = nn.TransformerEncoderLayer(
        d_model=16,
        nhead=4,
        dim_feedforward=32,
        dropout=0.0,
        activation="gelu",
        batch_first=True,
        norm_first=True,
    )
    original = copy.deepcopy(layer)
    for p in layer.parameters():
        p.requires_grad_(False)
    names = lora.inject_lora(layer, ("out_proj", "linear1", "linear2"), r=4, alpha=8.0, dropout=0.0)
    assert sorted(names) == ["linear1", "linear2", "self_attn.out_proj"]
    _randomize_b(layer, std=0.3)
    merged = copy.deepcopy(layer)
    assert lora.merge_lora(merged) == 3

    x = torch.randn(2, 6, 16)
    layer.train()
    y_train = layer(x)
    layer.eval()
    original.eval()
    merged.eval()
    with torch.no_grad():
        y_eval = layer(x)
        y_merged = merged(x)
        y_original = original(x)
    torch.testing.assert_close(y_train.detach(), y_merged, rtol=1e-4, atol=1e-5)
    torch.testing.assert_close(y_eval, y_merged, rtol=1e-4, atol=1e-5)
    assert float((y_merged - y_original).abs().max()) > 1e-3

    layer.train()
    layer(x).pow(2).mean().backward()
    out_proj = layer.self_attn.out_proj
    assert isinstance(out_proj, lora.LoRALinear)
    assert out_proj.lora_B.grad is not None
    assert float(out_proj.lora_B.grad.abs().sum()) > 0
