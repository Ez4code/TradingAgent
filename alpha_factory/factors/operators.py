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


def rolling_min_by_symbol(
    data: pd.DataFrame,
    column: str,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    periods = window if min_periods is None else min_periods
    return data.groupby("symbol", sort=False)[column].transform(
        lambda values: values.rolling(window=window, min_periods=periods).min()
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


def kdj_j_by_symbol(data: pd.DataFrame, window: int) -> pd.Series:
    low_n = rolling_min_by_symbol(data, "low", window)
    high_n = rolling_max_by_symbol(data, "high", window)
    range_n = high_n - low_n
    rsv = ((data["close"] - low_n) / range_n.where(range_n != 0.0)) * 100.0

    def _ewm(values: pd.Series) -> pd.Series:
        return values.ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()

    k_line = rsv.groupby(data["symbol"], sort=False).transform(_ewm)
    d_line = k_line.groupby(data["symbol"], sort=False).transform(_ewm)
    return 3.0 * k_line - 2.0 * d_line
