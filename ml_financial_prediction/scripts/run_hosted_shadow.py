"""Persist fixed-recipe research models and prospective forecasts without submission.

This separate hosted entry never promotes models or sends prediction POSTs.
Authentication is used only to read the official session/template for shadow
inference. Rehearsal is a read-only restore with no course network access.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'deployment/hosted'))

from runtime_store import (  # noqa: E402
    HostedBlocked, PrivateGitStore, no_symlink, pack_runtime, restore_runtime, write_json, write_private,
)
from finpred.data.daily_tables import prepare_prediction_table, prepare_training_table  # noqa: E402
from finpred.data.sharing import import_snapshot_bundle  # noqa: E402
from finpred.labels.intraday import aware_datetime  # noqa: E402
from finpred.pipelines.daily import PipelineBlocked, TAIPEI, _at, _private_file_bytes  # noqa: E402
from finpred.pipelines.shadow import (  # noqa: E402
    _store_directory, build_shadow_session_evidence, run_shadow_forecast,
)
from finpred.submission.course import CourseSubmissionClient, _session  # noqa: E402
from finpred.training.fit import fit_model, save_model_bundle  # noqa: E402

HOSTED_RUNTIME = Path('/tmp/finpred-hosted-runtime')
RECIPE = {'family': 'linear', 'objective': 'weighted_classification', 'seed': 42, 'epochs': 8}


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _now(clock):
    return aware_datetime(clock(), name='hosted shadow real clock')


def _fit_child(queue, table, destination, cutoff):
    try:
        bundle = fit_model(table, fit_cutoff=cutoff, allow_research=True, **RECIPE)
        if bundle.metadata.get('production_eligible') is not False:
            raise PipelineBlocked('shadow training must remain research only')
        save_model_bundle(bundle, destination)
        queue.put({'status': 'fitted'})
    except Exception as error:
        queue.put({'status': 'failed', 'error_type': type(error).__name__})


def bounded_research_fit(table, destination, cutoff, timeout_seconds):
    """One preregistered fit, killed at the training deadline; no tuning loop."""
    if timeout_seconds <= 0:
        return {'status': 'timeout'}
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    worker = context.Process(target=_fit_child, args=(queue, table, destination, cutoff))
    worker.start()
    try:
        try:
            return queue.get(timeout=timeout_seconds)
        except Exception:
            return {'status': 'timeout'}
    finally:
        worker.join(timeout=0.1)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
            if worker.is_alive():
                worker.kill()
                worker.join()
        queue.close()


def train_research(root, day, *, clock, fit_worker=bounded_research_fit):
    started = _now(clock)
    if not _at(day, 7, 20) <= started < _at(day, 7, 50):
        raise PipelineBlocked('research training requires target-day 07:20-07:50 Taipei window')
    prepared = prepare_training_table(root, day, allow_research=True)
    if prepared.get('status') != 'prepared' or prepared.get('readiness') != 'research_assumption':
        raise PipelineBlocked('research training source preparation blocked')
    table_bytes = _private_file_bytes(Path(prepared['table_path']))
    if _digest(table_bytes) != prepared['table_sha256']:
        raise PipelineBlocked('research training table hash changed')
    table = json.loads(table_bytes)
    identity = uuid.uuid4().hex
    destination = root / 'shadow/models' / day / identity
    for directory in (root / 'shadow', root / 'shadow/models', destination.parent):
        _store_directory(directory)
    cutoff = _at(day, 7, 20).isoformat()
    outcome = fit_worker(table, destination, cutoff, (_at(day, 7, 50) - _now(clock)).total_seconds())
    completed = _now(clock)
    if outcome.get('status') != 'fitted' or completed >= _at(day, 7, 50):
        raise PipelineBlocked('fixed-recipe research fit failed or missed training deadline')
    manifest_bytes = _private_file_bytes(destination / 'manifest.json')
    manifest = json.loads(manifest_bytes)
    if (manifest.get('readiness') != 'research_assumption'
            or manifest.get('production_eligible') is not False
            or any(manifest.get(key) != value for key, value in RECIPE.items())
            or manifest.get('fit_cutoff') != cutoff):
        raise PipelineBlocked('research model manifest differs from frozen recipe')
    pointer = {
        'schema_version': 'hosted-shadow-model-v1', 'model_path': str(destination),
        'manifest_sha256': _digest(manifest_bytes), 'recipe': dict(RECIPE), 'target_date': day,
        'training_table_sha256': manifest['training_table_sha256'],
        'training_table_file_sha256': prepared['table_sha256'],
        'source_revision_policy': 'observed snapshot provenance preserved in training table',
        'completed_at': completed.isoformat(), 'production_eligible': False,
        'historical_availability_verified': False, 'submitted': False,
    }
    write_json(destination / 'training-evidence.json', pointer)
    if _now(clock) >= _at(day, 7, 50):
        raise PipelineBlocked('research training evidence missed persistence deadline')
    latest = root / 'shadow/model-latest.json'
    previous = _private_file_bytes(latest) if latest.exists() else None
    write_json(latest, pointer)
    if _now(clock) >= _at(day, 7, 50):
        if previous is None:
            latest.unlink(missing_ok=True)
        else:
            write_private(latest, previous)
        raise PipelineBlocked('research model pointer missed persistence deadline; previous model retained')
    return {'status': 'research_model_fitted', **pointer}


def predict_shadow(root, day, *, clock, client_factory=CourseSubmissionClient):
    now = _now(clock)
    if not _at(day, 8, 10) <= now < _at(day, 9):
        raise PipelineBlocked('hosted shadow requires target-day 08:10-09:00 Taipei window')
    pointer = json.loads(_private_file_bytes(root / 'shadow/model-latest.json'))
    model = Path(pointer['model_path']).absolute()
    no_symlink(model)
    model = model.resolve(strict=True)
    if (not model.is_relative_to((root / 'shadow/models').resolve())
            or pointer.get('schema_version') != 'hosted-shadow-model-v1'
            or pointer.get('production_eligible') is not False
            or pointer.get('recipe') != RECIPE
            or _digest(_private_file_bytes(model / 'manifest.json')) != pointer.get('manifest_sha256')):
        raise PipelineBlocked('internally created fixed-recipe shadow model required')
    if aware_datetime(pointer['completed_at'], name='research model time') > now:
        raise PipelineBlocked('future research model cannot be used')
    prepared = prepare_prediction_table(root, day)
    if prepared.get('status') != 'prepared':
        raise PipelineBlocked('observed shadow feature preparation blocked')
    # This client has normal verified TLS, redirect/size guards and no prediction
    # POST calls here. Never persist the complete state, cookies or user account.
    client = client_factory()
    try:
        client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
        state = client.state()
        state_time = _now(clock)
        _session(state, day)  # A missing official date is not fabricated from weekdays.
        template = client.daily_template(day)
        template_time = _now(clock)
    finally:
        client.close()
    evidence = build_shadow_session_evidence(
        state, day, state_fetched_at=state_time, template_payload=template,
        template_fetched_at=template_time, tls_verified=True)
    inputs = root / 'shadow/inputs' / day / uuid.uuid4().hex
    for directory in (root / 'shadow/inputs', inputs.parent):
        _store_directory(directory)
    inputs.mkdir(mode=0o700)
    write_private(inputs / 'template.csv', template)
    write_json(inputs / 'session-evidence.json', evidence)
    return run_shadow_forecast(
        root, trusted_model_dir=model, prediction_table=prepared['table_path'],
        template_path=inputs / 'template.csv', session_evidence_path=inputs / 'session-evidence.json',
        target_date=day, clock=clock)


def run_hosted_shadow(data_root, repository, *, mode='rehearsal', runtime_root=HOSTED_RUNTIME,
                      target_date=None, allow_public_data=False, clock=None,
                      store_factory=PrivateGitStore):
    clock = clock or (lambda: datetime.now(timezone.utc))
    root = Path(runtime_root).absolute()
    no_symlink(root)
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise HostedBlocked('hosted shadow runtime must remain outside Git')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise HostedBlocked('hosted shadow runtime must be locally owned with mode 0700')
    store = (store_factory(data_root, repository, allow_public_data=True) if allow_public_data
             else store_factory(data_root, repository))
    imported = import_snapshot_bundle(data_root, root, revision=store.parent)
    restored = restore_runtime(data_root, root)
    if mode == 'rehearsal':
        return {'status': 'shadow_rehearsal_passed', 'source_revision': store.parent,
                'import_status': imported['status'], 'runtime_restore': restored,
                'production_eligible': False, 'submitted': False}
    if mode not in {'train', 'predict'}:
        raise HostedBlocked('unknown hosted shadow mode')
    day = target_date or _now(clock).astimezone(TAIPEI).date().isoformat()
    store.acquire()
    try:
        result = (train_research(root, day, clock=clock) if mode == 'train'
                  else predict_shadow(root, day, clock=clock))
        if result['status'] == 'prospective_shadow':
            directory = Path(result['directory'])
            local_manifest = json.loads(_private_file_bytes(directory / 'manifest.json'))
            deadline = aware_datetime(local_manifest['deadline'], name='shadow deadline')
            pack_runtime(root, data_root)
            published_commit = store.publish('Persist isolated prospective research forecast')
            published_at = _now(clock)
            timely = published_at < deadline
            record = {'schema_version': 'hosted-shadow-publication-v1',
                      'prediction_commit': published_commit, 'published_at': published_at.isoformat(),
                      'deadline': deadline.isoformat(), 'csv_sha256': result['csv_sha256'],
                      'hosted_persistence_before_deadline': timely,
                      'production_eligible': False, 'submitted': False}
            write_json(directory / 'hosted-publication.json', record)
            result.update(record)
            if not timely:
                result['status'] = 'shadow_hosted_persistence_missed_deadline'
        return {**result, 'source_revision': imported['git_revision']}
    finally:
        pack_runtime(root, data_root)
        store.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('rehearsal', 'train', 'predict'), default='rehearsal')
    parser.add_argument('--target-date')
    parser.add_argument('--allow-public-data', action='store_true')
    args = parser.parse_args()
    try:
        result = run_hosted_shadow(args.data_dir, args.repository, mode=args.mode,
                                   target_date=args.target_date, allow_public_data=args.allow_public_data)
    except Exception as error:
        # Never publish arbitrary adapter exceptions, state or credentials.
        result = {'status': 'blocked', 'error_type': type(error).__name__,
                  'production_eligible': False, 'submitted': False}
        print(json.dumps(result))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] != 'shadow_hosted_persistence_missed_deadline' else 1


if __name__ == '__main__':
    raise SystemExit(main())
