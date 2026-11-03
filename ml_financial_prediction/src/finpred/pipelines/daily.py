"""Small staged daily runner with a private persistent runtime and fail-closed gates.

Dry run suppresses prediction submission, not authenticated reads or computation.
Tables must already have source-specific point-in-time features: orchestration
never upgrades research assumptions into production evidence.
"""

import csv
import fcntl
import hashlib
import io
import json
import multiprocessing
import os
import stat
import tempfile
import uuid
from datetime import date, datetime, time, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

from finpred.inference.predict import predict_rows
from finpred.data.daily_tables import prepare_prediction_table, prepare_training_table
from finpred.ingestion.course import download_course_sources
from finpred.ingestion.external import SOURCE_SPECS, download_external
from finpred.ingestion.market_history import (
    HISTORY_SERIES, download_market_history, download_twse_sector_snapshot,
)
from finpred.labels.intraday import aware_datetime
from finpred.submission.course import (
    CourseSubmissionClient, _session, execute_submission, validate_prediction_csv,
)
from finpred.training.fit import load_model_bundle, train_candidate

TAIPEI = ZoneInfo('Asia/Taipei')
STAGES = ('collect', 'train', 'predict', 'submit', 'verify')


class PipelineBlocked(ValueError):
    """A safe public explanation, without raw response or credential content."""


def _at(day, hour, minute=0):
    return datetime.combine(date.fromisoformat(day), time(hour, minute), TAIPEI)


def window(now, day):
    now = aware_datetime(now, name='execution time')
    if not _at(day, 4) <= now < _at(day, 9):
        raise PipelineBlocked('outside target-day 04:00-09:00 Taipei window')
    return now


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.daily-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def _json(path, value):
    _write(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode())


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _private_root(root):
    root = Path(root).resolve()
    if any((p / '.git').exists() for p in (root, *root.parents)):
        raise PipelineBlocked('runtime must be outside Git')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise PipelineBlocked('runtime must be locally owned with mode 0700')
    return root


def _approved(root):
    path = root / 'approved.json'
    if not path.exists():
        raise PipelineBlocked('no approved model; production prediction blocked')
    record = json.loads(path.read_text())
    model = Path(record['model_path']).resolve()
    if not model.is_relative_to(root / 'candidates'):
        raise PipelineBlocked('approved model must belong to private candidate store')
    if _hash(model / 'manifest.json') != record['manifest_sha256']:
        raise PipelineBlocked('approved model manifest changed')
    bundle = load_model_bundle(model, trusted=True)
    if not bundle.metadata.get('production_eligible') or bundle.metadata.get('readiness') != 'verified':
        raise PipelineBlocked('research model cannot be approved')
    if bundle.metadata.get('family') == 'gru':
        raise PipelineBlocked('daily GRU requires verified intervening feature history; not implemented')
    packages = bundle.metadata.get('package_versions')
    if not isinstance(packages, dict) or not packages or any(
        version(name) != expected for name, expected in packages.items()
    ):
        raise PipelineBlocked('approved model requires its recorded package versions')
    return record, bundle


def _fit_child(queue, table, destination, kwargs):
    try:
        queue.put({'ok': True, 'report': train_candidate(table, destination, **kwargs)})
    except Exception as error:
        queue.put({'ok': False, 'error_type': type(error).__name__})


def bounded_training(table, destination, kwargs, timeout_seconds):
    """A child process is terminated at timeout; no unbounded training thread."""
    if timeout_seconds <= 0:
        return {'status': 'timeout'}
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    worker = context.Process(target=_fit_child, args=(queue, table, destination, kwargs))
    worker.start()
    try:
        try:
            result = queue.get(timeout=timeout_seconds)
        except Exception:
            return {'status': 'timeout'}
        worker.join(timeout=1)
        return result
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
            if worker.is_alive():
                worker.kill()
                worker.join()
        queue.close()


def _private_file_bytes(path):
    path = Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise PipelineBlocked('snapshot evidence must not use symlinks')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PipelineBlocked('snapshot evidence must be a locally owned private regular file')
        return stream.read()


def _prediction_table(table, day, now):
    cutoff = _at(day, 8, 10)
    if now < cutoff:
        raise PipelineBlocked('prediction waits until the 08:10 feature freeze')
    if table.get('readiness') != 'verified' or not table.get('availability_evidence', '').strip():
        raise PipelineBlocked('prediction requires verified feature availability')
    evidence = table.get('feature_evidence')
    if not isinstance(evidence, list) or not evidence:
        raise PipelineBlocked('actual source fetch and availability evidence required')
    from finpred.data.daily_tables import (
        DailyTableError, SOURCE_URLS, live_fetch_in_prediction_window, verify_prediction_values,
    )

    covered, live_checked, bound_payloads = set(), False, {}
    columns = table.get('feature_columns')
    if not isinstance(columns, list) or not columns or len(set(columns)) != len(columns):
        raise PipelineBlocked('unique feature_columns required')
    for item in evidence:
        features = item.get('feature_columns')
        if (not isinstance(features, list) or not features
                or any(name not in columns for name in features)):
            raise PipelineBlocked('source evidence must identify covered feature columns')
        basis = item.get('availability_basis')
        if (not isinstance(basis, dict)
                or basis.get('kind') not in {'source_publication', 'verified_release_policy', 'observed_fetch'}
                or not isinstance(basis.get('reference'), str) or not basis['reference'].strip()):
            raise PipelineBlocked('source availability basis required')
        manifest_path = Path(item['snapshot_manifest'])
        manifest_bytes = _private_file_bytes(manifest_path)
        if hashlib.sha256(manifest_bytes).hexdigest() != item.get('snapshot_manifest_sha256'):
            raise PipelineBlocked('source manifest hash mismatch')
        manifest = json.loads(manifest_bytes)
        if (manifest.get('schema_version') != 'snapshot-v1'
                or manifest.get('source') != item.get('source') or not item.get('source')
                or manifest.get('sha256') != item.get('payload_sha256')):
            raise PipelineBlocked('source evidence does not bind the snapshot')
        payload = _private_file_bytes(Path(manifest['payload_path']))
        if (hashlib.sha256(payload).hexdigest() != item['payload_sha256']
                or len(payload) != manifest.get('size_bytes')):
            raise PipelineBlocked('source payload integrity failed')
        if (item['source'] not in SOURCE_URLS or item['source'] in bound_payloads
                or manifest.get('source_url') != SOURCE_URLS[item['source']]
                or not isinstance(manifest.get('metadata'), dict)
                or manifest['metadata'].get('tls_verified') is not True):
            raise PipelineBlocked('prediction requires unique, trusted course source snapshots with verified TLS')
        bound_payloads[item['source']] = payload
        fetched = aware_datetime(item.get('fetched_at'), name='fetched_at')
        if fetched != aware_datetime(manifest.get('fetched_at'), name='manifest fetched_at'):
            raise PipelineBlocked('source fetched time differs from snapshot')
        available = aware_datetime(item.get('available_at'), name='available_at')
        if basis['kind'] == 'observed_fetch' and available != fetched:
            raise PipelineBlocked('observed snapshot cannot backdate availability before actual fetch')
        if available > cutoff or fetched > cutoff:
            raise PipelineBlocked('feature was unavailable or fetched after freeze')
        if item['source'] == 'course-live':
            if (manifest.get('source_url') != SOURCE_URLS['course-live']
                    or not isinstance(manifest.get('metadata'), dict)
                    or manifest['metadata'].get('tls_verified') is not True
                    or not live_fetch_in_prediction_window(manifest['fetched_at'], day)):
                raise PipelineBlocked('course-live requires a target-day 04:00–08:10 Taipei acquisition with verified TLS')
            live_checked = True
        covered.update(features)
    if not live_checked:
        raise PipelineBlocked('hash-bound course-live source evidence is required')
    if covered != set(columns):
        raise PipelineBlocked('source evidence must cover every model feature')
    rows = table.get('rows', [])
    if len(rows) != 50 or len({r['stock_id'] for r in rows}) != 50:
        raise PipelineBlocked('prediction table must contain exactly 50 unique stocks')
    for row in rows:
        if row['target_date'] != day or aware_datetime(row['feature_cutoff'], name='cutoff') != cutoff:
            raise PipelineBlocked('prediction rows must use target-day 08:10 cutoff')
    try:
        verify_prediction_values(table, day, bound_payloads)
    except (DailyTableError, ValueError, KeyError, TypeError):
        raise PipelineBlocked('prediction inputs do not match the trusted course-source reconstruction') from None
    return cutoff


def _collect(root, day):
    records, failures = [], []
    for source in ('training', 'live'):
        try:
            records.extend(download_course_sources(root / 'raw', source))
        except Exception as error:
            failures.append({'source': 'course-' + source, 'error_type': type(error).__name__})
    for source in SOURCE_SPECS:
        try:
            records.append(download_external(source, root / 'raw'))
        except Exception as error:
            failures.append({'source': source, 'error_type': type(error).__name__})
    # Full native history is needed before computing source-session returns.
    # The current-day bar can be incomplete; retaining it never certifies it.
    end = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    for source in HISTORY_SERIES:
        try:
            records.append(download_market_history(source, '2019-12-01', end, root / 'market-history'))
        except Exception as error:
            failures.append({'source': 'yahoo-' + source, 'error_type': type(error).__name__})
    try:
        records.append(download_twse_sector_snapshot(root / 'raw'))
    except Exception as error:
        failures.append({'source': 'twse-sectors', 'error_type': type(error).__name__})
    result = {'status': 'partial' if failures else 'collected',
              'manifests': [r['manifest_path'] for r in records], 'failures': failures}
    _json(root / 'latest_collection.json', result)
    return result


def _train(root, day, now, clock, table_path, allow_research, train_worker):
    if not _at(day, 7, 20) <= now < _at(day, 7, 50):
        raise PipelineBlocked('candidate training starts from 07:20 and stops at 07:50')
    if table_path is None:
        raise PipelineBlocked('--training-table is required; raw snapshots are not certified features')
    table = json.loads(Path(table_path).read_bytes())
    if table.get('readiness') != 'verified' and not allow_research:
        raise PipelineBlocked('non-verified training requires explicit research opt-in')
    incumbent = None
    incumbent_manifest = None
    incumbent_metadata = None
    if (root / 'approved.json').exists():
        approved, bundle = _approved(root)
        incumbent_manifest = approved['manifest_sha256']
        incumbent_metadata = bundle.metadata
        if (table.get('feature_columns') != bundle.metadata.get('feature_columns')
                or table.get('feature_version') != bundle.metadata.get('feature_version')):
            raise PipelineBlocked('candidate features must match the approved model schema')
        incumbent = {k: bundle.metadata[k] for k in ('family', 'objective', 'seed')}
    package = Path(__file__).resolve().parents[1]
    code_files = ['pipelines/daily.py', 'training/fit.py', 'models/estimators.py',
                  'inference/predict.py', 'evaluation/official_score.py', 'labels/intraday.py',
                  'data/daily_tables.py', 'data/training_table.py', 'features/stock.py']
    kwargs = {'fit_cutoff': _at(day, 7, 20).isoformat(), 'incumbent_configuration': incumbent,
              'incumbent_metadata': incumbent_metadata,
              'min_train_dates': 252, 'validation_dates': 60, 'allow_research': allow_research,
              'epochs': 8}
    decision_input = {'table': table, 'incumbent_manifest_sha256': incumbent_manifest,
                      'training_options': kwargs,
                      'package_versions': {name: version(name) for name in ('scikit-learn', 'numpy', 'joblib')},
                      'code_sha256': {name: _hash(package / name) for name in code_files}}
    identity = hashlib.sha256(json.dumps(decision_input, sort_keys=True).encode()).hexdigest()
    destination = root / 'candidates' / day / identity
    report_file = destination / 'candidate_report.json'
    if report_file.exists():
        result = {'ok': True, 'report': json.loads(report_file.read_text())}
    else:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        remaining = (_at(day, 7, 50) - aware_datetime(clock(), name='clock')).total_seconds()
        result = train_worker(table, destination, kwargs, remaining)
    if not result.get('ok') or aware_datetime(clock(), name='clock') >= _at(day, 7, 50):
        return {'status': 'fallback', 'reason': result.get('status', 'candidate_failed'),
                'approved_model_available': (root / 'approved.json').exists()}
    report = result['report']
    if allow_research or not report.get('eligible_for_promotion') or report.get('readiness') != 'verified':
        return {'status': 'candidate_not_promoted', 'report_path': str(report_file),
                'approved_model_available': (root / 'approved.json').exists()}
    model = Path(report['model_path']).resolve()
    if not model.is_relative_to(destination.resolve()):
        raise PipelineBlocked('candidate model path escaped its run directory')
    bundle = load_model_bundle(model, trusted=True)
    if not bundle.metadata.get('production_eligible') or bundle.metadata['fit_cutoff'] != kwargs['fit_cutoff']:
        raise PipelineBlocked('candidate model production or cutoff mismatch')
    if bundle.metadata['training_table_sha256'] != hashlib.sha256(
        json.dumps(table, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest():
        raise PipelineBlocked('candidate training table hash mismatch')
    pointer = {'model_path': str(model), 'manifest_sha256': _hash(model / 'manifest.json'),
               'approved_at': aware_datetime(clock(), name='clock').isoformat(),
               'report_path': str(report_file), 'configuration': report['selected_configuration']}
    old = root / 'approved.json'
    if old.exists() and aware_datetime(json.loads(old.read_text())['approved_at'], name='approval') > now:
        raise PipelineBlocked('older training run cannot replace a newer approval')
    _json(old, pointer)
    return {'status': 'promoted', **pointer}


def _predict(root, day, now, client, table_path):
    if table_path is None:
        raise PipelineBlocked('--prediction-table is required')
    table_bytes = Path(table_path).read_bytes()
    table = json.loads(table_bytes)
    cutoff = _prediction_table(table, day, now)
    approved, bundle = _approved(root)
    predictions = predict_rows(bundle, table['rows'], feature_columns=table['feature_columns'],
                               feature_version=table['feature_version'], require_production=True)
    template = client.daily_template(day)
    template_rows = list(csv.reader(io.StringIO(template.decode('utf-8-sig'))))
    ordered = {p['stock_id']: p['prediction'] for p in predictions}
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['id', day])
    for row in template_rows[1:]:
        if row[0] not in ordered:
            raise PipelineBlocked('prediction IDs differ from official template')
        writer.writerow([row[0], ordered[row[0]]])
    payload = output.getvalue().encode()
    validate_prediction_csv(payload, template, day)
    metadata = {'generated_at': now.isoformat(), 'target_date': day,
                'model_manifest_sha256': approved['manifest_sha256'],
                'feature_table_sha256': hashlib.sha256(table_bytes).hexdigest(), 'model_path': approved['model_path'],
                'csv_sha256': hashlib.sha256(payload).hexdigest(),
                'readiness': {'model_validated': True, 'feature_availability_verified': True,
                              'feature_cutoff': cutoff.isoformat()}}
    identity = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    destination = root / 'predictions' / day / identity
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    csv_path = destination / 'prediction.csv'
    if not csv_path.exists():
        _write(csv_path, payload)
        _json(destination / 'manifest.json', metadata)
    else:
        metadata = json.loads((destination / 'manifest.json').read_text())
    _json(root / 'predictions' / day / 'latest.json', {'csv_path': str(csv_path), **metadata})
    return {'status': 'predicted', 'csv_path': str(csv_path), **metadata}


def _submit(root, day, client, clock, dry_run, csv_path, verify_only):
    latest_path = root / 'predictions' / day / 'latest.json'
    if not latest_path.exists():
        raise PipelineBlocked('no pipeline-generated prediction manifest')
    latest = json.loads(latest_path.read_text())
    path = Path(latest['csv_path'])
    if csv_path is not None and Path(csv_path).resolve() != path.resolve():
        raise PipelineBlocked('--csv must identify the latest pipeline-generated version')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != latest['csv_sha256']:
        raise PipelineBlocked('prediction CSV hash mismatch')
    approved, bundle = _approved(root)
    if approved['manifest_sha256'] != latest['model_manifest_sha256']:
        raise PipelineBlocked('approved model changed; regenerate predictions')
    if not bundle.metadata.get('production_eligible'):
        raise PipelineBlocked('research model cannot submit')
    if verify_only:
        template = client.daily_template(day)
        expected = validate_prediction_csv(payload, template, day)
        receipt = client.current_receipt(client.state(), day, expected, template)
        if receipt is None:
            raise PipelineBlocked('no matching official current receipt')
        _json(root / 'verified' / f'{day}.json', receipt)
        return receipt
    return execute_submission(client, payload, day, root, dry_run=dry_run,
                              generated_at=latest['generated_at'], readiness=latest['readiness'], clock=clock)


def run_stage(runtime_dir, stage, *, target_date=None, dry_run=True,
              training_table=None, prediction_table=None, csv_path=None,
              allow_research_training=False, client=None, clock=None,
              train_worker=bounded_training):
    """Run one stage; tests inject a clock/client, CLI always uses real time."""
    if stage not in STAGES:
        raise PipelineBlocked('unknown stage')
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = aware_datetime(clock(), name='clock')
    day = target_date or now.astimezone(TAIPEI).date().isoformat()
    window(now, day)
    root = _private_root(runtime_dir)
    with (root / 'pipeline.lock').open('a+') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        owned = client is None
        if owned:
            client = CourseSubmissionClient()
        run_id = uuid.uuid4().hex
        result = {'run_id': run_id, 'stage': stage, 'target_date': day, 'started_at': now.isoformat(), 'dry_run': dry_run}
        try:
            if owned:
                client.login(os.environ.get('COURSE_EMAIL'), os.environ.get('COURSE_PASSWORD'))
            now = window(clock(), day)
            session = _session(client.state(), day)
            if session.get('enabled') not in (True, 1):
                raise PipelineBlocked('official target session is disabled')
            if stage == 'collect':
                value = _collect(root, day)
            elif stage == 'train':
                if training_table is None:
                    prepared = prepare_training_table(root, day, allow_research=allow_research_training)
                    result['preparation'] = prepared
                    if not prepared.get('table_path'):
                        raise PipelineBlocked('historical training availability unverified; see preparation report')
                    training_table = prepared['table_path']
                value = _train(root, day, now, clock, training_table, allow_research_training, train_worker)
            elif stage == 'predict':
                if prediction_table is None:
                    prepared = prepare_prediction_table(root, day)
                    result['preparation'] = prepared
                    if not prepared.get('table_path'):
                        raise PipelineBlocked('no verified current prediction table; see preparation report')
                    prediction_table = prepared['table_path']
                value = _predict(root, day, now, client, prediction_table)
            else:
                value = _submit(root, day, client, clock, dry_run, csv_path, stage == 'verify')
            window(clock(), day)
            result.update(value)
        except Exception as error:
            result.update(status='blocked', error_type=type(error).__name__)
            if isinstance(error, PipelineBlocked):
                result['reason'] = str(error)
            raise
        finally:
            _json(root / 'runs' / day / f'{stage}-{run_id}.json', result)
            _json(root / 'runs' / day / f'{stage}.json', result)
            if owned:
                client.close()
        return result
