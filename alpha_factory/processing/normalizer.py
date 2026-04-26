import numpy as np
import pandas as pd


def _winsorize(values: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return values
    lower = valid.quantile(lower_q)
    upper = valid.quantile(upper_q)
    return values.clip(lower=lower, upper=upper)


def _zscore(values: pd.Series) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return values

    mean = valid.mean()
    std = valid.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return values.where(values.isna(), 0.0)
    return (values - mean) / std


def normalize_factor(
    data: pd.DataFrame,
    factor_col: str,
    output_col: str,
) -> pd.DataFrame:
    result = data.copy()
    winsorized = result.groupby("date", group_keys=False)[factor_col].transform(_winsorize)
    result[output_col] = winsorized.groupby(result["date"], group_keys=False).transform(_zscore)
    return result
