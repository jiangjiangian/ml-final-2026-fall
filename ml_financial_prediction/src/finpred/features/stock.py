"""The shared seven stock lags, with no current-day outcome access."""

import math
from datetime import date

from finpred.labels.intraday import finite_number

STOCK_FEATURES = (
    'stock_prev_intraday_return', 'stock_return_between_observed_rows',
    'stock_prev_log_volume', 'stock_prev_rsi', 'stock_prev_atr_fraction',
    'stock_prev_sma_deviation', 'stock_previous_observation_gap_days',
)


def number(value):
    if value is None or (isinstance(value, str) and value.strip().lower() in {'', 'nan', 'null', 'none'}):
        return None
    return finite_number(value, name='raw candidate')


def positive(value):
    result = number(value)
    return result if result is not None and result > 0 else None


def stock_lags(previous_rows, target_date):
    """Use the last two observed rows, retaining a pending predecessor as missing.

    The caller supplies a sorted unique prefix strictly before target_date.
    These are observed-row returns, not certified one-native-session returns.
    """
    day = date.fromisoformat(target_date)
    if day.isoformat() != target_date:
        raise ValueError('target date must be canonical ISO')
    rows = list(previous_rows)
    days = [row['date'] for row in rows]
    if days != sorted(set(days)) or any(value >= target_date for value in days):
        raise ValueError('stock history must be unique, sorted and before target date')
    output = dict.fromkeys(STOCK_FEATURES)
    if not rows:
        return output
    prev = rows[-1]
    output['stock_previous_observation_gap_days'] = (day - date.fromisoformat(prev['date'])).days
    if number(prev['y']) not in (0, 1):
        return output
    close, opening = positive(prev['etl:adj_close']), positive(prev['etl:adj_open'])
    if close and opening:
        output['stock_prev_intraday_return'] = close / opening - 1
        atr, sma = number(prev.get('ATR')), positive(prev.get('SMA'))
        output['stock_prev_atr_fraction'] = atr / close if atr is not None and atr >= 0 else None
        output['stock_prev_sma_deviation'] = close / sma - 1 if sma else None
        if len(rows) > 1 and number(rows[-2]['y']) in (0, 1):
            denominator = positive(rows[-2]['etl:adj_close'])
            if denominator:
                output['stock_return_between_observed_rows'] = close / denominator - 1
    volume = number(prev.get('price:成交股數'))
    output['stock_prev_log_volume'] = math.log1p(volume) if volume is not None and volume >= 0 else None
    output['stock_prev_rsi'] = number(prev.get('RSI'))
    return output
