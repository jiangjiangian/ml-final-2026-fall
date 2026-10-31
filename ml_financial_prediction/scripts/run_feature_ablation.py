"""Reproduce bounded R1 and separately preregistered E04, never promote models."""

import argparse
import csv
from datetime import datetime, timezone
from dataclasses import asdict
import gzip
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter
import warnings

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from finpred.evaluation.official_score import evaluate_predictions  # noqa: E402
from finpred.training.fit import feature_matrix, target_cutoff, validate_table  # noqa: E402

FOLDS = [
    {'name': '2025Q1', 'start': '2025-01-01', 'end': '2025-04-01'},
    {'name': '2025Q2', 'start': '2025-04-01', 'end': '2025-07-01'},
    {'name': '2025Q3', 'start': '2025-07-01', 'end': '2025-10-01'},
    {'name': '2025Q4', 'start': '2025-10-01', 'end': '2026-01-01'},
]
MODELS = {
    'M1_ridge': {'alpha': 1.0},
    'M2_hist_gbdt': {'max_leaf_nodes': 15, 'max_iter': 100, 'min_samples_leaf': 100,
                     'l2_regularization': 1.0, 'early_stopping': False, 'random_state': 42},
}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def write(out, name, value):
    target = out / name
    target.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    target.chmod(0o600)


def key_hash(rows):
    return sha(json.dumps(sorted((r['stock_id'], r['target_date']) for r in rows)).encode())


def run(expansion_dir, out_dir, *, include_e04=False):
    SOURCE, OUT = Path(expansion_dir).resolve(), Path(out_dir).resolve()
    if any((p / '.git').exists() for p in (OUT, *OUT.parents)):
        raise ValueError('model/prediction outputs must remain outside Git')
    if OUT.exists() and any(OUT.iterdir()):
        raise ValueError('immutable output directory already contains work; do not rerun or overwrite')
    OUT.mkdir(parents=True, mode=0o700, exist_ok=True)
    schema = json.loads((SOURCE / 'frozen_schema.json').read_text())
    source_report = json.loads((SOURCE / 'expansion_report.json').read_text())
    for name, expected in source_report['artifact_sha256'].items():
        if sha((SOURCE / name).read_bytes()) != expected:
            raise ValueError('frozen input hash mismatch: ' + name)
    extra_e04 = [c for c in schema['group_extra_columns']['F3']
                 if not c.startswith(('tw_electronics_', 'tw_semiconductor_', 'tw_financials_'))]
    if len(extra_e04) != 9:
        raise ValueError('expected the frozen nine-column FX/yield diagnostic subset')
    ready_groups = [g for g in ('F0', 'F1', 'F2', 'F3')
                    if source_report['group_status'][g]['status'] == 'research_assumption']
    blocked_slots = [{'group': group, 'model': model, 'fold': fold['name'],
                      'reason': status['reasons']}
                     for group, status in source_report['group_status'].items()
                     if status['status'] == 'blocked' for model in MODELS for fold in FOLDS]
    e04_ready = include_e04 and {'fred_usd_twd', 'fred_us10y'} <= source_report.get('fred_sources', {}).keys()
    groups = ready_groups + (['E04'] if e04_ready else [])
    if 'F0' not in ready_groups:
        raise ValueError('a usable F0 baseline is required')
    registration = {
        'registered_at': datetime.now(timezone.utc).isoformat(),
        'registered_before_new_scores_observed': True,
        'R1': {'group_columns': schema['model_columns'], 'models': MODELS, 'folds': FOLDS,
               'maximum_fits': 32, 'planned_actual_fits': len(ready_groups) * len(MODELS) * len(FOLDS),
               'blocked_slots': blocked_slots},
        'E04': {'requested': include_e04, 'ready': e04_ready,
                'phase': 'separate_fixed_FX_yield_diagnostic_not_replacement_for_blocked_F3',
                'columns': schema['model_columns']['F0'] + extra_e04, 'models': MODELS,
                'folds': FOLDS, 'maximum_fits': 8,
                'reference': 'same-model F0 predictions from R1; no additional F0 fit',
                'vintage_policy': schema['fred_assumption'],
                'not_claimed_complete_F3_or_verified_history': True},
        'holdout_policy': '2026-01..2026-05 spent and never evaluated or tuned here',
        'seed': 42, 'primary_metric': 'mean((2 * prediction - 1) * target_intraday_return)',
        'production_eligible': False,
        'frozen_feature_schema_sha256': schema['schema_sha256'],
        'source_files_sha256': source_report['artifact_sha256'],
        'code_sha256': {Path(__file__).name: sha(Path(__file__).read_bytes()),
                       **{p: sha((ROOT / p).read_bytes()) for p in (
                           'src/finpred/features/research_expansion.py',
                           'src/finpred/training/fit.py', 'src/finpred/features/stock.py',
                           'src/finpred/evaluation/official_score.py',
                           'src/finpred/data/normalization.py', 'src/finpred/ingestion/external.py')}},
        'environment': {'python': sys.version, **{name: version(name)
                                                 for name in ('numpy', 'scikit-learn', 'joblib', 'threadpoolctl')}},
    }
    write(OUT, 'registration.json', registration)
    results, diagnostics, baselines = [], [], []
    all_key_hash = None
    started = perf_counter()
    for group in groups:
        payload = (SOURCE / ('F3.json' if group == 'E04' else group + '.json')).read_bytes()
        table = json.loads(payload)
        if group == 'E04':
            table['readiness'] = 'research_assumption'
            table['feature_columns'] = registration['E04']['columns']
            table['feature_version'] += '-fx-yield-only-E04'
            table['expansion_report'] = {'group': 'E04', 'status': 'research_assumption',
                                         'production_eligible': False,
                                         'not_frozen_F3_replacement': True}
        rows, columns = validate_table(table, allow_research=True)
        current_hash = key_hash(rows)
        if all_key_hash is None:
            all_key_hash = current_hash
        assert current_hash == all_key_hash
        for fold in FOLDS:
            train = [r for r in rows if '2020-01-01' <= r['target_date'] < fold['start']]
            validation = [r for r in rows if fold['start'] <= r['target_date'] < fold['end']]
            cutoff = min(target_cutoff(r) for r in validation)
            train = [r for r in train if datetime.fromisoformat(r['label_available_at']) <= cutoff]
            assert train and validation and max(r['target_date'] for r in train) < min(r['target_date'] for r in validation)
            xtrain = feature_matrix(train, columns)
            xvalidation = feature_matrix(validation, columns)
            ytrain = np.asarray([r['target_intraday_return'] for r in train])
            if group == 'F0':
                for label, prediction in [('always_0', 0), ('always_1', 1),
                                           ('train_majority', int(sum(r['y'] for r in train) > len(train) / 2))]:
                    output = [dict(stock_id=r['stock_id'], target_date=r['target_date'], prediction=prediction)
                              for r in validation]
                    baselines.append({'fold': fold['name'], 'model': label,
                                      **asdict(evaluate_predictions(output, validation))})
            diagnostics.append({'group': group, 'fold': fold['name'], 'fit_cutoff': cutoff.isoformat(),
                                'training_dates': [min(r['target_date'] for r in train), max(r['target_date'] for r in train)],
                                'training_rows': len(train), 'validation_rows': len(validation),
                                'validation_keys_sha256': key_hash(validation),
                                'feature_columns': columns,
                                'training_missing_fraction': {c: float(np.mean(np.isnan(xtrain[:, i])))
                                                              for i, c in enumerate(columns)}})
            for model, params in MODELS.items():
                estimator = Ridge(**params) if model == 'M1_ridge' else HistGradientBoostingRegressor(**params)
                pipeline = Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True,
                                                               keep_empty_features=True)),
                                     ('scaler', StandardScaler()), ('estimator', estimator)])
                fit_started = perf_counter()
                with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                    warnings.simplefilter('always')
                    pipeline.fit(xtrain, ytrain)
                    estimated = pipeline.predict(xvalidation)
                predictions = [dict(stock_id=r['stock_id'], target_date=r['target_date'],
                                    prediction=int(value > 0), estimated_return=float(value))
                               for r, value in zip(validation, estimated)]
                scored = asdict(evaluate_predictions(predictions, validation))
                result = {'group': group, 'fold': fold['name'], 'model': model, 'params': params,
                          'feature_count': len(columns), 'elapsed_seconds': perf_counter() - fit_started,
                          'warnings': sorted({str(w.message) for w in caught}), **scored}
                prediction_name = f'{group}-{model}-{fold["name"]}-predictions.csv.gz'
                with gzip.open(OUT / prediction_name, 'wt', encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
                    writer.writeheader()
                    writer.writerows(predictions)
                (OUT / prediction_name).chmod(0o600)
                result['predictions_path'] = prediction_name
                result['predictions_sha256'] = sha((OUT / prediction_name).read_bytes())
                results.append(result)
                write(OUT, 'progress.json', {'status': 'running', 'completed_fit_count': len(results), 'results': results})
                print(json.dumps({'fits': len(results), 'group': group, 'model': model,
                                  'fold': fold['name'], 'score': scored['score']}), flush=True)
    averages = {}
    for group in groups:
        for model in MODELS:
            subset = [r for r in results if r['group'] == group and r['model'] == model]
            averages[f'{group}/{model}'] = sum(r['score'] * r['count'] for r in subset) / sum(r['count'] for r in subset)
    baseline_scores = {label: sum(r['score'] * r['count'] for r in baselines if r['model'] == label)
                      / sum(r['count'] for r in baselines if r['model'] == label)
                      for label in ('always_0', 'always_1', 'train_majority')}
    report = {'status': 'completed', 'readiness': 'research_assumption', 'production_eligible': False,
              'completed_at': datetime.now(timezone.utc).isoformat(), 'elapsed_seconds': perf_counter() - started,
              'completed_fit_count': len(results),
              'R1_completed_fits': sum(r['group'] != 'E04' for r in results),
              'R1_blocked_fit_slots': len(blocked_slots),
              'E04_completed_fits': sum(r['group'] == 'E04' for r in results),
              'E04_status': 'completed' if e04_ready else ('blocked_missing_FRED_sources' if include_e04 else 'not_requested'), 'registration_sha256': sha((OUT / 'registration.json').read_bytes()),
              'validation_scope': 'already_seen_2025_expanding_quarters_no_new_unseen_test',
              'same_all_stock_date_keys_sha256': all_key_hash,
              'averages': averages, 'baseline_scores': baseline_scores,
              'baseline_results': baselines, 'fold_diagnostics': diagnostics, 'results': results,
              'interpretation': 'No production promotion; blocked groups remain blocked and E04 does not complete F3.'}
    write(OUT, 'report.json', report)
    assert len(results) == len(groups) * len(MODELS) * len(FOLDS)
    print(json.dumps({'status': 'completed', 'averages': averages, 'baseline_scores': baseline_scores,
                      'report': str(OUT / 'report.json')}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expansion-dir', type=Path, required=True,
                        help='Frozen build_research_expansion.py output, including schema, report and group JSON')
    parser.add_argument('--out-dir', type=Path, required=True, help='New private directory outside Git')
    parser.add_argument('--include-e04', action='store_true',
                        help='Preregister eight additional fixed FX/yield fits as a separate phase, not replacement F3')
    args = parser.parse_args()
    try:
        run(args.expansion_dir, args.out_dir, include_e04=args.include_e04)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
