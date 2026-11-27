"""協變量 head：主幹的表示加個股協變量，再用市場協變量做 FiLM 調變，輸出排名分數。

為什麼用 FiLM（Perez et al., 2018）：美股隔夜這類全市場的已知輸入，同一天每檔都一樣，
直接加進去只會讓當天所有分數一起平移，橫斷面排名不變。
讓它和個股表示相乘（`h · (1 + gamma) + beta`），才會依個股的特性改變排名
（例如高 beta 的股票對美股隔夜報酬更敏感）。

協變量只進 head、不進主幹：主幹只吃預訓練時看過的 K 棒，所以可以先凍結主幹、快取 embedding，
便宜地試很多協變量組合。
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class FiLMCovariateHead(nn.Module):
    """`h = GELU(Linear([repr, stock_cov]))` → `LayerNorm` → FiLM（市場協變量）→ `Linear → GELU → Dropout` → 分數。

    - FiLM 的 MLP：`Linear(n_market_cov, hidden) → GELU → Linear(hidden, 2·hidden)` 得 `gamma, beta` `[B, hidden]`。
      最後一層初始為 0，所以剛開始 `gamma = beta = 0`，等於沒有調變，訓練時再慢慢學。
    - `n_market_cov == 0` 時跳過 FiLM（LayerNorm 照做）。`n_stock_cov == 0` 時只用主幹的表示。
    - `n_quantiles > 0` 時另一個 `Linear(n_quantiles)` 接在同一層之後，
      第一個分位數是原始輸出，之後每個加上 `softplus` 的累加（`torch.cumsum`），保證遞增。
    - 輸出一律轉成 fp32（AMP 裡也是），損失函數不用再管 dtype。
    """

    def __init__(
        self,
        d_model: int,
        n_stock_cov: int,
        n_market_cov: int,
        hidden: int,
        dropout: float,
        n_quantiles: int = 0,
    ) -> None:
        super().__init__()
        if d_model < 1 or hidden < 1:
            raise ValueError("d_model、hidden 至少 1")
        if n_stock_cov < 0 or n_market_cov < 0 or n_quantiles < 0:
            raise ValueError("n_stock_cov、n_market_cov、n_quantiles 不能是負的")
        if not (0.0 <= dropout < 1.0):
            raise ValueError(f"dropout 要在 [0, 1)，拿到 {dropout}")
        self.d_model = int(d_model)
        self.n_stock_cov = int(n_stock_cov)
        self.n_market_cov = int(n_market_cov)
        self.hidden = int(hidden)
        self.n_quantiles = int(n_quantiles)

        self.input_proj = nn.Linear(self.d_model + self.n_stock_cov, self.hidden)
        self.act = nn.GELU()
        self.norm = nn.LayerNorm(self.hidden)
        self.film: nn.Sequential | None
        if self.n_market_cov > 0:
            self.film = nn.Sequential(
                nn.Linear(self.n_market_cov, self.hidden),
                nn.GELU(),
                nn.Linear(self.hidden, 2 * self.hidden),
            )
            last = self.film[2]
            assert isinstance(last, nn.Linear)
            nn.init.zeros_(last.weight)
            nn.init.zeros_(last.bias)
        else:
            self.film = None
        self.mid = nn.Linear(self.hidden, self.hidden)
        self.dropout = nn.Dropout(float(dropout))
        self.score_out = nn.Linear(self.hidden, 1)
        self.quantile_out: nn.Linear | None
        if self.n_quantiles > 0:
            self.quantile_out = nn.Linear(self.hidden, self.n_quantiles)
        else:
            self.quantile_out = None

    @staticmethod
    def _check_cov(cov: torch.Tensor | None, batch: int, width: int, name: str, ref: torch.Tensor) -> torch.Tensor:
        """檢查協變量形狀 `[B, width]`。width 是 0 時，None 或空的張量都回傳 `[B, 0]`。"""
        if width == 0 and (cov is None or cov.numel() == 0):
            return ref.new_zeros((batch, 0))
        if cov is None:
            raise ValueError(f"head 設定 {name} 有 {width} 欄，但沒有給 {name}")
        if cov.dim() != 2 or cov.shape[0] != batch or cov.shape[1] != width:
            raise ValueError(f"{name} 要是 [{batch}, {width}]，拿到 {tuple(cov.shape)}")
        return cov.to(device=ref.device, dtype=ref.dtype)

    def forward(
        self,
        repr: torch.Tensor,  # noqa: A002  名稱照規格
        stock_cov: torch.Tensor | None = None,
        market_cov: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """回傳 `{"score": [B]}`，有分位數頭時另有 `"quantiles": [B, Q]`，都是 fp32。"""
        if repr.dim() != 2 or repr.shape[1] != self.d_model:
            raise ValueError(f"repr 要是 [B, {self.d_model}]，拿到 {tuple(repr.shape)}")
        rep = repr.float()
        batch = rep.shape[0]
        sc = self._check_cov(stock_cov, batch, self.n_stock_cov, "stock_cov", rep)
        x = torch.cat([rep, sc], dim=-1) if self.n_stock_cov > 0 else rep
        h = self.norm(self.act(self.input_proj(x)))
        if self.film is not None:
            mc = self._check_cov(market_cov, batch, self.n_market_cov, "market_cov", rep)
            gamma, beta = self.film(mc).chunk(2, dim=-1)
            h = h * (1.0 + gamma) + beta
        z = self.dropout(self.act(self.mid(h)))
        out: dict[str, torch.Tensor] = {"score": self.score_out(z).squeeze(-1).float()}
        if self.quantile_out is not None:
            raw = self.quantile_out(z).float()
            first = raw[:, :1]
            if self.n_quantiles > 1:
                rest = first + torch.cumsum(F.softplus(raw[:, 1:]), dim=-1)
                out["quantiles"] = torch.cat([first, rest], dim=-1)
            else:
                out["quantiles"] = first
        return out
