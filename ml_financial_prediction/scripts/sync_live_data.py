"""Export portable raw snapshots; Git publishing requires an explicit flag."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.data.sharing import SharingError, export_snapshot_bundle


def command(arguments, *, cwd=None):
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise SharingError('Git or GitHub operation failed; response omitted')
    return result.stdout.strip()


def require_private_repository(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise SharingError('repository must be an owner/name identifier')
    if command(['gh', 'repo', 'view', repository, '--json', 'isPrivate', '--jq', '.isPrivate']) != 'true':
        raise SharingError('live-data publication requires a verified private repository')


def publication_preflight(directory, repository, *, require_clean=True, require_remote_current=True):
    root = Path(command(['git', 'rev-parse', '--show-toplevel'], cwd=directory)).resolve()
    if root != directory.resolve():
        raise SharingError('publish destination must be the live-data Git worktree root')
    if command(['git', 'branch', '--show-current'], cwd=root) != 'live-data':
        raise SharingError('publishing is restricted to the live-data branch')
    if require_clean and command(['git', 'status', '--porcelain'], cwd=root):
        raise SharingError('live-data worktree must be clean before export and publication')
    remote = command(['git', 'remote', 'get-url', 'origin'], cwd=root)
    parts = urlsplit(remote)
    identity = parts.path.strip('/').removesuffix('.git')
    if (parts.scheme != 'https' or parts.hostname != 'github.com'
            or parts.username or parts.password or identity.lower() != repository.lower()):
        raise SharingError('origin must be the expected credential-free GitHub HTTPS repository')
    if require_remote_current:
        local = command(['git', 'rev-parse', '--verify', 'HEAD^{commit}'], cwd=root)
        remote_head = command(['git', 'ls-remote', '--heads', 'origin', 'refs/heads/live-data'], cwd=root)
        if remote_head and remote_head.split()[0] != local:
            raise SharingError('live-data remote advanced; refresh the worktree before publishing')
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path, action='append', default=[])
    parser.add_argument('--required-source', action='append', default=[])
    parser.add_argument('--repo', required=True, help='Private GitHub owner/repository, never a token')
    parser.add_argument('--publish', action='store_true', help='Commit and push only managed live-data paths')
    parser.add_argument('--build-features', action='store_true',
                        help='Also refresh the explicit research feature/label exports')
    args = parser.parse_args()
    try:
        # Even a filesystem export intended for Git is checked against the named
        # private repository; no course payload is exported to a known public repo.
        require_private_repository(args.repo)
        root = publication_preflight(args.bundle_dir, args.repo) if args.publish else None
        if not args.publish and any((p / '.git').exists() for p in (args.bundle_dir, *args.bundle_dir.parents)):
            publication_preflight(args.bundle_dir, args.repo, require_clean=False, require_remote_current=False)
        result = export_snapshot_bundle(args.runtime_dir, args.bundle_dir,
                                        raw_roots=args.raw_root, required_sources=args.required_source)
        result = {key: value for key, value in result.items() if key != 'latest'}
        if args.build_features:
            # Missing historical evidence or feature construction must never
            # prevent publication of newly acquired, valid raw snapshots.
            try:
                from finpred.data.shared_features import build_shared_features
                result['features'] = build_shared_features(args.runtime_dir, args.bundle_dir,
                                                           allow_research=True)
            except Exception as error:
                result['features'] = {'status': 'blocked', 'error_type': type(error).__name__}
        if root is not None:
            managed = ['objects', 'manifests', 'catalog']
            if args.build_features:
                managed += [name for name in ('features', 'labels')
                            if (root / name).exists() or command(['git', 'ls-files', '--', name], cwd=root)]
            command(['git', 'add', '-A', '--', *managed], cwd=root)
            staged = command(['git', 'diff', '--cached', '--name-only'], cwd=root)
            if staged:
                command(['git', 'commit', '-m', 'Update immutable live-data snapshots'], cwd=root)
                # No force option: a competing writer must cause a safe failure.
                command(['git', 'push', 'origin', 'HEAD:refs/heads/live-data'], cwd=root)
                result['publication'] = 'pushed'
            else:
                result['publication'] = 'unchanged'
            result['git_revision'] = command(['git', 'rev-parse', 'HEAD'], cwd=root)
        else:
            result['publication'] = 'not_requested'
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'detail': 'Sharing validation or Git publication failed; source data and responses omitted.'}),
              file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
