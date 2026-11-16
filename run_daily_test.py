"""舊名字（2026-11-15 前的排程和說明用它）：直接換成 run_daily.py 執行，參數照傳。

oop 上裝好的 crontab 還在叫這支，所以留著。新的排程和說明都寫 run_daily.py。
這裡不能 import src/：要等 run_daily.py 先 git pull 才載入。
"""

import os
import sys
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "run_daily.py"
    os.environ["RUN_DAILY_ENTRY"] = str(Path(__file__).resolve())   # run_daily.py 被 pull 更新時，重新執行這支
    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
