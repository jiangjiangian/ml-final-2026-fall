"""Build point-in-time M0 features from normalized, evidenced observations."""

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from finpred.features.market import build_market_features  # noqa: E402


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def load_json(payload):
    return json.loads(payload.decode("utf-8-sig"), object_pairs_hook=unique_object)


def code_manifest():
    paths = sorted((PROJECT / "src").rglob("*.py")) + [Path(__file__).resolve()]
    result = {"python": platform.python_version(), "code_sha256": {
        str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }}
    try:
        result["code_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        result["working_tree_dirty"] = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=PROJECT, text=True,
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        result["code_commit"] = None
        result["working_tree_dirty"] = None
    return result


def stage(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False,
    ) as stream:
        stream.write(text)
        return Path(stream.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--feature-version", default="m0-v1")
    args = parser.parse_args()
    staged = []
    try:
        inputs = (args.observations, args.sessions, args.targets)
        outputs = (args.out, args.report)
        if len({p.resolve() for p in outputs}) != 2:
            raise ValueError("Feature CSV and report must have distinct paths")
        if {p.resolve() for p in inputs} & {p.resolve() for p in outputs}:
            raise ValueError("Output paths must not overwrite input data")
        # Hash exactly the bytes used below, even if an upstream writer replaces a file.
        payloads = {name: path.read_bytes() for name, path in zip(
            ("observations", "sessions", "targets"), inputs,
        )}
        observations = load_json(payloads["observations"])
        sessions = load_json(payloads["sessions"])
        with io.StringIO(payloads["targets"].decode("utf-8-sig"), newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["target_date", "feature_cutoff"]:
                raise ValueError("Targets CSV header must be target_date,feature_cutoff")
            targets = list(reader)
            if any(None in row or None in row.values() for row in targets):
                raise ValueError("Malformed targets CSV row width")
        result = build_market_features(observations, sessions, targets, args.feature_version)
        buffer = io.StringIO(newline="")
        # The core permits an empty target list; retain the schema in an empty CSV.
        from finpred.features.market import FEATURE_COLUMNS, SERIES_IDS
        fields = ["target_date", "feature_cutoff", "feature_version", *FEATURE_COLUMNS]
        suffixes = ("source_session_date", "source_available_at", "age_hours", "is_missing",
                    "is_new_session_since_previous_tw_target")
        fields += [f"{series}_{suffix}" for series in SERIES_IDS for suffix in suffixes]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result.rows)
        csv_text = buffer.getvalue()
        report = dict(result.report)
        report["manifest"] = {
            **code_manifest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_sha256": {name: hashlib.sha256(payload).hexdigest()
                             for name, payload in payloads.items()},
            "output_csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
            "mode": "historical_asof; fetched_at is provenance, not a historical filter",
        }
        report_text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # Prepare both files before replacing either. On failure, remove only our temp files.
        for path, text in ((args.out, csv_text), (args.report, report_text)):
            staged.append((stage(path, text), path))
        for temporary, destination in staged:
            os.replace(temporary, destination)
        print(json.dumps({"target_count": len(result.rows), "feature_version": args.feature_version,
                          "output": str(args.out), "report": str(args.report)}, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
