"""Verified public raw-data adapters; historical availability remains unverified.

These parsers deliberately do not construct M0 observations or manufacture
published_at/available_at. Provider observation dates are retained as such.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import date, datetime
from pathlib import Path

MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
SOURCE_SPECS = {
    "cboe_vix": {
        "url": "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        "format": "cboe_csv",
        "suffix": ".csv",
        "series_id": "vix",
        "provider_series_id": "VIX",
        "unit": "index_point",
        "transform": "level_and_difference_points",
    },
    "twse_twii": {
        "url": "https://openapi.twse.com.tw/v1/indicesReport/MI_5MINS_HIST",
        "format": "twse_json",
        "suffix": ".json",
        "series_id": "twii",
        "provider_series_id": "MI_5MINS_HIST",
        "unit": "index_point",
        "transform": "native_session_return_after_calendar_verification",
    },
    "fred_us10y": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
        "format": "fred_csv",
        "suffix": ".csv",
        "series_id": "us_10y_yield",
        "provider_series_id": "DGS10",
        "unit": "percent_per_annum",
        "transform": "level_and_difference_basis_points",
    },
    "fred_usd_twd": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXTAUS",
        "format": "fred_csv",
        "suffix": ".csv",
        "series_id": "usd_twd",
        "provider_series_id": "DEXTAUS",
        "unit": "TWD_per_USD",
        "transform": "fixing_return_after_calendar_and_publication_verification",
    },
}


class ExternalDataError(ValueError):
    """A public source did not produce a valid bounded raw dataset."""


def _number(raw, *, nullable=False, positive=False):
    if nullable and raw in ("", "."):
        return None
    if not isinstance(raw, str):
        raise ExternalDataError("Expected a numeric string in the source response")
    try:
        result = float(raw.replace(",", ""))
    except ValueError:
        raise ExternalDataError("Invalid numeric field in the source response") from None
    if not math.isfinite(result) or (positive and result <= 0):
        raise ExternalDataError("Non-finite or invalid source value")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExternalDataError("Duplicate JSON key in the source response")
        result[key] = value
    return result


def parse_external_payload(source_id: str, payload: bytes) -> list[dict]:
    """Return typed raw observations, never historical model-ready features."""
    if source_id not in SOURCE_SPECS:
        raise ExternalDataError("Unknown external source")
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise ExternalDataError("Empty or oversized source response")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExternalDataError("Source response is not UTF-8") from None
    if text.lstrip().startswith("<"):
        raise ExternalDataError("Source returned markup instead of data")
    spec = SOURCE_SPECS[source_id]
    observations = []
    try:
        if spec["format"] == "twse_json":
            rows = json.loads(text, object_pairs_hook=_unique_object)
            if not isinstance(rows, list):
                raise ExternalDataError("TWSE response must be a JSON array")
            for row in rows:
                if not isinstance(row, dict):
                    raise ExternalDataError("Invalid TWSE row")
                raw_date = row["Date"]
                if not isinstance(raw_date, str) or len(raw_date) != 7 or not raw_date.isdigit():
                    raise ExternalDataError("Invalid TWSE ROC date")
                observation_date = date(
                    int(raw_date[:3]) + 1911, int(raw_date[3:5]), int(raw_date[5:])
                )
                for field in ("OpeningIndex", "HighestIndex", "LowestIndex"):
                    _number(row[field], positive=True)
                value = _number(row["ClosingIndex"], positive=True)
                observations.append((observation_date, value))
        else:
            reader = csv.DictReader(io.StringIO(text, newline=""))
            expected = (
                ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]
                if spec["format"] == "cboe_csv"
                else ["observation_date", spec["provider_series_id"]]
            )
            # FRED's older export format used DATE; both designate observation date.
            if spec["format"] == "fred_csv" and reader.fieldnames == ["DATE", expected[1]]:
                expected[0] = "DATE"
            if reader.fieldnames != expected:
                raise ExternalDataError("Unexpected CSV header in the source response")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ExternalDataError("Malformed source CSV row")
                if spec["format"] == "cboe_csv":
                    observation_date = datetime.strptime(row["DATE"], "%m/%d/%Y").date()
                    for field in ("OPEN", "HIGH", "LOW"):
                        _number(row[field], positive=True)
                    value = _number(row["CLOSE"], positive=True)
                else:
                    observation_date = date.fromisoformat(row[expected[0]])
                    value = _number(
                        row[expected[1]], nullable=True, positive=source_id == "fred_usd_twd"
                    )
                observations.append((observation_date, value))
    except (KeyError, TypeError, ValueError, csv.Error) as exc:
        if isinstance(exc, ExternalDataError):
            raise
        raise ExternalDataError("Invalid source date, row or document format") from None
    if not observations:
        raise ExternalDataError("Source contains no observations")
    dates = [item[0] for item in observations]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ExternalDataError("Source observation dates must be unique and chronological")
    return [
        {
            "series_id": spec["series_id"],
            "provider_observation_date": day.isoformat(),
            "value": value,
            "unit": spec["unit"],
        }
        for day, value in observations
    ]


def summarize_external(source_id: str, rows: list[dict]) -> dict:
    """Summarize raw coverage without implying a complete trading calendar."""
    return {
        "series_id": SOURCE_SPECS[source_id]["series_id"],
        "provider_series_id": SOURCE_SPECS[source_id]["provider_series_id"],
        "row_count": len(rows),
        "missing_values": sum(row["value"] is None for row in rows),
        "date_min": rows[0]["provider_observation_date"],
        "date_max": rows[-1]["provider_observation_date"],
        "unit": SOURCE_SPECS[source_id]["unit"],
        "status": "raw_downloaded_needs_publication_evidence",
        "historical_features_ready": False,
        "published_at": None,
        "available_at": None,
        "complete_native_calendar_verified": False,
        "limitation": (
            "Provider observation date is retained; download time and HTTP headers do not "
            "establish historical publication time or vintage. TWSE endpoint coverage is "
            "a changing current-month window, not a verified full-history interface."
        ),
    }


def download_external(source_id: str, root: str | Path, *, session=None) -> dict:
    """Download, validate and retain an immutable raw snapshot via verified TLS."""
    if source_id not in SOURCE_SPECS:
        raise ExternalDataError("Unknown external source")
    # Imported here so pure parsers remain usable with the standard library alone.
    import requests

    from finpred.data.snapshots import snapshot_bytes

    owned_session = session is None
    if owned_session:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            allowed_methods=frozenset({"GET"}),
            status_forcelist=(429, 500, 502, 503, 504),
            respect_retry_after_header=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
    spec = SOURCE_SPECS[source_id]
    response = None
    try:
        response = session.get(
            spec["url"],
            timeout=(10, 40),
            allow_redirects=False,
            verify=True,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/csv,application/csv"},
        )
        if response.status_code != 200:
            raise ExternalDataError(f"External source returned HTTP {response.status_code}")
        if "html" in response.headers.get("Content-Type", "").lower():
            raise ExternalDataError("External source returned HTML instead of data")
        parts = []
        size = 0
        for part in response.iter_content(chunk_size=64 * 1024):
            size += len(part)
            if size > MAX_PAYLOAD_BYTES:
                raise ExternalDataError("Oversized source response")
            parts.append(part)
        payload = b"".join(parts)
        rows = parse_external_payload(source_id, payload)
        audit = summarize_external(source_id, rows)
        return snapshot_bytes(
            payload,
            root,
            source=source_id,
            source_url=spec["url"],
            suffix=spec["suffix"],
            metadata={
                "audit": audit,
                "transform_policy": spec["transform"],
                "tls_verification": True,
            },
        )
    except requests.RequestException:
        raise ExternalDataError("External source network or TLS request failed") from None
    finally:
        if response is not None:
            response.close()
        if owned_session:
            session.close()
