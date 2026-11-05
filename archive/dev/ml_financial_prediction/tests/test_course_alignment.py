"""Temporal-policy and native-calendar integration counterexamples."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finpred.data.availability import availability_for_session
from finpred.data.normalization import build_history_market_features, normalize_course_market


def calendar(series="ixic", days=("2020-01-02", "2020-01-03", "2020-01-06")):
    return {"source": "yahoo_" + series, "session_dates": list(days),
            "calendar_evidence": "SYNTHETIC independent native sessions",
            "close_times": {day: day + "T21:00:00+00:00" for day in days}}


SNAPSHOT = {"source_url": "https://example.org/history", "sha256": "a" * 64,
            "fetched_at": "2026-10-01T00:00:00+00:00"}


class CourseAlignmentTests(unittest.TestCase):
    def test_observed_availability_is_actual_fetch_not_historical_date(self):
        rule = {"availability_basis": "observed", "availability_evidence": "observed payload acquisition"}
        result = availability_for_session("2020-01-02T21:00:00Z", SNAPSHOT["fetched_at"], rule)
        self.assertEqual(result["available_at"], SNAPSHOT["fetched_at"])
        self.assertIsNone(result["published_at"])

    def test_assumptions_explicit_and_never_production_by_default(self):
        rule = {"availability_basis": "conservative_assumption", "availability_evidence": "SYNTHETIC delay assumption",
                "available_delay_seconds": 7200}
        with self.assertRaises(ValueError):
            availability_for_session("2020-01-02T21:00:00Z", SNAPSHOT["fetched_at"], rule)
        result = availability_for_session("2020-01-02T21:00:00Z", SNAPSHOT["fetched_at"], rule, mode="research")
        self.assertEqual(result["available_at"], "2020-01-02T23:00:00+00:00")
        self.assertIsNone(result["published_at"])

    def test_future_bar_and_unverified_documented_vintage_rejected(self):
        policy = {"availability_basis": "documented", "available_delay_seconds": 0,
                  "availability_evidence": "SYNTHETIC known close"}
        with self.assertRaises(ValueError):
            availability_for_session("2020-01-02T21:00:00Z", SNAPSHOT["fetched_at"], policy)
        with self.assertRaises(ValueError):
            availability_for_session("2027-01-02T21:00:00Z", SNAPSHOT["fetched_at"], policy, mode="research")

    def test_unknown_teacher_shift_returns_blocked_not_a_guessed_table(self):
        result = normalize_course_market([{"date": "2020-01-02", "^IXIC": "100"}], {}, {}, SNAPSHOT)
        self.assertEqual(result["report"]["readiness"], "blocked")
        self.assertEqual(result["observations"], [])
        self.assertEqual(len(result["report"]["source_status"]), 6)

    def test_explicit_live_previous_session_mapping_not_double_shifted(self):
        policy = {"row_date_semantics": "target_date_previous_session", "date_evidence": "SYNTHETIC live policy",
                  "availability_basis": "observed", "availability_evidence": "SYNTHETIC observed fetch"}
        result = normalize_course_market([{"date": "2020-01-06", "^IXIC": "100"}],
                                         {"ixic": calendar()}, {"ixic": policy}, SNAPSHOT)
        self.assertEqual(result["observations"][0]["session_date"], "2020-01-03")

    def test_duplicate_source_mapping_rejected(self):
        policy = {"row_date_semantics": "target_date_previous_session", "date_evidence": "SYNTHETIC",
                  "availability_basis": "observed", "availability_evidence": "SYNTHETIC fetch"}
        with self.assertRaises(ValueError):
            normalize_course_market([{"date": "2020-01-04", "^IXIC": "100"},
                                     {"date": "2020-01-05", "^IXIC": "101"}],
                                    {"ixic": calendar()}, {"ixic": policy}, SNAPSHOT)

    def test_explicit_source_mapping_keeps_long_holiday_gap_not_one_session(self):
        policy = {"row_date_semantics": "explicit_session_map", "date_evidence": "SYNTHETIC independently matched old source date",
                  "availability_basis": "observed", "availability_evidence": "SYNTHETIC actual fetch",
                  "source_session_by_row_date": {"2020-01-10": "2020-01-02"}}
        result = normalize_course_market([{"date": "2020-01-10", "^IXIC": "100"}],
                                         {"ixic": calendar()}, {"ixic": policy}, SNAPSHOT)
        self.assertEqual(result["observations"][0]["session_date"], "2020-01-02")

    def test_signed_minus_one_oi_ambiguity_missing_without_validity_evidence(self):
        policy = {"row_date_semantics": "native_session", "date_evidence": "SYNTHETIC native date",
                  "availability_basis": "observed", "availability_evidence": "SYNTHETIC fetch"}
        result = normalize_course_market([{"date": "2020-01-02", "^IXIC": "-1", "TX_OI": "-1"}],
            {"ixic": calendar(), "tx_foreign_net_oi": calendar("tx_foreign_net_oi")},
            {"ixic": policy, "tx_foreign_net_oi": policy}, SNAPSHOT)
        values = {row["series_id"]: row["value"] for row in result["observations"]}
        self.assertIsNone(values["ixic"])
        self.assertIsNone(values["tx_foreign_net_oi"])
        self.assertEqual(len(result["report"]["source_status"]["tx_foreign_net_oi"]["ambiguous_minus_one_rows"]), 1)
        evidence_policy = {**policy, "signed_minus_one_validity_evidence": "SYNTHETIC source confirms this cell complete"}
        evidenced = normalize_course_market([{"date": "2020-01-02", "TX_OI": "-1"}],
            {"tx_foreign_net_oi": calendar("tx_foreign_net_oi")}, {"tx_foreign_net_oi": evidence_policy}, SNAPSHOT)
        self.assertEqual(evidenced["observations"][0]["value"], -1)

    def _manifest(self, root, series, days, values):
        symbols = {"ixic": "^IXIC", "sox": "^SOX"}
        from datetime import datetime
        timestamps = [int(datetime.fromisoformat(day + "T14:30:00+00:00").timestamp()) for day in days]
        payload = json.dumps({"chart": {"error": None, "result": [{
            "meta": {"symbol": symbols[series], "exchangeTimezoneName": "America/New_York"},
            "timestamp": timestamps, "indicators": {"quote": [{"close": values}]}}]}}).encode()
        raw = root / (series + ".json")
        raw.write_bytes(payload)
        manifest = {**SNAPSHOT, "source": "yahoo-" + series, "payload_path": str(raw),
                    "sha256": hashlib.sha256(payload).hexdigest()}
        path = root / (series + "_manifest.json")
        manifest["manifest_path"] = str(path)
        path.write_text(json.dumps(manifest))
        return path

    def test_history_strict_blocks_current_vintage_and_research_has_native_return(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self._manifest(root, "ixic", ["2020-01-02", "2020-01-03", "2020-01-06"], [100, 110, 999])
            targets = [{"target_date": "2020-01-06", "feature_cutoff": "2020-01-06T08:10:00+08:00"}]
            strict = build_history_market_features([path], targets)
            self.assertEqual(strict["report"]["readiness"], "blocked")
            with patch("finpred.data.normalization.history_calendar", return_value=calendar()):
                research = build_history_market_features([path], targets, mode="research")
            self.assertAlmostEqual(research["rows"][0]["ixic_ret_1s"], 0.1)
            self.assertEqual(research["report"]["readiness"], "research_assumption")
            self.assertEqual(research["rows"][0]["ixic_source_session_date"], "2020-01-03")

    def test_missing_native_previous_not_skipped_for_additional_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self._manifest(root, "sox", ["2020-01-02", "2020-01-06"], [100, 120])
            targets = [{"target_date": "2020-01-07", "feature_cutoff": "2020-01-07T08:10:00+08:00"}]
            with patch("finpred.data.normalization.history_calendar", return_value=calendar("sox")):
                result = build_history_market_features([path], targets, mode="research")
            self.assertIsNone(result["rows"][0]["sox_ret_1s"])
            self.assertEqual(result["report"]["additional_series"]["sox"]["targets"][0]["expected_previous_session"], "2020-01-03")

    def test_manifest_integrity_failure_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._manifest(Path(temporary), "ixic", ["2020-01-02"], [100])
            payload = json.loads(path.read_text())
            Path(payload["payload_path"]).write_text("changed")
            with self.assertRaises(ValueError):
                build_history_market_features([path], [], mode="research")


if __name__ == "__main__":
    unittest.main()
