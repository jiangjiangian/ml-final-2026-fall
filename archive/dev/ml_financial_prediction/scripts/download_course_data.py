"""Download authorized course snapshots; secrets are read only from environment."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.ingestion.course import download_course_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=('training', 'live', 'both'), default='both')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--live-key-env', default='COURSE_LIVE_KEY', help='Environment variable name, never the key value')
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]
    if args.out_dir.resolve().is_relative_to(checkout):
        parser.error('raw snapshots must be stored outside this Git checkout')
    try:
        records = download_course_sources(args.out_dir, args.source, live_key=os.environ.get(args.live_key_env))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'detail': 'See private failure manifest; credentials and response omitted.'}), file=sys.stderr)
        return 1
    print(json.dumps({'status': 'downloaded_and_audited', 'snapshots': [
        {'source': record['source'], 'sha256': record['sha256'], 'size_bytes': record['size_bytes'],
         'manifest_path': record['manifest_path']} for record in records]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
