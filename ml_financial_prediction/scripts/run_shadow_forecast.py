"""Create immutable research-only prospective forecasts, fully offline; never submit."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.pipelines.shadow import run_shadow_forecast


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--trusted-model-dir', type=Path, required=True,
                        help='Locally controlled research ModelBundle; joblib can execute code')
    parser.add_argument('--prediction-table', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--session-evidence', type=Path, required=True)
    parser.add_argument('--target-date', help='Does not bypass the actual current clock')
    args = parser.parse_args()
    try:
        result = run_shadow_forecast(
            args.runtime_dir, trusted_model_dir=args.trusted_model_dir,
            prediction_table=args.prediction_table, template_path=args.template,
            session_evidence_path=args.session_evidence, target_date=args.target_date)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Never expose arbitrary input text, paths or raw source response content.
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
