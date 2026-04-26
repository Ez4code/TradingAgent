import json
import math
from typing import Any

import pandas as pd

from alpha_factory.config import OUTPUTS_DIR


def write_reports(
    summaries: list[dict[str, object]],
    factor_logs: list[dict[str, object]],
    backtest_results: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    data_mode: str = "",
) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_failed_symbols_file(clear=data_mode == "demo")

    summary_df = pd.DataFrame(summaries)
    base_columns = [
        "factor",
        "template_name",
        "window",
        "rank_ic_mean",
        "rank_ic_std",
        "rank_icir",
        "rank_ic_hit_rate",
        "coverage",
        "valid_observations",
        "rank_ic_dates",
        "concentration_risk",
    ]
    backtest_columns = [
        "annual_return_top50",
        "sharpe_top50",
        "max_drawdown_top50",
        "turnover_top50",
        "average_turnover_top50",
        "excess_return_top50",
        "annual_return_top100",
        "sharpe_top100",
        "max_drawdown_top100",
        "turnover_top100",
        "average_turnover_top100",
        "excess_return_top100",
        "annual_return_top200",
        "sharpe_top200",
        "max_drawdown_top200",
        "turnover_top200",
        "average_turnover_top200",
        "excess_return_top200",
    ]
    ordered_columns = [col for col in base_columns + backtest_columns if col in summary_df.columns]
    extra_columns = [col for col in summary_df.columns if col not in ordered_columns]
    summary_df = summary_df[ordered_columns + extra_columns]
    summary_df.to_csv(OUTPUTS_DIR / "factor_report.csv", index=False)

    log_df = pd.DataFrame(factor_logs)
    log_df.to_csv(OUTPUTS_DIR / "factors_simple_log.csv", index=False)

    if backtest_results is not None:
        write_backtest_outputs(backtest_results)

    write_final_summary(
        summaries=summaries,
        backtest_results=backtest_results or [],
        warnings=warnings or [],
        data_mode=data_mode,
    )


def write_backtest_outputs(backtest_results: list[dict[str, Any]]) -> None:
    equity_rows = []
    report = {}
    for result in backtest_results:
        equity_rows.extend(result.get("equity_curve", []))
        report[result["factor"]] = {
            "factor_col": result["factor_col"],
            "metrics": result["metrics"],
            "concentration_risk": result.get("concentration_risk", False),
            "warnings": result.get("warnings", []),
        }

    pd.DataFrame(equity_rows).to_csv(OUTPUTS_DIR / "equity_curve.csv", index=False)
    with open(OUTPUTS_DIR / "backtest_report.json", "w", encoding="utf-8") as file:
        json.dump(_json_safe(report), file, ensure_ascii=False, indent=2)


def write_final_summary(
    summaries: list[dict[str, object]],
    backtest_results: list[dict[str, Any]],
    warnings: list[str],
    data_mode: str,
) -> None:
    lines = [
        "# Final Summary",
        "",
        f"- data_mode: {data_mode or 'unknown'}",
        f"- factor_count: {len(summaries)}",
        f"- backtest_factor_count: {len(backtest_results)}",
        "- trading_timeline: signal uses T close and earlier; simulated return is open_{T+2} / open_{T+1} - 1.",
        "- live_trading: disabled; this is research-only output.",
        "",
        "## A-share Constraint Notes",
        "",
        "- Suspension/low-amount filters are applied when price, volume, and amount fields are available.",
        "- ST filtering is applied only when cached name/is_st fields are available.",
        "- Listing-age filtering uses first cached trading date as an approximation.",
        "- Limit-up, limit-down, and one-price-board backtest constraints use OHLC approximations unless exact limit-price fields are added later.",
        "- Real A-share limit-up/down and suspension rules are not claimed to be fully precise in this phase.",
        "",
        "## Warnings",
        "",
    ]

    if warnings:
        lines.extend(f"- {warning}" for warning in dict.fromkeys(warnings))
    else:
        lines.append("- None")

    with open(OUTPUTS_DIR / "final_summary.md", "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def _ensure_failed_symbols_file(clear: bool = False) -> None:
    path = OUTPUTS_DIR / "failed_symbols.csv"
    if clear or not path.exists():
        pd.DataFrame(columns=["symbol", "name", "error"]).to_csv(path, index=False)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return value
