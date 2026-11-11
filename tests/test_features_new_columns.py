"""使用者 2026-11-08 決定加的欄：證交所、櫃買的估值和委買賣、日韓開盤跳空、老師 S&P 500 和 Nasdaq 用 t 那列的版本，
以及 usd_twd_am 的舊K棒規則。定義見 memory/projects/features.md「使用者的決定」。全部離線。"""

import gzip
import json
import math

import numpy as np
import pandas as pd
import pytest

from src import crawler, features, utils
from tests.test_features import bar, fake_repo, hour, small_cfg, small_raw, weekdays, write_csv

SPECS = {(s.market, s.kind): s for s in crawler.EXCHANGE_SPECS}
NEW_COLUMNS = ["teacher_gspc_fresh_ret_lag1", "teacher_gspc_fresh_ret_lag2", "teacher_ixic_fresh_ret_lag1",
               "teacher_ixic_fresh_ret_lag2", "kospi_open_gap", "n225_open_gap", *features.VALUATION_COLUMNS,
               *features.QUOTE_COLUMNS, *features.SIDE_COLUMNS]


def nan_list(values):
    return ["nan" if isinstance(v, float) and math.isnan(v) else v for v in values]


# ---------------------------------------------------------------- 估值


@pytest.mark.parametrize("pe, pb, dy, expected", [
    ("12.50", "1.36", "9.09", [1 / 12.5, 0.0, math.log(1.36), 9.09 / 100]),
    ("-", "0.80", "0.00", ["nan", 1.0, math.log(0.8), 0.0]),          # 證交所虧損；殖利率 0 也算
    ("N/A", "2.17", "4.13", ["nan", 1.0, math.log(2.17), 4.13 / 100]),    # 櫃買虧損
    ("0.00", "0", "", ["nan", 0.0, "nan", "nan"]),                    # 本益比是數字但不 > 0；淨值比 0；殖利率空的
    ("", "-1", "x", ["nan", "nan", "nan", "nan"]),
])
def test_valuation_cells(pe, pb, dy, expected):
    assert nan_list(features.valuation_cells((pe, pb, dy))) == expected


# ---------------------------------------------------------------- 委買賣


BANDS = features.tick_bands(features.utils.load_config())


@pytest.mark.parametrize("bid, ask, ticks", [
    ("44.05", "44.10", 1), ("9.99", "10.05", 2), ("49.95", "50.10", 2), ("99.90", "100.50", 2),
    ("995.00", "1005.00", 6), ("1000.00", "1010.00", 2), ("12.00", "12.50", 10), ("9.50", "9.51", 1),
])
def test_spread_ticks_cross_price_bands(bid, ask, ticks):
    """台股升降單位：未滿 10 元 0.01、10～50 元 0.05、50～100 元 0.1、100～500 元 0.5、500～1000 元 1、1000 元以上 5。"""
    out = features.quote_cells((bid, "3", ask, "1"), BANDS)
    assert out[0] == ticks
    assert out[1] == pytest.approx((float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2))
    assert out[2] == 0.5 and out[3:] == (0.0, 0.0)


@pytest.mark.parametrize("row, expected", [
    (("44.05", "712", "44.10", "3"), [1.0, (44.10 - 44.05) / ((44.10 + 44.05) / 2), (712 - 3) / 715, 0.0, 0.0]),
    (("50.00", "1200", "--", "0"), ["nan", "nan", 1.0, 1.0, 0.0]),      # 證交所漲停鎖住：沒有賣價
    (("--", "0", "36.90", "880"), ["nan", "nan", -1.0, 0.0, 1.0]),      # 證交所跌停鎖住：沒有買價
    (("0.00", "0", "12635.00", "15"), ["nan", "nan", -1.0, 0.0, 1.0]),  # 櫃買的「沒有揭示」是 0.00
    (("142.00", "", "142.50", ""), [1.0, (142.50 - 142.00) / ((142.50 + 142.00) / 2), "nan", 0.0, 0.0]),   # 櫃買 2020 年上半年沒有買賣量
    (("--", "", "--", ""), ["nan", "nan", "nan", 0.0, 0.0]),            # 兩邊都沒有揭示
    (("10.05", "0", "10.05", "0"), ["nan", "nan", "nan", 0.0, 0.0]),    # 買價 ≥ 賣價；量都是 0
    (("10.07", "5", "10.10", "5"), ["nan", pytest.approx(0.03 / 10.085), 0.0, 0.0, 0.0]),   # 不在 0.05 的格子上
])
def test_quote_cells(row, expected):
    assert nan_list(features.quote_cells(row, BANDS)) == expected


def test_absurd_quote_price_does_not_raise():
    """'1e307' 這種有限但大得離譜的價格：檔數空白，不丟 OverflowError（交易所檔不能擋住每天的流程）。"""
    out = features.quote_cells(("10.00", "5", "1e307", "3"), BANDS)
    assert np.isnan(out[0]) and out[2] == 0.25
    assert features.tick_position(1e307, BANDS) is None


def test_exchange_values_survive_a_cell_that_raises(monkeypatch):
    """算格子時任何算術或字串錯誤：那張表的欄空白，其他表照算。"""
    def boom(row, bands):
        raise OverflowError("int too large")
    monkeypatch.setattr(features, "quote_cells", boom)
    exchange = {"valuation": {("2025-01-06", "A"): ("10", "2", "3")}, "quotes": {("2025-01-06", "A"): ("1", "1", "1", "1")}}
    out = features.exchange_values(["2025-01-06"], ["A"], exchange, small_cfg())
    assert out["val_ep_lag1"][0] == 0.1 and np.isnan(out["quote_imbalance_lag1"][0])


def test_tick_table_must_be_consistent():
    cfg = small_cfg()
    for table in ([[10, 0.01], [50, 0.05]], [[10, 0.03], [None, 5]], [[10, 0.01], [None, 5], [None, 1]],
                  [[50, 0.01], [10, 0.05], [None, 5]]):
        cfg["features"]["tick_table"] = table
        with pytest.raises(features.FeatureError, match="tick_table"):
            features.tick_bands(cfg)


# ---------------------------------------------------------------- 讀交易所的檔


def exchange_row(market, kind, day, code, **cells):
    spec = SPECS[market, kind]
    return [day, code] + [cells.get(c, "1.00") for c in spec.columns[2:]]


def write_exchange(root, market, kind, rows, header=None):
    spec = SPECS[market, kind]
    write_csv(root / spec.file, header or spec.columns, rows)


def test_load_exchange_reads_both_markets_and_notes_problems(tmp_path):
    write_exchange(tmp_path, "twse", "valuation", [
        exchange_row("twse", "valuation", "2024-01-25", "6446", 本益比="20.00"),
        exchange_row("twse", "valuation", "2024-01-25", "2330", 本益比="-"),
        exchange_row("twse", "valuation", "2024-01-25", "9999"),
        ["2024-01-25", "1101", "1"]])                                                        # 欄數不對：跳過
    write_exchange(tmp_path, "tpex", "valuation", [
        exchange_row("tpex", "valuation", "2024-01-24", "6446", 本益比="N/A"),
        exchange_row("tpex", "valuation", "2024-01-25", "9999")])                           # 兩邊都有：不用
    write_exchange(tmp_path, "twse", "quotes", [exchange_row("twse", "quotes", "2024-01-25", "2330")],
                   header=("date", "stock_id", "開盤價"))                                   # 表頭不對：整個檔不用
    out = {"notes": []}
    features.load_exchange(out, tmp_path)
    valuation = out["exchange"]["valuation"]
    assert valuation["2024-01-25", "6446"] == ("20.00", "1.00", "1.00")
    assert valuation["2024-01-24", "6446"] == ("N/A", "1.00", "1.00")
    assert valuation["2024-01-25", "2330"][0] == "-"
    assert valuation["2024-01-25", "9999"] is None
    assert ("2024-01-25", "1101") not in valuation
    assert out["exchange"]["quotes"] == {}
    notes = " ".join(out["notes"])
    assert "twse/valuation.csv 有 1 列壞掉" in notes and "出現兩次" in notes
    assert "twse/quotes.csv 讀不了或表頭不對" in notes and "沒有 tpex/quotes.csv" in notes


def test_load_exchange_survives_garbage(tmp_path):
    spec = SPECS["twse", "valuation"]
    (tmp_path / "twse").mkdir()
    (tmp_path / spec.file).write_bytes(b"\xff\xfe\x00garbage")
    out = {"notes": []}
    features.load_exchange(out, tmp_path)
    assert out["exchange"] == {"valuation": {}, "quotes": {}} and len(out["notes"]) == 4


def test_load_exchange_drops_suspended_days(tmp_path):
    """停牌那天交易所照樣有列：開高低收 '--'（櫃買 '----'）、成交股數 0，估值沿用前一天。兩張表都當成沒有列。
    例：1101 2025-08-13 停止交易、5347 2024-06-05（櫃買）。只有量 0 或只有價格是 '--' 的列照常留著。"""
    halt_twse = dict(開盤價="--", 最高價="--", 最低價="--", 收盤價="--", 成交股數="0",
                     最後揭示買價="--", 最後揭示買量="", 最後揭示賣價="--", 最後揭示賣量="")
    halt_tpex = dict(開盤="----", 最高="----", 最低="----", 收盤="----", 成交股數="0",
                     最後買價="0.00", 最後買量="0", 最後賣價="0.00", 最後賣量="0")
    write_exchange(tmp_path, "twse", "valuation", [exchange_row("twse", "valuation", d, "1101", 本益比="19.49")
                                                   for d in ("2025-08-12", "2025-08-13")])
    write_exchange(tmp_path, "twse", "quotes", [
        exchange_row("twse", "quotes", "2025-08-12", "1101"),
        exchange_row("twse", "quotes", "2025-08-13", "1101", **halt_twse),
        exchange_row("twse", "quotes", "2025-08-13", "2330", 成交股數="0"),                 # 量 0、有價格：留著
        exchange_row("twse", "quotes", "2025-08-13", "2317", 開盤價="--", 最高價="--", 最低價="--", 收盤價="--")])
    write_exchange(tmp_path, "tpex", "valuation", [exchange_row("tpex", "valuation", "2024-06-05", "5347")])
    write_exchange(tmp_path, "tpex", "quotes", [exchange_row("tpex", "quotes", "2024-06-05", "5347", **halt_tpex)])
    out = {"notes": []}
    features.load_exchange(out, tmp_path)
    valuation, quotes = out["exchange"]["valuation"], out["exchange"]["quotes"]
    for key in (("2025-08-13", "1101"), ("2024-06-05", "5347")):
        assert key not in valuation and key not in quotes
    assert ("2025-08-12", "1101") in valuation and ("2025-08-12", "1101") in quotes
    assert ("2025-08-13", "2330") in quotes and ("2025-08-13", "2317") in quotes
    assert out["notes"] == []


def test_suspended_day_blanks_all_nine_columns(tmp_path, monkeypatch):
    """i 那天停牌：t 那列 9 欄都空白（兩個旗標也是空白，不是 0），i−1 那天的值不會被拿來用。"""
    days = ["2025-11-03", "2025-11-04"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    raw_dir = tmp_path / "data" / "raw"
    write_exchange(raw_dir, "twse", "valuation", [exchange_row("twse", "valuation", d, "A", 本益比="20.00")
                                                  for d in days])
    write_exchange(raw_dir, "twse", "quotes", [
        exchange_row("twse", "quotes", days[0], "A"),
        exchange_row("twse", "quotes", days[1], "A", 開盤價="--", 最高價="--", 最低價="--", 收盤價="--",
                     成交股數="0", 最後揭示買價="--", 最後揭示買量="", 最後揭示賣價="--", 最後揭示賣量="")])
    table = features.build_features(features.load_raw(cfg), cfg, "2025-11-05").set_index(["date", "stock_id"])
    assert table.loc[("2025-11-05", "A"), list(features.VALUATION_COLUMNS + features.QUOTE_COLUMNS)].isna().all()
    assert table.loc[("2025-11-04", "A"), "val_ep_lag1"] == 0.05
    assert table.loc[("2025-11-04", "A"), "quote_limit_up_lag1"] == 0


def exchange_table(days, t=None, valuation=None, quotes=None):
    raw = small_raw(days)
    raw["exchange"] = {"valuation": valuation or {}, "quotes": quotes or {}}
    df = features.build_features(raw, small_cfg(), t)
    return df.set_index(["date", "stock_id"])


def test_exchange_columns_use_exactly_i():
    """t 那列用 i 那天的值；A 在 i 沒有列（停牌）就空白，不往前拿 i−1 的值。"""
    days = weekdays(4)
    t = "2025-01-10"
    valuation = {(d, c): (str(10 + j), "2.0", "3.0") for j, d in enumerate(days) for c in "AB"}
    quotes = {(d, c): ("20.00", "4", "20.05", "1") for d in days for c in "AB"}
    del valuation[days[-1], "A"], quotes[days[-1], "A"]
    table = exchange_table(days, t, valuation, quotes)
    b = table.loc[(t, "B")]
    assert b["val_ep_lag1"] == 1 / 13 and b["val_pe_loss_lag1"] == 0 and b["val_log_pb_lag1"] == math.log(2.0)
    assert b["val_dy_lag1"] == 0.03 and b["quote_spread_ticks_lag1"] == 1.0 and b["quote_imbalance_lag1"] == 0.6
    assert table.loc[(t, "A"), list(features.VALUATION_COLUMNS + features.QUOTE_COLUMNS)].isna().all()
    assert table.loc[(days[3], "A"), "val_ep_lag1"] == 1 / 12                       # days[3] 那列用 days[2]
    assert table.loc[(days[0], "A"), list(features.VALUATION_COLUMNS)].isna().all()   # 第一天沒有 i


def test_exchange_flags_are_written_as_integers():
    days = weekdays(3)
    quotes = {(d, "A"): ("50.00", "9", "--", "0") for d in days}
    table = exchange_table(days, quotes=quotes).reset_index()
    for c in features.FLAG_COLUMNS:
        assert str(table[c].dtype) == "Int64"
    a = table[table["stock_id"] == "A"].set_index("date")
    assert a.loc[days[1], "quote_limit_up_lag1"] == 1 and a.loc[days[1], "quote_limit_down_lag1"] == 0
    assert pd.isna(a.loc[days[1], "val_pe_loss_lag1"])                               # 沒有估值的列
    lines = gzip.decompress(features.to_csv_gz(table)).decode().splitlines()
    j = lines[0].split(",").index("quote_limit_up_lag1")
    assert {line.split(",")[j] for line in lines[1:]} == {"1", ""}            # 寫成 1，不是 1.0


# ---------------------------------------------------------------- 開盤跳空


def gap_cfg(days_rule=None, first_day=True):
    cfg = small_cfg()
    cfg["yfinance"]["tickers"].update(kospi="^KS11", n225="^N225")
    cfg["features"]["open_gap"] = {"series": ["kospi", "n225"], "late_open": {
        "kospi": {"first_day_of_year": first_day, "days": days_rule or []}}}
    return cfg


def gaps(rows, days, cfg, t=None, name="kospi"):
    raw = small_raw(days)
    raw["yfinance"][name] = rows
    df = features.build_features(raw, cfg, t)
    return df[df["stock_id"] == "A"].set_index("date")[f"{name}_open_gap"]


def test_open_gap_value_and_blanks():
    days = ["2024-12-30", "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    rows = [bar("2024-12-30", 100.0, open_=99.0, high=101, low=98),
            bar("2025-01-02", 102.0, open_=101.0, high=103, low=100),   # 每年第一個交易日：10:00 才開盤
            bar("2025-01-03", 104.0, open_=103.0, high=105, low=102),
            bar("2025-01-06", 104.0, volume=0.0),                         # 佔位K棒（開高低收相同、量 0）
            bar("2025-01-07", 110.0, open_=106.0, high=111, low=105)]     # 01-08 沒有K棒（休市）
    out = gaps(rows, days, gap_cfg())
    assert np.isnan(out["2024-12-30"])                                     # 序列的第一根，前面沒有
    assert np.isnan(out["2025-01-02"])
    assert out["2025-01-03"] == (103 - 102) / 102
    assert np.isnan(out["2025-01-06"])
    assert out["2025-01-07"] == (106 - 104) / 104                          # 前一根跳過佔位K棒
    assert np.isnan(out["2025-01-08"])
    cfg = gap_cfg(first_day=False)
    assert gaps(rows, days, cfg)["2025-01-02"] == (101 - 100) / 100
    assert np.isnan(gaps(rows, days, gap_cfg(days_rule=["2025-01-03"]))["2025-01-03"])   # 大學入學考試日


def test_open_gap_first_day_of_year_skips_placeholders():
    """Yahoo 在 1/2 補了佔位K棒時，每年第一個交易日是 1/3。"""
    days = ["2024-12-30", "2025-01-02", "2025-01-03", "2025-01-06"]
    rows = [bar("2024-12-30", 100.0, open_=99.0, high=101, low=98), bar("2025-01-02", 100.0, volume=None),
            bar("2025-01-03", 104.0, open_=103.0, high=105, low=102),
            bar("2025-01-06", 105.0, open_=104.5, high=106, low=104)]
    out = gaps(rows, days, gap_cfg())
    assert np.isnan(out["2025-01-03"]) and out["2025-01-06"] == (104.5 - 104) / 104


def test_open_gap_first_traded_bar_of_year_is_late():
    """Yahoo 在 1/1（韓國休市）補一根量 0、開高低收不同的K棒：它不算佔位K棒，但 1/2 才是真正的第一個交易日，
    10:00 才開盤，要空白。審查用合成資料找到的漏洞（2026-11-09）。"""
    days = ["2024-12-30", "2025-01-02", "2025-01-03"]
    rows = [bar("2024-12-30", 100.0, open_=99.0, high=101, low=98),
            bar("2025-01-01", 100.5, open_=100.0, high=101, low=99, volume=0.0),
            bar("2025-01-02", 102.0, open_=101.0, high=103, low=100),
            bar("2025-01-03", 104.0, open_=103.0, high=105, low=102)]
    out = gaps(rows, days, gap_cfg())
    assert np.isnan(out["2025-01-02"]) and out["2025-01-03"] == (103 - 102) / 102
    assert features.late_open_days(rows, {"first_day_of_year": True}) == {"2024-12-30", "2025-01-01", "2025-01-02"}
    # 整年都沒有成交量的序列：只算第一根
    flat = [dict(r, volume=None) for r in rows]
    assert features.late_open_days(flat, {"first_day_of_year": True}) == {"2024-12-30", "2025-01-01"}


def test_open_gap_is_blank_on_t_and_n225_has_no_late_rule():
    days = ["2025-01-02", "2025-01-03", "2025-01-06"]
    rows = [bar(d, 100.0 + j, open_=99.5 + j, high=101 + j, low=99 + j) for j, d in enumerate(days)]
    out = gaps(rows, days[:2], gap_cfg(), t=days[2], name="n225")
    assert np.isnan(out[days[0]]) and out[days[1]] == (100.5 - 100) / 100 and np.isnan(out[days[2]])
    assert gaps(rows, days, gap_cfg(), name="n225")[days[2]] == (101.5 - 101) / 101   # 隔天重算時補上


def test_config_late_open_days():
    cfg = utils.load_config()
    rule = cfg["features"]["open_gap"]["late_open"]["kospi"]
    assert rule["first_day_of_year"] is True
    assert rule["days"] == ["2020-12-03", "2021-11-18", "2022-11-17", "2023-11-16", "2024-11-14", "2025-11-13",
                            "2026-11-19"]
    assert cfg["features"]["open_gap"]["series"] == ["kospi", "n225"]
    assert "n225" not in cfg["features"]["open_gap"]["late_open"]


# ---------------------------------------------------------------- 老師 S&P 500、Nasdaq 用 t 那列


def test_fresh_teacher_columns_use_t_row():
    days = weekdays(5)
    t = "2025-01-13"
    raw = small_raw(days)
    for j, d in enumerate(days + [t]):   # ^VIX ^IXIC ^GSPC ^TWII ^KS11 TX_OI
        raw["global"][d] = [d, "20", str(1000 + 10 * j), str(500 + j), "1", "1", "1"]
    raw["global"][days[1]][3] = "-1"     # Training 的 -1 是數字，≤ 0 當空白
    raw["global"][days[2]][2] = ""
    del raw["global"][days[3]]           # Training 缺很多台股日的 global 列
    df = features.build_features(raw, small_cfg(), t)
    a = df[df["stock_id"] == "A"].set_index("date")
    assert a.loc[t, "teacher_gspc_fresh_ret_lag1"] == (505 - 504) / 504
    assert np.isnan(a.loc[t, "teacher_gspc_fresh_ret_lag2"])             # 往回第 2 個交易日沒有 global 列
    assert a.loc[t, "teacher_ixic_fresh_ret_lag1"] == (1050 - 1040) / 1040
    assert np.isnan(a.loc[days[2], "teacher_gspc_fresh_ret_lag1"])       # 分母是 -1
    assert a.loc[days[2], "teacher_gspc_fresh_ret_lag2"] == (502 - 500) / 500
    assert np.isnan(a.loc[days[2], "teacher_ixic_fresh_ret_lag1"])       # 分子是空的
    assert np.isnan(a.loc[days[4], "teacher_gspc_fresh_ret_lag1"])       # 分母那天沒有 global 列


# ---------------------------------------------------------------- usd_twd_am 的舊K棒規則


def test_stale_hourly_file_blanks_x_t():
    """爬蟲沒抓到新的 1h、沿用前一天的檔：最後一根在 i 的 06:00 結束。原本 x_t = x_i、lag1 是 0.0；現在 x_t 空白。"""
    days = ["2025-01-06", "2025-01-07", "2025-01-08"]
    t = "2025-01-09"
    hourly = [hour(f"{d}T05:00:00+08:00", 31.0 + j / 10) for j, d in enumerate(days)]
    raw = small_raw(days, hourly)
    cfg = small_cfg(hourly_from="2025-01-01")
    assert features.usd_twd_am_values(days + [t], raw, cfg) == [31.0, 31.1, 31.2, None]
    df = features.build_features(raw, cfg, t)
    row = df[(df["date"] == t) & (df["stock_id"] == "A")].iloc[0]
    assert np.isnan(row["usd_twd_am_ret_lag1"]) and np.isnan(row["usd_twd_am_ret_lag2"])
    fresh = sorted(hourly + [hour(f"{t}T04:00:00+08:00", 31.5)], key=lambda r: r["start"])
    assert features.usd_twd_am_values(days + [t], small_raw(days, fresh), cfg)[-1] == 31.5


def test_stale_rule_counts_trading_days_not_calendar_days():
    """週一的 x 取到週六 06:00 結束那根（週五紐約收盤），比週五 06:00 晚，照常有值；只有第一天只看 lookback。"""
    days = ["2025-01-10", "2025-01-13"]
    hourly = [hour("2025-01-10T05:00:00+08:00", 31.0), hour("2025-01-11T05:00:00+08:00", 31.4)]
    cfg = small_cfg(hourly_from="2025-01-01")
    assert features.usd_twd_am_values(days, small_raw(days, hourly), cfg) == [31.0, 31.4]
    assert features.usd_twd_am_values(["2025-01-13"], small_raw(days, hourly), cfg) == [31.4]


def test_stale_rule_leaves_daily_backfill_alone():
    """分界日之前用日K的 close，不看 1h，也不看舊K棒規則。"""
    days = ["2024-01-18", "2024-01-19", "2024-01-22"]
    raw = small_raw(days, [hour("2024-01-22T05:00:00+08:00", 31.0)])
    cfg = small_cfg(hourly_from="2024-01-22")
    assert features.usd_twd_am_values(days, raw, cfg) == [30, 31, 31.0]


# ---------------------------------------------------------------- 欄的順序、缺檔


def test_new_columns_sit_before_the_labels():
    days = weekdays(3)
    cfg = gap_cfg()
    raw = small_raw(days)
    raw["yfinance"]["kospi"] = []
    columns = list(features.build_features(raw, cfg).columns)
    assert columns[-len(NEW_COLUMNS) - 2:] == NEW_COLUMNS + list(features.LABELS)
    assert columns.index("kospi_ret_lag1") < columns.index("teacher_vix_ret_lag1")   # yfinance 序列照 tickers 排


def test_optional_inputs_are_notes_not_warnings(tmp_path, monkeypatch):
    """kospi.csv、證交所、櫃買的檔不見：那幾欄空白，記在 notes；warnings 還是空的，所以照樣可以 --rebuild。"""
    days = ["2025-10-30", "2025-10-31", "2025-11-03", "2025-11-04"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    cfg["yfinance"]["tickers"]["kospi"] = "^KS11"
    cfg["features"]["optional_inputs"] = ["kospi"]
    raw = features.load_raw(cfg)
    assert raw["warnings"] == [] and raw["yfinance"]["kospi"] == []
    assert len(raw["notes"]) == 5 and any("kospi.csv" in n for n in raw["notes"])   # kospi 和交易所的 4 個檔
    assert features.main(["--date", "2025-11-05", "--rebuild"]) == 0
    info = json.loads((tmp_path / "data" / "processed" / "manifest.json").read_text())
    assert info["warnings"] == [] and len(info["notes"]) == 5
    assert info["model_columns"] == features.model_columns(cfg)
    back = features.load_features(tmp_path / "data" / "processed")
    assert back[["kospi_ret_lag1", "kospi_open_gap", "val_ep_lag1", "quote_limit_up_lag1"]].isna().all().all()


def test_unreadable_optional_file_is_a_note_but_required_file_still_stops(tmp_path, monkeypatch):
    days = weekdays(3)
    cfg = fake_repo(tmp_path, monkeypatch, days)
    cfg["yfinance"]["tickers"]["kospi"] = "^KS11"
    cfg["features"]["optional_inputs"] = ["kospi"]
    yf = tmp_path / "data" / "raw" / "yfinance"
    write_csv(yf / "kospi.csv", ("date", "close"), [[days[0], "1"]])
    raw = features.load_raw(cfg)
    assert raw["warnings"] == [] and any("kospi.csv 讀不了" in n for n in raw["notes"])
    write_csv(yf / "usd_twd.csv", ("date", "close"), [[days[0], "1"]])
    with pytest.raises(features.FeatureError):
        features.load_raw(cfg)


def test_exchange_files_feed_the_table(tmp_path, monkeypatch):
    """從 data/raw/twse、tpex 讀到特徵表：上市的 A 和上櫃的 B 各從自己的交易所拿。"""
    days = ["2025-11-03", "2025-11-04"]
    cfg = fake_repo(tmp_path, monkeypatch, days)
    raw_dir = tmp_path / "data" / "raw"
    for kind in ("valuation", "quotes"):
        write_exchange(raw_dir, "twse", kind, [exchange_row("twse", kind, "2025-11-04", "A", 本益比="20.00",
                                                            最後揭示買價="--", 最後揭示買量="0")])
        write_exchange(raw_dir, "tpex", kind, [exchange_row("tpex", kind, "2025-11-04", "B", 本益比="N/A",
                                                            最後買價="10.00", 最後賣價="10.10")])
    raw = features.load_raw(cfg)
    assert raw["notes"] == [] and raw["warnings"] == []
    table = features.build_features(raw, cfg, "2025-11-05").set_index(["date", "stock_id"])
    a, b = table.loc[("2025-11-05", "A")], table.loc[("2025-11-05", "B")]
    assert a["val_ep_lag1"] == 0.05 and a["val_pe_loss_lag1"] == 0 and a["quote_limit_down_lag1"] == 1
    assert pd.isna(b["val_ep_lag1"]) and b["val_pe_loss_lag1"] == 1 and b["quote_spread_ticks_lag1"] == 2
