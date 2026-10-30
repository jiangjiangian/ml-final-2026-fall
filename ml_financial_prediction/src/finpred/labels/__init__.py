"""Label construction; these outputs are never model input features."""

from .intraday import LabelResult, build_intraday_labels

__all__ = ["LabelResult", "build_intraday_labels"]
