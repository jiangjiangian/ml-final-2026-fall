"""日韓當天的開盤（使用者 2026-11-11）：crawler.open_today 從 Yahoo 一分鐘K棒拿當地今天第一根，features 用它算
t 那列的 open_gap，run_daily_test.py 的 open_today_step 把兩邊接起來。全部離線，Yahoo 用假的 fetch。"""

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import run_daily_test as rdt
from src import crawler, features, online_lr, site_api, submit, utils
from tests.test_features import bar, fake_repo, small_raw, write_csv
from tests.test_features_new_columns import gap_cfg

T = "2026-11-12"
OPEN = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)   # 韓國、日本 09:00，台北 08:00
GOOD = {"^KS11": [(OPEN, 5209.7099609375, 5239.13)], "^N225": [(OPEN, 60525.30078125, 60459.58)]}
LOG = logging.getLogger("test_open_today")


class Yahoo:
    """假的 fetch_first_bar。answers[代號] 是一串回應，剩最後一個時一直重複；回應是例外就丟出去。"""

    def __init__(self, answers):
        self.answers, self.calls = {k: list(v) for k, v in answers.items()}, []

    def __call__(self, session, ticker, timeout):
        self.calls.append(ticker)
        seq = self.answers[ticker]
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, BaseException):
            raise item
        return item


class Clock:
    def __init__(self, hhmm, day=T):
        self.now, self.sleeps = datetime.fromisoformat(f"{day}T{hhmm}:00+08:00"), []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


def run_step(raw_dir, yahoo, clock, cfg=None, t=T):
    return crawler.open_today(cfg or utils.load_config(), t, LOG, raw_dir=raw_dir, now=clock, sleep=clock.sleep,
                              session=object(), fetch=yahoo)


def stored(raw_dir, name):
    return crawler.read_points(raw_dir / "open_today" / f"{name}.csv", crawler.OPEN_TODAY_COLUMNS, crawler.open_today_ok)


# ---------------------------------------------------------------- 爬蟲那一步


def test_stores_the_first_bar_of_today_and_records_it(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"run": {"target_date": T}, "yfinance": {"status": "ok"}}))
    write_csv(tmp_path / "open_today" / "kospi.csv", crawler.OPEN_TODAY_COLUMNS,
              [["2026-11-11", "5209.71", "5239.13", "2026-11-11T08:25:07+08:00"]])
    yahoo, clock = Yahoo(GOOD), Clock("08:25")
    entry = run_step(tmp_path, yahoo, clock)
    assert entry["status"] == "ok" and entry["written"] == ["kospi", "n225"]
    assert yahoo.calls == ["^KS11", "^N225"] and clock.sleeps == []
    assert stored(tmp_path, "kospi") == {"2026-11-11": ("5209.71", "5239.13", "2026-11-11T08:25:07+08:00"),
                                         T: ("5209.7099609375", "5239.13", "2026-11-12T08:25:00+08:00")}
    assert stored(tmp_path, "n225") == {T: ("60525.30078125", "60459.58", "2026-11-12T08:25:00+08:00")}
    assert entry["series"]["kospi"] == {"status": "ok", "attempts": 1, "first_bar": "2026-11-12T09:00+09:00",
                                        "open": 5209.7099609375, "prev_close": 5239.13}
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["open_today"] == entry and manifest["yfinance"] == {"status": "ok"}
    # 已經有 t 那列：不送請求，也不再寫 manifest
    assert run_step(tmp_path, yahoo, Clock("08:40")) == {"status": "ok", "written": []}
    assert len(yahoo.calls) == 2


@pytest.mark.parametrize("hhmm, day, enabled, reason", [
    ("08:21", T, True, "還沒到 08:22"),
    ("07:10", T, True, "還沒到 08:22"),
    ("08:25", "2026-11-13", True, "t 不是台北今天"),
    ("08:25", T, False, "open_today.enabled 是 false"),
])
def test_skips_without_a_request(tmp_path, hhmm, day, enabled, reason):
    cfg = utils.load_config()
    cfg["open_today"]["enabled"] = enabled
    yahoo = Yahoo(GOOD)
    assert run_step(tmp_path, yahoo, Clock(hhmm, day), cfg) == {"status": "skipped", "reason": reason, "written": []}
    assert yahoo.calls == [] and not (tmp_path / "open_today").exists()


def test_runs_from_not_before_on(tmp_path):
    assert run_step(tmp_path, Yahoo(GOOD), Clock("08:22"))["written"] == ["kospi", "n225"]


def test_waits_for_todays_bar_then_gives_up(tmp_path):
    """Yahoo 還沒更新時給的是上一個交易日的K棒：隔 30 秒再抓，最多 4 次。連不上也算一次。"""
    yesterday = OPEN - timedelta(days=1)
    yahoo = Yahoo({"^KS11": [(yesterday, 5000.0, 4990.0), ConnectionError("dns"), (OPEN, 5209.71, 5239.13)],
                   "^N225": [(yesterday, 60000.0, 59000.0)]})
    clock = Clock("08:25")
    entry = run_step(tmp_path, yahoo, clock)
    assert entry["status"] == "partial" and entry["written"] == ["kospi"]
    assert clock.sleeps == [30, 30, 30]
    assert yahoo.calls == ["^KS11", "^N225", "^KS11", "^N225", "^KS11", "^N225", "^N225"]
    assert entry["series"]["kospi"] == {"status": "ok", "attempts": 3, "first_bar": "2026-11-12T09:00+09:00",
                                        "open": 5209.71, "prev_close": 5239.13}
    assert entry["series"]["n225"] == {"status": "no_bar", "attempts": 4, "first_bar": "2026-11-11T09:00+09:00"}
    assert stored(tmp_path, "kospi")[T][2] == "2026-11-12T08:26:00+08:00"
    assert not (tmp_path / "open_today" / "n225.csv").exists()


@pytest.mark.parametrize("answer, status", [
    ((OPEN + timedelta(hours=1), 5209.71, 5239.13), "not_open_bar"),   # 韓國 10:00 才開盤的日子
    ((OPEN + timedelta(minutes=1), 5209.71, 5239.13), "not_open_bar"),  # 少了 09:00 那根：09:01 的不是開盤價
    ((OPEN, 0.0, 5239.13), "bad_value"),
    ((OPEN, float("nan"), 5239.13), "bad_value"),
    ((OPEN, 5209.71, None), "bad_value"),
    ((OPEN, 5209.71, 0.0), "bad_value"),
    ((OPEN, 125.0, 100.0), "bad_value"),                                # 差 25%，超過 max_abs_gap
])
def test_a_bar_that_is_not_a_usable_open_is_not_stored(tmp_path, answer, status):
    yahoo, clock = Yahoo({"^KS11": [answer], "^N225": [answer]}), Clock("08:25")
    entry = run_step(tmp_path, yahoo, clock)
    assert entry["status"] == "none" and entry["written"] == []
    assert [info["status"] for info in entry["series"].values()] == [status, status]
    assert yahoo.calls == ["^KS11", "^N225"] and clock.sleeps == []   # 今天的K棒已經有了，再抓也一樣，不重試
    assert not (tmp_path / "open_today").exists()


def test_the_largest_allowed_gap_is_stored(tmp_path):
    entry = run_step(tmp_path, Yahoo({"^KS11": [(OPEN, 120.0, 100.0)], "^N225": [(OPEN, 80.0, 100.0)]}), Clock("08:25"))
    assert entry["written"] == ["kospi", "n225"]


def test_network_errors_never_raise(tmp_path):
    yahoo, clock = Yahoo({"^KS11": [ConnectionError("dns")], "^N225": [TimeoutError("slow")]}), Clock("08:25")
    entry = run_step(tmp_path, yahoo, clock)
    assert entry["status"] == "none" and entry["written"] == [] and clock.sleeps == [30, 30, 30]
    assert entry["series"] == {"kospi": {"status": "error", "error": "ConnectionError", "attempts": 4},
                               "n225": {"status": "error", "error": "TimeoutError", "attempts": 4}}


def test_a_crawler_error_fails_the_step_without_raising(tmp_path):
    """yf_ticker 發現 session 被換掉時丟 CrawlerError：整步停下，寫在 entry，不往外丟。"""
    (tmp_path / "manifest.json").write_text(json.dumps({"run": {"target_date": T}}))
    entry = run_step(tmp_path, Yahoo({"^KS11": [crawler.CrawlerError("session 被換掉了")], "^N225": GOOD["^N225"]}),
                     Clock("08:25"))
    assert entry["status"] == "failed" and entry["error"] == "session 被換掉了" and entry["written"] == []
    assert json.loads((tmp_path / "manifest.json").read_text())["open_today"]["status"] == "failed"


def test_keyboard_interrupt_is_not_swallowed(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        run_step(tmp_path, Yahoo({"^KS11": [KeyboardInterrupt()], "^N225": GOOD["^N225"]}), Clock("08:25"))


def test_a_bad_file_is_left_alone_and_the_other_series_still_runs(tmp_path):
    path = tmp_path / "open_today" / "kospi.csv"
    write_csv(path, ("date", "open"), [["2026-11-11", "1"]])
    before = path.read_bytes()
    yahoo = Yahoo(GOOD)
    entry = run_step(tmp_path, yahoo, Clock("08:25"))
    assert entry["status"] == "partial" and entry["written"] == ["n225"] and yahoo.calls == ["^N225"]
    assert entry["series"]["kospi"]["status"] == "bad_file" and path.read_bytes() == before


def test_manifest_of_another_day_or_no_manifest_is_fine(tmp_path):
    assert run_step(tmp_path, Yahoo(GOOD), Clock("08:25"))["status"] == "ok"   # 沒有 manifest.json
    other = tmp_path / "other"
    other.mkdir()
    (other / "manifest.json").write_text(json.dumps({"run": {"target_date": "2026-11-11"}}))
    assert run_step(other, Yahoo(GOOD), Clock("08:25"))["status"] == "ok"
    assert "open_today" not in json.loads((other / "manifest.json").read_text())


def test_fetch_first_bar_reads_the_first_minute_and_the_previous_close(monkeypatch):
    index = pd.DatetimeIndex(["2026-11-12 09:00", "2026-11-12 09:01"], tz="Asia/Seoul")
    frame = pd.DataFrame({"Open": [5209.71, 5223.25], "Close": [5224.53, 5231.70]}, index=index)

    class Ticker:
        history_metadata = {"chartPreviousClose": 5239.13, "previousClose": 5239.13}
        df, kwargs = frame, None

        def history(self, **kwargs):
            self.kwargs = kwargs
            return self.df

    tk = Ticker()
    monkeypatch.setattr(crawler, "yf_ticker", lambda session, ticker: tk)
    start, price, prev = crawler.fetch_first_bar(None, "^KS11", 30)
    assert start == OPEN and (price, prev) == (5209.71, 5239.13)
    assert tk.kwargs == {"period": "1d", "interval": "1m", "auto_adjust": False, "actions": False, "repair": False,
                         "timeout": 30}
    tk.history_metadata = {"chartPreviousClose": 5239.13}
    assert crawler.fetch_first_bar(None, "^KS11", 30)[2] == 5239.13
    tk.history_metadata = {"chartPreviousClose": 5239.13, "previousClose": 5100.0}   # 兩個不一樣：不猜
    assert crawler.fetch_first_bar(None, "^KS11", 30)[2] is None
    tk.history_metadata = None
    assert crawler.fetch_first_bar(None, "^KS11", 30)[2] is None
    tk.df = frame.iloc[0:0]
    with pytest.raises(crawler.EmptyResult):
        crawler.fetch_first_bar(None, "^KS11", 30)


def test_config_and_crontab_agree():
    cfg = utils.load_config()
    conf = cfg["open_today"]
    assert conf["enabled"] is True
    assert list(conf["series"]) == cfg["features"]["open_gap"]["series"] == ["kospi", "n225"]
    assert all(name in cfg["yfinance"]["tickers"] for name in conf["series"])
    assert conf["not_before"] >= "08:20"   # 韓國 09:00（台北 08:00）開盤，Yahoo 晚 20 分
    lines = [line.split() for line in (utils.ROOT / "deploy" / "crontab.txt").read_text(encoding="utf-8").splitlines()
             if "run_daily_test.py" in line and not line.startswith("#")]
    times = [f"{int(hour):02d}:{int(minute):02d}" for minute, hour, *_ in lines]
    assert times == ["07:10", "07:25", "07:40", "07:55", "08:05", "08:25"]
    assert conf["not_before"] <= times[-1] and all(x < conf["not_before"] for x in times[:-1])


# ---------------------------------------------------------------- features


DAYS = ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
BARS = [bar(d, 100.0 + j, open_=99.5 + j, high=101 + j, low=99 + j) for j, d in enumerate(DAYS)]


def gap_table(rows, days, cfg, t=None, same=None, name="kospi"):
    raw = small_raw(days)
    raw["yfinance"][name] = rows
    raw["open_today"] = {name: same or {}}
    return features.build_features(raw, cfg, t)


def gap_of(df, name="kospi"):
    return df[df["stock_id"] == "A"].set_index("date")[f"{name}_open_gap"]


def test_t_row_uses_the_morning_fetch():
    t = DAYS[3]
    blank = gap_of(gap_table(BARS[:3], DAYS[:3], gap_cfg(), t=t))
    assert np.isnan(blank[t]) and blank[DAYS[2]] == (101.5 - 101) / 101
    out = gap_of(gap_table(BARS[:3], DAYS[:3], gap_cfg(), t=t, same={t: (103.0, 102.5)}))
    assert out[t] == (103.0 - 102.5) / 102.5
    assert out[DAYS[2]] == blank[DAYS[2]] and out[DAYS[1]] == blank[DAYS[1]]
    # 日K裡就算有 t 那根也不用它
    assert np.isnan(gap_of(gap_table(BARS, DAYS[:3], gap_cfg(), t=t))[t])
    assert gap_of(gap_table(BARS, DAYS[:3], gap_cfg(), t=t, same={t: (103.0, 102.5)}))[t] == (103.0 - 102.5) / 102.5


def test_the_morning_value_stays_after_the_daily_bar_arrives():
    """那天早上抓到的值留著：之後日K來了也不換。沒抓到的日子用日K。日K缺那一天時，早上抓到的照樣有值。"""
    same = {DAYS[2]: (101.9, 101.0)}
    out = gap_of(gap_table(BARS, DAYS, gap_cfg(), same=same))
    assert out[DAYS[2]] == (101.9 - 101.0) / 101.0
    assert out[DAYS[1]] == (100.5 - 100) / 100 and out[DAYS[3]] == (102.5 - 102) / 102
    no_bar = [r for r in BARS if r["date"] != DAYS[2]]
    assert gap_of(gap_table(no_bar, DAYS, gap_cfg(), same=same))[DAYS[2]] == (101.9 - 101.0) / 101.0
    assert gap_of(gap_table([], DAYS, gap_cfg(), same=same))[DAYS[2]] == (101.9 - 101.0) / 101.0


def test_the_morning_value_is_blank_on_late_open_days_and_bad_prices():
    same = {DAYS[1]: (100.9, 100.0), DAYS[2]: (0.0, 101.0), DAYS[3]: (102.9, 0.0)}
    out = gap_of(gap_table(BARS, DAYS, gap_cfg(days_rule=[DAYS[1]]), same=same))
    assert np.isnan(out[DAYS[1]]) and np.isnan(out[DAYS[2]]) and np.isnan(out[DAYS[3]])


def test_a_morning_row_only_changes_its_own_cell():
    """早上抓的那一列只影響同一天、同一個序列的 open_gap；日期比 t 晚的列用不到。"""
    t = DAYS[3]
    base = gap_table(BARS[:3], DAYS[:3], gap_cfg(), t=t)
    later = gap_table(BARS[:3], DAYS[:3], gap_cfg(), t=t, same={"2025-01-10": (105.0, 104.0)})
    pd.testing.assert_frame_equal(base, later)
    changed = gap_table(BARS[:3], DAYS[:3], gap_cfg(), t=t, same={DAYS[2]: (101.9, 101.0)})
    other = [c for c in base.columns if c != "kospi_open_gap"]
    pd.testing.assert_frame_equal(base[other], changed[other])
    rows = base["date"] != DAYS[2]
    pd.testing.assert_series_equal(base.loc[rows, "kospi_open_gap"], changed.loc[rows, "kospi_open_gap"])
    assert (changed.loc[~rows, "kospi_open_gap"] == (101.9 - 101.0) / 101.0).all()


def test_open_gap_still_cannot_be_a_model_column():
    cfg = utils.load_config()
    cfg["features"]["model_series"] = [*cfg["features"]["model_series"], "kospi_open_gap"]
    with pytest.raises(features.FeatureError):
        features.model_columns(cfg)
    assert not [c for c in features.model_columns(utils.load_config()) if features.OPEN_GAP in c]


def test_load_raw_reads_open_today_and_notes_bad_files(tmp_path, monkeypatch):
    cfg = fake_repo(tmp_path, monkeypatch, ["2025-11-03", "2025-11-04"])
    raw = features.load_raw(cfg)
    assert raw["open_today"] == {} and not [n for n in raw["notes"] if "open_today" in n]   # 沒有檔是正常的
    folder = tmp_path / "data" / "raw" / "open_today"
    write_csv(folder / "kospi.csv", crawler.OPEN_TODAY_COLUMNS, [["2025-11-04", "101.5", "100", "2025-11-04T08:25:10+08:00"]])
    write_csv(folder / "n225.csv", ("date", "open"), [["2025-11-04", "1"]])
    raw = features.load_raw(cfg)
    assert raw["open_today"] == {"kospi": {"2025-11-04": (101.5, 100.0)}}
    notes = [n for n in raw["notes"] if "open_today" in n]
    assert len(notes) == 1 and "open_today/n225.csv 讀不了" in notes[0] and "n225_open_gap 只用日K算" in notes[0]
    other = tmp_path / "other"
    write_csv(other / "open_today" / "n225.csv", crawler.OPEN_TODAY_COLUMNS,
              [["2025-11-04", "50", "40", "2025-11-04T08:25:10+08:00"]])
    assert features.load_raw(cfg, side_dir=other)["open_today"] == {"n225": {"2025-11-04": (50.0, 40.0)}}


def test_main_fills_the_t_row_once_the_file_has_it(tmp_path, monkeypatch):
    fake_repo(tmp_path, monkeypatch, ["2025-11-03", "2025-11-04", "2025-11-05"])
    t = "2025-11-06"
    month = tmp_path / "data" / "processed" / "features" / "2025-11.csv.gz"

    def table():
        return pd.read_csv(month, dtype={"stock_id": str})

    assert features.main(["--date", t]) == 0
    before = table()
    assert before.loc[before["date"] == t, ["kospi_open_gap", "n225_open_gap"]].isna().all().all()
    write_csv(tmp_path / "data" / "raw" / "open_today" / "kospi.csv", crawler.OPEN_TODAY_COLUMNS,
              [[t, "101.5", "100", f"{t}T08:25:10+08:00"]])
    assert features.main(["--date", t]) == 0
    after = table()
    row = after[after["date"] == t]
    assert len(row) == 2 and np.allclose(row["kospi_open_gap"], 0.015) and row["n225_open_gap"].isna().all()
    other = [c for c in before.columns if c != "kospi_open_gap"]
    pd.testing.assert_frame_equal(before[other], after[other])
    rest = before["date"] != t
    pd.testing.assert_series_equal(before.loc[rest, "kospi_open_gap"], after.loc[rest, "kospi_open_gap"])


# ---------------------------------------------------------------- run_daily_test.py


@pytest.fixture
def daily(tmp_path, monkeypatch):
    """rdt 的 src 模組換成真的（平常 import_src 之後才有），open_today 和 features.main 換成記錄呼叫的假函式。"""
    for name, module in (("crawler", crawler), ("features", features), ("online_lr", online_lr),
                         ("site_api", site_api), ("submit", submit), ("utils", utils)):
        monkeypatch.setattr(rdt, name, module)
    monkeypatch.setattr(rdt, "ROOT", tmp_path)
    state = {"calls": [], "entry": {"status": "skipped", "written": []}, "last_date": T}
    manifest = tmp_path / "data" / "processed" / "manifest.json"
    manifest.parent.mkdir(parents=True)

    def open_today(cfg, t, log):
        state["calls"].append(("open", t))
        if isinstance(state["entry"], BaseException):
            raise state["entry"]
        return state["entry"]

    def main(argv):
        state["calls"].append(("features", argv))
        if state.get("features_error"):
            raise state["features_error"]
        return 0

    def step():
        manifest.write_text(json.dumps({"last_date": state["last_date"]}))
        state["calls"].clear()
        rdt.open_today_step(state.get("t", T), T, LOG)
        return state["calls"]

    monkeypatch.setattr(crawler, "open_today", open_today)
    monkeypatch.setattr(features, "main", main)
    return state, step


def test_step_rebuilds_the_table_only_when_something_new_was_stored(daily):
    state, step = daily
    assert step() == [("open", T)]                                        # 還沒到時間：沒有新的，不重寫
    state["entry"] = {"status": "partial", "written": ["kospi"]}
    assert step() == [("open", T), ("features", ["--date", T])]
    state["entry"] = {"status": "ok", "written": []}                      # 已經有了
    assert step() == [("open", T)]


def test_step_does_nothing_when_the_table_has_no_t_row_or_t_is_not_today(daily):
    state, step = daily
    state["entry"] = {"status": "ok", "written": ["kospi", "n225"]}
    state["last_date"] = "2026-11-11"                                     # 今天的特徵還沒做出來
    assert step() == []
    state["last_date"], state["t"] = T, "2026-11-11"                      # 補跑別天
    assert step() == []


def test_step_never_raises(daily, tmp_path):
    state, step = daily
    state["entry"] = RuntimeError("boom")
    assert step() == [("open", T)]
    state["entry"] = {"status": "ok", "written": ["kospi"]}
    state["features_error"] = features.FeatureError("特徵欄和上次不一樣")
    assert step() == [("open", T), ("features", ["--date", T])]
    (tmp_path / "data" / "processed" / "manifest.json").unlink()        # 沒有特徵表的 manifest
    state["calls"].clear()
    rdt.open_today_step(T, T, LOG)
    assert state["calls"] == []
