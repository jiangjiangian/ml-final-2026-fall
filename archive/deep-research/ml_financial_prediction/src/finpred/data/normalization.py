"""Evidence-driven adapters for course CSV and already typed raw observations."""

from bisect import bisect_left
from datetime import date
import math

from finpred.data.availability import availability_for_session
from finpred.features.market import SERIES_IDS

COURSE_COLUMNS = {"ixic": "^IXIC", "gspc": "^GSPC", "twii": "^TWII",
                  "ks11": "^KS11", "vix": "^VIX", "tx_foreign_net_oi": "TX_OI"}


def _iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("dates must be canonical ISO strings")
    return value


def _calendar(calendar):
    days = [_iso_date(day) for day in calendar.get("session_dates", [])]
    if not days or days != sorted(set(days)):
        raise ValueError("a nonempty, sorted unique native calendar is required")
    for key in ("source", "calendar_evidence"):
        if not isinstance(calendar.get(key), str) or not calendar[key].strip():
            raise ValueError("calendar source and evidence are required")
    closes = calendar.get("close_times")
    if not isinstance(closes, dict) or set(closes) != set(days):
        raise ValueError("calendar must explicitly supply one aware close time per native session")
    return days


def _value(raw, series):
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in {"", "nan", "null", "none"}):
        return None
    if isinstance(raw, bool):
        raise ValueError("boolean observation values are forbidden")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("observation must be finite")
    # Negative price levels are an unambiguous invalid/unfinished value here.
    # Signed OI is different: -1 may be real and is preserved.
    if series != "tx_foreign_net_oi" and value < 0:
        return None
    return value


def normalize_course_market(rows, calendars, policies, snapshot, *, mode="strict"):
    """Build the existing M0 contract, with explicit row-date policies.

    calendars additionally supplies close_times. Each policy names native_session,
    target_date_previous_session or an evidenced explicit_session_map, plus its
    evidence and availability rule. Unknown series remain blocked, never guessed.
    ``snapshot`` supplies actual source_url, sha256 and fetched_at.
    """
    if mode not in {"strict", "research"}:
        raise ValueError("mode must be strict or research")
    if not isinstance(snapshot, dict) or any(not snapshot.get(k) for k in ("sha256", "source_url", "fetched_at")):
        raise ValueError("actual snapshot URL, SHA256 and acquisition time are required")
    rows = list(rows)
    row_days = [_iso_date(row["date"]) for row in rows]
    if row_days != sorted(set(row_days)):
        raise ValueError("course rows require sorted unique dates")
    observations, sessions, statuses = [], {}, {}
    for series in SERIES_IDS:
        policy, calendar = policies.get(series), calendars.get(series)
        if policy is None or calendar is None:
            statuses[series] = {"status": "blocked", "reason": "missing explicit date/availability policy or native calendar"}
            continue
        days = _calendar(calendar)
        semantics = policy.get("row_date_semantics")
        if semantics not in {"native_session", "target_date_previous_session", "explicit_session_map"}:
            statuses[series] = {"status": "blocked", "reason": "unverified row date semantics"}
            continue
        date_evidence = policy.get("date_evidence")
        if not isinstance(date_evidence, str) or not date_evidence.strip():
            statuses[series] = {"status": "blocked", "reason": "missing date/shift evidence"}
            continue
        converted, failures, seen, ambiguities = [], [], set(), []
        for row in rows:
            source_day = row["date"]
            if semantics == "explicit_session_map":
                mapping = policy.get("source_session_by_row_date")
                if not isinstance(mapping, dict) or row["date"] not in mapping:
                    failures.append({"row_date": row["date"], "reason": "no evidenced source-session mapping for row"})
                    continue
                source_day = _iso_date(mapping[row["date"]])
            if semantics == "target_date_previous_session":
                position = bisect_left(days, source_day) - 1
                if position < 0:
                    failures.append({"row_date": row["date"], "reason": "calendar lacks previous source session"})
                    continue
                source_day = days[position]
            if source_day not in calendar["close_times"]:
                failures.append({"row_date": row["date"], "reason": "row is not a source calendar session"})
                continue
            if source_day in seen:
                raise ValueError("multiple course rows map to the same source session; choose a version before normalization")
            seen.add(source_day)
            try:
                temporal = availability_for_session(calendar["close_times"][source_day], snapshot["fetched_at"], policy, mode=mode)
            except ValueError as exc:
                failures.append({"row_date": row["date"], "reason": str(exc)})
                continue
            value = _value(row.get(policy.get("column", COURSE_COLUMNS[series])), series)
            if series == "tx_foreign_net_oi" and value == -1:
                evidence = policy.get("signed_minus_one_validity_evidence")
                if not isinstance(evidence, str) or not evidence.strip():
                    ambiguities.append({"row_date": row["date"], "raw_value": -1,
                                        "reason": "unknown sentinel versus real signed value; no per-cell validity evidence"})
                    value = None
            converted.append({"source": calendar["source"], "series_id": series,
                              "session_date": source_day, **temporal,
                              "value": value,
                              "unit": "contracts" if series == "tx_foreign_net_oi" else "index_point",
                              "revision_id": snapshot["sha256"], "source_url": snapshot["source_url"],
                              "payload_sha256": snapshot["sha256"]})
        if converted:
            observations.extend(converted)
            sessions[series] = {key: calendar[key] for key in ("source", "session_dates", "calendar_evidence")}
        statuses[series] = {"status": "normalized" if converted else "blocked",
                            "observations": len(converted), "date_evidence": date_evidence,
                            "availability_basis": policy.get("availability_basis"), "excluded_rows": failures,
                            "ambiguous_minus_one_rows": ambiguities}
    assumption = any(o["availability_basis"] == "conservative_assumption" for o in observations)
    readiness = "research_assumption" if assumption or mode == "research" else "verified"
    if not observations:
        readiness = "blocked"
    return {"observations": observations, "native_sessions": sessions,
            "report": {"schema_version": "course-normalization-v1", "mode": mode,
                       "readiness": readiness,
                       "source_status": statuses, "observation_count": len(observations),
                       "historical_vintage_verified": all(p.get("historical_vintage_verified") is True for p in policies.values()) if policies else False,
                       "limitations": ["Policies/calendar evidence are caller-supplied and must be reviewed.",
                                       "Research assumptions/latest vintages are not certified historical availability."]}}


def history_calendar(series_id, start_date, end_date):
    """Export a maintained exchange calendar, not dates inferred from prices.

    Calendar rules are third-party research evidence. VIX uses NYSE sessions and
    a 15-minute close offset as an explicit proxy, not an official Cboe calendar.
    """
    import exchange_calendars as ec

    names = {"ixic": "XNAS", "gspc": "XNYS", "twii": "XTAI", "ks11": "XKRX",
             "vix": "XNYS", "sox": "XNAS", "tsm_adr": "XNYS", "nvda": "XNAS"}
    if series_id not in names:
        raise ValueError("no source calendar configured")
    calendar = ec.get_calendar(names[series_id], start=start_date, end=end_date)
    schedule = calendar.schedule
    from datetime import timedelta

    close_offset = timedelta(minutes=15) if series_id == "vix" else timedelta(0)
    days = [instant.date().isoformat() for instant in schedule.index]
    return {"source": "yahoo_" + series_id, "session_dates": days,
            "close_times": {day: (schedule.iloc[i]["close"].to_pydatetime() + close_offset).isoformat()
                            for i, day in enumerate(days)},
            "calendar_evidence": f"exchange_calendars {ec.__version__} {names[series_id]}, "
                                 "https://github.com/gerrymanoim/exchange_calendars; "
                                 "third-party calendar research evidence; VIX uses NYSE+15min proxy where applicable"}


def normalize_history_snapshots(manifests, *, mode="strict", delay_seconds=7200):
    """Normalize raw Yahoo histories for an explicitly qualified research run.

    Current-history snapshots do not provide historical vintages. Thus strict
    historical mode is blocked even though the API call itself succeeded.
    Research uses market-calendar closes plus a declared two-hour provider-delay
    assumption. It never claims those assumed times were actually observed.
    """
    import hashlib
    import json
    from pathlib import Path
    from finpred.ingestion.market_history import parse_chart_history

    if mode not in {"strict", "research"}:
        raise ValueError("mode must be strict or research")
    observations, calendars, excluded, raw_series = [], {}, {}, {}
    for path in manifests:
        manifest = json.loads(Path(path).read_text())
        series = manifest["source"].removeprefix("yahoo-")
        if series in raw_series:
            raise ValueError("choose exactly one immutable snapshot per series")
        payload = Path(manifest["payload_path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
            raise ValueError("history payload hash differs from manifest")
        raw = parse_chart_history(payload, series)
        raw_series[series] = {"manifest": manifest, "rows": raw}
        if mode == "strict":
            excluded[series] = [{"reason": "current history lacks historical publication/vintage evidence"}]
            continue
        cal = history_calendar(series, raw[0]["provider_observation_date"], raw[-1]["provider_observation_date"])
        calendars[series] = cal
        policy = {"availability_basis": "conservative_assumption", "available_delay_seconds": delay_seconds,
                  "availability_evidence": "RESEARCH ASSUMPTION: exchange calendar close + "
                  f"{delay_seconds}s provider delay; not measured historical release times. "
                  "Current snapshot vintage may contain retrospective revisions/adjustments."}
        excluded[series] = []
        for row in raw:
            day = row["provider_observation_date"]
            if day not in cal["close_times"]:
                excluded[series].append({"row_date": day, "reason": "not in independent exchange calendar"})
                continue
            try:
                temporal = availability_for_session(cal["close_times"][day], manifest["fetched_at"], policy, mode="research")
            except ValueError as exc:
                excluded[series].append({"row_date": day, "reason": str(exc)})
                continue
            observations.append({"source": cal["source"], "series_id": series, "session_date": day,
                                 **temporal, "value": row["value"], "unit": row["unit"],
                                 "revision_id": manifest["sha256"], "source_url": manifest["source_url"],
                                 "payload_sha256": manifest["sha256"]})
    return {"observations": observations, "native_sessions": calendars,
            "report": {"readiness": "research_assumption" if observations else "blocked",
                       "mode": mode, "historical_vintage_verified": False,
                       "assumed_provider_delay_seconds": delay_seconds, "excluded_rows": excluded,
                       "source_manifests": {s: d["manifest"]["manifest_path"] for s, d in raw_series.items()},
                       "source_rows": {s: len(d["rows"]) for s, d in raw_series.items()},
                       "limitations": ["No historical provider publication/vintage proof.",
                                       "Calendar rules are maintained third-party research evidence.",
                                       "Signed TX_OI omitted until source-date/sentinel evidence is sufficient."]}}


def build_history_market_features(manifests, targets, *, mode="strict", delay_seconds=7200):
    """Build existing M0 plus clearly named extra price returns for research.

    Additional returns deliberately support one immutable version per session;
    revision-aware production observations continue through the existing M0 core.
    """
    from bisect import bisect_right
    from finpred.data.availability import aware_instant
    from finpred.features.market import build_market_features

    prepared = normalize_history_snapshots(manifests, mode=mode, delay_seconds=delay_seconds)
    if prepared["report"]["readiness"] == "blocked":
        return {"rows": [], "report": prepared["report"]}
    obs = prepared["observations"]
    calendars = prepared["native_sessions"]
    result = build_market_features([o for o in obs if o["series_id"] in SERIES_IDS],
                                  {s: {k: c[k] for k in ("source", "session_dates", "calendar_evidence")}
                                   for s, c in calendars.items() if s in SERIES_IDS}, targets,
                                  feature_version="research-history-v1")
    report = {**result.report, **prepared["report"], "additional_series": {}}
    for series in sorted(set(calendars) - set(SERIES_IDS)):
        native = calendars[series]["session_dates"]
        previous = {day: native[i - 1] if i else None for i, day in enumerate(native)}
        records = {o["session_date"]: o for o in obs if o["series_id"] == series}
        ordered = sorted(records)
        available_times = [aware_instant(records[day]["available_at"]) for day in ordered]
        if available_times != sorted(available_times):
            raise ValueError("single-snapshot availability must increase with source sessions")
        # Use a single-snapshot version only. None values remain latest, never
        # search backwards to a more flattering valid observation.
        audits = []
        for row in result.rows:
            cutoff = aware_instant(row["feature_cutoff"])
            position = bisect_right(available_times, cutoff) - 1
            day = ordered[position] if position >= 0 else None
            current = records.get(day)
            prior = records.get(previous.get(day)) if day else None
            value = None
            if current and prior and aware_instant(prior["available_at"]) <= cutoff:
                if current["value"] is not None and prior["value"] not in (None, 0):
                    value = (current["value"] - prior["value"]) / prior["value"]
            row[series + "_ret_1s"] = value
            row[series + "_source_session_date"] = day
            row[series + "_is_missing"] = value is None
            audits.append({"target_date": row["target_date"], "current": current,
                           "previous": prior, "expected_previous_session": previous.get(day)})
        report["additional_series"][series] = {"policy": "single_snapshot_research_only",
                                               "calendar_evidence": calendars[series]["calendar_evidence"],
                                               "targets": audits}
    return {"rows": result.rows, "report": report}
