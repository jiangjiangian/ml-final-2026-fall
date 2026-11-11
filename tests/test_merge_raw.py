"""src/merge_raw.py：data/raw/ 合併成 data/merged/ 的個股表和市場表。用暫存資料夾裡的小假資料，不連網。"""

import csv
import gzip
import io
import json
import logging

import pandas as pd
import pytest

import run_daily_test as rdt
from src import crawler, merge_raw

CFG = {"yfinance": {"tickers": {"sox": "^SOX", "vix": "^VIX"}},
       "vixtwn": {"file": "taifex/vixtwn.csv"}, "cnn": {"file": "cnn/fear_greed.csv"}}
N = len(crawler.STOCK_COLUMNS) - 1   # 老師個股表除了 date 的欄數


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def stock_row(day, base, *, pending=False):
    """老師個股表的一列，每格都是不同的字串，方便確認沒有錯位。"""
    return [day] + (["-1"] * N if pending else [f"{base}.{j}" for j in range(N)])


def tx_row(day, expiry, session, close):
    row = [""] * len(crawler.TAIFEX_COLUMNS)
    row[0], row[1], row[2], row[6], row[17] = day, "TX", expiry, close, session
    row[3] = f"open-{expiry}-{session}"
    return row


@pytest.fixture
def raw(tmp_path):
    r = tmp_path / "raw"
    t, live = r / "teacher" / "training", r / "teacher" / "live"
    real_minus_one = stock_row("2026-08-31", 1101)
    real_minus_one[10] = "-1"                                       # Training 法人欄真的 -1，要保留
    write(t / "market" / "1101.csv", crawler.STOCK_COLUMNS, [stock_row("2026-08-28", 1100), real_minus_one])
    write(t / "market" / "2330.csv", crawler.STOCK_COLUMNS, [stock_row("2026-08-28", 2330)])   # 08-31 停牌
    write(live / "market" / "1101.csv", crawler.STOCK_COLUMNS,
          [stock_row("2026-08-31", 9999), stock_row("2026-09-01", 1102), stock_row("2026-09-02", 0, pending=True)])
    write(live / "market" / "2330.csv", crawler.STOCK_COLUMNS,
          [stock_row("2026-09-01", 2331), stock_row("2026-09-02", 0, pending=True)])
    (t / "info.json").write_text(json.dumps({"Top50@Y": ["2330"], "Top100@Y": ["2330", "1101"]}), encoding="utf-8")
    write(t / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS,
          [["2026-08-28", "1", "2", "3", "4", "5", "6"], ["2026-08-31", "11", "12", "13", "14", "15", "16"]])
    write(live / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS,
          [["2026-08-31", "x", "x", "x", "x", "x", "x"], ["2026-09-01", "21", "22", "23", "24", "25", "26"],
           ["2026-09-02", "-1", "-1", "-1", "-1", "-1", "-1"]])
    write(r / "yfinance" / "sox.csv", crawler.YF_COLUMNS,
          [["2026-08-28", "1", "2", "0.5", "1.5", "1.5", "0"], ["2026-08-31", "3", "4", "2", "3.5", "3.5", "0"]])
    write(r / "yfinance" / "vix.csv", crawler.YF_COLUMNS, [["2026-09-01", "20", "21", "19", "20.5", "20.5", "0"]])
    write(r / "taifex" / "tx.csv", crawler.TAIFEX_COLUMNS, [
        tx_row("2026-09-01", "202609", "一般", "-"),       # 近月沒成交：用下一個有成交的
        tx_row("2026-09-01", "202610", "一般", "24000"),
        tx_row("2026-09-01", "202610", "盤後", "23900"),
        tx_row("2026-09-01", "202609", "盤後", "23950"),   # 檔裡順序不一定照到期月
        tx_row("2026-09-02", "202610", "一般", "-"),
        tx_row("2026-09-02", "202609", "一般", "-"),       # 都沒成交：留到期月最早的
    ])
    write(r / "taifex" / "vixtwn.csv", crawler.VIXTWN_COLUMNS, [["2026-09-01", "30.1", "30.2"]])
    write(r / "cnn" / "fear_greed.csv", crawler.FEAR_GREED_COLUMNS, [["2026-08-30", "42.5"]])   # 美國日期
    specs = {s.key: s for s in crawler.EXCHANGE_SPECS}
    write(r / specs["twse_valuation"].file, specs["twse_valuation"].columns,
          [["2026-08-31", "1101", "40.0", "5.0", "-", "1.2", "115/2"],
           ["2026-08-31", "2330", "1000", "1.5", "20", "6.0", "115/2"]])   # 老師表沒有的停牌日
    write(r / specs["twse_quotes"].file, specs["twse_quotes"].columns,
          [["2026-08-31", "1101", "--", "--", "--", "--", "0", "--", "0", "--", "0"]])
    write(r / specs["tpex_valuation"].file, specs["tpex_valuation"].columns,
          [["2026-09-01", "3293", "N/A", "3.0", "2.0", ""]])
    write(r / specs["tpex_quotes"].file, specs["tpex_quotes"].columns,
          [["2026-09-01", "3293", "100", "101", "99", "100.5", "1000", "100.0", "", "100.5", ""]])
    return r


def read_gz(path):
    return pd.read_csv(io.BytesIO(gzip.decompress(path.read_bytes())), dtype=str, keep_default_na=False,
                       na_filter=False)


def test_stock_table_keeps_every_source_string(raw):
    df, boundary = merge_raw.build_stock(raw)
    assert boundary == "2026-08-31"
    teacher = list(crawler.STOCK_COLUMNS[1:])
    assert list(df.columns[:3]) == ["date", "stock_id", "is_top50"] and list(df.columns[3:3 + N]) == teacher
    assert list(df.columns[3 + N:6 + N]) == ["twse_valuation_收盤價", "twse_valuation_殖利率(%)", "twse_valuation_本益比"]
    rows = df.set_index(["date", "stock_id"])
    assert not rows.index.duplicated().any()
    assert list(rows.index) == sorted(rows.index)
    got = rows.loc[("2026-08-31", "1101"), teacher].tolist()
    expected = stock_row("2026-08-31", 1101)[1:]
    expected[9] = "-1"
    assert got == expected                                                  # Training 優先，Live 的 08-31 不用
    assert rows.loc[("2026-09-01", "2330"), teacher].tolist() == stock_row("2026-09-01", 2331)[1:]
    assert (rows.loc[("2026-09-02", "1101"), teacher] == "-1").all()       # Live 待定列原樣
    assert rows.loc[("2026-08-31", "1101"), "twse_valuation_本益比"] == "-"
    assert rows.loc[("2026-08-31", "1101"), "twse_quotes_開盤價"] == "--"
    assert rows.loc[("2026-08-31", "2330"), "twse_valuation_本益比"] == "20"
    assert rows.loc[("2026-08-31", "2330"), teacher].isna().all()          # 老師表跳過的日子，老師欄空白
    assert rows.loc[("2026-09-01", "3293"), "tpex_valuation_本益比"] == "N/A"
    assert rows.loc[("2026-09-01", "3293"), "tpex_quotes_最後買量"] == ""
    assert rows["is_top50"].to_dict() == {k: ("1" if k[1] == "2330" else "0") for k in rows.index}


def test_market_table_uses_each_source_date_and_the_near_month(raw):
    df, last = merge_raw.build_market(raw, CFG, "2026-08-31")
    rows = df.set_index("date")
    assert list(rows.index) == ["2026-08-28", "2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02"]
    assert rows.loc["2026-08-31", "teacher_^VIX"] == "11"                   # Live 的 08-31 不用
    assert rows.loc["2026-09-02", "teacher_TX_OI"] == "-1"
    assert rows.loc["2026-08-31", "sox_close"] == "3.5" and pd.isna(rows.loc["2026-09-01", "sox_close"])
    assert rows.loc["2026-09-01", "vix_open"] == "20"
    assert rows.loc["2026-09-01", "tx_day_到期月份(週別)"] == "202610"
    assert rows.loc["2026-09-01", "tx_day_開盤價"] == "open-202610-一般"
    assert rows.loc["2026-09-01", "tx_night_到期月份(週別)"] == "202609"
    assert rows.loc["2026-09-01", "tx_night_收盤價"] == "23950"
    assert rows.loc["2026-09-02", "tx_day_到期月份(週別)"] == "202609"
    assert "tx_day_交易時段" not in rows.columns and "tx_day_交易日期" not in rows.columns
    assert rows.loc["2026-09-01", ["vixtwn", "vixtwn_1min_avg"]].tolist() == ["30.1", "30.2"]
    assert rows.loc["2026-08-30", "fear_greed_score"] == "42.5"
    assert last["teacher_global"] == "2026-09-02" and last["tx_night"] == "2026-09-01" and last["fear_greed"] == "2026-08-30"


def test_merge_writes_files_that_read_back_the_same(raw, tmp_path):
    out = tmp_path / "merged"
    result = merge_raw.merge(CFG, raw, out)
    assert result["status"] == "written"
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "manifest.json", "market.csv.gz", "stock/2026-08.csv.gz", "stock/2026-09.csv.gz"]
    info = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert info["stock"]["months"] == ["2026-08", "2026-09"]
    stock = pd.concat([read_gz(out / "stock" / f"{m}.csv.gz") for m in info["stock"]["months"]], ignore_index=True)
    built, _ = merge_raw.build_stock(raw)
    pd.testing.assert_frame_equal(stock, built.fillna(""))
    assert list(stock.columns) == info["stock"]["columns"] and len(stock) == info["stock"]["rows"]
    market = read_gz(out / "market.csv.gz")
    assert list(market.columns) == info["market"]["columns"] and len(market) == info["market"]["rows"]
    assert "time" not in json.dumps(info)                                   # 沒有時間戳，沒變就不會有新 commit


def test_merge_skips_when_sources_are_the_same_and_rewrites_only_what_changed(raw, tmp_path):
    out = tmp_path / "merged"
    merge_raw.merge(CFG, raw, out)
    manifest = (out / "manifest.json").read_bytes()
    assert merge_raw.merge(CFG, raw, out) == {"status": "unchanged", "written": []}
    assert merge_raw.merge(CFG, raw, out, rebuild=True)["status"] == "same"
    assert (out / "manifest.json").read_bytes() == manifest
    write(raw / "teacher" / "live" / "market" / "2330.csv", crawler.STOCK_COLUMNS,
          [stock_row("2026-09-01", 2331), stock_row("2026-09-02", 2332)])   # Live 填好了
    result = merge_raw.merge(CFG, raw, out)
    assert result["written"] == ["stock/2026-09.csv.gz", "manifest.json"]
    (out / "stock" / "2026-08.csv.gz").unlink()                             # 檔不見了：來源沒變也重寫
    assert merge_raw.merge(CFG, raw, out)["written"] == ["stock/2026-08.csv.gz"]


def test_merge_removes_months_that_are_no_longer_in_the_table(raw, tmp_path):
    out = tmp_path / "merged"
    (out / "stock").mkdir(parents=True)
    (out / "stock" / "2019-12.csv.gz").write_bytes(b"old")
    result = merge_raw.merge(CFG, raw, out)
    assert "刪掉 stock/2019-12.csv.gz" in result["written"] and not (out / "stock" / "2019-12.csv.gz").exists()


@pytest.mark.parametrize("damage", ["missing", "header", "duplicate"])
def test_bad_sources_stop_before_writing_anything(raw, tmp_path, damage):
    target = raw / "yfinance" / "vix.csv"
    if damage == "missing":
        target.unlink()
    elif damage == "header":
        write(target, ("date", "open", "high", "low", "close", "volume"), [["2026-09-01", "1", "1", "1", "1", "0"]])
    else:
        write(target, crawler.YF_COLUMNS, [["2026-09-01", "1", "1", "1", "1", "1", "0"]] * 2)
    out = tmp_path / "merged"
    with pytest.raises(merge_raw.MergeError):
        merge_raw.merge(CFG, raw, out)
    assert not out.exists()


def test_live_stock_missing_from_training_is_an_error(raw, tmp_path):
    write(raw / "teacher" / "live" / "market" / "9999.csv", crawler.STOCK_COLUMNS, [stock_row("2026-09-01", 1)])
    with pytest.raises(merge_raw.MergeError, match="9999"):
        merge_raw.merge(CFG, raw, tmp_path / "merged")


def test_real_config_lists_every_yfinance_file():
    """config 的 tickers 都要有 data/raw/yfinance/<名稱>.csv（每天的合併靠它）；1 小時K棒不併。"""
    from src import utils
    cfg = utils.load_config()
    raw_dir = utils.ROOT / cfg["data"]["raw_dir"]
    assert cfg["data"]["merged_dir"] == "data/merged"
    names = {p.relative_to(raw_dir).as_posix() for p in merge_raw.source_files(raw_dir, cfg)}
    assert {f"yfinance/{n}.csv" for n in cfg["yfinance"]["tickers"]} <= names
    assert "yfinance/usd_twd_1h.csv" not in names


# ---------------------------------------------------------------- run_daily_test.py


def test_daily_commit_includes_merged_and_the_step_never_raises(monkeypatch, caplog):
    assert "data/merged" in rdt.DATA_PATHS and rdt.data_only(["data/merged/stock/2026-11.csv.gz"])
    from src import crawler as c, features, online_lr, site_api, submit
    for name, module in (("crawler", c), ("features", features), ("merge_raw", merge_raw), ("online_lr", online_lr),
                         ("site_api", site_api), ("submit", submit)):
        monkeypatch.setattr(rdt, name, module)
    calls = []

    def boom(argv):
        calls.append(argv)
        raise merge_raw.MergeError("yfinance/vix.csv 不見了")

    monkeypatch.setattr(merge_raw, "main", boom)
    log = logging.getLogger("test_merge_raw")
    with caplog.at_level(logging.WARNING, logger="test_merge_raw"):
        rdt.merged_step(log)
    assert calls == [[]]
    assert "合併原始資料沒做完" in caplog.text and "vix.csv" in caplog.text
