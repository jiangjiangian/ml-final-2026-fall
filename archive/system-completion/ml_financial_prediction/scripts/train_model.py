"""Fit one research model with the real clock; never select, approve or submit."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.labels.intraday import aware_datetime  # noqa: E402
from finpred.models.estimators import OBJECTIVES  # noqa: E402
from finpred.training.fit import fit_model, save_model_bundle  # noqa: E402

MAX_TABLE_BYTES = 128 * 1024 * 1024


def _safe_path(value):
    path = Path(value).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('training paths must not use symlinks')
    return path


def _table_bytes(path):
    path = _safe_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        details = os.fstat(stream.fileno())
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid()
                or details.st_mode & 0o077 or details.st_size > MAX_TABLE_BYTES):
            raise ValueError('training table must be a bounded locally owned private regular file')
        payload = stream.read(MAX_TABLE_BYTES + 1)
    if len(payload) > MAX_TABLE_BYTES:
        raise ValueError('training table exceeds the input limit')
    return payload


def _json_file(path, record):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write((json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _output_directory(value):
    destination = _safe_path(value)
    if any((parent / '.git').exists() for parent in (destination, *destination.parents)):
        raise ValueError('research models must remain outside Git')
    missing, parent = [], destination.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    # Reserve the unique output before fitting; an existing directory is never
    # reused, including an empty directory or an earlier failed attempt.
    destination.mkdir(mode=0o700)
    return destination


def train_model(table_path, out_dir, *, family='linear', objective='weighted_classification',
                seed=42, allow_research=False, clock=None):
    """Tests can inject a clock; the command line always uses the real UTC clock.

    The single fit uses all eligible rows from the supplied table. This does not
    perform validation, compare models or consume any held-out evaluation set.
    """
    if allow_research is not True:
        raise ValueError('single-fit research training requires explicit opt-in')
    if family not in {'linear', 'hist_gbdt'} or objective not in OBJECTIVES:
        raise ValueError('unsupported single-fit recipe')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError('seed must be an integer between 0 and 2**32-1')
    payload = _table_bytes(table_path)
    table = json.loads(payload)
    if not isinstance(table, dict) or table.get('readiness') not in {'research_assumption', 'synthetic'}:
        raise ValueError('this entry accepts only explicit research or synthetic tables')
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = aware_datetime(clock(), name='actual research fit cutoff')
    destination = _output_directory(out_dir)
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix='.finpred-single-fit-', dir=destination.parent))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            bundle = fit_model(table, fit_cutoff=started, family=family, objective=objective,
                               seed=seed, allow_research=True)
        if bundle.metadata.get('production_eligible') is not False:
            raise ValueError('single-fit research bundle must not be production eligible')
        metadata = save_model_bundle(bundle, staging)
        for name in ('model.joblib', 'manifest.json'):
            with (staging / name).open('rb') as stream:
                os.fsync(stream.fileno())
        finished = aware_datetime(clock(), name='research fit completion')
        if finished < started:
            raise ValueError('research completion precedes its actual start')
        record = {
            'schema_version': 'research-training-run-v1', 'status': 'research_model_fitted',
            'scope': 'single_fit_without_validation_selection_or_submission',
            'started_at': started.isoformat(), 'fit_finished_at': finished.isoformat(),
            'fit_cutoff': metadata['fit_cutoff'], 'family': family, 'objective': objective, 'seed': seed,
            'readiness': metadata['readiness'], 'production_eligible': False, 'submitted': False,
            'validation_evaluated': False, 'holdout_evaluated': False, 'selection_performed': False,
            'train_rows': metadata['train_rows'], 'train_end_date': metadata['train_end_date'],
            'input_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'training_table_sha256': metadata['training_table_sha256'],
            'model_manifest_sha256': hashlib.sha256((staging / 'manifest.json').read_bytes()).hexdigest(),
            'model_sha256': metadata['model_sha256'],
            'training_entrypoint_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'warning_categories': sorted({type(w.message).__name__ for w in caught}),
        }
        _json_file(staging / 'training-run.json', record)
        _sync_directory(staging)
        # Replace only our own empty reservation. A nonempty destination makes
        # rename fail, preserving anything created there by another writer.
        os.rename(staging, destination)
        staging = None
        _sync_directory(destination.parent)
        return {**{key: record[key] for key in (
            'status', 'family', 'objective', 'seed', 'readiness', 'fit_cutoff', 'train_rows',
            'input_payload_sha256', 'training_table_sha256', 'production_eligible', 'submitted',
            'validation_evaluated', 'holdout_evaluated')},
            'model_dir': str(destination), 'training_run': str(destination / 'training-run.json')}
    except BaseException as error:
        # Incomplete serialization stays in a private staging area until this
        # cleanup; no manifest/joblib is published at the requested model path.
        if staging is not None:
            shutil.rmtree(staging)
            try:
                _json_file(destination / 'failure.json', {
                    'schema_version': 'research-training-failure-v1', 'status': 'failed',
                    'error_type': type(error).__name__, 'production_eligible': False, 'submitted': False})
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True, help='New model directory outside Git; must not exist')
    parser.add_argument('--family', choices=('linear', 'hist_gbdt'), default='linear')
    parser.add_argument('--objective', choices=OBJECTIVES, default='weighted_classification')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--allow-research', action='store_true')
    args = parser.parse_args()
    try:
        result = train_model(args.table, args.out_dir, family=args.family, objective=args.objective,
                             seed=args.seed, allow_research=args.allow_research)
    except Exception as error:
        # Raw JSON, exception messages, source paths and credential values are
        # intentionally excluded from this public-facing failure response.
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__,
                          'detail': 'research training failed; input details omitted'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
