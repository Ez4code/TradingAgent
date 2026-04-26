import numpy as np
import pandas as pd


def _spearman_rank_ic(group: pd.DataFrame, factor_col: str, future_return_col: str) -> float:
    valid = group[[factor_col, future_return_col]].dropna()
    if len(valid) < 2:
        return np.nan
    if valid[factor_col].nunique() < 2 or valid[future_return_col].nunique() < 2:
        return np.nan

    factor_rank = valid[factor_col].rank(method="average")
    return_rank = valid[future_return_col].rank(method="average")
    return float(factor_rank.corr(return_rank))


def evaluate_factor(
    data: pd.DataFrame,
    factor_col: str,
    future_return_col: str = "future_return",
) -> dict[str, float | int]:
    rank_ic_values = [
        _spearman_rank_ic(group, factor_col, future_return_col)
        for _, group in data.groupby("date", sort=True)
    ]
    rank_ic = pd.Series(rank_ic_values).dropna()

    valid_pairs = data[[factor_col, future_return_col]].dropna()
    total_future_rows = int(data[future_return_col].notna().sum())
    coverage = len(valid_pairs) / total_future_rows if total_future_rows else 0.0

    rank_ic_mean = float(rank_ic.mean()) if not rank_ic.empty else 0.0
    rank_ic_std = float(rank_ic.std(ddof=1)) if len(rank_ic) > 1 else 0.0
    rank_icir = rank_ic_mean / rank_ic_std if rank_ic_std != 0 else 0.0
    rank_ic_hit_rate = float((rank_ic > 0).mean()) if not rank_ic.empty else 0.0

    return {
        "rank_ic_mean": rank_ic_mean,
        "rank_ic_std": rank_ic_std,
        "rank_icir": float(rank_icir),
        "rank_ic_hit_rate": rank_ic_hit_rate,
        "coverage": float(coverage),
        "valid_observations": int(len(valid_pairs)),
        "rank_ic_dates": int(len(rank_ic)),
    }
