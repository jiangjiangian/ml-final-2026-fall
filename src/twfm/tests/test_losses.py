"""`twfm.train.losses` 的測試。

- 完美排序的 listnet、pairwise、ic 損失比亂序、反序小；portfolio 也是。
- pinball、huber 的手算值。
- 梯度是有限值（含分數全部一樣的情況）。
- 一天只有 1 檔時回傳 0、`backward()` 不爆。
- 分天正確：同一天的分數加常數不改變 ic、listnet；把 batch 的列打亂不改變結果。
- `CompositeLoss`：未知名稱丟 `ValueError`、pinball 沒有分位點丟錯、總和等於各項加權。
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

torch = pytest.importorskip("torch")

import twfm.train.losses as losses  # noqa: E402

N_PER_DAY = 40
N_DAYS = 3


def _batch(seed: int = 0) -> tuple[torch.Tensor, torch.Tensor]:
    """三天、每天 40 檔的目標和天編號。目標是標準常態，沒有同分。"""
    g = torch.Generator().manual_seed(seed)
    target = torch.randn(N_DAYS * N_PER_DAY, generator=g)
    day_ids = torch.arange(N_DAYS).repeat_interleave(N_PER_DAY)
    return target, day_ids


def _shuffle_within_days(x: torch.Tensor, day_ids: torch.Tensor, seed: int = 1) -> torch.Tensor:
    """每天內部打亂（不跨天）。"""
    g = torch.Generator().manual_seed(seed)
    out = x.clone()
    for d in torch.unique(day_ids).tolist():
        rows = torch.nonzero(day_ids == d).reshape(-1)
        perm = rows[torch.randperm(rows.numel(), generator=g)]
        out[rows] = x[perm]
    return out


def _rank_losses() -> dict[str, Callable[[torch.Tensor, torch.Tensor, torch.Tensor], torch.Tensor]]:
    return {
        "ic": lambda s, t, d: losses.ic_loss(s, t, d),
        "listnet": lambda s, t, d: losses.listnet_loss(s, t, d, temperature=1.0),
        "pairwise": lambda s, t, d: losses.pairwise_rank_loss(s, t, d, max_pairs_per_day=2048),
        "pairwise_unweighted": lambda s, t, d: losses.pairwise_rank_loss(
            s, t, d, max_pairs_per_day=2048, weight_by_gap=False
        ),
        "portfolio": lambda s, t, d: losses.portfolio_return_loss(s, t, d, tau=1.0),
    }


@pytest.mark.parametrize("name", sorted(_rank_losses()))
def test_correct_order_beats_shuffled_and_reversed(name: str) -> None:
    fn = _rank_losses()[name]
    target, day_ids = _batch()
    # listnet 的最小值在 softmax(scores) = softmax(target)，所以完美的分數就用 target 本身。
    perfect = fn(target.clone(), target, day_ids)
    shuffled = fn(_shuffle_within_days(target, day_ids), target, day_ids)
    reversed_ = fn(-target, target, day_ids)
    assert torch.isfinite(perfect) and torch.isfinite(shuffled) and torch.isfinite(reversed_)
    assert float(perfect) < float(shuffled)
    assert float(perfect) < float(reversed_)


def test_ic_perfect_is_minus_one_and_reversed_is_plus_one() -> None:
    target, day_ids = _batch()
    assert float(losses.ic_loss(target, target, day_ids)) == pytest.approx(-1.0, abs=1e-5)
    assert float(losses.ic_loss(-target, target, day_ids)) == pytest.approx(1.0, abs=1e-5)
    # 正的倍數不改變相關。
    assert float(losses.ic_loss(3.0 * target + 2.0, target, day_ids)) == pytest.approx(-1.0, abs=1e-5)


def test_pinball_hand_computed() -> None:
    pred_q = torch.tensor([[0.0, 1.0], [0.0, 1.0]])
    target = torch.tensor([0.5, 2.0])
    # 第一列：u = [0.5, −0.5] → q=0.1：max(0.05, −0.45) = 0.05；q=0.9：max(−0.45, 0.05) = 0.05。
    # 第二列：u = [2, 1] → q=0.1：0.2；q=0.9：0.9。平均 (0.05 + 0.05 + 0.2 + 0.9) / 4 = 0.3。
    value = losses.pinball_loss(pred_q, target, (0.1, 0.9))
    assert float(value) == pytest.approx(0.3, abs=1e-6)
    one = losses.pinball_loss(torch.tensor([[0.0]]), torch.tensor([0.5]), (0.1,))
    assert float(one) == pytest.approx(0.05, abs=1e-7)


def test_pinball_shape_checks() -> None:
    with pytest.raises(ValueError):
        losses.pinball_loss(torch.zeros(3, 2), torch.zeros(3), (0.1, 0.5, 0.9))
    with pytest.raises(ValueError):
        losses.pinball_loss(torch.zeros(3, 1), torch.zeros(3), ())


def test_huber_hand_computed() -> None:
    pred = torch.zeros(2)
    target = torch.tensor([0.5, 3.0])
    # 0.5 × 0.5² = 0.125；|3| > 1：1 × (3 − 0.5) = 2.5。平均 1.3125。
    assert float(losses.huber_loss(pred, target, delta=1.0)) == pytest.approx(1.3125, abs=1e-6)


def test_huber_ignores_nonfinite_targets() -> None:
    pred = torch.zeros(3)
    target = torch.tensor([0.5, float("nan"), 3.0])
    assert float(losses.huber_loss(pred, target)) == pytest.approx(1.3125, abs=1e-6)


@pytest.mark.parametrize("name", sorted(_rank_losses()))
def test_gradients_are_finite(name: str) -> None:
    fn = _rank_losses()[name]
    target, day_ids = _batch(seed=3)
    g = torch.Generator().manual_seed(5)
    scores = torch.randn(target.numel(), generator=g).requires_grad_(True)
    loss = fn(scores, target, day_ids)
    loss.backward()
    assert scores.grad is not None
    assert torch.isfinite(scores.grad).all()
    assert float(scores.grad.abs().sum()) > 0.0


@pytest.mark.parametrize("name", sorted(_rank_losses()))
def test_constant_scores_do_not_blow_up(name: str) -> None:
    fn = _rank_losses()[name]
    target, day_ids = _batch(seed=4)
    scores = torch.zeros(target.numel(), requires_grad=True)
    loss = fn(scores, target, day_ids)
    assert torch.isfinite(loss)
    loss.backward()
    assert scores.grad is not None
    assert torch.isfinite(scores.grad).all()


def test_pointwise_gradients_are_finite() -> None:
    target, _ = _batch(seed=6)
    pred = torch.zeros(target.numel(), requires_grad=True)
    losses.huber_loss(pred, target).backward()
    assert pred.grad is not None and torch.isfinite(pred.grad).all()
    pred_q = torch.zeros(target.numel(), 3, requires_grad=True)
    losses.pinball_loss(pred_q, target, (0.1, 0.5, 0.9)).backward()
    assert pred_q.grad is not None and torch.isfinite(pred_q.grad).all()


@pytest.mark.parametrize("name", sorted(_rank_losses()))
def test_one_stock_per_day_returns_zero(name: str) -> None:
    fn = _rank_losses()[name]
    scores = torch.tensor([0.3, -1.2, 0.7], requires_grad=True)
    target = torch.tensor([1.0, 2.0, -0.5])
    day_ids = torch.tensor([10, 11, 12])
    loss = fn(scores, target, day_ids)
    assert loss.dim() == 0
    assert float(loss) == 0.0
    loss.backward()
    assert scores.grad is not None
    assert torch.equal(scores.grad, torch.zeros_like(scores))


def test_empty_batch_returns_zero() -> None:
    scores = torch.zeros(0, requires_grad=True)
    target = torch.zeros(0)
    day_ids = torch.zeros(0, dtype=torch.long)
    for fn in _rank_losses().values():
        loss = fn(scores, target, day_ids)
        assert float(loss) == 0.0
        loss.backward()


def test_days_with_one_stock_are_skipped_not_averaged() -> None:
    """一天 1 檔的天不進平均：加一天 1 檔，ic 不變。"""
    target, day_ids = _batch(seed=7)
    g = torch.Generator().manual_seed(8)
    scores = torch.randn(target.numel(), generator=g)
    base = losses.ic_loss(scores, target, day_ids)
    scores2 = torch.cat([scores, torch.tensor([5.0])])
    target2 = torch.cat([target, torch.tensor([1.0])])
    day2 = torch.cat([day_ids, torch.tensor([99])])
    assert float(losses.ic_loss(scores2, target2, day2)) == pytest.approx(float(base), abs=1e-6)


@pytest.mark.parametrize("name", ["ic", "listnet"])
def test_per_day_shift_invariance(name: str) -> None:
    """同一天的分數加同一個常數（每天不同），ic、listnet 不變。分天錯了這裡會抓到。"""
    fn = _rank_losses()[name]
    target, day_ids = _batch(seed=9)
    g = torch.Generator().manual_seed(10)
    scores = torch.randn(target.numel(), generator=g)
    shift = torch.tensor([5.0, -3.0, 11.0])[day_ids]
    assert float(fn(scores + shift, target, day_ids)) == pytest.approx(float(fn(scores, target, day_ids)), abs=1e-5)


@pytest.mark.parametrize("name", sorted(_rank_losses()))
def test_row_order_does_not_matter(name: str) -> None:
    """batch 的列整個打亂（同一天的列不再相鄰），結果一樣。配對數不超過上限，pairwise 用全部配對、沒有抽樣。"""
    fn = _rank_losses()[name]
    target, day_ids = _batch(seed=11)
    g = torch.Generator().manual_seed(12)
    scores = torch.randn(target.numel(), generator=g)
    perm = torch.randperm(target.numel(), generator=g)
    a = fn(scores, target, day_ids)
    b = fn(scores[perm], target[perm], day_ids[perm])
    assert float(b) == pytest.approx(float(a), abs=1e-5)


def test_pairwise_sampling_is_reproducible_and_ordered() -> None:
    """配對數超過上限時抽樣：同一個 generator 種子結果相同，完美排序仍比反序小。"""
    g0 = torch.Generator().manual_seed(13)
    target = torch.randn(200, generator=g0)
    day_ids = torch.zeros(200, dtype=torch.long)
    kwargs = {"max_pairs_per_day": 256}
    a = losses.pairwise_rank_loss(target, target, day_ids, generator=torch.Generator().manual_seed(1), **kwargs)
    b = losses.pairwise_rank_loss(target, target, day_ids, generator=torch.Generator().manual_seed(1), **kwargs)
    assert float(a) == float(b)
    worst = losses.pairwise_rank_loss(-target, target, day_ids, generator=torch.Generator().manual_seed(1), **kwargs)
    assert float(a) < math.log(2.0) < float(worst)


def test_portfolio_sign() -> None:
    """分數和報酬同向時損失是負的（賺錢），反向時是正的。"""
    target, day_ids = _batch(seed=14)
    r = 0.02 * target
    good = losses.portfolio_return_loss(r * 50.0, r, day_ids, tau=1.0)
    bad = losses.portfolio_return_loss(-r * 50.0, r, day_ids, tau=1.0)
    assert float(good) < 0.0 < float(bad)


def test_listnet_minimum_at_matching_softmax() -> None:
    target, day_ids = _batch(seed=15)
    best = losses.listnet_loss(target, target, day_ids, temperature=1.0)
    scaled = losses.listnet_loss(3.0 * target, target, day_ids, temperature=1.0)
    assert float(best) < float(scaled)
    # 溫度 T 時最小值在 scores = target / T。
    t2 = losses.listnet_loss(target / 2.0, target, day_ids, temperature=2.0)
    t2_off = losses.listnet_loss(target, target, day_ids, temperature=2.0)
    assert float(t2) < float(t2_off)


def _fake_out_and_batch(seed: int = 16, n_quantiles: int = 0) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor]]:
    target, day_ids = _batch(seed=seed)
    g = torch.Generator().manual_seed(seed + 100)
    score = torch.randn(target.numel(), generator=g, requires_grad=True)
    out: dict[str, torch.Tensor] = {"score": score}
    if n_quantiles:
        base = torch.randn(target.numel(), 1, generator=g)
        steps = torch.rand(target.numel(), n_quantiles, generator=g).cumsum(dim=1)
        out["quantiles"] = (base + steps).requires_grad_(True)
    batch = {
        "target_z": target,
        "label_r": 0.02 * target,
        "day_id": day_ids,
    }
    return out, batch


def test_composite_default_weights_match_manual_sum() -> None:
    out, batch = _fake_out_and_batch()
    loss_fn = losses.CompositeLoss({"huber": 1.0, "ic": 0.2}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    total, parts = loss_fn(out, batch)
    manual = losses.huber_loss(out["score"], batch["target_z"]) + 0.2 * losses.ic_loss(
        out["score"], batch["target_z"], batch["day_id"]
    )
    assert float(total) == pytest.approx(float(manual), abs=1e-6)
    assert set(parts) == {"huber", "ic", "total"}
    assert parts["total"] == pytest.approx(float(total), abs=1e-6)
    total.backward()
    assert out["score"].grad is not None and torch.isfinite(out["score"].grad).all()


def test_composite_all_losses_with_quantiles() -> None:
    out, batch = _fake_out_and_batch(n_quantiles=3)
    weights = {
        "huber": 1.0,
        "pinball": 0.5,
        "ic": 0.2,
        "listnet": 0.1,
        "pairwise_rank": 0.1,
        "portfolio_return": 0.1,
    }
    loss_fn = losses.CompositeLoss(weights, huber_delta=1.0, listnet_temperature=1.0, quantiles=(0.1, 0.5, 0.9))
    total, parts = loss_fn(out, batch)
    assert torch.isfinite(total)
    assert set(parts) == {"huber", "pinball", "ic", "listnet", "pairwise", "portfolio", "total"}
    total.backward()
    assert torch.isfinite(out["score"].grad).all()
    assert torch.isfinite(out["quantiles"].grad).all()


def test_composite_zero_weight_is_skipped() -> None:
    out, batch = _fake_out_and_batch()
    loss_fn = losses.CompositeLoss({"huber": 1.0, "listnet": 0.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    _, parts = loss_fn(out, batch)
    assert "listnet" not in parts


def test_composite_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        losses.CompositeLoss({"huber": 1.0, "mse": 1.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())


def test_composite_pinball_needs_quantiles() -> None:
    with pytest.raises(ValueError):
        losses.CompositeLoss({"pinball": 1.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    loss_fn = losses.CompositeLoss({"pinball": 1.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=(0.5,))
    out, batch = _fake_out_and_batch()
    with pytest.raises(ValueError):
        loss_fn(out, batch)


def test_composite_rejects_bad_weights() -> None:
    with pytest.raises(ValueError):
        losses.CompositeLoss({"huber": -1.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    with pytest.raises(ValueError):
        losses.CompositeLoss({"huber": 0.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    with pytest.raises(ValueError):
        losses.CompositeLoss({"pairwise": 1.0, "pairwise_rank": 1.0}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())


def test_composite_casts_half_scores_to_float32() -> None:
    out, batch = _fake_out_and_batch()
    half_out = {"score": out["score"].detach().half().requires_grad_(True)}
    loss_fn = losses.CompositeLoss({"huber": 1.0, "ic": 0.2}, huber_delta=1.0, listnet_temperature=1.0, quantiles=())
    total, _ = loss_fn(half_out, batch)
    assert total.dtype == torch.float32
    total.backward()
    assert half_out["score"].grad is not None and torch.isfinite(half_out["score"].grad.float()).all()
