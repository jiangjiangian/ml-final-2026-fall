"""Bounded four-family research comparisons with full stock/date input panels.

No production bundle or promotion is produced. The 2025 folds were already used
for exploration; January--May 2026 is deliberately never evaluated here.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from finpred.data.training_table import build_research_table
from finpred.evaluation.official_score import evaluate_predictions
from finpred.features.stock import stock_lags
from finpred.labels.intraday import aware_datetime
from finpred.models.temporal import TemporalRegressor
from finpred.training.fit import feature_matrix, target_cutoff, validate_table

DEFAULT_FOLDS = [
    {"name": "2025Q1", "start": "2025-01-01", "end": "2025-04-01"},
    {"name": "2025Q2", "start": "2025-04-01", "end": "2025-07-01"},
    {"name": "2025Q3", "start": "2025-07-01", "end": "2025-10-01"},
    {"name": "2025Q4", "start": "2025-10-01", "end": "2026-01-01"},
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def build_course_sequence_table(stock_rows, *, provenance, market_rows=None,
                                market_report=None, market_features=None):
    """Create all stock/date feature slots separately from completed labels.

    The row at date d uses only that stock's earlier observations. A pending
    current label does not remove its available feature vector or other stocks.
    Targets are the union of observed course dates, not a certified TWSE calendar.
    """
    table = build_research_table(stock_rows, provenance=provenance,
                                market_rows=market_rows, market_report=market_report,
                                market_features=market_features)
    dates = sorted({row['date'] for rows in stock_rows.values() for row in rows})
    market = {row['target_date']: row for row in (market_rows or [])}
    market_columns = [f for f in table['feature_columns'] if not f.startswith('stock_')]
    features = []
    for stock, rows in sorted(stock_rows.items()):
        raw = sorted(rows, key=lambda r: r['date'])
        raw_dates = [r['date'] for r in raw]
        for day in dates:
            end = bisect_left(raw_dates, day)
            row = {'stock_id': stock, 'target_date': day,
                   'feature_cutoff': datetime.combine(date.fromisoformat(day), time(8, 10),
                                                      ZoneInfo('Asia/Taipei')).isoformat(),
                   'feature_present': end > 0}
            row.update(stock_lags(raw[max(0, end - 2):end], day))
            match = market.get(day)
            if match and target_cutoff(row) != aware_datetime(match['feature_cutoff'], name='market cutoff'):
                raise ValueError('market and stock cutoff must agree')
            for column in market_columns:
                value = match.get(column) if match else None
                row[column] = None if value in (None, '') else float(value)
            features.append(row)
    feature_document = {
        'schema_version': 'sequence-feature-table-v1',
        'readiness': 'research_assumption', 'production_eligible': False,
        'availability_evidence': table['availability_evidence'],
        'feature_columns': table['feature_columns'], 'feature_version': table['feature_version'],
        'stock_ids': sorted(stock_rows), 'target_dates': dates, 'rows': features,
        'calendar_basis': 'union_of_observed_course_dates_not_certified_native_sessions',
        'market_feature_columns': market_columns, 'provenance': provenance,
    }
    return table, feature_document


@dataclass
class SequencePanel:
    dates: list[str]
    stocks: list[str]
    features: list[str]
    values: np.ndarray
    feature_present: np.ndarray
    label_mask: np.ndarray
    returns: np.ndarray
    labels: dict
    feature_metadata: dict


def build_sequence_panel(table, *, feature_rows=None, stock_ids=None, target_dates=None,
                         allow_research=False, expected_stocks=50):
    rows, columns = validate_table(table, allow_research=allow_research)
    metadata = feature_rows if isinstance(feature_rows, dict) else {}
    inputs = metadata.get('rows', rows) if isinstance(feature_rows, dict) else (feature_rows or rows)
    if metadata and metadata.get('feature_columns') != columns:
        raise ValueError('sequence features must have the same ordered columns as labels table')
    stocks = list(stock_ids or metadata.get('stock_ids') or sorted({r['stock_id'] for r in rows}))
    dates = list(target_dates or metadata.get('target_dates') or sorted({r['target_date'] for r in inputs}))
    if len(stocks) != expected_stocks or len(stocks) != len(set(stocks)) or any(not isinstance(s, str) or not s for s in stocks):
        raise ValueError('complete distinct stock universe is required')
    if dates != sorted(set(dates)) or any(date.fromisoformat(d).isoformat() != d for d in dates):
        raise ValueError('explicit ordered canonical target dates required')
    day_index, stock_index = ({v: i for i, v in enumerate(items)} for items in (dates, stocks))
    values = np.full((len(dates), len(stocks), len(columns)), np.nan, np.float32)
    present = np.zeros((len(dates), len(stocks)), bool)
    explicit = np.zeros_like(present)
    for row in inputs:
        key = (row['stock_id'], row['target_date'])
        target_cutoff(row)
        if key[0] not in stock_index or key[1] not in day_index:
            raise ValueError('feature key outside fixed universe/calendar')
        d, s = day_index[key[1]], stock_index[key[0]]
        if explicit[d, s]:
            raise ValueError('duplicate sequence feature key')
        explicit[d, s] = True
        values[d, s] = feature_matrix([row], columns)[0]
        if not isinstance(row.get('feature_present', True), bool):
            raise ValueError('feature_present must be boolean and label independent')
        present[d, s] = row.get('feature_present', True)
    labels = {}
    returns = np.full(present.shape, np.nan, np.float32)
    label_mask = np.zeros_like(present)
    for row in rows:
        key = (row['stock_id'], row['target_date'])
        if key[0] not in stock_index or key[1] not in day_index:
            raise ValueError('label outside fixed feature universe/calendar')
        d, s = day_index[key[1]], stock_index[key[0]]
        labels[key] = row
        returns[d, s], label_mask[d, s] = row['target_intraday_return'], True
    return SequencePanel(dates, stocks, columns, values, present, label_mask, returns, labels,
                         {'input_is_separate_from_labels': feature_rows is not None,
                          'explicit_feature_slots': int(explicit.sum()),
                          'expected_feature_slots': int(explicit.size),
                          'missing_feature_slots': int((~explicit).sum()),
                          'complete_feature_universe': bool(explicit.all()),
                          'calendar_basis': metadata.get('calendar_basis', 'provided_target_dates'),
                          'feature_document_sha256': digest(feature_rows) if feature_rows is not None else None,
                          'market_feature_columns': metadata.get('market_feature_columns', [])})


class PanelPreprocessor:
    """Train-only median/scaling; explicit missing and presence channels."""

    def fit(self, panel, train_dates):
        values = panel.values[train_dates].reshape(-1, len(panel.features))
        present = panel.feature_present[train_dates].reshape(-1)
        if not present.any():
            raise ValueError('no available training input features')
        self.imputer = SimpleImputer(strategy='median', keep_empty_features=True)
        self.scaler = StandardScaler()
        self.scaler.fit(self.imputer.fit_transform(values[present]))
        return self

    def transform(self, panel):
        flat = panel.values.reshape(-1, len(panel.features))
        values = self.scaler.transform(self.imputer.transform(flat)).astype(np.float32)
        result = np.concatenate([values, np.isnan(flat).astype(np.float32),
                                 panel.feature_present.reshape(-1, 1).astype(np.float32)], axis=1)
        result[~panel.feature_present.reshape(-1), :len(panel.features)] = 0
        return result.reshape(len(panel.dates), len(panel.stocks), -1)


def default_config():
    # Match the committed blueprint, without relying on the caller's cwd.
    path = Path(__file__).resolve().parents[3] / 'configs/research/model_families.json'
    return json.loads(path.read_text())


def candidate_configurations(config):
    models = config['models']
    if [m['id'] for m in models] != ['M1', 'M2', 'M3', 'M4']:
        raise ValueError('exact four architecture definitions required')
    candidates = []
    for model in models:
        for index, value in enumerate(model['initial_tuning']['values']):
            candidates.append({'config_id': f"{model['id']}-{index + 1}",
                               'model_id': model['id'], 'dimension': model['initial_tuning']['dimension'],
                               'value': value, 'fixed_design': model.get('fixed_design', {})})
    if len(candidates) != 12 or len(candidates) != config['validation']['initial_configuration_budget']:
        raise ValueError('R2 requires exactly the frozen twelve configurations')
    return candidates


def _code_hashes():
    project = Path(__file__).resolve().parents[3]
    files = ['src/finpred/training/architecture_comparison.py', 'src/finpred/models/temporal.py',
             'src/finpred/features/stock.py', 'src/finpred/data/training_table.py',
             'src/finpred/training/fit.py', 'src/finpred/evaluation/official_score.py',
             'src/finpred/labels/intraday.py']
    return {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in files}


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    path.chmod(0o600)


def _folds(folds):
    previous_end = None
    for fold in folds:
        begin, end = date.fromisoformat(fold['start']), date.fromisoformat(fold['end'])
        if begin >= end or end > date(2026, 1, 1) or previous_end and begin < previous_end:
            raise ValueError('ordered disjoint exploration folds must precede spent 2026 holdout')
        previous_end = end
    if not folds or len({f['name'] for f in folds}) != len(folds):
        raise ValueError('nonempty unique fold names required')


def compare_architectures(table, out_dir, *, feature_rows=None, config=None,
                          allow_research=False, quick_smoke=False, folds=None,
                          loaded_input_bytes=None):
    started, start_time = perf_counter(), datetime.now(timezone.utc).isoformat()
    config = default_config() if config is None else config
    candidates = candidate_configurations(config)
    panel = build_sequence_panel(table, feature_rows=feature_rows, allow_research=allow_research)
    if loaded_input_bytes is not None and json.loads(loaded_input_bytes) != table:
        raise ValueError('input buffer disagrees with table')
    folds = list(DEFAULT_FOLDS if folds is None else folds)
    _folds(folds)
    if quick_smoke:
        candidates = [c for c in candidates if c['config_id'].endswith('-1')]
        folds = folds[:1]
    elif folds != DEFAULT_FOLDS:
        raise ValueError('full R2 comparison requires the four frozen quarterly folds')
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError('immutable comparison directory must be empty')
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    out.chmod(0o700)
    code_hashes = _code_hashes()
    project = Path(__file__).resolve().parents[3]
    for name, expected in code_hashes.items():
        original = (project / name).read_bytes()
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError('source changed before experiment registration')
        archived = out / 'source_snapshot' / name
        archived.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        archived.write_bytes(original)
        archived.chmod(0o600)
    _write(out / 'experiment_contract.json', {'schema_version': 'r2-frozen-contract-v1',
           'table_sha256': digest(table), 'feature_metadata': panel.feature_metadata,
           'configuration_sha256': digest(config), 'configurations': candidates, 'folds': folds,
           'quick_smoke_not_full_research': quick_smoke, 'seed': 42,
           'metric': 'mean((2*prediction-1)*target_intraday_return)',
           'holdout_evaluated': False, 'code_sha256': code_hashes})
    results, predictions, baseline_results, fold_evidence = [], [], [], []
    for fold in folds:
        train = np.array([i for i, day in enumerate(panel.dates) if '2020-01-01' <= day < fold['start']])
        valid = np.array([i for i, day in enumerate(panel.dates) if fold['start'] <= day < fold['end']])
        if not len(train) or not len(valid):
            raise ValueError('every fold needs earlier train and validation dates')
        if quick_smoke:
            train, valid = train[-12:], valid[:2]
        first_valid = panel.dates[int(valid[0])]
        cutoff = datetime.combine(date.fromisoformat(first_valid), time(8, 10), ZoneInfo('Asia/Taipei'))
        late = {day for (_, day), row in panel.labels.items() if day < first_valid
                and row.get('label_available_at') is not None
                and aware_datetime(row['label_available_at'], name='label release') > cutoff}
        train = np.array([i for i in train if panel.dates[int(i)] not in late], dtype=int)
        if not len(train):
            raise ValueError('all training dates blocked by label release')
        valid_days = {panel.dates[int(i)] for i in valid}
        labels = [row for (_, day), row in panel.labels.items() if day in valid_days]
        if not labels:
            raise ValueError('validation has no complete labels')
        train_mask = panel.label_mask[train]
        train_y = panel.returns[train][train_mask]
        if not len(train_y):
            raise ValueError('no eligible completed training labels')
        preprocessing = PanelPreprocessor().fit(panel, train)
        values = preprocessing.transform(panel)
        x_train = values[train][train_mask]
        x_valid = values[valid].reshape(-1, values.shape[-1])
        keys = [(sid, panel.dates[int(day)]) for day in valid for sid in panel.stocks]
        required = set(panel.labels).intersection(keys)
        fold_evidence.append({'fold': fold['name'], 'fit_cutoff': cutoff.isoformat(),
                              'train_dates': [panel.dates[int(train[0])], panel.dates[int(train[-1])]],
                              'train_labels': len(train_y), 'validation_labels': len(labels),
                              'predicted_slots': len(keys), 'excluded_late_label_dates': sorted(late),
                              'validation_keys_sha256': digest(sorted(required))})
        for name, direction in [('always_0', 0), ('always_1', 1),
                                ('train_majority', int(np.sum(train_y > 0) > len(train_y) / 2))]:
            baseline = [{'stock_id': s, 'target_date': d, 'prediction': direction} for s, d in keys if (s, d) in required]
            baseline_results.append({'fold': fold['name'], 'name': name,
                                     **asdict(evaluate_predictions(baseline, labels))})
        for candidate in candidates:
            timer = perf_counter()
            model_id, value, fixed = candidate['model_id'], candidate['value'], candidate['fixed_design']
            if model_id == 'M1':
                model = Ridge(alpha=float(value))
                with threadpool_limits(limits=1):
                    model.fit(x_train, train_y)
                    estimates = model.predict(x_valid).reshape(len(valid), len(panel.stocks))
            elif model_id == 'M2':
                model = HistGradientBoostingRegressor(max_leaf_nodes=int(value),
                        max_iter=int(fixed.get('max_iter', 100)), min_samples_leaf=int(fixed.get('min_samples_leaf', 100)),
                        l2_regularization=float(fixed.get('l2_regularization', 1.0)), early_stopping=False, random_state=42)
                with threadpool_limits(limits=1):
                    model.fit(x_train, train_y)
                    estimates = model.predict(x_valid).reshape(len(valid), len(panel.stocks))
            else:
                market_indices = tuple(panel.features.index(f) for f in panel.feature_metadata['market_feature_columns'])
                model = TemporalRegressor(model_id, dropout=float(value), epochs=1 if quick_smoke else int(fixed.get('epochs', 20)),
                          lookback=int(fixed.get('lookback', 20)), hidden=int(fixed.get('hidden_channels', fixed.get('temporal_hidden', 32))),
                          seed=42, batch_dates=128, market_indices=market_indices)
                model.fit(values, panel.returns, panel.label_mask, train)
                estimates = model.predict(values, valid)
            if not np.isfinite(estimates).all():
                raise ValueError('nonfinite predictions')
            elapsed = perf_counter() - timer
            all_rows = [{'stock_id': stock, 'target_date': day, 'prediction': int(estimate > 0),
                         'estimated_return': float(estimate), 'scored': (stock, day) in required,
                         'fold': fold['name'], 'model_id': model_id, 'config_id': candidate['config_id']}
                        for (stock, day), estimate in zip(keys, estimates.ravel(), strict=True)]
            scored_rows = [r for r in all_rows if r['scored']]
            score = asdict(evaluate_predictions(scored_rows, labels))
            predictions.extend(all_rows)
            model_dir = out / fold['name'] / candidate['config_id']
            model_dir.mkdir(parents=True, mode=0o700)
            joblib.dump(preprocessing, model_dir / 'preprocessor.joblib')
            if model_id in {'M1', 'M2'}:
                joblib.dump(model, model_dir / 'estimator.joblib')
            else:
                state = {name: parameter.detach().cpu().numpy() for name, parameter in model.network_.state_dict().items()}
                np.savez(model_dir / 'weights.npz', **state)
            artifact_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model_dir.iterdir()}
            for artifact in model_dir.iterdir():
                artifact.chmod(0o600)
            record = {**candidate, 'fold': fold['name'], **score, 'fit_seconds': elapsed,
                      'model_artifacts_sha256': artifact_hashes, 'production_eligible': False}
            if model_id in {'M3', 'M4'}:
                record.update(epochs=model.epochs, batch_dates=model.batch_dates,
                              train_mse_percentage_point_history=model.loss_history_)
            results.append(record)
            _write(model_dir / 'metadata.json', record)
            _write(model_dir / 'predictions.json', all_rows)
            if _code_hashes() != code_hashes:
                raise ValueError('source changed during comparison; outputs remain unfinalized')
            _write(out / 'progress.json', {'status': 'running', 'completed_fit_count': len(results), 'results': results})
    configuration_scores = {c['config_id']: sum(r['score'] * r['count'] for r in results if r['config_id'] == c['config_id'])
                            / sum(r['count'] for r in results if r['config_id'] == c['config_id']) for c in candidates}
    winner = max(candidates, key=lambda c: configuration_scores[c['config_id']])
    baseline_scores = {name: sum(r['score'] * r['count'] for r in baseline_results if r['name'] == name)
                       / sum(r['count'] for r in baseline_results if r['name'] == name)
                       for name in ['always_0', 'always_1', 'train_majority']}
    if _code_hashes() != code_hashes:
        raise ValueError('source changed during comparison; outputs remain unfinalized')
    report = {'schema_version': 'architecture-comparison-v1', 'readiness': table['readiness'],
              'production_eligible': False, 'production_performance_claim': False,
              'availability_evidence': table['availability_evidence'], 'feature_columns': panel.features,
              'feature_version': table['feature_version'], 'feature_metadata': panel.feature_metadata,
              'input_table_sha256': digest(table), 'input_payload_sha256': hashlib.sha256(loaded_input_bytes).hexdigest() if loaded_input_bytes else None,
              'config_sha256': digest(config), 'configurations': candidates, 'seed': 42,
              'stock_universe': panel.stocks, 'folds': folds, 'fold_evidence': fold_evidence,
              'code_sha256': code_hashes, 'package_versions': {n: version(n) for n in ['numpy', 'scikit-learn', 'torch', 'joblib']},
              'python_version': sys.version, 'started_at': start_time, 'finished_at': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': perf_counter() - started, 'completed_fit_count': len(results),
              'quick_smoke_not_full_research': quick_smoke, 'holdout_evaluated': False,
              'holdout_policy': 'January-May2026 spent; no holdout selection/evaluation in this runner',
              'results': results, 'baseline_results': baseline_results, 'baseline_scores': baseline_scores,
              'configuration_scores': configuration_scores, 'validation_selected_configuration': winner,
              'beats_baseline': configuration_scores[winner['config_id']] > max(baseline_scores.values()),
              'market_context_policy': 'explicit_market_feature_columns' if panel.feature_metadata['market_feature_columns'] else 'known_cross_stock_feature_mean_no_outcomes',
              'selection_metric': 'pooled official score on common labelled keys across frozen 2025 folds'}
    _write(out / 'report.json', report)
    # Keep every 50-stock prediction; ``scored`` identifies the known-label subset.
    _write(out / 'predictions.json', predictions)
    (out / 'progress.json').unlink(missing_ok=True)
    return report
