"""The static benchmark never supplies its own outcomes to fitting or selection."""

from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finpred.features.stock import STOCK_FEATURES
from finpred.features.market import FEATURE_COLUMNS as MARKET_FEATURES
from finpred.training.architecture_comparison import digest
from finpred.training.phase1_forecast import (
    PHASE1_FEATURES, RECIPE, forecast_fixed_phase1, frozen_market_features,
    prepare_phase1_inputs, selection_reference,
)


def market_fixture(stocks, template):
    from finpred.submission.phase1 import template_contract

    contract = template_contract(template, expected_stock_count=len(stocks),
                                 expected_date_count=len(template.decode().splitlines()[0].split(',')) - 1)
    days = sorted({row['date'] for rows in stocks.values() for row in rows} | set(contract['target_dates']))
    rows = []
    for stock in sorted(stocks):
        for index, day in enumerate(days):
            rows.append({'stock_id': stock, 'target_date': day,
                         'feature_cutoff': day + 'T08:10:00+08:00', 'feature_present': index > 0,
                         **dict.fromkeys(STOCK_FEATURES),
                         **{name: index / 1000 for name in MARKET_FEATURES}})
    return json.dumps({'schema_version': 'sequence-feature-table-v1', 'readiness': 'research_assumption',
                       'production_eligible': False, 'feature_columns': list(PHASE1_FEATURES),
                       'market_feature_columns': list(MARKET_FEATURES), 'stock_ids': sorted(stocks),
                       'target_dates': days, 'rows': rows}).encode()


def fixture():
    stocks = ['0003', '0001', '0002']
    rows = {}
    dates = [(date(2026, 5, 1) + timedelta(days=i)).isoformat() for i in range(33)]
    for index, stock in enumerate(stocks):
        rows[stock] = [{'date': day, 'y': (i + index) % 2, 'etl:adj_open': 100,
                        'etl:adj_close': 101 if (i + index) % 2 else 99,
                        'price:成交股數': 1000 + i, 'RSI': 50 + i % 3,
                        'ATR': 1, 'SMA': 100} for i, day in enumerate(dates)]
    template = ('id,2026-06-01,2026-06-02\n' + ''.join(stock + ',0,0\n' for stock in stocks)).encode()
    report = {'schema_version': 'architecture-comparison-v1', 'completed_fit_count': 48,
              'holdout_evaluated': False, 'feature_columns': list(PHASE1_FEATURES),
              'feature_metadata': {'market_feature_columns': list(MARKET_FEATURES),
                                   'feature_document_sha256': digest(json.loads(market_fixture(rows, template)))},
              'validation_selected_configuration': {'config_id': 'M3-2', 'model_id': 'M3', 'value': .1,
                    'fixed_design': {'lookback': 20, 'hidden_channels': 32, 'epochs': 20}},
              'folds': [{'end': '2025-04-01'}, {'end': '2025-07-01'},
                        {'end': '2025-10-01'}, {'end': '2026-01-01'}],
              'configuration_scores': {'M3-2': .001}}
    return rows, template, json.dumps(report).encode()


def prepare(rows, template):
    report = json.loads(fixture()[2])
    market = market_fixture(rows, template)
    report['feature_metadata']['feature_document_sha256'] = digest(json.loads(market))
    return prepare_phase1_inputs(rows, template, [], market_feature_rows_payload=market,
                                 selection_report_payload=json.dumps(report).encode(),
                                 expected_stock_count=3, expected_date_count=2)


class Phase1ForecastTests(unittest.TestCase):
    def test_only_prefix_constructs_labels_and_every_target_slot_is_kept(self):
        rows, template, _ = fixture()
        training, features, panel, contract, evidence = prepare(rows, template)
        self.assertEqual(len(training['rows']), 31 * 3)
        self.assertTrue(all(row['target_date'] < '2026-06-01' for row in training['rows']))
        self.assertEqual(len(evidence), 6)
        self.assertEqual(panel.stocks, sorted(rows))
        self.assertTrue(panel.feature_metadata['complete_feature_universe'])
        for day in contract['target_dates']:
            position = panel.dates.index(day)
            self.assertFalse(panel.label_mask[position].any())
            self.assertTrue(panel.feature_present[position].all())
        self.assertFalse(any('y' in row or 'adj_close' in row for row in features['rows']))
        self.assertTrue(all(previous < row['target_date'] for row in evidence
                            for previous in row['source_observation_dates']))

    def test_current_outcomes_cannot_change_current_features_or_training(self):
        rows, template, _ = fixture()
        training, features, *_ = prepare(rows, template)
        changed = deepcopy(rows)
        for values in changed.values():
            # Last target has no later prediction: none of its outcomes are read.
            values[-1].update(y='unavailable-secret-outcome', **{'etl:adj_open': 'unreadable',
                                                              'etl:adj_close': 'unreadable'})
        training2, features2, *_ = prepare(changed, template)
        self.assertEqual(training, training2)
        self.assertEqual(features, features2)
        changed = deepcopy(rows)
        for values in changed.values():
            for row in values:
                if row['date'] >= '2026-06-01':
                    row['y'] = 1 - row['y']
        self.assertEqual(prepare(changed, template)[1], features)

    def test_pending_predecessor_is_not_replaced_with_an_older_complete_row(self):
        rows, template, _ = fixture()
        for values in rows.values():
            values[-2]['y'] = -1
        _, features, panel, *_ = prepare(rows, template)
        target_rows = [row for row in features['rows'] if row['target_date'] == '2026-06-02']
        self.assertEqual(len(target_rows), 3)
        self.assertTrue(all(row['stock_prev_intraday_return'] is None for row in target_rows))
        self.assertTrue(all(row['stock_previous_observation_gap_days'] == 1 for row in target_rows))
        self.assertTrue(panel.feature_present[panel.dates.index('2026-06-02')].all())

    def test_fixed_selection_cannot_switch_recipe_or_use_phase1_validation(self):
        _, _, payload = fixture()
        selection_reference(payload)
        for mutation in ('recipe', 'dropout', 'future_fold', 'holdout', 'feature'):
            report = json.loads(payload)
            if mutation == 'recipe':
                report['validation_selected_configuration']['config_id'] = 'M4-2'
            elif mutation == 'dropout':
                report['validation_selected_configuration']['value'] = .2
            elif mutation == 'future_fold':
                report['folds'][-1]['end'] = '2026-09-30'
            elif mutation == 'holdout':
                report['holdout_evaluated'] = True
            else:
                report['feature_columns'].append('target_intraday_return')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                selection_reference(json.dumps(report).encode())

    def test_frozen_market_binding_rejects_changed_cutoff_outcomes_and_stock_specific_vectors(self):
        stocks, template, report_payload = fixture()
        payload = market_fixture(stocks, template)
        market, binding = frozen_market_features(payload, report_payload, stocks)
        self.assertEqual(binding['market_feature_columns'], list(MARKET_FEATURES))
        self.assertEqual(len(market), 33)
        for mutation in ('hash', 'cutoff', 'outcome', 'stock_vector', 'duplicate'):
            with self.subTest(mutation=mutation):
                document, report = json.loads(payload), json.loads(report_payload)
                if mutation == 'cutoff':
                    document['rows'][0]['feature_cutoff'] = '2026-05-01T09:10:00+08:00'
                elif mutation == 'outcome':
                    document['rows'][0]['y'] = 1
                elif mutation in {'hash', 'stock_vector'}:
                    document['rows'][0][MARKET_FEATURES[0]] = 99
                else:
                    document['rows'][0] = document['rows'][1]
                if mutation != 'hash':
                    report['feature_metadata']['feature_document_sha256'] = digest(document)
                with self.assertRaises(ValueError):
                    frozen_market_features(json.dumps(document).encode(), json.dumps(report).encode(), stocks)

    def test_missing_frozen_market_date_cannot_silently_change_the_winner_feature_configuration(self):
        stocks, template, report_payload = fixture()
        document, report = json.loads(market_fixture(stocks, template)), json.loads(report_payload)
        document['target_dates'].remove('2026-05-01')
        document['rows'] = [row for row in document['rows'] if row['target_date'] != '2026-05-01']
        report['feature_metadata']['feature_document_sha256'] = digest(document)
        with self.assertRaisesRegex(ValueError, 'cover every'):
            prepare_phase1_inputs(stocks, template, [], market_feature_rows_payload=json.dumps(document).encode(),
                selection_report_payload=json.dumps(report).encode(), expected_stock_count=3, expected_date_count=2)

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'optional neural extra absent')
    def test_exact_one_frozen_fit_produces_complete_immutable_formatter_artifacts(self):
        from finpred.models.temporal import TemporalRegressor

        rows, template, report = fixture()
        calls = []

        class CountedModel(TemporalRegressor):
            def __init__(self, **kwargs):
                calls.append(('configuration', kwargs))
                super().__init__(**kwargs)

            def fit(self, values, returns, mask, train):
                calls.append(('fit', len(train)))
                if mask[-2:].any():
                    raise AssertionError('Phase 1 target labels reached fitting')
                return super().fit(values, returns, mask, train)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'forecast'
            with patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')):
                result = forecast_fixed_phase1(rows, template, output, source_snapshots=[],
                        archive_provenance=[], selection_report_payload=report,
                        market_feature_rows_payload=market_fixture(rows, template),
                        expected_stock_count=3, expected_date_count=2, _model_factory=CountedModel)
            self.assertEqual([name for name, _ in calls].count('fit'), 1)
            self.assertEqual(calls[0], ('configuration', RECIPE))
            self.assertEqual(result['prediction_count'], 6)
            self.assertTrue(result['no_phase1_labels_used'])
            self.assertFalse(result['phase1_targets_scored'])
            self.assertFalse(result['production_eligible'])
            self.assertFalse(result['submitted'])
            self.assertEqual(result['training_label_end_date'], '2026-05-31')
            self.assertEqual(set(json.loads((output / 'predictions.json').read_bytes())['predictions'][0]),
                             {'stock_id', 'target_date', 'prediction'})
            csv = (output / 'submission/predictions.csv').read_text().splitlines()
            self.assertEqual([row.split(',')[0] for row in csv[1:]], ['0003', '0001', '0002'])
            self.assertTrue((output / 'registration.json').is_file())
            self.assertTrue((output / 'model/weights.npz').is_file())
            self.assertEqual(len(result['artifact_sha256']), 13)
            self.assertEqual((output / 'selection-report.json').read_bytes(), report)
            with self.assertRaises(FileExistsError):
                forecast_fixed_phase1(rows, template, output, source_snapshots=[],
                        archive_provenance=[], selection_report_payload=report,
                        market_feature_rows_payload=market_fixture(rows, template),
                        expected_stock_count=3, expected_date_count=2, _model_factory=CountedModel)


if __name__ == '__main__':
    unittest.main()
