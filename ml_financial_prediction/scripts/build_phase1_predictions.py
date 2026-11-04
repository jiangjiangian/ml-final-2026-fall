"""Format or validate existing Phase 1 predictions offline; never train or submit."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.submission.phase1 import (  # noqa: E402
    MAX_TEMPLATE_BYTES, Phase1Error, read_input_bytes, validate_phase1_csv, write_phase1_predictions,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', type=Path, required=True,
                        help='Locally saved official 50 x 84 template; no network access')
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--predictions', type=Path, help='Existing prediction rows JSON; outcome columns rejected')
    inputs.add_argument('--validate-csv', type=Path, help='Validate only; writes no files')
    parser.add_argument('--out-dir', type=Path, help='New artifact directory outside Git; never overwrites')
    args = parser.parse_args()
    if (args.predictions is not None) != (args.out_dir is not None):
        parser.error('--out-dir is required only with --predictions')
    try:
        template = read_input_bytes(args.template, limit=MAX_TEMPLATE_BYTES)
        if args.validate_csv is not None:
            result = validate_phase1_csv(read_input_bytes(args.validate_csv), template)
        else:
            result = write_phase1_predictions(template, read_input_bytes(args.predictions), args.out_dir)
    except (OSError, ValueError, TypeError, KeyError) as error:
        result = {'status': 'blocked', 'error_type': type(error).__name__,
                  'production_eligible': False, 'submitted': False}
        if isinstance(error, Phase1Error):
            result['reason'] = str(error)
        print(json.dumps(result))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
