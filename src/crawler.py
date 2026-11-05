"""爬蟲：下載老師資料和 yfinance 額外指標，原樣存到 data/raw/。

輸出：
    data/raw/phase2_days.json      課程網站 /api/state 的 phase2Days（只存日期、enabled、isCompetition）
    data/raw/teacher/              老師 Training ZIP 解開：info.json、global/global_data.csv、market/<代號>.csv
    data/raw/teacher_live/         老師 Live ZIP 解開：global/global_data.csv、market/<代號>.csv（沒有 info.json），每次覆蓋
    data/raw/yfinance/<名稱>.csv   19 個額外指標各一檔：date, open, high, low, close, adj_close, volume
    data/raw/manifest.json         最近一次執行的紀錄：每個檔案的 sha256、筆數、狀態、錯誤類別

兩種模式：
    python -m src.crawler                    研究模式：t 取台北今天，不檢查時間，Live 沒有金鑰就跳過
    python -m src.crawler --date 2026-11-17  每日模式（run_daily.py 用）：t 是預測日，07:00 前不跑，08:30 後不再重試

名詞：
    t   預測日。
    i   t 的前一個台股交易日：phase2Days 裡早於 t 的最後一天（不篩 enabled）。phase2Days 沒有早於 t 的日子時，
        取 Live 裡早於 t、已經填好的最後一天。特徵用的就是 i 那天的值。

老師資料：
    - 兩個 ZIP 裡的路徑開頭都多一層 data/，解壓時拿掉，其他位元組原樣寫出（Live 的 CRLF 也保留）。
    - Training 不會再變。data/raw/teacher/ 的檔案指紋和上次的 manifest 一樣，就不下載 ZIP。
    - Live 每次都下載。t 那列在 t 當天 00:00 新增、先填 -1，^IXIC、^GSPC 約 05:05 前填好，其他欄和 y 在
      t 當天 22:05 前陸續填完。所以早上的 Live 已經有 t 那列，i 那列也填好了。
    - 每日模式要求 Live 有 t 那列；i 那列還沒填（例如 10-23 那種一直是 -1 的日子），就改用早於 t 最後一個
      填好的日子當 i，manifest 記 prev_day_never_filled。
    - -1 不處理。只有 Live 待定格的 -1 是「還沒有」，Training 法人欄有真的 -1。清理留給 features.py。

yfinance：
    - 限流加在 PacedSession（curl_cffi 的 Session）上，yfinance 自己送的 cookie、crumb、時區請求和每一跳轉址
      都要經過：上一個請求結束後至少等 min_interval_seconds，再加 0～jitter_seconds 的隨機。
    - auto_adjust=False，每天重抓 data.start 到 t 前一天的完整歷史（除息後 adj_close 會整欄重算）。
    - 只留日期 < t 的K棒，也丟掉週末日期的K棒。end 只限制請求的範圍，擋不住 Yahoo 附在最後的盤中資料。
    - 期貨（CL=F、GC=F）台北 07:00 後已經開始下一段交易：end 截在紐約 17:30；最後一根成交量低於前 21 根
      中位數的 10% 也丟掉。
    - 抓完檢查每個序列有沒有 i 那根（個股和 ETF 另外要成交量 > 0）。沒有的一起等一下重抓一次，還是沒有就標
      no_bar_i，那個特徵當天空白。

失敗時：
    - yfinance 某個序列失敗：舊檔留著，manifest 記 failed，繼續。main 回傳 3。
    - 抓回來是空的或比舊檔短：當成失敗，不覆蓋舊檔。
    - 老師資料拿不到、Live 沒更新到 t、每日模式讀不到 /api/state、還沒到開始時間：丟 CrawlerError。
      已經寫好的檔案和舊檔都留著。
    - main 回傳 0（全部正常）或 3（有東西不正常但可以繼續），不呼叫 sys.exit。

帳密、金鑰、cookie、crumb、網址 ? 後面的部分和伺服器回應的內容，都不寫進 manifest 和 log。
"""

import argparse
import csv
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
    """讀出資料夾裡所有檔案，回傳 {相對路徑（/ 分隔）: bytes}。"""
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


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

    每個請求都有逾時，邊下載邊數位元組，只跟隨同一個主機的轉址。GET 遇到 429、5xx 或連線錯誤重試 2 次；
    POST（登入）不重試。錯誤訊息只寫路徑和狀態碼，不寫回應內容。
    """

    def __init__(self, base_url: str, timeout, max_bytes: int, session=None, sleep=time.sleep):
        self.base = base_url.rstrip("/")
        self.timeout = tuple(timeout)
        self.max_bytes = max_bytes
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
        self.sleep = sleep

    def close(self):
        self.session.close()

    def read(self, method: str, path: str, *, max_bytes=None, retries=2, **kwargs) -> bytes:
        limit = max_bytes or self.max_bytes
        label = urlsplit(path).path or "/"
        for attempt in range(retries + 1 if method == "GET" else 1):
            try:
                return self._read_once(method, path, limit, label, **kwargs)
            except TransientError:
                if method != "GET" or attempt == retries:
                    raise
                self.sleep(2 ** attempt)
        raise TransientError(f"{label}：重試用完")

    def _read_once(self, method, path, limit, label, **kwargs) -> bytes:
        origin = urlsplit(self.base)
        url = urljoin(self.base + "/", path.lstrip("/"))
        for _ in range(5):
            parts = urlsplit(url)
            if (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc):
                raise CrawlerError(f"{label}：轉址到別的主機，不跟")
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
                    chunks.append(chunk)
                return b"".join(chunks)
            except requests.RequestException as e:
                raise TransientError(f"{label}：下載中斷（{type(e).__name__}）") from None
            finally:
                resp.close()
        raise CrawlerError(f"{label}：轉址太多次")


def course_client(cfg, sleep=time.sleep, session=None) -> SiteClient:
    site = cfg["course_site"]
    return SiteClient(site["base_url"], site["timeout_seconds"], site["max_zip_mb"] * 2**20, session, sleep)


def live_client(cfg, sleep=time.sleep, session=None) -> SiteClient:
    site = cfg["course_site"]
    return SiteClient(site["live"]["base_url"], site["timeout_seconds"], site["max_zip_mb"] * 2**20, session, sleep)


def course_login(course: SiteClient, cfg, secrets):
    raw = course.read("POST", cfg["course_site"]["login"], max_bytes=2**20,
                      json={"email": secrets["COURSE_EMAIL"], "password": secrets["COURSE_PASSWORD"]},
                      headers={"Origin": course.base, "Referer": course.base + "/login"})
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


def live_download(live: SiteClient, cfg, key: str) -> bytes:
    conf = cfg["course_site"]["live"]
    page = live.read("POST", conf["login"], max_bytes=4 * 2**20, data={"key": key},
                     headers={"Origin": live.base, "Referer": live.base + "/"})
    if not re.search(rb'href=["\']' + re.escape(conf["zip"].encode()) + rb'["\']', page):
        raise CrawlerError("Live 登入失敗：頁面沒有下載連結（金鑰可能不對）")
    return live.read("GET", conf["zip"], headers={"Referer": live.base + "/"})


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
        raise CrawlerError(f"{kind} ZIP 的成員不對：多了 {len(extra)} 個 {extra[:3]}，少了 {len(missing)} 個 {missing[:3]}")
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


def day_filled(stocks: dict, d: str) -> bool:
    """d 那天每一檔都有列，y 是 0 或 1，還原開盤價、收盤價都 > 0。法人欄的 -1 不看。"""
    for rows in stocks.values():
        row = rows.get(d)
        if row is None:
            return False
        y, open_, close = to_float(row[COL_Y]), to_float(row[COL_OPEN]), to_float(row[COL_CLOSE])
        if y not in (0.0, 1.0) or not open_ or open_ <= 0 or not close or close <= 0:
            return False
    return True


def live_check(stocks: dict, t: str, phase2_days) -> dict:
    """回傳 has_t_row、prev_day（實際用的 i）、prev_day_planned、prev_day_never_filled。"""
    has_t = bool(stocks) and all(t in rows for rows in stocks.values())
    planned = None
    if phase2_days:
        earlier = [d["tradingDate"] for d in phase2_days if d["tradingDate"] < t]
        planned = earlier[-1] if earlier else None
    if planned and day_filled(stocks, planned):
        return {"has_t_row": has_t, "prev_day": planned, "prev_day_planned": planned, "prev_day_never_filled": False}
    dates = sorted({d for rows in stocks.values() for d in rows if d < t})
    filled = [d for d in dates if day_filled(stocks, d)]
    prev = filled[-1] if filled else None
    return {"has_t_row": has_t, "prev_day": prev, "prev_day_planned": planned,
            "prev_day_never_filled": planned is not None}


# ---------------------------------------------------------------- 老師資料


def download_teacher(run: Run, secrets: dict, course: SiteClient, live: SiteClient):
    """Training（指紋一樣就不下載）和 Live（每次下載），解開到 data/raw/。決定 run.prev_day。"""
    cfg = run.cfg
    site = cfg["course_site"]
    max_bytes, max_unzipped = site["max_zip_mb"] * 2**20, site["max_unzipped_mb"] * 2**20
    teacher_dir, live_dir = run.raw_dir / "teacher", run.raw_dir / "teacher_live"

    # Training
    old = run.previous.get("teacher", {})
    on_disk = dir_files(teacher_dir) if teacher_dir.exists() else {}
    if on_disk and old.get("files_sha256") == files_digest(on_disk):
        run.manifest["teacher"] = {**old, "status": "ok", "action": "skipped_unchanged"}
        run.log.info("Training：本機的檔案和上次一樣，不下載")
    else:
        run.log.info("Training：下載")
        blob = course.read("GET", site["training_zip"], max_bytes=max_bytes)
        files, _ = unpack_zip(blob, "training", max_bytes=max_bytes, max_unzipped=max_unzipped)
        replace_dir(teacher_dir, files)
        run.manifest["teacher"] = {"status": "ok", "action": "downloaded", "zip_sha256": sha256_bytes(blob),
                                   "files_sha256": files_digest(files)}
    run.save()
    stock_ids = read_info((teacher_dir / "info.json").read_bytes())["Top100@Y"]

    # Live
    entry = {"status": "skipped", "source": urlsplit(site["live"]["base_url"]).netloc + site["live"]["zip"]}
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
    for attempt in range(1, attempts + 1):
        entry["attempts"] = attempt
        try:
            blob = live_download(live, cfg, secrets["COURSE_LIVE_KEY"])
            files, parsed = unpack_zip(blob, "live", stock_ids, max_bytes, max_unzipped)
            check = live_check(stock_rows(parsed), run.t, run.phase2_days)
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
    replace_dir(live_dir, files)
    dates = sorted({d for rows in stock_rows(parsed).values() for d in rows})
    entry.update({"status": "ok", "error": None, "zip_sha256": sha256_bytes(blob), "files_sha256": files_digest(files),
                  "date_max": dates[-1], **check})
    if run.daily and not check["prev_day"]:
        raise CrawlerError(f"Live 裡找不到早於 {run.t} 而且填好的日子")
    run.prev_day = check["prev_day"]
    if check["prev_day_never_filled"]:
        run.stale = True
        run.log.warning("前一個交易日 %s 在 Live 裡還沒填，改用 %s", check["prev_day_planned"], check["prev_day"])
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
        self.min_interval, self.jitter, self.max_hops = min_interval, jitter, max_redirects
        self._clock, self._sleep, self._rng = clock, sleep, rng
        self._lock = threading.Lock()
        self._next_ok = None
        self.requests = 0
        self.redirects = 0
        self.slept = 0.0
        self.log = []  # (方法, 網址不含 ? 後面, 狀態碼)

    def _send(self, method, url, **kwargs):
        """真的送出一個請求。測試時換掉這個方法。"""
        return super().request(method, url, **kwargs)

    def _paced(self, method, url, **kwargs):
        with self._lock:
            if self._next_ok is not None:
                wait = self._next_ok - self._clock()
                if wait > 0:
                    self._sleep(wait)
                    self.slept += wait
            status = None
            try:
                resp = self._send(method, url, **kwargs)
                status = resp.status_code
                return resp
            finally:
                self.requests += 1
                self._next_ok = self._clock() + self.min_interval + self.jitter * self._rng()
                self.log.append((method, url.split("?")[0], status))

    def request(self, method, url, *args, **kwargs):
        if args:
            raise TypeError("PacedSession.request 只接受關鍵字參數")
        kwargs["allow_redirects"] = False
        resp = self._paced(method, url, **kwargs)
        hops = 0
        while resp.status_code in REDIRECT_CODES and hops < self.max_hops:
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


def setup_yfinance(session: PacedSession, cache_dir: Path):
    """把 yfinance 的快取放到 cache_dir、關掉內建重試、出錯要丟例外、所有請求都走 session。"""
    import yfinance as yf
    from yfinance.data import YfData

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


def frame_to_rows(df) -> list:
    """yfinance 的 DataFrame → [[date, open, high, low, close, adj_close, volume], ...]，日期是交易所當地日期。"""
    need = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"yfinance 少了欄位 {missing}")

    def num(x):
        x = float(x)
        return repr(x) if math.isfinite(x) else ""

    def vol(x):
        x = float(x)
        return str(int(x)) if math.isfinite(x) else ""

    rows = []
    for ts, rec in zip(df.index, df[need].itertuples(index=False)):
        rows.append([ts.date().isoformat()] + [num(v) for v in rec[:5]] + [vol(rec[5])])
    return rows


class EmptyResult(ValueError):
    """抓回來是空的，或比舊檔短。"""


def filter_rows(rows: list, ticker: str, t: str, cfg, old_first=None):
    """丟掉日期 ≥ t、週末日期的K棒；期貨最後一根量太小也丟。回傳 (rows, dropped)。空的或變短丟 EmptyResult。"""
    dropped = {"on_or_after_t": 0, "weekend": 0, "low_volume_last_bar": False}
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
            kept.pop()
            dropped["low_volume_last_bar"] = True
    if not kept:
        raise EmptyResult("過濾後沒有資料")
    if old_first and kept[0][0] > old_first:
        raise EmptyResult("比舊檔短")
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


def fetch_once(session: PacedSession, ticker: str, start: str, end, timeout) -> list:
    import yfinance as yf
    from yfinance.data import YfData

    YfData.cache_get.cache_clear()
    if YfData()._session is not session:
        raise CrawlerError("yfinance 用的 session 被換掉了，限流會失效")
    df = yf.Ticker(ticker, session=session).history(start=start, end=end, interval="1d", auto_adjust=False,
                                                    actions=False, repair=False, timeout=timeout)
    return frame_to_rows(df)


def fetch_series(run: Run, session: PacedSession, ticker: str, old_first=None, retries=None):
    """抓一個序列，失敗照設定重試。回傳 (rows 或 None, dropped, 嘗試次數, 錯誤種類, 錯誤類別名稱)。"""
    from yfinance.exceptions import YFRateLimitError

    conf = run.cfg["yfinance"]
    retries = conf["max_retries"] if retries is None else retries
    end = yf_end(ticker, run.t, run.cfg)
    kind = name = None
    for attempt in range(1, retries + 2):
        try:
            rows = fetch_once(session, ticker, run.cfg["data"]["start"], end, conf["timeout_seconds"])
            rows, dropped = filter_rows(rows, ticker, run.t, run.cfg, old_first)
            return rows, dropped, attempt, None, None
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
        run.log.warning("%s：%s，%d 秒後重試", ticker, name, wait)
        run.sleep(wait)
    return None, None, attempt, kind, name


def has_bar(rows: list, d: str, need_volume: bool) -> bool:
    for row in reversed(rows):
        if row[0] == d:
            return not need_volume or (to_float(row[6]) or 0) > 0
        if row[0] < d:
            return False
    return False


def download_yfinance(run: Run, session: PacedSession):
    """依 cfg["yfinance"]["tickers"] 逐一下載日K，最後檢查每個序列有沒有 i 那根。"""
    conf = run.cfg["yfinance"]
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

    for sid, ticker in conf["tickers"].items():
        old = read_series(out_dir / f"{sid}.csv")
        old_first = old[0][0] if old else None
        if breaker >= conf["breaker_series"]:
            record(sid, ticker, "failed", error="skipped_rate_limit_breaker")
            continue
        if run.past_deadline():
            record(sid, ticker, "failed", error="skipped_deadline")
            continue
        rows, dropped, attempts, kind, name = fetch_series(run, session, ticker, old_first)
        if rows is None:
            breaker = breaker + 1 if kind == "rate_limited" else 0
            run.log.warning("%s 失敗（%s），沿用舊檔", ticker, name)
            record(sid, ticker, "failed", attempts=attempts, error=name)
        else:
            breaker = 0
            record(sid, ticker, "ok", rows, dropped, attempts)

    # 檢查有沒有 i 那根
    if not run.prev_day:
        run.log.warning("不知道前一個交易日，跳過「有沒有那根K棒」的檢查")
    else:
        need_volume = set(conf["volume_required"])

        def missing():
            return [sid for sid, ticker in conf["tickers"].items()
                    if entries[sid]["status"] == "ok"
                    and not has_bar(data.get(sid, []), run.prev_day, ticker in need_volume)]

        todo = missing()
        if todo and run.can_wait(conf["recheck_wait_seconds"]):
            run.log.info("%s 沒有 %s 那根，%d 秒後一起重抓一次", todo, run.prev_day, conf["recheck_wait_seconds"])
            run.sleep(conf["recheck_wait_seconds"])
            for sid in todo:
                ticker = conf["tickers"][sid]
                old_first = data[sid][0][0] if data.get(sid) else None
                rows, dropped, attempts, _, _ = fetch_series(run, session, ticker, old_first, retries=0)
                if rows is not None:
                    record(sid, ticker, "ok", rows, dropped, entries[sid]["attempts"] + attempts)
            todo = missing()
        for sid in todo:
            entries[sid]["status"] = "no_bar_i"
            run.log.warning("%s 沒有 %s 那根K棒，這個特徵當天會是空白", conf["tickers"][sid], run.prev_day)
        run.save()

    if any(e["status"] != "ok" for e in entries.values()):
        run.stale = True


# ---------------------------------------------------------------- 主程式


def crawl(run: Run, secrets: dict, *, course=None, live=None, yf_session=None) -> int:
    """依序：/api/state → Training → Live → yfinance → 寫 manifest。回傳 0 或 3，不能繼續就丟 CrawlerError。"""
    cfg = run.cfg
    now = run.now()
    if run.daily and now < run.at(cfg["crawler"]["start_time"]):
        raise CrawlerError(f"每日模式要在 {run.t} {cfg['crawler']['start_time']}（台北）之後才跑")
    try:
        run.previous = json.loads((run.raw_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        run.previous = {}
    run.manifest = {"run": {"started_at": now.isoformat(timespec="seconds"), "target_date": run.t,
                            "mode": "daily" if run.daily else "research", "status": "running"}}
    course = course or course_client(cfg, run.sleep)
    live = live or live_client(cfg, run.sleep)
    yf_session = yf_session or PacedSession(cfg["yfinance"]["min_interval_seconds"],
                                            cfg["yfinance"]["jitter_seconds"], cfg["yfinance"]["max_redirects"])
    try:
        course_login(course, cfg, secrets)
        try:
            run.phase2_days = fetch_phase2_days(course, cfg)
            write_atomic(run.raw_dir / "phase2_days.json",
                         (json.dumps(run.phase2_days, ensure_ascii=False, indent=2) + "\n").encode())
            run.manifest["phase2_days"] = {"status": "ok", "file": "phase2_days.json", "days": len(run.phase2_days)}
        except CrawlerError as e:
            if run.daily:
                raise
            run.manifest["phase2_days"] = {"status": "failed", "error": str(e)}
            run.log.warning("讀不到 phase2Days（%s），研究模式繼續", e)
        run.save()
        download_teacher(run, secrets, course, live)
        download_yfinance(run, yf_session)
    except CrawlerError as e:
        run.manifest["run"].update({"status": "failed", "error": str(e),
                                    "finished_at": run.now().isoformat(timespec="seconds")})
        run.save()
        run.log.error("爬蟲停下：%s", e)
        raise
    finally:
        course.close()
        live.close()
        yf_session.close()
    run.manifest["run"].update({"status": "stale" if run.stale else "ok", "prev_day": run.prev_day,
                                "finished_at": run.now().isoformat(timespec="seconds"),
                                "http_requests": yf_session.requests, "redirects": yf_session.redirects})
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
