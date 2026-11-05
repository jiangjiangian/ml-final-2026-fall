"""Official direction-times-intraday-return score, without silent row dropping."""

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from finpred.labels.intraday import finite_number, positive_price, row_key


@dataclass(frozen=True)
class ScoreResult:
    score: float
    accuracy: float
    count: int
    daily_scores: dict[str, float]


def _index(rows: Iterable[Mapping[str, Any]], *, name: str) -> dict:
    result = {}
    for row in rows:
        key = row_key(row)
        if key in result:
            raise ValueError(f"duplicate {name} stock/date key")
        result[key] = row
    return result


def evaluate_predictions(
    predictions: Iterable[Mapping[str, Any]], labels: Iterable[Mapping[str, Any]], *,
    expected_keys: Iterable[tuple[str, str]] | None = None,
) -> ScoreResult:
    """Score every required pair using complete label rows.

    Default coverage is the entire provided label set; predictions must match it
    exactly. For a template-defined subset pass ``expected_keys`` explicitly:
    predictions must match that set exactly and labels must cover it (extra
    historical labels are permitted). Missing or pending labels always fail.
    Prices belong only to labels/evaluation, never to premarket inputs.
    """
    pred = _index(predictions, name="prediction")
    truth = _index(labels, name="label")
    if expected_keys is None:
        required = set(truth)
    else:
        expected = list(expected_keys)
        canonical = []
        for item in expected:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("expected_keys entries must be (stock_id, target_date) tuples")
            canonical.append(row_key({"stock_id": item[0], "target_date": item[1]}))
        required = set(canonical)
        if len(required) != len(canonical):
            raise ValueError("duplicate expected stock/date key")
    if not required:
        raise ValueError("evaluation requires a nonempty target universe")
    if set(pred) != required:
        raise ValueError("prediction keys must match the required target universe exactly")
    if not required <= set(truth):
        raise ValueError("labels do not cover the required target universe")
    scores = []
    correct = 0
    daily = {}
    for key in sorted(required, key=lambda value: (value[1], value[0])):
        prediction = finite_number(pred[key].get("prediction"), name="prediction")
        if prediction not in (0, 1):
            raise ValueError("prediction must be binary 0 or 1")
        row = truth[key]
        y = finite_number(row.get("y"), name="y")
        if y not in (0, 1):
            raise ValueError("evaluation requires complete binary labels")
        opening = positive_price(row.get("adj_open"), name="adj_open")
        closing = positive_price(row.get("adj_close"), name="adj_close")
        if int(closing > opening) != y:
            raise ValueError("label y disagrees with adjusted prices")
        intraday_return = (closing - opening) / opening
        if not math.isfinite(intraday_return):
            raise ValueError("intraday return must be finite")
        if "target_intraday_return" in row:
            stored = finite_number(row["target_intraday_return"], name="target_intraday_return")
            if not math.isclose(stored, intraday_return, rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError("stored intraday return disagrees with adjusted prices")
        contribution = (2 * prediction - 1) * intraday_return
        scores.append(contribution)
        daily.setdefault(key[1], []).append(contribution)
        correct += int(prediction == y)
    return ScoreResult(
        score=math.fsum(scores) / len(scores), accuracy=correct / len(scores),
        count=len(scores),
        daily_scores={day: math.fsum(values) / len(values) for day, values in daily.items()},
    )


def official_score(predictions, labels, *, expected_keys=None) -> float:
    """Return only the official score; use evaluate_predictions for diagnostics."""
    return evaluate_predictions(predictions, labels, expected_keys=expected_keys).score
