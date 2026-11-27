"""損失函數。每個函式都回傳純量 `torch.Tensor`。

共同規則：
- 一律在 float32 算。AMP 下 head 可能輸出 fp16，進來先轉成 float32。
- 排序類損失（`ic_loss`、`listnet_loss`、`pairwise_rank_loss`、`portfolio_return_loss`）按 `day_ids` 分天，
  每天各算一次再平均。一天至少要 2 檔才算，不夠的那天跳過。
  整個 batch 都跳過時回傳 `0 * scores.sum()`，計算圖還在，`backward()` 不會出錯，梯度是 0。
- 目標或報酬是 NaN、inf 的列先丟掉，不讓一個壞值把整個 batch 變成 NaN。
- 同一天的列不用排在一起，分組只看 `day_ids` 的值。

`CompositeLoss` 把幾個損失加權相加，名稱：
`huber`、`pinball`、`ic`、`listnet`、`pairwise`（別名 `pairwise_rank`）、`portfolio`（別名 `portfolio_return`）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import torch
import torch.nn.functional as F
from torch import nn

# 名稱（含別名）對正式名稱。
LOSS_ALIASES: dict[str, str] = {
    "huber": "huber",
    "pinball": "pinball",
    "ic": "ic",
    "listnet": "listnet",
    "pairwise": "pairwise",
    "pairwise_rank": "pairwise",
    "portfolio": "portfolio",
    "portfolio_return": "portfolio",
}
LOSS_NAMES: tuple[str, ...] = ("huber", "pinball", "ic", "listnet", "pairwise", "portfolio")

# Pearson 相關的分母用 sqrt(var + eps)，分數全部一樣時梯度仍是有限值。
_CORR_EPS: float = 1e-8
# 一天的目標變異數小於這個值（例如全部是 0）就跳過那天。
_TARGET_VAR_MIN: float = 1e-12
# portfolio 的權重絕對值總和小於這個值（分數幾乎全部一樣）就跳過那天，避免除以接近 0 的數。
_WEIGHT_SUM_MIN: float = 1e-6


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _flat_float(x: torch.Tensor, name: str) -> torch.Tensor:
    """攤平成一維 float32。"""
    if not isinstance(x, torch.Tensor):
        raise TypeError(f"{name} 要是 torch.Tensor，拿到 {type(x).__name__}")
    return x.reshape(-1).float()


def _check_same_length(n: int, **tensors: torch.Tensor) -> None:
    for name, t in tensors.items():
        if t.numel() != n:
            raise ValueError(f"{name} 有 {t.numel()} 個元素，scores 有 {n} 個")


def _empty_loss(scores: torch.Tensor) -> torch.Tensor:
    """整個 batch 都跳過時的回傳值：0，但保留計算圖。"""
    return 0.0 * scores.sum()


def _day_groups(
    day_ids: torch.Tensor,
    valid: torch.Tensor | None = None,
    min_size: int = 2,
) -> list[torch.Tensor]:
    """把列按天分組，回傳每天的列號（`int64`，在原本 batch 裡的位置）。

    - `valid` 是 bool 遮罩，False 的列不進任何一組。
    - 少於 `min_size` 列的天不回傳。
    - 天的順序照 `day_ids` 由小到大，每天裡的列照原本的順序。
    """
    d = day_ids.reshape(-1)
    rows = torch.arange(d.numel(), device=d.device)
    if valid is not None:
        keep = valid.reshape(-1).to(device=d.device, dtype=torch.bool)
        rows = rows[keep]
        d = d[keep]
    if rows.numel() == 0:
        return []
    _, inv, counts = torch.unique(d, sorted=True, return_inverse=True, return_counts=True)
    order = torch.sort(inv, stable=True).indices
    groups = torch.split(rows[order], counts.tolist())
    return [g for g in groups if g.numel() >= int(min_size)]


def _mean_of(values: list[torch.Tensor], scores: torch.Tensor) -> torch.Tensor:
    """每天的損失取平均；沒有任何一天時回傳保留計算圖的 0。"""
    if not values:
        return _empty_loss(scores)
    return torch.stack(values).mean()


# ---------------------------------------------------------------------------
# 逐點損失
# ---------------------------------------------------------------------------


def huber_loss(pred: torch.Tensor, target_z: torch.Tensor, delta: float = 1.0) -> torch.Tensor:
    """Huber 損失（平均）。`|e| < delta` 時 `0.5 e²`，否則 `delta (|e| − 0.5 delta)`。

    目標是每天 z-score 後的報酬，肥尾的大報酬只用線性懲罰。目標非有限值的列不算。
    """
    if delta <= 0:
        raise ValueError(f"delta 要大於 0，拿到 {delta}")
    p = _flat_float(pred, "pred")
    t = _flat_float(target_z, "target_z").to(p.device)
    _check_same_length(p.numel(), target_z=t)
    ok = torch.isfinite(t)
    if p.numel() == 0 or not bool(ok.any()):
        return _empty_loss(p)
    return F.huber_loss(p[ok], t[ok], reduction="mean", delta=float(delta))


def pinball_loss(pred_q: torch.Tensor, target_z: torch.Tensor, quantiles: Sequence[float]) -> torch.Tensor:
    """分位數損失（pinball），對所有列和所有分位點取平均。

    `pred_q [B, Q]`、`target_z [B]`。`u = y − ŷ_q`，損失 `max(q · u, (q − 1) · u)`。
    例子：q = 0.1、ŷ = 0、y = 0.5 → 0.05；q = 0.9、ŷ = 1、y = 2 → 0.9。
    """
    qs = [float(q) for q in quantiles]
    if not qs:
        raise ValueError("quantiles 不能是空的")
    if any(not (0.0 < q < 1.0) for q in qs):
        raise ValueError("quantiles 每個都要在 0 和 1 之間")
    if not isinstance(pred_q, torch.Tensor):
        raise TypeError(f"pred_q 要是 torch.Tensor，拿到 {type(pred_q).__name__}")
    pq = pred_q.float()
    if pq.dim() != 2 or pq.shape[1] != len(qs):
        raise ValueError(f"pred_q 要是 [B, {len(qs)}]，拿到 {list(pq.shape)}")
    t = _flat_float(target_z, "target_z").to(pq.device)
    if t.numel() != pq.shape[0]:
        raise ValueError(f"target_z 有 {t.numel()} 個元素，pred_q 有 {pq.shape[0]} 列")
    ok = torch.isfinite(t)
    if pq.shape[0] == 0 or not bool(ok.any()):
        return _empty_loss(pq)
    q = torch.tensor(qs, dtype=torch.float32, device=pq.device).unsqueeze(0)
    u = t[ok].unsqueeze(1) - pq[ok]
    return torch.maximum(q * u, (q - 1.0) * u).mean()


# ---------------------------------------------------------------------------
# 排序類損失（每天一組）
# ---------------------------------------------------------------------------


def ic_loss(scores: torch.Tensor, target: torch.Tensor, day_ids: torch.Tensor) -> torch.Tensor:
    """每天分數和目標的 Pearson 相關取負，再對天平均（可微）。

    完美同向是 −1，完全反向是 +1。目標當天全部一樣（變異數約 0）時跳過那天。
    分母用 `sqrt(var + eps)`，分數全部一樣時梯度仍是有限值。
    對同一天的分數加常數或乘正數，損失不變。
    """
    s_all = _flat_float(scores, "scores")
    t_all = _flat_float(target, "target").to(s_all.device)
    _check_same_length(s_all.numel(), target=t_all, day_ids=day_ids.reshape(-1))
    per_day: list[torch.Tensor] = []
    for rows in _day_groups(day_ids.to(s_all.device), valid=torch.isfinite(t_all)):
        s = s_all[rows]
        t = t_all[rows]
        tc = t - t.mean()
        var_t = (tc * tc).mean()
        if float(var_t.detach()) < _TARGET_VAR_MIN:
            continue
        sc = s - s.mean()
        var_s = (sc * sc).mean()
        cov = (sc * tc).mean()
        corr = cov / (torch.sqrt(var_s + _CORR_EPS) * torch.sqrt(var_t + _CORR_EPS))
        per_day.append(-corr)
    return _mean_of(per_day, s_all)


def listnet_loss(
    scores: torch.Tensor,
    target: torch.Tensor,
    day_ids: torch.Tensor,
    temperature: float = 1.0,
) -> torch.Tensor:
    """ListNet：每天 `softmax(target / T)` 對 `log_softmax(scores)` 的交叉熵，再對天平均。

    最小值在 `softmax(scores) = softmax(target / T)`（例如 `scores = target / T`），
    不只是排序對就最小。對同一天的分數加常數，損失不變。
    """
    if temperature <= 0:
        raise ValueError(f"temperature 要大於 0，拿到 {temperature}")
    s_all = _flat_float(scores, "scores")
    t_all = _flat_float(target, "target").to(s_all.device)
    _check_same_length(s_all.numel(), target=t_all, day_ids=day_ids.reshape(-1))
    per_day: list[torch.Tensor] = []
    for rows in _day_groups(day_ids.to(s_all.device), valid=torch.isfinite(t_all)):
        p = torch.softmax(t_all[rows] / float(temperature), dim=0)
        log_q = torch.log_softmax(s_all[rows], dim=0)
        per_day.append(-(p * log_q).sum())
    return _mean_of(per_day, s_all)


def _pair_indices(
    n: int,
    max_pairs: int,
    device: torch.device,
    generator: torch.Generator | None,
) -> tuple[torch.Tensor, torch.Tensor]:
    """一天 n 檔的配對 `(a, b)`，`a ≠ b`。

    全部配對數 `n(n − 1)/2` 不超過 `max_pairs` 時用全部（每對一次，結果固定）；
    超過時抽 `max_pairs` 對（可重複）。抽樣在 `generator` 所在的裝置做，沒給就用 CPU 的全域亂數，
    抽完再搬到 `device`（CUDA 張量配 CPU generator 會出錯，所以不直接在 CUDA 上抽）。
    """
    total = n * (n - 1) // 2
    if total <= max_pairs:
        idx = torch.triu_indices(n, n, offset=1, device=device)
        return idx[0], idx[1]
    gen_device = generator.device if generator is not None else torch.device("cpu")
    a = torch.randint(0, n, (max_pairs,), generator=generator, device=gen_device)
    b = torch.randint(0, n - 1, (max_pairs,), generator=generator, device=gen_device)
    b = b + (b >= a).to(b.dtype)
    return a.to(device), b.to(device)


def pairwise_rank_loss(
    scores: torch.Tensor,
    target: torch.Tensor,
    day_ids: torch.Tensor,
    max_pairs_per_day: int = 2048,
    weight_by_gap: bool = True,
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """每天的配對排序損失（RankNet 型）。

    每對 `softplus(−sign(t_a − t_b) · (s_a − s_b))`：分數方向和目標一樣時小，相反時大。
    `weight_by_gap=True` 時每對的權重是 `|t_a − t_b|`（比賽分數 (2p−1)·r 對報酬差大的配對更在意），
    否則每對權重 1。目標相同的配對權重 0。每天是加權平均（除以權重總和），再對天平均。
    權重總和是 0 的天（全部同分）跳過。
    """
    if max_pairs_per_day < 1:
        raise ValueError(f"max_pairs_per_day 至少 1，拿到 {max_pairs_per_day}")
    s_all = _flat_float(scores, "scores")
    t_all = _flat_float(target, "target").to(s_all.device)
    _check_same_length(s_all.numel(), target=t_all, day_ids=day_ids.reshape(-1))
    per_day: list[torch.Tensor] = []
    for rows in _day_groups(day_ids.to(s_all.device), valid=torch.isfinite(t_all)):
        s = s_all[rows]
        t = t_all[rows]
        a, b = _pair_indices(int(rows.numel()), int(max_pairs_per_day), s.device, generator)
        dt = t[a] - t[b]
        gap = dt.abs()
        w = gap if weight_by_gap else (gap > 0).to(s.dtype)
        w_sum = w.sum()
        if float(w_sum.detach()) <= 0.0:
            continue
        pair_loss = F.softplus(-torch.sign(dt) * (s[a] - s[b]))
        per_day.append((w * pair_loss).sum() / w_sum)
    return _mean_of(per_day, s_all)


def portfolio_return_loss(
    scores: torch.Tensor,
    label_r: torch.Tensor,
    day_ids: torch.Tensor,
    tau: float = 1.0,
) -> torch.Tensor:
    """可微地近似比賽分數：每天的多空組合報酬取負，再對天平均。

    每天 `w = tanh((s − median(s)) / tau)`，`w /= Σ|w|`（總曝險 1），
    損失 = `−Σ w · (r − mean r)`。減掉當天平均報酬，只看橫斷面，不看大盤方向。
    中位數 `detach`（只當門檻）。分數幾乎全部一樣（`Σ|w|` 約 0）的天跳過。
    `tau` 越小越接近「前一半 +、後一半 −」的硬切。
    """
    if tau <= 0:
        raise ValueError(f"tau 要大於 0，拿到 {tau}")
    s_all = _flat_float(scores, "scores")
    r_all = _flat_float(label_r, "label_r").to(s_all.device)
    _check_same_length(s_all.numel(), label_r=r_all, day_ids=day_ids.reshape(-1))
    per_day: list[torch.Tensor] = []
    for rows in _day_groups(day_ids.to(s_all.device), valid=torch.isfinite(r_all)):
        s = s_all[rows]
        r = r_all[rows]
        med = torch.quantile(s.detach(), 0.5)
        w = torch.tanh((s - med) / float(tau))
        w_abs_sum = w.abs().sum()
        if float(w_abs_sum.detach()) < _WEIGHT_SUM_MIN:
            continue
        w = w / w_abs_sum
        per_day.append(-(w * (r - r.mean())).sum())
    return _mean_of(per_day, s_all)


# ---------------------------------------------------------------------------
# 組合損失
# ---------------------------------------------------------------------------


def _batch_day_ids(batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
    """batch 的天編號。`PanelWindowDataset` 的鍵是 `day_id`，也接受 `day_ids`。"""
    if "day_id" in batch:
        return batch["day_id"]
    if "day_ids" in batch:
        return batch["day_ids"]
    raise KeyError("batch 裡沒有 day_id（排序類損失要用）")


class CompositeLoss(nn.Module):
    """幾個損失加權相加。

    `weights` 是名稱對權重，例如預設 `{"huber": 1.0, "ic": 0.2}`。名稱見 `LOSS_ALIASES`。
    權重 0 的損失不算；權重不能是負的；未知的名稱丟 `ValueError`。

    - `huber`、`pinball`、`ic`、`listnet`、`pairwise` 用 `batch["target_z"]`（每天 z-score 後的目標）。
    - `portfolio` 用 `batch["label_r"]`（原始報酬），比較貼近比賽分數。
    - `pinball` 要 `out["quantiles"] [B, Q]`，`Q = len(quantiles)`；`quantiles` 是空的就不能用 `pinball`。

    `forward(out, batch)` 回傳 `(總損失, 各項)`。各項是 `{名稱: 未加權的值}` 加 `"total"`，都是 Python float。
    """

    def __init__(
        self,
        weights: Mapping[str, float],
        huber_delta: float = 1.0,
        listnet_temperature: float = 1.0,
        quantiles: Sequence[float] = (),
        pairwise_max_pairs: int = 2048,
        pairwise_weight_by_gap: bool = True,
        portfolio_tau: float = 1.0,
    ) -> None:
        super().__init__()
        if not isinstance(weights, Mapping):
            raise TypeError(f"weights 要是 dict，拿到 {type(weights).__name__}")
        resolved: dict[str, float] = {}
        for raw_name, raw_w in weights.items():
            name = LOSS_ALIASES.get(str(raw_name))
            if name is None:
                raise ValueError(f"未知的損失名稱 {raw_name!r}，可用的有 {sorted(LOSS_ALIASES)}")
            w = float(raw_w)
            if not (w >= 0.0):
                raise ValueError(f"損失 {raw_name!r} 的權重要 ≥ 0，拿到 {raw_w}")
            if name in resolved:
                raise ValueError(f"損失 {name!r} 重複出現（可能是名稱和別名都寫了）")
            resolved[name] = w
        self.weights: dict[str, float] = {k: v for k, v in resolved.items() if v > 0.0}
        if not self.weights:
            raise ValueError("至少要有一個權重大於 0 的損失")
        if huber_delta <= 0:
            raise ValueError(f"huber_delta 要大於 0，拿到 {huber_delta}")
        if listnet_temperature <= 0:
            raise ValueError(f"listnet_temperature 要大於 0，拿到 {listnet_temperature}")
        if portfolio_tau <= 0:
            raise ValueError(f"portfolio_tau 要大於 0，拿到 {portfolio_tau}")
        self.huber_delta = float(huber_delta)
        self.listnet_temperature = float(listnet_temperature)
        self.quantiles: tuple[float, ...] = tuple(float(q) for q in quantiles)
        self.pairwise_max_pairs = int(pairwise_max_pairs)
        self.pairwise_weight_by_gap = bool(pairwise_weight_by_gap)
        self.portfolio_tau = float(portfolio_tau)
        if "pinball" in self.weights and not self.quantiles:
            raise ValueError("用 pinball 損失要給 quantiles（模型也要有分位數頭）")

    def extra_repr(self) -> str:
        return f"weights={self.weights}"

    def _one(self, name: str, out: Mapping[str, torch.Tensor], batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        score = out["score"].float().reshape(-1)
        dev = score.device
        if name == "huber":
            return huber_loss(score, batch["target_z"].to(dev), delta=self.huber_delta)
        if name == "pinball":
            if "quantiles" not in out:
                raise ValueError("pinball 損失要 out['quantiles']，模型沒有輸出分位數（ModelConfig.quantiles 是空的？）")
            return pinball_loss(out["quantiles"], batch["target_z"].to(dev), self.quantiles)
        day_ids = _batch_day_ids(batch).to(dev)
        if name == "ic":
            return ic_loss(score, batch["target_z"].to(dev), day_ids)
        if name == "listnet":
            return listnet_loss(score, batch["target_z"].to(dev), day_ids, temperature=self.listnet_temperature)
        if name == "pairwise":
            return pairwise_rank_loss(
                score,
                batch["target_z"].to(dev),
                day_ids,
                max_pairs_per_day=self.pairwise_max_pairs,
                weight_by_gap=self.pairwise_weight_by_gap,
            )
        if name == "portfolio":
            return portfolio_return_loss(score, batch["label_r"].to(dev), day_ids, tau=self.portfolio_tau)
        raise ValueError(f"未知的損失名稱 {name!r}")

    def forward(
        self,
        out: Mapping[str, torch.Tensor],
        batch: Mapping[str, torch.Tensor],
    ) -> tuple[torch.Tensor, dict[str, float]]:
        if "score" not in out:
            raise KeyError("out 裡沒有 score")
        total: torch.Tensor | None = None
        parts: dict[str, float] = {}
        for name, w in self.weights.items():
            value = self._one(name, out, batch)
            parts[name] = float(value.detach())
            term = value * w
            total = term if total is None else total + term
        assert total is not None
        parts["total"] = float(total.detach())
        return total, parts
