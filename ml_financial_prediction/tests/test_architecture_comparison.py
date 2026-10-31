"""Full-universe sequence assembly, train-only transforms and bounded research."""

from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

try:
    import sklearn  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest('architecture comparisons require the models extra') from error

from finpred.training.architecture_comparison import (
    PanelPreprocessor, build_course_sequence_table, build_sequence_panel,
    candidate_configurations, compare_architectures, default_config,
)


def synthetic_panel():
    days = []
    day = date(2024, 10, 1)
    while len(days) < 80:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    features, labels = [], []
    stocks = [str(1000 + i) for i in range(50)]
    for index, day in enumerate(days):
        for stock_index, stock in enumerate(stocks):
            signal = 1 if (index + stock_index) % 3 else -1
            row = {'stock_id': stock, 'target_date': day,
                   'feature_cutoff': day + 'T08:10:00+08:00',
                   'signal': float(signal), 'market_signal': float(index % 2),
                   'sparse': None if stock_index % 7 == 0 else .1}
            features.append(dict(row))
            labels.append(dict(row, y=int(signal > 0), adj_open=100., adj_close=100. + signal,
                               target_intraday_return=signal / 100,
                               label_available_at=day + 'T23:59:00+08:00'))
    table = {'schema_version': 'training-table-v1', 'readiness': 'synthetic',
             'availability_evidence': 'synthetic test fixture; not market evidence',
             'feature_columns': ['signal', 'market_signal', 'sparse'], 'feature_version': 'synthetic-v1',
             'rows': labels}
    document = {'schema_version': 'sequence-feature-table-v1', 'feature_columns': table['feature_columns'],
                'market_feature_columns': ['market_signal'], 'rows': features,
                'stock_ids': stocks, 'target_dates': days}
    return table, document


class ArchitectureComparisonTests(unittest.TestCase):
    def test_features_of_pending_stock_are_retained_label_independently(self):
        table, inputs = synthetic_panel()
        removed = table['rows'].pop(155)
        panel = build_sequence_panel(table, feature_rows=inputs)
        day, stock = panel.dates.index(removed['target_date']), panel.stocks.index(removed['stock_id'])
        self.assertTrue(panel.feature_present[day, stock])
        self.assertFalse(panel.label_mask[day, stock])
        self.assertTrue(panel.feature_metadata['complete_feature_universe'])
        flat_only = build_sequence_panel(table, target_dates=panel.dates, stock_ids=panel.stocks)
        self.assertEqual(flat_only.feature_metadata['missing_feature_slots'], 1)
        self.assertFalse(flat_only.feature_metadata['complete_feature_universe'])

    def test_validation_features_do_not_fit_preprocessor(self):
        table, inputs = synthetic_panel()
        panel = build_sequence_panel(table, feature_rows=inputs)
        earlier = PanelPreprocessor().fit(panel, np.arange(20))
        original_mean = earlier.scaler.mean_.copy()
        panel.values[20:, :, 0] = 999999
        later = PanelPreprocessor().fit(panel, np.arange(20))
        np.testing.assert_array_equal(original_mean, later.scaler.mean_)

    def test_feature_duplicate_and_foreign_stock_fail_closed(self):
        table, inputs = synthetic_panel()
        inputs['rows'].append(inputs['rows'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_sequence_panel(table, feature_rows=inputs)
        inputs['rows'][-1] = dict(inputs['rows'][0], stock_id='outside')
        with self.assertRaisesRegex(ValueError, 'outside'):
            build_sequence_panel(table, feature_rows=inputs)

    def test_incomplete_stock_universe_and_research_without_opt_in_fail(self):
        table, inputs = synthetic_panel()
        with self.assertRaisesRegex(ValueError, 'universe'):
            build_sequence_panel(table, feature_rows=inputs, stock_ids=inputs['stock_ids'][:-1])
        table['readiness'] = 'research_assumption'
        with self.assertRaisesRegex(ValueError, 'opt-in'):
            build_sequence_panel(table, feature_rows=inputs)
        self.assertEqual(len(build_sequence_panel(table, feature_rows=inputs,
                                                  allow_research=True).stocks), 50)

    def test_config_budget_and_spent_holdout_guards(self):
        config = default_config()
        self.assertEqual(len(candidate_configurations(config)), 12)
        table, inputs = synthetic_panel()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'holdout'):
                compare_architectures(table, root, feature_rows=inputs, quick_smoke=True,
                                      folds=[{'name': 'bad', 'start': '2026-01-01', 'end': '2026-06-01'}])
        config['models'][0]['initial_tuning']['values'].append(99)
        with self.assertRaisesRegex(ValueError, 'twelve'):
            candidate_configurations(config)

    def test_course_builder_never_uses_current_outcome_as_feature(self):
        rows = {}
        for stock in ['1000', '1001']:
            rows[stock] = [{'date': f'2024-01-0{i}', 'y': 1,
                            'etl:adj_open': 100, 'etl:adj_close': 101,
                            'price:成交股數': 1000, 'RSI': 50, 'ATR': 1, 'SMA': 100}
                           for i in range(1, 5)]
        _, initial = build_course_sequence_table(rows, provenance=[])
        rows['1000'][-1]['etl:adj_close'] = 999
        _, changed = build_course_sequence_table(rows, provenance=[])
        self.assertEqual(initial['rows'], changed['rows'])
        self.assertEqual(len(initial['rows']), 8)

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'optional neural extra absent')
    def test_four_family_smoke_executes_and_keeps_all_stock_outputs(self):
        table, inputs = synthetic_panel()
        with tempfile.TemporaryDirectory() as root:
            report = compare_architectures(table, root, feature_rows=inputs, quick_smoke=True)
            self.assertEqual(report['completed_fit_count'], 4)
            self.assertEqual({r['model_id'] for r in report['results']}, {'M1', 'M2', 'M3', 'M4'})
            self.assertTrue(report['quick_smoke_not_full_research'])
            self.assertFalse(report['holdout_evaluated'])
            self.assertFalse(report['production_eligible'])
            predictions = json.loads((Path(root) / 'predictions.json').read_text())
            self.assertEqual(len(predictions), 4 * 2 * 50)
            self.assertEqual(len({(r['stock_id'], r['target_date']) for r in predictions}), 100)
            self.assertTrue((Path(root) / 'experiment_contract.json').exists())
            with self.assertRaisesRegex(ValueError, 'immutable'):
                compare_architectures(table, root, feature_rows=inputs, quick_smoke=True)


if __name__ == '__main__':
    unittest.main()
