"""Execute the frozen R2 comparison; no production promotion or holdout tuning."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.training.architecture_comparison import compare_architectures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path, required=True)
    parser.add_argument('--feature-rows', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--research-if-unverified', action='store_true')
    parser.add_argument('--quick-smoke', action='store_true')
    parser.add_argument('--folds', type=Path, help='Explicit exploration folds; no 2026 holdout')
    args = parser.parse_args()
    if any((p / '.git').exists() for p in [args.out_dir.resolve(), *args.out_dir.resolve().parents]):
        parser.error('private model and prediction artifacts must stay outside checkout')
    try:
        payload = args.table.read_bytes()
        report = compare_architectures(json.loads(payload), args.out_dir,
                 feature_rows=json.loads(args.feature_rows.read_bytes()) if args.feature_rows else None,
                 config=json.loads(args.config.read_bytes()) if args.config else None,
                 folds=json.loads(args.folds.read_bytes()) if args.folds else None,
                 allow_research=args.research_if_unverified, quick_smoke=args.quick_smoke,
                 loaded_input_bytes=payload)
    except (OSError, ValueError, ImportError) as error:
        parser.error(str(error))
    print(json.dumps({'status': 'evaluated', 'report': str(args.out_dir / 'report.json'),
                      'completed_fit_count': report['completed_fit_count'],
                      'selected': report['validation_selected_configuration'],
                      'beats_baseline': report['beats_baseline'],
                      'production_eligible': False, 'quick_smoke_not_full_research': args.quick_smoke}))


if __name__ == '__main__':
    main()
