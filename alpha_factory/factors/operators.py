import pandas as pd


def delay_by_symbol(data: pd.DataFrame, column: str, periods: int) -> pd.Series:
    return data.groupby("symbol", sort=False)[column].shift(periods)


def rolling_std_by_symbol(
    data: pd.DataFrame,
    column: str,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    periods = window if min_periods is None else min_periods
    return data.groupby("symbol", sort=False)[column].transform(
        lambda values: values.rolling(window=window, min_periods=periods).std()
    )


def rolling_mean_by_symbol(
    data: pd.DataFrame,
    column: str,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    periods = window if min_periods is None else min_periods
    return data.groupby("symbol", sort=False)[column].transform(
        lambda values: values.rolling(window=window, min_periods=periods).mean()
    )


def rolling_max_by_symbol(
    data: pd.DataFrame,
    column: str,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    periods = window if min_periods is None else min_periods
    return data.groupby("symbol", sort=False)[column].transform(
        lambda values: values.rolling(window=window, min_periods=periods).max()
    )


def rolling_corr_by_symbol(
    data: pd.DataFrame,
    left_col: str,
    right_col: str,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    periods = window if min_periods is None else min_periods

    def _corr(group: pd.DataFrame) -> pd.Series:
        return group[left_col].rolling(window=window, min_periods=periods).corr(group[right_col])

    return data.groupby("symbol", sort=False, group_keys=False).apply(_corr)
