"""Normalize evidenced course input or build explicitly assumed research history."""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.data.normalization import (  # noqa: E402
    build_history_market_features, normalize_course_market,
)
from finpred.features.market import build_market_features  # noqa: E402


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--history-root", type=Path)
    source.add_argument("--course-zip", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--calendars", type=Path)
    parser.add_argument("--policies", type=Path)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=("strict", "research"), default="strict")
    parser.add_argument("--allow-research", action="store_true")
    args = parser.parse_args()
    if args.mode == "research" and not args.allow_research:
        parser.error("research assumptions require explicit --allow-research")
    if args.out.resolve() == args.report.resolve():
        parser.error("CSV and report must be different paths")
    inputs = [p for p in (args.course_zip, args.snapshot_manifest, args.calendars,
                         args.policies, args.targets) if p is not None]
    if {p.resolve() for p in inputs} & {args.out.resolve(), args.report.resolve()}:
        parser.error("outputs must not overwrite inputs")
    try:
        raw_targets = args.targets.read_bytes()
        reader = csv.DictReader(io.StringIO(raw_targets.decode("utf-8-sig")))
        if reader.fieldnames != ["target_date", "feature_cutoff"]:
            raise ValueError("targets require target_date,feature_cutoff")
        targets = list(reader)
        if args.history_root:
            manifests = []
            for directory in sorted(args.history_root.glob("yahoo-*/manifests")):
                candidates = sorted(directory.glob("*.json"))
                if candidates:
                    manifests.append(candidates[-1])
            if not manifests:
                raise ValueError("no immutable history manifests found")
            result = build_history_market_features(manifests, targets, mode=args.mode)
        else:
            if any(p is None for p in (args.snapshot_manifest, args.calendars, args.policies)):
                raise ValueError("course normalization requires explicit snapshot/calendar/policy files")
            archive_bytes = args.course_zip.read_bytes()
            snapshot = json.loads(args.snapshot_manifest.read_text())
            if hashlib.sha256(archive_bytes).hexdigest() != snapshot["sha256"]:
                raise ValueError("course archive differs from snapshot manifest")
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                rows = list(csv.DictReader(io.StringIO(archive.read("data/global/global_data.csv").decode("utf-8-sig"))))
            prepared = normalize_course_market(rows, json.loads(args.calendars.read_text()),
                                               json.loads(args.policies.read_text()), snapshot, mode=args.mode)
            if prepared["report"]["readiness"] == "blocked":
                result = {"rows": [], "report": prepared["report"]}
            else:
                features = build_market_features(prepared["observations"], prepared["native_sessions"], targets,
                                                 feature_version="research-history-v1" if args.mode == "research" else "course-evidenced-v1")
                result = {"rows": features.rows, "report": {**features.report, **prepared["report"]}}
        result["report"]["target_sha256"] = hashlib.sha256(raw_targets).hexdigest()
        result["report"]["feature_version"] = "research-history-v1" if args.mode == "research" else "course-evidenced-v1"
        if result["report"]["readiness"] == "blocked":
            _write(args.report, json.dumps(result["report"], ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"status": "blocked", "report": str(args.report)}))
            return 2
        if not result["rows"]:
            raise ValueError("targets must be nonempty")
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(result["rows"][0]))
        writer.writeheader()
        writer.writerows(result["rows"])
        content = buffer.getvalue()
        result["report"]["output_csv_sha256"] = hashlib.sha256(content.encode()).hexdigest()
        _write(args.out, content)
        _write(args.report, json.dumps(result["report"], ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"status": result["report"]["readiness"], "rows": len(result["rows"]),
                          "out": str(args.out), "report": str(args.report)}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile):
        print(json.dumps({"status": "failed", "detail": "input, policy, schema or storage validation failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
