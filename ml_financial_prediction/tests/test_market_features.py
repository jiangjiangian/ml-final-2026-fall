"""Point-in-time M0 tests using only synthetic market observations."""

import copy
import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from finpred.features.market import build_market_features


SERIES = ("ixic", "gspc", "twii", "ks11", "vix", "tx_foreign_net_oi")
FEATURES = (
    "ixic_ret_1s", "gspc_ret_1s", "twii_ret_1s", "ks11_ret_1s",
    "vix_level", "vix_change_points", "tx_foreign_net_oi",
    "tx_foreign_net_oi_change",
)
DAYS = ["2026-01-02", "2026-01-05", "2026-01-06"]


def observation(series, day, value, *, available=None, revision="r1", **changes):
    available = available or f"{day}T21:00:00+00:00"
    result = {
        "source": "synthetic",
        "series_id": series,
        "session_date": day,
        "event_time": f"{day}T20:00:00+00:00",
        "published_at": available,
        "available_at": available,
        "availability_basis": "documented",
        "availability_evidence": "Synthetic release schedule for unit tests only.",
        "fetched_at": "2026-10-25T00:00:00+00:00",
        "value": value,
        "unit": "contracts" if series == "tx_foreign_net_oi" else "index_point",
        "revision_id": revision,
        "source_url": "https://example.org/synthetic-market",
        "payload_sha256": "a" * 64,
    }
    result.update(changes)
    return result


def calendars(days=None):
    return {
        series: {
            "source": "synthetic",
            "session_dates": list(days or DAYS),
            "calendar_evidence": "Explicit synthetic source-session calendar.",
        }
        for series in SERIES
    }


def target(day="2026-01-06", cutoff=None):
    return {"target_date": day, "feature_cutoff": cutoff or f"{day}T08:10:00+08:00"}


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class MarketFeaturesTests(unittest.TestCase):
    def build(self, observations, *, sessions=None, targets=None, **kwargs):
        return build_market_features(
            observations, sessions if sessions is not None else calendars(),
            targets if targets is not None else [target()], **kwargs,
        )

    def price_pair(self):
        return [observation("ixic", DAYS[0], 100), observation("ixic", DAYS[1], 110)]

    def test_all_eight_m0_features_have_their_documented_units(self):
        pairs = {
            "ixic": (100, 110), "gspc": (200, 190), "twii": (50, 55),
            "ks11": (80, 100), "vix": (20, 23), "tx_foreign_net_oi": (-10, 5),
        }
        observations = [
            observation(series, day, value)
            for series, values in pairs.items() for day, value in zip(DAYS, values)
        ]
        row = self.build(observations).rows[0]
        expected = (0.1, -0.05, 0.1, 0.25, 23, 3, 5, 15)
        for feature, value in zip(FEATURES, expected):
            with self.subTest(feature=feature):
                self.assertAlmostEqual(row[feature], value)
        self.assertEqual(row["target_date"], "2026-01-06")
        self.assertEqual(row["feature_version"], "m0-v1")
        self.assertFalse(row["ixic_is_missing"])
        self.assertIsNone(row["ixic_is_new_session_since_previous_tw_target"])

    def test_cutoff_is_inclusive_but_one_microsecond_later_is_not_available(self):
        cutoff = "2026-01-06T00:10:00+00:00"
        observations = self.price_pair()
        observations[-1].update(available_at=cutoff, published_at=cutoff)
        self.assertAlmostEqual(self.build(observations).rows[0]["ixic_ret_1s"], 0.1)
        later = "2026-01-06T00:10:00.000001+00:00"
        observations[-1].update(available_at=later, published_at=later)
        row = self.build(observations).rows[0]
        self.assertIsNone(row["ixic_ret_1s"])
        self.assertEqual(row["ixic_source_session_date"], DAYS[0])

    def test_adding_future_observations_does_not_change_historical_rows(self):
        original = self.build(self.price_pair()).rows
        future = observation("ixic", DAYS[2], 999999)
        self.assertEqual(self.build(self.price_pair() + [future]).rows, original)

    def test_same_day_after_close_cannot_enter_premarket_features(self):
        observations = self.price_pair() + [observation("ixic", DAYS[2], 1000)]
        row = self.build(observations).rows[0]
        self.assertEqual(row["ixic_source_session_date"], DAYS[1])
        self.assertAlmostEqual(row["ixic_ret_1s"], 0.1)

    def test_revision_changes_only_predictions_after_its_publication(self):
        revised = observation(
            "ixic", DAYS[1], 120, revision="r2", available="2026-01-06T09:00:00+00:00",
        )
        result = self.build(self.price_pair() + [revised], targets=[target(), target("2026-01-07")])
        self.assertAlmostEqual(result.rows[0]["ixic_ret_1s"], 0.1)
        self.assertAlmostEqual(result.rows[1]["ixic_ret_1s"], 0.2)
        self.assertFalse(result.rows[1]["ixic_is_new_session_since_previous_tw_target"])

    def test_publication_order_wins_over_out_of_order_available_times(self):
        older = observation(
            "ixic", DAYS[1], 110, available="2026-01-06T00:05:00+00:00",
            published_at="2026-01-05T21:00:00+00:00", payload_sha256="b" * 64,
        )
        newer = observation(
            "ixic", DAYS[1], 120, revision="r2", available="2026-01-06T00:00:00+00:00",
            published_at="2026-01-05T22:00:00+00:00", payload_sha256="c" * 64,
        )
        result = self.build([observation("ixic", DAYS[0], 100), older, newer])
        row = result.rows[0]
        self.assertAlmostEqual(row["ixic_ret_1s"], 0.2)
        self.assertEqual(utc(row["ixic_source_available_at"]), utc(newer["available_at"]))
        trace = result.report["targets"][0]["series"]["ixic"]
        self.assertEqual(trace["current"]["revision_id"], "r2")
        self.assertEqual(trace["current"]["payload_sha256"], "c" * 64)
        self.assertAlmostEqual(row["ixic_age_hours"], 10 / 60)

    def test_revision_order_falls_back_to_availability_only_when_all_publications_are_null(self):
        observations = [
            observation("ixic", DAYS[0], 100, published_at=None),
            observation("ixic", DAYS[1], 110, published_at=None),
            observation(
                "ixic", DAYS[1], 120, revision="r2", published_at=None,
                available="2026-01-06T00:00:00+00:00",
            ),
        ]
        self.assertAlmostEqual(self.build(observations).rows[0]["ixic_ret_1s"], 0.2)

    def test_revisions_with_mixed_null_and_known_publication_metadata_are_rejected(self):
        records = self.price_pair() + [observation(
            "ixic", DAYS[1], 120, revision="r2", published_at=None,
            available="2026-01-06T00:00:00+00:00",
        )]
        with self.assertRaises(ValueError):
            self.build(records)

    def test_same_publication_time_is_ambiguous_even_if_availability_times_differ(self):
        records = self.price_pair() + [observation(
            "ixic", DAYS[1], 120, revision="r2", published_at="2026-01-05T21:00:00+00:00",
            available="2026-01-06T00:00:00+00:00",
        )]
        with self.assertRaises(ValueError):
            self.build(records)

    def test_late_revision_of_an_older_session_does_not_replace_latest_session(self):
        revised_previous = observation(
            "ixic", DAYS[0], 80, revision="r2", available="2026-01-06T00:05:00+00:00",
            payload_sha256="b" * 64,
        )
        result = self.build(self.price_pair() + [revised_previous])
        row = result.rows[0]
        self.assertEqual(row["ixic_source_session_date"], DAYS[1])
        self.assertAlmostEqual(row["ixic_ret_1s"], 110 / 80 - 1)
        self.assertEqual(utc(row["ixic_source_available_at"]), utc(revised_previous["available_at"]))
        self.assertAlmostEqual(row["ixic_age_hours"], 5 / 60)
        # Both numerator and denominator payloads must remain auditable.
        provenance = json.dumps(result.report)
        self.assertIn("a" * 64, provenance)
        self.assertIn("b" * 64, provenance)
        self.assertIn("r2", provenance)

    def test_missing_native_previous_session_does_not_become_multi_session_return(self):
        observations = [observation("ixic", DAYS[0], 100), observation("ixic", DAYS[2], 130)]
        row = self.build(observations, targets=[target("2026-01-07")]).rows[0]
        self.assertEqual(row["ixic_source_session_date"], DAYS[2])
        self.assertIsNone(row["ixic_ret_1s"])
        self.assertTrue(row["ixic_is_missing"])

    def test_unpublished_native_denominator_cannot_be_skipped(self):
        observations = [
            observation("ixic", DAYS[0], 100),
            observation("ixic", DAYS[1], 110, available="2026-01-10T00:00:00+00:00"),
            observation("ixic", DAYS[2], 121),
        ]
        row = self.build(observations, targets=[target("2026-01-07")]).rows[0]
        self.assertEqual(row["ixic_source_session_date"], DAYS[2])
        self.assertIsNone(row["ixic_ret_1s"])

    def test_return_uses_native_sessions_not_the_target_calendar_subset(self):
        observations = self.price_pair() + [observation("ixic", DAYS[2], 121)]
        result = self.build(observations, targets=[target("2026-01-05"), target("2026-01-07")])
        self.assertAlmostEqual(result.rows[1]["ixic_ret_1s"], 0.1)
        self.assertNotAlmostEqual(result.rows[1]["ixic_ret_1s"], 0.21)

    def test_source_holiday_carries_previous_return_and_marks_not_fresh(self):
        sessions = calendars(["2026-01-02", "2026-01-05"])
        result = self.build(
            self.price_pair(), sessions=sessions,
            targets=[target("2026-01-09"), target("2026-01-12")],
        )
        self.assertAlmostEqual(result.rows[1]["ixic_ret_1s"], 0.1)
        self.assertFalse(result.rows[1]["ixic_is_new_session_since_previous_tw_target"])
        self.assertGreater(result.rows[1]["ixic_age_hours"], 24)

    def test_new_native_session_is_fresh_even_across_long_target_gap(self):
        observations = self.price_pair() + [observation("ixic", DAYS[2], 121)]
        result = self.build(observations, targets=[target(), target("2026-01-12")])
        self.assertTrue(result.rows[1]["ixic_is_new_session_since_previous_tw_target"])
        self.assertAlmostEqual(result.rows[1]["ixic_ret_1s"], 0.1)

    def test_negative_zero_and_cross_zero_oi_are_differences_in_contracts(self):
        observations = [
            observation("tx_foreign_net_oi", day, value)
            for day, value in zip(DAYS, [-10, 0, 5])
        ]
        rows = self.build(observations, targets=[target(), target("2026-01-07")]).rows
        self.assertEqual(rows[0]["tx_foreign_net_oi"], 0)
        self.assertEqual(rows[0]["tx_foreign_net_oi_change"], 10)
        self.assertEqual(rows[1]["tx_foreign_net_oi_change"], 5)

    def test_zero_price_denominator_is_missing_not_infinity(self):
        observations = [observation("ixic", DAYS[0], 0), observation("ixic", DAYS[1], 110)]
        self.assertIsNone(self.build(observations).rows[0]["ixic_ret_1s"])

    def test_level_remains_available_when_vix_difference_has_no_previous_session(self):
        row = self.build([observation("vix", DAYS[1], 23)]).rows[0]
        self.assertEqual(row["vix_level"], 23)
        self.assertIsNone(row["vix_change_points"])
        self.assertTrue(row["vix_is_missing"])

    def test_null_latest_value_never_falls_back_to_an_older_session(self):
        observations = [observation("vix", DAYS[0], 20), observation("vix", DAYS[1], None)]
        row = self.build(observations).rows[0]
        self.assertEqual(row["vix_source_session_date"], DAYS[1])
        self.assertIsNone(row["vix_level"])
        self.assertIsNone(row["vix_change_points"])

    def test_null_latest_revision_never_falls_back_to_older_revision(self):
        observations = self.price_pair() + [observation(
            "ixic", DAYS[1], None, revision="r2", available="2026-01-06T00:00:00+00:00",
        )]
        self.assertIsNone(self.build(observations).rows[0]["ixic_ret_1s"])

    def test_nonfinite_or_nonnumeric_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, True, "110"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.build([observation("ixic", DAYS[1], value)])

    def test_empty_sources_preserve_all_targets_and_all_feature_columns(self):
        targets = [target("2026-01-07"), target(), target("2026-01-08")]
        result = self.build([], sessions={}, targets=targets)
        self.assertEqual([r["target_date"] for r in result.rows], sorted(t["target_date"] for t in targets))
        for row in result.rows:
            self.assertTrue(all(feature in row and row[feature] is None for feature in FEATURES))
            self.assertTrue(all(row[f"{series}_is_missing"] for series in SERIES))

    def test_target_rows_sort_by_target_date_before_fresh_is_computed(self):
        observations = self.price_pair() + [observation("ixic", DAYS[2], 121)]
        rows = self.build(observations, targets=[target("2026-01-07"), target()]).rows
        self.assertEqual(rows[0]["target_date"], "2026-01-06")
        self.assertIsNone(rows[0]["ixic_is_new_session_since_previous_tw_target"])
        self.assertTrue(rows[1]["ixic_is_new_session_since_previous_tw_target"])

    def test_inputs_are_not_mutated_and_report_is_standard_json(self):
        observations, sessions, targets = self.price_pair(), calendars(), [target()]
        expected = copy.deepcopy((observations, sessions, targets))
        result = build_market_features(observations, sessions, targets)
        self.assertEqual((observations, sessions, targets), expected)
        json.dumps(result.report, allow_nan=False)
        json.dumps(result.rows, allow_nan=False)

    def test_fetched_later_is_valid_for_historical_publication_evidence(self):
        row = self.build(self.price_pair()).rows[0]
        self.assertAlmostEqual(row["ixic_ret_1s"], 0.1)

    def test_equivalent_utc_and_taipei_cutoffs_select_identical_information(self):
        taipei = self.build(self.price_pair()).rows[0]
        utc_row = self.build(self.price_pair(), targets=[target(cutoff="2026-01-06T00:10:00Z")]).rows[0]
        for key in FEATURES + ("ixic_source_session_date", "ixic_age_hours"):
            self.assertEqual(taipei[key], utc_row[key])

    def test_cutoff_on_previous_utc_date_is_valid_for_its_taipei_target(self):
        row = self.build(
            self.price_pair(), targets=[target(cutoff="2026-01-05T23:30:00+00:00")],
        ).rows[0]
        self.assertEqual(row["target_date"], "2026-01-06")
        self.assertAlmostEqual(row["ixic_ret_1s"], 0.1)

    def test_official_0900_taipei_deadline_is_inclusive(self):
        row = self.build(
            self.price_pair(), targets=[target(cutoff="2026-01-06T09:00:00+08:00")],
        ).rows[0]
        self.assertAlmostEqual(row["ixic_ret_1s"], 0.1)

    def test_cutoff_one_microsecond_after_official_deadline_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build([], targets=[target(cutoff="2026-01-06T09:00:00.000001+08:00")])

    def test_cutoff_days_after_target_cannot_smuggle_future_data_into_history(self):
        with self.assertRaises(ValueError):
            self.build([], targets=[target("2026-07-03", "2026-07-07T08:10:00+08:00")])

    def test_new_york_dst_offsets_are_respected_in_age_and_cutoff(self):
        ny = ZoneInfo("America/New_York")
        for previous_day, current_day, target_day, expected_age in (
            ("2026-03-06", "2026-03-09", "2026-03-10", 4 + 5 / 60),
            ("2026-01-30", "2026-02-02", "2026-02-03", 3 + 5 / 60),
        ):
            with self.subTest(current_day=current_day):
                observations = []
                for day, value in ((previous_day, 100), (current_day, 110)):
                    event = datetime.fromisoformat(day).replace(hour=16, tzinfo=ny)
                    available = event + timedelta(minutes=5)
                    observations.append(observation(
                        "ixic", day, value, available=available.isoformat(), event_time=event.isoformat(),
                    ))
                row = self.build(
                    observations, sessions=calendars([previous_day, current_day]),
                    targets=[target(target_day)],
                ).rows[0]
                self.assertAlmostEqual(row["ixic_ret_1s"], 0.1)
                self.assertAlmostEqual(row["ixic_age_hours"], expected_age)

    def test_naive_timestamp_is_rejected_in_each_required_time_field(self):
        for field in ("event_time", "published_at", "available_at", "fetched_at"):
            with self.subTest(field=field):
                record = observation("ixic", DAYS[1], 110)
                record[field] = "2026-01-05T21:00:00"
                with self.assertRaises(ValueError):
                    self.build([record])
        with self.assertRaises(ValueError):
            self.build([], targets=[target(cutoff="2026-01-06T08:10:00")])

    def test_available_at_cannot_precede_event_or_publication(self):
        for field in ("event_time", "published_at"):
            with self.subTest(field=field):
                record = observation("ixic", DAYS[1], 110)
                record[field] = "2026-01-05T22:00:00+00:00"
                with self.assertRaises(ValueError):
                    self.build([record])

    def test_duplicate_version_keys_are_rejected_even_when_values_match(self):
        record = observation("ixic", DAYS[1], 110)
        with self.assertRaises(ValueError):
            self.build([record, copy.deepcopy(record)])

    def test_same_session_same_available_at_is_an_ambiguous_revision_tie(self):
        records = [observation("ixic", DAYS[1], 110), observation("ixic", DAYS[1], 120, revision="r2")]
        with self.assertRaises(ValueError):
            self.build(records)

    def test_duplicate_target_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            self.build([], targets=[target(), target(cutoff="2026-01-06T08:20:00+08:00")])

    def test_calendar_must_be_unique_sorted_and_cover_every_observation(self):
        for bad_days in ([DAYS[1], DAYS[0]], [DAYS[0], DAYS[0]], [DAYS[0]]):
            with self.subTest(days=bad_days):
                with self.assertRaises(ValueError):
                    self.build(self.price_pair(), sessions=calendars(bad_days))
        with self.assertRaises(ValueError):
            self.build(self.price_pair(), sessions={})

    def test_series_cannot_mix_providers_or_disagree_with_its_calendar(self):
        mixed = self.price_pair()
        mixed[-1]["source"] = "other-provider"
        with self.assertRaises(ValueError):
            self.build(mixed)
        sessions = calendars()
        sessions["ixic"]["source"] = "different-calendar-provider"
        with self.assertRaises(ValueError):
            self.build(self.price_pair(), sessions=sessions)

    def test_unverified_availability_or_missing_evidence_is_rejected(self):
        for field, value in (("availability_basis", "unverified"), ("availability_evidence", "")):
            with self.subTest(field=field):
                record = observation("ixic", DAYS[1], 110)
                record[field] = value
                with self.assertRaises(ValueError):
                    self.build([record])
        sessions = calendars()
        sessions["ixic"]["calendar_evidence"] = ""
        with self.assertRaises(ValueError):
            self.build(self.price_pair(), sessions=sessions)

    def test_unknown_series_wrong_units_and_empty_feature_version_are_rejected(self):
        for record in (
            observation("unknown", DAYS[1], 110),
            observation("ixic", DAYS[1], 110, unit="contracts"),
            observation("tx_foreign_net_oi", DAYS[1], -10, unit="percent"),
        ):
            with self.subTest(series=record["series_id"], unit=record["unit"]):
                with self.assertRaises(ValueError):
                    self.build([record])
        with self.assertRaises(ValueError):
            self.build([], feature_version="")

    def test_source_url_cannot_include_credentials_or_query_secrets(self):
        for url in ("https://user:pass@example.org/data", "https://example.org/data?token=secret", "https://example.org/data#secret"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.build([observation("ixic", DAYS[1], 110, source_url=url)])

    def test_payload_hash_must_be_real_sha256_shape(self):
        with self.assertRaises(ValueError):
            self.build([observation("ixic", DAYS[1], 110, payload_sha256="not-a-hash")])


if __name__ == "__main__":
    unittest.main()
