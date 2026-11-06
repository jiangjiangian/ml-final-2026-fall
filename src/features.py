"""特徵工程：data/raw/ → data/processed/features/YYYY-MM.csv.gz（一個月一檔）和 data/processed/manifest.json。

一列＝一檔股票（老師資料的 100 檔）× 一個日期。日期是全部台股交易日；給了預測日 t 時，只留早於 t 的
交易日，最後再加 t 那天。欄位：
    date, stock_id            鍵；stock_id 一律當字串（"2330"），不轉成數字
    is_top50                  1＝要預測的 50 檔（info.json 的 Top50@Y）
    <名稱>_ret_lag{k}        特徵，見下方；k 來自 config 的 features.lags
    label_y                   答案：t 當天 etl:adj_close > etl:adj_open 為 1；還不知道時空白
    label_intraday_return     答案：t 當天 etl:adj_close / etl:adj_open − 1（官方分數用）；還不知道時空白
預測日 t 那列的 label 一定空白。模型用哪些欄由 config 的 features.model_series 決定，見 model_columns()。

特徵 <名稱>_ret_lag{k}：
    i 是 t 之前最後一個台股交易日。t 那列 = (close_i − close_(i−k)) / close_(i−k)，i−k 數的是該序列自己的列。
    該序列在 i 那天沒有列就留空白，不往前找。兩個端點任一是空的或 ≤ 0 也留空白。名稱有四種：
    - stock：股票自己的 etl:adj_close。這組讓 50 檔每天的值不同。
    - teacher_vix 等：老師 global 表的欄（features.teacher_global），只用交易日的列。
    - yfinance 的 19 個序列（yfinance.tickers）：features.adj_close_kinds 的代號用 adj_close，其他用 close。
    - usd_twd_am：台北 d 日 06:00 前最後一根 TWD=X 1h 的 close，和美股收盤同步。這個序列的 lag 用 t 自己的值：
      (x_t − x_(t 往回第 k 個交易日)) / x_(t 往回第 k 個交易日)。x_t 在 t 開盤前就知道。
      小時資料開始之前用 usd_twd 那天日K的 close 補（使用者 2026-11-06 決定）。
    - tx_day、tx_night：台指期（使用者 2026-11-06 加，來源看 tx_futures.source）。用近月合約（到期月最早的），
      分子分母用同一個合約，換月那天不會多出一段假的漲跌。i−k 數的是台指期自己的日盤日子。
      tx_day：日盤（08:45～13:45）收盤，和其他序列一樣，要有 i 那天的日盤。
      tx_night：標 t 日的夜盤收盤（t 的前一個營業日 15:00 開始、隔天 05:00 收盤；平常就是 t 日 05:00，連假後是
      連假前最後一晚的夜盤），t 開盤前就知道。分母是日盤收盤：
      lag1 比 t 之前最後一個日盤（通常是 i），lag2 比再前一個（使用者 2026-11-06 決定「比日盤收盤」）。

台股交易日（使用者 2026-11-06 決定，和爬蟲共用 crawler.trading_days）：
    100 檔裡至少 crawler.min_stocks_filled 檔填好的日子：y 是 0 或 1，etl:adj_open、etl:adj_close > 0。
    還是 -1 的日子（10/23 颱風假、當天早上的 t）不算交易日，往回數 i−k 時也不算。
    單一檔股票那天沒填好（停牌）就當那檔沒有那一列。phase2Days 不會讓日曆多出日子。

-1 的處理：
    個股檔沒填好的列不用（見上面）。Live global 表 6 欄的 -1 是待定，當空白。
    Training 法人欄有真的 -1，但法人欄不進特徵，也不影響「填好了」的判斷。

yfinance 清理：照舊爬蟲的 R0～R5 依序做（規則、測試資料、使用者的決定見 memory/projects/features.md）。
    刪掉的列整列拿掉，不留空白的一列。每一筆都記在 manifest.json 的 cleaning。

輸出（使用者 2026-11-06：一個月一檔，只往後加，repo 不會越來越肥；都進 Git，組員用網址讀）：
    features/YYYY-MM.csv.gz   那個月的列。每天只重寫最後 features.rewrite_months 個月（月初要補上個月最後一天
                              的答案），內容沒變就不寫；過去的月份不動。特徵定義改了用 --rebuild 全部重寫。
    manifest.json             months（有哪些月份）、columns（全部欄位）、model_columns（模型用的欄）、last_date、
                              清理紀錄、警告。欄位和上次不一樣時一定要 --rebuild，不然新舊月份的欄位會對不起來。
    t 比已經存的最後一天早時（例如拿舊的 t 做研究）丟 FeatureError，不會把較新的月份蓋掉；要蓋掉加 --rebuild。

用法：
    python -m src.features                    t 用爬蟲 data/raw/manifest.json 的 target_date；沒有就不加 t 那列
    python -m src.features --date 2026-11-17  指定 t：交易日只留早於 t 的，加上 t 那列
    python -m src.features --rebuild          所有月份都重寫，刪掉多出來的月份
"""

import argparse
import csv
import gzip
import io
import json
import math
from bisect import bisect_left, bisect_right
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src import crawler, utils

TAIPEI = utils.TAIPEI
HOURLY_COLUMNS = crawler.HOURLY_COLUMNS   # start：K棒開始時間，ISO 格式帶時區
HOURLY_BAR = crawler.HOURLY_BAR
PRICE_KEYS = ("open", "high", "low", "close", "adj_close")
LABELS = ("label_y", "label_intraday_return")


class FeatureError(RuntimeError):
    """資料有問題，不能產生特徵。訊息是自己寫的短句。"""


# ---------------------------------------------------------------- 讀檔


def read_csv_rows(path: Path, columns: tuple) -> list:
    """讀 CSV，表頭要和 columns 一樣，回傳表頭以外的列（空行跳過）。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or tuple(rows[0]) != tuple(columns):
        raise FeatureError(f"{path.name} 的欄位和預期不同")
    body = [r for r in rows[1:] if r]
    if any(len(r) != len(columns) for r in body):
        raise FeatureError(f"{path.name} 有列的欄數不對")
    return body


def check_date(text: str, name: str) -> str:
    if not crawler.is_iso_date(text):
        raise FeatureError(f"{name} 有不是 YYYY-MM-DD 的日期")
    return text


def num(text: str, name: str):
    """空字串、NaN、inf 當空值；不是數字就丟 FeatureError。"""
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError:
        raise FeatureError(f"{name} 有不是數字的格子") from None
    return value if math.isfinite(value) else None


def load_teacher(teacher_dir: Path, live_dir: Path | None):
    """回傳 (stocks, global_rows, top50)。

    stocks：{代號: {日期: 資料列}}，Training 全部的列，接上 Live 在 Training 最後一天之後的列。
    global_rows：{日期: 資料列}，Live 的列裡 6 欄的 -1（待定）換成空字串。
    top50：要預測的 50 檔代號。
    """
    paths = sorted((teacher_dir / "market").glob("*.csv"))
    if not paths:
        raise FeatureError("老師 Training 沒有個股檔")
    stocks = {}
    for path in paths:
        stocks[path.stem] = {check_date(r[0], path.name): r for r in read_csv_rows(path, crawler.STOCK_COLUMNS)}
    boundary = max((d for rows in stocks.values() for d in rows), default=None)
    if boundary is None:
        raise FeatureError("老師 Training 個股檔沒有資料")
    global_rows = {check_date(r[0], "global_data.csv"): r
                   for r in read_csv_rows(teacher_dir / "global" / "global_data.csv", crawler.GLOBAL_COLUMNS)}
    if live_dir is not None and live_dir.exists():
        for path in sorted((live_dir / "market").glob("*.csv")):
            if path.stem not in stocks:
                raise FeatureError(f"Live 有 Training 沒有的代號 {path.stem}")
            for r in read_csv_rows(path, crawler.STOCK_COLUMNS):
                if check_date(r[0], path.name) > boundary:
                    stocks[path.stem][r[0]] = r
        live_global = live_dir / "global" / "global_data.csv"
        if live_global.exists():
            for r in read_csv_rows(live_global, crawler.GLOBAL_COLUMNS):
                if check_date(r[0], "Live global_data.csv") > boundary:
                    global_rows[r[0]] = [r[0]] + ["" if crawler.to_float(v) == -1 else v for v in r[1:]]
    info = json.loads((teacher_dir / "info.json").read_text(encoding="utf-8-sig"))
    top50 = {str(x) for x in info["Top50@Y"]}
    return stocks, global_rows, top50


def read_yfinance(path: Path) -> list:
    """爬蟲存的日K → [{date, open, high, low, close, adj_close, volume}]，空格是 None。"""
    out = []
    for r in read_csv_rows(path, crawler.YF_COLUMNS):
        row = {"date": check_date(r[0], path.name)}
        row.update({key: num(text, path.name) for key, text in zip(crawler.YF_COLUMNS[1:], r[1:])})
        out.append(row)
    return out


def read_hourly(path: Path) -> list:
    """爬蟲存的 1h → [{start, open, high, low, close, volume}]，start 是帶時區的 datetime。"""
    out = []
    for r in read_csv_rows(path, HOURLY_COLUMNS):
        try:
            start = datetime.fromisoformat(r[0])
        except ValueError:
            raise FeatureError(f"{path.name} 有看不懂的時間") from None
        if start.tzinfo is None:
            raise FeatureError(f"{path.name} 的時間沒有時區")
        row = {"start": start}
        row.update({key: num(text, path.name) for key, text in zip(HOURLY_COLUMNS[1:], r[1:])})
        out.append(row)
    return out


# ---------------------------------------------------------------- yfinance 清理 R0～R5


def is_flat(row) -> bool:
    return len({row["open"], row["high"], row["low"], row["close"]}) == 1


def is_bond_holiday(day: str) -> bool:
    """美國債市休市、股市照常的日子：哥倫布日（10 月第 2 個週一）、退伍軍人節（11/11；週六提前、週日順延）。"""
    d = date.fromisoformat(day)
    if d.month == 10:
        return d.weekday() == 0 and 8 <= d.day <= 14
    if d.month == 11:
        vet = date(d.year, 11, 11)
        if vet.weekday() == 5:
            vet -= timedelta(days=1)
        elif vet.weekday() == 6:
            vet += timedelta(days=1)
        return d == vet
    return False


def split_factor(prev, cur, max_factor, tolerance):
    """前後收盤比接近整數 n（2～max_factor）時回傳 n（分割）或 1/n（反向合併），否則 None。"""
    if prev is None or cur is None or prev <= 0 or cur <= 0:
        return None
    ratio = prev / cur
    for value, reverse in ((ratio, False), (1 / ratio, True)):
        n = round(value)
        if 2 <= n <= max_factor and abs(value - n) / n < tolerance:
            return 1.0 / n if reverse else float(n)
    return None


def rescale_dividends(rows, boundary, factor, cc, record):
    """R5：Yahoo 漏調分割時，分割前的股利調整只做了約 1/factor；把分界前每個除息幅度乘回 factor。"""
    ratios = [r["adj_close"] / r["close"] if r["adj_close"] and r["close"] else None for r in rows[:boundary]]
    if boundary < 2 or any(x is None or x <= 0 for x in ratios):
        return
    level = ratios[-1]
    for t in range(boundary - 2, -1, -1):
        step = 1 - ratios[t] / ratios[t + 1]
        if step > cc["dividend_step_min"]:
            fixed = min(step * factor, cc["dividend_max_fraction"])
            level *= 1 - fixed
            record("dividend", rows[t + 1]["date"], yahoo_fraction=step, rescaled_fraction=fixed)
        else:
            level *= ratios[t] / ratios[t + 1]
        rows[t]["adj_close"] = rows[t]["close"] * level


def clean_series(rows: list, name: str, ticker: str, cfg: dict):
    """回傳 (清理後的列, 紀錄)。rows 不會被改到。

    順序：R0 空值、close ≤ 0、重複日期 → R1 壞報價 → R2 債市假日（殖利率）→ R3 佔位K棒（股票、ETF）
    → R4 漏調的分割（台股）→ R5 分割前的股利。紀錄裡被刪的列是 Yahoo 原始單位（還沒做分割修正）。
    """
    cc = cfg["features"]["cleaning"]
    records = []

    def record(rule, day, **extra):
        records.append({"series": name, "rule": rule, "date": day, **extra})

    def dropped(rule, row):
        record(rule, row["date"], **{k: row[k] for k in (*PRICE_KEYS, "volume")})

    signed = ticker in cfg["yfinance"]["futures"] or ticker in cc["yields"]
    by_date = {}
    for row in rows:
        row = dict(row)
        if row["close"] is None:
            dropped("empty_close", row)
        elif not signed and row["close"] <= 0:
            dropped("nonpositive_close", row)
        else:
            if row["date"] in by_date:
                dropped("duplicate_date", by_date[row["date"]])   # 使用者 2026-11-06：重複的日期留最後一列
            by_date[row["date"]] = row
    kept = []
    for day in sorted(by_date):
        row = by_date[day]
        lo, hi, close = row["low"], row["high"], row["close"]
        tol = cc["bad_tick_tolerance"]
        if lo is not None and hi is not None and lo <= hi and (close < lo - tol * abs(lo) or close > hi + tol * abs(hi)):
            dropped("bad_tick", row)
        elif ticker in cc["yields"] and is_flat(row) and is_bond_holiday(day):
            dropped("bond_holiday", row)
        else:
            kept.append(row)
    if ticker not in cfg["features"]["adj_close_kinds"]:
        return kept, records

    rows, kept = kept, []
    window = cc["partial_bar_window"]
    for row in rows:
        if kept and is_flat(row):
            if not row["volume"] and row["close"] == kept[-1]["close"]:
                dropped("placeholder", row)
                continue
            recent = sorted(r["volume"] for r in kept[-window:] if r["volume"])
            median = recent[len(recent) // 2] if recent else None   # 上中位數，和舊爬蟲一樣
            if row["volume"] and median and row["volume"] < cc["partial_bar_volume_ratio"] * median:
                dropped("placeholder", row)
                continue
        kept.append(row)

    taiwan = ticker.upper().endswith((".TW", ".TWO"))
    for i in range(1, len(kept)):
        prev, cur = kept[i - 1], kept[i]
        factor = split_factor(prev["close"], cur["close"], cc["max_split_factor"], cc["split_tolerance"])
        if factor is None or split_factor(prev["adj_close"], cur["adj_close"],
                                          cc["max_split_factor"], cc["split_tolerance"]) != factor:
            continue
        if not taiwan:
            record("suspected_split_not_applied", cur["date"], factor=factor)   # 沒有漲跌幅限制，可能是真的大漲跌
            continue
        before = prev["close"]
        for row in kept[:i]:
            for key in PRICE_KEYS:
                if row[key] is not None:
                    row[key] = row[key] / factor
            if row["volume"] is not None:
                row["volume"] = row["volume"] * factor
        if factor > 1:
            record("split", cur["date"], factor=factor, previous_close_before_fix=before,
                   close_on_boundary=cur["close"])
            rescale_dividends(kept, i, factor, cc, record)
        else:
            # 使用者交給 Claude 決定（2026-11-06）：反向合併照樣修正價格和成交量，但不乘回股利
            record("reverse_split", cur["date"], factor=factor, previous_close_before_fix=before,
                   close_on_boundary=cur["close"])
    return kept, records


def clean_hourly(rows: list, cfg: dict):
    """1h 只做 R0（空值、≤ 0、重複時間留最後一列）和 R1（壞報價）。回傳 (依時間排序的列, 紀錄)。"""
    tol = cfg["features"]["cleaning"]["bad_tick_tolerance"]
    records, by_start = [], {}
    for row in rows:
        when = row["start"].isoformat()
        close, lo, hi = row["close"], row["low"], row["high"]
        if close is None or close <= 0:
            records.append({"series": "usd_twd_1h", "rule": "empty_or_nonpositive_close", "start": when})
        elif lo is not None and hi is not None and lo <= hi and (close < lo - tol * abs(lo) or close > hi + tol * abs(hi)):
            records.append({"series": "usd_twd_1h", "rule": "bad_tick", "start": when, "close": close})
        else:
            if row["start"] in by_start:
                records.append({"series": "usd_twd_1h", "rule": "duplicate_start", "start": when})
            by_start[row["start"]] = row
    return [by_start[k] for k in sorted(by_start)], records


def read_taifex(path: Path) -> list:
    """爬蟲存的期交所檔（crawler.TAIFEX_COLUMNS）→ [{date, expiry, session, close, low, high}]，'-' 是 None。"""
    out = []
    for r in read_csv_rows(path, crawler.TAIFEX_COLUMNS):
        if r[17] not in crawler.TAIFEX_SESSIONS:
            raise FeatureError(f"{path.name} 有看不懂的交易時段")
        row = {"date": check_date(r[0], path.name), "expiry": r[2], "session": crawler.TAIFEX_SESSIONS[r[17]]}
        for key, j in (("close", 6), ("low", 5), ("high", 4)):
            row[key] = None if r[j] in ("", "-") else num(r[j], path.name)
        out.append(row)
    return out


def clean_taifex(rows: list, cfg: dict):
    """期交所是官方資料，只擋明顯不對的：close ≤ 0、close 超出 [low, high]（R1 的容差）、同一天同一合約同一時段
    重複（留最後一列）。沒成交（close 是 '-'）不算紀錄，直接不用。回傳 (列, 紀錄)。"""
    tol = cfg["features"]["cleaning"]["bad_tick_tolerance"]
    records, by_key = [], {}
    for row in rows:
        close, lo, hi = row["close"], row["low"], row["high"]
        where = {"series": "tx", "date": row["date"], "expiry": row["expiry"], "session": row["session"]}
        if close is None:
            continue
        if close <= 0:
            records.append({**where, "rule": "nonpositive_close"})
        elif lo is not None and hi is not None and lo <= hi and (close < lo - tol * abs(lo) or close > hi + tol * abs(hi)):
            records.append({**where, "rule": "bad_tick", "close": close})
        else:
            key = (row["date"], row["expiry"], row["session"])
            if key in by_key:
                records.append({**where, "rule": "duplicate"})
            by_key[key] = row
    return [by_key[k] for k in sorted(by_key)], records


# ---------------------------------------------------------------- 讀 data/raw/


def load_raw(cfg: dict, *, teacher_dir=None, live_dir=None, yf_dir=None, tx_path=None) -> dict:
    """讀 data/raw/，yfinance 清理過。路徑沒給就用 config 的 data.raw_dir（測試會改成凍結資料）。

    回傳 {"stocks", "global", "top50", "yfinance": {名稱: 列}, "hourly": 列或 None,
          "tx": [{date, expiry, session, close}], "cleaning": [紀錄], "warnings": [訊息]}。
    yfinance 某個檔不存在時，那個序列整欄空白，記一筆警告，不中斷（每天的流程要全自動）。台指期也一樣。
    """
    raw_dir = utils.ROOT / cfg["data"]["raw_dir"]
    teacher_dir = Path(teacher_dir) if teacher_dir else raw_dir / "teacher" / "training"
    live_dir = Path(live_dir) if live_dir else raw_dir / "teacher" / "live"
    yf_dir = Path(yf_dir) if yf_dir else raw_dir / "yfinance"
    stocks, global_rows, top50 = load_teacher(teacher_dir, live_dir)
    out = {"stocks": stocks, "global": global_rows, "top50": top50, "yfinance": {}, "hourly": None, "tx": [],
           "cleaning": [], "warnings": []}
    load_tx(out, cfg, Path(tx_path) if tx_path else crawler.taifex_path(raw_dir, cfg), yf_dir)
    for name, ticker in cfg["yfinance"]["tickers"].items():
        path = yf_dir / f"{name}.csv"
        if not path.exists():
            out["warnings"].append(f"沒有 yfinance/{name}.csv，{name} 的特徵整欄空白")
            out["yfinance"][name] = []
            continue
        rows, records = clean_series(read_yfinance(path), name, ticker, cfg)
        out["yfinance"][name] = rows
        out["cleaning"].extend(records)
    hourly = yf_dir / f'{cfg["features"]["usd_twd_am"]["hourly"]}.csv'
    if hourly.exists():
        out["hourly"], records = clean_hourly(read_hourly(hourly), cfg)
        out["cleaning"].extend(records)
    else:
        out["warnings"].append(f"沒有 yfinance/{hourly.name}，usd_twd_am 從 "
                               f"{cfg['features']['usd_twd_am']['hourly_from']} 起空白")
    return out


def load_tx(out: dict, cfg: dict, tx_path: Path, yf_dir: Path):
    """台指期放進 out["tx"]：開關是 taifex 時讀期交所檔；是 yfinance 時讀 yfinance/tx_day.csv、tx_night.csv，
    當成只有一個合約（expiry 寫 yfinance）。"""
    tx = cfg["tx_futures"]
    if crawler.tx_source(cfg) == "taifex":
        if not tx_path.exists():
            out["warnings"].append(f"沒有 {tx_path.parent.name}/{tx_path.name}，tx_day、tx_night 的特徵整欄空白")
            return
        out["tx"], records = clean_taifex(read_taifex(tx_path), cfg)
        out["cleaning"].extend(records)
        return
    adj_kinds = cfg["features"]["adj_close_kinds"]
    for session, ticker in tx["yfinance"].items():
        name = crawler.TX_SERIES[session]
        if not ticker:
            continue
        path = yf_dir / f"{name}.csv"
        if not path.exists():
            out["warnings"].append(f"沒有 yfinance/{name}.csv，{name} 的特徵整欄空白")
            continue
        rows, records = clean_series(read_yfinance(path), name, ticker, cfg)
        out["cleaning"].extend(records)
        key = "adj_close" if ticker in adj_kinds else "close"
        out["tx"].extend({"date": r["date"], "expiry": "yfinance", "session": session, "close": r[key]} for r in rows)


# ---------------------------------------------------------------- lag


def k_returns(dates: list, prices: list, k: int) -> dict:
    """{日期 d: (price_d − price_(d 往回第 k 列)) / price_(d 往回第 k 列)}。兩個價格任一是空的或 ≤ 0 就沒有值。"""
    out = {}
    for j in range(k, len(dates)):
        base, cur = prices[j - k], prices[j]
        if base is not None and cur is not None and base > 0 and cur > 0:
            out[dates[j]] = (cur - base) / base
    return out


def series_name(column: str) -> str:
    """老師 global 表的欄名 → 序列名稱，例如 ^VIX → teacher_vix。"""
    return "teacher_" + column.lstrip("^").lower()


def market_sources(raw: dict, cfg: dict, calendar: list) -> dict:
    """{序列名稱: (日期, 價格)}：yfinance 19 個加老師 global 的欄，只留交易日以內的列。"""
    last = calendar[-1] if calendar else ""
    adj_kinds = cfg["features"]["adj_close_kinds"]
    out = {}
    for name, ticker in cfg["yfinance"]["tickers"].items():
        rows = [r for r in raw["yfinance"].get(name, []) if r["date"] <= last]
        key = "adj_close" if ticker in adj_kinds else "close"
        out[name] = ([r["date"] for r in rows], [r[key] for r in rows])   # 使用者 2026-11-06：adj_close 空就是空，不退回 close
    days = set(calendar)
    gdates = sorted(d for d in raw["global"] if d in days)
    for column in cfg["features"]["teacher_global"]:
        j = crawler.GLOBAL_COLUMNS.index(column)
        out[series_name(column)] = (gdates, [crawler.to_float(raw["global"][d][j]) for d in gdates])
    return out


def hourly_switch(hourly, cfg: dict) -> date:
    """從這天起只用小時資料：config 的 hourly_from 和 1h 檔第一個可用日較晚的那個。"""
    am = cfg["features"]["usd_twd_am"]
    floor = date.fromisoformat(am["hourly_from"])
    if not hourly:
        return floor
    first_end = (hourly[0]["start"] + HOURLY_BAR).astimezone(TAIPEI)
    at = dtime.fromisoformat(am["at"])
    first_day = first_end.date() if first_end.time() <= at else first_end.date() + timedelta(days=1)
    return max(floor, first_day)


def usd_twd_am_values(days: list, raw: dict, cfg: dict) -> list:
    """每個日期 d 的 usd_twd_am：分界日起取「結束時間 ≤ 台北 d 日 at」的最後一根 1h 的 close（最多往回
    lookback_days 天），取不到就空白；分界日之前用 usd_twd 那天日K的 close。"""
    am = cfg["features"]["usd_twd_am"]
    hourly = raw["hourly"] or []
    switch = hourly_switch(hourly, cfg)
    ends = [r["start"] + HOURLY_BAR for r in hourly]
    at = dtime.fromisoformat(am["at"])
    lookback = timedelta(days=am["lookback_days"])
    daily = {r["date"]: r["close"] for r in raw["yfinance"].get(am["daily"], [])}
    out = []
    for d in days:
        day = date.fromisoformat(d)
        if day < switch:
            out.append(daily.get(d))
            continue
        target = datetime.combine(day, at, TAIPEI)
        j = bisect_right(ends, target) - 1
        out.append(hourly[j]["close"] if j >= 0 and ends[j] > target - lookback else None)
    return out


def ratio(cur, base):
    return (cur - base) / base if cur is not None and base is not None and cur > 0 and base > 0 else np.nan


def tx_values(days: list, prev_day: list, last: str, tx_rows: list, lags: list) -> dict:
    """台指期的特徵欄 {欄名: [每個日期的值]}（定義見檔案開頭）。

    日盤只用日期 ≤ last（t 之前最後一個交易日）的列，所以 t 當天的日盤一定用不到；夜盤只用標同一天的那列。
    """
    day, night = {}, {}
    for r in tx_rows:
        if r["close"] is None:
            continue
        if r["session"] == "day" and r["date"] <= last:
            day.setdefault(r["expiry"], {})[r["date"]] = r["close"]
        elif r["session"] == "night":
            night.setdefault(r["date"], {})[r["expiry"]] = r["close"]
    tx_days = sorted({d for closes in day.values() for d in closes})
    near = {}
    for expiry in sorted(day, reverse=True):   # 最後蓋上去的是到期月最早的
        for d in day[expiry]:
            near[d] = expiry
    out = {f"tx_{kind}_ret_lag{k}": [] for kind in ("day", "night") for k in lags}
    for d, i in zip(days, prev_day):
        j = bisect_left(tx_days, i) if i in near else None
        n = night.get(d)
        before = bisect_left(tx_days, d)   # tx_days 裡早於 d 的有幾天
        for k in lags:
            if j is not None and j - k >= 0:
                c = near[i]
                out[f"tx_day_ret_lag{k}"].append(ratio(day[c][i], day[c].get(tx_days[j - k])))
            else:
                out[f"tx_day_ret_lag{k}"].append(np.nan)
            if n and before - k >= 0:
                c = min(n)
                out[f"tx_night_ret_lag{k}"].append(ratio(n[c], day.get(c, {}).get(tx_days[before - k])))
            else:
                out[f"tx_night_ret_lag{k}"].append(np.nan)
    return out


# ---------------------------------------------------------------- 特徵表


def build_features(raw: dict, cfg: dict, t: str | None = None) -> pd.DataFrame:
    """回傳 pandas DataFrame（欄位見檔案開頭）。t 是預測日：給了就只留早於 t 的交易日，最後加 t 那列。

    只能用 t 之前的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能進特徵；
    global 表的 ^TWII、^KS11、TX_OI 是當天收盤後的值，只會用到 i 和更早的列。
    """
    lags = cfg["features"]["lags"]
    stocks = raw["stocks"]
    calendar = crawler.trading_days(stocks, cfg["crawler"]["min_stocks_filled"], cfg["crawler"]["closed_days"])
    if t is not None:
        check_date(t, "--date")
        calendar = [d for d in calendar if d < t]
    days = calendar + ([t] if t is not None else [])
    if not days:
        raise FeatureError("沒有任何台股交易日")
    pos = {d: j for j, d in enumerate(calendar)}
    prev_day = [calendar[j - 1] if j >= 1 else None for j in (bisect_left(calendar, d) for d in days)]

    def at_prev_day(values: dict) -> np.ndarray:
        return np.array([values.get(i, np.nan) if i else np.nan for i in prev_day], dtype=float)

    codes = sorted(stocks)
    n_days, n_codes = len(days), len(codes)
    data = {"date": np.repeat(days, n_codes), "stock_id": np.tile(codes, n_days),
            "is_top50": np.tile([int(c in raw["top50"]) for c in codes], n_days)}

    # 股票自己：只用交易日上填好的列
    own = {}
    for c in codes:
        ds = [d for d in sorted(stocks[c]) if d in pos and crawler.row_filled(stocks[c][d])]
        prices = [crawler.to_float(stocks[c][d][crawler.COL_CLOSE]) for d in ds]
        own[c] = {k: at_prev_day(k_returns(ds, prices, k)) for k in lags}
    for k in lags:
        data[f"stock_ret_lag{k}"] = np.stack([own[c][k] for c in codes], axis=1).reshape(-1)

    for name, (ds, prices) in market_sources(raw, cfg, calendar).items():
        for k in lags:
            data[f"{name}_ret_lag{k}"] = np.repeat(at_prev_day(k_returns(ds, prices, k)), n_codes)

    x = usd_twd_am_values(days, raw, cfg)   # t 自己的值當 cur
    for k in lags:
        values = k_returns(days, x, k)
        data[f"usd_twd_am_ret_lag{k}"] = np.repeat([values.get(d, np.nan) for d in days], n_codes)

    for column, values in tx_values(days, prev_day, calendar[-1] if calendar else "", raw["tx"], lags).items():
        data[column] = np.repeat(np.array(values, dtype=float), n_codes)

    label_y, label_ret = [], []
    for d in days:
        for c in codes:
            row = stocks[c].get(d)
            if d == t or not crawler.row_filled(row):
                label_y.append(None)
                label_ret.append(np.nan)
            else:
                label_y.append(int(crawler.to_float(row[crawler.COL_Y])))
                label_ret.append(crawler.to_float(row[crawler.COL_CLOSE]) / crawler.to_float(row[crawler.COL_OPEN]) - 1)
    df = pd.DataFrame(data)
    df["label_y"] = pd.array(label_y, dtype="Int64")
    df["label_intraday_return"] = np.array(label_ret, dtype=float)
    unknown = set(model_columns(cfg)) - set(df.columns)
    if unknown:
        raise FeatureError(f"features.model_series 有不存在的序列：{sorted(unknown)}")
    return df


def model_columns(cfg: dict) -> list:
    """模型要用的特徵欄：features.model_series 每個序列的每個 lag。train.py、predict.py 只讀這些欄。"""
    return [f"{s}_ret_lag{k}" for s in cfg["features"]["model_series"] for k in cfg["features"]["lags"]]


def to_csv_gz(df: pd.DataFrame) -> bytes:
    """CSV（UTF-8、LF、浮點數用最短可還原的寫法）壓成 gzip，mtime 固定，同樣的內容得到同樣的位元組。"""
    text = df.to_csv(index=False, lineterminator="\n")
    return gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0)


def write_months(df: pd.DataFrame, out_dir: Path, rewrite: int, rebuild: bool = False, complete: bool = True) -> list:
    """照月份寫 out_dir/features/YYYY-MM.csv.gz，回傳真的寫了的月份。

    最後 rewrite 個月、還沒有檔的月份、rebuild 時的所有月份才寫；內容和舊檔一樣就不寫（mtime 固定，位元組會一樣）。
    rebuild 時刪掉 df 裡沒有的月份。complete 是 False（有 yfinance 檔不見，某些欄整欄空白）時只寫最後 rewrite
    個月：過去的月份寫了就不再動，不能讓空白欄凍在裡面。
    """
    if rebuild and not complete:
        raise FeatureError("有輸入檔不見，不能 --rebuild（過去的月份會凍住空白欄）")
    month_dir = out_dir / "features"
    months = df["date"].str[:7]
    all_months = sorted(months.unique())
    recent = set(all_months[-rewrite:])
    written = []
    for m in all_months:
        path = month_dir / f"{m}.csv.gz"
        if not (rebuild or m in recent or (complete and not path.exists())):
            continue
        payload = to_csv_gz(df[months == m])
        if not path.exists() or path.read_bytes() != payload:
            crawler.write_atomic(path, payload)
            written.append(m)
    if rebuild and month_dir.exists():
        for path in month_dir.glob("*.csv.gz"):
            if path.name[:7] not in all_months:
                path.unlink()
    return written


def load_features(processed_dir: Path | None = None) -> pd.DataFrame:
    """讀回 features/ 的所有月份（manifest.json 的 months），date、stock_id 當字串。train.py、predict.py 用這個。"""
    processed_dir = processed_dir or utils.ROOT / utils.load_config()["data"]["processed_dir"]
    info = json.loads((processed_dir / "manifest.json").read_text(encoding="utf-8"))
    frames = [pd.read_csv(processed_dir / "features" / f"{m}.csv.gz", dtype={"date": str, "stock_id": str},
                          float_precision="round_trip") for m in info["months"]]
    return pd.concat(frames, ignore_index=True)


def crawler_target_date(raw_dir: Path):
    """爬蟲上次跑的 t（data/raw/manifest.json 的 run.target_date）；沒有就回傳 None。"""
    try:
        t = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))["run"]["target_date"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return t if crawler.is_iso_date(t) else None


def main(argv=None) -> int:
    """load_raw → build_features → 照月份寫 data/processed/features/ 和 manifest.json。"""
    parser = argparse.ArgumentParser(description="data/raw/ → data/processed/features/YYYY-MM.csv.gz")
    parser.add_argument("--date", help="預測日 t（YYYY-MM-DD）；不給就用爬蟲上次的 t")
    parser.add_argument("--rebuild", action="store_true", help="所有月份都重寫（特徵定義改了的時候）")
    args = parser.parse_args(argv)
    if args.date and not crawler.is_iso_date(args.date):
        parser.error("--date 要是 YYYY-MM-DD")
    cfg = utils.load_config()
    t = args.date or crawler_target_date(utils.ROOT / cfg["data"]["raw_dir"])
    log = utils.get_logger("features", t or utils.taipei_now().date().isoformat())
    raw = load_raw(cfg)
    for message in raw["warnings"]:
        log.warning(message)
    df = build_features(raw, cfg, t)
    out_dir = utils.ROOT / cfg["data"]["processed_dir"]
    last = df["date"].iloc[-1]
    try:
        previous = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    previous = previous if isinstance(previous, dict) else {}
    stored = previous.get("last_date")
    if stored and last < stored and not args.rebuild:
        raise FeatureError(f"特徵表已經到 {stored}，這次只到 {last}；要用舊的 t 覆蓋請加 --rebuild")
    has_months = any((out_dir / "features").glob("*.csv.gz")) if (out_dir / "features").exists() else False
    if has_months and previous.get("columns") != list(df.columns) and not args.rebuild:
        raise FeatureError("特徵欄和上次不一樣，舊月份的欄位會對不起來；請加 --rebuild 全部重寫")
    complete = not raw["warnings"]
    written = write_months(df, out_dir, cfg["features"]["rewrite_months"], args.rebuild, complete)
    if not complete:
        log.warning("有輸入檔不見，只更新最後 %d 個月，沒有檔的舊月份先不建立", cfg["features"]["rewrite_months"])
    counts = {}
    for r in raw["cleaning"]:
        counts[r["rule"]] = counts.get(r["rule"], 0) + 1
    report = {"target_date": t, "last_date": last, "rows": len(df), "dates": int(df["date"].nunique()),
              "months": sorted(m for m in df["date"].str[:7].unique()
                               if (out_dir / "features" / f"{m}.csv.gz").exists()),
              "columns": list(df.columns), "model_columns": model_columns(cfg),
              "cleaning_counts": counts, "warnings": raw["warnings"], "cleaning": raw["cleaning"]}
    crawler.write_atomic(out_dir / "manifest.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    log.info("特徵表：%d 列、%d 天，最後一天 %s；寫了 %s；清理紀錄 %s", len(df), report["dates"], last,
             written or "沒有月份變動", counts)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
