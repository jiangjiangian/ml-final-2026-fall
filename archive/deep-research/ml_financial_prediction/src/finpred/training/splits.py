"""Expanding folds that keep all stocks of a target date together.

This is date-group and label-release policy, not a replacement model framework.
Feature availability and fitting preprocessors only on train remain separate
requirements. Unavailable labels remove their entire date from a training fold.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from finpred.labels.intraday import aware_datetime, finite_number, row_key


@dataclass(frozen=True)
class DateSplit:
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    train_dates: tuple[str, ...]
    validation_dates: tuple[str, ...]
    excluded_train_dates: tuple[str, ...]
    fit_cutoff: str | None
    label_availability_checked: bool


def walk_forward_splits(
    rows: Iterable[Mapping[str, Any]], *, min_train_dates: int,
    validation_dates: int, step_dates: int | None = None, gap_dates: int = 0,
    validation_cutoffs: Mapping[str, str | datetime] | None = None,
    require_label_availability: bool = False,
) -> list[DateSplit]:
    """Return full validation blocks and expanding, earlier training dates.

    Input order can vary; indices refer to that original order. At least
    ``min_train_dates`` eligible dates are required in every produced fold.
    If any row includes ``label_available_at``, every row must include an aware
    timestamp and the first validation date must have an explicit fit cutoff.
    Only labels released by that cutoff may enter training; a late stock label
    excludes its entire date. Cutoffs are supplied by the caller, never guessed
    from a date or download timestamp. ``require_label_availability=True`` fails
    closed when that evidence is absent. Without evidence, these are candidate
    date partitions only, not a certified historical backtest.
    """
    for name, value, minimum in (
        ("min_train_dates", min_train_dates, 1),
        ("validation_dates", validation_dates, 1), ("gap_dates", gap_dates, 0),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    step = validation_dates if step_dates is None else step_dates
    if isinstance(step, bool) or not isinstance(step, int) or step < 1:
        raise ValueError("step_dates must be a positive integer")
    rows = list(rows)
    dates_to_indices = {}
    keys = set()
    released = []
    availability_present = any(row.get("label_available_at") is not None for row in rows)
    if require_label_availability and not availability_present:
        raise ValueError("label_available_at evidence is required")
    for index, row in enumerate(rows):
        key = row_key(row)
        if key in keys:
            raise ValueError("duplicate stock/date split key")
        keys.add(key)
        dates_to_indices.setdefault(key[1], []).append(index)
        if "y" in row and finite_number(row["y"], name="y") not in (0, 1):
            raise ValueError("split rows with labels must contain completed binary y")
        if availability_present:
            released.append(aware_datetime(row.get("label_available_at"), name="label_available_at"))
    if availability_present and validation_cutoffs is None:
        raise ValueError("explicit validation_cutoffs are required with label availability")
    if validation_cutoffs is not None and not availability_present:
        raise ValueError("validation_cutoffs cannot certify labels without label_available_at")
    dates = sorted(dates_to_indices)
    first_validation = min_train_dates + gap_dates
    if first_validation + validation_dates > len(dates):
        raise ValueError("not enough dates for a complete train/validation fold")
    folds = []
    for start in range(first_validation, len(dates) - validation_dates + 1, step):
        validation = tuple(dates[start:start + validation_dates])
        candidate_train = dates[:start - gap_dates]
        cutoff = None
        excluded = []
        if availability_present:
            cutoff = aware_datetime(
                validation_cutoffs.get(validation[0]), name="validation fit cutoff",
            )
            # A cutoff beyond the first held-out date would admit later training
            # releases into a model claimed to predict that earlier date.
            local = cutoff.astimezone(ZoneInfo("Asia/Taipei"))
            if local.date().isoformat() != validation[0] or (
                local.hour, local.minute, local.second, local.microsecond
            ) > (9, 0, 0, 0):
                raise ValueError("fit cutoff must be on first validation date by 09:00 Taipei")
            excluded = [
                day for day in candidate_train
                if any(released[i] > cutoff for i in dates_to_indices[day])
            ]
        excluded_dates = set(excluded)
        eligible = tuple(day for day in candidate_train if day not in excluded_dates)
        if len(eligible) < min_train_dates:
            raise ValueError("insufficient eligible training dates after label availability filtering")
        folds.append(DateSplit(
            train_indices=tuple(i for day in eligible for i in dates_to_indices[day]),
            validation_indices=tuple(i for day in validation for i in dates_to_indices[day]),
            train_dates=eligible, validation_dates=validation,
            excluded_train_dates=tuple(excluded),
            fit_cutoff=cutoff.isoformat() if cutoff else None,
            label_availability_checked=availability_present,
        ))
    return folds
