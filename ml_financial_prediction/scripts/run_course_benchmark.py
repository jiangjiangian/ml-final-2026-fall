"""Run the explicit retrospective-course / prospective-live competition policy."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.pipelines.course_benchmark import run_course_benchmark  # noqa: E402
from finpred.pipelines.daily import PipelineBlocked  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--stage', choices=('train', 'predict', 'submit', 'verify'), required=True)
    parser.add_argument('--target-date')
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    if args.submit and args.stage != 'submit':
        parser.error('--submit applies only to the submit stage')
    try:
        result = run_course_benchmark(args.runtime_dir, args.stage, target_date=args.target_date,
                                      dry_run=not args.submit, initialize=args.initialize)
    except Exception as error:
        result = {'status': 'blocked', 'error_type': type(error).__name__}
        if isinstance(error, PipelineBlocked):
            result['reason'] = str(error)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
