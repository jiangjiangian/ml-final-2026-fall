"""資料層：格式、還原權息、對齊協變量、股票池、假資料。

這個子套件除了 `dataset.py` 都只用 numpy、pandas、scipy，沒有 torch 也能用和測試。
這裡不 import `dataset`（它需要 torch），要用 Dataset 請直接 `from .dataset import ...`。

模組：
    schema     欄名常數、`validate_*`、`is_common_stock`
    adjust     事件因子、還原價、對數報酬、升降單位、漲跌停
    align      t 開盤前已知的協變量（美股隔夜、法人、融資、個股狀態）和標準化
    universe   每個 t 的股票池（處理存活偏差）
    synthetic  假市場，給測試和 smoke
"""

from __future__ import annotations

from .adjust import (
    adjusted_levels,
    cumulative_factor,
    effective_ref_price,
    event_factors,
    limit_flags,
    limit_prices,
    log_returns,
    tick_size,
)
from .align import (
    align_us_overnight,
    build_covariates,
    cross_sectional_rank_gauss,
    institutional_features,
    margin_features,
    market_cov_columns,
    prev_trading_day,
    rolling_market_zscore,
    stock_cov_columns,
    stock_state_features,
)
from .schema import (
    INST_COLS,
    MARGIN_COLS,
    PANEL_COLS,
    US_COLS,
    SchemaError,
    is_common_stock,
    validate_calendar,
    validate_inst,
    validate_margin,
    validate_panel,
    validate_us,
)
from .synthetic import SyntheticMarket, make_synthetic_market
from .universe import build_universe, universe_audit

__all__ = [
    "INST_COLS",
    "MARGIN_COLS",
    "PANEL_COLS",
    "US_COLS",
    "SchemaError",
    "SyntheticMarket",
    "adjusted_levels",
    "align_us_overnight",
    "build_covariates",
    "build_universe",
    "cross_sectional_rank_gauss",
    "cumulative_factor",
    "effective_ref_price",
    "event_factors",
    "institutional_features",
    "is_common_stock",
    "limit_flags",
    "limit_prices",
    "log_returns",
    "make_synthetic_market",
    "margin_features",
    "market_cov_columns",
    "prev_trading_day",
    "rolling_market_zscore",
    "stock_cov_columns",
    "stock_state_features",
    "tick_size",
    "universe_audit",
    "validate_calendar",
    "validate_inst",
    "validate_margin",
    "validate_panel",
    "validate_us",
]
