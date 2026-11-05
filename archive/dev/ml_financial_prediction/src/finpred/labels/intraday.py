"""Separate completed intraday labels from pending course rows.

The caller must verify that the two source price columns are adjusted prices.
Construction checks values and consistency; it cannot establish historical
publication times. A copied ``label_available_at`` remains caller evidence.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Real
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class LabelResult:
    complete: list[dict[str, Any]]
    pending: list[dict[str, Any]]


def row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return a canonical stock/date key, preserving leading stock-code zeros."""
    stock = row.get("stock_id")
    day = row.get("target_date")
    if not isinstance(stock, str) or not stock or stock.strip() != stock:
        raise ValueError("stock_id must be a nonempty string without outer whitespace")
    if not isinstance(day, str):
        raise ValueError("target_date must be an ISO date string")
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError("target_date must be an ISO date string") from exc
    if parsed.isoformat() != day:
        raise ValueError("target_date must be a canonical ISO date")
    return stock, day


def finite_number(value: Any, *, name: str) -> float:
    """Parse finite numeric source fields, excluding booleans and blank cells."""
    if isinstance(value, bool) or not isinstance(value, (Real, str)):
        raise ValueError(f"{name} must be finite numeric data")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite numeric data") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite numeric data")
    return result


def positive_price(value: Any, *, name: str) -> float:
    result = finite_number(value, name=name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def aware_datetime(value: Any, *, name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be a timezone-aware datetime") from exc
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def build_intraday_labels(
    rows: Iterable[Mapping[str, Any]], *, prices_verified_adjusted: bool,
    stock_id: str | None = None,
) -> LabelResult:
    """Build labels from course ``etl:adj_open/close`` rows.

    ``y=-1`` is reported as pending and its possibly incomplete prices are not
    used. Binary rows must have finite positive prices and the documented
    ``close > open`` label. ``y`` is mandatory so unresolved website rows do not
    silently become generated training labels. No source values are mutated.
    """
    if prices_verified_adjusted is not True:
        raise ValueError("adjusted-price meaning must be verified before label construction")
    complete = []
    pending = []
    seen = set()
    for row in rows:
        if stock_id is not None and "stock_id" in row and row["stock_id"] != stock_id:
            raise ValueError("row stock_id differs from the supplied stock_id")
        if "target_date" in row and "date" in row and row["target_date"] != row["date"]:
            raise ValueError("row date and target_date disagree")
        key_row = {
            "stock_id": stock_id if stock_id is not None else row.get("stock_id"),
            "target_date": row.get("target_date", row.get("date")),
        }
        key = row_key(key_row)
        if key in seen:
            raise ValueError("duplicate stock/date label key")
        seen.add(key)
        y = finite_number(row.get("y"), name="y")
        if y == -1:
            pending.append({**key_row, "status": "pending", "reason": "source_y_minus_one"})
            continue
        if y not in (0, 1):
            raise ValueError("y must be 0, 1, or the documented pending value -1")
        opening = positive_price(row.get("etl:adj_open"), name="etl:adj_open")
        closing = positive_price(row.get("etl:adj_close"), name="etl:adj_close")
        expected_y = int(closing > opening)
        if y != expected_y:
            raise ValueError("source y disagrees with adjusted close > adjusted open")
        intraday_return = (closing - opening) / opening
        if not math.isfinite(intraday_return):
            raise ValueError("intraday return must be finite")
        result = {
            **key_row, "adj_open": opening, "adj_close": closing,
            "y": expected_y, "target_intraday_return": intraday_return,
        }
        if row.get("label_available_at") is not None:
            result["label_available_at"] = aware_datetime(
                row["label_available_at"], name="label_available_at",
            ).isoformat()
        complete.append(result)
    def order(row):
        return row["target_date"], row["stock_id"]

    return LabelResult(sorted(complete, key=order), sorted(pending, key=order))
