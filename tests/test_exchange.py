"""src/crawler.py 證交所、櫃買回補（--exchange-backfill）的離線測試。

不連網：主機是假的 requests.Session，時鐘也是假的（sleep 只把時間往後撥）。
tests/data_exchange/ 是 2026-11-08 存下來的真回應剪小的版本：欄名和格子原樣，只留我們的 100 檔和幾檔別的。
流程的測試用測試裡現做的 JSON 和老師資料（91 檔上市、9 檔上櫃）。
"""

import copy
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
import requests
from curl_cffi.requests import Session as CurlSession

from src import crawler, utils

DATA = Path(__file__).parent / "data_exchange"
TAIPEI = ZoneInfo("Asia/Taipei")
JSON_TYPE = "application/json;charset=UTF-8"
REAL_IDS = set(json.loads((DATA / "stock_ids.json").read_text(encoding="utf-8")))
SPECS = {s.key: s for s in crawler.EXCHANGE_SPECS}
LOG = logging.getLogger("test.exchange")

TW_IDS = [str(1101 + i) for i in range(91)]
OTC_IDS = [str(3001 + i) for i in range(9)]
IDS = TW_IDS + OTC_IDS
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("測試不能連網")

    monkeypatch.setattr(CurlSession, "_request_once", boom, raising=False)
    monkeypatch.setattr(requests.Session, "send", boom)


@pytest.fixture
def cfg():
    conf = copy.deepcopy(utils.load_config())
    conf["exchange"]["enabled"] = False   # 設定檔 2026-11-10 起是 true；每天那一步的測試用 daily_cfg 打開
    return conf


def load(name: str) -> dict:
    return json.loads((DATA / name).read_bytes())


def parse(key, payload, day, ids=REAL_IDS, content_type=JSON_TYPE):
    body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
    return crawler.parse_exchange(SPECS[key], body, content_type, date.fromisoformat(day), ids)


# ================================================================ 解析真的回應


def test_twse_valuation_real_responses():
    old = parse("twse_valuation", load("twse_bwibbu_20200102.json"), "2020-01-02")
    new = parse("twse_valuation", load("twse_bwibbu_20261106.json"), "2026-11-06")
    assert len(old) == 90 and len(new) == 91
    assert "6446" not in old and "6446" in new   # 2024 年從櫃買轉上市
    # 收盤價, 殖利率(%), 本益比, 股價淨值比, 財報年/季；股利年度不存
    assert old["1101"] == ["44.10", "9.09", "10.86", "1.36", "108/3"]
    assert new["1101"] == ["26.75", "2.99", "-", "0.87", "115/2"]   # 虧損的本益比 '-' 原樣留
    assert SPECS["twse_valuation"].columns == ("date", "stock_id", "收盤價", "殖利率(%)", "本益比", "股價淨值比", "財報年/季")


def test_twse_quotes_finds_the_table_by_its_fields():
    payload = load("twse_mi_20261106.json")
    rows = parse("twse_quotes", payload, "2026-11-06")
    assert len(rows) == 91
    # 開盤價, 最高價, 最低價, 收盤價, 成交股數, 最後揭示買價, 最後揭示買量, 最後揭示賣價, 最後揭示賣量；千分位逗號拿掉
    assert rows["2330"] == ["2020.00", "2195.00", "2020.00", "2135.00", "110714587", "2135.00", "12", "2140.00", "1039"]
    assert any(v[5] == "--" for v in rows.values())   # 沒有揭示買價的 '--' 原樣留
    usual = [i for i, t in enumerate(payload["tables"]) if "最後揭示買價" in (t.get("fields") or [])]
    assert usual == [8]
    moved = copy.deepcopy(payload)
    moved["tables"].insert(1, moved["tables"].pop(8))   # 換個位置還是找得到
    assert parse("twse_quotes", moved, "2026-11-06") == rows
    old = parse("twse_quotes", load("twse_mi_20200102.json"), "2020-01-02")
    assert len(old) == 90 and old["1101"] == ["43.80", "44.15", "43.80", "44.10", "18470566", "44.05", "712", "44.10", "3"]


@pytest.mark.parametrize("change", ["drop", "twice"])
def test_twse_quotes_needs_exactly_one_quotes_table(change):
    payload = load("twse_mi_20261106.json")
    quotes = payload["tables"][8]
    if change == "drop":
        payload["tables"].pop(8)
    else:
        payload["tables"].append(copy.deepcopy(quotes))
    with pytest.raises(crawler.ExchangeFormatError):
        parse("twse_quotes", payload, "2026-11-06")


def test_tpex_valuation_year_variants_and_no_lookahead_columns():
    old = parse("tpex_valuation", load("tpex_pe_20200102.json"), "2020-01-02")
    new = parse("tpex_valuation", load("tpex_pe_20261106.json"), "2026-11-06")
    assert len(old) == 10 and len(new) == 9 and "6446" in old and "6446" not in new
    # 本益比, 股價淨值比, 殖利率(%), 財報年/季；2020 年沒有財報年/季，存空字串
    assert old["3293"] == ["16.97", "6.28", "2.80", ""]
    assert new["3293"] == ["17.01", "13.72", "4.89", "115Q2"]
    assert any(v[0] == "N/A" for v in old.values())   # 虧損的本益比 'N/A' 原樣留
    for key in ("tpex_valuation", "twse_valuation"):
        assert "每股股利" not in SPECS[key].columns and "股利年度" not in SPECS[key].columns
    # 3293 在 2020-01-02 的每股股利是 25.00000000（回填的值），不能出現在任何一格
    assert "25.00000000" in json.dumps(load("tpex_pe_20200102.json"))
    assert not any("25.00000000" in cell for v in old.values() for cell in v)


def test_tpex_quotes_field_variants():
    early = parse("tpex_quotes", load("tpex_otc_20200102.json"), "2020-01-02")    # 15 欄，沒有買賣量
    mid = parse("tpex_quotes", load("tpex_otc_20200701.json"), "2020-07-01")      # 17 欄，買賣量是「千股」
    new = parse("tpex_quotes", load("tpex_otc_20261106.json"), "2026-11-06")      # 17 欄，買賣量是「張數」
    assert len(early) == len(mid) == 10 and len(new) == 9
    # 開盤, 最高, 最低, 收盤, 成交股數, 最後買價, 最後買量, 最後賣價, 最後賣量
    assert early["3293"] == ["396.00", "406.50", "393.00", "393.00", "1471000", "392.50", "", "393.00", ""]
    assert mid["5274"] == ["1250.00", "1260.00", "1165.00", "1180.00", "1216000", "1180.00", "16", "1185.00", "4"]
    assert new["5274"] == ["11375.00", "11375.00", "11375.00", "11375.00", "219000", "0.00", "0", "11375.00", "202"]


def test_no_data_responses_are_empty():
    assert parse("twse_valuation", load("twse_bwibbu_20261009.json"), "2026-10-09") == {}   # 證交所休市
    assert parse("twse_quotes", load("twse_mi_20261009.json"), "2026-10-09") == {}
    assert parse("tpex_valuation", load("tpex_pe_20261108_sun.json"), "2026-11-08") == {}   # 櫃買：stat ok、0 筆
    assert parse("tpex_quotes", load("tpex_otc_20260101_hol.json"), "2026-01-01") == {}


def test_cell_and_field_normalisation():
    assert crawler.exchange_cell(" 1,234,567 ") == "1234567"
    assert crawler.exchange_cell("-1,260.00") == "-1260.00"
    assert crawler.exchange_cell("+0.50") == "+0.50"
    for marker in ("-", "N/A", "--", "----", "0.00", "108/3", "115Q2"):
        assert crawler.exchange_cell(marker) == marker
    assert crawler.exchange_cell(None) == "" and crawler.exchange_cell(114) == "114"
    assert crawler.exchange_field("最後買量<br>(千股)") == "最後買量(千股)"
    assert crawler.exchange_field(" 成交金額(元)") == "成交金額(元)"
    assert crawler.exchange_field("成交股數  ") == "成交股數"
    assert crawler.roc_date("115/11/06") == date(2026, 11, 6) and crawler.roc_date("2026/11/06") is None


# ================================================================ 格式和日期的檢查


def drop_field(table, name):
    j = table["fields"].index(name)
    table["fields"].pop(j)
    for row in table["data"]:
        row.pop(j)


def test_missing_required_field_is_a_format_error():
    payload = load("tpex_otc_20261106.json")
    drop_field(payload["tables"][0], "收盤 ")
    with pytest.raises(crawler.ExchangeFormatError, match="收盤"):
        parse("tpex_quotes", payload, "2026-11-06")
    payload = load("twse_bwibbu_20261106.json")
    drop_field(payload, "本益比")
    with pytest.raises(crawler.ExchangeFormatError, match="本益比"):
        parse("twse_valuation", payload, "2026-11-06")


def test_two_source_fields_for_one_column_is_a_format_error():
    payload = load("tpex_otc_20261106.json")
    table = payload["tables"][0]
    table["fields"][11] = "最後買量<br>(千股)"
    table["fields"].append("最後買量<br>(張數)")
    for row in table["data"]:
        row.append("1")
    with pytest.raises(crawler.ExchangeFormatError, match="最後買量"):
        parse("tpex_quotes", payload, "2026-11-06")


def tpex_redated(name: str, day: str) -> dict:
    """櫃買的真回應改成別的日期（最上層和 tables[0] 的日期一起改）。"""
    payload = load(name)
    y, m, d = (int(x) for x in day.split("-"))
    payload["date"] = day.replace("-", "")
    payload["tables"][0]["date"] = f"{y - 1911}/{m:02d}/{d:02d}"
    return payload


@pytest.mark.parametrize("key,name,day,old,new", [
    ("tpex_quotes", "tpex_otc_20200701.json", "2020-06-30", "最後買量<br>(千股)", "最後買量<br>(股)"),
    ("tpex_quotes", "tpex_otc_20200701.json", "2020-06-30", "最後賣量<br>(千股)", "最後賣量(仟股)"),
    ("tpex_valuation", "tpex_pe_20261106.json", "2026-11-06", "財報年/季", "財報年季"),
    ("twse_valuation", "twse_bwibbu_20261106.json", "2026-11-06", "股利年度", "本益比(倍)"),   # 名字裡有存檔欄名
])
def test_unknown_spelling_of_a_stored_field_is_a_format_error(key, name, day, old, new):
    """對照表沒有的寫法不默默存成空白：沒對到的來源欄像是存檔欄，就是格式錯誤（optional 的欄也一樣）。"""
    payload = tpex_redated(name, day) if key.startswith("tpex") else load(name)
    table = payload if key == "twse_valuation" else payload["tables"][0]
    hits = [j for j, f in enumerate(table["fields"]) if crawler.exchange_field(f) == crawler.exchange_field(old)]
    assert len(hits) == 1
    table["fields"][hits[0]] = new
    with pytest.raises(crawler.ExchangeFormatError, match="不在對照表"):
        parse(key, payload, day)


def test_bid_ask_volume_is_required_from_july_2020():
    for day, ok in (("2020-07-01", False), ("2020-06-30", True)):
        payload = tpex_redated("tpex_otc_20200701.json", day)
        table = payload["tables"][0]
        drop_field(table, next(f for f in table["fields"] if f.startswith("最後買量")))
        drop_field(table, next(f for f in table["fields"] if f.startswith("最後賣量")))
        if ok:   # 2020-07-01 以前少了還是可以，存空白
            rows = parse("tpex_quotes", payload, day)
            assert len(rows) == 10 and all(v[6] == v[8] == "" for v in rows.values())
        else:
            with pytest.raises(crawler.ExchangeFormatError, match="2020-07-01 起"):
                parse("tpex_quotes", payload, day)


def test_row_length_must_match_fields():
    payload = load("twse_bwibbu_20261106.json")
    payload["data"][5] = payload["data"][5][:-1]
    with pytest.raises(crawler.ExchangeFormatError):
        parse("twse_valuation", payload, "2026-11-06")


@pytest.mark.parametrize("key,name,day,edit", [
    ("twse_valuation", "twse_bwibbu_20261106.json", "2026-11-06", lambda p: p.update(date="20261105")),
    ("twse_quotes", "twse_mi_20261106.json", "2026-11-06", lambda p: p.pop("date")),
    ("tpex_valuation", "tpex_pe_20261106.json", "2026-11-06", lambda p: p["tables"][0].update(date="115/11/05")),
    ("tpex_quotes", "tpex_otc_20261106.json", "2026-11-06", lambda p: p.update(date="20261105")),
    ("tpex_quotes", "tpex_otc_20261106.json", "2026-11-06", lambda p: (p.pop("date"), p["tables"][0].pop("date"))),
])
def test_date_mismatch_is_a_format_error(key, name, day, edit):
    payload = load(name)
    edit(payload)
    with pytest.raises(crawler.ExchangeFormatError, match="日期"):
        parse(key, payload, day)


def test_same_id_twice_in_one_response_is_a_day_error():
    payload = load("twse_bwibbu_20261106.json")
    payload["data"].append(list(payload["data"][-1]))
    assert payload["data"][-1][0] in REAL_IDS
    with pytest.raises(crawler.ExchangeDayError):
        parse("twse_valuation", payload, "2026-11-06")


def test_blocked_and_unknown_responses():
    page = "<!DOCTYPE html><html><title>404</title></html>".encode()
    with pytest.raises(crawler.ExchangeBlocked):
        parse("tpex_quotes", page, "2026-11-06", content_type="text/html")
    with pytest.raises(crawler.ExchangeBlocked):
        parse("tpex_quotes", page, "2026-11-06")   # Content-Type 說 JSON，內容卻是 HTML
    with pytest.raises(crawler.ExchangeBlocked):
        parse("twse_valuation", {"stat": "請求過於頻繁，請稍後再試"}, "2026-11-06")
    with pytest.raises(crawler.ExchangeBlocked):
        parse("tpex_valuation", {"stat": "因安全性考量，暫停服務"}, "2026-11-06")
    with pytest.raises(crawler.ExchangeFormatError):
        parse("twse_valuation", {"stat": "查詢日期小於93年2月11日，請重新查詢!"}, "2026-11-06")
    with pytest.raises(crawler.ExchangeFormatError):
        parse("tpex_valuation", {"stat": "error"}, "2026-11-06")


# ================================================================ CSV、日曆、暫停時段


def test_csv_round_trip(tmp_path):
    columns = SPECS["tpex_quotes"].columns
    rows = [["2026-11-06", "5274", "11375.00", "11375.00", "11375.00", "11375.00", "219000", "0.00", "0", "11375.00", "202"],
            ["2020-01-02", "3293", "396.00", "406.50", "393.00", "393.00", "1471000", "392.50", "", "393.00", ""],
            ["2026-11-06", "3293", "----", "----", "----", "736.00", "0", "0.00", "0", "0.00", "0"]]
    data = crawler.exchange_to_csv(rows, columns)
    assert b"\r" not in data and data.decode("utf-8").splitlines()[0] == ",".join(columns)
    path = tmp_path / "tpex" / "quotes.csv"
    crawler.write_atomic(path, data)
    assert crawler.read_exchange_csv(path, columns) == sorted(rows, key=lambda r: (r[0], r[1]))


def test_csv_with_another_header_is_refused(tmp_path):
    path = tmp_path / "twse" / "valuation.csv"
    crawler.write_atomic(path, b"date,stock_id,PE\n2026-11-06,1101,10\n")
    with pytest.raises(crawler.CrawlerError, match="表頭"):
        crawler.read_exchange_csv(path, SPECS["twse_valuation"].columns)


def test_pause_window():
    window = ["07:00", "09:00"]
    assert crawler.exchange_pause(at("2026-11-09", "06:59:59"), window) == 0
    assert crawler.exchange_pause(at("2026-11-09", "07:00:00"), window) == 7200
    assert crawler.exchange_pause(at("2026-11-09", "08:59:30"), window) == 30
    assert crawler.exchange_pause(at("2026-11-09", "09:00:00"), window) == 0
    utc = datetime(2026, 11, 8, 23, 30, tzinfo=ZoneInfo("UTC"))   # 台北 07:30
    assert crawler.exchange_pause(utc, window) == 5400


# ================================================================ 假主機和老師資料


class Clock:
    def __init__(self, start: datetime):
        self.t, self.sleeps = start, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += timedelta(seconds=seconds)

    def monotonic(self):
        return self.t.timestamp()


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=TAIPEI)


class FakeResp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]

    def close(self):
        pass


def json_resp(payload) -> FakeResp:
    return FakeResp(200, json.dumps(payload, ensure_ascii=False).encode(), {"Content-Type": JSON_TYPE})


TWSE_VAL_FIELDS = load("twse_bwibbu_20261106.json")["fields"]
TWSE_MI = load("twse_mi_20261106.json")
TWSE_INDEX_FIELDS, TWSE_QUOTE_FIELDS = TWSE_MI["tables"][0]["fields"], TWSE_MI["tables"][8]["fields"]
TPEX_VAL_FIELDS = load("tpex_pe_20261106.json")["tables"][0]["fields"]
TPEX_QUOTE_FIELDS = load("tpex_otc_20261106.json")["tables"][0]["fields"]


def payload(market: str, kind: str, day: str, ids=None) -> dict:
    """假的正常回應，欄名用真的。ids 沒給就是那個交易所的全部股票，另外加一檔不是我們的。"""
    ymd = day.replace("-", "")
    ids = (TW_IDS if market == "twse" else OTC_IDS) if ids is None else ids
    if market == "twse" and kind == "valuation":
        rows = [[s, "名稱", "1,010.00", "1.00", 114, "-" if s == ids[0] else "12.00", "1.50", "115/2"] for s in ids]
        return {"stat": "OK", "date": ymd, "fields": list(TWSE_VAL_FIELDS), "data": rows + [["0050", "ETF", "1", "1", 114, "1", "1", "x"]]}
    if market == "twse":
        rows = [[s, "名稱", "1,234,567", "100", "1,000,000", "10.00", "11.00", "9.50", "10.50", "<p style= color:red>+</p>",
                 "0.50", "--" if s == ids[0] else "10.45", "3", "10.50", "5", "12.00"] for s in ids]
        return {"stat": "OK", "date": ymd, "tables": [
            {"title": "指數", "fields": list(TWSE_INDEX_FIELDS), "data": [["寶島股價指數", "43,675.60", "<p>-</p>", "1", "-1", ""]]},
            {"title": "收盤行情", "fields": list(TWSE_QUOTE_FIELDS), "data": rows}, {}]}
    y, m, d = (int(x) for x in day.split("-"))
    roc = f"{y - 1911}/{m:02d}/{d:02d}"
    if kind == "valuation":
        rows = [[s, "名稱        ", "N/A" if s == ids[0] else "12.50", "25.00000000", 114, "1.20", "2.30", "115Q2"] for s in ids]
        fields = list(TPEX_VAL_FIELDS)
    else:
        rows = [[s, "名稱", "1,885.00", "+1.00", "1,800.00", "1,900.00", "1,790.00", "993,000", "1,856,455,000", "854",
                 "1,880.00", "7", "1,885.00", "2", "74,686,492", "2,070.00", "1,700.00"] for s in ids]
        fields = list(TPEX_QUOTE_FIELDS)
    return {"tables": [{"title": "", "date": roc, "totalCount": len(rows), "fields": fields, "data": rows}],
            "date": ymd, "stat": "ok"}


class FakeExchange:
    """假的證交所或櫃買主機（requests.Session 的介面）。handler(kind, day) 回 FakeResp 或 None（None 就回正常資料）。"""

    def __init__(self, market, clock=None, handler=None):
        self.market, self.clock, self.handler = market, clock, handler
        self.headers, self.calls = {}, []

    def request(self, method, url, **kwargs):
        assert method == "GET" and kwargs["allow_redirects"] is False and "json" in kwargs["headers"]["Accept"]
        parts = urlsplit(url)
        kind = "valuation" if ("BWIBBU_d" in parts.path or "peQryDate" in parts.path) else "quotes"
        raw = parse_qs(parts.query)["date"][0]
        day = raw.replace("/", "-") if "/" in raw else f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        self.calls.append((kind, day, self.clock.now() if self.clock else None))
        resp = self.handler(kind, day) if self.handler else None
        return resp or json_resp(payload(self.market, kind, day))

    def close(self):
        pass


def stock_csv(days, pending=()) -> str:
    lines = [",".join(crawler.STOCK_COLUMNS)]
    for d in days:
        values = ["-1"] * 20 if d in pending else ["101.5", "100.0", "102", "99", "10", "1000", "5000", "50.1", "3", "4",
                                                  "5", "6", "50", "100", "0.1", "1", "105", "100", "95", "1"]
        lines.append(",".join([d] + values))
    return "\n".join(lines) + "\n"


def make_teacher(raw: Path, days=DAYS, pending=("2026-11-09",), live_days=()):
    """老師的 Training（days 加上一天全部 -1 的 pending），live_days 放在 Live。"""
    train = raw / "teacher" / "training"
    (train / "market").mkdir(parents=True)
    (train / "info.json").write_text(json.dumps({"Top50@Y": IDS[:50], "Top100@Y": IDS}), encoding="utf-8")
    for sid in IDS:
        (train / "market" / f"{sid}.csv").write_text(stock_csv(list(days) + list(pending), pending), encoding="utf-8")
    if live_days:
        (raw / "teacher" / "live" / "market").mkdir(parents=True)
        for sid in IDS:
            (raw / "teacher" / "live" / "market" / f"{sid}.csv").write_text(stock_csv(live_days), encoding="utf-8")


def weekdays(start: str, n: int) -> list:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def run_backfill(raw, cfg, clock, handlers=None, markets=("twse", "tpex"), **kwargs):
    fakes = {m: FakeExchange(m, clock, (handlers or {}).get(m)) for m in markets}
    clients = {m: crawler.exchange_client(cfg, m, session=fakes[m], clock=clock.monotonic) for m in markets}
    kwargs.setdefault("lock_dir", raw.parent / "locks")
    rc = crawler.exchange_backfill(cfg, raw, markets=markets, clients=clients, now=clock.now, sleep=clock.sleep,
                                   log=LOG, parallel=False, **kwargs)
    return rc, fakes


def csv_rows(raw, key) -> list:
    return crawler.read_exchange_csv(raw / SPECS[key].file, SPECS[key].columns)


def csv_days(raw, key) -> list:
    return sorted({r[0] for r in csv_rows(raw, key)})


def state(raw) -> dict:
    return json.loads((raw / "exchange_backfill.json").read_text(encoding="utf-8"))


@pytest.fixture
def raw(tmp_path):
    raw = tmp_path / "raw"
    make_teacher(raw)
    return raw


# ================================================================ 回補的流程


def test_backfill_writes_four_long_csvs_newest_first(raw, cfg):
    manifest = raw / "manifest.json"
    manifest.write_bytes(b'{"run": {"status": "ok"}}\n')
    clock = Clock(at("2026-11-08", "20:00"))
    rc, fakes = run_backfill(raw, cfg, clock)
    assert rc == 0
    for market in ("twse", "tpex"):
        assert [(k, d) for k, d, _ in fakes[market].calls] == [
            (k, d) for d in reversed(DAYS) for k in ("valuation", "quotes")]   # 新的先，2026-11-09（還是 -1）不抓
    for key, n in (("twse_valuation", 91), ("twse_quotes", 91), ("tpex_valuation", 9), ("tpex_quotes", 9)):
        rows = csv_rows(raw, key)
        assert len(rows) == n * len(DAYS) and rows == sorted(rows, key=lambda r: (r[0], r[1]))
        data = (raw / SPECS[key].file).read_bytes()
        assert b"\r" not in data and data.decode("utf-8").startswith(",".join(SPECS[key].columns) + "\n")
        info = state(raw)["sources"][key]
        assert (info["done_dates"], info["first_date"], info["last_date"]) == (5, DAYS[0], DAYS[-1])
        assert info["no_data"] == [] and info["failures"] == [] and info["blocked"] is False
        assert info["requests"] == info["requests_total"] == 5
    assert csv_rows(raw, "twse_valuation")[0] == ["2026-11-02", "1101", "1010.00", "1.00", "-", "1.50", "115/2"]
    assert csv_rows(raw, "twse_quotes")[0][2:] == ["10.00", "11.00", "9.50", "10.50", "1234567", "--", "3", "10.50", "5"]
    assert csv_rows(raw, "tpex_quotes")[0][2:] == ["1800.00", "1900.00", "1790.00", "1885.00", "993000", "1880.00", "7",
                                                   "1885.00", "2"]
    tpex_val = (raw / "tpex" / "valuation.csv").read_text(encoding="utf-8")
    assert "每股股利" not in tpex_val and "股利年度" not in tpex_val and "25.00000000" not in tpex_val
    assert state(raw)["last_run"]["status"] == "done"
    assert manifest.read_bytes() == b'{"run": {"status": "ok"}}\n'   # 不碰 manifest.json


def test_requests_to_one_host_are_spaced(raw, cfg):
    clock = Clock(at("2026-11-08", "20:00"))
    _, fakes = run_backfill(raw, cfg, clock)
    for fake in fakes.values():
        times = [t for _, _, t in fake.calls]
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        assert gaps and min(gaps) >= cfg["exchange"]["min_interval_seconds"]


def test_parallel_hosts_write_everything(raw, cfg):
    fakes = {m: FakeExchange(m) for m in ("twse", "tpex")}
    clients = {m: crawler.exchange_client(cfg, m, session=fakes[m]) for m in fakes}
    rc = crawler.exchange_backfill(cfg, raw, clients=clients, now=lambda: at("2026-11-08", "20:00"),
                                   sleep=lambda s: None, log=LOG, parallel=True, lock_dir=raw.parent / "locks")
    assert rc == 0
    assert all(csv_days(raw, key) == DAYS for key in SPECS)
    assert all(len(f.calls) == 2 * len(DAYS) for f in fakes.values())


def test_resume_skips_dates_already_in_the_csv(raw, cfg):
    spec = SPECS["twse_valuation"]
    old = [["2026-11-05", s, "1", "1", "1", "1", "x"] for s in TW_IDS]
    crawler.write_atomic(raw / spec.file, crawler.exchange_to_csv(old, spec.columns))
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")))
    assert rc == 0
    twse = [(k, d) for k, d, _ in fakes["twse"].calls]
    assert ("valuation", "2026-11-05") not in twse and ("quotes", "2026-11-05") in twse
    assert [r for r in csv_rows(raw, "twse_valuation") if r[0] == "2026-11-05"] == old   # 舊的列不動
    assert csv_days(raw, "twse_valuation") == DAYS
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "21:00")))   # 全部都有了：一個請求都不送
    assert rc == 0 and all(f.calls == [] for f in fakes.values())


def test_low_coverage_is_no_data_and_retried_later(raw, cfg):
    def thin(kind, day):
        if kind == "valuation" and day == "2026-11-04":
            return json_resp(payload("tpex", kind, day, ids=OTC_IDS[:5]))   # 只有 5 檔，要 8 檔

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"tpex": thin})
    assert rc == 0   # no_data 不算失敗
    assert "2026-11-04" not in csv_days(raw, "tpex_valuation")
    assert state(raw)["sources"]["tpex_valuation"]["no_data"] == ["2026-11-04"]
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-09", "20:00")))
    assert [(k, d) for k, d, _ in fakes["tpex"].calls] == [("valuation", "2026-11-04")]
    assert fakes["twse"].calls == []
    assert "2026-11-04" in csv_days(raw, "tpex_valuation")
    info = state(raw)["sources"]["tpex_valuation"]
    assert info["no_data"] == [] and info["requests"] == 1 and info["requests_total"] == 6


def test_holiday_style_empty_response_on_a_trading_day_is_no_data(raw, cfg):
    def closed(kind, day):
        if day == "2026-11-06":
            return json_resp({"stat": "很抱歉，沒有符合條件的資料!", "total": 0})

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": closed}, markets=("twse",))
    assert rc == 0
    for key in ("twse_valuation", "twse_quotes"):
        assert csv_days(raw, key) == DAYS[:-1] and state(raw)["sources"][key]["no_data"] == ["2026-11-06"]


def test_same_id_in_both_exchanges_writes_nothing_that_day(raw, cfg):
    def twice(kind, day):
        if kind == "quotes" and day == "2026-11-05":
            return json_resp(payload("tpex", kind, day, ids=OTC_IDS + [TW_IDS[0]]))

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"tpex": twice})
    assert rc == 3
    for key in SPECS:
        assert csv_days(raw, key) == [d for d in DAYS if d != "2026-11-05"]
        assert [f["date"] for f in state(raw)["sources"][key]["failures"]] == ["2026-11-05"]


def test_same_id_found_in_the_other_exchanges_old_file(raw, cfg):
    spec = SPECS["tpex_quotes"]
    old = [["2026-11-03", s, "1", "1", "1", "1", "1", "1", "1", "1", "1"] for s in OTC_IDS + [TW_IDS[0]]]
    crawler.write_atomic(raw / spec.file, crawler.exchange_to_csv(old, spec.columns))
    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), markets=("twse",))
    assert rc == 3
    assert "2026-11-03" not in csv_days(raw, "twse_valuation") + csv_days(raw, "twse_quotes")
    assert "tpex_quotes" not in state(raw)["sources"]   # 只記這次有跑的來源


def test_a_stock_that_moves_exchange_is_taken_from_where_it_appears(raw, cfg):
    mover = OTC_IDS[0]

    def twse(kind, day):
        if day >= "2026-11-05":
            return json_resp(payload("twse", kind, day, ids=TW_IDS + [mover]))

    def tpex(kind, day):
        if day >= "2026-11-05":
            return json_resp(payload("tpex", kind, day, ids=OTC_IDS[1:]))

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": twse, "tpex": tpex})
    assert rc == 0
    assert sorted(r[0] for r in csv_rows(raw, "twse_quotes") if r[1] == mover) == ["2026-11-05", "2026-11-06"]
    assert sorted(r[0] for r in csv_rows(raw, "tpex_quotes") if r[1] == mover) == DAYS[:3]


@pytest.mark.parametrize("resp", [
    FakeResp(200, b"<!DOCTYPE html><html>errors</html>", {"Content-Type": "text/html"}),
    FakeResp(403, b"forbidden"),
    FakeResp(429, b"too many"),
    FakeResp(302, b"", {"Location": "/errors"}),
    json_resp({"stat": "請求過於頻繁，請稍後再試"}),
    FakeResp(503, b"<!DOCTYPE html><title>Just a moment...</title>", {"Content-Type": "text/html; charset=UTF-8",
                                                                      "cf-mitigated": "challenge"}),
    FakeResp(502, b""),
], ids=["html", "403", "429", "redirect", "stat", "503-html", "502-no-type"])
def test_blocked_host_stops_and_the_other_host_continues(raw, cfg, resp):
    clock = Clock(at("2026-11-08", "20:00"))
    rc, fakes = run_backfill(raw, cfg, clock, {"twse": lambda kind, day: resp})
    assert rc == 3
    assert len(fakes["twse"].calls) == 1   # 不重試、不再送
    assert len(fakes["tpex"].calls) == 2 * len(DAYS)
    info = state(raw)["sources"]
    assert info["twse_valuation"]["blocked"] and info["twse_quotes"]["blocked"]
    assert info["twse_valuation"]["stopped"] and not info["tpex_quotes"]["blocked"]
    assert not (raw / "twse").exists() and csv_days(raw, "tpex_quotes") == DAYS
    assert 60 not in clock.sleeps   # 被擋不等


def json_503() -> FakeResp:
    return FakeResp(503, b'{"stat": "error"}', {"Content-Type": JSON_TYPE})


def test_server_error_is_retried_once_after_a_minute_then_skipped(raw, cfg):
    def broken(kind, day):
        if kind == "valuation" and day == "2026-11-06":
            return json_503()

    clock = Clock(at("2026-11-08", "20:00"))
    rc, fakes = run_backfill(raw, cfg, clock, {"twse": broken}, markets=("twse",))
    assert rc == 3
    calls = [(k, d) for k, d, _ in fakes["twse"].calls]
    assert calls.count(("valuation", "2026-11-06")) == 2 and len(calls) == 2 * len(DAYS) + 1
    assert clock.sleeps.count(cfg["exchange"]["retry_wait_seconds"]) == 1
    assert csv_days(raw, "twse_valuation") == DAYS[:-1] and csv_days(raw, "twse_quotes") == DAYS
    assert state(raw)["sources"]["twse_valuation"]["failures"][0]["date"] == "2026-11-06"


def test_server_error_then_success_is_written(raw, cfg):
    seen = []

    def flaky(kind, day):
        if (kind, day) == ("valuation", "2026-11-06") and not seen:
            seen.append(1)
            raise requests.exceptions.ReadTimeout("slow")

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": flaky}, markets=("twse",))
    assert rc == 0 and csv_days(raw, "twse_valuation") == DAYS


def test_host_that_keeps_timing_out_is_stopped_as_blocked(raw, cfg):
    def hang(kind, day):
        raise requests.exceptions.ConnectTimeout("no answer")

    clock = Clock(at("2026-11-08", "20:00"))
    rc, fakes = run_backfill(raw, cfg, clock, {"tpex": hang})
    assert rc == 3
    limit = cfg["exchange"]["max_failed_dates"]
    assert limit == 3 and len(fakes["tpex"].calls) == limit * 2 * 2   # 每天兩個來源、各試兩次，連續 3 天就停
    assert {d for _, d, _ in fakes["tpex"].calls} == set(DAYS[-limit:])
    info = state(raw)["sources"]
    assert info["tpex_quotes"]["blocked"] and "連續" in info["tpex_quotes"]["stopped"]
    assert [f["date"] for f in info["tpex_valuation"]["failures"]] == DAYS[-limit:]
    assert csv_days(raw, "twse_quotes") == DAYS and not info["twse_quotes"]["blocked"]


def test_timeout_streak_resets_when_the_host_answers(raw, cfg):
    def some(kind, day):
        if day != "2026-11-04":
            return json_503()

    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"tpex": some}, markets=("tpex",))
    assert rc == 3   # 有失敗
    info = state(raw)["sources"]["tpex_quotes"]
    assert not info["blocked"] and not info["stopped"]   # 11-06、11-05 失敗，11-04 有回應，11-03、11-02 失敗：沒有連續 3 天
    assert [f["date"] for f in info["failures"]] == ["2026-11-02", "2026-11-03", "2026-11-05", "2026-11-06"]
    assert csv_days(raw, "tpex_quotes") == ["2026-11-04"] and len(fakes["tpex"].calls) == 4 * 4 + 2


def test_retry_and_first_request_wait_at_least_min_interval(raw, cfg):
    cfg["exchange"]["retry_wait_seconds"] = 1   # 比 min_interval 短，也要等 min_interval

    def once(kind, day):
        if (kind, day) == ("valuation", "2026-11-06") and not seen:
            seen.append(1)
            return json_503()

    seen = []
    start = at("2026-11-08", "20:00")
    clock = Clock(start)
    rc, fakes = run_backfill(raw, cfg, clock, {"twse": once}, markets=("twse",))
    assert rc == 0
    times = [t for _, _, t in fakes["twse"].calls]
    gap = cfg["exchange"]["min_interval_seconds"]
    assert times[0] == start + timedelta(seconds=gap)   # 剛停掉又馬上重跑，第一個請求也隔 6.5 秒
    assert min((b - a).total_seconds() for a, b in zip(times, times[1:])) >= gap
    assert 1 not in clock.sleeps


def test_a_market_already_running_is_refused(raw, cfg):
    fcntl = pytest.importorskip("fcntl")
    locks = raw.parent / "locks"
    locks.mkdir()
    with open(locks / "exchange_twse.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(crawler.CrawlerError, match="還在跑 twse"):
            run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")))
        assert not (raw / "exchange_backfill.json").exists()
        rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), markets=("tpex",))   # 另一個交易所可以
        assert rc == 0 and csv_days(raw, "tpex_quotes") == DAYS
    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "21:00")), markets=("twse",))   # 鎖放開之後可以
    assert rc == 0 and csv_days(raw, "twse_quotes") == DAYS
    with open(locks / "exchange_tpex.lock", "w") as probe:   # 跑完會放開鎖
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_unreadable_file_of_the_other_exchange_only_warns(raw, cfg):
    bad = b"date,stock_id,price\n"
    crawler.write_atomic(raw / "tpex" / "quotes.csv", bad)
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), markets=("twse",))
    assert rc == 0 and csv_days(raw, "twse_quotes") == DAYS and fakes["twse"].calls
    assert (raw / "tpex" / "quotes.csv").read_bytes() == bad   # 不動那個檔
    assert any("表頭" in w for w in state(raw)["last_run"]["warnings"])


def test_format_error_stops_only_that_source(raw, cfg):
    def no_close(kind, day):
        if kind == "quotes":
            body = payload("tpex", kind, day)
            drop_field(body["tables"][0], "收盤 ")
            return json_resp(body)

    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"tpex": no_close}, markets=("tpex",))
    assert rc == 3
    calls = [(k, d) for k, d, _ in fakes["tpex"].calls]
    assert calls.count(("quotes", DAYS[-1])) == 1 and sum(k == "quotes" for k, _ in calls) == 1
    assert csv_days(raw, "tpex_valuation") == DAYS and not (raw / "tpex" / "quotes.csv").exists()
    info = state(raw)["sources"]["tpex_quotes"]
    assert "收盤" in info["stopped"] and info["blocked"] is False


def test_date_mismatch_stops_that_source(raw, cfg):
    def stale(kind, day):
        if kind == "valuation":
            return json_resp(payload("twse", kind, "2026-11-04"))

    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": stale}, markets=("twse",))
    assert rc == 3
    assert not (raw / "twse" / "valuation.csv").exists() and csv_days(raw, "twse_quotes") == DAYS
    assert "日期" in state(raw)["sources"]["twse_valuation"]["stopped"]


def test_pause_between_seven_and_nine(raw, cfg):
    clock = Clock(at("2026-11-09", "06:59:50"))
    rc, fakes = run_backfill(raw, cfg, clock, markets=("twse",), max_requests=2)
    assert rc == 0
    (_, _, first), (_, _, second) = fakes["twse"].calls
    assert first == at("2026-11-09", "06:59:50") + timedelta(seconds=6.5)   # 第一個請求也先等 6.5 秒
    assert second == at("2026-11-09", "09:00")   # 07:00:03 輪到第二個，睡到 09:00
    assert state(raw)["last_run"]["requests"] == 2


def test_max_requests_caps_the_run(raw, cfg):
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), max_requests=3)
    assert rc == 0
    assert sum(len(f.calls) for f in fakes.values()) == 3
    assert csv_days(raw, "twse_valuation") == csv_days(raw, "twse_quotes") == csv_days(raw, "tpex_valuation") == [DAYS[-1]]
    assert state(raw)["sources"]["tpex_quotes"]["stopped"] == "max_requests"


def test_ctrl_c_writes_what_was_fetched(raw, cfg):
    def interrupt(kind, day):
        if day == DAYS[-3]:
            raise KeyboardInterrupt

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": interrupt})
    assert rc == 130
    assert all(csv_days(raw, key) == DAYS[-2:] for key in SPECS)
    assert state(raw)["last_run"]["status"] == "interrupted"


def test_flushes_every_twenty_dates(tmp_path, cfg):
    raw = tmp_path / "raw"
    days = weekdays("2026-09-01", 25)
    make_teacher(raw, days=days, pending=())
    newest_first = sorted(days, reverse=True)
    on_disk = {}

    def watch(kind, day):
        if kind == "valuation" and day in (newest_first[19], newest_first[20]):
            on_disk[day] = len(csv_days(raw, "twse_valuation"))

    rc, _ = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"twse": watch}, markets=("twse",))
    assert rc == 0
    assert on_disk == {newest_first[19]: 0, newest_first[20]: 20}
    assert csv_days(raw, "twse_valuation") == days


def test_calendar_uses_training_and_live_and_skips_pending_days(tmp_path, cfg):
    raw = tmp_path / "raw"
    make_teacher(raw, days=["2026-08-27", "2026-08-28", "2026-08-31"], pending=(),
                 live_days=["2026-08-31", "2026-09-01", "2026-09-02"])
    for sid in IDS:   # Live 最後一天還是 -1（像早上的 t 那列）
        path = raw / "teacher" / "live" / "market" / f"{sid}.csv"
        path.write_text(stock_csv(["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"], pending=("2026-09-03",)),
                        encoding="utf-8")
    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), markets=("twse",), start="2026-08-28")
    assert rc == 0
    assert [d for k, d, _ in fakes["twse"].calls if k == "valuation"] == ["2026-09-02", "2026-09-01", "2026-08-31",
                                                                          "2026-08-28"]


def test_backfill_refuses_a_csv_it_cannot_read(raw, cfg):
    crawler.write_atomic(raw / "twse" / "quotes.csv", b"date,stock_id,price\n")
    with pytest.raises(crawler.CrawlerError, match="表頭"):
        run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")))
    assert (raw / "twse" / "quotes.csv").read_bytes() == b"date,stock_id,price\n"


# ================================================================ 指令和設定


def test_cli_runs_the_backfill_without_secrets(monkeypatch, cfg):
    def no(*args, **kwargs):
        raise AssertionError("回補不用帳密，也不寫每天的 log")

    monkeypatch.setattr(utils, "load_config", lambda: cfg)
    monkeypatch.setattr(utils, "load_secrets", no)
    monkeypatch.setattr(utils, "get_logger", no)
    monkeypatch.setattr(crawler, "crawl", no)
    seen = {}

    def fake_backfill(cfg, raw_dir, **kwargs):
        seen.update(kwargs, raw_dir=raw_dir)
        return 3

    monkeypatch.setattr(crawler, "exchange_backfill", fake_backfill)
    assert crawler.main(["--exchange-backfill", "--start", "2024-01-02", "--markets", "tpex", "--max-requests", "4"]) == 3
    assert (seen["start"], seen["end"], seen["markets"], seen["max_requests"]) == ("2024-01-02", None, ("tpex",), 4)
    assert seen["raw_dir"] == utils.ROOT / cfg["data"]["raw_dir"]
    assert crawler.main(["--exchange-backfill"]) == 3 and seen["markets"] == ("twse", "tpex")


@pytest.mark.parametrize("argv", [
    ["--exchange-backfill", "--date", "2026-11-17"],
    ["--exchange-backfill", "--markets", "twse,nyse"],
    ["--exchange-backfill", "--markets", "twse,twse"],
    ["--exchange-backfill", "--start", "2026/01/02"],
    ["--exchange-backfill", "--max-requests", "0"],
    ["--start", "2020-01-02"],
    ["--date", "2026-11-17", "--markets", "twse"],
])
def test_cli_rejects_bad_arguments(argv):
    with pytest.raises(SystemExit):
        crawler.main(argv)


def test_config_exchange_section():
    conf = utils.load_config()["exchange"]
    assert conf["enabled"] is True   # 每天的爬蟲要抓（使用者 2026-11-10 打開）
    assert conf["min_interval_seconds"] >= 6.5 and conf["pause"] == ["07:00", "09:00"]
    assert conf["twse"]["min_stocks"] == 85 and conf["tpex"]["min_stocks"] == 8
    assert conf["gapfill_days"] == 10 and conf["daily_max_requests"] == 12
    assert conf["daily_retries"] == 0 and conf["daily_max_failed_dates"] == 1 and conf["daily_budget_seconds"] > 0


def test_unexpected_error_stops_that_host_and_returns_3(raw, cfg):
    def bug(kind, day):
        raise ValueError("程式沒想到的情況")

    rc, fakes = run_backfill(raw, cfg, Clock(at("2026-11-08", "20:00")), {"tpex": bug})
    assert rc == 3
    assert len(fakes["tpex"].calls) == 1 and csv_days(raw, "twse_quotes") == DAYS
    assert state(raw)["sources"]["tpex_valuation"]["stopped"] == "tpex：ValueError"


# ================================================================ 每天的爬蟲（download_exchange）


@pytest.fixture
def daily_cfg(cfg):
    cfg["exchange"]["enabled"] = True
    return cfg


def daily_run(raw, cfg, clock, *, t="2026-11-09", prev_day="2026-11-06", daily=True):
    run = crawler.Run(cfg=cfg, t=t, daily=daily, raw_dir=raw, log=LOG, now=clock.now, sleep=clock.sleep)
    run.prev_day = prev_day
    run.manifest = {"run": {}}
    return run


def run_daily(raw, cfg, clock, handlers=None, **kwargs):
    """每天的爬蟲的這一步，對假主機跑；t 是 2026-11-09（週一），i 是 11-06（週五）。"""
    fakes = {m: FakeExchange(m, clock, (handlers or {}).get(m)) for m in crawler.EXCHANGE_MARKETS}
    clients = {m: crawler.exchange_client(cfg, m, session=fakes[m], clock=clock.monotonic) for m in fakes}
    run = daily_run(raw, cfg, clock, **kwargs)
    crawler.download_exchange(run, clients=clients, lock_dir=raw.parent / "locks", parallel=False)
    return run, fakes


def seed(raw, days):
    """四個來源的檔案先放 days 這幾天（像回補已經做完）。"""
    for spec in crawler.EXCHANGE_SPECS:
        ids = TW_IDS if spec.market == "twse" else OTC_IDS
        rows = [[d, sid] + ["1"] * (len(spec.columns) - 2) for d in days for sid in ids]
        crawler.write_atomic(raw / spec.file, crawler.exchange_to_csv(rows, spec.columns))


def calls(fake) -> list:
    return [(k, d) for k, d, _ in fake.calls]


def test_daily_disabled_sends_nothing_and_writes_nothing(raw, cfg):
    cfg["exchange"]["enabled"] = False
    run, fakes = run_daily(raw, cfg, Clock(at("2026-11-09", "07:10")))
    assert all(f.calls == [] for f in fakes.values())
    assert "exchange" not in run.manifest and not (raw / "manifest.json").exists()
    assert not (raw.parent / "locks").exists() and not (raw / "twse").exists() and not (raw / "tpex").exists()


def test_daily_normal_day_fetches_only_i(raw, daily_cfg):
    seed(raw, DAYS[:-1])
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")))
    for market in crawler.EXCHANGE_MARKETS:
        assert calls(fakes[market]) == [("valuation", "2026-11-06"), ("quotes", "2026-11-06")]
    assert all(csv_days(raw, key) == DAYS for key in SPECS)
    entry = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))["exchange"]
    assert entry["status"] == "ok" and entry["error"] is None and entry["prev_day"] == "2026-11-06"
    assert entry["dates"] == sorted(DAYS, reverse=True) and entry["requests"] == {"twse": 2, "tpex": 2}
    assert entry["markets"] == ["twse", "tpex"] and entry["locked"] == []
    for key, info in entry["sources"].items():
        assert info["ran"] and info["has_prev_day"] is True and info["new_dates"] == ["2026-11-06"]
        assert info["missing_dates"] == [] and info["failures"] == [] and info["no_data"] == {}
        assert info["last_date"] == "2026-11-06" and info["sha256"] and info["blocked"] is False
    assert not (raw / "exchange_backfill.json").exists()   # 回補的進度檔不碰
    assert run.stale is False
    # 同一天再跑一次（後面的時段）：都有了，一個請求都不送
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:25")))
    assert all(f.calls == [] for f in fakes.values()) and run.manifest["exchange"]["status"] == "ok"


def test_daily_fills_gaps_newest_first_within_the_window(raw, daily_cfg):
    seed(raw, DAYS[:2])   # 11-04、11-05、11-06 都還沒有
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")))
    expected = [(k, d) for d in ("2026-11-06", "2026-11-05", "2026-11-04") for k in ("valuation", "quotes")]
    assert all(calls(f) == expected for f in fakes.values())
    assert all(csv_days(raw, key) == DAYS for key in SPECS)
    assert run.manifest["exchange"]["sources"]["tpex_quotes"]["new_dates"] == ["2026-11-04", "2026-11-05", "2026-11-06"]
    # gapfill_days 只看老師最近幾個交易日：2 天的話 11-04 不補
    raw2 = raw.parent / "raw2"
    make_teacher(raw2)
    seed(raw2, DAYS[:2])
    daily_cfg["exchange"]["gapfill_days"] = 2
    run, fakes = run_daily(raw2, daily_cfg, Clock(at("2026-11-09", "07:10")))
    assert {d for f in fakes.values() for _, d in calls(f)} == {"2026-11-06", "2026-11-05"}
    assert run.manifest["exchange"]["dates"] == ["2026-11-06", "2026-11-05"]
    assert run.manifest["exchange"]["status"] == "ok"   # 視窗外的 11-04 不算缺


def test_daily_does_not_pause_at_seven(raw, daily_cfg):
    seed(raw, DAYS[:-1])
    clock = Clock(at("2026-11-09", "07:10"))
    _, fakes = run_daily(raw, daily_cfg, clock)
    gap = daily_cfg["exchange"]["min_interval_seconds"]
    times = [t for _, _, t in fakes["twse"].calls]
    assert times[0] == at("2026-11-09", "07:10") + timedelta(seconds=gap)   # 回補會睡到 09:00，這一步不睡
    assert max(clock.sleeps) == gap and (times[1] - times[0]).total_seconds() >= gap


def test_daily_failures_only_warn(raw, daily_cfg, caplog):
    """被擋、5xx、no_data 都只寫警告和 manifest，不設 stale；5xx 不重試，一天都失敗就停下那個主機。"""
    seed(raw, DAYS[:-2])   # 11-05、11-06 要抓

    def thin(kind, day):   # 櫃買 11-06 的本益比只有 5 檔：no_data
        if kind == "valuation" and day == "2026-11-06":
            return json_resp(payload("tpex", kind, day, ids=OTC_IDS[:5]))

    clock = Clock(at("2026-11-09", "07:10"))
    with caplog.at_level(logging.INFO, logger=LOG.name):
        run, fakes = run_daily(raw, daily_cfg, clock, {"twse": lambda kind, day: json_503(), "tpex": thin})
    assert run.stale is False
    assert calls(fakes["twse"]) == [("valuation", "2026-11-06"), ("quotes", "2026-11-06")]   # 不重試，停下
    assert len(fakes["tpex"].calls) == 4
    entry = run.manifest["exchange"]
    assert entry["status"] == "incomplete"
    tw = entry["sources"]["twse_valuation"]
    assert tw["blocked"] and "連續 1 天" in tw["stopped"] and tw["has_prev_day"] is False
    assert [f["date"] for f in tw["failures"]] == ["2026-11-06"] and tw["missing_dates"] == ["2026-11-06", "2026-11-05"]
    tp = entry["sources"]["tpex_valuation"]
    assert tp["no_data"] == {"2026-11-06": 5} and tp["missing_dates"] == ["2026-11-06"] and tp["new_dates"] == ["2026-11-05"]
    assert entry["sources"]["tpex_quotes"]["missing_dates"] == []
    assert "還沒有" in caplog.text and daily_cfg["exchange"]["retry_wait_seconds"] not in clock.sleeps
    assert csv_days(raw, "twse_valuation") == DAYS[:-2]


def test_daily_skips_after_the_deadline(raw, daily_cfg):
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "08:31")))
    assert all(f.calls == [] for f in fakes.values())
    assert run.manifest["exchange"] == {"status": "skipped", "error": "skipped_deadline", "prev_day": "2026-11-06"}
    assert run.stale is False


def test_daily_stops_sending_at_the_deadline(raw, daily_cfg):
    clock = Clock(at("2026-11-09", "08:29:50"))
    run, fakes = run_daily(raw, daily_cfg, clock)
    assert calls(fakes["twse"]) == [("valuation", "2026-11-06")]   # 08:29:56.5 送；下一個要等到 08:30:03，不送
    assert fakes["tpex"].calls == []
    assert clock.t < at("2026-11-09", "08:30")
    entry = run.manifest["exchange"]
    assert entry["status"] == "incomplete" and entry["sources"]["twse_quotes"]["stopped"] == "deadline"
    assert csv_days(raw, "twse_valuation") == ["2026-11-06"]


def test_daily_time_budget_also_applies_in_research_mode(raw, daily_cfg):
    daily_cfg["exchange"]["daily_budget_seconds"] = 10
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "20:00")), daily=False)
    assert sum(len(f.calls) for f in fakes.values()) == 1
    assert run.manifest["exchange"]["sources"]["tpex_quotes"]["stopped"] == "deadline"


def test_daily_request_cap_per_host(raw, daily_cfg):
    daily_cfg["exchange"]["daily_max_requests"] = 3
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")))
    expected = [("valuation", "2026-11-06"), ("quotes", "2026-11-06"), ("valuation", "2026-11-05")]
    assert all(calls(f) == expected for f in fakes.values())
    entry = run.manifest["exchange"]
    assert entry["requests"] == {"twse": 3, "tpex": 3} and entry["status"] == "incomplete"
    assert entry["sources"]["twse_quotes"]["missing_dates"] == ["2026-11-05", "2026-11-04", "2026-11-03", "2026-11-02"]
    assert entry["sources"]["twse_valuation"]["new_dates"] == ["2026-11-05", "2026-11-06"]


def test_daily_skips_a_market_whose_backfill_is_running(raw, daily_cfg, caplog):
    fcntl = pytest.importorskip("fcntl")
    seed(raw, DAYS[:-1])
    locks = raw.parent / "locks"
    locks.mkdir()
    with open(locks / "exchange_twse.lock", "w") as held, caplog.at_level(logging.WARNING, logger=LOG.name):
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")))
    assert fakes["twse"].calls == [] and len(fakes["tpex"].calls) == 2
    entry = run.manifest["exchange"]
    assert entry["locked"] == ["twse"] and entry["markets"] == ["tpex"] and entry["status"] == "incomplete"
    assert entry["sources"]["twse_quotes"]["ran"] is False and entry["sources"]["tpex_quotes"]["missing_dates"] == []
    assert "回補正在跑" in caplog.text
    with open(locks / "exchange_tpex.lock", "w") as probe:   # 跑完會放開自己拿的鎖
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_daily_without_prev_day_uses_the_teacher_calendar(raw, daily_cfg):
    """研究模式沒有 Live 金鑰時不知道 i：照老師日曆最後幾天補，has_prev_day 記 None。"""
    seed(raw, DAYS[:-1])
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "21:00")), prev_day=None, daily=False)
    assert all(calls(f) == [("valuation", "2026-11-06"), ("quotes", "2026-11-06")] for f in fakes.values())
    assert run.manifest["exchange"]["sources"]["twse_quotes"]["has_prev_day"] is None


def test_daily_errors_never_escape(raw, daily_cfg):
    crawler.write_atomic(raw / "twse" / "quotes.csv", b"date,stock_id,price\n")   # 看不懂的檔：不覆蓋，這步失敗
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")))
    entry = run.manifest["exchange"]
    assert entry["status"] == "failed" and "表頭" in entry["error"] and run.stale is False
    assert all(f.calls == [] for f in fakes.values())
    assert (raw / "twse" / "quotes.csv").read_bytes() == b"date,stock_id,price\n"
    # 鎖有放開：下一次（檔案修好之後）照常跑
    (raw / "twse" / "quotes.csv").unlink()
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:25")))
    assert run.manifest["exchange"]["status"] == "ok"


def test_daily_unexpected_error_in_one_host_is_contained(raw, daily_cfg):
    def bug(kind, day):
        raise ValueError("程式沒想到的情況")

    seed(raw, DAYS[:-1])
    run, fakes = run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")), {"tpex": bug})
    entry = run.manifest["exchange"]
    assert entry["status"] == "incomplete" and entry["sources"]["tpex_quotes"]["stopped"] == "tpex：ValueError"
    assert entry["sources"]["twse_quotes"]["missing_dates"] == [] and run.stale is False


def test_daily_ctrl_c_is_not_swallowed(raw, daily_cfg):
    def interrupt(kind, day):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_daily(raw, daily_cfg, Clock(at("2026-11-09", "07:10")), {"twse": interrupt})

