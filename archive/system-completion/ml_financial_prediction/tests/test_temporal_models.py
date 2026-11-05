"""Temporal causal receptive fields and independent stock/label masks."""

import unittest

import numpy as np

try:
    import torch
except ImportError as error:
    raise unittest.SkipTest('temporal model tests require the optional neural extra') from error

from finpred.models.temporal import CausalTCN, MarketGatedAttention, TemporalRegressor, make_windows


class TemporalModelTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(42)
        torch.set_num_threads(1)

    def test_causal_convolution_cannot_see_later_positions(self):
        model = CausalTCN(3, hidden=8).eval()
        x = torch.randn(2, 3, 20, 3)
        changed = x.clone()
        changed[:, :, 12:] += 1000
        with torch.no_grad():
            original = model.encode_sequence(x)
            later = model.encode_sequence(changed)
        torch.testing.assert_close(original[:, :, :12], later[:, :, :12], rtol=0, atol=0)

    def test_window_padding_keeps_missing_session_position(self):
        values = np.ones((5, 2, 3), dtype=np.float32)
        values[2] = 0  # explicit missing date slot; never compressed away
        window = make_windows(values, [3], lookback=5)[0]
        np.testing.assert_array_equal(window[:, 0], 0)
        np.testing.assert_array_equal(window[:, 3], 0)
        np.testing.assert_array_equal(window[:, 2], 1)
        changed = values.copy()
        changed[4] = 100
        np.testing.assert_array_equal(make_windows(values, [3]), make_windows(changed, [3]))

    def test_attention_batch_day_equivalence_and_all_missing_stocks(self):
        model = MarketGatedAttention(4, market_indices=(1,), hidden=8).eval()
        x = torch.randn(3, 50, 20, 4)
        x[:, :, :, -1] = 1
        x[0, :, :, -1] = 0
        x[2, 1, :, -1] = 0
        with torch.no_grad():
            batch = model(x)
            days = torch.cat([model(day.unsqueeze(0)) for day in x])
        self.assertTrue(torch.isfinite(batch).all())
        torch.testing.assert_close(batch, days, rtol=1e-5, atol=1e-6)

    def test_unknown_labels_do_not_change_fit_or_input_mask(self):
        rng = np.random.default_rng(1)
        values = rng.normal(size=(6, 50, 3)).astype(np.float32)
        values[:, :, -1] = 1
        returns = rng.normal(0, .01, size=(6, 50)).astype(np.float32)
        mask = np.ones((6, 50), dtype=bool)
        mask[:, 3] = False
        changed = returns.copy()
        changed[:, 3] = 999
        a = TemporalRegressor('M4', epochs=1, hidden=8, batch_dates=3, lookback=4)
        b = TemporalRegressor('M4', epochs=1, hidden=8, batch_dates=3, lookback=4)
        a.fit(values, returns, mask, np.arange(5))
        b.fit(values, changed, mask, np.arange(5))
        np.testing.assert_allclose(a.predict(values, [5]), b.predict(values, [5]), rtol=0, atol=0)

    def test_fitted_models_batch_day_and_future_invariance(self):
        rng = np.random.default_rng(7)
        values = rng.normal(size=(9, 50, 4)).astype(np.float32)
        values[:, :, -1] = 1
        values[3, 4] = 0  # a missing stock/date stays a masked slot
        returns = rng.normal(0, .01, size=(9, 50)).astype(np.float32)
        mask = np.ones((9, 50), bool)
        mask[3, 4] = False
        for family in ('M3', 'M4'):
            with self.subTest(family=family):
                model = TemporalRegressor(family, epochs=1, hidden=8, batch_dates=3,
                                          lookback=4, market_indices=(1,))
                model.fit(values, returns, mask, np.arange(6))
                batch = model.predict(values, [6, 7])
                daily = np.concatenate([model.predict(values, [day]) for day in [6, 7]])
                np.testing.assert_allclose(batch, daily, rtol=1e-5, atol=1e-7)
                changed = values.copy()
                changed[8] = 1_000_000
                np.testing.assert_array_equal(batch, model.predict(changed, [6, 7]))


if __name__ == '__main__':
    unittest.main()
