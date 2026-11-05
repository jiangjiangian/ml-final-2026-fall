"""Validate or submit one fixed Phase 1 forecast; never modify Phase 2 approval."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.submission.phase1 import read_input_bytes  # noqa: E402
from finpred.submission.phase1_submit import (  # noqa: E402
    Phase1SubmissionClient, execute_phase1_submission,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True, type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--forecast-manifest', required=True, type=Path)
    parser.add_argument('--runtime-dir', required=True, type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--submit', action='store_true', help='Perform the already-authorized Phase 1 POST')
    operation.add_argument('--verify-only', action='store_true', help='Reconcile a receipt without any prediction POST')
    args = parser.parse_args()
    client = None
    try:
        csv_bytes = read_input_bytes(args.csv)
        template = read_input_bytes(args.template)
        client = Phase1SubmissionClient()
        client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
        result = execute_phase1_submission(
            client, csv_bytes, template, args.runtime_dir, forecast_manifest=args.forecast_manifest,
            file_name=args.csv.name, dry_run=not (args.submit or args.verify_only), verify_only=args.verify_only)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['status'] == 'verified' or (
            result['status'] == 'dry_run' and result['would_submit']) else 1
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'detail': 'Phase 1 submission failed or remains unverified; private ledger retained.'}))
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == '__main__':
    raise SystemExit(main())
