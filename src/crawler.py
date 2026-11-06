"""爬蟲：下載老師資料和 yfinance 額外指標，原樣存到 data/raw/。

輸出：
    data/raw/phase2_days.json      課程網站 /api/state 的 phase2Days（只存日期、enabled、isCompetition）
    data/raw/teacher/training/     老師 Training ZIP 解開：info.json、global/global_data.csv、market/<代號>.csv
    data/raw/teacher/live/         老師 Live ZIP 解開：global/global_data.csv、market/<代號>.csv（沒有 info.json），
                                   每次整包換新。Live 本身從 9/1 到 t，每天多一列，所以在 Git 裡看起來是往後加
    data/raw/yfinance/<名稱>.csv   19 個額外指標各一檔：date, open, high, low, close, adj_close, volume
    data/raw/yfinance/usd_twd_1h.csv  TWD=X 的 1 小時K棒（yfinance.hourly）：start, open, high, low, close, volume，
                                   start 是K棒開始時間（台北，ISO 帶時區）。每次和舊檔合併，Yahoo 只給大約兩年多
    data/raw/taifex/tx.csv         台指期（tx_futures.source 是 taifex 時）：期交所「期貨每日交易行情」的 TX 列，
                                   欄位和期交所一樣（TAIFEX_COLUMNS），只留單月合約，日期改成 YYYY-MM-DD、去掉格子
                                   前後的空白、存成 UTF-8。每次和舊檔合併
    data/raw/manifest.json         最近一次執行的紀錄：每個檔案的 sha256、筆數、狀態、錯誤類別

兩種模式：
    python -m src.crawler                    研究模式：t 取台北今天，不檢查時間，Live 沒有金鑰就跳過
    python -m src.crawler --date 2026-11-17  每日模式（run_daily.py 用）：t 是預測日，07:00 前不跑，08:30 後不再重試

名詞：
    t   預測日。
    i   t 的前一個台股交易日：Live 裡早於 t 的最後一個交易日（trading_days()，和 features.py 同一條規則：
        100 檔裡至少 crawler.min_stocks_filled 檔填好）。特徵用的就是 i 那天的值。程式和 manifest 裡叫 prev_day。
        phase2Days 早於 t 的最後一天記成 prev_day_planned，只拿來比對。

老師資料：
    - 兩個 ZIP 裡的路徑開頭都多一層 data/，解壓時拿掉，其他位元組原樣寫出（Live 的 CRLF 也保留）。
    - Training 不會再變。data/raw/teacher/training/ 的檔案指紋和上次的 manifest 一樣，就不下載 ZIP。
    - Live 每次都下載。t 那列在 t 當天 00:00 新增、先填 -1，^IXIC、^GSPC 約 05:05 前填好，其他欄和 y 在
      t 當天 22:05 前陸續填完。所以早上的 Live 已經有 t 那列，i 那列也填好了。
    - 「有 t 那列」「i 那天填好」都是看 100 檔裡有沒有 crawler.min_stocks_filled（90）檔做到。個別股票停牌
      不會擋住流程，manifest 記 prev_day_missing_stocks，那幾檔自己的特徵當天空白。
    - 每日模式要求 Live 有 t 那列。phase2Days 的前一天比 i 晚、又不在 crawler.closed_days 裡（老師還沒填），
      manifest 記 prev_day_never_filled，回傳 3。closed_days（10-23 颱風假）那天出現填好的資料就停下。
    - -1 不處理。只有 Live 待定格的 -1 是「還沒有」，Training 法人欄有真的 -1。清理留給 features.py。

yfinance：
    - 限流加在 PacedSession（curl_cffi 的 Session）上，yfinance 自己送的 cookie、crumb（Yahoo 給的一次性驗證碼）、時區請求和每一跳轉址
      都要經過：上一個請求結束後至少等 min_interval_seconds，再加 0～jitter_seconds 的隨機。
    - auto_adjust=False，每天重抓 data.start 到 t 前一天的完整歷史（除息後 adj_close 會整欄重算）。
    - 只留日期 < t 的K棒（一天的開高低收和成交量），也丟掉週末日期的K棒。end 只限制請求的範圍，擋不住 Yahoo 附在最後的盤中資料。
    - 期貨（CL=F、GC=F）台北 07:00 後已經開始下一段交易：end 截在紐約 17:30。最後一根成交量低於前 21 根
      中位數的 10% 時只在 manifest 記 low_volume_last_bar_kept，不丟（換月日、Yahoo 量 0 的真結算K棒也會這樣）。
    - 抓完檢查每個序列有沒有 i 那根（個股和 ETF 另外要成交量 > 0），記在 has_bar_i。沒有的一起等一下重抓一次，
      還是沒有就列在 run.no_bar_i，那個特徵當天空白。外國放假時常這樣，不算失敗（使用者 2026-11-06）。
    - 1h 只留結束時間不晚於「現在」和「t 那天 features.usd_twd_am.at（06:00）」的K棒；has_value_t 記 t 那天
      06:00 前 lookback_days 天內有沒有K棒。
    - yfinance 1.7.0 讀到壞掉的 cookie 快取（沒有 A3）會丟 KeyError，而且每次都壞。setup_yfinance 把它包起來，
      讀不懂就當成沒有快取，重新拿一個。

台指期（tx_futures，使用者 2026-11-06 加）：
    - 開關 tx_futures.source：taifex（預設，期交所網站下載）或 yfinance（用 tx_futures.yfinance 填的代號，當成
      yfinance 序列 tx_day 抓）。切到 yfinance 但沒填代號，或填了夜盤代號（還沒查證 Yahoo 怎麼標夜盤的日期，
      而且 t 那根會被「日期 < t」丟掉），一開始就丟 CrawlerError。
    - 期交所一次最多查一個月，所以照月份切成好幾個請求，每個請求至少間隔 tx_futures.taifex.min_interval_seconds。
      第一次從 data.start 抓起（約 83 個請求），之後從舊檔最後一天往前 overlap_days 天抓到今天。
    - 交易時段「一般」是日盤（08:45～13:45），「盤後」是夜盤。標 d 日的盤後列是 d 的前一個營業日 15:00 開始、隔天
      05:00 收盤的夜盤（平常就是 d 日 05:00；連假後那天標的是連假前最後一晚的夜盤）。
      只存 t 之前的日盤；夜盤存到 t 那列為止，而且 t 那列要等到 t 當天 night_ready（05:15）以後才存。
    - 期交所失敗：舊檔留著，manifest 記 failed，回傳 3，流程繼續。沒有 i 的日盤或 t 的夜盤就列在 run.no_bar_i。

截止（crawler.deadline，08:30）：
    - 過了截止就不再等待、不再重試，每一步只試一次；yfinance 還沒抓的序列直接沿用舊檔。期交所只試一次。
    - 課程網站和 Live 的每個請求，從送出到下載完最多 course_site.total_timeout_seconds 秒。

失敗時：
    - 課程網站登入遇到逾時、連不上、429、5xx，最多再試 course_site.login_retries 次（使用者 2026-11-06）。
    - /api/state 讀不到時，改用上次存的 phase2_days.json，前提是裡面有 t；沒有 t 就停下（每日模式）。
    - yfinance 某個序列失敗：舊檔留著，manifest 記 failed，繼續。main 回傳 3。
    - 抓回來是空的、開頭比舊檔晚，或最後一天比舊檔裡早於 t 的最後一天還早（歷史被截短）：當成失敗，不覆蓋舊檔。
    - 老師資料拿不到、Live 沒更新到 t、每日模式讀不到 /api/state、還沒到開始時間：丟 CrawlerError。
      已經寫好的檔案和舊檔都留著。
    - main 回傳 0（全部正常）或 3（有東西真的失敗但可以繼續：序列抓失敗、改用快取的 phase2Days、
      prev_day_never_filled），不呼叫 sys.exit。只是沒有 i 那根不回傳 3。

帳密、金鑰、cookie、crumb、網址 ? 後面的部分和伺服器回應的內容，都不寫進 manifest 和 log。
"""

import argparse
import csv
import functools
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import statistics
import tempfile
import threading
import time
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from curl_cffi.requests import Session as CurlSession

from src import utils

TAIPEI = ZoneInfo("Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
REDIRECT_CODES = (301, 302, 303, 307, 308)
RETRY_STATUS = (429, 500, 502, 503, 504)

STOCK_COLUMNS = (
    "date", "etl:adj_close", "etl:adj_open", "etl:adj_high", "etl:adj_low",
    "price:成交筆數", "price:成交金額", "price:成交股數",
    "foreign_investors_shareholding:全體外資及陸資持股比率",
    "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)",
    "institutional_investors_trading_summary:投信買賣超股數",
    "institutional_investors_trading_summary:自營商買賣超股數(自行買賣)",
    "institutional_investors_trading_summary:自營商買賣超股數(避險)",
    "RSI", "SMA", "MACD", "ATR", "BBANDS_upper", "BBANDS_mid", "BBANDS_lower", "y",
)
GLOBAL_COLUMNS = ("date", "^VIX", "^IXIC", "^GSPC", "^TWII", "^KS11", "TX_OI")
YF_COLUMNS = ("date", "open", "high", "low", "close", "adj_close", "volume")
HOURLY_COLUMNS = ("start", "open", "high", "low", "close", "volume")   # start：K棒開始時間，ISO 格式帶時區
HOURLY_BAR = timedelta(hours=1)
TAIFEX_COLUMNS = ("交易日期", "契約", "到期月份(週別)", "開盤價", "最高價", "最低價", "收盤價", "漲跌價", "漲跌%", "成交量",
                  "結算價", "未沖銷契約數", "最後最佳買價", "最後最佳賣價", "歷史最高價", "歷史最低價",
                  "是否因訊息面暫停交易", "交易時段", "價差對單式委託成交量")
TAIFEX_SESSIONS = {"一般": "day", "盤後": "night"}   # 日盤、夜盤
TX_SERIES = {"day": "tx_day", "night": "tx_night"}   # 台指期在特徵表和 run.no_bar_i 裡的序列名稱
COL_CLOSE, COL_OPEN, COL_Y = STOCK_COLUMNS.index("etl:adj_close"), STOCK_COLUMNS.index("etl:adj_open"), STOCK_COLUMNS.index("y")


class CrawlerError(RuntimeError):
    """不能繼續的錯誤。訊息由這個檔案自己寫，不含帳密、金鑰和伺服器回應。"""


class TransientError(CrawlerError):
    """可能過一下就好的錯誤：逾時、連不上、429、5xx、ZIP 下載不完整、Live 還沒有 t 那列。"""


# ---------------------------------------------------------------- 共用的小工具


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files_digest(files: dict) -> str:
    """一組檔案的指紋：依路徑排序，把「路徑<TAB>sha256」逐行接起來再算 sha256。files 是 {相對路徑: bytes}。"""
    lines = "".join(f"{rel}\t{sha256_bytes(files[rel])}\n" for rel in sorted(files))
    return sha256_bytes(lines.encode())


def dir_files(path: Path) -> dict:
    """讀出資料夾裡所有檔案，回傳 {相對路徑（/ 分隔）: bytes}。點開頭的檔案（.DS_Store、暫存檔）不算。"""
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*"))
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(path).parts)}


def write_atomic(path: Path, data: bytes):
    """先寫到同一個資料夾的暫存檔，再換名，中途出錯不會留下寫一半的檔案。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def replace_dir(target: Path, files: dict):
    """把 files 寫成新的資料夾 target。先寫到 .<名稱>.new，全部寫完才把舊的移開、新的換進來。"""
    tmp = target.parent / f".{target.name}.new"
    old = target.parent / f".{target.name}.old"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    for rel, data in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.chmod(p, 0o644)
    if target.exists():
        target.rename(old)
    tmp.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def is_iso_date(text: str) -> bool:
    try:
        return date.fromisoformat(text).isoformat() == text
    except (TypeError, ValueError):
        return False


def to_float(text: str):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# ---------------------------------------------------------------- 一次執行的狀態


@dataclass
class Run:
    """一次執行共用的東西：設定、預測日、時鐘、manifest。測試時換掉 now 和 sleep。"""

    cfg: dict
    t: str
    daily: bool
    raw_dir: Path
    log: object
    now: object = utils.taipei_now
    sleep: object = time.sleep
    manifest: dict = field(default_factory=dict)
    previous: dict = field(default_factory=dict)
    prev_day: str | None = None
    phase2_days: list | None = None
    stale: bool = False
    no_bar_i: list = field(default_factory=list)

    def at(self, hhmm: str) -> datetime:
        hour, minute = (int(x) for x in hhmm.split(":"))
        return datetime.combine(date.fromisoformat(self.t), dtime(hour, minute), TAIPEI)

    @property
    def deadline(self):
        return self.at(self.cfg["crawler"]["deadline"]) if self.daily else None

    def can_wait(self, seconds: float) -> bool:
        """等 seconds 秒之後還沒過爬蟲截止。研究模式沒有截止。"""
        return self.deadline is None or self.now() + timedelta(seconds=seconds) < self.deadline

    def past_deadline(self) -> bool:
        return self.deadline is not None and self.now() >= self.deadline

    def save(self):
        write_atomic(self.raw_dir / "manifest.json",
                     (json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n").encode())


# ---------------------------------------------------------------- 課程網站和 Live 的 HTTP


class SiteClient:
    """課程網站和 Live 共用的 HTTP。

    每個請求都有逾時和總時間上限（total_seconds），邊下載邊數位元組，只跟隨同一個主機的轉址。GET 遇到 429、5xx
    或連線錯誤重試 2 次，但 can_wait 說不能等（過了爬蟲截止）就不重試；POST 在這一層不重試（登入的重試在
    course_login）。錯誤訊息只寫路徑和狀態碼，不寫回應內容。requests 數送出的請求（含轉址）。
    """

    def __init__(self, base_url: str, timeout, max_bytes: int, session=None, sleep=time.sleep, total_seconds=None,
                 clock=time.monotonic):
        self.base = base_url.rstrip("/")
        self.timeout = tuple(timeout)
        self.max_bytes = max_bytes
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
        self.sleep = sleep
        self.total_seconds = total_seconds
        self.clock = clock
        self.can_wait = lambda seconds: True   # crawl() 換成 run.can_wait
        self.requests = 0

    def close(self):
        self.session.close()

    def read(self, method: str, path: str, *, max_bytes=None, retries=2, **kwargs) -> bytes:
        limit = max_bytes or self.max_bytes
        label = urlsplit(path).path or "/"
        for attempt in range(retries + 1 if method == "GET" else 1):
            try:
                return self._read_once(method, path, limit, label, **kwargs)
            except TransientError:
                if method != "GET" or attempt == retries or not self.can_wait(2 ** attempt):
                    raise
                self.sleep(2 ** attempt)
        raise TransientError(f"{label}：重試用完")

    def _read_once(self, method, path, limit, label, **kwargs) -> bytes:
        started = self.clock()
        origin = urlsplit(self.base)
        url = urljoin(self.base + "/", path.lstrip("/"))
        for _ in range(5):
            parts = urlsplit(url)
            if (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc):
                raise CrawlerError(f"{label}：轉址到別的主機，不跟")
            self.requests += 1
            try:
                resp = self.session.request(method, url, timeout=self.timeout, allow_redirects=False,
                                            stream=True, **kwargs)
            except requests.RequestException as e:
                raise TransientError(f"{label}：連線失敗（{type(e).__name__}）") from None
            try:
                if resp.status_code in REDIRECT_CODES:
                    location = resp.headers.get("Location") or resp.headers.get("location")
                    if not location:
                        raise CrawlerError(f"{label}：轉址沒有目的地")
                    url = urljoin(url, location)
                    if resp.status_code == 303 or (resp.status_code in (301, 302) and method == "POST"):
                        method = "GET"
                        kwargs = {k: v for k, v in kwargs.items() if k not in ("data", "json")}
                    continue
                if resp.status_code in RETRY_STATUS:
                    raise TransientError(f"{label}：HTTP {resp.status_code}")
                if resp.status_code != 200:
                    raise CrawlerError(f"{label}：HTTP {resp.status_code}")
                chunks, size = [], 0
                for chunk in resp.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > limit:
                        raise CrawlerError(f"{label}：超過大小上限 {limit} bytes")
                    if self.total_seconds is not None and self.clock() - started > self.total_seconds:
                        raise TransientError(f"{label}：超過總時間上限 {self.total_seconds} 秒")
                    chunks.append(chunk)
                return b"".join(chunks)
            except requests.RequestException as e:
                raise TransientError(f"{label}：下載中斷（{type(e).__name__}）") from None
            finally:
                resp.close()
        raise CrawlerError(f"{label}：轉址太多次")


def course_client(cfg, sleep=time.sleep, session=None, clock=time.monotonic) -> SiteClient:
    site = cfg["course_site"]
    return SiteClient(site["base_url"], site["timeout_seconds"], site["max_zip_mb"] * 2**20, session, sleep,
                      site["total_timeout_seconds"], clock)


def live_client(cfg, sleep=time.sleep, session=None, clock=time.monotonic, *, fallback=False) -> SiteClient:
    """Live 的 HTTP。預設是助教原本的網址，只信任 course_site.live.ca_file 那張自簽憑證，不關掉憑證檢查；
    fallback=True 是 fallback_url（chatgpt.site），用系統的憑證。憑證檔不見時不指定，驗證會失敗，改用 fallback。"""
    site = cfg["course_site"]
    conf = site["live"]
    client = SiteClient(conf["fallback_url"] if fallback else conf["base_url"], site["timeout_seconds"],
                        site["max_zip_mb"] * 2**20, session, sleep, site["total_timeout_seconds"], clock)
    ca = utils.ROOT / conf["ca_file"] if conf.get("ca_file") and not fallback else None
    if ca is not None and ca.is_file():
        client.session.verify = str(ca)
    return client


def live_clients(cfg, sleep=time.sleep, clock=time.monotonic) -> list:
    """Live 依序要試的入口（使用者 2026-11-06）：原本的網址優先，連不上或出錯才用 chatgpt.site。
    助教說 chatgpt.site 承受不了太多流量，正常的日子不對它送請求。"""
    clients = [live_client(cfg, sleep, clock=clock)]
    if cfg["course_site"]["live"].get("fallback_url"):
        clients.append(live_client(cfg, sleep, clock=clock, fallback=True))
    return clients


def course_login(course: SiteClient, cfg, secrets):
    """登入課程網站。逾時、連不上、429、5xx 時最多再試 course_site.login_retries 次（使用者 2026-11-06：登入
    不是上傳，重送沒有副作用）。密碼錯（4xx）、回應說拒絕、過了爬蟲截止都不重試。"""
    retries = cfg["course_site"]["login_retries"]
    for attempt in range(retries + 1):
        try:
            raw = course.read("POST", cfg["course_site"]["login"], max_bytes=2**20,
                              json={"email": secrets["COURSE_EMAIL"], "password": secrets["COURSE_PASSWORD"]},
                              headers={"Origin": course.base, "Referer": course.base + "/login"})
            break
        except TransientError:
            if attempt == retries or not course.can_wait(2 ** attempt):
                raise
            course.sleep(2 ** attempt)
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CrawlerError("課程網站登入：回應不是 JSON") from None
    if not isinstance(result, dict) or result.get("success") is False or result.get("error"):
        raise CrawlerError("課程網站登入被拒絕")


def fetch_phase2_days(course: SiteClient, cfg) -> list:
    """讀 /api/state，回傳 phase2Days 排好的清單，每筆只留 tradingDate、enabled、isCompetition。"""
    raw = course.read("GET", cfg["course_site"]["state"], max_bytes=4 * 2**20)
    try:
        state = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CrawlerError("/api/state：回應不是 JSON") from None
    days = state.get("phase2Days") if isinstance(state, dict) else None
    if not isinstance(days, list) or not days:
        raise CrawlerError("/api/state：沒有 phase2Days")
    out = {}
    for item in days:
        d = item.get("tradingDate") if isinstance(item, dict) else None
        if not is_iso_date(d) or d in out:
            raise CrawlerError("/api/state：phase2Days 的日期格式不對或重複")
        out[d] = {"tradingDate": d, "enabled": item.get("enabled"), "isCompetition": item.get("isCompetition")}
    return [out[d] for d in sorted(out)]


def cached_phase2_days(raw_dir: Path):
    """上次存的 phase2_days.json；讀不到或格式不對回傳 None。"""
    try:
        days = json.loads((raw_dir / "phase2_days.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(days, list) or not all(isinstance(d, dict) and is_iso_date(d.get("tradingDate")) for d in days):
        return None
    return sorted(days, key=lambda d: d["tradingDate"])


def live_download(live: SiteClient, cfg, key: str) -> bytes:
    conf = cfg["course_site"]["live"]
    page = live.read("POST", conf["login"], max_bytes=4 * 2**20, data={"key": key},
                     headers={"Origin": live.base, "Referer": live.base + "/"})
    if not re.search(rb'href=["\']' + re.escape(conf["zip"].encode()) + rb'["\']', page):
        raise CrawlerError("Live 登入失敗：頁面沒有下載連結（金鑰可能不對）")
    return live.read("GET", conf["zip"], headers={"Referer": live.base + "/"})


def live_host(live: SiteClient) -> str:
    return urlsplit(live.base).netloc


def live_fetch(run: Run, lives: list, key: str, stock_ids, max_bytes: int, max_unzipped: int):
    """照順序試每個 Live 入口，第一個下載並解開成功的就用，回傳 (入口, ZIP, 檔案, 解析結果, 前面入口的錯誤)。

    連不上、憑證不符、逾時、5xx、金鑰被拒、ZIP 不對都換下一個入口，不等待。全部失敗時，只要有一個是暫時性
    錯誤就丟 TransientError（呼叫的人等一下再抓），否則丟 CrawlerError。還沒有 t 那列不在這裡判斷，不換入口。
    """
    errors, transient = [], False
    for n, client in enumerate(lives):
        try:
            blob = live_download(client, run.cfg, key)
            files, parsed = unpack_zip(blob, "live", stock_ids, max_bytes, max_unzipped)
            return client, blob, files, parsed, errors
        except CrawlerError as e:
            transient = transient or isinstance(e, TransientError)
            errors.append(f"{live_host(client)}：{e}")
            if n + 1 < len(lives):
                run.log.warning("Live %s 出錯（%s），改用 %s", live_host(client), e, live_host(lives[n + 1]))
    raise (TransientError if transient else CrawlerError)("；".join(errors))


# ---------------------------------------------------------------- 老師 ZIP 的檢查和解壓


def check_csv(name: str, data: bytes, columns: tuple) -> list:
    """表頭要一模一樣、每列欄數一樣、日期是 YYYY-MM-DD 而且遞增。回傳資料列（不含表頭）。"""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CrawlerError(f"{name}：不是 UTF-8") from None
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows or tuple(rows[0]) != columns:
        raise CrawlerError(f"{name}：表頭和預期不一樣")
    body = rows[1:]
    if not body:
        raise CrawlerError(f"{name}：沒有資料列")
    previous = ""
    for row in body:
        if len(row) != len(columns):
            raise CrawlerError(f"{name}：欄數不對")
        if not is_iso_date(row[0]) or row[0] <= previous:
            raise CrawlerError(f"{name}：日期格式不對、沒排好或重複")
        previous = row[0]
    return body


def read_info(data: bytes) -> dict:
    try:
        info = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CrawlerError("info.json 不是 JSON") from None
    if not isinstance(info, dict) or set(info) != {"Top50@Y", "Top100@Y"}:
        raise CrawlerError("info.json 的鍵不是 Top50@Y、Top100@Y")
    top50, top100 = info["Top50@Y"], info["Top100@Y"]
    ok = (isinstance(top50, list) and isinstance(top100, list) and len(top50) == 50 and len(top100) == 100
          and all(isinstance(s, str) and s.isdigit() for s in top100)
          and len(set(top100)) == 100 and len(set(top50)) == 50 and set(top50) <= set(top100))
    if not ok:
        raise CrawlerError("info.json 的 Top50@Y、Top100@Y 格式不對")
    return info


def unpack_zip(blob: bytes, kind: str, stock_ids=None, max_bytes=100 * 2**20, max_unzipped=512 * 2**20):
    """檢查老師 ZIP，回傳 ({拿掉 data/ 的相對路徑: bytes}, {相對路徑: 解析過的資料列})。

    kind 是 "training" 或 "live"。Training 的股票清單從自己的 info.json 來；Live 要傳 stock_ids（Training 的 Top100@Y）。
    成員名稱集合要剛好等於預期、不能重複；路徑照預期清單產生，不用 extractall。
    """
    if len(blob) > max_bytes:
        raise CrawlerError(f"{kind} ZIP 超過大小上限")
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        infos = zf.infolist()
    except (zipfile.BadZipFile, EOFError):
        raise TransientError(f"{kind} ZIP 打不開（可能沒下載完整）") from None
    names = [i.filename for i in infos]
    if len(names) != len(set(names)):
        raise CrawlerError(f"{kind} ZIP 有重複的成員名稱")
    if sum(i.file_size for i in infos) > max_unzipped:
        raise CrawlerError(f"{kind} ZIP 解開後超過大小上限")

    def read(name):
        try:
            return zf.read(name)
        except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError):
            raise TransientError(f"{kind} ZIP 的 {name} 讀不出來（CRC 不對或加密）") from None

    if kind == "training":
        if "data/info.json" not in names:
            raise CrawlerError("training ZIP 沒有 data/info.json")
        stock_ids = read_info(read("data/info.json"))["Top100@Y"]
    expected = {"data/global/global_data.csv"} | {f"data/market/{s}.csv" for s in stock_ids}
    if kind == "training":
        expected.add("data/info.json")
    if set(names) != expected:
        extra, missing = sorted(set(names) - expected), sorted(expected - set(names))
        # 多出來的名稱是伺服器給的內容，不寫進訊息；少掉的來自 info.json 的代號，可以寫
        raise CrawlerError(f"{kind} ZIP 的成員不對：多了 {len(extra)} 個，少了 {len(missing)} 個 {missing[:3]}")
    files, parsed = {}, {}
    for name in sorted(expected):
        data = read(name)
        rel = name[len("data/"):]
        if rel.startswith("market/"):
            parsed[rel] = check_csv(name, data, STOCK_COLUMNS)
        elif rel.startswith("global/"):
            parsed[rel] = check_csv(name, data, GLOBAL_COLUMNS)
        files[rel] = data
    return files, parsed


# ---------------------------------------------------------------- Live 有沒有更新到 t


def stock_rows(parsed: dict) -> dict:
    """{代號: {日期: 資料列}}"""
    return {rel[len("market/"):-len(".csv")]: {row[0]: row for row in rows}
            for rel, rows in parsed.items() if rel.startswith("market/")}


def row_filled(row) -> bool:
    """老師個股的一列填好了：y 是 0 或 1，還原開盤價、收盤價都 > 0。法人欄的 -1 不看。"""
    if not row:
        return False
    y, open_, close = to_float(row[COL_Y]), to_float(row[COL_OPEN]), to_float(row[COL_CLOSE])
    return y in (0.0, 1.0) and open_ is not None and open_ > 0 and close is not None and close > 0


def unfilled_stocks(stocks: dict, d: str) -> list:
    """d 那天沒填好的代號：沒有那列，或那列沒填好（見 row_filled）。"""
    return sorted(code for code, rows in stocks.items() if not row_filled(rows.get(d)))


def day_filled(stocks: dict, d: str, min_stocks: int) -> bool:
    """d 那天至少 min_stocks 檔填好。個別股票停牌（沒有列）不會讓整天算沒填；10-23 那種整天 -1 會。"""
    return bool(stocks) and len(stocks) - len(unfilled_stocks(stocks, d)) >= min_stocks


def trading_days(stocks: dict, min_stocks: int, closed_days=()) -> list:
    """台股交易日：老師個股資料裡至少 min_stocks 檔填好的日子，依日期排序。爬蟲和 features.py 都用這個。

    還是 -1 的日子（休市的 10-23、當天早上的 t）不算。closed_days 是 config 的 crawler.closed_days：
    Live 有建列但台股休市的日子。這些日子出現任何一檔填好的列，代表當初的判斷錯了，丟 CrawlerError。
    """
    for d in closed_days:
        if any(row_filled(rows.get(d)) for rows in stocks.values()):
            raise CrawlerError(f"休市日 {d} 出現填好的資料，和 config 的 closed_days 矛盾")
    dates = sorted({d for rows in stocks.values() for d in rows})
    return [d for d in dates if day_filled(stocks, d, min_stocks)]


def live_check(stocks: dict, t: str, phase2_days, min_stocks: int, closed_days=()) -> dict:
    """回傳 has_t_row、prev_day（實際用的 i）、prev_day_planned、prev_day_never_filled、prev_day_missing_stocks。

    has_t_row：至少 min_stocks 檔有 t 那列。prev_day：trading_days() 裡早於 t 的最後一天（和 features.py 同一條規則）。
    prev_day_planned：phase2Days 早於 t 的最後一天（不篩 enabled），只拿來比對。它比 i 晚、又不在 closed_days 裡，
    代表那天老師還沒填，記 prev_day_never_filled。prev_day_missing_stocks：i 那天沒填好的代號（多半是停牌），
    這幾檔自己的特徵當天會是空白。closed_days 那天出現填好的資料時，trading_days() 丟 CrawlerError。
    """
    has_t = sum(t in rows for rows in stocks.values()) >= min_stocks
    earlier = [d for d in trading_days(stocks, min_stocks, closed_days) if d < t]
    prev = earlier[-1] if earlier else None
    planned = None
    if phase2_days:
        scheduled = [d["tradingDate"] for d in phase2_days if d["tradingDate"] < t]
        planned = scheduled[-1] if scheduled else None
    never_filled = planned is not None and (prev is None or planned > prev) and planned not in closed_days
    return {"has_t_row": has_t, "prev_day": prev, "prev_day_planned": planned, "prev_day_never_filled": never_filled,
            "prev_day_missing_stocks": unfilled_stocks(stocks, prev) if prev else []}


# ---------------------------------------------------------------- 老師資料


def download_teacher(run: Run, secrets: dict, course: SiteClient, live):
    """Training（指紋一樣就不下載）和 Live（每次下載），解開到 data/raw/。決定 run.prev_day。

    live 是一個 SiteClient，或依序要試的清單（live_clients）。"""
    cfg = run.cfg
    site = cfg["course_site"]
    max_bytes, max_unzipped = site["max_zip_mb"] * 2**20, site["max_unzipped_mb"] * 2**20
    teacher_dir, live_dir = run.raw_dir / "teacher" / "training", run.raw_dir / "teacher" / "live"

    # Training
    old = run.previous.get("teacher")
    old = old if isinstance(old, dict) else {}
    on_disk = dir_files(teacher_dir) if teacher_dir.exists() else {}
    if on_disk and old.get("files_sha256") == files_digest(on_disk):
        run.manifest["teacher"] = {**old, "status": "ok", "action": "skipped_unchanged"}
        run.log.info("Training：本機的檔案和上次一樣，不下載")
    else:
        run.log.info("Training：下載")
        train_blob = course.read("GET", site["training_zip"], max_bytes=max_bytes)
        train_files, _ = unpack_zip(train_blob, "training", max_bytes=max_bytes, max_unzipped=max_unzipped)
        replace_dir(teacher_dir, train_files)
        run.manifest["teacher"] = {"status": "ok", "action": "downloaded", "zip_sha256": sha256_bytes(train_blob),
                                   "files_sha256": files_digest(train_files)}
    run.save()
    stock_ids = read_info((teacher_dir / "info.json").read_bytes())["Top100@Y"]

    # Live
    lives = live if isinstance(live, (list, tuple)) else [live]
    entry = {"status": "skipped", "source": live_host(lives[0]) + site["live"]["zip"]}
    run.manifest["teacher_live"] = entry
    if not secrets.get("COURSE_LIVE_KEY"):
        if run.daily:
            raise CrawlerError("沒有 COURSE_LIVE_KEY，每日模式一定要有 Live")
        run.log.warning("沒有 COURSE_LIVE_KEY，研究模式跳過 Live")
        entry["error"] = "no_key"
        run.save()
        return
    attempts = run.cfg["crawler"]["live_attempts"]
    wait = run.cfg["crawler"]["live_wait_seconds"]
    if attempts < 1:
        raise CrawlerError("crawler.live_attempts 至少要 1")
    for attempt in range(1, attempts + 1):
        entry["attempts"] = attempt
        try:
            used, live_blob, live_files, live_parsed, skipped = live_fetch(
                run, lives, secrets["COURSE_LIVE_KEY"], stock_ids, max_bytes, max_unzipped)
            entry["source"] = live_host(used) + site["live"]["zip"]
            entry["fallback_from"] = skipped or None   # 前面的入口出了什麼錯；用原本的網址成功時是 None
            check = live_check(stock_rows(live_parsed), run.t, run.phase2_days, cfg["crawler"]["min_stocks_filled"],
                               cfg["crawler"]["closed_days"])
            if run.daily and not check["has_t_row"]:
                raise TransientError(f"Live 還沒有 {run.t} 那列")
            break
        except TransientError as e:
            entry["error"] = str(e)
            if attempt == attempts or not run.can_wait(wait):
                raise CrawlerError(f"Live 抓了 {attempt} 次還是不行：{e}") from None
            run.log.warning("%s；%d 秒後再抓", e, wait)
            run.save()
            run.sleep(wait)
    replace_dir(live_dir, live_files)
    dates = sorted({d for rows in stock_rows(live_parsed).values() for d in rows})
    entry.update({"status": "ok", "error": None, "zip_sha256": sha256_bytes(live_blob),
                  "files_sha256": files_digest(live_files),
                  "date_max": dates[-1], **check})
    if run.daily and not check["prev_day"]:
        raise CrawlerError(f"Live 裡找不到早於 {run.t} 而且填好的日子")
    run.prev_day = check["prev_day"]
    if check["prev_day_never_filled"]:
        run.stale = True
        run.log.warning("前一個交易日 %s 在 Live 裡還沒填，改用 %s", check["prev_day_planned"], check["prev_day"])
    if check["prev_day_missing_stocks"]:
        run.log.warning("%s 這天 %s 沒有資料（多半是停牌），這幾檔自己的特徵會是空白",
                        check["prev_day"], check["prev_day_missing_stocks"])
    run.save()


# ---------------------------------------------------------------- yfinance


class PacedSession(CurlSession):
    """yfinance 用的 session。每個請求（含 cookie、crumb、時區、每一跳轉址）都經過同一個限流器。

    上一個請求結束後至少等 min_interval 秒，再加 0～jitter 秒隨機。轉址不交給 libcurl，自己跟，每一跳也限流。
    回應是 429 時丟 YFRateLimitError，yfinance 就不會再自己多送一次。
    """

    def __init__(self, min_interval=2.0, jitter=1.0, max_redirects=5, *, clock=time.monotonic,
                 sleep=time.sleep, rng=random.random, **kwargs):
        kwargs.setdefault("impersonate", "chrome")
        kwargs["retry"] = 0
        super().__init__(**kwargs)
        self.min_interval, self.jitter, self.max_redirects = min_interval, jitter, max_redirects
        self._clock, self._sleep, self._rng = clock, sleep, rng
        self._lock = threading.Lock()
        self._next_ok = None
        self.requests = 0
        self.redirects = 0

    def _send(self, method, url, **kwargs):
        """真的送出一個請求。測試時換掉這個方法。"""
        return super().request(method, url, **kwargs)

    def _paced(self, method, url, **kwargs):
        with self._lock:
            if self._next_ok is not None:
                wait = self._next_ok - self._clock()
                if wait > 0:
                    self._sleep(wait)
            try:
                return self._send(method, url, **kwargs)
            finally:
                self.requests += 1
                self._next_ok = self._clock() + self.min_interval + self.jitter * self._rng()

    def request(self, method, url, *args, **kwargs):
        if args:
            raise TypeError("PacedSession.request 只接受關鍵字參數")
        kwargs["allow_redirects"] = False
        resp = self._paced(method, url, **kwargs)
        hops = 0
        while resp.status_code in REDIRECT_CODES and hops < self.max_redirects:
            location = resp.headers.get("location") or resp.headers.get("Location")
            if not location:
                break
            hops += 1
            self.redirects += 1
            url = urljoin(url, location)
            kwargs.pop("params", None)
            if resp.status_code == 303 or (resp.status_code in (301, 302) and method.upper() == "POST"):
                method = "GET"
                kwargs.pop("data", None)
                kwargs.pop("json", None)
            resp = self._paced(method, url, **kwargs)
        if resp.status_code == 429:
            from yfinance.exceptions import YFRateLimitError
            raise YFRateLimitError()
        return resp


COOKIE_ERRORS = (KeyError, IndexError, AttributeError, TypeError)


def tolerant_cookie_loader(load):
    """yfinance 1.7.0 的 _load_cookie_curlCffi 遇到快取裡的 cookie 沒有 A3 時丟 KeyError（data.py），19 個序列
    全部失敗，而且之後每次都壞，直到有人刪掉快取。包一層：讀不懂就當成沒有快取（回傳 False），yfinance 會重新拿
    cookie 再存回去。"""

    @functools.wraps(load)
    def wrapper(self, *args, **kwargs):
        try:
            return load(self, *args, **kwargs)
        except COOKIE_ERRORS:
            return False

    wrapper.tolerant = True
    return wrapper


def setup_yfinance(session: PacedSession, cache_dir: Path):
    """把 yfinance 的快取放到 cache_dir、關掉內建重試、出錯要丟例外、所有請求都走 session，壞掉的 cookie 快取當成沒有。

    不要打開 yf.config.debug.logging，也不要把 root logger 設成 DEBUG：yfinance 會印出 crumb 和整個回應。
    """
    import yfinance as yf
    from yfinance.data import YfData

    if not getattr(YfData._load_cookie_curlCffi, "tolerant", False):
        YfData._load_cookie_curlCffi = tolerant_cookie_loader(YfData._load_cookie_curlCffi)
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))
    yf.config.network.retries = 0
    yf.config.debug.hide_exceptions = False
    YfData(session=session)


def yf_end(ticker: str, t: str, cfg):
    """yfinance 的 end。一般序列是 t（交易所當地的午夜，不含）。期貨是「t 那天台北 00:00 的紐約日期」17:30（紐約）。"""
    if ticker in cfg["yfinance"]["futures"]:
        ny_date = datetime.combine(date.fromisoformat(t), dtime(0, 0), TAIPEI).astimezone(NEW_YORK).date()
        return datetime.combine(ny_date, dtime(17, 30), NEW_YORK)
    return t


def num_cell(x) -> str:
    x = float(x)
    return repr(x) if math.isfinite(x) else ""


def volume_cell(x) -> str:
    x = float(x)
    return str(int(x)) if math.isfinite(x) else ""


def frame_to_rows(df) -> list:
    """yfinance 的 DataFrame → [[date, open, high, low, close, adj_close, volume], ...]，日期是交易所當地日期。"""
    need = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"yfinance 少了欄位 {missing}")
    rows = []
    for ts, rec in zip(df.index, df[need].itertuples(index=False)):
        rows.append([ts.date().isoformat()] + [num_cell(v) for v in rec[:5]] + [volume_cell(rec[5])])
    return rows


def hourly_frame_rows(df) -> list:
    """yfinance 1h 的 DataFrame → [[start, open, high, low, close, volume], ...]，start 換成台北時間的 ISO 字串。"""
    need = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"yfinance 少了欄位 {missing}")
    return [[ts.tz_convert(TAIPEI).isoformat()] + [num_cell(v) for v in rec[:4]] + [volume_cell(rec[4])]
            for ts, rec in zip(df.index, df[need].itertuples(index=False))]


class EmptyResult(ValueError):
    """抓回來是空的，或開頭比舊檔晚、最後一天比舊檔早（歷史被截短）。"""


def old_span(old: list, t: str):
    """舊檔的 (第一天, 早於 t 的最後一天)，給 filter_rows 判斷新資料有沒有被截短。沒有舊檔回傳 None。"""
    before = [r[0] for r in old if r[0] < t]
    return (old[0][0], before[-1] if before else None) if old else None


def filter_rows(rows: list, ticker: str, t: str, cfg, span=None):
    """丟掉日期 ≥ t、週末日期的K棒；期貨最後一根量太小只記下來，不丟。回傳 (rows, dropped)。

    span 是 old_span() 的結果。過濾後是空的、開頭比舊檔晚、或最後一天比舊檔早，丟 EmptyResult。
    """
    dropped = {"on_or_after_t": 0, "weekend": 0, "low_volume_last_bar_kept": False}
    kept = []
    for row in rows:
        if row[0] >= t:
            dropped["on_or_after_t"] += 1
        elif date.fromisoformat(row[0]).weekday() >= 5:
            dropped["weekend"] += 1
        else:
            kept.append(row)
    if ticker in cfg["yfinance"]["futures"] and len(kept) >= 22:
        volumes = [to_float(r[6]) for r in kept[-22:-1]]
        volumes = [v for v in volumes if v is not None]
        last = to_float(kept[-1][6]) or 0.0
        if volumes and last < 0.1 * statistics.median(volumes):
            # 使用者 2026-11-05：只記錄。回測時這條會誤丟換月日、量 0 的真結算K棒；盤中那段已經由 end 擋掉
            dropped["low_volume_last_bar_kept"] = True
    if not kept:
        raise EmptyResult("過濾後沒有資料")
    if span and kept[0][0] > span[0]:
        raise EmptyResult("開頭日期比舊檔晚")
    if span and span[1] and kept[-1][0] < span[1]:
        raise EmptyResult("最後一天比舊檔早")
    return kept, dropped


def read_series(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[1:] if rows and tuple(rows[0]) == YF_COLUMNS else []


def rows_to_csv(rows: list) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(YF_COLUMNS)
    writer.writerows(rows)
    return buf.getvalue().encode()


def yf_ticker(session: PacedSession, ticker: str):
    import yfinance as yf
    from yfinance.data import YfData

    YfData.cache_get.cache_clear()
    if YfData()._session is not session:
        raise CrawlerError("yfinance 用的 session 被換掉了，限流會失效")
    return yf.Ticker(ticker, session=session)


def fetch_once(session: PacedSession, ticker: str, start: str, end, timeout) -> list:
    df = yf_ticker(session, ticker).history(start=start, end=end, interval="1d", auto_adjust=False,
                                            actions=False, repair=False, timeout=timeout)
    return frame_to_rows(df)


def fetch_hourly_once(session: PacedSession, ticker: str, start, timeout) -> list:
    """抓 1h。start 是 None 時抓 Yahoo 給的最長一段（730d）。外匯沒有盤前盤後，prepost=True 讓 yfinance
    不再用交易時段過濾K棒。"""
    opts = {"interval": "1h", "auto_adjust": False, "actions": False, "repair": False, "prepost": True,
            "timeout": timeout}
    tk = yf_ticker(session, ticker)
    df = tk.history(period="730d", **opts) if start is None else tk.history(start=start, **opts)
    return hourly_frame_rows(df)


def with_retries(run: Run, label: str, fetch, retries: int):
    """呼叫 fetch()，失敗照 yfinance 的設定重試。回傳 (結果或 None, 嘗試次數, 錯誤種類, 錯誤類別名稱)。"""
    from yfinance.exceptions import YFRateLimitError

    conf = run.cfg["yfinance"]
    kind = name = None
    for attempt in range(1, retries + 2):
        try:
            return fetch(), attempt, None, None
        except CrawlerError:
            raise
        except YFRateLimitError:
            kind, name = "rate_limited", "YFRateLimitError"
        except Exception as e:  # 其他錯誤一律當暫時性，不看訊息文字
            kind, name = "error", type(e).__name__
        if attempt > retries:
            break
        waits = conf["rate_limit_wait_seconds"] if kind == "rate_limited" else conf["retry_wait_seconds"]
        wait = waits[min(attempt - 1, len(waits) - 1)]
        if not run.can_wait(wait):
            name += "（到了爬蟲截止）"
            break
        run.log.warning("%s：%s，%d 秒後重試", label, name, wait)
        run.sleep(wait)
    return None, attempt, kind, name


def fetch_series(run: Run, session: PacedSession, ticker: str, span=None, retries=None):
    """抓一個序列，失敗照設定重試。回傳 (rows 或 None, dropped, 嘗試次數, 錯誤種類, 錯誤類別名稱)。"""
    conf = run.cfg["yfinance"]
    end = yf_end(ticker, run.t, run.cfg)

    def fetch():
        rows = fetch_once(session, ticker, run.cfg["data"]["start"], end, conf["timeout_seconds"])
        return filter_rows(rows, ticker, run.t, run.cfg, span)

    result, attempt, kind, name = with_retries(run, ticker, fetch, conf["max_retries"] if retries is None else retries)
    if result is None:
        return None, None, attempt, kind, name
    return result[0], result[1], attempt, None, None


def read_hourly(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[1:] if rows and tuple(rows[0]) == HOURLY_COLUMNS else []


def hourly_to_csv(rows: list) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HOURLY_COLUMNS)
    writer.writerows(rows)
    return buf.getvalue().encode()


def hourly_start(old: list, t: str, overlap_days: int):
    """1h 從哪天開始抓：舊檔最後一根往前 overlap_days 天。沒有舊檔、或舊檔停在 600 天以前，回傳 None（抓 730d）。"""
    if not old:
        return None
    last = datetime.fromisoformat(old[-1][0]).astimezone(TAIPEI).date()
    if (date.fromisoformat(t) - last).days > 600:
        return None
    return (last - timedelta(days=overlap_days)).isoformat()


def merge_hourly(old: list, new: list, cutoff: datetime) -> list:
    """舊檔和新抓的合併，同一個開始時間用新的；只留結束時間 ≤ cutoff 的K棒，依時間排序。"""
    by_start = {r[0]: r for r in old}
    by_start.update({r[0]: r for r in new})
    keep = [r for r in by_start.values() if datetime.fromisoformat(r[0]) + HOURLY_BAR <= cutoff]
    return sorted(keep, key=lambda r: datetime.fromisoformat(r[0]))


def hourly_has_value(rows: list, target: datetime, lookback_days: int) -> bool:
    """target 之前 lookback_days 天內，有沒有結束時間 ≤ target、close 有值的K棒（features 的 usd_twd_am 取得到值）。"""
    for r in reversed(rows):
        end = datetime.fromisoformat(r[0]) + HOURLY_BAR
        close = to_float(r[4])
        if end <= target and close is not None and close > 0:
            return end > target - timedelta(days=lookback_days)
    return False


def has_bar(rows: list, d: str, need_volume: bool) -> bool:
    for row in reversed(rows):
        if row[0] == d:
            return not need_volume or (to_float(row[6]) or 0) > 0
        if row[0] < d:
            return False
    return False


def download_yfinance(run: Run, session: PacedSession):
    """依 yf_series()（yfinance.tickers，開關切到 yfinance 時加上台指期）逐一下載日K，再抓 yfinance.hourly 的 1h，
    最後檢查每個序列有沒有 i 那根。"""
    conf = run.cfg["yfinance"]
    tickers = yf_series(run.cfg)
    out_dir = run.raw_dir / "yfinance"
    setup_yfinance(session, utils.ROOT / conf["cache_dir"])
    entries = run.manifest.setdefault("yfinance", {})
    data = {}
    breaker = 0

    def record(sid, ticker, status, rows=None, dropped=None, attempts=0, error=None):
        path = out_dir / f"{sid}.csv"
        entry = {"ticker": ticker, "status": status, "file": f"yfinance/{sid}.csv", "attempts": attempts,
                 "error": error}
        if rows is not None:
            payload = rows_to_csv(rows)
            write_atomic(path, payload)
            data[sid] = rows
            entry["dropped"] = dropped
        elif path.exists():
            payload = path.read_bytes()
            data[sid] = read_series(path)
            entry["kept_previous_file"] = True
        else:
            payload = None
        if payload is not None:
            entry.update({"rows": len(data[sid]), "date_max": data[sid][-1][0] if data[sid] else None,
                          "sha256": sha256_bytes(payload)})
        if ticker in conf["futures"]:
            end = yf_end(ticker, run.t, run.cfg)
            entry["end"] = end.isoformat()
        entries[sid] = entry
        run.save()

    for sid, ticker in tickers.items():
        span = old_span(read_series(out_dir / f"{sid}.csv"), run.t)
        if breaker >= conf["breaker_series"]:
            record(sid, ticker, "failed", error="skipped_rate_limit_breaker")
            continue
        if run.past_deadline():
            record(sid, ticker, "failed", error="skipped_deadline")
            continue
        rows, dropped, attempts, kind, name = fetch_series(run, session, ticker, span)
        if rows is None:
            breaker = breaker + 1 if kind == "rate_limited" else 0
            run.log.warning("%s 失敗（%s），沿用舊檔", ticker, name)
            record(sid, ticker, "failed", attempts=attempts, error=name)
        else:
            breaker = 0
            record(sid, ticker, "ok", rows, dropped, attempts)

    # 1h：和舊檔合併，只留結束時間不晚於現在和 t 那天 06:00 的K棒
    am = run.cfg["features"]["usd_twd_am"]
    target = run.at(am["at"])
    for sid, ticker in conf.get("hourly", {}).items():
        path = out_dir / f"{sid}.csv"
        rows = read_hourly(path)
        entry = {"ticker": ticker, "interval": "1h", "file": f"yfinance/{sid}.csv", "attempts": 0, "error": None}
        if breaker >= conf["breaker_series"]:
            entry.update(status="failed", error="skipped_rate_limit_breaker")
        elif run.past_deadline():
            entry.update(status="failed", error="skipped_deadline")
        else:
            start = hourly_start(rows, run.t, conf["hourly_overlap_days"])

            def fetch():
                new = fetch_hourly_once(session, ticker, start, conf["timeout_seconds"])
                if not new:
                    raise EmptyResult("沒有資料")
                return new

            new, attempts, kind, name = with_retries(run, f"{ticker} 1h", fetch, conf["max_retries"])
            entry["attempts"] = attempts
            if new is None:
                breaker = breaker + 1 if kind == "rate_limited" else 0
                run.log.warning("%s 1h 失敗（%s），沿用舊檔", ticker, name)
                entry.update(status="failed", error=name)
            else:
                breaker = 0
                rows = merge_hourly(rows, new, min(run.now(), target))
                write_atomic(path, hourly_to_csv(rows))
                entry.update(status="ok", fetched_rows=len(new), start=start)
        if entry["status"] == "failed" and path.exists():
            entry["kept_previous_file"] = True
        if path.exists():
            entry.update(rows=len(rows), first=rows[0][0] if rows else None, last=rows[-1][0] if rows else None,
                         sha256=sha256_bytes(path.read_bytes()))
        entry["has_value_t"] = hourly_has_value(rows, target, am["lookback_days"])
        entries[sid] = entry
        run.save()

    # 檢查有沒有 i 那根。沒有的不算失敗（外國放假常這樣），列在 run.no_bar_i（使用者 2026-11-06）
    run.no_bar_i = [sid for sid in conf.get("hourly", {}) if not entries[sid]["has_value_t"]]
    if not run.prev_day:
        run.log.warning("不知道前一個交易日，跳過「有沒有那根K棒」的檢查")
        for sid in tickers:
            entries[sid]["has_bar_i"] = None
    else:
        need_volume = set(conf["volume_required"])

        def missing():
            return [sid for sid, ticker in tickers.items()
                    if entries[sid]["status"] == "ok"
                    and not has_bar(data.get(sid, []), run.prev_day, ticker in need_volume)]

        todo = missing()
        if todo and run.can_wait(conf["recheck_wait_seconds"]):
            run.log.info("%s 沒有 %s 那根，%d 秒後一起重抓一次", todo, run.prev_day, conf["recheck_wait_seconds"])
            run.sleep(conf["recheck_wait_seconds"])
            for sid in todo:
                if run.past_deadline():
                    run.log.warning("到了爬蟲截止，不再重抓")
                    break
                ticker = tickers[sid]
                rows, dropped, attempts, _, _ = fetch_series(run, session, ticker, old_span(data.get(sid, []), run.t),
                                                             retries=0)
                if rows is not None:
                    record(sid, ticker, "ok", rows, dropped, entries[sid]["attempts"] + attempts)
        for sid, ticker in tickers.items():
            entries[sid]["has_bar_i"] = sid in data and has_bar(data[sid], run.prev_day, ticker in need_volume)
        run.no_bar_i = [sid for sid in tickers if not entries[sid]["has_bar_i"]] + run.no_bar_i
    for sid in run.no_bar_i:
        if sid in tickers:
            run.log.warning("%s 沒有 %s 那根K棒，這個特徵當天會是空白", sid, run.prev_day)
        else:
            run.log.warning("%s 在 %s %s 前 %d 天內沒有K棒，usd_twd_am 當天會是空白", sid, run.t, am["at"],
                            am["lookback_days"])
    run.save()

    if any(e["status"] != "ok" for e in entries.values()):
        run.stale = True


# ---------------------------------------------------------------- 台指期（期交所）


def tx_source(cfg) -> str:
    """tx_futures.source 的開關（使用者 2026-11-06）。切到 yfinance 但沒填代號就丟 CrawlerError。"""
    tx = cfg["tx_futures"]
    if tx["source"] not in ("taifex", "yfinance"):
        raise CrawlerError("tx_futures.source 只能是 taifex 或 yfinance")
    if tx["source"] == "yfinance":
        tickers = tx.get("yfinance") or {}
        if not any(tickers.values()):
            raise CrawlerError("tx_futures.source 是 yfinance，但 tx_futures.yfinance 沒有填代號")
        if tickers.get("night"):
            # 一般的 yfinance 序列只留日期 < t 的K棒，t 那根夜盤會被丟掉；Yahoo 用哪一天標夜盤也還沒查證，
            # 標成開始那天的話歷史列會用到開盤後的資料（2026-11-06 審查）。查清楚之前不開放。
            raise CrawlerError("tx_futures.yfinance.night 還不支援：要先查證 Yahoo 夜盤K棒標的日期")
    return tx["source"]


def yf_series(cfg) -> dict:
    """要用 yfinance 抓的日K {名稱: 代號}：yfinance.tickers，加上開關切到 yfinance 時的台指期代號。"""
    out = dict(cfg["yfinance"]["tickers"])
    if tx_source(cfg) == "yfinance":
        for session, ticker in cfg["tx_futures"]["yfinance"].items():
            if ticker:
                out[TX_SERIES[session]] = ticker
    return out


def taifex_path(raw_dir: Path, cfg) -> Path:
    return raw_dir / "taifex" / f'{cfg["tx_futures"]["taifex"]["commodity"].lower()}.csv'


def taifex_client(cfg, sleep=time.sleep, session=None, clock=time.monotonic) -> SiteClient:
    conf = cfg["tx_futures"]["taifex"]
    parts = urlsplit(conf["url"])
    return SiteClient(f"{parts.scheme}://{parts.netloc}", conf["timeout_seconds"], conf["max_mb"] * 2**20, session,
                      sleep, cfg["course_site"]["total_timeout_seconds"], clock)


def parse_taifex(data: bytes, commodity: str) -> list:
    """期交所下載的 CSV（CP950）→ 只留 commodity 的單月合約列，每列 19 格，日期 YYYY-MM-DD、去掉前後空白。

    表頭要和 TAIFEX_COLUMNS 一樣，否則多半是「區間太長」之類的提示頁，丟 CrawlerError。沒有交易的區間只有表頭，
    回傳空清單。價差單（到期月份像 202611/202612）不存。
    """
    try:
        text = data.decode("cp950")
    except UnicodeDecodeError:
        raise CrawlerError("期交所：回應不是 CP950 的文字（可能是提示頁）") from None
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error:
        raise CrawlerError("期交所：回應不是正常的 CSV") from None
    n = len(TAIFEX_COLUMNS)
    if not rows or tuple(c.strip() for c in rows[0]) != TAIFEX_COLUMNS:
        raise CrawlerError("期交所：回應的表頭和預期不一樣（區間太長或查詢被拒）")
    out = []
    for r in rows[1:]:
        cells = [c.strip() for c in r]
        if not any(cells):
            continue
        if len(cells) < n or any(cells[n:]):
            raise CrawlerError("期交所：有列的欄數不對")
        cells = cells[:n]
        cells[0] = cells[0].replace("/", "-")
        if not is_iso_date(cells[0]):
            raise CrawlerError("期交所：有看不懂的日期")
        if cells[1] != commodity or not re.fullmatch(r"\d{6}", cells[2]):
            continue
        if cells[17] not in TAIFEX_SESSIONS:
            raise CrawlerError("期交所：有看不懂的交易時段")
        out.append(cells)
    return out


def read_taifex(path: Path) -> list:
    """讀舊的 tx.csv。沒有檔、或表頭不對（當成沒有）回傳空清單；有壞掉的列丟 CrawlerError。"""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
    except (OSError, UnicodeError, csv.Error):
        raise CrawlerError(f"{path.name}：讀不了") from None
    if not rows or tuple(rows[0]) != TAIFEX_COLUMNS:
        return []
    body = [r for r in rows[1:] if r]
    for r in body:
        if len(r) != len(TAIFEX_COLUMNS) or not is_iso_date(r[0]) or r[17] not in TAIFEX_SESSIONS:
            raise CrawlerError(f"{path.name}：有壞掉的列")
    return body


def taifex_to_csv(rows: list) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(TAIFEX_COLUMNS)
    writer.writerows(rows)
    return buf.getvalue().encode()


def taifex_chunks(start: date, end: date) -> list:
    """[start, end] 照月份切開：[(開始, 結束), ...]，每段不跨月（期交所一次最多查一個月）。"""
    out, cur = [], start
    while cur <= end:
        month_end = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        stop = min(month_end, end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def taifex_start(old: list, cfg) -> date:
    """從哪天開始抓：沒有舊檔就從 data.start；有的話從舊檔最後一天往前 overlap_days 天（不早於 data.start）。"""
    first = date.fromisoformat(cfg["data"]["start"])
    if not old:
        return first
    last = date.fromisoformat(max(r[0] for r in old))
    return max(first, last - timedelta(days=cfg["tx_futures"]["taifex"]["overlap_days"]))


def taifex_keep(rows: list, t: str, now: datetime, ready: str):
    """只留開盤前已經知道的列：t 之前的日盤；夜盤到 t 那列為止，t 那列要 now 過了 t 當天 ready（夜盤 05:00 收盤）。"""
    night_ok = now >= datetime.combine(date.fromisoformat(t), dtime.fromisoformat(ready), TAIPEI)
    kept, dropped = [], {"day_on_or_after_t": 0, "night_after_t": 0, "night_t_not_ready": 0}
    for r in rows:
        day, session = r[0], TAIFEX_SESSIONS[r[17]]
        if session == "day" and day >= t:
            dropped["day_on_or_after_t"] += 1
        elif session == "night" and day > t:
            dropped["night_after_t"] += 1
        elif session == "night" and day == t and not night_ok:
            dropped["night_t_not_ready"] += 1
        else:
            kept.append(r)
    return kept, dropped


def merge_taifex(old: list, new: list, start: str, end: str) -> list:
    """[start, end] 裡的日子用新抓的列，其他日子留舊檔；照日期、到期月份、交易時段（日盤先）排序。"""
    rows = {(r[0], r[2], r[17]): r for r in old if not start <= r[0] <= end}
    rows.update({(r[0], r[2], r[17]): r for r in new})
    return [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1], k[2] != "一般"))]


def taifex_has(rows: list, d: str, session: str) -> bool:
    """d 那天的 session（day 或 night）有沒有收盤價。"""
    return any(r[0] == d and TAIFEX_SESSIONS[r[17]] == session and to_float(r[6]) is not None for r in rows)


def download_taifex(run: Run, client: SiteClient):
    """期交所的台指期，和舊檔合併存到 data/raw/taifex/。失敗時舊檔留著、記 failed，不中斷。"""
    cfg = run.cfg
    if tx_source(cfg) != "taifex":
        return
    conf = cfg["tx_futures"]["taifex"]
    url = urlsplit(conf["url"])
    path = taifex_path(run.raw_dir, cfg)
    entry = {"source": url.netloc + url.path, "file": path.relative_to(run.raw_dir).as_posix(), "status": "failed",
             "requests": 0, "error": None}
    run.manifest["taifex"] = entry
    try:
        old = read_taifex(path)
    except CrawlerError as e:
        # 舊檔壞了：這一步算失敗、檔案不動，流程繼續（壞檔要人修，不能自動蓋掉）
        entry["error"] = str(e)
        run.stale = True
        run.log.warning("期交所舊檔有問題（%s），這次不抓", e)
        old, path_ok = [], False
    else:
        path_ok = True
    retries = 0 if run.past_deadline() else conf["retries"]
    sent = [0]

    def request(a: date, b: date) -> list:
        form = {"down_type": "1", "commodity_id": conf["commodity"], "commodity_id2": "",
                "queryStartDate": a.strftime("%Y/%m/%d"), "queryEndDate": b.strftime("%Y/%m/%d")}
        for attempt in range(retries + 1):
            if sent[0]:
                run.sleep(conf["min_interval_seconds"])
            sent[0] += 1
            entry["requests"] = sent[0]
            try:
                return parse_taifex(client.read("POST", url.path, data=form), conf["commodity"])
            except TransientError as e:
                wait = conf["retry_wait_seconds"][min(attempt, len(conf["retry_wait_seconds"]) - 1)]
                if attempt == retries or not run.can_wait(wait):
                    raise
                run.log.warning("期交所 %s～%s：%s，%d 秒後重試", a, b, e, wait)
                run.sleep(wait)

    def fetch(start: date, end: date) -> list:
        rows = [r for a, b in taifex_chunks(start, end) for r in request(a, b)]
        kept, dropped = taifex_keep(rows, run.t, run.now(), conf["night_ready"])
        missing = {r[0] for r in old if start.isoformat() <= r[0] <= end.isoformat()} - {r[0] for r in kept}
        if missing:
            raise CrawlerError(f"期交所回傳的日子比舊檔少 {len(missing)} 天，不覆蓋舊檔")
        entry["dropped"] = dropped
        return merge_taifex(old, kept, start.isoformat(), end.isoformat())

    rows = old
    start, end = taifex_start(old, cfg), min(run.now().date(), date.fromisoformat(run.t))
    entry["start"] = start.isoformat()
    try:
        if not path_ok:
            raise CrawlerError(entry["error"])
        rows = fetch(start, end)
        write_atomic(path, taifex_to_csv(rows))
        entry["status"] = "ok"
    except (CrawlerError, csv.Error, ValueError, IndexError, KeyError) as e:
        # 期交所失敗不能讓整支爬蟲停下（舊檔留著、回傳 3）；不是自己寫的錯誤只記類別
        entry["error"] = str(e) if isinstance(e, CrawlerError) else type(e).__name__
        run.stale = True
        run.log.warning("期交所失敗（%s），沿用舊檔", entry["error"])
    wait = cfg["yfinance"]["recheck_wait_seconds"]
    if entry["status"] == "ok" and run.daily and not taifex_has(rows, run.t, "night") and run.can_wait(wait):
        # 夜盤 05:00 收盤，期交所什麼時候放上網站還沒確認：沒有 t 的夜盤就等一下重抓最近幾天一次
        run.log.info("期交所還沒有 %s 的夜盤，%d 秒後重抓一次", run.t, wait)
        run.sleep(wait)
        old = rows
        try:
            rows = fetch(max(start, end - timedelta(days=conf["overlap_days"])), end)
            write_atomic(path, taifex_to_csv(rows))
            entry["rechecked"] = True
        except (CrawlerError, csv.Error, ValueError, IndexError, KeyError) as e:
            entry["recheck_error"] = str(e) if isinstance(e, CrawlerError) else type(e).__name__
            run.log.warning("期交所重抓失敗（%s），用第一次抓到的", entry["recheck_error"])
    if path.exists():
        entry.update(kept_previous_file=entry["status"] != "ok", rows=len(rows),
                     date_max=max((r[0] for r in rows), default=None), sha256=sha256_bytes(path.read_bytes()))
    # 不知道 i 的時候（研究模式沒有 Live 金鑰）和 yfinance 一樣記 None，不算缺
    entry["has_day_i"] = taifex_has(rows, run.prev_day, "day") if run.prev_day else None
    entry["has_night_t"] = taifex_has(rows, run.t, "night")
    for session, ok in (("day", entry["has_day_i"]), ("night", entry["has_night_t"])):
        if ok is False:
            run.no_bar_i.append(TX_SERIES[session])
            run.log.warning("台指期沒有%s，%s 當天會是空白", f" {run.prev_day} 的日盤" if session == "day"
                            else f" {run.t} 的夜盤", TX_SERIES[session])
    run.save()


# ---------------------------------------------------------------- 主程式


def crawl(run: Run, secrets: dict, *, course=None, live=None, yf_session=None, taifex=None) -> int:
    """依序：/api/state → Training → Live → yfinance → 期交所 → 寫 manifest。回傳 0 或 3，不能繼續就丟 CrawlerError。"""
    cfg = run.cfg
    tx_source(cfg)   # 開關設錯就在送出任何請求前停下
    now = run.now()
    if run.daily and now < run.at(cfg["crawler"]["start_time"]):
        raise CrawlerError(f"每日模式要在 {run.t} {cfg['crawler']['start_time']}（台北）之後才跑")
    try:
        run.previous = json.loads((run.raw_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        run.previous = {}
    run.manifest = {"run": {"started_at": now.isoformat(timespec="seconds"), "target_date": run.t,
                            "mode": "daily" if run.daily else "research", "status": "running"}}
    if isinstance(run.previous.get("teacher"), dict):
        # 先抄上一次的 Training 紀錄：這次如果在下載 Training 前就失敗，下次還認得本機的檔案，不用重下載
        run.manifest["teacher"] = run.previous["teacher"]
    course = course or course_client(cfg, run.sleep)
    live = live or live_clients(cfg, run.sleep)
    lives = live if isinstance(live, (list, tuple)) else [live]
    course.can_wait = run.can_wait   # 過了爬蟲截止，課程網站和 Live 都不再重試
    for client in lives:
        client.can_wait = run.can_wait
    if run.past_deadline():
        run.log.warning("已經過了爬蟲截止 %s：每一步只試一次，不再等待或重試", cfg["crawler"]["deadline"])
    yf_session = yf_session or PacedSession(cfg["yfinance"]["min_interval_seconds"],
                                            cfg["yfinance"]["jitter_seconds"], cfg["yfinance"]["max_redirects"])
    taifex = taifex or taifex_client(cfg, run.sleep)
    taifex.can_wait = run.can_wait
    try:
        course_login(course, cfg, secrets)
        try:
            run.phase2_days = fetch_phase2_days(course, cfg)
            write_atomic(run.raw_dir / "phase2_days.json",
                         (json.dumps(run.phase2_days, ensure_ascii=False, indent=2) + "\n").encode())
            run.manifest["phase2_days"] = {"status": "ok", "file": "phase2_days.json", "days": len(run.phase2_days)}
        except CrawlerError as e:
            cached = cached_phase2_days(run.raw_dir)
            if cached and any(d["tradingDate"] == run.t for d in cached):
                # 使用者 2026-11-06：/api/state 讀不到時改用上次存的清單，前提是裡面有 t
                run.phase2_days, run.stale = cached, True
                run.manifest["phase2_days"] = {"status": "cached", "error": str(e), "file": "phase2_days.json",
                                               "days": len(cached)}
                run.log.warning("讀不到 phase2Days（%s），改用上次存的清單", e)
            elif run.daily:
                raise CrawlerError(f"{e}；上次存的 phase2_days.json 裡也沒有 {run.t}") from None
            else:
                run.manifest["phase2_days"] = {"status": "failed", "error": str(e)}
                run.log.warning("讀不到 phase2Days（%s），研究模式繼續", e)
        run.save()
        download_teacher(run, secrets, course, live)
        download_yfinance(run, yf_session)
        download_taifex(run, taifex)
    except BaseException as e:
        # CrawlerError 的訊息是自己寫的短句；其他例外（OSError、Ctrl-C…）只記類別，訊息可能帶路徑或伺服器內容
        error = str(e) if isinstance(e, CrawlerError) else type(e).__name__
        run.manifest["run"].update({"status": "failed", "error": error,
                                    "finished_at": run.now().isoformat(timespec="seconds")})
        run.save()
        run.log.error("爬蟲停下：%s", error)
        raise
    finally:
        course.close()
        for client in lives:
            client.close()
        yf_session.close()
        taifex.close()
    run.manifest["run"].update({"status": "stale" if run.stale else "ok", "prev_day": run.prev_day,
                                "no_bar_i": run.no_bar_i, "finished_at": run.now().isoformat(timespec="seconds"),
                                "yahoo_requests": yf_session.requests, "yahoo_redirects": yf_session.redirects,
                                "site_requests": course.requests + sum(client.requests for client in lives),
                                "taifex_requests": taifex.requests})
    run.save()
    run.log.info("爬蟲完成：%s", run.manifest["run"]["status"])
    return 3 if run.stale else 0


def main(argv=None) -> int:
    """研究模式不給 --date；每日模式由 run_daily.py 傳 --date t。回傳 0 或 3，不能繼續就丟 CrawlerError。"""
    parser = argparse.ArgumentParser(description="下載老師資料和 yfinance 額外指標到 data/raw/")
    parser.add_argument("--date", help="每日模式：預測日 t（YYYY-MM-DD）。不給就是研究模式，t 取台北今天")
    args = parser.parse_args(argv)
    if args.date and not is_iso_date(args.date):
        parser.error("--date 要是 YYYY-MM-DD")
    cfg = utils.load_config()
    secrets = utils.load_secrets()
    t = args.date or utils.taipei_now().date().isoformat()
    log = utils.get_logger("crawler", t)
    run = Run(cfg=cfg, t=t, daily=bool(args.date), raw_dir=utils.ROOT / cfg["data"]["raw_dir"], log=log)
    return crawl(run, secrets)


if __name__ == "__main__":
    import sys

    sys.exit(main())
