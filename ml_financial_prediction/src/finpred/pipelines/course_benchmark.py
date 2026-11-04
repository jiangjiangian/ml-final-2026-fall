"""Prospective course deployment with explicitly retrospective validation.

This policy does not certify historical publication or adjustment vintages.
Its models remain research-assumption bundles; a separate, checked descriptor
authorizes future competition inference using genuinely observed current inputs.
The strict PIT pipeline and its approved model are never modified.
"""

import csv
import fcntl
import hashlib
from importlib.metadata import version
import io
import json
import math
import os
from pathlib import Path
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sklearn.dummy import DummyClassifier

from finpred.data.daily_tables import (
    _sources, _save, prepare_prediction_table,
)
from finpred.data.training_table import build_research_table
from finpred.features.stock import STOCK_FEATURES
from finpred.inference.predict import predict_rows
from finpred.labels.intraday import aware_datetime
from finpred.pipelines.daily import (
    PipelineBlocked, _at, _hash, _json, _prediction_table, _private_file_bytes,
    _private_root, _write, bounded_training, window,
)
from finpred.submission.course import (
    CourseSubmissionClient, _session, execute_submission, validate_prediction_csv,
)
from finpred.training.fit import ModelBundle, feature_matrix, load_model_bundle, save_model_bundle

POLICY = 'course-benchmark-v1'
RECIPE = {'family': 'linear', 'objective': 'weighted_classification', 'seed': 42, 'epochs': 8}
BASELINE_RECIPE = {'family': 'dummy_majority', 'objective': 'classification', 'seed': 42, 'epochs': 0}
MIN_TRAIN_DATES = 252
VALIDATION_DATES = 60
CODE_FILES = (
    'pipelines/course_benchmark.py', 'pipelines/daily.py', 'data/daily_tables.py',
    'data/training_table.py', 'features/stock.py', 'training/fit.py',
    'inference/predict.py', 'models/estimators.py', 'evaluation/official_score.py',
    'labels/intraday.py',
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def _code_hashes():
    package = Path(__file__).resolve().parents[1]
    return {name: _hash(package / name) for name in CODE_FILES}


def _directory(path, root):
    path = _safe_path(path, root)
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for part in reversed(missing):
        part.mkdir(mode=0o700)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise PipelineBlocked('course policy directories require private ownership')
    return path


def _read_json(path, root):
    path = _safe_path(path, root)
    return json.loads(_private_file_bytes(path))


def _safe_path(value, root):
    path = Path(value).absolute()
    if ('..' in path.parts or not path.is_relative_to(root)
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise PipelineBlocked('course policy artifacts require canonical private runtime paths')
    return path


def _pointer(root):
    return root / 'candidates' / POLICY / 'approved.json'


def _source_evidence(selected):
    return [{'source': item['record']['source'],
             'source_url': item['record']['source_url'],
             'manifest_path': item['manifest_path'],
             'manifest_sha256': item['manifest_sha256'],
             'payload_path': item['record']['payload_path'],
             'payload_sha256': item['record']['sha256'],
             'fetched_at': item['record']['fetched_at']}
            for item in selected]


def _validate_sources(sources, root, actual_fit_cutoff):
    from finpred.data.daily_tables import SOURCE_URLS

    if not isinstance(sources, list) or {x.get('source') for x in sources} != set(SOURCE_URLS) or len(sources) != 2:
        raise PipelineBlocked('course training requires exactly both official source snapshots')
    for item in sources:
        record = _read_json(item['manifest_path'], root)
        payload_path = _safe_path(item['payload_path'], root)
        payload = _private_file_bytes(payload_path)
        if (record.get('source') != item['source']
                or record.get('source_url') != SOURCE_URLS[item['source']]
                or item.get('source_url') != record.get('source_url')
                or record.get('schema_version') != 'snapshot-v1'
                or record.get('payload_path') != str(payload_path)
                or record.get('fetched_at') != item.get('fetched_at')
                or not isinstance(record.get('metadata'), dict)
                or record['metadata'].get('tls_verified') is not True
                or _hash(item['manifest_path']) != item.get('manifest_sha256')
                or hashlib.sha256(payload).hexdigest() != item.get('payload_sha256')
                or item['payload_sha256'] != record.get('sha256')
                or len(payload) != record.get('size_bytes')
                or aware_datetime(item['fetched_at'], name='training source fetch') > actual_fit_cutoff):
            raise PipelineBlocked('course training source integrity or actual acquisition cutoff failed')


def load_course_approved(root, *, now=None):
    """Check the complete course-policy chain without upgrading historical PIT."""
    root = _private_root(root)
    record = _read_json(_pointer(root), root)
    model = _safe_path(record['model_path'], root)
    store = root / 'candidates' / POLICY / 'runs'
    if not model.is_relative_to(store) or model.name not in {'model', 'baseline-model'}:
        raise PipelineBlocked('course approved model must belong to its isolated run store')
    if (record.get('schema_version') != 'course-approved-v1'
            or record.get('deployment_policy') != POLICY
            or record.get('deployment_eligible') is not True
            or record.get('historical_vintage_verified') is not False
            or record.get('validation_scope') != 'retrospective_latest_vintage_time_split'
            or record.get('recipe') != RECIPE
            or record.get('code_sha256') != _code_hashes()
            or _hash(model / 'manifest.json') != record.get('model_manifest_sha256')):
        raise PipelineBlocked('course model policy, manifest or trusted code identity mismatch')
    bundle = load_model_bundle(model, trusted=True)
    metadata = bundle.metadata
    registration = _read_json(model.parent / 'registration.json', root)
    report = _read_json(model.parent / 'candidate_report.json', root)
    candidate, baseline = report.get('candidate_score'), report.get('incumbent_score')
    if (isinstance(candidate, bool) or isinstance(baseline, bool)
            or not isinstance(candidate, (float, int)) or not isinstance(baseline, (float, int))
            or not math.isfinite(candidate) or not math.isfinite(baseline)):
        raise PipelineBlocked('course validation requires finite numeric scores')
    winner = 'linear' if candidate > baseline else 'train_majority'
    model_recipe = RECIPE if winner == 'linear' else BASELINE_RECIPE
    if (record.get('selected_model') != winner
            or model.name != ('model' if winner == 'linear' else 'baseline-model')
            or record.get('selected_model_recipe') != model_recipe
            or report.get('candidate_improved') is not (candidate > baseline)):
        raise PipelineBlocked('course selection must follow the preregistered comparison, ties select baseline')
    if (record.get('registration_sha256') != _hash(model.parent / 'registration.json')
            or record.get('report_sha256') != _hash(model.parent / 'candidate_report.json')
            or registration.get('deployment_policy') != POLICY
            or registration.get('recipe') != RECIPE
            or registration.get('code_sha256') != record['code_sha256']
            or registration.get('source_snapshots') != record.get('source_snapshots')
            or registration.get('training_table_sha256') != metadata.get('training_table_sha256')
            or metadata.get('readiness') != 'research_assumption'
            or metadata.get('production_eligible') is not False
            or metadata.get('feature_columns') != list(STOCK_FEATURES)
            or metadata.get('feature_version') != 'course-research-lags-v1'
            or any(metadata.get(key) != value for key, value in model_recipe.items())
            or report.get('readiness') != 'research_assumption'
            or report.get('eligible_for_promotion') is not False
            or report.get('promotion_reason') != 'non_verified_model'
            or report.get('evaluation_scope') != 'train_majority_baseline_on_same_validation_keys'
            or report.get('model_path') != str(model.parent / 'model')
            or report.get('selected_configuration') != {k: RECIPE[k] for k in ('family', 'objective', 'seed')}
            or report.get('selected_epochs') != RECIPE['epochs']
            or report.get('validation_dates') != VALIDATION_DATES
            or not isinstance(report.get('training_dates'), int)
            or report['training_dates'] < MIN_TRAIN_DATES):
        raise PipelineBlocked('course model lacks its exact fixed retrospective validation evidence')
    packages = metadata.get('package_versions')
    if not isinstance(packages, dict) or not packages or any(version(k) != v for k, v in packages.items()):
        raise PipelineBlocked('course model requires its recorded package versions')
    started = aware_datetime(registration.get('actual_fit_cutoff'), name='actual fit cutoff')
    completed = aware_datetime(record.get('fit_completed_at'), name='fit completed')
    approved = aware_datetime(record.get('approved_at'), name='course approved time')
    if (metadata.get('fit_cutoff') != started.isoformat() or not started <= completed <= approved
            or (now is not None and approved > aware_datetime(now, name='clock'))):
        raise PipelineBlocked('course model execution timestamps are inconsistent')
    _validate_sources(record['source_snapshots'], root, started)
    saved_table = _read_json(registration['training_table_path'], root)
    if (_digest(saved_table) != metadata['training_table_sha256']
            or saved_table.get('readiness') != 'research_assumption'
            or saved_table.get('feature_columns') != list(STOCK_FEATURES)
            or saved_table.get('availability_policy_version') != POLICY
            or saved_table.get('course_deployment', {}).get('source_snapshots') != record['source_snapshots']
            or any(row['target_date'] >= started.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()
                   for row in saved_table.get('rows', []))):
        raise PipelineBlocked('course saved training table differs from the approved model')
    return record, bundle


def _train(root, day, now, clock, initialize, train_worker):
    if not initialize and not _at(day, 7, 20) <= now < _at(day, 7, 50):
        raise PipelineBlocked('course daily training runs only 07:20–07:50 Taipei')
    # Bootstrap is an explicit, bounded real-time operation; it never pretends
    # an afternoon fit existed for that morning's prediction cutoff.
    deadline = now + timedelta(seconds=300) if initialize else _at(day, 7, 50)
    stocks, provenance, selected = _sources(root, now)
    history = {sid: [row for row in values if row['date'] < day] for sid, values in stocks.items()}
    table = build_research_table(history, provenance=provenance)
    table['availability_policy_version'] = POLICY
    table['course_deployment'] = {
        'historical_vintage_verified': False,
        'validation_scope': 'retrospective_latest_vintage_time_split',
        'actual_training_source_latest_acquired_at': max(
            aware_datetime(item['record']['fetched_at'], name='fetch') for item in selected).isoformat(),
        'source_snapshots': _source_evidence(selected),
    }
    # The historical 23:59 label times remain declared assumptions. Current
    # deployability is separately grounded in the immutable observed archives.
    if any(row['target_date'] >= day or aware_datetime(row['label_available_at'], name='label time') > now
           for row in table['rows']):
        raise PipelineBlocked('course training contains current, future or unavailable labels')
    sources = _source_evidence(selected)
    _validate_sources(sources, root, now)
    code = _code_hashes()
    table_path, _ = _save(root, day, 'course-benchmark-training', table)
    stable_table = {key: value for key, value in table.items() if key != 'course_deployment'}
    identity = _digest({'policy': POLICY, 'day': day, 'recipe': RECIPE,
                        'table_content_sha256': _digest(stable_table), 'code': code})
    destination = root / 'candidates' / POLICY / 'runs' / identity
    pointer = _pointer(root)
    previous_pointer = _private_file_bytes(pointer) if pointer.exists() else None
    if destination.exists():
        if pointer.exists():
            previous, _ = load_course_approved(root, now=now)
            if Path(previous['model_path']).parent == destination:
                return {'status': 'course_model_retained', 'reason': 'same_inputs_already_trained',
                        'course_model_available': True, 'historical_vintage_verified': False}
        raise PipelineBlocked('course fit run already exists; never overwrite or blindly repeat a partial fit')
    _directory(destination, root)
    registration = {
        'schema_version': 'course-training-registration-v1', 'deployment_policy': POLICY,
        'actual_fit_cutoff': now.isoformat(), 'recipe': RECIPE, 'code_sha256': code,
        'source_snapshots': sources, 'training_table_sha256': _digest(table),
        'training_table_path': table_path, 'historical_vintage_verified': False,
        'validation_scope': 'retrospective_latest_vintage_time_split',
        'min_train_dates': MIN_TRAIN_DATES, 'validation_dates': VALIDATION_DATES,
        'selection_rule': 'larger_official_score_on_same_validation_keys; ties select train_majority',
        'fit_budget': 'two fixed linear fits plus at most one trivial majority fit; no search',
        'initialization': bool(initialize), 'holdout_reused': False,
    }
    _json(destination / 'registration.json', registration)
    kwargs = {**RECIPE, 'fit_cutoff': now.isoformat(), 'min_train_dates': MIN_TRAIN_DATES,
              'validation_dates': VALIDATION_DATES, 'allow_research': True}
    result = train_worker(table, destination, kwargs,
                          max(0, (deadline - aware_datetime(clock(), name='clock')).total_seconds()))
    completed = aware_datetime(clock(), name='clock')
    if not result.get('ok') or completed >= deadline:
        return {'status': 'course_model_retained', 'reason': 'candidate_failed_or_timed_out',
                'course_model_available': pointer.exists(), 'historical_vintage_verified': False}
    report = _read_json(destination / 'candidate_report.json', root)
    if report != result.get('report') or _code_hashes() != code:
        raise PipelineBlocked('course training evidence or code changed during fit')
    candidate, baseline = report.get('candidate_score'), report.get('incumbent_score')
    if (isinstance(candidate, bool) or isinstance(baseline, bool)
            or not isinstance(candidate, (float, int)) or not isinstance(baseline, (float, int))
            or not math.isfinite(candidate) or not math.isfinite(baseline)
            or report.get('candidate_improved') is not (candidate > baseline)):
        raise PipelineBlocked('course comparison requires finite scores consistent with its decision')
    model = destination / 'model'
    if Path(report['model_path']).absolute() != model:
        raise PipelineBlocked('course candidate escaped its isolated model directory')
    selected_model = 'linear'
    selected_recipe = RECIPE
    if candidate <= baseline:
        # Refit the predeclared conservative baseline on exactly the same full
        # past training prefix. Never overwrite the immutable linear artifact.
        linear = load_model_bundle(model, trusted=True)
        values = linear.preprocessor.transform(feature_matrix(table['rows'], table['feature_columns']))
        estimator = DummyClassifier(strategy='most_frequent')
        estimator.fit(values, [row['y'] for row in table['rows']])
        metadata = {**linear.metadata, **BASELINE_RECIPE,
                    'baseline_definition': 'unweighted majority of all completed past training labels; tie predicts 0'}
        model = destination / 'baseline-model'
        save_model_bundle(ModelBundle(linear.preprocessor, estimator, metadata), model)
        selected_model, selected_recipe = 'train_majority', BASELINE_RECIPE
        completed = aware_datetime(clock(), name='clock')
    approved_at = aware_datetime(clock(), name='clock')
    descriptor = {
        'schema_version': 'course-approved-v1', 'deployment_policy': POLICY,
        'deployment_eligible': True, 'historical_vintage_verified': False,
        'validation_scope': 'retrospective_latest_vintage_time_split', 'recipe': RECIPE,
        'selected_model': selected_model, 'selected_model_recipe': selected_recipe,
        'model_path': str(model), 'model_manifest_sha256': _hash(model / 'manifest.json'),
        'registration_sha256': _hash(destination / 'registration.json'),
        'report_sha256': _hash(destination / 'candidate_report.json'),
        'source_snapshots': sources, 'code_sha256': code,
        'fit_completed_at': completed.isoformat(), 'approved_at': approved_at.isoformat(),
    }
    _json(pointer, descriptor)
    try:
        load_course_approved(root, now=clock())
        if aware_datetime(clock(), name='clock') >= deadline:
            raise PipelineBlocked('course model approval crossed its real execution deadline')
    except BaseException:
        if previous_pointer is None:
            pointer.unlink(missing_ok=True)
        else:
            _write(pointer, previous_pointer)
        raise
    return {'status': 'course_model_approved', 'deployment_policy': POLICY,
            'model_manifest_sha256': descriptor['model_manifest_sha256'],
            'approved_at': descriptor['approved_at'], 'fit_cutoff': now.isoformat(),
            'historical_vintage_verified': False, 'model_production_eligible': False,
            'selected_model': selected_model,
            'candidate_score': report['candidate_score'], 'baseline_score': report['incumbent_score']}


def _predict(root, day, now, client, clock):
    prepared = prepare_prediction_table(root, day)
    if not prepared.get('table_path'):
        raise PipelineBlocked('course inference lacks genuinely observed cutoff-eligible inputs')
    table = _read_json(prepared['table_path'], root)
    state = client.state()
    cutoff = _prediction_table(table, day, now, official_state=state)
    approved, bundle = load_course_approved(root, now=now)
    if aware_datetime(approved['approved_at'], name='approval') > cutoff:
        raise PipelineBlocked('course model was approved after the requested feature freeze')
    predictions = predict_rows(bundle, table['rows'], feature_columns=table['feature_columns'],
                               feature_version=table['feature_version'], require_production=False)
    template = client.daily_template(day)
    order = list(csv.reader(io.StringIO(template.decode('utf-8-sig'))))
    values = {row['stock_id']: row['prediction'] for row in predictions}
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['id', day])
    for row in order[1:]:
        if len(row) != 2 or row[0] not in values:
            raise PipelineBlocked('course prediction universe differs from official template')
        writer.writerow([row[0], values[row[0]]])
    payload = output.getvalue().encode()
    validate_prediction_csv(payload, template, day)
    generated = aware_datetime(clock(), name='clock')
    window(generated, day)
    metadata = {
        'deployment_policy': POLICY, 'target_date': day, 'generated_at': generated.isoformat(),
        'model_manifest_sha256': approved['model_manifest_sha256'],
        'approval_descriptor_sha256': _hash(_pointer(root)),
        'feature_table_sha256': _hash(prepared['table_path']),
        'feature_table_path': prepared['table_path'],
        'csv_sha256': hashlib.sha256(payload).hexdigest(),
        'historical_vintage_verified': False,
        'validation_scope': approved['validation_scope'],
        'readiness': {'model_validated': True, 'feature_availability_verified': True,
                      'feature_cutoff': cutoff.isoformat(), 'model_validation_policy': POLICY,
                      'historical_vintage_verified': False},
    }
    destination = _directory(root / 'predictions' / POLICY / day / _digest(metadata), root)
    _write(destination / 'prediction.csv', payload)
    _json(destination / 'manifest.json', metadata)
    latest = {'csv_path': str(destination / 'prediction.csv'), **metadata}
    pointer = root / 'predictions' / POLICY / day / 'latest.json'
    previous = _private_file_bytes(pointer) if pointer.exists() else None
    _json(pointer, latest)
    try:
        window(clock(), day)
    except BaseException:
        if previous is None:
            pointer.unlink(missing_ok=True)
        else:
            _write(pointer, previous)
        raise
    return {'status': 'predicted', 'prediction_count': 50, **latest}


def _submit(root, day, now, client, clock, dry_run, verify_only):
    latest = _read_json(root / 'predictions' / POLICY / day / 'latest.json', root)
    approved, _ = load_course_approved(root, now=now)
    if (latest.get('deployment_policy') != POLICY
            or latest.get('model_manifest_sha256') != approved['model_manifest_sha256']
            or latest.get('approval_descriptor_sha256') != _hash(_pointer(root))):
        raise PipelineBlocked('course model policy changed; regenerate the daily prediction')
    payload = _private_file_bytes(_safe_path(latest['csv_path'], root))
    if hashlib.sha256(payload).hexdigest() != latest.get('csv_sha256'):
        raise PipelineBlocked('course prediction CSV hash changed')
    table = _read_json(latest['feature_table_path'], root)
    if _hash(latest['feature_table_path']) != latest.get('feature_table_sha256'):
        raise PipelineBlocked('course input table hash changed')
    # Revalidate sources, current session coverage and reconstruction before POST.
    cutoff = _prediction_table(table, day, now, official_state=client.state())
    if (aware_datetime(approved['approved_at'], name='approval') > cutoff
            or latest.get('historical_vintage_verified') is not False
            or latest.get('readiness', {}).get('model_validation_policy') != POLICY):
        raise PipelineBlocked('course prediction provenance or approval timing failed')
    if verify_only:
        template = client.daily_template(day)
        expected = validate_prediction_csv(payload, template, day)
        receipt = client.current_receipt(client.state(), day, expected, template)
        if receipt is None:
            raise PipelineBlocked('course prediction has no matching official current receipt')
        _directory(root / 'verified' / POLICY, root)
        _json(root / 'verified' / POLICY / (day + '.json'), receipt)
        return receipt
    return execute_submission(client, payload, day, root, dry_run=dry_run,
                              generated_at=latest['generated_at'], readiness=latest['readiness'], clock=clock)


def run_course_benchmark(runtime_dir, stage, *, target_date=None, dry_run=True,
                         initialize=False, client=None, clock=None, train_worker=bounded_training):
    """Run one real-time stage under the named course policy, never strict PIT."""
    from finpred.pipelines.daily import TAIPEI

    if stage not in {'train', 'predict', 'submit', 'verify'} or (initialize and stage != 'train'):
        raise PipelineBlocked('unknown course stage or initialization outside training')
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = aware_datetime(clock(), name='clock')
    day = target_date or now.astimezone(TAIPEI).date().isoformat()
    if day != now.astimezone(TAIPEI).date().isoformat():
        raise PipelineBlocked('course pipeline target must be the true current Taipei date')
    if not initialize:
        window(now, day)
    root = _private_root(runtime_dir)
    _directory(root / 'candidates' / POLICY, root)
    _directory(root / 'runs' / POLICY / day, root)
    with (root / 'pipeline.lock').open('a+') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        owned = client is None
        if owned and not initialize:
            client = CourseSubmissionClient()
        result = {'run_id': uuid.uuid4().hex, 'deployment_policy': POLICY, 'stage': stage,
                  'target_date': day, 'started_at': now.isoformat(), 'dry_run': dry_run,
                  'historical_vintage_verified': False, 'initialization': bool(initialize)}
        try:
            if owned and not initialize:
                client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
            now = aware_datetime(clock(), name='clock')
            if not initialize:
                window(now, day)
                session = _session(client.state(), day)
                if session.get('enabled') not in (True, 1):
                    raise PipelineBlocked('official course session is disabled')
            if stage == 'train':
                value = _train(root, day, now, clock, initialize, train_worker)
            elif stage == 'predict':
                value = _predict(root, day, now, client, clock)
            else:
                value = _submit(root, day, now, client, clock, dry_run, stage == 'verify')
            if not initialize:
                window(clock(), day)
            result.update(value)
        except Exception as error:
            result.update(status='blocked', error_type=type(error).__name__)
            if isinstance(error, PipelineBlocked):
                result['reason'] = str(error)
            raise
        finally:
            _json(root / 'runs' / POLICY / day / (stage + '-' + result['run_id'] + '.json'), result)
            _json(root / 'runs' / POLICY / day / (stage + '.json'), result)
            if owned and client is not None:
                client.close()
        return result
