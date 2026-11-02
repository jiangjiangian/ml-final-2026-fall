"""Fetch one private live-data Git revision and restore verified local snapshots."""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.sharing import (
    SharingError, import_shared_feature_exports, import_snapshot_bundle,
)
from sync_live_data import command, require_private_repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='Private GitHub owner/repository')
    parser.add_argument('--revision', required=True, help='40-character commit SHA, or live-data to resolve current version')
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--with-features', action='store_true',
                        help='Also restore hash-verified research features/labels to runtime/shared-data')
    args = parser.parse_args()
    stage = 'private_repository_verification'
    try:
        require_private_repository(args.repo)
        stage = 'revision_validation'
        if not re.fullmatch(r'[a-f0-9]{40}|live-data', args.revision):
            raise SharingError('revision must be a pinned commit SHA or live-data')
        with tempfile.TemporaryDirectory(prefix='finpred-live-data-') as temporary:
            root = Path(temporary)
            stage = 'git_transport'
            command(['git', 'init', '-q', str(root)])
            command(['git', 'remote', 'add', 'origin', 'https://github.com/' + args.repo + '.git'], cwd=root)
            ref = 'refs/heads/live-data' if args.revision == 'live-data' else args.revision
            command(['git', 'fetch', '--no-tags', '--depth=1', 'origin', ref], cwd=root)
            revision = command(['git', 'rev-parse', '--verify', 'FETCH_HEAD^{commit}'], cwd=root)
            command(['git', '-c', 'core.hooksPath=/dev/null', 'checkout', '-q', '--detach', 'FETCH_HEAD'], cwd=root)
            stage = 'raw_snapshot_validation_and_import'
            result = import_snapshot_bundle(root, args.runtime_dir, revision=revision)
            result['requested_revision'] = args.revision
            if args.with_features:
                stage = 'derived_feature_validation_and_import'
                result['features'] = import_shared_feature_exports(root, args.runtime_dir, revision=revision)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'failure_stage': stage,
                          'detail': 'Private data fetch or integrity validation failed; responses omitted.'}),
              file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    if args.with_features and result['features']['status'] != 'imported':
        return 2  # Raw succeeded; the explicitly requested derived export is blocked.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
