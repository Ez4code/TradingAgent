import pandas as pd

from alpha_factory.factors.operators import (
    delay_by_symbol,
    kdj_j_by_symbol,
    rolling_corr_by_symbol,
    rolling_max_by_symbol,
    rolling_mean_by_symbol,
    rolling_std_by_symbol,
)


def compute_factor(
    data: pd.DataFrame,
    template_name: str,
    window: int,
    output_col: str = "factor",
) -> pd.DataFrame:
    result = data.copy()

    if template_name == "momentum":
        delayed_close = delay_by_symbol(result, "close", window)
        result[output_col] = result["close"] / delayed_close - 1.0
    elif template_name == "reversal":
        delayed_close = delay_by_symbol(result, "close", window)
        result[output_col] = -1.0 * (result["close"] / delayed_close - 1.0)
    elif template_name == "volatility":
        result[output_col] = rolling_std_by_symbol(result, "returns", window)
    elif template_name == "inverse_volatility":
        result[output_col] = -1.0 * rolling_std_by_symbol(result, "returns", window)
    elif template_name == "price_volume_corr":
        result[output_col] = rolling_corr_by_symbol(result, "close", "volume", window)
    elif template_name == "amount_momentum":
        amount_mean = rolling_mean_by_symbol(result, "amount", window)
        result[output_col] = amount_mean / amount_mean.groupby(result["symbol"], sort=False).shift(window) - 1.0
    elif template_name == "liquidity":
        result[output_col] = rolling_mean_by_symbol(result, "amount", window)
    elif template_name == "breakout":
        result[output_col] = result["close"] / rolling_max_by_symbol(result, "close", window) - 1.0
    elif template_name == "distance_to_ma":
        result[output_col] = result["close"] / rolling_mean_by_symbol(result, "close", window) - 1.0
    elif template_name == "turnover_proxy":
        result[output_col] = result["volume"] / rolling_mean_by_symbol(result, "volume", window)
    elif template_name == "kdj_j_oversold":
        result[output_col] = -1.0 * kdj_j_by_symbol(result, window)
    elif template_name == "kdj_j_rebound":
        j_line = kdj_j_by_symbol(result, window)
        j_delta = j_line.groupby(result["symbol"], sort=False).diff(1)
        result[output_col] = (20.0 - j_line) / 100.0 + j_delta / 100.0
    else:
        raise ValueError(f"unknown factor template: {template_name}")

    return result
