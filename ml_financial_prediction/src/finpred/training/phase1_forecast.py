"""One frozen TCN fit for the static Phase 1 benchmark, without target scoring.

Only pre-template outcomes construct the training table. Prediction inputs are
separate, earlier-observation stock lags; retrospective vintages remain research
assumptions, rather than being upgraded to Phase 2 production evidence.
"""

from bisect import bisect_left
from datetime import date, datetime, time, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

import joblib
import numpy as np

from finpred.data.snapshots import _exclusive_write
from finpred.data.training_table import build_research_table, read_course_archives
from finpred.features.stock import STOCK_FEATURES, number, stock_lags
from finpred.models.temporal import TemporalRegressor
from finpred.submission.phase1 import read_input_bytes, template_contract, write_phase1_predictions
from finpred.training.architecture_comparison import PanelPreprocessor, build_sequence_panel, digest

SOURCE_URLS = {
    'course-training': 'https://final.html2026.csie.org/downloads/fin_pred_data.zip',
    'course-live': 'https://fin-pred-daily.jiangxuehaokeai.chatgpt.site/data.zip',
    'course-template': 'https://final.html2026.csie.org/api/sample-submission',
}
RECIPE = {'family': 'M3', 'dropout': 0.1, 'epochs': 20, 'lookback': 20,
          'hidden': 32, 'seed': 42, 'batch_dates': 128, 'market_indices': ()}
CODE_FILES = (
    'src/finpred/training/phase1_forecast.py', 'src/finpred/training/architecture_comparison.py',
    'src/finpred/models/temporal.py', 'src/finpred/features/stock.py',
    'src/finpred/data/training_table.py', 'src/finpred/training/fit.py',
    'src/finpred/labels/intraday.py', 'src/finpred/submission/phase1.py',
)
FEATURE_INPUT_FIELDS = ('date', 'etl:adj_open', 'etl:adj_close', 'price:成交股數', 'RSI', 'ATR', 'SMA')


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()


def _write_json(path, value):
    _exclusive_write(path, _json_bytes(value))


def _code_hashes():
    project = Path(__file__).resolve().parents[3]
    return {name: _sha((project / name).read_bytes()) for name in CODE_FILES}


def _private_new_directory(value):
    path = Path(value).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('forecast output requires canonical paths without symlinks')
    if any((p / '.git').exists() for p in (path, *path.parents)):
        raise ValueError('forecast artifacts must remain outside Git')
    missing, parent = [], path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    path.mkdir(mode=0o700)  # Even an existing empty directory cannot be reused.
    return path


def load_source_manifests(manifest_paths):
    """Bind exactly the collected official source bytes, retaining true fetch times."""
    payloads, sources = {}, []
    for supplied in manifest_paths:
        path = Path(supplied).absolute()
        raw = read_input_bytes(path)
        record = json.loads(raw)
        source = record.get('source')
        if (record.get('schema_version') != 'snapshot-v1' or source not in SOURCE_URLS
                or source in payloads or record.get('source_url') != SOURCE_URLS[source]
                or record.get('metadata', {}).get('tls_verified') is not True):
            raise ValueError('unique official source snapshots with verified TLS required')
        payload_path = Path(record['payload_path']).absolute()
        payload = read_input_bytes(payload_path, limit=100 * 1024 * 1024)
        if len(payload) != record.get('size_bytes') or _sha(payload) != record.get('sha256'):
            raise ValueError('source payload hash or length changed')
        instant = datetime.fromisoformat(record['fetched_at'].replace('Z', '+00:00'))
        if instant.utcoffset() is None:
            raise ValueError('actual source acquisition time must be timezone aware')
        payloads[source] = payload
        sources.append({'source': source, 'source_url': record['source_url'],
                        'manifest_path': str(path), 'manifest_sha256': _sha(raw),
                        'payload_path': str(payload_path), 'payload_sha256': _sha(payload),
                        'fetched_at': record['fetched_at'], 'tls_verified': True})
    if set(payloads) != set(SOURCE_URLS):
        raise ValueError('training, live and official Phase 1 template snapshots required')
    stocks, archive_provenance = read_course_archives(payloads['course-training'], [payloads['course-live']])
    return stocks, payloads['course-template'], sorted(sources, key=lambda x: x['source']), archive_provenance


def selection_reference(report_payload):
    report = json.loads(report_payload)
    selected = report.get('validation_selected_configuration', {})
    fixed = selected.get('fixed_design', {})
    if (report.get('schema_version') != 'architecture-comparison-v1'
            or report.get('completed_fit_count') != 48 or report.get('holdout_evaluated') is not False
            or report.get('feature_columns') != list(STOCK_FEATURES)
            or selected.get('config_id') != 'M3-2' or selected.get('model_id') != 'M3'
            or selected.get('value') != RECIPE['dropout']
            or fixed.get('lookback') != RECIPE['lookback']
            or fixed.get('hidden_channels') != RECIPE['hidden']
            or fixed.get('epochs') != RECIPE['epochs']
            or len(report.get('folds', [])) != 4
            or any(fold.get('end', '9999') > '2026-01-01' for fold in report['folds'])):
        raise ValueError('frozen completed 2025 R2 M3-2 selection reference required')
    return {'report_sha256': _sha(report_payload), 'recipe_id': 'M3-2',
            'selection_scope': 'completed_2025_exploration_only',
            'phase1_selection_or_scoring': False, 'completed_prior_fits': 48,
            'historical_validation_score': report['configuration_scores']['M3-2']}


def _previous_features(rows, day):
    # Preserve completion/missing state, but discard the directional target y.
    previous = [{**{name: row.get(name) for name in FEATURE_INPUT_FIELDS},
                 'y': 1 if number(row.get('y')) in (0, 1) else -1} for row in rows]
    return stock_lags(previous, day)


def prepare_phase1_inputs(stock_rows, template_payload, provenance, *,
                          expected_stock_count=50, expected_date_count=84):
    contract = template_contract(template_payload, expected_stock_count=expected_stock_count,
                                 expected_date_count=expected_date_count)
    stocks, targets = contract['stock_ids'], contract['target_dates']
    if set(stocks) != set(stock_rows):
        raise ValueError('source stock universe must exactly match official template')
    begin, end = targets[0], targets[-1]
    ordered = {}
    for stock, source_rows in stock_rows.items():
        rows = sorted(source_rows, key=lambda row: row['date'])
        dates = [row['date'] for row in rows]
        if dates != sorted(set(dates)) or any(date.fromisoformat(d).isoformat() != d for d in dates):
            raise ValueError('raw stock observations must have unique canonical dates')
        ordered[stock] = [row for row in rows if row['date'] <= end]
    prefix = {stock: [row for row in rows if row['date'] < begin] for stock, rows in ordered.items()}
    # Do not build a target-outcome table and filter it later: Phase 1 outcomes
    # never enter this function's training/selection/scoring path at all.
    training = build_research_table(prefix, provenance=provenance)
    if any(row['target_date'] >= begin for row in training['rows']):
        raise ValueError('Phase 1 target labels cannot enter training')
    calendar = sorted({row['date'] for rows in ordered.values() for row in rows} | set(targets))
    features, evidence = [], []
    for stock in stocks:
        rows = ordered[stock]
        dates = [row['date'] for row in rows]
        for day in calendar:
            index = bisect_left(dates, day)
            previous = rows[max(0, index - 2):index]
            row = {'stock_id': stock, 'target_date': day,
                   'feature_cutoff': datetime.combine(date.fromisoformat(day), time(8, 10),
                                                      ZoneInfo('Asia/Taipei')).isoformat(),
                   'feature_present': index > 0}
            row.update(_previous_features(previous, day))
            features.append(row)
            if day in targets:
                evidence.append({'stock_id': stock, 'target_date': day,
                                 'source_observation_dates': [item['date'] for item in previous]})
    document = {'schema_version': 'sequence-feature-table-v1', 'readiness': 'research_assumption',
                'production_eligible': False, 'feature_columns': list(STOCK_FEATURES),
                'feature_version': training['feature_version'], 'stock_ids': sorted(stocks),
                'target_dates': calendar, 'rows': features, 'market_feature_columns': [],
                'calendar_basis': 'union_of_observed_course_dates_plus_exact_template_not_certified_native_sessions',
                'availability_evidence': training['availability_evidence'], 'provenance': provenance}
    panel = build_sequence_panel(training, feature_rows=document, allow_research=True,
                                 expected_stocks=expected_stock_count)
    return training, document, panel, contract, evidence


def forecast_fixed_phase1(stock_rows, template_payload, output_dir, *, source_snapshots,
                          archive_provenance, selection_report_payload,
                          expected_stock_count=50, expected_date_count=84,
                          _model_factory=TemporalRegressor):
    """Freeze all inputs, fit exactly once, emit unscored independent predictions."""
    reference = selection_reference(selection_report_payload)
    training, features, panel, contract, evidence = prepare_phase1_inputs(
        stock_rows, template_payload, archive_provenance,
        expected_stock_count=expected_stock_count, expected_date_count=expected_date_count)
    first = contract['target_dates'][0]
    train = np.array([i for i, day in enumerate(panel.dates) if day < first], dtype=int)
    predicted = np.array([panel.dates.index(day) for day in contract['target_dates']], dtype=int)
    if not len(train) or not panel.label_mask[train].any():
        raise ValueError('nonempty pre-template training prefix required')
    if panel.label_mask[predicted].any():
        raise ValueError('Phase 1 label mask must remain empty')
    out = _private_new_directory(output_dir)
    model_dir = out / 'model'
    model_dir.mkdir(mode=0o700)
    training_bytes, feature_bytes = _json_bytes(training), _json_bytes(features)
    _exclusive_write(out / 'training-table.json', training_bytes)
    _exclusive_write(out / 'feature-rows.json', feature_bytes)
    _exclusive_write(out / 'template.csv', template_payload)
    _exclusive_write(out / 'selection-report.json', selection_report_payload)
    _write_json(out / 'feature-evidence.json', evidence)
    code_hashes = _code_hashes()
    packages = {name: version(name) for name in ('numpy', 'scikit-learn', 'joblib', 'torch')}
    project = Path(__file__).resolve().parents[3]
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=project, capture_output=True,
                              text=True, check=True).stdout.strip()
    registration = {'schema_version': 'phase1-fixed-registration-v1',
                    'registered_at': datetime.now(timezone.utc).isoformat(),
                    'scope': 'static_phase1_backtest_not_phase2_production', 'recipe_id': 'M3-2',
                    'recipe': dict(RECIPE, market_indices=[]), 'selection_reference': reference,
                    'template_sha256': _sha(template_payload), 'target_dates': contract['target_dates'],
                    'stock_ids': contract['stock_ids'], 'panel_stock_ids': panel.stocks,
                    'training_rows': len(training['rows']),
                    'training_label_start_date': min(row['target_date'] for row in training['rows']),
                    'training_label_end_date': max(row['target_date'] for row in training['rows']),
                    'training_table_sha256': digest(training), 'training_table_file_sha256': _sha(training_bytes),
                    'feature_rows_sha256': digest(features), 'feature_rows_file_sha256': _sha(feature_bytes),
                    'source_snapshots': source_snapshots, 'code_sha256': code_hashes,
                    'code_git_revision_at_registration': revision, 'package_versions': packages,
                    'readiness': 'research_assumption', 'historical_availability_verified': False,
                    'production_eligible': False, 'no_phase1_labels_used': True,
                    'label_usage_scope': 'no Phase 1 outcomes in fit, selection, or scoring; previous-row completion mask only',
                    'lookback_basis': features['calendar_basis'], 'target_dates_scored': False}
    _write_json(out / 'registration.json', registration)
    registered = (out / 'registration.json').read_bytes()
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    preprocessing = PanelPreprocessor().fit(panel, train)
    values = preprocessing.transform(panel)
    model = _model_factory(**RECIPE)
    model.fit(values, panel.returns, panel.label_mask, train)  # Exactly one fixed fit.
    estimates = np.asarray(model.predict(values, predicted))
    if estimates.shape != (len(predicted), len(panel.stocks)) or not np.isfinite(estimates).all():
        raise ValueError('complete finite Phase 1 prediction matrix required')
    predictions = [{'stock_id': stock, 'target_date': day, 'prediction': int(estimates[d, s] > 0)}
                   for d, day in enumerate(contract['target_dates']) for s, stock in enumerate(panel.stocks)]
    prediction_payload = _json_bytes({'schema_version': 'phase1-predictions-v1',
                                      'readiness': 'research_assumption', 'predictions': predictions})
    _exclusive_write(out / 'predictions.json', prediction_payload)
    formatted = write_phase1_predictions(template_payload, prediction_payload, out / 'submission',
                                         expected_stock_count=expected_stock_count,
                                         expected_date_count=expected_date_count)
    joblib.dump(preprocessing, model_dir / 'preprocessor.joblib')
    state = {name: parameter.detach().cpu().numpy() for name, parameter in model.network_.state_dict().items()}
    np.savez(model_dir / 'weights.npz', **state)
    _write_json(model_dir / 'metadata.json', {'schema_version': 'phase1-tcn-model-v1',
                'recipe_id': 'M3-2', 'recipe': dict(RECIPE, market_indices=[]),
                'readiness': 'research_assumption', 'production_eligible': False,
                'input_channels': int(values.shape[-1]), 'feature_columns': panel.features,
                'feature_version': training['feature_version'], 'stock_ids': panel.stocks,
                'package_versions': packages,
                'training_mse_percentage_point_history': model.loss_history_})
    for path in model_dir.iterdir():
        path.chmod(0o600)
    if _code_hashes() != code_hashes:
        raise ValueError('source changed during the fixed fit; no finalized forecast produced')
    artifacts = {path.relative_to(out).as_posix(): _sha(path.read_bytes())
                 for path in sorted(out.rglob('*')) if path.is_file()}
    for path in sorted(out.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    manifest = {'schema_version': 'phase1-forecast-v1', 'phase': 1,
                'status': 'phase1_forecast_generated', 'generated_at': datetime.now(timezone.utc).isoformat(),
                'recipe_id': 'M3-2', 'registration_sha256': _sha(registered),
                'template_sha256': _sha(template_payload), 'prediction_json_sha256': _sha(prediction_payload),
                'csv_sha256': formatted['csv_sha256'], 'csv_path': 'submission/predictions.csv',
                'stock_count': len(panel.stocks), 'date_count': len(predicted),
                'prediction_count': len(predictions), 'training_label_end_date': registration['training_label_end_date'],
                'no_phase1_labels_used': True, 'model_fit_count': 1, 'phase1_targets_scored': False,
                'source_snapshots': source_snapshots, 'code_sha256': code_hashes,
                'readiness': 'research_assumption', 'historical_availability_verified': False,
                'production_eligible': False, 'submitted': False, 'artifact_sha256': artifacts}
    _write_json(out / 'manifest.json', manifest)
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {'directory': str(out), 'manifest_path': str(out / 'manifest.json'), **manifest}
