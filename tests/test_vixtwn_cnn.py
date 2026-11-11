"""VIXTWN（臺指選擇權波動率指數）和 CNN 恐懼貪婪（使用者 2026-11-09）：爬蟲的兩步和長表的 4 欄。全部離線。

來源和定義見 memory/projects/crawler.md「VIXTWN、CNN 恐懼貪婪」、memory/projects/features.md。
"""

import copy
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src import crawler, features, utils
from tests.test_crawler import (Clock, FakeHttp, FakeResp, at, crawl, fresh_yfdata, make_run,  # noqa: F401（fixture）
                                no_network)
from tests.test_features import bar, cfg_with, fake_repo, small_cfg, small_raw, weekdays, write_csv

VIX_PATH = "/file/taifex/Dailydownload/vix/log2data/{}new.txt"
CNN_PATH = "/index/fearandgreed/graphdata/{}"
# 沒有舊檔時抓全部的開始日：放在 CNN 最早那天（2020-09-19）到 cnn.start 前一天之間，照 t 錯開（crawler.cnn_start）
FULL = {"2026-11-09": "2021-01-26", "2026-11-10": "2021-01-27", "2026-11-17": "2020-09-21"}
NEXT = "2026-10-11"   # t = 2026-11-10、舊檔最近：從 t 往前 30 天
HEADER = "交易日期\t時間(時/分/秒/毫秒)\t臺指選擇權波動率指數\t收盤前1分鐘平均指數"
DASHES = "--------\t-------------------\t--------------------\t-------------------"
NOV = [("2026-11-02", "31.30", "31.28"), ("2026-11-03", "36.83", "36.83"), ("2026-11-04", "35.65", "35.64"),
       ("2026-11-05", "39.92", "39.93"), ("2026-11-06", "46.52", "46.62"), ("2026-11-09", "43.80", "43.70")]
# 2026-11-09 17:20 從期交所抓的 202611new.txt，原樣的位元組
REAL_202611 = (
    b'\xa5\xe6\xa9\xf6\xa4\xe9\xb4\xc1\t\xae\xc9\xb6\xa1(\xae\xc9/\xa4\xc0/\xac\xed/\xb2@\xac\xed)\t\xbbO\xab\xfc'
    b'\xbf\xef\xbe\xdc\xc5v\xaai\xb0\xca\xb2v\xab\xfc\xbc\xc6\t\xa6\xac\xbdL\xabe1\xa4\xc0\xc4\xc1\xa5\xad\xa7\xa1'
    b'\xab\xfc\xbc\xc6\r\n--------\t-------------------\t--------------------\t-------------------\r\n'
    b'20261102\t13450000\t\t\t31.30\t\t31.28\r\n20261103\t13450000\t\t\t36.83\t\t36.83\r\n'
    b'20261104\t13450000\t\t\t35.65\t\t35.64\r\n20261105\t13450000\t\t\t39.92\t\t39.93\r\n'
    b'20261106\t13450000\t\t\t46.52\t\t46.62\r\n20261109\t13450000\t\t\t43.80\t\t43.70\r\n')


@pytest.fixture
def cfg(tmp_path):
    """真的 config（VIXTWN、CNN 的開關是開的，交易所關掉），yfinance 只留兩個序列，1h 不抓。"""
    conf = copy.deepcopy(utils.load_config())
    conf["yfinance"]["tickers"] = {"sox": "^SOX", "etf_0050": "0050.TW"}
    conf["yfinance"]["cache_dir"] = str(tmp_path / "yfcache")
    conf["yfinance"]["hourly"] = {}
    conf["exchange"]["enabled"] = False   # 設定檔 2026-11-10 起是 true；交易所那一步在 tests/test_exchange.py 測
    return conf


# ---------------------------------------------------------------- 假的期交所、CNN


def vix_file(rows) -> bytes:
    lines = [HEADER, DASHES] + [f"{d.replace('-', '')}\t13450000\t\t\t{v}" + (f"\t\t{a}" if a else "")
                                for d, v, a in rows]
    return ("\r\n".join(lines) + "\r\n").encode("cp950")


def vix_fake(months: dict, missing=(), errors=None):
    """months：{YYYYMM: [(日期, 值, 平均)]}。missing 的月份 302 到 404 頁（http），errors：{YYYYMM: 回應}。"""
    routes = {("GET", VIX_PATH.format(m)): FakeResp(200, vix_file(rows)) for m, rows in months.items()}
    for m in missing:
        routes["GET", VIX_PATH.format(m)] = FakeResp(302, b"", {"Location": "http://www.taifex.com.tw/file/taifex/404.htm"})
    for m, resp in (errors or {}).items():
        routes["GET", VIX_PATH.format(m)] = resp
    return FakeHttp(routes)


def ms(day, hhmm="00:00"):
    return datetime.fromisoformat(f"{day}T{hhmm}:00+00:00").timestamp() * 1000


def cnn_body(points, now=None) -> bytes:
    """points：[(美國日期, 時:分 UTC, 分數)]，和真的 JSON 一樣 x 是浮點數的毫秒。"""
    data = [{"x": ms(d, hm), "y": y, "rating": "fear"} for d, hm, y in points]
    now = now or {"score": points[-1][2], "rating": "fear", "timestamp": "2026-11-09T23:10:00+00:00",
                  "previous_close": 22.08, "previous_1_week": 19.4}
    return json.dumps({"fear_and_greed": now,
                       "fear_and_greed_historical": {"timestamp": 0, "score": 0, "rating": "fear", "data": data},
                       "market_volatility_vix": {"data": []}}).encode()


def cnn_fake(responses: dict):
    """responses：{開始日: 回應}。記下每個請求的 kwargs（看 headers）。"""
    seen = []

    def route(start):
        def answer(kwargs):
            seen.append(kwargs)
            return responses[start]
        return answer

    http = FakeHttp({("GET", CNN_PATH.format(s)): route(s) for s in responses})
    http.seen = seen
    return http


def vix_rows(run):
    return crawler.read_points(run.raw_dir / "taifex" / "vixtwn.csv", crawler.VIXTWN_COLUMNS, crawler.vixtwn_cells_ok)


def cnn_rows(run):
    return crawler.read_points(run.raw_dir / "cnn" / "fear_greed.csv", crawler.FEAR_GREED_COLUMNS, crawler.score_ok)


def vix_run(tmp_path, cfg, clock, http, t="2026-11-10", prev_day="2026-11-09"):
    run = make_run(tmp_path, cfg, clock, t=t)
    run.prev_day = prev_day
    crawler.download_vixtwn(run, crawler.vixtwn_client(cfg, clock.sleep, http, clock.monotonic))
    return run


def cnn_run(tmp_path, cfg, clock, http, t="2026-11-10", prev_day="2026-11-09"):
    run = make_run(tmp_path, cfg, clock, t=t)
    run.prev_day = prev_day
    crawler.download_fear_greed(run, crawler.cnn_client(cfg, clock.sleep, http, clock.monotonic))
    return run


# ---------------------------------------------------------------- VIXTWN：解析


def test_vix_file_helper_matches_the_real_file():
    assert vix_file(NOV) == REAL_202611


def test_parse_vixtwn_real_file():
    assert crawler.parse_vixtwn(REAL_202611, "202611") == {d: (v, a) for d, v, a in NOV}


def test_parse_vixtwn_without_the_one_minute_average():
    """2020-11-23 以前沒有「收盤前1分鐘平均指數」那一欄。"""
    assert crawler.parse_vixtwn(vix_file([("2020-11-20", "25.10", "")]), "202011") == {"2020-11-20": ("25.10", "")}


@pytest.mark.parametrize("body", [
    b"<html>404</html>",
    vix_file(NOV).replace(b"13450000", b"13440000", 1),                   # 不是 13:45 的值
    vix_file(NOV + [("2026-11-09", "43.80", "43.70")]),                   # 同一天兩列
    vix_file([("2026-10-30", "30.00", "30.10")]),                         # 不是這個月
    vix_file([("2026-11-02", "0", "31.28")]),                              # 值不 > 0
    vix_file([("2026-11-02", "abc", "31.28")]),
    vix_file(NOV).replace(b"\t\t31.28", b"\t\t31.28\t\t9", 1),             # 多一欄
    vix_file([("2026-11-02", "31.30", "")]),                               # 少一格：2020-11-23 起每列都有平均
    "交易日期\t時間\n20261102\t13450000\t31.30".encode("utf-8"),            # 不是 CP950
    vix_file([("2026-11-31", "31.30", "31.28")]),                          # 沒有這天：存進去之後每天都讀不了檔
    vix_file([("2026-11-00", "31.30", "31.28")]),
    vix_file([("2026-11-02", "31.30", "0")]),                              # 平均不 > 0
    vix_file([("2026-11-02", "31.30", "abc")]),
])
def test_parse_vixtwn_rejects_a_changed_format(body):
    with pytest.raises(crawler.CrawlerError):
        crawler.parse_vixtwn(body, "202611")


@pytest.mark.parametrize("text", [
    "date,vixtwn,vixtwn_1min_avg\n2026-11-02,31.30,31.28\n2026-11-02,31.30,31.28\n",   # 同一天兩列
    "date,vixtwn,vixtwn_1min_avg\n2026/11/02,31.30,31.28\n",                         # 不是 YYYY-MM-DD
    "date,vixtwn,vixtwn_1min_avg\n2026-11-02,31.30\n",                               # 少一格
])
def test_read_points_rejects_a_hand_edited_file(tmp_path, text):
    path = tmp_path / "vixtwn.csv"
    path.write_text(text)
    with pytest.raises(crawler.CrawlerError, match="壞掉的列"):
        crawler.read_points(path, crawler.VIXTWN_COLUMNS, crawler.vixtwn_cells_ok)


def test_vixtwn_months():
    conf = {"start_month": "2026-08", "overlap_days": 7}
    end = datetime(2026, 11, 9).date()
    assert crawler.vixtwn_months({}, end, conf) == ["202608", "202609", "202610", "202611"]
    assert crawler.vixtwn_months({"2026-11-06": ("1", "")}, end, conf) == ["202610", "202611"]   # 11-06 往前 7 天是 10-30
    assert crawler.vixtwn_months({"2026-11-09": ("1", "")}, datetime(2026, 11, 10).date(), conf) == ["202611"]
    assert crawler.vixtwn_months({"2026-12-31": ("1", "")}, datetime(2027, 1, 4).date(), conf) == ["202612", "202701"]


# ---------------------------------------------------------------- VIXTWN：每天的一步


def test_vixtwn_first_run_takes_every_month_and_keeps_only_dates_before_t(tmp_path, cfg):
    clock = Clock(at("2026-11-10", "07:10"))
    http = vix_fake({"202608": [("2026-08-03", "20.00", "20.10")], "202609": [("2026-09-01", "21.00", "21.10")],
                     "202610": [("2026-10-30", "30.00", "30.10")], "202611": NOV + [("2026-11-10", "50.00", "50.10")]})
    run = vix_run(tmp_path, cfg, clock, http)
    rows = vix_rows(run)
    assert rows["2026-11-09"] == ("43.80", "43.70") and "2026-11-10" not in rows and len(rows) == 9
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "ok" and entry["requests"] == 4 and entry["missing_months"] == []
    assert entry["months"] == ["202608", "202609", "202610", "202611"] and len(entry["new_dates"]) == 9
    assert entry["has_prev_day"] is True and entry["last_dates"] == ["2026-11-06", "2026-11-09"]
    assert clock.sleeps == [2, 2, 2, 2] and not run.stale
    assert json.loads((run.raw_dir / "manifest.json").read_text())["vixtwn"]["status"] == "ok"
    assert (run.raw_dir / "taifex" / "vixtwn.csv").read_text().splitlines()[:2] == [
        "date,vixtwn,vixtwn_1min_avg", "2026-08-03,20.00,20.10"]


def test_vixtwn_second_run_fetches_the_last_week_and_merges(tmp_path, cfg):
    vix_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")),
            vix_fake({"202611": NOV[:5]}, missing=("202608", "202609", "202610")), t="2026-11-09", prev_day="2026-11-06")
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")],
                     "202611": [NOV[0], ("2026-11-03", "36.90", "36.83"), *NOV[2:]]})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["months"] == ["202610", "202611"] and entry["requests"] == 2   # 11-06 往前 7 天是 10 月
    assert entry["new_dates"] == ["2026-10-30", "2026-11-09"] and entry["changed_dates"] == ["2026-11-03"]
    assert vix_rows(run)["2026-11-03"] == ("36.90", "36.83")


def test_vixtwn_month_without_a_file_is_not_a_failure(tmp_path, cfg):
    """期交所只留最近約 4 個月，更早的 302 到 404 頁：記在 missing_months，這一步還是 ok。"""
    clock = Clock(at("2026-11-10", "07:10"))
    run = vix_run(tmp_path, cfg, clock, vix_fake({"202609": [("2026-09-01", "21.00", "21.10")], "202610": [],
                                                  "202611": NOV}, missing=("202608",)))
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "ok" and entry["missing_months"] == ["202608"] and len(vix_rows(run)) == 7


def test_vixtwn_month_of_i_without_a_file_is_incomplete(tmp_path, cfg):
    """i 所在的月份也 302：網址可能改了，不能算 ok（審查 2026-11-09）。抓到的照樣存。"""
    cfg["vixtwn"]["start_month"] = "2026-10"
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")]}, missing=("202611",))
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and "202611" in entry["error"] and entry["missing_months"] == ["202611"]
    assert list(vix_rows(run)) == ["2026-10-30"] and not run.stale


def test_vixtwn_dates_missing_from_a_fetched_month_are_kept_and_reported(tmp_path, cfg):
    vix_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")),
            vix_fake({"202611": NOV[:5]}, missing=("202608", "202609", "202610")), t="2026-11-09", prev_day="2026-11-06")
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")], "202611": [NOV[0], *NOV[2:]]})   # 11-03 不見了
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "ok" and entry["vanished_dates"] == ["2026-11-03"]
    assert vix_rows(run)["2026-11-03"] == ("36.83", "36.83")


@pytest.mark.parametrize("resp, error", [
    (FakeResp(503), "HTTP 503"), (FakeResp(404), "HTTP 404"), (FakeResp(200, b"<html>busy</html>"), "表頭"),
])
def test_vixtwn_failure_keeps_the_old_file_and_does_not_mark_stale(tmp_path, cfg, resp, error):
    first = vix_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")),
                    vix_fake({"202611": NOV[:5]}, missing=("202608", "202609", "202610")), t="2026-11-09",
                    prev_day="2026-11-06")
    before = (first.raw_dir / "taifex" / "vixtwn.csv").read_bytes()
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")),
                  vix_fake({"202610": []}, errors={"202611": resp}))
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "failed" and error in entry["error"] and not run.stale
    assert (run.raw_dir / "taifex" / "vixtwn.csv").read_bytes() == before
    assert entry["rows"] == 5 and entry["has_prev_day"] is False


def test_vixtwn_broken_old_file_is_left_alone(tmp_path, cfg):
    path = tmp_path / "raw" / "taifex" / "vixtwn.csv"
    write_csv(path, ("date", "vix"), [["2026-11-06", "46.52"]])
    http = vix_fake({"202611": NOV})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "failed" and "表頭不對" in entry["error"]
    assert http.calls == [] and path.read_text() == "date,vix\n2026-11-06,46.52\n"
    # 讀不了不是空的：列數、最後兩天、有沒有 i 都記 None（審查 2026-11-09）
    assert entry["old_file_unreadable"] is True and entry["rows"] is None and entry["last_dates"] is None
    assert entry["has_prev_day"] is None and "sha256" in entry


def test_vixtwn_after_the_deadline_is_skipped(tmp_path, cfg):
    http = vix_fake({"202611": NOV})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "08:31")), http)
    assert run.manifest["vixtwn"]["status"] == "skipped" and http.calls == []


def test_vixtwn_budget_keeps_what_it_already_has(tmp_path, cfg):
    cfg["vixtwn"]["budget_seconds"] = 3   # 等 2 秒送第一個；第二個要再等 2 秒就超過
    http = vix_fake({"202608": [("2026-08-03", "20.00", "20.10")], "202609": [], "202610": [], "202611": NOV})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and "202609" in entry["error"] and entry["requests"] == 1
    assert list(vix_rows(run)) == ["2026-08-03"]


def test_vixtwn_switch_off_sends_nothing(tmp_path, cfg):
    cfg["vixtwn"]["enabled"] = False
    http = vix_fake({"202611": NOV})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    assert "vixtwn" not in run.manifest and http.calls == []


def test_vixtwn_does_not_retry(tmp_path, cfg):
    cfg["vixtwn"]["start_month"] = "2026-11"
    clock = Clock(at("2026-11-10", "07:10"))
    http = vix_fake({}, errors={"202611": FakeResp(503)})
    run = vix_run(tmp_path, cfg, clock, http)
    assert run.manifest["vixtwn"]["status"] == "failed" and len(http.calls) == 1 and clock.sleeps == [2]


def test_vixtwn_sends_nothing_after_the_deadline_inside_the_loop(tmp_path, cfg):
    """08:29:57 開始、要抓兩個月：第二個月的請求會在 08:30 之後，不送（審查 2026-11-09）。"""
    cfg["vixtwn"]["start_month"] = "2026-10"
    clock = Clock(at("2026-11-10", "08:29").replace(second=57))
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")], "202611": NOV})
    sent_at = []
    original = http.request

    def stamped(method, url, **kwargs):
        sent_at.append(clock.now())
        return original(method, url, **kwargs)

    http.request = stamped
    run = vix_run(tmp_path, cfg, clock, http)
    entry = run.manifest["vixtwn"]
    assert len(sent_at) == 1 and sent_at[0] < at("2026-11-10", "08:30")
    assert entry["requests"] == 1 and entry["status"] == "incomplete" and "202611" in entry["error"]


@pytest.mark.parametrize("t, i, old_month, new_month", [
    ("2026-12-01", "2026-11-30", "202611", "202612"),   # 12 月第一個交易日：07:10 還沒有 12 月的檔
    ("2026-03-02", "2026-02-27", "202602", "202603"),   # 週一，i 是上個月最後一個週五
])
def test_vixtwn_takes_the_month_of_i_at_a_month_boundary(tmp_path, cfg, t, i, old_month, new_month):
    cfg["vixtwn"]["start_month"] = f"{old_month[:4]}-{old_month[4:]}"
    http = vix_fake({old_month: [(i, "31.00", "31.10")]}, missing=(new_month,))
    run = vix_run(tmp_path, cfg, Clock(at(t, "07:10")), http, t=t, prev_day=i)
    entry = run.manifest["vixtwn"]
    assert entry["months"] == [old_month] and entry["status"] == "ok" and entry["has_prev_day"] is True


def test_vixtwn_ok_but_without_i_warns(tmp_path, cfg, caplog):
    cfg["vixtwn"]["start_month"] = "2026-11"
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), vix_fake({"202611": NOV[:5]}))   # 沒有 11-09
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "ok" and entry["has_prev_day"] is False
    assert any("VIXTWN 沒有 2026-11-09" in r.getMessage() for r in caplog.records)


def test_vixtwn_an_older_month_failing_still_takes_the_month_of_i(tmp_path, cfg):
    """月初抓兩個月，上個月逾時或 5xx：i 的月份照抓照存，算 incomplete；沒抓到的月份不算不見（審查 2026-11-09）。"""
    vix_run(tmp_path, cfg, Clock(at("2026-12-01", "07:10")),
            vix_fake({"202611": [("2026-11-27", "30.00", "30.10"), ("2026-11-30", "31.00", "31.10")]},
                     missing=("202608", "202609", "202610", "202612")), t="2026-12-01", prev_day="2026-11-30")
    http = vix_fake({"202612": [("2026-12-01", "32.00", "32.10")]}, errors={"202611": FakeResp(503)})
    run = vix_run(tmp_path, cfg, Clock(at("2026-12-02", "07:10")), http, t="2026-12-02", prev_day="2026-12-01")
    entry = run.manifest["vixtwn"]
    assert entry["months"] == ["202611", "202612"] and entry["requests"] == 2
    assert entry["status"] == "incomplete" and "202611" in entry["error"] and "HTTP 503" in entry["error"]
    assert list(entry["failed_months"]) == ["202611"] and entry["vanished_dates"] == []
    assert vix_rows(run)["2026-12-01"] == ("32.00", "32.10") and entry["has_prev_day"] is True


def test_vixtwn_the_month_of_i_failing_is_a_failure_but_keeps_the_rest(tmp_path, cfg):
    cfg["vixtwn"]["start_month"] = "2026-10"
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")]}, errors={"202611": FakeResp(503)})
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "failed" and entry["error"].startswith("i 所在的月份 202611 沒抓到")
    assert list(vix_rows(run)) == ["2026-10-30"] and not run.stale


@pytest.mark.parametrize("case", ["missing", "deadline", "failed"])
def test_vixtwn_first_run_leaves_no_empty_file_when_the_month_of_i_was_not_read(tmp_path, cfg, case, caplog):
    """沒有舊檔，i 的月份 302、時間到了沒送、或 5xx：不留只有表頭的檔。留了的話 features 少一條「沒有檔」的註記，
    空檔還會跟著 data/raw 被推上去（審查 2026-11-10）。i 的月份沒讀到時也不報「沒有 i 的值」。"""
    cfg["vixtwn"]["start_month"] = "2026-11"
    clock = Clock(at("2026-11-10", "08:29").replace(second=59) if case == "deadline" else at("2026-11-10", "07:10"))
    http = {"missing": vix_fake({}, missing=("202611",)), "deadline": vix_fake({"202611": NOV}),
            "failed": vix_fake({}, errors={"202611": FakeResp(503)})}[case]
    run = vix_run(tmp_path, cfg, clock, http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == ("failed" if case == "failed" else "incomplete") and entry["rows"] == 0
    assert len(http.calls) == (0 if case == "deadline" else 1)
    assert not (run.raw_dir / "taifex" / "vixtwn.csv").exists() and "sha256" not in entry
    assert not any("VIXTWN 沒有 2026-11-09" in r.getMessage() for r in caplog.records)


def test_vixtwn_month_of_i_read_but_empty_still_writes_the_file(tmp_path, cfg):
    """i 的月份讀到了、裡面沒有早於 t 的列（月初）：照樣建檔，下次看得出這個月抓過。"""
    cfg["vixtwn"]["start_month"] = "2026-11"
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-02", "07:10")), vix_fake({"202611": NOV}), t="2026-11-02",
                  prev_day="2026-11-02")
    assert run.manifest["vixtwn"]["rows"] == 0 and (run.raw_dir / "taifex" / "vixtwn.csv").exists()


def test_vixtwn_without_i_still_reports_when_no_month_could_be_read(tmp_path, cfg):
    """不知道 i 時，月初那個月沒有檔不報；一個月都沒讀到（例如網址改了）要報（審查 2026-11-10）。"""
    clock = Clock(at("2026-11-10", "10:00"))
    run = make_run(tmp_path, cfg, clock, t="2026-11-10", daily=False)
    assert run.prev_day is None
    http = vix_fake({}, missing=("202608", "202609", "202610", "202611"))
    crawler.download_vixtwn(run, crawler.vixtwn_client(cfg, clock.sleep, http, clock.monotonic))
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and "t 前一天所在的月份 202611 期交所沒有檔" in entry["error"]
    assert not (run.raw_dir / "taifex" / "vixtwn.csv").exists()


def test_vixtwn_warns_about_a_missing_i_even_when_an_older_month_failed(tmp_path, cfg, caplog):
    """上個月 5xx（incomplete），i 的月份讀到了但還沒有 i：照樣要說 i 沒有值（審查 2026-11-10）。"""
    vix_run(tmp_path, cfg, Clock(at("2026-12-01", "07:10")),
            vix_fake({"202611": [("2026-11-30", "31.00", "31.10")]}, missing=("202608", "202609", "202610", "202612")),
            t="2026-12-01", prev_day="2026-11-30")
    caplog.clear()
    http = vix_fake({"202612": [("2026-12-01", "32.00", "32.10")]}, errors={"202611": FakeResp(503)})
    run = vix_run(tmp_path, cfg, Clock(at("2026-12-03", "07:10")), http, t="2026-12-03", prev_day="2026-12-02")
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and entry["has_prev_day"] is False
    assert [r.getMessage() for r in caplog.records if "VIXTWN 沒有" in r.getMessage()] == [
        "VIXTWN 沒有 2026-12-02 的值，vixtwn 欄那天會是空白"]


@pytest.mark.parametrize("resp", [FakeResp(404), FakeResp(200, b"x" * 100_000)])   # 100 KB 超過 vixtwn.max_kb
def test_vixtwn_an_older_month_with_a_non_retryable_error_still_takes_the_month_of_i(tmp_path, cfg, resp):
    """上個月 404 或回應太大（不是逾時、5xx 那一類）：一樣只算那個月沒抓到，i 的月份照抓照存。"""
    cfg["vixtwn"]["start_month"] = "2026-10"
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), vix_fake({"202611": NOV}, errors={"202610": resp}))
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and list(entry["failed_months"]) == ["202610"] and entry["requests"] == 2
    assert vix_rows(run)["2026-11-09"] == ("43.80", "43.70") and entry["has_prev_day"] is True


@pytest.mark.parametrize("stop", ["budget", "missing"])
def test_vixtwn_months_not_read_do_not_report_their_old_dates_as_vanished(tmp_path, cfg, stop):
    """舊檔有 11 月：11 月因為時間到了沒抓、或 11 月的檔 302，舊的 11 月日子都不能記成「這次沒有」。"""
    vix_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")),
            vix_fake({"202611": NOV[:5]}, missing=("202608", "202609", "202610")), t="2026-11-09", prev_day="2026-11-06")
    if stop == "budget":
        cfg["vixtwn"]["budget_seconds"] = 3
        http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")], "202611": NOV})
    else:
        http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")]}, missing=("202611",))
    run = vix_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "incomplete" and entry["vanished_dates"] == [] and len(vix_rows(run)) == 6


def test_vixtwn_without_i_does_not_call_a_missing_month_a_changed_url(tmp_path, cfg):
    """研究模式沒有 Live 的帳號時 i 不知道，end 用 t 前一天：月初那個月可能還沒有檔，不能報「網址可能改了」。"""
    cfg["vixtwn"]["start_month"] = "2026-10"
    clock = Clock(at("2026-11-02", "10:00"))
    run = make_run(tmp_path, cfg, clock, t="2026-11-02", daily=False)
    assert run.prev_day is None
    http = vix_fake({"202610": [("2026-10-30", "30.00", "30.10")]}, missing=("202611",))
    crawler.download_vixtwn(run, crawler.vixtwn_client(cfg, clock.sleep, http, clock.monotonic))
    entry = run.manifest["vixtwn"]
    assert entry["status"] == "ok" and entry["missing_months"] == ["202611"] and entry["has_prev_day"] is None


# ---------------------------------------------------------------- CNN：解析


def test_parse_fear_greed_keeps_daily_points_before_t():
    """每天那點在 00:00 UTC；最後的「現在」點、t 那天先建好的點、start 以前的假值都丟。"""
    body = cnn_body([("2021-01-21", "00:00", 50.0), ("2021-02-01", "00:00", 43.4), ("2026-11-06", "00:00", 23.648),
                     ("2026-11-09", "00:00", 24.1), ("2026-11-10", "00:00", 24.1), ("2026-11-10", "00:05", 24.2)])
    rows, now, dropped = crawler.parse_fear_greed(body, "2026-11-10", "2021-02-01")
    assert rows == {"2021-02-01": ("43.4",), "2026-11-06": ("23.648",), "2026-11-09": ("24.1",)}
    assert dropped == {"not_daily": 1, "on_or_after_t": 1, "before_start": 1}
    assert now == {"score": 24.2, "timestamp": "2026-11-09T23:10:00+00:00", "previous_close": 22.08}


def test_parse_fear_greed_integer_score_and_zero():
    rows, _, _ = crawler.parse_fear_greed(cnn_body([("2025-04-08", "00:00", 0), ("2025-04-09", "00:00", 100)]),
                                          "2025-04-10", "2021-02-01")
    assert rows == {"2025-04-08": ("0.0",), "2025-04-09": ("100.0",)}


def test_parse_fear_greed_keeps_only_clean_now_values():
    """「現在」的分數只寫進 manifest：不是有限數字的值、有怪字元的時間都不留，免得 manifest 寫不出來（審查 2026-11-09）。"""
    now = {"score": True, "previous_close": float("nan"), "timestamp": "\ud800", "rating": "fear"}
    body = json.dumps({"fear_and_greed": now,
                       "fear_and_greed_historical": {"data": [{"x": ms("2026-11-06"), "y": 23.6}]}}).encode()
    assert crawler.parse_fear_greed(body, "2026-11-10", "2021-02-01")[1] == {}


@pytest.mark.parametrize("body", [
    b"Internal Server Error",
    b'{"fear_and_greed": {}}',
    b'{"fear_and_greed_historical": {"data": {"x": 1}}}',
    cnn_body([("2026-11-06", "00:00", 101.0)]),
    cnn_body([("2026-11-06", "00:00", -0.5)]),
    cnn_body([("2026-11-06", "00:00", 23.6), ("2026-11-06", "00:00", 23.7)]),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": "1794182400000", "y": 20}]}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": 1794182400000, "y": "20"}]}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": True, "y": 20}]}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": 1794182400000.5, "y": 20}]}}).encode(),
    cnn_body([("2026-11-06", "05:00", 23.6), ("2026-11-09", "05:00", 24.1)]),    # 每天的點不在 00:00 UTC 了
    cnn_body([("2026-11-05", "00:00", 19.99), ("2026-11-06", "05:00", 23.6),     # 只有最新的幾天換時間
              ("2026-11-09", "05:00", 24.1), ("2026-11-09", "23:10", 24.1)]),
    cnn_body([("2026-11-09", "23:10", 24.1)]),                                   # 只有「現在」的點
    json.dumps({"fear_and_greed_historical": {"data": []}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": ms("2026-11-06"), "y": 20}, {"x": True, "y": 20}]}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": ms("2026-11-06"), "y": 20},             # 不在 2000～2100 年
                                                       {"x": crawler.DAY_MS * 3_000_000, "y": 20}]}}).encode(),
    json.dumps({"fear_and_greed_historical": {"data": [{"x": ms("2026-11-06"), "y": 20}, {"x": -crawler.DAY_MS, "y": 20}]}}).encode(),
])
def test_parse_fear_greed_rejects_a_changed_format(body):
    with pytest.raises(crawler.CrawlerError):
        crawler.parse_fear_greed(body, "2026-11-10", "2021-02-01")


# ---------------------------------------------------------------- CNN：每天的一步


def test_cnn_start_is_different_for_every_t():
    """CDN 對要過的網址會先回上一次存的那份（2026-11-09 查到），所以每個 t 的開始日都要不一樣（審查 2026-11-09）。"""
    conf = {"start": "2021-02-01", "fetch_days": 30, "overlap_days": 10}
    recent = {"2026-11-06": ("23.6",)}
    assert crawler.cnn_start(recent, "2026-11-10", conf) == "2026-10-11"   # 平常：t 往前 30 天
    assert crawler.cnn_start(recent, "2026-11-11", conf) == "2026-10-12"   # 檔沒有變（例如美國假日）網址也會換
    assert crawler.cnn_start({"2026-10-21": ("1",)}, "2026-11-10", conf) == "2026-10-11"   # 最後一天剛好重疊 10 天
    # 沒有舊檔、或舊檔停太久：抓全部，開始日在 CNN 最早那天到 cnn.start 前一天之間，照 t 錯開
    assert crawler.cnn_start({}, "2026-11-10", conf) == "2021-01-27"
    assert crawler.cnn_start({"2026-10-20": ("1",)}, "2026-11-10", conf) == "2021-01-27"
    days = [(datetime(2026, 11, 10) + pd.Timedelta(days=k)).date().isoformat() for k in range(135)]
    full = [crawler.cnn_start({}, d, conf) for d in days]
    assert len(set(full)) == 135 and min(full) == crawler.CNN_FIRST and max(full) == "2021-01-31"
    assert {d: crawler.cnn_start({}, d, conf) for d in FULL} == FULL


def test_fear_greed_first_run_takes_everything_with_browser_headers(tmp_path, cfg):
    http = cnn_fake({FULL["2026-11-10"]: FakeResp(
        200, cnn_body([("2021-01-27", "00:00", 52.9), ("2021-02-01", "00:00", 43.4), ("2026-11-06", "00:00", 23.6),
                       ("2026-11-09", "00:00", 24.1), ("2026-11-09", "23:10", 24.1)]),
        {"Age": "0", "X-Cache": "MISS, MISS"})})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["cnn"]
    assert entry["status"] == "ok" and entry["start"] == "2021-01-27" and entry["requests"] == 1
    assert entry["last_dates"] == ["2026-11-06", "2026-11-09"]
    assert entry["has_prev_day"] is None   # CNN 是美國日期，對不上台股的 i（審查 2026-11-09）
    assert entry["now"]["previous_close"] == 22.08 and entry["dropped"]["not_daily"] == 1
    assert entry["dropped"]["before_start"] == 1 and entry["cache"] == {"Age": "0", "X-Cache": "MISS, MISS"}
    assert cnn_rows(run) == {"2021-02-01": ("43.4",), "2026-11-06": ("23.6",), "2026-11-09": ("24.1",)}
    assert http.seen[0]["headers"] == {"Accept": "application/json", "Referer": "https://edition.cnn.com/"}
    assert http.headers["User-Agent"].startswith("Mozilla/5.0")   # 不像瀏覽器的 User-Agent 會被回 418
    assert not run.stale


def test_fear_greed_second_run_overlaps_and_takes_the_new_values(tmp_path, cfg):
    """最後一天的分數收盤後還會被改：重疊的日子用新的值，記在 changed_dates。抓的範圍外的舊日子不算不見。"""
    first = {FULL["2026-11-09"]: FakeResp(200, cnn_body([("2026-10-01", "00:00", 40.0), ("2026-11-05", "00:00", 19.99),
                                                         ("2026-11-06", "00:00", 23.75)]))}
    cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    http = cnn_fake({NEXT: FakeResp(200, cnn_body([("2026-11-05", "00:00", 19.99), ("2026-11-06", "00:00", 23.65),
                                                   ("2026-11-09", "00:00", 24.1)]))})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = run.manifest["cnn"]
    assert entry["start"] == NEXT and entry["new_dates"] == ["2026-11-09"] and entry["vanished_dates"] == []
    assert entry["changed_dates"] == ["2026-11-06"] and cnn_rows(run)["2026-11-06"] == ("23.65",)
    assert cnn_rows(run)["2026-10-01"] == ("40.0",)


def test_fear_greed_url_changes_even_when_the_file_does_not(tmp_path, cfg):
    """美國假日那天 CNN 沒有新的點，檔的最後一天不變。舊版的開始日跟著檔走，隔天會要同一個網址，
    CDN 就回前一天存的那份（審查 2026-11-09）。"""
    body = cnn_body([("2026-11-05", "00:00", 19.99), ("2026-11-06", "00:00", 23.65)])
    first = {FULL["2026-11-09"]: FakeResp(200, body)}
    cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    seen = []
    for t in ("2026-11-10", "2026-11-11"):
        http = cnn_fake({crawler.cnn_start({"2026-11-06": ()}, t, cfg["cnn"]): FakeResp(200, body)})
        run = cnn_run(tmp_path, cfg, Clock(at(t, "07:10")), http, t=t, prev_day="2026-11-09")
        assert run.manifest["cnn"]["status"] == "ok" and run.manifest["cnn"]["new_dates"] == []
        seen += http.calls
    assert seen == [("GET", CNN_PATH.format("2026-10-11")), ("GET", CNN_PATH.format("2026-10-12"))]


def test_fear_greed_keeps_only_plain_cache_headers(tmp_path, cfg):
    resp = FakeResp(200, cnn_body([("2026-11-06", "00:00", 23.75)]), {"age": "7200", "x-cache": "HIT\ud800"})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), cnn_fake({FULL["2026-11-10"]: resp}))
    saved = json.loads((run.raw_dir / "manifest.json").read_text())["cnn"]
    assert saved["status"] == "ok" and saved["cache"] == {"Age": "7200"}


def test_fear_greed_dates_missing_from_the_response_are_kept_and_reported(tmp_path, cfg):
    first = {FULL["2026-11-09"]: FakeResp(200, cnn_body([("2026-11-02", "00:00", 19.0), ("2026-11-05", "00:00", 19.99),
                                                         ("2026-11-06", "00:00", 23.75)]))}
    cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    http = cnn_fake({NEXT: FakeResp(200, cnn_body([("2026-11-05", "00:00", 19.99), ("2026-11-06", "00:00", 23.65),
                                                   ("2026-11-09", "00:00", 24.1)]))})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    assert run.manifest["cnn"]["status"] == "ok" and run.manifest["cnn"]["vanished_dates"] == ["2026-11-02"]
    assert cnn_rows(run)["2026-11-02"] == ("19.0",)


def test_fear_greed_drops_the_old_last_day_when_cnn_no_longer_lists_it(tmp_path, cfg, caplog):
    """舊檔的最後一天是上次抓到時還在變的值。CNN 之後拿掉那天（像 2026-03-12 那種缺口）：留著的話 second_last 會
    把它當成定住的分數用，所以拿掉；其他不見的日子照樣留著，回應少一段時才不會清掉舊資料（審查 2026-11-10）。"""
    first = {FULL["2026-11-09"]: FakeResp(200, cnn_body([("2026-11-02", "00:00", 19.0), ("2026-11-05", "00:00", 19.99),
                                                         ("2026-11-06", "00:00", 23.75)]))}
    cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    http = cnn_fake({NEXT: FakeResp(200, cnn_body([("2026-11-05", "00:00", 19.99), ("2026-11-09", "00:00", 24.1)]))})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    entry = json.loads((run.raw_dir / "manifest.json").read_text())["cnn"]
    assert entry["status"] == "ok" and entry["vanished_dates"] == ["2026-11-02", "2026-11-06"]
    assert entry["dropped_last"] == "2026-11-06" and entry["rows"] == 3
    assert cnn_rows(run) == {"2026-11-02": ("19.0",), "2026-11-05": ("19.99",), "2026-11-09": ("24.1",)}
    messages = [r.getMessage() for r in caplog.records]
    assert any("舊檔的最後一天 2026-11-06" in m and "拿掉" in m for m in messages)
    assert any("['2026-11-02'] 這次的回應沒有，檔裡留著舊的值" in m for m in messages)


def test_fear_greed_records_the_cache_headers_of_a_failed_response(tmp_path, cfg):
    """失敗時也記 CDN 的標頭：看得出錯誤是 CDN 存的那份還是 CNN 剛回的。"""
    first = {FULL["2026-11-09"]: FakeResp(200, cnn_body([("2026-11-06", "00:00", 23.75)]))}
    cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    http = cnn_fake({NEXT: FakeResp(503, b"", {"Age": "86000", "X-Cache": "HIT, HIT"})})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    saved = json.loads((run.raw_dir / "manifest.json").read_text())["cnn"]
    assert saved["status"] == "failed" and saved["cache"] == {"Age": "86000", "X-Cache": "HIT, HIT"}
    assert "dropped_last" not in saved and list(cnn_rows(run)) == ["2026-11-06"]


def test_fear_greed_odd_now_values_do_not_break_the_manifest(tmp_path, cfg):
    now = {"score": 24.1, "timestamp": "\ud800", "previous_close": 22.08}
    http = cnn_fake({FULL["2026-11-10"]: FakeResp(200, cnn_body([("2026-11-06", "00:00", 23.75)], now=now))})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    saved = json.loads((run.raw_dir / "manifest.json").read_text())["cnn"]
    assert saved["status"] == "ok" and saved["now"] == {"score": 24.1, "previous_close": 22.08}


def test_side_finish_falls_back_to_a_short_entry_when_the_manifest_cannot_be_written(tmp_path, cfg):
    """side_finish 在 finally 裡，例外跑出去會讓整個爬蟲停下（審查 2026-11-09）。"""
    run = make_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), t="2026-11-10")
    entry = crawler.side_entry(run, "cnn", "cnn/fear_greed.csv")
    entry["now"] = {"timestamp": "\ud800"}   # ensure_ascii=False 寫不出單獨的 surrogate
    crawler.side_finish(run, "cnn", entry, run.raw_dir / "cnn" / "fear_greed.csv", {})
    saved = json.loads((run.raw_dir / "manifest.json").read_text())["cnn"]
    assert saved == {"status": "failed", "error": "manifest 寫不出來（UnicodeEncodeError）", "file": "cnn/fear_greed.csv"}


def test_side_finish_warns_when_it_cannot_record_the_file(tmp_path, cfg, monkeypatch, caplog):
    run = make_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), t="2026-11-10")
    path = run.raw_dir / "cnn" / "fear_greed.csv"
    write_csv(path, crawler.FEAR_GREED_COLUMNS, [["2026-11-06", "23.6"]])

    def refuse(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(crawler.Path, "read_bytes", refuse)
    entry = crawler.side_entry(run, "cnn", "cnn/fear_greed.csv")
    crawler.side_finish(run, "cnn", entry, path, {"2026-11-06": ("23.6",)})
    assert run.manifest["cnn"]["finish_error"] == "PermissionError"
    assert any("記不了檔案的狀態" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("resp", [FakeResp(418, b"I'm a teapot"), FakeResp(500), FakeResp(200, b"<html></html>"),
                                  FakeResp(302, b"", {"Location": "https://edition.cnn.com/"})])
def test_fear_greed_failure_keeps_the_old_file(tmp_path, cfg, resp):
    first = {FULL["2026-11-09"]: FakeResp(200, cnn_body([("2026-11-06", "00:00", 23.75)]))}
    old = cnn_run(tmp_path, cfg, Clock(at("2026-11-09", "07:10")), cnn_fake(first), t="2026-11-09", prev_day="2026-11-06")
    before = (old.raw_dir / "cnn" / "fear_greed.csv").read_bytes()
    clock = Clock(at("2026-11-10", "07:10"))
    http = cnn_fake({NEXT: resp})
    run = cnn_run(tmp_path, cfg, clock, http)
    assert run.manifest["cnn"]["status"] == "failed" and not run.stale
    assert (run.raw_dir / "cnn" / "fear_greed.csv").read_bytes() == before
    assert len(http.calls) == 1 and clock.sleeps == []   # 不重試（審查 2026-11-09）
    assert run.manifest["cnn"]["rows"] == 1 and run.manifest["cnn"]["has_prev_day"] is None


def test_fear_greed_after_the_deadline_or_switched_off(tmp_path, cfg):
    http = cnn_fake({FULL["2026-11-10"]: FakeResp(200, cnn_body([("2026-11-06", "00:00", 23.75)]))})
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "08:31")), http)
    assert run.manifest["cnn"]["status"] == "skipped" and http.calls == []
    cfg["cnn"]["enabled"] = False
    run = cnn_run(tmp_path, cfg, Clock(at("2026-11-10", "07:10")), http)
    assert "cnn" not in run.manifest and http.calls == []


# ---------------------------------------------------------------- 整個爬蟲


def test_crawl_runs_both_steps_after_taifex(tmp_path, cfg):
    cfg["vixtwn"]["start_month"] = "2026-11"
    vix = vix_fake({"202611": [("2026-11-13", "40.00", "40.10"), ("2026-11-16", "41.00", "41.10"),
                               ("2026-11-17", "42.00", "42.10")]})
    cnn = cnn_fake({FULL["2026-11-17"]: FakeResp(200, cnn_body([("2026-11-13", "00:00", 30.0),
                                                                ("2026-11-16", "00:00", 31.0),
                                                                ("2026-11-17", "00:00", 31.0)]))})
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), vixtwn=vix, cnn=cnn)
    assert code == 0 and run.manifest["run"]["status"] == "ok"
    assert run.manifest["vixtwn"]["status"] == "ok" and run.manifest["vixtwn"]["has_prev_day"] is True
    assert run.manifest["cnn"]["status"] == "ok" and run.manifest["cnn"]["last_dates"] == ["2026-11-13", "2026-11-16"]
    assert list(run.manifest).index("taifex") < list(run.manifest).index("vixtwn") < list(run.manifest).index("cnn")


def test_crawl_return_code_ignores_both_steps_failing(tmp_path, cfg):
    cfg["vixtwn"]["start_month"] = "2026-11"
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")),
                      vixtwn=vix_fake({}, errors={"202611": FakeResp(503)}), cnn=cnn_fake({FULL["2026-11-17"]: FakeResp(418)}))
    assert code == 0 and run.manifest["run"]["status"] == "ok"
    assert run.manifest["vixtwn"]["status"] == run.manifest["cnn"]["status"] == "failed"
    assert "HTTP 503" in run.manifest["vixtwn"]["error"] and "HTTP 418" in run.manifest["cnn"]["error"]
    assert not (run.raw_dir / "taifex" / "vixtwn.csv").exists()   # i 的月份沒抓到：不留空的檔


def test_crawl_survives_errors_that_are_not_crawler_errors(tmp_path, cfg, monkeypatch):
    """兩步各有自己的 except Exception：寫檔時的 PermissionError 這類錯誤也不能讓爬蟲停下（審查 2026-11-09：
    改成只接 CrawlerError 時舊的測試全過）。"""
    real = crawler.write_atomic

    def picky(path, data):
        if path.name in ("vixtwn.csv", "fear_greed.csv"):
            raise PermissionError(13, "Permission denied")
        return real(path, data)

    monkeypatch.setattr(crawler, "write_atomic", picky)
    cfg["vixtwn"]["start_month"] = "2026-11"
    vix = vix_fake({"202611": [("2026-11-13", "40.00", "40.10"), ("2026-11-16", "41.00", "41.10")]})
    cnn = cnn_fake({FULL["2026-11-17"]: FakeResp(200, cnn_body([("2026-11-13", "00:00", 30.0),
                                                                ("2026-11-16", "00:00", 31.0)]))})
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), vixtwn=vix, cnn=cnn)
    assert code == 0 and run.manifest["run"]["status"] == "ok" and not run.stale
    assert run.manifest["vixtwn"]["status"] == run.manifest["cnn"]["status"] == "failed"
    assert run.manifest["vixtwn"]["error"] == run.manifest["cnn"]["error"] == "PermissionError"


def test_crawl_survives_a_folder_where_the_side_files_should_be(tmp_path, cfg):
    """檔案的位置是資料夾：舊版在 finally 裡讀 sha256 時丟 IsADirectoryError，整個爬蟲停下（審查 2026-11-09）。"""
    cfg["vixtwn"]["start_month"] = "2026-11"
    for name in ("taifex/vixtwn.csv", "cnn/fear_greed.csv"):
        (tmp_path / "raw" / name).mkdir(parents=True)
    code, run = crawl(tmp_path, cfg, Clock(at("2026-11-17", "07:10")), vixtwn=vix_fake({"202611": NOV}),
                      cnn=cnn_fake({FULL["2026-11-17"]: FakeResp(200, cnn_body([("2026-11-16", "00:00", 31.0)]))}))
    saved = json.loads((run.raw_dir / "manifest.json").read_text())
    assert code == 0 and saved["run"]["status"] == "ok"
    for key in ("vixtwn", "cnn"):
        assert saved[key]["status"] == "failed" and "讀不了" in saved[key]["error"] and "sha256" not in saved[key]
        assert saved[key]["old_file_unreadable"] is True and saved[key]["rows"] is None


# ---------------------------------------------------------------- 長表的 4 欄


def side_table(raw, cfg, t=None):
    return features.build_features(raw, cfg, t).groupby("date")[list(features.SIDE_COLUMNS)].first()


def test_vixtwn_uses_i_and_its_own_previous_day():
    days = weekdays(5)   # 2025-01-06（一）～01-10（五）
    t = "2025-01-13"
    raw = small_raw(days)
    raw["vixtwn"] = {days[0]: 20.0, days[1]: 22.0, days[3]: 25.0, days[4]: 30.0, t: 99.0}   # 01-08 沒有值
    table = side_table(raw, small_cfg(), t)
    level, ret = table["vixtwn_lag1"].tolist(), table["vixtwn_ret_lag1"].tolist()
    assert np.isnan(level[0]) and level[1:3] == [20.0, 22.0] and np.isnan(level[3]) and level[4:] == [25.0, 30.0]
    assert np.isnan(ret[1]) and ret[2] == pytest.approx(0.1) and np.isnan(ret[3])
    assert ret[4] == pytest.approx(3 / 22)   # 01-08 沒有值，前一天數 VIXTWN 自己的日子：01-07
    assert ret[5] == pytest.approx(0.2)      # t 那列用 i（01-10），t 自己的 99 用不到


US_DAYS = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-10", "2025-01-13"]


def fg_raw():
    """台股 2025-01-06（一）～01-13（一）。美股 01-09 休市（卡特國葬，台股有開）：道瓊那天只有一根佔位K棒，
    CNN 卻先建了一點（值是前一天的）。"""
    days = weekdays(6)
    raw = small_raw(days)
    raw["yfinance"]["dji"] = sorted([bar(d, 40000.0 + j, high=40100.0 + j) for j, d in enumerate(US_DAYS)]
                                    + [bar("2025-01-09", 40004.0, volume=0.0)], key=lambda r: r["date"])
    raw["fear_greed"] = {"2025-01-02": 5.0, "2025-01-03": 10.0, "2025-01-06": 20.0, "2025-01-07": 30.0,
                         "2025-01-08": 35.0, "2025-01-09": 99.0, "2025-01-10": 50.0, "2025-01-13": 60.0}
    cfg = small_cfg()
    cfg["cnn"]["start"] = "2025-01-01"
    return days, raw, cfg


def test_us_trading_days_skip_placeholder_bars():
    _, raw, _ = fg_raw()
    assert features.us_trading_days(raw["yfinance"]["dji"]) == US_DAYS


def test_fear_greed_second_last_us_day_before_each_row():
    """使用者 2026-11-09：CNN 最後一天的分數收盤後還會改，用 d 之前最後一個美股交易日的前一個美股交易日。
    美股日只看道瓊：CNN 在美國休市的 01-09 也有點，不能把它當成「最後一天」（審查 2026-11-09）。"""
    days, raw, cfg = fg_raw()
    table = side_table(raw, cfg)
    level = table["fear_greed_lag1"].tolist()
    chg = table["fear_greed_chg_lag1"].tolist()
    # 01-10 那列：d 之前最後一個美股日是 01-08（01-09 休市），所以用 01-07，不用 01-08
    assert level == [5.0, 10.0, 20.0, 30.0, 30.0, 35.0]
    assert np.isnan(chg[0]) and chg[1:] == [5.0, 10.0, 10.0, 10.0, 5.0]


def test_fear_greed_prev_day_rule_uses_us_date_i():
    days, raw, cfg = fg_raw()
    cfg["features"]["fear_greed"] = {"day": "prev_day", "us_calendar": "dji"}
    table = side_table(raw, cfg)
    level, chg = table["fear_greed_lag1"].tolist(), table["fear_greed_chg_lag1"].tolist()
    # i 是前一個台股交易日；01-10 那列的 i 是 01-09，美股休市，CNN 那點（99）不用
    assert np.isnan(level[0]) and level[1:4] == [20.0, 30.0, 35.0] and np.isnan(level[4]) and level[5] == 50.0
    assert chg[1:4] == [10.0, 10.0, 5.0] and np.isnan(chg[4]) and chg[5] == 15.0


def test_fear_greed_ignores_scores_before_cnn_start():
    days, raw, cfg = fg_raw()
    cfg["cnn"]["start"] = "2025-01-06"
    table = side_table(raw, cfg)
    assert table["fear_greed_lag1"].isna().tolist()[:2] == [True, True] and table["fear_greed_lag1"].iloc[2] == 20.0
    assert np.isnan(table["fear_greed_chg_lag1"].iloc[2])


def test_fear_greed_does_not_carry_old_scores_forward():
    """CNN 少了 01-06、01-08、01-10：選到的日子沒有分數就空白，不往前找；前一個美股日沒有分數，chg 也空白。"""
    days, raw, cfg = fg_raw()
    raw["fear_greed"] = {d: v for d, v in raw["fear_greed"].items() if d not in ("2025-01-06", "2025-01-08", "2025-01-10")}
    table = side_table(raw, cfg)
    level, chg = table["fear_greed_lag1"].tolist(), table["fear_greed_chg_lag1"].tolist()
    assert level[:2] == [5.0, 10.0] and np.isnan(level[2]) and level[3:5] == [30.0, 30.0] and np.isnan(level[5])
    assert chg[1] == 5.0 and np.isnan(chg[3]) and np.isnan(chg[4])   # 01-07 的前一個美股日 01-06 沒有分數


def test_fear_greed_is_blank_when_cnn_has_nothing_after_the_day_it_needs():
    """使用者 2026-11-09：那天早上 CNN 沒抓到時，檔裡最新的美股日就是 s，s 的值是前一次抓的、還沒定住，空白。
    01-13（一）那列 e 是 01-10、s 是 01-08；檔只到 01-08（01-10 早上之後沒抓到）。01-09 是美國假日先建的點，
    不在美股日曆裡，不能當成「檔裡有比 s 新的」。"""
    days, raw, cfg = fg_raw()
    raw["fear_greed"] = {d: v for d, v in raw["fear_greed"].items() if d <= "2025-01-09"}
    table = side_table(raw, cfg)
    level, chg = table["fear_greed_lag1"].tolist(), table["fear_greed_chg_lag1"].tolist()
    assert level[:5] == [5.0, 10.0, 20.0, 30.0, 30.0] and np.isnan(level[5]) and np.isnan(chg[5])
    # 01-10 那天的分數抓到了：01-13 那列照常用 01-08
    raw["fear_greed"]["2025-01-10"] = 50.0
    assert side_table(raw, cfg)["fear_greed_lag1"].tolist()[5] == 35.0


def test_fear_greed_prev_day_rule_with_a_stale_or_missing_dow_file_is_blank():
    """prev_day 規則：道瓊的檔比 i 舊或不見時，那幾列空白，不能讓 build_features 停下（審查 2026-11-09）。"""
    days, raw, cfg = fg_raw()
    cfg["features"]["fear_greed"] = {"day": "prev_day", "us_calendar": "dji"}
    stale = copy.deepcopy(raw)
    stale["yfinance"]["dji"] = [r for r in raw["yfinance"]["dji"] if r["date"] <= "2025-01-07"]
    table = side_table(stale, cfg)
    assert table["fear_greed_lag1"].tolist()[1:3] == [20.0, 30.0] and table["fear_greed_lag1"].iloc[3:].isna().all()
    del raw["yfinance"]["dji"]
    assert side_table(raw, cfg)[["fear_greed_lag1", "fear_greed_chg_lag1"]].isna().all().all()


def test_fear_greed_without_the_us_calendar_is_blank():
    days, raw, cfg = fg_raw()
    del raw["yfinance"]["dji"]
    assert side_table(raw, cfg)[["fear_greed_lag1", "fear_greed_chg_lag1"]].isna().all().all()


def test_real_config_us_calendar_is_the_dow():
    cfg = utils.load_config()
    assert cfg["yfinance"]["tickers"][cfg["features"]["fear_greed"]["us_calendar"]] == "^DJI"


def test_fear_greed_unknown_rule_stops():
    days, raw, cfg = fg_raw()
    cfg["features"]["fear_greed"] = {"day": "last"}
    with pytest.raises(features.FeatureError, match="fear_greed.day"):
        features.build_features(raw, cfg)


def test_side_files_feed_the_table_and_missing_ones_are_notes(tmp_path, monkeypatch):
    days = ["2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06"]
    cfg = fake_repo(tmp_path, monkeypatch, days)   # 兩個檔都寫了：vixtwn 20、21…，分數 40、41…
    cfg["cnn"]["start"] = "2025-01-01"
    cfg["yfinance"]["tickers"]["dji"] = "^DJI"     # 美股日曆
    write_csv(tmp_path / "data" / "raw" / "yfinance" / "dji.csv", crawler.YF_COLUMNS,
              [[d, "100", "101", "99", "100", "100", "5"] for d in days])
    raw = features.load_raw(cfg)
    assert raw["vixtwn"]["2025-11-04"] == 21.0 and raw["fear_greed"]["2025-11-05"] == 42.0
    assert not [n for n in raw["notes"] if "vixtwn" in n or "fear_greed" in n]
    row = side_table(raw, cfg, "2025-11-07").loc["2025-11-07"]
    assert row["vixtwn_lag1"] == 23.0 and row["fear_greed_lag1"] == 42.0 and row["fear_greed_chg_lag1"] == 1.0
    (tmp_path / "data" / "raw" / "taifex" / "vixtwn.csv").unlink()
    write_csv(tmp_path / "data" / "raw" / "cnn" / "fear_greed.csv", ("date", "score"), [["2025-11-03", "120"]])
    raw = features.load_raw(cfg)
    assert raw["warnings"] == [] and raw["vixtwn"] == {} and raw["fear_greed"] == {}
    assert any("沒有 taifex/vixtwn.csv" in n for n in raw["notes"])
    assert any("cnn/fear_greed.csv 讀不了" in n for n in raw["notes"])
    assert side_table(raw, cfg, "2025-11-07").isna().all().all()


def test_load_raw_reads_the_side_files_from_side_dir(tmp_path, monkeypatch):
    """檢查試跑的結果時用 side_dir 指到別的資料夾；不能偷偷讀 data/raw（審查 2026-11-09）。"""
    cfg = fake_repo(tmp_path, monkeypatch, ["2025-11-03", "2025-11-04"])
    other = tmp_path / "other"
    write_csv(other / "taifex" / "vixtwn.csv", crawler.VIXTWN_COLUMNS, [["2025-11-04", "77.00", "77.10"]])
    write_csv(other / "cnn" / "fear_greed.csv", crawler.FEAR_GREED_COLUMNS, [["2025-11-04", "12.5"]])
    raw = features.load_raw(cfg, side_dir=other)
    assert raw["vixtwn"] == {"2025-11-04": 77.0} and raw["fear_greed"] == {"2025-11-04": 12.5}


def test_main_warns_when_the_t_row_side_columns_are_blank(tmp_path, monkeypatch):
    """爬蟲看不出特徵要用哪一天，t 那列空白時 features 寫警告（審查 2026-11-09）。"""
    days = ["2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    cfg["cnn"]["start"] = "2025-01-01"
    cfg["yfinance"]["tickers"]["dji"] = "^DJI"
    write_csv(tmp_path / "data" / "raw" / "yfinance" / "dji.csv", crawler.YF_COLUMNS,
              [[d, "100", "101", "99", "100", "100", "5"] for d in days])
    log = tmp_path / "data" / "submission" / "run_2025-11-07.log"

    def warned():
        return [line for line in log.read_text(encoding="utf-8").splitlines() if "t 那列" in line]

    assert features.main(["--date", "2025-11-07"]) == 0
    assert warned() == []
    write_csv(tmp_path / "data" / "raw" / "cnn" / "fear_greed.csv", crawler.FEAR_GREED_COLUMNS,
              [[d, str(40.0 + j)] for j, d in enumerate(days[:3])])   # 11-07 早上 CNN 沒抓到：s（11-05）是最新的
    assert features.main(["--date", "2025-11-07"]) == 0
    lines = warned()
    assert len(lines) == 1 and "WARNING" in lines[0] and "fear_greed_lag1" in lines[0] and "vixtwn_lag1" not in lines[0]


def test_side_columns_sit_after_the_exchange_columns():
    days = weekdays(3)
    columns = list(features.build_features(small_raw(days), small_cfg()).columns)
    assert columns[-6:] == [*features.SIDE_COLUMNS, *features.LABELS]
    assert columns.index("quote_limit_down_lag1") == columns.index("vixtwn_lag1") - 1
    assert not set(features.SIDE_COLUMNS) & set(features.model_columns(utils.load_config()))


def test_real_config_column_count_is_107():
    """真的 config 長表應有 107 欄，而且欄名不可重複。"""
    cfg = cfg_with(min_stocks_filled=2, closed_days=[])
    days = weekdays(3)
    raw = small_raw(days)
    columns = features.build_features(raw, cfg).columns
    assert len(columns) == 107 and len(set(columns)) == 107
    assert pd.Index(columns[-6:-2]).tolist() == list(features.SIDE_COLUMNS)
