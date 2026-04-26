import numpy as np
import pandas as pd


MATCH_REPORT_COLUMNS = [
    "factor",
    "symbol",
    "rank",
    "obs_count",
    "corr_spearman",
    "corr_pearson",
    "positive_signal_count",
    "positive_signal_hit_rate",
    "avg_return_when_positive_signal",
    "avg_return_when_nonpositive_signal",
    "last_signal_date",
    "last_factor_value",
    "last_future_return",
]


def match_stocks_to_factor(
    data: pd.DataFrame,
    factor_col: str,
    factor_name: str,
    future_return_col: str = "future_return",
    min_obs: int = 30,
    positive_only: bool = True,
    top_n: int = 0,
) -> list[dict[str, object]]:
    rows = []
    required = ["date", "symbol", factor_col, future_return_col]
    valid_data = data[required].dropna().copy()
    if valid_data.empty:
        return rows

    for symbol, group in valid_data.groupby("symbol", sort=False):
        match = _match_one_symbol(
            group=group.sort_values("date"),
            factor_col=factor_col,
            future_return_col=future_return_col,
            factor_name=factor_name,
            symbol=str(symbol),
            min_obs=min_obs,
        )
        if match is None:
            continue
        if positive_only and float(match["corr_spearman"]) <= 0.0:
            continue
        rows.append(match)

    rows = sorted(rows, key=lambda item: float(item["corr_spearman"]), reverse=True)
    if top_n > 0:
        rows = rows[:top_n]
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _match_one_symbol(
    group: pd.DataFrame,
    factor_col: str,
    future_return_col: str,
    factor_name: str,
    symbol: str,
    min_obs: int,
) -> dict[str, object] | None:
    obs_count = len(group)
    if obs_count < min_obs:
        return None
    if group[factor_col].nunique() < 2 or group[future_return_col].nunique() < 2:
        return None

    corr_spearman = _spearman_corr(group[factor_col], group[future_return_col])
    corr_pearson = group[factor_col].corr(group[future_return_col])
    if not np.isfinite(corr_spearman):
        return None

    positive_signal = group[factor_col] > 0.0
    positive_returns = group.loc[positive_signal, future_return_col]
    nonpositive_returns = group.loc[~positive_signal, future_return_col]
    last_row = group.iloc[-1]

    return {
        "factor": factor_name,
        "symbol": symbol,
        "rank": 0,
        "obs_count": int(obs_count),
        "corr_spearman": float(corr_spearman),
        "corr_pearson": float(corr_pearson) if np.isfinite(corr_pearson) else np.nan,
        "positive_signal_count": int(positive_signal.sum()),
        "positive_signal_hit_rate": _positive_hit_rate(positive_returns),
        "avg_return_when_positive_signal": _mean_or_nan(positive_returns),
        "avg_return_when_nonpositive_signal": _mean_or_nan(nonpositive_returns),
        "last_signal_date": pd.to_datetime(last_row["date"]).date().isoformat(),
        "last_factor_value": float(last_row[factor_col]),
        "last_future_return": float(last_row[future_return_col]),
    }


def _spearman_corr(left: pd.Series, right: pd.Series) -> float:
    left_rank = left.rank(method="average")
    right_rank = right.rank(method="average")
    corr = left_rank.corr(right_rank)
    return float(corr) if corr is not None else np.nan


def _positive_hit_rate(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    return float((returns > 0.0).mean())


def _mean_or_nan(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    return float(values.mean())
