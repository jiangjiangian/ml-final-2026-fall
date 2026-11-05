"""Build M0 features from evidence-bearing, versioned native-market records.

This module does not infer release times, shifts, or trading calendars from a
teacher CSV. Callers must supply those facts (or documented assumptions). All
historical queries select only the revisions available at that query's cutoff.
"""

from __future__ import annotations

from bisect import insort
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import math
import re
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


SERIES_IDS = ("ixic", "gspc", "twii", "ks11", "vix", "tx_foreign_net_oi")
_FEATURES = {
    "ixic": ("ixic_ret_1s",),
    "gspc": ("gspc_ret_1s",),
    "twii": ("twii_ret_1s",),
    "ks11": ("ks11_ret_1s",),
    "vix": ("vix_level", "vix_change_points"),
    "tx_foreign_net_oi": ("tx_foreign_net_oi", "tx_foreign_net_oi_change"),
}
FEATURE_COLUMNS = tuple(feature for series in SERIES_IDS for feature in _FEATURES[series])
_BASES = {"observed", "documented", "conservative_assumption"}
_REQUIRED_OBSERVATION_FIELDS = {
    "source", "series_id", "session_date", "event_time", "published_at",
    "available_at", "availability_basis", "availability_evidence", "fetched_at",
    "value", "unit", "revision_id", "source_url", "payload_sha256",
}


@dataclass(frozen=True)
class FeatureResult:
    """Flat target rows and their JSON-serializable audit evidence."""

    rows: list[dict[str, Any]]
    report: dict[str, Any]


@dataclass(frozen=True)
class _Observation:
    series: str
    session: str
    available: datetime
    revision_order: datetime
    value: float | None
    provenance: dict[str, Any]


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def _date(value: Any, field: str) -> str:
    value = _text(value, field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")
    return value


def _instant(value: Any, field: str) -> datetime:
    value = _text(value, field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a timezone-aware ISO datetime") from exc


def _safe_source_url(value: Any) -> str:
    value = _text(value, "source_url")
    try:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("userinfo forbidden")
        if "?" in value or "#" in value:
            raise ValueError("query and fragment forbidden")
        if parsed.scheme in {"http", "https"} and not parsed.hostname:
            raise ValueError("hostname required")
    except ValueError as exc:
        raise ValueError("source_url must be a public identifier without credentials, query, or fragment") from exc
    return value


def _calendars(native_sessions: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(native_sessions, dict):
        raise ValueError("native_sessions must be an object keyed by series_id")
    if set(native_sessions) - set(SERIES_IDS):
        raise ValueError("native_sessions contains an unsupported series_id")
    result = {}
    for series, calendar in native_sessions.items():
        if not isinstance(calendar, dict):
            raise ValueError("Each native session calendar must be an object")
        source = _text(calendar.get("source"), "calendar source")
        evidence = _text(calendar.get("calendar_evidence"), "calendar_evidence")
        raw_dates = calendar.get("session_dates")
        if not isinstance(raw_dates, list):
            raise ValueError("session_dates must be a list of ISO dates")
        dates = [_date(value, "session_dates") for value in raw_dates]
        if dates != sorted(set(dates)):
            raise ValueError("session_dates must be unique and sorted")
        result[series] = {
            "source": source,
            "calendar_evidence": evidence,
            "dates": dates,
            "previous": {day: dates[i - 1] if i else None for i, day in enumerate(dates)},
        }
    return result


def _observations(raw: Any, calendars: dict[str, dict[str, Any]]) -> dict[str, list[_Observation]]:
    if not isinstance(raw, list):
        raise ValueError("observations must be a list")
    result: dict[str, list[_Observation]] = {series: [] for series in SERIES_IDS}
    keys = set()
    revision_times = set()
    publication_kinds: dict[tuple[str, str, str], bool] = {}
    publication_times = set()
    for item in raw:
        if not isinstance(item, dict) or _REQUIRED_OBSERVATION_FIELDS - set(item):
            raise ValueError("Each observation must contain the complete data-contract fields and availability_evidence")
        series = _text(item["series_id"], "series_id")
        if series not in _FEATURES:
            raise ValueError("Unsupported observation series_id")
        if series not in calendars:
            raise ValueError("An observation requires an explicit native session calendar")
        calendar = calendars[series]
        source = _text(item["source"], "source")
        if source != calendar["source"]:
            raise ValueError("Observation source must match its series calendar; provider mixing is forbidden")
        session = _date(item["session_date"], "session_date")
        if session not in calendar["previous"]:
            raise ValueError("Observation session_date is absent from its native calendar")
        basis = _text(item["availability_basis"], "availability_basis")
        if basis not in _BASES:
            raise ValueError("Unverified availability_basis is blocked")
        evidence = _text(item["availability_evidence"], "availability_evidence")
        revision = _text(item["revision_id"], "revision_id")
        key = (source, series, session, revision)
        if key in keys:
            raise ValueError("Duplicate observation revision key")
        keys.add(key)
        event = _instant(item["event_time"], "event_time")
        available = _instant(item["available_at"], "available_at")
        fetched = _instant(item["fetched_at"], "fetched_at")
        published = None if item["published_at"] is None else _instant(item["published_at"], "published_at")
        if available < event or fetched < event:
            raise ValueError("available_at and fetched_at cannot precede event_time")
        if published is not None and (published < event or available < published or fetched < published):
            raise ValueError("Contradictory event, publication, availability, or fetch timestamps")
        session_key = (source, series, session)
        has_publication = published is not None
        if session_key in publication_kinds and publication_kinds[session_key] != has_publication:
            raise ValueError("A session's revisions cannot mix null and non-null published_at")
        publication_kinds[session_key] = has_publication
        if published is not None:
            publication_time = (*session_key, published)
            if publication_time in publication_times:
                raise ValueError("Ambiguous revisions with the same session and published_at")
            publication_times.add(publication_time)
        revision_time = (source, series, session, available)
        if revision_time in revision_times:
            raise ValueError("Ambiguous revisions with the same session and available_at")
        revision_times.add(revision_time)
        unit = _text(item["unit"], "unit")
        expected_unit = "contracts" if series == "tx_foreign_net_oi" else "index_point"
        if unit != expected_unit:
            raise ValueError(f"{series} requires unit {expected_unit}")
        value = item["value"]
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("value must be a finite JSON number or null")
            try:
                value = float(value)
            except (ValueError, OverflowError) as exc:
                raise ValueError("value must be finite") from exc
            if not math.isfinite(value):
                raise ValueError("value must be finite")
        digest = _text(item["payload_sha256"], "payload_sha256")
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise ValueError("payload_sha256 must be a SHA-256 hexadecimal digest")
        provenance = {
            "source": source, "series_id": series, "session_date": session,
            "event_time": event.isoformat(),
            "published_at": None if published is None else published.isoformat(),
            "available_at": available.isoformat(), "availability_basis": basis,
            "availability_evidence": evidence, "fetched_at": fetched.isoformat(),
            "value": value, "unit": unit, "revision_id": revision,
            "source_url": _safe_source_url(item["source_url"]),
            "payload_sha256": digest.lower(),
        }
        result[series].append(_Observation(series, session, available, published or available, value, provenance))
    for values in result.values():
        values.sort(key=lambda observation: observation.available)
    return result


def _targets(raw: Any) -> list[tuple[str, datetime]]:
    if not isinstance(raw, list):
        raise ValueError("targets must be a list")
    result = []
    seen = set()
    for target in raw:
        if not isinstance(target, dict):
            raise ValueError("Each target must be an object")
        day = _date(target.get("target_date"), "target_date")
        if day in seen:
            raise ValueError("Duplicate target_date; this version supports one cutoff per target date")
        seen.add(day)
        cutoff = _instant(target.get("feature_cutoff"), "feature_cutoff")
        deadline = datetime.combine(date.fromisoformat(day), time(9), ZoneInfo("Asia/Taipei"))
        if cutoff > deadline.astimezone(timezone.utc):
            raise ValueError("feature_cutoff cannot exceed target_date 09:00 Asia/Taipei competition deadline")
        result.append((day, cutoff))
    return sorted(result)


def _feature_values(series: str, current: _Observation | None, previous: _Observation | None,
                    previous_date: str | None) -> tuple[dict[str, float | None], dict[str, str]]:
    features = _FEATURES[series]
    values: dict[str, float | None] = dict.fromkeys(features)
    reasons = {}
    if current is None or current.value is None:
        reason = "no_available_observation" if current is None else "missing_current_value"
        return values, dict.fromkeys(features, reason)
    if len(features) == 2:
        values[features[0]] = current.value
    transformed = features[-1]
    if previous_date is None:
        reasons[transformed] = "no_previous_native_session"
    elif previous is None:
        reasons[transformed] = "previous_session_unavailable"
    elif previous.value is None:
        reasons[transformed] = "missing_previous_value"
    elif len(features) == 1 and previous.value == 0:
        reasons[transformed] = "zero_previous_value"
    else:
        assert previous is not None and previous.value is not None
        if len(features) == 1:
            value = (current.value - previous.value) / previous.value
        else:
            value = current.value - previous.value
        if math.isfinite(value):
            values[transformed] = value
        else:
            reasons[transformed] = "non_finite_result"
    return values, reasons


def build_market_features(observations, native_sessions, targets, feature_version="m0-v1") -> FeatureResult:
    """Construct eight M0 values for every target without future revisions.

    ``native_sessions`` maps each series to ``source``, sorted ``session_dates``
    and nonempty ``calendar_evidence``. A missing calendar is accepted only for
    a series without observations. Targets and observation timestamps use ISO
    strings with explicit UTC offsets. A target's cutoff may be earlier than,
    or equal to, its official 09:00 Asia/Taipei deadline, but never later. The
    proposed 08:10 schedule is not enforced. Missing values are ``None``. No
    filling, normalization, teacher-date reinterpretation, or network access
    occurs.

    Rows are sorted by target date. A series' ``is_missing`` is true if any of
    its numerical features is missing; the report explains each such feature.
    Freshness compares selected source sessions, not revision timestamps. The
    first target has unknown freshness (``None``). Age is measured from the
    latest availability timestamp among the versions needed by the transform.
    Fetch times describe retrieval and do not filter historical backfills.
    ``published_at`` means the first publication time of this specific version,
    not the first-ever publication of the session. Among eligible versions of
    one session, the latest publication wins even if an older version has a
    later ``available_at``. Only when every version of a session lacks a
    publication timestamp does availability also determine revision order.
    Mixed null/non-null publication metadata and publication ties are rejected.
    """
    feature_version = _text(feature_version, "feature_version")
    calendars = _calendars(native_sessions)
    grouped = _observations(observations, calendars)
    target_rows = _targets(targets)
    # Sweep by cutoff, not target date: explicitly supplied cutoffs may differ
    # in order. Each revision is processed once per series, and a late revision
    # of an old session cannot replace a newer selected session.
    snapshots: dict[str, dict[str, tuple[_Observation | None, _Observation | None, str | None]]] = {
        day: {} for day, _ in target_rows
    }
    for series in SERIES_IDS:
        versions = grouped[series]
        active: dict[str, _Observation] = {}
        sessions: list[str] = []
        offset = 0
        for day, cutoff in sorted(target_rows, key=lambda target: target[1]):
            while offset < len(versions) and versions[offset].available <= cutoff:
                observation = versions[offset]
                if observation.session not in active:
                    insort(sessions, observation.session)
                previous_revision = active.get(observation.session)
                if previous_revision is None or observation.revision_order > previous_revision.revision_order:
                    active[observation.session] = observation
                offset += 1
            current = active[sessions[-1]] if sessions else None
            previous_date = calendars[series]["previous"][current.session] if current is not None else None
            previous = active.get(previous_date) if previous_date is not None else None
            snapshots[day][series] = (current, previous, previous_date)

    rows = []
    trace_rows = []
    counts = Counter({feature: 0 for feature in FEATURE_COLUMNS})
    previous_selected: dict[str, str | None] = {}
    for index, (day, cutoff) in enumerate(target_rows):
        row = {"target_date": day, "feature_cutoff": cutoff.isoformat(), "feature_version": feature_version}
        row.update(dict.fromkeys(FEATURE_COLUMNS))
        trace = {"target_date": day, "feature_cutoff": cutoff.isoformat(), "series": {}}
        for series in SERIES_IDS:
            current, previous, previous_date = snapshots[day][series]
            values, reasons = _feature_values(series, current, previous, previous_date)
            row.update(values)
            for feature in reasons:
                counts[feature] += 1
            # The prior version was examined even when its null/zero value
            # prevents a difference or return. Its availability is provenance.
            inputs = [value for value in (current, previous) if value is not None]
            available = max(value.available for value in inputs) if inputs else None
            session = current.session if current is not None else None
            prior_session = previous_selected.get(series)
            fresh = None if index == 0 else session is not None and (prior_session is None or session > prior_session)
            previous_selected[series] = session
            row.update({
                f"{series}_source_session_date": session,
                f"{series}_source_available_at": available.isoformat() if available is not None else None,
                f"{series}_age_hours": (cutoff - available).total_seconds() / 3600 if available is not None else None,
                f"{series}_is_missing": bool(reasons),
                f"{series}_is_new_session_since_previous_tw_target": fresh,
            })
            trace["series"][series] = {
                "current": current.provenance if current is not None else None,
                "previous": previous.provenance if previous is not None else None,
                "expected_previous_session_date": previous_date,
                "missing_reasons": reasons,
                "source_condition": "unknown_without_expected_publication_schedule",
            }
        rows.append(row)
        trace_rows.append(trace)

    report = {
        "feature_version": feature_version,
        "feature_columns": list(FEATURE_COLUMNS),
        "target_count": len(target_rows),
        "observation_count": len(observations),
        "missing_counts": dict(counts),
        "series_status": {},
        "targets": trace_rows,
        "availability_status": "uses_input_evidence; does_not_verify_teacher_date_or_shift_semantics",
        "missing_policy": "preserve_all_targets; null_without_backfill_or_skipping_native_sessions",
        "freshness_policy": "new_source_session_only; first_target_unknown; revisions_are_not_new_sessions",
        "revision_selection_policy": "eligible_available_at_lte_cutoff; latest_per_version_published_at_per_session; use_available_at_only_when_all_session_versions_lack_published_at; reject_publication_ties_or_mixed_null_metadata",
    }
    for series in SERIES_IDS:
        calendar = calendars.get(series)
        report["series_status"][series] = {
            "source": calendar["source"] if calendar else None,
            "calendar_evidence": calendar["calendar_evidence"] if calendar else None,
            "session_count": len(calendar["dates"]) if calendar else 0,
            "availability_bases": sorted({item.provenance["availability_basis"] for item in grouped[series]}),
            "status": "has_observations" if grouped[series] else "no_observations",
        }
    return FeatureResult(rows=rows, report=report)
