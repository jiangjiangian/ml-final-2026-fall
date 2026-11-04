"""Static Phase 1 submission with artifact checks and a durable no-retry ledger.

The official frontend's Phase 1 contract is a stock-by-date prediction matrix.
It uses the Phase 1 opening/deadline and daily quota, never Phase 2's 09:00
session or approved-model policy. Research vintages remain explicitly unverified.
"""

import csv
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
from datetime import date, datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from finpred.data.daily_tables import SOURCE_URLS as DAILY_SOURCE_URLS
from finpred.features.stock import STOCK_FEATURES
from finpred.features.market import FEATURE_COLUMNS as MARKET_FEATURES
from finpred.ingestion.course import CourseDownloadError
from finpred.submission.course import CourseSubmissionClient, SubmissionError, _aware
from finpred.submission.phase1 import (
    _sync_directory, build_phase1_csv, parse_prediction_json, read_input_bytes,
    template_contract, validate_phase1_csv,
)

TAIPEI = ZoneInfo('Asia/Taipei')
MAX_ARTIFACT_BYTES = 90 * 1024 * 1024
SHA256 = re.compile(r'[0-9a-f]{64}')
SOURCE_URLS = {**DAILY_SOURCE_URLS,
               'course-template': 'https://final.html2026.csie.org/api/sample-submission'}
FIXED_RECIPE = {'family': 'M3', 'dropout': 0.1, 'epochs': 20, 'lookback': 20,
                'hidden': 32, 'seed': 42, 'batch_dates': 128, 'market_indices': []}
EXPECTED_FEATURES = list(STOCK_FEATURES) + list(MARKET_FEATURES)
FORECAST_CODE_FILES = {
    'src/finpred/training/phase1_forecast.py', 'src/finpred/training/architecture_comparison.py',
    'src/finpred/models/temporal.py', 'src/finpred/features/stock.py',
    'src/finpred/data/training_table.py', 'src/finpred/training/fit.py',
    'src/finpred/labels/intraday.py', 'src/finpred/submission/phase1.py',
}


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _document_sha(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())


def _json(payload):
    def unique_object(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError('duplicate artifact keys')
            value[key] = child
        return value

    def invalid_constant(value):
        raise ValueError('nonfinite artifact number')

    try:
        value = json.loads(payload, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise SubmissionError('artifact JSON is invalid') from None
    if not isinstance(value, dict):
        raise SubmissionError('artifact JSON must be an object')
    return value


def _private_bytes(path, *, limit=MAX_ARTIFACT_BYTES):
    path = Path(path).absolute()
    payload = read_input_bytes(path, limit=limit)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SubmissionError('submission evidence must be locally owned with private permissions')
    return payload


def _artifact_path(root, name):
    if (not isinstance(name, str) or '\\' in name or PurePosixPath(name).is_absolute()
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise SubmissionError('unsafe forecast artifact path')
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise SubmissionError('forecast artifact escaped its root')
    return path


def phase1_payload(csv_bytes, template_bytes):
    """Exact official wire shape, retaining stock and date order from the CSV."""
    validate_phase1_csv(csv_bytes, template_bytes)
    rows = list(csv.reader(io.StringIO(csv_bytes.decode('utf-8-sig'))))
    return {'stockIds': [row[0] for row in rows[1:]], 'dates': rows[0][1:],
            'predictions': [[int(cell) for cell in row[1:]] for row in rows[1:]]}


def validate_forecast_evidence(manifest_path, csv_bytes, template_bytes, *, now):
    """Bind the actual fixed-fit artifacts; do not certify historical release times."""
    manifest_path = Path(manifest_path).absolute()
    manifest_bytes = _private_bytes(manifest_path, limit=4 * 1024 * 1024)
    manifest = _json(manifest_bytes)
    contract = template_contract(template_bytes)
    first_day = contract['target_dates'][0]
    required = {
        'schema_version': 'phase1-forecast-v1', 'phase': 1,
        'readiness': 'research_assumption', 'historical_availability_verified': False,
        'production_eligible': False, 'submitted': False,
        'no_phase1_labels_used': True, 'phase1_targets_scored': False,
        'model_fit_count': 1, 'recipe_id': 'M3-2',
        'stock_count': 50, 'date_count': 84, 'prediction_count': 4200,
        'template_sha256': _sha(template_bytes), 'csv_sha256': _sha(csv_bytes),
    }
    if any(manifest.get(key) != value or (type(value) in (bool, int) and type(manifest.get(key)) is not type(value))
           for key, value in required.items()):
        raise SubmissionError('forecast does not meet the fixed Phase 1 benchmark contract')
    generated = _aware(manifest.get('generated_at'))
    if generated > now:
        raise SubmissionError('prediction generation time is in the future')
    end = manifest.get('training_label_end_date')
    try:
        if not isinstance(end, str) or date.fromisoformat(end).isoformat() != end or end >= first_day:
            raise ValueError
    except ValueError:
        raise SubmissionError('training labels must end before the first Phase 1 target') from None
    artifacts = manifest.get('artifact_sha256')
    required_names = {
        'registration.json', 'training-table.json', 'feature-rows.json', 'predictions.json',
        'model/preprocessor.joblib', 'model/weights.npz', 'model/metadata.json',
        'submission/predictions.csv', 'submission/manifest.json', 'template.csv', 'feature-evidence.json',
        'selection-report.json',
        'market-feature-rows.json',
    }
    if not isinstance(artifacts, dict) or not required_names <= set(artifacts):
        raise SubmissionError('complete immutable model and forecast artifacts are required')
    contents = {}
    root = manifest_path.parent
    for name, expected in artifacts.items():
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise SubmissionError('forecast artifact digest is invalid')
        content = _private_bytes(_artifact_path(root, name))
        if _sha(content) != expected:
            raise SubmissionError('forecast artifact checksum mismatch')
        contents[name] = content
    if (contents['submission/predictions.csv'] != csv_bytes or contents['template.csv'] != template_bytes
            or artifacts['registration.json'] != manifest.get('registration_sha256')
            or artifacts['predictions.json'] != manifest.get('prediction_json_sha256')):
        raise SubmissionError('forecast manifest does not bind the submitted bytes')
    rebuilt = build_phase1_csv(parse_prediction_json(contents['predictions.json']), template_bytes)
    if rebuilt != csv_bytes:
        raise SubmissionError('CSV differs from the bound prediction rows')
    formatted = _json(contents['submission/manifest.json'])
    if (formatted.get('csv_sha256') != _sha(csv_bytes)
            or formatted.get('template_sha256') != _sha(template_bytes)):
        raise SubmissionError('formatter manifest does not bind CSV and template')
    training = _json(contents['training-table.json'])
    rows = training.get('rows')
    if (not isinstance(rows, list) or not rows or training.get('readiness') != 'research_assumption'
            or any(not isinstance(row, dict) or not isinstance(row.get('target_date'), str)
                   or row['target_date'] >= first_day for row in rows)
            or max(row['target_date'] for row in rows) != end):
        raise SubmissionError('saved training table violates the Phase 1 label prefix')
    registration = _json(contents['registration.json'])
    features = _json(contents['feature-rows.json'])
    metadata = _json(contents['model/metadata.json'])
    reference = registration.get('selection_reference')
    from finpred.training.phase1_forecast import frozen_market_features, selection_reference

    try:
        replayed_reference = selection_reference(contents['selection-report.json'])
        market_vectors, market_binding = frozen_market_features(
            contents['market-feature-rows.json'], contents['selection-report.json'], contract['stock_ids'])
    except (ValueError, KeyError, TypeError):
        raise SubmissionError('original fixed recipe selection report is invalid') from None
    loss = metadata.get('training_mse_percentage_point_history')
    packages = registration.get('package_versions')
    if (registration.get('schema_version') != 'phase1-fixed-registration-v1'
            or registration.get('scope') != 'static_phase1_backtest_not_phase2_production'
            or registration.get('recipe_id') != 'M3-2' or registration.get('recipe') != FIXED_RECIPE
            or registration.get('readiness') != 'research_assumption'
            or registration.get('historical_availability_verified') is not False
            or registration.get('production_eligible') is not False
            or registration.get('no_phase1_labels_used') is not True
            or registration.get('target_dates_scored') is not False
            or registration.get('template_sha256') != _sha(template_bytes)
            or registration.get('target_dates') != contract['target_dates']
            or registration.get('stock_ids') != contract['stock_ids']
            or registration.get('panel_stock_ids') != sorted(contract['stock_ids'])
            or registration.get('training_rows') != len(rows)
            or registration.get('training_label_start_date') != min(row['target_date'] for row in rows)
            or registration.get('training_label_end_date') != end
            or registration.get('training_table_sha256') != _document_sha(training)
            or registration.get('training_table_file_sha256') != artifacts['training-table.json']
            or registration.get('feature_rows_sha256') != _document_sha(features)
            or registration.get('feature_rows_file_sha256') != artifacts['feature-rows.json']
            or registration.get('market_feature_rows_sha256') != artifacts['market-feature-rows.json']
            or registration.get('market_feature_document_sha256') != market_binding['market_feature_document_sha256']
            or registration.get('market_feature_binding') != market_binding
            or manifest.get('market_feature_rows_sha256') != artifacts['market-feature-rows.json']
            or manifest.get('market_feature_document_sha256') != market_binding['market_feature_document_sha256']
            or registration.get('code_sha256') != manifest.get('code_sha256')
            or _aware(registration.get('registered_at')) > generated
            or not isinstance(registration.get('code_git_revision_at_registration'), str)
            or not re.fullmatch(r'[0-9a-f]{40}', registration['code_git_revision_at_registration'])
            or not isinstance(packages, dict) or set(packages) != {'numpy', 'scikit-learn', 'joblib', 'torch'}
            or any(not isinstance(value, str) or not value for value in packages.values())):
        raise SubmissionError('fixed preregistration does not bind the recipe, inputs and code')
    if (reference != replayed_reference or not isinstance(reference, dict) or reference.get('recipe_id') != 'M3-2'
            or reference.get('selection_scope') != 'completed_2025_exploration_only'
            or reference.get('phase1_selection_or_scoring') is not False
            or reference.get('completed_prior_fits') != 48
            or not isinstance(reference.get('report_sha256'), str)
            or not SHA256.fullmatch(reference['report_sha256'])
            or type(reference.get('historical_validation_score')) not in (int, float)
            or not math.isfinite(reference['historical_validation_score'])):
        raise SubmissionError('fixed recipe selection must remain the completed 2025 exploration')
    if (training.get('feature_columns') != EXPECTED_FEATURES
            or features.get('schema_version') != 'sequence-feature-table-v1'
            or features.get('feature_columns') != EXPECTED_FEATURES
            or features.get('feature_version') != training.get('feature_version')
            or features.get('readiness') != 'research_assumption'
            or features.get('production_eligible') is not False
            or features.get('stock_ids') != sorted(contract['stock_ids'])
            or features.get('frozen_market_feature_binding') != market_binding
            or metadata.get('schema_version') != 'phase1-tcn-model-v1'
            or metadata.get('recipe_id') != 'M3-2' or metadata.get('recipe') != FIXED_RECIPE
            or metadata.get('readiness') != 'research_assumption'
            or metadata.get('production_eligible') is not False
            or metadata.get('feature_columns') != EXPECTED_FEATURES
            or metadata.get('feature_version') != training.get('feature_version')
            or metadata.get('stock_ids') != sorted(contract['stock_ids'])
            or metadata.get('package_versions') != packages
            or type(metadata.get('input_channels')) is not int or metadata['input_channels'] != 2 * len(EXPECTED_FEATURES) + 1
            or not isinstance(loss, list) or len(loss) != FIXED_RECIPE['epochs']
            or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in loss)):
        raise SubmissionError('saved model and features differ from the fixed preregistration')
    feature_rows = features.get('rows')
    if not isinstance(feature_rows, list):
        raise SubmissionError('complete outcome-free input feature rows are required')
    for row in [*rows, *feature_rows]:
        vector = market_vectors.get(row.get('target_date')) if isinstance(row, dict) else None
        if (vector is None or row.get('feature_cutoff') != vector['feature_cutoff']
                or any(column not in row or row[column] != vector[column] for column in MARKET_FEATURES)):
            raise SubmissionError('saved inputs differ from the original frozen R2 market vectors')
    sources = manifest.get('source_snapshots')
    if (not isinstance(sources, list) or not sources
            or registration.get('source_snapshots') != sources):
        raise SubmissionError('registration and forecast source provenance differ')
    seen = set()
    for source in sources:
        if not isinstance(source, dict) or source.get('source') not in SOURCE_URLS:
            raise SubmissionError('unrecognized course snapshot source')
        name = source['source']
        if name in seen or source.get('source_url') != SOURCE_URLS[name] or source.get('tls_verified') is not True:
            raise SubmissionError('unique official verified-TLS course sources are required')
        seen.add(name)
        snapshot_bytes = _private_bytes(source.get('manifest_path'), limit=4 * 1024 * 1024)
        snapshot = _json(snapshot_bytes)
        payload = _private_bytes(source.get('payload_path'))
        if (_sha(snapshot_bytes) != source.get('manifest_sha256')
                or _sha(payload) != source.get('payload_sha256')
                or snapshot.get('schema_version') != 'snapshot-v1' or snapshot.get('source') != name
                or snapshot.get('source_url') != SOURCE_URLS[name]
                or snapshot.get('sha256') != source.get('payload_sha256')
                or snapshot.get('size_bytes') != len(payload)
                or Path(snapshot.get('payload_path', '')).absolute() != Path(source['payload_path']).absolute()
                or snapshot.get('metadata', {}).get('tls_verified') is not True
                or _aware(source.get('fetched_at')) != _aware(snapshot.get('fetched_at'))
                or _aware(source.get('fetched_at')) > _aware(registration['registered_at'])):
            raise SubmissionError('source snapshots are not bound to observed authentic-origin bytes')
        if name == 'course-template' and payload != template_bytes:
            raise SubmissionError('collected template source differs from submitted template bytes')
    if seen != set(SOURCE_URLS):
        raise SubmissionError('teacher training, live and official template snapshots are required')
    code = manifest.get('code_sha256')
    if not isinstance(code, dict) or set(code) != FORECAST_CODE_FILES:
        raise SubmissionError('forecast code identity is required')
    project = Path(__file__).resolve().parents[3]
    for name, expected in code.items():
        if _sha(read_input_bytes(_artifact_path(project, name), limit=4 * 1024 * 1024)) != expected:
            raise SubmissionError('forecast code differs from the recorded implementation')
    return {'forecast_manifest_sha256': _sha(manifest_bytes), 'generated_at': generated.isoformat(),
            'recipe_id': manifest['recipe_id'], 'training_label_end_date': end,
            'historical_availability_verified': False, 'production_eligible': False}


def phase1_guard(state, now):
    config = state.get('config')
    if not isinstance(config, dict):
        raise SubmissionError('official Phase 1 configuration is unavailable')
    if not _aware(config.get('phase1OpenAt'), server=True) <= now < _aware(config.get('phase1Deadline'), server=True):
        raise SubmissionError('official Phase 1 submission window is not open or deadline passed')
    user = state.get('user')
    if not isinstance(user, dict) or not isinstance(user.get('role'), str) or not user['role']:
        raise SubmissionError('authenticated course user is required')
    if user['role'] == 'student' and not state.get('team'):
        raise SubmissionError('student account must belong to an official team')
    quotas = state.get('uploadQuota')
    quota = quotas.get('phase1') if isinstance(quotas, dict) else None
    if not isinstance(quota, dict) or quota.get('day') != now.astimezone(TAIPEI).date().isoformat():
        raise SubmissionError('fresh official Phase 1 daily upload quota is unavailable')
    for prefix in ('user', 'team'):
        limit, count = quota.get(prefix + 'Limit'), quota.get(prefix + 'Count')
        if type(limit) is not int or type(count) is not int or limit < 0 or count < 0:
            raise SubmissionError('official Phase 1 quota is malformed')
        if limit and count >= limit:
            raise SubmissionError('official Phase 1 upload quota exhausted')
    return {'open_at': _aware(config['phase1OpenAt'], server=True).isoformat(),
            'deadline': _aware(config['phase1Deadline'], server=True).isoformat()}


class Phase1SubmissionClient(CourseSubmissionClient):
    """Only the verified Phase 1 wire fields; no Phase 2 session is consulted."""

    def post_phase1(self, file_name, payload):
        response = None
        try:
            response = self.session.request(
                'POST', self.base + '/api/submissions', timeout=(10, 30), verify=True,
                allow_redirects=False, stream=True,
                json={'phase': 1, 'fileName': file_name, 'payload': payload,
                      'note': 'finpred fixed prefix-trained Phase1 benchmark; historical vintage not certified'},
                headers={'Origin': self.base, 'Referer': self.base + '/'})
            if not 200 <= response.status_code < 300:
                raise SubmissionError('Phase 1 POST did not acknowledge HTTP success; body omitted')
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > 1024 * 1024:
                    raise SubmissionError('Phase 1 acknowledgement exceeded its size limit')
                chunks.append(chunk)
            ack = _json(b''.join(chunks))
            if ack.get('error') or ack.get('success') is False:
                raise SubmissionError('Phase 1 acknowledgement rejected; body omitted')
        except requests.RequestException:
            raise SubmissionError('Phase 1 POST outcome unknown; response omitted') from None
        finally:
            if response is not None:
                response.close()

    def phase1_receipt(self, state, expected, template):
        records = state.get('mySubmissions')
        if not isinstance(records, list):
            raise SubmissionError('official current submissions are unavailable')
        current = [item for item in records if isinstance(item, dict) and item.get('phase') == 1]
        if len(current) > 1:
            raise SubmissionError('official current Phase 1 record is ambiguous')
        if not current:
            return None
        record = current[0]
        if not isinstance(record.get('id'), (str, int)) or isinstance(record.get('id'), bool) or not str(record['id']):
            raise SubmissionError('official current Phase 1 record identifier is unavailable')
        raw = self.read('GET', '/api/submissions/' + quote(str(record['id']), safe='') + '?record=current',
                        max_bytes=2 * 1024 * 1024)
        if phase1_payload(raw, template) != expected:
            return None
        return {'status': 'verified', 'record_id': str(record['id']),
                'submitted_at': _aware(record.get('submittedAt'), server=True).isoformat(),
                'scoring_status': 'pending' if record.get('score') is None else 'scored',
                'receipt_method': 'current_state_record_plus_downloaded_4200_cell_comparison',
                'receipt_csv_sha256': _sha(raw), 'submitted': True}


def _private_directory(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise SubmissionError('submission runtime must not use symbolic links')
    missing, current = [], path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SubmissionError('submission runtime must be locally owned with mode 0700')
    return path


def _write_ledger(path, record):
    if path.is_symlink():
        raise SubmissionError('submission ledger must not be a symbolic link')
    descriptor, temporary = tempfile.mkstemp(prefix='.phase1-ledger-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(record, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def execute_phase1_submission(client, csv_bytes, template_bytes, runtime_dir, *, forecast_manifest,
                              file_name='phase1-predictions.csv', dry_run=True, verify_only=False,
                              clock=None, poll_attempts=3, poll_interval=1.0):
    """One authorized static-benchmark POST; unknown outcomes never auto-repeat."""
    if Path(file_name).name != file_name or not file_name.endswith('.csv'):
        raise SubmissionError('file name must be a plain CSV filename')
    if type(poll_attempts) is not int or not 1 <= poll_attempts <= 5 or not 0 <= poll_interval <= 5:
        raise SubmissionError('Phase 1 receipt polling must be bounded')
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(clock())
    fresh_template = client.template()
    if template_contract(fresh_template) != template_contract(template_bytes):
        raise SubmissionError('saved Phase 1 template differs from the current official identity')
    expected = phase1_payload(csv_bytes, fresh_template)
    evidence = validate_forecast_evidence(forecast_manifest, csv_bytes, template_bytes, now=now)
    result = {'phase': 1, 'csv_sha256': _sha(csv_bytes), 'template_sha256': _sha(template_bytes),
              'stock_count': 50, 'date_count': 84, 'prediction_count': 4200,
              **evidence, 'submitted': False}
    state = client.state()
    if dry_run:
        blockers = []
        try:
            phase1_guard(state, now)
        except SubmissionError as error:
            blockers.append(str(error))
        return {**result, 'status': 'dry_run', 'would_submit': not blockers, 'blockers': blockers}
    root = Path(runtime_dir).absolute()
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise SubmissionError('submission runtime must be outside Git')
    root = _private_directory(root)
    base = _private_directory(_private_directory(root / 'submission') / 'phase1')
    lock_fd = os.open(base / 'submission.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'a+') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise SubmissionError('submission lock must be a private regular file')
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        ledger_path = base / 'latest.json'
        ledger = _json(_private_bytes(ledger_path)) if ledger_path.exists() else None
        if ledger and _aware(result['generated_at']) < _aware(ledger.get('generated_at')):
            raise SubmissionError('older Phase 1 prediction job cannot replace a newer version')
        state = client.state()
        receipt = client.phase1_receipt(state, expected, fresh_template)
        if receipt:
            result.update(receipt)
            _write_ledger(ledger_path, result)
            return result
        if verify_only:
            return {**result, 'status': 'no_matching_current_receipt'}
        if ledger and ledger.get('status') in {'post_in_flight', 'unverified'}:
            raise SubmissionError('prior Phase 1 POST outcome unresolved; reconcile before retrying')
        for record in state.get('mySubmissions', []):
            if (isinstance(record, dict) and record.get('phase') == 1
                    and _aware(record.get('submittedAt'), server=True) > _aware(result['generated_at'])):
                raise SubmissionError('older Phase 1 prediction job cannot replace a newer official version')
        phase1_guard(state, _aware(clock()))
        result['status'] = 'post_in_flight'
        _write_ledger(ledger_path, result)
        # Disk checkpoint and state reads consume actual time; check fresh quota
        # and the real deadline after persistence, directly before the only POST.
        try:
            phase1_guard(client.state(), _aware(clock()))
        except SubmissionError:
            result['status'] = 'blocked_before_post'
            _write_ledger(ledger_path, result)
            raise
        try:
            client.post_phase1(file_name, expected)
        except (CourseDownloadError, SubmissionError):
            result['status'] = 'unverified'
            _write_ledger(ledger_path, result)
            raise SubmissionError('Phase 1 POST outcome unverified; reconcile state before retrying') from None
        for attempt in range(poll_attempts):
            receipt = client.phase1_receipt(client.state(), expected, fresh_template)
            if receipt:
                result.update(receipt)
                _write_ledger(ledger_path, result)
                return result
            if attempt + 1 < poll_attempts and poll_interval:
                time.sleep(poll_interval)
        result['status'] = 'unverified'
        _write_ledger(ledger_path, result)
        raise SubmissionError('Phase 1 acknowledgement lacks a verified current receipt; not retried')
