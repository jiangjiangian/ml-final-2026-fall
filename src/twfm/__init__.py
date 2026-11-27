"""twfm：台股時序基礎模型的遷移學習和微調 pipeline（研究用）。

和每天交件的正式流程完全分開：這個套件不 import `src.pipeline`、`src.models`、`run_daily`，
正式程式也不 import 這個套件。

子套件：
    data/   資料格式、還原權息、對齊協變量、股票池、假資料（不需要 torch）
    models/ 主幹（Kronos、PatchTransformer）、LoRA、協變量 head
    train/  切分、損失、微調
    eval/   指標、交易成本、回測
    pipeline.py  端到端和 CLI（`python -m src.twfm.pipeline`）

套件內一律用相對 import，所以不管載入成 `src.twfm`（repo）或 `twfm`（Kaggle 複製成頂層）都能用。
測試一律用頂層的 `twfm` 這個名字 import（`tests/conftest.py` 會設好 `sys.path`）。說明在 `README.md`。
這個檔不 import 任何子模組，import 套件本身不會載入 torch。
"""

from __future__ import annotations

__version__ = "0.1.0"
