"""Run the explicit course-benchmark policy with durable Git checkpoints.

This adapter preserves the separate strict-PIT service. Its course policy records
the historical-vintage assumption and verifies actual current input availability.
Push rehearsals restore data without training, authentication or prediction POSTs.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))
sys.path.insert(0, str(PROJECT / 'scripts'))

from runtime_store import (  # noqa: E402
    HostedBlocked, PrivateGitStore, no_symlink, pack_runtime, restore_runtime,
    write_json, write_private,
)
from run_hosted_pipeline import collect_raw, durable_submission_client  # noqa: E402
from finpred.data.sharing import export_snapshot_bundle, import_snapshot_bundle  # noqa: E402
from finpred.labels.intraday import aware_datetime  # noqa: E402
from finpred.pipelines.daily import TAIPEI, _at, _private_file_bytes  # noqa: E402

HOSTED_RUNTIME = Path('/tmp/finpred-hosted-runtime')
POLICY = 'course-benchmark-v1'
MODES = ('rehearsal', 'initialize', 'train', 'predict', 'submit', 'verify')


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _now(clock):
    return aware_datetime(clock(), name='hosted course clock')


def _collect_child(queue, root):
    try:
        queue.put(collect_raw(root))
    except Exception as error:
        queue.put({'status': 'partial', 'failures': [{'source': 'hosted-collection',
                                                    'error_type': type(error).__name__}]})


def bounded_collection(root, timeout_seconds):
    """Stop slow source downloads before they consume the training window."""
    if timeout_seconds <= 0:
        raise HostedBlocked('no time remains for course training collection')
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    worker = context.Process(target=_collect_child, args=(queue, root))
    worker.start()
    timed_out = False
    try:
        try:
            result = queue.get(timeout=timeout_seconds)
        except Exception:
            timed_out = True
            result = {'status': 'partial', 'failures': [
                {'source': 'hosted-collection', 'error_type': 'CollectionTimeout'}]}
    finally:
        worker.join(timeout=0.1)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
            if worker.is_alive():
                worker.kill()
                worker.join()
        queue.close()
    if timed_out:
        # Write only after stopping the child so it cannot race this status.
        # Finished immutable snapshots remain available to the bundle exporter.
        write_json(Path(root) / 'latest_collection.json', {**result, 'manifests': []})
    return result


def _pointer(root):
    return root / 'candidates' / POLICY / 'approved.json'


def _publication_marker(root):
    return root / 'candidates' / POLICY / 'hosted-approved.json'


def verify_hosted_approval(root):
    """A locally written pointer alone cannot prove completed remote publication."""
    pointer = _private_file_bytes(_pointer(root))
    marker = json.loads(_private_file_bytes(_publication_marker(root)))
    if (not isinstance(marker, dict)
            or marker.get('schema_version') != 'hosted-course-approval-v1'
            or marker.get('policy') != POLICY
            or marker.get('approved_pointer_sha256') != _digest(pointer)
            or not re.fullmatch(r'[a-f0-9]{40}', str(marker.get('published_commit', '')))
            or marker.get('hosted_persistence_eligible') is not True):
        raise HostedBlocked('course approval requires its matching durable publication record')
    published = aware_datetime(marker.get('published_at'), name='course model published_at')
    if marker.get('initialize') is not True:
        deadline = aware_datetime(marker.get('deadline'), name='course model publication deadline')
        if published >= deadline:
            raise HostedBlocked('course approval was published after its training deadline')
    return marker


def _publish_model(root, data_root, store, day, *, clock, initialize, previous):
    pointer = _private_file_bytes(_pointer(root))
    try:
        pack_runtime(root, data_root)
        commit = store.publish('Persist explicit course-benchmark model approval')
    except BaseException:
        if previous is None:
            _pointer(root).unlink(missing_ok=True)
        else:
            write_private(_pointer(root), previous)
        raise
    published = _now(clock)
    deadline = None if initialize else _at(day, 7, 50)
    if deadline is not None and published >= deadline:
        # Keep the lease while rolling the pointer back. Even a crash before this
        # rollback leaves no matching eligible hosted approval for the new hash.
        if previous is None:
            _pointer(root).unlink(missing_ok=True)
        else:
            write_private(_pointer(root), previous)
        raise HostedBlocked('course model missed durable publication deadline; previous approval retained')
    marker = {'schema_version': 'hosted-course-approval-v1', 'policy': POLICY,
              'approved_pointer_sha256': _digest(pointer), 'prediction_posted': False,
              'published_commit': commit, 'published_at': published.isoformat(),
              'deadline': None if deadline is None else deadline.isoformat(),
              'initialize': initialize, 'hosted_persistence_eligible': True,
              'historical_vintage_verified': False}
    write_json(_publication_marker(root), marker)
    return marker


def run_hosted_course(data_root, repository, *, mode='rehearsal',
                      runtime_root=HOSTED_RUNTIME, target_date=None, submit=False,
                      allow_public_data=False, clock=None, store_factory=PrivateGitStore,
                      stage_runner=None, client_factory=durable_submission_client,
                      collector=bounded_collection):
    """CLI uses the real clock. Tests may inject isolated stores and stage runners."""
    if mode not in MODES:
        raise HostedBlocked('unknown hosted course stage')
    if submit and mode != 'submit':
        raise HostedBlocked('course POST flag applies only to the submit stage')
    if submit and os.environ.get('FINPRED_SUBMISSION_RELEASED') != 'true':
        raise HostedBlocked('course submission release gate is not enabled')
    clock = clock or (lambda: datetime.now(timezone.utc))
    root = Path(runtime_root).absolute()
    no_symlink(root)
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise HostedBlocked('hosted course runtime must remain outside Git')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise HostedBlocked('hosted course runtime must be locally owned with mode 0700')
    store = (store_factory(data_root, repository, allow_public_data=True) if allow_public_data
             else store_factory(data_root, repository))
    imported = import_snapshot_bundle(data_root, root, revision=store.parent)
    restored = restore_runtime(data_root, root)
    if mode == 'rehearsal':
        return {'status': 'course_rehearsal_passed', 'policy': POLICY,
                'source_revision': store.parent, 'import_status': imported['status'],
                'runtime_restore': restored, 'prediction_posted': False,
                'historical_vintage_verified': False}
    if stage_runner is None:
        from finpred.pipelines.course_benchmark import run_course_benchmark
        stage_runner = run_course_benchmark
    day = target_date or _now(clock).astimezone(TAIPEI).date().isoformat()
    initialize = mode == 'initialize'
    stage = 'train' if initialize else mode
    store.acquire()
    client = None
    try:
        previous = _private_file_bytes(_pointer(root)) if _pointer(root).exists() else None
        collection = None
        if stage == 'train':
            started = _now(clock)
            if not initialize and not _at(day, 7, 20) <= started < _at(day, 7, 50):
                raise HostedBlocked('scheduled course training requires 07:20-07:50 Taipei')
            budget = 180 if initialize else min(180, (_at(day, 7, 50) - started).total_seconds() - 15)
            collection = collector(root, budget)
            # Source sharing remains useful even if model fitting later blocks.
            export_snapshot_bundle(root, data_root, required_sources=collection.get('required_sources', ()))
            try:
                from finpred.data.shared_features import build_shared_features
                collection['features'] = build_shared_features(root, data_root, allow_research=True)
            except Exception as error:
                collection['features'] = {'status': 'blocked', 'error_type': type(error).__name__}
                collection['status'] = 'partial'
            write_json(Path(data_root) / 'catalog/collection-status.json', collection)
            if not initialize and _now(clock) >= _at(day, 7, 50):
                raise HostedBlocked('collection missed course training deadline; previous approval retained')
        if stage in {'predict', 'submit', 'verify'}:
            verify_hosted_approval(root)
        client = client_factory(root, store)
        client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
        result = stage_runner(root, stage, target_date=day, dry_run=not submit,
                              initialize=initialize, client=client, clock=clock)
        if collection is not None:
            result['collection'] = {'status': collection['status'],
                                    'failed_source_count': len(collection.get('failures', []))}
        if stage == 'train':
            current = _private_file_bytes(_pointer(root)) if _pointer(root).exists() else None
            needs_publication = current is not None and current != previous
            if current is not None and not needs_publication:
                marker = _publication_marker(root)
                if marker.exists():
                    # Unsafe ownership/path evidence remains a hard failure;
                    # only a missing or invalid publication record is repaired.
                    _private_file_bytes(marker)
                    try:
                        verify_hosted_approval(root)
                    except (HostedBlocked, ValueError, TypeError, KeyError):
                        needs_publication = True
                else:
                    needs_publication = True
                if needs_publication:
                    # A crash after publishing a new pointer may leave an old
                    # marker. Recheck its complete local chain and publish at
                    # the real retry time, without another model fit or a
                    # backdated training deadline.
                    from finpred.pipelines.course_benchmark import load_course_approved

                    retry_at = _now(clock)
                    if not initialize and retry_at >= _at(day, 7, 50):
                        raise HostedBlocked('course approval recovery missed publication deadline')
                    load_course_approved(root, now=retry_at)
            if current is not None and needs_publication:
                result['hosted_approval'] = _publish_model(
                    root, data_root, store, day, clock=clock, initialize=initialize, previous=previous)
            elif current is not None:
                verify_hosted_approval(root)
        attempted = bool(getattr(client, 'post_attempted', False))
        verified = result.get('status') == 'verified'
        return {**result, 'policy': POLICY, 'source_revision': imported['git_revision'],
                'prediction_post_attempted': attempted, 'receipt_verified': verified,
                'prediction_posted': bool(attempted and verified),
                'historical_vintage_verified': False}
    finally:
        if client is not None:
            client.close()
        pack_runtime(root, data_root)
        store.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=MODES, default='rehearsal')
    parser.add_argument('--target-date')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--allow-public-data', action='store_true')
    args = parser.parse_args()
    try:
        result = run_hosted_course(args.data_dir, args.repository, mode=args.mode,
                                   target_date=args.target_date, submit=args.submit,
                                   allow_public_data=args.allow_public_data)
    except Exception as error:
        # Never echo exception text, source responses, sessions or account state.
        print(json.dumps({'status': 'blocked', 'policy': POLICY,
                          'error_type': type(error).__name__, 'prediction_posted': False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
