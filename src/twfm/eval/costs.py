"""台股交易成本（不 import torch）。

規則（`CostConfig` 的預設值）：
- 手續費：買賣各收一次，費率 0.1425% 乘券商折扣 `commission_discount`。
  `capital_ntd` 有給時，每筆委託最低收 NT$20（`min_fee_ntd`）。沒給本金時只用費率，不套最低手續費。
- 證交稅：只在賣出那邊收。一般 0.3%；現股當沖 0.15%（當沖減半從 2017-04-28 起，適用到 2027-12-31；
  有給日期而且在這段期間以外時用 0.3%）；ETF 0.1%（不論是不是當沖）。
- 現股當沖 2014-01-06 才開放（先買後賣），先賣後買 2014-06-30 才開放。更早的日期，做空那一腳只能用
  融資融券的資券相抵，這裡不另外處理，回測 2014 年以前的當沖要知道這點。
- 滑價：每邊 `slippage_bps` 個基點，買賣都算。

開盤買、收盤賣（做多）和開盤賣、收盤買（做空，用現股當沖先賣後買）都是一次當沖：
付一買一賣兩次手續費和一次當沖證交稅。

沒有算的：融券的借券費和融券手續費、手續費和稅金的元以下捨去、零股的最低手續費。
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from ..config import CostConfig

DAYTRADE_TAX_CUT_START: pd.Timestamp = pd.Timestamp("2017-04-28")
"""現股當沖證交稅減半的第一天（含）。之前的當沖用一般稅率。"""

DAYTRADE_TAX_CUT_END: pd.Timestamp = pd.Timestamp("2027-12-31")
"""現股當沖證交稅減半的最後一天（含）。之後的日期用一般稅率。"""

_DAYTRADE_TAX_CUT_START = np.datetime64("2017-04-28T00:00:00", "ns")
_DAYTRADE_TAX_CUT_END_EXCLUSIVE = np.datetime64("2028-01-01T00:00:00", "ns")
SIDES: tuple[str, ...] = ("buy", "sell")


def _check_side(side: str) -> None:
    if side not in SIDES:
        raise ValueError(f"side 要是 {SIDES} 之一，拿到 {side!r}")


def _scalar_date(date: Any) -> pd.Timestamp | None:
    """單一日期轉成無時區的 Timestamp，缺值回傳 None。有時區的先轉成台北時間。"""
    ts = pd.Timestamp(date)
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Taipei").tz_localize(None)
    return ts


class TaiwanCostModel:
    """台股交易成本模型。

    比率類的方法（`round_trip_rate`、`trade_cost_fraction`）回傳「成本 ÷ 成交金額」或「成本 ÷ 本金」，
    回測用；`order_cost` 回傳單筆委託的新台幣金額。
    """

    def __init__(self, cfg: CostConfig | None = None) -> None:
        self.cfg: CostConfig = cfg if cfg is not None else CostConfig()

    def __repr__(self) -> str:
        return f"TaiwanCostModel({self.cfg!r})"

    @property
    def commission_rate_effective(self) -> float:
        """實收手續費率 = `commission_rate × commission_discount`（每邊）。"""
        return float(self.cfg.commission_rate) * float(self.cfg.commission_discount)

    @property
    def slippage_rate(self) -> float:
        """每邊的滑價比率 = `slippage_bps / 1e4`。"""
        return float(self.cfg.slippage_bps) / 1e4

    def with_discount(self, discount: float) -> TaiwanCostModel:
        """回傳只改手續費折扣的新模型（報告列 1.0、0.6、0.28 用）。"""
        return TaiwanCostModel(dataclasses.replace(self.cfg, commission_discount=float(discount)))

    def daytrade_cut_in_force(self, date: Any = None) -> bool:
        """當沖證交稅減半在這天有沒有效：2017-04-28 到 2027-12-31（都含）。

        `date` 是 None 或缺值時當作有效（現行規定）。
        """
        if date is None:
            return True
        ts = _scalar_date(date)
        if ts is None:
            return True
        return bool(DAYTRADE_TAX_CUT_START <= ts < DAYTRADE_TAX_CUT_END + pd.Timedelta(days=1))

    def sell_tax(self, daytrade: bool, is_etf: bool = False, *, date: Any = None) -> float:
        """賣出那邊的證交稅率：ETF 0.1%；當沖 0.15%；一般 0.3%。

        `date` 早於 2017-04-28 或晚於 2027-12-31 時，當沖也用一般稅率。不給 `date` 就照現行規定。
        """
        if is_etf:
            return float(self.cfg.etf_sell_tax_rate)
        if daytrade and self.daytrade_cut_in_force(date):
            return float(self.cfg.daytrade_sell_tax_rate)
        return float(self.cfg.sell_tax_rate)

    def round_trip_rate(self, daytrade: bool = True, is_etf: bool = False, *, date: Any = None) -> float:
        """一買一賣的總成本率 = `2 × 手續費 + 賣出稅 + 2 × slippage_bps / 1e4`（相對成交金額）。

        開盤買、收盤賣（做多）和開盤賣、收盤買（做空，用現股當沖先賣後買）都是一次當沖，
        各付一買一賣的手續費和一次當沖證交稅，所以兩個方向的來回成本一樣。
        這是比率，不含最低手續費；要算最低手續費用 `order_cost` 或 `trade_cost_fraction`。

        例：折扣 0.28 的當沖來回 = 2 × 0.001425 × 0.28 + 0.0015 = 0.002298；
        折扣 1.0 的一般來回 = 0.00285 + 0.003 = 0.00585。
        """
        return (
            2.0 * self.commission_rate_effective
            + self.sell_tax(daytrade, is_etf, date=date)
            + 2.0 * self.slippage_rate
        )

    def order_cost(
        self,
        notional_ntd: float,
        side: str,
        daytrade: bool = True,
        is_etf: bool = False,
        *,
        date: Any = None,
    ) -> float:
        """單筆委託的成本（新台幣）。

        手續費 = 成交金額 × 實收費率；`capital_ntd` 有給時至少 `min_fee_ntd`（NT$20）。
        再加滑價；`side="sell"` 時加證交稅。成交金額是 0 時沒有委託，成本 0。
        成交金額取絕對值，正負號不影響。
        """
        _check_side(side)
        amount = abs(float(notional_ntd))
        if not math.isfinite(amount):
            raise ValueError(f"notional_ntd 要是有限的數，拿到 {notional_ntd}")
        if amount == 0.0:
            return 0.0
        commission = amount * self.commission_rate_effective
        if self.cfg.capital_ntd is not None:
            commission = max(commission, float(self.cfg.min_fee_ntd))
        cost = commission + amount * self.slippage_rate
        if side == "sell":
            cost += amount * self.sell_tax(daytrade, is_etf, date=date)
        return float(cost)

    def sell_tax_rates(
        self,
        shape: tuple[int, ...],
        daytrade: bool,
        is_etf: npt.ArrayLike | bool = False,
        dates: npt.ArrayLike | None = None,
    ) -> npt.NDArray[np.float64]:
        """向量版的 `sell_tax`，回傳形狀 `shape` 的稅率陣列。

        `is_etf`、`dates` 要能 broadcast 到 `shape`。`dates` 是 None 時當沖一律用減半稅率；
        有給時，2017-04-28 到 2027-12-31（都含）和 NaT 的當沖用減半稅率，這段期間以外用一般稅率。
        """
        etf = np.broadcast_to(np.asarray(is_etf, dtype=bool), shape)
        normal = float(self.cfg.sell_tax_rate)
        rates = np.full(shape, normal, dtype=np.float64)
        if daytrade:
            if dates is None:
                in_force = np.ones(shape, dtype=bool)
            else:
                d = np.asarray(dates, dtype="datetime64[ns]")
                in_window = (d >= _DAYTRADE_TAX_CUT_START) & (d < _DAYTRADE_TAX_CUT_END_EXCLUSIVE)
                in_force = np.broadcast_to(np.isnat(d) | in_window, shape)
            rates = np.where(in_force, float(self.cfg.daytrade_sell_tax_rate), rates)
        rates = np.where(etf, float(self.cfg.etf_sell_tax_rate), rates)
        return np.asarray(rates, dtype=np.float64)

    def trade_cost_fraction(
        self,
        sizes: npt.ArrayLike,
        side: str,
        daytrade: bool,
        is_etf: npt.ArrayLike | bool = False,
        dates: npt.ArrayLike | None = None,
    ) -> npt.NDArray[np.float64]:
        """一批委託的成本，單位是「本金的比例」，形狀和 `sizes` 一樣。

        `sizes` 是每筆的成交金額 ÷ 本金（例如權重的絕對值），取絕對值後用。
        手續費 = sizes × 實收費率；`capital_ntd` 有給時，每筆 > 0 的委託至少
        `min_fee_ntd / capital_ntd`（NT$20 換成本金比例）。再加滑價；`side="sell"` 時加證交稅。
        沒給 `capital_ntd` 時就是 `sizes × 費率`，和 `round_trip_rate` 一致。
        """
        _check_side(side)
        a = np.abs(np.asarray(sizes, dtype=np.float64))
        a = np.where(np.isfinite(a), a, 0.0)
        commission = a * self.commission_rate_effective
        capital = self.cfg.capital_ntd
        if capital is not None:
            min_frac = float(self.cfg.min_fee_ntd) / float(capital)
            commission = np.where(a > 0.0, np.maximum(commission, min_frac), 0.0)
        cost = commission + a * self.slippage_rate
        if side == "sell":
            cost = cost + a * self.sell_tax_rates(a.shape, daytrade, is_etf, dates)
        return np.asarray(cost, dtype=np.float64)
