"""Competition evaluation over explicitly matched stock/date keys."""

from .official_score import ScoreResult, evaluate_predictions, official_score

__all__ = ["ScoreResult", "evaluate_predictions", "official_score"]
