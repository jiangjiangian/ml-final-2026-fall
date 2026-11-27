"""讓測試一律用頂層的套件名稱 `twfm` import。

套件可能放在兩種地方：repo 的 `src/twfm/`，或 Kaggle 上複製成頂層的 `twfm/`。
這裡把「`twfm` 資料夾的上一層」放到 `sys.path` 最前面，測試就都寫 `from twfm.x import y`。
套件裡的程式一律用相對 import，所以不管被載入成哪個名字都能用；
測試只用一個名字，同一個測試裡不會出現兩份 `twfm`（兩份的 dataclass 會讓 `isinstance` 判斷失敗）。

檢查「不載入 torch」的測試會開子程序，子程序拿 `sys.path` 當 `PYTHONPATH`，所以也找得到 `twfm`。
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_PARENT = str(Path(__file__).resolve().parents[2])

if _PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, _PACKAGE_PARENT)
