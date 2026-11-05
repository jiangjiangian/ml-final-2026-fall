"""src/crawler.py 的離線測試。

不連網：課程網站、Live、Yahoo 都是測試裡的假伺服器，時鐘也是假的（sleep 只是把時間往後撥）。
老師 ZIP 在測試裡現做，100 檔股票、幾天的資料。
"""

import copy
import io
import json
import logging
import warnings
import zipfile
from datetime import datetime, timedelta
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import pytest
import requests
from curl_cffi.requests import Session as CurlSession

from src import crawler, utils

TAIPEI = ZoneInfo("Asia/Taipei")
NY = ZoneInfo("America/New_York")
STOCKS = [str(1101 + i) for i in range(100)]
SECRETS = {"COURSE_EMAIL": "member@example.com", "COURSE_PASSWORD": "pw-SECRET-123",
           "COURSE_LIVE_KEY": "key-SECRET-456"}


# ---------------------------------------------------------------- 共用的假東西


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("測試不能連網")

    monkeypatch.setattr(CurlSession, "_request_once", boom, raising=False)
    monkeypatch.setattr(requests.Session, "send", boom)


@pytest.fixture(autouse=True)
def fresh_yfdata():
    """yfinance 的 YfData 是全程式共用的單例，crumb、cookie 策略、快取會留到下一個測試。每個測試從新的開始，結果才不看順序。"""
    from yfinance.data import YfData

    def reset():
        YfData._instances.pop(YfData, None)
        YfData.cache_get.cache_clear()

    reset()
    yield
    reset()


class Clock:
    """假時鐘：sleep 只把時間往後撥，順便記下睡了幾秒。"""

    def __init__(self, start: datetime):
        self.t = start
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += timedelta(seconds=seconds)

    def monotonic(self):
        return self.t.timestamp()


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=TAIPEI)


@pytest.fixture
def cfg(tmp_path):
    conf = copy.deepcopy(utils.load_config())
    conf["yfinance"]["tickers"] = {"sox": "^SOX", "etf_0050": "0050.TW"}
    conf["yfinance"]["cache_dir"] = str(tmp_path / "yfcache")
    return conf


def make_run(tmp_path, cfg, clock, t="2026-11-17", daily=True):
    return crawler.Run(cfg=cfg, t=t, daily=daily, raw_dir=tmp_path / "raw", log=logging.getLogger("test.crawler"),
                       now=clock.now, sleep=clock.sleep)


# ---------------------------------------------------------------- 老師 ZIP


def stock_csv(dates, pending=(), crlf=False, real_minus_one=False, empty_cell=False) -> bytes:
    lines = [",".join(crawler.STOCK_COLUMNS)]
    for d in dates:
        if d in pending:
            values = ["-1"] * 20
        else:
            y = "1.0" if crlf else "1"
            values = ["101.5", "100.0", "102", "99", "10", "1000", "5000", "50.1",
                      "-1.0" if real_minus_one else "3", "4", "" if empty_cell else "5", "6",
                      "50", "100", "0.1", "1", "105", "100", "95", y]
        lines.append(",".join([d] + values))
    nl = "\r\n" if crlf else "\n"
    return (nl.join(lines) + nl).encode()


def global_csv(dates, pending=(), crlf=False) -> bytes:
    lines = [",".join(crawler.GLOBAL_COLUMNS)]
    for d in dates:
        values = ["18.5", "25000", "7600", "-1", "-1", "-1"] if d in pending else ["18.5", "25000", "7600", "27000", "4000", "-5000"]
        lines.append(",".join([d] + values))
    nl = "\r\n" if crlf else "\n"
    return (nl.join(lines) + nl).encode()


def make_zip(members) -> bytes:
    """members 是 [(名稱, bytes)]，可以有重複的名稱。"""
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in members:
                zf.writestr(name, data)
    return buf.getvalue()


TRAIN_DATES = ["2026-08-27", "2026-08-28", "2026-08-31"]


def training_members(real_minus_one=False):
    info = json.dumps({"Top50@Y": STOCKS[:50], "Top100@Y": STOCKS}).encode()
    members = [("data/info.json", info), ("data/global/global_data.csv", global_csv(TRAIN_DATES))]
    members += [(f"data/market/{s}.csv", stock_csv(TRAIN_DATES, real_minus_one=real_minus_one and s == STOCKS[0],
                                                   empty_cell=real_minus_one and s == STOCKS[1])) for s in STOCKS]
    return members


def live_members(dates, pending=()):
    members = [("data/global/global_data.csv", global_csv(dates, pending, crlf=True))]
    members += [(f"data/market/{s}.csv", stock_csv(dates, pending, crlf=True)) for s in STOCKS]
    return members


LIVE_DATES = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]


# ---------------------------------------------------------------- 假的課程網站和 Live


class FakeResp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]

    def close(self):
        pass


class FakeHttp:
    """假的 requests.Session。routes 是 {(方法, 路徑): 回應或函式}。"""

    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def request(self, method, url, **kwargs):
        path = "/" + url.split("://", 1)[1].split("/", 1)[1] if url.count("/") > 2 else "/"
        self.calls.append((method, path))
        route = self.routes.get((method, path))
        if route is None:
            return FakeResp(404)
        return route(kwargs) if callable(route) else route

    def close(self):
        pass


def course_fake(training=None, state_days=None, login=None):
    days = state_days or ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]
    state = {"phase2Days": [{"tradingDate": d, "enabled": 1, "isCompetition": 1} for d in days],
             "uploadQuota": 5, "mySubmissions": []}
    return FakeHttp({
        ("POST", "/api/auth/login"): login or FakeResp(200, b'{"success": true}'),
        ("GET", "/api/state"): FakeResp(200, json.dumps(state).encode()),
        ("GET", "/downloads/fin_pred_data.zip"): FakeResp(200, make_zip(training or training_members())),
    })


def live_fake(zip_bytes, login=None):
    return FakeHttp({
        ("POST", "/login"): login or FakeResp(200, b'<a href="/data.zip">download</a>'),
        ("GET", "/data.zip"): zip_bytes if callable(zip_bytes) else FakeResp(200, zip_bytes),
    })


class SequenceHttp:
    """依序回 responses 的假 requests.Session，記下每個請求的方法、網址和 kwargs。"""

    def __init__(self, responses):
        self.responses, self.headers, self.calls = list(responses), {}, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def close(self):
        pass


def site(responses, clock=None, max_bytes=1000):
    http = SequenceHttp(responses)
    sleeps = clock.sleep if clock else (lambda s: None)
    return crawler.SiteClient("https://site.example", (10, 90), max_bytes, http, sleeps), http


# ---------------------------------------------------------------- 假的 Yahoo


def chart_json(symbol, tz, itype, bars):
    """bars 是 [(有時區的 datetime, open, high, low, close, adj_close, volume)]；None 代表回應裡沒有K棒（沒有 timestamp）。"""
    meta = {"currency": "USD", "symbol": symbol, "exchangeTimezoneName": tz, "instrumentType": itype,
            "validRanges": ["1d", "5d", "max"], "priceHint": 2, "timezone": "X", "gmtoffset": 0, "exchangeName": "X"}
    if bars is None:
        return json.dumps({"chart": {"result": [{"meta": meta, "indicators": {"quote": [{}]}}], "error": None}})
    return json.dumps({"chart": {"result": [{
        "meta": meta,
        "timestamp": [int(b[0].timestamp()) for b in bars],
        "indicators": {"quote": [{"open": [b[1] for b in bars], "high": [b[2] for b in bars],
                                  "low": [b[3] for b in bars], "close": [b[4] for b in bars],
                                  "volume": [b[6] for b in bars]}],
                       "adjclose": [{"adjclose": [b[5] for b in bars]}]}}], "error": None}})


class YResp:
    def __init__(self, url, status, text, headers=None):
        self.url, self.status_code, self.text = url, status, text
        self.content = text.encode()
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


def bars_on(days, tz, hhmm="09:30", close=100.0, volume=1000):
    zone = ZoneInfo(tz)
    return [(datetime.fromisoformat(f"{d}T{hhmm}").replace(tzinfo=zone), close, close + 1, close - 1, close, close, volume)
            for d in days]


class FakeYahoo(crawler.PacedSession):
    """換掉 _send 的 PacedSession：照 scenarios 回假的 chart JSON。

    scenarios = {代號: (時區, 種類, bars)}。chart_status = {代號: 狀態碼}，只套用在抓歷史的那種 chart 請求
    （有 period1 參數），時區查詢照常回 200。crumb_status 是 getcrumb 的狀態碼。
    """

    def __init__(self, clock, scenarios):
        super().__init__(2.0, 1.0, 5, clock=clock.monotonic, sleep=clock.sleep, rng=lambda: 0.5)
        self.clock, self.scenarios = clock, scenarios
        self.sent = []  # (時間, 方法, 網址, allow_redirects, params 的鍵)
        self.chart_status = {}
        self.crumb_status = 200

    def _send(self, method, url, **kwargs):
        self.sent.append((self.clock.monotonic(), method, url.split("?")[0], kwargs.get("allow_redirects"),
                          frozenset((kwargs.get("params") or {}).keys())))
        if "fc.yahoo.com" in url:
            return YResp(url, 404, "")
        if "getcrumb" in url:
            return YResp(url, self.crumb_status, "CRUMB" if self.crumb_status == 200 else "Too Many Requests")
        if "/v8/finance/chart/" in url:
            symbol = unquote(url.split("/v8/finance/chart/")[1].split("?")[0])
            status = self.chart_status.get(symbol, 200)
            if status != 200 and "period1" in (kwargs.get("params") or {}):
                return YResp(url, status, "<html>error</html>")
            tz, itype, bars = self.scenarios[symbol]
            return YResp(url, 200, chart_json(symbol, tz, itype, bars))
        if "guce.yahoo.com" in url:
            return YResp(url, 200, "<html>no form</html>")
        return YResp(url, 200, "{}")

    def charts(self, symbol=None):
        return [s for s in self.sent if "/v8/finance/chart/" in s[2] and (symbol is None or s[2].endswith(symbol))]

    def history(self, symbol=None):
        """抓歷史的 chart 請求（有 period1）。時區查詢也打 chart，但不算在這裡。"""
        return [s for s in self.charts(symbol) if "period1" in s[4]]


def default_yahoo(clock):
    days = ["2026-11-12", "2026-11-13", "2026-11-16"]
    return FakeYahoo(clock, {
        "^SOX": ("America/New_York", "INDEX", bars_on(days, "America/New_York", volume=0)),
        "0050.TW": ("Asia/Taipei", "ETF", bars_on(days + ["2026-11-17"], "Asia/Taipei", "09:00")),
    })


# ================================================================ ZIP


def test_training_zip_strips_prefix_and_keeps_bytes():
    members = training_members(real_minus_one=True)
    files, _ = crawler.unpack_zip(make_zip(members), "training")
    assert set(files) == {name[len("data/"):] for name, _ in members}
    for name, data in members:
        assert files[name[len("data/"):]] == data  # 真的 -1.0 和空格都原樣保留


def test_live_zip_keeps_crlf():
    members = live_members(LIVE_DATES, pending={"2026-11-17"})
    files, parsed = crawler.unpack_zip(make_zip(members), "live", STOCKS)
    assert files["market/1101.csv"] == dict(members)["data/market/1101.csv"]
    assert b"\r\n" in files["market/1101.csv"]
    assert parsed["market/1101.csv"][-1][0] == "2026-11-17"


def bad_zips():
    good = live_members(LIVE_DATES)
    yield "多一個成員", good + [("data/../evil.csv", b"x")], crawler.CrawlerError
    yield "少一個成員", good[:-1], crawler.CrawlerError
    yield "名稱重複", good + [good[-1]], crawler.CrawlerError
    wrong = [(n, d.replace(b"etl:adj_close", b"close", 1)) if n.endswith("1101.csv") else (n, d) for n, d in good]
    yield "表頭不對", wrong, crawler.CrawlerError
    info = ("data/info.json", json.dumps({"Top50@Y": STOCKS[:50], "Top100@Y": STOCKS}).encode())
    yield "Live 有 info.json", good + [info], crawler.CrawlerError


@pytest.mark.parametrize("label,members,error", list(bad_zips()), ids=[z[0] for z in bad_zips()])
def test_live_zip_rejected(label, members, error):
    with pytest.raises(error) as e:
        crawler.unpack_zip(make_zip(members), "live", STOCKS)
    assert type(e.value) is error  # 不會自己好的錯誤不能被當成暫時性


def test_zip_error_message_has_no_server_names():
    members = live_members(LIVE_DATES) + [("data/market/EVIL-NAME.csv", b"x")]
    with pytest.raises(crawler.CrawlerError) as e:
        crawler.unpack_zip(make_zip(members), "live", STOCKS)
    assert "EVIL-NAME" not in str(e.value) and "多了 1 個" in str(e.value)


def test_zip_size_limits():
    blob = make_zip(live_members(LIVE_DATES))
    for kwargs in ({"max_bytes": len(blob) - 1}, {"max_unzipped": 1000}):
        with pytest.raises(crawler.CrawlerError) as e:
            crawler.unpack_zip(blob, "live", STOCKS, **kwargs)
        assert type(e.value) is crawler.CrawlerError
    with pytest.raises(crawler.TransientError):
        crawler.unpack_zip(blob[: len(blob) // 2], "live", STOCKS)  # 沒下載完整


# ================================================================ SiteClient（課程網站和 Live 的 HTTP）


def test_site_post_is_not_retried():
    client, http = site([FakeResp(503), FakeResp(200, b"ok")])
    with pytest.raises(crawler.TransientError):
        client.read("POST", "/login", data={"key": "k"})
    assert len(http.calls) == 1  # 登入失敗不自動重試


def test_site_get_retries_5xx():
    clock = Clock(at("2026-11-17", "07:10"))
    client, http = site([FakeResp(503), FakeResp(503), FakeResp(200, b"ok")], clock)
    assert client.read("GET", "/data.zip") == b"ok"
    assert len(http.calls) == 3 and clock.sleeps == [1, 2]


def test_site_redirect_to_other_host_is_refused():
    client, http = site([FakeResp(307, headers={"Location": "https://evil.example/steal"})])
    with pytest.raises(crawler.CrawlerError) as e:
        client.read("POST", "/login", data={"key": "secret"})
    assert type(e.value) is crawler.CrawlerError
    assert len(http.calls) == 1  # 金鑰沒有送到別的主機


def test_site_follows_same_host_redirect_without_libraries():
    client, http = site([FakeResp(303, headers={"Location": "/data.zip"}), FakeResp(200, b"zip")])
    assert client.read("POST", "/login", data={"key": "k"}) == b"zip"
    assert [c[0] for c in http.calls] == ["POST", "GET"]
    assert "data" not in http.calls[1][2]  # 303 改成 GET，表單不再送
    assert all(c[2]["allow_redirects"] is False for c in http.calls)


def test_site_size_limit():
    client, _ = site([FakeResp(200, b"x" * 1001)], max_bytes=1000)
    with pytest.raises(crawler.CrawlerError) as e:
        client.read("GET", "/data.zip")
    assert type(e.value) is crawler.CrawlerError


# ================================================================ Live 有沒有更新到 t


def live_stocks(dates, pending=()):
    _, parsed = crawler.unpack_zip(make_zip(live_members(dates, pending)), "live", STOCKS)
    return crawler.stock_rows(parsed)


def days(*dates):
    return [{"tradingDate": d, "enabled": 1, "isCompetition": 1} for d in dates]


def test_live_check_normal_morning():
    stocks = live_stocks(LIVE_DATES, pending={"2026-11-17"})
    check = crawler.live_check(stocks, "2026-11-17", days("2026-11-13", "2026-11-16", "2026-11-17"), 90)
    assert check == {"has_t_row": True, "prev_day": "2026-11-16", "prev_day_planned": "2026-11-16",
                     "prev_day_never_filled": False, "prev_day_missing_stocks": []}


def test_live_check_suspended_stocks():
    stocks = live_stocks(LIVE_DATES, pending={"2026-11-17"})
    calendar = days("2026-11-13", "2026-11-16", "2026-11-17")
    for code in STOCKS[60:62]:  # 兩檔從 11-16 起停牌：沒有列
        del stocks[code]["2026-11-16"], stocks[code]["2026-11-17"]
    check = crawler.live_check(stocks, "2026-11-17", calendar, 90)
    assert check["has_t_row"] is True and check["prev_day"] == "2026-11-16"
    assert check["prev_day_never_filled"] is False and check["prev_day_missing_stocks"] == STOCKS[60:62]
    for code in STOCKS[62:71]:  # 停牌的變成 11 檔：只剩 89 檔，不算數
        del stocks[code]["2026-11-16"], stocks[code]["2026-11-17"]
    check = crawler.live_check(stocks, "2026-11-17", calendar, 90)
    assert check["has_t_row"] is False and check["prev_day"] == "2026-11-13" and check["prev_day_never_filled"] is True


def test_live_check_never_filled_day_falls_back():
    # 10-23 整列一直是 -1，10-26 放假沒有列
    stocks = live_stocks(["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-27"], pending={"2026-10-23", "2026-10-27"})
    check = crawler.live_check(stocks, "2026-10-27", days("2026-10-22", "2026-10-23", "2026-10-27"), 90)
    assert check["prev_day"] == "2026-10-22"
    assert check["prev_day_planned"] == "2026-10-23"
    assert check["prev_day_never_filled"] is True


def test_live_check_does_not_filter_enabled():
    stocks = live_stocks(LIVE_DATES, pending={"2026-11-17"})
    calendar = days("2026-11-13", "2026-11-16", "2026-11-17")
    calendar[1]["enabled"] = 0
    check = crawler.live_check(stocks, "2026-11-17", calendar, 90)
    assert check["prev_day"] == check["prev_day_planned"] == "2026-11-16"
    assert check["prev_day_never_filled"] is False


def test_live_check_without_t_row():
    stocks = live_stocks(LIVE_DATES[:-1])
    assert crawler.live_check(stocks, "2026-11-17", days("2026-11-16"), 90)["has_t_row"] is False


# ================================================================ yfinance 的日期和檢查


def test_yf_end(cfg):
    assert crawler.yf_end("^SOX", "2026-11-17", cfg) == "2026-11-17"
    tue = crawler.yf_end("CL=F", "2026-11-17", cfg)
    assert tue == datetime(2026, 11, 16, 17, 30, tzinfo=NY)
    mon = crawler.yf_end("GC=F", "2026-11-16", cfg)  # 週一的 t：截在週日 17:30，週日晚上那段進不來
    assert mon == datetime(2026, 11, 15, 17, 30, tzinfo=NY)


def row(d, volume="1000", close="100.0"):
    return [d, close, close, close, close, close, volume]


def test_filter_rows_drops_t_and_weekend(cfg):
    rows = [row("2026-11-13"), row("2026-11-14"), row("2026-11-16"), row("2026-11-17")]
    kept, dropped = crawler.filter_rows(rows, "^SOX", "2026-11-17", cfg)
    assert [r[0] for r in kept] == ["2026-11-13", "2026-11-16"]
    assert dropped == {"on_or_after_t": 1, "weekend": 1, "low_volume_last_bar_kept": False}


def test_filter_rows_futures_low_volume_last_bar(cfg):
    dates = [(datetime(2026, 10, 5) + timedelta(days=i)).date().isoformat() for i in range(40)]
    rows = [row(d, "300000") for d in dates if datetime.fromisoformat(d).weekday() < 5]
    rows.append(row("2026-11-16", "4200"))
    kept, dropped = crawler.filter_rows(rows, "CL=F", "2026-11-17", cfg)
    assert kept[-1][0] == "2026-11-16" and dropped["low_volume_last_bar_kept"] is True  # 只記錄，不丟


def test_filter_rows_empty_or_shorter(cfg):
    t = "2026-11-17"
    with pytest.raises(crawler.EmptyResult):
        crawler.filter_rows([row(t)], "^SOX", t, cfg)
    old = [row("2020-01-02"), row("2026-11-13"), row("2026-11-16")]
    span = crawler.old_span(old, t)
    assert span == ("2020-01-02", "2026-11-16")
    with pytest.raises(crawler.EmptyResult, match="開頭"):
        crawler.filter_rows([row("2026-11-13"), row("2026-11-16")], "^SOX", t, cfg, span)
    with pytest.raises(crawler.EmptyResult, match="最後一天"):
        crawler.filter_rows([row("2020-01-02"), row("2026-11-13")], "^SOX", t, cfg, span)  # 歷史被截短
    kept, _ = crawler.filter_rows([row("2020-01-02"), row("2026-11-16")], "^SOX", t, cfg, span)
    assert len(kept) == 2
    # 用比較早的 t 重跑：舊檔裡晚於 t 的那幾天不算，所以不會被誤擋
    kept, _ = crawler.filter_rows([row("2020-01-02"), row("2026-11-12")], "^SOX", "2026-11-13", cfg,
                                  crawler.old_span(old, "2026-11-13"))
    assert kept[-1][0] == "2026-11-12"


def test_has_bar_volume_rule():
    assert crawler.has_bar([row("2026-11-16", "0")], "2026-11-16", need_volume=False)  # ^SOX 量永遠是 0
    assert not crawler.has_bar([row("2026-11-16", "0")], "2026-11-16", need_volume=True)  # NVDA 量 0 不行
    assert not crawler.has_bar([row("2026-11-13")], "2026-11-16", need_volume=False)


# ================================================================ 限流


class Recorder(crawler.PacedSession):
    def __init__(self, clock, responses):
        super().__init__(2.0, 1.0, 5, clock=clock.monotonic, sleep=clock.sleep, rng=lambda: 0.5)
        self.clock, self.responses, self.sent = clock, list(responses), []

    def _send(self, method, url, **kwargs):
        self.sent.append((self.clock.monotonic(), method, url, kwargs.get("allow_redirects")))
        self.clock.t += timedelta(seconds=0.3)  # 請求本身花 0.3 秒
        return self.responses.pop(0)


def gaps(sent):
    """相鄰兩個請求送出時間的差，扣掉 1 毫秒的浮點誤差。"""
    return [b[0] - a[0] + 1e-3 for a, b in zip(sent, sent[1:])]


def test_paced_session_spacing_counts_from_end():
    clock = Clock(at("2026-11-17", "07:10"))
    s = Recorder(clock, [YResp("u", 200, "") for _ in range(3)])
    for _ in range(3):
        s.get("https://example.com/a")
    assert all(g >= 0.3 + 2.0 + 0.5 for g in gaps(s.sent))  # 上一個結束後 2 秒加隨機 0.5


def test_paced_session_follows_redirects_itself():
    clock = Clock(at("2026-11-17", "07:10"))
    s = Recorder(clock, [YResp("u", 302, "", {"location": "/b?x=1"}), YResp("u", 200, "ok")])
    resp = s.get("https://example.com/a", params={"crumb": "c"})
    assert resp.status_code == 200
    assert [x[2] for x in s.sent] == ["https://example.com/a", "https://example.com/b?x=1"]
    assert all(x[3] is False for x in s.sent)  # libcurl 不自己跟轉址
    assert gaps(s.sent)[0] >= 2.0
    assert s.redirects == 1


def test_paced_session_429_raises():
    from yfinance.exceptions import YFRateLimitError

    clock = Clock(at("2026-11-17", "07:10"))
    s = Recorder(clock, [YResp("u", 429, "Too Many Requests")])
    with pytest.raises(YFRateLimitError):
        s.get("https://query2.finance.yahoo.com/v8/finance/chart/X")


# ================================================================ 和 yfinance 接起來


def test_yfinance_requests_are_all_paced(tmp_path):
    from yfinance.data import YfData

    clock = Clock(at("2026-11-17", "07:10"))
    s = default_yahoo(clock)
    crawler.setup_yfinance(s, tmp_path / "yfc")
    assert YfData()._session is s
    rows = crawler.fetch_once(s, "^SOX", "2020-01-01", "2026-11-17", 30)
    crawler.fetch_once(s, "0050.TW", "2020-01-01", "2026-11-17", 30)
    assert [r[0] for r in rows] == ["2026-11-12", "2026-11-13", "2026-11-16"]
    urls = [x[2] for x in s.sent]
    assert any("fc.yahoo.com" in u for u in urls) and any("getcrumb" in u for u in urls)
    assert all(g >= 2.5 for g in gaps(s.sent))


def test_chart_429_is_not_resent(tmp_path):
    from yfinance.exceptions import YFRateLimitError

    clock = Clock(at("2026-11-17", "07:10"))
    s = default_yahoo(clock)
    crawler.setup_yfinance(s, tmp_path / "yfc")
    s.chart_status["^SOX"] = 429
    with pytest.raises(YFRateLimitError):
        crawler.fetch_once(s, "^SOX", "2020-01-01", "2026-11-17", 30)
    history = s.history("^SOX")
    assert len(history) == 1  # yfinance 自己的「換 cookie 策略再送一次」被擋住
    assert history[0] is s.sent[-1]  # 429 之後什麼都沒再送
    assert history[0][3] is False


def test_getcrumb_429_still_fetches_chart(tmp_path):
    clock = Clock(at("2026-11-17", "07:10"))
    s = default_yahoo(clock)
    crawler.setup_yfinance(s, tmp_path / "yfc")
    s.crumb_status = 429
    rows = crawler.fetch_once(s, "^SOX", "2020-01-01", "2026-11-17", 30)
    assert rows
    crumbs = [x for x in s.sent if "getcrumb" in x[2]]
    assert crumbs  # 真的送了 getcrumb，而且它回 429
    history = s.history("^SOX")
    assert len(history) == 1 and "crumb" not in history[0][4]  # 沒有 crumb 也照樣抓
    assert all(g >= 2.5 for g in gaps(s.sent))


def test_retry_after_cache_clear_sends_a_new_request(tmp_path, cfg):
    """t 用過去的日期，yfinance 才會走 lru 快取；沒有 cache_clear 的話重試只會重播舊的錯誤。"""
    import yfinance as yf

    clock = Clock(at("2026-11-04", "07:10"))
    s = FakeYahoo(clock, {"0050.TW": ("Asia/Taipei", "ETF", bars_on(["2026-11-02", "2026-11-03"], "Asia/Taipei", "09:00"))})
    crawler.setup_yfinance(s, tmp_path / "yfc")
    run = make_run(tmp_path, cfg, clock, t="2026-11-04", daily=False)
    s.chart_status["0050.TW"] = 500
    real_sleep = clock.sleep

    def sleep_and_recover(seconds):
        s.chart_status.clear()  # 第一次失敗後，伺服器恢復
        real_sleep(seconds)

    run.sleep = sleep_and_recover
    rows, _, attempts, _, _ = crawler.fetch_series(run, s, "0050.TW")
    assert [r[0] for r in rows] == ["2026-11-02", "2026-11-03"] and attempts == 2

    # 反向對照：不清快取直接再抓一次，完全不會送 chart，證明上面真的有走到快取那條路
    before = len(s.charts())
    yf.Ticker("0050.TW", session=s).history(start="2020-01-01", end="2026-11-04", interval="1d", auto_adjust=False,
                                          actions=False, repair=False, timeout=30)  # timeout 也是快取 key 的一部分
    assert len(s.charts()) == before


def test_futures_intraday_row_is_cut(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    settled = [(datetime(2026, 11, d, tzinfo=NY), 58.0, 61.0, 57.0, close, close, 300000)
               for d, close in ((12, 58.5), (13, 59.0), (16, 60.0))]
    intraday = (datetime(2026, 11, 16, 18, 10, tzinfo=NY), 60.4, 60.6, 60.3, 60.55, 60.55, 4200)
    s = FakeYahoo(clock, {"CL=F": ("America/New_York", "FUTURE", settled + [intraday])})
    crawler.setup_yfinance(s, tmp_path / "yfc")
    run = make_run(tmp_path, cfg, clock)
    rows, *_ = crawler.fetch_series(run, s, "CL=F")
    assert rows[-1][0] == "2026-11-16" and rows[-1][4] == "60.0" and rows[-1][6] == "300000"


def test_futures_sunday_session_is_cut_for_monday(tmp_path, cfg):
    clock = Clock(at("2026-11-16", "07:10"))
    settled = [(datetime(2026, 11, d, tzinfo=NY), 58.0, 61.0, 57.0, 59.0, 59.0, 300000) for d in (12, 13)]
    sunday = (datetime(2026, 11, 15, 18, 10, tzinfo=NY), 59.2, 59.4, 59.1, 59.3, 59.3, 3100)
    s = FakeYahoo(clock, {"GC=F": ("America/New_York", "FUTURE", settled + [sunday])})
    crawler.setup_yfinance(s, tmp_path / "yfc")
    run = make_run(tmp_path, cfg, clock, t="2026-11-16")
    rows, *_ = crawler.fetch_series(run, s, "GC=F")
    assert [r[0] for r in rows] == ["2026-11-12", "2026-11-13"]


def test_empty_result_keeps_old_file(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    cfg["yfinance"]["tickers"] = {"sox": "^SOX"}
    s = FakeYahoo(clock, {"^SOX": ("America/New_York", "INDEX", bars_on(["2026-11-17"], "America/New_York"))})
    run = make_run(tmp_path, cfg, clock, daily=False)
    old = crawler.rows_to_csv([row("2020-01-02"), row("2026-11-13")])
    crawler.write_atomic(run.raw_dir / "yfinance" / "sox.csv", old)
    crawler.download_yfinance(run, s)
    assert (run.raw_dir / "yfinance" / "sox.csv").read_bytes() == old
    entry = run.manifest["yfinance"]["sox"]
    assert entry["status"] == "failed" and entry["kept_previous_file"] is True
    assert entry["attempts"] == cfg["yfinance"]["max_retries"] + 1
    assert [x for x in clock.sleeps if x >= 5] == cfg["yfinance"]["retry_wait_seconds"]  # 其他是限流的 2.5 秒


def test_bar_i_check_rechecks_once(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    cfg["yfinance"]["tickers"] = {"sox": "^SOX", "nvda": "NVDA", "tsm_adr": "TSM"}
    ny = "America/New_York"
    s = FakeYahoo(clock, {
        "^SOX": (ny, "INDEX", bars_on(["2026-11-13", "2026-11-16"], ny, volume=0)),  # 量 0 但不用查量
        "NVDA": (ny, "EQUITY", bars_on(["2026-11-13", "2026-11-16"], ny, volume=0)),  # 量 0，要查量
        "TSM": (ny, "EQUITY", bars_on(["2026-11-12", "2026-11-13"], ny)),  # 沒有 11-16
    })
    run = make_run(tmp_path, cfg, clock)
    run.prev_day = "2026-11-16"
    wait = cfg["yfinance"]["recheck_wait_seconds"]

    def sleep(seconds):
        if seconds == wait:  # 等的這段時間 Yahoo 補上了 TSM 的 11-16
            s.scenarios["TSM"] = (ny, "EQUITY", bars_on(["2026-11-12", "2026-11-13", "2026-11-16"], ny))
        clock.sleep(seconds)

    run.sleep = sleep
    crawler.download_yfinance(run, s)
    entries = run.manifest["yfinance"]
    assert {sid: e["status"] for sid, e in entries.items()} == {"sox": "ok", "nvda": "no_bar_i", "tsm_adr": "ok"}
    assert entries["tsm_adr"]["attempts"] == 2
    assert clock.sleeps.count(wait) == 1
    # 只重抓缺的：^SOX 1 次，NVDA、TSM 各 2 次
    assert [len(s.history(x)) for x in ("^SOX", "NVDA", "TSM")] == [1, 2, 2]
    assert run.stale is True


def test_recheck_stops_at_deadline(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "08:20"))
    cfg["yfinance"]["tickers"] = {"nvda": "NVDA", "tsm_adr": "TSM"}
    ny = "America/New_York"
    s = FakeYahoo(clock, {x: (ny, "EQUITY", bars_on(["2026-11-12", "2026-11-13"], ny)) for x in ("NVDA", "TSM")})
    run = make_run(tmp_path, cfg, clock)
    run.prev_day = "2026-11-16"
    wait = cfg["yfinance"]["recheck_wait_seconds"]

    def sleep(seconds):
        clock.sleep(seconds)
        if seconds == wait:
            clock.t = at("2026-11-17", "08:29:58")  # 等完重抓的 60 秒，離截止只剩 2 秒

    run.sleep = sleep
    crawler.download_yfinance(run, s)
    assert clock.sleeps.count(wait) == 1
    # NVDA 重抓一次後就過了 08:30，TSM 不再重抓
    assert [len(s.history(x)) for x in ("NVDA", "TSM")] == [2, 1]


def test_rate_limit_waits_and_breaker(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    cfg["yfinance"]["tickers"] = {"a": "AAA", "b": "BBB", "c": "CCC"}
    ny = "America/New_York"
    s = FakeYahoo(clock, {x: (ny, "EQUITY", bars_on(["2026-11-16"], ny)) for x in ("AAA", "BBB", "CCC")})
    s.chart_status = {"AAA": 429, "BBB": 429, "CCC": 429}
    run = make_run(tmp_path, cfg, clock, daily=False)
    crawler.download_yfinance(run, s)
    entries = run.manifest["yfinance"]
    waits = cfg["yfinance"]["rate_limit_wait_seconds"]
    for sid in ("a", "b"):
        assert entries[sid]["status"] == "failed" and entries[sid]["error"] == "YFRateLimitError"
        assert entries[sid]["attempts"] == cfg["yfinance"]["max_retries"] + 1
    assert [x for x in clock.sleeps if x >= 5] == waits * 2
    assert entries["c"]["error"] == "skipped_rate_limit_breaker" and not s.history("CCC")


def test_prices_missing_is_retried(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    cfg["yfinance"]["tickers"] = {"sox": "^SOX"}
    s = FakeYahoo(clock, {"^SOX": ("America/New_York", "INDEX", None)})  # chart 沒有任何K棒
    run = make_run(tmp_path, cfg, clock, daily=False)
    crawler.download_yfinance(run, s)
    entry = run.manifest["yfinance"]["sox"]
    assert entry["status"] == "failed" and entry["attempts"] == cfg["yfinance"]["max_retries"] + 1
    assert entry["error"] == "YFPricesMissingError"  # 也確認 hide_exceptions 是關的，錯誤真的丟出來
    assert [x for x in clock.sleeps if x >= 5] == cfg["yfinance"]["retry_wait_seconds"]


def test_yfinance_after_deadline_skips_everything(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "08:31"))
    s = default_yahoo(clock)
    run = make_run(tmp_path, cfg, clock)
    old = crawler.rows_to_csv([row("2020-01-02"), row("2026-11-13")])
    crawler.write_atomic(run.raw_dir / "yfinance" / "sox.csv", old)
    crawler.download_yfinance(run, s)
    assert {e["error"] for e in run.manifest["yfinance"].values()} == {"skipped_deadline"}
    assert (run.raw_dir / "yfinance" / "sox.csv").read_bytes() == old
    assert not s.history()


def test_yfinance_failure_near_deadline_does_not_retry(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "08:29:50"))
    cfg["yfinance"]["tickers"] = {"etf_0050": "0050.TW"}
    s = default_yahoo(clock)
    s.chart_status["0050.TW"] = 500
    run = make_run(tmp_path, cfg, clock)
    crawler.download_yfinance(run, s)
    entry = run.manifest["yfinance"]["etf_0050"]
    assert entry["attempts"] == 1 and entry["error"].endswith("（到了爬蟲截止）")
    assert not [x for x in clock.sleeps if x >= 5]


# ================================================================ 整個流程


def crawl(tmp_path, cfg, clock, *, t="2026-11-17", daily=True, course=None, live=None, yahoo=None, secrets=SECRETS):
    run = make_run(tmp_path, cfg, clock, t=t, daily=daily)
    course = crawler.course_client(cfg, clock.sleep, course or course_fake())
    live = crawler.live_client(cfg, clock.sleep, live or live_fake(make_zip(live_members(LIVE_DATES, {"2026-11-17"}))))
    code = crawler.crawl(run, secrets, course=course, live=live, yf_session=yahoo or default_yahoo(clock))
    return code, run


def test_daily_run_happy_path_and_training_skip(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    code, run = crawl(tmp_path, cfg, clock)
    assert code == 0
    raw = run.raw_dir
    manifest = json.loads((raw / "manifest.json").read_text())
    assert manifest["run"]["status"] == "ok" and manifest["run"]["prev_day"] == "2026-11-16"
    assert manifest["teacher"]["action"] == "downloaded"
    assert {e["status"] for e in manifest["yfinance"].values()} == {"ok"}
    assert (raw / "teacher" / "info.json").exists() and (raw / "teacher_live" / "market" / "1101.csv").exists()
    assert b"\r\n" in (raw / "teacher_live" / "market" / "1101.csv").read_bytes()
    assert json.loads((raw / "phase2_days.json").read_text())[0]["tradingDate"] == "2026-11-12"
    etf = crawler.read_series(raw / "yfinance" / "etf_0050.csv")
    assert etf[-1][0] == "2026-11-16"  # t 那天的K棒沒有存進來

    course = course_fake()
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:45")), course=course)
    assert code == 0 and run.manifest["teacher"]["action"] == "skipped_unchanged"
    assert ("GET", "/downloads/fin_pred_data.zip") not in course.calls

    (raw / "teacher" / ".DS_Store").write_bytes(b"finder")  # Finder 留下的檔不算
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:50")))
    assert run.manifest["teacher"]["action"] == "skipped_unchanged"

    original = (raw / "teacher" / "market" / "1101.csv").read_bytes()
    (raw / "teacher" / "market" / "1101.csv").write_bytes(original.replace(b"101.5", b"999.9", 1))
    course = course_fake()
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:55")), course=course)
    assert run.manifest["teacher"]["action"] == "downloaded"  # 本機的檔被改過就重新下載
    assert ("GET", "/downloads/fin_pred_data.zip") in course.calls
    assert (raw / "teacher" / "market" / "1101.csv").read_bytes() == original


def test_failed_run_keeps_training_fingerprint(tmp_path, cfg):
    crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")))
    broken = course_fake()
    broken.routes[("GET", "/api/state")] = FakeResp(500)
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:20")), course=broken)
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text())
    assert manifest["run"]["status"] == "failed" and manifest["teacher"]["files_sha256"]
    course = course_fake()
    crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:45")), course=course)
    assert ("GET", "/downloads/fin_pred_data.zip") not in course.calls


def test_unexpected_error_marks_run_failed(tmp_path, cfg):
    def disk_error(kwargs):
        raise OSError("/Users/someone/private/path")

    course = course_fake()
    course.routes[("GET", "/downloads/fin_pred_data.zip")] = disk_error
    with pytest.raises(OSError):
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), course=course)
    manifest = (tmp_path / "raw" / "manifest.json").read_text()
    assert json.loads(manifest)["run"]["status"] == "failed"
    assert json.loads(manifest)["run"]["error"] == "OSError"
    assert "/Users/someone" not in manifest  # 例外訊息可能帶路徑，不寫進 manifest


def test_live_attempts_must_be_positive(tmp_path, cfg):
    cfg["crawler"]["live_attempts"] = 0
    with pytest.raises(crawler.CrawlerError, match="live_attempts"):
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")))
    assert not (tmp_path / "raw" / "teacher_live").exists()  # 沒有把 Training 的檔寫進 teacher_live/


def test_daily_run_before_start_time_refuses(tmp_path, cfg):
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, Clock(at("2026-11-16", "23:00")))  # 前一晚：美股還在盤中
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "06:30")))


def test_live_without_t_row_retries_then_stops(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    live_dir = tmp_path / "raw" / "teacher_live"
    live_dir.mkdir(parents=True)
    (live_dir / "old.csv").write_bytes(b"old")
    no_t = live_fake(make_zip(live_members(LIVE_DATES[:-1])))
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, clock, live=no_t)
    assert clock.sleeps.count(cfg["crawler"]["live_wait_seconds"]) == cfg["crawler"]["live_attempts"] - 1
    assert (live_dir / "old.csv").read_bytes() == b"old"
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text())
    assert manifest["run"]["status"] == "failed"


def test_live_near_deadline_does_not_wait(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "08:28"))
    no_t = live_fake(make_zip(live_members(LIVE_DATES[:-1])))
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, clock, live=no_t)
    assert cfg["crawler"]["live_wait_seconds"] not in clock.sleeps


def test_bad_live_zip_keeps_old_dir(tmp_path, cfg):
    clock = Clock(at("2026-11-17", "07:10"))
    live_dir = tmp_path / "raw" / "teacher_live"
    live_dir.mkdir(parents=True)
    (live_dir / "old.csv").write_bytes(b"old")
    members = live_members(LIVE_DATES, {"2026-11-17"})
    bad = [(n, d.replace(b"RSI", b"rsi")) for n, d in members]
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, clock, live=live_fake(make_zip(bad)))
    assert sorted(p.name for p in live_dir.iterdir()) == ["old.csv"]
    assert cfg["crawler"]["live_wait_seconds"] not in clock.sleeps  # 表頭不對不會自己好，不重抓


def test_missing_live_key(tmp_path, cfg):
    no_key = {**SECRETS, "COURSE_LIVE_KEY": ""}
    with pytest.raises(crawler.CrawlerError):
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), secrets=no_key)
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), daily=False, secrets=no_key)
    assert run.manifest["teacher_live"]["status"] == "skipped" and code == 0


def test_never_filled_prev_day_continues_with_3(tmp_path, cfg):
    clock = Clock(at("2026-10-27", "07:10"))
    dates = ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-27"]
    live = live_fake(make_zip(live_members(dates, {"2026-10-23", "2026-10-27"})))
    course = course_fake(state_days=["2026-10-22", "2026-10-23", "2026-10-27"])
    ny = "America/New_York"
    yahoo = FakeYahoo(clock, {"^SOX": (ny, "INDEX", bars_on(["2026-10-21", "2026-10-22"], ny, volume=0)),
                              "0050.TW": ("Asia/Taipei", "ETF", bars_on(["2026-10-21", "2026-10-22"], "Asia/Taipei", "09:00"))})
    code, run = crawl(tmp_path, cfg, clock, t="2026-10-27", course=course, live=live, yahoo=yahoo)
    assert code == 3
    assert run.prev_day == "2026-10-22" and run.manifest["teacher_live"]["prev_day_never_filled"] is True
    assert {e["status"] for e in run.manifest["yfinance"].values()} == {"ok"}


def test_secrets_never_leak(tmp_path, cfg, caplog):
    clock = Clock(at("2026-11-17", "07:10"))
    leaky_login = FakeResp(401, f"wrong password {SECRETS['COURSE_PASSWORD']}".encode())
    with caplog.at_level(logging.INFO), pytest.raises(crawler.CrawlerError) as err:
        crawl(tmp_path, cfg, clock, course=course_fake(login=leaky_login))
    leaky_live = FakeResp(200, f"bad key {SECRETS['COURSE_LIVE_KEY']}".encode())
    with caplog.at_level(logging.INFO), pytest.raises(crawler.CrawlerError) as err2:
        crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")),
              live=live_fake(make_zip(live_members(LIVE_DATES)), login=leaky_live))
    manifest = (tmp_path / "raw" / "manifest.json").read_text()
    for secret in SECRETS.values():
        assert secret not in str(err.value) and secret not in str(err2.value)
        assert secret not in manifest and secret not in caplog.text


def test_main_returns_code_without_system_exit(monkeypatch, tmp_path, cfg):
    monkeypatch.setattr(utils, "load_config", lambda: cfg)
    monkeypatch.setattr(utils, "load_secrets", lambda: SECRETS)
    monkeypatch.setattr(utils, "get_logger", lambda name, t: logging.getLogger("test.crawler"))
    seen = {}

    def fake_crawl(run, secrets):
        seen.update(t=run.t, daily=run.daily)
        return 3

    monkeypatch.setattr(crawler, "crawl", fake_crawl)
    assert crawler.main(["--date", "2026-11-17"]) == 3
    assert seen == {"t": "2026-11-17", "daily": True}
