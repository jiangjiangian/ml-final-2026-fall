"""Bounded Yahoo chart snapshots for private research, not historical vintages.

Yahoo's public chart endpoint is usable here but is not a contracted production
API. Raw prices, provider timestamps and adjustments are retained in the payload;
no publication time or complete session calendar is inferred by this adapter.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from finpred.data.snapshots import snapshot_bytes

HISTORY_SERIES = {
    "ixic": ("^IXIC", "index_point"),
    "gspc": ("^GSPC", "index_point"),
    "twii": ("^TWII", "index_point"),
    "ks11": ("^KS11", "index_point"),
    "vix": ("^VIX", "index_point"),
    "sox": ("^SOX", "index_point"),
    "tsm_adr": ("TSM", "USD"),
    "nvda": ("NVDA", "USD"),
}
MAX_HISTORY_BYTES = 8 * 1024 * 1024
TWSE_SECTOR_NAMES = {"電子工業類指數": "tw_electronics", "半導體類指數": "tw_semiconductor",
                     "金融保險類指數": "tw_financials"}


def parse_twse_sector_snapshot(payload):
    """Parse official daily sector levels; this is not a historical series."""
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_HISTORY_BYTES:
        raise ValueError("empty or oversized sector response")
    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError
        result, seen = [], set()
        for row in data:
            name = row.get("指數")
            if name not in TWSE_SECTOR_NAMES:
                continue
            raw_date = row["日期"]
            if not isinstance(raw_date, str) or len(raw_date) != 7 or not raw_date.isdigit():
                raise ValueError
            day = date(int(raw_date[:3]) + 1911, int(raw_date[3:5]), int(raw_date[5:])).isoformat()
            value = float(row["收盤指數"].replace(",", ""))
            if not math.isfinite(value) or value <= 0 or name in seen:
                raise ValueError
            seen.add(name)
            result.append({"series_id": TWSE_SECTOR_NAMES[name], "provider_name": name,
                           "provider_observation_date": day, "value": value, "unit": "index_point"})
        if seen != set(TWSE_SECTOR_NAMES):
            raise ValueError
        if len({r["provider_observation_date"] for r in result}) != 1:
            raise ValueError
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("malformed or incomplete TWSE sector snapshot") from None


def download_twse_sector_snapshot(root, *, session=None):
    """Acquire one current official snapshot for prospective version collection."""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
    owned, client, response = session is None, session or requests.Session(), None
    try:
        response = client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(10, 45),
                              verify=True, allow_redirects=False, stream=True)
        if response.status_code != 200:
            raise ValueError(f"sector source returned HTTP {response.status_code}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_HISTORY_BYTES:
                raise ValueError("sector response exceeds size limit")
            chunks.append(chunk)
        raw = b"".join(chunks)
        rows = parse_twse_sector_snapshot(raw)
        return snapshot_bytes(raw, root, "twse-sectors", url, ".json", {
            "tls_verification": True, "audit": {"selected_series": [r["series_id"] for r in rows],
            "date": rows[0]["provider_observation_date"], "selected_row_count": len(rows)},
            "readiness": "current_raw_snapshot_only", "historical_vintage_verified": False,
            "limitation": "Official current sector levels; not a verified full-history interface. "
                          "One level cannot produce a native-session return. Keep future acquisitions as new versions."})
    except requests.RequestException:
        raise ValueError("sector network/TLS request failed") from None
    finally:
        if response is not None:
            response.close()
        if owned:
            client.close()


def parse_chart_history(payload, series_id):
    """Return provider close records on the provider's local observation date."""
    if series_id not in HISTORY_SERIES or not isinstance(payload, bytes):
        raise ValueError("unknown history series or invalid payload")
    if not payload or len(payload) > MAX_HISTORY_BYTES:
        raise ValueError("empty or oversized history response")
    try:
        chart = json.loads(payload)["chart"]
        if chart.get("error") or len(chart["result"]) != 1:
            raise ValueError
        result = chart["result"][0]
        symbol, unit = HISTORY_SERIES[series_id]
        if result["meta"]["symbol"] != symbol:
            raise ValueError
        zone = ZoneInfo(result["meta"]["exchangeTimezoneName"])
        timestamps = result["timestamp"]
        prices = result["indicators"]["quote"][0]["close"]
        if not timestamps or len(timestamps) != len(prices):
            raise ValueError
        rows = []
        for timestamp, value in zip(timestamps, prices):
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
                raise ValueError
            instant = datetime.fromtimestamp(timestamp, timezone.utc)
            day = instant.astimezone(zone).date().isoformat()
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError
                value = float(value)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
            rows.append({"series_id": series_id, "provider_observation_date": day,
                         "value": value, "unit": unit,
                         "provider_timestamp": instant.isoformat(),
                         "provider_timezone": str(zone)})
        days = [row["provider_observation_date"] for row in rows]
        if days != sorted(set(days)):
            raise ValueError
        return rows
    except (KeyError, TypeError, ValueError, OverflowError, OSError, IndexError):
        raise ValueError("malformed Yahoo history response") from None


def download_market_history(series_id, start_date, end_date, root, *, session=None):
    """Save a normal-TLS, bounded raw response and its explicit limitations.

    ``end_date`` is exclusive, matching the provider endpoint. No credential is
    used. Caller output storage must remain private and outside the Git checkout.
    """
    if series_id not in HISTORY_SERIES:
        raise ValueError("unknown history series")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start.isoformat() != start_date or end.isoformat() != end_date or start >= end:
        raise ValueError("history range must be ordered ISO dates")
    symbol = HISTORY_SERIES[series_id][0]
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + quote(symbol, safe="")
    params = {"period1": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
              "period2": int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()),
              "interval": "1d", "events": "div,splits"}
    owned = session is None
    client = session or requests.Session()
    response = None
    try:
        response = client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"},
                              timeout=(10, 45), verify=True, allow_redirects=False, stream=True)
        if response.status_code != 200:
            raise ValueError(f"history source returned HTTP {response.status_code}")
        parts, size = [], 0
        for part in response.iter_content(65536):
            size += len(part)
            if size > MAX_HISTORY_BYTES:
                raise ValueError("history response exceeds size limit")
            parts.append(part)
        payload = b"".join(parts)
        rows = parse_chart_history(payload, series_id)
        return snapshot_bytes(payload, root, "yahoo-" + series_id, url, ".json", {
            "provider_series_id": symbol, "request": params, "tls_verification": True,
            "audit": {"row_count": len(rows), "date_min": rows[0]["provider_observation_date"],
                      "date_max": rows[-1]["provider_observation_date"],
                      "missing_values": sum(row["value"] is None for row in rows)},
            "readiness": "raw_research_only", "historical_vintage_verified": False,
            "publication_times_verified": False, "native_calendar_verified": False,
            "limitation": "Public Yahoo chart endpoint; operational terms/availability not guaranteed. "
                          "Current historical closes can include retrospective adjustments/revisions. "
                          "TSM/NVDA close is provider historical close, not certified total return. "
                          "Provider timestamp is not a publication timestamp; latest bar may be incomplete.",
        })
    except requests.RequestException:
        raise ValueError("history network/TLS request failed") from None
    finally:
        if response is not None:
            response.close()
        if owned:
            client.close()
