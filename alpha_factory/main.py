import argparse

from alpha_factory.config import (
    BACKTEST_TOP_K_LIST,
    DATA_MODE,
    DEFAULT_REQUEST,
    DEFAULT_NUM_DAYS,
    DEFAULT_NUM_SYMBOLS,
    SAMPLE_DATA_PATH,
)
from alpha_factory.backtest.backtester import run_backtest
from alpha_factory.data.data_loader import load_data
from alpha_factory.data.sample_data_generator import generate_sample_data
from alpha_factory.evaluation.factor_evaluator import evaluate_factor
from alpha_factory.factors.expression_engine import compute_expression_factor
from alpha_factory.factors.factor_engine import compute_factor
from alpha_factory.factors.factor_generator import generate_factor_plan
from alpha_factory.processing.neutralizer import neutralize_size
from alpha_factory.processing.normalizer import normalize_factor
from alpha_factory.processing.signal_smoother import smooth_signal
from alpha_factory.reports.report_writer import write_reports
from alpha_factory.universe.universe_filter import UniverseFilter


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    request_text = args.request or DEFAULT_REQUEST

    if DATA_MODE == "demo" and not SAMPLE_DATA_PATH.exists():
        print(f"Sample data not found. Generating {SAMPLE_DATA_PATH} ...")
        generate_sample_data(
            output_path=SAMPLE_DATA_PATH,
            num_symbols=DEFAULT_NUM_SYMBOLS,
            num_days=DEFAULT_NUM_DAYS,
        )

    data = load_data(DATA_MODE)
    universe_filter = UniverseFilter(data_mode=DATA_MODE)
    universe = universe_filter.apply(data)
    factor_plan = generate_factor_plan(request_text)

    summaries = []
    factor_logs = []
    backtest_results = []
    warnings = list(data.attrs.get("data_warnings", []))
    warnings.extend(universe_filter.get_warnings())

    print(f"Request: {request_text}")
    print(f"Data mode: {DATA_MODE}")
    print(
        f"Planner mode: {factor_plan['planner']['planner_mode']} "
        f"({factor_plan['planner']['planner_notes']})"
    )

    for generated_factor in factor_plan["generated_factors"]:
        factor_name = generated_factor["factor_name"]
        factor_type = generated_factor.get("factor_type", "template")
        template_name = generated_factor["template_name"]
        window = generated_factor["window"]
        factor_col = f"factor_{factor_name}"
        normalized_col = f"{factor_col}_zscore"
        neutralized_col = f"{factor_col}_neutralized"
        smoothed_col = f"{factor_col}_smoothed"

        if factor_type == "generated_expression":
            factor_data = compute_expression_factor(
                universe,
                expression=generated_factor["expression"],
                output_col=factor_col,
            )
        else:
            factor_data = compute_factor(
                universe,
                template_name=template_name,
                window=window,
                output_col=factor_col,
            )
        factor_data = normalize_factor(
            factor_data,
            factor_col=factor_col,
            output_col=normalized_col,
        )
        factor_data = neutralize_size(
            factor_data,
            factor_col=normalized_col,
            output_col=neutralized_col,
        )
        factor_data = smooth_signal(
            factor_data,
            signal_col=neutralized_col,
            output_col=smoothed_col,
        )

        summary = evaluate_factor(
            factor_data,
            factor_col=smoothed_col,
            future_return_col="future_return",
        )
        backtest_result = run_backtest(
            factor_data,
            factor_col=smoothed_col,
            factor_name=factor_name,
            top_k_list=BACKTEST_TOP_K_LIST,
            return_col="future_return",
        )
        concentration_risk = _detect_concentration_risk(backtest_result["metrics"])
        backtest_result["concentration_risk"] = concentration_risk
        warnings.extend(backtest_result.get("warnings", []))

        summary["factor"] = factor_name
        summary["template_name"] = template_name
        summary["window"] = window
        summary["concentration_risk"] = concentration_risk
        summary.update(_flatten_backtest_metrics(backtest_result["metrics"]))
        summaries.append(summary)
        backtest_results.append(backtest_result)

        factor_logs.append(
            {
                "factor": factor_name,
                "template_name": template_name,
                "template": generated_factor["expression"],
                "window": window,
                "expression_hash": generated_factor["expression_hash"],
                "status": "success",
                "signal_column": smoothed_col,
                "valid_observations": summary["valid_observations"],
                "rank_ic_dates": summary["rank_ic_dates"],
            }
        )

        print(
            f"{factor_name:>10} | "
            f"RankIC mean={summary['rank_ic_mean']:.6f}, "
            f"std={summary['rank_ic_std']:.6f}, "
            f"ICIR={summary['rank_icir']:.6f}, "
            f"hit_rate={summary['rank_ic_hit_rate']:.2%}, "
            f"coverage={summary['coverage']:.2%}, "
            f"sharpe_top50={summary.get('sharpe_top50', 0.0):.6f}"
        )

    write_reports(
        summaries=summaries,
        factor_logs=factor_logs,
        backtest_results=backtest_results,
        warnings=warnings,
        data_mode=DATA_MODE,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Alpha Factory factor research MVP.")
    parser.add_argument(
        "--request",
        type=str,
        default=None,
        help="Natural language factor research request.",
    )
    return parser.parse_args(argv)


def _flatten_backtest_metrics(metrics_by_top_k: dict[str, dict[str, object]]) -> dict[str, object]:
    flattened = {}
    for top_key, metrics in metrics_by_top_k.items():
        for metric_name in [
            "annual_return",
            "sharpe",
            "max_drawdown",
            "turnover",
            "average_turnover",
            "excess_return",
        ]:
            flattened[f"{metric_name}_{top_key}"] = metrics.get(metric_name, 0.0)
    return flattened


def _detect_concentration_risk(metrics_by_top_k: dict[str, dict[str, object]]) -> bool:
    top50 = metrics_by_top_k.get("top50")
    broader = [metrics_by_top_k.get("top100"), metrics_by_top_k.get("top200")]
    broader = [metrics for metrics in broader if metrics]
    if not top50 or not broader:
        return False

    top50_sharpe = float(top50.get("sharpe", 0.0))
    top50_excess = float(top50.get("excess_return", 0.0))
    broader_sharpes = [float(metrics.get("sharpe", 0.0)) for metrics in broader]
    broader_excess = [float(metrics.get("excess_return", 0.0)) for metrics in broader]

    clearly_better = (
        top50_sharpe > max(broader_sharpes) + 0.5
        or top50_excess > max(broader_excess) + 0.05
    )
    broader_bad = any(sharpe < 0.0 and excess < 0.0 for sharpe, excess in zip(broader_sharpes, broader_excess))
    return bool(top50_sharpe > 0.5 and top50_excess > 0.0 and clearly_better and broader_bad)


if __name__ == "__main__":
    main()
