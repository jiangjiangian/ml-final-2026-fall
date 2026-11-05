"""Behavioral submission tests use synthetic CSVs and no real network mutation."""

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

from finpred.submission.course import (
    CourseSubmissionClient, SubmissionError, execute_submission, validate_prediction_csv,
)

DAY = "2026-10-30"
NOW = datetime.fromisoformat("2026-10-30T00:20:00+00:00")
READY = {"model_validated": True, "feature_availability_verified": True,
         "feature_cutoff": "2026-10-30T08:10:00+08:00"}


def csv_bytes(value=0, *, day=DAY, ids=None, bom=False):
    ids = ids or [str(1000 + i) for i in range(50)]
    text = f"id,{day}\n" + "".join(f"{stock},{value}\n" for stock in ids)
    return (("\ufeff" if bom else "") + text).encode()


def state():
    session = {"tradingDate": DAY, "openAt": "2026-10-29T07:00:00Z",
               "deadline": "2026-10-30T01:00:00Z", "enabled": 1, "isCompetition": 0}
    return {"phase2Days": [session], "activePhase2Day": session,
            "user": {"role": "student"}, "team": {"id": "synthetic"},
            "mySubmissions": [], "uploadQuota": {"phase2": {
                "userLimit": 0, "userCount": 0, "teamLimit": 10, "teamCount": 0}}}


class Client(CourseSubmissionClient):
    def __init__(self):
        self.data = state()
        self.post_count = 0
        self.acknowledge_only = False
        self.fail_post = False
        self.current_csv = csv_bytes(1)

    def state(self):
        return copy.deepcopy(self.data)

    def daily_template(self, target_date):
        return csv_bytes()

    def post_predictions(self, target_date, file_name, payload):
        self.post_count += 1
        if self.fail_post:
            raise SubmissionError("synthetic unknown network outcome")
        if not self.acknowledge_only:
            self.data["mySubmissions"] = [{"phase": 2, "tradingDate": DAY,
                "id": "record/1", "predictionCount": 50, "score": None,
                "submittedAt": "2026-10-30 00:20:00"}]

    def read(self, method, path, **kwargs):
        if method != "GET" or path != "/api/submissions/record%2F1?record=current":
            raise AssertionError("unverified endpoint")
        return self.current_csv


def execute(client, root, **kwargs):
    arguments = dict(dry_run=False, clock=lambda: NOW, readiness=READY, poll_interval=0)
    arguments.update(kwargs)
    return execute_submission(client, csv_bytes(1), DAY, root, **arguments)


class CsvTests(unittest.TestCase):
    def test_atomic_replacement_does_not_mix_bytes_and_generation_time(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "submit_predictions.py"
        spec = importlib.util.spec_from_file_location("submission_cli", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            path, replacement = Path(root) / "candidate.csv", Path(root) / "replacement.csv"
            path.write_bytes(csv_bytes(0))
            replacement.write_bytes(csv_bytes(1))
            old_time, new_time = 1700000000, 1800000000
            os.utime(path, (old_time, old_time))
            os.utime(replacement, (new_time, new_time))
            original_open = Path.open

            def replacing_open(candidate_path, *args, **kwargs):
                handle = original_open(candidate_path, *args, **kwargs)
                os.replace(replacement, path)
                return handle

            with patch.object(Path, "open", replacing_open):
                payload, generated = module.read_prediction_file(path)
            self.assertEqual(payload, csv_bytes(0))
            self.assertEqual(generated.timestamp(), old_time)
            self.assertEqual(path.read_bytes(), csv_bytes(1))

    def test_exact_universe_and_bom(self):
        result = validate_prediction_csv(csv_bytes(1, bom=True), csv_bytes(), DAY)
        self.assertEqual(result["stockIds"][0], "1000")
        self.assertEqual(result["predictions"], [1] * 50)

    def test_bad_counts_headers_order_duplicates_and_probabilities(self):
        ids = [str(1000 + i) for i in range(50)]
        candidates = [csv_bytes(ids=ids[:-1]), csv_bytes(day="2026-10-29"),
                      csv_bytes(ids=list(reversed(ids))), csv_bytes(ids=ids[:-1] + [ids[0]]),
                      csv_bytes("0.5"), csv_bytes("1.0"), csv_bytes(-1), csv_bytes() + b"\n"]
        for payload in candidates:
            with self.subTest(payload=payload[:35]), self.assertRaises(SubmissionError):
                validate_prediction_csv(payload, csv_bytes(), DAY)

    def test_leading_zero_stock_ids_preserved(self):
        ids = [f"{i:04}" for i in range(50)]
        result = validate_prediction_csv(csv_bytes(ids=ids), csv_bytes(ids=ids), DAY)
        self.assertEqual(result["stockIds"][0], "0000")


class WorkflowTests(unittest.TestCase):
    def test_dry_run_has_no_post_or_runtime_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            result = execute(client, root, dry_run=True)
            self.assertTrue(result["would_submit"])
            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(client.post_count, 0)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_acknowledgement_and_downloaded_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            result = execute(client, root)
            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["scoring_status"], "pending")
            self.assertEqual(result["submitted_at"], "2026-10-30T00:20:00+00:00")
            path = Path(root) / "submission" / DAY / "latest.json"
            self.assertEqual(json.loads(path.read_text())["csv_sha256"], result["csv_sha256"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(client.post_count, 1)

    def test_same_predictions_do_not_post_twice(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            execute(client, root)
            execute(client, root)
            self.assertEqual(client.post_count, 1)

    def test_http_ack_without_current_receipt_is_not_success_or_blind_retry(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            client.acknowledge_only = True
            with self.assertRaisesRegex(SubmissionError, "lacks verified"):
                execute(client, root)
            with self.assertRaisesRegex(SubmissionError, "unresolved"):
                execute(client, root)
            self.assertEqual(client.post_count, 1)

    def test_unknown_network_outcome_never_blind_retries(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            client.fail_post = True
            with self.assertRaisesRegex(SubmissionError, "unverified"):
                execute(client, root)
            with self.assertRaisesRegex(SubmissionError, "unresolved"):
                execute(client, root)
            self.assertEqual(client.post_count, 1)

    def test_unknown_outcome_can_reconcile_existing_current_record(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            client.fail_post = True
            with self.assertRaises(SubmissionError):
                execute(client, root)
            client.data["mySubmissions"] = [{"phase": 2, "tradingDate": DAY,
                "id": "record/1", "predictionCount": 50, "score": None,
                "submittedAt": "2026-10-30T00:20:00Z"}]
            self.assertEqual(execute(client, root)["status"], "verified")
            self.assertEqual(client.post_count, 1)

    def test_older_job_cannot_override_newer_job(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            execute(client, root)
            with self.assertRaisesRegex(SubmissionError, "older prediction"):
                execute(client, root, generated_at="2026-10-30T00:19:00Z")
            self.assertEqual(client.post_count, 1)

    def test_deadline_and_wrong_day_are_blocked(self):
        for instant in ["2026-10-30T01:00:00Z", "2026-10-30T01:00:00.000001Z",
                        "2026-10-29T23:59:00+08:00", "2026-10-30T03:59:59+08:00"]:
            with tempfile.TemporaryDirectory() as root, self.subTest(instant=instant):
                client = Client()
                with self.assertRaises(SubmissionError):
                    execute(client, root, clock=lambda: datetime.fromisoformat(instant.replace("Z", "+00:00")))
                self.assertEqual(client.post_count, 0)

    def test_before_official_open_and_disabled_session_blocked(self):
        for mutate in [lambda s: s["phase2Days"][0].update(enabled=0),
                       lambda s: s["phase2Days"][0].update(openAt="2026-10-30T00:30:00Z")]:
            with tempfile.TemporaryDirectory() as root:
                client = Client()
                mutate(client.data)
                with self.assertRaises(SubmissionError):
                    execute(client, root)
                self.assertEqual(client.post_count, 0)

    def test_unknown_or_exhausted_quota_is_not_assumed_unlimited(self):
        for quota in [None, {"userLimit": 1, "userCount": 1, "teamLimit": 0, "teamCount": 0}]:
            with tempfile.TemporaryDirectory() as root:
                client = Client()
                client.data["uploadQuota"]["phase2"] = quota
                with self.assertRaises(SubmissionError):
                    execute(client, root)
                self.assertEqual(client.post_count, 0)

    def test_readiness_evidence_and_naive_timestamps_rejected(self):
        for readiness in [None, {**READY, "model_validated": False},
                          {**READY, "feature_availability_verified": False},
                          {**READY, "feature_cutoff": "2026-10-30T08:30:00+08:00"},
                          {**READY, "feature_cutoff": "2026-10-30T08:10:00"}]:
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises(SubmissionError):
                    execute(Client(), root, readiness=readiness)
        with tempfile.TemporaryDirectory() as root, self.assertRaises(SubmissionError):
            execute(Client(), root, clock=lambda: datetime(2026, 10, 30, 8, 20))

    def test_recheck_deadline_after_lock_before_post(self):
        clocks = iter([NOW, datetime(2026, 10, 30, 1, tzinfo=timezone.utc)])
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            with self.assertRaises(SubmissionError):
                execute(client, root, clock=lambda: next(clocks))
            self.assertEqual(client.post_count, 0)

    def test_dry_run_reports_blockers_and_never_submits(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client()
            result = execute(client, root, dry_run=True, readiness=None)
            self.assertFalse(result["would_submit"])
            self.assertIn("validated model evidence is required", result["blockers"])
            self.assertEqual(client.post_count, 0)


class Response:
    def __init__(self, status=200, payload=b"{}"):
        self.status_code = status
        self.payload = payload
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response):
        self.headers = {}
        self.response = response
        self.calls = []

    def mount(self, *args):
        pass

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class TransportTests(unittest.TestCase):
    def test_post_is_verified_tls_no_redirect_no_retry_and_exact_contract(self):
        session = Session(Response())
        client = CourseSubmissionClient(session=session)
        payload = validate_prediction_csv(csv_bytes(1), csv_bytes(), DAY)
        client.post_predictions(DAY, "prediction.csv", payload)
        args, kwargs = session.calls[0]
        self.assertEqual(args, ("POST", "https://final.html2026.csie.org/api/submissions"))
        self.assertTrue(kwargs["verify"])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["json"]["payload"], payload)
        self.assertEqual(kwargs["json"]["phase"], 2)
        self.assertTrue(session.response.closed)

    def test_redirect_bad_json_and_network_exception_do_not_replay_or_leak(self):
        for response in [Response(307), Response(200, b"<html>login</html>"),
                         requests.ConnectionError("private secret response")]:
            session = Session(response)
            client = CourseSubmissionClient(session=session)
            with self.assertRaises(SubmissionError) as error:
                client.post_predictions(DAY, "prediction.csv", {})
            self.assertNotIn("private secret", str(error.exception))
            self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
