"""Numeric percentile grades shared by report cards and weekly comparisons."""

import pandas as pd


def percentile_grade(baseline, value, higher_is_better=True):
    """Rank a value with average ties, including it as an extra observation.

    This preserves the report cards' existing percentile convention, including
    their neutral fallback when no baseline exists. Missing values stay missing.
    """
    if pd.isna(value):
        return float("nan")
    values = baseline.dropna().astype(float)
    if values.empty:
        return 50.0
    value = float(value)
    if not higher_is_better:
        values, value = -values, -value
    return float(pd.concat([values, pd.Series([value])], ignore_index=True).rank(pct=True).iloc[-1]) * 100.0
