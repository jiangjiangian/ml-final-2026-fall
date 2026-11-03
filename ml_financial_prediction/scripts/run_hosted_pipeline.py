"""Run on a GitHub-hosted runner; Git is a private durable store, never a cache."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))

from runtime_store import (  # noqa: E402
    HostedBlocked, PrivateGitStore, pack_runtime, restore_runtime, write_json,
)

TAIPEI = ZoneInfo('Asia/Taipei')
HOSTED_RUNTIME = Path('/tmp/finpred-hosted-runtime')


def collection_failure(source, error):
    """Classify only known adapter errors; never publish arbitrary exception text."""
    from finpred.ingestion.course import CourseDownloadError
    from finpred.ingestion.external import ExternalDataError

    message = str(error)
    category = 'unknown'
    status = None
    if isinstance(error, CourseDownloadError):
        if message == 'COURSE_EMAIL and COURSE_PASSWORD are required':
            category = 'missing_course_credentials'
        elif message == 'course login rejected; response omitted':
            category = 'authentication_rejected'
        elif message == 'published live key not found; set COURSE_LIVE_KEY via secret environment':
            category = 'live_key_unavailable'
        elif message in {'HTTPS request failed; response and credentials omitted',
                         'HTTPS response interrupted; credentials omitted'}:
            category = 'network_or_tls'
        else:
            match = re.fullmatch(r'endpoint returned HTTP ([1-5][0-9]{2}); body omitted', message)
            if match:
                category, status = 'http_error', int(match.group(1))
    elif isinstance(error, ExternalDataError):
        if message == 'External source network or TLS request failed':
            category = 'network_or_tls'
        elif message == 'External source returned HTML instead of data':
            category = 'unexpected_markup'
        else:
            match = re.fullmatch(r'External source returned HTTP ([1-5][0-9]{2})', message)
            if match:
                category, status = 'http_error', int(match.group(1))
    result = {'source': source, 'error_type': type(error).__name__, 'category': category,
              'detail': 'source response and credentials omitted'}
    network_category = getattr(error, 'network_category', None)
    if network_category in {'proxy_failure', 'tls_failure', 'connect_timeout', 'read_timeout',
                            'request_timeout', 'connection_failure', 'request_failure'}:
        result['network_category'] = network_category
    if status is not None:
        result['http_status'] = status
    return result


def select_stage(now):
    local = now.astimezone(TAIPEI)
    minute = local.hour * 60 + local.minute
    if 440 <= minute < 470:
        return 'train'
    if 490 <= minute < 500:
        return 'predict'
    if 500 <= minute < 515:
        return 'submit'
    if 515 <= minute < 540:
        return 'verify'
    raise HostedBlocked('delayed scheduler missed its stage window; no catch-up submission')


def collect_raw(runtime_root, *, clock=None):
    """Collection is independent of labels, model quality and prediction windows."""
    from finpred.ingestion.course import download_course_sources
    from finpred.ingestion.external import SOURCE_SPECS, download_external
    from finpred.ingestion.market_history import (
        HISTORY_SERIES, download_market_history, download_twse_sector_snapshot,
    )
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    end = (now.astimezone(TAIPEI).date() + timedelta(days=1)).isoformat()
    root, records, failures, manifests = Path(runtime_root), [], [], []
    jobs = [('course-' + name, lambda name=name: download_course_sources(root / 'raw', name))
            for name in ('training', 'live')]
    jobs += [(source, lambda source=source: [download_external(source, root / 'raw')])
             for source in SOURCE_SPECS]
    jobs += [('yahoo-' + series, lambda series=series: [download_market_history(
        series, '2019-12-01', end, root / 'raw')]) for series in HISTORY_SERIES]
    jobs += [('twse-sectors', lambda: [download_twse_sector_snapshot(root / 'raw')])]
    for source, job in jobs:
        try:
            acquired = job()
            records.extend({'source': item['source'], 'sha256': item['sha256'],
                            'fetched_at': item['fetched_at']} for item in acquired)
            manifests.extend(item['manifest_path'] for item in acquired)
        except Exception as error:
            failures.append(collection_failure(source, error))
    result = {'status': 'partial' if failures else 'collected', 'acquired': records, 'failures': failures,
              'started_at': now.isoformat(),
              'finished_at': (clock or (lambda: datetime.now(timezone.utc)))().isoformat(),
              'required_sources': sorted({name for name, _ in jobs} | {'course-template'}),
              'historical_availability_verified': False}
    # Export reads this current acquisition status, rather than the previous
    # imported catalog. Absolute paths stay in the private runtime, not logs.
    write_json(root / 'latest_collection.json', {**result, 'manifests': sorted(set(manifests))})
    return result


def durable_submission_client(runtime_root, store):
    from finpred.submission import course as submission
    from finpred.submission.course import CourseSubmissionClient, SubmissionError

    class DurableClient(CourseSubmissionClient):
        post_attempted = False

        def post_predictions(self, target_date, file_name, payload):
            ledger_path = Path(runtime_root) / 'submission' / target_date / 'latest.json'
            if not ledger_path.exists() or json.loads(ledger_path.read_bytes()).get('status') != 'post_in_flight':
                raise SubmissionError('durable hosted POST requires an existing in-flight ledger')
            try:
                pack_runtime(runtime_root, store.root)
                store.publish('Persist in-flight ledger before course prediction POST')
            except Exception:
                raise SubmissionError('durable pre-POST checkpoint failed; prediction was not sent') from None
            # Git publication and state reads consume real time. Recheck the
            # official quota/window after checkpoint, immediately before POST.
            store.assert_lease()
            fresh_state = self.state()
            submission._guard(fresh_state, target_date, datetime.now(timezone.utc))
            self.post_attempted = True
            return super().post_predictions(target_date, file_name, payload)

    return DurableClient()


def run_hosted(data_root, repository, *, mode='rehearsal', stage=None, runtime_root=HOSTED_RUNTIME,
               target_date=None, submit=False, store_factory=PrivateGitStore, allow_public_data=False):
    from finpred.data.sharing import export_snapshot_bundle, import_snapshot_bundle
    from finpred.pipelines.daily import run_stage

    runtime_root = Path(runtime_root).absolute()
    if runtime_root.is_symlink() or any(p.is_symlink() for p in runtime_root.parents):
        raise HostedBlocked('hosted runtime must not use symlinks')
    if any((p / '.git').exists() for p in (runtime_root, *runtime_root.parents)):
        raise HostedBlocked('hosted runtime must be outside Git')
    runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime_root.chmod(0o700)
    # Only the explicit CLI flag permits a public data repository.
    store = (store_factory(data_root, repository, allow_public_data=True) if allow_public_data
             else store_factory(data_root, repository))
    imported = import_snapshot_bundle(data_root, runtime_root, revision=store.parent)
    restored = restore_runtime(data_root, runtime_root)
    if mode == 'rehearsal':
        return {'status': 'rehearsal_passed', 'source_revision': store.parent, 'import': imported,
                'runtime_restore': restored, 'prediction_posted': False, 'collection_performed': False}
    if mode not in {'collect', 'stage', 'auto'}:
        raise HostedBlocked('unknown hosted execution mode')
    store.acquire()
    client = None
    try:
        if mode == 'collect':
            result = collect_raw(runtime_root)
            export_snapshot_bundle(runtime_root, data_root, raw_roots=(runtime_root / 'market-history',),
                                   required_sources=result.get('required_sources', ()))
            try:
                from finpred.data.shared_features import build_shared_features
                result['features'] = build_shared_features(runtime_root, data_root, allow_research=True)
            except Exception as error:
                result['features'] = {'status': 'blocked', 'error_type': type(error).__name__,
                                      'detail': 'derived feature preparation failed; raw publication continues'}
                result['status'] = 'partial'
            write_json(Path(data_root) / 'catalog/collection-status.json', result)
            store.publish('Synchronize validated private source snapshots')
        else:
            selected = select_stage(datetime.now(timezone.utc)) if mode == 'auto' else stage
            if selected not in {'train', 'predict', 'submit', 'verify'}:
                raise HostedBlocked('hosted stage must be train, predict, submit or verify')
            if submit and selected != 'submit':
                raise HostedBlocked('real submission flag applies only to submit stage')
            if submit and os.environ.get('FINPRED_SUBMISSION_RELEASED') != 'true':
                raise HostedBlocked('real submission has not passed the repository release gate')
            client = durable_submission_client(runtime_root, store)
            client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
            result = run_stage(runtime_root, selected, target_date=target_date, dry_run=not submit, client=client)
        attempted = bool(client is not None and client.post_attempted)
        verified = result.get('status') == 'verified'
        return {**result, 'prediction_post_attempted': attempted, 'receipt_verified': verified,
                'prediction_posted': bool(attempted and verified)}
    finally:
        if client is not None:
            client.close()
        # This also persists blocked/unknown outcomes. If checkpointing fails,
        # leave the lease active and durable in-flight state unresolved.
        pack_runtime(runtime_root, data_root)
        store.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    data_repository = os.environ.get('FINPRED_DATA_REPOSITORY') or os.environ.get('GITHUB_REPOSITORY')
    parser.add_argument('--repository', default=data_repository, required=not data_repository,
                        help='Private data repository; may differ from the public code repository')
    parser.add_argument('--mode', choices=('rehearsal', 'collect', 'stage', 'auto'), default='rehearsal')
    parser.add_argument('--stage', choices=('train', 'predict', 'submit', 'verify'))
    parser.add_argument('--target-date')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--allow-public-data', action='store_true',
                        help='Explicitly allow a verified public data repository')
    args = parser.parse_args()
    try:
        result = run_hosted(args.data_dir, args.repository, mode=args.mode, stage=args.stage,
                            target_date=args.target_date, submit=args.submit,
                            allow_public_data=args.allow_public_data)
    except Exception as error:
        from finpred.data.sharing import SharingError
        from finpred.pipelines.daily import PipelineBlocked
        result = {'status': 'blocked', 'error_type': type(error).__name__}
        if isinstance(error, (HostedBlocked, SharingError, PipelineBlocked)):
            result['reason'] = str(error)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as stream:
            stream.write('Hosted result: `' + result['status'] + '`. Partial source failures are recorded in '
                         '`live-data:catalog/collection-status.json`; job success does not certify all sources or ML readiness.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
