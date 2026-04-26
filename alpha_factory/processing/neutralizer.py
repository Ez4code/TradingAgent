import logging

import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)


def neutralize_size(
    data: pd.DataFrame,
    factor_col: str,
    output_col: str = "neutralized_factor",
    amount_col: str = "amount",
    min_samples: int = 3,
) -> pd.DataFrame:
    result = data.copy()
    result[output_col] = result[factor_col]
    fallback_dates = []

    for date, group in result.groupby("date", sort=True):
        valid = (
            group[factor_col].notna()
            & group[amount_col].notna()
            & np.isfinite(group[amount_col])
            & (group[amount_col] > 0)
        )
        if int(valid.sum()) < min_samples:
            fallback_dates.append((date, "insufficient_valid_samples"))
            continue

        valid_group = group.loc[valid, [factor_col, amount_col]]
        size_proxy = np.log(valid_group[amount_col].astype(float))
        if size_proxy.nunique(dropna=True) < 2:
            fallback_dates.append((date, "constant_size_proxy"))
            continue

        y = valid_group[factor_col].astype(float).to_numpy()
        x = size_proxy.to_numpy()
        design = np.column_stack([np.ones(len(x)), x])

        try:
            beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        except np.linalg.LinAlgError:
            fallback_dates.append((date, "regression_failed"))
            continue

        residual = y - design @ beta
        result.loc[valid_group.index, output_col] = residual

    if fallback_dates:
        examples = ", ".join(f"{date.date()}:{reason}" for date, reason in fallback_dates[:5])
        LOGGER.warning(
            "Size neutralization fell back to the original factor on %s dates. Examples: %s",
            len(fallback_dates),
            examples,
        )
        result.attrs["neutralizer_warnings"] = [
            {"date": str(date.date()), "reason": reason} for date, reason in fallback_dates
        ]

    return result
