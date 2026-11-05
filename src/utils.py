"""各步驟共用的小工具：讀設定和帳密、台北時間、截止檢查、log。"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "config.yaml"
ENV_PATH = ROOT / ".env"
TAIPEI = ZoneInfo("Asia/Taipei")
SECRET_KEYS = ("COURSE_EMAIL", "COURSE_PASSWORD", "COURSE_LIVE_KEY")
REQUIRED_SECRETS = ("COURSE_EMAIL", "COURSE_PASSWORD")


def load_config(path=CONFIG_PATH):
    """讀 configs/config.yaml，回傳 dict。帳號密碼不在設定檔裡，用 load_secrets() 讀。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_secrets():
    """回傳 {"COURSE_EMAIL": ..., "COURSE_PASSWORD": ..., "COURSE_LIVE_KEY": ...}。

    先讀環境變數，沒有再讀根目錄的 .env。.env 由這個函式自己逐行解析
    （KEY=VALUE，# 開頭的行跳過），不另外裝套件。
    COURSE_EMAIL、COURSE_PASSWORD 一定要有，缺了就丟出錯誤，不要用空字串繼續跑。
    COURSE_LIVE_KEY 可以是空的：研究時不抓 Live 也能跑；每日模式由 crawler 自己擋。
    這些值不可以印到 log。
    """
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key.strip()] = value
    secrets = {key: os.environ.get(key) or values.get(key, "") for key in SECRET_KEYS}
    missing = [key for key in REQUIRED_SECRETS if not secrets[key]]
    if missing:
        raise RuntimeError(f"缺少 {', '.join(missing)}：請填在 .env 或環境變數")
    return secrets


def taipei_now(now: datetime | None = None):
    """回傳台北時間（有時區的 datetime）。測試時傳入 now，就回傳 now 換成台北時區的值。"""
    if now is None:
        return datetime.now(TAIPEI)
    if now.tzinfo is None:
        raise ValueError("now 要帶時區")
    return now.astimezone(TAIPEI)


def check_deadline(cfg: dict, target_date: str, now: datetime | None = None, key: str = "deadline"):
    """現在已經過了預測日 target_date 當天的截止時間（台北）就丟出錯誤。

    截止時間讀 cfg["competition"][key]：predict.py 用 "deadline"（09:00），
    submit.py 用 "upload_cutoff"（08:50，留時間給上傳和核對）。
    crawler、features、train 不呼叫這個函式，研究時什麼時間都能跑。
    """
    raise NotImplementedError


def get_logger(name: str, target_date: str):
    """回傳寫到畫面和 data/submission/run_<target_date>.log 的 logger。

    等級是 INFO。不要改成 DEBUG：yfinance 在 DEBUG 會印出 crumb 和整個回應。
    """
    logger = logging.getLogger(f"finpred.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = ROOT / "data" / "submission" / f"run_{target_date}.log"
    if any(getattr(h, "baseFilename", None) == str(log_path) for h in logger.handlers):
        return logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger
