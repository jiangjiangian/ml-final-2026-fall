"""各步驟共用的小工具：讀設定和帳密、台北時間、截止檢查、log。"""

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "config.yaml"


def load_config(path=CONFIG_PATH):
    """讀 configs/config.yaml，回傳 dict。帳號密碼不在設定檔裡，用 load_secrets() 讀。"""
    raise NotImplementedError


def load_secrets():
    """回傳 {"COURSE_EMAIL": ..., "COURSE_PASSWORD": ..., "COURSE_LIVE_KEY": ...}。

    先讀環境變數，沒有再讀根目錄的 .env。.env 由這個函式自己逐行解析
    （KEY=VALUE，# 開頭的行跳過），不另外裝套件。
    COURSE_EMAIL、COURSE_PASSWORD 一定要有，缺了就丟出錯誤，不要用空字串繼續跑。
    COURSE_LIVE_KEY 在 Live 的下載方式決定前可以是空的。
    這些值不可以印到 log。
    """
    raise NotImplementedError


def taipei_now(now: datetime | None = None):
    """回傳台北時間（有時區的 datetime）。測試時傳入 now，就回傳 now 換成台北時區的值。"""
    raise NotImplementedError


def check_deadline(cfg: dict, target_date: str, now: datetime | None = None, key: str = "deadline"):
    """現在已經過了預測日 target_date 當天的截止時間（台北）就丟出錯誤。

    截止時間讀 cfg["competition"][key]：predict.py 用 "deadline"（09:00），
    submit.py 用 "upload_cutoff"（08:50，留時間給上傳和核對）。
    crawler、features、train 不呼叫這個函式，研究時什麼時間都能跑。
    """
    raise NotImplementedError


def get_logger(name: str, target_date: str):
    """回傳寫到畫面和 data/submission/run_<target_date>.log 的 logger。"""
    raise NotImplementedError
