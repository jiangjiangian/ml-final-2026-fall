"""Build deterministic research exports for an explicitly private live-data bundle."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.shared_features import build_shared_features  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--allow-research', action='store_true', required=True)
    args = parser.parse_args()
    try:
        result = build_shared_features(args.runtime_dir, args.bundle_dir,
                                       allow_research=args.allow_research)
    except (OSError, ValueError, TypeError, KeyError, ImportError):
        print(json.dumps({'status': 'failed', 'detail': 'Source integrity, schema or feature export validation failed.'}),
              file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
