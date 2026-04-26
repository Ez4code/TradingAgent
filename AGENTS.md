# AGENTS.md

## Project Goal

Build a reproducible A-share Alpha Factory research system.

This system is for factor research only. It must not provide investment advice, connect to live trading, or claim guaranteed returns.

The system should first prove whether stable alpha exists, not build a complex production trading platform.

## Core Design Principles

1. Do not let LLM freely invent factor expressions.
2. Factors must come from a fixed template library.
3. Python code generates, executes, evaluates, and backtests factors.
4. No future data leakage.
5. No unsafe eval.
6. Keep the system modular, readable, and runnable.
7. Every phase must keep `python main.py` runnable.

## Project Structure

alpha_factory/
  main.py
  config.py
  data/
    data_loader.py
    sample_data_generator.py
  universe/
    universe_filter.py
  factors/
    template_library.py
    factor_generator.py
    factor_engine.py
    operators.py
  processing/
    normalizer.py
    neutralizer.py
    signal_smoother.py
  evaluation/
    factor_evaluator.py
    metrics.py
  backtest/
    backtester.py
  reports/
    report_writer.py
  outputs/
  examples/
    sample_data.csv
  README.md

## Data Requirements

Minimum fields:

date, symbol, open, high, low, close, volume, amount

For demo mode, generate synthetic data.

Later, real data may come from AKShare with qfq adjustment.

## Trading Timeline

Strictly enforce:

- Factor uses data up to T close.
- Signal is generated at T close.
- Trade is executed at T+1 open.
- One-period return is open_{T+2} / open_{T+1} - 1.

Never use T+1 or later information to compute signal_T.

## Universe Rules

For demo mode, use all available synthetic symbols.

For real A-share mode later:

- Rebuild universe monthly.
- Keep universe fixed within each month.
- Exclude ST stocks if data is available.
- Exclude stocks listed less than 120 days if data is available.
- Exclude suspended or non-tradable stocks if data is available.
- Exclude bottom 20% by amount.

If a real-world filter cannot be implemented reliably due to missing data, log a warning. Do not fake the implementation.

## Factor Template Rules

Factor expressions must come from templates.

No arbitrary free-form factor generation.

Initial templates:

1. momentum:
   close / delay(close, N) - 1

2. reversal:
   -1 * (close / delay(close, N) - 1)

3. volatility:
   std(returns, N)

Later templates:

4. inverse_volatility:
   -1 * std(returns, N)

5. price_volume_corr:
   correlation(close, volume, N)

6. amount_momentum:
   mean(amount, N) / delay(mean(amount, N), N) - 1

7. liquidity:
   mean(amount, N)

8. breakout:
   close / max(close, N) - 1

9. distance_to_ma:
   close / mean(close, N) - 1

10. turnover_proxy:
   volume / mean(volume, N)

Allowed windows:

[5, 10, 20, 40, 60]

## Factor Execution Rules

- Do not use eval.
- Use explicit Python functions or operator registry.
- Failed factors must be recorded.
- Duplicate expressions should be skipped using expression hash.

## Cross-Sectional Evaluation

All factors are cross-sectional.

For each trading date:

- Compute factor values for all symbols in that date’s universe.
- Normalize factor values cross-sectionally.
- Compute RankIC as Spearman correlation between factor value and future return.

Do not treat a single-stock time-series correlation as RankIC.

## Processing Rules

Standard processing:

1. winsorize cross-sectionally
2. zscore or rank normalize cross-sectionally
3. optional size neutralization using size_proxy = log(amount)
4. optional signal smoothing using rolling mean over 3 days

## Metrics

At minimum output:

- rank_ic_mean
- rank_ic_std
- rank_icir
- rank_ic_hit_rate
- coverage
- group returns if implemented
- sharpe if backtest is implemented
- max_drawdown if backtest is implemented
- turnover if backtest is implemented

## Backtest Rules

When implemented:

- Long-only.
- Use T+1 open execution.
- Use open_{T+2} / open_{T+1} - 1 return.
- Test Top 50 / Top 100 / Top 200 when enough stocks exist.
- Equal weight.
- Use round_trip_cost = 0.0025.
- Output equity curve and report.

## Output Files

Use outputs/ for generated files.

Expected outputs over phases:

- factor_report.csv
- rejected_factors.csv
- factors_simple_log.csv
- equity_curve.csv
- backtest_report.json
- failed_symbols.csv
- final_summary.md

## Engineering Rules

- Python only.
- Use pandas and numpy.
- Type hints where reasonable.
- Clear logging.
- Clear exceptions.
- No huge single-file implementation.
- Keep phase changes minimal.
- Do not introduce unnecessary dependencies.

## Done Means

For every phase:

1. `python main.py` runs successfully.
2. Required output files are created.
3. No unsafe eval is used.
4. No future data is used in signal generation.
5. README is updated with how to run.
