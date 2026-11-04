"""Preflight or fit the frozen Phase 1 recipe once; no scoring or submission."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from finpred.submission.phase1 import read_input_bytes  # noqa: E402
from finpred.training.phase1_forecast import (  # noqa: E402
    RECIPE, forecast_fixed_phase1, load_source_manifests, prepare_phase1_inputs, selection_reference,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest', type=Path, action='append', required=True)
    parser.add_argument('--selection-report', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--allow-research-assumptions', action='store_true', required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if not args.preflight_only and args.out_dir is None:
        parser.error('--out-dir is required for a fixed fit')
    try:
        stocks, template, snapshots, archive_provenance = load_source_manifests(args.source_manifest)
        report = read_input_bytes(args.selection_report)
        selection_reference(report)
        if args.preflight_only:
            table, features, panel, contract, evidence = prepare_phase1_inputs(stocks, template, archive_provenance)
            result = {'status': 'phase1_preflight_passed', 'stock_count': len(panel.stocks),
                      'date_count': len(contract['target_dates']), 'prediction_count': len(evidence),
                      'training_rows': len(table['rows']),
                      'training_label_end_date': max(row['target_date'] for row in table['rows']),
                      'template_start': contract['target_dates'][0], 'template_end': contract['target_dates'][-1],
                      'feature_slots': len(features['rows']), 'recipe_id': 'M3-2', 'recipe': RECIPE,
                      'historical_availability_verified': False, 'model_fit_count': 0,
                      'source_snapshots': snapshots}
        else:
            result = forecast_fixed_phase1(stocks, template, args.out_dir, source_snapshots=snapshots,
                    archive_provenance=archive_provenance, selection_report_payload=report)
            result = {key: result[key] for key in ('status', 'directory', 'manifest_path', 'recipe_id',
                                                  'prediction_count', 'csv_sha256', 'model_fit_count',
                                                  'readiness', 'production_eligible', 'submitted')}
    except Exception as error:
        print(json.dumps({'status': 'blocked', 'error_type': type(error).__name__, 'submitted': False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
