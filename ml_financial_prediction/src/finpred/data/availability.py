"""Explicit availability rules; never equate an observation date with release."""

from datetime import datetime, timedelta, timezone


def aware_instant(value, name="timestamp"):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an aware ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be an aware ISO timestamp") from None
    if result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone aware")
    return result.astimezone(timezone.utc)


def availability_for_session(event_time, fetched_at, policy, *, mode="strict"):
    """Return qualified availability or raise for an unsupported assumption.

    Observed mode makes *every* fetched value available no earlier than this
    actual acquisition. Documented historical mode additionally requires a
    vintage-verification claim and explicit source evidence from the caller.
    Research mode can use an explicit event-plus-delay assumption but labels it
    as an assumption, with published_at remaining unknown.
    """
    if mode not in {"strict", "research"}:
        raise ValueError("mode must be strict or research")
    event = aware_instant(event_time, "event_time")
    fetched = aware_instant(fetched_at, "fetched_at")
    basis = policy.get("availability_basis")
    evidence = policy.get("availability_evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("nonempty availability evidence is required")
    if fetched < event:
        raise ValueError("event occurred after acquisition; incomplete/future bar rejected")
    if basis == "observed":
        available = fetched
    elif basis in {"documented", "conservative_assumption"}:
        if mode == "strict" and (basis != "documented" or policy.get("historical_vintage_verified") is not True):
            raise ValueError("historical assumptions or unverified vintages are forbidden in strict mode")
        delay = policy.get("available_delay_seconds")
        if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
            raise ValueError("an explicit nonnegative publication delay is required")
        available = event + timedelta(seconds=delay)
    else:
        raise ValueError("unsupported availability basis")
    return {"event_time": event.isoformat(), "published_at": None,
            "available_at": available.isoformat(), "availability_basis": basis,
            "availability_evidence": evidence.strip(), "fetched_at": fetched.isoformat()}
