"""Compatibility exports for existing line-metric consumers."""

from coverage_eval.metrics import comparison, measured, merge_lines, normalize_pair
from coverage_eval.workspace import changed_lines

__all__ = ["comparison", "measured", "merge_lines", "normalize_pair", "changed_lines"]
