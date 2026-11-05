"""Counterexamples for research lags and preserving incomplete source history."""

import copy
import unittest

from finpred.data.training_table import STOCK_FEATURES, build_research_table


def row(day, opening=10, closing=11, y=1):
    return {'date': day, 'etl:adj_open': opening, 'etl:adj_close': closing, 'y': y,
            'ATR': 1, 'SMA': 10, 'RSI': 50, 'price:成交股數': 100}


class TrainingTableTests(unittest.TestCase):
    def test_future_changes_do_not_change_past_features(self):
        rows = {'0050': [row('2025-01-02'), row('2025-01-03'), row('2025-01-06')]}
        before = build_research_table(rows, provenance=[])
        changed = copy.deepcopy(rows)
        changed['0050'][-1] = row('2025-01-06', 100, 90, 0)
        after = build_research_table(changed, provenance=[])
        self.assertEqual(before['readiness'], 'research_assumption')
        self.assertFalse(before['audit']['production_eligible'])
        for b, a in zip(before['rows'], after['rows']):
            self.assertEqual({f: b[f] for f in STOCK_FEATURES}, {f: a[f] for f in STOCK_FEATURES})
        self.assertEqual(before['rows'][0]['stock_id'], '0050')

    def test_pending_previous_row_not_skipped(self):
        table = build_research_table({'A': [row('2025-01-02'), row('2025-01-03', -1, -1, -1), row('2025-01-06')]}, provenance=[])
        self.assertEqual(len(table['rows']), 2)
        self.assertEqual(table['audit']['pending_rows'], 1)
        self.assertIsNone(table['rows'][-1]['stock_prev_intraday_return'])
        self.assertIsNone(table['rows'][-1]['stock_return_between_observed_rows'])

    def test_duplicate_date_rejected_and_missing_market_preserved(self):
        with self.assertRaises(ValueError):
            build_research_table({'A': [row('2025-01-02'), row('2025-01-02')]}, provenance=[])
        table = build_research_table({'A': [row('2025-01-02')]}, provenance=[], market_rows=[], market_report={'status': 'research'})
        self.assertEqual(table['audit']['missing_market_rows'], 1)
        self.assertIsNone(table['rows'][0]['ixic_ret_1s'])

    def test_incompatible_market_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            build_research_table({'A': [row('2025-01-02')]}, provenance=[], market_rows=[{'target_date': '2025-01-02', 'feature_cutoff': '2025-01-02T08:20:00+08:00'}], market_report={'status': 'research'})


if __name__ == '__main__':
    unittest.main()
