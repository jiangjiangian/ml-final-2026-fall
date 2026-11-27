"""訓練相關的模組。這裡刻意不 import 任何子模組，`import twfm.train` 不會載入 torch。

- `walkforward`：按日期切訓練、驗證、測試，含 embargo。只用 numpy、pandas，沒有 torch 也能用。
- `losses`：損失函數（要 torch）。
- `finetune`：分階段微調、checkpoint、預測（要 torch）。
"""

from __future__ import annotations
