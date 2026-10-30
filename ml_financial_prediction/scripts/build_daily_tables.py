"""Prepare stock-only daily tables from private immutable course acquisitions."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.daily_tables import prepare_prediction_table, prepare_training_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--target-date', required=True)
    parser.add_argument('--kind', choices=('training', 'prediction'), required=True)
    parser.add_argument('--allow-research', action='store_true')
    args = parser.parse_args()
    if args.allow_research and args.kind != 'training':
        parser.error('--allow-research is only valid for training')
    try:
        result = (prepare_training_table(args.runtime_dir, args.target_date, args.allow_research)
                  if args.kind == 'training' else prepare_prediction_table(args.runtime_dir, args.target_date))
    except (ValueError, OSError):
        print(json.dumps({'status': 'blocked', 'reason': 'invalid target date or private runtime'}))
        return 2
    print(json.dumps({key: value for key, value in result.items() if key != 'report'}, ensure_ascii=False))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
