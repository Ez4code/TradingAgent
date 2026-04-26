import pandas as pd


def smooth_signal(
    data: pd.DataFrame,
    signal_col: str,
    output_col: str = "smoothed_factor",
    window: int = 3,
) -> pd.DataFrame:
    result = data.sort_values(["symbol", "date"]).copy()
    result[output_col] = result.groupby("symbol", sort=False)[signal_col].transform(
        lambda values: values.rolling(window=window, min_periods=1).mean()
    )
    return result
