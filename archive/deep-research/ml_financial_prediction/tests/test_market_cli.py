"""Exercise the real CLI, file formats, manifests and failure behavior."""

import csv
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]


class MarketCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        subprocess.run(
            [sys.executable, str(PROJECT / "scripts/create_market_demo.py"),
             "--out-dir", str(self.directory)], check=True, capture_output=True,
        )
        self.output = self.directory / "features.csv"
        self.report = self.directory / "report.json"

    def run_cli(self, *, output=None, report=None):
        return subprocess.run([
            sys.executable, str(PROJECT / "scripts/build_market_features.py"),
            "--observations", str(self.directory / "observations.json"),
            "--sessions", str(self.directory / "sessions.json"),
            "--targets", str(self.directory / "targets.csv"),
            "--out", str(output or self.output), "--report", str(report or self.report),
        ], cwd=self.directory, capture_output=True, text=True)

    def test_real_cli_serializes_expected_market_values_and_complete_manifest(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["target_count"], 3)
        with self.output.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["target_date"] for r in rows], ["2026-07-03", "2026-07-06", "2026-07-07"])
        self.assertAlmostEqual(float(rows[0]["ixic_ret_1s"]), 0.1)
        self.assertAlmostEqual(float(rows[1]["ixic_ret_1s"]), 0.1)
        self.assertAlmostEqual(float(rows[2]["ixic_ret_1s"]), -0.1)
        self.assertEqual(rows[1]["ixic_is_new_session_since_previous_tw_target"], "False")
        self.assertAlmostEqual(float(rows[1]["twii_ret_1s"]), 0.02)
        self.assertEqual(float(rows[1]["vix_change_points"]), 2)
        self.assertEqual(float(rows[1]["tx_foreign_net_oi_change"]), 10)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["target_count"], 3)
        self.assertEqual(len(report["feature_columns"]), 8)
        manifest = report["manifest"]
        self.assertEqual(manifest["output_csv_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        for key, filename in (("observations", "observations.json"),
                              ("sessions", "sessions.json"), ("targets", "targets.csv")):
            self.assertEqual(manifest["input_sha256"][key],
                             hashlib.sha256((self.directory / filename).read_bytes()).hexdigest())
        self.assertIn("src/finpred/features/market.py", manifest["code_sha256"])

    def test_repeat_execution_produces_identical_feature_csv(self):
        self.assertEqual(self.run_cli().returncode, 0)
        before = self.output.read_bytes()
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.output.read_bytes(), before)

    def test_manifest_hashes_the_parsed_snapshot_when_inputs_change_during_the_run(self):
        observations_path = self.directory / "observations.json"
        original_payload = observations_path.read_bytes()
        original_records = json.loads(original_payload)
        expected_current = next(
            record for record in original_records
            if record["series_id"] == "ixic" and record["session_date"] == "2026-07-02"
        )
        replacement = [dict(record) for record in original_records]
        for record in replacement:
            if record["series_id"] == "ixic" and record["session_date"] == "2026-07-02":
                record["value"] = 990
                record["payload_sha256"] = "f" * 64
        changed_payload = (json.dumps(replacement, indent=2) + "\n").encode()
        self.assertNotEqual(original_payload, changed_payload)

        spec = importlib.util.spec_from_file_location(
            "market_cli_snapshot_test", PROJECT / "scripts/build_market_features.py",
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)

        def replace_input_during_manifest_creation():
            observations_path.write_bytes(changed_payload)
            return {"python": "synthetic-test", "code_sha256": {}}

        argv = [
            "build_market_features.py", "--observations", str(observations_path),
            "--sessions", str(self.directory / "sessions.json"),
            "--targets", str(self.directory / "targets.csv"),
            "--out", str(self.output), "--report", str(self.report),
        ]
        with patch.object(cli, "code_manifest", side_effect=replace_input_during_manifest_creation) as manifest:
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                cli.main()
        manifest.assert_called_once_with()
        report = json.loads(self.report.read_text())
        self.assertEqual(observations_path.read_bytes(), changed_payload)
        recorded_hash = report["manifest"]["input_sha256"]["observations"]
        self.assertEqual(recorded_hash, hashlib.sha256(original_payload).hexdigest())
        self.assertNotEqual(recorded_hash, hashlib.sha256(changed_payload).hexdigest())
        trace = report["targets"][0]["series"]["ixic"]["current"]
        self.assertEqual(trace["value"], expected_current["value"])
        self.assertEqual(trace["payload_sha256"], expected_current["payload_sha256"])
        with self.output.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertAlmostEqual(float(rows[0]["ixic_ret_1s"]), 0.1)
        self.assertNotAlmostEqual(float(rows[0]["ixic_ret_1s"]), 8.9)

    def test_date_only_teacher_rows_fail_without_overwriting_existing_outputs(self):
        (self.directory / "observations.json").write_text('[{"date":"2026-07-02","^IXIC":110}]')
        self.output.write_text("preserve CSV")
        self.report.write_text("preserve report")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data-contract", result.stderr)
        self.assertEqual(self.output.read_text(), "preserve CSV")
        self.assertEqual(self.report.read_text(), "preserve report")

    def test_same_output_paths_and_input_overwrite_are_rejected(self):
        self.assertNotEqual(self.run_cli(report=self.output).returncode, 0)
        path = self.directory / "observations.json"
        before = path.read_bytes()
        self.assertNotEqual(self.run_cli(output=path).returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_ambiguous_json_keys_are_rejected(self):
        (self.directory / "sessions.json").write_text('{"ixic":{},"ixic":{}}')
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate JSON", result.stderr)
        self.assertFalse(self.output.exists())

    def test_malformed_target_row_width_is_rejected(self):
        (self.directory / "targets.csv").write_text("target_date,feature_cutoff\n2026-07-03\n")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("row width", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
