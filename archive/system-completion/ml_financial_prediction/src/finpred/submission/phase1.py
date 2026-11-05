"""Offline Phase 1 formatting only: exact template cells, never model approval.

Predictions must already exist. This module neither loads models nor reads outcome
tables, fits estimators, contacts the course service, or certifies historical PIT.
Input identity hashes prove bytes, rather than the provenance of a prediction.
"""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat

from finpred.data.snapshots import _exclusive_write
from finpred.ingestion.course import CourseDownloadError, audit_template

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
PHASE1_START, PHASE1_END = '2026-06-01', '2026-09-30'
ROW_FIELDS = {'stock_id', 'target_date', 'prediction'}
MODEL_FIELDS = {
    'schema_version', 'created_by', 'family', 'objective', 'seed', 'feature_columns',
    'feature_version', 'fit_cutoff', 'train_end_date', 'train_rows', 'readiness',
    'availability_evidence', 'production_eligible', 'training_table_sha256', 'epochs',
    'availability_policy_version', 'package_versions', 'code_sha256', 'model_sha256',
}
OUTCOME_FIELDS = {'y', 'label', 'labels', 'outcome', 'outcomes', 'adj_open', 'adj_close',
                  'target_intraday_return', 'label_rows'}


class Phase1Error(ValueError):
    """A safe contract error without input values or source paths."""


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def template_contract(payload, *, expected_stock_count=50, expected_date_count=84):
    """Read the exact supplied order; never infer exchange sessions from weekdays.

    Smaller explicit dimensions support generic offline tests. The CLI always
    requires the official 50 x 84 contract and the competition date interval.
    """
    if (type(expected_stock_count) is not int or type(expected_date_count) is not int
            or not 1 <= expected_stock_count <= 1000 or not 1 <= expected_date_count <= 366):
        raise Phase1Error('positive bounded integer template dimensions required')
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_TEMPLATE_BYTES:
        raise Phase1Error('template requires bounded nonempty CSV bytes')
    try:
        contract = audit_template(payload, expected_target_count=expected_stock_count)
    except CourseDownloadError:
        raise Phase1Error('Phase 1 template shape, identifiers, dates or values are invalid') from None
    if (len(contract['target_dates']) != expected_date_count
            or any(not PHASE1_START <= day <= PHASE1_END for day in contract['target_dates'])):
        raise Phase1Error('Phase 1 template date count or competition interval is invalid')
    return contract


def _unique_json_object(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise Phase1Error('duplicate JSON object keys are forbidden')
        value[key] = child
    return value


def _invalid_json_constant(value):
    raise Phase1Error('nonfinite JSON numbers are forbidden')


def parse_prediction_json(payload):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_INPUT_BYTES:
        raise Phase1Error('predictions require bounded nonempty JSON bytes')
    try:
        return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=_unique_json_object,
                          parse_constant=_invalid_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise Phase1Error('predictions JSON is malformed') from None


def _reject_outcomes(value):
    pending = [value]
    seen = set()
    while pending:
        item = pending.pop()
        if isinstance(item, (dict, list, tuple)):
            if id(item) in seen:
                raise Phase1Error('cyclic or repeated metadata containers are unsupported')
            seen.add(id(item))
        if isinstance(item, dict):
            if any(str(key).lower() in OUTCOME_FIELDS or str(key).lower().startswith('etl:adj_')
                   for key in item):
                raise Phase1Error('outcome or label fields cannot accompany predictions')
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)


def _prediction_rows(predictions):
    if isinstance(predictions, dict):
        allowed = {'schema_version', 'readiness', 'rows', 'predictions', 'model'}
        if set(predictions) - allowed or ('rows' in predictions) == ('predictions' in predictions):
            raise Phase1Error('prediction wrapper requires exactly one rows or predictions array')
        if predictions.get('schema_version', 'phase1-predictions-v1') != 'phase1-predictions-v1':
            raise Phase1Error('unsupported Phase 1 prediction schema')
        if predictions.get('readiness', 'research_assumption') not in {'research_assumption', 'synthetic'}:
            raise Phase1Error('formatter accepts research or synthetic inputs only')
        if 'model' in predictions:
            metadata = predictions['model']
            if not isinstance(metadata, dict) or set(metadata) - MODEL_FIELDS:
                raise Phase1Error('unsupported model metadata; no arbitrary input fields accepted')
            _reject_outcomes(metadata)
            columns = metadata.get('feature_columns', [])
            if (not isinstance(columns, list) or any(not isinstance(name, str) or name.lower() in OUTCOME_FIELDS
                    or name.lower().startswith('etl:adj_') for name in columns)):
                raise Phase1Error('outcome columns cannot be model input features')
        rows = predictions['rows'] if 'rows' in predictions else predictions['predictions']
    else:
        rows = predictions
    if not isinstance(rows, (list, tuple)) or not rows:
        raise Phase1Error('predictions must be a nonempty row array')
    return rows


def build_phase1_csv(predictions, template_payload, *, expected_stock_count=50, expected_date_count=84):
    """Format an exact stock/date key set; reject extras, missing cells and labels."""
    contract = template_contract(template_payload, expected_stock_count=expected_stock_count,
                                 expected_date_count=expected_date_count)
    rows = _prediction_rows(predictions)
    ids, days = set(contract['stock_ids']), set(contract['target_dates'])
    cells = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise Phase1Error('each prediction must contain only stock_id, target_date and prediction')
        stock, day, value = row['stock_id'], row['target_date'], row['prediction']
        if (not isinstance(stock, str) or stock not in ids
                or not isinstance(day, str) or day not in days):
            raise Phase1Error('prediction identifier or date differs from the exact template')
        if type(value) is not int or value not in (0, 1):
            raise Phase1Error('prediction values must be integer zero or one, never booleans or probabilities')
        key = stock, day
        if key in cells:
            raise Phase1Error('duplicate stock/date prediction key')
        cells[key] = value
    if len(cells) != len(ids) * len(days):
        raise Phase1Error('every template stock/date cell requires exactly one prediction')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['id', *contract['target_dates']])
    for stock in contract['stock_ids']:
        writer.writerow([stock, *(cells[stock, day] for day in contract['target_dates'])])
    payload = stream.getvalue().encode('utf-8-sig' if template_payload.startswith(b'\xef\xbb\xbf') else 'utf-8')
    validate_phase1_csv(payload, template_payload, expected_stock_count=expected_stock_count,
                        expected_date_count=expected_date_count)
    return payload


def validate_phase1_csv(payload, template_payload, *, expected_stock_count=50, expected_date_count=84):
    """Validate CSV shape and exact template order, independently of input rows."""
    options = {'expected_stock_count': expected_stock_count, 'expected_date_count': expected_date_count}
    template = template_contract(template_payload, **options)
    candidate = template_contract(payload, **options)
    if candidate != template:
        raise Phase1Error('CSV stock and date order must exactly match the supplied template')
    return {'status': 'format_validated', 'stock_count': len(template['stock_ids']),
            'date_count': len(template['target_dates']),
            'prediction_count': len(template['stock_ids']) * len(template['target_dates']),
            'template_sha256': _sha(template_payload), 'csv_sha256': _sha(payload),
            'readiness': 'research_assumption', 'production_eligible': False,
            'submitted': False, 'validation_scope': 'format_and_template_identity_only'}


def _no_symlink(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise Phase1Error('input and output paths must not use symbolic links')


def read_input_bytes(path, *, limit=MAX_INPUT_BYTES):
    path = Path(path).absolute()
    _no_symlink(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise Phase1Error('input must be a bounded regular file')
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise Phase1Error('input exceeded its byte limit')
    return payload


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_phase1_predictions(template_payload, predictions_payload, output_dir, *,
                             expected_stock_count=50, expected_date_count=84):
    """Create an immutable research artifact directory; manifest is written last."""
    predictions = parse_prediction_json(predictions_payload)
    options = {'expected_stock_count': expected_stock_count, 'expected_date_count': expected_date_count}
    payload = build_phase1_csv(predictions, template_payload, **options)
    validated = validate_phase1_csv(payload, template_payload, **options)
    destination = Path(output_dir).absolute()
    _no_symlink(destination)
    if '..' in destination.parts or any((parent / '.git').exists() for parent in (destination, *destination.parents)):
        raise Phase1Error('artifacts must be outside Git and use canonical output paths')
    missing = []
    parent = destination.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)  # Fail if it already exists, including an empty directory.
    manifest = {
        'schema_version': 'phase1-format-artifact-v1', **validated,
        'status': 'research_csv_written', 'phase': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'prediction_json_sha256': _sha(predictions_payload),
        'code_sha256': {
            'submission/phase1.py': _sha(Path(__file__).read_bytes()),
            'ingestion/course.py': _sha((Path(__file__).resolve().parents[1] / 'ingestion/course.py').read_bytes()),
        },
        'historical_availability_verified': False, 'model_validated': False,
        'limitation': 'Formatting only; input predictions are not certified as independent of outcomes.',
    }
    manifest_path = destination / 'manifest.json'
    try:
        _exclusive_write(destination / 'predictions.csv', payload)
        _exclusive_write(manifest_path, _json_bytes(manifest))
        _sync_directory(destination)
        _sync_directory(destination.parent)
    except BaseException:
        manifest_path.unlink(missing_ok=True)
        raise
    return {**manifest, 'directory': str(destination)}
