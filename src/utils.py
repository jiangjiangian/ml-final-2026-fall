"""各步驟共用的小工具：讀設定、台北時間、截止檢查、log。"""

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "config.yaml"


def load_config(path=CONFIG_PATH):
    """讀 configs/config.yaml，回傳 dict。

    帳號密碼不在設定檔裡；需要時用 load_secrets() 從環境變數或 .env 讀。
    """
    raise NotImplementedError


def load_secrets():
    """回傳 {"COURSE_EMAIL": ..., "COURSE_PASSWORD": ..., "COURSE_LIVE_KEY": ...}。

    先讀環境變數，沒有再讀根目錄的 .env。缺必要的值就丟出錯誤，不要用空字串繼續跑。
    不可以把這些值印到 log。
    """
    raise NotImplementedError


def taipei_now():
    """回傳現在的台北時間（有時區的 datetime）。測試時可以用參數蓋掉。"""
    raise NotImplementedError


def check_deadline(now: datetime | None = None, deadline: str = "09:00"):
    """過了當天的截止時間（台北）就丟出錯誤。每個步驟開始前都呼叫一次。"""
    raise NotImplementedError


def get_logger(name: str):
    """回傳寫到畫面和 data/submission/run_YYYY-MM-DD.log 的 logger。"""
    raise NotImplementedError
