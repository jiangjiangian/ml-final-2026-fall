#!/usr/bin/env python3
"""yfinance 額外指標爬蟲 → data/ 資料夾整合 → 收盤報酬 lag 轉換 → schema.json。

1. 用 yfinance（https://github.com/ranaroussi/yfinance）下載老師 global_data 以外的 19 個額外指標
   （含台幣匯率 TWD=X），範圍 2020-01-01 ～ 2026-08-31，全程限流。
2. 清理 Yahoo 日K：丟掉壞報價（close 超出 [low, high] 0.5% 以上）、股票／ETF 的零量佔位K棒，
   並回補 Yahoo 漏調的股票分割（例：0052 在 2025-11-17 一拆七）。每筆修改都記在 manifest。
3. 從 live-data 分支取出老師 Training ZIP（核對 sha256），原樣放入 data/teacher/。
4. data/features/market_features.csv：每個台股交易日一列＝老師 global 欄位＋對齊後的額外特徵。
5. data/transform/lag2、lag5：每個特徵各一個 CSV（列＝台股交易日 t；值＝i＝t 的前一個台股交易日時，
   (close_i − close_{i−k}) / close_{i−k}，i−k 數該序列自己的交易日）。
6. schema.json：老師全部欄位、額外指標、transform 的定義、單位、lag 規則與資料品質紀錄。

限流：單執行緒；yfinance 發出的「每一個」HTTP 請求（時區、cookie、crumb、chart）都經過同一個
限流器（libcurl 自動跟隨的重新導向共用同一個名額，最多 5 次），上一個請求結束後至少間隔 --min-interval 秒＋0～--jitter 秒隨機抖動；暫時性錯誤指數退避重試，
Yahoo 回 429／YFRateLimitError 時退避再乘倍率；404／查無代碼等永久錯誤不重試；yfinance 內建重試關閉、
每次重試前清掉 yfinance 的記憶體快取；某序列因限流放棄後全域冷卻 --backoff-max 秒，連續 3 個序列
被限流就中止並保留舊檔。

用法（在 repo 根目錄）：
    pip install yfinance==1.7.0
    git fetch origin live-data
    python crawler.py                      # 下載＋整合＋transform＋schema
    python crawler.py --skip-download      # 只用現有 raw CSV 重建
    python crawler.py --only usd_twd --only sox
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from contextlib import nullcontext
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
SCHEMA_PATH = ROOT / 'schema.json'
START, END_INCLUSIVE = '2020-01-01', '2026-08-31'
SCHEMA_VERSION = 'data-folder-schema-v2'
MANIFEST_VERSION = 'yfinance-extra-manifest-v2'
FEATURES_FILE = 'features/market_features.csv'
TRANSFORM_DIR = 'transform'
TRANSFORM_LAGS = (2, 5)

# --------------------------------------------------------------------------- 額外指標清單
# kind: index / stock / etf / fx / fx_index / yield_percent / futures
TEACHER_TICKERS = ('^VIX', '^IXIC', '^GSPC', '^TWII', '^KS11')  # 老師 global_data 已有，排除
SERIES = [
    ('sox', '^SOX', 'PHLX Semiconductor Index', '費城半導體指數', 'M1_semiconductor', 'index', 'index_point', True, None),
    ('tsm_adr', 'TSM', 'Taiwan Semiconductor ADR', '台積電ADR', 'M2_overseas_stock', 'stock', 'USD', True, None),
    ('nvda', 'NVDA', 'NVIDIA', '輝達', 'M2_overseas_stock', 'stock', 'USD', True, None),
    ('usd_twd', 'TWD=X', 'USD/TWD exchange rate', '美元兌新台幣匯率', 'M3_fx_rates', 'fx', 'TWD_per_USD', True,
     '報價＝1美元兌多少台幣；報酬為正＝台幣貶值。Yahoo FX 日K依倫敦／GMT日界，不是台北收盤或定盤；'
     '約 68% 的列 close＝open（close 常是當日第一筆報價），各年比例不同。'),
    ('dxy', 'DX-Y.NYB', 'US Dollar Index', '美元指數', 'M3_fx_rates', 'fx_index', 'index_point', False, None),
    ('us10y', '^TNX', 'CBOE 10-Year Treasury Yield', '美國10年期公債殖利率', 'M3_fx_rates', 'yield_percent',
     'percent_per_annum', True, '以百分比報價（4.25＝4.25%）。'),
    ('us13w', '^IRX', '13-Week Treasury Bill Yield', '美國13週國庫券殖利率', 'M3_fx_rates', 'yield_percent',
     'percent_per_annum', False, '2020–2021 接近 0 且偶有負值；百分比報酬在此期間會非常大。'),
    ('etf_006201', '006201.TWO', 'Yuanta TPEx 50 ETF', '元大富櫃50（櫃買市場代理）', 'M4_taiwan', 'etf', 'TWD', False,
     'Yahoo 沒有櫃買指數本身（^TWOII／^TWO／^TPEX 皆查無）；以追蹤富櫃50指數的 ETF 代理櫃買市場。'),
    ('etf_0050', '0050.TW', 'Yuanta Taiwan Top 50 ETF', '元大台灣50（台灣50指數代理）', 'M4_taiwan', 'etf', 'TWD', False,
     'ETF 代理，不是台灣50指數本身。'),
    ('etf_0052', '0052.TW', 'Fubon Taiwan Technology ETF', '富邦科技（電子類代理）', 'M4_taiwan', 'etf', 'TWD', False,
     '電子類股代理，不是證交所電子類指數。2025 年 11 月一拆七（11-19～25 停牌、11-26 復牌）；Yahoo 只把 11-17 起的K棒'
     '÷7、更早的沒調整，且分割前的股利調整只做約 1/7，兩者都由 crawler 修正（見 cleaning）。'),
    ('etf_0055', '0055.TW', 'Yuanta MSCI Taiwan Financials ETF', '元大MSCI金融（金融類代理）', 'M4_taiwan', 'etf', 'TWD',
     False, '金融類股代理，不是證交所金融保險類指數。'),
    ('dji', '^DJI', 'Dow Jones Industrial Average', '道瓊工業指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('n225', '^N225', 'Nikkei 225', '日經225指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('hsi', '^HSI', 'Hang Seng Index', '恒生指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('sse', '000001.SS', 'SSE Composite Index', '上證綜合指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('stoxx50e', '^STOXX50E', 'EURO STOXX 50', '歐洲斯托克50指數', 'M5_global_index', 'index', 'index_point', False,
     'Yahoo 依瑞士假日缺 21 個 Eurex 交易日（1/2、耶穌升天日、聖靈降臨節翌日、8/1），因此 1 期報酬偶爾跨 2 個交易日。'),
    ('gdaxi', '^GDAXI', 'DAX', '德國DAX指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('wti', 'CL=F', 'WTI Crude Oil Futures', 'WTI原油期貨', 'M5_commodity', 'futures', 'USD_per_barrel', False,
     '連續近月合約；2020-04-20 結算價 −37.63，碰到非正價格的報酬保持空值。'),
    ('gold', 'GC=F', 'Gold Futures', '黃金期貨', 'M5_commodity', 'futures', 'USD_per_troy_ounce', False, None),
]
SPECS = [dict(zip(('series_id', 'ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required', 'note'), row))
         for row in SERIES]
SIGNED_KINDS = {'futures', 'yield_percent'}   # 原始價格可為 0 或負
ADJ_KINDS = {'stock', 'etf'}                  # 報酬用 adj_close；做分割與佔位K棒檢查
LEVEL_KINDS = {'fx', 'fx_index'}              # market_features 另輸出水準欄
RETURN_WINDOWS, YIELD_WINDOWS = (1, 5, 20), (1, 5)
RAW_COLUMNS = ('date', 'open', 'high', 'low', 'close', 'adj_close', 'volume')
PRICE_COLUMNS = ('open', 'high', 'low', 'close', 'adj_close')
YAHOO_COLUMNS = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'adj_close': 'Adj Close',
                 'volume': 'Volume'}
BAD_TICK_TOLERANCE = 0.005                    # close 超出 [low, high] 0.5% 以上視為壞報價
SPLIT_TOLERANCE, MAX_SPLIT_FACTOR = 0.03, 50
TW_SUFFIXES = ('.TW', '.TWO')                 # 台股漲跌幅 10%，單日 2 倍以上變動只可能是公司行動
PARTIAL_BAR_VOLUME_RATIO, PARTIAL_BAR_WINDOW = 0.01, 21
DIVIDEND_STEP_MIN = 1e-5                      # adj_close/close 比的跳動大於此值才算除息日
RATE_LIMIT_ERRORS = {'YFRateLimitError'}
PERMANENT_ERRORS = {'YFTickerMissingError', 'YFInvalidPeriodError', 'YFNotImplementedError'}
RETRY_ONCE_ERRORS = {'YFPricesMissingError', 'YFTzMissingError'}  # Yahoo 暫時錯誤也會丟這兩種，重試一次
CIRCUIT_BREAKER_SERIES = 3
REDIRECT_LIMIT = 5

# --------------------------------------------------------------------------- 老師欄位字典
GLOBAL_COLUMNS = ('date', '^VIX', '^IXIC', '^GSPC', '^TWII', '^KS11', 'TX_OI')
STOCK_COLUMNS = (
    'date', 'etl:adj_close', 'etl:adj_open', 'etl:adj_high', 'etl:adj_low',
    'price:成交筆數', 'price:成交金額', 'price:成交股數',
    'foreign_investors_shareholding:全體外資及陸資持股比率',
    'institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)',
    'institutional_investors_trading_summary:投信買賣超股數',
    'institutional_investors_trading_summary:自營商買賣超股數(自行買賣)',
    'institutional_investors_trading_summary:自營商買賣超股數(避險)',
    'RSI', 'SMA', 'MACD', 'ATR', 'BBANDS_upper', 'BBANDS_mid', 'BBANDS_lower', 'y',
)
US_TIMING = ('列日期 d 的值＝「前一個老師 global 列日期」的美股收盤（老師已位移，09:00 前可得）。'
             'global 表是台／美／韓交易日交集，長假後可能落後多個美股交易日；不要再自行 shift。')
SAME_DAY_NOTE = '09:00 前不可得；作為輸入至少要往前一列。market_features.csv 已改放前一列的值。'
TWII_TIMING = '列日期 d 的值＝d 當日收盤（實證：列報酬與 0050 同日報酬相關 0.94、與前一交易日 0.08）；' + SAME_DAY_NOTE
KS11_TIMING = '列日期 d 的值＝d 當日收盤（實證：列報酬與日經225同日報酬相關 0.65、與前一交易日 0.01）；' + SAME_DAY_NOTE
OI_TIMING = '發布時點未驗證（相關性檢查無定論）；專案在取得證據前不把它當正式特徵。'
TEACHER_GLOBAL = {
    'date': ('key', '老師 global 表的列日期：五個老師 Yahoo 序列同日都有資料才有列（大致是台／美／韓交易日交集，'
                    '但例如 2021-04-06 三地都有交易仍缺列）；缺列不代表休市', 'ISO date', None),
    '^VIX': ('market_lagged_by_teacher', 'CBOE VIX 波動率指數', 'index_point', US_TIMING),
    '^IXIC': ('market_lagged_by_teacher', 'Nasdaq Composite 那斯達克綜合指數', 'index_point', US_TIMING),
    '^GSPC': ('market_lagged_by_teacher', 'S&P 500 標普500指數', 'index_point', US_TIMING),
    '^TWII': ('raw_same_day', '台灣加權股價指數', 'index_point', TWII_TIMING),
    '^KS11': ('raw_same_day', 'KOSPI 韓國綜合指數', 'index_point', KS11_TIMING),
    'TX_OI': ('timing_unverified', '台指期外資淨未平倉口數（多方減空方，可為負）', 'contracts', OI_TIMING),
}
TEACHER_STOCK = {
    'date': ('key', '台股交易日', 'ISO date'),
    'etl:adj_close': ('outcome_same_day', '還原收盤價', 'TWD'),
    'etl:adj_open': ('outcome_same_day', '還原開盤價', 'TWD'),
    'etl:adj_high': ('outcome_same_day', '還原最高價', 'TWD'),
    'etl:adj_low': ('outcome_same_day', '還原最低價', 'TWD'),
    'price:成交筆數': ('raw_same_day', '成交筆數', 'trades'),
    'price:成交金額': ('raw_same_day', '成交金額', 'TWD'),
    'price:成交股數': ('raw_same_day', '成交股數', 'shares'),
    'foreign_investors_shareholding:全體外資及陸資持股比率': ('raw_same_day', '全體外資及陸資持股比率', 'percent'),
    'institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)':
        ('raw_same_day', '外陸資買賣超股數（不含外資自營商）', 'shares_signed'),
    'institutional_investors_trading_summary:投信買賣超股數': ('raw_same_day', '投信買賣超股數', 'shares_signed'),
    'institutional_investors_trading_summary:自營商買賣超股數(自行買賣)':
        ('raw_same_day', '自營商買賣超股數（自行買賣）', 'shares_signed'),
    'institutional_investors_trading_summary:自營商買賣超股數(避險)':
        ('raw_same_day', '自營商買賣超股數（避險）', 'shares_signed'),
    'RSI': ('raw_same_day', 'RSI 相對強弱指標（來源尺度）', 'provider_units'),
    'SMA': ('raw_same_day', 'SMA 簡單移動平均', 'TWD'),
    'MACD': ('raw_same_day', 'MACD', 'provider_units'),
    'ATR': ('raw_same_day', 'ATR 平均真實波幅', 'TWD'),
    'BBANDS_upper': ('raw_same_day', '布林通道上軌', 'TWD'),
    'BBANDS_mid': ('raw_same_day', '布林通道中軌', 'TWD'),
    'BBANDS_lower': ('raw_same_day', '布林通道下軌', 'TWD'),
    'y': ('label', '目標：1{adj_close > adj_open}（盤中上漲）', 'binary'),
}
ROLE_NOTES = {
    'key': '索引鍵，不是數值特徵',
    'market_lagged_by_teacher': '全市場共用；老師已位移到前一列日期，可直接作輸入',
    'raw_same_day': '目標日收盤後才知道；只能用前一列（lag）',
    'timing_unverified': '發布時點未驗證；使用前自行確認',
    'outcome_same_day': '目標日當日價格＝答案的一部分；只能用前一觀測（lag）',
    'label': '只用於訓練／評分，絕不放入輸入',
}
TEACHER_TRANSFORM = {'^VIX': 'teacher_vix', '^IXIC': 'teacher_ixic', '^GSPC': 'teacher_gspc',
                     '^TWII': 'teacher_twii', '^KS11': 'teacher_ks11'}


class CrawlError(ValueError):
    """永久性的下載、驗證或設定錯誤。"""


# --------------------------------------------------------------------------- 限流
@dataclass(frozen=True)
class RateLimitPolicy:
    min_interval_seconds: float = 2.0
    jitter_seconds: float = 1.0
    max_retries: int = 5
    backoff_base_seconds: float = 5.0
    backoff_max_seconds: float = 120.0
    rate_limited_backoff_multiplier: float = 3.0
    request_timeout_seconds: float = 30.0

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise CrawlError('限流設定必須是有限的非負數')
        if self.max_retries != int(self.max_retries) or self.max_retries > 20:
            raise CrawlError('max_retries 必須是 0～20 的整數')
        if self.rate_limited_backoff_multiplier < 1 or self.request_timeout_seconds <= 0:
            raise CrawlError('限流倍率需 >= 1，逾時需 > 0')


class RateLimiter:
    """保證「上一個請求結束」到「下一個請求開始」至少間隔 min_interval＋隨機抖動。"""

    def __init__(self, min_interval, jitter=0.0, *, clock=time.monotonic, sleep=time.sleep, rng=random.random):
        self.min_interval, self.jitter = float(min_interval), float(jitter)
        self._clock, self._sleep, self._rng = clock, sleep, rng
        self._next_allowed = None
        self.requests, self.slept_seconds = 0, 0.0

    def __enter__(self):
        if self._next_allowed is not None:
            delay = self._next_allowed - self._clock()
            if delay > 0:
                self._sleep(delay)
                self.slept_seconds += delay
        self.requests += 1
        return self

    def __exit__(self, *exc):
        self._next_allowed = self._clock() + self.min_interval + self.jitter * self._rng()
        return False


def classify_error(exc):
    name, text = type(exc).__name__, str(exc).lower()
    if name in RATE_LIMIT_ERRORS or 'too many requests' in text or 'rate limit' in text or ' 429' in text:
        return 'rate_limited'
    if name in PERMANENT_ERRORS or isinstance(exc, CrawlError) or 'http error 404' in text or 'not found' in text:
        return 'permanent'
    if name in RETRY_ONCE_ERRORS:
        return 'maybe_permanent'
    return 'transient'


def backoff_delay(attempt, policy, kind, rng=random.random):
    delay = policy.backoff_base_seconds * (2 ** (attempt - 1))
    if kind == 'rate_limited':
        delay *= policy.rate_limited_backoff_multiplier
    return min(policy.backoff_max_seconds, delay) + policy.jitter_seconds * rng()


def fetch_with_retry(fetch, spec, start, end_exclusive, limiter, policy, *, sleep=time.sleep, rng=random.random):
    """fetch 若自帶 HTTP 層限流（fetch.limiter），就不再外包一層，避免重複等待。"""
    paced_inside = getattr(fetch, 'limiter', None) is not None
    events = []
    for attempt in range(1, policy.max_retries + 2):
        try:
            with nullcontext() if paced_inside else limiter:
                rows = fetch(spec['ticker'], start.isoformat(), end_exclusive.isoformat())
            return rows, attempt, events
        except Exception as exc:  # 依類型分流；KeyboardInterrupt 不在此攔截
            kind = classify_error(exc)
            events.append({'attempt': attempt, 'error_class': type(exc).__name__, 'kind': kind,
                           'message': str(exc)[:200]})
            if kind == 'permanent' or (kind == 'maybe_permanent' and attempt >= 2) or attempt > policy.max_retries:
                error = CrawlError(f"{spec['series_id']}: {type(exc).__name__}: {str(exc)[:200]}")
                error.events, error.kind = events, kind
                raise error from exc
            delay = backoff_delay(attempt, policy, kind, rng)
            events[-1]['backoff_seconds'] = round(delay, 3)
            sleep(delay)
    raise AssertionError('unreachable')


# --------------------------------------------------------------------------- 下載、驗證與清理
def _iso(value, name):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise CrawlError(f'{name} 必須是 ISO 日期') from None
    if parsed.isoformat() != value:
        raise CrawlError(f'{name} 必須是標準 ISO 日期')
    return parsed


def _finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CrawlError('價格欄位不是數字') from None
    return number if math.isfinite(number) else None


def frame_to_rows(frame):
    """yfinance DataFrame → list[dict]；index 為交易所時區，.date() 即原生交易日。"""
    rows = []
    for stamp, record in zip(frame.index, frame.to_dict('records')):
        day = stamp.date() if hasattr(stamp, 'date') else stamp
        rows.append({'date': day.isoformat(), **{k: record.get(c) for k, c in YAHOO_COLUMNS.items()}})
    return rows


def validate_rows(rows, spec, start, end_inclusive):
    """丟掉範圍外與 close 缺值的佔位列；價格異常或重複日期則報錯。"""
    lo, hi = start.isoformat(), end_inclusive.isoformat()
    cleaned, dropped, seen = [], 0, set()
    for raw in rows:
        day = _iso(raw.get('date'), 'bar date').isoformat()
        values = {key: _finite(raw.get(key)) for key in RAW_COLUMNS[1:]}
        if day < lo or day > hi or values['close'] is None:
            dropped += 1
            continue
        if spec['kind'] not in SIGNED_KINDS and values['close'] <= 0:
            raise CrawlError(f"{spec['series_id']}: {day} close <= 0")
        if day in seen:
            raise CrawlError(f"{spec['series_id']}: 重複交易日 {day}")
        seen.add(day)
        cleaned.append({'date': day, **values})
    if not cleaned:
        raise CrawlError(f"{spec['series_id']}: 範圍內沒有可用日K")
    cleaned.sort(key=lambda r: r['date'])
    return cleaned, dropped


def _split_factor(prev, cur):
    """前後收盤比接近整數 n（2..50）時回傳 n（正向分割）或 1/n（反向合併）。"""
    if prev is None or cur is None or prev <= 0 or cur <= 0:
        return None
    ratio = prev / cur
    for value, factor in ((ratio, None), (1 / ratio, -1)):
        n = round(value)
        if 2 <= n <= MAX_SPLIT_FACTOR and abs(value - n) / n < SPLIT_TOLERANCE:
            return float(n) if factor is None else 1.0 / n
    return None


def _flat(row):
    return len({row[k] for k in ('open', 'high', 'low', 'close')}) == 1


def _dropped(row, reason):
    return {**{k: row[k] for k in RAW_COLUMNS}, 'reason': reason}


def _is_bond_holiday(day):
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


def _rescale_dividends(rows, boundary, factor, log):
    """Yahoo 漏調分割時，分割前的股利調整也只做了約 1/factor；把該段每個除息幅度乘回 factor。"""
    ratios = [r['adj_close'] / r['close'] if r['adj_close'] and r['close'] else None for r in rows[:boundary]]
    if boundary < 2 or any(x is None or x <= 0 for x in ratios):
        return
    level = ratios[-1]
    fixes = []
    for t in range(boundary - 2, -1, -1):
        step = 1 - ratios[t] / ratios[t + 1]
        if step > DIVIDEND_STEP_MIN:
            fixed = min(step * factor, 0.95)
            level *= 1 - fixed
            fixes.append({'ex_date': rows[t + 1]['date'], 'yahoo_fraction': step, 'rescaled_fraction': fixed})
        else:
            level *= ratios[t] / ratios[t + 1]
        rows[t]['adj_close'] = rows[t]['close'] * level
    log['dividend_adjustments_rescaled'].extend(sorted(fixes, key=lambda x: x['ex_date']))


def clean_series(rows, spec):
    """回傳 (清理後列, 修改紀錄)。

    順序：壞報價 → 債市假日平盤K棒（殖利率）→ 佔位／不完整K棒（股票、ETF）→ 漏調的分割與分割前股利（台股）。
    紀錄中被刪除的列是 Yahoo 原始單位（尚未做分割修正）。
    """
    log = {'bad_ticks_dropped': [], 'bond_holiday_bars_dropped': [], 'placeholder_bars_dropped': [],
           'split_adjustments': [], 'dividend_adjustments_rescaled': [], 'suspected_splits_not_applied': []}
    kept = []
    for row in rows:
        lo, hi, close = row['low'], row['high'], row['close']
        if lo is not None and hi is not None and lo <= hi and (
                close < lo - BAD_TICK_TOLERANCE * abs(lo) or close > hi + BAD_TICK_TOLERANCE * abs(hi)):
            log['bad_ticks_dropped'].append(_dropped(row, 'close 超出 [low, high] 0.5% 以上'))
            continue
        if spec['kind'] == 'yield_percent' and _flat(row) and _is_bond_holiday(row['date']):
            log['bond_holiday_bars_dropped'].append(_dropped(row, '美國債市休市日（哥倫布日／退伍軍人節）的平盤K棒'))
            continue
        kept.append(row)
    if spec['kind'] not in ADJ_KINDS:
        return kept, log
    rows, kept = kept, []
    for row in rows:
        if kept and _flat(row):
            if not row['volume'] and row['close'] == kept[-1]['close']:
                log['placeholder_bars_dropped'].append(_dropped(row, '零量平盤且等於前一收盤'))
                continue
            recent = sorted(r['volume'] for r in kept[-PARTIAL_BAR_WINDOW:] if r['volume'])
            median = recent[len(recent) // 2] if recent else None
            if row['volume'] and median and row['volume'] < PARTIAL_BAR_VOLUME_RATIO * median:
                log['placeholder_bars_dropped'].append(
                    _dropped(row, f'平盤且成交量 < 前 {PARTIAL_BAR_WINDOW} 筆中位數的 1%（不完整K棒）'))
                continue
        kept.append(row)
    taiwan = spec['ticker'].upper().endswith(TW_SUFFIXES)
    for i in range(1, len(kept)):
        prev, cur = kept[i - 1], kept[i]
        factor = _split_factor(prev['close'], cur['close'])
        if factor is None or _split_factor(prev['adj_close'], cur['adj_close']) != factor:
            continue
        if not taiwan:
            log['suspected_splits_not_applied'].append(
                {'date': cur['date'], 'factor': factor, 'reason': '非台股沒有漲跌幅限制，可能是真實的大漲跌；未修改'})
            continue
        for row in kept[:i]:
            for key in PRICE_COLUMNS:
                if row[key] is not None:
                    row[key] = row[key] / factor
            if row['volume'] is not None:
                row['volume'] = row['volume'] * factor
        log['split_adjustments'].append({
            'yahoo_adjustment_boundary': cur['date'], 'factor': factor,
            'previous_close_before_fix': prev['close'] * factor, 'close_on_boundary': cur['close'],
            'reason': 'Yahoo 只把此日起的K棒做了分割調整；更早的價格 ÷factor、成交量 ×factor（台股漲跌幅 10%，'
                      '單日 2 倍以上變動只可能是公司行動）'})
        _rescale_dividends(kept, i, factor, log)
    return kept, log


def _raw_cell(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def rows_to_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(RAW_COLUMNS)
    for row in rows:
        writer.writerow([row['date']] + [_raw_cell(row[key]) for key in RAW_COLUMNS[1:]])
    return buffer.getvalue().encode('utf-8')


def write_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(payload)
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _sha(payload):
    """以 LF 行尾計算 sha256，Windows autocrlf 取出的檔案也能核對。"""
    return hashlib.sha256(payload.replace(b'\r\n', b'\n')).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _existing_entry(path, meta):
    """失敗時檢查舊檔是否仍可用，可用就沿用並重算 hash，不因 manifest 過期而刪檔。"""
    try:
        rows = read_raw_series(path)
    except (OSError, ValueError, CrawlError):
        return None
    if not rows:
        return None
    return {**meta, 'status': 'ok', 'file': f'yfinance/{path.name}', 'sha256': _sha(path.read_bytes()),
            'rows': len(rows), 'date_min': rows[0][0], 'date_max': rows[-1][0], 'kept_previous_file': True}


def crawl(specs, extra_dir, fetch, *, start=START, end_inclusive=END_INCLUSIVE, library_version='unknown',
          only=None, policy=None, sleep=time.sleep, clock=time.monotonic, rng=random.random, now=None):
    """逐檔下載、清理後寫 extra/yfinance/<series_id>.csv；每完成一檔就更新 extra/manifest.json。"""
    extra_dir = Path(extra_dir)
    start_d, end_d = _iso(start, 'start'), _iso(end_inclusive, 'end')
    end_exclusive = end_d + timedelta(days=1)  # yfinance 的 end 不含當天
    policy = policy or RateLimitPolicy()
    limiter = getattr(fetch, 'limiter', None) or RateLimiter(
        policy.min_interval_seconds, policy.jitter_seconds, clock=clock, sleep=sleep, rng=rng)
    manifest_path = extra_dir / 'manifest.json'
    previous = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding='utf-8')).get('series', {})
        except (ValueError, AttributeError):
            previous = {}
    known = {s['series_id'] for s in specs}
    if only and set(only) - known:
        raise CrawlError(f'未知的 series_id：{sorted(set(only) - known)}')
    selected = [s for s in specs if not only or s['series_id'] in set(only)]
    run_started = (now or (lambda: datetime.now(timezone.utc)))().isoformat(timespec='seconds')
    entries = {sid: entry for sid, entry in previous.items() if sid in known}
    state = {'failed': [], 'aborted': [], 'consecutive_rate_limited': 0, 'cooldown_seconds': 0.0}

    def manifest():
        ordered = {s['series_id']: entries[s['series_id']] for s in specs if s['series_id'] in entries}
        missing = sorted(s['series_id'] for s in specs
                         if s['required'] and ordered.get(s['series_id'], {}).get('status') != 'ok')
        all_ok = len(ordered) == len(specs) and all(v.get('status') == 'ok' for v in ordered.values())
        refreshed = not state['failed'] and not state['aborted']
        status = ('complete' if refreshed else 'stale') if all_ok else 'partial'
        return {
            'schema_version': MANIFEST_VERSION, 'source': 'Yahoo Finance via yfinance',
            'library': 'https://github.com/ranaroussi/yfinance', 'library_version': library_version,
            'terms_note': 'Yahoo 非官方介面，僅供課程研究；再散布授權未核實。',
            'range': {'start': start_d.isoformat(), 'end_inclusive': end_d.isoformat(),
                      'request_end_exclusive': end_exclusive.isoformat()},
            'request_options': {'interval': '1d', 'auto_adjust': False, 'actions': False, 'repair': False},
            'date_semantics': 'date＝該日K的交易所當地原生交易日；不是發布或可用時間',
            'cleaning_rules': {
                'bad_tick': f'所有序列：close 超出 [low, high] {BAD_TICK_TOLERANCE:.1%} 以上 → 刪除該列',
                'bond_holiday_bar': '殖利率：美國債市休市（哥倫布日、退伍軍人節，週六提前／週日順延）的平盤K棒 → 刪除',
                'placeholder_bar': ('股票／ETF：OHLC 相同，且（成交量 0 並等於前一收盤，或成交量 < 前 '
                                    f'{PARTIAL_BAR_WINDOW} 筆中位數的 {PARTIAL_BAR_VOLUME_RATIO:.0%}）→ 刪除'),
                'split_fix': ('台股（' + '／'.join(TW_SUFFIXES) + '）股票／ETF：前後 close 與 adj_close 比都接近整數 n'
                              f'（2..{MAX_SPLIT_FACTOR}，誤差 <{SPLIT_TOLERANCE:.0%}）→ 之前的價格 ÷n、成交量 ×n；'
                              '反向（後/前≈n）則之前的價格 ×n、成交量 ÷n。非台股只記為 suspected，不修改'),
                'split_dividend_fix': '修正分割時，分割前每個除息日的調整幅度（adj_close/close 比的跳動）乘以 n',
                'logged_units': '被刪除列的紀錄是 Yahoo 原始單位（尚未做分割修正）',
            },
            'rate_limit': {
                'config': {**asdict(policy), 'mode': 'sequential_single_thread',
                           'scope': '每一個 HTTP 請求（時區、cookie、crumb、chart）都經過同一限流器',
                           'yfinance_internal_retries': 0,
                           'circuit_breaker': f'序列因限流放棄後冷卻 backoff_max 秒；連續 {CIRCUIT_BREAKER_SERIES} '
                                              '個序列被限流即中止'},
                'last_run': {'run_started_at': run_started, 'series_requested': [s['series_id'] for s in selected],
                             'http_requests': limiter.requests,
                             'paced_sleep_seconds': round(limiter.slept_seconds, 3),
                             'circuit_breaker_cooldown_seconds': round(state['cooldown_seconds'], 3)},
            },
            'failed_last_run': state['failed'], 'aborted_last_run': state['aborted'], 'missing_required': missing,
            'status': status,
            'status_meaning': ('complete＝全部 ok 且本次都更新；stale＝全部 ok 但本次有失敗或中止（沿用舊檔）；'
                               'partial＝有序列不可用'),
            'series': ordered,
        }

    for index, spec in enumerate(selected):
        sid = spec['series_id']
        if state['consecutive_rate_limited'] >= CIRCUIT_BREAKER_SERIES:
            state['aborted'] = [s['series_id'] for s in selected[index:]]
            print(f'[crawl] 連續 {CIRCUIT_BREAKER_SERIES} 個序列被限流，中止：{state["aborted"]}', file=sys.stderr)
            break
        meta = {k: spec[k] for k in ('ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required')}
        print(f'[crawl] {sid:<11} {spec["ticker"]}', file=sys.stderr, flush=True)
        path = extra_dir / 'yfinance' / f'{sid}.csv'
        try:
            raw, attempts, events = fetch_with_retry(fetch, spec, start_d, end_exclusive, limiter, policy,
                                                     sleep=sleep, rng=rng)
            rows, dropped = validate_rows(raw, spec, start_d, end_d)
            rows, cleaning = clean_series(rows, spec)
            if not rows:
                raise CrawlError(f'{sid}: 清理後沒有資料')
            payload = rows_to_csv(rows)
            write_atomic(path, payload)
            entries[sid] = {**meta, 'status': 'ok', 'file': f'yfinance/{sid}.csv', 'sha256': _sha(payload),
                            'rows': len(rows), 'dropped_out_of_range_or_empty': dropped,
                            'date_min': rows[0]['date'], 'date_max': rows[-1]['date'], 'fetched_at': run_started,
                            'attempts': attempts, 'retry_events': events, 'cleaning': cleaning}
            state['consecutive_rate_limited'] = 0
        except CrawlError as exc:
            state['failed'].append(sid)
            kind = getattr(exc, 'kind', 'permanent')
            print(f'[crawl] {sid} 失敗（{kind}）：{exc}', file=sys.stderr, flush=True)
            attempt = {'status': 'failed', 'kind': kind, 'at': run_started, 'error': str(exc)[:300],
                       'retry_events': getattr(exc, 'events', [])}
            kept = _existing_entry(path, meta) if path.exists() else None
            if kept is not None:
                old = entries.get(sid) or {}
                entries[sid] = {**{k: v for k, v in old.items() if k != 'last_attempt'}, **kept, 'last_attempt': attempt}
            else:
                path.unlink(missing_ok=True)
                entries[sid] = {**meta, 'status': 'failed', 'last_attempt': attempt}
            if kind == 'rate_limited':
                state['consecutive_rate_limited'] += 1
                last = index == len(selected) - 1
                if not last and state['consecutive_rate_limited'] < CIRCUIT_BREAKER_SERIES:
                    sleep(policy.backoff_max_seconds)
                    state['cooldown_seconds'] += policy.backoff_max_seconds
            else:
                state['consecutive_rate_limited'] = 0
        write_atomic(manifest_path, _json_bytes(manifest()))
    final = manifest()
    write_atomic(manifest_path, _json_bytes(final))
    return final


def yfinance_fetcher(limiter, timeout=30.0, cache_dir=None):
    """回傳經限流 HTTP session 的 fetch；yfinance 自己的重試關閉，重試前清掉其 lru_cache。"""
    import yfinance as yf
    import yfinance.data as yf_data
    from curl_cffi import requests as curl_requests

    class PacedSession(curl_requests.Session):
        def request(self, *args, **kwargs):  # Session.get/post 都會走到這裡
            with limiter:
                return super().request(*args, **kwargs)

    config = getattr(yf, 'config', None)
    if config is not None:
        config.debug.hide_exceptions = False  # 被限流時拋出例外，而不是回傳空表
        config.network.retries = 0
    if cache_dir is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))
    session = PacedSession(impersonate='chrome', max_redirects=REDIRECT_LIMIT)

    def fetch(ticker, start, end_exclusive):
        cache = getattr(getattr(yf_data, 'YfData', None), 'cache_get', None)
        if cache is not None and hasattr(cache, 'cache_clear'):
            cache.cache_clear()  # 否則重試只會重播快取中的錯誤回應
        frame = yf.Ticker(ticker, session=session).history(
            start=start, end=end_exclusive, interval='1d', auto_adjust=False, actions=False, repair=False,
            timeout=timeout)
        if frame is None or len(frame) == 0:
            raise CrawlError(f'{ticker}: 空的歷史資料')
        return frame_to_rows(frame)

    fetch.limiter = limiter
    return fetch, getattr(yf, '__version__', 'unknown')


# --------------------------------------------------------------------------- 老師資料
def live_data_training_zip(repo, ref='origin/live-data'):
    """經 git 從 live-data 分支讀最新老師 Training ZIP，逐層核對 sha256。"""
    def show(path):
        result = subprocess.run(['git', '-C', str(repo), 'show', f'{ref}:{path}'], capture_output=True, check=False)
        if result.returncode != 0:
            raise CrawlError(f'無法從 {ref} 讀 {path}；請先 git fetch origin live-data')
        return result.stdout

    pointer = json.loads(show('catalog/latest.json'))
    catalog = show(pointer['catalog_key'])
    if hashlib.sha256(catalog).hexdigest() != pointer['catalog_sha256']:
        raise CrawlError('live-data catalog hash 不符')
    source = json.loads(catalog)['sources']['course-training']
    digest = source['latest_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise CrawlError('Training 物件 digest 格式錯誤')
    payload = show(f'objects/{digest}.zip')
    if hashlib.sha256(payload).hexdigest() != digest:
        raise CrawlError('老師 Training ZIP hash 不符')
    return payload, {'live_data_ref': ref, 'catalog_sha256': pointer['catalog_sha256'],
                     'object': f'live-data:objects/{digest}.zip', 'source_fetched_at': source.get('fetched_at')}


def _csv_rows(payload):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
    return tuple(reader.fieldnames or ()), list(reader)


def teacher_summary(members, expected_stocks=100, expected_targets=50):
    """驗證老師檔案集合（{'data/...': bytes}）並回傳摘要。"""
    names = list(members)
    stocks = sorted(n for n in names if re.fullmatch(r'data/market/[0-9A-Za-z]+\.csv', n))
    if set(names) != set(stocks) | {'data/global/global_data.csv', 'data/info.json'}:
        raise CrawlError('老師檔案成員不符預期')
    if len(stocks) != expected_stocks:
        raise CrawlError('老師股票數不符預期')
    info = json.loads(members['data/info.json'].decode('utf-8-sig'))
    ids = [PurePosixPath(n).stem for n in stocks]
    if set(info) != {'Top50@Y', 'Top100@Y'} or set(map(str, info['Top100@Y'])) != set(ids) \
            or len(info['Top50@Y']) != expected_targets:
        raise CrawlError('info.json 名單與檔案不一致')
    fields, global_rows = _csv_rows(members['data/global/global_data.csv'])
    if fields != GLOBAL_COLUMNS:
        raise CrawlError('global_data.csv 欄位改變')
    stock_dates, stock_rows = set(), 0
    for name in stocks:
        fields, rows = _csv_rows(members[name])
        if fields != STOCK_COLUMNS:
            raise CrawlError(f'{name} 欄位改變')
        stock_dates.update(r['date'] for r in rows)
        stock_rows += len(rows)
    gdates = {r['date'] for r in global_rows}
    in_range = {d for d in stock_dates if START <= d <= END_INCLUSIVE}
    digest = hashlib.sha256(''.join(f'{name}\t{_sha(members[name])}\n' for name in sorted(members)).encode())
    return {'members_sha256': digest.hexdigest(), 'stock_count': len(stocks), 'target_stock_count': len(info['Top50@Y']), 'stock_rows': stock_rows,
            'stock_date_min': min(stock_dates), 'stock_date_max': max(stock_dates),
            'global_rows': len(global_rows), 'global_date_min': min(gdates), 'global_date_max': max(gdates),
            'global_missing_taiwan_trading_days': len(in_range - gdates)}


def extract_teacher(payload, data_dir):
    """驗證後把老師 ZIP 原樣（逐位元組）放入 data/teacher/。"""
    teacher = Path(data_dir) / 'teacher'
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    summary = teacher_summary(members)
    if teacher.exists():
        shutil.rmtree(teacher)
    for name, content in members.items():
        write_atomic(teacher.joinpath(*PurePosixPath(name).parts[1:]), content)
    return {'archive_sha256': hashlib.sha256(payload).hexdigest(), **summary}


def teacher_from_dir(data_dir):
    """--keep-teacher：直接驗證 data/teacher/ 的現有檔案。"""
    teacher = Path(data_dir) / 'teacher'
    if not (teacher / 'global' / 'global_data.csv').exists():
        raise CrawlError(f'{teacher} 沒有老師資料：請 git fetch origin live-data 後不要加 --keep-teacher')
    members = {'data/' + p.relative_to(teacher).as_posix(): p.read_bytes()
               for p in sorted(teacher.rglob('*')) if p.is_file()}
    return teacher_summary(members)


# --------------------------------------------------------------------------- 特徵對齊
def _read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return tuple(reader.fieldnames or ()), list(reader)


def taiwan_target_dates(data_dir, start=START, end_inclusive=END_INCLUSIVE):
    dates = set()
    for path in sorted((Path(data_dir) / 'teacher' / 'market').glob('*.csv')):
        dates.update(r['date'] for r in _read_csv(path)[1] if start <= r['date'] <= end_inclusive)
    if not dates:
        raise CrawlError('範圍內沒有老師台股交易日')
    return sorted(dates)


def _num(text):
    if text in (None, ''):
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def read_raw_series(path):
    fields, rows = _read_csv(path)
    if fields != RAW_COLUMNS:
        raise CrawlError(f'{Path(path).name}: raw 欄位不符')
    out = [(r['date'], _num(r['close']), _num(r['adj_close'])) for r in rows]
    out = [r for r in out if r[1] is not None]
    if [r[0] for r in out] != sorted({r[0] for r in out}):
        raise CrawlError(f'{Path(path).name}: 日期須排序且唯一')
    return out


def series_prices(spec, rows):
    """回傳 (dates, prices)；股票／ETF 用 adj_close（缺值時 close），其他用 close。"""
    dates = [r[0] for r in rows]
    prices = [(r[2] if spec['kind'] in ADJ_KINDS and r[2] is not None else r[1]) for r in rows]
    return dates, prices


def feature_columns(spec):
    sid = spec['series_id']
    if spec['kind'] == 'yield_percent':
        cols = [f'{sid}_level_pct'] + [f'{sid}_change_bp_{k}s' for k in YIELD_WINDOWS]
    else:
        cols = ([f'{sid}_level'] if spec['kind'] in LEVEL_KINDS else []) + [f'{sid}_ret_{k}s' for k in RETURN_WINDOWS]
    return cols + [f'{sid}_age_days', f'{sid}_source_date']


def feature_definitions(spec, min_lag_days):
    sid, unit, kind = spec['series_id'], spec['unit'], spec['kind']
    base = {'series_id': sid, 'ticker': spec['ticker'], 'group': spec['group'],
            'lag_rule': (f's＝{spec["ticker"]} 最後一個 session_date <= target_date − {min_lag_days} 日曆天的交易日；'
                         'k 期＝往回 k 個該序列有資料的交易日，不是台股列位移'),
            'historical_vintage_verified': False}
    out = {}
    if kind == 'yield_percent':
        out[f'{sid}_level_pct'] = {**base, 'formula': 'Y[s]', 'unit': unit, 'description': f'{spec["name_zh"]}水準'}
        for k in YIELD_WINDOWS:
            out[f'{sid}_change_bp_{k}s'] = {**base, 'formula': f'100*(Y[s]-Y[s-{k}])', 'unit': 'basis_point',
                                            'description': f'{spec["name_zh"]} {k} 期基點變化（不是價格報酬）'}
    else:
        price = 'adj_close（缺值時 close）' if kind in ADJ_KINDS else 'close'
        if kind in LEVEL_KINDS:
            out[f'{sid}_level'] = {**base, 'formula': 'P[s]', 'unit': unit, 'description': f'{spec["name_zh"]}水準'}
        for k in RETURN_WINDOWS:
            note = '；正值＝台幣貶值' if sid == 'usd_twd' else ''
            out[f'{sid}_ret_{k}s'] = {**base, 'formula': f'P[s]/P[s-{k}]-1', 'unit': 'decimal_return',
                                      'price_column': price,
                                      'description': f'{spec["name_zh"]} {k} 個交易日累積報酬{note}',
                                      'missing_policy': '前 k 期不存在或任一價格 <= 0 時為空值'}
    out[f'{sid}_age_days'] = {**base, 'formula': 'target_date − s', 'unit': 'calendar_days',
                              'description': '所用來源交易日距目標日的日曆天數（新鮮度）'}
    out[f'{sid}_source_date'] = {**base, 'formula': 's', 'unit': 'ISO date', 'role': 'trace_not_model_input',
                                 'description': '實際採用的來源交易日（追溯用，不是模型輸入）'}
    return out


def series_features(spec, rows, targets, min_lag_days=1):
    """先在完整原生序列算報酬，再對齊到每個台股目標日。"""
    sid, kind = spec['series_id'], spec['kind']
    dates, prices = series_prices(spec, rows)
    cols = {name: [] for name in feature_columns(spec)}
    for target in targets:
        t = date.fromisoformat(target)
        i = bisect_right(dates, (t - timedelta(days=min_lag_days)).isoformat()) - 1
        if i < 0:
            for values in cols.values():
                values.append(None)
            continue
        if kind == 'yield_percent':
            cols[f'{sid}_level_pct'].append(prices[i])
            for k in YIELD_WINDOWS:
                cols[f'{sid}_change_bp_{k}s'].append(100 * (prices[i] - prices[i - k]) if i >= k else None)
        else:
            if kind in LEVEL_KINDS:
                cols[f'{sid}_level'].append(prices[i])
            for k in RETURN_WINDOWS:
                ok = i >= k and prices[i] > 0 and prices[i - k] > 0
                cols[f'{sid}_ret_{k}s'].append(prices[i] / prices[i - k] - 1 if ok else None)
        cols[f'{sid}_age_days'].append((t - date.fromisoformat(dates[i])).days)
        cols[f'{sid}_source_date'].append(dates[i])
    return cols


def _cell(value):
    if value is None:
        return ''
    return repr(value) if isinstance(value, float) else str(value)


def _write_table(path, header, columns, n_rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(header)
    for i in range(n_rows):
        writer.writerow([_cell(columns[name][i]) for name in header])
    payload = buffer.getvalue().encode('utf-8')
    write_atomic(path, payload)
    return _sha(payload)


def _teacher_global(data_dir):
    fields, rows = _read_csv(Path(data_dir) / 'teacher' / 'global' / 'global_data.csv')
    if fields != GLOBAL_COLUMNS:
        raise CrawlError('老師 global_data.csv 欄位改變')
    return rows


def _usable_series(data_dir, specs, manifest):
    usable, skipped = [], []
    for spec in specs:
        entry = manifest.get('series', {}).get(spec['series_id'], {})
        path = Path(data_dir) / 'extra' / entry.get('file', f"yfinance/{spec['series_id']}.csv")
        if entry.get('status') != 'ok' or not path.exists() or _sha(path.read_bytes()) != entry.get('sha256'):
            skipped.append(spec['series_id'])
        else:
            usable.append((spec, read_raw_series(path)))
    return usable, skipped


def build_market_features(data_dir, usable, targets, min_lag_days=1):
    data_dir = Path(data_dir)
    global_rows = _teacher_global(data_dir)
    teacher = {r['date']: r for r in global_rows}
    gdates = [r['date'] for r in global_rows]
    header = ['date', '^VIX', '^IXIC', '^GSPC', '^TWII_prev_row', '^KS11_prev_row', 'TX_OI']
    table = {'date': list(targets)}
    for column in ('^VIX', '^IXIC', '^GSPC', 'TX_OI'):
        table[column] = [teacher.get(t, {}).get(column, '') for t in targets]
    for column in ('^TWII', '^KS11'):
        values = []
        for t in targets:
            j = bisect_left(gdates, t) - 1  # 最後一個日期 < t 的老師 global 列
            values.append(global_rows[j][column] if j >= 0 else '')
        table[f'{column}_prev_row'] = values
    definitions, coverage = {}, {}
    for spec, rows in usable:
        definitions.update(feature_definitions(spec, min_lag_days))
        for name, values in series_features(spec, rows, targets, min_lag_days).items():
            header.append(name)
            table[name] = values
            coverage[name] = sum(v is not None for v in values)
    sha = _write_table(data_dir / FEATURES_FILE, header, table, len(targets))
    return header, definitions, coverage, sha


# --------------------------------------------------------------------------- 收盤報酬 lag 轉換
def k_period_returns(dates, prices, k):
    """R_k(i) = (close_i − close_{i−k}) / close_{i−k}；i−k＝同一序列往回第 k 個自己的交易日。

    兩個價格任一缺值或 <= 0 則沒有值。
    """
    out = {}
    for i in range(k, len(dates)):
        base, cur = prices[i - k], prices[i]
        if base is not None and cur is not None and base > 0 and cur > 0:
            out[dates[i]] = (cur - base) / base
    return out


def at_previous_taiwan_day(targets, values_by_date):
    """台股日 t 那一列放 i＝前一個台股交易日的值；該序列在 i 那天沒有資料就空白。"""
    return [values_by_date.get(targets[j - 1]) if j >= 1 else None for j in range(len(targets))]


def transform_sources(data_dir, usable):
    """回傳 [(feature_id, dates, prices, meta)]：19 個額外指標＋老師 5 個全球指數＋老師 100 檔個股。"""
    sources = []
    for spec, rows in usable:
        dates, prices = series_prices(spec, rows)
        sources.append((spec['series_id'], dates, prices,
                        {'source': f"yfinance {spec['ticker']}", 'name_zh': spec['name_zh'], 'group': spec['group'],
                         'price_column': 'adj_close' if spec['kind'] in ADJ_KINDS else 'close',
                         'previous_trading_day': '該序列在 Yahoo 往回第 k 個有資料的交易日'}))
    global_rows = _teacher_global(data_dir)
    for column, fid in TEACHER_TRANSFORM.items():
        sources.append((fid, [r['date'] for r in global_rows], [_num(r[column]) for r in global_rows],
                        {'source': f'teacher global_data.csv {column}', 'name_zh': TEACHER_GLOBAL[column][1],
                         'group': 'teacher_global', 'price_column': column,
                         'previous_trading_day': '老師 global 表的前 k 列（global 表只有五個序列同日都有資料才有列）',
                         'timing': TEACHER_GLOBAL[column][3]}))
    for path in sorted((Path(data_dir) / 'teacher' / 'market').glob('*.csv')):
        _, rows = _read_csv(path)
        rows = sorted((r for r in rows if r.get('date')), key=lambda r: r['date'])
        sources.append((f'stock_{path.stem}', [r['date'] for r in rows], [_num(r['etl:adj_close']) for r in rows],
                        {'source': f'teacher market/{path.name} etl:adj_close', 'name_zh': f'個股 {path.stem}',
                         'group': 'teacher_stock', 'price_column': 'etl:adj_close',
                         'previous_trading_day': '該股在老師資料中往回第 k 列'}))
    return sources


def build_transforms(data_dir, usable, targets, data_prefix='data'):
    root = Path(data_dir) / TRANSFORM_DIR
    if root.exists():
        shutil.rmtree(root)
    features = {}
    for fid, dates, prices, meta in transform_sources(data_dir, usable):
        entry = {**meta, 'files': {}}
        for lag in TRANSFORM_LAGS:
            column = f'{fid}_ret_lag{lag}'
            values = at_previous_taiwan_day(targets, k_period_returns(dates, prices, lag))
            rel = f'{TRANSFORM_DIR}/lag{lag}/{fid}.csv'
            sha = _write_table(Path(data_dir) / rel, ['date', column], {'date': targets, column: values}, len(targets))
            entry['files'][f'lag{lag}'] = {'file': f'{data_prefix}/{rel}', 'column': column, 'sha256': sha,
                                           'non_missing_rows': sum(v is not None for v in values)}
        features[fid] = entry
    return features


# --------------------------------------------------------------------------- schema
def build_schema(specs, manifest, teacher_info, targets, header, definitions, coverage, skipped, features_sha,
                 transforms, min_lag_days, series_dates, data_prefix='data'):
    def teacher_global_cols():
        return {name: {'role': role, 'description': desc, 'unit': unit, 'role_note': ROLE_NOTES[role],
                       'file': f'{data_prefix}/teacher/global/global_data.csv', **({'timing': timing} if timing else {})}
                for name, (role, desc, unit, timing) in TEACHER_GLOBAL.items()}

    def teacher_stock_cols():
        return {name: {'role': role, 'description': desc, 'unit': unit, 'role_note': ROLE_NOTES[role],
                       'file': f'{data_prefix}/teacher/market/<stock_id>.csv'}
                for name, (role, desc, unit) in TEACHER_STOCK.items()}

    target_set = set(targets)
    raw_series, missing_required = {}, list(manifest.get('missing_required', []))
    for spec in specs:
        sid = spec['series_id']
        entry = manifest.get('series', {}).get(sid, {})
        ok = sid in series_dates
        if ok:
            status = 'ok'
        elif entry.get('status') == 'ok':
            status = 'skipped_hash_mismatch'
        else:
            status = entry.get('status', 'not_downloaded')
        info = {**{k: spec[k] for k in ('ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required', 'note')},
                'status': status, 'file': f"{data_prefix}/extra/{entry['file']}" if ok else None,
                'rows': entry.get('rows'), 'date_min': entry.get('date_min'), 'date_max': entry.get('date_max'),
                'sha256': entry.get('sha256'), 'fetched_at': entry.get('fetched_at'),
                'cleaning': entry.get('cleaning'), 'last_error': (entry.get('last_attempt') or {}).get('error')}
        if ok and spec['group'] == 'M4_taiwan':
            info['missing_taiwan_trading_days'] = sorted(target_set - series_dates[sid])
        raw_series[sid] = info
        if spec['required'] and not ok and sid not in missing_required:
            missing_required.append(sid)
    teacher_market = ['^VIX', '^IXIC', '^GSPC', '^TWII_prev_row', '^KS11_prev_row', 'TX_OI']
    crawl_status = 'partial' if skipped or manifest.get('status') in (None, 'partial') else manifest['status']
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_by': 'crawler.py',
        'date_range': {'start': START, 'end_inclusive': END_INCLUSIVE},
        'readiness': 'research_assumption',
        'historical_vintage_verified': False,
        'layout': {
            f'{data_prefix}/teacher/info.json': 'Top50@Y（預測目標50股）／Top100@Y 名單',
            f'{data_prefix}/teacher/global/global_data.csv':
                f"老師全球指標；只有台／美／韓同日都交易的日期才有列（{teacher_info.get('global_rows')} 列，"
                f"缺 {teacher_info.get('global_missing_taiwan_trading_days')} 個台股交易日）",
            f'{data_prefix}/teacher/market/<stock_id>.csv': '老師個股資料（每股一檔，21欄含 y）',
            f'{data_prefix}/extra/yfinance/<series_id>.csv': 'yfinance 額外指標日K（已清理，見 extra.series.*.cleaning）',
            f'{data_prefix}/extra/manifest.json': '爬蟲紀錄：取得時間、限流設定、重試、清理、hash、失敗原因',
            f'{data_prefix}/{FEATURES_FILE}': '每台股交易日一列：老師市場欄（已處理當日收盤）＋已對齊的額外特徵',
            f'{data_prefix}/{TRANSFORM_DIR}/lag2/<feature>.csv': '每個特徵一檔：date＋第 2 期收盤報酬',
            f'{data_prefix}/{TRANSFORM_DIR}/lag5/<feature>.csv': '每個特徵一檔：date＋第 5 期收盤報酬',
        },
        'join_keys': {
            'stock': ['stock_id（檔名）', 'date'], 'market': ['date'], 'transform': ['date'],
            'how_to_join': (f'{data_prefix}/teacher/market/<stock_id>.csv、{data_prefix}/{FEATURES_FILE} 與 '
                            f'{data_prefix}/{TRANSFORM_DIR}/lag*/<feature>.csv 都以 date（台股交易日）對齊；'
                            '同日市場特徵由 50 股共用，驗證需按日期切分'),
        },
        'teacher': {
            **teacher_info,
            'global_columns': teacher_global_cols(),
            'stock_columns': teacher_stock_cols(),
            'label_columns': ['y', 'etl:adj_open', 'etl:adj_close', 'etl:adj_high', 'etl:adj_low'],
            'label_definition': 'y＝1{etl:adj_close > etl:adj_open}；盤中報酬＝adj_close/adj_open−1；官方分數 mean((2p−1)×盤中報酬)',
        },
        'extra': {
            'api': 'yfinance（Yahoo Finance chart API：query1/query2.finance.yahoo.com/v8/finance/chart）；19 個序列全部經 yfinance',
            'library_version': manifest.get('library_version'),
            'crawl_status': crawl_status,
            'crawl_status_meaning': manifest.get('status_meaning'),
            'failed_last_run': manifest.get('failed_last_run', []),
            'aborted_last_run': manifest.get('aborted_last_run', []),
            'missing_required': sorted(missing_required),
            'skipped_series_hash_mismatch': skipped,
            'excluded_teacher_tickers': list(TEACHER_TICKERS),
            'rate_limit': manifest.get('rate_limit'),
            'cleaning_rules': manifest.get('cleaning_rules'),
            'raw_columns': {
                'date': '交易所當地原生交易日',
                'open/high/low/close': '該序列單位；Yahoo 已做分割調整（股利未調整），另經本程式補正漏調的分割',
                'adj_close': '分割＋股利調整；指數／FX／殖利率／期貨等於 close',
                'volume': '股票／ETF＝股數，期貨＝口數；指數為供應商彙總量（可能非 0），FX／殖利率為 0',
            },
            'series': raw_series,
        },
        'market_features': {
            'file': f'{data_prefix}/{FEATURES_FILE}', 'sha256': features_sha, 'rows': len(targets),
            'date_min': targets[0], 'date_max': targets[-1],
            'date_definition': '老師個股檔所有台股交易日（聯集），比老師 global 表多',
            'alignment_rule': (f'額外特徵：對每個台股目標日 t，取來源交易日 s <= t − {min_lag_days} 日曆天的最後一筆；'
                               '報酬先在完整原生序列計算再對齊，不先做多市場日期交集。研究假設：美股收盤約台北 04:00–05:00，'
                               'FX／期貨日K可能在台北清晨才收盤，未經歷史發布時間驗證。'),
            'teacher_columns': teacher_market,
            'teacher_columns_definition': {
                '^VIX/^IXIC/^GSPC/TX_OI': '老師 global 同日期原值照抄（老師表缺該日則空白）；時間語意見 teacher.global_columns',
                '^TWII_prev_row/^KS11_prev_row': '最後一個日期 < t 的老師 global 列之 ^TWII／^KS11（避免當日收盤洩漏）',
            },
            'extra_columns': [c for c in header if c not in teacher_market and c != 'date'],
            'columns_in_order': header,
        },
        'extra_feature_definitions': definitions,
        'extra_feature_non_missing_rows': coverage,
        'transform': {
            'definition': {
                'confirmed_by_user': '2026-11-04 使用者確認；取代先前「往前位移 k 列的單日報酬」版本',
                'formula': 'ret_lag{k}(t) = (close_i − close_{i−k}) / close_{i−k}，k＝2、5（k 個交易日的累積報酬）',
                'i': 'i＝t 的前一個台股交易日，所以只用 t 開盤前已知的收盤；該序列在 i 那天沒有資料 → 空白',
                'i_minus_k': ('i−k＝同一序列往回第 k 個「自己的」交易日（不是台股列）；老師 global 指數＝往回 k 個 '
                              'global 列；老師個股＝該股往回 k 列'),
                'example': ('SOX close 01-16=100、01-17=102、01-21=99（01-20 美股休市）。列 01-22 用 i＝01-21：'
                            'lag2＝99/100−1＝−1.00%；列 01-21 用 i＝01-20，SOX 沒有資料 → 空白'),
                'price': '額外指標：股票／ETF 用 adj_close，其他用 close；老師個股用 etl:adj_close；老師全球指數用該欄值',
                'yields': ('殖利率（us10y、us13w）也一律用百分比報酬（使用者選擇）；us13w 在 2020-03 與 2021-02～2022-02 '
                           '接近 0，報酬會到 ±100% 以上，建模時可考慮 winsorize 或穩健縮放'),
                'missing': '空白＝缺值：序列在 i 沒有資料、往回不足 k 個交易日、或 close_i／close_{i−k} 缺值或 <= 0；不補值',
                'leakage': 'i 一定早於 t；老師美股欄已被老師位移一次，所以 teacher_vix／ixic／gspc 的值實際更舊一天',
            },
            'lags': list(TRANSFORM_LAGS),
            'rows_per_file': len(targets), 'date_min': targets[0], 'date_max': targets[-1],
            'feature_count': len(transforms),
            'files_per_lag': len(transforms),
            'features': transforms,
        },
        'project_derived_reference': {
            'note': '專案既有、由老師資料衍生的研究特徵；定義見 live-data 分支 features/schema.json，不在本資料夾重複存放',
            'stock_lags': ['stock_prev_intraday_return', 'stock_return_between_observed_rows', 'stock_prev_log_volume',
                           'stock_prev_rsi', 'stock_prev_atr_fraction', 'stock_prev_sma_deviation',
                           'stock_previous_observation_gap_days'],
            'market_m0': ['ixic_ret_1s', 'gspc_ret_1s', 'twii_ret_1s', 'ks11_ret_1s', 'vix_level', 'vix_change_points',
                          'tx_foreign_net_oi', 'tx_foreign_net_oi_change'],
        },
        'missing_value_policy': ('空白＝缺值。market_features 的額外特徵是 as-of：沿用最後一個 <= t−1 的來源交易日，'
                                 '所以休市期間會在連續台股日重複；用 age_days／source_date 判斷新舊。transform 不沿用、不補值。'),
        'float_format': '完整精度（Python repr），不四捨五入',
        'license_note': '老師 ZIP 與 Yahoo 資料的公開再散布授權未核實，僅供課程研究。',
    }


def build_outputs(data_dir, schema_path, specs, *, teacher_payload=None, teacher_source=None, keep_teacher=False,
                  min_lag_days=1):
    if min_lag_days < 1:
        raise CrawlError('min_lag_days 必須 >= 1，避免當日收盤混入特徵')
    data_dir, schema_path = Path(data_dir), Path(schema_path)
    manifest_path = data_dir / 'extra' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if teacher_payload is not None:
        teacher_info = {'source': teacher_source, **extract_teacher(teacher_payload, data_dir)}
    elif keep_teacher:
        old = {}
        if schema_path.exists():
            try:
                old = json.loads(schema_path.read_text(encoding='utf-8')).get('teacher', {})
            except ValueError:
                old = {}
        current = teacher_from_dir(data_dir)
        if old.get('members_sha256') and old['members_sha256'] != current['members_sha256']:
            raise CrawlError('data/teacher 的內容和 schema.json 記錄的老師 ZIP 不同；請改用 --live-data-ref 重新取出')
        verified = old.get('members_sha256') == current['members_sha256']
        teacher_info = {'source': old.get('source') if verified else {'kept_existing_directory': True,
                                                                     'verified_against_archive': False},
                        'archive_sha256': old.get('archive_sha256') if verified else None, **current}
    else:
        raise CrawlError('缺老師資料來源：用 --live-data-ref、--teacher-zip 或 --keep-teacher')
    targets = taiwan_target_dates(data_dir)
    usable, skipped = _usable_series(data_dir, specs, manifest)
    header, definitions, coverage, sha = build_market_features(data_dir, usable, targets, min_lag_days)
    try:
        prefix = data_dir.resolve().relative_to(schema_path.resolve().parent).as_posix()
    except ValueError:
        prefix = data_dir.as_posix()
    transforms = build_transforms(data_dir, usable, targets, data_prefix=prefix)
    series_dates = {spec['series_id']: {r[0] for r in rows} for spec, rows in usable}
    schema = build_schema(specs, manifest, teacher_info, targets, header, definitions, coverage, skipped, sha,
                          transforms, min_lag_days, series_dates, data_prefix=prefix)
    write_atomic(schema_path, _json_bytes(schema))
    return schema


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR)
    parser.add_argument('--schema', type=Path, default=SCHEMA_PATH)
    parser.add_argument('--only', action='append', metavar='SERIES_ID', help='只下載指定序列（可重複）')
    parser.add_argument('--skip-download', action='store_true', help='不連網，只用現有 raw CSV 重建')
    teacher = parser.add_mutually_exclusive_group()
    teacher.add_argument('--live-data-ref', default='origin/live-data', help='放老師 ZIP 的 git ref')
    teacher.add_argument('--teacher-zip', type=Path, help='改用本機老師 Training ZIP')
    teacher.add_argument('--keep-teacher', action='store_true', help='沿用 data/teacher 現有內容（會重新驗證）')
    parser.add_argument('--min-lag-days', type=int, default=1, help='來源交易日至少早於目標日幾個日曆天')
    rl = RateLimitPolicy()
    parser.add_argument('--min-interval', type=float, default=rl.min_interval_seconds, help='每個 HTTP 請求間最小間隔秒數')
    parser.add_argument('--jitter', type=float, default=rl.jitter_seconds, help='每次間隔再加 0～N 秒隨機抖動')
    parser.add_argument('--max-retries', type=int, default=rl.max_retries, help='每檔暫時性錯誤的最多重試次數')
    parser.add_argument('--backoff-base', type=float, default=rl.backoff_base_seconds, help='首次退避秒數（每次加倍）')
    parser.add_argument('--backoff-max', type=float, default=rl.backoff_max_seconds, help='退避上限與限流冷卻秒數')
    parser.add_argument('--rate-limited-multiplier', type=float, default=rl.rate_limited_backoff_multiplier,
                        help='被 Yahoo 限流（429）時退避時間倍率')
    parser.add_argument('--timeout', type=float, default=rl.request_timeout_seconds,
                        help='chart 歷史資料請求的逾時秒數（yfinance 的時區／cookie 請求用自己的 10／30 秒）')
    parser.add_argument('--cache-dir', type=Path, default=Path.home() / '.cache' / 'finpred-yfinance',
                        help='yfinance 時區快取（放在 data/ 之外）')
    args = parser.parse_args(argv)
    try:
        if not args.skip_download:
            policy = RateLimitPolicy(args.min_interval, args.jitter, args.max_retries, args.backoff_base,
                                     args.backoff_max, args.rate_limited_multiplier, args.timeout)
            limiter = RateLimiter(policy.min_interval_seconds, policy.jitter_seconds)
            fetch, version = yfinance_fetcher(limiter, policy.request_timeout_seconds, args.cache_dir)
            crawl(SPECS, args.data_dir / 'extra', fetch, library_version=version, only=args.only, policy=policy)
        payload = source = None
        if args.teacher_zip:
            payload = args.teacher_zip.read_bytes()
            source = {'zip_file': args.teacher_zip.name, 'object_sha256': hashlib.sha256(payload).hexdigest()}
        elif not args.keep_teacher:
            payload, source = live_data_training_zip(ROOT, args.live_data_ref)
        schema = build_outputs(args.data_dir, args.schema, SPECS, teacher_payload=payload, teacher_source=source,
                               keep_teacher=args.keep_teacher, min_lag_days=args.min_lag_days)
    except (CrawlError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    extra, m, tr = schema['extra'], schema['market_features'], schema['transform']
    print(json.dumps({'crawl_status': extra['crawl_status'], 'missing_required': extra['missing_required'],
                      'series_ok': [k for k, v in extra['series'].items() if v['status'] == 'ok'],
                      'series_not_ok': {k: v['status'] for k, v in extra['series'].items() if v['status'] != 'ok'},
                      'failed_last_run': extra['failed_last_run'], 'aborted_last_run': extra['aborted_last_run'],
                      'market_rows': m['rows'], 'market_columns': len(m['columns_in_order']),
                      'transform_features': tr['feature_count'], 'transform_files': tr['feature_count'] * len(tr['lags']),
                      'date_min': m['date_min'], 'date_max': m['date_max']}, ensure_ascii=False, indent=2))
    if extra['missing_required']:
        return 1
    return 3 if extra['failed_last_run'] or extra['aborted_last_run'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
