"""課程網站的 API：登入、/api/state、範本、上傳、下載提交。submit.py 和 run_daily_test.py 共用。

格式是 2026-11-06 從網站前端的程式碼查到的（memory/context/competition.md）：
    上傳：POST /api/submissions，JSON {phase, tradingDate, fileName, payload, note}
          Phase 1 payload：{stockIds: [50], dates: [84], predictions: [[84 個 0/1] × 50]}
          Phase 2 payload：{stockIds: [50], predictions: [50 個 0/1]}
    範本：GET /api/sample-submission?phase=1，或 ?phase=2&tradingDate=t
    下載：GET /api/submissions/{id}?record=current
    /api/state 的時間沒帶時區時當成 UTC（前端也這樣讀）。
網站的錯誤訊息（JSON 的 error）是驗證說明，不含帳密，可以寫進 log。
"""

import csv
import io
import json
import re
from datetime import datetime, timezone

import requests

from src import crawler, utils

SITE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$")
STATE_MAX_BYTES = 8 * 2**20
CSV_MAX_BYTES = 4 * 2**20


class SiteError(RuntimeError):
    """網站回應不對或拒絕。訊息由這個檔案自己寫，最多附上網站 JSON 的 error 欄。"""


def parse_time(text) -> datetime:
    """網站的時間字串 → 有時區的 datetime。沒帶時區的當成 UTC。"""
    if not isinstance(text, str) or not text:
        raise SiteError("網站的時間欄是空的")
    if SITE_TIME.match(text):
        text = text.replace(" ", "T") + "+00:00"
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise SiteError(f"網站的時間格式看不懂：{text[:40]}") from None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def read_csv_text(data: bytes) -> list:
    """網站的 CSV（開頭可能有 BOM）→ 列的清單，每格去掉前後空白。"""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SiteError("CSV 不是 UTF-8") from None
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]
    return [row for row in rows if any(row)]


class Site:
    """登入後的課程網站。一個 Site 用一個 requests.Session（cookie 存登入狀態）。"""

    def __init__(self, cfg: dict, secrets: dict, client=None):
        self.cfg = cfg
        self.client = client or crawler.course_client(cfg)
        crawler.course_login(self.client, cfg, secrets)

    def close(self):
        self.client.close()

    def _json(self, path: str, label: str) -> dict:
        raw = self.client.read("GET", path, max_bytes=STATE_MAX_BYTES)
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SiteError(f"{label}：回應不是 JSON") from None
        if not isinstance(value, dict):
            raise SiteError(f"{label}：回應不是物件")
        return value

    def state(self) -> dict:
        return self._json(self.cfg["course_site"]["state"], "/api/state")

    def template(self, phase: int, t: str | None = None) -> tuple:
        """回傳 (表頭, 股票代號清單)。表頭是 ["id", 日期...]，代號照網站的順序，一律是字串。"""
        site = self.cfg["course_site"]
        path = site["template_phase1"] if phase == 1 else site["template"].format(date=t)
        rows = read_csv_text(self.client.read("GET", path, max_bytes=CSV_MAX_BYTES))
        if len(rows) < 2 or rows[0][0] != "id":
            raise SiteError(f"Phase {phase} 範本的格式不對")
        ids = [row[0] for row in rows[1:]]
        if len(set(ids)) != len(ids) or not all(ids):
            raise SiteError(f"Phase {phase} 範本的代號重複或空白")
        return rows[0], ids

    def download(self, submission_id) -> list:
        """下載網站上目前有效的那份提交，回傳 CSV 的列。"""
        path = self.cfg["course_site"]["submission_file"].format(id=requests.utils.quote(str(submission_id), safe=""))
        return read_csv_text(self.client.read("GET", path, max_bytes=CSV_MAX_BYTES))

    def post_submission(self, body: dict) -> dict:
        """POST 一次，不重試（逾時或連不上就丟 crawler.TransientError，由呼叫的人回去查網站有沒有收到）。

        SiteClient.read 在 HTTP 不是 200 時只回狀態碼；這裡要網站的驗證訊息，所以自己送。
        """
        client = self.client
        url = client.base + self.cfg["course_site"]["submissions"]
        client.requests += 1
        try:
            resp = client.session.post(url, json=body, timeout=client.timeout, allow_redirects=False,
                                       headers={"Origin": client.base, "Referer": client.base + "/"})
        except requests.RequestException as e:
            raise crawler.TransientError(f"上傳：連線失敗（{type(e).__name__}），不知道網站有沒有收到") from None
        try:
            result = resp.json() if resp.content else {}
        except ValueError:
            result = {}
        if resp.status_code != 200:
            message = result.get("error") if isinstance(result, dict) else None
            raise SiteError(f"上傳被拒絕：HTTP {resp.status_code}" + (f"，網站說：{str(message)[:300]}" if message else ""))
        if not isinstance(result, dict) or result.get("error"):
            raise SiteError("上傳的回應不對" + (f"：{str(result.get('error'))[:300]}" if isinstance(result, dict) else ""))
        return result


# ---------------------------------------------------------------- 從 state 取資料


def phase2_day(state: dict, t: str):
    """state 的 phase2Days 裡 t 那筆；沒有回傳 None。"""
    for day in state.get("phase2Days") or []:
        if isinstance(day, dict) and day.get("tradingDate") == t:
            return day
    return None


def day_status(state: dict, t: str) -> str:
    """t 這天在網站上的狀態。休市不寫死在程式裡：每次都看網站的 phase2Days。

    closed：不在清單上（週末、國定假日、颱風假，或網站還沒加這天）。
    not_open：在清單上但 enabled 不是真。我們沒看過這種狀態，可能是臨時休市，也可能是還沒更新
              （使用者 2026-11-07 提醒），所以不當成休市：照常準備，上傳前再看一次，還是停用就這次不送。
    open：在清單上而且 enabled。
    """
    day = phase2_day(state, t)
    if day is None:
        return "closed"
    return "open" if day.get("enabled") else "not_open"


def submission_key(phase: int, t: str | None) -> str:
    """mySubmissions 的 tradingDate：Phase 1 是 'phase1'，Phase 2 是日期。"""
    return "phase1" if phase == 1 else t


def current_entry(state: dict, phase: int, t: str | None):
    """mySubmissions 裡這個 phase（和交易日）目前有效的那筆；沒有回傳 None。"""
    key = submission_key(phase, t)
    found = [s for s in state.get("mySubmissions") or []
             if isinstance(s, dict) and s.get("phase") == phase and s.get("tradingDate") == key]
    if not found:
        return None
    return max(found, key=lambda s: parse_time(s.get("submittedAt")))


def quota(state: dict, phase: int, t: str | None) -> dict:
    """uploadQuota 裡這次要看的那一格（Phase 1 是 phase1；Phase 2 是 phase2ByDate[t]，沒有就用 phase2）。"""
    q = state.get("uploadQuota") or {}
    if phase == 1:
        return q.get("phase1") or {}
    by_date = q.get("phase2ByDate") or {}
    return by_date.get(t) or q.get("phase2") or {}


def quota_left(info: dict):
    """還能上傳幾次；看不出來回傳 None。limit 是 0 或沒有時當成沒有上限（網站的 uploadLimitPerUser 是 0）。"""
    left = []
    for count_key, limit_key in (("teamCount", "teamLimit"), ("userCount", "userLimit")):
        limit, count = info.get(limit_key), info.get(count_key)
        if isinstance(limit, int) and limit > 0:
            if not isinstance(count, int):
                return None
            left.append(limit - count)
    return min(left) if left else None


def to_taipei(value: datetime) -> datetime:
    return value.astimezone(utils.TAIPEI)
