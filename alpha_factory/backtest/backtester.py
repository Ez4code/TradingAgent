from typing import Any

import numpy as np
import pandas as pd

from alpha_factory.config import BACKTEST_TOP_K_LIST, MIN_AMOUNT_THRESHOLD, ROUND_TRIP_COST, TRADING_DAYS_PER_YEAR


def run_backtest(
    data: pd.DataFrame,
    factor_col: str,
    factor_name: str | None = None,
    top_k_list: list[int] | None = None,
    return_col: str = "future_return",
    round_trip_cost: float = ROUND_TRIP_COST,
    min_amount_threshold: float = MIN_AMOUNT_THRESHOLD,
    enforce_trading_constraints: bool = True,
) -> dict[str, Any]:
    required = {"date", "symbol", factor_col, return_col}
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"backtest data is missing required columns: {missing}")

    factor_label = factor_name or factor_col
    top_ks = top_k_list or BACKTEST_TOP_K_LIST
    sorted_data = data.sort_values(["date", "symbol"]).copy()
    constraint_warnings = _build_constraint_warnings(enforce_trading_constraints)
    if enforce_trading_constraints:
        sorted_data = _add_execution_constraint_columns(sorted_data, min_amount_threshold)

    metrics_by_top_k = {}
    equity_curve = []
    for top_k in top_ks:
        metrics, curve = _run_single_top_k(
            sorted_data,
            factor_col=factor_col,
            factor_name=factor_label,
            top_k=top_k,
            return_col=return_col,
            round_trip_cost=round_trip_cost,
            enforce_trading_constraints=enforce_trading_constraints,
        )
        metrics_by_top_k[f"top{top_k}"] = metrics
        equity_curve.extend(curve)

    return {
        "factor": factor_label,
        "factor_col": factor_col,
        "metrics": metrics_by_top_k,
        "equity_curve": equity_curve,
        "warnings": constraint_warnings,
    }


def _run_single_top_k(
    data: pd.DataFrame,
    factor_col: str,
    factor_name: str,
    top_k: int,
    return_col: str,
    round_trip_cost: float,
    enforce_trading_constraints: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prev_weights = pd.Series(dtype=float)
    equity = 1.0
    benchmark_equity = 1.0
    daily_returns = []
    benchmark_returns = []
    daily_turnover = []
    rows = []

    for date, group in data.groupby("date", sort=True):
        tradable = group[[factor_col, return_col]].dropna()
        if enforce_trading_constraints:
            tradable = tradable.loc[group.loc[tradable.index, "can_buy_next_open"].fillna(False)]
        if tradable.empty:
            continue

        ranked = group.loc[tradable.index, ["symbol", factor_col, return_col]].sort_values(
            [factor_col, "symbol"],
            ascending=[False, True],
        )
        selected = ranked.head(min(top_k, len(ranked)))
        if selected.empty:
            continue

        selected_count = len(selected)
        weights = pd.Series(
            1.0 / selected_count,
            index=selected["symbol"].astype(str),
            dtype=float,
        )
        returns = pd.Series(
            selected[return_col].astype(float).to_numpy(),
            index=selected["symbol"].astype(str),
            dtype=float,
        )

        turnover, blocked_sell_weight = _calculate_turnover(
            prev_weights,
            weights,
            group,
            enforce_trading_constraints=enforce_trading_constraints,
        )
        gross_return = float((weights * returns).sum())
        cost = turnover * round_trip_cost
        net_return = gross_return - cost

        benchmark_return = float(group[return_col].dropna().astype(float).mean())
        equity *= 1.0 + net_return
        benchmark_equity *= 1.0 + benchmark_return

        daily_returns.append(net_return)
        benchmark_returns.append(benchmark_return)
        daily_turnover.append(turnover)
        prev_weights = weights

        rows.append(
            {
                "date": date.date().isoformat(),
                "factor": factor_name,
                "top_k": top_k,
                "gross_return": gross_return,
                "cost": cost,
                "net_return": net_return,
                "benchmark_return": benchmark_return,
                "daily_turnover": turnover,
                "blocked_sell_weight": blocked_sell_weight,
                "equity": equity,
                "benchmark_equity": benchmark_equity,
                "selected_count": selected_count,
            }
        )

    metrics = _calculate_metrics(
        rows=rows,
        daily_returns=daily_returns,
        benchmark_returns=benchmark_returns,
        daily_turnover=daily_turnover,
    )
    return metrics, rows


def _calculate_turnover(
    prev_weights: pd.Series,
    new_weights: pd.Series,
    group: pd.DataFrame,
    enforce_trading_constraints: bool,
) -> tuple[float, float]:
    all_symbols = prev_weights.index.union(new_weights.index)
    prev_aligned = prev_weights.reindex(all_symbols, fill_value=0.0)
    new_aligned = new_weights.reindex(all_symbols, fill_value=0.0)
    delta = new_aligned - prev_aligned
    blocked_sell_weight = 0.0

    if enforce_trading_constraints and "can_sell_next_open" in group.columns:
        sellability = group.set_index(group["symbol"].astype(str))["can_sell_next_open"].reindex(all_symbols, fill_value=True)
        blocked_sells = (delta < 0) & (~sellability.astype(bool))
        blocked_sell_weight = float((-delta.loc[blocked_sells]).sum())
        delta.loc[blocked_sells] = 0.0

    return float(delta.abs().sum()), blocked_sell_weight


def _calculate_metrics(
    rows: list[dict[str, Any]],
    daily_returns: list[float],
    benchmark_returns: list[float],
    daily_turnover: list[float],
) -> dict[str, Any]:
    if not rows:
        return {
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_start": "",
            "max_drawdown_end": "",
            "turnover": 0.0,
            "average_turnover": 0.0,
            "excess_return": 0.0,
            "benchmark_return": 0.0,
            "total_return": 0.0,
            "trading_days": 0,
        }

    returns = pd.Series(daily_returns, dtype=float)
    benchmark = pd.Series(benchmark_returns, dtype=float)
    equity = pd.Series([row["equity"] for row in rows], index=[row["date"] for row in rows], dtype=float)

    total_return = float(equity.iloc[-1] - 1.0)
    benchmark_total_return = float((1.0 + benchmark).prod() - 1.0)
    annual_return = _annualize_return(total_return, len(returns))
    sharpe = _sharpe_ratio(returns)
    max_drawdown, max_drawdown_start, max_drawdown_end = _max_drawdown(equity)

    return {
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "max_drawdown_start": max_drawdown_start,
        "max_drawdown_end": max_drawdown_end,
        "turnover": float(np.sum(daily_turnover)),
        "average_turnover": float(np.mean(daily_turnover)) if daily_turnover else 0.0,
        "excess_return": float(total_return - benchmark_total_return),
        "benchmark_return": benchmark_total_return,
        "total_return": total_return,
        "trading_days": int(len(returns)),
    }


def _annualize_return(total_return: float, trading_days: int) -> float:
    if trading_days <= 0 or total_return <= -1.0:
        return 0.0
    return float((1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / trading_days) - 1.0)


def _sharpe_ratio(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    std = float(returns.std(ddof=1))
    if not np.isfinite(std) or std == 0.0:
        return 0.0
    return float(returns.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(equity: pd.Series) -> tuple[float, str, str]:
    if equity.empty:
        return 0.0, "", ""

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    end = str(drawdown.idxmin())
    max_drawdown = float(drawdown.min())
    if max_drawdown >= 0.0:
        return 0.0, "", ""

    start = str(equity.loc[:end].idxmax())
    return max_drawdown, start, end


def _add_execution_constraint_columns(data: pd.DataFrame, min_amount_threshold: float) -> pd.DataFrame:
    result = data.sort_values(["symbol", "date"]).copy()
    by_symbol = result.groupby("symbol", sort=False)
    result["exec_open"] = by_symbol["open"].shift(-1)
    result["exec_high"] = by_symbol["high"].shift(-1)
    result["exec_low"] = by_symbol["low"].shift(-1)
    result["exec_close"] = by_symbol["close"].shift(-1)
    result["exec_amount"] = by_symbol["amount"].shift(-1)

    has_exec_prices = result[["exec_open", "exec_high", "exec_low", "exec_close", "exec_amount"]].notna().all(axis=1)
    has_amount = result["exec_amount"] > min_amount_threshold
    one_price_board = (
        np.isclose(result["exec_open"], result["exec_high"])
        & np.isclose(result["exec_open"], result["exec_low"])
        & np.isclose(result["exec_open"], result["exec_close"])
    )
    limit_up_approx = (result["exec_open"] / result["close"] - 1.0) >= 0.095
    limit_down_approx = (result["exec_open"] / result["close"] - 1.0) <= -0.095

    result["can_buy_next_open"] = has_exec_prices & has_amount & (~one_price_board) & (~limit_up_approx)
    result["can_sell_next_open"] = has_exec_prices & has_amount & (~one_price_board) & (~limit_down_approx)
    return result


def _build_constraint_warnings(enforce_trading_constraints: bool) -> list[str]:
    if not enforce_trading_constraints:
        return ["Trading constraints disabled."]
    return [
        "Suspension and low-amount tradability are enforced from available next-open OHLCV fields.",
        "Limit-up, limit-down, and one-price-board constraints use approximate OHLC detection because exact daily limit prices are not available in the cached fields.",
        "Blocked sell turnover is not charged when approximate next-open sellability is false; holdings are otherwise re-targeted in this simplified demo backtest.",
    ]
