"""評估：指標、台股交易成本、回測（都不需要 torch）。

子模組：
    metrics   每天 IC、Newey-West 標準誤、Sharpe、最大回撤
    costs     台股手續費、證交稅、最低手續費（`TaiwanCostModel`）
    backtest  權重、回測、比賽分數、損益兩平成本、總報告

這個檔不在 import 時載入子模組。`from twfm.eval import backtest_report` 這類寫法
第一次用到名字時才載入對應的子模組（PEP 562 的 `__getattr__`）。
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backtest import (
        backtest_report,
        break_even_cost,
        competition_score,
        make_weights,
        run_backtest,
    )
    from .costs import TaiwanCostModel
    from .metrics import (
        daily_ic,
        ic_summary,
        max_drawdown,
        newey_west_se,
        sharpe_ratio,
        summarize_daily,
    )

_LAZY: dict[str, str] = {
    "daily_ic": "metrics",
    "newey_west_se": "metrics",
    "ic_summary": "metrics",
    "sharpe_ratio": "metrics",
    "max_drawdown": "metrics",
    "summarize_daily": "metrics",
    "TaiwanCostModel": "costs",
    "make_weights": "backtest",
    "run_backtest": "backtest",
    "competition_score": "backtest",
    "break_even_cost": "backtest",
    "backtest_report": "backtest",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    """第一次用到公開名字時才 import 對應的子模組。"""
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
