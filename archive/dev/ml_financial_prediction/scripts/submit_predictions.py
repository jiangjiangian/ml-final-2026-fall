"""Validate or submit a Phase 2 prediction; credentials are environment-only."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finpred.submission import CourseSubmissionClient, execute_submission  # noqa: E402


def read_prediction_file(path):
    """Bind candidate bytes and generation mtime to one opened inode."""
    with path.open("rb") as stream:
        metadata = os.fstat(stream.fileno())
        payload = stream.read()
    return payload, datetime.fromtimestamp(metadata.st_mtime, timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--readiness", type=Path, help="Pipeline-generated model and availability evidence JSON")
    parser.add_argument("--submit", action="store_true", help="Perform the already-authorized submission after all checks")
    args = parser.parse_args()
    if any((parent / ".git").exists() for parent in (args.runtime_dir.resolve(), *args.runtime_dir.resolve().parents)):
        parser.error("--runtime-dir must be a persistent private location outside Git")
    client = None
    try:
        payload, generated = read_prediction_file(args.csv)
        readiness = json.loads(args.readiness.read_text()) if args.readiness else None
        client = CourseSubmissionClient()
        client.login(os.environ.get("COURSE_EMAIL"), os.environ.get("COURSE_PASSWORD"))
        result = execute_submission(client, payload, args.target_date, args.runtime_dir,
                                    file_name=args.csv.name, dry_run=not args.submit,
                                    generated_at=generated, readiness=readiness)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        # Do not expose source response bodies, credentials or arbitrary exception text.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "detail": "Submission failed or remains unverified; inspect private pipeline state."}),
              file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
