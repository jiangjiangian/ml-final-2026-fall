"""Verified Phase 2 course submission contract and private receipt ledger.

Endpoint evidence: the authenticated course frontend and GET /api/state.
HTTP success is only an acknowledgement. A receipt is verified by downloading
the current submission from the state record and comparing all predictions.
"""

import csv
import fcntl
import hashlib
import io
import json
import os
import re
import tempfile
import time
from datetime import date, datetime, time as daytime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from finpred.ingestion.course import CourseClient, CourseDownloadError

TAIPEI = ZoneInfo("Asia/Taipei")


class SubmissionError(ValueError):
    """A controlled failure without credentials or source response bodies."""


def _day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise SubmissionError("target date must be canonical YYYY-MM-DD") from None
    return value


def _aware(value, *, server=False):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise SubmissionError("invalid timestamp") from None
    if not isinstance(value, datetime):
        raise SubmissionError("timezone-aware timestamp required")
    # The verified frontend explicitly treats naive server SQLite timestamps as UTC.
    if value.utcoffset() is None and server:
        value = value.replace(tzinfo=timezone.utc)
    if value.utcoffset() is None:
        raise SubmissionError("timezone-aware timestamp required")
    return value


def _csv(payload, target_date):
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline="")))
    except (AttributeError, UnicodeDecodeError, csv.Error):
        raise SubmissionError("CSV must be valid UTF-8") from None
    if len(rows) != 51 or rows[0] != ["id", target_date]:
        raise SubmissionError("Phase 2 CSV requires id,target_date and exactly 50 stocks")
    if any(len(row) != 2 for row in rows[1:]):
        raise SubmissionError("CSV row width must be two")
    stock_ids = [row[0] for row in rows[1:]]
    if len(set(stock_ids)) != 50 or not all(re.fullmatch(r"[0-9]+", stock) for stock in stock_ids):
        raise SubmissionError("stock IDs must be unique numeric strings")
    if any(row[1] not in {"0", "1"} for row in rows[1:]):
        raise SubmissionError("predictions must be literal integer 0 or 1")
    return {"stockIds": stock_ids, "predictions": [int(row[1]) for row in rows[1:]]}


def validate_prediction_csv(payload, template_payload, target_date):
    """Validate official template order, target date and all 50 binary predictions."""
    _day(target_date)
    template = _csv(template_payload, target_date)
    candidate = _csv(payload, target_date)
    if candidate["stockIds"] != template["stockIds"]:
        raise SubmissionError("stock IDs and order must exactly match the official template")
    return candidate


def _session(state, target_date):
    days = state.get("phase2Days")
    if not isinstance(days, list):
        raise SubmissionError("official session list is unavailable")
    matches = [day for day in days if isinstance(day, dict) and day.get("tradingDate") == target_date]
    if len(matches) != 1:
        raise SubmissionError("target date must identify one official session")
    return matches[0]


def _guard(state, target_date, now):
    session = _session(state, target_date)
    if session.get("enabled") not in (True, 1):
        raise SubmissionError("official session is disabled")
    local = now.astimezone(TAIPEI)
    hard_deadline = datetime.combine(date.fromisoformat(target_date), daytime(9), TAIPEI)
    if local.date().isoformat() != target_date or local.hour < 4:
        raise SubmissionError("submission is restricted to target-day 04:00-09:00 Taipei")
    if not _aware(session.get("openAt"), server=True) <= now < min(
        _aware(session.get("deadline"), server=True), hard_deadline,
    ):
        raise SubmissionError("official submission window is not open or deadline passed")
    if state.get("user", {}).get("role") == "student" and not state.get("team"):
        raise SubmissionError("student account must belong to an official team")
    quota = state.get("uploadQuota", {}).get("phase2ByDate", {}).get(target_date)
    if quota is None:
        active = state.get("activePhase2Day") or {}
        if active.get("tradingDate") == target_date:
            quota = state.get("uploadQuota", {}).get("phase2")
    if not isinstance(quota, dict):
        raise SubmissionError("official upload quota is unavailable")
    for prefix in ("user", "team"):
        limit, count = quota.get(prefix + "Limit"), quota.get(prefix + "Count")
        if (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
                or isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise SubmissionError("official upload quota is malformed")
        if limit and count >= limit:
            raise SubmissionError("official upload quota exhausted")
    return session


def _readiness(readiness, target_date, now):
    if not isinstance(readiness, dict) or readiness.get("model_validated") is not True:
        raise SubmissionError("validated model evidence is required")
    if readiness.get("feature_availability_verified") is not True:
        raise SubmissionError("verified feature availability evidence is required")
    cutoff = _aware(readiness.get("feature_cutoff"))
    if cutoff.astimezone(TAIPEI).date().isoformat() != target_date or cutoff > now:
        raise SubmissionError("feature cutoff must be on target date and no later than execution")


class CourseSubmissionClient(CourseClient):
    """Use only endpoints and wire fields found in the official frontend."""

    def state(self):
        try:
            state = json.loads(self.read("GET", "/api/state", max_bytes=4 * 1024 * 1024))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SubmissionError("official state did not return valid JSON") from None
        if not isinstance(state, dict):
            raise SubmissionError("official state did not return an object")
        return state

    def daily_template(self, target_date):
        _day(target_date)
        return self.read("GET", "/api/sample-submission?phase=2&tradingDate=" + quote(target_date),
                         max_bytes=1024 * 1024)

    def post_predictions(self, target_date, file_name, payload):
        # Never retry a POST automatically: unknown outcomes are reconciled via state.
        response = None
        try:
            response = self.session.request(
                "POST", self.base + "/api/submissions", timeout=(10, 30), verify=True,
                allow_redirects=False, stream=True,
                json={"phase": 2, "tradingDate": target_date, "fileName": file_name,
                      "payload": payload, "note": "finpred automated validated prediction"},
                headers={"Origin": self.base, "Referer": self.base + "/"},
            )
            if not 200 <= response.status_code < 300:
                raise SubmissionError("submission endpoint did not acknowledge HTTP success; body omitted")
            parts, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > 1024 * 1024:
                    raise SubmissionError("submission acknowledgement exceeded size limit")
                parts.append(chunk)
            raw = b"".join(parts)
        except requests.RequestException:
            raise SubmissionError("submission network outcome unknown; response omitted") from None
        finally:
            if response is not None:
                response.close()
        try:
            acknowledgement = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SubmissionError("submission acknowledgement was not valid JSON") from None
        if not isinstance(acknowledgement, dict) or acknowledgement.get("error"):
            raise SubmissionError("submission acknowledgement rejected; body omitted")

    def current_receipt(self, state, target_date, expected, template):
        records = state.get("mySubmissions")
        if not isinstance(records, list):
            raise SubmissionError("official current submissions are unavailable")
        for record in records:
            if (not isinstance(record, dict) or record.get("phase") != 2
                    or record.get("tradingDate") != target_date or not record.get("id")
                    or record.get("predictionCount") != 50):
                continue
            identifier = str(record["id"])
            raw = self.read("GET", "/api/submissions/" + quote(identifier, safe="") + "?record=current",
                            max_bytes=1024 * 1024)
            if validate_prediction_csv(raw, template, target_date) == expected:
                return {"status": "verified", "record_id": identifier,
                        "submitted_at": _aware(record.get("submittedAt"), server=True).isoformat(),
                        "scoring_status": "pending" if record.get("score") is None else "scored",
                        "receipt_method": "current_state_record_plus_downloaded_csv_comparison"}
        return None


def _write(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def execute_submission(client, csv_bytes, target_date, runtime_dir, *, file_name="prediction.csv",
                       dry_run=True, generated_at=None, readiness=None, clock=None,
                       poll_attempts=3, poll_interval=1.0):
    """Validate or submit one prediction version under a persistent per-day lock.

    Real submission requires explicit model/availability evidence. An ambiguous
    POST outcome is recorded and never retried blindly, even after process death.
    Caller clocks are injection points for tests; the CLI always uses real time.
    """
    _day(target_date)
    if Path(file_name).name != file_name or not file_name.endswith(".csv"):
        raise SubmissionError("file name must be a plain CSV filename")
    if (isinstance(poll_attempts, bool) or not isinstance(poll_attempts, int)
            or not 1 <= poll_attempts <= 5 or not 0 <= poll_interval <= 5):
        raise SubmissionError("receipt polling must be bounded")
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(clock())
    generated = _aware(generated_at) if generated_at is not None else now
    if generated > now:
        raise SubmissionError("prediction generation time is in the future")
    template = client.daily_template(target_date)
    payload = validate_prediction_csv(csv_bytes, template, target_date)
    digest = hashlib.sha256(csv_bytes).hexdigest()
    result = {"phase": 2, "target_date": target_date, "csv_sha256": digest,
              "generated_at": generated.isoformat(), "stock_count": 50}
    state = client.state()
    blockers = []
    for check in (lambda: _guard(state, target_date, now),
                  lambda: _readiness(readiness, target_date, now)):
        try:
            check()
        except SubmissionError as error:
            blockers.append(str(error))
    if dry_run:
        return {**result, "status": "dry_run", "would_submit": not blockers, "blockers": blockers}
    if blockers:
        raise SubmissionError("; ".join(blockers))
    base = Path(runtime_dir).resolve() / "submission" / target_date
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    with (base / "submission.lock").open("a+") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        ledger_path = base / "latest.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else None
        if ledger and generated < _aware(ledger["generated_at"]):
            raise SubmissionError("older prediction job must not replace a newer version")
        state = client.state()
        existing = client.current_receipt(state, target_date, payload, template)
        if existing:
            result.update(existing)
            _write(ledger_path, result)
            return result
        if ledger and ledger.get("status") in {"post_in_flight", "unverified"}:
            raise SubmissionError("prior POST outcome is unresolved; reconcile before retrying")
        # Check again under the lock immediately before the external mutation.
        now = _aware(clock())
        _guard(state, target_date, now)
        _readiness(readiness, target_date, now)
        result["status"] = "post_in_flight"
        _write(ledger_path, result)
        try:
            client.post_predictions(target_date, file_name, payload)
        except (CourseDownloadError, SubmissionError):
            result["status"] = "unverified"
            _write(ledger_path, result)
            raise SubmissionError("POST outcome unverified; reconcile state before retrying") from None
        for attempt in range(poll_attempts):
            state = client.state()
            receipt = client.current_receipt(state, target_date, payload, template)
            if receipt:
                result.update(receipt)
                _write(ledger_path, result)
                return result
            if attempt + 1 < poll_attempts and poll_interval:
                time.sleep(poll_interval)
        result["status"] = "unverified"
        _write(ledger_path, result)
        raise SubmissionError("server acknowledgement lacks verified current receipt; not retried")
