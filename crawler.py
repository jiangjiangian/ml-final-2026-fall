#!/usr/bin/env python3
"""yfinance 額外指標爬蟲 → data/ 資料夾整合 → schema.json。

1. 用 yfinance（https://github.com/ranaroussi/yfinance）下載老師 global_data 以外的
   額外指標與台幣匯率（TWD=X），範圍 2020-01-01 ～ 2026-08-31，逐檔「限流」下載。
2. 從 live-data 分支取出老師 Training ZIP（核對 sha256），原樣放入 data/teacher/。
3. 產生 data/features/market_features.csv：每個台股交易日一列＝老師 global 欄位＋額外特徵。
4. 產生 schema.json：老師全部欄位＋額外指標全部欄位的定義、單位與 lag 規則。

限流：單執行緒逐檔請求；每次請求「結束後」至少間隔 --min-interval 秒＋0～--jitter 秒隨機抖動；
暫時性錯誤指數退避重試，Yahoo 回 429／YFRateLimitError 時退避時間再乘倍率；
未知 ticker 等永久錯誤不重試；yfinance 內建重試關閉，避免重試疊加成突發流量。

用法（在 repo 根目錄）：
    pip install yfinance==1.7.0
    git fetch origin live-data
    python crawler.py                      # 下載＋整合＋schema
    python crawler.py --skip-download      # 只用現有 raw CSV 重建 features 與 schema
    python crawler.py --only usd_twd --only sox
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
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
SCHEMA_VERSION = 'data-folder-schema-v1'
MANIFEST_VERSION = 'yfinance-extra-manifest-v1'
FEATURES_FILE = 'features/market_features.csv'

# --------------------------------------------------------------------------- 額外指標清單
# kind: index / stock / etf / fx / fx_index / yield_percent / futures
TEACHER_TICKERS = ('^VIX', '^IXIC', '^GSPC', '^TWII', '^KS11')  # 老師 global_data 已有，排除
SERIES = [
    ('sox', '^SOX', 'PHLX Semiconductor Index', '費城半導體指數', 'M1_semiconductor', 'index', 'index_point', True, None),
    ('tsm_adr', 'TSM', 'Taiwan Semiconductor ADR', '台積電ADR', 'M2_overseas_stock', 'stock', 'USD', True, None),
    ('nvda', 'NVDA', 'NVIDIA', '輝達', 'M2_overseas_stock', 'stock', 'USD', True, None),
    ('usd_twd', 'TWD=X', 'USD/TWD exchange rate', '美元兌新台幣匯率', 'M3_fx_rates', 'fx', 'TWD_per_USD', True,
     '報價＝1美元兌多少台幣；報酬為正＝台幣貶值。Yahoo FX 日K依倫敦／GMT日界，不是台北收盤或定盤。'),
    ('dxy', 'DX-Y.NYB', 'US Dollar Index', '美元指數', 'M3_fx_rates', 'fx_index', 'index_point', False, None),
    ('us10y', '^TNX', 'CBOE 10-Year Treasury Yield', '美國10年期公債殖利率', 'M3_fx_rates', 'yield_percent',
     'percent_per_annum', True, '以百分比報價（4.25＝4.25%）；變化用基點，不是債券價格報酬。'),
    ('us13w', '^IRX', '13-Week Treasury Bill Yield', '美國13週國庫券殖利率', 'M3_fx_rates', 'yield_percent',
     'percent_per_annum', False, None),
    ('etf_006201', '006201.TWO', 'Yuanta TPEx 50 ETF', '元大富櫃50（櫃買市場代理）', 'M4_taiwan', 'etf', 'TWD', False,
     'Yahoo 沒有櫃買指數本身（^TWOII／^TWO／^TPEX 皆查無）；以追蹤富櫃50指數的 ETF 代理櫃買市場。'),
    ('etf_0050', '0050.TW', 'Yuanta Taiwan Top 50 ETF', '元大台灣50（台灣50指數代理）', 'M4_taiwan', 'etf', 'TWD', False,
     'ETF 代理，不是台灣50指數本身；報酬用含分割／股利調整的 adj_close。'),
    ('etf_0052', '0052.TW', 'Fubon Taiwan Technology ETF', '富邦科技（電子類代理）', 'M4_taiwan', 'etf', 'TWD', False,
     '電子類股代理，不是證交所電子類指數。'),
    ('etf_0055', '0055.TW', 'Yuanta MSCI Taiwan Financials ETF', '元大MSCI金融（金融類代理）', 'M4_taiwan', 'etf', 'TWD',
     False, '金融類股代理，不是證交所金融保險類指數。'),
    ('dji', '^DJI', 'Dow Jones Industrial Average', '道瓊工業指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('n225', '^N225', 'Nikkei 225', '日經225指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('hsi', '^HSI', 'Hang Seng Index', '恒生指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('sse', '000001.SS', 'SSE Composite Index', '上證綜合指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('stoxx50e', '^STOXX50E', 'EURO STOXX 50', '歐洲斯托克50指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('gdaxi', '^GDAXI', 'DAX', '德國DAX指數', 'M5_global_index', 'index', 'index_point', False, None),
    ('wti', 'CL=F', 'WTI Crude Oil Futures', 'WTI原油期貨', 'M5_commodity', 'futures', 'USD_per_barrel', False,
     '連續近月合約；2020-04-20 結算價為負，碰到非正價格的報酬保持空值。'),
    ('gold', 'GC=F', 'Gold Futures', '黃金期貨', 'M5_commodity', 'futures', 'USD_per_troy_ounce', False, None),
]
SPECS = [dict(zip(('series_id', 'ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required', 'note'), row))
         for row in SERIES]
SIGNED_KINDS = {'futures', 'yield_percent'}   # 原始價格可為 0 或負
ADJ_KINDS = {'stock', 'etf'}                  # 報酬用 adj_close
LEVEL_KINDS = {'fx', 'fx_index'}              # 另輸出水準欄
RETURN_WINDOWS, YIELD_WINDOWS = (1, 5, 20), (1, 5)
RAW_COLUMNS = ('date', 'open', 'high', 'low', 'close', 'adj_close', 'volume')
YAHOO_COLUMNS = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'adj_close': 'Adj Close',
                 'volume': 'Volume'}
RATE_LIMIT_ERRORS = {'YFRateLimitError'}
PERMANENT_ERRORS = {'YFTickerMissingError', 'YFPricesMissingError', 'YFTzMissingError', 'YFInvalidPeriodError',
                    'YFNotImplementedError'}

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
TEACHER_GLOBAL = {
    'date': ('key', '台股交易日（老師 global 表的列日期）', 'ISO date'),
    '^VIX': ('market', 'CBOE VIX 波動率指數', 'index_point'),
    '^IXIC': ('market', 'Nasdaq Composite 那斯達克綜合指數', 'index_point'),
    '^GSPC': ('market', 'S&P 500 標普500指數', 'index_point'),
    '^TWII': ('market', '台灣加權股價指數', 'index_point'),
    '^KS11': ('market', 'KOSPI 韓國綜合指數', 'index_point'),
    'TX_OI': ('market', '台指期外資淨未平倉口數（多方減空方，可為負）', 'contracts'),
}
GLOBAL_TIMING = ('老師表的美股欄位已對齊到台股日期（已含位移）；^TWII／^KS11 可能是目標日當日收盤，'
                 '09:00 前尚不可知。使用前需依專案 MARKET_FEATURES.md 對齊，不可再盲目 shift。')
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
    'market': '全市場共用；見 timing',
    'outcome_same_day': '目標日當日價格＝答案的一部分；只能用前一觀測（lag）',
    'raw_same_day': '收盤後才知道；只能用前一觀測（lag）',
    'label': '只用於訓練／評分，絕不放入輸入',
}


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
    return 'transient'


def backoff_delay(attempt, policy, kind, rng=random.random):
    delay = policy.backoff_base_seconds * (2 ** (attempt - 1))
    if kind == 'rate_limited':
        delay *= policy.rate_limited_backoff_multiplier
    return min(policy.backoff_max_seconds, delay) + policy.jitter_seconds * rng()


def fetch_with_retry(fetch, spec, start, end_exclusive, limiter, policy, *, sleep=time.sleep, rng=random.random):
    events = []
    for attempt in range(1, policy.max_retries + 2):
        try:
            with limiter:
                rows = fetch(spec['ticker'], start.isoformat(), end_exclusive.isoformat())
            return rows, attempt, events
        except Exception as exc:  # 依類型分流；KeyboardInterrupt 不在此攔截
            kind = classify_error(exc)
            events.append({'attempt': attempt, 'error_class': type(exc).__name__, 'kind': kind,
                           'message': str(exc)[:200]})
            if kind == 'permanent' or attempt > policy.max_retries:
                error = CrawlError(f"{spec['series_id']}: {type(exc).__name__}: {str(exc)[:200]}")
                error.events = events
                raise error from exc
            delay = backoff_delay(attempt, policy, kind, rng)
            events[-1]['backoff_seconds'] = round(delay, 3)
            sleep(delay)
    raise AssertionError('unreachable')


# --------------------------------------------------------------------------- 下載與驗證
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
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def crawl(specs, extra_dir, fetch, *, start=START, end_inclusive=END_INCLUSIVE, library_version='unknown',
          only=None, policy=None, sleep=time.sleep, clock=time.monotonic, rng=random.random, now=None):
    """逐檔限流下載，寫 extra/yfinance/<series_id>.csv 與 extra/manifest.json。

    某檔失敗時保留上一次成功的檔案與紀錄（附 last_attempt），不會默默消失。
    """
    extra_dir = Path(extra_dir)
    start_d, end_d = _iso(start, 'start'), _iso(end_inclusive, 'end')
    end_exclusive = end_d + timedelta(days=1)  # yfinance 的 end 不含當天
    policy = policy or RateLimitPolicy()
    limiter = RateLimiter(policy.min_interval_seconds, policy.jitter_seconds, clock=clock, sleep=sleep, rng=rng)
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
    failed = []
    for spec in selected:
        sid = spec['series_id']
        meta = {k: spec[k] for k in ('ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required')}
        print(f'[crawl] {sid:<10} {spec["ticker"]}', file=sys.stderr, flush=True)
        try:
            raw, attempts, events = fetch_with_retry(fetch, spec, start_d, end_exclusive, limiter, policy,
                                                     sleep=sleep, rng=rng)
            rows, dropped = validate_rows(raw, spec, start_d, end_d)
            payload = rows_to_csv(rows)
            write_atomic(extra_dir / 'yfinance' / f'{sid}.csv', payload)
            entries[sid] = {**meta, 'status': 'ok', 'file': f'yfinance/{sid}.csv', 'sha256': _sha(payload),
                            'rows': len(rows), 'dropped_rows': dropped, 'date_min': rows[0]['date'],
                            'date_max': rows[-1]['date'], 'fetched_at': run_started, 'attempts': attempts,
                            'retry_events': events}
        except CrawlError as exc:
            failed.append(sid)
            print(f'[crawl] {sid} 失敗：{exc}', file=sys.stderr, flush=True)
            attempt = {'status': 'failed', 'at': run_started, 'error': str(exc)[:300],
                       'retry_events': getattr(exc, 'events', [])}
            old, old_file = entries.get(sid), extra_dir / 'yfinance' / f'{sid}.csv'
            if (old and old.get('status') == 'ok' and old_file.exists()
                    and _sha(old_file.read_bytes()) == old.get('sha256')):
                entries[sid] = {**old, 'last_attempt': attempt}
            else:
                old_file.unlink(missing_ok=True)
                entries[sid] = {**meta, 'status': 'failed', 'last_attempt': attempt}
    ordered = {s['series_id']: entries[s['series_id']] for s in specs if s['series_id'] in entries}
    missing_required = sorted(s['series_id'] for s in specs
                              if s['required'] and ordered.get(s['series_id'], {}).get('status') != 'ok')
    complete = len(ordered) == len(specs) and all(v.get('status') == 'ok' for v in ordered.values())
    manifest = {
        'schema_version': MANIFEST_VERSION, 'source': 'Yahoo Finance via yfinance',
        'library': 'https://github.com/ranaroussi/yfinance', 'library_version': library_version,
        'terms_note': 'Yahoo 非官方介面，僅供課程研究；再散布授權未核實。',
        'range': {'start': start_d.isoformat(), 'end_inclusive': end_d.isoformat(),
                  'request_end_exclusive': end_exclusive.isoformat()},
        'request_options': {'interval': '1d', 'auto_adjust': False, 'actions': False, 'repair': False},
        'date_semantics': 'date＝該日K的交易所當地原生交易日；不是發布或可用時間',
        'rate_limit': {**asdict(policy), 'mode': 'sequential_single_thread', 'requests_this_run': limiter.requests,
                       'paced_sleep_seconds_this_run': round(limiter.slept_seconds, 3)},
        'run_started_at': run_started, 'series_requested_this_run': [s['series_id'] for s in selected],
        'failed_this_run': failed, 'missing_required': missing_required,
        'status': 'complete' if complete else 'partial', 'series': ordered,
    }
    write_atomic(manifest_path, _json_bytes(manifest))
    return manifest


def yfinance_fetcher(timeout=30.0, cache_dir=None):
    """回傳 (fetch, version)；yfinance 自己的重試關閉，由本程式統一限流。"""
    import yfinance as yf

    config = getattr(yf, 'config', None)
    if config is not None:
        config.debug.hide_exceptions = False  # 被限流時拋出例外，而不是回傳空表
        config.network.retries = 0
    if cache_dir is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))

    def fetch(ticker, start, end_exclusive):
        frame = yf.Ticker(ticker).history(start=start, end=end_exclusive, interval='1d', auto_adjust=False,
                                          actions=False, repair=False, timeout=timeout)
        if frame is None or len(frame) == 0:
            raise CrawlError(f'{ticker}: 空的歷史資料')
        return frame_to_rows(frame)

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
    if _sha(catalog) != pointer['catalog_sha256']:
        raise CrawlError('live-data catalog hash 不符')
    source = json.loads(catalog)['sources']['course-training']
    digest = source['latest_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise CrawlError('Training 物件 digest 格式錯誤')
    payload = show(f'objects/{digest}.zip')
    if _sha(payload) != digest:
        raise CrawlError('老師 Training ZIP hash 不符')
    return payload, {'live_data_ref': ref, 'catalog_sha256': pointer['catalog_sha256'],
                     'object': f'live-data:objects/{digest}.zip', 'source_fetched_at': source.get('fetched_at')}


def _csv_rows(payload):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
    return tuple(reader.fieldnames or ()), list(reader)


def extract_teacher(payload, data_dir, expected_stocks=100, expected_targets=50):
    """驗證後把老師 ZIP 原樣（逐位元組）放入 data/teacher/。"""
    teacher = Path(data_dir) / 'teacher'
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        stocks = sorted(n for n in names if re.fullmatch(r'data/market/[0-9A-Za-z]+\.csv', n))
        if set(names) != set(stocks) | {'data/global/global_data.csv', 'data/info.json'}:
            raise CrawlError('老師 ZIP 成員不符預期')
        if len(stocks) != expected_stocks:
            raise CrawlError('老師 ZIP 股票數不符預期')
        info = json.loads(archive.read('data/info.json').decode('utf-8-sig'))
        ids = [PurePosixPath(n).stem for n in stocks]
        if set(info) != {'Top50@Y', 'Top100@Y'} or set(map(str, info['Top100@Y'])) != set(ids) \
                or len(info['Top50@Y']) != expected_targets:
            raise CrawlError('info.json 名單與 ZIP 不一致')
        fields, global_rows = _csv_rows(archive.read('data/global/global_data.csv'))
        if fields != GLOBAL_COLUMNS:
            raise CrawlError('global_data.csv 欄位改變')
        stock_dates, stock_rows = set(), 0
        for name in stocks:
            fields, rows = _csv_rows(archive.read(name))
            if fields != STOCK_COLUMNS:
                raise CrawlError(f'{name} 欄位改變')
            stock_dates.update(r['date'] for r in rows)
            stock_rows += len(rows)
        if teacher.exists():
            shutil.rmtree(teacher)
        for name in names:
            write_atomic(teacher.joinpath(*PurePosixPath(name).parts[1:]), archive.read(name))
    gdates = [r['date'] for r in global_rows]
    return {'archive_sha256': _sha(payload), 'stock_count': len(stocks), 'target_stock_count': len(info['Top50@Y']),
            'stock_rows': stock_rows, 'stock_date_min': min(stock_dates), 'stock_date_max': max(stock_dates),
            'global_rows': len(global_rows), 'global_date_min': min(gdates), 'global_date_max': max(gdates)}


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
            'lag_rule': (f's＝{spec["ticker"]} 最後一個 session_date <= target_date − {min_lag_days} 日曆天的原生交易日；'
                         'k 期＝往回 k 個原生交易日，不是台股列位移'),
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
                                      'description': f'{spec["name_zh"]} {k} 個原生交易日報酬{note}',
                                      'missing_policy': '前 k 期不存在或任一價格 <= 0 時為空值'}
    out[f'{sid}_age_days'] = {**base, 'formula': 'target_date − s', 'unit': 'calendar_days',
                              'description': '所用來源交易日距目標日的日曆天數（新鮮度）'}
    out[f'{sid}_source_date'] = {**base, 'formula': 's', 'unit': 'ISO date', 'role': 'trace_not_model_input',
                                 'description': '實際採用的來源原生交易日（追溯用，不是模型輸入）'}
    return out


def series_features(spec, rows, targets, min_lag_days=1):
    """先在完整原生序列算報酬，再對齊到每個台股目標日。"""
    sid, kind = spec['series_id'], spec['kind']
    dates = [r[0] for r in rows]
    prices = [(r[2] if kind in ADJ_KINDS and r[2] is not None else r[1]) for r in rows]
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


def _feature_cell(value):
    if value is None:
        return ''
    return repr(round(value, 12)) if isinstance(value, float) else str(value)


def build_market_features(data_dir, specs, manifest, targets, min_lag_days=1):
    data_dir = Path(data_dir)
    fields, global_rows = _read_csv(data_dir / 'teacher' / 'global' / 'global_data.csv')
    if fields != GLOBAL_COLUMNS:
        raise CrawlError('老師 global_data.csv 欄位改變')
    teacher = {r['date']: r for r in global_rows}
    header = list(GLOBAL_COLUMNS)
    table = {'date': list(targets), **{c: [teacher.get(t, {}).get(c, '') for t in targets] for c in GLOBAL_COLUMNS[1:]}}
    definitions, coverage, skipped = {}, {}, []
    for spec in specs:
        entry = manifest.get('series', {}).get(spec['series_id'], {})
        path = data_dir / 'extra' / entry.get('file', f"yfinance/{spec['series_id']}.csv")
        if entry.get('status') != 'ok' or not path.exists() or _sha(path.read_bytes()) != entry.get('sha256'):
            skipped.append(spec['series_id'])
            continue
        definitions.update(feature_definitions(spec, min_lag_days))
        for name, values in series_features(spec, read_raw_series(path), targets, min_lag_days).items():
            header.append(name)
            table[name] = values
            if not name.endswith('_source_date'):
                coverage[name] = sum(v is not None for v in values)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(header)
    for i in range(len(targets)):
        writer.writerow([_feature_cell(table[name][i]) for name in header])
    payload = buffer.getvalue().encode('utf-8')
    write_atomic(data_dir / FEATURES_FILE, payload)
    return header, definitions, coverage, skipped, _sha(payload)


# --------------------------------------------------------------------------- schema
def build_schema(specs, manifest, teacher_info, targets, header, definitions, coverage, skipped, features_sha,
                 min_lag_days, data_prefix='data'):
    def teacher_cols(mapping, file):
        return {name: {'role': role, 'description': desc, 'unit': unit, 'file': file, 'role_note': ROLE_NOTES[role],
                       **({'timing': GLOBAL_TIMING} if role == 'market' else {})}
                for name, (role, desc, unit) in mapping.items()}

    raw_series = {}
    for spec in specs:
        entry = manifest.get('series', {}).get(spec['series_id'], {})
        raw_series[spec['series_id']] = {
            **{k: spec[k] for k in ('ticker', 'name', 'name_zh', 'group', 'kind', 'unit', 'required', 'note')},
            'status': entry.get('status', 'not_downloaded'),
            'file': f"{data_prefix}/extra/{entry['file']}" if entry.get('status') == 'ok' else None,
            'rows': entry.get('rows'), 'date_min': entry.get('date_min'), 'date_max': entry.get('date_max'),
            'sha256': entry.get('sha256'), 'fetched_at': entry.get('fetched_at'),
            'last_error': (entry.get('last_attempt') or {}).get('error')}
    teacher_market = list(GLOBAL_COLUMNS[1:])
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_by': 'crawler.py',
        'date_range': {'start': START, 'end_inclusive': END_INCLUSIVE},
        'readiness': 'research_assumption',
        'historical_vintage_verified': False,
        'layout': {
            f'{data_prefix}/teacher/info.json': 'Top50@Y（預測目標50股）／Top100@Y 名單',
            f'{data_prefix}/teacher/global/global_data.csv': '老師全球指標（每台股日一列）',
            f'{data_prefix}/teacher/market/<stock_id>.csv': '老師個股資料（每股一檔，21欄含 y）',
            f'{data_prefix}/extra/yfinance/<series_id>.csv': 'yfinance 額外指標原生日K（date, open, high, low, close, adj_close, volume）',
            f'{data_prefix}/extra/manifest.json': '爬蟲紀錄：取得時間、限流設定、重試、hash、失敗原因',
            f'{data_prefix}/{FEATURES_FILE}': '每台股交易日一列：老師 global 欄位＋已對齊的額外特徵',
        },
        'join_keys': {
            'stock': ['stock_id（檔名）', 'date'], 'market': ['date'],
            'how_to_join': f'{data_prefix}/teacher/market/<stock_id>.csv 的 date ＝ {data_prefix}/{FEATURES_FILE} 的 date；'
                           '同日市場特徵由 50 股共用，驗證需按日期切分',
        },
        'teacher': {
            'source': teacher_info.get('source'),
            **{k: v for k, v in teacher_info.items() if k != 'source'},
            'global_columns': teacher_cols(TEACHER_GLOBAL, f'{data_prefix}/teacher/global/global_data.csv'),
            'stock_columns': teacher_cols(TEACHER_STOCK, f'{data_prefix}/teacher/market/<stock_id>.csv'),
            'label_columns': ['y', 'etl:adj_open', 'etl:adj_close', 'etl:adj_high', 'etl:adj_low'],
            'label_definition': 'y＝1{etl:adj_close > etl:adj_open}；盤中報酬＝adj_close/adj_open−1；官方分數 mean((2p−1)×盤中報酬)',
        },
        'extra': {
            'source': 'Yahoo Finance via yfinance (https://github.com/ranaroussi/yfinance)',
            'library_version': manifest.get('library_version'),
            'crawl_status': manifest.get('status', 'not_run'),
            'missing_required': manifest.get('missing_required', [s['series_id'] for s in specs if s['required']]),
            'excluded_teacher_tickers': list(TEACHER_TICKERS),
            'rate_limit': manifest.get('rate_limit') or {**asdict(RateLimitPolicy()), 'mode': 'sequential_single_thread'},
            'raw_columns': {'date': '交易所當地原生交易日', 'open/high/low/close': '該序列單位',
                            'adj_close': '含分割／股利調整（指數＝close）', 'volume': '股數或口數；指數／FX 為 0 或空'},
            'series': raw_series,
        },
        'market_features': {
            'file': f'{data_prefix}/{FEATURES_FILE}', 'sha256': features_sha, 'rows': len(targets),
            'date_min': targets[0], 'date_max': targets[-1], 'row_dates': '老師個股檔所有台股交易日（聯集）',
            'alignment_rule': (f'額外特徵：對每個台股目標日 t，取來源原生交易日 s <= t − {min_lag_days} 日曆天的最後一筆；'
                               '報酬先在完整原生序列計算再對齊，不先做多市場日期交集。研究假設：美股收盤約台北 04:00–05:00，'
                               'FX／期貨日K可能在台北清晨才收盤，未經歷史發布時間驗證。'),
            'teacher_columns': teacher_market,
            'teacher_columns_note': '老師 global 原值照抄（該日缺列則空白）；時間語意見 teacher.global_columns.*.timing',
            'extra_columns': [c for c in header if c not in GLOBAL_COLUMNS],
            'skipped_series': skipped,
            'columns_in_order': header,
        },
        'extra_feature_definitions': definitions,
        'extra_feature_non_missing_rows': coverage,
        'project_derived_reference': {
            'note': '專案既有、由老師資料衍生的研究特徵；定義見 live-data 分支 features/schema.json，不在本資料夾重複存放',
            'stock_lags': ['stock_prev_intraday_return', 'stock_return_between_observed_rows', 'stock_prev_log_volume',
                           'stock_prev_rsi', 'stock_prev_atr_fraction', 'stock_prev_sma_deviation',
                           'stock_previous_observation_gap_days'],
            'market_m0': ['ixic_ret_1s', 'gspc_ret_1s', 'twii_ret_1s', 'ks11_ret_1s', 'vix_level', 'vix_change_points',
                          'tx_foreign_net_oi', 'tx_foreign_net_oi_change'],
        },
        'missing_value_policy': '空白＝缺值；不向前補值、不用未來值補洞',
        'license_note': '老師 ZIP 與 Yahoo 資料的公開再散布授權未核實，僅供課程研究。',
    }


def build_outputs(data_dir, schema_path, specs, *, teacher_payload=None, teacher_source=None, min_lag_days=1):
    if min_lag_days < 1:
        raise CrawlError('min_lag_days 必須 >= 1，避免當日收盤混入特徵')
    data_dir, schema_path = Path(data_dir), Path(schema_path)
    manifest_path = data_dir / 'extra' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if teacher_payload is not None:
        teacher_info = {'source': teacher_source, **extract_teacher(teacher_payload, data_dir)}
    elif schema_path.exists() and (data_dir / 'teacher' / 'global' / 'global_data.csv').exists():
        old = json.loads(schema_path.read_text(encoding='utf-8'))['teacher']
        teacher_info = {k: v for k, v in old.items() if k not in ('global_columns', 'stock_columns', 'label_columns',
                                                                 'label_definition')}
    else:
        raise CrawlError('缺老師資料：請 git fetch origin live-data，或用 --teacher-zip')
    targets = taiwan_target_dates(data_dir)
    header, definitions, coverage, skipped, sha = build_market_features(data_dir, specs, manifest, targets, min_lag_days)
    try:
        prefix = data_dir.resolve().relative_to(schema_path.resolve().parent).as_posix()
    except ValueError:
        prefix = data_dir.as_posix()
    schema = build_schema(specs, manifest, teacher_info, targets, header, definitions, coverage, skipped, sha,
                          min_lag_days, data_prefix=prefix)
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
    teacher.add_argument('--keep-teacher', action='store_true', help='沿用 data/teacher 現有內容')
    parser.add_argument('--min-lag-days', type=int, default=1, help='來源交易日至少早於目標日幾個日曆天')
    rl = RateLimitPolicy()
    parser.add_argument('--min-interval', type=float, default=rl.min_interval_seconds, help='請求間最小間隔秒數')
    parser.add_argument('--jitter', type=float, default=rl.jitter_seconds, help='每次間隔再加 0～N 秒隨機抖動')
    parser.add_argument('--max-retries', type=int, default=rl.max_retries, help='每檔暫時性錯誤的最多重試次數')
    parser.add_argument('--backoff-base', type=float, default=rl.backoff_base_seconds, help='首次退避秒數（每次加倍）')
    parser.add_argument('--backoff-max', type=float, default=rl.backoff_max_seconds, help='退避上限秒數')
    parser.add_argument('--rate-limited-multiplier', type=float, default=rl.rate_limited_backoff_multiplier,
                        help='被 Yahoo 限流（429）時退避時間倍率')
    parser.add_argument('--timeout', type=float, default=rl.request_timeout_seconds, help='單次請求逾時秒數')
    parser.add_argument('--cache-dir', type=Path, default=Path.home() / '.cache' / 'finpred-yfinance',
                        help='yfinance 時區快取（放在 data/ 之外）')
    args = parser.parse_args(argv)
    try:
        if not args.skip_download:
            policy = RateLimitPolicy(args.min_interval, args.jitter, args.max_retries, args.backoff_base,
                                     args.backoff_max, args.rate_limited_multiplier, args.timeout)
            fetch, version = yfinance_fetcher(policy.request_timeout_seconds, args.cache_dir)
            crawl(SPECS, args.data_dir / 'extra', fetch, library_version=version, only=args.only, policy=policy)
        payload = source = None
        if args.teacher_zip:
            payload = args.teacher_zip.read_bytes()
            source = {'zip_file': args.teacher_zip.name, 'object_sha256': _sha(payload)}
        elif not args.keep_teacher:
            payload, source = live_data_training_zip(ROOT, args.live_data_ref)
        schema = build_outputs(args.data_dir, args.schema, SPECS, teacher_payload=payload, teacher_source=source,
                               min_lag_days=args.min_lag_days)
    except (CrawlError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    extra, m = schema['extra'], schema['market_features']
    print(json.dumps({'crawl_status': extra['crawl_status'], 'missing_required': extra['missing_required'],
                      'series_ok': [k for k, v in extra['series'].items() if v['status'] == 'ok'],
                      'series_failed': [k for k, v in extra['series'].items() if v['status'] == 'failed'],
                      'series_not_downloaded': [k for k, v in extra['series'].items()
                                                if v['status'] == 'not_downloaded'],
                      'market_rows': m['rows'], 'market_columns': len(m['columns_in_order']),
                      'date_min': m['date_min'], 'date_max': m['date_max']}, ensure_ascii=False, indent=2))
    return 1 if extra['missing_required'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
