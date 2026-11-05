"""Run one daily stage. Dry run permits reads/training but never prediction POST."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.pipelines.daily import STAGES, PipelineBlocked, run_stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--target-date')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Default: reads and computation allowed, no prediction POST')
    mode.add_argument('--submit', action='store_true', help='Explicit prediction POST authorization for submit stage')
    parser.add_argument('--training-table', type=Path)
    parser.add_argument('--prediction-table', type=Path)
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--allow-research-training', action='store_true', help='Manual research only; never promote or submit')
    args = parser.parse_args()
    if args.submit and args.stage != 'submit':
        parser.error('--submit is only valid with --stage submit')
    if args.allow_research_training and args.stage != 'train':
        parser.error('--allow-research-training is only valid with --stage train')
    try:
        result = run_stage(args.runtime_dir, args.stage, target_date=args.target_date,
                           dry_run=not args.submit, training_table=args.training_table,
                           prediction_table=args.prediction_table, csv_path=args.csv,
                           allow_research_training=args.allow_research_training)
    except Exception as error:
        result = {'status': 'blocked', 'error_type': type(error).__name__}
        if isinstance(error, PipelineBlocked):
            result['reason'] = str(error)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return int(result.get('status') in {'blocked', 'partial'})


if __name__ == '__main__':
    raise SystemExit(main())
