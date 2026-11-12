"""特徵工程：data/raw/ → data/processed/features/YYYY-MM.csv.gz（一個月一檔）和 data/processed/manifest.json。

一列＝一檔股票（老師資料的 100 檔）× 一個日期。日期是全部台股交易日；給了預測日 t 時，只留早於 t 的
交易日，最後再加 t 那天。欄位：
    date, stock_id            鍵；stock_id 一律當字串（"2330"），不轉成數字
    is_top50                  1＝要預測的 50 檔（info.json 的 Top50@Y）
    industry_original         交易所原始產業別
    industry_group            合併後的六大產業名稱
    industry_group_id         六大產業編號 0～5（靜態類別，不進 model_columns）
    <名稱>_ret_lag{k}        特徵，見下方；個股衍生特徵各有自己的 lag 設定
    teacher_<名稱>_fresh_ret_lag{k}、<名稱>_open_gap、val_*_lag1、quote_*_lag1、vixtwn_*、fear_greed_*
                              使用者 2026-11-08、11-09 加的欄，見下方「只進長表的欄」
    label_y                   答案：t 當天 etl:adj_close > etl:adj_open 為 1；還不知道時空白
    label_intraday_return     答案：t 當天 etl:adj_close / etl:adj_open − 1（官方分數用）；還不知道時空白
預測日 t 那列的 label 一定空白。模型用哪些欄由 config 的 features.model_series 決定，見 model_columns()。
欄的順序：鍵、產業、stock、yfinance（照 yfinance.tickers）、老師 global、usd_twd_am、台指期、只進長表的欄、答案。

特徵 <名稱>_ret_lag{k}：
    i 是 t 之前最後一個台股交易日。t 那列 = (close_i − close_(i−k)) / close_(i−k)，i−k 數的是該序列自己的列。
    stock_intraday_ret_lag{k} 是 t 之前第 k 個有效個股交易日的 (close − open) / open，不使用 t 當天收盤價。
    stock_gap_ret_lag{k} 是該交易日的 (open − 前次 close) / 前次 close；stock_log_shares_lag{k} 是 log(1 + 成交股數)。
    stock_open_lag1、stock_close_lag1、stock_high_lag1、stock_low_lag1 是前一交易日的還原 OHLC 原始價格。
    該序列在 i 那天沒有列就留空白，不往前找。兩個端點任一是空的或 ≤ 0 也留空白。名稱有四種：
    - stock：股票自己的 etl:adj_close。這組讓 50 檔每天的值不同。
    - teacher_vix 等：老師 global 表的欄（features.teacher_global），只用交易日的列。
    - yfinance 的序列（yfinance.tickers，2026-11-09 起 21 個）：features.adj_close_kinds 的代號用 adj_close，其他用 close。
    - usd_twd_am：台北 d 日 06:00 前最後一根 TWD=X 1h 的 close，和美股收盤同步。這個序列的 lag 用 t 自己的值：
      (x_t − x_(t 往回第 k 個交易日)) / x_(t 往回第 k 個交易日)。x_t 在 t 開盤前就知道。
      小時資料開始之前用 usd_twd 那天日K的 close 補（使用者 2026-11-06 決定）。
      選到的K棒要比前一個交易日的 06:00 晚結束，不然是沒更新的舊K棒（爬蟲沒抓到新的 1h），x_d 空白（使用者 2026-11-08）。
    - tx_day、tx_night：台指期（使用者 2026-11-06 加，來源看 tx_futures.source）。用近月合約（到期月最早的），
      分子分母用同一個合約，換月那天不會多出一段假的漲跌。i−k 數的是台指期自己的日盤日子。
      tx_day：日盤（08:45～13:45）收盤，和其他序列一樣，要有 i 那天的日盤。
      tx_night：標 t 日的夜盤收盤（t 的前一個營業日 15:00 開始、隔天 05:00 收盤；平常就是 t 日 05:00，連假後是
      連假前最後一晚的夜盤），t 開盤前就知道。分母是日盤收盤：
      lag1 比 t 之前最後一個日盤（通常是 i），lag2 比再前一個（使用者 2026-11-06 決定「比日盤收盤」）。

只進長表的欄（使用者 2026-11-08、11-09，都不進 model_columns），順序是 fresh、開盤跳空、交易所、VIXTWN、CNN：
    teacher_gspc_fresh_ret_lag{k}、teacher_ixic_fresh_ret_lag{k}（features.teacher_fresh）：
        x_d 是老師 global 第 d 列的 ^GSPC（^IXIC），也就是 d 開盤前最後一次美股收盤。和 usd_twd_am 一樣用 t 自己那列：
        (x_t − x_(t 往回第 k 個交易日)) / x_(t 往回第 k 個交易日)。沒有那列、-1、≤ 0 空白。原本的 teacher_gspc 不變。
    kospi_open_gap、n225_open_gap（features.open_gap）：d 那列 = d 當地開盤（台北 08:00）÷ 前一個當地交易日收盤 − 1。
        這是全表唯一用到 d 當天資料的欄，model_columns() 擋掉任何 open_gap 欄。兩個來源（open_gap_values）：
        data/raw/open_today/<序列>.csv 有 d 那列就用它（d 當天台北 08:25 的排程從 Yahoo 抓的，使用者 2026-11-11），
        沒有才用日K（d 那根的 open ÷ 前一根的 close，前一根跳過佔位K棒）。日K沒有 t 那根，所以 t 那列在 08:25
        以前空白，那天沒抓到就等之後的日K補上。沒有 d 那根（當地休市）、佔位K棒（開高低收相同、量 0 或空）、
        韓國 10:00 才開盤的日子（每年第一根和第一根有成交量的K棒、config 列的大學入學考試日）空白。
    證交所、櫃買中心（data/raw/twse/、data/raw/tpex/，欄位見 crawler.EXCHANGE_SPECS），t 那列用 i 那天的值：
        股票 i 那天在兩個交易所的檔都沒有列（停牌、還沒抓）就空白，不往前找；停牌那天交易所照樣有列
        （開高低收是 '--' 或 '----'、成交股數 0，估值沿用前一天），也當成沒有列。6446 2024-01-25 從櫃買轉上市，
        哪邊有就用哪邊。價格是交易所的原始價（沒還原），不和老師的還原價混用。
        val_ep_lag1         1 ÷ 本益比（> 0 時），其他空白
        val_pe_loss_lag1    本益比是虧損記號（證交所 '-'、櫃買 'N/A'）是 1，是數字是 0，沒有列空白
        val_log_pb_lag1     ln(股價淨值比)（> 0 時）
        val_dy_lag1         殖利率(%) ÷ 100（0 也算）
        quote_spread_ticks_lag1  最後揭示買價到賣價差幾檔（features.tick_table，跨價格區間一檔一檔數）
        quote_rel_spread_lag1    (賣價 − 買價) ÷ 兩者平均。這兩欄在買價或賣價沒有揭示、或買價 ≥ 賣價時空白
        quote_imbalance_lag1     (買量 − 賣量) ÷ (買量 + 賣量)。量是空的、不是數字、兩邊都是 0 時空白
        quote_limit_up_lag1      沒有賣價、有買價（漲停鎖住）是 1，其他 0，沒有列空白
        quote_limit_down_lag1    沒有買價、有賣價（跌停鎖住）是 1，其他 0，沒有列空白
    VIXTWN（data/raw/taifex/vixtwn.csv，使用者 2026-11-09）：期交所的免費檔從 2026-08-03 開始，i 更早的列空白。
        vixtwn_lag1         i 那天 13:45 的臺指選擇權波動率指數（i 收盤後才公布，所以只用 i）
        vixtwn_ret_lag1     和 VIXTWN 自己前一天比的漲跌幅，和 vix_ret_lag1 同算法
    CNN 恐懼貪婪（data/raw/cnn/fear_greed.csv，美國日期，2021-02-01 起），哪一天看 features.fear_greed.day，
    美股交易日看 features.fear_greed.us_calendar（道瓊有K棒的日子）：
        fear_greed_lag1     分數（0～100，越低越怕）
        fear_greed_chg_lag1 和前一個美股交易日的分數差幾分
        second_last（使用者 2026-11-09）用 t 之前最後一個美股交易日的前一個美股交易日：CNN 最後一天的點要到
        下一個美股交易日開盤後幾分鐘才定住（2026-11-10 量的）。通常比 vix 舊一天；台股休市期間美股開了 n 天時比 vix 新 n − 1 天（休一天時
        同一天，農曆年這種長假會新好幾天）。選到的那天是 CNN 檔裡最新的美股交易日時也空白（使用者 2026-11-09：
        前一天早上之後沒抓到新的，檔裡的分數還沒定住），之後抓到新的、重寫最後兩個月時補上。
        prev_day 用美國 i 那天。CNN 沒有選到的那天就空白，不往前找。
    這些欄的原始檔不見或讀不了時整欄空白，記在 manifest.json 的 notes，不算缺檔（不擋 --rebuild）。
    這時 --rebuild 會把空白寫進過去的月份，每天只重寫最後兩個月，所以檔案補齊後要再 --rebuild 一次。

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
                              清理紀錄、warnings（缺檔，會擋 --rebuild）、notes（只進長表的欄缺檔，不擋）。
                              欄位和上次不一樣時一定要 --rebuild，不然新舊月份的欄位會對不起來。
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
OPEN_GAP = "open_gap"                 # 當天開盤跳空欄（<序列>_open_gap）的記號；這種欄不能進 model_columns
FRESH_ALLOWED = ("^GSPC", "^IXIC")    # features.teacher_fresh 只能是這兩欄：第 d 列是 d 開盤前的美股收盤
PE_LOSS = ("-", "N/A")                # 本益比的虧損記號：證交所 '-'、櫃買 'N/A'
NO_QUOTE = ("--", "----")             # 沒有揭示的價格：證交所 '--'；櫃買寫 0.00，數字 0 也算沒有揭示
EXCHANGE_FIELDS = {                   # (交易所, 檔) → 要用的欄（crawler.EXCHANGE_SPECS 的存檔欄名）
    ("twse", "valuation"): ("本益比", "股價淨值比", "殖利率(%)"),
    ("tpex", "valuation"): ("本益比", "股價淨值比", "殖利率(%)"),
    ("twse", "quotes"): ("最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量"),
    ("tpex", "quotes"): ("最後買價", "最後買量", "最後賣價", "最後賣量"),
}
SUSPENSION_FIELDS = {                 # 收盤行情裡判斷停牌的欄：開高低收都是 NO_QUOTE、成交股數 0
    "twse": ("開盤價", "最高價", "最低價", "收盤價", "成交股數"),
    "tpex": ("開盤", "最高", "最低", "收盤", "成交股數"),
}
VALUATION_COLUMNS = ("val_ep_lag1", "val_pe_loss_lag1", "val_log_pb_lag1", "val_dy_lag1")
QUOTE_COLUMNS = ("quote_spread_ticks_lag1", "quote_rel_spread_lag1", "quote_imbalance_lag1",
                 "quote_limit_up_lag1", "quote_limit_down_lag1")
FLAG_COLUMNS = ("val_pe_loss_lag1", "quote_limit_up_lag1", "quote_limit_down_lag1")   # 0、1、空白，存成整數
SIDE_COLUMNS = ("vixtwn_lag1", "vixtwn_ret_lag1", "fear_greed_lag1", "fear_greed_chg_lag1")   # 使用者 2026-11-09
INDUSTRY_COLUMNS = ("industry_original", "industry_group", "industry_group_id")


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


def load_industry(path: Path) -> pd.DataFrame:
    """讀一列一檔的產業參考表，回傳 stock_id 加三個產業欄。"""
    try:
        table = pd.read_csv(path, encoding="utf-8-sig", dtype={"代號": str, "stock_id": str})
    except (OSError, ValueError, csv.Error) as e:
        raise FeatureError(f"產業參考表讀不了：{path}（{e}）") from None
    stock_column = "stock_id" if "stock_id" in table.columns else "代號"
    required = [stock_column, *INDUSTRY_COLUMNS]
    missing = [column for column in required if column not in table.columns]
    if missing:
        raise FeatureError(f"產業參考表缺少欄位：{missing}")

    table = table[required].rename(columns={stock_column: "stock_id"}).copy()
    table["stock_id"] = table["stock_id"].astype("string").str.strip()
    if table["stock_id"].isna().any() or table["stock_id"].eq("").any():
        raise FeatureError("產業參考表有空白股票代號")
    duplicates = table.loc[table["stock_id"].duplicated(keep=False), "stock_id"].unique().tolist()
    if duplicates:
        raise FeatureError(f"產業參考表有重複股票代號：{duplicates}")

    for column in ("industry_original", "industry_group"):
        table[column] = table[column].astype("string").str.strip()
        if table[column].isna().any() or table[column].eq("").any():
            raise FeatureError(f"產業參考表的 {column} 有空白")
    group_id = pd.to_numeric(table["industry_group_id"], errors="coerce")
    if group_id.isna().any() or not np.equal(group_id, np.floor(group_id)).all():
        raise FeatureError("產業參考表的 industry_group_id 必須是整數")
    table["industry_group_id"] = group_id.astype(np.int64)
    if not table["industry_group_id"].between(0, 5).all():
        raise FeatureError("產業參考表的 industry_group_id 必須介於 0～5")
    if (table.groupby("industry_group_id")["industry_group"].nunique() != 1).any() or \
            (table.groupby("industry_group")["industry_group_id"].nunique() != 1).any():
        raise FeatureError("industry_group 和 industry_group_id 必須一對一")
    return table


def add_industry_columns(df: pd.DataFrame, industry: pd.DataFrame) -> pd.DataFrame:
    """依 stock_id 把靜態產業欄插在 is_top50 後；不改列數、列順序或模型欄。"""
    stocks = set(df["stock_id"].astype(str))
    reference = set(industry["stock_id"].astype(str))
    missing, extra = sorted(stocks - reference), sorted(reference - stocks)
    if missing or extra:
        raise FeatureError(f"產業參考表和特徵股票不一致：缺少 {missing}；多出 {extra}")

    lookup = industry.set_index("stock_id")
    out = df.copy()
    for column in INDUSTRY_COLUMNS:
        out[column] = out["stock_id"].map(lookup[column])
    columns = list(df.columns)
    at = columns.index("is_top50") + 1
    columns[at:at] = INDUSTRY_COLUMNS
    return out[columns]


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


def load_raw(cfg: dict, *, teacher_dir=None, live_dir=None, yf_dir=None, tx_path=None, exchange_dir=None,
             side_dir=None) -> dict:
    """讀 data/raw/，yfinance 清理過。路徑沒給就用 config 的 data.raw_dir（測試會改成凍結資料）。

    回傳 {"stocks", "global", "top50", "yfinance": {名稱: 列}, "hourly": 列或 None,
          "tx": [{date, expiry, session, close}], "exchange": 見 load_exchange,
          "vixtwn": {日期: 值}, "fear_greed": {美國日期: 分數}, "open_today": 見 load_open_today,
          "cleaning": [紀錄], "warnings": [訊息], "notes": [訊息]}。
    yfinance 某個檔不存在時，那個序列整欄空白，記一筆警告，不中斷（每天的流程要全自動）。台指期也一樣。
    警告會讓 main() 當成缺檔（不能 --rebuild）。features.optional_inputs 的 yfinance 序列、證交所、櫃買、
    VIXTWN、CNN 的檔只進長表，不見或讀不了時記在 notes，不算缺檔。exchange_dir 是放 twse/、tpex/ 的資料夾，
    side_dir 是 vixtwn.file、cnn.file、open_today.dir 的起點，預設都是 data.raw_dir。
    """
    raw_dir = utils.ROOT / cfg["data"]["raw_dir"]
    teacher_dir = Path(teacher_dir) if teacher_dir else raw_dir / "teacher" / "training"
    live_dir = Path(live_dir) if live_dir else raw_dir / "teacher" / "live"
    yf_dir = Path(yf_dir) if yf_dir else raw_dir / "yfinance"
    stocks, global_rows, top50 = load_teacher(teacher_dir, live_dir)
    out = {"stocks": stocks, "global": global_rows, "top50": top50, "yfinance": {}, "hourly": None, "tx": [],
           "exchange": {}, "cleaning": [], "warnings": [], "notes": []}
    load_tx(out, cfg, Path(tx_path) if tx_path else crawler.taifex_path(raw_dir, cfg), yf_dir)
    optional = set(cfg["features"].get("optional_inputs") or ())
    for name, ticker in cfg["yfinance"]["tickers"].items():
        path = yf_dir / f"{name}.csv"
        out["yfinance"][name] = []
        if not path.exists():
            (out["notes"] if name in optional else out["warnings"]).append(
                f"沒有 yfinance/{name}.csv，{name} 的特徵整欄空白")
            continue
        try:
            rows, records = clean_series(read_yfinance(path), name, ticker, cfg)
        except (FeatureError, OSError, ValueError, csv.Error) as e:   # UnicodeDecodeError 也是 ValueError
            if name not in optional:
                raise
            out["notes"].append(f"yfinance/{name}.csv 讀不了（{e}），{name} 的特徵整欄空白")
            continue
        out["yfinance"][name] = rows
        out["cleaning"].extend(records)
    load_exchange(out, Path(exchange_dir) if exchange_dir else raw_dir)
    side_dir = Path(side_dir) if side_dir else raw_dir
    load_points(out, "vixtwn", side_dir / cfg["vixtwn"]["file"], crawler.VIXTWN_COLUMNS, crawler.vixtwn_cells_ok)
    load_points(out, "fear_greed", side_dir / cfg["cnn"]["file"], crawler.FEAR_GREED_COLUMNS, crawler.score_ok)
    load_open_today(out, cfg, side_dir)
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


def load_exchange(out: dict, raw_dir: Path):
    """證交所、櫃買的回補長表放進 out["exchange"]：{"valuation": {(日期, 代號): (本益比, 股價淨值比, 殖利率(%))},
    "quotes": {(日期, 代號): (買價, 買量, 賣價, 賣量)}}，格子是檔案裡的原樣字串。

    不會丟例外：檔案不見、讀不了、表頭少了要的欄，那個檔當作沒有；欄數不對、日期不對、沒有代號的列跳過。
    同一天同一檔出現兩次（兩個交易所都有，或同一個檔重複）那格是 None，算出來是空白。都記在 out["notes"]。
    停牌：交易所停牌那天照樣有列（收盤行情開高低收是 '--' 或 '----'、成交股數 0，估值沿用前一天），
    這種（日期, 代號）兩張表都拿掉，當成沒有列，9 欄空白（核准的定義「停牌空白，不往前找」）。不記 notes。
    """
    tables = {"valuation": {}, "quotes": {}}
    repeated = {"valuation": set(), "quotes": set()}
    suspended = set()
    for spec in crawler.EXCHANGE_SPECS:
        fields = EXCHANGE_FIELDS.get((spec.market, spec.kind))
        if fields is None:
            continue
        halt = SUSPENSION_FIELDS[spec.market] if spec.kind == "quotes" else ()
        path = raw_dir / spec.file
        if not path.exists():
            out["notes"].append(f"沒有 {spec.file}，{spec.market} 的股票 {spec.kind} 欄空白")
            continue
        try:
            with open(path, encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
            header = rows[0] if rows else []
            index = [header.index(name) for name in ("date", "stock_id", *fields)]
            halt_index = [header.index(name) for name in halt]
        except (OSError, ValueError, csv.Error):   # 讀不了、不是 UTF-8、表頭少了要的欄
            out["notes"].append(f"{spec.file} 讀不了或表頭不對，{spec.market} 的股票 {spec.kind} 欄空白")
            continue
        table, bad = tables[spec.kind], 0
        for r in rows[1:]:
            if not r:
                continue
            if len(r) != len(header) or not crawler.is_iso_date(r[index[0]]) or not r[index[1]]:
                bad += 1
                continue
            key = (r[index[0]], r[index[1]])
            if key in table:
                repeated[spec.kind].add(key)
            table[key] = tuple(r[j] for j in index[2:])
            if halt_index and crawler.to_float(r[halt_index[-1]]) == 0 \
                    and all(r[j].strip() in NO_QUOTE for j in halt_index[:-1]):
                suspended.add(key)
        if bad:
            out["notes"].append(f"{spec.file} 有 {bad} 列壞掉，跳過")
    for kind, keys in repeated.items():
        for key in keys:
            tables[kind][key] = None
        if keys:
            out["notes"].append(f"{kind} 有 {len(keys)} 個（日期, 代號）出現兩次，那幾格空白")
    for key in suspended:
        for table in tables.values():
            table.pop(key, None)
    out["exchange"] = tables


def load_points(out: dict, key: str, path: Path, columns: tuple, check):
    """VIXTWN、CNN 的原始檔放進 out[key]：{日期: 第一個數值}（VIXTWN 是 13:45 收盤、CNN 是分數）。
    不會丟例外：檔案不見、讀不了、表頭不對、有壞列，都當作沒有，記在 out["notes"]（只進長表的欄，不算缺檔）。"""
    out[key] = {}
    if not path.exists():
        out["notes"].append(f"沒有 {path.parent.name}/{path.name}，{key} 的欄空白")
        return
    try:
        rows = crawler.read_points(path, columns, check)
    except crawler.CrawlerError as e:
        out["notes"].append(f"{path.parent.name}/{path.name} 讀不了（{e}），{key} 的欄空白")
        return
    out[key] = {d: float(cells[0]) for d, cells in rows.items()}


def load_open_today(out: dict, cfg: dict, raw_dir: Path):
    """日韓當天早上抓的開盤（crawler.open_today 存的 open_today/<序列>.csv）放進 out["open_today"]：
    {序列: {日期: (open, 前一個當地交易日收盤)}}，只讀 features.open_gap.series 的序列。

    不會丟例外。沒有檔是正常的（還沒開始抓，或從來沒抓到），不記；讀不了、表頭不對、有壞列時當作沒有，
    記在 out["notes"]，那個序列只用日K算。"""
    out["open_today"] = {}
    folder = raw_dir / (cfg.get("open_today") or {}).get("dir", "open_today")
    for name in (cfg["features"].get("open_gap") or {}).get("series") or ():
        path = folder / f"{name}.csv"
        if not path.exists():
            continue
        try:
            rows = crawler.read_points(path, crawler.OPEN_TODAY_COLUMNS, crawler.open_today_ok)
        except crawler.CrawlerError as e:
            out["notes"].append(f"{folder.name}/{path.name} 讀不了（{e}），{name}_{OPEN_GAP} 只用日K算")
            continue
        out["open_today"][name] = {d: (float(cells[0]), float(cells[1])) for d, cells in rows.items()}


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
    """{序列名稱: (日期, 價格)}：yfinance.tickers 的序列加老師 global 的欄，只留交易日以內的列。"""
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
    """每個日期 d 的 usd_twd_am：分界日起取「結束時間 ≤ 台北 d 日 at」的最後一根 1h 的 close，取不到就空白；
    分界日之前用 usd_twd 那天日K的 close。

    那根要在 d 往回 lookback_days 天內結束，而且要晚於前一個日期（days 的前一個，也就是前一個交易日）的 at 結束。
    不然它就是前一天選過的那根：爬蟲那次沒抓到新的 1h、沿用舊檔，x_t 會等於 x_i、lag1 變成 0。這時空白
    （使用者 2026-11-08）。days 的第一天沒有前一天，只看 lookback。爬蟲的 has_value_t 用同一條規則。
    """
    am = cfg["features"]["usd_twd_am"]
    hourly = raw["hourly"] or []
    switch = hourly_switch(hourly, cfg)
    ends = [r["start"] + HOURLY_BAR for r in hourly]
    at = dtime.fromisoformat(am["at"])
    lookback = timedelta(days=am["lookback_days"])
    daily = {r["date"]: r["close"] for r in raw["yfinance"].get(am["daily"], [])}
    out = []
    for n, d in enumerate(days):
        day = date.fromisoformat(d)
        if day < switch:
            out.append(daily.get(d))
            continue
        target = datetime.combine(day, at, TAIPEI)
        floor = target - lookback
        if n > 0:
            floor = max(floor, datetime.combine(date.fromisoformat(days[n - 1]), at, TAIPEI))
        j = bisect_right(ends, target) - 1
        out.append(hourly[j]["close"] if j >= 0 and ends[j] > floor else None)
    return out


def teacher_fresh_values(days: list, global_rows: dict, column: str) -> list:
    """老師 global 第 d 列的 column（^GSPC 或 ^IXIC：d 開盤前最後一次美股收盤），沒有那列是 None。
    -1 和 ≤ 0 留給 k_returns 當空白（Live 的 -1 在 load_teacher 已經換成空字串）。"""
    if column not in FRESH_ALLOWED:
        raise FeatureError(f"features.teacher_fresh 只能是 {list(FRESH_ALLOWED)}：{column} 第 d 列是 d 當天收盤")
    j = crawler.GLOBAL_COLUMNS.index(column)
    return [crawler.to_float(global_rows[d][j]) if d in global_rows else None for d in days]


def is_placeholder(row) -> bool:
    """Yahoo 補的佔位K棒：開高低收相同，成交量是 0 或空的。"""
    return is_flat(row) and not row["volume"]


def late_open_days(rows: list, rule: dict) -> set:
    """10:00 才開盤的日子：config 列的日子，加上 first_day_of_year 時序列每年的第一根（rows 已經去掉佔位K棒）。

    每年的第一根和第一根成交量 > 0 的都算：Yahoo 在 1/1 休市補一根量 0、開高低收不同的K棒時（不算佔位K棒），
    真正的第一個交易日還是空白。兩根是同一天時就是一天。
    """
    out = set((rule or {}).get("days") or ())
    if (rule or {}).get("first_day_of_year"):
        first, traded = set(), set()
        for r in rows:
            year = r["date"][:4]
            if year not in first:
                first.add(year)
                out.add(r["date"])
            if r["volume"] and year not in traded:
                traded.add(year)
                out.add(r["date"])
    return out


def open_gap_values(days: list, rows: list, rule: dict | None, same_day: dict | None = None,
                    t: str | None = None) -> list:
    """每個日期 d 的開盤跳空：d 的開盤 ÷ 前一個當地交易日的收盤 − 1（寫成 (open − close) / close）。

    same_day 是 {日期: (open, 前一個當地交易日收盤)}：d 當天早上從 Yahoo 一分鐘K棒抓到的（crawler.open_today，
    使用者 2026-11-11）。有 d 就用它，之後日K來了也不換，表裡留的是那天早上看得到的值。
    same_day 沒有 d 時用日K（rows，清理過、依日期排序）：d 那根的 open ÷ 前一根的 close，前一根是序列自己的
    前一根，跳過佔位K棒。沒有 d 那根、d 那根是佔位K棒、前面沒有K棒、d 是 t（t 那根當天還沒走完，爬蟲也不留）：空白。
    兩個來源都一樣：d 是 late_open_days、任一價格空的或 ≤ 0 時空白。
    """
    real = [r for r in rows if not is_placeholder(r)]
    late = late_open_days(real, rule)
    pos = {r["date"]: j for j, r in enumerate(real)}
    same_day = same_day or {}
    out = []
    for d in days:
        j = pos.get(d)
        if d in late:
            out.append(np.nan)
        elif d in same_day:
            out.append(ratio(*same_day[d]))
        elif j is None or j == 0 or d == t:
            out.append(np.nan)
        else:
            out.append(ratio(real[j]["open"], real[j - 1]["close"]))
    return out


def tick_bands(cfg: dict) -> list:
    """features.tick_table → [(價格上限（分，不含；最後一段是 None）, 一檔幾分)]。每段的下限要是那段一檔的倍數。"""
    bands, low = [], 0
    for upper, tick in cfg["features"]["tick_table"]:
        high, step = (None if upper is None else round(upper * 100)), round(tick * 100)
        if low is None or step <= 0 or low % step or (high is not None and (high <= low or high % step)):
            raise FeatureError("features.tick_table 的價格區間或升降單位不對")
        bands.append((high, step))
        low = high
    if not bands or bands[-1][0] is not None:
        raise FeatureError("features.tick_table 最後一段要是 [null, 一檔多少]")
    return bands


def tick_position(price: float, bands: list):
    """從 0 數到 price 有幾檔（一檔一檔跨過價格區間）。price 不在升降單位的格子上、大到換算不了時回傳 None。"""
    if not math.isfinite(price * 100):   # 例如 '1e307'：round(inf) 會丟 OverflowError
        return None
    cents = round(price * 100)
    if abs(price * 100 - cents) > 1e-6:
        return None
    total, low = 0, 0
    for high, step in bands:
        if high is None or cents < high:
            return None if (cents - low) % step else total + (cents - low) // step
        total += (high - low) // step
        low = high
    return None


def quote_price(text: str):
    """最後揭示的價格：> 0 是價格，0.0 代表沒有揭示（'--'、'----'、0.00），看不懂是 None。"""
    if text.strip() in NO_QUOTE:
        return 0.0
    value = crawler.to_float(text)
    return value if value is not None and value >= 0 else None


def valuation_cells(row) -> tuple:
    """(本益比, 股價淨值比, 殖利率(%)) 的字串 → VALUATION_COLUMNS 的值。"""
    pe_text, pb_text, dy_text = row
    pe, pb, dy = crawler.to_float(pe_text), crawler.to_float(pb_text), crawler.to_float(dy_text)
    loss = 1.0 if pe_text.strip() in PE_LOSS else (0.0 if pe is not None else np.nan)
    return (1 / pe if pe is not None and pe > 0 else np.nan, loss,
            math.log(pb) if pb is not None and pb > 0 else np.nan,
            dy / 100 if dy is not None else np.nan)


def quote_cells(row, bands: list) -> tuple:
    """(買價, 買量, 賣價, 賣量) 的字串 → QUOTE_COLUMNS 的值。"""
    bid, ask = quote_price(row[0]), quote_price(row[2])
    has_bid, has_ask = bid is not None and bid > 0, ask is not None and ask > 0
    ticks = rel = np.nan
    if has_bid and has_ask and bid < ask:
        low, high = tick_position(bid, bands), tick_position(ask, bands)
        ticks = float(high - low) if low is not None and high is not None else np.nan
        rel = (ask - bid) / ((ask + bid) / 2)
    bid_volume, ask_volume = crawler.to_float(row[1]), crawler.to_float(row[3])
    imbalance = np.nan
    if bid_volume is not None and ask_volume is not None and bid_volume >= 0 and ask_volume >= 0 \
            and bid_volume + ask_volume > 0:
        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
    return (ticks, rel, imbalance, float(ask == 0.0 and has_bid), float(bid == 0.0 and has_ask))


def exchange_values(prev_day: list, codes: list, exchange: dict, cfg: dict) -> dict:
    """證交所、櫃買的欄 {欄名: 長度 len(prev_day) × len(codes) 的陣列}，順序和 build_features 的列一樣（日期在外層）。
    每列用 i（prev_day）那天、那檔的列；沒有就空白，不往前找。
    格子算不出來（看不懂的字串、算術溢位）時那張表的欄空白，不丟例外：交易所檔的內容不能擋住每天的流程。"""
    bands = tick_bands(cfg)
    valuation, quotes = exchange.get("valuation") or {}, exchange.get("quotes") or {}
    out = {c: np.full(len(prev_day) * len(codes), np.nan) for c in VALUATION_COLUMNS + QUOTE_COLUMNS}
    n = 0
    for i in prev_day:
        for code in codes:
            if i is not None:
                for table, columns, cells in ((valuation, VALUATION_COLUMNS, valuation_cells),
                                              (quotes, QUOTE_COLUMNS, lambda r: quote_cells(r, bands))):
                    row = table.get((i, code))
                    if row is None:
                        continue
                    try:
                        values = cells(row)
                    except (ArithmeticError, ValueError, TypeError, AttributeError):
                        continue
                    for c, value in zip(columns, values):
                        out[c][n] = value
            n += 1
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


def vixtwn_values(prev_day: list, values: dict) -> dict:
    """VIXTWN 的兩欄 {欄名: [每個日期的值]}：vixtwn_lag1 是 i 那天 13:45 的值，vixtwn_ret_lag1 是它和 VIXTWN
    自己前一天比的漲跌幅（和 vix_ret_lag1 同算法）。i 沒有值就空白，不往前找。VIXTWN 是 i 收盤後才公布，
    所以只用 i，不用 t。"""
    dates = sorted(values)
    level, ret = [], []
    for i in prev_day:
        v = values.get(i) if i else None
        level.append(np.nan if v is None else v)
        j = bisect_left(dates, i) if v is not None else 0
        ret.append(ratio(v, values[dates[j - 1]]) if j >= 1 else np.nan)
    return {"vixtwn_lag1": level, "vixtwn_ret_lag1": ret}


def us_trading_days(rows: list) -> list:
    """美股交易日：features.fear_greed.us_calendar 那個 yfinance 序列有K棒的日子，佔位K棒不算。
    道瓊 2021～2026 沒有一根假日K棒（2026-11-09 查過）；CNN 當天的點在美股開盤前就出現，美國假日可能也會建，所以不能用 CNN 自己的日期。"""
    return sorted(r["date"] for r in rows if not is_placeholder(r))


def fear_greed_values(days: list, prev_day: list, scores: dict, rule: str, start: str, us_days: list) -> dict:
    """CNN 恐懼貪婪的兩欄 {欄名: [每個日期的值]}：fear_greed_lag1 是選到那天 s 的分數，fear_greed_chg_lag1 是它減掉
    s 前一個美股交易日的分數（差幾分；2021-02-01 起最低到過 2.9，1 分就是 30% 以上，所以不用漲跌幅）。

    s 只從 us_days（美股交易日）挑，rule 是 features.fear_greed.day（使用者 2026-11-09）：
        second_last  d 之前最後一個美股交易日 e 的前一個美股交易日 s。CNN 最後一天（e）的點收盤後還會跟著下一個
                     美股交易日的盤前變，開盤後 3～14 分鐘才定住（2026-11-09、11-10 量的：11-09 那點到台北 11-10
                     13:00 都是 31.71，19:03 盤前變成 33.23）。e 的點要到台北 d 那天晚上才定住，會帶到 d 收盤以後的
                     資訊，不能用。s 的點在 e 開盤後幾分鐘（台北 e 那天晚上，一定早於 d）就定住了；定住的值是
                     e 開盤後約 10 分鐘的分數，不是 s 收盤時的分數。
                     s 是 CNN 檔裡最新的美股交易日時也空白（使用者 2026-11-09）：e 之後沒抓到新的（例如那天早上
                     CNN 沒抓到，或 CNN 自己少了 e 那天，像 2026-03-12），檔裡 s 的值是前一次抓的，那時還沒定住。
                     之後抓到新的、重寫最後兩個月時補上。
        prev_day     美國 i 那天，和 vix 一樣；美股 i 那天休市就空白。量到最後一天要到台北 t 那天晚上才定住，
                     所以現在不用這個規則。
    CNN 沒有 s 那天（例如 CNN 自己少了 2026-03-12）就空白，不往前找：往前找會在檔停住時一直沿用舊分數。
    道瓊的檔沒更新（^DJI 抓失敗、留著舊檔）時不會空白：e、s 照檔裡最後一天往前選，用比較舊的分數；道瓊補上後，
    隔天重寫最後兩個月時改回來。start（cnn.start）以前的分數不用。us_days 是空的（道瓊的檔不見、us_calendar
    不是 yfinance.tickers 的名稱）時整欄空白，不擋每天的流程；真的 config 有測試檢查。"""
    if rule not in ("second_last", "prev_day"):
        raise FeatureError(f"features.fear_greed.day 只能是 second_last 或 prev_day：{rule}")

    def score(day):
        return scores.get(day) if day is not None and day >= start else None

    us_set = set(us_days)
    newest = max((day for day in scores if day in us_set), default=None)   # CNN 檔裡最新的美股交易日
    level, chg = [], []
    for d, i in zip(days, prev_day):
        if rule == "second_last":
            j = bisect_left(us_days, d) - 2   # us_days[j + 1] 是 e
            if j >= 0 and newest is not None and us_days[j] >= newest:
                j = -1   # s 之後沒抓到新的：s 的值還沒定住
        else:
            j = bisect_left(us_days, i) if i else -1
            if j >= len(us_days) or (j >= 0 and us_days[j] != i):
                j = -1
        s = score(us_days[j]) if j >= 0 else None
        before = score(us_days[j - 1]) if j >= 1 else None
        level.append(np.nan if s is None else s)
        chg.append(s - before if s is not None and before is not None else np.nan)
    return {"fear_greed_lag1": level, "fear_greed_chg_lag1": chg}


# ---------------------------------------------------------------- 特徵表


def build_features(raw: dict, cfg: dict, t: str | None = None) -> pd.DataFrame:
    """回傳 pandas DataFrame（欄位見檔案開頭）。t 是預測日：給了就只留早於 t 的交易日，最後加 t 那列。

    只能用 t 之前的資料。t 當天的價格、成交量、法人、技術指標和 y 都不能進特徵；
    global 表的 ^TWII、^KS11、TX_OI 是當天收盤後的值，只會用到 i 和更早的列。
    """
    lags = cfg["features"]["lags"]
    stock_lags = cfg["features"].get("stock_lags", lags)
    stock_intraday_lags = cfg["features"].get("stock_intraday_lags", [])
    stock_gap_lags = cfg["features"].get("stock_gap_lags", [])
    stock_log_shares_lags = cfg["features"].get("stock_log_shares_lags", [])
    stock_ohlc_lags = cfg["features"].get("stock_ohlc_lags", [])
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

    def stock_value_lags(ds: list, values: list, requested_lags: list) -> dict:
        """把每個交易日自己的數值退到預測列；lag1 是 prev_day 那天，lag2 再往回一個有效個股資料列。"""
        return {
            k: at_prev_day({ds[j]: values[j - k + 1] for j in range(k - 1, len(ds))})
            for k in requested_lags
        }

    codes = sorted(stocks)
    n_days, n_codes = len(days), len(codes)
    data = {"date": np.repeat(days, n_codes), "stock_id": np.tile(codes, n_days),
            "is_top50": np.tile([int(c in raw["top50"]) for c in codes], n_days)}

    # 股票自己：只用交易日上填好的列
    own, own_intraday, own_gap, own_log_shares = {}, {}, {}, {}
    own_ohlc = {name: {} for name in ("open", "close", "high", "low")}
    for c in codes:
        ds = [d for d in sorted(stocks[c]) if d in pos and crawler.row_filled(stocks[c][d])]
        prices = [crawler.to_float(stocks[c][d][crawler.COL_CLOSE]) for d in ds]
        opens = [crawler.to_float(stocks[c][d][crawler.COL_OPEN]) for d in ds]
        highs = [crawler.to_float(stocks[c][d][crawler.COL_HIGH]) for d in ds]
        lows = [crawler.to_float(stocks[c][d][crawler.COL_LOW]) for d in ds]
        shares = [crawler.to_float(stocks[c][d][crawler.COL_SHARES]) for d in ds]
        intraday = [(close - open_) / open_ for close, open_ in zip(prices, opens)]
        gaps = [(opens[j] - prices[j - 1]) / prices[j - 1] for j in range(1, len(ds))]
        log_shares = [math.log1p(value) if value is not None and value >= 0 else np.nan for value in shares]
        own[c] = {k: at_prev_day(k_returns(ds, prices, k)) for k in stock_lags}
        own_intraday[c] = stock_value_lags(ds, intraday, stock_intraday_lags)
        own_gap[c] = stock_value_lags(ds[1:], gaps, stock_gap_lags)
        own_log_shares[c] = stock_value_lags(ds, log_shares, stock_log_shares_lags)
        for name, values in (("open", opens), ("close", prices), ("high", highs), ("low", lows)):
            own_ohlc[name][c] = stock_value_lags(ds, values, stock_ohlc_lags)
    for k in stock_lags:
        data[f"stock_ret_lag{k}"] = np.stack([own[c][k] for c in codes], axis=1).reshape(-1)
    for k in stock_intraday_lags:
        data[f"stock_intraday_ret_lag{k}"] = np.stack(
            [own_intraday[c][k] for c in codes], axis=1
        ).reshape(-1)
    for k in stock_gap_lags:
        data[f"stock_gap_ret_lag{k}"] = np.stack([own_gap[c][k] for c in codes], axis=1).reshape(-1)
    for k in stock_log_shares_lags:
        data[f"stock_log_shares_lag{k}"] = np.stack(
            [own_log_shares[c][k] for c in codes], axis=1
        ).reshape(-1)
    for name in ("open", "close", "high", "low"):
        for k in stock_ohlc_lags:
            data[f"stock_{name}_lag{k}"] = np.stack(
                [own_ohlc[name][c][k] for c in codes], axis=1
            ).reshape(-1)

    for name, (ds, prices) in market_sources(raw, cfg, calendar).items():
        for k in lags:
            data[f"{name}_ret_lag{k}"] = np.repeat(at_prev_day(k_returns(ds, prices, k)), n_codes)

    x = usd_twd_am_values(days, raw, cfg)   # t 自己的值當 cur
    for k in lags:
        values = k_returns(days, x, k)
        data[f"usd_twd_am_ret_lag{k}"] = np.repeat([values.get(d, np.nan) for d in days], n_codes)

    for column, values in tx_values(days, prev_day, calendar[-1] if calendar else "", raw["tx"], lags).items():
        data[column] = np.repeat(np.array(values, dtype=float), n_codes)

    # 以下只進長表（使用者 2026-11-08）。老師 S&P 500、Nasdaq 用 t 自己那列，和 usd_twd_am 一樣
    for column in cfg["features"].get("teacher_fresh") or ():
        x = teacher_fresh_values(days, raw["global"], column)
        for k in lags:
            values = k_returns(days, x, k)
            data[f"{series_name(column)}_fresh_ret_lag{k}"] = np.repeat([values.get(d, np.nan) for d in days], n_codes)

    gap = cfg["features"].get("open_gap") or {}
    same_day = raw.get("open_today") or {}
    for name in gap.get("series") or ():
        # t 那列只用當天早上抓的（08:25 以後才有）；日K的 t 那根爬蟲不留，open_gap_values 也再擋一次
        values = open_gap_values(days, raw["yfinance"].get(name, []), (gap.get("late_open") or {}).get(name),
                                 same_day.get(name), t)
        data[f"{name}_{OPEN_GAP}"] = np.repeat(np.array(values, dtype=float), n_codes)

    data.update(exchange_values(prev_day, codes, raw.get("exchange") or {}, cfg))

    # VIXTWN、CNN 恐懼貪婪（使用者 2026-11-09），只進長表
    fg = cfg["features"].get("fear_greed") or {}
    us_days = us_trading_days(raw["yfinance"].get(fg.get("us_calendar", "dji"), []))   # 不在 tickers 裡就是空的
    side = {**vixtwn_values(prev_day, raw.get("vixtwn") or {}),
            **fear_greed_values(days, prev_day, raw.get("fear_greed") or {}, fg.get("day", "second_last"),
                                (cfg.get("cnn") or {}).get("start", ""), us_days)}
    for column, values in side.items():
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
    for column in FLAG_COLUMNS:
        df[column] = df[column].astype("Int64")
    df["label_y"] = pd.array(label_y, dtype="Int64")
    df["label_intraday_return"] = np.array(label_ret, dtype=float)
    unknown = set(model_columns(cfg)) - set(df.columns)
    if unknown:
        raise FeatureError(f"features.model_series 有不存在的序列：{sorted(unknown)}")
    return df


def model_columns(cfg: dict) -> list:
    """模型特徵欄：個股特徵使用各自的 lag 設定，其他序列使用 lags。

    train.py、predict.py 只讀這些欄。

    開盤跳空（*_open_gap）用到 t 當天的資料，任何名字裡有 open_gap 的序列都丟 FeatureError（使用者 2026-11-08）。
    """
    series = cfg["features"]["model_series"]
    same_day = [s for s in series if OPEN_GAP in str(s)]
    if same_day:
        raise FeatureError(f"features.model_series 不能放開盤跳空的欄（用到 t 當天的資料）：{same_day}")
    lags = cfg["features"]["lags"]
    stock_lags = cfg["features"].get("stock_lags", lags)
    stock_intraday_lags = cfg["features"].get("stock_intraday_lags", [])
    stock_gap_lags = cfg["features"].get("stock_gap_lags", [])
    stock_log_shares_lags = cfg["features"].get("stock_log_shares_lags", [])
    stock_ohlc_lags = cfg["features"].get("stock_ohlc_lags", [])
    lag_sets = {"stock": stock_lags, "stock_intraday": stock_intraday_lags, "stock_gap": stock_gap_lags,
                "stock_log_shares": stock_log_shares_lags}
    stems = {"stock_log_shares": "stock_log_shares"}
    for name in ("stock_open", "stock_close", "stock_high", "stock_low"):
        lag_sets[name] = stock_ohlc_lags
        stems[name] = name
    return [f"{stems.get(s, f'{s}_ret')}_lag{k}" for s in series for k in lag_sets.get(s, lags)]


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
    for message in raw["notes"]:
        log.warning("%s（只進長表的欄，不算缺檔；檔案補齊後要 --rebuild，不然過去月份的這幾欄一直空白）", message)
    df = build_features(raw, cfg, t)
    row_t = df[df["date"] == t] if t else df.iloc[0:0]
    blank = [c for c in SIDE_COLUMNS if len(row_t) and row_t[c].isna().all()]
    if blank:   # 例如那天早上 CNN 沒抓到（審查 2026-11-09：爬蟲看不到特徵用哪一天，在這裡報）
        log.warning("t 那列的 %s 空白（只進長表的欄，原因見 fear_greed_values、vixtwn_values）", blank)
    out_dir = utils.ROOT / cfg["data"]["processed_dir"]
    industry = load_industry(out_dir / cfg["features"]["industry_file"])
    df = add_industry_columns(df, industry)
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
              "cleaning_counts": counts, "warnings": raw["warnings"], "notes": raw["notes"], "cleaning": raw["cleaning"]}
    crawler.write_atomic(out_dir / "manifest.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    log.info("特徵表：%d 列、%d 天，最後一天 %s；寫了 %s；清理紀錄 %s", len(df), report["dates"], last,
             written or "沒有月份變動", counts)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
